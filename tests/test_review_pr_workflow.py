"""Run with: python3 -m unittest discover -s tests"""
import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "examples" / "ci" / "review-pr.yml"
SECRET_REF = re.compile(r"\$\{\{ secrets\.[A-Z][A-Z0-9_]* \}\}")
KEY_SHAPES = re.compile(r"sk-ant|ghp_|gho_|github_pat_|AKIA[0-9A-Z]{8}|-----BEGIN")


def code(text):
    """The file without its comments, which explain the rules and so name them."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def block(text, key):
    """The indented lines under a top-level `key:`, as a list of stripped lines."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^{}:\s*$".format(re.escape(key)), line):
            out = []
            for follow in lines[i + 1:]:
                if follow.strip() and not follow.startswith(" "):
                    break
                if follow.strip():
                    out.append(follow.strip())
            return out
    return None


def run_lines(text):
    """Every line inside a `run:` block, where an expression is a script injection."""
    out, indent = [], None
    for line in text.splitlines():
        if indent is not None:
            if not line.strip() or len(line) - len(line.lstrip()) > indent:
                out.append(line)
                continue
            indent = None
        if re.match(r"^\s*run:\s*[|>]", line):
            indent = len(line) - len(line.lstrip())
    return out


def branch(script, name):
    """The body of a `name)` branch of a shell case, up to its `;;`, or None."""
    match = re.search(r"^\s*{}\)\s*\n(.*?)^\s*;;".format(re.escape(name)), script, re.M | re.S)
    return match.group(1) if match else None


