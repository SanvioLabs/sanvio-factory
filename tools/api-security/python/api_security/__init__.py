"""API security, SPEC-034: every route is refused unless declared public(reason) or role(...).

Copied into a project as `security/api_security/` by the harness's `tools/api-security/apply.py`.
Stdlib only and Python 3.9 compatible, because it runs wherever the project's own Python does.
"""
from .decorators import UnknownRole, public, role
from .registry import register_ownership, register_role
from .router import Router

__all__ = ["Router", "UnknownRole", "public", "register_ownership", "register_role", "role"]
