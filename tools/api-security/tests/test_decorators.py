"""SPEC-034 REQ-009, REQ-011, AC-004: the two declarations and what they refuse at load."""
import unittest

import _path  # noqa: F401  (imported for its sys.path side effect)

from api_security import registry
from api_security.decorators import UnknownRole, public, role


class DecoratorTests(unittest.TestCase):
    def setUp(self):
        registry.reset()
        registry.register_role("user", lambda event: None)

    def test_public_requires_a_reason(self):
        with self.assertRaises(TypeError):
            public()  # no reason at all
        for empty in ("", "   "):
            with self.assertRaises(ValueError):
                public(reason=empty)

    def test_role_with_no_registered_verifier_fails_at_decoration(self):
        with self.assertRaises(UnknownRole):
            @role("nobody-registered-this")
            def handler(event, identity):
                return {}

    def test_role_needs_at_least_one_role(self):
        with self.assertRaises(ValueError):
            role()

    def test_declarations_attach_their_policy(self):
        @public(reason="health check, no data")
        def health(event, identity):
            return {}

        @role("user", owns="user_id")
        def mine(event, identity):
            return {}

        self.assertEqual(health.__api_security__.kind, "public")
        self.assertEqual(health.__api_security__.reason, "health check, no data")
        self.assertEqual(mine.__api_security__.kind, "role")
        self.assertEqual(mine.__api_security__.roles, ("user",))
        self.assertEqual(mine.__api_security__.owns, "user_id")


if __name__ == "__main__":
    unittest.main()
