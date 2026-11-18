# Workflows

Your team's workflows, one folder each. A workflow is one piece of work done
the same way every time: work comes in, an agent drafts, a script checks, a
second reader checks, and a named person approves. Nothing sends itself.

How to understand, build, check and run one is in
[`docs/building-workflows.md`](../docs/building-workflows.md).

This folder starts empty.

## Starting a workflow

[`skills/run-workflow/SKILL.md`](../skills/run-workflow/SKILL.md) runs one by name, in a way its `runs` lists. It drafts
into the workflow's output, runs its gate, has its reviewer read the draft and
stops at the approval lines. `python3 scripts/workflows.py list` lists the
workflows here.

| `runs` | How you start it |
|---|---|
| `chat` | In a session: `/run-workflow supplier-terms`, or "run supplier terms on what's in its inbox" |
| `loop` | An issue naming the workflow and what to run it on, labelled for the loop. The draft comes back as a pull request, and merging it is the approval |
| `schedule` | Unattended, from cron, launchd or a CI job: `claude -p "/run-workflow supplier-terms --as schedule"`. It stops at the draft like the others |

`--as` says how it was started, and defaults to `chat`. A run `--as schedule`
is refused for any workflow whose `restricted_data` isn't `none`.
