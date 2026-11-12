"""Run with: python3 -m unittest discover -s tests"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "examples" / "ci" / "loop.yml"

# The one way a secret may be named: ${{ secrets.NAME }}.
SECRET_REF = re.compile(r"^\$\{\{\s*secrets\.[A-Z][A-Z0-9_]*\s*\}\}$")


def top_level_block(text, key):
    """The indented lines under a top-level `key:`, or None."""
    match = re.search(r"^{}:[ \t]*\n((?:[ \t]+\S.*\n?|[ \t]*\n)*)".format(re.escape(key)), text, re.M)
    return match.group(1) if match else None


def bad_secret_references(text):
    """Every `secrets` mention that isn't a whole ${{ secrets.NAME }} expression."""
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    inside = [m.group(0) for m in re.finditer(r"\$\{\{.*?\}\}", code)]
    bad = [e for e in inside if "secrets" in e and not SECRET_REF.match(e)]
    outside = re.sub(r"\$\{\{.*?\}\}", "", code)
    if re.search(r"\bsecrets\b", outside):
        bad.append("a bare 'secrets' outside an expression")
    return bad


class LoopWorkflowExample(unittest.TestCase):
    def setUp(self):
        self.assertTrue(WORKFLOW.exists(), "examples/ci/loop.yml is missing")
        self.text = WORKFLOW.read_text()

    def test_it_runs_one_pass_of_the_loop(self):
        self.assertRegex(self.text, r"(?m)^\s*python3 scripts/loop\.py run --once\s*$")

    def test_no_token_is_left_where_the_tests_could_read_it(self):
        self.assertRegex(self.text, r"(?m)^\s*persist-credentials:\s*false\s*$")
        self.assertRegex(self.text, r"(?m)^\s*gh auth setup-git\s*$")

    def test_the_agent_cli_is_pinned(self):
        self.assertRegex(self.text, r"@anthropic-ai/claude-code@\d+\.\d+\.\d+")

    def test_it_runs_on_a_schedule_and_by_hand(self):
        triggers = top_level_block(self.text, "on")
        self.assertIsNotNone(triggers, "no on: block")
        self.assertRegex(triggers, r"(?m)^\s+schedule:")
        self.assertRegex(triggers, r"(?m)^\s+workflow_dispatch:")

    def test_it_asks_only_for_what_one_pass_uses(self):
        block = top_level_block(self.text, "permissions")
        self.assertIsNotNone(block, "no top-level permissions: block")
        granted = dict(re.findall(r"^\s+([a-z-]+):\s*(\S+)\s*$", block, re.M))
        self.assertEqual(granted, {"contents": "write", "issues": "write", "pull-requests": "write"})

    def test_it_keeps_the_loop_folder_after_the_runner_is_gone(self):
        self.assertRegex(self.text, r"(?m)^\s*uses:\s*actions/upload-artifact@")
        self.assertRegex(self.text, r"(?m)^\s*path:\s*\.loop/?\s*$")
        # a .loop folder is hidden, and the action skips hidden files unless told not to
        self.assertRegex(self.text, r"(?m)^\s*include-hidden-files:\s*true\s*$")

    def test_secrets_are_named_never_written(self):
        self.assertEqual(bad_secret_references(self.text), [])
        self.assertIn("${{ secrets.ANTHROPIC_API_KEY }}", self.text)
        self.assertNotRegex(self.text, r"sk-ant-|ghp_|github_pat_")

    def test_the_reference_check_catches_a_pasted_key(self):
        self.assertEqual(bad_secret_references("ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}"), [])
        self.assertTrue(bad_secret_references("KEY: ${{ toJSON(secrets) }}"))
        self.assertTrue(bad_secret_references("KEY: ${{ secrets['ANTHROPIC_API_KEY'] }}"))
        self.assertTrue(bad_secret_references("run: echo $secrets"))

    def test_how_it_works_says_where_it_runs_and_the_limits(self):
        text = (ROOT / "HOW-IT-WORKS.md").read_text()
        self.assertIn("### Off your laptop", text)
        self.assertIn("examples/ci/loop.yml", text)
        self.assertIn("GITHUB_TOKEN", text)


PROJECT_CHECKS = ROOT / "examples" / "ci" / "project-checks.yml"


def job_block(text, name):
    """The lines of job `name` under `jobs:`, up to the next job, or None."""
    jobs = top_level_block(text, "jobs")
    if jobs is None:
        return None
    match = re.search(r"^  {}:[ \t]*\n((?:    .*\n?|[ \t]*\n)*)".format(re.escape(name)), jobs, re.M)
    return match.group(1) if match else None


