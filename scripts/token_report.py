#!/usr/bin/env python3
"""Summarize the Claude Code tokens spent under this repo, as Markdown.

    python3 scripts/token_report.py                    # the last 14 days
    python3 scripts/token_report.py --since 2026-10-01
    python3 scripts/token_report.py --projects /some/other/.claude/projects

Reads Claude Code's own transcripts, ~/.claude/projects/**/*.jsonl, subagents
included, and counts the tokens on each reply whose working folder is this
repo: conversations at its root, each repo under projects/, and each issue
the loop built in its worktrees. Nothing it prints holds a prompt, a reply, a
file path or a line of code: counts, model names, session ids, issue names,
and for the loop, estimated dollars. Claude Code only: Codex, Kiro and other
tools keep their own logs. The dollars are the estimate at API prices each loop
run recorded in .loop/**/usage.json, not what was billed; a conversation's
transcript carries no cost, so it stays in tokens. A last section splits the
sessions started at the root, including after they move into projects/, by
subagent type, skill and slash command, a skill's or command's share attributed
from where it started to the next prompt. The skills/factory-trends/ skill runs
this next to usage_report.py.
"""
import argparse
import datetime
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from loop import load_config, usage_totals  # noqa: E402 (needs scripts/ on the path first)
from usage_report import since_date  # noqa: E402 (same reason)
import names  # noqa: E402 (same reason)
import old_names  # noqa: E402 (same reason: the loop's home before the rename)

# The four counts on a reply's message.usage, with the names the tables give them.
FIELDS = (("input_tokens", "Input"), ("output_tokens", "Output"),
          ("cache_creation_input_tokens", "Cache writes"), ("cache_read_input_tokens", "Cache reads"))
GROUPS = (("Conversations", "Where"), ("projects/", "Repo"), ("Loop", "Issue"))
TOP = 5
NO_AGENT_TYPE = "agent type not recorded"
ATTRIBUTED = ("Attributed from where each started to the next prompt, not measured. "
              "This section covers sessions started at the root, including after they move into projects/.")


def loop_dir(root):
    """Where the loop puts its worktrees: worktree_dir from loop.json, or ~/.sanvio-loop/<root's name>."""
    configured = load_config(root).get("worktree_dir")
    if configured:
        return Path(configured).expanduser()
    return names.loop_home() / Path(root).name


# The repo's name before the rename: a clone made then and renamed since kept its old runs under it.
OLD_REPO_NAME = "sanvio-harness-starter"


def loop_dirs(root, home=None):
    """Every folder the loop's checkouts can be in, to count their tokens.

    worktree_dir from loop.json when it's set, and nothing else. Otherwise ~/.sanvio-loop/<root's name>,
    then ~/.harness-loop/<root's name> and ~/.harness-loop/sanvio-harness-starter when each is there:
    checkouts the loop made before the rename, counted for as long as they're kept. The second covers a
    clone whose folder was renamed with the repo; a separate clone still named sanvio-harness-starter on
    the same machine would be counted here too. The loop itself never makes or reuses one there.
    """
    configured = load_config(root).get("worktree_dir")
    if configured:
        return [Path(configured).expanduser()]
    name = Path(root).name
    found = [names.loop_home(home) / name]
    for old_name in (name, OLD_REPO_NAME):
        old = old_names.old_loop_home(home) / old_name
        if old.is_dir() and old not in found:
            found.append(old)
    return found


def usage_files(root):
    """(issue, path) for every usage.json the loop wrote: issue-N for this repo, <name>/issue-N for a project."""
    state = Path(root) / ".loop"
    paths = [(p.parent.name, p) for p in state.glob("issue-*/usage.json")]
    paths += [("{}/{}".format(p.parent.parent.name, p.parent.name), p) for p in state.glob("projects/*/issue-*/usage.json")]
    return paths


def loop_runs(root, since):
    """{issue: [usage.json entries]} for the loop's runs on or after `since`.

    A run counts when its run_started, the time the loop picked the issue up, is on or after `since`;
    a run with no run_started is in no period. A record that can't be read is skipped, and an issue
    with no run in the period is left out.
    """
    out = {}
    for name, path in usage_files(root):
        try:
            found = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(found, list):
            continue
        runs = [e for e in found if isinstance(e, dict) and isinstance(e.get("run_started"), str)
                and e["run_started"][:10] >= since]
        if runs:
            out[name] = runs
    return out


