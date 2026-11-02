"""Run with: python3 -m unittest discover -s tests -p 'test_eval_harness.py'

No real model or network: gh is a small fake on PATH and the harness is a stub command."""
import ast
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import eval_harness  # noqa: E402


def write_suite(folder, **overrides):
    """A small valid suite in folder, with suite.json's fields overridden. Returns its path."""
    folder = Path(folder)
    (folder / "seed").mkdir(parents=True)
    (folder / "seed" / "app.txt").write_text("seed\n")
    (folder / "issues").mkdir()
    (folder / "issues" / "01-first.md").write_text("Fix the app\n\nIt is wrong.\n")
    (folder / "key").mkdir()
    (folder / "key" / "score").write_text("#!/bin/sh\necho '{\"tests\": [], \"traps\": []}'\n")
    os.chmod(str(folder / "key" / "score"), 0o755)
    config = {"name": "tiny", "seed": "seed", "key": "key", "issues": ["issues/01-first.md"],
              "required_checks": ["checks"]}
    config.update(overrides)
    (folder / "suite.json").write_text(json.dumps(config))
    return folder


class LoadSuite(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(os.path.realpath(tmp.name))
        self.suite = self.tmp / "suite"
        self.harness = self.tmp / "harness"
        self.harness.mkdir()

    def load(self):
        return eval_harness.load_suite(self.suite, self.harness)

    def assert_refused(self, words):
        with self.assertRaises(eval_harness.SuiteError) as caught:
            self.load()
        self.assertIn(words, str(caught.exception))

    def test_a_suite_outside_the_harness_loads(self):
        write_suite(self.suite)
        suite = self.load()
        self.assertEqual(suite["name"], "tiny")
        self.assertEqual(suite["seed"], self.suite / "seed")
        self.assertEqual(suite["key"], self.suite / "key")
        self.assertEqual(suite["issues"], [self.suite / "issues" / "01-first.md"])

    def test_a_missing_suite_json_is_refused(self):
        self.suite.mkdir()
        self.assert_refused("suite.json")

    def test_a_missing_field_is_refused_by_name(self):
        write_suite(self.suite)
        config = json.loads((self.suite / "suite.json").read_text())
        del config["required_checks"]
        (self.suite / "suite.json").write_text(json.dumps(config))
        self.assert_refused("required_checks")

    def test_a_missing_issue_file_is_refused(self):
        write_suite(self.suite, issues=["issues/nope.md"])
        self.assert_refused("nope.md")

    def test_a_key_with_no_score_program_is_refused(self):
        write_suite(self.suite)
        (self.suite / "key" / "score").unlink()
        self.assert_refused("key/score")

    def test_hidden_tests_under_the_seed_are_refused(self):
        write_suite(self.suite, key="seed/key")
        (self.suite / "seed" / "key").mkdir()
        (self.suite / "seed" / "key" / "score").write_text("x")
        self.assert_refused("under the seed")

    def test_a_seed_under_the_key_is_refused(self):
        write_suite(self.suite, seed="key/seed")
        (self.suite / "key" / "seed").mkdir()
        self.assert_refused("under the seed")

    def test_a_symlink_in_the_seed_reaching_the_key_is_refused(self):
        write_suite(self.suite)
        (self.suite / "seed" / "link").symlink_to(self.suite / "key")
        self.assert_refused("link")

    def test_a_copy_of_a_key_file_in_the_seed_is_refused(self):
        write_suite(self.suite)
        (self.suite / "key" / "hidden.txt").write_text("the answer\n")
        (self.suite / "seed" / "stray.txt").write_text("the answer\n")
        self.assert_refused("stray.txt")

    def test_an_empty_file_in_both_seed_and_key_is_no_leak(self):
        write_suite(self.suite)
        (self.suite / "key" / "__init__.py").write_text("")
        (self.suite / "seed" / "__init__.py").write_text("")
        self.assertEqual(self.load()["name"], "tiny")

    def test_a_name_that_wouldnt_make_a_repo_name_is_refused(self):
        write_suite(self.suite, name="tiny; rm -rf")
        self.assert_refused("name")

    def test_no_required_checks_is_refused(self):
        write_suite(self.suite, required_checks=[])
        self.assert_refused("required_checks")

    def test_a_key_inside_the_harness_is_refused(self):
        self.suite = self.harness / "suite"
        write_suite(self.suite)
        self.assert_refused("inside the harness")

    def test_a_key_inside_the_clone_folder_is_refused(self):
        write_suite(self.suite)
        with self.assertRaises(eval_harness.SuiteError) as caught:
            eval_harness.load_suite(self.suite, self.harness, clone_into=self.tmp)
        self.assertIn("clone folder", str(caught.exception))

    def test_the_public_example_may_sit_inside_the_harness(self):
        self.suite = self.harness / "suite"
        write_suite(self.suite, public_example=True)
        self.assertTrue(self.load()["public_example"])


# A score program that passes when the checkout's answer.txt says right and nothing else was touched.
SCORE = """#!/usr/bin/env python3
import json, os, subprocess
run = os.environ["RUN_DIR"]
right = open(os.path.join(run, "answer.txt")).read().strip() == "right"
changed = subprocess.run(["git", "diff", "--name-only", os.environ["BASE_SHA"], "HEAD"], cwd=run,
                         capture_output=True, text=True, check=True).stdout.split()
print(json.dumps({"tests": [{"name": "answer is right", "passed": right}],
                  "traps": [{"name": "decoy untouched", "avoided": "decoy.txt" not in changed}]}))
"""


class Validate(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(os.path.realpath(tmp.name))
        self.suite = write_suite(self.tmp / "suite")
        (self.suite / "seed" / "answer.txt").write_text("seed\n")
        (self.suite / "seed" / "decoy.txt").write_text("decoy\n")
        (self.suite / "key" / "score").write_text(SCORE)
        self.overlay("reference", {"answer.txt": "right\n"})
        self.overlay("wrong/touches-decoy", {"answer.txt": "right\n", "decoy.txt": "changed\n"})

    def overlay(self, where, files):
        folder = self.suite / "key" / where
        folder.mkdir(parents=True)
        for name, text in files.items():
            (folder / name).write_text(text)

    def validate(self):
        suite = eval_harness.load_suite(self.suite, self.tmp / "harness")
        return eval_harness.validate_suite(suite)

    def test_a_sound_suite_passes(self):
        self.assertEqual(self.validate(), [])

    def test_a_second_suite_needs_no_runner_change(self):
        (self.suite / "suite.json").write_text(json.dumps(
            dict(json.loads((self.suite / "suite.json").read_text()), name="another")))
        self.assertEqual(self.validate(), [])

    def test_a_seed_that_already_passes_is_a_problem(self):
        (self.suite / "seed" / "answer.txt").write_text("right  \n")
        self.assertIn("the seed", " ".join(self.validate()))

    def test_a_wrong_answer_that_passes_is_named(self):
        self.overlay("wrong/looks-fine", {"answer.txt": "right\n"})
        self.assertIn("looks-fine", " ".join(self.validate()))

    def test_a_reference_that_fails_is_a_problem(self):
        (self.suite / "key" / "reference" / "answer.txt").write_text("nope\n")
        self.assertIn("the reference", " ".join(self.validate()))

    def test_a_suite_with_no_reference_is_a_problem(self):
        (self.suite / "key" / "reference" / "answer.txt").unlink()
        (self.suite / "key" / "reference").rmdir()
        self.assertIn("no key/reference", " ".join(self.validate()))

    def test_a_suite_with_no_wrong_answer_is_a_problem(self):
        (self.suite / "key" / "wrong" / "touches-decoy" / "answer.txt").unlink()
        (self.suite / "key" / "wrong" / "touches-decoy" / "decoy.txt").unlink()
        (self.suite / "key" / "wrong" / "touches-decoy").rmdir()
        self.assertIn("no key/wrong", " ".join(self.validate()))

    def test_score_output_that_isnt_json_is_not_scored(self):
        (self.suite / "key" / "score").write_text("#!/bin/sh\necho hello\n")
        problems = self.validate()
        self.assertIn("not scored", " ".join(problems))

    def test_the_public_example_is_sound(self):
        suite = eval_harness.load_suite(ROOT / "examples" / "eval-suite", ROOT)
        self.assertTrue(suite["public_example"])
        self.assertEqual(eval_harness.validate_suite(suite), [])

    def test_validate_from_the_command_line(self):
        code = eval_harness.main(["validate", str(ROOT / "examples" / "eval-suite")])
        self.assertEqual(code, 0)


# gh, kept in a folder: a repo is a bare git repo, and everything else is state.json. It logs every call.
FAKE_GH = r"""#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
home = Path(os.environ["FAKE_GH_HOME"])
args = sys.argv[1:]
with open(home / "calls.log", "a") as log:
    log.write(" ".join(args) + "\n")
state_path = home / "state.json"
state = json.loads(state_path.read_text()) if state_path.exists() else {}
repos = state.setdefault("repos", {})
def save():
    state_path.write_text(json.dumps(state))
def value(flag):
    return args[args.index(flag) + 1]
def bare(name):
    return str(home / "remotes" / (name.replace("/", "__") + ".git"))
if args[:2] == ["repo", "create"]:
    name = args[2]
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare(name)], check=True)
    repos[name] = {"id": "R_" + name, "visibility": state.get("force_visibility", "PRIVATE"),
                   "issues": [], "prs": [], "private_flag": "--private" in args}
elif args[:2] == ["repo", "view"]:
    print(json.dumps({k: repos[args[2]][k] for k in ("id", "visibility")}))
elif args[:2] == ["repo", "clone"]:
    subprocess.run(["git", "clone", "-q", bare(args[2]), args[3]], check=True, capture_output=True)
elif args[0] == "api":
    if state.get("protect_fails"):
        print(json.dumps({"message": state.get("protect_message", "Upgrade to GitHub Pro")}))
        sys.exit(1)
    name = args[args.index("--method") + 2].split("/branches/")[0][len("repos/"):]
    repos[name]["protection"] = json.loads(sys.stdin.read())
elif args[:2] == ["issue", "create"]:
    issues = repos[value("-R")]["issues"]
    issues.append({"title": value("--title"), "body": Path(value("--body-file")).read_text()})
    print("https://github.example/{}/issues/{}".format(value("-R"), len(issues)))
elif args[:2] == ["pr", "create"]:
    prs = repos[value("-R")]["prs"]
    prs.append({"number": len(prs) + 1, "state": "OPEN", "head": value("--head")})
elif args[:2] == ["pr", "list"]:
    print(json.dumps([{"number": p["number"], "state": p["state"]} for p in repos[value("-R")]["prs"]]))
elif args[:2] == ["pr", "view"]:
    pr = repos[value("-R")]["prs"][int(args[2]) - 1]
    print(json.dumps({"state": pr["state"], "headRefName": pr["head"]}))
elif args[:2] == ["pr", "checks"]:
    checks = state.get("checks", [{"name": "checks", "bucket": "pass"}])
    print(json.dumps(checks))
    sys.exit(8 if any(c["bucket"] == "pending" for c in checks) else 0)
elif args[:2] == ["pr", "merge"]:
    if state.get("merge_fails", 0) > 0:
        state["merge_fails"] -= 1
        save()
        sys.exit("GraphQL: Something went wrong while executing your query")
    pr = repos[value("-R")]["prs"][int(args[2]) - 1]
    subprocess.run(["git", "--git-dir", bare(value("-R")), "update-ref", "refs/heads/main", "refs/heads/" + pr["head"]], check=True)
    pr["state"] = "MERGED"
else:
    sys.exit("fake gh doesn't know: " + " ".join(args))
save()
"""

# A harness: for each issue it reads what to do from STUB_PLAN, then branches, commits, pushes and opens PRs.
STUB_HARNESS = r"""#!/usr/bin/env python3
import json, os, subprocess, sys, time
issue, clone, repo = sys.argv[1:4]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps({"issue": issue, "clone": clone, "repo": repo, "cwd": os.getcwd()}) + "\n")
plan = json.loads(open(os.environ["STUB_PLAN"]).read()).get(issue, {})
time.sleep(plan.get("sleep", 0))
def git(*args):
    subprocess.run(["git", "-c", "user.name=stub", "-c", "user.email=stub@example.invalid"] + list(args),
                   cwd=clone, check=True, capture_output=True)
for n in range(plan.get("prs", 1)):
    branch = "issue-{}-{}".format(issue, n)
    git("fetch", "-q", "origin")
    git("checkout", "-q", "-B", branch, "origin/main")
    for name, text in plan.get("files", {"work-{}.txt".format(issue): "done"}).items():
        with open(os.path.join(clone, name), "w") as out:
            out.write(text)
    git("add", "-A")
    git("commit", "-q", "--allow-empty", "-m", "Work on " + issue)
    git("push", "-q", "origin", branch)
    subprocess.run(["gh", "pr", "create", "-R", repo, "--head", branch], check=True)
sys.exit(plan.get("exit", 0))
"""


class WithFakeGh(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(os.path.realpath(tmp.name))
        self.gh_home = self.tmp / "gh"
        (self.gh_home / "remotes").mkdir(parents=True)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "gh").write_text(FAKE_GH)
        os.chmod(str(bin_dir / "gh"), 0o755)
        env = {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "FAKE_GH_HOME": str(self.gh_home)}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.harness = self.tmp / "harness"
        (self.harness / "projects").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.harness)], check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q",
                        "--allow-empty", "-m", "first"], cwd=str(self.harness), check=True)
        old = os.getcwd()
        os.chdir(str(self.harness))
        self.addCleanup(os.chdir, old)
        self.suite = write_suite(self.tmp / "suite")
        (self.suite / "key" / "hidden.txt").write_text("the hidden answer\n")

    def gh_state(self):
        path = self.gh_home / "state.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def set_gh(self, **fields):
        state = self.gh_state()
        state.update(fields)
        (self.gh_home / "state.json").write_text(json.dumps(state))

    def gh_calls(self):
        path = self.gh_home / "calls.log"
        return path.read_text().splitlines() if path.exists() else []

    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = eval_harness.main(list(args))
        return code, out.getvalue()

    def create(self):
        suite = eval_harness.load_suite(self.suite, self.harness, clone_into=self.harness / "projects")
        return eval_harness.create_run(suite, {"owner": "acme", "harness": self.harness, "start": "true",
                                               "clone_into": self.harness / "projects"})


