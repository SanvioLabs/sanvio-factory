---
id: SPEC-004
status: draft
created: 2026-11-19
updated: 2026-11-19
owner: Pat
---

# SPEC-004: Usage export, sending a team's numbers to one place

The `status` field in the frontmatter above is the only copy of this spec's
state. Its values, in order: `draft`, `ready`, `in-progress`, `complete`.

A spec enters `plan-spec` only once it is `ready`, and `ready` means every Open
Question below is resolved. A person sets it.

## Summary

Every copy of this factory keeps its numbers on the machine it runs on: the
usage log in `.sanvio/usage/<user>.jsonl`, the loop's `.loop/` records, and the
token counts [`scripts/token_report.py`](../../../scripts/token_report.py) reads from Claude Code's own transcripts.
[`scripts/export.py`](../../../scripts/export.py) bundles them into one file, and nothing sends it.

That works for one person on one machine. It stops working once a team runs
the factory on several laptops and on unattended machines that run loops. The
factory's owner can't see the team's usage in one view, and nobody notices when
a node's loop stops, or when a run burns its whole budget.

This spec adds a way to send that bundle to one store the owner runs, in two
modes:

- **General.** Counts and performance only: sessions, skills, agents, slash
  commands, guard refusals and asks, loop runs with outcome, rounds, tokens and
  cost. This is the bundle `export.py` writes today, plus the fields that say
  which node and which factory version produced it.
- **Detailed.** Everything general sends, plus the text of the shell commands
  agents ran, scrubbed of secrets and of anything from a project's clone. Each
  person opts in, and the opt-in expires.

It also adds a heartbeat, so a silent node reads as down rather than idle, and
a spend alert, so a run that heads for its budget gets noticed while it runs.

**`export.py` stays the gate.** Its docstring already says its shape is the
only one any later sender may send. The sender added here sends only what
`export.py` writes, and the store checks that shape again when the bundle lands.

## Problem

- **No team view.** Each person's numbers live on their machine. The owner's
  only way to read them together is the sprint reports
  [`skills/factory-trends/`](../../../skills/factory-trends/) writes, which are prose and hold no history.
- **Unattended nodes go quiet.** A machine whose loop process died and a
  machine with nothing queued look the same from outside. A second loop on one
  node has died a minute after it started, and nothing said so.
- **Spend is reviewed, not watched.** `usage_report.py --review` finds a day
  over 3 times the usual spend, but only when someone runs it, after the fact.
  Two issues have each spent their full token budget on one environment bug
  before anyone looked.
- **Commands can't be reviewed at all.** The usage log records names, never
  arguments, by design. When the owner needs to see what agents actually ran,
  to tune [`bin/factory-tools`](../../../bin/factory-tools) or to understand a guard refusal, there's no record.
- **A bundle can't say where it came from.** The `user` field is the same on
  every node that runs as the same account, and nothing names the factory
  version, so a change in fix rounds can't be tied to a release.

## Goals

1. The owner reads every person's and every node's general numbers in one
   store, by day, person, node, project and factory version.
2. A person who opts in sends the shell commands their agents ran, scrubbed,
   for a set window, and the opt-in ends on its own.
3. A node whose loop stops sending a heartbeat raises an alert within the
   window the owner sets.
4. A loop run that passes a set share of its token budget raises an alert
   while it runs.
5. Nothing reaches the store that `export.py`'s shape doesn't allow, checked
   on the sending machine and again at the store.
6. A copy of this factory sends nothing anywhere until its owner configures a
   store of their own.

## Non-Goals

- Prompts, file contents, tool output, or any tool call's arguments beyond the
  shell command text in detailed mode.
- Claude Code's own OpenTelemetry export. It sends straight from the agent,
  with no shape check and no step where a person reads it first. A team can
  turn it on alongside this spec, but this spec doesn't depend on it or
  configure it.
- A hosted store run for other teams. Each factory's owner runs their own.
- Changing what the local usage log records in general mode. The promise in
  [`reports/usage/README.md`](../../../reports/usage/README.md) (*Telling your team*) stays true for anyone who
  doesn't opt in.
- Real-time dashboards. The store answers queries. A dashboard on top of it is
  a later spec.

## The questions the store answers

Every field the bundle carries has to serve at least one of these. A field
that serves none is cut. AC-012 checks the mapping.

| ID | Question |
|---|---|
| RQ-1 | Which skills, agents and slash commands did the team use this sprint, and which went unused? |
| RQ-2 | What does a merged pull request cost, in tokens and dollars, by project and by agent? |
| RQ-3 | How many fix rounds does an issue take, by agent, reviewer and factory version? |
| RQ-4 | Where does the guard refuse or ask most, and which asks do people always say yes to? |
| RQ-5 | Is every node's loop running, and when did each last report? |
| RQ-6 | Which shell commands do agents run most, and which ones get refused or asked about? (detailed only) |

