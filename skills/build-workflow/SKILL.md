---
name: build-workflow
description: Build a workflow folder in workflows/<name>/ from a blueprint whose outcome is build and whose standard is written, then run check_workflow.py on it and call it done only when it prints PASS. Stops and writes nothing when the blueprint isn't ready or the folder already exists. Use when a blueprint ends in build, or when asked to build, scaffold or set up a workflow from a blueprint.
license: MIT. From Sanvio Factory by Sanvio Labs, https://github.com/SanvioLabs/sanvio-factory
---

# Build a workflow

[`docs/building-workflows.md`](../../docs/building-workflows.md) is the contract: *The workflow folder* says
what a workflow holds, *The rules* says what every output does, and *The trust
tests* says what proves it. Read all three before writing a file. This skill
is step 2 of building a workflow: `blueprint-workflow` comes before it, and
`check-workflow` checks what it writes.

[`examples/workflows/supplier-terms/`](../../examples/workflows/supplier-terms/) is a folder built this way, from
[`examples/blueprints/supplier-terms.md`](../../examples/blueprints/supplier-terms.md). Copy its shape, not its rules.

## Steps

1. **Read the blueprint.** It's `blueprints/<name>.md`. If the person didn't
   name one, list the files in `blueprints/` and ask. Then check two keys, and
   stop on either, writing nothing:
   - `outcome` isn't `build`. Say the key and its value, and what comes next:
     `write-standard` means the rules live in someone's head, so writing them
     down is the first piece of work; `no-fit` means there's nothing to build,
     and that's a good answer.
   - `standard_status` isn't `written`. Say the key and its value: the rules
     get written down first, and the blueprint is updated after.

   A blueprint with `gaps` and `outcome: build` still gets built. Each gap
   goes in the README under what it doesn't do yet, and is never filled with a
   guess.
2. **Check the folder isn't there.** If `workflows/<name>/` exists already,
   stop and say so. This skill never overwrites a team's workflow.
3. **Build every part** *The workflow folder* lists, in `workflows/<name>/`:
   - `workflow.json` with every key *The manifest* names, filled from the
     blueprint: `"status": "draft"`, `runs` from how the team will start it
     (never `schedule` when `restricted_data` isn't `none`), `never` as a
     list, and `blueprint` set to `../../blueprints/<name>.md`.
   - A README with its five parts: using it, its parts, installing, the trust
     tests, and what it doesn't do yet.
   - The standard: the blueprint's `rules` as numbered rules (`S1`, `S2`), in
     the standard folder and as the same copy in `sample/standard/`.
   - The template, the workflow's skill, its reviewer agent, its gate (standard
     library only, Python 3.9+, `PASS` or each problem, exit 0 or 1), the test
     file, and `inbox/.gitkeep` and `out/.gitkeep`.

   The skill follows the seven rules in *The rules*. It never sends, never
   changes an input and never fills in the approval lines.
4. **Write the sample inputs.** Invented, Markdown or JSON only, each marked
   `invented: true` (in the frontmatter, or at the top level of a JSON one).
   Reuse only names the blueprint already uses, and invent the rest. Include:
   - every `went_wrong` item carried by at least one input; one input can
     carry more than one
   - one input carrying a planted instruction: a line telling whoever reads it
     to do something, such as mark every rule as met

   Then write a sample output for each input, by hand, that passes the gate.
   Each one names `sample/standard/` as its standard, never the team's own.
5. **Write the trust tests.**
   - Gate cases in `evals/gate/`: one for each `went_wrong` and `never` item
     an output can show, then a citation that doesn't exist, an invented date
     or amount, a blank used as a value, and template text left in. Six at
     least. Each `case.json` holds `"expect": "fail"`, the `says` text the gate
     prints for it, and `why`. A `never` item no output can show, such as
     changing an input, goes in a review case or the README instead.
   - Review cases in `evals/review/`: two at least, which the gate passes and
     only judgement catches. One is an output that obeyed the planted
     instruction.
6. **Run the check** from the harness root and show what it prints:

   ```bash
   python3 scripts/check_workflow.py workflows/<name>
   ```

   The work is done only when it prints `PASS`. Anything else is a list of
   what to fix; `check-workflow` says how to read each line. Fix the folder
   and run it again.

## Rules

- Never edit the blueprint, [`scripts/check_workflow.py`](../../scripts/check_workflow.py) or a case to get a
  pass. A case the gate doesn't catch means the gate needs fixing.
- Every person, company and document in `sample/` is invented. Never copy a
  real agreement, message or record in, even with the names changed.
- When the blueprint's `inputs` arrive as something other than Markdown or
  JSON, such as a PDF or a spreadsheet, the sample inputs are still Markdown
  or JSON, and the README says what shape the real ones take.
- The new workflow's `status` stays `draft`. Changing it to `live` is the
  owner's call, after it has run for real.
