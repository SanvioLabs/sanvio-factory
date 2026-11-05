#!/usr/bin/env python3
"""Golden-example eval for the review agents: does a reviewer still catch what it should?
It also runs the review-pr skill the same way, on a diff.

Usage:
    python3 scripts/eval_agents.py FOLDER [--runs 2] [--agent claude] [--save [FILE]]
                                          [--baseline FILE|latest] [--checkout PATH]

FOLDER holds one folder per case, <NN-slug>/, each with a work file for the agent to review and a
case.json that says what a good review of it looks like:

    agent           the agent in agents/, such as reviewer
    skill           the skill in skills/, in place of agent, such as review-pr. A case names one of
                    agent and skill, never both. A skill case's work is a diff, and its reviewer is
                    skill:<name>
    work            optional: the work file's name in the case's folder, work.md by default
    brief           optional: the job's brief, a path from the harness root
    must_find       texts from the work file that at least one finding must quote. An entry can be a
                    list of alternatives, and any one of them in a finding is enough
    must_cover      optional: lines of the work file, each a number or "first-last", that at least one
                    finding's **Where:** line must name, as :N or :N-M overlapping it. For a skill case
                    the work is a diff, so the lines are the changed file's, as a review cites them
    must_mention   optional: texts the reply must hold anywhere, findings or not
    must_not_flag   texts no finding may quote
    max_findings    most findings the reply may hold
    verdict         optional: the **Verdict:** the reply must end on

A finding is the block around a **Where:** line. It starts at the title and severity lines just
above it: the lines directly above, back to a blank line, a heading, a closing line or the previous
**Where:** line. So a finding written with no blank line before the next one can lose its last lines
to the next, which changes no grade. It ends at the next finding or the first closing line after its
**Where:**: a heading, or a line starting **Recommendations:**, **Not checked:** or **Summary:**.
Matching ignores case.

A case passes a run when its reply meets all of that and the agent left the checkout as it found it.
Each case runs --runs times (two by default): all pass is stable, some is flaky, none is failing.
Every run starts a real agent session, so a run of ten cases costs twenty. --agent takes claude or
codex like loop.json's reader_agent, or any command line that reads the prompt on standard input.
The agent is given the work's path, not its text, so it has to be able to read files: ollama can't.
Only claude is held to read tools. --save writes the results as JSON, with the reviewer, the folder and
when it was saved: to FILE, or with no FILE to .harness/evals/<YYYY-MM-DDTHHMM>-<reviewer>.json, with
a skill's colon as a hyphen, so skill:review-pr saves as ...-skill-review-pr.json. --baseline
lists the cases whose status differs from a file saved earlier: FILE, or with latest the newest file in
.harness/evals/ whose "reviewer" is this run's. Both defaults need every case to name the same agent or
skill.

Exits 0 when no case is failing, 1 when one is, 2 when the folder has no cases or a default is asked of
cases for more than one reviewer. A case that names both agent and skill, or neither, raises ValueError.

From the Sanvio Labs harness starter, MIT: https://github.com/SanvioLabs/sanvio-harness-starter
"""
import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from loop import command, confined, result_line  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SAVED = ROOT / ".harness" / "evals"  # where --save with no file writes, and --baseline latest reads
TIMEOUT = 900  # seconds one agent session may take
WHERE = re.compile(r"^\s*(?:[-*]\s+|\d+[.)]\s+)?\*\*Where:\*\*", re.M)
CLOSING = re.compile(r"^(?:#+ |\s*(?:[-*]\s+|\d+[.)]\s+)?\*\*(?:Recommendations|Not checked|Summary):\*\*)", re.M)
LINES = re.compile(r":(\d+)(?:-(\d+))?")
VERDICT = re.compile(r"\*\*Verdict:\*\*\s*([A-Za-z][A-Za-z-]*)")
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens")


def load_cases(folder):
    """Every case under folder, in name order: dicts of case.json plus name, folder and work."""
    cases = []
    for spec in sorted(Path(folder).glob("*/case.json")):
        case = json.loads(spec.read_text())
        if ("agent" in case) == ("skill" in case):
            raise ValueError("{}: case.json names {} of agent and skill; it needs exactly one".format(
                spec.parent.name, "both" if "agent" in case else "neither"))
        case.setdefault("must_find", [])
        case.setdefault("must_cover", [])
        case.setdefault("must_mention", [])
        case.setdefault("must_not_flag", [])
        case.setdefault("max_findings", 10)
        case.update(name=spec.parent.name, folder=spec.parent, work=spec.parent / case.get("work", "work.md"))
        cases.append(case)
    return cases


