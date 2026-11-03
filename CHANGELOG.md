# What's new

Newest first. Each entry has a dated heading with a short name that never
changes, what it adds, the files it touched, and **Do:** what you need to do to
take it. Ask the agent "what's new" and [`skills/whats-new/`](skills/whats-new/) reads this, and your
remote's copy, and tells you what you don't have yet.

Changing your own harness? Any noticeable change gets an entry at the top, in
the same change, not later. Then "what's new" works for your team too.
Noticeable means:

- **Something new:** a skill, a steering file, a gate, a hook, an agent, a
  check, a folder people are meant to use
- **Something that works differently:** a skill or gate that now does more,
  less or something else, a rule that got stricter or looser
- **Something that moved:** a file renamed or relocated, so old paths break
- **Anything with a Do:** if someone has to run a command or edit a file to
  take it, it needs an entry whatever its size

Typo fixes, rewording, tests on their own and tidying inside a file don't. The
test: would someone who copied the harness last week want to know, or need to
act? If you're unsure, write the entry.

One entry per change someone would name, not per commit: three files that add
one feature are one entry. The heading is `## YYYY-MM-DD: Name`, and the name
never changes once it's written, because copies are compared by it. Under it:
what it adds in a sentence or two, the files, and a **Do:** line ("nothing" is
fine).

## 2026-11-03: Harness-report is now harness-trends

The `harness-report` skill is now `harness-trends`. It does the same as before, and the phrases in its description, such as "my harness report", "sprint follow-up" and "how many tokens", still reach it. `/harness-trends` replaces `/harness-report`.
Files: [`skills/harness-trends/SKILL.md`](skills/harness-trends/SKILL.md), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`skills/starter-updates/capabilities.md`](skills/starter-updates/capabilities.md), [`reports/usage/README.md`](reports/usage/README.md), [`.claude/hooks/usage_log.py`](.claude/hooks/usage_log.py), [`scripts/usage_report.py`](scripts/usage_report.py), [`scripts/token_report.py`](scripts/token_report.py), [`scripts/plugin_report.py`](scripts/plugin_report.py), [`tests/test_skills.py`](tests/test_skills.py), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** run `git mv skills/harness-report skills/harness-trends`, then take the starter's files over it, taking [`tests/test_skills.py`](tests/test_skills.py) and the lines naming the skill in [`AGENTS.md`](AGENTS.md), [`README.md`](README.md), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`skills/starter-updates/capabilities.md`](skills/starter-updates/capabilities.md), [`reports/usage/README.md`](reports/usage/README.md), [`.claude/hooks/usage_log.py`](.claude/hooks/usage_log.py), [`scripts/usage_report.py`](scripts/usage_report.py), [`scripts/token_report.py`](scripts/token_report.py) and [`scripts/plugin_report.py`](scripts/plugin_report.py) in the same step.

## 2026-11-03: Propose a pulse question

A pulse question can now be asked on one date only: give it a `Date:` line, and every other day still gets the undated questions in turn, so adding a dated question shifts no other day. `python3 scripts/pulse.py propose --file <path> --date YYYY-MM-DD` adds one to the end of `questions.md`, and changes nothing if the date isn't after today, the id is already in the bank, or the bank with it would fail `check`. `check` now also reports a date that isn't a real YYYY-MM-DD, two questions on one date, and a bank with no undated question.
Files: [`scripts/pulse.py`](scripts/pulse.py), [`tests/test_pulse.py`](tests/test_pulse.py), [`skills/pulse/README.md`](skills/pulse/README.md), [`skills/pulse/questions.example.md`](skills/pulse/questions.example.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** nothing.

## 2026-11-03: Mod test failures by name

When a mod's tests fail, [`tests/test_mods.py`](tests/test_mods.py) now reports every failing test's name, its file and its error, wherever it falls in the output, instead of the last 40 lines.
Files: [`tests/test_mods.py`](tests/test_mods.py), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** nothing.

## 2026-11-02: Loop history in the dashboard data

`python3 scripts/dashboard_data.py --json` now prints a `loop_history` section: every loop run that ended since `--since`, for the harness and each project, with its outcome, rounds, tests, verdicts and cost, and counts of each outcome by day. The dashboard pane doesn't draw it yet.
Files: [`scripts/dashboard_data.py`](scripts/dashboard_data.py), [`tests/test_dashboard_data.py`](tests/test_dashboard_data.py), [`examples/mods/harness-dashboard/hooks/sample.ts`](examples/mods/harness-dashboard/hooks/sample.ts), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** nothing.

## 2026-11-02: Time per step

Each issue's row in `.loop/status.json` now records how long the current run spent on each step: `step_started` says when the current step began, and `step_seconds` holds the whole seconds per step, with rounds summed. It covers the current run only, and `loop.log` and `.loop/history.jsonl` are unchanged.
Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md).

**Do:** nothing. A running loop picks it up when it's next started.

## 2026-11-02: Project focus

