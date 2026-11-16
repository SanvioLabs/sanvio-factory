"""The README's "On this page" line links every ## section, in order, and nothing else, and
HOW-IT-WORKS.md's Keeping the loop to its own work says what it must, with the README pointing at it."""
import re
import unittest
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"
HOW = Path(__file__).resolve().parent.parent / "HOW-IT-WORKS.md"
MARK = "**On this page:** "
KEEPING = "### Keeping the loop to its own work"
LINK = "HOW-IT-WORKS.md#keeping-the-loop-to-its-own-work"


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


def part(text, heading):
    """From the line that is heading up to the next ## or ### heading, skipping fenced code."""
    lines, inside, fenced = [], False, False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        heading_line = not fenced and (line.startswith("## ") or line.startswith("### "))
        if inside and heading_line:
            break
        if line == heading:
            inside = True
        if inside:
            lines.append(line)
    return "\n".join(lines)


def table_rows(text):
    """Each table body row's first cell, the header and separator rows left out."""
    rows = [line for line in text.splitlines() if line.startswith("|")]
    body = [line for line in rows[1:] if not re.match(r"^\|[\s|:-]+\|$", line)]
    return [row.split("|")[1].strip() for row in body]


class KeepingTheLoopToItsOwnWork(unittest.TestCase):
    def setUp(self):
        self.how = HOW.read_text(encoding="utf-8")
        self.section = part(self.how, KEEPING)
        self.assertTrue(self.section, "HOW-IT-WORKS.md has no " + KEEPING)

    def test_it_comes_straight_after_off_your_laptop(self):
        after = self.how.split("\n### Off your laptop\n", 1)[1]
        headings = [line for line in after.splitlines() if line.startswith(("## ", "### "))]
        self.assertEqual(headings[0], KEEPING)

    def test_its_parts_are_the_three_boundaries_in_order(self):
        parts = [line[5:] for line in self.section.splitlines() if line.startswith("#### ")]
        self.assertEqual(parts, ["On your own machine", "In the dev container", "Off your machine"])

    def test_it_names_the_settings_the_token_and_the_container(self):
        text = " ".join(self.section.split())
        for needed in ("network_allow", "max_issue_tokens", "sandbox_commands", "fine-grained",
                       "Contents read and write", "Pull requests read and write", "Issues read and write",
                       "Commit statuses read", "Checks read", "Metadata read",
                       "Contents write is needed only where the loop pushes branches or `auto_merge` is on",
                       ".devcontainer/README.md", "https://code.claude.com/docs/en/sandboxing",
                       "The guard is a backstop rather than a sandbox.",
                       "None of the three stops an agent from reading what's inside its own boundary."):
            self.assertIn(needed, text)

    def test_it_points_at_the_vm_and_actions_rows_rather_than_repeating_them(self):
        self.assertEqual([line for line in self.section.splitlines() if line.startswith("|")], [])

    def test_off_your_laptop_keeps_its_three_rows(self):
        self.assertEqual(table_rows(part(self.how, "### Off your laptop")),
                         ["Your own machine, in tmux", "An always-on machine (a VM) beside the repo", "GitHub Actions"])


class ReadmePointsAtIt(unittest.TestCase):
    def test_the_anchor_matches_the_heading(self):
        self.assertEqual(LINK.split("#")[1], slug(KEEPING[4:]))

    def test_set_up_links_it_before_where_to_run_it(self):
        text = README.read_text(encoding="utf-8")
        start, end = text.index("\n## Set up\n"), text.index("\n### Where to run it\n")
        self.assertIn(LINK, text[start:end])
        self.assertNotIn(LINK, part(text, "### Where to run it"))


if __name__ == "__main__":
    unittest.main()
