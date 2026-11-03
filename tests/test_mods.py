"""Run with: python3 -m unittest discover -s tests"""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
MODS_DIR = ROOT / "examples" / "mods"
MODS = sorted(p for p in MODS_DIR.iterdir() if (p / ".claude-plugin" / "plugin.json").is_file())
TIMEOUT = 60
NEEDS_CLAUDE = "needs Claude Code (claude) on the PATH"
FAIL = "(fail) "
TEST_FILE = (".test.ts:", ".test.tsx:")
SUMMARY = re.compile(r" \d+ (pass|fail|skip|todo)")
MAX_ERROR_LINES = 30


def failures(output):
    """Each failing test in output with its file and error, then the summary. None when nothing failed."""
    lines = output.splitlines()
    kept = []
    header = None
    given = set()
    for i, line in enumerate(lines):
        if not line.startswith(" ") and line.endswith(TEST_FILE):
            header = i
            continue
        if not line.startswith(FAIL):
            continue
        if header is not None and header not in given:
            kept.append(lines[header])
            given.add(header)
        kept.append(line)
        end = i + 1
        while end < len(lines) and (lines[end].startswith("  ") or not lines[end].strip()):
            end += 1
        block = lines[i + 1:end]
        while block and not block[-1].strip():
            block.pop()
        dropped = len(block) - MAX_ERROR_LINES
        if dropped > 0:
            block = block[:MAX_ERROR_LINES] + ["  … {} more line{}".format(dropped, "" if dropped == 1 else "s")]
        kept.extend(block)
    if not kept:
        return None
    kept.extend(line for line in lines if SUMMARY.fullmatch(line) or line.startswith("Ran "))
    return "\n".join(kept)


