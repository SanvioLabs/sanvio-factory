---
name: factory-trends
description: Turn your factory usage for a sprint into a short report you share with the factory's owner, with what you'd add, change or drop. A daily run reads the day before's numbers, names at most three trends, recommends one change and, with your yes, puts it to the team as tomorrow's pulse question. Reads your own local usage log, Claude Code's token counts, the loop's own records and the dashboard's numbers, and the sprint run reads the team's pulse counts. You read every report before it goes anywhere, and nothing goes to the pulse folder without your yes. Use at the end of a sprint, or when someone asks for "factory trends", "how did yesterday go", "what should we change in the factory", "my factory report", "what did I use this sprint", "sprint follow-up", "what should we add to the factory", "token burn", "how many tokens", or "what did the loop cost", or by its old name, "harness trends", "my harness report" or "what should we add to the harness".
license: MIT. From Sanvio Factory by Sanvio Labs, https://github.com/SanvioLabs/sanvio-factory
---

# Factory trends

Each person's usage log stays on their own machine. This turns it into the one
thing that's shared: a short report, with the person's own proposals, that they
send to the factory's owner themselves. The report is gitignored and never
committed. The owner reads the sprint's reports together and decides what goes
into the factory.

The daily run is smaller. It compares yesterday with the six days before it,
recommends one change to the factory, and with the person's yes asks the team
about it in tomorrow's pulse. Its note stays in [`reports/trends/`](../../reports/trends/) on the
machine that wrote it, and the sprint report collects the notes and the team's
votes.

The log is written by [`.claude/hooks/usage_log.py`](../../.claude/hooks/usage_log.py). It holds names and counts,
never prompts, paths or code. The token counts come from Claude Code's own
transcripts on your machine, read by [`scripts/token_report.py`](../../scripts/token_report.py), which prints
only numbers, model names, session ids and issue names. The one dollar figure,
the loop's, comes from the estimate the loop records for each run. The plugin
list comes from `claude plugin list --json`, read by
[`scripts/plugin_report.py`](../../scripts/plugin_report.py), which prints each enabled plugin's id,
version and scope and no path.

## Steps

1. **Choose the run.** The sprint run is for a factory report, a sprint
   follow-up, tokens or the loop's cost, or any period longer than a day.
   Anything else is the daily run.

### Sprint run

1. **Pick the period.** Use the date of their last report in
   [`reports/usage/`](../../reports/usage/) (the newest file with their name) as the start. If there
   isn't one, ask how long their sprint is, and default to 14 days.
2. **Run the summary:**

   ```bash
   python3 scripts/usage_report.py --since <YYYY-MM-DD> --previous reports/usage/<their last report>
   ```

   Leave out `--previous` if there isn't a last report. With it, the summary
   adds an `Unused two sprints running:` line naming the skills on both that
   report's `Never used here:` line and this one's.

   If it says there's no log, tell them why it might be missing (the hook isn't
   wired, or `SANVIO_USAGE_LOG` is off) and stop. Don't guess at their usage.

   Then the tokens, from the same date:

   ```bash
   python3 scripts/token_report.py --since <YYYY-MM-DD>
   ```

   It reads Claude Code's own transcripts and prints tokens for conversations
   here, for each repo under [`projects/`](../../projects/) and for each issue the loop built,
   Claude Code only. It also prints each loop issue's cost as the loop recorded
   it: an estimate at API prices, not what was billed, low wherever a run
   recorded none, and counted by when the loop picked the issue up. A
   conversation's transcript carries no cost, so conversations stay in tokens.

   Then the plugins and mods, with their last report (step 1) to compare with:

   ```bash
   python3 scripts/plugin_report.py --previous reports/usage/<their last report>
   ```

   Leave out `--previous` if there isn't one. It lists the enabled plugins and
   mods and says which changed version, arrived or went since that report. If
   it can't read them it says so in a line, and the report carries that line.
