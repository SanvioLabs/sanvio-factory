---
spec: SPEC-004
status: complete
created: 2026-11-21
updated: 2026-11-22
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
- [x] T005 Phase 1's CHANGELOG entry, and open the pull request
  - Depends on: T001 to T004
  - Verification: the full suite, `python3 -m unittest discover -s tests`

  - Done 2026-11-21: the *Usage bundle v2* entry, draft PR #704
## Phase 2: Detailed capture

- [x] T006 Add the opt-in file `.sanvio/usage/<user>.detailed` and its `detailed_on` line. `SANVIO_DETAILED_DAYS`, 14 by default, through `names.py`
  - Requirements: REQ-004
  - Acceptance: AC-003
  - Privacy: PRIV-002
  - Depends on: T005
  - Verification: `TESTS` with a fixed clock
  - Done 2026-11-21: `opt_in()`, `detailed_path()` and `detailed_until()` in `usage_log.py`, `names.detailed_days()`; `Detailed` in [`tests/test_usage.py`](../../../tests/test_usage.py)
- [x] T007 `usage_log.py` writes a scrubbed line to `<user>.commands.jsonl` for each `PreToolUse` Bash call while the opt-in is live, with `ran`, `refused` or `asked` from the guard's verdict, through `log_chain`, pruned like the usage log
  - Requirements: REQ-005
  - Acceptance: AC-004
  - Security: SEC-001
  - Depends on: T002, T006
  - Verification: `TESTS`
  - Done 2026-11-21: `command_record()` and the Bash branch of `main()`; the guard is asked once per call; `prune()` covers the commands file
- [x] T008 No command line from a headless session or one whose `cwd` is inside [`projects/`](../../../projects/)
  - Requirements: REQ-006
  - Acceptance: AC-004
  - Depends on: T007
  - Verification: `TESTS`
  - Done 2026-11-21: `inside_projects()`, and `names.headless()` in `command_record()`
- [x] T009 At session start, an end date in the past removes the opt-in, writes `detailed_expired`, and adds one line to the setup message. A live one adds a line naming its end date
  - Requirements: REQ-008
  - Acceptance: AC-003
  - Privacy: PRIV-002
  - Depends on: T006
  - Verification: `TESTS`
  - Done 2026-11-21: `usage_log.expire()`, called from `session_start.detailed_notes()`, which says it once; `report()` takes notes
- [x] T010 The guard asks a person before a change to `.sanvio/export.json` and refuses one from a headless run, as it does `.sanvio/factory-floor/`. Confirm the commands and opt-in files are already read-only under `LOG_NAME`
  - Requirements: SEC-004
  - Depends on: None
  - Verification: `TESTS` in [`tests/test_agent_hooks.py`](../../../tests/test_agent_hooks.py)
  - Done 2026-11-21: `EXPORT_FILE`, `OPT_IN` and `persons_verdict()` in `guard.py`; `TheUsageSettings` in [`tests/test_agent_hooks.py`](../../../tests/test_agent_hooks.py). The opt-in and commands files were already under `LOG_NAME`
- [x] T011 `export.py --mode detailed` adds the `commands` section from the commands file, and refuses with no live opt-in
  - Requirements: REQ-003
  - Acceptance: AC-003
  - Depends on: T007, T009
  - Verification: `TESTS`
  - Done 2026-11-21: `bundle(..., mode)` and `--mode` in `export.py`; `DetailedBundle` in [`tests/test_export.py`](../../../tests/test_export.py)
- [x] T012 Phase 2's CHANGELOG entry, and the pull request
  - Depends on: T006 to T011
  - Verification: the full suite

## Phase 3: Sender

  - Done 2026-11-21: the *Detailed mode for the usage bundle* entry, plus the README's *Detailed mode* section and its paste-ready message (part of T028) and the retention row
- [x] T013 `send_usage.py FILE`: check the shape, refuse unknown keys, run the scrubber again and refuse the file if anything changes, then send its exact bytes through the cloud CLI's profile to `incoming/<node>/<user>/<mode>/<bundle_id>.json`
  - Requirements: REQ-009
  - Acceptance: AC-006
  - Security: SEC-002
  - Depends on: T012
  - Verification: `TESTS` with a stand-in CLI first on `PATH`
  - Done 2026-11-21: `send_file()`, `check()`, `key_for()` and `deliver()` in `send_usage.py`; `Sending` in [`tests/test_send_usage.py`](../../../tests/test_send_usage.py), with a stand-in `aws` on `PATH`
