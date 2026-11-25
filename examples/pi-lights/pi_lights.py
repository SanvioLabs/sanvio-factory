#!/usr/bin/env python3
"""Front lights for a Raspberry Pi builder: four LEDs, dimmed in software.

    sudo python3 pi_lights.py                     drive the lights (what the service runs)
    python3 pi_lights.py --show                   print what each light would show, touch nothing
    sudo python3 pi_lights.py --test              light each one in turn, then stop

What each light shows:

  net   green   on while the network is up, flickering while traffic moves
  disk  blue    flickers while the drive reads or writes
  loop  orange  flickers while the factory's loop is working an issue
  ai    white   flickers while a claude process runs as the agent account

The lights are the gpio-led overlay's, so each is on or off. Dimming works by
switching each lit one on for LEVEL of every 4 ms, so one process owns all four
and none of them keeps a kernel trigger. It reads the loop's status files, the
drive's counters, the network's counters and the process list, and writes only
the four lights' trigger and brightness files. Run it as root, or as a user
that can write those files.
"""
import argparse
import glob
import json
import os
import pwd
import sys
import time

PERIOD = 0.004          # one dimming cycle, 250 Hz
TICK = 0.05             # how often activity is sampled
LOOP_EVERY = 2.0        # how often the loop's status is read
LEDS = "/sys/class/leds"
PR_SET_TIMERSLACK = 29  # prctl option: how late the kernel may wake a sleep


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def loop_working(factory, proc="/proc"):
    """How many issues the factory's loops are working: the factory's own .loop/status.json and each
    project's under .loop/projects/. A loop whose process is gone counts as working nothing."""
    n = 0
    base = os.path.join(factory, ".loop")
    for path in [os.path.join(base, "status.json"), *glob.glob(os.path.join(base, "projects", "*", "status.json"))]:
        try:
            with open(path, encoding="utf-8") as f:
                st = json.load(f)
            pid = int(st.get("pid") or 0)
        except (OSError, ValueError, AttributeError, TypeError):
            continue
        if pid <= 0 or not os.path.isdir(os.path.join(proc, str(pid))):
            continue
        n += sum(1 for r in st.get("issues") or [] if isinstance(r, dict) and r.get("state") == "working")
    return n


def is_claude(pid, proc="/proc"):
    """True when the process is the claude CLI, by its first argument or, for the native install,
    its executable under ~/.local/share/claude/versions/."""
    argv0 = (read(os.path.join(proc, str(pid), "cmdline")) or "").split("\0", 1)[0]
    if os.path.basename(argv0) == "claude" or "/claude/versions/" in argv0:
        return True
    try:
        return "/claude/versions/" in os.readlink(os.path.join(proc, str(pid), "exe"))
    except OSError:
        return False


def owner(pid, proc="/proc"):
    """The real uid a process runs as, or None."""
    for line in (read(os.path.join(proc, str(pid), "status")) or "").splitlines():
        if line.startswith("Uid:"):
            try:
                return int(line.split()[1])
            except (IndexError, ValueError):
                return None
    return None


def ai_running(uid, proc="/proc"):
    """True while a claude process runs as uid."""
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return False
    return any(owner(p, proc) == uid and is_claude(p, proc) for p in pids)


def pick_dev(block="/sys/block"):
    """The first NVMe drive, else the SD card, else a USB drive."""
    for pat in ("nvme*n1", "mmcblk0", "sd?"):
        found = sorted(glob.glob(os.path.join(block, pat)))
        if found:
            return os.path.basename(found[0])
    return None


def disk_counters(dev, block="/sys/block"):
    """(reads completed, writes completed) for dev, or None."""
    s = read(os.path.join(block, dev, "stat")) if dev else None
    try:
        fields = s.split()
        return int(fields[0]), int(fields[4])
    except (AttributeError, ValueError, IndexError):
        return None


def pick_iface(route="/proc/net/route"):
    """The interface that carries the default route, else eth0."""
    for line in (read(route) or "").splitlines()[1:]:
        parts = line.split()
        if len(parts) > 1 and parts[1] == "00000000":
            return parts[0]
    return "eth0"


def net_state(iface, net="/sys/class/net"):
    """(up, packet counters) for iface."""
    base = os.path.join(net, iface)
    up = (read(os.path.join(base, "operstate")) or "").strip() == "up"
    return up, tuple(read(os.path.join(base, "statistics", k + "_packets")) for k in ("rx", "tx"))


class Light:
    """One gpio-led light, written through a held file descriptor so dimming stays cheap."""

    def __init__(self, label):
        self.label = label
        self.path = os.path.join(LEDS, label, "brightness")
        self.fd = None
        self.cur = None
        self.want = False

    def present(self):
        return os.path.isdir(os.path.join(LEDS, self.label))

    def release(self):
        """Take the light off any kernel trigger, so only this process switches it."""
        try:
            with open(os.path.join(LEDS, self.label, "trigger"), "w") as f:
                f.write("none")
        except OSError:
            pass  # not there until the overlay's reboot; write() skips it the same way

    def write(self, v):
        if v == self.cur:
            return
        if self.fd is None:
            try:
                self.fd = os.open(self.path, os.O_WRONLY)
            except OSError:
                return
        try:
            os.write(self.fd, v)
            self.cur = v
        except OSError:
            os.close(self.fd)
            self.fd, self.cur = None, None


