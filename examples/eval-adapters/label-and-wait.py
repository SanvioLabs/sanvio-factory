#!/usr/bin/env python3
"""Hand one issue to a factory that watches for a label and opens its own pull request, then wait for it.

Usage, as scripts/eval_factory.py's --start:
    python3 examples/eval-adapters/label-and-wait.py {issue} {repo}

EVAL_LABEL           the label your factory picks issues up by, by default "loop-ready"
EVAL_STOPPED_LABEL   a label your factory puts on an issue it gives up on, if it has one
EVAL_WAIT_MINUTES    how long to wait for the pull request, by default 55: keep it under --timeout
EVAL_POLL_SECONDS    how often to look, by default 30

Use it when your factory is already watching the run repo, or is started some other way, and opens its own
pull requests. It makes the label if the repo doesn't have it, puts it on this issue only, then waits for a
pull request that wasn't there before. It exits 0 once one is open, and 1 when the wait runs out or the issue
gets the stopped label, so the run records a stop. It never merges, comments, or touches another issue.

From Sanvio Factory by Sanvio Labs, MIT: https://github.com/SanvioLabs/sanvio-factory
"""
import json
import os
import subprocess
import sys
import time

LABEL = os.environ.get("EVAL_LABEL", "loop-ready")
STOPPED = os.environ.get("EVAL_STOPPED_LABEL", "")
WAIT_MINUTES = float(os.environ.get("EVAL_WAIT_MINUTES", "55"))
POLL_SECONDS = float(os.environ.get("EVAL_POLL_SECONDS", "30"))


def say(text):
    print("[label-and-wait] {}".format(text), flush=True)


def gh(*args):
    return subprocess.run(["gh"] + list(args), capture_output=True, text=True, check=True).stdout


def pull_requests(repo):
    return {pr["number"]: pr["url"] for pr in json.loads(gh("pr", "list", "-R", repo, "--state", "all",
                                                             "--limit", "200", "--json", "number,url"))}


def stopped(issue, repo):
    if not STOPPED:
        return False
    labels = json.loads(gh("issue", "view", issue, "-R", repo, "--json", "labels"))["labels"]
    return any(label["name"] == STOPPED for label in labels)


def main(argv):
    if len(argv) != 2:
        raise SystemExit("usage: label-and-wait.py ISSUE REPO")
    issue, repo = argv
    before = pull_requests(repo)
    gh("label", "create", LABEL, "-R", repo, "--force")
    gh("issue", "edit", issue, "-R", repo, "--add-label", LABEL)
    say("labelled #{} {}; waiting up to {:g} minutes for its pull request".format(issue, LABEL, WAIT_MINUTES))
    deadline = time.monotonic() + WAIT_MINUTES * 60
    while time.monotonic() < deadline:
        new = {number: url for number, url in pull_requests(repo).items() if number not in before}
        if new:
            for url in new.values():
                say("pull request {}".format(url))
            return 0
        if stopped(issue, repo):
            say("#{} got {}: the factory gave up on it".format(issue, STOPPED))
            return 1
        time.sleep(POLL_SECONDS)
    say("no pull request for #{} after {:g} minutes".format(issue, WAIT_MINUTES))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
