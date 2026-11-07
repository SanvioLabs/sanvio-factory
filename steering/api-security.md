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
| `role(*roles, owns=None, unowned=None)` | Only a caller holding one of the named roles. With `owns="user_id"`, only when the verified caller owns the resource that path parameter names. A route with a path parameter and no owner says why with `unowned="..."` |

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
| `hardened` | Restricted data: health or medical records, children's data, biometrics, payment cards, financial account or tax records, government ID numbers, precise location | The checklist below, plus a security review on every PR touching handlers or infrastructure before it merges |

`off` is the default so that a harness already in use changes nothing until
someone chooses. The cost is that a live project can sit at `off` unnoticed, so
`python3 scripts/check_setup.py` warns about any project under [`projects/`](../projects/)
whose `.studio-project.yaml` says `live_users: true` or `regulated: true` while
its level is `off`.

**Raise the level before you need it.** `guided` costs a rules file and nothing
else, and it is what makes `enforced` a switch rather than a retrofit: code
written with declarations from the first handler passes the check the day it is
turned on.

## Per language

| Language | Refused by default | `public` | `role` | `owns` |
|---|---|---|---|---|
| Python | The library's router refuses an undeclared handler | `@public(reason=...)` | `@role("admin")` | `@role("user", owns="user_id")` |
| TypeScript, NestJS | A global guard | `@Public()` with a reason | `@Roles("admin")` | A guard comparing the route param with the verified caller |
| TypeScript, Express, Hono, bare Lambda | One wrapper every route is registered through | `route(publicRoute("reason"), handler)` | `route(role("admin"), handler)` | `route(role("user", { owns: "userId" }), handler)` |
| PHP, Laravel | A default `auth` middleware group | A separate public group, reason in a comment | `can:` middleware or a gate | Policies |
| PHP, Symfony | `access_control` ending in deny-all | `#[IsGranted('PUBLIC_ACCESS')]` | `#[IsGranted('ROLE_ADMIN')]` | A voter |
| .NET, ASP.NET Core | `FallbackPolicy = RequireAuthenticatedUser()` | `[AllowAnonymous]` | `[Authorize(Roles = "admin")]` | A resource-based `AuthorizationHandler` |

The `enforced` check is built for one shape so far: **Python on Lambda behind
API Gateway HTTP API v2, with the function's handler set to the library's
`router.handle`**. `apply.py` asks for `--runtime lambda-httpapi` to say so. A
Python API on FastAPI, Flask or Django, and every other language, goes no higher
than `guided` until its own check exists.

At `guided`, Python gets the library itself under `security/api_security/`, so
the rules file's import works from the first handler. Every other language gets
the rules file only: the guard, wrapper or middleware in the table above is the
project's to write, in its framework's own way.

## Registering roles

Each role is registered once, with one verifier, in the module
`security/config.json` names as `roles_module`, imported before any handler:

```python
from security.api_security import register_ownership, register_role

def user(event):
    """The verified identity, or None. Never a bool, never async."""
    claims = verify_jwt(event["headers"].get("authorization", ""))  # your own verification
    return {"sub": claims["sub"]} if claims else None

def owns(identity, param, value):
    """Compare the path value exactly as the handler will read it."""
    return identity["sub"] == value

register_role("user", user)
register_ownership(owns)
```

A verifier returning anything but an identity (a bool, an empty value, a
coroutine) is a refusal, and registering a second verifier under a taken name
raises, so a later import can't swap it.

## `enforced`: what holds it

