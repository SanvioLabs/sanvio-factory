"""Run with: python3 -m unittest discover -s tests"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2}): (\S.*)$", re.M)


def entries(text):
    """(date, name, body) for each entry, in file order."""
    found = list(HEADING.finditer(text))
    out = []
    for i, match in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(text)
        out.append((match.group(1), match.group(2), text[match.end():end]))
    return out


def problems(text):
    """Every reason skills/whats-new couldn't read this log. Empty means it can."""
    found = []
    items = entries(text)
    if not items:
        found.append("no entries: each starts with '## YYYY-MM-DD: Name'")
    names = [name for _, name, _ in items]
    for name in sorted({n for n in names if names.count(n) > 1}):
        found.append("two entries named '{}': headings are how copies are compared".format(name))
    for (date, name, _), (next_date, next_name, _) in zip(items, items[1:]):
        if next_date > date:
            found.append("'{}' is above the newer '{}': newest first".format(name, next_name))
    for _, name, body in items:
        if "**Do:**" not in body:
            found.append("'{}' has no **Do:** line".format(name))
    return found


GOOD = """# What's new

## 2026-10-08: Second

Adds a thing.

**Do:** nothing.

## 2026-10-08: First

**Do:** run the setup check.
"""


class Changelog(unittest.TestCase):
    def test_the_log_sanvio_factory_ships_is_readable(self):
        self.assertEqual(problems((ROOT / "CHANGELOG.md").read_text()), [])

    def test_a_good_log_passes(self):
        self.assertEqual(problems(GOOD), [])

    def test_an_entry_without_a_do_line_fails(self):
        self.assertIn("'First' has no **Do:** line", problems(GOOD.replace("**Do:** run the setup check.", "")))

    def test_an_older_entry_above_a_newer_one_fails(self):
        self.assertTrue(problems(GOOD.replace("2026-10-08: First", "2026-10-09: First")))

    def test_two_entries_with_one_name_fail(self):
        self.assertTrue(problems(GOOD.replace("2026-10-08: Second", "2026-10-08: First")))

    def test_a_log_with_no_entries_fails(self):
        self.assertTrue(problems("# What's new\n\nNothing yet.\n"))


class WhatsNewCommands(unittest.TestCase):
    """The listing commands in skills/whats-new/SKILL.md, run as written against a sample log."""

    LOG = "# What's new\n\nIntro.\n\n## 2026-10-13: Third\n\nx\n\n## 2026-10-13: Second\n\nx\n\n## 2026-10-12: First\n\nx\n\n## 2026-10-11: Older\n\nx\n"

    def command(self, starts):
        skill = (ROOT / "skills" / "whats-new" / "SKILL.md").read_text()
        found = [line.strip() for line in skill.splitlines() if line.strip().startswith(starts)]
        self.assertEqual(len(found), 1, "one command starting " + starts)
        return found[0]

    def run_in(self, folder, cmd, env=None):
        import subprocess
        done = subprocess.run(["bash", "-c", cmd], cwd=folder, capture_output=True, text=True, env=env)
        return [line for line in done.stdout.splitlines() if line]

    def test_since_a_date_lists_every_entry_on_or_after_it(self):
        import tempfile
        cmd = self.command("grep '^## ' CHANGELOG.md | awk")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "CHANGELOG.md").write_text(self.LOG)
            got = self.run_in(tmp, cmd)
        self.assertEqual(got, ["## 2026-10-13: Third", "## 2026-10-13: Second", "## 2026-10-12: First"])


