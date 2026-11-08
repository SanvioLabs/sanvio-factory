#!/usr/bin/env python3
"""Run a harness through a suite of jobs and score the result.

Usage:
    python3 scripts/eval_harness.py run SUITE --start "COMMAND" --owner ORG [--harness PATH] [--clone-into DIR]
                                        [--merge-in-run-repo] [--usage-command "COMMAND"]
                                        [--timeout MINUTES] [--yes]
    python3 scripts/eval_harness.py resume RUN [--end]
    python3 scripts/eval_harness.py stop RUN "WHY"
    python3 scripts/eval_harness.py compare A B
    python3 scripts/eval_harness.py list
    python3 scripts/eval_harness.py validate SUITE

A suite is a folder:

    suite.json      name, seed, key, issues (in order), required_checks, optional public_example
    seed/           the repo's starting contents, including its CI workflow. Made-up data only
    issues/         one Markdown file per issue, its first line the title
    key/
      score         executable: reads RUN_DIR, BASE_SHA, PR_NUMBERS, RUN_REPO and PR_DATA (a JSON file of
                    each pull request's number, state, headRefName, baseRefOid, headRefOid, body and
                    comments), and prints {"tests": [{"name", "passed"}], "traps": [{"name", "avoided"}]}
      reference/    files that overlay the seed to make the right answer
      wrong/<name>/ files that overlay the seed to make a known wrong answer

--start runs in the harness's folder, once per issue. It may use {issue}, {repo}, {clone} and {project}
(the clone's path from the harness), which only ever hold values this tool made, shell-quoted. A start
command that fails or times out ends the run, recorded as a stop, and what exists still gets scored.

With --merge-in-run-repo the tool merges each issue's pull request once its required checks pass, and only
in the repo this run created. Without it, the run stops at each merge and exits 3: merge it, then resume.
Run repos are private, stay until a person deletes them, and nothing here deletes one.

When the run ends, a fresh clone outside the harness is scored: the default branch, or the last pull
request if it never merged. Its history is checked for the key's files, and key/score runs with anything
named like a secret out of its environment. The run's folder in .sanvio/harness-evals/ gets one
result.json: the suite, the harness commit, tests, traps, key leaks, time, stops, rounds, tokens and cost.
Cost comes from --usage-command, a command that prints one number. Failing that, it's this harness's own loop
usage when --start runs its scripts/loop.py. Failing that it reads "not reported", never zero. Rounds and
tokens come only from that loop usage, so another harness's read "not reported". Exits 0 when every test
and trap is clean with no leak, 1 otherwise. compare takes two run names or result files.

validate spends no model tokens and creates no repo. It passes only when the seed fails, every wrong
answer fails, and the reference passes every test and trap. Exits 0 when sound, 1 when not, 2 when the
suite can't be read.

Scoring runs key/score on the checkout, and that usually runs code an agent wrote, on this machine. It gets
an empty HOME and no gh login, so it reads pull requests from PR_DATA, not GitHub. It still has the network
and whatever this user can read outside HOME, the suite's key included. Keep a private suite's folder
somewhere its agents aren't allowed to read: this tool refuses a key inside the harness or the clone folder,
and finds a key committed to a run repo, but can't see what an agent read.

What a run acts on (its repo, the merge flag, the start and usage commands, the suite's path) is kept in a
sealed copy in ~/.sanvio-evals, or SANVIO_EVALS_HOME, and resume takes it from there, so an agent editing
the harness's copy can't redirect it. Ctrl-C ends the start command too; resume --end then scores what the
interrupted run got to. Needs a POSIX system.

From the Sanvio Labs harness starter, MIT: https://github.com/SanvioLabs/sanvio-harness-starter
"""
import argparse
import filecmp
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import names  # noqa: E402  beside this file: the state and home folders, old names included for a release
import loop  # noqa: E402  beside this file: the loop's own usage arithmetic and secret-stripped environment

REQUIRED_FIELDS = ("name", "seed", "key", "issues", "required_checks")
SCORE_TIMEOUT = 900
USAGE_TIMEOUT = 120
CI_POLL_SECONDS = 30
MERGE_TRIES = 3
PULL_FIELDS = "number,state,headRefName,baseRefOid,headRefOid,body,comments"  # what key/score gets in PR_DATA
WAITING = 3  # the exit code while a run waits for a person
# What a run acts on: kept in a sealed copy outside the harness, and taken from there over the harness's copy.
SEALED = ("repo", "repo_id", "merge", "start", "usage_command", "suite_path", "harness", "clone", "timeout_minutes",
          "base_sha", "harness_commit", "harness_dirty")
OUTSIDE_ONLY = ("suite_path",)
# So a commit works on a machine with no git identity set.
GIT_IDENTITY = ["-c", "user.name=eval-harness", "-c", "user.email=eval-harness@example.invalid"]


class SuiteError(Exception):
    """A suite can't be used, and nothing has started."""


