"""SPEC-034 REQ-014, AC-005: generated tests prove 401 with no token, 403 for a caller without the
role, 403 for another user's resource under owns, and catch a route that skips its check."""
import os
import shutil
import subprocess
import sys
import unittest

import _path  # noqa: F401  (imported for its sys.path side effect)
import fixture

FIXTURES = '''
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app.roles  # registers the roles before the handlers load
from app.handlers import router

def token_for(role):
    return "tok-alice"

def token_without(roles):
    return "tok-mallory"

def owner_params(role, param):
    return "tok-alice", "alice", "bob"

def invoke(method, path, token, path_params):
    headers = {"authorization": "Bearer " + token} if token else {}
    event = {"routeKey": method + " " + path, "headers": headers, "pathParameters": path_params}
    return router.handle(event, None)["statusCode"]
'''

# A route whose handler is declared, but the project's own invoke bypasses the router for it,
# the way a hand-rolled dispatch can.
LEAKY = FIXTURES.replace(
    'def invoke(method, path, token, path_params):',
    'def invoke(method, path, token, path_params):\n'
    '    if path == "/v1/records/{user_id}":\n'
    '        return 200\n'
    '    return _real(method, path, token, path_params)\n\n'
    'def _real(method, path, token, path_params):')


def pytest_cmd():
    try:
        import pytest  # noqa: F401  (only probing whether this interpreter has it)
        return [sys.executable, "-m", "pytest"]
    except ImportError:
        uv = shutil.which("uv")
        return [uv, "run", "--no-project", "--with", "pytest", "python", "-m", "pytest"] if uv else None


def run_authz(root):
    cmd = pytest_cmd()
    if cmd is None:  # fail, never skip: a check that cannot run must not read as one that passed
        raise AssertionError("the generated authz tests need pytest, or uv to fetch it")
    env = dict(os.environ, PYTHONPATH=str(_path.LIB))
    return subprocess.run(cmd + ["-p", "api_security.authz", "-q", "-rA", "-p", "no:cacheprovider",
                                 str(root / "security" / "fixtures.py")],
                          capture_output=True, text=True, env=env, cwd=str(root))


class GeneratedAuthzTests(unittest.TestCase):
    def test_every_protected_route_gets_its_cases_and_they_pass(self):
        root = fixture.project(extra={"security/fixtures.py": FIXTURES})
        r = run_authz(root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("GET /v1/records/{user_id} no-token 401", out)
        self.assertIn("GET /v1/records/{user_id} without-role 403", out)
        self.assertIn("GET /v1/records/{user_id} not-owner 403", out)
        self.assertIn("GET /v1/records/{user_id} owner allowed", out)
        self.assertNotIn("GET /v1/health no-token", out)  # public routes get no refusal cases

    def test_a_route_that_skips_its_check_fails(self):
        root = fixture.project(extra={"security/fixtures.py": LEAKY})
        r = run_authz(root)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no-token", r.stdout)

    def test_missing_fixture_hooks_fail_rather_than_skip(self):
        root = fixture.project(extra={"security/fixtures.py": "import app.roles\nimport app.handlers\n"})
        r = run_authz(root)
        self.assertNotEqual(r.returncode, 0)

    # review-spec, 2026-11-06 (T033): coverage comes from security/config.json, not from what
    # fixtures.py happens to import.

    def test_a_role_route_in_a_module_the_fixtures_never_import_still_gets_its_cases(self):
        other = (
            "from api_security import Router, role\n"
            "router = Router()\n"
            "@router.route('GET /v1/export')\n"
            "@role('user')\n"
            "def export(event, identity):\n"
            "    return {'statusCode': 200, 'body': 'everyone'}\n"
        )
        wide_open = FIXTURES.replace(
            'def invoke(method, path, token, path_params):',
            'def invoke(method, path, token, path_params):\n'
            '    if path == "/v1/export":\n'
            '        return 200\n'
            '    return _real(method, path, token, path_params)\n\n'
            'def _real(method, path, token, path_params):')
        root = fixture.project(extra={"security/fixtures.py": wide_open, "app/other.py": other},
                               handler_modules=["app.handlers", "app.other"])
        r = run_authz(root)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("GET /v1/export no-token 401", r.stdout)

    def test_a_project_with_no_role_routes_passes(self):
        public_only = (
            "from api_security import Router, public\n"
            "router = Router()\n"
            "@router.route('GET /v1/health')\n"
            "@public(reason='health check, returns no data')\n"
            "def health(event, identity):\n"
            "    return {'statusCode': 200, 'body': 'ok'}\n"
        )
        hooks = FIXTURES.replace("import app.roles  # registers the roles before the handlers load\n", "")
        root = fixture.project(handlers=public_only, extra={"security/fixtures.py": hooks})
        r = run_authz(root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