def loop_costs(root, since):
    """{issue: (estimated dollars or None, runs without a cost)} from loop_runs().

    A run without a numeric cost_usd (it ended early, its agent isn't Claude, or it predates the
    loop recording cost) is counted as one without.
    """
    out = {}
    for name, runs in loop_runs(root, since).items():
        priced = [e for e in runs if isinstance(e.get("cost_usd"), (int, float)) and not isinstance(e.get("cost_usd"), bool)]
        out[name] = (usage_totals(priced)[1], len(runs) - len(priced))
    return out


def cost_table(costs):
    if not costs:
        return ["None recorded.", ""]
    out = ["| Issue | Estimated cost | Runs without a cost |", "|---|---|---|"]
    for name in sorted(costs, key=natural):
        cost, without = costs[name]
        out.append("| {} | {} | {} |".format(name, "none recorded" if cost is None else "${:,.2f}".format(cost), without))
    total = sum(cost for cost, _ in costs.values() if cost is not None)
    without = sum(n for _, n in costs.values())
    note = ["Total: ${:,.2f}, estimated at API prices, not what was billed.".format(total)]
    if without:
        note.append("{} run{} recorded no cost, so the issues they belong to cost more than shown.".format(
            without, "" if without == 1 else "s"))
    note.append("Runs are counted by when the loop picked the issue up.")
    return out + ["", " ".join(note), ""]


def read(projects_dir, since):
    """Every reply with a usage on or after `since` (YYYY-MM-DD), each counted once.

    Claude Code writes one reply as several lines, one per content block, each with the same
    message id and request id, so a pair seen before is skipped. A reply from a subagent, marked
    isSidechain or written to a file in a session's subfolder, gets `_subagent` set. Lines that
    aren't JSON, files that can't be read and a folder that isn't there are skipped.
    """
    projects_dir = Path(projects_dir)
    if not projects_dir.is_dir():
        return []
    entries, seen = [], set()
    for path in sorted(projects_dir.rglob("*.jsonl")):
        nested = len(path.relative_to(projects_dir).parts) > 2
        try:
            found = read_file(path, nested)
        except OSError:
            continue
        for entry in found:
            if str(entry.get("timestamp", ""))[:10] < since:
                continue
            key = (entry["message"].get("id"), entry.get("requestId"))
            if key != (None, None):
                if key in seen:
                    continue
                seen.add(key)
            entries.append(entry)
    return entries


