---
id: lightweight-loop
status: draft
created: 2026-10-09
updated: 2026-10-09
owner: Pat
---

# Spec: the lightweight loop

## Status

`Draft`. Three Open Questions are unresolved.

This spec was written after the first build, from what [`scripts/loop.py`](../../scripts/loop.py) does and what [`tests/test_loop.py`](../../tests/test_loop.py) proves. The requirements describe built behavior. The Open Questions are where it is still a guess.

## Summary

[`scripts/loop.py`](../../scripts/loop.py) takes an open GitHub issue labelled `loop-ready` through the flywheel: plan it, build it, check it, open a pull request. It is the small version of a runner for a team with one repo, one agent tool and a person who wants to watch a plain log. It never merges unless the owner turns on `auto_merge`.

## Problem

[`HOW-IT-WORKS.md`](../../HOW-IT-WORKS.md) said a bigger harness adds a runner that works tickets without a person at the keyboard, and the starter shipped none. A team that wanted one had to build it from nothing, or adopt a full runner built to manage many projects, dispatch by voice and steward pull requests. Either is far more than a first loop needs.

## Goals

1. One pass is one turn of the flywheel: Discover, Shape, Build, Validate, Scale, each a named step in the log.
2. The agent never grades its own work: the script runs the tests, and a pass needs both the tests and a fresh reviewer.
3. A person can watch it with `tail -f` and build their own monitor from the log and the per-issue files.
4. A failure ends in a labelled issue and a lesson, never in a loop that retries forever.
5. It is one standard-library file, small enough to read in one sitting and change.

## Non-Goals

- Running many projects or many issues at once.
- Merging by default. A person merges unless the owner turns on `auto_merge` in the factory's `loop.json`.
- A dispatcher, voice control, a dashboard, a database, or routing work to different models by tier.
- Holding credentials. It uses the person's own agent and `gh` sign-in.

## Affected Areas

```
Affected:
- scripts/loop.py
- tests/test_loop.py
- HOW-IT-WORKS.md, README.md, CHANGELOG.md
- skills/learn/SKILL.md (reads .loop/lessons.md)
- .gitignore (.loop/)
```

## User Stories

| ID | Story |
|---|---|
| US-001 | As a team lead, I want ready issues worked through the same plan, build, check and review each time, so that I read pull requests, not transcripts. |
| US-002 | As a developer, I want one log I can tail, so that I know what the loop is doing without opening a dashboard. |
| US-003 | As the harness owner, I want what went wrong written down in a shape `learn` reads, so that a failure becomes a rule. |

## Requirements

