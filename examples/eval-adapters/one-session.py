#!/usr/bin/env python3
"""Start one plain Claude Code session on one issue of an eval run, then open its pull request.

It's the smallest factory there is: no rules, no review, no retries. Run a suite through it to get a
baseline, then run the same suite through your own factory and compare the two. Copy it as the start
of an adapter for a factory that doesn't open its own pull requests.

Usage, as scripts/eval_factory.py's --start:
    python3 examples/eval-adapters/one-session.py {issue} {clone} {repo}

EVAL_CLAUDE   the claude command to run, by default "claude". Point it at a wrapper to use a local model
EVAL_MODEL    the model, by default "sonnet"

What it does for each issue: puts the clone on origin/main, gives one `claude -p` session the issue's
title and body under a one-line instruction, then commits whatever changed onto eval/issue-N, pushes
that branch and opens the pull request, with the session's last reply as its body. The session can
read, edit and run python3, but it can't push or call gh: the adapter does both after it finishes.
Exits 0 once the pull request is open, and 1 when the session changed nothing, so the run records a stop.

From Sanvio Factory by Sanvio Labs, MIT: https://github.com/SanvioLabs/sanvio-factory
"""
import json
import os
import subprocess
import sys
from pathlib import Path

CLAUDE = os.environ.get("EVAL_CLAUDE", "claude")
MODEL = os.environ.get("EVAL_MODEL", "sonnet")
IDENTITY = ["-c", "user.name=eval-adapter", "-c", "user.email=eval-adapter@example.invalid"]
TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash(python3:*)", "Bash(git diff:*)",
         "Bash(git status:*)", "Bash(git log:*)", "Bash(ls:*)"]
DENIED = ["Bash(git push:*)", "Bash(gh:*)"]
INSTRUCTION = "Resolve this GitHub issue in the repository in the current folder."


def say(text):
    print("[one-session] {}".format(text), flush=True)


def git(*args):
    return subprocess.run(["git"] + list(args), capture_output=True, text=True, check=True).stdout.strip()


def main(argv):
    if len(argv) != 3:
        raise SystemExit("usage: one-session.py ISSUE CLONE REPO")
    issue, clone, repo = argv[0], Path(argv[1]).resolve(), argv[2]
    os.chdir(str(clone))
    git("fetch", "-q", "origin")
    git("checkout", "-q", "-f", "-B", "main", "origin/main")
    found = json.loads(subprocess.run(["gh", "issue", "view", issue, "-R", repo, "--json", "title,body"],
                                      capture_output=True, text=True, check=True).stdout)
    prompt = "{}\n\n# {}\n\n{}".format(INSTRUCTION, found["title"], found["body"] or "")
    say("starting {} on #{}".format(MODEL, issue))
    done = subprocess.run([CLAUDE, "-p", "--model", MODEL, "--permission-mode", "acceptEdits",
                           "--allowedTools"] + TOOLS + ["--disallowedTools"] + DENIED + ["--", prompt],
                          capture_output=True, text=True)
    say("the session exited {}".format(done.returncode))
    if done.stderr.strip():
        say("stderr: {}".format(done.stderr.strip()[-1000:]))
    git("add", "-A")
    if not git("status", "--porcelain"):
        say("the session changed nothing, so there's no pull request")
        return done.returncode or 1
    branch = "eval/issue-{}".format(issue)
    git("checkout", "-q", "-B", branch)
    git(*IDENTITY, "commit", "-q", "-m", "Work on #{}".format(issue))
    git("push", "-q", "-f", "origin", branch)
    subprocess.run(["gh", "pr", "create", "-R", repo, "--base", "main", "--head", branch,
                    "--title", "Work on #{}".format(issue),
                    "--body", (done.stdout.strip() or "No reply from the session.")[-60000:]], check=True)
    git("checkout", "-q", "-f", "main")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