def prompt(case, root=ROOT):
    """What the agent is given: its instructions (the agent's file, or the skill's SKILL.md), the job's brief
    if the case names one, and where the work is."""
    if case.get("skill"):
        instructions = Path(root) / "skills" / case["skill"] / "SKILL.md"
    else:
        instructions = Path(root) / "agents" / (case["agent"] + ".md")
    parts = [instructions.read_text().strip()]
    if case.get("brief"):
        parts.append("The job's brief:\n\n" + (Path(root) / case["brief"]).read_text().strip())
    work = Path(case["work"]).resolve()
    if case.get("skill"):
        parts.append("The change to review is the diff in {}. Read it from that file. You have no shell and no "
                     "GitHub access, so say you did not run the tests, then report as the skill's Output says."
                     .format(work))
    else:
        parts.append("Review the work in {}. Read it from that file, then report as your instructions say."
                     .format(work))
    return "\n\n".join(parts) + "\n"


def opening(reply, line, floor):
    """Where the finding whose **Where:** line starts at line begins: back over the lines directly above,
    stopping at a blank line, a heading, a closing line or floor."""
    while line > floor:
        above = reply.rfind("\n", 0, line - 1) + 1
        text = reply[above:line - 1]
        if not text.strip() or CLOSING.match(text):
            break
        line = above
    return line


def findings(reply):
    """The reply's findings: a block around each **Where:** line, from its title to the next finding or the
    first closing line. A reply with no **Where:** line has zero."""
    lines = [reply.rfind("\n", 0, m.end()) + 1 for m in WHERE.finditer(reply)]
    floors = [0] + [reply.find("\n", at) + 1 for at in lines[:-1]]
    starts = [opening(reply, at, floor) for at, floor in zip(lines, floors)]
    found = []
    for at, start, end in zip(lines, starts, starts[1:] + [len(reply)]):
        closing = CLOSING.search(reply, at)
        found.append(reply[start:min(end, closing.start()) if closing else end])
    return found


def covered(finding):
    """The (first, last) line ranges a finding's **Where:** line names: each :N or :N-M on it, so
    `work.ts:33-40` and `/full/path/work.ts:31, then :39` both count. Nothing else in the finding does."""
    where = WHERE.search(finding)
    if not where:
        return []
    line = finding[where.end():].split("\n", 1)[0]
    return [(int(first), int(last or first)) for first, last in LINES.findall(line)]


def span(entry):
    """A must_cover entry, 37 or "30-37", as (first, last)."""
    first, _, last = str(entry).partition("-")
    return int(first), int(last or first)


def grade(case, reply, changed=()):
    """(passed, reasons) for one reply to case. changed is what the agent altered in the checkout."""
    found = findings(reply)
    text = "\n".join(found).lower()
    reasons = []
    for anchor in case["must_find"]:
        options = anchor if isinstance(anchor, list) else [anchor]
        if not any(option.lower() in text for option in options):
            reasons.append("missed: " + " | ".join(options))
    ranges = [r for finding in found for r in covered(finding)]
    for entry in case["must_cover"]:
        first, last = span(entry)
        if not any(start <= last and first <= end for start, end in ranges):
            reasons.append("not covered: line {}".format(entry))
    for anchor in case["must_mention"]:
        if anchor.lower() not in reply.lower():
            reasons.append("not mentioned: " + anchor)
    for anchor in case["must_not_flag"]:
        if anchor.lower() in text:
            reasons.append("flagged: " + anchor)
    if len(found) > case["max_findings"]:
        reasons.append("{} findings, more than {}".format(len(found), case["max_findings"]))
    if case.get("verdict"):
        match = VERDICT.search(reply)
        said = match.group(1) if match else "none"
        if said.upper() != case["verdict"].upper():
            reasons.append("verdict {}, not {}".format(said, case["verdict"]))
    if changed:
        reasons.append("changed the checkout: " + ", ".join(sorted(changed)))
    return not reasons, reasons


def status_of(checkout):
    """The checkout's `git status --porcelain` lines; empty when it isn't a git repo."""
    done = subprocess.run(["git", "-C", str(checkout), "status", "--porcelain"], capture_output=True, text=True)
    return set(done.stdout.splitlines()) if done.returncode == 0 else set()


def run_case(case, agent="claude", checkout=ROOT, root=ROOT):
    """Run one fresh session on case. Returns {"passed", "reasons", "reply", "tokens", "seconds"}."""
    cmd, why = command({"agent_reader": agent}, "agent_reader")
    if cmd is None:
        return {"passed": False, "reasons": ["agent can't run: " + why], "reply": "", "tokens": None, "seconds": 0.0}
    held = confined(cmd)
    if held is not None:
        cmd = held + ["--output-format", "json"]
    before = status_of(checkout)
    started = time.monotonic()
    try:
        done = subprocess.run(cmd, cwd=str(checkout), input=prompt(case, root), capture_output=True,
                              text=True, timeout=TIMEOUT)
        reply, tokens = done.stdout, None
        for line in done.stdout.splitlines():
            found = result_line(line)
            if found:
                reply, usage = found
                tokens = sum(usage.get(key) or 0 for key in TOKEN_KEYS) if usage else None
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"passed": False, "reasons": ["agent didn't finish: {}".format(type(error).__name__)],
                "reply": "", "tokens": None, "seconds": round(time.monotonic() - started, 1)}
    seconds = round(time.monotonic() - started, 1)
    passed, reasons = grade(case, reply, status_of(checkout) ^ before)
    return {"passed": passed, "reasons": reasons, "reply": reply, "tokens": tokens, "seconds": seconds}


