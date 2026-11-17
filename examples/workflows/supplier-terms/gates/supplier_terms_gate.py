#!/usr/bin/env python3
"""Supplier terms gate: refuses a terms review that doesn't trace to its agreement.

Run from the workflow's folder:

    python3 gates/supplier_terms_gate.py <output.md>

Prints PASS and exits 0, or prints each problem and exits 1. Standard library
only, Python 3.9+.

A review is Markdown with `sources:` (the agreement and its price list) and
`standard:` in its frontmatter. It cites a clause as `<agreement>.md, clause 6.3`
and a price list entry as `<prices>.json, item 2`. The gate checks:

- the sources and the standard exist, every cited rule is in the standard, and
  every rule in the standard has a line
- every cited clause or item exists, in a file the review names as a source
- every clause that mentions renewal or a minimum order is cited, wherever it
  sits in the agreement
- every item where the price list and the agreement differ is named on a line
  that says "Not met"
- every date appears in a source, and every $ amount is one a source or the
  standard gives as money: a clause number or a weight isn't one
- every blank in an agreement is quoted under Could not confirm
- no template text is left in, nothing is written to the supplier, and the
  approval lines are there and blank

From Sanvio Factory by Sanvio Labs, MIT: https://github.com/SanvioLabs/sanvio-factory
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

FOLDER = Path(__file__).resolve().parent.parent
RULE = re.compile(r"^S(\d+)\.", re.M)
CITED_RULE = re.compile(r"\bS(\d+)\b")
CLAUSE = re.compile(r"^(?:#{1,6}\s+)?(\d+(?:\.\d+)*)\.?\s")
CITED_CLAUSE = re.compile(r"([\w./-]+\.md), clause (\d+(?:\.\d+)*)")
CITED_ITEM = re.compile(r"([\w./-]+\.json), item (\d+)")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
AMOUNT = re.compile(r"\$(\d[\d,]*(?:\.\d+)?)")
BLANK = re.compile(r"_{4,}")
PRICE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*\$(\d[\d,]*(?:\.\d+)?)\s*\|")
TO_SUPPLIER = re.compile(r"^(Dear |To:|Subject:)", re.M)
# A clause holding one of these words is cited, wherever it sits: the renewal
# nobody spotted was under "General".
WATCH = (("renew", "mentions renewal"), ("minimum", "sets a minimum order"))


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


def clause_lines(text):
    """(the clause it sits in, or None, and the line) for each line of an agreement's body."""
    current = None
    found = []
    for line in split(text)[1].splitlines():
        match = CLAUSE.match(line)
        if match:
            current = match.group(1)
        found.append((current, line))
    return found


def order(clause):
    return tuple(int(part) for part in clause.split("."))


def number(text):
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def cites(text, source, clause):
    """True when text cites that clause of that source, and not a longer number that starts the same."""
    return re.search(re.escape("{}, clause {}".format(source, clause)) + r"(?!\.?\d)", text) is not None


def section(body, title):
    match = re.search(r"^## {}\s*$(.*?)(?=^## |\Z)".format(re.escape(title)), body, re.M | re.S)
    return match.group(1) if match else ""


def check_rules(body, standard_text):
    rules = RULE.findall(standard_text)
    cited = set(CITED_RULE.findall(body))
    problems = ["cites S{}, which isn't in the standard".format(n) for n in sorted(cited - set(rules), key=int)]
    problems += ["S{} has no line in the review".format(n) for n in rules if n not in cited]
    return problems


def check_citations(body, texts, agreements, price_lists):
    problems = []
    for source, clause in CITED_CLAUSE.findall(body):
        if source not in texts:
            problems.append("cites {}, which isn't in its sources".format(source))
        elif source in agreements and clause not in {c for c, _ in agreements[source] if c}:
            problems.append("cites clause {} of {}, which has no clause {}".format(clause, source, clause))
    for source, item in CITED_ITEM.findall(body):
        if source not in texts:
            problems.append("cites {}, which isn't in its sources".format(source))
        elif source in price_lists:
            items = price_lists[source].get("items") or []
            if not 1 <= int(item) <= len(items):
                problems.append("cites item {} of {}, which has {} items".format(item, source, len(items)))
    return problems


def check_agreements(body, agreements):
    """Watched clauses are cited, and blanks are quoted under Could not confirm."""
    problems = []
    unsure = section(body, "Could not confirm")
    for source, lines in agreements.items():
        for word, what in WATCH:
            for clause in sorted({c for c, line in lines if c and word in line.lower()}, key=order):
                if not cites(body, source, clause):
                    problems.append("clause {} of {} {}, and the review doesn't cite it".format(clause, source, what))
        for clause in sorted({c for c, line in lines if c and BLANK.search(line)}, key=order):
            if not cites(unsure, source, clause):
                problems.append("clause {} of {} has a blank, and the review doesn't quote it under Could not "
                                "confirm".format(clause, source))
    return problems


