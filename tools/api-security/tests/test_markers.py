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


if __name__ == "__main__":
    unittest.main()
