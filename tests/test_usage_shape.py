"""Run with: python3 -m unittest discover -s tests"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import usage_shape  # noqa: E402 (needs scripts/ on the path first)

RUN = {"v": 1, "run": "1-2026-11-20T09:00:00", "issue": 1, "project": None, "started": "2026-11-20T09:00:00",
       "ended": "2026-11-20T10:00:00", "outcome": "pr", "rounds": 2, "tests": ["fail", "pass"],
       "verdicts": ["CHANGES", "APPROVE"], "fix_reasons": None, "tests_changed": None, "tokens": 1200,
       "cost_usd": 0.42, "agent": "claude", "reviewer": "claude"}
USAGE = {"sessions": 1, "skills": {"review-pr": 1}, "agents": {}, "commands": {}, "guard_deny": {},
         "guard_ask": {}, "ask_approved": {}, "log_off": 0}
BUNDLE = {"v": 2, "kind": "bundle", "mode": "general", "exported": "2026-11-21", "since": "2026-11-07",
          "period": {"first": "2026-11-07", "last": "2026-11-21"}, "user": "someone", "node": "laptop",
          "factory": {"commit": "a" * 40, "changelog": "2026-11-21"},
          "loop_config": {"factory": {"agent": "claude", "reviewer": "claude", "max_workers": 1,
                                      "max_rounds": 5, "max_issue_tokens": 0}},
          "chain_head": "b" * 64, "bundle_id": "c" * 64, "loop": [RUN], "usage": USAGE}
COMMAND = {"ts": "2026-11-20T09:00:00Z", "session": "s1", "verdict": "ran", "text": "ls ~", "redactions": 0}
HEARTBEAT = {"v": 2, "kind": "heartbeat", "node": "node-1", "ts": "2026-11-21T09:00:00Z",
             "factory": {"commit": "a" * 40, "changelog": "2026-11-21"},
             "loops": [{"label": "factory", "alive": True, "waiting": 2, "issue": 5, "tokens": 900,
                        "budget": 10000}]}


class Bundles(unittest.TestCase):
    def test_a_general_bundle_has_no_problems(self):
        self.assertEqual(usage_shape.problems(BUNDLE), [])

    def test_a_detailed_bundle_needs_commands_and_a_general_one_refuses_them(self):
        detailed = dict(BUNDLE, mode="detailed", commands=[COMMAND])
        self.assertEqual(usage_shape.problems(detailed), [])
        self.assertTrue(usage_shape.problems(dict(BUNDLE, mode="detailed")))
        self.assertTrue(usage_shape.problems(dict(BUNDLE, commands=[COMMAND])))

    def test_an_unknown_key_is_a_problem_at_every_level(self):
        for path in ((), ("usage",), ("factory",), ("period",)):
            with self.subTest(path=path):
                bundle = copy.deepcopy(BUNDLE)
                target = bundle
                for key in path:
                    target = target[key]
                target["title"] = "Fix the payments bug for Acme"
                self.assertTrue(any("title" in p for p in usage_shape.problems(bundle)))
        bundle = copy.deepcopy(BUNDLE)
        bundle["loop"][0]["title"] = "x"
        self.assertTrue(usage_shape.problems(bundle))
        bundle = copy.deepcopy(BUNDLE)
        bundle["loop_config"]["factory"]["test_command"] = "x"
        self.assertTrue(usage_shape.problems(bundle))

    def test_a_missing_key_or_wrong_type_is_a_problem(self):
        bundle = copy.deepcopy(BUNDLE)
        del bundle["node"]
        self.assertTrue(usage_shape.problems(bundle))
        self.assertTrue(usage_shape.problems(dict(BUNDLE, v=1)))
        self.assertTrue(usage_shape.problems(dict(BUNDLE, mode="everything")))
        self.assertTrue(usage_shape.problems(dict(BUNDLE, usage=dict(USAGE, skills={"x": "many"}))))

    def test_a_command_record_is_held_to_its_keys(self):
        bad = dict(COMMAND, cwd="/Users/someone/projects/acme")
        self.assertTrue(usage_shape.problems(dict(BUNDLE, mode="detailed", commands=[bad])))
        self.assertTrue(usage_shape.problems(dict(BUNDLE, mode="detailed", commands=[dict(COMMAND, verdict="x")])))

    def test_something_that_is_not_an_object_is_a_problem(self):
        self.assertTrue(usage_shape.problems([]))
        self.assertTrue(usage_shape.problems({"kind": "letter"}))


class Heartbeats(unittest.TestCase):
    def test_a_heartbeat_has_no_problems_and_refuses_a_title(self):
        self.assertEqual(usage_shape.problems(HEARTBEAT), [])
        bad = copy.deepcopy(HEARTBEAT)
        bad["loops"][0]["title"] = "x"
        self.assertTrue(usage_shape.problems(bad))

    def test_an_idle_loop_has_no_issue(self):
        idle = copy.deepcopy(HEARTBEAT)
        idle["loops"][0].update(issue=None, tokens=None, budget=None)
        self.assertEqual(usage_shape.problems(idle), [])


class EveryFieldServesAQuestion(unittest.TestCase):
    def test_every_key_in_either_shape_is_mapped(self):
        for key in usage_shape.all_keys():
            with self.subTest(key=key):
                self.assertIn(key, usage_shape.SERVES)

    def test_each_mapping_names_a_question_or_says_why_it_is_envelope(self):
        for key, serves in usage_shape.SERVES.items():
            with self.subTest(key=key):
                self.assertTrue(serves)
                for item in serves:
                    self.assertTrue(item in usage_shape.QUESTIONS or item.startswith("envelope:"), item)

    def test_a_key_added_with_no_mapping_fails(self):
        original = usage_shape.BUNDLE_KEYS
        try:
            usage_shape.BUNDLE_KEYS = dict(original, unmapped=(str,))
            self.assertNotIn("unmapped", usage_shape.SERVES)
            self.assertIn("unmapped", usage_shape.all_keys())
        finally:
            usage_shape.BUNDLE_KEYS = original


if __name__ == "__main__":
    unittest.main()