- [x] T014 No `.sanvio/export.json`, or no `store` in it: send nothing, open no connection, and say how to configure one
  - Requirements: REQ-010
  - Acceptance: AC-007
  - Depends on: T013
  - Verification: `TESTS` with a socket that fails the test when opened
  - Done 2026-11-21: `store_of()`; a test that fails on any socket or process
- [x] T015 `--auto` builds and sends a general bundle only, and says so when detailed was asked for
  - Requirements: REQ-011
  - Acceptance: AC-008
  - Depends on: T013
  - Verification: `TESTS`
  - Done 2026-11-21: `send_auto()`; `export.bundle(..., last=)` so each day's bundle covers that day only
- [x] T016 `--heartbeat`, per the plan's *Heartbeat*: lock pid, queue, running issue's tokens and budget, unlisted projects under a hashed label, no titles
  - Requirements: REQ-012
  - Acceptance: AC-009
  - Depends on: T013
  - Verification: `TESTS` over a fixture `.loop/` with one live and one dead lock
  - Done 2026-11-21: `heartbeat()` and `beat()`; `Heartbeat` in [`tests/test_send_usage.py`](../../../tests/test_send_usage.py)
- [x] T017 `--opt-in detailed` and `--opt-out`, writing through T006
  - Requirements: REQ-004
  - Depends on: T006, T013
  - Verification: `TESTS`
  - Done 2026-11-21: done early, in phase 2: `scripts/send_usage.py --opt-in detailed` and `--opt-out`; [`tests/test_send_usage.py`](../../../tests/test_send_usage.py)
- [x] T018 `export_sent` and `export_refused` lines in the usage log, and the dashboard's last send and mode
  - Requirements: OBS-001, OBS-002
  - Depends on: T013
  - Verification: `TESTS`
  - Done 2026-11-21: `export_sent` and `export_refused` lines, `.sanvio/usage/last-send`, `last_send()` in `dashboard_data.py`, and the factory-dashboard mod's line (0.10.0)
- [x] T019 `factory-trends`'s *Sprint run* offers the period's general bundle after the report, shows it, and sends only on a yes. A failed send never stops the report
  - Requirements: REQ-018
  - Acceptance: AC-014
  - Depends on: T013
  - Verification: `TESTS` with a stand-in sender, then a reading of the skill
  - Done 2026-11-21: step 8 of the sprint run; `FactoryTrendsSend` in [`tests/test_skills.py`](../../../tests/test_skills.py)
- [x] T031 A store with `kind: folder`: copy into its `incoming/<node>/` path after the same checks as T013, creating folders as needed
  - Requirements: REQ-020
  - Acceptance: AC-016
  - Depends on: T013
  - Verification: `TESTS`
  - Done 2026-11-21: `deliver()` writes a folder store's `incoming/` path through a `.part` file
- [x] T020 Phase 3's CHANGELOG entry, and the pull request
  - Depends on: T013 to T019, T031
  - Verification: the full suite

## Phase 4: Reference store

  - Done 2026-11-21: the *Sending the usage bundle* entry, and the README's *Sending it* section (part of T028)
- [x] T030 Spike: run the DuckDB Grafana plugin's current release locally against a folder and against a test bucket through a CLI profile. Record the version, whether the bucket read worked, and which cloud data source the plan uses
  - Requirements: REQ-022
  - Depends on: T020
  - Verification: the spike's result, recorded here
  - Done 2026-11-21, local half: Grafana OSS 13.0.2 with motherduck-duckdb-datasource 0.4.6 (unsigned, allowed by name; carries DuckDB 1.5.6) reads a folder store through `read_json`, and all six RQ panels returned rows through Grafana's query API. Two findings went into the Dockerfile: the plugin's backend is built against glibc and won't start on the default Alpine image, so the image is the `-ubuntu` one; and `/var/lib/grafana` is a volume, so the plugin lives in `/opt/grafana-plugins`. The plugin's query `format` is a number (1, a table), not a string. The cloud data source is the same plugin over `s3://` with DuckDB's `httpfs` and `aws` extensions and a `credential_chain` secret, set by `USAGE_INIT`. **Bucket half open:** it needs a test account, which isn't named in local config yet
  - Bucket half: **Ruled by the owner 2026-11-21: the cloud live runs happen at the first real cloud deployment, against that setup; the spec closes on the local run.** [`examples/usage-store/cloud/README.md`](../../../examples/usage-store/cloud/README.md) lists the checks to run then
