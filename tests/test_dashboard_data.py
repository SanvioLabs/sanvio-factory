"""Run with: python3 -m unittest discover -s tests"""
import contextlib
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import dashboard_data  # noqa: E402 (needs scripts/ on the path first)
import token_report  # noqa: E402 (same reason)
from log_chain import link  # noqa: E402 (same reason)
from usage_report import log_path  # noqa: E402 (same reason)

TODAY = datetime.date(2026, 10, 27)
SINCE = "2026-10-15"
LEAK = "sentinel-zq7"  # put in every field the output must never carry
NOW = datetime.datetime(2026, 10, 27, 12, 0, tzinfo=datetime.timezone.utc)
SYSTEM_PATH = "/usr/bin:/bin"  # for the fake gh's own commands; the real gh isn't on it
# A real run of build(), kept in the dashboard mod for its tests to draw. Sample checks it and rewrites it.
SAMPLE = ROOT / "examples" / "mods" / "factory-dashboard" / "hooks" / "sample.ts"
UPDATE_SAMPLE = "UPDATE_SAMPLE=1 python3 -m unittest tests.test_dashboard_data.Sample"
SAMPLE_HEAD = ("// What scripts/dashboard_data.py's build() printed in tests/test_dashboard_data.py's Sample. Don't edit it:\n"
               "// " + UPDATE_SAMPLE + " writes it again.\n"
               "import type { Doc } from '../types'\n\n"
               "export const SAMPLE: Doc = ")


def check_run(status, conclusion):
    return {"__typename": "CheckRun", "name": "tests", "status": status, "conclusion": conclusion,
            "detailsUrl": "https://github.com/o/r/actions/runs/1?" + LEAK}


def commit_status(state):
    return {"__typename": "StatusContext", "context": "ci", "state": state,
            "targetUrl": "https://github.com/o/r/status?" + LEAK}


def pr(number, created, branch, draft=False, mergeable="MERGEABLE", rollup=(), title=None):
    """One row of gh pr list --json, with the fields dashboard_data asks for."""
    return {"number": number, "title": title or "PR {} {}".format(number, LEAK), "createdAt": created,
            "headRefName": branch, "isDraft": draft, "mergeable": mergeable, "statusCheckRollup": list(rollup)}


PRS = [pr(41, "2026-10-27T09:30:00Z", "loop/issue-264",
          rollup=[check_run("COMPLETED", "SUCCESS"), commit_status("SUCCESS")]),
       pr(42, "2026-10-25T12:00:00Z", "fix-typo", draft=True, mergeable="CONFLICTING",
          rollup=[check_run("COMPLETED", "SUCCESS"), check_run("COMPLETED", "FAILURE")]),
       pr(43, "2026-10-27T11:00:00Z", "loop/issue-7-old", mergeable="UNKNOWN",
          rollup=[check_run("COMPLETED", "SUCCESS"), check_run("IN_PROGRESS", "")]),
       pr(44, "2026-10-27T11:00:00Z", "loop/issue-8", rollup=[commit_status("PENDING")]),
       pr(45, "2026-10-27T11:00:00Z", "docs", rollup=[commit_status("ERROR"), check_run("QUEUED", "")]),
       pr(46, "2026-10-27T11:00:00Z", "docs-2")]


def fake_gh(folder, script):
    """A gh in folder that runs the shell script given, for PATH to find instead of the real one."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "gh"
    path.write_text("#!/bin/sh\n" + script + "\n")
    path.chmod(0o755)

# A stand-in for gh, found on PATH. It logs each call, answers pr list from prs-<state>.json for its
# --state, or prs.json when there's none ([] when neither is there), api graphql by printing each page
# in search.json (failing when there's none), and pulls/<n>/commits from commits.json's pages for n, and
# exits 1 while a file named fail exists.
GH = """#!PYTHON
import json, os, sys
folder = FOLDER
args = sys.argv[1:]
with open(os.path.join(folder, "calls"), "a") as f:
    f.write(" ".join(args) + "\\n")
if os.path.exists(os.path.join(folder, "fail")):
    sys.exit(1)
if args[:2] == ["pr", "list"]:
    state = args[args.index("--state") + 1] if "--state" in args else ""
    path = os.path.join(folder, "prs-" + state + ".json")
    if not os.path.exists(path):
        path = os.path.join(folder, "prs.json")
    print(open(path).read() if os.path.exists(path) else "[]")
elif args[:2] == ["api", "graphql"]:
    path = os.path.join(folder, "search.json")
    if not os.path.exists(path):
        sys.exit(1)
    for page in json.load(open(path)):
        print(json.dumps(page))
elif args[:1] == ["api"]:
    for page in json.load(open(os.path.join(folder, "commits.json")))[args[1].split("/")[-2]]:
        print(json.dumps(page))
else:
    sys.exit(1)
"""


def run(started, step, model, tokens, cost):
    """One usage.json entry, the shape loop.py's record_usage() writes."""
    return {"step": step, "round": 1, "run_started": started, "reported": True, "model": model,
            "input_tokens": tokens, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0,
            "cost_usd": cost}


def write(folder, relative, content):
    path = Path(folder) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    return path


class Factory(unittest.TestCase):
    """A temporary harness root, empty until a test fills it."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / ("harness-" + LEAK)
        self.root.mkdir()
        self.transcripts = Path(tmp.name).resolve() / "transcripts"  # not there until a test writes one
        # A gh that fails unless a test says otherwise, so no test reaches the real one.
        self.bin = Path(tmp.name).resolve() / "bin"
        fake_gh(self.bin, "exit 1")
        patcher = mock.patch.dict(os.environ, {"PATH": str(self.bin) + os.pathsep + SYSTEM_PATH})
        patcher.start()
        self.addCleanup(patcher.stop)

    def gh(self, prs):
        """Make gh print prs as gh pr list --json would."""
        write(self.bin, "prs.json", prs)
        fake_gh(self.bin, 'cat "{}"'.format(self.bin / "prs.json"))

    def answer_gh(self):
        """Put GH in place of the gh that fails, answering from files in self.bin and logging each call there."""
        fake = self.bin / "gh"
        fake.write_text(GH.replace("PYTHON", sys.executable).replace("FOLDER", repr(str(self.bin))))
        fake.chmod(0o755)

    def fill(self):
        write(self.root, ".loop/issue-7/usage.json", [
            run("2026-10-27T09:00:00", "plan", "claude-a", 100, 1.0),
            run("2026-10-27T09:00:00", "build", None, 200, 0.5),
            run("2026-10-22T09:00:00", "plan", "claude-a", 10, 0.25)])
        write(self.root, ".loop/issue-9/usage.json", [
            run("2026-10-16T09:00:00", "plan", "claude-b", 1000, 2.0),
            run("2026-10-01T09:00:00", "plan", "claude-b", 5000, 9.0)])
        write(self.root, ".loop/projects/app/issue-3/usage.json", [
            run("2026-10-27T10:00:00", "review", "claude-a", 5, 0.25)])
        write(self.root, ".loop/status.json", {"queue": [], "issues": [
            {"number": 7, "title": LEAK, "state": "pr", "round": 2, "note": LEAK,
             "pr": "https://github.com/o/r/pull/1?" + LEAK},
            {"number": 9, "title": LEAK, "state": "blocked", "round": 3, "pr": None, "note": LEAK},
            {"number": 12, "title": "", "state": "building", "round": 1, "pr": None, "note": ""}]})
        write(self.root, ".loop/projects/app/status.json", {"issues": [
            {"number": 3, "title": LEAK, "state": "pr", "round": 1, "pr": "https://github.com/o/app/pull/4"}]})
        lines = [{"ts": "2026-10-20T10:00:00Z", "event": "skill", "name": "review-pr"},
                 {"ts": "2026-10-21T10:00:00Z", "event": "skill", "name": "review-pr"},
                 {"ts": "2026-10-21T10:00:00Z", "event": "skill", "name": "learn"},
                 {"ts": "2026-10-21T10:00:00Z", "event": "agent", "name": "reviewer"},
                 {"ts": "2026-10-21T10:00:00Z", "event": "command", "name": "standup", "prompt": LEAK},
                 {"ts": "2026-10-22T10:00:00Z", "event": "guard_deny", "rule": "credential-file"},
                 {"ts": "2026-10-22T10:00:00Z", "event": "guard_deny", "rule": "credential-file"},
                 {"ts": "2026-10-22T10:00:00Z", "event": "guard_ask", "rule": "connector-write",
                  "tool": "mcp__" + LEAK},
                 {"ts": "2026-10-01T10:00:00Z", "event": "skill", "name": "too-old"}]
        write(log_path(self.root).parent, log_path(self.root).name,
              "\n".join(json.dumps(l) for l in lines) + "\nnot json\n")
        saved = {"agent": "claude --" + LEAK, "folder": str(self.root / LEAK)}
        write(self.root, ".sanvio/evals/2026-10-20T0900-reviewer.json",
              dict(saved, reviewer="reviewer", saved="2026-10-20T09:00:00+00:00",
                   cases={"01-a": {"status": "failing", "reasons": ["missed: " + LEAK]}}))
        write(self.root, ".sanvio/evals/2026-10-25T0900-reviewer.json",
              dict(saved, reviewer="reviewer", saved="2026-10-25T09:00:00+00:00",
                   cases={"01-a": {"status": "stable", "reasons": []},
                          "02-b": {"status": "flaky", "reasons": ["missed: " + LEAK]},
                          "03-c": {"status": "failing", "reasons": ["missed: " + LEAK]}}))
        write(self.root, ".sanvio/evals/2026-10-26T0900-security-reviewer.json",
              dict(saved, reviewer="security-reviewer", saved="2026-10-26T09:00:00+00:00",
                   cases={"01-x": {"status": "stable", "reasons": []}}))
        write(self.root, ".sanvio/evals/2026-10-27T0900-broken.json", "not json")

    def build(self, since=SINCE):
        return dashboard_data.build(self.root, since, TODAY, NOW, projects_dir=self.transcripts)

    def main(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = dashboard_data.main(["--json", "--since", SINCE, *args], root=self.root,
                                       projects_dir=self.transcripts)
        return code, out.getvalue()


class Layout(Factory):
    def test_the_top_level_keys(self):
        self.fill()
        code, out = self.main()
        self.assertEqual(code, 0)
        found = json.loads(out)
        self.assertEqual(list(found), ["schema", "generated", "since", "loop_spend", "loop_throughput", "activity",
                                       "evals", "conversations", "waiting", "loop_rework", "stage_times",
                                       "loop_history", "work_by_type", "last_review"])
        self.assertEqual(found["schema"], 2)
        self.assertEqual(found["since"], SINCE)
        self.assertIsNotNone(datetime.datetime.fromisoformat(found["generated"]).tzinfo)

    def test_the_conversations_sides_match_the_schema(self):
        # The side names conversations prints, for each schema. SIDES' keys are token_report's group
        # names and don't reach the document, so only its values are pinned.
        SIDES_BY_SCHEMA = {2: ["factory", "loop"]}
        self.assertEqual(sorted(set(dashboard_data.SIDES.values())), SIDES_BY_SCHEMA.get(dashboard_data.SCHEMA),
                         "conversations' sides changed: raise SCHEMA and add a row to SIDES_BY_SCHEMA")

    def test_the_docstring_says_when_schema_goes_up(self):
        doc = dashboard_data.__doc__
        self.assertIn("schema", doc)
        self.assertIn("It goes up when a section's shape changes", doc)

    def test_the_docstring_lists_the_schema_versions(self):
        self.assertIn('where 1 called it "harness"', dashboard_data.__doc__)

    def test_the_activity_docs_say_which_sessions_count(self):
        readme = (ROOT / "examples/mods/factory-dashboard/README.md").read_text(encoding="utf-8")
        doc = dashboard_data.__doc__
        self.assertNotIn("conversations at the factory's root", doc)
        self.assertNotIn("conversations at the factory's root", readme)
        self.assertIn("including after they move into", doc)

    def test_the_activity_docs_say_what_chain_holds(self):
        doc = dashboard_data.__doc__
        section = doc[doc.index("\n    activity "):doc.index("\n    evals ")]
        self.assertIn("unchained", section)

    def test_without_json_it_refuses(self):
        with self.assertRaises(SystemExit) as raised, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            dashboard_data.main([], root=self.root)
        self.assertEqual(raised.exception.code, 2)


class Spend(Factory):
    def test_today_the_last_7_days_and_since(self):
        self.fill()
        spend = self.build()["loop_spend"]
        self.assertEqual(spend["today"], {"tokens": 305, "cost_usd": 1.75})
        self.assertEqual(spend["last_7_days"], {"tokens": 315, "cost_usd": 2.0})
        self.assertEqual(spend["since"], {"tokens": 1315, "cost_usd": 4.0})
        self.assertEqual(spend["by_issue"], {"app/issue-3": {"tokens": 5, "cost_usd": 0.25},
                                             "issue-7": {"tokens": 310, "cost_usd": 1.75},
                                             "issue-9": {"tokens": 1000, "cost_usd": 2.0}})
        self.assertEqual(spend["by_step"], {"build": {"tokens": 200, "cost_usd": 0.5},
                                            "plan": {"tokens": 1110, "cost_usd": 3.25},
                                            "review": {"tokens": 5, "cost_usd": 0.25}})

    def test_by_model_puts_an_unrecorded_model_under_null(self):
        self.fill()
        self.assertEqual(self.build()["loop_spend"]["by_model"], {
            "claude-a": {"tokens": 115, "cost_usd": 1.5, "label": "claude-a"},
            "claude-b": {"tokens": 1000, "cost_usd": 2.0, "label": "claude-b"},
            "null": {"tokens": 200, "cost_usd": 0.5, "label": "model not recorded"}})

    def test_a_since_inside_the_week_still_gives_the_whole_week(self):
        self.fill()
        spend = self.build(since="2026-10-26")["loop_spend"]
        self.assertEqual(spend["last_7_days"], {"tokens": 315, "cost_usd": 2.0})
        self.assertEqual(spend["since"], {"tokens": 305, "cost_usd": 1.75})
        self.assertEqual(spend["by_issue"]["issue-7"], {"tokens": 300, "cost_usd": 1.5})

    def test_odd_numbers_in_a_record_are_left_out_not_counted(self):
        write(self.root, ".loop/issue-1/usage.json", [
            dict(run("2026-10-27T09:00:00", "plan", "m", 10, True), output_tokens="lots"),
            run("2026-10-27T09:00:00", "plan", "m", 5, "free")])
        self.assertEqual(self.build()["loop_spend"]["today"], {"tokens": 15, "cost_usd": None})


class SpendByDay(Factory):
    def test_every_day_from_since_to_today_with_zero_on_a_day_without_a_run(self):
        self.fill()
        spend = self.build()["loop_spend"]
        self.assertEqual([d["day"] for d in spend["by_day"]],
                         ["2026-10-{}".format(n) for n in range(15, 28)])
        found = {d["day"]: {"tokens": d["tokens"], "cost_usd": d["cost_usd"]} for d in spend["by_day"]}
        self.assertEqual(found["2026-10-16"], {"tokens": 1000, "cost_usd": 2.0})
        self.assertEqual(found["2026-10-22"], {"tokens": 10, "cost_usd": 0.25})
        self.assertEqual(found["2026-10-27"], {"tokens": 305, "cost_usd": 1.75})
        self.assertEqual(found["2026-10-20"], {"tokens": 0, "cost_usd": 0.0})
        self.assertEqual({"tokens": sum(d["tokens"] for d in found.values()),
                          "cost_usd": round(sum(d["cost_usd"] for d in found.values()), 4)}, spend["since"])

    def test_first_run_is_the_earliest_day_counted_and_ignores_a_run_before_since(self):
        self.fill()  # issue-9 also ran on 2026-10-01, before SINCE
        self.assertEqual(self.build()["loop_spend"]["first_run"], "2026-10-16")
        self.assertEqual(self.build(since="2026-10-26")["loop_spend"]["first_run"], "2026-10-27")

    def test_a_day_whose_runs_recorded_no_cost_has_cost_null(self):
        write(self.root, ".loop/issue-7/usage.json", [run("2026-10-20T09:00:00", "plan", "m", 10, None)])
        found = {d["day"]: d for d in self.build()["loop_spend"]["by_day"]}
        self.assertEqual(found["2026-10-20"], {"day": "2026-10-20", "tokens": 10, "cost_usd": None})

    def test_a_run_dated_after_today_counts_in_since_but_has_no_day(self):
        self.fill()
        write(self.root, ".loop/issue-11/usage.json", [run("2026-10-28T09:00:00", "plan", "m", 7, 0.5)])
        spend = self.build()["loop_spend"]
        self.assertEqual(spend["by_day"][-1]["day"], "2026-10-27")
        self.assertEqual(spend["since"], {"tokens": 1315 + 7, "cost_usd": 4.0 + 0.5})
        self.assertEqual(sum(d["tokens"] for d in spend["by_day"]), 1315)

    def test_no_run_counted_gives_no_first_run_and_every_day_zero(self):
        write(self.root, ".loop/issue-7/usage.json", [run("2026-09-01T09:00:00", "plan", "m", 10, 1.0)])
        spend = self.build()["loop_spend"]
        self.assertIsNone(spend["first_run"])
        self.assertEqual(len(spend["by_day"]), 13)
        self.assertTrue(all((d["tokens"], d["cost_usd"]) == (0, 0.0) for d in spend["by_day"]))


class CostPerPr(Factory):
    def test_the_since_cost_over_the_issues_with_a_pull_request(self):
        self.fill()
        self.assertEqual(self.build()["loop_spend"]["cost_per_pr"], 2.0)

    def test_only_issues_that_ran_in_the_period_and_status_json_lists(self):
        self.fill()
        # #5 has a pull request but no run since SINCE; #11 ran but has dropped off status.json.
        found = json.loads((self.root / ".loop" / "status.json").read_text())
        found["issues"].append({"number": 5, "state": "pr", "round": 1, "pr": "https://github.com/o/r/pull/2"})
        write(self.root, ".loop/status.json", found)
        write(self.root, ".loop/issue-5/usage.json", [run("2026-10-01T09:00:00", "plan", "claude-a", 1, 8.0)])
        write(self.root, ".loop/issue-11/usage.json", [run("2026-10-20T09:00:00", "plan", "claude-a", 1, 6.0)])
        self.assertEqual(self.build()["loop_spend"]["cost_per_pr"], 2.0)

    def test_no_pull_request_gives_null(self):
        self.fill()
        write(self.root, ".loop/status.json", {"issues": [{"number": 7, "state": "blocked", "pr": None}]})
        write(self.root, ".loop/projects/app/status.json", {"issues": []})
        self.assertIsNone(self.build()["loop_spend"]["cost_per_pr"])

    def test_no_status_json_leaves_spend_but_not_cost_per_pr(self):
        self.fill()
        (self.root / ".loop" / "status.json").unlink()
        (self.root / ".loop" / "projects" / "app" / "status.json").unlink()
        spend = self.build()["loop_spend"]
        self.assertEqual(spend["since"], {"tokens": 1315, "cost_usd": 4.0})
        self.assertIsNone(spend["cost_per_pr"])


class Throughput(Factory):
    def test_states_rounds_and_repeats_across_the_harness_and_projects(self):
        self.fill()
        self.assertEqual(self.build()["loop_throughput"], {
            "issues": 4, "by_state": {"pr": 2, "blocked": 1, "building": 1},
            "rounds": {"app/issue-3": 1, "issue-7": 2, "issue-9": 3, "issue-12": 1},
            "more_than_one_round": 2})


class Activity(Factory):
    def test_counts_by_name_rule_and_asks_since_the_date(self):
        self.fill()
        self.assertEqual(self.build()["activity"], {
            "skills": {"review-pr": 2, "learn": 1}, "agents": {"reviewer": 1}, "commands": {"standup": 1},
            "guard_refusals": {"credential-file": 2}, "asks": 1, "log_off": 0, "chain": "unchained"})

    def test_counts_the_sessions_started_with_the_log_off_since_the_date(self):
        lines = [{"ts": "2026-10-01T10:00:00Z", "event": "log_off"},  # before SINCE
                 {"ts": "2026-10-20T10:00:00Z", "event": "log_off"},
                 {"ts": "2026-10-21T10:00:00Z", "event": "session_start", "session": "s1"},
                 {"ts": "2026-10-22T10:00:00Z", "event": "log_off"}]
        write(log_path(self.root).parent, log_path(self.root).name,
              "".join(json.dumps(line) + "\n" for line in lines))
        self.assertEqual(self.build()["activity"]["log_off"], 2)

    def write_chained(self, path, edit=False):
        """Five lines chained with link() at path, with line 3's name changed after it was written when edit is set."""
        lines = []
        for n in range(1, 6):
            entry = {"ts": "2026-10-2{}T10:00:00Z".format(n), "event": "skill", "name": "skill-{}".format(n)}
            lines.append(json.dumps(link(lines[-1] if lines else None, entry)))
        if edit:
            changed = json.loads(lines[2])
            changed["name"] = "something-else"
            lines[2] = json.dumps(changed)
        write(path.parent, path.name, "".join(line + "\n" for line in lines))

    def test_a_chained_log_is_intact(self):
        self.write_chained(log_path(self.root))
        self.assertEqual(self.build()["activity"]["chain"], "intact")

    def test_an_edited_log_gives_the_line_it_changed_from(self):
        self.write_chained(log_path(self.root), edit=True)
        self.assertEqual(self.build()["activity"]["chain"], 4)

    def test_an_edit_from_before_since_still_gives_its_line(self):
        # Line 3 is from 2026-10-23, before since; the whole log is checked, not just the window.
        self.write_chained(log_path(self.root), edit=True)
        activity = self.build(since="2026-10-24")["activity"]
        self.assertEqual(activity["skills"], {"skill-4": 1, "skill-5": 1})
        self.assertEqual(activity["chain"], 4)

    def test_someone_elses_edited_log_leaves_yours_intact(self):
        mine = log_path(self.root)
        self.write_chained(mine)
        self.write_chained(mine.with_name("other-" + mine.name), edit=True)
        self.assertEqual(self.build()["activity"]["chain"], "intact")


