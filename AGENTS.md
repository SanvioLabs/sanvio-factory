# How to work in this repo

This is a harness: the rules, skills, gates and agents you work inside. You do
the work. A human reviews it, and a human sends, merges or pays.

## Steering

Standing guidance, one file per topic, in [`steering/`](steering/). These three apply to
every session. Claude Code loads them through the lines below and Kiro through
[`.kiro/steering/`](.kiro/steering/). In any other tool, read them before you start:

@steering/operating.md
@steering/response-style.md
@steering/data-and-tools.md

Read these when their moment comes:

| File | Read when |
|---|---|
| [`steering/writing.md`](steering/writing.md) | Writing anything a person outside the company will read, or a README or doc that explains how something is set up |
| [`steering/project-setup.md`](steering/project-setup.md) | Starting a new repo or project |
| [`steering/building-and-testing.md`](steering/building-and-testing.md) | Writing or changing code, or writing tests for it |
| [`steering/deploying.md`](steering/deploying.md) | Setting up infrastructure, deploying, or changing anything people use |
| [`steering/model-selection.md`](steering/model-selection.md) | Deciding which model runs what, or handing work to a subagent |
| [`steering/gates.md`](steering/gates.md) | Adding, moving or strengthening a check, or deciding whether a rule needs one |
| [`steering/tickets.md`](steering/tickets.md) | Writing an issue, putting one on the loop, commenting on one, or closing one |

Add your own the same way: one topic per file, and a row here saying when it
applies. Where a steering file and this file disagree, this file wins, and you
say so.

## Who you work for

Before any company work, read `company/COMPANY.md` and `company/DATA.md` if
they exist. The first says who the company is and what it won't do. The second
says where its data lives and how you reach it. Never invent a fact about the
company: if a section is empty or a file is missing, ask, or suggest
`/orientation`. Both files are gitignored, so never quote them into a tracked
file.

## Where you start

Sessions start at the harness root, the folder this file is in. Code repos are
cloned into [`projects/`](projects/) and worked on from here. If your working directory is
below the root, say so before any work: the harness's skills, agents and
guards didn't load, so the rules below are unenforced. Ask the person to
restart from the root. [`projects/README.md`](projects/README.md) has why.

A project's own `AGENTS.md` or `CLAUDE.md` adds to these rules for that
project. Where the two disagree, these rules win and you say so.

## Rules

- Every input comes from a named source: a file, a connector in
  `company/DATA.md`, or the person in this session. Never invent one. If you
  don't know something, ask. Don't guess, and don't fill it with something
  plausible.
- Leave no `{{placeholder}}`, `TODO` or `TBD` in finished work.
- Never send, email or publish anything. A connector that can send, edit,
  delete or share does so only when a human says yes to that one call.
- Never read, write or print a credential, a key or a `.env` file.
  [`steering/data-and-tools.md`](steering/data-and-tools.md) has the detail.

## Skills

Skills are procedures. When a request matches one, read it and follow its
steps in order.

