"""Run with: python3 -m unittest discover -s tests"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from link_files import link_text  # noqa: E402 (the import needs scripts/ on the path first)

FILES = {"LICENSE", "AGENTS.md", "steering/gates.md", "steering/operating.md", "skills/learn/SKILL.md"}
DIRS = {"steering", "skills", "skills/learn"}


def link(md, text):
    return link_text(md, text, FILES, DIRS)


class LinkFiles(unittest.TestCase):
    def test_a_tracked_file_becomes_a_link(self):
        self.assertEqual(link("README.md", "Read `AGENTS.md` first."),
                         ("Read [`AGENTS.md`](AGENTS.md) first.", 1))

    def test_the_link_is_relative_to_the_file(self):
        text, _ = link("steering/gates.md", "See `AGENTS.md` and `operating.md`.")
        self.assertEqual(text, "See [`AGENTS.md`](../AGENTS.md) and [`operating.md`](operating.md).")

    def test_a_folder_keeps_its_slash(self):
        self.assertEqual(link("README.md", "`skills/learn/`")[0], "[`skills/learn/`](skills/learn/)")

    def test_a_file_with_no_extension_becomes_a_link(self):
        self.assertEqual(link("README.md", "See `LICENSE`.")[0], "See [`LICENSE`](LICENSE).")

    def test_a_bare_folder_name_stays_plain(self):
        self.assertEqual(link("README.md", "the `steering` idea"), ("the `steering` idea", 0))

    def test_a_dot_stays_plain_below_the_root(self):
        text = "tmux won't take a `.` in a name, or `./`."
        self.assertEqual(link("skills/learn/SKILL.md", text), (text, 0))

    def test_a_named_folder_still_links_below_the_root(self):
        self.assertEqual(link("skills/learn/SKILL.md", "`steering/`")[0], "[`steering/`](../../steering/)")

    def test_an_untracked_name_stays_plain(self):
        self.assertEqual(link("README.md", "`company/COMPANY.md` and `.env`"), ("`company/COMPANY.md` and `.env`", 0))

    def test_another_projects_file_stays_plain(self):
        text = "A project's own `AGENTS.md` adds to these.\nRead its\n`AGENTS.md`."
        self.assertEqual(link("README.md", text), (text, 0))

    def test_code_blocks_headings_and_frontmatter_stay_plain(self):
        text = "---\ndescription: reads `AGENTS.md`\n---\n# `AGENTS.md`\n```\ncat `AGENTS.md`\n```"
        self.assertEqual(link("skills/learn/SKILL.md", text), (text, 0))

    def test_a_tilde_fence_stays_plain(self):
        text = "~~~\ncat `AGENTS.md`\n~~~"
        self.assertEqual(link("README.md", text), (text, 0))

    def test_a_backtick_fence_inside_a_tilde_block_does_not_close_it(self):
        # A ``` pair inside the block opens and closes nothing: the name after it is still code.
        text = "~~~\n```\n```\ncat `AGENTS.md`\n~~~"
        self.assertEqual(link("README.md", text), (text, 0))

    def test_running_twice_changes_nothing(self):
        once, _ = link("README.md", "Read `AGENTS.md` and `steering/`.")
        self.assertEqual(link("README.md", once), (once, 0))


class TheScript(unittest.TestCase):
    """Runs a copy of the script in a throwaway repo, so the real one is never touched."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        (self.repo / "scripts").mkdir()
        shutil.copy(ROOT / "scripts" / "link_files.py", self.repo / "scripts" / "link_files.py")
        (self.repo / "a.md").write_text("A.\n")
        self.readme = self.repo / "README.md"
        self.readme.write_text("Read `a.md`.\n")
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        self.before = self.readme.read_bytes()

    def run_script(self, *args):
        return subprocess.run([sys.executable, str(self.repo / "scripts" / "link_files.py"), *args],
                              cwd=self.repo, capture_output=True, text=True)

    def test_help_prints_usage_and_changes_nothing(self):
        result = self.run_script("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--check", result.stdout)
        self.assertEqual(self.readme.read_bytes(), self.before)

    def test_an_eval_suites_issue_stays_plain_and_other_issues_folders_still_link(self):
        # A suite's issue is posted in the run's own repo, where a link into this one would break.
        suite, other = self.repo / "suite" / "issues", self.repo / "notes" / "issues"
        suite.mkdir(parents=True)
        other.mkdir(parents=True)
        (self.repo / "suite" / "suite.json").write_text("{}\n")
        (suite / "01.md").write_text("Title\n\nEdit `a.md`.\n")
        (other / "01.md").write_text("Edit `a.md`.\n")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((suite / "01.md").read_text(), "Title\n\nEdit `a.md`.\n")
        self.assertEqual((other / "01.md").read_text(), "Edit [`a.md`](../../a.md).\n")

    def test_an_unknown_flag_stops_and_changes_nothing(self):
        result = self.run_script("--chek")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.readme.read_bytes(), self.before)


class ThisRepo(unittest.TestCase):
    """CI runs the same check. Here too, so the loop's test command catches a missing link before CI does."""

    def test_every_file_name_in_the_markdown_is_a_link(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "link_files.py"), "--check"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
