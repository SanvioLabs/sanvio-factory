"""The README's "On this page" line links every ## section, in order, and nothing else."""
import re
import unittest
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"
MARK = "**On this page:** "


def slug(heading):
    """GitHub's anchor for a heading: lower case, punctuation but - dropped, spaces as -."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def sections(text):
    """Each ## heading's anchor, in order, skipping fenced code."""
    found, fenced = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            found.append(slug(line[3:]))
    return found


class OnThisPage(unittest.TestCase):
    def test_slug_matches_github_for_the_awkward_headings(self):
        self.assertEqual(slug("Gates: done is a script's call"), "gates-done-is-a-scripts-call")
        self.assertEqual(slug("The main loop, and four inside it"), "the-main-loop-and-four-inside-it")

    def test_it_links_every_section_in_order(self):
        text = README.read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if line.startswith(MARK)]
        self.assertEqual(len(lines), 1, "README.md needs exactly one line starting " + MARK.strip())
        links = re.findall(r"\]\(#([^)]+)\)", lines[0])
        self.assertEqual(links, sections(text),
                         "README.md's On this page line doesn't match its ## headings: add, remove or reorder its links")

    def test_it_sits_above_the_first_section(self):
        text = README.read_text(encoding="utf-8")
        self.assertLess(text.index(MARK), text.index("\n## "))


if __name__ == "__main__":
    unittest.main()
