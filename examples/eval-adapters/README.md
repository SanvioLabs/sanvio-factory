# Eval adapters

An adapter is the `--start` command [`scripts/eval_factory.py`](../../scripts/eval_factory.py) runs once per issue. It
starts a factory on that one issue and returns when there's a pull request to merge.

| Adapter | Starts |
|---|---|
| [`one-session.py`](one-session.py) | One plain Claude Code session per issue: no rules, no review, no retries. A baseline to compare a factory against, and a starting point for an adapter to a factory that doesn't open its own pull requests |
| [`label-and-wait.py`](label-and-wait.py) | A factory that picks issues up by a label and opens its own pull requests: it labels the one issue, waits for a new pull request, and exits. `EVAL_LABEL` names the label |

This factory needs no adapter of its own: its loop takes a labelled issue and opens the pull request
itself. [`examples/eval-suite/README.md`](../eval-suite/README.md) has the `--start` command for it.

![Two kinds of adapter. The run calls --start once per issue, and either way the adapter leaves one pull request and exits 0. one-session.py, for a factory that doesn't open pull requests: it starts one Claude Code session on issue N in the run's clone; the session edits the clone and can't push or call gh; the adapter commits, pushes and opens the pull request; and it exits 0, or 1 if nothing changed. label-and-wait.py, for a factory that opens its own: it labels issue N and only N, with EVAL_LABEL, loop-ready by default; your factory picks it up however it watches the repo and opens the pull request; the adapter sees the new pull request and exits 0, or 1 on time out or the stopped label. Neither adapter merges. The run merges each pull request after its CI passes, then starts the next issue.](../../docs/eval-adapters.gif)

## What any adapter has to do

1. Take the issue number, the clone's path and the run repo's name, from `{issue}`, `{clone}` and `{repo}`.
2. Work on that one issue only. Every issue in the suite is open from the start, so a factory that takes
   whatever is open needs telling which one.
3. Leave one pull request against `main` in the run repo, from its own branch, so the suite's CI runs on it.
4. Exit 0 once that pull request is open. Anything else ends the run, recorded as a stop.
5. Never merge. `--merge-in-run-repo` merges in the run repo once CI passes, or the run waits for a person.

[`docs/eval-walkthrough.md`](../../docs/eval-walkthrough.md) step 4 has the detail. For cost, a factory that runs Claude
Code in the clone can use [`scripts/eval_session_cost.py`](../../scripts/eval_session_cost.py) as its `--usage-command`.
