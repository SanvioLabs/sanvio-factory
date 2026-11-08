---
name: work-report
description: Write a one-page report of what got done in a repo over a period, for a lead or a team: what merged by type (bug, enhancement, documentation, chore) and who made and approved it, what the loop built, the milestones GitHub recorded, the specs it touched, a chart of merges, and what to watch. Reads GitHub through gh and the repo's CHANGELOG.md and changes nothing. Use when someone asks for a "work report", "what got done", "what did we ship", "which milestones did we hit", "a report for my lead", "showcase the work", or "what did the team do this sprint".
license: MIT. From the Sanvio Labs harness starter, https://github.com/SanvioLabs/sanvio-harness-starter
---

# Work report

One page on what got done in one repo over a period, built from what GitHub
recorded rather than what anyone remembers. [`scripts/work_report.py`](../../scripts/work_report.py) reads
the facts: merged pull requests, who made, reviewed and approved each one,
the issues they closed, releases, GitHub milestones, the `Spec:` lines on
closed issues, each one's type label, and the repo's [`CHANGELOG.md`](../../CHANGELOG.md) as merged on GitHub's default
branch. It also prints what to watch.
You add the summary, from those numbers only.

It names people. Its last section lists every pull request with its number,
title, address, author and reviewers by GitHub login, because a lead reads it
to see who did what. Say so when you hand it over, and the people it names
should be able to read the same report.

Two things a reader needs told. Loop-built pull requests count as the login
the loop runs as, since the loop opens them as that account. And a review
counts only when it's on GitHub: someone who read a pull request and merged it
without leaving a review shows as nobody else reviewing it.

## Steps

1. **Pick the repo and the period.** This repo by default, or a repo
   under [`projects/`](../../projects/) by its folder name. Ask for the period, and default to
   the last 14 days. One repo per report. Repos for different customers never
   go into one report for anyone but the person running it:
   [`steering/data-and-tools.md`](../../steering/data-and-tools.md) has why.
2. **Run the script:**

   ```bash
   python3 scripts/work_report.py --since <YYYY-MM-DD>
   python3 scripts/work_report.py --since <YYYY-MM-DD> --project <name>
   ```

   It prints the facts as Markdown. A section that says `Not available` stays
   that way in the report, with its reason. For `gh unavailable`, check
   `gh auth status`; any other reason says what it couldn't read. Don't fill a
   gap from memory.
3. **Write the report** to `reports/work/<since>-to-<until>-<repo>.md`, with
   the dates as YYYY-MM-DD and the repo's name after its `/`:
   - The script's title line.
   - `## Summary`: three to five sentences. Lead with what was delivered (the
     releases and milestones closed), then how much merged and how much the
     loop built, then who. Every figure in it is one the script printed; don't
     work out a new one.
   - The script's output as printed, from the line after its title to the end.
     `## To watch` is already in it. The `## Merges` chart is a Mermaid
     `xychart-beta` block: GitHub draws it, and VS Code's Markdown preview
     needs a Mermaid extension to.

   Describe the work, never the person: no "productive", "slow" or ranking.
4. **Have them read it.** Name what it holds that others will see: GitHub
   logins, pull request titles and addresses.
5. **Say how to share it.** It stays in [`reports/work/`](../../reports/work/), gitignored, and they
   send it. If they want it as a page or a post, that's a publish, and it
   waits for their yes to that one step. Run the `reviewer` agent on it first.

## Making milestones and specs show up

The report counts only what GitHub records, so a team gets out of it what it
puts in:

- **A deliverable is a GitHub milestone.** Name it after the deliverable or
  goal, put its issues on it, and close it when they're done. The report lists
  it on the day it closed, with how many of its issues were done and
  its due date, and To watch says when it closed late or with issues open.
  Open ones are listed with their progress, and flagged once past due.
- **A release is a milestone too.** `gh release create` records it.
- **An issue names its spec** with one line in its References section:
  `Spec: docs/specs/004-search REQ-002`. The path is the spec; what follows
  it is free text, so several requirements of one spec count together.
- **A type is a label:** exactly one of `bug`, `enhancement`,
  `documentation` or `chore` on each issue, per [`steering/tickets.md`](../../steering/tickets.md). A pull
  request takes its own label's type, or else its closed issue's, and
  otherwise counts as untyped. It's never guessed from a branch or a title.
- **Loop work needs nothing.** The script knows it by the loop's branch,
  `loop/issue-N`.

A CHANGELOG entry is what shipped, in words. It's never counted as a
milestone.

## Rules

- Every figure in the report comes from the script's output.
- Never put an issue's or a pull request's body, a commit message or an email
  address in the report.
- Never commit a report, force-add it, or send it anywhere. They send it.
- Change nothing on GitHub: no labels, comments or milestones.

## Output

The report file, read by the person it's for, and its path.
