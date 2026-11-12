#!/usr/bin/env python3
"""Claude Code guard: runs before every tool call the agent makes.

From Sanvio Factory by Sanvio Labs, MIT: https://github.com/SanvioLabs/sanvio-factory

Wired in .claude/settings.json as a PreToolUse hook. Four jobs:

1. Credentials stay unread. A Read, Edit or Write on a credential file, a Grep
   whose path or glob names one (or a .ssh, .aws, .gnupg or .kube folder) or
   whose glob can only match one, or a shell command that names one, is
   refused. Env files, .pem and .key files, keystores (.p12, .pfx, .jks,
   .keystore), SSH and GnuPG keys, cloud and Kubernetes config, service-account
   files, .htpasswd and Docker's login file all count. A path is checked as
   written and once resolved, in any case, so a link to one counts. Glob lists
   names without reading them, so it isn't, and nor is a Grep over a folder
   that happens to hold one: the guard sees the call's arguments, not the files
   the search opens.
2. A connector call that isn't a plain read asks first. An MCP tool runs
   unasked only when its name says it gets, lists, searches, reads, finds,
   queries, fetches or views, and nothing in it says it sends, creates, edits,
   deletes, shares, runs or executes. Any other is put to the human, so a tool
   nobody has seen yet asks rather than slips through. It goes by the name, so
   a read tool with an odd name (git_status) asks too.
3. The security-reviewer agent's shell runs audits and nothing else. It reads
   code someone else may have written, and that code can carry text meant to
   steer it. A command on the audit list runs without a prompt; any other is
   refused.
4. A run bin/factory started (SANVIO_HEADLESS=1, or the stricter old
   HARNESS_HEADLESS=1) reads a pull request or an issue by number and nothing else.
   Nobody is watching it, and what it reads was written by someone else. Its
   shell runs only `gh pr view <n>`,
   `gh pr diff <n>` and `gh issue view <n>`, with `--comments` on a view, no
   connector runs at all, and its file tools (Read, Grep and Glob among them)
   reach only paths inside the harness root, after `..` and links resolve.
   Inside the root, they don't reach the files that hold tokens or company
   data: .claude/settings.local.json, any .git folder or bare repo (*.git),
   and the folders PRIVATE_FOLDERS lists below. Each headless Grep is passed on
   with those folders and !*.git added to its glob as excludes, so it leaves
   them out, and bare repos at any depth.

A call this hook can't check, because its input is unreadable or the hook has a bug, goes through with a
warning in a person's session. In a headless run, and in an agent scripts/loop.py started
(SANVIO_UNATTENDED=1), nobody reads the warning, so it's refused instead.

AGENTS.md says the same thing as a rule. This is the part that holds when the
agent decides otherwise. It's a backstop for honest mistakes, not a sandbox: a
command built to dodge it can.

Claude Code only. The git hook in .githooks/ is the check every tool shares.
"""
import fnmatch
import json
import os
import re
import shlex
import sys
import traceback

CREDENTIAL = re.compile(
    r"(^|[\s/'\"=<:])("  # : as well, for git show HEAD:.env
    r"\.env(\.(?!example\b|sample\b|template\b)[\w.-]+)?"  # .env, .env.local, not .env.example
    # A .key named with one character counts only in a path: in a command, s.key is code's property access
    r"|[\w.-]*\.pem|(?:[\w.-]{2,})?\.key|(?<=[/:])[\w.-]\.key|id_(rsa|ed25519|ecdsa)[\w.-]*"
    r"|\.aws/credentials|\.ssh/[\w.-]+|\.netrc|\.npmrc|\.pypirc"
    r"|[\w.-]*\.(p12|pfx|jks|keystore)|\.kube/config|service-account[\w.-]*\.json"
    r"|\.htpasswd|\.docker/config\.json|\.gnupg/[\w.-]+"
    r")(?=$|[\s'\";|&>)])"
)
# The usage log and the loop's logs. An agent reads them, never writes, moves or deletes them (AU-9).
LOG_PATH = (r"(?:^|(?<=[/\s'\"=<:]))(?:\.sanvio/usage(?:/[^\s'\";|&>]*)?"
            r"|\.loop/(?:[^\s'\";|&>]*/)?(?:loop|agent)\.log)(?=$|[\s'\";|&>)])")
