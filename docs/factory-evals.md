# Measuring a factory

A change to a prompt, a rule or the loop can make your factory cheaper and
worse in the same commit, and reading a few pull requests won't show it. Two
scripts measure it instead.

| Script | Answers | Spends |
|---|---|---|
| [`scripts/eval_agents.py`](../scripts/eval_agents.py) | Does a review agent, or the review-pr skill, still find what it should in work with known problems? | One real session per case per run, two runs by default |
| [`scripts/eval_factory.py`](../scripts/eval_factory.py) | Does the whole factory still deliver: from issues to merged pull requests, scored by checks its agents can't see? | A new private repo per run, and the factory's model tokens |

New to this? [`eval-walkthrough.md`](eval-walkthrough.md) takes you through a first run of the second
script, then a baseline, your own factory, an A/B test and a suite of your own, in that order.

In Claude Code, the [`factory-eval`](../skills/factory-eval/SKILL.md) skill runs both for you: say "eval the
factory". It checks a suite first and asks before anything spends tokens.

Run the first after you change an agent's file, a skill, a job's brief or the
model. Run the second before and after a change to the factory itself, then
compare the two runs. Neither is part of the gate, and neither runs in CI: a
person starts each one.

![A suite in a private repo holds seed/, a repo and its CI; issues/, 01, 02 and 03 in order; and key/, holding score, reference/ and wrong/, which the factory never sees. eval_factory.py run makes a new repo from the seed, and issues 1, 2 and 3 are merged one at a time, each after its CI passes. A scorecard follows, with made-up figures: tests 28/30, traps 5/5, stops 0, time 41.2 minutes, cost $5.80 via --usage-command. With --repeat 3 there are three runs, and the scorecard shows the middle of them. eval_factory.py compare a-1,a-2,a-3 b-1,b-2,b-3 compares two groups and names what moved: Better, test refunds round to the cent, from 1/3 to 3/3; Worse, test an empty cart is refused, from 3/3 to 2/3, flaky in B. eval_factory.py report writes report.pdf, .html and .md, with each issue, misses by issue and every check.](factory-evals.gif)

## Is a reviewer still catching things?

A case is a piece of made-up work, usually with a problem planted in it, and
a `case.json` that says what a good review of it must find, which lines it must
cover, and what it must leave alone. Each set also has a clean case, so a
reviewer that flags everything fails too. Keep one in any set you write. This
repo has three sets:

| Folder | Reviews it |
|---|---|
| [`examples/proposal/evals/`](../examples/proposal/evals/) | The `reviewer` agent, on a proposal |
| [`examples/typescript/evals/`](../examples/typescript/evals/) | The `security-reviewer` agent, on code |
| [`examples/ci/evals/`](../examples/ci/evals/) | The review-pr skill, on a diff |

Run a set, keep the result, and next time see which cases changed:

```bash
python3 scripts/eval_agents.py examples/ci/evals --save
python3 scripts/eval_agents.py examples/ci/evals --save --baseline latest
```