class Evals(Factory):
    def test_the_newest_file_for_each_reviewer(self):
        self.fill()
        gone = {"stale": True, "changed": [], "newest_change": None, "why": "folder missing"}
        self.assertEqual(self.build()["evals"], {
            "reviewer": dict(gone, saved="2026-10-25T09:00:00+00:00", stable=1, flaky=1, failing=1,
                             failing_cases=["03-c"]),
            "security-reviewer": dict(gone, saved="2026-10-26T09:00:00+00:00", stable=1, flaky=0, failing=0,
                                      failing_cases=[])})


class GitHarness(Factory):
    """A harness root that is a git repo, with git's own settings and the machine's left out."""

    def setUp(self):
        super().setUp()
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        patched = mock.patch.dict(os.environ, env, clear=True)
        patched.start()
        self.addCleanup(patched.stop)
        self.git("init", "-q")

    def git(self, *args, date=None):
        env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date) if date else None
        return subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@example.com",
                               *args], check=True, capture_output=True, text=True, env=env).stdout

    def commit(self, date):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change", date=date)
        # The tests turn on this date, so a commit git dated otherwise fails here rather than as a fresh result.
        # Some versions of git print UTC as Z and others as +00:00, so the times are compared, not the text.
        self.assertEqual(dashboard_data.when(self.git("log", "-1", "--format=%cI").strip()),
                         dashboard_data.when(date))


class StaleEvals(GitHarness):
    """A saved result in a git repo holding the files its one case rests on, all committed before it was saved."""

    SAVED = "2026-10-25T09:00:00+00:00"

    def setUp(self):
        super().setUp()
        write(self.root, "agents/reviewer.md", "the reviewer\n")
        write(self.root, "scripts/eval_agents.py", "# the eval\n")
        write(self.root, "briefs/proposal.md", "the brief\n")
        write(self.root, "evals/01-x/case.json", {"agent": "reviewer", "brief": "briefs/proposal.md"})
        write(self.root, "evals/01-x/work.md", "the work\n")
        write(self.root, "notes.md", "read by no case\n")
        self.commit("2026-10-20T09:00:00+00:00")
        self.save("reviewer")

    def save(self, reviewer, **fields):
        result = {"reviewer": reviewer, "folder": "evals", "saved": self.SAVED, "cases": {"01-x": {"status": "stable"}}}
        write(self.root, ".sanvio/evals/2026-10-25T0900-{}.json".format(reviewer), dict(result, **fields))

    def stale(self, reviewer="reviewer"):
        found = self.build()["evals"][reviewer]
        return {k: found[k] for k in ("stale", "changed", "newest_change", "why") if k in found}

    def test_files_last_committed_before_it_was_saved_leave_it_fresh(self):
        write(self.root, "notes.md", "changed, but no case reads it\n")
        self.commit("2026-10-26T09:00:00+00:00")
        self.assertEqual(self.stale(), {"stale": False, "changed": [], "newest_change": None})

    def test_a_commit_to_the_brief_after_it_was_saved_makes_it_stale(self):
        write(self.root, "briefs/proposal.md", "the brief, rewritten\n")
        self.commit("2026-10-26T09:00:00+00:00")
        self.assertEqual(self.stale(), {"stale": True, "changed": ["briefs/proposal.md"],
                                        "newest_change": "2026-10-26T09:00:00+00:00"})

    def test_an_uncommitted_edit_to_the_work_makes_it_stale(self):
        work = write(self.root, "evals/01-x/work.md", "the work, edited\n")
        written = datetime.datetime(2026, 10, 26, 12, 0, tzinfo=datetime.timezone.utc)
        os.utime(work, (written.timestamp(), written.timestamp()))
        found = self.stale()
        self.assertEqual((found["stale"], found["changed"]), (True, ["evals/01-x/work.md"]))
        self.assertEqual(datetime.datetime.fromisoformat(found["newest_change"]), written)

    def test_changed_names_each_file_from_the_root_and_newest_change_the_latest_commit(self):
        write(self.root, "evals/01-x/work.md", "the work, edited\n")
        self.commit("2026-10-26T09:00:00+00:00")
        write(self.root, "briefs/proposal.md", "the brief, rewritten\n")
        self.commit("2026-10-27T09:00:00+00:00")
        self.assertEqual(self.stale(), {"stale": True, "changed": ["briefs/proposal.md", "evals/01-x/work.md"],
                                        "newest_change": "2026-10-27T09:00:00+00:00"})
        self.assertNotIn(str(self.root), json.dumps(self.build()))

    def test_a_missing_folder_or_saved_time_stays_with_its_why(self):
        self.save("reviewer", folder="nowhere")
        self.save("security-reviewer", saved=None)
        self.assertEqual(self.stale(), {"stale": True, "changed": [], "newest_change": None, "why": "folder missing"})
        self.assertEqual(self.stale("security-reviewer"),
                         {"stale": True, "changed": [], "newest_change": None, "why": "no saved time"})

    def test_a_commit_dated_with_z_after_it_was_saved_makes_it_stale(self):
        # git prints Z on some versions, and fromisoformat() before Python 3.11 refuses it.
        write(self.root, "briefs/proposal.md", "the brief, rewritten\n")
        self.commit("2026-10-26T09:00:00Z")
        self.assertEqual(self.stale(), {"stale": True, "changed": ["briefs/proposal.md"],
                                        "newest_change": "2026-10-26T09:00:00+00:00"})

    def test_a_brief_git_ignores_written_after_it_was_saved_makes_it_stale(self):
        write(self.root, ".gitignore", "briefs/\n")
        self.git("rm", "-r", "-q", "--cached", "briefs")
        self.commit("2026-10-21T09:00:00+00:00")
        brief = self.root / "briefs" / "proposal.md"
        written = datetime.datetime(2026, 10, 26, 12, 0, tzinfo=datetime.timezone.utc)
        os.utime(brief, (written.timestamp(), written.timestamp()))
        found = self.stale()
        self.assertEqual((found["stale"], found["changed"]), (True, ["briefs/proposal.md"]))

    def test_a_reviewer_that_isnt_a_string_doesnt_stop_the_check(self):
        found = dashboard_data.freshness(self.root, {"reviewer": ["a"], "folder": "evals", "saved": self.SAVED})
        self.assertEqual(found, {"stale": False, "changed": [], "newest_change": None})

    def test_without_git_stale_is_null(self):
        shutil.rmtree(self.root / ".git")
        self.assertEqual(self.stale(), {"stale": None, "changed": [], "newest_change": None, "why": "no git"})


