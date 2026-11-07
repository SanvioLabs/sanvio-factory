"""Build throwaway projects for the check's tests, and run the check against them."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import _path

ROLES = '''
from api_security import registry
TOKENS = {"tok-alice": {"sub": "alice"}, "tok-bob": {"sub": "bob"}}
def _user(event):
    auth = (event.get("headers") or {}).get("authorization", "")
    return TOKENS.get(auth.replace("Bearer ", "", 1))
registry.register_role("user", _user)
registry.register_ownership(lambda identity, param, value: identity["sub"] == value)
'''

HANDLERS = '''
import json
from api_security import Router, public, role
router = Router()

@router.route("GET /v1/health")
@public(reason="health check, returns no data")
def health(event, identity):
    return {"statusCode": 200, "body": "ok"}

@router.route("GET /v1/records/{user_id}")
@role("user", owns="user_id")
def records(event, identity):
    return {"statusCode": 200, "body": json.dumps({"sub": identity["sub"]})}
'''

TERRAFORM = '''
resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "GET /v1/health"
}
resource "aws_apigatewayv2_route" "records" {
  api_id             = aws_apigatewayv2_api.api.id
  route_key          = "GET /v1/records/{user_id}"
  authorization_type = "JWT"
}
'''


def project(handlers=HANDLERS, terraform=TERRAFORM, snapshot="GET /v1/health\n", adapter=None, extra=None,
            handler_modules=None):
    root = Path(tempfile.mkdtemp(prefix="api-security-"))
    (root / "app").mkdir()
    (root / "app" / "__init__.py").write_text("")
    (root / "app" / "roles.py").write_text(textwrap.dedent(ROLES))
    (root / "app" / "handlers.py").write_text(textwrap.dedent(handlers))
    (root / "infra").mkdir()
    (root / "infra" / "main.tf").write_text(textwrap.dedent(terraform))
    (root / "security").mkdir()
    if snapshot is not None:
        (root / "security" / "public-routes.txt").write_text(snapshot)
    config = {
        "roles_module": "app.roles",
        "handler_modules": handler_modules or ["app.handlers"],
        "adapter": adapter or {"kind": "terraform", "paths": ["infra"]},
    }
    (root / "security" / "config.json").write_text(json.dumps(config))
    for rel, text in (extra or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(text))
    return root


def run_check(root, *args):
    env = dict(os.environ, PYTHONPATH=str(_path.LIB))
    return subprocess.run([sys.executable, "-m", "api_security.check", "--root", str(root), *args],
                          capture_output=True, text=True, env=env, cwd=str(root))