def check_mod(folder):
    """Validate and test the mod in folder. None when both pass, else why not."""
    for verb in ("validate", "test"):
        command = ["claude", "plugin", verb, folder.name]
        try:
            result = subprocess.run(command, cwd=folder.parent, capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return "claude plugin {} {} didn't finish within {}s".format(verb, folder.name, TIMEOUT)
        if result.returncode != 0:
            output = result.stdout + result.stderr
            report = failures(output) if verb == "test" else None
            if report is None:
                report = "\n".join(output.splitlines()[-40:])
            return "{} failed (exit {}):\n{}".format(" ".join(command), result.returncode, report)
    return None


class Mods(unittest.TestCase):
    """Each mod under examples/mods/ validates and passes its own tests."""

    def setUp(self):
        if not shutil.which("claude"):
            self.skipTest(NEEDS_CLAUDE)


def add_mod_test(folder):
    def test(self):
        failure = check_mod(folder)
        self.assertIsNone(failure, failure)
    setattr(Mods, "test_" + folder.name.replace("-", "_"), test)


for _folder in MODS:
    add_mod_test(_folder)


class CheckModCatchesFailures(unittest.TestCase):
    """check_mod passes a mod as shipped, and fails one whose test fails."""

    def setUp(self):
        if not shutil.which("claude"):
            self.skipTest(NEEDS_CLAUDE)
        self.copy = Path(tempfile.mkdtemp()) / "harness-lens"
        self.addCleanup(shutil.rmtree, self.copy.parent)
        shutil.copytree(MODS_DIR / "harness-lens", self.copy)

    def test_a_mod_as_shipped_passes(self):
        self.assertIsNone(check_mod(self.copy))

    def test_a_failing_test_is_reported(self):
        with open(self.copy / "hooks" / "logic.test.ts", "a") as tests:
            tests.write("\ndescribe('broken', () => {\n"
                        "  test('deliberately fails', () => expect(1).toBe(2))\n})\n")
        failure = check_mod(self.copy)
        self.assertIsNotNone(failure, "check_mod passed a mod with a failing test")
        self.assertIn("harness-lens", failure)
        self.assertIn("deliberately fails", failure)


ERROR_LINES = [
    "  error: expect(received).toBe(expected)",
    "  Expected: 2",
    "  Received: 1",
]
PASS_LINES = ["(pass) b > ok {} [0.1ms]".format(n) for n in range(60)]
SUMMARY_LINES = [" 60 pass", " 1 fail", "Ran 61 tests across 2 files. [0.2s]"]
HIDDEN_FAILURE = "\n".join(
    ["hooks/a.test.ts:", "(fail) a > broken [0.1ms]"] + ERROR_LINES
    + ["hooks/b.test.ts:"] + PASS_LINES + SUMMARY_LINES) + "\n"


def with_errors(count):
    """One failing test followed by count error lines."""
    errors = ["  line {}".format(n) for n in range(count)]
    return "\n".join(["hooks/a.test.ts:", "(fail) a > broken"] + errors)


class Failures(unittest.TestCase):
    """failures() keeps each failing test, its file and its error, and the summary."""

    def test_a_failure_hidden_above_many_passes_is_kept(self):
        report = failures(HIDDEN_FAILURE)
        self.assertIn("(fail) a > broken [0.1ms]", report)
        self.assertIn("hooks/a.test.ts:", report)
        for line in ERROR_LINES + SUMMARY_LINES:
            self.assertIn(line, report)
        self.assertNotIn("hooks/b.test.ts:", report)
        self.assertNotIn("(pass)", report)

    def test_a_file_with_two_failures_is_named_once(self):
        output = "\n".join([
            "hooks/a.test.ts:",
            "(fail) a > one", "  error one",
            "(pass) a > fine",
            "(fail) a > two", "  error two",
        ])
        report = failures(output)
        self.assertEqual(report.count("hooks/a.test.ts:"), 1)
        self.assertEqual(report.splitlines(), [
            "hooks/a.test.ts:", "(fail) a > one", "  error one", "(fail) a > two", "  error two"])

    def test_failures_in_two_files_name_each_file_once_in_order(self):
        output = "\n".join([
            "hooks/a.test.ts:", "(fail) a > one", "  error one",
            "hooks/b.test.ts:", "(fail) b > two", "  error two",
        ])
        report = failures(output)
        self.assertEqual(report.count("hooks/a.test.ts:"), 1)
        self.assertEqual(report.count("hooks/b.test.ts:"), 1)
        self.assertLess(report.index("hooks/a.test.ts:"), report.index("hooks/b.test.ts:"))
        self.assertLess(report.index("(fail) a > one"), report.index("hooks/b.test.ts:"))

    def test_a_long_error_is_cut_at_30_lines(self):
        lines = failures(with_errors(35)).splitlines()
        self.assertEqual(lines[2:32], ["  line {}".format(n) for n in range(30)])
        self.assertEqual(lines[32:], ["  … 5 more lines"])

    def test_one_line_over_says_one_more_line(self):
        self.assertTrue(failures(with_errors(31)).endswith("  line 29\n  … 1 more line"))

    def test_exactly_30_lines_has_no_marker(self):
        report = failures(with_errors(30))
        self.assertNotIn("more line", report)
        self.assertTrue(report.endswith("  line 29"))

    def test_blank_lines_after_an_error_are_dropped(self):
        output = "\n".join([
            "hooks/a.test.ts:",
            "(fail) a > broken [0.2ms]",
            "  error: expect(received).toBe(expected)",
            "",
            "  Expected: 2",
            "  Received: 1",
            "",
            " 49 pass",
            " 1 fail",
        ])
        self.assertEqual(failures(output).splitlines(), [
            "hooks/a.test.ts:",
            "(fail) a > broken [0.2ms]",
            "  error: expect(received).toBe(expected)",
            "",
            "  Expected: 2",
            "  Received: 1",
            " 49 pass",
            " 1 fail",
        ])

    def test_an_indented_test_file_line_is_not_a_header(self):
        output = "\n".join(["  hooks/a.test.ts:", "(fail) a > broken", "  error"])
        self.assertEqual(failures(output).splitlines(), ["(fail) a > broken", "  error"])

    def test_a_tsx_file_is_a_header(self):
        output = "\n".join(["ui/pane.test.tsx:", "(fail) pane > draws", "  error"])
        self.assertEqual(failures(output).splitlines()[0], "ui/pane.test.tsx:")

    def test_nothing_failed_gives_none(self):
        self.assertIsNone(failures("\n".join(["hooks/b.test.ts:"] + PASS_LINES + [" 60 pass", " 0 fail"])))

    def test_fail_partway_through_a_line_gives_none(self):
        self.assertIsNone(failures("hooks/a.test.ts:\nsee (fail) a > broken above\n 0 fail"))


def completed(code, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout, stderr=stderr)


class CheckModReport(unittest.TestCase):
    """check_mod reports failing tests by name, and the tail of everything else."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp()) / "demo"
        self.addCleanup(shutil.rmtree, self.folder.parent)
        self.folder.mkdir()

    def check(self, *results):
        with mock.patch("subprocess.run", side_effect=list(results)) as run:
            report = check_mod(self.folder)
        return report, run

    def test_a_failing_test_is_reported_by_name(self):
        report, _ = self.check(completed(0), completed(1, HIDDEN_FAILURE))
        first, rest = report.split("\n", 1)
        self.assertEqual(first, "claude plugin test demo failed (exit 1):")
        self.assertEqual(rest, failures(HIDDEN_FAILURE))

    def test_a_failure_with_no_test_named_keeps_the_last_40_lines(self):
        output = "\n".join("output line {}".format(n) for n in range(50))
        report, _ = self.check(completed(0), completed(1, output))
        tail = "\n".join(output.splitlines()[-40:])
        self.assertEqual(report, "claude plugin test demo failed (exit 1):\n" + tail)

    def test_a_validate_failure_keeps_the_last_40_lines(self):
        output = "\n".join(["(fail) not a test"] + ["output line {}".format(n) for n in range(50)])
        report, run = self.check(completed(1, output), completed(0))
        tail = "\n".join(output.splitlines()[-40:])
        self.assertEqual(report, "claude plugin validate demo failed (exit 1):\n" + tail)
        self.assertEqual(run.call_count, 1)

    def test_a_short_validate_failure_with_a_fail_line_is_not_parsed(self):
        output = "hooks/a.test.ts:\n(fail) a > broken\n  error\nhooks/b.test.ts:\n(pass) b > ok"
        report, run = self.check(completed(1, output), completed(0))
        self.assertNotEqual(failures(output), output)
        self.assertEqual(report, "claude plugin validate demo failed (exit 1):\n" + output)
        self.assertEqual(run.call_count, 1)

    def test_a_timeout_is_reported(self):
        report, _ = self.check(completed(0), subprocess.TimeoutExpired(cmd="claude", timeout=TIMEOUT))
        self.assertEqual(report, "claude plugin test demo didn't finish within 60s")

    def test_both_passing_gives_none(self):
        report, run = self.check(completed(0), completed(0))
        self.assertIsNone(report)
        self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
