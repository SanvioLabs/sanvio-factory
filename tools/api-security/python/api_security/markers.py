"""Every Semgrep suppression of the identity rules carries a reason. SPEC-034 REQ-013.

    python3 -m security.api_security.markers [--root DIR]

Semgrep honours `nosemgrep: <rule>` with or without text after it, so the reason is enforced here:
`nosemgrep: api-security.identity-from-request.<lang> -- <why>`. A bare `nosemgrep` silences every
rule on its line, these included, and fails too. Exit 0 clean, 1 a finding, 2 could not run.
"""
import argparse
import re
import sys
from pathlib import Path
from typing import List

RULE_PREFIX = "api-security.identity-from-request"
NOSEMGREP = re.compile(r"nosemgrep(?::\s*(?P<ids>[^\s]+))?(?P<rest>.*)$")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "vendor", "bin", "obj", "dist", "build",
             "__pycache__", ".terraform", "semgrep"}
SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".php", ".cs"}


def unreasoned(root: Path) -> List[str]:
    root = Path(root)
    found: List[str] = []
    for path in sorted(root.rglob("*")):
        if path.suffix not in SUFFIXES or not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            m = NOSEMGREP.search(line)
            if not m:
                continue
            ids = m.group("ids")
            if ids and not any(i.startswith(RULE_PREFIX) for i in ids.split(",")):
                continue
            reason = m.group("rest").strip()
            if not reason.startswith("--") or not reason[2:].strip():
                where = f"{path.relative_to(root)}:{n}"
                what = "bare nosemgrep silences the identity rules" if not ids else "marker has no reason"
                found.append(f"{where}: {what}; write `nosemgrep: {RULE_PREFIX}.<lang> -- <why this is safe>`")
    return found


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
