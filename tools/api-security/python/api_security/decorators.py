"""The two declarations. A handler carries exactly one of them, or the router refuses it."""
from typing import Callable, Optional

from . import registry
from .registry import Policy

ATTR = "__api_security__"


class UnknownRole(LookupError):
    """A role named in a declaration has no verifier registered. Register roles before handlers load."""


def _attach(policy: Policy) -> Callable:
    def wrap(fn: Callable) -> Callable:
        if getattr(fn, ATTR, None) is not None:
            raise ValueError(f"{fn.__qualname__} already carries a declaration; it takes exactly one")
        setattr(fn, ATTR, policy)
        return fn
    return wrap


def public(*, reason: str) -> Callable:
    """Anyone may call this route. `reason` says why, and is required."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("public() needs a non-empty reason saying why anyone may call this route")
    return _attach(Policy(kind="public", reason=reason.strip()))


def role(*roles: str, owns: Optional[str] = None) -> Callable:
    """Only a caller holding one of `roles`. With `owns`, only when that caller owns the resource the
    named path parameter points at."""
    if not roles:
        raise ValueError("role() needs at least one role name")
    missing = [r for r in roles if not registry.has_role(r)]
    if missing:
        raise UnknownRole(f"no verifier registered for role(s) {', '.join(missing)}; "
                          "register roles before the handlers that use them are imported")
    if owns is not None and (not isinstance(owns, str) or not owns.strip()):
        raise ValueError("owns names a path parameter, e.g. owns='user_id'")
    return _attach(Policy(kind="role", roles=tuple(roles), owns=owns))


def policy_of(fn: Callable) -> Optional[Policy]:
    return getattr(fn, ATTR, None)