class WhatsNewAgainstItsRemote(unittest.TestCase):
    """The remote commands in skills/whats-new/SKILL.md, run as written in a clone whose origin moved on."""

    command = WhatsNewCommands.command
    run_in = WhatsNewCommands.run_in

    def setUp(self):
        import os
        import tempfile
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.remote, self.copy, self.other = tmp / "remote.git", tmp / "copy", tmp / "other"
        self.git(tmp, "init", "-q", "--bare", "-b", "main", str(self.remote))
        self.git(tmp, "init", "-q", "-b", "main", "seed")
        self.commit(tmp / "seed", WhatsNewCommands.LOG)
        self.git(tmp / "seed", "push", "-q", str(self.remote), "main")
        self.git(tmp, "clone", "-q", str(self.remote), str(self.copy))
        self.git(tmp, "clone", "-q", str(self.remote), str(self.other))
        self.add_heading(self.other, "## 2026-10-14: Remote-only")
        self.git(self.other, "push", "-q", "origin", "main")
        self.add_heading(self.copy, "## 2026-10-14: Local-only")
        self.git(self.copy, "fetch", "-q", "origin")

    def git(self, folder, *args):
        import subprocess
        identity = ["-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false"]
        subprocess.run(["git"] + identity + list(args), cwd=folder, env=self.env, check=True, capture_output=True)

    def commit(self, folder, log):
        (folder / "CHANGELOG.md").write_text(log)
        self.git(folder, "add", "CHANGELOG.md")
        self.git(folder, "commit", "-q", "-m", "log")

    def add_heading(self, folder, heading):
        log = (folder / "CHANGELOG.md").read_text()
        self.commit(folder, log.replace("Intro.\n\n", "Intro.\n\n{}\n\nx\n\n".format(heading)))

    def test_whats_new_lists_only_the_remotes_headings_missing_here(self):
        cmd = self.command("git show origin/HEAD:CHANGELOG.md")
        self.assertEqual(self.run_in(self.copy, cmd, env=self.env), ["## 2026-10-14: Remote-only"])

    def test_the_count_is_ahead_then_behind(self):
        cmd = self.command("git rev-list --left-right --count")
        self.assertEqual(self.run_in(self.copy, cmd, env=self.env), ["1\t1"])
        self.add_heading(self.other, "## 2026-10-15: Remote again")
        self.git(self.other, "push", "-q", "origin", "main")
        self.git(self.copy, "fetch", "-q", "origin")
        self.assertEqual(self.run_in(self.copy, cmd, env=self.env), ["1\t2"])


