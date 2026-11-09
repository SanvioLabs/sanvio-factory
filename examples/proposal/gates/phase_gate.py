#!/usr/bin/env python3
"""Phase gate: what a client's proposal is missing before the work can enter a phase.

Usage:
    python3 examples/proposal/gates/phase_gate.py <shape|build> <client>

<client> is the proposal's file name without .md (juniper-bakery), or its path.
For each gap it names what closes it: a skill, an agent, or nobody but you. It
only reports. It never changes the proposal and never moves the phase on: that's
a person's call. Exits 0 when nothing is missing and 1 when something is.

The questions each phase asks are in steering/gates.md. The ones a script can
decide are here. Validate and Scale are a person's, so they aren't.

From Sanvio Factory by Sanvio Labs, MIT: https://github.com/SanvioLabs/sanvio-factory
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proposal_gate import HTML_COMMENT, ROOT, section  # noqa: E402 (same folder)
from stamp import split, state  # noqa: E402

DRAFT = "skill draft-proposal"
STAMP = "stamp.py gate"  # not the skill: re-drafting would copy the template over a finished proposal
REVIEW = "agent reviewer, then you stamp it reviewed"  # the brief: agents/proposal-reviewer.md


def has_problem(text):
    return bool(HTML_COMMENT.sub("", section(text, "Problem")).strip()) and "{{" not in section(text, "Problem")


def fresh(name):
    return lambda text: dict(state(text))[name] == "fresh"


def signed(text):
    return any(re.match(r"\s*signed\s*:\s*\S", line) for line in split(text)[0])


# Entering a phase means passing every check of the gate before it. None: nothing but a person closes it.
PHASES = {
    "shape": ("Discover", [
        ("Problem written down", has_problem, DRAFT),
    ]),
    "build": ("Shape", [
        ("Problem written down", has_problem, DRAFT),
        ("Gate passed on this text", fresh("gate"), STAMP),
        ("Reviewed on this text", fresh("reviewed"), REVIEW),
        ("Signed by the client", signed, None),
    ]),
}


def gaps(phase, text):
    """[(check, what closes it or None)] for each check the text doesn't pass yet."""
    return [(name, closer) for name, passes, closer in PHASES[phase][1] if not passes(text)]


def main(argv):
    if len(argv) != 2 or argv[0] not in PHASES:
        print(__doc__.strip().split("\n\n")[1])
        return 2
    phase, client = argv
    path = Path(client) if client.endswith(".md") else ROOT / "proposals" / (client + ".md")
    if not path.is_file():
        print("no proposal at {}. Close it with: {}".format(path, DRAFT))
        return 1
    before = PHASES[phase][0]
    found = gaps(phase, path.read_text())
    print("phase-gate {} {}".format(phase, path.stem))
    for name, closer in found:
        print("  x {:<26} {}".format(name, "closes it: " + closer if closer else "no skill closes this"))
    if not found:
        print("Nothing missing for {}. Moving the phase on is yours.".format(phase.capitalize()))
        return 0
    noun = "gap" if len(found) == 1 else "gaps"
    if all(closer is None for _, closer in found):
        print("Still in {}: {} {}, and only you can close {}.".format(before, len(found), noun, "it" if len(found) == 1 else "them"))
    else:
        print("Still in {}: {} {} before {}.".format(before, len(found), noun, phase.capitalize()))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
