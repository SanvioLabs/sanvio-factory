"""Run with: python3 -m unittest discover -s tests

The reference store in examples/usage-store/ (SPEC-004 phase 4): the validator, and the SQL every RQ panel
runs. The SQL tests need DuckDB and skip without it:

    uv run --no-project --with duckdb==1.5.6 --with pytz python3 -m unittest tests.test_usage_store

1.5.6 is the DuckDB the pinned Grafana plugin carries. All the data here is invented.
"""
import datetime
import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "examples" / "usage-store"
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(STORE))
import export  # noqa: E402 (the imports need those folders on the path first)
import usage_shape  # noqa: E402 (same reason)
import send_usage  # noqa: E402 (same reason)
import usage_log  # noqa: E402 (same reason)
import render  # noqa: E402 (same reason)
import validator  # noqa: E402 (same reason)

HAVE_DUCKDB = all(importlib.util.find_spec(m) is not None for m in ("duckdb", "pytz"))  # pytz: DuckDB returns time zones with it
PERSON = {"SANVIO_HEADLESS": "", "HARNESS_HEADLESS": "", "SANVIO_USAGE_LOG": "", "HARNESS_USAGE_LOG": ""}


def run_line(issue, ended, **extra):
    line = {"v": 1, "run": "{}-{}".format(issue, ended), "issue": issue, "project": None, "started": ended,
            "ended": ended, "outcome": "pr", "rounds": 2, "tests": ["fail", "pass"], "verdicts": ["FIX", "PASS"],
            "fix_reasons": [["tests-failed"], []], "tests_changed": [False, False], "tokens": 1000,
            "cost_usd": 1.5, "agent": "claude", "reviewer": "claude"}
    line.update(extra)
    return line


def write_lines(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(l) + "\n" for l in lines), encoding="utf-8")