class RunError(Exception):
    """A run can't go on, and a person needs to know why."""


def is_under(path, folder):
    """Whether path is folder or anything inside it. Both are resolved first."""
    path, folder = Path(path).resolve(), Path(folder).resolve()
    return path == folder or folder in path.parents


def key_files(key):
    """The key's files that hold something: an empty file gives nothing away."""
    return [path for path in Path(key).rglob("*") if path.is_file() and path.stat().st_size]


def check_seed_against_key(seed, key):
    """Refuse a seed that could hand the key to whoever works in it."""
    answers = key_files(key)
    for path in Path(seed).rglob("*"):
        name = path.relative_to(seed)
        if path.is_symlink():
            if is_under(path, key):
                raise SuiteError("{} in the seed links to the key".format(name))
        elif path.is_file():
            for answer in answers:
                if filecmp.cmp(str(path), str(answer), shallow=False):
                    raise SuiteError("{} in the seed is a copy of {} in the key".format(name, answer.name))


def load_suite(folder, harness, clone_into=None):
    """Read folder/suite.json and return it with its paths resolved, or raise SuiteError.

    Runs before a run creates anything, so a suite that could leak its key never starts."""
    folder = Path(folder).resolve()
    config_path = folder / "suite.json"
    try:
        config = json.loads(config_path.read_text())
    except OSError:
        raise SuiteError("no suite.json in {}".format(folder))
    except ValueError as err:
        raise SuiteError("suite.json isn't JSON: {}".format(err))
    missing = [field for field in REQUIRED_FIELDS if field not in config]
    if missing:
        raise SuiteError("suite.json has no {}".format(", ".join(missing)))

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", str(config["name"])):
        raise SuiteError("the suite's name has to work in a repo name: {}".format(config["name"]))
    if not config["required_checks"]:
        raise SuiteError("required_checks is empty, so nothing would hold a merge back")

    seed, key = folder / config["seed"], folder / config["key"]
    if is_under(key, seed) or is_under(seed, key):
        raise SuiteError("the key can't be under the seed, or the seed under the key")
    for name, path in (("seed", seed), ("key", key)):
        if not path.is_dir():
            raise SuiteError("the suite's {} folder is missing: {}".format(name, path))
    if not (key / "score").is_file():
        raise SuiteError("the suite has no key/score program")
    issues = [folder / issue for issue in config["issues"]]
    for issue in issues:
        if not issue.is_file():
            raise SuiteError("issue file not found: {}".format(issue))

    public = bool(config.get("public_example"))
    if not public:
        if is_under(key, harness):
            raise SuiteError("the key is inside the harness, where its agents could read it")
        if clone_into and is_under(key, clone_into):
            raise SuiteError("the key is inside the clone folder, where its agents could read it")
    check_seed_against_key(seed, key)
    return {"name": config["name"], "folder": folder, "seed": seed, "key": key, "issues": issues,
            "required_checks": list(config["required_checks"]), "public_example": public}


def git(*args, cwd):
    """git's stdout, stripped. Raises CalledProcessError when it fails."""
    done = subprocess.run(["git"] + list(args), cwd=str(cwd), capture_output=True, text=True, check=True)
    return done.stdout.strip()


def score_checkout(key, run_dir, base_sha, pulls=(), repo=""):
    """key/score's verdict on run_dir: {"tests": [...], "traps": [...]}, or {"not_scored": why}.

    It runs code an agent wrote, so it gets an empty home and no gh login, and reads each pull request's
    details from the PR_DATA file rather than from GitHub."""
    with tempfile.TemporaryDirectory() as home:
        pulls_file = Path(home) / "pull-requests.json"
        pulls_file.write_text(json.dumps(list(pulls)))
        (Path(home) / "gh").mkdir()
        env = dict(loop.env_for_tests(os.environ), RUN_DIR=str(run_dir), BASE_SHA=base_sha, RUN_REPO=repo,
                   PR_NUMBERS=" ".join(str(pull["number"]) for pull in pulls), PR_DATA=str(pulls_file),
                   HOME=home, XDG_CONFIG_HOME=str(Path(home) / ".config"), GH_CONFIG_DIR=str(Path(home) / "gh"))
        try:
            done = subprocess.run([str(Path(key) / "score")], cwd=str(run_dir), env=env, capture_output=True,
                                  text=True, timeout=SCORE_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as err:
            return {"not_scored": "key/score didn't finish: {}".format(err)}
    if done.returncode:
        return {"not_scored": "key/score exited {}".format(done.returncode)}
    try:
        found = json.loads(done.stdout)
        tests = [{"name": str(t["name"]), "passed": bool(t["passed"])} for t in found["tests"]]
        traps = [{"name": str(t["name"]), "avoided": bool(t["avoided"])} for t in found["traps"]]
    except (ValueError, KeyError, TypeError):
        return {"not_scored": "key/score printed something other than its JSON"}
    return {"tests": tests, "traps": traps}


def all_clean(score):
    """Every test passed and every trap avoided, with at least one test run."""
    return bool(score.get("tests")) and all(t["passed"] for t in score["tests"]) \
        and all(t["avoided"] for t in score["traps"])


def overlay_and_score(suite, overlay, workspace):
    """Score a temporary git copy of the seed, committed, with overlay's files committed on top."""
    work = Path(workspace) / "repo"
    shutil.copytree(str(suite["seed"]), str(work), symlinks=True)
    git("init", "-q", cwd=work)
    git("add", "-A", cwd=work)
    git(*GIT_IDENTITY, "commit", "-q", "--allow-empty", "-m", "seed", cwd=work)
    base = git("rev-parse", "HEAD", cwd=work)
    if overlay:
        for path in Path(overlay).rglob("*"):
            if path.is_file():
                target = work / path.relative_to(overlay)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(path), str(target))
        git("add", "-A", cwd=work)
        git(*GIT_IDENTITY, "commit", "-q", "--allow-empty", "-m", "answer", cwd=work)
    return score_checkout(suite["key"], work, base)


