# Example: a project's control register

A starting register for a project the loop works on. [`controls.json`](controls.json) here
is an empty list, so it passes the check as it stands and holds the project to
nothing until you add entries. [`docs/controls.md`](../../docs/controls.md) explains the fields, the
statuses and both commands.

```
examples/controls/
  controls.json   an empty register: []
```

## Start a project's register

1. Copy [`controls.json`](controls.json) into the root of the project's own repo, beside its
   `.git`, and commit it there. The loop reads it from the checkout, so a copy
   anywhere else, this factory's root included, holds the project to nothing.
2. Choose the `framework` value from `company/COMPANY.md`: the framework the
   company is held to, such as SOC 2, written the same way in every entry. If
   that file names none, ask the person whether one applies before you assume
   there isn't, as [`steering/compliance.md`](../../steering/compliance.md) says. Don't quote from that
   file into the register.
3. Add an entry for each control, with every field
   [`docs/controls.md`](../../docs/controls.md) asks for and `evidence` pointing at the files in the
   project that carry it. Paths are relative to the project's root.
4. From the harness root, check it:

```bash
python3 scripts/controls.py check --file projects/<name>/controls.json
```

## What the loop then does

In every build round, after `test_command`, the loop runs
[`scripts/controls.py`](../../scripts/controls.py) `check` on the register at the checkout's root. The script is
the factory's own copy, never one the project's checkout holds. Its output goes after the tests' output, where the reviewer,
the round's saved `test-output.txt` and the next build round all read it. A
failing check fails the round, as a failing test does, even when the tests
passed.

The loop also runs `touched` against the branch's base and puts what it prints
on a `Controls touched:` line after the diff in the round's review prompt, and
in the prompt of a pull request review when the pull request's checkout has a
register. A checkout without a register gets neither: its rounds and
reviews run as they did before.
