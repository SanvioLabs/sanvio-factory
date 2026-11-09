#!/usr/bin/env python3
"""Stamps: which checks passed on this exact text, in a fixed order.

Usage:
    python3 examples/proposal/gates/stamp.py gate proposal.md       # run the gate; on PASS, stamp it
    python3 examples/proposal/gates/stamp.py reviewed proposal.md   # you read the review and are happy
    python3 examples/proposal/gates/stamp.py status proposal.md     # each stamp: fresh, stale or missing

A stamp records a short fingerprint of the proposal's text (everything below the
frontmatter) on its `stamps:` line. Edit the text and every stamp goes stale, so
the checks run again, in the same order. A stamp is only written when every
check before it is fresh. `status` exits 0 only when all of them are.

From Sanvio Factory by Sanvio Labs, MIT: https://github.com/SanvioLabs/sanvio-factory
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proposal_gate import ROOT, check  # noqa: E402 (same folder)

ORDER = ["gate", "reviewed"]


def split(text):
    """(frontmatter lines, body). No frontmatter gives ([], the whole text)."""
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[1:i], "".join(lines[i + 1:])
    return [], text


def fingerprint(text):
    """What a stamp is taken against: the body only, so signing or a status change doesn't stale it."""
    return hashlib.sha256(split(text)[1].encode()).hexdigest()[:12]


def stamps(text):
    """{check: fingerprint} from the `stamps:` line, e.g. `stamps: gate 3f2a9c1b04de, reviewed 3f2a9c1b04de`."""
    found = {}
    for line in split(text)[0]:
        key, sep, value = line.partition(":")
        if sep and key.strip() == "stamps":
            for item in value.split(","):
                parts = item.split()
                if len(parts) == 2:
                    found[parts[0]] = parts[1]
    return found


def state(text):
    """[(check, "fresh" | "stale" | "missing")] in ORDER."""
    now, have = fingerprint(text), stamps(text)
    return [(name, "missing" if name not in have else "fresh" if have[name] == now else "stale") for name in ORDER]


def with_stamp(text, name):
    """The text with `name` stamped against its current fingerprint."""
    have = stamps(text)
    have[name] = fingerprint(text)
    line = "stamps: " + ", ".join("{} {}".format(n, have[n]) for n in ORDER if n in have) + "\n"
    front, body = split(text)
    front = [x for x in front if x.partition(":")[0].strip() != "stamps"] + [line]
    return "---\n" + "".join(front) + "---\n" + body


def stamp(path, name):
    """Stamp `name` on the file at `path`. Returns 0, or 1 with the reason printed."""
    text = Path(path).read_text()
    for before, how in state(text)[:ORDER.index(name)]:
        if how != "fresh":
            print("BLOCKED: {} is {} on {}. Run it first: stamp.py {} {}".format(before, how, path, before, path))
            return 1
    if name == "gate":
        problems = check(path, json.loads((ROOT / "data" / "rates.json").read_text()))
        print("{} {}".format("FAIL" if problems else "PASS", path))
        for problem in problems:
            print("  - " + problem)
        if problems:
            return 1
    Path(path).write_text(with_stamp(text, name))
    print("stamped {}: {}".format(name, path))
    return 0


def status(path):
    rows = state(Path(path).read_text())
    print(path)
    for name, how in rows:
        print("  {:<9} {}".format(name, how))
    todo = [name for name, how in rows if how != "fresh"]
    if todo:
        print("Not ready. Run again, in order: " + ", ".join(todo))
        return 1
    print("Ready to send.")
    return 0


def main(argv):
    if len(argv) != 2 or argv[0] not in ORDER + ["status"]:
        print(__doc__.strip().split("\n\n")[1])
        return 2
    command, path = argv
    return status(path) if command == "status" else stamp(path, command)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
