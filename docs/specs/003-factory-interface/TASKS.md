---
spec: SPEC-003
status: draft
created: 2026-11-13
updated: 2026-11-13
---

# Tasks: SPEC-003

Execution state for this spec. A fresh session resumes from this file's
checkboxes and the Requirement Traceability table. Task IDs run across the whole
spec. Built by hand, never on the loop (the spec's Constraints). `TESTS` below
means:

```
python3 -m unittest tests.test_loop tests.test_agent_hooks
```

## Phase 1: Fork push and rounds (#421)

- [ ] T001 Add the `fork` machine key. At start, check it's `OWNER/NAME`, reachable, a fork of `origin`, and owned by the login the loop runs as. Otherwise block each issue with a comment saying why, and push nothing
  - Requirements: REQ-001, REQ-003
  - Acceptance: AC-001
  - Security: SEC-002
  - Depends on: None
  - Verification: `TESTS`
- [ ] T002 With `fork` set, add it as a `fork` remote in the clone and push each `loop/issue-N` there (line 3312), never to `origin`. The merge pass that keeps both `CHANGELOG.md` entries (line 3535) pushes there too
  - Requirements: REQ-001
  - Acceptance: AC-001
  - Depends on: T001
  - Verification: `TESTS`, with two bare local remotes
- [ ] T003 Open the pull request into `origin`'s base from `<fork owner>:loop/issue-N`
  - Requirements: REQ-001
  - Acceptance: AC-001
  - Depends on: T002
  - Verification: `TESTS`
- [ ] T004 `open_pr` checks the fork for the branch, and takes a cross-repository pull request only when its head repository is the configured fork. Any other fork's is still refused
  - Requirements: REQ-002
  - Acceptance: AC-001
  - Depends on: T003
  - Verification: `TESTS`
- [ ] T005 A round resets from the fork's branch, not `origin`'s, and updates the same pull request
  - Requirements: REQ-002
  - Acceptance: AC-001
  - Depends on: T004
  - Verification: `TESTS`
- [ ] T006 Without `fork`, the loop pushes to `origin` as today, and every existing test passes unchanged
  - Requirements: NFR-002
  - Depends on: T005
  - Verification: `python3 -m unittest discover -s tests`

## Phase 2: Caller intake

- [ ] T007 Add the `caller`, `accept_label`, `acceptors` and `account_tier` machine keys. In caller mode, take `ready_label` and `blocked_label` from the factory's entry and ignore them in the project's own `loop.json`. Refuse to start a caller project with no `network_allow`, a `max_issue_tokens` of 0, or no `account_tier`
  - Requirements: REQ-004, REQ-009
  - Acceptance: AC-006
  - Security: SEC-004
  - Depends on: None
  - Verification: `TESTS`
- [ ] T008 Add `actor { login }` to `ISSUE_QUERY`'s `LabeledEvent`. In caller mode, hold an issue (a queue row, a `HELD` log line, no comment) until it carries `accept_label` added by a login in `acceptors`
  - Requirements: REQ-005
  - Acceptance: AC-002
  - Security: SEC-001
  - Depends on: T007
  - Verification: `TESTS`
- [ ] T009 In caller mode, block an accepted issue that changed after the accept label or holds an HTML comment, naming which, whoever wrote it
  - Requirements: REQ-006
  - Acceptance: AC-003
  - Security: SEC-001
  - Depends on: T008
  - Verification: `TESTS`
- [ ] T010 The work-order check: before the plan step, a caller issue needs `## Objective`, `## Acceptance Criteria`, `## Scope` and `## Verification` sections, each with text. One that doesn't is blocked naming what's missing, before any agent runs
  - Requirements: REQ-007
  - Acceptance: AC-004
  - Depends on: T009
  - Verification: `TESTS`, recording every agent call

## Phase 3: Isolation

- [ ] T011 For a caller project's build and tester agents, add to `--settings`: sandbox `denyRead` and `permissions.deny` `Read(...)` rules for the factory's private folders and `loop.json`, every other project's clone, and every other project's state folder and worktrees. Set `SANVIO_CONFINE` to the issue's worktree and the clone's `.git`
  - Requirements: REQ-008
  - Acceptance: AC-005
  - Security: SEC-003
  - Depends on: T007
  - Verification: `TESTS`, reading the settings `argv()` builds
- [ ] T012 In the guard, with `SANVIO_CONFINE` set, refuse a Read, Edit, Write, Grep or Glob path outside the named folders, and a Bash command naming one
  - Requirements: REQ-008
  - Acceptance: AC-005
  - Depends on: None
  - Verification: `python3 -m unittest tests.test_agent_hooks`
- [ ] T013 Live check on this machine's Claude Code, with T011's settings in a scratch layout of two projects: the shell's `cat` and the Read tool on the sibling's file are both refused, and the agent's own worktree works. Record the Claude Code version and the result here
  - Requirements: REQ-008
  - Acceptance: AC-005
  - Depends on: T011, T012
  - Verification: the recorded run

## Phase 4: What comes back

- [ ] T014 `auto_merge` never acts on a caller project, whatever its `bases`
  - Requirements: REQ-010
  - Acceptance: AC-007
  - Depends on: T007
  - Verification: `TESTS`, recording every `gh` call
- [ ] T015 A caller's pull request body gets a *Built by* block: the factory's commit, each step's model from the usage record, `account_tier`, and tokens and cost, with cost reading `not reported` where it wasn't
  - Requirements: REQ-011
  - Acceptance: AC-008
  - Depends on: T007
  - Verification: `TESTS`
- [ ] T016 A whole caller run, recorded call by call, posts only its pull request, its review and the comments a hold, block or round needs, each passed through `safe_to_post()`
  - Requirements: REQ-012
  - Depends on: T010, T015
  - Verification: `TESTS`
- [ ] T017 Check that the dashboard shows a caller project's spend as it does any project's. Change nothing if it does
  - Requirements: OBS-002
  - Depends on: T015
  - Verification: `python3 scripts/dashboard_data.py` against a scratch caller project

## Phase 5: The page, and the live runs

- [ ] T018 Write `docs/factory-interface.md`: invented data only (PRIV-001); the account to grant triage to; the labels; the fork workflow settings from *Getting to ready*; what a work order needs; what comes back; how to send it back for a round. Point [`factories/README.md`](../../../factories/README.md) to it and replace "still to decide". Add the keys to [`HOW-IT-WORKS.md`](../../../HOW-IT-WORKS.md), a row to [`README.md`](../../../README.md), and one [`CHANGELOG.md`](../../../CHANGELOG.md) entry
  - Requirements: REQ-013
  - Security: PRIV-001, PRIV-002
  - Depends on: T016
  - Verification: `python3 scripts/link_files.py --check` and `python3 -m unittest tests.test_changelog`
- [ ] T019 A person creates the machine user, a private sandbox caller repo holding invented data, and the fork, and sets the caller entry in this factory's `loop.json`. Nothing tracked names them
  - Requirements: Q5, PRIV-002
  - Depends on: T018
  - Verification: `python3 scripts/check_setup.py` and `loop.py run --dry-run`
- [ ] T020 Live: an outside setup labels one work order in the sandbox repo, a person here accepts it, and a pull request comes back from the fork that the caller's `factories.py status` reads `ready for a person`. Record the run here
  - Requirements: REQ-001 to REQ-013
  - Acceptance: AC-009
  - Depends on: T019
  - Verification: the recorded run
- [ ] T021 Live: someone who has never used this factory follows `docs/factory-interface.md` alone to T020's result. Record every question they had to ask, and fix the page for each
  - Requirements: REQ-013
  - Acceptance: AC-010
  - Depends on: T020
  - Verification: the recorded run

## Requirement Traceability

| Requirement | Tasks | Acceptance | Status |
|---|---|---|---|
| REQ-001 | T001, T002, T003 | AC-001 | open |
| REQ-002 | T004, T005 | AC-001 | open |
| REQ-003 | T001 | AC-001 | open |
| REQ-004 | T007 | AC-002 | open |
| REQ-005 | T008 | AC-002 | open |
| REQ-006 | T009 | AC-003 | open |
| REQ-007 | T010 | AC-004 | open |
| REQ-008 | T011, T012, T013 | AC-005 | open |
| REQ-009 | T007 | AC-006 | open |
| REQ-010 | T014 | AC-007 | open |
| REQ-011 | T015 | AC-008 | open |
| REQ-012 | T016 | none | open |
| REQ-013 | T018, T021 | AC-010 | open |
| AC-009 | T020 | AC-009 | open |
| NFR-002 | T006 | none | open |
