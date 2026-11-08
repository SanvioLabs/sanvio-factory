---
name: retro
description: Find out why the agent got something wrong in an ordinary session, from that session's own log, and queue the answer for learn. Use when someone says "retro", "run a retro", "why did that go wrong", or asks which sessions the retro hook kept.
license: MIT. From the Sanvio Labs harness starter, https://github.com/SanvioLabs/sanvio-harness-starter
---

# Session retro

A correction says what the agent got wrong. A retro says why it didn't know:
nothing said it, it wasn't loaded, it was loaded and ignored, something said the
opposite, or nothing could have. Each points at a different fix, and
[`skills/learn/`](../learn/) uses the cause to pick one. The loop's retro does
this for loop runs; this does it for ordinary sessions, with the same digest,
causes and checks from [`scripts/loop.py`](../../scripts/loop.py).

With `SANVIO_RETRO=on`, [`.claude/hooks/session_retro.py`](../../.claude/hooks/session_retro.py)
keeps a copy of each session's log where the person corrected the agent, or
one file was edited three or more times, in `local-data/retro/`. Off, nothing
is kept, and this skill reads the current session only.

## Steps

1. **Write the prompt.** Run `python3 .claude/hooks/session_retro.py prompt`.
   It takes the oldest kept session, or this one when none is kept, and writes
   the classifier's prompt to a file. Add `--current` to read this session
   whatever is kept. Tell the person which session it is and how many are
   waiting, from what it prints.
2. **Have a fresh agent classify it.** Run
   `python3 .claude/hooks/session_retro.py classify <session id>`, and give
   the command up to 10 minutes. It starts a new `claude` that can only read,
   gives it the prompt, and saves its reply beside the prompt. It has to be
   fresh. An agent asked about its own session tends to make up the turn where
   it learned something. Where `claude` isn't installed it says so: run the
   prompt in a separate session that can only read files, and save its reply
   where the message says.
3. **Record it.** Run
   `python3 .claude/hooks/session_retro.py record <session id>`. It reads the
   saved reply, drops any finding it can't place in the log, appends an entry
   to `.loop/lessons.md` marked as from a session, and deletes the kept copy,
   the prompt and the reply. The entry names each correction by its record in
   the log, never in the person's words.
4. **Offer to learn from it.** Show the entry it printed, and offer
   [`skills/learn/`](../learn/) on it. The mistake and the right behaviour still
   come from the person.

## Rules

- Never write, change or add a finding yourself, and never edit the saved
  reply. The fresh agent classifies and the script checks.
- Never read the kept log, the prompt file or the reply into this session.
  The fresh agent reads them.
- Nothing from a session log, a prompt file or a lessons entry goes into a
  tracked file, a pull request, an issue, or anything that leaves this machine.
- If the person says a kept session needs no retro, run
  `python3 .claude/hooks/session_retro.py drop <session id>`. It deletes the
  copy and writes nothing.

## Output

The session's id, the entry written to `.loop/lessons.md`, and the lines it
printed about findings it dropped.
