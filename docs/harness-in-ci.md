# Your factory in CI

Your factory can run in CI in three ways, and each works on its own. Two of
them go in a product repo. The loop's workflow goes in a repo that carries the
factory itself.

| What | Workflow | Goes in | What it does | Needs |
|---|---|---|---|---|
| Checks | [`examples/ci/project-checks.yml`](../examples/ci/project-checks.yml) | The product repo | Runs the repo's checks on every pull request and every push to `main`. Each job skips with a notice until the file it needs exists, such as `pyproject.toml` or `package.json` | Nothing else |
| Review | A short caller of [`.github/workflows/review-pr.yml`](../.github/workflows/review-pr.yml), which stays in your factory repo | The product repo | Reviews every pull request with your harness's review-pr skill, its rules and your team's standards, and posts the report as one comment, edited on each push | A read-only deploy key and an Anthropic API key, held as secrets |
| Loop | [`examples/ci/loop.yml`](../examples/ci/loop.yml) | The factory repo | One pass of the loop on a runner: one issue labelled `loop-ready`, through to a pull request it doesn't merge | An API key, and a token that isn't the workflow's own if its pull requests are to start your checks |

Start with checks, then add the review. The loop is optional.

![Three product repos each hold one short caller, review.yml. A pull request, #42, opens in the first. Its caller asks the factory repo, your-org/factory, for .github/workflows/review-pr.yml. The review job checks the harness out with a read-only deploy key, holding only AGENTS.md, steering, skills, agents and standards, beside the product repo at the pull request's base and the pull request itself. The pull request's own AGENTS.md, CLAUDE.md, .claude folders and symlinks are struck out, so its copies of those can't change the review's rules. Claude reads with Read, Grep and Glob only, and one comment is posted: changes needed, two findings. A second push edits the same comment to ready with nits, one finding, marked edited. Last, the factory repo's main is shown as protected, and a change to it marks all three product repos: their next review uses the new rules.](harness-in-ci.gif)

You make each key yourself and paste it into GitHub. Nobody else, including
anyone helping you set this up, needs to see one.

## Checks first

1. Copy [`examples/ci/project-checks.yml`](../examples/ci/project-checks.yml) into the product repo as
   `.github/workflows/checks.yml`.
2. Open a pull request. Each job runs, or skips with a notice saying which file
   it looked for.
3. Once a job has run on a pull request, make it a required check in the
   repo's branch protection, using the name from that run. A check that isn't
   required only reports.
4. When the repo has a real command for something, swap the job's guard for
   that command. Its opening comment says how.

## A review on every pull request

The review lives in your factory repo, and each product repo calls it. A change
to the skill, the rules or your standards reaches every product repo on its
next pull request, with no copy in each repo to keep up to date.

Set it up in this order. Each step links to its detail in
[`examples/ci/README.md`](../examples/ci/README.md).

1. **Protect the factory repo's `main`.** Every review runs whatever `main` holds,
   with each product repo's secrets, so anyone who can push there can read
   them. Require a pull request with one approval from someone other than its
   author, require the factory repo's own CI to pass, block force pushes and
   deletion, and apply it to admins too.
   [Protecting the factory repo](../examples/ci/README.md#protecting-the-factory-repo)
2. **Let the product repos call it**, if the factory repo is private: Settings,
   Actions, General, and under Access, "Accessible from repositories in the
   organization".
   [A private factory repo](../examples/ci/README.md#a-private-factory-repo)
3. **Make a deploy key** on your machine, and add its public half to the
   factory repo with write access off. If GitHub refuses it,
   [When the first review fails](#when-the-first-review-fails) has why.
   [The credential](../examples/ci/README.md#the-credential)
4. **Add two secrets**, before the caller, so its first pull request doesn't
   skip: `FACTORY_DEPLOY_KEY`, the deploy key's private half, and
   `ANTHROPIC_API_KEY`, made inside a workspace in the Anthropic Console.
   Setting them once for the organisation is easier: each later product repo
   is then added to the secrets' repository access in the organisation's
   settings, with no key file needed. With a secret per repo, set every repo's
   before you go on. Then delete both halves of the deploy key,
   `review-pr-deploy-key` and `review-pr-deploy-key.pub`. A repo you add later
   then needs a new deploy key.
   [The secret](../examples/ci/README.md#the-secret)
5. **Add the caller** to each product repo, with your factory repo's name in
   both places it appears. It's the only file a product repo needs. Anyone who
   can push a branch to a product repo can change its caller in that branch, to
   skip the review or print both secrets, so add the secrets only where you'd
   trust the writers to read the factory repo.
   [The caller](../examples/ci/README.md#the-caller)
6. **Open a test pull request** in one product repo (the next section has
   what to put in it). The workflow posts one comment on it, and a second push
   edits that comment rather than adding another. Until step 7, the comment's
   first line says no team standards were loaded. The run's log names the
   harness commit it reviewed with.
7. **Add your team's standards**, if you have them written down, as Markdown
   files in a `standards/` folder at the factory repo's root. A finding then
   names the file and heading of the standard it breaks.
   [Team standards](../examples/ci/README.md#team-standards)

### When the first review fails

Each of these stops a first setup, and each one says so in the run's log. A
failure from Claude itself shows in the step "Run the review-pr skill on
Claude", after `claude exited 1. What it said:`.

| The message | What it means | The fix |
|---|---|---|
| `Deploy keys are disabled for this repository`, when you add the key | The organisation has deploy keys switched off for every repo | An organisation owner allows them in the organisation's settings. Then add the key again |
| `FACTORY_DEPLOY_KEY is not set` | The product repo has no deploy-key secret | Step 4 |
| `has no skills/review-pr/SKILL.md` | `factory-repo` names the wrong repo, or the key belongs to another one | Check both places the caller names the factory repo, and the deploy key's repo |
| `Credit balance is too low` | The Anthropic account the key bills to has no credit | Add credit in the Anthropic Console, then rerun the job: no new push needed |
| `This API key is not scoped to a workspace` | The key was made for the organisation, not inside a workspace | Make a new key inside a workspace, set `ANTHROPIC_API_KEY` again, and rerun |
| `This pull request has no ANTHROPIC_API_KEY`, as a notice | The secret isn't set in this repo, or it's a Dependabot pull request | Step 4, or nothing for Dependabot |

To rerun a failed review after a fix, use the run's Re-run button, or
`gh run rerun <run id> --repo <your-org>/<product>`.

### Try it on a change you made up

Before you point it at real work, open a pull request in a repo of your own
with problems you planted, and check the review names each one with its file
and line. Two that work in any repo:

- a function that branches on its input, with no test
- `except Exception: pass` around a call that can fail

A made-up password in the code is worth a pull request of its own. The review
names its file and line without repeating the value, then stops there, as the
skill says to, so anything planted beside it goes unread.

[`examples/ci/evals/`](../examples/ci/evals/) holds six changes like these, each with what a good
review of it finds. `python3 scripts/eval_agents.py examples/ci/evals` runs
them against the skill on your machine, which spends model tokens.
[Measuring a harness](harness-evals.md) has the rest.

### What the review can and can't be changed by

- It never approves, requests changes, merges or pushes. A person decides.
- Claude reads with Read, Grep and Glob only, and runs nothing from the pull
  request.
- The rules come from the harness, and the pull request's own copies can't
  change them. Its [`AGENTS.md`](../AGENTS.md), [`CLAUDE.md`](../CLAUDE.md), `CLAUDE.local.md` and [`.claude`](../.claude)
  folders, and its symlinks, are removed before the review starts, and the
  standards come from the factory repo's default branch.
- The caller is another matter. It lives in the product repo, so a pull request
  can edit it, as step 5 says.
- A pull request from a fork skips with a notice, since a fork gets no secrets.
  So does one with no `ANTHROPIC_API_KEY`, such as Dependabot's.

## The loop on a runner

Optional, and for the factory's own issues. [`examples/ci/loop.yml`](../examples/ci/loop.yml) runs
[`scripts/loop.py`](../scripts/loop.py) from the repo it sits in, so it goes in your factory repo, or
another repo that carries the factory, with a `loop.json` whose `test_command`
tests that repo. In a product repo that only calls the review, there's no loop
to run. To work a product repo's issues, run the loop on a machine with
`--project`, as [HOW-IT-WORKS.md](../HOW-IT-WORKS.md) (*The loop*) describes.

1. Copy [`examples/ci/loop.yml`](../examples/ci/loop.yml) into the factory repo's [`.github/workflows/`](../.github/workflows/).
2. Add `ANTHROPIC_API_KEY` as a secret.
3. Turn on Settings, Actions, General, "Allow GitHub Actions to create and
   approve pull requests", or opening the pull request fails.
4. Label an issue `loop-ready`. The loop builds only from an issue a
   collaborator wrote, or one nobody changed after it was labelled, so label
   only what you've read.

Two limits come with the workflow's own token:

- **Its pull request won't start your checks.** One opened with `GITHUB_TOKEN`
  triggers no other workflow.
- **It can't tell who you are,** so it takes only unassigned issues.

One change fixes both: add a fine-grained personal access token with contents,
issues and pull requests write, as a secret named `LOOP_GITHUB_TOKEN`, and swap
both `GITHUB_TOKEN` lines in the workflow for it.
[Off your laptop](../HOW-IT-WORKS.md#off-your-laptop) compares a runner with your own machine and an
always-on one.

Start with one product repo. Once its first real pull request has a review
comment you'd act on, add the caller to the next.
