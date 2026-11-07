"""SPEC-034 REQ-012, AC-006, SEC-004: declared routes against deployed routes, both adapters."""
import unittest
from pathlib import Path

import _path  # noqa: F401  (imported for its sys.path side effect)
import fixture

from api_security.adapters import AdapterError, terraform_apigw


class TerraformAdapterTests(unittest.TestCase):
    def test_reads_literal_route_keys(self):
        root = fixture.project()
        got = terraform_apigw.deployed_routes(root, ["infra"])
        self.assertEqual(got, {("GET", "/v1/health"), ("GET", "/v1/records/{user_id}")})

    def test_an_interpolated_route_key_fails_closed(self):
        tf = 'resource "aws_apigatewayv2_route" "r" {\n  route_key = "GET ${var.prefix}/x"\n}\n'
        root = fixture.project(terraform=tf)
        with self.assertRaises(AdapterError):
            terraform_apigw.deployed_routes(root, ["infra"])

    def test_a_computed_route_key_fails_closed(self):
        tf = 'resource "aws_apigatewayv2_route" "r" {\n  for_each  = local.routes\n  route_key = each.key\n}\n'
        root = fixture.project(terraform=tf)
        with self.assertRaises(AdapterError):
            terraform_apigw.deployed_routes(root, ["infra"])

    def test_a_catch_all_route_fails_closed(self):
        tf = 'resource "aws_apigatewayv2_route" "r" {\n  route_key = "$default"\n}\n'
        root = fixture.project(terraform=tf)
        with self.assertRaises(AdapterError):
            terraform_apigw.deployed_routes(root, ["infra"])

    def test_a_missing_directory_fails_closed(self):
        root = fixture.project()
        with self.assertRaises(AdapterError):
            terraform_apigw.deployed_routes(root, ["no-such-dir"])


class CheckAgainstDeployedTests(unittest.TestCase):
    def test_matching_routes_pass(self):
        r = fixture.run_check(fixture.project())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_deployed_route_with_no_handler_fails(self):
        tf = fixture.TERRAFORM + 'resource "aws_apigatewayv2_route" "old" {\n  route_key = "POST /v1/voice/twiml"\n}\n'
        r = fixture.run_check(fixture.project(terraform=tf))
        self.assertEqual(r.returncode, 1)
        self.assertIn("POST /v1/voice/twiml", r.stdout)
        self.assertIn("deployed with no declared handler", r.stdout)

    def test_a_handler_with_no_deployed_route_fails(self):
        tf = fixture.TERRAFORM.split('resource "aws_apigatewayv2_route" "records"')[0]
        r = fixture.run_check(fixture.project(terraform=tf))
        self.assertEqual(r.returncode, 1)
        self.assertIn("GET /v1/records/{user_id}", r.stdout)
        self.assertIn("declared with no deployed route", r.stdout)

    def test_an_undeclared_handler_fails(self):
        handlers = fixture.HANDLERS + '''
@router.route("POST /v1/forgotten")
def forgotten(event, identity):
    return {"statusCode": 200}
'''
        tf = fixture.TERRAFORM + 'resource "aws_apigatewayv2_route" "f" {\n  route_key = "POST /v1/forgotten"\n}\n'
        r = fixture.run_check(fixture.project(handlers=handlers, terraform=tf))
        self.assertEqual(r.returncode, 1)
        self.assertIn("POST /v1/forgotten", r.stdout)
        self.assertIn("no declaration", r.stdout)

    def test_dispatch_adapter_reads_the_router_and_refuses_a_plain_table(self):
        # review-spec, 2026-11-06 (T036): a plain table cannot show requests go through Router.handle.
        ok = fixture.run_check(fixture.project(adapter={"kind": "dispatch", "table": "app.handlers:router"}))
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        table = 'ROUTES = {"GET /v1/health": None, "GET /v1/records/{user_id}": None}\n'
        plain = fixture.run_check(fixture.project(adapter={"kind": "dispatch", "table": "app.table:ROUTES"},
                                                  extra={"app/table.py": table}))
        self.assertEqual(plain.returncode, 2, plain.stdout)
        self.assertIn("Router", plain.stdout)

    def test_dispatch_adapter_finds_a_route_declared_on_another_router(self):
        other = ("from api_security import Router, role\nrouter = Router()\n"
                 "@router.route('DELETE /v1/x')\n@role('user')\ndef x(event, identity):\n    return {}\n")
        r = fixture.run_check(fixture.project(adapter={"kind": "dispatch", "table": "app.handlers:router"},
                                              extra={"app/other.py": other},
                                              handler_modules=["app.handlers", "app.other"]))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("DELETE /v1/x: declared with no deployed route", r.stdout)

    def test_a_broken_config_is_an_error_not_a_pass(self):
        root = fixture.project()
        (root / "security" / "config.json").write_text("{not json")
        r = fixture.run_check(root)
        self.assertNotEqual(r.returncode, 0)

    def test_a_handler_module_that_fails_to_import_is_an_error(self):
        r = fixture.run_check(fixture.project(handlers="raise RuntimeError('boom')\n"))
        self.assertNotEqual(r.returncode, 0)