LOG_FILE = re.compile(LOG_PATH)
LOG_REDIRECT = re.compile(r">>?\|?\s*['\"]?(?:[^\s'\";|&>]*/)?" + LOG_PATH.replace("(?:^|(?<=[/\s'\"=<:]))", ""))
LOG_CHANGERS = {"rm", "mv", "truncate", "shred", "unlink", "tee", "rmdir"}
LOG_IN_PLACE = re.compile(r"^(?:sed|perl|ruby)$")
LOG_COPIERS = {"cp", "install", "ln", "rsync", "dd"}
LOGS_ARE_READ_ONLY = ("{} is one of the factory's logs. Agents read them and never write, move or delete them, "
                      "so a change to one shows as tampering. Ask a human if a log needs to change.")


def log_write(command):
    """The log a shell command writes to, moves or deletes, or None. Reading one, or copying one out, is fine."""
    for segment in re.split(r"&&|\|\||;|\||\n", command):
        found = LOG_REDIRECT.search(segment)
        if found:
            return LOG_FILE.search(segment[found.start():]).group(0)
        named = LOG_FILE.search(segment)
        if not named:
            continue
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        while words and re.match(r"^\w+=", words[0]):
            words = words[1:]  # FOO=bar rm ...
        if words and words[0] in ("sudo", "command", "env"):
            words = words[1:]
        if not words:
            continue
        verb = os.path.basename(words[0])
        if verb in LOG_CHANGERS:
            return named.group(0)
        if LOG_IN_PLACE.match(verb) and any(w == "-i" or w.startswith("-i") or w.startswith("--in-place")
                                            or (w.startswith("-") and not w.startswith("--") and "i" in w[1:])
                                            for w in words[1:]):
            return named.group(0)
        if verb in LOG_COPIERS:
            target = words[-1][3:] if verb == "dd" and words[-1].startswith("of=") else words[-1]
            if LOG_FILE.search(target):
                return named.group(0)
    return None


SECRET_COMMANDS = re.compile(
    r"\bsecretsmanager\s+get-secret-value\b|\bssm\s+get-parameters?\b.*--with-decryption"
    r"|\bgh\s+auth\s+token\b|\bprintenv\b|^\s*env\s*($|[|>])",
    re.I,  # the Mac's disk finds an upper-case name as the lower-case command
)
# `test -e .env`, `[ -f .env ]`: whether a file exists, which is the check the
# steering asks for. It's taken out before the credential match, so the rest of
# the command still has to pass: `test -f .env && cat .env` is still refused.
EXISTENCE_CHECK = re.compile(
    r"\btest\s+-[efs]\s+[^\s;|&]+|\[\[?\s+-[efs]\s+[^\s;|&\]]+\s+\]\]?"
)
WRITE_VERBS = re.compile(
    r"(^|_)(send|create|update|edit|write|delete|remove|trash|share|post|publish"
    r"|upload|move|rename|archive|invite|reply|forward|comment|label|assign|merge|close"
    r"|run|execute)(_|$)",
    re.I,
)
READ_VERBS = re.compile(r"(^|_)(get|list|search|read|find|query|fetch|view)(_|$)", re.I)

# The agent whose shell is held to AUDITS, by its name in .claude/agents/.
AUDITOR = "security-reviewer"
# One `cd <dir> &&` in front is fine; anything else that chains, pipes,
# redirects or substitutes is refused.
CD_PREFIX = re.compile(r"^\s*cd\s+[^\s;&|`$<>()]+\s*&&\s*")
SHELL_MAGIC = re.compile(r"[;&|`$<>()\n\\]")
GIT_READS = {"log", "diff", "show", "ls-files", "blame", "status", "rev-parse", "shortlog"}
# Flags that make log or show print file contents, history's secrets included. Finding those is the
# secret scan's job, and it redacts what it finds.
PATCH_FLAGS = {"-p", "-u", "--patch", "--patch-with-stat", "--patch-with-raw", "--cc", "-c", "-m", "-W",
               "--function-context", "--full-diff", "--textconv", "--ext-diff"}
