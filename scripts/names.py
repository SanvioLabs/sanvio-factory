"""The names this repo uses: its state folder, its variables and its home folders.

The state folder is .sanvio/, the variables are SANVIO_*, and the home folders are ~/.sanvio-loop and
~/.sanvio-evals. Two old switches still count, because they only ever make things stricter:
HARNESS_HEADLESS=1 still makes a run headless, and HARNESS_USAGE_LOG=off still turns the usage log off.
The first read of the real environment also warns once about an old variable still set, where
old_names.py is beside this file to do it. Without it, only the new names are read and nothing warns.

Standard library only: everything here imports it, a fresh clone included, before any setup.
"""
import os
from pathlib import Path

STATE = ".sanvio"
PREFIX = "SANVIO_"
# The old prefix, read here only for the two switches above.
_STRICTER = "HARNESS_"
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
    """Where each eval run keeps its sealed copy: SANVIO_EVALS_HOME, else the home folder."""
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
    return environ.get(PREFIX + "HEADLESS") == "1" or environ.get(_STRICTER + "HEADLESS") == "1"


def logging_off(environ=None):
    """The usage log is switched off. The old name's off still counts: like headless, it only ever means
    less is recorded, so someone who opted out stays opted out."""
    if environ is None:
        check_real_environment()
        environ = os.environ
    return any(environ.get(prefix + "USAGE_LOG", "").strip().lower() in OFF for prefix in (PREFIX, _STRICTER))


def check_real_environment():
    """Warn about old names in this process's own environment, the first time anything here reads it."""
    global _checked
    if _checked:
        return
    _checked = True
    try:
        import old_names
    except ModuleNotFoundError as error:
        if error.name != "old_names":
            raise
        return  # a copy that took this file alone has no old names to warn about
    old_names.warn_unless_in_a_hook()
