"""Run with: python3 -m unittest discover -s tests"""
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_blueprint.py"
EXAMPLE = ROOT / "examples" / "blueprints" / "supplier-terms.md"

# Every key from *The blueprint* in docs/building-workflows.md, in its order, with a made-up answer.
BASE = [
    ("name", "invoice-match"),
    ("owner", "Dana Whitfield, finance lead"),
    ("trigger", "A supplier invoice arrives in the accounts inbox"),
    ("inputs", "The invoice as a PDF, the purchase order, the delivery note"),
    ("inputs_live", "The accounts inbox, the ordering system"),
    ("frequency", "About forty a week"),
    ("rules", "The matching policy in the finance handbook, section 2"),
    ("standard_status", "written"),
    ("output", "A match report: matched, or each line that differs"),
    ("done", "The approver can pay or query in one read"),
    ("does", "Dana Whitfield"),
    ("approves", "Lee Moreno, above $2,000"),
    ("receives", "Accounts payable"),
    ("went_wrong", "A credit note paid as an invoice, a duplicate invoice paid twice"),
    ("never", "Pay anything, change an invoice"),
    ("today", "Ten minutes an invoice"),
    ("measure", "Minutes an invoice"),
    ("systems", "Email, the ordering system, the accounting software"),
    ("incumbent", "none"),
    ("restricted_data", "none"),
    ("outcome", "build"),
    ("gaps", ""),
]


def blueprint(fields):
    lines = ["---"] + ["{}: {}".format(key, value).rstrip() for key, value in fields] + ["---", "",
                                                                                        "The walkthrough.", ""]
    return "\n".join(lines)


def changed(fields, key, value):
    return [(k, value if k == key else v) for k, v in fields]