`/project <name>` puts one project under [`projects/`](projects/) in focus for the session: the GitHub line shows that project's repo with `<name>: ` at the start, in every state, and the model is told that an unnamed "the project" means that one. `/project off` clears it and `/project` says which it is. The focus is one file per session, `.harness/project/<id>`, which a `/clear` leaves behind and doesn't carry over, and the 15-second timer now runs whether or not the harness has a GitHub remote, and reads the file each time. The mod now writes that file, where it only read before.
Files: [`examples/mods/github-status/`](examples/mods/github-status/), [`AGENTS.md`](AGENTS.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** `/plugin update github-status@sanvio-harness-starter`, then `/reload-plugins` or a new session.

## 2026-11-02: Safer harness eval runs

A harness eval run can no longer be redirected by an agent editing its record: what a run acts on is sealed in `~/.harness-evals`, and the suite's path is kept only there. Scoring gets an empty home and no `gh` login, and reads each pull request from a `PR_DATA` file. Ctrl-C now ends the start command too, and `resume --end` scores an interrupted run. A failed start's pull request is now scored.
Files: [`scripts/eval_harness.py`](scripts/eval_harness.py), [`tests/test_eval_harness.py`](tests/test_eval_harness.py), [`examples/eval-suite/README.md`](examples/eval-suite/README.md), [`docs/specs/002-harness-evals/TASKS.md`](docs/specs/002-harness-evals/TASKS.md).

**Do:** if your own suite's `key/score` calls `gh` for pull request details, read them from `PR_DATA` instead, since scoring now has no `gh` login.

## 2026-11-02: Loop crew lanes

`/loop-crew`'s pane is now a board of lanes in place of the floor: a header naming the loop's steps left to right, then a lane for each issue being worked on, its words over a rail with a node at each step. Each issue's figure runs along its lane to its step when the step changes and works there, beside a small drawing of the work, and runs off the end when its pull request opens. The rail is lit in the steps' colours up to where the figure is going, and on a terminal it lights up behind the figure as it runs. The board matches the session's light or dark theme as of when the session started. On a terminal the board fits the pane's width and shows the lanes that fit, up to 8, and `/loop-crew` asks for room for three. It has been seen only in Claude Code run in VS Code's integrated terminal, against a pretend loop. The VS Code extension, Claude Desktop and the mobile app haven't been tried.
Files: [`examples/mods/loop-crew/`](examples/mods/loop-crew/), [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md), [`skills/starter-updates/capabilities.md`](skills/starter-updates/capabilities.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** `/plugin update loop-crew@sanvio-harness-starter`, then `/reload-plugins` or a new session.

## 2026-11-02: Harness evals

[`scripts/eval_harness.py`](scripts/eval_harness.py) runs a harness through a suite of jobs in a new private repo, then scores the result with hidden tests and traps: tests passed, traps avoided, time, stops, build rounds, tokens and cost. `compare` names what changed between two runs, `validate` checks a suite is a fair test without spending tokens, and `list` names the run repos, which only a person deletes. Merging between issues is off unless you pass `--merge-in-run-repo`.
Files: [`scripts/eval_harness.py`](scripts/eval_harness.py), [`tests/test_eval_harness.py`](tests/test_eval_harness.py), [`examples/eval-suite/`](examples/eval-suite/), [`docs/specs/002-harness-evals/SPEC.md`](docs/specs/002-harness-evals/SPEC.md), [`README.md`](README.md), [`AGENTS.md`](AGENTS.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** nothing. To try it, read [`examples/eval-suite/README.md`](examples/eval-suite/README.md).
## 2026-11-01: Loop crew map

`/loop-crew`'s pane now draws a map of a work floor with a station for each loop step: a door, a planning table, a test bench, a workbench, a review desk and a loading dock. Each issue being worked on is a small figure that walks to its step's station when the step changes and acts out the work there, and walks back to the door when its pull request opens. A legend under the floor lists the issues. The terminal paints the floor in place, wide or compact to fit, and the other surfaces animate an Svg. It hasn't yet been tried on any surface.
Files: [`examples/mods/loop-crew/`](examples/mods/loop-crew/), [`AGENTS.md`](AGENTS.md), [`skills/starter-updates/capabilities.md`](skills/starter-updates/capabilities.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** `/plugin update`, then `/reload-plugins` or a new session, picks it up.

## 2026-10-31: Loop crew

A new mod: `/loop-crew` opens a pane with an animated figure for each issue the loop is working on, acting out its step: at a drafting board, writing on a board, swinging a hammer, holding up a magnifying glass or carrying a box. `/loop-crew <project>` shows a project's loop. It only reads the loop's files and spends no model tokens. The terminal paints the frames in place and the other surfaces animate an Svg. It hasn't yet been tried on any surface, and the animation on the mobile app is expected but untried.
Files: [`examples/mods/loop-crew/`](examples/mods/loop-crew/), [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json), [`.claude/settings.json`](.claude/settings.json), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md), [`skills/starter-updates/capabilities.md`](skills/starter-updates/capabilities.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** `/plugin install loop-crew@sanvio-harness-starter` or `/reload-plugins` picks it up.

## 2026-10-31: Decisions and requirement tests in loop pull requests

The loop's planner now writes a short Decisions section and plans tests for what a rule must not touch, and a pull request shows those Decisions above the folded plan. The loop's reviewer writes a table of each requirement and its test from the diff, and returns `VERDICT: FIX` when a requirement has no test. The must-not-touch rule is also in the building and testing steering. Behaviour the plan's requirements don't ask for gets a row too.
Files: [`scripts/loop.py`](scripts/loop.py), [`steering/building-and-testing.md`](steering/building-and-testing.md), [`CHANGELOG.md`](CHANGELOG.md), [`tests/test_loop.py`](tests/test_loop.py), [`tests/test_pulse.py`](tests/test_pulse.py).

**Do:** nothing.

## 2026-10-31: Loop pane running and queued counts

The line beside the loop pane's dropdown now counts the loops running a job and the live loops with ready issues waiting, the one on screen included (`● 2 running · 3 queued`), in place of `● 2 others working`.
Files: [`examples/mods/loop-pane/hooks/logic.ts`](examples/mods/loop-pane/hooks/logic.ts), [`examples/mods/loop-pane/hooks/register.tsx`](examples/mods/loop-pane/hooks/register.tsx), [`examples/mods/loop-pane/hooks/pane.test.ts`](examples/mods/loop-pane/hooks/pane.test.ts), [`examples/mods/loop-pane/README.md`](examples/mods/loop-pane/README.md), [`examples/mods/loop-pane/.claude-plugin/plugin.json`](examples/mods/loop-pane/.claude-plugin/plugin.json), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** `/plugin update`, then `/reload-plugins` or a new session, picks it up.

## 2026-10-31: Loop merges CHANGELOG.md conflicts

When a loop pull request stops merging only because `CHANGELOG.md` gained entries on its base, the idle loop merges the base in, keeps both sets of entries with the branch's on top, runs the tests, and pushes the merge if they pass, without a force. Any other conflict, an edited entry, a commit the loop didn't push or a worktree with changes logs an `UPDATE kept:` line and changes nothing. Failing tests push nothing and get one comment on the pull request, and each commit of the base is tried once per issue.
Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** restart the loop to use it: `python3 scripts/loop.py stop`, then start it again. It needs git 2.38 or later.

## 2026-10-31: Daily pulse question summary

Ask `/pulse` to summarise for leadership and it writes a period's answers, 14 days by default, to a gitignored report you read and send yourself. `python3 scripts/pulse.py summary` prints the same Markdown: for each date and question, how many answered, how many chose each option, and each Other answer quoted as written. It never prints a login or a file name, and it holds back a question fewer than three people answered.
Files: [`scripts/pulse.py`](scripts/pulse.py), [`skills/pulse/SKILL.md`](skills/pulse/SKILL.md), [`skills/pulse/README.md`](skills/pulse/README.md), [`reports/pulse/README.md`](reports/pulse/README.md), [`.gitignore`](.gitignore), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md), [`skills/starter-updates/capabilities.md`](skills/starter-updates/capabilities.md), [`CHANGELOG.md`](CHANGELOG.md), [`tests/test_pulse_summary.py`](tests/test_pulse_summary.py).

**Do:** nothing beyond the existing folder setup.

## 2026-10-31: Daily pulse question

Say "pulse" and a team answers one multiple-choice question a day from a shared synced folder, with no server or connector. Each person's answers land in a file named after their login in that folder, anyone with the folder can read them, and `results` prints counts only. Standup mentions the day's question where `company/DATA.md` clears the folder.
Files: [`scripts/pulse.py`](scripts/pulse.py), [`skills/pulse/SKILL.md`](skills/pulse/SKILL.md), [`skills/pulse/README.md`](skills/pulse/README.md), [`skills/pulse/questions.example.md`](skills/pulse/questions.example.md), [`skills/standup/SKILL.md`](skills/standup/SKILL.md), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md), [`skills/starter-updates/capabilities.md`](skills/starter-updates/capabilities.md), [`CHANGELOG.md`](CHANGELOG.md), [`tests/test_pulse.py`](tests/test_pulse.py).

**Do:** nothing to leave it off. To use it, set `HARNESS_PULSE_FOLDER` in your shell profile, add a `Pulse folder` row to `company/DATA.md`, and copy [`skills/pulse/questions.example.md`](skills/pulse/questions.example.md) into the folder as `questions.md`.

## 2026-10-31: Loop pane dropdown from two loops

The loop pane's row of loop buttons is now a dropdown whenever there's more than one loop in the terminal, VS Code and Claude Desktop, instead of only past four. The mobile app, which draws no dropdown, keeps the buttons.
Files: [`examples/mods/loop-pane/hooks/register.tsx`](examples/mods/loop-pane/hooks/register.tsx), [`examples/mods/loop-pane/hooks/logic.ts`](examples/mods/loop-pane/hooks/logic.ts), [`examples/mods/loop-pane/hooks/pane.test.ts`](examples/mods/loop-pane/hooks/pane.test.ts), [`examples/mods/loop-pane/README.md`](examples/mods/loop-pane/README.md), [`examples/mods/loop-pane/.claude-plugin/plugin.json`](examples/mods/loop-pane/.claude-plugin/plugin.json), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** `/plugin update`, then `/reload-plugins` or a new session, picks it up.

## 2026-10-31: Tester writes new files only

With `test_first` on, the tester may only add new files: [`scripts/loop.py`](scripts/loop.py) blocks the issue if it changes or deletes a file that already existed. The planner now leaves those tests out of its plan, and the build can change any existing test file.
Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** nothing.

## 2026-10-31: Tests written first

With `test_first` on, a separate agent writes failing tests after the planner and before round 1, in a commit of their own, and the build has to make them pass without changing them. [`scripts/loop.py`](scripts/loop.py) blocks the issue if the tester changes nothing, changes a path outside `test_paths` or a lockfile, or its tests already pass, and if a build changes or deletes one of its files.
Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** nothing to leave it off. To turn it on, set "test_first": true in loop.json.

## 2026-10-31: Session retro

Ordinary sessions can now get the same retro the loop's lessons get. With `HARNESS_RETRO=on`, a hook on `SessionEnd` and `PreCompact` keeps a copy of the session's log in `local-data/retro/` when the person corrected the agent ("that's wrong", "not what I asked", "don't do that", "learn from that", or a message opening "no,") or one file was edited three or more times. Say "retro" and the `retro` skill has a fresh `claude` that can only read classify why the agent didn't know, from the loop's digest of the log plus what the person corrected; [`scripts/loop.py`](scripts/loop.py)'s checks drop what the log doesn't bear out, and the entry goes in `.loop/lessons.md`, headed `session`, for `learn`, naming each correction by its record rather than quoting it. A kept copy is deleted once read, and anything in `local-data/retro/` older than 30 days on the next session end, whether the switch is on or off. With none kept, `retro` reads the current session. Copies hold everything said in a session, are readable by their owner alone, and never leave the machine. The hook copies nothing unless git says `local-data/` is ignored, and [`scripts/loop.py`](scripts/loop.py) starts its agents with `HARNESS_RETRO=off`, so a loop run's session is never kept.
Files: [`.claude/hooks/session_retro.py`](.claude/hooks/session_retro.py), [`.claude/settings.json`](.claude/settings.json), [`skills/retro/SKILL.md`](skills/retro/SKILL.md), [`skills/learn/SKILL.md`](skills/learn/SKILL.md), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md), [`skills/starter-updates/capabilities.md`](skills/starter-updates/capabilities.md), [`scripts/loop.py`](scripts/loop.py), [`tests/test_session_retro.py`](tests/test_session_retro.py), [`tests/test_loop.py`](tests/test_loop.py), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** nothing to leave it off. To turn it on, set `HARNESS_RETRO=on` in your environment and start a new session.

## 2026-10-31: Check-starter is now starter-updates

The `check-starter` skill is now `starter-updates`, so its name says what it's for. What it does hasn't changed. "check the starter" still triggers it, and so does "starter updates".
Files: [`skills/starter-updates/SKILL.md`](skills/starter-updates/SKILL.md), [`skills/starter-updates/capabilities.md`](skills/starter-updates/capabilities.md), [`skills/review-skill/SKILL.md`](skills/review-skill/SKILL.md), [`tests/test_skills.py`](tests/test_skills.py), [`tests/test_changelog.py`](tests/test_changelog.py), [`README.md`](README.md), [`AGENTS.md`](AGENTS.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** run `git mv skills/check-starter skills/starter-updates`, then take the starter's files over it. Take [`tests/test_changelog.py`](tests/test_changelog.py), [`tests/test_skills.py`](tests/test_skills.py) and the lines naming the skill in [`AGENTS.md`](AGENTS.md), [`README.md`](README.md) and [`skills/review-skill/SKILL.md`](skills/review-skill/SKILL.md) in the same step.

## 2026-10-30: Check-starter asks what's worth bringing over

`check-starter` now reads a table of the starter's capabilities and asks, one question at a time, whether to bring over each one this copy lacks and whether to take updates to the ones it has. A copy level with the starter is still offered what it lacks. Its output opens with what you said yes to and the commands for it, and names what `cp` doesn't bring. Every commit is still listed, with the same answers, plus a note where you said no or left it undecided. The windows themselves aren't tested: the tests cover the table and the command that reads it.
Files: [`skills/check-starter/SKILL.md`](skills/check-starter/SKILL.md), [`skills/check-starter/capabilities.md`](skills/check-starter/capabilities.md), [`tests/test_skills.py`](tests/test_skills.py), [`tests/test_changelog.py`](tests/test_changelog.py), [`README.md`](README.md), [`AGENTS.md`](AGENTS.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** nothing.
## 2026-10-30: Loop plans carry the ticket's exact content

The loop's planner is now told that the build agent gets only the plan, so what a ticket gives exactly, such as a table's rows, paths, command text or required wording, goes in the plan word for word and marked as content. The 40-line limit now covers only the planner's own words. The ticket's wording now reaches the agent that writes files, as the planner's copy, with no cap on its length.
Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** a running loop needs `python3 scripts/loop.py stop`, then starting again, to pick this up.

## 2026-10-30: Loop setup command

`setup_command`, in the harness's `loop.json` or a project's own, runs once per worktree before the planner, such as `npm ci`, with the same environment and timeout as `test_command`. If it fails or times out, the issue blocks and its output stays on this machine, in `.loop/issue-N/setup-output.txt`. If it leaves anything git would commit, the issue blocks and the comment names the paths. On a branch that already has the loop's commits and no record of setup, it doesn't run. Empty, the default, runs nothing. It runs with no approval, so use a locked install.
Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** nothing, unless a project wants its packages installed before the agents start: then set `setup_command`. A running loop needs `python3 scripts/loop.py stop`, then starting again, to pick this up.

## 2026-10-30: Loop holds tickets that name the same file

With `max_workers` above 1, the loop no longer starts an issue whose ticket names, in backticks under Scope **In**, a file or folder that a running issue's ticket named. `CHANGELOG.md` doesn't count, since nearly every ticket names it. It logs `#13 HELD waits on #12 for src/app/main.py` once, shows `waiting_on` and `held_path` on the issue's queue row, and starts it once that worker ends. Ready issues that don't overlap still start, and a `--dry-run` with more than one worker prints a `HELD` line for each issue that overlaps its pick. A ticket that names no path runs as it did. The loop only knows what tickets name, not what else an agent edits.
Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`steering/tickets.md`](steering/tickets.md), [`.github/ISSUE_TEMPLATE/loop-task.md`](.github/ISSUE_TEMPLATE/loop-task.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** name exact files in backticks in a ticket's Scope **In**, with folders as `dir/` or `a/b`. A running loop needs `python3 scripts/loop.py stop`, then starting again, to pick this up.
## 2026-10-30: Loop retro classifies its lessons

With `"retro": true` in `loop.json`, each entry the loop writes to `.loop/lessons.md` also gets findings on why the lesson reached the agent late, `ABSENT`, `IGNORED`, `UNLOADED`, `WRONG` or `INHERENT`, each citing a record in the run's session logs and checked against them. `usage.json` entries now hold a `session_id` when the agent names one. [`skills/learn/`](skills/learn/) says where each cause's fix goes. With it unset, the loop does what it did. The log checks come from a made-up session log, so run one real retro before relying on the `(unverified)` marks.
Files: [`scripts/loop.py`](scripts/loop.py), [`skills/learn/SKILL.md`](skills/learn/SKILL.md), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`tests/test_loop.py`](tests/test_loop.py), [`tests/test_skills.py`](tests/test_skills.py), [`tests/fixtures/retro_session.jsonl`](tests/fixtures/retro_session.jsonl), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** nothing, and set `retro` to use it.
## 2026-10-30: Loop pane dropdown past four loops

Past four loops, the loop pane's row of loop buttons becomes a dropdown in the terminal, VS Code and Claude Desktop, with the loops working a job first and, beside it, how many other loops are working. Four or fewer keep their buttons, and so does the mobile app, which draws no dropdown.
Files: [`examples/mods/loop-pane/hooks/logic.ts`](examples/mods/loop-pane/hooks/logic.ts), [`examples/mods/loop-pane/hooks/register.tsx`](examples/mods/loop-pane/hooks/register.tsx), [`examples/mods/loop-pane/hooks/pane.test.ts`](examples/mods/loop-pane/hooks/pane.test.ts), [`examples/mods/loop-pane/README.md`](examples/mods/loop-pane/README.md), [`examples/mods/loop-pane/.claude-plugin/plugin.json`](examples/mods/loop-pane/.claude-plugin/plugin.json), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** `/plugin update`, then `/reload-plugins` or a new session, picks it up.

## 2026-10-30: Loop pane lists fill its height

The loop pane's lists now grow with the pane: at 60 rows **Active** and **Finished** show 7 jobs and **Queue** 49 issues, on the terminal in the same rows on every tab. They never drop below today's 3 jobs and 21 issues, and a pane that reports no height keeps those numbers. On Desktop and VS Code a short queue still holds only three lines open.
Files: [`examples/mods/loop-pane/hooks/logic.ts`](examples/mods/loop-pane/hooks/logic.ts), [`examples/mods/loop-pane/hooks/register.tsx`](examples/mods/loop-pane/hooks/register.tsx), [`examples/mods/loop-pane/hooks/pane.test.ts`](examples/mods/loop-pane/hooks/pane.test.ts), [`examples/mods/loop-pane/README.md`](examples/mods/loop-pane/README.md), [`examples/mods/loop-pane/.claude-plugin/plugin.json`](examples/mods/loop-pane/.claude-plugin/plugin.json), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** `/plugin update`, then `/reload-plugins` or a new session, picks it up.

## 2026-10-30: Loop pane tabs keep one height

The loop pane's **Queue** tab now takes the same 21 rows on the terminal as **Active** and **Finished**, so what's below the list stays put as you change tabs. **Queue** shows up to 21 issues instead of 3, and **▲ more**, **▼ more** and the wheel move it a line at a time. On Desktop and VS Code it shows up to 21 too, and a short queue still holds only three lines open.
Files: [`examples/mods/loop-pane/hooks/logic.ts`](examples/mods/loop-pane/hooks/logic.ts), [`examples/mods/loop-pane/hooks/register.tsx`](examples/mods/loop-pane/hooks/register.tsx), [`examples/mods/loop-pane/hooks/logic.test.ts`](examples/mods/loop-pane/hooks/logic.test.ts), [`examples/mods/loop-pane/hooks/pane.test.ts`](examples/mods/loop-pane/hooks/pane.test.ts), [`examples/mods/loop-pane/README.md`](examples/mods/loop-pane/README.md), [`examples/mods/loop-pane/.claude-plugin/plugin.json`](examples/mods/loop-pane/.claude-plugin/plugin.json), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** `/plugin update`, then `/reload-plugins` or a new session, picks it up.

## 2026-10-30: Open a pull request from the loop pane

A job's button on the loop pane is now **Open pull request** instead of **Copy pull request link**, and it opens the link in the browser. It copies the link instead, and says so, when the link isn't an `https://` link or no browser opens.
Files: [`examples/mods/loop-pane/hooks/logic.ts`](examples/mods/loop-pane/hooks/logic.ts), [`examples/mods/loop-pane/hooks/register.tsx`](examples/mods/loop-pane/hooks/register.tsx), [`examples/mods/loop-pane/hooks/pane.test.ts`](examples/mods/loop-pane/hooks/pane.test.ts), [`examples/mods/loop-pane/README.md`](examples/mods/loop-pane/README.md), [`examples/mods/loop-pane/.claude-plugin/plugin.json`](examples/mods/loop-pane/.claude-plugin/plugin.json), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** `/plugin update`, then `/reload-plugins` or a new session, picks it up.

## 2026-10-30: `/loop-pane` closes a showing pane

`/loop-pane` now closes the pane when it's showing, and says so. A pane behind another or not placed still opens. Because the command no longer reopens a showing pane, the loop you're on stays until you press another or close and reopen the pane, which picks again.
Files: [`examples/mods/loop-pane/hooks/register.tsx`](examples/mods/loop-pane/hooks/register.tsx), [`examples/mods/loop-pane/hooks/pane.test.ts`](examples/mods/loop-pane/hooks/pane.test.ts), [`examples/mods/loop-pane/README.md`](examples/mods/loop-pane/README.md), [`examples/mods/loop-pane/.claude-plugin/plugin.json`](examples/mods/loop-pane/.claude-plugin/plugin.json), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** `/plugin update`, then `/reload-plugins` or a new session, picks it up.

## 2026-10-30: Activity after a session moves into projects

A session started at the harness's root now keeps counting by subagent type, skill and slash command after it moves into [`projects/`](projects/), and so do its subagents. A session started under [`projects/`](projects/) still stays out. The figures in `## By activity` in [`scripts/token_report.py`](scripts/token_report.py)'s report and the dashboard's spend columns can go up, and `.harness/cache/activity.json` is replaced on the first dashboard read once it's over 15 minutes old.
Files: [`scripts/token_report.py`](scripts/token_report.py), [`tests/test_token_report.py`](tests/test_token_report.py), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** nothing.

## 2026-10-30: Generated files in the loop's commit

The loop now runs a new `generate_command` after each build and before the commit, so files the build agent can't make itself land in that round's commit and count as a change. The harness's runs `UPDATE_SAMPLE=1 python3 -m unittest tests.test_dashboard_data.Sample; python3 scripts/draw_dashboard.py`; a project's is empty unless its own `loop.json` sets it. It gets the same environment and timeout as `test_command`, and one that fails logs a `GENERATE` line and the round goes on. The plan, build and review prompts say what it does when it's set. [`scripts/check_mod_versions.py`](scripts/check_mod_versions.py) no longer counts a change to a mod's `hooks/sample.ts`, since only tests read it.
Files: [`scripts/loop.py`](scripts/loop.py), [`scripts/check_mod_versions.py`](scripts/check_mod_versions.py), [`tests/test_loop.py`](tests/test_loop.py), [`tests/test_mod_versions.py`](tests/test_mod_versions.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md), [`steering/tickets.md`](steering/tickets.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** restart a running loop (`python3 scripts/loop.py stop`, then start it again) to use it.

## 2026-10-30: Dependencies met on a non-default base

A dependency now counts as met when a merged pull request into `base` says in its body that it closes it, because GitHub fills in the closing references only for the default branch. The loop reads the 200 most recently opened pull requests merged into `base`, so an older dependency is refused until someone takes the `Depends on` line out.
Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`CHANGELOG.md`](CHANGELOG.md).

**Do:** restart a running loop (`python3 scripts/loop.py stop`, then start it again) to use it.

## 2026-10-30: Working loops on the loop pane's buttons

The loop pane's buttons now show which loops are working, on screen or not: `● app` for a loop on one job and `● app 2` from two up, counted the same way as the header's **Running**. A loop with no live lock shows its name alone.
Files: [`examples/mods/loop-pane/hooks/logic.ts`](examples/mods/loop-pane/hooks/logic.ts), [`examples/mods/loop-pane/hooks/register.tsx`](examples/mods/loop-pane/hooks/register.tsx), [`examples/mods/loop-pane/README.md`](examples/mods/loop-pane/README.md), [`examples/mods/loop-pane/.claude-plugin/plugin.json`](examples/mods/loop-pane/.claude-plugin/plugin.json), [`examples/mods/loop-pane/hooks/logic.test.ts`](examples/mods/loop-pane/hooks/logic.test.ts), [`examples/mods/loop-pane/hooks/pane.test.ts`](examples/mods/loop-pane/hooks/pane.test.ts).

**Do:** `/plugin update`, then `/reload-plugins` or a new session, picks it up.

## 2026-10-30: Project loops in the loop pane

The loop pane now shows loops started with `--project`, not only the harness's. With more than one loop, a row of buttons above the tabs switches between them; `/loop-pane` opens on the first one running, the harness first, and the loop you pick stays. An issue reaching an end in any loop raises a toast, a project's starting with its name.
Files: [`examples/mods/loop-pane/hooks/logic.ts`](examples/mods/loop-pane/hooks/logic.ts), [`examples/mods/loop-pane/hooks/register.tsx`](examples/mods/loop-pane/hooks/register.tsx), [`examples/mods/loop-pane/types/index.d.ts`](examples/mods/loop-pane/types/index.d.ts), [`examples/mods/loop-pane/README.md`](examples/mods/loop-pane/README.md), [`examples/mods/loop-pane/.claude-plugin/plugin.json`](examples/mods/loop-pane/.claude-plugin/plugin.json), [`examples/mods/loop-pane/hooks/logic.test.ts`](examples/mods/loop-pane/hooks/logic.test.ts), [`examples/mods/loop-pane/hooks/pane.test.ts`](examples/mods/loop-pane/hooks/pane.test.ts).

**Do:** reopen `/loop-pane`, or reload mods.

## 2026-10-30: Quoted command tags don't count

The token report and the dashboard's Activity section no longer count a `<command-name>` tag quoted in a
prompt as a slash command. The tag now has to open the line, after at most one `<command-message>` block, and hold
one command-shaped word, and a prompt quoting one closes the open span like any other prompt. An existing
`.harness/cache/activity.json` can show the old names for up to 15 minutes.
Files: [`scripts/token_report.py`](scripts/token_report.py), [`tests/test_token_report.py`](tests/test_token_report.py).

**Do:** nothing.

## 2026-10-30: Activity tokens and estimated cost in the pane

The harness dashboard's **Activity** section now shows **Tokens** and **Est. cost** beside **Times** for
each skill, agent and slash command, with **?** where there's no figure, never $0.00. Lines under the
tables say the cost is an estimate from `.harness/prices.json`, when its prices were checked and when the
figures were worked out. With no price file, they also say to fill one. What the guard refused keeps its two columns.
A read that works those figures out again takes longer, including each time you pick another range; the mod's README has the times.
Files: [`examples/mods/harness-dashboard/`](examples/mods/harness-dashboard/), [`docs/harness-dashboard.svg`](docs/harness-dashboard.svg).

**Do:** if you installed the mod, `/plugin update`, then `/reload-plugins` or a new session, picks it up. To get dollars, follow the price-file step in
*Tokens and cost per activity item*, below.

## 2026-10-30: Tokens and cost per activity item

`dashboard_data.py`'s `activity` section now also says what each skill, agent and slash command spent:
`skill_spend`, `agent_spend` and `command_spend`, each name's tokens and estimated dollars, with
`unpriced`, `prices_checked` and `spend_at`. Dollars come from a price file you keep yourself, and stay
null, with the reason under `unpriced`, for a model it doesn't price. The split of the transcripts is kept
for 15 minutes in `.harness/cache/activity.json`. The pane doesn't show the new fields yet.
Files: [`scripts/dashboard_data.py`](scripts/dashboard_data.py), [`scripts/prices.example.json`](scripts/prices.example.json), [`tests/test_dashboard_data.py`](tests/test_dashboard_data.py), [`examples/mods/harness-dashboard/`](examples/mods/harness-dashboard/).

**Do:** to get dollars, copy [`scripts/prices.example.json`](scripts/prices.example.json) to `.harness/prices.json` and put in the
models you use, in dollars per million tokens, from your provider's price list. Its figures are an
example, not real prices.

## 2026-10-29: Tokens by agent, skill and command

The token report has a new section, `## By activity`, for conversations at the harness's root: runs
and tokens for each subagent type, each skill and each slash command. A subagent's tokens are
measured from its own transcript; a skill's or command's are attributed from where it started to the
next prompt you typed. Repos under [`projects/`](projects/) and the loop's worktrees are left out.
Files: [`scripts/token_report.py`](scripts/token_report.py), [`tests/test_token_report.py`](tests/test_token_report.py).

**Do:** nothing. The harness report prints the new section.

## 2026-10-29: Tickets carry a type label

Every issue now carries exactly one type label: `bug`, `enhancement`, `documentation` or `chore`
(maintenance). It's on the list of what makes a ticket ready for the loop, and `loop-control` checks
for it and adds one with the ready label. The work report counts merged work by type, a pull request
taking its own label's type or else its closed issue's, and says how much has none.
Files: [`steering/tickets.md`](steering/tickets.md), [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md), [`.github/ISSUE_TEMPLATE/loop-task.md`](.github/ISSUE_TEMPLATE/loop-task.md),
[`scripts/work_report.py`](scripts/work_report.py), [`skills/work-report/SKILL.md`](skills/work-report/SKILL.md).

**Do:** add the fourth label if your repo doesn't have it: `gh label create chore --description
"Maintenance: dependencies, tooling, tidying"`. GitHub made the other three with the repo. Then put a
type on open issues as you touch them.

## 2026-10-29: Work report

Say "work report" or "what did we ship" for one page on a repo over a period, built from what GitHub
recorded: pull requests merged and who made, reviewed and approved them, how many the loop built
(known by its `loop/issue-N` branch), releases and closed GitHub milestones, the specs closed issues
name on a `Spec:` line, the CHANGELOG's entries, a chart of merges by day (by week past a month),
and what to watch, such as work nobody but its author approved or a milestone past due. The skill
adds a summary from those numbers only. Milestones are only what GitHub records, so a deliverable
shows up when its GitHub milestone closes. Unlike the other reports, it names people by GitHub
login and lists every pull request. Reports stay gitignored in [`reports/work/`](reports/work/). A ticket's
References can now carry a `Spec:` line naming the spec it builds.
Files: [`scripts/work_report.py`](scripts/work_report.py), [`skills/work-report/`](skills/work-report/), [`reports/work/README.md`](reports/work/README.md),
[`tests/test_work_report.py`](tests/test_work_report.py), [`steering/tickets.md`](steering/tickets.md), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md),
[`.gitignore`](.gitignore).

**Do:** nothing to take it. To see deliverables in it, put each one's issues on a GitHub milestone,
and name an issue's spec with a `Spec:` line in its References.

## 2026-10-28: Mods find the harness after a /clear

`/loop-pane`, `/harness-dashboard` and `/github <project>` now work after a `/clear`. Each mod saves
the session's folder at `session.start`, and a `/clear` starts a new session without one, so
`/loop-pane` said there was no [`scripts/loop.py`](scripts/loop.py). When the saved folder is missing or leads to no
harness, they now look from the session's root instead, so a session without a `/clear` behaves as
before. `/loop-pane` and `/harness-dashboard` name the folder they looked from when they find none.
The harness lens gets the same fallback, but it still builds its picture only at `session.start`.
Files: [`examples/mods/loop-pane/`](examples/mods/loop-pane/), [`examples/mods/harness-dashboard/`](examples/mods/harness-dashboard/),
[`examples/mods/github-status/`](examples/mods/github-status/), [`examples/mods/harness-lens/`](examples/mods/harness-lens/).

**Do:** nothing. `/plugin update`, then `/reload-plugins` or a new session, picks it up.

## 2026-10-28: Loop help shows example commands

`python3 scripts/loop.py --help` now ends with three example commands: `run --once`, `review --once`
and `stop`. Each subcommand's own help is unchanged.
Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py).

**Do:** nothing.

## 2026-10-28: Build agent says why before each step

The loop's build agent now says, in a line, what it's about to do and why before each step, so an
issue's window shows its reasoning as well as its tool calls. `claude -p` sends no thinking text, so
this is the way to see it.
Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py).

**Do:** restart a running loop (`python3 scripts/loop.py stop`, then start it again) to use it.

## 2026-10-28: Guard lets code read a key property

[`.claude/hooks/guard.py`](.claude/hooks/guard.py) no longer refuses a shell command for code like `s.key)`: a `.key` file named with
one character counts only in a path. `server.key`, `config/a.key` and the like are still refused.
Files: [`.claude/hooks/guard.py`](.claude/hooks/guard.py), [`tests/test_agent_hooks.py`](tests/test_agent_hooks.py).

**Do:** nothing.

## 2026-10-28: Dashboard picture keeps to its own run

[`scripts/draw_dashboard.py`](scripts/draw_dashboard.py) stops, naming the file, when the test file it writes for a run is
already there, rather than writing over another run's and deleting it. [`.gitignore`](.gitignore) keeps that file out
of a commit when a killed run leaves it behind.
Files: [`scripts/draw_dashboard.py`](scripts/draw_dashboard.py), [`tests/test_draw_dashboard.py`](tests/test_draw_dashboard.py), [`.gitignore`](.gitignore).

**Do:** if it says the file is already there and no run is going, delete it.

## 2026-10-28: Tickets check a tool claim first

[`steering/tickets.md`](steering/tickets.md) now says to check, by running it, any claim a ticket makes about how a tool or
runtime behaves before the ticket rests on it, and to say in the ticket how it was checked.
Files: [`steering/tickets.md`](steering/tickets.md).

**Do:** nothing.

## 2026-10-28: Dashboard picture from the pane

[`scripts/draw_dashboard.py`](scripts/draw_dashboard.py) redraws the harness dashboard README's picture, [`docs/harness-dashboard.svg`](docs/harness-dashboard.svg),
and its text version from what the pane draws for [`examples/mods/harness-dashboard/hooks/sample.ts`](examples/mods/harness-dashboard/hooks/sample.ts). [`tests/test_draw_dashboard.py`](tests/test_draw_dashboard.py)
fails when either is out of date, and skips without Claude Code, as CI does. So the picture reads like a
harness at work, [`tests/test_dashboard_data.py`](tests/test_dashboard_data.py)'s `Sample` now builds the sample from made-up inputs of its
own, with titles, model names and token counts of a real size, rather than the leak checks' fixtures.
The picture's header time is noon wherever it's drawn. The mod is now 0.1.4.
Files: [`scripts/draw_dashboard.py`](scripts/draw_dashboard.py), [`tests/test_draw_dashboard.py`](tests/test_draw_dashboard.py), [`tests/test_dashboard_data.py`](tests/test_dashboard_data.py),
[`examples/mods/harness-dashboard/hooks/picture.test.ts`](examples/mods/harness-dashboard/hooks/picture.test.ts), [`examples/mods/harness-dashboard/hooks/sample.ts`](examples/mods/harness-dashboard/hooks/sample.ts),
[`examples/mods/harness-dashboard/README.md`](examples/mods/harness-dashboard/README.md), [`examples/mods/harness-dashboard/.claude-plugin/plugin.json`](examples/mods/harness-dashboard/.claude-plugin/plugin.json),
[`docs/harness-dashboard.svg`](docs/harness-dashboard.svg).

**Do:** after changing how the dashboard pane draws, or writing its sample again, run
`python3 scripts/draw_dashboard.py` from the root.

## 2026-10-28: Dashboard says when its script is newer

[`scripts/dashboard_data.py`](scripts/dashboard_data.py) now prints `"schema": 1` first, a number that goes up when a section's shape
changes in a way an older pane would misread. When the script's schema is higher than the one the
harness dashboard reads, the pane draws a yellow line under its header saying to run `/plugin update`,
and still draws every section. A script with no schema draws as before. The mod is now 0.1.3.
Files: [`scripts/dashboard_data.py`](scripts/dashboard_data.py), [`tests/test_dashboard_data.py`](tests/test_dashboard_data.py),
[`examples/mods/harness-dashboard/hooks/logic.ts`](examples/mods/harness-dashboard/hooks/logic.ts), [`examples/mods/harness-dashboard/hooks/register.tsx`](examples/mods/harness-dashboard/hooks/register.tsx),
[`examples/mods/harness-dashboard/hooks/logic.test.ts`](examples/mods/harness-dashboard/hooks/logic.test.ts), [`examples/mods/harness-dashboard/hooks/sample.ts`](examples/mods/harness-dashboard/hooks/sample.ts),
[`examples/mods/harness-dashboard/.claude-plugin/plugin.json`](examples/mods/harness-dashboard/.claude-plugin/plugin.json).

**Do:** nothing. When you change a section's shape in `dashboard_data.py`, raise `SCHEMA` there and in
the mod's `logic.ts` together.

## 2026-10-28: Dashboard sample from build()

The harness dashboard's tests now also draw [`examples/mods/harness-dashboard/hooks/sample.ts`](examples/mods/harness-dashboard/hooks/sample.ts), what
[`scripts/dashboard_data.py`](scripts/dashboard_data.py)'s `build()` prints for made-up inputs that fill every section. [`tests/test_dashboard_data.py`](tests/test_dashboard_data.py)'s `Sample`
fails when `build()` no longer prints that sample, so a renamed or moved field can't reach the pane
unnoticed, and `sample.test.ts` fails when the pane can't read one. The mod is now 0.1.2.
Files: [`tests/test_dashboard_data.py`](tests/test_dashboard_data.py), [`examples/mods/harness-dashboard/hooks/sample.ts`](examples/mods/harness-dashboard/hooks/sample.ts),
[`examples/mods/harness-dashboard/hooks/sample.test.ts`](examples/mods/harness-dashboard/hooks/sample.test.ts),
[`examples/mods/harness-dashboard/.claude-plugin/plugin.json`](examples/mods/harness-dashboard/.claude-plugin/plugin.json).

**Do:** after changing what `dashboard_data.py` prints, run
`UPDATE_SAMPLE=1 python3 -m unittest tests.test_dashboard_data.Sample` to write the sample again,
then `claude plugin test harness-dashboard` from [`examples/mods/`](examples/mods/).

## 2026-10-27: Dashboard tables stack in a narrow pane

In a pane too narrow to leave 8 columns for a table's names, the harness dashboard puts each row's
figures on a line under its name, in the row's colour, instead of cutting the name to a few letters.
Wider panes look as they did. The mod goes to 0.1.1. Touches [`examples/mods/harness-dashboard/hooks/register.tsx`](examples/mods/harness-dashboard/hooks/register.tsx)
and [`examples/mods/harness-dashboard/.claude-plugin/plugin.json`](examples/mods/harness-dashboard/.claude-plugin/plugin.json).

**Do:** nothing.

## 2026-10-27: Harness dashboard pane

A new mod, [`examples/mods/harness-dashboard/`](examples/mods/harness-dashboard/): `/harness-dashboard` opens a pane that draws
[`scripts/dashboard_data.py`](scripts/dashboard_data.py) `--json` as tables, with what's waiting on you first, then the loop's spend,
throughput and rework, evals and whether they're stale, Claude Code's tokens and the harness's activity.
Loop spend and Conversations start with a bar chart a day, each day's figures under its bar, which needs
the script from "Spend and conversation tokens by day"; a pane too narrow for each bar's figures labels
every 7th bar with its day. **7 days**, **14 days** and **30 days** pick the range, 14 by default. It
reads when it opens and every five minutes while it's open, and **Refresh** reads now; a refresh that fails keeps the last numbers and says so. It
spends no model tokens, calls GitHub through `gh` on each read, and writes only the script's caches in
`.harness/cache/`. It's off by default, and starts at 0.1.0.

Files: [`examples/mods/harness-dashboard/`](examples/mods/harness-dashboard/), [`docs/harness-dashboard.svg`](docs/harness-dashboard.svg), [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json),
[`AGENTS.md`](AGENTS.md), [`README.md`](README.md), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** nothing to keep things as they are. To try it, `claude --plugin-dir examples/mods/harness-dashboard`
from the root, or the two `/plugin` commands in its README's *Open it*.

## 2026-10-27: Spend and conversation tokens by day

[`scripts/dashboard_data.py`](scripts/dashboard_data.py) gains `by_day` in `loop_spend` and in each side of `conversations`:
every day from `--since` to today, oldest first, with its tokens, and for spend its `cost_usd`. A day
with nothing on it is 0, not left out. Both series cover the same days, in local time: a reply is
counted on the day it was where you are, so an evening west of UTC stays on its own day. The conversation
cache now keeps that local day too, so the first run after taking this reads every transcript again once.
`loop_spend` also gains `first_run`, the earliest day a run counted since `--since` started, or `null`. A section
that's `null` with a `why` has neither. Touches
[`scripts/dashboard_data.py`](scripts/dashboard_data.py), [`tests/test_dashboard_data.py`](tests/test_dashboard_data.py).

**Do:** nothing.

## 2026-10-27: Loop rework in the dashboard numbers

[`scripts/dashboard_data.py`](scripts/dashboard_data.py) gains a `loop_rework` section: how many of the loop's pull requests
(branch `loop/issue-N`) merged since `--since`, how many gained a commit without the loop's
`Loop: issue #` line, and each of those with its number, title, merges from main and other commits.
It reads them through `gh`, and is `null` with a `why` when `gh` fails. Each pull request's commits are
fetched once and cached in `.harness/cache/loop_rework.json`. Its pull request titles are printed,
as `waiting`'s are; a commit's message and author never are. Touches [`scripts/dashboard_data.py`](scripts/dashboard_data.py),
[`tests/test_dashboard_data.py`](tests/test_dashboard_data.py).

**Do:** nothing.

## 2026-10-27: What's waiting in the dashboard data

[`scripts/dashboard_data.py`](scripts/dashboard_data.py) gains a `waiting` section with two halves that fail on their own.
`pull_requests` is the harness repo's open pull requests from `gh`, each with its title, when it
opened, hours waited, its loop issue for a `loop/issue-N` branch, whether it's a draft, its checks
(`pass`, `fail`, `pending`, or `null` with none) and whether it conflicts; without `gh`, signed out or
on output it can't read, it's `null` with `why: "gh unavailable"`, never an empty list. `blocked` is
the issues in `status.json`, the harness's and each project's, whose state is blocked, with title,
note and last update. The rule that the output holds no title or note now has this one exception:
titles and notes appear under `waiting` and nowhere else; addresses, prompts and paths still never
appear. Touches [`scripts/dashboard_data.py`](scripts/dashboard_data.py), [`tests/test_dashboard_data.py`](tests/test_dashboard_data.py).

**Do:** nothing. Anything that reads the output and assumed it holds no titles should skip `waiting`.

## 2026-10-27: Stale eval results marked

[`scripts/dashboard_data.py`](scripts/dashboard_data.py)'s `evals` now says, for each reviewer's newest saved result, whether it is
stale: whether the agent's file in [`agents/`](agents/), [`scripts/eval_agents.py`](scripts/eval_agents.py), or a case's `case.json`, work file or
brief was committed, or edited and not yet committed, or written while git ignores it, after the result was saved. `changed` lists
those files from the harness root and `newest_change` gives the latest date. A result with no saved
time or no cases in its folder is stale with a `why`, and one git can't check has `stale: null`.
Touches [`scripts/dashboard_data.py`](scripts/dashboard_data.py), [`tests/test_dashboard_data.py`](tests/test_dashboard_data.py).

**Do:** nothing. To clear a stale result, run the eval again with `--save`.

## 2026-10-27: Conversation tokens in the dashboard numbers

[`scripts/dashboard_data.py`](scripts/dashboard_data.py) `--json` gains a `conversations` section: Claude Code's tokens since
`--since` from `~/.claude/projects`, counted as [`scripts/token_report.py`](scripts/token_report.py) counts them, split into
`harness` (the root and [`projects/`](projects/)) and `loop` (the loop's worktrees), each by model with a session
count. It keeps what it read in `.harness/cache/conversations.json`, which is gitignored, and reads a transcript again
only when its size or time changes. The cache holds per-reply ids, days, models,
session ids and counts under each transcript's path, never a prompt, a reply or a working folder.
[`scripts/token_report.py`](scripts/token_report.py) gains `read_file()`; its report is unchanged. Touches
[`scripts/dashboard_data.py`](scripts/dashboard_data.py), [`scripts/token_report.py`](scripts/token_report.py), [`tests/test_dashboard_data.py`](tests/test_dashboard_data.py),
[`tests/test_token_report.py`](tests/test_token_report.py).

**Do:** nothing.

## 2026-10-27: Dashboard numbers as JSON

[`scripts/dashboard_data.py`](scripts/dashboard_data.py) `--json` prints the numbers a dashboard needs as one JSON object: the
loop's estimated spend today, over the last 7 days and since `--since` (14 days by default), by issue,
step and model, with the cost per pull request over the issues that ran in that time; how many recent issues are in each state and how many
took more than one round; your usage log's skills, agents, commands, guard refusals and asks; and the
newest saved eval for each reviewer. A section whose source is missing or unreadable is `null` with a
`why`, and it still exits 0. It prints counts and names only, never a title, note, prompt or path.
[`scripts/token_report.py`](scripts/token_report.py) gains `loop_runs()`, which both scripts read the loop's records with; its
report is unchanged. Touches [`scripts/dashboard_data.py`](scripts/dashboard_data.py), [`scripts/token_report.py`](scripts/token_report.py),
[`tests/test_dashboard_data.py`](tests/test_dashboard_data.py).

**Do:** nothing.

## 2026-10-27: Eval results saved to .harness/evals/

`--save` with no file now writes [`scripts/eval_agents.py`](scripts/eval_agents.py)'s results to `.harness/evals/`, named for
the time and the reviewer, such as `2026-10-27T0930-reviewer.json`, and `--baseline latest` compares
with the newest file there for the same reviewer. Every saved file, named or not, now also holds
`reviewer`, `folder` and `saved`. `--save FILE` and `--baseline FILE` work as before. Either default
on a folder whose cases name more than one agent exits 2 before any session starts. Touches
[`scripts/eval_agents.py`](scripts/eval_agents.py), [`tests/test_eval_agents.py`](tests/test_eval_agents.py), [`examples/proposal/evals/README.md`](examples/proposal/evals/README.md).

**Do:** nothing, unless you kept results elsewhere and want `latest` to find them: move them into
`.harness/evals/`, such as `mv ~/harness-evals/*.json .harness/evals/`, and add a `"reviewer"` field
to each, such as `"reviewer": "reviewer"`. `latest` skips a file without one. It takes the last
file in name order, so name each one for when it ran, as `2026-10-01T0900-reviewer.json`.

## 2026-10-26: Loop pane shows each job's model

In the [loop pane](examples/mods/loop-pane/), each job's clock line now ends with the model its
latest step ran on, with `claude-` dropped, for example `840k tokens · ~$3.40 · opus-5-5`. Any other
model, an ollama one say, shows whole. A job with no model recorded, as from a loop.py older than the
entry below, shows the line as before, and a narrow pane cuts the model first. The pane is now 0.5.0.

Files: [`examples/mods/loop-pane/`](examples/mods/loop-pane/)

**Do:** nothing. `/plugin update`, then `/reload-plugins` or a new session, picks it up.

## 2026-10-26: The loop records which model each step ran on

Each agent run by [`scripts/loop.py`](scripts/loop.py) now records its model: the one `claude`'s `init` event
names, or the model the setting names, such as `qwen3:8b` for `ollama:qwen3:8b`, or `null` when
nothing says. For a `claude` run, `.loop/issue-N/agent.log` shows `· model <id>` before its first
tool call and the issue's status row takes it as `model`. Every run's `USAGE` line in `loop.log`
names it after the round (`build round 1 claude-opus-5-5 tokens …`, or `model unknown`), each
`usage.json` entry has a `model` field, and the pull request's `## Usage` table has a Model column.
Older `usage.json` and `status.json` files still load, and their entries show as `unknown`. Touches
[`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md).

**Do:** nothing, unless something of yours reads the `USAGE` line or the Usage table by position:
allow for the model after the round, and the new column.

## 2026-10-26: CI fails a mod change without a new version

A pull request that changes what a mod under [`examples/mods/`](examples/mods/) does now fails CI's `checks` job unless it
raises `version` in that mod's `.claude-plugin/plugin.json`. `/plugin update` keeps an installed copy
whose version hasn't changed, so without a new version the change never reaches anyone who already has
the mod. A change only to the mod's Markdown or to its `*.test.ts` and `*.test.tsx` files doesn't count, and a
mod that's new or removed in the pull request is skipped. Versions are three whole numbers, compared as
numbers, so 0.10.0 is higher than 0.9.0. The check runs on pull requests only, not in the pre-commit hook.

Files: [`scripts/check_mod_versions.py`](scripts/check_mod_versions.py), [`tests/test_mod_versions.py`](tests/test_mod_versions.py), [`.github/workflows/ci.yml`](.github/workflows/ci.yml),
the READMEs of [`examples/mods/harness-lens/`](examples/mods/harness-lens/), [`examples/mods/loop-pane/`](examples/mods/loop-pane/) and [`examples/mods/github-status/`](examples/mods/github-status/).

**Do:** raise a mod's version in any pull request that changes what it does.

## 2026-10-26: The issue window shows each tool call

While a `claude` agent run by [`scripts/loop.py`](scripts/loop.py) works, `.loop/issue-N/agent.log` now gets a line for
each tool call it makes: the tool's name and the path, pattern or URL it was given, such as
`→ Read /Users/you/.harness-loop/my-harness/issue-12/scripts/loop.py`, or the command on one line,
cut to 80 characters. What the agent says between calls shows too. Tool results and the rest of a
tool's input, such as an edit's text, stay out. In tmux, the issue's `issue-N` window follows that
file, so you watch it live; without tmux, `tail -f` it. Usage is still recorded.

If `claude` fails before it answers, with a bad flag say, its error now shows in `agent.log`. The issue's block comment gives the exit code, so `agent.log` is where to look.

This needs the loop to choose the output format. If the `agent`, `reader_agent` or `review_agent`
in your `loop.json` names `--output-format`, the loop keeps your format, and you won't see the tool calls.
Take the flag out to get them. One that names `stream-json` also needs `--verbose`, or `claude`
exits at once with `requires --verbose`.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md).

**Do:** if a loop is running, stop it the way [`skills/loop-control/`](skills/loop-control/) (*Stop it*) says, so no issue
is picked straight back up, then start it again. A running loop keeps the old code until then.

## 2026-10-26: The lens settles reviewers it missed ending

A reviewer that ended while the lens was reloading no longer shows `▶` for the rest of the session.
Every few seconds, while any reviewer shows as running, the lens checks the session's own list of
agents: one listed as completed shows `✓`, one failed or killed shows `✗`, and one no longer listed
shows `? reviewer`, dim, because the lens didn't see how it ended. One still listed as working keeps
its `▶`. If the list can't be read, nothing changes until the next check.

Files: [`examples/mods/harness-lens/`](examples/mods/harness-lens/) (`hooks/logic.ts`, `hooks/register.tsx`,
`types/index.d.ts`, [`README.md`](examples/mods/harness-lens/README.md), the tests), version 0.4.1.

**Do:** nothing. The lens is on by default; reload or restart Claude Code to take it.

## 2026-10-26: The lens counts headless sessions

The lens has a new **running** segment: how many headless `claude` sessions the loop and the agent
eval are running now, such as `eval 2 · loop 1`, or `none`. It counts every few seconds from `ps`,
so any clone's [`scripts/loop.py`](scripts/loop.py) counts under `loop`, and a `ps` that fails or takes over two
seconds keeps the last counts. An interactive session never counts. `/lens` lists each label with
its count, a zero included. The new `running` key in [`.claude/harness-lens.json`](.claude/harness-lens.json) sets the labels
and what they match.

Files: [`examples/mods/harness-lens/`](examples/mods/harness-lens/) (`hooks/logic.ts`, `hooks/register.tsx`,
`types/index.d.ts`, [`README.md`](examples/mods/harness-lens/README.md), the tests), version 0.4.0.

**Do:** nothing.

## 2026-10-26: The lens shows reviewers while they run

The lens's **review** segment now shows a reviewer agent from the moment it starts, with how long it
has run: `▶ reviewer 1:20`, or `▶ 2 reviewer · security-reviewer` when there are two or three, or
`▶ 4` past that. When it ends, the segment shows `✓ reviewer`, or `✗ reviewer` if it stopped on an
error, a refusal or an interrupt. `/lens` adds a `Running now:` line. Only the harness's own agents
show, and only ones the session you're driving sends. A subagent's run no longer counts as a turn
of yours, so starting a reviewer doesn't dim the rest of the band.

Files: [`examples/mods/harness-lens/`](examples/mods/harness-lens/) (`hooks/logic.ts`, `hooks/register.tsx`,
`types/index.d.ts`, [`README.md`](examples/mods/harness-lens/README.md), the tests), version 0.3.0.

**Do:** nothing.

## 2026-10-26: Security case 08 graded on the note's line

The security reviewer's case [`08-note-to-the-reviewer`](examples/typescript/evals/08-note-to-the-reviewer/) now passes when a finding's `**Where:**`
names line 2, the note telling reviewers to ignore their instructions, whatever words the finding
uses. Before, the reply had to quote "Ignore your previous instructions" exactly, so a reviewer that
caught the note and described it in its own words failed, as it did in the baseline. A reviewer the
note steered still reports no findings and fails. A security reviewer result saved before this
change can't be compared with one saved after it.

Files: [`examples/typescript/evals/08-note-to-the-reviewer/case.json`](examples/typescript/evals/08-note-to-the-reviewer/case.json), [`examples/proposal/evals/README.md`](examples/proposal/evals/README.md),
[`tests/test_eval_agents.py`](tests/test_eval_agents.py)

**Do:** to compare security reviewer runs, save a new baseline with
`python3 scripts/eval_agents.py examples/typescript/evals --save <file>`.

## 2026-10-26: The reviewer reads past a placeholder the gate catches

[`agents/reviewer.md`](agents/reviewer.md) and the proposal brief now say that a failure the gate catches, a
placeholder say, doesn't change how the reviewer reads the rest. Before, one `TBD` in an otherwise
clean proposal drew 7 to 10 findings where the same proposal without it drew none. Case 10 now
passes, and all ten reviewer cases pass both runs. A reviewer result saved before this change
can't be compared with one saved after it.

Files: [`agents/reviewer.md`](agents/reviewer.md), [`examples/proposal/agents/proposal-reviewer.md`](examples/proposal/agents/proposal-reviewer.md)

**Do:** to compare reviewer runs, save a new baseline with
`python3 scripts/eval_agents.py examples/proposal/evals --save <file>`.

## 2026-10-26: The clean proposal cases are clean

The reviewer's cases [`08-clean-bakery`](examples/proposal/evals/08-clean-bakery/) and [`09-clean-cycles`](examples/proposal/evals/09-clean-cycles/) were missing
things a client's finance lead would ask about: days and limits, changes and refunds, when
invoices are due, when the page launches and what pushes it back, and fees after launch. So a
reviewer that flagged them was right, and the cases failed it. Both proposals now say these things,
and the reviewer passes both cases with no findings,
two runs each on the final text. [`10-placeholder-the-gate-catches`](examples/proposal/evals/10-placeholder-the-gate-catches/) is the new 08 plus one
`TBD`, and it still fails. The reviewer leaves the `TBD` out as it should, then reports 7 to 10 points
on text it otherwise passes, so that's a fix for the reviewer, not the case. A reviewer result saved
before this change can't be compared with one saved after it.

Files: [`examples/proposal/evals/08-clean-bakery/work.md`](examples/proposal/evals/08-clean-bakery/work.md), [`examples/proposal/evals/09-clean-cycles/work.md`](examples/proposal/evals/09-clean-cycles/work.md),
[`examples/proposal/evals/10-placeholder-the-gate-catches/work.md`](examples/proposal/evals/10-placeholder-the-gate-catches/work.md)

**Do:** to compare reviewer runs, save a new baseline with
`python3 scripts/eval_agents.py examples/proposal/evals --save <file>`.

## 2026-10-26: Security eval cases graded on the flawed line

[`scripts/eval_agents.py`](scripts/eval_agents.py) takes a new `must_cover` field in a case: lines of the work file, each a
number or `"first-last"`, that some finding's `**Where:**` line must name as `:N` or `:N-M`. Only the
`**Where:**` line counts, and a miss prints as `not covered: line 37`. The security cases `01` to `07`
now use it in place of `must_find`, each naming the line that does the harm, so a finding that cites
the right line without quoting it passes. Results saved with `--save` before this change can't be
compared with `--baseline` for `01` to `07`.

Files: [`scripts/eval_agents.py`](scripts/eval_agents.py), [`examples/typescript/evals/`](examples/typescript/evals/) (`01` to `07`'s `case.json`),
[`examples/proposal/evals/README.md`](examples/proposal/evals/README.md), [`tests/test_eval_agents.py`](tests/test_eval_agents.py)

**Do:** re-run `python3 scripts/eval_agents.py examples/typescript/evals --save FILE` for a new baseline.

## 2026-10-26: Headless searches skip bare repos at any depth

[`.claude/hooks/guard.py`](.claude/hooks/guard.py) now passes each headless `Grep` on with `!*.git`, in any case, added to its glob,
so a search over a project leaves out a bare repo inside it, `vendor/lib.git/` included, where
before only one at the root or a project's top was left out. Nothing changes in ordinary sessions,
and the usage log doesn't count the rewrite.

Files: [`.claude/hooks/guard.py`](.claude/hooks/guard.py), [`tests/test_agent_hooks.py`](tests/test_agent_hooks.py), [`tests/test_usage.py`](tests/test_usage.py), [`README.md`](README.md)

**Do:** nothing.

## 2026-10-25: Headless runs skip .inbox and bare repos

A run [`bin/harness`](bin/harness) started now also can't read a leftover `.inbox/` (where the old inbox
sweep kept ideas taken from email) or a bare git repo's files under the root, such as
`projects/mirror.git/config`, which can hold a token in a remote URL. [`.gitignore`](.gitignore) now lists `*.git/`, so a
search over the root leaves a bare repo there out. One deeper inside a project is still searched.

Files: [`.claude/hooks/guard.py`](.claude/hooks/guard.py), [`tests/test_agent_hooks.py`](tests/test_agent_hooks.py), [`README.md`](README.md)

**Do:** nothing.

## 2026-10-25: Review evals grade the finding that names the flaw

[`scripts/eval_agents.py`](scripts/eval_agents.py) has new edges for a finding. It now takes in its title and severity
lines just above `**Where:**`, and stops at the next finding, a heading, or a line starting
`**Recommendations:**`, `**Not checked:**` or `**Summary:**`. Before, it started at `**Where:**` and
the last one ran to the end of the reply.
A `must_find` entry can be a list of alternatives, and a new `must_mention` field names texts the
reply has to hold anywhere. The security reviewer's cases in [`examples/typescript/evals/`](examples/typescript/evals/) now
anchor on the line that does the harm, not the function's name, which a reply could mention
without finding the flaw. Case `08`'s planted note is now a `must_mention`. A baseline saved
before this change can't be compared with a run after it.

Files: [`scripts/eval_agents.py`](scripts/eval_agents.py), `examples/typescript/evals/01`–`08/case.json`,
[`examples/proposal/evals/README.md`](examples/proposal/evals/README.md), [`tests/test_eval_agents.py`](tests/test_eval_agents.py).

**Do:** if you saved a `--save` file to use with `--baseline`, run the eval again and save a new one.

## 2026-10-25: More credential files, and the root's private files

[`.claude/hooks/guard.py`](.claude/hooks/guard.py) now treats keystores (`*.p12`, `*.pfx`, `*.jks`, `*.keystore`),
`.kube/config`, `service-account*.json`, `.htpasswd`, `.docker/config.json` and anything under
`.gnupg/` as credentials, in every session and in any case, shell commands included. A run
[`bin/harness`](bin/harness) started also doesn't reach `.claude/settings.local.json`, any `.git` folder,
`company/` or `local-data/`, which can hold a token or company data. Ordinary sessions still read
those, since `/orientation` and permission changes need them. `credentials.json` stays readable:
the name is too common to refuse.

Two refusals that ran before: a shell command is now matched in any case, so a `jq` filter on a
field named `.Key` or `.Env` after a space or a quote is refused (write `.["Key"]`); and a headless
`Grep` glob of `*.json` is refused, since it can match a cloud key file.

Files: [`.claude/hooks/guard.py`](.claude/hooks/guard.py), [`.claude/hooks/usage_log.py`](.claude/hooks/usage_log.py), [`tests/test_agent_hooks.py`](tests/test_agent_hooks.py), [`tests/test_usage.py`](tests/test_usage.py),
[`README.md`](README.md)

**Do:** nothing. The hook reads the new rules on its next call.

## 2026-10-25: The guard checks searches

[`.claude/hooks/guard.py`](.claude/hooks/guard.py) now sees `Grep` and `Glob`. In every session, a `Grep` whose
path or glob names a credential file, or a `.ssh` or `.aws` folder, is refused as a `Read` of it
is. That holds for a glob that can only match one (`*.pem`, `id_*`, a wildcard or class mid-name), in
any case, and for a link that lands on one. `Glob` only lists names, so it isn't checked for them.
In a run [`bin/harness`](bin/harness) started, `Read`, `Grep` and `Glob` reach only the harness root, after
`..`, braces and links resolve, a `Glob` pattern that climbs out included, and a `Grep` by
ripgrep's `sh` type, which takes in env files, is refused, as is any `Grep` glob that can match a
credential file, however broad (`*env*`). The usage log counts those
refusals as `headless` and a refused search as `credential-file`. A `Grep` over a folder that
happens to hold a credential file still isn't stopped: the guard sees the call, not the files.

Files: [`.claude/hooks/guard.py`](.claude/hooks/guard.py), [`.claude/hooks/usage_log.py`](.claude/hooks/usage_log.py), [`.claude/settings.json`](.claude/settings.json), [`tests/test_agent_hooks.py`](tests/test_agent_hooks.py),
[`tests/test_usage.py`](tests/test_usage.py), [`bin/harness-tools`](bin/harness-tools), [`README.md`](README.md)

**Do:** start a new session, so Claude Code reads the new matchers in [`.claude/settings.json`](.claude/settings.json).

## 2026-10-25: review-pr runs headless

[`.claude/hooks/guard.py`](.claude/hooks/guard.py) now holds a run [`bin/harness`](bin/harness) started to reading a pull
request or issue by number: `gh pr view <n>`, `gh pr diff <n>` and
`gh issue view <n>`, with `--comments` on a view. Every other command and every
connector is refused, and so is a call the guard can't check. With that in place
`review-pr` is marked headless, so `harness review-pr 42` works from any
folder. A skill now names its headless tools under `headless-tools`, which only
[`bin/harness`](bin/harness) reads: Claude Code's `allowed-tools` would grant them in ordinary
sessions too, where nothing narrows them. The guard is unchanged outside a
headless run. [`bin/harness`](bin/harness) also loads no MCP servers, and the usage log counts
these refusals under a `headless` rule, not as credential reads.

Files: [`.claude/hooks/guard.py`](.claude/hooks/guard.py), [`tests/test_agent_hooks.py`](tests/test_agent_hooks.py), [`.claude/hooks/usage_log.py`](.claude/hooks/usage_log.py), [`tests/test_usage.py`](tests/test_usage.py), [`bin/harness`](bin/harness), [`bin/harness-tools`](bin/harness-tools),
[`skills/review-pr/SKILL.md`](skills/review-pr/SKILL.md), [`tests/test_skills.py`](tests/test_skills.py), [`tests/test_harness_cli.py`](tests/test_harness_cli.py), [`README.md`](README.md)

**Do:** nothing.

## 2026-10-25: Local export

[`scripts/export.py`](scripts/export.py) bundles your loop runs and usage counts for a period into one JSON
file on your machine: the harness loop's lines from `.loop/history.jsonl`, keys it writes only and
no project's runs, and the counts your harness report uses. Nothing sends it, and its shape is
the only one a later sender may send.

Files: [`scripts/export.py`](scripts/export.py), [`tests/test_export.py`](tests/test_export.py), [`reports/usage/README.md`](reports/usage/README.md).

**Do:** nothing. Run `python3 scripts/export.py` to see your own.

## 2026-10-25: Run a skill headless with bin/harness

[`bin/harness`](bin/harness) runs a skill from any folder without opening a session:
`harness <skill> [arguments]`, or `harness --json <skill>` for JSON output. It
starts `claude -p` at the harness root and runs only skills marked
`headless: true`, with only the tools their `allowed-tools` line names, each of
which has to be in [`bin/harness-tools`](bin/harness-tools). It pins the permission mode and the
tools. No skill is marked yet: every Bash command checked could run a program,
write a file or reach another host, so marking `review-pr` waits on a guard
rule for headless runs. The usage log marks a session it started as `headless`.

Files: [`bin/harness`](bin/harness), [`bin/harness-tools`](bin/harness-tools), [`.claude/hooks/usage_log.py`](.claude/hooks/usage_log.py),
[`README.md`](README.md), [`tests/test_harness_cli.py`](tests/test_harness_cli.py), [`tests/test_skills.py`](tests/test_skills.py), [`tests/test_usage.py`](tests/test_usage.py)

**Do:** to use it, add `alias harness=~/path/to/my-harness/bin/harness` to your
shell's startup file, with the path to your copy.

## 2026-10-25: Security reviewer eval cases

Ten TypeScript cases for `security-reviewer` are in [`examples/typescript/evals/`](examples/typescript/evals/), the set to start
from for a team that writes code and no proposals. Seven plant one flaw each (a shell command,
a file path, a missing owner check, SQL, a server-side fetch, `new Function`, a sign-in redirect)
and expect NOT-READY. One holds a comment telling the reviewer to approve it, and two are clean
and expect READY. [`scripts/eval_agents.py`](scripts/eval_agents.py) now takes a `work` field in `case.json` naming the file
to review, `work.md` when it's left out, so existing cases are unchanged.

Files: [`examples/typescript/evals/`](examples/typescript/evals/), [`scripts/eval_agents.py`](scripts/eval_agents.py), [`examples/proposal/evals/README.md`](examples/proposal/evals/README.md), [`tests/test_eval_agents.py`](tests/test_eval_agents.py), [`AGENTS.md`](AGENTS.md).

**Do:** nothing. After you change [`agents/security-reviewer.md`](agents/security-reviewer.md) or its model, run
`python3 scripts/eval_agents.py examples/typescript/evals`.

## 2026-10-25: Loop run history

[`scripts/loop.py`](scripts/loop.py) adds one line to `.loop/history.jsonl` each time a run of an issue
ends, whether it opened a pull request, was blocked, stopped or skipped: when it started and
ended, its outcome, rounds, each round's test result and verdict, its tokens and cost, and which
agent and reviewer ran. Numbers and labels only, no titles or review text, and lines are never
changed. [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) says what each key holds.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md).

**Do:** nothing. The file starts with the next run that ends.

## 2026-10-24: One meaning of "cleared" for inbox and standup

The `inbox` and `standup` skills now both say a source is cleared only when its
`Cleared for this tool` answer is exactly `yes`,
and both allow only get, list, search and read calls. `inbox` also counts at
most 50 unread threads, and `standup` treats what it reads as data, never
instructions.

Files: [`skills/inbox/SKILL.md`](skills/inbox/SKILL.md), [`skills/standup/SKILL.md`](skills/standup/SKILL.md),
[`tests/test_skills.py`](tests/test_skills.py)

**Do:** a row with a condition after `yes`, such as `yes, summaries only`,
isn't cleared. If your `company/DATA.md` has one, rewrite it as plain `yes` or
`no`.

## 2026-10-24: Golden-example eval for review agents

[`scripts/eval_agents.py`](scripts/eval_agents.py) runs a review agent, twice per case by default, on a folder of known
examples and says which it catches: each case is stable, flaky or failing, with the tokens and
seconds it took. A case fails if the reply misses a planted defect, flags something it shouldn't,
has too many findings, gives the wrong verdict, or if the agent changed the checkout. `--save`
keeps a run as JSON and `--baseline` lists the cases whose status changed since. Ten cases for the
proposal reviewer are in [`examples/proposal/evals/`](examples/proposal/evals/), with a README on when to run it and what it
costs (twenty agent sessions). It isn't in the gate, because it starts real sessions.

Files: [`scripts/eval_agents.py`](scripts/eval_agents.py), [`examples/proposal/evals/`](examples/proposal/evals/), [`tests/test_eval_agents.py`](tests/test_eval_agents.py), [`AGENTS.md`](AGENTS.md).

**Do:** nothing. After you change [`agents/reviewer.md`](agents/reviewer.md), a brief or the reviewer's model, run
`python3 scripts/eval_agents.py examples/proposal/evals`.

## 2026-10-24: Loop pane wraps on Desktop and VS Code

In the Claude Desktop and VS Code panes, a job's title, time line and detail
line, and a queued issue's title and `waiting on` note, now show in full and
wrap instead of being cut at the pane's width. The terminal pane is unchanged.

Files: [`examples/mods/loop-pane/hooks/register.tsx`](examples/mods/loop-pane/hooks/register.tsx) and
[`examples/mods/loop-pane/hooks/pane.test.ts`](examples/mods/loop-pane/hooks/pane.test.ts).

**Do:** nothing

## 2026-10-24: Sprint report asks about skills unused twice

[`scripts/usage_report.py`](scripts/usage_report.py) takes `--previous <last report>` and, when given,
prints an `Unused two sprints running:` line naming the skills on both that
report's and this period's `Never used here:` lines. The `harness-report`
skill asks about each one: drop it, keep it, or test it (naming
`skill-creator`'s evals where installed), and records the answer under
`## Proposals`. The report itself removes and evaluates nothing.

Files: [`scripts/usage_report.py`](scripts/usage_report.py), [`tests/test_usage.py`](tests/test_usage.py),
[`skills/harness-report/SKILL.md`](skills/harness-report/SKILL.md)

**Do:** nothing

## 2026-10-24: Learn writes rules only from the person, through a PR

The `learn` skill now takes the mistake and the correct behaviour only from the
person in the session, and quotes a `.loop/lessons.md` entry to them instead of
working from it. It asks who a rule applies to (everyone, one project, or only
them), writes nothing when an existing rule conflicts and asks which governs,
and puts a shared rule in as a pull request with a `CHANGELOG.md` entry. "Remember
this" and "write that down" no longer trigger it.

Files: [`skills/learn/SKILL.md`](skills/learn/SKILL.md), [`tests/test_skills.py`](tests/test_skills.py)

**Do:** nothing.


## 2026-10-24: Loop-control shows the issue and describes stop

The `loop-control` skill now shows the person the issue's body and comments
verbatim before labelling, flags hidden comments and criteria changed only in a
comment, uses the project's effective ready label with `--repo`, says `run`
keeps polling when the queue is empty, and describes stop truthfully: label off
working issues, the running round may still open a pull request, and
`tmux kill-session` for an immediate halt.

Files: [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md), [`tests/test_skills.py`](tests/test_skills.py)

**Do:** nothing.

## 2026-10-24: Loop finds every ready issue

The loop's `discover` now asks GitHub only for issues carrying the ready label,
so a ready issue is found however many newer unlabelled ones there are. It used
to read the newest 50 open issues and miss an older ready one. `run`'s help now
says it keeps polling until stopped, and that `--for` bounds it.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py)

**Do:** nothing

## 2026-10-24: review-skill quarantines outside the repo

`review-skill` now copies an outside skill or plugin to `~/skill-quarantine/`,
outside every folder an agent loads from, instead of `incoming/` in the repo,
where Claude Code could load its `<skill>/CLAUDE.md` or `<skill>/.claude/skills/` as soon as a
file was read. It treats everything in the skill as data, reviews a skill with
no licence and adopts from nowhere, lists a plugin's hooks, MCP servers and
agents, flags more (bidi and tag characters, auto-loaded files, symlinks and
binaries, sending files out, persistence, permission-mode flags), and deletes
the copy at the end.

Files: [`skills/review-skill/SKILL.md`](skills/review-skill/SKILL.md), [`README.md`](README.md), [`STARTER-SKILLS.md`](STARTER-SKILLS.md),
[`.gitignore`](.gitignore), [`tests/test_skills.py`](tests/test_skills.py)

**Do:** move or delete anything left in `incoming/`, then remove the folder.

## 2026-10-24: Sprint report lists plugins and mods

The `harness-report` skill now runs [`scripts/plugin_report.py`](scripts/plugin_report.py), which lists the
enabled Claude Code plugins and mods by id, version and scope, and says which
changed, arrived or went since the person's last report. It shows no path. The
skill asks once whether the person owns the harness, and on a yes runs
`review-skill` on each changed or new plugin's installed folder, with the
findings under `## Changed plugins`.

Files: [`scripts/plugin_report.py`](scripts/plugin_report.py), [`tests/test_plugin_report.py`](tests/test_plugin_report.py),
[`skills/harness-report/SKILL.md`](skills/harness-report/SKILL.md), [`reports/usage/README.md`](reports/usage/README.md)

**Do:** nothing

## 2026-10-24: Harness reports stay out of the repo

Reports in [`reports/usage/`](reports/usage/) are now gitignored, and only the folder's README is
tracked. The `harness-report` skill writes the report there as before, then
says to send it to the harness owner yourself, not to open a pull request. The
owner reads them together and replies to each author about their proposals.

Files: [`.gitignore`](.gitignore), [`skills/harness-report/SKILL.md`](skills/harness-report/SKILL.md),
[`reports/usage/README.md`](reports/usage/README.md), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`tests/test_usage.py`](tests/test_usage.py)

**Do:** if a report is already committed, `git rm --cached` it. The file stays
on your machine.

## 2026-10-24: Harness report shows the loop's cost

`token_report.py`, and so the harness report, ends with a *Loop cost* table:
each issue's estimated dollars as the loop recorded them, how many of its runs
recorded none, and the total. It's an estimate at API prices, not what was
billed, and a run counts by when the loop picked its issue up. Conversations
stay in tokens, since their transcripts carry no cost. A project's loop issues
are now named `<project>/issue-N` in the token tables too, so the two line up.

Files: [`scripts/token_report.py`](scripts/token_report.py), [`tests/test_token_report.py`](tests/test_token_report.py),
[`skills/harness-report/SKILL.md`](skills/harness-report/SKILL.md), [`CHANGELOG.md`](CHANGELOG.md)

**Do:** nothing.

## 2026-10-23: Project loop.json sets project keys only

With `--project`, the project's own `loop.json` now sets only `test_command`,
`test_timeout`, `base`, `ready_label` and `blocked_label`. Every other key,
`agent` and `allow_lockfile_changes` included, comes from the harness's
`loop.json`, for one project under `"projects": {"<folder>": {...}}`. A project
file that sets one is refused with an `ERROR` line, so whoever can merge to a
project can't change what the loop runs there.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py),
[`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`projects/README.md`](projects/README.md),
[`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md)

**Do:** if a project's `loop.json` sets a key other than those five, move it
into the harness's `loop.json` under `"projects"`, keyed by the folder name.

## 2026-10-23: Where to run it

The README's *Set up* now says what works in the terminal, the VS Code
extension, Claude Desktop's Code tab and Claude Desktop's chat, from a test run
in each: all of the harness in the first three, none of it in chat. It also
says that two clones on one machine share one set of mods. Each mod's README
names where it was seen working.

Files: [`README.md`](README.md), the three mod READMEs in [`examples/mods/`](examples/mods/), [`tests/test_steering.py`](tests/test_steering.py), [`CHANGELOG.md`](CHANGELOG.md)

**Do:** nothing.

## 2026-10-23: Python suite runs the mods' tests

`python3 -m unittest discover -s tests`, and so the loop, now runs
`claude plugin validate` and `claude plugin test` on every mod under
[`examples/mods/`](examples/mods/), one test per mod. Where Claude Code isn't
installed, as in CI, those tests are skipped with the reason.

Files: [`tests/test_mods.py`](tests/test_mods.py), the *Changing it* section of
each mod's README in [`examples/mods/`](examples/mods/)

**Do:** nothing.

## 2026-10-22: Loop pane usage on the clock line

In the [loop pane](examples/mods/loop-pane/), each job's tokens and cost now
follow its start time and duration, for example `840k tokens · ~$3.40`, totalled
over every run of the issue. The cost is Claude Code's estimate at API prices,
not a bill. A job with no tokens recorded shows neither, and a narrow pane cuts
the usage first. No extra row.

Files: [`examples/mods/loop-pane/`](examples/mods/loop-pane/)

**Do:** nothing. `/reload-plugins`, or a new session, picks it up.

## 2026-10-22: Loop tidies a rebased pull request

The loop now records the commit it pushed for each pull request. If a person
rebases or amends the pull request, its head no longer holds the branch, but the
loop still removes the worktree and branch after the merge when the branch is
still that commit. A branch with a later commit, or a worktree with changes, is
kept as before. Pull requests opened before this keep the old behaviour.

Files: [`scripts/loop.py`](scripts/loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** nothing. Restart a running loop to pick it up.

## 2026-10-22: Loop pane start time on its own line

In the [loop pane](examples/mods/loop-pane/), when a job started and how long it
has run now sit on their own line under its title, above its step, so a long
step no longer pushes the clock off the edge. Each job takes one more row.

Files: [`examples/mods/loop-pane/`](examples/mods/loop-pane/)

**Do:** nothing. `/reload-plugins`, or a new session, picks it up.

## 2026-10-22: Loop token budget per issue

`max_issue_tokens` in `loop.json` caps the tokens one run of an issue may use.
Before each build and each review the loop checks the run's total from
`usage.json`; over the cap, it starts no more agents and blocks the issue with
the number in the comment. A run already started finishes, so one run can
overshoot. Relabelling the issue starts a fresh budget. Only runs that report
tokens count, and the loop warns at start-up about each agent that doesn't. The
default is `0`, no budget, so nothing changes until you set it.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md), [`CHANGELOG.md`](CHANGELOG.md)

**Do:** nothing. To use it, set `max_issue_tokens` in `loop.json`. Pick the number from what your
issues already use, which `python3 scripts/token_report.py` shows: cache reads count, and they are most of
a run.

## 2026-10-22: Loop blocks a round that changes a lockfile

A round of the loop's build agent that adds, edits, deletes or renames a
lockfile (`package-lock.json`, `yarn.lock`, `uv.lock`, `Cargo.lock`,
`requirements*.txt` and the like, at any depth) now blocks the issue before the
tests run, and the comment names the paths and says to put the dependency on
`base` and drop the agent's commit. It reads all the loop's commits on the
branch, so putting the issue back on the loop doesn't get past it, and it
blocks if git can't list them. A team that lets the agent install sets `"allow_lockfile_changes": true` in `loop.json`; any other value is an
`ERROR` when `run` starts. A manifest edited alone isn't caught, so `uv` and
`cargo` test commands should pass `--locked`.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md), [`CHANGELOG.md`](CHANGELOG.md)