class When(unittest.TestCase):
    def test_a_trailing_z_is_utc_on_every_python(self):
        self.assertEqual(dashboard_data.when("2026-10-20T09:00:00Z"),
                         datetime.datetime(2026, 10, 20, 9, 0, tzinfo=datetime.timezone.utc))

    def test_anything_else_that_isnt_a_time_is_none(self):
        for text in (None, 3, "", "Z", "not a time"):
            self.assertIsNone(dashboard_data.when(text), text)


class PullRequests(Factory):
    def test_each_open_pull_request_with_its_wait_branch_draft_checks_and_conflicts(self):
        self.gh(PRS)
        found = self.build()["waiting"]["pull_requests"]
        self.assertEqual([(p["number"], p["loop_issue"], p["draft"], p["checks"], p["conflicts"]) for p in found], [
            (41, 264, False, "pass", False),
            (42, None, True, "fail", True),
            (43, None, False, "pending", None),
            (44, 8, False, "pending", False),
            (45, None, False, "fail", False),
            (46, None, False, None, False)])

    def test_title_opened_and_hours_waited_against_now(self):
        self.gh(PRS[:2])
        found = self.build()["waiting"]["pull_requests"]
        self.assertEqual(found[0], {"number": 41, "title": "PR 41 " + LEAK, "opened": "2026-10-27T09:30:00Z",
                                    "hours_waited": 2.5, "loop_issue": 264, "draft": False, "checks": "pass",
                                    "conflicts": False})
        self.assertEqual(found[1]["hours_waited"], 48.0)

    def test_no_open_pull_requests_is_an_empty_list(self):
        self.gh([])
        self.assertEqual(self.build()["waiting"]["pull_requests"], [])


class Blocked(Factory):
    def test_blocked_issues_with_title_note_and_update(self):
        self.fill()
        self.assertEqual(self.build()["waiting"]["blocked"], [
            {"issue": "issue-9", "number": 9, "title": LEAK, "note": LEAK, "updated": None}])

    def test_a_project_issue_carries_its_prefix(self):
        self.fill()
        write(self.root, ".loop/projects/app/status.json", {"issues": [
            {"number": 3, "state": "pr", "round": 1},
            {"number": 5, "title": "Stuck", "state": "blocked", "round": 2, "note": "tests failed twice",
             "updated": "2026-10-26T15:00:00", "pr": "https://github.com/o/app/pull/6"}]})
        self.assertEqual(self.build()["waiting"]["blocked"], [
            {"issue": "app/issue-5", "number": 5, "title": "Stuck", "note": "tests failed twice",
             "updated": "2026-10-26T15:00:00"},
            {"issue": "issue-9", "number": 9, "title": LEAK, "note": LEAK, "updated": None}])


class GhUnavailable(Factory):
    def assert_unavailable_but_blocked_filled(self):
        found = self.build()["waiting"]
        self.assertEqual(found["pull_requests"], {"value": None, "why": "gh unavailable"})
        self.assertEqual([b["issue"] for b in found["blocked"]], ["issue-9"])

    def test_gh_missing(self):
        self.fill()
        empty = self.root.parent / "empty"
        empty.mkdir()
        with mock.patch.dict(os.environ, {"PATH": str(empty)}):
            self.assert_unavailable_but_blocked_filled()

    def test_gh_failing_as_when_signed_out(self):
        self.fill()
        self.assert_unavailable_but_blocked_filled()

    def test_gh_printing_something_other_than_a_list(self):
        self.fill()
        for script in ("echo not json", "echo '{\"number\": 1}'"):
            with self.subTest(script=script):
                fake_gh(self.bin, script)
                self.assert_unavailable_but_blocked_filled()

    def test_gh_timing_out(self):
        self.fill()
        fake_gh(self.bin, "exec sleep 5")
        with mock.patch.object(dashboard_data, "GH_TIMEOUT", 0.2):
            self.assert_unavailable_but_blocked_filled()


def commit(message, parents=1):
    """One item from the pulls/<n>/commits API, the parts loop_rework reads and an author it mustn't keep."""
    return {"sha": "abc", "commit": {"message": message, "author": {"name": LEAK}},
            "parents": [{"sha": "p{}".format(i)} for i in range(parents)]}


class Rework(Factory):
    def setUp(self):
        super().setUp()
        self.answer_gh()
        loop = commit("Build it\n\nLoop: issue #1, round 1.")
        write(self.bin, "prs.json", [
            {"number": 101, "title": "All the loop's", "headRefName": "loop/issue-1", "mergedAt": "2026-10-20T12:00:00Z"},
            {"number": 102, "title": "Fixed by hand", "headRefName": "loop/issue-2", "mergedAt": "2026-10-21T12:00:00Z"},
            {"number": 103, "title": "Not the loop's", "headRefName": "feature/x", "mergedAt": "2026-10-22T12:00:00Z"},
            {"number": 104, "title": "Too old", "headRefName": "loop/issue-4", "mergedAt": "2026-10-01T12:00:00Z"}])
        # 102's commits come in two pages, as gh --paginate prints them.
        write(self.bin, "commits.json", {
            "101": [[loop, loop]],
            "102": [[loop, commit("Merge branch 'main' into loop/issue-2", parents=2)], [commit("fix " + LEAK)]],
            "103": [[commit("by hand")]], "104": [[commit("by hand")]]})

    def test_counts_the_loop_pull_requests_merged_since_and_the_reworked_ones(self):
        rework = self.build()["loop_rework"]
        self.assertEqual((rework["merged"], rework["reworked"]), (2, 1))

    def test_lists_each_reworked_pull_request_with_its_merges_and_other_commits(self):
        self.assertEqual(self.build()["loop_rework"]["pull_requests"], [
            {"number": 102, "title": "Fixed by hand", "merges_from_base": 1, "other_commits": 1}])

    def test_asks_gh_for_a_pull_requests_commits_once_and_caches_only_what_it_counts(self):
        first, second = self.build()["loop_rework"], self.build()["loop_rework"]
        self.assertEqual(first, second)
        calls = [c for c in (self.bin / "calls").read_text().splitlines() if "/commits" in c]
        self.assertEqual(sorted(c.split("/")[-2] for c in calls), ["101", "102"])
        cache = (self.root / ".sanvio" / "cache" / "loop_rework.json").read_text()
        self.assertEqual(sorted(json.loads(cache)), ["101", "102"])
        self.assertNotIn(LEAK, cache)

    def test_a_failed_fetch_keeps_the_commits_already_read_in_the_cache(self):
        commits = json.loads((self.bin / "commits.json").read_text())
        del commits["102"]  # the fake gh fails on 102, after reading 101
        write(self.bin, "commits.json", commits)
        self.assertEqual(self.build()["loop_rework"], {"value": None, "why": "gh failed"})
        cache = json.loads((self.root / ".sanvio" / "cache" / "loop_rework.json").read_text())
        self.assertEqual(sorted(cache), ["101"])

    def test_gh_failing_gives_null_and_why_and_exits_0(self):
        write(self.bin, "fail", "")
        code, out = self.main()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["loop_rework"], {"value": None, "why": "gh failed"})


def stage_row(number, started, **seconds):
    """One status.json row with the time it spent at each step, and a title and note it mustn't print."""
    return {"number": number, "title": LEAK, "state": "pr", "round": 1, "note": LEAK, "started": started,
            "step_seconds": seconds}


def merged_pr(number, branch, created, merged, reviews=()):
    """One row of gh pr list --state merged, opened by the loop's account, with each review as (login, time)."""
    return {"number": number, "title": LEAK, "headRefName": branch, "author": {"login": "loop-" + LEAK},
            "createdAt": created, "mergedAt": merged,
            "reviews": [{"author": {"login": who}, "submittedAt": at, "body": LEAK} for who, at in reviews]}


OTHER = "person-" + LEAK  # a reviewer who isn't the pull request's author


class StageTimes(Factory):
    """Four issues started since SINCE, one before it, and the loop's merged pull requests and a person's."""

    def setUp(self):
        super().setUp()
        self.answer_gh()
        write(self.root, ".loop/status.json", {"queue": [], "issues": [
            stage_row(1, "2026-10-16T09:00:00", SHAPE=120, BUILD=600, VALIDATE=1800, SCALE=60),
            stage_row(2, "2026-10-20T09:00:00", SHAPE=240, BUILD=1200, VALIDATE=3600, SCALE=120),
            stage_row(3, "2026-10-22T09:00:00", SHAPE=360, BUILD=900, VALIDATE=2400),  # no SCALE yet
            stage_row(4, "2026-10-01T09:00:00", SHAPE=99_999, BUILD=99_999, VALIDATE=99_999, SCALE=99_999),
            stage_row(6, "2026-10-23T09:00:00", SHAPE="600", BUILD=True),  # not numbers, so not counted
            {"number": 8, "title": LEAK, "state": "working", "step_seconds": {"SHAPE": 99_999}}]})  # never started
        write(self.root, ".loop/projects/app/status.json", {"issues": [
            stage_row(5, "2026-10-25T09:00:00", SHAPE=480, BUILD=300, VALIDATE=600, SCALE=180)]})
        write(self.bin, "prs-merged.json", [
            # 10 hours to merge; the author's own review at half an hour isn't the first, the person's at 2 hours is.
            merged_pr(101, "loop/issue-1", "2026-10-16T10:00:00Z", "2026-10-16T20:00:00Z",
                      [("loop-" + LEAK, "2026-10-16T10:30:00Z"), (OTHER, "2026-10-16T12:00:00Z")]),
            # 24 hours to merge, the earlier of two reviews at 1 hour.
            merged_pr(102, "loop/issue-2", "2026-10-20T10:00:00Z", "2026-10-21T10:00:00Z",
                      [(OTHER, "2026-10-20T14:00:00Z"), ("other-" + LEAK, "2026-10-20T11:00:00Z")]),
            # 6 hours to merge, reviewed only by its author.
            merged_pr(103, "loop/issue-3", "2026-10-22T00:00:00Z", "2026-10-22T06:00:00Z",
                      [("loop-" + LEAK, "2026-10-22T01:00:00Z")]),
            merged_pr(104, "feature/x", "2026-10-22T00:00:00Z", "2026-10-22T01:00:00Z",
                      [(OTHER, "2026-10-22T00:06:00Z")]),  # a person's pull request
            merged_pr(105, "loop/issue-4", "2026-10-01T00:00:00Z", "2026-10-05T04:00:00Z",
                      [(OTHER, "2026-10-01T00:06:00Z")])])  # merged before SINCE

    def stages(self):
        return self.build()["stage_times"]

    def test_the_median_minutes_of_each_step_for_odd_and_even_counts(self):
        steps = self.stages()["loop_steps"]
        self.assertEqual(steps["SCALE"], {"median_minutes": 2.0, "issues": 3})  # 1, 2 and 3 minutes
        self.assertEqual(steps["SHAPE"], {"median_minutes": 5.0, "issues": 4})  # between 4 and 6 minutes
        self.assertEqual(steps["BUILD"], {"median_minutes": 12.5, "issues": 4})
        self.assertEqual(steps["VALIDATE"], {"median_minutes": 35.0, "issues": 4})

    def test_the_median_hours_to_merge_and_to_first_review(self):
        self.assertEqual(self.stages()["pull_requests"], {"merged": 3, "median_hours_to_merge": 10.0,
                                                          "reviewed": 2, "median_hours_to_first_review": 1.5})

    def test_since_drops_an_issue_that_started_earlier_and_a_pull_request_merged_earlier(self):
        early = self.build(since="2026-09-01")["stage_times"]
        self.assertEqual(early["loop_steps"]["SHAPE"]["issues"], 5)
        self.assertEqual(early["pull_requests"]["merged"], 4)
        found = self.stages()
        self.assertEqual(found["loop_steps"]["SHAPE"]["issues"], 4)
        self.assertEqual(found["pull_requests"]["merged"], 3)

    def test_a_step_missing_from_one_issue_lowers_only_that_steps_count(self):
        steps = self.stages()["loop_steps"]
        self.assertEqual({step: steps[step]["issues"] for step in steps},
                         {"SHAPE": 4, "BUILD": 4, "VALIDATE": 4, "SCALE": 3})

    def test_slowest_names_the_largest_median(self):
        self.assertEqual(self.stages()["slowest"], "merge")  # 10 hours, ahead of the 35 minutes VALIDATE takes
        write(self.bin, "fail", "")
        self.assertEqual(self.stages()["slowest"], "VALIDATE")

    def test_slowest_is_none_with_2_issues_even_when_a_median_exists(self):
        write(self.root, ".loop/status.json", {"issues": [
            stage_row(1, "2026-10-16T09:00:00", SHAPE=120, BUILD=600, VALIDATE=1800, SCALE=60),
            stage_row(2, "2026-10-20T09:00:00", SHAPE=240, BUILD=1200, VALIDATE=3600, SCALE=120)]})
        (self.root / ".loop" / "projects" / "app" / "status.json").unlink()
        prs = json.loads((self.bin / "prs-merged.json").read_text())
        write(self.bin, "prs-merged.json", prs[:2])
        found = self.stages()
        self.assertEqual(found["loop_steps"]["VALIDATE"], {"median_minutes": 45.0, "issues": 2})
        self.assertEqual(found["pull_requests"]["merged"], 2)
        self.assertIsNone(found["slowest"])

    def test_a_pull_request_a_person_opened_isnt_counted(self):
        prs = json.loads((self.bin / "prs-merged.json").read_text())
        write(self.bin, "prs-merged.json", [p for p in prs if p["headRefName"] == "feature/x"])
        self.assertEqual(self.stages()["pull_requests"], {"merged": 0, "median_hours_to_merge": None,
                                                          "reviewed": 0, "median_hours_to_first_review": None})

    def test_a_review_by_the_author_isnt_a_first_review(self):
        prs = json.loads((self.bin / "prs-merged.json").read_text())
        write(self.bin, "prs-merged.json", [p for p in prs if p["number"] in (101, 103)])
        # 101's first review is the person's at 2 hours, not its author's at half an hour; 103 has no other reviewer.
        self.assertEqual(self.stages()["pull_requests"], {"merged": 2, "median_hours_to_merge": 8.0,
                                                          "reviewed": 1, "median_hours_to_first_review": 2.0})

    def test_no_status_json_leaves_the_pull_requests_filled(self):
        shutil.rmtree(self.root / ".loop")
        found = self.stages()
        self.assertEqual(found["loop_steps"], {"value": None, "why": "no status.json"})
        self.assertEqual(found["pull_requests"]["merged"], 3)
        self.assertEqual(found["slowest"], "merge")

    def test_an_unreadable_status_json_says_so(self):
        write(self.root, ".loop/status.json", "not json")
        write(self.root, ".loop/projects/app/status.json", ["not", "an", "object"])
        self.assertEqual(self.stages()["loop_steps"], {"value": None, "why": "unreadable"})

    def test_gh_failing_leaves_the_steps_filled_and_exits_0(self):
        write(self.bin, "fail", "")
        code, out = self.main()
        self.assertEqual(code, 0)
        found = json.loads(out)["stage_times"]
        self.assertEqual(found["pull_requests"], {"value": None, "why": "gh failed"})
        self.assertEqual(found["loop_steps"]["SHAPE"], {"median_minutes": 5.0, "issues": 4})

    def test_gh_printing_the_wrong_shape_counts_as_failed(self):
        write(self.bin, "prs-merged.json", {"number": 101})
        self.assertEqual(self.stages()["pull_requests"], {"value": None, "why": "gh failed"})

    def test_it_prints_no_title_note_or_login(self):
        code, out = self.main()
        self.assertEqual(code, 0)
        self.assertNotIn(LEAK, json.dumps(json.loads(out)["stage_times"]))

    def test_the_docstring_says_the_steps_cover_status_jsons_issues(self):
        self.assertIn("status.json keeps only the loop's 20 most recent issues (STATUS_KEEP), so the loop-step "
                      "medians cover those whatever --since says, the same limit cost_per_pr has.",
                      dashboard_data.__doc__)


