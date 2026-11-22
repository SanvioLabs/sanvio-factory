#!/usr/bin/env python3
"""The only shapes usage may leave this machine in: bundle v2 and the heartbeat (SPEC-004).

    problems(obj)   # [] when obj is a bundle or a heartbeat in exactly this shape, else every way it isn't

export.py checks a bundle against this before writing it, send_usage.py again before sending it, and the
store's validator a third time when it lands, all from this one file. A key not named here is a problem,
at every level, so a field added somewhere else can't ride along.

Every key also has to serve one of the questions the store answers (SPEC-004, *The questions the store
answers*), or be envelope: what's needed to read, order or de-duplicate any bundle. SERVES says which, and
tests/test_usage_shape.py fails on a key it doesn't list.

Standard library only, and nothing that opens a network connection or a process: the store's validator
packages this file as it is.
"""

V = 2

QUESTIONS = {
    "RQ-1": "Which skills, agents and slash commands did the team use, and which went unused?",
    "RQ-2": "What does a merged pull request cost, by project and by agent?",
    "RQ-3": "How many fix rounds does an issue take, by agent, reviewer and factory version?",
    "RQ-4": "Where does the guard refuse or ask most, and which asks do people always say yes to?",
    "RQ-5": "Is every node's loop running, and when did each last report?",
    "RQ-6": "Which shell commands do agents run most, and which get refused or asked about?",
}


class Check:
    """One value's rule. problems() appends to out a line per way value breaks it."""

    def check(self, value, path, out):
        raise NotImplementedError


class Kind(Check):
    def __init__(self, name, test):
        self.name, self.test = name, test

    def check(self, value, path, out):
        if not self.test(value):
            out.append("{}: expected {}".format(path, self.name))


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


STR = Kind("text", lambda v: isinstance(v, str))
INT = Kind("a whole number", lambda v: isinstance(v, int) and not isinstance(v, bool))
NUM = Kind("a number", _number)
BOOL = Kind("true or false", lambda v: isinstance(v, bool))


def _jsonish(value):
    """A scalar, or a list of them, nested as deep as it likes, and never an object."""
    if value is None or isinstance(value, (str, bool)) or _number(value):
        return True
    return isinstance(value, list) and all(_jsonish(item) for item in value)


FLAT = Kind("a value or a list, never an object", _jsonish)


class Maybe(Check):
    def __init__(self, inner):
        self.inner = inner

    def check(self, value, path, out):
        if value is not None:
            self.inner.check(value, path, out)


class OneOf(Check):
    def __init__(self, *values):
        self.values = values

    def check(self, value, path, out):
        if value not in self.values:
            out.append("{}: expected one of {}".format(path, ", ".join(map(str, self.values))))


class ListOf(Check):
    def __init__(self, inner):
        self.inner = inner

    def check(self, value, path, out):
        if not isinstance(value, list):
            out.append("{}: expected a list".format(path))
            return
        for i, item in enumerate(value):
            self.inner.check(item, "{}[{}]".format(path, i), out)


class MapOf(Check):
    """Names chosen at run time (a skill's name, a project's label) to values of one kind."""

    def __init__(self, inner):
        self.inner = inner

    def check(self, value, path, out):
        if not isinstance(value, dict):
            out.append("{}: expected an object".format(path))
            return
        for name, item in value.items():
            if not isinstance(name, str):
                out.append("{}: a name that isn't text".format(path))
            self.inner.check(item, "{}.{}".format(path, name), out)


class Obj(Check):
    """Exactly these keys: one missing, or one more, is a problem."""

    def __init__(self, keys):
        self.keys = keys

    def check(self, value, path, out):
        if not isinstance(value, dict):
            out.append("{}: expected an object".format(path or "the file"))
            return
        prefix = path + "." if path else ""
        for name in sorted(set(value) - set(self.keys)):
            out.append("{}{}: not a key this shape allows".format(prefix, name))
        for name, rule in self.keys.items():
            if name not in value:
                out.append("{}{}: missing".format(prefix, name))
            else:
                rule.check(value[name], prefix + name, out)


DAY = STR
FACTORY = Obj({"commit": Maybe(STR), "changelog": Maybe(DAY)})
LOOP_RUN_KEYS = ("v", "run", "issue", "project", "started", "ended", "outcome", "rounds", "tests", "verdicts",
                 "fix_reasons", "tests_changed", "tokens", "cost_usd", "agent", "reviewer")
LOOP_RUN = Obj({key: FLAT for key in LOOP_RUN_KEYS})
LOOP_CONFIG = Obj({"agent": Maybe(STR), "reviewer": Maybe(STR), "max_workers": Maybe(INT),
                   "max_rounds": Maybe(INT), "max_issue_tokens": Maybe(INT)})
USAGE = Obj({"sessions": INT, "log_off": INT, "skills": MapOf(INT), "agents": MapOf(INT),
             "commands": MapOf(INT), "guard_deny": MapOf(INT), "guard_ask": MapOf(INT),
             "ask_approved": MapOf(INT)})
VERDICTS = ("ran", "refused", "asked")
COMMAND = Obj({"ts": STR, "session": STR, "verdict": OneOf(*VERDICTS), "text": STR, "redactions": INT})

