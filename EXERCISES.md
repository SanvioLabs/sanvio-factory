# Exercises

Work in pairs, and pick one of two starting points. Then build the five layers
around it, in this repo or a copy of it.

- **A job you do every week**: a status update, a code review, an invoice, a
  support reply, a release note.
- **A project your company is starting**: a client engagement, a product
  launch, an internal tool. This track is for whoever decides how projects run,
  not only whoever writes the code.

Each step below works for both, and has a **Company project** line for the
second. On that track, run `/orientation` first: it writes `company/COMPANY.md`,
and the agent reads it before any company work.

On your own? Run `/orientation` in Claude Code, or say "get me started" to
any agent, and [`skills/orientation/`](skills/orientation/) walks you through the same five layers,
one at a time.

The whole workshop, with the deck and a walkthrough of each section, is in
[`docs/workshop/`](docs/workshop/).

## 1. Write the instructions file (10 min)

Rewrite [`AGENTS.md`](AGENTS.md) for your job. Three things only:

- Where the inputs come from, and that the agent never invents them
- Where the output goes, and what it's called
- What the agent never does on its own (send, pay, delete, merge)

Test it: ask your agent to do the job and watch what it gets wrong. Every
mistake is a line you're missing.

**Company project:** write how a project runs at your company. Who approves the
start, where the brief and the documents live, and what an agent never does on
a project without a person: sign, spend, or send anything to a client.

## 2. Turn the job into a skill (10 min)

Copy [`examples/proposal/skills/draft-proposal/`](examples/proposal/skills/draft-proposal/) to `skills/<your-job>/` and
rewrite it for your job. A skill has a name, a description that says when to
use it, numbered steps, and a defined output.
If you can't say what the output is, it isn't a skill yet.

**Company project:** write `skills/start-project/`. Its output is one brief at
`briefs/<project>.md` with five sections: the problem, the owner, the success
criteria, the first milestone, and where the work lives.

## 3. Write a gate that blocks (10 min)

Write a script that exits non-zero when the output isn't ready. Check the things
that are cheap to check and expensive to miss: an empty section, a placeholder,
a number that doesn't match its source. [`examples/proposal/gates/proposal_gate.py`](examples/proposal/gates/proposal_gate.py)
is the pattern, and [`gates/README.md`](gates/README.md) has the rules. Yours goes in [`gates/`](gates/).

Then try to break it. Ask the agent to mark the job done with the gate failing.

**Company project:** the gate fails a brief with no owner, no success criteria,
or a placeholder left in, and names what's missing. Then ask the agent to start
building with the gate failing. It's the same refusal you watched at 6:42, when
a session asked to skip a phase.

## 4. Wire it into the hook (5 min)

Add your gate to [`.githooks/pre-commit`](.githooks/pre-commit). Run `git config core.hooksPath .githooks`
if you haven't. Commit something that should fail and watch it refuse.

**Company project:** run your brief gate on any commit that touches `briefs/`.

## 5. Add one agent (if you have time)

The harness already has a reviewer, [`agents/reviewer.md`](agents/reviewer.md). Write it a brief
for your output in [`agents/`](agents/), shaped like
[`examples/proposal/agents/proposal-reviewer.md`](examples/proposal/agents/proposal-reviewer.md): who receives the output, and
what they'd hold you to. The reviewer reads as that person, reports, and never
edits.

**Company project:** brief the reviewer as whoever signs off a project at your
company: your CTO, a client, a board. What would they send back?

## Bonus: borrow a skill safely

Pick one skill from `mattpocock/skills` or `obra/superpowers` and ask your agent
to review it with [`skills/review-skill/`](skills/review-skill/). What did it find that you already had?
What gap did it fill? Did anything get flagged?

## Bonus: a hook inside the agent loop

The git hook runs at commit. Claude Code, Codex and Kiro each have their own
hooks that run before or after the agent calls a tool, so a check can fire the
moment a file is written instead of at commit. Pick your tool, find its hook
docs, and run your gate after every file write.

## Questions to bring back to the room

- What did your agent get wrong that you'd never have thought to write down?
- What did your gate catch?
- What would you never let an agent do unattended?
- What would your company never let a project start without?
