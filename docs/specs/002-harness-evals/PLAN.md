---
spec: SPEC-002
status: draft
created: 2026-10-31
updated: 2026-10-31
---

# Implementation Plan: SPEC-002

## Specification

Link: [`SPEC.md`](SPEC.md). Its status when this plan was written: `ready` as of
2026-10-31. If the spec changes after this date, this plan may be stale.

## Repository Analysis

Read for this plan:

- [`scripts/eval_agents.py`](../../../scripts/eval_agents.py): the closest existing tool, a single standard-library script with its usage in the docstring.
- [`scripts/loop.py`](../../../scripts/loop.py): its `argparse` subcommands (from line 2994), `usage_totals()` (line 1007), its state folder (line 1221) and `run --issue` (line 2996).
- [`tests/test_eval_agents.py`](../../../tests/test_eval_agents.py) and [`tests/test_loop.py`](../../../tests/test_loop.py): `unittest`, with fake commands placed first on `PATH` (`test_loop.py`, lines 759 and 779).
- [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml): Python 3.9 and 3.13, `python3 -m unittest discover -s tests`, and `python3 scripts/link_files.py --check`.
- [`tests/test_changelog.py`](../../../tests/test_changelog.py): each changelog entry needs a dated heading and a `**Do:**` line.
- [`scripts/dashboard_data.py`](../../../scripts/dashboard_data.py) (line 349): it reads `.harness/evals/*.json` as reviewer evals.
- [`.gitignore`](../../../.gitignore): `.loop/`, `.harness/` and `projects/*` are all ignored.
- The method plugin's spec templates, for this file's shape. This repo has no `package.json` or `pyproject.toml` at its root, and no linter or type checker runs on [`scripts/`](../../../scripts/).

A private prototype scorer also informed `key/score` below: it scores one checkout and prints tests and traps as JSON.

## Existing Patterns

- **One standard-library script, docstring as the manual:** [`scripts/eval_agents.py`](../../../scripts/eval_agents.py).
- **Saved runs under `.harness/`:** `eval_agents.py --save`. This runner uses `.harness/harness-evals/` rather than `.harness/evals/`, because `dashboard_data.py` reads every JSON file in the latter as a reviewer eval.
- **Fake `gh` and agent on `PATH` in tests, so no model or network is used:** [`tests/test_loop.py`](../../../tests/test_loop.py).
- **Cost as `not reported`, not zero:** `usage_totals()` returns `None` when nothing reported, and the runner reuses it for the starter's loop by importing `loop`. `loop.py` itself doesn't change.

New pattern: a suite's scorer is a program in the suite (`key/score`) rather than a format the runner interprets. Hidden tests differ by language and traps differ by job, and the spec requires adding a suite without changing the runner.

## Architecture Impact

One new script calling `git` and `gh` as subprocesses. Nothing under test imports it. The run is a resumable state machine stored in a run record:

```
validate suite -> confirm -> create repo -> for each issue: start command, find PR, merge or stop -> score -> result
```

### Suite format

```
<suite>/
  suite.json        name, seed path, key path, required_checks, issues in order
  seed/             the repo's starting contents, including its CI workflow
  issues/           one Markdown file per issue, first line is the title
  key/
    score           executable: reads RUN_DIR, BASE_SHA, PR_NUMBERS, RUN_REPO, prints JSON
    reference/      files that overlay the seed to make the right answer
    wrong/<name>/   files that overlay the seed to make a known wrong answer
```

`key/score` prints `{"tests": [{"name", "passed"}], "traps": [{"name", "avoided"}]}`. Output that doesn't parse leaves the run `not scored`, with the reason recorded, rather than counting as zero.

## Files Expected to Change

| File | Change |
|---|---|
| [`README.md`](../../../README.md) | A row for the runner |
| [`AGENTS.md`](../../../AGENTS.md) | A line beside `eval_agents.py` |
| [`CHANGELOG.md`](../../../CHANGELOG.md) | An entry at the top |

## New Files Expected

| File | Purpose |
|---|---|
| [`scripts/eval_harness.py`](../../../scripts/eval_harness.py) | The runner |
| [`tests/test_eval_harness.py`](../../../tests/test_eval_harness.py) | Its tests, using a fake `gh` and a stub start command |
| [`examples/eval-suite/`](../../../examples/eval-suite/) | The tiny public suite, marked `"public_example": true` |

## Data Model Changes

None. A run's files are gitignored:

- `.harness/harness-evals/<run>/run.json`: state, the created repo's name and GitHub id, each issue's PR, and stops
- `.harness/harness-evals/<run>/result.json`: the REQ-007 result

## API / Interface Changes

```
eval_harness.py run <suite> --start "<command>" --owner <org> [--harness PATH] [--clone-into DIR]
                [--merge-in-run-repo] [--usage-command "<command>"] [--timeout MIN] [--yes]
eval_harness.py resume <run> [--end]
eval_harness.py stop <run> "<why>"
eval_harness.py compare <a> <b>
eval_harness.py list
eval_harness.py validate <suite>
```

`--start` may use `{issue}`, `{repo}`, `{clone}` and `{project}`, all values the runner made, shell-quoted.

The spec doesn't name `resume`, `validate`, `--owner`, `--harness`, `--clone-into` or `--timeout`. `resume` is what makes REQ-013's stop recoverable. `validate` is the Evaluation Requirements check. The flags supply values a run can't otherwise know.

## Infrastructure Changes

None identified. Each run creates one private GitHub repo in the given owner.

## Security Considerations

