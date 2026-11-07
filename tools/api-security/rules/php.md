---
paths:
  - "app/Http/Controllers/**"
  - "app/Http/Middleware/**"
  - "app/Policies/**"
  - "routes/**/*.php"
  - "src/Controller/**"
  - "config/packages/security.yaml"
---

# API security: PHP

This project's `security_level` is `guided` or higher (SPEC-034). Every route is refused unless it
says who may call it.

**Laravel:** every route sits inside the `auth` middleware group by default. Public routes sit in
their own, explicitly named group, each with a comment giving the reason. Roles use `can:`
middleware or a gate. A route that names a user's resource is authorized through a policy:

```php
// public: health check, returns no data
Route::get('/v1/health', HealthController::class);

Route::middleware('auth')->group(function () {
    Route::get('/v1/records/{user}', [RecordController::class, 'show']);  // $this->authorize('view', $user)
});
```

**Symfony:** `access_control` ends in a rule that denies everything; routes open with
`#[IsGranted('PUBLIC_ACCESS')]` (with the reason in a comment) or `#[IsGranted('ROLE_...')]`, and
ownership goes through a voter.

Rules:

- The caller's identity comes only from the authenticated user (`$request->user()`,
  `$this->getUser()`). Never from `$request->input()`, `query()`, a header the caller sets,
  `$_GET`, `$_POST` or `$_REQUEST`.
- A route that names a user's resource is checked by a policy or voter, not just a role.
- **Removing a feature removes its server side**: routes, tables, secrets and permissions, in the
  same change.

The `enforced` check is built for Python first, so a PHP project stays at `guided` until its own
check exists. Nothing is copied in at `guided`: the project writes the middleware groups and
policies itself, in its framework's own way. The harness's `api-security.md` steering file has the
full model.
