"""Run with: python3 -m unittest discover -s tests"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "docs" / "upgrading-to-sanvio-factory.md"
SECTION = "### What else the rename's files carry"


def table_rows():
    """The cells of each row in the guide's table of what else the rename's files carry."""
    lines = GUIDE.read_text().splitlines()
    start = lines.index(SECTION)
    rows = []
    for line in lines[start + 1:]:
        if line.startswith("#"):
            break
        if line.startswith("|"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    # Drop the header and the |---| line by what they are, so a lost separator can't take a real row with it.
    return [row for row in rows if row != ["File", "Also brings", "Entry"] and not all(set(cell) <= set("-:") for cell in row)]


class WhatElseTheRenamesFilesCarry(unittest.TestCase):
    def test_the_section_has_a_table_with_rows(self):
        self.assertIn(SECTION, GUIDE.read_text().splitlines())
        rows = table_rows()
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(len(row), 3, row)

    def test_every_entry_named_is_a_changelog_heading(self):
        headings = set(re.findall(r"^## (.+)$", (ROOT / "CHANGELOG.md").read_text(), re.M))
        for _, _, entry in table_rows():
            names = re.findall(r"`([^`]+)`", entry)
            self.assertTrue(names, entry)
            for name in names:
                self.assertIn(name, headings)

    def test_every_file_linked_exists(self):
        for row in table_rows():
            for target in re.findall(r"\]\(([^)]+)\)", " ".join(row)):
                self.assertTrue((GUIDE.parent / target).exists(), target)


if __name__ == "__main__":
    unittest.main()