BUNDLE_KEYS = {
    "v": OneOf(V), "kind": OneOf("bundle"), "mode": OneOf("general", "detailed"),
    "exported": DAY, "since": DAY, "period": Obj({"first": DAY, "last": DAY}),
    "user": STR, "node": STR, "factory": FACTORY, "loop_config": MapOf(LOOP_CONFIG),
    "chain_head": Maybe(STR), "bundle_id": STR, "loop": ListOf(LOOP_RUN), "usage": USAGE,
}
DETAILED_KEYS = {"commands": ListOf(COMMAND)}  # in a detailed bundle only, and required there

LOOP_BEAT = Obj({"label": STR, "alive": BOOL, "waiting": INT, "issue": Maybe(INT), "tokens": Maybe(INT),
                 "budget": Maybe(INT)})
HEARTBEAT_KEYS = {"v": OneOf(V), "kind": OneOf("heartbeat"), "node": STR, "ts": STR, "factory": FACTORY,
                  "loops": ListOf(LOOP_BEAT)}

ENVELOPE = "envelope: needed to read, order or de-duplicate any bundle"
SERVES = {
    "v": [ENVELOPE], "kind": [ENVELOPE], "mode": [ENVELOPE], "exported": [ENVELOPE], "since": [ENVELOPE],
    "period": [ENVELOPE], "period.first": [ENVELOPE], "period.last": [ENVELOPE], "bundle_id": [ENVELOPE],
    "chain_head": ["envelope: shows a bundle edited or missing between sends (REQ-016)"],
    "ts": [ENVELOPE, "RQ-5"],
    "user": ["RQ-1", "RQ-4"], "node": ["RQ-5", "RQ-2"],
    "factory": ["RQ-3"], "factory.commit": ["RQ-3"], "factory.changelog": ["RQ-3"],
    "loop_config": ["RQ-2", "RQ-3"], "loop_config.agent": ["RQ-2", "RQ-3"],
    "loop_config.reviewer": ["RQ-3"], "loop_config.max_workers": ["RQ-5"],
    "loop_config.max_rounds": ["RQ-3"], "loop_config.max_issue_tokens": ["RQ-2", "RQ-5"],
    "loop": ["RQ-2", "RQ-3"],
    "loop.v": [ENVELOPE], "loop.run": [ENVELOPE], "loop.issue": ["RQ-2", "RQ-3"], "loop.project": ["RQ-2"],
    "loop.started": ["RQ-2"], "loop.ended": ["RQ-2"], "loop.outcome": ["RQ-2", "RQ-3"],
    "loop.rounds": ["RQ-3"], "loop.tests": ["RQ-3"], "loop.verdicts": ["RQ-3"], "loop.fix_reasons": ["RQ-3"],
    "loop.tests_changed": ["RQ-3"], "loop.tokens": ["RQ-2"], "loop.cost_usd": ["RQ-2"],
    "loop.agent": ["RQ-2", "RQ-3"], "loop.reviewer": ["RQ-3"],
    "usage": ["RQ-1", "RQ-4"], "usage.sessions": ["RQ-1"], "usage.log_off": ["RQ-1"],
    "usage.skills": ["RQ-1"], "usage.agents": ["RQ-1"], "usage.commands": ["RQ-1"],
    "usage.guard_deny": ["RQ-4"], "usage.guard_ask": ["RQ-4"], "usage.ask_approved": ["RQ-4"],
    "commands": ["RQ-6"], "commands.ts": ["RQ-6"], "commands.session": ["RQ-6"],
    "commands.verdict": ["RQ-6"], "commands.text": ["RQ-6"], "commands.redactions": ["RQ-6"],
    "loops": ["RQ-5"], "loops.label": ["RQ-5"], "loops.alive": ["RQ-5"], "loops.waiting": ["RQ-5"],
    "loops.issue": ["RQ-5"], "loops.tokens": ["RQ-5", "RQ-2"], "loops.budget": ["RQ-5"],
}


def _walk(keys, prefix, out):
    for name, rule in keys.items():
        out.add(prefix + name)
        inner = rule.inner if isinstance(rule, (ListOf, MapOf, Maybe)) else rule
        if isinstance(inner, Obj):
            _walk(inner.keys, prefix + name + ".", out)


def all_keys():
    """Every key either shape names, nested ones as parent.child."""
    out = set()
    for keys in (BUNDLE_KEYS, DETAILED_KEYS, HEARTBEAT_KEYS):
        _walk(keys, "", out)
    return out


def problems(obj):
    """Every way obj isn't a v2 bundle or heartbeat. [] means it's exactly one."""
    if not isinstance(obj, dict):
        return ["the file: expected an object"]
    out = []
    kind = obj.get("kind")
    if kind == "heartbeat":
        Obj(HEARTBEAT_KEYS).check(obj, "", out)
    elif kind == "bundle":
        keys = dict(BUNDLE_KEYS, **DETAILED_KEYS) if obj.get("mode") == "detailed" else BUNDLE_KEYS
        Obj(keys).check(obj, "", out)
    else:
        out.append("kind: expected bundle or heartbeat")
    return out
