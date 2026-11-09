"""The one place factories.py and factory_checks.py run gh, the GitHub CLI, and where doctor's allowlist lives.

Every gh call those two scripts make goes through gh() here; while read_only() is held it makes reads only,
by an allowlist, and records every call with what it came to. It carries the transport, not the meaning:
the callers still build gh's own arguments, GitHub's REST paths, GraphQL and field names, and loop.py,
which posts the review, has gh calls of its own. So a second forge would need more than another module with
these names: what ready means there, and what a backend replaces, is a design question of its own.

One rule of meaning lives here, because it's applied where an answer is read: gh_json and parsed return
every string marked by one_line, each character that isn't printable as ?, one for one. A caller comparing
one with a value of its own compares marked with unmarked, so a value of its own has to read the same
marked and hold no ? (factories.json's labels are refused otherwise: a ? of its own would match a character
GitHub's carried there). The clash check isn't made here but in each reader that keys on names: it asks for
them as GitHub sent them (marked=False), refuses two that clash, and marks them before it prints or keeps
any of them.
"""

import contextlib
import json
import re
import subprocess

# What the scripts may import. A test holds their imports to these.
__all__ = ("LOGIN", "cant_use", "clash", "gh", "gh_json", "not_found", "one_line", "parsed", "printable", "read_only",
           "repo_args", "said", "shown", "skipped")

GH_TIMEOUT = 120  # seconds: a gh call that hangs (the network, a prompt for a login) fails, never waits forever


LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}")  # a GitHub login, and nothing a path could take

RECORDING = None  # while read_only() holds it: each gh call, its exit code, what a failed one said, and its notes


@contextlib.contextmanager
def read_only():
    """While held, gh makes reads only, refusing anything else unrun, and records each call it was asked for:
    the list it yields, of {"call", "code", "said", "notes"}. A reader notes on the call that gave it a reply it
    couldn't use or a row it skipped. doctor holds it, so its read-only promise is the code's."""
    global RECORDING
    before, RECORDING = RECORDING, []
    try:
        yield RECORDING
    finally:
        RECORDING = before


def note(text):
    """Note text on the gh call just made, while read_only() records: a reply a reader couldn't use, or a row
    it skipped. Outside it, nothing."""
    if RECORDING:
        RECORDING[-1]["notes"].append(text)


# The flags a read takes, each with whether a value follows it. Any other flag, or a joined form such as
# --field=, makes the call something other than a read.
READ_FLAGS = {"pr": {"-R": True, "--json": True, "--state": True, "--search": True, "--limit": True},
              "api": {"--paginate": False, "--jq": True, "-f": True}}
READ_FLAGS["issue"] = READ_FLAGS["repo"] = READ_FLAGS["pr"]


def is_read(args):
    """Whether a gh call only reads, by an allowlist: pr or issue view or list, repo view, a REST gh api call
    with no field, or one GraphQL query. Any flag not on the list refuses it: gh api sends a POST once it's
    given a field, so -f is taken only by a GraphQL query, whose one operation has to be a query."""
    args = list(args)
    if args[:2] not in (["pr", "view"], ["pr", "list"], ["issue", "view"], ["issue", "list"], ["repo", "view"],
                        ["api"] + args[1:2]):
        return False
    flags, rest = READ_FLAGS[args[0]], args[1:] if args[0] == "api" else args[2:]
    plain, fields = [], []
    while rest:
        arg = rest.pop(0)
        if not arg.startswith("-"):
            plain.append(arg)
        elif arg not in flags or (flags[arg] and not rest):
            return False
        elif flags[arg]:
            (fields if arg == "-f" else []).append(rest.pop(0))
    if args[0] != "api":
        return len(plain) <= 1
    if len(plain) != 1:
        return False
    if plain[0] != "graphql":
        return not fields
    queries = [field for field in fields if field.startswith("query=")]
    return (len(queries) == 1 and re.match(r"query=\s*query\b", queries[0]) is not None
            and re.search(r"\b(mutation|subscription)\b", queries[0]) is None)


