"""Deployed routes from the project's Router, for an API that sends every request to one function
whose handler is `router.handle`. Config: `"table": "module:router"`.

A plain mapping is refused: the check could read its keys, but nothing would show that a request
reaching one of its handlers went through `Router.handle`, which is where the declaration is
enforced.
"""
import importlib
from typing import Set, Tuple

from . import AdapterError, parse_route_key


def deployed_routes(table: str) -> Set[Tuple[str, str]]:
    from ..router import Router

    module_name, sep, attr = table.partition(":")
    if not sep or not module_name or not attr:
        raise AdapterError(f"dispatch table {table!r} is not 'module:router'")
    router = getattr(importlib.import_module(module_name), attr, None)
    if not isinstance(router, Router):
        raise AdapterError(f"{table} is not an api_security Router; point the dispatch adapter at the "
                           "Router whose handle() the function runs")
    return {parse_route_key(f"{method} {path}", table) for method, path in router.routes()}
