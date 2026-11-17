"""The workflow's trust tests. Run from its folder: python3 -m unittest discover -s tests"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

FOLDER = Path(__file__).resolve().parent.parent
GATE = "gates/supplier_terms_gate.py"
TEMPLATE = "templates/terms-review.md"


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
        self.assertTrue((FOLDER / "evals" / "review" / "01-obeys-planted-instruction" / "output.md").is_file())


if __name__ == "__main__":
    unittest.main()
