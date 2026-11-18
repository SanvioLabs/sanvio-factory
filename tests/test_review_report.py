"""Run with: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import review_report  # noqa: E402 (the import needs scripts/ on the path first)

SCHEMA_PATH = ROOT / "skills" / "review-pr" / "report.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())
FINDING = {"file": "src/app.py", "line": 12, "severity": "blocks", "rule": "AGENTS.md: Rules",
           "summary": "Catches every exception and drops it."}


def report(verdict="changes needed", findings=(FINDING,), **more):
    return json.dumps(dict({"verdict": verdict, "findings": list(findings)}, **more))


def without(key):
    return {name: value for name, value in FINDING.items() if name != key}


class LoadAndRender(unittest.TestCase):
    def test_a_valid_report_loads_and_renders(self):
        loaded = review_report.load(report(), SCHEMA)
        self.assertEqual(loaded["verdict"], "changes needed")
        text = review_report.render(loaded)
        lines = text.strip().splitlines()
        self.assertIn("didn't run the tests", lines[0])
        self.assertIn("- **blocks** src/app.py:12 (AGENTS.md: Rules): Catches every exception and drops it.", lines)
        self.assertEqual(lines[-1], "Verdict: changes needed")

    def test_a_finding_without_a_line_and_no_findings_both_render(self):
        loaded = review_report.load(report("ready with nits", [dict(without("line"), severity="nit")]), SCHEMA)
        self.assertIn("- **nit** src/app.py (AGENTS.md: Rules): ", review_report.render(loaded))
        loaded = review_report.load(report("ready", []), SCHEMA)
        self.assertIn("No findings.", review_report.render(loaded))
        self.assertTrue(review_report.render(loaded).strip().endswith("Verdict: ready"))

    def test_a_finding_without_a_rule_does_not_load(self):
        self.assertIsNone(review_report.load(report(findings=[without("rule")]), SCHEMA))

    def test_a_severity_the_schema_does_not_allow_does_not_load(self):
        self.assertIsNone(review_report.load(report(findings=[dict(FINDING, severity="major")]), SCHEMA))

    def test_text_that_is_not_json_does_not_load(self):
        for text in ("Looks fine.\n\nVERDICT: ready\n", "", "{", "[" * 100000):
            self.assertIsNone(review_report.load(text, SCHEMA), text[:40])

    def test_a_key_the_schema_does_not_list_does_not_load(self):
        self.assertIsNone(review_report.load(report(grade=10), SCHEMA))
        self.assertIsNone(review_report.load(report(findings=[dict(FINDING, image="x")]), SCHEMA))

    def test_wrong_types_and_bounds_do_not_load(self):
        for bad in ([dict(FINDING, line=0)], [dict(FINDING, line=True)], [dict(FINDING, line="12")],
                    [dict(FINDING, file="")], [dict(FINDING, summary=None)], ["a finding"]):
            self.assertIsNone(review_report.load(report(findings=bad), SCHEMA), bad)
        self.assertIsNone(review_report.load(report(verdict="ready, ship it"), SCHEMA))
        self.assertIsNone(review_report.load(json.dumps({"verdict": "ready", "findings": {}}), SCHEMA))
        self.assertIsNone(review_report.load(json.dumps(["ready"]), SCHEMA))

    def test_one_json_fence_comes_off_and_nothing_else(self):
        self.assertIsNotNone(review_report.load("```json\n" + report() + "\n```\n", SCHEMA))
        for text in ("```\n" + report() + "\n```", "Here it is:\n```json\n" + report() + "\n```",
                     "```json\n```json\n" + report() + "\n```\n```"):
            self.assertIsNone(review_report.load(text, SCHEMA), text[:30])


class Clean(unittest.TestCase):
    def test_a_mention_html_and_a_script_are_defused(self):
        loaded = review_report.load(report(findings=[dict(FINDING, summary="@octocat <img src=x> <script>")]),
                                    SCHEMA)
        text = review_report.render(loaded)
        for gone in ("@octocat", "<img", "<script"):
            self.assertNotIn(gone, text)
        self.assertIn("octocat &lt;img src=x&gt; &lt;script&gt;", text)

    def test_an_email_address_is_left_as_it_is(self):
        self.assertEqual(review_report.clean("write to a@b.com"), "write to a@b.com")
        self.assertEqual(review_report.clean("cc @team/leads and (@octocat)"), "cc team/leads and (octocat)")
        for field in ("@@octocat", "x @@@octocat", "é@octocat", "&@octocat"):
            self.assertNotRegex(review_report.clean(field), r"(?<![A-Za-z0-9_])@[A-Za-z0-9]", field)

    def test_ampersands_go_first_so_escapes_are_not_doubled(self):
        self.assertEqual(review_report.clean("a & b < c > d"), "a &amp; b &lt; c &gt; d")
        self.assertEqual(review_report.clean("Vec<String>"), "Vec&lt;String&gt;")

    def test_images_and_line_breaks_are_broken(self):
        self.assertEqual(review_report.clean("![x](https://e.example/a)"), "! [x](https://e.example/a)")
        for field in ("one\n## Heading", "one\r\n<!-- review-pr-report -->", "one\r---", "one two"):
            self.assertEqual(len(review_report.clean(field).splitlines()), 1, repr(field))

    def test_every_model_written_field_is_cleaned(self):
        loud = "@octocat\n<b>![i](x)"
        finding = {"file": loud, "line": 1, "severity": "nit", "rule": loud, "summary": loud}
        text = review_report.render({"verdict": "ready", "findings": [finding]})
        for gone in ("@octocat", "<b>", "!["):
            self.assertNotIn(gone, text)
        self.assertEqual(len([line for line in text.splitlines() if line.startswith("- ")]), 1)


class Schema(unittest.TestCase):
    def test_every_keyword_in_the_schema_is_one_the_validator_handles(self):
        used = review_report.keywords(SCHEMA)
        self.assertTrue(used)
        self.assertLessEqual(used, set(review_report.SUPPORTED))

    def test_a_keyword_the_validator_does_not_handle_is_refused(self):
        with self.assertRaises(review_report.Unsupported):
            review_report.validate("x", {"type": "string", "pattern": "^x$"})
        with self.assertRaises(review_report.Unsupported):
            review_report.validate({"a": "x"}, {"properties": {"a": {"maxLength": 0}}})
        self.assertIsNone(review_report.load('"x"', {"type": "string", "format": "email"}))

    def test_the_schema_is_the_shape_the_ticket_names(self):
        self.assertIs(SCHEMA["additionalProperties"], False)
        self.assertEqual(sorted(SCHEMA["required"]), ["findings", "verdict"])
        self.assertEqual(SCHEMA["properties"]["verdict"]["enum"], ["ready", "ready with nits", "changes needed"])
        item = SCHEMA["properties"]["findings"]["items"]
        self.assertIs(item["additionalProperties"], False)
        self.assertEqual(sorted(item["required"]), ["file", "rule", "severity", "summary"])
        self.assertEqual(item["properties"]["severity"]["enum"], ["blocks", "nit"])
        self.assertEqual(item["properties"]["line"], {"type": "integer", "minimum": 1})


class Main(unittest.TestCase):
    def run_main(self, text, planted=None):
        """Run review_report.py as the workflow does, from a workspace whose harness/ holds it and the schema,
        with `planted` as a report.schema.json under head/ and base/. Returns the result and report.md."""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "harness" / "scripts").mkdir(parents=True)
            (ws / "harness" / "skills" / "review-pr").mkdir(parents=True)
            (ws / "harness" / "scripts" / "review_report.py").write_text(
                (ROOT / "scripts" / "review_report.py").read_text())
            (ws / "harness" / "skills" / "review-pr" / "report.schema.json").write_text(SCHEMA_PATH.read_text())
            if planted is not None:
                for folder in ("head", "base"):
                    (ws / folder / "skills" / "review-pr").mkdir(parents=True)
                    (ws / folder / "skills" / "review-pr" / "report.schema.json").write_text(planted)
            temp = ws / "temp"
            temp.mkdir()
            if text is not None:
                (temp / "report.json").write_text(text)
            result = subprocess.run([sys.executable, "harness/scripts/review_report.py"], cwd=ws,
                                    env={"PATH": os.environ["PATH"], "RUNNER_TEMP": str(temp)},
                                    capture_output=True, text=True)
            out = temp / "report.md"
            return result, out.read_text() if out.exists() else None

    def test_a_valid_report_becomes_the_comment(self):
        result, text = self.run_main(report())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("src/app.py:12", text)
        self.assertEqual(text.strip().splitlines()[-1], "Verdict: changes needed")

    def test_an_unreadable_report_posts_only_the_could_not_be_read_line(self):
        secret_ish = "Leaky summary text"
        for text in ("Looks fine.\n" + secret_ish, report(findings=[dict(FINDING, severity="major",
                                                                       summary=secret_ish)]), None):
            result, md = self.run_main(text)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(md, review_report.UNREADABLE + "\n")
            self.assertNotIn(secret_ish, result.stdout + result.stderr)
        self.assertEqual(review_report.UNREADABLE,
                         "The review's report couldn't be read, so no findings are posted.")

    def test_a_schema_under_head_or_base_changes_nothing(self):
        # Valid only under the planted schema, which allows anything: the factory's own still refuses it.
        planted = '{"type": "object"}'
        bad = json.dumps({"verdict": "ship it", "findings": "none", "note": "@octocat"})
        self.assertIsNotNone(review_report.load(bad, json.loads(planted)))
        result, md = self.run_main(bad, planted=planted)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(md, review_report.UNREADABLE + "\n")


if __name__ == "__main__":
    unittest.main()
