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

Nothing sends it. It stays where you write it. Its shape,
[`scripts/usage_shape.py`](../../scripts/usage_shape.py), is the only shape any later sender may send:
anything not in it stays on your machine, and the export refuses to write a
bundle that isn't in it.

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
