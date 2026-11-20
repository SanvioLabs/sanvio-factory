"""scripts/run_tests.py runs the tests as unittest does and keeps a status file for the run.

Every test here runs the script on a small suite in a temporary folder that is its own
git repo, never on this repo's suite, and checks that nothing it ran left a status file in
this clone's `.sanvio/tests/`.
"""
import datetime
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
SCRIPT = SCRIPTS / "run_tests.py"

PASSING = """import unittest

class T(unittest.TestCase):
    def test_a(self):
        pass

    def test_b(self):
        pass
"""

FAILING = """import unittest

class T(unittest.TestCase):
    def test_a(self):
        pass

    def test_b(self):
        self.fail("no")

    def test_c(self):
        raise RuntimeError("broken")

    @unittest.skip("not today")
    def test_d(self):
        pass
"""

# test_a finishes at once; test_b waits for the file named in WAIT_FOR, or for `seconds`.
SLOW = """import os, time, unittest

class T(unittest.TestCase):
    def test_a(self):
        pass

    def test_b(self):
        end = time.time() + {seconds}
        while time.time() < end and not os.path.exists(os.environ.get("WAIT_FOR", "")):
            time.sleep(0.05)
"""


def git_env(ceiling):
    """An environment with no git settings from outside: no GIT_* variable, no user config."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_CEILING_DIRECTORIES=ceiling,
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return env


def clone_status_folder():
    out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    return Path(out.stdout.strip()).parent / ".sanvio" / "tests"


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.env = git_env(str(self.tmp))
        self.addCleanup(self.left_nothing_in_this_clone)

    def left_nothing_in_this_clone(self):
        folder = clone_status_folder()
        for path in folder.glob("*.json") if folder.is_dir() else []:
            try:
                worktree = json.loads(path.read_text()).get("worktree", "")
            except (OSError, ValueError):
                continue
            self.assertFalse(str(worktree).startswith(str(self.tmp)),
                             f"{path} came from this test's run")

    def git(self, cwd, *args):
        subprocess.run(["git", *args], cwd=cwd, env=self.env, check=True, capture_output=True)

    def repo(self, name="repo", files=None):
        path = self.tmp / name
        (path / "tests").mkdir(parents=True)
        for file, text in (files or {"test_x.py": PASSING}).items():
            (path / "tests" / file).write_text(text)
        self.git(path, "init", "-q", "-b", "trunk")
        return path

    def run_script(self, cwd, *args, heartbeat=None, env=None):
        return subprocess.run(self.command(*args, heartbeat=heartbeat), cwd=cwd, env=env or self.env,
                              capture_output=True, text=True, timeout=60)

    def command(self, *args, heartbeat=None):
        if heartbeat is None:
            return [sys.executable, str(SCRIPT), *args]
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import run_tests; "
                f"run_tests.HEARTBEAT = {heartbeat}; run_tests.main(sys.argv[2:])")
        return [sys.executable, "-c", code, str(SCRIPTS), *args]

    def statuses(self, repo):
        folder = repo / ".sanvio" / "tests"
        return [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))]

    def only_status(self, repo):
        found = self.statuses(repo)
        self.assertEqual(len(found), 1, found)
        return found[0]

    # The run itself

    def test_with_no_arguments_it_runs_what_unittest_discover_runs(self):
        repo = self.repo(files={"test_x.py": PASSING, "test_y.py": FAILING})
        ours = self.run_script(repo)
        theirs = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                                cwd=repo, env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(ours.returncode, theirs.returncode)
        self.assertNotEqual(ours.returncode, 0)
        self.assertIn("Ran 6 tests", ours.stderr)
        self.assertIn("FAILED (failures=1, errors=1, skipped=1)", ours.stderr)
        self.assertIn("RuntimeError: broken", ours.stderr)

    def test_a_passing_run_exits_0_and_records_passed(self):
        repo = self.repo()
        out = self.run_script(repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        status = self.only_status(repo)
        self.assertEqual(status["state"], "passed")
        self.assertEqual(status["exit_code"], 0)
        self.assertEqual((status["total"], status["ran"], status["failed"], status["skipped"]), (2, 2, 0, 0))
        self.assertEqual(status["worktree"], str(repo))
        self.assertEqual(status["branch"], "trunk")
        self.assertIsInstance(status["pid"], int)
        for field in ("started", "updated", "ended"):
            self.assertIsNotNone(datetime.datetime.fromisoformat(status[field]).tzinfo, field)

    def test_a_failing_run_records_failures_and_errors_together(self):
        repo = self.repo(files={"test_y.py": FAILING})
        out = self.run_script(repo)
        self.assertEqual(out.returncode, 1)
        status = self.only_status(repo)
        self.assertEqual(status["state"], "failed")
        self.assertEqual(status["exit_code"], 1)
        self.assertEqual((status["total"], status["ran"], status["failed"], status["skipped"]), (4, 4, 2, 1))

    def test_names_run_only_what_they_name(self):
        repo = self.repo(files={"test_x.py": PASSING, "test_y.py": FAILING})
        out = self.run_script(repo, "tests.test_x")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Ran 2 tests", out.stderr)
        self.assertEqual(self.only_status(repo)["total"], 2)

    def test_flags_alone_still_run_the_whole_suite(self):
        repo = self.repo(files={"test_x.py": PASSING, "test_y.py": FAILING})
        out = self.run_script(repo, "-v")
        self.assertIn("Ran 6 tests", out.stderr)
        self.assertIn("test_a (", out.stderr)

    def test_a_detached_head_records_an_empty_branch(self):
        repo = self.repo()
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", "one")
        self.git(repo, "checkout", "-q", "--detach")
        self.run_script(repo)
        self.assertEqual(self.only_status(repo)["branch"], "")

    def test_a_run_started_in_a_subfolder_names_the_worktree_root(self):
        repo = self.repo()
        self.run_script(repo / "tests", "test_x")
        self.assertEqual(self.only_status(repo)["worktree"], str(repo))

    # Where the file goes

    def linked(self):
        repo = self.repo()
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", "one")
        wt = self.tmp / "wt"
        self.git(repo, "worktree", "add", "-q", "-b", "side", str(wt))
        return repo, wt

    def test_a_run_in_a_linked_worktree_lands_in_the_main_clone(self):
        repo, wt = self.linked()
        out = self.run_script(wt)
        self.assertEqual(out.returncode, 0, out.stderr)
        status = self.only_status(repo)
        self.assertEqual(status["worktree"], str(wt))
        self.assertEqual(status["branch"], "side")
        self.assertFalse((wt / ".sanvio").exists())

    def test_two_runs_at_once_in_two_worktrees_write_two_files(self):
        repo, wt = self.linked()
        procs = [subprocess.Popen(self.command(), cwd=where, env=self.env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                 for where in (repo, wt)]
        for p in procs:
            self.assertEqual(p.wait(timeout=60), 0)
        found = self.statuses(repo)
        self.assertEqual(sorted(s["worktree"] for s in found), sorted([str(repo), str(wt)]))
        self.assertTrue(all(s["state"] == "passed" for s in found))

    # While it runs

    def test_it_writes_while_one_test_runs_long_and_never_half_a_file(self):
        repo = self.repo(files={"test_x.py": SLOW.format(seconds=2)})
        proc = subprocess.Popen(self.command(heartbeat=0.1), cwd=repo, env=self.env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(proc.kill)
        folder = repo / ".sanvio" / "tests"
        beats = set()
        while proc.poll() is None:
            for path in folder.glob("*.json"):
                try:
                    text = path.read_text()
                except FileNotFoundError:
                    continue
                status = json.loads(text)  # a half-written file fails here
                if status["state"] == "running" and status["ran"] == 1:
                    beats.add(status["updated"])
            time.sleep(0.02)
        self.assertEqual(proc.returncode, 0)
        self.assertGreaterEqual(len(beats), 3, "updated didn't move while test_b ran")
        self.assertEqual([p.name for p in folder.iterdir() if not p.name.endswith(".json")], [])

    @unittest.skipIf(sys.platform == "win32", "Ctrl-C is a POSIX signal here")
    def test_ctrl_c_records_failed_with_exit_code_130(self):
        repo = self.repo(files={"test_x.py": SLOW.format(seconds=30)})
        proc = subprocess.Popen(self.command(), cwd=repo, env=self.env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(proc.kill)
        deadline = time.time() + 20
        while time.time() < deadline:
            found = self.statuses(repo) if (repo / ".sanvio" / "tests").is_dir() else []
            if found and found[0]["ran"] == 1:
                break
            time.sleep(0.05)
        else:
            self.fail("test_a never finished")
        proc.send_signal(signal.SIGINT)
        self.assertEqual(proc.wait(timeout=20), 130)
        status = self.only_status(repo)
        # unittest ends the test Ctrl-C stopped before the interrupt leaves it, so it counts.
        self.assertEqual((status["state"], status["exit_code"], status["ran"]), ("failed", 130, 2))

    # When it can't keep the file

    def test_an_unwritable_folder_still_runs_the_tests_and_says_so_once(self):
        repo = self.repo(files={"test_y.py": FAILING})
        (repo / ".sanvio").write_text("a file where the folder would go")
        out = self.run_script(repo)
        self.assertEqual(out.returncode, 1)
        self.assertIn("Ran 4 tests", out.stderr)
        self.assertEqual(out.stderr.count("run_tests: can't keep a status file"), 1, out.stderr)

    def test_outside_a_git_repo_it_runs_the_tests_and_says_so(self):
        plain = self.tmp / "plain"
        (plain / "tests").mkdir(parents=True)
        (plain / "tests" / "test_x.py").write_text(PASSING)
        out = self.run_script(plain)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Ran 2 tests", out.stderr)
        self.assertIn("run_tests: can't keep a status file (this isn't a git repo)", out.stderr)
        self.assertFalse((plain / ".sanvio").exists())

    # Keeping

    def test_a_start_removes_status_files_over_30_days_old_and_nothing_else(self):
        repo = self.repo()
        folder = repo / ".sanvio" / "tests"
        folder.mkdir(parents=True)
        utc = datetime.timezone.utc
        old = (datetime.datetime.now(utc) - datetime.timedelta(days=31)).isoformat()
        recent = (datetime.datetime.now(utc) - datetime.timedelta(days=29)).isoformat()
        (folder / "old.json").write_text(json.dumps({"updated": old}))
        (folder / "recent.json").write_text(json.dumps({"updated": recent}))
        (folder / "broken.json").write_text("{not json")
        (folder / "nofield.json").write_text("{}")
        (folder / "notes.txt").write_text(old)
        self.run_script(repo)
        left = sorted(p.name for p in folder.iterdir())
        self.assertNotIn("old.json", left)
        for name in ("recent.json", "broken.json", "nofield.json", "notes.txt"):
            self.assertIn(name, left)
        self.assertEqual(len(left), 5)


if __name__ == "__main__":
    unittest.main()