def steps_of(job):
    """Each `- ` step of a job, as its own block of lines."""
    return re.split(r"(?m)^(?=      - )", job)[1:]


def step_run_block(text, name):
    """The lines of the `run: |` block under the step called `name`, or None."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^\s*-\s*name:\s*{}\s*$".format(re.escape(name)), line):
            break
    else:
        return None
    for j in range(i + 1, len(lines)):
        match = re.match(r"^(\s*)run:\s*\|\s*$", lines[j])
        if match:
            indent = len(match.group(1))
            block = []
            for body in lines[j + 1:]:
                if body.strip() and len(body) - len(body.lstrip()) <= indent:
                    break
                block.append(body)
            return block
        if re.match(r"^\s*-\s", lines[j]):
            return None
    return None


class ProjectChecksExample(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PROJECT_CHECKS.exists(), "examples/ci/project-checks.yml is missing")
        self.text = PROJECT_CHECKS.read_text()

    def test_the_e2e_job_runs_playwright_only_when_the_project_has_a_config(self):
        job = job_block(self.text, "e2e")
        self.assertIsNotNone(job, "no e2e: job under jobs:")
        steps = steps_of(job)
        detect = [s for s in steps if re.search(r"(?m)^\s+id:\s*detect\s*$", s)]
        self.assertEqual(len(detect), 1, "no detect step in the e2e job")
        for config in ("playwright.config.ts", "playwright.config.js", "playwright.config.mjs"):
            self.assertRegex(detect[0], r"-f\s+{}\b".format(re.escape(config)))
        runs = [s for s in steps if re.search(r"(?m)^\s+(?:run:\s*)?npx playwright test\s*$", s)]
        self.assertEqual(len(runs), 1, "no step runs npx playwright test")
        self.assertRegex(runs[0], r"(?m)^\s+if:\s*steps\.detect\.outputs\.found == 'true'\s*$")

    def test_coverage_runs_only_behind_the_pytest_cov_check(self):
        block = step_run_block(self.text, "Tests")
        self.assertIsNotNone(block, "no Tests step with a run: block")
        guard = next((i for i, line in enumerate(block) if "import pytest_cov" in line), None)
        self.assertIsNotNone(guard, "the Tests step doesn't check for pytest-cov")
        indent = len(block[guard]) - len(block[guard].lstrip())
        end = next(
            (i for i in range(guard + 1, len(block))
             if block[i].strip() in ("else", "fi") and len(block[i]) - len(block[i].lstrip()) == indent),
            None,
        )
        self.assertIsNotNone(end, "the pytest-cov check has no else or fi")
        uses = [i for i, line in enumerate(block) if "--cov" in line]
        self.assertTrue(uses, "the Tests step never runs coverage")
        for i in uses:
            self.assertTrue(guard < i < end, "--cov outside the pytest-cov check: " + block[i].strip())

    def test_the_workflow_sets_no_coverage_threshold(self):
        # The bar is the project's, in its own pyproject.toml.
        code = "\n".join(line for line in self.text.splitlines() if not line.lstrip().startswith("#"))
        self.assertNotIn("--cov-fail-under", code)
        self.assertNotIn("fail_under", code)


WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml")) + sorted((ROOT / "examples" / "ci").glob("*.yml"))


def unpinned_actions(text):
    """Every `uses:` that names an action by tag or branch rather than a full commit SHA."""
    refs = re.findall(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", text, re.M)
    return [r for r in refs if not r.startswith("./") and not re.search(r"@[0-9a-f]{40}$", r)]


def unquoted_heredocs(text):
    """Every heredoc opened with a bare delimiter, whose body the shell would expand."""
    return re.findall(r"<<-?\s*([A-Za-z_]\w*)\b", text)


def unchecked_downloads(text):
    """Every curl or wget that fetches something to run, in a workflow with no pinned sha256 check."""
    commands = re.findall(r"\b(?:curl|wget)\b[^\n]*", text.replace("\\\n", " "))
    fetched = [c for c in commands if re.search(r"\|\s*(?:tar|sh|bash)\b|\s-[oO]\s|\.(?:tar\.gz|tgz|zip|deb)\b", c)]
    checked = re.search(r"sha256sum\s+(?:-c|--check)\b", text) and re.search(r"\b[0-9a-f]{64}\b", text)
    return [] if checked else fetched


class EveryWorkflow(unittest.TestCase):
    def test_every_download_is_checked_against_a_pinned_sha256(self):
        # A release asset can be replaced after it's published; a checksum
        # written here can't.
        for path in WORKFLOWS:
            self.assertEqual(unchecked_downloads(path.read_text()), [], path.name)

    def test_the_download_check_catches_an_unchecked_binary(self):
        unchecked = 'curl -sSfL "https://example.com/tool_1.0_linux_x64.tar.gz" \\\n  | tar -xz -C /tmp tool\n'
        self.assertEqual(len(unchecked_downloads(unchecked)), 1)
        checked = (
            "SHA256=" + "a" * 64 + "\n"
            'curl -sSfL -o /tmp/tool.tar.gz "https://example.com/tool_1.0_linux_x64.tar.gz"\n'
            'echo "${SHA256}  /tmp/tool.tar.gz" | sha256sum -c -\n'
        )
        self.assertEqual(unchecked_downloads(checked), [])
        self.assertEqual(unchecked_downloads('curl -sSf "https://api.github.com/repos/o/r"\n'), [])


    def test_every_action_is_pinned_to_a_commit(self):
        # A tag can be moved to other code; a commit can't.
        for path in WORKFLOWS:
            self.assertEqual(unpinned_actions(path.read_text()), [], path.name)

    def test_the_pin_check_catches_a_tag(self):
        self.assertEqual(unpinned_actions("      - uses: actions/checkout@v4\n"), ["actions/checkout@v4"])
        self.assertEqual(unpinned_actions("      - uses: actions/checkout@" + "a" * 40 + " # v4\n"), [])

    def test_every_heredoc_is_quoted(self):
        for path in WORKFLOWS:
            self.assertEqual(unquoted_heredocs(path.read_text()), [], path.name)

    def test_the_heredoc_check_catches_a_bare_delimiter(self):
        self.assertEqual(unquoted_heredocs('cat > f <<EOF\n'), ["EOF"])
        self.assertEqual(unquoted_heredocs("cat > f <<'EOF'\n"), [])


DEPS = ROOT / ".github" / "workflows" / "deps.yml"
DEPENDABOT = ROOT / ".github" / "dependabot.yml"


def code_lines(text):
    """The text without its comment lines."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def write_grants(text):
    """Every `name: write` or `permissions: write-all` grant, at any level, outside a comment."""
    grant = r"^\s*(?:[a-z-]+:\s*[\"']?write[\"']?|permissions:\s*[\"']?write-all[\"']?)\s*(?:#.*)?$"
    return re.findall(grant, code_lines(text), re.M)


