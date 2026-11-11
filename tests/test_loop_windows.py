"""Run with: python3 -m unittest tests.test_loop_windows

The loop's lock, signals and agent stops on Windows (#480). The patched tests run everywhere: each answers
loop.on_windows itself and stands in for what Windows has. The real-Windows tests at the end skip elsewhere.
"""
import builtins
import os
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import loop  # noqa: E402 (needs scripts/ on the path first)

STILL_ACTIVE, ACCESS_DENIED, INVALID_PARAMETER = 259, 5, 87


class Kernel32:
    """A stand-in for ctypes.windll.kernel32: OpenProcess hands out handle, or 0 with error."""

    def __init__(self, exit_code=STILL_ACTIVE, handle=7, error=0):
        self.exit_code, self.handle, self.error = exit_code, handle, error
        self.calls = []

    def OpenProcess(self, access, inherit, pid):
        self.calls.append(("OpenProcess", access, inherit, pid))
        return self.handle

    def GetLastError(self):
        self.calls.append(("GetLastError",))
        return self.error

    def GetExitCodeProcess(self, handle, ref):
        self.calls.append(("GetExitCodeProcess", handle))
        ref._obj.value = self.exit_code  # ref is ctypes.byref(c_ulong): _obj is the c_ulong
        return 1

    def CloseHandle(self, handle):
        self.calls.append(("CloseHandle", handle))
        return 1


class Msvcrt:
    """A stand-in for msvcrt: one lock per file, which a different handle can't take while it's held."""
    LK_UNLCK, LK_NBLCK = 0, 2

    def __init__(self):
        self.calls = []  # (fileno, mode, bytes, offset, whether the file was open)
        self.held = {}  # (st_dev, st_ino) -> the fileno that holds it

    def locking(self, fileno, mode, nbytes):
        offset = os.lseek(fileno, 0, os.SEEK_CUR)
        try:
            os.fstat(fileno)
            still_open = True
        except OSError:
            still_open = False
        self.calls.append((fileno, mode, nbytes, offset, still_open))
        stat = os.fstat(fileno)
        key = (stat.st_dev, stat.st_ino)
        if mode == self.LK_NBLCK:
            if key in self.held and self.held[key] != fileno:
                raise OSError(36, "Resource deadlock avoided")
            self.held[key] = fileno
        elif mode == self.LK_UNLCK:
            self.held.pop(key, None)


class Fcntl:
    """A stand-in for fcntl that grants every lock."""
    LOCK_EX, LOCK_NB = 2, 4

    def __init__(self):
        self.calls = []

    def flock(self, handle, flags):
        self.calls.append(flags)


def imports():
    """A patch on builtins.__import__ that records each name imported, and the list it records into."""
    real = builtins.__import__
    names = []

    def record(name, *args, **kwargs):
        names.append(name)
        return real(name, *args, **kwargs)

    return mock.patch.object(builtins, "__import__", side_effect=record), names


class Folder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def loop(self, **cfg):
        return loop.Loop(self.root, dict(loop.DEFAULTS, **cfg))


