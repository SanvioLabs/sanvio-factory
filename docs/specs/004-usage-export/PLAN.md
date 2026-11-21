---
spec: SPEC-004
status: draft
created: 2026-11-21
updated: 2026-11-21
---

# Implementation Plan: SPEC-004

## Specification

Link: [`SPEC.md`](SPEC.md). Its status when this plan was written: `ready` as of
2026-11-21. If the spec changes after this date, this plan may be stale.

## Repository Analysis

Read for this plan:

- [`.claude/hooks/usage_log.py`](../../../.claude/hooks/usage_log.py): `entry()` turns each hook event into one line and records nothing for a plain Bash call today. `record()`, `record_off()` and `prune()` write through [`scripts/log_chain.py`](../../../scripts/log_chain.py) under its lock. `log_path()` is `.sanvio/usage/<user>.jsonl`.
- [`scripts/export.py`](../../../scripts/export.py): `bundle()` writes `v: 1` with `exported`, `since`, `user`, `loop` and `usage`. `loop_runs()` drops any history line tagged with a project, and `LOOP_KEYS` is the allowlist of keys per run.
- [`.claude/hooks/guard.py`](../../../.claude/hooks/guard.py): `LOG_NAME` already covers every path under `.sanvio/usage/`, so a commands file and an opt-in file there are read-only to agents with no change. `MACHINES_NAME` is the pattern for a file a person is asked about and a headless run is refused, which is what `.sanvio/export.json` needs. `CREDENTIAL`, `CREDENTIAL_NAMES` and `SECRET_COMMANDS` are what the scrubber reuses.
- [`scripts/loop.py`](../../../scripts/loop.py): `SECRET_ENV` (the env names to redact), `pid_alive()`, `Loop.take_lock()` (the pid in `.loop/lock`, or `.loop/projects/<name>/lock`), `read_status()` (`queue`, `issues`, `reviews`), `mark()` (an issue row's fields), and `budget()` (a project's `max_issue_tokens`).
- [`scripts/names.py`](../../../scripts/names.py): `state_dir()`, `headless()`, `keep_days()`, `logging_off()`, and the `SANVIO_` prefix every new variable takes.
- [`.claude/hooks/session_start.py`](../../../.claude/hooks/session_start.py): `LOG_OFF`, the one-line message pattern for a setting that changes what's recorded.
- [`scripts/dashboard_data.py`](../../../scripts/dashboard_data.py): `last_review()` and the `activity` block, the pattern for OBS-002's last send.
- [`skills/factory-trends/SKILL.md`](../../../skills/factory-trends/SKILL.md): the *Sprint run* steps that REQ-018's offer goes after.
- [`tests/test_export.py`](../../../tests/test_export.py), [`tests/test_usage.py`](../../../tests/test_usage.py), [`tests/test_agent_hooks.py`](../../../tests/test_agent_hooks.py), [`tests/test_dashboard_data.py`](../../../tests/test_dashboard_data.py): fixed clocks, temporary roots, and hook events fed on stdin.

## Existing Patterns

- **Names, never content, in the usage log.** Every new usage-log line (`detailed_on`, `detailed_expired`, `export_sent`, `export_refused`) holds a time and a few fixed fields, like `log_off`.
- **One copy of a rule.** `usage_log.py` imports the guard rather than restating its patterns. The scrubber imports the guard's and the loop's patterns the same way, and the store's validator imports the same shape module the sender uses.
- **Hash-chained, pruned, guard-protected logs.** The commands file is a second log of the same kind, written with `log_chain.append()` and pruned by the same `_prune()`.
- **Gitignored local config for anything that names a machine, account or person.** `.sanvio/` is already ignored.
- **Standard library only outside [`examples/`](../../../examples/).** A cloud call shells out to the CLI, as `gh` is shelled out to today.
- **A failure in a hook never stops a session.** The new hook paths keep `usage_log.py`'s catch-all.

## Design

### New modules

| File | Holds |
|---|---|
| `scripts/usage_shape.py` | The v2 bundle's keys and types, the heartbeat's, the field-to-question table (AC-012), and `problems(obj)`, which returns every way an object is off-shape. Read by `export.py`, `send_usage.py` and the store's validator |
| `scripts/usage_scrub.py` | `scrub(command, home)`, returning `(text, redactions)` or `None` for a dropped command. Imports its patterns from `guard.py` and `loop.py` |
| `scripts/send_usage.py` | `FILE`, `--auto`, `--heartbeat`, `--opt-in detailed`, `--opt-out`. Reads `.sanvio/export.json`, sends through the cloud CLI's named profile |
| `examples/usage-store/` | Terraform for the bucket, the key, the roles and the workload identity; one validator function; the alert job; one saved query per RQ |

