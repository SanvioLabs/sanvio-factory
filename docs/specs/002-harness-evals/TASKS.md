---
spec: SPEC-002
status: in-progress
created: 2026-10-31
updated: 2026-11-01
---

# Tasks: SPEC-002

Execution state for this spec. A fresh session resumes from this file's
checkboxes and the Requirement Traceability table. Task IDs run across the whole
spec. `TESTS` below means:

```
python3 -m unittest discover -s tests -p 'test_eval_harness.py'
```

## Phase 1: Suite format and validation

- [x] T001 Load `suite.json` from any path and refuse a bad suite before anything starts: a key under the seed or the reverse, a symlink reaching the key, a key file's copy in the seed, or a key inside the harness or clone folder unless `public_example`
  - Requirements: REQ-002, REQ-003, REQ-005
  - Acceptance: AC-002
  - Depends on: None
  - Verification: `TESTS`
- [x] T002 Write [`examples/eval-suite/`](../../../examples/eval-suite/), with one tiny issue, one reference, one wrong answer and a `key/score`, using standard-library Python and made-up data
  - Requirements: REQ-002
  - Security: SEC-001
  - Depends on: T001
  - Verification: `python3 -m json.tool examples/eval-suite/suite.json`
- [x] T003 Add `validate <suite>`: the seed fails, each wrong answer fails, the reference passes, with no repo and no tokens. A test adds a second suite with no runner change
  - Requirements: Evaluation Requirements, NFR (suite added without runner change)
  - Depends on: T001, T002
  - Verification: `python3 scripts/eval_harness.py validate examples/eval-suite`

## Phase 2: Starting a run

- [x] T004 Require `--yes` or a typed `yes` before creating anything, stating that a run spends model tokens. With neither and no terminal, exit having created nothing
  - Requirements: REQ-012
  - Acceptance: AC-007
  - Depends on: T001
  - Verification: `TESTS`
- [x] T005 Create the run repo from the seed: private and confirmed so, branch protection with the suite's required checks, then the issues in order from `--body-file`. A protection failure stops the run and says why
  - Requirements: REQ-004
  - Security: SEC-001, SEC-002, SEC-003
  - Depends on: T004
  - Verification: `TESTS`
- [x] T006 Write the run record with the repo's name and GitHub id, and add `list`. No code path deletes a repo, and a test asserts `gh repo delete` is absent
  - Requirements: REQ-014
  - Acceptance: AC-010
  - Security: SEC-004
  - Depends on: T005
  - Verification: `TESTS`

## Phase 3: Working the issues

- [x] T007 Run `--start` from the harness folder for each issue, filling only runner-made values, shell-quoted. A non-zero exit or a timeout records a stop, and the run goes on to scoring
  - Requirements: REQ-001, REQ-010
  - Acceptance: AC-003
  - Security: SEC-002
  - Depends on: T006
  - Verification: `TESTS`
- [x] T008 Find the pull request the issue produced. None or several records a stop
  - Requirements: REQ-010, REQ-013
  - Depends on: T007
  - Verification: `TESTS`
- [x] T009 With `--merge-in-run-repo`, check the repo's GitHub id against the run record, wait for required CI, then merge. Refuse on a different repo or on CI that hasn't passed
  - Requirements: REQ-013
  - Acceptance: AC-008
  - Security: SEC-004
  - Depends on: T008
  - Verification: `TESTS`
- [x] T010 Without the flag, stop at the merge, save the state and say which pull request it's waiting on. Add `resume <run>`, which continues once it's merged, and `resume <run> --end`, which scores what exists
  - Requirements: REQ-013
  - Acceptance: AC-009
  - Depends on: T008
  - Verification: `TESTS`
- [x] T011 Add `stop <run> "<why>"`, and count runner-recorded stops and a person's together
  - Requirements: REQ-011
  - Depends on: T006
  - Verification: `TESTS`

## Phase 4: Scoring

- [x] T012 Take a fresh clone outside the harness, check its whole history for key files by blob id, and record any found
  - Requirements: REQ-005
  - Acceptance: AC-006
  - Depends on: T009, T010
  - Verification: `TESTS`
- [x] T013 Run `key/score` on the clone and read tests and traps. Output that doesn't parse reads `not scored`, with the reason
  - Requirements: REQ-006
  - Depends on: T012
  - Verification: `TESTS`
- [x] T014 Read cost from `--usage-command`, then the starter's own usage, then `not reported`. Never zero
  - Requirements: REQ-008, REQ-015
  - Acceptance: AC-004
  - Depends on: T007
  - Verification: `TESTS`
- [x] T015 Write `result.json` and print the scorecard, then prove the whole run on the public suite with a stub start command
  - Requirements: REQ-007
  - Acceptance: AC-001
  - Depends on: T013, T014
  - Verification: `TESTS`

## Phase 5: Compare

- [x] T016 Add `compare <a> <b>`: side by side, naming each test or trap that changed, was added or disappeared, and saying so when nothing changed
  - Requirements: REQ-009
  - Acceptance: AC-005
  - Depends on: T015
  - Verification: `TESTS`

## Phase 6: Documentation

