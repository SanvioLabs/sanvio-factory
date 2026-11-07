# API security levels

Read this when you write or review an API handler, raise a project's security
level, or set up a project that exposes an API.

The commonest API bugs are not clever. A handler trusts a user id the caller
sent in the body. An anonymous route returns stored personal data. A feature is
removed from the app and its server route keeps answering anyone who finds it.
In every case a route with no check looks the same in review as a correct one.
This file is the rule that makes the difference visible, and the levels decide
how hard the harness holds a project to it.

## The model

**Every route is refused unless it says who may call it.** There are exactly two
ways to say it:

| Declaration | Means |
|---|---|
| `public(reason)` | Anyone may call it. The reason is required and says why, e.g. "payment webhook, signature checked" |
| `role(*roles, owns=None)` | Only a caller holding one of the named roles. With `owns="user_id"`, only when the verified caller owns the resource that path parameter names |

Three rules hold under both:

- **Identity comes only from the verified token.** A handler never reads who the
  caller is from the body, the query string or a header the caller sets. The
  declaration verifies the token and hands the identity in.
- **A role is a name the repo defines** (`user`, `device`, `admin`,
  `webhook:payments`), each backed by one verifier registered once. A role name
  with no verifier is an error at load, not a silent pass.
- **A route that names a user's resource takes `owns`.** A role says what kind
  of caller this is, not whose data they may reach. `role("user")` alone lets any
  signed-in user read anyone's records.

The declaration sits on the handler, in the same diff as the code it protects.
A central table of routes and policies is the tempting alternative and the
wrong one: one edited line far from the handler relaxes a route without anyone
reading the code.

## The levels

Set in the project's `.studio-project.yaml` as `workspace.security_level`.
Absent or unrecognised means `off`. Each level includes everything below it.
`python3 tools/api-security/apply.py --level <level> <repo>` copies in what a
level needs and nothing else.

| Level | For | What applies |
|---|---|---|
| `off` (default) | Prototypes, anything not deployed, every project that has not chosen | Nothing is loaded or checked |
| `guided` | Deployed, no real users yet | A rules file for the project's language, loaded when handler code is edited and pointed at from the project's `AGENTS.md`. Endpoint tickets carry a wrong-user-is-refused check ([`tickets.md`](tickets.md)). Nothing blocks |
| `enforced` | Real users | A check in the project repo as a required status: every deployed route declared, no identity read from request input, generated 401/403/`owns` tests pass, and a new public route carries a signed approval. The project's `deploy_ready` gate runs it |
| `hardened` | Personal, health, financial or children's data | The checklist below, plus a security review on every PR touching handlers or infrastructure before it merges |

`off` is the default so that a harness already in use changes nothing until
someone chooses. The cost is that a live project can sit at `off` unnoticed, so
`python3 scripts/check_setup.py` warns about any project under `projects/`
whose `.studio-project.yaml` says `live_users: true` or `regulated: true` while
its level is `off`.

**Raise the level before you need it.** `guided` costs a rules file and nothing
else, and it is what makes `enforced` a switch rather than a retrofit: code
written with declarations from the first handler passes the check the day it is
turned on.

## Per language

| Language | Refused by default | `public` | `role` | `owns` |
|---|---|---|---|---|
| Python | The library's router refuses an undeclared handler | `@public(reason=...)` | `@role("admin")` | `@role("user", owns="user_id")`; FastAPI can do the same through dependencies |
| TypeScript, NestJS | A global guard | `@Public()` with a reason | `@Roles("admin")` | A guard comparing the route param with the verified caller |
| TypeScript, Express, Hono, bare Lambda | One wrapper every route is registered through | `route(publicRoute("reason"), handler)` | `route(role("admin"), handler)` | `route(role("user", { owns: "userId" }), handler)` |
| PHP, Laravel | A default `auth` middleware group | A separate public group, reason in a comment | `can:` middleware or a gate | Policies |
| PHP, Symfony | `access_control` ending in deny-all | `#[IsGranted('PUBLIC_ACCESS')]` | `#[IsGranted('ROLE_ADMIN')]` | A voter |
| .NET, ASP.NET Core | `FallbackPolicy = RequireAuthenticatedUser()` | `[AllowAnonymous]` | `[Authorize(Roles = "admin")]` | A resource-based `AuthorizationHandler` |