class ReviewPrWorkflow(unittest.TestCase):
    def setUp(self):
        self.assertTrue(WORKFLOW.is_file(), "examples/ci/review-pr.yml doesn't exist")
        self.text = WORKFLOW.read_text()
        self.code = code(self.text)

    def scope(self):
        return self.code.split("id: scope", 1)[1].split("- uses:", 1)[0]

    def steps(self):
        """Each step under the job as (name, text), the name '' for one without."""
        body = self.code.split("\n    steps:\n", 1)[1]
        out = []
        for text in re.split(r"^(?=      - )", body, flags=re.M):
            if not text.strip():
                continue
            name = re.search(r"^      (?:- |  )name: \"?(.*?)\"?$", text, re.M)
            out.append((name.group(1) if name else "", text))
        return out

    def step(self, name):
        found = [text for each, text in self.steps() if each == name]
        self.assertEqual(len(found), 1, "no single step named " + name)
        return found[0]

    def run_step(self, name, **env):
        """Run a step's script as Actions would. Returns it, its outputs and what it added to the env."""
        script = self.step(name).split("run: |\n", 1)[1]
        with tempfile.TemporaryDirectory() as tmp:
            output, added = Path(tmp) / "output", Path(tmp) / "env"
            output.touch()
            added.touch()
            result = subprocess.run(
                ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", textwrap.dedent(script)],
                env={"PATH": os.environ["PATH"], "HEAD_REPO": "o/r", "THIS_REPO": "o/r", "REVIEWER": "claude",
                     "REVIEW_MODEL": "", "ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "",
                     "GITHUB_OUTPUT": str(output), "GITHUB_ENV": str(added), **env},
                capture_output=True, text=True)
            return result, output.read_text(), added.read_text()

    def run_scope(self, reviewer, **env):
        return self.run_step("Skip a pull request from a fork", REVIEWER=reviewer, **env)[:2]

    def test_it_runs_on_pull_request_and_never_the_target_variant(self):
        self.assertNotIn("pull_request_target", self.text)
        on = block(self.code, "on")
        self.assertIsNotNone(on, "no top-level on: block")
        self.assertIn("pull_request:", on)
        types = [line for line in on if line.startswith("types:")]
        self.assertEqual(len(types), 1, "pull_request needs one types: list")
        for kind in ("opened", "synchronize", "reopened"):
            self.assertIn(kind, types[0])

    def test_it_runs_on_nothing_but_pull_request(self):
        on = block(self.code, "on")
        triggers = [line for line in on if re.match(r"^[a-z_]+:", line) and not line.startswith("types:")]
        self.assertEqual(triggers, ["pull_request:"])

    def test_permissions_are_read_contents_and_write_comments_only(self):
        permissions = block(self.code, "permissions")
        self.assertIsNotNone(permissions, "no top-level permissions: block")
        self.assertEqual(sorted(permissions), ["contents: read", "pull-requests: write"])
        self.assertNotIn("contents: write", self.text)
        self.assertNotIn("write-all", self.text)

    def test_no_job_widens_the_permissions(self):
        self.assertEqual(len(re.findall(r"^\s*permissions:", self.code, re.M)), 1)

    def test_secrets_are_only_ever_referenced_by_name(self):
        for number, line in enumerate(self.text.splitlines(), 1):
            leftover = SECRET_REF.sub("", line)
            self.assertNotIn("secrets.", leftover,
                             "line {}: reference a secret as ${{{{ secrets.NAME }}}}".format(number))
        self.assertTrue(SECRET_REF.search(self.code), "the workflow references no secret")
        self.assertIsNone(KEY_SHAPES.search(self.text), "something in the file looks like a key")
        for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            self.assertIn("${{ secrets." + name + " }}", self.code)

    def test_a_pull_request_from_a_fork_skips_with_a_notice(self):
        self.assertIn("github.event.pull_request.head.repo.full_name", self.code)
        self.assertIn("::notice::", self.code)

    def test_a_pull_request_without_the_secret_skips_instead_of_failing(self):
        scope = self.code.split("id: scope", 1)[1].split("- uses:", 1)[0]
        self.assertIn("${{ secrets.ANTHROPIC_API_KEY }}", scope)
        self.assertRegex(scope, r'-z "\$ANTHROPIC_API_KEY"')

    def test_the_agent_runs_restricted_with_read_tools_only(self):
        review = self.code.split("Run the review-pr skill", 1)[1].split("Post the report", 1)[0]
        call = re.search(r"claude -p[^<]*", review)
        self.assertIsNotNone(call, "no claude -p call")
        flags = call.group(0).split()
        for flag in ("--restricted", "--strict-mcp-config"):
            self.assertIn(flag, flags, flag + " keeps the agent inside the checkout")
        self.assertEqual(flags[flags.index("--tools") + 1], "Read,Grep,Glob")
        for loose in ("--allowedTools", "--setting-sources", "--dangerously-skip-permissions"):
            self.assertNotIn(loose, review)

    def test_the_diff_reaches_the_agent_in_the_prompt(self):
        review = self.code.split("Run the review-pr skill", 1)[1].split("Post the report", 1)[0]
        self.assertIn('git diff "origin/$BASE_REF...HEAD" > "$RUNNER_TEMP/diff.patch"', review)
        self.assertRegex(review, r'head -c \d+ "\$RUNNER_TEMP/diff\.patch" >> "\$RUNNER_TEMP/prompt\.md"')
        self.assertNotIn("| head", review, "a pipe into head fails under pipefail on a big diff")

    def test_a_failed_run_says_why_only_after_the_key_check(self):
        review = self.code.split("Run the review-pr skill", 1)[1].split("Post the report", 1)[0]
        self.assertIn("code=$?", review)
        self.assertLess(review.index('grep -qF -e "$ANTHROPIC_API_KEY"'), review.index('head -c 2000 "$RUNNER_TEMP/report.md"'))

    def test_the_cli_is_pinned(self):
        self.assertRegex(self.code, r"npm install -g @anthropic-ai/claude-code@\d+\.\d+\.\d+")

    def test_a_report_holding_the_key_is_not_posted(self):
        review = self.code.split("Run the review-pr skill", 1)[1].split("Post the report", 1)[0]
        self.assertIn('grep -qF -e "$ANTHROPIC_API_KEY"', review)

    def test_no_expression_is_expanded_inside_a_script(self):
        self.assertTrue(run_lines(self.code), "found no run: blocks to check")
        for line in run_lines(self.code):
            self.assertNotIn("${{", line, "pass it through env: and read it as a variable")

    def test_the_skill_points_at_the_example(self):
        skill = (ROOT / "skills" / "review-pr" / "SKILL.md").read_text()
        self.assertIn("examples/ci/review-pr.yml", skill)

    def test_the_reviewer_defaults_to_claude(self):
        self.assertIn("REVIEWER: ${{ vars.REVIEWER || 'claude' }}", self.code)
        self.assertIn("REVIEW_MODEL: ${{ vars.REVIEW_MODEL }}", self.code)

    def test_an_unknown_reviewer_fails_and_names_the_three(self):
        other = branch(self.scope(), "*")
        self.assertIsNotNone(other, "the scope step's case has no *) branch")
        self.assertIn("::error::", other)
        self.assertIn("claude, codex or ollama", other)
        self.assertRegex(other, r"exit [1-9]")

    def test_the_reviewer_is_read_in_any_case(self):
        for value in ("claude", "Claude", "codex", "CODEX", "ollama", "Ollama"):
            result, output = self.run_scope(value, ANTHROPIC_API_KEY="a", OPENAI_API_KEY="o", REVIEW_MODEL="m")
            self.assertEqual(result.returncode, 0, value + ": " + result.stdout)
            self.assertIn("review=true", output, value)
        result, output = self.run_scope("gpt")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("claude, codex or ollama", result.stdout)
        self.assertNotIn("review=true", output)

    def test_a_missing_key_skips_and_a_missing_model_fails(self):
        for name, key in (("Claude", "ANTHROPIC_API_KEY"), ("Codex", "OPENAI_API_KEY")):
            result, _, added = self.run_step("Skip when {} has no key".format(name))
            self.assertEqual(result.returncode, 0, name)
            self.assertIn("REVIEW_SKIPPED=true", added, name)
            self.assertIn("::notice::", result.stdout, name)
            result, _, added = self.run_step("Skip when {} has no key".format(name), **{key: "k"})
            self.assertEqual(result.returncode, 0, name)
            self.assertNotIn("REVIEW_SKIPPED", added, name)
        result, output = self.run_scope("ollama")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("review=true", output)

    def test_a_skipped_review_runs_nothing_after_the_key_checks(self):
        names = [name for name, _ in self.steps()]
        for name, text in self.steps()[names.index("Skip when Codex has no key") + 1:]:
            self.assertIn("env.REVIEW_SKIPPED != 'true'", text, name or "the checkout")
        for name, reviewer in (("Claude", "claude"), ("Codex", "codex")):
            self.assertIn("env.REVIEWER == '{}'".format(reviewer), self.step("Skip when {} has no key".format(name)))

    def test_codex_runs_read_only_and_its_commands_get_no_environment(self):
        call = re.search(r"codex exec[^<]*", self.step("Run the review-pr skill on Codex"))
        self.assertIsNotNone(call, "no codex exec call in the Codex step")
        self.assertIn("--sandbox read-only", call.group(0))
        self.assertIn("-c shell_environment_policy.inherit=none", call.group(0))
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", self.code)

    def test_only_codex_s_last_message_is_posted(self):
        codex = self.step("Run the review-pr skill on Codex")
        self.assertIn('--output-last-message "$RUNNER_TEMP/report.md"', codex)
        self.assertIn('> "$RUNNER_TEMP/codex.log" 2>&1', codex)
        self.assertNotIn("codex.log", self.step("Post the report as one comment"))

    def test_codex_is_pinned(self):
        self.assertRegex(self.code, r"npm install -g @openai/codex@\d+\.\d+\.\d+(\s|$)")

    def test_codex_without_its_key_skips_instead_of_failing(self):
        codex = self.step("Skip when Codex has no key")
        self.assertRegex(codex, r'-z "\$OPENAI_API_KEY"')
        self.assertIn("${{ secrets.OPENAI_API_KEY }}", self.scope())

    def test_a_codex_report_or_log_holding_the_key_is_not_posted(self):
        codex = self.step("Run the review-pr skill on Codex")
        self.assertIn('grep -qF -e "$OPENAI_API_KEY" "$RUNNER_TEMP/report.md" "$RUNNER_TEMP/codex.log"', codex)
        self.assertLess(self.code.index('grep -qF -e "$OPENAI_API_KEY"'), self.code.index("Post the report"))

    def test_each_reviewer_s_step_holds_only_its_own_key(self):
        expected = {
            "Run the review-pr skill: build the prompt": set(),
            "Run the review-pr skill on Claude": {"ANTHROPIC_API_KEY"},
            "Run the review-pr skill on Codex": {"OPENAI_API_KEY"},
            "Run the review-pr skill on Ollama": set(),
        }
        for name, keys in expected.items():
            self.assertEqual(set(re.findall(r"secrets\.(\w+)", self.step(name))), keys, name)
        for name, reviewer in (("Claude", "claude"), ("Codex", "codex"), ("Ollama", "ollama")):
            self.assertIn("env.REVIEWER == '{}'".format(reviewer), self.step("Run the review-pr skill on " + name))
        holding = [name for name, text in self.steps() if "secrets." in text]
        self.assertEqual(sorted(holding), ["Run the review-pr skill on Claude", "Run the review-pr skill on Codex",
                                           "Skip when Claude has no key", "Skip when Codex has no key"])
        self.assertEqual(set(re.findall(r"secrets\.(\w+)", self.step("Skip when Claude has no key"))),
                         {"ANTHROPIC_API_KEY"})
        self.assertEqual(set(re.findall(r"secrets\.(\w+)", self.step("Skip when Codex has no key"))),
                         {"OPENAI_API_KEY"})

    def test_every_step_holding_a_key_checks_its_output_for_it(self):
        for name, text in self.steps():
            if name.startswith("Skip when"):
                continue
            for key in re.findall(r"secrets\.(\w+)", text):
                self.assertIn('grep -qF -e "${}"'.format(key), text, name)

    def test_ollama_runs_a_named_model_on_a_self_hosted_runner_with_no_key(self):
        self.assertRegex(self.code, r"runs-on: \$\{\{ vars\.REVIEWER == 'ollama' && "
                                    r"fromJSON\('\[\"self-hosted\",\"ollama\"\]'\) \|\| 'ubuntu-latest' \}\}")
        ollama = self.step("Run the review-pr skill on Ollama")
        self.assertRegex(ollama, r'ollama run "\$REVIEW_MODEL"')
        self.assertNotIn("secrets.", ollama)
        self.assertNotIn("API_KEY", ollama)
        required = branch(self.scope(), "ollama")
        self.assertIsNotNone(required, "the scope step's case has no ollama) branch")
        self.assertRegex(required, r'-z "\$REVIEW_MODEL"')
        self.assertIn("::error::", required)
        self.assertRegex(required, r"exit [1-9]")

    def test_the_header_names_all_three_reviewers(self):
        header = self.text.split("\nname:", 1)[0]
        for word in ("Claude", "Codex", "Ollama", "REVIEWER", "REVIEW_MODEL", "OPENAI_API_KEY", "self-hosted"):
            self.assertIn(word, header)


