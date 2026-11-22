#!/usr/bin/env python3
"""Scrub one shell command before it's recorded or sent (SPEC-004 REQ-007).

    text, redactions = scrub(command, home)   # or None: the command is dropped, not recorded

The one scrubber. The usage log hook runs it before a command reaches disk, and send_usage.py runs it again
before a bundle leaves the machine, refusing the bundle if the second pass changes anything.

A command is dropped whole when it reaches a project's clone (projects/) or a client folder (clients/), names
a credential file the guard knows, or is a secret command the guard knows. In what's kept, the home folder
becomes ~, a URL loses its user and password, and these become [redacted]: the value of an environment
assignment whose name names.SECRET_ENV matches or ends in PASS, PWD or PIN, the value of a --password,
--token, --secret, --api-key or similar flag, quoted or not, a -u or --user value holding a password, the
password of mysql -p and sshpass -p, the value of `configure set` on a secret's name, an Authorization,
API-key, token or cookie header's value and a Bearer token, each known token shape, a PEM block, and any run
of 32 or more characters that mixes letters and digits and looks random, slashes included. The result is
cut to 500 characters, never inside a [redacted].

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
OUT_OF_BOUNDS = re.compile(r"(?:^|[\s/'\"=:~.])(?:projects|clients)(?:/|\s|['\";|&)]|$)", re.I)
PEM = re.compile(r"-----BEGIN [A-Z ]+-----.*?(?:-----END [A-Z ]+-----|$)", re.S)
URL_USER = re.compile(r"(\b[a-z][a-z0-9+.-]*://)(?!\[redacted\]@)[^/\s:@'\"]+(?::[^/\s@'\"]*)?(?=@)", re.I)
# The scheme word is never the value: without the second lookahead a redacted header matches again, as "Bearer".
AUTH_HEADER = re.compile(r"(authorization:\s*(?:(?:basic|bearer|token)\s+)?)(?!\[redacted\])(?!(?:basic|bearer|token)\s)"
                         r"[^\s'\"]+", re.I)
BEARER = re.compile(r"(\bbearer\s+)(?!\[redacted\])[^\s'\"]+", re.I)
# A flag's value, bare or quoted: --password=x, --token 'x', --client-secret "x".
VALUE = r"(?!['\"]?\[redacted\])(?:'[^']*'|\"[^\"]*\"|[^\s'\"]+)"
SECRET_FLAG = re.compile(r"(--(?:[a-z0-9]+-)*(?:password|passwd|pass|token|secret|api-?key|access-?key|secret-?key|"
                         r"private-?key|auth)(?:=|\s+))" + VALUE, re.I)
USER_PASSWORD = re.compile(r"((?:\s-u|--user)(?:=|\s*)['\"]?[^\s:'\"]+:)(?!\[redacted\])[^\s'\"]+")
SHORT_PASSWORD = re.compile(r"(\b(?:mysql|mysqldump|mariadb|mysqladmin)\b[^|;&]*?\s-p)(?!\[redacted\])([^\s'\"]+)"
                            r"|(\bsshpass\s+-p\s*)" + VALUE)
CONFIGURE_SET = re.compile(r"(\bconfigure\s+set\s+\S*(?:secret|token|password|passwd|key)\S*\s+)" + VALUE, re.I)
KEY_HEADER = re.compile(r"((?:x-api-key|api-key|apikey|x-auth-token|private-token|x-amz-security-token|cookie|"
                        r"x-access-token):\s*)(?!\[redacted\])[^'\"]+?(?=['\"]|\s-|$)", re.I)
SECRET_NAME = re.compile(r"(?:^|_)(?:PASS|PWD|PIN)$", re.I)
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
# A run with slashes, as base64 and cloud secret keys have. Paths have them too, so it needs upper and lower
# case and digits, and doesn't start like a path.
SLASH_RUN = re.compile(r"(?<![\w./~+=-])[A-Za-z0-9+=][A-Za-z0-9+/=]{31,}(?![\w/+=])")


def _random(run):
    """Whether a long run looks like a key rather than a word: letters and digits both, and high entropy."""
    if not (re.search(r"[A-Za-z]", run) and re.search(r"[0-9]", run)):
        return False
    counts = Counter(run)
    entropy = -sum(n / len(run) * math.log2(n / len(run)) for n in counts.values())
    return entropy >= 3.5


def _keylike(run):
    """A slash-bearing run that reads as a key, not a path: every case and digits, random, few slashes."""
    return (bool(re.search(r"[A-Z]", run) and re.search(r"[a-z]", run) and re.search(r"[0-9]", run))
            and run.count("/") * 8 <= len(run) and _random(run.replace("/", "")))


def cut(text):
    """Cut to MAX_LENGTH, and further back where the cut would split a [redacted]."""
    if len(text) <= MAX_LENGTH:
        return text
    head = text[:MAX_LENGTH]
    start = head.rfind("[", MAX_LENGTH - len(REDACTED))
    if start != -1 and REDACTED.startswith(head[start:]):
        head = head[:start]
    return head


def dropped(command):
    """Whether a command is dropped whole rather than redacted."""
    return bool(OUT_OF_BOUNDS.search(command) or guard.CREDENTIAL.search(" " + command.lower())
                or guard.SECRET_COMMANDS.search(command))


def scrub(command, home=None):
    """(text, redactions) for a command that's kept, or None for one that's dropped.

    The result is a fixed point: scrubbing it again changes nothing, which send_usage.py checks. A cut can
    leave a header's scheme word where its value was, so the cut text is scrubbed again until it holds."""
    if not isinstance(command, str) or dropped(command):
        return None
    text, count = _once(command.replace(home, "~") if home else command)
    for _ in range(5):
        again, more = _once(text)
        if not more:
            break
        text, count = again, count + more
    return text, count


def _once(text):
    """One pass of every pattern, then the cut: (text, redactions)."""
    count = 0

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
    text = sub(KEY_HEADER, True, text)
    text = sub(SECRET_FLAG, True, text)
    text = sub(USER_PASSWORD, True, text)
    text = sub(CONFIGURE_SET, True, text)

    def short_password(match):
        nonlocal count
        count += 1
        return (match.group(1) or match.group(3)) + REDACTED

    text = SHORT_PASSWORD.sub(short_password, text)

    def assignment(match):
        nonlocal count
        if names.SECRET_ENV.search(match.group(1)) or SECRET_NAME.search(match.group(1)):
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

    def slash_run(match):
        nonlocal count
        if "/" in match.group(0) and _keylike(match.group(0)):
            count += 1
            return REDACTED
        return match.group(0)

    text = SLASH_RUN.sub(slash_run, text)
    return cut(text), count
