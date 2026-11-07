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

@router.route("GET /v1/patterns/{user_id}")
@role("user", owns="user_id")
def get_patterns(event, identity):
    ...  # identity is the verified caller. Never read who the caller is from event["body"].
```

Rules:

- `public` needs a reason that says why anyone may call the route. A webhook names how its
  signature is checked.
- `role` names roles registered once, each with one verifier. A route that names a user's resource
  in its path takes `owns=` that parameter. `role("user")` alone lets any signed-in user reach
  anyone's records.
- The caller's identity comes only from `identity`, which the declaration hands in. Never take
  `user_id`, `device_id` or any other identity from the body, the query string or a header the
  caller sets.
- A handler with no declaration is refused with 403 at runtime.
- With FastAPI, express the same with a dependency on every route and a router-level default that
  refuses; the rule is unchanged.

**Removing a feature removes its server side**: its routes, tables, secrets and permissions, in the
same change.

At `enforced`, `security-check` proves all of this on every pull request, and a new public route
needs a signed approval. The harness's `api-security.md` steering file has the full model.
