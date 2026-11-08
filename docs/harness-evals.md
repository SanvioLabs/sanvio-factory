# Measuring a harness

A change to a prompt, a rule or the loop can make your harness cheaper and
worse in the same commit, and reading a few pull requests won't show it. Two
scripts measure it instead.

| Script | Answers | Spends |
|---|---|---|
| [`scripts/eval_agents.py`](../scripts/eval_agents.py) | Does a review agent, or the review-pr skill, still find what it should in work with known problems? | One real session per case per run, two runs by default |
| [`scripts/eval_harness.py`](../scripts/eval_harness.py) | Does the whole harness still deliver: from issues to merged pull requests, scored by checks its agents can't see? | A new private repo per run, and the harness's model tokens |

Run the first after you change an agent's file, a skill, a job's brief or the
model. Run the second before and after a change to the harness itself, then
compare the two runs. Neither is part of the gate, and neither runs in CI: a
person starts each one.

![A suite in a private repo holds three things: seed/, a repo and its CI; issues/, 01 to 03 in order; and key/, holding score, reference/ and wrong/, which the harness never sees. eval_harness.py run makes a new private repo from the seed and files all three issues at once. The harness takes them in order, and each goes from harness building, to CI passed, to merged. A fresh clone outside the harness is scored with the key, and one scorecard prints, with made-up figures: tests 28/30, traps 5/5, time 41.2 minutes, stops 0, rounds 6, tokens 1,912,408, cost $5.80. Then eval_harness.py compare run-a run-b names what moved: Better, test refunds round to the cent; Worse, test an empty cart is refused. Compare the same suite on the same models, so the change is yours.](harness-evals.gif)

## Is a reviewer still catching things?

A case is a piece of made-up work, usually with a problem planted in it, and
a `case.json` that says what a good review of it must find, which lines it must
cover, and what it must leave alone. Each set also has a clean case, so a
reviewer that flags everything fails too. Keep one in any set you write. The
starter has three sets:

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

## Did the change make the harness better?

[`scripts/eval_harness.py`](../scripts/eval_harness.py) runs a harness through a suite of jobs and
prints one scorecard. It works on any harness that takes GitHub issues, not
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

The key is the part the harness must never see. A trap is a wrong move the
key checks for, such as editing the seed's own test until it passes. Before
you spend a token on a suite, check it's a fair test:

```bash
python3 scripts/eval_harness.py validate <suite>
```

It passes only when the seed fails, each wrong answer fails and the reference
passes everything. It creates no repo and spends nothing.

### A run

You need `gh` signed in with the right to create repos in the owner you pass
as `--owner`, on a paid GitHub plan: the run protects its repo's `main`, and a
private repo's branch protection needs one. On a free plan the repo is created
and kept, and setup stops there. The harness's own agent needs to be signed in
too.

`run` makes a private repo in that owner, from the seed, and files every issue
at the start. Then it runs your `--start` command on each issue in order, which
starts the harness on that one issue. With `--merge-in-run-repo` it merges each pull
request once its required checks pass, in that repo alone. Without it, the run
stops at each merge for you to merge by hand, then `resume` carries on. When
the last issue is done, a fresh clone outside the harness is scored with the
key.

[`examples/eval-suite/README.md`](../examples/eval-suite/README.md) has the `--start` command that drives this
harness's loop, and how to run one on a local model for no token spend.

### Reading the scorecard

```
Suite     tiny-example
Harness   a1b2c3d4e5f6
Tests     2/3
Traps     1/1
  failed: no tax
Time      6.2 min
Stops     0
Rounds    2
Tokens    412,306
Cost      $0.94
```

That's a made-up run of the starter's own suite, in the real shape.

| Line | Means |
|---|---|
| Harness | The harness commit the run used, marked when it had uncommitted changes |
| Tests, Traps | How many of the key's checks passed, and how many traps the harness avoided, with each miss named underneath |
| Key leak | Shown only when one of the key's hidden files, such as `score`, turned up in the run repo's history. The run then exits 1, whatever it scored |
| Time | Wall-clock time for the whole run, merge waits included |
| Stops | Every time the run couldn't carry on by itself: a start command that failed or timed out, CI that failed, a pull request closed without merging, each wait for a merge (shown as `N at merges`), and each `stop <run> "why"` a person recorded |
| Rounds, Tokens | From this harness's loop. Another harness reads `not reported` |
| Cost | From `--usage-command`, or else this harness's loop. `not reported` means nothing reported it, never that it was free |

### Comparing two runs

```bash
python3 scripts/eval_harness.py list
python3 scripts/eval_harness.py compare <run-a> <run-b>
```

`compare` puts two scorecards side by side and names every test or trap that
changed: `Better:` and `Worse:`, and `New:` or `Gone:` when the suite itself
changed. With no change it says `Nothing changed in tests or traps.` Compare
runs of the same suite, on the same models, both with or both without
`--merge-in-run-repo`, or the difference may be the model, or the merge waits,
rather than your change.

### Pointing it at another harness

Pass `--harness <folder>` for the harness to run, and a `--start` command that
starts it on the one issue in `{issue}`. Every issue is open from the start, so
a harness that takes whatever is open starts later issues early and spoils the
run. Give `--usage-command` a command that prints the run's
total cost as one number, or the cost reads `not reported`.

## Keeping a suite fair

- **A public suite can't measure anything.** An agent can read it, the key
  included. [`examples/eval-suite/`](../examples/eval-suite/) is public to show the format, and
  that's all it's for.
- **Keep a real suite in a private repo,** outside the harness and anywhere its
  agents may read. The script refuses a key inside the harness or the clone
  folder, and checks the run repo's history for the key's files, but it can't
  see what an agent read.
- **Use made-up data only.** Scoring runs code an agent wrote, on your machine,
  with an empty `HOME` and no `gh` login, but with the network and whatever
  else you can read.
- **Run repos stay until you delete them.** Nothing in the script deletes one.
  `list` shows each run and its repo.

Start by running the starter's own suite once to see the shape, then write a
small private suite around one job your team does every week.
