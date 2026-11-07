"""SPEC-034 REQ-004, REQ-009, REQ-010, AC-003, OBS-001: the router refuses what is not declared,
hands in identity from the verified credential only, and records every route it serves."""
import json
import unittest

import _path  # noqa: F401  (imported for its sys.path side effect)

from api_security import registry
from api_security.decorators import public, role
from api_security.router import Router

TOKENS = {"tok-alice": {"sub": "alice"}, "tok-bob": {"sub": "bob"}}


def user_verifier(event):
    auth = (event.get("headers") or {}).get("authorization", "")
    return TOKENS.get(auth.replace("Bearer ", "", 1))


def event(route_key, token=None, body=None, path_params=None):
    method, path = route_key.split(" ", 1)
    headers = {"authorization": f"Bearer {token}"} if token else {}
    return {
        "routeKey": route_key,
        "headers": headers,
        "pathParameters": path_params or {},
        "body": json.dumps(body) if body is not None else None,
    }


class RouterTests(unittest.TestCase):
    def setUp(self):
        registry.reset()
        registry.register_role("user", user_verifier)
        registry.register_ownership(lambda identity, param, value: identity["sub"] == value)
        self.router = Router()

        @self.router.route("GET /v1/health")
        @public(reason="health check, returns no data")
        def health(event, identity):
            return {"statusCode": 200, "body": "ok"}

        @self.router.route("GET /v1/records/{user_id}")
        @role("user", owns="user_id")
        def records(event, identity):
            return {"statusCode": 200, "body": json.dumps({"sub": identity["sub"]})}

        @self.router.route("POST /v1/summarize")
        @role("user")
        def summarize(event, identity):
            return {"statusCode": 200, "body": json.dumps({"sub": identity["sub"]})}

        @self.router.route("POST /v1/forgotten")
        def forgotten(event, identity):
            return {"statusCode": 200, "body": "should never run"}

    def call(self, *args, **kwargs):
        return self.router.handle(event(*args, **kwargs), None)

    def test_an_undeclared_handler_is_refused_and_logged_without_the_body(self):
        with self.assertLogs("api_security", level="WARNING") as logs:
            resp = self.call("POST /v1/forgotten", token="tok-alice", body={"secret": "SHOULD-NOT-APPEAR"})
        self.assertEqual(resp["statusCode"], 403)
        joined = "\n".join(logs.output)
        self.assertIn("api_security.undeclared method=POST path=/v1/forgotten", joined)
        self.assertNotIn("SHOULD-NOT-APPEAR", joined)

    def test_public_route_needs_no_credential(self):
        self.assertEqual(self.call("GET /v1/health")["statusCode"], 200)

    def test_role_route_with_no_credential_is_401(self):
        self.assertEqual(self.call("POST /v1/summarize")["statusCode"], 401)

    def test_role_route_with_an_unrecognised_credential_is_403(self):
        self.assertEqual(self.call("POST /v1/summarize", token="tok-mallory")["statusCode"], 403)

    def test_owns_refuses_another_users_resource(self):
        resp = self.call("GET /v1/records/{user_id}", token="tok-bob", path_params={"user_id": "alice"})
        self.assertEqual(resp["statusCode"], 403)
        resp = self.call("GET /v1/records/{user_id}", token="tok-alice", path_params={"user_id": "alice"})
        self.assertEqual(resp["statusCode"], 200)

    def test_identity_comes_from_the_credential_not_the_body(self):
        resp = self.call("POST /v1/summarize", token="tok-alice", body={"user_id": "bob"})
        self.assertEqual(json.loads(resp["body"])["sub"], "alice")

    def test_unknown_route_is_404(self):
        self.assertEqual(self.call("GET /v1/nowhere")["statusCode"], 404)

    def test_registry_records_every_route_with_its_policy(self):
        got = {(r.method, r.path): (r.policy.kind if r.policy else None) for r in registry.routes()}
        self.assertEqual(got, {
            ("GET", "/v1/health"): "public",
            ("GET", "/v1/records/{user_id}"): "role",
            ("POST", "/v1/summarize"): "role",
            ("POST", "/v1/forgotten"): None,
        })

    def test_a_verifier_that_raises_is_a_refusal_not_a_pass(self):
        def broken(event):
            raise RuntimeError("verifier blew up")
        registry.reset()
        registry.register_role("user", broken)
        self.assertIn(self.call("POST /v1/summarize", token="tok-alice")["statusCode"], (401, 403))

    # review-spec, 2026-11-06 (T032): only an identity is an identity.

    def test_a_verifier_result_that_is_not_an_identity_is_refused(self):
        def coroutine_like(event):
            async def later():
                return None
            return later()
        for result in (False, True, {}, "", 0, []):
            with self.subTest(result=result):
                registry.reset()
                registry.register_role("user", lambda event, r=result: r)
                self.assertIn(self.call("POST /v1/summarize")["statusCode"], (401, 403))
                self.assertIn(self.call("POST /v1/summarize", token="tok-alice")["statusCode"], (401, 403))
        registry.reset()
        registry.register_role("user", coroutine_like)
        self.assertEqual(self.call("POST /v1/summarize", token="tok-alice")["statusCode"], 403)

    def test_an_async_verifier_is_refused_at_registration(self):
        async def verify(event):
            return {"sub": "alice"}
        with self.assertRaises(ValueError):
            registry.register_role("staff", verify)

    def test_registering_a_role_or_the_ownership_test_twice_differently_raises(self):
        registry.register_role("user", user_verifier)  # the same callable again is fine
        with self.assertRaises(ValueError):
            registry.register_role("user", lambda event: {"sub": "anyone"})
        with self.assertRaises(ValueError):
            registry.register_ownership(lambda identity, param, value: True)

    # Security re-review, 2026-11-06: the ownership test and tuple-shaped results.

    def test_a_tuple_or_list_verifier_result_is_refused(self):
        for result in ((False, None), [None], ("alice",)):
            with self.subTest(result=result):
                registry.reset()
                registry.register_role("user", lambda event, r=result: r)
                self.assertIn(self.call("POST /v1/summarize")["statusCode"], (401, 403))

    def test_an_ownership_answer_that_is_not_true_is_refused(self):
        def coroutine_like(identity, param, value):
            async def later():
                return False
            return later()
        for owns in (lambda i, p, v: "no", lambda i, p, v: 1, coroutine_like):
            with self.subTest(owns=owns):
                registry.reset()
                registry.register_role("user", user_verifier)
                registry.register_ownership(owns)
                resp = self.call("GET /v1/records/{user_id}", token="tok-bob", path_params={"user_id": "alice"})
                self.assertEqual(resp["statusCode"], 403)

    def test_an_async_ownership_test_is_refused_at_registration(self):
        async def owns(identity, param, value):
            return False
        registry.reset()
        with self.assertRaises(ValueError):
            registry.register_ownership(owns)

    def test_registration_is_exported(self):
        import api_security
        self.assertIs(api_security.register_role, registry.register_role)
        self.assertIs(api_security.register_ownership, registry.register_ownership)


if __name__ == "__main__":
    unittest.main()