def read_file(path, nested):
    """Every line in one transcript that is a reply with a usage, in file order, with `_subagent` set.

    No date filter and no dedup: read() does both across files. Lines that aren't JSON are skipped;
    a file that can't be read raises OSError.
    """
    with open(path, encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    entries = []
    for raw in lines:
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        message = entry.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
            continue
        entry["_subagent"] = bool(entry.get("isSidechain")) or nested
        entries.append(entry)
    return entries


def group(entry, root, loop_dir):
    """(group, row) for the folder this reply ran in, or None when it ran outside this repo.

    loop_dir is one folder or a list of them. The loop's folders are checked first, because a
    worktree_dir set in loop.json can sit inside the root.
    """
    cwd = entry.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    try:
        here = Path(cwd).resolve()
        root = Path(root).resolve()
        loops = [Path(one).resolve() for one in (loop_dir if isinstance(loop_dir, (list, tuple)) else [loop_dir])]
    except (OSError, RuntimeError, ValueError):
        return None
    for loop in loops:
        if here != loop and here.is_relative_to(loop):
            parts = here.relative_to(loop).parts
            # A project's worktrees sit one folder down, in <project>/issue-N.
            if not parts[0].startswith("issue-") and len(parts) > 1:
                return ("Loop", "{}/{}".format(parts[0], parts[1]))
            return ("Loop", parts[0])
    projects = root / "projects"
    if here != projects and here.is_relative_to(projects):
        return ("projects/", here.relative_to(projects).parts[0])
    if here.is_relative_to(root):
        return ("Conversations", "")
    return None


def activity(projects_dir, since, root, loop_dir):
    """Runs and tokens by model for each subagent type, skill and slash command, for sessions started at the root.

    Returns {"agents": {...}, "skills": {...}, "commands": {...}}, each name mapping to
    {"runs": n, "models": {model: [input, output, cache writes, cache reads]}}. Only lines dated on or
    after `since` count, and each reply counts once, as in read(). A line counts when group() puts its
    folder in Conversations, or in projects/ for a session started at the root, including after it moves
    there. It reads every line itself, because read_file() drops the lines without a usage.

    A session started where its first line with a cwd says, whatever that line's date. A subagent started
    where its session did, or, when its session's file is missing, unreadable or has no cwd, where its
    own first line with a cwd says.

    A subagent's file, in a session's subfolder, is one run of the agentType in the .meta.json beside
    it, from its first line in scope, even if it has no tokens. In a session's own file, a
    <command-name> line or a Skill call opens a span, and a typed prompt closes it; a new start replaces
    the open span. A start out of scope closes the span and isn't a run. A reply counts toward the span
    open when its id pair is first seen, so the reply that calls a skill stays with what came before it.
    A start already seen, by its line's uuid for a command or its block's id for a skill, isn't a second
    run: the same line written twice, or repeated in a resumed session's file. isSidechain lines in a
    session's own file are a subagent's, so they don't open, close or count toward a span.
    """
    out = {"agents": {}, "skills": {}, "commands": {}}
    projects_dir = Path(projects_dir)
    if not projects_dir.is_dir():
        return out
    seen, started, where, sessions = set(), set(), {}, {}
    rooted = None

    def started_at_root(lines, skip_sidechain):
        """Whether the first line with a cwd is in Conversations, or None when no line has one.

        A subagent's lines are normally isSidechain, so only a session's own file skips them.
        """
        for entry in lines:
            cwd = entry.get("cwd")
            if isinstance(cwd, str) and cwd and not (skip_sidechain and entry.get("isSidechain")):
                return group(entry, root, loop_dir) == ("Conversations", "")
        return None

    def session_rooted(path):
        """started_at_root() for a session's file, read once, or None when it can't be read."""
        if path not in sessions:
            try:
                sessions[path] = started_at_root(transcript(path), True)
            except OSError:
                sessions[path] = None
        return sessions[path]

    def once(kind, key):
        """False for a start already seen: the same line written twice, or repeated in a resumed session's file."""
        if key is None:
            return True
        if (kind, key) in started:
            return False
        started.add((kind, key))
        return True

    def in_scope(entry):
        if str(entry.get("timestamp", ""))[:10] < since:
            return False
        cwd = entry.get("cwd")
        key = cwd if isinstance(cwd, str) else None
        if key not in where:
            where[key] = group(entry, root, loop_dir)
        side = where[key][0] if where[key] else None
        return side == "Conversations" or (side == "projects/" and bool(rooted))

    def counts(entry):
        """True for a reply with a usage, in scope, not counted before."""
        message = entry.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("usage"), dict) or not in_scope(entry):
            return False
        key = (message.get("id"), entry.get("requestId"))
        if key != (None, None):
            if key in seen:
                return False
            seen.add(key)
        return True

    def start(table, name, entry):
        if not in_scope(entry):
            return None
        row = table.setdefault(name, {"runs": 0, "models": {}})
        row["runs"] += 1
        return row

    def opened(kind, name, key, entry, span):
        """The span after a start: none out of scope, the open one for a start already seen, else a new one."""
        if not in_scope(entry):
            return None
        return start(out[kind + "s"], name, entry) if once(kind, key) else span

    for path in sorted(projects_dir.rglob("*.jsonl")):
        try:
            lines = transcript(path)
        except OSError:
            continue
        parts = path.relative_to(projects_dir).parts
        if len(parts) > 2:
            rooted = session_rooted(projects_dir / parts[0] / (parts[1] + ".jsonl"))
            if rooted is None:
                rooted = started_at_root(lines, False)
            name, row = agent_type(path), None
            for entry in lines:
                row = row or start(out["agents"], name, entry)
                if counts(entry) and row is not None:
                    add_usage(row, entry)
            continue
        rooted = started_at_root(lines, True)
        span, owner = None, {}
        for entry in lines:
            if entry.get("isSidechain"):
                continue
            if entry.get("type") == "user":
                name = command_name(entry)
                if name is None:
                    if typed_prompt(entry):
                        span = None
                elif name:
                    span = opened("command", name, entry.get("uuid"), entry, span)
                continue
            message = entry.get("message")
            if entry.get("type") != "assistant" or not isinstance(message, dict):
                continue
            key = (message.get("id"), entry.get("requestId"))
            target = span if key == (None, None) else owner.setdefault(key, span)
            if counts(entry) and target is not None:
                add_usage(target, entry)
            skill, call = skill_called(entry)
            if skill:
                span = opened("skill", skill, call, entry, span)
    return out


