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

    STEERING = ROOT / "steering" / "compliance.md"
    # Phrases, not single words, so an unrelated "merge" or "model" elsewhere in the text can't stand in for a kind.
    AI_PHRASES = ("what an agent does unattended", "outside text reach a prompt", "who merges or decides",
                  "changes the model")
    HEADER = "| Kind of change | Families to keep in mind | The question to answer before calling it done |"
    # Each kind's name, the part of its first cell before any colon, so rewording an example doesn't fail this.
    KINDS = [
        "Stores or moves personal data",
        "Adds or changes access",
        "Adds or changes logging",
        "Adds a dependency or outside service",
        "Changes deployment or infrastructure",
        "Widens what an agent does unattended",
        "Lets text from outside reach a prompt",
        "Changes who merges, approves or decides",
        "Changes the model, the provider or an agent's instructions",
    ]

    @staticmethod
    def bullet(text, start):
        """The list item whose first line starts with start (after its indent), with its indented continuation lines."""
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.lstrip().startswith(start):
                indent = len(line) - len(line.lstrip())
                item = [line]
                for follow in lines[i + 1:]:
                    if not follow.strip() or len(follow) - len(follow.lstrip()) <= indent:
                        break
                    item.append(follow)
                return "\n".join(item)
        return ""

    def test_the_baseline_names_the_ai_companions(self):
        text = " ".join(section(self.STEERING.read_text(), "## The baseline", "## ").split())
        for name in ("NIST AI RMF 1.0", "ISO/IEC 42001:2023", "OWASP Top 10 for LLM Applications"):
            self.assertIn(name, text)

    def test_each_read_when_names_the_ai_kinds(self):
        agents_rows = [line for line in AGENTS.splitlines() if line.startswith("| [`steering/compliance.md`]")]
        self.assertEqual(len(agents_rows), 1, "AGENTS.md should have one steering/compliance.md row")
        texts = {
            "steering/compliance.md": paragraph(self.STEERING.read_text(), "Read this when"),
            "AGENTS.md": agents_rows[0],
            "steering/tickets.md": paragraph((ROOT / "steering" / "tickets.md").read_text(),
                                             "**A ticket that touches personal data"),
            "steering/building-and-testing.md": self.bullet((ROOT / "steering" / "building-and-testing.md").read_text(),
                                                            "- **Know which kind of change it is.**"),
        }
        for name, text in texts.items():
            self.assertTrue(text, "{}: the text that lists the kinds wasn't found".format(name))
            flat = " ".join(text.split())
            for phrase in self.AI_PHRASES:
                self.assertIn(phrase, flat, "{} doesn't name the kind with '{}'".format(name, phrase))

    def test_the_table_keeps_the_old_kinds_then_adds_the_ai_ones(self):
        text = section(self.STEERING.read_text(), "## By kind of change", "## ")
        rows = [line for line in text.splitlines() if line.startswith("|")]
        self.assertEqual(rows[:1], [self.HEADER])
        body = [line for line in rows[1:] if not re.match(r"^\|[\s|:-]+\|$", line)]
        self.assertEqual([row.split("|")[1].split(":")[0].strip() for row in body], self.KINDS)

    def test_it_still_says_what_it_is_not(self):
        text = section(self.STEERING.read_text(), "## What this is not", "## ")
        self.assertIn("not a formal SP 800-53A assessment", " ".join(text.split()))

    def test_a_finding_names_the_owasp_risk_beside_the_control(self):
        text = self.bullet((ROOT / "agents" / "security-reviewer.md").read_text(), "- **Control:**")
        self.assertTrue(text, "security-reviewer.md has no **Control:** bullet")
        self.assertIn("SP 800-53", text)
        self.assertIn("OWASP", text)


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
        self.assertEqual(firsts, ["Terminal", "VS Code extension", "Claude Desktop, Code tab", "Claude Desktop, chat",
                                  "Claude mobile app, following a session"])


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


