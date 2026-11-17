# Quote check (test fixture)

A small, complete workflow that meets the workflow contract in the factory's
docs/building-workflows.md. The tests for scripts/check_workflow.py copy it,
break one thing at a time and check the script says so. Everything in it is
invented.

## Using it

Drop a supplier quote in the inbox and ask for it to be checked. A review is
drafted into out/, checked by the gate and read by the reviewer, and waits for
the finance lead.

## Its parts

The standard holds three numbered rules. The template is the one review the
approver reads. The gate checks the review traces to its sources: they exist,
every cited rule is in the standard, every date is in an input, no template
text is left in, and it ends with approval lines.

## Installing

Copy the folder into workflows/ and replace the standard with your own rules.

## The trust tests

Six gate cases the gate refuses, two review cases it passes on purpose (one
obeys the instruction planted in the sample quote), and a test file that runs
them all, the sample output and the template.

## What it doesn't do yet

It doesn't check amounts against the inputs.
