"""Run with: python3 -m unittest discover -s tests"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_setup  # noqa: E402 (the import needs scripts/ on the path first)

# Keep the person's own git config out of these repos, so an unset key is unset.
ISOLATED = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


class SetupCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git("init", "-q")
        self.env = os.environ.copy()
        os.environ.update(ISOLATED)
        self.addCleanup(self.restore_env)

    def restore_env(self):
        os.environ.clear()
        os.environ.update(self.env)

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root)] + list(args), check=True, env=ISOLATED)

    def wire_links(self):
        (self.root / "skills").mkdir()
        (self.root / "AGENTS.md").write_text("# Rules\n")
        (self.root / "CLAUDE.md").write_text("@AGENTS.md\n")
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "skills").symlink_to("../skills")
        (self.root / ".kiro" / "steering").mkdir(parents=True)
        (self.root / ".kiro" / "steering" / "project.md").symlink_to("../../AGENTS.md")

    def test_no_old_name_passes(self):
        self.assertEqual(check_setup.check_old_names(self.root, environ={})[0], "PASS")

    def test_an_old_variable_still_set_warns_with_its_new_name_and_never_its_value(self):
        status, line, fix = check_setup.check_old_names(self.root, environ={"HARNESS_RETRO": "secret-ish"})
        self.assertEqual(status, "WARN")
        self.assertIn("HARNESS_RETRO", line)
        self.assertIn("SANVIO_RETRO", fix)
        self.assertNotIn("secret-ish", line + fix)

    def test_an_old_state_folder_still_here_warns(self):
        (self.root / ".harness").mkdir()
        status, line, _ = check_setup.check_old_names(self.root, environ={})
        self.assertEqual(status, "WARN")
        self.assertIn(".harness/", line)

    def test_an_old_folder_and_an_old_variable_are_both_named(self):
        (self.root / ".harness").mkdir()
        status, line, fix = check_setup.check_old_names(self.root, environ={"HARNESS_RETRO": "on"})
        self.assertEqual(status, "WARN")
        self.assertIn(".harness/", line)
        self.assertIn("HARNESS_RETRO", line)
        self.assertIn("SANVIO_RETRO", fix)

    def test_the_check_runs_with_the_others(self):
        self.assertIn("names:", " ".join(line for _, line, _ in check_setup.run(self.root)))

    def test_python_39_passes_and_38_fails(self):
        self.assertEqual(check_setup.check_python((3, 9, 0))[0], "PASS")
        self.assertEqual(check_setup.check_python((3, 8, 18))[0], "FAIL")

    def test_unset_hooks_path_fails_with_the_fix(self):
        status, line, fix = check_setup.check_hooks(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn("not set", line)
        self.assertIn("git config core.hooksPath .githooks", fix)

    def test_githooks_passes(self):
        self.git("config", "core.hooksPath", ".githooks")
        self.assertEqual(check_setup.check_hooks(self.root)[0], "PASS")

    def test_another_hooks_path_fails_and_names_it(self):
        self.git("config", "core.hooksPath", ".husky")
        status, line, _ = check_setup.check_hooks(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn(".husky", line)

    def test_wired_links_pass(self):
        self.wire_links()
        self.assertEqual(check_setup.check_links(self.root)[0], "PASS")

    def test_a_link_that_arrived_as_text_fails(self):
        self.wire_links()
        (self.root / ".claude" / "skills").unlink()
        (self.root / ".claude" / "skills").write_text("../skills")
        status, line, _ = check_setup.check_links(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn(".claude/skills", line)

    def test_no_remote_passes(self):
        self.assertEqual(check_setup.check_remote(self.root)[0], "PASS")

    def test_the_public_starter_as_origin_warns(self):
        self.git("remote", "add", "origin", "git@github.com:SanvioLabs/sanvio-harness-starter.git")
        status, line, fix = check_setup.check_remote(self.root)
        self.assertEqual(status, "WARN")
        self.assertIn("public starter", line)
        self.assertIn("private copy", fix)

    def test_a_token_in_the_remote_url_is_never_printed(self):
        self.git("remote", "add", "origin", "https://someone:ghp_notarealtoken@github.com/acme/harness.git")
        _, line, _ = check_setup.check_remote(self.root)
        self.assertNotIn("ghp_notarealtoken", line)
        self.assertIn("https://github.com/acme/harness.git", line)

    def test_a_remote_s_control_characters_print_marked(self):
        # Before T076 a newline in origin printed a line of its own (review after Phase 13, security).
        self.git("remote", "add", "origin", "https://gitlab.example/o/r\n- forged \x1b[2J")
        _, line, _ = check_setup.check_remote(self.root)
        self.assertNotIn("\n", line)
        self.assertNotIn("\x1b", line)
        self.assertIn("r?- forged ?[2J", line)

    def test_the_example_proposal_passes_the_gate_in_this_repo(self):
        self.assertEqual(check_setup.check_gate(ROOT)[0], "PASS")

    def test_a_missing_example_warns_rather_than_fails(self):
        self.assertEqual(check_setup.check_gate(self.root)[0], "WARN")

    def test_no_company_record_warns_and_points_at_orientation(self):
        status, _, fix = check_setup.check_company(self.root)
        self.assertEqual(status, "WARN")
        self.assertIn("/orientation", fix)

    def test_a_written_company_record_passes(self):
        (self.root / "company").mkdir()
        (self.root / "company" / "COMPANY.md").write_text("# Company\n")
        self.assertEqual(check_setup.check_company(self.root)[0], "PASS")

    def company_repo(self, origin="https://user:tok@github.com/acme/company.git"):
        company = self.root / "company"
        company.mkdir()
        subprocess.run(["git", "-C", str(company), "init", "-q"], check=True, env=ISOLATED)
        if origin:
            subprocess.run(["git", "-C", str(company), "remote", "add", "origin", origin],
                           check=True, env=ISOLATED)

    def fake_gh(self, script=None):
        """PATH holds only git and, given a script, a fake gh that runs it. Its arguments go to gh.args."""
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        (bin_dir / "git").symlink_to(shutil.which("git"))
        if script is not None:
            gh = bin_dir / "gh"
            gh.write_text('#!/bin/sh\necho "$@" >> "{}"\n{}\n'.format(self.root / "gh.args", script))
            gh.chmod(0o755)
        os.environ["PATH"] = str(bin_dir)

    def assert_no_token(self, result):
        _, line, fix = result
        self.assertNotIn("tok", line + (fix or ""))
        args = self.root / "gh.args"
        if args.exists():
            self.assertNotIn("tok", args.read_text())

    def test_a_public_company_repo_fails(self):
        self.company_repo()
        self.fake_gh("echo PUBLIC")
        status, line, _ = check_setup.check_company(self.root)
        self.assertEqual(status, "FAIL")
        self.assertIn("https://github.com/acme/company", line)

    def test_a_remote_that_isn_t_a_plain_url_prints_as_a_placeholder_in_the_command(self):
        # Before T076 it printed the remote as it came, so a ; or $( in it ran as a command (review after
        # Phase 13, security). Before T080 it was quoted, which fish reads otherwise, and cut after quoting
        # (review after Phase 14, security).
        self.fake_gh()
        for origin in ("https://github.com/acme/co;touch x", "https://github.com/acme/co\\'\";touch pwned;#",
                       "https://github.com/acme/" + "a" * 300):
            with self.subTest(origin=origin[:40]):
                shutil.rmtree(self.root / "company", ignore_errors=True)
                self.company_repo(origin=origin)
                _, _, fix = check_setup.check_company(self.root)
                self.assertIn("gh repo view <company/'s origin URL> --json visibility", fix)
                self.assertNotIn("touch", fix)

    def test_a_plain_remote_prints_as_it_is_in_the_command(self):
        self.company_repo(origin="https://github.com/acme/company.git")
        self.fake_gh()
        _, _, fix = check_setup.check_company(self.root)
        self.assertIn("gh repo view https://github.com/acme/company --json visibility", fix)

    def test_a_remote_starting_with_a_dash_never_reaches_gh(self):
        # Before T080 it went to gh as a flag, --web opening a browser (review after Phase 14, security).
        self.company_repo(origin=None)
        with open(self.root / "company" / ".git" / "config", "a") as config:
            config.write('[remote "origin"]\n\turl = --web\n')
        self.fake_gh("echo PRIVATE")
        status, _, fix = check_setup.check_company(self.root)
        self.assertEqual(status, "WARN")
        self.assertFalse((self.root / "gh.args").exists())
        self.assertIn("<company/'s origin URL>", fix)

    def test_a_private_company_repo_passes(self):
        self.company_repo()
        self.fake_gh("echo PRIVATE")
        result = check_setup.check_company(self.root)
        self.assertEqual(result[0], "PASS")
        self.assert_no_token(result)

    def test_an_internal_company_repo_passes(self):
        self.company_repo()
        self.fake_gh("echo INTERNAL")
        result = check_setup.check_company(self.root)
        self.assertEqual(result[0], "PASS")
        self.assert_no_token(result)

    def test_a_gh_error_warns_with_the_command(self):
        self.company_repo()
        self.fake_gh('echo "could not resolve $3 tok" >&2; exit 1')
        result = check_setup.check_company(self.root)
        self.assertEqual(result[0], "WARN")
        self.assertIn("gh repo view https://github.com/acme/company --json visibility", result[2])
        self.assert_no_token(result)

    def test_no_gh_warns_with_the_command(self):
        self.company_repo()
        self.fake_gh()
        status, _, fix = check_setup.check_company(self.root)
        self.assertEqual(status, "WARN")
        self.assertIn("gh repo view https://github.com/acme/company --json visibility", fix)

    def test_a_company_repo_with_no_origin_warns(self):
        self.company_repo(origin=None)
        self.fake_gh("echo PRIVATE")
        status, line, fix = check_setup.check_company(self.root)
        self.assertEqual(status, "WARN")
        self.assertIn("no origin", line)
        self.assertIn("gh repo view", fix)

    def test_an_ssh_origin_is_asked_about_as_https(self):
        self.company_repo(origin="git@github.com:acme/company.git")
        self.fake_gh("echo PRIVATE")
        self.assertEqual(check_setup.check_company(self.root)[0], "PASS")
        self.assertIn("https://github.com/acme/company", (self.root / "gh.args").read_text())

    def test_a_company_record_committed_in_the_harness_warns(self):
        (self.root / "company").mkdir()
        (self.root / "company" / "COMPANY.md").write_text("# Company\n")
        self.git("add", "company/COMPANY.md")
        status, line, fix = check_setup.check_company(self.root)
        self.assertEqual(status, "WARN")
        self.assertIn("committed in this repo", line)
        self.assertIn("gh repo view --json visibility", fix)

    def test_the_company_record_never_gets_committed(self):
        def ignored(path):
            return subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", path],
                                  env=ISOLATED).returncode == 0
        self.assertTrue(ignored("company/README.md"))
        self.assertTrue(ignored("company/COMPANY.md"))
        self.assertTrue(ignored("company/x/y"))

    def write_skill(self, folder, name):
        path = Path(folder) / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text("---\nname: {}\ndescription: x\n---\n".format(name))

    def test_a_personal_skill_with_a_repo_skills_name_warns(self):
        home = self.root / "home"
        self.write_skill(self.root / "skills", "review-pr")
        self.write_skill(home / ".claude" / "skills", "review-pr")
        status, line, _ = check_setup.check_shadowed_skills(self.root, home)
        self.assertEqual(status, "WARN")
        self.assertIn("review-pr", line)

    def test_a_personal_skill_renamed_by_frontmatter_still_counts(self):
        home = self.root / "home"
        self.write_skill(self.root / "skills", "review-pr")
        folder = home / ".claude" / "skills" / "my-pr-review"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text("---\nname: review-pr\ndescription: x\n---\n")
        self.assertEqual(check_setup.check_shadowed_skills(self.root, home)[0], "WARN")

    def test_different_personal_skills_pass(self):
        home = self.root / "home"
        self.write_skill(self.root / "skills", "review-pr")
        self.write_skill(home / ".claude" / "skills", "archify")
        self.assertEqual(check_setup.check_shadowed_skills(self.root, home)[0], "PASS")

    def test_no_personal_skills_folder_passes(self):
        self.write_skill(self.root / "skills", "review-pr")
        self.assertEqual(check_setup.check_shadowed_skills(self.root, self.root / "nohome")[0], "PASS")

    def test_projects_are_never_committed_but_stay_searchable(self):
        def ignored(path):
            return subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", path],
                                  env=ISOLATED).returncode == 0
        self.assertTrue(ignored("projects/billing/app.py"))
        self.assertFalse(ignored("projects/README.md"))
        searchable = (ROOT / ".ignore").read_text()
        self.assertIn("!/projects/", searchable)
        self.assertIn("!/company/", searchable)


def run_script(*args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "check_setup.py"), *args],
                          capture_output=True, text=True)


def check_lines(result):
    return [line for line in (result.stdout + result.stderr).splitlines()
            if line.startswith(("PASS", "WARN", "FAIL"))]


class SafeUrl(unittest.TestCase):
    def test_a_password_holding_an_at_is_never_printed(self):
        # Before T072 the cut stopped at the first @, and the password's tail printed (review after Phase 12).
        token = "made" + "up" + "tok" + "en42"
        self.assertEqual(check_setup.safe_url("https://u:p@" + token + "@github.com/o/r"), "https://github.com/o/r")
        self.assertEqual(check_setup.safe_url("git@github.com:o/r.git"), "git@github.com:o/r.git")


# Each scrub's cases, one table for both: check_setup.py keeps its own, since it runs before the harness is
# set up, and the two mustn't drift (review after Phase 13).
TOKEN = "made" + "up" + "tok" + "en42"
SCRUBS = (("https://u:p@" + TOKEN + "@github.com/o/r", "https://github.com/o/r"),
          ("https://someone:" + TOKEN + "@gitlab.example/o/r.git", "https://gitlab.example/o/r.git"),
          ("HTTPS://x:" + TOKEN + "@github.com/o/r", "HTTPS://github.com/o/r"),
          ("git@github.com:o/r.git", "git@github.com:o/r.git"),
          ("https://github.com/o/r", "https://github.com/o/r"),
          # Before T080 a quote in a password ended the user part, and the password printed (review after
          # Phase 14, security).
          ("https://u:pa'ss" + TOKEN + "@github.com/o/r", "https://github.com/o/r"))


class Scrubs(unittest.TestCase):
    def test_a_url_on_its_own_is_cut_whatever_its_password_holds(self):
        # A URL alone has no JSON around it, so nothing in its password ends the user part (review after
        # Phase 14, security).
        import loop  # noqa: E402  scripts/ is on the path
        for held in "'\"<>":
            url = "https://u:a" + held + TOKEN + "@github.com/o/r"
            with self.subTest(held=held):
                self.assertEqual(check_setup.safe_url(url), "https://github.com/o/r")
                self.assertEqual(loop.url_alone(url), "https://github.com/o/r")

    def test_both_scripts_cut_a_url_alike(self):
        import loop  # noqa: E402  scripts/ is on the path
        for url, want in SCRUBS:
            with self.subTest(url=url):
                self.assertEqual(check_setup.safe_url(url), want)
                self.assertEqual(loop.shown_url(url), want)


class Arguments(unittest.TestCase):
    def test_help_prints_usage_and_runs_no_check(self):
        result = run_script("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout)
        self.assertEqual(check_lines(result), [])

    def test_an_unknown_flag_stops_and_runs_no_check(self):
        result = run_script("--chek")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(check_lines(result), [])


if __name__ == "__main__":
    unittest.main()