| Skill | Use when |
|---|---|
| [`skills/review-pr/SKILL.md`](skills/review-pr/SKILL.md) | Asked to review a pull request, a branch or a diff, or whether a change is ready to merge |
| [`skills/review-tests/SKILL.md`](skills/review-tests/SKILL.md) | Asked whether tests are any good or would catch a regression, or after tests were written by an agent |
| [`skills/review-skill/SKILL.md`](skills/review-skill/SKILL.md) | Asked to install, add, try or review a skill from outside this repo |
| [`skills/learn/SKILL.md`](skills/learn/SKILL.md) | The agent got something wrong and the person wants it to stick: "learn from that", "don't do that again", "make that a rule" |
| [`skills/retro/SKILL.md`](skills/retro/SKILL.md) | Asked for a retro, why something went wrong in a session, or which sessions the retro hook kept. The hook keeps nothing unless `HARNESS_RETRO=on` |
| [`skills/loop-control/SKILL.md`](skills/loop-control/SKILL.md) | Putting an issue on the loop, starting or stopping [`scripts/loop.py`](scripts/loop.py), or asked what the loop did or why an issue is blocked |
| [`skills/orientation/SKILL.md`](skills/orientation/SKILL.md) | Someone runs `/orientation`, is new here, asks how to use this, says "get me started", or wants it set up for their own job and their company's data |
| [`skills/harness-trends/SKILL.md`](skills/harness-trends/SKILL.md) | At the end of a sprint, or asked for a harness report, a sprint follow-up, or what to add to the harness, or how many tokens the harness or the loop used |
| [`skills/work-report/SKILL.md`](skills/work-report/SKILL.md) | Asked for a work report, what got done or shipped over a period, which milestones were met, or a report on the team's work for a lead |
| [`skills/whats-new/SKILL.md`](skills/whats-new/SKILL.md) | Asked what's new, what changed, or whether this copy is up to date with its remote |
| [`skills/starter-updates/SKILL.md`](skills/starter-updates/SKILL.md) | Asked to "check the starter", "starter updates", "what's new in the starter", "what has the starter added", or "should we take the starter's changes". It asks what you want to bring over, one question at a time |
| [`skills/standup/SKILL.md`](skills/standup/SKILL.md) | Asked for a standup or a morning check, or what's on them today: reviews waiting, issues assigned, what the loop finished or blocked, today's meetings |
| [`skills/inbox/SKILL.md`](skills/inbox/SKILL.md) | Asked to check their email or inbox: what needs a reply, what's waiting on someone, what matters today |
| [`skills/pulse/SKILL.md`](skills/pulse/SKILL.md) | Someone runs `/pulse`, says "pulse", or asks to see or answer the team's daily question, or how the team answered yesterday, or to summarise a period's answers for leadership |

These come from the Stelliad plugin, which [`.claude/settings.json`](.claude/settings.json) switches on.
Installing it is the one install that doesn't go through `review-skill`; the
README says why. In Claude Code, invoke them by name, and if one isn't
installed, say so and point at `/plugin install stelliad@sanvio-harness-starter`. In a tool
without plugins, write tickets from [`steering/tickets.md`](steering/tickets.md) and
[`.github/ISSUE_TEMPLATE/loop-task.md`](.github/ISSUE_TEMPLATE/loop-task.md), and say there's no spec procedure here
without Stelliad.

| Skill | Use when |
|---|---|
| `stelliad:create-spec`, then `stelliad:plan-spec`, `stelliad:implement-spec`, `stelliad:review-spec` | Asked to spec a feature, plan a spec, build it a task at a time, or review a finished one |
| `stelliad:create-ticket`, `stelliad:review-ticket` | Asked to write, split or grade an issue. One meant for the loop also needs what [`steering/tickets.md`](steering/tickets.md) asks, then `loop-control` puts it on |

## Done means the gate passes

Work that has a gate is done when its gate passes. Each job's skill names its
gate and the command that runs it. Run it and show the output. Never say work
is done, ready or finished while its gate fails, and never edit a gate to make
work pass.

The gates also run in [`.githooks/pre-commit`](.githooks/pre-commit), along with a check for secrets.
If a commit is blocked, fix what it names. Never commit with `--no-verify`.

In Claude Code, [`.claude/hooks/guard.py`](.claude/hooks/guard.py) also runs before every tool call: it
refuses credential files and asks the human before any connector changes
something. If it refuses, don't look for another way to do the same thing. Say
what you needed and ask.

## Changing the harness

A noticeable change (something new, something that works differently,
something that moved, or anything someone has to act on) adds an entry at the
top of [`CHANGELOG.md`](CHANGELOG.md) in the same change. Its header has what counts and the
shape of an entry. That's how the next person finds out with "what's new".

## Agents

After the gate passes, hand the work to a reviewer before a human sees it.