def transcript(path):
    """Every line in one transcript that is a JSON object, in file order. A file that can't be read raises OSError."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    entries = []
    for raw in lines:
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def agent_type(path):
    """The agentType in the .meta.json beside a subagent's transcript, or NO_AGENT_TYPE."""
    try:
        found = json.loads(Path(path).with_suffix(".meta.json").read_text())
    except (OSError, ValueError):
        return NO_AGENT_TYPE
    name = found.get("agentType") if isinstance(found, dict) else None
    return name if isinstance(name, str) and name else NO_AGENT_TYPE


def text_of(entry):
    """The text of a line's message: its content if that's a string, or its text blocks joined."""
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b["text"] for b in content if isinstance(b, dict) and isinstance(b.get("text"), str))
    return ""


def command_name(entry):
    """The slash command a user line runs, without its /, or "" when its tag is empty.

    The tag has to open the line, after whitespace and at most one <command-message> block, and hold one
    command-shaped word. Anything else is None: no tag, or a tag someone typed or pasted into a prompt.
    """
    found = re.match(r"\s*(?:<command-message>(?:(?!</command-message>).)*</command-message>\s*)?"
                     r"<command-name>(.*?)</command-name>", text_of(entry), re.S)
    name = found.group(1).strip() if found else ""
    return name.lstrip("/") if found and re.fullmatch(r"/?[\w:.-]*", name) else None


def typed_prompt(entry):
    """True for a user line someone typed: not isMeta and not a tool result."""
    message = entry.get("message")
    if entry.get("isMeta") or not isinstance(message, dict):
        return False
    content = message.get("content")
    if isinstance(content, list):
        return not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
    return isinstance(content, str)


def skill_called(entry):
    """(skill, the block's id) for a Skill tool_use block on this line, or (None, None)."""
    content = entry["message"].get("content")
    if not isinstance(content, list):
        return None, None
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill":
            given = block.get("input")
            skill = given.get("skill") if isinstance(given, dict) else None
            if isinstance(skill, str) and skill:
                call = block.get("id")
                return skill, call if isinstance(call, str) and call else None
    return None, None


def add_usage(row, entry):
    model = entry["message"].get("model")
    model = model if isinstance(model, str) and model else "unknown"
    row["models"][model] = [a + b for a, b in zip(row["models"].get(model, [0] * len(FIELDS)), tokens(entry))]


def tokens(entry):
    """The four usage counts on a reply, with anything that isn't a whole number taken as 0."""
    usage = entry["message"]["usage"]
    out = []
    for field, _ in FIELDS:
        n = usage.get(field)
        out.append(n if isinstance(n, int) and not isinstance(n, bool) and n > 0 else 0)
    return out


def natural(name):
    """A sort key that puts issue-9 before issue-10."""
    return [(0, int(part), "") if part.isdigit() else (1, 0, part) for part in re.split(r"(\d+)", name)]


def counts_table(rows, header):
    if not rows:
        return ["None.", ""]
    out = ["| {} | {} | Total |".format(header, " | ".join(label for _, label in FIELDS)),
           "|---|" + "---|" * (len(FIELDS) + 1)]
    for name in sorted(rows, key=natural):
        values = rows[name]
        out.append("| {} | {} | {:,} |".format(name, " | ".join("{:,}".format(v) for v in values), sum(values)))
    return out + [""]


