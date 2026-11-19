"""Run with: python3 -m unittest discover -s tests"""
import contextlib
import io
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import quick_check  # noqa: E402 (the import needs scripts/ on the path first)

PASSES = [sys.executable, "-c", "pass"]
# It reports on stderr, as unittest does, so its output only shows if stderr is kept.
FAILS = [sys.executable, "-c", "import sys; sys.stderr.write('it broke here\\n'); sys.exit(1)"]
WARNS = [sys.executable, "-c", "print('PASS fine'); print('WARN mods: older'); print('     note: run this'); "
         "print('PASS also fine')"]


def run(parts):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = quick_check.main([], parts=parts)
    return code, out.getvalue()


class QuickCheck(unittest.TestCase):
    def test_a_failing_part_doesnt_stop_the_others_and_fails_the_run(self):
        code, out = run([("first", PASSES), ("broken", FAILS), ("last", PASSES)])
        self.assertEqual(code, 1)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("PASS first"))
        self.assertTrue(any(line.startswith("FAIL broken") for line in lines))
        self.assertTrue(any(line.startswith("PASS last") for line in lines))
        self.assertIn("it broke here", out)
        self.assertRegex(lines[-1], r"^2 of 3 parts passed in \d+\.\d seconds$")

    def test_every_part_passing_exits_0(self):
        code, out = run([("one", PASSES), ("two", PASSES)])
        self.assertEqual(code, 0)
        self.assertRegex(out.splitlines()[-1], r"^2 of 2 parts passed in \d+\.\d seconds$")

    def test_a_passing_part_shows_its_warnings_and_nothing_else(self):
        code, out = run([("setup", WARNS)])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("PASS setup"))
        self.assertIn("WARN mods: older", out)
        self.assertIn("note: run this", out)
        self.assertNotIn("fine", out)

    def test_a_command_that_cant_start_fails_its_part(self):
        code, out = run([("gone", [str(ROOT / "no-such-command")]), ("after", PASSES)])
        self.assertEqual(code, 1)
        self.assertIn("FAIL gone", out)
        self.assertIn("PASS after", out)


class Parts(unittest.TestCase):
    def test_each_module_is_a_test_file(self):
        for module in quick_check.MODULES:
            with self.subTest(module=module):
                self.assertTrue((ROOT / "tests" / (module + ".py")).is_file())

    def test_it_doesnt_run_its_own_tests(self):
        self.assertNotIn("test_quick_check", quick_check.MODULES)

    def test_it_runs_the_setup_check_the_link_check_and_the_modules(self):
        commands = [" ".join(command) for _, command in quick_check.default_parts()]
        self.assertTrue(any(re.search(r"scripts/check_setup\.py$", command) for command in commands))
        self.assertTrue(any(command.endswith("scripts/link_files.py --check") for command in commands))
        tests = [command for _, command in quick_check.default_parts() if "unittest" in command]
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0][-len(quick_check.MODULES):], ["tests." + m for m in quick_check.MODULES])

    def test_help_prints_usage_and_runs_no_part(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "quick_check.py"), "--help"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout)
        self.assertNotIn("parts passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
