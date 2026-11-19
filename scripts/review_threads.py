#!/usr/bin/env python3
"""Open a review thread on each blocking finding in the CI review's report, and fail the check when asked to.

Usage, from the Actions workspace, as .github/workflows/review-pr.yml runs it:
    python3 harness/scripts/review_threads.py

It reads $RUNNER_TEMP/report.json through review_report.check(), against the schema beside this file in the
factory checkout, and $RUNNER_TEMP/diff.patch, the diff the prompt was built from. The environment says what to
do: REVIEW_THREADS ("true" to manage threads), FAIL_ON ("blocks" or "never"), AGENT_NAME (the agent whose
report this is, review-pr when unset), and REPO, PR, HEAD_SHA and GH_TOKEN for the GitHub calls, which all go
through gh.

Threads: one per finding whose severity is blocks, on its line when that line is in the diff, else on its file,
else on the first changed file, with the finding's own place in the body. Nits get none. Each thread's first
comment starts with a marker holding a fingerprint of the finding's rule, file and summary, so a later run finds
it again instead of opening a second. Each named agent runs as its own review job, so the marker also names the
agent, except review-pr's, which keeps the marker it always had, and a run touches only its own agent's threads. When a later run no longer reports the finding, the thread gets a reply and
is resolved; when it's reported again, a thread this workflow resolved is reopened. A thread a person resolved
stays resolved, and a thread whose first comment isn't this workflow's is never touched. A run opens at most
MAX_NEW threads. A report that can't be read opens and resolves nothing.

The check: with FAIL_ON=blocks it exits 1 while the report holds a blocking finding, or can't be read; with
never it exits 0. The count comes from the validated report, never from thread state, and a failed GitHub call is
a warning that never changes the exit code. Nothing here approves, requests changes or merges. Standard library
only.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_report  # noqa: E402 (the import needs this folder on the path first)

MAX_NEW = 25
# The Actions token posts as github-actions[bot] to REST and as github-actions to GraphQL.
BOT_LOGINS = ("github-actions", "github-actions[bot]")
MARKER = "<!-- review-pr-thread:{} -->"
RESOLVED_MARKER = "<!-- review-pr-resolved:{} -->"
# The agent's name, then the fingerprint; review-pr's markers carry no name, as before agents could be named.
THREAD = re.compile(r"\A<!-- review-pr-thread:(?:([a-z0-9-]+):)?([0-9a-f]{16}) -->")
RESOLVED = re.compile(r"\A<!-- review-pr-resolved:(?:([a-z0-9-]+):)?([0-9a-f]{16}) -->")
DEFAULT_AGENT = "review-pr"
AGENT = re.compile(r"[a-z0-9-]+")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
TRAILER = "Posted by the review-pr workflow. A person decides what happens to this pull request."
FAIL_ON = ("blocks", "never")

THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          resolvedBy { login }
          first: comments(first: 1) { nodes { databaseId author { login } body } }
          last: comments(last: 1) { nodes { author { login } body } }
        }
      }
    }
  }
}
"""
RESOLVE = "mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { id } } }"
REOPEN = "mutation($id: ID!) { unresolveReviewThread(input: {threadId: $id}) { thread { id } } }"


class GitHubError(Exception):
    """A gh call that failed, or a GraphQL answer that carries errors."""


class GitHub:
    """Every GitHub call this script makes, each through `gh api` with its payload on stdin."""

    def __init__(self, repo, pr, head_sha, run=subprocess.run):
        self.repo, self.pr, self.head_sha, self.run = repo, int(pr), head_sha, run

    def call(self, endpoint, payload):
        try:
            done = self.run(["gh", "api", "--method", "POST", endpoint, "--input", "-"],
                            input=json.dumps(payload), capture_output=True, text=True, check=False)
        except (OSError, subprocess.SubprocessError) as error:
            raise GitHubError(type(error).__name__) from None
        if done.returncode != 0:
            said = (done.stderr or "").strip().splitlines()
            raise GitHubError(said[-1] if said else "gh exited {}".format(done.returncode))
        try:
            answer = json.loads(done.stdout or "null")
        except ValueError:
            raise GitHubError("gh's answer isn't JSON") from None
        if isinstance(answer, dict) and answer.get("errors"):
            raise GitHubError("the GraphQL answer carries errors")
        return answer

    def graphql(self, query, **variables):
        return self.call("graphql", {"query": query, "variables": variables})

    def threads(self):
        """The pull request's review threads, each as a dict of what sync() reads."""
        owner, name = self.repo.split("/", 1)
        out, after = [], None
        while True:
            answer = self.graphql(THREADS_QUERY, owner=owner, name=name, number=self.pr, after=after)
            try:
                page = answer["data"]["repository"]["pullRequest"]["reviewThreads"]
                nodes, info = page["nodes"], page["pageInfo"]
            except (KeyError, TypeError):
                raise GitHubError("the GraphQL answer has no review threads") from None
            for node in nodes:
                first = (node.get("first") or {}).get("nodes") or [{}]
                last = (node.get("last") or {}).get("nodes") or [{}]
                out.append({
                    "id": node.get("id"),
                    "resolved": bool(node.get("isResolved")),
                    "resolved_by": (node.get("resolvedBy") or {}).get("login"),
                    "comment_id": first[0].get("databaseId"),
                    "author": (first[0].get("author") or {}).get("login"),
                    "body": first[0].get("body") or "",
                    "last_author": (last[0].get("author") or {}).get("login"),
                    "last_body": last[0].get("body") or "",
                })
            if not info.get("hasNextPage"):
                return out
            after = info.get("endCursor")

    def open_thread(self, body, path, line=None):
        payload = {"body": body, "commit_id": self.head_sha, "path": path}
        if line is None:
            payload["subject_type"] = "file"
        else:
            payload.update(line=line, side="RIGHT")
        self.call("repos/{}/pulls/{}/comments".format(self.repo, self.pr), payload)

    def reply(self, comment_id, body):
        self.call("repos/{}/pulls/{}/comments/{}/replies".format(self.repo, self.pr, int(comment_id)),
                  {"body": body})

    def resolve(self, thread_id):
        self.graphql(RESOLVE, id=thread_id)

    def reopen(self, thread_id):
        self.graphql(REOPEN, id=thread_id)