def search_pr(number, branch, merged, labels=(), closes=(), title=None, author=None):
    """One pull request from work_report.py's GraphQL search, each of closes as (issue, its labels). Unless
    given, its title, address, author and its issues' bodies carry LEAK, which the section mustn't print."""
    def labelled(names):
        return {"nodes": [{"name": name} for name in names]}

    return {"number": number, "title": title or LEAK, "url": "https://github.com/o/r/pull/{}?{}".format(number, LEAK),
            "createdAt": merged, "mergedAt": merged, "headRefName": branch,
            "author": {"__typename": "User", "login": author or "person-" + LEAK}, "milestone": None,
            "labels": labelled(labels),
            "closingIssuesReferences": {"nodes": [{"number": n, "body": "Spec: " + LEAK, "milestone": None,
                                                   "labels": labelled(names)} for n, names in closes]},
            "reviews": {"nodes": []}, "approvals": {"nodes": []}}


def search_page(prs, matched):
    """One page of the search as gh --paginate prints it, matched being the search's whole count."""
    return {"data": {"search": {"issueCount": matched, "pageInfo": {"hasNextPage": False, "endCursor": None},
                                "nodes": list(prs)}}}


class WorkByType(Factory):
    """fill()'s loop records, and merged pull requests of every type over two pages: issue-7 (310 tokens,
    $1.75) closed by the loop's pull request and a person's, issue-9 (6000 tokens, $11.00 on every date)
    by one labelled bug whose issue says enhancement, and spend on issue-11 that nothing merged closes."""

    def setUp(self):
        super().setUp()
        self.fill()
        write(self.root, ".loop/issue-11/usage.json", [run("2026-10-20T09:00:00", "plan", "claude-a", 777, 7.0)])
        self.answer_gh()
        prs = [
            search_pr(201, "loop/issue-7", "2026-10-20T12:00:00Z", closes=[(7, ["enhancement"])]),  # typed by its issue
            search_pr(202, "feature/x", "2026-10-21T12:00:00Z", labels=["enhancement"], closes=[(7, [])]),
            search_pr(203, "loop/issue-9", "2026-10-22T12:00:00Z", labels=["bug"], closes=[(9, ["enhancement"])]),
            search_pr(204, "feature/docs", "2026-10-23T12:00:00Z", labels=["documentation"], closes=[(3, [])]),
            search_pr(205, "feature/y", "2026-10-24T12:00:00Z"),  # no type anywhere
            search_pr(206, "loop/issue-12", "2026-10-01T12:00:00Z", labels=["chore"], closes=[(9, [])])]  # before SINCE
        write(self.bin, "search.json", [search_page(prs[:3], len(prs)), search_page(prs[3:], len(prs))])

    def types(self, since=SINCE):
        return {row["type"]: row for row in self.build(since)["work_by_type"]["types"]}

    def test_every_type_then_untyped_in_order_with_its_counts_and_spend(self):
        self.assertEqual(self.build()["work_by_type"], {"types": [
            {"type": "bug", "merged": 1, "loop_built": 1, "issues": 1, "tokens": 6000, "cost_usd": 11.0},
            {"type": "enhancement", "merged": 2, "loop_built": 1, "issues": 1, "tokens": 310, "cost_usd": 1.75},
            {"type": "documentation", "merged": 1, "loop_built": 0, "issues": 1, "tokens": 0, "cost_usd": 0.0},
            {"type": "chore", "merged": 0, "loop_built": 0, "issues": 0, "tokens": 0, "cost_usd": 0.0},
            {"type": None, "merged": 1, "loop_built": 0, "issues": 0, "tokens": 0, "cost_usd": 0.0}],
            "truncated": False})

    def test_the_loops_pull_request_and_a_persons_of_one_type(self):
        found = self.types()["enhancement"]
        self.assertEqual((found["merged"], found["loop_built"]), (2, 1))

    def test_its_own_label_comes_before_its_issues_and_an_issues_types_one_without(self):
        write(self.bin, "search.json", [search_page([
            search_pr(203, "loop/issue-9", "2026-10-22T12:00:00Z", labels=["bug"], closes=[(9, ["enhancement"])]),
            search_pr(201, "loop/issue-7", "2026-10-20T12:00:00Z", closes=[(7, ["documentation"])])], 2)])
        found = self.types()
        self.assertEqual([found[kind]["merged"] for kind in ("bug", "enhancement", "documentation")], [1, 0, 1])

    def test_a_pull_request_with_no_type_counts_under_null(self):
        self.assertEqual(self.types()[None]["merged"], 1)

    def test_an_issue_with_an_unpriced_record_gives_its_type_a_null_cost(self):
        write(self.root, ".loop/issue-9/usage.json", [run("2026-10-16T09:00:00", "plan", "claude-b", 1000, None)])
        found = self.types()
        self.assertEqual((found["bug"]["tokens"], found["bug"]["cost_usd"]), (1000, None))
        self.assertEqual(found["enhancement"]["cost_usd"], 1.75)

    def test_a_search_that_matched_more_than_it_returns_says_truncated(self):
        prs = json.loads((self.bin / "search.json").read_text())
        for page in prs:
            page["data"]["search"]["issueCount"] = 1001
        write(self.bin, "search.json", prs)
        self.assertTrue(self.build()["work_by_type"]["truncated"])

    def test_no_gh_no_answer_or_a_page_it_cant_read_gives_null_and_why_and_exits_0(self):
        unreadable = "GitHub's search returned a page it couldn't read"
        for name, search, why in (("fails", None, "gh unavailable"), ("prints nothing", [], "gh unavailable"),
                                  ("an error page", [{"errors": [{"message": LEAK}]}], unreadable),
                                  ("a list", [[1, 2]], unreadable)):
            with self.subTest(name):
                if search is None:
                    (self.bin / "search.json").unlink(missing_ok=True)
                else:
                    write(self.bin, "search.json", search)
                code, out = self.main()
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(out)["work_by_type"], {"value": None, "why": why})
        empty = self.root.parent / "empty"
        empty.mkdir()
        with mock.patch.dict(os.environ, {"PATH": str(empty)}):
            self.assertEqual(self.build()["work_by_type"], {"value": None, "why": "gh unavailable"})

    def test_it_prints_no_title_author_login_body_or_address(self):
        code, out = self.main()
        self.assertEqual(code, 0)
        self.assertNotIn(LEAK, json.dumps(json.loads(out)["work_by_type"]))

    def test_spend_on_an_issue_no_merged_pull_request_closes_adds_nothing(self):
        found = self.build()["work_by_type"]["types"]
        self.assertEqual(sum(row["tokens"] for row in found), 6000 + 310)

    def test_a_projects_issue_isnt_this_repos_issue_of_the_same_number(self):
        found = self.types()["documentation"]  # 204 closes #3; only app/issue-3 has records
        self.assertEqual((found["issues"], found["tokens"], found["cost_usd"]), (1, 0, 0.0))

    def test_a_pull_request_merged_before_since_isnt_counted(self):
        self.assertEqual(self.types()["chore"]["merged"], 0)
        self.assertEqual(self.types(since="2026-09-01")["chore"]["merged"], 1)

    def test_an_issue_two_pull_requests_of_a_type_close_is_charged_once(self):
        found = self.types()["enhancement"]
        self.assertEqual((found["issues"], found["tokens"], found["cost_usd"]), (1, 310, 1.75))

    def test_the_docstring_lists_the_section(self):
        self.assertIn("\n    work_by_type ", dashboard_data.__doc__)


class LastReview(Factory):
    """When usage_report.py --review last ran, from the date it wrote to .sanvio/usage/last-review."""

    def mark(self, text):
        write(self.root, ".sanvio/usage/last-review", text)

    def test_the_date_and_the_days_since_it(self):
        self.mark("2026-10-20\n")
        self.assertEqual(self.build()["last_review"], {"date": "2026-10-20", "days_since": 7})

    def test_no_file_is_no_review_yet(self):
        self.assertEqual(self.build()["last_review"], {"value": None, "why": "no review yet"})

    def test_a_file_without_a_date_is_unreadable(self):
        for text in ("not a date\n", "2026-13-45\n", "", "2026-10-20T09:00:00\n"):
            self.mark(text)
            self.assertEqual(self.build()["last_review"], {"value": None, "why": "unreadable"}, text)

    def test_a_folder_in_its_place_is_unreadable(self):
        (self.root / ".sanvio" / "usage" / "last-review").mkdir(parents=True)
        self.assertEqual(self.build()["last_review"], {"value": None, "why": "unreadable"})

    def test_the_docstring_lists_the_section(self):
        self.assertIn("\n    last_review ", dashboard_data.__doc__)


class MissingOrCorrupt(Factory):
    def test_every_source_missing_gives_null_and_why_and_exits_0(self):
        code, out = self.main()
        self.assertEqual(code, 0)
        found = json.loads(out)
        self.assertEqual(found["loop_spend"], {"value": None, "why": "no loop records"})
        self.assertEqual(found["loop_throughput"], {"value": None, "why": "no status.json"})
        self.assertEqual(found["activity"], {"value": None, "why": "no usage log"})
        self.assertEqual(found["evals"], {"value": None, "why": "no saved evals"})
        self.assertEqual(found["conversations"], {"value": None, "why": "no transcripts"})
        for section in ("loop_spend", "conversations"):
            self.assertNotIn("by_day", found[section], section)
        self.assertEqual(found["waiting"], {"pull_requests": {"value": None, "why": "gh unavailable"},
                                            "blocked": {"value": None, "why": "no status.json"}})
        self.assertEqual(found["loop_history"], {"value": None, "why": "no run history"})

    def test_every_source_corrupt_gives_null_and_why_and_exits_0(self):
        write(self.root, ".loop/issue-7/usage.json", "not json")
        write(self.root, ".loop/projects/app/issue-3/usage.json", {"not": "a list"})
        write(self.root, ".loop/status.json", "not json")
        write(self.root, ".loop/projects/app/status.json", ["not", "an", "object"])
        write(log_path(self.root).parent, log_path(self.root).name, "not json\n[1, 2]\n")
        write(self.root, ".sanvio/evals/2026-10-25T0900-reviewer.json", "not json")
        write(self.root, ".sanvio/evals/2026-10-26T0900-reviewer.json", {"reviewer": "reviewer"})
        (self.root / ".loop" / "history.jsonl").mkdir()
        (self.root / ".loop" / "projects" / "app" / "history.jsonl").write_bytes(b"\xff\xfe not utf-8\n")
        code, out = self.main()
        self.assertEqual(code, 0)
        found = json.loads(out)
        for section in ("loop_spend", "loop_throughput", "activity", "evals", "loop_history"):
            self.assertEqual(found[section], {"value": None, "why": "unreadable"}, section)

    def test_records_with_no_run_in_the_window_are_zero_not_missing(self):
        write(self.root, ".loop/issue-7/usage.json", [run("2026-09-01T09:00:00", "plan", "m", 10, 1.0)])
        spend = self.build()["loop_spend"]
        self.assertEqual(spend["since"], {"tokens": None, "cost_usd": None})
        self.assertEqual(spend["by_issue"], {})


def reply(cwd, n, id, session, model="m-a", ts="2026-10-20T12:00:00Z", sidechain=False):
    """One transcript line for a reply, the shape Claude Code writes, with n, 2n, 3n and 4n tokens."""
    return {"type": "assistant", "cwd": str(cwd), "sessionId": session, "timestamp": ts, "requestId": "req_" + id,
            "isSidechain": sidechain,
            "message": {"id": "msg_" + id, "model": model, "role": "assistant",
                        "usage": {"input_tokens": n, "output_tokens": 2 * n, "cache_creation_input_tokens": 3 * n,
                                  "cache_read_input_tokens": 4 * n},
                        "content": [{"type": "text", "text": "reply " + LEAK}]}}


def lines(folder, relative, entries):
    return write(folder, relative, "".join(json.dumps(e) + "\n" for e in entries))


class Stop(Exception):
    """Stands in for a read stopped part way, as when the pane's timeout kills it."""