class OnByDefault(unittest.TestCase):
    """Every plugin .claude/settings.json switches on has a row saying why (NIST SP 800-53 CM-7)."""

    def test_every_enabled_plugin_has_a_row(self):
        import json
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
        on = [name.split("@")[0] for name, enabled in (settings.get("enabledPlugins") or {}).items() if enabled]
        text = (ROOT / "steering" / "data-and-tools.md").read_text()
        self.assertIn("## On by default", text)
        section = text.split("## On by default", 1)[1].split("\n## ", 1)[0]
        rows = {line.split("|")[1].strip().strip("`") for line in section.splitlines() if line.startswith("| `")}
        self.assertTrue(on)
        for name in on:
            self.assertIn(name, rows, "{} is on by default with no row in steering/data-and-tools.md".format(name))


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


def front_matter(text):
    """The lines between a file's opening --- and the next ---."""
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return match.group(1).splitlines() if match else []


def paragraph(text, start):
    """The blank-line-separated paragraph that begins with start."""
    return next((p for p in re.split(r"\n\s*\n", text) if p.startswith(start)), "")


class Concern(unittest.TestCase):
    TEMPLATES = ROOT / ".github" / "ISSUE_TEMPLATE"
    TEMPLATE = TEMPLATES / "concern.md"
    INCIDENTS = ROOT / "steering" / "incidents.md"
    TICKETS = ROOT / "steering" / "tickets.md"
    COMPANY = ROOT / "skills" / "orientation" / "COMPANY.example.md"
    TYPES = ("bug", "enhancement", "documentation", "chore")

    def labels(self, path):
        lines = [line for line in front_matter(path.read_text()) if line.startswith("labels:")]
        self.assertEqual(len(lines), 1, "{} has no single labels: line".format(path.name))
        return lines[0][len("labels:"):].strip()

    def test_the_template_is_named_and_labelled_concern(self):
        self.assertTrue(self.TEMPLATE.is_file(), "no .github/ISSUE_TEMPLATE/concern.md")
        lines = front_matter(self.TEMPLATE.read_text())
        self.assertIn("name: Raise a concern", lines)
        self.assertIn("labels: concern", lines)

    def test_the_template_has_its_three_sections_in_order(self):
        headings = [line for line in self.TEMPLATE.read_text().splitlines() if line.startswith("## ")]
        self.assertEqual(headings, ["## What happened", "## Where", "## What harm you think it does"])

    def test_the_template_sends_vulnerabilities_elsewhere_and_keeps_secrets_and_data_out(self):
        text = self.TEMPLATE.read_text()
        for phrase in (".github/SECURITY.md", "credential", "personal data", "documents"):
            self.assertIn(phrase, text)

    def test_the_template_carries_no_type_or_loop_label(self):
        labels = {label.strip() for label in self.labels(self.TEMPLATE).split(",")}
        for name in ("loop-ready",) + self.TYPES:
            self.assertNotIn(name, labels)

    def test_the_task_template_still_has_no_label(self):
        self.assertEqual(self.labels(self.TEMPLATES / "loop-task.md"), '""')

    def test_incidents_routes_a_concern_to_the_ai_risk_owner(self):
        text = section(self.INCIDENTS.read_text(), "## Who to tell, and how soon", "## ")
        for phrase in ("concern", "AI risk owner", "Who decides", "incident"):
            self.assertIn(phrase, text)

    def test_the_incident_contact_still_comes_from_the_incidents_section(self):
        text = section(self.INCIDENTS.read_text(), "## Who to tell, and how soon", "## ")
        self.assertIn("from the `## Incidents`", text)

    def test_tickets_gives_a_concern_no_type_label(self):
        self.assertIn("concern", paragraph(self.TICKETS.read_text(), "**One type label.**"))

    def test_every_other_issue_still_takes_exactly_one_type(self):
        text = paragraph(self.TICKETS.read_text(), "**One type label.**")
        self.assertIn("exactly one of", text)
        for name in self.TYPES:
            self.assertIn("`{}`".format(name), text)

    def test_the_company_template_asks_who_owns_ai_risk(self):
        text = section(self.COMPANY.read_text(), "## Who decides", "## ")
        self.assertIn("AI risk", text)
        self.assertIn("concern", text)


