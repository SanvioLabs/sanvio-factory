"""Run with: python3 -m unittest discover -s tests

scripts/workflows.py lists the workflows in a folder and shows one only in a way
it may run, and the run-workflow skill runs it first and never sends.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "workflows.py"
SKILL = ROOT / "skills" / "run-workflow" / "SKILL.md"
EXAMPLES = "examples/workflows"


def run(*args):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, str(SCRIPT)] + list(args), cwd=str(ROOT), env=env,
                          capture_output=True, text=True, timeout=60)


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir"
            for p in root.rglob("*")}


class TheExample(unittest.TestCase):
    def test_list_names_supplier_terms_with_its_owner_status_and_runs(self):
        done = run("list", "--dir", EXAMPLES)
        self.assertEqual(done.returncode, 0, done.stderr)
        owner = json.loads((ROOT / EXAMPLES / "supplier-terms" / "workflow.json").read_text())["owner"]
        self.assertIn("supplier-terms\t{}\tdraft\tchat,loop".format(owner), done.stdout.splitlines())

    def test_show_prints_paths_from_the_root(self):
        done = run("show", "supplier-terms", "--dir", EXAMPLES)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('"gate": "examples/workflows/supplier-terms/gates/supplier_terms_gate.py"', done.stdout)
        self.assertIn('"blueprint": "examples/blueprints/supplier-terms.md"', done.stdout)
        manifest = json.loads(done.stdout)
        self.assertTrue((ROOT / manifest["gate"]).is_file())
        self.assertTrue((ROOT / manifest["blueprint"]).is_file())

    def test_a_missing_name_exits_1_and_names_it(self):
        done = run("show", "no-such-workflow", "--dir", EXAMPLES)
        self.assertEqual(done.returncode, 1)
        self.assertIn("no workflow named no-such-workflow", done.stderr)
        self.assertEqual(done.stdout, "")

    def test_a_name_that_climbs_out_is_refused(self):
        done = run("show", "../supplier-terms", "--dir", EXAMPLES + "/supplier-terms")
        self.assertEqual(done.returncode, 1)
        self.assertIn("no workflow named ../supplier-terms", done.stderr)
        self.assertEqual(done.stdout, "")

    def test_it_runs_only_in_the_ways_its_runs_list(self):
        self.assertEqual(run("show", "supplier-terms", "--dir", EXAMPLES, "--as", "schedule").returncode, 1)
        self.assertEqual(run("show", "supplier-terms", "--dir", EXAMPLES, "--as", "loop").returncode, 0)

    def test_leaving_out_as_acts_as_chat(self):
        default = run("show", "supplier-terms", "--dir", EXAMPLES)
        chat = run("show", "supplier-terms", "--dir", EXAMPLES, "--as", "chat")
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(default.stdout, chat.stdout)


class TempWorkflows(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "workflows"
        self.dir.mkdir()

    def add(self, name, **fields):
        manifest = {"name": name, "owner": "Ana Ruiz, office lead", "status": "live", "runs": ["chat"],
                    "gate": "gates/{}_gate.py".format(name), "restricted_data": "none"}
        manifest.update(fields)
        (self.dir / name).mkdir()
        (self.dir / name / "workflow.json").write_text(json.dumps(manifest))

    def show(self, name, mode=None):
        args = ["show", name, "--dir", str(self.dir)] + (["--as", mode] if mode else [])
        return run(*args)

    def test_a_retired_workflow_is_refused_in_every_mode(self):
        self.add("old-quotes", status="retired", runs=["chat", "loop", "schedule"])
        for mode in ("chat", "loop", "schedule"):
            done = self.show("old-quotes", mode)
            self.assertEqual(done.returncode, 1, mode)
            self.assertIn("retired", done.stderr)
            self.assertEqual(done.stdout, "")

    def test_restricted_data_is_refused_on_a_schedule_only(self):
        self.add("payroll", runs=["chat", "schedule"], restricted_data="personal")
        scheduled = self.show("payroll", "schedule")
        self.assertEqual(scheduled.returncode, 1)
        self.assertIn("restricted data", scheduled.stderr)
        self.assertEqual(self.show("payroll", "chat").returncode, 0)

    def test_a_schedule_with_no_restricted_data_is_allowed(self):
        self.add("weekly-orders", runs=["schedule"], restricted_data="none")
        done = self.show("weekly-orders", "schedule")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["name"], "weekly-orders")

    def test_one_refusal_leaves_the_next_workflow_runnable(self):
        self.add("old-quotes", status="retired")
        self.add("new-quotes")
        self.assertEqual(self.show("old-quotes").returncode, 1)
        done = self.show("new-quotes")
        self.assertEqual(done.returncode, 0, done.stderr)
        gate = json.loads(done.stdout)["gate"]
        self.assertEqual(Path(os.path.normpath(str(ROOT / gate))), (self.dir / "new-quotes" / "gates" /
                                                                    "new-quotes_gate.py").resolve())

    def test_dir_lists_only_that_folders_workflows(self):
        self.add("new-quotes")
        done = run("list", "--dir", str(self.dir))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines(), ["new-quotes\tAna Ruiz, office lead\tlive\tchat"])

    def test_an_empty_folder_says_so_and_exits_0(self):
        done = run("list", "--dir", str(self.dir))
        self.assertEqual(done.returncode, 0)
        self.assertIn("no workflows in", done.stdout)

    def test_list_and_show_change_no_file(self):
        self.add("old-quotes", status="retired")
        self.add("new-quotes", runs=["chat", "schedule"], restricted_data="personal")
        (self.dir / "new-quotes" / "notes.md").write_text("kept as it is\n")
        before = snapshot(self.dir.parent)
        run("list", "--dir", str(self.dir))
        for name in ("old-quotes", "new-quotes", "missing"):
            for mode in ("chat", "loop", "schedule"):
                self.show(name, mode)
        self.assertEqual(snapshot(self.dir.parent), before)


class TheSkill(unittest.TestCase):
    def test_it_runs_the_script_first_and_never_sends(self):
        text = " ".join(SKILL.read_text().split())
        for words in ("scripts/workflows.py show", "never sends", "never changes an input", "never fills in"):
            self.assertIn(words, text)


if __name__ == "__main__":
    unittest.main()