Each case runs twice. Both runs passing is stable, one is flaky, and neither is
failing. Results go to `.sanvio/evals/`, which stays on your machine.
[Testing the review](../examples/ci/README.md#testing-the-review) says how to add a case of your own.

## Did the change make the factory better?

[`scripts/eval_factory.py`](../scripts/eval_factory.py) runs a factory through a suite of jobs and
prints one scorecard. It works on any factory that takes GitHub issues, not
only this one.

### What a suite holds

```
suite.json        name, seed, key, issues in order, required_checks
seed/             the repo a run starts from, with its CI workflow
issues/           one Markdown file per issue, its first line the title
key/
  score           executable: prints which tests passed and which traps were avoided
  reference/      overlays the seed to make the right answer
  wrong/<name>/   overlays the seed to make a known wrong answer
```

The key is the part the factory must never see. A trap is a wrong move the
key checks for, such as editing the seed's own test until it passes. A test
or trap in `score`'s output may also carry `"issue"`, the position of the
issue it checks in `suite.json`'s list, from 1. A report then groups what was
missed by issue.

To start one, `new-suite` makes the folders and files to fill in, with a
`score` to start from. It refuses a folder inside the factory:

```bash
python3 scripts/eval_factory.py new-suite ../my-suites/billing
```

Before you spend a token on a suite, check it's a fair test:

```bash
python3 scripts/eval_factory.py validate <suite>
```

It passes only when the seed fails, each wrong answer fails and the reference
passes everything. It creates no repo and spends nothing.

### A run

You need `gh` signed in with the right to create repos in the owner you pass
as `--owner`, on a paid GitHub plan: the run protects its repo's `main`, and a
private repo's branch protection needs one. On a free plan the repo is created
and kept, and setup stops there. The factory's own agent needs to be signed in
too.

`run` makes a private repo in that owner, from the seed, and files every issue
at the start. Then it runs your `--start` command on each issue in order, which
starts the factory on that one issue. With `--merge-in-run-repo` it merges each pull
request once its required checks pass, in that repo alone. Without it, the run
stops at each merge for you to merge by hand, then `resume` carries on. When
the last issue is done, a fresh clone outside the factory is scored with the
key.

[`examples/eval-suite/README.md`](../examples/eval-suite/README.md) has the `--start` command that drives this
factory's loop, and how to run one on a local model for no token spend.

### Reading the scorecard

```
Suite     tiny-example
Factory   a1b2c3d4e5f6
Tests     2/3
Traps     1/1
  failed: no tax
Time      6.2 min
Stops     0
Rounds    2
Tokens    412,306
Cost      $0.94
```

That's a made-up run of this repo's own suite, in the real shape.

| Line | Means |
|---|---|
| Factory | The factory commit the run used, marked when it had uncommitted changes |
| Tests, Traps | How many of the key's checks passed, and how many traps the factory avoided, with each miss named underneath |
| Key leak | Shown only when one of the key's hidden files, such as `score`, turned up in the run repo's history. The run then exits 1, whatever it scored |
| Time | Wall-clock time for the whole run, merge waits included |
| Stops | Every time the run couldn't carry on by itself: a start command that failed or timed out, CI that failed, a pull request closed without merging, each wait for a merge (shown as `N at merges`), and each `stop <run> "why"` a person recorded |
| Rounds, Tokens | From this factory's loop. Another factory reads `not reported` |
| Cost | From `--usage-command`, or else this factory's loop. `not reported` means nothing reported it, never that it was free |

### Comparing two runs

```bash
python3 scripts/eval_factory.py list
python3 scripts/eval_factory.py compare <run-a> <run-b>
```

`compare` puts two scorecards side by side and names every test or trap that
changed: `Better:` and `Worse:`, and `New:` or `Gone:` when the suite itself
changed. With no change it says `Nothing changed in tests or traps.` Compare
runs of the same suite, on the same models, both with or both without
`--merge-in-run-repo`, or the difference may be the model, or the merge waits,
rather than your change.

### A report to share

```bash
python3 scripts/eval_factory.py report <run> [--compare <other-run>]
```

`report` writes the run's `report.html` and `report.md` into its folder, and
`report.pdf` when Chrome, Chromium or Edge is installed to print it. Without
one, it says so: open the HTML and print it to PDF. Each holds the verdict,
the headline numbers, each issue with its pull request and time, what was
missed grouped by issue, every check, the stops, the run's details, and an
appendix on reading the report and writing a suite. `--compare` adds a second
run beside it, with what got worse and what got better. `--out <folder>`
writes them somewhere else. Set `EVAL_REPORT_BROWSER` to name the browser, or
to nothing for no PDF.

### Pointing it at another factory

Pass `--factory <folder>` for the factory to run, and a `--start` command that
starts it on the one issue in `{issue}`. Every issue is open from the start, so
a factory that takes whatever is open starts later issues early and spoils the
run. Give `--usage-command` a command that prints the run's
total cost as one number, or the cost reads `not reported`.
[`examples/eval-adapters/`](../examples/eval-adapters/) has two adapters to start from, one for a
factory that opens its own pull requests and one that opens them for it, and
the list of what any start command has to do.

If the factory runs Claude Code in the run's clone, the cost command can be
[`scripts/eval_session_cost.py`](../scripts/eval_session_cost.py). It adds up those sessions from Claude
Code's own transcripts, at the prices in `.sanvio/prices.json` (copy
[`scripts/prices.example.json`](../scripts/prices.example.json) and fill in each model you use):

