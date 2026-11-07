"""What the project has declared: routes and their policies, role verifiers, the ownership test.

One module-level registry per process. The check imports the project's handler modules and reads
it, so nothing has to be deployed to know what a route requires.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

Verifier = Callable[[dict], Any]  # event -> identity, or None when the caller does not hold the role
Ownership = Callable[[Any, str, str], bool]  # (identity, parameter name, parameter value) -> owns it


@dataclass(frozen=True)
class Policy:
    kind: str  # "public" or "role"
    reason: str = ""
    roles: Tuple[str, ...] = ()
    owns: Optional[str] = None


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    policy: Optional[Policy]  # None: the handler carries no declaration, and is refused
    handler: str  # module.qualname, for reports


_routes: Dict[Tuple[str, str], Route] = {}
_roles: Dict[str, Verifier] = {}
_ownership: List[Ownership] = []


def reset() -> None:
    """Forget everything. For tests."""
    _routes.clear()
    _roles.clear()
    _ownership.clear()


def register_role(name: str, verifier: Verifier) -> None:
    if not name or not callable(verifier):
        raise ValueError("a role needs a name and a callable verifier")
    _roles[name] = verifier


def verifier(name: str) -> Optional[Verifier]:
    return _roles.get(name)


def has_role(name: str) -> bool:
    return name in _roles


def register_ownership(fn: Ownership) -> None:
    if not callable(fn):
        raise ValueError("the ownership test must be callable")
    _ownership[:] = [fn]


def ownership() -> Optional[Ownership]:
    return _ownership[0] if _ownership else None


def record(method: str, path: str, policy: Optional[Policy], handler: str) -> None:
    key = (method.upper(), path)
    if key in _routes and _routes[key].handler != handler:
        raise ValueError(f"{method.upper()} {path} is declared twice: {_routes[key].handler} and {handler}")
    _routes[key] = Route(method.upper(), path, policy, handler)


def routes() -> List[Route]:
    return sorted(_routes.values(), key=lambda r: (r.path, r.method))


def lookup(method: str, path: str) -> Optional[Route]:
    return _routes.get((method.upper(), path))