### `.sanvio/export.json`

```json
{
  "store": {"kind": "s3", "bucket": "<bucket>", "prefix": "<team>", "profile": "<cli profile>", "region": "<region>"},
  "node": "<name>",
  "auto": false,
  "export_projects": {"<project folder>": "<label>"},
  "heartbeat_minutes": 10
}
```

No store means nothing is sent (REQ-010). The repo ships an example of this
file under `examples/usage-store/`, with invented values, and no copy at the
root.

### Where things land

```
<prefix>/incoming/<node>/<user>/general/<bundle_id>.json
<prefix>/incoming/<node>/<user>/detailed/<bundle_id>.json   (encrypted, owner key)
<prefix>/incoming/<node>/heartbeat/<time>.json
        -> validator -> accepted/... or rejected/...<reason>
```

A sender's role may `PutObject` only under its own `incoming/<node>/`. Nothing
may `GetObject` under `incoming/`. The validator moves each object and writes
the reason beside a rejected one. Athena reads `accepted/` only.

### Detailed mode on the machine

- `--opt-in detailed` writes `.sanvio/usage/<user>.detailed` holding the end
  date, and the usage log gets `detailed_on`. Under `.sanvio/usage/`, the
  guard already keeps it from agents.
- While that date is in the future, `entry()` turns a `PreToolUse` Bash call
  into a line for `.sanvio/usage/<user>.commands.jsonl`: time, session,
  scrubbed text, redactions, and `ran`, `refused` or `asked` from the guard's
  verdict. `None` from the scrubber writes nothing.
- A headless session, or one whose `cwd` is inside [`projects/`](../../../projects/), writes no
  command line (REQ-006).
- At session start, a past end date removes the file, writes
  `detailed_expired`, and adds one line to the setup message.

### Heartbeat

`--heartbeat` finds each loop by its state folder (`.loop/` and each
`.loop/projects/<name>/`), reads the pid in its `lock` with `pid_alive()`,
counts `queue`, takes the top `issues` row whose state is still running, and
reads its tokens and the project's `budget()`. A project not in
`export_projects` appears only as `alive` and `waiting`, under a hashed
label, so a node's liveness never names an unlisted project.

## Phases

| Phase | Delivers | Needs before it starts |
|---|---|---|
| 1. Shape and scrubber | `usage_shape.py`, `usage_scrub.py`, `export.py` v2 with `export_projects`. No network, nothing new recorded | Nothing |
| 2. Detailed capture | The opt-in, the commands file, expiry, the setup message, the guard rule for `export.json`, `export.py --mode detailed` | Phase 1 |
| 3. Sender | `send_usage.py` in every mode, OBS-001 lines, the dashboard's last send, the `factory-trends` offer | Phase 2 |
| 4. Reference store | `examples/usage-store/` and the live runs AC-010, AC-011, AC-015 | Phase 3, and a test cloud account named in local config |
| 5. Docs | [`reports/usage/README.md`](../../../reports/usage/README.md), [`steering/data-and-tools.md`](../../../steering/data-and-tools.md), [`HOW-IT-WORKS.md`](../../../HOW-IT-WORKS.md), [`README.md`](../../../README.md) | Each phase updates its own docs; this one checks they agree |

One pull request per phase into `main`, each with its own
[`CHANGELOG.md`](../../../CHANGELOG.md) entry. Phases 1 to 3 change nothing for
a copy with no `.sanvio/export.json` (NFR-002), so each can merge alone.

## Outside this repo

A deployment's own machines and account need wiring this repo doesn't hold:
a scheduler on each unattended node running `--heartbeat` and `--auto`, the
node's certificate, and the account that hosts the store. Each deployment
does that in its own provisioning, after Phase 4.

## Risks

| Risk | What holds it |
|---|---|
| A secret shape the scrubber doesn't know | The scrubber runs twice, the sender refuses a file a second pass changes, and the high-randomness rule catches most unknown tokens. AC-005's fixture grows with every shape found |
| Hook latency on every Bash call in detailed mode | NFR-004, measured in a test that times 1,000 scrubs |
| The validator and the sender disagree on the shape | Both import `usage_shape.py`; the Terraform packages that file, not a copy |
| A heartbeat naming a client's project | Unlisted projects go under a hashed label (Design, *Heartbeat*) |
| Terraform in a repo with no Terraform CI | Phase 4 runs `terraform fmt -check` and `terraform validate` by hand and records them, and the module stays under [`examples/`](../../../examples/) |
