# The control register

[`controls.json`](../controls.json) lists the security controls this factory helps a company meet, what
it does toward each one, and the files that do it. It's the factory's own
engineering mapping, written in our own words. It isn't a certification, an
assessment or an audit result, and it doesn't say that any company using the
factory meets a control.

Each entry names its evidence: the files and folders that carry the control.
Rename or delete one of them and [`scripts/controls.py`](../scripts/controls.py) `check` fails. The test
suite runs that check on the shipped register, so CI fails too, and the
register can't drift from the code without someone noticing.

## The fields

Each entry is one JSON object.

| Field | Holds |
|---|---|
| `framework` | The framework the control comes from, written the same way in every entry. Today the register uses `NIST SP 800-53 Rev. 5` and `OWASP Top 10 for LLM Applications`. `check` doesn't validate this name, so copy it from an existing entry |
| `id` | The control's identifier in its framework, such as `AC-5`. For OWASP it's a slug of the risk's name, such as `prompt-injection`, because the numbers differ between editions of the list. An `id` appears once per framework; two frameworks can share one |
| `name` | The control's name, as the framework gives it |
| `status` | One of the six statuses below |
| `summary` | What the factory does toward the control, in a sentence or two |
| `setup` | What a customer does so the control is met. Required when `status` is `configured` |
| `evidence` | A non-empty list of paths, relative to the register's own folder. A folder must end in `/`, a path ending in `/` must be a folder, and no path may resolve outside the register's folder |

## The statuses

| Status | Means |
|---|---|
| `core` | Met as shipped |
| `configured` | Met once a customer does what `setup` says |
| `gap-customer` | Left to the customer's own process |
| `gap-limit` | A limit by design: the factory can reduce the risk but can't close it |
| `enhancement` | Not built yet |
| `na` | Doesn't apply to the factory |

## The commands

```bash
python3 scripts/controls.py check
python3 scripts/controls.py touched origin/main
```

`check` reads the register and prints, for the shipped one:

```text
controls.json: 5 controls, all evidence present
```

It exits 1 and prints one line per problem when a field is missing, a
`status` isn't one of the six, a `configured` entry has no `setup`, or an
`id` repeats within one framework. It does the same for an evidence path that
is missing, names a folder without a trailing `/`, ends in `/` but isn't a
folder, or resolves outside the register's folder. Each line names the entry
by its framework and `id`, or by its place in the file, counted from 1, when
either is missing.

`touched <base>` runs `git diff --name-only --no-renames <base>...HEAD` and
prints the controls whose evidence the branch changed, one `<framework> <id>`
per line in register order, or `none`. A changed file matches an evidence path
that names the same file, or a folder path it sits under. A rename counts as
both names, so the controls of the old path and the new one both show. With no
register it prints `no controls.json` and exits 0. If `git diff` fails, for a
base that doesn't exist, it says why and exits 1.

The review-pr skill runs `touched` in its step 3 and reports what it printed
on a `Controls touched:` line, so a reviewer sees which controls a pull request
moves. See [`skills/review-pr/SKILL.md`](../skills/review-pr/SKILL.md).

Without `--file`, both commands find the git root of the folder you run them
from and read its own `controls.json` there, or the one in that folder when it
isn't in a git repo, so run from the factory they read [`controls.json`](../controls.json). Both take `--file <path>` to
read another register, and `touched` runs `git diff` in that register's
folder. For a project cloned under `projects/<name>/`, run from the harness
root:

```bash
python3 scripts/controls.py touched origin/<base> --file projects/<name>/controls.json
```

## The Controls line and the monthly list

A [`CHANGELOG.md`](../CHANGELOG.md) entry for a change that moves a control carries one more line,
after its description and before `Files:`:

```text
**Controls:** AC-5, prompt-injection
```

It holds the `id` of each control whose evidence the change edits, adds or
removes, or whose status it changes, separated by `, `. Write the bare `id`,
without the framework. The CHANGELOG's own header says the same.

The changelog test, [`tests/test_changelog.py`](../tests/test_changelog.py), fails any id on a
`**Controls:**` line that isn't an `id` in [`controls.json`](../controls.json). The review-pr skill reports a
finding when its `Controls touched:` line isn't `none` and the change's new
entry has no `**Controls:**` line.

`python3 scripts/usage_report.py --review`, the monthly log review, ends with a
`## Controls` section. It prints what `check` prints for the register, then a
blank line, then each entry in the review's 30 days that has a `**Controls:**`
line, as `<date>: <name>: <ids>`, or `None.` when there are none. With no
[`controls.json`](../controls.json) it prints `No controls.json, so no controls to list.` instead,
and the review still counts as done.

## Adding an entry

Add an object to the array with every field the table asks for, point its
`evidence` at the files that actually do the work, and run `check`. Write the
`summary` in your own words. Don't paste a framework's text or a reviewer's
report into it.
