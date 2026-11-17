---
name: check-workflow
description: Check one workflow folder against the workflow contract with a single command, and say what's missing or wrong, or that it passes. Never edits the workflow it checks. Use when asked to check a workflow, whether a workflow in workflows/ meets the contract or is ready, after building one, or before calling one done or changing its status.
license: MIT. From Sanvio Factory by Sanvio Labs, https://github.com/SanvioLabs/sanvio-factory
---

# Check a workflow

[`docs/building-workflows.md`](../../docs/building-workflows.md) is the contract: *The workflow folder* says
what a workflow holds and *The trust tests* says what proves it. This skill
runs [`scripts/check_workflow.py`](../../scripts/check_workflow.py), which checks one folder against both and
prints `PASS`, or one problem per line.

## When to run it

- Right after `build-workflow` writes a folder.
- Before saying a workflow is done, ready or finished.
- Before changing its `status` in `workflow.json`, to `live` or back.
- When someone asks whether a workflow in [`workflows/`](../../workflows/) meets the contract.

## Steps

1. **Name the folder.** It's `workflows/<name>/`. If the person didn't say
   which, list the folders in [`workflows/`](../../workflows/) and ask. Don't guess.
2. **Run the check** from the harness root and show the output as it came:

   ```bash
   python3 scripts/check_workflow.py workflows/<name>
   ```

   It runs the workflow's gate on every eval case, sample output and the
   template, and runs the workflow's own tests, each from the workflow's
   folder. Nothing it runs sends anything.
3. **Read the result.** `PASS` and exit 0 means the folder meets the contract.
   Anything else is a list of problems and exit 1. Report every line, grouped
   as below, with the fix each one needs.
4. **Stop there.** This skill never edits, adds or removes a file in the
   workflow it checks. If the person wants the fixes made, that's a separate
   change, and the check runs again after it.

## Reading what it prints

Each line starts with the part of the folder it's about.

| The line | Means | The fix |
|---|---|---|
| `missing: <path>` | A file or folder the contract requires isn't there | Add it. `build-workflow` writes every one |
| `workflow.json: <problem>` | The manifest can't be read, lacks a key, has a value outside the listed ones, or names a path that doesn't exist | Correct the manifest. `name` matches the folder, and a workflow touching restricted data never lists `schedule` in `runs` |
| `evals/gate/<case>: <problem>` | The gate didn't refuse that case, didn't print its `says` text, or the case doesn't expect `fail` | Fix the gate so it catches the case, or the case's `says` to what the gate prints for it. Never weaken a case to pass |
| `evals/review/<case>: the gate fails it, so it sits in the wrong folder` | The gate refuses a case meant to pass it | Move it to `evals/gate/` with a `says`, or fix its output so only judgement catches it |
| `evals/gate: <n> cases` or `evals/review: <n> case` | Too few cases: six and two at least | Write more, starting from the blueprint's `went_wrong` and `never` |
| `sample/outputs/<file>: fails the gate` | A sample output fails the gate | Fix the output, or the gate if the output is right |
| `<template>: passes the gate unfilled` | The template passes the gate as it stands | The gate has to refuse template text left in |
| `sample/inputs/<file>: no invented: true` | An input doesn't say it's invented | Add it to the frontmatter, or at the top level of a JSON input |
| `<file>: line <n> names standard/` | A sample output or eval points at your standard, not at `sample/standard/` | Point it at `sample/standard/`, so rewriting `standard/` never breaks the tests |
| `tests: <problem>` | The workflow's own tests failed, or ran none | Fix what the named test says. A test file that runs no tests isn't a trust test |
| `skipped: <checks>` | Checks that couldn't run, because the manifest names no gate or template that exists | Fix the `workflow.json` lines, then run the check again |

## Rules

- Run it, show the output, and say PASS only when it printed `PASS`.
- Never edit a gate, a case or a test to make the check pass. A case that
  fails is the check working.
- It checks that the README exists, not what it says, and not the seven rules'
  content. Those stay with the reviewer and the person who owns the workflow.