## Affected Areas

```
Affected:
- scripts/export.py and tests/test_export.py: bundle v2 (mode, node,
  factory version, loop config, chain head, period, bundle id), the
  project allowlist, the commands section
- scripts/send_usage.py, new, and tests/test_send_usage.py: validate, scrub
  again, send one bundle or one heartbeat; --auto for unattended machines
- scripts/usage_scrub.py, new, and its tests: the one scrubber both the hook
  and the sender use
- .claude/hooks/usage_log.py and tests/test_usage.py: the commands file, the
  opt-in and its expiry, the detailed_on and detailed_expired lines
- .claude/hooks/session_start.py: says detailed mode is on and when it ends
- .claude/hooks/guard.py and tests/test_agent_hooks.py: agents can't write,
  move or delete the commands file or the export config
- examples/usage-store/, new: the reference store (bucket, validator,
  queries, alert job) as Terraform and one function
- skills/factory-trends/: offers to send the bundle as its last step
- reports/usage/README.md: the sending flow, and a second paste-ready message
  for detailed mode
- steering/data-and-tools.md: the commands file in the retention table, the
  store's retention
- HOW-IT-WORKS.md, README.md, CHANGELOG.md

Not Affected:
- what the usage log records for anyone not in detailed mode
- scripts/loop.py's run records (the heartbeat reads status.json, it
  doesn't change it)
```

## User Stories

| ID | Story |
|---|---|
| US-001 | As the factory's owner, I want every person's and node's numbers in one store, so that I can review the team's usage without collecting files by hand. |
| US-002 | As a person on the team, I want to read my bundle before it's sent, so that nothing leaves my machine I haven't seen. |
| US-003 | As a person who opts in to detailed mode, I want it to end on its own, so that a setting I turned on to debug one thing doesn't keep recording for months. |
| US-004 | As the owner, I want to hear when a node stops reporting or a run nears its budget, so that a dead loop or a runaway run costs minutes rather than a day. |
| US-005 | As an outside team using this factory, I want it to send nothing until I point it at my own store, so that adopting it never sends my numbers to anyone else. |

## Requirements

