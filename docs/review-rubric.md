# The review rubric

Every review the factory posts ends with a grade out of 10, such as
`Grade 8/10: ready with nits, checks passing.` The reviewer doesn't pick the
number. It comes from the review's verdict and the reviewed commit's check
runs, scored by [`review-rubric.json`](../review-rubric.json) at the factory's root. This page says
what the grade is for, the two shapes the rubric can take, and how to try one
before anything acts on it.

## What the grade is for

The verdict says what one reader thought of the diff. The grade puts that
verdict together with what the checks found, as one number a person or a
script can sort and act on. With `auto_merge` on in `loop.json`, `review`
merges a pull request it graded at least `min_grade`, once every check on that
commit has passed. Off, the grade is information for the person who merges.

The loop's `review`, the CI review ([`examples/ci/README.md`](../examples/ci/README.md)) and a review a
person runs with [`skills/review-pr/`](../skills/review-pr/) all grade through the same code in
[`scripts/loop.py`](../scripts/loop.py), from the same file.

## Two shapes: five keys, or a ladder

The rubric the factory ships gives each verdict a number, and two more for a
failed check and a verdict it can't read:

```json
{"ready": 10, "ready with nits": 8, "changes needed": 3, "failing": 0, "unreadable": 0}
```

Any check run that finished without passing (success, neutral and skipped
pass) gives `failing`, whichever check it was. That works until one check
matters more than the rest, or a grade should need a check to have run at all.

A **ladder** says, for each grade, what it takes. This ladder gives the same
numbers as the five keys above:

```json
{"levels": {
  "10": {"verdict": ["ready"], "checks": ["*"]},
  "8": {"verdict": ["ready with nits"], "checks": ["*"]},
  "3": {"verdict": ["changes needed"], "checks": ["*"]},
  "0": {}
}}
```

Its reasons read differently: `ready, checks (*) passed` where the five keys
say `ready, checks passing`.

![A ladder with rungs 10, 8, 3 and 0, walked from the top for a ready review whose tests passed, whose lint failed and whose security-scan never ran: rung 10 needs ready plus security-scan and tests, misses because security-scan never ran, and the walk steps down; rung 8 needs ready or ready with nits plus tests, and is met, so the grade is 8 and rungs 3 and 0 aren't reached; lint fails, but no rung names it, so the grade doesn't move, though auto_merge still waits for every check; beside it, a rung is met when the verdict is one it lists and every check it names passed, missed when the verdict isn't listed or a named check failed or never ran, and unsettled while a named check still runs or GitHub can't say, which makes a rung met below it grade pending; no rung met grades 0; the trailer reads Grade 8/10: ready, checks (tests) passed; 10 needs a check named security-scan, and none ran.](review-rubric.svg)

### How a ladder grades

The file is an object with one key, `levels`. Each key under it is a grade,
`"0"` to `"10"`, and `"0"` has to be there. Each rung can ask for two things,
both lists:

- `verdict`: the verdicts it takes, from `ready`, `ready with nits` and
  `changes needed`. Leave it out and any verdict will do, an unreadable one
  included.
- `checks`: the names of check runs on the reviewed commit that have to have
  passed. `"*"` means every check run on the commit. Leave it out and the rung
  needs no checks.

The grade walks the rungs from the highest down. Each rung is one of three:

| A rung is | When | Then |
|---|---|---|
| met | the verdict is one it lists, and every check it names passed | its grade is the grade |
| missed | the verdict isn't one it lists, or a check it names failed or never ran | the walk steps down |
| unsettled | a check it names is still running, or GitHub can't list the runs | the walk steps down, and a rung met below it grades pending |

The first rung met gives the grade. While a rung above it is unsettled, the
grade is `pending`, and the loop's next poll grades it again once the checks
finish, as it does for the five keys. When no rung is met, not even `"0"`, the
grade is 0.

A few more rules:

- A name several check runs share passes only when every one of them passed.
- `"*"` on a commit with no check runs counts as met, as `no checks ran` does
  for the five keys.
- A check run that no rung names never moves the grade. It still stops
  `auto_merge`, which waits for every check on the commit to pass.
- A verdict the grade can't read takes only a rung with no `verdict`.

The reason names the rung met and the nearest rung above it that was missed:
`ready, checks (tests) passed; 10 needs a check named security-scan, and none
ran.` A rung with no checks says `no checks needed`.

