#!/usr/bin/env python3
"""Claude Code usage log: one line per harness event, kept on this machine.

Wired in .claude/settings.json on SessionStart, SessionEnd, UserPromptSubmit,
PreToolUse and PostToolUse. It records what the harness did, so the factory's owner
can see what people actually use: which skills and agents ran, which slash
commands, when the guard refused or asked, and when a person said yes to an ask.

It records names, never content. No prompts, no command arguments, no file
paths, no code. Each person's log is .sanvio/usage/<user>.jsonl, which is
gitignored. What reaches the team is the summary skills/factory-trends/ writes,
and the person reads that before it goes anywhere.

Turn it off for yourself with SANVIO_USAGE_LOG=off. Each session start then
writes one line and nothing else: the time and "event": "log_off", so a quiet
log reads as switched off rather than unused (NIST SP 800-53 AU-2). It never
blocks a tool call, never prints, and never stops a session if it fails.

Each line carries prev, the hash of the line before it (scripts/log_chain.py),
so an edit, a removal or an insertion shows in the usage report and the
dashboard. It shows a change; it can't stop one. Agents can't write to the log:
.claude/hooks/guard.py refuses it.

Entries are kept for SANVIO_KEEP_DAYS, 90 by default. Each session start drops
older ones from your own log, with the log on or off, so turning it off doesn't
keep old entries forever. An entry whose time can't be read is kept.
"""
import datetime
import getpass
import json
import os
import re
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS))
import guard  # noqa: E402 (the guard's own verdict, so there's one copy of the rules)
sys.path.insert(0, str(HOOKS.parent.parent / "scripts"))
import names  # noqa: E402 (the state folder and the variables)
import log_chain  # noqa: E402 (each line linked to the one before it, so an edit shows)

FILE_TOOLS = guard.FILE_TOOLS + ("Grep", "Glob")
COMMAND = re.compile(r"^/([A-Za-z0-9][A-Za-z0-9:_-]*)(\s|$)")
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def rule(tool, reason=""):
    """Which of the guard's rules a verdict on this tool came from, given the guard's reason for it."""
    if reason in (guard.HEADLESS_SHELL, guard.HEADLESS_CONNECTOR, guard.HEADLESS_OUTSIDE, guard.HEADLESS_PRIVATE):
        return "headless"
    if tool in FILE_TOOLS:
        return "credential-file"
    if tool == "Bash":
        return "credential-command"
    return "connector-write"


def entry(hook, event):
    """The log line for one hook event, or None when there's nothing to record."""
    tool = event.get("tool_name", "")
    data = event.get("tool_input") or {}

    if hook == "SessionStart":
        line = {"event": "session_start", "source": event.get("source", "")}
        if names.headless():
            line["headless"] = True  # started by bin/factory, so a report can tell a script from a person
        return line
    if hook == "SessionEnd":
        return {"event": "session_end", "reason": event.get("reason", "")}
    if hook == "UserPromptSubmit":
        match = COMMAND.match(event.get("prompt", "").lstrip())
        return {"event": "command", "name": match.group(1)} if match else None

    if hook == "PreToolUse":
        if tool == "Skill":
            return {"event": "skill", "name": str(data.get("skill", ""))}
        if tool in ("Agent", "Task"):
            return {"event": "agent", "name": str(data.get("subagent_type") or "general-purpose")}
        verdict = guard.decide(event)
        if verdict:
            line = {"event": "guard_" + verdict[0], "rule": rule(tool, verdict[1])}
            if tool.startswith("mcp__"):
                line["tool"] = tool
            return line
        return None

    if hook == "PostToolUse":
        # The guard asked before this ran, and it ran: a person said yes.
        verdict = guard.decide(event)
        if verdict and verdict[0] == "ask":
            return {"event": "ask_approved", "rule": rule(tool), "tool": tool}
    return None


def log_path(root, user=None):
    name = SAFE_NAME.sub("_", user or getpass.getuser()) or "unknown"
    return names.state_dir(root) / "usage" / (name + ".jsonl")


def record(root, line, session_id="", now=None):
    stamp = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    full = {"ts": stamp, "session": session_id}
    full.update(line)
    log_chain.append(log_path(root), full)


def record_off(root, now=None):
    """The one line a session start writes with the log off: its time and event log_off, no session or name."""
    stamp = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_chain.append(log_path(root), {"ts": stamp, "event": "log_off"})


def prune(root, now=None, days=None):
    """Rewrite this person's log without the entries older than days (SANVIO_KEEP_DAYS, 90 by default).
    The new file replaces the old in one step, so a reader never sees half a log."""
    path = log_path(root)
    if not path.is_file():
        return
    with log_chain.locked(path):
        _prune(path, now, days)


def _prune(path, now, days):
    """prune()'s rewrite, under the log's lock so no line is appended between the read and the replace.
    Only lines from the start go, so the chain from the first kept line on stays intact."""
    days = days or names.keep_days()
    cutoff = (now or datetime.datetime.now(datetime.timezone.utc)) - datetime.timedelta(days=days)
    kept = []
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        try:
            stamp = datetime.datetime.strptime(json.loads(line)["ts"], "%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, KeyError, TypeError):
            kept.append(line)  # a time it can't read: keep it rather than guess its age
            continue
        if stamp.replace(tzinfo=datetime.timezone.utc) >= cutoff:
            kept.append(line)
    part = path.with_name(path.name + ".part")
    part.write_text("".join(kept), encoding="utf-8")
    os.replace(part, path)


def main():
    try:
        event = json.load(sys.stdin)
        hook = event.get("hook_event_name", "")
        root = os.environ.get("CLAUDE_PROJECT_DIR") or str(HOOKS.parent.parent)
        if hook == "SessionStart":
            try:
                prune(root)
            except Exception:  # a log it can't rewrite is kept as it is
                pass
        if names.logging_off():
            if hook == "SessionStart":
                record_off(root)
            return 0
        line = entry(hook, event)
        if line:
            record(root, line, str(event.get("session_id", "")))
    except Exception:  # a broken log must never get in the way of the work
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
