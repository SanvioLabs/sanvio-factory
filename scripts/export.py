#!/usr/bin/env python3
"""Bundle your loop and usage numbers into one JSON file, kept on this machine.

    python3 scripts/export.py                         # the last 14 days, printed
    python3 scripts/export.py --since 2026-10-01 --out reports/usage/export.json

The bundle holds:

- `v`, `exported`, `since`: the format version, today's date and the first day counted
- `user`: the same cleaned name your usage log's filename uses, so no new identifier
- `loop`: the lines of .loop/history.jsonl since that day, each rebuilt from the keys
  scripts/loop.py writes and nothing else. Only the factory's own loop: nothing under
  .loop/projects/ is read, and a line tagged with a project is dropped
- `usage`: counts from your usage log, .sanvio/usage/<you>.jsonl: sessions, then
  skills, agents and slash commands by name, guard refusals by rule, and guard asks
  and the asks you said yes to by tool (or by rule when there's no tool), and `log_off`,
  how many sessions started with SANVIO_USAGE_LOG=off

Nothing sends it. It only reads, prints or writes the one file you name. This shape is
the only one any later sender may send: anything not in it stays on this machine.
"""
import argparse
import datetime
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import usage_report  # noqa: E402 (needs scripts/ on the path first)
from usage_report import log_path  # noqa: E402 (same reason)

# The keys record_run in scripts/loop.py writes. Any other key on a history line is dropped.
LOOP_KEYS = ("v", "run", "issue", "project", "started", "ended", "outcome", "rounds",
             "tests", "verdicts", "tokens", "cost_usd", "agent", "reviewer")


def loop_runs(root, since):
    """The factory's own history lines that ended on or after `since`. Unreadable lines are skipped."""
    runs = []
    try:
        text = (Path(root) / ".loop" / "history.jsonl").read_text(encoding="utf-8")
    except OSError:
        return runs
    for raw in text.splitlines():
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(line, dict) or line.get("project") is not None:
            continue
        if str(line.get("ended", ""))[:10] < since:
            continue
        runs.append({key: line.get(key) for key in LOOP_KEYS})
    return runs


def by_tool(lines, kind):
    """How often each tool appears on lines of this event kind, by rule when a line has no tool, as report() keys them."""
    return Counter(l.get("tool") or l.get("rule", "") for l in lines if l.get("event") == kind)


def usage_counts(root, since):
    lines = usage_report.read(log_path(root), since)
    return {"sessions": len({l.get("session") for l in lines if l.get("session")}),
            "skills": dict(usage_report.count(lines, "skill", "name")),
            "agents": dict(usage_report.count(lines, "agent", "name")),
            "commands": dict(usage_report.count(lines, "command", "name")),
            "guard_deny": dict(usage_report.count(lines, "guard_deny", "rule")),
            "guard_ask": dict(by_tool(lines, "guard_ask")),
            "ask_approved": dict(by_tool(lines, "ask_approved")),
            "log_off": sum(1 for l in lines if l.get("event") == "log_off")}


def bundle(root, since, today):
    return {"v": 1, "exported": today, "since": since, "user": log_path(root).stem,
            "loop": loop_runs(root, since), "usage": usage_counts(root, since)}


def main(argv=None):
    today = datetime.date.today()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=usage_report.since_date,
                        default=(today - datetime.timedelta(days=14)).isoformat(),
                        help="the first day to count, as YYYY-MM-DD (default: 14 days ago)")
    parser.add_argument("--out", help="a file to write the bundle to, instead of printing it")
    args = parser.parse_args(argv)
    text = json.dumps(bundle(ROOT, args.since, today.isoformat()), indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
