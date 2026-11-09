"""Run with: python3 -m unittest discover -s tests"""
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "session_retro.py"
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))
import loop  # noqa: E402 (the imports need those folders on the path first)
import session_retro  # noqa: E402 (same reason)

SESSION = "11111111-2222-3333-4444-555555555555"


def said(uuid, text, **extra):
    return dict({"type": "user", "uuid": uuid, "timestamp": "2026-10-31T10:00:00.000Z",
                 "message": {"role": "user", "content": text}}, **extra)


def edit(uuid, path):
    return {"type": "assistant", "uuid": uuid, "timestamp": "2026-10-31T10:00:01.000Z",
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t-" + uuid, "name": "Edit", "input": {"file_path": path}}]}}


def read(uuid, path):
    return {"type": "assistant", "uuid": uuid, "timestamp": "2026-10-31T10:00:02.000Z",
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t-" + uuid, "name": "Read", "input": {"file_path": path}}]}}


def tool_output(uuid, text):
    return {"type": "user", "uuid": uuid, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": text}]}}


CORRECTED = [said("r1", "Add the setting."), read("r2", "/work/AGENTS.md"), said("r3", "That's wrong, it goes in loop.json")]
QUIET = [said("r1", "Add the setting."), edit("r2", "/work/a.py"), said("r3", "Thanks, looks good")]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "harness"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text("local-data/\n")
        self.folder = self.root / "local-data" / "retro"

    def log(self, records, name=SESSION, where=None):
        path = (where or Path(self.tmp.name)) / (name + ".jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(one) + "\n" for one in records))
        return path

    def event(self, path, hook="SessionEnd", session=SESSION):
        return {"hook_event_name": hook, "session_id": session, "transcript_path": str(path)}

    def run_hook(self, stdin, **env):
        full = {k: v for k, v in os.environ.items() if not k.endswith(("_RETRO", "_HEADLESS"))}
        full.update(env, CLAUDE_PROJECT_DIR=str(self.root))
        return subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True,
                              env=full, timeout=30)

    def kept(self):
        return sorted(path.name for path in self.folder.glob("*.jsonl")) if self.folder.is_dir() else []


class Capture(Base):
    def test_off_by_default_nothing_is_copied_or_listed(self):
        result = self.run_hook(json.dumps(self.event(self.log(CORRECTED))))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.assertFalse(self.folder.exists())

    def test_a_correction_from_the_person_is_copied_and_listed(self):
        result = self.run_hook(json.dumps(self.event(self.log(CORRECTED))), SANVIO_RETRO="on")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.assertEqual(self.kept(), [SESSION + ".jsonl"])
        self.assertEqual(session_retro.listed(self.folder), [SESSION])

    def test_each_phrase_counts_and_no_comma_opens_one(self):
        for text in ("not what I asked for", "Please don't do that again", "learn from that",
                     "no, the other file", "That’s wrong"):
            path = self.log([said("r1", text)])
            self.assertTrue(session_retro.signals(path), text)

    def test_a_file_edited_three_times_counts(self):
        path = self.log([edit("e1", "/w/a.py"), edit("e2", "/w/a.py"), edit("e3", "/w/a.py")])
        found = session_retro.signals(path)
        self.assertEqual(found, [{"kind": "edited", "uuid": "e3", "file": "/w/a.py", "count": 3}])
        with mock.patch.dict(os.environ, {"SANVIO_RETRO": "on"}):
            self.assertEqual(session_retro.capture(self.root, self.event(path)), SESSION)

    def test_the_old_switch_does_nothing(self):
        with mock.patch.dict(os.environ, {"HARNESS_RETRO": "on"}):
            os.environ.pop("SANVIO_RETRO", None)
            self.assertFalse(session_retro.switched_on())

    def test_no_signal_is_not_copied(self):
        with mock.patch.dict(os.environ, {"SANVIO_RETRO": "on"}):
            self.assertIsNone(session_retro.capture(self.root, self.event(self.log(QUIET))))
        self.assertEqual(self.kept(), [])

    def test_text_the_person_did_not_write_is_not_a_signal(self):
        path = self.log([tool_output("t1", "no, file not found"),
                         said("s1", "no, summary of the earlier part", isCompactSummary=True),
                         said("s2", "that's wrong", isMeta=True),
                         said("s3", "that's wrong", isSidechain=True),
                         said("s4", "<command-name>/clear</command-name> no, that's wrong"),
                         edit("e1", "/w/a.py"), edit("e2", "/w/a.py"),
                         dict(edit("e3", "/w/a.py"), isSidechain=True)])
        self.assertEqual(session_retro.signals(path), [])

    def test_precompact_then_session_end_lists_it_once_and_keeps_the_longer_log(self):
        path = self.log(CORRECTED)
        with mock.patch.dict(os.environ, {"SANVIO_RETRO": "on"}):
            session_retro.capture(self.root, self.event(path, "PreCompact"))
            self.log(CORRECTED + [said("r4", "Done now")])
            session_retro.capture(self.root, self.event(path, "SessionEnd"))
        self.assertEqual(session_retro.listed(self.folder), [SESSION])
        self.assertIn('"r4"', (self.folder / (SESSION + ".jsonl")).read_text())

    def test_the_copy_and_its_folder_are_readable_by_their_owner_alone(self):
        with mock.patch.dict(os.environ, {"SANVIO_RETRO": "on"}):
            session_retro.capture(self.root, self.event(self.log(CORRECTED)))
        self.assertEqual(stat.S_IMODE(self.folder.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.folder / (SESSION + ".jsonl")).stat().st_mode), 0o600)

    def test_nothing_is_copied_where_git_does_not_ignore_the_folder(self):
        (self.root / ".gitignore").write_text("")  # as a ticket that dropped the line would leave it
        with mock.patch.dict(os.environ, {"SANVIO_RETRO": "on"}):
            self.assertIsNone(session_retro.capture(self.root, self.event(self.log(CORRECTED))))
        outside = Path(self.tmp.name) / "not-a-checkout"
        outside.mkdir()
        with mock.patch.dict(os.environ, {"SANVIO_RETRO": "on"}):
            self.assertIsNone(session_retro.capture(outside, self.event(self.log(CORRECTED))))
        self.assertEqual(self.kept(), [])
        self.assertFalse((outside / "local-data").exists())

    def test_a_run_bin_harness_started_is_not_copied(self):
        with mock.patch.dict(os.environ, {"SANVIO_RETRO": "on", "SANVIO_HEADLESS": "1"}):
            self.assertIsNone(session_retro.capture(self.root, self.event(self.log(CORRECTED))))

    def test_a_hook_run_that_fails_leaves_the_session_alone(self):
        for stdin in ("not json", json.dumps({"hook_event_name": "SessionEnd", "session_id": "../x",
                                              "transcript_path": "/nowhere"})):
            result = self.run_hook(stdin, SANVIO_RETRO="on")
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.assertFalse(self.folder.exists())

    def test_a_copy_older_than_30_days_is_deleted_on_the_next_run_even_when_off(self):
        with mock.patch.dict(os.environ, {"SANVIO_RETRO": "on"}):
            session_retro.capture(self.root, self.event(self.log(CORRECTED)))
        old = time.time() - 31 * 86400
        os.utime(self.folder / (SESSION + ".jsonl"), (old, old))
        result = self.run_hook(json.dumps(self.event(self.log(QUIET, name="other"), session="other")))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.kept(), [])
        self.assertEqual(session_retro.listed(self.folder), [])


class Kept(Base):
    """A transcripts folder of its own, and no session id from the session running the tests."""

    def setUp(self):
        super().setUp()
        self.transcripts = Path(self.tmp.name) / "projects"
        patcher = mock.patch.object(loop, "TRANSCRIPTS", self.transcripts)
        patcher.start()
        self.addCleanup(patcher.stop)
        environ = mock.patch.dict(os.environ)  # put back as it was after each test
        environ.start()
        self.addCleanup(environ.stop)
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)

    def own(self):
        """Claude Code's folder for this root's session logs."""
        return self.transcripts / re.sub(r"[^A-Za-z0-9-]", "-", os.path.abspath(str(self.root)))

    def replied(self, text, session=SESSION):
        session_retro.private_folder(self.folder)
        (self.folder / (session + ".reply.txt")).write_text(text)

    def keep(self, records=CORRECTED):
        with mock.patch.dict(os.environ, {"SANVIO_RETRO": "on"}):
            return session_retro.capture(self.root, self.event(self.log(records)))