def tight_timers():
    """Ask for 1 us timer slack instead of 50 us, so a dimmed light's short on-time doesn't wander
    and flicker. Only this process changes."""
    try:
        import ctypes
        ctypes.CDLL(None).prctl(PR_SET_TIMERSLACK, 1000, 0, 0, 0)
    except Exception:
        pass  # only steadier dimming is lost; the lights still work


def parse(argv=None):
    ap = argparse.ArgumentParser(description="Front lights for a Raspberry Pi builder.")
    ap.add_argument("--factory", default="/home/agent/factory", help="the factory clone whose loop the orange light follows")
    ap.add_argument("--user", default="agent", help="the account whose claude processes the white light follows")
    ap.add_argument("--iface", default=None, help="network interface; default: the one with the default route")
    ap.add_argument("--dev", default=None, help="block device, such as nvme0n1; default: NVMe, else the SD card")
    ap.add_argument("--level", type=float, default=0.08, help="brightness, 0 to 1 (default 0.08)")
    ap.add_argument("--blink", type=float, default=0.1, help="seconds per flicker of the loop and ai lights; 0 holds them steady")
    ap.add_argument("--labels", default="pi-net,pi-disk,pi-loop,pi-ai", help="the four lights' labels, in the order net,disk,loop,ai")
    ap.add_argument("--show", action="store_true", help="print each light's state once a second, touch no light")
    ap.add_argument("--test", action="store_true", help="light each one in turn at full brightness, then stop")
    a = ap.parse_args(argv)
    a.labels = [x.strip() for x in a.labels.split(",")]
    if len(a.labels) != 4 or not all(a.labels):
        ap.error("--labels takes four names: net,disk,loop,ai")
    a.level = min(max(a.level, 0.0), 1.0)
    return a


def main(argv=None):
    a = parse(argv)
    lights = [Light(x) for x in a.labels]
    net, disk, loop, ai = lights

    if a.test:
        missing = [l.label for l in lights if not l.present()]
        if missing:
            sys.exit("not found under {}: {}. Add the overlay lines to /boot/firmware/config.txt and reboot".format(
                LEDS, ", ".join(missing)))
        for l in lights:
            l.release()
            l.write(b"0")
        for name, l in zip(("net, green", "disk, blue", "loop, orange", "ai, white"), lights):
            print(name)
            l.write(b"1")
            time.sleep(1.5)
            l.write(b"0")
        return

    try:
        uid = pwd.getpwnam(a.user).pw_uid
    except KeyError:
        sys.exit("no account named {}".format(a.user))
    iface, dev = a.iface or pick_iface(), a.dev or pick_dev()
    last_disk, last_net = disk_counters(dev), net_state(iface)[1]

    if a.show:
        print("net: {}  disk: {}  factory: {}  user: {}".format(iface, dev, a.factory, a.user))
        while True:
            time.sleep(1)
            d, (up, counts) = disk_counters(dev), net_state(iface)
            print("net {:<9} disk {:<5} loop {:<2} ai {}".format(
                ("busy" if counts != last_net else "up") if up else "down",
                "busy" if d != last_disk else "idle", loop_working(a.factory),
                "on" if ai_running(uid) else "off"), flush=True)
            last_disk, last_net = d, counts

    for l in lights:
        l.release()
    tight_timers()
    next_tick = next_loop = 0.0
    flicker = loop_on = ai_on = False
    while True:
        now = time.monotonic()
        if now >= next_tick:
            next_tick = now + TICK
            flicker = not flicker
            d = disk_counters(dev)
            disk.want = d is not None and last_disk is not None and d != last_disk
            last_disk = d
            up, counts = net_state(iface)
            net.want = up and (flicker if counts != last_net else True)
            last_net = counts
            ai_on = ai_running(uid)
        if now >= next_loop:
            next_loop = now + LOOP_EVERY
            loop_on = loop_working(a.factory) > 0
        flash = a.blink <= 0 or now % a.blink < a.blink / 2
        loop.want = loop_on and flash
        ai.want = ai_on and flash

        lit = [l for l in lights if l.want]
        if a.level >= 1.0 or not lit:
            for l in lights:
                l.write(b"1" if l.want else b"0")
            time.sleep(PERIOD)
            continue
        start = time.monotonic()
        for l in lights:
            l.write(b"1" if l.want else b"0")
        wait = start + PERIOD * a.level - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        for l in lit:
            l.write(b"0")
        rest = start + PERIOD - time.monotonic()
        if rest > 0:
            time.sleep(rest)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass  # Ctrl-C is how --show and a hand run end: no traceback
