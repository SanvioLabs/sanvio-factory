"""Run with: python3 -m unittest discover -s tests"""
import contextlib
import datetime
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))
import export  # noqa: E402 (needs scripts/ on the path first)
import send_usage  # noqa: E402 (same reason)
import usage_log  # noqa: E402 (same reason)

PERSON = {"SANVIO_HEADLESS": "", "HARNESS_HEADLESS": "", "SANVIO_USAGE_LOG": "", "HARNESS_USAGE_LOG": ""}


def run_main(root, *args, **env):
    """send_usage's main in root, as a person's session: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, dict(PERSON, **env)), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        code = send_usage.main(list(args), root=root)
    return code, out.getvalue(), err.getvalue()


class OptInAndOut(unittest.TestCase):
    def run_main(self, root, *args, **env):
        return run_main(root, *args, **env)

    def test_opt_in_then_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code, out, _ = self.run_main(root, "--opt-in", "detailed")
            self.assertEqual(code, 0)
            self.assertIn("Detailed mode is on until", out)
            self.assertTrue(usage_log.detailed_path(root).exists())
            self.assertEqual(self.run_main(root, "--opt-out")[:2], (0, "Detailed mode is off.\n"))
            self.assertEqual(self.run_main(root, "--opt-out")[:2], (0, "Detailed mode wasn't on.\n"))

    def test_a_headless_run_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = self.run_main(Path(tmp), "--opt-in", "detailed", SANVIO_HEADLESS="1")
            self.assertEqual(code, 1)
            self.assertIn("headless", err)
            self.assertFalse(usage_log.detailed_path(Path(tmp)).exists())

    def test_it_needs_one_of_the_two(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                send_usage.main([], root=Path("."))


COMMAND = {"ts": "2026-11-21T09:00:00Z", "session": "s1", "verdict": "ran", "text": "git status", "redactions": 0}
AWS_STAND_IN = """#!/bin/sh
# Records its arguments and the body it was given, as the real CLI would upload it.
printf '%s\\n' "$@" > "$RECORD/argv"
while [ $# -gt 0 ]; do
  if [ "$1" = "--body" ]; then cp "$2" "$RECORD/body"; fi
  shift
done
exit ${AWS_EXIT:-0}
"""


class Sending(unittest.TestCase):
    """SPEC-004 REQ-009 to REQ-012 and REQ-020, OBS-001."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.store = Path(self.tmp.name) / "store"
        patcher = mock.patch.dict(os.environ, PERSON)
        patcher.start()
        self.addCleanup(patcher.stop)

    def config(self, **cfg):
        path = self.root / ".sanvio" / "export.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg))

    def folder(self, **extra):
        self.config(store={"kind": "folder", "path": str(self.store)}, node="bench", **extra)

    def bundle_file(self, mode="general", **changes):
        found = export.bundle(self.root, "2026-11-20", "2026-11-21")
        if mode == "detailed":
            found = dict(found, mode="detailed", commands=[COMMAND])
        found.update(changes)
        path = self.root / "export.json"
        path.write_text(json.dumps(found, indent=2) + "\n")
        return path

    def sent(self):
        return sorted(str(p.relative_to(self.store)) for p in self.store.rglob("*.json")) if self.store.exists() else []

    def log_events(self):
        path = usage_log.log_path(self.root)
        return [json.loads(l)["event"] for l in path.read_text().splitlines()] if path.exists() else []

    def test_a_folder_store_gets_the_files_exact_bytes_under_incoming(self):
        self.folder()
        path = self.bundle_file()
        keys = send_usage.send_file(self.root, path)
        bundle = json.loads(path.read_text())
        self.assertEqual(keys, ["incoming/bench/{}/general/{}.json".format(bundle["user"], bundle["bundle_id"])])
        self.assertEqual((self.store / keys[0]).read_bytes(), path.read_bytes())
        self.assertEqual(self.log_events(), ["export_sent"])
        self.assertEqual(json.loads((self.root / ".sanvio" / "usage" / "last-send").read_text())["mode"], "general")

    def test_an_extra_key_is_refused_and_nothing_lands(self):
        self.folder()
        path = self.bundle_file(title="Fix the payments bug for Acme")
        with self.assertRaises(send_usage.Refused):
            send_usage.send_file(self.root, path)
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.log_events(), ["export_refused"])

    def test_a_command_a_second_scrub_would_change_is_refused(self):
        self.folder()
        token = "gh" + "p_" + "a1B2c3D4e5" * 4
        path = self.bundle_file("detailed")
        bundle = json.loads(path.read_text())
        bundle["commands"][0]["text"] = "git push " + token
        path.write_text(json.dumps(bundle))
        with self.assertRaises(send_usage.Refused) as caught:
            send_usage.send_file(self.root, path)
        self.assertNotIn(token, str(caught.exception))
        self.assertEqual(self.sent(), [])

    def test_a_clean_detailed_bundle_lands_under_detailed(self):
        self.folder()
        keys = send_usage.send_file(self.root, self.bundle_file("detailed"))
        self.assertIn("/detailed/", keys[0])

    def test_with_no_store_nothing_opens_a_connection_or_a_process(self):
        path = self.bundle_file()
        def refuse(*args, **kwargs):
            raise AssertionError("opened a connection or a process")
        with mock.patch.object(socket, "socket", refuse), mock.patch.object(subprocess, "run", refuse), \
                mock.patch.object(subprocess, "Popen", refuse):
            code, _, err = run_main(self.root, str(path))
        self.assertEqual(code, 1)
        self.assertIn("no store is configured", err)

    def test_auto_needs_the_switch_and_sends_two_general_days(self):
        self.folder()
        with self.assertRaises(send_usage.Refused):
            send_usage.send_auto(self.root, datetime.date(2026, 11, 21))
        self.folder(auto=True)
        keys = send_usage.send_auto(self.root, datetime.date(2026, 11, 21))
        self.assertEqual(len(keys), 2)
        days = sorted(json.loads((self.store / k).read_text())["period"]["first"] for k in keys)
        self.assertEqual(days, ["2026-11-20", "2026-11-21"])
        self.assertTrue(all("/general/" in k for k in keys))

    def test_auto_never_sends_detailed_even_while_it_is_on(self):
        self.folder(auto=True)
        usage_log.opt_in(self.root)
        keys = send_usage.send_auto(self.root)
        self.assertFalse(any("/detailed/" in k for k in keys))

    def test_an_s3_store_goes_through_the_cli_profile_with_the_files_bytes(self):
        record = Path(self.tmp.name) / "record"
        record.mkdir()
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir()
        (bin_dir / "aws").write_text(AWS_STAND_IN)
        (bin_dir / "aws").chmod(0o755)
        self.config(store={"kind": "s3", "bucket": "b", "prefix": "team", "profile": "usage-writer",
                           "region": "us-east-2", "detailed_key": "alias/usage-detailed"}, node="bench")
        path = self.bundle_file("detailed")
        env = {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "RECORD": str(record)}
        with mock.patch.dict(os.environ, env):
            keys = send_usage.send_file(self.root, path)
        argv = (record / "argv").read_text().split("\n")
        self.assertEqual(argv[:3], ["s3api", "put-object", "--bucket"])
        self.assertIn("usage-writer", argv)
        self.assertIn("alias/usage-detailed", argv)
        self.assertTrue(keys[0].startswith("team/incoming/bench/"))
        self.assertEqual((record / "body").read_bytes(), path.read_bytes())

    def test_a_refusing_store_is_reported_and_logged(self):
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir()
        (bin_dir / "aws").write_text("#!/bin/sh\necho 'An error occurred (AccessDenied)' >&2\nexit 254\n")
        (bin_dir / "aws").chmod(0o755)
        self.config(store={"kind": "s3", "bucket": "b", "profile": "p"}, node="bench")
        with mock.patch.dict(os.environ, {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}):
            with self.assertRaises(send_usage.Refused) as caught:
                send_usage.send_file(self.root, self.bundle_file())
        self.assertIn("AccessDenied", str(caught.exception))
        self.assertEqual(self.log_events(), ["export_refused"])


    def test_a_folder_it_cannot_write_is_refused_and_logged(self):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text("a file, not a folder")
        self.folder()
        with self.assertRaises(send_usage.Refused):
            send_usage.send_file(self.root, self.bundle_file())
        self.assertEqual(self.log_events(), ["export_refused"])

    def test_a_file_that_is_not_an_object_is_refused_and_logged(self):
        self.folder()
        path = self.root / "export.json"
        path.write_text("[]")
        with self.assertRaises(send_usage.Refused):
            send_usage.send_file(self.root, path)
        self.assertEqual(self.log_events(), ["export_refused"])

    def test_each_send_says_where_it_went(self):
        self.folder()
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            self.assertEqual(send_usage.main([str(self.bundle_file())], root=self.root), 0)
        self.assertIn("To: the folder " + str(self.store), out.getvalue())

    def test_an_abbreviated_flag_is_refused(self):
        with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
            send_usage.main(["--opt-i", "detailed"], root=self.root)
        self.assertFalse(usage_log.detailed_path(self.root).exists())

    def test_a_node_name_is_made_safe_in_the_bundle_and_the_key(self):
        self.config(store={"kind": "folder", "path": str(self.store)}, node="Bench Mac's")
        (key,) = send_usage.send_file(self.root, self.bundle_file())
        self.assertTrue(key.startswith("incoming/Bench_Mac_s/"), key)
        self.assertEqual(json.loads((self.store / key).read_text())["node"], "Bench_Mac_s")