class Decisions(unittest.TestCase):
    """steering/decisions.md points at the rule for each step a person decides; it never restates one."""
    PATH = ROOT / "steering" / "decisions.md"
    HEADER = "| Decision | Who decides | Where the rule lives |"
    LINK = re.compile(r"\]\(([^)]+)\)")
    # (Decision, Who decides, the files its third cell links to, from the repo root)
    ROWS = [
        ("Sending, emailing or publishing anything", "A person, who sends it themselves",
         {"AGENTS.md"}),
        ("A connector call that sends, edits, deletes or shares", "The person in the session, a yes to that one call",
         {"AGENTS.md"}),
        ("Merging a pull request", "A person, unless the factory's owner has turned on `auto_merge`",
         {"AGENTS.md", "HOW-IT-WORKS.md"}),
        ("Turning on `auto_merge`", "The factory's owner, never the agent",
         {"AGENTS.md"}),
        ("A price, a contract, a send to a customer",
         "The person named under `## Who decides` in the company record",
         {"skills/orientation/COMPANY.example.md"}),
        ("Using a data source marked `unconfirmed`", "A person, in this session",
         {"skills/orientation/SKILL.md"}),
        ("Editing a gate to make work pass",
         "Nobody: it isn't done. Changing a gate is a person's deliberate change",
         {"AGENTS.md", "steering/gates.md"}),
        ("Writing a new rule from a lesson", "The person, a yes to the rule as shown",
         {"skills/learn/SKILL.md"}),
        ("Turning off the usage log",
         "The person running the session, unless an administrator's managed setting keeps it on",
         {"steering/data-and-tools.md"}),
        ("Turning off the loop's command sandbox, or letting a path through it with `sandbox_allow`",
         "The factory's owner, in the factory's `loop.json`",
         {"HOW-IT-WORKS.md"}),
        ("Adding an AI tool or MCP server",
         "Whoever agrees it with the customer, before any customer information reaches it",
         {"steering/data-and-tools.md"}),
        ("Deploying to production", "A person, a yes to that one deploy",
         {"steering/deploying.md"}),
        ("Deleting or overwriting data, test data included", "A person, asked first",
         {"steering/deploying.md"}),
    ]

    def rows(self):
        return [line for line in self.PATH.read_text().splitlines() if line.startswith("|")]

    def cells(self):
        """Each body row's cells, keyed by its Decision cell."""
        body = [line for line in self.rows()[1:] if not re.match(r"^\|[\s|:-]+\|$", line)]
        found = {}
        for line in body:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            found[cells[0]] = cells
        return found

    def target(self, link):
        return (ROOT / "steering" / link).resolve().relative_to(ROOT.resolve()).as_posix()

    def test_header_row(self):
        self.assertTrue(self.PATH.is_file(), "no steering/decisions.md")
        self.assertEqual(self.rows()[:1], [self.HEADER])

    def test_each_decision_has_its_row(self):
        found = self.cells()
        for decision, who, files in self.ROWS:
            self.assertIn(decision, found, "no row for: " + decision)
            cells = found[decision]
            self.assertEqual(len(cells), 3, decision)
            self.assertEqual(cells[1], who, decision)
            self.assertEqual({self.target(link) for link in self.LINK.findall(cells[2])}, files, decision)

    def test_every_link_resolves(self):
        links = self.LINK.findall(self.PATH.read_text())
        self.assertTrue(links)
        for link in links:
            path = link.split("#", 1)[0]
            self.assertTrue((ROOT / "steering" / path).is_file(), link)

    def test_linked_file_wins(self):
        self.assertIn("the linked file wins", self.PATH.read_text())

    def test_decisions_is_read_when_not_imported(self):
        """An @ import would load it in every session, and Kiro's check would then want it linked."""
        imported = {Path(target).name for target in IMPORT.findall(AGENTS)}
        self.assertNotIn("decisions.md", imported)

    def test_existing_rules_unchanged(self):
        text = " ".join(AGENTS.split())
        self.assertIn("Never send, email or publish anything.", text)
        self.assertIn("never edit a gate to make work pass", text)

    def test_rules_line_points_at_it(self):
        rules = section(AGENTS, "## Rules", "## ")
        self.assertIn("steering/decisions.md", rules)
        self.assertIn("who decides", rules)


if __name__ == "__main__":
    unittest.main()