- [x] T021 [`examples/usage-store/cloud/`](../../../examples/usage-store/cloud/): bucket, `incoming/`, `accepted/`, `rejected/`, a 90-day lifecycle, a key only the owner role can use for `detailed/`, and an example `export.json` with invented values
  - Requirements: REQ-013, REQ-014
  - Privacy: PRIV-004, PRIV-005
  - Depends on: T020
  - Verification: `terraform fmt -check` and `terraform validate`, recorded here
  - Done 2026-11-21: [`examples/usage-store/cloud/main.tf`](../../../examples/usage-store/cloud/main.tf), with [`export.example.json`](../../../examples/usage-store/cloud/export.example.json). The bucket policy refuses a detailed put without the detailed key, so `detailed_key` is the key's ARN. `terraform fmt -check -recursive` and `terraform validate` (offline, `-backend=false`) pass
- [x] T022 Sender roles that may only put under their own `incoming/<node>/` and read nothing, with certificate-based workload identity for unattended nodes
  - Requirements: REQ-013, REQ-019
  - Security: SEC-003
  - Depends on: T021
  - Verification: `terraform validate`
  - Done 2026-11-21: nodes through an IAM Roles Anywhere trust anchor, each limited to `incoming/<its certificate's CN>/`, general and heartbeats only; people through a role limited to `incoming/<usage_node session tag>/`. Neither may read. `terraform validate` passes
- [x] T023 `validator.py`: imports [`scripts/usage_shape.py`](../../../scripts/usage_shape.py), moves each object to `accepted/` or `rejected/` with its reason, and marks a chain gap. One file, run as the cloud function and as `--folder PATH` locally
  - Requirements: REQ-013, REQ-016, REQ-021
  - Depends on: T021
  - Verification: unit tests beside the function, with stand-in storage
  - Done 2026-11-21: [`examples/usage-store/validator.py`](../../../examples/usage-store/validator.py), tested in [`tests/test_usage_store.py`](../../../tests/test_usage_store.py) over a folder store
- [x] T024 Grafana alert rules as provisioning files: a silent node past its window and a run past 80% of its budget, one alert each until it recovers. The contact point from the secret store by name, or an environment variable locally
  - Requirements: REQ-015, REQ-022
  - Security: SEC-005
  - Depends on: T025
  - Verification: part of AC-011 and AC-016
  - Done 2026-11-21: written by [`render.py`](../../../examples/usage-store/render.py) from `alert-*.sql`, evaluated every minute, one notification per node or run (`group_by: ['...']`), not repeated while firing (`repeat_interval: 8760h`). Seen firing in AC-016's live run