def check_prices(body, price_lists):
    """Every item where a price list and its agreement differ is flagged as not met."""
    problems = []
    for source, data in price_lists.items():
        agreement = data.get("agreement")
        if not isinstance(agreement, str) or not (FOLDER / agreement).is_file():
            problems.append("{} names no agreement that exists".format(source))
            continue
        listed = {}
        for line in split((FOLDER / agreement).read_text())[1].splitlines():
            match = PRICE_ROW.match(line)
            if match:
                listed[match.group(1)] = number(match.group(2))
        for entry in data.get("items") or []:
            if not isinstance(entry, dict) or not isinstance(entry.get("item"), str):
                continue
            item = entry["item"]
            if listed.get(item) == number(str(entry.get("price", ""))):
                continue
            if not any(item in line and "Not met" in line for line in body.splitlines()):
                problems.append('the price list and the agreement differ on "{}", and the review doesn\'t flag '
                                "it as not met".format(item))
    return problems


def known_amounts(texts, price_lists, standard_text):
    """Every amount a source or the standard gives as money: a $ amount, or a price in a price list.

    A bare number, such as a clause number, a weight or a count of days, isn't one, so a
    review can't turn "14 days" into $14.
    """
    known = {number(a) for a in AMOUNT.findall("\n".join(list(texts.values()) + [standard_text]))}
    for data in price_lists.values():
        for entry in data.get("items") or []:
            if isinstance(entry, dict) and isinstance(entry.get("price"), (str, int, float)):
                known.add(number(str(entry["price"])))
    return known - {None}


def check_values(body, source_text, known):
    """Every date is in a source, and every amount is one a source or the standard gives."""
    problems = []
    for date in sorted(set(DATE.findall(body))):
        if date not in source_text:
            problems.append("date {} isn't in any source".format(date))
    for amount in AMOUNT.findall(body):
        if number(amount) not in known:
            problems.append("amount ${} isn't in any source".format(amount))
    return problems


def check_approval(body):
    if TO_SUPPLIER.search(body):
        problems = ["the review writes to the supplier, and it never drafts or sends a message to one"]
    else:
        problems = []
    approved = re.search(r"^Approved by:(.*)$", body, re.M)
    dated = re.search(r"^Date:(.*)$", body, re.M)
    if not approved or not dated:
        return problems + ["no approval lines: it ends with Approved by: and Date:"]
    for match in (approved, dated):
        if match.group(1).strip():
            problems.append("approval line filled in: {}".format(match.group(0).strip()))
    return problems


def check(path):
    """Every problem with this output. An empty list means it passes."""
    text = Path(path).read_text()
    fields, body = split(text)
    problems = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if "{{" in line:
            problems.append("line {}: template text left in: {}".format(line_number, line.strip()))

    sources = [s.strip() for s in fields.get("sources", "").split(",") if s.strip()]
    if not sources:
        problems.append("no sources: line in the frontmatter")
    texts = {}
    for source in sources:
        if (FOLDER / source).is_file():
            texts[source] = (FOLDER / source).read_text()
        else:
            problems.append("source not found: " + source)
    agreements = {s: clause_lines(t) for s, t in texts.items() if s.endswith(".md")}
    price_lists = {}
    for source, source_text in texts.items():
        if source.endswith(".json"):
            try:
                data = json.loads(source_text)
            except ValueError:
                problems.append("{}: not valid JSON".format(source))
                continue
            price_lists[source] = data if isinstance(data, dict) else {}

    standard = fields.get("standard", "")
    standard_text = ""
    if not standard:
        problems.append("no standard: line in the frontmatter")
    elif not (FOLDER / standard).is_file():
        problems.append("standard not found: " + standard)
    else:
        standard_text = (FOLDER / standard).read_text()
        problems += check_rules(body, standard_text)

    problems += check_citations(body, texts, agreements, price_lists)
    problems += check_agreements(body, agreements)
    problems += check_prices(body, price_lists)
    problems += check_values(body, "\n".join(texts.values()), known_amounts(texts, price_lists, standard_text))
    problems += check_approval(body)
    return list(dict.fromkeys(problems))


def main(argv):
    if len(argv) != 1:
        print("usage: python3 gates/supplier_terms_gate.py <output.md>")
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
