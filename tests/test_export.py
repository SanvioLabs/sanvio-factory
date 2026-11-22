"""Run with: python3 -m unittest discover -s tests"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "export.py"
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))
import export  # noqa: E402 (the imports need those folders on the path first)
import usage_log  # noqa: E402 (same reason)
import usage_shape  # noqa: E402 (same reason)

# Fixed here rather than read from export.py, so a key added there fails until it's added here too.
TOP_KEYS = ["bundle_id", "chain_head", "exported", "factory", "kind", "loop", "loop_config", "mode", "node",
            "period", "since", "usage", "user", "v"]
LOOP_KEYS = ["agent", "cost_usd", "ended", "fix_reasons", "issue", "outcome", "project", "reviewer", "rounds", "run",
             "started", "tests", "tests_changed", "tokens", "v", "verdicts"]
USAGE_KEYS = ["agents", "ask_approved", "commands", "guard_ask", "guard_deny", "log_off", "sessions", "skills"]
COUNT_KEYS = ("sessions", "log_off")  # plain numbers; every other usage key is counts by name
EMPTY_USAGE = {"sessions": 0, "skills": {}, "agents": {}, "commands": {}, "guard_deny": {},
               "guard_ask": {}, "ask_approved": {}, "log_off": 0}


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
        for key in COUNT_KEYS:
            self.assertIsInstance(got["usage"][key], int, key)
        for key in USAGE_KEYS:
            if key in COUNT_KEYS:
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
                               "ask_approved": {"mcp__gmail__send_email": 1}, "log_off": 0})

    def test_sessions_started_with_the_log_off_are_counted_since_the_date(self):
        self.usage(USAGE + [{"ts": "2026-10-20T08:00:00Z", "event": "log_off"},
                            {"ts": "2026-10-22T08:00:00Z", "event": "log_off"},
                            {"ts": "2026-10-01T08:00:00Z", "event": "log_off"}])
        got = export.bundle(self.root, "2026-10-14", "2026-10-25")["usage"]
        self.assertEqual(got["log_off"], 2)
        self.assertEqual(got["sessions"], 2)  # a log_off line has no session, so it isn't one

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

    def test_fix_reasons_and_tests_changed_are_copied_and_an_older_line_has_them_as_none(self):
        self.history([run_line(1, "2026-10-21T10:00:00"),
                      run_line(2, "2026-10-21T11:00:00", fix_reasons=[["tests-failed"], []],
                               tests_changed=[False, True])])
        got = export.bundle(self.root, "2026-10-14", "2026-10-25")["loop"]
        self.assertEqual([(line["fix_reasons"], line["tests_changed"]) for line in got],
                         [(None, None), ([["tests-failed"], []], [False, True])])

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


class Version2(unittest.TestCase):
    """SPEC-004 REQ-001 and REQ-002: what a v2 bundle adds, and which project runs it carries."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write_config(self, cfg):
        path = self.root / ".sanvio" / "export.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg), encoding="utf-8")

    def bundle(self):
        return export.bundle(self.root, "2026-10-14", "2026-10-25")

    def test_a_v2_bundle_is_in_the_shape_and_keeps_every_v1_key(self):
        got = self.bundle()
        self.assertEqual(usage_shape.problems(got), [])
        self.assertEqual((got["v"], got["kind"], got["mode"]), (2, "bundle", "general"))
        self.assertEqual(got["period"], {"first": "2026-10-14", "last": "2026-10-25"})
        for key in ("exported", "loop", "since", "usage", "user"):
            self.assertIn(key, got)

    def test_the_node_is_the_configured_name_else_the_host(self):
        self.assertTrue(self.bundle()["node"])
        self.write_config({"node": "bench-2"})
        self.assertEqual(self.bundle()["node"], "bench-2")

    def test_the_bundle_id_is_the_same_for_the_same_period_and_differs_for_another(self):
        first = self.bundle()["bundle_id"]
        self.assertEqual(self.bundle()["bundle_id"], first)
        self.assertNotEqual(export.bundle(self.root, "2026-10-15", "2026-10-25")["bundle_id"], first)

    def test_the_chain_head_is_the_hash_of_the_logs_last_line(self):
        self.assertIsNone(self.bundle()["chain_head"])
        usage_log.record(self.root, {"event": "skill", "name": "review-pr"}, "s1")
        last = (usage_log.log_path(self.root)).read_bytes().rstrip(b"\n").rsplit(b"\n", 1)[-1]
        self.assertEqual(self.bundle()["chain_head"], export.log_chain.digest(last))

    def test_the_factory_commit_is_read_from_git_without_running_it(self):
        sha = "1" * 40
        (self.root / ".git" / "refs" / "heads").mkdir(parents=True)
        (self.root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (self.root / ".git" / "refs" / "heads" / "main").write_text(sha + "\n", encoding="utf-8")
        (self.root / "CHANGELOG.md").write_text("# What's new\n\n## 2026-11-20: Thing\n\n## 2026-11-01: Old\n",
                                                encoding="utf-8")
        self.assertEqual(self.bundle()["factory"], {"commit": sha, "changelog": "2026-11-20"})

    def test_a_packed_ref_and_a_worktree_are_followed(self):
        sha = "2" * 40
        main = self.root / "main-git"
        (main / "worktrees" / "wt").mkdir(parents=True)
        (main / "packed-refs").write_text("# pack-refs\n{} refs/heads/topic\n".format(sha), encoding="utf-8")
        (main / "worktrees" / "wt" / "HEAD").write_text("ref: refs/heads/topic\n", encoding="utf-8")
        (main / "worktrees" / "wt" / "commondir").write_text("../..\n", encoding="utf-8")
        (self.root / ".git").write_text("gitdir: main-git/worktrees/wt\n", encoding="utf-8")
        self.assertEqual(export.head_commit(self.root), sha)

    def test_loop_config_names_agents_and_never_their_command_lines(self):
        (self.root / "loop.json").write_text(json.dumps({
            "agent": "SECRET_THING=x claude -p --model claude-sonnet-5-5 --permission-mode acceptEdits",
            "review_agent": "codex:gpt-6", "max_workers": 2, "max_issue_tokens": 9000,
            "test_command": "python3 -m unittest", "projects": {"acme": {"max_workers": 1, "agent": "claude"}}}),
            encoding="utf-8")
        self.write_config({"export_projects": {"acme": "web-app"}})
        got = self.bundle()["loop_config"]
        self.assertEqual(got["factory"], {"agent": "claude:claude-sonnet-5-5", "reviewer": "codex:gpt-6",
                                          "max_workers": 2, "max_rounds": None, "max_issue_tokens": 9000})
        self.assertEqual(got["web-app"]["max_workers"], 1)
        self.assertEqual(got["web-app"]["agent"], "claude")
        text = json.dumps(got)
        for leak in ("SECRET_THING", "acceptEdits", "unittest", "acme"):
            self.assertNotIn(leak, text)

    def test_a_listed_projects_runs_come_under_its_label_and_no_other_projects_do(self):
        write_lines(self.root / ".loop" / "projects" / "acme" / "history.jsonl",
                    [run_line(7, "2026-10-21T10:00:00", project="acme")])
        write_lines(self.root / ".loop" / "projects" / "other" / "history.jsonl",
                    [run_line(9, "2026-10-21T10:00:00", project="other")])
        write_lines(self.root / ".loop" / "history.jsonl", [run_line(223, "2026-10-21T10:00:00")])
        self.write_config({"export_projects": {"acme": "web-app"}})
        got = self.bundle()
        self.assertEqual([(line["issue"], line["project"]) for line in got["loop"]], [(223, None), (7, "web-app")])
        self.assertNotIn("acme", json.dumps(got))
        self.assertNotIn("other", json.dumps(got["loop"]))

    def test_with_no_list_no_project_is_read(self):
        write_lines(self.root / ".loop" / "projects" / "acme" / "history.jsonl",
                    [run_line(7, "2026-10-21T10:00:00", project="acme")])
        self.write_config({"node": "x", "export_projects": {"../escape": "x", "ok": 3}})
        self.assertEqual(self.bundle()["loop"], [])

    def test_a_bundle_off_the_shape_is_never_written(self):
        out = self.root / "export.json"
        original = usage_shape.problems
        try:
            usage_shape.problems = lambda obj: ["something: not a key this shape allows"]
            with unittest.mock.patch.object(export, "ROOT", self.root):
                self.assertEqual(export.main(["--out", str(out)]), 1)
        finally:
            usage_shape.problems = original
        self.assertFalse(out.exists())


class DetailedBundle(unittest.TestCase):
    """SPEC-004 REQ-003: --mode detailed adds the commands, and only while detailed mode is on."""

    PERSON = {"SANVIO_HEADLESS": "", "HARNESS_HEADLESS": "", "SANVIO_USAGE_LOG": "", "HARNESS_USAGE_LOG": "",
              "SANVIO_DETAILED_DAYS": ""}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = unittest.mock.patch.dict(os.environ, self.PERSON)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.on = datetime.datetime(2026, 10, 20, tzinfo=datetime.timezone.utc)

    def write_commands(self):
        write_lines(usage_log.commands_path(self.root), [
            {"ts": "2026-10-21T09:00:00Z", "session": "s1", "verdict": "ran", "text": "git status",
             "redactions": 0, "prev": "", "cwd": "/somewhere"},
            {"ts": "2026-10-01T09:00:00Z", "session": "s0", "verdict": "ran", "text": "old", "redactions": 0}])

    def test_with_no_opt_in_it_is_refused(self):
        self.write_commands()
        with self.assertRaises(ValueError):
            export.bundle(self.root, "2026-10-14", "2026-10-25", "detailed")

    def test_while_on_it_adds_the_commands_since_the_date_rebuilt_from_the_shape(self):
        usage_log.opt_in(self.root, now=self.on)
        self.write_commands()
        got = export.bundle(self.root, "2026-10-14", "2026-10-25", "detailed")
        self.assertEqual(got["mode"], "detailed")
        self.assertEqual(got["commands"], [{"ts": "2026-10-21T09:00:00Z", "session": "s1", "verdict": "ran",
                                            "text": "git status", "redactions": 0}])
        self.assertEqual(usage_shape.problems(got), [])
        self.assertNotEqual(got["bundle_id"], export.bundle(self.root, "2026-10-14", "2026-10-25")["bundle_id"])

    def test_the_day_after_it_ends_it_is_refused(self):
        usage_log.opt_in(self.root, days=1, now=self.on)
        export.bundle(self.root, "2026-10-14", "2026-10-21", "detailed")
        with self.assertRaises(ValueError):
            export.bundle(self.root, "2026-10-14", "2026-10-22", "detailed")

    def test_a_general_bundle_never_has_commands(self):
        usage_log.opt_in(self.root, now=self.on)
        self.write_commands()
        self.assertNotIn("commands", export.bundle(self.root, "2026-10-14", "2026-10-25"))


if __name__ == "__main__":
    unittest.main()
