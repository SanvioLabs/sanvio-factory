---
paths:
  - "**/handler*.py"
  - "**/handlers/**/*.py"
  - "**/api/**/*.py"
  - "**/routes/**/*.py"
  - "**/views*.py"
  - "**/routers/**/*.py"
---

# API security: Python

This project's `security_level` is `guided` or higher (SPEC-034). Every route is refused unless it
says who may call it.

**Declare every handler with exactly one of two decorators:**

```python
from security.api_security import Router, public, role

router = Router()

@router.route("GET /v1/health")
@public(reason="health check, returns no data")
def health(event, identity):
    ...

@router.route("GET /v1/records/{user_id}")
@role("user", owns="user_id")
def get_records(event, identity):
    ...  # identity is the verified caller. Never read who the caller is from event["body"].
```

Rules:

- `public` needs a reason that says why anyone may call the route. A webhook names how its
  signature is checked.
- `role` names roles registered once, each with one verifier, through `register_role` in the
  module `security/config.json` calls `roles_module`. A verifier returns the verified identity or
  `None`: never a bool, a number, a tuple or list, an empty value, or anything `async`. Each of
  those refuses the request and logs `api_security.bad_identity`; return a numeric user id as
  `str(user_id)` or inside a dict such as `{"sub": user_id}`.
- A route with a parameter in its path takes `owns=` that parameter, checked by the one
  `register_ownership` test. `role("user")` alone lets any signed-in user reach anyone's records.
  Where any holder of the role may reach every value, say why: `unowned="..."`.
- The caller's identity comes only from `identity`, which the declaration hands in. Never take
  `user_id`, `device_id` or any other identity from the body, the query string or a header the
  caller sets.
- A handler with no declaration is refused with 403 at runtime.
- The library's `Router` is for Lambda behind API Gateway HTTP API v2, with the function's handler
  set to `router.handle`. On FastAPI, Flask or Django, keep the same rule with that framework's own
  default-deny (a dependency or middleware on every route); the project then stays at `guided`.

**Removing a feature removes its server side**: its routes, tables, secrets and permissions, in the
same change.

At `enforced`, `security-check` proves all of this on every pull request, and a new public route
needs a signed approval. The harness's `api-security.md` steering file has the full model.
