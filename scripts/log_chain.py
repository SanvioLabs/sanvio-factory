#!/usr/bin/env python3
"""Chain a JSON-lines log's entries together, and check the chain.

link() gives an entry a `prev` field: the SHA-256 of the raw line written before it, so a line
edited, removed or inserted later no longer matches the line after it. verify() reads a log and
says whether its chain holds. It shows a log was changed, it doesn't stop it: an edit to the last
line, or lines dropped from the start, can't be seen.
"""
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
