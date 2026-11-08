---
name: review-tests
description: Check whether a set of tests, especially AI-generated ones, would actually catch a bug. Breaks the code on purpose in a scratch copy, runs the tests, and reports which tests protect something and which only pass. Use when asked "are these tests any good", "review the tests", "would these catch a regression", or after an agent writes tests.
license: MIT. From Sanvio Factory by Sanvio Labs, https://github.com/SanvioLabs/sanvio-factory
---

# Review tests

A test that passes proves nothing on its own. A test is worth keeping when it
fails the moment the behaviour it covers breaks. AI-written tests often pass
for the wrong reason: they assert what the code does rather than what it
should do, test the mock instead of the code, or check nothing at all.

## Inputs

The test file or folder, and the code it covers. If it's unclear which code a
test covers, ask.

## Steps

1. **Run them as they are.** All pass, or note which don't. Don't go further on
   a red suite: say what fails and stop.
2. **Read each test** and flag the shapes that pass without protecting:
   - No assertion, or one that can't fail (`assert True`, `expect(x).toBeDefined()`
     on something always defined)
   - Asserts the mock's return value rather than what the code did with it
   - Copies the implementation's logic into the expected value
   - Only the happy path: nothing for empty input, a failure, a boundary
   - A name that doesn't say what behaviour it guards
3. **Break the code on purpose, in a scratch copy only.** Make one
   `git worktree add <scratch path> HEAD`, or copy the project to a temporary
   folder, and work there. Never edit the real working tree. Pick three to five
   lines that matter (a comparison, a condition, a return value, an error
   branch) and change one at a time: flip `<` to `<=`, negate a condition,
   return early, drop an error check. Run the tests after each change and
   record which test, if any, failed.
4. **Remove the scratch copy** (`git worktree remove <scratch path>`) and
   confirm with `git status` that the real working tree is untouched.

## Output

- A table of the deliberate breaks: what you changed, `file:line`, and the test
  that caught it, or **nothing caught it**
- The tests that never failed during step 3, with step 2's reason if there is
  one. These are the candidates to rewrite or delete
- The behaviour no test covers, as a short list of tests worth writing, each
  in one line. Don't write them unless asked

## Rules

- Never change the real code or the real tests. Everything breakable happens in
  the scratch copy, and the scratch copy is removed before you report.
- Never weaken an assertion or delete a test to make anything pass.
- Coverage percentages are not the answer here. A line that runs under a test
  that can't fail is covered and unprotected.