def fingerprint(finding):
    """Sixteen hex characters that stay the same while the finding's rule, file and summary do."""
    text = json.dumps([finding["rule"], finding["file"], finding["summary"]])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def changed_lines(diff):
    """{file: set of its lines on the pull request's side that the diff shows}, in the diff's file order."""
    files, path, line = {}, None, None
    for text in diff.splitlines():
        if text.startswith("diff --git "):
            path, line = None, None
        elif text.startswith("+++ ") and line is None:
            name = text[4:].split("\t", 1)[0].strip().strip('"')
            path = name[2:] if name.startswith("b/") else None  # /dev/null: the file was deleted
            if path is not None:
                files.setdefault(path, set())
        elif path is not None and HUNK.match(text):
            line = int(HUNK.match(text).group(1))
        elif path is not None and line is not None:
            if text.startswith((" ", "+")) or text == "":
                files[path].add(line)
                line += 1
            # a removed line takes no number on this side, and "\ No newline" isn't a line
    return files


def place(finding, files):
    """(path, line or None) to put the finding's thread on, or None when the diff changes no file."""
    path = finding["file"]
    if path in files and finding.get("line") in files[path]:
        return path, finding["line"]
    if path in files:
        return path, None
    first = next(iter(files), None)
    return (first, None) if first is not None else None


def marker(agent, fp):
    """The first line of a thread an agent opens for the finding fp."""
    return MARKER.format(fp if agent == DEFAULT_AGENT else "{}:{}".format(agent, fp))


def resolved_marker(agent, fp):
    """The first line of the reply with which an agent resolves its thread for fp."""
    return RESOLVED_MARKER.format(fp if agent == DEFAULT_AGENT else "{}:{}".format(agent, fp))


def parsed(pattern, text):
    """(agent, fingerprint) from a marker at the start of text, or None."""
    match = pattern.match(text or "")
    return (match.group(1) or DEFAULT_AGENT, match.group(2)) if match else None


def where(finding):
    text = review_report.clean(finding["file"])
    if "line" in finding:
        text += ":{}".format(int(finding["line"]))
    return text


def body(finding, fp, path, line, shown=False, agent=DEFAULT_AGENT):
    """The thread's first comment: the agent's marker, then the finding as one line built from its cleaned
    fields. `shown` says the diff does show the finding's line, and the thread is on its file only because GitHub
    refused the line."""
    rule = review_report.clean(finding["rule"]).strip()
    lines = [marker(agent, fp), "",
             "**{}** {}{}: {}".format(review_report.clean(finding["severity"]), where(finding),
                                       " ({})".format(rule) if rule else "", review_report.clean(finding["summary"]))]
    if agent != DEFAULT_AGENT:
        lines += ["", "From the {} agent.".format(agent)]
    if path != finding["file"] or ("line" in finding and line != finding["line"] and not shown):
        lines += ["", "The finding is at {}, which this diff doesn't show, so its thread is on {}.".format(
            where(finding), review_report.clean(path))]
    lines += ["", TRAILER]
    return "\n".join(lines) + "\n"


def ours(thread, agent=DEFAULT_AGENT):
    """The fingerprint of a thread this workflow opened for agent, or None for anyone else's, another agent's
    among them."""
    if thread.get("author") not in BOT_LOGINS:
        return None
    found = parsed(THREAD, thread.get("body"))
    return found[1] if found and found[0] == agent else None


def resolved_by_us(thread, fp, agent=DEFAULT_AGENT):
    """True when this agent's run resolved the thread. resolvedBy may come back empty for a bot, so a last
    comment that is this agent's resolving reply counts too. Another agent's run never resolves this agent's
    thread, so a bot named in resolvedBy is this workflow; anyone else is a person."""
    who = thread.get("resolved_by")
    if who is not None:
        return who in BOT_LOGINS
    return thread.get("last_author") in BOT_LOGINS and parsed(RESOLVED, thread.get("last_body")) == (agent, fp)


