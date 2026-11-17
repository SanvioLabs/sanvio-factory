#!/usr/bin/env python3
"""Check a blueprint against *The blueprint* in docs/building-workflows.md.

    python3 scripts/check_blueprint.py blueprints/<name>.md

Reads the frontmatter between the first two `---` lines, as plain `key: value`
lines. Every key the doc lists is present; one nobody could answer is empty and
named in `gaps`, and one named in `gaps` is empty. `name` is the file name
without `.md`, and `standard_status` and `outcome` each hold one of their listed
values. Keys beyond the listed ones are allowed.

Prints PASS and exits 0, or prints each problem on its own line and exits 1. A
missing argument or a file that can't be read prints usage and exits 2. It never
writes anything. Standard library only, Python 3.9+.

From Sanvio Factory by Sanvio Labs, MIT: https://github.com/SanvioLabs/sanvio-factory
"""
import sys
from pathlib import Path

# In the doc's order.
KEYS = ["name", "owner", "trigger", "inputs", "inputs_live", "frequency", "rules", "standard_status",
        "output", "done", "does", "approves", "receives", "went_wrong", "never", "today", "measure",
        "systems", "incumbent", "restricted_data", "outcome", "gaps"]
STANDARD_STATUSES = ("written", "not-written")
OUTCOMES = ("build", "write-standard", "no-fit")
# Always answered, so never a gap: the interview settles the first and the skill sets the second.
SET_KEYS = ("standard_status", "outcome")
USAGE = "usage: python3 scripts/check_blueprint.py blueprints/<name>.md"


def frontmatter(text):
    """The key: value pairs between the first two --- lines, or None when there are none."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return None


def listed(value):
    """The items of a one-line, comma-separated list."""
    return [item.strip() for item in value.split(",") if item.strip()]


def problems(path, text):
    fields = frontmatter(text)
    if fields is None:
        return ["no frontmatter: the file starts with --- and the frontmatter ends with ---"]
    found = []
    for key in KEYS:
        if key not in fields:
            found.append("{}: missing".format(key))
    gaps = listed(fields.get("gaps", ""))
    for item in gaps:
        if item not in KEYS:
            found.append("gaps: {} isn't a blueprint key".format(item))
    for key in KEYS:
        if key not in fields or key == "gaps" or key in SET_KEYS:
            continue
        if not fields[key] and key not in gaps:
            found.append("{}: empty and not named in gaps".format(key))
    for item in gaps:
        if item in KEYS and fields.get(item):
            found.append("{}: named in gaps but has a value".format(item))
    if "name" in fields and fields["name"] != path.stem:
        found.append("name: {} doesn't match the file name {}".format(fields["name"], path.stem))
    if "standard_status" in fields and fields["standard_status"] not in STANDARD_STATUSES:
        found.append("standard_status: '{}' isn't written or not-written".format(fields["standard_status"]))
    if "outcome" in fields and fields["outcome"] not in OUTCOMES:
        found.append("outcome: '{}' isn't build, write-standard or no-fit".format(fields["outcome"]))
    return found


def main(argv):
    if len(argv) != 1:
        print(USAGE, file=sys.stderr)
        return 2
    path = Path(argv[0])
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print("{}: can't read it ({})".format(path, error), file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2
    found = problems(path, text)
    if found:
        for line in found:
            print(line)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
