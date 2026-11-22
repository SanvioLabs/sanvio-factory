"""Run with: python3 -m unittest discover -s tests

Every secret here is invented, and each is built from pieces at run time, so no line of this file reads as a
real credential to a scanner.
"""
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import usage_scrub  # noqa: E402 (needs scripts/ on the path first)

HOME = "/Users/someone"
AWS_KEY = "AK" + "IA" + "Q" * 16
GITHUB = "gh" + "p_" + "a1B2c3D4e5" * 4
GITHUB_PAT = "github" + "_pat_" + "11AAAAAAA0" + "x1Y2z3" * 5
SLACK = "xo" + "xb-" + "1234567890-" + "abcdefghij"
OPENAI = "s" + "k-" + "proj-" + "Zx9" * 10
ANTHROPIC = "s" + "k-ant-" + "api03-" + "Qw7" * 10
JWT = "ey" + "JhbGciOiJIUzI1NiJ9" + ".ey" + "JzdWIiOiIxIn0" + ".c2lnbmF0dXJlLWhlcmU"
PEM = "-----BEGIN " + "PRIVATE KEY-----\nMIIEvQIBADAN\n-----END " + "PRIVATE KEY-----"
RANDOM = "q8Zr2LmX0vT4bN7cWd1Ye5Hs9Kp3Jf6U"  # 32 characters, mixed letters and digits
SLASHED = "q8Zr2LmX0v" + "/T4bN7cWd1Y" + "/e5Hs9Kp3Jf6Ub2Mn"  # a 40-character cloud secret key's shape


def scrub(command):
    return usage_scrub.scrub(command, HOME)


class Secrets(unittest.TestCase):
    def assertRedacted(self, command, *secrets):
        got = scrub(command)
        self.assertIsNotNone(got, command)
        text, count = got
        for secret in secrets:
            self.assertNotIn(secret, text)
        self.assertIn("[redacted]", text)
        self.assertGreaterEqual(count, 1)
        return text

    def test_each_known_token_shape_is_redacted(self):
        for token in (AWS_KEY, GITHUB, GITHUB_PAT, SLACK, OPENAI, ANTHROPIC, JWT):
            with self.subTest(token=token[:6]):
                self.assertRedacted("tool login --with " + token, token)

    def test_a_pem_block_is_redacted_whole(self):
        text = self.assertRedacted("printf '%s' '" + PEM + "' > /tmp/x", "MIIEvQIBADAN", "BEGIN")
        self.assertIn("printf", text)

    def test_a_url_keeps_its_host_and_loses_its_user_and_password(self):
        text = self.assertRedacted("git clone https://bob:" + "hunter2@example.com/repo.git", "bob", "hunter2")
        self.assertIn("example.com/repo.git", text)

    def test_an_authorization_header_and_a_bearer_token_are_redacted(self):
        # Split so a secret scan doesn't read the made-up header as a real one.
        self.assertRedacted('curl -H "Authorization: Basic ' + 'dXNlcjpwYXNz" https://example.com', "dXNlcjpwYXNz")
        self.assertRedacted("curl -H 'Authorization: Bearer " + "abc.def.ghi' https://example.com", "abc.def.ghi")

    def test_a_secret_named_environment_value_is_redacted_and_its_name_kept(self):
        text = self.assertRedacted("MY_API_KEY=plainvalue123 STRIPE_SECRET=other ./run.sh", "plainvalue123", "other")
        self.assertIn("MY_API_KEY=", text)
        self.assertIn("./run.sh", text)

    def test_an_ordinary_environment_value_is_kept(self):
        self.assertEqual(scrub("DEBUG=1 python3 app.py"), ("DEBUG=1 python3 app.py", 0))

    def test_a_secret_flag_value_is_redacted(self):
        self.assertRedacted("mysql --password=letmein -u root", "letmein")
        self.assertRedacted("tool --token abc123 run", "abc123")

    def test_a_long_random_run_is_redacted(self):
        self.assertRedacted("deploy --key-id " + RANDOM, RANDOM)

    def test_quoted_flag_values_are_redacted(self):
        self.assertRedacted('tool --password "letmein now" run', "letmein")
        self.assertRedacted("tool --token 'abc123' run", "abc123")
        self.assertRedacted("tool --client-secret=s3cr3tvalue run", "s3cr3tvalue")

    def test_a_slash_bearing_secret_key_is_redacted(self):
        self.assertRedacted("aws configure set aws_secret_access_key " + SLASHED, SLASHED, "q8Zr2")
        self.assertRedacted("export X=1; tool --with " + SLASHED, SLASHED)

    def test_user_passwords_and_short_password_flags_are_redacted(self):
        self.assertRedacted("curl -u bob:" + "hunter2 https://example.com", "hunter2")
        self.assertRedacted("curl --user bob:" + "hunter2 https://example.com", "hunter2")
        self.assertRedacted("mysql -u root -p" + "letmein db", "letmein")
        self.assertRedacted("sshpass -p " + "letmein ssh host", "letmein")

    def test_key_headers_and_pass_named_values_are_redacted(self):
        self.assertRedacted('curl -H "X-Api-Key: ' + 'abc123def" https://example.com', "abc123def")
        self.assertRedacted("curl -H 'Cookie: session=" + "abc123def' https://example.com", "abc123def")
        text = self.assertRedacted("DB_PASS=" + "letmein ./run.sh", "letmein")
        self.assertIn("DB_PASS=", text)

    def test_paths_and_ordinary_slashes_are_kept(self):
        for command in ("ls /usr/local/lib/python3.9/site-packages/someLongPackage2/module.py",
                        "git log origin/main..feature/AddTheThing2Quickly/forReal",
                        "python3 scripts/export.py --since 2026-11-01"):
            with self.subTest(command=command):
                self.assertEqual(scrub(command), (command, 0))

    def test_long_ordinary_words_and_paths_are_kept(self):
        command = "python3 -m unittest tests.test_usage_scrub_and_everything_else_in_the_suite"
        self.assertEqual(scrub(command), (command, 0))


