"""Run with: python3 -m unittest discover -s tests"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "plugin_report.py"

INSTALL = "/Users/someone/.claude/plugins/cache/secret-install-folder"
OTHER = "/Users/someone/elsewhere/other-folder"
FIXTURE = [
    {"id": "stelliad@sanvio-factory", "version": "1.3", "scope": "project", "enabled": True,
     "projectPath": str(ROOT), "installPath": INSTALL + "/stelliad"},
    {"id": "loom-pane@inline", "version": "0.2", "scope": "session", "enabled": True,
     "installPath": INSTALL + "/loom-pane"},
    {"id": "off@market", "version": "9.9", "scope": "user", "enabled": False, "installPath": INSTALL + "/off"},
    {"id": "elsewhere@market", "version": "4.0", "scope": "project", "enabled": True,
     "projectPath": OTHER, "installPath": INSTALL + "/elsewhere"},
]
TABLE = ["| Plugin | Version | Scope |", "|---|---|---|",
         "| loom-pane@inline | 0.2 | session |", "| stelliad@sanvio-factory | 1.3 | project |"]


def run(args=(), stdout=None, path=None):
    """Run the script with a fake `claude` that prints `stdout`, or with `path` as PATH when given."""
    with tempfile.TemporaryDirectory() as folder:
        bin_dir = Path(folder) / "bin"
        bin_dir.mkdir()
        if stdout is not None:
            fake = bin_dir / "claude"
            fake.write_text("#!{}\nimport sys\nsys.stdout.write({!r})\n".format(sys.executable, stdout))
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        env = dict(os.environ, PATH=path if path is not None else str(bin_dir))
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                              timeout=60, env=env)


def previous(folder, rows, name="2026-10-10-pat.md"):
    """A harness report holding a plugin table with `rows` as (id, version, scope)."""
    lines = ["# Report", "", "## Plugins and mods", "", "| Plugin | Version | Scope |", "|---|---|---|"]
    lines += ["| {} | {} | {} |".format(*row) for row in rows] + ["", "## Proposals", "", "| x | y | z |"]
    path = Path(folder) / name
    path.write_text("\n".join(lines) + "\n")
    return str(path)


class PluginReportTest(unittest.TestCase):
    def test_table_lists_enabled_plugins_for_this_harness(self):
        result = run(stdout=json.dumps(FIXTURE))
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], "## Plugins and mods")
        self.assertEqual(lines[2:6], TABLE)
        self.assertNotIn("off@market", result.stdout)
        self.assertNotIn("elsewhere@market", result.stdout)

    def test_changed_new_and_gone_show_on_one_line(self):
        with tempfile.TemporaryDirectory() as folder:
            old = previous(folder, [("stelliad@sanvio-factory", "1.2", "project"), ("gone@market", "1.0", "user")])
            result = run(["--previous", old], stdout=json.dumps(FIXTURE))
        self.assertIn("Changed since 2026-10-10: gone@market (gone), loom-pane@inline (new), "
                      "stelliad@sanvio-factory 1.2 → 1.3", result.stdout.splitlines())

    def test_nothing_changed(self):
        with tempfile.TemporaryDirectory() as folder:
            old = previous(folder, [("loom-pane@inline", "0.2", "session"), ("stelliad@sanvio-factory", "1.3", "project")])
            result = run(["--previous", old], stdout=json.dumps(FIXTURE))
        self.assertEqual(result.stdout.splitlines()[-1], "Nothing changed since 2026-10-10.")

    def test_no_earlier_report(self):
        self.assertEqual(run(stdout=json.dumps(FIXTURE)).stdout.splitlines()[-1], "No earlier report to compare with.")
        with tempfile.TemporaryDirectory() as folder:
            bare = Path(folder) / "2026-10-10-pat.md"
            bare.write_text("# Report\n\nNo plugin table here.\n")
            result = run(["--previous", str(bare)], stdout=json.dumps(FIXTURE))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], "No earlier report to compare with.")

    def test_claude_missing(self):
        result = run(path="/nonexistent")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[:2], ["## Plugins and mods", ""])
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[2].startswith("Couldn't read plugin versions: "))

    def test_claude_prints_something_that_is_not_json(self):
        result = run(stdout="not json at all")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(),
                         ["## Plugins and mods", "", "Couldn't read plugin versions: claude's answer wasn't JSON."])

    def test_a_report_that_couldnt_read_versions_is_no_earlier_report(self):
        with tempfile.TemporaryDirectory() as folder:
            failed = Path(folder) / "2026-10-10-pat.md"
            failed.write_text(run(stdout="not json").stdout + "\n## Proposals\n")
            result = run(["--previous", str(failed)], stdout=json.dumps(FIXTURE))
        self.assertEqual(result.stdout.splitlines()[-1], "No earlier report to compare with.")

    def test_a_plugin_registered_at_two_scopes_shows_both(self):
        twice = FIXTURE + [
            {"id": "lens@market", "version": "0.2.0", "scope": "user", "enabled": True},
            {"id": "lens@market", "version": "0.1.0", "scope": "project", "enabled": True, "projectPath": str(ROOT)}]
        result = run(stdout=json.dumps(twice))
        self.assertIn("| lens@market | 0.1.0 | project |", result.stdout)
        self.assertIn("| lens@market | 0.2.0 | user |", result.stdout)

    def test_a_change_at_one_of_two_scopes_names_the_scope(self):
        twice = FIXTURE + [
            {"id": "lens@market", "version": "0.2.0", "scope": "user", "enabled": True},
            {"id": "lens@market", "version": "0.2.0", "scope": "project", "enabled": True, "projectPath": str(ROOT)}]
        with tempfile.TemporaryDirectory() as folder:
            old = previous(folder, [("loom-pane@inline", "0.2", "session"), ("stelliad@sanvio-factory", "1.3", "project"),
                                    ("lens@market", "0.2.0", "user"), ("lens@market", "0.1.0", "project")])
            result = run(["--previous", old], stdout=json.dumps(twice))
        self.assertEqual(result.stdout.splitlines()[-1], "Changed since 2026-10-10: lens@market (project) 0.1.0 → 0.2.0")

    def test_no_install_or_project_path_in_the_output(self):
        with tempfile.TemporaryDirectory() as folder:
            old = previous(folder, [("gone@market", "1.0", "user")])
            result = run(["--previous", old], stdout=json.dumps(FIXTURE))
        self.assertIn("| stelliad@sanvio-factory | 1.3 | project |", result.stdout)
        for value in (INSTALL, OTHER, str(ROOT), "installPath", "projectPath"):
            self.assertNotIn(value, result.stdout)


if __name__ == "__main__":
    unittest.main()
