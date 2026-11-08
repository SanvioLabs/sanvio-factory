# Factories

A factory is any system that takes work in and puts checked work out. This
repo is one. So is another team's delivery system, or another copy of this
factory. This repo can hand an issue to another factory and review what comes
back, with GitHub as the only thing between them.

Name the factory in `factories.json` at the harness root. Copy
[`factories.example.json`](../factories.example.json) to start: it holds one step, with every key a step can set. A factory that runs
on this machine gets a folder here, one checkout per factory, named the way
`factories.json` names it:

```bash
cd factories
git clone <the factory's repo> build-team    # the name factories.json uses
```

A factory someone else runs needs no folder: `factories.json` names it as
`remote`. A step's two labels match on GitHub whatever their case, and neither
can hold a comma, which `gh` would read as two labels.

This repo tracks nothing in this folder except this file, so a factory's
code never reaches this repo's history.

## What this repo does with a factory's folder

It reads the checkout's commit at submission, and the run records it, with a
warning when the checkout had uncommitted changes. It reads the checkout's own
git config first (what it includes, and its worktree config), and asks
`git status` only when none of it names a filter or fsmonitor, since either would run something of the factory's. A folder that
isn't its own checkout is refused, so this repo's own commit is never
recorded as the factory's. That's the version that was
checked out when you submitted, not proof of what the factory ran. It will
never run, import or load a file from a factory's folder.
The factory runs under its own rules and its own guard, not this harness's.

## What the factory must do

This repo and the factory meet only on GitHub, so this is the whole
contract. A factory that does less doesn't break anything here: its run waits,
then stops at the time limit or needs a person.

- **Take the issue when the submit label appears on it.** That label, added on
  your yes, is the only thing this repo sends.
- **Open one pull request that closes the issue,** with `Closes #N` in its
  body, into the repo's default branch. GitHub links it to the issue, and
  that's how this repo finds it. Open it as the step's `factory_login`, from
  that account's own fork if it's ever to read `ready for a person`. A draft
  isn't reviewed until it's marked ready.
- **Take the submit label off once it hands the pull request back.** `resend`
  waits until it's gone before it puts it back for another round.
- **On a round, read the review and push to the same branch.** The submit
  label comes back on the issue, and the newest comment starting
  `<!-- loop-review-pr-report -->` from your login says what to change. New
  commits go on the same pull request. A second pull request is followed only
  when the first is closed.
- **Give up with the stopped label.** Put the step's `stopped_label` on the
  issue, and the run stops with its reason.
- **Never merge, approve or close** the pull request or the issue. A person
  does.

A factory that's a copy of this repo does all of that with its own loop,
once its `loop.json` says so. In its top-level `loop.json` on the factory's
machine, never a project's own:

```json
{
  "ready_label": "<the step's submit_label>",
  "blocked_label": "<the step's stopped_label>",
  "review_logins": ["<your GitHub login>"]
}
```

`review_logins` is whose review its round reads: yours, since `review` posts
the review under your login. Left empty, it reads only its own login's, and
your review never reaches its planner.

## Before you add one

- **Keep its work out of this factory.** A factory that runs on this machine
  works in its own clone of the repo, outside this factory, and never in a
  clone under [`projects/`](../projects/). An agent started below the harness root loads this
  harness's [`CLAUDE.md`](../CLAUDE.md), which tells it to stop.
- **Check what it's allowed to see.** Submitting an issue sends the issue and
  the repo to that factory. A factory someone else runs reaches the repo
  through a GitHub account of theirs, and the code it works on sits on their
  machine. Customer information goes only to a tool the customer has agreed
  to, per [`steering/data-and-tools.md`](../steering/data-and-tools.md).
