#!/usr/bin/env python3
"""The numbers the factory dashboard shows, as JSON.

    python3 scripts/dashboard_data.py --json                    # the last 14 days
    python3 scripts/dashboard_data.py --json --since 2026-10-01

--json is the only output, and the script refuses to run without it. It prints one object:

    schema           the document's shape, an integer. It goes up when a section's shape changes in a
                     way an older pane would misread. Adding a field doesn't change it. Its versions:
                         1  the first shape
                         2  conversations' first side is "factory", where 1 called it "harness"
    generated        when it ran, an ISO time with the local offset
    since            the first day counted
    loop_spend       tokens and estimated dollars from the loop's .loop/**/usage.json records: today,
                     the last 7 days and since --since, each keyed on when the loop picked the issue
                     up, then the --since totals by issue, step and model. A run that recorded no
                     model is under "null". cost_per_pr is, over the issues that ran since --since
                     and are in status.json, their cost over how many have a pull request,
                     or null when none has one. by_day lists every day from --since to today, oldest
                     first, each with its tokens and cost_usd, 0 and 0.0 on a day with no run, and
                     cost_usd null on a day whose runs recorded no cost. run_started is local time,
                     so a run dated after today only comes from a wrong clock: it counts in since
                     but has no day. first_run is the earliest day a run counted since --since
                     started, or null
    loop_throughput  the issues in .loop/status.json and each project's: how many are in each
                     state, each one's round, and how many took more than one
    activity         your usage log, .sanvio/usage/<you>.jsonl, since --since: skills, agents and
                     slash commands by name, guard refusals by rule, and how many times it asked.
                     chain is "intact", "unchained" (no line carries prev, as in a log written before
                     chaining), or the line number from which the log was changed after it was
                     written. It comes from scripts/log_chain.py's verify() over the whole log,
                     whatever --since says. skill_spend, agent_spend and command_spend hold each
                     name's tokens and estimated cost_usd, from token_report.py's split of the transcripts in ~/.claude/projects for
                     sessions started at the factory's root, including after they move into projects/. A
                     session started under projects/ isn't counted. A name there needn't match the counts: a
                     subagent's are measured, a skill's or command's attributed from where it started to
                     the next prompt. cost_usd prices each model's tokens at .sanvio/prices.json's
                     dollars per million tokens (scripts/prices.example.json has the shape), and is
                     null when a model with tokens has no price. unpriced names those models, each with
                     why: "no prices.json", "unreadable" or "not in prices.json". prices_checked is
                     that file's "checked" date, or null when it isn't a date, and spend_at when the
                     transcripts were read. The split is kept in .sanvio/cache/activity.json, only
                     names, models and counts, and read again when it's over 15 minutes old or --since
                     changes; prices are read every run. With no transcripts folder, or a loop.json or
                     transcript that stops the read, these fields are left out and the counts stay
    evals            the newest file in .sanvio/evals/ for each reviewer: when it was saved, how
                     many cases were stable, flaky and failing, and the failing cases' names. stale
                     is true when a file the result rests on changed after it was saved: the agent's
                     file in agents/, scripts/eval_agents.py, or a case's case.json, work file or
                     brief. A file changed when its last commit is later than saved, or when it has
                     uncommitted changes, or git ignores it, and it was written later. A file that
                     doesn't exist and was never committed can't count. changed lists those files from the factory
                     root, and newest_change is the latest of their dates. A result with no saved
                     time or no cases in its folder is stale with a why, and one git can't check
                     has stale null with a why
    conversations    Claude Code's tokens since --since from ~/.claude/projects, counted as
                     token_report.py counts them: "factory" for conversations at the root and in
                     projects/, "loop" for the loop's worktrees, each by model (input, output, cache
                     writes, cache reads and total) with how many sessions, and by_day, every day
                     from --since to today, oldest first, the same days as loop_spend's, with its
                     total tokens, 0 on a day with no reply. A reply's day there is local time, as a
                     loop run's is, so the evening stays on its own day; --since and by_model go by
                     the transcript's UTC date, as token_report.py does, so west of UTC a reply on
                     the evening before --since counts in by_model but has no day. What each
                     transcript held is kept in .sanvio/cache/conversations-2.json and read again
                     only when the file's size or time changes: per reply, its message and request
                     ids, UTC day, side, model, session id, local day and counts, under the
                     transcript's path, and nothing else
    waiting          what's waiting on you, in two halves that each fail on their own: pull_requests,
                     this repo's open pull requests from gh, each with its title, when it
                     opened, hours waited, its loop issue if its branch is loop/issue-N, whether it's
                     a draft, its checks (pass, fail, pending, or null with none) and whether it
                     conflicts (null while GitHub doesn't know); and blocked, the issues in
                     status.json whose state is blocked, each with its title, note and last update
    loop_rework      the loop's pull requests (branch loop/issue-N) merged since --since, read through
                     gh: how many, how many gained a commit without the loop's "Loop: issue #" line,
                     and each of those with its number, title, merges from main and other commits.
                     A pull request's commits are cached in .sanvio/cache/loop_rework.json, so
                     each is asked for once
    stage_times      how long the loop's work spends at each stage, in two halves that each fail on their
                     own, and the slowest stage. loop_steps reads .loop/status.json and each project's,
                     keeps the issues whose `started` date is on or after --since, and for each of SHAPE,
                     BUILD, VALIDATE and SCALE gives median_minutes, the median of the issues'
                     step_seconds for it in minutes to 1 decimal, and issues, how many it covers. An
                     issue whose step_seconds has no number for a step doesn't count in that step, and
                     median_minutes is null when no issue does.
                     status.json keeps only the loop's 20 most recent issues (STATUS_KEEP), so the loop-step medians cover those whatever --since says, the same limit cost_per_pr has.
                     pull_requests asks gh for the merged pull requests, its own call apart from
                     loop_rework's, and keeps the loop's (branch loop/issue-N) merged since --since:
                     merged and median_hours_to_merge, from opened to merged, then reviewed and
                     median_hours_to_first_review, from opened to the earliest review by anyone other
                     than the pull request's author. Hours are to 1 decimal, a median is null when it
                     covers none, and a pull request whose times can't be read isn't counted. slowest
                     is the stage with the largest median, compared in minutes, among those with 3 or
                     more behind it: SHAPE, BUILD, VALIDATE, SCALE, first_review or merge, or null when
                     none has 3. Why values: loop_steps' are status.json's, "no status.json" and
                     "unreadable", and pull_requests' is "gh failed". It prints no title, login or address
    loop_history     every loop run that ended since --since, from .loop/history.jsonl and each
                     .loop/projects/*/history.jsonl, as runs, by_day, by_outcome and skipped_lines.
                     It keys on `ended`, where loop_spend keys on when the loop picked the issue up.
                     A run counts when the date of its `ended`, its first 10 characters, is on or after `--since`.
                     runs is sorted by the whole of ended, and each holds only its own fields.
                     Run fields: `issue`, `started`, `ended`, `outcome`, `rounds`, `tests`, `verdicts`, `tokens` and `cost_usd`. Nothing else goes in.
                     Issue names: `issue-N` for this repo and `<name>/issue-N` for a project.
                     The name is the project's folder, and issue is null when the line's isn't a whole
                     number. rounds, tokens and cost_usd are null when they aren't numbers, started
                     and outcome when they aren't text, tests and verdicts when they aren't lists of
                     text. by_day lists every day from --since to today, oldest first, the same days as
                     loop_spend's, each with its runs, pr, blocked, stopped, skipped and
                     more_than_one_round, 0 on a day with none.
                     A run ending after today counts in `runs` and `by_outcome` but has no day.
                     `by_outcome` has `pr`, `blocked`, `stopped` and `skipped`, every key always present.
                     Any other outcome counts only in runs and its day's runs. skipped_lines counts
                     the lines left out, whatever their date: not a JSON object (NaN and Infinity
                     aren't JSON, and a blank line isn't an object), v not the integer 1, or ended
                     not a string of 10 or more characters. A file that can't be read doesn't stop
                     the others.
                     Why values: `{"value": null, "why": "no run history"}` and `"unreadable"`.
                     The first is for no files and the second for none that can be read. It prints no
                     title, note, link, path or command name
    work_by_type     this repo's pull requests merged since --since, by type, and what the loop spent on
                     the issues they close. It reads them through work_report.py's GraphQL search, one gh
                     call of up to SEARCH_TIMEOUT seconds, and types each as that script does: the first
                     of bug, enhancement, documentation and chore among its own labels, else among its
                     closed issues', else null. types has one row for each of those, then null, every row
                     always present: merged, loop_built (its branch is loop/issue-N), issues (how many
                     different issues its pull requests close), and tokens and cost_usd, the totals over
                     those issues' issue-N usage.json records on every date, since work merged in the
                     period was often started before it. A person's pull request counts its issues too.
                     A type whose issues have no loop records has tokens 0 and cost_usd 0.0, and cost_usd
                     is null when none of their records has a cost. A project's issue-N isn't this repo's.
                     truncated is true when the search matched more than the 1000 it returns, and then
                     the counts are low. Why values are work_report.py's: "gh unavailable" and "GitHub's
                     search returned a page it couldn't read". It prints no title, author, login or address

A section whose source is missing or can't be read is {"value": null, "why": ...}, and the why names
the kind of problem, never a path or an error's text. The script still exits 0. status.json keeps
only the loop's 20 most recent issues, so throughput covers those whatever --since says, and
cost_per_pr leaves out an issue that ran in the period but has dropped off the list. loop_rework and
stage_times read the 200 most recently merged pull requests, and work_by_type the first 1000 its search
matches, so a --since far enough back can undercount them. Titles appear only under waiting and loop_rework, and notes only under waiting, printed as they
were written, so they hold whatever was typed into them. Nowhere else does it print a title or a note:
stage_times reads the same status.json and pull requests and prints none. Nowhere does it add a pull
request's address, a pull request's or review's author, a prompt, a commit's message or author, an eval's reasons or a
file path other than those in changed, which are from the harness root: counts, dollars, dates, issue
names, step, model, skill, agent, rule and case names, and a run's outcome, tests and verdicts. The dollars are the loop's estimate at API
prices, or under activity an estimate at the prices in .sanvio/prices.json, not what was billed.
"""
import argparse
import contextlib
import datetime
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import token_report  # noqa: E402 (needs scripts/ on the path first)
from eval_agents import load_cases  # noqa: E402 (same reason)
from log_chain import verify  # noqa: E402 (same reason)
from loop import USAGE_TOKENS, usage_totals  # noqa: E402 (same reason)
from token_report import group, loop_dirs, loop_runs, natural, read_file, tokens, usage_files  # noqa: E402 (same reason)
from usage_report import count, log_path, read, since_date  # noqa: E402 (same reason)
import names  # noqa: E402 (same reason)