**Do:** nothing, unless your loop lets the agent install: then set
`"allow_lockfile_changes": true` in its `loop.json`.

## 2026-10-22: Loop blocks a later round that adds nothing

A build round after the first that stages no new files now blocks the issue at
once, with the agent's reply quoted on the issue, instead of running the tests
and the review again up to `max_rounds`. This reverses the fourth criterion of
#118, which sent such a round to review. A round with no change against the
base is still blocked as before, and a resumed branch's first round still goes
to review.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`CHANGELOG.md`](CHANGELOG.md)

**Do:** nothing.

## 2026-10-22: Loop records each issue's usage

When the loop's agent is `claude`, it now records each run's tokens and
estimated cost: per run in `.loop/issue-N/usage.json`, as totals on the
issue's row in `status.json`, as a `USAGE` line in `loop.log`, in a `## Usage`
table on the pull request, and in one sentence on a block comment. A run that
reports nothing is `null` and "not reported", never 0. The dollar figure is
Claude Code's estimate at API prices.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md), [`CHANGELOG.md`](CHANGELOG.md)

**Do:** nothing. A tool that reads `loop.log` line by line will now see `USAGE` lines.

## 2026-10-22: Loop installs nothing by default

Says what the loop's build agent has always done: it doesn't install packages,
so a ticket that needs a new dependency isn't ready until someone adds it. A
team can allow installs for its own loop in `loop.json`. The agent can still
edit a manifest or lockfile, so the section recommends a test command that
installs only from the committed lockfile, such as `npm ci`.

