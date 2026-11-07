"""Deployed routes from API Gateway v2 `route_key` values in Terraform or OpenTofu.

Reads only literal keys, one `route_key = "METHOD /path"` per line, in `.tf` and `.tofu` files under
the configured paths. Comments, string contents and heredoc bodies are masked before anything is
read, so a brace or a `route_key` inside one changes nothing. Everything it cannot read fails
closed, because the check cannot say which routes it serves and refuses to guess:

- an interpolated or computed key (`${...}`, `each.key`, `local.x`, a conditional) or the
  `$default` catch-all;
- a `route_key` sharing its line with other syntax, or written as a quoted attribute name;
- JSON Terraform (`*.tf.json`, `*.tofu.json`) that mentions an API or a route;
- a route defined outside the configured paths;
- a module from anywhere but a local path that mentions routes or API Gateway;
- anywhere in the repository, a front door this adapter does not read: a Lambda function URL, a
  REST API (v1) resource, or an HTTP API built from an OpenAPI `body` or a quick-create `target`.

This is a pattern reader, not an HCL parser. Projects that build routes dynamically use the
dispatch adapter instead.
"""
import re
from pathlib import Path
from typing import Iterable, Iterator, List, Set, Tuple

from . import AdapterError, parse_route_key

SUFFIXES = (".tf", ".tofu")
JSON_SUFFIXES = (".tf.json", ".tofu.json")
SKIP = {".terraform", ".git", "node_modules"}  # derived or vendored; a module sourced from one is refused
API_MARKERS = ("route_key", "aws_apigatewayv2", "aws_api_gateway_", "aws_lambda_function_url")
LABEL = r'"?[\w-]+"?'
OTHER_DOORS = (
    (re.compile(r'\bresource\s+"?aws_lambda_function_url"?\s'),
     "a Lambda function URL is a front door the check cannot see"),
    (re.compile(r'\bresource\s+"?aws_api_gateway_'),
     "a REST API (v1) resource; only HTTP API v2 routes are read"),
)
API_HEADER = re.compile(r'\bresource\s+"?aws_apigatewayv2_api"?\s+' + LABEL + r'\s*\{')
MODULE_HEADER = re.compile(r'\bmodule\s+' + LABEL + r'\s*\{')
TOP_ATTR = re.compile(r'(?:^|[\s{;])(body|target)\s*=')
SOURCE = re.compile(r'(?:^|[\s{;])source\s*=\s*"([^"]*)"')
ROUTE_LINE = re.compile(r'^[ \t]*route_key[ \t]*=[ \t]*(\S.*?)[ \t]*$', re.M)
ANY_ROUTE_KEY = re.compile(r'\broute_key"?\s*=')
LITERAL = re.compile(r'^"[^"\\$]*"$')
HEREDOC = re.compile(r'<<-?\s*([A-Za-z_][\w-]*)[ \t]*\n')
SPECIAL = set('{}#/*="\\')


def mask(text: str) -> str:
    """`text` with comments and heredoc bodies blanked and the characters that carry syntax blanked
    inside strings, newlines and length kept, so positions in the result index the original. An
    interpolation inside a string is read as code, nested strings included."""
    out = list(text)
    i, n = 0, len(text)
    stack: List[str] = []  # "s" inside a string, "i" inside a ${...} that opened in a string
    depth: List[int] = []  # brace depth within each open interpolation

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = text[i]
        if stack and stack[-1] == "s":
            if c == "\\" and i + 1 < n:
                blank(i, i + 2)
                i += 2
            elif c == '"':
                stack.pop()
                i += 1
            elif text.startswith("${", i) or text.startswith("%{", i):
                stack.append("i")
                depth.append(0)
                i += 2
            else:
                if c in SPECIAL:
                    out[i] = " "
                i += 1
            continue
        if c == '"':
            stack.append("s")
            i += 1
        elif c == "#" or text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            blank(i, end)
            i = end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            blank(i, end)
            i = end
        elif c == "<" and HEREDOC.match(text, i):
            m = HEREDOC.match(text, i)
            close = re.compile(r'^[ \t]*' + re.escape(m.group(1)) + r'[ \t]*$', re.M)
            end_m = close.search(text, m.end())
            end = n if end_m is None else end_m.end()
            blank(m.end(), end)
            i = end
        elif stack and stack[-1] == "i" and c in "{}":
            if c == "{":
                depth[-1] += 1
            elif depth[-1]:
                depth[-1] -= 1
            else:  # closes the interpolation: back inside the string
                stack.pop()
                depth.pop()
            out[i] = " "
            i += 1
        else:
            i += 1
    return "".join(out)