SCHEMA = 2  # the document's shape; see "schema" above
WEEK = 7  # days in the last-7-days window, today included
TRANSCRIPTS = Path.home() / ".claude" / "projects"
CACHE = Path("cache") / "conversations-2.json"  # each of these under names.state_dir()
SAVE_EVERY = 50  # transcripts read between saves of the conversations cache
SIDES = {"Conversations": "factory", "projects/": "factory", "Loop": "loop"}  # token_report's groups, two sides
COUNTS = ("input", "output", "cache_writes", "cache_reads")  # token_report's FIELDS, in order
GH_TIMEOUT = 30  # seconds before a gh call counts as unavailable
PR_FIELDS = "number,title,createdAt,headRefName,isDraft,statusCheckRollup,mergeable"
FAILED = {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}
LOOP_BRANCH = re.compile(r"^loop/issue-(\d+)$")
REWORK_CACHE = Path("cache") / "loop_rework.json"
BASE_MERGES = ("Merge branch 'main'", "Merge remote-tracking branch 'origin/main'")
ACTIVITY_CACHE = Path("cache") / "activity.json"
ACTIVITY_KEEP = datetime.timedelta(minutes=15)  # how long a read of the transcripts is used again
PRICES = Path("prices.json")
PRICED_TOKENS = 1_000_000  # prices.json's figures are dollars for this many tokens
SPEND_FIELDS = {"skills": "skill_spend", "agents": "agent_spend", "commands": "command_spend"}
OUTCOMES = ("pr", "blocked", "stopped", "skipped")  # the states a run ends in; see record_run in loop.py
STAGE_STEPS = ("SHAPE", "BUILD", "VALIDATE", "SCALE")  # the loop's steps stage_times takes medians of
STAGE_PR_FIELDS = "number,headRefName,author,createdAt,mergedAt,reviews"
SLOWEST_AT = 3  # how many a stage's median needs behind it before it can be named slowest