def validate_suite(suite):
    """Everything wrong with the suite as a test of a harness. Empty means it's sound."""
    problems = []
    key = suite["key"]
    reference = key / "reference"
    wrong = sorted(path for path in (key / "wrong").glob("*") if path.is_dir())
    if not reference.is_dir():
        problems.append("no key/reference")
    if not wrong:
        problems.append("no key/wrong answers")

    def verdict(overlay):
        with tempfile.TemporaryDirectory() as workspace:
            return overlay_and_score(suite, overlay, workspace)

    def check_fails(label, overlay):
        score = verdict(overlay)
        if "not_scored" in score:
            problems.append("{}: not scored: {}".format(label, score["not_scored"]))
        elif all_clean(score):
            problems.append("{} passes every test and trap, and it should fail".format(label))

    check_fails("the seed", None)
    for answer in wrong:
        check_fails("wrong answer {}".format(answer.name), answer)
    if reference.is_dir():
        score = verdict(reference)
        if "not_scored" in score:
            problems.append("the reference: not scored: {}".format(score["not_scored"]))
        elif not all_clean(score):
            problems.append("the reference fails a test or a trap, and it should pass all of them")
    return problems


def gh(*args, stdin=None):
    """(exit code, stdout, stderr) for one gh call. It uses the person's own login, and never reads it."""
    done = subprocess.run(["gh"] + list(args), capture_output=True, text=True, input=stdin)
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def said(code, out, err):
    """What a failed gh call said. gh api puts its error on stdout."""
    return err or out or "gh exited {}".format(code)


def gh_ok(why, *args, stdin=None):
    """gh's stdout, or RunError saying why it was called and what it said."""
    code, out, err = gh(*args, stdin=stdin)
    if code:
        raise RunError("{}: {}".format(why, said(code, out, err)))
    return out


def runs_dir():
    """Each run's state, logs and result, in the harness. Its agents can write here."""
    return names.state_dir(Path.cwd()) / "harness-evals"


def sealed_dir():
    """Where each run's sealed copy lives: outside the harness, so an agent working there doesn't edit it."""
    return names.evals_home()


def write_json(path, data):
    """Write through a .part file, so a reader never sees half of it."""
    part = Path(str(path) + ".part")
    part.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(str(part), str(path))


def save_run(record):
    """The sealed fields go outside the harness, and the rest in it. The key's location only goes outside."""
    folder = runs_dir() / record["id"]
    folder.mkdir(parents=True, exist_ok=True)
    sealed_dir().mkdir(parents=True, exist_ok=True)
    write_json(sealed_dir() / "{}.json".format(record["id"]), {field: record.get(field) for field in SEALED})
    write_json(folder / "run.json", {field: value for field, value in record.items() if field not in OUTSIDE_ONLY})


def load_run(run_id, sealed=True):
    """The run's record, with its sealed copy over whatever the harness folder says. RunError when either is
    missing, or a pull request isn't a number."""
    try:
        record = json.loads((runs_dir() / run_id / "run.json").read_text())
    except (OSError, ValueError):
        raise RunError("no run called {} in {}".format(run_id, runs_dir()))
    if not sealed:
        return record
    try:
        record.update(json.loads((sealed_dir() / "{}.json".format(run_id)).read_text()))
    except (OSError, ValueError):
        raise RunError("run {} has no sealed copy in {}, so it can't be carried on".format(run_id, sealed_dir()))
    record["id"] = run_id
    for issue in record["issues"]:
        if issue.get("pr") is not None and type(issue["pr"]) is not int:
            raise RunError("run {}: {!r} isn't a pull request number".format(run_id, issue["pr"]))
    return record


def issue_title_and_body(path):
    title, _, body = Path(path).read_text().partition("\n")
    return title.strip(), body.strip()


