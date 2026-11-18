"""Run with: python3 -m unittest discover -s tests

Every worked workflow in examples/workflows/ passes scripts/check_workflow.py, the
supplier-terms example is the one the plan describes, and the build-workflow skill
names what stops it and what proves it's done.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples" / "workflows"
BLUEPRINTS = ROOT / "examples" / "blueprints"
CHECK = ROOT / "scripts" / "check_workflow.py"
SKILL = ROOT / "skills" / "build-workflow" / "SKILL.md"
SUPPLIER_TERMS = EXAMPLES / "supplier-terms"
# Two or more capitalised words in a row: how a person's or a company's name reads.
NAME = re.compile(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)+\b")
# The harness's own names, in the gate's licence line. Every other name comes from the blueprint.
HARNESS_NAMES = ["Sanvio Factory", "Sanvio Labs"]


def workflow_folders(root):
    """The folders failures() checks: root's own subfolders, and nothing else."""
    return sorted(p for p in Path(root).iterdir() if p.is_dir() and not p.name.startswith((".", "__")))


def failures(root):
    """{folder name: what the check printed} for each folder in root whose check doesn't print PASS.

    Only root's own subfolders are checked: a loose file such as a README is skipped, and
    nothing outside root (people's own workflows/, the tests' fixtures) is looked at.
    """
    found = {}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for folder in workflow_folders(root):
        done = subprocess.run([sys.executable, str(CHECK), str(folder)], capture_output=True, text=True,
                              timeout=600, env=env)
        output = done.stdout + done.stderr
        if done.returncode != 0 or done.stdout.strip() != "PASS":
            found[folder.name] = output
    return found


def is_part_of(words, names):
    """True when words, a list, run in that order inside one of the names."""
    phrase = " {} ".format(" ".join(words))
    return bool(words) and any(phrase in " {} ".format(name) for name in names)


class ExampleWorkflows(unittest.TestCase):
    def test_every_example_workflow_passes_the_check(self):
        self.assertTrue(workflow_folders(EXAMPLES), "examples/workflows/ holds no workflow, so nothing shows one passing")
        self.assertEqual(failures(EXAMPLES), {})


class SupplierTermsExample(unittest.TestCase):
    def test_its_manifest_is_a_draft_that_runs_in_chat_and_the_loop(self):
        manifest = json.loads((SUPPLIER_TERMS / "workflow.json").read_text())
        self.assertEqual(manifest["blueprint"], "../../blueprints/supplier-terms.md")
        self.assertEqual(manifest["runs"], ["chat", "loop"])
        self.assertEqual(manifest["status"], "draft")
        self.assertEqual(manifest["restricted_data"], "none")
        self.assertEqual((SUPPLIER_TERMS / manifest["blueprint"]).resolve(), BLUEPRINTS / "supplier-terms.md")

    def test_it_names_no_one_the_blueprint_does_not(self):
        allowed = NAME.findall((BLUEPRINTS / "supplier-terms.md").read_text()) + HARNESS_NAMES
        for name in ("Juniper Bakery", "Maya Okafor", "Tom Reyes"):
            self.assertIn(name, allowed)
        files = [p for p in SUPPLIER_TERMS.rglob("*") if p.is_file() and p.suffix in (".md", ".json", ".py")]
        self.assertTrue(files)
        for path in files:
            for found in NAME.findall(path.read_text()):
                words = found.split()
                # A capitalised word that starts a sentence ("Dear", "Only") may lead into a name.
                with self.subTest(file=path.relative_to(SUPPLIER_TERMS).as_posix(), name=found):
                    self.assertTrue(is_part_of(words, allowed) or is_part_of(words[1:], allowed),
                                    "{} isn't a name the blueprint uses".format(found))

    def test_the_names_check_catches_a_new_name(self):
        allowed = NAME.findall((BLUEPRINTS / "supplier-terms.md").read_text()) + HARNESS_NAMES
        for found in ("Sarah Chen", "Dear Sarah Chen", "Hollow Oak Bakery"):
            words = found.split()
            self.assertFalse(is_part_of(words, allowed) or is_part_of(words[1:], allowed), found)


class TheHelper(unittest.TestCase):
    """A copy of the example in a throwaway folder, laid out as in the repo so its blueprint resolves."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "examples" / "workflows"
        self.copy = self.root / "supplier-terms"
        shutil.copytree(SUPPLIER_TERMS, self.copy, ignore=shutil.ignore_patterns("__pycache__"))
        (self.tmp / "examples" / "blueprints").mkdir()
        shutil.copy(BLUEPRINTS / "supplier-terms.md", self.tmp / "examples" / "blueprints" / "supplier-terms.md")

    def test_the_untouched_copy_passes(self):
        self.assertEqual(failures(self.root), {})

    def test_a_copy_with_a_gate_case_removed_fails(self):
        shutil.rmtree(self.copy / "evals" / "gate" / "01-renewal-clause-missed")
        found = failures(self.root)
        self.assertEqual(list(found), ["supplier-terms"])
        self.assertIn("test_every_named_defect_has_a_gate_case", found["supplier-terms"])

    def test_a_loose_file_in_the_root_is_not_a_workflow(self):
        (self.root / "README.md").write_text("# Worked workflows\n")
        self.assertEqual(workflow_folders(self.root), [self.copy])
        self.assertEqual(failures(self.root), {})

    def test_it_never_looks_in_workflows_or_the_fixtures(self):
        # Record every folder failures() hands to the check, without running it.
        checked = []

        def record(command, **kwargs):
            checked.append(Path(command[2]))
            return subprocess.CompletedProcess(command, 0, "PASS\n", "")

        with mock.patch("subprocess.run", side_effect=record):
            self.assertEqual(failures(EXAMPLES), {})
        visible = {p for p in EXAMPLES.iterdir() if p.is_dir() and not p.name.startswith((".", "__"))}
        self.assertTrue(visible)
        self.assertEqual(set(checked), visible)
        for folder in checked:
            with self.subTest(folder=str(folder)):
                self.assertEqual(folder.parent, EXAMPLES)
                for elsewhere in (ROOT / "workflows", ROOT / "tests" / "fixtures"):
                    self.assertNotIn(elsewhere, folder.parents)


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