class Heartbeat(unittest.TestCase):
    """SPEC-004 REQ-012: alive, waiting, the issue in progress; an unlisted project only alive and waiting."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def state(self, folder, alive, queue, rows):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "status.json").write_text(json.dumps({"queue": queue, "issues": rows}))
        (folder / "lock").write_text(str(os.getpid() if alive else 999999))

    def test_live_and_dead_loops_and_no_titles(self):
        (self.root / "loop.json").write_text(json.dumps({"max_issue_tokens": 5000, "projects": {"acme": {}}}))
        (self.root / ".sanvio").mkdir()
        (self.root / ".sanvio" / "export.json").write_text(json.dumps({"node": "pi-1",
                                                                      "export_projects": {"acme": "web-app"}}))
        working = {"number": 7, "title": "Fix the payments bug", "state": "working", "tokens": 1200}
        self.state(self.root / ".loop", True, [{"number": 8}], [working])
        self.state(self.root / ".loop" / "projects" / "acme", False, [], [working])
        self.state(self.root / ".loop" / "projects" / "secret-client", True, [{"number": 1}, {"number": 2}], [working])
        import loop
        with mock.patch.object(loop, "pid_alive", lambda pid: pid == os.getpid()):
            got = send_usage.heartbeat(self.root)
        self.assertEqual(send_usage.usage_shape.problems(got), [])
        loops = {l["label"]: l for l in got["loops"]}
        self.assertEqual(loops["factory"], {"label": "factory", "alive": True, "waiting": 1, "issue": 7,
                                            "tokens": 1200, "budget": 5000})
        self.assertEqual(loops["web-app"]["alive"], False)
        self.assertIsNone(loops["web-app"]["issue"])
        hidden = [l for label, l in loops.items() if label.startswith("project-")]
        self.assertEqual(len(hidden), 1)
        self.assertEqual((hidden[0]["alive"], hidden[0]["waiting"], hidden[0]["issue"]), (True, 2, None))
        text = json.dumps(got)
        for leak in ("payments", "secret-client", "acme"):
            self.assertNotIn(leak, text)


if __name__ == "__main__":
    unittest.main()
