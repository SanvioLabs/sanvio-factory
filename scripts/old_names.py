"""The names this repo had before it became Sanvio Factory, and what still reads them.

The state folder was .harness/, the variables were HARNESS_*, and the loop kept its checkouts in
~/.harness-loop. Nothing works under those names now. They're kept so a leftover .harness/ can be moved
across once, the setup check can name an old variable still set, the first script that reads a person's
own variable can warn about one once per shell, and the token reports can still count the loop checkouts
left in ~/.harness-loop for as long as that folder is there. Hooks never warn: Claude Code doesn't show a
hook's stderr, so a warning there would use up the shell's one telling where nobody sees it.

Standard library only, and names.py beside it.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

import names

OLD_STATE = ".harness"
OLD_PREFIX = "HARNESS_"
PREFIX, PERSONAL, OFF, STATE = names.PREFIX, names.PERSONAL, names.OFF, names.STATE


def old_loop_home(home=None):
    """Where the loop kept its checkouts before the rename. Only the token reports read it, to count them."""
    home = Path(home) if home else Path.home()
    return home / ".harness-loop"


def warn_unless_in_a_hook():
    """Warn about old names in this process's own environment, unless a hook is the one reading it."""
    if not in_a_hook():
        warn_old_once()


def old_variables(environ=None):
    """The old names of a person's own variables still set without the new one beside them. They do
    nothing now, so the setup check names them."""
    environ = os.environ if environ is None else environ
    return [OLD_PREFIX + name for name in PERSONAL if OLD_PREFIX + name in environ and PREFIX + name not in environ]


def in_a_hook(argv=None):
    """The program running is one of the Claude Code hooks in a .claude/hooks/ folder. They read the
    variables on every event, and Claude Code shows their stderr to nobody, so they stay silent and
    leave the shell's marker for a script whose warning a person reads."""
    argv = getattr(sys, "argv", None) if argv is None else argv
    if not argv or not argv[0]:
        return False
    try:
        folder = Path(argv[0]).resolve().parent
    except (OSError, RuntimeError):
        return False
    return folder.name == "hooks" and folder.parent.name == ".claude"


def mine(path):
    """The file is this user's own. Where /tmp is shared, another user's file of the same name says
    nothing about this shell."""
    if not hasattr(os, "getuid"):
        return True
    try:
        return os.lstat(path).st_uid == os.getuid()
    except OSError:
        return False


def to_stderr(text):
    try:
        os.write(2, text.encode("utf-8", "replace"))
    except OSError:
        pass  # nowhere to say it: the script goes on as it would have


def warn_old_once(environ=None, marker_dir=None, session=None, write=None, day=None):
    """Say on stderr which old variables are set without their new names, once per shell, and return
    them. HARNESS_USAGE_LOG set to off isn't named: it still switches the log off. HARNESS_HEADLESS
    isn't a person's own variable, so it never is. A marker file named for the terminal session makes
    it once per shell, because a script can't change its shell's environment. The day is in its name
    too: macOS seldom empties $TMPDIR, so a later shell given the same session number isn't silenced
    by an old marker, and a shell left open overnight is told again the next day. Under Claude Code
    (CLAUDECODE set) each Bash call is a session of its own, so there the marker is named for Claude
    Code instead, and a person is told once a day, not on every command."""
    environ = os.environ if environ is None else environ
    old = [variable for variable in old_variables(environ)
           if not (variable == OLD_PREFIX + "USAGE_LOG" and environ[variable].strip().lower() in OFF)]
    if not old:
        return []
    if marker_dir is None:
        marker_dir = tempfile.gettempdir()
    if session is None and environ.get("CLAUDECODE"):
        session = "claude-code"  # every Bash call gets its own session: one telling a day, not one a command
    if session is None:
        session = os.getsid(0) if hasattr(os, "getsid") else os.getppid()
    if day is None:
        day = time.strftime("%Y%m%d")
    marker = os.path.join(str(marker_dir), "sanvio-old-names-{}-{}".format(session, day))
    try:
        os.close(os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        if mine(marker):
            return []  # this shell has been told already
        # someone else's file: it can't say this shell was told, so say it
    except OSError:
        pass  # no marker, so it may say it again: better than never saying it
    write = write or to_stderr
    for variable in old:
        write("{} is set but does nothing now: set {} instead\n".format(
            variable, PREFIX + variable[len(OLD_PREFIX):]))
    return old


def only_focus(new):
    """True when .sanvio/ is a real folder holding nothing but the mods' project/ focus files."""
    if new.is_symlink() or not new.is_dir():
        return False
    entries = list(new.iterdir())
    return bool(entries) and [entry.name for entry in entries] == ["project"] and entries[0].is_dir() \
        and not entries[0].is_symlink()


def fold_focus(new, old):
    """Move .sanvio/project/'s files into .harness/project/, then remove the emptied .sanvio/."""
    try:
        target = old / "project"
        target.mkdir(exist_ok=True)
        for one in (new / "project").iterdir():
            if one.is_file() and not one.is_symlink():
                os.replace(one, target / one.name)
        (new / "project").rmdir()
        new.rmdir()
    except OSError:
        pass  # left as it is: both folders stay, and the message below says so


def move_old_state(root):
    """Move .harness/ to .sanvio/ when only the old one exists, and say what happened, or None."""
    new, old = Path(root) / STATE, Path(root) / OLD_STATE
    if not old.exists():
        return None
    if only_focus(new):
        # An updated mod wrote its /project focus before any session moved .harness/: fold it in first.
        fold_focus(new, old)
    if new.exists():
        return ("both .harness/ and .sanvio/ are here, and only .sanvio/ is read. Move what you still need "
                "from .harness/ into .sanvio/, then delete .harness/")
    try:
        os.rename(old, new)
    except OSError as error:
        return "couldn't move .harness/ to .sanvio/ ({}), and nothing reads .harness/ now. Move it by hand".format(
            error.strerror or error)
    return "moved .harness/ to .sanvio/, the new name for this repo's own state, with everything in it"