class PromptAndRecord(Kept):
    def test_prompt_takes_the_oldest_kept_session_and_carries_what_the_person_corrected(self):
        self.keep()
        out = io.StringIO()
        self.assertEqual(session_retro.prompt(self.root, out=out), 0)
        self.assertIn("Session {} (kept), 1 correction signal".format(SESSION), out.getvalue())
        text = (self.folder / (SESSION + ".prompt.md")).read_text()
        self.assertIn('- r3 the person wrote: "That\'s wrong, it goes in loop.json"', text)
        self.assertIn("r2", text)  # the Read, from the loop's digest
        self.assertIn("FINDING: CAUSE | record id or none", text)

    def test_prompt_takes_the_first_kept_of_two(self):
        self.keep()
        with mock.patch.dict(os.environ, {"SANVIO_RETRO": "on"}):
            session_retro.capture(self.root, self.event(self.log(CORRECTED, name="second"), session="second"))
        self.assertEqual(session_retro.listed(self.folder), [SESSION, "second"])
        out = io.StringIO()
        session_retro.prompt(self.root, out=out)
        self.assertIn("Session {} (kept)".format(SESSION), out.getvalue())
        self.assertIn("waiting: 2", out.getvalue())

    def test_drop_deletes_a_kept_session_and_writes_nothing(self):
        self.keep()
        self.assertEqual(session_retro.drop(self.root, SESSION, out=io.StringIO()), 0)
        self.assertEqual(self.kept(), [])
        self.assertEqual(session_retro.listed(self.folder), [])
        self.assertFalse((self.root / ".loop" / "lessons.md").exists())
        self.assertEqual(session_retro.drop(self.root, SESSION, out=io.StringIO()), 1)

    def test_record_appends_a_session_entry_and_deletes_the_copy(self):
        self.keep()
        reply = ("FINDING: UNLOADED | r3 | this repo | steering | loop.json | The setting's home was never read.\n"
                 "FINDING: IGNORED | r-not-in-the-log | this repo | steering | AGENTS.md | Made up.\n"
                 "FINDING: GUESSED | r3 | this repo | steering | none | Not a cause.\n")
        self.replied(reply)
        out = io.StringIO()
        self.assertEqual(session_retro.record(self.root, SESSION, out=out), 0)
        entry = (self.root / ".loop" / "lessons.md").read_text()
        self.assertIn("session {}: 1 signal".format(SESSION), entry)
        self.assertIn("the person corrected the agent [record r3]", entry)
        self.assertNotIn("it goes in loop.json", entry)  # lessons.md is never pruned: no words of theirs
        self.assertIn("- UNLOADED (this repo, steering) loop.json: The setting's home was never read. [record r3]", entry)
        self.assertNotIn("Made up", entry)
        self.assertNotIn("Not a cause", entry)
        self.assertIn("dropped a finding: its record isn't in the session logs", out.getvalue())
        self.assertIn("dropped a finding: unknown cause or scope", out.getvalue())
        self.assertEqual(list(self.folder.iterdir()), [self.folder / "candidates.txt"])
        self.assertEqual(session_retro.listed(self.folder), [])

    def test_an_ignored_finding_the_log_contradicts_is_marked_unverified(self):
        self.keep()
        self.replied("FINDING: IGNORED | r3 | this repo | steering | /work/README.md | It was never read.\n")
        session_retro.record(self.root, SESSION, out=io.StringIO())
        self.assertIn("(unverified)", (self.root / ".loop" / "lessons.md").read_text())

    def test_with_none_kept_prompt_reads_this_session(self):
        folder = self.own()
        self.log(QUIET, name="older", where=folder)
        os.utime(folder / "older.jsonl", (1, 1))
        self.log(CORRECTED, name="newest", where=folder)
        out = io.StringIO()
        self.assertEqual(session_retro.prompt(self.root, out=out), 0)
        self.assertIn("Session newest (this session)", out.getvalue())
        self.replied("", session="newest")
        session_retro.record(self.root, "newest", out=io.StringIO())
        self.assertIn("session newest: 1 signal", (self.root / ".loop" / "lessons.md").read_text())
        self.assertTrue((folder / "newest.jsonl").exists())  # Claude Code's own log is never deleted

    def test_no_session_to_read_says_so(self):
        out = io.StringIO()
        self.assertEqual(session_retro.prompt(self.root, out=out), 1)
        self.assertEqual(session_retro.record(self.root, "../etc", out=io.StringIO()), 1)
        self.assertFalse((self.root / ".loop" / "lessons.md").exists())

    def test_current_is_the_session_claude_code_names_not_the_newest_log(self):
        self.log(CORRECTED, name="this-one", where=self.own())
        os.utime(self.own() / "this-one.jsonl", (1, 1))
        self.log(QUIET, name="a-peer", where=self.own())
        os.environ["CLAUDE_CODE_SESSION_ID"] = "this-one"
        out = io.StringIO()
        self.assertEqual(session_retro.prompt(self.root, current=True, out=out), 0)
        self.assertIn("Session this-one (this session)", out.getvalue())

    def test_record_never_reads_another_projects_session(self):
        self.log(CORRECTED, name="elsewhere", where=self.transcripts / "-some-client-repo")
        self.replied("", session="elsewhere")
        out = io.StringIO()
        self.assertEqual(session_retro.record(self.root, "elsewhere", out=out), 1)
        self.assertIn("No log for that session", out.getvalue())
        self.assertFalse((self.root / ".loop" / "lessons.md").exists())

    def test_record_without_a_saved_reply_writes_nothing(self):
        self.keep()
        out = io.StringIO()
        self.assertEqual(session_retro.record(self.root, SESSION, out=out), 1)
        self.assertIn("run classify first", out.getvalue())
        self.assertFalse((self.root / ".loop" / "lessons.md").exists())
        self.assertEqual(self.kept(), [SESSION + ".jsonl"])