def protection_for(checks):
    """Required CI on the default branch, for admins too, with reviews left to the merge step."""
    return {"required_status_checks": {"strict": False, "contexts": checks}, "enforce_admins": True,
            "required_pull_request_reviews": None, "restrictions": None}


def create_run(suite, options):
    """Make the run's private repo from the seed, protect it, file the issues, and save the record.

    The key is never copied: only the seed goes into the clone. Once the repo exists a failure leaves it
    for a person to look at, and the error names it."""
    harness = Path(options["harness"])
    run_id = "{}-{}".format(suite["name"], datetime.now().strftime("%Y%m%d-%H%M%S"))
    name = "eval-{}".format(run_id)
    repo = "{}/{}".format(options["owner"], name)
    clone = Path(options["clone_into"]) / name
    if clone.exists():
        raise RunError("{} already exists".format(clone))
    gh_ok("couldn't create {}".format(repo), "repo", "create", repo, "--private")
    # Saved at once, so list names this repo however setup ends.
    record = {"id": run_id, "suite": suite["name"], "suite_path": str(suite["folder"]), "repo": repo,
              "repo_id": None, "clone": str(clone), "harness": str(harness), "start": options["start"],
              "merge": bool(options.get("merge")), "usage_command": options.get("usage_command"),
              "timeout_minutes": options.get("timeout_minutes", 60), "state": "setup stopped", "issues": [],
              "seen_prs": [], "stops": [], "seconds": 0, "started": datetime.now().isoformat(timespec="seconds")}
    save_run(record)
    try:
        found = json.loads(gh_ok("couldn't read {}".format(repo), "repo", "view", repo, "--json", "id,visibility"))
        if found["visibility"] != "PRIVATE":
            raise RunError("it came back {}, and a run repo has to be private".format(found["visibility"]))
        gh_ok("couldn't clone it", "repo", "clone", repo, str(clone))
        shutil.copytree(str(suite["seed"]), str(clone), symlinks=True, dirs_exist_ok=True)
        git("checkout", "-q", "-B", "main", cwd=clone)
        git("add", "-A", cwd=clone)
        git(*GIT_IDENTITY, "commit", "-q", "--allow-empty", "-m", "Seed for {}".format(suite["name"]), cwd=clone)
        git("push", "-q", "-u", "origin", "main", cwd=clone)
        code, out, err = gh("api", "--method", "PUT", "repos/{}/branches/main/protection".format(repo), "--input", "-",
                            stdin=json.dumps(protection_for(suite["required_checks"])))
        if code:
            why = said(code, out, err)
            hint = " (a private repo's protection needs a paid plan)" if "upgrade" in why.lower() else ""
            raise RunError("couldn't protect its main branch{}: {}".format(hint, why))
        record.update(repo_id=found["id"], harness_commit=git("rev-parse", "HEAD", cwd=harness),
                      harness_dirty=bool(git("status", "--porcelain", cwd=harness)),
                      base_sha=git("rev-parse", "HEAD", cwd=clone))
        for path in suite["issues"]:
            title, body = issue_title_and_body(path)
            with tempfile.NamedTemporaryFile("w", suffix=".md") as body_file:
                body_file.write(body)
                body_file.flush()
                url = gh_ok("couldn't file {}".format(Path(path).name), "issue", "create", "-R", repo,
                            "--title", title, "--body-file", body_file.name)
            record["issues"].append({"number": int(url.rstrip("/").rsplit("/", 1)[-1]), "state": "pending",
                                     "pr": None, "seconds": 0})
    except (RunError, subprocess.CalledProcessError, OSError, ValueError, KeyError) as err:
        raise RunError("{} was created, and is kept, but setup stopped: {}".format(repo, err))
    record["state"] = "working"
    save_run(record)
    return record


def add_stop(record, why, kind):
    """kind is what stopped: the run, a merge waiting for a person, or a person stepping in."""
    record["stops"].append({"why": why, "kind": kind})
    print("Stop: {}".format(why))


def fill(command, record, number):
    """The start command with this tool's own values in, quoted. Text from an issue never gets here."""
    clone, harness = Path(record["clone"]), Path(record["harness"])
    project = clone.relative_to(harness) if harness in clone.parents else clone
    values = {"{issue}": str(number), "{repo}": record["repo"], "{clone}": str(clone), "{project}": str(project)}
    for name, value in values.items():
        command = command.replace(name, shlex.quote(value))
    return command


