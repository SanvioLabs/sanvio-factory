"""SPEC-034 REQ-015, AC-008: the public surface against the checked-in snapshot."""
import unittest

import _path  # noqa: F401  (imported for its sys.path side effect)
import fixture

NEW_PUBLIC = fixture.HANDLERS + '''
@router.route("GET /v1/consent/terms/{code}")
@public(reason="consent page")
def terms(event, identity):
    return {"statusCode": 200}
'''
NEW_TF = fixture.TERRAFORM + 'resource "aws_apigatewayv2_route" "t" {\n  route_key = "GET /v1/consent/terms/{code}"\n}\n'


class SnapshotTests(unittest.TestCase):
    def test_a_new_public_route_without_a_snapshot_update_fails(self):
        r = fixture.run_check(fixture.project(handlers=NEW_PUBLIC, terraform=NEW_TF))
        self.assertEqual(r.returncode, 1)
        self.assertIn("+ GET /v1/consent/terms/{code}", r.stdout)

    def test_update_snapshot_writes_it_and_then_passes(self):
        root = fixture.project(handlers=NEW_PUBLIC, terraform=NEW_TF)
        r = fixture.run_check(root, "--update-snapshot")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (root / "security" / "public-routes.txt").read_text()
        self.assertIn("GET /v1/consent/terms/{code}", text)
        self.assertEqual(fixture.run_check(root).returncode, 0)

    def test_a_missing_snapshot_fails(self):
        r = fixture.run_check(fixture.project(snapshot=None))
        self.assertNotEqual(r.returncode, 0)

    def test_comments_and_blank_lines_in_the_snapshot_are_ignored(self):
        r = fixture.run_check(fixture.project(snapshot="# public routes\n\nGET /v1/health\n"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_route_in_the_snapshot_that_is_no_longer_public_fails(self):
        r = fixture.run_check(fixture.project(snapshot="GET /v1/health\nGET /v1/gone\n"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("- GET /v1/gone", r.stdout)

    def test_a_semgrepignore_fails_the_check(self):
        # review-spec, 2026-11-06 (T035): an ignore file can hide every handler from the scan.
        root = fixture.project(extra={".semgrepignore": "app/\n"})
        r = fixture.run_check(root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(".semgrepignore", r.stdout)


    def test_a_nested_semgrepignore_fails_the_check(self):
        # Security re-review 3, 2026-11-06: semgrep honours an ignore file in any folder.
        root = fixture.project(extra={"app/.semgrepignore": "handlers.py\n"})
        r = fixture.run_check(root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("app/.semgrepignore", r.stdout)

    def test_a_handler_module_semgrep_skips_by_default_fails_the_check(self):
        # Security re-review, 2026-11-06: semgrep skips tests/, build/, dist/, vendor/ and the like
        # with no ignore file at all, so a handler there would never be scanned.
        root = fixture.project(handler_modules=["app.tests.handlers"])
        (root / "app" / "tests").mkdir()
        (root / "app" / "tests" / "__init__.py").write_text("")
        (root / "app" / "handlers.py").rename(root / "app" / "tests" / "handlers.py")
        r = fixture.run_check(root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("app/tests/handlers.py", r.stdout)

if __name__ == "__main__":
    unittest.main()