class Fixture(unittest.TestCase):
    """A repo with a usage log, loop runs and a live loop, sending into a folder store."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.store = Path(self.tmp.name) / "store"
        self.repo.mkdir()
        patcher = mock.patch.dict(os.environ, PERSON)
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.repo / ".sanvio").mkdir()
        (self.repo / ".sanvio" / "export.json").write_text(json.dumps(
            {"store": {"kind": "folder", "path": str(self.store)}, "node": "bench", "auto": True}))
        (self.repo / "loop.json").write_text(json.dumps({"max_issue_tokens": 10000}))
        write_lines(usage_log.log_path(self.repo), [
            {"ts": "2026-11-20T09:00:00Z", "session": "a", "event": "skill", "name": "review-pr"},
            {"ts": "2026-11-20T09:05:00Z", "session": "a", "event": "skill", "name": "review-pr"},
            {"ts": "2026-11-20T09:10:00Z", "session": "a", "event": "agent", "name": "reviewer"},
            {"ts": "2026-11-21T09:00:00Z", "session": "b", "event": "guard_ask", "rule": "connector-write",
             "tool": "mcp__mail__send"},
            {"ts": "2026-11-21T09:00:01Z", "session": "b", "event": "ask_approved", "rule": "connector-write",
             "tool": "mcp__mail__send"},
        ])
        write_lines(self.repo / ".loop" / "history.jsonl", [
            run_line(1, "2026-11-20T10:00:00"), run_line(2, "2026-11-21T10:00:00", rounds=4, cost_usd=2.5)])

    def send_days(self):
        return send_usage.send_auto(self.repo, datetime.date(2026, 11, 21))


class Validator(Fixture):
    def test_good_objects_are_accepted_at_the_same_path_and_incoming_is_emptied(self):
        keys = self.send_days()
        results = validator.sort_all(validator.FolderStore(self.store))
        self.assertEqual(sorted(dest for dest, _ in results), sorted("accepted/" + k[len("incoming/"):] for k in keys))
        self.assertEqual(list((self.store / "incoming").rglob("*.json")), [])
        for key in validator.SHAPE_FILES:
            self.assertTrue((self.store / key).is_file(), key)

    def test_an_object_off_the_shape_is_rejected_with_its_reason(self):
        self.send_days()
        bad = self.store / "incoming" / "bench" / "someone" / "general" / "x.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text(json.dumps({"kind": "bundle", "title": "Fix the payments bug"}))
        results = dict(validator.sort_all(validator.FolderStore(self.store)))
        self.assertIn("rejected/bench/someone/general/x.json", results)
        reason = json.loads((self.store / "rejected/bench/someone/general/x.reason.json").read_text())["reason"]
        self.assertIn("title", reason)

    def test_a_bundle_filed_under_someone_else_is_rejected(self):
        found = export.bundle(self.repo, "2026-11-21", "2026-11-21")
        other = self.store / "incoming" / "bench" / "somebody-else" / "general" / (found["bundle_id"] + ".json")
        other.parent.mkdir(parents=True)
        other.write_text(json.dumps(found))
        (dest, reason), = validator.sort_all(validator.FolderStore(self.store))
        self.assertTrue(dest.startswith("rejected/"))
        self.assertIn("path", reason)

    def accept(self, *bundles):
        store = validator.FolderStore(self.store)
        for found in bundles:
            store.write(send_usage.key_for(found, {"kind": "folder"}), json.dumps(found).encode("utf-8"))
            validator.sort_all(store)
        return sorted(p.name for p in (self.store / "marks").rglob("*.json"))

    def test_a_period_resent_with_the_same_chain_head_and_new_counts_marks_both(self):
        first = export.bundle(self.repo, "2026-11-20", "2026-11-20", last="2026-11-20")
        again = dict(first, usage=dict(first["usage"], sessions=99))
        self.assertEqual(self.accept(first, again), [first["bundle_id"] + ".before.json", first["bundle_id"] + ".json"])

    def test_different_periods_with_one_chain_head_are_not_marked(self):
        # a day's bundle and a sprint's, or yesterday's and today's, exported together: same head, other counts
        day = export.bundle(self.repo, "2026-11-21", "2026-11-21", last="2026-11-21")
        sprint = export.bundle(self.repo, "2026-11-01", "2026-11-21", last="2026-11-21")
        self.assertEqual(day["chain_head"], sprint["chain_head"])
        self.assertNotEqual(day["usage"], sprint["usage"])
        self.assertEqual(self.accept(day, sprint), [])

    def test_a_bundle_with_no_chain_head_after_one_with_one_marks_both(self):
        first = export.bundle(self.repo, "2026-11-20", "2026-11-20", last="2026-11-20")
        later = dict(export.bundle(self.repo, "2026-11-21", "2026-11-21", last="2026-11-21"), chain_head=None)
        self.assertEqual(self.accept(first, later), sorted([first["bundle_id"] + ".before.json", later["bundle_id"] + ".json"]))

    def test_a_folder_store_drops_what_is_older_than_its_days_and_keeps_the_shape_files(self):
        self.send_days()
        store = validator.FolderStore(self.store)
        validator.sort_all(store)
        accepted = sorted(store.keys("accepted/bench/"))
        old = self.store / accepted[0]
        os.utime(old, (0, 0))
        self.assertEqual(store.prune(90), [accepted[0]])
        self.assertFalse(old.exists())
        self.assertEqual(sorted(store.keys("accepted/bench/")), accepted[1:])
        for key in validator.SHAPE_FILES:
            os.utime(self.store / key, (0, 0))
        self.assertEqual(store.prune(90), [])

    def test_the_command_runs_over_a_folder(self):
        self.send_days()
        with mock.patch("sys.stdout"):
            self.assertEqual(validator.main(["--folder", str(self.store)]), 0)


class Provisioning(unittest.TestCase):
    """REQ-022: Grafana's files hold the SQL in queries/, and nothing that names a store or a secret."""

    def test_every_provisioning_file_is_what_render_writes(self):
        with mock.patch("sys.stdout"):
            self.assertEqual(render.main(["--check"]), 0, "run: python3 examples/usage-store/render.py")

    def test_every_panel_and_rule_runs_a_query_file_unchanged(self):
        texts = "".join(path.read_text() for path in render.files())
        for name in ["rq-{}.sql".format(n) for n in range(1, 7)] + [a[0] for a in render.ALERTS]:
            body = render.sql(name).splitlines()[-1].strip()
            self.assertIn(body, texts, name)

    def test_the_team_data_source_has_no_detailed_view_and_the_store_comes_from_the_environment(self):
        general = (STORE / "grafana" / "provisioning" / "datasources" / "usage.yaml").read_text()
        self.assertNotIn("/detailed/", general)
        self.assertNotIn("VIEW commands", general)
        for path in render.files():
            text = path.read_text()
            self.assertNotRegex(text, r"s3://[a-z0-9]", path)
            self.assertNotRegex(text, r"https?://", path)

    def test_the_local_grafana_listens_on_loopback_only(self):
        compose = (STORE / "local" / "compose.yaml").read_text()
        self.assertIn('"127.0.0.1:3000:3000"', compose)
        self.assertIn(":/store:ro", compose)

    def test_the_cloud_example_config_is_one_the_sender_takes(self):
        example = json.loads((STORE / "cloud" / "export.example.json").read_text())
        store = send_usage.store_of(example)
        self.assertEqual(store["kind"], "s3")
        self.assertTrue(store["detailed_key"].startswith("arn:"), "the bucket policy compares the key's ARN")

    def test_the_image_and_plugin_are_pinned(self):
        dockerfile = (STORE / "Dockerfile").read_text()
        self.assertRegex(dockerfile, r"FROM grafana/grafana-oss:[0-9.]+-ubuntu@sha256:[0-9a-f]{64}")
        self.assertRegex(dockerfile, r"ARG PLUGIN_SHA256=[0-9a-f]{64}")
        self.assertIn("sha256sum -c", dockerfile)


