#!/usr/bin/env python3
"""Hand an issue to another factory, and review what comes back.

Usage:
    python3 scripts/factories.py steps [--root PATH]
    python3 scripts/factories.py dispatch ISSUE [--repo OWNER/NAME] [--yes] [--root PATH]
    python3 scripts/factories.py status [RUN] [--root PATH]
    python3 scripts/factories.py review RUN [--root PATH]
    python3 scripts/factories.py resend RUN [--yes] [--root PATH]
    python3 scripts/factories.py cancel RUN [--yes] [--root PATH]
    python3 scripts/factories.py doctor --repo OWNER/NAME --pr N [--root PATH]
    python3 scripts/factories.py list [--root PATH]

A factory is any system that takes work in and puts checked work out: another team's delivery
system, or another harness. factories.json at the harness root names one, as a single step:

    {"steps": [{"factory": "build-team", "where": "local", "commit": "<sha>",
                "submit_label": "factory-ready", "stopped_label": "factory:blocked",
                "time_limit_hours": 24, "max_rounds": 3}]}

What the limits allow, what they count and when a run has none is in HOW-IT-WORKS.md's
*Handing work to another factory*, and LIMITS below checks it. A local step's checkout is
factories/<factory>, which git ignores. A remote one runs somewhere
else and needs no folder. With no factories.json, or an empty steps list, nothing here runs.
This version takes one step: a chain waits until one factory is proved.

Each run records the factory's commit. A local step's comes from its checkout, and a pin that
differs from it stops everything before anything is submitted. A remote step's is recorded as
declared, unverified, since its code isn't here to read. The commands run against a factory's
checkout are git rev-parse, git config to read whether its own config names a filter or fsmonitor,
and git status only when it names neither: nothing in it is ever run, imported or loaded. A folder
that isn't its own checkout is refused. Repos are on github.com only.

dispatch shows the factory, the repo and the issue, and submits only on a yes to that one
submission. Submitting adds the step's submit_label to the issue, and nothing else: GitHub is the
only way in. An issue carrying the loop's ready label is refused, so the loop and a factory can't
both work it. gh runs on the person's own login, which this never reads. When the repo's default
branch requires no status check, branch protection or ruleset, dispatch says so before the yes:
nothing independent would check what the factory returns.

The first time anything goes to a factory, dispatch says what submitting sends, before the yes.
Each submission writes one run record to .harness/factories/run-<issue>-<time>.json, which git
ignores. A factory's tokens and cost aren't visible from here, so they read "not reported".

status reads GitHub and moves each run on, and writes nothing to GitHub. A pull request linked to
the issue means the factory returned it; a head commit not yet reviewed is named, with the review to
run. review RUN runs it, with the loop's own reader: python3 scripts/loop.py review --pr N, given the
number and nothing the factory wrote, with --project when the repo is a clone under projects/. That
reader is held to read tools and posts one comment on your login, edited in place on each new
commit. A repo with no clone here can't be reviewed, and says so; a review that failed can be run again.
The step's stopped label, or its time limit passing, stops the run with the reason, and nothing is
submitted again. A run that read
ready reads returned from the moment status starts on it until a status gets through. A GitHub read
that fails changes nothing else, except a failed read
of the required checks after a ready verdict, which reads checks unknown.
doctor builds the record dispatch would make and makes status's reads for one pull request through the
same code, with gh held to an allowlist of reads, listing every call with what it came to.
Each record says whose move it is (waiting_on: the factory, a person, a review or its checks), and
one run's commands hold its own lock, so two never write over each other.

The verdict is read from the trailer of the person's own marked review comment for the pull
request's head commit, through the loop's one reader: "changes needed", "ready" or "ready with
nits". Anything else hands the run to a person rather than starting another round, since the diff
the reviewer read can shape its words. loop.py review --pr says what it did in one JSON line, and
nothing here reads the loop's files.
After changes needed, resend puts the submit label back on the issue for the factory, after a yes
to that one round, and counts it, once per reviewed commit. After a ready verdict whose checks fail
or that changes CI, or with a person's reason in --because, it first posts one comment saying why,
under a person's header and ending in changes needed, since a factory reads only the label and that
comment. Once max_rounds are spent, the next changes needed sends nothing and the run reads
needs-person.

After a ready verdict, status reports the pull request's required checks on their own, read from the
base repo, never from anything the factory said, and only ready for a person moves the run on. What
ready requires, and what it can't show, is written once, in factories/README.md's *Getting to ready*;
factory_checks.py reads it. A person merges, with the one command
status prints, which checks the base first: nothing here does.

Python 3.9 or newer, standard library only.

From the Sanvio Labs harness starter, MIT: https://github.com/SanvioLabs/sanvio-harness-starter
"""
import argparse
import contextlib
import json
import math
import os
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # factory_checks and loop, beside this file
from factory_checks import (CI_PATHS, check_report, checks_line, default_branch, not_factory_fork,  # noqa: E402
                            required_checks)
from forge import LOGIN, cant_use, gh, gh_json, one_line, printable, read_only, repo_args, said, shown, skipped  # noqa: E402

LOOP = Path(__file__).resolve().parent / "loop.py"  # the reviewer a returned pull request goes to

DEFAULT_TIME_LIMIT_HOURS = 24
DEFAULT_MAX_ROUNDS = 3
REVIEW_TIMEOUT_HOURS = 2  # the loop's review of one pull request: past this it's stopped, and says so
WHERE = ("local", "remote")


class StepError(Exception):
    """factories.json can't be used as it stands. The message says why."""


def read_steps(root):
    """The configured steps, checked. [] when there's no factories.json or no step in it.

    Reads one file and starts no process, so a harness with no factory pays nothing for this."""
    path = Path(root) / "factories.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except ValueError as err:
        raise StepError("factories.json isn't valid JSON: {}".format(err))
    if not isinstance(data, dict) or not isinstance(data.get("steps", []), list):
        raise StepError("factories.json has to be an object with a steps list")
    steps = data.get("steps", [])
    if len(steps) > 1:
        raise StepError("factories.json has {} steps, and this version takes one step: "
                        "a chain waits until one factory is proved".format(len(steps)))
    return [check_step(Path(root), step) for step in steps]


def check_step(root, step):
    """One step with its defaults filled in, or StepError naming what's wrong with it."""
    if not isinstance(step, dict):
        raise StepError("a step in factories.json has to be an object")
    name = step.get("factory")
    if not isinstance(name, str) or not name.strip():
        raise StepError("a step in factories.json has no factory name")
    where = step.get("where")
    if where not in WHERE:
        raise StepError("step {} is neither local nor remote: set where to one of them".format(name))
    for key in ("submit_label", "stopped_label"):
        if not isinstance(step.get(key), str) or not step[key].strip():
            raise StepError("step {} has no {}".format(name, key))
        if "," in step[key]:
            raise StepError("step {}'s {} has a comma, which gh would read as two labels".format(name, key))
        if one_line(step[key]) != step[key] or "?" in step[key]:
            raise StepError("step {}'s {} holds a character that isn't printable, or a ?, which is how GitHub's "
                            "labels read once marked, so it couldn't be told from another label".format(name, key))
    if step["submit_label"].lower() == step["stopped_label"].lower():
        raise StepError("step {} uses the same label to submit and to mean it stopped: give each its own".format(name))
    commit = step.get("commit")
    if commit is not None and not isinstance(commit, str):
        raise StepError("step {} has a commit that isn't a string".format(name))
    limit = step.get("time_limit_hours", DEFAULT_TIME_LIMIT_HOURS)
    rounds = step.get("max_rounds", DEFAULT_MAX_ROUNDS)
    for field, value in (("time_limit_hours", limit), ("max_rounds", rounds)):
        if not within_limits(field, value):
            raise StepError("step {} has a {} that {}".format(name, field, limit_rule(field)))
    login = step.get("factory_login")
    if login is not None and (not isinstance(login, str) or not LOGIN.fullmatch(login)):
        raise StepError("step {} has a factory_login that isn't a GitHub login".format(name))
    method = step.get("merge_method")
    if method is not None and method not in MERGE_METHODS:
        raise StepError("step {} has a merge_method that isn't merge, squash or rebase".format(name))
    extra = step.get("ci_paths", [])
    if not isinstance(extra, list) or not all(
            isinstance(path, str) and path.strip() and "/" not in path and path not in (".", "..") for path in extra):
        raise StepError("step {} has ci_paths that aren't a list of top-level file or folder names".format(name))
    checked = {"factory": name, "where": where, "submit_label": step["submit_label"],
               "stopped_label": step["stopped_label"], "commit": commit,
               "time_limit_hours": limit, "max_rounds": rounds, "factory_login": login,
               "ci_paths": sorted(set(CI_PATHS) | set(extra)), "merge_method": method}
    if where == "local":
        checked["folder"] = local_folder(root, name)
    return checked


