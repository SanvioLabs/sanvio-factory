# How it works

Two pages on what's actually running when you use this factory: what makes it a
factory, what it's made of, where the loops are, how context is handled, and how much of it is code.

## What it's made of

Nothing here is a framework. It's files your coding agent already knows how to
read, plus a few short scripts that run whatever the agent decides.

| Piece | Is | Who runs it |
|---|---|---|
| [`AGENTS.md`](AGENTS.md) | Standing rules | The agent reads it at the start of every session |
| [`steering/`](steering/) | Standing guidance, one topic per file. Three load every session, the rest when needed | The agent, through [`AGENTS.md`](AGENTS.md) |
| [`skills/`](skills/) | Named procedures with inputs, steps and an output | The agent, when a request matches one |
| [`agents/`](agents/) | Instructions for a second reader with one job | A separate agent session, started by the first |
| [`gates/`](gates/) | Scripts that exit non-zero when work isn't ready | The agent, the git hook and CI |
| [`.githooks/`](.githooks/) | The check at commit | Git, whatever the agent decided |
| [`.claude/hooks/`](.claude/hooks/) | Checks before each tool call and at session start | Claude Code, whatever the agent decided |
| `company/`, [`projects/`](projects/) | Who you are, where your data is, your code | Read by the agent, never committed here |
| [`examples/`](examples/) | One worked job with all five layers, to read and copy | You, and the agent when you point it there |