- **Have it work from its own fork, with triage access only.** A factory that
  can push to the repo could post a passing check on its own commit, so only
  one working from its own fork can read `ready for a person`;
  [*Getting to ready*](#getting-to-ready) has everything that takes. This
  repo reads the account's access; it can't see another account or app the
  factory also controls, so check it has none that can write to the repo.
  Triage lets the factory take its own label off. `factory_login` names a
  user account, such as a machine user: an organisation authors no pull
  request, and a GitHub App's bot can't be looked up, so dispatch refuses
  either.
- **On a private repo, switch fork workflows on, without write tokens.** A
  private repo runs no workflow for a fork's pull request by default, so the
  factory's checks never report. Turn on running fork pull request workflows,
  and leave sending them write tokens and secrets off: with either on, or
  unreadable to you, the checks read `checks pass, not independent`.
- **Know what ready means.** It's what this repo can read, not proof:
  [*Getting to ready*](#getting-to-ready) says what it requires and what it
  can't show.
- **A factory that's a copy of this repo works in the same repo.** Its
  loop takes a round only on its own pull request from a branch in the repo,
  so its runs read `checks pass, not independent` and a person weighs its
  checks. A round on a pull request from its own fork is still to decide.
- **A local factory runs as you.** It can change this repo's files on this
  machine, run records included, so a local factory is one you already trust
  with this clone.
- **Check it can take a round.** A review that asks for changes goes back
  to the factory as its submit label, put back on the issue, and the review's
  comment on its pull request says what to change. A factory that reads only
  its issue never sees that comment, so it rebuilds nothing. This factory's
  loop reads it, so a factory that is a copy of this repo takes a round
  once it has the loop that does.
- **Keep a factory copy's `loop.json` local.** A copy of this starter that
  commits its `loop.json` fails the starter's own link check on every round,
  whatever the change.
- **Clone the repo, if it isn't this one.** `review` reads a pull request
  from the repo's clone under [`projects/`](../projects/), and that clone's `loop.json` has to set
  `test_command`: the loop refuses a project without one, since the default
  tests this repo.
- **Keep `factories.json` local.** It's gitignored, so a factory's name and
  its account stay on the machine that runs it. Only [`factories.example.json`](../factories.example.json)
  is tracked: name no real factory in it.

## Getting to ready

This is the one place that says what ready takes. The scripts, the skill and
[`HOW-IT-WORKS.md`](../HOW-IT-WORKS.md) point here.

### What ready requires

A run reads `ready for a person` only when the review of the pull request's
head says `ready` or `ready with nits`, and then all of these hold. It follows
from these rules and the tests; no live run has read it yet, since the probe's
factory account has admin access. Each
`status` checks them again from the start, and one it can't check isn't
ready.

- **The required checks pass, read from the base repo.** They're the checks
  the base branch dispatch recorded requires, the repo's default, read from
  the branch and its rulesets, which anyone who can read the repo sees.
  Their results come from the base repo's own check runs and statuses for the
  reviewed commit, never from the pull request's rollup, which can show a
  fork's own. Every run of a check is read, and the newest of each name in
  each check suite stands for it, so a re-run counts; where a check has more
  than one entry, the worst counts, so another suite's pass never hides a
  failure. A skipped check never passes. A check pinned to apps counts only
  those apps' runs, each of them, and one pinned to an app that posts commit
  statuses rather than check runs reads pending. Short of this:
  `checks failing`, `checks pending`, or `checks unknown` when they can't be
  read.
- **The branch requires a check.** One that requires none reads
  `no required check`.
- **The head hasn't moved since the review.** If it has, the checks read
  `checks pending` until the next review.
- **CI is left alone.** A pull request that changes [`.github/`](../.github/), the other CI
  configs and check-config files at the top of the repo, or any path the
  step names in `ci_paths`, compared by tree between where it leaves the
  branch and its head, so a rename counts, reads `changes CI`.
- **The checks are independent of the factory.** Otherwise they read
  `checks pass, not independent`, with every reason named:
  - it comes from a fork owned by the account dispatch recorded for
    `factory_login`, by account id, so a renamed login taken by someone else
    doesn't count: not from a branch in the repo, and not in a run recorded
    before account ids were
  - that account has read or triage access to the repo and no more, and your
    own account can read it
  - each required check's GitHub Actions run came from the fork's own
    `pull_request` run, since a comment, a push or a `pull_request_target`
    workflow on any branch can run the pull request's code with a token that
    posts checks
  - the factory's account posted no commit status on the commit
  - no other pull request shares its head, and its base was never changed,
    since check runs belong to the commit
  - a repo that isn't public sends fork pull request workflows no write token
    and no secrets
  - the base branch has no `pull_request_target` or `workflow_run` workflow

Ready is a claim about what this repo can read, not proof the factory
couldn't have produced its checks. GitHub records no producer for a commit
status, and nothing of which workflow set or edited a check run's result; a
third-party CI's settings, and workflows on branches other than the base,
can't be seen from here; and a factory can always shape what CI tests through
a test script or a test config. So read the diff. Pinning each required check
to the app that runs it, and keeping `pull_request_target`, `workflow_run` and
comment-triggered workflows that run pull request code off every branch,
leaves the factory the fewest ways in.

Only a factory that works from its own fork gets there. A copy of this
repo pushes its branches to the repo, so its runs read
`checks pass, not independent` at best.

### Setting it up

`status` names what a run is missing. It stops at the first of some rows, such
as a branch that requires no check, so fix that one and run it again. For any
row, and before the first run on a repo, open a pull request there as the
factory would, then run
`python3 scripts/factories.py doctor --repo <owner>/<repo> --pr <N>`. It
builds the record dispatch would make, from the step's `factory_login` and the
repo's default branch, takes the head as reviewed, and moves it on through the
run's own code, changing nothing. Where you haven't posted a review of the
head, it reads it as ready and says so, so the checks are read, and gives no
merge: no review read that commit. It stops where
a run would, so the stopped label, a pull request that isn't the factory's, a
draft, another base or a `changes needed` review reads no checks, and then it
exits 1. It lists every call with what it came to, notes a reply it couldn't
use, or a row it skipped, on the call that gave it, and ends with what
`status` would say. It needs `factory_login` in `factories.json`.

| Setting | Who changes it | Without it |
|---|---|---|
| The default branch requires at least one status check, through branch protection or a ruleset | A repo admin | `no required check`, and dispatch warns before the yes |
| On a private repo in an organisation, forking private repos is allowed, by the organisation and then the repo; both are off by default | An organisation owner, then a repo admin | The factory can't fork, so its pull request comes from a branch in the repo: `checks pass, not independent` |
| On a private repo, workflows run for fork pull requests | A repo admin, where the organisation allows it | The required checks never report: `checks pending` |
| Fork pull request workflows get no write token and no secrets | A repo admin | `checks pass, not independent` |
| A workflow run GitHub holds for approval, such as a first-time contributor's, is approved | A repo maintainer, on the pull request | `checks pending` until it's approved, which keeps the time limit, as [`HOW-IT-WORKS.md`](../HOW-IT-WORKS.md#handing-work-to-another-factory) says |
| `factory_login` is a user account, such as a machine user, with read or triage access to the repo and no more | A repo admin | Dispatch refuses an organisation; more access reads `checks pass, not independent` |
| Your own account can read `factory_login`'s access to the repo | A repo admin | Nothing reads ready, and `status` says it couldn't read it |
| The factory opens its pull request from its own fork, as `factory_login` | The factory | `checks pass, not independent` |
| No workflow on the base branch runs on `pull_request_target` or `workflow_run` | The repo's maintainers | `checks pass, not independent` |
| The pull request leaves [`.github/`](../.github/), the other CI configs and the step's `ci_paths` alone | The factory | `changes CI` |

## Picking a stopped run back up

A run stops when the factory adds its stopped label, the issue closes with
nothing back, or its time limit passes, which
[`HOW-IT-WORKS.md`](../HOW-IT-WORKS.md#handing-work-to-another-factory) says what counts toward. A head waiting on your
review is worth a `review RUN` before the limit, not after.

A stopped run is over: nothing is submitted again. Its line says whether the
issue may still carry the submit label, with the command that takes it off, so
the factory doesn't take it up with nothing tracking it. To go again, dispatch
the issue again: that adds the label once more, as a new run, and its rounds
start from 0.

## The limits

What `time_limit_hours` and `max_rounds` allow, and when a run has no limit,
is in [`HOW-IT-WORKS.md`](../HOW-IT-WORKS.md#handing-work-to-another-factory). These are
`factories.json`'s, for a factory's rounds: `loop.json`'s `max_rounds` is the
loop's own rounds on an issue, and means something else. To put a record's
limit back in range, see
[*When a record can't be read*](#when-a-record-cant-be-read).

## One person runs each run

A run lives in the clone that dispatched it. Its record is in
`.sanvio/factories/` on that machine, `review` posts under the login of
whoever runs it, and the verdict is read from that login's comment. So one
person dispatches, reviews, sends back and cancels a given run, from one
clone, and a teammate's `status` in their own clone doesn't see it. A factory
that's a copy of this repo names that person in `review_logins`. To hand a
run over, cancel it, and dispatch the issue again from the other clone.

## Stopping

To stop using a factory, first run
`python3 scripts/factories.py cancel RUN --yes` on each run `list` shows that
hasn't ended. That takes the submit label off its issue, so a factory that
hasn't started it won't. It doesn't withdraw a submission the factory has
already taken: it may keep building and open a pull request nothing tracks.
Close any it opens, and tell the factory by hand. Then delete
`factories.json`. The review comments stay on the pull requests, as the
record of what was reviewed.

## When a record can't be read

`status` names a run whose record in `.sanvio/factories/` it can't read, says
why, and goes on with the others; dispatch refuses the issue while one for it
can't be read. A record goes bad when it's edited by hand or by a local
factory, or when a newer `factories.py` wrote it. If a newer `factories.py` wrote
it, update this copy's `factories.py`: the record is fine. If you know what the
field should be, put it back as the line says, with times in the record's own
format, which carries a timezone. Otherwise, take the run's submit label off
its issue by hand if it's there, and delete that one `run-*.json`, leaving the
`.lock` beside it: the issue can then be dispatched again.

## macOS and Linux only

A run's `status`, `review`, `resend` and `cancel` hold its file lock, which
Windows lacks, so there each refuses in one line, changing nothing. `dispatch`
refuses there too, before reading anything, since nothing could then watch or
cancel the run it would start.

## github.com only

Factories work with repos on github.com. This repo tells a pull request's
repo, and a check run's, from its github.com address, so on GitHub Enterprise
Server every pull request would read as from another repo. This section is
the one place that says which origins count. A clone's origin counts when the
URL git fetches from starts `https://github.com/`, `https://USER@github.com/`,
`git@github.com:` or `ssh://git@github.com/`, in any case, followed by
`OWNER/NAME`. An SSH host alias such as `git@github-work:OWNER/NAME` doesn't,
since the host is read as written, nor does a port, `http://`, or a URL that
`insteadOf` sends somewhere else.
`review` won't run from such a clone, and `steps` warns when it's this
repo's own, each saying which rule it failed. To use another key, set
origin to `git@github.com:OWNER/NAME` and pick the key with
`git config core.sshCommand "ssh -i <key>"` in that clone, or an
`IdentityFile` under `Host github.com` in your SSH config.

The starter's maintainers check factories against GitHub itself before each
release: [`docs/maintaining.md`](../docs/maintaining.md).
