"""SPEC-034 REQ-002, REQ-003, REQ-004, REQ-007, REQ-019, REQ-024, AC-001, AC-002: apply.py copies
exactly what a level needs, stamps the version, and never lowers a level by accident."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _path

APPLY = _path.TOOL / "apply.py"

IDENTITY = """repo:
  github: "o/example"
  branch: "main"

workspace:
  type: "product"
  live_users: false
"""

GATES = """gates:
  repo_baseline:
    description: "Verify repo meets security and quality baseline"
    requires:
      - file_exists: ".gitignore"

  deploy_ready:
    description: "Ready for production deployment"
    requires:
      - gate: repo_baseline
"""


def repo(files=None, identity=IDENTITY, gates=GATES):
    root = Path(tempfile.mkdtemp(prefix="apply-"))
    (root / "pyproject.toml").write_text('[project]\nname = "x"\n')
    if identity is not None:
        (root / ".studio-project.yaml").write_text(identity)
    if gates is not None:
        (root / ".gates.yaml").write_text(gates)
    (root / "AGENTS.md").write_text("# Agents\n\nExisting guidance.\n")
    for rel, text in (files or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


def apply(root, *args):
    return subprocess.run([sys.executable, str(APPLY), *args, str(root)], capture_output=True, text=True)


def level(root):
    for line in (root / ".studio-project.yaml").read_text().splitlines():
        if line.strip().startswith("security_level:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None


class ApplyTests(unittest.TestCase):
    def test_off_and_absent_add_nothing(self):
        root = repo()
        before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
        r = apply(root, "--level", "off")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual((root / ".gates.yaml").read_text(), GATES)

    def test_guided_copies_only_the_language_rules_and_points_agents_at_them(self):
        root = repo()
        r = apply(root, "--level", "guided")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(level(root), "guided")
        rules = root / ".claude" / "rules" / "api-security-python.md"
        self.assertTrue(rules.is_file())
        self.assertTrue(rules.read_text().startswith("---\npaths:"))
        self.assertFalse((root / ".claude" / "rules" / "api-security-typescript.md").exists())
        self.assertFalse((root / "security").exists())
        self.assertIn(".claude/rules/api-security-python.md", (root / "AGENTS.md").read_text())
        self.assertIn("Existing guidance.", (root / "AGENTS.md").read_text())
        self.assertEqual((root / ".gates.yaml").read_text(), GATES)

    def test_enforced_adds_the_check_workflows_snapshot_version_and_gates(self):
        root = repo()
        r = apply(root, "--level", "enforced")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for rel in ("security/__init__.py", "security/api_security/check.py",
                    "security/api_security/verify_approval.py", "security/semgrep/identity-from-request.yml",
                    "security/public-routes.txt", "security/allowed_signers", "security/config.json",
                    "security/fixtures.py", "security/VERSION",
                    ".github/workflows/security-check.yml", ".github/workflows/security-approval.yml"):
            self.assertTrue((root / rel).is_file(), rel)
        self.assertFalse((root / "security" / "semgrep" / "identity-from-request.py").exists(),
                         "the rule's own test fixtures stay in the harness")
        self.assertEqual((root / "security" / "VERSION").read_text().strip(),
                         (_path.TOOL / "VERSION").read_text().strip())
        gates = (root / ".gates.yaml").read_text()
        self.assertIn('file_exists: "security/allowed_signers"', gates)
        self.assertIn("python3 -m security.api_security.check", gates)
        self.assertFalse(json.loads((root / "security" / "config.json").read_text()).get("hardened"))

    def test_enforced_keeps_files_the_holder_already_filled_in(self):
        root = repo({"security/allowed_signers": "owner@example.com ssh-ed25519 AAAA\n",
                     "security/public-routes.txt": "GET /v1/health\n"})
        apply(root, "--level", "enforced")
        self.assertIn("owner@example.com", (root / "security" / "allowed_signers").read_text())
        self.assertIn("GET /v1/health", (root / "security" / "public-routes.txt").read_text())

    def test_running_twice_does_not_duplicate(self):
        root = repo()
        apply(root, "--level", "enforced")
        apply(root, "--level", "enforced")
        gates = (root / ".gates.yaml").read_text()
        self.assertEqual(gates.count('file_exists: "security/allowed_signers"'), 1)
        self.assertEqual((root / "AGENTS.md").read_text().count("api-security:start"), 1)

    def test_hardened_sets_the_flag_and_the_hold_paths(self):
        root = repo()
        r = apply(root, "--level", "hardened")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads((root / "security" / "config.json").read_text())["hardened"])
        self.assertTrue((root / "security" / "hold-paths.txt").read_text().strip())

    def test_lowering_needs_the_flag(self):
        root = repo()
        apply(root, "--level", "enforced")
        r = apply(root, "--level", "guided")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(level(root), "enforced")
        r = apply(root, "--level", "guided", "--lower")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(level(root), "guided")
        self.assertNotIn("security/allowed_signers", (root / ".gates.yaml").read_text())
        self.assertTrue((root / "security").is_dir(), "lowering never deletes security/")

    def test_lowering_to_off_removes_the_rules_and_the_agents_block(self):
        root = repo()
        apply(root, "--level", "guided")
        r = apply(root, "--level", "off", "--lower")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((root / ".claude" / "rules" / "api-security-python.md").exists())
        self.assertNotIn("api-security", (root / "AGENTS.md").read_text())
        self.assertIn("Existing guidance.", (root / "AGENTS.md").read_text())

    def test_an_unrecognised_current_level_counts_as_off(self):
        root = repo(identity=IDENTITY + '  security_level: "maximum"\n')
        r = apply(root, "--level", "guided")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(level(root), "guided")

    def test_an_unknown_target_level_is_refused(self):
        r = apply(repo(), "--level", "maximum")
        self.assertNotEqual(r.returncode, 0)

    def test_enforced_needs_a_python_implementation(self):
        root = repo()
        (root / "pyproject.toml").unlink()
        (root / "package.json").write_text("{}")
        r = apply(root, "--level", "enforced")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("python", (r.stdout + r.stderr).lower())

    def test_no_identity_file_is_refused(self):
        r = apply(repo(identity=None), "--level", "guided")
        self.assertNotEqual(r.returncode, 0)

    def test_enforced_without_a_gates_file_is_refused(self):
        r = apply(repo(gates=None), "--level", "enforced")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(".gates.yaml", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
