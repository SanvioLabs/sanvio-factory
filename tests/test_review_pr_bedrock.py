"""The Bedrock review, .github/workflows/review-pr-bedrock.yml, made from review-pr.yml by
scripts/bedrock_workflow.py (#647). Only its caller grants id-token: write, its review job checks out the
harness its own OIDC token names before anything else runs, and its role holds the code to the regions listed."""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_review_pr_workflow as single  # noqa: E402 (the import needs tests/ on the path first)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import bedrock_workflow  # noqa: E402

SOURCE = ROOT / ".github" / "workflows" / "review-pr.yml"
BEDROCK = ROOT / ".github" / "workflows" / "review-pr-bedrock.yml"
TEMPLATE = ROOT / "examples" / "ci" / "bedrock-review-role.yml"
README = ROOT / "examples" / "ci" / "README.md"
OWN = "Check this is the factory's own workflow"
HOLD = "Hold the agent to this harness"
ASSUME = "Assume the review role on AWS"
REVIEW = "Run the review-pr skill on Claude"
CLEAR = "Clear the AWS credentials"
SHA = "a" * 40
OWN_REF = "acme/factory/.github/workflows/review-pr-bedrock.yml@refs/heads/main"


def b64(part):
    return base64.urlsafe_b64encode(json.dumps(part).encode()).decode().rstrip("=")


def jwt(claims):
    """An unsigned stand-in token: the workflow reads the runner's own endpoint, so it checks the claims only."""
    return "{}.{}.signature".format(b64({"alg": "RS256"}), b64(claims))


def yaml_blocks(text):
    """The bodies of the ```yaml fences in a Markdown file, a fence indented inside a list item included."""
    return [textwrap.dedent(body) for _, body in re.findall(r"^( *)```yaml\n(.*?)^\1```", text, re.M | re.S)]


class FakeOidc:
    """A stand-in for the runner's token endpoint: it answers a bearer T request for the sts audience with a
    token holding `claims`, and anything else with a 403."""

    def __init__(self):
        self.claims = {}
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                ok = self.headers.get("Authorization") == "bearer T" and "&audience=sts.amazonaws.com" in self.path
                self.send_response(200 if ok else 403)
                self.end_headers()
                self.wfile.write(json.dumps({"value": jwt(fake.claims)}).encode())

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:{}/token?api-version=2.0".format(self.server.server_port)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class TheGeneratedWorkflow(unittest.TestCase):
    def test_the_committed_file_is_what_the_script_makes(self):
        self.assertEqual(BEDROCK.read_text(), bedrock_workflow.build(SOURCE.read_text(), BEDROCK.read_text()),
                         "run python3 scripts/bedrock_workflow.py")
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "bedrock_workflow.py"), "--check"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_an_anchor_gone_from_review_pr_stops_the_build_and_says_why(self):
        source = SOURCE.read_text()
        values = bedrock_workflow.pins(source)
        for number, (why, anchor, _) in enumerate(bedrock_workflow.EDITS, 1):
            for placeholder, value in values.items():
                anchor = anchor.replace(placeholder, value)
            with self.subTest(edit=number):
                with self.assertRaises(ValueError) as caught:
                    bedrock_workflow.build(source.replace(anchor, ""))
                said = str(caught.exception)
                # The CLI's version is read from the anchor edit 9 makes, so losing it trips that read first.
                if "versions of the Claude Code CLI" not in said:
                    self.assertIn("Edit {} of {} ({})".format(number, len(bedrock_workflow.EDITS), why), said)
                self.assertIn("scripts/bedrock_workflow.py", str(caught.exception))

    def test_a_dependabot_bump_to_either_file_regenerates_to_the_same_thing(self):
        source, current = SOURCE.read_text(), BEDROCK.read_text()
        old_checkout = bedrock_workflow.CHECKOUT.search(source).group(1)
        new_checkout = "actions/checkout@" + "b" * 40 + " # v9.9.9"
        bumped = bedrock_workflow.build(source.replace(old_checkout, new_checkout), current.replace(old_checkout, new_checkout))
        self.assertEqual(bumped, current.replace(old_checkout, new_checkout))
        old_aws = bedrock_workflow.AWS.search(current).group(1)
        new_aws = "aws-actions/configure-aws-credentials@" + "c" * 40 + " # v9.9.9"
        self.assertEqual(bedrock_workflow.build(source, current.replace(old_aws, new_aws)), current.replace(old_aws, new_aws))

    def test_it_says_its_generated_and_review_pr_yml_says_so_too(self):
        first = BEDROCK.read_text().splitlines()[0]
        self.assertIn("GENERATED from review-pr.yml by scripts/bedrock_workflow.py", first)
        header = SOURCE.read_text().split("\nname:", 1)[0]
        self.assertIn("review-pr-bedrock.yml, the review on Amazon Bedrock, is made from this file", " ".join(header.replace("#", "").split()))
        self.assertNotIn("ANTHROPIC_API_KEY", BEDROCK.read_text().split("\nname:", 1)[0])


