"""The surface apply.py shares with harness-health and the starter's setup check, SPEC-034.

They load this file by path, so every name here is a promise: the levels, the files each needs,
the identity-file parser, the VERSION hash and the apply.py command a check prints.
`tests/test_levels.py` pins the names. Stdlib only, Python 3.9 or later.

Two names write, and only apply.py calls them: `with_level` (the identity file) and `stamp`
(this tool's VERSION). They sit here because they share the parser and the hash with the readers;
a check that calls either is a bug.
"""
import hashlib
import json
import re
import shlex
from pathlib import Path
from typing import List, Optional, Sequence

TOOL = Path(__file__).resolve().parent
LEVELS = ("off", "guided", "enforced", "hardened")
WORKFLOWS = ("security-check.yml", "security-approval.yml")
ENFORCED_FILES = ("security/VERSION", "security/allowed_signers", "security/public-routes.txt",
                  ".github/workflows/security-check.yml", ".github/workflows/security-approval.yml")
RUNTIMES = ("lambda-httpapi",)
# The identity field names the Semgrep rule matches, in each of its RULE_FIELD_SITES patterns.
# apply.py inserts a project's `identity_fields` straight after this string, and the hash takes
# exactly that insertion back out, so nothing else in the rule escapes the hash.
DEFAULT_FIELDS = "user_id|userId|account_id|accountId|owner_id|ownerId|device_id|deviceId|tenant_id|tenantId"
RULE_FIELD_SITES = 5
FIELD_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


class Refused(Exception):
    pass


# ── The Semgrep rule's identity fields ─────────────────────────────

def identity_extras(config: object) -> List[str]:
    """The extra field names a parsed `security/config.json` adds to the rule; anything that is
    not a list of plain names adds none."""
    fields = config.get("identity_fields") if isinstance(config, dict) else None
    if not isinstance(fields, list):
        return []
    return [f for f in fields if isinstance(f, str) and FIELD_NAME.match(f)]


def rule_with_fields(rule: str, extras: Sequence[str]) -> str:
    """The rule a project holds: `extras` inserted after DEFAULT_FIELDS at every site."""
    return rule.replace(DEFAULT_FIELDS, DEFAULT_FIELDS + "|" + "|".join(extras)) if extras else rule


