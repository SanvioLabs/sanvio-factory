#!/usr/bin/env python3
"""List the Claude Code plugins and mods this harness runs with, as Markdown.

    python3 scripts/plugin_report.py
    python3 scripts/plugin_report.py --previous reports/usage/2026-10-10-pat.md

Runs `claude plugin list --json` and keeps the enabled plugins and mods that
apply here: installed for the user, or for this harness's folder. Each prints as
its id, version and scope, and nothing else: no install folder and no path. With
--previous, a harness report from an earlier sprint, it also says which plugins
changed version, arrived or went since that report's date, read from the
report's own table. Claude Code only. If claude isn't installed or its answer
isn't JSON, it prints one line saying so and still exits 0, so a report can be
written without it. The skills/factory-trends/ skill runs this next to
token_report.py.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADING = "## Plugins and mods"
FAILED = "Couldn't read plugin versions"


def installed():
    """[(id, version, scope)] for the enabled plugins that apply to this harness, sorted by id then scope.

    One plugin can be registered at more than one scope, user and project say, at different versions, and
    both load. Each shows as its own row rather than one hiding the other."""
    try:
        result = subprocess.run(["claude", "plugin", "list", "--json"], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise ValueError("claude isn't installed")
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("claude didn't answer ({})".format(type(error).__name__))
    if result.returncode != 0:
        raise ValueError("claude exited with {}".format(result.returncode))
    try:
        found = json.loads(result.stdout)
    except ValueError:
        raise ValueError("claude's answer wasn't JSON")
    if not isinstance(found, list):
        raise ValueError("claude's answer wasn't a list")
    rows = {}
    for record in found:
        if not isinstance(record, dict) or record.get("enabled") is not True or not applies(record.get("projectPath")):
            continue
        name = record.get("id")
        if isinstance(name, str) and name:
            scope = text(record.get("scope"))
            rows[(name, scope)] = (name, text(record.get("version")), scope)
    return [rows[name] for name in sorted(rows)]


def applies(project_path):
    """True for a plugin with no project folder, or whose project folder is this harness."""
    if project_path is None:
        return True
    if not isinstance(project_path, str):
        return False
    try:
        return Path(project_path).resolve() == ROOT
    except (OSError, RuntimeError, ValueError):
        return False


def text(value):
    return value if isinstance(value, str) and value else "unknown"


def table(rows):
    if not rows:
        return ["None.", ""]
    out = ["| Plugin | Version | Scope |", "|---|---|---|"]
    return out + ["| {} | {} | {} |".format(*row) for row in rows] + [""]


def earlier(path):
    """(date, {(id, scope): version}) from a harness report's plugin table, or None when it has none, or
    when that report couldn't read the versions."""
    match = re.match(r"(\d{4}-\d{2}-\d{2})", Path(path).name)
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not match or HEADING not in lines:
        return None
    versions = {}
    for line in lines[lines.index(HEADING) + 1:]:
        if line.startswith("#"):
            break
        if line.startswith(FAILED):
            return None
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == 3 and cells[0] != "Plugin" and not set(cells[0]) <= {"-", ":"}:
            versions[(cells[0], cells[2])] = cells[1]
    return match.group(1), versions


def changes(before, rows):
    """The plugins that changed version, are new, or are gone, as short phrases in id order. A plugin
    registered at more than one scope, then or now, is named with the scope that changed."""
    now = {(name, scope): version for name, version, scope in rows}
    keys = set(before) | set(now)
    twice = {name for name, _ in keys if sum(1 for other, _ in keys if other == name) > 1}
    out = []
    for key in sorted(keys):
        name, scope = key
        label = "{} ({})".format(name, scope) if name in twice else name
        if key not in before:
            out.append("{} (new)".format(label))
        elif key not in now:
            out.append("{} (gone)".format(label))
        elif before[key] != now[key]:
            out.append("{} {} → {}".format(label, before[key], now[key]))
    return out


def report(rows, previous):
    out = [HEADING, ""] + table(rows)
    found = earlier(previous) if previous else None
    if found is None:
        out.append("No earlier report to compare with.")
    else:
        date, before = found
        changed = changes(before, rows)
        out.append("Changed since {}: {}".format(date, ", ".join(changed)) if changed
                   else "Nothing changed since {}.".format(date))
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--previous", help="an earlier harness report, to say what changed since")
    args = parser.parse_args(argv)
    try:
        print(report(installed(), args.previous))
    except ValueError as error:
        # Under the heading, so the next report finds the section and knows there was nothing to compare.
        print("\n".join([HEADING, "", "{}: {}.".format(FAILED, error)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