class Confirmation(WithFakeGh):
    def start_args(self, *extra):
        return ("run", str(self.suite), "--start", "true", "--owner", "acme") + extra

    def test_with_no_terminal_and_no_yes_nothing_is_created(self):
        with mock.patch("sys.stdin", io.StringIO("")):
            code, out = self.run_cli(*self.start_args())
        self.assertNotEqual(code, 0)
        self.assertIn("--yes", out)
        self.assertEqual(self.gh_calls(), [])
        self.assertFalse((self.harness / ".harness").exists())

    def test_the_question_says_a_run_spends_model_tokens(self):
        with mock.patch("eval_harness.interactive", return_value=True), \
                mock.patch("builtins.input", return_value="no") as asked:
            code, _ = self.run_cli(*self.start_args())
        self.assertIn("model tokens", asked.call_args[0][0])
        self.assertNotEqual(code, 0)
        self.assertEqual(self.gh_calls(), [])

    def test_a_refused_suite_stops_before_the_question(self):
        (self.suite / "suite.json").unlink()
        with mock.patch("builtins.input") as asked:
            code, out = self.run_cli(*self.start_args("--yes"))
        self.assertEqual(code, 2)
        asked.assert_not_called()
        self.assertEqual(self.gh_calls(), [])


class CreateRun(WithFakeGh):
    def test_the_repo_is_private_with_the_seed_on_main(self):
        record = self.create()
        repo = self.gh_state()["repos"][record["repo"]]
        self.assertTrue(repo["private_flag"])
        self.assertTrue(record["repo"].startswith("acme/eval-tiny-"))
        files = subprocess.run(["git", "ls-tree", "-r", "--name-only", "origin/main"], cwd=record["clone"],
                               capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(files, ["app.txt"])

    def test_branch_protection_requires_the_suites_checks(self):
        record = self.create()
        protection = self.gh_state()["repos"][record["repo"]]["protection"]
        self.assertEqual(protection["required_status_checks"]["contexts"], ["checks"])
        self.assertTrue(protection["enforce_admins"])

    def test_the_issues_are_filed_in_order(self):
        (self.suite / "issues" / "02-second.md").write_text("Then this\n\nMore.\n")
        config = json.loads((self.suite / "suite.json").read_text())
        config["issues"].append("issues/02-second.md")
        (self.suite / "suite.json").write_text(json.dumps(config))
        record = self.create()
        issues = self.gh_state()["repos"][record["repo"]]["issues"]
        self.assertEqual([issue["title"] for issue in issues], ["Fix the app", "Then this"])
        self.assertEqual(issues[0]["body"].strip(), "It is wrong.")
        self.assertEqual([item["number"] for item in record["issues"]], [1, 2])

    def test_a_repo_that_comes_back_public_stops_the_run(self):
        self.set_gh(force_visibility="PUBLIC")
        with self.assertRaises(eval_harness.RunError) as caught:
            self.create()
        self.assertIn("private", str(caught.exception))
        self.assertFalse([call for call in self.gh_calls() if call.startswith("issue create")])

    def test_protection_that_fails_stops_the_run_and_says_why(self):
        self.set_gh(protect_fails=True)
        with self.assertRaises(eval_harness.RunError) as caught:
            self.create()
        self.assertIn("Upgrade to GitHub Pro", str(caught.exception))
        self.assertFalse([call for call in self.gh_calls() if call.startswith("issue create")])

    def test_a_protection_error_that_isnt_about_the_plan_doesnt_blame_the_plan(self):
        self.set_gh(protect_fails=True, protect_message="unexpected end of JSON input")
        with self.assertRaises(eval_harness.RunError) as caught:
            self.create()
        self.assertIn("unexpected end of JSON input", str(caught.exception))
        self.assertNotIn("paid plan", str(caught.exception))

    def test_a_protection_error_about_the_plan_says_so(self):
        self.set_gh(protect_fails=True)
        with self.assertRaises(eval_harness.RunError) as caught:
            self.create()
        self.assertIn("paid plan", str(caught.exception))

    def test_a_stopped_setup_keeps_the_repo_and_names_it(self):
        self.set_gh(protect_fails=True)
        with self.assertRaises(eval_harness.RunError) as caught:
            self.create()
        self.assertIn("acme/eval-tiny-", str(caught.exception))
        self.assertFalse([call for call in self.gh_calls() if "delete" in call])

    def test_list_names_a_repo_whose_setup_stopped(self):
        self.set_gh(protect_fails=True)
        with self.assertRaises(eval_harness.RunError):
            self.create()
        out = self.run_cli("list")[1]
        self.assertIn("acme/eval-tiny-", out)
        self.assertIn("setup stopped", out)

    def test_no_key_file_reaches_the_clone(self):
        record = self.create()
        names = [path.name for path in Path(record["clone"]).rglob("*")]
        self.assertNotIn("hidden.txt", names)
        self.assertNotIn("score", names)


class RunRecord(WithFakeGh):
    def test_the_record_holds_the_repos_id_and_the_harness_commit(self):
        record = self.create()
        saved = json.loads((self.harness / ".harness" / "harness-evals" / record["id"] / "run.json").read_text())
        self.assertEqual(saved["repo_id"], "R_" + record["repo"])
        self.assertEqual(saved["harness_commit"], subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(self.harness), capture_output=True, text=True).stdout.strip())
        self.assertEqual(saved["suite_path"], str(self.suite))

    def test_list_names_each_run_repo(self):
        record = self.create()
        code, out = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn(record["repo"], out)
        self.assertIn(record["id"], out)

    def test_list_says_so_when_there_are_no_runs(self):
        self.assertIn("No runs", self.run_cli("list")[1])

    def test_nothing_in_the_runner_deletes_a_repo(self):
        source = (ROOT / "scripts" / "eval_harness.py").read_text()
        self.assertNotIn('"delete"', source)
        self.assertNotIn("repo delete", source)


