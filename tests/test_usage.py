"""Run with: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "usage_log.py"
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))
import usage_log  # noqa: E402 (the imports need those folders on the path first)
import usage_report  # noqa: E402 (same reason)


def pre(tool, **tool_input):
    return usage_log.entry("PreToolUse", {"tool_name": tool, "tool_input": tool_input})


class Entries(unittest.TestCase):
    def test_a_skill_is_logged_by_name(self):
        self.assertEqual(pre("Skill", skill="review-pr"), {"event": "skill", "name": "review-pr"})

    def test_an_agent_is_logged_by_type(self):
        self.assertEqual(pre("Agent", subagent_type="reviewer", prompt="secret plan"),
                         {"event": "agent", "name": "reviewer"})

    def test_a_guard_refusal_is_logged_by_rule_without_the_path(self):
        line = pre("Read", file_path="/home/me/project/.env")
        self.assertEqual(line, {"event": "guard_deny", "rule": "credential-file"})
        self.assertEqual(pre("Bash", command="cat .env"), {"event": "guard_deny", "rule": "credential-command"})

    def test_a_connector_ask_names_the_tool(self):
        self.assertEqual(pre("mcp__gmail__send_email", to="x@example.com"),
                         {"event": "guard_ask", "rule": "connector-write", "tool": "mcp__gmail__send_email"})

    def test_an_approved_ask_is_logged_after_it_ran(self):
        line = usage_log.entry("PostToolUse", {"tool_name": "mcp__gmail__send_email", "tool_input": {}})
        self.assertEqual(line["event"], "ask_approved")

    def test_ordinary_calls_log_nothing(self):
        self.assertIsNone(pre("Read", file_path="README.md"))
        self.assertIsNone(pre("Bash", command="git status"))
        self.assertIsNone(usage_log.entry("PostToolUse", {"tool_name": "mcp__gmail__search", "tool_input": {}}))

    def test_a_slash_command_is_logged_without_its_arguments(self):
        line = usage_log.entry("UserPromptSubmit", {"prompt": "/review-pr the payments branch"})
        self.assertEqual(line, {"event": "command", "name": "review-pr"})

    def test_an_ordinary_prompt_is_not_logged(self):
        self.assertIsNone(usage_log.entry("UserPromptSubmit", {"prompt": "fix the login bug in /src/auth"}))

    def test_sessions_are_logged(self):
        self.assertEqual(usage_log.entry("SessionStart", {"source": "startup"})["event"], "session_start")
        self.assertEqual(usage_log.entry("SessionEnd", {"reason": "exit"})["event"], "session_end")

    def test_a_session_bin_factory_started_says_it_was_headless(self):
        with mock.patch.dict(os.environ, {"SANVIO_HEADLESS": "1"}):
            self.assertIs(usage_log.entry("SessionStart", {"source": "startup"})["headless"], True)
        with mock.patch.dict(os.environ):
            os.environ.pop("SANVIO_HEADLESS", None)
            os.environ.pop("HARNESS_HEADLESS", None)
            self.assertNotIn("headless", usage_log.entry("SessionStart", {"source": "startup"}))

    def test_a_headless_refusal_is_logged_as_headless_not_as_a_credential(self):
        with mock.patch.dict(os.environ, {"SANVIO_HEADLESS": "1"}):
            self.assertEqual(pre("Bash", command="npm test"), {"event": "guard_deny", "rule": "headless"})
            self.assertEqual(pre("mcp__claude_ai_Gmail__search_threads", query="x")["rule"], "headless")
            self.assertEqual(pre("Bash", command="cat .env")["rule"], "credential-command")
            # A path can't pass itself off as a headless refusal: the reason has to match exactly.
            self.assertEqual(pre("Read", file_path="A headless run/.env")["rule"], "credential-file")
            self.assertEqual(pre("Read", file_path="/etc/hosts"), {"event": "guard_deny", "rule": "headless"})
            self.assertEqual(pre("Glob", pattern="../**")["rule"], "headless")
            # A headless Grep the guard passes on with !*.git isn't a refusal, so it isn't logged.
            self.assertIsNone(pre("Grep", pattern="x", path="projects/app"))
            company = os.path.join(usage_log.guard.ROOT, "company", "COMPANY.md")
            self.assertEqual(pre("Read", file_path=company), {"event": "guard_deny", "rule": "headless"})

    def test_a_refused_search_is_logged_as_a_credential_file(self):
        self.assertEqual(pre("Grep", pattern="KEY", path="/home/me/project/.env"),
                         {"event": "guard_deny", "rule": "credential-file"})
        self.assertEqual(pre("Grep", pattern="KEY", glob="*.pem")["rule"], "credential-file")
        self.assertIsNone(pre("Grep", pattern="KEY"))


class TheHook(unittest.TestCase):
    def run_hook(self, event, **env):
        with tempfile.TemporaryDirectory() as tmp:
            full_env = dict(os.environ, CLAUDE_PROJECT_DIR=tmp, **env)
            result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event),
                                    capture_output=True, text=True, env=full_env, timeout=30)
            logs = list((Path(tmp) / ".sanvio" / "usage").glob("*.jsonl"))
            lines = [json.loads(l) for p in logs for l in p.read_text().splitlines()]
            return result, lines

    def test_it_appends_a_line_and_prints_nothing(self):
        result, lines = self.run_hook({"hook_event_name": "PreToolUse", "session_id": "s1",
                                       "tool_name": "Skill", "tool_input": {"skill": "learn"}})
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertEqual(len(lines), 1)
        self.assertEqual((lines[0]["event"], lines[0]["name"], lines[0]["session"]), ("skill", "learn", "s1"))

    def test_the_old_off_switch_still_counts_since_it_only_records_less(self):
        _, lines = self.run_hook({"hook_event_name": "PreToolUse", "tool_name": "Skill",
                                  "tool_input": {"skill": "learn"}}, HARNESS_USAGE_LOG="off")
        self.assertEqual(lines, [])

    def test_a_leftover_old_folder_is_not_logged_to(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".harness").mkdir()
            usage_log.record(tmp, {"event": "skill", "name": "learn"})
            self.assertEqual(len(list((Path(tmp) / ".sanvio" / "usage").glob("*.jsonl"))), 1)
            self.assertFalse((Path(tmp) / ".harness" / "usage").exists())

    def test_off_means_nothing_is_written(self):
        _, lines = self.run_hook({"hook_event_name": "PreToolUse", "tool_name": "Skill",
                                  "tool_input": {"skill": "learn"}}, SANVIO_USAGE_LOG="off")
        self.assertEqual(lines, [])

    def test_bad_input_never_fails_the_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True,
                                    text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=tmp), timeout=30)
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_the_log_is_gitignored(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        # No trailing slash, so a link by either name is ignored too, not only a folder (security review).
        self.assertIn("/.sanvio", lines)
        self.assertIn("/.harness", lines)  # a leftover old folder that failed to move stays out of git

    def test_a_report_is_gitignored_and_the_folders_readme_is_not(self):
        def ignored(path):
            return subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", path], timeout=30).returncode == 0
        self.assertTrue(ignored("reports/usage/2026-10-24-someone.md"))
        self.assertFalse(ignored("reports/usage/README.md"))

    def test_it_is_wired_on_every_event_it_handles(self):
        hooks = json.loads((ROOT / ".claude" / "settings.json").read_text())["hooks"]
        for event in ("SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse"):
            commands = [h["command"] for block in hooks.get(event, []) for h in block["hooks"]]
            self.assertTrue(any("usage_log.py" in c for c in commands), event)


class Report(unittest.TestCase):
    LINES = [
        {"ts": "2026-10-01T09:00:00Z", "session": "a", "event": "skill", "name": "review-pr"},
        {"ts": "2026-10-02T09:00:00Z", "session": "a", "event": "skill", "name": "review-pr"},
        {"ts": "2026-10-02T09:00:00Z", "session": "b", "event": "command", "name": "learn"},
        {"ts": "2026-10-03T09:00:00Z", "session": "b", "event": "guard_deny", "rule": "credential-file"},
        {"ts": "2026-10-03T09:00:00Z", "session": "b", "event": "guard_ask", "rule": "connector-write",
         "tool": "mcp__gmail__send_email"},
        {"ts": "2026-10-03T09:00:01Z", "session": "b", "event": "ask_approved", "rule": "connector-write",
         "tool": "mcp__gmail__send_email"},
        {"ts": "2026-09-20T09:00:00Z", "session": "old", "event": "skill", "name": "whats-new"},
    ]

    def write_log(self, tmp):
        path = Path(tmp) / "me.jsonl"
        path.write_text("\n".join(json.dumps(l) for l in self.LINES) + "\nnot json\n")
        return path

    def test_it_reads_only_the_period_and_skips_bad_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = usage_report.read(self.write_log(tmp), "2026-10-01")
        self.assertEqual(len(lines), 6)

    def test_the_summary_counts_and_lists_what_went_unused(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = usage_report.read(self.write_log(tmp), "2026-10-01")
        text = usage_report.report(lines, "2026-10-01", "2026-10-14", ["learn", "review-pr", "whats-new"])
        self.assertIn("Sessions: 2", text)
        self.assertIn("| `review-pr` | 2 |", text)
        self.assertIn("| `credential-file` | 1 |", text)
        self.assertIn("| `mcp__gmail__send_email` | 1 | 1 |", text)
        self.assertIn("Never used here: `whats-new`", text)

    def earlier_report(self, tmp, text):
        path = Path(tmp) / "earlier.md"
        path.write_text(text)
        return usage_report.earlier_unused(path)

    def test_a_skill_unused_in_both_periods_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = usage_report.read(self.write_log(tmp), "2026-10-01")
            earlier = self.earlier_report(tmp, "# Old\n\nNever used here: `whats-new`, `learn`\n")
        text = usage_report.report(lines, "2026-10-01", "2026-10-14", ["learn", "review-pr", "whats-new"], earlier)
        self.assertIn("Unused two sprints running: `whats-new`\n", text)

    def test_no_overlap_says_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = usage_report.read(self.write_log(tmp), "2026-10-01")
            earlier = self.earlier_report(tmp, "Never used here: `learn`\n")
        text = usage_report.report(lines, "2026-10-01", "2026-10-14", ["learn", "review-pr", "whats-new"], earlier)
        self.assertIn("Unused two sprints running: none", text)

    def test_without_a_usable_previous_report_no_line_is_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self.write_log(tmp)
            earlier = Path(tmp) / "earlier.md"
            earlier.write_text("# Old report\n\nNo skills line here.\n")
            script = str(ROOT / "scripts" / "usage_report.py")
            for extra in ([], ["--previous", str(earlier)], ["--previous", str(Path(tmp) / "missing.md")]):
                result = subprocess.run([sys.executable, script, "--log", str(log), "--since", "2026-10-01"] + extra,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0)
                self.assertNotIn("Unused two sprints running", result.stdout)

    def test_a_missing_log_says_why(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "usage_report.py"),
                                 "--log", "/nonexistent/me.jsonl"], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertIn("SANVIO_USAGE_LOG", result.stderr)

    def test_the_help_says_what_since_and_log_take(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "usage_report.py"), "--help"],
                                capture_output=True, text=True, timeout=30)
        text = " ".join(result.stdout.split())  # argparse wraps to the terminal width
        self.assertEqual(result.returncode, 0)
        self.assertIn("YYYY-MM-DD", text)
        self.assertIn("14 days ago", text)
        self.assertIn("a log file other than your own", text)

    def run_report(self, since):
        with tempfile.TemporaryDirectory() as tmp:
            return subprocess.run([sys.executable, str(ROOT / "scripts" / "usage_report.py"),
                                   "--log", str(self.write_log(tmp)), "--since", since],
                                  capture_output=True, text=True, timeout=30)

    def assert_refused(self, result):
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("--since", result.stderr)
        self.assertIn("YYYY-MM-DD", result.stderr)

    def test_an_unreadable_since_is_refused(self):
        self.assert_refused(self.run_report("garbage"))

    def test_an_impossible_date_is_refused(self):
        self.assert_refused(self.run_report("2026-13-45"))

    def test_a_real_since_still_reports(self):
        result = self.run_report("2026-10-01")
        self.assertEqual(result.returncode, 0)
        self.assertIn("# Harness usage, 2026-10-01 to", result.stdout)


if __name__ == "__main__":
    unittest.main()