def _project_extras(repo: Path) -> List[str]:
    try:
        return identity_extras(json.loads((repo / "security" / "config.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


# ── VERSION: <number>+<hash of what a project copies verbatim> ────

def content_hash(lib: Path, workflows: Path, rule: Path, extras: Sequence[str] = ()) -> str:
    """What a project copies verbatim: the library, the two workflows and the Semgrep rule, with
    exactly the identity fields `extras` the project added taken back out. The same hash over the
    tool and over a project shows whether the project's copy is the stamped one. Templates and
    rules files are left out: a project fills them in by design."""
    h = hashlib.sha256()
    files = sorted(f for f in lib.rglob("*") if f.is_file() and "__pycache__" not in f.parts
                   and f.suffix != ".pyc") if lib.is_dir() else []
    for f in files:
        h.update(b"api_security/" + f.relative_to(lib).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
    for name in WORKFLOWS:
        f = workflows / name
        h.update(b"workflows/" + name.encode() + b"\0" + (f.read_bytes() if f.is_file() else b"<absent>") + b"\0")
    text = rule.read_text(encoding="utf-8") if rule.is_file() else "<absent>"
    if extras:
        text = text.replace(DEFAULT_FIELDS + "|" + "|".join(extras), DEFAULT_FIELDS)
    h.update(b"semgrep/identity-from-request.yml\0" + text.encode() + b"\0")
    return h.hexdigest()[:12]


def tool_hash() -> str:
    return content_hash(TOOL / "python" / "api_security", TOOL / "workflows",
                        TOOL / "semgrep" / "identity-from-request.yml")


def project_hash(repo: Path) -> str:
    return content_hash(repo / "security" / "api_security", repo / ".github" / "workflows",
                        repo / "security" / "semgrep" / "identity-from-request.yml", _project_extras(repo))


# ── The command a check prints ───────────────────────────────────────

def apply_command(tool: str, level: str, repo: Path, identity: Optional[Path] = None) -> str:
    """The apply.py line that takes `repo` to `level`, runnable as printed from the root `tool` and
    the paths are relative to. `--identity` is added when the identity file is not the repo's own."""
    argv = ["python3", tool, "--level", level]
    if level in LEVELS and LEVELS.index(level) >= LEVELS.index("enforced"):
        argv += ["--runtime", RUNTIMES[0]]
    if identity is not None and Path(identity).parent != Path(repo):
        argv += ["--identity", str(identity)]
    return " ".join(shlex.quote(a) for a in argv + [str(repo)])


def stamp() -> str:
    """Rewrite this tool's VERSION. apply.py --stamp only."""
    number = (TOOL / "VERSION").read_text(encoding="utf-8").strip().partition("+")[0]
    value = f"{number}+{tool_hash()}"
    (TOOL / "VERSION").write_text(value + "\n", encoding="utf-8")
    return value


# ── .studio-project.yaml ─────────────────────────────────────────────

def _scalar(raw: str) -> str:
    raw = raw.strip()
    if raw[:1] in ('"', "'"):
        end = raw.find(raw[0], 1)
        return raw[1:end] if end != -1 else raw[1:]
    return raw.split(" #")[0].strip()


WORKSPACE_KEYS = ("security_level", "live_users", "regulated")


def _workspace_lines(identity: str):
    """(index, line) for each line inside the top-level `workspace:` block. Blank lines and
    comments, at any indent, neither end the block nor count as its content."""
    lines = identity.splitlines()
    inside = False
    for i, line in enumerate(lines):
        if re.match(r"^workspace:\s*(#.*)?$", line):
            inside = True
            continue
        if not inside or not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            return
        yield i, line


def workspace_fields(identity: str) -> dict:
    """security_level, live_users and regulated from the `workspace:` block, lower-cased. The one
    parser apply.py, harness-health and the starter's setup check share."""
    fields = {}
    for _, line in _workspace_lines(identity):
        m = re.match(r"^\s+(" + "|".join(WORKSPACE_KEYS) + r"):\s*(.*)$", line)
        if m and m.group(1) not in fields:
            fields[m.group(1)] = _scalar(m.group(2)).lower()
    return fields


def current_level(identity: str) -> str:
    """The declared level; absent or unrecognised is `off`."""
    value = workspace_fields(identity).get("security_level", "off")
    return value if value in LEVELS else "off"


def required_files(level: str) -> List[str]:
    """The files a level needs beyond the rules file, as harness-health and the setup check test."""
    if level not in LEVELS or LEVELS.index(level) < LEVELS.index("enforced"):
        return []
    return list(ENFORCED_FILES) + (["security/hold-paths.txt"] if level == "hardened" else [])


def with_level(identity: str, level: str) -> str:
    """The identity file with `security_level` set. Writes nothing itself; apply.py only."""
    lines = identity.splitlines()
    block = list(_workspace_lines(identity))
    for i, line in block:
        if re.match(r"^\s+security_level:", line):
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = f'{indent}security_level: "{level}"'
            return "\n".join(lines) + "\n"
    for i, line in enumerate(lines):
        if re.match(r"^workspace:\s*(#.*)?$", line):
            indent = block[0][1][: len(block[0][1]) - len(block[0][1].lstrip())] if block else "  "
            lines.insert(i + 1, f'{indent}security_level: "{level}"')
            return "\n".join(lines) + "\n"
    if re.search(r"^workspace:", identity, re.M):
        raise Refused("the identity file's `workspace:` is not a block mapping; add security_level by hand")
    return identity.rstrip("\n") + f'\n\nworkspace:\n  security_level: "{level}"\n'