def start_issue(record, number):
    """Run the start command on one issue. Returns why it failed, or None."""
    log_path = runs_dir() / record["id"] / "issue-{}.log".format(number)
    limit = record["timeout_minutes"] * 60
    with open(str(log_path), "w") as log:
        process = subprocess.Popen(["sh", "-c", fill(record["start"], record, number)], cwd=record["harness"],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            end_session(process)
            return "the start command timed out on issue {} after {:g} minutes".format(number, record["timeout_minutes"])
        except BaseException:
            # Ctrl-C included: the agent doesn't go on spending once the prompt is back.
            end_session(process)
            raise
    return "the start command exited {} on issue {}".format(code, number) if code else None


def end_session(process):
    """End the start command and, since it has its own session, whatever it started."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    except ProcessLookupError:
        pass


def new_pull_request(record, number):
    """(the pull request this issue produced, None) or (None, why there isn't exactly one)."""
    try:
        out = gh_ok("couldn't list pull requests", "pr", "list", "-R", record["repo"], "--state", "all",
                    "--limit", "200", "--json", "number,state")
    except RunError as err:
        return None, str(err)
    found = [pr["number"] for pr in json.loads(out) if pr["number"] not in record["seen_prs"]]
    record["seen_prs"].extend(found)
    if len(found) == 1:
        return found[0], None
    if not found:
        return None, "issue {} produced no pull request".format(number)
    # A guess could merge the wrong one.
    return None, "issue {} produced {} pull requests".format(number, len(found))


def pull_request_state(record, number):
    return json.loads(gh_ok("couldn't read pull request {}".format(number), "pr", "view", str(number), "-R",
                            record["repo"], "--json", "state"))["state"]


def merge_pull_request(record, number, required):
    """Merge once every required check has passed, only in this run's own repo. RunError otherwise.

    The repo is checked by the GitHub id the run recorded when it created it, not by name."""
    if not record.get("merge"):
        raise RunError("this run wasn't started with --merge-in-run-repo")
    code, out, err = gh("repo", "view", record["repo"], "--json", "id,visibility")
    if code or json.loads(out).get("id") != record["repo_id"]:
        raise RunError("{} isn't this run's repo, so nothing was merged".format(record["repo"]))
    deadline = time.monotonic() + record["timeout_minutes"] * 60
    while True:
        # gh pr checks exits non-zero for a pending or failed check, and still prints them.
        code, out, err = gh("pr", "checks", str(number), "-R", record["repo"], "--json", "name,bucket")
        try:
            buckets = {check["name"]: check["bucket"] for check in json.loads(out)}
        except ValueError:
            buckets = {}
        failed = [name for name in required if buckets.get(name) in ("fail", "cancel")]
        if failed:
            raise RunError("pull request {} failed {}".format(number, ", ".join(failed)))
        if all(buckets.get(name) == "pass" for name in required):
            break
        if time.monotonic() >= deadline:
            raise RunError("pull request {}'s required CI hasn't passed".format(number))
        time.sleep(CI_POLL_SECONDS)
    # GitHub sometimes fails a merge it would accept a moment later, so it gets a few tries.
    for attempt in range(MERGE_TRIES):
        code, out, err = gh("pr", "merge", str(number), "-R", record["repo"], "--merge")
        if not code:
            return
        if attempt + 1 < MERGE_TRIES:
            time.sleep(CI_POLL_SECONDS)
    raise RunError("couldn't merge pull request {} in {} tries: {}".format(number, MERGE_TRIES, said(code, out, err)))


def work(record, suite):
    """Take the issues in order. Returns "waiting" for a person, or "ended" when it's time to score."""
    for issue in record["issues"]:
        if issue["state"] == "done":
            continue
        began = time.monotonic()
        try:
            if issue["state"] == "pending":
                failed = start_issue(record, issue["number"])
                issue["pr"], why = new_pull_request(record, issue["number"])
                if issue["pr"]:
                    issue["state"] = "open"
                if failed or why:
                    # What a failed start left behind still gets scored.
                    add_stop(record, failed or why, "run")
                    return "ended"
                save_run(record)
            state = pull_request_state(record, issue["pr"])
            if state == "CLOSED":
                add_stop(record, "pull request {} was closed without merging".format(issue["pr"]), "run")
                return "ended"
            if state != "MERGED":
                if not record["merge"]:
                    return wait_for_person(record, issue)
                merge_pull_request(record, issue["pr"], suite["required_checks"])
            issue["state"] = "done"
        except RunError as err:
            add_stop(record, str(err), "run")
            return "ended"
        finally:
            record["seconds"] += time.monotonic() - began
            save_run(record)
    return "ended"


def wait_for_person(record, issue):
    """One stop for each merge, however many times the run is resumed before it happens."""
    if not issue.get("merge_stop"):
        issue["merge_stop"] = True
        add_stop(record, "pull request {} is waiting to be merged".format(issue["pr"]), "merge")
    print("Waiting for pull request {} in {}. Merge it, then: eval_harness.py resume {}".format(
        issue["pr"], record["repo"], record["id"]))
    return "waiting"


def check_out_for_scoring(record, clone):
    """Put the fresh clone on what the run produced. Returns what was scored."""
    open_prs = [issue["pr"] for issue in record["issues"] if issue["pr"] and issue["state"] != "done"]
    if not open_prs:
        return "the default branch"
    number = open_prs[-1]
    head = json.loads(gh_ok("couldn't read pull request {}".format(number), "pr", "view", str(number), "-R",
                            record["repo"], "--json", "state,headRefName"))["headRefName"]
    git("checkout", "-q", "origin/{}".format(head), cwd=clone)
    return "pull request {}".format(number)


def key_leaks(key, clone):
    """The names of the key's hidden files whose exact contents are anywhere in the clone's history.

    The reference and the wrong answers are left out: a good harness can write the same small fix."""
    history = {line.split()[0] for line in git("rev-list", "--objects", "--all", cwd=clone).splitlines()}
    answers = [Path(key) / "reference", Path(key) / "wrong"]
    hidden = [path for path in key_files(key) if not any(is_under(path, folder) for folder in answers)]
    return sorted({path.name for path in hidden if git("hash-object", str(path), cwd=clone) in history})


def number_from(text):
    try:
        return float(text.strip())
    except ValueError:
        return None


def loop_usage(record):
    """{issue number: the loop's usage entries for it} when --start runs this kind of harness's loop, else None."""
    harness = Path(record["harness"])
    if "scripts/loop.py" not in record["start"] or not (harness / "scripts" / "loop.py").exists():
        return None
    return {issue["number"]: loop.issue_usage(harness, Path(record["clone"]).name, issue["number"])
            for issue in record["issues"]}


def read_usage(record):
    """(cost, tokens, rounds), each "not reported" when nobody reported it, never zero.

    Cost comes from --usage-command when there is one, else from the loop. Tokens and rounds come from
    the loop either way: rounds is {issue number: its highest build round}."""
    cost = tokens = rounds = None
    by_issue = loop_usage(record)
    if by_issue is not None:
        tokens, cost = loop.usage_totals([entry for entries in by_issue.values() for entry in entries])
        builds = {str(number): max((e.get("round") or 0 for e in entries if e.get("step") == "build"), default=0)
                  for number, entries in by_issue.items()}
        rounds = {number: count for number, count in builds.items() if count} or None
    command = record.get("usage_command")
    if command:
        cost = None
        try:
            done = subprocess.run(["sh", "-c", fill(command, record, "")], cwd=record["harness"], text=True,
                                  capture_output=True, stdin=subprocess.DEVNULL, timeout=USAGE_TIMEOUT)
            cost = number_from(done.stdout) if not done.returncode else None
        except (OSError, subprocess.TimeoutExpired):
            pass
    return tuple("not reported" if value is None else value for value in (cost, tokens, rounds))


def score_run(record):
    """Score a fresh clone outside the harness. Returns the fields the result takes from it."""
    suite_key = Path(record["suite_path"]) / json.loads(
        (Path(record["suite_path"]) / "suite.json").read_text())["key"]
    fields = {"tests": [], "traps": [], "key_leaks": []}
    try:
        pulls = [json.loads(gh_ok("couldn't read pull request {}".format(issue["pr"]), "pr", "view", str(issue["pr"]),
                                  "-R", record["repo"], "--json", PULL_FIELDS))
                 for issue in record["issues"] if issue["pr"]]
        with tempfile.TemporaryDirectory() as workspace:
            clone = Path(workspace) / "scored"
            gh_ok("couldn't clone {}".format(record["repo"]), "repo", "clone", record["repo"], str(clone))
            fields["scored_at"] = check_out_for_scoring(record, clone)
            fields["key_leaks"] = key_leaks(suite_key, clone)
            fields.update(score_checkout(suite_key, clone, record["base_sha"], pulls, record["repo"]))
    except (RunError, subprocess.CalledProcessError, OSError, ValueError, KeyError) as err:
        fields["not_scored"] = str(err)
    return fields


def print_scorecard(result):
    print("\nSuite     {}".format(result["suite"]))
    print("Harness   {}{}".format(result["harness_commit"][:12], " (with uncommitted changes)" if result.get("harness_dirty") else ""))
    if result.get("not_scored"):
        print("Not scored: {}".format(result["not_scored"]))
    else:
        print("Tests     {}".format(tally(result["tests"], "passed")))
        print("Traps     {}".format(tally(result["traps"], "avoided")))
        for test in result["tests"]:
            if not test["passed"]:
                print("  failed: {}".format(test["name"]))
        for trap in result["traps"]:
            if not trap["avoided"]:
                print("  fell in: {}".format(trap["name"]))
    if result["key_leaks"]:
        print("Key leak  {}".format(", ".join(result["key_leaks"])))
    print("Time      {}".format(minutes(result["seconds"])))
    print("Stops     {}".format(count_stops(result)))
    print("Rounds    {}".format(round_count(result.get("rounds"))))
    print("Tokens    {}".format(token_count(result.get("tokens"))))
    print("Cost      {}".format(money(result["cost"])))


def tally(items, field):
    return "{}/{}".format(sum(1 for item in items if item[field]), len(items))


def minutes(seconds):
    return "{:.1f} min".format(seconds / 60)


def money(cost):
    return cost if isinstance(cost, str) else "${:.2f}".format(cost)


def round_count(rounds):
    """The build rounds across every issue, with each issue's when there's more than one."""
    if not isinstance(rounds, dict):
        return "not reported"
    total = sum(rounds.values())
    if len(rounds) < 2:
        return str(total)
    return "{} ({})".format(total, ", ".join("issue {}: {}".format(n, c) for n, c in sorted(rounds.items(), key=lambda i: int(i[0]))))


def round_total(rounds):
    return str(sum(rounds.values())) if isinstance(rounds, dict) else "not reported"


def token_count(tokens):
    return "{:,}".format(tokens) if isinstance(tokens, (int, float)) else "not reported"


def count_stops(result):
    merges = sum(1 for stop in result["stops"] if stop.get("kind") == "merge")
    total = len(result["stops"])
    return "{} ({} at merges)".format(total, merges) if merges else str(total)


def finish(record):
    """Score the run, write its one result file, and print the scorecard. Returns the exit code."""
    result = {"run": record["id"], "suite": record["suite"], "repo": record["repo"],
              "harness_commit": record["harness_commit"], "harness_dirty": record["harness_dirty"],
              "seconds": record["seconds"], "stops": record["stops"]}
    result.update(score_run(record))
    result["cost"], result["tokens"], result["rounds"] = read_usage(record)
    record["state"] = "ended"
    save_run(record)
    write_json(runs_dir() / record["id"] / "result.json", result)
    print_scorecard(result)
    return 0 if all_clean(result) and not result["key_leaks"] else 1


def drive(record, suite):
    """Work the issues, then score, unless a person is needed first. Returns the exit code."""
    record["state"] = "working"
    if work(record, suite) == "waiting":
        record["state"] = "waiting"
        save_run(record)
        return WAITING
    return finish(record)


def interactive():
    return sys.stdin.isatty()


def confirmed(args, suite):
    """REQ-012: nothing is created until the person has agreed to spend the tokens."""
    if args.yes:
        return True
    if not interactive():
        print("A run spends model tokens. Pass --yes to start one with no terminal.", file=sys.stderr)
        return False
    question = "Run {} through this harness? It creates a private repo in {} and spends model tokens. Type yes: "
    try:
        return input(question.format(suite["name"], args.owner)).strip().lower() == "yes"
    except EOFError:
        return False


def cmd_run(args):
    harness = Path(args.harness).resolve()
    clone_into = Path(args.clone_into).resolve() if args.clone_into else harness / "projects"
    try:
        suite = load_suite(args.suite, harness, clone_into=clone_into)
    except SuiteError as err:
        print("Refused: {}".format(err), file=sys.stderr)
        return 2
    if not clone_into.is_dir():
        print("Refused: {} isn't a folder. Pass --clone-into.".format(clone_into), file=sys.stderr)
        return 2
    if subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(harness), capture_output=True).returncode:
        print("Refused: {} has no git commit to record the run against.".format(harness), file=sys.stderr)
        return 2
    if not confirmed(args, suite):
        print("Nothing was created.", file=sys.stderr)
        return 2
    try:
        record = create_run(suite, {"owner": args.owner, "harness": harness, "start": args.start,
                                    "clone_into": clone_into, "merge": args.merge_in_run_repo,
                                    "timeout_minutes": args.timeout, "usage_command": args.usage_command})
    except RunError as err:
        print(err, file=sys.stderr)
        return 2
    print("Created {} for run {}.".format(record["repo"], record["id"]))
    return drive(record, suite)


def cmd_resume(args):
    try:
        record = load_run(args.run)
        if args.end and record["state"] in ("waiting", "working"):
            # working here means it was interrupted: what it got to still gets scored.
            return finish(record)
        if record["state"] == "working":
            raise RunError("run {} was interrupted. Score what it got to with: eval_harness.py resume {} --end"
                           .format(args.run, args.run))
        if record["state"] != "waiting":
            raise RunError("run {} isn't waiting: it's {}".format(args.run, record["state"]))
        suite = load_suite(record["suite_path"], record["harness"], clone_into=Path(record["clone"]).parent)
    except (RunError, SuiteError) as err:
        print(err, file=sys.stderr)
        return 2
    return drive(record, suite)


def cmd_stop(args):
    try:
        # Only stops change, so the harness's copy is enough, and it's all an older run has.
        record = load_run(args.run, sealed=False)
    except RunError as err:
        print(err, file=sys.stderr)
        return 2
    add_stop(record, args.why, "person")
    write_json(runs_dir() / args.run / "run.json", record)
    result_path = runs_dir() / args.run / "result.json"
    if result_path.exists():
        result = json.loads(result_path.read_text())
        result["stops"] = record["stops"]
        write_json(result_path, result)
    return 0


def load_result(name):
    """A run's name or a result file's path. RunError when there's neither."""
    path = Path(name) if Path(name).is_file() else runs_dir() / name / "result.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        raise RunError("no result for {}".format(name))


def changes(kind, field, before, after):
    """A line for each of kind's items that got worse, got better, was added or disappeared."""
    was = {item["name"]: item[field] for item in before}
    now = {item["name"]: item[field] for item in after}
    lines = []
    for name in sorted(set(was) | set(now)):
        if name not in now:
            lines.append("Gone: {} {}".format(kind, name))
        elif name not in was:
            lines.append("New: {} {}".format(kind, name))
        elif was[name] and not now[name]:
            lines.append("Worse: {} {}".format(kind, name))
        elif now[name] and not was[name]:
            lines.append("Better: {} {}".format(kind, name))
    return lines


def cmd_compare(args):
    try:
        a, b = load_result(args.a), load_result(args.b)
    except RunError as err:
        print(err, file=sys.stderr)
        return 2
    rows = [("", a["run"], b["run"]),
            ("Harness", a["harness_commit"][:12], b["harness_commit"][:12]),
            ("Tests", tally(a["tests"], "passed"), tally(b["tests"], "passed")),
            ("Traps", tally(a["traps"], "avoided"), tally(b["traps"], "avoided")),
            ("Key leaks", len(a["key_leaks"]), len(b["key_leaks"])),
            ("Time", minutes(a["seconds"]), minutes(b["seconds"])),
            ("Stops", count_stops(a), count_stops(b)),
            ("Rounds", round_total(a.get("rounds")), round_total(b.get("rounds"))),
            ("Tokens", token_count(a.get("tokens")), token_count(b.get("tokens"))),
            ("Cost", money(a["cost"]), money(b["cost"]))]
    widths = [max(len(str(row[column])) for row in rows) for column in range(3)]
    for row in rows:
        print("  ".join(str(cell).ljust(width) for cell, width in zip(row, widths)).rstrip())
    for result in (a, b):
        if result.get("not_scored"):
            print("{} wasn't scored: {}".format(result["run"], result["not_scored"]))
    lines = changes("test", "passed", a["tests"], b["tests"]) + changes("trap", "avoided", a["traps"], b["traps"])
    print("\n" + ("\n".join(lines) if lines else "Nothing changed in tests or traps."))
    return 0


def cmd_list(args):
    folders = sorted(runs_dir().glob("*/run.json")) if runs_dir().is_dir() else []
    if not folders:
        print("No runs in {}.".format(runs_dir()))
    for path in folders:
        record = json.loads(path.read_text())
        print("{}  {}  {}".format(record["id"], record["repo"], record["state"]))
    return 0


def cmd_validate(args):
    try:
        suite = load_suite(args.suite, Path.cwd())
    except SuiteError as err:
        print("Refused: {}".format(err), file=sys.stderr)
        return 2
    problems = validate_suite(suite)
    for problem in problems:
        print(problem)
    if not problems:
        print("{}: the seed fails, each wrong answer fails, the reference passes.".format(suite["name"]))
    return 1 if problems else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run a harness through a suite of jobs and score the result.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run a harness through a suite: creates a repo and spends model tokens")
    run.add_argument("suite")
    run.add_argument("--start", required=True, help="what starts the harness on one issue")
    run.add_argument("--owner", required=True, help="the GitHub user or organisation to create the run repo in")
    run.add_argument("--harness", default=".", help="the harness's folder, where --start runs")
    run.add_argument("--clone-into", help="where to clone the run repo: the harness's projects/ by default")
    run.add_argument("--merge-in-run-repo", action="store_true",
                     help="merge each passing pull request, only in the repo this run created")
    run.add_argument("--usage-command", help="prints the run's total cost, for a harness that isn't this one")
    run.add_argument("--timeout", type=float, default=60, metavar="MINUTES",
                     help="for each issue's start command, and for its CI: 60 by default")
    run.add_argument("--yes", action="store_true", help="don't ask before spending model tokens")
    run.set_defaults(handler=cmd_run)
    resume = sub.add_parser("resume", help="carry on a run that stopped for a merge")
    resume.add_argument("run")
    resume.add_argument("--end", action="store_true", help="stop waiting, and score what exists")
    resume.set_defaults(handler=cmd_resume)
    stop = sub.add_parser("stop", help="record that a person had to step in")
    stop.add_argument("run")
    stop.add_argument("why")
    stop.set_defaults(handler=cmd_stop)
    compare = sub.add_parser("compare", help="two results side by side, naming each test or trap that changed")
    compare.add_argument("a")
    compare.add_argument("b")
    compare.set_defaults(handler=cmd_compare)
    listing = sub.add_parser("list", help="the runs here and their repos, which only a person deletes")
    listing.set_defaults(handler=cmd_list)
    validate = sub.add_parser("validate", help="check a suite is a fair test, with no repo and no tokens")
    validate.add_argument("suite")
    validate.set_defaults(handler=cmd_validate)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
