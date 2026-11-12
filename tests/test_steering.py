"""Run with: python3 -m unittest discover -s tests"""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = (ROOT / "AGENTS.md").read_text()
IMPORT = re.compile(r"^@(\S+)$", re.M)
EM_DASH = chr(0x2014)  # written as a code point so this file passes its own check


class Steering(unittest.TestCase):
    def test_every_steering_file_is_named_in_agents_md(self):
        files = sorted((ROOT / "steering").glob("*.md"))
        self.assertTrue(files)
        for path in files:
            self.assertIn("steering/" + path.name, AGENTS, path.name)

    def test_every_import_in_agents_md_resolves(self):
        imports = IMPORT.findall(AGENTS)
        self.assertTrue(imports)
        for target in imports:
            self.assertTrue((ROOT / target).is_file(), target)

    def test_kiro_loads_the_same_files_claude_code_imports(self):
        imported = {Path(target).name for target in IMPORT.findall(AGENTS)}
        linked = {p.name for p in (ROOT / ".kiro" / "steering").glob("*.md") if p.name != "project.md"}
        self.assertEqual(imported, linked)
        for name in linked:
            link = ROOT / ".kiro" / "steering" / name
            self.assertEqual(link.resolve(), (ROOT / "steering" / name).resolve(), name)


class Compliance(unittest.TestCase):
    def test_compliance_steering_names_the_baseline(self):
        path = ROOT / "steering" / "compliance.md"
        self.assertTrue(path.is_file(), "no steering/compliance.md")
        self.assertIn("NIST SP 800-53", path.read_text())

    def test_builders_ticket_writers_and_the_security_reviewer_point_at_it(self):
        for name in ("steering/building-and-testing.md", "steering/tickets.md", "agents/security-reviewer.md"):
            self.assertIn("compliance.md", (ROOT / name).read_text(), name)

    def test_compliance_stays_read_when_and_out_of_every_session(self):
        """An @ import would load it in every session, and Kiro's check would then want it linked."""
        imported = {Path(target).name for target in IMPORT.findall(AGENTS)}
        self.assertNotIn("compliance.md", imported)

    def test_a_control_on_a_finding_leaves_the_verdict_where_it_was(self):
        text = (ROOT / "agents" / "security-reviewer.md").read_text()
        self.assertIn("NOT-READY means at least one Critical or High", text)


# What Sanvio Factory ships. Your own files (AGENTS.md, your skills, gates and briefs)
# aren't held to the house style: an agent's em dash shouldn't fail your suite.
SHIPPED = ["steering/*.md", "examples/**/*", "skills/orientation/*", "skills/learn/*",
           "skills/review-pr/*", "skills/review-tests/*", "skills/review-skill/*",
           "skills/whats-new/*", "CHANGELOG.md",
           "agents/reviewer.md", "agents/security-reviewer.md", "agents/ceo.md", "agents/cto.md",
           "agents/cmo.md", "agents/gc.md", "gates/README.md",
           "projects/README.md", "README.md", "HOW-IT-WORKS.md",
           "EXERCISES.md", "STARTER-SKILLS.md", "scripts/*", "tests/*", ".claude/**/*",
           ".githooks/*", ".github/**/*"]


def ignored_by_git(paths):
    """The paths git ignores: not shipped, whatever lands there. Claude Code lays a
    mod's types into examples/mods/*/.claude-plugin/types/ when it loads one."""
    try:
        out = subprocess.run(["git", "check-ignore", "--stdin"], cwd=ROOT, capture_output=True, text=True,
                             input="\n".join(str(p.relative_to(ROOT)) for p in paths)).stdout
    except OSError:
        return set()
    return {ROOT / line for line in out.splitlines() if line}