def _block(masked: str, start: int, what: str, rel: Path) -> Tuple[int, int]:
    """Span of the body of the block whose `{` ends just before `start`."""
    level, i = 1, start
    while i < len(masked) and level:
        level += {"{": 1, "}": -1}.get(masked[i], 0)
        i += 1
    if level:
        raise AdapterError(f"{rel}: a {what} block does not close; the check cannot read it")
    return start, i - 1


def _top_level(masked: str, a: int, b: int) -> str:
    """The text of a block body at its own level, nested blocks blanked."""
    out, level = [], 0
    for c in masked[a:b]:
        if c == "{":
            level += 1
        out.append(c if level == 0 else " ")
        if c == "}":
            level -= 1
    return "".join(out)


def _files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name.endswith(SUFFIXES + JSON_SUFFIXES) \
                and not SKIP.intersection(path.relative_to(root).parts):
            yield path


def _front_doors(rel: Path, text: str, masked: str) -> None:
    """Refuses a front door this adapter cannot read, wherever it is in the repository."""
    for pattern, why in OTHER_DOORS:
        if pattern.search(masked):
            raise AdapterError(f"{rel}: {why}")
    for m in API_HEADER.finditer(masked):
        a, b = _block(masked, m.end(), "aws_apigatewayv2_api", rel)
        attr = TOP_ATTR.search(_top_level(masked, a, b))
        if attr:
            raise AdapterError(f"{rel}: an HTTP API with `{attr.group(1)} =` defines routes this "
                               "adapter cannot read")


def _modules(rel: Path, text: str, masked: str) -> None:
    for m in MODULE_HEADER.finditer(masked):
        a, b = _block(masked, m.end(), "module", rel)
        top = _top_level(masked, a, b)
        src = SOURCE.search(top)
        source = text[a + src.start(1):a + src.end(1)] if src else ""
        local = source.startswith(("./", "../")) and not SKIP.intersection(Path(source).parts)
        if not local and re.search(r"route|apigateway", text[a:b], re.I):
            raise AdapterError(f"{rel}: module {source or '(no source)'!r} may define routes the check "
                               "cannot read; use a local module under the configured paths")


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
        if tf.name.endswith(JSON_SUFFIXES):
            if inside or any(k in text for k in API_MARKERS):
                raise AdapterError(f"{rel}: JSON Terraform cannot be read; write the routes as .tf")
            continue
        masked = mask(text)
        _front_doors(rel, text, masked)
        if not inside:
            if ANY_ROUTE_KEY.search(masked) or "aws_apigatewayv2_route" in masked:
                raise AdapterError(f"{rel}: defines a route outside the configured terraform paths; "
                                   "add its directory to security/config.json adapter.paths")
            continue
        _modules(rel, text, masked)
        lines = list(ROUTE_LINE.finditer(masked))
        if len(lines) != len(ANY_ROUTE_KEY.findall(masked)):
            raise AdapterError(f"{rel}: a route_key shares its line with other syntax or is written as a "
                               "quoted name; put each on its own line as `route_key = \"METHOD /path\"`")
        for m in lines:
            where = f"{rel}:{text.count(chr(10), 0, m.start()) + 1}"
            raw = text[m.start(1):m.end(1)]
            if not LITERAL.match(raw):
                raise AdapterError(f"{where}: route_key {raw} is not one literal string; the check cannot verify it")
            found.add(parse_route_key(raw[1:-1], where))
    return found