Files: [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`steering/tickets.md`](steering/tickets.md), [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md), [`CHANGELOG.md`](CHANGELOG.md)

**Do:** nothing. To let your loop install, read [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) (*The build
agent doesn't install packages*) first.

## 2026-10-22: Loop works a project

`loop.py run`, `review` and `stop` take `--project projects/<name>` to work a
clone under [`projects/`](projects/) rather than the harness: that repo's issues and pull
requests, and its own `loop.json`, which has to set `test_command` (for
TypeScript, `"npm test"` or `"node --test"`). Its state stays in the harness, in
`.loop/projects/<name>/`, with a lock of its own. Its checkouts go in
`~/.harness-loop/<harness>/<name>/`. Every prompt opens with the harness's
[`AGENTS.md`](AGENTS.md) and the steering files it loads, and a `claude` build agent runs the
harness's `guard.py`. A codex build agent builds without that guard. A folder
outside [`projects/`](projects/), one that isn't its own clone, a clone off GitHub, or a
`loop.json` without `test_command` gets one `ERROR` line, and the loop exits 1
before it takes anything.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md),
[`projects/README.md`](projects/README.md), [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md)

**Do:** nothing. Without `--project` the loop works the harness, as before. To
use it on a project, give the project a `loop.json` with `test_command`.