| ID | Pattern | Requirement |
|---|---|---|
| REQ-001 | Event-Driven | When `run` starts and no other loop holds the lock, the loop shall take the lowest-numbered open issue labelled `ready_label` that does not carry `blocked_label` and is unassigned or assigned to the signed-in user. |
| REQ-002 | Event-Driven | When an issue is taken, the loop shall write `ticket.md`, then a fresh reader agent's plan to `plan.md`, under `.loop/issue-N/`. |
| REQ-003 | Event-Driven | When a plan exists, the loop shall build in a git worktree on `loop/issue-N`, started from `origin/<base>`, outside the clone, using a fresh agent session whose prompt carries the plan and, after a failed round, the last review and test output. |
| REQ-004 | Event-Driven | When a round is built, the loop shall run `test_command` itself in the worktree and save its output, then run a fresh reader agent on the plan, the diff and that output. |
| REQ-005 | Ubiquitous | The loop shall count a round as passed only when the tests exit 0 and the last `VERDICT:` line of the review is PASS. A review with no verdict counts as FIX. |
| REQ-006 | Unwanted | If the reader agent leaves uncommitted changes in the worktree, then the loop shall discard them and log it. |
| REQ-007 | Unwanted | If a round fails `max_rounds` times, or an agent exits non-zero, then the loop shall remove `ready_label` from the issue, then add `blocked_label`, append a lesson, log BLOCKED, and go on to the next issue. |
| REQ-008 | Event-Driven | When a round passes, the loop shall push the branch, open a pull request against `base` without merging it, remove `ready_label`, and append a lesson if it took more than one round. |
| REQ-009 | Ubiquitous | The loop shall append one line per event to `.loop/loop.log` as `time #issue STEP detail`, with steps DISCOVER, SHAPE, BUILD, VALIDATE, SCALE, REVIEW, BLOCKED, STOPPED, IDLE and ERROR, and shall write no agent output or credential to it. |
| REQ-010 | Ubiquitous | The loop shall write each lesson to `.loop/lessons.md` as a heading, **What went wrong** and **What should have happened**, the shape [`skills/learn`](../../skills/learn) reads. |
| REQ-011 | Unwanted | If another live process holds `.loop/lock`, then `run` shall refuse and exit 1. A lock whose process is gone is replaced. |
| REQ-012 | Event-Driven | When `stop` is run, a running loop shall end at its next step and log STOPPED. |
| REQ-013 | Optional | Where `--dry-run`, `--once` or `--issue N` is given, the loop shall only name the issue it would take, take one issue, or take only that issue. |
| REQ-014 | Ubiquitous | The loop shall read its settings from `loop.json` at the repo root, each key defaulting when absent. |
| REQ-015 | Unwanted | If the issue is no longer open when a round passes, then the loop shall not push or open a pull request, and shall log that it skipped. |
| REQ-016 | Event-Driven | When the loop opens a pull request, its body shall say `Closes #N`, and the loop shall comment the link and the round count on the issue. When it blocks an issue, it shall comment the reason, the round count where there is one, and how to put it back. A comment that fails is logged as ERROR and changes nothing else. Added 2026-10-09. |

## Acceptance Criteria

| ID | Requirement | Criteria | Verification |
|---|---|---|---|
| AC-001 | REQ-001 | Lowest ready issue wins; blocked, unlabelled and other people's issues are skipped | `test_pick_takes_the_lowest_ready_issue_you_may_take` |
| AC-002 | REQ-002, 003, 004, 008 | A good change logs the five steps in order and opens a pull request | `test_a_good_change_opens_a_pull_request_in_five_steps` |
| AC-003 | REQ-003 | The checkout is outside the clone | `test_checkouts_live_outside_the_clone` |
| AC-004 | REQ-003, 004 | Prompts carry the plan, the diff, the output and any earlier review | `test_prompts_carry_their_inputs_so_the_agent_needs_no_file_access` |
| AC-005 | REQ-005 | Failing tests block even when the reviewer says PASS; no verdict is FIX | `test_failing_tests_block_even_when_the_reviewer_says_pass`, `test_verdict_is_the_last_line_and_defaults_to_fix` |
| AC-006 | REQ-006 | A reviewer's edits do not reach the diff | `test_a_reviewer_that_edits_files_has_them_thrown_away` |
| AC-007 | REQ-007, 010 | After the limit the label comes off before blocked goes on, and a lesson is written | `test_a_change_that_keeps_failing_is_blocked_with_the_label_taken_off_first` |
| AC-008 | REQ-011 | A second loop is refused; a stale lock is replaced; another user's process is respected | the three lock tests |
| AC-009 | REQ-012 | A stop file ends the loop between steps | `test_a_stop_file_ends_the_loop_between_steps` |
| AC-010 | REQ-013 | Dry run names an issue and starts no agent; nothing ready logs IDLE once | `test_dry_run_names_the_issue_and_starts_no_agent`, `test_nothing_ready_logs_idle_once` |
| AC-011 | REQ-014 | Defaults overlay from `loop.json` | `test_config_overlays_defaults_from_loop_json` |
| AC-012 | REQ-015 | A change for an issue closed meanwhile pushes nothing and opens no pull request | `test_a_change_for_an_issue_closed_meanwhile_opens_no_pull_request` |
| AC-013 | REQ-016 | The pull request closes the issue and the issue gets the link; a blocked issue gets why and how to retry; a failed comment leaves the pull request standing | `test_a_pull_request_closes_the_issue_and_the_issue_hears_about_it`, `test_a_blocked_issue_says_why_and_how_to_retry`, `test_a_comment_that_fails_is_logged_and_the_pull_request_stands` |