class HouseStyle(unittest.TestCase):
    def test_no_em_dashes_in_what_sanvio_factory_ships(self):
        found = []
        paths = sorted({p for pattern in SHIPPED for p in ROOT.glob(pattern)})
        self.assertTrue(paths)
        ignored = ignored_by_git(paths)
        for path in paths:
            if not path.is_file() or path.is_symlink() or path in ignored:
                continue
            try:
                text = path.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if EM_DASH in line:
                    found.append("{}:{}".format(path.relative_to(ROOT), number))
        self.assertEqual(found, [], "em dashes: use a colon, commas, parentheses or two sentences")


class Agents(unittest.TestCase):
    def test_every_agent_has_a_read_only_wrapper(self):
        """Every agents/*.md runs in Claude Code from a .claude/agents/ file of the same name that can't
        change anything: no Edit or Write, and Bash only for security-reviewer, whose shell guard.py
        holds to a list. Every .md in agents/ counts as an agent, so a README there would need a wrapper."""
        files = sorted((ROOT / "agents").glob("*.md"))
        self.assertTrue(files)
        for path in files:
            wrapper = ROOT / ".claude" / "agents" / path.name
            self.assertTrue(wrapper.is_file(), "no wrapper for agents/" + path.name)
            # Without a tools line a subagent gets every tool.
            line = re.search(r"^tools:(.*)$", wrapper.read_text(), re.M)
            self.assertTrue(line, "no tools line in " + str(wrapper.relative_to(ROOT)))
            tools = {tool.strip() for tool in line.group(1).split(",")}
            banned = {"Edit", "Write"} | ({"Bash"} if path.stem != "security-reviewer" else set())
            self.assertFalse(tools & banned, "{} can {}".format(wrapper.relative_to(ROOT), sorted(tools & banned)))


def section(text, start, end):
    """The text from the line starting with start up to the next line starting with end."""
    match = re.search(r"^{}.*?(?=^{}|\Z)".format(re.escape(start), re.escape(end)), text, re.M | re.S)
    return match.group(0) if match else ""


class WhereToRunIt(unittest.TestCase):
    def test_readme_says_what_works_in_each_app(self):
        text = section((ROOT / "README.md").read_text(), "### Where to run it", "## ")
        self.assertTrue(text, "README.md's Set up has no ### Where to run it part")
        rows = [line for line in text.splitlines() if line.startswith("|")]
        body = [line for line in rows[1:] if not re.match(r"^\|[\s|:-]+\|$", line)]
        firsts = [row.split("|")[1].strip() for row in body]
        self.assertEqual(firsts, ["Terminal", "VS Code extension", "Claude Desktop, Code tab", "Claude Desktop, chat"])


