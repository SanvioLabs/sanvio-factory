---
id: SPEC-003
status: ready
created: 2026-11-13
updated: 2026-11-13
owner: Pat
---

# SPEC-003: Factory interface, taking work from another factory

The `status` field in the frontmatter above is the only copy of this spec's
state. Its values, in order: `draft`, `ready`, `in-progress`, `complete`.

A spec enters `plan-spec` only once it is `ready`, and `ready` means every Open
Question below is resolved. A person sets it.

## Summary

This factory can already hand an issue to another factory and review what
comes back: [`factories/README.md`](../../../factories/README.md) and [`scripts/factories.py`](../../../scripts/factories.py). This spec is the
other direction. Someone else's setup sends work in, and this factory builds
it and hands back a reviewed pull request, so an outside team can use a
factory without running one.

GitHub stays the only interface. The caller opens an issue in their own repo
and adds a label. This factory's loop builds it from its own fork and opens a
pull request into the caller's repo. The caller's setup can be anything that
can open and label a GitHub issue: another copy of this factory, a different
harness, or a person.

The contract the caller sees is already written, from the caller's side, in
[`factories/README.md`](../../../factories/README.md) (*What the factory must do*, *Getting to ready*).
This spec doesn't restate it. It covers what this factory still lacks to be
the remote end of that contract, and the page that tells an outside team how
to use it.

## Problem

A copy of this factory can act as a remote factory today only by hand, and
not safely:

- **Its pull requests can't read ready.** The loop pushes `loop/issue-N` to
  the repo itself, so it needs write access, and a caller's harness reads its
  runs as `checks pass, not independent` at best. Issue #421 asks for a fork
  push, and says to plan it with a spec first.
- **Its rounds stop at the fork.** The loop takes a round only on its own
  pull request from a branch in the repo. A round on a pull request from its
  own fork is still to decide.
- **Outside text drives an agent on this machine.** `vouch()` in
  [`scripts/loop.py`](../../../scripts/loop.py) trusts an issue written by the repo's owner, members or
  collaborators. In a caller's repo, that's the caller's people, so their
  issue text becomes instructions to a build agent running here, and nothing
  on this side reads it first.
- **Callers aren't kept apart.** A build agent in one [`projects/`](../../../projects/) clone can
  read a sibling clone: the guard keeps `company/`, [`factories/`](../../../factories/) and the
  credential files out of reach, not other projects.
- **The caller can't see what ran.** A pull request records each step's model,
  tokens and cost, but not which factory commit built it or the account tier
  the agents ran on, which a caller's vendor review asks for.

## Goals

1. An outside setup submits one issue to this factory by label, and gets back
   one pull request that its own harness can read `ready for a person`.
2. A review that asks for changes goes back to this factory as a round, on the
   same pull request from the fork.
3. Nothing a caller writes reaches a build agent before this factory's side
   has accepted it as a work order.
4. One caller's repo, issues and pull requests never reach another caller's
   build.
5. Each pull request says what built it: the factory's commit, each model, the
   account tier, and tokens and cost.
6. An outside team can follow one public page from nothing to its first
   returned pull request.

## Non-Goals

- Real material. v1 runs on sandbox repos holding invented data only. Taking a
  caller's own code or their customers' material is a later amendment, with
  its own approvals.
- Any transport but GitHub. An MCP server and the Agent2Agent protocol are
  later options, specced once v1 has run.
- Forges other than github.com, which is #422.
- Merging, approving or closing anything in a caller's repo.
- Hosting this factory for callers as a service. Where it runs, and billing,
  are decided outside this repo.
- Changing how this factory dispatches to another one. That's
  [`factories/README.md`](../../../factories/README.md) as it stands.

## Affected Areas

```
Affected:
- scripts/loop.py and tests/test_loop.py: fork push and rounds on a fork pull
  request (#421), the intake hold, the work-order check, the build record
- .claude/hooks/guard.py and tests/test_agent_hooks.py: a caller project's
  build agent confined to its own clone
- docs/factory-interface.md, new: the page an outside team follows
- factories/README.md: points a caller at docs/factory-interface.md, and
  closes "a round on a pull request from its own fork is still to decide"
- HOW-IT-WORKS.md: the new loop.json keys
- README.md, CHANGELOG.md

Not Affected:
- scripts/factories.py and how it reads ready
- skills/ and agents/
- any project's own loop.json, which still can't set a machine key
```

