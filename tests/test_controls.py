"""Run with: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "controls.py"
NIST = "NIST SP 800-53 Rev. 5"
OWASP = "OWASP Top 10 for LLM Applications"


def control(ident, framework=NIST, status="core", evidence=("a.md",), **extra):
    entry = {"framework": framework, "id": ident, "name": "Name of " + ident, "status": status,
             "summary": "What " + ident + " does.", "evidence": list(evidence)}
    entry.update(extra)
    return entry


def clean_env():
    """This environment without the loop's or a hook's git settings, so git acts only on the temp repo."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return env


def run(*args, cwd=None):
    done = subprocess.run([sys.executable, str(SCRIPT)] + list(args), cwd=cwd, env=clean_env(),
                          capture_output=True, text=True)
    return done.returncode, done.stdout.splitlines()


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        for name in ("a.md", "b.md"):
            (self.dir / name).write_text("x\n")
        (self.dir / "docs").mkdir()

    def check(self, entries, name="fixture.json"):
        path = self.dir / name
        path.write_text(json.dumps(entries))
        return run("check", "--file", str(path))

    def test_a_good_register_passes_with_its_name_and_count(self):
        code, out = self.check([control("AC-5", evidence=("a.md", "docs/")), control("AU-9", evidence=("b.md",))])
        self.assertEqual((code, out), (0, ["fixture.json: 2 controls, all evidence present"]))

    def test_each_missing_path_gets_a_line_with_its_control(self):
        code, out = self.check([control("AC-5", evidence=("a.md", "gone.md")), control("AU-9", evidence=("lost/",))])
        self.assertEqual(code, 1)
        self.assertEqual(len(out), 2, out)
        self.assertIn("AC-5", out[0])
        self.assertIn("gone.md", out[0])
        self.assertIn("AU-9", out[1])
        self.assertIn("lost/", out[1])

    def test_each_missing_field_fails_naming_the_entry(self):
        for field in ("name", "status", "summary", "evidence"):
            with self.subTest(field=field):
                entry = control("AC-5")
                del entry[field]
                code, out = self.check([entry])
                self.assertEqual(code, 1)
                self.assertTrue(any(NIST + " AC-5" in line and field in line for line in out), out)

    def test_a_missing_id_or_framework_names_the_entry_by_its_place(self):
        for field in ("id", "framework"):
            with self.subTest(field=field):
                entry = control("AU-9")
                del entry[field]
                code, out = self.check([control("AC-5"), entry])
                self.assertEqual(code, 1)
                self.assertTrue(any("entry 2" in line and field in line for line in out), out)

    def test_an_empty_evidence_list_fails(self):
        code, out = self.check([control("AC-5", evidence=())])
        self.assertEqual(code, 1)
        self.assertTrue(any("AC-5" in line and "evidence" in line for line in out), out)

    def test_an_unknown_status_fails(self):
        code, out = self.check([control("AC-5", status="partial")])
        self.assertEqual(code, 1)
        self.assertTrue(any("AC-5" in line and "partial" in line for line in out), out)

    def test_every_listed_status_passes(self):
        for status in ("core", "configured", "gap-customer", "gap-limit", "enhancement", "na"):
            with self.subTest(status=status):
                code, out = self.check([control("AC-5", status=status, setup="Turn it on.")])
                self.assertEqual(code, 0, out)

    def test_configured_without_setup_fails(self):
        code, out = self.check([control("AC-5", status="configured")])
        self.assertEqual(code, 1)
        self.assertTrue(any("AC-5" in line and "setup" in line for line in out), out)

    def test_an_id_repeated_within_one_framework_fails(self):
        code, out = self.check([control("AC-5"), control("AC-5", evidence=("b.md",))])
        self.assertEqual(code, 1)
        self.assertTrue(any("AC-5" in line and "repeats" in line for line in out), out)

    def test_one_id_in_two_frameworks_passes(self):
        code, out = self.check([control("prompt-injection"), control("prompt-injection", framework=OWASP)])
        self.assertEqual((code, out), (0, ["fixture.json: 2 controls, all evidence present"]))

    def test_a_folder_written_without_a_slash_fails(self):
        code, out = self.check([control("AC-5", evidence=("docs",))])
        self.assertEqual(code, 1)
        self.assertTrue(any("AC-5" in line and "docs" in line and "trailing /" in line for line in out), out)

    def test_a_file_written_with_a_slash_fails(self):
        code, out = self.check([control("AC-5", evidence=("a.md/",))])
        self.assertEqual(code, 1)
        self.assertTrue(any("AC-5" in line and "a.md/" in line and "isn't a folder" in line for line in out), out)

    def test_a_path_outside_the_register_folder_fails_even_when_it_exists(self):
        (self.dir / "outside.md").write_text("x\n")
        (self.dir / "inner").mkdir()
        code, out = self.check([control("AC-5", evidence=("../outside.md",))], name="inner/fixture.json")
        self.assertEqual(code, 1)
        self.assertTrue(any("AC-5" in line and "../outside.md" in line and "outside" in line for line in out), out)

    def test_the_shipped_register_passes(self):
        code, out = run("check", cwd=ROOT)
        self.assertEqual((code, out), (0, ["controls.json: 5 controls, all evidence present"]))