class Classify(Kept):
    def ran(self, code=0, said="FINDING: ABSENT | r3 | this repo | steering | none | Nothing said it.\n"):
        calls = []

        def run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return subprocess.CompletedProcess(cmd, code, said, "")
        return calls, run

    def test_a_fresh_claude_that_can_only_read_gets_the_prompt_on_stdin_and_its_reply_is_saved(self):
        self.keep()
        session_retro.prompt(self.root, out=io.StringIO())
        calls, run = self.ran()
        out = io.StringIO()
        os.environ["CLAUDE_CODE_SESSION_ID"] = "the-session-running-the-command"
        self.assertEqual(session_retro.classify(self.root, SESSION, out=out, run=run), 0)
        cmd, kwargs = calls[0]
        self.assertEqual(cmd, ["claude", "-p"] + loop.UNTRUSTED_CLAUDE)
        self.assertEqual(kwargs["input"], (self.folder / (SESSION + ".prompt.md")).read_text())
        self.assertEqual((kwargs["env"]["SANVIO_RETRO"], kwargs["env"]["SANVIO_HEADLESS"]), ("off", "1"))
        self.assertNotIn("CLAUDE_CODE_SESSION_ID", kwargs["env"])
        reply = self.folder / (SESSION + ".reply.txt")
        self.assertIn("ABSENT", reply.read_text())
        self.assertEqual(stat.S_IMODE(reply.stat().st_mode), 0o600)
        self.assertIn("1 FINDING line", out.getvalue())
        self.assertEqual(session_retro.record(self.root, SESSION, out=io.StringIO()), 0)
        self.assertIn("- ABSENT", (self.root / ".loop" / "lessons.md").read_text())
        self.assertEqual(list(self.folder.iterdir()), [self.folder / "candidates.txt"])

    def test_a_classifier_that_fails_saves_nothing(self):
        self.keep()
        session_retro.prompt(self.root, out=io.StringIO())
        calls, run = self.ran(code=3)
        out = io.StringIO()
        self.assertEqual(session_retro.classify(self.root, SESSION, out=out, run=run), 1)
        self.assertIn("exited 3", out.getvalue())
        self.assertFalse((self.folder / (SESSION + ".reply.txt")).exists())

    def test_no_prompt_or_a_bad_id_runs_nothing(self):
        calls, run = self.ran()
        self.assertEqual(session_retro.classify(self.root, SESSION, out=io.StringIO(), run=run), 1)
        self.assertEqual(session_retro.classify(self.root, "../x", out=io.StringIO(), run=run), 1)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