class Lock(Folder):
    """take_lock reads the pid in .loop/lock and asks pid_alive whether it still runs."""

    def take(self, k32, windows=True):
        lp = self.loop()
        (lp.dir / "lock").write_text("4242")
        with mock.patch.object(loop, "on_windows", return_value=windows), \
                mock.patch.object(loop, "kernel32", return_value=k32), \
                mock.patch.object(os, "kill") as kill:
            took = lp.take_lock()
        return took, (lp.dir / "lock").read_text(), kill

    def test_a_live_pid_on_windows_keeps_the_lock_and_never_calls_os_kill(self):
        k32 = Kernel32(exit_code=STILL_ACTIVE)
        took, held, kill = self.take(k32)
        self.assertFalse(took)
        self.assertEqual(held, "4242")
        self.assertEqual(kill.call_count, 0)
        self.assertIn(("OpenProcess", 0x1000, False, 4242), k32.calls)
        self.assertIn(("CloseHandle", 7), k32.calls)

    def test_a_dead_pid_on_windows_is_replaced_by_ours(self):
        for name, k32 in (("exited", Kernel32(exit_code=0)),
                          ("gone", Kernel32(handle=0, error=INVALID_PARAMETER))):
            with self.subTest(name):
                took, held, kill = self.take(k32)
                self.assertTrue(took)
                self.assertEqual(held, str(os.getpid()))
                self.assertEqual(kill.call_count, 0)

    def test_an_exited_pid_still_closes_its_handle(self):
        k32 = Kernel32(exit_code=0)
        self.take(k32)
        self.assertIn(("CloseHandle", 7), k32.calls)

    def test_access_denied_on_windows_counts_as_alive(self):
        took, held, kill = self.take(Kernel32(handle=0, error=ACCESS_DENIED))
        self.assertFalse(took)
        self.assertEqual(held, "4242")
        self.assertEqual(kill.call_count, 0)

    def test_on_posix_it_asks_os_kill_and_never_touches_kernel32(self):
        k32 = Kernel32()
        took, held, kill = self.take(k32, windows=False)
        kill.assert_called_once_with(4242, 0)
        self.assertEqual(k32.calls, [])

    def test_on_posix_another_users_process_keeps_the_lock(self):
        k32 = Kernel32()
        lp = self.loop()
        (lp.dir / "lock").write_text("4242")
        with mock.patch.object(loop, "on_windows", return_value=False), \
                mock.patch.object(loop, "kernel32", return_value=k32), \
                mock.patch.object(os, "kill", side_effect=PermissionError()) as kill:
            self.assertFalse(lp.take_lock())
        kill.assert_called_once_with(4242, 0)
        self.assertEqual((lp.dir / "lock").read_text(), "4242")
        self.assertEqual(k32.calls, [])

    def test_on_posix_a_gone_process_is_replaced(self):
        lp = self.loop()
        (lp.dir / "lock").write_text("4242")
        with mock.patch.object(loop, "on_windows", return_value=False), \
                mock.patch.object(os, "kill", side_effect=ProcessLookupError()):
            self.assertTrue(lp.take_lock())
        self.assertEqual((lp.dir / "lock").read_text(), str(os.getpid()))


class AgentStart(Folder):
    """stream starts an agent apart from the loop's terminal: its own process group or session."""

    def options(self, windows):
        seen = []

        def popen(*args, **kwargs):
            seen.append(kwargs)
            raise FileNotFoundError()  # stream returns 127 at once, with nothing to stop

        lp = self.loop()
        with mock.patch.object(loop, "on_windows", return_value=windows), \
                mock.patch.object(loop.subprocess, "Popen", side_effect=popen):
            code, _ = lp.stream(["agent-stand-in"], self.root, "prompt", self.root / "agent.log", "agent")
        self.assertEqual(code, 127)
        self.assertEqual(len(seen), 1)
        return seen[0]

    def test_on_windows_an_agent_gets_a_process_group_of_its_own(self):
        kwargs = self.options(True)
        self.assertEqual(kwargs.get("creationflags"), 0x200)
        self.assertNotIn("start_new_session", kwargs)

    def test_on_posix_an_agent_gets_a_session_of_its_own(self):
        kwargs = self.options(False)
        self.assertIs(kwargs.get("start_new_session"), True)
        self.assertNotIn("creationflags", kwargs)