def step_with(steps, pattern):
    """The steps whose lines match `pattern`."""
    return [s for s in steps if re.search(pattern, s, re.M)]


def dependabot_updates(text):
    """(ecosystem, directory, interval) for each entry under `updates:`."""
    block = top_level_block(text, "updates") or ""
    found = []
    for entry in re.split(r"(?m)^  - ", block)[1:]:
        fields = []
        for key in ("package-ecosystem", "directory", "interval"):
            match = re.search(r'(?m)^\s*{}:\s*"?([^"\s]+)"?\s*$'.format(key), entry)
            fields.append(match.group(1) if match else None)
        found.append(tuple(fields))
    return found


class DependencyScan(unittest.TestCase):
    def setUp(self):
        self.assertTrue(DEPS.exists(), ".github/workflows/deps.yml is missing")
        self.assertTrue(DEPENDABOT.exists(), ".github/dependabot.yml is missing")
        self.deps = DEPS.read_text()
        self.dependabot = DEPENDABOT.read_text()
        job = job_block(self.deps, "scan")
        self.assertIsNotNone(job, "no scan: job under jobs:")
        self.steps = steps_of(job)

    def test_its_actions_are_pinned_to_a_commit(self):
        self.assertRegex(self.deps, r"(?m)^\s*(?:-\s*)?uses:\s*\S")
        self.assertEqual(unpinned_actions(self.deps), [])

    def test_the_checkout_leaves_no_token_on_disk(self):
        checkout = step_with(self.steps, r"^\s*-?\s*uses:\s*actions/checkout@")
        self.assertEqual(len(checkout), 1, "no single checkout step")
        self.assertRegex(checkout[0], r"(?m)^\s+persist-credentials:\s*false\s*$")

    def test_it_can_only_read(self):
        block = top_level_block(self.deps, "permissions")
        self.assertIsNotNone(block, "no top-level permissions: block")
        granted = dict(re.findall(r"^\s+([a-z-]+):\s*(\S+)\s*$", block, re.M))
        self.assertEqual(granted, {"contents": "read"})
        # A job-level grant would get past a check on the top-level block alone.
        self.assertEqual(write_grants(self.deps), [])

    def test_the_write_check_catches_a_job_level_grant(self):
        job = "jobs:\n  scan:\n    permissions:\n      security-events: write\n"
        self.assertEqual(len(write_grants(job)), 1)
        self.assertEqual(write_grants("# a checksum written here\npermissions:\n  contents: read\n"), [])
        self.assertEqual(len(write_grants("permissions: write-all\n")), 1)
        self.assertEqual(len(write_grants("    permissions:\n      contents: 'write'\n")), 1)
        # A message that only mentions the word is not a grant.
        self.assertEqual(write_grants('        run: echo "::error::write down why it does not apply"\n'), [])

    def test_it_runs_weekly_by_hand_and_on_lockfile_pull_requests_only(self):
        triggers = top_level_block(self.deps, "on")
        self.assertIsNotNone(triggers, "no on: block")
        self.assertRegex(triggers, r"(?m)^  schedule:")
        self.assertRegex(triggers, r"(?m)^  workflow_dispatch:")
        self.assertNotRegex(triggers, r"(?m)^\s+push:")
        pull_request = re.search(r"(?m)^  pull_request:[ \t]*\n((?:    .*\n?)*)", triggers)
        self.assertIsNotNone(pull_request, "no pull_request: trigger with paths")
        self.assertRegex(pull_request.group(1), r"(?m)^\s+paths:")
        paths = re.findall(r"""(?m)^\s+-\s*["']?([^"'\s]+)["']?\s*$""", pull_request.group(1))
        self.assertIn("**/package-lock.json", paths)
        # Otherwise a change to the workflow itself isn't run before it merges.
        self.assertIn(".github/workflows/deps.yml", paths)

    def test_the_scanner_is_pinned_and_checked(self):
        install = step_with(self.steps, r"^\s+id:\s*install\s*$")
        self.assertEqual(len(install), 1, "no single step with id: install")
        self.assertRegex(install[0], r"(?m)^\s*-?\s*name:\s*Install osv-scanner\s*$")
        block = step_run_block(self.deps, "Install osv-scanner")
        self.assertIsNotNone(block, "no Install osv-scanner step with a run: block")
        lines = [line.strip() for line in block]
        self.assertIn("VERSION=2.7.0", lines)
        self.assertIn("SHA256=160c6253e2922e9e0a6a9771c5c4c40a4b3c6090b34a3cdd5e80c96cc2e4218b", lines)
        download = (
            'curl -sSfL -o /tmp/osv-scanner '
            '"https://github.com/google/osv-scanner/releases/download/v${VERSION}/osv-scanner_linux_amd64"'
        )
        check = 'echo "${SHA256}  /tmp/osv-scanner" | sha256sum -c -'
        for line in (download, check, "chmod +x /tmp/osv-scanner"):
            self.assertIn(line, lines)
        # Download, then check, and only then make it runnable.
        self.assertLess(lines.index(download), lines.index(check))
        self.assertLess(lines.index(check), lines.index("chmod +x /tmp/osv-scanner"))
        self.assertEqual(unchecked_downloads(self.deps), [])

    def test_the_scan_step_runs_the_checked_scanner_over_the_repo(self):
        scan = step_with(self.steps, r"^\s+id:\s*scan\s*$")
        self.assertEqual(len(scan), 1, "no single step with id: scan")
        self.assertRegex(scan[0], r"(?m)^\s+(?:run:\s*)?/tmp/osv-scanner scan source --recursive \.\s*$")
        self.assertLess(self.steps.index(step_with(self.steps, r"^\s+id:\s*install\s*$")[0]), self.steps.index(scan[0]))

    def test_a_failure_says_what_to_do(self):
        cases = {
            "scan": ("Upgrade the package", "record why"),
            "install": ("the scan didn't run", "Don't remove the check", "SHA256", "osv-scanner_SHA256SUMS"),
        }
        for step_id, phrases in cases.items():
            guard = r"^\s+if:\s*failure\(\) && steps\.{}\.outcome == 'failure'\s*$".format(step_id)
            found = step_with(self.steps, guard)
            self.assertEqual(len(found), 1, "no single failure step for " + step_id)
            errors = re.findall(r'(?m)^\s+echo "::error::(.+)"\s*$', found[0])
            self.assertEqual(len(errors), 1, "the failure step for {} has no ::error:: line".format(step_id))
            for phrase in phrases:
                self.assertIn(phrase, errors[0], step_id)

    def test_dependabot_watches_only_the_factorys_own_dependencies(self):
        self.assertEqual(sorted(dependabot_updates(self.dependabot)), [
            ("github-actions", "/", "weekly"),
            ("npm", "/examples/typescript", "weekly"),
        ])
        # projects/ and a copy's own repos keep their own dependabot.yml.
        code = code_lines(self.dependabot)
        self.assertEqual(len(re.findall(r"(?m)^\s*directory:", code)), 2)
        self.assertNotRegex(code, r"(?m)^\s*directories:")


