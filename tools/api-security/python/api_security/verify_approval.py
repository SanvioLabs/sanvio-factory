"""Signed approval for the guarded surface, SPEC-034 REQ-016, SEC-002, SEC-004.

    python3 verify_approval.py --base <base sha> --head <head sha> [--repo DIR]
                               [--author <PR author login> --sender <event sender login>]

Run by `security-approval.yml` on `pull_request_target`, from the BASE branch's copy of this file,
over the pull request's commits as git objects. It never checks out or executes anything from the
pull request.

The guarded surface is everything under `security/` and `.github/workflows/`. Every workflow is
guarded because a required status matches by name, and no reading of a workflow's text can tell
what name a job will report under: it can take it from the pull request's own title. One change
needs no signature: a pull request Dependabot opened, with every push to it Dependabot's own, that
moves only the `@ref` of existing `uses:` lines in a workflow that is neither a security workflow,
nor one the base's `security/config.json` lists under `deploy_workflows`, nor a reusable workflow
(`workflow_call`). Content alone cannot be the test: a commit that exists only in a fork resolves
through the parent's path, so the same action path is not the same publisher. A malformed
`deploy_workflows` list counts every workflow as a deploy workflow. The verifier judges
what would land: the three-way merge of the head into the base, the tree GitHub merges. A pull
request that changes a guarded file in that tree passes only when one commit in the pull
request, built on top of this base and signed with an SSH key listed in the base's
`security/allowed_signers`, holds exactly what lands across the whole guarded surface. A signed
change lands whole or not at all. Removing lines from `security/public-routes.txt` is the one
change that needs no signature.

A signed commit that does not contain the base it is judged against does not count: an old signed
commit could otherwise be replayed over a later fix. So after updating a branch from its base, sign
the update.

Exit 0 pass, 1 refused, 2 could not decide. 2 is a refusal too: the job fails closed.
Stdlib only, no imports from the package, so the base branch's copy runs on its own.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Set

SIGNERS = "security/allowed_signers"
SNAPSHOT = "security/public-routes.txt"
CONFIG = "security/config.json"
WORKFLOWS_DIR = ".github/workflows/"
SECURITY_WORKFLOWS = (".github/workflows/security-check.yml", ".github/workflows/security-approval.yml")
BARE = ("security", ".github", ".github/workflows")  # replacing one of these replaces what is under it
USES = re.compile(r"^(\s*-?\s*uses:\s*)([^@\s'\"]+)@([A-Za-z0-9._/-]+)(\s+#.*)?$")
DEPENDABOT = "dependabot[bot]"
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\x85\u2028\u2029]")
DEPLOY_ENTRY = re.compile(r"^\.github/workflows/[^/]+\.ya?ml$")
SSH_SIGNATURE = "-----BEGIN SSH SIGNATURE-----"


class Undecided(Exception):
    pass


def git(repo: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    # surrogateescape: a path that is not UTF-8 decodes losslessly and goes back to git intact.
    res = subprocess.run(["git", "-C", repo, *args], capture_output=True,
                         encoding="utf-8", errors="surrogateescape")
    if check and res.returncode != 0:
        raise Undecided(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res


def entry(repo: str, treeish: str, path: str) -> Optional[str]:
    """Mode, type and object id of `path` in `treeish`, or None when it does not exist there."""
    out = git(repo, "ls-tree", "-z", "--full-tree", treeish, "--", path).stdout
    for item in out.split("\0"):
        meta, _, name = item.partition("\t")
        if name == path:
            return meta
    return None


def content(repo: str, treeish: str, path: str) -> str:
    """Text of a regular file; empty when it does not exist. Anything else cannot be read as
    routes, and is an error rather than an empty file."""
    meta = entry(repo, treeish, path)
    if meta is None:
        return ""
    mode, kind, oid = meta.split()
    if mode != "100644" or kind != "blob":
        raise Undecided(f"{path} is not a regular file at {treeish[:12]} (mode {mode})")
    return git(repo, "cat-file", "blob", oid).stdout


def show(text: str) -> str:
    """Printable form of a path that may hold undecodable bytes."""
    return text.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")


def surface(repo: str, treeish: str, skip: Set[str]) -> Dict[str, str]:
    """Every guarded file in `treeish` with its mode, type and object id, less `skip`."""
    out = git(repo, "ls-tree", "-r", "-z", "--full-tree", treeish, "--", "security", ".github").stdout
    found = {}
    for item in out.split("\0"):
        meta, _, name = item.partition("\t")
        if name and guarded(name) and name not in skip:
            found[name] = meta
    return found


def guarded(path: str) -> bool:
    return path.startswith(("security/", WORKFLOWS_DIR)) or path in BARE


def routes(text: str) -> Set[str]:
    lines = (line.strip() for line in text.splitlines())
    return {line for line in lines if line and not line.startswith("#")}


def landed_tree(repo: str, base: str, head: str) -> Optional[str]:
    """The tree a merge of `head` into `base` produces, or None on a conflict."""
    res = git(repo, "merge-tree", "--write-tree", "--no-messages", base, head, check=False)
    if res.returncode == 1:
        return None
    if res.returncode != 0:  # an old git without --write-tree included: fail closed
        raise Undecided(f"git merge-tree failed ({res.returncode}): {res.stderr.strip()}")
    return res.stdout.split("\n", 1)[0].strip()


def changed_guarded(repo: str, base: str, tree: str) -> List[str]:
    out = git(repo, "diff", "-z", "--name-only", "--no-renames", base, tree).stdout
    return sorted(p for p in out.split("\0") if p and guarded(p))


def deploy_workflows(repo: str, base: str) -> Optional[Set[str]]:
    """The deploy workflows the base lists, read from the base so a PR cannot unlist its own. None
    when the list is not a list of `.github/workflows/<file>.yml` paths: every workflow is then
    treated as a deploy workflow, which widens the guard and still lets a signed fix land."""
    text = content(repo, base, CONFIG)
    if not text.strip():
        return set()
    try:
        listed = json.loads(text).get("deploy_workflows", [])
    except (ValueError, AttributeError):
        return None
    if not isinstance(listed, list) or not all(isinstance(w, str) and DEPLOY_ENTRY.match(w) for w in listed):
        return None
    return set(listed)


def ref_bump_only(repo: str, base: str, tree: str, path: str) -> bool:
    """True when `path` differs between base and tree only in the @ref (and its trailing comment)
    of `uses:` lines that keep the same action."""
    before, after = entry(repo, base, path), entry(repo, tree, path)
    if before is None or after is None or not before.startswith("100644 blob ") \
            or not after.startswith("100644 blob "):
        return False
    before_text, after_text = content(repo, base, path), content(repo, tree, path)
    if CONTROL.search(after_text) or re.search(r"^\s*workflow_call\s*:|[{,\s]workflow_call\b",
                                                before_text + "\n" + after_text, re.M):
        return False
    old, new = before_text.split("\n"), after_text.split("\n")
    if len(old) != len(new):
        return False
    for x, y in zip(old, new):
        if x == y:
            continue
        mx, my = USES.match(x), USES.match(y)
        if not (mx and my and mx.group(1) == my.group(1) and mx.group(2) == my.group(2)):
            return False
    return True


def exempt_bumps(repo: str, base: str, tree: str, files: List[str], dependabot: bool) -> Set[str]:
    """Dependabot's ref bumps to ordinary workflows, which need no signature."""
    deploy = deploy_workflows(repo, base)
    if not dependabot or deploy is None:
        return set()
    return {p for p in files if p.startswith(WORKFLOWS_DIR) and p not in SECURITY_WORKFLOWS
            and p not in deploy and ref_bump_only(repo, base, tree, p)}


