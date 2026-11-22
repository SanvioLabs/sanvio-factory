#!/usr/bin/env python3
"""Bundle your loop and usage numbers into one JSON file, kept on this machine.

    python3 scripts/export.py                         # the last 14 days, printed
    python3 scripts/export.py --since 2026-10-01 --out reports/usage/export.json
    python3 scripts/export.py --mode detailed         # with your shell commands, while detailed mode is on

The bundle is format v2 (SPEC-004), checked against scripts/usage_shape.py before it's written. It holds:

- `v`, `kind`, `mode`: the format version, "bundle", and "general" or "detailed"
- `exported`, `since`, `period`: today's date, the first day counted, and the first and last days counted
- `user`: the same cleaned name your usage log's filename uses, so no new identifier
- `node`: the `node` in .sanvio/export.json, else this machine's host name
- `factory`: this repo's commit, read from .git without running git, and the date of CHANGELOG.md's top entry
- `loop_config`: for the factory's own loop, as "factory", and for each project .sanvio/export.json lists, the
  agent and reviewer by name and model, and max_workers, max_rounds and max_issue_tokens. Never a command
  line, a path or anything else in loop.json
- `chain_head`: the hash of your usage log's last line, so the store can tell when a log changed between sends
- `bundle_id`: a hash of user, node, mode and period, the same each time the same period is exported
- `loop`: the lines of .loop/history.jsonl since that day, each rebuilt from the keys scripts/loop.py writes
  and nothing else. The factory's own loop, and a project's runs only where .sanvio/export.json's
  `export_projects` lists that project's folder, under the label it gives. With no list, no project's runs
- `usage`: counts from your usage log, .sanvio/usage/<you>.jsonl: sessions, then skills, agents and slash
  commands by name, guard refusals by rule, and guard asks and the asks you said yes to by tool (or by rule
  when there's no tool), and `log_off`, how many sessions started with SANVIO_USAGE_LOG=off

- `commands`, in a detailed bundle only: your shell commands since that day from
  .sanvio/usage/<you>.commands.jsonl, each with its time, session, whether it ran or the guard refused or asked,
  its text as the hook scrubbed it, and how many redactions that took. Refused unless detailed mode is on

Nothing sends it. It only reads, prints or writes the one file you name. This shape is the only one any later
sender may send: anything not in it stays on this machine.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shlex
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import log_chain  # noqa: E402 (needs scripts/ on the path first)
import names  # noqa: E402 (same reason)
import usage_report  # noqa: E402 (same reason)
import usage_log  # noqa: E402 (same reason: usage_report put .claude/hooks/ on the path)
import usage_shape  # noqa: E402 (same reason)
from usage_report import log_path  # noqa: E402 (same reason)

# The keys record_run in scripts/loop.py writes. Any other key on a history line is dropped.
LOOP_KEYS = usage_shape.LOOP_RUN_KEYS
FACTORY_LABEL = "factory"  # the factory's own loop, in loop_config
COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
CHANGELOG_DAY = re.compile(r"^## (\d{4}-\d{2}-\d{2}):", re.M)


def config(root):
    """.sanvio/export.json as an object, or {} when it's missing or unreadable. It's gitignored: it names
    the store, this machine and the projects whose numbers may leave it."""
    try:
        found = json.loads((names.state_dir(root) / "export.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def listed_projects(cfg):
    """{project folder: label} from export_projects, keeping only text on both sides."""
    found = cfg.get("export_projects")
    if not isinstance(found, dict):
        return {}
    return {folder: label for folder, label in found.items()
            if isinstance(folder, str) and folder and "/" not in folder and isinstance(label, str) and label}


def history_lines(path, since, last=None):
    """The JSON object lines of one history file that ended from `since` to `last`, both days included, or
    with no `last`, on or after `since`. Unreadable lines are skipped."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for raw in text.splitlines():
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        day = str(line.get("ended", ""))[:10] if isinstance(line, dict) else ""
        if day >= since and (last is None or day <= last):
            out.append(line)
    return out