- **The check** (`security-check.yml`, on `pull_request`): the declarations
  against the routes actually deployed (read from Terraform API Gateway routes,
  or from a single router's dispatch table); a Semgrep scan for identity read
  from request input; generated tests proving 401 with no token and 403 with
  another identity's token; and the list of public routes against the checked-in
  `security/public-routes.txt`.
- **The approval** (`security-approval.yml`, on `pull_request_target`): any line
  added to `security/public-routes.txt`, and any other change under `security/`
  or [`.github/workflows/`](../.github/workflows/), needs a commit signed by a key in the **base
  branch's** `security/allowed_signers`. It judges what would land, the merge of
  the PR into its base, and one signed commit containing that base has to hold
  exactly what lands across those paths. Every workflow is guarded because a
  required status matches by job name, and a workflow can take that name from
  the PR's own title. Two changes need no signature: removing a public route,
  and a Dependabot bump: a PR Dependabot opened and only Dependabot pushed to,
  moving only the `@ref` of existing `uses:` lines, in a workflow that is not a
  security workflow, not a reusable one (`workflow_call`), and not listed under
  `deploy_workflows` in the base's `security/config.json`. The same change from
  anyone else is signed: a commit that exists only in a fork resolves through
  the parent's path, so the same action path is not the same publisher.
- **Both are required statuses** on every protected branch, with branches
  required to be up to date before merging. Turn them on in this order
  ([`project-setup.md`](project-setup.md)): create the key; run
  `apply.py --level enforced --runtime lambda-httpapi`; put the key in
  `security/allowed_signers`; fill in `security/config.json` and
  `security/fixtures.py` until the check passes locally (the templates fail on
  purpose); make sure the function's deploy bundle carries `security/`, which
  the handlers import at runtime; land that on the default branch; then require
  `security-check` and `security-approval`.

**The check catches mistakes, not an adversary.** It imports the project's
handlers to list their declarations, so code written to subvert it can make it
pass. The approval is the part that holds against a hostile PR, and it covers
only `security/` and [`.github/workflows/`](../.github/workflows/). A deliberate change to app code is what
review is for, and at `hardened` that review is required before merge.

**Updating a branch from its base after signing needs a new signature** when
the branch changes a guarded file: sign the merge commit
(`git commit --amend -S` on it). A signature on a commit built on an older base
doesn't count, because an old signed commit could otherwise be replayed over a
later fix. List every workflow that deploys in `deploy_workflows`: they hold
the deploy credentials, and listing them is what puts them behind the
signature. A merge queue isn't supported: the approval job doesn't run there.

### Signing

The approval needs an SSH signature from a key in the base branch's
`security/allowed_signers`, made by the same email the commit carries:

```bash
git config gpg.format ssh
git config user.signingkey <path to the public half of the touch-required key>
git config commit.gpgsign true          # or pass -S on the commits that need it
# security/allowed_signers, one line per key:
#   you@example.com ssh-ed25519 AAAA...
```

The refusal names its cause:

| It says | Do |
|---|---|
| no commit is signed by a listed key | Sign the commit (`git commit --amend -S`, then push). Check the commit email matches the `allowed_signers` line; a GitHub noreply address doesn't |
| the signed commit is built on an older base | Update from the base on your machine, sign the merge commit, push. Never use GitHub's **Update branch** button on a guarded PR: it makes an unsigned merge |
| what lands differs from every signed commit | A later commit changed a guarded file. Sign the latest |

A rebase or squash rewrites commits and drops their signatures, so sign after
it. A Dependabot PR bumping a security, deploy or reusable workflow needs the
same signature; one bumping any other workflow does not, as long as it changes
nothing but `@ref`s. Pushing to a Dependabot branch, or closing and reopening
its PR, makes you the sender, and then it needs a signature too.

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
  With no ignore file it still skips [`tests/`](../tests/), `test/`, `build/`, `dist/`,
  `vendor/` and `node_modules/`, so deployed code does not live under them: the
  check fails a handler module there, and code a handler imports from one goes
  unscanned.
- **The Terraform adapter reads patterns, not HCL.** Comments, strings and
  heredocs are masked first, `.tf` and `.tofu` are read, and anything it cannot
  read fails the check: an unterminated string, comment or heredoc, a computed
  `route_key`, a route outside the configured paths, any module that is not a
  plain local folder, and anywhere in the repository JSON Terraform, a function
  URL, a REST API, or an HTTP API built from `body` or `target`. Vendor a
  registry module into the configured paths to use it at `enforced`.

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
