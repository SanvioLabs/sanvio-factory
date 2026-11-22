---
spec: SPEC-004
status: draft
created: 2026-11-21
updated: 2026-11-21
---

# Tasks: SPEC-004

Execution state for this spec. A fresh session resumes from this file's
checkboxes and the Requirement Traceability table. Task IDs run across the whole
spec. Built by hand, never on the loop (the spec's Constraints). `TESTS` below
means:

```
python3 -m unittest tests.test_usage_shape tests.test_usage_scrub tests.test_export tests.test_usage tests.test_agent_hooks tests.test_send_usage tests.test_dashboard_data tests.test_link_files tests.test_changelog
```

## Phase 1: Shape and scrubber

- [x] T001 Add [`scripts/usage_shape.py`](../../../scripts/usage_shape.py): the v2 bundle's and the heartbeat's keys and types, `problems(obj)`, and the table mapping every key to RQ-1 to RQ-6
  - Requirements: REQ-001, REQ-009, REQ-013
  - Acceptance: AC-012
  - Depends on: None
  - Verification: `TESTS`; a test adds a key with no RQ and expects a failure
  - Done 2026-11-21: [`scripts/usage_shape.py`](../../../scripts/usage_shape.py) and `SERVES`; [`tests/test_usage_shape.py`](../../../tests/test_usage_shape.py)
- [x] T002 Add [`scripts/usage_scrub.py`](../../../scripts/usage_scrub.py), importing its patterns from `guard.py` and `loop.py`. Write AC-005's fixture of invented secrets first and watch it fail
  - Requirements: REQ-007
  - Acceptance: AC-005
  - Security: SEC-001
  - Depends on: None
  - Verification: `TESTS`; a timing test of 1,000 scrubs for NFR-004
  - Done 2026-11-21: [`scripts/usage_scrub.py`](../../../scripts/usage_scrub.py), with `SECRET_ENV` moved to `names.py` so the hook needn't import `loop.py`; [`tests/test_usage_scrub.py`](../../../tests/test_usage_scrub.py), under 5 ms a call
- [x] T003 `export.py` writes `v: 2`: `mode`, `node`, `factory`, `loop_config`, `chain_head`, `period`, `bundle_id`, checked against `usage_shape.problems()` before it's written
  - Requirements: REQ-001
  - Acceptance: AC-001
  - Depends on: T001
  - Verification: `TESTS`
  - Done 2026-11-21: `export.bundle()` writes v2 and refuses a bundle off the shape; `Version2` in [`tests/test_export.py`](../../../tests/test_export.py)
- [x] T004 `export.py` reads `export_projects` from `.sanvio/export.json` and includes those projects' runs under their labels, and no others
  - Requirements: REQ-002
  - Acceptance: AC-002
  - Privacy: PRIV-003
  - Depends on: T003
  - Verification: `TESTS`
  - Done 2026-11-21: `config()` and `listed_projects()` in `export.py`; a listed project's runs from `.loop/projects/<folder>/` under its label
- [ ] T005 Phase 1's CHANGELOG entry, and open the pull request
  - Depends on: T001 to T004
  - Verification: the full suite, `python3 -m unittest discover -s tests`

## Phase 2: Detailed capture

- [ ] T006 Add the opt-in file `.sanvio/usage/<user>.detailed` and its `detailed_on` line. `SANVIO_DETAILED_DAYS`, 14 by default, through `names.py`
  - Requirements: REQ-004
  - Acceptance: AC-003
  - Privacy: PRIV-002
  - Depends on: T005
  - Verification: `TESTS` with a fixed clock
- [ ] T007 `usage_log.py` writes a scrubbed line to `<user>.commands.jsonl` for each `PreToolUse` Bash call while the opt-in is live, with `ran`, `refused` or `asked` from the guard's verdict, through `log_chain`, pruned like the usage log
  - Requirements: REQ-005
  - Acceptance: AC-004
  - Security: SEC-001
  - Depends on: T002, T006
  - Verification: `TESTS`
- [ ] T008 No command line from a headless session or one whose `cwd` is inside [`projects/`](../../../projects/)
  - Requirements: REQ-006
  - Acceptance: AC-004
  - Depends on: T007
  - Verification: `TESTS`
- [ ] T009 At session start, an end date in the past removes the opt-in, writes `detailed_expired`, and adds one line to the setup message. A live one adds a line naming its end date
  - Requirements: REQ-008
  - Acceptance: AC-003
  - Privacy: PRIV-002
  - Depends on: T006
  - Verification: `TESTS`
- [ ] T010 The guard asks a person before a change to `.sanvio/export.json` and refuses one from a headless run, as it does `.sanvio/factory-floor/`. Confirm the commands and opt-in files are already read-only under `LOG_NAME`
  - Requirements: SEC-004
  - Depends on: None
  - Verification: `TESTS` in [`tests/test_agent_hooks.py`](../../../tests/test_agent_hooks.py)
- [ ] T011 `export.py --mode detailed` adds the `commands` section from the commands file, and refuses with no live opt-in
  - Requirements: REQ-003
  - Acceptance: AC-003
  - Depends on: T007, T009
  - Verification: `TESTS`
- [ ] T012 Phase 2's CHANGELOG entry, and the pull request
  - Depends on: T006 to T011
  - Verification: the full suite

## Phase 3: Sender

- [ ] T013 `send_usage.py FILE`: check the shape, refuse unknown keys, run the scrubber again and refuse the file if anything changes, then send its exact bytes through the cloud CLI's profile to `incoming/<node>/<user>/<mode>/<bundle_id>.json`
  - Requirements: REQ-009
  - Acceptance: AC-006
  - Security: SEC-002
  - Depends on: T012
  - Verification: `TESTS` with a stand-in CLI first on `PATH`
- [ ] T014 No `.sanvio/export.json`, or no `store` in it: send nothing, open no connection, and say how to configure one
  - Requirements: REQ-010
  - Acceptance: AC-007
  - Depends on: T013
  - Verification: `TESTS` with a socket that fails the test when opened
- [ ] T015 `--auto` builds and sends a general bundle only, and says so when detailed was asked for
  - Requirements: REQ-011
  - Acceptance: AC-008
  - Depends on: T013
  - Verification: `TESTS`
- [ ] T016 `--heartbeat`, per the plan's *Heartbeat*: lock pid, queue, running issue's tokens and budget, unlisted projects under a hashed label, no titles
  - Requirements: REQ-012
  - Acceptance: AC-009
  - Depends on: T013
  - Verification: `TESTS` over a fixture `.loop/` with one live and one dead lock
- [ ] T017 `--opt-in detailed` and `--opt-out`, writing through T006
  - Requirements: REQ-004
  - Depends on: T006, T013
  - Verification: `TESTS`
- [ ] T018 `export_sent` and `export_refused` lines in the usage log, and the dashboard's last send and mode
  - Requirements: OBS-001, OBS-002
  - Depends on: T013
  - Verification: `TESTS`
- [ ] T019 `factory-trends`'s *Sprint run* offers the period's general bundle after the report, shows it, and sends only on a yes. A failed send never stops the report
  - Requirements: REQ-018
  - Acceptance: AC-014
  - Depends on: T013
  - Verification: `TESTS` with a stand-in sender, then a reading of the skill
- [ ] T031 A store with `kind: folder`: copy into its `incoming/<node>/` path after the same checks as T013, creating folders as needed
  - Requirements: REQ-020
  - Acceptance: AC-016
  - Depends on: T013
  - Verification: `TESTS`
- [ ] T020 Phase 3's CHANGELOG entry, and the pull request
  - Depends on: T013 to T019, T031
  - Verification: the full suite

## Phase 4: Reference store

- [ ] T030 Spike: run the DuckDB Grafana plugin's current release locally against a folder and against a test bucket through a CLI profile. Record the version, whether the bucket read worked, and which cloud data source the plan uses
  - Requirements: REQ-022
  - Depends on: T020
  - Verification: the spike's result, recorded here
- [ ] T021 `examples/usage-store/cloud/`: bucket, `incoming/`, `accepted/`, `rejected/`, a 90-day lifecycle, a key only the owner role can use for `detailed/`, and an example `export.json` with invented values
  - Requirements: REQ-013, REQ-014
  - Privacy: PRIV-004, PRIV-005
  - Depends on: T020
  - Verification: `terraform fmt -check` and `terraform validate`, recorded here
- [ ] T022 Sender roles that may only put under their own `incoming/<node>/` and read nothing, with certificate-based workload identity for unattended nodes
  - Requirements: REQ-013, REQ-019
  - Security: SEC-003
  - Depends on: T021
  - Verification: `terraform validate`
- [ ] T023 `validator.py`: imports [`scripts/usage_shape.py`](../../../scripts/usage_shape.py), moves each object to `accepted/` or `rejected/` with its reason, and marks a chain gap. One file, run as the cloud function and as `--folder PATH` locally
  - Requirements: REQ-013, REQ-016, REQ-021
  - Depends on: T021
  - Verification: unit tests beside the function, with stand-in storage
- [ ] T024 Grafana alert rules as provisioning files: a silent node past its window and a run past 80% of its budget, one alert each until it recovers. The contact point from the secret store by name, or an environment variable locally
  - Requirements: REQ-015, REQ-022
  - Security: SEC-005
  - Depends on: T025
  - Verification: part of AC-011 and AC-016
- [ ] T025 `queries/rq-1.sql` to `rq-6.sql`, and the dashboard with a panel per RQ, as a provisioning file
  - Requirements: OBS-003, REQ-022
  - Acceptance: AC-017
  - Depends on: T023, T030
  - Verification: each file run with the DuckDB CLI over a folder of invented bundles, in a test that skips where DuckDB isn't installed
- [ ] T032 `examples/usage-store/local/`: a compose file running Grafana and the plugin at pinned versions on `127.0.0.1`, the folder mounted read-only, and a README going from nothing to the dashboard
  - Requirements: REQ-022, REQ-023
  - Acceptance: AC-016
  - Depends on: T024, T025
  - Verification: AC-016's live run
- [ ] T033 Grafana in `cloud/`: behind the owner's identity provider, with the general and detailed data sources split by role
  - Requirements: REQ-023, REQ-014
  - Depends on: T021, T030
  - Verification: `terraform validate`, then part of AC-010
- [ ] T026 Live runs: AC-016 on one machine, then AC-010, AC-011, AC-015 and AC-017 in a test account, each recorded here with what it showed
  - Acceptance: AC-010, AC-011, AC-015, AC-016, AC-017
  - Depends on: T022 to T025, T032, T033
  - Verification: the live runs
- [ ] T027 Phase 4's CHANGELOG entry, and the pull request
  - Depends on: T021 to T026, T030, T032, T033

## Phase 5: Docs

- [ ] T028 [`reports/usage/README.md`](../../../reports/usage/README.md): the sending flow, and the second paste-ready message for detailed mode. [`steering/data-and-tools.md`](../../../steering/data-and-tools.md): the commands file and the store in the retention table, and deletion on request
  - Requirements: REQ-017
  - Acceptance: AC-013
  - Privacy: PRIV-001, PRIV-004
  - Depends on: T020
  - Verification: a reading, and `TESTS`
- [ ] T029 [`HOW-IT-WORKS.md`](../../../HOW-IT-WORKS.md) and [`README.md`](../../../README.md) agree with what shipped
  - Depends on: T027, T028
  - Verification: a reading, and `TESTS`

## Requirement Traceability

| Requirement | Tasks | Acceptance | Done |
|---|---|---|---|
| REQ-001 | T001, T003 | AC-001 | |
| REQ-002 | T004 | AC-002 | |
| REQ-003 | T011 | AC-003 | |
| REQ-004 | T006, T017 | AC-003 | |
| REQ-005 | T007 | AC-004 | |
| REQ-006 | T008 | AC-004 | |
| REQ-007 | T002 | AC-005 | |
| REQ-008 | T009 | AC-003 | |
| REQ-009 | T001, T013 | AC-006 | |
| REQ-010 | T014 | AC-007 | |
| REQ-011 | T015 | AC-008 | |
| REQ-012 | T016 | AC-009 | |
| REQ-013 | T001, T021, T022, T023 | AC-010 | |
| REQ-014 | T021 | AC-010 | |
| REQ-015 | T024 | AC-011, AC-016 | |
| REQ-016 | T023 | AC-010 | |
| REQ-017 | T028 | AC-013 | |
| REQ-018 | T019 | AC-014 | |
| REQ-019 | T022 | AC-015 | |
| REQ-020 | T031 | AC-016 | |
| REQ-021 | T023 | AC-016 | |
| REQ-022 | T024, T025, T030, T032 | AC-016, AC-017 | |
| REQ-023 | T032, T033 | AC-016, AC-010 | |