class Touched(unittest.TestCase):
    REGISTER = [
        control("file", evidence=("AGENTS.md",)),
        control("folder", evidence=("scripts/",)),
        control("old", evidence=("old.md",)),
        control("new", evidence=("new.md",)),
    ]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        (self.repo / "controls.json").write_text(json.dumps(self.REGISTER))
        (self.repo / "scripts").mkdir()
        for name in ("AGENTS.md", "old.md", "README.md", "scripts/loop.py", "scripts/other.py"):
            (self.repo / name).write_text("x\n")
        self.commit("base")
        self.git("checkout", "-q", "-b", "change")

    def git(self, *args):
        identity = ["-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false"]
        subprocess.run(["git"] + identity + list(args), cwd=self.repo, env=clean_env(), check=True,
                       capture_output=True)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def edit(self, *names):
        for name in names:
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("changed\n")
        self.commit("change")

    def touched(self):
        return run("touched", "main", "--file", str(self.repo / "controls.json"))

    def test_a_changed_file_names_its_control(self):
        self.edit("AGENTS.md")
        self.assertEqual(self.touched(), (0, [NIST + " file"]))

    def test_a_change_under_a_folder_names_its_control(self):
        self.edit("scripts/loop.py")
        self.assertEqual(self.touched(), (0, [NIST + " folder"]))

    def test_a_rename_names_the_controls_of_both_names(self):
        self.git("mv", "old.md", "new.md")
        self.commit("rename")
        self.assertEqual(self.touched(), (0, [NIST + " old", NIST + " new"]))

    def test_a_sibling_path_matches_nothing(self):
        self.edit("scriptsX/loop.py", "AGENTS.md.bak")
        self.assertEqual(self.touched(), (0, ["none"]))

    def test_an_unrelated_change_prints_none(self):
        self.edit("README.md")
        self.assertEqual(self.touched(), (0, ["none"]))

    def test_each_control_is_named_once_in_register_order(self):
        self.edit("scripts/other.py", "scripts/loop.py", "AGENTS.md")
        self.assertEqual(self.touched(), (0, [NIST + " file", NIST + " folder"]))

    def test_a_missing_register_says_so_and_passes(self):
        with tempfile.TemporaryDirectory() as empty:
            code, out = run("touched", "main", "--file", str(Path(empty) / "controls.json"), cwd=empty)
        self.assertEqual((code, out), (0, ["no controls.json"]))

    def test_with_no_file_it_reads_the_register_of_the_repo_it_runs_in(self):
        self.edit("scripts/loop.py")
        self.assertEqual(run("touched", "main", cwd=self.repo / "scripts"), (0, [NIST + " folder"]))

    def test_with_no_file_in_a_repo_without_a_register_it_never_reads_the_factorys(self):
        (self.repo / "controls.json").unlink()
        self.edit("AGENTS.md", "scripts/loop.py")
        self.assertEqual(run("touched", "main", cwd=self.repo), (0, ["no controls.json"]))

    def test_with_no_file_check_reads_the_register_at_the_git_root(self):
        (self.repo / "controls.json").write_text(json.dumps([control("only", evidence=("AGENTS.md",))]))
        self.assertEqual(run("check", cwd=self.repo / "scripts"),
                         (0, ["controls.json: 1 control, all evidence present"]))


class ReviewPrSkill(unittest.TestCase):
    def test_review_pr_lists_the_controls_a_change_touches(self):
        text = (ROOT / "skills" / "review-pr" / "SKILL.md").read_text()
        self.assertIn("python3 scripts/controls.py touched origin/<base>", text)
        self.assertIn("Controls touched:", text)


if __name__ == "__main__":
    unittest.main()