PATCH_PREFIXES = ("-U", "--unified", "--word-diff", "--color-words", "--output")
NO_PATCH = {"--stat", "--shortstat", "--numstat", "--name-only", "--name-status", "--no-patch", "-s", "--summary"}
# What a repo's own git config can make a read run: a filesystem monitor, a pager, an external or
# textconv diff, an ssh command, or another file pulled in. A clone never copies config, but a repo
# handed over as an archive brings its .git/config, and git reads it.
RISKY_GIT_CONFIG = re.compile(
    r"^\s*(fsmonitor|external|textconv|pager|sshcommand|askpass|command)\s*="
    r"|^\s*\[\s*(include|includeif|filter|pager)\b", re.I | re.M)


def git_dir_configs(start):
    """The config files git reads for the repo holding `start`, nearest repo first."""
    here = os.path.abspath(start)
    while True:
        dot = os.path.join(here, ".git")
        if os.path.isdir(dot):
            gitdir = dot
            break
        if os.path.isfile(dot):
            try:
                with open(dot) as handle:
                    line = handle.read().strip()
            except OSError:
                return []
            if not line.startswith("gitdir:"):
                return []
            gitdir = os.path.join(here, line[len("gitdir:"):].strip())
            break
        parent = os.path.dirname(here)
        if parent == here:
            return []
        here = parent
    found = [os.path.join(gitdir, "config"), os.path.join(gitdir, "config.worktree")]
    try:
        with open(os.path.join(gitdir, "commondir")) as handle:
            found.append(os.path.join(gitdir, handle.read().strip(), "config"))
    except OSError:
        pass
    return [f for f in found if os.path.isfile(f)]


def risky_git_config(start):
    """The config file that could make a git read run a command, or None."""
    for path in git_dir_configs(start):
        try:
            with open(path, errors="replace") as handle:
                if RISKY_GIT_CONFIG.search(handle.read()):
                    return path
        except OSError:
            return path
    return None


def git_read_allowed(args):
    """Whether git with these arguments, after any -C, is a read that prints no old file contents."""
    if not args or args[0] not in GIT_READS:
        return False
    sub, rest = args[0], args[1:]
    if any(a in PATCH_FLAGS or a.startswith(PATCH_PREFIXES) for a in rest):
        return False
    if sub == "show":
        # show prints a patch unless told not to, and rev:path prints a file as it was.
        return any(a in NO_PATCH for a in rest) and not any(":" in a for a in rest if not a.startswith("-"))
    return True


def audit_refusal(command, cwd=None):
    """Why the security reviewer may not run this command, or None when it may."""
    listed = ("The security reviewer's shell runs audits only: osv-scanner, npm audit, pip-audit (flags "
              "only, or --disable-pip), trivy fs or config, govulncheck, bundle-audit, bandit, gitleaks "
              "with a bare --redact, and git reads that print no old file contents (show needs --stat or "
              "--name-only). One command, no pipes. List anything else under Not checked for a person "
              "to run.")
    where = cwd or os.getcwd()
    moved = CD_PREFIX.match(command)
    if moved:
        where = os.path.join(where, os.path.expanduser(moved.group(0).strip()[2:].rstrip("&").strip()))
    command = CD_PREFIX.sub("", command, count=1)
    if SHELL_MAGIC.search(command):
        return listed
    try:
        words = shlex.split(command)
    except ValueError:
        return listed
    if not words:
        return listed
    tool, args = words[0], words[1:]
    first = args[0] if args else ""
    uses_git = False
    if tool == "git":
        if args[:1] == ["-C"] and len(args) > 2:
            where = os.path.join(where, os.path.expanduser(args[1]))
            args = args[2:]
        if not git_read_allowed(args):
            return listed
        uses_git = True
    elif tool == "gitleaks":
        # A bare --redact is 100%. --redact=N shows the rest of each secret.
        if first not in ("detect", "git", "dir", "protect") or not any(a in ("--redact", "--redact=100") for a in args):
            return listed
        if first != "dir" and "--no-git" not in args:
            uses_git = True
            for flag in ("--source", "-s"):
                if flag in args and args.index(flag) + 1 < len(args):
                    where = os.path.join(where, os.path.expanduser(args[args.index(flag) + 1]))
            paths = [a for a in args[1:] if not a.startswith("-")]
            if first == "git" and paths:
                where = os.path.join(where, os.path.expanduser(paths[-1]))
    elif not audit_tool_allowed(tool, args):
        return listed
    if uses_git:
        risky = risky_git_config(where)
        if risky:
            return ("{} sets something that makes git run a command on a read (a pager, an external "
                    "diff, a filesystem monitor, an include). Don't run git here; list it under Not "
                    "checked and say why.".format(risky))
    return None


