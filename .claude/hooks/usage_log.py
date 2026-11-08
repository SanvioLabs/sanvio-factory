#!/usr/bin/env python3
"""Claude Code usage log: one line per harness event, kept on this machine.

Wired in .claude/settings.json on SessionStart, SessionEnd, UserPromptSubmit,
PreToolUse and PostToolUse. It records what the harness did, so whoever owns it
can see what people actually use: which skills and agents ran, which slash
commands, when the guard refused or asked, and when a person said yes to an ask.

It records names, never content. No prompts, no command arguments, no file
paths, no code. Each person's log is .sanvio/usage/<user>.jsonl, which is
gitignored. What reaches the team is the summary skills/factory-trends/ writes,
and the person reads that before it goes anywhere.

Turn it off for yourself with SANVIO_USAGE_LOG=off. It never blocks a tool
call, never prints, and never stops a session if it fails.
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
import names  # noqa: E402 (the state folder and the variables, old names included for a release)

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
    path = log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(full) + "\n")


def main():
    if names.env("USAGE_LOG").strip().lower() in ("off", "0", "false", "no"):
        return 0
    try:
        event = json.load(sys.stdin)
        line = entry(event.get("hook_event_name", ""), event)
        if line:
            root = os.environ.get("CLAUDE_PROJECT_DIR") or str(HOOKS.parent.parent)
            record(root, line, str(event.get("session_id", "")))
    except Exception:  # a broken log must never get in the way of the work
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