def without(fields, key):
    return [(k, v) for k, v in fields if k != key]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CheckBlueprint(unittest.TestCase):
    """Each test writes a blueprint into <tmp>/blueprints/ from BASE, breaks one thing and runs the script."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name) / "blueprints"
        self.folder.mkdir()

    def write(self, fields, name="invoice-match", text=None):
        path = self.folder / (name + ".md")
        path.write_text(blueprint(fields) if text is None else text, encoding="utf-8")
        return path

    def check(self, *args):
        """(exit code, its lines) for the script run with these arguments."""
        done = subprocess.run([sys.executable, str(SCRIPT)] + [str(a) for a in args],
                              capture_output=True, text=True, timeout=60)
        return done.returncode, (done.stdout + done.stderr).splitlines()

    def assertFails(self, path, *texts):
        code, lines = self.check(path)
        self.assertEqual(code, 1, lines)
        self.assertNotIn("PASS", lines)
        joined = "\n".join(lines)
        for text in texts:
            self.assertIn(text, joined)
        return lines

    def test_the_base_passes(self):
        code, lines = self.check(self.write(BASE))
        self.assertEqual((code, lines), (0, ["PASS"]))

    def test_a_missing_key_fails(self):
        for key, _ in BASE:
            with self.subTest(key=key):
                self.assertFails(self.write(without(BASE, key)), key + ": missing")

    def test_an_empty_key_not_in_gaps_fails(self):
        self.assertFails(self.write(changed(BASE, "owner", "")), "owner: empty and not named in gaps")

    def test_an_empty_key_named_in_gaps_passes(self):
        fields = changed(changed(BASE, "measure", ""), "gaps", "measure")
        code, lines = self.check(self.write(fields))
        self.assertEqual((code, lines), (0, ["PASS"]))

    def test_two_empty_keys_named_in_gaps_pass(self):
        fields = changed(changed(changed(BASE, "measure", ""), "today", ""), "gaps", "today, measure")
        code, lines = self.check(self.write(fields))
        self.assertEqual((code, lines), (0, ["PASS"]))

    def test_a_key_in_gaps_with_a_value_fails(self):
        self.assertFails(self.write(changed(BASE, "gaps", "today")), "today: named in gaps but has a value")

    def test_a_gaps_item_that_isnt_a_key_fails(self):
        fields = changed(changed(BASE, "measure", ""), "gaps", "meausre")
        self.assertFails(self.write(fields), "gaps: meausre isn't a blueprint key", "measure: empty")

    def test_a_name_that_isnt_the_file_name_fails(self):
        self.assertFails(self.write(BASE, name="invoice-matching"), "name: invoice-match", "invoice-matching")

    def test_a_standard_status_outside_the_list_fails(self):
        for value in ("draft", "", "Written"):
            with self.subTest(value=value):
                self.assertFails(self.write(changed(BASE, "standard_status", value)), "standard_status:")

    def test_an_outcome_outside_the_list_fails(self):
        for value in ("maybe", "", "Build"):
            with self.subTest(value=value):
                self.assertFails(self.write(changed(BASE, "outcome", value)), "outcome:")

    def test_standard_status_and_outcome_are_never_gaps(self):
        fields = changed(changed(changed(BASE, "standard_status", ""), "outcome", ""), "gaps",
                         "standard_status, outcome")
        self.assertFails(self.write(fields), "standard_status:", "outcome:")

    def test_no_frontmatter_fails(self):
        self.assertFails(self.write(BASE, text="# Invoice match\n\nname: invoice-match\n"), "no frontmatter")

    def test_unclosed_frontmatter_fails(self):
        text = blueprint(BASE).replace("---\n\nThe walkthrough.", "\nThe walkthrough.")
        self.assertFails(self.write(BASE, text=text), "no frontmatter")

    def test_two_problems_are_both_named(self):
        fields = changed(without(BASE, "systems"), "outcome", "later")
        lines = self.assertFails(self.write(fields), "systems: missing", "outcome:")
        self.assertEqual(len(lines), 2, lines)

    def test_a_value_with_a_colon_is_kept_whole(self):
        code, lines = self.check(self.write(changed(BASE, "today", "Ten minutes: more at month end")))
        self.assertEqual((code, lines), (0, ["PASS"]))

    def test_extra_keys_are_allowed(self):
        code, lines = self.check(self.write(BASE + [("notes", "Asked twice")]))
        self.assertEqual((code, lines), (0, ["PASS"]))

    def test_no_argument_prints_usage_and_exits_2(self):
        code, lines = self.check()
        self.assertEqual(code, 2)
        self.assertIn("usage", "\n".join(lines))

    def test_the_example_passes(self):
        code, lines = self.check(EXAMPLE)
        self.assertEqual((code, lines), (0, ["PASS"]))

    def test_the_example_is_a_build_with_written_rules_and_no_gaps(self):
        text = EXAMPLE.read_text(encoding="utf-8")
        for line in ("standard_status: written", "outcome: build", "restricted_data: none"):
            self.assertIn("\n" + line + "\n", text)
        self.assertRegex(text, r"\ngaps:[ ]*\n")

    # What it must not touch.

    def test_a_run_leaves_the_file_as_it_was(self):
        good = self.write(BASE)
        bad = self.write(changed(BASE, "outcome", "later"), name="broken")
        for path, code in ((good, 0), (bad, 1)):
            with self.subTest(path=path.name):
                before = digest(path)
                self.assertEqual(self.check(path)[0], code)
                self.assertEqual(digest(path), before)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["broken.md", "invoice-match.md"])

    def test_a_broken_blueprint_beside_a_good_one_doesnt_change_its_result(self):
        good = self.write(BASE)
        alone = self.check(good)
        self.write(without(BASE, "owner"), name="broken")
        self.write(changed(BASE, "name", "invoice-match"), name="other")
        self.assertEqual(self.check(good), alone)
        self.assertEqual(alone, (0, ["PASS"]))

    def test_the_examples_name_matches_its_own_file_not_another(self):
        copy = self.write(BASE, name="invoice-match", text=EXAMPLE.read_text(encoding="utf-8"))
        self.assertFails(copy, "name: supplier-terms", "invoice-match")
        self.assertEqual(self.check(EXAMPLE), (0, ["PASS"]))


if __name__ == "__main__":
    unittest.main()
