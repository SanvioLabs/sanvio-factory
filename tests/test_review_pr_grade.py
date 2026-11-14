"""Run with: python3 -m unittest discover -s tests"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import loop  # noqa: E402 (the import needs scripts/ on the path first)

SKILL = ROOT / "skills" / "review-pr" / "SKILL.md"
VERDICTS = ("ready", "ready with nits", "changes needed")


def output_lines(text):
    """The lines of the ```text fence that holds the line starting `Verdict: <`."""
    for block in re.findall(r"^[ \t]*```text\n(.*?)^[ \t]*```", text, re.S | re.M):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if any(line.startswith("Verdict: <") for line in lines):
            return lines
    raise AssertionError("SKILL.md has no ```text fence holding a `Verdict: <` line")


def expanded(template):
    """One line for each verdict the template's <a | b | c> names."""
    found = re.search(r"<([^>]*)>", template)
    return [template[:found.start()] + choice.strip() + template[found.end():] for choice in found.group(1).split("|")]


class HandRunGrade(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text()
        self.flat = " ".join(self.text.split())
        lines = output_lines(self.text)
        self.verdict = next(line for line in lines if line.startswith("Verdict: <"))
        self.grades = [line.replace("<n>", "8").replace("<reason>", "ready, checks passing")
                       for line in lines if line.startswith("Grade ")]

    def test_the_fence_names_the_three_verdicts_and_two_grade_lines(self):
        self.assertEqual([line[len("Verdict: "):-1] for line in expanded(self.verdict)], list(VERDICTS))
        self.assertEqual(self.grades, ["Grade 8/10: ready, checks passing.", "Grade pending: checks still running."])

    def test_the_verdict_line_alone_is_read(self):
        for line, verdict in zip(expanded(self.verdict), VERDICTS):
            self.assertEqual(loop.report_verdict("## Review\n\nFindings.\n\n" + line + "\n"), verdict, line)

    def test_a_grade_line_above_the_verdict_leaves_it_readable(self):
        for line, verdict in zip(expanded(self.verdict), VERDICTS):
            for grade in self.grades:
                report = "## Review\n\nFindings.\n\n{}\n{}\n".format(grade, line)
                self.assertEqual(loop.report_verdict(report), verdict, report)

    def test_a_grade_line_last_is_unreadable(self):
        for grade in self.grades:
            self.assertEqual(loop.report_verdict("## Review\n\n" + grade + "\n"), "unreadable", grade)

    def test_a_grade_after_the_verdict_on_one_line_is_unreadable(self):
        report = "## Review\n\nVerdict: ready. Grade 10/10: ready, checks passing.\n"
        self.assertEqual(loop.report_verdict(report), "unreadable")

    def test_the_skill_names_each_reason(self):
        for reason in ("a check failed", "the verdict is unreadable", "checks still running",
                       "checks passing", "no checks ran"):
            self.assertIn(reason, self.flat)

    def test_the_skill_writes_no_grade_when_the_prompt_names_the_last_line(self):
        self.assertIn("no grade line", self.flat)
        for path in (ROOT / "scripts" / "loop.py", ROOT / ".github" / "workflows" / "review-pr.yml"):
            self.assertIn("Its last line is its verdict", path.read_text(), path.name)

    def test_headless_runs_get_no_gh_pr_checks(self):
        headless = next(line for line in self.text.splitlines() if line.startswith("headless-tools:"))
        self.assertNotIn("gh pr checks", headless)

    def test_the_rubric_comes_from_the_factory_root_only(self):
        self.assertIn("<root>/review-rubric.json", self.flat)
        self.assertNotIn("./review-rubric.json", self.flat)


if __name__ == "__main__":
    unittest.main()
