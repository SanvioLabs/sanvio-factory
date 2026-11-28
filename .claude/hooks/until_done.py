#!/usr/bin/env python3
"""Until done: a Stop hook that keeps a session building until its acceptance check passes.

From Sanvio Factory by Sanvio Labs, MIT: https://github.com/SanvioLabs/sanvio-factory

Wired in .claude/settings.json on Stop. Off until a session arms it. Say "keep going until it's
done" and the agent arms it with the check that proves it; from then on, each time the agent goes
to end its turn, this runs the check. It passes and the turn ends. It fails and the stop is refused,
with the check's output handed back, so the agent takes its own Next: instead of waiting for you
to say "continue".

    python3 .claude/hooks/until_done.py --set --spec 003            done when its TASKS.md has no open box
    python3 .claude/hooks/until_done.py --set --check "npm test"    any command; exit 0 is done
    python3 .claude/hooks/until_done.py --set --spec 003 --check "npm test" --max 20 --max-tokens 20000000
    python3 .claude/hooks/until_done.py --status | --clear

The check is a command's exit status, or TASKS.md's boxes, never the agent saying it's done.

It lets the stop through, and says why, when:

- the agent's last message carries a 🔴 No go: a decision that's yours, or a step you take. It
  stays armed, so the turn after you answer is held to the same check
- the check couldn't run (not found, timed out). That isn't a pass, so it stays armed
- nothing moved for STALL_LIMIT continuations in a row: the same check output, the same HEAD,
  the same working tree. A session that can't make progress is handed back, not spun
- it has continued --max times (DEFAULT_MAX)
- the session has used more than --max-tokens since it was armed (DEFAULT_MAX_TOKENS, 0 for none),
  counted the way the loop counts max_issue_tokens: input, output, cache write and cache read, each
  message once, subagents included
- the run is headless (SANVIO_HEADLESS=1): the loop and bin/factory have their own rounds and budget

It ignores stop_hook_active on purpose: that's true on every stop after the first refusal, so
honouring it would allow one extra push and no more. The stall, --max and --max-tokens limits end
a session that can't finish.

It fails open, and says so: a bug here must never trap a session, so an error of its own lets the
stop through with a message naming it. Its state is one file per session in local-data/until-done/,
so arming one session never holds another. With no file for this session it returns at once.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent
STATE = ROOT / "local-data" / "until-done"
SPECS = ROOT / "docs" / "specs"
TRANSCRIPTS = Path.home() / ".claude" / "projects"

DEFAULT_MAX = 40
DEFAULT_MAX_TOKENS = 10_000_000
STALL_LIMIT = 3
CHECK_TIMEOUT = 840  # under the 900 seconds .claude/settings.json gives the hook
OUTPUT_TAIL = 2000
TRANSCRIPT_TAIL = 512 * 1024

# A session id goes into a file name, so it's held to the shape Claude Code gives it.
SESSION_ID = re.compile(r"\A[0-9a-fA-F-]{8,64}\Z")
UNCHECKED = re.compile(r"^\s*[-*]\s+\[ \]\s+(.*)$")
# The flag line steering/response-style.md defines: the icon and the words together, so a 🔴 quoted
# in a table of earlier findings doesn't end the run.
NO_GO = re.compile(r"🔴\s*\**\s*No[ -]go", re.IGNORECASE)


# -- state --------------------------------------------------------------------


def clean_session(value):
    return value if isinstance(value, str) and SESSION_ID.match(value) else None


def state_path(session):
    return STATE / (session + ".json")


def load_state(session):
    path = state_path(session)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def save_state(session, state):
    STATE.mkdir(parents=True, exist_ok=True)
    path = state_path(session)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


def clear_state(session):
    path = state_path(session)
    if path.is_file():
        path.unlink()
        return True
    return False


def headless(environ=None):
    """The loop's and bin/factory's runs: scripts/names.py's reading, the old name included."""
    environ = os.environ if environ is None else environ
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import names
        return names.headless(environ)
    except Exception:  # a copy without names.py: read both names here
        return environ.get("SANVIO_HEADLESS") == "1" or environ.get("HARNESS_HEADLESS") == "1"


