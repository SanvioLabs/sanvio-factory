#!/usr/bin/env python3
"""Summarize your usage log for a sprint, as Markdown.

    python3 scripts/usage_report.py                    # the last 14 days
    python3 scripts/usage_report.py --since 2026-10-01
    python3 scripts/usage_report.py --previous reports/usage/<last report>.md

Reads your own log, .sanvio/usage/<you>.jsonl, written by
.claude/hooks/usage_log.py, and prints counts only: sessions, skills, agents,
slash commands, guard refusals and asks, and how many sessions started with
the log off. Nothing it prints names a file, a
prompt or a line of code, because the log never holds them. The
skills/factory-trends/ skill runs this and turns it into the report you share.
"""
import argparse
import datetime
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))
from log_chain import verify  # noqa: E402 (needs scripts/ on the path first)
from usage_log import log_path  # noqa: E402 (needs .claude/hooks/ on the path first)


def read(path, since):
    """Every log line on or after `since` (a YYYY-MM-DD string). Unreadable lines are skipped."""
    lines = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return lines
    for raw in text.splitlines():
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        if isinstance(line, dict) and str(line.get("ts", ""))[:10] >= since:
            lines.append(line)
    return lines


def skills_here(root):
    return sorted(p.parent.name for p in (Path(root) / "skills").glob("*/SKILL.md"))


def table(counter, header):
    if not counter:
        return ["None.", ""]
    out = ["| {} | Times |".format(header), "|---|---|"]
    out += ["| `{}` | {} |".format(name, n) for name, n in counter.most_common()]
    return out + [""]


def count(lines, kind, key):
    """How often each value of `key` appears on lines of this event kind."""
    return Counter(l.get(key, "") for l in lines if l.get("event") == kind)


def earlier_unused(path):
    """The skills on an earlier report's `Never used here:` line, or None if it can't be read or has none."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("Never used here:"):
            return re.findall(r"`([^`]+)`", line)
    return None


def report(lines, since, until, available, previous_unused=None):
    skills = count(lines, "skill", "name")
    sessions = len({l.get("session") for l in lines if l.get("session")})
    asks = Counter(l.get("tool") or l.get("rule", "") for l in lines if l.get("event") == "guard_ask")
    approved = Counter(l.get("tool") or l.get("rule", "") for l in lines if l.get("event") == "ask_approved")
    # A skill typed as /review-pr arrives as a command, not a Skill call, so both count as used.
    used = set(skills) | set(count(lines, "command", "name"))
    unused = [name for name in available if name not in used]
    # With SANVIO_USAGE_LOG=off, each session start writes one log_off line and nothing else.
    off = sum(1 for l in lines if l.get("event") == "log_off")

    out = ["# Harness usage, {} to {}".format(since, until), "", "Sessions: {}".format(sessions), ""]
    if off:
        out += ["Usage log off for {} sessions.".format(off), ""]
    out += ["## Skills", ""]
    out += table(skills, "Skill")
    out += ["Never used here: {}".format(", ".join("`{}`".format(n) for n in unused) if unused else "none"), ""]
    if previous_unused is not None:
        again = [n for n in unused if n in previous_unused]
        out += ["Unused two sprints running: {}".format(", ".join("`{}`".format(n) for n in again) if again else "none"), ""]
    out += ["## Agents", ""] + table(count(lines, "agent", "name"), "Agent")
    out += ["## Slash commands", ""] + table(count(lines, "command", "name"), "Command")
    out += ["## Guard refusals", ""] + table(count(lines, "guard_deny", "rule"), "Rule")
    out += ["## Guard asks", ""]
    if asks:
        out += ["| Tool | Asked | Said yes |", "|---|---|---|"]
        out += ["| `{}` | {} | {} |".format(name, n, approved.get(name, 0)) for name, n in asks.most_common()]
        out.append("")
    else:
        out += ["None.", ""]
    return "\n".join(out)


def since_date(text):
    """A --since value as YYYY-MM-DD, or an argparse error that says what to type."""
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD, e.g. 2026-10-01")


def main(argv=None):
    today = datetime.date.today()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=since_date, default=(today - datetime.timedelta(days=14)).isoformat(),
                        help="the first day to count, as YYYY-MM-DD (default: 14 days ago)")
    parser.add_argument("--previous", help="your last report, to name the skills unused in both")
    parser.add_argument("--log", help="a log file other than your own")
    args = parser.parse_args(argv)
    path = Path(args.log) if args.log else log_path(ROOT)
    if not path.exists():
        print("No usage log at {}. Is the hook wired in .claude/settings.json, and "
              "SANVIO_USAGE_LOG not set to off?".format(path), file=sys.stderr)
        return 1
    previous = earlier_unused(args.previous) if args.previous else None
    print(report(read(path, args.since), args.since, today.isoformat(), skills_here(ROOT), previous))
    # The whole log, whatever --since says: an edit before the period still means it was changed.
    chain = verify(path)
    if isinstance(chain, int):
        print("Usage log changed after it was written, from line {}.".format(chain))
    return 0


if __name__ == "__main__":
    sys.exit(main())