def audit_tool_allowed(tool, args):
    """Whether a non-git audit tool with these arguments reads without installing or running the code."""
    first = args[0] if args else ""
    # Only tools that read a lock file or the code without running it. yarn and pnpm are left
    # out because a checkout can carry plugins or hooks they run, and osv-scanner reads their
    # lock files anyway, as it does Cargo, Go, Ruby and uv ones.
    if tool == "npm":
        return first == "audit" and "fix" not in args
    if tool == "pip-audit":
        # Given a requirements file or a project, pip-audit installs the packages to resolve
        # them, and an install can run their code. --disable-pip reads the file as it is; with
        # flags only, it audits the environment it's run in.
        installs = any(a in ("-r", "--requirement") or a.startswith(("--requirement=", "-r"))
                       or not a.startswith("-") for a in args)
        return "--fix" not in args and (not installs or "--disable-pip" in args)
    if tool == "osv-scanner":
        return first != "fix"
    if tool == "trivy":
        return first in ("fs", "filesystem", "config")
    if tool in ("govulncheck", "bandit", "bundle-audit", "bundler-audit"):
        return True
    return False


HEADLESS_READS = {("pr", "view"), ("pr", "diff"), ("issue", "view")}
# The reasons a headless refusal gives. usage_log.py compares against these, so its rule is exact.
HEADLESS_SHELL = ("A headless run's shell reads a pull request or issue by number and nothing else: "
                  "gh pr view <n>, gh pr diff <n> or gh issue view <n>, with --comments on a view. "
                  "Say in the report that you couldn't run anything else.")
HEADLESS_CONNECTOR = ("A headless run uses no connector: nobody is there to say what it may read or "
                      "send. Run it in a session instead.")
HEADLESS_UNCHECKED = "A headless run's tool call couldn't be checked, so it's refused."
UNATTENDED_UNCHECKED = "A loop agent's tool call couldn't be checked, so it's refused: nobody is there to read a warning."


def headless_refusal(command):
    """Why a headless run may not run this command, or None when it's an exact read by number.

    Only the issue or pull request number may follow, and --comments on a view: -R, a URL, --web,
    --jq and --template each let the command choose a host, open a browser or read the environment.
    """
    listed = HEADLESS_SHELL
    if SHELL_MAGIC.search(command):
        return listed
    try:
        words = shlex.split(command)
    except ValueError:
        return listed
    if len(words) < 4 or words[0] != "gh" or tuple(words[1:3]) not in HEADLESS_READS:
        return listed
    rest = words[4:]
    if not re.fullmatch(r"[0-9]+", words[3]) or rest not in ([], ["--comments"]):
        return listed
    if rest and words[2] != "view":
        return listed
    return None


# The harness root, two folders up from this file, whatever folder the session reports.
ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
HEADLESS_OUTSIDE = ("A headless run reads, searches and lists files inside the harness root and nowhere "
                    "else. Say in the report what you couldn't read.")
FILE_TOOLS = ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit")
# Every tool decide() has a rule for. tests/ holds .claude/settings.json's matcher to this list.
CHECKED_TOOLS = FILE_TOOLS + ("Grep", "Glob", "Bash")
GLOB_MAGIC = re.compile(r"[*?\[{]")
BRACES = re.compile(r"\{([^{}]*)\}")
ESCAPE = re.compile(r"\\(.)")
NEGATED_CLASS = re.compile(r"\[\^")
# More {a,b} alternatives than this and the guard refuses rather than check some of them.
MAX_ALTERNATIVES = 64
# A folder that holds credentials and little else, so searching it reads them.
CREDENTIAL_DIR = re.compile(r"(^|/)(\.ssh|\.aws|\.gnupg|\.kube)$")
# Names only a credential file has, and names any project has. A glob that matches one of the
# first and none of the second can only be after credentials: .en?, id_*, .e[n]v.
CREDENTIAL_NAMES = (".env", ".env.local", ".env.production", "server.pem", "server.key", "id_rsa",
                    "id_ed25519", "id_ecdsa", ".netrc", ".npmrc", ".pypirc", ".ssh/config", ".aws/credentials",
                    "store.p12", "cert.pfx", "keystore.jks", "release.keystore", ".kube/config",
                    "service-account.json", ".htpasswd", ".docker/config.json", ".gnupg/pubring.kbx")