# review-spec, 2026-11-06 (T036): Terraform the adapter cannot read is a failure, never a skip.
class TerraformUnreadableTests(unittest.TestCase):
    def assertRefused(self, terraform=fixture.TERRAFORM, extra=None, needle=None):
        root = fixture.project(terraform=terraform, extra=extra)
        with self.assertRaises(AdapterError) as ctx:
            terraform_apigw.deployed_routes(root, ["infra"])
        if needle:
            self.assertIn(needle, str(ctx.exception))

    def test_json_terraform(self):
        self.assertRefused(extra={"infra/routes.tf.json": "{}"}, needle="tf.json")

    def test_a_route_key_that_is_not_on_its_own_line(self):
        tf = fixture.TERRAFORM + 'resource "aws_apigatewayv2_route" "x" { route_key = "GET /v1/x" }\n'
        self.assertRefused(terraform=tf, needle="route_key")

    def test_a_function_url_rest_api_or_openapi_body(self):
        for tf in ('resource "aws_lambda_function_url" "u" {\n  authorization_type = "NONE"\n}\n',
                   'resource "aws_api_gateway_method" "m" {\n  http_method = "GET"\n}\n',
                   'resource "aws_apigatewayv2_api" "api" {\n  name = "x"\n  body = file("openapi.json")\n}\n',
                   'resource "aws_apigatewayv2_api" "api" {\n  name = "x"\n  target = aws_lambda_function.f.arn\n}\n'):
            with self.subTest(tf=tf.split(chr(10))[0]):
                self.assertRefused(terraform=fixture.TERRAFORM + tf)

    def test_a_route_outside_the_configured_paths(self):
        extra = {"modules/api/routes.tf": 'resource "aws_apigatewayv2_route" "x" {\n  route_key = "GET /v1/x"\n}\n'}
        self.assertRefused(extra=extra, needle="modules/api/routes.tf")

    # Security re-review, 2026-11-06: braces in strings, comments and heredocs; labels; other files.

    def test_body_or_target_hidden_behind_a_brace_is_still_seen(self):
        api = lambda inner: 'resource "aws_apigatewayv2_api" "x" {\n  name = "x"\n' + inner + '\n}\n'
        for inner in ('  description = "}"\n  body = file("o.json")',
                      '  # }\n  body = file("o.json")',
                      '  description = <<EOT\n}\nEOT\n  body = file("o.json")',
                      '  /* } */\n  body = file("o.json")',
                      '  tags = { a = "}" }\n  target = aws_lambda_function.f.arn'):
            with self.subTest(inner=inner):
                self.assertRefused(terraform=fixture.TERRAFORM + api(inner))
        for tf in ('resource aws_apigatewayv2_api x {\n  body = file("o.json")\n}\n',
                   'resource "aws_apigatewayv2_api" "x" { body = file("o.json") }\n'):
            with self.subTest(tf=tf):
                self.assertRefused(terraform=fixture.TERRAFORM + tf)

    def test_a_registry_module_building_routes_is_refused(self):
        tf = ('module "apigw" {\n  source = "terraform-aws-modules/apigateway-v2/aws"\n'
              '  routes = {\n    "GET /secret" = {}\n  }\n}\n')
        self.assertRefused(terraform=fixture.TERRAFORM + tf)

    def test_tofu_files_and_venv_folders_are_read(self):
        route = 'resource "aws_apigatewayv2_route" "h" {\n  route_key = "GET /hidden"\n}\n'
        for rel in ("infra/extra.tofu", "infra/venv/a/main.tf"):
            with self.subTest(rel=rel):
                root = fixture.project(extra={rel: route})
                self.assertIn(("GET", "/hidden"), terraform_apigw.deployed_routes(root, ["infra"]))

    def test_an_api_built_from_a_target_outside_the_paths_is_refused(self):
        tf = 'resource "aws_apigatewayv2_api" "z" {\n  name = "z"\n  target = "arn"\n}\n'
        self.assertRefused(extra={"other/x.tf": tf}, needle="target")

    def test_a_route_key_that_is_not_one_plain_string_is_refused(self):
        for line in ('route_key = "GET /a"=="x"?"GET/b":"POST/c"', '"route_key" = "GET /hidden"'):
            with self.subTest(line=line):
                tf = fixture.TERRAFORM + f'resource "aws_apigatewayv2_route" "q" {{\n  {line}\n}}\n'
                self.assertRefused(terraform=tf)

    def test_a_commented_out_route_is_not_deployed(self):
        tf = fixture.TERRAFORM + '/*\nroute_key = "GET /old"\n*/\n# route_key = "GET /older"\n'
        root = fixture.project(terraform=tf)
        self.assertEqual(len(terraform_apigw.deployed_routes(root, ["infra"])), 2)

    def test_an_api_with_a_name_only_is_still_read(self):
        tf = fixture.TERRAFORM + 'resource "aws_apigatewayv2_api" "api" {\n  name = "x"\n  protocol_type = "HTTP"\n}\n'
        root = fixture.project(terraform=tf)
        self.assertEqual(len(terraform_apigw.deployed_routes(root, ["infra"])), 2)