- SEC-001: `gh repo create --private`, confirmed afterwards with `gh repo view --json visibility`, and the run stops if the repo isn't private. Made-up data is the suite author's duty, stated in the format docs and the example.
- SEC-002: issue text goes to `gh issue create --body-file` and is never parsed for instructions or put into a command. Only runner-made values fill `--start` placeholders.
- SEC-003: the runner calls `gh` and doesn't read a token or a credentials file. A test asserts the script holds no `GH_TOKEN`, `GITHUB_TOKEN` or `gh auth token`.
- SEC-004: before each merge, the runner compares the repo's GitHub id from `gh repo view --json id` with the id in the run record, and passes that repo explicitly to `gh pr merge`.

## Observability

None identified. Each step prints one line, and the run record holds the state.

## Evaluation Strategy

The spec's Evaluation Requirements: `validate <suite>` overlays nothing, then each `key/wrong/*`, then `key/reference`, on temporary copies of the seed, and runs `key/score` on each. It passes only when the seed fails, every wrong answer fails, and the reference passes every test and trap. It spends no model tokens and creates no repo.

Graders are deterministic. Baseline: the first saved result for each suite on the harness commit it ran against. No score blocks a release, because a person reads `compare` and decides.

Expected cost is unknown until the first real run of each suite.

Safety cases: the Build and Repair suites carry traps for doing the wrong thing, and the suites stay private.

## Implementation Phases

### Phase 1: Suite format and validation

Covers: REQ-002, REQ-003, REQ-005, AC-002, NFR (suite added without runner change), Evaluation Requirements

Expected changes: suite loading and refusals, the public example, `validate`. Refused before anything starts: a key under the seed (or the reverse), a symlink in the seed reaching the key, a file in the seed identical to a key file, and a key inside the harness or clone folder unless the suite is the public example.

Verification: `python3 -m unittest discover -s tests -p 'test_eval_harness.py'` and `python3 scripts/eval_harness.py validate examples/eval-suite`

### Phase 2: Starting a run

Covers: REQ-004, REQ-012, REQ-014, AC-007, AC-010, SEC-001, SEC-003

Expected changes: confirmation, repo creation, branch protection (exit status checked before parsing, as `gh api` prints errors to stdout), issues, the run record, `list`.

Verification: `python3 -m unittest discover -s tests -p 'test_eval_harness.py'`

### Phase 3: Working the issues

Covers: REQ-001, REQ-010, REQ-011, REQ-013, AC-003, AC-008, AC-009, SEC-002, SEC-004

Expected changes: the start command with a timeout that ends its process group, finding the issue's pull request, merging or stopping, `stop`, `resume`.

Finding the pull request: the one open pull request created since this issue's start. None or several is recorded as a stop, since a guess could merge the wrong thing.

Verification: `python3 -m unittest discover -s tests -p 'test_eval_harness.py'`

### Phase 4: Scoring

Covers: REQ-006, REQ-007, REQ-008, REQ-015, AC-001, AC-004, AC-006

Expected changes: a fresh clone outside the harness at the default branch, or at the last open pull request's head when a run ended unmerged. A leak check first compares the blob ids of key files (`git hash-object`) with `git rev-list --objects --all`. Then `key/score`, cost, the result file and the scorecard.

Cost, in order: `--usage-command`, then the starter's own `.loop/projects/<clone>/issue-N/usage.json` when the start command runs that harness's [`scripts/loop.py`](../../../scripts/loop.py), then `not reported`. Output from `--usage-command` that isn't a number reads `not reported`.

Verification: `python3 -m unittest discover -s tests -p 'test_eval_harness.py'`

### Phase 5: Compare

Covers: REQ-009, AC-005

Expected changes: `compare`, matching tests and traps by name, and naming each one that changed, was added or disappeared.

Verification: `python3 -m unittest discover -s tests -p 'test_eval_harness.py'`

### Phase 6: Documentation

Covers: the spec's Affected Areas, NFR (standard library only)

Expected changes: README, AGENTS and CHANGELOG, plus a test that the script imports only the standard library and `loop`.

Verification: `python3 -m unittest discover -s tests` and `python3 scripts/link_files.py --check`

### Phase 7: The three private suites

Covers: Goal 2, Evaluation Requirements

Expected changes: Build, Repair and Migrate, in a private repo, passed in by path. Nothing from them enters this repo. Each is validated, then run once through this harness, which spends model tokens and is started by a person.

Verification: `python3 scripts/eval_harness.py validate <private suite path>`

## Testing Strategy

Unit and integration tests with `unittest`, the repo's runner: a fake `gh` on `PATH` backed by a local bare git repo, a stub start command, and a stub `key/score`. No test uses a model or the network. Tests run on Python 3.9 and 3.13 in CI. The script's real `gh` calls are only proven by Phase 7's first run.

## Migration Strategy

None.

## Rollback Strategy

Delete the script, its test, the example and the doc rows. Created repos stay until a person deletes them.

## Risks

- **An agent on the same machine might read the key.** REQ-005 keeps it out of the seed and the working folder, but an agent with wide file access could still reach another path. The leak check only catches what gets committed. Keep private suites outside any folder the agent is allowed to read.
- **Scoring runs agent-written code on this machine.** `key/score` usually runs the result's tests, as any CI would, and the repo is an agent's output. Suites use made-up data, and this should be stated in the docs.
- **Branch protection on private repos needs a paid GitHub plan.** On a free plan REQ-004 can't be met, so the run stops with that reason rather than continuing unprotected. The repo it already created stays, per REQ-014.
- **Fake `gh` can differ from real `gh`.** Phase 7's first run is the real check.

## Open Implementation Questions

None blocking.
