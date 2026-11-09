"""Run with: python3 -m unittest discover -s tests"""
import getpass
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import draw_dashboard  # noqa: E402 (needs scripts/ on the path first)

NEEDS_CLAUDE = "needs Claude Code (claude) on the PATH"
RUN = "run: python3 scripts/draw_dashboard.py"


class Picture(unittest.TestCase):
    """The dashboard README's picture and its text are what the pane draws now, and name no one."""

    @classmethod
    def setUpClass(cls):
        if not shutil.which("claude"):
            raise unittest.SkipTest(NEEDS_CLAUDE)
        cls.svg, cls.text = draw_dashboard.drawn()

    def test_the_svg_is_current(self):
        self.assertTrue(draw_dashboard.SVG.read_text() == self.svg,
                        "docs/factory-dashboard.svg isn't what the pane draws; " + RUN)

    def test_the_readme_text_is_current(self):
        self.assertTrue(draw_dashboard.details(draw_dashboard.README.read_text()) == self.text,
                        "the README's text version isn't what the pane draws; " + RUN)

    def test_the_svg_holds_no_path_or_user(self):
        for leak in (str(ROOT), str(Path.home()), getpass.getuser(), "/Users/", "/home/"):
            self.assertNotIn(leak, self.svg, "docs/factory-dashboard.svg names a path or user: " + leak)


class OwnTest(unittest.TestCase):
    """The test file the command writes for one run: never another run's, and never committed."""

    def test_one_already_there_stops_the_run_and_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            there = Path(tmp) / "draw-picture.test.ts"
            there.write_text("another run's\n")
            with mock.patch.object(draw_dashboard, "OUT_TEST", there), \
                    mock.patch.object(draw_dashboard, "ROOT", Path(tmp)), \
                    mock.patch.object(draw_dashboard.subprocess, "run") as run:
                with self.assertRaises(RuntimeError) as raised:
                    draw_dashboard.pane_rows()
            run.assert_not_called()
            self.assertEqual(there.read_text(), "another run's\n")
            self.assertIn("already there", str(raised.exception))

    def test_git_ignores_it(self):
        if not (ROOT / ".git").exists():
            self.skipTest("not a git checkout")
        path = draw_dashboard.OUT_TEST.relative_to(ROOT)
        found = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "--no-index", str(path)])
        self.assertEqual(found.returncode, 0, "{} isn't in .gitignore".format(path))


if __name__ == "__main__":
    unittest.main()
