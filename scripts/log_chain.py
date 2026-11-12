#!/usr/bin/env python3
"""Chain a JSON-lines log's entries together, and check the chain.

link() gives an entry a `prev` field: the SHA-256 of the raw line written before it, so a line
edited, removed or inserted later no longer matches the line after it. verify() reads a log and
says whether its chain holds. It shows a log was changed, it doesn't stop it: an edit to the last
line, or lines dropped from the start, can't be seen.
"""
import contextlib
import hashlib
import json
from pathlib import Path


def digest(raw):
    """The SHA-256 hex of a raw line, bytes or text, with one trailing newline removed first."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    return hashlib.sha256(raw).hexdigest()


def link(previous_line, entry):
    """A copy of entry with prev set to previous_line's hash, or to "" when there's no line before it."""
    return dict(entry, prev=digest(previous_line) if previous_line else "")


def prev_of(raw):
    """A raw line's prev when the line is a JSON object whose prev is a string, otherwise None."""
    try:
        found = json.loads(raw)
    except ValueError:
        return None
    if isinstance(found, dict) and isinstance(found.get("prev"), str):
        return found["prev"]
    return None


def verify(path):
    """"intact", "unchained" (no line carries prev), or the 1-based number of the first line whose prev
    doesn't match the line before it.

    The first line that carries prev starts the chain and isn't checked, so a log chained part way
    through, or with its first lines pruned, still reads as intact. Lines before it are ignored. Every
    later line has to carry prev, the hash of the raw line before it. A file that is missing, empty or
    can't be read is "unchained".
    """
    try:
        data = Path(path).read_bytes()
    except OSError:
        return "unchained"
    lines = data.split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    start = next((n for n, raw in enumerate(lines) if prev_of(raw) is not None), None)
    if start is None:
        return "unchained"
    for n in range(start + 1, len(lines)):
        if prev_of(lines[n]) != digest(lines[n - 1]):
            return n + 1
    return "intact"


@contextlib.contextmanager
def locked(path):
    """Hold an exclusive lock on path's .lock file beside it, so writers to the same log take turns:
    two appends that both read the same last line would break the chain. fcntl's flock, or msvcrt's lock
    on Windows. A lock that can't be taken is skipped rather than blocking whoever writes."""
    lock_path = Path(path).with_name(Path(path).name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a")
    try:
        try:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        except ImportError:
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        except OSError:
            pass
        yield
    finally:
        handle.close()  # closing the file lets the lock go


def last_line(path):
    """The last non-empty raw line of the file at path, as bytes, or None when it's missing or empty.
    Reads back from the end, so a long log isn't read whole."""
    try:
        handle = open(path, "rb")
    except OSError:
        return None
    with handle:
        handle.seek(0, 2)
        pos, tail = handle.tell(), b""
        while pos > 0:
            step = min(4096, pos)
            pos -= step
            handle.seek(pos)
            tail = handle.read(step) + tail
            body = tail.rstrip(b"\n")
            if b"\n" in body:
                return body.rsplit(b"\n", 1)[1]
        return tail.rstrip(b"\n") or None


def append(path, entry):
    """Append entry to the log at path as one JSON line, linked to the line before it, under the lock."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with locked(path):
        line = json.dumps(link(last_line(path), entry))
        with open(path, "a", encoding="utf-8") as out:
            out.write(line + "\n")