class WithStub(WithFakeGh):
    def setUp(self):
        super().setUp()
        self.stub = self.tmp / "stub_harness.py"
        self.stub.write_text(STUB_HARNESS)
        self.log = self.tmp / "stub.log"
        self.plan = self.tmp / "plan.json"
        self.plan.write_text("{}")
        patcher = mock.patch.dict(os.environ, {"STUB_LOG": str(self.log), "STUB_PLAN": str(self.plan)})
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.suite / "issues" / "02-second.md").write_text("Then this\n\nMore.\n")
        config = json.loads((self.suite / "suite.json").read_text())
        config["issues"].append("issues/02-second.md")
        (self.suite / "suite.json").write_text(json.dumps(config))
        patcher = mock.patch("eval_harness.CI_POLL_SECONDS", 0.01)
        patcher.start()
        self.addCleanup(patcher.stop)

    def set_plan(self, **issues):
        self.plan.write_text(json.dumps({key.lstrip("i"): value for key, value in issues.items()}))

    def run_suite(self, *extra):
        start = "{} {} {{issue}} {{clone}} {{repo}}".format(sys.executable, self.stub)
        return self.run_cli("run", str(self.suite), "--start", start, "--owner", "acme", "--yes", *extra)

    def stub_calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def only_run(self):
        records = sorted((self.harness / ".harness" / "harness-evals").glob("*/run.json"))
        self.assertEqual(len(records), 1)
        return json.loads(records[0].read_text())

    def merges(self):
        return [call for call in self.gh_calls() if call.startswith("pr merge")]


