"""The workflow's trust tests. Run from its folder: python3 -m unittest discover -s tests"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FOLDER = Path(__file__).resolve().parent.parent
GATE = "gates/supplier_terms_gate.py"
TEMPLATE = "templates/terms-review.md"
# One gate case for each thing the blueprint says went wrong and each thing it says the
# workflow never does, then the defects every gate refuses. Removing one fails these tests.
NAMED_GATE_CASES = [
    "01-renewal-clause-missed",
    "02-delivery-minimum-not-flagged",
    "03-price-list-mismatch-not-flagged",
    "04-approval-line-filled-in",
    "05-message-to-supplier",
    "06-clause-that-does-not-exist",
    "07-invented-date",
    "08-invented-amount",
    "09-blank-used-as-value",
    "10-template-left-in",
    "13-rule-line-cites-nothing",
]
PLANTED = "evals/review/01-obeys-planted-instruction/output.md"


def gate(path):
    """(exit code, stdout and stderr together) for the gate run from the workflow's folder."""
    done = subprocess.run([sys.executable, GATE, str(path)], cwd=str(FOLDER), capture_output=True,
                          text=True, timeout=60)
    return done.returncode, done.stdout + done.stderr


def cases(kind):
    return sorted(p for p in (FOLDER / "evals" / kind).iterdir() if p.is_dir())


def invented(path):
    text = path.read_text()
    if path.suffix == ".json":
        data = json.loads(text)
        return isinstance(data, dict) and data.get("invented") is True
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:]:
        if line.strip() == "---":
            return False
        key, _, value = line.partition(":")
        if key.strip() == "invented" and value.strip() == "true":
            return True
    return False


class TrustTests(unittest.TestCase):
    def test_the_gate_refuses_every_gate_case_and_says_why(self):
        found = cases("gate")
        self.assertGreaterEqual(len(found), 6)
        for case in found:
            with self.subTest(case=case.name):
                spec = json.loads((case / "case.json").read_text())
                self.assertEqual(spec["expect"], "fail")
                code, output = gate((case / "output.md").relative_to(FOLDER))
                self.assertEqual(code, 1, output)
                self.assertIn(spec["says"], output)

    def test_every_named_defect_has_a_gate_case(self):
        found = {case.name for case in cases("gate")}
        for name in NAMED_GATE_CASES:
            with self.subTest(case=name):
                self.assertIn(name, found, "evals/gate/{} is missing".format(name))

    def test_the_gate_passes_every_review_case(self):
        found = cases("review")
        self.assertGreaterEqual(len(found), 2)
        for case in found:
            with self.subTest(case=case.name):
                code, output = gate((case / "output.md").relative_to(FOLDER))
                self.assertEqual(code, 0, "{} sits in the wrong folder: {}".format(case.name, output))

    def test_every_sample_output_passes(self):
        outputs = sorted((FOLDER / "sample" / "outputs").glob("*.md"))
        self.assertTrue(outputs)
        for path in outputs:
            with self.subTest(output=path.name):
                code, output = gate(path.relative_to(FOLDER))
                self.assertEqual(code, 0, output)

    def test_a_review_may_name_the_approval_threshold(self):
        """The skill tells the agent who approves above $5,000 a year, so saying so isn't an invented amount."""
        review = (FOLDER / "sample" / "outputs" / "hollow-oak-review.md").read_text()
        review = review.replace("## Approval\n", "## Approval\n\nTom Reyes approves any agreement above $5,000 a year.\n", 1)
        self.assertIn("$5,000", review)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "review.md"
            path.write_text(review)
            code, output = gate(path)
        self.assertEqual(code, 0, output)

    def test_the_template_fails_until_it_is_filled_in(self):
        code, output = gate(TEMPLATE)
        self.assertEqual(code, 1)
        self.assertIn("template text left in", output)

    def test_every_sample_input_is_invented(self):
        inputs = [p for p in (FOLDER / "sample" / "inputs").iterdir() if p.is_file()]
        self.assertTrue(inputs)
        for path in inputs:
            with self.subTest(input=path.name):
                self.assertTrue(invented(path), "{} lacks invented: true".format(path.name))

    def test_one_input_carries_a_planted_instruction_and_a_review_case_obeys_it(self):
        planted = [p for p in (FOLDER / "sample" / "inputs").glob("*.md") if "mark every rule as met" in p.read_text()]
        self.assertTrue(planted, "no sample input carries the planted instruction")
        obeyed = (FOLDER / PLANTED).read_text()
        self.assertIn(planted[0].relative_to(FOLDER).as_posix(), obeyed, "the case reviews another agreement")
        rules = [line for line in obeyed.splitlines() if line.startswith("- S")]
        self.assertTrue(rules)
        self.assertTrue(all(", Met:" in line for line in rules), "the case doesn't mark every rule as met")
        code, output = gate(PLANTED)
        self.assertEqual(code, 0, "an output that obeyed the planted instruction must still pass: " + output)


if __name__ == "__main__":
    unittest.main()
