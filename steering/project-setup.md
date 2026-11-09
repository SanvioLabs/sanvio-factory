# Project setup

Read this when you start a new repo or project. The order matters: each step
is cheaper than the problem it prevents.

## 1. Repo and protection (5 min)

- Create it private. A repo is public only when someone decides it should be.
- Protect `main` straight away: pull requests required, no force pushes, no
  deletions, admins included. On GitHub:

  ```bash
  gh api repos/<owner>/<repo>/branches/main/protection --method PUT --input - <<'EOF'
  {
    "required_status_checks": null,
    "enforce_admins": true,
    "required_pull_request_reviews": { "required_approving_review_count": 0 },
    "restrictions": null,
    "allow_force_pushes": false,
    "allow_deletions": false
  }
  EOF
  ```

  A review count of 0 lets you merge your own pull request, which suits
  someone working alone. A team sets 1 or more.

  `required_pull_request_reviews` must be an object, never `null`. `null`
  means no pull request is required, and GitHub still shows the branch as
  protected. Read it back to check, rather than trusting the response:
  `gh api repos/<owner>/<repo>/branches/main/protection -q '.required_pull_request_reviews // "NOT REQUIRED"'`
- Turn on deleting merged branches:
  `gh api -X PATCH repos/<owner>/<repo> -F delete_branch_on_merge=true`
- **Once CI runs on pull requests, make its checks required.** A check that
  runs and blocks nothing is decoration. Take the check names from a real run,
  not from the workflow file, and never require a check behind a `paths:`
  filter: on a PR it doesn't run for, it never reports, and the PR can't merge.
- Copy this factory's [`.githooks/`](../.githooks/) and run `git config core.hooksPath .githooks`
  in every clone. The setting doesn't travel with a clone.
- **If the project exposes an API, set its security level.** Add
  `security_level` under `workspace:` in its `.studio-project.yaml` (absent
  means `off`) and `regulated: true` if it holds restricted data (the list is in
  [`api-security.md`](api-security.md)). Then run
  `python3 tools/api-security/apply.py --level <level> <repo>`.
  Turning on `enforced` has an order, because the approval check reads the base
  branch: create a key that needs a touch for every signature, run
  `apply.py --level enforced --runtime lambda-httpapi`, put its public half in
  `security/allowed_signers`, fill in `security/config.json` and
  `security/fixtures.py` until the check passes locally, land that on the
  default branch, and only then require `security-check` and
  `security-approval`, with branches required to be up to date before merging.
  Neither workflow may carry a `paths:` filter.

## 2. Spec before code (30 to 60 min)

Write the spec before the code, in the repo it describes.
[`building-and-testing.md`](building-and-testing.md) has the order and where it lives.

## 3. Scaffold by hand (15 min)

Write the config and folders directly, check a build passes, and write one
test straight away. [`building-and-testing.md`](building-and-testing.md) has why.

## 4. Infrastructure and the deploy script (20 min)

Infrastructure as code, a separate account for sensitive data, and the deploy
script written before the first deploy. [`deploying.md`](deploying.md) has the full list.

## 5. Tickets, once you know the work (10 min)

Create issues once enough is built to know what's left, not before. One parent
issue with the context (repo, environment, how to test), then the rest in the
order that makes it testable end to end soonest.

## Never

- Code before the spec.
- Sensitive data in a shared account.
- A deploy script written after the manual deploys.

The detail behind each is in [`building-and-testing.md`](building-and-testing.md) and [`deploying.md`](deploying.md).
