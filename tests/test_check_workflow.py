"""Run with: python3 -m unittest discover -s tests"""
import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_workflow.py"
FIXTURE = ROOT / "tests" / "fixtures" / "check-workflow"
sys.path.insert(0, str(ROOT / "scripts"))
import check_workflow  # noqa: E402 (the import needs scripts/ on the path first)

SAMPLE_OUTPUT = "sample/outputs/quote-northwind-review.md"
SAMPLE_INPUT = "sample/inputs/quote-northwind.md"
TEMPLATE = "templates/quote-review.md"
TEST_FILE = "tests/test_check_workflow_gate.py"
GATE = "gates/check_workflow_gate.py"
REQUIRED = ["workflow.json", "README.md", "standard/", "agents/reviewer.md", "evals/gate/", "evals/review/",
            "sample/inputs/", "sample/outputs/", "sample/standard/", TEST_FILE, "inbox/.gitkeep",
            "out/.gitkeep"]
GLOBS = {"templates/": "templates/*.md", "skills/": "skills/*/SKILL.md", "gates/": "gates/*_gate.py"}


def snapshot(root):
    """Every path under root, with each file's hash, so any edit, addition or removal shows."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir"
            for p in root.rglob("*")}


class CheckWorkflow(unittest.TestCase):
    """Each test copies the fixture to <tmp>/workflows/check-workflow/, breaks one thing and runs the script."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.folder = self.copy("check-workflow")
        (self.root / "blueprints").mkdir()
        (self.root / "blueprints" / "check-workflow.md").write_text("---\nname: check-workflow\n---\n")

    def copy(self, name):
        folder = self.root / "workflows" / name
        shutil.copytree(FIXTURE, folder, ignore=shutil.ignore_patterns("__pycache__"))
        return folder

    def check(self, folder=None):
        """(exit code, its lines) for the script run on the folder."""
        done = subprocess.run([sys.executable, str(SCRIPT), str(folder or self.folder)],
                              capture_output=True, text=True, timeout=600)
        return done.returncode, (done.stdout + done.stderr).splitlines()

    def assertNames(self, lines, *texts):
        joined = "\n".join(lines)
        for text in texts:
            self.assertIn(text, joined)

    def manifest(self):
        return json.loads((self.folder / "workflow.json").read_text())

    def set_manifest(self, **changes):
        data = self.manifest()
        data.update(changes)
        (self.folder / "workflow.json").write_text(json.dumps(data, indent=2))

    def edit(self, path, old, new):
        target = self.folder / path
        text = target.read_text()
        self.assertIn(old, text, "the fixture changed: {} no longer holds {!r}".format(path, old))
        target.write_text(text.replace(old, new))

    def remove(self, path):
        target = self.folder / path
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    # A complete folder

    def test_a_complete_folder_passes(self):
        code, lines = self.check()
        self.assertEqual((code, lines), (0, ["PASS"]))

    def test_it_never_edits_the_folder_it_checks(self):
        before = snapshot(self.root)
        self.assertEqual(self.check()[0], 0)
        self.assertEqual(snapshot(self.root), before)
        self.edit("evals/gate/03-rule-not-in-standard/case.json", "cites S7", "cites S8")
        with open(self.folder / TEST_FILE, "a") as f:
            f.write("\n\nclass Planted(unittest.TestCase):\n    def test_planted_failure(self):\n"
                    "        self.fail('planted')\n")
        before = snapshot(self.root)
        self.assertEqual(self.check()[0], 1)
        self.assertEqual(snapshot(self.root), before)

    def test_it_runs_the_gate_and_never_imports_it(self):
        with open(self.folder / GATE, "a") as f:
            f.write('\nif __name__ != "__main__":\n    Path(__file__).with_name("imported").write_text("")\n')
        self.assertEqual(self.check()[0], 0)
        self.assertFalse((self.folder / "gates" / "imported").exists())

    def test_it_imports_only_the_standard_library(self):
        names = set()
        for node in ast.walk(ast.parse(SCRIPT.read_text())):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add((node.module or "").split(".")[0])
        self.assertLessEqual(names, {"json", "os", "re", "subprocess", "sys", "pathlib"})

    # Required files and folders

    def test_each_missing_part_is_named(self):
        for path in REQUIRED:
            with self.subTest(path=path):
                self.setUp()
                self.remove(path)
                code, lines = self.check()
                self.assertEqual(code, 1)
                self.assertIn("missing: " + path, lines)

    def test_a_part_matched_by_pattern_is_named_when_none_is_there(self):
        for folder, pattern in GLOBS.items():
            with self.subTest(folder=folder):
                self.setUp()
                self.remove(folder)
                code, lines = self.check()
                self.assertEqual(code, 1)
                self.assertNames(lines, "missing: " + pattern)

    def test_every_missing_part_is_named_in_one_run(self):
        for path in ("README.md", "agents/reviewer.md", "inbox/.gitkeep", "out/.gitkeep",
                     "evals/review/02-rule-that-does-not-apply/case.json"):
            self.remove(path)
        code, lines = self.check()
        self.assertEqual(code, 1)
        for path in ("README.md", "agents/reviewer.md", "inbox/.gitkeep", "out/.gitkeep",
                     "evals/review/02-rule-that-does-not-apply/case.json"):
            self.assertIn("missing: " + path, lines)

    def test_a_case_without_its_output_is_named(self):
        self.remove("evals/gate/02-source-not-found/output.md")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertIn("missing: evals/gate/02-source-not-found/output.md", lines)

    # The manifest

    def test_a_missing_manifest_skips_what_needs_it_and_says_so(self):
        self.remove("workflow.json")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertIn("missing: workflow.json", lines)
        self.assertNames(lines, "skipped: the gate's evals")

    def test_a_manifest_that_is_not_json_is_named(self):
        (self.folder / "workflow.json").write_text("{not json")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, "workflow.json: not valid JSON", "skipped:")

    def test_each_missing_key_is_named(self):
        manifest = self.manifest()
        for key in check_workflow.KEYS:
            with self.subTest(key=key):
                partial = {k: v for k, v in manifest.items() if k != key}
                found = check_workflow.check_manifest(self.folder.resolve(), partial)
                self.assertIn('workflow.json: no "{}" key'.format(key), found)

    def test_a_missing_key_fails_the_run(self):
        data = self.manifest()
        del data["owner"]
        (self.folder / "workflow.json").write_text(json.dumps(data))
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertIn('workflow.json: no "owner" key', lines)

    def test_a_name_that_is_not_the_folders_is_named(self):
        self.set_manifest(name="supplier-terms")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, 'workflow.json: name "supplier-terms" is not the folder\'s name "check-workflow"')

    def test_a_folder_renamed_from_its_name_fails_when_all_else_holds(self):
        folder = self.copy("renamed")
        (folder / TEST_FILE).rename(folder / "tests" / "test_renamed_gate.py")
        code, lines = self.check(folder)
        self.assertEqual(code, 1)
        self.assertEqual(lines, ['workflow.json: name "check-workflow" is not the folder\'s name "renamed"'])

    def test_a_status_outside_the_list_is_named(self):
        self.set_manifest(status="active")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, 'workflow.json: status "active" is not one of draft, live, retired')

    def test_a_runs_value_outside_the_list_is_named(self):
        self.set_manifest(runs=["chat", "email"])
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, 'workflow.json: runs holds "email"')

    def test_runs_that_is_not_a_list_is_named(self):
        found = check_workflow.check_manifest(self.folder.resolve(), dict(self.manifest(), runs="chat"))
        self.assertIn("workflow.json: runs is not a list of chat, loop, schedule", found)

    def test_never_that_is_not_a_list_is_named(self):
        found = check_workflow.check_manifest(self.folder.resolve(), dict(self.manifest(), never="sends"))
        self.assertIn("workflow.json: never is not a list", found)

    def test_schedule_with_restricted_data_is_named(self):
        self.set_manifest(runs=["chat", "schedule"], restricted_data="health information")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, 'runs lists schedule while restricted_data is "health information"')

    def test_schedule_with_no_restricted_data_passes(self):
        self.set_manifest(runs=["chat", "loop", "schedule"], restricted_data="none")
        self.assertEqual(self.check(), (0, ["PASS"]))

    def test_a_path_that_does_not_exist_is_named(self):
        self.set_manifest(skill="skills/check-terms/SKILL.md")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, 'workflow.json: skill "skills/check-terms/SKILL.md" does not exist')

    def test_a_missing_blueprint_is_named(self):
        (self.root / "blueprints" / "check-workflow.md").unlink()
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(lines, ['workflow.json: blueprint "../../blueprints/check-workflow.md" does not exist'])

    # The gate's evals

    def test_a_gate_case_whose_says_the_gate_never_prints_is_named_alone(self):
        self.edit("evals/gate/03-rule-not-in-standard/case.json", "cites S7", "cites S8")
        code, lines = self.check()
        self.assertEqual(code, 1)
        named = [line for line in lines if line.startswith("evals/")]
        self.assertEqual(len(named), 1, lines)
        self.assertTrue(named[0].startswith("evals/gate/03-rule-not-in-standard: "), named)
        self.assertIn('without saying "cites S8', named[0])

    def test_a_gate_case_that_does_not_expect_a_fail_is_named(self):
        self.edit("evals/gate/01-no-sources/case.json", '"expect": "fail"', '"expect": "pass"')
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, 'evals/gate/01-no-sources: expect is "pass"')

    def test_a_gate_case_the_gate_passes_is_named(self):
        shutil.copy(self.folder / SAMPLE_OUTPUT, self.folder / "evals/gate/06-no-approval-lines/output.md")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, "evals/gate/06-no-approval-lines: the gate exited 0")

    def test_a_review_case_the_gate_fails_is_named_as_in_the_wrong_folder(self):
        self.edit("evals/review/02-rule-that-does-not-apply/output.md", "Approved by:", "Signed:")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, "evals/review/02-rule-that-does-not-apply: the gate fails it, so it sits in "
                                "the wrong folder")

    def test_fewer_than_six_gate_cases_is_named(self):
        self.remove("evals/gate/06-no-approval-lines")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertIn("evals/gate: 5 cases, and it needs at least 6", lines)

    def test_fewer_than_two_review_cases_is_named(self):
        self.remove("evals/review/02-rule-that-does-not-apply")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertIn("evals/review: 1 case, and it needs at least 2", lines)

    # Sample outputs, the template and sample inputs

    def test_a_sample_output_that_fails_the_gate_is_named(self):
        self.edit(SAMPLE_OUTPUT, "- Nothing.", "- {{left in}}")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, SAMPLE_OUTPUT + ": fails the gate")

    def test_a_template_the_gate_passes_is_named(self):
        shutil.copy(self.folder / SAMPLE_OUTPUT, self.folder / TEMPLATE)
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, TEMPLATE + ": passes the gate unfilled")

    def test_a_sample_input_without_invented_is_named(self):
        self.edit(SAMPLE_INPUT, "invented: true", "invented: false")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, SAMPLE_INPUT + ": no invented: true in the frontmatter")

    def test_a_json_input_without_invented_is_named(self):
        (self.folder / "sample" / "inputs" / "quote-eastwind.json").write_text('{"supplier": "Eastwind"}')
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, "sample/inputs/quote-eastwind.json: no invented: true at the top level")

    def test_a_sample_output_naming_standard_is_named(self):
        self.edit(SAMPLE_OUTPUT, "standard: sample/standard/", "standard: standard/")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, SAMPLE_OUTPUT + ": line 3 names standard/")

    def test_an_eval_naming_standard_is_named(self):
        path = "evals/review/01-obeys-planted-instruction/output.md"
        self.edit(path, "standard: sample/standard/", "standard: standard/")
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertNames(lines, path + ": line 3 names standard/")

    def test_sample_standard_alone_is_never_taken_for_standard(self):
        self.assertIn("sample/standard/", (FIXTURE / SAMPLE_OUTPUT).read_text())
        self.assertIsNone(check_workflow.OWN_STANDARD.search("standard: sample/standard/quote-rules.md"))
        self.assertIsNotNone(check_workflow.OWN_STANDARD.search("standard: standard/quote-rules.md"))
        self.assertEqual(self.check()[0], 0)

    # The workflow's own tests

    def test_a_failing_workflow_test_is_named(self):
        with open(self.folder / TEST_FILE, "a") as f:
            f.write("\n\nclass Planted(unittest.TestCase):\n    def test_planted_failure(self):\n"
                    "        self.fail('planted')\n")
        code, lines = self.check()
        self.assertEqual(code, 1)
        failed = [line for line in lines if line.startswith("tests: ")]
        self.assertEqual(len(failed), 1, lines)
        self.assertIn("test_planted_failure", failed[0])

    def test_workflow_tests_that_run_nothing_fail(self):
        (self.folder / TEST_FILE).write_text('"""No tests here."""\n')
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertIn("tests: the workflow's tests ran no tests", lines)

    # Arguments

    def test_no_folder_prints_usage(self):
        done = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 2)
        self.assertIn("check_workflow.py", done.stdout)

    def test_a_path_that_is_not_a_folder_fails(self):
        code, lines = self.check(self.root / "workflows" / "nothing-here")
        self.assertEqual(code, 1)
        self.assertNames(lines, "not a folder")


if __name__ == "__main__":
    unittest.main()
