#!/usr/bin/env python3
"""Grade a CI review the way the loop grades its own: the report's verdict and the pull request's other
checks, through the factory's review-rubric.json.

Usage, from the Actions workspace, as .github/workflows/review-pr.yml runs it:
    python3 harness/scripts/review_grade.py

Each report is a file in $RUNNER_TEMP/reports/, <agent>.md, one for each review agent that ran, or
$RUNNER_TEMP/report.md when that folder holds none. Each report's verdict is its last line, and the one graded is
the worst of them, by WORST_FIRST. An agent $AGENT_NAMES lists (comma-separated) that has no report counts as
unreadable, so an agent that failed can't raise the grade. The rubric is the review-rubric.json at the root of
the factory checkout this file sits in, never one under base/ or head/, which the pull request's repo
controls. The checks are the check runs on $HEAD_SHA in $REPO, read with gh, leaving out the grade's own job
($OWN_CHECK_RUN_ID, from job.check_run_id), so a sibling job in the same run still counts, a review agent's
failed job included. Without that id, as
on GitHub Enterprise Server, it leaves out every check run from this workflow run ($GITHUB_RUN_ID) instead.
While one is still running it reads them again every 30 seconds ($GRADE_POLL_SECONDS), for up to
$GRADE_WAIT_MINUTES minutes (default 10, at most 15, so the grade still lands inside the job's 30 minutes). A
read GitHub refuses (HTTP 403, a token without checks: read) is final: it grades pending at once, saying so.

It writes "Verdict: <verdict>. Grade <n>/10: <why>." to $RUNNER_TEMP/grade.txt and to the step summary. The
grade is advisory: it sets no status, approves nothing and merges nothing. It always exits 0, so the reviews
keep their comments whatever happens here.

The grade itself is loop.py's, imported from beside this file, so there is one copy of how a verdict and the
checks become a number. Standard library only.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Each check run on the commit, one per line: its status, its conclusion or '', its page, which names the
# workflow run it belongs to, its id, and its name, which a ladder rubric's rungs name.
RUNS_JQ = '.check_runs[] | [.status, (.conclusion // ""), .html_url, (.id | tostring), .name] | @tsv'
MAX_WAIT_MINUTES = 15  # the job's timeout is 30 minutes, and the comments are rewritten after this step
NOT_LATER = ("Nothing grades this review later: it stays pending until the workflow runs again on a new push "
             "or a re-run.")
# The verdicts from worst to best. One that isn't here counts as the worst.
WORST_FIRST = ("unreadable", "changes needed", "ready with nits", "ready")


def worst(verdicts):
    """The worst of the verdicts by WORST_FIRST: unreadable for one it doesn't know, or for none at all."""
    ranks = [WORST_FIRST.index(verdict) if verdict in WORST_FIRST else 0 for verdict in verdicts]
    return WORST_FIRST[min(ranks)] if ranks else "unreadable"


def verdict_of(environ, read_verdict):
    """The worst verdict among the reports in $RUNNER_TEMP/reports/, or of report.md when there are none there,
    with unreadable for each agent $AGENT_NAMES lists that has no report."""
    temp = Path(environ.get("RUNNER_TEMP", "."))
    reports = {}
    for path in sorted((temp / "reports").glob("*.md")):
        try:
            reports[path.stem] = path.read_text()
        except OSError:
            reports[path.stem] = ""
    if not reports:
        try:
            reports[""] = (temp / "report.md").read_text()
        except OSError:
            reports[""] = ""
    verdicts = [read_verdict(text) for text in reports.values()]
    names = [name.strip() for name in environ.get("AGENT_NAMES", "").split(",") if name.strip()]
    verdicts += ["unreadable" for name in names if name not in reports]
    return worst(verdicts)


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
    change it; the runs as (status, conclusion, name), or None when they couldn't be read), the way loop.py's
    pr_runs() and pr_checks() read them, without the review's own job. A failed read is pending, as it is in
    the loop. A refused one is final, since reading again gets the same refusal."""
    try:
        done = subprocess.run(["gh", "api", "--paginate", "repos/{}/commits/{}/check-runs".format(repo, sha),
                               "--jq", RUNS_JQ], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        return "pending", "gh couldn't be run ({})".format(error), False, None
    if done.returncode != 0:
        said = (done.stderr.strip().splitlines() or ["nothing"])[0]
        if "HTTP 403" in said:
            return "pending", ("GitHub refused it ({}). The workflow's token needs checks: read to grade the "
                               "checks".format(said)), True, None
        return "pending", "gh api exited {}: {}".format(done.returncode, said), False, None
    own = "/actions/runs/{}/".format(run_id)
    runs = []
    for line in done.stdout.split("\n"):
        if not line.strip():
            continue
        run = line.split("\t")
        if len(run) == 4:  # a line without a name, which a ladder's rung can't match
            run.append("")
        if len(run) != 5:
            return "pending", "gh api gave a line that isn't a check run", False, None
        if own_check_run:
            if run[3] == own_check_run:
                continue
        elif run_id and own in run[2]:
            continue
        runs.append((run[0], run[1], run[4]))
    if any(status == "completed" and conclusion not in passing for status, conclusion, _ in runs):
        return "failing", None, False, runs
    if any(status != "completed" for status, _, _ in runs):
        return "pending", None, False, runs
    return ("passing" if runs else "none"), None, False, runs


def grade(environ):
    """(the line for grade.txt, whether the grade is pending, notes for the step summary)."""
    sys.path.insert(0, str(HERE))
    import loop  # here, inside main's try, so a broken loop.py still lets the review post

    verdict = verdict_of(environ, loop.report_verdict)
    rubric, why = loop.load_rubric(loop.ROOT / loop.DEFAULTS["review_rubric"])
    poll = number(environ, "GRADE_POLL_SECONDS", 30)
    deadline = time.monotonic() + wait_minutes(environ) * 60
    notes, checks, final, runs = [], "", False, ()
    while True:
        if rubric is not None:  # a bad rubric grades 0 whatever the checks say, as in the loop
            checks, failed, final, runs = read_checks(environ.get("REPO", ""), environ.get("HEAD_SHA", ""),
                                                      environ.get("GITHUB_RUN_ID", ""),
                                                      environ.get("OWN_CHECK_RUN_ID", ""), loop.PASSING_CHECKS)
            note = "Reading the check runs failed, so they count as pending: {}.".format(failed) if failed else None
            if note and note not in notes:
                notes.append(note)
        result = loop.review_grade_for(verdict, checks, rubric, why, runs=runs)
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