def loop_runs(root, since, projects=None, last=None):
    """The factory's own runs since `since`, then each listed project's from .loop/projects/<folder>/, with
    its project set to the label it's listed under. A line tagged with any other project is dropped."""
    runs = [{key: line.get(key) for key in LOOP_KEYS}
            for line in history_lines(Path(root) / ".loop" / "history.jsonl", since, last)
            if line.get("project") is None]
    for folder, label in sorted((projects or {}).items()):
        for line in history_lines(Path(root) / ".loop" / "projects" / folder / "history.jsonl", since, last):
            if line.get("project") == folder:
                runs.append(dict({key: line.get(key) for key in LOOP_KEYS}, project=label))
    return runs


def agent_label(value):
    """An agent setting as a name and model, never its command line: claude:claude-opus-5-5 stays as it is,
    and "claude -p --model sonnet" becomes claude:sonnet. None when there's nothing to name."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        words = shlex.split(value)
    except ValueError:
        return None
    words = [w for w in words if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w)]  # an env assignment in front
    if not words:
        return None
    first = words[0] if ":" in words[0] and "/" not in words[0] else os.path.basename(words[0])
    model = next((words[i + 1] for i, w in enumerate(words[:-1]) if w == "--model"), None)
    label = first if not model or ":" in first else first + ":" + model
    return label[:100]


def whole(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def loop_config(root, projects=None):
    """The settings that explain a run's cost and rounds, for the factory's own loop and each listed project:
    a project's entry in the factory's loop.json over the top-level values. Keys loop.json doesn't set are None."""
    try:
        found = json.loads((Path(root) / "loop.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        found = {}
    found = found if isinstance(found, dict) else {}
    entries = found.get("projects") if isinstance(found.get("projects"), dict) else {}

    def settings(cfg):
        return {"agent": agent_label(cfg.get("agent")), "reviewer": agent_label(cfg.get("review_agent")),
                "max_workers": whole(cfg.get("max_workers")), "max_rounds": whole(cfg.get("max_rounds")),
                "max_issue_tokens": whole(cfg.get("max_issue_tokens"))}

    out = {FACTORY_LABEL: settings(found)}
    for folder, label in sorted((projects or {}).items()):
        entry = entries.get(folder) if isinstance(entries.get(folder), dict) else {}
        out[label] = settings(dict(found, **entry))
    return out


def git_dir(root):
    """This checkout's git folder, following a worktree's .git file, or None."""
    git = Path(root) / ".git"
    if git.is_file():
        text = git.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir:"):
            return None
        git = (Path(root) / text[len("gitdir:"):].strip()).resolve()
    return git if git.is_dir() else None


def head_commit(root):
    """HEAD's commit, read from git's own files, since this script never starts a process. None if unreadable."""
    try:
        git = git_dir(root)
        if git is None:
            return None
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            return head if COMMIT.match(head) else None
        ref = head[len("ref:"):].strip()
        common = git
        if (git / "commondir").is_file():
            common = (git / (git / "commondir").read_text(encoding="utf-8").strip()).resolve()
        for base in (git, common):
            if (base / ref).is_file():
                found = (base / ref).read_text(encoding="utf-8").strip()
                return found if COMMIT.match(found) else None
        packed = common / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref and COMMIT.match(parts[0]):
                    return parts[0]
    except OSError:
        pass
    return None


def changelog_day(root):
    try:
        found = CHANGELOG_DAY.search((Path(root) / "CHANGELOG.md").read_text(encoding="utf-8"))
    except OSError:
        return None
    return found.group(1) if found else None


def node_name(cfg):
    if isinstance(cfg.get("node"), str) and cfg["node"].strip():
        return cfg["node"].strip()[:100]
    if hasattr(os, "uname"):
        return os.uname().nodename or "unknown"
    return os.environ.get("COMPUTERNAME") or "unknown"


def chain_head(root):
    last = log_chain.last_line(log_path(root))
    return log_chain.digest(last) if last else None


def by_tool(lines, kind):
    """How often each tool appears on lines of this event kind, by rule when a line has no tool, as report() keys them."""
    return Counter(l.get("tool") or l.get("rule", "") for l in lines if l.get("event") == kind)


def until(lines, last):
    """The log lines whose day is `last` or earlier; all of them with no `last`."""
    return lines if last is None else [l for l in lines if str(l.get("ts", ""))[:10] <= last]


def usage_counts(root, since, last=None):
    lines = until(usage_report.read(log_path(root), since), last)
    return {"sessions": len({l.get("session") for l in lines if l.get("session")}),
            "skills": dict(usage_report.count(lines, "skill", "name")),
            "agents": dict(usage_report.count(lines, "agent", "name")),
            "commands": dict(usage_report.count(lines, "command", "name")),
            "guard_deny": dict(usage_report.count(lines, "guard_deny", "rule")),
            "guard_ask": dict(by_tool(lines, "guard_ask")),
            "ask_approved": dict(by_tool(lines, "ask_approved")),
            "log_off": sum(1 for l in lines if l.get("event") == "log_off")}


COMMAND_KEYS = tuple(usage_shape.COMMAND.keys)


def commands_since(root, since, last=None):
    """Detailed mode's command lines from `since` to `last`, each rebuilt from the shape's keys and nothing else."""
    return [{key: line.get(key) for key in COMMAND_KEYS}
            for line in until(usage_report.read(usage_log.commands_path(root), since), last)]


def bundle(root, since, today, mode="general", last=None):
    """A v2 bundle, general or detailed, of the days from `since` to `last` (today when it's None), written
    today. Raises ValueError, naming each problem, if it isn't in usage_shape's shape, and for a detailed one
    with no live opt-in."""
    last = last or today
    cfg = config(root)
    projects = listed_projects(cfg)
    user, node = log_path(root).stem, node_name(cfg)
    if mode == "detailed":
        now = datetime.datetime.combine(datetime.date.fromisoformat(today), datetime.time(), datetime.timezone.utc)
        if usage_log.detailed_until(root, now) is None:
            raise ValueError("detailed mode isn't on; python3 scripts/send_usage.py --opt-in detailed turns it on")
    found = {"v": usage_shape.V, "kind": "bundle", "mode": mode, "exported": today, "since": since,
             "period": {"first": since, "last": last}, "user": user, "node": node,
             "factory": {"commit": head_commit(root), "changelog": changelog_day(root)},
             "loop_config": loop_config(root, projects), "chain_head": chain_head(root),
             "bundle_id": hashlib.sha256("|".join((user, node, mode, since, last)).encode("utf-8")).hexdigest(),
             "loop": loop_runs(root, since, projects, last), "usage": usage_counts(root, since, last)}
    if mode == "detailed":
        found["commands"] = commands_since(root, since, last)
    problems = usage_shape.problems(found)
    if problems:
        raise ValueError("the bundle isn't in the v2 shape: " + "; ".join(problems[:10]))
    return found


def main(argv=None):
    today = datetime.date.today()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=usage_report.since_date,
                        default=(today - datetime.timedelta(days=14)).isoformat(),
                        help="the first day to count, as YYYY-MM-DD (default: 14 days ago)")
    parser.add_argument("--out", help="a file to write the bundle to, instead of printing it")
    parser.add_argument("--mode", choices=("general", "detailed"), default="general",
                        help="detailed adds your shell commands, while detailed mode is on (default: general)")
    args = parser.parse_args(argv)
    try:
        text = json.dumps(bundle(ROOT, args.since, today.isoformat(), args.mode), indent=2) + "\n"
    except ValueError as err:
        print("Nothing written: {}".format(err), file=sys.stderr)
        return 1
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
