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


REUSABLE = ROOT / ".github" / "workflows" / "review-pr.yml"
TEMPLATE = ROOT / "examples" / "ci" / "bedrock-review-role.yml"
AWS_ACTION_SHA = "e1253824e5c10ff9df46874f81ed3ec929e19cfd"
SKIP = "Skip when Claude has no key"
ASSUME = "Assume the review role on AWS"
CLAUDE = "Run the review-pr skill on Claude"
CLEAR = "Clear the AWS credentials"
GRADE = "Grade the review"
POST = "Post the report as one comment"
USUAL_IF = "steps.scope.outputs.review == 'true' && env.REVIEW_SKIPPED != 'true'"
AWS_VALUES = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")
CLEARED = AWS_VALUES + ("AWS_REGION", "AWS_DEFAULT_REGION")


class BedrockReview(unittest.TestCase):
    """The reusable review's Bedrock path: an AWS role assumed through OIDC in place of a Claude key."""
    steps = ReviewPrWorkflow.steps
    step = ReviewPrWorkflow.step
    run_step = ReviewPrWorkflow.run_step

    def setUp(self):
        self.assertTrue(REUSABLE.is_file(), ".github/workflows/review-pr.yml doesn't exist")
        self.text = REUSABLE.read_text()
        self.code = code(self.text)

    def names(self):
        return [name for name, _ in self.steps()]

    def if_line(self, name):
        return next((line.strip() for line in self.step(name).splitlines() if line.strip().startswith("if:")), "")

    def review_with(self, report, **env):
        """Run the Claude step with a stand-in claude that writes `report`. Returns it and whether a report is left."""
        script = self.step(CLAUDE).split("run: |\n", 1)[1]
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            (bin_dir / "claude").write_text("#!/bin/sh\ncat > /dev/null\nprintf '%s\\n' \"$FAKE_REPORT\"\n")
            (bin_dir / "claude").chmod(0o755)
            (Path(tmp) / "prompt.md").write_text("review\n")
            result = subprocess.run(
                ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", textwrap.dedent(script)], cwd=tmp,
                env={"PATH": f"{bin_dir}:{os.environ['PATH']}", "RUNNER_TEMP": tmp, "GITHUB_WORKSPACE": tmp,
                     "FAKE_REPORT": report, **env},
                capture_output=True, text=True)
            return result, (Path(tmp) / "report.md").exists()

    def test_it_takes_the_role_and_the_region_as_optional_inputs(self):
        on = self.code.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        for name in ("aws-role-arn", "aws-region"):
            self.assertRegex(on, r"      {}:\n        description: .*\n        required: false\n"
                                 r"        default: ''\n        type: string\n".format(name))
        self.assertIn("CLAUDE_CODE_USE_BEDROCK: ${{ inputs.aws-role-arn != '' && '1' || '' }}", self.step(CLAUDE))

    def test_the_aws_action_is_pinned_to_v6_3_0_and_holds_no_secret(self):
        assume = self.step(ASSUME)
        pins = re.findall(r"uses: aws-actions/configure-aws-credentials@([0-9a-f]{40}) # v6\.3\.0$", assume, re.M)
        self.assertEqual(pins, [AWS_ACTION_SHA])
        self.assertNotIn("secrets.", assume)
        for line in ("role-to-assume: ${{ inputs.aws-role-arn }}", "aws-region: ${{ inputs.aws-region }}",
                     "role-duration-seconds: 900"):
            self.assertIn(line, assume)
        self.assertEqual(self.text.count("aws-actions/configure-aws-credentials@"), 1)

    def test_the_role_is_assumed_only_when_given_and_directly_before_the_review(self):
        self.assertEqual(self.if_line(ASSUME), "if: " + USUAL_IF + " && inputs.aws-role-arn != ''")
        names = self.names()
        self.assertEqual(names.index(ASSUME) + 1, names.index(CLAUDE))

    def test_nothing_set_skips_with_a_notice_naming_all_three(self):
        result, _, added = self.run_step(SKIP)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REVIEW_SKIPPED=true", added)
        notice = next(line for line in result.stdout.splitlines() if line.startswith("::notice::"))
        for name in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "aws-role-arn"):
            self.assertIn(name, notice)

    def test_a_role_with_its_region_runs_the_review(self):
        result, _, added = self.run_step(SKIP, AWS_ROLE_ARN="arn:aws:iam::123456789012:role/r",
                                         AWS_REGION_INPUT="us-east-1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("REVIEW_SKIPPED", added)

    def test_a_role_without_a_region_fails_and_names_both(self):
        result, _, added = self.run_step(SKIP, AWS_ROLE_ARN="arn:aws:iam::123456789012:role/r")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("REVIEW_SKIPPED", added)
        error = next(line for line in result.stdout.splitlines() if line.startswith("::error::"))
        for name in ("aws-role-arn", "aws-region"):
            self.assertIn(name, error)

    def test_the_skip_step_reads_the_role_and_the_region(self):
        skip = self.step(SKIP)
        self.assertIn("AWS_ROLE_ARN: ${{ inputs.aws-role-arn }}", skip)
        self.assertIn("AWS_REGION_INPUT: ${{ inputs.aws-region }}", skip)

    def test_a_key_alone_still_runs_the_review_with_no_role(self):
        for name in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
            result, _, added = self.run_step(SKIP, **{name: "k"})
            self.assertEqual(result.returncode, 0, name + ": " + result.stdout + result.stderr)
            self.assertNotIn("REVIEW_SKIPPED", added, name)
            result, kept = self.review_with("Looks fine.", **{name: "cred-123", "CLAUDE_CODE_USE_BEDROCK": ""})
            self.assertEqual(result.returncode, 0, name + ": " + result.stdout + result.stderr)
            self.assertTrue(kept, name)

    def test_a_report_holding_an_aws_value_is_not_posted(self):
        for name in AWS_VALUES:
            result, kept = self.review_with("Looks fine. cred-123", **{name: "cred-123"})
            self.assertNotEqual(result.returncode, 0, name)
            self.assertFalse(kept, name)
            self.assertIn("::error::The report contained a credential, so it was not posted.", result.stdout, name)
            self.assertNotIn("cred-123", result.stdout + result.stderr, name)

    def test_a_clean_report_with_the_aws_values_set_is_kept(self):
        values = {name: "value-" + name for name in AWS_VALUES}
        result, kept = self.review_with("Looks fine.", CLAUDE_CODE_USE_BEDROCK="1", **values)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(kept)

    def test_the_clear_step_empties_all_five_values(self):
        result, _, added = self.run_step(CLEAR)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(added.splitlines(), [name + "=" for name in CLEARED])

    def test_the_clear_step_runs_after_the_review_and_before_the_grade_and_the_post(self):
        names = self.names()
        self.assertEqual(names.index(CLAUDE) + 1, names.index(CLEAR))
        self.assertLess(names.index(CLEAR), names.index(GRADE))
        self.assertLess(names.index(CLEAR), names.index(POST))
        self.assertEqual(self.if_line(CLEAR), "if: " + USUAL_IF)
        self.assertNotIn("secrets.", self.step(CLEAR))
        for name in (GRADE, POST):
            self.assertNotIn("AWS_", self.step(name), name)

    def test_the_header_says_how_the_bedrock_path_works(self):
        header = " ".join(self.text.split("\nname:", 1)[0].split())
        for words in ("aws-role-arn", "CLAUDE_CODE_USE_BEDROCK", "examples/ci/bedrock-review-role.yml",
                      "id-token: write"):
            self.assertIn(words, header)

    def template(self):
        self.assertTrue(TEMPLATE.is_file(), "examples/ci/bedrock-review-role.yml doesn't exist")
        return TEMPLATE.read_text()

    def test_the_template_trusts_one_repo_s_pull_requests_running_the_factory_s_review(self):
        text = self.template()
        self.assertNotIn("StringLike", text)
        self.assertIn("Action: sts:AssumeRoleWithWebIdentity", text)
        self.assertIn("Federated: !Ref GitHubOidcProviderArn", text)
        self.assertIn("StringEquals:", text)
        self.assertIn('"token.actions.githubusercontent.com:aud": sts.amazonaws.com', text)
        subs = re.findall(r'"token\.actions\.githubusercontent\.com:sub": !Sub "([^"]+)"', text)
        self.assertEqual(subs, ["repo:${ProductRepo}:pull_request:job_workflow_ref:"
                                "${FactoryRepo}/.github/workflows/review-pr.yml@${FactoryRef}"])
        self.assertNotIn("*", subs[0])
        self.assertIn("pull_request", subs[0])
        self.assertIn("review-pr.yml@${FactoryRef}", subs[0])

    def test_the_template_takes_its_four_parameters(self):
        text = self.template()
        parameters = text.split("\nParameters:\n", 1)[1].split("\nResources:\n", 1)[0]
        self.assertEqual(re.findall(r"^  (\w+):$", parameters, re.M),
                         ["ProductRepo", "FactoryRepo", "FactoryRef", "GitHubOidcProviderArn"])
        self.assertIn("Default: refs/heads/main", parameters)
        self.assertNotIn("AWS::IAM::OIDCProvider", text)

    def test_the_template_allows_only_invoking_anthropic_models(self):
        text = self.template()
        self.assertNotIn("bedrock:*", text)
        self.assertEqual(re.findall(r"^\s*- (bedrock:\S+)$", text, re.M),
                         ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"])
        self.assertEqual(re.findall(r"arn:aws:bedrock:[^\"\s]+", text),
                         ["arn:aws:bedrock:*::foundation-model/anthropic.*",
                          "arn:aws:bedrock:*:${AWS::AccountId}:inference-profile/*anthropic.*"])
        self.assertEqual(text.count("PolicyName:"), 1)
        self.assertNotIn("ManagedPolicyArns", text)
        self.assertNotIn("Resource: \"*\"", text)

    def test_the_template_says_what_it_trusts_and_holds_no_key(self):
        text = self.template()
        header = " ".join(line.lstrip("# ") for line in text.split("\nAWSTemplateFormatVersion", 1)[0].splitlines())
        for words in ("What it trusts", "pull_request", "review-pr.yml", "job_workflow_ref", "What it allows",
                      "Anthropic"):
            self.assertIn(words, header)
        self.assertIsNone(KEY_SHAPES.search(text), "something in the template looks like a key")
        self.assertIsNone(re.search(r"(?:AKIA|ASIA)[0-9A-Z]{16}", text))


if __name__ == "__main__":
    unittest.main()
