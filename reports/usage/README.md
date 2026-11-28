# Usage reports

One file per person per sprint, written by [`skills/factory-trends/`](../../skills/factory-trends/) from that
person's own usage log and read by them before they send it to the factory's
owner. Reports are gitignored, so they stay here on each person's machine and
never go into the repo; only this README is tracked. The owner reads a
sprint's reports together, takes the proposals worth taking, and says why for
the ones it doesn't.

Each report also lists the plugins and mods enabled for that person, by id,
version and scope, and says which changed since their last report. The owner
reviews the ones that changed before the next sprint.

Counts and proposals only. The raw logs stay in `.sanvio/usage/` on each
person's machine, and that folder is gitignored.

## The export

```
python3 scripts/export.py --since 2026-10-01 --out reports/usage/export.json
```

That path is gitignored, like the reports.

[`scripts/export.py`](../../scripts/export.py) bundles your numbers into one JSON file. Without `--since`
it counts the last 14 days, and without `--out` it prints the bundle. It holds
your user name as your usage log's filename has it, the runs of the factory's
own loop from `.loop/history.jsonl` (outcome, rounds, test results, verdicts,
the review's reasons for each FIX, whether each round changed an existing test
file, tokens, cost, agent and reviewer), and the counts from your usage log:
sessions, skills, agents, slash commands, guard refusals, guard asks and the
asks you said yes to.

It also says where it came from: this machine's name, the factory's commit and
the date of its newest changelog entry, the loop's agent and reviewer by name and
model with its worker, round and token limits, and the hash of your usage log's
last line. A project's runs are in it only where `.sanvio/export.json` lists that
project, under the label you give it:

```json
{"node": "my-laptop", "export_projects": {"web-app": "web-app"}}
```

With no list, no project's runs are in it. `.sanvio/` is gitignored, so the list
stays on your machine.

It stays where you write it until you send it. Its shape,
[`scripts/usage_shape.py`](../../scripts/usage_shape.py), is the only shape anything may send:
anything not in it stays on your machine, and the export refuses to write a
bundle that isn't in it.

## Sending it

[`scripts/send_usage.py`](../../scripts/send_usage.py) sends a bundle to the store your factory's owner
runs, and nothing at all until `.sanvio/export.json` says `"send": true` and
names a store. This repo ships neither. The store is a folder (one on this
machine, for a store you run locally) or a bucket reached through the cloud
CLI's named profile:

```json
{"send": true, "store": {"kind": "folder", "path": "~/usage-store"}, "node": "my-laptop"}
```

`"send"` is this machine's switch. Set it to `false`, or leave it out, and
nothing is sent from here, by hand or on a schedule. The store's settings
stay where they are, so turning it back on is one word. A scheduled `--auto`
or `--heartbeat` run on a machine that's switched off says so and exits 0, so
it doesn't read as a failure. A machine that's switched off stops sending
heartbeats too, so the store's silent-machine alert fires for it once.

```
python3 scripts/export.py --out reports/usage/export.json   # write it, then read it
python3 scripts/send_usage.py reports/usage/export.json      # send exactly that file
```

It checks the file against the shape first, refuses a key the shape doesn't
name, and scrubs every command in a detailed bundle again, sending nothing if
that would change one. The sprint report offers to send its period's general
bundle as its last step, and only sends on your yes.

A machine nobody watches, one that runs loops, sets `"auto": true` and runs
two commands on a schedule: `--auto` sends yesterday's and today's general
bundles, never detailed, and `--heartbeat` sends whether each of its loops is
alive and how many issues wait, so a stopped loop shows as stopped rather than
quiet. A loop that died, killed or ended on an error, raises the store's alert;
one you stopped, whose `--for` ran out, or that never ran on this machine
doesn't. A project you haven't listed under `export_projects` shows in a
heartbeat under a hashed label, with no issue, tokens or budget.

The store's silent-machine alert fires after 30 minutes without a heartbeat,
so send one more often than that. With cron, from the factory's folder:

```
*/10 * * * *  cd /path/to/factory && python3 scripts/send_usage.py --heartbeat
0 * * * *     cd /path/to/factory && python3 scripts/send_usage.py --auto
```

A launchd job or a systemd timer does the same with the same two commands.

Each send or refusal of a bundle adds one line to your usage log, with the
mode and the bundle's id, and the factory dashboard says when you last sent.

## Telling your team

The log is on by default, so tell people before their first session. This is
written to paste into Slack or your team's working-practices doc as it is:

> The harness keeps a usage log on your own machine: which skills, agents and
> slash commands you ran, and when the guard refused something or asked you
> first. It records names and counts only. No prompts, no code, no file paths,
> and nothing leaves your machine on its own.
>
> At the end of each sprint, ask your agent for "my factory report". It
> summarizes your log, asks what worked, what you worked around and what you'd
> change, and writes a short report you read before you send it to me. It
> never goes into the repo. I read the sprint's reports together and we decide
> what goes into the factory.
>
> To turn the log off for yourself, set `SANVIO_USAGE_LOG=off` in your shell
> profile.

## Detailed mode

Detailed mode adds the shell commands your sessions run to your bundle, for
when the owner needs to see what agents actually ran. Only you turn it on, for
yourself, and it ends on its own:

```
python3 scripts/send_usage.py --opt-in detailed   # on for 14 days (SANVIO_DETAILED_DAYS)
python3 scripts/send_usage.py --opt-out           # off now
python3 scripts/export.py --mode detailed          # a bundle with the commands
```

Each command is scrubbed before it's written to
`.sanvio/usage/<you>.commands.jsonl`: secrets become `[redacted]`, your home
folder becomes `~`, and a command that reaches [`projects/`](../../projects/), `clients/` or a
credential file isn't written at all. Nothing is recorded from a headless run,
from a session working inside [`projects/`](../../projects/), or with the usage log off. Every
session start says it's on and until when, and says once when it ends. The
guard asks before an agent turns it on for you, and refuses a loop agent.

If you ask people to turn it on, tell them first. This is written to paste as
it is:

> For the next two weeks I'd like some of us to turn on the factory's detailed
> mode: `python3 scripts/send_usage.py --opt-in detailed`. It adds the shell
> commands your agents run to your usage report, scrubbed first: secrets are
> redacted, and anything touching a project's or client's files isn't recorded
> at all. Only I can read the detailed records. It turns itself off after 14
> days, and `--opt-out` turns it off sooner. No prompts, no code and no file
> contents, ever.