All run with `python3 -m unittest discover -s tests`. The tests use a temporary git repo, a stand-in agent and a stand-in `gh`.

Run by hand, not in CI, 2026-10-09: a real issue in a private scratch repo ("create hello.txt"), real `gh`, real `claude -p` (Haiku), the starter's full test suite plus a one-line check as `test_command`. It went Discover to Scale in about 45 seconds in one round, opened a real pull request against `main` with a one-line diff, took `loop-ready` off the issue, and merged nothing.

## Security Requirements

| ID | Requirement |
|---|---|
| SEC-001 | A ticket is an instruction to an agent. The loop shall act only on issues carrying `ready_label`, and the README shall say to label only issues the team wrote or read. |
| SEC-002 | The loop shall never merge unless the owner sets `auto_merge.enabled` to true in the factory's `loop.json`, never a project's. Then `review` shall merge only a pull request it graded at least `min_grade` on its current head, by an author in `authors`, into a base in `bases`, with at least one check and every check passed, and never a fork or a draft. The loop shall never hold or read a credential. It runs on the person's own agent and `gh` sign-in. |
| SEC-003 | The reader agent shall be told not to edit, and any edit it makes shall be discarded (REQ-006). |

## Privacy / Compliance Requirements

| ID | Requirement |
|---|---|
| PRIV-001 | Ticket text, the plan, the diff and the test output are sent to the agent the team configured, as in any session. The loop shall add no other destination. |
| PRIV-002 | The log shall carry issue numbers, step names and counts, never ticket text or agent output. |

## Infrastructure Requirements

None identified for this spec.

## Observability Requirements

| ID | Requirement |
|---|---|
| OBS-001 | The log is the whole interface (REQ-009). The per-issue files are the second: `ticket.md`, `plan.md`, `test-output.txt`, `diff.patch`, `review.md`. |

## Database Requirements

None identified for this spec.

## Evaluation Requirements

None identified for this spec. The reviewer is an agent, and its noise is an Open Question below, not an evaluated behavior.

## Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-001 | One Python file, standard library only, Python 3.9 or newer, needing only `git` and a signed-in `gh`. |
| NFR-002 | Each agent call times out after `agent_timeout` seconds (1800), and the tests after `test_timeout`. A timeout is a failed round, not a hang. |

## Constraints

- Agents in a worktree cannot read the loop's own folder, so everything an agent needs goes in its prompt.
- A worktree nested inside the clone makes an agent load the clone's [`CLAUDE.md`](../../CLAUDE.md) as well, which tells it to stop. Checkouts live in `~/.sanvio-loop/`; before the rename they were in `~/.harness-loop/`, which only the token reports still read.

## Dependencies

`git`, `gh`, and one agent tool that takes a prompt on stdin (`claude -p` by default; Codex works the same way).

## Out of Scope

- Issues from a `tickets/` folder for teams without GitHub issues.
- Running on a schedule or as a service.
- Resuming mid-round after a crash. A restart takes the issue again from Shape, on the existing branch.
- A spend or token limit per issue.

## Open Questions

1. **Other agent tools.** The defaults are `claude -p` flags. Codex and Kiro flags for "may edit" and "read only" are not tested.
2. **Reviewer noise.** In the live run the reviewer listed five problems and still said PASS. Should a PASS need an empty problem list, or is the verdict enough?
3. **When the ready label comes off.** It comes off when the pull request opens, so a closed or abandoned PR needs a person to relabel. Leave it on until merge instead?

## Decisions

Pat, 2026-10-09:

- **A setup warning in the plan:** document it, don't strip it. [`HOW-IT-WORKS.md`](../../HOW-IT-WORKS.md) tells the reader to run [`scripts/check_setup.py`](../../scripts/check_setup.py) and fix any FAIL before the first run.
- **Shape stays its own session.** It costs one more agent call per issue and gives the builder and the reviewer the same plan.
- **A closed issue gets no pull request.** REQ-015.
