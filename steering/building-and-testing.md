# Building and testing

Read this when you write or change code, or write tests for it. Whatever the
language, the habits are the same.

## Before the code

- **Spec first.** The data model, then how the core logic works, then the user
  flow. It forces the architecture decisions before there's code to defend.
  The spec lives in the repo it describes: `SPEC.md` at the root for the whole
  system, [`docs/specs/`](../docs/specs/) for the parts. Kept anywhere else, it stops travelling
  with the code.
- **Read before you write.** The code you're changing, its tests, and the code
  around it. Match its naming, its structure and how much it comments.
- **Scaffold by hand.** Interactive scaffolding tools prompt, fail on existing
  folders and waste time in an agent session. Write the config and folders
  directly, then check a build passes before writing features.
- **Know which kind of change it is.** If it stores or moves personal data,
  changes access or logging, adds a dependency or outside service, or changes
  deployment, [`compliance.md`](compliance.md) has that kind's question. Answer it before
  calling the work done.

## While you build

- **One change does one thing.** If describing a pull request needs "and",
  it's two. A reviewer should be able to read it in one sitting.
- **Tests come with the change, not after it.** A bug fix starts with a test
  that fails on the bug, then the fix that makes it pass.
- **Run it the way a user would.** A build that passes isn't a feature that
  works. Click it, call it, read what comes back.
- **Two sessions, one clone: give each its own worktree.** Two agents in one
  checkout share the branch and every file on disk, so one commits onto the
  other's branch or switches it mid-task. `git worktree add -b <branch>
  ../<name> origin/main` gives the second its own folder and branch, with the
  same hook setting. Remove it once the branch merges.
- **Add a dependency only when it earns its place.** Pin it, and commit the
  lockfile.
- **CI from the first commit.** [`examples/ci/project-checks.yml`](../examples/ci/project-checks.yml) is green on
  an empty repo and checks more as the repo grows: each job skips with a
  notice until the file it needs exists. Make its jobs required once they've
  run on a pull request.

## Tests that protect something

A test is worth keeping when it fails the moment the behaviour it covers
breaks. One that passes whatever the code does is decoration.

- **Test what it should do, from the outside.** Inputs and outputs, not which
  private function got called. A test tied to the implementation breaks on
  every refactor and catches nothing.
- **Test what a rule must not touch.** Another account's record, the other party to an action. A correct change can still leak, and tests of the intended record alone won't notice.
- **Mock only at the edges**: the network, the clock, a paid API. A test of a
  mock tests the mock.
- **Synthetic data in fixtures.** Never real customer data, never a real
  secret.
- **Check the tests an agent wrote.** They tend to assert what the code does
  rather than what it should. [`skills/review-tests/`](../skills/review-tests/) breaks the code on purpose
  and reports which tests notice.
- **Keep the fast ones fast.** Slow tests go to CI. [`gates.md`](gates.md) has where each
  check runs.

## Done

- The full suite passes, not just the new test. Show the output.
- [`skills/review-pr/`](../skills/review-pr/) has read the change before a human does.
- A human merges.

## Never

- Delete, skip or loosen a test to make it pass. If the test is wrong, say why
  in the pull request and fix it there.
- Carry a red test. One that stays red stops being read, and the next real
  failure hides behind it. Fix it, or delete it with the reason.
- Commit with `--no-verify`.
