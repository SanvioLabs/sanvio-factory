---
paths:
  - "**/Controllers/**/*.cs"
  - "**/*Endpoints.cs"
  - "**/Program.cs"
  - "**/Authorization/**/*.cs"
---

# API security: .NET

This project's `security_level` is `guided` or higher (SPEC-034). Every route is refused unless it
says who may call it. ASP.NET Core does this natively:

```csharp
builder.Services.AddAuthorization(o =>
    o.FallbackPolicy = new AuthorizationPolicyBuilder().RequireAuthenticatedUser().Build());

[AllowAnonymous]                       // public: health check, returns no data
[HttpGet("/v1/health")] public IActionResult Health() => Ok();

[Authorize(Roles = "user")]
[HttpGet("/v1/records/{userId}")]
public async Task<IActionResult> Records(string userId)
{
    var result = await _auth.AuthorizeAsync(User, userId, "Owns");  // resource-based check
    if (!result.Succeeded) return Forbid();
    ...
}
```

Rules:

- The `FallbackPolicy` stays in place; every `[AllowAnonymous]` carries a comment giving the
  reason.
- A route that names a user's resource goes through a resource-based `AuthorizationHandler`, not
  just a role.
- The caller's identity comes only from `User` (the verified principal). Never from a `[FromBody]`
  model, `Request.Query`, `Request.Form`, or a header the caller sets.
- **Removing a feature removes its server side**: routes, tables, secrets and permissions, in the
  same change.

The `enforced` check is built for Python first, so a .NET project stays at `guided` until its own
check exists. Nothing is copied in at `guided`: the project writes the fallback policy and the
authorization handlers itself, in its framework's own way. The harness's `api-security.md` steering
file has the full model.
