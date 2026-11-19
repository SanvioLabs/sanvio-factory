#!/usr/bin/env python3
"""Quick check: is this copy set up, and are its updates in place?

Usage:
    python3 scripts/quick_check.py

Runs three parts from the repo root: the setup check, the link check, and the tests that cover a copy's
setup and its updates. Prints PASS or FAIL for each, with that part's output when it fails, and any WARN
from a part that passes, then the time the whole run took. A failing part doesn't stop the parts after it.
Exits 1 when any part fails. The full suite is still python3 -m unittest discover -s tests.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The tests that cover a copy's setup and its updates. The full suite runs the rest.
MODULES = (
    "test_check_setup",
    "test_skills",
    "test_steering",
    "test_tickets",
    "test_link_files",
    "test_gate",
    "test_pre_commit",
    "test_plugins",
    "test_mod_versions",
    "test_changelog",
    "test_names",
    "test_old_names",
    "test_check_blueprint",
)


def default_parts():
    """(name, command) for each part, run in this order. The tests are one unittest run, so Python starts once."""
    return [
        ("setup", [sys.executable, "scripts/check_setup.py"]),
        ("links", [sys.executable, "scripts/link_files.py", "--check"]),
        ("tests", [sys.executable, "-m", "unittest"] + ["tests." + module for module in MODULES]),
    ]


def warnings(output):
    """The WARN lines a passing part printed, each with the note line under it."""
    kept, lines = [], output.splitlines()
    for number, line in enumerate(lines):
        if line.startswith("WARN "):
            kept.append(line)
            if number + 1 < len(lines) and lines[number + 1].lstrip().startswith("note:"):
                kept.append(lines[number + 1])
    return kept


def run_part(command):
    """(passed, output) for one part, its stderr folded into its stdout, since unittest reports on stderr."""
    try:
        result = subprocess.run(command, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True)
    except OSError as exc:
        return False, "couldn't start {}: {}".format(command[0], exc)
    return result.returncode == 0, result.stdout


def main(argv, parts=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    parts = default_parts() if parts is None else parts
    started = time.monotonic()
    failed = 0
    for name, command in parts:
        part_started = time.monotonic()
        passed, output = run_part(command)
        took = time.monotonic() - part_started
        print("{} {} ({:.1f}s)".format("PASS" if passed else "FAIL", name, took), flush=True)
        if passed:
            for line in warnings(output):
                print("    " + line)
        else:
            failed += 1
            for line in output.rstrip().splitlines():
                print("    " + line)
        sys.stdout.flush()
    total = time.monotonic() - started
    print("{} of {} parts passed in {:.1f} seconds".format(len(parts) - failed, len(parts), total))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
