---
spec: SPEC-003
status: draft
created: 2026-11-13
updated: 2026-11-13
---

# Implementation Plan: SPEC-003

## Specification

Link: [`SPEC.md`](SPEC.md). Its status when this plan was written: `ready` as of
2026-11-13. If the spec changes after this date, this plan may be stale.

## Repository Analysis

Read for this plan:

- [`scripts/loop.py`](../../../scripts/loop.py):
  - `PROJECT_KEYS` and `MACHINE_KEYS` (line 471), `load_project_config()` (line 476) and the project check that refuses a machine key in a project's own `loop.json` (line 615)
  - `vouch()` (line 810) and `ISSUE_QUERY` (line 216), whose `LabeledEvent` carries no actor today
  - `SANDBOX_DENY_READ` and `sandbox_settings()` (lines 873 and 877), `env_for_agents()` (line 918), and `Loop.argv()` (line 2346), which builds a build agent's `--settings`
  - `Loop.discover()` and `Loop.fresh()` (lines 2578 and 2620), where an issue is picked and then vouched for
  - `Loop.open_pr()` (line 2788), which takes only a pull request with `isCrossRepository` false, and `Loop.from_origin()`
  - the two pushes: an issue's branch (line 3312) and the merge pass that keeps both [`CHANGELOG.md`](../../../CHANGELOG.md) entries (line 3535)
  - `pr_body()` (line 1440), `auto_merge_problem()` (line 1643) and `Loop.merge_when_ready()` (line 4194)
- [`.claude/hooks/guard.py`](../../../.claude/hooks/guard.py): `PRIVATE_FOLDERS` and the headless rules. It keeps `company/`, `local-data/`, `.inbox/` and [`factories/`](../../../factories/) from a headless run, and nothing keeps one [`projects/`](../../../projects/) clone from another.
- [`factories/README.md`](../../../factories/README.md): the contract from the caller's side, and *Getting to ready*.
- [`scripts/factories.py`](../../../scripts/factories.py): how a caller's harness reads ready. Unchanged here.
- Factory issue #421, which this spec takes in whole.
- [`tests/test_loop.py`](../../../tests/test_loop.py) and [`tests/test_agent_hooks.py`](../../../tests/test_agent_hooks.py): a stand-in `gh` first on `PATH`, and bare local remotes.

## Existing Patterns

- **Machine keys in the factory's `loop.json`, never a project's own.** Every new key here is one: `fork`, `caller`, `accept_label`, `acceptors`, `account_tier`.
- **Refuse at start, not per issue.** `sandbox_problem()` stops a run before any issue is taken. REQ-009's check goes beside it.
- **A block says why on the issue.** `Loop.block()` takes the ready label off, adds the blocked label and comments. In a caller's repo those are the caller's submit and stopped labels, which is how the caller's `factories.py` sees a stop.
- **A hold waits without a comment.** `Loop.hold()` keeps an issue in the queue with a reason on its row. An issue not yet accepted is held, not blocked: blocking would end the caller's run before anyone here has read it.
- **Mentions stripped from anything posted:** `safe_to_post()`.
- **Every `gh` call recorded in a test**, to prove a call is never made.

## Architecture Impact

No new script. `loop.py` gains a caller mode, switched on per project in the factory's `loop.json`:

```json
{
  "projects": {
    "caller-sandbox": {
      "caller": true,
      "fork": "factory-bot/caller-sandbox",
      "ready_label": "factory:submit",
      "blocked_label": "factory:stopped",
      "accept_label": "factory:accepted",
      "acceptors": ["a-person-here"],
      "account_tier": "Claude Team",
      "network_allow": ["github.com", "pypi.org"],
      "max_issue_tokens": 4000000,
      "review_logins": ["the-callers-login"]
    }
  }
}
```

`ready_label` and `blocked_label` are project keys today. A caller project sets
them in the factory's entry. Its own `loop.json` sits in the caller's repo,
which the caller can push to, so in caller mode the loop ignores those two keys
there.

An issue on a caller project goes:

```
caller labels submit -> discover lists it -> held until a person here labels accept
  -> fresh(): accepted by an acceptor, unchanged since, no HTML comment
  -> work-order check: objective, acceptance criteria, scope, verification
  -> plan, build (confined to its worktree), test, review
  -> push to the fork, pull request from fork into origin's base, with the build record
```

## Files Expected to Change

| File | Change |
|---|---|
| [`scripts/loop.py`](../../../scripts/loop.py) | The fork remote, both pushes, `open_pr`, rounds from the fork, caller mode, the intake hold, the work-order check, confinement settings, auto-merge refusal, the build record |
| [`tests/test_loop.py`](../../../tests/test_loop.py) | Tests for each of those |
| [`.claude/hooks/guard.py`](../../../.claude/hooks/guard.py) | With `SANVIO_CONFINE` set, refuse a file path outside the named folders |
| [`tests/test_agent_hooks.py`](../../../tests/test_agent_hooks.py) | Its tests |
| [`factories/README.md`](../../../factories/README.md) | Points a caller at `docs/factory-interface.md`, and replaces "a round on a pull request from its own fork is still to decide" |
| [`HOW-IT-WORKS.md`](../../../HOW-IT-WORKS.md) | The new keys in the `loop.json` table, and a short *Taking work from another factory* section |
| [`README.md`](../../../README.md) | A row in the Guides table |
| [`CHANGELOG.md`](../../../CHANGELOG.md) | One entry for the feature |

## New Files Expected

| File | Purpose |
|---|---|
| `docs/factory-interface.md` | The page an outside team follows (REQ-013) |

## Data Model Changes

None. `ISSUE_QUERY` adds `actor { login }` to `LabeledEvent`, read only in caller mode.

## API / Interface Changes

Five machine keys in the factory's `loop.json`, under a project's entry:

| Key | Default | Meaning |
|---|---|---|
| `fork` | `null` | `OWNER/NAME` of the fork the loop pushes this project's branches to |
| `caller` | `false` | This project is an outside caller's repo |
| `accept_label` | `"factory:accepted"` | The label a person here adds to accept a work order |
| `acceptors` | `[]` | The logins whose accept label counts. Empty accepts nothing |
| `account_tier` | `null` | The plan the agents run on, as the pull request should name it. Required in caller mode |

## Infrastructure Changes

None in this repo. A person creates the machine user, its fork of each caller's
repo, and the caller's grant of triage to it (Q5).

## Security Considerations

- SEC-001: a caller's text reaches an agent only after `fresh()` has checked acceptance (REQ-005, REQ-006) and the work-order check (REQ-007) has passed. The review step stays read-only.
- SEC-002: `fork` must be a fork of `origin` owned by the login the loop runs as (`gh api repos/{fork} --jq .parent.full_name, .owner.login`). The loop reads no token.
- SEC-003: lessons are already per project (`state_dir()` names the project), so a caller's lessons stay with it. Confinement (REQ-008) keeps a build from reading another caller's clone or state.
- SEC-004: caller mode reads `ready_label` and `blocked_label` only from the factory's entry, and the existing check already refuses a machine key in the project's own `loop.json`.
- Confinement has two layers. Claude Code's sandbox `denyRead` covers the shell, and `permissions.deny` `Read(...)` rules cover the Read, Grep and Glob tools, which the sandbox doesn't touch. Each names the factory root's private folders and `loop.json`, every other project's clone, and every other project's state and worktrees. The guard's `SANVIO_CONFINE` check is the backstop. None of them is proven until T013 shows it refusing in a live session on the installed Claude Code.

## Observability

- OBS-001: `ACCEPT`, `HELD` (waiting for acceptance) and `ORDER` (work-order check) log lines, with the project's name, through the existing `log()`.
- OBS-002: the dashboard already splits loop spend by project from each project's `.loop/`. T017 checks that a caller project shows, and changes nothing if it does.

## Evaluation Strategy

No model output is graded here. The work-order check is deterministic. AC-009 and AC-010 are live runs, recorded in [`TASKS.md`](TASKS.md).