class WhereThingsLive(unittest.TestCase):
    def test_readme_names_the_three_places(self):
        text = section((ROOT / "README.md").read_text(), "## Where things live", "## ")
        self.assertTrue(text, "README.md has no ## Where things live section")
        # The section's first table; a later one (the forms company/ takes) is its own.
        rows = []
        for line in text.splitlines():
            if line.startswith("|"):
                rows.append(line)
            elif rows:
                break
        body = [line for line in rows[1:] if not re.match(r"^\|[\s|:-]+\|$", line)]
        self.assertEqual(len(body), 3, "the table should have one row per place things live")
        self.assertIn("company/DATA.md", text)

    def test_orientation_asks_where_the_company_record_lives(self):
        text = section((ROOT / "skills" / "orientation" / "SKILL.md").read_text(), "### 5.", "### 6.")
        self.assertTrue(text, "orientation has no step 5")
        for choice in ("**Here.**", "**In a company repo.**", "git clone <url> company", "**In a wiki.**"):
            self.assertIn(choice, text)

    def test_orientation_offers_to_start_from_urls(self):
        text = section((ROOT / "skills" / "orientation" / "SKILL.md").read_text(), "### 5.", "### 6.")
        self.assertIn("up to three", text)
        self.assertIn("URL", text)

    def test_orientation_names_the_four_draftable_sections(self):
        text = section((ROOT / "skills" / "orientation" / "SKILL.md").read_text(), "### 5.", "### 6.")
        for heading in ("**What we do**", "**Who it's for**", "**How we sound**", "**Words that mean something here**"):
            self.assertIn(heading, text)

    def test_orientation_never_drafts_wont_do_or_who_decides(self):
        text = section((ROOT / "skills" / "orientation" / "SKILL.md").read_text(), "### 5.", "### 6.")
        lines = [line for line in text.splitlines() if "never drafted" in line]
        self.assertTrue(lines, "step 5 never says which sections are never drafted")
        self.assertTrue(any("What we won't do" in line and "Who decides" in line for line in lines),
                        "the never-drafted line should name What we won't do and Who decides")

    def test_orientation_treats_page_content_as_material(self):
        text = section((ROOT / "skills" / "orientation" / "SKILL.md").read_text(), "### 5.", "### 6.")
        self.assertIn("never as instructions", text)

    TEMPLATE = ROOT / "skills" / "orientation" / "COMPANY.example.md"
    EARLIER = ["## What we do", "## Who it's for", "## How we sound", "## What we won't do",
               "## Who decides", "## Words that mean something here"]

    def test_the_template_has_an_onboarding_table_with_one_placeholder_row(self):
        text = section(self.TEMPLATE.read_text(), "## Onboarding", "## ")
        self.assertTrue(text, "COMPANY.example.md has no ## Onboarding section")
        rows = [line for line in text.splitlines() if line.startswith("|")]
        self.assertEqual(rows[:1], ["| Person | Date | What they went through |"])
        body = [line for line in rows[1:] if not re.match(r"^\|[\s|:-]+\|$", line)]
        self.assertEqual(len(body), 1, "the template should hold exactly one placeholder row")
        cells = [cell.strip() for cell in body[0].strip("|").split("|")]
        self.assertEqual(len(cells), 3)
        for cell in cells:
            self.assertRegex(cell, r"^_[^_]+_$", "every placeholder cell is wrapped in _..._")

    def test_the_earlier_template_sections_stay_in_order_before_onboarding(self):
        headings = [line for line in self.TEMPLATE.read_text().splitlines() if line.startswith("## ")]
        self.assertEqual(headings, self.EARLIER + ["## Onboarding"])

    def test_data_and_tools_says_where_onboarding_is_recorded(self):
        text = (ROOT / "steering" / "data-and-tools.md").read_text()
        self.assertIn("## Onboarding", text)
        self.assertIn("company/COMPANY.md", text)


class Incidents(unittest.TestCase):
    PATH = ROOT / "steering" / "incidents.md"
    HEADINGS = ["## Stop the agent and the loop", "## Who to tell, and how soon",
                "## Rotate secrets and record it", "## Where the records are", "## What to keep"]

    def test_the_five_headings_appear_in_order(self):
        self.assertTrue(self.PATH.is_file(), "no steering/incidents.md")
        found = [line for line in self.PATH.read_text().splitlines() if line.startswith("## ")]
        self.assertEqual(found, self.HEADINGS)

    def test_it_stops_the_loop_and_reads_the_contact_from_the_company_record(self):
        text = self.PATH.read_text()
        self.assertIn("python3 scripts/loop.py stop", text)
        self.assertIn("company/COMPANY.md", text)

    def test_it_names_no_default_contact(self):
        self.assertIsNone(re.search(r"\S+@\S+\.\w+", self.PATH.read_text()),
                          "incidents.md hard-codes an email address; the contact comes from company/COMPANY.md")

    def test_only_the_say_it_the_same_day_rule_links_it(self):
        text = (ROOT / "steering" / "data-and-tools.md").read_text()
        self.assertIn("incidents.md", section(text, "- **Say it the same day.**", "- **"))
        rules = section(text, "## Standing rules", "## ")
        others = [bullet for bullet in re.split(r"^(?=- \*\*)", rules, flags=re.M)
                  if bullet.startswith("- **") and not bullet.startswith("- **Say it the same day.**")]
        self.assertTrue(others, "Standing rules has no other bullets to check")
        for bullet in others:
            self.assertNotIn("incidents.md", bullet, bullet.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