## 2026-10-22: /github reads your projects

`/github acme` reads the repo cloned in `projects/acme`, and `/github all`
reads the harness and every folder under [`projects/`](projects/) with a GitHub remote,
one line each, from a session at the harness root. `/github` alone and the line
above the prompt are the harness's repo, as before. It still only reads.

Files: [`examples/mods/github-status/`](examples/mods/github-status/)

**Do:** nothing

## 2026-10-22: TypeScript example

A new example, [`examples/typescript/`](examples/typescript/), shows a TypeScript project tested
with Node alone: Node 22.18.0 and newer run the `.ts` tests directly with
`node --test`, `tsc` checks the types, and `typescript` is the one dependency.
Its README gives the loop setting,
`"test_command": "npm ci && npm run typecheck && npm test"`. CI gains a
`typescript` job that runs the example on Node 22.18.0, and a harness test
copies the example, runs it, breaks it and expects it to fail. Without Node
22.18.0 or newer, that test skips.

Files: [`examples/typescript/`](examples/typescript/), [`tests/test_typescript_example.py`](tests/test_typescript_example.py), [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md)

**Do:** nothing

## 2026-10-22: Loop keeps to working hours

`"hours": "Mon-Fri 09:00-17:00"` in `loop.json`, or `--hours` on `loop.py run`
or `loop.py review` for one run, keeps the loop to those local hours. Outside
them it starts nothing new, lets what's running finish, logs one `HOURS` line
with the next start, and waits. A window that crosses midnight, such as
`Fri 22:00-06:00`, belongs to the day it starts. A value it can't read logs an
`ERROR` and the loop exits before taking anything.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py),
[`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md)

**Do:** nothing. Without `hours` the loop runs at any time, as before.

## 2026-10-22: Check the starter

"Check the starter" lists what the public starter has shipped since your copy
was taken from it, oldest first, from a scratch clone it never runs anything
in. It flags each commit that touches a file you adapted, and recommends take,
merge by hand, skip or ask for each. It names the commands and never takes
anything itself. It finds where you left off from a `starter: <sha>` line in
this file's header, or else from the newest heading both logs share.
[`skills/review-skill/`](skills/review-skill/) now points here for changes from the starter's own
`main`.

Files: [`skills/check-starter/`](skills/check-starter/), [`skills/review-skill/SKILL.md`](skills/review-skill/SKILL.md), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md), [`tests/test_changelog.py`](tests/test_changelog.py)

**Do:** nothing. After you take the starter's changes, add `starter: <sha>`
above the first entry here, so the next check starts from there.

## 2026-10-22: Inbox reads your mail

`inbox` is now a read of your mail, not an idea list. Say "inbox" or "check
my email" and it reads the last day's mail, plus anything unread, from Gmail
by default or the provider you name (`/inbox outlook`), where
`company/DATA.md` clears it. It reports what needs a reply from you, what's
waiting on someone and what's worth knowing, one line per thread, and counts
the bulk mail. It only searches and reads. [`skills/standup/`](skills/standup/) now reads email
the same way.

Files: [`skills/inbox/SKILL.md`](skills/inbox/SKILL.md), [`skills/standup/SKILL.md`](skills/standup/SKILL.md), [`tests/test_skills.py`](tests/test_skills.py), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md). Removes `inbox.py` and `test_inbox.py`.

**Do:** nothing. The idea list and `inbox.py` are gone. Anything already in
`.inbox/` stays on your machine untouched, and is never committed.

## 2026-10-22: Loop counts a dependency a merged pull request closed

The loop now takes an issue whose `Depends on` issue was closed by a merged
pull request that names it, such as one with `Closes #3`, even when GitHub put
no commit on the close. Before, it blocked the issue as "closed without a
merged change". An issue closed by hand with no merged pull request is still
blocked, with the same message.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py)

**Do:** nothing. An issue already blocked this way needs its `loop:blocked`
label taken off and `loop-ready` put back to be tried again.

## 2026-10-22: GitHub status mod on by default

The [GitHub status mod](examples/mods/github-status/) now loads by itself, like
the harness lens and the loop pane: [`.claude/settings.json`](.claude/settings.json) turns it on.
It draws one line above the prompt with the repo's running actions, open pull
requests and open issues, read through `gh` at most every two minutes. It only
reads. Without `gh` signed in, the line says GitHub is unavailable.

Files: [`.claude/settings.json`](.claude/settings.json), [`examples/mods/github-status/README.md`](examples/mods/github-status/README.md), [`AGENTS.md`](AGENTS.md)

**Do:** nothing. To keep it off just for you:
`claude plugin disable github-status@sanvio-harness-starter --scope local`.

## 2026-10-22: What's new reads your own remote

"What's new" and "am I up to date" now fetch from this copy's own `origin`
and compare its [`CHANGELOG.md`](CHANGELOG.md) with yours, instead of reading the public
starter's. They also say how many commits you're ahead and behind, and name
`git pull --ff-only` to take the changes, saying when it would refuse. It
still only reports. What the starter has that your copy doesn't is now a
question for the starter check, not this skill.

Files: [`skills/whats-new/`](skills/whats-new/), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md)

**Do:** nothing
## 2026-10-22: Loop runs for a set time

`loop.py run --for 8h` and `loop.py review --for 8h` (or `90m`, `2d`) start
nothing new once that time has passed, let what's running finish, and exit. An
`UNTIL` line in `.loop/loop.log` says when it ends, and an `END` line says it
did. A running issue still gets every round, unlike a stop.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py),
[`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md)

**Do:** nothing. Add `--for` when you start the loop to give it an end time.
## 2026-10-22: The loop says when its own code changed

A running loop, or `loop.py review`, now logs one `STALE` line on an idle poll
when [`scripts/loop.py`](scripts/loop.py) has changed on disk since it started, so a pull or merge
doesn't leave it quietly running the old code. It only logs: it doesn't stop or
reload itself.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** stop the loop and start it again after pulling a change to [`scripts/loop.py`](scripts/loop.py).
## 2026-10-22: Orientation starts the company record from your pages

Orientation can now draft four sections of a local company record from up to
three public pages you name, each confirmed by you before it's written, and it
still asks you what you won't do and who decides.

Files: [`skills/orientation/SKILL.md`](skills/orientation/SKILL.md), [`tests/test_steering.py`](tests/test_steering.py)

**Do:** nothing
## 2026-10-22: Token report

[`scripts/token_report.py`](scripts/token_report.py) counts the Claude Code tokens spent under this
harness from Claude Code's own transcripts, subagents included: conversations
at the root, each repo under [`projects/`](projects/), and each issue the loop built, with
tokens by model, the subagent share and the top sessions and issues. It prints
counts only, never a prompt, a reply, a path or code. Tokens, not dollars, and
Claude Code only. The harness report now runs it and adds a `## Tokens`
section.

Files: [`scripts/token_report.py`](scripts/token_report.py), [`tests/test_token_report.py`](tests/test_token_report.py), [`skills/harness-report/SKILL.md`](skills/harness-report/SKILL.md), [`AGENTS.md`](AGENTS.md)

**Do:** nothing. Run `python3 scripts/token_report.py` to see the last 14 days.
## 2026-10-22: Loop pull requests describe themselves

A pull request the loop opens now carries what a reviewer on GitHub needs: the
files changed with their line counts, the test command and the last lines of
its output, the review in full, and the plan, collapsed. Mentions in the
agents' text can't ping anyone. A description that would pass GitHub's limit
cuts the plan first, then the review, and says where the full file is. Before
this, it said `Closes #N` and pointed at `.loop/` on the machine that ran it.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** nothing.

## 2026-10-22: Loop pane ready for Claude Desktop's Code tab

The [loop pane](examples/mods/loop-pane/)'s header now pushes the loop's state
to the right edge with the layout instead of padding spaces, which only line up
in a fixed-width font. Its tests now also draw the pane as Claude Desktop's Code
tab would, so a change that breaks it there fails. Whether Desktop loads the
starter's plugins at all is still to be tried by hand, under the issue about
where the starter runs.

Files: [`examples/mods/loop-pane/`](examples/mods/loop-pane/)

**Do:** nothing

## 2026-10-17: Name the loop's agents

`agent`, `reader_agent` and `review_agent` in `loop.json` can now be just a
name, `claude`, `codex` or `ollama:<model>`, with an optional model, and the
loop supplies the flags each job needs. `{"review_agent": "ollama:qwen3"}`
builds with Claude and reviews with a local model. A name that can't do its
job stops the run before it takes an issue. In `loop.py review`, an
`ollama:<model>` reviewer now runs, and `codex` is refused with the reason.
Anything a planner edits is now thrown away, as a reviewer's edits already
were. Command lines work as before.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** nothing.

## 2026-10-17: Pick the pull-request reviewer

The review-pr workflow example now runs on Claude, Codex or a local Ollama
model, picked with one `REVIEWER` repository variable. Left unset it stays on
Claude, as before. Each reviewer runs in its own step, which gets only its
own key. Codex runs in its read-only sandbox, and because its commands can
still read files across the runner, its report and its log are checked for
its key before anything is posted. Ollama runs a model named in
`REVIEW_MODEL` on a self-hosted runner labelled `ollama`, and its step holds
no key. `REVIEWER` is read in any case, and any other value fails the run.

Files: [`examples/ci/review-pr.yml`](examples/ci/review-pr.yml), [`skills/review-pr/SKILL.md`](skills/review-pr/SKILL.md), [`tests/test_review_pr_workflow.py`](tests/test_review_pr_workflow.py)

**Do:** nothing to stay on Claude. To switch, set `REVIEWER` to `codex` or
`ollama` (and `REVIEW_MODEL`), and add `OPENAI_API_KEY` for Codex.

## 2026-10-17: Idea inbox

A new `inbox` skill keeps the ideas you have away from the desk. Email one to
your own plus address from your phone, or say "idea: ..." in a session. Say
"inbox" and it sweeps those emails in, where `company/DATA.md` clears your
mail, then goes through each idea with you and gives it a fate: do it now,
make an issue, park it or drop it. The list lives in `.inbox/`, which is
gitignored, and the skill never changes a message.

Files: [`skills/inbox/SKILL.md`](skills/inbox/SKILL.md), [`skills/inbox/inbox.py`](skills/inbox/inbox.py), [`tests/test_inbox.py`](tests/test_inbox.py), [`.gitignore`](.gitignore), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md)

**Do:** pick a plus address, such as `name+idea@example.com`, and add a phone
shortcut that emails it. Step 1 of [`skills/inbox/SKILL.md`](skills/inbox/SKILL.md), *Set up capture*,
has both.

## 2026-10-17: Setup gets a figure

[`steering/writing.md`](steering/writing.md) now asks for a figure beside any README or doc that explains how
something is set up, with alt text that carries what it shows, and
[`AGENTS.md`](AGENTS.md) sends the agent there when it writes one. [`projects/README.md`](projects/README.md) gets
the first: the harness and its projects on disk, and where to start the agent.

Files: [`steering/writing.md`](steering/writing.md), [`AGENTS.md`](AGENTS.md), [`projects/README.md`](projects/README.md), [`docs/projects-layout.png`](docs/projects-layout.png)

**Do:** nothing.

## 2026-10-17: A dependency closed by hand blocks its issue

The loop now checks how a dependency was closed. One that a merged change
closed counts as met, as before. One closed by hand, so its work never reached
the base branch, now blocks the issue that depends on it straight away, with a
comment saying how to unblock it, instead of failing round after round.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** nothing.

