# A three-issue eval suite

A worked example for [`scripts/eval_factory.py`](../../scripts/eval_factory.py), big enough to see a
factory take issues in order, each building on the last. [`examples/eval-suite/`](../eval-suite/) shows
the format in one issue. This one shows what a suite looks like when it tests more than one thing.
[`docs/eval-walkthrough.md`](../../docs/eval-walkthrough.md) runs it step by step.

Like the smaller one, it's public, so an agent could read its key. It shows you how a suite works and how
your factory runs one. It can't tell you how good your factory is: write a private suite for that.

## What's in it

The seed is lending code for a made-up community tool library: members borrow tools for a week and pay
50 cents a day when one comes back late. Every name and number is invented.

| Issue | Asks for | What it tests |
|---|---|---|
| [`01-due-date-fee.md`](issues/01-due-date-fee.md) | A bug, reported as what a member saw | Finding the cause from a symptom |
| [`02-fee-rules.md`](issues/02-fee-rules.md) | Two new rules for late fees | Using data the code already has, without breaking a caller outside the repo |
| [`03-borrowing-limit.md`](issues/03-borrowing-limit.md) | A limit on tools out at once | Getting the edges right: returned tools, other members' tools, two plans |

[`key/score`](key/score) runs 12 hidden tests and checks two traps:

| Trap | The wrong move it catches |
|---|---|
| The kiosk's call still works | Changing `late_fee`'s signature. A note at the top of `fees.py` says a kiosk outside the repo calls it by keyword |
| Seed tests left alone | Deleting, skipping or rewriting a test that was already there. Adding tests beside them is fine |

Four known wrong answers sit in [`key/wrong/`](key/wrong/), one per kind of mistake: stopping after the first
issue, adding a required argument to `late_fee`, counting tools already returned, and dropping a seed test.

## Check it, then run it

Free, and makes no repo:

    python3 scripts/eval_factory.py validate examples/eval-suite-tool-library

A run with the plain one-session adapter, to get a baseline. It makes a private repo in the owner you name
and spends model tokens:

    python3 scripts/eval_factory.py run examples/eval-suite-tool-library --owner <your-org> \
      --merge-in-run-repo --start "python3 $PWD/examples/eval-adapters/one-session.py {issue} {clone} {repo}"

The walkthrough has the same run on a local model for no token spend, and how to point it at your own
factory instead.