class StartCommand(WithStub):
    def test_it_runs_in_the_harness_with_its_values_filled(self):
        self.run_suite("--merge-in-run-repo")
        calls = self.stub_calls()
        record = self.only_run()
        self.assertEqual([c["issue"] for c in calls], ["1", "2"])
        self.assertEqual(calls[0]["clone"], record["clone"])
        self.assertEqual(calls[0]["repo"], record["repo"])
        self.assertEqual(calls[0]["cwd"], str(self.harness))

    def test_project_is_the_clone_relative_to_the_harness(self):
        self.run_cli("run", str(self.suite), "--start", "echo {project} >> " + str(self.log), "--owner", "acme",
                     "--yes")
        self.assertTrue(self.log.read_text().startswith("projects/eval-tiny-"))

    def test_a_non_zero_exit_records_a_stop_and_ends_the_run(self):
        self.set_plan(i1={"exit": 3})
        self.run_suite("--merge-in-run-repo")
        record = self.only_run()
        self.assertIn("exited 3", record["stops"][0]["why"])
        self.assertEqual(record["state"], "ended")
        self.assertEqual([c["issue"] for c in self.stub_calls()], ["1"])

    def test_a_timeout_records_a_stop_and_ends_the_run(self):
        self.set_plan(i1={"sleep": 30})
        self.run_suite("--timeout", "0.005")
        record = self.only_run()
        self.assertIn("timed out", record["stops"][0]["why"])
        self.assertEqual(record["state"], "ended")

    def test_text_in_an_issue_never_reaches_a_command(self):
        marker = self.tmp / "pwned"
        (self.suite / "issues" / "01-first.md").write_text("$(touch {0})\n\n`touch {0}`\n".format(marker))
        self.run_suite("--merge-in-run-repo")
        self.assertFalse(marker.exists())