- [x] T017 Add the README row, the AGENTS line, the CHANGELOG entry and the suite format's docs. Add the tests for standard-library imports and for no credential reads
  - Requirements: NFR (standard library only)
  - Security: SEC-003
  - Depends on: T016
  - Verification: `python3 -m unittest discover -s tests` and `python3 scripts/link_files.py --check`

## Phase 7: The three private suites

Nothing from these tasks enters this repo. Each run spends model tokens, so a person starts it.

- [ ] T018 Build the Repair suite in the private suites repo and validate it
  - Requirements: Evaluation Requirements
  - Depends on: T003
  - Verification: `python3 scripts/eval_harness.py validate <private suite path>`
- [ ] T019 Build the Migrate suite and validate it
  - Requirements: Evaluation Requirements
  - Depends on: T003
  - Verification: `python3 scripts/eval_harness.py validate <private suite path>`
- [ ] T020 Build the Build suite and validate it
  - Requirements: Evaluation Requirements
  - Depends on: T003
  - Verification: `python3 scripts/eval_harness.py validate <private suite path>`
- [ ] T021 Run each suite once through this harness, and save each result as its baseline
  - Requirements: REQ-001, REQ-004, REQ-013
  - Depends on: T015, T018, T019, T020
  - Verification: `python3 scripts/eval_harness.py list`

## Final Verification

- [ ] Acceptance criteria pass
- [x] Unit tests pass
- [ ] Security requirements verified
- [ ] Documentation updated
- [ ] Independent review completed (`review-spec`)

## Verification Evidence

Fresh on 2026-11-01. `IN PROGRESS` rows also need Phase 7's real run, since these tests use a fake `gh`.

### The runner's tests

Command:

```
python3 -m unittest discover -s tests -p 'test_eval_harness.py'
uv run --no-project --python 3.13 python -m unittest discover -s tests -p 'test_eval_harness.py'
```

Result:

```
OK on Python 3.9.6 and on 3.13
```

### The public suite

Command:

```
python3 scripts/eval_harness.py validate examples/eval-suite
```

Result:

```
tiny-example: the seed fails, each wrong answer fails, the reference passes. Exit 0.
```

### Whole repo

Command:

```
python3 -m unittest discover -s tests
python3 scripts/link_files.py --check
```

Result:

```
Link check: 0 file names to link.
Tests: FAILED (failures=2), neither in the new code. See Review Findings.
```

### First real run, on the tiny suite

Through a starter copy whose loop runs on local Ollama models, with real `gh` and `--merge-in-run-repo`.

Result:

```
Created the private repo, protected main, filed the issue. The loop planned, built and reviewed, opened
pull request 2, required CI passed, and the runner merged it. Scored 3/3 tests, 0 stops, 4.0 min.
The trap scored 0/1 because it counted any edit to the seed's test file, so a model that added a test
fell in it. The trap is fixed, a weakened-test wrong answer added, validate passes, and the result rescored 1/1.
The first attempt found nothing ready: a new label takes seconds to show in GitHub's issue list. The
example's start command now waits for it. That attempt's repo is kept, as every run repo is.
```

### The Repair suite

Built in a local folder outside this repo. T018 stays open until it's in the private suites repo.

Command:

```
python3 scripts/eval_harness.py validate <private suite path>
```

Result:

```
repair: the seed fails, each wrong answer fails, the reference passes. Exit 0.
```

### The Migrate suite

Built in a local folder outside this repo. T019 stays open until it's in the private suites repo.

Result:

```
migrate: the seed fails, each wrong answer fails, the reference passes. Exit 0.
```

### The Build suite

A new job, built in a local folder outside this repo. T020 stays open until it's in the private suites repo.

Result:

```
build: the seed fails, each wrong answer fails, the reference passes. Exit 0.
```

### Repair and Migrate on local models

Both through the Ollama starter copy, with real `gh` and `--merge-in-run-repo`. A first look at difficulty, not a baseline.

```
repair:  11/12 tests, 6/6 traps, 0 stops, 14.2 min.
migrate: 14/14 tests, 4/4 traps, 0 stops, 51.8 min, three pull requests merged in order.
build:   30/30 tests, 5/5 traps, 0 stops, 41.1 min, issue 1 in 4 rounds and issue 2 in 2.
```

Two of three suites scored full marks on local models, so pass and fail alone may not separate harnesses.
Rounds and tokens would, and the result doesn't record either yet: with `--usage-command`, tokens read
`not reported` even though the loop logged them.

The Repair run first reported a key leak that wasn't one: an answer file matched what the model wrote.
Answer files are now left out of the leak check, and the result was rescored.

### Second runs, same models, 2026-11-02

```
repair: 11/12, 6/6, 1 round, 273k tokens  ->  5/12, 4/6, 2 rounds, 378k tokens. The second run fixed the
        wrong thing, and the suite's tests and traps caught it.
build:  30/30, 5/5, 6 rounds, 2.0M tokens  ->  30/30, 5/5, 5 rounds, 1.3M tokens.
        A run in between hit a GitHub error on merging and ended after issue 1. It isn't a sample.
migrate: not rerun. A command guard held it for confirmation and got no answer.
```