def needs_signature(repo: str, base: str, tree: str, files: List[str]) -> List[str]:
    """The changed guarded files a signature must cover. A snapshot that stays a regular file and
    only loses routes (comments and blank lines aside) is exempt."""
    out = []
    for path in files:
        if path == SNAPSHOT and (entry(repo, tree, path) or "").startswith("100644 blob "):
            if not (routes(content(repo, tree, path)) - routes(content(repo, base, path))):
                continue
        out.append(path)
    return out


def signed_by_trusted(repo: str, commit: str, signers_file: str) -> bool:
    raw = git(repo, "cat-file", "commit", commit).stdout
    if SSH_SIGNATURE not in raw:
        return False  # unsigned, or an OpenPGP signature: only the listed SSH keys count
    res = git(repo, "-c", "gpg.format=ssh", "-c", f"gpg.ssh.allowedSignersFile={signers_file}",
              "verify-commit", commit, check=False)
    return res.returncode == 0


def contains(repo: str, ancestor: str, commit: str) -> bool:
    res = git(repo, "merge-base", "--is-ancestor", ancestor, commit, check=False)
    if res.returncode not in (0, 1):
        raise Undecided(f"git merge-base --is-ancestor failed: {res.stderr.strip()}")
    return res.returncode == 0


def decide(repo: str, base: str, head: str, author: str = "", sender: str = "") -> List[str]:
    """Reasons to refuse; empty means pass."""
    for ref in (base, head):
        git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    git(repo, "merge-base", base, head)  # unrelated histories: could not decide
    at = f"head {head[:12]} into base {base[:12]}"
    tree = landed_tree(repo, base, head)
    if tree is None:
        return [f"{at}: the pull request conflicts with its base, so what would land is unknown. "
                "Update the branch from its base, and sign the update if it touches a guarded file"]
    changed = changed_guarded(repo, base, tree)
    exempt = exempt_bumps(repo, base, tree, changed, author == DEPENDABOT and sender == DEPENDABOT)
    covered = needs_signature(repo, base, tree, [p for p in changed if p not in exempt])
    if not covered:
        return []

    signers = content(repo, base, SIGNERS)
    if not routes(signers):
        return [
            f"{at}: {', '.join(show(p) for p in covered)} changed, and the base has no {SIGNERS} to "
            f"approve it. Land {SIGNERS} on the base branch before security-approval becomes a "
            "required check (api-security.md, enforced)"]

    # A signature covers the guarded surface as a whole: one signed commit must hold exactly what
    # lands, so part of a signed change, or parts of two, cannot land on their own. The snapshot is
    # left out only when it needs no signature, so an unsigned route removal still passes.
    skip = set(exempt) | (set() if SNAPSHOT in covered else {SNAPSHOT})
    wanted = surface(repo, tree, skip)
    commits = git(repo, "rev-list", head, f"^{base}").stdout.split()
    signed = on_base = False
    with tempfile.TemporaryDirectory() as tmp:
        signers_file = os.path.join(tmp, "allowed_signers")
        with open(signers_file, "w", encoding="utf-8") as fh:
            fh.write(signers)
        for commit in commits:  # newest first
            if not signed_by_trusted(repo, commit, signers_file):
                continue
            signed = True
            if not contains(repo, base, commit):
                continue
            on_base = True
            if surface(repo, commit, skip) == wanted:
                return []
    if not signed:
        why = ("no commit in the pull request is signed by a key in the base's allowed_signers "
               "(unsigned, an OpenPGP signature, or a key or committer email that is not listed)")
    elif not on_base:
        why = ("the signed commit is built on an older base. Update the branch from its base and sign "
               "the update (`git commit --amend -S` on the merge), then push")
    else:
        why = ("what lands under the guarded paths differs from every signed commit on this base: a later "
               "commit changed a guarded file, or only part of a signed change is landing. Sign the latest")
    return [f"{show(p)}: changed ({at}); {why}" for p in covered]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="verify_approval")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--author", default="", help="the pull request's author login")
    ap.add_argument("--sender", default="", help="the login whose action fired this run")
    args = ap.parse_args(argv)
    try:
        reasons = decide(args.repo, args.base, args.head, args.author, args.sender)
    except Exception as exc:  # fail closed: could not decide is a refusal
        print(f"security approval could not decide: {type(exc).__name__}: {exc}")
        return 2
    for r in reasons:
        print(f"REFUSED {show(r)}")
    print("security approval: " + ("passed" if not reasons else "refused"))
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