class FolderCases(WithStub):
    def test_a_clone_path_with_odd_characters_stays_one_argument(self):
        odd = self.tmp / "odd $(touch pwned) folder"
        odd.mkdir()
        self.set_plan(i1={"prs": 0})
        self.run_suite("--clone-into", str(odd))
        self.assertTrue(self.stub_calls()[0]["clone"].startswith(str(odd)))
        self.assertFalse((self.harness / "pwned").exists())

    def test_a_harness_that_isnt_a_git_repo_is_refused_before_anything_is_created(self):
        plain = self.tmp / "plain"
        (plain / "projects").mkdir(parents=True)
        code, out = self.run_suite("--harness", str(plain))
        self.assertEqual(code, 2)
        self.assertIn("git", out)
        self.assertEqual(self.gh_calls(), [])

    def test_a_timed_out_start_takes_what_it_started_with_it(self):
        marker = self.tmp / "still-running"
        self.run_cli("run", str(self.suite), "--owner", "acme", "--yes", "--timeout", "0.005", "--start",
                     "(sleep 2; touch {}) & wait".format(marker))
        time.sleep(2.5)
        self.assertFalse(marker.exists())


class FindingThePullRequest(WithStub):
    def test_no_pull_request_records_a_stop(self):
        self.set_plan(i1={"prs": 0})
        self.run_suite("--merge-in-run-repo")
        self.assertIn("no pull request", self.only_run()["stops"][0]["why"])
        self.assertEqual(self.merges(), [])

    def test_several_pull_requests_record_a_stop_and_nothing_is_merged(self):
        self.set_plan(i1={"prs": 2})
        self.run_suite("--merge-in-run-repo")
        self.assertIn("2 pull requests", self.only_run()["stops"][0]["why"])
        self.assertEqual(self.merges(), [])

    def test_the_next_issue_doesnt_count_the_last_ones_pull_request(self):
        self.run_suite("--merge-in-run-repo")
        record = self.only_run()
        self.assertEqual([issue["pr"] for issue in record["issues"]], [1, 2])


class Merging(WithStub):
    def test_with_the_flag_each_passing_pull_request_is_merged(self):
        self.run_suite("--merge-in-run-repo")
        self.assertEqual(len(self.merges()), 2)
        self.assertEqual(self.only_run()["stops"], [])

    def test_a_merge_that_fails_once_is_tried_again(self):
        self.set_gh(merge_fails=1)
        self.run_suite("--merge-in-run-repo")
        self.assertEqual(self.only_run()["stops"], [])
        self.assertEqual([issue["state"] for issue in self.only_run()["issues"]], ["done", "done"])

    def test_a_merge_that_keeps_failing_stops_the_run(self):
        self.set_gh(merge_fails=10)
        self.run_suite("--merge-in-run-repo")
        self.assertIn("couldn't merge", self.only_run()["stops"][0]["why"])
        self.assertEqual(len(self.merges()), 3)

    def test_failing_ci_stops_the_run_with_nothing_merged(self):
        self.set_gh(checks=[{"name": "checks", "bucket": "fail"}])
        self.run_suite()
        record = self.only_run()
        record.update(merge=True, timeout_minutes=0)
        with self.assertRaises(eval_harness.RunError) as caught:
            eval_harness.merge_pull_request(record, 1, ["checks"])
        self.assertIn("failed checks", str(caught.exception))
        self.assertEqual(self.merges(), [])

    def merge_with_no_time_left(self):
        """Stop at the merge, then try it with a record that allows no wait."""
        self.run_suite()
        record = self.only_run()
        record.update(merge=True, timeout_minutes=0)
        with self.assertRaises(eval_harness.RunError) as caught:
            eval_harness.merge_pull_request(record, 1, ["checks"])
        self.assertIn("hasn't passed", str(caught.exception))
        self.assertEqual(self.merges(), [])

    def test_pending_ci_that_never_finishes_isnt_merged(self):
        self.set_gh(checks=[{"name": "checks", "bucket": "pending"}])
        self.merge_with_no_time_left()

    def test_a_required_check_that_never_appeared_isnt_merged(self):
        self.set_gh(checks=[{"name": "something else", "bucket": "pass"}])
        self.merge_with_no_time_left()

    def test_a_repo_that_isnt_the_runs_own_is_refused(self):
        self.set_plan(i1={"prs": 0})
        self.run_suite("--merge-in-run-repo")
        record = self.only_run()
        state = self.gh_state()
        state["repos"]["someone/else"] = dict(state["repos"][record["repo"]], id="R_other")
        self.set_gh(**state)
        record["repo"] = "someone/else"
        with self.assertRaises(eval_harness.RunError) as caught:
            eval_harness.merge_pull_request(record, 1, ["checks"])
        self.assertIn("isn't this run's repo", str(caught.exception))
        self.assertEqual(self.merges(), [])

    def test_a_record_that_says_no_merge_is_refused(self):
        self.set_plan(i1={"prs": 0})
        self.run_suite("--merge-in-run-repo")
        record = self.only_run()
        record["merge"] = False
        with self.assertRaises(eval_harness.RunError):
            eval_harness.merge_pull_request(record, 1, ["checks"])
        self.assertEqual(self.merges(), [])


