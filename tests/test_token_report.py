"""Run with: python3 -m unittest discover -s tests"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "token_report.py"
sys.path.insert(0, str(ROOT / "scripts"))
import token_report  # noqa: E402 (needs scripts/ on the path first)
import names  # noqa: E402 (same reason)

SINCE = "2026-10-01"
USAGE = {"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 30, "cache_read_input_tokens": 40}
_ids = iter(range(1, 1_000_000))


def entry(cwd, usage=None, id=None, req=None, session="s1", ts="2026-10-05T12:00:00.000Z",
          model="claude-test-1", sidechain=False, content="a reply"):
    """One transcript line for a reply, the shape Claude Code writes."""
    n = next(_ids)
    return {"type": "assistant", "cwd": str(cwd), "sessionId": session, "timestamp": ts,
            "requestId": req or "req_{}".format(n), "isSidechain": sidechain,
            "message": {"id": id or "msg_{}".format(n), "model": model, "role": "assistant",
                        "usage": dict(USAGE) if usage is None else usage,
                        "content": [{"type": "text", "text": content}]}}


def write(folder, relative, lines):
    path = Path(folder) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join((l if isinstance(l, str) else json.dumps(l)) + "\n" for l in lines))
    return path


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=60)


class Harness(unittest.TestCase):
    """A temporary harness root, a loop folder beside it, and a transcripts folder."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root = base / "harness"
        self.loop = base / "loop-checkouts"
        self.transcripts = base / "transcripts"
        for folder in (self.root / "projects" / "app", self.loop / "issue-7", self.transcripts):
            folder.mkdir(parents=True)

    def rows(self, lines):
        return [token_report.group(e, self.root, self.loop) for e in lines]


