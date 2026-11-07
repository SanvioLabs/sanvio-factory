"""Deployed routes from API Gateway v2 `route_key` values in Terraform.

Reads only literal keys. An interpolated key, a computed one (`each.key`, `local.x`) or the
`$default` catch-all fails closed: the check cannot say which routes it serves, so it refuses to
guess. Projects that build routes dynamically use the dispatch adapter instead.
"""
import re
from pathlib import Path
from typing import Iterable, Set, Tuple

from . import AdapterError, parse_route_key

ROUTE_KEY = re.compile(r"^\s*route_key\s*=\s*(.+?)\s*(?:#.*|//.*)?$", re.M)


def deployed_routes(root: Path, paths: Iterable[str]) -> Set[Tuple[str, str]]:
    found: Set[Tuple[str, str]] = set()
    for rel in paths:
        base = (Path(root) / rel)
        if not base.is_dir():
            raise AdapterError(f"terraform path {rel!r} does not exist under {root}")
        for tf in sorted(base.rglob("*.tf")):
            if ".terraform" in tf.parts:
                continue
            text = tf.read_text(encoding="utf-8")
            for m in ROUTE_KEY.finditer(text):
                where = f"{tf.relative_to(root)}:{text.count(chr(10), 0, m.start()) + 1}"
                raw = m.group(1)
                if not (raw.startswith('"') and raw.endswith('"')) or "${" in raw:
                    raise AdapterError(f"{where}: route_key {raw} is not a literal string; the check cannot verify it")
                found.add(parse_route_key(raw[1:-1], where))
    return found