class WaitingForAPerson(WithStub):
    def merge_by_hand(self, number=1):
        record = self.only_run()
        state = self.gh_state()
        state["repos"][record["repo"]]["prs"][number - 1]["state"] = "MERGED"
        head = state["repos"][record["repo"]]["prs"][number - 1]["head"]
        subprocess.run(["git", "--git-dir", str(self.gh_home / "remotes" / (record["repo"].replace("/", "__") + ".git")),
                        "update-ref", "refs/heads/main", "refs/heads/" + head], check=True)
        self.set_gh(**state)

    def test_without_the_flag_the_run_stops_at_its_first_merge_and_says_so(self):
        code, out = self.run_suite()
        self.assertEqual(code, 3)
        self.assertIn("pull request 1", out)
        self.assertIn("resume", out)
        self.assertEqual(self.merges(), [])
        self.assertEqual([c["issue"] for c in self.stub_calls()], ["1"])
        record = self.only_run()
        self.assertEqual(record["state"], "waiting")
        self.assertEqual(len(record["stops"]), 1)
        self.assertEqual(record["stops"][0]["kind"], "merge")

    def test_resume_before_the_merge_still_waits_and_adds_no_stop(self):
        self.run_suite()
        code, out = self.run_cli("resume", self.only_run()["id"])
        self.assertEqual(code, 3)
        self.assertIn("pull request 1", out)
        self.assertEqual(len(self.only_run()["stops"]), 1)
        self.assertEqual([c["issue"] for c in self.stub_calls()], ["1"])

    def test_resume_after_the_merge_works_the_next_issue(self):
        self.run_suite()
        self.merge_by_hand()
        code, _ = self.run_cli("resume", self.only_run()["id"])
        self.assertEqual(code, 3)
        self.assertEqual([c["issue"] for c in self.stub_calls()], ["1", "2"])
        self.assertEqual(len(self.only_run()["stops"]), 2)

    def test_resume_end_ends_the_run_there(self):
        self.run_suite()
        self.run_cli("resume", self.only_run()["id"], "--end")
        self.assertEqual(self.only_run()["state"], "ended")
        self.assertEqual([c["issue"] for c in self.stub_calls()], ["1"])


class Stops(WithStub):
    def test_stop_adds_a_persons_stop_to_the_count(self):
        self.run_suite()
        run_id = self.only_run()["id"]
        code, _ = self.run_cli("stop", run_id, "had to fix the login")
        self.assertEqual(code, 0)
        stops = self.only_run()["stops"]
        self.assertEqual(len(stops), 2)
        self.assertEqual(stops[1], {"why": "had to fix the login", "kind": "person"})

    def test_a_stop_after_the_run_ended_reaches_its_result(self):
        self.run_suite("--merge-in-run-repo")
        run_id = self.only_run()["id"]
        self.run_cli("stop", run_id, "had to fix it afterwards")
        result = json.loads((self.harness / ".harness" / "harness-evals" / run_id / "result.json").read_text())
        self.assertEqual(result["stops"][-1]["why"], "had to fix it afterwards")

    def test_stop_on_an_unknown_run_says_so(self):
        code, out = self.run_cli("stop", "nope", "why")
        self.assertEqual(code, 2)
        self.assertIn("no run called nope", out)


class Boundaries(unittest.TestCase):
    SOURCE = (ROOT / "scripts" / "eval_harness.py").read_text()

    def test_the_runner_imports_only_the_standard_library_and_the_loop(self):
        imported = set()
        for node in ast.walk(ast.parse(self.SOURCE)):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module.split(".")[0])
        allowed = {"argparse", "datetime", "filecmp", "json", "loop", "os", "pathlib", "re", "shlex", "shutil",
                   "signal", "subprocess", "sys", "tempfile", "time"}
        self.assertEqual(imported - allowed, set())

    def test_the_runner_never_reads_a_credential(self):
        for text in ("GH_TOKEN", "GITHUB_TOKEN", "auth token", "hosts.yml", ".netrc"):
            self.assertNotIn(text, self.SOURCE)


# Passes when answer.txt says right. Its one trap: no secret-named variable reached it.
SCORE_RUN = r"""#!/usr/bin/env python3
import json, os
run = os.environ["RUN_DIR"]
try:
    right = open(os.path.join(run, "answer.txt")).read().strip() == "right"
except OSError:
    right = False
print(json.dumps({"tests": [{"name": "answer is right", "passed": right},
                            {"name": "saw pull requests " + os.environ["PR_NUMBERS"], "passed": True}],
                  "traps": [{"name": "no token in scoring", "avoided": "GH_TOKEN" not in os.environ}]}))
"""


class ScoredRun(WithStub):
    def setUp(self):
        super().setUp()
        (self.suite / "key" / "score").write_text(SCORE_RUN)

    def result(self):
        return json.loads((self.harness / ".harness" / "harness-evals" / self.only_run()["id"] / "result.json").read_text())