## User Stories

| ID | Story |
|---|---|
| US-001 | As an outside team, I want to send a ticket to a factory by labelling an issue in my own repo, so that I don't have to run a factory to use one. |
| US-002 | As that team, I want the pull request that comes back to read `ready for a person` in my own harness, so that I can trust its checks as much as my own. |
| US-003 | As the person running this factory, I want to read each outside work order before anything builds it, so that a stranger's text never steers an agent on my machine unread. |
| US-004 | As that person, I want each caller kept in its own clone with its own budget, so that one caller never sees another's work or spends their tokens. |
| US-005 | As a caller facing a vendor review, I want each pull request to say what built it, so that I can answer which models and accounts touched the work. |

## Requirements

| ID | Pattern | Requirement |
|---|---|---|
| REQ-001 | Optional | Where a project's entry in the factory's `loop.json` sets `fork` to `OWNER/NAME`, the loop shall push every `loop/issue-N` branch for that project to the fork, never to `origin`, and open its pull request into `origin`'s base from `<fork owner>:loop/issue-N`. This is #421's acceptance criteria, which this spec takes in whole. |
| REQ-002 | Event-Driven | When the loop takes a round on an issue whose open pull request comes from the configured fork, it shall start from the fork's branch and update that pull request, and it shall still refuse a pull request from any other fork. |
| REQ-003 | Unwanted Behavior | If `fork` can't be reached or isn't a fork of `origin`, then the loop shall block the issue with a comment saying why, and push nothing. |
| REQ-004 | Optional | Where a project's entry sets `caller` to true, the loop shall treat it as an outside caller's repo, and REQ-005 to REQ-012 shall apply to it. |
| REQ-005 | State-Driven | While a caller project's issue has not been accepted, the loop shall not plan or build it. Accepting is a person on this factory's side adding the project's `accept_label` to the issue, read from that label event's actor, who must be in the entry's `acceptors` list. |
| REQ-006 | Unwanted Behavior | If a caller's issue changes after it was accepted, or holds an HTML comment, then the loop shall block it, naming which, as `vouch()` does for an outsider's issue today. |
| REQ-007 | Event-Driven | When a caller's issue is picked, the loop shall check it has an objective, acceptance criteria, a scope and a way to verify it, before the plan step, and block it with the stopped label and what's missing when it doesn't. |
| REQ-008 | Ubiquitous | A caller project's build agent shall read and write only inside that issue's worktree: the guard shall refuse a path in another project's clone, another worktree, or the factory's root. |
| REQ-009 | Ubiquitous | A caller project shall run with `network_allow` set and `max_issue_tokens` above 0, and the loop shall refuse to start a caller project that has either unset. |
| REQ-010 | Ubiquitous | Auto-merge shall never act on a caller project, whatever `auto_merge` says. |
| REQ-011 | Event-Driven | When the loop opens or updates a caller's pull request, its body shall record the factory's commit, each step's model, the account tier named in the entry's `account_tier`, and tokens and cost, with cost reading `not reported` where it wasn't. |
| REQ-012 | Ubiquitous | The loop shall post nothing in a caller's repo but its pull request, its review and the comments a block or a round needs, each with mentions stripped. |
| REQ-013 | Ubiquitous | `docs/factory-interface.md` shall take an outside team from nothing to a returned pull request: the account and access to grant, the labels, the fork workflow settings, what a work order needs, what comes back, and how to send it back for a round. |

## Acceptance Criteria

