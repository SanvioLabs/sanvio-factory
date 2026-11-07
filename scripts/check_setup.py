#!/usr/bin/env python3
"""Setup check: is this clone wired up the way the harness assumes?

Usage:
    python3 scripts/check_setup.py

Read-only. Prints one PASS, WARN or FAIL line per check, with the fix on the
line below. Exits 1 when anything FAILs, so you can run it in a script. A WARN
doesn't fail: it's something to decide, not something broken.
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STARTER = re.compile(r"[/:]SanvioLabs/sanvio-harness-starter(\.git)?/?$", re.I)


def git(root, *args):
    """A git command's output, or None when it fails (unset key, no remote)."""
    try:
        result = subprocess.run(["git", "-C", str(root)] + list(args),
                                capture_output=True, text=True)
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def check_python(version=None):
    version = version or sys.version_info[:3]
    shown = ".".join(str(n) for n in version)
    if tuple(version[:2]) >= (3, 9):
        return ("PASS", "python " + shown, None)
    return ("FAIL", "python " + shown + " is older than 3.9",
            "Install Python 3.9 or newer. No packages are needed.")


def check_hooks(root):
    path = git(root, "config", "core.hooksPath")
    if path == ".githooks":
        return ("PASS", "hooks: core.hooksPath is .githooks", None)
    fix = "git config core.hooksPath .githooks"
    if not path:
        return ("FAIL", "hooks: core.hooksPath is not set, so the pre-commit hook never runs",
                fix + "   (every check in the hook silently does nothing until you do)")
    return ("FAIL", "hooks: core.hooksPath is {}, not .githooks".format(path),
            fix + "   (hooks in {} stop running, so decide first)".format(path))


def check_links(root):
    """CLAUDE.md, .claude/skills and the Kiro steering link all lead back to the real files."""
    problems = []
    claude = root / "CLAUDE.md"
    if not claude.is_file() or "@AGENTS.md" not in claude.read_text():
        problems.append("CLAUDE.md doesn't import @AGENTS.md")
    skills = root / ".claude" / "skills"
    if not skills.is_dir() or skills.resolve() != (root / "skills").resolve():
        problems.append(".claude/skills isn't a link to skills/")
    steering = root / ".kiro" / "steering" / "project.md"
    if not steering.is_file() or steering.resolve() != (root / "AGENTS.md").resolve():
        problems.append(".kiro/steering/project.md isn't a link to AGENTS.md")
    for link in sorted((root / ".kiro" / "steering").glob("*.md")):
        if link.name != "project.md" and link.resolve() != (root / "steering" / link.name).resolve():
            problems.append(".kiro/steering/{} isn't a link to steering/{}".format(link.name, link.name))
    if not problems:
        return ("PASS", "links: CLAUDE.md, .claude/skills and .kiro/steering lead to the real files", None)
    return ("FAIL", "links: " + "; ".join(problems),
            "Re-clone with symlinks on (Windows: git clone -c core.symlinks=true, "
            "with Developer Mode on). Without them Claude Code won't find the skills.")


def safe_url(url):
    """The remote URL with any user:token@ part removed, so a credential never gets printed."""
    return re.sub(r"^([a-z+]+://)[^/@]+@", r"\1", url)


def repo_ref(url):
    """The remote as a credential-free https URL gh accepts: git@host:owner/repo becomes https://host/owner/repo."""
    url = safe_url(url)
    scp = re.match(r"^[^/@:]+@([^/:]+):(.+)$", url)
    if scp:
        url = "https://{}/{}".format(scp.group(1), scp.group(2))
    return re.sub(r"\.git/?$", "", url)


def check_remote(root):
    url = git(root, "remote", "get-url", "origin")
    if not url:
        return ("PASS", "remote: no origin, so nothing gets pushed anywhere yet", None)
    shown = safe_url(url)
    if STARTER.search(url):
        return ("WARN", "remote: origin is the public starter ({})".format(shown),
                "company/ stays on your machine either way. Make your own private copy "
                "before you push your own work: anything pushed to a public repo is public.")
    return ("WARN", "remote: origin is {}".format(shown),
            "If that repo is public, keep company material out of it. "
            "Check: gh repo view --json visibility")


def check_gate(root):
    example_dir = root / "examples" / "proposal"
    example = example_dir / "proposals" / "juniper-bakery.md"
    if not example.is_file():
        return ("WARN", "gate: examples/proposal/ is gone, so the example gate wasn't run",
                "Fine if you've removed the example on purpose.")
    result = subprocess.run([sys.executable, str(example_dir / "gates" / "proposal_gate.py"), str(example)],
                            capture_output=True, text=True)
    if result.returncode == 0:
        return ("PASS", "gate: the example proposal passes", None)
    return ("FAIL", "gate: the example proposal fails on a clone where it should pass",
            "Run python3 examples/proposal/gates/proposal_gate.py "
            "examples/proposal/proposals/juniper-bakery.md and "
            "git status to see what changed.")