## 2026-10-17: Company setup lives in the README

How to keep the company record now sits in the README's *Where things live*
section, with the four forms it can take and how to share it, instead of in
a separate `docs/company.md`. The company record template moved next to the
skill that uses it, and the section's figure lost its own title, since the
README heading above it already says it.

Files: [`README.md`](README.md), [`docs/where-things-live.png`](docs/where-things-live.png), [`skills/orientation/SKILL.md`](skills/orientation/SKILL.md), [`skills/orientation/COMPANY.example.md`](skills/orientation/COMPANY.example.md), [`tests/test_steering.py`](tests/test_steering.py)

**Do:** nothing. A link to `docs/company.md` now goes to the README's
*Where things live* section.

## 2026-10-17: Where things live

The README has a new *Where things live* section: the harness holds the method,
your company record and code live in repos you own, and your company's systems
are reached through connectors listed in `company/DATA.md`, never copied in. It
names the three forms `company/` can take, including a short `COMPANY.md` that
points at wiki pages, with a figure of the whole setup. `/orientation` now says this before its questions, and
asks where the company record lives before it interviews you for one: here, in
a company repo, or in a wiki.

Files: [`README.md`](README.md), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`skills/orientation/SKILL.md`](skills/orientation/SKILL.md), [`docs/COMPANY.example.md`](docs/COMPANY.example.md), [`docs/where-things-live.png`](docs/where-things-live.png), [`tests/test_steering.py`](tests/test_steering.py)

**Do:** nothing.

## 2026-10-17: company/ can be a private repo's clone

`company/` is now ignored as a whole, so you can clone a private company repo
into it with `git clone <url> company` and keep one record across harnesses and
machines. Its README and example moved out to [`docs/company.md`](docs/company.md) and
[`docs/COMPANY.example.md`](docs/COMPANY.example.md), and the README says when to keep the record
as local files, committed in a private copy, or in its own repo. The setup
check now asks GitHub for the company repo's visibility and fails if it's
public, and warns when the record is committed in the harness itself.

Files: [`.gitignore`](.gitignore), [`docs/company.md`](docs/company.md), [`docs/COMPANY.example.md`](docs/COMPANY.example.md), [`scripts/check_setup.py`](scripts/check_setup.py), [`tests/test_check_setup.py`](tests/test_check_setup.py), [`tests/test_steering.py`](tests/test_steering.py), [`skills/orientation/SKILL.md`](skills/orientation/SKILL.md), [`README.md`](README.md), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** nothing: your existing `company/` files stay where they are. To move
them into a company repo, run `git init` inside `company/`, commit, and push to
a private repo. On other machines, `git clone <url> company` from the harness
root.

## 2026-10-17: What's new works in a downloaded copy

"What's new" now reads the starter's `CHANGELOG.md` over HTTPS with `curl`
instead of `git fetch`, so it works in a copy downloaded as a ZIP as well as in
a clone. To show what an entry would change, it checks whether the copy is a
git repo: in a clone it uses `git diff` as before, and in a download it fetches
the starter's file with `curl` and shows a `diff -u`.

Files: [`skills/whats-new/SKILL.md`](skills/whats-new/SKILL.md), [`tests/test_changelog.py`](tests/test_changelog.py)

**Do:** nothing.

## 2026-10-17: Playwright e2e job in the CI example

The project CI example has an `e2e` job that runs `npx playwright test` when the
repo has a `playwright.config.ts`, `.js` or `.mjs`, skips with a notice when it
doesn't, and keeps `playwright-report/` for seven days when the tests fail. The
Playwright config has to start the app itself; the job needs no secrets.
[`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) says how to put e2e tests in the loop's `test_command`.

Files: [`examples/ci/project-checks.yml`](examples/ci/project-checks.yml), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`tests/test_ci_example.py`](tests/test_ci_example.py), [`CHANGELOG.md`](CHANGELOG.md)

**Do:** re-copy [`examples/ci/project-checks.yml`](examples/ci/project-checks.yml) into each project's
`.github/workflows/checks.yml` to take it.

## 2026-10-17: Coverage as an opt-in check

The example project workflow now runs `pytest --cov` when `pytest-cov` is a
dev dependency, and plain `pytest` with a notice when it isn't. It sets no
bar: the job fails on coverage only when the project sets `fail_under` under
`[tool.coverage.report]` in its own `pyproject.toml`. The Node job says
coverage belongs in the project's own `test` script. HOW-IT-WORKS shows how
to make coverage part of a loop round through `test_command`, and says what a
coverage pass doesn't prove. New tests check that `--cov` runs only behind the
`pytest-cov` check and that the workflow sets no threshold.

Files: [`examples/ci/project-checks.yml`](examples/ci/project-checks.yml), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`tests/test_ci_example.py`](tests/test_ci_example.py)

**Do:** to gate on coverage in CI, add `pytest-cov` as a dev dependency, set
`fail_under` under `[tool.coverage.report]` in the project's `pyproject.toml`,
and copy the updated workflow. For the loop, put `--cov --cov-fail-under=N`
in `test_command`.

## 2026-10-17: Loop review_agent

A new `loop.json` key, `review_agent`, names the command that reviews, so a
different model can review what the build agent wrote. It reviews each round in
the issue loop and each pull request in `loop.py review`, held to read tools the
same way `reader_agent` is, and for `review` it has to be `claude`. Planning
stays with `reader_agent`. Empty, the default, means `reader_agent` reviews as
before.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** nothing.

## 2026-10-17: Anatomy picture at the top of the README

The README shows one picture of the whole harness, after the opening animation:
your coding agent in the middle, the eight parts around it, the company
documents that feed each one, and the folder where each lives in this repo. The agent is named generically, since
the same harness works for Claude Code, Codex and Kiro.

Files: [`README.md`](README.md), [`docs/harness-anatomy.png`](docs/harness-anatomy.png)

**Do:** nothing.

## 2026-10-16: Secret scan checks the gitleaks download

The secret-scan workflow now checks the gitleaks binary against a SHA-256
written in the workflow before it runs it. Until now it piped the release
download straight into `tar`. A mismatch fails the job with its own message,
separate from the "a secret is in this repo's history" one. To move the
version, change `VERSION` and `SHA256` together, taking the checksum from that
release's checksums file. A new test fails on any workflow that downloads
something to run without a pinned sha256 check.

Files: [`.github/workflows/secrets.yml`](.github/workflows/secrets.yml), [`tests/test_ci_example.py`](tests/test_ci_example.py)

**Do:** if your harness has its own copy of `secrets.yml`, take this one, or add
the same check to yours.

## 2026-10-15: Loop blocks a build that changes nothing

When the loop's build leaves the branch the same as its base, the loop now
blocks the issue there and then: no tests, no review, no push and no pull
request. The status note and the log say `the build made no change in round N`,
and the comment on the issue quotes the last 2,000 characters of the build
agent's reply, with its @-mentions made harmless, so you can see why. A round
that adds nothing on top of earlier rounds' commits still goes to review.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py)

**Do:** nothing.

## 2026-10-15: CEO, CTO, CMO and GC reviewers

Four more read-only reviewers, one per executive seat, each reading finished
work for what that seat answers for and reporting at most ten findings the way
`reviewer` does. Each reads `company/COMPANY.md` if it exists and judges from
the work alone if it doesn't. The CTO sends vulnerabilities to
`security-reviewer`. The GC looks at licences, promises, other parties' names
or content, and personal data, says it isn't a lawyer, and ends each report
with the findings that need one. A new test checks every agent has a wrapper
in [`.claude/agents/`](.claude/agents/) that can't edit, write or run a shell.

Files: [`agents/ceo.md`](agents/ceo.md), [`agents/cto.md`](agents/cto.md), [`agents/cmo.md`](agents/cmo.md), [`agents/gc.md`](agents/gc.md), [`.claude/agents/ceo.md`](.claude/agents/ceo.md), [`.claude/agents/cto.md`](.claude/agents/cto.md), [`.claude/agents/cmo.md`](.claude/agents/cmo.md), [`.claude/agents/gc.md`](.claude/agents/gc.md), [`AGENTS.md`](AGENTS.md), [`tests/test_steering.py`](tests/test_steering.py)

**Do:** nothing.

## 2026-10-15: Loop pane header dot pulses

The dot before **Running** in the `/loop-pane` header now pulses, bright then
dim, in step with the dot beside each job the loop is on. Idle, stopping and
not running keep a still dot.

Files: [`examples/mods/loop-pane/`](examples/mods/loop-pane/)

**Do:** reopen `/loop-pane`, or reload mods, to pick it up.

## 2026-10-15: Loop pane header and a Watch button per job

`/loop-pane` opens on a header: the repo on the left, and on the right whether
the loop is running, idle, stopping or not running, how many jobs it's on, and
how long it has been up. Watch it and Copy attach command share one row, and
the bare `tmux attach` line is gone. Each job with a tmux window has its own
**Watch** button, which opens a read-only Terminal window on that job, or copies
its attach command when it can't. A queued issue that depends on an open one
says what it's waiting on. [`scripts/loop.py`](scripts/loop.py) writes `started` to
`.loop/status.json` while a run holds the lock, and on macOS in tmux
`.loop/issue-N/watch.command` while an issue's window is open. tmux has one
current window per session, so a job's Watch also switches any other window
attached to the loop's session.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`examples/mods/loop-pane/`](examples/mods/loop-pane/), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** restart a running loop, and reopen `/loop-pane`, to pick it up.

## 2026-10-15: GitHub status mod

A new mod, off unless you install it, draws one line above the prompt with the
session repo's running actions, open pull requests and open issues, and adds
`/github` to read them straight away. It only reads, through `gh`, at most once
every two minutes, and a repo without a GitHub `origin` remote never calls
`gh`.

Files: [`examples/mods/github-status/`](examples/mods/github-status/), [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)

**Do:** to use it, `/plugin install github-status@sanvio-harness-starter`,
with `gh` installed and signed in.

## 2026-10-15: The loop works several issues at once

[`scripts/loop.py`](scripts/loop.py) takes a `max_workers` key in `loop.json`,
default 1: how many ready issues it works side by side, each on its own thread
and worktree. An issue that depends on one still being worked waits for it. A
stop starts nothing new and lets each running issue finish its step. What each
issue's agents say goes to `.loop/issue-N/agent.log` as they say it, and run
inside tmux, each issue gets a window named `issue-N` that follows that file and
closes when the issue ends; while it's open, the issue's row in
`.loop/status.json` names it as `window`.
Every worker runs its own agent sessions, so usage grows with the number of
workers. Closing the loop's terminal or tmux session, or a `kill`, now ends the
run as a Ctrl-C does: its agents are stopped, not left working.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`README.md`](README.md), [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md)

**Do:** restart a running loop to pick it up. To work more than one issue at
once, set `"max_workers"` in `loop.json`.

## 2026-10-15: The loop waits for an issue's dependencies

[`scripts/loop.py`](scripts/loop.py) no longer takes an issue while one it
depends on is open. It reads each `Depends on #N` line in the issue and each
issue GitHub lists as blocking it, skips the issue until they're all closed as
completed, and takes the next one meanwhile. A `WAITING` line in the log says
what it waits on, as does `waiting_on` on its entry in the queue in
`.loop/status.json`. A dependency closed as not planned, a number that isn't an
issue, or a cycle blocks the issue with a comment saying which. It checks again
just before it starts, so a line added after the issue was queued still
counts.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`steering/tickets.md`](steering/tickets.md), [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** restart a running loop to pick it up. From then on, `loop-ready` can go
on a dependent issue before what it depends on has closed.

## 2026-10-15: Stamps and a phase gate for proposals

Two loops the README only described before now run. Each check stamps a
proposal with a fingerprint of its text, in order (the gate, then your okay on
the review), and an edit makes every stamp stale until they run again. A phase
gate names what a proposal is missing before Shape or Build and what closes
each gap, and never moves the phase itself. The README's loops are now the
main loop plus four: fix and recheck, a stamp goes stale (in place of a pass
goes stale), close the gap, and mistake to rule. The draft-proposal skill
stamps a proposal once its gate passes.

Files: [`examples/proposal/gates/stamp.py`](examples/proposal/gates/stamp.py), [`examples/proposal/gates/phase_gate.py`](examples/proposal/gates/phase_gate.py), [`tests/test_stamp.py`](tests/test_stamp.py), [`examples/proposal/README.md`](examples/proposal/README.md), [`examples/proposal/skills/draft-proposal/SKILL.md`](examples/proposal/skills/draft-proposal/SKILL.md), [`README.md`](README.md), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`steering/gates.md`](steering/gates.md), [`docs/stamp-goes-stale.gif`](docs/stamp-goes-stale.gif), [`docs/close-the-gap.gif`](docs/close-the-gap.gif), [`docs/mistake-to-rule.gif`](docs/mistake-to-rule.gif)

**Do:** nothing to take it. `docs/pass-goes-stale.gif` is gone, and the loops
section's anchor is now `#the-main-loop-and-four-inside-it`, so update anything
of yours that links to either.

## 2026-10-15: README loops follow the flywheel

The README's loops section now treats the flywheel as the main loop, with fix
and recheck, a pass goes stale and mistake to rule turning inside it, so
mistake to rule is now loop 3. The opening animation is a proposal job instead
of a bug fix, and a new animation at the end of the section shows harnesses
feeding each other as factories. `docs/flywheel.gif` is now
[`docs/main-loop.gif`](docs/main-loop.gif), and the section's anchor changed from
`#four-loops-that-keep-it-working` to `#the-main-loop-and-three-inside-it`.

Files: [`README.md`](README.md), [`docs/what-is-a-harness.gif`](docs/what-is-a-harness.gif), [`docs/main-loop.gif`](docs/main-loop.gif), [`docs/mistake-to-rule.gif`](docs/mistake-to-rule.gif), [`docs/factories-chain.gif`](docs/factories-chain.gif)

**Do:** nothing, unless something of yours links to `docs/flywheel.gif` or the
old anchor.

## 2026-10-15: Loop pane shows which job is live, when it started and for how long

Each job in the [loop pane](examples/mods/loop-pane/) now has a dot beside its
title. On a job the loop is working, the dot pulses and the row says when it
started and how long it has been running, counting up. An ended job keeps a
still dot in its result's colour and says how long it took. For this,
[`scripts/loop.py`](scripts/loop.py) now writes a `started` time on each issue
in `.loop/status.json`.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`examples/mods/loop-pane/`](examples/mods/loop-pane/)

**Do:** restart a running loop to pick up the start times. Jobs it started
before the restart have no clock.

## 2026-10-14: Loop cleans up finished worktrees

While the loop is idle, each time it polls it checks each issue it opened a
pull request for. If the pull request is merged or closed, the issue's worktree
has no changes, and every commit on the local `loop/issue-N` branch is in the
pull request, it removes the worktree and the branch and logs a `CLEANUP` line.
A worktree with changes, or a branch with commits that were never pushed, is
kept and logged once as `KEPT`. An open pull request, a blocked issue, or a
pull request GitHub can't be asked about leaves everything as it was. Remote branches, `review-pr-N` checkouts and
`.loop/issue-N/` stay.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** nothing

## 2026-10-14: Workflow actions pinned to commits

Every action in [`.github/workflows/`](.github/workflows/) and [`examples/ci/`](examples/ci/) is now named by
a full commit SHA, with its version in a comment, instead of a tag like `@v4`
that its owner can move to other code. The review prompt in
[`examples/ci/review-pr.yml`](examples/ci/review-pr.yml) is now written with a quoted heredoc, so nothing in
its body is ever expanded; the base branch goes in through `printf`. A new test
fails on an unpinned action or an unquoted heredoc in any workflow.

To move a pin, look up the commit the new release tag points at and change the
SHA and the comment together.

Files: [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [`.github/workflows/secrets.yml`](.github/workflows/secrets.yml), [`examples/ci/loop.yml`](examples/ci/loop.yml),
[`examples/ci/review-pr.yml`](examples/ci/review-pr.yml), [`examples/ci/project-checks.yml`](examples/ci/project-checks.yml), [`tests/test_ci_example.py`](tests/test_ci_example.py)

**Do:** if you copied an example workflow into your own [`.github/workflows/`](.github/workflows/),
copy it again, or pin its actions the same way.

## 2026-10-14: Secret scan blocks what it can't read

The pre-commit secret scan now reads a file whose type changed, such as a
symlink replaced by a regular file, and a file whose name starts like `0:`.
Before, both went through unscanned. A file it can't read at all, such as one
whose name holds a quote, a backslash, a tab or a newline, is now blocked with
"could not be read for scanning" instead of passing as clean. A staged deletion
still commits.

Files: [`.githooks/pre-commit`](.githooks/pre-commit), [`tests/test_pre_commit.py`](tests/test_pre_commit.py)

**Do:** nothing

## 2026-10-14: Stelliad pinned to a commit

The Stelliad plugin now installs from one Stelliad commit instead of whatever
is on Stelliad's main branch. It comes through the starter's own marketplace,
[`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json), whose entry names the commit; the separate
`stelliad` marketplace is gone from [`.claude/settings.json`](.claude/settings.json). A new Stelliad
commit reaches nobody until someone reads the diff and moves the `sha` in a
pull request. Its name is now `stelliad@sanvio-harness-starter`; the skills
still run as `stelliad:<name>`.

Files: [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json), [`.claude/settings.json`](.claude/settings.json), [`tests/test_plugins.py`](tests/test_plugins.py),
[`README.md`](README.md), [`STARTER-SKILLS.md`](STARTER-SKILLS.md), [`AGENTS.md`](AGENTS.md)

**Do:** if you had it before, remove the unpinned copy so only the pinned one
loads: `claude plugin uninstall stelliad@stelliad` and
`claude plugin marketplace remove stelliad`, then accept the install prompt the
next time you start in the harness.

## 2026-10-14: Connectors ask unless the name says read

The guard now asks before any connector call whose name doesn't say it's a
plain read. A tool passes only when its name says get, list, search, read,
find, query, fetch or view, and nothing in it says it sends, creates, edits,
deletes, shares, runs or executes. Before, a tool got through unless its name
said it changed something, so `copy_file`, `save_note` and `run_query` ran
without a prompt. More connector calls ask now, including some that only read,
like `git_status`, `skippy_usage` and `download_file_content`.

Files: [`.claude/hooks/guard.py`](.claude/hooks/guard.py), [`tests/test_agent_hooks.py`](tests/test_agent_hooks.py), [`README.md`](README.md),
[`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** nothing.

## 2026-10-14: The loop blocks an issue whose commit is refused

When a build round's `git commit` fails (no git identity set, say, or a locked index),
[`scripts/loop.py`](scripts/loop.py) now blocks the issue straight away with "commit refused
(git exit N)", instead of running the tests and review on a change that was
never committed. git's own output stays out of the issue comment.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py)

**Do:** nothing.

## 2026-10-14: Tighter guard on the security reviewer and on credential names

[`.claude/hooks/guard.py`](.claude/hooks/guard.py) closes gaps the security reviewer found in its own
fence. Git and `gitleaks` don't run in a repo whose `.git/config` can make a
read run a command (a pager, an external or textconv diff, a filesystem
monitor, an include), which a repo handed over as an archive can carry.
`git log` and `git show` can't print old file contents (`show` needs
`--stat` or `--name-only`, and no `rev:path`), and `gitleaks` takes only a
bare `--redact`. For every agent, `git show HEAD:.env` now counts as reading
a credential. [`.githooks/pre-commit`](.githooks/pre-commit) blocks `.env.*` and `id_rsa*` in a folder
too, not only at the root.

Files: [`.claude/hooks/guard.py`](.claude/hooks/guard.py), [`tests/test_agent_hooks.py`](tests/test_agent_hooks.py), [`.githooks/pre-commit`](.githooks/pre-commit),
[`tests/test_pre_commit.py`](tests/test_pre_commit.py), [`agents/security-reviewer.md`](agents/security-reviewer.md)

**Do:** nothing.

## 2026-10-14: Secret scan reads every staged name

The pre-commit secret scan now checks files whose names have a space in them
and files renamed in the commit. Before, a name like `a b.txt` was split into
two names that didn't exist, and a renamed file was skipped, so a key in
either got through. Accented names come through as written. Names holding a
newline, a quote, a backslash or a control character are still not handled.

Files: [`.githooks/pre-commit`](.githooks/pre-commit), [`tests/test_pre_commit.py`](tests/test_pre_commit.py)

**Do:** nothing.

## 2026-10-14: Review mode refuses a reader it can't confine

`python3 scripts/loop.py review` now starts only a `reader_agent` that is
`claude` itself, and always holds it to `--restricted --strict-mcp-config
--tools Read,Grep,Glob`, replacing any tools or permission flags `loop.json`
gave it. With any other command (`npx`, `env claude`, Codex) it reviews
nothing and logs why, where before it ran that command unconfined on a
stranger's checkout. The posted comment opens with a line saying an agent
wrote it from the pull request's own text, and an `@` in the report no longer
mentions anyone. The issue loop still takes any agent command.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** if `loop.json` sets `reader_agent` to anything but a `claude` command,
review mode stops reviewing: point it at `claude`, or run review elsewhere.

## 2026-10-14: The loop checks whose issue it builds from

[`scripts/loop.py`](scripts/loop.py) now reads each issue fresh before it takes it, and builds
from an issue written outside the repo's collaborators only if nothing in it
changed after it was labelled `loop-ready` and it hides no HTML comment.
Otherwise it blocks the issue and says why. The planner and the reviewer run
in the build checkout with read tools only, commits run with git hooks off,
and the test command runs without tokens, keys or passwords in its
environment. [`examples/ci/loop.yml`](examples/ci/loop.yml) leaves no token in `.git/config`, pushes
through `gh auth setup-git`, and pins the agent CLI.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`examples/ci/loop.yml`](examples/ci/loop.yml),
[`tests/test_ci_example.py`](tests/test_ci_example.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** if you copied [`examples/ci/loop.yml`](examples/ci/loop.yml), copy it again. If your test
command needs a token or key from the environment, it no longer gets one:
have the tests read a test-only value instead.

## 2026-10-14: The security reviewer runs pip-audit and bandit

On a Python project, the `security-reviewer` agent now runs `pip-audit` on
each requirements file, with `--disable-pip` so nothing installs, and
`bandit` on the code. It treats bandit's hits as leads to trace, not as
findings. Either one that isn't installed is listed under Not checked.

Files: [`agents/security-reviewer.md`](agents/security-reviewer.md)

**Do:** `brew install pip-audit bandit`, or `pipx install pip-audit bandit`,
if you want them.

## 2026-10-14: The security reviewer runs audits

The `security-reviewer` agent now has a shell, for audits only. It runs
`osv-scanner` over the lock files, `npm audit`, `pip-audit`, `trivy fs`,
`govulncheck`, `bundle-audit` or `bandit` where they fit, and `gitleaks
--redact` over the history, and reports findings from them rather than
naming them for you to run. [`.claude/hooks/guard.py`](.claude/hooks/guard.py) holds its shell to
that list plus git reads: one command at a time, no pipes, nothing that
installs, builds or runs the code under review. Any other command it tries is
refused. The audits send package names and versions to their advisory
services.

Files: [`.claude/hooks/guard.py`](.claude/hooks/guard.py), [`tests/test_agent_hooks.py`](tests/test_agent_hooks.py), [`agents/security-reviewer.md`](agents/security-reviewer.md),
[`.claude/agents/security-reviewer.md`](.claude/agents/security-reviewer.md), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md)