- [x] T025 `queries/rq-1.sql` to `rq-6.sql`, and the dashboard with a panel per RQ, as a provisioning file
  - Requirements: OBS-003, REQ-022
  - Acceptance: AC-017
  - Depends on: T023, T030
  - Verification: each file run with the DuckDB CLI over a folder of invented bundles, in a test that skips where DuckDB isn't installed
  - Done 2026-11-21: `views.sql`, `views-detailed.sql`, `rq-1.sql` to `rq-6.sql`, and two dashboards (RQ-6 on the owner's), rendered from the SQL. The tests run each over a folder of invented bundles with DuckDB 1.5.6, and skip without it
- [x] T032 [`examples/usage-store/local/`](../../../examples/usage-store/local/): a compose file running Grafana and the plugin at pinned versions on `127.0.0.1`, the folder mounted read-only, and a README going from nothing to the dashboard
  - Requirements: REQ-022, REQ-023
  - Acceptance: AC-016
  - Depends on: T024, T025
  - Verification: AC-016's live run
  - Done 2026-11-21: [`local/compose.yaml`](../../../examples/usage-store/local/compose.yaml) and [`local/README.md`](../../../examples/usage-store/local/README.md)
- [x] T033 Grafana in `cloud/`: behind the owner's identity provider, with the general and detailed data sources split by role
  - Requirements: REQ-023, REQ-014
  - Depends on: T021, T030
  - Verification: `terraform validate`, then part of AC-010
  - Done 2026-11-21, with one change from the task's wording: the cloud Grafana has the general data source only. OSS Grafana can't limit a data source to a role, so the team's Grafana role gets no access to `detailed/` or its key, and the owner reads detailed bundles from a copy of `accepted/` in the local Grafana, which has the detailed data source. REQ-023's "only the owner's role" holds through the key. `terraform validate` passes. **Ruled by the owner 2026-11-21: keep this design**
- [x] T026 Live runs: AC-016 on one machine, then AC-010, AC-011, AC-015 and AC-017 in a test account, each recorded here with what it showed
  - Acceptance: AC-010, AC-011, AC-015, AC-016, AC-017
  - Depends on: T022 to T025, T032, T033
  - Verification: the live runs
  - AC-016, 2026-11-21, on one machine with invented data: `send_usage.py --auto` and `--heartbeat` wrote two general bundles and a heartbeat into a folder, a hand-written heartbeat two hours old stood in for a node that stopped, and a detailed bundle went in through `send_usage.py FILE`. `validator.py` moved all to `accepted/`. `docker compose -f local/compose.yaml up --build` started Grafana 13.0.2, published on `127.0.0.1:3000` only (`docker compose port`); RQ-1 to RQ-6 each returned rows, running the panels' own queries from the dashboards Grafana provisioned; the silent-node rule fired for the stale node and not the fresh one, the budget rule fired for the run at 90%, and the webhook received one notification for each and no repeats while they stayed firing. Then the bench node's heartbeats stopped (last at 23:01:37 UTC) and its silent-node alert reached the webhook at 23:32, inside the 30-minute window plus one evaluation. A recreated container sends firing alerts once more, since Grafana's alert state lives in its own database. **AC-010, AC-011, AC-015 and AC-017's bucket half are open:** they need a test account
  - AC-010, AC-011, AC-015, AC-017: **Ruled by the owner 2026-11-21: the cloud live runs happen at the first real cloud deployment, against that setup; the spec closes on the local run.** [`examples/usage-store/cloud/README.md`](../../../examples/usage-store/cloud/README.md) lists the checks to run then
  - Cloud runs, 2026-11-26, at the first real deployment, with a test node signed in by certificate and invented bundles. The first attempt found that the cloud Grafana had never read its bucket (F23), so checks 3's Grafana half, 4, 6 and 7 ran after that fix.
    - **AC-010 (check 1): pass.** The node's bundle was accepted. As the node, `get-object` on it, listing the bucket, `put-object` under another node's `incoming/` and `put-object` straight into `accepted/` were all refused. The person half did not run: that deployment configures no person role.
    - **AC-011 (check 2): pass.** A bundle with a key the shape doesn't name went to `rejected/` with `surprise: not a key this shape allows`. A resend with the same `chain_head` and inflated counts got a mark: `the usage log changed without a new line: same chain_head, different counts`.
    - **AC-017 (check 3): pass.** The owner decrypted an accepted detailed bundle. The node can't use the detailed key at all. A general bundle put under the detailed key was refused by the bucket policy, even for the owner. In the cloud Grafana, reading the detailed bundle by its exact key was refused by S3, and a glob of the detailed prefix listed nothing. The IAM policy simulator agrees: Grafana's task role gets an implicit deny on the detailed object and on `kms:Decrypt`, and the key policy's explicit deny covers everyone but the owner and the validator.
    - **AC-015 (check 4): pass on the rules, with one finding (F24).**
      - A healthy heartbeat resolved all three alerts, one notification each.
      - A heartbeat with a stopped loop and a run at 90% brought one loop-stopped notification and one budget notification about a minute later. Neither repeated over the next two heartbeats.
      - With heartbeats stopped (last at 21:34:32 UTC), the silent-node alert fired at 22:05:17, 30 minutes 45 seconds later.
      - It was sent twice, 20 seconds apart: a restart of Grafana's service at 22:00 left the old task evaluating rules until it stopped at 22:08, alongside the new one.
    - **AC-010's revocation half (check 5): pass.** After revoking the node's certificate and importing the CA's revocation list, its next sign-in was refused: `CreateSession ... AccessDeniedException: Certificate revoked`. The node holds a key and a certificate on disk, never an access key.
    - **Check 6: pass.** `accepted/` was copied to a folder and served by the local Grafana. Every panel query of *Factory usage* (RQ-1 to RQ-5 and RQ-7), run through `/api/ds/query`, returned the same rows as the cloud Grafana.
    - **Check 7: pass.**
      - In the cloud Grafana, these were all refused: `read_text('/proc/self/environ')`, `read_text('/proc/1/environ')`, `glob('/proc/*')`, `getenv(...)` (no such function), `duckdb_secrets(redact=false)`, `ATTACH`, and `SET enable_external_access = true` (the configuration is locked).
      - The API returned 401 to basic auth and to no auth.
- [x] T027 Phase 4's CHANGELOG entry, and the pull request
  - Depends on: T021 to T026, T030, T032, T033

  - Done 2026-11-21: the *The usage store* entry, draft PR #709
## Phase 5: Docs

- [x] T028 [`reports/usage/README.md`](../../../reports/usage/README.md): the sending flow, and the second paste-ready message for detailed mode. [`steering/data-and-tools.md`](../../../steering/data-and-tools.md): the commands file and the store in the retention table, and deletion on request
  - Requirements: REQ-017
  - Acceptance: AC-013
  - Privacy: PRIV-001, PRIV-004
  - Depends on: T020
  - Verification: a reading, and `TESTS`
  - Done 2026-11-21: the sending flow and the detailed-mode message went in with phase 3; this adds the schedule for an unattended machine's two commands. [`steering/data-and-tools.md`](../../../steering/data-and-tools.md) has the commands file in the retention table (phase 2), and now the store's 90 days, deletion of a person's prefix on request, and that the store sits in an approved system
- [x] T029 [`HOW-IT-WORKS.md`](../../../HOW-IT-WORKS.md) and [`README.md`](../../../README.md) agree with what shipped
  - Depends on: T027, T028
  - Verification: a reading, and `TESTS`
  - Done 2026-11-21: [`HOW-IT-WORKS.md`](../../../HOW-IT-WORKS.md) says where the numbers can go and what's sent on its own, and [`README.md`](../../../README.md)'s usage log row names the sender and the store

## Phase 6: Review fixes

- [x] T034 Fix the review's findings, each with a test where code changed
  - Depends on: the review
  - Verification: `TESTS`, the usage store's SQL tests with DuckDB 1.5.6, `terraform validate`, and the fixed image's extensions and lock checked in a local Grafana
  - Done 2026-11-21: F01 to F13, F15 to F19 and F22, and part of F20 and F21. F14 waits on a test account

## Requirement Traceability

| Requirement | Tasks | Acceptance | Done |
|---|---|---|---|
| REQ-001 | T001, T003 | AC-001 | 2026-11-21 |
| REQ-002 | T004 | AC-002 | 2026-11-21 |
| REQ-003 | T011 | AC-003 | 2026-11-21 |
| REQ-004 | T006, T017 | AC-003 | 2026-11-21 |
| REQ-005 | T007 | AC-004 | 2026-11-21 |
| REQ-006 | T008 | AC-004 | 2026-11-21 |
| REQ-007 | T002 | AC-005 | 2026-11-21 |
| REQ-008 | T009 | AC-003 | 2026-11-21 |
| REQ-009 | T001, T013 | AC-006 | 2026-11-21 |
| REQ-010 | T014 | AC-007 | 2026-11-21 |
| REQ-011 | T015 | AC-008 | 2026-11-21 |
| REQ-012 | T016 | AC-009 | 2026-11-21 |
| REQ-013 | T001, T021, T022, T023 | AC-010 | 2026-11-21; AC-010 at the first cloud deployment |
| REQ-014 | T021 | AC-010 | 2026-11-21; AC-010 at the first cloud deployment |
| REQ-015 | T024 | AC-011, AC-016 | 2026-11-21; AC-011 at the first cloud deployment |
| REQ-016 | T023 | AC-010 | 2026-11-21; AC-010 at the first cloud deployment |
| REQ-017 | T028 | AC-013 | 2026-11-21 |
| REQ-018 | T019 | AC-014 | 2026-11-21 |
| REQ-019 | T022 | AC-015 | 2026-11-21; AC-015 at the first cloud deployment |
| REQ-020 | T031 | AC-016 | 2026-11-21 |
| REQ-021 | T023 | AC-016 | 2026-11-21 |
| REQ-022 | T024, T025, T030, T032 | AC-016, AC-017 | 2026-11-21; AC-017 at the first cloud deployment |
| REQ-023 | T032, T033 | AC-016, AC-010 | 2026-11-21; AC-010 at the first cloud deployment |

## Review Findings

review-spec, 2026-11-21, on `usage-export/phase-5` against `main`. Lenses run: correctness and the requirement walk (probe, standing in for `code-review`), security (viper), engineering quality and architecture (cto, covering atlas's and review-principles' questions). Skipped: a separate atlas run and `find-dead-code`, since cto covered structure and dead code in the same pass. Nothing was run against a cloud account.

**Recommendation: Complete, for what can be checked without a cloud account.** F01 to F18 blocked it; T034 fixed all but F14, and the owner ruled on 2026-11-21 that F14's cloud runs happen at the first real cloud deployment. Until then the cloud halves of F06, F07, F08 and F10 are unverified, and the cloud README says so. Moving the spec to completed is the owner's step.

| ID | Severity | Finding | Where | Lens | Status |
|---|---|---|---|---|---|
| F01 | HIGH | A loop that dies while cron keeps sending heartbeats raises no alert: the silent-node rule reads only the newest `ts`, and `alive: false` shows only in RQ-5. AC-011 can't pass as written | `queries/alert-silent-node.sql`, `grafana/provisioning/alerting/rules.yaml` | probe | fixed |
| F02 | HIGH | Overlapping bundles double count: two 14-day exports a day apart have different `bundle_id`s, so RQ-1 and RQ-4 sum the same lines twice | `queries/views.sql` | probe | fixed |
| F03 | HIGH | A node name outside `[A-Za-z0-9._-]` is cleaned in the sender's key and not in the validator's check, so every bundle and heartbeat from it is rejected while the sender says `Sent:` | [`scripts/send_usage.py`](../../../scripts/send_usage.py) `safe()`, `validator.py` `expected_tail` | probe, cto | fixed |
| F04 | HIGH | The scrubber keeps quoted flag values (`--password "x"`), slash-bearing secrets (a 40-character cloud secret key), `curl -u`, `-pPASS`, `sshpass -p`, `X-Api-Key:` headers and `*_PASS=` assignments. The send-side check runs the same function, so it can't catch a miss. SEC-001 | [`scripts/usage_scrub.py`](../../../scripts/usage_scrub.py) | viper (risk 7), probe | fixed |
| F05 | HIGH | The guard misses writes to `export.json` that don't spell `.sanvio/export.json` (`cd .sanvio && ... > export.json`, `tee`, `python3 -c`), and `--opt-i`, which argparse accepts as `--opt-in`. An agent can repoint the store or turn on detailed mode. The send prints the key, not the store, so a repointed store goes unnoticed | [`.claude/hooks/guard.py`](../../../.claude/hooks/guard.py), [`scripts/send_usage.py`](../../../scripts/send_usage.py) | viper (risk 6), probe | fixed |
| F06 | HIGH | The person-sender role trusts any listed principal to set its own `usage_node` session tag, so one person can write under another's node, including heartbeats | `cloud/main.tf` person trust policy | viper (risk 6, plausible) | fixed in code, unverified until AC-010 |
| F07 | HIGH | One malformed accepted bundle (a date that isn't a date, an integer past range) breaks every panel until it expires; the validator catches only `ValueError`, reads objects of any size, and copies a KMS header onto a general bundle that Grafana then can't read | [`scripts/usage_shape.py`](../../../scripts/usage_shape.py) `DAY`, `validator.py`, `queries/views.sql`, `cloud/main.tf` bucket policy | viper (risk 5) | fixed; the bucket-policy half unverified until AC-010 |
| F08 | HIGH | The cloud Grafana sets no `GF_AUTH_BASIC_ENABLED=false` or admin password, and DuckDB's external access isn't locked, so a viewer posting SQL may read local files such as the task's environment | `cloud/grafana.tf`, the data sources' init SQL | viper (risk 6, plausible) | fixed; the lock verified in the local Grafana, the sign-in settings unverified until AC-010 |
| F09 | HIGH | Skill and agent names an agent chooses reach general bundles as they are; a prompt-injected agent can put text into the store through them | [`.claude/hooks/usage_log.py`](../../../.claude/hooks/usage_log.py), [`scripts/usage_shape.py`](../../../scripts/usage_shape.py) | viper (risk 4) | fixed |
| F10 | HIGH | No way to revoke one node's certificate: no CRL on the trust anchor and no instructions. REQ-019, AC-015 | `cloud/main.tf`, `cloud/README.md` | probe | fixed: revocation through an imported CRL, documented; unverified until AC-015 |
| F11 | HIGH | The SQL views hard-code their columns, and the only tie to the shape is a DuckDB test CI skips, so a renamed key reads as NULL with no failure | `queries/views.sql`, [`tests/test_usage_store.py`](../../../tests/test_usage_store.py), CI | cto | fixed |
| F12 | HIGH | Version skew: the Lambda carries the `usage_shape.py` of the clone it was applied from, so a team that updates the factory has its bundles rejected with nothing raised; and nothing says to schedule `validator.py --folder`, without which a healthy local node reads as silent | `cloud/main.tf`, `cloud/README.md`, `local/README.md` | cto, probe | fixed |
| F13 | HIGH | The cloud Grafana installs DuckDB's `httpfs` and `aws` extensions from the network at each start, unpinned | `cloud/grafana.tf` `USAGE_INIT` | cto | fixed: extensions baked into the image and checked, loaded in the local Grafana |
| F14 | HIGH | The cloud form is unverified: the T030 bucket half and AC-010, AC-011, AC-015, AC-017 haven't run, and no CI step runs `terraform validate` | T030, T026 | cto | ran 2026-11-26 at the first cloud deployment: see T026 |
| F15 | MEDIUM | A headless session consumes an expired opt-in, so the person never sees the "detailed mode ended" notice. REQ-008 | [`.claude/hooks/session_start.py`](../../../.claude/hooks/session_start.py) `detailed_notes` | probe | fixed |
| F16 | MEDIUM | `send_usage.py` crashes with no `export_refused` line on a folder store it can't write or a bundle file that isn't an object; the 500-character cut can land inside `[redacted]`, after which the send check refuses that day's detailed bundle on every export | [`scripts/send_usage.py`](../../../scripts/send_usage.py), [`scripts/usage_scrub.py`](../../../scripts/usage_scrub.py) | probe | fixed |
| F17 | MEDIUM | Usage lines are dated in UTC and the bundle's `today` in local time, so a late-evening use west of UTC drops out of a manual bundle | [`scripts/export.py`](../../../scripts/export.py) | probe | fixed |
| F18 | MEDIUM | PRIV-003: the path check is case-sensitive and misses `cd clients`, `ls projects`; the unlisted-project label is an unsalted hash a guess can reverse; an env-prefixed command's first word reaches the history `agent` field | [`scripts/usage_scrub.py`](../../../scripts/usage_scrub.py), [`scripts/send_usage.py`](../../../scripts/send_usage.py), [`scripts/loop.py`](../../../scripts/loop.py) | viper (risk 3) | fixed |
| F19 | MEDIUM | The detailed key delegates to the account root, so any principal there with IAM `kms:Decrypt` and bucket read can open detailed bundles; "owner only" holds only with an explicit deny | `cloud/main.tf` key policy | viper (risk 3) | fixed |
| F20 | MEDIUM | Small repeats: `SHAPE_FILES` in the validator and in Terraform, `LAST_SEND` in two scripts, the `.part` write in three places, two `keep_days`; `usage_log.rule()` classifies by a substring of the guard's message; Dependabot doesn't watch the image digest, the plugin or the providers | several | cto | partly fixed: Dependabot watches the image and providers, and the usage log's rule name comes from the guard. The small repeats stay |
| F21 | LOW | Minor behaviour: the cloud example's `projects/app` label is dropped without an error; `send_usage.py`'s docstring says key alias where the ARN is needed; extra workers' budgets aren't in the heartbeat; a node with no loops drops out of RQ-5; RQ-3 uses the latest sender's version; stray `.part` files are never pruned | several | probe | partly fixed: the docstring and the example's label. The rest stay |
| F22 | INFO | `local/compose.yaml` says an empty webhook means nowhere; its default is a dead local port | `local/compose.yaml` | cto | fixed |
| F23 | CRITICAL | The cloud Grafana never read its bucket. Grafana gives a backend plugin only an allowlist of its environment, so the DuckDB plugin never saw the task role's credentials, and every panel and alert rule errored. A smoke test of `/api/health` passed anyway | `cloud/grafana.tf` | first cloud deployment | fixed: `GF_PLUGINS_FORWARD_HOST_ENV_VARS` for that one plugin (#762); check 7 covers what it then holds |
| F24 | MEDIUM | Alert state lives in the task's own database. A new task re-sends every alert still firing, and during a rolling deployment the draining task keeps evaluating, so an alert that starts in that window is sent twice. REQ-015 says once | `cloud/grafana.tf` | first cloud deployment | open |