CI = ROOT / ".github" / "workflows" / "ci.yml"


class BanditScan(unittest.TestCase):
    def setUp(self):
        self.assertTrue(CI.exists(), ".github/workflows/ci.yml is missing")
        self.text = CI.read_text()
        job = job_block(self.text, "checks")
        self.assertIsNotNone(job, "no checks: job under jobs:")
        self.steps = steps_of(job)
        found = step_with(self.steps, r"uvx bandit")
        self.assertEqual(len(found), 1, "no single step in checks runs uvx bandit")
        self.step = found[0]

    def test_the_version_is_pinned_exactly(self):
        # Moving the version means changing it here and in ci.yml together.
        self.assertRegex(self.step, r"(?m)^\s+run:\s*" + re.escape(
            "uvx bandit==1.9.4 -q -r scripts .claude/hooks tools examples -x '*/tests/*,*/node_modules/*'"
            " --severity-level medium --confidence-level medium") + r"\s*$")
        self.assertRegex(self.step, r"uvx bandit==\d+\.\d+\.\d+ ")
        self.assertNotRegex(self.step, r"bandit\s*(?:>=|~=|<|>|!=)")
        self.assertNotRegex(self.step, r"uvx bandit(?!==)")

    def test_it_scans_the_factorys_python_at_medium_and_up(self):
        for part in ("-r scripts .claude/hooks tools examples", "-x '*/tests/*,*/node_modules/*'",
                     "--severity-level medium", "--confidence-level medium"):
            self.assertIn(part, self.step)

    def test_a_finding_fails_the_job(self):
        self.assertNotIn("continue-on-error", self.step)
        self.assertNotRegex(self.step, r"\|\|\s*true")

    def test_it_runs_on_every_pull_request_and_every_push_to_main(self):
        triggers = top_level_block(self.text, "on")
        self.assertIsNotNone(triggers, "no on: block")
        push = re.search(r"(?m)^  push:[ \t]*\n((?:    .*\n?)*)", triggers)
        self.assertIsNotNone(push, "no push: trigger")
        self.assertRegex(push.group(1), r"(?m)^\s+branches:\s*\[main\]\s*$")
        pull_request = re.search(r"(?m)^  pull_request:[ \t]*\n((?:    .*\n?)*)", triggers)
        self.assertIsNotNone(pull_request, "no pull_request: trigger")
        self.assertNotRegex(pull_request.group(1), r"(?m)^\s+paths(?:-ignore)?:")

    def test_it_runs_after_uv_is_set_up(self):
        setup = step_with(self.steps, r"^\s*-?\s*uses:\s*astral-sh/setup-uv@")
        self.assertEqual(len(setup), 1, "no single setup-uv step in checks")
        self.assertLess(self.steps.index(setup[0]), self.steps.index(self.step))

    def test_the_loops_one_nosec_names_its_test_at_the_shell_call(self):
        lines = (ROOT / "scripts" / "loop.py").read_text(encoding="utf-8").splitlines()
        marked = [i for i, line in enumerate(lines) if "nosec" in line]
        self.assertEqual(len(marked), 1, "scripts/loop.py should have exactly one nosec")
        line = lines[marked[0]]
        self.assertRegex(line, r"subprocess\.run\(.*shell=shell.*# nosec B602\s*$")
        # It sits in ran(), the body of sh(), the one place the loop runs shell text.
        defs = [i for i, text in enumerate(lines[:marked[0]]) if re.match(r"\s*def ", text)]
        self.assertRegex(lines[defs[-1]], r"^\s*def ran\(")
        self.assertRegex(lines[defs[-2]], r"^\s*def sh\(")
        self.assertIn("self.ran(", "\n".join(lines[defs[-2]:defs[-1]]))

    def test_no_nosec_is_bare(self):
        for folder in ("scripts", ".claude/hooks", "tools"):
            for path in (ROOT / folder).rglob("*.py"):
                if "node_modules" in path.parts:
                    continue
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    with self.subTest(path=path.relative_to(ROOT).as_posix(), line=number):
                        self.assertNotRegex(line, r"#\s*nosec\s*$")

    def test_old_names_asks_tempfile_for_the_temp_folder(self):
        text = (ROOT / "scripts" / "old_names.py").read_text(encoding="utf-8")
        self.assertNotIn('"/tmp"', text)
        self.assertIn("tempfile.gettempdir()", text)


if __name__ == "__main__":
    unittest.main()