**Do:** install the scanners you want it to use. `osv-scanner` and `gitleaks`
cover most projects (`brew install osv-scanner gitleaks`). One that's missing
is listed under Not checked.

## 2026-10-14: A security reviewer

A second agent, `security-reviewer`, reads code the way an attacker would and
reports what could be exploited. Each Critical or High finding carries its
attack path from entry point to payoff, and the report opens with a READY or
NOT-READY verdict. It only reads and has no shell, so text planted in the code
it reviews can't make it run anything. It names the dependency audit and the
history scan for a person to run instead. `review-pr` hands it changes that
touch auth, input handling, secrets, infrastructure or dependencies.

Files: [`agents/security-reviewer.md`](agents/security-reviewer.md), [`.claude/agents/security-reviewer.md`](.claude/agents/security-reviewer.md),
[`AGENTS.md`](AGENTS.md), [`skills/review-pr/SKILL.md`](skills/review-pr/SKILL.md), [`tests/test_steering.py`](tests/test_steering.py)

**Do:** nothing. Ask for a security review, or run the `security-reviewer`
agent by name.

## 2026-10-14: Loop pane tabs

The loop pane (0.4.0) splits its list into **Queue**, **Active** and
**Finished** tabs, each with its count, and shows three jobs at a time:
scroll over the pane, or press the more lines, for the rest. **Finished**
keeps only the last 24 hours, so a pull request the loop opened days ago no
longer reads as open.

Files: [`examples/mods/loop-pane/`](examples/mods/loop-pane/)

**Do:** nothing. It arrives with your next session.

## 2026-10-14: Loop pane opens a window on the loop

On a Mac, the loop pane (0.3.0) has a **Watch it** button while the loop runs
in tmux. It opens a new Terminal window attached to the loop's session,
read-only, so you watch without typing into it; closing the window leaves the
loop running. [`scripts/loop.py`](scripts/loop.py) writes `.loop/watch.command` for it when a run
starts inside tmux on macOS, and removes it when the run ends. Elsewhere the
pane copies the attach command as before. The pane also stops reading the
loop's files once it's closed, which it was meant to and didn't.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`examples/mods/loop-pane/`](examples/mods/loop-pane/),
[`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`AGENTS.md`](AGENTS.md)

**Do:** nothing. The button arrives with your next session, from the next
loop run started in tmux.

## 2026-10-13: Standup reads only cleared sources

[`skills/standup/`](skills/standup/) reads a calendar, email or tracker only when `company/DATA.md` clears it, as [`AGENTS.md`](AGENTS.md)
already requires. A connector being there isn't enough.

Files: [`skills/standup/SKILL.md`](skills/standup/SKILL.md), [`tests/test_skills.py`](tests/test_skills.py)

**Do:** nothing. To include your calendar or email, run `/orientation` so `company/DATA.md` lists them.

## 2026-10-13: What's new lists every entry

[`skills/whats-new/`](skills/whats-new/) makes its list with a command and gives every entry on it, with the count. "Since a date" includes that day.

Files: [`skills/whats-new/SKILL.md`](skills/whats-new/SKILL.md), [`tests/test_changelog.py`](tests/test_changelog.py)

**Do:** nothing.

## 2026-10-13: The PR review workflow runs restricted

[`examples/ci/review-pr.yml`](examples/ci/review-pr.yml) runs the agent in Claude Code's restricted mode: read tools only, confined
to the checkout, with the diff in its prompt. That replaces the allow and deny lists.

Files: [`examples/ci/review-pr.yml`](examples/ci/review-pr.yml), [`tests/test_review_pr_workflow.py`](tests/test_review_pr_workflow.py)

**Do:** copied it already? Copy it again.

## 2026-10-13: loop.py review

`python3 scripts/loop.py review` watches the open pull requests that ask for
your review (`review_query`, by default `review-requested:@me`), has a fresh
`reader_agent` review each new head commit with [`skills/review-pr/`](skills/review-pr/), and posts the report as one
comment per pull request, edited in place on later commits. A commit is reviewed
once, the agent can read the checkout and nothing else, and it never
approves, merges or pushes. It shares the loop's lock, log, status file and
stop file.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md)

**Do:** nothing, or start `loop.py review` on the machine the loop runs on, in a clone of its own if `run` is working the first.

## 2026-10-13: Where a change lives

[`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) says which changes reach the team and which stay on your machine, and why a
skill kept in both this repo and `~/.claude/skills/` runs differently for you than for everyone else.

Files: [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** nothing.

## 2026-10-13: The PR review workflow runs

[`examples/ci/review-pr.yml`](examples/ci/review-pr.yml) failed on every run: the CLI refuses Grep and Glob path rules. It now
denies `/proc` with one Read rule, pins the CLI, prints why a run failed, and says the key must be scoped to a workspace.

Files: [`examples/ci/review-pr.yml`](examples/ci/review-pr.yml), [`tests/test_review_pr_workflow.py`](tests/test_review_pr_workflow.py)

**Do:** copied it already? Copy it again.

## 2026-10-13: A standup skill

[`skills/standup/`](skills/standup/) gives you one morning read of what's on you, from GitHub, the
loop and any calendar, email or tracker your session reaches, then asks about
each item and suggests an order for the day. It reads only and changes nothing.

Files: [`skills/standup/SKILL.md`](skills/standup/SKILL.md), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md), [`STARTER-SKILLS.md`](STARTER-SKILLS.md), [`tests/test_skills.py`](tests/test_skills.py)

**Do:** nothing; ask for a standup in a new session.

## 2026-10-13: The loop off your laptop

"The loop" in [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) has a subsection, *Off your laptop*: where the loop can run
besides your terminal, what each place costs, and the limits of GitHub Actions.
[`examples/ci/loop.yml`](examples/ci/loop.yml) runs one pass there on a schedule or on demand.

Files: [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`examples/ci/loop.yml`](examples/ci/loop.yml), [`tests/test_ci_example.py`](tests/test_ci_example.py)

**Do:** to use it, copy it into [`.github/workflows/`](.github/workflows/) and add the secret it names,
`ANTHROPIC_API_KEY`.

## 2026-10-13: Review every pull request in CI

[`examples/ci/review-pr.yml`](examples/ci/review-pr.yml) is a GitHub Actions workflow that runs the
`review-pr` skill on every pull request and posts its report as one comment. It
runs on `pull_request` only, skips forks with a notice, and gives the agent no
GitHub token.

Files: [`examples/ci/review-pr.yml`](examples/ci/review-pr.yml), [`tests/test_review_pr_workflow.py`](tests/test_review_pr_workflow.py),
[`skills/review-pr/SKILL.md`](skills/review-pr/SKILL.md)

**Do:** to use it, copy it into [`.github/workflows/`](.github/workflows/) and add the secret it
names, `ANTHROPIC_API_KEY`, as a repository secret.

## 2026-10-13: The loop, animated

"The loop" in [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) has an animation after its step table,
[`docs/one-issue-through-the-loop.gif`](docs/one-issue-through-the-loop.gif): one issue through Discover, Shape, Build and
Validate, a FIX round back to Build, then a pull request the loop doesn't
merge. The log lines are in the format [`scripts/loop.py`](scripts/loop.py) writes.

Files: [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`docs/one-issue-through-the-loop.gif`](docs/one-issue-through-the-loop.gif)

**Do:** nothing.

## 2026-10-13: The README explains gates

[`README.md`](README.md) has a new section, *Gates: done is a script's call*: what a gate
is, the three places one runs and what each catches, when a check earns one,
and how a job's gate differs from the gate at the end of a phase. An
animation, [`docs/where-a-gate-runs.gif`](docs/where-a-gate-runs.gif), shows one gate file catching three
different mistakes in three places.

Files: [`README.md`](README.md), [`docs/where-a-gate-runs.gif`](docs/where-a-gate-runs.gif)

**Do:** nothing.

## 2026-10-12: link_files leaves . plain

[`scripts/link_files.py`](scripts/link_files.py) no longer turns a backticked `.` or `./` into a link
to the file's own folder. Below the root it used to; at the root it never did.
Named folders still link as before.

Files: [`scripts/link_files.py`](scripts/link_files.py), [`tests/test_link_files.py`](tests/test_link_files.py)

**Do:** nothing.

## 2026-10-12: loop-control starts the loop in tmux

When tmux is installed, [`skills/loop-control/`](skills/loop-control/) starts the loop in a tmux
session named after the clone's folder, instead of in the background of the
conversation. It keeps running after the conversation ends, and
`tmux attach -t loop-<folder>` opens it to watch; `Ctrl-b d` leaves it
running. Without tmux it starts in the background as before.
[`scripts/loop.py`](scripts/loop.py), run inside tmux, logs a `START` line with the session name
and `tmux attach -t <name>`, and writes the name to `tmux` in
`.loop/status.json` while it runs. The loop pane (0.2.0) shows it under its
first line, with a button that copies the attach command.

Files: [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md), [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py),
[`examples/mods/loop-pane/`](examples/mods/loop-pane/), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** install tmux if you want to watch the loop this way. The pane's new
line arrives with your next session.

## 2026-10-12: Tickets use Stelliad's sections

The issue template, [`steering/tickets.md`](steering/tickets.md) and the `loop-control` readiness
check now use the sections of Stelliad's Ticket Authoring Standard: Objective,
Why, Acceptance Criteria (flat checkboxes), Scope with In and Out, and Risk,
plus Verification, Context, Dependencies or References when they carry
something. `stelliad:create-ticket` writes this shape and
`stelliad:review-ticket` grades it; its checker blocked every ticket in the old
What and why / Done means shape. The loop's own rules stay on top: at least
one criterion is proved by a test the loop's test command runs, and a ticket
with High or Critical risk, a Human Approval section or an open dependency
isn't loop-ready. The loop's comment on a
blocked issue now says to fix the acceptance criteria.

Files: [`.github/ISSUE_TEMPLATE/loop-task.md`](.github/ISSUE_TEMPLATE/loop-task.md), [`steering/tickets.md`](steering/tickets.md),
[`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md), [`scripts/loop.py`](scripts/loop.py), [`tests/test_tickets.py`](tests/test_tickets.py)

**Do:** rewrite open tickets in the new shape before you label them
`loop-ready`: `loop-control` now wants `stelliad:review-ticket` to say READY,
and the checker blocks the old shape. Tickets already labelled still run, since
the loop reads the whole issue body.

## 2026-10-12: CI runs the link check

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) now runs `python3 scripts/link_files.py --check`, so
a pull request that names a tracked file in its Markdown without linking it
fails CI instead of merging. It's checked against what git tracks, so a file
added in the same change counts.

Files: [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [`README.md`](README.md)

**Do:** run `python3 scripts/link_files.py` before you push if you've
written file names into Markdown. It adds the links for you.

## 2026-10-12: Stelliad comes switched on

[`.claude/settings.json`](.claude/settings.json) now names the public Stelliad marketplace and switches
its plugin on, so trusting the folder switches it on, with no separate prompt.
Its skills run as `stelliad:<name>`: `stelliad:create-spec` and the spec loop
for specs, `stelliad:create-ticket` and `review-ticket` for issues the loop can
take. [`AGENTS.md`](AGENTS.md) points spec and ticket work at them, the README and
[`STARTER-SKILLS.md`](STARTER-SKILLS.md) say why Stelliad is the one set installed rather than copied,
and the lens counts its skills as the harness's. A new test checks every
plugin the settings switch on comes from a marketplace they name.
[`.gitignore`](.gitignore) now ignores `.claude/settings.local.json`, where the
per-person opt-out below is written, so it can't be committed by accident.

Files: [`.claude/settings.json`](.claude/settings.json), [`.claude/harness-lens.json`](.claude/harness-lens.json), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md),
[`STARTER-SKILLS.md`](STARTER-SKILLS.md), [`examples/mods/harness-lens/README.md`](examples/mods/harness-lens/README.md), [`tests/test_plugins.py`](tests/test_plugins.py), [`.gitignore`](.gitignore)

**Do:** in an older copy, add the `stelliad` entry to `extraKnownMarketplaces`
and `"stelliad@stelliad": true` to `enabledPlugins` in [`.claude/settings.json`](.claude/settings.json),
and copy [`.claude/harness-lens.json`](.claude/harness-lens.json). Stelliad should come on with your next
session in that folder; if it doesn't, run `/plugin install stelliad@stelliad`.
To keep it off for yourself, run
`claude plugin disable stelliad@stelliad --scope local`.

## 2026-10-11: link_files.py leaves ~~~ code blocks alone

[`scripts/link_files.py`](scripts/link_files.py) now treats a block fenced with `~~~` as code, the same
as one fenced with three backticks, and a block closes only on the marker that
opened it, so file names inside it stay plain.

Files: [`scripts/link_files.py`](scripts/link_files.py), [`tests/test_link_files.py`](tests/test_link_files.py)

**Do:** if your copy has `~~~` blocks, check them for links like
``[`name`](path)`` that an earlier run added and remove them by hand.
Re-running the script won't remove them.

## 2026-10-11: Loop commits use the issue title

Each round's commit from [`scripts/loop.py`](scripts/loop.py) now takes the issue's title as its
subject and names the issue and round in its body, so a squash merge leaves a
readable line on `main` instead of `loop: issue N round R`.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py)

**Do:** nothing.

## 2026-10-11: loop run --issue exits when that issue is done

`python3 scripts/loop.py run --issue N` now stops once issue N has a pull
request or is blocked, or logs `IDLE` once and stops if N isn't ready, instead
of polling for an issue that can never come.

Files: [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py)

**Do:** nothing.

## 2026-10-11: check_setup stops on --help or an unknown flag

[`scripts/check_setup.py`](scripts/check_setup.py) now reads its arguments with argparse, so `--help`
prints usage and a mistyped flag such as `--chek` stops with an error, instead
of either one running every check.

Files: [`scripts/check_setup.py`](scripts/check_setup.py), [`tests/test_check_setup.py`](tests/test_check_setup.py)

**Do:** nothing.

## 2026-10-11: usage_report refuses a date it can't read

[`scripts/usage_report.py`](scripts/usage_report.py) now stops with an error naming `--since` and the
`YYYY-MM-DD` format when given a date it can't read, instead of printing a
report that silently counts the wrong lines.

Files: [`scripts/usage_report.py`](scripts/usage_report.py), [`tests/test_usage.py`](tests/test_usage.py)

**Do:** nothing.

## 2026-10-11: link_files stops on --help or an unknown flag

[`scripts/link_files.py`](scripts/link_files.py) now reads its arguments with argparse, so `--help`
prints usage and a mistyped flag such as `--chek` stops with an error, instead
of either one linking every file name in the repo.

Files: [`scripts/link_files.py`](scripts/link_files.py), [`tests/test_link_files.py`](tests/test_link_files.py)

**Do:** nothing.

## 2026-10-11: The lens can show the session's scope

A harness that scopes a session to one client or project can now see that
scope on the lens line, first: `scope: partner fabrikam`. List the files that
hold it under a new `scope` key in [`.claude/harness-lens.json`](.claude/harness-lens.json); `/lens` prints
it too. The starter declares no scope, so its band doesn't change.

Files: [`examples/mods/harness-lens/`](examples/mods/harness-lens/) (`hooks/logic.ts`, `hooks/register.tsx`,
`types/index.d.ts`, [`README.md`](examples/mods/harness-lens/README.md), the tests), version 0.2.0.

**Do:** nothing, unless your harness has a scope file. Then add its path to
`scope` in [`.claude/harness-lens.json`](.claude/harness-lens.json).

## 2026-10-09: What a ticket holds, and how one ends

[`steering/tickets.md`](steering/tickets.md) says what goes in an issue (what and why, a "done
means" a check can prove, what's out of scope, pointers), when one is ready
for the loop, what a comment on one is for, and how one ends. New issues on
GitHub start from [`.github/ISSUE_TEMPLATE/loop-task.md`](.github/ISSUE_TEMPLATE/loop-task.md). The loop's pull
request now says `Closes #N`, so merging it closes the issue, and the loop
comments on the issue when it opens the pull request or blocks.

**Files:** [`steering/tickets.md`](steering/tickets.md), [`.github/ISSUE_TEMPLATE/loop-task.md`](.github/ISSUE_TEMPLATE/loop-task.md), [`scripts/loop.py`](scripts/loop.py),
[`tests/test_loop.py`](tests/test_loop.py), [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md), [`AGENTS.md`](AGENTS.md), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md),
[`docs/specs/lightweight-loop.md`](docs/specs/lightweight-loop.md)