```bash
--usage-command "python3 $PWD/scripts/eval_session_cost.py {clone}"
```

It prints nothing, so the cost reads `not reported`, when it can't give the
whole figure: no sessions in the clone, no prices file, or a model with no
price. `--detail` shows tokens and dollars by model.

### Repeat runs

One run of a factory can pass a check that the next run fails. Before you keep
a change, run each side more than once:

```bash
python3 scripts/eval_factory.py run <suite> --repeat 3 --merge-in-run-repo ...
```

That makes three runs, each in its own repo, and prints their names joined by
commas. Wherever `compare` and `report` take a run, they also take a group like
that:

```bash
python3 scripts/eval_factory.py compare a-1,a-2,a-3 b-1,b-2,b-3
python3 scripts/eval_factory.py report b-1,b-2,b-3 --compare a-1,a-2,a-3
```

A group shows the middle result of its runs. `compare` names each check whose
pass rate moved (`Worse: test refunds round to the cent (from 3/3 to 1/3)`) and
each check that passed in some runs and not others, as `Flaky in A:` or
`Flaky in B:`. Don't read much into a flaky check from one run.

`report` also takes several suites at once, one run or group each, with the
same number after `--compare`. It starts with a summary table and gives each
suite its own section.

## Keeping a suite fair

- **A public suite can't measure anything.** An agent can read it, the key
  included. [`examples/eval-suite/`](../examples/eval-suite/) and
  [`examples/eval-suite-tool-library/`](../examples/eval-suite-tool-library/) are public to show the format, and
  that's all they're for.
- **Keep a real suite in a private repo,** outside the factory and anywhere its
  agents may read. The script refuses a key inside the factory or the clone
  folder, and checks the run repo's history for the key's files, but it can't
  see what an agent read.
- **Use made-up data only.** Scoring runs code an agent wrote, on your machine,
  with an empty `HOME` and no `gh` login, but with the network and whatever
  else you can read.
- **Run repos stay until you delete them.** Nothing in the script deletes one.
  `list` shows each run and its repo.

[`writing-eval-suites.md`](writing-eval-suites.md) covers how to build a suite that tells factories
apart: issues, checks, traps, wrong answers, and checking it isn't too easy.

Start by running this repo's own suite once to see the shape, then write a
small private suite around one job your team does every week.

## Cleaning up

A run leaves its repo on GitHub, its clone in the factory's [`projects/`](../projects/) (or
`--clone-into`), and its results in `.sanvio/factory-evals/<run>/`. Keep the
results: `compare` and `report` read them. Delete the rest when you're done:

```bash
python3 scripts/eval_factory.py list
gh repo delete <owner>/<run-repo>        # asks you to confirm, and needs the delete_repo scope
```

Then remove the run's clone folder. Nothing in the script deletes any of
these: deleting is a person's call.

## When a run doesn't go to plan

| What you see | What it means and what to do |
|---|---|
| Setup stops after creating the repo, mentioning an upgrade | Branch protection on a private repo needs a paid GitHub plan. Use an owner on one |
| The factory says there's nothing to do, or takes the wrong issue | Every issue is open from the start. Tell the factory which one: a label it watches, or an argument. A new label can take a few seconds to show in GitHub's issue list |
| Every start fails at once on a local model | Check the wrapper sets `ANTHROPIC_BASE_URL` to your local server, and that the model name in `EVAL_MODEL` or your factory's config is one the server has |
| Cost reads `not reported` | Nothing reported it. Pass `--usage-command`, and see what `eval_session_cost.py --detail` says it's missing |
| `issue N produced 2 pull requests` | The start command opened more than one. The run won't guess which to merge, so it stops: make the adapter open exactly one |
| A run waits at every merge | It ran without `--merge-in-run-repo`. Merge in the run repo, then `resume <run>`, or `resume <run> --end` to score what exists |
| `report` writes no PDF | No Chrome, Chromium or Edge could print it. Open `report.html` and print it to PDF, or name a browser in `EVAL_REPORT_BROWSER` |
| CI doesn't start on a pull request | GitHub runs `pull_request` workflows only on a pull request that can merge. A conflict holds CI back |
