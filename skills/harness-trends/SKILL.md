---
name: harness-trends
description: Turn your harness usage for a sprint into a short report you share with the harness owner, with what you'd add, change or drop. Reads only your own local usage log, Claude Code's token counts and the loop's own cost records, and you read the report before it goes anywhere. Use at the end of a sprint, or when someone asks for "my harness report", "what did I use this sprint", "sprint follow-up", "what should we add to the harness", "token burn", "how many tokens", or "what did the loop cost".
license: MIT. From the Sanvio Labs harness starter, https://github.com/SanvioLabs/sanvio-harness-starter
---

# Harness trends

Each person's usage log stays on their own machine. This turns it into the one
thing that's shared: a short report, with the person's own proposals, that they
send to the harness owner themselves. The report is gitignored and never
committed. The owner reads the sprint's reports together and decides what goes
into the harness.

The log is written by [`.claude/hooks/usage_log.py`](../../.claude/hooks/usage_log.py). It holds names and counts,
never prompts, paths or code. The token counts come from Claude Code's own
transcripts on your machine, read by [`scripts/token_report.py`](../../scripts/token_report.py), which prints
only numbers, model names, session ids and issue names. The one dollar figure,
the loop's, comes from the estimate the loop records for each run. The plugin
list comes from `claude plugin list --json`, read by
[`scripts/plugin_report.py`](../../scripts/plugin_report.py), which prints each enabled plugin's id,
version and scope and no path.

## Steps

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
   wired, or `HARNESS_USAGE_LOG` is off) and stop. Don't guess at their usage.

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
   - Where did you work around the harness: a skill you skipped, a guard you
     kept saying yes to, a step you did by hand?
   - One or two proposals. For each: add, change or drop what, and why.
   Use their words. Point at the numbers where they back a proposal up ("asked
   12 times, said yes 12 times" argues for loosening that ask). Don't invent a
   proposal they didn't make.
4. **Review what changed, if they own this harness.** Ask once: "Do you own
   this harness?" On a no, or if the plugin output has no `Changed since` line,
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
   then a `## Proposals` section with their answers. Leave nothing unfilled.
6. **Have them read it.** It's going to the owner. They can cut anything.
7. **Say how to share it:** they send the file to the harness owner
   themselves, the way the team passes documents around. It stays in
   [`reports/usage/`](../../reports/usage/) on their machine, gitignored, where step 1 finds it next
   sprint.

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
- Never commit anything under `.harness/`. The raw log stays local.
- Never commit a report, force-add it, or send it anywhere. It's gitignored,
  and the author sends it.

## Output

The report file, read by its author, and the commands that share it.