class KillTree(unittest.TestCase):
    def test_on_windows_taskkill_ends_the_tree_and_killpg_is_never_called(self):
        proc = types.SimpleNamespace(pid=4242)
        with mock.patch.object(loop, "on_windows", return_value=True), \
                mock.patch.object(loop.subprocess, "run") as run, \
                mock.patch.object(loop.os, "killpg", create=True) as killpg:
            loop.kill_tree(proc)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["taskkill", "/T", "/F", "/PID", "4242"])
        self.assertEqual(run.call_args.kwargs.get("check"), False)
        self.assertEqual(killpg.call_count, 0)

    def test_on_posix_killpg_ends_the_group_and_taskkill_never_runs(self):
        proc = types.SimpleNamespace(pid=4242)
        # create=True for both: Windows has no os.killpg and no signal.SIGKILL.
        with mock.patch.object(loop, "on_windows", return_value=False), \
                mock.patch.object(loop.subprocess, "run") as run, \
                mock.patch.object(loop.os, "killpg", create=True) as killpg, \
                mock.patch.object(loop.signal, "SIGKILL", 9, create=True):
            loop.kill_tree(proc)
        killpg.assert_called_once_with(4242, 9)
        self.assertEqual(run.call_count, 0)


class StopSites(Folder):
    """Both places the loop ends an agent go through kill_tree, with that agent alone."""

    def test_a_timeout_in_stream_kills_that_agent_tree(self):
        started = []
        real = subprocess.Popen

        def popen(*args, **kwargs):
            started.append(real(*args, **kwargs))
            return started[-1]

        lp = self.loop(agent_timeout=0.2)
        cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
        with mock.patch.object(loop.subprocess, "Popen", side_effect=popen), \
                mock.patch.object(loop, "kill_tree", side_effect=lambda proc: proc.kill()) as kill:
            began = time.time()
            code, _ = lp.stream(cmd, self.root, "", self.root / "agent.log", "agent")
        self.assertLess(time.time() - began, 20)
        self.assertEqual(code, 124)
        self.assertEqual(len(started), 1)
        kill.assert_called_once_with(started[0])

    def test_an_interrupt_in_work_kills_each_running_agent(self):
        lp = self.loop()
        agent = mock.Mock(pid=4242)  # hashable, unlike a SimpleNamespace: self.agents is a set
        lp.agents.add(agent)
        with mock.patch.object(loop.Loop, "stopped", side_effect=KeyboardInterrupt), \
                mock.patch.object(loop, "kill_tree") as kill, \
                mock.patch.object(loop.Loop, "log"):
            with self.assertRaises(KeyboardInterrupt):
                lp.work(False, None, False)
        kill.assert_called_once_with(agent)
        self.assertTrue(lp.interrupted.is_set())


class Signals(unittest.TestCase):
    def test_a_system_without_sighup_catches_sigterm_alone(self):
        stand_in = types.SimpleNamespace(SIGTERM=15, signal=mock.Mock(return_value="before"))
        handler = object()
        with mock.patch.object(loop, "signal", stand_in):
            caught = loop.catch_signals(handler)
        stand_in.signal.assert_called_once_with(15, handler)
        self.assertEqual(caught, {15: "before"})


