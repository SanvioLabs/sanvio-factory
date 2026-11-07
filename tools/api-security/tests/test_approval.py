"""SPEC-034 REQ-016, AC-009, SEC-002, SEC-004: a change to the guarded surface needs a commit
signed by a key the base branch already trusts. Fixture histories use throwaway keys."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _path

VERIFY = _path.LIB / "api_security" / "verify_approval.py"
CLEAN_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
CLEAN_ENV.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                 GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                 GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")


def git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=CLEAN_ENV, check=check)


def keypair(where, name):
    key = Path(where) / name
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)], check=True)
    return key, (Path(str(key) + ".pub")).read_text().strip()


class Repo:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="approval-"))
        self.keys = self.dir.parent / (self.dir.name + "-keys")
        self.keys.mkdir()
        self.trusted, self.trusted_pub = keypair(self.keys, "trusted")
        self.other, self.other_pub = keypair(self.keys, "other")
        git(self.dir, "init", "-q", "-b", "main")
        self.write("app/handlers.py", "x = 1\n")
        self.write("security/public-routes.txt", "GET /v1/health\n")
        self.write("security/allowed_signers", f"owner@example.com {self.trusted_pub}\n")
        self.write(".github/workflows/security-check.yml", "name: security-check\n")
        self.commit("base")
        self.base = self.head()
        git(self.dir, "checkout", "-q", "-b", "pr")

    def write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def append(self, rel, text):
        p = self.dir / rel
        p.write_text(p.read_text() + text)

    def commit(self, msg, key=None):
        git(self.dir, "add", "-A")
        args = ["commit", "-q", "-m", msg]
        if key is not None:
            args = ["-c", "gpg.format=ssh", "-c", f"user.signingkey={key}", *args, "-S"]
        git(self.dir, *args)

    def head(self):
        return git(self.dir, "rev-parse", "HEAD").stdout.strip()

    def verify(self, author=None, sender=None, action=None):
        args = [sys.executable, str(VERIFY), "--repo", str(self.dir), "--base", self.base, "--head", self.head()]
        args += ["--author", author] if author is not None else []
        args += ["--sender", sender] if sender is not None else []
        args += ["--action", action] if action is not None else []
        return subprocess.run(args, capture_output=True, text=True, env=CLEAN_ENV)

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(self.keys, ignore_errors=True)


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        missing = [b for b in ("git", "ssh-keygen") if not shutil.which(b)]
        if missing:  # fail, never skip: a check that cannot run must not read as one that passed
            self.fail(f"needs {', '.join(missing)}")
        self.r = Repo()

    def tearDown(self):
        self.r.cleanup()

    def g(self, *args):
        return git(self.r.dir, *args)

    def assertPasses(self, **who):
        res = self.r.verify(**who)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def assertFails(self, needle=None, **who):
        res = self.r.verify(**who)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        if needle:
            self.assertIn(needle, res.stdout)

    def test_no_guarded_change_passes(self):
        self.r.write("app/handlers.py", "x = 2\n")
        self.r.commit("handler change")
        self.assertPasses()

    def test_an_unsigned_public_route_addition_fails(self):
        self.r.append("security/public-routes.txt", "GET /v1/new\n")
        self.r.commit("add public route")
        self.assertFails("security/public-routes.txt")

    def test_an_addition_signed_by_an_unlisted_key_fails(self):
        self.r.append("security/public-routes.txt", "GET /v1/new\n")
        self.r.commit("add public route", key=self.r.other)
        self.assertFails()

    def test_a_pr_adding_its_own_key_and_signing_with_it_fails(self):
        self.r.append("security/allowed_signers", f"intruder@example.com {self.r.other_pub}\n")
        self.r.append("security/public-routes.txt", "GET /v1/new\n")
        self.r.commit("add my key and a route", key=self.r.other)
        self.assertFails()

    def test_an_addition_signed_by_a_base_listed_key_passes(self):
        self.r.append("security/public-routes.txt", "GET /v1/new\n")
        self.r.commit("add public route", key=self.r.trusted)
        self.assertPasses()

    def test_an_unsigned_commit_after_the_signed_one_fails(self):
        self.r.append("security/public-routes.txt", "GET /v1/new\n")
        self.r.commit("signed", key=self.r.trusted)
        self.r.append("security/public-routes.txt", "GET /v1/sneaky\n")
        self.r.commit("unsigned on top")
        self.assertFails()

    def test_a_removal_from_public_routes_passes_unsigned(self):
        self.r.write("security/public-routes.txt", "")
        self.r.commit("drop a public route")
        self.assertPasses()

    def test_an_unsigned_change_to_another_security_file_fails(self):
        self.r.write("security/config.json", "{}\n")
        self.r.commit("touch config")
        self.assertFails("security/config.json")

    def test_an_unsigned_change_to_a_security_workflow_fails(self):
        self.r.write(".github/workflows/security-check.yml", "name: security-check\non: {}\n")
        self.r.commit("neuter the check")
        self.assertFails(".github/workflows/security-check.yml")

    def test_a_merge_from_base_is_not_an_unsigned_change(self):
        git(self.r.dir, "checkout", "-q", "main")
        self.r.append("security/public-routes.txt", "GET /v1/landed\n")
        self.r.commit("landed on main", key=self.r.trusted)
        new_base = self.r.head()
        git(self.r.dir, "checkout", "-q", "pr")
        self.r.write("app/handlers.py", "x = 3\n")
        self.r.commit("pr work")
        git(self.r.dir, "merge", "-q", "--no-edit", "main")
        self.r.base = new_base
        self.assertPasses()

    def test_a_base_without_allowed_signers_fails_closed(self):
        git(self.r.dir, "checkout", "-q", "main")
        git(self.r.dir, "rm", "-q", "security/allowed_signers")
        self.r.commit("no signers")
        self.r.base = self.r.head()
        git(self.r.dir, "checkout", "-q", "-b", "pr2")
        self.r.append("security/public-routes.txt", "GET /v1/new\n")
        self.r.commit("add", key=self.r.trusted)
        self.assertFails("allowed_signers")

    # Review findings, 2026-11-06 (T027).

    def test_a_guarded_path_git_would_quote_is_still_guarded(self):
        for name in ("security/caf\u00e9.json", 'security/a"b.json', "security/tab\tname.json"):
            with self.subTest(name=name):
                self.r.write(name, "{}\n")
                self.r.commit("odd name")
                self.assertFails("caf" if "caf" in name else None)
                git(self.r.dir, "reset", "-q", "--hard", "HEAD~1")

    def test_a_mode_only_change_after_the_signed_commit_fails(self):
        self.r.append("security/public-routes.txt", "GET /v1/new\n")
        self.r.commit("signed", key=self.r.trusted)
        git(self.r.dir, "update-index", "--chmod=+x", ".github/workflows/security-check.yml")
        git(self.r.dir, "commit", "-q", "-m", "chmod")
        self.assertFails(".github/workflows/security-check.yml")

    def test_a_non_utf8_comment_edit_to_the_snapshot_passes(self):
        (self.r.dir / "security" / "public-routes.txt").write_bytes(b"# caf\xe9\nGET /v1/health\n")
        self.r.commit("latin-1 comment")
        self.assertPasses()

    def test_a_deleted_guarded_file_needs_a_signature(self):
        git(self.r.dir, "rm", "-q", ".github/workflows/security-check.yml")
        self.r.commit("drop the check")
        self.assertFails(".github/workflows/security-check.yml")
        git(self.r.dir, "reset", "-q", "--hard", "HEAD~1")
        git(self.r.dir, "rm", "-q", ".github/workflows/security-check.yml")
        self.r.commit("drop the check, signed", key=self.r.trusted)
        self.assertPasses()

    def test_a_rename_into_security_needs_a_signature(self):
        git(self.r.dir, "mv", "app/handlers.py", "security/handlers.py")
        self.r.commit("move into security")
        self.assertFails("security/handlers.py")

    def test_an_evil_merge_editing_a_guarded_file_fails(self):
        git(self.r.dir, "checkout", "-q", "main")
        self.r.write("app/other.py", "y = 1\n")
        self.r.commit("main moves")
        git(self.r.dir, "checkout", "-q", "pr")
        git(self.r.dir, "merge", "-q", "--no-commit", "main")
        self.r.append("security/public-routes.txt", "GET /v1/slipped-in\n")
        git(self.r.dir, "add", "-A")
        git(self.r.dir, "commit", "-q", "-m", "merge main")
        self.assertFails("security/public-routes.txt")

    def test_several_signed_commits_and_an_unrelated_unsigned_one_pass(self):
        self.r.append("security/public-routes.txt", "GET /v1/a\n")
        self.r.commit("one", key=self.r.trusted)
        self.r.write("security/config.json", "{}\n")
        self.r.commit("two", key=self.r.trusted)
        self.r.write("app/handlers.py", "x = 9\n")
        self.r.commit("unrelated, unsigned")
        self.assertPasses()

    def test_the_refusal_names_the_file_and_the_head(self):
        self.r.append("security/public-routes.txt", "GET /v1/new\n")
        self.r.commit("unsigned")
        res = self.r.verify()
        self.assertIn("security/public-routes.txt", res.stdout)
        self.assertIn(self.r.head()[:12], res.stdout)

    # Security review findings, 2026-11-06 (T027, viper). What lands is a three-way merge against the
    # base tip, so the verifier judges that tree, and a signature counts only on a commit that
    # already contains the base it is judged against.

    def test_a_criss_cross_merge_rolling_back_a_guarded_file_fails(self):
        self.g("checkout", "-q", "main")
        self.r.write("security/rule.yml", "0\n")
        self.r.commit("config starts at 0", key=self.r.trusted)
        self.g("checkout", "-q", "-b", "feat")
        self.r.write("security/rule.yml", "A\n")
        self.r.commit("feat sets A", key=self.r.trusted)
        p2 = self.r.head()
        self.g("checkout", "-q", "main")
        self.r.write("app/other.py", "y = 1\n")
        self.r.commit("main moves")
        p1 = self.r.head()
        self.g("merge", "-q", "--no-ff", "--no-edit", "feat")
        self.r.base = self.r.head()  # base tip holds A, through a merge commit
        self.g("checkout", "-q", "-b", "atk", p1)
        self.g("merge", "-q", "--no-commit", "--no-ff", p2)
        self.r.write("security/rule.yml", "0\n")
        self.g("add", "-A")
        self.g("commit", "-q", "-m", "merge the other way, config back to nothing")
        self.assertFails("security/rule.yml")

    def test_replaying_an_old_signed_commit_fails(self):
        self.g("checkout", "-q", "main")
        self.g("checkout", "-q", "-b", "pr1")
        self.r.write("security/rule.yml", "F1\n")
        self.r.commit("signed F1, later fixed", key=self.r.trusted)
        s1 = self.r.head()
        self.g("checkout", "-q", "main")
        self.r.write("security/rule.yml", "F1\n")
        self.r.commit("squash of pr1")
        self.r.write("security/rule.yml", "F2\n")
        self.r.commit("signed fix", key=self.r.trusted)
        self.r.base = self.r.head()
        self.g("checkout", "-q", "-b", "replay", s1)
        self.g("merge", "-q", "-s", "ours", "--no-edit", self.r.base)
        self.assertFails("security/rule.yml")

    def test_a_pull_request_that_conflicts_with_its_base_fails(self):
        self.r.write("security/config.json", "pr\n")
        self.r.commit("pr side", key=self.r.trusted)
        git(self.r.dir, "checkout", "-q", "main")
        self.r.write("security/config.json", "main\n")
        self.r.commit("main side", key=self.r.trusted)
        self.r.base = self.r.head()
        git(self.r.dir, "checkout", "-q", "pr")
        self.assertFails("conflicts")

    def test_merging_base_in_after_signing_needs_the_merge_signed(self):
        self.r.append("security/public-routes.txt", "GET /v1/new\n")
        self.r.commit("signed on the old base", key=self.r.trusted)
        git(self.r.dir, "checkout", "-q", "main")
        self.r.write("app/other.py", "y = 1\n")
        self.r.commit("main moves")
        self.r.base = self.r.head()
        git(self.r.dir, "checkout", "-q", "pr")
        git(self.r.dir, "merge", "-q", "--no-edit", "main")
        self.assertFails("security/public-routes.txt")
        git(self.r.dir, "-c", "gpg.format=ssh", "-c", f"user.signingkey={self.r.trusted}",
            "commit", "-q", "--amend", "--no-edit", "-S")
        self.assertPasses()

    # Pat's ruling, 2026-11-06, after the re-review: every workflow is guarded, because no text check
    # can stop another workflow reporting under a required job name (it can take its name from the
    # PR title). One exemption: a change that only moves the @ref of existing `uses:` lines in a
    # workflow that is not a security or deploy workflow, which is what Dependabot sends.

    def test_an_unsigned_change_to_ordinary_ci_fails(self):
        self.r.write(".github/workflows/ci.yml", "name: ci\non: push\n")
        self.r.commit("a person edits CI")
        self.assertFails(".github/workflows/ci.yml")

    def test_a_workflow_reporting_under_a_required_name_fails_however_it_is_spelt(self):
        for text in ('jobs:\n  "security-check":\n    runs-on: ubuntu-latest\n',
                     "jobs:\n  security-check: # ok\n    runs-on: ubuntu-latest\n",
                     "jobs: {security-check: {runs-on: ubuntu-latest}}\n",
                     "jobs:\n  x:\n    name: ${{ github.event.pull_request.title }}\n"):
            with self.subTest(text=text):
                self.r.write(".github/workflows/x.yml", text)
                self.r.commit("a second job under a required name")
                self.assertFails(".github/workflows/x.yml")
                self.g("reset", "-q", "--hard", "HEAD~1")

    def _ci(self, uses):
        return ("name: ci\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n"
                f"      - uses: {uses}\n      - run: make test\n")

    DEPENDABOT = {"author": "dependabot[bot]", "sender": "dependabot[bot]", "action": "synchronize"}

    def _bump_branch(self, before="actions/checkout@" + "a" * 40 + " # v4.1.0", ci=None):
        self.g("checkout", "-q", "main")
        self.r.write(".github/workflows/ci.yml", (ci or self._ci)(before))
        self.r.commit("CI exists on the base", key=self.r.trusted)
        self.r.base = self.r.head()
        self.g("checkout", "-q", "-b", "bump")

    def test_a_dependabot_ref_bump_to_ordinary_ci_passes_unsigned(self):
        self._bump_branch()
        self.r.write(".github/workflows/ci.yml", self._ci("actions/checkout@" + "b" * 40 + " # v4.2.0"))
        self.r.commit("Bump actions/checkout from 4.1.0 to 4.2.0")
        self.assertPasses(**self.DEPENDABOT)
        self.r.write(".github/workflows/ci.yml", self._ci("evil/checkout@" + "b" * 40 + " # v4.2.0"))
        self.r.commit("a different action under the bump's cover")
        self.assertFails(".github/workflows/ci.yml", **self.DEPENDABOT)

    def test_a_ref_bump_from_anyone_but_dependabot_needs_a_signature(self):
        # Security re-review 3, 2026-11-06: a SHA that exists only in a fork resolves through the
        # parent's path, so the same action path is not the same publisher. Only Dependabot's own
        # pull requests, pushed only by Dependabot, are exempt.
        self._bump_branch()
        self.r.write(".github/workflows/ci.yml", self._ci("actions/checkout@" + "b" * 40 + " # v4.2.0"))
        self.r.commit("Bump actions/checkout from 4.1.0 to 4.2.0")
        for who in ({}, {"author": "someone"}, {"author": "dependabot[bot]"},
                    {"author": "dependabot[bot]", "sender": "someone"},
                    {"author": "someone", "sender": "dependabot[bot]"}, {"author": "", "sender": ""}):
            with self.subTest(who=who):
                self.assertFails(".github/workflows/ci.yml", **who)

    def test_a_dependabot_bump_that_is_not_only_refs_needs_a_signature(self):
        self._bump_branch(before="actions/checkout@v4")
        for after in ("actions/checkout@$(curl evil)", "actions/checkout@${{ github.head_ref }}",
                      "actions/checkout@v4\f      - run: curl evil"):
            with self.subTest(after=after):
                self.r.write(".github/workflows/ci.yml", self._ci(after))
                self.r.commit("not only a ref")
                self.assertFails(".github/workflows/ci.yml", **self.DEPENDABOT)
                self.g("reset", "-q", "--hard", "HEAD~1")

    def test_a_dependabot_bump_to_a_reusable_workflow_needs_a_signature(self):
        # Security re-review 4: flow style, quoted and escaped keys all declare workflow_call.
        for trigger in ("on:\n  workflow_call:", "on: [workflow_call]", "on: ['workflow_call']",
                        'on:\n  "workflow_call":', 'on:\n  "workflow\\x5fcall":', 'on:\n  "workflow\\u005fcall":'):
            with self.subTest(trigger=trigger):
                self.setUp()
                reusable = lambda uses: self._ci(uses).replace("on: push", trigger)
                self._bump_branch(before="actions/checkout@v4", ci=reusable)
                self.r.write(".github/workflows/ci.yml", reusable("actions/checkout@v5"))
                self.r.commit("bump")
                self.assertFails(".github/workflows/ci.yml", **self.DEPENDABOT)
                self.tearDown()
        self.setUp()

    def test_the_exemption_holds_only_for_opened_and_synchronize(self):
        self._bump_branch()
        self.r.write(".github/workflows/ci.yml", self._ci("actions/checkout@" + "b" * 40 + " # v4.2.0"))
        self.r.commit("Bump actions/checkout from 4.1.0 to 4.2.0")
        for action in ("opened", "synchronize"):
            with self.subTest(action=action):
                self.assertPasses(**{**self.DEPENDABOT, "action": action})
        for action in ("edited", "reopened", "", None):
            with self.subTest(action=action):
                who = {**self.DEPENDABOT, "action": action}
                self.assertFails(".github/workflows/ci.yml", **who)

    def test_a_ref_bump_to_a_deploy_workflow_still_needs_a_signature(self):
        self.g("checkout", "-q", "main")
        self.r.write("security/config.json", '{"deploy_workflows": [".github/workflows/deploy.yml"]}\n')
        self.r.write(".github/workflows/deploy.yml", self._ci("actions/checkout@v4"))
        self.r.commit("deploy exists on the base", key=self.r.trusted)
        self.r.base = self.r.head()
        self.g("checkout", "-q", "-b", "bump")
        self.r.write(".github/workflows/deploy.yml", self._ci("actions/checkout@v5"))
        self.r.commit("bump")
        self.assertFails(".github/workflows/deploy.yml", **self.DEPENDABOT)

    def test_a_malformed_deploy_list_widens_the_guard(self):
        self.g("checkout", "-q", "main")
        self.r.write("security/config.json", '{"deploy_workflows": ".github/workflows/ci.yml"}\n')
        self.r.write(".github/workflows/ci.yml", self._ci("actions/checkout@v4"))
        self.r.commit("a list that is not a list", key=self.r.trusted)
        self.r.base = self.r.head()
        self.g("checkout", "-q", "-b", "bump")
        self.r.write(".github/workflows/ci.yml", self._ci("actions/checkout@v5"))
        self.r.commit("bump")
        self.assertFails(".github/workflows/ci.yml", **self.DEPENDABOT)

    def test_a_deploy_workflow_the_base_lists_needs_a_signature(self):
        self.g("checkout", "-q", "main")
        self.r.write("security/config.json", '{"deploy_workflows": [".github/workflows/deploy.yml"]}\n')
        self.r.write(".github/workflows/deploy.yml", "name: deploy\n")
        self.r.commit("list the deploy workflow", key=self.r.trusted)
        self.r.base = self.r.head()
        self.g("checkout", "-q", "-b", "deploy-edit")
        self.r.write(".github/workflows/deploy.yml", "name: deploy\non: push\n")
        self.r.commit("edit the deploy workflow")
        self.assertFails(".github/workflows/deploy.yml")

    def test_the_refusal_names_its_cause(self):
        self.r.append("security/public-routes.txt", "GET /v1/new\n")
        self.r.commit("unsigned")
        self.assertFails("no commit in the pull request is signed by a key")
        self.g("reset", "-q", "--hard", "HEAD~1")
        self.r.append("security/public-routes.txt", "GET /v1/new\n")
        self.r.commit("signed", key=self.r.trusted)
        self.r.append("security/public-routes.txt", "GET /v1/more\n")
        self.r.commit("unsigned on top")
        self.assertFails("differs from every signed commit")
        self.g("reset", "-q", "--hard", "HEAD~1")
        self.g("checkout", "-q", "main")
        self.r.write("app/other.py", "y = 1\n")
        self.r.commit("main moves")
        self.r.base = self.r.head()
        self.g("checkout", "-q", "pr")
        self.g("merge", "-q", "--no-edit", "main")
        self.assertFails("built on an older base")

    def test_an_invalid_utf8_guarded_path_is_not_covered_by_an_unrelated_signature(self):
        self.r.write("app/g.txt", "signed\n")
        self.r.commit("an owner-signed commit that touches no guarded file", key=self.r.trusted)
        oid = git(self.r.dir, "hash-object", "-w", "app/g.txt").stdout.strip()
        subprocess.run([b"git", b"-C", bytes(self.r.dir), b"update-index", b"--add", b"--cacheinfo",
                        b"100644," + oid.encode() + b",security/\xff.json"],
                       check=True, env=CLEAN_ENV, capture_output=True)
        self.g("commit", "-q", "-m", "unsigned, a path that is not UTF-8")
        self.assertFails()

    def test_landing_part_of_a_signed_commit_fails(self):
        self.r.write("security/config.json", "{}\n")
        self.r.write("security/rule.yml", "rules: []\n")
        self.r.commit("both files", key=self.r.trusted)
        self.r.base = self.r.head()
        self.g("checkout", "-q", "-b", "partial")
        self.g("rm", "-q", "security/rule.yml")
        self.r.write("security/config.json", '{"strict": true}\n')
        self.r.commit("owner drops the rule and tightens config together", key=self.r.trusted)
        self.r.write("security/config.json", "{}\n")
        self.r.commit("keep the drop, undo the tightening")
        self.assertFails("security/rule.yml")

    def test_an_unsigned_route_removal_on_top_of_a_signed_change_passes(self):
        self.r.write("security/config.json", "{}\n")
        self.r.commit("signed config", key=self.r.trusted)
        self.r.write("security/public-routes.txt", "")
        self.r.commit("drop a public route, unsigned")
        self.assertPasses()

    def test_the_guarded_directory_replaced_by_a_symlink_is_itself_guarded(self):
        self.g("rm", "-q", "-r", "security")
        (self.r.dir / "security").symlink_to("app")
        self.r.commit("security is now a link")
        self.assertFails("REFUSED security:")

    def test_an_unknown_ref_is_an_error_not_a_pass(self):
        res = subprocess.run([sys.executable, str(VERIFY), "--repo", str(self.r.dir),
                              "--base", "0" * 40, "--head", self.r.head()],
                             capture_output=True, text=True, env=CLEAN_ENV)
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)


if __name__ == "__main__":
    unittest.main()
