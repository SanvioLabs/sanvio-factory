# Gates: what to check, and where it runs

Read this when you add a check, move one, or decide whether a rule needs one.
[`gates/README.md`](../gates/README.md) has how to write the script. This file has whether it earns
one, where it runs, and when in the work it applies.

## Does it earn a gate?

Three tests, and it needs all three:

- **A script can decide it.** Pass or fail, no judgement. "Every section has
  text" is a gate. "The argument is convincing" is the reviewer's job, through
  a brief in [`agents/`](../agents/).
- **Missing it costs more than checking it.** An empty section a customer
  reads, a number that doesn't match its source, a key in a commit.
- **It has to hold when the agent decides otherwise.** If a line in a skill is
  enough, put it there. A gate is for the rule that already got broken once.

Fails the first test: reviewer brief. Fails the other two: a skill step or a
line in [`AGENTS.md`](../AGENTS.md).

## Where it runs

Earliest and cheapest first. Each place catches what the one above it missed.

| Where | Runs | Suits | Doesn't hold when |
|---|---|---|---|
| The skill's last step | When the agent follows the skill | Fix and recheck inside a session, before anyone sees the work | The agent skips the step |
| The guard, [`.claude/hooks/guard.py`](../.claude/hooks/guard.py) | Before each tool call. **Claude Code only** | Things that must not happen at all: reading a credential, a connector sending or deleting | Any other tool, or a command built to dodge it |
| The git hook, [`.githooks/pre-commit`](../.githooks/pre-commit) | Every commit, from any tool or person | Fast checks on the staged files. Seconds, not minutes | `core.hooksPath` isn't set in that clone, or someone uses `--no-verify` |
| CI, [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | Every push and pull request | Slow checks, whole-repo checks, the tests. The copy nobody can skip by accident | It isn't a required check, so it only reports |
| A required check | Before a merge | Turning CI from a report into a block | Nothing in the repo gets past it. [`project-setup.md`](project-setup.md) has how to set it |
| Your release step, if you have one | Before anything leaves | One-way doors: production, anything outbound. [`deploying.md`](deploying.md) has the checklist | It's run by hand and someone forgets |

Five rules for placing a check:

- **One script, many call sites.** The example's proposal gate runs in its
  skill's last step, in the hook and in CI. Same file each time. Never write a
  second copy of a check for a second place.
- **Run it early, and enforce it where it can't be skipped.** The skill step
  gives the agent the fastest fix. CI as a required check is what actually
  holds. A check only in the hook isn't enforced, because the hook setting
  doesn't travel with a clone.
- **Keep the hook fast.** A slow hook gets bypassed. Anything over a few
  seconds goes to CI only.
- **Stop the action, or judge the output.** If the harm happens the moment the
  action runs (a key read, an email sent), a gate on the result is too late.
  That's the guard's job. In Codex and Kiro there's no guard, so the earliest
  enforced point is the hook, and the rule in [`AGENTS.md`](../AGENTS.md) carries the rest.
- **A gate that can be run with no files checks everything.** The hook passes
  the staged files. CI passes none, so the gate checks the whole output
  folder. [`examples/proposal/gates/proposal_gate.py`](../examples/proposal/gates/proposal_gate.py) does both.

## When: between phases

[`operating.md`](operating.md) says each phase ends at a gate. These are the questions that
gate asks, for whatever your job is. Most are a checklist a person answers. One
or two become scripts.

| Leaving | Ask | Usually checked by |
|---|---|---|
| Discover | Is the problem, the user and the workflow each written down from a named source, not a guess? | A person |
| Shape | Is the first version written down, with success criteria someone could measure? | A script that the sections exist and aren't empty, then a person |
| Build | Do the tests and the job's gate pass, and has the reviewer read it? | Scripts, in the hook and CI |
| Validate | Was it measured against Shape's success criteria, on real use? | A person, with the numbers |
| Scale | Can it run without you: written down, watched, with a named owner? | A person |

Start with Build. It's the one a script decides best, and it's the one
Sanvio Factory already wires. [`examples/proposal/gates/phase_gate.py`](../examples/proposal/gates/phase_gate.py) is the script half for
the proposal job: it names what's missing before Shape or Build and what closes
each gap, and leaves the person's questions, and moving the phase, to a person.