class MsvcrtLock(Folder):
    """Where there's no fcntl, FileLock takes msvcrt's lock on the file's first byte."""

    def setUp(self):
        super().setUp()
        self.msvcrt = Msvcrt()
        self.handles = []

        def opened(*args, **kwargs):
            self.handles.append(open(*args, **kwargs))
            return self.handles[-1]

        for patch in (mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": self.msvcrt}),
                      mock.patch.object(loop, "open", create=True, side_effect=opened)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_the_first_lock_holds_and_a_second_is_refused_and_closes_its_file(self):
        path = self.root / ".loop" / "review-pr-7.lock"
        first, second = loop.FileLock(path), loop.FileLock(path)
        self.assertTrue(first.acquire())
        fileno, mode, nbytes, offset, _ = self.msvcrt.calls[0]
        self.assertEqual((fileno, mode, nbytes, offset), (self.handles[0].fileno(), Msvcrt.LK_NBLCK, 1, 0))
        self.assertFalse(second.acquire())
        self.assertEqual(self.msvcrt.calls[1][1:4], (Msvcrt.LK_NBLCK, 1, 0))
        self.assertTrue(self.handles[1].closed)
        self.assertIsNone(second.handle)
        first.release()

    def test_release_unlocks_before_it_closes_the_file(self):
        lock = loop.FileLock(self.root / "x.lock")
        self.assertTrue(lock.acquire())
        fileno = self.handles[0].fileno()
        lock.release()
        self.assertEqual(self.msvcrt.calls[-1], (fileno, Msvcrt.LK_UNLCK, 1, 0, True))
        self.assertTrue(self.handles[0].closed)
        self.assertIsNone(lock.handle)

    def test_once_released_another_can_take_it(self):
        path = self.root / "x.lock"
        with loop.FileLock(path) as held:
            self.assertTrue(held)
        with loop.FileLock(path) as held:
            self.assertTrue(held)


class FileLocks(unittest.TestCase):
    def test_msvcrt_alone_is_a_file_lock(self):
        with mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": Msvcrt()}):
            self.assertTrue(loop.file_locks())

    def test_neither_is_no_file_lock(self):
        with mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": None}):
            self.assertFalse(loop.file_locks())

    def test_the_fcntl_path_never_imports_msvcrt(self):
        fcntl = Fcntl()
        patch, names = imports()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(sys.modules, {"fcntl": fcntl, "msvcrt": None}), patch:
                self.assertTrue(loop.file_locks())
                lock = loop.FileLock(Path(tmp) / "x.lock")
                self.assertTrue(lock.acquire())
                lock.release()
        self.assertEqual(fcntl.calls, [Fcntl.LOCK_EX | Fcntl.LOCK_NB])
        self.assertIn("fcntl", names)
        self.assertNotIn("msvcrt", names)


class Multiplexer(Folder):
    """The session and issue windows run in psmux on Windows when it's installed, and tmux everywhere else."""

    def where(self, found):
        """A stand-in for shutil.which that finds only the names in found."""
        return lambda name: "/bin/" + name if name in found else None

    def on(self, windows, found=("psmux",)):
        return mock.patch.object(loop, "on_windows", return_value=windows), \
            mock.patch.object(loop.shutil, "which", side_effect=self.where(found))

    def pick(self, windows, found):
        a, b = self.on(windows, found)
        with a, b:
            return loop.multiplexer()

    def test_windows_with_psmux_installed_uses_psmux(self):
        self.assertEqual(self.pick(True, ("psmux",)), "psmux")

    def test_windows_without_psmux_uses_tmux(self):
        self.assertEqual(self.pick(True, ()), "tmux")

    def test_off_windows_it_is_tmux_even_when_psmux_is_found(self):
        self.assertEqual(self.pick(False, ("psmux", "tmux")), "tmux")

    def test_in_a_psmux_session_the_session_name_comes_from_psmux(self):
        lp = self.loop()
        seen = []

        def sh(cmd, *args, **kwargs):
            seen.append(cmd)
            return 0, "loop-work\n"

        a, b = self.on(True)
        with a, b, mock.patch.dict(os.environ, {"TMUX": "psmux-socket,1,0", "TMUX_PANE": "%3"}), \
                mock.patch.object(lp, "sh", side_effect=sh):
            self.assertEqual(lp.tmux_session(), "loop-work")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][:6], ["psmux", "display-message", "-p", "-t", "%3", "#S"])

    def test_outside_a_session_nothing_is_run(self):
        lp = self.loop()
        a, b = self.on(True)
        with a, b, mock.patch.dict(os.environ), mock.patch.object(lp, "sh") as sh:
            os.environ.pop("TMUX", None)
            os.environ.pop("TMUX_PANE", None)
            self.assertIsNone(lp.tmux_session())
        self.assertEqual(sh.call_count, 0)

    def open(self, windows):
        """open_window for issue 12 under a root whose path holds a ', and the argv it ran, and the log."""
        root = self.root / "it's here"
        root.mkdir()
        lp = loop.Loop(root, dict(loop.DEFAULTS))
        lp.session = "loop-work"
        seen = []

        def sh(cmd, *args, **kwargs):
            seen.append(cmd)
            return 0, ""

        found = ("psmux",) if windows else ("tmux",)
        a, b = self.on(windows, found)
        with a, b, mock.patch.object(lp, "sh", side_effect=sh):
            self.assertEqual(lp.open_window(12), "issue-12")
        self.assertEqual(len(seen), 1)
        return seen[0], lp.dir / "issue-12" / "agent.log"

    def test_on_windows_an_issue_window_follows_its_log_with_powershell_in_psmux(self):
        argv, log = self.open(True)
        quoted = str(log).replace("'", "''")
        self.assertIn("''", quoted)
        self.assertEqual(argv, ["psmux", "new-window", "-d", "-t", "loop-work", "-n", "issue-12",
                                "powershell -NoProfile -Command \"Get-Content -Wait -LiteralPath '{}'\"".format(quoted)])

    def test_on_posix_an_issue_window_still_tails_its_log_in_tmux(self):
        argv, log = self.open(False)
        self.assertEqual(argv, ["tmux", "new-window", "-d", "-t", "loop-work", "-n", "issue-12",
                                "tail -n +1 -f " + loop.shlex.quote(str(log))])

    def test_on_windows_the_issue_window_is_closed_with_psmux(self):
        lp = self.loop()
        lp.session = "loop-work"
        lp.windows[12] = "issue-12"
        seen = []

        def sh(cmd, *args, **kwargs):
            seen.append(cmd)
            return 0, ""

        a, b = self.on(True)
        with a, b, mock.patch.object(lp, "sh", side_effect=sh), mock.patch.object(lp, "process"):
            lp.worker({"number": 12}, "issue-12")
        self.assertIn(["psmux", "kill-window", "-t", "loop-work:issue-12"], seen)
        self.assertNotIn(12, lp.windows)


