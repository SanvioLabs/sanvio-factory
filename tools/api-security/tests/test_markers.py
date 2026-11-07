"""SPEC-034 REQ-013, AC-007: an allowlist marker for the identity rules must carry a reason."""
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401  (imported for its sys.path side effect)

from api_security import markers

RULE = "api-security.identity-from-request.python"


def tree(files):
    root = Path(tempfile.mkdtemp(prefix="markers-"))
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


class MarkerTests(unittest.TestCase):
    def test_a_marker_with_a_reason_passes(self):
        root = tree({"app/h.py": f'x = body["user_id"]  # nosemgrep: {RULE} -- echoed back only\n'})
        self.assertEqual(markers.unreasoned(root), [])

    def test_a_marker_without_a_reason_fails(self):
        for line in (f'x = 1  # nosemgrep: {RULE}\n', f'x = 1  # nosemgrep: {RULE} --   \n'):
            root = tree({"app/h.py": line})
            found = markers.unreasoned(root)
            self.assertEqual(len(found), 1, line)
            self.assertIn("app/h.py:1", found[0])

    def test_a_bare_nosemgrep_silences_every_rule_and_fails(self):
        root = tree({"app/h.ts": "const u = req.body.userId; // nosemgrep\n"})
        self.assertEqual(len(markers.unreasoned(root)), 1)

    def test_markers_for_other_rules_are_not_its_business(self):
        root = tree({"app/h.py": "x = 1  # nosemgrep: some.other-rule\n"})
        self.assertEqual(markers.unreasoned(root), [])

    def test_dependency_folders_are_skipped(self):
        root = tree({"node_modules/x/h.js": "a // nosemgrep\n", ".venv/lib/h.py": "a # nosemgrep\n"})
        self.assertEqual(markers.unreasoned(root), [])

    def test_main_exits_non_zero_on_a_finding(self):
        root = tree({"app/h.py": f"x = 1  # nosemgrep: {RULE}\n"})
        self.assertEqual(markers.main(["--root", str(root)]), 1)
        self.assertEqual(markers.main(["--root", str(tree({"a.py": "x = 1\n"}))]), 0)

    # review-spec, 2026-11-06 (T035): every spelling semgrep honours is held to the same rule.

    def test_every_spelling_semgrep_honours_needs_a_reason(self):
        qualified = "security.semgrep." + RULE
        for line in ("x = 1  # nosem\n", "x = 1  # NOSEMGREP\n", "x = 1  # nosemgrep -- because\n",
                     f"x = 1  # nosemgrep: other-rule, {RULE}\n", f"x = 1  # nosemgrep: other-rule {RULE}\n",
                     f"x = 1  # nosemgrep: {qualified}\n", f"x = 1  # NoSem: {RULE}\n"):
            with self.subTest(line=line):
                self.assertEqual(len(markers.unreasoned(tree({"app/h.py": line}))), 1)

    def test_the_qualified_id_ci_prints_passes_with_a_reason(self):
        line = f"x = 1  # nosemgrep: security.semgrep.{RULE} -- echoed back only\n"
        self.assertEqual(markers.unreasoned(tree({"app/h.py": line})), [])

    def test_folders_semgrep_scans_are_scanned_here_too(self):
        # Security re-review 3, 2026-11-06: semgrep reads venv/, .terraform/ and any folder named
        # semgrep, so a bare marker there silenced it while this check looked away.
        root = tree({"venv/h.py": "a # nosem\n", ".terraform/h.py": "a # nosem\n",
                     "src/semgrep/h.py": "a # nosem\n", "security/semgrep/rule.py": "a # nosem\n"})
        found = sorted(f.split(":")[0] for f in markers.unreasoned(root))
        self.assertEqual(found, [".terraform/h.py", "src/semgrep/h.py", "venv/h.py"])

    def test_bin_and_obj_are_scanned_and_the_librarys_own_copy_is_not(self):
        root = tree({"bin/run.py": "a # nosemgrep\n", "obj/x.cs": "a // nosemgrep\n",
                     "security/api_security/markers.py": "NOSEMGREP = 'nosemgrep'\n"})
        found = markers.unreasoned(root)
        self.assertEqual(sorted(f.split(":")[0] for f in found), ["bin/run.py", "obj/x.cs"])


if __name__ == "__main__":
    unittest.main()