CALLED = ROOT / ".github" / "workflows" / "review-pr.yml"
SKIP = "Skip when only skip-paths files changed"
SKIP_DOCS = "docs/**\npackage-lock.json\n"


def git_env(tmp):
    """An environment that keeps the machine's own git config out of the test."""
    return {"PATH": os.environ["PATH"], "TMPDIR": tmp, "HOME": tmp, "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def write(head, *names):
    for name in names:
        path = head / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("changed " + name + "\n")


class SkipPaths(unittest.TestCase):
    """The called workflow's skip-paths step, run on a real base and head commit."""
    steps = ReviewPrWorkflow.steps
    step = ReviewPrWorkflow.step

    def setUp(self):
        self.assertTrue(CALLED.is_file(), ".github/workflows/review-pr.yml doesn't exist")
        self.text = CALLED.read_text()
        self.code = code(self.text)

    def names(self):
        return [name for name, _ in self.steps()]

    def skip_with(self, patterns, change):
        """Run the step on a pull request that `change(head)` makes. Returns its result and what it added to the env."""
        with tempfile.TemporaryDirectory() as tmp:
            env = git_env(tmp)
            head = Path(tmp) / "head"
            head.mkdir()

            def git(*args):
                return subprocess.run(["git", "-C", str(head), *args], env=env, check=True,
                                      capture_output=True, text=True).stdout.strip()

            git("init", "-q")
            (head / "src").mkdir()
            (head / "src" / "x.py").write_text("def x():\n    return 'the same in both places'\n")
            (head / "README.md").write_text("base\n")
            git("add", "-A")
            git("commit", "-q", "-m", "base")
            base = git("rev-parse", "HEAD")
            change(head)
            git("add", "-A")
            git("commit", "-q", "--allow-empty", "-m", "head")
            added = Path(tmp) / "env"
            added.touch()
            script = self.step(SKIP).split("run: |\n", 1)[1]
            result = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", textwrap.dedent(script)],
                                    cwd=tmp, env={**env, "SKIP_PATHS": patterns, "BASE_SHA": base,
                                                  "GITHUB_ENV": str(added)},
                                    capture_output=True, text=True)
            return result, added.read_text()

    def test_the_input_is_optional_and_empty_by_default(self):
        on = self.code.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        block = re.search(r"^      skip-paths:\n((?:        .*\n)+)", on, re.M)
        self.assertIsNotNone(block, "no skip-paths input")
        lines = [line.strip() for line in block.group(1).splitlines()]
        for line in ("required: false", "default: ''", "type: string"):
            self.assertIn(line, lines)
        self.assertIn("SKIP_PATHS: ${{ inputs.skip-paths }}", self.step(SKIP))

    def test_without_patterns_the_review_runs_and_says_nothing(self):
        result, added = self.skip_with("", lambda head: write(head, "docs/a.md"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(added, "")
        self.assertNotIn("::notice::", result.stdout)

    def test_blank_lines_alone_are_no_patterns(self):
        result, added = self.skip_with("\n  \n\t\n", lambda head: write(head, "docs/a.md"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("REVIEW_SKIPPED", added)
        self.assertNotIn("::notice::", result.stdout)

    def test_every_file_matching_skips_with_a_notice_naming_the_patterns(self):
        result, added = self.skip_with(SKIP_DOCS, lambda head: write(head, "docs/a.md", "docs/api/b.md",
                                                                     "package-lock.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(added, "REVIEW_SKIPPED=true\n")
        notice = [line for line in result.stdout.splitlines() if line.startswith("::notice::")]
        self.assertEqual(len(notice), 1, result.stdout)
        for pattern in ("docs/**", "package-lock.json"):
            self.assertIn(pattern, notice[0])

    def test_one_file_that_matches_nothing_reviews(self):
        result, added = self.skip_with(SKIP_DOCS, lambda head: write(head, "docs/a.md", "package-lock.json",
                                                                     "src/app.py"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("REVIEW_SKIPPED", added)
        self.assertNotIn("::notice::", result.stdout)

    def test_code_renamed_into_a_skipped_path_reviews(self):
        def rename(head):
            (head / "docs").mkdir()
            (head / "src" / "x.py").rename(head / "docs" / "x.py")
        result, added = self.skip_with(SKIP_DOCS, rename)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("REVIEW_SKIPPED", added)

    def test_a_pull_request_that_changes_nothing_reviews(self):
        result, added = self.skip_with(SKIP_DOCS, lambda head: None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("REVIEW_SKIPPED", added)

    def test_the_step_holds_no_secret_and_no_token(self):
        skip = self.step(SKIP)
        for word in ("secrets.", "GH_TOKEN", "github.token"):
            self.assertNotIn(word, skip)

    def test_it_runs_after_the_head_checkout_and_before_any_credential_is_used(self):
        names = self.names()
        at = names.index(SKIP)
        self.assertLess(names.index("Check out the pull request's head"), at)
        self.assertLess(at, names.index("Remove the pull request's own rules"))
        holding = [name for name, text in self.steps()
                   if re.search(r"secrets\.(ANTHROPIC_API_KEY|CLAUDE_CODE_OAUTH_TOKEN)|github\.token", text)]
        before = [name for name in holding if names.index(name) < at]
        self.assertEqual(before, ["Skip when Claude has no key"], "only the key check, which reads no file, runs first")
        self.assertTrue([name for name in holding if names.index(name) > at], "no credential step after the skip")

    def test_a_skip_runs_nothing_after_it(self):
        names = self.names()
        after = self.steps()[names.index(SKIP) + 1:]
        for name in ("Run the review-pr skill on Claude", "Grade the review", "Post the report as one comment"):
            self.assertIn(name, [each for each, _ in after])
        for name, text in after:
            if_line = next((line for line in text.splitlines() if line.strip().startswith("if:")), "")
            self.assertIn("env.REVIEW_SKIPPED != 'true'", if_line, name)


if __name__ == "__main__":
    unittest.main()