CHILD_PATH = "import sys; sys.path.insert(0, {!r}); ".format(str(SCRIPTS))


@unittest.skipUnless(sys.platform == "win32", "needs a real Windows")
class RealWindows(unittest.TestCase):
    def test_a_lock_another_process_holds_is_refused_until_it_ends(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.lock"
            child = subprocess.Popen(
                [sys.executable, "-c", CHILD_PATH + "import loop; lock = loop.FileLock(sys.argv[1]); "
                 "print(lock.acquire(), flush=True); sys.stdin.read()", str(path)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), "True")
                lock = loop.FileLock(path)
                self.assertFalse(lock.acquire())
            finally:
                child.stdin.close()
                child.wait(10)
                child.stdout.close()
            self.assertTrue(lock.acquire())
            lock.release()

    def test_our_pid_is_alive_and_an_exited_childs_is_not(self):
        self.assertTrue(loop.pid_alive(os.getpid()))
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait(10)
        self.assertFalse(loop.pid_alive(child.pid))

    def test_kill_tree_ends_the_agent_and_what_it_started(self):
        grandchild = "import time; time.sleep(60)"
        child = subprocess.Popen(
            [sys.executable, "-c", "import subprocess, sys, time; "
             "p = subprocess.Popen([sys.executable, '-c', {!r}]); print(p.pid, flush=True); "
             "time.sleep(60)".format(grandchild)],
            stdout=subprocess.PIPE, text=True, creationflags=0x200)
        try:
            grandchild_pid = int(child.stdout.readline())
            loop.kill_tree(child)
            child.wait(10)  # reaps it, so its pid reads as gone
            deadline = time.time() + 10
            while time.time() < deadline and (loop.pid_alive(child.pid) or loop.pid_alive(grandchild_pid)):
                time.sleep(0.2)
            self.assertFalse(loop.pid_alive(child.pid))
            self.assertFalse(loop.pid_alive(grandchild_pid))
        finally:
            child.stdout.close()
            if child.poll() is None:
                child.kill()


if __name__ == "__main__":
    unittest.main()
