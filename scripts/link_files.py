#!/usr/bin/env python3
"""Turn file names in this repo's Markdown into links to those files.

    python3 scripts/link_files.py           # link every `path` that names a tracked file or folder
    python3 scripts/link_files.py --check   # change nothing, exit 1 if anything would change

A name in backticks becomes a link when it resolves to something git tracks, from
the file's own folder first and then the repo root. Code blocks, headings,
frontmatter, existing links and symlinked files are left alone, and so is a
generic mention like "a project's own `AGENTS.md`", which means some other
project's file. A gitignored file, such as `company/COMPANY.md`, stays plain
because the link would be broken for everyone else. So does an eval suite's
issue, a Markdown file in an `issues/` folder beside a `suite.json`: it's posted
as an issue in the run's own repo, where a link into this one would break. Safe
to run twice.
"""
import argparse
import os
import re
import subprocess
import sys

LINK = re.compile(r"!?\[[^\]\n]*\]\([^)\n]*\)")
SPAN = re.compile(r"`([^`\n]+)`")
PATHY = re.compile(r"^[A-Za-z0-9_.\-/]+$")
# "a project's own `AGENTS.md`", "read its `README.md`": a file of that name somewhere else.
GENERIC = re.compile(r"(project's( own)?|its( own)?|their own)\s+(`[^`]+`\s+or\s+)?$")


def resolve(md, ref, files, dirs):
    """The link target for `ref` written in `md`, or None when it isn't a tracked path."""
    if not PATHY.match(ref) or ref.startswith(("/", "-", "..")):
        return None
    if os.path.normpath(ref) == ".":  # `.` or `./` means "this folder", never a link
        return None
    # A bare word with no dot or slash links only to a file of that name, like LICENSE:
    # `tests` or `skills` in a sentence is usually the idea, not the folder.
    bare = "/" not in ref and "." not in ref
    for base in (os.path.dirname(md), ""):
        cand = os.path.normpath(os.path.join(base, ref.rstrip("/")))
        if cand in files or (cand in dirs and not bare):
            if cand == md:
                return None
            rel = os.path.relpath(cand, os.path.dirname(md) or ".")
            return rel + ("/" if cand in dirs and ref.endswith("/") else "")
    return None


def link_text(md, text, files, dirs):
    """`text` with its file names linked, and how many it linked."""
    lines = text.split("\n")
    out, fence, front, count = [], None, lines[:1] == ["---"], 0
    for i, line in enumerate(lines):
        if front:
            out.append(line)
            front = not (i > 0 and line == "---")
            continue
        marker = line.lstrip()[:3]
        if marker in ("```", "~~~"):
            # A block closes only on the marker that opened it: ``` inside ~~~ is code.
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            out.append(line)
            continue
        if fence or line.startswith("#"):
            out.append(line)
            continue
        masked = [(m.start(), m.end()) for m in LINK.finditer(line)]
        prev = lines[i - 1] if i else ""
        pieces, last = [], 0
        for m in SPAN.finditer(line):
            ref = m.group(1)
            if any(a <= m.start() < b for a, b in masked):
                continue
            if "/" not in ref and GENERIC.search((prev + " " + line[:m.start()])[-60:]):
                continue
            target = resolve(md, ref, files, dirs)
            if target:
                pieces += [line[last:m.start()], "[`{}`]({})".format(ref, target)]
                last = m.end()
                count += 1
        out.append("".join(pieces) + line[last:])
    return "\n".join(out), count


def tracked(root):
    files = set(subprocess.run(["git", "-C", root, "ls-files"], capture_output=True, text=True,
                               check=True).stdout.split())
    dirs = set()
    for f in files:
        d = os.path.dirname(f)
        while d:
            dirs.add(d)
            d = os.path.dirname(d)
    return files, dirs


def suite_issue(md, files):
    """True for an eval suite's issue: its body is posted in another repo, so it stays as written."""
    folder = os.path.dirname(md)
    return os.path.basename(folder) == "issues" and os.path.join(os.path.dirname(folder), "suite.json") in files


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="change nothing, exit 1 if anything would change")
    check = parser.parse_args(argv).check
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files, dirs = tracked(root)
    total = 0
    for md in sorted(f for f in files if f.endswith(".md") and not suite_issue(f, files)):
        path = os.path.join(root, md)
        if os.path.islink(path):
            continue
        with open(path) as f:
            text = f.read()
        new, count = link_text(md, text, files, dirs)
        if count:
            total += count
            print("{:4d}  {}".format(count, md))
            if not check:
                with open(path, "w") as f:
                    f.write(new)
    print("{} file name{} {}".format(total, "" if total == 1 else "s", "to link" if check else "linked"))
    return 1 if check and total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