class Conversations(Factory):
    """Transcripts beside the factory, and the loop's worktrees in a folder set by loop.json."""

    def setUp(self):
        super().setUp()
        # West of UTC, where an evening's replies carry tomorrow's UTC date, whatever the machine's zone.
        zone = os.environ.get("TZ")
        os.environ["TZ"] = "America/Los_Angeles"
        time.tzset()
        self.addCleanup(time.tzset)
        self.addCleanup(lambda: os.environ.pop("TZ", None) if zone is None else os.environ.__setitem__("TZ", zone))
        self.loop = self.root.parent / "loop-checkouts"
        write(self.root, "loop.json", {"worktree_dir": str(self.loop)})
        self.cache = self.root / ".sanvio" / dashboard_data.CACHE
        prompt = {"type": "user", "cwd": str(self.root), "sessionId": "s1", "timestamp": "2026-10-20T11:00:00Z",
                  "message": {"role": "user", "content": "prompt " + LEAK}}
        first = reply(self.root, 1, "1", "s1")
        lines(self.transcripts, "a/s1.jsonl", [
            prompt, first, first, reply(self.root / "projects" / "app", 10, "2", "s1", model="m-b"),
            reply(self.root, 7, "old", "s1", ts="2026-10-01T12:00:00Z"),
            reply(self.root.parent / "elsewhere", 5, "out", "s9")])
        lines(self.transcripts, "a/s1/subagents/agent-x.jsonl", [reply(self.root, 100, "3", "s1", sidechain=True)])
        # The same reply again, as a resumed session copies it, then one from the loop.
        self.other = lines(self.transcripts, "b/s2.jsonl", [
            dict(first, sessionId="s3"), reply(self.loop / "issue-7" / "src", 1000, "4", "s2")])

    def conversations(self):
        return dashboard_data.conversations(self.root, SINCE, TODAY, self.transcripts, self.cache)

    def from_token_report(self):
        """What token_report.read() and group() make of the same transcripts, in the same shape."""
        by_model, sessions = {"factory": {}, "loop": {}}, {"factory": set(), "loop": set()}
        by_day = {side: dict.fromkeys(dashboard_data.days(SINCE, TODAY), 0) for side in by_model}
        for entry in token_report.read(self.transcripts, SINCE):
            found = token_report.group(entry, self.root, self.loop)
            if found is None:
                continue
            side = "loop" if found[0] == "Loop" else "factory"
            model = entry["message"]["model"]
            by_model[side][model] = [a + b for a, b in zip(by_model[side].get(model, [0, 0, 0, 0]),
                                                           token_report.tokens(entry))]
            day = datetime.datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).astimezone().date().isoformat()
            if day in by_day[side]:
                by_day[side][day] += sum(token_report.tokens(entry))
            sessions[side].add(entry["sessionId"])
        return {side: {"by_model": {m: dict(zip(dashboard_data.COUNTS, v), total=sum(v))
                                    for m, v in sorted(by_model[side].items())},
                       "sessions": len(sessions[side]),
                       "by_day": [{"day": d, "tokens": n} for d, n in by_day[side].items()]} for side in by_model}

    def test_tokens_by_side_and_model_counted_as_token_report_counts_them(self):
        found = self.conversations()

        def on_the_20th(tokens):
            return [{"day": d, "tokens": tokens if d == "2026-10-20" else 0} for d in dashboard_data.days(SINCE, TODAY)]

        self.assertEqual(found, {
            "factory": {"by_model": {"m-a": {"input": 101, "output": 202, "cache_writes": 303, "cache_reads": 404,
                                             "total": 1010},
                                     "m-b": {"input": 10, "output": 20, "cache_writes": 30, "cache_reads": 40,
                                             "total": 100}},
                        "sessions": 1, "by_day": on_the_20th(1110)},
            "loop": {"by_model": {"m-a": {"input": 1000, "output": 2000, "cache_writes": 3000, "cache_reads": 4000,
                                          "total": 10000}},
                     "sessions": 1, "by_day": on_the_20th(10000)}})
        self.assertEqual(found, self.from_token_report())

    def test_a_second_run_reads_only_the_transcript_that_changed(self):
        first = self.conversations()
        stat = self.other.stat()
        os.utime(self.other, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        with mock.patch.object(dashboard_data, "read_file", wraps=token_report.read_file) as reading:
            self.assertEqual(self.conversations(), first)
        self.assertEqual([call.args[0] for call in reading.call_args_list], [self.other])

    def stop_on_read(self, n):
        """read_file, raising Stop on the nth transcript read."""
        calls = []

        def reading(path, *args):
            calls.append(path)
            if len(calls) == n:
                raise Stop(path)
            return token_report.read_file(path, *args)
        return reading

    def test_a_read_stopped_part_way_keeps_what_it_read_and_the_next_read_finishes_it(self):
        with mock.patch.object(dashboard_data, "SAVE_EVERY", 1), \
                mock.patch.object(dashboard_data, "read_file", self.stop_on_read(3)):
            self.assertRaises(Stop, self.conversations)
        kept = json.loads(self.cache.read_text())
        self.assertEqual(len(kept), 2)
        self.assertNotIn(str(self.other), kept)
        with mock.patch.object(dashboard_data, "read_file", wraps=token_report.read_file) as reading:
            self.assertEqual(self.conversations(), self.from_token_report())
        self.assertEqual([call.args[0] for call in reading.call_args_list], [self.other])

    def test_a_save_part_way_keeps_the_earlier_caches_entries(self):
        self.conversations()
        before = json.loads(self.cache.read_text())[str(self.other)]
        for path in (self.transcripts / "a" / "s1.jsonl", self.other):
            stat = path.stat()
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        with mock.patch.object(dashboard_data, "SAVE_EVERY", 1), \
                mock.patch.object(dashboard_data, "read_file", self.stop_on_read(2)):
            self.assertRaises(Stop, self.conversations)
        self.assertEqual(json.loads(self.cache.read_text())[str(self.other)], before)

    def test_an_unchanged_read_leaves_the_cache_file_alone(self):
        self.conversations()
        inode = self.cache.stat().st_ino
        self.conversations()
        self.assertEqual(self.cache.stat().st_ino, inode)

    def test_a_cache_that_cant_be_read_or_has_the_wrong_shape_is_rebuilt(self):
        for junk in ("not json", "[1, 2]", json.dumps({str(self.other): {"size": "big", "replies": [[1]]}})):
            write(self.cache.parent, self.cache.name, junk)
            self.assertEqual(self.conversations(), self.from_token_report(), junk)
            self.assertIn(str(self.other), json.loads(self.cache.read_text()))

    def test_a_deleted_transcript_drops_out_of_the_cache_and_the_counts(self):
        self.conversations()
        self.other.unlink()
        found = self.conversations()
        self.assertNotIn(str(self.other), json.loads(self.cache.read_text()))
        self.assertEqual(found["loop"]["by_model"], {})
        self.assertEqual(found["loop"]["sessions"], 0)
        self.assertTrue(all(d["tokens"] == 0 for d in found["loop"]["by_day"]))
        self.assertEqual(found, self.from_token_report())

    def test_tokens_by_day_count_a_copied_reply_once_and_add_up_to_the_models(self):
        lines(self.transcripts, "c/s4.jsonl", [reply(self.root, 2, "5", "s4", ts="2026-10-25T08:00:00Z")])
        found = self.conversations()
        for side in ("factory", "loop"):
            self.assertEqual([d["day"] for d in found[side]["by_day"]], dashboard_data.days(SINCE, TODAY))
            self.assertEqual(sum(d["tokens"] for d in found[side]["by_day"]),
                             sum(m["total"] for m in found[side]["by_model"].values()), side)
        factory = {d["day"]: d["tokens"] for d in found["factory"]["by_day"]}
        # Reply 1 is in a/s1.jsonl twice and b/s2.jsonl once: 10 tokens, counted once.
        self.assertEqual(factory["2026-10-20"], 10 + 100 + 1000)
        self.assertEqual(factory["2026-10-25"], 20)
        self.assertEqual(factory["2026-10-21"], 0)
        self.assertEqual(factory["2026-10-15"], 0)
        self.assertEqual(found, self.from_token_report())

    def test_an_evening_reply_west_of_utc_counts_on_its_own_local_day(self):
        # 02:00 UTC on the 28th is 19:00 on the 27th in Los Angeles: today's last bar, not off the end.
        lines(self.transcripts, "c/s4.jsonl", [reply(self.root, 2, "5", "s4", ts="2026-10-28T02:00:00Z")])
        found = self.conversations()
        for side in ("factory", "loop"):
            self.assertEqual([d["day"] for d in found[side]["by_day"]], dashboard_data.days(SINCE, TODAY), side)
            self.assertEqual(sum(d["tokens"] for d in found[side]["by_day"]),
                             sum(m["total"] for m in found[side]["by_model"].values()), side)
        self.assertEqual(found["factory"]["by_day"][-1], {"day": "2026-10-27", "tokens": 20})
        self.assertEqual(found, self.from_token_report())

    def test_a_cache_from_before_local_days_is_read_again(self):
        old = [["1", "r", "2026-10-28", "factory", "m-a", "s1", 1, 2, 3, 4]]  # no local day
        stat = self.other.stat()
        write(self.cache.parent, self.cache.name,
              {str(self.other): {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "replies": old}})
        self.assertEqual(self.conversations(), self.from_token_report())

    def test_by_day_runs_over_the_same_days_as_loop_spend(self):
        lines(self.transcripts, "c/s4.jsonl", [reply(self.root, 2, "5", "s4", ts="2026-10-28T02:00:00Z")])
        write(self.root, ".loop/issue-7/usage.json", [run("2026-10-22T09:00:00", "plan", "m", 10, 1.0)])
        found = self.build()
        spend = [d["day"] for d in found["loop_spend"]["by_day"]]
        for side in ("factory", "loop"):
            self.assertEqual([d["day"] for d in found["conversations"][side]["by_day"]], spend, side)

    def test_a_loop_checkout_from_before_the_rename_counts_on_the_loop_side(self):
        write(self.root, "loop.json", {})  # no worktree_dir, so the home folders are where the loop worked
        home = self.root.parent / "home"
        old = token_report.old_names.old_loop_home(home) / self.root.name / "issue-3"
        old.mkdir(parents=True)
        lines(self.transcripts, "c/s5.jsonl", [reply(old / "src", 50, "old-3", "s5")])
        # Only the home folder is swapped, so the dashboard's own loop_dirs(root) call has to find the old folder.
        with mock.patch.object(Path, "home", return_value=home):
            found = self.conversations()
        self.assertEqual(found["loop"]["by_model"],
                         {"m-a": {"input": 50, "output": 100, "cache_writes": 150, "cache_reads": 200, "total": 500}})
        self.assertEqual(found["loop"]["sessions"], 1)

    def test_the_cache_has_a_new_name_so_every_transcript_is_read_again(self):
        # conversations.json holds old-folder checkouts as outside the repo, and a finished checkout's
        # transcript never changes size or time, so under that name they would never be counted.
        self.assertNotEqual(dashboard_data.CACHE.name, "conversations.json")
        self.assertEqual(dashboard_data.CACHE, Path("cache") / "conversations-2.json")

    def test_a_missing_transcripts_folder_gives_null_and_why(self):
        self.assertEqual(dashboard_data.conversations(self.root, SINCE, TODAY, self.transcripts / "missing",
                                                      self.cache),
                         {"value": None, "why": "no transcripts"})

    def test_no_prompt_reply_or_folder_reaches_the_output_or_the_cache(self):
        code, out = self.main()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["conversations"]["loop"]["sessions"], 1)
        cache = self.cache.read_text()
        for text in (out, cache):
            for leak in (LEAK, str(self.root), str(self.loop)):
                self.assertNotIn(leak, text)


# What token_report.activity() returns, each model's counts in FIELDS order: input, output, cache writes, reads.
CANNED = {"skills": {"review-pr": {"runs": 2, "models": {"m-a": [1000, 2000, 3000, 4000]}}},
          "agents": {"reviewer": {"runs": 1, "models": {"m-a": [100, 0, 0, 0], "m-b": [0, 500, 0, 0]}}},
          "commands": {"standup": {"runs": 3, "models": {}}}}
PRICE_A = {"input": 1, "output": 2, "cache_writes": 3, "cache_reads": 4}
USAGE_COUNTS = {"skills": {"review-pr": 2, "learn": 1}, "agents": {"reviewer": 1}, "commands": {"standup": 1},
                "guard_refusals": {"credential-file": 2}, "asks": 1, "log_off": 0, "chain": "unchained"}