class Scoring(ScoredRun):
    def test_the_merged_result_is_scored(self):
        self.set_plan(i1={"files": {"answer.txt": "right"}})
        code, out = self.run_suite("--merge-in-run-repo")
        self.assertEqual(code, 0)
        result = self.result()
        self.assertEqual(result["tests"][0], {"name": "answer is right", "passed": True})
        self.assertEqual(result["tests"][1]["name"], "saw pull requests 1 2")
        self.assertIn("2/2", out)

    def test_an_unmerged_run_scores_its_last_pull_request(self):
        self.set_plan(i1={"files": {"answer.txt": "right"}})
        self.run_suite()
        self.run_cli("resume", self.only_run()["id"], "--end")
        self.assertTrue(self.result()["tests"][0]["passed"])
        self.assertIn("pull request 1", self.result()["scored_at"])

    def test_a_failed_start_still_gets_a_score(self):
        self.set_plan(i1={"prs": 0, "exit": 1})
        code, out = self.run_suite("--merge-in-run-repo")
        self.assertEqual(code, 1)
        self.assertEqual(self.result()["stops"][0]["kind"], "run")
        self.assertFalse(self.result()["tests"][0]["passed"])
        self.assertIn("Stops", out)

    def test_score_output_that_doesnt_parse_reads_not_scored(self):
        (self.suite / "key" / "score").write_text("#!/bin/sh\necho hello\n")
        code, out = self.run_suite("--merge-in-run-repo")
        self.assertEqual(code, 1)
        self.assertIn("printed something other", self.result()["not_scored"])
        self.assertIn("Not scored", out)

    def test_secrets_in_the_environment_dont_reach_the_scorer(self):
        self.set_plan(i1={"files": {"answer.txt": "right"}})
        with mock.patch.dict(os.environ, {"GH_TOKEN": "x"}):
            self.run_suite("--merge-in-run-repo")
        self.assertTrue(self.result()["traps"][0]["avoided"])

    def test_no_key_file_in_the_history_means_no_leak(self):
        self.run_suite("--merge-in-run-repo")
        self.assertEqual(self.result()["key_leaks"], [])

    def test_a_key_file_committed_to_the_repo_is_found(self):
        self.set_plan(i1={"files": {"found.txt": "the hidden answer\n"}}, i2={"files": {"found.txt": "gone\n"}})
        code, out = self.run_suite("--merge-in-run-repo")
        self.assertEqual(self.result()["key_leaks"], ["hidden.txt"])
        self.assertEqual(code, 1)
        self.assertIn("hidden.txt", out)

    def test_an_answer_the_harness_wrote_the_same_as_the_reference_isnt_a_leak(self):
        (self.suite / "key" / "reference").mkdir()
        (self.suite / "key" / "reference" / "answer.txt").write_text("right\n")
        (self.suite / "key" / "wrong" / "close").mkdir(parents=True)
        (self.suite / "key" / "wrong" / "close" / "answer.txt").write_text("nearly\n")
        self.set_plan(i1={"files": {"answer.txt": "right\n", "other.txt": "nearly\n"}})
        self.run_suite("--merge-in-run-repo")
        self.assertEqual(self.result()["key_leaks"], [])

    def test_the_result_holds_what_the_spec_asks(self):
        self.run_suite("--merge-in-run-repo")
        result = self.result()
        for field in ("suite", "harness_commit", "tests", "traps", "seconds", "stops", "cost"):
            self.assertIn(field, result)

    def test_the_tiny_public_suite_runs_with_a_stub(self):
        self.suite = ROOT / "examples" / "eval-suite"
        self.set_plan(i1={"files": {"shop.py": "def order_total(subtotal, tax_rate):\n"
                                               "    return subtotal + subtotal * tax_rate\n"}})
        code, out = self.run_suite("--merge-in-run-repo")
        self.assertEqual(code, 0, out)
        self.assertIn("3/3", out)
        self.assertEqual(self.result()["cost"], "not reported")