# -- the spec check -----------------------------------------------------------


def resolve_spec(spec):
    """A spec number (003), a spec folder, or a TASKS.md path."""
    given = Path(spec).expanduser()
    if given.is_file():
        return given.resolve()
    if (given / "TASKS.md").is_file():
        return (given / "TASKS.md").resolve()
    digits = re.sub(r"\A(?:SPEC-)?", "", spec, flags=re.IGNORECASE)
    if digits.isdigit():
        for match in sorted(SPECS.glob("{:03d}-*/TASKS.md".format(int(digits)))):
            return match.resolve()
    raise SystemExit("until_done: no TASKS.md found for spec '{}'".format(spec))


def spec_check(tasks):
    """(0 or 1, what it found) for a TASKS.md: 0 when every box is checked."""
    try:
        lines = Path(tasks).read_text(encoding="utf-8").splitlines()
    except OSError as error:
        return None, "{} can't be read: {}".format(tasks, error)
    open_tasks = [m.group(1).strip() for m in map(UNCHECKED.match, lines) if m]
    if not open_tasks:
        return 0, "TASKS.md: every box is checked"
    shown = "\n".join("  [ ] " + task[:160] for task in open_tasks[:5])
    return 1, "TASKS.md: {} unchecked\n{}".format(len(open_tasks), shown)


def run_command(command, cwd):
    """(exit status, output tail). None for the status means it couldn't run."""
    try:
        done = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True,  # nosec B602
                              timeout=CHECK_TIMEOUT, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, "timed out after {}s".format(CHECK_TIMEOUT)
    except OSError as error:
        return None, "{}: {}".format(type(error).__name__, error)
    output = (done.stdout + done.stderr).strip()[-OUTPUT_TAIL:]
    if done.returncode in (126, 127) or (os.name == "nt" and done.returncode == 9009):
        return None, output  # the shell couldn't find or run it
    return done.returncode, output


def run_check(state, cwd):
    """The spec check, then the command, as one result: the first that doesn't pass decides."""
    results = []
    if state.get("spec"):
        results.append(spec_check(state["spec"]))
    if state.get("check"):
        results.append(run_command(state["check"], cwd))
    for status, output in results:
        if status != 0:
            return status, output
    return 0, "\n".join(output for _, output in results)


def describe(state):
    parts = []
    if state.get("spec"):
        parts.append("every box in " + state["spec"])
    if state.get("check"):
        parts.append("`{}`".format(state["check"]))
    return " and ".join(parts)


# -- transcripts --------------------------------------------------------------


def find_transcript(session):
    matches = sorted(TRANSCRIPTS.glob("*/{}.jsonl".format(session)))
    return matches[0] if matches else None


def transcript_files(transcript):
    files = [transcript] if transcript.is_file() else []
    subagents = transcript.with_suffix("") / "subagents"
    if subagents.is_dir():
        files += sorted(subagents.glob("*.jsonl"))
    return files


def session_tokens(transcript):
    """The session's tokens, each message once, or None when nothing reported any.

    Claude Code writes each content block of a message on its own line and repeats the message's
    usage on each, so lines are keyed by the message's id, as the loop's stream() counts them.
    """
    if transcript is None:
        return None
    seen = {}
    for path in transcript_files(transcript):
        with path.open("r", encoding="utf-8", errors="replace") as lines:
            for line in lines:
                if '"usage"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                message = entry.get("message") if isinstance(entry, dict) else None
                if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
                    continue
                usage = message["usage"]
                key = (path.name, message.get("id") or entry.get("uuid") or len(seen))
                seen[key] = sum(value for value in (
                    usage.get("input_tokens"), usage.get("output_tokens"),
                    usage.get("cache_creation_input_tokens"), usage.get("cache_read_input_tokens"))
                    if isinstance(value, int) and not isinstance(value, bool))
    return sum(seen.values()) if seen else None