ORDINARY_NAMES = ("readme.md", "app.py", "index.ts", "main.go", "package.json", "tsconfig.json", "config.json",
                  "notes.txt", "keys.py", "env.py", "config.yaml", "makefile")
# Inside the root, what a headless run doesn't reach: a token in the local settings' env block or
# in a remote URL in git's config, and the company's own record and exports.
PRIVATE_FILES = (".claude/settings.local.json",)
PRIVATE_FOLDERS = ("company", "local-data", ".inbox", "factories")
# Every list below that names the private folders is built from PRIVATE_FOLDERS, so a folder added there
# reaches the search exclude, the glob checks and the refusal at once.
# What a headless glob must not match. A ripgrep glob that matches an ignored or hidden folder or
# file brings it back into the search ({company,*.md} lists company/, measured 2026-10-25), and
# ripgrep tests a glob without a / against each name and one with a / against each path.
# company/** alone didn't get in when measured; a path below each folder refuses it anyway.
PRIVATE_ENTRIES = (".claude", ".git", ".claude/settings.local.json", ".git/config") + tuple(
    entry for folder in PRIVATE_FOLDERS for entry in (folder, folder + "/x"))
# Added to every headless Grep's glob: ripgrep leaves out a bare repo at any depth. ripgrep's
# globs match case, and the Mac's disk doesn't, so Lib.GIT counts (measured 2026-10-26).
EXCLUDE_BARE_REPOS = "!*.[gG][iI][tT]"
# Also added: the private folders at the root. .ignore lets company/ back into a search, so an ordinary
# session can read it, and a headless Grep over the root would search it too (ripgrep 15.2.0 with Claude
# Code's flags, measured 2026-11-07). The leading / anchors each to the root.
EXCLUDE_PRIVATE = "!/{" + ",".join(PRIVATE_FOLDERS) + "}"
# The names a headless Glob pattern may not carry in a later part: the private places themselves.
PRIVATE_NAMES = set(PRIVATE_FOLDERS) | {".claude", ".git", "settings.local.json"}
HEADLESS_PRIVATE = ("A headless run doesn't read the files inside the root that hold tokens or company "
                    "data: .claude/settings.local.json, any .git folder or bare repo, "
                    + ", ".join(folder + "/" for folder in PRIVATE_FOLDERS[:-1])
                    + " and " + PRIVATE_FOLDERS[-1] + "/. Say in "
                    "the report what you couldn't read.")
# ripgrep's file types that take in a credential name: sh lists .env and *.env (rg --type-list, 2026-10-25).
CREDENTIAL_TYPES = {"sh"}


def alternatives(glob):
    """Each glob a {a,b} pattern spells out, or None when there are more than the guard checks."""
    pending, spelled = [glob], []
    while pending:
        if len(pending) + len(spelled) > MAX_ALTERNATIVES:
            return None
        one = pending.pop()
        brace = BRACES.search(one)
        if brace:
            pending += [one[:brace.start()] + part + one[brace.end():] for part in brace.group(1).split(",")]
        else:
            spelled.append(one)
    return spelled


def path_names_credential(path, cwd):
    """Whether a path names a credential file or a folder of them, as written or once resolved.

    Resolved means ~, // and .. collapsed and links followed, so docs/setup.md linked to ../.env
    counts. Case is ignored, as the Mac's disk ignores it: .ENV opens .env.
    """
    plain = os.path.expanduser(path)
    forms = (path, os.path.normpath(plain), os.path.realpath(os.path.join(cwd, plain)))
    return any(CREDENTIAL.search(" " + form.lower()) or CREDENTIAL_DIR.search(form.lower()) for form in forms)


def glob_matches(glob, names):
    """Whether a glob matches any of these names, at the top of a tree or below it."""
    return any(fnmatch.fnmatchcase(name, glob) or fnmatch.fnmatchcase("sub/" + name, glob) for name in names)