The `enforced` check is built for Python first. Projects in other languages can
go up to `guided` until their own check exists.

## `enforced`: what holds it

- **The check** (`security-check.yml`, on `pull_request`): the declarations
  against the routes actually deployed (read from Terraform API Gateway routes,
  or from a single router's dispatch table); a Semgrep scan for identity read
  from request input; generated tests proving 401 with no token and 403 with
  another identity's token; and the list of public routes against the checked-in
  `security/public-routes.txt`.
- **The approval** (`security-approval.yml`, on `pull_request_target`): any line
  added to `security/public-routes.txt`, and any other change under `security/`
  or `.github/workflows/`, needs a commit signed by a key in the **base
  branch's** `security/allowed_signers`. It judges what would land, the merge of
  the PR into its base, and one signed commit containing that base has to hold
  exactly what lands under both. Removing a public route needs no signature.
- **Both are required statuses** on every protected branch, with branches
  required to be up to date before merging. Turn them on in this order: create
  the key, run `apply.py --level enforced`, put the key in
  `security/allowed_signers`, land that on the default branch, then require
  `security-check` and `security-approval` ([`project-setup.md`](project-setup.md)).

**The check catches mistakes, not an adversary.** It imports the project's
handlers to list their declarations, so code written to subvert it can make it
pass. The approval is the part that holds against a hostile PR, and it covers
only `security/` and the workflows. A deliberate change to app code is what
review is for, and at `hardened` that review is required before merge.

**Updating a branch from its base after signing needs a new signature** when
the branch changes a guarded file: sign the merge commit
(`git commit --amend -S` on it). A signature on a commit built on an older base
doesn't count, because an old signed commit could otherwise be replayed over a
later fix. Every workflow edit in an `enforced` repo needs a signature,
deploy workflows included. A merge queue isn't supported: the approval job
doesn't run there.

Why it is built this way:

- **The approval reads the base branch.** A PR cannot add the key that approves
  it, and cannot edit the workflow that checks it, because `pull_request_target`
  runs the base branch's definition. That job checks out the base only and reads
  the PR's commits as git objects; it never runs code from the PR. Checking out
  the PR head inside `pull_request_target` hands untrusted code a write token,
  so treat any change to that workflow as a security review.
- **The key needs a touch.** An agent working for you uses your GitHub account,
  so a label or an approval click can come from automation on your machine. A
  signature from a key that needs a physical touch or a biometric for every use
  cannot. Use a Secure Enclave key (Secretive, or 1Password's SSH agent with
  approval per use) or `ssh-keygen -t ed25519-sk -O verify-required` on a
  hardware key. A plain key in `ssh-agent` does not qualify.
- **Semgrep runs locally.** Pinned version, `--metrics=off`, local rules only,
  no login and no `--config auto`, so your code never goes to a hosted service.

## `hardened`: the checklist

| Item | Done when |
|---|---|
| Failed-attempt limit | Every access code, email code, 2FA code and password login goes through one shared limiter, counted per code and per source, carried across resends, incremented atomically |
| No way around the edge | The API's default endpoint is disabled where a custom domain fronts it, and every load balancer refuses traffic that did not come through the CDN |
| Gateway authorizer | Every route not in `security/public-routes.txt` carries an authorizer at the gateway, a second layer independent of the handler declaration |
| Per-function permissions | Each function has its own role. The public and webhook handlers first |
| Deploy role ceiling | The deploy role carries a permissions boundary and cannot modify its own role |
| Pinned CI | Every third-party action in the security and deploy workflows is pinned to a full commit SHA. The check fails otherwise |
| Reviewed before merge | Every PR touching a path in `security/hold-paths.txt` has had a security review before it merges |

## Removing a feature removes its server side

At every level above `off`: a ticket that removes a feature lists the routes,
tables, secrets and permissions it leaves behind, and removes them in the same
change. A route whose client is gone still answers anyone who finds it.
