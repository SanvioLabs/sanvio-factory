"""Deployed routes from a single router's dispatch table: `module:ATTRIBUTE`, a mapping whose keys
are "METHOD /path" strings or (METHOD, /path) tuples. For an API that sends every request to one
function which routes internally."""
import importlib
from typing import Set, Tuple

from . import AdapterError, parse_route_key


def deployed_routes(table: str) -> Set[Tuple[str, str]]:
    module_name, sep, attr = table.partition(":")
    if not sep or not module_name or not attr:
        raise AdapterError(f"dispatch table {table!r} is not 'module:ATTRIBUTE'")
    mapping = getattr(importlib.import_module(module_name), attr, None)
    if mapping is None or not hasattr(mapping, "keys"):
        raise AdapterError(f"{table} is not a mapping")
    found: Set[Tuple[str, str]] = set()
    for key in mapping.keys():
        if isinstance(key, tuple) and len(key) == 2:
            found.add(parse_route_key(f"{key[0]} {key[1]}", table))
        elif isinstance(key, str):
            found.add(parse_route_key(key, table))
        else:
            raise AdapterError(f"{table}: key {key!r} is neither 'METHOD /path' nor (METHOD, /path)")
    return found
