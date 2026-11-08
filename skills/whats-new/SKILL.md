---
name: whats-new
description: Say what's changed in this factory, and what this copy's own remote has that it doesn't yet, from CHANGELOG.md and `origin`, with what to do to take each one. Reports only, never pulls, merges or checks out. Use when someone asks "what's new", "what changed", "am I up to date", "what did I miss", or "what's changed since <date>".
license: MIT. From the Sanvio Labs harness starter, https://github.com/SanvioLabs/sanvio-harness-starter
---

# What's new

[`CHANGELOG.md`](../../CHANGELOG.md) is the release log: newest first, one entry per change, each
with a dated heading, the files it touched and a **Do:** line. This skill reads
it, and the copy on this repo's own `origin`, and tells the person what's new
for them.

## Steps

1. **Read [`CHANGELOG.md`](../../CHANGELOG.md) here.** If it's missing, this copy predates it, and
   everything in the remote's log is new to them.
2. **Reach the remote,** for "what's new" or "am I up to date". Say first that
   this fetches from their own `origin` and changes none of their files. Run
   these in order, each only if the one before it worked:

   ```bash
   git rev-parse --is-inside-work-tree
   ```

   ```bash
   git remote get-url origin
   ```

   ```bash
   git fetch --quiet origin
   ```

   If one fails, say which: the first means this isn't a git clone, the second
   that it has no `origin`, the third that the remote couldn't be reached
   (offline, or no access). Then report from the local log only.
3. **List the entries with a command, not by reading.** Several entries can
   share a date, and a long log is easy to miscount by eye, so let the shell
   make the list and answer from it.
   - "What's new" or "am I up to date": the headings in the remote's log that
     aren't in theirs, in the remote's order, newest first. A heading only in
     theirs is their own change, not something missing.

     ```bash
     git show origin/HEAD:CHANGELOG.md | grep '^## ' | grep -vxF -f <(git show HEAD:CHANGELOG.md 2>/dev/null | grep '^## ')
     ```

     If it says `origin/HEAD` is unknown, this clone doesn't know the remote's
     default branch. Say so and report from the local log only.
   - "What changed since <date>" or "lately": the headings in their own log
     dated on or after that day (`YYYY-MM-DD`; for "lately", the last 14 days).
     This reads only the local log and needs no fetch.

     ```bash
     grep '^## ' CHANGELOG.md | awk -v d=2026-10-12 'substr($2, 1, 10) >= d'
     ```
4. **Count the commits** each side has that the other doesn't, for "what's
   new" or "am I up to date" only, and only when steps 2 and 3 reached the
   remote. A date question has no fetch, so its count would be stale:

   ```bash
   git rev-list --left-right --count HEAD...origin/HEAD
   ```

   It prints two numbers. The first is commits here the remote doesn't have,
   the second is commits on the remote not here. Report them as "ahead N,
   behind M".
5. **Answer what was asked,** from that list. Say how many entries it has and
   give every one of them. If it's empty for "what's new", say so with the
   count: behind 0 means they're up to date, so show the latest three entries
   they do have; behind more than 0 means the remote has commits with no log
   entry, so say that. For a date, say "on or after" so the reader knows the
   day itself is included.
6. **For each entry**, give the name, one line on what it adds, and its
   **Do:** line as written.
7. **If they're behind, name how to take it:** `git pull --ff-only`. It
   fast-forwards this branch to the remote and stops rather than merging, so
   it never makes a merge they didn't ask for. It pulls the current branch's
   upstream, so if they're on another branch, say so. Before naming it, check:
   - **Ahead and behind both more than 0:** the branch has diverged from the
     remote, and the pull would refuse. Say so.
   - **`git status --porcelain` prints anything:** they have changes that
     aren't committed, and the pull may refuse. Say so, without guessing which
     files would block it.

## Rules

- Never pull, merge, check out or commit, and never offer to. Name the
  command and let the person run it. A bare "say the word and I'll pull" is
  the thing this rule is for.
- Quote the **Do:** line as written. Don't add steps it doesn't have.
- Every entry on the list is in the answer, and the count you give is the
  list's length. To be brief, shorten each line, never drop an entry.
- Never call a copy up to date when step 2 failed or `origin/HEAD` didn't
  resolve. Say the remote couldn't be read.
- Asked what the public starter has that this copy doesn't, say that's the
  starter check, a separate skill, and don't answer it here.

## Output

The entries new to them, each with what it adds and what to do, or that
they're up to date. Then "ahead N, behind M" and, if they're behind, the pull
command and whether it would refuse. End there: the next step is theirs to
run.
