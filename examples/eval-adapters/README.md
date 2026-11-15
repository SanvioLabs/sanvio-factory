# Eval adapters

An adapter is the `--start` command [`scripts/eval_factory.py`](../../scripts/eval_factory.py) runs once per issue. It
starts a factory on that one issue and returns when there's a pull request to merge.

| Adapter | Starts |
|---|---|
| [`one-session.py`](one-session.py) | One plain Claude Code session per issue: no rules, no review, no retries. A baseline to compare a factory against, and a starting point for your own adapter |

This factory needs no adapter of its own: its loop takes a labelled issue and opens the pull request
itself. [`examples/eval-suite/README.md`](../eval-suite/README.md) has the `--start` command for it.

## What any adapter has to do

1. Take the issue number, the clone's path and the run repo's name, from `{issue}`, `{clone}` and `{repo}`.
2. Work on that one issue only. Every issue in the suite is open from the start, so a factory that takes
   whatever is open needs telling which one.
3. Leave one pull request against `main` in the run repo, from its own branch, so the suite's CI runs on it.
4. Exit 0 once that pull request is open. Anything else ends the run, recorded as a stop.
5. Never merge. `--merge-in-run-repo` merges in the run repo once CI passes, or the run waits for a person.

[`docs/eval-walkthrough.md`](../../docs/eval-walkthrough.md) step 4 has the detail, and how to report a factory's cost.