class ActivitySpend(Factory):
    """A usage log and a transcripts folder, with token_report.activity() canned unless a test writes transcripts."""

    def setUp(self):
        super().setUp()
        self.fill()
        self.transcripts.mkdir()

    def prices(self, models=None, **fields):
        write(self.root, ".sanvio/prices.json", dict(fields, models={"m-a": PRICE_A} if models is None else models))

    def canned(self, result=CANNED):
        patcher = mock.patch.object(token_report, "activity", return_value=result)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def activity(self, since=SINCE, now=NOW):
        return dashboard_data.build(self.root, since, TODAY, now, projects_dir=self.transcripts)["activity"]

    def test_each_names_tokens_and_cost_sit_beside_the_usage_counts(self):
        self.prices(checked="2026-10-20", models={"m-a": PRICE_A, "m-b": PRICE_A})
        reading = self.canned()
        self.assertEqual(self.activity(), dict(
            USAGE_COUNTS,
            skill_spend={"review-pr": {"tokens": 10000, "cost_usd": 0.03}},
            agent_spend={"reviewer": {"tokens": 600, "cost_usd": 0.0011}},
            command_spend={"standup": {"tokens": 0, "cost_usd": 0.0}},
            unpriced={}, prices_checked="2026-10-20", spend_at=NOW.isoformat(timespec="seconds")))
        reading.assert_called_once_with(self.transcripts, SINCE, self.root, dashboard_data.loop_dirs(self.root))

    def test_a_section_thats_missing_adds_nothing_and_reads_nothing(self):
        log_path(self.root).unlink()
        reading = self.canned()
        self.assertEqual(self.activity(), {"value": None, "why": "no usage log"})
        reading.assert_not_called()

    def test_no_transcripts_folder_leaves_the_counts_without_empty_spend(self):
        self.transcripts.rmdir()
        self.assertEqual(self.activity(), USAGE_COUNTS)
        self.assertFalse((self.root / ".sanvio" / dashboard_data.ACTIVITY_CACHE).exists())

    def test_a_loop_json_that_stops_the_read_leaves_the_counts_without_empty_spend(self):
        write(self.root, "loop.json", "not json")
        self.assertEqual(self.activity(), USAGE_COUNTS)

    def test_a_transcript_that_stops_the_read_leaves_the_counts_without_empty_spend(self):
        lines(self.transcripts, "a/s1.jsonl", [dict(reply(self.root, 1, "1", "s1"), requestId=["not", "a", "string"])])
        self.assertEqual(self.activity(), USAGE_COUNTS)

    def real_transcripts(self):
        """A command, then a reply calling a skill, then the skill's reply, a subagent, and a resumed session's
        copy of the skill's reply. Each reply has 10n tokens."""
        def user(text, uuid):
            return {"type": "user", "cwd": str(self.root), "sessionId": "s1", "timestamp": "2026-10-20T11:00:00Z",
                    "uuid": uuid, "message": {"role": "user", "content": text}}

        calling = reply(self.root, 1, "2", "s1")
        calling["message"]["content"].append({"type": "tool_use", "id": "toolu_1", "name": "Skill",
                                              "input": {"skill": "review-pr"}})
        skills = reply(self.root, 3, "3", "s1")
        lines(self.transcripts, "a/s1.jsonl", [
            user("<command-name>/standup</command-name> " + LEAK, "u1"), reply(self.root, 5, "1", "s1"),
            user("prompt " + LEAK, "u2"), calling, skills])
        lines(self.transcripts, "a/s1/subagents/agent-x.jsonl", [reply(self.root, 7, "4", "s1", sidechain=True)])
        write(self.transcripts, "a/s1/subagents/agent-x.meta.json", {"agentType": "reviewer"})
        lines(self.transcripts, "b/s2.jsonl", [dict(skills, sessionId="s3")])

    def test_real_transcripts_count_a_copied_reply_once_and_match_token_reports_split(self):
        self.real_transcripts()
        self.prices()
        found = self.activity()
        self.assertEqual(found["skill_spend"]["review-pr"]["tokens"], 30)
        self.assertEqual(found["agent_spend"]["reviewer"]["tokens"], 70)
        self.assertEqual(found["command_spend"]["standup"]["tokens"], 50)
        # The reply that calls the skill stays with what came before it, a typed prompt, so with nobody.
        split = token_report.activity(self.transcripts, SINCE, self.root, dashboard_data.loop_dirs(self.root))
        for kind, field in dashboard_data.SPEND_FIELDS.items():
            self.assertEqual({name: row["tokens"] for name, row in found[field].items()},
                             {name: sum(map(sum, row["models"].values())) for name, row in split[kind].items()}, kind)
        # 30 tokens at 3n, 6n, 9n, 12n of PRICE_A: 3 + 12 + 27 + 48 dollars per million.
        self.assertEqual(found["skill_spend"]["review-pr"]["cost_usd"], 0.0001)

    def test_no_prompt_reply_or_folder_reaches_the_output_or_the_kept_result(self):
        self.real_transcripts()
        self.prices(source=LEAK, checked=LEAK)
        found = json.dumps(self.activity())
        kept = (self.root / ".sanvio" / dashboard_data.ACTIVITY_CACHE).read_text()
        for text in (found, kept):
            for leak in (LEAK, str(self.root), "prompt"):
                self.assertNotIn(leak, text)

    def test_a_kept_result_is_used_again_for_15_minutes_at_the_same_since(self):
        reading = self.canned()
        self.activity()
        minutes = NOW + datetime.timedelta(minutes=15)
        self.assertEqual(self.activity(now=minutes)["spend_at"], NOW.isoformat(timespec="seconds"))
        self.assertEqual(reading.call_count, 1)
        later = minutes + datetime.timedelta(seconds=1)
        self.assertEqual(self.activity(now=later)["spend_at"], later.isoformat(timespec="seconds"))
        self.assertEqual(reading.call_count, 2)

    def test_a_kept_result_dated_in_the_future_is_used_again(self):
        reading = self.canned()
        self.activity(now=NOW + datetime.timedelta(days=1))
        self.activity()
        self.assertEqual(reading.call_count, 1)

    def test_a_changed_since_reads_again(self):
        reading = self.canned()
        self.activity()
        self.activity(since="2026-10-20")
        self.assertEqual([call.args[1] for call in reading.call_args_list], [SINCE, "2026-10-20"])

    def test_a_kept_result_that_cant_be_used_counts_as_none(self):
        at = NOW.isoformat(timespec="seconds")
        for junk in ("not json", "[1, 2]", {"at": at, "since": SINCE},
                     {"at": "not a time", "since": SINCE, "result": CANNED},
                     {"at": at, "since": SINCE, "result": {"skills": {}, "agents": {}}},
                     {"at": at, "since": SINCE, "result": dict(CANNED, skills={"a": {"runs": 1, "models": {"m": [1]}}})},
                     {"at": at, "since": SINCE, "result": dict(CANNED, skills={"a": {"runs": "1", "models": {}}})}):
            with self.subTest(junk=junk):
                write(self.root, Path(".sanvio") / dashboard_data.ACTIVITY_CACHE, junk)
                reading = self.canned()
                self.assertEqual(self.activity()["skill_spend"]["review-pr"]["tokens"], 10000)
                reading.assert_called_once()

    def test_new_prices_show_without_reading_the_transcripts_again(self):
        reading = self.canned()
        self.assertIsNone(self.activity()["skill_spend"]["review-pr"]["cost_usd"])
        self.prices()
        found = self.activity()
        self.assertEqual(found["skill_spend"]["review-pr"]["cost_usd"], 0.03)
        self.assertNotIn("m-a", found["unpriced"])
        self.assertEqual(reading.call_count, 1)

    def test_no_price_file_says_so_for_every_model(self):
        self.canned()
        found = self.activity()
        self.assertEqual(found["unpriced"], {"m-a": "no prices.json", "m-b": "no prices.json"})
        self.assertEqual(found["skill_spend"]["review-pr"], {"tokens": 10000, "cost_usd": None})
        self.assertIsNone(found["prices_checked"])

    def test_a_price_file_that_cant_be_read_says_so_for_every_model(self):
        self.canned()
        for junk in ("not json", "[1, 2]", {"models": ["m-a"]}, {"checked": "2026-10-20"}):
            with self.subTest(junk=junk):
                write(self.root, ".sanvio/prices.json", junk)
                found = self.activity()
                self.assertEqual(found["unpriced"], {"m-a": "unreadable", "m-b": "unreadable"})
                self.assertIsNone(found["prices_checked"])

    def test_a_model_the_file_doesnt_list_is_named_and_makes_only_its_items_null(self):
        self.prices()
        self.canned()
        found = self.activity()
        self.assertEqual(found["unpriced"], {"m-b": "not in prices.json"})
        self.assertEqual(found["skill_spend"]["review-pr"]["cost_usd"], 0.03)
        # reviewer has one model priced and one not, so its cost isn't the part that could be priced.
        self.assertEqual(found["agent_spend"]["reviewer"], {"tokens": 600, "cost_usd": None})

    def test_a_model_with_no_tokens_needs_no_price(self):
        self.prices()
        self.canned({"skills": {"a": {"runs": 1, "models": {"m-a": [1000, 0, 0, 0], "m-z": [0, 0, 0, 0]}}},
                     "agents": {"b": {"runs": 1, "models": {}}}, "commands": {}})
        found = self.activity()
        self.assertEqual(found["skill_spend"]["a"], {"tokens": 1000, "cost_usd": 0.001})
        self.assertEqual(found["agent_spend"]["b"], {"tokens": 0, "cost_usd": 0.0})
        self.assertEqual(found["unpriced"], {})

    def test_an_entry_without_four_finite_non_negative_numbers_is_unreadable(self):
        self.canned()
        for bad in ('{"input": 1, "output": 2, "cache_writes": 3}', '{"input": 1, "output": 2, "cache_writes": 3, "cache_reads": NaN}',
                    '{"input": 1, "output": 2, "cache_writes": 3, "cache_reads": Infinity}',
                    '{"input": 1, "output": 2, "cache_writes": 3, "cache_reads": -1}',
                    '{"input": 1, "output": 2, "cache_writes": 3, "cache_reads": true}',
                    '{"input": 1, "output": 2, "cache_writes": 3, "cache_reads": "4"}',
                    '{"input": 1, "output": 2, "cache_writes": 3, "cache_reads": 1' + "0" * 400 + '}', '[1, 2, 3, 4]'):
            with self.subTest(bad=bad):
                write(self.root, ".sanvio/prices.json", '{"models": {"m-a": ' + bad + '}}')
                found = self.activity()
                self.assertEqual(found["unpriced"]["m-a"], "unreadable")
                self.assertIsNone(found["skill_spend"]["review-pr"]["cost_usd"])
                json.dumps(found, allow_nan=False)

    def test_a_cost_too_big_for_a_float_is_null_not_invalid_json(self):
        huge = {name: 1e308 for name in PRICE_A}
        self.prices(models={"m-a": huge, "m-b": huge})
        self.canned()
        found = self.activity()
        self.assertIsNone(found["skill_spend"]["review-pr"]["cost_usd"])
        json.dumps(found, allow_nan=False)

    def test_only_a_date_is_printed_as_checked_and_the_source_never_is(self):
        self.canned()
        for checked, printed in (("2026-10-20", "2026-10-20"), ("2026-13-40", None), ("20261020", None),
                                 ("last week", None), (20261020, None), (None, None)):
            with self.subTest(checked=checked):
                self.prices(source=LEAK, checked=checked)
                found = self.activity()
                self.assertEqual(found["prices_checked"], printed)
                self.assertNotIn(LEAK, json.dumps(found))

    def test_the_example_price_file_is_read_and_holds_only_an_example_model(self):
        shutil.copy(ROOT / "scripts" / "prices.example.json", self.prices_path())
        self.canned({"skills": {"a": {"runs": 1, "models": {"example-model": [1000000, 0, 0, 0]}}},
                     "agents": {}, "commands": {}})
        found = self.activity()
        self.assertEqual(found["skill_spend"]["a"], {"tokens": 1000000, "cost_usd": 1.0})
        self.assertEqual(list(json.loads((ROOT / "scripts" / "prices.example.json").read_text())["models"]),
                         ["example-model"])

    def prices_path(self):
        path = self.root / ".sanvio" / dashboard_data.PRICES
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@contextlib.contextmanager
def zone(name):
    """Run in the time zone given, whatever the machine's, and put the old one back after."""
    was = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if was is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = was
        time.tzset()


def read_sample():
    """The document in SAMPLE, or None when the file is missing or doesn't start with SAMPLE_HEAD."""
    text = SAMPLE.read_text() if SAMPLE.is_file() else ""
    return json.loads(text[len(SAMPLE_HEAD):]) if text.startswith(SAMPLE_HEAD) else None


OPUS = "claude-opus-5-5"
SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"


def finished(issue, ended, outcome="pr", tests=("passed",), verdicts=("PASS",), started="2026-10-20T09:00:00",
             tokens=100, cost=1.0, project=None):
    """One line of a history.jsonl, the shape loop.py's record_run() writes."""
    return {"v": 1, "run": "{}-{}".format(issue, started), "issue": issue, "project": project, "started": started,
            "ended": ended, "outcome": outcome, "rounds": len(tests), "tests": list(tests), "verdicts": list(verdicts),
            "tokens": tokens, "cost_usd": cost, "agent": "claude", "reviewer": "claude"}


