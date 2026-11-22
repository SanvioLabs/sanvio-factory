#!/usr/bin/env python3
"""Turn detailed mode on or off for yourself (SPEC-004).

    python3 scripts/send_usage.py --opt-in detailed   # record your sessions' shell commands, scrubbed, for 14 days
    python3 scripts/send_usage.py --opt-out           # stop now

Detailed mode adds the shell commands your sessions run to your usage bundle (python3 scripts/export.py
--mode detailed). The usage log hook scrubs each one before it's written: secrets redacted, and a command that
reaches projects/, clients/ or a credential file dropped. It never records a headless run, a session working
inside projects/, or anything while the usage log is off. It ends on its own after SANVIO_DETAILED_DAYS days,
14 by default, and every session start in between says it's on.

Only a person turns it on, for themselves: a headless run is refused, and the guard asks before an agent runs
--opt-in for you.

Sending a bundle to a store comes in a later step of SPEC-004. Today this only switches the mode.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))
import usage_log  # noqa: E402 (needs .claude/hooks/ on the path first)


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--opt-in", choices=("detailed",), help="turn detailed mode on for yourself")
    which.add_argument("--opt-out", action="store_true", help="turn detailed mode off now")
    args = parser.parse_args(argv)
    if args.opt_out:
        was_on = usage_log.opt_out(root)
        print("Detailed mode is off." if was_on else "Detailed mode wasn't on.")
        return 0
    try:
        until = usage_log.opt_in(root)
    except PermissionError as err:
        print("Not turned on: {}.".format(err), file=sys.stderr)
        return 1
    print("Detailed mode is on until {}. Your sessions' shell commands are recorded, scrubbed, in {}. "
          "python3 scripts/send_usage.py --opt-out turns it off.".format(until, usage_log.commands_path(root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
