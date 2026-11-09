"""Run with: python3 -m unittest discover -s tests"""
import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path

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

    def test_old_variables_are_named_once_each(self):
        environ = {"HARNESS_RETRO": "on", "HARNESS_PULSE_FOLDER": "/p", "SANVIO_PULSE_FOLDER": "/p",
                   "HARNESS_HEADLESS": "1", "HARNESS_OTHER": "x"}
        self.assertEqual(names.old_variables(environ), ["HARNESS_RETRO"])


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
