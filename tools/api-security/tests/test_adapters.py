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
        self.assertEqual(got, {("GET", "/v1/health"), ("GET", "/v1/patterns/{user_id}")})

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
        tf = fixture.TERRAFORM.split('resource "aws_apigatewayv2_route" "patterns"')[0]
        r = fixture.run_check(fixture.project(terraform=tf))
        self.assertEqual(r.returncode, 1)
        self.assertIn("GET /v1/patterns/{user_id}", r.stdout)
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

    def test_dispatch_adapter_both_directions(self):
        table = 'ROUTES = {"GET /v1/health": None, "GET /v1/patterns/{user_id}": None, "DELETE /v1/x": None}\n'
        r = fixture.run_check(fixture.project(adapter={"kind": "dispatch", "table": "app.table:ROUTES"},
                                              extra={"app/table.py": table}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("DELETE /v1/x", r.stdout)
        table_ok = 'ROUTES = {("GET", "/v1/health"): None, ("GET", "/v1/patterns/{user_id}"): None}\n'
        r = fixture.run_check(fixture.project(adapter={"kind": "dispatch", "table": "app.table:ROUTES"},
                                              extra={"app/table.py": table_ok}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_broken_config_is_an_error_not_a_pass(self):
        root = fixture.project()
        (root / "security" / "config.json").write_text("{not json")
        r = fixture.run_check(root)
        self.assertNotEqual(r.returncode, 0)

    def test_a_handler_module_that_fails_to_import_is_an_error(self):
        r = fixture.run_check(fixture.project(handlers="raise RuntimeError('boom')\n"))
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