class Dropped(unittest.TestCase):
    def test_a_command_reaching_a_project_or_client_folder_is_dropped(self):
        for command in ("cat projects/acme/README.md", "cd ~/work/clients/acme && ls", "ls ./projects/"):
            with self.subTest(command=command):
                self.assertIsNone(scrub(command))

    def test_a_bare_or_differently_cased_folder_is_dropped(self):
        for command in ("cd clients", "ls projects", "cat ./Clients/Foo/notes.md", "cd PROJECTS && ls"):
            with self.subTest(command=command):
                self.assertIsNone(scrub(command))

    def test_a_word_that_only_contains_projects_is_kept(self):
        self.assertIsNotNone(scrub("python3 scripts/list_myprojects.py"))

    def test_a_credential_file_or_secret_command_is_dropped(self):
        for command in ("cat .env", "less ~/.aws/credentials", "gh auth token", "printenv",
                        "aws secretsmanager get-secret-value --secret-id x"):
            with self.subTest(command=command):
                self.assertIsNone(scrub(command))


class Shape(unittest.TestCase):
    def test_the_home_folder_becomes_a_tilde(self):
        self.assertEqual(scrub("ls /Users/someone/code"), ("ls ~/code", 0))

    def test_a_long_command_is_cut_to_500_characters(self):
        text, _ = scrub("echo " + "word " * 300)
        self.assertEqual(len(text), usage_scrub.MAX_LENGTH)

    def test_the_cut_never_splits_a_placeholder(self):
        for pad in range(450, 500):
            with self.subTest(pad=pad):
                text, _ = scrub("echo " + "y" * pad + " Authorization: Bearer abcdefgh")
                self.assertLessEqual(len(text), usage_scrub.MAX_LENGTH)
                placeholder = usage_scrub.REDACTED
                self.assertFalse(any(text.endswith(placeholder[:k]) for k in range(1, len(placeholder))), text[-20:])
                self.assertEqual(scrub(text), (text, 0))

    def test_scrubbing_twice_changes_nothing_the_second_time(self):
        once = scrub("MY_TOKEN=abc curl -H 'Authorization: Bearer x.y.z' https://u:" + "p@example.com " + GITHUB)
        self.assertEqual(scrub(once[0]), (once[0], 0))

    def test_it_is_fast_enough_to_run_on_every_shell_command(self):
        command = "git -C /Users/someone/code log --oneline -n 20 | head -5 && MY_TOKEN=abc ./x " + GITHUB
        start = time.perf_counter()
        for _ in range(1000):
            scrub(command)
        per_call_ms = (time.perf_counter() - start)  # seconds for 1,000 calls is ms per call
        self.assertLess(per_call_ms, 5, "NFR-004 leaves 50 ms for the whole hook")


if __name__ == "__main__":
    unittest.main()
