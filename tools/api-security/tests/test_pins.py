"""SPEC-034 REQ-022, AC-013: at hardened, every third-party action in the security and deploy
workflows is pinned to a full commit SHA."""
import json
import unittest

import _path  # noqa: F401  (imported for its sys.path side effect)
import fixture

from api_security import pins

PINNED = "steps:\n  - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n"
TAGGED = "steps:\n  - uses: actions/checkout@v4\n"
LOCAL = "steps:\n  - uses: ./.github/actions/setup\n  - uses: docker://alpine:3.20\n"


def project(deploy_text, hardened=True):
    root = fixture.project(extra={
        ".github/workflows/security-check.yml": PINNED,
        ".github/workflows/security-approval.yml": PINNED,
        ".github/workflows/deploy.yml": deploy_text,
    })
    cfg_path = root / "security" / "config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg.update(hardened=hardened, deploy_workflows=[".github/workflows/deploy.yml"])
    cfg_path.write_text(json.dumps(cfg))
    return root


class PinTests(unittest.TestCase):
    def test_a_tag_pin_is_reported(self):
        root = project(TAGGED)
        found = pins.unpinned(root, [".github/workflows/deploy.yml"])
        self.assertEqual(len(found), 1)
        self.assertIn("actions/checkout@v4", found[0])

    def test_sha_pins_and_local_actions_pass(self):
        root = project(PINNED + LOCAL.replace("steps:\n", ""))
        self.assertEqual(pins.unpinned(root, [".github/workflows/deploy.yml"]), [])

    def test_hardened_check_fails_on_a_tag_and_passes_on_a_sha(self):
        r = fixture.run_check(project(TAGGED))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("actions/checkout@v4", r.stdout)
        r = fixture.run_check(project(PINNED))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_below_hardened_the_pin_check_does_not_run(self):
        r = fixture.run_check(project(TAGGED, hardened=False))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_listed_workflow_that_is_missing_fails(self):
        root = project(PINNED)
        (root / ".github" / "workflows" / "deploy.yml").unlink()
        r = fixture.run_check(root)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