| ID | Pattern | Requirement |
|---|---|---|
| REQ-001 | Ubiquitous | `export.py` shall write bundle format `v: 2`, which adds to today's bundle: `mode` (`general` or `detailed`), `node` (the name set in the export config, else the host name), `factory` (this repo's commit and the top `CHANGELOG.md` entry's date), `loop_config` (agent, reviewer, workers and `max_issue_tokens` per included project, and no paths), `chain_head` (the hash of the usage log's last line), `period` (first and last day counted), and `bundle_id` (a hash of user, node, mode and period). |
| REQ-002 | Optional | Where the gitignored export config lists a project under `export_projects`, `export.py` shall include that project's loop runs under the label the config gives it. With no list, it shall include no project's runs, as it does today. |
| REQ-003 | Optional | Where detailed mode is live for the person, `export.py --mode detailed` shall add a `commands` section: one record per shell command with its time, session, whether it ran, was refused or was asked about, and its scrubbed text. Without a live opt-in it shall refuse `--mode detailed` and say why. |
| REQ-004 | Event-Driven | When a person runs `send_usage.py --opt-in detailed`, it shall record the opt-in with an end date `SANVIO_DETAILED_DAYS` days out (14 by default), and the usage log shall get a `detailed_on` line holding only the time and the end date. |
| REQ-005 | State-Driven | While detailed mode is live, the usage log hook shall write each Bash tool call's command, scrubbed by REQ-007, to `.sanvio/usage/<user>.commands.jsonl`, with the same hash chain and the same 90-day pruning as the usage log. |
| REQ-006 | Unwanted Behavior | If a session is headless (started by `bin/factory` or the loop), or its working folder is inside `projects/`, then the hook shall record no command for it, whatever the opt-in says. |
| REQ-007 | Ubiquitous | `usage_scrub.py` shall be the one scrubber. It drops a command naming `projects/`, `clients/`, a credential file the guard knows, or a secret command the guard knows. In the commands it keeps, it replaces the home folder with `~`, removes the user and password from any URL, and replaces with `[redacted]` each value of an environment assignment whose name `SECRET_ENV` in `scripts/loop.py` matches, each header value after `Authorization:` or `Bearer`, each known token shape (cloud access keys, GitHub, Slack, OpenAI and Anthropic key prefixes, PEM blocks), and each run of 32 or more characters that looks random. It cuts the command to 500 characters. Each record notes how many redactions it made. |
| REQ-008 | Event-Driven | When the opt-in's end date passes, the next session start shall stop writing commands, add a `detailed_expired` line, and say in its setup message that detailed mode ended and how to turn it on again. |
| REQ-009 | Event-Driven | When a person runs `send_usage.py FILE`, it shall check `FILE` against the v2 shape, refuse any key the shape doesn't name, run the scrubber over every command again, refuse the file if that changes anything, and send exactly the bytes of `FILE`. |
| REQ-010 | Unwanted Behavior | If no store is configured in `.sanvio/export.json`, then `send_usage.py` shall send nothing and say how to configure one. The repo shall ship no default store. |
| REQ-011 | Optional | Where the export config sets `auto: true`, `send_usage.py --auto` shall build and send a general bundle with no review step, for a machine nobody watches. `--auto` shall never send detailed mode. |
| REQ-012 | Event-Driven | When `send_usage.py --heartbeat` runs, it shall send one heartbeat: node, time, factory commit, and for each loop running on the node its label, whether its process is alive, how many issues wait, the issue in progress by number, its tokens so far and its budget. No issue title or text. |
| REQ-013 | Ubiquitous | The reference store in `examples/usage-store/` shall accept a bundle or heartbeat only into the sender's own prefix, never let a sender read or overwrite, check each object against the v2 shape when it lands and move it to `accepted/` or `rejected/` with the reason, and expire objects after the same 90 days as the local logs. |
| REQ-014 | Ubiquitous | The reference store shall keep detailed bundles under a separate prefix, encrypted with a key only the owner's role can use, so that general numbers can be shared with the team and commands can't. |
| REQ-015 | Event-Driven | When a node's last heartbeat is older than its window (30 minutes by default), or a heartbeat shows a run past a set share of its budget (80% by default), the reference store's alert job shall send one alert to the destination the owner configures, and not again for the same node or run until it recovers. |
| REQ-016 | Event-Driven | When a bundle lands whose `chain_head` doesn't follow from the same person's last accepted bundle, the store shall mark both, as the local report does for a broken chain. |
| REQ-017 | Ubiquitous | `reports/usage/README.md` shall carry the sending flow and a second paste-ready message telling the team what detailed mode records, who can read it and when it ends. |
| REQ-018 | Event-Driven | When `factory-trends` has written a person's sprint report, it shall offer to send that period's general bundle, show the person the bundle first, and send it through `send_usage.py` only on their yes. Laptops send no heartbeat. |
| REQ-019 | Ubiquitous | An unattended node shall authenticate to the store with short-lived credentials from the cloud provider's certificate-based workload identity, one certificate per node, so that no long-lived key sits on its disk and access is revoked node by node. `examples/usage-store/` shall set this up. |

## Acceptance Criteria

| ID | Requirement | Criteria | Verification |
|---|---|---|---|
| AC-001 | REQ-001 | A v2 bundle carries every new field, and a v1 reader's keys are unchanged | Unit test |
| AC-002 | REQ-002 | With no `export_projects`, no project run appears; with one listed, its runs appear under its label and no other project's do | Unit test |
| AC-003 | REQ-003, REQ-004, REQ-008 | `--mode detailed` is refused with no opt-in, works within the window, and is refused the day after it ends, with a `detailed_expired` line written | Unit test with a fixed clock |
| AC-004 | REQ-005, REQ-006 | A Bash call in a person's session lands in the commands file; one from a headless session, and one from a session under `projects/`, don't | Test in [`tests/test_usage.py`](../../../tests/test_usage.py) |
| AC-005 | REQ-007 | A fixture of commands holding each token shape, a URL with a password, an `Authorization` header, an env assignment of a secret name, a home path and a `clients/` path comes out with every secret redacted and the `clients/` command dropped | Unit test over a fixture of invented secrets |
| AC-006 | REQ-009 | A bundle with an extra key is refused; one whose commands still hold a secret shape is refused; a clean one is sent byte for byte | Unit test with a stand-in store |
| AC-007 | REQ-010 | With no `.sanvio/export.json`, nothing opens a network connection | Unit test that fails on any socket |
| AC-008 | REQ-011 | `--auto` with detailed asked for sends general, and says so | Unit test |
| AC-009 | REQ-012 | A heartbeat from a node with one live loop and one dead one reports both correctly, and holds no issue title | Unit test over a fixture `status.json` |
| AC-010 | REQ-013, REQ-014, REQ-016 | In a test account, a sender can't read its own prefix back, can't write another's, an off-shape bundle lands in `rejected/`, a detailed bundle can't be read by the general readers' role, and a chain gap is marked | A live run of `examples/usage-store/`, recorded in TASKS.md |
| AC-011 | REQ-015 | Stopping a test node's loop raises one alert inside its window, and one alert only; a run pushed past 80% of its budget raises one | A live run, recorded in TASKS.md |
| AC-012 | The questions the store answers | Every key in the v2 shape maps to at least one RQ in a table the tests read; adding a key with no mapping fails | Unit test |
| AC-013 | REQ-017 | The detailed-mode message names what's recorded, who reads it, and the end date | Reading, at review |
| AC-014 | REQ-018 | `factory-trends` shows the bundle and sends nothing when the person says no | Reading, plus a test of the skill's send step with a stand-in sender |
| AC-015 | REQ-019 | A test node sends with a certificate-issued credential, holds no access key on disk, and is refused once its certificate is revoked | A live run, recorded in TASKS.md |

