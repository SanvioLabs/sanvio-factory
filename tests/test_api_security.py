"""API security levels: the steering, the tool, and the setup check's report.

Run with: python3 -m unittest discover -s tests
The tool's own suite is tools/api-security/tests, run as its own CI step.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "api-security"
sys.path.insert(0, str(ROOT / "scripts"))
import check_setup  # noqa: E402 (the import needs scripts/ on the path first)


def project(root, name, workspace):
    d = root / "projects" / name
    d.mkdir(parents=True)
    (d / ".studio-project.yaml").write_text('repo:\n  github: "o/r"\n\nworkspace:\n' + workspace)
    return d


class ApiSecurity(unittest.TestCase):
    def test_the_steering_and_the_tool_ship(self):
        self.assertTrue((ROOT / "steering" / "api-security.md").is_file())
        for rel in ("apply.py", "VERSION", "rules/python.md", "workflows/security-approval.yml",
                    "python/api_security/verify_approval.py", "semgrep/identity-from-request.yml"):
            self.assertTrue((TOOL / rel).is_file(), rel)

    def test_agents_md_indexes_the_steering_file(self):
        self.assertIn("[`steering/api-security.md`](steering/api-security.md)", (ROOT / "AGENTS.md").read_text())

    def test_the_steering_says_what_the_approval_guards_and_what_the_check_does_not(self):
        text = (ROOT / "steering" / "api-security.md").read_text()
        self.assertIn("`.github/workflows/`", text)
        self.assertIn("catches mistakes, not an adversary", text)
        self.assertIn("up to date", text)

    def test_the_tool_names_no_harness_specific_path(self):
        for path in TOOL.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                self.assertNotIn(".studio/", path.read_text(errors="replace"), path.relative_to(ROOT))

    def test_apply_guided_writes_the_rules_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "pyproject.toml").write_text('[project]\nname = "x"\n')
            (repo / ".studio-project.yaml").write_text('repo:\n  github: "o/r"\n\nworkspace:\n  type: "product"\n')
            result = subprocess.run([sys.executable, str(TOOL / "apply.py"), "--level", "guided", str(repo)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((repo / ".claude" / "rules" / "api-security-python.md").is_file())

    def test_setup_check_lists_levels_and_passes_a_quiet_project_at_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project(root, "quiet", "  live_users: false\n")
            status, line, _ = check_setup.check_security_levels(root)
            self.assertEqual(status, "PASS")
            self.assertIn("quiet off", line)

    def test_setup_check_warns_on_a_live_or_regulated_project_at_off(self):
        for workspace in ("  live_users: true\n", "  regulated: true\n"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                project(root, "app", workspace)
                status, line, fix = check_setup.check_security_levels(root)
                self.assertEqual(status, "WARN", workspace)
                self.assertIn("app", line)
                self.assertIn("apply.py", fix)

    def test_setup_check_warns_when_a_level_has_no_files_behind_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project(root, "app", '  security_level: "enforced"\n')
            status, line, _ = check_setup.check_security_levels(root)
            self.assertEqual(status, "WARN")
            self.assertIn("security/allowed_signers", line)

    def test_setup_check_runs_it(self):
        self.assertIn("check_security_levels(root)", (ROOT / "scripts" / "check_setup.py").read_text())


if __name__ == "__main__":
    unittest.main()