def local_folder(root, name):
    """factories/<name>, which has to be a folder directly inside factories/."""
    base = (root / "factories").resolve()
    folder = (base / name).resolve()
    if folder.parent != base:
        raise StepError("step {} names a folder outside factories/".format(name))
    if not folder.is_dir():
        raise StepError("step {} is local, and there's no folder factories/{}".format(name, name))
    return folder


def resolve_commit(step):
    """{"commit", "pinned", "verified"} for a step, or StepError when a local pin differs from HEAD."""
    pin = step.get("commit")
    if step["where"] == "remote":
        return {"commit": pin, "pinned": bool(pin), "verified": False}
    done = subprocess.run(["git", "-C", str(step["folder"]), "rev-parse", "--show-toplevel", "HEAD"],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)
    lines = done.stdout.split()
    if done.returncode or len(lines) != 2:
        raise StepError("couldn't read the commit of factories/{}: {}".format(
            step["factory"], done.stderr.strip() or "git exited {}".format(done.returncode)))
    top, head = lines
    if Path(top).resolve() != Path(step["folder"]).resolve():
        # git walked up to a checkout around it, such as this harness's own: that commit isn't the factory's.
        raise StepError("factories/{} isn't its own git checkout: clone the factory there".format(step["factory"]))
    if pin and not (len(pin) >= 7 and head.startswith(pin)):
        raise StepError("step {} is pinned to {}, and factories/{} is at {}: check out the pin, "
                        "or change it".format(step["factory"], pin, step["factory"], head))
    return {"commit": head, "pinned": bool(pin), "verified": True, "dirty": uncommitted(step["folder"])}


