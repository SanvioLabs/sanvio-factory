#!/usr/bin/env python3
"""List the workflows in workflows/, and show one that may run in a given mode.

    python3 scripts/workflows.py list [--dir D]
    python3 scripts/workflows.py show <name> [--dir D] [--as chat|loop|schedule]

`list` prints one tab-separated line per D/*/workflow.json: name, owner, status
and runs. `show` prints the workflow's manifest as JSON, with its paths
relative to the harness root, or exits 1 with the reason on stderr when the
workflow isn't there or may not run that way: the mode isn't in its `runs`, it's
`retired`, or it's run `--as schedule` and its `restricted_data` isn't `none`.
The run-workflow skill runs `show` before anything else. Neither command writes
a file. Standard library only, Python 3.9+.

From Sanvio Factory by Sanvio Labs, MIT: https://github.com/SanvioLabs/sanvio-factory
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODES = ("chat", "loop", "schedule")
PATH_KEYS = ["inputs", "output", "standard", "skill", "gate", "reviewer", "template", "blueprint"]


def read_manifest(path):
    """(manifest, None), or (None, why it can't be read)."""
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as err:
        return None, "{} can't be read: {}".format(path, err)
    if not isinstance(manifest, dict):
        return None, "{} isn't a JSON object".format(path)
    return manifest, None


def runs_of(manifest):
    runs = manifest.get("runs")
    return [r for r in runs if isinstance(r, str)] if isinstance(runs, list) else []


def refusal(manifest, mode):
    """Why the workflow may not run in this mode, or None if it may."""
    if manifest.get("status") == "retired":
        return "it's retired"
    if mode not in runs_of(manifest):
        return "its runs don't list {}".format(mode)
    if mode == "schedule" and manifest.get("restricted_data") != "none":
        return "it touches restricted data ({}), so it never runs on a schedule".format(
            manifest.get("restricted_data", "not stated"))
    return None


def from_root(folder, value):
    """A manifest path, resolved against the workflow folder and written relative to ROOT."""
    target = os.path.normpath(os.path.join(str(folder), value))
    relative = Path(os.path.relpath(target, str(ROOT))).as_posix()
    return relative + "/" if value.endswith("/") and not relative.endswith("/") else relative


def list_workflows(where):
    manifests = sorted(p for p in where.glob("*/workflow.json") if p.is_file())
    if not manifests:
        print("no workflows in {}".format(where))
        return 0
    for path in manifests:
        manifest, problem = read_manifest(path)
        if problem:
            print(problem, file=sys.stderr)
            continue
        print("\t".join([str(manifest.get("name", path.parent.name)), str(manifest.get("owner", "")),
                         str(manifest.get("status", "")), ",".join(runs_of(manifest))]))
    return 0


def show(where, name, mode):
    path = where / name / "workflow.json"
    if not name or "/" in name or "\\" in name or ".." in name or not path.is_file():
        print("no workflow named {} in {}".format(name, where), file=sys.stderr)
        return 1
    manifest, problem = read_manifest(path)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    why = refusal(manifest, mode)
    if why:
        print("{} can't run --as {}: {}".format(name, mode, why), file=sys.stderr)
        return 1
    for key in PATH_KEYS:
        if isinstance(manifest.get(key), str) and manifest[key]:
            manifest[key] = from_root(path.parent, manifest[key])
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description="List the workflows, or show one that may run in a given mode.")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="one line per workflow: name, owner, status, runs")
    listing.add_argument("--dir", default=str(ROOT / "workflows"), help="the folder of workflows")
    showing = commands.add_parser("show", help="print a workflow's manifest, or why it may not run")
    showing.add_argument("name")
    showing.add_argument("--dir", default=str(ROOT / "workflows"), help="the folder of workflows")
    showing.add_argument("--as", dest="mode", choices=MODES, default="chat", help="how it was started")
    args = parser.parse_args(argv)
    where = Path(args.dir).resolve()
    if args.command == "list":
        return list_workflows(where)
    return show(where, args.name, args.mode)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
