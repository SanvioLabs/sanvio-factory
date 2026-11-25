#!/usr/bin/env python3
"""Run the test suite, and keep a status file for the run that a pane can read.

    python3 scripts/run_tests.py                          # what `python3 -m unittest discover -s tests` runs
    python3 scripts/run_tests.py tests.test_link_files    # only what the names say, in unittest's own form
    python3 scripts/run_tests.py -v                       # flags alone still mean the whole suite

The output and the exit code are unittest's. While the tests run, the status is
kept in `.sanvio/tests/<run id>.json` in the main clone, the parent of the
folder `git rev-parse --git-common-dir` prints, so a run in a linked worktree
lands beside one in the clone. The file holds where the run is and how it ended:
paths, a branch name and counts, never test output. It's written whole each
time, by a rename, so a reader never sees half of one.

Each start removes status files whose `updated` is over 30 days old, unless
SANVIO_HOLD is on. If the
file can't be written, or this isn't a git repo, the tests run anyway and one
line on stderr says the run won't show.
"""
import datetime
import json
import os
import subprocess
import sys
import threading
import unittest

import names  # beside this file: the hold switch

KEEP_DAYS = 30
HEARTBEAT = 10.0  # seconds between writes while one test runs long
FOLDER = os.path.join(".sanvio", "tests")
INTERRUPTED = 130


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def git(*args):
    """What a git command prints, or None when it fails."""
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    except OSError:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def status_folder():
    """The main clone's `.sanvio/tests/`, or why there isn't one."""
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        return None, "this isn't a git repo"
    return os.path.join(os.path.dirname(common), FOLDER), None


def prune(folder, days=KEEP_DAYS):
    """Remove status files last updated over `days` ago. Anything else stays, and under SANVIO_HOLD
    everything does."""
    if names.held():
        return
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    try:
        entries = os.listdir(folder)
    except OSError:
        return
    for name in entries:
        if not name.endswith(".json"):
            continue
        path = os.path.join(folder, name)
        try:
            with open(path, encoding="utf-8") as f:
                updated = datetime.datetime.fromisoformat(json.load(f)["updated"])
            if updated.tzinfo is not None and updated < cutoff:
                os.remove(path)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue


class Status:
    """One run's status file. After a failed write it stops trying and says so once."""

    def __init__(self, folder, why=None):
        self.lock = threading.Lock()
        self.path = None
        self.data = {
            "state": "running",
            "worktree": git("rev-parse", "--show-toplevel") or os.getcwd(),
            "branch": git("symbolic-ref", "--short", "-q", "HEAD") or "",
            "pid": os.getpid(),
            "started": now(),
            "updated": None,
            "total": None,
            "ran": 0,
            "failed": 0,
            "skipped": 0,
        }
        if folder is None:
            self.warn(why)
            return
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = os.path.join(folder, f"{stamp}-{os.getpid()}.json")
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            self.warn(e.strerror or str(e))
            return
        prune(folder)
        self.write()

    def warn(self, why):
        self.path = None
        print(f"run_tests: can't keep a status file ({why}), so this run won't show in a pane",
              file=sys.stderr)

    def write(self, **fields):
        with self.lock:
            self.data.update(fields)
            if self.path is None:
                return
            self.data["updated"] = now()
            tmp = f"{self.path}.{os.getpid()}.tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=2)
                os.replace(tmp, self.path)
            except OSError as e:
                try:
                    os.remove(tmp)
                except OSError:
                    pass  # often never made; the warning below is what tells the person
                self.warn(e.strerror or str(e))

    def count(self, result):
        self.write(ran=self.data["ran"] + 1,
                   failed=len(result.failures) + len(result.errors),
                   skipped=len(result.skipped))

    def end(self, code):
        self.write(state="passed" if code == 0 else "failed", ended=now(), exit_code=code)


class Result(unittest.TextTestResult):
    status = None

    def stopTest(self, test):
        super().stopTest(test)
        self.status.count(self)


class Runner(unittest.TextTestRunner):
    resultclass = Result
    status = None

    def run(self, test):
        self.status.write(total=test.countTestCases())
        stop = threading.Event()

        def beat():
            while not stop.wait(HEARTBEAT):
                self.status.write()

        thread = threading.Thread(target=beat, daemon=True)
        thread.start()
        try:
            return super().run(test)
        finally:
            stop.set()


def unittest_argv(args):
    """The arguments `python3 -m unittest` would get for these."""
    if all(a.startswith("-") for a in args):
        return ["discover", "-s", "tests", *args]
    return list(args)


def main(args=None):
    args = sys.argv[1:] if args is None else args
    # `python3 -m unittest` puts the current folder first on the path, not the script's.
    here = os.path.dirname(os.path.abspath(__file__))
    if sys.path and os.path.abspath(sys.path[0] or ".") == here:
        sys.path[0] = ""
    status = Status(*status_folder())
    Result.status = Runner.status = status
    try:
        unittest.main(module=None, argv=["python3 -m unittest", *unittest_argv(args)],
                      testRunner=Runner)
    except SystemExit as e:
        # unittest exits with a bool (`not wasSuccessful()`), or 5 when it ran no tests.
        code = int(e.code) if isinstance(e.code, int) else (0 if e.code is None else 1)
        status.end(code)
        raise
    except KeyboardInterrupt:
        status.end(INTERRUPTED)
        sys.exit(INTERRUPTED)


if __name__ == "__main__":
    main()