def last_assistant_text(transcript):
    if transcript is None or not transcript.is_file():
        return ""
    with transcript.open("rb") as raw:
        size = raw.seek(0, os.SEEK_END)
        raw.seek(max(0, size - TRANSCRIPT_TAIL))
        tail = raw.read().decode("utf-8", errors="replace")
    last = ""
    for line in tail.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue  # a tail's first line is usually cut part way
        message = entry.get("message") if isinstance(entry, dict) else None
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, str):
            texts = [content]
        elif isinstance(content, list):
            texts = [block.get("text", "") for block in content
                     if isinstance(block, dict) and block.get("type") == "text"]
        else:
            texts = []
        if any(text.strip() for text in texts):
            last = "\n".join(texts)
    return last


def progress(cwd, status, output):
    """What would differ if the agent had moved anything since the last stop."""
    digest = hashlib.sha256("{}\n{}".format(status, output).encode())
    for args in (["git", "rev-parse", "HEAD"], ["git", "status", "--porcelain"], ["git", "diff"]):
        try:
            digest.update(subprocess.run(args, cwd=cwd, capture_output=True, timeout=30,
                                         stdin=subprocess.DEVNULL).stdout)
        except (OSError, subprocess.TimeoutExpired):
            digest.update(b"-")  # not a repo, or no git: the check's output still counts
    return digest.hexdigest()


# -- the hook -----------------------------------------------------------------


def emit(message, reason=None):
    out = {"systemMessage": message}
    if reason is not None:
        out["decision"] = "block"
        out["reason"] = reason
    print(json.dumps(out))
    sys.exit(0)


def stop(event):
    if headless():
        sys.exit(0)  # the loop's rounds and max_issue_tokens already bound it
    session = clean_session(event.get("session_id"))
    state = load_state(session) if session else None
    if state is None:
        sys.exit(0)  # not armed, the usual case

    cwd = state.get("cwd") or event.get("cwd") or os.getcwd()
    raw = event.get("transcript_path")
    transcript = Path(raw) if isinstance(raw, str) and raw else None
    limit = int(state.get("max", DEFAULT_MAX))

    ceiling = int(state.get("max_tokens", DEFAULT_MAX_TOKENS))
    total = session_tokens(transcript)
    if ceiling and total is not None:
        if state.get("tokens_at_arm") is None:
            state["tokens_at_arm"] = total  # armed before its log could be found
        used = total - int(state["tokens_at_arm"])
        state["tokens_used"] = used
        if used > ceiling:
            clear_state(session)
            emit("🛑 until-done: used {:,} tokens since it was armed, over the ceiling of {:,}. "
                 "Disarmed and handed back.".format(used, ceiling))

    if NO_GO.search(last_assistant_text(transcript)):
        save_state(session, state)
        emit("⏸ until-done: stopped on a 🔴 No go. Still armed, so the next turn is held to the "
             "same check.")

    status, output = run_check(state, cwd)
    if status is None:
        save_state(session, state)
        emit("⚠️ until-done: the check couldn't run, so it isn't treated as passing. Still armed. "
             "{}".format(output[-300:]))
    if status == 0:
        clear_state(session)
        emit("✅ until-done: the check passed after {} continuation(s). Disarmed.".format(
            state.get("blocks", 0)))

    fingerprint = progress(cwd, status, output)
    stalls = state.get("stalls", 0) + 1 if fingerprint == state.get("fingerprint") else 0
    blocks = state.get("blocks", 0) + 1
    if stalls >= STALL_LIMIT:
        clear_state(session)
        emit("🛑 until-done: nothing changed across {} continuations (the same check output and "
             "tree). Disarmed and handed back.".format(STALL_LIMIT))
    if blocks > limit:
        clear_state(session)
        emit("🛑 until-done: {} continuations and the check still fails. Disarmed and handed "
             "back.".format(limit))

    state.update(blocks=blocks, stalls=stalls, fingerprint=fingerprint, last_status=status,
                 last_run=time.strftime("%Y-%m-%dT%H:%M:%S"))
    save_state(session, state)
    used = state.get("tokens_used")
    spent = ", {:,}/{:,} tokens".format(used, ceiling) if ceiling and used is not None else ""
    emit("🔄 until-done {}/{}{}: not done yet, continuing.".format(blocks, limit, spent), reason=(
        "Not done yet: {} has to pass, and it exited {}. Don't end the turn to ask whether to "
        "continue: take your own Next: and keep building until it passes.\n\n"
        "Check output (tail):\n{}\n\n"
        "End the turn only with a `Go: 🔴 No go` line that names the decision that's the person's, "
        "or the step they take: a merge, a deploy, anything sent outside, a payment or a legal "
        "commitment. Those still wait for them.".format(describe(state), status, output)))


