"""Every Semgrep suppression of the identity rules carries a reason. SPEC-034 REQ-013.

    python3 -m security.api_security.markers [--root DIR]

Semgrep honours `nosem` and `nosemgrep` in any case, with rule ids separated by commas or spaces
and with or without text after them, so the reason is enforced here:
`nosemgrep: api-security.identity-from-request.<lang> -- <why>`. The fully qualified id semgrep
prints in CI (`security.semgrep.api-security...`) counts the same. A bare marker silences every
rule on its line, these included, and fails whatever follows it. The library's own copy under
`security/api_security/` is not scanned. Exit 0 clean, 1 a finding, 2 could not run.
"""
import argparse
import re
import sys
from pathlib import Path
from typing import List

RULE_PREFIX = "api-security.identity-from-request"
NOSEMGREP = re.compile(r"\bnosem(?:grep)?\b(?P<colon>:)?(?P<body>.*)$", re.IGNORECASE)
# Folders semgrep itself skips by default (a marker there silences nothing), and nothing it scans:
# `bin/`, `obj/`, `venv/`, `.terraform/` and a folder named `semgrep` are all read.
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "vendor", "dist", "build", "test", "tests",
             ".env", ".tox", ".npm", ".yarn"}
OWN = (("security", "api_security"), ("security", "semgrep"))  # the library and the rule tests
SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".php", ".cs"}


def unreasoned(root: Path) -> List[str]:
    root = Path(root)
    found: List[str] = []
    for path in sorted(root.rglob("*")):
        if path.suffix not in SUFFIXES or not path.is_file():
            continue
        parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in parts[:-1]) or parts[:2] in OWN:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            what = _problem(line)
            if what:
                found.append(f"{path.relative_to(root)}:{n}: {what}; "
                             f"write `nosemgrep: {RULE_PREFIX}.<lang> -- <why this is safe>`")
    return found


def _problem(line: str) -> str:
    m = NOSEMGREP.search(line)
    if not m:
        return ""
    if not m.group("colon"):
        return "bare nosemgrep silences the identity rules"
    ids_part, sep, reason = m.group("body").partition("--")
    ids = [i for i in re.split(r"[,\s]+", ids_part.strip()) if i]
    if not any(RULE_PREFIX in i for i in ids):
        return ""  # a marker for other rules is not this check's business
    if not sep or not reason.strip():
        return "marker has no reason"
    return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="api_security.markers")
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    try:
        found = unreasoned(Path(args.root).resolve())
    except Exception as exc:  # fail closed
        print(f"api-security markers could not run: {type(exc).__name__}: {exc}")
        return 2
    for f in found:
        print(f"FAIL {f}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
