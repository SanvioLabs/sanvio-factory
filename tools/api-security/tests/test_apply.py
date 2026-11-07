"""SPEC-034 REQ-002, REQ-003, REQ-004, REQ-007, REQ-019, REQ-024, AC-001, AC-002: apply.py copies
exactly what a level needs, stamps the version, and never lowers a level by accident."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _path

APPLY = _path.TOOL / "apply.py"
RUNTIME = ("--runtime", "lambda-httpapi")

IDENTITY = """repo:
  github: "o/example"
  branch: "main"

workspace:
  type: "product"
  live_users: false
"""

GATES = """gates:
  repo_baseline:
    description: "Verify repo meets security and quality baseline"
    requires:
      - file_exists: ".gitignore"

  deploy_ready:
    description: "Ready for production deployment"
    requires:
      - gate: repo_baseline
"""


def repo(files=None, identity=IDENTITY, gates=GATES):
    root = Path(tempfile.mkdtemp(prefix="apply-"))
    (root / "pyproject.toml").write_text('[project]\nname = "x"\n')
    if identity is not None:
        (root / ".studio-project.yaml").write_text(identity)
    if gates is not None:
        (root / ".gates.yaml").write_text(gates)
    (root / "AGENTS.md").write_text("# Agents\n\nExisting guidance.\n")
    for rel, text in (files or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


def apply(root, *args):
    return subprocess.run([sys.executable, str(APPLY), *args, str(root)], capture_output=True, text=True)


def level(root):
    for line in (root / ".studio-project.yaml").read_text().splitlines():
        if line.strip().startswith("security_level:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None


class ApplyTests(unittest.TestCase):
    def test_off_and_absent_add_nothing(self):
        root = repo()
        before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
        r = apply(root, "--level", "off")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual((root / ".gates.yaml").read_text(), GATES)

    def test_guided_copies_only_the_language_rules_and_points_agents_at_them(self):
        root = repo()
        r = apply(root, "--level", "guided")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(level(root), "guided")
        rules = root / ".claude" / "rules" / "api-security-python.md"
        self.assertTrue(rules.is_file())
        self.assertTrue(rules.read_text().startswith("---\npaths:"))
        self.assertFalse((root / ".claude" / "rules" / "api-security-typescript.md").exists())
        self.assertTrue((root / "security" / "api_security" / "router.py").is_file(),
                        "the library the Python rules import arrives at guided")
        self.assertFalse((root / "security" / "config.json").exists())
        self.assertFalse((root / ".github").exists())
        self.assertIn(".claude/rules/api-security-python.md", (root / "AGENTS.md").read_text())
        self.assertIn("Existing guidance.", (root / "AGENTS.md").read_text())
        self.assertEqual((root / ".gates.yaml").read_text(), GATES)

    def test_enforced_adds_the_check_workflows_snapshot_version_and_gates(self):
        root = repo()
        r = apply(root, "--level", "enforced", *RUNTIME)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for rel in ("security/__init__.py", "security/api_security/check.py",
                    "security/api_security/verify_approval.py", "security/semgrep/identity-from-request.yml",
                    "security/public-routes.txt", "security/allowed_signers", "security/config.json",
                    "security/fixtures.py", "security/VERSION",
                    ".github/workflows/security-check.yml", ".github/workflows/security-approval.yml"):
            self.assertTrue((root / rel).is_file(), rel)
        self.assertFalse((root / "security" / "semgrep" / "identity-from-request.py").exists(),
                         "the rule's own test fixtures stay in the harness")
        self.assertEqual((root / "security" / "VERSION").read_text().strip(),
                         (_path.TOOL / "VERSION").read_text().strip())
        gates = (root / ".gates.yaml").read_text()
        self.assertIn('file_exists: "security/allowed_signers"', gates)
        self.assertIn("python3 -m security.api_security.check", gates)
        self.assertFalse(json.loads((root / "security" / "config.json").read_text()).get("hardened"))

    def test_enforced_keeps_files_the_holder_already_filled_in(self):
        root = repo({"security/allowed_signers": "owner@example.com ssh-ed25519 AAAA\n",
                     "security/public-routes.txt": "GET /v1/health\n"})
        apply(root, "--level", "enforced", *RUNTIME)
        self.assertIn("owner@example.com", (root / "security" / "allowed_signers").read_text())
        self.assertIn("GET /v1/health", (root / "security" / "public-routes.txt").read_text())

    def test_running_twice_does_not_duplicate(self):
        root = repo()
        apply(root, "--level", "enforced", *RUNTIME)
        apply(root, "--level", "enforced", *RUNTIME)
        gates = (root / ".gates.yaml").read_text()
        self.assertEqual(gates.count('file_exists: "security/allowed_signers"'), 1)
        self.assertEqual((root / "AGENTS.md").read_text().count("api-security:start"), 1)

    def test_hardened_sets_the_flag_and_the_hold_paths(self):
        root = repo()
        r = apply(root, "--level", "hardened", *RUNTIME)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads((root / "security" / "config.json").read_text())["hardened"])
        self.assertTrue((root / "security" / "hold-paths.txt").read_text().strip())

    def test_lowering_needs_the_flag(self):
        root = repo()
        apply(root, "--level", "enforced", *RUNTIME)
        r = apply(root, "--level", "guided")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(level(root), "enforced")
        r = apply(root, "--level", "guided", "--lower")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(level(root), "guided")
        self.assertNotIn("security/allowed_signers", (root / ".gates.yaml").read_text())
        self.assertTrue((root / "security").is_dir(), "lowering never deletes security/")

    def test_lowering_to_off_removes_the_rules_and_the_agents_block(self):
        root = repo()
        apply(root, "--level", "guided")
        r = apply(root, "--level", "off", "--lower")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((root / ".claude" / "rules" / "api-security-python.md").exists())
        self.assertNotIn("api-security", (root / "AGENTS.md").read_text())
        self.assertIn("Existing guidance.", (root / "AGENTS.md").read_text())

    def test_an_unrecognised_current_level_counts_as_off(self):
        root = repo(identity=IDENTITY + '  security_level: "maximum"\n')
        r = apply(root, "--level", "guided")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(level(root), "guided")

    def test_an_unknown_target_level_is_refused(self):
        r = apply(repo(), "--level", "maximum")
        self.assertNotEqual(r.returncode, 0)

    def test_enforced_needs_a_python_implementation(self):
        root = repo()
        (root / "pyproject.toml").unlink()
        (root / "package.json").write_text("{}")
        r = apply(root, "--level", "enforced", *RUNTIME)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("python", (r.stdout + r.stderr).lower())

    def test_no_identity_file_is_refused(self):
        r = apply(repo(identity=None), "--level", "guided")
        self.assertNotEqual(r.returncode, 0)

    # review-spec, 2026-11-06 (T037).

    def test_enforced_without_a_gates_file_works_and_prints_the_manual_step(self):
        root = repo(gates=None)
        r = apply(root, "--level", "enforced", *RUNTIME)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(level(root), "enforced")
        self.assertFalse((root / ".gates.yaml").exists())
        self.assertIn("python3 -m security.api_security.check", r.stdout)

    def test_a_refused_run_writes_nothing(self):
        broken = GATES.replace("  deploy_ready:", "  deploy_later:")
        root = repo(gates=broken)
        before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        r = apply(root, "--level", "enforced", *RUNTIME)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        after = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_a_flow_style_workspace_or_a_broken_config_writes_nothing(self):
        # review-spec 2, 2026-11-06: both refused only after 25 files had been written.
        for name, root in (("flow workspace", repo(identity='repo:\n  github: "o/x"\nworkspace: {type: internal}\n')),
                           ("broken config", repo(files={"security/config.json": '{"hardened": false,}\n'}))):
            with self.subTest(name):
                before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
                r = apply(root, "--level", "enforced", *RUNTIME)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                if name == "broken config":
                    self.assertIn("security/config.json", r.stderr)
                after = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
                self.assertEqual(before, after)

    def test_python_enforced_names_its_runtime(self):
        r = apply(repo(), "--level", "enforced")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--runtime lambda-httpapi", r.stderr)

    def test_a_symlinked_destination_is_refused_and_nothing_outside_is_touched(self):
        outside = Path(tempfile.mkdtemp(prefix="outside-"))
        (outside / "target.txt").write_text("keep\n")
        (outside / "api_security").mkdir()
        (outside / "api_security" / "keep.txt").write_text("keep\n")
        for link, target, level_ in (("AGENTS.md", outside / "target.txt", "guided"),
                                     ("security", outside, "enforced")):
            with self.subTest(link=link):
                root = repo()
                (root / link).unlink() if (root / link).exists() else None
                (root / link).symlink_to(target)
                r = apply(root, "--level", level_, *RUNTIME)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("symlink", r.stderr)
        self.assertEqual((outside / "target.txt").read_text(), "keep\n")
        self.assertTrue((outside / "api_security" / "keep.txt").exists())

    def test_a_symlinked_file_under_security_is_refused_before_anything_is_written(self):
        outside = Path(tempfile.mkdtemp(prefix="outside-"))
        (outside / "victim.json").write_text("{}\n")
        root = repo()
        (root / "security").mkdir()
        (root / "security" / "config.json").symlink_to(outside / "victim.json")
        (root / "security" / "public-routes.txt").symlink_to(outside / "absent.txt")
        before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
        r = apply(root, "--level", "enforced", *RUNTIME)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("symlink", r.stderr)
        self.assertEqual((outside / "victim.json").read_text(), "{}\n")
        self.assertFalse((outside / "absent.txt").exists())
        self.assertEqual(sorted(p.relative_to(root).as_posix() for p in root.rglob("*")), before)

    def test_an_identity_file_outside_the_repo(self):
        root = repo(identity=None)
        elsewhere = Path(tempfile.mkdtemp(prefix="client-")) / ".studio-project.yaml"
        elsewhere.write_text(IDENTITY)
        r = apply(root, "--level", "guided", "--identity", str(elsewhere))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('security_level: "guided"', elsewhere.read_text())

    def test_a_mixed_language_refusal_names_lang(self):
        root = repo({"package.json": "{}"})
        r = apply(root, "--level", "enforced", *RUNTIME)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--lang python", r.stderr)
        r = apply(root, "--level", "enforced", "--lang", "python", *RUNTIME)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_what_apply_writes_names_no_internal_spec(self):
        root = repo()
        apply(root, "--level", "enforced", *RUNTIME)
        for rel in (".gates.yaml", "AGENTS.md"):
            self.assertNotIn("SPEC-", (root / rel).read_text(), rel)

    def test_an_older_marked_block_is_still_replaced(self):
        old = ("# Agents\n\n<!-- api-security:start (SPEC-034, written by apply.py) -->\nold\n"
               "<!-- api-security:end -->\n")
        root = repo({"AGENTS.md": old})
        apply(root, "--level", "guided")
        text = (root / "AGENTS.md").read_text()
        self.assertEqual(text.count("api-security:start"), 1)
        self.assertNotIn("\nold\n", text)

    def test_hardened_holds_the_handler_modules(self):
        root = repo({"security/config.json": json.dumps({
            "roles_module": "app.roles", "handler_modules": ["app.handlers", "app.api.users"],
            "adapter": {"kind": "terraform", "paths": ["infra"]}})})
        r = apply(root, "--level", "hardened", *RUNTIME)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        hold = (root / "security" / "hold-paths.txt").read_text()
        for glob in ("app/handlers.py", "app/handlers/**", "app/api/users.py", "app/api/users/**"):
            self.assertIn(glob, hold)


class VersionStampTests(unittest.TestCase):
    """review-spec, 2026-11-06 (T039): VERSION names its content, so a copy can be checked."""

    def test_the_stamp_matches_the_files_it_names(self):
        sys.path.insert(0, str(_path.TOOL))
        import apply as tool
        number, _, digest = (_path.TOOL / "VERSION").read_text().strip().partition("+")
        self.assertTrue(number and digest, "VERSION is <number>+<hash>")
        self.assertEqual(digest, tool.tool_hash(),
                         "the library or a workflow changed without a new stamp: run `python3 apply.py --stamp`")

    def test_an_applied_project_matches_its_stamp_until_it_is_edited(self):
        sys.path.insert(0, str(_path.TOOL))
        import apply as tool
        root = repo()
        apply(root, "--level", "enforced", *RUNTIME)
        stamp = (root / "security" / "VERSION").read_text().strip().partition("+")[2]
        self.assertEqual(tool.project_hash(root), stamp)
        router = root / "security" / "api_security" / "router.py"
        router.write_text(router.read_text() + "# edited\n")
        self.assertNotEqual(tool.project_hash(root), stamp)


class IdentityFieldTests(unittest.TestCase):
    """review-spec 3, 2026-11-07: the rule's identity field list is one string apply.py extends and
    the hash takes back out; both have to find it, and nothing else may escape the hash."""

    RULE = _path.TOOL / "semgrep" / "identity-from-request.yml"

    def levels(self):
        sys.path.insert(0, str(_path.TOOL))
        import api_security_levels as levels
        return levels

    def enforced(self, config=None):
        root = repo()
        if config is not None:
            (root / "security").mkdir()
            (root / "security" / "config.json").write_text(json.dumps(config))
        r = apply(root, "--level", "enforced", *RUNTIME)
        self.assertEqual(r.returncode, 0, r.stderr)
        return root

    def test_the_default_fields_appear_at_every_site_in_the_rule(self):
        levels = self.levels()
        self.assertEqual(self.RULE.read_text().count(levels.DEFAULT_FIELDS), levels.RULE_FIELD_SITES,
                         "edit DEFAULT_FIELDS and the rule together, and RULE_FIELD_SITES with them")

    def test_a_projects_identity_fields_reach_every_site_and_keep_the_stamp(self):
        levels = self.levels()
        root = self.enforced({"identity_fields": ["org_no", "bad name", 5]})
        rule = (root / "security" / "semgrep" / "identity-from-request.yml").read_text()
        self.assertEqual(rule.count(levels.DEFAULT_FIELDS + "|org_no"), levels.RULE_FIELD_SITES)
        self.assertNotIn("bad name", rule)
        stamp = (root / "security" / "VERSION").read_text().strip().partition("+")[2]
        self.assertEqual(levels.project_hash(root), stamp)

    def test_an_edit_to_the_header_names_in_the_rule_changes_the_hash(self):
        levels = self.levels()
        for config in (None, {"identity_fields": ["org_no"]}):
            root = self.enforced(config)
            before = levels.project_hash(root)
            path = root / "security" / "semgrep" / "identity-from-request.yml"
            path.write_text(path.read_text().replace("|x-user-id", "|x-other-id"))
            self.assertNotEqual(levels.project_hash(root), before, config)

    def test_an_extra_field_left_in_the_rule_after_it_leaves_the_config_is_drift(self):
        levels = self.levels()
        root = self.enforced({"identity_fields": ["org_no"]})
        stamp = (root / "security" / "VERSION").read_text().strip().partition("+")[2]
        (root / "security" / "config.json").write_text(json.dumps({"identity_fields": []}))
        self.assertNotEqual(levels.project_hash(root), stamp)

    def test_the_identity_field_reader_ignores_anything_but_a_list_of_names(self):
        levels = self.levels()
        for config in ({"identity_fields": "org_no"}, {"identity_fields": 5}, [], None, {}):
            self.assertEqual(levels.identity_extras(config), [], config)


class ApplyCommandTests(unittest.TestCase):
    """review-spec 3, 2026-11-07: the command a check prints runs as printed."""

    def test_the_command_names_runtime_and_identity_only_when_needed(self):
        sys.path.insert(0, str(_path.TOOL))
        import api_security_levels as levels
        T = "t/apply.py"
        self.assertEqual(levels.apply_command(T, "guided", Path("p/app")),
                         "python3 t/apply.py --level guided p/app")
        self.assertEqual(levels.apply_command(T, "enforced", Path("p/app"), Path("p/app/.studio-project.yaml")),
                         "python3 t/apply.py --level enforced --runtime lambda-httpapi p/app")
        self.assertEqual(levels.apply_command(T, "guided", Path("c/x/repos/a"), Path("c/x/.studio-project.yaml")),
                         "python3 t/apply.py --level guided --identity c/x/.studio-project.yaml c/x/repos/a")
        self.assertEqual(levels.apply_command(T, "guided", Path("a b")), "python3 t/apply.py --level guided 'a b'")

    def test_apply_parses_every_flag_the_command_uses(self):
        sys.path.insert(0, str(_path.TOOL))
        import api_security_levels as levels
        root = repo()
        cmd = levels.apply_command(str(APPLY), "enforced", root, root / ".studio-project.yaml")
        r = subprocess.run(cmd.replace("python3", sys.executable, 1), shell=True, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
