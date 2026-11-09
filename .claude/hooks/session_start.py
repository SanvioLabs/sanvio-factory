#!/usr/bin/env python3
"""Claude Code session start: say what's not wired before any work starts.

Wired in .claude/settings.json as a SessionStart hook. Runs the same checks as
scripts/check_setup.py and stays silent when everything passes. When something
fails or needs a decision, it tells the person in one line and gives the agent
the detail, so the first reply can mention it.

The failure it exists for: a pre-commit hook that never runs because one git
config line was unset, and nothing ever says so.

It also moves .harness/ to .sanvio/ once, when that's all there is, and says so
that one time: the state folder's new name, with any live factory runs in it.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def report(results):
    """The hook's JSON for these check results, or None when there's nothing to say."""
    open_items = [(status, line, fix) for status, line, fix in results if status != "PASS"]
    if not open_items:
        return None
    failed = [line for status, line, _ in open_items if status == "FAIL"]
    headline = failed[0] if failed else open_items[0][1]
    more = len(open_items) - 1
    message = "[setup] {}{}. Run /orientation or python3 scripts/check_setup.py".format(
        headline, " (+{} more)".format(more) if more else "")
    detail = "\n".join("{} {}{}".format(status, line, "\n  {}: {}".format(
        "fix" if status == "FAIL" else "note", fix) if fix else "") for status, line, fix in open_items)
    return {
        "systemMessage": message,
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "The setup check found these at session start. Mention any FAIL "
                                 "in your first reply, with its fix, and don't run the fix "
                                 "yourself:\n" + detail,
        },
    }


def startup(root):
    """Move .harness/ to .sanvio/ if that's all there is, then the checks' JSON for this root, or None."""
    import check_setup
    import names
    moved = names.move_old_state(root)
    results = check_setup.run(root)
    if moved and not moved.startswith("both "):  # check_old_names already names both folders
        results.insert(0, ("WARN", "names: " + moved, None))  # a move is said once: the next session has none
    return report(results)


def main():
    try:
        payload = startup(ROOT)
    except Exception as error:  # a broken check must never stop a session from starting
        payload = {"systemMessage": "[setup] the session-start check failed to run: {}".format(error)}
    if payload:
        print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
