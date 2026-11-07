"""Deployed routes from API Gateway v2 `route_key` values in Terraform.

Reads only literal keys, one `route_key = "METHOD /path"` per line, in `.tf` files under the
configured paths. Everything it cannot read fails closed, because the check cannot say which routes
it serves and refuses to guess:

- an interpolated or computed key (`${...}`, `each.key`, `local.x`) or the `$default` catch-all;
- a `route_key` sharing its line with other syntax;
- JSON Terraform (`*.tf.json`) that mentions an API or a route;
- a route defined outside the configured paths;
- a front door this adapter does not read: a Lambda function URL, a REST API (v1) resource, or an
  HTTP API built from an OpenAPI `body` or a quick-create `target`.

Projects that build routes dynamically use the dispatch adapter instead.
"""
import re
from pathlib import Path
from typing import Iterable, Iterator, List, Set, Tuple

from . import AdapterError, parse_route_key

ROUTE_KEY = re.compile(r"^\s*route_key\s*=\s*(.+?)\s*(?:#.*|//.*)?$", re.M)
ANY_ROUTE_KEY = re.compile(r"\broute_key\s*=")
SKIP = {".terraform", ".git", "node_modules", ".venv", "venv"}
API_MARKERS = ("route_key", "aws_apigatewayv2", "aws_api_gateway_", "aws_lambda_function_url")
OTHER_DOORS = (
    (re.compile(r'resource\s+"aws_lambda_function_url"'),
     "a Lambda function URL is a front door the check cannot see"),
    (re.compile(r'resource\s+"aws_api_gateway_'),
     "a REST API (v1) resource; only HTTP API v2 routes are read"),
)
API_HEADER = re.compile(r'resource\s+"aws_apigatewayv2_api"\s+"[^"]*"\s*\{')
API_ATTR = re.compile(r"^\s*(body|target)\s*=", re.M)


def _files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and (path.name.endswith(".tf") or path.name.endswith(".tf.json")) \
                and not SKIP.intersection(path.relative_to(root).parts):
            yield path


def _api_blocks(text: str) -> Iterator[str]:
    for m in API_HEADER.finditer(text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        if depth:
            raise AdapterError("an aws_apigatewayv2_api block does not close; the check cannot read it")
        yield text[m.end():i - 1]


def deployed_routes(root: Path, paths: Iterable[str]) -> Set[Tuple[str, str]]:
    root = Path(root)
    bases: List[Path] = []
    for rel in paths:
        base = root / rel
        if not base.is_dir():
            raise AdapterError(f"terraform path {rel!r} does not exist under {root}")
        bases.append(base.resolve())

    found: Set[Tuple[str, str]] = set()
    for tf in _files(root):
        rel = tf.relative_to(root)
        text = tf.read_text(encoding="utf-8")
        inside = any(tf.resolve().is_relative_to(b) for b in bases)
        if tf.name.endswith(".tf.json"):
            if inside or any(k in text for k in API_MARKERS):
                raise AdapterError(f"{rel}: JSON Terraform cannot be read; write the routes as .tf")
            continue
        if not inside:
            if ANY_ROUTE_KEY.search(text) or "aws_apigatewayv2_route" in text:
                raise AdapterError(f"{rel}: defines a route outside the configured terraform paths; "
                                   "add its directory to security/config.json adapter.paths")
            continue
        for pattern, why in OTHER_DOORS:
            if pattern.search(text):
                raise AdapterError(f"{rel}: {why}")
        for block in _api_blocks(text):
            attr = API_ATTR.search(block)
            if attr:
                raise AdapterError(f"{rel}: an HTTP API with `{attr.group(1)} =` defines routes this "
                                   "adapter cannot read")
        literal = list(ROUTE_KEY.finditer(text))
        if len(literal) != len(ANY_ROUTE_KEY.findall(text)):
            raise AdapterError(f"{rel}: a route_key shares its line with other syntax; put each on its own line")
        for m in literal:
            where = f"{rel}:{text.count(chr(10), 0, m.start()) + 1}"
            raw = m.group(1)
            if not (raw.startswith('"') and raw.endswith('"')) or "${" in raw:
                raise AdapterError(f"{where}: route_key {raw} is not a literal string; the check cannot verify it")
            found.add(parse_route_key(raw[1:-1], where))
    return found
