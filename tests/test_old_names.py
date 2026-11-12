"""Run with: python3 -m unittest discover -s tests"""
import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import old_names  # noqa: E402 (needs scripts/ on the path first)


class Folders(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_the_old_loop_folder_is_named_for_the_token_reports(self):
        self.assertEqual(old_names.old_loop_home(self.tmp), self.tmp / ".harness-loop")


class Moving(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_nothing_to_move_says_nothing(self):
        self.assertIsNone(old_names.move_old_state(self.tmp))
        (self.tmp / ".sanvio").mkdir()
        self.assertIsNone(old_names.move_old_state(self.tmp))

    def test_the_old_folder_moves_whole_with_what_is_in_it(self):
        run = self.tmp / ".harness" / "factories" / "run-7.json"
        run.parent.mkdir(parents=True)
        run.write_text("{}", encoding="utf-8")
        said = old_names.move_old_state(self.tmp)
        self.assertFalse((self.tmp / ".harness").exists())
        self.assertEqual((self.tmp / ".sanvio" / "factories" / "run-7.json").read_text(encoding="utf-8"), "{}")
        self.assertIn("moved .harness/ to .sanvio/", said)

    def test_a_new_folder_holding_only_a_mods_focus_is_folded_in_and_the_move_goes_ahead(self):
        # An updated mod can write .sanvio/project/<id> before any session has moved .harness/ (review).
        run = self.tmp / ".harness" / "factories" / "run-7.json"
        run.parent.mkdir(parents=True)
        run.write_text("{}", encoding="utf-8")
        focus = self.tmp / ".sanvio" / "project" / "aaaaaaaa-1111"
        focus.parent.mkdir(parents=True)
        focus.write_text("app\n", encoding="utf-8")
        said = old_names.move_old_state(self.tmp)
        self.assertIn("moved .harness/ to .sanvio/", said)
        self.assertFalse((self.tmp / ".harness").exists())
        self.assertTrue((self.tmp / ".sanvio" / "factories" / "run-7.json").is_file())
        self.assertEqual((self.tmp / ".sanvio" / "project" / "aaaaaaaa-1111").read_text(encoding="utf-8"), "app\n")

    def test_both_folders_are_left_alone_and_named(self):
        (self.tmp / ".harness").mkdir()
        (self.tmp / ".sanvio").mkdir()
        said = old_names.move_old_state(self.tmp)
        self.assertTrue((self.tmp / ".harness").is_dir())
        self.assertIn(".harness/", said)
        self.assertIn("only .sanvio/ is read", said)

    def test_a_move_that_fails_is_reported_not_raised(self):
        (self.tmp / ".harness").mkdir()
        real = os.rename

        def refuse(*_):
            raise PermissionError("no")
        os.rename = refuse
        try:
            said = old_names.move_old_state(self.tmp)
        finally:
            os.rename = real
        self.assertIn("couldn't move .harness/", said)
        self.assertIn("nothing reads .harness/ now", said)


class Variables(unittest.TestCase):
    def test_old_variables_are_named_once_each(self):
        environ = {"HARNESS_RETRO": "on", "HARNESS_PULSE_FOLDER": "/p", "SANVIO_PULSE_FOLDER": "/p",
                   "HARNESS_HEADLESS": "1", "HARNESS_OTHER": "x"}
        self.assertEqual(old_names.old_variables(environ), ["HARNESS_RETRO"])


class Warning(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.said = []

    def warn(self, environ, session=101, day="20261109"):
        return old_names.warn_old_once(environ, marker_dir=self.dir, session=session, write=self.said.append, day=day)

    def test_an_old_name_alone_warns_once_naming_both(self):
        self.assertEqual(self.warn({"HARNESS_RETRO": "on"}), ["HARNESS_RETRO"])
        self.assertEqual(self.said, ["HARNESS_RETRO is set but does nothing now: set SANVIO_RETRO instead\n"])
        self.assertEqual(self.warn({"HARNESS_RETRO": "on"}), [])
        self.assertEqual(len(self.said), 1)

    def test_another_shell_is_told_too(self):
        self.warn({"HARNESS_EVALS_HOME": "/e"}, session=101)
        self.warn({"HARNESS_EVALS_HOME": "/e"}, session=202)
        self.assertEqual(len(self.said), 2)
        self.assertIn("SANVIO_EVALS_HOME", self.said[1])

    def test_under_claude_code_each_command_is_not_told_again(self):
        # Claude Code gives each Bash call a session of its own (review of #477), so the shell's session
        # can't be what makes it once.
        environ = {"HARNESS_RETRO": "on", "CLAUDECODE": "1"}
        with mock.patch.object(old_names.os, "getsid", side_effect=[101, 202, 303], create=True), \
                mock.patch.object(old_names.os, "getppid", side_effect=[101, 202, 303]):
            for _ in range(3):
                self.warn(environ, session=None)
        self.assertEqual(len(self.said), 1)

    def test_outside_claude_code_each_shell_is_told(self):
        with mock.patch.object(old_names.os, "getsid", side_effect=[101, 202], create=True), \
                mock.patch.object(old_names.os, "getppid", side_effect=[101, 202]):
            self.warn({"HARNESS_RETRO": "on"}, session=None)
            self.warn({"HARNESS_RETRO": "on"}, session=None)
        self.assertEqual(len(self.said), 2)

    def test_the_two_that_still_count_do_not_warn(self):
        for environ in ({"HARNESS_HEADLESS": "1"}, {"HARNESS_USAGE_LOG": "off"}, {"HARNESS_USAGE_LOG": " No "}):
            with self.subTest(environ=environ):
                self.assertEqual(self.warn(environ), [])
        self.assertEqual(self.said, [])
        self.assertEqual(list(self.dir.iterdir()), [], "nothing to say leaves no marker")

    def test_the_usage_log_switched_on_by_the_old_name_warns(self):
        self.warn({"HARNESS_USAGE_LOG": "on"})
        self.assertEqual(self.said, ["HARNESS_USAGE_LOG is set but does nothing now: set SANVIO_USAGE_LOG instead\n"])

    def test_no_warning_beside_the_new_name_or_for_other_names(self):
        self.warn({"HARNESS_PULSE_FOLDER": "/p", "SANVIO_PULSE_FOLDER": "/p"})
        self.warn({"HARNESS_OTHER": "x"})
        self.assertEqual(self.said, [])

    def test_a_marker_that_cannot_be_written_still_warns(self):
        self.warn({"HARNESS_RETRO": "on"}, session="missing/folder")
        self.assertEqual(len(self.said), 1)

    def test_an_old_days_marker_does_not_silence_a_later_shell(self):
        self.warn({"HARNESS_RETRO": "on"}, day="20261108")
        self.warn({"HARNESS_RETRO": "on"}, day="20261109")
        self.assertEqual(len(self.said), 2, "a reused session number on a later day is told again")

    @unittest.skipUnless(hasattr(os, "getuid"), "no user ids here")
    def test_another_users_marker_does_not_silence_this_shell(self):
        (self.dir / "sanvio-old-names-101-20261109").touch()
        with mock.patch.object(old_names.os, "getuid", return_value=os.getuid() + 1):
            self.assertEqual(self.warn({"HARNESS_RETRO": "on"}), ["HARNESS_RETRO"])
        self.assertEqual(len(self.said), 1)

    def test_only_a_hook_counts_as_one(self):
        hooks = ROOT / ".claude" / "hooks"
        self.assertTrue(old_names.in_a_hook([str(hooks / "usage_log.py")]))
        self.assertTrue(old_names.in_a_hook([str(hooks / "session_retro.py")]))
        for argv in ([str(ROOT / "scripts" / "pulse.py")], [str(ROOT / "hooks" / "x.py")], [""], []):
            with self.subTest(argv=argv):
                self.assertFalse(old_names.in_a_hook(argv))

    def test_the_hooks_say_nothing_and_leave_the_marker_unwritten(self):
        project = self.dir / "project"
        project.mkdir()
        markers = self.dir / "tmp"
        markers.mkdir()
        environ = {key: value for key, value in os.environ.items()
                   if not key.startswith(("SANVIO_", "HARNESS_"))}
        environ.update(HARNESS_RETRO="on", HARNESS_PULSE_FOLDER="/p", SANVIO_USAGE_LOG="off",
                       TMPDIR=str(markers), CLAUDE_PROJECT_DIR=str(project))
        for hook, event in (("usage_log.py", {"hook_event_name": "PreToolUse", "tool_name": "Skill",
                                              "tool_input": {"skill": "learn"}}),
                            ("session_retro.py", {"hook_event_name": "SessionEnd", "session_id": "s1"})):
            with self.subTest(hook=hook):
                result = subprocess.run([sys.executable, str(ROOT / ".claude" / "hooks" / hook)],
                                        input=json.dumps(event), capture_output=True, text=True,
                                        env=environ, timeout=30)
                self.assertEqual(result.returncode, 0)
                self.assertNotIn("HARNESS_", result.stderr)
                self.assertEqual(list(markers.glob("sanvio-old-names-*")), [])


class TheModule(unittest.TestCase):
    def test_it_imports_the_standard_library_and_names_only(self):
        tree = ast.parse((ROOT / "scripts" / "old_names.py").read_text(encoding="utf-8"), feature_version=(3, 9))
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                found.add((node.module or "").split(".")[0])
        self.assertLessEqual(found, {"os", "pathlib", "sys", "tempfile", "time", "names"})

    def test_only_what_still_reads_the_old_names_imports_them(self):
        found = set()
        for path in list((ROOT / "scripts").glob("*.py")) + list((ROOT / ".claude" / "hooks").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 9))
            if any(isinstance(node, ast.Import) and any(alias.name == "old_names" for alias in node.names)
                   for node in ast.walk(tree)):
                found.add(path.relative_to(ROOT).as_posix())
        self.assertEqual(found, {"scripts/names.py", "scripts/check_setup.py", "scripts/token_report.py",
                                 ".claude/hooks/session_start.py"})


if __name__ == "__main__":
    unittest.main()