def missing(why):
    return {"value": None, "why": why}


def number(value):
    """value when it's an int or float that isn't a bool, else None."""
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def totals(entries):
    """{tokens, cost_usd} over usage.json entries, reading only the numbers in them, each None when no entry had one."""
    tokens, cost = usage_totals([{name: number(e.get(name)) for name in USAGE_TOKENS + ("cost_usd",)} for e in entries])
    return {"tokens": tokens, "cost_usd": None if cost is None else round(cost, 4)}


def days(since, today):
    """Every YYYY-MM-DD from since to today, oldest first."""
    first = datetime.date.fromisoformat(since)
    return [(first + datetime.timedelta(days=n)).isoformat() for n in range((today - first).days + 1)]


def readable(path):
    try:
        return isinstance(json.loads(path.read_text()), list)
    except (OSError, ValueError):
        return False


def status_rows(root):
    """({issue: row}, None) from .loop/status.json and each project's, or (None, why) when none can be read.

    Issues are named as loop_runs() names them: issue-N for this repo, <name>/issue-N for a project.
    """
    state = Path(root) / ".loop"
    paths = [("", state / "status.json")]
    paths += [(p.parent.name + "/", p) for p in sorted(state.glob("projects/*/status.json"))]
    paths = [(prefix, path) for prefix, path in paths if path.is_file()]
    if not paths:
        return None, "no status.json"
    rows, read_any = {}, False
    for prefix, path in paths:
        try:
            found = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(found, dict) or not isinstance(found.get("issues"), list):
            continue
        read_any = True
        for row in found["issues"]:
            if isinstance(row, dict) and isinstance(number(row.get("number")), int):
                rows["{}issue-{}".format(prefix, row["number"])] = row
    return (rows, None) if read_any else (None, "unreadable")


def loop_spend(root, since, today):
    files = usage_files(root)
    if not files:
        return missing("no loop records")
    day, week = today.isoformat(), (today - datetime.timedelta(days=WEEK - 1)).isoformat()
    runs = loop_runs(root, min(since, week))
    if not runs and not any(readable(path) for _, path in files):
        return missing("unreadable")
    every = [(issue, e) for issue, entries in runs.items() for e in entries]
    counted = [(issue, e) for issue, e in every if e["run_started"][:10] >= since]

    def by(key):
        groups = {}
        for issue, e in counted:
            groups.setdefault(key(issue, e), []).append(e)
        return {name: totals(groups[name]) for name in sorted(groups, key=natural)}

    def named(value):
        return value if isinstance(value, str) and value else "null"

    out = {"today": totals([e for _, e in every if e["run_started"][:10] == day]),
           "last_7_days": totals([e for _, e in every if e["run_started"][:10] >= week]),
           "since": totals([e for _, e in counted]),
           "by_issue": by(lambda issue, e: issue),
           "by_step": by(lambda issue, e: named(e.get("step"))),
           "by_model": by(lambda issue, e: named(e.get("model")))}
    for name, value in out["by_model"].items():
        value["label"] = "model not recorded" if name == "null" else name
    on = {}
    for _, e in counted:
        on.setdefault(e["run_started"][:10], []).append(e)
    out["by_day"] = [dict(day=d, **(totals(on[d]) if d in on else {"tokens": 0, "cost_usd": 0.0}))
                     for d in days(since, today)]
    out["first_run"] = min((e["run_started"][:10] for _, e in counted), default=None)
    # Both sides over the same issues: ones that ran in the period and status.json still lists.
    rows = status_rows(root)[0] or {}
    tracked = {issue for issue in out["by_issue"] if issue in rows}
    prs = sum(1 for issue in tracked if rows[issue].get("pr"))
    cost = totals([e for issue, e in counted if issue in tracked])["cost_usd"]
    out["cost_per_pr"] = round(cost / prs, 4) if prs and cost is not None else None
    return out


def loop_throughput(root):
    rows, why = status_rows(root)
    if rows is None:
        return missing(why)
    states = Counter(row["state"] if isinstance(row.get("state"), str) and row["state"] else "unknown"
                     for row in rows.values())
    rounds = {name: number(rows[name].get("round")) or 0 for name in sorted(rows, key=natural)}
    return {"issues": len(rows), "by_state": dict(states.most_common()), "rounds": rounds,
            "more_than_one_round": sum(1 for n in rounds.values() if n > 1)}


def activity(root, since):
    path = log_path(root)
    if not path.is_file():
        return missing("no usage log")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return missing("unreadable")
    if text.strip() and not read(path, ""):
        return missing("unreadable")
    # The hook writes strings; a line with anything else in these fields can't be counted by name.
    lines = [l for l in read(path, since) if all(isinstance(l.get(k, ""), str) for k in ("event", "name", "rule"))]
    return {"skills": dict(count(lines, "skill", "name").most_common()),
            "agents": dict(count(lines, "agent", "name").most_common()),
            "commands": dict(count(lines, "command", "name").most_common()),
            "guard_refusals": dict(count(lines, "guard_deny", "rule").most_common()),
            "asks": sum(1 for l in lines if l.get("event") == "guard_ask"),
            "chain": verify(path)}


