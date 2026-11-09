"""Run with: python3 -m unittest discover -s tests"""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The retired mods' names, built in pieces so this file doesn't name them itself. factory-floor
# replaced both, and keeps their commands as aliases until a later release.
RETIRED = ("loop-" + "pane", "loop-" + "crew")

# Where the old names may stay: the changelog's history, the specs' record of what was planned, and
# factory-floor, whose aliases and comments name the mods they replaced.
ALLOWED_FILES = {"CHANGELOG.md"}
ALLOWED_DIRS = ("docs/specs/", "examples/mods/factory-floor/")


def tracked():
    """Every file git tracks, by its path from the root."""
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, text=True,
                         check=True, timeout=30).stdout
    return [name for name in out.split("\0") if name]


def is_allowed(path):
    return path in ALLOWED_FILES or path.startswith(ALLOWED_DIRS)


def naming_retired(files):
    """Each path in `files`, a map of path to text, outside the allowed ones whose text names a retired mod."""
    return sorted(path for path, text in files.items()
                  if not is_allowed(path) and any(name in text for name in RETIRED))


def read_tracked():
    """Each tracked file's text, by path. A file that's gone, unreadable or not text is left out."""
    files = {}
    for path in tracked():
        try:
            files[path] = (ROOT / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return files


class RetiredModsStayGone(unittest.TestCase):
    """The retired mods were replaced by factory-floor: nothing tracked points at them again."""

    def test_no_tracked_file_names_a_retired_mod(self):
        self.assertEqual(naming_retired(read_tracked()), [])

    def test_the_tracked_files_are_read(self):
        # An empty listing would pass the check above without reading anything.
        files = read_tracked()
        self.assertIn("AGENTS.md", files)
        self.assertIn("examples/mods/factory-floor/hooks/register.tsx", files)

    def test_a_file_naming_a_retired_mod_is_caught_outside_the_allowed_paths(self):
        pane, crew = RETIRED
        files = {
            "README.md": "Open it with /{}.".format(pane),
            "skills/loop-control/SKILL.md": "see examples/mods/{}/".format(crew),
            "HOW-IT-WORKS.md": "Open it with /factory-floor.",
            "CHANGELOG.md": "Removed {} and {}.".format(pane, crew),
            "docs/specs/001-x/TASKS.md": "Retire {}.".format(pane),
            "examples/mods/factory-floor/hooks/register.tsx": "{ name: '" + crew + "' }",
            "examples/mods/factory-floor-two/README.md": "Like /{}.".format(pane),
        }
        self.assertEqual(naming_retired(files), [
            "README.md", "examples/mods/factory-floor-two/README.md", "skills/loop-control/SKILL.md"])


if __name__ == "__main__":
    unittest.main()
