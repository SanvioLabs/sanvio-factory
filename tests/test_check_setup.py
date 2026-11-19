"""Run with: python3 -m unittest discover -s tests"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        self.fake_gh()  # no claude on PATH, so the mods check never runs the real one
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

    def test_the_public_factory_as_origin_warns(self):
        self.git("remote", "add", "origin", "git@github.com:SanvioLabs/sanvio-factory.git")
        status, line, fix = check_setup.check_remote(self.root)
        self.assertEqual(status, "WARN")
        self.assertIn("public Sanvio Factory", line)
        self.assertIn("private copy", fix)

    def test_its_old_address_is_not_recognised(self):
        # A clone still on the address from before the GitHub rename is told to set the new one by the upgrade page.
        self.git("remote", "add", "origin", "https://github.com/SanvioLabs/sanvio-harness-starter")
        status, line, _ = check_setup.check_remote(self.root)
        self.assertNotIn("public Sanvio Factory", line)

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

    MCP_FIX = ("Add it to the Approved tools table in steering/data-and-tools.md once the customer "
               "has agreed to it, or remove it")

    def write_approved(self, *rows, extra=""):
        table = "".join("| {} | business | 2026-11-01 |\n".format(row) for row in rows)
        path = self.root / "steering" / "data-and-tools.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Data and tools\n\n## Approved tools\n\nIntro.\n\n| Tool | Plan | Checked |\n"
                        "|---|---|---|\n| _your coding agent_ | _personal_ | _the date_ |\n" + table +
                        "\nAfter the table.\n\n## What may go to an AI coding tool\n\n"
                        "| Fine | Not without written permission |\n|---|---|\n"
                        "| Source code | Customers' personal data |\n" + extra)

    def write_servers(self, source, servers):
        path = self.root / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mcpServers": servers}))

    def test_no_mcp_config_passes(self):
        self.write_approved("github")
        status, line, fix = check_setup.check_mcp(self.root)
        self.assertEqual(status, "PASS")
        self.assertTrue(line.startswith("mcp: "))
        self.assertIsNone(fix)

    def test_a_listed_server_in_another_letter_case_passes_and_is_named(self):
        self.write_approved("`GitHub`")
        self.write_servers(".mcp.json", {"github": {"command": "gh-mcp"}})
        status, line, _ = check_setup.check_mcp(self.root)
        self.assertEqual(status, "PASS")
        self.assertIn("github", line)

    def assert_unlisted_warns(self, source):
        self.write_approved("github")
        self.write_servers(source, {"linear": {"command": "linear-mcp"}})
        status, line, fix = check_setup.check_mcp(self.root)
        self.assertEqual(status, "WARN")
        self.assertTrue(line.startswith("mcp: "))
        self.assertIn("linear ({})".format(source), line)
        self.assertIn(self.MCP_FIX, fix)

    def test_an_unlisted_server_in_mcp_json_warns(self):
        self.assert_unlisted_warns(".mcp.json")

    def test_an_unlisted_server_in_claude_settings_warns(self):
        self.assert_unlisted_warns(".claude/settings.json")

    def test_an_unlisted_server_in_claude_local_settings_warns(self):
        self.assert_unlisted_warns(".claude/settings.local.json")

    def test_a_server_matching_only_an_italic_placeholder_warns(self):
        self.write_approved("_github_", "*linear*")
        self.write_servers(".mcp.json", {"github": {}, "linear": {}})
        status, line, _ = check_setup.check_mcp(self.root)
        self.assertEqual(status, "WARN")
        self.assertIn("github (.mcp.json)", line)
        self.assertIn("linear (.mcp.json)", line)

    def test_a_config_that_isn_t_json_warns_without_a_crash(self):
        self.write_approved("github")
        (self.root / ".mcp.json").write_text("{not json")
        status, line, _ = check_setup.check_mcp(self.root)
        self.assertEqual(status, "WARN")
        self.assertIn(".mcp.json can't be read", line)

    def test_an_mcp_servers_that_isn_t_an_object_warns_beside_an_unlisted_server(self):
        self.write_approved("github")
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text(json.dumps({"mcpServers": ["github"]}))
        self.write_servers(".mcp.json", {"linear": {}})
        status, line, fix = check_setup.check_mcp(self.root)
        self.assertEqual(status, "WARN")
        self.assertIn(".claude/settings.json can't be read", line)
        self.assertIn("linear (.mcp.json)", line)
        self.assertIn(self.MCP_FIX, fix)

    def test_a_server_s_env_headers_and_args_are_never_printed(self):
        self.write_approved("github")
        self.write_servers(".mcp.json", {"linear": {
            "command": "npx", "args": ["--api-key-arg-text"], "env": {"TOKEN": "s3cret-value"},
            "headers": {"Authorization": "Bearer header-value"}}})
        status, line, fix = check_setup.check_mcp(self.root)
        self.assertEqual(status, "WARN")
        for value in ("s3cret-value", "header-value", "--api-key-arg-text", "TOKEN", "Authorization"):
            self.assertNotIn(value, line + fix)

    def test_a_name_only_in_the_plan_column_or_another_table_is_not_approved(self):
        self.write_approved("github", extra="| linear | x |\n")
        (self.root / "steering" / "data-and-tools.md").write_text(
            (self.root / "steering" / "data-and-tools.md").read_text().replace(
                "| github | business |", "| github | slack |"))
        self.write_servers(".mcp.json", {"slack": {}, "source code": {}, "linear": {}})
        status, line, _ = check_setup.check_mcp(self.root)
        self.assertEqual(status, "WARN")
        for name in ("slack", "source code", "linear"):
            self.assertIn("{} (.mcp.json)".format(name), line)

    def test_servers_under_the_home_folder_are_never_named(self):
        self.write_approved("github")
        home = self.root / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "settings.json").write_text(json.dumps({"mcpServers": {"homeonly": {}}}))
        (home / ".claude.json").write_text(json.dumps({"mcpServers": {"homeuser": {}}}))
        self.fake_gh()
        lines = [line for _, line, _ in check_setup.run(self.root, home) if line.startswith("mcp:")]
        self.assertEqual(len(lines), 1)
        self.assertNotIn("homeonly", lines[0])
        self.assertNotIn("homeuser", lines[0])

    def test_an_env_key_named_like_a_tool_is_not_a_server(self):
        self.write_approved("github")
        self.write_servers(".mcp.json", {"linear": {"env": {"github": "x"}}})
        status, line, _ = check_setup.check_mcp(self.root)
        self.assertEqual(status, "WARN")
        self.assertIn("linear (.mcp.json)", line)
        self.assertNotIn("github", line)

    def test_the_mcp_check_runs_with_the_others(self):
        self.fake_gh()
        self.assertTrue(any(line.startswith("mcp:") for _, line, _ in check_setup.run(self.root)))

    def test_projects_are_never_committed_but_stay_searchable(self):
        def ignored(path):
            return subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", path],
                                  env=ISOLATED).returncode == 0
        self.assertTrue(ignored("projects/billing/app.py"))
        self.assertFalse(ignored("projects/README.md"))
        searchable = (ROOT / ".ignore").read_text()
        self.assertIn("!/projects/", searchable)
        self.assertIn("!/company/", searchable)


class Mods(unittest.TestCase):
    """check_mods against a stand-in claude, on a PATH that holds only git and the stand-in."""
    SENTINEL = "/SENTINEL-install-path"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "copy"
        self.root.mkdir()
        self.env = os.environ.copy()
        self.addCleanup(self.restore_env)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "git").symlink_to(shutil.which("git"))
        os.environ["PATH"] = str(self.bin)
        self.write_root("market")

    def restore_env(self):
        os.environ.clear()
        os.environ.update(self.env)

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def write_root(self, market):
        self.market = market
        self.write(".claude-plugin/marketplace.json", {"name": market, "plugins": [
            {"name": "lens", "source": "./examples/mods/lens"},
            {"name": "stelliad", "source": {"source": "github", "repo": "o/r", "sha": "0" * 40}}]})
        self.write(".claude/settings.json", {"enabledPlugins": {
            "lens@" + market: True, "stelliad@" + market: True, "other@elsewhere": True}})
        self.write("examples/mods/lens/.claude-plugin/plugin.json", {"name": "lens", "version": "1.2.0"})

    def stand_in(self, script):
        claude = self.bin / "claude"
        claude.write_text('#!/bin/sh\necho "$@" >> "{}"\n{}\n'.format(self.tmp / "claude.args", script))
        claude.chmod(0o755)

    def listed(self, *entries):
        path = self.tmp / "plugins.json"
        path.write_text(json.dumps(list(entries)))
        self.stand_in('exec /bin/cat "{}"'.format(path))

    def entry(self, name, version="1.2.0", scope="user", enabled=True, project=None, market=None):
        found = {"id": "{}@{}".format(name, market or self.market), "version": version, "scope": scope,
                 "enabled": enabled, "installPath": "{}/{}".format(self.SENTINEL, name)}
        if project is not None:
            found["projectPath"] = str(project)
        return found

    def check(self):
        return check_setup.check_mods(self.root)

    def test_every_mod_installed_on_and_current_passes(self):
        self.listed(self.entry("lens"), self.entry("stelliad", version="3.0.0"))
        status, line, fix = self.check()
        self.assertEqual(status, "PASS")
        self.assertIn("lens 1.2.0", line)
        self.assertIn("stelliad", line)
        self.assertIsNone(fix)
        self.assertEqual((self.tmp / "claude.args").read_text().strip(), "plugin list --json")

    def test_a_mod_not_installed_warns_with_the_install_command(self):
        self.listed(self.entry("stelliad"))
        status, line, fix = self.check()
        self.assertEqual(status, "WARN")
        self.assertIn("not installed: lens", line)
        self.assertIn("claude plugin install lens@market --scope local", fix)

    def test_an_older_mod_warns_with_the_update_command_and_a_newer_one_passes(self):
        self.listed(self.entry("lens", version="1.1.9"), self.entry("stelliad"))
        status, line, fix = self.check()
        self.assertEqual(status, "WARN")
        self.assertIn("lens 1.1.9 (this repo has 1.2.0)", line)
        self.assertIn("claude plugin update lens@market", fix)
        # 1.10.0 is newer than 1.2.0, though it sorts before it as text.
        self.listed(self.entry("lens", version="1.10.0"), self.entry("stelliad"))
        self.assertEqual(self.check()[0], "PASS")

    def test_a_version_that_doesnt_parse_counts_as_older(self):
        self.listed(self.entry("lens", version="next"), self.entry("stelliad"))
        status, _, fix = self.check()
        self.assertEqual(status, "WARN")
        self.assertIn("claude plugin update lens@market", fix)

    def test_a_turned_off_mod_warns_with_the_enable_command_and_not_install(self):
        self.listed(self.entry("lens", enabled=False), self.entry("stelliad"))
        status, line, fix = self.check()
        self.assertEqual(status, "WARN")
        self.assertIn("turned off: lens", line)
        self.assertIn("claude plugin enable lens@market", fix)
        self.assertNotIn("install", fix)

    def test_an_entry_that_is_on_beats_one_that_is_off(self):
        self.listed(self.entry("lens", enabled=False), self.entry("lens", scope="local", project=self.root),
                    self.entry("stelliad"))
        self.assertEqual(self.check()[0], "PASS")

    def test_an_install_for_another_project_doesnt_count(self):
        elsewhere = self.tmp / "another-project"
        elsewhere.mkdir()
        self.listed(self.entry("lens", scope="local", project=elsewhere),
                    self.entry("lens", scope="project", project=elsewhere), self.entry("stelliad"))
        status, _, fix = self.check()
        self.assertEqual(status, "WARN")
        self.assertIn("claude plugin install lens@market --scope local", fix)

    def test_an_install_for_this_checkout_through_a_link_counts(self):
        link = self.tmp / "link"
        link.symlink_to(self.root)
        for scope in ("local", "project"):
            with self.subTest(scope=scope):
                self.listed(self.entry("lens", scope=scope, project=link), self.entry("stelliad"))
                self.assertEqual(self.check()[0], "PASS")

    def test_a_mod_switched_off_for_you_is_named_and_doesnt_warn(self):
        self.write(".claude/settings.local.json", {"enabledPlugins": {"lens@market": False}})
        self.listed(self.entry("stelliad"))
        status, line, fix = self.check()
        self.assertEqual(status, "PASS")
        self.assertIn("switched off for you: lens", line)
        self.assertIsNone(fix)

    def test_a_switched_off_mod_stays_out_of_a_warning(self):
        self.write(".claude/settings.local.json", {"enabledPlugins": {"lens@market": False}})
        self.listed()
        status, line, fix = self.check()
        self.assertEqual(status, "WARN")
        self.assertIn("not installed: stelliad", line)
        self.assertNotIn("lens@market", fix)

    def test_stelliad_passes_at_any_version(self):
        for version in ("0.0.1", "99.0.0", "weird"):
            with self.subTest(version=version):
                self.listed(self.entry("lens"), self.entry("stelliad", version=version))
                self.assertEqual(self.check()[0], "PASS")

    def assert_couldnt_check(self):
        status, line, fix = self.check()
        self.assertEqual(status, "WARN")
        self.assertIn("couldn't check", line)
        self.assertIn("claude plugin list", fix)

    def test_no_claude_warns(self):
        self.assert_couldnt_check()

    def test_claude_failing_warns(self):
        self.stand_in("exit 1")
        self.assert_couldnt_check()

    def test_output_that_isnt_json_warns(self):
        self.stand_in("echo 'Installed plugins:'")
        self.assert_couldnt_check()

    def test_a_list_that_takes_too_long_warns(self):
        self.stand_in("exec /bin/sleep 5")
        with mock.patch.object(check_setup, "CLAUDE_TIMEOUT", 0.5):
            self.assert_couldnt_check()

    def test_a_check_that_couldnt_run_doesnt_change_the_exit_status(self):
        self.stand_in("exit 1")
        out = io.StringIO()
        with mock.patch.object(check_setup, "run", lambda root, home=None: [check_setup.check_mods(self.root)]), \
                contextlib.redirect_stdout(out):
            code = check_setup.main([])
        self.assertEqual(code, 0)
        self.assertIn("WARN mods: couldn't check", out.getvalue())

    def test_paths_from_the_list_are_never_printed(self):
        elsewhere = self.entry("lens", scope="local", project="/SENTINEL-project-path")
        for entries in ([self.entry("lens"), self.entry("stelliad"), elsewhere],
                        [self.entry("stelliad"), elsewhere]):
            with self.subTest(count=len(entries)):
                self.listed(*entries)
                _, line, fix = self.check()
                self.assertNotIn("SENTINEL", line + (fix or ""))

    def test_a_renamed_marketplace_shows_in_the_commands(self):
        self.write_root("acme-tools")
        self.listed(self.entry("lens", version="1.0.0"))
        _, _, fix = self.check()
        self.assertIn("claude plugin update lens@acme-tools", fix)
        self.assertIn("claude plugin install stelliad@acme-tools --scope local", fix)

    def test_it_runs_with_the_others(self):
        self.assertTrue(any(line.startswith("mods:") for _, line, _ in check_setup.run(self.root)))


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
