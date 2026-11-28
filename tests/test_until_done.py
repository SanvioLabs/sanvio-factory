"""Run with: python3 -m unittest discover -s tests

until_done.py, the Stop hook that keeps a session building until its check passes. Run as Claude
Code runs it, a script over stdin, against a throwaway git repo, with its state in a temporary
folder rather than the clone's local-data/.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "until_done.py"
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
import until_done  # noqa: E402 (the import needs the hooks folder on the path first)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.state = Path(self.tmp.name) / "state"
        self.session = str(uuid.uuid4())
        self.transcript = Path(self.tmp.name) / (self.session + ".jsonl")
        self.say("Go: 🟢 Go.\nNext: the next task.")

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if k not in ("SANVIO_HEADLESS", "HARNESS_HEADLESS")}
        env.update(CLAUDE_CODE_SESSION_ID=self.session, UNTIL_DONE_TEST_STATE=str(self.state))
        env.update(extra)
        return env

    def run_hook(self, args, stdin="", **extra):
        # Loads the hook with STATE moved to the test's folder, so a test never writes local-data/.
        code = ("import sys, os; from pathlib import Path; import importlib.util;"
                "spec = importlib.util.spec_from_file_location('until_done', {hook!r});"
                "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m);"
                "m.STATE = Path(os.environ['UNTIL_DONE_TEST_STATE']);"
                "sys.exit(m.run(sys.argv[1:]))").format(hook=str(HOOK))
        return subprocess.run([sys.executable, "-c", code] + list(args), cwd=str(self.repo), input=stdin,
                              capture_output=True, text=True, timeout=60, env=self.env(**extra))

    def arm(self, *args):
        done = self.run_hook(["--set"] + list(args))
        self.assertEqual(done.returncode, 0, done.stderr)
        return done

    def say(self, text, tokens=0, msg_id=None):
        message = {"role": "assistant", "id": msg_id or str(uuid.uuid4()),
                   "content": [{"type": "text", "text": text}]}
        if tokens:
            message["usage"] = {"input_tokens": 1, "output_tokens": tokens - 1}
        with self.transcript.open("a", encoding="utf-8") as log:
            log.write(json.dumps({"type": "assistant", "message": message}) + "\n")

    def stop(self, **extra):
        event = {"hook_event_name": "Stop", "session_id": self.session, "cwd": str(self.repo),
                 "transcript_path": str(self.transcript), "stop_hook_active": True}
        done = self.run_hook(["--stop"], json.dumps(event), **extra)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout) if done.stdout.strip() else None

    def armed(self):
        return (self.state / (self.session + ".json")).exists()


class NotArmed(Case):
    def test_a_session_that_never_armed_it_stops_quietly(self):
        self.assertIsNone(self.stop())

    def test_arming_one_session_never_holds_another(self):
        self.arm("--check", "false")
        other = {"session_id": str(uuid.uuid4()), "cwd": str(self.repo)}
        self.assertEqual(self.run_hook(["--stop"], json.dumps(other)).stdout.strip(), "")

    def test_arming_needs_a_session_id(self):
        done = self.run_hook(["--set", "--check", "true"], CLAUDE_CODE_SESSION_ID="")
        self.assertNotEqual(done.returncode, 0)
        self.assertFalse(self.state.exists())

    def test_a_headless_run_is_left_to_the_loop(self):
        self.arm("--check", "false")
        self.assertIsNone(self.stop(SANVIO_HEADLESS="1"))


class Blocks(Case):
    def test_a_failing_check_refuses_the_stop_and_hands_back_its_output(self):
        self.arm("--check", "echo 3 tests failing; false")
        out = self.stop()
        self.assertEqual(out["decision"], "block")
        self.assertIn("3 tests failing", out["reason"])
        self.assertIn("take your own Next", out["reason"])

    def test_stop_hook_active_doesnt_let_it_go(self):
        self.arm("--check", "false")
        self.assertEqual(self.stop()["decision"], "block")
        (self.repo / "progress.txt").write_text("moved")
        self.assertEqual(self.stop()["decision"], "block")


class LetsItStop(Case):
    def test_a_passing_check_lets_it_stop_and_disarms(self):
        self.arm("--check", "true")
        out = self.stop()
        self.assertNotIn("decision", out)
        self.assertIn("passed", out["systemMessage"])
        self.assertFalse(self.armed())

    def test_a_no_go_lets_it_stop_and_stays_armed(self):
        self.arm("--check", "false")
        self.say("Go: 🔴 No go. The merge is yours.\nNext: merge it once you say so.")
        self.assertNotIn("decision", self.stop())
        self.assertTrue(self.armed())

    def test_a_check_that_cant_run_isnt_a_pass(self):
        self.arm("--check", "definitely-not-a-command-xyz")
        out = self.stop()
        self.assertNotIn("decision", out)
        self.assertIn("couldn't run", out["systemMessage"])
        self.assertTrue(self.armed())

    def test_no_progress_hands_it_back(self):
        self.arm("--check", "echo same; false")
        outs = [self.stop() for _ in range(5)]
        self.assertEqual([out.get("decision") for out in outs[:3]], ["block"] * 3)
        self.assertNotIn("decision", outs[3])
        self.assertIn("nothing changed", outs[3]["systemMessage"])
        self.assertIsNone(outs[4])

    def test_the_cap_hands_it_back(self):
        self.arm("--check", "false", "--max", "2")
        for i in range(2):
            (self.repo / "step{}.txt".format(i)).write_text(str(i))
            self.assertEqual(self.stop()["decision"], "block")
        (self.repo / "last.txt").write_text("x")
        out = self.stop()
        self.assertNotIn("decision", out)
        self.assertIn("2 continuations", out["systemMessage"])

    def test_a_broken_state_file_fails_open_and_says_so(self):
        self.state.mkdir(parents=True)
        (self.state / (self.session + ".json")).write_text("{not json")
        out = self.stop()
        self.assertNotIn("decision", out)
        self.assertIn("failed open", out["systemMessage"])


class TokenCeiling(Case):
    def test_over_the_ceiling_since_arming_hands_it_back(self):
        self.arm("--check", "false", "--max-tokens", "1000")
        self.say("Go: 🟢 Go.", tokens=600)
        self.assertEqual(self.stop()["decision"], "block")  # sets the baseline at 600
        self.say("Go: 🟢 Go.", tokens=1200)
        out = self.stop()
        self.assertNotIn("decision", out)
        self.assertIn("over the ceiling of 1,000", out["systemMessage"])
        self.assertFalse(self.armed())

    def test_a_message_repeated_on_each_block_counts_once(self):
        for _ in range(4):
            self.say("one message, four blocks", tokens=100, msg_id="msg_same")
        self.assertEqual(until_done.session_tokens(self.transcript), 100)

    def test_subagents_count(self):
        self.say("main", tokens=100)
        subagents = self.transcript.with_suffix("") / "subagents"
        subagents.mkdir(parents=True)
        (subagents / "agent-x.jsonl").write_text(json.dumps(
            {"message": {"role": "assistant", "id": "m2", "usage": {"input_tokens": 50}}}) + "\n")
        self.assertEqual(until_done.session_tokens(self.transcript), 150)

    def test_zero_means_no_ceiling(self):
        self.arm("--check", "false", "--max-tokens", "0")
        self.say("Go: 🟢 Go.", tokens=10 ** 9)
        self.assertEqual(self.stop()["decision"], "block")


class SpecCheck(Case):
    def tasks(self, body):
        path = self.repo / "TASKS.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_open_boxes_name_the_tasks(self):
        status, output = until_done.spec_check(self.tasks("- [x] T001 done\n- [ ] T002 build it\n"))
        self.assertEqual(status, 1)
        self.assertIn("T002 build it", output)

    def test_every_box_checked_passes(self):
        self.assertEqual(until_done.spec_check(self.tasks("- [x] T001\n- [x] T002\n"))[0], 0)

    def test_armed_on_a_spec_it_holds_until_the_boxes_are_checked(self):
        path = self.tasks("- [ ] T001 build\n")
        self.arm("--spec", str(path))
        self.assertEqual(self.stop()["decision"], "block")
        path.write_text("- [x] T001 build\n", encoding="utf-8")
        self.assertNotIn("decision", self.stop())

    def test_spec_and_check_both_have_to_pass(self):
        self.arm("--spec", str(self.tasks("- [x] T001\n")), "--check", "false")
        self.assertEqual(self.stop()["decision"], "block")

    def test_a_spec_number_finds_its_tasks(self):
        found = until_done.resolve_spec("3")
        self.assertEqual(found.name, "TASKS.md")
        self.assertTrue(found.parent.name.startswith("003-"))


class TheShellCall(unittest.TestCase):
    def test_its_one_nosec_is_the_check_command(self):
        lines = HOOK.read_text(encoding="utf-8").splitlines()
        marked = [line for line in lines if "nosec" in line]
        self.assertEqual(len(marked), 1, "until_done.py should have exactly one nosec")
        self.assertRegex(marked[0], r"subprocess\.run\(command, shell=True.*# nosec B602\s*$")

    def test_its_state_folder_is_ignored(self):
        self.assertTrue(re.search(r"(?m)^local-data/$", (ROOT / ".gitignore").read_text()))


if __name__ == "__main__":
    unittest.main()
