#!/usr/bin/env python3
"""Proposal gate: blocks a proposal that isn't ready for a human to send.

Usage:
    python3 gates/proposal_gate.py [proposal.md ...]

With no arguments it checks every file in proposals/. Exits 0 when every file
passes and 1 when any fails, so a hook or CI can block on it.

From Sanvio Factory by Sanvio Labs, MIT: https://github.com/SanvioLabs/sanvio-factory
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_SECTIONS = ["Problem", "Scope", "Out of scope", "Fees", "Assumptions"]
PLACEHOLDER = re.compile(r"\{\{|\bTODO\b|\bTBD\b")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def money(text):
    return float(text.replace("$", "").replace(",", "").strip())


def section(text, name):
    """The body of one ## section, or an empty string."""
    match = re.search(r"^##\s+" + re.escape(name) + r"\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    return match.group(1) if match else ""


def check(path, rates):
    """Every reason this proposal isn't ready. An empty list means it passes."""
    text = Path(path).read_text()
    problems = []

    for number, line in enumerate(text.splitlines(), 1):
        if PLACEHOLDER.search(line):
            problems.append("line {}: unfinished: {}".format(number, line.strip()))

    headings = {h.strip() for h in re.findall(r"^##\s+(.+)$", text, re.M)}
    for name in REQUIRED_SECTIONS:
        if name not in headings:
            problems.append("missing section: " + name)
        elif name != "Fees" and not HTML_COMMENT.sub("", section(text, name)).strip():
            problems.append("empty section: " + name)  # Fees has its own check below

    roles = rates["roles"]
    total = 0.0
    rows = 0
    for line in section(text, "Fees").splitlines():
        line = line.strip()
        if not line.startswith("|") or PLACEHOLDER.search(line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 4 or cells[0] == "Role" or set(cells[0]) <= set("-: "):
            continue
        role, hours, rate, amount = cells
        rows += 1
        if role not in roles:
            problems.append("fee row '{}': not a role in data/rates.json".format(role))
            continue
        try:
            hours, rate, amount = float(hours), money(rate), money(amount)
        except ValueError:
            problems.append("fee row '{}': hours, rate and amount must be numbers".format(role))
            continue
        if rate != roles[role]:
            problems.append("fee row '{}': rate {:g} is not the rate card's {}".format(role, rate, roles[role]))
        if abs(hours * rate - amount) > 0.005:
            problems.append("fee row '{}': {:g} x {:g} is {:,.2f}, not {:,.2f}".format(
                role, hours, rate, hours * rate, amount))
        total += amount
    if rows == 0 and "Fees" in headings:
        problems.append("no fee rows under Fees")

    stated = re.search(r"\*\*Total:\s*([^*]+)\*\*", text)
    if not stated:
        problems.append("no **Total: ...** line")
    elif not PLACEHOLDER.search(stated.group(0)):
        try:
            value = money(stated.group(1))
        except ValueError:
            problems.append("total is not a number: " + stated.group(1).strip())
        else:
            if abs(value - total) > 0.005:
                problems.append("total says {:,.2f} but the fee rows add to {:,.2f}".format(value, total))
            if value < rates["minimum_fee"]:
                problems.append("total {:,.2f} is under the minimum fee of {:,}".format(value, rates["minimum_fee"]))

    return problems


def main(argv):
    rates = json.loads((ROOT / "data" / "rates.json").read_text())
    paths = [Path(a) for a in argv] or sorted((ROOT / "proposals").glob("*.md"))
    if not paths:
        print("no proposals to check")
        return 0
    failed = 0
    for path in paths:
        problems = check(path, rates)
        print("{} {}".format("FAIL" if problems else "PASS", path))
        for problem in problems:
            print("  - " + problem)
        failed += bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