| Agent | Does | Use when |
|---|---|---|
| [`agents/reviewer.md`](agents/reviewer.md) | Reads finished work as the person who receives it would and reports what's unclear or over-promised, using the job's brief if it has one. Never edits | Any finished work, before it's sent or merged |
| [`agents/security-reviewer.md`](agents/security-reviewer.md) | Reads code the way an attacker would and reports what could be exploited, each finding with its attack path, and a READY or NOT-READY verdict. Read-only; its shell runs dependency audits and a redacted secret scan, nothing else | Asked for a security review, or a change touches auth, input handling, secrets, infrastructure or dependencies |
| [`agents/ceo.md`](agents/ceo.md) | Reads finished work from the chief executive's seat and reports what it commits the company to that nobody decided, what it costs, and anything the company says it won't do. Never edits | Work that commits money, time or people, or changes what the company is for |
| [`agents/cto.md`](agents/cto.md) | Reads finished work from the chief technology officer's seat and reports what won't hold, what can't be run or undone, and technical claims it doesn't show. Sends vulnerabilities to `security-reviewer`. Never edits | Work that adds a design, a dependency or a technical claim |
| [`agents/cmo.md`](agents/cmo.md) | Reads finished work from the chief marketing officer's seat and reports claims a customer could check and find wrong, and anything at odds with how the company presents itself. Never edits | Work a customer or the public will read |
| [`agents/gc.md`](agents/gc.md) | Reads finished work from the general counsel's seat for licences, promises, other parties' names or content, and personal data, and ends with the findings that need a lawyer. Not a lawyer, not legal advice. Never edits | Work that makes a promise, uses someone else's code or content, or handles personal data |

In Claude Code they run as the `reviewer`, `security-reviewer`, `ceo`, `cto`,
`cmo` and `gc` subagents.
In other tools, run each as a separate session with its file as its
instructions.

[`scripts/eval_agents.py`](scripts/eval_agents.py) runs a review agent on known examples and says which defects it still
catches. Run it after changing an agent's file, a job's brief or the model. It starts real
sessions, so it isn't part of the gate; [`examples/proposal/evals/`](examples/proposal/evals/) has the reviewer's cases, and [`examples/typescript/evals/`](examples/typescript/evals/) the security reviewer's.

[`scripts/eval_harness.py`](scripts/eval_harness.py) runs a whole harness through a suite of jobs and prints a scorecard, and `compare` shows what a harness change did. It creates a private repo and spends model tokens, so only start a run when a person asks. [`examples/eval-suite/`](examples/eval-suite/) shows a suite's format. A private suite's `key/` never goes in this repo, or anywhere an agent working on the run can read.

## Examples

[`examples/`](examples/) holds worked jobs to read and copy. Before working in one, read its
`README.md`: it carries that job's rules, and they apply on top of these.

| Example | Shows |
|---|---|
| [`examples/proposal/`](examples/proposal/) | Drafting a client proposal: inputs, rules, a skill (`skills/draft-proposal/SKILL.md` inside it), a gate, the hook block and a review brief. Also when asked whether a proposal is ready to send or can enter Shape or Build: its README's *Ready to send, and ready for Build* |
| [`examples/typescript/`](examples/typescript/) | A TypeScript project tested with Node alone: `node --test` runs the `.ts` tests with no build step, `tsc` checks the types, and its README gives the loop's `test_command`. Read it when starting a TypeScript project or putting one on the loop |
| [`examples/mods/harness-lens/`](examples/mods/harness-lens/) | A Claude Code mod that shows which layer just acted, above the prompt. On by default from [`.claude/settings.json`](.claude/settings.json); `/lens` lists the session |
| [`examples/mods/loop-pane/`](examples/mods/loop-pane/) | A Claude Code mod: `/loop-pane` opens a pane showing [`scripts/loop.py`](scripts/loop.py)'s queue, each issue's step and round, its tokens and estimated cost, and its pull request, and on a Mac opens a read-only window on the loop's tmux session. On by default; it never changes the loop |
| [`examples/mods/github-status/`](examples/mods/github-status/) | A Claude Code mod that shows the repo's running actions, open pull requests and open issues above the prompt, read through `gh`. On by default; it only reads, and `/github` reads now |
| [`examples/mods/harness-dashboard/`](examples/mods/harness-dashboard/) | A Claude Code mod: `/harness-dashboard` opens a pane with what's waiting on you, the loop's spend, throughput and rework, the saved evals and whether they're stale, Claude Code's tokens and the harness's activity, from [`scripts/dashboard_data.py`](scripts/dashboard_data.py), with a bar chart a day for the loop's spend and Claude Code's tokens, over 7, 14 or 30 days. Off by default; it spends no model tokens, calls `gh` on each read and writes only the script's caches |
| [`examples/mods/loop-crew/`](examples/mods/loop-crew/) | A Claude Code mod: `/loop-crew` opens a pane with a lane for each issue being worked on, the loop's steps left to right, and a figure running to its step and working there, and `/loop-crew <project>` shows a project's loop. On by default; it only reads the loop's files and spends no model tokens |
