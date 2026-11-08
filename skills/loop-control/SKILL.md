---
name: loop-control
description: Drive the loop in scripts/loop.py from a conversation. Put an issue on it after checking it's ready, start it, say what it did, or stop it in the right order, or start the pull-request reviewer. Use when someone says "put #12 on the loop", "is this ready for the loop", "start the loop", "run the loop on #12", "what did the loop do", "why is #12 blocked", "stop the loop", or "review the pull requests waiting on me".
license: MIT. From the Sanvio Labs harness starter, https://github.com/SanvioLabs/sanvio-harness-starter
---

# Loop control

[`scripts/loop.py`](../../scripts/loop.py) takes an issue carrying the ready label, plans it, builds it,
runs the tests, has a fresh agent review it and opens a pull request. "The
ready label" here means the effective `ready_label`: `loop-ready` unless a
`loop.json` sets another. For the factory's own loop, read the factory's
`loop.json`. For a project, its own `loop.json` wins, then its entry under
`"projects"` in the factory's; the factory's top-level value doesn't apply.
In project mode (see *A project under projects/*) every `gh issue` command
takes `--repo <owner>/<repo>`.
[`HOW-IT-WORKS.md`](../../HOW-IT-WORKS.md) (*The loop*) says how. This skill is the conversation
around it: what goes on the loop, when it starts, what it did and how it
stops, and the pull-request reviewer beside it. Five jobs. Do the one asked for.

## Put an issue on the loop

A ticket is an instruction to an agent that runs without anyone watching, so
it gets read before it's labelled.

1. **Read it:** `gh issue view <N> --comments` (add `--repo <owner>/<repo>` for
   a project). Show the person the body verbatim, as it comes back, not a
   summary. Flag any `<!--` in the body: the issue's page hides it. Flag any
   comment that changes the acceptance criteria while the body stays the same:
   the loop reads only the body, so the body has to be edited first.
2. **Check it's ready** against [`steering/tickets.md`](../../steering/tickets.md). All of these, or it isn't:
   - **One change**, small enough for one pull request.
   - **Acceptance criteria** a check can prove, at least one of them by a
     test that fails now and passes after. "Make it better" isn't one.
   - **Risk Low or Medium,** and no Human Approval section. Open
     dependencies needn't stop you labelling it: the loop waits for them.
     `WAITING` lines in `.loop/loop.log`, and `waiting_on` on the issue's
     entry in the queue in `.loop/status.json`, show what it waits on.
   - **Where Stelliad is installed,** `stelliad:review-ticket <N>` says READY.
   - **No package to install,** unless the loop's `agent` is allowed to. By
     default it can't, so a new dependency goes on `base` first, or on a
     `Depends on #N` issue; [`HOW-IT-WORKS.md`](../../HOW-IT-WORKS.md) (*The build agent doesn't
     install packages*) has how, including for a ticket that already blocked.
     A round that changes a lockfile blocks the issue before the tests run,
     naming the paths (it reads every commit the loop made on the branch, so
     drop the agent's commit before putting the issue back), unless `loop.json` sets `"allow_lockfile_changes":
     true`, which a team that lets the agent install sets too. Its `uv` and
     `cargo` test commands should pass `--locked`.
   - **Nothing outside the repo:** no deploying, sending, publishing,
     credentials, or anything the guard would refuse.
   - **Not assigned to someone else.** The loop skips those anyway.
   - **Exactly one type label:** `bug`, `enhancement`, `documentation` or
     `chore`. With none, suggest the one that fits what it asks, and add it
     with the ready label in step 5. If the repo has no `chore` label yet,
     `gh label create chore --description "Maintenance: dependencies, tooling,
     tidying"` (with `--repo` for a project) makes it, asked first like the
     label itself.
3. **If something's missing,** draft the missing part (usually the
   acceptance criteria) in the shape of [`.github/ISSUE_TEMPLATE/loop-task.md`](../../.github/ISSUE_TEMPLATE/loop-task.md), and show it. The person adds it to the issue, or tells you to.
4. **Check where the pull request would go:** `gh repo view --json visibility
   -q .visibility`. If it's `PUBLIC`, say the pull request will be public and
   ask whether that's meant. A copy of the public starter is public until
   someone makes it otherwise.
5. **Ask, then label:** "Label #N with the ready label?" On a yes,
   `gh issue edit <N> --add-label <ready label>` (with `--repo` for a project),
   and its type label in the same `--add-label`, comma-separated, if it had none.
   Label only after step 1's verbatim body and comments have been shown in this
   conversation, or when the person wrote the issue. A yes to your summary
   doesn't count.

## Start it

1. Run `python3 scripts/check_setup.py`. Fix or name any FAIL before going on.
2. Run `python3 scripts/loop.py run --dry-run` and say which issue it would
   take. Nothing ready means say so and stop.
3. Ask: one issue (`--once`, or `--issue <N>` for a particular one) or every
   ready issue (`run` alone, which keeps polling once the queue is empty: it
   idles and picks up anything labelled later, until it's stopped; `--once` and
   `--issue` exit when they're done). To put an end on `run`, for every ready
   issue over a set time, such as overnight, add `--for 8h` (a whole
   number then `m`, `h` or `d`). After that time it takes no new issue, lets
   each running one finish, logs `END --for 8h reached` and exits. To keep it
   to working hours, add `--hours "Mon-Fri 09:00-17:00"` (local time, days `Mon`
   to `Sun`, capitalised as shown, as a day, a range or a comma list, then `HH:MM-HH:MM`), or set
   `"hours"` in `loop.json`; `--hours` replaces the `loop.json` value for that
   run. A window that crosses midnight belongs to the day it starts:
   `Fri 22:00-06:00` covers early Saturday. Outside the hours it starts nothing,
   lets a running issue finish, logs one `HOURS` line with the next start and
   waits. A value it can't read logs an `ERROR` and it exits having taken
   nothing.
4. Start it in tmux when `command -v tmux` finds it, so it outlives this
   conversation and the person can open it and watch. One session per clone,
   named after the folder (tmux won't take a dot or a colon in a name), with the
   flags from step 3 in place of `<flags>`:

   ```bash
   name="loop-$(basename "$PWD" | tr '.:' '--')"
   tmux new-session -d -s "$name" -c "$PWD" \
     "python3 scripts/loop.py run <flags>; echo; echo 'The loop has exited. Press Enter to close.'; read _"
   ```

   If `tmux new-session` says `duplicate session`, a loop is probably
   running there: say so and give the attach command rather than starting a
   second. The loop's lock refuses a second run in one clone anyway.
   Without tmux, start it in the background instead, and say that it stops
   when this session ends.
5. Check it started: `tail -3 .loop/loop.log` shows a `START` line naming
   the tmux session (none without tmux), an `UNTIL` line with `--for`'s end
   time, then `DISCOVER`, `IDLE` or `HOURS`. Then say
   how to watch it: `tmux attach -t <name>` (`Ctrl-b d` leaves it
   running), `/loop-pane` in Claude Code, or `tail -f .loop/loop.log`.

`max_workers` in `loop.json` (default 1) is how many issues `run` works at
once. Each worker runs its own agent sessions, so say that usage grows with the
number before the person raises it. Each issue's agents write to
`.loop/issue-<N>/agent.log` as they go, and in tmux each issue gets a window
named `issue-<N>` that follows it (`Ctrl-b w` lists them) and closes when the
issue ends. A stop doesn't interrupt the round already running (see *Stop it*).

`max_issue_tokens` in `loop.json` (default 0, no budget) caps the tokens one
run of an issue may use. Set it to a whole number above 0. Before each build
and each review the loop checks, and over the cap it blocks the issue with
`used N tokens this run, over max_issue_tokens M` in the log and the block
comment. A run already started finishes, so the overshoot is up to one run.
Taking `loop:blocked` off and putting the ready label back starts a fresh
budget. Say that only runs that report tokens count (`claude`), and that the
loop warns at start-up about each agent that doesn't. Any other value stops
`run` with an `ERROR` before it takes an issue.

## A project under projects/

To work a code repo cloned into [`projects/`](../../projects/) rather than this repo, add
`--project projects/<name>` to `run`, `review` and `stop`, and run them from
the harness root as above. Name the tmux session after the project,
`loop-<name>`, so it sits beside the factory's own.

1. The project needs its own `loop.json` with a `test_command`, since the
   default tests this repo, not the project. For TypeScript that's
   `{"test_command": "npm test"}`, or `node --test` with no `package.json`
   script. Its `base` (default `main`) is where branches start and pull
   requests go. If it has no `loop.json`, say so and ask the person for the
   command. Don't write one up. Its `loop.json` may set only `test_command`,
   `test_timeout`, `base`, `ready_label`, `blocked_label`, `generate_command`
   and `setup_command`. Every other key
   (`agent`, `max_workers`, `allow_lockfile_changes`, ...) is the machine's: it
   goes in the factory's `loop.json`, for one project under `"projects"`, such
   as `"projects": {"app": {"agent": "claude", "max_workers": 2}}`.
2. The loop refuses, with one `ERROR` line and before it takes anything, a
   folder that isn't directly under [`projects/`](../../projects/), one that isn't a git clone of
   its own, a clone whose `origin` isn't on github.com, a `loop.json` with
   no `test_command`, or one that sets a machine key.
3. Issues, labels and pull requests are the project's GitHub repo's. Label
   with `gh issue edit <N> --repo <owner>/<repo> --add-label <ready label>`; with
   no `--repo`, `gh` from the harness root reaches this repo.
4. Its state is in this repo, in `.loop/projects/<name>/`: `status.json`,
   `loop.log` and `issue-<N>/`, with a lock of its own, so it runs beside the
   factory's loop. Read those in place of `.loop/` under *Say what it did*.
   Its checkouts are in `~/.sanvio-loop/<factory>/<name>/`.
5. The agents get the harness's [`AGENTS.md`](../../AGENTS.md) and its three steering files at
   the top of each prompt. A `claude` build agent also runs the harness's
   `guard.py` before each tool call. Another build agent, such as `codex`, has
   no hook to put it in, so say it builds without the guard.

## Say what it did

1. Read `.loop/status.json` for where each issue ended, then that issue's
   folder: `.loop/issue-<N>/plan.md`, `review.md`, and the end of
   `test-output.txt`.
2. Report, in this order:
   - how it ended: a pull request (with its link), blocked, stopped or skipped
   - how many rounds it took
   - what the review found, most important first
   - what the review couldn't check: the default reviewer reads, it doesn't
     run commands, so name anything it took on trust
   - what it used: `tokens` and `cost_usd` on the issue's row in `status.json`,
     per run in `.loop/issue-<N>/usage.json`, and a `USAGE` line each in
     `loop.log`. Say the dollar figure is Claude Code's estimate at API
     prices, and that `null` means the run didn't report it (codex, ollama, a
     timeout), not that it was free
3. **Blocked:** say why, from `review.md` and the last test output, and point
   at the entry in `.loop/lessons.md`. If the cause is the ticket (no check,
   too big), say what to change in it. The `learn` skill turns a repeated
   lesson into a rule.
4. **A pull request:** suggest reading its diff before merging. The loop never
   merges, and neither does this skill.

## Review pull requests

`python3 scripts/loop.py review` is the other half of the queue: it reviews
each open pull request that asks for the person (`review_query`, by default
`review-requested:@me`), once per head commit, with
[`skills/review-pr/`](../review-pr/SKILL.md), and posts the report as one comment per pull request,
edited in place on later commits. Start it only when asked.

1. Run `python3 scripts/check_setup.py`, then say what it will do: which pull
   requests match, and that the comments go up under the person's own GitHub
   identity. Ask before starting.
2. `python3 scripts/loop.py review --once` reviews what is waiting and exits;
   without `--once` it keeps watching. Start it in tmux as under *Start it*,
   with that command in place of `run <flags>`.
3. It takes the same lock as `run`, so one process works a clone at a time. If
   the loop is running here, say so: the review needs its own clone, or waits.
4. Say what it did from `.loop/loop.log`: one `REVIEW #N <sha> posted`,
   `skipped` or `failed: <why>` line per pull request and commit. A review
   whose agent exited non-zero or timed out, or whose diff couldn't be made,
   posted nothing and isn't retried until the pull request has a new commit. A
   fetch, checkout or post error ends in `(will retry)` and is tried again on
   the next poll. `loop.py stop` ends it at its next step.

It never approves, requests changes, merges or pushes, and the agent is never
asked to post: the script does. A person decides what happens to the pull
request.

## Stop it

The order matters. Stopping alone lets the loop take the issue straight back.

1. Take the ready label off every issue whose row in `.loop/status.json`
   (`.loop/projects/<name>/status.json` for a project's loop) has
   `state: "working"`, and any other you don't want picked up again:
   `gh issue edit <N> --remove-label <ready label>`, with
   `--repo <owner>/<repo>` for a project's issue.
2. Then `python3 scripts/loop.py stop`, with `--project projects/<name>` for
   a project's loop. The loop ends at its next step, not mid-step.
3. Say plainly that the round already running may still push and open a pull
   request.
4. For an immediate halt, `tmux kill-session -t <name>`. Say it can leave a
   half-done branch or worktree behind.
5. Say what it was doing when it stopped, from the same `status.json`. In tmux,
   its session waits for Enter once the loop exits, so the last lines stay
   readable; once the loop has exited, `tmux kill-session -t <name>` closes
   that waiting session.

## Rules

- Never label an issue until its verbatim body and comments have been shown in
  this conversation, or the person wrote it. A yes to a summary isn't reading it.
- Never merge a pull request the loop opened, or approve one. `loop.py review`
  doesn't approve or merge either, and nothing here makes it.
- Never take `loop:blocked` off an issue without the person: it's the record
  that the loop gave up.
- Never edit anything under `.loop/`. The loop writes it; you read it.
- The test command lives in `loop.json`, and the person sets it. If the proof
  an issue needs isn't in it, say so rather than changing it.

## Output

For each job, one short report: what you checked or did, the issue number,
and the pull request link or the reason it stopped. Every label added or taken
off is named.