The harness holds only the method. Your company record, your code and your
company's systems stay where they live, under their own access control, and
the harness records where they are. [Where things live](README.md#where-things-live) in the README
has the three places and how the agent reaches each.

The tool (Claude Code, Codex or Kiro) does the model calls, the tool calls, the
MCP connections and the context handling. The harness writes none of that. It
decides what the agent knows, what it's allowed to do, and what counts as done.

## What makes it a factory

The harness is one session's guides and guards: [`AGENTS.md`](AGENTS.md), [`steering/`](steering/),
[`skills/`](skills/), the hooks and the gates that a single agent works inside.
It decides what that agent knows, what it may do, and what counts as done.

The factory is the part that keeps going after the session ends. Issues
labelled for the loop are its queue. [The loop](#the-loop) plans each one, builds
it in a checkout of its own, runs the tests and opens a pull request. A second
agent reviews that pull request, and the gates and required checks stand
between it and a merge. You decide what goes on the queue and what merges, and
handing an issue to another factory waits for your yes too. The loop never
merges a pull request.

Another factory can take an issue through the same contract: a label on an
issue goes in, and a pull request that closes it comes back to be reviewed.
[Handing work to another factory](#handing-work-to-another-factory) shows how this repo hands an issue to
another team's delivery system, or to a second copy of itself, on github.com,
and treats what comes back the way it treats its own loop's work. It's new:
[Getting to ready](factories/README.md#getting-to-ready) says what a run can show today and what it
can't yet. For developers, it's one interface with many implementations, and
the loop is the implementation that ships here.

## A request, start to finish

1. You ask for something. The tool has already loaded [`AGENTS.md`](AGENTS.md), and in
   Claude Code the name and description of every skill. A skill's full steps
   load only when a request matches it, so twenty skills cost little until one
   is used.
2. The agent follows the skill's steps. Before each tool call, the guard
   checks it: credential files are refused, and a connector call that isn't
   named as a plain read asks you first.
3. The skill ends at a gate. The agent runs it, fixes what it names, and runs
   it again until it passes. That's the first loop.
4. A review agent reads the result in its own fresh context and reports
   findings. It never edits.
5. You commit. The git hook runs the same gate and the secret check. You push,
   and CI runs everything again.

## Where the loops are

- **Fix and recheck**, inside a session: gate fails, agent fixes, gate runs.
- **At commit and at push**: the same checks, run by git and CI rather than
  by the agent's good intentions.
- **A stamp goes stale**, on one piece of work: each check stamps a fingerprint
  of the text it passed, in order, and an edit sends it back through them.
  [`examples/proposal/gates/stamp.py`](examples/proposal/gates/stamp.py) is the small version.
- **Close the gap**, between phases: the phase gate names what's missing and
  what closes it, you close it, and the gate runs again.
  [`examples/proposal/gates/phase_gate.py`](examples/proposal/gates/phase_gate.py) is the small version.
- **Mistake to rule**, across sessions: when the agent gets something wrong,
  [`skills/learn/`](skills/learn/) writes the rule into the file that governs it.
- **Sprint report**, across people: each person's usage log records which
  skills, agents and guards fired. At sprint end, `factory-trends` turns it into
  a short report with their proposals, shared as a pull request. The owner reads
  the sprint's reports together and takes what earns a place.

**The runner**, across tickets, is the fifth, and [`scripts/loop.py`](scripts/loop.py)
is the small version of it. It picks up an issue labelled `loop-ready`, starts
a fresh agent session to build it, runs your tests and a review, and repeats
until both pass or it gives up and asks a person. Each round starts clean and
reads its state from files (the ticket, the diff, the test output), not from a
growing transcript. That's the same shape as this repo, run headless with
`claude -p` instead of you at the keyboard. [The loop](#the-loop) below has
the rest.

## The loop

`python3 scripts/loop.py run` takes one issue through the flywheel and then
the next. Nothing runs until you start it, and it never merges.

| Step | What happens | Left behind in `.loop/issue-N/` |
|---|---|---|
| Discover | The next open issue labelled `loop-ready` that isn't assigned to someone else, skipping one still waiting on an open dependency until it closes. A dependency counts as met when a merged change closes it; one closed by hand blocks the issue, with a comment saying why. On a `base` that isn't the default branch, a merged pull request into `base` whose body closes the dependency counts. Only the 200 most recently opened pull requests merged into `base` are read, so an older dependency is refused until someone takes the `Depends on` line out | `ticket.md` |
| Shape | A fresh agent writes the smallest plan that would count, plus the check that proves it | `plan.md` |
| Build | A fresh agent makes the change in a git worktree, outside your clone (`~/.sanvio-loop/`). Once the pull request is merged or closed, the loop removes the worktree and its branch while it's idle, unless the worktree has changes or the branch has commits the pull request doesn't. A pull request someone rebased or amended is still tidied, as long as the branch is still the commit the loop pushed. While it's idle the loop also merges the base into an open pull request whose only conflict is in [`CHANGELOG.md`](CHANGELOG.md). An `UPDATE` line says how that went: `merged <base>, kept both CHANGELOG.md entries` means it pushed the merge, and `kept: <why>` means it pushed nothing, with the reason, such as a conflict in another file or failing tests. It tries each commit of the base once per issue, and the tests' output goes to `.loop/issue-<N>/update-output.txt` | the commit |
| Validate | The script runs your test command. A second fresh agent reads the diff and the output and says PASS or FIX | `test-output.txt`, `diff.patch`, `review.md` |
| Scale | On PASS, and if the issue is still open, it opens a pull request that says `Closes #N`, the files changed, the last test lines, the review in full and the plan (collapsed), and comments the link on the issue. A blocked issue gets a comment saying why. It writes what went wrong into `.loop/lessons.md`, in the shape [`skills/learn/`](skills/learn/) reads, then takes the next issue | the pull request |

Build and Validate repeat up to five rounds. After that the issue is labelled
`loop:blocked` and the loop moves on without it. A round after the first that
adds nothing new ends the run there, blocked, with the agent's reply quoted on
the issue: the tests and the review would only repeat. A pass needs the tests to exit 0
**and** the review to say PASS: the script runs the tests, so the agent never
grades its own work.

The review says FIX only when the tests failed, a requirement in the plan has
no test, a build with `test_first` on worked around the tests written first, or
the change would cost something real if it merged, such as wrong behaviour, a
security or privacy gap, or lost data. Anything else it finds, such as an
untested extra the plan didn't ask for, goes in its table on the pull request
for the person who merges, and costs no round.

![scripts/loop.py takes issue #12 through five steps. Discover picks the loop-ready issue and writes ticket.md. Shape: a fresh agent writes plan.md. Build: another fresh agent makes the change in a worktree outside the clone. Validate: the script runs the tests and a second agent reads the diff; round 1 fails with review FIX, so it goes back to Build. Round 2 passes the tests and the review says PASS. Scale opens a pull request that closes #12 and doesn't merge it, and what went wrong goes to lessons.md. Each step writes one line to .loop/loop.log as it happens.](docs/one-issue-through-the-loop.gif)

**Watch it** with `tail -f .loop/loop.log`, or run it in tmux and attach: the `loop-control` skill starts it that way when tmux is installed, and a run inside tmux logs a `START` line with the attach command. One line per event, the issue
first, nothing secret in it:

    2026-10-09T20:14:52 #12 VALIDATE round 1 tests failed (2) review FIX
    2026-10-09T20:19:30 #12 VALIDATE round 2 tests passed review PASS
    2026-10-09T20:19:44 #12 SCALE PR opened https://github.com/you/repo/pull/31

Point a dashboard or a Slack post at that file and you have a monitor.
`.loop/status.json` holds the same state for a tool to read rather than parse:
`running`, when the run `started` (UTC), the `tmux` session it's in (when it was started in one), the
`queue` of ready issues waiting, and one row per issue, newest
first, with its `step`, `round`, `state` (`working`, `pr`, `blocked`,
`stopped` or `skipped`), the last `tests` and `review`, and the `pr` link.
A row also has `step_started`, when the current step began (`null` once the row
is out of `working`), and `step_seconds`, the whole seconds spent so far on each
step that has finished, by step name, with rounds summed. `step_seconds` covers
the current run only and starts empty on each new run, unlike `tokens` and
`cost_usd`, which count every run. A row from before these fields, or one no run
has started since, has neither.
It's rewritten whole at each step, so a reader never sees half of it.

In Claude Code, `/loop-pane` draws it in a pane beside the conversation
([`examples/mods/loop-pane/`](examples/mods/loop-pane/)). On a Mac, a run inside tmux also writes
`.loop/watch.command`, and the pane's **Watch it** button opens it: a new
Terminal window attached to the session, read-only.

What the loop cost, day by day and by issue, and how many of its pull requests
needed someone's commit before merging, come from `python3 scripts/dashboard_data.py --json`.
In Claude Code, `/factory-dashboard` draws them in a pane, off by default
([`examples/mods/factory-dashboard/`](examples/mods/factory-dashboard/)).

**What an issue used.** When the agent is `claude`, each run's tokens and cost
go in `.loop/issue-N/usage.json`: one entry per run (plan, each build round,
each review) with its `step`, `round`, the four token counts and `cost_usd`.
The issue's row in `status.json` carries the totals as `tokens` and `cost_usd`,
`loop.log` gets a `USAGE` line per run, the pull request has a `## Usage`
table, and a block comment says what the run used before it stopped. A run that
reports nothing, such as one from `codex` or `ollama`, or one that timed out, is
`null` and "not reported", never 0. The dollar figure is Claude Code's estimate
at API prices; a subscription is billed differently. Under `--project`, the
file is in `.loop/projects/<name>/issue-N/`. A `claude` command in `loop.json`
that sets its own `--output-format` keeps it, and its usage is read only when
that's `json`.

**Which model ran.** Each run also records its model: the one `claude`'s
`init` event names, or, without one, the model the setting names, so
`ollama:qwen3:8b` records `qwen3:8b`. A bare `codex` or a command line records
`null`. For a `claude` run, the issue's window shows `· model <id>` ahead of
its first tool call and the status row's `model` takes it, so the row holds the
model the last `claude` run started on. Every run's `USAGE` line in `loop.log`
names it after the round (`model unknown` when it's `null`), each `usage.json`
entry has it as `model`, and the pull request's `## Usage` table has a Model
column. Entries written before this read as `unknown`.

**A history of runs.** Each run of an issue that ends (`pr`, `blocked`,
`stopped` or `skipped`) adds one line to `.loop/history.jsonl`, under
`--project` `.loop/projects/<name>/history.jsonl`. The line is JSON with
numbers and labels only: `v` (1), `run` (the issue and when the run started),
`issue`, `project` (`null` for this repo), `started`, `ended`, `outcome`,
`rounds`, `tests` and `verdicts` (one per round that reached its review), the
run's `tokens` and `cost_usd` (`null` when not reported), and the `agent` and
`reviewer` command names, never a path. No title, note, link or review text
goes in it. Lines are only ever added, never changed, so a relabelled issue's
second run is a second line. A worker that fails is recorded as `blocked`. A
run cut short by a Ctrl-C, or by the loop itself being killed, leaves none.
It stays on this machine, because `.loop/` is gitignored. If the line can't be
written, `loop.log` gets an `ERROR` line and the run ends as it would have.

**A token budget.** Set `max_issue_tokens` in `loop.json` to a whole number and
the loop counts the tokens one run of an issue has used, over its plan, builds
and reviews. Before each build and before each review it checks: over the
number, it starts no more agents and blocks the issue, and the block comment
says `used N tokens this run, over max_issue_tokens M`. A run already started
always finishes, so one run can overshoot by up to a run's worth. Relabelling
the issue starts a fresh budget, though `usage.json` keeps the earlier runs.
Only a run that reports its tokens counts, so `codex`, `ollama` and a timed-out
run add nothing, and the loop logs a `WARN` at start-up naming each such
agent. `0` or empty means no budget; anything else that isn't a whole number
above 0 stops the run before it takes an issue.

A running loop keeps the code it started with: when [`scripts/loop.py`](scripts/loop.py) changes
on disk under it, it logs one `STALE` line on an idle poll and carries on, and
`python3 scripts/loop.py stop` then starting it again picks up the new code.

**More than one at once.** Set `max_workers` in `loop.json` and it works up to
that many ready issues side by side, each in its own worktree. One that depends
on an issue still being worked waits for it. So does one held by a path: when a
ticket's Scope **In** names, in backticks, a file or folder that a running
issue's ticket also named, it waits until that issue's worker ends, and any
ready issue that doesn't overlap can start meanwhile. [`CHANGELOG.md`](CHANGELOG.md) never holds anything: nearly every ticket names it, and a
hold wouldn't stop two entries conflicting. The loop merges a conflict in [`CHANGELOG.md`](CHANGELOG.md) alone itself instead, once it's idle: it merges the base into the pull request, keeps both sets of entries with the branch's on top, runs the tests, and pushes if they pass. The log says
`#13 HELD waits on #12 for src/app/main.py` once, its queue row in `status.json`
has `waiting_on` and `held_path` while it's held, and with more than one worker
a `--dry-run` prints a `HELD` line for each issue that overlaps its pick. The
loop only knows what tickets name: it won't notice an agent editing a file its
ticket left out, and a worker ends once its pull request is open, so an open
pull request holds nothing. Each issue's agents write what
they say to `.loop/issue-N/agent.log` as they say it. A `claude` agent's
window also shows each tool call it makes by its name and target, such as
`→ Read scripts/loop.py`. Run inside tmux, each
issue also gets a window named `issue-N` that follows that file and closes
when the issue ends, and while it's open the issue's row in `status.json`
names it as `window`. On a Mac the run also writes `.loop/issue-N/watch.command`
for that window, which the pane's **Watch** on the issue opens read-only. A stop
starts nothing new and lets each running issue finish its step. Every worker
runs its own agent sessions, so usage grows with the number of workers.

**Make it yours** with a `loop.json` at the repo root. Any key you leave out
keeps its default:

| Key | Default | Is |
|---|---|---|
| `agent` | `claude -p --permission-mode acceptEdits` | The command that builds, or a name: `claude` or `codex`, with `:<model>` if you like. `ollama` can't build: it has no tools to edit files with. The prompt arrives on stdin, so any other command line works the same way |
| `reader_agent` | `claude -p` | The command that plans and reviews, or a name: `claude`, `codex` or `ollama:<model>`. It's told not to edit, and anything it edits is thrown away. Held to read tools in the checkout when it's `claude`; for `review`, it has to be `claude` or `ollama:<model>` |
| `review_agent` | empty | The command that reviews, when it's set, or a name: `claude`, `codex` or `ollama:<model>`. Empty means `reader_agent` reviews. Held to read tools the same way, and for `review` it has to be `claude` or `ollama:<model>` |
| `test_command` | `python3 -m unittest discover -s tests` | Run by the script, in the worktree |
| `generate_command` | For this repo, `UPDATE_SAMPLE=1 python3 -m unittest tests.test_dashboard_data.Sample; python3 scripts/draw_dashboard.py`. For a project, empty | Run by the script after each build, before the commit, in the worktree, with the same environment and timeout as `test_command`. What it writes goes in that round's commit, for files the build agent can't make itself. Empty runs nothing. One that fails logs a `GENERATE` line with its exit code, and the round goes on |
| `setup_command` | empty | Run by the script once per worktree, before the planner, with the same environment and timeout as `test_command`, such as `npm ci`. Empty runs nothing. It logs `SETUP done` when it passes. One that fails or times out blocks the issue, with its output kept in `.loop/issue-N/setup-output.txt` and off the public comment. On a branch that already has the loop's commits and no record of setup, it doesn't run and the issue blocks, since it would run what an agent wrote; remove the worktree and the branch to start over. One that passes but leaves anything git would commit blocks too, naming the paths, so it may write only what git ignores. A blocked setup runs again when the issue is put back; a passed one doesn't, even if the command changes, until the worktree is removed |
| `test_first` | `false` | Only `true` turns it on. A separate agent writes failing tests, in new files only, after the planner and before round 1, and the build has to make them pass without changing them. The issue blocks if the tester changes nothing, changes or deletes a file that already existed, changes a path outside `test_paths` or a lockfile, or its tests already pass. A build that changes or deletes one of its files blocks too. A branch with a `round 0 (tests)` commit skips the tester and keeps that commit's files fixed |
| `tester_agent` | empty | The command that writes the tests, named the same way as `agent`. Empty means `agent` |
| `test_paths` | `["tests/**"]` | Globs for the files the tester may write. `*` stays within a folder and `**` crosses folders. For a project, set it in the factory's `projects` entry |
| `base`, `max_rounds` | `main`, `5` | Where branches start, and rounds before giving up |
| `builder_runs_tests` | `false` | Only `true` turns it on, and only for a `claude` build agent. The build agent may then run `test_command`, and nothing else new, inside its round, and is asked to fix what fails before it finishes. The loop still runs the tests after it and the reviewer still reads them. Measured on a local model, it took fewer rounds and about a quarter less time for the same scores |
| `max_workers` | `1` | How many issues it works at once. Each runs its own agent sessions, so usage grows with it |
| `max_issue_tokens` | `0` | Tokens one run of an issue may use before it's blocked. `0` means no budget. *A token budget* above has the detail |
| `retro` | `false` | Only `true` turns it on. Each entry in `.loop/lessons.md` then gets findings on why the lesson reached the agent late, from one more `reader_agent` run over the run's session logs in `~/.claude/projects`, with the digest in `.loop/issue-N/evidence.md`. A finding that cites a record not in the logs is dropped, and one the logs don't bear out says `(unverified)`. A file [`CLAUDE.md`](CLAUDE.md) loaded may not appear in the logs, so a finding about one can say that wrongly. A session with no log, such as a Codex run, says `no session log`. It runs after the pull request opens or before the block, and if it fails, times out or is over budget, the entry says unclassified and the run ends the same. On a pass its tokens are in `usage.json` but not in that run's `history.jsonl` line |
| `hours` | empty | When `run` and `review` may start something, in local time, such as `Mon-Fri 09:00-17:00`. Empty means any time; `--hours` replaces it for one run. *In working hours* below has the format |
| `worktree_dir` | `~/.sanvio-loop/<repo>` | Where the build checkouts go. Keep it outside the clone: an agent started inside it loads this repo's [`CLAUDE.md`](CLAUDE.md) twice and stops to ask you to restart from the root |
| `ready_label`, `blocked_label` | `loop-ready`, `loop:blocked` | What it looks for, and what it leaves on a failure |
| `review_query` | `review-requested:@me` | The GitHub search `loop.py review` runs to find pull requests that ask for you |
| `review_label` | empty | A label whose open pull requests `loop.py review` also takes, as well as the ones `review_query` finds, each once per head commit. Empty means off. Only the factory's `loop.json` or its `projects` entry sets it, never a project's own |
| `label_own_prs` | `false` | Whether `run` puts `review_label` on each pull request it opens or pushes to, so `review` takes it. Needs `review_label` set. A label that isn't added is an `ERROR` line in the log, and the issue isn't blocked. Only the factory's `loop.json` or its `projects` entry sets it, never a project's own |
| `review_logins` | empty | The GitHub logins whose review a round reads, such as the person who hands this loop issues as a factory. Empty means the login the loop runs as. Only the factory's `loop.json` or its `projects` entry sets it, never a project's own |
| `review_rubric` | [`review-rubric.json`](review-rubric.json) | The file, from the factory's root, that turns a posted review's verdict into a grade out of 10. *The grade on a review* below has the detail. Only the factory's `loop.json` or its `projects` entry sets it, never a project's own |

To have one model build and another review it, set the two apart:

    "agent": "claude -p --model <one model> --permission-mode acceptEdits",
    "review_agent": "claude -p --model <another model>"

Or name the tool, and the loop gives it the flags its job needs. Codex
reviews, in its read-only sandbox, with:

    {"review_agent": "codex"}

To build with Claude and review with a model on your own machine:

    {"review_agent": "ollama:qwen3"}

A name can carry a model, as in `claude:<model>` or `codex:<model>`. Ollama
needs one. A name that can't do its job, `ollama` as `agent` or `ollama` with
no model, stops the run before it takes an issue, and the log says why.

**Before the first run,** run `python3 scripts/check_setup.py` and fix any FAIL. A
warning the harness's session-start hook prints (an unset `core.hooksPath`, for
instance) is the first thing every agent session says, and it ends up at the top of
`plan.md` and the review.

**Try it** on a private copy first. On a clone of the public Sanvio Factory,
the first real run opens a public pull request. Label one small issue
`loop-ready`, then:

    python3 scripts/loop.py run --dry-run    # which issue it would take, then stop
    python3 scripts/loop.py run --once       # one issue, then stop
    python3 scripts/loop.py run --issue 12   # only issue #12
    python3 scripts/loop.py run              # every ready issue, until none are left
    python3 scripts/loop.py run --for 8h     # every ready issue, taking no new one after 8 hours

Then read `.loop/issue-N/` and the pull request it opened.

**For a set time.** `--for` takes a whole number then `m`, `h` or `d` (`90m`,
`8h`, `2d`), and works on `review` too. The loop logs an `UNTIL` line with the
local time it ends. After that it starts no new issue or review, lets each
running one finish (an issue still gets every round, to a pull request or a
block), logs `END --for 8h reached` and exits. Any other value for `--for` is
refused before the loop starts. `loop.py stop` still ends it sooner.

**In working hours.** `"hours": "Mon-Fri 09:00-17:00"` in `loop.json`, or
`--hours "Mon-Fri 09:00-17:00"` on `run` or `review` for one run (it replaces
the `loop.json` value), keeps the loop to those hours in the machine's local
time. Days are `Mon` to `Sun`, capitalised as shown (`mon` is refused), alone, as a range (`Fri-Mon` wraps) or in a
comma list (`Mon,Wed-Fri`), then `HH:MM-HH:MM` on a 24-hour clock. A window
that crosses midnight belongs to the day it starts: `Fri 22:00-06:00` covers
early Saturday, not early Friday. Outside the hours the loop starts no new
issue or review, lets a running one finish every round, logs one `HOURS` line
with the next start, and waits, so `run --hours "Mon-Fri 22:00-06:00"` works
the queue on weeknights only. A value it can't read logs an `ERROR` and the
loop exits before it takes anything. With `--for` as well, the run still ends
on time, waiting or not.

**The build agent doesn't install packages.** This is the default, and it
stays the default. The agent can edit files, but `npm install`, `pip install`
and anything else that fetches a package need an approval nobody is there to
give, unless your own `~/.claude/settings.json` or the checkout's
[`.claude/settings.json`](.claude/settings.json) already allows it, so check both. A ticket whose work
needs a package the agent has to install blocks in the first round after the
first that adds nothing.

What the agent can still do is edit `package.json`, `pyproject.toml` or a
lockfile, and the script runs `test_command` with no approval at all. So use a
test command that installs only what the committed lockfile says and fails when
the manifest disagrees with it: `npm ci && npm test`, or `uv run --locked
pytest`. A fresh checkout has no `node_modules`, so a Node project needs that
`npm ci` anyway. In the pull request, read any manifest or lockfile change
before you merge it.

To have the packages there before the agents start, so the planner and the
build agent can see them, set `setup_command` to the same locked install, such
as `npm ci` or `uv sync --locked`. Setup runs with no approval, like
`test_command`, so don't use a command that can pull anything the lockfile
doesn't name, such as `npm install`. It runs once for each worktree, with every
variable named like a token removed.

To give a ticket a new dependency, add it yourself first:

- Commit the dependency and its lockfile straight to `base`, and the ticket
  needs nothing more. Or open an issue for it, leave `loop-ready` off it, and
  merge a pull request that says `Closes #N`. Then put `Depends on #N` on the
  ticket, naming that issue rather than the pull request: the loop blocks a
  number that isn't an issue, or an issue closed by hand. On a `base` that
  isn't the default branch, a merged pull request into `base` whose body closes
  the issue counts. Only the 200 most recently opened pull requests merged into
  `base` are read, so an older dependency is refused until someone takes the
  `Depends on` line out.
- If the ticket has already blocked, its old checkout and branch are reused as
  they are when it's relabelled, without your dependency. Remove both first,
  `git worktree remove <worktree_dir>/issue-N` then `git branch -D
  loop/issue-N`, then take `loop:blocked` off and put `loop-ready` back.

A team that wants its loop to install can allow it, in the factory's
`loop.json`; with `--project`, under `"projects"` there, as described below. Name
the commands the build agent may run:

    {"agent": "claude -p --permission-mode acceptEdits --allowedTools \"Bash(npm install --ignore-scripts *)\""}

That works for a `claude` agent only. `codex` ignores `--allowedTools`, and a
full command line replaces `claude:<model>`, so add `--model` if you had one.
It's the team's decision, not the factory's default, and it lets an agent
nobody is watching pull any package the registry has. Without
`--ignore-scripts`, that package's install scripts also run on the machine
with your full environment, including the tokens the test command is denied.
Allow the narrowest command that does the job. With `--project`, the agent
setting is read from the factory's `loop.json`, never from the project's, so
whoever can merge to the project's repo can't widen it. A private
registry's token won't reach `test_command`, which runs with every variable
named like a token removed.

Allowing installs also means setting `"allow_lockfile_changes": true` in the
same factory `loop.json` (with `--project`, in the project's `"projects"`
entry there; the project's own file can't set it), because an install rewrites
the lockfile. Until it is set, a round whose commit adds, edits, deletes or
renames a lockfile, at any depth
(`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `uv.lock`, `poetry.lock`,
`Cargo.lock`, `go.sum`, `Gemfile.lock`, `requirements*.txt` and the like),
blocks the issue before the tests run. The check reads every commit the loop
made on the issue's branch, so a blocked round's lockfile still blocks the
issue when it is put back on the loop. The comment on the issue names the
paths and says to put the dependency and its lockfile on `base` yourself and
drop the agent's commit (reset the branch to `origin/<base>`), or to set that
key. If git can't list those commits, the issue is blocked too, with no tests.
The commits are recognised by the `Loop: issue #N, round` line in their
message, so a commit the agent makes itself, without that line, isn't counted.
A lockfile you commit on the branch yourself isn't counted either. Any value
but `true` or `false` is an `ERROR` when `run` starts, and no issue is taken.
A manifest edited on its own isn't caught, so a `uv` or `cargo` test command
should pass `--locked` (`uv run --locked`, `cargo test --locked`), which fails
when the lockfile disagrees with it.

**An issue put back while its pull request is open** is a round on that pull
request, which is how a review that asks for changes comes back. Only the
loop's own pull request counts: one from this repo, into its base, whose head
is where `origin`'s branch is. One from a fork on a branch of the same name
doesn't. The loop fetches `loop/issue-N` from `origin` and resets the issue's
branch to it, so it builds on what the pull request shows, and logs a line if
that drops commits here that were never pushed. Changes in the worktree that
were never committed block the issue instead, and nothing is reset. The
planner gets the newest review of that head: the comment starting
`<!-- loop-review-pr-report -->`, posted by a login in `review_logins` (by
default the one the loop runs as), whose last line names the head's commit,
newest by its last edit. Anyone who can read the repo can comment, so no one
else's comment is read. The review
comes after the ticket as evidence, never instructions, and the planner
restates in its own words only the changes the ticket backs. The push isn't
forced, so a branch that moved during the round still blocks. No second pull
request opens: the log says `PR updated`, and the ready label comes off. If
the pull request was closed or merged during the round, or its state can't
be read, the round pushes nothing and blocks the issue: a close a person made
stays made. So does a round that leaves the branch where the pull request
already is. It asks GitHub only when `origin` has the branch, so a new issue
runs as before.

**What the review can see.** The reviewer gets the plan, the diff and the
script's test output. With the default `reader_agent` it can't run commands,
so it checks the rest by reading the code. If the proof is a command, put
that command in `test_command`, which the script runs itself. That includes
end-to-end tests: `npm test && npx playwright test` runs them every round, and
makes each round slower.

**Coverage, if you want it.** Put it in `test_command`, for instance
`"test_command": "uv run pytest --cov --cov-fail-under=80"`. The number is
the project's to choose, and a round below it fails like any other test
failure. A coverage pass shows which lines ran, not that a test would catch
a change to them; [`skills/review-tests/`](skills/review-tests/) checks that.

**On a project under [`projects/`](projects/).** Run it from the harness root with
`--project`, on `run`, `review` and `stop`:

    python3 scripts/loop.py run --project projects/app
    python3 scripts/loop.py stop --project projects/app

It then works that clone's GitHub repo: its issues, its pull requests and the
`base` in its own `loop.json`. That `loop.json` has to set `test_command`,
because the default tests this repo. For a TypeScript project,
`{"test_command": "npm test"}`, or `node --test` with no `package.json`
script; [`examples/typescript/`](examples/typescript/) has a fuller one. The loop refuses, with one
`ERROR` line and before it takes anything, a folder that isn't directly under
[`projects/`](projects/), one that isn't a git clone of its own, a clone whose `origin`
isn't on github.com, or a `loop.json` without `test_command`.

Which `loop.json` sets what: the project's own sets only `test_command`,
`test_timeout`, `base`, `ready_label`, `blocked_label`, `generate_command` and `setup_command`. Every other key,
`agent`, `max_workers` and `allow_lockfile_changes` among them, comes from the
factory's `loop.json`, and can be set for one project under `"projects"` there,
keyed by the folder name:

    {"max_rounds": 3, "projects": {"app": {"agent": "claude", "max_workers": 2}}}

The order is the defaults, the factory's other keys, its `"projects"` entry for
the folder, then the project's own seven. One of the seven the project leaves out
is the default, not the factory's value: the factory's `base` describes the
factory. A project's `loop.json` that sets one of
the others is refused with an `ERROR` line naming the key, because a clone
anyone can merge to mustn't choose what the loop runs or spends. Without
`--project`, `"projects"` is ignored. Its state stays in
the factory, in `.loop/projects/<name>/` (`status.json`, `loop.log`,
`issue-N/` and a lock of its own, so it runs beside the factory's own loop). None of
it goes in the project's folder, which gets only the `loop/issue-N` branches
and their checkouts, as any clone the loop works does. Its checkouts go in
`~/.sanvio-loop/<factory>/<name>/`. A checkout of the project holds none of
the harness's rules, so every prompt starts with [`AGENTS.md`](AGENTS.md) and the three
steering files it loads every session, and says
the project's own `AGENTS.md` or `CLAUDE.md` adds to them and never loosens them. A `claude` build agent also
gets the harness's [`.claude/hooks/guard.py`](.claude/hooks/guard.py) through `--settings`. Another
build agent, such as `codex`, has no hook to put it in, so it builds without
the guard. The loop pane shows the factory's own loop only.

**From a conversation,** the [`skills/loop-control/`](skills/loop-control/) skill does the same jobs:
it checks an issue is ready before labelling it, starts the loop, says what
it did, and stops it with the label off first.

**Rules it keeps.** To take an issue off the loop, the label comes off first and
then the run stops, because stopping alone lets the queue pick it straight back
up. `python3 scripts/loop.py stop` ends a running loop at its next step. A lock
file stops two loops running in one clone. On your machine it uses your own
agent sign-in and holds no credentials; in [GitHub Actions](#off-your-laptop) the
agent needs a key, held as a repository secret. A ticket is an instruction to an
agent, so label only issues you wrote or have read.

**Whose issues it builds from.** An issue written by the repo's owner, a member
or a collaborator is taken as it stands. Anyone else's is taken only as it was
when it was labelled `loop-ready`: if its title or body changed after the label
went on, or it holds an HTML comment (text the issue's page doesn't show), the
loop blocks it and says why on the issue. Read it again and label it again, or
copy what it asks into an issue of your own. The loop reads the issue fresh at
that check, so the text it checked is the text the agents get.

**What the issue's text can reach.** The planner and the reviewer run in the
build checkout with read tools only, so they can't read the rest of your clone
(`company/`, [`projects/`](projects/)) into a plan that ends up in a pull request.
The build agent gets the ticket's exact wording where the planner copies it into the plan, so it's steered by the issue too.
The loop commits with git hooks off, so a hook the agent writes doesn't run. It runs your
test command without anything named like a secret in its environment (tokens,
keys, passwords, `AWS_*`, the SSH agent). The tests still run code the agent
wrote, as you, so they can reach whatever your user can on disk. Run the loop
as a user, or on a machine, with nothing you'd mind a test reading.

**Reviewing pull requests.** The issues are half the queue; pull requests waiting
on your review are the other half. Start it on the machine the loop runs on, in
its own tmux session. It takes the same lock as `run`, so one process works a
clone at a time: to run both at once, give each its own clone. `review --pr N`
is the exception: a person asked for that one pull request, so it runs while
the loop runs and outside `hours`, holding a lock for that pull request alone,
which the loop's own review of it waits on too. Each reads the commit the
other reviewed, so the watcher never reviews a head `--pr` already did, and
`--pr` reviews again a head whose review failed. A review names origin's repo
to `gh` on every call, so a comment can't land on another repo's pull request,
and refuses in one line, before any call, when origin as git fetches it isn't
on github.com.

    python3 scripts/loop.py review --once    # review what is waiting, then stop
    python3 scripts/loop.py review           # then keep watching, every poll_seconds
    python3 scripts/loop.py review --pr 31   # review pull request 31 alone, then stop

It lists the open, non-draft pull requests that match `review_query` or carry
`review_label`. For each
new head commit it checks the pull request out detached, outside your clone, in
`~/.sanvio-loop/`, and has a fresh `reader_agent` follow
[`skills/review-pr/`](skills/review-pr/) for the change between the base and the
head. The agent ends its report with a verdict line, `VERDICT: ready`,
`VERDICT: ready with nits` or `VERDICT: changes needed`. The script, not the
agent, posts the report: one comment per pull request, marked, edited in place
on the next commit (only its own: a marked comment with another header, such as
a person's send-back, is left as it is), and ending in a trailer that names the whole commit and
the verdict the report's last line gave, or `unreadable` when it isn't one of
those or the report had to be cut to fit one comment, since its last line
then isn't posted. Every `<` in the report is escaped, in code too, every
footnote marker too, and a fence it leaves open is closed, so no tag, HTML
block, footnote or fence can hide the trailer on the page, wherever a list or
a quote puts it; code in a review shows `&lt;` for `<`. It's the same
comment-edited-in-place pattern as [`examples/ci/review-pr.yml`](examples/ci/review-pr.yml), on the machine
that already runs the loop and with no CI minutes. It writes one line per
review to the same log:

    2026-10-13T09:02:11 - REVIEW #31 4f2a9c1 posted
    2026-10-13T09:02:12 - REVIEW #32 7be03d8 skipped (draft)
    2026-10-13T09:11:40 - REVIEW #33 c19e5a2 failed: agent exit 1

A commit is reviewed once against each base. The result goes in
`.loop/status.json` under `reviews` with the base its diff was read against,
so a poll that sees the same commit on the same base again starts no agent; a
pull request retargeted since, or a review recorded before reviews kept their
base, is reviewed again. With
`--pr N` the result goes in `.loop/review-pr-N.json` instead, since a loop
running in that clone rewrites `status.json` whole; the log goes to stderr,
and stdout is one JSON line for that pull request: its `number`, the `sha` and
`state` of its newest review, a `note`, the `verdict`, and the `base` its
diff was read against. While another
review of it is running, the line's `state` is `not reviewed` and its `note`
says so. Each pull request `--pr` or the watcher reviews keeps a
`.loop/review-pr-N.lock` beside its result, one pair per pull request, never
cleared; on a system with no file lock (Windows), `--pr` refuses and the
watcher reviews without one. Each review fetches the pull request's head into
`refs/loop/review-pr-N` and its base into `refs/loop/review-base-N`, refs of
their own in the clone, kept like the lock and replaced on the next review.
Before it reviews, each reads both `status.json` and the pull request's own
file again, so a head the other just reviewed isn't paid for twice. A review
whose agent exits non-zero or times out posts nothing, and it isn't tried again
until the pull request has a new commit; neither is a diff that can't be made,
such as a base with no history in common. A fetch, checkout or GitHub error is
logged once with `(will retry)` and tried again on the next poll.

**The grade on a review.** The trailer's line also carries a grade out of
10, after the verdict, such as `Verdict: ready with nits. Grade 8/10: ready
with nits, checks passing.` It comes from
[`review-rubric.json`](review-rubric.json) at the factory's root, which gives
each of five keys a whole number from 0 to 10: `ready`, `ready with nits` and
`changes needed` for the verdicts, `failing` for a reviewed commit with a check
run that finished and didn't pass (success, neutral and skipped pass), and
`unreadable` for a verdict that isn't one of the three. The checks are the
reviewed commit's check runs, not the pull request's newer head. A commit with
no check runs counts as passing, and the grade says `no checks ran`. While a
check is still running, or GitHub can't say, the trailer reads `Grade pending:
checks still running.` and the status row's `grade` is `pending`; the next poll
reads the checks again, with no agent, and once they've finished edits the
grade into your own comment's trailer and nothing else, logging `REVIEW #31
4f2a9c1 graded 10/10`. A comment someone else posted, or a send-back with
another header, is never edited, and a newer send-back under your login doesn't
hide the comment that's waiting. If that comment is gone, the row stops waiting
and no later poll asks again. A rubric that's missing, isn't valid JSON, or
lacks a key, has another key or a value outside 0 to 10 grades every review 0,
with the file named in the trailer. Edit the file to change the grades. A
project under [`projects/`](projects/) gets its own with `review_rubric` in the
factory's `projects` entry, a path from the factory's root. The project's own
`loop.json` can't set it, since anyone who can push to the project could
otherwise give every pull request a 10. The grade is read from the trailer
alone, never from the report above it. It's recorded as `grade` in the review's
status row, and isn't in `--pr`'s JSON line.

**What it never does:** approve, request changes, merge, push, or ask the agent
to post. The comment goes up under your own GitHub identity. A pull request's
diff, commit messages and files are written by whoever opened it, so the prompt
calls them material to review, never instructions. The agent is told not to
edit, and whatever it edits is thrown away with the checkout. The
`reader_agent` runs with `--restricted --strict-mcp-config --tools Read,Grep,Glob`,
whatever tools or permissions `loop.json` gave it: it can read the checkout and
nothing outside it, so a pull request written to steer it can't get your keys
or tokens into the comment, and the checkout's own [`.claude/`](.claude/) settings and
hooks never load. That's why review mode needs `reader_agent` to be `claude`
itself (a path is fine, `npx` or `env` in front isn't), or `ollama:<model>`,
which runs as it is because it has no tools to reach anything with. Nothing
here knows how to confine another tool, so with any other command it reviews
nothing and logs why. That includes `codex`: its read-only sandbox can still
read files outside the checkout, and what it read could end up in the posted
comment. When `review_agent` is set, it's the one that reviews, so the same
holds for it. The issue loop still takes Codex or Kiro, because the issues it
builds from are checked first.

The comment opens with a line saying an agent wrote it from the pull request's
own text, and an `@` in the report can't mention anyone, so text planted in a
pull request can't page your team through your account. It still posts as you:
to post as a bot, sign `gh` in as one on the machine that runs the review.
`loop.py stop` ends it at its next step, as it does `run`.

**Not in it, on purpose:** many projects in one run, voice dispatch, merge passes,
a dashboard, model-tier routing. Each can be added by whoever needs it, reading
the log.

### Off your laptop

The loop is one script, so it runs wherever `python3`, `git`, `gh` and your
agent's CLI do. There are three places, and the script is the same in each:

| Where | Needs | Costs |
|---|---|---|
| Your own machine, in tmux | Your laptop awake and online, `gh` signed in, your agent signed in | Nothing extra. It stops when the lid closes |
| An always-on machine (a VM) beside the repo | A clone, `python3`, `git`, `gh` and the agent CLI signed in as you, and `loop.py run` in tmux | A machine that's billed whether or not there's work, and someone to patch it |
| GitHub Actions | The workflow in [`examples/ci/loop.yml`](examples/ci/loop.yml), an API key as a repository secret, and the agent CLI installed on the runner each run | Runner minutes for as long as a pass iterates, and the agent's usage on the key |

Setting up the VM is yours: nothing here goes beyond naming it. Actions is the
one this repo ships an example for: it runs `python3 scripts/loop.py run --once`
on a schedule and on manual dispatch, and uploads `.loop/` as a build artifact so
the plan, the test output and the review outlive the runner.

**Where Actions is the weaker home:**

- A run that iterates for an hour spends an hour of runner minutes. Five rounds
  of a slow test command is a long job, and it's billed like one.
- `/loop-pane` and `tmux attach` don't reach a runner. You read the job log and
  the artifact, not the pane.
- A job that commits back puts building into a pipeline that is otherwise only
  checks. Everything else in [`.github/workflows/`](.github/workflows/) reads the repo; this one writes
  to it, which is why its `permissions:` block names contents, issues and pull
  requests, all write, and nothing else.

**Its pull request won't start your checks.** A pull request opened with the
workflow's own `GITHUB_TOKEN` doesn't trigger other workflows, so the repo's
required checks don't run on it, and it can't merge until something triggers
them. The choice that changes that is a token that isn't the workflow's: a
fine-grained personal access token (or a GitHub App's token) with contents,
issues and pull requests write, held as a secret and used in place of
`GITHUB_TOKEN` for `GH_TOKEN` and the checkout. The example sets that token
only on the step that runs the loop and on checkout, after the agent is
installed, so the install never reads it.

**It can't tell who you are.** With a workflow token, `gh api user` returns no
login, so the loop skips every issue that's assigned to anyone and takes only
unassigned ones. The same personal token gives it your login, and your assigned
issues come back. Reading a login from the config instead is a change to
[`scripts/loop.py`](scripts/loop.py), left for when this limit bites.

**Credentials change.** On your machine the loop uses your own agent sign-in. In
Actions the agent needs an API key (or a cloud provider's credentials), held as a
repository secret and referenced by name, as `${{ secrets.ANTHROPIC_API_KEY }}`.
It's never written into a file, the workflow, `loop.json` or an issue.

**To use it,** copy [`examples/ci/loop.yml`](examples/ci/loop.yml) into [`.github/workflows/`](.github/workflows/), add the
secret it names, and read its opening comment: it lists the repository setting
that has to be on for a workflow to open a pull request at all.

## Handing work to another factory

A factory is any system that takes work in and puts checked work out. This
repo is one. So is another team's delivery system, or a second copy of this
repo on the same machine. [`scripts/factories.py`](scripts/factories.py) hands an issue to one, and GitHub is
the only thing between them: a label goes on the issue, a pull request comes
back.

```mermaid
sequenceDiagram
    participant You
    participant Factory as This factory
    participant GitHub
    participant Factory
    You->>Factory: dispatch #12, then yes
    Factory->>GitHub: add the factory's submit label to #12
    Factory->>GitHub: open a pull request that closes #12
    Factory->>GitHub: status: read #12 and its pull request
    Factory->>GitHub: review: loop.py review --pr N posts one comment
    alt changes needed
        You->>Factory: resend, then yes
        Factory->>GitHub: put the submit label back on #12
    else ready
        Factory->>GitHub: read the required checks
        Factory-->>You: ready for a person, or why not
    end
    You->>GitHub: merge
```

`factories.json` at the harness root names the factory as one step: its name,
whether it runs on this machine (`local`, with a checkout in [`factories/`](factories/)) or
somewhere else (`remote`), the label that submits an issue to it, the label it
uses to give up, a time limit (24 hours by default) and a number of rounds
(3 by default). `time_limit_hours` is above 0 and at most 8,760, a year, and
`max_rounds` a whole number from 1 to 100; no value turns either off, `steps`
refuses one outside them, and a record holding one reads as a record `status`
can't read. The limit applies while a run waits on the factory, a review or
its checks, counted from the submission, the last round sent back or the pull
request's newest commit, whichever came last, so it also counts your own wait
to review a head. A ready verdict waits on you with no limit whatever its
checks read, `ready for a person`, failing, unknown, `changes CI`,
`no required check` or not independent, except checks still pending, which
keep it, a workflow held for approval included. What the limits allow and
count is written here and nowhere else; `LIMITS` in
[`scripts/factories.py`](scripts/factories.py) checks the ranges, and a test holds the two to each
other. A GitHub read that fails changes nothing, except a
failed read of the required checks after a ready verdict, which reads
`checks unknown`, and a run that read ready reads `returned` from the moment
status starts on it until a status gets all the way through. A run
ends when its
pull request is merged, or closed with nothing in its place. Only the
factory's own pull request counts as what it returned: one in the issue's
repo, into the default branch, by the step's `factory_login` when it names
one, and from a branch in the repo or a fork that `factory_login` owns. [`factories.example.json`](factories.example.json) has every key, and [`factories/README.md`](factories/README.md) says what a
factory has to do, and how a copy of this factory is set up as one. With no `factories.json`,
nothing here runs. A chain of factories waits until one is proved.

| Command | What it does | Writes to GitHub |
|---|---|---|
| `factories.py steps` | Reads `factories.json` and the factory's commit | Nothing |
| `factories.py dispatch 12 --repo o/r` | Shows the factory, the repo, the issue and the label; warns when the branch requires no status check; says what goes to the factory the first time; then submits on `--yes` or a typed yes | The submit label on #12 |
| `factories.py status` | Reads each run's issue and pull request, then the verdict and the required checks of a reviewed head, and names `review RUN` for a head not yet reviewed | Nothing |
| `factories.py review RUN` | Has `loop.py review --pr N` review the run's pull request, spending model tokens, then moves the run on as `status` does. It runs while the loop runs and outside its hours, on a lock for that pull request alone, and only from the clone `factories.py` is in | The review's one comment, on your login |
| `factories.py resend RUN` | Sends a run back for one more round, once per reviewed commit, on `--yes` or a typed yes: after changes needed, or after a ready verdict whose checks fail or that changes CI, or with `--because "why"` when a person disagrees. After a ready verdict it first posts why, ending `VERDICT: changes needed`, for the factory to read | The submit label on #12 again, and that comment |
| `factories.py cancel RUN` | Shows what cancelling does and changes nothing; on `--yes` or a typed yes, takes the submit label off the issue and ends the run as `cancelled`. It doesn't withdraw what the factory already took: a pull request it opens afterwards is closed, and the factory told, by hand | The label off #12, on the yes |
| `factories.py doctor --repo o/r --pr 31` | Builds the record dispatch would make, takes the head as reviewed, reading it as ready where you haven't reviewed it, and never gives a merge, and moves it on through the run's own code with `gh` held to an allowlist of reads, so it stops where a run would: the stopped label, a pull request that isn't the factory's, a draft, another base or changes needed read no checks, and it exits 1. Lists every call with what it came to, a reply it couldn't use or a row it skipped noted on the call that gave it, then what `status` would say, short of the merge, with every control character GitHub sent printed as `?` | Nothing |
| `factories.py list` | Every run from its record alone | Nothing |

Each run writes one record to `.sanvio/factories/`, gitignored: the issue,
the factory, its commit and whether it was read from a checkout or only
declared, the state, the pull request, the rounds, and when it started and
ended. A factory's tokens and cost read `not reported`, since its usage isn't
visible from here. A run belongs to the clone that dispatched it and the
person who runs its review, and works with repos on github.com only:
[`factories/README.md`](factories/README.md) has both, and *Getting to ready*, every setting a ready
run needs.

**What it holds to.** The only write to the issue is the submit label, each
time on a yes. Nothing in `factories/<name>/` is run, imported or read except
the checkout's commit and its local git config. The guard keeps a headless run out of
[`factories/`](factories/) altogether. The reviewer is the loop's: it reads the diff detached,
outside your clone, with read tools only, and the pull request's text is data
in its prompt. The verdict is read from the trailer of your own review comment
for the head commit, through the same reader the loop's round uses, and
anything but "changes needed", "ready" or "ready with nits" goes to a person
rather than another round. A factory's own verdict, such as
"VERDICT: merge", is never read. The verdict that decides between another
round and a person is the reviewer's last line, which the diff it read can
steer: that's why the checks have to hold on their own. If the comment's
verdict changed after the loop posted it, the run needs a person.

Ready means the required checks passed on the commit the review read, read
from the base repo, and none of the ways this factory knows for another to
produce its own checks was found: a claim about what it can read, not proof,
so read the diff. *Getting to ready* in [`factories/README.md`](factories/README.md) is the one place
that says what it requires and what it can't show. Short of it, a run reads
`checks failing`, `checks pending`, `checks unknown`, `changes CI`,
`no required check` or `checks pass, not independent`, and says why. Nothing
here merges, approves or closes. A ready run's line ends with one command for
a person to copy. It checks the base just before merging, since a pull
request's author can change it, and says why when it doesn't merge; it names
the whole commit the review read, so a push after the review fails the merge.
A retarget between that check and the merge isn't caught, since GitHub's merge
pins the head and not the base, so protect every branch a pull request could
target. A step's `merge_method` in `factories.json`, `merge`, `squash` or
`rebase`, goes into the command; without one gh asks which, and fails with no
terminal. `--match-head-commit` needs gh 2.13.0 or later. `list` gives no merge: it says to
run `status` on the run right before merging. [`skills/dispatch/`](skills/dispatch/) is the conversation around it.

## Context: who remembers what

- **Each agent has its own context.** A review agent, or any subagent, starts
  with only what it's given and hands back a report. The main session gets the
  report, not everything the reviewer read. That's why read-heavy work goes to
  a subagent: it can read 300 pages and return one.
- **The tool summarises, not the harness.** When a long session fills its
  context, Claude Code compacts it automatically. The harness doesn't write
  summarisation code.
- **What must survive goes in a file.** A session ends and its context is
  gone. Rules, decisions and lessons live in [`AGENTS.md`](AGENTS.md), a skill or a gate,
  where the next session reads them. A correction you only said out loud
  hasn't happened.

## How much of it is code

Less than the rest. The agents are the tool's own agents, defined in
Markdown, and the skills are Markdown. The code is standard-library Python or
shell, all with tests: the gate, the git hook, the setup check, the Claude
Code hooks, and the scripts in [`scripts/`](scripts/), of which the loop and `factories.py`
are the largest.

You'd write SDK code when a loop has to run without a person: in CI, on a
schedule, or across many tickets at once. Even then, the harness files stay
the same. The runner reads [`AGENTS.md`](AGENTS.md), the skills and the gates exactly as you
do.

## One factory, many teams

One harness carries the rules every team shares. Each project under
[`projects/`](projects/) adds its own `AGENTS.md` for what's specific to it, and can only
add rules, never loosen them. A risky project (one that writes to a
production system) tightens its own rules and gates. A read-only one needs
fewer. Same harness, same skills, different strictness per project.

One person owns the factory and merges changes to it. Everyone else pulls.
That's what keeps ten developers' agents behaving like one team instead of ten
people's personal setups.

### Strictness follows risk

The same harness runs a read-only report and a service that writes to
production. What changes is how much each project's own `AGENTS.md`, gates
and branch protection ask for:

| | Reads only | Writes to something people use |
|---|---|---|
| Connectors | Read tools are fine | Every write asks first. The guard asks for any connector call not named as a plain read |
| Gates | The harness's own | Plus the project's, in its hook and its CI, required before merge |
| Agents working alone | Fine on a ready ticket | Never against production. Staging only, with that permission written in [`AGENTS.md`](AGENTS.md) |
| Merging | Anyone the owner trusts | The project's owner, after `review-pr` |
| Deploying | Nothing to deploy | A human yes for each production deploy. [`steering/deploying.md`](steering/deploying.md) has the rest |

Start a new project on the right-hand column and loosen it once you've seen
what it does. Going the other way, you learn the risk from an incident.

### How the harness changes

Someone's agent gets something wrong. They say "learn from that", and
[`skills/learn/`](skills/learn/) drafts the rule in the file that governs it. That goes to the
owner as a pull request with a [`CHANGELOG.md`](CHANGELOG.md) entry. Once it's merged,
everyone's `/whats-new` shows it and says what to do to take it.

The sprint report catches what nobody said out loud: a skill nobody uses, an
ask that always gets a yes, a step everyone does by hand. Each person's log
stays on their own machine, holding names and counts, never prompts or code.
Only the report they've read reaches the owner, and they send it themselves:
it's gitignored in [`reports/usage/`](reports/usage/), never committed.

Nobody edits a shared rule in their own copy. A local edit is a quiet fork,
and the next update collides with it. A rule only one project needs goes in
that project's `AGENTS.md`.

### Where a change lives

A change reaches the people who load the file it's written in, and nobody else:

| Where it's written | Who gets it | What belongs there |
|---|---|---|
| This repo: [`skills/`](skills/), [`steering/`](steering/), [`AGENTS.md`](AGENTS.md), [`.claude/settings.json`](.claude/settings.json) | Everyone, once it's merged and they pull | Anything the team relies on |
| A project's `AGENTS.md`, in that project's own repo under [`projects/`](projects/) | Anyone working in that project, once it's merged there | What only that project needs |
| `.claude/settings.local.json` in your clone | You, in this clone. Git ignores it | Your own permissions and preferences here |
| Your own `~/.claude/CLAUDE.md`, `~/.claude/settings.json` and `~/.claude/skills/` | You, in every repo on your machine | Personal habits nobody else depends on |

The quick test: if `git status` in the repo it belongs to doesn't show the
change, your team won't get it. Something that lives only in `~/.claude/` works for you and for
nobody you work with, and nothing tells you so. If the team needs it, it goes
in one of the first two rows, through a pull request with a
[`CHANGELOG.md`](CHANGELOG.md) entry.

**Don't keep a copy in both.** A skill in `~/.claude/skills/` with the same name
as one in [`skills/`](skills/) wins in Claude Code, so your agent runs your copy and
everyone else runs the harness's: one name, two different skills.
`python3 scripts/check_setup.py` warns when that happens. Settings go the other
way: where this repo's [`.claude/settings.json`](.claude/settings.json) or your `settings.local.json` sets
something, it wins over your `~/.claude/settings.json`. Your `~/.claude/CLAUDE.md`
and this repo's [`CLAUDE.md`](CLAUDE.md) both load, so a rule in yours applies to you alone.

### Who owns what

- **The factory's owner**: steering, skills, gates, hooks and the release log.
  Merges every change to them.
- **Each project's lead**: that project's `AGENTS.md`, its gates and its CI.
- **Whoever runs production**: the release step, meaning
  [`steering/deploying.md`](steering/deploying.md) and the deploy workflow.

To make that hold rather than just be written down, add a
`.github/CODEOWNERS` naming the owner for [`steering/`](steering/), [`skills/`](skills/), [`gates/`](gates/),
[`.githooks/`](.githooks/) and [`.github/`](.github/), and turn on "require review from code owners" in
branch protection. A code owner can't approve their own pull request, so this
needs at least two people.
