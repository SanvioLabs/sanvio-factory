"""Run with: python3 -m unittest discover -s tests"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "examples" / "mods" / "factory-floor"
TYPES = MOD / "types" / "index.d.ts"

# The reading code the List and the Crew share, which hooks/logic.ts holds the one copy of.
SHARED = ["loopDir", "parseStatus", "loopLabel", "loopValue", "workingCount", "loopButtonLabel", "loopOptions",
          "projectName", "focusFile", "focusName", "ALL", "pickerOrder", "loopTag", "allActive"]


def sources():
    """The mod's own code: every .ts and .tsx that isn't a test, outside the types Claude Code lays."""
    out = []
    for path in sorted(MOD.rglob("*")):
        if path.suffix not in (".ts", ".tsx") or ".test." in path.name:
            continue
        if ".claude-plugin" in path.relative_to(MOD).parts:
            continue
        out.append(path)
    return out


class OneCopy(unittest.TestCase):
    """A mod test can't read files, so this checks the source that factory-floor's views read loops through one copy."""

    def test_the_sources_are_found(self):
        names = {p.name for p in sources()}
        self.assertTrue({"logic.ts", "crew-logic.ts", "crew.tsx", "register.tsx"} <= names, sorted(names))

    def test_each_shared_name_is_defined_once(self):
        text = "\n".join(p.read_text() for p in sources())
        for name in SHARED:
            pattern = r"function {0}\b|const {0} =".format(re.escape(name))
            self.assertEqual(len(re.findall(pattern, text)), 1, name)

    def test_each_view_type_is_declared_once_and_the_crew_copies_are_gone(self):
        text = TYPES.read_text()
        for name in ("Row", "Status", "Seen"):
            self.assertEqual(len(re.findall(r"type {}\b".format(name), text)), 1, name)
        self.assertEqual(re.findall(r"type Crew(?:Row|Status|Seen|Loop)\b", text), [])


def ignored(path):
    """Whether git ignores `path`, relative to the root. check-ignore exits 0 for an ignored path, 1 for one it isn't."""
    ran = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", path], capture_output=True)
    if ran.returncode not in (0, 1):
        raise AssertionError(ran.stderr.decode() or f"git check-ignore exited {ran.returncode}")
    return ran.returncode == 0


@unittest.skipUnless(shutil.which("git") and (ROOT / ".git").exists(), "needs git and a clone")
class OtherMachines(unittest.TestCase):
    """The list of other machines names hosts and folders, so it stays on this machine; the example ships."""

    def test_the_machines_file_is_ignored(self):
        self.assertTrue(ignored(".sanvio/factory-floor/machines.json"))

    def test_the_example_is_not_ignored(self):
        self.assertTrue((MOD / "machines.example.json").exists())
        self.assertFalse(ignored("examples/mods/factory-floor/machines.example.json"))


README = MOD / "README.md"


def paragraphs():
    """The README's paragraphs, split on blank lines, each with its whitespace collapsed to single spaces."""
    return [" ".join(block.split()) for block in re.split(r"\n\s*\n", README.read_text()) if block.strip()]


def paragraph(test, phrase, start=False):
    """The one paragraph that holds `phrase`, or starts with it when `start` is set."""
    found = [p for p in paragraphs() if (p.startswith(phrase) if start else phrase in p)]
    test.assertEqual(len(found), 1, phrase)
    return found[0]


class Readme(unittest.TestCase):
    """The README says how fast a job's dot pulses on each surface, and what a pane behind another pane does."""

    DOT = "The dot beside a job the loop is on pulses"
    SCREEN = "Only the view on screen reads the loop's files"

    def test_the_dot_names_both_pulse_rates(self):
        text = paragraph(self, self.DOT)
        self.assertIn("about once a second in the terminal", text)
        self.assertIn("about once every two seconds in VS Code and Claude Desktop", text)

    def test_a_hidden_pane_does_not_redraw(self):
        text = paragraph(self, self.SCREEN, start=True)
        self.assertIn("behind another pane, neither view redraws", text)
        self.assertIn("the reads go on", text)
        self.assertIn("walks then", text)

    def test_the_dot_paragraph_keeps_the_rest(self):
        self.assertIn("If the loop dies mid-step", paragraph(self, self.DOT))

    def test_the_screen_paragraph_keeps_the_rest(self):
        self.assertIn("the list's two-second read", paragraph(self, self.SCREEN, start=True))

    def test_the_rate_is_stated_once(self):
        rated = [p for p in paragraphs() if re.search(r"once (?:a second|every)", p)]
        self.assertEqual(len(rated), 1, rated)
        self.assertIn(self.DOT, rated[0])


if __name__ == "__main__":
    unittest.main()
