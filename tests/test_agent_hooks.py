"""Run with: python3 -m unittest discover -s tests"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / ".claude" / "hooks"
sys.path.insert(0, str(HOOKS))
import guard  # noqa: E402 (the import needs .claude/hooks/ on the path first)
import session_start  # noqa: E402


def call(tool, **tool_input):
    return guard.decide({"tool_name": tool, "tool_input": tool_input})


class Guard(unittest.TestCase):
    def assertDenied(self, verdict):
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict[0], "deny")

    def test_reading_env_files_is_denied(self):
        self.assertDenied(call("Read", file_path="/repo/.env"))
        self.assertDenied(call("Read", file_path="/repo/.env.local"))
        self.assertDenied(call("Edit", file_path="config/.env.production"))

    def test_env_example_is_allowed(self):
        self.assertIsNone(call("Read", file_path="/repo/.env.example"))

    def test_keys_are_denied(self):
        self.assertDenied(call("Read", file_path="/home/me/.ssh/id_ed25519"))
        self.assertDenied(call("Read", file_path="certs/server.pem"))
        self.assertDenied(call("Read", file_path="/home/me/.aws/credentials"))

    def test_ordinary_files_are_allowed(self):
        for path in ("AGENTS.md", "examples/proposal/gates/proposal_gate.py", "docs/environment.md", "keys.py"):
            self.assertIsNone(call("Read", file_path=path), path)

    def test_shell_reads_of_credentials_are_denied(self):
        self.assertDenied(call("Bash", command="cat .env"))
        self.assertDenied(call("Bash", command="grep KEY .env.local | head"))
        self.assertDenied(call("Bash", command="gh auth token"))
        self.assertDenied(call("Bash", command="printenv"))
        self.assertDenied(call("Bash", command="aws secretsmanager get-secret-value --secret-id x"))

    def test_a_key_file_is_refused_and_a_key_property_in_code_is_not(self):
        for command in ("cat server.key", "cat ca.key", "cat .key", "cat config/a.key", "git show main:a.key",
                        "openssl rsa -in tls.key -noout"):
            self.assertDenied(call("Bash", command=command))
        for command in ("python3 - <<'EOF'\nrows.sort(key=lambda s: s.key)\nEOF",
                        "node -e \"const k = e.key; f(k)\""):
            self.assertIsNone(call("Bash", command=command), command)
        # A file tool checks the path once resolved too, so a one-character name is refused there.
        self.assertDenied(call("Read", file_path="a.key"))

    def test_checking_a_credential_exists_is_allowed(self):
        for command in ("test -e .env && echo yes", "test -f .env.local", "[ -e .env ] && echo yes",
                        "[[ -s .env ]] || echo missing"):
            self.assertIsNone(call("Bash", command=command), command)

    def test_an_existence_check_does_not_cover_a_read(self):
        self.assertDenied(call("Bash", command="test -f .env && cat .env"))
        self.assertDenied(call("Bash", command="[ -e .env ] && grep KEY .env"))

    def test_ordinary_shell_is_allowed(self):
        for command in ("python3 -m unittest discover -s tests", "git status", "ls -la",
                        "cat .env.example", "python3 scripts/check_setup.py"):
            self.assertIsNone(call("Bash", command=command), command)

    def test_connector_writes_ask(self):
        for tool in ("mcp__claude_ai_Gmail__create_draft", "mcp__claude_ai_Google_Drive__share_file",
                     "mcp__claude_ai_Notion__notion-create-pages", "mcp__linear__createIssue",
                     "mcp__slack__send_message"):
            self.assertEqual(call(tool)[0], "ask", tool)

    def test_connector_reads_pass(self):
        for tool in ("mcp__claude_ai_Gmail__search_threads", "mcp__claude_ai_Google_Drive__read_file_content",
                     "mcp__claude_ai_Gmail__list_labels", "mcp__linear__getIssue"):
            self.assertIsNone(call(tool), tool)

    def test_connector_reads_by_name_pass(self):
        for tool in ("mcp__claude_ai_Notion__notion-search", "mcp__claude_ai_Notion__notion-fetch",
                     "mcp__skippy__skippy_knowledge_search"):
            self.assertIsNone(call(tool), tool)

    def test_any_connector_not_named_as_a_read_asks(self):
        for tool in ("mcp__claude_ai_Google_Drive__copy_file", "mcp__skippy__skippy_save_note",
                     "mcp__skippy__skippy_schedule_job", "mcp__db__run_query",
                     "mcp__claude_ai_Google_Calendar__respond_to_event", "mcp__x__search_and_delete",
                     "mcp__git__git_status", "mcp__skippy__skippy_usage", "mcp__linear__createIssue"):
            self.assertEqual((call(tool) or ("none",))[0], "ask", tool)

    def test_the_hook_prints_a_deny_decision(self):
        event = json.dumps({"tool_name": "Read", "tool_input": {"file_path": ".env"}})
        out = subprocess.run([sys.executable, str(HOOKS / "guard.py")], input=event,
                             capture_output=True, text=True, check=True).stdout
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertEqual(decision["permissionDecision"], "deny")

    def test_an_allowed_call_prints_nothing(self):
        event = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "AGENTS.md"}})
        out = subprocess.run([sys.executable, str(HOOKS / "guard.py")], input=event,
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(out, "")

    def test_garbage_input_lets_the_call_through_and_says_so(self):
        result = subprocess.run([sys.executable, str(HOOKS / "guard.py")], input="not json",
                                capture_output=True, text=True, env=interactive_env())
        self.assertEqual(result.returncode, 0)
        self.assertIn("wasn't checked", json.loads(result.stdout)["systemMessage"])


def interactive_env():
    """This environment as a person's session has it: no switch that makes the guard stricter, so a test
    reads the same whether a person runs it or a loop agent does."""
    return {k: v for k, v in os.environ.items()
            if k not in ("SANVIO_HEADLESS", "HARNESS_HEADLESS", "SANVIO_UNATTENDED", "SANVIO_CONFINE")}


class Unattended(unittest.TestCase):
    """A loop agent's session: SANVIO_UNATTENDED=1. Nobody is there to read a warning, so a call the guard
    can't check is refused, and nothing else changes."""

    def test_a_call_the_guard_cant_read_is_refused(self):
        env = dict(interactive_env(), SANVIO_UNATTENDED="1")
        result = subprocess.run([sys.executable, str(HOOKS / "guard.py")], input="not json",
                                capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(result.returncode, 0)
        out = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertEqual(out["permissionDecisionReason"], guard.UNATTENDED_UNCHECKED)

    def test_only_one_counts(self):
        for value in ("0", "", "yes"):
            env = dict(interactive_env(), SANVIO_UNATTENDED=value)
            result = subprocess.run([sys.executable, str(HOOKS / "guard.py")], input="not json",
                                    capture_output=True, text=True, env=env, timeout=30)
            self.assertIn("wasn't checked", json.loads(result.stdout)["systemMessage"], value)

    def test_it_adds_none_of_a_headless_runs_limits(self):
        with mock.patch.dict(os.environ, interactive_env(), clear=True):
            with mock.patch.dict(os.environ, {"SANVIO_UNATTENDED": "1"}):
                self.assertIsNone(guard.decide({"tool_name": "Bash", "tool_input": {"command": "git status"}}))
                self.assertIsNone(guard.decide({"tool_name": "Read", "tool_input": {"file_path": "AGENTS.md"}}))
                self.assertEqual(guard.decide({"tool_name": "Read", "tool_input": {"file_path": ".env"}})[0], "deny")


class TheLogs(unittest.TestCase):
    """No session's agent writes to, moves or deletes the usage log or the loop's logs. Reading them is fine."""

    WRITES = [("Write", {"file_path": ".sanvio/usage/pat.jsonl", "content": "x"}),
              ("Edit", {"file_path": "/repo/.sanvio/usage/pat.jsonl", "old_string": "a", "new_string": "b"}),
              ("Write", {"file_path": ".loop/loop.log", "content": "x"}),
              ("Edit", {"file_path": ".loop/issue-12/agent.log", "old_string": "a", "new_string": "b"}),
              ("Write", {"file_path": ".loop/projects/app/loop.log", "content": "x"})]
    COMMANDS = ["rm .sanvio/usage/pat.jsonl", "rm -rf .sanvio/usage", "echo x >> .sanvio/usage/pat.jsonl",
                "echo x > .loop/loop.log", "mv .loop/loop.log /tmp/old.log", "truncate -s 0 .loop/loop.log",
                "sed -i '' 1d .sanvio/usage/pat.jsonl", "printf x | tee -a .loop/issue-3/agent.log",
                "cp /tmp/forged.jsonl .sanvio/usage/pat.jsonl", ": > .sanvio/usage/pat.jsonl"]
    READS = ["tail -f .loop/loop.log", "cat .sanvio/usage/pat.jsonl", "grep skill .sanvio/usage/pat.jsonl",
             "tail -n 50 .loop/loop.log > /tmp/recent.txt", "cp .sanvio/usage/pat.jsonl /tmp/copy.jsonl",
             "wc -l .loop/issue-3/agent.log", "python3 scripts/usage_report.py"]

    def test_writing_a_log_is_refused(self):
        for tool, tool_input in self.WRITES:
            verdict = call(tool, **tool_input)
            self.assertEqual(verdict[0] if verdict else None, "deny", (tool, tool_input))
            self.assertIn("log", verdict[1])

    def test_a_command_that_changes_a_log_is_refused(self):
        for command in self.COMMANDS:
            verdict = call("Bash", command=command)
            self.assertEqual(verdict[0] if verdict else None, "deny", command)

    def test_reading_a_log_is_fine(self):
        self.assertIsNone(call("Read", file_path=".sanvio/usage/pat.jsonl"))
        self.assertIsNone(call("Read", file_path=".loop/loop.log"))
        for command in self.READS:
            self.assertIsNone(call("Bash", command=command), command)

    def test_other_files_nearby_are_untouched(self):
        self.assertIsNone(call("Write", file_path=".loop/issue-3/plan.md", content="x"))
        self.assertIsNone(call("Write", file_path=".sanvio/prices.json", content="{}"))
        self.assertIsNone(call("Bash", command="rm .loop/issue-3/plan.md"))


def deny_rule_matches(rule, path):
    """Whether a permissions rule's path pattern matches a path from the repo root, the gitignore way Claude
    Code reads it: **/ any folders or none, /** everything below, * within one name."""
    pattern = re.escape(rule)
    pattern = pattern.replace(r"\*\*/", "(?:.*/)?").replace(r"/\*\*", "/.*").replace(r"\*", "[^/]*")
    return re.fullmatch(pattern, path) is not None


class ProjectMcpServers(unittest.TestCase):
    """A server named in a .mcp.json isn't started without a person's yes (NIST SP 800-53 AC-20)."""

    def test_project_mcp_servers_are_not_all_enabled(self):
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
        self.assertIs(settings.get("enableAllProjectMcpServers"), False)


class DenyList(unittest.TestCase):
    """.claude/settings.json's permissions.deny: Claude Code itself refusing the credential files the guard
    refuses, so they stay refused when the guard doesn't run or errors. Checked live on 2026-11-11 with
    claude -p in a scratch repo: Read(**/.env) refused .env and sub/.env, and .env.example stayed readable."""

    SETTINGS = json.loads((ROOT / ".claude" / "settings.json").read_text())
    # Paths the guard refuses, one or more for each kind of file its CREDENTIAL pattern names.
    CREDENTIALS = [".env", "app/.env", ".env.local", ".env.production.local", ".env.development",
                   ".env.production", ".env.staging", ".env.test", "server.pem", "certs/tls.key", "id_rsa",
                   "id_ed25519", "id_ecdsa", ".aws/credentials", ".ssh/config", ".netrc", ".npmrc", ".pypirc",
                   "cert.p12", "cert.pfx", "store.jks", "app.keystore", ".kube/config",
                   "service-account-prod.json", ".htpasswd", ".docker/config.json", ".gnupg/pubring.kbx"]
    ORDINARY = [".env.example", ".env.sample", ".env.template", "notes.txt", "README.md", "steering/gates.md",
                "src/keys.py"]

    def rules(self, tool):
        deny = self.SETTINGS.get("permissions", {}).get("deny", [])
        return [rule[len(tool) + 1:-1] for rule in deny if rule.startswith(tool + "(") and rule.endswith(")")]

    def test_each_credential_the_guard_refuses_is_denied_to_read_and_edit(self):
        for path in self.CREDENTIALS:
            self.assertTrue(guard.path_names_credential(path, str(ROOT)), path + " isn't one the guard refuses")
            for tool in ("Read", "Edit"):
                self.assertTrue(any(deny_rule_matches(rule, path) for rule in self.rules(tool)), (tool, path))

    def test_an_example_env_file_and_ordinary_files_stay_readable(self):
        for path in self.ORDINARY:
            for tool in ("Read", "Edit"):
                self.assertFalse([r for r in self.rules(tool) if deny_rule_matches(r, path)], (tool, path))

    def test_read_and_edit_deny_the_same_paths(self):
        self.assertTrue(self.rules("Read"))
        self.assertEqual(sorted(self.rules("Read")), sorted(self.rules("Edit")))

    def test_the_home_folders_are_denied_too(self):
        for rule in ("~/.ssh/**", "~/.aws/credentials", "~/.gnupg/**"):
            self.assertIn(rule, self.rules("Read"))


def reviewer_runs(command, cwd=None):
    event = {"tool_name": "Bash", "tool_input": {"command": command}, "agent_type": "security-reviewer"}
    if cwd:
        event["cwd"] = str(cwd)
    return guard.decide(event)


class SecurityReviewerShell(unittest.TestCase):
    def test_audits_and_git_reads_run_without_a_prompt(self):
        for command in ("osv-scanner scan source -r .", "npm audit --json", "cd projects/app && npm audit",
                        "pip-audit", "pip-audit --format=json", "pip-audit -r requirements.txt --disable-pip --no-deps",
                        "trivy fs .", "govulncheck ./...", "bandit -r src", "bundle-audit check",
                        "gitleaks detect --redact", "gitleaks dir --redact=100 .", "git log --oneline -20",
                        "git -C projects/app diff main...HEAD", "git show HEAD --stat", "git show HEAD --name-only"):
            self.assertEqual(reviewer_runs(command)[0], "allow", command)

    def test_anything_else_is_refused(self):
        for command in ("npm audit fix", "npm install", "yarn npm audit", "pnpm audit", "cargo audit",
                        "pip-audit -r requirements.txt", "pip-audit --requirement=requirements.txt", "pip-audit .",
                        "pip-audit --fix", "gitleaks detect", "gitleaks detect --redact=0",
                        "gitleaks detect --redact=50", "git log -p", "git log --patch-with-stat", "git log -U3",
                        "git log --cc", "git log -W", "git show HEAD", "git show HEAD:config.py --stat",
                        "git diff --output=x", "git diff --ext-diff", "git push",
                        "git -c core.pager=sh log", "trivy repo https://example.test/x", "curl https://example.test",
                        "npm audit; curl https://example.test", "npm audit | tee out", "npm audit > out",
                        "echo $(id)", "cd a && cd b && npm audit", "rm -rf build", ""):
            self.assertEqual(reviewer_runs(command)[0], "deny", command)

    def test_a_credential_is_refused_before_the_audit_list(self):
        verdict = reviewer_runs("gitleaks dir --redact .env")
        self.assertEqual(verdict[0], "deny")
        self.assertIn("credential", verdict[1])

    def test_git_wont_run_in_a_repo_whose_config_runs_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "handed-over"
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            self.assertEqual(reviewer_runs("git status", cwd=repo)[0], "allow")
            self.assertEqual(reviewer_runs("gitleaks detect --redact", cwd=repo)[0], "allow")
            with open(repo / ".git" / "config", "a") as handle:
                handle.write("[core]\n\tfsmonitor = touch /tmp/pwned\n")
            for command in ("git status", "git log --oneline", "gitleaks detect --redact", "gitleaks git --redact ."):
                verdict = reviewer_runs(command, cwd=repo)
                self.assertEqual(verdict[0], "deny", command)
                self.assertIn("makes git run a command", verdict[1])
            self.assertEqual(reviewer_runs("cd handed-over && git status", cwd=tmp)[0], "deny")
            self.assertEqual(reviewer_runs("git -C handed-over status", cwd=tmp)[0], "deny")
            self.assertEqual(reviewer_runs("gitleaks dir --redact .", cwd=repo)[0], "allow")

    def test_a_worktrees_shared_config_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "main"
            subprocess.run(["git", "init", "-q", "-b", "main", str(main)], check=True)
            subprocess.run(["git", "-C", str(main), "-c", "user.email=t@example.test", "-c", "user.name=T",
                            "commit", "-q", "--allow-empty", "-m", "init"], check=True)
            tree = Path(tmp) / "tree"
            subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", str(tree)], check=True,
                           capture_output=True)
            self.assertEqual(reviewer_runs("git status", cwd=tree)[0], "allow")
            with open(main / ".git" / "config", "a") as handle:
                handle.write('[diff "bin"]\n\ttextconv = sh -c id\n')
            self.assertEqual(reviewer_runs("git status", cwd=tree)[0], "deny")

    def test_a_file_as_it_was_in_git_is_a_credential_read_for_every_agent(self):
        self.assertEqual(call("Bash", command="git show HEAD:.env")[0], "deny")
        self.assertEqual(call("Bash", command="git show main:config/server.key")[0], "deny")
        self.assertIsNone(call("Bash", command="git show HEAD:README.md"))

    def test_other_agents_and_the_main_session_are_untouched(self):
        self.assertIsNone(call("Bash", command="npm install"))
        self.assertIsNone(guard.decide({"tool_name": "Bash", "tool_input": {"command": "npm install"},
                                        "agent_type": "reviewer"}))