def git(root, *args):
    """git's output run in root, or None when git isn't there or fails."""
    try:
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


def when(text):
    """text as an aware datetime, a time without an offset taken as local, or None when it isn't one.

    A trailing Z, which some versions of git print for UTC, becomes +00:00: fromisoformat() before
    Python 3.11 refuses it."""
    try:
        found = datetime.datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except (AttributeError, TypeError, ValueError):
        return None
    return found if found.tzinfo else found.astimezone()


def freshness(root, result):
    """{stale, changed, newest_change} for a saved result, with a why when it can't say from the files.

    The files are the agent's, eval_agents.py, and each case's case.json, work file and brief. One counts
    as changed when its date is later than "saved": its last commit's, or for one with uncommitted
    changes or that git ignores, when it was last written. One that doesn't exist and was never
    committed has no date, so it can't count as changed."""
    root = Path(root).resolve()
    unknown = {"stale": True, "changed": [], "newest_change": None}
    saved = when(result.get("saved"))
    if saved is None:
        return dict(unknown, why="no saved time")
    folder = result.get("folder")
    try:
        cases = load_cases(root / folder) if isinstance(folder, str) and folder else []
    except (OSError, ValueError, TypeError, AttributeError):
        cases = []
    if not cases:
        return dict(unknown, why="folder missing")
    reviewer = result.get("reviewer")
    files = [root / "agents" / (reviewer + ".md")] if isinstance(reviewer, str) and reviewer else []
    files.append(root / "scripts" / "eval_agents.py")
    for case in cases:
        files += [case["folder"] / "case.json", case["work"]]
        if isinstance(case.get("brief"), str) and case["brief"]:
            files.append(root / case["brief"])
    paths = []
    for path in files:
        try:
            name = path.resolve().relative_to(root).as_posix()
        except ValueError:
            continue  # outside this repo: git here can't date it, and its path isn't printed
        if name not in paths:
            paths.append(name)
    prefix = git(root, "rev-parse", "--show-prefix")
    status = git(root, "status", "--porcelain", "-z", "--untracked-files=all", "--ignored", "--", *paths)
    # Newest commit first, each as a NUL, its date, then the names it touched, one per line.
    log = git(root, "-c", "core.quotePath=false", "log", "--format=%x00%cI", "--name-only", "--", *paths)
    if prefix is None or status is None or log is None:
        return dict(unknown, stale=None, why="no git")
    # Status and log name files from the repository's top, so the prefix comes off to match paths. A
    # rename or copy in status is followed by a field holding the old name, which is skipped.
    top, dirty = prefix.strip(), set()
    fields = iter(status.split("\0"))
    for field in fields:
        if "R" in field[:2] or "C" in field[:2]:
            next(fields, None)
        if field[3:].startswith(top):
            dirty.add(field[3 + len(top):])
    dates = {}
    for name in dirty & set(paths):
        try:
            dates[name] = datetime.datetime.fromtimestamp((root / name).stat().st_mtime).astimezone()
        except OSError:
            dates[name] = datetime.datetime.now().astimezone()  # deleted, so changed by now
    for entry in log.split("\0")[1:]:
        lines = [line for line in entry.split("\n") if line]
        date = when(lines[0]) if lines else None
        for line in lines[1:]:
            name = line[len(top):] if line.startswith(top) else None
            if date and name in paths and name not in dates:
                dates[name] = date  # the first commit seen is the newest
    changed = sorted(name for name, date in dates.items() if date > saved)
    return {"stale": bool(changed), "changed": changed,
            "newest_change": max(dates[name] for name in changed).isoformat(timespec="seconds") if changed else None}


def evals(root):
    """The newest saved result for each reviewer. The same loop as eval_agents.latest(): names start with
    the time they were saved, so name order newest first, matched on the "reviewer" field, not the name.
    It's repeated here because latest() reads this repo's own folder and finds one reviewer's file."""
    paths = sorted((names.state_dir(root) / "evals").glob("*.json"), reverse=True)
    if not paths:
        return missing("no saved evals")
    out = {}
    for path in paths:
        try:
            found = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(found, dict) or not isinstance(found.get("cases"), dict):
            continue
        reviewer = found.get("reviewer")
        if not isinstance(reviewer, str) or not reviewer or reviewer in out:
            continue
        statuses = {name: case.get("status") if isinstance(case, dict) else None
                    for name, case in found["cases"].items()}
        out[reviewer] = {"saved": found["saved"] if isinstance(found.get("saved"), str) else None,
                         "stable": sum(1 for s in statuses.values() if s == "stable"),
                         "flaky": sum(1 for s in statuses.values() if s == "flaky"),
                         "failing": sum(1 for s in statuses.values() if s == "failing"),
                         "failing_cases": sorted(name for name, s in statuses.items() if s == "failing"),
                         **freshness(root, found)}
    return {name: out[name] for name in sorted(out)} if out else missing("unreadable")


def checks(rollup):
    """fail if any check failed, else pending if any hasn't finished, else pass; None with no checks.

    gh mixes two shapes: a check run has status and conclusion ("" until it ends), a commit status has state.
    """
    found = [c for c in rollup if isinstance(c, dict)] if isinstance(rollup, list) else []
    if not found:
        return None
    ends = [c.get("conclusion") or c.get("state") for c in found]
    if any(end in FAILED for end in ends):
        return "fail"
    if any(c.get("status", "COMPLETED") != "COMPLETED" or end in ("PENDING", "EXPECTED") or not end
           for c, end in zip(found, ends)):
        return "pending"
    return "pass"


def hours_since(opened, now):
    try:
        then = datetime.datetime.fromisoformat(opened.replace("Z", "+00:00"))
        return round((now - then).total_seconds() / 3600, 1)
    except (AttributeError, TypeError, ValueError):
        return None


