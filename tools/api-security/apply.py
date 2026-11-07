#!/usr/bin/env python3
"""Set a project's API security level and copy in exactly what that level needs. SPEC-034.

    python3 <harness>/tools/api-security/apply.py --level <off|guided|enforced|hardened> \
        [--lang python,typescript,php,dotnet] [--lower] <repo>

  guided    .claude/rules/api-security-<lang>.md per language, and a pointer in AGENTS.md
  enforced  adds security/ (the Python library and check, the Semgrep rule, config, snapshot,
            allowed_signers, fixtures, VERSION), both workflows, and the .gates.yaml additions
  hardened  adds "hardened": true to security/config.json and security/hold-paths.txt

Writes `workspace.security_level` in the project's .studio-project.yaml last, so a failed run never
leaves a level the files do not back. Lowering needs --lower, and never deletes security/ or the
workflows: that, and the branch protection that requires them, is the holder's call.
Stdlib only, Python 3.9 or later, so it runs on whatever python3 a holder has.
"""
import argparse
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
MARK = "# api-security (SPEC-034)"
AGENTS_START = "<!-- api-security:start (SPEC-034, written by apply.py) -->"
AGENTS_END = "<!-- api-security:end -->"
DEFAULT_FIELDS = "user_id|userId|account_id|accountId|owner_id|ownerId|device_id|deviceId|tenant_id|tenantId"
WORKFLOWS = ("security-check.yml", "security-approval.yml")


class Refused(Exception):
    pass


# ── .studio-project.yaml ─────────────────────────────────────────────

def _scalar(raw: str) -> str:
    raw = raw.strip()
    if raw[:1] in ('"', "'"):
        end = raw.find(raw[0], 1)
        return raw[1:end] if end != -1 else raw[1:]
    return raw.split(" #")[0].strip()


def current_level(identity: str) -> str:
    for line in identity.splitlines():
        m = re.match(r"^\s+security_level:\s*(.*)$", line)
        if m:
            value = _scalar(m.group(1))
            return value if value in LEVELS else "off"
    return "off"


def with_level(identity: str, level: str) -> str:
    lines = identity.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^\s+security_level:", line):
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = f'{indent}security_level: "{level}"'
            return "\n".join(lines) + "\n"
    for i, line in enumerate(lines):
        if re.match(r"^workspace:\s*(#.*)?$", line):
            indent = "  "
            for nxt in lines[i + 1:]:
                if nxt.strip():
                    indent = nxt[: len(nxt) - len(nxt.lstrip())] or "  "
                    break
            lines.insert(i + 1, f'{indent}security_level: "{level}"')
            return "\n".join(lines) + "\n"
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
    pattern = re.compile(r"\n*" + re.escape(AGENTS_START) + r".*?" + re.escape(AGENTS_END) + r"\n?", re.S)
    return pattern.sub("\n", text).rstrip("\n") + "\n"


def write_guided(repo: Path, langs: List[str], level: str) -> None:
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


def write_gates(repo: Path) -> None:
    path = repo / ".gates.yaml"
    if not path.exists():
        raise Refused(".gates.yaml not found; `enforced` adds to its repo_baseline and deploy_ready gates")
    lines = strip_gate_additions(path.read_text(encoding="utf-8")).splitlines()
    files = ("security/VERSION", "security/allowed_signers", "security/public-routes.txt",
             ".github/workflows/security-check.yml", ".github/workflows/security-approval.yml")
    _insert_under(lines, "repo_baseline", [f'- file_exists: "{f}"  {MARK}' for f in files])
    _insert_under(lines, "deploy_ready", [
        f"- command:  {MARK}\n"
        f'    description: "API security check passes"  {MARK}\n'
        f'    run: "python3 -m security.api_security.check"  {MARK}'])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def remove_gates(repo: Path) -> None:
    path = repo / ".gates.yaml"
    if path.exists():
        path.write_text(strip_gate_additions(path.read_text(encoding="utf-8")), encoding="utf-8")


def _copy_if_absent(src: Path, dest: Path) -> None:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)


def write_enforced(repo: Path, hardened: bool) -> None:
    sec = repo / "security"
    lib = sec / "api_security"
    if lib.exists():
        shutil.rmtree(lib)
    shutil.copytree(TOOL / "python" / "api_security", lib, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (sec / "__init__.py").touch()
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
        shutil.copyfile(TOOL / "workflows" / name, wf / name)
    if hardened:
        _copy_if_absent(TOOL / "templates" / "hold-paths.txt", sec / "hold-paths.txt")
    shutil.copyfile(TOOL / "VERSION", sec / "VERSION")
    write_gates(repo)


def unharden(repo: Path) -> None:
    config_path = repo / "security" / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["hardened"] = False
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


# ── main ─────────────────────────────────────────────────────────────

def apply(repo: Path, level: str, langs: Optional[List[str]], lower: bool) -> List[str]:
    notes: List[str] = []
    if level not in LEVELS:
        raise Refused(f"unknown level {level!r}; use one of {', '.join(LEVELS)}")
    identity_path = repo / ".studio-project.yaml"
    if not identity_path.exists():
        raise Refused(f"{identity_path} not found; create the project's identity file first")
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
    if rank(level) >= rank("enforced"):
        missing = [l for l in langs if l not in ENFORCED_LANGS]
        if "python" not in langs or missing:
            raise Refused("`enforced` has a Python implementation only so far; this repo's "
                          f"{', '.join(missing) or 'languages'} would have no check. Stay at `guided`")

    if level == "off":
        remove_gates(repo)
        unharden(repo)
        remove_guided(repo)
        notes.append("security/ and the workflows were left in place; delete them and drop the required "
                     "checks from branch protection yourself if they are no longer wanted")
    else:
        write_guided(repo, langs, level)
        if rank(level) >= rank("enforced"):
            write_enforced(repo, hardened=(level == "hardened"))
            notes.append("next: fill in security/config.json, security/fixtures.py and security/allowed_signers, "
                         "then follow project-setup.md's order for requiring the two checks")
        else:
            remove_gates(repo)
            unharden(repo)
            if (repo / "security").exists():
                notes.append("security/ and the workflows were left in place; the gate additions were removed")

    identity_path.write_text(with_level(identity, level), encoding="utf-8")
    notes.insert(0, f"security_level: {current} -> {level}")
    return notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="apply.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--level", required=True)
    ap.add_argument("--lang", help="comma-separated: " + ", ".join(LANGS) + " (default: detected)")
    ap.add_argument("--lower", action="store_true", help="allow lowering the level")
    ap.add_argument("repo")
    args = ap.parse_args(argv)
    repo = Path(args.repo).resolve()
    langs = [l.strip() for l in args.lang.split(",")] if args.lang else None
    try:
        notes = apply(repo, args.level, langs, args.lower)
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