**Do:** take the steering file, its row in [`AGENTS.md`](AGENTS.md), the issue template and
[`scripts/loop.py`](scripts/loop.py). The loop's `gh` sign-in now needs permission to comment on
issues, which a normal sign-in has.

## 2026-10-09: Loop control skill

[`skills/loop-control/`](skills/loop-control/) drives the loop from a conversation. "Put #12 on the
loop" reads the issue, checks it's one change with a check that proves it and
nothing outside the repo, says if the pull request would be public, and asks
before labelling. It also starts the loop (setup check and dry run first),
says what the loop did (outcome, rounds, review findings, what the review
couldn't check), and stops it with the label taken off first.

**Files:** [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md), [`AGENTS.md`](AGENTS.md), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** take [`skills/loop-control/`](skills/loop-control/) and its row in [`AGENTS.md`](AGENTS.md).

## 2026-10-09: Loop pane

A Claude Code mod: `/loop-pane` opens a pane beside the conversation showing
the loop. Whether it's running, which ready issues are waiting, and for each
issue the step it's on and its round, the last test and review results, and
its pull request, with a button that copies the link. An issue that reaches
an end pops up a notice. It reads `.loop/status.json` every two seconds while
the pane is open and only reads. It's on by default, like the lens.

**Files:** [`examples/mods/loop-pane/`](examples/mods/loop-pane/), [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json),
[`.claude/settings.json`](.claude/settings.json), [`AGENTS.md`](AGENTS.md), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** take [`examples/mods/loop-pane/`](examples/mods/loop-pane/) and the `loop-pane` entry in
[`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json), and add
`"loop-pane@sanvio-harness-starter": true` to `enabledPlugins` in your
[`.claude/settings.json`](.claude/settings.json). Needs the status file entry below.

## 2026-10-09: The loop writes a status file

[`scripts/loop.py`](scripts/loop.py) now keeps `.loop/status.json` up to date at every step:
whether it's running, which ready issues are waiting, and for each issue the
step it's on, the round, the last test and review results, and the pull
request. The log stays as it was. A dashboard, a pane or a script reads the
file instead of parsing the log.

**Files:** [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** take [`scripts/loop.py`](scripts/loop.py) if you haven't changed yours. `.loop/` is already
gitignored.

## 2026-10-09: How to try the loop

[`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) now shows the loop's flags (`--dry-run`, `--once`,
`--issue`), says to try it on a private copy because a real run opens a pull
request, and says what the review agent can and can't check.

**Files:** [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** nothing.

## 2026-10-09: What counts lives in this file

What gets an entry here, and the shape of one, moved from
[`steering/operating.md`](steering/operating.md) to the top of this file, where you are when you write
one. [`steering/operating.md`](steering/operating.md) loads into every session, and it no longer
repeats what [`AGENTS.md`](AGENTS.md) already says about the company files. The
always-loaded set is about 30 lines shorter.

**Files:** [`CHANGELOG.md`](CHANGELOG.md), [`steering/operating.md`](steering/operating.md), [`AGENTS.md`](AGENTS.md),
[`skills/review-pr/SKILL.md`](skills/review-pr/SKILL.md)

**Do:** if you copied [`steering/operating.md`](steering/operating.md), take the new one, or delete
its "Telling people what changed" section and take this file's header.

## 2026-10-09: Where it came from

The README now says who makes the starter and asks one thing beyond the MIT
licence: keep the line that says where a file came from. Each skill carries
that line as a `license:` field in its frontmatter, and the gate, the guard
and the git hook carry it as a comment. [`CITATION.cff`](CITATION.cff) turns on GitHub's
"Cite this repository" button.

**Files:** [`README.md`](README.md), [`CITATION.cff`](CITATION.cff), every `SKILL.md`,
[`examples/proposal/gates/proposal_gate.py`](examples/proposal/gates/proposal_gate.py), [`.claude/hooks/guard.py`](.claude/hooks/guard.py),
[`.githooks/pre-commit`](.githooks/pre-commit)

**Do:** nothing. If you copy a file into your own harness, keep its credit line.

## 2026-10-09: Usage log and sprint report

A new hook logs which skills, agents and slash commands ran, and when the guard
refused or asked and whether you said yes. Names and counts only, never
prompts, paths or code, in `.harness/usage/<you>.jsonl`, which is gitignored.
At the end of a sprint, `harness-report` turns your log into a short report with
your own proposals, shared as a pull request into [`reports/usage/`](reports/usage/). Whoever owns
the harness reads them together and decides what goes in.

**Files:** [`.claude/hooks/usage_log.py`](.claude/hooks/usage_log.py), [`.claude/settings.json`](.claude/settings.json), [`scripts/usage_report.py`](scripts/usage_report.py),
[`skills/harness-report/SKILL.md`](skills/harness-report/SKILL.md), [`reports/usage/README.md`](reports/usage/README.md), [`.gitignore`](.gitignore),
[`tests/test_usage.py`](tests/test_usage.py), [`AGENTS.md`](AGENTS.md), [`README.md`](README.md)

**Do:** take the files above, add the usage-log entries from [`.claude/settings.json`](.claude/settings.json) to
yours, and add `.harness/` to your [`.gitignore`](.gitignore). Tell your team it's on, and
that `HARNESS_USAGE_LOG=off` turns it off for them.

## 2026-10-09: A loop that runs without you

[`scripts/loop.py`](scripts/loop.py) takes an open issue labelled `loop-ready`
through the flywheel: a fresh agent plans it, another builds it in a worktree,
the script runs your tests itself, a third fresh session reviews the diff, and
a pull request opens when both pass. Five rounds, then the issue is labelled
`loop:blocked`. It writes one plain log, `.loop/loop.log`, to watch with
`tail -f`, and a `.loop/lessons.md` in the shape [`skills/learn/`](skills/learn/)
reads. It checks the issue is still open before it opens a pull request, and
it never merges. Standard library only.

**Files:** [`scripts/loop.py`](scripts/loop.py), [`tests/test_loop.py`](tests/test_loop.py),
[`docs/specs/lightweight-loop.md`](docs/specs/lightweight-loop.md), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`README.md`](README.md), [`skills/learn/SKILL.md`](skills/learn/SKILL.md),
[`.gitignore`](.gitignore)

**Do:** take [`scripts/loop.py`](scripts/loop.py) and its test, and add `.loop/` to your
[`.gitignore`](.gitignore). Set `test_command` in a `loop.json` at your repo root to the
command that proves a change works, then try `python3 scripts/loop.py run --dry-run`.
It needs `git` and a signed-in `gh`.

## 2026-10-09: The harness lens is on by default

The lens now loads by itself in Claude Code: [`.claude/settings.json`](.claude/settings.json) names
this repo as a plugin marketplace, listed in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json), and
turns the lens on. Its README says how to install it from inside a session if
it doesn't show, and how to turn it off just for you.
`/orientation` now points at the line rather than asking you to load it.
The Set up section of [`README.md`](README.md) covers it too: trust the folder,
what the line looks like, and what to do when it doesn't show.

**Files:** [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json), [`.claude/settings.json`](.claude/settings.json),
[`examples/mods/harness-lens/README.md`](examples/mods/harness-lens/README.md), [`skills/orientation/SKILL.md`](skills/orientation/SKILL.md),
[`AGENTS.md`](AGENTS.md), [`README.md`](README.md)

**Do:** take [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json), and add the `extraKnownMarketplaces`
and `enabledPlugins` blocks from [`.claude/settings.json`](.claude/settings.json) to yours. Then restart
Claude Code at the root.

## 2026-10-09: The guard lets an existence check through

The guard refused `test -e .env`, the very check [`steering/data-and-tools.md`](steering/data-and-tools.md)
and the guard's own message tell the agent to use. `test -e`, `-f`, `-s` and
`[ -e … ]` on a credential file now pass. Anything else in the same command
still has to: `test -f .env && cat .env` is refused as before.

**Files:** [`.claude/hooks/guard.py`](.claude/hooks/guard.py), [`tests/test_agent_hooks.py`](tests/test_agent_hooks.py)

**Do:** take [`.claude/hooks/guard.py`](.claude/hooks/guard.py) if you haven't changed yours.

## 2026-10-09: Harness lens

A Claude Code mod that draws one line above the prompt naming which layer just
acted: the steering read, the skill followed, the last gate and how it went, a
tool the guard refused, the reviewer. `/lens` lists everything the harness did
in the session. It only looks, and it shows only this harness's own skills and
agents. `/orientation` now offers it at the end, for Claude Code users.

**Files:** [`examples/mods/harness-lens/`](examples/mods/harness-lens/), [`skills/orientation/SKILL.md`](skills/orientation/SKILL.md), [`AGENTS.md`](AGENTS.md),
[`README.md`](README.md), [`tests/test_steering.py`](tests/test_steering.py) (the house-style check skips what git ignores, so the
types Claude Code lays into a loaded mod don't fail it)

**Do:** nothing. To try it, start Claude Code from the harness root with
`claude --plugin-dir examples/mods/harness-lens`.

## 2026-10-08: File names are links

Every file or folder a Markdown file names is now a link to it, so you can
click from the README, a skill or a steering file straight to what it means.
[`scripts/link_files.py`](scripts/link_files.py) does it for the whole repo and is safe to run again;
[`steering/operating.md`](steering/operating.md) says to keep doing it.

**Files:** every tracked `.md` file, [`scripts/link_files.py`](scripts/link_files.py),
[`tests/test_link_files.py`](tests/test_link_files.py), [`steering/operating.md`](steering/operating.md)

**Do:** run `python3 scripts/link_files.py` after editing your own Markdown.
Read the diff before committing: it skips mentions of another project's
file, but a name it can't tell apart is yours to check.

## 2026-10-08: Two sessions, one clone

`building-and-testing.md` now says to give a second agent session its own git
worktree, so two sessions never share a branch or a checkout. The README now
opens with what a harness is, for someone who has never seen one, and shows
what shapes a session (what the agent reads and can skip, and what checks it)
and where something new goes, in the order `learn` uses.

**Files:** [`steering/building-and-testing.md`](steering/building-and-testing.md), [`README.md`](README.md),
[`docs/what-is-a-harness.gif`](docs/what-is-a-harness.gif), [`docs/what-shapes-a-session.gif`](docs/what-shapes-a-session.gif),
[`docs/where-it-goes.gif`](docs/where-it-goes.gif)

**Do:** if you run two agents at once, start the second in a worktree.

## 2026-10-07: Running one harness across teams

[`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) now says how strictness follows risk (a read-only project
against one that writes to something people use), how a change to the harness
travels from one person's mistake to everyone's `/whats-new`, and who owns
which part, with `CODEOWNERS` to make it hold.

**Files:** [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)

**Do:** nothing. If more than one person changes your harness, read "Who owns
what" and decide yours.

## 2026-10-07: CI for your own repos, and the deploy workflow

[`examples/ci/project-checks.yml`](examples/ci/project-checks.yml) is CI to copy into a repo in [`projects/`](projects/). It's
green on an empty repo and checks more as the repo grows. `deploying.md` has a
new section on the deploy workflow: one workflow with a caller per
environment, production started by hand with a typed confirmation, plan on
the pull request and apply only in the deploy, short-lived credentials.

**Files:** [`examples/ci/project-checks.yml`](examples/ci/project-checks.yml), [`steering/deploying.md`](steering/deploying.md),
[`steering/building-and-testing.md`](steering/building-and-testing.md), [`projects/README.md`](projects/README.md)

**Do:** copy [`examples/ci/project-checks.yml`](examples/ci/project-checks.yml) into each of your code repos as
`.github/workflows/checks.yml`, then require its jobs once they've run.

## 2026-10-07: Secret scan in CI

[`.github/workflows/secrets.yml`](.github/workflows/secrets.yml) runs gitleaks over the whole history on every
push to main and every pull request. The hook checks for secrets too, but
`--no-verify` skips the hook, and nothing skips this.

**Files:** [`.github/workflows/secrets.yml`](.github/workflows/secrets.yml), [`README.md`](README.md)

**Do:** take the file from the starter. After it has run once on a pull
request, add `secret scan` to your required checks. If it finds something,
rotate the secret first: deleting the commit doesn't un-leak it.

## 2026-10-07: CI should block, not just report

Nothing in your copy changes. CI runs the tests, the gate and the setup check
on every push, but until branch protection requires its checks, a red run
still lets the merge through. A check that blocks nothing is decoration.

**Files:** none. It's a setting on GitHub. [`steering/project-setup.md`](steering/project-setup.md) has the
steps.

**Do:** protect `main` and require CI's checks. Take the names from a run that
actually happened, not from the workflow file: unrenamed, they're
`checks (python 3.9)` and `checks (python 3.13)`. A wrong name waits forever
and blocks every pull request. Read the protection back to confirm it took.
Branch protection on a private repo needs a paid GitHub plan; on the free plan,
read every CI run before you merge.

## 2026-10-07: Example gate catches empty sections

The proposal example's gate now fails a required section that has a heading
and nothing under it: no text, only whitespace, or only an HTML comment. Each
one gets its own `empty section: <name>` line. An empty Fees section still
reports `no fee rows under Fees`, and a missing heading still reports only
`missing section: <name>`.

**Files:** [`examples/proposal/gates/proposal_gate.py`](examples/proposal/gates/proposal_gate.py), [`tests/test_gate.py`](tests/test_gate.py),
`CHANGELOG.md`

**Do:** nothing.

## 2026-10-07: What goes in the log

[`steering/operating.md`](steering/operating.md) now says which changes get an entry here: anything
new, anything that works differently, anything that moved, and anything you
have to act on. `whats-new` also stops at naming commands, and no longer
offers to merge the starter's changes, which can't work on a template copy.

**Files:** [`steering/operating.md`](steering/operating.md), [`AGENTS.md`](AGENTS.md), [`skills/whats-new/SKILL.md`](skills/whats-new/SKILL.md),
[`skills/review-pr/SKILL.md`](skills/review-pr/SKILL.md), `CHANGELOG.md`

**Do:** nothing. Add an entry when you change something noticeable.

## 2026-10-07: What's new

A release log, this file, and a skill that answers "what's new" from it,
including what the public starter has that your copy doesn't.

**Files:** `CHANGELOG.md`, [`skills/whats-new/`](skills/whats-new/), [`AGENTS.md`](AGENTS.md),
[`skills/review-pr/SKILL.md`](skills/review-pr/SKILL.md), [`skills/orientation/SKILL.md`](skills/orientation/SKILL.md), [`README.md`](README.md),
[`tests/test_changelog.py`](tests/test_changelog.py), [`tests/test_steering.py`](tests/test_steering.py)

**Do:** nothing. From now on, ask "what's new" after the starter changes.

## 2026-10-07: Building, testing and deploying steering

Two on-demand steering files. `building-and-testing.md`: spec first, small
changes, tests that fail when the behaviour breaks, never weaken a test.
`deploying.md`: infrastructure as code, the deploy script first, staging
before production, a known rollback, and a human yes for every production
deploy. `project-setup.md` now points at both instead of repeating them.

**Files:** [`steering/building-and-testing.md`](steering/building-and-testing.md), [`steering/deploying.md`](steering/deploying.md),
[`steering/project-setup.md`](steering/project-setup.md), [`steering/gates.md`](steering/gates.md), [`AGENTS.md`](AGENTS.md),
[`skills/learn/SKILL.md`](skills/learn/SKILL.md)

**Do:** nothing. Edit both to match how your team builds and ships.

## 2026-10-07: Gate guide

[`steering/gates.md`](steering/gates.md): whether a check earns a gate, the six places one can run
(skill step, Claude guard, git hook, CI, required check, release step) and
what each one misses, and the question each phase gate asks. Orientation now
adds a new gate to CI as well as the hook.

**Files:** [`steering/gates.md`](steering/gates.md), [`gates/README.md`](gates/README.md), [`steering/operating.md`](steering/operating.md),
[`skills/orientation/SKILL.md`](skills/orientation/SKILL.md), [`skills/learn/SKILL.md`](skills/learn/SKILL.md), [`AGENTS.md`](AGENTS.md)

**Do:** if you added a gate to the hook before this, add the same command,
with no file arguments, as a step in [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## 2026-10-07: Steering

Six light steering files in [`steering/`](steering/): how the agent operates, how it
replies, what data may go to which tool, writing, project setup and model
choice. Three load every session, through [`AGENTS.md`](AGENTS.md) and [`.kiro/steering/`](.kiro/steering/).

**Files:** [`steering/`](steering/), [`.kiro/steering/`](.kiro/steering/), [`AGENTS.md`](AGENTS.md), [`scripts/check_setup.py`](scripts/check_setup.py),
[`tests/test_steering.py`](tests/test_steering.py)

**Do:** read the three that always load, and edit them to sound like you.

## 2026-10-07: The proposal job moved to examples/

The root is generic now. The proposal job (its skill, gate, data, template,
review brief and finished proposal) lives in [`examples/proposal/`](examples/proposal/), and there's
one generic reviewer in [`agents/reviewer.md`](agents/reviewer.md) that takes a brief per job.

**Files:** [`examples/proposal/`](examples/proposal/), [`agents/reviewer.md`](agents/reviewer.md), [`gates/README.md`](gates/README.md),
[`.githooks/pre-commit`](.githooks/pre-commit), [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [`.claude/agents/`](.claude/agents/),
[`AGENTS.md`](AGENTS.md), [`scripts/check_setup.py`](scripts/check_setup.py)

**Do:** if you copied the starter before this, your proposal files are at the
old paths and block 2 of your hook points at the old gate. Keep your own
blocks, take block 2 from the starter, and run `python3 scripts/check_setup.py`.

## 2026-10-07: Your repos inside the harness, and two review skills

[`projects/`](projects/) for cloning your code repos into, so they work under the
harness's rules. `review-pr` and `review-tests`, a check for personal skills
that hide the repo's, and [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md).

**Files:** [`projects/README.md`](projects/README.md), [`skills/review-pr/`](skills/review-pr/), [`skills/review-tests/`](skills/review-tests/),
[`CLAUDE.md`](CLAUDE.md), [`.ignore`](.ignore), [`.gitignore`](.gitignore), [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md), [`scripts/check_setup.py`](scripts/check_setup.py)

**Do:** start the agent from the harness root, never from inside a project.
[`projects/README.md`](projects/README.md) has why.

## 2026-10-07: Orientation, company record, guards, learn and CI

`/orientation` sets you up: checks the clone, maps where your company's data
lives, interviews you for a company record, and builds the five layers around
your job. Claude Code guards refuse credential files and ask before a
connector changes anything. `learn` writes a correction into the file that
governs it. CI runs the tests, the gate and the setup check.

**Files:** [`skills/orientation/`](skills/orientation/), [`skills/learn/`](skills/learn/), [`company/`](company/),
[`.claude/settings.json`](.claude/settings.json), [`.claude/hooks/`](.claude/hooks/), [`.github/workflows/ci.yml`](.github/workflows/ci.yml),
[`scripts/check_setup.py`](scripts/check_setup.py), [`AGENTS.md`](AGENTS.md)

**Do:** run `git config core.hooksPath .githooks` if you haven't, then
`/orientation`.

## 2026-10-06: Starter skills list

[`STARTER-SKILLS.md`](STARTER-SKILLS.md): skills worth adding first, where they come from, and how
to make one your own.

**Files:** [`STARTER-SKILLS.md`](STARTER-SKILLS.md)

**Do:** nothing. Read it before you install an outside skill.

## 2026-09-23: The five layers

The starter itself: instructions, a skill, a gate, a hook and a review agent,
each tagged `step-1` to `step-5`, plus `review-skill` and the four loops.

**Files:** everything

**Do:** `git diff step-1 step-2` shows what one layer adds.
