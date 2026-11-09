"""Run with: python3 -m unittest discover -s tests"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "examples" / "mods" / "factory-floor"
TYPES = MOD / "types" / "index.d.ts"

# The reading code the List and the Crew share, which hooks/logic.ts holds the one copy of.
SHARED = ["loopDir", "parseStatus", "loopLabel", "workingCount", "loopButtonLabel", "loopOptions",
          "projectName", "focusFile", "focusName"]


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


if __name__ == "__main__":
    unittest.main()