def blocking(report):
    """The report's blocking findings, one per fingerprint, in report order."""
    out = {}
    for finding in report["findings"]:
        if finding["severity"] == "blocks":
            out.setdefault(fingerprint(finding), finding)
    return out


def sync(report, threads, diff, gh, head_sha="", warn=print, agent=DEFAULT_AGENT):
    """Open, resolve and reopen agent's threads to match its report. Returns what it did, as counts."""
    done = {"opened": 0, "resolved": 0, "reopened": 0, "skipped": 0}
    if report is None:
        return done
    wanted = blocking(report)
    mine = {}
    for thread in threads:
        fp = ours(thread, agent)
        if fp is not None:
            mine.setdefault(fp, thread)
    sha = " on {}".format(head_sha[:12]) if head_sha else ""

    def attempt(what, *args):
        try:
            what(*args)
            return True
        except (GitHubError, TypeError, ValueError) as error:  # a thread with no comment id is one GitHub broke
            warn("::warning::A GitHub call for a review thread failed, so it was left as it was: {}".format(error))
            return False

    for fp, thread in mine.items():
        if fp in wanted:
            if thread["resolved"] and resolved_by_us(thread, fp, agent):
                # Reopen first: a reply left after a failed reopen would hide the resolving marker for good.
                if attempt(gh.reopen, thread["id"]):
                    done["reopened"] += 1
                    attempt(gh.reply, thread["comment_id"], "This finding is reported again{}.\n\n{}\n".format(
                        sha, TRAILER))
        elif not thread["resolved"]:
            text = "{}\n\nThis finding is no longer reported{}, so the thread is resolved.\n\n{}\n".format(
                resolved_marker(agent, fp), sha, TRAILER)
            if attempt(gh.reply, thread["comment_id"], text) and attempt(gh.resolve, thread["id"]):
                done["resolved"] += 1
    files = changed_lines(diff)
    for fp, finding in wanted.items():
        if fp in mine:
            continue
        spot = place(finding, files)
        if spot is None or done["opened"] >= MAX_NEW:
            done["skipped"] += 1
            continue
        path, line = spot
        opened = attempt(gh.open_thread, body(finding, fp, path, line, agent=agent), path, line)
        if not opened and line is not None:  # the line can move between the diff and the head commit
            opened = attempt(gh.open_thread, body(finding, fp, path, None, shown=True, agent=agent), path, None)
        if opened:
            done["opened"] += 1
    if done["skipped"]:
        warn("::warning::{} blocking finding{} got no new thread: a run opens at most {}, and needs a changed "
             "file to put one on.".format(done["skipped"], "" if done["skipped"] == 1 else "s", MAX_NEW))
    return done


def read_report(temp):
    """(the report, None) or (None, why it can't be read), through review_report's own check."""
    try:
        text = (temp / "report.json").read_text()
    except (OSError, ValueError) as error:
        return None, "report.json couldn't be read ({})".format(type(error).__name__)
    try:
        rules = review_report.schema()
    except (OSError, ValueError) as error:
        return None, "{} couldn't be read ({})".format(review_report.SCHEMA.name, type(error).__name__)
    return review_report.check(text, rules)


def main(environ=None, gh=None, out=print):
    environ = os.environ if environ is None else environ
    fail_on = environ.get("FAIL_ON", "never")
    if fail_on not in FAIL_ON:
        out("::error::fail-on is {!r}, and has to be blocks or never.".format(fail_on))
        return 1
    agent = environ.get("AGENT_NAME") or DEFAULT_AGENT
    if not AGENT.fullmatch(agent):
        out("::error::AGENT_NAME is {!r}, which isn't an agent's name: lowercase letters, digits and hyphens.".format(
            agent))
        return 1
    temp = Path(environ.get("RUNNER_TEMP", "."))
    report, why = read_report(temp)
    threads_on = environ.get("REVIEW_THREADS") == "true"
    if report is None:
        out("::warning::The review's report couldn't be read{}: {}.".format(
            ", so no thread is opened or resolved" if threads_on else "", why))
    if threads_on and report is not None:
        try:
            diff = (temp / "diff.patch").read_text(errors="replace")
        except OSError:
            diff = ""
        head_sha = environ.get("HEAD_SHA", "")
        try:
            gh = gh or GitHub(environ.get("REPO", ""), environ.get("PR", ""), head_sha)
            threads = gh.threads()
        except (GitHubError, ValueError) as error:
            out("::warning::The review threads couldn't be read, so none is opened or resolved: {}".format(error))
        else:
            done = sync(report, threads, diff, gh, head_sha, warn=out, agent=agent)
            out("Review threads: {opened} opened, {resolved} resolved, {reopened} reopened.".format(**done))
    if fail_on == "never":
        return 0
    if report is None:
        out("::error::The review's report couldn't be read, so fail-on: blocks fails this check.")
        return 1
    count = len(blocking(report))
    if count:
        out("::error::{} blocking finding{} open in the review's report.".format(
            count, " is" if count == 1 else "s are"))
        return 1
    out("No blocking findings in the review's report.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
