"""Third-party actions pinned to a full commit SHA, SPEC-034 REQ-022 (hardened).

A tag such as `@v4` can be moved to different code after review; a 40-character SHA cannot.
Local actions (`./...`) and container images (`docker://...`) are out of this check's reach.
"""
import re
from pathlib import Path
from typing import Iterable, List

USES = re.compile(r"^\s*(?:-\s*)?uses:\s*['\"]?([^'\"\s#]+)", re.M)
SHA = re.compile(r"@[0-9a-f]{40}$")
SECURITY_WORKFLOWS = (".github/workflows/security-check.yml", ".github/workflows/security-approval.yml")


def unpinned(root: Path, workflows: Iterable[str]) -> List[str]:
    found: List[str] = []
    for rel in workflows:
        path = Path(root) / rel
        if not path.is_file():
            raise FileNotFoundError(f"{rel} is listed for the pin check but does not exist")
        for m in USES.finditer(path.read_text(encoding="utf-8")):
            ref = m.group(1)
            if ref.startswith("./") or ref.startswith("docker://"):
                continue
            if not SHA.search(ref):
                found.append(f"{rel}: {ref} is not pinned to a full commit SHA")
    return found
