# Supplier terms

A worked workflow, built by following [`skills/build-workflow/`](../../../skills/build-workflow/) against the
blueprint in [`examples/blueprints/supplier-terms.md`](../../blueprints/supplier-terms.md). It checks a supplier's
agreement and price list against Juniper Bakery's purchasing rules, and drafts
a one-page terms review for the owner to approve. Juniper Bakery, its
suppliers, its people and every document here are invented.

Its status is `draft`: nobody owns it for real, and it has never run on a real
agreement.

## Using it

Put the agreement (as Markdown) and its price list (as JSON) in [`inbox/`](inbox/),
and ask for the supplier terms in the inbox to be checked. The skill drafts a
review into [`out/`](out/), one line per rule with the clause that shows it, runs the
gate on it, has the reviewer read it, and stops at the blank approval lines.
Tom Reyes approves any agreement above $5,000 a year or longer than twelve
months, and Maya Okafor tells the supplier. Nothing is signed, sent or changed.

It runs in a session or from the loop, as [`workflow.json`](workflow.json) lists.

## Its parts

| Part | What it does |
|---|---|
| [`workflow.json`](workflow.json) | Who owns it, how it runs, who approves, and where each part lives |
| [`standard/purchasing-rules.md`](standard/purchasing-rules.md) | Seven sample rules, S1 to S7. Replace them with your own |
| [`templates/terms-review.md`](templates/terms-review.md) | The one page the approver reads |
| [`skills/check-supplier-terms/SKILL.md`](skills/check-supplier-terms/SKILL.md) | How the agent drafts the review |
| [`gates/supplier_terms_gate.py`](gates/supplier_terms_gate.py) | Refuses a review that doesn't trace to its inputs |
| [`agents/reviewer.md`](agents/reviewer.md) | The second read, for what a script can't decide |
| [`sample/`](sample/) | Two invented agreements, their price lists, and a finished review of each |
| [`sample/standard/`](sample/standard/) | The copy of the sample rules that every sample output and eval names |

The gate refuses a review when:

- a source or the standard is missing, it cites a rule the standard doesn't
  have, or a rule has no line
- it cites a clause or a price list item that isn't there
- a clause that mentions renewal or a minimum order isn't cited, wherever it
  sits in the agreement
- the price list and the agreement differ on an item, and no Not met line
  names it
- a date or a $ amount appears in no input and not in the standard
- a blank in the agreement isn't quoted under Could not confirm
- template text is left in, it writes to the supplier, or the approval lines
  are missing or filled in

## Installing

Copy the folder and its blueprint into your factory, from the harness root:

```bash
cp -R examples/workflows/supplier-terms workflows/
mkdir -p blueprints && cp examples/blueprints/supplier-terms.md blueprints/
```

Then replace the rules in [`standard/purchasing-rules.md`](standard/purchasing-rules.md) with your own, and
the owner, approver and receiver in [`workflow.json`](workflow.json) with your people. Leave
[`sample/standard/`](sample/standard/) as it is: the tests read it, so rewriting your rules
never breaks them. The words the gate searches every agreement for are in
`WATCH` at the top of the gate. Check the copy with
`python3 scripts/check_workflow.py workflows/supplier-terms`.

## The trust tests

[`evals/gate/`](evals/gate/) holds eleven reviews the gate must refuse. The first five come
from the blueprint: the renewal clause missed, a delivery minimum not flagged,
a price list mismatch not flagged, an approval line filled in, and a message
to the supplier. Then a clause that doesn't exist, an invented date, an
invented amount, a blank used as a value, template text left in, and a rule
left out.

[`evals/review/`](evals/review/) holds three reviews the gate passes on purpose, where only
the reviewer can catch the mistake: one obeys the instruction planted in the
Hollow Oak agreement, one says an agreement clause was corrected, and one
marks a 60 kg minimum as meeting a 40 kg rule.

[`tests/test_supplier_terms_gate.py`](tests/test_supplier_terms_gate.py) runs all of them, both sample outputs and
the template, and checks every sample input says it's invented. From the
harness root, `python3 scripts/check_workflow.py examples/workflows/supplier-terms`
runs the whole check.

## What it doesn't do yet

- Real agreements arrive as PDFs and price lists as spreadsheets. The sample
  inputs are Markdown and JSON, because the workflow contract allows only
  those, and turning a PDF into Markdown isn't part of this workflow.
- The gate can't tell whether an input was changed. The skill never changes
  one, and the reviewer flags a draft that says one was.
- It doesn't work out whether an agreement is above $5,000 a year or longer
  than twelve months, so every review stops at the approval lines.
- It has never run for real. Before calling it done, run it once on a copy
  with [`sample/outputs/`](sample/outputs/) and [`evals/`](evals/) removed, so the agent can't read the
  answers.