def uncommitted(folder):
    """Whether the checkout has changes beside its commit: True, False, or "unchecked" when asking would
    run something of its own. git status runs the filter drivers and fsmonitor the checkout's own config
    names: .git/config, what it includes, and .git/config.worktree once extensions.worktreeConfig is on. So
    it's asked only when none of them names either, with fsmonitor off and submodules left alone. Without
    that extension, --worktree reads what --local does."""
    for scope in ("--local", "--worktree"):
        done = subprocess.run(["git", "-C", str(folder), "config", scope, "--includes", "--get-regexp",
                               r"^(filter\..*|core\.fsmonitor)$"],
                              capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if done.returncode not in (0, 1) or done.stdout.strip():
            return "unchecked"
    done = subprocess.run(["git", "-C", str(folder), "-c", "core.fsmonitor=false", "status", "--porcelain",
                           "--ignore-submodules=all"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return "unchecked" if done.returncode else bool(done.stdout.strip())


def runs_dir(root):
    """Each run's record, and which factories have been told what submitting sends."""
    return Path(root) / ".harness" / "factories"


def write_json(path, data):
    """Write through a temporary file of its own, so a reader never sees half of it and two writers never
    share one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, part = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".part")
    try:
        with os.fdopen(handle, "w") as out:
            out.write(json.dumps(data, indent=2) + "\n")
        os.replace(part, str(path))
    except BaseException:
        if os.path.exists(part):
            os.unlink(part)
        raise


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def privacy_notice(root, step):
    """What submitting sends, the first time anything goes to this factory from here. None after that."""
    path = runs_dir(root) / "notices.json"
    told = json.loads(path.read_text()) if path.exists() else {}
    if step["factory"] in told:
        return None
    told[step["factory"]] = now()
    write_json(path, told)
    return ("Submitting sends the issue and the repo to {}. Customer information goes only to a tool the "
            "customer has agreed to, per steering/data-and-tools.md: check that before you say yes."
            .format(step["factory"]))


def record_run(root, step, found, issue, repo, base):
    """The run's first record: submitted, with the factory's commit. Returns its path."""
    record = new_record(step, found, issue, repo, base)
    path = runs_dir(root) / (record["run"] + ".json")
    write_json(path, record)
    return path


def new_record(step, found, issue, repo, base):
    """A run's first record, as dispatch writes it and doctor builds it."""
    started = now()
    stamp = started.replace("-", "").replace(":", "")[:15]
    record = {"version": RECORD_VERSION, "run": "run-{}-{}".format(issue["number"], stamp), "repo": repo, "issue": issue["number"],
              "title": issue["title"], "factory": step["factory"], "where": step["where"],
              "commit": found["commit"], "pinned": found["pinned"], "verified": found["verified"],
              "dirty": found.get("dirty", False), "base": base, "factory_login": step.get("factory_login"),
              "factory_id": step.get("factory_id"),
              "ci_paths": step["ci_paths"], "merge_method": step.get("merge_method"),
              "submit_label": step["submit_label"], "stopped_label": step["stopped_label"],
              "time_limit_hours": step["time_limit_hours"], "max_rounds": step["max_rounds"],
              "state": "submitted", "pr": None, "rounds": 0, "started": started, "ended": None, "waiting_on": "factory",
              "tokens": "not reported", "cost": "not reported"}
    return record


ENDED = ("stopped", "needs-person", "merged", "closed", "cancelled")
MERGE_METHODS = ("merge", "squash", "rebase")  # gh pr merge's flags, one of which a step may name
# Each limit's kind, the least and the most it can be, in factories.json and in a record, and what a bad one
# isn't. A year, past which overdue() can't add the hours to a time, and more rounds than any factory gets.
LIMITS = {"time_limit_hours": ((int, float), 0, 8760, "isn't a number of hours above {least:g} and at most {most:,}, a year"),
          "max_rounds": ((int,), 1, 100, "isn't a whole number from {least} to {most}")}


def limit_rule(field):
    """What a bad value of field isn't, in words built from LIMITS' numbers, so the two can't drift."""
    _, least, most, rule = LIMITS[field]
    return rule.format(least=least, most=most)


def within_limits(field, value):
    """Whether value can be field's: time_limit_hours or max_rounds. The one check of both, for factories.json
    and for a record, so dispatch never writes a record its own reader refuses. Hours are above the least;
    rounds are from it."""
    kinds, least, most, _ = LIMITS[field]
    if isinstance(value, bool) or not isinstance(value, kinds) or not math.isfinite(value):
        return False
    return (value > least if field == "time_limit_hours" else value >= least) and value <= most


# What every run record holds from dispatch on: a record without one can't be moved on, and says which. A
# record doctor makes for itself also carries doctor=True, which after_review reads to give no merge; it's
# never written to disk.
FIELDS = ("run", "repo", "issue", "factory", "base", "submit_label", "stopped_label", "time_limit_hours",
          "max_rounds", "state", "pr", "started")


RECORD_VERSION = 1
# Each field a record gained after the fields above that the code reads as it is, with what an older record
# means by its absence. A field added later goes here too, so a run dispatched by an older factories.py still
# reads. One read with .get(), such as factory_id, stays absent: absent says it was never recorded.
ADDED = {"version": 1, "rounds": 0, "ended": None, "waiting_on": None}


def checked(record):
    """record, with each field added since it was written filled in, or ValueError saying why it can't be
    used: a field missing, a newer version, or a time or limit that isn't one."""
    if not isinstance(record, dict):
        raise ValueError("not a run record")
    missing = [field for field in FIELDS if field not in record]
    if missing:
        raise ValueError("it has no {}".format(", ".join(repr(field) for field in missing)))
    version = record.get("version", 1)
    if not isinstance(version, int) or isinstance(version, bool) or version > RECORD_VERSION:
        raise ValueError("it was written by a newer factories.py (version {}): update this one".format(version))
    for field, value in ADDED.items():
        record.setdefault(field, value)
    seen = record.get("head_seen")
    if seen is not None and not isinstance(seen, dict):
        raise ValueError("its head_seen isn't a commit and a time")
    for field, value in (("started", record["started"]), ("sent_at", record.get("sent_at")),
                         ("head_seen", (seen or {}).get("at")), ("ended", record["ended"])):
        try:
            if value is not None and datetime.fromisoformat(value).tzinfo is None:
                raise ValueError("no timezone")
        except (TypeError, ValueError):
            raise ValueError("its {} isn't a time with a timezone: {!r}".format(field, value))
    if record.get("merge_method") not in (None,) + MERGE_METHODS:  # read with .get(): absent says none was named
        raise ValueError("its merge_method isn't merge, squash or rebase: {!r}".format(record["merge_method"]))
    for field in LIMITS:
        if not within_limits(field, record[field]):
            raise ValueError("its {} {}: {!r}".format(field, limit_rule(field), record[field]))
    rounds = record["rounds"]
    if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 0:
        raise ValueError("its rounds isn't a whole number from 0: {!r}".format(rounds))
    whole = lambda value: isinstance(value, int) and not isinstance(value, bool) and value > 0  # noqa: E731
    if not whole(record["issue"]) or not (record["pr"] is None or whole(record["pr"])):
        raise ValueError("its issue or pull request isn't a number: {!r}, {!r}".format(record["issue"], record["pr"]))
    for field in ("run", "repo", "factory", "base", "submit_label", "stopped_label", "state"):
        if not isinstance(record[field], str):
            raise ValueError("its {} isn't text: {!r}".format(field, record[field]))
    for field in ("review", "checks"):
        if record.get(field) is not None and not isinstance(record[field], dict):
            raise ValueError("its {} isn't a review or a set of checks: {!r}".format(field, record[field]))
    review = record.get("review")
    if review is not None and not all(isinstance(review.get(field), str) for field in ("sha", "state", "note")):
        raise ValueError("its review hasn't a sha, a state and a note, each as text: {!r}".format(review))
    return record


def load_runs(root, name=None, unreadable=None):
    """(path, record) for each run here, or the one named. A record that can't be read is left out, and
    named in unreadable when that's a list, so one bad file stops no other run."""
    paths = sorted(runs_dir(root).glob("run-*.json"))
    if name:
        paths = [path for path in paths if path.stem == name]
    runs = []
    for path in paths:
        try:
            record = checked(json.loads(path.read_text()))
        except (OSError, ValueError) as err:
            if unreadable is not None:
                unreadable.append("{}: couldn't read its record: {}".format(path.stem, err))
            continue
        runs.append((path, record))
    return runs


def read_linked(record):
    """The issue as status needs it: its labels and the pull requests that would close it."""
    issue, why = gh_json("issue", "view", str(record["issue"]), *repo_args(record["repo"]),
                         "--json", "number,state,labels,closedByPullRequestsReferences")
    if why:
        raise StepError("couldn't read issue #{}: {}".format(record["issue"], why))
    return issue


def stop(record, why):
    return end(record, "stopped", why)


def end(record, state, why):
    """The run is over: every ending comes through here, so each records its state, reason and end time. A
    run that stops, or ends needing a person, may leave the submit label on the issue, which status can't
    take off since it writes nothing to GitHub: its line says how."""
    record.update(state=state, why=why, ended=now(), waiting_on=None)
    record.pop("until_new_commit", None)
    return ended_line(record)


def unlabel_args(record):
    """gh's arguments for taking the run's submit label off its issue: cancel runs them, and they're printed,
    quoted for a shell, wherever a line says how to take the label off."""
    return ["issue", "edit", str(record["issue"]), *repo_args(record["repo"]), "--remove-label", record["submit_label"]]


def unlabel_command(record):
    """unlabel_args as a person would type them."""
    return "gh " + shlex.join(unlabel_args(record))


def label_left(record):
    """What an ended run that stopped or needs a person says of the submit label it may have left on, or ""."""
    if not is_over(record) or record["state"] not in ("stopped", "needs-person"):
        return ""
    return ". If #{} still carries {}, the factory can still take it with nothing tracking it: {}".format(
        record["issue"], one_line(record["submit_label"]), unlabel_command(record))


def ended_line(record, label=True):
    """A run's state and why, on one line, with the way to take the submit label off when it ended stopped or
    needing a person: what status, list and cancel each say of a run that's over. The command ends the line,
    so a line that says more puts label_left after it, as list does."""
    line = "{}: {}".format(record["state"], one_line(record["why"])) if record.get("why") else record["state"]
    return line + (label_left(record) if label else "")


def is_over(record):
    """Whether the run has ended. Every ending goes through end(), which sets ended; a run that needs a person
    until the factory's next commit hasn't ended. status, list, cancel and dispatch all ask this."""
    return bool(record.get("ended"))


def waiting_since(record):
    """(when the run's current wait began, what began it): the latest of the submission, the last round sent
    back, and when the pull request's current head was first seen."""
    marks = [(record["started"], "the submission")]
    if record.get("sent_at"):
        marks.append((record["sent_at"], "the last round was sent back"))
    seen = record.get("head_seen") or {}
    if seen.get("at"):
        marks.append((seen["at"], "{} was first seen".format(str(seen.get("sha", ""))[:7])))
    return max(marks, key=lambda mark: datetime.fromisoformat(mark[0]))


def overdue(record, since=None):
    """Whether the step's time limit has passed since the given time, or since the run's current wait began."""
    since = since or waiting_since(record)[0]
    return datetime.now(timezone.utc) - datetime.fromisoformat(since) > timedelta(hours=record["time_limit_hours"])


def stalled(record, line):
    """status's line for a run waiting on the factory, a review or its checks, or the stop once the step's time
    limit has passed since that wait began. A ready run waits on a person and never comes here."""
    since, what = waiting_since(record)
    if not overdue(record, since):
        return line
    return stop(record, "nothing came of it {:g} hours after {}: {}".format(record["time_limit_hours"], what, line))


def slug(folder):
    """The OWNER/NAME of folder's GitHub origin, lower case, or None when it has none: as loop.py reads it."""
    import loop  # noqa: E402  beside this file
    found = loop.origin_slug(folder)
    return found.lower() if found else None


def clone_here(root, repo):
    """Where repo is cloned here: the harness itself (None), a folder under projects/, or False for nowhere."""
    wanted = (repo or "").lower()
    if slug(root) == wanted:
        return None
    projects = Path(root) / "projects"
    for folder in sorted(projects.iterdir()) if projects.is_dir() else []:
        if (folder / ".git").exists() and slug(folder) == wanted:
            return folder
    return False


def origin_why(folder):
    """Why folder's origin names no repo, as loop.py says it, or "" when it names one."""
    import loop  # noqa: E402  beside this file
    return loop.origin(folder)[1]


def unnamed_clones(root):
    """(where, why) for this harness and each clone under projects/ whose origin names no repo on github.com, as
    loop.py reads it: one of them may be the clone a review was wanted from. Each origin is read once."""
    import loop  # noqa: E402  beside this file
    projects = Path(root) / "projects"
    folders = [("this harness", root)] + [("projects/" + folder.name, folder) for folder in (
        sorted(projects.iterdir()) if projects.is_dir() else []) if (folder / ".git").exists()]
    found = []
    for where, folder in folders:
        name, why = loop.origin(folder)
        if name is None:
            found.append((where, why))
    return found


def review_target(root, repo):
    """loop.py's arguments for repo when it's cloned here, or None."""
    folder = clone_here(root, repo)
    if folder is False:
        return None
    return [] if folder is None else ["--project", "projects/" + folder.name]


def ready_labels(root, repo):
    """The ready labels of the loop that would build repo's issues: the harness's own, a projects/ clone's
    as its loop resolves it, or with no clone here both the harness's and the default."""
    import loop  # noqa: E402
    folder = clone_here(root, repo)
    try:
        if folder is None:
            return {loop.load_config(root)["ready_label"]}
        if folder:
            return {loop.load_project_config(root, folder)["ready_label"]}
        return {loop.load_config(root)["ready_label"], loop.DEFAULTS["ready_label"]}
    except (OSError, ValueError, KeyError) as err:
        raise StepError("couldn't read the loop's ready label for {}: {}".format(repo, err))


def factory_pr(record, ref):
    """None when the linked pull request ref is the factory's own, or why it isn't: in this repo, into the
    default branch, by the step's factory_login where it names one, and from a branch in this repo or a fork
    that factory_login owns. Any other fork is someone else's work."""
    url = str(ref.get("url") or "").lower()
    if not url.startswith("https://github.com/{}/pull/".format(record["repo"].lower())):
        return "it's in another repo"
    pr, why = gh_json("pr", "view", str(ref["number"]), *repo_args(record["repo"]),
                      "--json", "number,isCrossRepository,headRepositoryOwner,baseRefName,author")
    if why:
        return "couldn't read it: {}".format(why)
    login = record.get("factory_login")
    if not isinstance(pr.get("isCrossRepository"), bool):
        return "couldn't read whether #{} is from a fork".format(ref["number"])
    if pr["isCrossRepository"]:
        why = not_factory_fork(record, pr)
        if why:
            return why
    if pr.get("baseRefName") != record["base"]:
        return "it's into {}, not {}".format(shown(pr.get("baseRefName")), record["base"])
    author = pr.get("author") or {}
    if login and str(author.get("login") or "").lower() != login.lower():
        return "it's by {}, not {}".format(author.get("login") or "nobody", login)
    if login and record.get("factory_id") and author.get("id") != record["factory_id"]:
        return "it's by an account that isn't the one {} named at dispatch".format(login)
    return None


def account_id(login):
    """The GitHub account id behind login, as gh pr view gives a pull request's author and fork owner, or
    StepError. A login can be renamed and taken by someone else; the id stays with the account."""
    found, why = gh_json("api", "graphql", "-f",
                         "query=query($login: String!) { repositoryOwner(login: $login) { id __typename } }",
                         "-f", "login=" + login, "--jq", ".data.repositoryOwner | [.id, .__typename]", shape=list)
    if why or len(found) != 2 or not isinstance(found[0], str) or not found[0]:
        raise StepError("couldn't read the GitHub account behind factory_login {}: {}".format(
            login, why or "no such account"))
    if found[1] != "User":
        raise StepError("factory_login {} is an organisation, not a user account: its pull requests come from a "
                        "user, such as a machine user the factory's team runs".format(login))
    return found[0]


def factory_prs(record, refs):
    """(the newest linked pull request that is the factory's, or None, [why each newer one isn't])."""
    refused = []
    for ref in reversed(list(refs)):
        why = factory_pr(record, ref)
        if why and why.startswith("couldn't read"):  # a failed read isn't a refusal: nothing changes
            raise StepError("couldn't read pull request #{}: {}".format(ref["number"], why))
        if why is None:
            return ref["number"], refused
        refused.append("#{} isn't the factory's: {}".format(ref["number"], why))
    return None, refused


def whoami():
    """Your GitHub login, or StepError: a review comment is yours only by it."""
    code, out, err = gh("api", "user", "--jq", ".login")
    if not code and not out.strip():
        cant_use("no login came back")
    if code or not out.strip():
        raise StepError("couldn't read your GitHub login: {}".format(said(code, out, err) if code else "none came back"))
    return one_line(out.strip())


READY = ("ready", "ready with nits")


def read_verdict(record, sha):
    """The verdict in the trailer of the person's own review comment for commit sha: "ready", "ready with
    nits", "changes needed" or "unreadable", or None when there's no such comment yet. Read through the
    loop's one reader, so both scripts take a review comment the same way. A read that fails is StepError,
    never "no comment yet": status then changes nothing."""
    import loop  # noqa: E402
    me = whoami()
    code, out, err = gh("api", "--paginate", "repos/{}/issues/{}/comments".format(record["repo"], record["pr"]),
                        "--jq", loop.REVIEW_COMMENTS_JQ)
    if code:
        raise StepError("couldn't read pull request #{}'s comments: {}".format(record["pr"], said(code, out, err)))
    passed_over = []
    found = loop.newest_review(out, [me], sha, passed_over)
    for why in passed_over:
        skipped(why)
    if found is None:
        return None
    return found[1] or "unreadable"  # a comment from before the trailer carried a verdict


def after_review(record, head, current=None, read=None):
    """Where a posted review leaves the run, from its verdict. Returns the rest of status's line, which
    already names the commit: "review of <sha> " comes before it. read reads the verdict: read_verdict,
    unless doctor gives its own. A record doctor made gives no merge, whatever the verdict: doctor reads a
    comment by commit alone, and status is what reads it against the run's base."""
    done = record["review"]
    sha, rounds, most = done["sha"], record.get("rounds", 0), record["max_rounds"]
    verdict = (read or read_verdict)(record, sha)
    posting = done.get("posting")  # resend's comment, written down before it was posted
    if posting and verdict == posting:
        done.update(posted=posting, verdict=posting)  # it landed, though gh may not have said so
        done.pop("posting")
        done.pop("posting_read", None)
    elif posting:
        # Not there: it never posted, or someone deleted it, or the older review now says something else. A
        # person sent it back, so it's never ready again until they send it again.
        done["posting_read"] = True
        record["waiting_on"] = "person"
        return ("posted, but the comment sending it back isn't on pull request #{}: send it again with "
                "python3 scripts/factories.py resend {}{}".format(record["pr"], record["run"],
                                                                  ": it sends the same reason" if done.get("because")
                                                                  else ""))
    if verdict is None:
        record["waiting_on"] = "person"
        return stalled(record, "posted, but there's no review comment for it from you yet")
    if done.get("posted") and verdict != done["posted"]:
        # Anyone with write access can edit a comment, and it still shows its author.
        return "posted, and " + end(record, "needs-person", "the review comment on {} changed after the loop "
                                    "posted it: it said {}, and now says {}".format(sha[:7], done["posted"], verdict))
    if verdict == "unreadable":
        # A person reads the review. The run isn't over: the factory's next commit is reviewed again.
        record.update(state="needs-person", why="couldn't read the review's verdict on {}".format(sha[:7]),
                      ended=None, waiting_on="person", until_new_commit=sha)
        return "posted, and needs a person: {}; a new commit from {} is reviewed again".format(
            record["why"], record["factory"])
    done["verdict"] = verdict
    if verdict in READY:
        record["checks"] = check_report(record, head, current)
        result = record["checks"]["result"]
        record["state"] = "ready for a person" if result == "ready for a person" else "returned"
        record["waiting_on"] = "checks" if result == "checks pending" else "person"  # failing: a person resends
        line = "says {}. Required checks, apart from any verdict: {}".format(verdict, checks_line(record["checks"]))
        if result in ("checks failing", "changes CI"):
            line += ". Send it back, with why, for round {} of {}: python3 scripts/factories.py resend {}".format(
                rounds + 1, most, record["run"])
        if result == "checks pending":
            return stalled(record, line)
        if result == "checks failing":
            return line
        if record.get("doctor"):
            return line + (". doctor gives no merge, whatever the review says: python3 scripts/factories.py status "
                           "gives it for a run, right before a person merges")
        line += (". {}, with the commit the review read, checking just before that it still targets {}: {}").format(
            "A person merges it" if result == "ready for a person" else "If a person merges it anyway",
            record["base"], merge_command(record))
        return line
    if record.get("sent_for") == sha:  # sent back already: the factory's next commit is what's due
        if overdue(record):
            return "says changes needed, and " + stop(record, "no new commit {:g} hours after round {} was sent back"
                                                        .format(record["time_limit_hours"], rounds))
        record["waiting_on"] = "factory"
        return "says changes needed; sent back for round {} of {}, waiting on {} for a new commit".format(
            rounds, most, record["factory"])
    if rounds >= most:
        return "says changes needed, and " + end(record, "needs-person", "changes still needed after {} round{}: a "
                                                 "person takes it from here".format(rounds, "" if rounds == 1 else "s"))
    record["waiting_on"] = "person"
    return "says changes needed. Send it back for round {} of {}: python3 scripts/factories.py resend {}".format(
        rounds + 1, most, record["run"])


def merge_command(record):
    """The merge, for a person to run, as one command. It checks the base just before merging and says why when
    it doesn't, and gh fails it if the head moved since the review. A retarget between the check and the merge
    isn't caught, since GitHub's merge pins the head and not the base: HOW-IT-WORKS says so. The step's
    merge_method is passed when it named one; otherwise gh asks, or fails with no terminal."""
    pr, repo, base = record["pr"], shlex.quote(record["repo"]), shlex.quote(record["base"])
    method = " --" + record["merge_method"] if record.get("merge_method") in MERGE_METHODS else ""
    refused = "Not merged: #{} no longer targets {}, or gh couldn't say which base it targets. Run status again.".format(
        pr, one_line(record["base"]))
    return ('if [ "$(gh pr view {pr} -R {repo} --json baseRefName -q .baseRefName)" = {base} ]; then '
            "gh pr merge {pr} -R {repo}{method} --match-head-commit {sha}; else echo {refused} >&2; false; fi").format(
        pr=pr, repo=repo, base=base, method=method, sha=shlex.quote(record["review"]["sha"]),
        refused=shlex.quote(refused))


def read_head(record):
    """The returned pull request's state and head commit, as GitHub has them now."""
    head, why = gh_json("pr", "view", str(record["pr"]), *repo_args(record["repo"]),
                        "--json", "state,isDraft,baseRefName,headRefOid,isCrossRepository,headRepositoryOwner")
    if why or not isinstance(head.get("headRefOid"), str):
        if not why:
            cant_use("no head commit")
        raise StepError("couldn't read pull request #{}: {}".format(record["pr"], why or "no head commit"))
    return head


def review(root, record, linked=(), run_review=False, read=None):
    """Move a returned run on from its pull request as GitHub has it now. With run_review, have the loop's
    read-only reader review a head not yet reviewed, and record what it did; without, only read, and name the
    review to run. linked is the issue's linked pull requests, for following the factory's one that replaced
    a closed one."""
    pr = record["pr"]
    head = read_head(record)
    if head["state"] == "MERGED":
        return end(record, "merged", "pull request #{} was merged".format(pr))
    if head["state"] != "OPEN":
        other, _ = factory_prs(record, [ref for ref in linked if ref.get("number") != pr])
        if other is None:
            return end(record, "closed", "pull request #{} was closed with nothing in its place".format(pr))
        record.update(pr=other, state="returned")
        record.pop("checks", None)
        return "pull request #{} was closed; following #{}, which replaced it: {}".format(
            pr, record["pr"], review(root, record, (), run_review, read))
    seen = record.get("head_seen") or {}
    if seen.get("sha") != head["headRefOid"]:
        record["head_seen"] = {"sha": head["headRefOid"], "at": now()}  # where the time limit counts from
    if record.get("until_new_commit"):
        if head["headRefOid"] == record["until_new_commit"]:
            record["waiting_on"] = "person"
            if overdue(record):
                return stop(record, "no new commit {:g} hours after {}: {}".format(
                    record["time_limit_hours"], waiting_since(record)[1], record["why"]))
            return "needs a person: {}".format(record["why"])
        record.update(state="returned", why=None)  # the factory pushed again: that commit is reviewed
        record.pop("until_new_commit")
    record["waiting_on"] = "factory"
    if head.get("baseRefName") != record["base"]:
        return stalled(record, "returned as pull request #{}, but it now targets {}, not {}, so it isn't reviewed"
                       .format(pr, shown(head.get("baseRefName")), record["base"]))
    if head.get("isDraft"):
        if overdue(record):
            return stop(record, "pull request #{} was still a draft after {:g} hours".format(pr, record["time_limit_hours"]))
        return "returned as pull request #{}, a draft: it's reviewed once it's marked ready".format(pr)
    done = record.get("review") or {}
    again = "python3 scripts/factories.py review {}".format(record["run"])
    reviewed_now = False
    if head["headRefOid"] != done.get("sha") or done.get("state") != "posted":
        # Ready only for the commit just checked: until this head's review and checks are read, it isn't.
        record["state"] = "returned"
        record.pop("checks", None)
        if not run_review:
            record["waiting_on"] = "review"
            if head["headRefOid"] != done.get("sha"):
                return stalled(record, "returned as pull request #{}, and {} isn't reviewed yet. Review it: {}".format(
                    pr, head["headRefOid"][:7], again))
            return stalled(record, "returned as pull request #{}; review of {} {}{}. Review it again: {}".format(
                pr, done["sha"][:7], done["state"], ": " + done["note"] if done.get("note") else "", again))
        line = run_loop_review(root, record, head)
        if line:
            return stalled(record, line)
        reviewed_now = True
    done = record["review"]
    line = "returned as pull request #{}; review of {}".format(pr, done["sha"][:7])
    if done["state"] != "posted":
        record["waiting_on"] = "review"
        return stalled(record, "{} {}{}. Review it again: {}".format(
            line, done["state"], ": " + done["note"] if done["note"] else "", again))
    # Read just now unless a review ran since, which takes minutes: then check_report reads it again.
    return "{} {}".format(line, after_review(record, head, None if reviewed_now else head, read))


def run_loop_review(root, record, head):
    """Run loop.py review --pr on the pull request's head and record its result. Returns status's line when
    there's no review of this head to go on from, or None when record["review"] now holds one."""
    pr = record["pr"]
    record["waiting_on"] = "review"
    target = review_target(root, record["repo"])
    if target is None:
        unnamed = unnamed_clones(root)
        return ("returned as pull request #{}, but there's no clone of {} here to review it from. Clone it into "
                "projects/, then: python3 scripts/factories.py review {}{}".format(
                    pr, record["repo"], record["run"],
                    ". A clone here names no repo, so it can't be that one: {}. factories/README.md's "
                    "*github.com only* says which origins count".format(
                        "; ".join("{}: {}".format(name, why) for name, why in unnamed)) if unnamed else ""))
    try:
        done = subprocess.run([sys.executable, str(LOOP)] + review_argv(pr, target), cwd=str(root),
                              stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=REVIEW_TIMEOUT_HOURS * 3600)
    except subprocess.TimeoutExpired:
        return "returned as pull request #{}, but the review didn't finish in {} hours, so it was stopped".format(
            pr, REVIEW_TIMEOUT_HOURS)
    if done.returncode:
        lines = done.stderr.strip().splitlines() or ["loop.py exited {}".format(done.returncode)]
        return "returned as pull request #{}, but the review didn't run: {}".format(pr, lines[-1][:200])
    found = review_result(done.stdout, pr)
    # Only a review of the commit GitHub has now: an older one's result stays in the loop's file.
    if found.get("sha") and found["sha"] != head["headRefOid"]:  # GitHub served loop.py an older head
        return ("returned as pull request #{}, but the loop's review is of {}, not {}, the head GitHub showed "
                "here: GitHub served loop.py an older head, or the factory pushed while the review ran{}. Run "
                "python3 scripts/factories.py review {} again in a minute").format(
            pr, shown(found["sha"]), shown(head["headRefOid"]),
            "; loop.py says: " + shown(found["note"]) if found.get("note") else "; the loop's log says which it read",
            record["run"])
    if found.get("sha") != head["headRefOid"]:
        return "returned as pull request #{}, no review of {} yet{}".format(
            pr, head["headRefOid"][:7], ": " + found["note"] if found.get("note") else ": see the loop's log")
    if found.get("base") != record["base"]:
        return "returned as pull request #{}, but the loop reviewed it against {}, not {}, so it doesn't count".format(
            pr, shown(found.get("base") or "no base"), record["base"])
    if found.get("state") == "posted" and not found.get("verdict"):
        return ("returned as pull request #{}, but the loop's review of {} posted with no verdict, so it doesn't "
                "count: see the loop's log, then python3 scripts/factories.py review {}").format(
            pr, head["headRefOid"][:7], record["run"])
    before = record.get("review") or {}
    record["review"] = {"sha": found["sha"], "state": found.get("state", ""), "note": found.get("note", ""),
                        "posted": found.get("verdict")}  # the verdict loop.py wrote, to check GitHub's against
    if before.get("sha") == found["sha"] and "verdict" in before:
        record["review"]["verdict"] = before["verdict"]
    return None


def review_argv(pr, target):
    """loop.py's arguments for reviewing pull request pr: the number only, so nothing the factory wrote reaches
    a command line or a prompt from here. A test parses them with loop.py's own parser."""
    return ["review", "--pr", str(int(pr))] + list(target)


def this_harness(root):
    """Whether root is the harness this script, and the loop.py it runs, are in. loop.py reviews from its own
    harness, so a review run for another's would read that one's clones and post from this one."""
    return Path(root).resolve() == LOOP.resolve().parent.parent


def review_result(stdout, pr):
    """review --pr's one JSON line on stdout, as a dict of loop.REVIEW_RESULT's keys, or {} when it printed
    none for pull request pr. Read from its output, never the loop's files: what that run of it found."""
    import loop  # noqa: E402
    try:
        found = one_line(json.loads(stdout.strip().split("\n")[-1]))  # loop.py's own line, marked as gh's are
    except (ValueError, IndexError):
        return {}
    if not isinstance(found, dict) or found.get("number") != int(pr) or set(found) != set(loop.REVIEW_RESULT):
        return {}
    return found


def advance(record, root, run_review=False):
    """Move a run on from what GitHub says. Returns one line saying where it is."""
    if is_over(record):
        return ended_line(record)
    issue = read_linked(record)
    labels = labels_of(issue)
    # Whatever the run's state: a factory can give up on a round as well as on the first build.
    if record["stopped_label"].lower() in labels:
        return stop(record, "the factory labelled #{} {}".format(record["issue"], record["stopped_label"]))
    refs = issue.get("closedByPullRequestsReferences") or []
    if record["state"] == "submitted":
        found, refused = factory_prs(record, refs)
        if found is not None:
            record.update(state="returned", pr=found)
        elif issue.get("state") == "CLOSED":
            return stop(record, "#{} was closed with nothing back".format(record["issue"]))
        else:
            if overdue(record, record["started"]):
                return stop(record, "no pull request after {:g} hours".format(record["time_limit_hours"]))
            record["waiting_on"] = "factory"
            return "; ".join(["waiting on {} for #{}".format(record["factory"], record["issue"])] + refused)
    return review(root, record, refs, run_review)


class Busy(Exception):
    """Another factories.py command holds the run's lock."""


NO_LOCKS = ("factories need a file lock, which this system doesn't have (fcntl, on macOS and Linux): nothing was "
            "read or changed")


@contextlib.contextmanager
def run_lock(path):
    """Hold the run's own lock while its record is read, moved on and written back, so a status, a review, a
    resend and a cancel of one run never write over each other. The loop's FileLock: the OS lets it go when
    the process ends, so nothing is ever left to clear."""
    import loop  # noqa: E402
    if not loop.file_locks():
        raise StepError(NO_LOCKS)
    with loop.FileLock(path.with_suffix(".lock")) as held:
        if not held:
            raise Busy()
        yield


def busy(path):
    print("{}: another factories.py command is moving it on; run this again once it's done".format(path.stem),
          file=sys.stderr)
    return 1


def read_record(path):
    """The run's record as it is on disk now, under its lock, or StepError when it can't be read."""
    try:
        return checked(json.loads(path.read_text()))
    except (OSError, ValueError) as err:
        raise StepError("{}: couldn't read its record: {}".format(path.stem, err))


def one_run(args):
    """The path of the run args names, or None after saying why: there's none by that name, or its record
    can't be read."""
    unreadable = []
    runs = load_runs(args.root, args.run, unreadable)
    if runs:
        return runs[0][0]
    print(unreadable[0] if unreadable else "No run named {}.".format(args.run), file=sys.stderr)
    return None


def labels_of(issue):
    """The issue's labels, in lower case: GitHub's labels match whatever their case."""
    return {str(label.get("name", "")).lower() for label in issue.get("labels") or [] if isinstance(label, dict)}


def move_runs(args, run_review):
    """status, and review: each run, under its lock, from its record as it is on disk now."""
    unreadable = []
    runs = load_runs(args.root, args.run, unreadable)
    for line in unreadable:
        print(line, file=sys.stderr)
    if not runs:
        if not unreadable:
            print("No run{}.".format(" named " + args.run if args.run else " yet"))
        return 1 if (args.run or unreadable) else 0
    failed = 1 if unreadable else 0
    for path, record in runs:
        try:
            with run_lock(path):
                record = read_record(path)
                if record["state"] == "ready for a person":
                    # Ready only on this command's own check: out of ready on disk before anything is read.
                    record.update(state="returned", waiting_on="person")
                    record.pop("checks", None)
                    write_json(path, record)
                line = advance(record, args.root, run_review)
                write_json(path, record)
        except Busy:
            failed = busy(path)
            continue
        except StepError as err:  # a record or a GitHub read it couldn't use: nothing more was written
            print(err if str(err).startswith(path.stem) else "{}: {}".format(path.stem, err), file=sys.stderr)
            failed = 1
            continue
        print("{}: {}".format(record["run"], line))
    return failed


def cmd_list(args):
    """Each run as its record has it. Reads .harness/factories/ alone: no gh call, no review."""
    unreadable = []
    runs = load_runs(args.root, unreadable=unreadable)
    for line in unreadable:
        print(line, file=sys.stderr)
    if not runs:
        print("No run yet." if not unreadable else "No other run.")
        return 1 if unreadable else 0
    whose = {"factory": "waiting on the factory", "person": "waiting on a person", "review": "waiting on a review",
             "checks": "waiting on its checks"}
    for _, record in runs:
        where = ended_line(record, label=False)
        parts = [record["run"], "#{} in {}".format(record["issue"], record["repo"]), record["factory"], where]
        if record.get("waiting_on") in whose and not is_over(record):
            parts.append(whose[record["waiting_on"]])
        if record.get("pr"):
            parts.append("pull request #{}".format(record["pr"]))
        if (record.get("review") or {}).get("verdict"):
            parts.append("review says {}".format(record["review"]["verdict"]))
        if (record.get("checks") or {}).get("result"):
            parts.append("checks: {}".format(record["checks"]["result"]))
        if record["state"] == "ready for a person":
            parts.append("run status {} right before merging: it checks again and gives the merge".format(record["run"]))
        parts.append("round {} of {}".format(record.get("rounds", 0), record["max_rounds"]))
        parts.append("started " + record["started"] + (", ended " + record["ended"] if record.get("ended") else ""))
        print(", ".join(parts) + label_left(record))
    return 1 if unreadable else 0


def cmd_status(args):
    """Read GitHub and move each run on. Writes nothing to GitHub and runs no review: it names the one to run."""
    return move_runs(args, run_review=False)


def cmd_review(args):
    """Have the loop review the run's pull request, posting its comment on your login, then move it on."""
    if not this_harness(args.root):
        print("{} isn't the harness this script is in, {}: run review from there.".format(
            args.root, LOOP.resolve().parent.parent), file=sys.stderr)
        return 1
    return move_runs(args, run_review=True)


def interactive():
    return sys.stdin.isatty()


def current_repo(repo):
    """(OWNER/NAME, its default branch) for --repo, or for this clone's repo when there's none."""
    name, branch, why = default_branch(repo)
    if why or not (repo or name):
        raise StepError("couldn't tell which repo the issue is in: {}. Name it with --repo.".format(
            why or "gh's answer had no name or default branch"))
    return repo or name, branch


def read_issue(number, repo):
    issue, why = gh_json("issue", "view", str(number), *repo_args(repo), "--json", "number,title,url,labels")
    if why or not isinstance(issue.get("number"), int):
        raise StepError("couldn't read issue #{}: {}".format(number, why or "no issue number"))
    return issue


def check_warning(repo):
    """The warning to show before the yes, or None when the repo's default branch requires a status check."""
    name, branch, found, problem = required_checks(repo)
    return warning_for(name, branch, found, problem)


def warning_for(name, branch, found, problem):
    if problem:
        return ("Warning: {}'s {}: {}. If it requires no status check, nothing independent checks what the "
                "factory returns before a person merges it.".format(name, branch, problem))
    if not found:
        return ("Warning: {}'s {} has no required status check, so nothing independent checks what the "
                "factory returns before a person merges it.".format(name, branch))
    return None


def confirmed(args, step, issue):
    """A yes to this one submission: --yes, or yes typed at the prompt."""
    return said_yes(args, "Submit #{} to {}? Type yes: ".format(issue["number"], step["factory"]))


def said_yes(args, question, need="Submitting needs a yes. Pass --yes to submit with no terminal."):
    if args.yes:
        return True
    if not interactive():
        print(need, file=sys.stderr)
        return False
    try:
        answer = input(question)
    except EOFError:
        return False
    return answer.strip().lower() == "yes"


def cmd_resend(args):
    """Send a run back to its factory for one more round, after a yes, once per reviewed commit."""
    path = one_run(args)
    if path is None:
        return 1
    try:
        with run_lock(path):
            return resend(args, path, read_record(path))
    except Busy:
        return busy(path)
    except StepError as err:
        print(err, file=sys.stderr)
        return 1


def resend(args, path, record):
    """cmd_resend, holding the run's lock, with its record as it is on disk now."""
    review = record.get("review") or {}
    rounds, most = record.get("rounds", 0), record["max_rounds"]
    verdict = review.get("verdict")
    if review.get("posting") and not review.get("posting_read"):
        print("The last send-back of {} may have posted: run status first, so it reads whether it did.".format(
            record["run"]), file=sys.stderr)
        return 1
    if record["state"] not in ("returned", "ready for a person") or verdict not in ("changes needed",) + READY:
        print("Nothing to send back: {} reads {}{}.".format(
            record["run"], record["state"], ", " + review["verdict"] if review.get("verdict") else ""), file=sys.stderr)
        return 1
    if rounds >= most:
        print("{} has had its {} rounds: a person takes it from here.".format(record["run"], most), file=sys.stderr)
        return 1
    try:
        head = read_head(record)
    except StepError as err:
        print(err, file=sys.stderr)
        return 1
    if head.get("state") != "OPEN":
        print("Pull request #{} is {}: nothing to send back.".format(record["pr"], str(head.get("state")).lower()),
              file=sys.stderr)
        return 1
    try:
        issue = read_linked(record)
    except StepError as err:
        print(err, file=sys.stderr)
        return 1
    on_issue = labels_of(issue)
    stopped = record["stopped_label"].lower() in on_issue
    if stopped or issue.get("state") == "CLOSED":
        print("#{} {}: the factory has stopped, so nothing is sent back. Run status to end the run.".format(
            record["issue"], "carries {}".format(record["stopped_label"]) if stopped
            else "is closed"), file=sys.stderr)
        return 1
    if record["submit_label"].lower() in on_issue:
        print("#{} still carries {}: the factory hasn't taken up the last submission, so adding it again would "
              "send nothing. Wait for it, or ask the factory.".format(record["issue"], record["submit_label"]),
              file=sys.stderr)
        return 1
    if head["headRefOid"] != review["sha"]:
        print("The review is of {}, and pull request #{} is now at {}: run status first.".format(
            review["sha"][:7], record["pr"], head["headRefOid"][:7]), file=sys.stderr)
        return 1
    if record.get("sent_for") == review["sha"]:
        print("The review of {} was already sent back, as round {}.".format(review["sha"][:7], rounds),
              file=sys.stderr)
        return 1
    why = None
    if verdict in READY:
        try:  # read again: a check re-run since the last status may pass now
            checks = check_report(record, head, head)
        except StepError as err:
            print(err, file=sys.stderr)
            return 1
        found = checks_line(checks) if checks.get("result") in ("checks failing", "changes CI") else None
        because = getattr(args, "because", None) or review.get("because")  # kept from a send-back that didn't land
        why = "\n\n".join(part for part in (because, found) if part)
        if not why:
            print("The review of {} says {}, and its required checks read {}. To send it back anyway, say why, for "
                  "the factory to read: python3 scripts/factories.py resend {} --because \"...\"".format(
                      review["sha"][:7], verdict, checks.get("result"), record["run"]), file=sys.stderr)
            return 1
    if why:
        print("Sending #{} back to {} for round {} of {} posts one comment on pull request #{} saying why, ending "
              "VERDICT: changes needed, and adds the label {} to the issue, and nothing else.".format(
                  record["issue"], record["factory"], rounds + 1, most, record["pr"], record["submit_label"]))
    else:
        print("Sending #{} back to {} for round {} of {} adds the label {} to the issue, and nothing else. The "
              "review's comment on pull request #{} says what to change.".format(
                  record["issue"], record["factory"], rounds + 1, most, record["submit_label"], record["pr"]))
    if not said_yes(args, "Send #{} back to {}? Type yes: ".format(record["issue"], record["factory"])):
        print("Not sent.")
        return 1
    if why:
        import loop  # noqa: E402  the comment a factory's loop reads, built as the loop's review builds it
        body = loop.review_comment("A person sent this back after a review that said {}:\n\n{}\n\n"
                                   "VERDICT: changes needed".format(verdict, why), review["sha"],
                                   header="A person sent this back to the factory, after reading the review.")
        # Written down first: if gh dies or times out after GitHub took it, status still knows it's ours.
        review["posting"] = "changes needed"
        if because:
            review["because"] = because
        review.pop("posting_read", None)
        record["review"] = review
        write_json(path, record)
        code, out, err = gh("pr", "comment", str(record["pr"]), *repo_args(record["repo"]), "--body", body)
        if code:
            print("couldn't post why on pull request #{}: {}. If GitHub took it anyway, status reads it as this "
                  "run's own.".format(record["pr"], said(code, out, err)), file=sys.stderr)
            return 1
        # Ours now: what the run reads back is this comment's verdict, not a change by someone else.
        review.pop("posting")
        review.update(verdict="changes needed", posted="changes needed")
        record.update(review=review, state="returned")
        record.pop("checks", None)
        write_json(path, record)
    code, out, err = gh("issue", "edit", str(record["issue"]), *repo_args(record["repo"]),
                        "--add-label", record["submit_label"])
    if code:
        print("couldn't add {} to #{}: {}".format(record["submit_label"], record["issue"], said(code, out, err)),
              file=sys.stderr)
        return 1
    record.update(rounds=rounds + 1, sent_for=review["sha"], sent_at=now())
    write_json(path, record)
    print("Sent #{} back to {}: round {} of {}.".format(record["issue"], record["factory"], rounds + 1, most))
    return 0


def cmd_cancel(args):
    """End a run that hasn't ended, as cancelled, and take the step's submit label off the issue so the factory
    doesn't start it: both on one yes. Without it, show what it would do and change nothing."""
    path = one_run(args)
    if path is None:
        return 1
    try:
        with run_lock(path):
            return cancel(args, path, read_record(path))
    except Busy:
        return busy(path)
    except StepError as err:
        print(err, file=sys.stderr)
        return 1


def cancel(args, path, record):
    """cmd_cancel, holding the run's lock. The label comes off first, so a label that won't come off leaves
    the run as it was rather than over with the factory still able to start it."""
    if is_over(record):
        print("{} already ended: {}".format(record["run"], ended_line(record)), file=sys.stderr)
        return 1
    label = record["submit_label"]
    on_issue = label.lower() in labels_of(read_linked(record))  # unreadable: StepError, and nothing changes
    print("Cancelling {} ends it as cancelled, so status leaves it alone and #{} can be dispatched again.".format(
        record["run"], record["issue"]))
    if on_issue:
        print("#{} still carries {}, so {} may yet start it: cancelling also takes it off, and nothing else: "
              "{}".format(record["issue"], label, record["factory"], unlabel_command(record)))
    else:
        print("#{} doesn't carry {}: there's nothing to take off.".format(record["issue"], label))
    print("Cancelling doesn't withdraw what {0} has already taken: if it opens a pull request for #{1} after this, "
          "close it and tell {0} by hand.".format(record["factory"], record["issue"]))
    if not said_yes(args, "Cancel {}? Type yes: ".format(record["run"]),
                    need="Cancelling needs a yes. Pass --yes to cancel with no terminal."):
        print("Nothing changed.")
        return 1
    if on_issue:
        code, out, err = gh(*unlabel_args(record))
        if code:
            print("couldn't take {} off #{}, so the run wasn't cancelled: {}".format(
                label, record["issue"], said(code, out, err)), file=sys.stderr)
            return 1
    end(record, "cancelled", "a person cancelled it")
    write_json(path, record)
    print("Cancelled {}{}.".format(record["run"], ", and took {} off #{}".format(label, record["issue"])
                                   if on_issue else ""))
    return 0


def cmd_dispatch(args):
    import loop  # noqa: E402
    if not loop.file_locks():  # nothing could watch or cancel the run it would start
        print(NO_LOCKS, file=sys.stderr)
        return 1
    try:
        steps = read_steps(args.root)
        if not steps:
            raise StepError("No factory is configured: add a step to factories.json first.")
        step = steps[0]
        found = resolve_commit(step)
        repo, base = current_repo(args.repo)
        issue = read_issue(args.issue, repo)
        refusal = dispatch_refusal(args.root, step, repo, issue)
        if not refusal and step.get("factory_login"):
            step = dict(step, factory_id=account_id(step["factory_login"]))
        warning = None if refusal else check_warning(repo)
    except StepError as err:
        print(err, file=sys.stderr)
        return 1
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    print("Factory: {} ({}, commit {}{})".format(step["factory"], step["where"], found["commit"] or "none named",
                                                "" if found["verified"] else ", declared"))
    print("Repo:    {}".format(repo))
    print("Issue:   #{} {}".format(issue["number"], issue["title"]))
    print("Submitting adds the label {} to the issue, and nothing else.".format(step["submit_label"]))
    if found.get("dirty") == "unchecked":
        print("Warning: factories/{}'s own git config names a filter or fsmonitor, so it wasn't checked for "
              "uncommitted changes: its commit may not be all of the code that would run.".format(step["factory"]))
    elif found.get("dirty"):
        print("Warning: factories/{} has uncommitted changes, so its commit isn't all of the code that would "
              "run. The record says so.".format(step["factory"]))
    if warning:
        print(warning)
    notice = privacy_notice(args.root, step)
    if notice:
        print(notice)
    if not confirmed(args, step, issue):
        print("Not submitted.")
        return 1
    code, out, err = gh("issue", "edit", str(args.issue), *repo_args(repo), "--add-label", step["submit_label"])
    if code:
        print("couldn't add {} to #{}: {}".format(step["submit_label"], args.issue, said(code, out, err)),
              file=sys.stderr)
        return 1
    path = record_run(args.root, step, found, issue, repo, base)
    print("Submitted #{} to {}. Its record is {}.".format(issue["number"], step["factory"], path.name))
    return 0


def dispatch_refusal(root, step, repo, issue):
    """Why this issue can't go to the factory, or None: the loop may build it, the step's label is the
    loop's, the factory already stopped on it, or a run on it hasn't ended."""
    labels = labels_of(issue)
    ready = {label.lower() for label in ready_labels(root, repo)}
    if step["submit_label"].lower() in ready:
        return ("Step {} submits with {}, which is the loop's ready label for {}: the loop and the factory would "
                "both build it. Give the step a label of its own.".format(step["factory"], step["submit_label"], repo))
    for label in sorted(ready & labels):
        return ("#{} carries {}, so the loop may build it. Take that label off before handing it to a "
                "factory.".format(issue["number"], label))
    if step["stopped_label"].lower() in labels:
        return ("#{} carries {}: the factory stopped on it. Read why, and take the label off before sending it "
                "again.".format(issue["number"], step["stopped_label"]))
    unreadable = []
    for _, record in load_runs(root, unreadable=unreadable):
        if (str(record.get("repo", "")).lower() == repo.lower() and record.get("issue") == issue["number"]
                and not is_over(record)):
            return "#{} already has a run that hasn't ended: {} ({}).".format(
                issue["number"], record["run"], record.get("state"))
    for line in unreadable:
        if line.startswith("run-{}-".format(issue["number"])):
            return ("{}. A run on #{} may still be live: fix or remove that record before dispatching it "
                    "again.".format(line, issue["number"]))
    return None


def cmd_steps(args):
    try:
        steps = read_steps(args.root)
        commits = [resolve_commit(step) for step in steps]
    except StepError as err:
        print(err, file=sys.stderr)
        return 1
    if slug(args.root) is None:
        print("Warning: this harness's {}. Factories read pull requests and checks from github.com only: "
              "factories/README.md's *github.com only* says which origins count.".format(origin_why(args.root)))
    if not steps:
        print("No factory is configured: nothing to do.")
        return 0
    for step, found in zip(steps, commits):
        state = "verified" if found["verified"] else "declared, unverified"
        print("{factory}: {where}, submit label {submit_label}, stopped label {stopped_label}, "
              "{time_limit_hours} hours, {max_rounds} rounds".format(**step))
        print("  commit {} ({}{})".format(found["commit"] or "none named", state,
                                          "" if found["pinned"] else ", unpinned"))
    return 0


def call_named(call):
    """A recorded gh call as a person would type it, up to its first option carrying a query or fields."""
    shown = []
    for arg in call:
        if arg in ("--jq", "--json", "-f", "--search"):
            break
        shown.append(arg)
    return "gh " + " ".join(shown)


def call_result(entry):
    """What one recorded gh call came to: ok, or its exit code and what it said, then each note a reader made."""
    shown = ("exit {}: {}".format(entry["code"], entry["said"]) if entry["code"] else
             "exit 0" if entry["notes"] else "ok")
    return "; ".join([shown] + entry["notes"])


# What one of doctor's stages came to.
READ, UNUSABLE, STOP = "read", "unusable", "stop"


def doctor_reads(root, repo, number, step, said_of):
    """Make the reads a run's status makes for pull request number, with the record dispatch would make and a
    posted review of its head, through the run's own review(), so it stops where a run stops. With no review
    comment of yours on the head it reads it as ready, so the checks are read. said_of(label, how) runs one
    stage, which returns READ, UNUSABLE for a reply it couldn't use, or STOP where a run would stop, with what
    it came to; anything but READ ends the reads there."""
    record = {}
    closers = []  # the issue's linked pull requests, which review() follows when this one closed

    def the_record():
        _, base, why = default_branch(repo)
        if why:
            return UNUSABLE, "couldn't read {}'s default branch: {}".format(repo, why)
        found = {"commit": None, "pinned": None, "verified": False}
        record.update(new_record(dict(step, factory_id=account_id(step["factory_login"])), found,
                                 {"number": None, "title": ""}, repo, base), pr=number, state="returned", run="<run>",
                      doctor=True)
        return READ, "{} by factory_login {}, into {}".format(record["factory"], record["factory_login"], base)
    if not said_of("the record dispatch would make", the_record):
        return

    def the_issue():
        found, why = gh_json("pr", "view", str(number), *repo_args(repo), "--json", "closingIssuesReferences")
        if why:
            return UNUSABLE, "couldn't read pull request #{}: {}".format(number, why)
        refs = found.get("closingIssuesReferences")
        if not isinstance(refs, list) or not all(isinstance(ref, dict) for ref in refs):
            cant_use("the issues it closes aren't a list")
            return UNUSABLE, "couldn't read which issues pull request #{} closes".format(number)
        home = "https://github.com/{}/issues/".format(repo.lower())
        ours = [ref for ref in refs if isinstance(ref.get("number"), int)
                and str(ref.get("url") or "").lower().startswith(home)]
        if not ours:
            return STOP, "it closes no issue in {}, so a run would never find it".format(repo)
        record["issue"] = ours[0]["number"]
        issue = read_linked(record)
        linked = issue.get("closedByPullRequestsReferences")
        if not isinstance(linked, list) or not all(isinstance(ref, dict) for ref in linked):
            cant_use("the pull requests that close it aren't a list")
            return UNUSABLE, "couldn't read which pull requests close #{}".format(record["issue"])
        closers.extend(linked)
        if record["stopped_label"].lower() in labels_of(issue):
            return STOP, "#{} carries {}, so a run on it stops".format(record["issue"], record["stopped_label"])
        found, refused = factory_prs(record, linked)
        if found == number:
            return READ, "#{} links it, and it's the factory's own".format(record["issue"])
        return STOP, "; ".join(["a run on #{} {}".format(record["issue"], "follows #{}".format(found) if found else
                                                            "follows none of its pull requests")] + refused)
    if not said_of("the issue it closes", the_issue):
        return

    head = {}

    def the_head():
        head.update(read_head(record))
        return READ, "{}{}, at {}, into {}".format(str(head.get("state", "")).lower(),
                                                  ", a draft" if head.get("isDraft") else "",
                                                  head["headRefOid"][:7], head.get("baseRefName"))
    if not said_of("its head", the_head):
        return

    def what_status_says():
        # As the loop's review of this head would leave the record: status reads its verdict, and for a ready
        # one the required checks. A draft, another base or changes needed stop before either, as a run does.
        record["review"] = {"sha": head["headRefOid"], "state": "posted", "note": "", "posted": None}
        assumed = []  # each head read as ready with no review to go on, a followed pull request's included

        def read(run, sha):
            verdict = read_verdict(run, sha)
            if verdict is None:  # nobody has reviewed it yet: read it as ready, so the checks are read
                assumed.append(sha)
                return "ready"
            return verdict
        line = review(root, record, closers, read=read)
        if assumed:
            line = "no review comment from you for {} yet, so doctor reads it as ready: {}".format(
                assumed[-1][:7], line)
        if "checks" not in record:
            return STOP, line
        return UNUSABLE if record["checks"]["unread"] else READ, line
    said_of("what status says", what_status_says)


def cmd_doctor(args):
    """Make the reads a run's status makes for one pull request, with the record dispatch would make and a
    posted review of its head, read as ready when you haven't reviewed it, through the run's own review(),
    changing nothing, then say what status would. Exit 1 when it stops before the required checks.
    List every gh call with what it came to, a reply a reader couldn't use or a row it skipped noted on the
    call that gave it, with nothing GitHub sent printed raw. For a run that stalls on GitHub's answers, or
    before the first one."""
    try:
        steps = read_steps(args.root)
    except StepError as err:
        print(err, file=sys.stderr)
        return 1
    if not steps or not steps[0].get("factory_login"):
        print("doctor reads with the record dispatch would make, and a run that can be ready needs the step's "
              "factory_login: name it in factories.json first.", file=sys.stderr)
        return 1
    print("Reading what a run's status reads for {} pull request #{}, with the record dispatch would make and a "
          "posted review of its head, changing nothing.".format(args.repo, args.pr))
    stages = []

    def said_of(label, how):
        try:
            state, text = how()
        except StepError as err:
            state, text = UNUSABLE, str(err)
        stages.append((label, state, text))
        return state == READ
    with read_only() as made:
        doctor_reads(args.root, args.repo, args.pr, steps[0], said_of)
    print("Each call, in order:")
    for entry in made:
        print("- {}: {}".format(call_named(entry["call"]), call_result(entry)))
    print("What a run makes of them:")
    for label, _, text in stages:
        print("- {}: {}".format(label, text))
    unusable = sum(1 for _, state, _ in stages if state == UNUSABLE)
    unusable += sum(1 for entry in made if entry.get("unusable"))
    if unusable:
        print("{} couldn't be used or read: each is named above, on the call that gave it.".format(unusable))
        return 1
    if any(state == STOP for _, state, _ in stages):
        print("It stopped where a run would, before the required checks, so they weren't read.")
        return 1
    print("Every reply could be used.")
    return 0


def main(argv=None):
    out, err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = Printable(out), Printable(err)  # anything GitHub sent, or an argument, printed as ?
    try:
        return run_command(parsed_args(argv))
    finally:
        sys.stdout, sys.stderr = out, err


def parsed_args(argv):
    parser = argparse.ArgumentParser(description="Hand an issue to another factory, and review what comes back.")
    sub = parser.add_subparsers(dest="command", required=True)
    steps = sub.add_parser("steps", help="the configured step, checked, or that there's none")
    steps.add_argument("--root", type=Path, default=Path.cwd(), help="the harness root: the current folder by default")
    dispatch = sub.add_parser("dispatch", help="hand one issue to the factory, after a yes")
    dispatch.add_argument("issue", type=int)
    dispatch.add_argument("--repo", help="the issue's repo as OWNER/NAME: the current repo by default")
    dispatch.add_argument("--yes", action="store_true", help="submit without asking")
    dispatch.add_argument("--root", type=Path, default=Path.cwd(), help="the harness root: the current folder by default")
    status = sub.add_parser("status", help="read GitHub and move each run on; writes nothing to GitHub, runs no review")
    status.add_argument("run", nargs="?", help="one run by name: every run by default")
    status.add_argument("--root", type=Path, default=Path.cwd(), help="the harness root: the current folder by default")
    review = sub.add_parser("review", help="have the loop review a run's pull request, posting on your login, then "
                                           "move it on")
    review.add_argument("run", help="the run, as status names it")
    review.add_argument("--root", type=Path, default=Path.cwd(), help="the harness root: the current folder by default")
    resend = sub.add_parser("resend", help="send a run back to its factory for one round, after a yes")
    resend.add_argument("run", help="the run, as status names it")
    resend.add_argument("--yes", action="store_true", help="send without asking")
    resend.add_argument("--because", help="why it goes back, when its review said ready: posted for the factory "
                                          "to read")
    resend.add_argument("--root", type=Path, default=Path.cwd(), help="the harness root: the current folder by default")
    cancel = sub.add_parser("cancel", help="end a run that hasn't ended; takes the submit label off only on a yes")
    cancel.add_argument("run", help="the run, as status names it")
    cancel.add_argument("--yes", action="store_true", help="take the submit label off without asking")
    cancel.add_argument("--root", type=Path, default=Path.cwd(), help="the harness root: the current folder by default")
    doctor = sub.add_parser("doctor", help="make the reads a run's status makes for one pull request, through the "
                                           "same code, changing nothing, and list every call with its result")
    doctor.add_argument("--repo", required=True, help="the pull request's repo as OWNER/NAME")
    doctor.add_argument("--pr", type=int, required=True, help="the pull request's number")
    doctor.add_argument("--root", type=Path, default=Path.cwd(), help="the harness root: the current folder by default")
    listing = sub.add_parser("list", help="each run as its record has it; reads nothing from GitHub")
    listing.add_argument("--root", type=Path, default=Path.cwd(), help="the harness root: the current folder by default")
    return parser.parse_args(argv)


class Printable:
    """A stream that writes each character a terminal could act on, or that hides or reorders what follows, as
    ?: every command prints what GitHub sent, a title or a branch name, and either can carry any of them."""

    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        return self.stream.write("\n".join(printable(line) for line in str(text).split("\n")))

    def __getattr__(self, name):
        return getattr(self.stream, name)


def run_command(args):
    return {"steps": cmd_steps, "dispatch": cmd_dispatch, "status": cmd_status, "review": cmd_review,
            "resend": cmd_resend, "cancel": cmd_cancel, "doctor": cmd_doctor,
            "list": cmd_list}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