def check_company_repo(company):
    """company/ is its own clone: ask GitHub whether the repo it pushes to is private."""
    origin = git(company, "remote", "get-url", "origin")
    if not origin:
        return ("WARN", "company: company/ is a git repo with no origin, so its visibility can't be checked",
                "Push it to a private repo, then check: gh repo view <url> --json visibility")
    ref = repo_ref(origin)
    command = "gh repo view {} --json visibility -q .visibility".format(ref)
    if not shutil.which("gh"):
        return ("WARN", "company: company/ is a clone of {}, and without gh its visibility can't be "
                "checked".format(ref), "Install gh, or check by hand: " + command)
    try:
        result = subprocess.run(["gh", "repo", "view", ref, "--json", "visibility", "-q", ".visibility"],
                                capture_output=True, text=True, timeout=15)
        visibility = result.stdout.strip().upper() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        visibility = ""
    if visibility == "PUBLIC":
        return ("FAIL", "company: company/ is a clone of {}, which is public".format(ref),
                "Make that repo private now: anyone can read what's in it.")
    if visibility in ("PRIVATE", "INTERNAL"):
        return ("PASS", "company: company/ is a clone of {}, which is {}".format(ref, visibility.lower()), None)
    return ("WARN", "company: couldn't check whether {} is private".format(ref),
            "Check by hand: " + command)


def check_company(root):
    if (root / "company" / ".git").exists():
        return check_company_repo(root / "company")
    if git(root, "ls-files", "company/"):
        return ("WARN", "company: the company record is committed in this harness, so it goes wherever "
                "the harness is pushed", "Keep this repo private. Check: gh repo view --json visibility")
    record = root / "company" / "COMPANY.md"
    if record.is_file():
        return ("PASS", "company: company/COMPANY.md is written", None)
    return ("WARN", "company: no company record yet, so the agent doesn't know who it works for",
            "Run /orientation, or say \"get me started\", and it interviews you for it.")


def skill_names(folder):
    """{name: path} for every skill in a skills folder, by folder name and frontmatter name."""
    names = {}
    for skill in sorted(Path(folder).glob("*/SKILL.md")):
        names[skill.parent.name] = skill
        match = re.search(r"^name:\s*(\S+)", skill.read_text(errors="replace"), re.M)
        if match:
            names[match.group(1)] = skill
    return names


def check_shadowed_skills(root, home=None):
    """A personal skill with the same name as one of this repo's wins, so the repo's never runs."""
    personal = Path(home or Path.home()) / ".claude" / "skills"
    clashes = sorted(set(skill_names(root / "skills")) & set(skill_names(personal)))
    if not clashes:
        return ("PASS", "skills: no personal skill hides one of this repo's", None)
    return ("WARN", "skills: your personal ~/.claude/skills has {} too, and in Claude Code the personal "
            "copy wins, so this repo's never runs".format(", ".join(clashes)),
            "Keep one copy. Move what you want into skills/ here, then rename or remove the personal "
            "one, so everyone using this harness runs the same skill.")


API_SECURITY_TOOL = Path(__file__).resolve().parent.parent / "tools" / "api-security" / "apply.py"


def _api_security_tool():
    """The levels, the files each needs, the identity-file parser and the content stamp come from
    the tool itself, so this check and apply.py cannot disagree."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_api_security_apply", str(API_SECURITY_TOOL))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_security_levels(root):
    """Each project's API security level (steering/api-security.md). Off is never a problem on its
    own; a live or regulated project at off is, and so is a level its files don't back, or a copy
    of the tool that no longer matches its stamp."""
    try:
        tool = _api_security_tool()
    except Exception as exc:  # report it; the setup check never stops on one line
        return ("WARN", "security: tools/api-security/apply.py could not be loaded ({})".format(exc),
                "Restore tools/api-security/ from the harness.")
    levels, warnings = [], []
    for folder in sorted(p for p in (root / "projects").glob("*") if p.is_dir()):
        identity = folder / ".studio-project.yaml"
        if not identity.is_file():
            continue
        fields = tool.workspace_fields(identity.read_text(errors="replace"))
        raw = fields.get("security_level", "off")
        level = raw if raw in tool.LEVELS else "off"
        levels.append("{} {}".format(folder.name, level))
        if raw not in tool.LEVELS:
            warnings.append("{} says security_level {!r}, which is not a level".format(folder.name, raw))
        if level == "off":
            why = [k + ": true" for k in ("live_users", "regulated") if fields.get(k) == "true"]
            if why:
                warnings.append("{} is off with {}".format(folder.name, " and ".join(why)))
            continue
        missing = [] if list((folder / ".claude" / "rules").glob("api-security-*.md")) else [".claude/rules"]
        missing += [f for f in tool.required_files(level) if not (folder / f).exists()]
        if missing:
            warnings.append("{} is {} but {} missing".format(folder.name, level, ", ".join(missing)))
        stamp = folder / "security" / "VERSION"
        digest = stamp.read_text().strip().partition("+")[2] if stamp.is_file() else ""
        if digest and tool.project_hash(folder) != digest:
            warnings.append("{}'s security/api_security or security workflows differ from its stamp".format(folder.name))
    if warnings:
        return ("WARN", "security: " + "; ".join(warnings),
                "Run python3 tools/api-security/apply.py --level <level> projects/<name>. "
                "steering/api-security.md has what each level means.")
    if not levels:
        return ("PASS", "security: no project under projects/ declares an API security level", None)
    return ("PASS", "security: " + ", ".join(levels), None)


def run(root, home=None):
    return [check_python(), check_hooks(root), check_links(root), check_gate(root),
            check_company(root), check_shadowed_skills(root, home), check_security_levels(root),
            check_remote(root)]


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    results = run(ROOT)
    for status, line, fix in results:
        print("{} {}".format(status, line))
        if fix:
            print("     {}: {}".format("fix" if status == "FAIL" else "note", fix))
    return 1 if any(status == "FAIL" for status, _, _ in results) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
