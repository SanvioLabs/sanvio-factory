#!/usr/bin/env python3
"""Summarize your usage log for a sprint, as Markdown.

    python3 scripts/usage_report.py                    # the last 14 days
    python3 scripts/usage_report.py --since 2026-10-01
    python3 scripts/usage_report.py --previous reports/usage/<last report>.md
    python3 scripts/usage_report.py --review                   # the monthly log review

Reads your own log, .sanvio/usage/<you>.jsonl, written by
.claude/hooks/usage_log.py, and prints counts only: sessions, skills, agents,
slash commands, guard refusals and asks, and how many sessions started with
the log off. Nothing it prints names a file, a
prompt or a line of code, because the log never holds them. The
skills/factory-trends/ skill runs this and turns it into the report you share.

--review prints the monthly log review instead, for the 30 days to today: whether
your log's chain holds over the whole log (or that there's no log), how many
guard refusals and asks it has in those days, each ERROR and CLEANUP line in the
loop's .loop/loop.log as its date, issue and level only, and each day the loop
spent more than 3 times the median day with spend. A missing log is a line that
says so. It then writes today's date to .sanvio/usage/last-review, which the
factory dashboard shows. It never changes the logs it reads.
"""
import argparse
import datetime
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))
from log_chain import verify  # noqa: E402 (needs scripts/ on the path first)
from usage_log import log_path  # noqa: E402 (needs .claude/hooks/ on the path first)
import names  # noqa: E402 (same reason as log_chain)

REVIEW_DAYS = 30  # the days a log review covers, today included
SPIKE = 3  # a day's loop spend over this many times the median day's is listed
LOOP_LEVELS = ("ERROR", "CLEANUP")  # the loop.log steps a review lists
ISSUE = re.compile(r"^(?:#\d+|-)$")  # a loop.log line's second field: the issue, or - for none


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


def loop_lines(path, since, until):
    """Each ERROR and CLEANUP line in a loop.log from since to until, as "<YYYY-MM-DD> <#N or -> <LEVEL>", or
    None when the file can't be read. A loop line is "<iso time> <#N|-> <STEP> <text>"; the text, which can
    hold a path, a command or an error's words, is never kept, and a line that doesn't have that shape is skipped."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    out = []
    for raw in text.splitlines():
        parts = raw.split(" ", 3)
        if len(parts) < 3 or parts[2] not in LOOP_LEVELS or not ISSUE.match(parts[1]):
            continue
        try:
            day = datetime.date.fromisoformat(parts[0][:10]).isoformat()
        except ValueError:
            continue
        if since <= day <= until:
            out.append("{} {} {}".format(day, parts[1], parts[2]))
    return out


def spend_spikes(root, since, until):
    """[(day, dollars)] for each day from since to until whose loop spend is over SPIKE times the median day's.

    A day's spend is the cost_usd of the loop's runs picked up that day. Only days with spend count toward the
    median: with every empty day in it, the median would be $0 and every day with a run would be listed."""
    import token_report  # here, not at the top: token_report imports this module as it loads
    by_day = Counter()
    for runs in token_report.loop_runs(root, since).values():
        for entry in runs:
            cost = entry.get("cost_usd")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool) and entry["run_started"][:10] <= until:
                by_day[entry["run_started"][:10]] += cost
    spent = {day: cost for day, cost in by_day.items() if cost > 0}
    if not spent:
        return []
    middle = statistics.median(spent.values())
    return [(day, spent[day]) for day in sorted(spent) if spent[day] > SPIKE * middle]


def review(root, today, usage_path):
    """The monthly log review's text, for the REVIEW_DAYS days to today. It reads the logs and changes none of them."""
    since = (today - datetime.timedelta(days=REVIEW_DAYS - 1)).isoformat()
    until = today.isoformat()
    out = ["# Log review, {} to {}".format(since, until), ""]

    path = Path(usage_path)
    if path.is_file():
        # The whole log, as the report checks it: an edit before the period still means it was changed.
        chain = verify(path)
        if isinstance(chain, int):
            chain = "changed after it was written, from line {}".format(chain)
        elif chain == "unchained":
            chain = "unchained (no line carries a hash, as in a log written before chaining)"
        lines = [l for l in read(path, since) if str(l.get("ts", ""))[:10] <= until]
        out += ["Usage log chain: {}".format(chain), "",
                "Guard refusals: {}".format(sum(1 for l in lines if l.get("event") == "guard_deny")),
                "Guard asks: {}".format(sum(1 for l in lines if l.get("event") == "guard_ask")), ""]
    else:
        out += ["Usage log chain: missing", "",
                "No usage log, so no guard refusals or asks to count.", ""]

    out += ["## Loop errors and clean-ups", ""]
    found = loop_lines(Path(root) / ".loop" / "loop.log", since, until)
    if found is None:
        out += ["No loop log, so no loop errors or clean-ups to list.", ""]
    else:
        out += (found or ["None."]) + [""]

    out += ["## Days the loop spent over {} times the median day".format(SPIKE), ""]
    spikes = spend_spikes(root, since, until)
    out += ["{} ${:.2f}".format(day, cost) for day, cost in spikes] or ["None."]
    return "\n".join(out) + "\n"


def mark_reviewed(root, today):
    """Write today's date to .sanvio/usage/last-review, for the dashboard to show."""
    path = names.state_dir(root) / "usage" / "last-review"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(today.isoformat() + "\n", encoding="utf-8")


def since_date(text):
    """A --since value as YYYY-MM-DD, or an argparse error that says what to type."""
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD, e.g. 2026-10-01")


def main(argv=None, root=ROOT):
    today = datetime.date.today()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=since_date, default=(today - datetime.timedelta(days=14)).isoformat(),
                        help="the first day to count, as YYYY-MM-DD (default: 14 days ago)")
    parser.add_argument("--previous", help="your last report, to name the skills unused in both")
    parser.add_argument("--log", help="a log file other than your own")
    parser.add_argument("--review", action="store_true",
                        help="print the monthly log review of the last 30 days and record today as its date")
    args = parser.parse_args(argv)
    path = Path(args.log) if args.log else log_path(root)
    if args.review:
        # A missing log is something the review found, so it still counts as a review.
        print(review(root, today, path), end="")
        mark_reviewed(root, today)
        return 0
    if not path.exists():
        print("No usage log at {}. Is the hook wired in .claude/settings.json, and "
              "SANVIO_USAGE_LOG not set to off?".format(path), file=sys.stderr)
        return 1
    previous = earlier_unused(args.previous) if args.previous else None
    print(report(read(path, args.since), args.since, today.isoformat(), skills_here(root), previous))
    # The whole log, whatever --since says: an edit before the period still means it was changed.
    chain = verify(path)
    if isinstance(chain, int):
        print("Usage log changed after it was written, from line {}.".format(chain))
    return 0


if __name__ == "__main__":
    sys.exit(main())
