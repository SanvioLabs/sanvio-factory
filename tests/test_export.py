"""Run with: python3 -m unittest discover -s tests"""
import datetime
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "export.py"
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))
import export  # noqa: E402 (the imports need those folders on the path first)
import usage_log  # noqa: E402 (same reason)

# Fixed here rather than read from export.py, so a key added there fails until it's added here too.
TOP_KEYS = ["exported", "loop", "since", "usage", "user", "v"]
LOOP_KEYS = ["agent", "cost_usd", "ended", "issue", "outcome", "project", "reviewer", "rounds", "run",
             "started", "tests", "tokens", "v", "verdicts"]
USAGE_KEYS = ["agents", "ask_approved", "commands", "guard_ask", "guard_deny", "sessions", "skills"]
EMPTY_USAGE = {"sessions": 0, "skills": {}, "agents": {}, "commands": {}, "guard_deny": {},
               "guard_ask": {}, "ask_approved": {}}


def run_line(issue, ended, project=None, **extra):
    """A history line as record_run in scripts/loop.py writes it, plus any extra keys."""
    line = {"v": 1, "run": "{}-2026-10-20T09:00:00".format(issue), "issue": issue, "project": project,
            "started": "2026-10-20T09:00:00", "ended": ended, "outcome": "pr", "rounds": 2,
            "tests": ["fail", "pass"], "verdicts": ["CHANGES", "APPROVE"], "tokens": 1200, "cost_usd": 0.42,
            "agent": "claude", "reviewer": "claude"}
    line.update(extra)
    return line


USAGE = [
    {"ts": "2026-10-20T09:00:00Z", "session": "a", "event": "skill", "name": "review-pr"},
    {"ts": "2026-10-20T09:01:00Z", "session": "a", "event": "agent", "name": "reviewer"},
    {"ts": "2026-10-21T09:00:00Z", "session": "b", "event": "command", "name": "learn"},
    {"ts": "2026-10-21T09:00:00Z", "session": "b", "event": "guard_deny", "rule": "credential-file"},
    {"ts": "2026-10-21T09:00:00Z", "session": "b", "event": "guard_ask", "rule": "connector-write",
     "tool": "mcp__gmail__send_email"},
    {"ts": "2026-10-21T09:00:01Z", "session": "b", "event": "ask_approved", "rule": "connector-write",
     "tool": "mcp__gmail__send_email"},
    {"ts": "2026-10-01T09:00:00Z", "session": "old", "event": "skill", "name": "whats-new"},
]


def write_lines(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(l) for l in lines) + "\nnot json\n", encoding="utf-8")


class Bundle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def history(self, lines):
        write_lines(self.root / ".loop" / "history.jsonl", lines)

    def usage(self, lines):
        write_lines(usage_log.log_path(self.root), lines)

    def test_every_key_at_every_level_is_one_the_bundle_allows(self):
        self.history([run_line(223, "2026-10-21T10:00:00", title="Fix the payments bug for Acme")])
        self.usage(USAGE)
        got = export.bundle(self.root, "2026-10-14", "2026-10-25")
        self.assertEqual(sorted(got), TOP_KEYS)
        self.assertEqual(len(got["loop"]), 1)
        for line in got["loop"]:
            self.assertEqual(sorted(line), LOOP_KEYS)
        self.assertNotIn("payments", json.dumps(got))
        self.assertEqual(sorted(got["usage"]), USAGE_KEYS)
        self.assertIsInstance(got["usage"]["sessions"], int)
        for key in USAGE_KEYS:
            if key == "sessions":
                continue
            for name, times in got["usage"][key].items():
                self.assertIsInstance(name, str, key)
                self.assertIsInstance(times, int, key)

    def test_the_counts_match_the_log(self):
        self.usage(USAGE)
        got = export.bundle(self.root, "2026-10-14", "2026-10-25")["usage"]
        self.assertEqual(got, {"sessions": 2, "skills": {"review-pr": 1}, "agents": {"reviewer": 1},
                               "commands": {"learn": 1}, "guard_deny": {"credential-file": 1},
                               "guard_ask": {"mcp__gmail__send_email": 1},
                               "ask_approved": {"mcp__gmail__send_email": 1}})

    def test_the_user_is_the_usage_logs_own_name(self):
        self.assertEqual(export.bundle(self.root, "2026-10-14", "2026-10-25")["user"],
                         usage_log.log_path(self.root).stem)

    def test_no_project_reaches_the_bundle(self):
        write_lines(self.root / ".loop" / "projects" / "acme" / "history.jsonl", [run_line(7, "2026-10-21T10:00:00")])
        self.history([run_line(223, "2026-10-21T10:00:00"), run_line(8, "2026-10-21T11:00:00", project="acme")])
        got = export.bundle(self.root, "2026-10-14", "2026-10-25")
        self.assertEqual([line["issue"] for line in got["loop"]], [223])
        self.assertTrue(all(line["project"] is None for line in got["loop"]))
        self.assertNotIn("acme", json.dumps(got))

    def test_missing_files_give_an_empty_bundle(self):
        got = export.bundle(self.root, "2026-10-14", "2026-10-25")
        self.assertEqual(got["loop"], [])
        self.assertEqual(got["usage"], EMPTY_USAGE)

    def test_lines_before_since_are_left_out(self):
        self.history([run_line(1, "2026-10-13T23:59:59"), run_line(2, "2026-10-14T00:00:00")])
        self.usage(USAGE)
        got = export.bundle(self.root, "2026-10-14", "2026-10-25")
        self.assertEqual([line["issue"] for line in got["loop"]], [2])
        self.assertNotIn("whats-new", got["usage"]["skills"])


class TheCommand(unittest.TestCase):
    def run_export(self, *args, env=None, code=None):
        cmd = [sys.executable] + (["-c", code, str(SCRIPT)] if code else [str(SCRIPT)]) + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)

    def test_since_defaults_to_14_days_ago(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "export.json"
            self.assertEqual(export.main(["--out", str(out)]), 0)
            got = json.loads(out.read_text())
        self.assertEqual(got["since"], (datetime.date.today() - datetime.timedelta(days=14)).isoformat())

    def test_an_impossible_since_is_refused(self):
        result = self.run_export("--since", "2026-13-01")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("use YYYY-MM-DD", result.stderr)

    def test_it_runs_without_claude_on_the_path_and_prints_json(self):
        result = self.run_export(env={"PATH": ""})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(json.loads(result.stdout)), TOP_KEYS)

    def test_out_writes_the_file_and_prints_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "export.json"
            result = self.run_export("--out", str(out), env={"PATH": ""})
            self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)
            self.assertEqual(sorted(json.loads(out.read_text())), TOP_KEYS)

    def test_it_never_loads_a_network_or_subprocess_module(self):
        # None in sys.modules makes any later import of that module fail.
        code = ("import runpy, sys\n"
                "for name in ('socket', 'ssl', 'http', 'http.client', 'urllib.request', 'subprocess'):\n"
                "    sys.modules[name] = None\n"
                "sys.argv = sys.argv[1:]\n"
                "runpy.run_path(sys.argv[0], run_name='__main__')\n")
        result = self.run_export(code=code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(json.loads(result.stdout)), TOP_KEYS)


if __name__ == "__main__":
    unittest.main()