One run per suite can't tell a harness change from noise: Repair swung from nearly full marks to under half.
Merges now get three tries, since GitHub failed one it would have accepted.

### Three runs each, same models, 2026-11-02

Each suite's range over three valid runs on the Ollama starter copy:

```
repair:  tests 5-11/12, traps 4-6/6, rounds 1-2, tokens 252k-378k, 11-27 min. 2 of 3 runs at 11/12.
build:   tests 30/30, traps 5/5, rounds 5-6, tokens 1.3M-2.0M, 32-41 min.
migrate: tests 14/14, traps 4/4, rounds 3-5, tokens 0.8M-1.8M, 21-52 min.
```

The Build run that GitHub cut short isn't counted. Pass and fail separate Repair runs, while rounds and
tokens are all that move on Build and Migrate. Three setup failures in a row (GitHub errors on repo create
and branch protection) left one repo with no protection, which `list` shows as setup stopped.

### How the tests were proven

Phases 1 and 2 were watched failing first. Phases 3 to 5 were written with their code, so their failure was never watched. To make up for that, 21 deliberate faults were put into the runner, one at a time, and the tests caught all 21. One of them hung instead of failing, so that test was rewritten, and it now fails cleanly on the same fault.

## Requirement Traceability

| Requirement | Task | Implementation | Verification | Status |
|---|---|---|---|---|
| REQ-001 | T007, T021 | scripts/eval_harness.py | TESTS, first real run | PASS |
| REQ-002 | T001, T002 | scripts/eval_harness.py, examples/eval-suite/ | TESTS | PASS |
| REQ-003 | T001 | scripts/eval_harness.py | TESTS | PASS |
| REQ-004 | T005, T021 | scripts/eval_harness.py | TESTS, first real run | PASS |
| REQ-005 | T001, T012 | scripts/eval_harness.py | TESTS | PASS |
| REQ-006 | T013 | scripts/eval_harness.py | TESTS | PASS |
| REQ-007 | T015 | scripts/eval_harness.py | TESTS | PASS |
| REQ-008 | T014 | scripts/eval_harness.py | TESTS | PASS |
| REQ-009 | T016 | scripts/eval_harness.py | TESTS | PASS |
| REQ-010 | T007, T008 | scripts/eval_harness.py | TESTS | PASS |
| REQ-011 | T011 | scripts/eval_harness.py | TESTS | PASS |
| REQ-012 | T004 | scripts/eval_harness.py | TESTS | PASS |
| REQ-013 | T008, T009, T010, T021 | scripts/eval_harness.py | TESTS, first real run | PASS |
| REQ-014 | T006 | scripts/eval_harness.py | TESTS | PASS |
| REQ-015 | T014 | scripts/eval_harness.py | TESTS | PASS |
| AC-001 | T015 | tests/test_eval_harness.py | TESTS | PASS |
| AC-002 | T001 | tests/test_eval_harness.py | TESTS | PASS |
| AC-003 | T007 | tests/test_eval_harness.py | TESTS | PASS |
| AC-004 | T014 | tests/test_eval_harness.py | TESTS | PASS |
| AC-005 | T016 | tests/test_eval_harness.py | TESTS | PASS |
| AC-006 | T012 | tests/test_eval_harness.py | TESTS | PASS |
| AC-007 | T004 | tests/test_eval_harness.py | TESTS | PASS |
| AC-008 | T009 | tests/test_eval_harness.py | TESTS | PASS |
| AC-009 | T010 | tests/test_eval_harness.py | TESTS | PASS |
| AC-010 | T006 | tests/test_eval_harness.py | TESTS | PASS |
| SEC-001 | T002, T005 | scripts/eval_harness.py, examples/eval-suite/ | TESTS | PASS |
| SEC-002 | T005, T007 | scripts/eval_harness.py | TESTS | PASS |
| SEC-003 | T005, T017 | scripts/eval_harness.py | TESTS | PASS |
| SEC-004 | T006, T009 | scripts/eval_harness.py | TESTS | PASS |
| Evaluation Requirements | T003, T018, T019, T020 | scripts/eval_harness.py, private suites | validate | IN PROGRESS |
| NFR: standard library only | T017 | tests/test_eval_harness.py | TESTS | PASS |
| NFR: suite added without runner change | T003 | tests/test_eval_harness.py | TESTS | PASS |

## Review Findings

| Severity | Finding | File | Status |
|---|---|---|---|
| MEDIUM | The result records no rounds, and with `--usage-command` it drops the loop's token counts, which are the measures most likely to separate two harnesses that both pass | scripts/eval_harness.py | Fixed 2026-11-02: each result now has `rounds` and the loop's `tokens`, and the five saved results were filled in from the loop's usage files |
| LOW | `test_an_empty_run_exits_0` fails on a machine with real loop usage. It failed before this spec too | tests/test_token_report.py | Open, out of scope |
| LOW | Three "a job in the pane" tests expect a time with no date, so they fail when their 6 minutes ago falls on yesterday, just after midnight. Found at 00:02 local | examples/mods/loop-pane/hooks/root.test.ts | Open, out of scope |
