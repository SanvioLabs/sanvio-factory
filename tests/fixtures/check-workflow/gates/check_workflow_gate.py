#!/usr/bin/env python3
"""Quote review gate: refuses a review that doesn't trace to its sources.

Run from the workflow's folder:

    python3 gates/check_workflow_gate.py <output.md>

Prints PASS and exits 0, or prints each problem and exits 1. Standard library
only, Python 3.9+. A test fixture for scripts/check_workflow.py.
"""
import re
import sys
from pathlib import Path

FOLDER = Path(__file__).resolve().parent.parent
CITATION = re.compile(r"\bS(\d+)\b")
RULE = re.compile(r"^S(\d+)\.", re.M)
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def split(text):
    """(the frontmatter's key: value pairs, the body). No frontmatter gives ({}, text)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    fields = {}
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return fields, "\n".join(lines[i + 1:])
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return {}, text


def check(path):
    """Every problem with this output. An empty list means it passes."""
    text = Path(path).read_text()
    fields, body = split(text)
    problems = []
    for number, line in enumerate(text.splitlines(), 1):
        if "{{" in line:
            problems.append("line {}: template text left in: {}".format(number, line.strip()))

    sources = [s.strip() for s in fields.get("sources", "").split(",") if s.strip()]
    if not sources:
        problems.append("no sources: line in the frontmatter")
    source_text = ""
    for source in sources:
        if (FOLDER / source).is_file():
            source_text += (FOLDER / source).read_text()
        else:
            problems.append("source not found: " + source)

    standard = fields.get("standard", "")
    rules = set()
    if not standard:
        problems.append("no standard: line in the frontmatter")
    elif not (FOLDER / standard).is_file():
        problems.append("standard not found: " + standard)
    else:
        rules = set(RULE.findall((FOLDER / standard).read_text()))
        for number in sorted(set(CITATION.findall(body)) - rules, key=int):
            problems.append("cites S{}, which isn't in the standard".format(number))

    for date in sorted(set(DATE.findall(body))):
        if date not in source_text:
            problems.append("date {} isn't in any source".format(date))

    if not re.search(r"^Approved by:", body, re.M) or not re.search(r"^Date:", body, re.M):
        problems.append("no approval lines: it ends with Approved by: and Date:")
    return problems


def main(argv):
    if len(argv) != 1:
        print("usage: python3 gates/check_workflow_gate.py <output.md>")
        return 1
    if not Path(argv[0]).is_file():
        print("no such file: " + argv[0])
        return 1
    problems = check(argv[0])
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