def pull_requests(root, now):
    try:
        done = subprocess.run(["gh", "pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS],
                              cwd=root, capture_output=True, text=True, timeout=GH_TIMEOUT)
        found = json.loads(done.stdout) if done.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        found = None
    if not isinstance(found, list):
        return missing("gh unavailable")
    out = []
    for pr in found:
        if not isinstance(pr, dict):
            continue
        opened = pr.get("createdAt") if isinstance(pr.get("createdAt"), str) else None
        branch = LOOP_BRANCH.match(pr["headRefName"]) if isinstance(pr.get("headRefName"), str) else None
        out.append({"number": number(pr.get("number")),
                    "title": pr["title"] if isinstance(pr.get("title"), str) else None,
                    "opened": opened,
                    "hours_waited": hours_since(opened, now),
                    "loop_issue": int(branch.group(1)) if branch else None,
                    "draft": pr["isDraft"] if isinstance(pr.get("isDraft"), bool) else None,
                    "checks": checks(pr.get("statusCheckRollup")),
                    "conflicts": {"CONFLICTING": True, "MERGEABLE": False}.get(pr.get("mergeable"))})
    return out


def blocked(root):
    rows, why = status_rows(root)
    if rows is None:
        return missing(why)

    def text(row, name):
        return row[name] if isinstance(row.get(name), str) else None

    return [{"issue": name, "number": rows[name]["number"], "title": text(rows[name], "title"),
             "note": text(rows[name], "note"), "updated": text(rows[name], "updated")}
            for name in sorted(rows, key=natural) if rows[name].get("state") == "blocked"]


def waiting(root, now):
    return {"pull_requests": pull_requests(root, now), "blocked": blocked(root)}


def text_or_none(value):
    return value if isinstance(value, str) and value else None


def replies(entries, root, loop):
    """One record per reply in a transcript's entries, for the cache, leaving out replies outside this repo:
    [message id, request id, UTC day, side, model, session id, local day, input, output, cache writes,
    cache reads]. The UTC day is the transcript's own, which --since and dedup go by; the local day is
    the one by_day counts under, and is the UTC day when the timestamp can't be read.

    A reply written as several lines keeps only its first line for each day. read() keeps the first line
    on or after its since date, so that's the same line whatever the date.
    """
    out, kept, sides = [], set(), {}
    for entry in entries:
        cwd = text_or_none(entry.get("cwd"))
        if cwd not in sides:
            found = group(entry, root, loop)
            sides[cwd] = SIDES[found[0]] if found else None
        if sides[cwd] is None:
            continue
        message = entry["message"]
        stamp = str(entry.get("timestamp", ""))
        at = when(stamp)
        record = [text_or_none(message.get("id")), text_or_none(entry.get("requestId")), stamp[:10], sides[cwd],
                  text_or_none(message.get("model")) or "unknown", text_or_none(entry.get("sessionId")),
                  at.astimezone().date().isoformat() if at else stamp[:10]] + tokens(entry)
        if record[:2] != [None, None]:
            if tuple(record[:3]) in kept:
                continue
            kept.add(tuple(record[:3]))
        out.append(record)
    return out


def whole(n):
    return isinstance(n, int) and not isinstance(n, bool) and n >= 0


def cached(entry):
    """True when a cache entry has the shape conversations() writes."""
    if not isinstance(entry, dict) or not whole(entry.get("size")) or not whole(entry.get("mtime_ns")):
        return False
    records = entry.get("replies")
    return isinstance(records, list) and all(
        isinstance(r, list) and len(r) == 7 + len(COUNTS) and all(v is None or isinstance(v, str) for v in r[:2])
        and isinstance(r[2], str) and r[3] in SIDES.values() and isinstance(r[4], str)
        and (r[5] is None or isinstance(r[5], str)) and isinstance(r[6], str) and all(whole(n) for n in r[7:])
        for r in records)


def save(path, data):
    """Write data as JSON through a temporary file beside path, so a reader never sees half of it.
    A cache that can't be written is left as it was."""
    path, temp = Path(path), None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=path.name + ".", suffix=".tmp",
                                         delete=False, encoding="utf-8") as handle:
            temp = handle.name
            json.dump(data, handle, separators=(",", ":"))
        os.replace(temp, path)
    except OSError:
        if temp:
            with contextlib.suppress(OSError):
                os.unlink(temp)