## Security Requirements

| ID | Requirement |
|---|---|
| SEC-001 | Command text is scrubbed twice: by the hook before it's written to disk (REQ-005), and by the sender before it leaves (REQ-009). A secret never lands in a local file to be cleaned later. |
| SEC-002 | The sender reads no credential itself. It uses the cloud CLI's named profile set in the export config, and the config names the profile, never a key. On an unattended node that profile gets short-lived credentials (REQ-019). |
| SEC-003 | A sender's access to the store is write-only, to its own prefix. No sender can read anything back, its own included. |
| SEC-004 | Agents can't write, move or delete `.sanvio/export.json` or the commands file: the guard refuses it, as it does the usage log. |
| SEC-005 | The alert destination (a chat webhook, say) is read from the store's own secret store by name. It never sits in the repo, in the export config, or in a bundle. |

## Privacy and Compliance Requirements

| ID | Requirement |
|---|---|
| PRIV-001 | General mode records names and counts only, as the usage log does today. The paste-ready message in [`reports/usage/README.md`](../../../reports/usage/README.md) stays true for anyone not in detailed mode. |
| PRIV-002 | Detailed mode is one person's choice, for a set window, and they're told it's on at the start of every session in that window. Nobody turns it on for someone else. |
| PRIV-003 | Nothing from a project's clone, and no customer material, reaches a bundle. A command touching `projects/` or `clients/` is dropped, not redacted, and loop runs are included only for projects the owner lists. |
| PRIV-004 | The store keeps 90 days, like the local logs, and a person can ask the owner to delete their prefix. [`steering/data-and-tools.md`](../../../steering/data-and-tools.md) says so. |
| PRIV-005 | The store must sit in a system the owner has approved for the team's data, per [`steering/data-and-tools.md`](../../../steering/data-and-tools.md). The reference store is a cloud account the owner controls, not a third-party analytics service. |

## Observability Requirements

| ID | Requirement |
|---|---|
| OBS-001 | `send_usage.py` writes one line per send to the usage log: `export_sent` or `export_refused`, with the mode and the bundle id, never the contents. |
| OBS-002 | The factory dashboard shows when this machine last sent, and in which mode. |
| OBS-003 | The reference store's queries answer RQ-1 to RQ-6 as saved queries, one per question. |

## Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-001 | Python 3.9 or newer, standard library only, for everything outside `examples/usage-store/`. The sender shells out to the cloud CLI rather than adding a client library. |
| NFR-002 | A copy with no `.sanvio/export.json` behaves exactly as today, and every existing test passes unchanged. |
| NFR-003 | A send or heartbeat that fails never blocks a session or a loop. It logs `export_refused` with the reason and tries again next time. |
| NFR-004 | The usage log hook's added work for a Bash call in detailed mode stays under 50 ms. |

## Constraints

- **Built by hand, never on the loop.** It changes what leaves the machine and
  what the guard protects.
- **One sender, one shape.** Anything that sends usage anywhere goes through
  `send_usage.py` and the v2 shape. A second path is a defect.
- **Public repo.** Nothing tracked names a store, an account, a node or a
  person. Those live in the gitignored `.sanvio/export.json`.
- **Unattended machines get general mode only** (REQ-011), whatever their
  config says.

## Open Questions

Resolved by Pat on 2026-11-19:

- [x] Q1: In detailed mode, "commands" means the shell commands agents ran.
  Slash commands are already counted in general mode, and no other tool's
  arguments are recorded.
- [x] Q2: Only the factory's owner can read detailed records. General numbers
  can be shared with the team (REQ-014).
- [x] Q3: Unattended nodes send general bundles and heartbeats automatically,
  and never detailed mode (REQ-011).

- [x] Q4: An unattended node authenticates with short-lived credentials from
  the cloud provider's certificate-based workload identity, one certificate
  per node, revoked node by node (REQ-019). No long-lived key on its disk.
- [x] Q5: `export.py`'s rule changes from "a project's loop runs never leave
  the machine" to "only the projects the owner lists, under a label the owner
  picks", with the list empty by default (REQ-002).
- [x] Q6: A person sends when they write their sprint report: `factory-trends`
  offers it as its last step (REQ-018). Laptops send no heartbeat.

No questions remain open.