def glob_pieces(glob):
    """The globs a Grep glob comes to, ready for fnmatch, or None when there are more than the guard checks.

    Each {a,b} alternative, split on commas or spaces, with \\ escapes undone and lowercased. ripgrep
    reads [^x] as any character but x and fnmatch reads it as ^ or x, so it's written [!x], which
    both read the same way (.en[^_] matches .env in ripgrep, measured 2026-10-25).
    """
    spelled = alternatives(glob)
    if spelled is None:
        return None
    return [NEGATED_CLASS.sub("[!", piece) for one in spelled
            for piece in re.split(r"[\s,]+", ESCAPE.sub(r"\1", one).lower()) if piece]


def glob_names_credential(glob):
    """Whether a Grep glob names a credential file, or can only match credential files."""
    pieces = glob_pieces(glob)
    if pieces is None:
        return True
    return any(CREDENTIAL.search(" " + re.sub(r"[*?]", "", piece))
               or glob_matches(piece, CREDENTIAL_NAMES) and not glob_matches(piece, ORDINARY_NAMES)
               for piece in pieces)


def glob_reaches(glob, names):
    """Whether a Grep glob can match any of these names at all, however much else it matches."""
    pieces = glob_pieces(glob)
    return pieces is None or any(glob_matches(piece, names) for piece in pieces)


def bare_repos():
    """The bare repos at the root and one folder into each project, as paths from the root, lowercased.

    A glob that names one brings it back into a search (a glob matching an ignored folder's name
    does), so the glob check tests against the real names, not only a stand-in, and mirror.gi? is
    caught as well as mirror.git. A headless Grep also gets !*.git, which leaves out every bare repo
    at any depth; this is what still holds if that rewrite ever stops applying.
    """
    found = []
    projects = os.path.join(ROOT, "projects")
    for folder in [ROOT, projects] + sorted(os.path.join(projects, name) for name in listing(projects)):
        for name in listing(folder):
            if name.lower().endswith(".git") and name != ".git" and os.path.isdir(os.path.join(folder, name)):
                found.append(os.path.relpath(os.path.join(folder, name), ROOT).lower())
    return found


def listing(folder):
    """A folder's names, or none when it can't be read."""
    try:
        return os.listdir(folder)
    except OSError:
        return []


def glob_unlocks_private(glob):
    """Whether a glob matches one of the root's private folders or files, as ripgrep would test it."""
    pieces = glob_pieces(glob)
    if pieces is None:
        return True
    repos = ["x.git"] + bare_repos()
    entries = PRIVATE_ENTRIES + tuple(repos) + tuple(repo + "/config" for repo in repos)
    for piece in pieces:
        piece = piece.lstrip("!/").rstrip("/")
        if not piece:
            continue
        if any(part.endswith(".git") for part in piece.split("/")):
            return True  # names a bare repo outright, wherever it sits
        if "/" in piece:
            targets = entries + tuple("sub/" + entry for entry in entries)
        else:
            targets = tuple(entry.rsplit("/", 1)[-1] for entry in entries)
        if any(fnmatch.fnmatchcase(target, piece) for target in targets):
            return True
    return False


def resolved(path, cwd):
    """A path read from cwd, with ~, .. and links resolved."""
    return os.path.realpath(os.path.join(cwd, os.path.expanduser(path)))


def outside_root(path, cwd):
    """Whether a path, read from cwd with ~, .. and links resolved, lands outside the harness root."""
    full = resolved(path, cwd)
    return full != ROOT and not full.startswith(ROOT + os.sep)


def private_path(full):
    """Whether a resolved path is, or is inside, a place in the root a headless run doesn't reach."""
    if not full.startswith(ROOT + os.sep):
        return False
    parts = os.path.relpath(full, ROOT).lower().split(os.sep)
    # A bare repo, or a --separate-git-dir clone, keeps git's config in a folder like mirror.git/.
    return "/".join(parts) in PRIVATE_FILES or parts[0] in PRIVATE_FOLDERS or any(
        part.endswith(".git") for part in parts)


