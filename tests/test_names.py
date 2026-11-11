"""Run with: python3 -m unittest discover -s tests"""
import ast
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import names  # noqa: E402 (needs scripts/ on the path first)
import old_names  # noqa: E402 (same reason)


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


class Checking(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.said = []

    def warn(self, environ, session=101, day="20261109"):
        return names.warn_old_once(environ, marker_dir=self.dir, session=session, write=self.said.append, day=day)

    def test_an_explicit_environment_stays_silent(self):
        with mock.patch.dict(os.environ, {"TMPDIR": str(self.dir)}), \
                mock.patch.object(old_names, "warn_old_once") as warn:
            names.env("RETRO", environ={"HARNESS_RETRO": "on"})
            names.logging_off({"HARNESS_USAGE_LOG": "on"})
            names.evals_home(environ={"HARNESS_EVALS_HOME": "/e"})
        warn.assert_not_called()
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_the_real_environment_is_checked_once_per_process(self):
        with mock.patch.object(names, "_checked", False), mock.patch.object(old_names, "warn_old_once") as warn:
            names.env("RETRO")
            names.logging_off()
        warn.assert_called_once_with()

    def test_a_hook_reads_without_checking(self):
        with mock.patch.object(names, "_checked", False), mock.patch.object(old_names, "in_a_hook", return_value=True), \
                mock.patch.object(old_names, "warn_old_once") as warn:
            names.env("RETRO")
            names.logging_off()
        warn.assert_not_called()

    def test_a_copy_without_the_old_names_reads_the_new_ones_and_says_nothing(self):
        alone = self.dir / "scripts"
        alone.mkdir()
        (alone / "names.py").write_text((ROOT / "scripts" / "names.py").read_text(encoding="utf-8"), encoding="utf-8")
        environ = {key: value for key, value in os.environ.items() if not key.startswith(("SANVIO_", "HARNESS_"))}
        environ.update(HARNESS_RETRO="on", HARNESS_HEADLESS="1", SANVIO_PULSE_FOLDER="/p", TMPDIR=str(self.dir))
        result = subprocess.run([sys.executable, "-c", "import names; print(names.env('PULSE_FOLDER'), names.env('RETRO', 'none'), names.headless())"],
                                cwd=str(alone), capture_output=True, text=True, env=environ, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ["/p", "none", "True"])
        self.assertEqual(result.stderr, "")


class TheModule(unittest.TestCase):
    def test_it_imports_the_standard_library_only(self):
        tree = ast.parse((ROOT / "scripts" / "names.py").read_text(encoding="utf-8"), feature_version=(3, 9))
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                found.add((node.module or "").split(".")[0])
        self.assertLessEqual(found, {"os", "pathlib", "old_names"}, "the standard library, and old_names beside it")

    def test_its_docstring_names_no_other_files_job(self):
        said = ast.get_docstring(ast.parse((ROOT / "scripts" / "names.py").read_text(encoding="utf-8")))
        for other in (".claude/", "hooks", "check_setup", "session_start", "token_report", "dashboard", "eval_factory"):
            with self.subTest(other=other):
                self.assertNotIn(other, said)

    def test_the_stricter_prefix_is_the_old_one(self):
        self.assertEqual(names._STRICTER, old_names.OLD_PREFIX)


if __name__ == "__main__":
    unittest.main()