# review-spec, 2026-11-06 (T034): a role route reaching a resource by id says whose it is.
UNOWNED_TF = fixture.TERRAFORM + '''
resource "aws_apigatewayv2_route" "thing" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "GET /v1/things/{thing_id}"
}
'''


def _thing(declaration):
    return fixture.HANDLERS + (
        "\n@router.route('GET /v1/things/{thing_id}')\n"
        f"@{declaration}\n"
        "def thing(event, identity):\n"
        "    return {'statusCode': 200, 'body': 'x'}\n")


class OwnershipDeclarationTests(unittest.TestCase):
    def test_a_role_route_with_an_id_parameter_and_no_owns_fails(self):
        r = fixture.run_check(fixture.project(handlers=_thing('role("user")'), terraform=UNOWNED_TF))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("GET /v1/things/{thing_id}", r.stdout)
        self.assertIn("owns", r.stdout)

    def test_unowned_with_a_reason_passes(self):
        decl = 'role("user", unowned="things are a shared catalogue every user may read")'
        r = fixture.run_check(fixture.project(handlers=_thing(decl), terraform=UNOWNED_TF))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_unowned_needs_a_reason_and_excludes_owns(self):
        from api_security import registry
        from api_security.decorators import role
        registry.reset()
        registry.register_role("user", lambda event: None)
        for kwargs in ({"unowned": ""}, {"unowned": "x", "owns": "thing_id"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                role("user", **kwargs)


if __name__ == "__main__":
    unittest.main()
