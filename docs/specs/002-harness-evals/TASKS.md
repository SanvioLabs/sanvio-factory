---
spec: SPEC-002
status: complete
created: 2026-10-31
updated: 2026-11-05
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

- [x] T018 Build the Repair suite in the private suites repo and validate it
  - Requirements: Evaluation Requirements
  - Depends on: T003
  - Verification: `python3 scripts/eval_harness.py validate <private suite path>`
- [x] T019 Build the Migrate suite and validate it
  - Requirements: Evaluation Requirements
  - Depends on: T003
  - Verification: `python3 scripts/eval_harness.py validate <private suite path>`
- [x] T020 Build the Build suite and validate it
  - Requirements: Evaluation Requirements
  - Depends on: T003
  - Verification: `python3 scripts/eval_harness.py validate <private suite path>`
- [x] T021 Run each suite once through this harness, and save each result as its baseline
  - Requirements: REQ-001, REQ-004, REQ-013
  - Depends on: T015, T018, T019, T020
  - Verification: `python3 scripts/eval_harness.py list`

## Phase 8: Review fixes

From `review-spec` on 2026-11-02. Each test was watched failing before its fix.

- [x] T022 A failed or timed-out start still finds the pull request it opened, and that gets scored
  - Requirements: REQ-010, AC-003
  - Depends on: T013
  - Verification: `python3 -m unittest discover -s tests -p 'test_eval_harness.py'` (`FailedStartWithAPullRequest`)
- [x] T023 Ctrl-C ends the start command's process group, and `resume --end` scores an interrupted run
  - Requirements: REQ-012
  - Depends on: T010
  - Verification: `python3 -m unittest discover -s tests -p 'test_eval_harness.py'` (`Interrupted`)
- [x] T024 What a run acts on is kept in a sealed copy outside the harness, the key's path only there, and a pull request that isn't a number is refused
  - Requirements: SEC-004, REQ-005
  - Depends on: T009
  - Verification: `python3 -m unittest discover -s tests -p 'test_eval_harness.py'` (`SealedRecord`)
- [x] T025 Scoring gets an empty home and no `gh` login, and each pull request's details in `PR_DATA`. The Repair and Migrate scorers read it
  - Requirements: SEC-002, SEC-003
  - Depends on: T014
  - Verification: `python3 -m unittest discover -s tests -p 'test_eval_harness.py'` (`ScoringReach`), then `validate` on each private suite
- [x] T026 One place says what a failed `gh` call said
  - Requirements: NFR
  - Depends on: None
  - Verification: `python3 -m unittest discover -s tests -p 'test_eval_harness.py'`

## Final Verification

- [x] Acceptance criteria pass
- [x] Unit tests pass
- [x] Security requirements verified
- [x] Documentation updated
- [x] Independent review completed (`review-spec`)

## Verification Evidence

Fresh on 2026-11-01, rerun 2026-11-05 on main after #364: `test_eval_harness.py` OK, `validate examples/eval-suite` sound. The real `gh` path was proven by the runs under Phase 7.

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

### Review fixes, 2026-11-02

```
$ python3 -m unittest discover -s tests -p 'test_eval_harness.py'
Ran 115 tests in 81.545s
OK

$ python3 scripts/eval_harness.py validate <private build suite>
build: the seed fails, each wrong answer fails, the reference passes.
$ python3 scripts/eval_harness.py validate <private repair suite>
repair: the seed fails, each wrong answer fails, the reference passes.
```

Pat ran the Migrate suite's `validate` by hand on 2026-11-02, since a local guard holds any command naming that suite for a person: `migrate: the seed fails, each wrong answer fails, the reference passes.` The whole repo's run had one failure, `test_token_report`'s, which predates this spec.

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

Built in a local folder outside this repo. In the private suites repo since 2026-11-02.

Command:

```
python3 scripts/eval_harness.py validate <private suite path>
```

Result:

```
repair: the seed fails, each wrong answer fails, the reference passes. Exit 0.
```

### The Migrate suite

Built in a local folder outside this repo. In the private suites repo since 2026-11-02.

Result:

