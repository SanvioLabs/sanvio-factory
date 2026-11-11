#!/usr/bin/env python3
"""Grade a CI review the way the loop grades its own: the report's verdict and the pull request's other
checks, through the factory's review-rubric.json.

Usage, from the Actions workspace, as .github/workflows/review-pr.yml runs it:
    python3 harness/scripts/review_grade.py

The verdict is the last line of $RUNNER_TEMP/report.md. The rubric is the review-rubric.json at the root of
the factory checkout this file sits in, never one under base/ or head/, which the pull request's repo
controls. The checks are the check runs on $HEAD_SHA in $REPO, read with gh, leaving out the review's own job
($OWN_CHECK_RUN_ID, from job.check_run_id), so a sibling job in the same run still counts. Without that id, as
on GitHub Enterprise Server, it leaves out every check run from this workflow run ($GITHUB_RUN_ID) instead.
While one is still running it reads them again every 30 seconds ($GRADE_POLL_SECONDS), for up to
$GRADE_WAIT_MINUTES minutes (default 10, at most 15, so the review still posts inside the job's 30 minutes). A
read GitHub refuses (HTTP 403, a token without checks: read) is final: it grades pending at once, saying so.

It writes "Verdict: <verdict>. Grade <n>/10: <why>." to $RUNNER_TEMP/grade.txt and to the step summary. The
grade is advisory: it sets no status, approves nothing and merges nothing. It always exits 0, so the review
is posted whatever happens here.

The grade itself is loop.py's, imported from beside this file, so there is one copy of how a verdict and the
checks become a number. Standard library only.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Each check run on the commit, one per line: its status, its conclusion or '', and its page, which names
# the workflow run it belongs to.
RUNS_JQ = '.check_runs[] | [.status, (.conclusion // ""), .html_url, (.id | tostring)] | @tsv'
MAX_WAIT_MINUTES = 15  # the job's timeout is 30 minutes, and the review posts after this step
NOT_LATER = ("Nothing grades this review later: it stays pending until the workflow runs again on a new push "
             "or a re-run.")


def number(environ, name, default):
    """The environment's name as a number of at least 0, or default when it's unset or not a number."""
    try:
        return max(0.0, float(environ.get(name, "") or default))
    except ValueError:
        return float(default)


def wait_minutes(environ):
    """$GRADE_WAIT_MINUTES, at most MAX_WAIT_MINUTES."""
    return min(number(environ, "GRADE_WAIT_MINUTES", 10), MAX_WAIT_MINUTES)


def read_checks(repo, sha, run_id, own_check_run, passing):
    """(passing, none, failing or pending; why reading them failed, or None; whether reading again could
    change it), the way loop.py's pr_checks() reads them, without the review's own job. A failed read is
    pending, as it is in the loop. A refused one is final, since reading again gets the same refusal."""
    try:
        done = subprocess.run(["gh", "api", "--paginate", "repos/{}/commits/{}/check-runs".format(repo, sha),
                               "--jq", RUNS_JQ], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        return "pending", "gh couldn't be run ({})".format(error), False
    if done.returncode != 0:
        said = (done.stderr.strip().splitlines() or ["nothing"])[0]
        if "HTTP 403" in said:
            return "pending", ("GitHub refused it ({}). The workflow's token needs checks: read to grade the "
                               "checks".format(said)), True
        return "pending", "gh api exited {}: {}".format(done.returncode, said), False
    own = "/actions/runs/{}/".format(run_id)
    runs = []
    for line in done.stdout.split("\n"):
        if not line.strip():
            continue
        run = line.split("\t")
        if len(run) != 4:
            return "pending", "gh api gave a line that isn't a check run", False
        if own_check_run:
            if run[3] == own_check_run:
                continue
        elif run_id and own in run[2]:
            continue
        runs.append(run[:2])
    if any(status == "completed" and conclusion not in passing for status, conclusion in runs):
        return "failing", None, False
    if any(status != "completed" for status, _ in runs):
        return "pending", None, False
    return ("passing" if runs else "none"), None, False


def grade(environ):
    """(the line for grade.txt, whether the grade is pending, notes for the step summary)."""
    sys.path.insert(0, str(HERE))
    import loop  # here, inside main's try, so a broken loop.py still lets the review post

    try:
        report = (Path(environ.get("RUNNER_TEMP", ".")) / "report.md").read_text()
    except OSError:
        report = ""
    verdict = loop.report_verdict(report)
    rubric, why = loop.load_rubric(loop.ROOT / loop.DEFAULTS["review_rubric"])
    poll = number(environ, "GRADE_POLL_SECONDS", 30)
    deadline = time.monotonic() + wait_minutes(environ) * 60
    notes, checks, final = [], "", False
    while True:
        if rubric is not None:  # a bad rubric grades 0 whatever the checks say, as in the loop
            checks, failed, final = read_checks(environ.get("REPO", ""), environ.get("HEAD_SHA", ""),
                                                environ.get("GITHUB_RUN_ID", ""), environ.get("OWN_CHECK_RUN_ID", ""),
                                                loop.PASSING_CHECKS)
            note = "Reading the check runs failed, so they count as pending: {}.".format(failed) if failed else None
            if note and note not in notes:
                notes.append(note)
        result = loop.review_grade_for(verdict, checks, rubric, why)
        left = deadline - time.monotonic()
        if result[0] is not None or final or left <= 0:
            break
        time.sleep(min(poll, left))
    return "Verdict: {}.{}".format(verdict, loop.grade_text(result)), result[0] is None, notes


def main(environ=None):
    environ = os.environ if environ is None else environ
    try:
        line, pending, notes = grade(environ)
    except Exception as error:  # noqa: BLE001 (the review posts whatever goes wrong here)
        print("::warning::The review couldn't be graded: {}".format(error))
        return 0
    lines = [line] + notes + ([NOT_LATER] if pending else [])
    print("\n".join(lines))
    try:
        (Path(environ.get("RUNNER_TEMP", ".")) / "grade.txt").write_text(line + "\n")
        summary = environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as out:
                out.write("\n".join(lines) + "\n")
    except OSError as error:
        print("::warning::The grade couldn't be written: {}".format(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