# -- the commands -------------------------------------------------------------


def cli_session(args):
    session = clean_session(args.session or os.environ.get("CLAUDE_CODE_SESSION_ID"))
    if session is None:
        # Never a shared file: one that held every session in the clone would trap the ones that
        # never asked for it.
        raise SystemExit("until_done: no session id (CLAUDE_CODE_SESSION_ID isn't set); pass --session")
    return session


def main(argv):
    parser = argparse.ArgumentParser(prog="until_done.py", description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stop", action="store_true", help="run as the Stop hook, the event on stdin")
    mode.add_argument("--set", action="store_true", help="arm this session")
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--clear", action="store_true")
    parser.add_argument("--check", help="a command; exit 0 means done")
    parser.add_argument("--spec", help="a spec number, folder or TASKS.md: done when every box is checked")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, help="0 for no ceiling")
    parser.add_argument("--cwd", help="where the check runs (default: here)")
    parser.add_argument("--session")
    args = parser.parse_args(argv)

    if args.stop:
        event = json.load(sys.stdin)
        stop(event if isinstance(event, dict) else {})
        return 0

    session = cli_session(args)
    if args.clear:
        print("until-done: disarmed" if clear_state(session) else "until-done: wasn't armed")
        return 0
    if args.status:
        state = load_state(session)
        print(json.dumps({k: v for k, v in state.items() if k != "fingerprint"}, indent=2)
              if state else "until-done: not armed")
        return 0
    if not (args.spec or args.check):
        parser.error("--set needs --spec, --check, or both")
    if args.max < 1:
        parser.error("--max must be 1 or more")
    if args.max_tokens < 0:
        parser.error("--max-tokens must be 0 (no ceiling) or more")
    state = {"spec": str(resolve_spec(args.spec)) if args.spec else None, "check": args.check,
             "cwd": str(Path(args.cwd or os.getcwd()).resolve()), "max": args.max,
             "max_tokens": args.max_tokens, "blocks": 0, "stalls": 0,
             "tokens_at_arm": session_tokens(find_transcript(session)),
             "armed_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    save_state(session, state)
    ceiling = "{:,} tokens".format(args.max_tokens) if args.max_tokens else "no token ceiling"
    print("until-done: armed. Done when {} passes. At most {} continuations, {}.".format(
        describe(state), args.max, ceiling))
    return 0


def fail_open(error):
    """Let the stop through, and say why."""
    print(json.dumps({"systemMessage": "until-done failed open: {}: {}".format(
        type(error).__name__, error)}))
    sys.exit(0)


def run(argv):
    """main(), failing open on any error of its own: a bug here must never trap a session."""
    try:
        return main(argv)
    except SystemExit:
        raise
    except Exception as error:  # fail open, and say so in the message fail_open() prints
        fail_open(error)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