def top_table(counter, header, label=None, limit=TOP):
    if not counter:
        return ["None.", ""]
    out = ["| {} | Tokens |".format(header), "|---|---|"]
    out += ["| {} | {:,} |".format(label(name) if label else name, n) for name, n in counter.most_common(limit)]
    return out + [""]


def activity_table(rows, header):
    """Runs and the four counts summed over models, most tokens first."""
    if not rows:
        return ["None.", ""]
    summed = {name: [sum(v) for v in zip(*row["models"].values())] or [0] * len(FIELDS) for name, row in rows.items()}
    out = ["| {} | Runs | {} | Total |".format(header, " | ".join(label for _, label in FIELDS)),
           "|---|---|" + "---|" * (len(FIELDS) + 1)]
    for name in sorted(summed, key=lambda n: (-sum(summed[n]), natural(n))):
        values = summed[name]
        out.append("| {} | {:,} | {} | {:,} |".format(
            name, rows[name]["runs"], " | ".join("{:,}".format(v) for v in values), sum(values)))
    return out + [""]


def report(entries, since, until, root, loop_dir, costs=None, activity=None):
    groups = {name: {} for name, _ in GROUPS}
    models, sessions, issues = Counter(), Counter(), Counter()
    first_seen = {}
    total = subagents = 0
    where = {}
    for entry in entries:
        cwd = entry.get("cwd")
        key = cwd if isinstance(cwd, str) else None
        if key not in where:
            where[key] = group(entry, root, loop_dir)
        found = where[key]
        if found is None:
            continue
        values = tokens(entry)
        n = sum(values)
        name, row = found
        rows = groups[name]
        row = row or "This repo"
        rows[row] = [a + b for a, b in zip(rows.get(row, [0] * len(FIELDS)), values)]
        total += n
        model = entry["message"].get("model")
        models[model if isinstance(model, str) and model else "unknown"] += n
        if entry.get("_subagent"):
            subagents += n
        session = entry.get("sessionId")
        if isinstance(session, str) and session:
            sessions[session] += n
            day = str(entry.get("timestamp", ""))[:10]
            first_seen[session] = min(first_seen.get(session, day), day)
        if name == "Loop":
            issues[row] += n

    if not any(groups.values()) and not costs:
        return "No Claude Code usage under this repo since {}.".format(since)

    out = ["# Claude Code tokens, {} to {}".format(since, until), "",
           "Total: {:,} tokens across {} sessions.".format(total, len(sessions)), ""]
    for name, header in GROUPS:
        out += ["## {}".format(name), ""] + counts_table(groups[name], header)
    out += ["## By model", ""] + top_table(models, "Model", limit=None)
    share = 100 * subagents / total if total else 0
    out += ["## Subagents", "", "{:,} of {:,} tokens ({:.0f}%) were spent by subagents.".format(
        subagents, total, share), ""]
    out += ["## Top sessions", ""] + top_table(
        sessions, "Session", lambda s: "`{}`, first {}".format(s, first_seen[s]))
    out += ["## Top loop issues", ""] + top_table(issues, "Issue")
    if activity is not None:
        out += ["## By activity", "", "### Agents", ""] + activity_table(activity["agents"], "Agent")
        out += ["### Skills", ""] + activity_table(activity["skills"], "Skill") + [ATTRIBUTED, ""]
        out += ["### Commands", ""] + activity_table(activity["commands"], "Command") + [ATTRIBUTED, ""]
    out += ["## Loop cost", ""] + cost_table(costs)
    out.append("Claude Code sessions only. Dollars only for the loop's runs, as the loop recorded them at API prices.")
    return "\n".join(out)


def main(argv=None):
    today = datetime.date.today()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=since_date, default=(today - datetime.timedelta(days=14)).isoformat())
    parser.add_argument("--projects", default=str(Path.home() / ".claude" / "projects"),
                        help="Claude Code's transcripts folder, if not ~/.claude/projects")
    args = parser.parse_args(argv)
    projects, loops = Path(args.projects).expanduser(), loop_dirs(ROOT)
    entries = read(projects, args.since)
    print(report(entries, args.since, today.isoformat(), ROOT, loops, loop_costs(ROOT, args.since),
                 activity(projects, args.since, ROOT, loops)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