A ladder that breaks any of those rules, such as a key other than `levels`, a
grade like `"07"` or `"11"`, a rung key other than `verdict` and `checks`, an
empty list, a verdict that isn't one of the three, or a check name that's
blank, grades every review 0, and the reason names the file and the fault.

## Three worked rubrics

### 10 needs the security scan

Your repo has a `security-scan` job, and you want a 10 to mean it ran and
passed:

```json
{"levels": {
  "10": {"verdict": ["ready"], "checks": ["security-scan", "tests"]},
  "8": {"verdict": ["ready", "ready with nits"], "checks": ["tests"]},
  "3": {"verdict": ["changes needed"]},
  "0": {}
}}
```

A ready review on a commit where `security-scan` didn't run gets
`Grade 8/10: ready, checks (tests) passed; 10 needs a check named
security-scan, and none ran.` A failed `tests` drops a ready review to 0,
since only rung 3 asks for no checks and it takes only `changes needed`.

### A stricter ladder for one project

A project under [`projects/`](../projects/) takes its rubric from the factory's
`loop.json`, under its `projects` entry, as a path from the factory's root:

```json
{"projects": {"payments": {"review_rubric": "rubrics/payments.json"}}}
```

`rubrics/payments.json` can ask more of that project alone:

```json
{"levels": {
  "10": {"verdict": ["ready"], "checks": ["*", "security-scan", "migrations-check"]},
  "6": {"verdict": ["ready", "ready with nits"], "checks": ["*"]},
  "0": {}
}}
```

Nothing below 10 is merge-worthy here: a nit, or a missing migrations check,
lands at 6, and `changes needed` at 0.

### How min_grade reads against each

`min_grade` in `auto_merge` (10 unless you set it) is the least grade
`review` merges, and only once every check on the commit has passed, whatever
the rubric names.

| Rubric | `min_grade` 10 merges | `min_grade` 8 merges |
|---|---|---|
| The five keys, or the ladder like them | ready, every check passed | also ready with nits |
| 10 needs the security scan | ready, with `security-scan` and `tests` passed | also ready or ready with nits once `tests` passed, `security-scan` or not |
| The stricter ladder | ready, every check passed, `security-scan` and `migrations-check` among them | the same as 10: nothing grades 8 or 9 |

On the stricter ladder `min_grade` 6 would merge nits too. Pick `min_grade` by
reading the rung it lands on, not the number alone.

## Read only from the factory's root

The loop, `loop.py grade` and the CI review read the rubric from the factory's
own checkout: [`review-rubric.json`](../review-rubric.json) at its root, or the file `review_rubric`
names in its `loop.json`. Never from a project's clone, and never from the
pull request. A project's own `loop.json` can't set `review_rubric` either.
Anyone who can push to a project could otherwise give its every pull request
a 10, and with `auto_merge` on, merge it. The CI review reads the root
[`review-rubric.json`](../review-rubric.json) alone; [`examples/ci/README.md`](../examples/ci/README.md) says where that can
differ from the loop's.

## Rungs name check runs, never the reviewer's words

A rung's `checks` are matched against the check runs GitHub lists for the
reviewed commit, by name. The report's text is never matched. The reviewer
reads the diff, and the pull request's author wrote the diff, so a line in it
saying `security-scan passed` could find its way into the report. The verdict
is the one thing read from the report, and it has to be one of three words.

A check run's name is set by whoever writes the workflow that runs it, and a
pull request that edits [`.github/workflows/`](../.github/workflows/) can add a passing job with any
name. A rung trusts a name only as far as your repo controls who can add one:
have a person review workflow changes, and make the checks a rung names
required in branch protection.

## Try a rubric before auto_merge relies on it

`loop.py grade` prints the grade a verdict would get on a pull request's head
commit, with the rubric on disk now, and changes nothing: it posts no comment,
writes no status row and takes no lock, so it runs beside a running loop.

```text
python3 scripts/loop.py grade 42 --verdict "ready"
Grade 8/10: ready, checks (tests) passed; 10 needs a check named security-scan, and none ran.

python3 scripts/loop.py grade 7 --verdict "ready with nits" --project projects/payments
Grade pending: checks still running.
```

Run it on a few open pull requests with each verdict before you turn on
`auto_merge`, or before you change a rubric it already uses. It exits 0 for
any grade, and 1, saying why, when it can't read the pull request's head.
[`skills/review-pr/`](../skills/review-pr/) runs the same command for a review a person runs by hand.
