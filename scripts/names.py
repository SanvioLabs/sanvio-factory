"""The names this repo took when it became Sanvio Factory, and the old ones it still reads for a release.

The state folder is .sanvio/, the variables are SANVIO_*, and the home folders are ~/.sanvio-loop and
~/.sanvio-evals. Until the release that removes them, each old name still works: .harness/ is read while
.sanvio/ is missing, a HARNESS_* variable counts where its SANVIO_* one isn't set, and the old home folders
are read while the new ones are missing. .claude/hooks/session_start.py moves .harness/ across once and
names any old variable still set, so the warning comes once a session and never from a hook that runs on
every tool call.

Standard library only: the hooks and the loop import it, and so does a fresh clone before setup.
"""
import os
from pathlib import Path

STATE, OLD_STATE = ".sanvio", ".harness"
PREFIX, OLD_PREFIX = "SANVIO_", "HARNESS_"
# The variables a person sets themselves. SANVIO_HEADLESS isn't one: bin/factory sets it for the run.
PERSONAL = ("PULSE_FOLDER", "RETRO", "USAGE_LOG", "EVALS_HOME")


def either(new, old):
    """The new folder, unless it's missing and the old one is there."""
    new, old = Path(new), Path(old)
    return old if not new.exists() and old.exists() else new


def state_dir(root):
    """The repo's own state folder: .sanvio/, or .harness/ while that's all there is."""
    return either(Path(root) / STATE, Path(root) / OLD_STATE)


def loop_homes(home=None):
    """Both home folders the loop's checkouts can be in, the new one first."""
    home = Path(home) if home else Path.home()
    return home / ".sanvio-loop", home / ".harness-loop"


def loop_home(home=None):
    """Where the loop keeps its checkouts when loop.json names no worktree_dir."""
    return either(*loop_homes(home))


def evals_home(home=None, environ=None):
    """Where eval_harness.py keeps each run's sealed copy: SANVIO_EVALS_HOME, else the home folder."""
    named = env("EVALS_HOME", environ=environ)
    if named:
        return Path(named)
    home = Path(home) if home else Path.home()
    return either(home / ".sanvio-evals", home / ".harness-evals")


def env(name, default="", environ=None):
    """SANVIO_<name> if it's set, else HARNESS_<name>, else the default."""
    environ = os.environ if environ is None else environ
    for prefix in (PREFIX, OLD_PREFIX):
        if prefix + name in environ:
            return environ[prefix + name]
    return default


def headless(environ=None):
    """Either name says this run is headless. The stricter reading always wins, so a run bin/harness
    started stays headless under a guard that only knows the new name, and the other way round."""
    environ = os.environ if environ is None else environ
    return environ.get(PREFIX + "HEADLESS") == "1" or environ.get(OLD_PREFIX + "HEADLESS") == "1"


def old_variables(environ=None):
    """The old names of a person's own variables still set without the new one beside them."""
    environ = os.environ if environ is None else environ
    return [OLD_PREFIX + name for name in PERSONAL if OLD_PREFIX + name in environ and PREFIX + name not in environ]


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
        return "couldn't move .harness/ to .sanvio/ ({}), so .harness/ is still read. Move it by hand".format(
            error.strerror or error)
    return "moved .harness/ to .sanvio/, the new name for this repo's own state, with everything in it"