def glob_prefixes(pattern, base):
    """For each {a,b} alternative of a Glob pattern, \\ escapes undone, the folder its fixed parts name
    and the parts after them. None when there are more alternatives than the guard checks.

    The pattern can carry the folder itself: ../other/** or /etc/*. Its parts up to the first
    wildcard are a path, and a .. after a wildcard climbs from wherever that matched.
    """
    spelled = alternatives(pattern)
    if spelled is None:
        return None
    found = []
    for one in spelled:
        parts = ESCAPE.sub(r"\1", one).split("/")
        fixed = []
        for part in parts:
            if GLOB_MAGIC.search(part):
                break
            fixed.append(part)
        found.append((os.path.join(base, "/".join(fixed)), parts[len(fixed):]))
    return found


def glob_outside(pattern, base, cwd):
    """Whether a Glob pattern climbs out of the root."""
    prefixes = glob_prefixes(pattern, base)
    return prefixes is None or any(".." in rest or outside_root(folder, cwd) for folder, rest in prefixes)


def headless_outside(tool, data, cwd):
    """Whether a headless file tool's call reaches outside the harness root."""
    if tool == "Glob":
        base = data.get("path") or ""
        return outside_root(base, cwd) or glob_outside(data.get("pattern") or "", base, cwd)
    if tool == "Grep":
        return outside_root(data.get("path") or "", cwd)
    return outside_root(data.get("file_path") or data.get("notebook_path") or "", cwd)


def headless_private(tool, data, cwd):
    """Whether a headless file tool's call reaches a place in the root that holds tokens or company data.

    A Grep over the root leaves them out: headless_rewrite adds them to its glob as excludes, since .ignore
    lets company/ back in, and Claude Code's Grep passes --glob '!.git' (with --hidden, so
    hidden protects nothing; Claude Code 2.1.310, measured 2026-10-25). So the guard checks the path it
    names, and refuses a glob that would bring one back in. Glob
    lists names and reads nothing, so a pattern is refused when the folder its fixed parts name is
    private, or a later part names a private folder or file outright (**/company/*); c*/** can
    still list the names under company/.
    """
    if tool == "Glob":
        base = data.get("path") or ""
        prefixes = glob_prefixes(data.get("pattern") or "", base)
        return prefixes is None or private_path(resolved(base, cwd)) or any(
            private_path(resolved(folder, cwd)) or PRIVATE_NAMES & {part.lower() for part in rest}
            for folder, rest in prefixes)
    if tool == "Grep":
        glob = data.get("glob") or ""
        return private_path(resolved(data.get("path") or "", cwd)) or bool(glob) and glob_unlocks_private(glob)
    return private_path(resolved(data.get("file_path") or data.get("notebook_path") or "", cwd))


def is_headless():
    """A run bin/factory started. Either name counts, so the stricter reading always wins: the old name
    stays honoured, since it only ever makes the guard stricter. Kept here, not imported, so the guard stands alone."""
    return os.environ.get("SANVIO_HEADLESS") == "1" or os.environ.get("HARNESS_HEADLESS") == "1"


def is_unattended():
    """An agent scripts/loop.py started (SANVIO_UNATTENDED=1). Nobody reads a warning in its session, so a call
    this hook can't check is refused there. Nothing else changes: the agent still has to edit and run tests."""
    return os.environ.get("SANVIO_UNATTENDED") == "1"


