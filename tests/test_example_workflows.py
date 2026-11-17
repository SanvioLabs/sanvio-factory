"""Run with: python3 -m unittest discover -s tests

Every worked workflow in examples/workflows/ passes scripts/check_workflow.py, and
the build-workflow skill names what stops it and what proves it's done.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples" / "workflows"
BLUEPRINTS = ROOT / "examples" / "blueprints"
CHECK = ROOT / "scripts" / "check_workflow.py"
SKILL = ROOT / "skills" / "build-workflow" / "SKILL.md"


def failures(root):
    """{folder name: what the check printed} for each folder in root whose check doesn't print PASS.

    Only root's own subfolders are checked: a loose file such as a README is skipped, and
    nothing outside root (people's own workflows/, the tests' fixtures) is looked at.
    """
    found = {}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for folder in sorted(p for p in Path(root).iterdir() if p.is_dir() and not p.name.startswith((".", "__"))):
        done = subprocess.run([sys.executable, str(CHECK), str(folder)], capture_output=True, text=True,
                              timeout=600, env=env)
        output = done.stdout + done.stderr
        if done.returncode != 0 or done.stdout.strip() != "PASS":
            found[folder.name] = output
    return found


class ExampleWorkflows(unittest.TestCase):
    def test_every_example_workflow_passes_the_check(self):
        folders = [p for p in EXAMPLES.iterdir() if p.is_dir()]
        self.assertTrue(folders, "examples/workflows/ holds no workflow, so nothing shows one passing")
        self.assertEqual(failures(EXAMPLES), {})

    def test_it_checks_the_examples_and_nowhere_else(self):
        self.assertEqual(EXAMPLES, ROOT / "examples" / "workflows")


class TheHelper(unittest.TestCase):
    """A copy of the example in a throwaway folder, laid out as in the repo so its blueprint resolves."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "examples" / "workflows"
        self.copy = self.root / "supplier-terms"
        shutil.copytree(EXAMPLES / "supplier-terms", self.copy, ignore=shutil.ignore_patterns("__pycache__"))
        (self.tmp / "examples" / "blueprints").mkdir()
        shutil.copy(BLUEPRINTS / "supplier-terms.md", self.tmp / "examples" / "blueprints" / "supplier-terms.md")

    def test_the_untouched_copy_passes(self):
        self.assertEqual(failures(self.root), {})

    def test_a_copy_with_a_gate_case_removed_fails(self):
        # Deleting a whole case folder still leaves more than the six the contract asks for,
        # so remove the case's expectation: the check must say it's missing.
        self.assertEqual(failures(self.root), {})
        (self.copy / "evals" / "gate" / "01-renewal-clause-missed" / "case.json").unlink()
        found = failures(self.root)
        self.assertEqual(list(found), ["supplier-terms"])
        self.assertIn("missing: evals/gate/01-renewal-clause-missed/case.json", found["supplier-terms"])

    def test_a_loose_file_in_the_root_is_not_a_workflow(self):
        (self.root / "README.md").write_text("# Worked workflows\n")
        self.assertEqual(failures(self.root), {})

    def test_it_never_looks_beyond_its_root(self):
        # A broken workflow in people's own workflows/ and in the tests' fixtures: neither is looked at.
        for broken in (self.tmp / "workflows" / "broken", self.tmp / "tests" / "fixtures" / "broken"):
            broken.mkdir(parents=True)
            (broken / "workflow.json").write_text("{}\n")
        self.assertEqual(failures(self.root), {})
        self.assertEqual(list(failures(self.tmp / "workflows")), ["broken"])


class BuildWorkflowSkill(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text()

    def test_it_stops_on_either_key(self):
        for key in ("`outcome`", "`standard_status`", "`build`", "`written`", "`write-standard`", "`no-fit`"):
            self.assertIn(key, self.text)

    def test_it_never_overwrites_a_workflow(self):
        self.assertIn("exists already", self.text)

    def test_it_is_done_only_when_the_check_prints_pass(self):
        self.assertIn("check_workflow.py", self.text)
        self.assertIn("python3 scripts/check_workflow.py workflows/<name>", self.text)
        self.assertIn("only when it prints `PASS`", self.text)

    def test_it_never_edits_what_it_is_checked_against(self):
        self.assertIn("Never edit the blueprint", self.text)


if __name__ == "__main__":
    unittest.main()