def headless(tool, _cwd=guard.ROOT, **tool_input):
    """The guard's verdict in a run bin/factory started, which it starts at the root."""
    with mock.patch.dict(os.environ, {"SANVIO_HEADLESS": "1"}):
        return guard.decide({"tool_name": tool, "tool_input": tool_input, "cwd": _cwd})


class HeadlessRun(unittest.TestCase):
    """A session bin/factory started: nobody watches, and what it reads was written by someone else."""

    def test_the_old_name_still_makes_a_run_headless_for_a_release(self):
        with mock.patch.dict(os.environ, {"HARNESS_HEADLESS": "1"}):
            os.environ.pop("SANVIO_HEADLESS", None)
            self.assertEqual(guard.decide({"tool_name": "Bash", "tool_input": {"command": "npm test"},
                                           "cwd": guard.ROOT}), ("deny", guard.HEADLESS_SHELL))
            self.assertIsNotNone(guard.headless_rewrite({"tool_name": "Grep", "tool_input": {"pattern": "x"}}))
        with mock.patch.dict(os.environ, {"SANVIO_HEADLESS": "0", "HARNESS_HEADLESS": "1"}):
            self.assertEqual(guard.decide({"tool_name": "Bash", "tool_input": {"command": "npm test"},
                                           "cwd": guard.ROOT})[0], "deny")

    def test_an_exact_read_of_a_pull_request_or_issue_passes(self):
        for command in ("gh pr view 12", "gh pr view 12 --comments", "gh pr diff 12", "gh issue view 7",
                        "gh issue view 7 --comments", "gh pr view '12'"):
            self.assertIsNone(headless("Bash", command=command), command)

    def test_every_other_command_is_refused(self):
        for command in ("gh pr view -R example.invalid/o/r 1", "gh pr view --repo=o/r 1",
                        "gh pr view https://example.invalid/x/y/pull/1", "gh pr view 1 --web", "gh pr view 1 -w",
                        "gh pr view 1 --jq .", "gh pr view 1 -q .", "gh pr view 1 --json body --jq .body",
                        "gh pr view 1 --template x", "gh pr view 1; ls", "gh pr view 1 && ls", "gh pr view $(id)",
                        "gh pr diff 1 --comments", "gh pr view", "gh pr view main", "gh pr list", "gh pr merge 1",
                        "GH_HOST=example.invalid gh pr view 1", "git fetch", "git diff --output=x", "npm test",
                        "ls", "cat README.md", ""):
            verdict = headless("Bash", command=command)
            self.assertIsNotNone(verdict, command)
            self.assertEqual(verdict[0], "deny", command)
            self.assertIn("headless", verdict[1], command)

    def test_the_security_reviewers_audit_list_doesnt_open_a_headless_run(self):
        with mock.patch.dict(os.environ, {"SANVIO_HEADLESS": "1"}):
            verdict = guard.decide({"tool_name": "Bash", "tool_input": {"command": "osv-scanner scan source -r ."},
                                    "agent_type": "security-reviewer"})
        self.assertEqual(verdict, ("deny", guard.HEADLESS_SHELL))

    def test_a_call_the_guard_cant_read_is_refused_headless_and_let_through_otherwise(self):
        hook = [sys.executable, str(HOOKS / "guard.py")]
        env = dict(interactive_env(), SANVIO_HEADLESS="1")
        result = subprocess.run(hook, input="not json", capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        env.pop("SANVIO_HEADLESS")
        result = subprocess.run(hook, input="not json", capture_output=True, text=True, env=env, timeout=30)
        self.assertIn("wasn't checked", json.loads(result.stdout)["systemMessage"])

    def test_a_connector_is_refused_even_when_named_as_a_read(self):
        self.assertEqual(headless("mcp__claude_ai_Gmail__search_threads", query="x")[0], "deny")

    def test_reading_files_still_passes_and_credentials_are_still_refused(self):
        self.assertIsNone(headless("Read", file_path="README.md"))
        self.assertEqual(headless("Read", file_path="/repo/.env")[0], "deny")

    def test_outside_a_headless_run_nothing_changes(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("SANVIO_HEADLESS", None)
            os.environ.pop("HARNESS_HEADLESS", None)
            self.assertIsNone(call("Bash", command="npm test"))
            self.assertIsNone(call("Bash", command="gh pr view -R example.invalid/o/r 1"))
            self.assertIsNone(call("mcp__claude_ai_Gmail__search_threads", query="x"))
            self.assertIsNone(call("Read", file_path="/etc/hosts"))
            self.assertIsNone(call("Grep", pattern="x", path="/etc"))

    def test_a_file_tool_reaching_outside_the_root_is_refused(self):
        up = os.path.join(guard.ROOT, "..", "elsewhere")
        for tool, tool_input in (
                ("Read", {"file_path": "/etc/hosts"}), ("Read", {"file_path": up}), ("Read", {"file_path": "../x"}),
                ("Grep", {"pattern": "x", "path": "/etc"}), ("Grep", {"pattern": "x", "path": up}),
                ("Grep", {"pattern": "x", "path": ".."}),
                ("Glob", {"pattern": "*", "path": "/etc"}), ("Glob", {"pattern": "*", "path": up}),
                ("Glob", {"pattern": "/etc/*"}), ("Glob", {"pattern": "../**"}),
                ("Glob", {"pattern": "skills/*/../../../**"}), ("Glob", {"pattern": "{..,x}/**"}),
                ("Glob", {"pattern": "{..,a}/{..,b}/**"}), ("Glob", {"pattern": "{/,x}etc/**"}),
                ("Glob", {"pattern": "\\.\\./**"}),
                ("Glob", {"pattern": "{" + ",".join("a%d" % i for i in range(65)) + "}/*"})):
            self.assertEqual(headless(tool, **tool_input), ("deny", guard.HEADLESS_OUTSIDE), (tool, tool_input))

    def test_a_link_out_of_the_root_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, outside = Path(tmp) / "root", Path(tmp) / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "notes.md").write_text("x")
            (root / "link").symlink_to(outside)
            with mock.patch.object(guard, "ROOT", os.path.realpath(root)):
                for tool, tool_input in (("Read", {"file_path": str(root / "link" / "notes.md")}),
                                         ("Grep", {"pattern": "x", "path": str(root / "link")}),
                                         ("Glob", {"pattern": "link/*"}), ("Glob", {"pattern": "*", "path": "link"})):
                    self.assertEqual(headless(tool, _cwd=str(root), **tool_input), ("deny", guard.HEADLESS_OUTSIDE),
                                     tool)
                self.assertIsNone(headless("Glob", _cwd=str(root), pattern="*"))

    def test_a_file_tool_inside_the_root_passes(self):
        self.assertIsNone(headless("Read", file_path=os.path.join(guard.ROOT, "README.md")))
        self.assertIsNone(headless("Read", file_path="projects/some-repo/src/app.py"))
        self.assertIsNone(headless("Grep", pattern="x"))
        self.assertIsNone(headless("Grep", pattern="x", path="steering"))
        self.assertIsNone(headless("Glob", pattern="*", path="skills/"))
        self.assertIsNone(headless("Glob", pattern="**/*.md"))

    def test_a_run_whose_folder_is_outside_the_root_reads_nothing(self):
        self.assertEqual(headless("Grep", _cwd="/etc", pattern="x"), ("deny", guard.HEADLESS_OUTSIDE))


class Search(unittest.TestCase):
    """Grep reads what it searches, so a credential is as off limits to it as to Read. Glob only lists names."""

    def test_a_grep_naming_a_credential_is_refused(self):
        for tool_input in ({"path": "/repo/.env"}, {"path": "/home/me/.ssh/id_ed25519"}, {"path": "/home/me/.ssh"},
                           {"path": "/home/me/.aws/"}, {"glob": "*.pem"}, {"glob": ".env*"}, {"glob": "**/.env"},
                           {"glob": "*.{pem,key}"}, {"glob": ".env.*"},
                           # A wildcard or class inside the name, an escape, another case, a list.
                           {"glob": ".en?"}, {"glob": ".e*v"}, {"glob": "*.pe?"}, {"glob": "id_*"},
                           {"glob": ".e[n]v"}, {"glob": "*.pe[m]"}, {"glob": "\\.env"}, {"glob": ".ss[h]/*"},
                           {"glob": ".ENV"}, {"glob": "*.md,.env"}, {"glob": "*.md .env"},
                           # Padding a brace list past what the guard checks refuses rather than skips.
                           {"glob": "{.env," + ",".join("a%d" % i for i in range(64)) + "}"},
                           # A path that only names a credential once it's tidied up.
                           {"path": "/home/me/.ssh//"}, {"path": "~/.aws/./"}, {"path": "projects/app/.ENV"},
                           {"path": "certs/server.PEM"}):
            verdict = call("Grep", pattern="KEY", **tool_input)
            self.assertEqual(verdict[0] if verdict else None, "deny", tool_input)
            self.assertIn("looks like a credential file", verdict[1])

    def test_a_link_to_a_credential_is_refused_by_where_it_lands(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret = Path(tmp) / "server.pem"
            secret.write_text("x")
            (Path(tmp) / "setup.md").symlink_to(secret)
            for tool, tool_input in (("Read", {"file_path": str(Path(tmp) / "setup.md")}),
                                     ("Grep", {"pattern": "x", "path": str(Path(tmp) / "setup.md")})):
                self.assertEqual(call(tool, **tool_input)[0], "deny", tool)

    def test_an_ordinary_search_passes(self):
        for tool_input in ({}, {"path": "steering/"}, {"glob": "*.md"}, {"glob": "*.{py,md}"}, {"glob": "*"},
                           {"glob": "**/*.ts"}, {"glob": "*key*"}, {"glob": "*.env.example"},
                           {"glob": ".env.example*"}, {"path": "/repo/.env.example"}, {"type": "sh"}):
            self.assertIsNone(call("Grep", pattern="KEY", **tool_input), tool_input)

    def test_a_headless_search_by_a_type_that_takes_in_credentials_is_refused(self):
        self.assertEqual(headless("Grep", pattern="KEY", type="sh")[0], "deny")
        self.assertEqual(headless("Grep", pattern="KEY", type=["py", "sh"])[0], "deny")
        self.assertIsNone(headless("Grep", pattern="KEY", type="py"))

    def test_a_headless_glob_that_can_match_a_credential_is_refused_however_broad(self):
        for glob in ("*env*", "*key*", "*en*", "*"):
            self.assertEqual(headless("Grep", pattern="KEY", glob=glob)[0], "deny", glob)
        for glob in ("*.md", "*.{py,ts}", "src/**/*.go"):
            self.assertIsNone(headless("Grep", pattern="KEY", glob=glob), glob)

    def test_listing_names_passes_even_for_credentials(self):
        self.assertIsNone(call("Glob", pattern="**/*.md"))
        self.assertIsNone(call("Glob", pattern="**/.env*"))

    def test_the_guard_is_wired_to_every_tool_it_has_a_rule_for(self):
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
        for script in ("guard.py", "usage_log.py"):
            matchers = [entry["matcher"] for entry in settings["hooks"]["PreToolUse"]
                        if any(script in hook["command"] for hook in entry["hooks"])]
            self.assertEqual(len(matchers), 1, script)
            for tool in guard.CHECKED_TOOLS + ("mcp__any__get_thing",):
                self.assertTrue(re.fullmatch(matchers[0], tool), "{} doesn't see {}".format(script, tool))


class MoreCredentials(unittest.TestCase):
    """Keystores, cluster and cloud config, and the like are credentials as much as an env file is."""

    NAMES = ("certs/store.p12", "certs/STORE.P12", "client.pfx", "app.jks", "release.keystore",
             "/home/me/.kube/config", "keys/service-account-prod.json", "/srv/site/.htpasswd",
             "/home/me/.docker/config.json", "/home/me/.gnupg/secring.gpg")

    def test_each_is_refused_to_every_tool_that_names_it(self):
        for name in self.NAMES:
            for verdict in (call("Read", file_path=name), call("Edit", file_path=name),
                            call("Grep", pattern="x", path=name), call("Bash", command="cat " + name)):
                self.assertEqual(verdict[0] if verdict else None, "deny", name)

    def test_a_folder_of_them_is_refused_to_a_search(self):
        for folder in ("/home/me/.gnupg", "/home/me/.kube/", "~/.gnupg"):
            self.assertEqual(call("Grep", pattern="x", path=folder)[0], "deny", folder)

    def test_a_glob_that_can_only_match_one_is_refused(self):
        for glob in ("*.p12", "*.P12", ".kube/*", "*.{pfx,jks}", "service-account*.json"):
            self.assertEqual(call("Grep", pattern="x", glob=glob)[0], "deny", glob)
        for glob in ("*.json", "*config.json", "config.json"):
            self.assertIsNone(call("Grep", pattern="x", glob=glob), glob)

    def test_a_secret_printing_command_is_refused_in_any_case(self):
        for command in ("PRINTENV", "Printenv HOME", "GH AUTH TOKEN"):
            self.assertEqual(call("Bash", command=command)[0], "deny", command)

    def test_ordinary_files_are_still_readable(self):
        for name in ("README.md", "package.json", "tsconfig.json", "keys.py", "config.json", "src/keystore.ts"):
            self.assertIsNone(call("Read", file_path=name), name)
            self.assertIsNone(call("Bash", command="cat " + name), name)


class HeadlessPrivate(unittest.TestCase):
    """Inside the root, the files that hold tokens or company data stay out of a headless run's reach."""

    def test_each_private_place_is_refused(self):
        for path in (".claude/settings.local.json", ".claude/SETTINGS.LOCAL.JSON", ".git/config",
                     "projects/app/.git/config", "company/COMPANY.md", "local-data/export.csv",
                     os.path.join(guard.ROOT, "company", "DATA.md")):
            self.assertEqual(headless("Read", file_path=path), ("deny", guard.HEADLESS_PRIVATE), path)
        for tool_input in ({"path": "company"}, {"path": "local-data/"}, {"path": "projects/app/.git"},
                           {"path": ".claude/settings.local.json"}, {"path": "projects/app", "glob": "config"},
                           {"path": "projects/app", "glob": ".git/*"}):
            self.assertEqual(headless("Grep", pattern="x", **tool_input), ("deny", guard.HEADLESS_PRIVATE), tool_input)
        for tool_input in ({"pattern": "company/*"}, {"pattern": "{company,src}/*"}, {"pattern": "*/.git/config"},
                           {"pattern": "*", "path": "local-data"}, {"pattern": "**/company/*"},
                           {"pattern": "**/settings.local.json"}):
            self.assertEqual(headless("Glob", **tool_input), ("deny", guard.HEADLESS_PRIVATE), tool_input)

    def test_a_search_glob_that_brings_a_private_place_back_in_is_refused(self):
        # A ripgrep glob that matches an ignored or hidden folder or file searches it: {company,*.md}
        # lists company/, measured with Claude Code's own --hidden --glob '!.git' on 2026-10-25.
        for glob in ("{company,*.md}", "company/**", "local-data/**", "*.local.json", "settings.local.json",
                     ".claude/**", "{.claude,settings.local.json}", "{.git,*.md}", "co*y", "/company"):
            self.assertEqual(headless("Grep", pattern="x", glob=glob), ("deny", guard.HEADLESS_PRIVATE), glob)
        for glob in ("*.md", "src/**/*.go", "**/*.ts", "!*.lock"):
            self.assertIsNone(headless("Grep", pattern="x", glob=glob), glob)

    def test_a_caret_class_is_read_as_ripgrep_reads_it(self):
        # ripgrep reads [^x] as any character but x: {compan[^_],*.md} listed company/, measured 2026-10-25.
        for glob in ("{compan[^_],*.md}", "settings.local.jso[^_]", ".en[^_]"):
            self.assertEqual(headless("Grep", pattern="x", path="projects/app", glob=glob)[0], "deny", glob)
        for glob in ("*.p1[^_]", ".en[^_]", "id_rs[^_]"):
            self.assertEqual(call("Grep", pattern="x", glob=glob)[0], "deny", glob)
        self.assertIsNone(call("Grep", pattern="x", glob="*.m[^_]"))

    def test_a_glob_can_still_list_names_where_it_names_no_private_place(self):
        self.assertIsNone(headless("Glob", pattern="*"))
        self.assertIsNone(headless("Glob", pattern="**/*.md"))
        self.assertIsNone(headless("Glob", pattern="projects/*/config/**"))
        self.assertIsNone(headless("Glob", pattern="**/config/*.rb"))

    def test_a_link_into_a_private_place_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            (root / "company").mkdir(parents=True)
            (root / "company" / "COMPANY.md").write_text("x")
            (root / "notes.md").symlink_to(root / "company" / "COMPANY.md")
            with mock.patch.object(guard, "ROOT", os.path.realpath(root)):
                self.assertEqual(headless("Read", _cwd=str(root), file_path="notes.md"),
                                 ("deny", guard.HEADLESS_PRIVATE))

    def test_the_rest_of_the_root_still_passes(self):
        self.assertIsNone(headless("Read", file_path="projects/app/.gitignore"))
        self.assertIsNone(headless("Read", file_path="steering/company-notes.md"))
        self.assertIsNone(headless("Read", file_path="companyx/notes.md"))
        self.assertIsNone(headless("Grep", pattern="x", path="projects/app", glob="*.md"))
        self.assertIsNone(headless("Grep", pattern="x"))
        self.assertIsNone(headless("Glob", pattern="projects/*/src/**"))

    def test_outside_a_headless_run_they_read_as_before(self):
        self.assertIsNone(call("Read", file_path=os.path.join(guard.ROOT, ".claude", "settings.local.json")))
        self.assertIsNone(call("Read", file_path=os.path.join(guard.ROOT, "company", "COMPANY.md")))
        self.assertIsNone(call("Read", file_path=os.path.join(guard.ROOT, ".inbox", "ideas.md")))
        self.assertIsNone(call("Read", file_path="projects/mirror.git/config"))

    def test_a_leftover_inbox_is_private(self):
        denied = ("deny", guard.HEADLESS_PRIVATE)
        self.assertEqual(headless("Read", file_path=".inbox/ideas.md"), denied)
        self.assertEqual(headless("Grep", pattern="x", path=".inbox"), denied)
        self.assertEqual(headless("Grep", pattern="x", glob="{.inbox,*.md}"), denied)
        self.assertEqual(headless("Glob", pattern=".inbox/*"), denied)
        self.assertEqual(headless("Glob", pattern="**/.inbox/*"), denied)

    def test_a_factory_s_folder_is_private(self):
        # Another factory's code, cloned for its commit: a headless reader never reads, searches or lists it.
        denied = ("deny", guard.HEADLESS_PRIVATE)
        self.assertEqual(headless("Read", file_path="factories/build-team/run.py"), denied)
        self.assertEqual(headless("Grep", pattern="x", path="factories"), denied)
        self.assertEqual(headless("Grep", pattern="x", glob="{factories,*.md}"), denied)
        self.assertEqual(headless("Glob", pattern="factories/*"), denied)
        self.assertEqual(headless("Glob", pattern="**/factories/*"), denied)
        self.assertIsNone(call("Read", file_path=os.path.join(guard.ROOT, "factories", "README.md")))

    def test_a_bare_repo_is_private_like_a_git_folder(self):
        denied = ("deny", guard.HEADLESS_PRIVATE)
        for path in ("projects/mirror.git/config", "projects/mirror.git/packed-refs", "projects/app/vendor/lib.git/config"):
            self.assertEqual(headless("Read", file_path=path), denied, path)
        self.assertEqual(headless("Grep", pattern="x", path="projects/mirror.git"), denied)
        for path in ("projects/app/src/widget.gitignore.md", "projects/app/.gitignore", "projects/app/.gitattributes"):
            self.assertIsNone(headless("Read", file_path=path), path)

    def test_a_glob_that_names_a_bare_repo_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            (root / "mirror.git").mkdir(parents=True)
            (root / "projects" / "app" / "lib.git").mkdir(parents=True)
            (root / "projects" / "backup.git").mkdir(parents=True)
            with mock.patch.object(guard, "ROOT", os.path.realpath(root)):
                for glob in ("{mirror.git,*.md}", "{mirror.gi?,*.md}", "**/mirror.git/*", "{lib.git,*.ts}",
                             "{other.git,*.md}", "{backup.gi?,**/backup.gi?/c*}", "{lib.gi?,*.ts}"):
                    self.assertEqual(headless("Grep", _cwd=str(root), pattern="x", glob=glob),
                                     ("deny", guard.HEADLESS_PRIVATE), glob)
                self.assertIsNone(headless("Grep", _cwd=str(root), pattern="x", glob="*.md"))

    def test_every_private_folder_reaches_each_list_the_guard_keeps(self):
        # Load the guard with one more private folder: each list built from PRIVATE_FOLDERS takes it in,
        # so a folder added in one place can't be left out of the search exclude or the refusals.
        source = (HOOKS / "guard.py").read_text()
        line = "PRIVATE_FOLDERS = ({})".format(", ".join('"{}"'.format(f) for f in guard.PRIVATE_FOLDERS))
        self.assertEqual(source.count(line), 1)
        probe = {"__name__": "guard_probe", "__file__": str(HOOKS / "guard.py")}
        exec(compile(source.replace(line, line[:-1] + ', "vault")'), "guard.py", "exec"), probe)
        for folder in guard.PRIVATE_FOLDERS + ("vault",):
            self.assertIn(folder, probe["EXCLUDE_PRIVATE"].strip("!/{}").split(","), folder)
            self.assertIn(folder, probe["PRIVATE_NAMES"], folder)
            self.assertIn(folder, probe["PRIVATE_ENTRIES"], folder)
            self.assertIn(folder + "/x", probe["PRIVATE_ENTRIES"], folder)
            self.assertIn(folder + "/", probe["HEADLESS_PRIVATE"], folder)
        self.assertEqual(guard.EXCLUDE_PRIVATE, "!/{company,local-data,.inbox,factories}")

    def test_a_headless_search_leaves_out_bare_repos_at_any_depth(self):
        with mock.patch.dict(os.environ, {"SANVIO_HEADLESS": "1"}):
            rewrite = guard.headless_rewrite
            self.assertEqual(rewrite({"tool_name": "Grep", "tool_input": {"pattern": "x", "path": "projects/app"}}),
                             {"pattern": "x", "path": "projects/app", "glob": "!/{company,local-data,.inbox,factories} !*.[gG][iI][tT]"})
            self.assertEqual(rewrite({"tool_name": "Grep", "tool_input": {"pattern": "x", "glob": "*.ts",
                                                                        "output_mode": "content"}}),
                             {"pattern": "x", "glob": "*.ts !/{company,local-data,.inbox,factories} !*.[gG][iI][tT]", "output_mode": "content"})
            self.assertIsNone(rewrite({"tool_name": "Read", "tool_input": {"file_path": "README.md"}}))
        with mock.patch.dict(os.environ):
            os.environ.pop("SANVIO_HEADLESS", None)
            os.environ.pop("HARNESS_HEADLESS", None)
            self.assertIsNone(guard.headless_rewrite({"tool_name": "Grep", "tool_input": {"pattern": "x"}}))

    def test_the_hook_passes_a_headless_search_on_changed_and_refuses_as_before(self):
        def hook(tool_input, headless_run=True):
            env = dict(os.environ)
            env.pop("SANVIO_HEADLESS", None)
            env.pop("HARNESS_HEADLESS", None)
            if headless_run:
                env["SANVIO_HEADLESS"] = "1"
            event = {"tool_name": "Grep", "tool_input": tool_input, "cwd": guard.ROOT}
            out = subprocess.run([sys.executable, str(HOOKS / "guard.py")], input=json.dumps(event),
                                 capture_output=True, text=True, env=env, timeout=30).stdout
            return json.loads(out)["hookSpecificOutput"] if out.strip() else None
        changed = hook({"pattern": "x", "path": "projects/app", "glob": "*.ts"})
        self.assertEqual(changed["updatedInput"]["glob"], "*.ts !/{company,local-data,.inbox,factories} !*.[gG][iI][tT]")
        self.assertNotIn("permissionDecision", changed)
        refused = hook({"pattern": "x", "glob": "{company,*.md}"})
        self.assertEqual(refused["permissionDecision"], "deny")
        self.assertNotIn("updatedInput", refused)
        self.assertIsNone(hook({"pattern": "x", "glob": "*.ts"}, headless_run=False))

    @unittest.skipUnless(shutil.which("rg"), "ripgrep isn't installed")
    def test_a_headless_search_of_the_root_leaves_out_the_private_folders_that_ignore_lets_back_in(self):
        # .ignore re-includes company/ and factories/ so an ordinary session can search them, and Claude
        # Code's Grep runs ripgrep with --hidden and --glob '!.git': measured, that searches both.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for name in (".gitignore", ".ignore"):
                (root / name).write_text((ROOT / name).read_text())
            for path in ("company/COMPANY.md", "factories/build-team/app.py", "local-data/x.md", ".inbox/x.md",
                         "steering/keep.md"):
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text("PROBEWORD\n")
            with mock.patch.dict(os.environ, {"SANVIO_HEADLESS": "1"}):
                glob = guard.headless_rewrite({"tool_name": "Grep", "tool_input": {"pattern": "PROBEWORD"}})["glob"]
            args = ["rg", "-l", "--hidden", "--glob", "!.git"]
            for part in glob.split():
                args += ["--glob", part]
            found = subprocess.run(args + ["PROBEWORD", "."], cwd=root, capture_output=True, text=True).stdout
            self.assertIn("./steering/keep.md", found.split())
            for private in ("company/", "factories/", "local-data/", ".inbox/"):
                self.assertFalse([path for path in found.split() if path.startswith("./" + private)], found)

    def test_the_root_ignores_bare_repos(self):
        self.assertIn("*.git/", (ROOT / ".gitignore").read_text().splitlines())


class Confined(unittest.TestCase):
    """A caller project's build agent (SANVIO_CONFINE set to its worktree and its clone's .git): no file tool or
    shell path outside them, the sibling project's clone and the factory's loop.json above all (SPEC-003 AC-005).
    The layout is a made-up factory: the worktree outside it, as ~/.sanvio-loop keeps them, and two projects."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.factory = base / "factory"
        self.own = self.factory / "projects" / "a"
        self.sibling = self.factory / "projects" / "b"
        self.tree = base / "trees" / "a" / "issue-12"
        self.other_tree = base / "trees" / "b" / "issue-3"
        for folder in (self.own / ".git", self.sibling, self.tree, self.other_tree):
            folder.mkdir(parents=True)
        (self.sibling / "notes.txt").write_text("made-up text\n")
        (self.factory / "loop.json").write_text("{}\n")
        (self.tree / "app.py").write_text("x = 1\n")
        # The guard's root is the factory, as a copy of guard.py in the made-up factory would have it.
        root = mock.patch.object(guard, "ROOT", str(self.factory))
        root.start()
        self.addCleanup(root.stop)
        held = os.pathsep.join([str(self.tree), str(self.own / ".git")])
        env = mock.patch.dict(os.environ, dict(interactive_env(), SANVIO_UNATTENDED="1", SANVIO_CONFINE=held),
                              clear=True)
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, tool, **tool_input):
        return guard.decide({"tool_name": tool, "tool_input": tool_input, "cwd": str(self.tree)})

    def assertRefused(self, verdict, why):
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict[0], "deny")
        self.assertIn("SANVIO_CONFINE", verdict[1])
        self.assertIn(why, verdict[1])

    def test_a_file_tool_on_the_sibling_project_or_the_factory_is_refused(self):
        for tool in ("Read", "Edit", "Write", "MultiEdit"):
            for path in (self.sibling / "notes.txt", self.factory / "loop.json", self.other_tree / "x.py"):
                with self.subTest(tool=tool, path=path):
                    self.assertRefused(self.call(tool, file_path=str(path)), "held to its own worktree")
        self.assertRefused(self.call("NotebookEdit", notebook_path=str(self.sibling / "n.ipynb")), "worktree")
        self.assertRefused(self.call("Read", file_path="../../b/issue-3/x.py"), "worktree")
        self.assertRefused(self.call("Grep", pattern="made", path=str(self.sibling)), "worktree")
        self.assertRefused(self.call("Glob", pattern="*", path=str(self.factory)), "worktree")
        self.assertRefused(self.call("Glob", pattern="../../../factory/projects/b/*"), "worktree")
        self.assertRefused(self.call("Glob", pattern=str(self.sibling) + "/**"), "worktree")
        self.assertRefused(self.call("Glob", pattern="src/*/../../../x"), "worktree")

    def test_a_link_in_the_worktree_to_the_sibling_is_refused(self):
        (self.tree / "peek").symlink_to(self.sibling / "notes.txt")
        self.assertRefused(self.call("Read", file_path="peek"), "worktree")

    def test_its_own_worktree_and_the_clones_git_are_allowed(self):
        self.assertIsNone(self.call("Read", file_path=str(self.tree / "app.py")))
        self.assertIsNone(self.call("Read", file_path="app.py"))
        self.assertIsNone(self.call("Edit", file_path="src/new.py"))
        self.assertIsNone(self.call("Grep", pattern="x"))
        self.assertIsNone(self.call("Glob", pattern="**/*.py"))
        self.assertIsNone(self.call("Read", file_path=str(self.own / ".git" / "HEAD")))

    def test_its_own_session_folder_can_be_read_and_nothing_else_there(self):
        sessions = Path(os.path.expanduser("~")) / ".claude" / "projects"
        own = sessions / re.sub(r"[^A-Za-z0-9]", "-", str(self.tree))
        self.assertIsNone(self.call("Read", file_path=str(own / "s1" / "tool-results" / "out.txt")))
        self.assertRefused(self.call("Edit", file_path=str(own / "s1" / "x.txt")), "worktree")
        self.assertRefused(self.call("Read", file_path=str(sessions / "-elsewhere" / "s.jsonl")), "worktree")

    def test_a_shell_command_naming_the_sibling_or_the_factory_is_refused(self):
        for command in ("cat {}".format(self.sibling / "notes.txt"), "ls {}".format(self.factory),
                        "cd {} && cat notes.txt".format(self.sibling), "python3 -c 1 < {}".format(
                            self.factory / "loop.json"),
                        "cat ../../b/issue-3/x.py", "cat ~/.zshrc", "cat $HOME/notes", "cat ${HOME}/notes",
                        "cd ~", "cat /etc/passwd", "git --git-dir={}/.git log".format(self.sibling)):
            with self.subTest(command=command):
                self.assertRefused(self.call("Bash", command=command), "outside this build's worktree")

    def test_the_factory_stays_refused_when_it_sits_under_temp(self):
        # This layout is itself under temp, which the shell may name: the factory's root still wins.
        self.assertTrue(guard.within(str(self.factory), guard.tool_paths()))
        self.assertRefused(self.call("Bash", command="cat {}".format(self.sibling / "notes.txt")), "outside")

    def test_ordinary_build_commands_and_system_paths_are_allowed(self):
        for command in ("python3 -m unittest discover -s tests", "git status", "git log -1", "ls -la",
                        "cat {}".format(self.tree / "app.py"), "cat app.py", "/usr/bin/env python3 -V",
                        "ls /usr/bin", "echo hi > /dev/null", "PATH=/usr/bin:/bin ls", "ls /",
                        "curl -sS https://pypi.org/simple/requests/", "grep -rn '/api/users' .",
                        "awk '/^x/ {print}' app.py", "node -e '1 // 2'", "echo $((4 / 2))",
                        "mktemp -d {}/x.XXXX".format(tempfile.gettempdir()), "ls ~/.pyenv/versions",
                        "git -C {} log -1".format(self.own / ".git")):
            with self.subTest(command=command):
                self.assertIsNone(self.call("Bash", command=command))

    def test_credentials_are_still_refused_inside(self):
        self.assertEqual(self.call("Read", file_path=str(self.tree / ".env"))[0], "deny")
        self.assertEqual(self.call("Bash", command="cat .env")[0], "deny")

    def test_unset_or_empty_the_guard_is_as_it_was(self):
        for value in (None, ""):
            env = {k: v for k, v in os.environ.items() if k != "SANVIO_CONFINE"}
            if value is not None:
                env["SANVIO_CONFINE"] = value
            with self.subTest(value=value), mock.patch.dict(os.environ, env, clear=True):
                self.assertIsNone(guard.confined_folders())
                self.assertIsNone(self.call("Read", file_path=str(self.sibling / "notes.txt")))
                self.assertIsNone(self.call("Glob", pattern="*", path=str(self.factory)))
                self.assertIsNone(self.call("Bash", command="cat {}".format(self.sibling / "notes.txt")))
                self.assertIsNone(self.call("Bash", command="cat ~/.zshrc"))

    def test_the_hook_refuses_the_sibling_end_to_end(self):
        event = {"tool_name": "Read", "tool_input": {"file_path": str(self.sibling / "notes.txt")},
                 "cwd": str(self.tree)}
        result = subprocess.run([sys.executable, str(HOOKS / "guard.py")], input=json.dumps(event),
                                capture_output=True, text=True, env=dict(os.environ), timeout=30)
        out = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", guard.CONFINED_OUTSIDE))


class SessionStart(unittest.TestCase):
    def test_all_passing_says_nothing(self):
        self.assertIsNone(session_start.report([("PASS", "python 3.12", None)]))

    def test_a_fail_leads_the_message(self):
        payload = session_start.report([
            ("WARN", "company: no company record yet", "Run /orientation"),
            ("FAIL", "hooks: core.hooksPath is not set", "git config core.hooksPath .githooks"),
        ])
        self.assertIn("core.hooksPath is not set", payload["systemMessage"])
        self.assertIn("+1 more", payload["systemMessage"])
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("git config core.hooksPath .githooks", context)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "SessionStart")

    LOG_OFF = ("The usage log is off for this session; unset SANVIO_USAGE_LOG and start a new session "
               "to turn it back on.")

    def test_with_the_log_off_and_all_passing_it_says_only_that_the_log_is_off(self):
        payload = session_start.report([("PASS", "python 3.12", None)], log_off=True)
        self.assertEqual(payload, {"systemMessage": "[usage] " + self.LOG_OFF})

    def test_with_the_log_on_all_passing_still_says_nothing(self):
        self.assertIsNone(session_start.report([("PASS", "python 3.12", None)], log_off=False))

    def test_with_the_log_off_a_fail_still_leads_and_the_log_off_comes_after(self):
        payload = session_start.report([
            ("PASS", "python 3.12", None),
            ("FAIL", "hooks: core.hooksPath is not set", "git config core.hooksPath .githooks"),
        ], log_off=True)
        message = payload["systemMessage"]
        self.assertTrue(message.startswith("[setup] hooks: core.hooksPath is not set"), message)
        self.assertTrue(message.endswith(self.LOG_OFF), message)
        self.assertIn("git config core.hooksPath .githooks", payload["hookSpecificOutput"]["additionalContext"])

    def test_an_old_state_folder_is_moved_and_said_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".harness" / "factories").mkdir(parents=True)
            first = session_start.startup(Path(tmp))
            self.assertTrue((Path(tmp) / ".sanvio" / "factories").is_dir())
            self.assertFalse((Path(tmp) / ".harness").exists())
            self.assertIn("moved .harness/ to .sanvio/", first["hookSpecificOutput"]["additionalContext"])
            again = session_start.startup(Path(tmp)) or {}
            self.assertNotIn("moved .harness/", json.dumps(again))

    def test_a_move_that_fails_is_said_with_its_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".harness").mkdir()
            with mock.patch("os.rename", side_effect=PermissionError(13, "Permission denied")):
                payload = session_start.startup(Path(tmp))
            self.assertIn("couldn't move .harness/ to .sanvio/ (Permission denied)",
                          payload["hookSpecificOutput"]["additionalContext"])

    def test_the_hook_runs_and_prints_json_or_nothing(self):
        out = subprocess.run([sys.executable, str(HOOKS / "session_start.py")],
                             capture_output=True, text=True, check=True).stdout
        if out:
            self.assertIn("systemMessage", json.loads(out))


if __name__ == "__main__":
    unittest.main()
