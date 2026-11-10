"""Run with: python3 -m unittest discover -s tests"""
import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import names  # noqa: E402 (needs scripts/ on the path first)


class Folders(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_the_new_folder_is_used_when_neither_exists(self):
        self.assertEqual(names.state_dir(self.tmp), self.tmp / ".sanvio")

    def test_the_old_folder_is_never_read(self):
        (self.tmp / ".harness").mkdir()
        self.assertEqual(names.state_dir(self.tmp), self.tmp / ".sanvio")

    def test_the_new_folder_wins_when_both_exist(self):
        (self.tmp / ".harness").mkdir()
        (self.tmp / ".sanvio").mkdir()
        self.assertEqual(names.state_dir(self.tmp), self.tmp / ".sanvio")

    def test_the_home_folders_are_the_new_ones_even_when_the_old_ones_exist(self):
        (self.tmp / ".harness-loop").mkdir()
        (self.tmp / ".harness-evals").mkdir()
        self.assertEqual(names.loop_home(self.tmp), self.tmp / ".sanvio-loop")
        self.assertEqual(names.evals_home(self.tmp, environ={}), self.tmp / ".sanvio-evals")

    def test_the_evals_home_variable_beats_the_folder_and_its_old_name_does_nothing(self):
        self.assertEqual(names.evals_home(self.tmp, environ={"SANVIO_EVALS_HOME": "/new"}), Path("/new"))
        self.assertEqual(names.evals_home(self.tmp, environ={"HARNESS_EVALS_HOME": "/old"}), self.tmp / ".sanvio-evals")


class Moving(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_nothing_to_move_says_nothing(self):
        self.assertIsNone(names.move_old_state(self.tmp))
        (self.tmp / ".sanvio").mkdir()
        self.assertIsNone(names.move_old_state(self.tmp))

    def test_the_old_folder_moves_whole_with_what_is_in_it(self):
        run = self.tmp / ".harness" / "factories" / "run-7.json"
        run.parent.mkdir(parents=True)
        run.write_text("{}", encoding="utf-8")
        said = names.move_old_state(self.tmp)
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
        said = names.move_old_state(self.tmp)
        self.assertIn("moved .harness/ to .sanvio/", said)
        self.assertFalse((self.tmp / ".harness").exists())
        self.assertTrue((self.tmp / ".sanvio" / "factories" / "run-7.json").is_file())
        self.assertEqual((self.tmp / ".sanvio" / "project" / "aaaaaaaa-1111").read_text(encoding="utf-8"), "app\n")

    def test_both_folders_are_left_alone_and_named(self):
        (self.tmp / ".harness").mkdir()
        (self.tmp / ".sanvio").mkdir()
        said = names.move_old_state(self.tmp)
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
            said = names.move_old_state(self.tmp)
        finally:
            os.rename = real
        self.assertIn("couldn't move .harness/", said)
        self.assertIn("nothing reads .harness/ now", said)


class Variables(unittest.TestCase):
    def test_the_new_name_is_read_first(self):
        environ = {"SANVIO_RETRO": "off", "HARNESS_RETRO": "on"}
        self.assertEqual(names.env("RETRO", environ=environ), "off")

    def test_the_old_name_does_nothing(self):
        self.assertEqual(names.env("PULSE_FOLDER", "none", environ={"HARNESS_PULSE_FOLDER": "/p"}), "none")
        self.assertEqual(names.env("PULSE_FOLDER", "none", environ={}), "none")

    def test_either_headless_variable_makes_a_run_headless(self):
        self.assertTrue(names.headless({"SANVIO_HEADLESS": "1"}))
        self.assertTrue(names.headless({"HARNESS_HEADLESS": "1"}))
        self.assertTrue(names.headless({"SANVIO_HEADLESS": "0", "HARNESS_HEADLESS": "1"}))
        self.assertFalse(names.headless({}))

    def test_either_name_switches_the_usage_log_off(self):
        self.assertTrue(names.logging_off({"SANVIO_USAGE_LOG": "off"}))
        self.assertTrue(names.logging_off({"HARNESS_USAGE_LOG": "no"}))
        self.assertFalse(names.logging_off({"HARNESS_USAGE_LOG": "on"}))
        self.assertFalse(names.logging_off({}))

    def test_old_variables_are_named_once_each(self):
        environ = {"HARNESS_RETRO": "on", "HARNESS_PULSE_FOLDER": "/p", "SANVIO_PULSE_FOLDER": "/p",
                   "HARNESS_HEADLESS": "1", "HARNESS_OTHER": "x"}
        self.assertEqual(names.old_variables(environ), ["HARNESS_RETRO"])


class Warning(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.said = []

    def warn(self, environ, session=101):
        return names.warn_old_once(environ, marker_dir=self.dir, session=session, write=self.said.append)

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

    def test_an_explicit_environment_stays_silent(self):
        with mock.patch.dict(os.environ, {"TMPDIR": str(self.dir)}), \
                mock.patch.object(names, "warn_old_once") as warn:
            names.env("RETRO", environ={"HARNESS_RETRO": "on"})
            names.logging_off({"HARNESS_USAGE_LOG": "on"})
            names.evals_home(environ={"HARNESS_EVALS_HOME": "/e"})
        warn.assert_not_called()
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_the_real_environment_is_checked_once_per_process(self):
        with mock.patch.object(names, "_checked", False), mock.patch.object(names, "warn_old_once") as warn:
            names.env("RETRO")
            names.logging_off()
        warn.assert_called_once_with()


class TheModule(unittest.TestCase):
    def test_it_imports_the_standard_library_only(self):
        tree = ast.parse((ROOT / "scripts" / "names.py").read_text(encoding="utf-8"), feature_version=(3, 9))
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                found.add((node.module or "").split(".")[0])
        self.assertLessEqual(found, {"os", "pathlib"})


if __name__ == "__main__":
    unittest.main()
