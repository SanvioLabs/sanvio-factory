"""INSTALL.md is the procedure an outside agent session follows to install the factory: it names the
clone, the hooks, the setup check and the private copy, asks before the copy is made, never asks for a
token, and stops short of company/, connectors, mods and the loop. The README points at it."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://github.com/SanvioLabs/sanvio-factory"
RAW = URL + "/blob/main/INSTALL.md"


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def section(text, heading):
    """From the ## heading up to the next ## heading, skipping fenced code."""
    lines, inside, fenced = [], False, False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            if inside:
                break
            inside = line == heading
        if inside:
            lines.append(line)
    return "\n".join(lines)


class Install(unittest.TestCase):
    def setUp(self):
        self.text = read("INSTALL.md")

    def test_it_names_each_step_the_install_runs(self):
        for needed in (URL, "core.hooksPath .githooks", "scripts/check_setup.py", "core.symlinks=true",
                       "--private", "/orientation"):
            self.assertIn(needed, self.text, needed)

    def test_the_clone_is_the_public_repo_into_the_chosen_path(self):
        self.assertIn("git clone " + URL + " <path>", self.text)
        self.assertIn("git clone -c core.symlinks=true " + URL + " <path>", self.text)

    def test_it_never_asks_for_a_token(self):
        self.assertIn("Never ask for a token", self.text)

    def test_gh_login_is_read_from_the_exit_code_alone(self):
        self.assertIn("gh auth status", self.text)
        self.assertIn("Never show or read its output", self.text)

    def test_the_private_copy_waits_for_a_second_yes(self):
        self.assertLess(self.text.index("second yes"), self.text.index("--private"))

    def test_the_remote_moves_in_three_commands_not_one(self):
        for command in ("gh repo create <owner>/<name> --private",
                        "git remote set-url origin https://github.com/<owner>/<name>.git",
                        "git push -u origin main"):
            self.assertIn(command, self.text)
        self.assertNotIn("--source", self.text)

    def test_it_says_what_the_install_doesnt_do(self):
        part = section(self.text, "## What the install doesn't do")
        self.assertTrue(part, "INSTALL.md has no What the install doesn't do section")
        for item in ("write anything in `company/`", "add a connector or an MCP server",
                     "install a mod by hand", "label an issue for the loop or start the loop"):
            self.assertIn(item, part, item)


class Readme(unittest.TestCase):
    def setUp(self):
        self.text = read("README.md")

    def test_a_line_to_paste_names_install_md_above_the_first_picture(self):
        line = ("Install Sanvio Factory by following " + RAW + ". Read it before running anything.")
        self.assertIn(line, self.text)
        self.assertLess(self.text.index(line), self.text.index("!["))

    def test_set_up_links_install_md(self):
        self.assertIn("[`INSTALL.md`](INSTALL.md)", section(self.text, "## Set up"))


class Orientation(unittest.TestCase):
    def test_it_points_at_install_md_rather_than_a_template(self):
        text = read("skills/orientation/SKILL.md")
        self.assertNotIn("Use this template", text)
        self.assertIn("(../../INSTALL.md)", text)


if __name__ == "__main__":
    unittest.main()
