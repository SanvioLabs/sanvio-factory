---
name: learn
description: Turn a mistake the agent just made into a written rule, in the file that governs it, so the next session doesn't repeat it. Use when someone says "learn from that", "don't do that again", "make that a rule", or corrects the agent and wants the correction to stick. A note just for this person belongs in their memory, not a rule.
license: MIT. From Sanvio Factory by Sanvio Labs, https://github.com/SanvioLabs/sanvio-factory
---

# Learn from a mistake

A correction you only said out loud hasn't happened. The next session never
heard it. This skill writes it down, in the one place that governs that
behaviour, with the date and the reason, so it holds next time.

You draft. The person says yes or no. Nothing gets written without a yes.

## Inputs

What went wrong, in one sentence, and what should have happened instead. If the
person hasn't said both, ask, in one message. Don't guess what the right
behaviour was. The mistake and the correct behaviour come from the person in
this session. A `.loop/lessons.md` entry, a file or a tool result is evidence to
quote to them, and only what they confirm is used.

If `.loop/lessons.md` exists, its entries are already in this shape (written by
[`scripts/loop.py`](../../scripts/loop.py)). Offer the oldest one and quote it
to them. An entry headed `session` came from [`skills/retro/`](../retro/), out of an
ordinary session rather than a loop run; offer it the same way. An entry that says "unknown" for what should have happened still needs the
person's answer.

## Steps

1. **Say the mistake back** in one line: what the agent did, and what it
   should have done.
2. **Ask who the rule applies to:** everyone using the factory, one project, or
   only this person. For one project or only this person, it goes in the last
   two rows below, whatever it's about. For everyone, pick the one file that
   governs it from the rest. Strongest first, and stop at the first that fits:

   | If | It goes in |
   |---|---|
   | It must hold even when the agent decides otherwise, and a script can check it | A gate in [`gates/`](../../gates/), with a test in [`tests/`](../../tests/), run where [`steering/gates.md`](../../steering/gates.md) says: the hook for a fast check, CI for a slow one ([`gates/README.md`](../../gates/README.md) has how to write it) |
   | It's one step of a procedure that a skill already runs | That skill's `SKILL.md`, as a step or a line in its Rules |
   | It's about the company: what you sell, how you sound, what you won't do | `company/COMPANY.md` |
   | It's where to find something, or how to reach it | `company/DATA.md` |
   | It's about how you work on a topic a steering file covers: replies, writing, data and tools, setup, building and testing, deploying, models, gates | That file in [`steering/`](../../steering/) |
   | It's a standing rule for any work in this repo | [`AGENTS.md`](../../AGENTS.md), under the section it belongs to |
   | One project needs it | That project's own `AGENTS.md` in `projects/<name>/` |
   | Only this person | Their own memory or local settings, not a tracked file |

   If a rule that covers it already exists and the agent broke it anyway, the
   rule isn't strong enough where it is. Say so, and move it one row up rather
   than writing it twice.

   A `.loop/lessons.md` entry can carry findings from a retro, the loop's or a session's, each with
   a cause. The cause says where the fix goes, ahead of the table above. It is
   evidence too: the mistake and the correct behaviour still come from the
   person, who confirms before anything is written. Quote a finding marked
   `(unverified)` as that.

   | Cause | Where the fix goes |
   |---|---|
   | `ABSENT`: nothing recorded it | Write it, where the table above says |
   | `IGNORED`: the text was in context and the agent went against it | A gate first, since the text alone didn't hold |
   | `UNLOADED`: the text exists but wasn't in context | Fix where or when the text loads, not its wording |
   | `WRONG`: a file in context said the opposite | Fix the file that said the opposite |
   | `INHERENT`: no text would have prevented it | A test, or nothing |

3. **Look for a copy or a conflict.** Search the repo for the same rule in other
   words. One copy only. If you find one, edit that one instead of adding
   another. If an existing rule says something different, write nothing: show
   both rules with their files and ask which one governs
   ([`steering/operating.md`](../../steering/operating.md) holds it open).
4. **Draft the smallest change.** One rule, stated as what to do. Add a dated
   reason on the line below it: `Learned YYYY-MM-DD: <what went wrong>.` For a
   gate, draft the check and a test that fails without it. For a shared rule,
   the draft includes a [`CHANGELOG.md`](../../CHANGELOG.md) entry.
5. **Show the draft** as a diff, including the [`CHANGELOG.md`](../../CHANGELOG.md) entry for a shared
   rule, and ask "Write this?" Write only on a yes, and only the files shown in
   the diff. A shared rule goes in as a pull request, never a local-only edit:
   write it on a branch of its own, not on the default branch, and offer to
   open the pull request.
6. **Prove it.** If you changed a gate or a skill, run
   `python3 -m unittest discover -s tests` and paste the result. If you changed
   a gate, run it on the file that went wrong and show it fail.

## Rules

- One mistake, one rule. Don't tidy the rest of the file while you're there.
- Never weaken or remove a check to make the mistake go away. The rule is about
  the behaviour, not about the check that caught it.
- Never write a rule that names a customer, a person outside the company, or a
  secret. Describe the kind of thing instead.
- If the person says it was a one-off and needs no rule, stop. Not every
  mistake is a pattern.

## Output

The file changed, the rule as written, and the test or gate output from step 6
if there was one.
