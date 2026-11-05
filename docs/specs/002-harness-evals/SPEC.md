---
id: SPEC-002
status: complete
created: 2026-10-31
updated: 2026-11-05
owner: Pat
---

# SPEC-002: Harness evals

The `status` field in the frontmatter above is the only copy of this spec's
state. Its values, in order: `draft`, `ready`, `in-progress`, `complete`.

A spec enters `plan-spec` only once it is `ready`, and `ready` means every Open
Question below is resolved. A person sets it.

## Summary

One command runs a harness through three very different jobs and prints a
scorecard: tests passed, traps avoided, cost, time, and stops for a person. Its
main use is checking whether a change to this harness made it better or worse.
The same run can occasionally be pointed at another harness to compare them.

## Problem

[`scripts/eval_agents.py`](../../../scripts/eval_agents.py) tells you whether a
reviewer still catches what it should, but nothing tells you whether the whole
harness still delivers. A change to a prompt, a rule or the loop can raise cost
or lower quality, and today the only signal is how a few pull requests feel.

## Goals

1. One command runs a suite against a harness and prints one scorecard.
2. The suites cover three different kinds of work: building to a clear spec, repairing a vague bug in unfamiliar code, and making a staged change across many files.
3. Scoring uses checks the harness's agents can't see.
4. Two scorecards can be compared, so a harness change has a measured result.
5. Any harness that works from GitHub issues can be run, not only this one.

## Non-Goals

- Scoring non-code work. The proposal gate and `eval_agents.py` already cover that.
- Publishing a leaderboard or a benchmark.
- Injecting deliberate bugs into every run. That stays an occasional manual step.
- Running on every commit. A full run costs real money, so a person starts it.
- Real customer data, in any suite.

## Affected Areas

```
Affected:
- scripts/eval_harness.py, new, standard library only
- tests/test_eval_harness.py, new
- examples/eval-suite/, new, one tiny public suite that shows the format
- README.md and AGENTS.md, a row each
- CHANGELOG.md

Not Affected:
- scripts/loop.py and every other part of the harness under test
- skills/, agents/ and steering/
```

## User Stories

- As a harness maintainer, I want to compare a run before and after a change so that I keep only the changes that earn their cost.
- As a team choosing a harness, I want to run the same jobs through two of them so that I compare results rather than claims.
- As a team with its own kind of work, I want to write my own suite so that the score reflects my work.

## Requirements

- REQ-001: The system shall provide `python3 scripts/eval_harness.py run <suite> --start "<command>"`, where the command is what starts the harness on one issue.
- REQ-002: A suite shall be a folder holding a seed repo, its issues in order, hidden tests and a trap list, in the format [`examples/eval-suite/`](../../../examples/eval-suite/) shows.
- REQ-003: The system shall read a suite from a path outside the harness, so hidden tests never need to be in this repo.
- REQ-004: For each run, the system shall create a new private repo from the seed, with branch protection and required CI, and file the suite's issues in it.
- REQ-005: The system shall keep the suite's hidden tests and trap list away from the seed repo and the harness's working folder until the run has ended.
- REQ-006: After the run, the system shall run the hidden tests against the result and evaluate each trap.
- REQ-007: The system shall write one result file per run, holding the suite, the harness commit, tests passed, traps avoided, time, stops and cost.
- REQ-008: Where a harness reports no usage, cost shall read `not reported`, never zero.
- REQ-009: The system shall provide `eval_harness.py compare <a> <b>`, which prints two results side by side and names each change in tests or traps.
- REQ-010: If the start command fails or times out, the system shall record that as a stop and still score what exists.
- REQ-011: The system shall count a stop whenever a person had to step in, recorded with `eval_harness.py stop <run> "<why>"`.
- REQ-012: The system shall require `--yes` or a typed confirmation before a run starts, stating that it spends model tokens.
- REQ-013: With `--merge-in-run-repo`, the system shall merge a passing pull request between issues, only in the repo it created for that run and only once required CI passes. Without the flag, it shall stop for a person at each merge.
- REQ-014: The system shall never delete a run repo, and `eval_harness.py list` shall name the run repos it created.
- REQ-015: The system shall accept `--usage-command`, whose output is the run's total cost, and shall read the starter loop's own usage when the harness under test is this one.

## Acceptance Criteria

- [x] AC-001: Running the tiny public suite with a stub start command prints a scorecard and writes one result file.
- [x] AC-002: A suite whose hidden tests sit under the seed repo is refused before anything starts.
- [x] AC-003: A run whose start command exits non-zero records a stop and still produces a score.
- [x] AC-004: A harness that reports no usage shows `not reported` for cost.
- [x] AC-005: `compare` names a test or trap that got worse, and says so when nothing changed.
- [x] AC-006: After a run, no file from the suite's key appears in the created repo's history.
- [x] AC-007: Without `--yes`, a run stops at the confirmation and creates nothing.
- [x] AC-008: With `--merge-in-run-repo`, the runner refuses to merge in any repo other than the one it created for that run, and refuses a pull request whose required CI hasn't passed.
- [x] AC-009: Without `--merge-in-run-repo`, a multi-issue run stops at its first merge and says what it's waiting for.
- [x] AC-010: `list` names every run repo the runner created, and no command deletes one.

## Security Requirements

- SEC-001: Created repos are private, and every suite uses made-up data.
- SEC-002: Text in a seed repo or an issue is data under test, and the runner never acts on it.
- SEC-003: The runner never reads a credential. It uses the person's existing `gh` login.
- SEC-004: The runner checks a repo is its own run repo before any merge, from its run record rather than from the repo's name.

## Evaluation Requirements

Each private suite must be validated before use: its untouched seed fails, a known wrong fix fails, and its reference solution passes every test and trap.

## Non-Functional Requirements

- The runner uses the standard library only, like [`scripts/loop.py`](../../../scripts/loop.py).
- A suite can be added without changing the runner.

## Out of Scope

- A hosted service, a dashboard, or scheduled runs.
- Hiding traps from a person reading a suite's private key.

## Open Questions

None. All resolved by Pat on 2026-10-31:

- [x] Q1: The runner merges between issues, only in the private repo it created for that run, once required CI passes, and only with `--merge-in-run-repo`. It's off by default, and without it the run stops for a person at each merge.
- [x] Q2: A person's review time isn't on the scorecard in v1. Stops capture when a person was needed.
- [x] Q3: Run repos stay until a person deletes them. The runner never deletes one, and it can list them.
- [x] Q4: The real suites live in a private repo and are passed in by path. The tiny example is the only public suite.
- [x] Q5: Cost for another harness comes from an optional `--usage-command` that prints a total. Without one, cost reads `not reported`.