class WhoGetsTheToken(unittest.TestCase):
    def setUp(self):
        self.code = single.code(BEDROCK.read_text())
        self.jobs = single.jobs(self.code)

    def test_review_pr_yml_and_its_caller_ask_for_no_id_token(self):
        self.assertNotIn("id-token", single.code(SOURCE.read_text()))
        self.assertNotIn("id-token", yaml_blocks(README.read_text())[0])

    def test_only_the_review_job_asks_for_id_token(self):
        self.assertEqual(sorted(single.block(self.code, "permissions")), ["contents: read", "pull-requests: write"])
        self.assertEqual(sorted(self.jobs), ["agents", "grade", "review"])
        for name in ("agents", "grade"):
            with self.subTest(job=name):
                self.assertNotIn("permissions:", self.jobs[name])
                self.assertNotIn("id-token", self.jobs[name])
        permissions = self.jobs["review"].split("    permissions:\n", 1)[1].split("    strategy:", 1)[0]
        self.assertEqual(sorted(line.strip() for line in permissions.splitlines() if line.strip()),
                         ["contents: read", "id-token: write", "pull-requests: write"])

    def test_it_takes_no_claude_credential(self):
        on = self.code.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        secrets = on.split("    secrets:\n", 1)[1]
        self.assertEqual(re.findall(r"^      ([A-Z_]+):", secrets, re.M), ["FACTORY_DEPLOY_KEY"])
        for name in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
            self.assertNotIn(name, self.code)

    def test_the_role_the_region_and_the_model_are_required(self):
        on = self.code.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        for name in ("aws-role-arn", "aws-region", "aws-model"):
            self.assertRegex(on, r"      {}:\n        description: .*\n        required: true\n"
                                 r"        type: string\n".format(name))


