#!/usr/bin/env python3
"""Scrub one shell command before it's recorded or sent (SPEC-004 REQ-007).

    text, redactions = scrub(command, home)   # or None: the command is dropped, not recorded

The one scrubber. The usage log hook runs it before a command reaches disk, and send_usage.py runs it again
before a bundle leaves the machine, refusing the bundle if the second pass changes anything.

A command is dropped whole when it reaches a project's clone (projects/) or a client folder (clients/), names
a credential file the guard knows, or is a secret command the guard knows. In what's kept, the home folder
becomes ~, a URL loses its user and password, and these become [redacted]: the value of an environment
assignment whose name names.SECRET_ENV matches, the value of a --password, --token, --secret or --api-key
flag, an Authorization header's value and a Bearer token, each known token shape, a PEM block, and any run
of 32 or more characters that mixes letters and digits and looks random. The result is cut to 500
characters.

Standard library only, and it imports the guard and names.py rather than restating their patterns.
"""
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _folder in (ROOT / "scripts", ROOT / ".claude" / "hooks"):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))
import guard  # noqa: E402 (its credential and secret-command patterns, so there's one copy)
import names  # noqa: E402 (SECRET_ENV, the one copy the loop uses too)

MAX_LENGTH = 500
REDACTED = "[redacted]"

# A path segment, not a word that only contains the name: projects/acme, ./clients/, ~/work/projects/.
OUT_OF_BOUNDS = re.compile(r"(?:^|[\s/'\"=:~.])(?:projects|clients)/")
PEM = re.compile(r"-----BEGIN [A-Z ]+-----.*?(?:-----END [A-Z ]+-----|$)", re.S)
URL_USER = re.compile(r"(\b[a-z][a-z0-9+.-]*://)(?!\[redacted\]@)[^/\s:@'\"]+(?::[^/\s@'\"]*)?(?=@)", re.I)
# The scheme word is never the value: without the second lookahead a redacted header matches again, as "Bearer".
AUTH_HEADER = re.compile(r"(authorization:\s*(?:(?:basic|bearer|token)\s+)?)(?!\[redacted\])(?!(?:basic|bearer|token)\s)"
                         r"[^\s'\"]+", re.I)
BEARER = re.compile(r"(\bbearer\s+)(?!\[redacted\])[^\s'\"]+", re.I)
SECRET_FLAG = re.compile(r"(--(?:password|passwd|token|secret|api-?key|access-?key)(?:=|\s+))(?!\[redacted\])[^\s'\"]+",
                         re.I)
ASSIGNMENT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)=(?!\[redacted\])('[^']*'|\"[^\"]*\"|[^\s;|&]+)")
TOKENS = re.compile(
    r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"  # cloud access key ids
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}"  # GitHub tokens
    r"|\bgithub_pat_[A-Za-z0-9_]{20,}"
    r"|\bxox[abposr]-[A-Za-z0-9-]{10,}"  # Slack
    r"|\bsk-ant-[A-Za-z0-9_-]{20,}"  # Anthropic
    r"|\bsk-[A-Za-z0-9_-]{20,}"  # OpenAI and the like
    r"|\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"  # a JWT
)
LONG_RUN = re.compile(r"[A-Za-z0-9+_=-]{32,}")


def _random(run):
    """Whether a long run looks like a key rather than a word: letters and digits both, and high entropy."""
    if not (re.search(r"[A-Za-z]", run) and re.search(r"[0-9]", run)):
        return False
    counts = Counter(run)
    entropy = -sum(n / len(run) * math.log2(n / len(run)) for n in counts.values())
    return entropy >= 3.5


def dropped(command):
    """Whether a command is dropped whole rather than redacted."""
    return bool(OUT_OF_BOUNDS.search(command) or guard.CREDENTIAL.search(" " + command.lower())
                or guard.SECRET_COMMANDS.search(command))


def scrub(command, home=None):
    """(text, redactions) for a command that's kept, or None for one that's dropped."""
    if not isinstance(command, str) or dropped(command):
        return None
    count = 0
    text = command.replace(home, "~") if home else command

    def sub(pattern, keep_group, value):
        nonlocal count
        found = [0]

        def one(match):
            found[0] += 1
            return (match.group(1) if keep_group else "") + REDACTED

        result = pattern.sub(one, value)
        count += found[0]
        return result

    text = sub(PEM, False, text)
    text = sub(URL_USER, True, text)
    text = sub(AUTH_HEADER, True, text)
    text = sub(BEARER, True, text)
    text = sub(SECRET_FLAG, True, text)

    def assignment(match):
        nonlocal count
        if names.SECRET_ENV.search(match.group(1)):
            count += 1
            return match.group(1) + "=" + REDACTED
        return match.group(0)

    text = ASSIGNMENT.sub(assignment, text)
    text = sub(TOKENS, False, text)

    def long_run(match):
        nonlocal count
        if _random(match.group(0)):
            count += 1
            return REDACTED
        return match.group(0)

    text = LONG_RUN.sub(long_run, text)
    return text[:MAX_LENGTH], count
