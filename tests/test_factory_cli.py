"""Run with: python3 -m unittest discover -s tests"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "bin" / "factory"
OLD_NAME = ROOT / "bin" / "harness"
APPROVED = "# approved\nRead\nGrep\nBash(gh pr view:*)\n"
TOOLS = "Read, Grep, Bash(gh pr view:*)"
PASSED = "Read,Grep,Bash(gh pr view:*)"  # the checked entries, as bin/factory passes them on

# Stands in for claude: writes where it ran, $SANVIO_HEADLESS and its argv, one per line.
FAKE_CLAUDE = """#!/bin/sh
{ pwd -P; printf '%s\\n' "$SANVIO_HEADLESS"; printf '%s\\n' "$@"; } > "$RECORD"
"""


def skill(root, name, extra):
    folder = root / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text("---\nname: {}\ndescription: A skill.\n{}---\n\n# {}\n".format(name, extra, name))


class FactoryCli(unittest.TestCase):
    """bin/factory copied into a fake harness, run from another folder, with a fake claude on PATH."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        tmp = Path(self.dir.name).resolve()
        self.root = tmp / "harness"
        (self.root / "bin").mkdir(parents=True)
        for script in (SCRIPT, OLD_NAME):
            shutil.copy2(script, self.root / "bin" / script.name)
            (self.root / "bin" / script.name).chmod(0o755)  # test_the_script_is_executable checks the real bits
        (self.root / "bin" / "factory-tools").write_text(APPROVED)
        skill(self.root, "x", "headless: true\nheadless-tools: {}\n".format(TOOLS))
        skill(self.root, "plain", "headless-tools: Read\n")
        fake = tmp / "fakebin"
        fake.mkdir()
        (fake / "claude").write_text(FAKE_CLAUDE)
        (fake / "claude").chmod(0o755)
        self.elsewhere = tmp / "elsewhere"
        self.elsewhere.mkdir()
        self.record = tmp / "record"
        self.env = dict(os.environ, PATH="{}{}{}".format(fake, os.pathsep, os.environ["PATH"]), RECORD=str(self.record))
        self.env.pop("SANVIO_HEADLESS", None)
        self.env.pop("HARNESS_HEADLESS", None)

    def tearDown(self):
        self.dir.cleanup()

    def run_harness(self, *args, name="factory"):
        return subprocess.run([str(self.root / "bin" / name)] + list(args), cwd=self.elsewhere,
                              env=self.env, capture_output=True, text=True, timeout=30)

    def recorded(self):
        return self.record.read_text().splitlines()

    def test_the_script_is_executable(self):
        for script in (SCRIPT, OLD_NAME):
            self.assertTrue(os.access(script, os.X_OK), "chmod +x bin/" + script.name)

    def test_the_old_name_says_so_and_runs_the_same_skill(self):
        result = self.run_harness("--json", "x", name="harness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("bin/harness is now bin/factory", result.stderr)
        self.assertEqual(result.stdout, "")
        cwd, headless, *argv = self.recorded()
        self.assertEqual((cwd, headless), (str(self.root), "1"))
        self.assertEqual(argv[:4], ["-p", "/x", "--output-format", "json"])
        linked = self.root.parent / "elsewhere" / "harness"
        linked.symlink_to(self.root / "bin" / "harness")
        through_link = subprocess.run([str(linked), "x"], cwd=self.elsewhere, env=self.env, capture_output=True,
                                      text=True, timeout=30)
        self.assertEqual(through_link.returncode, 2, "a link elsewhere finds no root, and refuses as before")
        refused = self.run_harness("plain", name="harness")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("factory: plain isn't marked headless", refused.stderr)

    def test_a_headless_skill_runs_from_the_root_with_only_its_tools(self):
        result = self.run_harness("x", "a", "b")
        self.assertEqual(result.returncode, 0, result.stderr)
        cwd, headless, *argv = self.recorded()
        self.assertEqual(cwd, str(self.root))
        self.assertEqual(headless, "1")
        self.assertEqual(argv, ["-p", "/x a b", "--permission-mode", "default", "--strict-mcp-config", "--tools",
                                "Read,Grep,Bash",
                                "--allowedTools", PASSED])

    def test_json_asks_for_json_output(self):
        result = self.run_harness("--json", "x")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded()[2:], ["-p", "/x", "--output-format", "json", "--permission-mode", "default",
                                               "--strict-mcp-config",
                                               "--tools", "Read,Grep,Bash", "--allowedTools", PASSED])

    def assert_refused(self, *args):
        result = self.run_harness(*args)
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.strip())
        self.assertFalse(self.record.exists(), "claude started")

    def test_a_skill_not_marked_headless_is_refused(self):
        self.assert_refused("plain")

    def test_a_missing_skill_is_refused(self):
        self.assert_refused("nope")

    def test_a_path_is_refused(self):
        self.assert_refused("../x")

    def test_a_name_with_a_newline_is_refused(self):
        self.assert_refused("x\nx")

    def test_a_flag_for_a_name_is_refused(self):
        self.assert_refused("-p")

    def test_no_skill_is_refused(self):
        self.assert_refused()

    def test_a_tool_the_approved_list_lacks_is_refused(self):
        skill(self.root, "wide", "headless: true\nheadless-tools: Read, Bash(git diff:*)\n")
        self.assert_refused("wide")

    def test_a_second_allowed_tools_line_is_refused(self):
        skill(self.root, "twice", "headless: true\nheadless-tools: Read\nheadless-tools: Read, Bash(rm:*)\n")
        self.assert_refused("twice")

    def test_a_key_spelled_with_a_space_still_counts_as_a_second_line(self):
        skill(self.root, "spaced", "headless: true\nheadless-tools: Read\nheadless-tools : Read, Bash(rm:*)\n")
        self.assert_refused("spaced")

    def test_an_indented_frontmatter_line_is_refused(self):
        skill(self.root, "indented", "headless: true\nheadless-tools: Read,\n  Bash(rm:*)\n")
        self.assert_refused("indented")

    def test_an_entry_that_matches_a_file_name_is_still_checked_as_written(self):
        (self.root / "Bash(gh pr view:x)").write_text("")
        skill(self.root, "glob", "headless: true\nheadless-tools: Read, Bash(gh pr view:*)\n")
        result = self.run_harness("glob")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded()[-1], "Read,Bash(gh pr view:*)")

    def test_a_folded_allowed_tools_value_is_refused(self):
        skill(self.root, "folded", "headless: true\nheadless-tools: >-\n  Read\n")
        self.assert_refused("folded")


if __name__ == "__main__":
    unittest.main()