class TheReviewJob(unittest.TestCase):
    def setUp(self):
        self.code = single.code(BEDROCK.read_text())
        self.steps = single.job_steps(single.jobs(self.code)["review"])
        self.names = [name for name, _ in self.steps]

    def step(self, name):
        found = [text for each, text in self.steps if each == name]
        self.assertEqual(len(found), 1, "no single step named " + name)
        return found[0]

    STEPS = [OWN, "Check out the harness", "Say which harness commit reviews", HOLD,
             "Check out the pull request's base", "Check out the pull request's head",
             "Remove the pull request's own rules", "Install the Claude Code CLI",
             "Run the review-pr skill: build the prompt", ASSUME, REVIEW, CLEAR,
             "Check the report against its schema", "Post the report as one comment",
             "Open a thread per blocking finding"]

    def test_every_step_in_the_job_that_can_ask_for_a_session_is_one_decided_on(self):
        # A step review-pr.yml adds to its review job runs here too, where it can mint the token. Decide, then
        # add it here (the CTO review of #657).
        self.assertEqual(self.names, self.STEPS)
        uses = [re.search(r"uses: ([\w./-]+)@", text) for _, text in self.steps]
        self.assertEqual(sorted({match.group(1) for match in uses if match}),
                         ["actions/checkout", "aws-actions/configure-aws-credentials"])

    def test_the_agent_is_told_this_workflow_is_running_the_review(self):
        harness = self.step("Check out the harness")
        self.assertIn("/.github/workflows/review-pr-bedrock.yml", harness)
        self.assertNotIn("/.github/workflows/review-pr.yml", harness)
        prompt = self.step("Run the review-pr skill: build the prompt")
        self.assertIn("harness/.github/workflows/review-pr-bedrock.yml is the workflow running", prompt)
        self.assertNotIn("workflows/review-pr.yml", prompt)

    def test_its_first_step_is_the_identity_check_and_the_harness_is_what_it_names(self):
        self.assertEqual(self.names[:4], [OWN, "Check out the harness", "Say which harness commit reviews", HOLD])
        checkout = self.step("Check out the harness")
        self.assertIn("repository: ${{ steps.own.outputs.repo }}", checkout)
        self.assertIn("ref: ${{ steps.own.outputs.sha }}", checkout)
        self.assertNotIn("inputs.factory-repo", checkout)
        self.assertIn("id: own", self.step(OWN))

    def own(self, claims, factory_repo="acme/factory", token=True):
        fake = FakeOidc()
        self.addCleanup(fake.close)
        fake.claims = claims
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output"
            out.write_text("")
            env = {"FACTORY_REPO": factory_repo, "GITHUB_OUTPUT": str(out)}
            if token:
                env.update(ACTIONS_ID_TOKEN_REQUEST_URL=fake.url, ACTIONS_ID_TOKEN_REQUEST_TOKEN="T")
            done = single.run_script(self.step(OWN), tmp, **env)
            return done, out.read_text()

    def test_the_identity_check_passes_the_factorys_own_workflow_and_names_its_commit(self):
        for ref, repo in ((OWN_REF, "acme/factory"), (OWN_REF.replace("acme/factory", "Acme/Factory"), "acme/factory")):
            with self.subTest(ref=ref):
                done, out = self.own({"job_workflow_ref": ref, "job_workflow_sha": SHA}, repo)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(out, "repo={}\nsha={}\n".format(ref.split("/.github/")[0], SHA))
                self.assertIn("job_workflow_ref: " + ref, done.stdout)
                self.assertNotIn("signature", done.stdout + done.stderr)

    def test_the_identity_check_stops_anything_else(self):
        cases = {
            "factory-repo names another repo": ({"job_workflow_ref": OWN_REF, "job_workflow_sha": SHA},
                                                "evil/harness", "They have to be the same repo"),
            "the key workflow's token": ({"job_workflow_ref": OWN_REF.replace("review-pr-bedrock.yml", "review-pr.yml"),
                                          "job_workflow_sha": SHA}, "acme/factory", "isn't the factory's own workflow"),
            "no commit": ({"job_workflow_ref": OWN_REF}, "acme/factory", "isn't the factory's own workflow"),
            "a short commit": ({"job_workflow_ref": OWN_REF, "job_workflow_sha": "abc123"}, "acme/factory",
                               "isn't the factory's own workflow"),
        }
        for why, (claims, repo, said) in cases.items():
            with self.subTest(why):
                done, out = self.own(claims, repo)
                self.assertNotEqual(done.returncode, 0)
                self.assertIn(said, done.stdout)
                self.assertEqual(out, "")

    def test_the_identity_check_stops_without_a_token(self):
        done, out = self.own({}, token=False)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("has to grant id-token: write", done.stdout)
        self.assertEqual(out, "")

    def hold(self, tools="Read,Grep,Glob", file="harness/skills/review-pr/SKILL.md", name="review-pr",
             front="---\nname: review-pr\n---\n"):
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "harness" / "skills" / "review-pr"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(front + "Review it.\n")
            return single.run_script(self.step(HOLD), tmp, AGENT_NAME=name, AGENT_FILE=file, AGENT_TOOLS=tools)

    def test_the_agent_is_held_to_this_harness(self):
        done = self.hold()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        for why, kwargs, said in (
                ("a shell from the agents job", {"tools": "Read,Grep,Glob,Bash(env:*)"}, "Read, Grep and Glob only"),
                ("a file this harness doesn't have", {"file": "harness/agents/review-pr.md"}, "isn't in this workflow"),
                ("a name that isn't one", {"name": "../x"}, "isn't a skill's or an agent's name"),
                ("a ci-shell: line here", {"front": "---\nci-shell: env\n---\n"}, "has a ci-shell: line")):
            with self.subTest(why):
                done = self.hold(**kwargs)
                self.assertNotEqual(done.returncode, 0)
                self.assertIn(said, done.stdout)

    def test_the_cli_installs_with_every_script_off_but_its_own(self):
        install = self.step("Install the Claude Code CLI")
        version = re.search(r"claude-code@([0-9.]+)", single.code(SOURCE.read_text())).group(1)
        self.assertIn("npm install -g --ignore-scripts @anthropic-ai/claude-code@" + version, install)
        self.assertIn('cd "$(npm root -g)/@anthropic-ai/claude-code"', install)
        self.assertIn("node install.cjs", install)

    def test_the_role_is_assumed_directly_before_the_review_and_cleared_directly_after(self):
        at = self.names.index(REVIEW)
        self.assertEqual(self.names[at - 1:at + 2], [ASSUME, REVIEW, CLEAR])
        assume = self.step(ASSUME)
        pins = re.findall(r"uses: aws-actions/configure-aws-credentials@([0-9a-f]{40}) # v[0-9.]+$", assume, re.M)
        self.assertEqual(len(pins), 1, assume)
        self.assertNotIn("secrets.", assume)
        # As long as the job may run, so a long review doesn't outlive its session (the reviews of #657).
        self.assertIn("timeout-minutes: 30", single.jobs(self.code)["review"])
        for line in ("role-to-assume: ${{ inputs.aws-role-arn }}", "aws-region: ${{ inputs.aws-region }}",
                     "role-duration-seconds: 1800"):
            self.assertIn(line, assume)
        self.assertNotIn("if:", assume)
        clear = self.step(CLEAR)
        for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_REGION",
                     "AWS_DEFAULT_REGION"):
            self.assertIn(name, clear)

    def test_the_review_runs_on_bedrock_with_the_callers_model(self):
        review = self.step(REVIEW)
        for line in ("CLAUDE_CODE_USE_BEDROCK: '1'", "ANTHROPIC_MODEL: ${{ inputs.aws-model }}",
                     "ANTHROPIC_SMALL_FAST_MODEL: ${{ inputs.aws-model }}",
                     "ANTHROPIC_DEFAULT_HAIKU_MODEL: ${{ inputs.aws-model }}"):
            self.assertIn(line, review)

    def review_with(self, report, **env):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            (bin_dir / "claude").write_text("#!/bin/sh\ncat > /dev/null\nprintf '%s\\n' \"$FAKE_REPORT\"\n")
            (bin_dir / "claude").chmod(0o755)
            (Path(tmp) / "prompt.md").write_text("review\n")
            script = self.step(REVIEW).split("run: |\n", 1)[1]
            done = subprocess.run(
                ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", textwrap.dedent(script)], cwd=tmp,
                env={"PATH": "{}:{}".format(bin_dir, os.environ["PATH"]), "RUNNER_TEMP": tmp,
                     "GITHUB_WORKSPACE": tmp, "FAKE_REPORT": report, **env},
                capture_output=True, text=True)
            return done, (Path(tmp) / "report.json").exists()

    def test_a_report_holding_the_session_isnt_posted(self):
        session = {"AWS_ACCESS_KEY_ID": "ASIAEXAMPLEKEYID", "AWS_SECRET_ACCESS_KEY": "secret/value+1",
                   "AWS_SESSION_TOKEN": "session-token-value"}
        for name, value in session.items():
            with self.subTest(name=name):
                done, kept = self.review_with('{"verdict": "PASS", "summary": "' + value + '"}', **session)
                self.assertNotEqual(done.returncode, 0)
                self.assertIn("AWS session's credentials", done.stdout)
                self.assertFalse(kept)
        done, kept = self.review_with('{"verdict": "PASS"}', **session)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(kept)


