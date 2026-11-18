"""Run with: python3 -m unittest discover -s tests"""
import itertools
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop  # noqa: E402 (the import needs scripts/ on the path first)
import review_grade  # noqa: E402
import test_review_pr_reusable as reusable  # noqa: E402 (the import needs tests/ on the path first)
import test_review_pr_workflow as single  # noqa: E402

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

    def test_the_skill_grades_with_the_loops_own_command(self):
        # The skill doesn't apply the rubric itself: it runs the command the loop grades with, so a hand-run
        # review gets the grade the loop and CI would give. The reasons live in loop.py, tested there.
        self.assertIn('python3 scripts/loop.py grade <n> --verdict "<verdict>"', self.flat)
        self.assertIn("Don't apply the rubric yourself", self.flat)
        args = loop.build_parser().parse_args(["grade", "42", "--verdict", "ready with nits"])
        self.assertEqual((args.command, args.pr, args.verdict), ("grade", 42, "ready with nits"))
        self.assertIn("--project projects/<name>", self.flat)

    def test_the_skill_writes_no_grade_when_the_prompt_names_the_last_line(self):
        self.assertIn("no grade line", self.flat)
        for path in (ROOT / "scripts" / "loop.py", ROOT / ".github" / "workflows" / "review-pr.yml"):
            self.assertIn("Its last line is its verdict", path.read_text(), path.name)

    def test_headless_runs_get_no_gh_pr_checks(self):
        headless = next(line for line in self.text.splitlines() if line.startswith("headless-tools:"))
        self.assertNotIn("gh pr checks", headless)

    def test_the_rubric_comes_from_the_factory_root_only(self):
        # The command runs from the factory's root, found from the skill's own path, and the rubric it reads is
        # the factory's, never the repo under review's.
        self.assertIn("the root is three levels above the resolved file", self.flat)
        self.assertIn("never one from the repo under review", self.flat)
        # A rubric in the working folder, never the link to the factory's own (../../review-rubric.json).
        self.assertNotRegex(self.flat, r"(?<![./])\./review-rubric\.json")


class TheWorstVerdictGrades(unittest.TestCase):
    """CI grades the worst of its agents' verdicts, and an agent without a report can't raise it."""

    steps = reusable.ReusableReviewWorkflow.steps
    step = single.ReviewPrWorkflow.step
    run_in = reusable.ReusableReviewWorkflow.run_in
    grade = reusable.GradeTheReview.grade
    assertGrade = reusable.GradeTheReview.assertGrade

    def setUp(self):
        self.code = single.code(reusable.WORKFLOW.read_text())

    def test_the_order_runs_from_unreadable_to_ready(self):
        self.assertEqual(review_grade.WORST_FIRST, ("unreadable", "changes needed", "ready with nits", "ready"))
        self.assertEqual(set(review_grade.WORST_FIRST), set(VERDICTS) | {"unreadable"})

    def test_worst_of_every_pair(self):
        order = review_grade.WORST_FIRST
        for first, second in itertools.product(order, repeat=2):
            expected = order[min(order.index(first), order.index(second))]
            self.assertEqual(review_grade.worst([first, second]), expected, (first, second))

    def test_worst_of_none_or_an_unknown_verdict_is_unreadable(self):
        self.assertEqual(review_grade.worst([]), "unreadable")
        self.assertEqual(review_grade.worst(["ready", "looks good"]), "unreadable")
        self.assertEqual(review_grade.worst(["ready"]), "ready")

    def test_ready_and_changes_needed_grade_changes_needed(self):
        self.assertGrade(None, "Verdict: changes needed. Grade 3/10: changes needed, checks passing.",
                         reports={"review-pr": "Fine.\n\nVERDICT: ready\n",
                                  "security-reviewer": "A finding.\n\nVERDICT: changes needed\n"},
                         names="review-pr,security-reviewer")

    def test_a_listed_agent_with_no_report_grades_unreadable(self):
        self.assertGrade(None, "Verdict: unreadable. Grade 2/10: the verdict is unreadable.",
                         reports={"review-pr": "Fine.\n\nVERDICT: ready\n"}, names="review-pr,security-reviewer")
        self.assertGrade(None, "Verdict: unreadable. Grade 2/10: the verdict is unreadable.", names="review-pr")

    def test_every_listed_agent_with_a_report_grades_as_its_reports_do(self):
        self.assertGrade(None, "Verdict: ready with nits. Grade 8/10: ready with nits, checks passing.",
                         reports={"review-pr": "VERDICT: ready\n", "cto": "VERDICT: ready with nits\n"},
                         names="review-pr,cto")

    def test_one_report_md_grades_as_it_always_has(self):
        for report, line in (("Ready.\n\nVERDICT: ready\n", "Verdict: ready. Grade 10/10: ready, checks passing."),
                             ("VERDICT: changes needed\n",
                              "Verdict: changes needed. Grade 3/10: changes needed, checks passing."),
                             ("Fine.\n", "Verdict: unreadable. Grade 2/10: the verdict is unreadable.")):
            self.assertGrade(report, line)

    def test_reports_win_over_report_md(self):
        self.assertGrade("VERDICT: changes needed\n", "Verdict: ready. Grade 10/10: ready, checks passing.",
                         reports={"review-pr": "VERDICT: ready\n"})


if __name__ == "__main__":
    unittest.main()
