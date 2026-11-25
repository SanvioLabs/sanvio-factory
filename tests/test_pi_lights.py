"""examples/pi-lights/pi_lights.py reads the loop, the processes, the drive and the network right,
against a pretend /proc and /sys in a temporary folder."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "examples" / "pi-lights" / "pi_lights.py"


def load():
    spec = importlib.util.spec_from_file_location("pi_lights", PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@unittest.skipIf(os.name == "nt", "the lights run on Linux, and pi_lights imports pwd")
class PiLights(unittest.TestCase):
    def setUp(self):
        self.m = load()
        self.tmp = Path(tempfile.mkdtemp())
        self.proc = self.tmp / "proc"
        self.proc.mkdir()

    def process(self, pid, argv0, uid=1001):
        d = self.proc / str(pid)
        d.mkdir()
        (d / "cmdline").write_text(argv0 + "\0-p\0", encoding="utf-8")
        (d / "status").write_text("Name:\tx\nUid:\t{0}\t{0}\t{0}\t{0}\n".format(uid), encoding="utf-8")

    def status(self, where, pid, states):
        where.mkdir(parents=True, exist_ok=True)
        rows = [{"number": i, "state": s} for i, s in enumerate(states)]
        (where / "status.json").write_text(json.dumps({"pid": pid, "issues": rows}), encoding="utf-8")

    def test_counts_working_issues_across_the_factory_and_its_projects(self):
        fac = self.tmp / "factory"
        self.process(10, "python3")
        self.process(11, "python3")
        self.status(fac / ".loop", 10, ["working", "done"])
        self.status(fac / ".loop" / "projects" / "shop", 11, ["working", "working", "blocked"])
        self.assertEqual(self.m.loop_working(str(fac), str(self.proc)), 3)

    def test_a_loop_whose_process_is_gone_counts_nothing(self):
        fac = self.tmp / "factory"
        self.status(fac / ".loop", 99, ["working"])
        self.assertEqual(self.m.loop_working(str(fac), str(self.proc)), 0)

    def test_a_missing_or_broken_status_file_counts_nothing(self):
        fac = self.tmp / "factory"
        self.assertEqual(self.m.loop_working(str(fac), str(self.proc)), 0)
        (fac / ".loop").mkdir(parents=True)
        (fac / ".loop" / "status.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(self.m.loop_working(str(fac), str(self.proc)), 0)

    def test_ai_follows_claude_run_as_the_named_account_only(self):
        self.process(20, "/home/agent/.local/bin/claude", uid=1001)
        self.process(21, "claude", uid=1002)
        self.process(22, "python3", uid=1001)
        self.assertTrue(self.m.ai_running(1001, str(self.proc)))
        self.assertTrue(self.m.ai_running(1002, str(self.proc)))
        self.assertFalse(self.m.ai_running(1003, str(self.proc)))

    def test_ai_is_off_when_the_account_runs_no_claude(self):
        self.process(30, "node", uid=1001)
        self.assertFalse(self.m.ai_running(1001, str(self.proc)))

    def test_disk_counters_read_reads_and_writes(self):
        block = self.tmp / "block" / "nvme0n1"
        block.mkdir(parents=True)
        (block / "stat").write_text("  120 0 900 40   75 0 600 30 0 50 70\n", encoding="utf-8")
        self.assertEqual(self.m.disk_counters("nvme0n1", str(self.tmp / "block")), (120, 75))
        self.assertIsNone(self.m.disk_counters("sda", str(self.tmp / "block")))
        self.assertIsNone(self.m.disk_counters(None, str(self.tmp / "block")))

    def test_pick_dev_prefers_nvme_then_the_sd_card(self):
        block = self.tmp / "block"
        (block / "mmcblk0").mkdir(parents=True)
        self.assertEqual(self.m.pick_dev(str(block)), "mmcblk0")
        (block / "nvme0n1").mkdir()
        self.assertEqual(self.m.pick_dev(str(block)), "nvme0n1")

    def test_pick_iface_takes_the_default_route(self):
        route = self.tmp / "route"
        route.write_text("Iface\tDestination\tGateway\n"
                         "wlan0\t0001A8C0\t00000000\n"
                         "wlan0\t00000000\t0101A8C0\n", encoding="utf-8")
        self.assertEqual(self.m.pick_iface(str(route)), "wlan0")
        self.assertEqual(self.m.pick_iface(str(self.tmp / "none")), "eth0")

    def test_labels_take_exactly_four_names(self):
        self.assertEqual(self.m.parse(["--labels", "a,b,c,d"]).labels, ["a", "b", "c", "d"])
        with self.assertRaises(SystemExit):
            self.m.parse(["--labels", "a,b,c"])

    def test_level_is_held_between_0_and_1(self):
        self.assertEqual(self.m.parse(["--level", "3"]).level, 1.0)
        self.assertEqual(self.m.parse(["--level", "-1"]).level, 0.0)


if __name__ == "__main__":
    unittest.main()
