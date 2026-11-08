---
name: draft-proposal
description: Draft a client proposal from the template and price it from the rate card. Use when asked to write, draft or price a proposal.
license: MIT. From Sanvio Factory by Sanvio Labs, https://github.com/SanvioLabs/sanvio-factory
---

# Draft a proposal

## Inputs

You need all five before you write anything. Ask for whatever is missing, in one
message:

1. Client name
2. The problem, in the client's words
3. What's in scope
4. What's out of scope
5. Hours per role, using only the roles in [`examples/proposal/data/rates.json`](../../data/rates.json)

## Steps

First read [`examples/proposal/README.md`](../../README.md): its rules apply to every step here.
Paths are from the harness root.

1. Copy [`examples/proposal/templates/proposal.md`](../../templates/proposal.md) to
   `examples/proposal/proposals/<client-name-in-kebab-case>.md`.
2. Fill every section from the inputs. Write it the way you'd say it to the
   client across a table: short, specific, no filler.
3. For each fee row, take the rate from [`examples/proposal/data/rates.json`](../../data/rates.json) and compute
   amount = hours x rate. Write money as `$1,750`.
4. Add the amounts for the total. If it's under `minimum_fee`, stop and tell
   the human rather than padding the hours.
5. Run `python3 examples/proposal/gates/proposal_gate.py examples/proposal/proposals/<file>.md`.
6. Fix what it names and run it again until it passes.
7. Stamp it: `python3 examples/proposal/gates/stamp.py gate examples/proposal/proposals/<file>.md`.
   That runs the gate once more and records that it passed on this text.

## Output

The path of the proposal and the gate's output, pasted as it printed. Nothing
else. Then hand it to the `reviewer` agent with [`examples/proposal/agents/proposal-reviewer.md`](../../agents/proposal-reviewer.md)
as its brief. Don't stamp it `reviewed` yourself: that stamp is the person's,
once they've read the findings.