def columns(sql):
    """Each read_json's columns in a SQL file: [{key: type}], in order."""
    out = []
    for block in re.findall(r"columns = \{(.*?)\n\s*\}\)", sql, re.S):
        out.append(dict(re.findall(r"'([a-z_]+)': '([^']*)'", block)))
    return out


def fields(kind):
    """The field names of the outermost STRUCT in a DuckDB type, such as STRUCT(a INT, "b" VARCHAR)[]."""
    body = kind[kind.index("STRUCT(") + len("STRUCT("):]
    depth, part, parts = 0, "", []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(part)
            part = ""
        else:
            part += ch
    parts.append(part)
    return {p.strip().split()[0].strip('"') for p in parts}


class ViewsMatchTheShape(unittest.TestCase):
    """F11: the views name their columns, so a key added or renamed in usage_shape.py has to change them too.
    Runs without DuckDB, so CI catches the drift."""

    def setUp(self):
        queries = STORE / "queries"
        self.bundle, self.heartbeat = columns((queries / "views.sql").read_text())
        (self.detailed,) = columns((queries / "views-detailed.sql").read_text())

    def test_bundle_columns_are_the_bundle_keys(self):
        self.assertEqual(set(self.bundle), set(usage_shape.BUNDLE_KEYS))
        self.assertEqual(fields(self.bundle["usage"]), set(usage_shape.USAGE.keys))
        self.assertEqual(fields(self.bundle["loop"]), set(usage_shape.LOOP_RUN_KEYS))
        self.assertEqual(fields(self.bundle["loop_config"]), set(usage_shape.LOOP_CONFIG.keys))
        self.assertEqual(fields(self.bundle["factory"]), set(usage_shape.FACTORY.keys))
        self.assertEqual(fields(self.bundle["period"]), {"first", "last"})

    def test_heartbeat_columns_are_the_heartbeat_keys(self):
        self.assertEqual(set(self.heartbeat), set(usage_shape.HEARTBEAT_KEYS))
        self.assertEqual(fields(self.heartbeat["loops"]), set(usage_shape.LOOP_BEAT.keys))

    def test_detailed_columns_read_the_commands_whole(self):
        self.assertEqual(fields(self.detailed["commands"]), set(usage_shape.COMMAND.keys))


@unittest.skipUnless(HAVE_DUCKDB, "needs DuckDB: uv run --no-project --with duckdb==1.5.6 --with pytz python3 -m unittest "
                                  "tests.test_usage_store")
