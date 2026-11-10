"""The names this repo took when it became Sanvio Factory, and the old ones it still recognises.

The state folder is .sanvio/, the variables are SANVIO_*, and the home folders are ~/.sanvio-loop and
~/.sanvio-evals. Nothing reads the old names any more, with two exceptions that only ever make things
stricter: HARNESS_HEADLESS=1 still makes a run headless, and HARNESS_USAGE_LOG=off still turns the usage log
off. The old names are kept here so
.claude/hooks/session_start.py can move a leftover .harness/ across once, scripts/check_setup.py can
name any old variable still set, which now does nothing, and the first script that reads a person's own
variable can warn about one once per shell.

Standard library only: the hooks and the loop import it, and so does a fresh clone before setup.
"""
import os
from pathlib import Path

STATE, OLD_STATE = ".sanvio", ".harness"
PREFIX, OLD_PREFIX = "SANVIO_", "HARNESS_"
# The variables a person sets themselves. SANVIO_HEADLESS isn't one: bin/factory sets it for the run.
PERSONAL = ("PULSE_FOLDER", "RETRO", "USAGE_LOG", "EVALS_HOME")
# The values that switch the usage log off, under either name.
OFF = ("off", "0", "false", "no")
# Set once this process has checked the real environment for old names, so it checks only once.
_checked = False


def state_dir(root):
    """The repo's own state folder."""
    return Path(root) / STATE


def loop_home(home=None):
    """Where the loop keeps its checkouts when loop.json names no worktree_dir."""
    home = Path(home) if home else Path.home()
    return home / ".sanvio-loop"


def evals_home(home=None, environ=None):
    """Where eval_factory.py keeps each run's sealed copy: SANVIO_EVALS_HOME, else the home folder."""
    named = env("EVALS_HOME", environ=environ)
    if named:
        return Path(named)
    home = Path(home) if home else Path.home()
    return home / ".sanvio-evals"


def env(name, default="", environ=None):
    """SANVIO_<name> if it's set, else the default."""
    if environ is None:
        check_real_environment()
        environ = os.environ
    return environ.get(PREFIX + name, default)


def headless(environ=None):
    """Either name says this run is headless. The old one is still read because the stricter reading
    always wins: a script that sets only HARNESS_HEADLESS keeps the guard as strict as it was."""
    environ = os.environ if environ is None else environ
    return environ.get(PREFIX + "HEADLESS") == "1" or environ.get(OLD_PREFIX + "HEADLESS") == "1"


def logging_off(environ=None):
    """The usage log is switched off. The old name's off still counts: like headless, it only ever means
    less is recorded, so someone who opted out stays opted out."""
    if environ is None:
        check_real_environment()
        environ = os.environ
    return any(environ.get(prefix + "USAGE_LOG", "").strip().lower() in OFF for prefix in (PREFIX, OLD_PREFIX))


def old_variables(environ=None):
    """The old names of a person's own variables still set without the new one beside them. They do
    nothing now, so the setup check names them."""
    environ = os.environ if environ is None else environ
    return [OLD_PREFIX + name for name in PERSONAL if OLD_PREFIX + name in environ and PREFIX + name not in environ]


def check_real_environment():
    """Warn about old names in this process's own environment, the first time anything here reads it."""
    global _checked
    if _checked:
        return
    _checked = True
    warn_old_once()


def to_stderr(text):
    try:
        os.write(2, text.encode("utf-8", "replace"))
    except OSError:
        pass  # nowhere to say it: the script goes on as it would have


def warn_old_once(environ=None, marker_dir=None, session=None, write=None):
    """Say on stderr which old variables are set without their new names, once per shell, and return
    them. HARNESS_USAGE_LOG set to off isn't named: it still switches the log off. HARNESS_HEADLESS
    isn't a person's own variable, so it never is. A marker file named for the terminal session makes
    it once per shell, because a script can't change its shell's environment."""
    environ = os.environ if environ is None else environ
    old = [variable for variable in old_variables(environ)
           if not (variable == OLD_PREFIX + "USAGE_LOG" and environ[variable].strip().lower() in OFF)]
    if not old:
        return []
    if marker_dir is None:
        marker_dir = os.environ.get("TMPDIR") or "/tmp"
    if session is None:
        session = os.getsid(0) if hasattr(os, "getsid") else os.getppid()
    marker = os.path.join(str(marker_dir), "sanvio-old-names-{}".format(session))
    try:
        os.close(os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        return []  # this shell has been told already
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