class StarterUpdatesCommands(unittest.TestCase):
    """The commands in skills/factory-updates/SKILL.md, run as written against a scratch clone of a
    stand-in upstream and a copy that shares none of its history."""

    run_in = WhatsNewCommands.run_in
    git = WhatsNewAgainstItsRemote.git
    commit = WhatsNewAgainstItsRemote.commit
    add_heading = WhatsNewAgainstItsRemote.add_heading
    LOG = "# What's new\n\nIntro.\n\n## 2026-10-01: A\n\nx\n"

    def command(self, starts):
        skill = (ROOT / "skills" / "factory-updates" / "SKILL.md").read_text()
        found = [line.strip() for line in skill.splitlines() if line.strip().startswith(starts)]
        self.assertEqual(len(found), 1, "one command starting " + starts)
        return found[0]

    def setUp(self):
        import os
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", TMPDIR=str(tmp))
        starter, self.copy = tmp / "starter", tmp / "copy"
        self.starter = starter
        self.env["clone"] = str(tmp / "factory-updates" / "factory")
        self.git(tmp, "init", "-q", "-b", "main", str(starter))
        (starter / "one.md").write_text("one\n")
        (starter / "two.md").write_text("two\n")
        self.git(starter, "add", "one.md", "two.md")
        self.commit(starter, self.LOG)
        self.sha = {"A": self.head(starter)}
        for name in ("B", "C"):
            self.add_heading(starter, "## 2026-10-0{}: {}".format(" ABC".index(name), name))
            self.sha[name] = self.head(starter)
        self.git(tmp, "clone", "-q", str(starter), self.env["clone"])
        self.git(tmp, "init", "-q", "-b", "main", str(self.copy))
        (self.copy / "one.md").write_text("one, adapted\n")
        (self.copy / "two.md").write_text("two\n")
        self.git(self.copy, "add", "one.md", "two.md")
        self.commit(self.copy, self.LOG.replace("Intro.\n\n", "Intro.\n\n## 2026-10-04: Copy-only\n\nx\n\n"
                                                "## 2026-10-02: B\n\nx\n\n"))

    def head(self, folder):
        return self.run_in(folder, "git rev-parse HEAD", env=self.env)[0]

    def run_with(self, cmd, **values):
        env = dict(self.env, **values)
        return self.run_in(self.copy, cmd, env=env)

    def test_the_baseline_comes_from_a_starter_line(self):
        log = (self.copy / "CHANGELOG.md").read_text()
        (self.copy / "CHANGELOG.md").write_text(log.replace("Intro.\n\n", "Intro.\n\nstarter: {}\n\n".format(self.sha["B"])))
        self.assertEqual(self.run_with(self.command("awk '/^## /{exit}")), [self.sha["B"]])

    def test_the_baseline_comes_from_the_newest_shared_heading(self):
        heading = self.run_with(self.command("grep '^## ' CHANGELOG.md | grep -xF"))
        self.assertEqual(heading, ["## 2026-10-02: B"])
        found = self.run_with(self.command('git -C "$clone" log --reverse --format=%H -S'), heading=heading[0])
        self.assertEqual(found, [self.sha["B"]])

    def test_the_commits_after_the_baseline_are_listed_oldest_first(self):
        found = self.run_with(self.command("git -C \"$clone\" log --reverse --format='%H %s'"), base=self.sha["A"])
        self.assertEqual(found, [self.sha["B"] + " log", self.sha["C"] + " log"])

    def test_an_edited_file_is_adapted_and_an_untouched_one_isnt(self):
        cmd = self.command('git -C "$clone" show "$base:$path" |') + " && echo same || echo adapted"
        self.assertEqual(self.run_with(cmd, base=self.sha["A"], path="one.md"), ["adapted"])
        self.assertEqual(self.run_with(cmd, base=self.sha["A"], path="two.md"), ["same"])

    def test_one_files_commits_leave_out_another_files(self):
        found = {}
        for name in ("one.md", "two.md"):
            (self.starter / name).write_text(name + ", changed upstream\n")
            self.git(self.starter, "add", name)
            self.git(self.starter, "commit", "-q", "-m", "touch " + name)
            found[name] = self.head(self.starter)
        self.git(Path(self.env["clone"]), "fetch", "-q", "origin", "main")
        cmd = self.command("git -C \"$clone\" log --format='%H %s' \"$base\"..origin/main --")
        self.assertEqual(self.run_with(cmd, base=self.sha["A"], path="two.md"), [found["two.md"] + " touch two.md"])
        self.assertEqual(self.run_with(cmd, base=self.sha["A"], path="one.md"), [found["one.md"] + " touch one.md"])

    CAPABILITIES = 'git -C "$clone" show origin/main:skills/factory-updates/capabilities.md'

    def test_the_capabilities_table_is_read_from_the_clone(self):
        table = self.starter / "skills" / "factory-updates" / "capabilities.md"
        table.parent.mkdir(parents=True)
        table.write_text("| Name |\n|---|\n| The loop |\n")
        self.git(self.starter, "add", "skills/factory-updates/capabilities.md")
        self.git(self.starter, "commit", "-q", "-m", "table")
        self.git(Path(self.env["clone"]), "fetch", "-q", "origin", "main")
        self.assertEqual(self.run_with(self.command(self.CAPABILITIES)), ["| Name |", "|---|", "| The loop |"])

    def test_an_upstream_without_the_capabilities_table_fails_the_command(self):
        cmd = self.command(self.CAPABILITIES) + " && echo found || echo missing"
        self.assertEqual(self.run_with(cmd), ["missing"])


if __name__ == "__main__":
    unittest.main()
