---
paths:
  - "**/*.controller.ts"
  - "**/routes/**/*.ts"
  - "**/handlers/**/*.ts"
  - "**/api/**/*.ts"
  - "**/app/**/route.ts"
  - "**/pages/api/**"
  - "**/*.guard.ts"
---

# API security: TypeScript

This project's `security_level` is `guided` or higher (SPEC-034). Every route is refused unless it
says who may call it.

**NestJS:** register a global guard that refuses any route without metadata, then declare each
route with exactly one of:

```ts
@Public("health check, returns no data")
@Get("/v1/health")
health() {}

@Roles("user")
@Owns("userId")          // the guard compares this route param with the verified caller
@Get("/v1/records/:userId")
records(@CurrentUser() caller: Caller) {}
```

**Express, Hono, a bare Lambda:** register every route through one wrapper that refuses a handler
it was not given a declaration for:

```ts
route("GET /v1/health", publicRoute("health check, returns no data"), health);
route("GET /v1/records/:userId", role("user", { owns: "userId" }), records);
```

Rules:

- A public route carries a reason. A webhook names how its signature is checked.
- A route that names a user's resource takes `owns`. A role alone lets any signed-in user reach
  anyone's records.
- The caller's identity comes only from the verified credential the guard or wrapper hands in.
  Never from `req.body`, `req.query`, a header the caller sets, or `JSON.parse(event.body)`.
- **Removing a feature removes its server side**: routes, tables, secrets and permissions, in the
  same change.

The `enforced` check is built for Python first, so a TypeScript project stays at `guided` until its
own check exists. Nothing is copied in at `guided`: the project writes the global guard or the
wrapper itself, in its framework's own way. The harness's `api-security.md` steering file has the
full model.