class Sample(GitHarness):
    """build() with every section filled, which must match the sample the dashboard's tests draw.

    Its inputs are its own, not fill()'s: the dashboard README's picture is drawn from this sample, so its
    titles, models and token counts read like a factory at work, a few weeks in. All of it is made up."""

    def setUp(self):
        super().setUp()
        # The loop's runs: plans and reviews on Sonnet, builds on Opus, weekdays only.
        runs = {
            "issue-31": [("2026-10-16T09:00:00", "plan", SONNET, 610_000, 0.90),
                         ("2026-10-16T09:20:00", "build", OPUS, 1_480_000, 2.20),
                         ("2026-10-16T10:10:00", "review", SONNET, 350_000, 0.55)],
            "issue-32": [("2026-10-19T09:00:00", "plan", SONNET, 720_000, 1.05),
                         ("2026-10-19T09:30:00", "build", OPUS, 2_100_000, 3.10),
                         ("2026-10-20T09:00:00", "review", SONNET, 400_000, 0.60)],
            "issue-33": [("2026-10-20T11:00:00", "plan", SONNET, 540_000, 0.80),
                         ("2026-10-20T11:30:00", "build", OPUS, 1_750_000, 2.60),
                         ("2026-10-21T09:00:00", "build", OPUS, 1_620_000, 2.40),
                         ("2026-10-21T10:00:00", "review", SONNET, 330_000, 0.50)],
            "issue-34": [("2026-10-22T09:00:00", "plan", SONNET, 470_000, 0.70),
                         ("2026-10-22T09:30:00", "build", OPUS, 2_560_000, 3.80),
                         ("2026-10-23T09:00:00", "build", OPUS, 2_760_000, 4.10),
                         ("2026-10-23T10:30:00", "review", SONNET, 370_000, 0.55)],
            "issue-36": [("2026-10-26T09:00:00", "plan", SONNET, 570_000, 0.85),
                         ("2026-10-26T09:30:00", "build", OPUS, 1_950_000, 2.90),
                         ("2026-10-26T10:40:00", "review", SONNET, 300_000, 0.45)],
            "issue-38": [("2026-10-26T13:00:00", "plan", SONNET, 470_000, 0.70),
                         ("2026-10-27T08:00:00", "build", OPUS, 2_150_000, 3.20),
                         ("2026-10-27T08:40:00", "review", SONNET, 400_000, 0.60)],
            "issue-40": [("2026-10-27T10:00:00", "plan", SONNET, 500_000, 0.75)],
        }
        for issue, entries in runs.items():
            write(self.root, ".loop/{}/usage.json".format(issue), [run(*e) for e in entries])
        write(self.root, ".loop/projects/app/issue-3/usage.json", [
            run("2026-10-22T14:00:00", "build", OPUS, 880_000, 1.30)])

        def issue(number, title, state, round, note="", pull=None, started=None, steps=None):
            return {"number": number, "title": title, "state": state, "round": round, "note": note,
                    "pr": "https://github.com/o/r/pull/{}".format(pull) if pull else None,
                    "updated": "2026-10-23T16:00:00Z" if state == "blocked" else None,
                    "started": started, "step_seconds": steps or {}}

        def steps(shape, build, validate, scale=None):
            """Seconds at each step, as loop.py's time_step() keeps them. Review takes 2 to 3 times the build."""
            found = {"SHAPE": shape, "BUILD": build, "VALIDATE": validate, "TEST": 300}
            return dict(found, SCALE=scale) if scale is not None else found

        write(self.root, ".loop/status.json", {"queue": [], "issues": [
            issue(31, "Dashboard: stack narrow tables", "pr", 1, pull=39, started="2026-10-16T09:00:00",
                  steps=steps(260, 1180, 2900, 70)),
            issue(32, "Loop: say which round a review was", "pr", 1, pull=41, started="2026-10-19T09:00:00",
                  steps=steps(300, 1500, 3700, 80)),
            issue(33, "Gate: name the section that's empty", "pr", 2, pull=43, started="2026-10-20T11:00:00",
                  steps=steps(220, 2600, 5400, 65)),
            issue(34, "README: link the loop section", "blocked", 5, "the link check still fails after 5 rounds",
                  started="2026-10-22T09:00:00", steps=steps(280, 5200, 12000)),
            issue(36, "Loop: retry a flaky test once", "pr", 1, pull=44, started="2026-10-26T09:00:00",
                  steps=steps(240, 1300, 3300, 75)),
            issue(38, "Gate: check the fee total", "pr", 1, pull=45, started="2026-10-26T13:00:00",
                  steps=steps(250, 1400, 3500, 70)),
            issue(40, "Steering: when a ticket needs a spec", "building", 1, started="2026-10-27T10:00:00",
                  steps={"SHAPE": 270})]})
        write(self.root, ".loop/projects/app/status.json", {"issues": [
            {"number": 3, "title": "Add a health check", "state": "pr", "round": 1, "pr": "https://github.com/o/app/pull/4",
             "started": "2026-10-22T14:00:00", "step_seconds": steps(200, 1100, 2500, 60)}]})
        # The same issues as they ended, each outcome and round count agreeing with status.json above.
        lines(self.root, ".loop/history.jsonl", [
            finished(31, "2026-10-16T10:40:00", started="2026-10-16T09:00:00", tokens=2_440_000, cost=3.65),
            finished(32, "2026-10-20T09:40:00", started="2026-10-19T09:00:00", tokens=3_220_000, cost=4.75),
            finished(33, "2026-10-21T10:30:00", tests=("failed", "passed"), verdicts=("FIX", "PASS"),
                     started="2026-10-20T11:00:00", tokens=4_240_000, cost=6.30),
            finished(34, "2026-10-23T16:00:00", "blocked", tests=("failed",) * 5, verdicts=("FIX",) * 5,
                     started="2026-10-22T09:00:00", tokens=6_160_000, cost=9.15),
            finished(36, "2026-10-26T11:00:00", started="2026-10-26T09:00:00", tokens=2_820_000, cost=4.20),
            finished(38, "2026-10-27T08:48:00", started="2026-10-26T13:00:00", tokens=3_020_000, cost=4.50)])
        lines(self.root, ".loop/projects/app/history.jsonl", [
            finished(3, "2026-10-22T15:10:00", started="2026-10-22T14:00:00", tokens=880_000, cost=1.30, project="app")])

        events = []
        for day, names in (("15", ["standup", "review-pr"]), ("16", ["standup", "review-pr", "learn"]),
                           ("19", ["standup", "review-pr"]), ("20", ["standup", "review-pr", "review-pr"]),
                           ("21", ["standup", "learn"]), ("22", ["standup", "review-pr"]),
                           ("23", ["standup"]), ("26", ["standup", "review-pr", "review-pr"]),
                           ("27", ["standup", "review-pr"])):
            ts = "2026-10-{}T10:00:00Z".format(day)
            events += [{"ts": ts, "event": "command" if n == "standup" else "skill", "name": n} for n in names]
        events += [{"ts": "2026-10-20T11:00:00Z", "event": "agent", "name": "reviewer"},
                   {"ts": "2026-10-26T11:00:00Z", "event": "agent", "name": "reviewer"},
                   {"ts": "2026-10-26T11:30:00Z", "event": "agent", "name": "security-reviewer"},
                   {"ts": "2026-10-21T15:00:00Z", "event": "guard_deny", "rule": "credential-file"},
                   {"ts": "2026-10-22T15:00:00Z", "event": "guard_ask", "rule": "connector-write",
                    "tool": "mcp__github__create_pull_request"},
                   {"ts": "2026-10-26T15:00:00Z", "event": "guard_ask", "rule": "connector-write",
                    "tool": "mcp__github__create_pull_request"}]
        write(log_path(self.root).parent, log_path(self.root).name, "".join(json.dumps(e) + "\n" for e in events))
        # The last monthly log review, a week before TODAY.
        write(self.root, ".sanvio/usage/last-review", "2026-10-20\n")

        # Each reviewer's saved result reads a folder of cases committed before it was saved. The reviewer's
        # brief is committed again after, so the reviewer is stale with the file that changed and the other fresh.
        stable = {"status": "stable", "reasons": []}
        for name, reviewer, saved, cases in (
                ("2026-10-25T0900-reviewer", "reviewer", "2026-10-25T09:00:00+00:00",
                 dict({"{:02}".format(i): stable for i in range(1, 10)},
                      **{"10": {"status": "flaky", "reasons": ["missed: the fee total"]}})),
                ("2026-10-26T0900-security-reviewer", "security-reviewer", "2026-10-26T09:00:00+00:00",
                 {"{:02}".format(i): stable for i in range(1, 9)})):
            write(self.root, ".sanvio/evals/{}.json".format(name),
                  {"agent": "claude", "reviewer": reviewer, "saved": saved, "cases": cases,
                   "folder": "reviewer-cases" if reviewer == "reviewer" else "security-cases"})
        write(self.root, "agents/reviewer.md", "the reviewer\n")
        write(self.root, "agents/security-reviewer.md", "the security reviewer\n")
        write(self.root, "scripts/eval_agents.py", "# the eval\n")
        write(self.root, "briefs/proposal.md", "the brief\n")
        write(self.root, "reviewer-cases/01-a/case.json", {"agent": "reviewer", "brief": "briefs/proposal.md"})
        write(self.root, "reviewer-cases/01-a/work.md", "the work\n")
        write(self.root, "security-cases/01-x/case.json", {"agent": "security-reviewer"})
        write(self.root, "security-cases/01-x/work.md", "the code\n")
        self.commit("2026-10-20T09:00:00+00:00")
        write(self.root, "briefs/proposal.md", "the brief, rewritten\n")
        self.commit("2026-10-26T12:00:00+00:00")
        # gh answers the open pull requests for waiting and the merged ones for loop_rework from their own files.
        self.answer_gh()
        write(self.bin, "prs-open.json", [
            pr(45, "2026-10-27T08:48:00Z", "loop/issue-38", title="Gate: check the fee total",
               rollup=[check_run("COMPLETED", "SUCCESS")]),
            pr(44, "2026-10-26T11:00:00Z", "loop/issue-36", mergeable="UNKNOWN", title="Loop: retry a flaky test once",
               rollup=[check_run("COMPLETED", "SUCCESS"), check_run("IN_PROGRESS", "")]),
            pr(42, "2026-10-25T12:00:00Z", "response-style", draft=True, mergeable="CONFLICTING",
               title="Steering: shorter replies", rollup=[check_run("COMPLETED", "FAILURE")]),
            pr(46, "2026-10-27T11:00:00Z", "go-example", title="Examples: a Go project")])
        # The loop's account opens them; a person reviews them, and the loop's own comment on 41 isn't a review.
        def review(who, at):
            return {"author": {"login": who}, "submittedAt": at, "state": "COMMENTED"}

        write(self.bin, "prs-merged.json", [
            {"number": 39, "title": "Dashboard: stack narrow tables", "headRefName": "loop/issue-31",
             "author": {"login": "loop-bot"}, "createdAt": "2026-10-16T10:40:00Z", "mergedAt": "2026-10-17T12:00:00Z",
             "reviews": [review("a-reviewer", "2026-10-16T15:10:00Z")]},
            {"number": 41, "title": "Loop: say which round a review was", "headRefName": "loop/issue-32",
             "author": {"login": "loop-bot"}, "createdAt": "2026-10-20T09:40:00Z", "mergedAt": "2026-10-20T12:00:00Z",
             "reviews": [review("loop-bot", "2026-10-20T09:45:00Z"), review("a-reviewer", "2026-10-20T11:00:00Z")]},
            {"number": 43, "title": "Gate: name the section that's empty", "headRefName": "loop/issue-33",
             "author": {"login": "loop-bot"}, "createdAt": "2026-10-21T10:30:00Z", "mergedAt": "2026-10-22T12:00:00Z",
             "reviews": [review("a-reviewer", "2026-10-21T16:00:00Z")]}])
        loop = commit("Build it\n\nLoop: issue #31, round 1.")
        write(self.bin, "commits.json", {
            "39": [[loop]],
            "41": [[loop, commit("fix the test")]],
            "43": [[loop, commit("Merge branch 'main' into loop/issue-33", parents=2)]]})
        # The same three as the search finds them for work_by_type, typed by their own label or their issue's,
        # with a person's documentation fix and a tidy-up nobody labelled.
        merged = [
            search_pr(39, "loop/issue-31", "2026-10-17T12:00:00Z", labels=["enhancement"], closes=[(31, [])],
                      title="Dashboard: stack narrow tables", author="loop-bot"),
            search_pr(41, "loop/issue-32", "2026-10-20T12:00:00Z", closes=[(32, ["bug"])],
                      title="Loop: say which round a review was", author="loop-bot"),
            search_pr(43, "loop/issue-33", "2026-10-22T12:00:00Z", closes=[(33, ["enhancement"])],
                      title="Gate: name the section that's empty", author="loop-bot"),
            search_pr(37, "readme-links", "2026-10-19T15:00:00Z", labels=["documentation"],
                      title="README: fix two links", author="a-person"),
            search_pr(47, "tidy", "2026-10-23T15:00:00Z", title="Tidy the scripts folder", author="a-person")]
        write(self.bin, "search.json", [search_page(merged, len(merged))])
        # Replies at noon UTC fall on the same day in UTC and in Los Angeles. reply() gives 10n tokens a reply.
        checkouts = self.root.parent / "loop-checkouts"
        write(self.root, "loop.json", {"worktree_dir": str(checkouts)})
        factory = {"15": 150_000, "16": 420_000, "19": 380_000, "20": 610_000, "21": 520_000, "22": 700_000,
                   "23": 450_000, "24": 90_000, "26": 820_000, "27": 560_000}
        for day, n in factory.items():
            ts = "2026-10-{}T12:00:00Z".format(day)
            entries = [reply(self.root, n, "h" + day, "s" + day, model=OPUS, ts=ts),
                       reply(self.root, n // 20, "k" + day, "s" + day, model=HAIKU, ts=ts)]
            if day == "20":  # the reviewer ran that day, in the Haiku reply, so it moves to the subagent's file
                lines(self.transcripts, "harness/s20/subagents/agent-x.jsonl", [entries.pop()])
                write(self.transcripts, "harness/s20/subagents/agent-x.meta.json", {"agentType": "reviewer"})
            if day == "26":  # /standup's Opus reply calls review-pr, so the Haiku reply after it is the skill's
                entries[0]["message"]["content"].append({"type": "tool_use", "id": "toolu_26", "name": "Skill",
                                                         "input": {"skill": "review-pr"}})
                entries.insert(0, {"type": "user", "cwd": str(self.root), "sessionId": "s26", "timestamp": ts, "uuid": "u26",
                                   "message": {"role": "user", "content": "<command-name>/standup</command-name>"}})
            lines(self.transcripts, "harness/s{}.jsonl".format(day), entries)
        write(self.root, ".sanvio/prices.json", {
            "checked": "2026-10-01",
            "models": {OPUS: {"input": 5, "output": 25, "cache_writes": 6.25, "cache_reads": 0.5},
                       HAIKU: {"input": 1, "output": 5, "cache_writes": 1.2, "cache_reads": 0.1}}})
        for issue, day, n in (("issue-31", "16", 210_000), ("issue-32", "19", 280_000), ("issue-33", "21", 330_000),
                              ("issue-34", "23", 520_000), ("issue-36", "26", 240_000), ("issue-38", "27", 260_000)):
            lines(self.transcripts, "loop/{}.jsonl".format(issue), [
                reply(checkouts / issue, n, "l" + issue, issue, model=OPUS, ts="2026-10-{}T12:00:00Z".format(day))])

    def build_afresh(self):
        # The cache keeps each reply's local day, so a second zone would read the first zone's days.
        (self.root / ".sanvio" / dashboard_data.CACHE).unlink(missing_ok=True)
        return self.build()

    def test_the_sample_is_what_build_prints(self):
        if os.environ.get("UPDATE_SAMPLE"):
            with zone("UTC"):
                SAMPLE.write_text(SAMPLE_HEAD + json.dumps(self.build_afresh(), indent=2, sort_keys=True) + "\n")
        for name in ("UTC", "America/Los_Angeles"):
            with self.subTest(zone=name), zone(name):
                self.assertEqual(read_sample(), self.build_afresh(),
                                 "build() no longer prints the dashboard's sample. run: " + UPDATE_SAMPLE)

    def test_every_section_is_filled(self):
        found = read_sample()
        self.assertIsNotNone(found, "no sample. run: " + UPDATE_SAMPLE)
        parts = {name: found[name] for name in found if name not in ("generated", "since")}
        parts.update({"waiting." + half: found["waiting"][half] for half in ("pull_requests", "blocked")})
        parts.update({"stage_times." + half: found["stage_times"][half] for half in ("loop_steps", "pull_requests")})
        for name, value in parts.items():
            self.assertTrue(value, name)
            self.assertFalse(isinstance(value, dict) and "value" in value and value["value"] is None, name)
        # Each reviewer's freshness came from its files, not a why, and one has a file changed since it was saved.
        rows = found["evals"].values()
        self.assertEqual([r["why"] for r in rows if "why" in r], [])
        self.assertTrue(any(r["changed"] and r["newest_change"] for r in rows))
        for field, name in (("skill_spend", "review-pr"), ("agent_spend", "reviewer"), ("command_spend", "standup")):
            self.assertIsNotNone(found["activity"][field][name]["cost_usd"], field)


class LoopHistory(Factory):
    """Runs from the factory and project app, over several days, one before SINCE and one of each outcome."""

    def setUp(self):
        super().setUp()
        self.harness = [finished(1, "2026-10-01T09:00:00"),  # before SINCE
                        finished(2, "2026-10-15T00:00:00", "skipped", tests=(), verdicts=(), tokens=None, cost=None),
                        finished(7, "2026-10-20T10:00:00"),
                        finished(9, "2026-10-22T09:00:00", "stopped"),
                        finished(8, "2026-10-22T11:00:00", "blocked", tests=("failed", "failed"),
                                 verdicts=("FIX", "FIX"), tokens=200, cost=2.5)]
        self.app = [finished(7, "2026-10-21T10:00:00", project="app"),
                    finished(3, "2026-10-22T10:00:00", project="app")]

    def fill_history(self):
        lines(self.root, ".loop/history.jsonl", self.harness)
        lines(self.root, ".loop/projects/app/history.jsonl", self.app)

    def history(self, since=SINCE):
        return dashboard_data.loop_history(self.root, since, TODAY)

    def test_every_run_since_in_ended_order_across_files_with_exactly_its_fields(self):
        self.fill_history()
        pr = {"outcome": "pr", "rounds": 1, "tests": ["passed"], "verdicts": ["PASS"], "tokens": 100, "cost_usd": 1.0,
              "started": "2026-10-20T09:00:00"}
        self.assertEqual(self.history()["runs"], [
            dict(pr, issue="issue-2", ended="2026-10-15T00:00:00", outcome="skipped", rounds=0, tests=[], verdicts=[],
                 tokens=None, cost_usd=None),
            dict(pr, issue="issue-7", ended="2026-10-20T10:00:00"),
            dict(pr, issue="app/issue-7", ended="2026-10-21T10:00:00"),
            dict(pr, issue="issue-9", ended="2026-10-22T09:00:00", outcome="stopped"),
            dict(pr, issue="app/issue-3", ended="2026-10-22T10:00:00"),
            dict(pr, issue="issue-8", ended="2026-10-22T11:00:00", outcome="blocked", rounds=2,
                 tests=["failed", "failed"], verdicts=["FIX", "FIX"], tokens=200, cost_usd=2.5)])

    def test_the_sections_keys_and_each_runs_fields_in_order(self):
        self.fill_history()
        found = self.history()
        self.assertEqual(list(found), ["runs", "by_day", "by_outcome", "skipped_lines"])
        self.assertEqual(list(found["runs"][0]), ["issue", "started", "ended", "outcome", "rounds", "tests", "verdicts",
                                                  "tokens", "cost_usd"])
        self.assertEqual(list(found["by_day"][0]), ["day", "runs", "pr", "blocked", "stopped", "skipped",
                                                    "more_than_one_round"])

    def test_runs_ending_at_the_same_time_keep_the_harness_before_the_project(self):
        same = "2026-10-20T10:00:00"
        lines(self.root, ".loop/history.jsonl", [finished(5, same)])
        lines(self.root, ".loop/projects/app/history.jsonl", [finished(4, same)])
        lines(self.root, ".loop/projects/web/history.jsonl", [finished(3, same)])
        self.assertEqual([r["issue"] for r in self.history()["runs"]], ["issue-5", "app/issue-4", "web/issue-3"])

    def test_by_day_runs_over_loop_spends_days_with_zeros_on_empty_days(self):
        self.fill_history()
        write(self.root, ".loop/issue-7/usage.json", [run("2026-10-20T09:00:00", "plan", "m", 10, 1.0)])
        found = self.build()
        rows = found["loop_history"]["by_day"]
        self.assertEqual([r["day"] for r in rows], [d["day"] for d in found["loop_spend"]["by_day"]])
        by_day = {r["day"]: r for r in rows}
        empty = {"runs": 0, "pr": 0, "blocked": 0, "stopped": 0, "skipped": 0, "more_than_one_round": 0}
        self.assertEqual(by_day["2026-10-16"], dict(empty, day="2026-10-16"))
        self.assertEqual(by_day["2026-10-15"], dict(empty, day="2026-10-15", runs=1, skipped=1))
        self.assertEqual(by_day["2026-10-21"], dict(empty, day="2026-10-21", runs=1, pr=1))
        self.assertEqual(by_day["2026-10-22"], dict(empty, day="2026-10-22", runs=3, pr=1, blocked=1, stopped=1,
                                                    more_than_one_round=1))

    def test_by_outcome_totals(self):
        self.fill_history()
        self.assertEqual(self.history()["by_outcome"], {"pr": 3, "blocked": 1, "stopped": 1, "skipped": 1})

    def test_by_outcome_has_every_key_with_no_run_counted(self):
        lines(self.root, ".loop/history.jsonl", [self.harness[0]])
        found = self.history()
        self.assertEqual(found["runs"], [])
        self.assertEqual(found["by_outcome"], {"pr": 0, "blocked": 0, "stopped": 0, "skipped": 0})

    def test_a_run_ending_after_today_is_in_runs_and_by_outcome_on_no_day(self):
        lines(self.root, ".loop/history.jsonl", [finished(11, "2026-10-28T09:00:00")])
        found = self.history()
        self.assertEqual([r["issue"] for r in found["runs"]], ["issue-11"])
        self.assertEqual(found["by_outcome"]["pr"], 1)
        self.assertEqual(found["by_day"][-1]["day"], TODAY.isoformat())
        self.assertEqual(sum(r["runs"] for r in found["by_day"]), 0)

    def test_each_kind_of_bad_line_is_skipped(self):
        good = finished(7, "2026-10-20T10:00:00")
        for raw in ("not json", "[1, 2]", "3", "null", "",
                    json.dumps(dict(good, v=2)), json.dumps(dict(good, v=True)), json.dumps(dict(good, v=1.0)),
                    json.dumps({k: v for k, v in good.items() if k != "v"}),
                    json.dumps({k: v for k, v in good.items() if k != "ended"}),
                    json.dumps(dict(good, ended="2026-10-2")), json.dumps(dict(good, ended=20261020101010)),
                    json.dumps(dict(good, cost_usd=float("nan"))), json.dumps(dict(good, tokens=float("inf"))),
                    json.dumps(dict(good, tokens=float("-inf"))),
                    json.dumps(dict(good, cost_usd=1.0)).replace("1.0", "1e999")):
            with self.subTest(raw=raw):
                write(self.root, ".loop/history.jsonl", json.dumps(good) + "\n" + raw + "\n" + json.dumps(good) + "\n")
                found = self.history()
                self.assertEqual(found["skipped_lines"], 1)
                self.assertEqual(len(found["runs"]), 2)

    def test_skipped_lines_are_summed_across_files_whatever_their_date(self):
        old = dict(self.harness[0], v=2)  # before SINCE, and still a bad line
        write(self.root, ".loop/history.jsonl", "not json\n" + json.dumps(old) + "\n")
        write(self.root, ".loop/projects/app/history.jsonl", json.dumps(dict(self.app[0], v=True)) + "\n")
        self.assertEqual(self.history()["skipped_lines"], 3)

    def test_a_trailing_newline_is_no_line_to_skip(self):
        self.fill_history()
        self.assertEqual(self.history()["skipped_lines"], 0)

    def test_nan_in_a_line_cant_make_the_output_invalid_json(self):
        write(self.root, ".loop/history.jsonl",
              json.dumps(dict(finished(7, "2026-10-20T10:00:00"), cost_usd=float("nan"))) + "\n")
        code, out = self.main()
        self.assertEqual(code, 0)
        self.assertNotIn("NaN", out)
        self.assertEqual(json.loads(out)["loop_history"]["runs"], [])

    def test_odd_values_exit_0_and_count_only_in_runs(self):
        for odd in ({"outcome": ["pr"], "rounds": "lots"}, {"outcome": {"a": 1}, "rounds": True},
                    {"outcome": "building", "rounds": None}, {"outcome": None, "rounds": [3]}):
            with self.subTest(odd=odd):
                lines(self.root, ".loop/history.jsonl", [dict(finished(7, "2026-10-20T10:00:00"), **odd)])
                code, out = self.main()
                self.assertEqual(code, 0)
                found = json.loads(out)["loop_history"]
                self.assertEqual(len(found["runs"]), 1)
                self.assertIsNone(found["runs"][0]["rounds"])
                self.assertEqual(found["by_outcome"], {"pr": 0, "blocked": 0, "stopped": 0, "skipped": 0})
                day = {r["day"]: r for r in found["by_day"]}["2026-10-20"]
                self.assertEqual(day, {"day": "2026-10-20", "runs": 1, "pr": 0, "blocked": 0, "stopped": 0,
                                       "skipped": 0, "more_than_one_round": 0})

    def test_a_field_of_the_wrong_type_prints_as_null(self):
        lines(self.root, ".loop/history.jsonl", [dict(
            finished(7, "2026-10-20T10:00:00"), started=[LEAK], outcome={"text": LEAK}, tests=LEAK, verdicts=[LEAK, 1],
            tokens="lots", cost_usd=True)])
        code, out = self.main()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["loop_history"]["runs"], [
            {"issue": "issue-7", "started": None, "ended": "2026-10-20T10:00:00", "outcome": None, "rounds": 1,
             "tests": None, "verdicts": None, "tokens": None, "cost_usd": None}])
        self.assertNotIn(LEAK, out)

    def test_a_list_nested_too_deep_to_print_doesnt_stop_the_script(self):
        for depth in (600, 100_000):
            with self.subTest(depth=depth):
                write(self.root, ".loop/history.jsonl",
                      '{"v": 1, "ended": "2026-10-20T10:00:00", "issue": 7, "tests": ' + "[" * depth + "]" * depth + "}\n")
                code, out = self.main()
                self.assertEqual(code, 0)
                self.assertIn("loop_history", json.loads(out))

    def test_an_issue_that_isnt_a_whole_number_prints_as_null(self):
        for odd in ("free text " + LEAK, True, 7.5, None):
            with self.subTest(odd=odd):
                lines(self.root, ".loop/history.jsonl", [dict(finished(7, "2026-10-20T10:00:00"), issue=odd)])
                found = self.history()
                self.assertIsNone(found["runs"][0]["issue"])
                self.assertEqual(found["skipped_lines"], 0)

    def test_the_folder_names_the_project_not_the_line(self):
        lines(self.root, ".loop/history.jsonl", [finished(7, "2026-10-20T10:00:00", project="other")])
        lines(self.root, ".loop/projects/app/history.jsonl", [finished(7, "2026-10-21T10:00:00", project="other")])
        self.assertEqual([r["issue"] for r in self.history()["runs"]], ["issue-7", "app/issue-7"])

    def test_the_docstring_has_the_section_and_says_it_keys_on_ended(self):
        doc = " ".join(dashboard_data.__doc__.split())
        self.assertIn("loop_history every loop run that ended since --since", doc)
        self.assertIn("It keys on `ended`", doc)
        for sentence in ("A run counts when the date of its `ended`, its first 10 characters, is on or after `--since`.",
                         "A run ending after today counts in `runs` and `by_outcome` but has no day.",
                         "`by_outcome` has `pr`, `blocked`, `stopped` and `skipped`, every key always present.",
                         "Run fields: `issue`, `started`, `ended`, `outcome`, `rounds`, `tests`, `verdicts`, `tokens` "
                         "and `cost_usd`. Nothing else goes in.",
                         "Issue names: `issue-N` for this repo and `<name>/issue-N` for a project.",
                         'Why values: `{"value": null, "why": "no run history"}` and `"unreadable"`.'):
            self.assertIn(sentence, doc)

    def test_a_run_before_since_appears_nowhere_and_isnt_skipped(self):
        self.fill_history()
        found = self.history()
        self.assertNotIn("issue-1", [r["issue"] for r in found["runs"]])
        self.assertNotIn("2026-10-01", [r["day"] for r in found["by_day"]])
        self.assertEqual(sum(found["by_outcome"].values()), len(found["runs"]))
        self.assertEqual(sum(r["runs"] for r in found["by_day"]), len(found["runs"]))
        self.assertEqual(found["skipped_lines"], 0)

    def test_a_run_started_before_since_and_ended_after_counts_here_not_in_loop_spend(self):
        started = "2026-10-10T09:00:00"
        lines(self.root, ".loop/history.jsonl", [finished(7, "2026-10-16T09:00:00", started=started)])
        write(self.root, ".loop/issue-7/usage.json", [run(started, "plan", "m", 10, 1.0)])
        found = self.build()
        self.assertEqual([r["issue"] for r in found["loop_history"]["runs"]], ["issue-7"])
        self.assertEqual(found["loop_spend"]["by_issue"], {})

    def test_an_unreadable_project_file_doesnt_lose_the_harnesss_runs(self):
        for spoil in (lambda path: path.write_bytes(b"\xff\xfe not utf-8\n"), lambda path: path.mkdir()):
            with self.subTest(spoil=spoil):
                lines(self.root, ".loop/history.jsonl", self.harness[1:2])
                path = self.root / ".loop" / "projects" / "app" / "history.jsonl"
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.is_dir():
                    path.rmdir()
                path.unlink(missing_ok=True)
                spoil(path)
                self.assertEqual([r["issue"] for r in self.history()["runs"]], ["issue-2"])

    def test_every_file_unreadable_is_unreadable_and_one_empty_file_is_not(self):
        (self.root / ".loop").mkdir()
        (self.root / ".loop" / "history.jsonl").mkdir()
        self.assertEqual(self.history(), {"value": None, "why": "unreadable"})
        (self.root / ".loop" / "history.jsonl").rmdir()
        write(self.root, ".loop/history.jsonl", "")
        self.assertEqual(self.history()["runs"], [])

    def test_no_other_field_and_no_path_reaches_the_output(self):
        leaky = dict(finished(7, "2026-10-20T10:00:00"), run=LEAK, project=LEAK, agent=LEAK, reviewer=LEAK,
                     title=LEAK, note=LEAK, pr="https://github.com/o/r/pull/1?" + LEAK)
        lines(self.root, ".loop/history.jsonl", [leaky])
        code, out = self.main()
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["loop_history"]["runs"]), 1)
        for leak in (LEAK, str(self.root), "github.com"):
            self.assertNotIn(leak, out)

    def test_the_other_sections_are_the_same_with_and_without_history_files(self):
        self.fill()
        self.gh(PRS)
        before = self.build()
        self.fill_history()
        after = self.build()
        self.assertEqual(before.pop("loop_history"), {"value": None, "why": "no run history"})
        self.assertEqual(len(after.pop("loop_history")["runs"]), 6)
        self.assertEqual(before, after)


class Privacy(Factory):
    def test_titles_and_notes_only_under_waiting_and_no_address_prompt_reason_or_path_anywhere(self):
        self.fill()
        self.gh(PRS)
        code, out = self.main()
        self.assertEqual(code, 0)
        found = json.loads(out)
        for section in found:
            if section != "waiting":
                self.assertNotIn(LEAK, json.dumps(found[section]), section)
        for leak in (str(self.root), str(self.root.parent), "github.com"):
            self.assertNotIn(leak, out)
        # The exemption is used: waiting carries the titles and the note, nothing else of LEAK's.
        self.assertEqual([(b["title"], b["note"]) for b in found["waiting"]["blocked"]], [(LEAK, LEAK)])
        self.assertTrue(all(p["title"].endswith(LEAK) for p in found["waiting"]["pull_requests"]))


if __name__ == "__main__":
    unittest.main()