3. **Show them the summary.** If it has an `Unused two sprints running:` line
   other than `none`, ask about each skill on it first, one at a time: drop it,
   keep it, or test it. For "test it", name the evals in `skill-creator` if
   that skill is installed, and otherwise say no eval skill is installed here.
   Don't run an eval. Record each answer under `## Proposals` in their words.
   If they skip, the line stays in the summary and nothing is recorded. Then
   ask, one at a time:
   - What worked well enough that the team should use it?
   - Where did you work around the factory: a skill you skipped, a guard you
     kept saying yes to, a step you did by hand?
   - One or two proposals. For each: add, change or drop what, and why.
   Use their words. Point at the numbers where they back a proposal up ("asked
   12 times, said yes 12 times" argues for loosening that ask). Don't invent a
   proposal they didn't make.
4. **Review what changed, if they own this factory.** Ask once: "Do you own
   this factory?" On a no, or if the plugin output has no `Changed since` line,
   skip this step. On a yes, run `stelliad:review-skill` on the installed folder
   of each changed or new plugin, or [`skills/review-skill/`](../review-skill/SKILL.md) where Stelliad isn't
   installed. Read each folder from `claude plugin list --json` yourself, and
   never put it in the report. There is no old version on disk to diff against,
   so the review reads the whole folder and its changelog if it has one. The
   findings go under `## Changed plugins` in the report. Don't ask again for
   this report, and don't record the answer.
5. **Write the report** to `reports/usage/<YYYY-MM-DD>-<user>.md`: the summary
   as printed, then a `## Tokens and loop cost` section with the token summary
   as printed, then the plugin output as printed (it starts with its own
   `## Plugins and mods` heading), then `## Changed plugins` if step 4 ran,
   then a `## Daily recommendations` section, then a `## Proposals` section
   with their answers. Leave nothing unfilled.

   `## Daily recommendations` lists each file in [`reports/trends/`](../../reports/trends/) dated in
   the period, one line each, with its date and its recommendation. Then the
   team's vote on it, if the pulse skill's step 1 finds the `Pulse folder` row
   in `company/DATA.md` cleared. Run, from the period's start to today:

   ```bash
   python3 scripts/pulse.py summary --since <YYYY-MM-DD> --until <YYYY-MM-DD>
   ```

   For each file, find the summary entry headed
   `## <the file's date plus one day>: Factory`, or, for a question asked
   before the chip's rename, `## <that date>: Harness`, or
   `## <that date>: trend-<that date>` for a question since removed from the
   bank. Copy that entry's option counts. Write
   `Fewer than three answered.` where the summary says that, and `No answers.`
   where there's no entry. The skill never copies an Other answer. If the row
   isn't cleared, list the recommendations and write
   `Pulse folder not cleared.` once, under them.
6. **Have them read it.** It's going to the owner. They can cut anything.
7. **Say how to share it:** they send the file to the factory's owner
   themselves, the way the team passes documents around. It stays in
   [`reports/usage/`](../../reports/usage/) on their machine, gitignored, where step 1 finds it next
   sprint.

### Daily run

Dates are written `YYYY-MM-DD`: today, yesterday, and tomorrow, the day the
question would be asked.

1. **Check the report is ignored.** Run:

   ```bash
   git check-ignore -q reports/trends/<today>.md
   ```

   On a non-zero exit, say the file isn't ignored, write nothing, and stop.
2. **Get the numbers.** Run, with the day 7 days before today:

   ```bash
   python3 scripts/dashboard_data.py --json --since <YYYY-MM-DD>
   ```

   Compare only the `by_day` entries in `loop_history`, `loop_spend` and
   `conversations` (its `factory` and `loop` sides each have one). Yesterday's
   entry is compared against the sum of the six entries before it, never
   today's: today isn't over. A day in `loop_spend` whose `cost_usd` is `null`
   is named, not summed. `activity` and `loop_rework` are cited only as totals
   for the period, never as a trend. A section whose `value` is `null` is named
   with its `why`, and nothing is filled in for it.
3. **Name the trends.** At most three, each one sentence giving yesterday's
   figure and the six days' sum. In two cases say `No trend yesterday.`, write
   the report (step 7) with that line and `Proposed: no, no trend`, and stop:
   - every compared section is `null`
   - every compared field is 0 or `null` both yesterday and across the six days
4. **Recommend one change.** Add, change or drop one thing in the factory,
   named as people say it (for example "the pulse skill"), never by its path,
   and say which trend it answers. Never more than one.
5. **Draft the question** in the bank's format, and show it exactly as it will
   be written:

   ```text
   ## trend-<tomorrow>
   Chip: Factory
   Question: <Should we make the change, in one line?>
   - Yes: Make this change
   - Not yet: Ask again later
   - No: Leave the factory as it is
   ```

   The `Question:` line is one line naming only the change, with no figure,
   title, project name or issue name. There's no `Date:` line: `propose`
   refuses a file with one, and takes the date from `--date`.
6. **Propose it.** Only when the pulse skill's step 1 finds the
   `Pulse folder` row in `company/DATA.md` cleared, and the person says yes to
   this one step. If the row isn't cleared, say so and propose nothing. On a
   yes:
   - Write the question to `local-data/pulse-proposal.md` with the Write tool.
   - Run:

     ```bash
     python3 scripts/pulse.py propose --file local-data/pulse-proposal.md --date <tomorrow>
     ```

   - Delete `local-data/pulse-proposal.md` whether or not `propose` succeeded.
   - On a non-zero exit, show the reason it gave and don't retry.
7. **Write the report last** to `reports/trends/<today>.md`. It holds the
   trends, the recommendation and the question, and ends `Proposed: yes` or
   `Proposed: no, <reason>`. The reason is one of: not cleared, declined, or
   the reason `propose` gave.

## For the owner

Read the sprint's reports together, not one at a time. A pattern across
people is the signal: the same skill never used, the same ask answered yes
every time, the same workaround. For each proposal you take, make the change
in its own PR with a [`CHANGELOG.md`](../../CHANGELOG.md) entry, so "what's new" tells everyone. For
one you don't, tell its author why.

## Rules

- Never read or quote another person's log. Each report comes from its
  author's own machine.
- Never add a prompt, a file path, a command or code to the report, even if
  they mention one. Describe it instead ("a deploy script", not the script).
- Never commit anything under `.sanvio/`. The raw log stays local.
- Never commit a report, force-add it, or send it anywhere. It's gitignored,
  and the author sends it.
- A drafted question never holds a figure, a title, a project or issue name, a
  prompt, a file path, a command or code.
- A daily report holds no prompt, file path, command or code.
- Never run `propose` without a yes given in this session, and never write to
  the shared folder any other way.

## Output

For the sprint run, the report file, read by its author, and the commands that
share it. For the daily run, the note in [`reports/trends/`](../../reports/trends/), and the
question in tomorrow's pulse if the person said yes.