def status(passes, runs):
    return "stable" if passes == runs else "failing" if passes == 0 else "flaky"


def evaluate(cases, runs, agent, checkout=ROOT, root=ROOT):
    """{case name: {"status", "passes", "runs", "reasons", "tokens", "seconds"}} for every case."""
    out = {}
    for case in cases:
        results = [run_case(case, agent, checkout, root) for _ in range(runs)]
        passes = sum(r["passed"] for r in results)
        counted = [r["tokens"] for r in results if r["tokens"] is not None]
        out[case["name"]] = {
            "status": status(passes, runs), "passes": passes, "runs": runs,
            "reasons": sorted({reason for r in results for reason in r["reasons"]}),
            "tokens": sum(counted) if counted else None,
            "seconds": round(sum(r["seconds"] for r in results), 1)}
    return out


def changed_since(old, new):
    """Lines naming each case whose status differs between two saved results, or is in only one."""
    lines = []
    for name in sorted(set(old) | set(new)):
        before = old.get(name, {}).get("status", "absent")
        after = new.get(name, {}).get("status", "absent")
        if before != after:
            lines.append("{}: {} -> {}".format(name, before, after))
    return lines


def reviewer_of(cases):
    """The set of reviewers the cases name: an agent's name, or skill:<name> for a skill case."""
    return {"skill:" + case["skill"] if case.get("skill") else case["agent"] for case in cases}


def latest(reviewer):
    """The newest file in SAVED whose "reviewer" field is reviewer, or None. Names start with the time
    they were saved, so the last in name order is the newest. The field is read, not the name, because
    *-reviewer.json also matches security-reviewer's files."""
    for path in sorted(SAVED.glob("*.json"), reverse=True):
        try:
            if json.loads(path.read_text()).get("reviewer") == reviewer:
                return path
        except (OSError, ValueError, AttributeError):
            continue
    return None


def shown(path):
    """path relative to ROOT, or whole when it's outside ROOT."""
    path = Path(path).resolve()
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv):
    ap = argparse.ArgumentParser(description="Run the golden examples against a review agent.")
    ap.add_argument("folder")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--agent", default="claude")
    ap.add_argument("--save", metavar="FILE", nargs="?", const="")
    ap.add_argument("--baseline", metavar="FILE")
    ap.add_argument("--checkout", default=str(ROOT))
    args = ap.parse_args(argv)
    cases = load_cases(args.folder)
    if not cases:
        print("no cases in " + args.folder)
        return 2
    reviewers = sorted(reviewer_of(cases))
    reviewer = ", ".join(reviewers)
    if len(reviewers) > 1 and (args.save == "" or args.baseline == "latest"):
        print("the cases are for more than one reviewer ({}), so --save needs a FILE and --baseline "
              "can't be latest".format(reviewer))
        return 2
    baseline = args.baseline
    if baseline == "latest":
        baseline = latest(reviewer)
    results = evaluate(cases, max(1, args.runs), args.agent, Path(args.checkout))
    for name, r in results.items():
        print("{:<8} {}  ({}/{} runs)".format(r["status"].upper(), name, r["passes"], r["runs"]))
        for reason in r["reasons"]:
            print("           - " + reason)
    counts = [sum(r["status"] == s for r in results.values()) for s in ("stable", "flaky", "failing")]
    tokens = [r["tokens"] for r in results.values() if r["tokens"] is not None]
    print("{} stable, {} flaky, {} failing; {} tokens, {:.0f}s".format(
        *counts, sum(tokens) if tokens else "unknown", sum(r["seconds"] for r in results.values())))
    if args.save is not None:
        # With its UTC offset, so it compares with git's commit dates, which carry one.
        now = datetime.now().astimezone()
        # A colon breaks filenames on some systems, so skill:review-pr saves as ...-skill-review-pr.json. The
        # "reviewer" field keeps the colon, and latest() reads the field, so it never matches an agent's run.
        path = Path(args.save) if args.save else SAVED / "{:%Y-%m-%dT%H%M}-{}.json".format(
            now, reviewer.replace(":", "-"))
        if not args.save:
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"agent": args.agent, "reviewer": reviewer, "folder": shown(args.folder),
                                    "saved": now.isoformat(timespec="seconds"), "cases": results}, indent=2) + "\n")
    if args.baseline == "latest" and baseline is None:
        print("no saved run for {} in {}/".format(reviewer, shown(SAVED)))
    elif baseline:
        old = json.loads(Path(baseline).read_text())["cases"]
        diff = changed_since(old, results)
        shown_as = shown(baseline) if args.baseline == "latest" else baseline
        print("against {}: {}".format(shown_as, "no case changed" if not diff else ""))
        for line in diff:
            print("  " + line)
    return 1 if counts[2] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
