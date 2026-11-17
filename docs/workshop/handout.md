# Sanvio Factory workshop: before you come

Two hours. You'll leave with the factory running in your own clone, answering
from your team's docs, and one piece of work you repeat understood well enough
to build into a workflow. You'll watch one real ticket go through the loop to a
pull request, and see a check refuse a mistake.

## Before you come

About 20 minutes. Reply with the last line of the setup check when you're done.

1. **Claude Code on a business or team plan.** On a personal plan, bring
   invented data only.
2. **Clone the factory and run the setup check:**

   ```bash
   git clone https://github.com/SanvioLabs/sanvio-factory my-factory && cd my-factory
   git config core.hooksPath .githooks
   python3 scripts/check_setup.py
   ```

   Don't skip the middle line. Without it, the checks never run, and nothing
   tells you.
3. **Optional: make your clone a private sandbox** the loop can write to.
   The session's loop run is a demo, so you only need this to try it yourself
   afterwards. GitHub won't
   make a private fork of a public repo, so don't use Fork. From inside
   `my-factory`:

   ```bash
   git remote rename origin upstream
   gh repo create my-factory --private --source=. --remote=origin --push
   gh label create loop-ready
   gh label create loop:blocked
   ```

   Never point the loop at a production repo.
4. **Pick one place your team's standards live**: a single wiki space or
   folder, not the whole wiki. It should hold how you work, not customer
   records.
5. **Optional: pick one small, real task**: a bug, a doc fix, a small
   feature. It's your first loop run after the session.
6. **Pick one piece of work you repeat**: something that arrives, gets checked
   against your rules, and goes to someone for sign-off. You'll be interviewed
   about the last real time you did it.

## What you'll have at the end

| | Finish line |
|---|---|
| Your clone | The setup check passes, on your account, and you're its owner |
| Your knowledge | It answers a question from your docs and names the page |
| Your blueprint | One piece of work you repeat, understood well enough to say: build it, write the rules down first, or not a fit |
| The loop, watched | One real ticket goes to a pull request, and you've read it the way a reviewer would |
| A gate, watched | You've seen a check refuse a commit, and know which mistake you'd block first |

Your own first loop run and first gate are the homework after the session.

## The path from here

The session starts the first five steps. Here's the whole path:

1. Starter in your hands: the factory in your own environment, on your account, owned by you
2. Intelligence first: connect the docs you already have and check it can read them
3. Skills: the ones that match work you already do, each reviewed before it comes in
4. First motion: one small real task taken end to end
5. Gates and guards: added where the agent actually went wrong
6. Spec-driven work: feature-level specs built from your own notes
7. Team: one person first, then the whole team, improving each sprint
8. Your own loop: tickets in, built, tested and reviewed, with a person at the end

Then deploying (card 7), and a monthly review of what the factory cost and
what it bought (card 8).

## Workflows

A workflow is one piece of your team's work done the same way every time: work
comes in, an agent drafts it, a script checks it against your rules, a second
reader checks what a script can't, and a named person approves. Nothing sends
itself. [`docs/building-workflows.md`](../building-workflows.md) in the factory is the reference.

## Rules of the road

- Your data stays in your environment, reached through your own connectors.
- Connect read-only, one named space at a time.
- Never paste a credential, token or key. Reference it by name.
- The loop opens pull requests. You merge them. Auto-merge is off until the
  factory's owner turns it on, and today it stays off.

The exercises are in [`EXERCISES.md`](../../EXERCISES.md), and the walkthrough of every section is in [`README.md`](README.md).