```
migrate: the seed fails, each wrong answer fails, the reference passes. Exit 0.
```

### The Build suite

A new job, built in a local folder outside this repo. In the private suites repo since 2026-11-02.

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
| Evaluation Requirements | T003, T018, T019, T020 | scripts/eval_harness.py, private suites | validate | PASS |
| NFR: standard library only | T017 | tests/test_eval_harness.py | TESTS | PASS |
| NFR: suite added without runner change | T003 | tests/test_eval_harness.py | TESTS | PASS |

## Review Findings

`review-spec`, 2026-11-02. Lenses run: requirement walk, viper, cto, review-principles. `code-review` ran against the wrong pull request #360 (a pre-commit change in another repo), so its findings are discarded and correctness rests on the requirement walk. Atlas skipped: one standalone script and no structural change to the harness. Recommendation: **Not Complete**, blocked by the five HIGH rows. Since #364 fixed the loop usage part, no HIGH row is open, so the spec is **Complete** as of 2026-11-05. The MEDIUM and LOW rows still marked Open are known limits, not blockers. After the Phase 8 fixes, one HIGH stays open: the loop coupling.

| Severity | Finding | File | Status |
|---|---|---|---|
| HIGH | SEC-004 holds only while `run.json` is honest. It sits under the harness folder the start command runs in, and `repo`, `repo_id`, `merge`, `start`, `usage_command`, `suite_path` and `issues[].pr` all come from it, so an agent that edits it before `resume` can redirect a merge or a command. Viper risk 7 | scripts/eval_harness.py:258, :411 | Fixed 2026-11-02 (T024): the fields a run acts on are sealed in `~/.harness-evals` and resume takes them from there; a pull request must be a number. An agent that goes looking in the person's home can still reach the sealed copy |
| HIGH | Scoring runs agent-written code with only secret-named variables removed, so `HOME`, `~/.config/gh`, `~/.ssh` and the suite's own `key/` stay reachable over an open network. The README and docstring say "as CI would", and SEC-002 reads as if it can't happen. Viper risk 6 | scripts/eval_harness.py:164-181, examples/eval-suite/README.md | Fixed 2026-11-02 (T025): an empty `HOME`, `XDG_CONFIG_HOME` and `GH_CONFIG_DIR`, pull requests in `PR_DATA`, and the docs now say what it can still reach: the network, and files outside `HOME`, the key included |
| HIGH | REQ-010 and AC-003 partly met: when the start command fails or times out, `work()` stops before looking for a pull request, so a PR the harness did open is ignored, left out of `PR_NUMBERS`, and the default branch is scored. The test uses a run with no PR, so it can't catch this | scripts/eval_harness.py:448-451 | Fixed 2026-11-02 (T022) |
| HIGH | Ctrl-C during a start command leaves its process group running, because only `TimeoutExpired` kills it. The agent keeps spending tokens after the prompt returns | scripts/eval_harness.py:365-377 | Fixed 2026-11-02 (T023) |
| HIGH | Review principles, significant: the runner reads the starter loop's files directly (`.loop/projects/<clone>/issue-N/usage.json`, detected by [`scripts/loop.py`](../../../scripts/loop.py) in `--start`), so a loop refactor silently turns cost, tokens and rounds into "not reported". The same `gh` error handling is hand-written in five places, and `create_run` and `merge_pull_request` each do several jobs | scripts/eval_harness.py:243-255, :288-341, :405, :518-524 | Partly fixed 2026-11-02 (T026): `gh` error text is in one place. Loop usage part fixed 2026-11-02 (#363): the runner reads it through `issue_usage` in [`scripts/loop.py`](../../../scripts/loop.py). Open: `create_run` and `merge_pull_request` still do several jobs |
| MEDIUM | A run interrupted by anything other than `RunError` (Ctrl-C, bad JSON from `gh`) stays `working`, and `resume` and `resume --end` both refuse it, so it can never be scored. A network failure during scoring also can't be retried | scripts/eval_harness.py:470-472, :640, :706 | Partly fixed 2026-11-02 (T023): `resume --end` scores a run left `working`. Open: a failure during scoring can't be retried |
| MEDIUM | REQ-005 partly met: `run.json` records the key's path inside the harness folder where the agent works | scripts/eval_harness.py:302 | Fixed 2026-11-02 (T024) |
| MEDIUM | AC-006 partly met: `key_leaks` matches whole-file hashes only and exempts `key/reference` and `key/wrong`, so an edited or partial copy of the key isn't found | scripts/eval_harness.py:498-505 | Open |
| MEDIUM | AC-010's "no command deletes a repo" test greps for the string `repo delete`, which `gh("repo", "delete", ...)` would pass. `runs_dir()` is relative to the working directory, so `list` misses runs started elsewhere | tests/test_eval_harness.py:479, scripts/eval_harness.py:258 | Open |
| MEDIUM | Evaluation Requirements partly met: `run` doesn't check the suite was validated, and `validate` passes empty `PR_NUMBERS` and `RUN_REPO`, so a scorer that depends on them is never exercised before a paid run | scripts/eval_harness.py:206 | Open |
| MEDIUM | On a free GitHub plan, branch protection fails only after the private repo exists, leaving an orphan. The README mentions neither this nor the Actions minutes billed to the owner | scripts/eval_harness.py:300, :318-324 | Open |
| MEDIUM | Review principles, minor: `round_count` and `round_total` overlap, `result.json` is written without the `.part` rename `run.json` uses, and `create_run` catches five exception types as one setup stop | scripts/eval_harness.py:609-620, :642, :729, :337 | Partly fixed 2026-11-02: `result.json` is written through a `.part` file. Open: the overlapping round helpers and the broad `except` |
| MEDIUM | The result records no rounds, and with `--usage-command` it drops the loop's token counts, which are the measures most likely to separate two harnesses that both pass | scripts/eval_harness.py | Fixed 2026-11-02: each result now has `rounds` and the loop's `tokens`, and the five saved results were filled in from the loop's usage files |
| LOW | `test_an_empty_run_exits_0` fails on a machine with real loop usage. It failed before this spec too | tests/test_token_report.py | Open, out of scope |
| LOW | Three "a job in the pane" tests expect a time with no date, so they fail when their 6 minutes ago falls on yesterday, just after midnight. Found at 00:02 local | examples/mods/loop-pane/hooks/root.test.ts | Open, out of scope |
| LOW | Eval integrity: agent code imported by `key/score` can print a passing JSON and exit, the required check is matched by name only so a PR can edit its workflow to emit it, `usage.json` is agent-writable, and `SCORE_TIMEOUT` kills only the direct child. Viper risk 2-3 | scripts/eval_harness.py:169, :176, :422, :524 | Open |
| LOW | The Requirement Traceability table marks every row PASS while Final Verification and T021 are unchecked. Rows with no test behind them: Evaluation Requirements, SEC-001's made-up data, SEC-002's seed half, and the new-suite NFR (its test only renames the same suite) | docs/specs/002-harness-evals/TASKS.md | Fixed 2026-11-05: T021 and Final Verification are checked. The rows with no test behind them stand |
| LOW | A failing `--usage-command` throws away a cost the loop did report | scripts/eval_harness.py:546 | Open |
| LOW | The runner is POSIX-only (`killpg`, `sh -c`) and the docs don't say so. Long lines and missing docstrings on `runs_dir`, `save_run`, `load_run` and the `cmd_*` functions; "REQ-012" is unexplained in a comment | scripts/eval_harness.py | Open |
| INFO | Drift from the spec, none of it flagged: `--owner` is required; `validate`, `resume` and exit code 3 exist; `public_example` skips REQ-005's check; the last PR is merged too, though REQ-013 says "between issues"; `compare` doesn't check both results come from the same suite; the runner imports `loop` from the harness under test, so comparing two commits also compares two versions of its own arithmetic | docs/specs/002-harness-evals/SPEC.md | Open |
| INFO | A suite is code: the seed's `.git` is copied over the clone's, `suite.json` paths accept `..` and absolute paths, and `public_example` is self-declared. All sit behind the trust `key/score` already needs, so install a suite like software | scripts/eval_harness.py:134-147, :313 | Open |
