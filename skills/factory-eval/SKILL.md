---
name: factory-eval
description: Measure the factory, so a change to a prompt, a rule, a model or the loop is judged by results rather than by reading a few pull requests. Checks whether the review agents still catch known defects, runs the whole factory through a suite of jobs and scores it with checks its agents can't see, and compares two runs. Checks a suite for free first, says what a run creates and spends, and starts one only on a yes. Never deletes a run's repo. Use when someone asks to "eval the factory", "run the evals", "harness eval", "factory eval", "did that change make the factory better", "is the factory worse", "compare two runs", "do the reviewers still catch things", or "score the factory".
license: MIT. From Sanvio Factory by Sanvio Labs, https://github.com/SanvioLabs/sanvio-factory
---

# Factory eval

A change to the factory can make it cheaper and worse in the same commit.
This skill measures it, with the two scripts [`docs/factory-evals.md`](../../docs/factory-evals.md)
walks through:

| Script | Answers | Spends |
|---|---|---|
| [`scripts/eval_agents.py`](../../scripts/eval_agents.py) | Does a review agent, or the review-pr skill, still find what it should? | One session per case per run, two runs by default |
| [`scripts/eval_factory.py`](../../scripts/eval_factory.py) | Does the whole factory still deliver, from issues to merged pull requests? | A new private repo per run, and the factory's model tokens |

You run the commands and read the results. The person decides what runs, and
they delete what a run leaves behind.

## Rules for this skill

- Never start anything that spends model tokens or creates a repo without the
  person's yes to that one run, after you've said what it creates and spends.
  `--yes` goes on the command only after that yes, because the script can't
  ask from inside an agent's shell.
- Validate a suite before its first run, and again after anyone changes it.
  It's free, and a suite that fails validation can't tell you anything.
- Never read, print or summarise anything in a suite's `key/`. A key is what
  the factory must never see, and anything you read can end up in a prompt.
  Report what the scripts print about it: names of tests and traps, and pass
  or fail.
- Never put a suite inside this factory, its [`projects/`](../../projects/), or any folder its
  agents can read. The script refuses a key inside the factory or the clone
  folder. Say so when the person names a suite there, and stop. The one
  exception is [`examples/eval-suite/`](../../examples/eval-suite/), which is public on purpose and
  can't tell you how good a factory is.
- Never delete a run's repo, close its issues or merge its pull requests
  yourself. `--merge-in-run-repo` lets the script merge in the repo it created
  and nowhere else.
- Compare only runs of the same suite, on the same models, both with or both
  without `--merge-in-run-repo`. If the two runs differ in any of those, say
  so above the comparison, because the difference may not be the change.
- Suites hold made-up data only. If a suite's seed or issues look like real
  customer or personal data, stop and say so before anything runs.

## Steps

### 1. Find out what they want to know

Ask, if it isn't clear already:

- **Do the reviewers still catch things?** After a change to an agent's file,
  a skill, a job's brief or the model. Go to step 2.
- **Did a change make the factory better or worse?** Before and after a
  change to the factory itself. Go to step 3.
- **How did two runs compare?** Go to step 5.

### 2. Check the review agents

Name the sets this repo has, from [`docs/factory-evals.md`](../../docs/factory-evals.md): [`examples/proposal/evals/`](../../examples/proposal/evals/)
for the `reviewer`, [`examples/typescript/evals/`](../../examples/typescript/evals/) for the `security-reviewer`,
[`examples/ci/evals/`](../../examples/ci/evals/) for the review-pr skill, and any of the person's own.
Say how many cases the chosen set has and that each runs twice, then ask
before starting. On a yes:

```bash
python3 scripts/eval_agents.py <set> --save --baseline latest
```

With no earlier result saved, drop `--baseline latest`. Report each case as
stable (both runs pass), flaky (one) or failing (neither), and which cases
changed since the baseline. A clean case that now fails means the reviewer
flags too much. A planted problem it no longer finds means it misses things.
Both matter.

### 3. Check the suite, then say what a run costs

Ask which suite. A real one lives in a private repo outside this factory. On
this machine, the person may keep their suites in one folder. Ask for the
path rather than looking for it.

Validate it first:

```bash
python3 scripts/eval_factory.py validate <suite>
```

It spends nothing. Exit 0 means the seed fails, each wrong answer fails and
the reference passes everything. Exit 1 or 2 means stop: report what it
printed, and don't offer a run.

Then show, before anything runs:

- the owner the run repo goes in (`--owner`), and that the repo is private
  and stays until they delete it
- that `gh` needs the right to create repos there, on a paid plan, because
  the run protects its repo's `main`
- the start command. For this factory's loop it's the one in
  [`examples/eval-suite/README.md`](../../examples/eval-suite/README.md). For another factory, they give it, along
  with `--factory` and a `--usage-command`
- whether it merges in the run repo (`--merge-in-run-repo`), or stops at each
  merge for them
- the issue count, and that each one runs the factory's agents once at least.
  If an earlier run of this suite exists in `python3 scripts/eval_factory.py list`,
  give its time and cost as the best guess of this one's
- that scoring runs code an agent wrote on this machine, with an empty `HOME`
  and no `gh` login, but with the network

Ask for a yes to that run. A no ends here.

### 4. Run it

On a yes, start it in the background. A run takes minutes to an hour:

```bash
python3 scripts/eval_factory.py run <suite> --owner <owner> --start '<start command>' [--merge-in-run-repo] --yes
```

Exit 0 means every test and trap was clean with no key leak, and 1 means
something wasn't. Exit 3 means it stopped at a merge: tell the person which
pull request is waiting, and once they've merged it, `python3 scripts/eval_factory.py resume <run>`
carries on. If they want to end a run early, `stop <run> "why"` records it
and `resume <run> --end` scores what it got to.

Print the scorecard as the script gave it, then add at most three lines:
- the misses by name
- any key leak, which makes the run count as failed whatever it scored
- each stop, and what caused it

### 5. Compare

```bash
python3 scripts/eval_factory.py list
python3 scripts/eval_factory.py compare <run-a> <run-b>
```

Say which run is before the change and which is after. Check both ran the same
suite, on the same models, with the same merge setting. Then give the
`Better:`, `Worse:`, `New:` and `Gone:` lines, and the change in time, rounds,
tokens and cost. One run each way is a weak signal, because a model's runs
vary. When the difference is a test or two, recommend three runs each and
comparing the middle result, before anyone acts on it.

### 6. Say what's left behind

End by listing every run repo this session created, by name. Say that each
one stays until they delete it, and that `gh repo delete <owner>/<name>`
removes one when they're done. Don't run it.

## Output

The scorecard or the comparison as the script printed it, the few lines
above, then what's left behind. When the evidence supports one, finish with a
recommendation: keep the change, revert it, or run it again.