class Queries(Fixture):
    """AC-017's local half: each RQ file runs unchanged over a folder store's accepted/."""

    def connect(self, detailed=False):
        import duckdb
        db = duckdb.connect()
        files = ["views.sql"] + (["views-detailed.sql"] if detailed else []) + ["lock.sql"]
        for name in files:
            db.execute((STORE / "queries" / name).read_text().replace("${USAGE_ROOT}", str(self.store)))
        return db

    def rows(self, name, detailed=False):
        db = self.connect(detailed)
        cursor = db.execute((STORE / "queries" / name).read_text())
        head = [d[0] for d in cursor.description]
        return [dict(zip(head, row)) for row in cursor.fetchall()]

    def test_an_empty_store_reads_as_no_rows_not_an_error(self):
        validator.sort_all(validator.FolderStore(self.store))
        for n in range(1, 6):
            self.assertEqual(self.rows("rq-{}.sql".format(n)), [], n)
        self.assertEqual(self.rows("rq-6.sql", detailed=True), [])

    def test_rq1_counts_skills_and_agents_across_bundles(self):
        self.send_days()
        validator.sort_all(validator.FolderStore(self.store))
        got = {(r["kind"], r["name"]): r["times"] for r in self.rows("rq-1.sql")}
        self.assertEqual(got, {("skill", "review-pr"): 2, ("agent", "reviewer"): 1})

    def test_rq2_and_rq3_count_each_run_once_however_many_bundles_carry_it(self):
        self.send_days()
        self.send_days()  # the same days again: the same bundle ids, replaced
        found = export.bundle(self.repo, "2026-11-01", "2026-11-21")  # a sprint bundle overlapping both
        send_usage.send_bundle(self.repo, json.dumps(found).encode("utf-8"), send_usage.store_of(export.config(self.repo)))
        validator.sort_all(validator.FolderStore(self.store))
        (cost,) = self.rows("rq-2.sql")
        self.assertEqual((cost["pull_requests"], cost["cost_usd"]), (2, 4.0))
        (rounds,) = self.rows("rq-3.sql")
        self.assertEqual((rounds["runs"], rounds["mean_rounds"]), (2, 3.0))

    def test_rq4_pairs_asks_with_approvals(self):
        self.send_days()
        validator.sort_all(validator.FolderStore(self.store))
        (row,) = self.rows("rq-4.sql")
        self.assertEqual((row["name"], row["asked"], row["approved"]), ("mcp__mail__send", 1, 1))

    def test_rq5_and_the_alerts_read_the_heartbeats(self):
        loop = self.repo / ".loop"
        (loop / "status.json").write_text(json.dumps({"queue": [{"number": 9}],
                                                      "issues": [{"number": 3, "state": "working", "tokens": 9000}]}))
        (loop / "lock").write_text(str(os.getpid()))
        send_usage.send_heartbeat(self.repo)
        validator.sort_all(validator.FolderStore(self.store))
        (node,) = self.rows("rq-5.sql")
        self.assertEqual((node["node"], node["loops_alive"], node["waiting"]), ("bench", 1, 1))
        (silent,) = self.rows("alert-silent-node.sql")
        self.assertLess(silent["minutes_silent"], 5)
        (spend,) = self.rows("alert-budget.sql")
        self.assertEqual((spend["run"], spend["percent_of_budget"]), ("bench/factory#3", 90.0))

    def test_overlapping_bundles_count_each_day_once(self):
        # two default 14-day exports a day apart, both holding the same two review-pr lines
        store = send_usage.store_of(export.config(self.repo))
        for today in ("2026-11-21", "2026-11-22"):
            since = (datetime.date.fromisoformat(today) - datetime.timedelta(days=14)).isoformat()
            send_usage.send_bundle(self.repo, json.dumps(export.bundle(self.repo, since, today)).encode("utf-8"), store)
        validator.sort_all(validator.FolderStore(self.store))
        got = {(r["kind"], r["name"]): r["times"] for r in self.rows("rq-1.sql")}
        self.assertEqual(got[("skill", "review-pr")], 2)

    def test_a_stopped_loop_on_a_live_machine_raises_the_dead_loop_alert(self):
        (self.repo / ".loop" / "status.json").write_text(json.dumps({"queue": [], "issues": []}))
        send_usage.send_heartbeat(self.repo)  # no lock file: the loop isn't running, the machine is
        validator.sort_all(validator.FolderStore(self.store))
        (row,) = self.rows("alert-dead-loop.sql")
        self.assertEqual((row["loop"], row["stopped"]), ("bench/factory", 1))
        (silent,) = self.rows("alert-silent-node.sql")
        self.assertLess(silent["minutes_silent"], 5)  # the silent-node rule alone wouldn't have fired

    def test_a_node_name_with_a_space_is_accepted_under_its_safe_name(self):
        cfg = json.loads((self.repo / ".sanvio" / "export.json").read_text())
        (self.repo / ".sanvio" / "export.json").write_text(json.dumps(dict(cfg, node="Bench Mac's")))
        self.send_days()
        send_usage.send_heartbeat(self.repo)
        results = validator.sort_all(validator.FolderStore(self.store))
        self.assertTrue(results)
        self.assertTrue(all(reason is None for _, reason in results), results)
        self.assertEqual({r["node"] for r in self.rows("rq-5.sql")}, {"Bench_Mac_s"})

    def test_a_viewer_query_reads_the_store_and_no_other_file(self):
        validator.sort_all(validator.FolderStore(self.store))
        db = self.connect()
        with self.assertRaises(Exception):
            db.execute("SELECT * FROM read_text('/etc/hosts')").fetchall()
        with self.assertRaises(Exception):
            db.execute("SET enable_external_access = true")

    def test_rq6_reads_detailed_commands(self):
        usage_log.opt_in(self.repo, now=datetime.datetime(2026, 11, 20, tzinfo=datetime.timezone.utc))
        write_lines(usage_log.commands_path(self.repo), [
            {"ts": "2026-11-21T09:00:00Z", "session": "b", "verdict": "ran", "text": "git status", "redactions": 0},
            {"ts": "2026-11-21T09:01:00Z", "session": "b", "verdict": "refused", "text": "git push", "redactions": 0}])
        found = export.bundle(self.repo, "2026-11-20", "2026-11-21", "detailed")
        path = self.repo / "detailed.json"
        path.write_text(json.dumps(found))
        send_usage.send_file(self.repo, path)
        validator.sort_all(validator.FolderStore(self.store))
        (row,) = self.rows("rq-6.sql", detailed=True)
        self.assertEqual((row["program"], row["runs"], row["refused"]), ("git", 2, 1))
        with self.assertRaises(Exception):
            self.rows("rq-6.sql")  # the general data source has no commands view


if __name__ == "__main__":
    unittest.main()
