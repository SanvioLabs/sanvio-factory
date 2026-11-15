# Writing an eval suite that tells factories apart

A suite earns its keep when two factories, or one factory before and after a
change, get different scores on it for a reason you can name. This page is
how to build one like that. [`eval-walkthrough.md`](eval-walkthrough.md) step 6 has the
short version, and [`factory-evals.md`](factory-evals.md) has the format.

```bash
python3 scripts/eval_factory.py new-suite ../my-suites/billing
```

That makes the folders and files to fill in, outside the factory.

## Start from work you've really done

Pick something your team shipped in the last month or two: a bug that took
longer than it should have, a small feature, a change that touched more files
than it looked like it would. Real work has the shape agents get wrong: the
cause isn't where the symptom is, a rule lives in a doc nobody links to, a
caller sits outside the file you're in.

Then rewrite it. Change every name, number and record, so the suite holds
made-up data only. Scoring runs code an agent wrote on your machine, and the
suite will be read by more people than the original ticket was.

Three issues is a good size. One issue tests one thing. Three, where later
ones build on earlier ones, also tests whether the factory leaves the code in
a state it can keep working in.

## Write the issues the way people do

Describe what a user saw, not the fix: "a tool brought back on its due date is
charged a late fee", not "`days_late` is off by one". Leave out what a careful
engineer would go and find for themselves. If a rule is in the repo's docs, the
issue doesn't need to repeat it, and whether the factory finds it is part of
what you're measuring.

Don't plant tricks the issue can't be fairly expected to cover. Every check in
the key should be something a good engineer, given the issue and the repo,
would get right.

## Checks: behaviour, not wording

`key/score` runs against the finished repo and prints which checks passed.

- **Call the code, don't read it.** Import the module and check what it
  returns. A check that greps for a function name passes a stub and fails a
  correct answer that names things differently.
- **Cover the edges the issue implies.** The example's borrowing limit has five
  checks: at the limit, under it, returned tools, other members' tools, and
  the second plan. A factory that gets the happy path and misses one edge
  shows up as one failed check, by name.
- **Name checks by the behaviour,** so a miss reads as a sentence: `failed: a
  fee stops at the replacement cost`.
- **Tag each check with its issue** (`"issue": 2`), so a report groups misses
  under the issue that caused them.
- **A crash is a failed check,** not a broken scorer. Wrap each check, as
  [`examples/eval-suite-tool-library/key/score`](../examples/eval-suite-tool-library/key/score) does.

## Traps: the wrong moves CI can't see

A trap catches work that passes CI and is still wrong. Good ones come from
mistakes you've watched agents make:

- editing, skipping or deleting an existing test until it passes;
- changing a function's signature that something outside the repo calls;
- touching files the issue had no reason to touch, such as data or generated
  files;
- leaving out a step the repo's contributing guide asks for.

Each trap should be one specific move, checked directly. Two or three per
suite is plenty.

## Wrong answers prove the checks work

Each folder in `key/wrong/` is a complete answer with one mistake in it. Write
one for every check you'd be embarrassed to see pass by accident: stopping
after the first issue, the signature change, the edge case that's easy to
miss, the weakened test. `validate` then proves each one fails:

```bash
python3 scripts/eval_factory.py validate ../my-suites/billing
```

It passes only when the seed fails, every wrong answer fails and the reference
passes everything. A wrong answer that passes means a check is missing.

## Check it isn't too easy

A suite that every factory aces can't tell them apart. Run it once through the
plain one-session adapter, [`examples/eval-adapters/one-session.py`](../examples/eval-adapters/one-session.py),
on the cheapest model you use, or a local one. If that scores full marks, the
suite is measuring the model, not your factory: make the issues more like the
real work, with the cause further from the symptom, or add the edge cases and
traps you've seen factories miss.

The public tool-library example is the case in point. A plain session on a
local model scored 12/12 and 2/2 on it. It shows the format and nothing else.

## Keep it private, and keep it fresh

- **Keep the suite in a private repo,** outside your factory and anywhere its
  agents can read. `run` refuses a key inside the factory or the clone folder,
  and checks each run repo for the key's files, but it can't see what an agent
  read.
- **Never point an agent at the key,** to write it or to debug it. Write the
  key yourself.
- **Retire a suite that leaks.** If a run repo's history ever holds a key
  file, the report says `Key leak`. That suite has been seen, and its scores
  from then on don't count.
- **Add a suite, don't edit one in use.** Changing a suite's checks makes its
  old runs incomparable with new ones. `compare` marks checks as `New:` or
  `Gone:` when that happens.