def gh(*args):
    """(exit code, stdout, stderr) for one gh call, on the person's own login."""
    if RECORDING is not None and not is_read(args):
        refused = "doctor reads only, and this gh call would change something: it wasn't run"
        RECORDING.append({"call": list(args), "code": 1, "said": refused, "notes": []})
        return 1, "", refused
    try:
        done = subprocess.run(["gh"] + list(args), capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              timeout=GH_TIMEOUT)
    except subprocess.TimeoutExpired:
        result = 124, "", "gh didn't answer in {} seconds".format(GH_TIMEOUT)
    else:
        result = done.returncode, done.stdout.strip(), done.stderr.strip()
    if RECORDING is not None:
        RECORDING.append({"call": list(args), "code": result[0], "said": said(*result)[:300] if result[0] else "",
                          "notes": []})
    return result


def said(code, out, err):
    """What a failed gh call said, on one line. gh api puts its error on stdout."""
    return one_line(err or out or "gh exited {}".format(code))


def printable(text):
    """text with each character a terminal could act on, or that hides, breaks or reorders what follows, as ?,
    one for one: a line break, a tab, a control or format character, a non-breaking space."""
    return "".join(ch if ch.isprintable() else "?" for ch in str(text))


def one_line(value):
    """value as GitHub sent it, with every string marked: printable, so none can start a line of its own in what
    the scripts print, and nothing else in it moves. Nothing is collapsed or trimmed, so two names that differ
    only in whitespace still differ. Lists and objects are read through, and anything else is left as it is."""
    if isinstance(value, str):
        return value if value.isprintable() else printable(value)
    if isinstance(value, list):
        return [one_line(item) for item in value]
    if isinstance(value, dict):
        return {key: one_line(item) for key, item in value.items()}
    return value


SHOWN_CAP = 100  # characters of one name GitHub sent, as printed
# Characters that print as nothing and that Python counts as printable, so marking leaves them: Hangul fillers
# and the Braille blank. shown reads each as a space, so they can't pad a name past the collapse.
BLANKS = "\u115f\u1160\u2800\u3164\uffa0"


def shown(name):
    """A name GitHub sent, as a line prints it: marked, each run of spaces as one, and cut to SHOWN_CAP with an
    ellipsis. Only for printing: compare names as one_line leaves them, since this can make two of them read
    the same. Padding with spaces, or with a BLANKS character, could otherwise push the text after it onto a
    row of its own on screen."""
    text = re.sub(" {2,}", " ", one_line(str(name)).translate({ord(c): " " for c in BLANKS}))
    return text if len(text) <= SHOWN_CAP else text[:SHOWN_CAP - 1] + "\u2026"


def parsed(text, marked=True):
    """One JSON answer from gh, every string in it marked by one_line, or as GitHub sent it with marked=False.
    ValueError when it isn't JSON."""
    found = json.loads(text)
    return one_line(found) if marked else found


def clash(names):
    """Two names GitHub sent that differ, and read the same once marked, or None. A reader that keys on names
    refuses then: either could pass for the other."""
    seen = {}
    for name in names:
        if isinstance(name, str):
            other = seen.setdefault(one_line(name), name)
            if other != name:
                return other, name
    return None


def gh_json(*args, shape=dict, marked=True):
    """(GitHub's answer to one gh call, parsed, None), or (None, why it couldn't be read). A failed gh api
    call prints its error as JSON on stdout, so the answer is parsed only when gh exited 0, and an answer that
    isn't JSON, or isn't the shape asked for, is a failure too, never something a caller reads into."""
    code, out, err = gh(*args)
    if code:
        return None, said(code, out, err)
    try:
        data = parsed(out, marked)
    except ValueError:
        return None, cant_use("gh's answer wasn't JSON")
    if shape is not None and not isinstance(data, shape):
        return None, cant_use("gh's answer wasn't the {} expected".format("object" if shape is dict else "list"))
    return data, None


def cant_use(why):
    """why, noted on the call just made, which is flagged as a reply a reader couldn't use. Returns why."""
    note("couldn't use its reply: " + why)
    if RECORDING:
        RECORDING[-1]["unusable"] = True
    return why


def skipped(why):
    """Note a row a reader passed over on the call just made."""
    note("skipped a row: " + why)


def repo_args(repo):
    return ["-R", repo] if repo else []


def not_found(out):
    """Whether a failed gh api call was a 404, which for a branch's rulesets or workflows means there are none."""
    try:
        found = str(json.loads(out).get("status")) == "404"
    except (ValueError, AttributeError):
        return False
    if found:
        note("a 404, read as none")
    return found
