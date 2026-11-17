#!/usr/bin/env python3
"""Check the control register, and say which controls a branch touches.

    python3 scripts/controls.py check                  # exit 1 if an entry is malformed or its evidence is gone
    python3 scripts/controls.py touched origin/main    # the controls whose evidence this branch changes

Both take --file <path>, default controls.json at the repo root. Evidence paths resolve against the
register's own folder. A path ending in / names a folder and matches any file under it; any other
path matches only that file. docs/controls.md says what each field and status means.
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUSES = ("core", "configured", "gap-customer", "gap-limit", "enhancement", "na")
TEXT_FIELDS = ("id", "framework", "name", "status", "summary")


def load(path):
    """The register's entries, or raise ValueError saying why it can't be read."""
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as err:
            raise ValueError("not valid JSON: {}".format(err))
    if not isinstance(data, list):
        raise ValueError("not a JSON array of controls")
    return data


def text(entry, field):
    """The field's value when it's a non-empty string, otherwise None."""
    value = entry.get(field) if isinstance(entry, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def label(entry, index):
    """How a line names an entry: its framework and id, or its place in the file counted from 1."""
    framework, ident = text(entry, "framework"), text(entry, "id")
    return "{} {}".format(framework, ident) if framework and ident else "entry {}".format(index + 1)


def evidence(entry):
    """The entry's evidence paths, or None when it has no non-empty list of strings."""
    value = entry.get("evidence") if isinstance(entry, dict) else None
    if not isinstance(value, list) or not value or not all(isinstance(p, str) and p for p in value):
        return None
    return value


def problems(entries, folder):
    """One line per problem, in register order. Empty means the register passes."""
    found, seen = [], set()
    for index, entry in enumerate(entries):
        name = label(entry, index)
        if not isinstance(entry, dict):
            found.append("{}: not a JSON object".format(name))
            continue
        for field in TEXT_FIELDS:
            if not text(entry, field):
                found.append("{}: missing {}".format(name, field))
        paths = evidence(entry)
        if paths is None:
            found.append("{}: missing evidence, a non-empty list of paths".format(name))
        status = text(entry, "status")
        if status and status not in STATUSES:
            found.append("{}: status '{}' is not one of {}".format(name, status, ", ".join(STATUSES)))
        if status == "configured" and not text(entry, "setup"):
            found.append("{}: status configured needs a setup".format(name))
        key = (text(entry, "framework"), text(entry, "id"))
        if all(key):
            if key in seen:
                found.append("{}: id repeats within {}".format(name, key[0]))
            seen.add(key)
        for path in paths or []:
            if not os.path.exists(os.path.join(folder, path)):
                found.append("{}: evidence not found: {}".format(name, path))
    return found


def check(path):
    try:
        entries = load(path)
    except FileNotFoundError:
        print("{}: not found".format(path))
        return 1
    except ValueError as err:
        print("{}: {}".format(os.path.basename(path), err))
        return 1
    found = problems(entries, os.path.dirname(path))
    for line in found:
        print(line)
    if found:
        return 1
    count = len(entries)
    print("{}: {} control{}, all evidence present".format(os.path.basename(path), count, "" if count == 1 else "s"))
    return 0


def matches(changed, path):
    """True when a changed file is this evidence path, or sits under it when the path ends in /."""
    return changed.startswith(path) if path.endswith("/") else changed == path


def touched(path, base):
    if not os.path.isfile(path):
        print("no {}".format(os.path.basename(path)))
        return 0
    try:
        entries = load(path)
    except ValueError as err:
        print("{}: {}".format(os.path.basename(path), err))
        return 1
    if base.startswith("-"):
        print("controls.py: the base must be a branch or commit, not an option: {}".format(base))
        return 1
    done = subprocess.run(["git", "diff", "--name-only", "--no-renames", "{}...HEAD".format(base)],
                          cwd=os.path.dirname(path), capture_output=True, text=True)
    if done.returncode:
        print("controls.py: git diff against {} failed: {}".format(base, done.stderr.strip()), file=sys.stderr)
        return 1
    changed = [line for line in done.stdout.splitlines() if line]
    hits = []
    for index, entry in enumerate(entries):
        name = label(entry, index)
        if name not in hits and any(matches(c, p) for c in changed for p in evidence(entry) or []):
            hits.append(name)
    print("\n".join(hits) if hits else "none")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name, helptext in (("check", "exit 1 if an entry is malformed or its evidence is gone"),
                           ("touched", "list the controls whose evidence changed since <base>")):
        sub = commands.add_parser(name, help=helptext)
        if name == "touched":
            sub.add_argument("base", help="the branch the change merges into, such as origin/main")
        sub.add_argument("--file", help="the register, default controls.json at the repo root")
    args = parser.parse_args(argv)
    path = os.path.abspath(args.file or os.path.join(ROOT, "controls.json"))
    return check(path) if args.command == "check" else touched(path, args.base)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
