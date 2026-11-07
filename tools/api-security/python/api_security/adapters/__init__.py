"""Where the deployed routes come from. Each adapter returns a set of (METHOD, /path) pairs, or
raises AdapterError when it cannot be sure: a route it cannot read is a failure, never a skip."""


class AdapterError(Exception):
    pass


def parse_route_key(key: str, where: str):
    """'GET /v1/x' -> ('GET', '/v1/x'). Anything else is an AdapterError."""
    method, sep, path = key.strip().partition(" ")
    if not sep or not method.isalpha() or not path.startswith("/") or " " in path:
        raise AdapterError(f"{where}: route key {key!r} is not 'METHOD /path'; the check cannot verify it")
    return method.upper(), path