class Cost(ScoredRun):
    def test_no_usage_reads_not_reported(self):
        _, out = self.run_suite("--merge-in-run-repo")
        self.assertEqual(self.result()["cost"], "not reported")
        self.assertIn("not reported", out)

    def test_the_usage_command_gives_the_total(self):
        self.run_suite("--merge-in-run-repo", "--usage-command", "echo 1.25")
        self.assertEqual(self.result()["cost"], 1.25)

    def test_a_usage_command_that_prints_no_number_reads_not_reported(self):
        self.run_suite("--merge-in-run-repo", "--usage-command", "echo lots")
        self.assertEqual(self.result()["cost"], "not reported")

    def test_a_usage_command_that_fails_reads_not_reported(self):
        self.run_suite("--merge-in-run-repo", "--usage-command", "echo 3; exit 1")
        self.assertEqual(self.result()["cost"], "not reported")

    def starter_run(self, entries, *extra):
        """A harness whose start command names scripts/loop.py and leaves the usage that loop would."""
        (self.harness / "scripts").mkdir()
        (self.harness / "scripts" / "loop.py").write_text("")
        usage = self.tmp / "usage.json"
        usage.write_text(json.dumps(entries))
        start = ('mkdir -p .loop/projects/$(basename {{clone}})/issue-{{issue}} && '
                 'cp {} .loop/projects/$(basename {{clone}})/issue-{{issue}}/usage.json; '
                 'exit 1 # scripts/loop.py').format(usage)
        return self.run_cli("run", str(self.suite), "--start", start, "--owner", "acme", "--yes", *extra)

    def test_this_harness_reads_its_loops_own_usage(self):
        self.starter_run([{"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.5},
                          {"input_tokens": 1, "output_tokens": 1, "cost_usd": 0.25}])
        self.assertEqual(self.result()["cost"], 0.75)
        self.assertEqual(self.result()["tokens"], 17)

    def test_a_loop_that_reported_nothing_reads_not_reported(self):
        self.starter_run([{"input_tokens": None, "cost_usd": None}])
        self.assertEqual(self.result()["cost"], "not reported")

    def test_the_usage_command_outranks_the_loops_usage(self):
        self.starter_run([{"input_tokens": 10, "cost_usd": 0.5}], "--usage-command", "echo 9")
        self.assertEqual(self.result()["cost"], 9)

    def test_the_usage_command_sets_cost_and_the_loop_still_gives_tokens(self):
        self.starter_run([{"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.5}], "--usage-command", "echo 0")
        self.assertEqual(self.result()["cost"], 0)
        self.assertEqual(self.result()["tokens"], 15)

    def test_rounds_are_the_loops_highest_build_round_per_issue(self):
        self.starter_run([{"step": "plan", "round": 0, "input_tokens": 1},
                          {"step": "build", "round": 1, "input_tokens": 1},
                          {"step": "review", "round": 1, "input_tokens": 1},
                          {"step": "build", "round": 3, "input_tokens": 1}])
        self.assertEqual(self.result()["rounds"], {"1": 3})

    def test_another_harness_reports_no_rounds(self):
        self.run_suite("--merge-in-run-repo")
        self.assertEqual(self.result()["rounds"], "not reported")
        self.assertEqual(self.result()["tokens"], "not reported")

    def test_the_scorecard_shows_rounds_and_tokens(self):
        _, out = self.starter_run([{"step": "build", "round": 2, "input_tokens": 1200, "output_tokens": 300}])
        self.assertIn("Rounds    2", out)
        self.assertIn("Tokens    1,500", out)


def result_file(folder, name, tests, traps, cost=1.0, seconds=60, stops=0, rounds="not reported", tokens="not reported"):
    folder = Path(folder) / name
    folder.mkdir(parents=True)
    (folder / "result.json").write_text(json.dumps({
        "run": name, "suite": "tiny", "harness_commit": name + "000", "seconds": seconds, "cost": cost,
        "rounds": rounds, "tokens": tokens,
        "stops": [{"why": "x", "kind": "run"}] * stops, "key_leaks": [],
        "tests": [{"name": n, "passed": p} for n, p in tests.items()],
        "traps": [{"name": n, "avoided": a} for n, a in traps.items()]}))


class Compare(WithFakeGh):
    def setUp(self):
        super().setUp()
        self.runs = self.harness / ".harness" / "harness-evals"

    def compare(self, a_tests, a_traps, b_tests, b_traps, **b_fields):
        result_file(self.runs, "a", a_tests, a_traps)
        result_file(self.runs, "b", b_tests, b_traps, **b_fields)
        return self.run_cli("compare", "a", "b")

    def test_a_test_that_got_worse_is_named(self):
        code, out = self.compare({"adds up": True}, {}, {"adds up": False}, {})
        self.assertEqual(code, 0)
        self.assertIn("Worse: test adds up", out)

    def test_a_trap_that_got_worse_is_named(self):
        out = self.compare({}, {"no decoy": True}, {}, {"no decoy": False})[1]
        self.assertIn("Worse: trap no decoy", out)

    def test_a_test_that_got_better_is_named(self):
        out = self.compare({"adds up": False}, {}, {"adds up": True}, {})[1]
        self.assertIn("Better: test adds up", out)

    def test_a_test_that_disappeared_is_named(self):
        out = self.compare({"adds up": True, "gone": True}, {}, {"adds up": True}, {})[1]
        self.assertIn("Gone: test gone", out)

    def test_a_new_test_is_named(self):
        out = self.compare({}, {}, {"fresh": True}, {})[1]
        self.assertIn("New: test fresh", out)

    def test_it_says_so_when_nothing_changed(self):
        out = self.compare({"adds up": True}, {"no decoy": True}, {"adds up": True}, {"no decoy": True})[1]
        self.assertIn("Nothing changed in tests or traps", out)

    def test_the_two_runs_sit_side_by_side(self):
        out = self.compare({"adds up": True}, {}, {"adds up": True}, {}, cost="not reported", seconds=90, stops=2)[1]
        self.assertIn("not reported", out)
        self.assertIn("Stops", out)
        self.assertIn("b000", out)

    def test_rounds_and_tokens_sit_side_by_side(self):
        out = self.compare({"adds up": True}, {}, {"adds up": True}, {}, rounds={"1": 3, "2": 1}, tokens=2500000)[1]
        self.assertRegex(out, r"Rounds\s+not reported\s+4")
        self.assertRegex(out, r"Tokens\s+not reported\s+2,500,000")

    def test_an_older_result_with_no_rounds_still_compares(self):
        result_file(self.runs, "a", {"adds up": True}, {})
        path = self.runs / "a" / "result.json"
        old = json.loads(path.read_text())
        del old["rounds"]
        path.write_text(json.dumps(old))
        self.assertIn("Nothing changed", self.run_cli("compare", "a", "a")[1])

    def test_an_unknown_run_says_so(self):
        code, out = self.run_cli("compare", "a", "b")
        self.assertEqual(code, 2)
        self.assertIn("no result for a", out)

    def test_a_result_file_path_also_works(self):
        result_file(self.runs, "a", {"adds up": True}, {})
        path = str(self.runs / "a" / "result.json")
        self.assertIn("Nothing changed", self.run_cli("compare", path, path)[1])


if __name__ == "__main__":
    unittest.main()