class Discovery(Harness):
    def test_subagent_files_in_a_session_subfolder_are_found(self):
        write(self.transcripts, "proj/s1.jsonl", [entry(self.root)])
        write(self.transcripts, "proj/s1/subagents/agent-a.jsonl", [entry(self.root)])
        found = token_report.read(self.transcripts, SINCE)
        self.assertEqual(len(found), 2)
        self.assertEqual(sorted(e["_subagent"] for e in found), [False, True])

    def test_a_sidechain_line_counts_as_a_subagent(self):
        write(self.transcripts, "proj/s1.jsonl", [entry(self.root, sidechain=True)])
        self.assertTrue(token_report.read(self.transcripts, SINCE)[0]["_subagent"])

    def test_the_projects_flag_is_where_it_reads(self):
        write(self.transcripts, "proj/s1.jsonl", [entry(ROOT, content="flag-test")])
        result = run("--projects", str(self.transcripts), "--since", SINCE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Total: 100 tokens across 1 sessions.", result.stdout)


class JudgedByCwd(Harness):
    def test_a_session_that_leaves_the_root_counts_only_its_lines_inside(self):
        outside = self.root.parent / "elsewhere"
        lines = [entry(self.root), entry(outside), entry(self.root / "notes")]
        out = token_report.report(lines, SINCE, "2026-10-22", self.root, self.loop)
        self.assertIn("Total: 200 tokens across 1 sessions.", out)

    def test_a_sibling_sharing_the_roots_name_is_outside(self):
        sibling = self.root.parent / (self.root.name + "-other")
        self.assertIsNone(token_report.group(entry(sibling), self.root, self.loop))
        self.assertIsNone(token_report.group(entry(sibling / "projects" / "app"), self.root, self.loop))

    def test_a_line_without_a_cwd_is_outside(self):
        line = entry(self.root)
        del line["cwd"]
        self.assertIsNone(token_report.group(line, self.root, self.loop))


class Grouping(Harness):
    def test_root_projects_and_loop(self):
        self.assertEqual(self.rows([entry(self.root), entry(self.root / "skills"), entry(self.root / "projects"),
                                    entry(self.root / "projects" / "app" / "src"), entry(self.loop / "issue-7" / "x")]),
                         [("Conversations", ""), ("Conversations", ""), ("Conversations", ""),
                          ("projects/", "app"), ("Loop", "issue-7")])

    def test_without_worktree_dir_the_loop_folder_is_beside_home(self):
        self.assertEqual(token_report.loop_dir(self.root), names.loop_home() / "harness")

    def test_without_worktree_dir_both_home_folders_count_for_a_release(self):
        self.assertEqual(token_report.loop_dirs(self.root),
                         [home / "harness" for home in names.loop_homes()])
        new, old = self.root.parent / "new-loop", self.root.parent / "old-loop"
        both = [new, old]
        self.assertEqual(token_report.group(entry(old / "issue-7"), self.root, both), ("Loop", "issue-7"))
        self.assertEqual(token_report.group(entry(new / "app" / "issue-2"), self.root, both), ("Loop", "app/issue-2"))
        self.assertEqual(token_report.group(entry(self.root), self.root, both), ("Conversations", ""))

    def test_worktree_dir_from_loop_json_is_used(self):
        (self.root / "loop.json").write_text(json.dumps({"worktree_dir": str(self.loop)}))
        self.assertEqual(token_report.loop_dir(self.root), self.loop)
        self.assertEqual(token_report.loop_dirs(self.root), [self.loop])

    def test_a_worktree_dir_inside_the_root_counts_as_the_loop(self):
        inside = self.root / "checkouts"
        (self.root / "loop.json").write_text(json.dumps({"worktree_dir": str(inside)}))
        loop = token_report.loop_dir(self.root)
        self.assertEqual(token_report.group(entry(inside / "issue-3"), self.root, loop), ("Loop", "issue-3"))
        self.assertEqual(token_report.group(entry(self.root), self.root, loop), ("Conversations", ""))


class Repeats(Harness):
    def test_a_reply_written_as_several_lines_counts_once(self):
        line = entry(self.root, id="msg_same", req="req_same")
        write(self.transcripts, "proj/s1.jsonl", [line, line, entry(self.root, id="msg_same", req="req_other")])
        self.assertEqual(len(token_report.read(self.transcripts, SINCE)), 2)

    def test_read_file_keeps_every_line_and_date_for_read_to_sort_out(self):
        line = entry(self.root, id="msg_same", req="req_same", ts="2026-09-01T00:00:00Z")
        path = write(self.transcripts, "proj/s1.jsonl", [line, line, "not json"])
        found = token_report.read_file(path, nested=True)
        self.assertEqual(len(found), 2)
        self.assertTrue(all(e["_subagent"] for e in found))
        self.assertEqual(token_report.read(self.transcripts, SINCE), [])


class Since(Harness):
    def test_replies_before_the_date_are_left_out(self):
        write(self.transcripts, "proj/s1.jsonl", [entry(self.root, ts="2026-09-30T23:59:59Z"),
                                                  entry(self.root, ts="2026-10-01T00:00:00Z")])
        found = token_report.read(self.transcripts, SINCE)
        self.assertEqual([e["timestamp"] for e in found], ["2026-10-01T00:00:00Z"])

    def test_a_bad_date_is_refused_as_usage_report_refuses_it(self):
        mine = run("--since", "last week")
        theirs = subprocess.run([sys.executable, str(ROOT / "scripts" / "usage_report.py"), "--since", "last week"],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual((mine.returncode, theirs.returncode), (2, 2))
        self.assertIn("use YYYY-MM-DD, e.g. 2026-10-01", mine.stderr)
        self.assertEqual(mine.stderr.splitlines()[-1].split(": ", 1)[1], theirs.stderr.splitlines()[-1].split(": ", 1)[1])


class Output(Harness):
    def test_every_section_is_there(self):
        lines = [entry(self.root, session="a"), entry(self.root / "projects" / "app", session="b", model="claude-other"),
                 entry(self.loop / "issue-7", session="c", sidechain=True, ts="2026-10-03T08:00:00Z"),
                 entry(self.loop / "issue-12", session="d")]
        for line in lines:
            line["_subagent"] = bool(line["isSidechain"])
        out = token_report.report(lines, SINCE, "2026-10-22", self.root, self.loop)
        for heading in ("# Claude Code tokens, 2026-10-01 to 2026-10-22", "## Conversations", "## projects/",
                        "## Loop", "## By model", "## Subagents", "## Top sessions", "## Top loop issues"):
            self.assertIn(heading, out)
        self.assertIn("| Repo | Input | Output | Cache writes | Cache reads | Total |", out)
        self.assertIn("| app | 10 | 20 | 30 | 40 | 100 |", out)
        self.assertIn("| This harness | 10 | 20 | 30 | 40 | 100 |", out)
        self.assertLess(out.index("| issue-7 |"), out.index("| issue-12 |"))
        self.assertIn("| claude-other | 100 |", out)
        self.assertIn("100 of 400 tokens (25%) were spent by subagents.", out)
        self.assertIn("`c`, first 2026-10-03", out)
        self.assertIn("## Loop cost", out)
        self.assertTrue(out.endswith("Claude Code sessions only. Dollars only for the loop's runs, as the loop "
                                     "recorded them at API prices."))

    def test_nothing_under_the_harness_says_so(self):
        out = token_report.report([entry(self.root.parent / "elsewhere")], SINCE, "2026-10-22", self.root, self.loop)
        self.assertEqual(out, "No Claude Code usage under this harness since 2026-10-01.")


class LoopCost(Harness):
    """The loop's own estimates, from each issue's usage.json under the harness's .loop/."""

    def record(self, relative, entries):
        write(self.root / ".loop", relative, [json.dumps(entries)])

    def test_costs_come_from_the_loops_records_since_the_date(self):
        self.record("issue-7/usage.json", [
            {"step": "plan", "run_started": "2026-10-05T09:00:00", "cost_usd": 1.25},
            {"step": "build", "run_started": "2026-10-06T09:00:00", "cost_usd": 0.5},
            {"step": "review", "run_started": "2026-10-06T09:00:00", "cost_usd": None},
            {"step": "plan", "run_started": "2026-09-30T09:00:00", "cost_usd": 9.0}])
        self.record("issue-12/usage.json", [{"step": "plan", "run_started": "2026-10-05T09:00:00", "cost_usd": None}])
        self.record("projects/app/issue-3/usage.json", [
            {"step": "plan", "run_started": "2026-10-05T09:00:00", "cost_usd": 0.25}])
        self.assertEqual(token_report.loop_costs(self.root, SINCE),
                         {"issue-7": (1.75, 1), "issue-12": (None, 1), "app/issue-3": (0.25, 0)})

    def test_a_run_with_no_start_date_is_in_no_period(self):
        self.record("issue-7/usage.json", [{"step": "plan", "run_started": None, "cost_usd": 4.0},
                                           {"step": "plan", "cost_usd": 4.0}])
        self.assertEqual(token_report.loop_costs(self.root, SINCE), {})

    def test_unreadable_records_and_odd_values_are_skipped(self):
        write(self.root / ".loop", "issue-1/usage.json", ["not json"])
        self.record("issue-2/usage.json", {"cost_usd": 3})
        self.record("issue-3/usage.json", [["x"], {"run_started": "2026-10-05", "cost_usd": "lots"},
                                           {"run_started": "2026-10-05", "cost_usd": True},
                                           {"run_started": "2026-10-05", "cost_usd": 2}])
        self.assertEqual(token_report.loop_costs(self.root, SINCE), {"issue-3": (2, 2)})

    def test_no_loop_folder_reads_as_no_costs(self):
        self.assertEqual(token_report.loop_costs(self.root, SINCE), {})

    def test_the_report_lists_them_with_a_total_and_the_runs_without_one(self):
        out = token_report.report([entry(self.root)], SINCE, "2026-10-22", self.root, self.loop,
                                  costs={"issue-12": (0.25, 0), "issue-7": (1.75, 1), "issue-9": (None, 2)})
        self.assertIn("| Issue | Estimated cost | Runs without a cost |", out)
        self.assertIn("| issue-7 | $1.75 | 1 |", out)
        self.assertIn("| issue-9 | none recorded | 2 |", out)
        self.assertLess(out.index("| issue-7 |"), out.index("| issue-12 |"))
        self.assertIn("Total: $2.00, estimated at API prices, not what was billed.", out)
        self.assertIn("3 runs recorded no cost", out)
        self.assertIn("when the loop picked the issue up", out)

    def test_without_costs_it_says_none_were_recorded(self):
        out = token_report.report([entry(self.root)], SINCE, "2026-10-22", self.root, self.loop)
        self.assertIn("## Loop cost\n\nNone recorded.", out)

    def test_costs_print_when_no_transcript_is_under_the_harness(self):
        out = token_report.report([], SINCE, "2026-10-22", self.root, self.loop, costs={"issue-7": (1.75, 0)})
        self.assertIn("| issue-7 | $1.75 | 0 |", out)

    def test_a_project_issue_has_the_same_name_in_the_token_and_cost_tables(self):
        (self.loop / "app" / "issue-3").mkdir(parents=True)
        self.assertEqual(token_report.group(entry(self.loop / "app" / "issue-3"), self.root, self.loop),
                         ("Loop", "app/issue-3"))
        self.assertEqual(token_report.group(entry(self.loop / "app" / "issue-3" / "src"), self.root, self.loop),
                         ("Loop", "app/issue-3"))


class Privacy(Harness):
    def test_no_prompt_reply_path_or_code_is_printed(self):
        secret_dir = ROOT / "secret-folder-zq7"
        prompt = {"type": "user", "cwd": str(secret_dir), "sessionId": "s1", "timestamp": "2026-10-05T11:00:00Z",
                  "message": {"role": "user", "content": "prompt-text-zq7"}}
        write(self.transcripts, "proj/s1.jsonl", [
            prompt, entry(secret_dir, content="reply-text-zq7 def secret_function_zq7(): pass")])
        result = run("--projects", str(self.transcripts), "--since", SINCE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Total: 100 tokens", result.stdout)
        for leak in ("prompt-text-zq7", "reply-text-zq7", "secret_function_zq7", "secret-folder-zq7", str(ROOT)):
            self.assertNotIn(leak, result.stdout)


def said(cwd, content, meta=False, ts="2026-10-05T12:00:00.000Z"):
    """One user line: a typed prompt when content is a string and meta is False."""
    return {"type": "user", "cwd": str(cwd), "sessionId": "s1", "timestamp": ts, "isMeta": meta,
            "message": {"role": "user", "content": content}}


def command(cwd, name, args=""):
    return said(cwd, "<command-message>{0}</command-message>\n<command-name>/{0}</command-name>\n"
                     "<command-args>{1}</command-args>".format(name, args))


def tool_result(cwd):
    return said(cwd, [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "done"}])


def skill_call(cwd, skill, id, req):
    """The line of a reply holding a Skill call, without the usage, which comes on its other line."""
    line = entry(cwd, id=id, req=req)
    del line["message"]["usage"]
    line["message"]["content"] = [{"type": "tool_use", "id": "toolu_" + id, "name": "Skill", "input": {"skill": skill}}]
    return line


ONE = {"claude-test-1": [10, 20, 30, 40]}
TWO = {"claude-test-1": [20, 40, 60, 80]}


class Activity(Harness):
    """Tokens by subagent type, skill and slash command, for sessions started at the root."""

    def activity(self):
        return token_report.activity(self.transcripts, SINCE, self.root, self.loop)

    def test_subagents_count_by_their_recorded_type_and_under_no_skill_or_command(self):
        write(self.transcripts, "proj/s1.jsonl", [command(self.root, "plan"), entry(self.root)])
        write(self.transcripts, "proj/s1/subagents/agent-a.jsonl", [entry(self.root), entry(self.root)])
        write(self.transcripts, "proj/s1/subagents/agent-a.meta.json", [{"agentType": "reviewer"}])
        write(self.transcripts, "proj/s1/subagents/agent-b.jsonl", [entry(self.root)])
        self.assertEqual(self.activity(), {
            "agents": {"reviewer": {"runs": 1, "models": TWO},
                       "agent type not recorded": {"runs": 1, "models": ONE}},
            "skills": {},
            "commands": {"plan": {"runs": 1, "models": ONE}}})

    def test_a_subagent_with_no_tokens_is_still_a_run(self):
        write(self.transcripts, "proj/s1/subagents/agent-a.jsonl", [said(self.root, "go")])
        write(self.transcripts, "proj/s1/subagents/agent-a.meta.json", [{"agentType": "reviewer"}])
        self.assertEqual(self.activity()["agents"], {"reviewer": {"runs": 1, "models": {}}})

    def test_a_sidechain_line_in_a_sessions_file_takes_no_span(self):
        write(self.transcripts, "proj/s1.jsonl", [command(self.root, "plan"), entry(self.root, sidechain=True),
                                                  entry(self.root)])
        self.assertEqual(self.activity()["commands"], {"plan": {"runs": 1, "models": ONE}})

    def test_a_skill_counts_from_the_reply_after_its_call_to_the_next_prompt(self):
        write(self.transcripts, "proj/s1.jsonl", [
            said(self.root, "review this"), skill_call(self.root, "review-pr", "msg_call", "req_call"),
            entry(self.root, id="msg_call", req="req_call"), tool_result(self.root),
            entry(self.root), entry(self.root), said(self.root, "thanks"), entry(self.root)])
        self.assertEqual(self.activity()["skills"], {"review-pr": {"runs": 1, "models": TWO}})

    def test_a_skill_call_written_twice_is_one_run(self):
        call = skill_call(self.root, "review-pr", "msg_call", "req_call")
        write(self.transcripts, "proj/s1.jsonl", [call, call, entry(self.root, id="msg_call", req="req_call"),
                                                  entry(self.root)])
        self.assertEqual(self.activity()["skills"], {"review-pr": {"runs": 1, "models": ONE}})

    def test_a_skill_inside_a_command_takes_over_from_it(self):
        write(self.transcripts, "proj/s1.jsonl", [
            command(self.root, "plan"), entry(self.root), skill_call(self.root, "create-ticket", "msg_x", "req_x"),
            entry(self.root, id="msg_x", req="req_x"), tool_result(self.root), entry(self.root), entry(self.root)])
        found = self.activity()
        self.assertEqual(found["commands"], {"plan": {"runs": 1, "models": TWO}})
        self.assertEqual(found["skills"], {"create-ticket": {"runs": 1, "models": TWO}})

    def test_a_command_followed_by_a_prompt_has_one_run_and_no_tokens(self):
        write(self.transcripts, "proj/s1.jsonl", [command(self.root, "plan"), said(self.root, "hi"), entry(self.root)])
        found = self.activity()
        self.assertEqual(found["commands"], {"plan": {"runs": 1, "models": {}}})
        out = token_report.report(token_report.read(self.transcripts, SINCE), SINCE, "2026-10-22",
                                  self.root, self.loop, activity=found)
        self.assertIn("| plan | 1 | 0 | 0 | 0 | 0 | 0 |", out)

    def test_projects_and_loop_worktrees_are_left_out(self):
        app, issue = self.root / "projects" / "app", self.loop / "issue-7"
        write(self.transcripts, "app/s1.jsonl", [command(app, "plan"), entry(app),
                                                 skill_call(app, "review-pr", "msg_a", "req_a"), entry(app)])
        write(self.transcripts, "loop/s2.jsonl", [command(issue, "plan"), entry(issue)])
        write(self.transcripts, "loop/s2/subagents/agent-c.jsonl", [entry(issue)])
        write(self.transcripts, "loop/s2/subagents/agent-c.meta.json", [{"agentType": "reviewer"}])
        self.assertEqual(self.activity(), {"agents": {}, "skills": {}, "commands": {}})

    def test_a_skill_started_at_the_root_keeps_its_replies_after_the_move_into_projects(self):
        app = self.root / "projects" / "app"
        write(self.transcripts, "proj/s1.jsonl", [
            said(self.root, "review this"), skill_call(self.root, "review-pr", "msg_call", "req_call"),
            entry(self.root, id="msg_call", req="req_call"), tool_result(app), entry(app), entry(app)])
        self.assertEqual(self.activity()["skills"], {"review-pr": {"runs": 1, "models": TWO}})

    def test_a_skill_called_after_the_move_into_projects_counts(self):
        app = self.root / "projects" / "app"
        write(self.transcripts, "proj/s1.jsonl", [
            said(self.root, "go"), skill_call(app, "review-pr", "msg_call", "req_call"),
            entry(app, id="msg_call", req="req_call"), entry(app)])
        self.assertEqual(self.activity()["skills"], {"review-pr": {"runs": 1, "models": ONE}})

    def test_a_subagent_under_projects_follows_a_session_started_at_the_root(self):
        app = self.root / "projects" / "app"
        write(self.transcripts, "proj/s1.jsonl", [entry(self.root)])
        write(self.transcripts, "proj/s1/subagents/agent-a.jsonl", [entry(app, sidechain=True), entry(app, sidechain=True)])
        write(self.transcripts, "proj/s1/subagents/agent-a.meta.json", [{"agentType": "reviewer"}])
        self.assertEqual(self.activity()["agents"], {"reviewer": {"runs": 1, "models": TWO}})

    def test_a_subagent_decides_for_itself_when_its_session_cant(self):
        app = self.root / "projects" / "app"
        for session in (None, [{"type": "summary"}], [entry(self.root, sidechain=True)]):
            with self.subTest(session):
                folder = Path(tempfile.mkdtemp(dir=self.transcripts))
                if session:
                    write(folder, "proj/s1.jsonl", session)
                write(folder, "proj/s1/subagents/agent-a.jsonl", [entry(self.root, sidechain=True), entry(app, sidechain=True)])
                found = token_report.activity(folder, SINCE, self.root, self.loop)
                self.assertEqual(found["agents"], {"agent type not recorded": {"runs": 1, "models": TWO}})

    def test_a_start_out_of_scope_doesnt_use_up_its_key(self):
        app = self.root / "projects" / "app"
        write(self.transcripts, "a/s1.jsonl", [said(app, "go"), skill_call(app, "review-pr", "msg_call", "req_call")])
        write(self.transcripts, "b/s2.jsonl", [said(self.root, "go"), skill_call(self.root, "review-pr", "msg_call", "req_call"),
                                               entry(self.root)])
        self.assertEqual(self.activity()["skills"], {"review-pr": {"runs": 1, "models": ONE}})

    def test_a_session_started_under_projects_stays_out_and_so_does_its_subagent(self):
        app = self.root / "projects" / "app"
        write(self.transcripts, "proj/s1.jsonl", [command(app, "plan"), entry(app)])
        write(self.transcripts, "proj/s1/subagents/agent-a.jsonl", [entry(self.root), entry(app)])
        write(self.transcripts, "proj/s1/subagents/agent-a.meta.json", [{"agentType": "reviewer"}])
        found = self.activity()
        self.assertEqual(found["commands"], {})
        self.assertEqual(found["agents"], {"reviewer": {"runs": 1, "models": ONE}})

    def test_a_line_in_another_folder_doesnt_count_and_leaves_the_span_open(self):
        write(self.transcripts, "proj/s1.jsonl", [command(self.root, "plan"), entry(self.root.parent), entry(self.root)])
        self.assertEqual(self.activity()["commands"], {"plan": {"runs": 1, "models": ONE}})

    def test_a_session_that_moves_into_a_loop_worktree_doesnt_count_there(self):
        write(self.transcripts, "proj/s1.jsonl", [command(self.root, "plan"), entry(self.root), entry(self.loop / "issue-7")])
        self.assertEqual(self.activity()["commands"], {"plan": {"runs": 1, "models": ONE}})

    def test_a_prompt_typed_elsewhere_closes_the_span(self):
        write(self.transcripts, "proj/s1.jsonl", [command(self.root, "plan"), entry(self.root),
                                                  said(self.root.parent, "next"), entry(self.root)])
        self.assertEqual(self.activity()["commands"], {"plan": {"runs": 1, "models": ONE}})

    def test_a_skill_called_elsewhere_closes_the_span_and_isnt_a_run(self):
        write(self.transcripts, "proj/s1.jsonl", [command(self.root, "plan"), entry(self.root),
                                                  skill_call(self.root.parent, "review-pr", "msg_call", "req_call"),
                                                  entry(self.root)])
        found = self.activity()
        self.assertEqual(found["commands"], {"plan": {"runs": 1, "models": ONE}})
        self.assertEqual(found["skills"], {})

    def test_a_first_line_before_since_still_says_where_the_session_started(self):
        app = self.root / "projects" / "app"
        write(self.transcripts, "proj/s1.jsonl", [entry(self.root, ts="2026-09-01T12:00:00.000Z"),
                                                  command(app, "plan"), entry(app)])
        self.assertEqual(self.activity()["commands"], {"plan": {"runs": 1, "models": ONE}})

    def test_a_reply_repeated_across_two_files_counts_once(self):
        app = self.root / "projects" / "app"
        write(self.transcripts, "a/s1.jsonl", [command(self.root, "plan"), entry(app, id="msg_r", req="req_r")])
        write(self.transcripts, "b/s2.jsonl", [command(self.root, "review"), entry(app, id="msg_r", req="req_r")])
        found = self.activity()["commands"]
        self.assertEqual(found["plan"], {"runs": 1, "models": ONE})
        self.assertEqual(found["review"], {"runs": 1, "models": {}})

    def test_the_section_is_printed_most_tokens_first_without_prompts_or_arguments(self):
        write(self.transcripts, "proj/s1.jsonl", [
            command(ROOT, "plan", args="args-text-zq8"), entry(ROOT), said(ROOT, "prompt-text-zq8"),
            command(ROOT, "review"), entry(ROOT), entry(ROOT)])
        result = run("--projects", str(self.transcripts), "--since", SINCE)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        for heading in ("## By activity", "### Agents", "### Skills", "### Commands",
                        "| Command | Runs | Input | Output | Cache writes | Cache reads | Total |"):
            self.assertIn(heading, out)
        self.assertEqual(out.count(token_report.ATTRIBUTED), 2)
        self.assertLess(out.index("| review | 1 | 20 |"), out.index("| plan | 1 | 10 |"))
        for leak in ("args-text-zq8", "prompt-text-zq8"):
            self.assertNotIn(leak, out)


class QuotedCommandTag(Harness):
    """A <command-name> counts only where Claude Code writes it, holding a command-shaped name."""

    def name_in(self, text):
        return token_report.command_name(said(self.root, text))

    def test_a_tag_that_isnt_a_commands_own_is_no_command(self):
        for text in ("see <command-name>/standup</command-name> in the log",
                     "see <command-name></command-name> in the log",
                     "<command-message>plan</command-message> pasted <command-name>/plan</command-name>",
                     "<command-name>words with spaces</command-name>",
                     "<command-message>a</command-message> pasted text "
                     "<command-message>b</command-message><command-name>x</command-name>"):
            with self.subTest(text):
                self.assertIsNone(self.name_in(text))

    def test_a_commands_own_tag_still_gives_its_name(self):
        for text, name in (("<command-name>/standup</command-name>", "standup"),
                           ("<command-name>standup</command-name>", "standup"),
                           ("<command-name>/plugin:skill</command-name>", "plugin:skill"),
                           ("<command-message>plan</command-message>\n<command-name>/plan</command-name>", "plan"),
                           ("<command-name></command-name>", "")):
            with self.subTest(text):
                self.assertEqual(self.name_in(text), name)

    def test_a_quoted_tag_doesnt_reach_the_report(self):
        write(self.transcripts, "proj/s1.jsonl", [
            said(self.root, "<command-name>quoted marker-zq9 text</command-name>"), entry(self.root)])
        found = token_report.activity(self.transcripts, SINCE, self.root, self.loop)
        out = token_report.report(token_report.read(self.transcripts, SINCE), SINCE, "2026-10-22",
                                  self.root, self.loop, activity=found)
        self.assertNotIn("marker-zq9", out)
        self.assertIn("Total: 100 tokens", out)

    def test_a_prompt_quoting_a_tag_closes_the_span_and_opens_no_command(self):
        for quoted in ("see <command-name></command-name> in the log",
                       "see <command-name>/plan</command-name> in the log"):
            with self.subTest(quoted):
                write(self.transcripts, "proj/s1.jsonl", [
                    skill_call(self.root, "review-pr", "msg_call", "req_call"),
                    entry(self.root, id="msg_call", req="req_call"), entry(self.root),
                    said(self.root, quoted), entry(self.root)])
                found = token_report.activity(self.transcripts, SINCE, self.root, self.loop)
                self.assertEqual(found["commands"], {})
                self.assertEqual(found["skills"], {"review-pr": {"runs": 1, "models": ONE}})


class BadInput(Harness):
    def test_junk_lines_and_odd_shapes_are_skipped(self):
        bad_usage = entry(self.root)
        bad_usage["message"]["usage"] = [1, 2]
        no_message = entry(self.root)
        no_message["message"] = "text"
        odd_counts = entry(self.root, usage={"input_tokens": "lots", "output_tokens": None, "cache_read_input_tokens": 5})
        write(self.transcripts, "proj/s1.jsonl",
              ["not json", "[1, 2]", "", "{\"broken\":", bad_usage, no_message, odd_counts])
        found = token_report.read(self.transcripts, SINCE)
        self.assertEqual(len(found), 1)
        self.assertIn("Total: 5 tokens", token_report.report(found, SINCE, "2026-10-22", self.root, self.loop))

    def test_a_missing_folder_reads_as_nothing(self):
        self.assertEqual(token_report.read(self.transcripts / "missing", SINCE), [])

    def test_an_empty_run_exits_0(self):
        result = run("--projects", str(self.transcripts / "missing"), "--since", SINCE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "No Claude Code usage under this harness since 2026-10-01.")


if __name__ == "__main__":
    unittest.main()
