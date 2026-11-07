#!/usr/bin/env python3
"""Set a project's API security level and copy in exactly what that level needs. SPEC-034.

    python3 <harness>/tools/api-security/apply.py --level <off|guided|enforced|hardened> \
        [--lang python,typescript,php,dotnet] [--runtime lambda-httpapi] [--identity FILE] \
        [--lower] <repo>

  guided    .claude/rules/api-security-<lang>.md per language, a pointer in AGENTS.md, and for
            Python the library under security/api_security/, which the rules import
  enforced  adds the rest of security/ (the Semgrep rule, config, snapshot, allowed_signers,
            fixtures, VERSION), both workflows, and the .gates.yaml additions when the repo has
            a .gates.yaml (otherwise it prints them). Python `enforced` is for Lambda behind
            API Gateway HTTP API v2 dispatching through the library's Router, and says so with
            --runtime lambda-httpapi
  hardened  adds "hardened": true to security/config.json and security/hold-paths.txt, seeded
            with the handler modules config.json names

Every precondition is checked before anything is written, so a refused run changes nothing, and
a destination that is a symlink is refused. `workspace.security_level` is written last, in
--identity or the repo's own .studio-project.yaml. Lowering needs --lower, and never deletes
security/ or the workflows: that, and the branch protection that requires them, is the holder's
call. Stdlib only, Python 3.9 or later, so it runs on whatever python3 a holder has.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import List, Optional

TOOL = Path(__file__).resolve().parent
LEVELS = ("off", "guided", "enforced", "hardened")
LANGS = ("python", "typescript", "php", "dotnet")
ENFORCED_LANGS = ("python",)
RUNTIMES = ("lambda-httpapi",)
MARK = "# api-security"  # also matches the older "# api-security (SPEC-034)", so those strip too
AGENTS_START = "<!-- api-security:start (written by apply.py) -->"
AGENTS_START_ANY = r"<!-- api-security:start[^>]*-->"
AGENTS_END = "<!-- api-security:end -->"
DESTINATIONS = (".claude", ".claude/rules", "AGENTS.md", "security", "security/api_security",
                "security/semgrep", ".github", ".github/workflows", ".gates.yaml")
DEFAULT_FIELDS = "user_id|userId|account_id|accountId|owner_id|ownerId|device_id|deviceId|tenant_id|tenantId"
WORKFLOWS = ("security-check.yml", "security-approval.yml")


class Refused(Exception):
    pass


# ── VERSION: <number>+<hash of the library and the two workflows> ────

def content_hash(lib: Path, workflows: Path) -> str:
    """What a project copies verbatim: the library and the two workflows. The same hash over the
    tool and over a project shows whether the project's copy is the stamped one."""
    h = hashlib.sha256()
    files = sorted(f for f in lib.rglob("*") if f.is_file() and "__pycache__" not in f.parts
                   and f.suffix != ".pyc") if lib.is_dir() else []
    for f in files:
        h.update(b"api_security/" + f.relative_to(lib).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
    for name in WORKFLOWS:
        f = workflows / name
        h.update(b"workflows/" + name.encode() + b"\0" + (f.read_bytes() if f.is_file() else b"<absent>") + b"\0")
    return h.hexdigest()[:12]


def tool_hash() -> str:
    return content_hash(TOOL / "python" / "api_security", TOOL / "workflows")


def project_hash(repo: Path) -> str:
    return content_hash(repo / "security" / "api_security", repo / ".github" / "workflows")


def stamp() -> str:
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


# ── languages ────────────────────────────────────────────────────────

def detect_languages(repo: Path) -> List[str]:
    found = []
    if (repo / "pyproject.toml").exists() or (repo / "requirements.txt").exists():
        found.append("python")
    if (repo / "package.json").exists():
        found.append("typescript")
    if (repo / "composer.json").exists():
        found.append("php")
    if any(repo.glob("*.csproj")) or any(repo.glob("*.sln")) or any(repo.glob("src/**/*.csproj")):
        found.append("dotnet")
    return found


# ── guided ───────────────────────────────────────────────────────────

def rules_path(repo: Path, lang: str) -> Path:
    return repo / ".claude" / "rules" / f"api-security-{lang}.md"


def strip_agents_block(text: str) -> str:
    pattern = re.compile(r"\n*" + AGENTS_START_ANY + r".*?" + re.escape(AGENTS_END) + r"\n?", re.S)
    return pattern.sub("\n", text).rstrip("\n") + "\n"


def copy_library(repo: Path) -> None:
    sec = repo / "security"
    lib = sec / "api_security"
    if lib.exists():
        shutil.rmtree(lib)
    shutil.copytree(TOOL / "python" / "api_security", lib, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (sec / "__init__.py").touch()


def write_guided(repo: Path, langs: List[str], level: str) -> None:
    if "python" in langs:
        copy_library(repo)
    for lang in langs:
        dest = rules_path(repo, lang)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TOOL / "rules" / f"{lang}.md", dest)
    agents = repo / "AGENTS.md"
    text = strip_agents_block(agents.read_text(encoding="utf-8")) if agents.exists() else "# Agents\n"
    files = ", ".join(f"`.claude/rules/api-security-{lang}.md`" for lang in langs)
    block = (f"\n{AGENTS_START}\n## API security\n\n"
             f"This project's `security_level` is `{level}`. Before writing or changing an API handler, read {files}.\n"
             f"{AGENTS_END}\n")
    agents.write_text(text + block, encoding="utf-8")


def remove_guided(repo: Path) -> None:
    for lang in LANGS:
        p = rules_path(repo, lang)
        if p.exists():
            p.unlink()
    agents = repo / "AGENTS.md"
    if agents.exists():
        agents.write_text(strip_agents_block(agents.read_text(encoding="utf-8")), encoding="utf-8")


# ── enforced ─────────────────────────────────────────────────────────

def strip_gate_additions(text: str) -> str:
    return "".join(line for line in text.splitlines(keepends=True) if MARK not in line)


def _insert_under(lines: List[str], gate: str, items: List[str]) -> None:
    g = next((i for i, l in enumerate(lines) if re.match(rf"^(\s*){gate}:\s*(#.*)?$", l)), None)
    if g is None:
        raise Refused(f".gates.yaml has no `{gate}` gate; add the canonical one from repo-baseline.md first")
    g_indent = len(lines[g]) - len(lines[g].lstrip())
    r = None
    for i in range(g + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped and (len(lines[i]) - len(lines[i].lstrip())) <= g_indent:
            break
        if re.match(r"^\s*requires:\s*(#.*)?$", lines[i]):
            r = i
            break
    if r is None:
        raise Refused(f".gates.yaml's `{gate}` gate has no `requires:` list")
    r_indent = len(lines[r]) - len(lines[r].lstrip())
    item_indent = r_indent + 2
    for nxt in lines[r + 1:]:
        if nxt.strip():
            if nxt.lstrip().startswith("-"):
                item_indent = len(nxt) - len(nxt.lstrip())
            break
    pad = " " * item_indent
    lines[r + 1:r + 1] = [pad + item.replace("\n", "\n" + pad) for item in items]


ENFORCED_FILES = ("security/VERSION", "security/allowed_signers", "security/public-routes.txt",
                  ".github/workflows/security-check.yml", ".github/workflows/security-approval.yml")
CHECK_COMMAND = "python3 -m security.api_security.check"


def planned_gates(repo: Path) -> Optional[str]:
    """The .gates.yaml text `enforced` writes, or None when the repo has no .gates.yaml. Pure: a
    gates file it cannot extend refuses here, before anything is written."""
    path = repo / ".gates.yaml"
    if not path.exists():
        return None
    lines = strip_gate_additions(path.read_text(encoding="utf-8")).splitlines()
    _insert_under(lines, "repo_baseline", [f'- file_exists: "{f}"  {MARK}' for f in ENFORCED_FILES])
    _insert_under(lines, "deploy_ready", [
        f"- command:  {MARK}\n"
        f'    description: "API security check passes"  {MARK}\n'
        f'    run: "{CHECK_COMMAND}"  {MARK}'])
    return "\n".join(lines) + "\n"


def remove_gates(repo: Path) -> None:
    path = repo / ".gates.yaml"
    if path.exists():
        path.write_text(strip_gate_additions(path.read_text(encoding="utf-8")), encoding="utf-8")


def _copy_if_absent(src: Path, dest: Path) -> None:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)


def hold_globs(config: dict) -> List[str]:
    out = []
    for module in config.get("handler_modules") or []:
        if isinstance(module, str) and re.match(r"^[A-Za-z_][\w.]*$", module):
            base = module.replace(".", "/")
            out += [f"{base}.py", f"{base}/**"]
    return out


def write_hold_paths(sec: Path, config: dict, notes: List[str]) -> None:
    path = sec / "hold-paths.txt"
    _copy_if_absent(TOOL / "templates" / "hold-paths.txt", path)
    text = path.read_text(encoding="utf-8")
    have = {line.strip() for line in text.splitlines()}
    globs = hold_globs(config)
    missing = [g for g in globs if g not in have]
    if missing:
        path.write_text(text.rstrip("\n") + "\n" + "".join(f"{g}\n" for g in missing), encoding="utf-8")
    if not globs:
        notes.append("security/hold-paths.txt holds infrastructure only: config.json names no handler_modules "
                     "yet; add the handler paths to it, or re-run once config.json is filled in")


def write_enforced(repo: Path, hardened: bool, gates: Optional[str], notes: List[str]) -> None:
    sec = repo / "security"
    copy_library(repo)
    for name in ("config.json", "public-routes.txt", "allowed_signers", "fixtures.py"):
        _copy_if_absent(TOOL / "templates" / name, sec / name)

    config_path = sec / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["hardened"] = hardened
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    rule = (TOOL / "semgrep" / "identity-from-request.yml").read_text(encoding="utf-8")
    extra = [f for f in (config.get("identity_fields") or []) if re.match(r"^[A-Za-z0-9_-]+$", f)]
    if extra:
        rule = rule.replace(DEFAULT_FIELDS, DEFAULT_FIELDS + "|" + "|".join(extra))
    (sec / "semgrep").mkdir(exist_ok=True)
    (sec / "semgrep" / "identity-from-request.yml").write_text(rule, encoding="utf-8")

    wf = repo / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    for name in WORKFLOWS:
        src, dest = TOOL / "workflows" / name, wf / name
        if dest.exists() and dest.read_bytes() != src.read_bytes():
            notes.append(f"replaced .github/workflows/{name}, which differed from this version's")
        shutil.copyfile(src, dest)
    if hardened:
        write_hold_paths(sec, config, notes)
    shutil.copyfile(TOOL / "VERSION", sec / "VERSION")
    if gates is not None:
        (repo / ".gates.yaml").write_text(gates, encoding="utf-8")
    else:
        notes.append("no .gates.yaml, so none was changed. Where your gates live, require these files: "
                     + ", ".join(ENFORCED_FILES) + f"; and before a deploy, run `{CHECK_COMMAND}`")


def unharden(repo: Path) -> None:
    config_path = repo / "security" / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["hardened"] = False
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


# ── main ─────────────────────────────────────────────────────────────

def refuse_symlinks(repo: Path, rels) -> None:
    """A destination, or a folder on the way to it, that is a symlink could send a write or a
    delete outside the repo. Refuse rather than follow it."""
    for rel in rels:
        cur = repo
        for part in Path(rel).parts:
            cur = cur / part
            if cur.is_symlink():
                raise Refused(f"{cur.relative_to(repo)} is a symlink; apply.py writes only inside the repo")


def apply(repo: Path, level: str, langs: Optional[List[str]], lower: bool,
          runtime: Optional[str] = None, identity_path: Optional[Path] = None) -> List[str]:
    notes: List[str] = []
    if level not in LEVELS:
        raise Refused(f"unknown level {level!r}; use one of {', '.join(LEVELS)}")
    identity_path = identity_path or repo / ".studio-project.yaml"
    if not identity_path.exists():
        raise Refused(f"{identity_path} not found; create the project's identity file first, "
                      "or name it with --identity")
    identity = identity_path.read_text(encoding="utf-8")
    current = current_level(identity)
    rank = LEVELS.index
    if rank(level) < rank(current) and not lower:
        raise Refused(f"the project is at `{current}`; lowering it to `{level}` needs --lower")
    if level == current == "off":
        return ["already off; nothing to do"]

    langs = langs or detect_languages(repo)
    unknown = [l for l in langs if l not in LANGS]
    if unknown:
        raise Refused(f"unknown language(s) {', '.join(unknown)}; use {', '.join(LANGS)}")
    if level != "off" and not langs:
        raise Refused("no language detected; pass --lang")
    gates: Optional[str] = None
    if rank(level) >= rank("enforced"):
        missing = [l for l in langs if l not in ENFORCED_LANGS]
        if "python" not in langs or missing:
            raise Refused("`enforced` has a Python implementation only so far; this repo's "
                          f"{', '.join(missing) or 'languages'} would have no check. If the API is the "
                          "Python part, pass --lang python; otherwise stay at `guided`")
        if runtime not in RUNTIMES:
            raise Refused("Python `enforced` checks Lambda behind API Gateway HTTP API v2, dispatching "
                          "through the library's Router. If that is this API, pass --runtime "
                          "lambda-httpapi; any other framework stays at `guided` for now")
        gates = planned_gates(repo)
    refuse_symlinks(repo, DESTINATIONS + tuple(f".claude/rules/api-security-{l}.md" for l in LANGS)
                    + tuple(f".github/workflows/{w}" for w in WORKFLOWS))
    if identity_path.is_symlink():
        raise Refused(f"{identity_path} is a symlink; name the real file")

    if level == "off":
        remove_gates(repo)
        unharden(repo)
        remove_guided(repo)
        notes.append("security/ and the workflows were left in place; delete them and drop the required "
                     "checks from branch protection yourself if they are no longer wanted")
    else:
        write_guided(repo, langs, level)
        if rank(level) >= rank("enforced"):
            write_enforced(repo, hardened=(level == "hardened"), gates=gates, notes=notes)
            notes.append("next: fill in security/config.json, security/fixtures.py and security/allowed_signers, "
                         "then follow project-setup.md's order for requiring the two checks")
        else:
            remove_gates(repo)
            unharden(repo)
            if (repo / "security" / "config.json").exists():
                notes.append("security/ and the workflows were left in place; the gate additions were removed")

    identity_path.write_text(with_level(identity, level), encoding="utf-8")
    notes.insert(0, f"security_level: {current} -> {level}")
    return notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="apply.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--level")
    ap.add_argument("--stamp", action="store_true",
                    help="rewrite this tool's VERSION hash after changing the library or a workflow")
    ap.add_argument("--lang", help="comma-separated: " + ", ".join(LANGS) + " (default: detected)")
    ap.add_argument("--lower", action="store_true", help="allow lowering the level")
    ap.add_argument("--runtime", help="for Python enforced: " + ", ".join(RUNTIMES))
    ap.add_argument("--identity", help="the project's .studio-project.yaml, when it is not at the repo root")
    ap.add_argument("repo", nargs="?")
    args = ap.parse_args(argv)
    if args.stamp:
        print(stamp())
        return 0
    if not args.level or not args.repo:
        ap.error("--level and a repo are required")
    repo = Path(args.repo).resolve()
    langs = [l.strip() for l in args.lang.split(",")] if args.lang else None
    identity = Path(args.identity).absolute() if args.identity else None
    try:
        notes = apply(repo, args.level, langs, args.lower, args.runtime, identity)
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # anything unexpected is a failure, never a silent half-apply
        print(f"apply.py failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    for n in notes:
        print(n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