def conversations(root, since, today, projects_dir, cache_path):
    """Tokens since `since` in the transcripts under projects_dir, by side and model, the way token_report.py
    counts them: each reply once, the first copy in path order, judged by the folder it ran in.

    A transcript whose size and time match its cache entry isn't read again. The cache drops transcripts
    that are gone, and one that can't be read or isn't the right shape is rebuilt. The cache is saved as
    the read goes, so a read stopped part way keeps what it read, and isn't rewritten when nothing changed.
    """
    projects_dir = Path(projects_dir)
    if not projects_dir.is_dir():
        return missing("no transcripts")
    try:
        loop = loop_dirs(root)
    except (OSError, ValueError):
        return missing("unreadable")
    try:
        cache = json.loads(Path(cache_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    if not isinstance(cache, dict):
        cache = {}
    fresh, read = {}, 0
    for path in sorted(projects_dir.rglob("*.jsonl")):
        try:
            stat = path.stat()  # before the read, so a file that grows during it is read again next time
            entry = cache.get(str(path))
            stale = not (cached(entry) and entry["size"] == stat.st_size and entry["mtime_ns"] == stat.st_mtime_ns)
            if stale:
                entry = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                         "replies": replies(read_file(path, False), root, loop)}
        except OSError:
            continue
        fresh[str(path)] = entry
        read += stale
        if stale and read % SAVE_EVERY == 0:
            save(cache_path, {**cache, **fresh})  # keep the entries this read hasn't reached yet
    if read or fresh.keys() != cache.keys():
        save(cache_path, fresh)

    by_model = {"factory": {}, "loop": {}}
    sessions = {"factory": set(), "loop": set()}
    by_day = {side: dict.fromkeys(days(since, today), 0) for side in ("factory", "loop")}
    seen = set()
    for entry in fresh.values():
        for message_id, request_id, day, side, model, session, local, *counts in entry["replies"]:
            if day < since:
                continue
            if (message_id, request_id) != (None, None):
                if (message_id, request_id) in seen:
                    continue
                seen.add((message_id, request_id))
            by_model[side][model] = [a + b for a, b in zip(by_model[side].get(model, [0] * len(COUNTS)), counts)]
            if local in by_day[side]:
                by_day[side][local] += sum(counts)
            if session:
                sessions[side].add(session)
    return {side: {"by_model": {model: dict(zip(COUNTS, values), total=sum(values))
                                for model, values in sorted(by_model[side].items(), key=lambda kv: natural(kv[0]))},
                   "sessions": len(sessions[side]),
                   "by_day": [{"day": day, "tokens": n} for day, n in by_day[side].items()]}
            for side in ("factory", "loop")}


def kept_shape(result):
    """True when a kept result has the shape token_report.activity() returns."""
    return isinstance(result, dict) and all(
        isinstance(result.get(kind), dict) and all(
            isinstance(row, dict) and whole(row.get("runs")) and isinstance(row.get("models"), dict) and all(
                isinstance(counts, list) and len(counts) == len(COUNTS) and all(whole(n) for n in counts)
                for counts in row["models"].values())
            for row in result[kind].values())
        for kind in SPEND_FIELDS)


def kept_activity(root, since, now, projects_dir):
    """(token_report.activity()'s result, when it was read), or (None, None) when it can't be read.

    The read goes through every transcript, so its result is kept and used again for ACTIVITY_KEEP at the
    same since. A kept result that can't be read or isn't the right shape counts as none."""
    path = names.state_dir(root) / ACTIVITY_CACHE
    try:
        kept = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        kept = None
    if isinstance(kept, dict) and kept.get("since") == since and kept_shape(kept.get("result")):
        at = when(kept.get("at"))
        if at and now - at <= ACTIVITY_KEEP:
            return kept["result"], at
    try:
        result = token_report.activity(projects_dir, since, root, loop_dirs(root))
    except (OSError, ValueError, TypeError):
        return None, None
    save(path, {"at": now.isoformat(timespec="seconds"), "since": since, "result": result})
    return result, now


def iso_date(value):
    """value when it's a YYYY-MM-DD date, else None."""
    try:
        return value if datetime.date.fromisoformat(value).isoformat() == value else None
    except (TypeError, ValueError):
        return None


def rate(entry):
    """[dollars per PRICED_TOKENS for each of COUNTS] from a prices.json entry, or None unless it has four
    finite, non-negative numbers: json.loads() takes NaN, which json.dumps() would print as invalid JSON."""
    found = [number(entry.get(name)) for name in COUNTS] if isinstance(entry, dict) else [None]
    try:
        return [float(n) for n in found] if all(n is not None and n >= 0 and math.isfinite(n) for n in found) else None
    except OverflowError:  # a whole number too big for a float
        return None


def prices(root):
    """({model: its rate(), None when that can't be read}, why a model not listed has no price, the date checked)."""
    try:
        found = json.loads((names.state_dir(root) / PRICES).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "no prices.json", None
    except (OSError, ValueError):
        return {}, "unreadable", None
    models = found.get("models") if isinstance(found, dict) else None
    if not isinstance(models, dict):
        return {}, "unreadable", None
    return {model: rate(entry) for model, entry in models.items()}, "not in prices.json", iso_date(found.get("checked"))


def dollars(counts, price):
    """What counts cost at price, infinite when that's too big for a float."""
    try:
        return sum(n * p for n, p in zip(counts, price)) / PRICED_TOKENS
    except OverflowError:
        return math.inf


def spent(models, rates, why, unpriced):
    """{tokens, cost_usd} over {model: counts}, adding to unpriced each model with tokens and no price.

    A model with no tokens costs nothing, priced or not, so an item with none costs 0.0."""
    count, cost = 0, 0.0
    for model, counts in models.items():
        if not any(counts):
            continue
        count += sum(counts)
        price = rates.get(model, why)
        if isinstance(price, list):
            cost = None if cost is None else cost + dollars(counts, price)
        else:
            unpriced[model] = price or "unreadable"
            cost = None
    return {"tokens": count, "cost_usd": round(cost, 4) if cost is not None and math.isfinite(cost) else None}


def spend(section, root, since, now, projects_dir):
    """The activity section with what each skill, agent and command spent merged in. A section that's
    missing stays as it is, and so do the counts when there's nothing to say what was spent: empty maps
    would claim nothing was."""
    if "why" in section or not Path(projects_dir).is_dir():
        return section
    result, at = kept_activity(root, since, now, projects_dir)
    if result is None:
        return section
    rates, why, checked = prices(root)
    unpriced, out = {}, dict(section)
    for kind, field in SPEND_FIELDS.items():
        rows = {name: spent(row["models"], rates, why, unpriced) for name, row in result[kind].items()}
        out[field] = {name: rows[name] for name in sorted(rows, key=lambda n: (-rows[n]["tokens"], natural(n)))}
    out["unpriced"] = {model: unpriced[model] for model in sorted(unpriced, key=natural)}
    out["prices_checked"] = checked
    out["spend_at"] = at.isoformat(timespec="seconds")
    return out


def gh(root, *args, timeout=None):
    """The JSON values gh prints, run in root so it reaches root's repo, or None when gh is missing, fails
    or prints anything else. A list with --paginate is printed a page at a time, one array after another.
    timeout is the seconds the whole call gets, GH_TIMEOUT when it's None."""
    try:
        done = subprocess.run(["gh", *args], cwd=root, capture_output=True, text=True,
                              timeout=GH_TIMEOUT if timeout is None else timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    decoder, text, at, values = json.JSONDecoder(), done.stdout, 0, []
    while True:
        while at < len(text) and text[at].isspace():
            at += 1
        if at == len(text):
            return values
        try:
            value, at = decoder.raw_decode(text, at)
        except ValueError:
            return None
        values.append(value)


def commit_kind(item):
    """{loop, merge_from_base} for one commit from the REST API, keeping nothing else of it."""
    item = item if isinstance(item, dict) else {}
    commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
    message = commit.get("message") if isinstance(commit.get("message"), str) else ""
    parents = item.get("parents") if isinstance(item.get("parents"), list) else []
    return {"loop": any(line.startswith("Loop: issue #") for line in message.splitlines()),
            "merge_from_base": len(parents) > 1 and message.startswith(BASE_MERGES)}


def loop_rework(root, since):
    """The loop's merged pull requests since since, and the ones a commit without the loop's line reached.

    A merged pull request's commits don't change, so each one's are fetched once and cached for good.
    """
    pages = gh(root, "pr", "list", "--state", "merged", "--json", "number,title,headRefName,mergedAt",
               "--limit", "200")
    if pages is None or not all(isinstance(page, list) for page in pages):
        return missing("gh failed")
    prs = [pr for page in pages for pr in page
           if isinstance(pr, dict) and isinstance(number(pr.get("number")), int)
           and isinstance(pr.get("headRefName"), str) and LOOP_BRANCH.match(pr["headRefName"])
           and isinstance(pr.get("mergedAt"), str) and pr["mergedAt"][:10] >= since]
    path = names.state_dir(root) / REWORK_CACHE
    try:
        cache = json.loads(path.read_text())
    except (OSError, ValueError):
        cache = {}
    cache = cache if isinstance(cache, dict) else {}
    fetched = {}
    out = []
    for pr in sorted(prs, key=lambda pr: pr["number"]):
        key = str(pr["number"])
        kinds = cache.get(key)
        if not (isinstance(kinds, list) and all(isinstance(k, dict) for k in kinds)):
            pages = gh(root, "api", "repos/{owner}/{repo}/pulls/" + key + "/commits", "--paginate")
            if pages is None or not all(isinstance(page, list) for page in pages):
                if fetched:
                    save(path, dict(cache, **fetched))  # keep what this run did read
                return missing("gh failed")
            kinds = fetched[key] = [commit_kind(item) for page in pages for item in page]
        added = [k for k in kinds if not k.get("loop")]
        if added:
            merges = sum(1 for k in added if k.get("merge_from_base"))
            out.append({"number": pr["number"], "title": pr["title"] if isinstance(pr.get("title"), str) else None,
                        "merges_from_base": merges, "other_commits": len(added) - merges})
    if fetched:
        save(path, dict(cache, **fetched))  # the counts stand without the cache; the next run asks gh again
    return {"merged": len(prs), "reworked": len(out), "pull_requests": out}


def median(values):
    """The median of a list of numbers, or None when it's empty."""
    found = sorted(values)
    if not found:
        return None
    mid = len(found) // 2
    return found[mid] if len(found) % 2 else (found[mid - 1] + found[mid]) / 2


def rounded(value):
    return None if value is None else round(value, 1)


def loop_steps(root, since):
    """For each of STAGE_STEPS, the median minutes the issues started since `since` spent at it, and how many."""
    rows, why = status_rows(root)
    if rows is None:
        return missing(why)
    counted = [row for row in rows.values() if isinstance(row.get("started"), str) and row["started"][:10] >= since]
    out = {}
    for step in STAGE_STEPS:
        minutes = []
        for row in counted:
            spent = row.get("step_seconds")
            seconds = number(spent.get(step)) if isinstance(spent, dict) else None
            if seconds is None:
                continue
            try:
                value = float(seconds) / 60
            except OverflowError:  # a whole number too big for a float
                continue
            # json.loads() takes NaN, which json.dumps() would print as invalid JSON.
            if math.isfinite(value):
                minutes.append(value)
        out[step] = {"median_minutes": rounded(median(minutes)), "issues": len(minutes)}
    return out


def login(person):
    """A gh author's login, or None when it has none. Used only to compare, never printed."""
    return text_or_none(person.get("login")) if isinstance(person, dict) else None


def stage_pull_requests(root, since):
    """The loop's pull requests merged since `since`: the median hours from opened to merged, and to the first
    review by someone other than the pull request's author, each with how many it covers."""
    pages = gh(root, "pr", "list", "--state", "merged", "--json", STAGE_PR_FIELDS, "--limit", "200")
    if pages is None or not all(isinstance(page, list) for page in pages):
        return missing("gh failed")
    to_merge, to_review = [], []
    for pr in (pr for page in pages for pr in page):
        if not (isinstance(pr, dict) and isinstance(pr.get("headRefName"), str) and LOOP_BRANCH.match(pr["headRefName"])
                and isinstance(pr.get("mergedAt"), str) and pr["mergedAt"][:10] >= since):
            continue
        opened, merged = when(pr.get("createdAt")), when(pr["mergedAt"])
        if opened is None or merged is None:
            continue  # a pull request whose times can't be read isn't counted
        to_merge.append((merged - opened).total_seconds() / 3600)
        own = login(pr.get("author"))
        reviews = pr.get("reviews") if isinstance(pr.get("reviews"), list) else []
        times = [when(r.get("submittedAt")) for r in reviews
                 if isinstance(r, dict) and login(r.get("author")) not in (None, own)]
        times = [t for t in times if t is not None]
        if times:
            to_review.append((min(times) - opened).total_seconds() / 3600)
    return {"merged": len(to_merge), "median_hours_to_merge": rounded(median(to_merge)),
            "reviewed": len(to_review), "median_hours_to_first_review": rounded(median(to_review))}


def slowest(steps, prs):
    """The stage with the largest median, in minutes, among those with SLOWEST_AT or more behind it, or None."""
    found = []
    if "why" not in steps:
        found += [(steps[step]["median_minutes"], steps[step]["issues"], step) for step in STAGE_STEPS]
    if "why" not in prs:
        for name, hours, n in (("first_review", prs["median_hours_to_first_review"], prs["reviewed"]),
                               ("merge", prs["median_hours_to_merge"], prs["merged"])):
            found.append((None if hours is None else hours * 60, n, name))
    found = [(minutes, name) for minutes, n, name in found if minutes is not None and n >= SLOWEST_AT]
    return max(found, key=lambda f: f[0])[1] if found else None


def stage_times(root, since):
    steps, prs = loop_steps(root, since), stage_pull_requests(root, since)
    return {"loop_steps": steps, "pull_requests": prs, "slowest": slowest(steps, prs)}


def finite(text):
    """text as a float, refusing NaN and the infinities: json.loads() takes them, and json.dumps() would print
    them as invalid JSON. A number too big for a float, like 1e999, comes through here as well."""
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(text)
    return value


def history_line(raw):
    """One line of a history.jsonl as a dict, or None when loop_history skips it."""
    try:
        line = json.loads(raw, parse_constant=finite, parse_float=finite)
    except (ValueError, RecursionError):
        return None
    if not isinstance(line, dict) or type(line.get("v")) is not int or line["v"] != 1:
        return None
    return line if isinstance(line.get("ended"), str) and len(line["ended"]) >= 10 else None


def history_run(prefix, line):
    """The fields a run prints from its history line, and only those. The folder names the project, as in
    status_rows(), and an issue that isn't a whole number is null, so free text can't come through it. A
    field of the wrong type is null too, so a list nested too deep to print can't stop the whole document."""
    def labels(value):
        return value if isinstance(value, list) and all(isinstance(item, str) for item in value) else None

    issue = number(line.get("issue"))
    return {"issue": "{}issue-{}".format(prefix, issue) if isinstance(issue, int) else None,
            "started": text_or_none(line.get("started")), "ended": line["ended"],
            "outcome": text_or_none(line.get("outcome")), "rounds": number(line.get("rounds")),
            "tests": labels(line.get("tests")), "verdicts": labels(line.get("verdicts")),
            "tokens": number(line.get("tokens")), "cost_usd": number(line.get("cost_usd"))}


def outcome_counts(runs):
    """How many of runs ended in each of OUTCOMES."""
    return {name: sum(1 for run in runs if run["outcome"] == name) for name in OUTCOMES}


def loop_history(root, since, today):
    state = Path(root) / ".loop"
    paths = [("", state / "history.jsonl")]
    paths += [(p.parent.name + "/", p) for p in sorted(state.glob("projects/*/history.jsonl"))]
    # exists(), not is_file(): a directory at that path is a file that can't be read, not one that isn't there.
    paths = [(prefix, path) for prefix, path in paths if path.exists()]
    if not paths:
        return missing("no run history")
    runs, skipped, read_any = [], 0, False
    for prefix, path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, ValueError):
            continue
        read_any = True
        for raw in text.splitlines():
            line = history_line(raw)
            if line is None:
                skipped += 1
            elif line["ended"][:10] >= since:
                runs.append(history_run(prefix, line))
    if not read_any:
        return missing("unreadable")
    runs.sort(key=lambda run: run["ended"])
    on = {}
    for run in runs:
        on.setdefault(run["ended"][:10], []).append(run)
    by_day = [dict(day=d, runs=len(on.get(d, [])), **outcome_counts(on.get(d, [])),
                   more_than_one_round=sum(1 for run in on.get(d, []) if (run["rounds"] or 0) > 1))
              for d in days(since, today)]
    return {"runs": runs, "by_day": by_day, "by_outcome": outcome_counts(runs), "skipped_lines": skipped}


def work_by_type(root, since):
    """This repo's pull requests merged since `since`, by type, with what the loop spent on the issues they close.

    The pull requests and their types come from work_report.py's search, read the way it reads them. Spend
    is over every date, since work merged in the period was often started before it."""
    import work_report  # here, not at the top: work_report imports this module as it loads
    pages = gh(root, "api", "graphql", "--paginate",
               "-F", "q=repo:{{owner}}/{{repo}} is:pr is:merged merged:>={}".format(since),
               "-f", "query=" + work_report.QUERY, timeout=work_report.SEARCH_TIMEOUT)
    prs, matched, why = work_report.searched(pages or None)  # no page at all is a gh that didn't answer
    if prs is None:
        return missing(why)
    rows = [row for row in work_report.pull_request_rows(prs) if row["merged"] >= since]
    runs = loop_runs(root, "0000-01-01")
    out = []
    for kind in work_report.TYPES + (None,):
        typed = [row for row in rows if row["type"] == kind]
        issues = sorted({n for row in typed for n in row["closes"]})
        entries = [e for n in issues for e in runs.get("issue-{}".format(n), [])]
        spent = totals(entries) if entries else {"tokens": 0, "cost_usd": 0.0}
        out.append({"type": kind, "merged": len(typed), "loop_built": sum(1 for row in typed if row["loop_built"]),
                    "issues": len(issues), "tokens": spent["tokens"] or 0, "cost_usd": spent["cost_usd"]})
    return {"types": out, "truncated": matched > work_report.LIMIT}


def build(root, since, today, now=None, projects_dir=TRANSCRIPTS):
    now = now or datetime.datetime.now().astimezone()
    return {"schema": SCHEMA, "generated": now.isoformat(timespec="seconds"), "since": since,
            "loop_spend": loop_spend(root, since, today),
            "loop_throughput": loop_throughput(root),
            "activity": spend(activity(root, since), root, since, now, projects_dir),
            "evals": evals(root),
            "conversations": conversations(root, since, today, projects_dir, names.state_dir(root) / CACHE),
            "waiting": waiting(root, now),
            "loop_rework": loop_rework(root, since),
            "stage_times": stage_times(root, since),
            "loop_history": loop_history(root, since, today),
            "work_by_type": work_by_type(root, since)}


def main(argv=None, root=ROOT, projects_dir=TRANSCRIPTS):
    now = datetime.datetime.now().astimezone()
    today = now.date()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", required=True, help="print the numbers as JSON")
    parser.add_argument("--since", type=since_date, default=(today - datetime.timedelta(days=14)).isoformat(),
                        help="the first day to count, as YYYY-MM-DD (default: 14 days ago)")
    args = parser.parse_args(argv)
    print(json.dumps(build(root, args.since, today, now, projects_dir), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
