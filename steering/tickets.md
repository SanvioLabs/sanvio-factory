# Tickets: what goes in one, and how one ends

Read this when you write an issue, put one on the loop, or close one.
[`.github/ISSUE_TEMPLATE/loop-task.md`](../.github/ISSUE_TEMPLATE/loop-task.md) is the shape; this file is why.

## What goes in

A ticket says what has to be true and how anyone can tell. It doesn't say how
to write the code: the rules in [`AGENTS.md`](../AGENTS.md) and the steering already do.

The sections are Stelliad's Ticket Authoring Standard, so `stelliad:create-ticket`
writes this shape and `stelliad:review-ticket` grades it. Its checker blocks on
a missing required section, whatever else the ticket gets right.

| Section | Holds | Fails when |
|---|---|---|
| **Objective** | The outcome when it's done, in one or two sentences. At least 8 words | It describes a task or a feeling ("make the gate better") rather than a result |
| **Why** | The reason, legible to someone who wasn't there. At least 12 words | It leans on a conversation the reader didn't have |
| **Acceptance Criteria** | Flat `- [ ]` items, one observable outcome each, in order, failure behaviour included | Nobody could check one. "Works well" is not a check |
| **Scope** | **In:** what it changes, with the exact files in backticks, such as `src/app/main.py`, and folders as `dir/` or `a/b`. A bare folder name with no slash doesn't count. The loop holds a ticket that names a path a running issue named. **Out:** what it leaves alone | The Out half is missing |
| **Risk** | Low, Medium, High or Critical, with a reason for the top two | It's missing |
| Verification, Context, Dependencies, References | Only when they carry something: a command the tests can't express, a past decision, `Depends on #N`, files to start from, a `Spec: docs/specs/<name>` line naming the spec it builds | They're there as `N/A`, or References turns into instructions for writing the code |

The standard also allows Requirements, Constraints, Assumptions and Human
Approval, on the same terms, and `stelliad:create-ticket` writes them when they
apply. The title starts with a verb and names the outcome: "Make `--issue N`
exit when the issue is done", not "Loop bug".

Write a criterion as behaviour you can observe, and let the test prove it:
"`run --issue 12` returns once #12 has a pull request, proved by a new test in
[`tests/test_loop.py`](../tests/test_loop.py)", not "add `test_issue_exits`".

**Check a claim about a tool before a ticket rests on it.** Where Context or
Requirements says how a tool or runtime behaves (what a test runner passes
through, what a command prints, what an API allows), run it first and say in
the ticket how you checked. The loop builds on the claim with nobody watching,
and finds out it's wrong only after the rounds it took.
Learned 2026-10-28: #279 said a mod test could print, and under
`claude plugin test` its output never reached the caller. The loop spent its
whole token budget finding out.

**A ticket that touches an endpoint**, in a project whose `security_level` is
`guided` or higher ([`api-security.md`](api-security.md)), names the declaration each route takes
in Scope (`public(reason)`, or `role(...)` with `owns` where the route names a
user's resource), and states the wrong-user check as behaviour in Acceptance
Criteria: "a request with another user's token is refused with 403", and "a
request with no token is refused with 401" for any non-public route. A ticket
that removes a feature lists the routes, tables, secrets and permissions it
leaves behind, and removes them in the same change.

**One change per ticket.** If the acceptance criteria hold two unrelated
outcomes, it's two tickets. If it can't fit one pull request, split it so each
part can be tested on its own.

**One type label.** Every issue carries exactly one of `bug`, `enhancement`,
`documentation` or `chore` (maintenance: dependencies, tooling, tidying). A
pull request takes its type from its own label, or else from the issue it
closes, and [`skills/work-report/`](../skills/work-report/) counts work by it. GitHub creates the
first three with a new repo; `gh label create chore --description
"Maintenance: dependencies, tooling, tidying"` adds the fourth.

`stelliad:create-ticket` also suggests priority and risk labels. Beyond the
type and the loop's labels the starter ships none, so it says when one is
missing, and that's fine to leave.

## Ready for the loop

Label an issue `loop-ready` only when all of these hold. The `loop-control`
skill checks them and asks before it labels.

- Someone has read the whole issue, comments included. A ticket is an
  instruction to an agent, and the loop acts on it with nobody watching.
- At least one acceptance criterion is a test that fails now and passes
  after, which the loop's `test_command` runs. If the proof is something
  else, the loop can't see it, and the reviewer only reads.
- A file the build agent can't make itself comes from `generate_command`,
  which the loop runs after each build, committing what it writes. The ticket
  says the file changes, not that the agent runs the command. A project sets
  the key in its own `loop.json`; [`HOW-IT-WORKS.md`](../HOW-IT-WORKS.md) has it.
- Where Stelliad is installed, `stelliad:review-ticket` says READY. Its
  docs call the Ready label `agent-ready`; here it's `loop-ready`, applied
  through `loop-control`.
- Any new package it needs is already on `base`, or named on a `Depends on #N`
  line, unless this loop's `agent` is allowed to install. The build agent
  can't install one by default; [`HOW-IT-WORKS.md`](../HOW-IT-WORKS.md) (*The build agent doesn't
  install packages*) has how to add it first.
- Nothing outside the repo: no deploy, no message, no credentials, nothing the
  guard would refuse.
- Risk is Low or Medium, and there's no Human Approval section. The loop runs
  with nobody watching, so nothing in a ticket can make it stop and ask.
- Its dependencies can be left to the loop. It waits until each `Depends on
  #N` line's issues, and each issue GitHub lists as blocking it, are closed
  as completed, so `loop-ready` can go on a dependent issue straight away. One
  closed as not planned, a number that isn't an issue, or a cycle blocks it
  with a comment. The loop doesn't read priority: of the issues with nothing
  left to wait for, it takes the lowest-numbered.
- It isn't assigned to someone else.
- It carries exactly one type label: `bug`, `enhancement`, `documentation` or
  `chore`.

## While it's worked

The loop comments on the issue twice at most, so the issue tells the story
without the machine that ran it:

- **A pull request opened:** the link, how many rounds it took, and that the
  tests and review passed.
- **Blocked:** why, the round count, and that the plan, test output and review
  are in `.loop/issue-N/` on the machine that ran it.

A person commenting adds what changed: a decision, a narrowed scope, an
answer to a question the review raised. A comment that changes the
acceptance criteria changes the ticket, so edit the description too. The loop reads the
description, not the comments.

## How it ends

- **Done:** the pull request that does it says `Closes #N`, and merging it
  closes the issue. The loop writes that line itself. A pull request a person
  opens writes it too. GitHub only acts on it when the pull request merges
  into the repo's default branch; one that lands somewhere else first leaves
  the issue for a person to close.
- **Blocked:** stays open with `loop:blocked`. Fix the ticket (usually the
  acceptance criteria), take `loop:blocked` off, put `loop-ready` back. The loop picks
  up where it left off, on its old `loop/issue-N` branch. For a clean start,
  delete that branch and its checkout under `~/.sanvio-loop/` first.
- **Not doing it:** close it as not planned, with one line saying why.

Never close an issue whose acceptance criteria haven't been checked.