class WhatTheAgentCanReach(unittest.TestCase):
    """Review of the reworked #657: base/ is whatever branch the pull request targets, which anyone who can push
    a branch can choose, so its links go too, and the CLI never holds the means to ask for a session."""
    setUp, step, review_with = TheReviewJob.setUp, TheReviewJob.step, TheReviewJob.review_with

    def test_links_go_from_base_and_head_and_base_keeps_its_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            for side in ("base", "head"):
                (Path(tmp) / side).mkdir()
                (Path(tmp) / side / "notes").symlink_to("/proc/self/environ")
                (Path(tmp) / side / "AGENTS.md").write_text("rules\n")
            done = single.run_script(self.step("Remove the pull request's own rules"), tmp)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            for side in ("base", "head"):
                self.assertFalse(os.path.lexists(Path(tmp) / side / "notes"), side)
            self.assertTrue((Path(tmp) / "base" / "AGENTS.md").is_file())
            self.assertFalse((Path(tmp) / "head" / "AGENTS.md").exists())

    def test_the_cli_runs_without_the_token_request_values(self):
        token = {"ACTIONS_ID_TOKEN_REQUEST_TOKEN": "request-token-value", "ACTIONS_ID_TOKEN_REQUEST_URL": "http://x"}
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            (bin_dir / "claude").write_text(
                '#!/bin/sh\ncat > /dev/null\nprintf \'{"verdict": "PASS", "seen": "%s%s"}\\n\' '
                '"${ACTIONS_ID_TOKEN_REQUEST_TOKEN:-none}" "${ACTIONS_ID_TOKEN_REQUEST_URL:-}"\n')
            (bin_dir / "claude").chmod(0o755)
            (Path(tmp) / "prompt.md").write_text("review\n")
            script = self.step(REVIEW).split("run: |\n", 1)[1]
            done = subprocess.run(
                ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", textwrap.dedent(script)], cwd=tmp,
                env={"PATH": "{}:{}".format(bin_dir, os.environ["PATH"]), "RUNNER_TEMP": tmp,
                     "GITHUB_WORKSPACE": tmp, **token}, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn('"seen": "none"', (Path(tmp) / "report.json").read_text())
        install = self.step("Install the Claude Code CLI")
        self.assertIn("env -u ACTIONS_ID_TOKEN_REQUEST_TOKEN -u ACTIONS_ID_TOKEN_REQUEST_URL node install.cjs", install)

    def test_a_report_holding_the_request_token_isnt_posted(self):
        done, kept = self.review_with('{"verdict": "PASS", "summary": "request-token-value"}',
                                      ACTIONS_ID_TOKEN_REQUEST_TOKEN="request-token-value")
        self.assertNotEqual(done.returncode, 0)
        self.assertFalse(kept)

    def test_nonessential_traffic_is_off(self):
        self.assertIn("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1'", self.step(REVIEW))


class TheAgentsJob(unittest.TestCase):
    def setUp(self):
        steps = single.job_steps(single.jobs(single.code(BEDROCK.read_text()))["agents"])
        self.steps = dict(steps)

    def resolve(self, front):
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "harness" / "skills" / "review-pr"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(front + "Review it.\n")
            out = Path(tmp) / "output"
            out.write_text("")
            done = single.run_script(self.steps["Resolve the agents"], tmp, AGENTS="review-pr",
                                     GITHUB_OUTPUT=str(out))
            return done, out.read_text()

    def test_an_agent_with_a_ci_shell_line_stops_the_run(self):
        done, out = self.resolve("---\nci-shell: env\n---\n")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Read, Grep and Glob only", done.stdout)
        self.assertNotIn("matrix=", out)

    def test_an_agent_without_one_gets_read_grep_and_glob(self):
        done, out = self.resolve("---\nname: review-pr\n---\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        matrix = json.loads(re.search(r"^matrix=(.*)$", out, re.M).group(1))
        self.assertEqual([each["tools"] for each in matrix], ["Read,Grep,Glob"])

    def test_dependabot_skips_with_no_deploy_key_and_anyone_else_goes_on_to_fail(self):
        step = self.steps["Skip a Dependabot pull request"]
        for actor, skipped in (("dependabot[bot]", True), ("someone", False)):
            with self.subTest(actor=actor), tempfile.TemporaryDirectory() as tmp:
                env_file = Path(tmp) / "env"
                env_file.write_text("")
                done = single.run_script(step, tmp, FACTORY_DEPLOY_KEY="", ACTOR=actor, GITHUB_ENV=str(env_file))
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual("REVIEW_SKIPPED=true" in env_file.read_text(), skipped)


class TheRole(unittest.TestCase):
    def setUp(self):
        self.text = TEMPLATE.read_text()
        self.code = single.code(self.text)

    def test_it_trusts_only_the_bedrock_workflow_for_one_repos_pull_requests(self):
        self.assertIn('"token.actions.githubusercontent.com:aud": sts.amazonaws.com', self.code)
        self.assertIn('"token.actions.githubusercontent.com:sub": !Sub "repo:${ProductRepo}:pull_request:'
                      'job_workflow_ref:${FactoryRepo}/.github/workflows/review-pr-bedrock.yml@${FactoryRef}"',
                      self.code)
        self.assertNotIn("StringLike", self.code)

    def test_it_holds_bedrock_to_the_regions_listed(self):
        parameter = self.code.split("  BedrockRegions:\n", 1)[1].split("\nResources:", 1)[0]
        self.assertIn("Type: CommaDelimitedList", parameter)
        self.assertNotIn("Default:", parameter)
        self.assertIn('"aws:RequestedRegion": !Ref BedrockRegions', self.code)

    def test_it_allows_two_invoke_actions_for_an_hour_at_most(self):
        self.assertIn("MaxSessionDuration: 3600", self.code)
        actions = re.findall(r"^\s+- (bedrock:\S+)$", self.code, re.M)
        self.assertEqual(actions, ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"])
        self.assertNotRegex(self.code, r"Action: ['\"]?\*")


class TheBedrockCaller(unittest.TestCase):
    def setUp(self):
        blocks = yaml_blocks(README.read_text())
        self.assertEqual(len(blocks), 2)
        self.caller = blocks[1]

    def test_it_calls_the_bedrock_workflow_with_the_three_inputs_and_the_deploy_key_alone(self):
        self.assertIn("uses: your-org/factory/.github/workflows/review-pr-bedrock.yml@main", self.caller)
        for name in ("factory-repo", "aws-role-arn", "aws-region", "aws-model"):
            self.assertRegex(self.caller, r"\n      {}: \S+".format(name))
        self.assertIn("FACTORY_DEPLOY_KEY: ${{ secrets.FACTORY_DEPLOY_KEY }}", self.caller)
        for name in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "secrets: inherit", "pull_request_target"):
            self.assertNotIn(name, self.caller)

    def test_it_grants_id_token_on_the_review_job_alone(self):
        self.assertEqual(sorted(single.block(self.caller, "permissions")), ["contents: read", "pull-requests: write"])
        job = self.caller.split("\n  review:\n", 1)[1]
        permissions = job.split("    permissions:\n", 1)[1].split("    uses:", 1)[0]
        self.assertEqual(sorted(line.strip() for line in permissions.splitlines() if line.strip()),
                         ["contents: read", "id-token: write", "pull-requests: write"])


if __name__ == "__main__":
    unittest.main()
