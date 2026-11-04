# Usage reports

One file per person per sprint, written by [`skills/harness-trends/`](../../skills/harness-trends/) from that
person's own usage log and read by them before they send it to the harness
owner. Reports are gitignored, so they stay here on each person's machine and
never go into the repo; only this README is tracked. The owner reads a
sprint's reports together, takes the proposals worth taking, and says why for
the ones it doesn't.

Each report also lists the plugins and mods enabled for that person, by id,
version and scope, and says which changed since their last report. The owner
reviews the ones that changed before the next sprint.

Counts and proposals only. The raw logs stay in `.harness/usage/` on each
person's machine, and that folder is gitignored.

## The export

```
python3 scripts/export.py --since 2026-10-01 --out reports/usage/export.json
```

That path is gitignored, like the reports.

[`scripts/export.py`](../../scripts/export.py) bundles your numbers into one JSON file. Without `--since`
it counts the last 14 days, and without `--out` it prints the bundle. It holds
your user name as your usage log's filename has it, the harness loop's runs
from `.loop/history.jsonl` (outcome, rounds, test results, verdicts, tokens,
cost, agent and reviewer, and never a project's runs), and the counts from your
usage log: sessions, skills, agents, slash commands, guard refusals, guard asks
and the asks you said yes to.

Nothing sends it. It stays where you write it. Its shape is the only shape any
later sender may send: anything not in it stays on your machine.

## Telling your team

The log is on by default, so tell people before their first session. This is
written to paste into Slack or your team's working-practices doc as it is:

> The harness keeps a usage log on your own machine: which skills, agents and
> slash commands you ran, and when the guard refused something or asked you
> first. It records names and counts only. No prompts, no code, no file paths,
> and nothing leaves your machine on its own.
>
> At the end of each sprint, ask your agent for "my harness report". It
> summarizes your log, asks what worked, what you worked around and what you'd
> change, and writes a short report you read before you send it to me. It
> never goes into the repo. I read the sprint's reports together and we decide
> what goes into the harness.
>
> To turn the log off for yourself, set `HARNESS_USAGE_LOG=off` in your shell
> profile.