def decide(event):
    """(decision, reason) for one tool call, or None to let it through untouched."""
    tool = event.get("tool_name", "")
    data = event.get("tool_input") or {}
    headless = is_headless()
    cwd = event.get("cwd") or os.getcwd()

    if tool in FILE_TOOLS or tool == "Grep":
        if tool == "Grep":
            path, glob = data.get("path") or "", data.get("glob") or ""
        else:
            path, glob = data.get("file_path") or data.get("notebook_path") or "", ""
        named = ""
        if path and path_names_credential(path, cwd):
            named = path
        elif glob and glob_names_credential(glob):
            named = glob
        if named:
            return ("deny", "{} looks like a credential file. Agents never read or write those. "
                    "Reference the secret by name and let the runtime load it.".format(named))
        # Ordinary sessions keep broad globs (*env*) and type sh for shell scripts; a headless run has
        # nobody to notice what else they took in, so there any glob that can match a credential is refused.
        if headless and tool == "Grep":
            if glob and glob_reaches(glob, CREDENTIAL_NAMES):
                return ("deny", "{} can match a credential file, and a headless run searches none. Name the "
                        "files more narrowly, or leave the glob out.".format(glob))
            types = data.get("type") or []
            for kind in types if isinstance(types, list) else [types]:
                if str(kind).lower() in CREDENTIAL_TYPES:
                    return ("deny", "ripgrep's {} type takes in credential files. Name the files with a glob "
                            "instead.".format(kind))

    if tool in FILE_TOOLS and tool != "Read":
        path = data.get("file_path") or data.get("notebook_path") or ""
        if path and LOG_FILE.search(os.path.normpath(path).replace(os.sep, "/")):
            return ("deny", LOGS_ARE_READ_ONLY.format(path))

    if headless and (tool in FILE_TOOLS or tool in ("Grep", "Glob")):
        if headless_outside(tool, data, cwd):
            return ("deny", HEADLESS_OUTSIDE)
        if headless_private(tool, data, cwd):
            return ("deny", HEADLESS_PRIVATE)

    if tool == "Bash":
        command = data.get("command", "")
        named = EXISTENCE_CHECK.sub(" ", command)
        if CREDENTIAL.search(" " + named.lower()) or SECRET_COMMANDS.search(command):
            return ("deny", "That command reads a credential or prints secrets. Agents never do "
                    "that. Check the secret exists without showing its value, or ask a human.")
        written = log_write(command)
        if written:
            return ("deny", LOGS_ARE_READ_ONLY.format(written))
        # Before the auditor's list: a headless run is held to its reads whichever agent asks.
        if headless:
            why = headless_refusal(command)
            if why:
                return ("deny", why)
        if event.get("agent_type") == AUDITOR:
            why = audit_refusal(command, event.get("cwd"))
            if why:
                return ("deny", why)
            return ("allow", "a read-only audit on the security reviewer's list")

    if tool.startswith("mcp__"):
        if headless:
            return ("deny", HEADLESS_CONNECTOR)
        # create_draft, notion-create-pages and createIssue all read as create_...
        action = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", tool.split("__")[-1]).replace("-", "_")
        if WRITE_VERBS.search(action) or not READ_VERBS.search(action):
            return ("ask", "{} isn't named as a plain read, so it may change something outside "
                    "this repo. A human says yes to each one.".format(tool))

    return None


def headless_rewrite(event):
    """The input a headless Grep the guard let through goes on with, or None to leave it as it is.

    Claude Code's Grep leaves out folders named exactly .git, and ripgrep stops applying the root's
    .gitignore at a project's own repo, so a bare repo deeper inside a project (vendor/lib.git) would
    be searched. A trailing !*.git wins over any glob before it, and Claude Code passes each
    space-separated part as its own --glob (Claude Code 2.1.310 and ripgrep 15.2.0, measured
    2026-10-26), so every headless search gets one. decide() still refuses a glob that names a bare
    repo, in case the rewrite ever stops applying.
    """
    if not is_headless() or event.get("tool_name") != "Grep":
        return None
    data = event.get("tool_input") or {}
    return dict(data, glob=" ".join(part for part in (data.get("glob") or "", EXCLUDE_PRIVATE, EXCLUDE_BARE_REPOS)
                                    if part))


def main():
    headless = is_headless()
    try:
        event = json.load(sys.stdin)
        verdict = decide(event)
        if verdict is None and headless_rewrite(event) is not None:
            verdict = ("update", headless_rewrite(event))
    except Exception:
        if not headless and not is_unattended():
            # Unreadable input, or a bug here: let the call through and say so, rather than block every
            # tool, and leave the traceback on stderr so a guard bug doesn't fail quietly.
            traceback.print_exc()
            print(json.dumps({"systemMessage": "[guard] couldn't check the tool call, so it wasn't checked"}))
            return 0
        # Nobody is watching a headless run or a loop agent, so a call the guard couldn't check doesn't run.
        verdict = ("deny", HEADLESS_UNCHECKED if headless else UNATTENDED_UNCHECKED)
    if verdict and verdict[0] == "update":
        # No decision with it: the call goes on to the usual permission check, with this input.
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": verdict[1]}}))
    elif verdict:
        decision, reason = verdict
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
