"""Dispatch for API Gateway (HTTP API, payload v2) Lambda events.

Every route registered here is recorded with its declaration. At request time an undeclared
handler is refused with 403, a role route with no credential gets 401, and a credential that no
verifier accepts gets 403. The handler receives the identity the verifier returned and nothing
the caller asserted. Anything that goes wrong while deciding is a refusal, never a pass.
"""
import json
import logging
from typing import Any, Callable, Dict, Optional, Tuple

from . import registry
from .decorators import policy_of
from .registry import Policy

log = logging.getLogger("api_security")

CREDENTIAL_HEADERS = ("authorization",)


def _response(status: int, message: str) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json"},
            "body": json.dumps({"error": message})}


def _has_credential(event: dict) -> bool:
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    return any(headers.get(h) for h in CREDENTIAL_HEADERS)


class Router:
    def __init__(self) -> None:
        self._handlers: Dict[Tuple[str, str], Callable] = {}

    def route(self, route_key: str) -> Callable:
        """Register a handler for "METHOD /path", as API Gateway writes a route key."""
        try:
            method, path = route_key.split(" ", 1)
        except ValueError:
            raise ValueError(f"route key {route_key!r} is not 'METHOD /path'") from None

        def wrap(fn: Callable) -> Callable:
            key = (method.upper(), path)
            self._handlers[key] = fn
            registry.record(method, path, policy_of(fn), f"{fn.__module__}.{fn.__qualname__}")
            return fn
        return wrap

    def handle(self, event: dict, context: Any) -> dict:
        route_key = event.get("routeKey") or ""
        method, _, path = route_key.partition(" ")
        fn = self._handlers.get((method.upper(), path))
        if fn is None:
            return _response(404, "not found")
        policy = policy_of(fn)
        if policy is None:
            log.warning("api_security.undeclared method=%s path=%s", method.upper(), path)
            return _response(403, "forbidden")
        try:
            allowed, status, identity = self._decide(policy, event)
        except Exception as exc:  # deciding failed: refuse, and say why in the log, never in the response
            log.error("api_security.decision_error method=%s path=%s error=%s", method.upper(), path, type(exc).__name__)
            return _response(403, "forbidden")
        if not allowed:
            return _response(status, "unauthorized" if status == 401 else "forbidden")
        return fn(event, identity)

    @staticmethod
    def _decide(policy: Policy, event: dict) -> Tuple[bool, int, Optional[Any]]:
        if policy.kind == "public":
            return True, 200, None
        if policy.kind != "role":
            return False, 403, None
        identity = None
        for name in policy.roles:
            verify = registry.verifier(name)
            if verify is None:
                return False, 403, None
            identity = verify(event)
            if identity is not None:
                break
        if identity is None:
            return False, (401 if not _has_credential(event) else 403), None
        if policy.owns:
            owns = registry.ownership()
            value = (event.get("pathParameters") or {}).get(policy.owns)
            if owns is None or value is None or not owns(identity, policy.owns, value):
                return False, 403, None
        return True, 200, identity
