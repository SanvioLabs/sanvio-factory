---
name: blueprint-workflow
description: Interview the person who does a piece of work, one question at a time from the last real time it happened, and write what they say as a blueprint in blueprints/<name>.md, ending in build it, write the rules down first, or not a fit. Never guesses an answer. Use when asked to understand, map or blueprint a piece of work, to interview someone about a process, or before building a workflow for it.
license: MIT. From Sanvio Factory by Sanvio Labs, https://github.com/SanvioLabs/sanvio-factory
---

# Blueprint a workflow

[`docs/building-workflows.md`](../../docs/building-workflows.md) is the reference: *Understanding the workflow*
says what to ask and in what order, and *The blueprint* says what to write.
Read both before the first question. This skill is step 1 of building a
workflow; `build-workflow` comes after it, and only when the outcome is
`build`.

## Who you ask

The person who does the work, not the person who manages it. If the person in
the session doesn't do it, ask who does, and ask them. People describe the
process they wish they ran. The last real time it happened is the process they
run, so every question starts from that, never from the general case.

## Steps

1. **Name it.** Ask for a short name for the work. The blueprint's `name` is
   that, in kebab-case, and the file is `blueprints/<name>.md`. If that file
   exists already, show it and ask whether this interview updates it.
2. **Ask one question at a time**, in the order *Understanding the workflow*
   gives, and wait for each answer before the next. Don't stack questions or
   offer a guess for them to confirm.
   1. What starts it: what arrives, from whom, where, and how often.
   2. What data it touches. Ask this before the detail (step 3 below).
   3. The last real time: walk through it step by step.
   4. The time it went sideways: what was different, what they did, how they
      noticed.
   5. The rules: what it's checked against, and whether that's written down,
      and where.
   6. What comes out, who reads it, and what done looks like to them.
   7. Who signs off, above what amount or risk, and who gets the result.
   8. What goes wrong: mistakes that happened or nearly did.
   9. What must never happen.
   10. Today's numbers: how often, how many, how long it takes.
   11. Where it lives: the systems it touches, and any tool they already pay
       for that claims to do it.

   When they answer in general terms ("usually", "we always"), ask about the
   last time instead. Write down their words, not a summary of them.
3. **Check the data before the detail.** After question 2, compare the answer
   with *Data that needs an agreement first*. If the work touches any of health information, children's data, payment card data, financial customer information, tax return information, government IDs, biometric data, precise location, and employees' personal data,
   say so now: the workflow is built and tested on invented data only until
   the team's agreements cover it. Ask the rest of the questions about the
   work, not about any real record, and don't ask them to paste or attach one.
   Put the categories in `restricted_data`, or `none`.
4. **Write the blueprint** to `blueprints/<name>.md`. Make the `blueprints/`
   folder at the harness root if it isn't there.
   - The frontmatter is every one of the 22 keys in *The blueprint*, in that
     order, as plain `key: value` lines between `---` lines. A list goes on one
     line, separated by commas.
   - A key nobody could answer stays empty and goes in `gaps`. Never fill it
     with a guess, a likely value or a placeholder. `gaps` is empty when every
     key has an answer.
   - `standard_status` is `written` when the rules from question 5 are written
     down somewhere a new person could find them, and `not-written` when they
     aren't. It's never a gap.
   - Below the frontmatter, write the walkthrough from question 3 and the
     exception from question 4 in the person's own words, quoted, not tidied.
   - [`examples/blueprints/supplier-terms.md`](../../examples/blueprints/supplier-terms.md) is a finished one. Match its shape.
5. **Set the outcome** in `outcome`, and say what comes next:

   | `outcome` | When | Next |
   |---|---|---|
   | `build` | The work repeats, the rules are written down, and someone owns it | `build-workflow`, from this blueprint |
   | `write-standard` | The work is real, but the rules live in someone's head | Writing the rules down is the first piece of work. Name who could write them, and stop there |
   | `no-fit` | It doesn't repeat, or it's judgement from start to finish | Nothing. The blueprint says so, and that's a good answer |

   A rule that lives in someone's head is a finding, not a failure. Say so
   plainly, and don't push toward `build` to have something to build.
6. **Run the check** from the harness root and show its output as it came:

   ```bash
   python3 scripts/check_blueprint.py blueprints/<name>.md
   ```

   [`scripts/check_blueprint.py`](../../scripts/check_blueprint.py) prints `PASS` and exits 0, or one problem per
   line and exits 1. Fix what each line names, from the person's answers, and
   run it again. The blueprint is done only when it printed `PASS`.

## Reading what it prints

Each line starts with the key it's about.

| The line | The fix |
|---|---|
| `<key>: missing` | Add the key. Every one of the 22 is present, even if it's empty |
| `<key>: empty and not named in gaps` | Ask the question again, or add the key to `gaps` if nobody could answer it |
| `<key>: named in gaps but has a value` | Take it out of `gaps`, or empty the value if it was a guess |
| `gaps: <item> isn't a blueprint key` | Correct the spelling, so the real gap isn't hidden |
| `name: ... doesn't match the file name ...` | Make `name` and the file name the same |
| `standard_status: ...` or `outcome: ...` | Set one of the listed values. Neither is ever a gap |
| `no frontmatter: ...` | Start the file with `---` and close the frontmatter with `---` |

## Rules

- One question at a time, about the last real time, in the person's words.
- Never guess an answer. An unanswered key is empty and named in `gaps`.
- Never ask for, read or paste a real record that touches restricted data.
- Say the blueprint is done only after the check printed `PASS`.
- This skill writes only `blueprints/<name>.md`. It never sends anything, and
  never builds the workflow itself.