| ID | Requirement | Criteria | Verification |
|---|---|---|---|
| AC-001 | REQ-001 to REQ-003 | #421's acceptance criteria pass as written | Tests in [`tests/test_loop.py`](../../../tests/test_loop.py) with a stand-in `gh` and two local remotes |
| AC-002 | REQ-004, REQ-005 | An unaccepted issue on a caller project is never planned; one accepted by someone outside `acceptors` isn't either; one accepted by someone in it is | Unit test |
| AC-003 | REQ-006 | An issue edited after acceptance, and one holding an HTML comment, each block with the reason | Unit test |
| AC-004 | REQ-007 | An issue missing acceptance criteria blocks before any agent runs, naming what's missing | Unit test that records every agent call |
| AC-005 | REQ-008 | The guard refuses a caller build agent's read of a sibling project's file and of the factory's `loop.json`, and allows its own worktree | Test in [`tests/test_agent_hooks.py`](../../../tests/test_agent_hooks.py) |
| AC-006 | REQ-009 | A caller project with no `network_allow`, or with `max_issue_tokens` of 0, is refused at start | Unit test |
| AC-007 | REQ-010 | With `auto_merge` on and a caller project's base in `bases`, no merge call is made | Unit test that records every `gh` call |
| AC-008 | REQ-011 | A caller's pull request body names the factory commit, each model, the account tier and the cost | Unit test |
| AC-009 | REQ-001 to REQ-013 | An outside setup labels one issue in a private sandbox repo holding invented data, a person here accepts it, and a pull request comes back from this factory's fork that the caller's `factories.py status` reads `ready for a person` | A live run, recorded in this spec's TASKS.md |
| AC-010 | REQ-013 | Someone who has never used this factory follows `docs/factory-interface.md` alone and gets to AC-009 without asking a question | A live run, recorded with what they had to ask |

## Security Requirements

| ID | Requirement |
|---|---|
| SEC-001 | Everything a caller writes (issue, comments, pull request reviews, repo contents) is untrusted text. It reaches an agent only after REQ-005 and REQ-007, and a reviewer reads it with read tools only, as the loop's review does today. |
| SEC-002 | This factory's account holds triage on the caller's repo and owns its fork, and nothing more. The loop reads no credential, and uses the `gh` login the machine already has. |
| SEC-003 | No caller's repo, issue text or pull request reaches another caller's clone, prompt, lessons or report. `.loop/lessons.md` entries from a caller project stay in that project. |
| SEC-004 | A caller can't widen what this factory does: a caller's repo sets nothing in this factory's `loop.json`, and its own `loop.json`, if it has one, can't set a machine key. |

## Privacy and Compliance Requirements

| ID | Requirement |
|---|---|
| PRIV-001 | v1 takes sandbox repos holding invented data only. `docs/factory-interface.md` says so, and says that real material needs a written agreement first, per [`steering/data-and-tools.md`](../../../steering/data-and-tools.md). |
| PRIV-002 | Nothing tracked in this repo names a caller, their repo or their account. Caller entries live in the gitignored `loop.json`. |

## Observability Requirements

| ID | Requirement |
|---|---|
| OBS-001 | The loop's log names each caller issue's acceptance, block, round and return, with the caller project's name. |
| OBS-002 | Tokens and cost per caller project show in the factory dashboard, as they do per project today. |

## Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-001 | Python 3.9 or newer, standard library only, like the rest of [`scripts/loop.py`](../../../scripts/loop.py). |
| NFR-002 | A factory with no `fork` and no `caller` project behaves as it does today, and every existing test passes unchanged. |

## Constraints

- **Built by hand, never on the loop.** It changes where the loop pushes and
  what a stranger's issue can reach, which #421 rates high risk.
- **A caller's own harness reads ready.** This factory meets
  [`factories/README.md`](../../../factories/README.md)'s *Getting to ready* on its side (its own fork, triage
  only). The caller's side (required checks, fork workflows on without write
  tokens) is the caller's to set, and `docs/factory-interface.md` says how.
- **The levers start held.** Every caller issue waits for a person here
  (REQ-005). Letting go of that check is a later change, made once the
  work-order check (REQ-007) has caught what the person would have.

## Open Questions

None. All resolved by Pat on 2026-11-13:

- [x] Q1: The spec lives in this repo, public. Who a caller is, and the
  commercial terms, stay outside it.
- [x] Q2: v1's transport is GitHub issues and pull requests.
- [x] Q3: v1 is the contract plus the GitHub transport, proved by one outside
  setup's ticket coming back as a reviewed pull request (AC-009).
- [x] Q4: v1 runs on invented data only.
- [x] Q5: A machine user runs this factory for callers. It holds triage on
  each caller's repo and owns the forks, so no person's own login has access
  anywhere a caller can see, and access is revoked caller by caller.
- [x] Q6: A person here accepts each work order by label (REQ-005). An
  allowlist of the caller's own logins is a later lever, once the work-order
  check has caught what the person would have.
- [x] Q7: In v1, confining the build agent to its worktree (REQ-008) keeps
  callers apart. Once real material comes in, each caller gets a separate
  machine.
- [x] Q8: The work-order check (REQ-007) is a fixed check in
  [`scripts/loop.py`](../../../scripts/loop.py), with no model call.
