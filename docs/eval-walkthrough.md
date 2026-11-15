# Your first factory eval, step by step

Six steps, from a clone of this repo to a measured answer about your own
factory. Steps 1 and 3 spend nothing. Step 2 spends nothing on a local model.
[`factory-evals.md`](factory-evals.md) is the reference for every command and field; this page is
the order to do them in.

![Who does what in a run, in three columns. eval_factory.py makes a private repo from the seed and files every issue, then runs your --start command for issue N with the issue number, the clone and the repo. Your adapter tells your factory to work issue N and only N. Your factory builds, tests and reviews, whatever it does, and opens one pull request against main. The adapter exits 0 once that pull request is open. eval_factory.py waits for the required checks, merges, and goes on to the next issue. After the last issue it scores a fresh clone with key/, which the factory never sees.](eval-walkthrough.svg)

You need Python 3.8 or later, `gh` signed in with the right to create private
repos in a GitHub organisation on a paid plan, and Claude Code signed in, or a
local model behind it.

## 1. Check the examples

Two public suites ship with this repo. Check both:

```bash
python3 scripts/eval_factory.py validate examples/eval-suite
python3 scripts/eval_factory.py validate examples/eval-suite-tool-library
```

Each prints `the seed fails, each wrong answer fails, the reference passes`.
That's what makes a suite fair: the untouched repo scores badly, every known
mistake is caught, and the right answer scores full marks. No repo is created
and no model runs.

[`examples/eval-suite-tool-library/`](../examples/eval-suite-tool-library/) is the one to learn from: three issues in
order, 12 hidden tests and two traps. Its [README](../examples/eval-suite-tool-library/README.md) says what each part
tests.

## 2. Run a baseline

Before you measure your factory, measure the plainest thing that could do the
work: one Claude Code session per issue, with no rules, review or retries.
[`examples/eval-adapters/one-session.py`](../examples/eval-adapters/one-session.py) is that, as an adapter. Your factory
has to beat it to be worth its cost.

```bash
python3 scripts/eval_factory.py run examples/eval-suite-tool-library --owner <your-org> \
  --merge-in-run-repo \
  --start "python3 $PWD/examples/eval-adapters/one-session.py {issue} {clone} {repo}"
```

It says what it will create and spend, and asks first. Then it makes a
private repo named after the suite and the time, files the three issues, and
runs the adapter on each in turn. With `--merge-in-run-repo` it merges each pull
request once the suite's CI passes, in that repo and nowhere else.

To spend no tokens, run the session on a local model. Point `EVAL_CLAUDE` at a
wrapper script that sets `ANTHROPIC_BASE_URL` to your local server before it
runs `claude`, name the model in `EVAL_MODEL`, and add `--usage-command 'echo 0'`,
because Claude Code prices local tokens as though they were Anthropic's:

```bash
EVAL_CLAUDE=~/bin/claude-local EVAL_MODEL=<local-model> \
  python3 scripts/eval_factory.py run examples/eval-suite-tool-library --owner <your-org> \
  --merge-in-run-repo --usage-command 'echo 0' \
  --start "python3 $PWD/examples/eval-adapters/one-session.py {issue} {clone} {repo}"
```

## 3. Read the scorecard

This is a real run of step 2, on a 35B coding model served locally, on
15 November 2026:

```
Suite     tool-library-example
Factory   cb6ccff9c193 (with uncommitted changes)
Tests     12/12
Traps     2/2
Time      6.0 min
Stops     0
Rounds    not reported
Tokens    not reported
Cost      $0.00
```

A plain session got every test, so this suite can't separate a good factory
from a plain one. It isn't meant to: it's public and small, for learning the
shape. Your own suite, from step 6, is the one that tells factories apart.

What to look at, in order:

1. **Tests and Traps.** Any miss is named underneath, by behaviour: `failed: a
   fee stops at the replacement cost`. A trap miss is the one to worry about:
   the work passed CI and was still wrong.
2. **Stops.** Each time the run couldn't carry on alone: a failed start, failed
   CI, a pull request closed unmerged. A factory that scores well with stops
   needed a person to get there.
3. **Time and Cost.** Only worth comparing once the first two hold.

`Rounds` and `Tokens` come from this factory's own loop, so another factory
reads `not reported`. `list` shows every run and its repo. Run repos stay until
you delete them.

## 4. Point it at your factory

Write a `--start` command for your factory. Whatever it is, it has to:

1. Take `{issue}`, `{clone}` and `{repo}`, and work on that one issue. Every
   issue is open from the start, so a factory that picks up whatever is open
   needs telling which one, with a label or an argument.
2. Leave one pull request against `main` in `{repo}`, from its own branch.
3. Exit 0 once the pull request is open. Anything else ends the run as a stop.
4. Never merge. The run does that after CI, or waits for you.

If your factory opens its own pull requests, the adapter only starts it on
the issue and waits for it to finish. If it doesn't, copy `one-session.py` and
replace the one `claude -p` call with your factory's own command: the adapter
then commits what it left, pushes and opens the pull request.

Pass `--factory <folder>` so the command runs in your factory's folder, and
`--timeout <minutes>` if an issue can take more than the default 60.

For cost, give `--usage-command` a command that prints one number: the run's
total, in dollars. Usually that's a short script that sums your factory's own
usage records since the run started. Without one, cost reads `not reported`,
never zero.

Run the same suite through your factory as you ran the baseline in step 2.

## 5. Test one change at a time

The reason to have evals is to try a change and see what it did:

1. Run the suite on your factory as it is. That's run A.
2. Change one thing: a model for one stage, one prompt line, a retry limit.
3. Run the same suite again, on the same models, with the same flags. That's run B.
4. Compare:

```bash
python3 scripts/eval_factory.py list
python3 scripts/eval_factory.py compare <run-a> <run-b>
```

`compare` names every test and trap that moved, as `Better:` or `Worse:`.

Agent runs vary, so one run each way can mislead. For a change you'll keep,
run each side three times and compare the middle result. Keep a change when
tests and traps hold and time or cost drops, or when they improve at a cost
you accept. Two changes in one pair can't be told apart, so change one thing
per pair.

## 6. Write a suite of your own

The examples are public, so any agent can read their keys. A suite that
measures something has to be one your factory has never seen.

1. **Pick work your team really does.** A bug fixed last month, a small
   feature, a change that touched more files than it looked like it would.
   Rewrite it with made-up names and data. Never real customer data.
2. **Seed:** the repo as it was before, with its CI workflow. `seed/loop.json`
   only matters for this factory's loop.
3. **Issues:** what a person would write, in the order they'd come. Describe
   the problem a user sees, not the fix.
4. **Reference:** the right answer, as files that overlay the seed.
5. **Wrong answers:** one folder per mistake you've seen agents make. Each
   should fail for one reason.
6. **Score:** `key/score` checks behaviour, not wording, and prints its JSON.
   A trap is a wrong move the tests can't see, such as editing an existing
   test until it passes, or breaking a caller outside the repo.
7. **Validate** until it passes, then validate again after every change.

Keep the suite in a private repo, outside your factory and anywhere its
agents can read. The script refuses a key inside the factory or its clone
folder, and checks every run repo's history for the key's files, but it can't
see what an agent read.

Start with one suite of three issues around a job your team does every week,
and run it before and after the next change you make to your factory.
