"""Run with: python3 -m unittest discover -s tests"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))
import send_usage  # noqa: E402 (needs scripts/ on the path first)
import usage_log  # noqa: E402 (same reason)

PERSON = {"SANVIO_HEADLESS": "", "HARNESS_HEADLESS": "", "SANVIO_USAGE_LOG": "", "HARNESS_USAGE_LOG": ""}


class OptInAndOut(unittest.TestCase):
    def run_main(self, root, *args, **env):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, dict(PERSON, **env)), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = send_usage.main(list(args), root=root)
        return code, out.getvalue(), err.getvalue()

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


if __name__ == "__main__":
    unittest.main()
