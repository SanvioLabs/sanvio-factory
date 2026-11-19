"""Run with: python3 -m unittest discover -s tests"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import review_threads  # noqa: E402 (the import needs scripts/ on the path first)
import test_review_pr_workflow as single  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "review-pr.yml"
STEP = "Open a thread per blocking finding"
POST = "Post the report as one comment"
BOT = "github-actions"

# gone.py is deleted, so the first file a thread can go on is src/app.py. Its pull-request-side lines are
# 10 to 13; docs/x.md's is 1.
DIFF = """diff --git a/gone.py b/gone.py
deleted file mode 100644
index 1111111..0000000
--- a/gone.py
+++ /dev/null
@@ -1 +0,0 @@
-x = 1
diff --git a/src/app.py b/src/app.py
index 1111111..2222222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -10,3 +10,4 @@ def run():
     a = 1
-    b = 2
+    c = 3
+    d = 4
     e = 5
diff --git a/docs/x.md b/docs/x.md
index 1111111..2222222 100644
--- a/docs/x.md
+++ b/docs/x.md
@@ -1 +1 @@
-old
+new
\\ No newline at end of file
"""


def finding(summary="Catches every exception and drops it.", file="src/app.py", line=12, severity="blocks",
            rule="AGENTS.md: Rules"):
    out = {"file": file, "severity": severity, "rule": rule, "summary": summary}
    if line is not None:
        out["line"] = line
    return out


def report(*findings, verdict="changes needed"):
    return {"verdict": verdict, "findings": list(findings)}


def thread(fp, resolved=False, resolved_by=None, author=BOT, body=None, last_author=None, last_body=None,
           id="T1", comment_id=101):
    first = body if body is not None else review_threads.MARKER.format(fp) + "\n\nfinding\n"
    return {"id": id, "resolved": resolved, "resolved_by": resolved_by, "comment_id": comment_id,
            "author": author, "body": first, "last_author": last_author or author,
            "last_body": last_body if last_body is not None else first}


class FakeGitHub:
    """Stands in for review_threads.GitHub: records each call, and fails every one when told to."""

    def __init__(self, threads=(), fail=False):
        self.listed, self.fail, self.calls = list(threads), fail, []

    def _do(self, *call):
        self.calls.append(call)
        if self.fail:
            raise review_threads.GitHubError("HTTP 500")

    def threads(self):
        self._do("threads")
        return self.listed

    def open_thread(self, body, path, line=None):
        self._do("open", body, path, line)

    def reply(self, comment_id, body):
        self._do("reply", comment_id, body)

    def resolve(self, thread_id):
        self._do("resolve", thread_id)

    def reopen(self, thread_id):
        self._do("reopen", thread_id)

    def named(self, kind):
        return [call for call in self.calls if call[0] == kind]


def sync(rep, threads=(), diff=DIFF, gh=None):
    gh = gh or FakeGitHub(threads)
    warnings = []
    done = review_threads.sync(rep, list(threads), diff, gh, "abc123def4567890", warn=warnings.append)
    return gh, done, warnings


class Fingerprint(unittest.TestCase):
    def test_it_is_stable_and_sixteen_hex_characters(self):
        fp = review_threads.fingerprint(finding())
        self.assertRegex(fp, r"^[0-9a-f]{16}$")
        self.assertEqual(fp, review_threads.fingerprint(finding()))

    def test_it_changes_with_the_rule_the_file_or_the_summary(self):
        fp = review_threads.fingerprint(finding())
        for other in (finding(rule="AGENTS.md: Other"), finding(file="src/other.py"), finding(summary="Else.")):
            self.assertNotEqual(review_threads.fingerprint(other), fp, other)

    def test_it_holds_when_only_the_line_or_severity_moves(self):
        fp = review_threads.fingerprint(finding())
        self.assertEqual(review_threads.fingerprint(finding(line=40)), fp)
        self.assertEqual(review_threads.fingerprint(finding(line=None)), fp)
        self.assertEqual(review_threads.fingerprint(finding(severity="nit")), fp)


class ChangedLines(unittest.TestCase):
    def test_it_maps_each_file_to_its_pull_request_side_lines(self):
        files = review_threads.changed_lines(DIFF)
        self.assertEqual(list(files), ["src/app.py", "docs/x.md"])
        self.assertEqual(files["src/app.py"], {10, 11, 12, 13})
        self.assertEqual(files["docs/x.md"], {1})

    def test_an_empty_diff_changes_nothing(self):
        self.assertEqual(review_threads.changed_lines(""), {})


class Placement(unittest.TestCase):
    def test_a_line_in_the_diff_gets_a_thread_on_that_line(self):
        gh, done, _ = sync(report(finding(line=12)))
        self.assertEqual(done["opened"], 1)
        (_, body, path, line), = gh.named("open")
        self.assertEqual((path, line), ("src/app.py", 12))
        fp = review_threads.fingerprint(finding())
        self.assertTrue(body.startswith(review_threads.MARKER.format(fp) + "\n"))
        self.assertIn("**blocks** src/app.py:12 (AGENTS.md: Rules): Catches every exception and drops it.", body)
        self.assertNotIn("this diff doesn't show", body)

    def test_a_line_outside_the_diff_goes_on_its_file(self):
        gh, _, _ = sync(report(finding(line=50)))
        (_, body, path, line), = gh.named("open")
        self.assertEqual((path, line), ("src/app.py", None))
        self.assertIn("src/app.py:50", body)

    def test_a_finding_with_no_line_goes_on_its_file(self):
        gh, _, _ = sync(report(finding(file="docs/x.md", line=None)))
        (_, body, path, line), = gh.named("open")
        self.assertEqual((path, line), ("docs/x.md", None))
        self.assertNotIn("this diff doesn't show", body)

    def test_a_file_outside_the_diff_goes_on_the_first_changed_file_naming_the_real_place(self):
        gh, _, _ = sync(report(finding(file="lib/elsewhere.py", line=7)))
        (_, body, path, line), = gh.named("open")
        self.assertEqual((path, line), ("src/app.py", None), "a deleted file takes no thread")
        self.assertIn("lib/elsewhere.py:7", body)
        self.assertIn("The finding is at lib/elsewhere.py:7, which this diff doesn't show", body)

    def test_a_nit_gets_no_thread(self):
        gh, done, _ = sync(report(finding(severity="nit")))
        self.assertEqual(gh.named("open"), [])
        self.assertEqual(done["opened"], 0)

    def test_an_empty_diff_opens_nothing_and_says_so(self):
        gh, done, warnings = sync(report(finding()), diff="")
        self.assertEqual(gh.named("open"), [])
        self.assertEqual(done["skipped"], 1)
        self.assertTrue(any(w.startswith("::warning::") for w in warnings))

    def test_a_refused_line_comment_falls_back_to_the_file(self):
        class RefusesLines(FakeGitHub):
            def open_thread(self, body, path, line=None):
                self._do("open", body, path, line)
                if line is not None:
                    raise review_threads.GitHubError("HTTP 422")

        gh, done, _ = sync(report(finding()), gh=RefusesLines())
        self.assertEqual([(c[2], c[3]) for c in gh.named("open")], [("src/app.py", 12), ("src/app.py", None)])
        self.assertEqual(done["opened"], 1)

    def test_the_body_is_built_from_cleaned_fields(self):
        gh, _, _ = sync(report(finding(summary="Ping @alice <img src=x> ![a](https://e.example/a)\n# Heading")))
        body = gh.named("open")[0][1]
        self.assertNotIn("@alice", body)
        self.assertNotIn("<img", body)
        self.assertNotIn("![", body)
        self.assertNotRegex(body, r"(?m)^# Heading")
        self.assertEqual(body.count("<!--"), 1, "the marker is the only comment in the body")


class Rerun(unittest.TestCase):
    def test_a_rerun_reuses_its_thread_and_opens_nothing(self):
        fp = review_threads.fingerprint(finding())
        gh, done, _ = sync(report(finding(line=13)), [thread(fp)])
        self.assertEqual([c for c in gh.calls if c[0] != "threads"], [])
        self.assertEqual(done, {"opened": 0, "resolved": 0, "reopened": 0, "skipped": 0})

    def test_the_same_finding_twice_opens_one_thread(self):
        gh, done, _ = sync(report(finding(), finding(line=11)))
        self.assertEqual(len(gh.named("open")), 1)

    def test_a_fixed_finding_gets_a_reply_and_is_resolved(self):
        fp = review_threads.fingerprint(finding())
        gh, done, _ = sync(report(), [thread(fp, id="T9", comment_id=77)])
        (_, comment_id, body), = gh.named("reply")
        self.assertEqual(comment_id, 77)
        self.assertTrue(body.startswith(review_threads.RESOLVED_MARKER.format(fp)))
        self.assertIn("no longer reported", body)
        self.assertEqual(gh.named("resolve"), [("resolve", "T9")])
        self.assertEqual(done["resolved"], 1)

    def test_a_finding_turned_nit_is_resolved_too(self):
        fp = review_threads.fingerprint(finding())
        gh, _, _ = sync(report(finding(severity="nit")), [thread(fp)])
        self.assertEqual(len(gh.named("resolve")), 1)

    def test_a_resolved_thread_whose_finding_stays_fixed_is_left_alone(self):
        fp = review_threads.fingerprint(finding())
        gh, _, _ = sync(report(), [thread(fp, resolved=True, resolved_by=BOT)])
        self.assertEqual([c for c in gh.calls if c[0] != "threads"], [])

    def test_a_finding_that_comes_back_reopens_the_thread_this_workflow_resolved(self):
        fp = review_threads.fingerprint(finding())
        gh, done, _ = sync(report(finding()), [thread(fp, resolved=True, resolved_by=BOT, id="T3")])
        self.assertEqual(gh.named("reopen"), [("reopen", "T3")])
        self.assertIn("reported again", gh.named("reply")[0][2])
        self.assertEqual(gh.named("open"), [])
        self.assertEqual(done["reopened"], 1)

    def test_an_empty_resolved_by_counts_as_this_workflow_when_its_reply_is_last(self):
        fp = review_threads.fingerprint(finding())
        last = review_threads.RESOLVED_MARKER.format(fp) + "\n\nno longer reported\n"
        gh, _, _ = sync(report(finding()), [thread(fp, resolved=True, resolved_by=None, last_body=last)])
        self.assertEqual(len(gh.named("reopen")), 1)


class PeopleDecide(unittest.TestCase):
    def test_a_thread_a_person_resolved_stays_resolved_when_its_finding_comes_back(self):
        fp = review_threads.fingerprint(finding())
        for resolved in (thread(fp, resolved=True, resolved_by="alice"),
                         # resolvedBy empty, and the last word a person's, not this workflow's resolving reply
                         thread(fp, resolved=True, resolved_by=None, last_author="alice", last_body="Won't fix."),
                         # resolvedBy empty, and this workflow's last word is its "reported again" reply
                         thread(fp, resolved=True, resolved_by=None, last_body="This finding is reported again.")):
            gh, _, _ = sync(report(finding()), [resolved])
            self.assertEqual([c for c in gh.calls if c[0] != "threads"], [], resolved)

    def test_a_marker_in_someone_else_s_thread_is_never_touched(self):
        fp = review_threads.fingerprint(finding())
        other = review_threads.fingerprint(finding(summary="Gone."))
        for author in ("alice", "dependabot[bot]", "github-actions-impostor"):
            # Not reported any more, so a thread of this workflow's would be resolved; theirs isn't.
            gh, _, _ = sync(report(finding()), [thread(other, author=author),
                                                thread(fp, author=author, resolved=True, resolved_by=BOT)])
            for kind in ("reply", "resolve", "reopen"):
                self.assertEqual(gh.named(kind), [], (author, kind))
            self.assertEqual(len(gh.named("open")), 1, "the finding gets this workflow's own thread")

    def test_a_comment_with_no_marker_is_ignored(self):
        for body in ("Looks wrong to me.", "text before <!-- review-pr-thread:0123456789abcdef -->"):
            gh, _, _ = sync(report(), [thread("0123456789abcdef", body=body)])
            self.assertEqual([c for c in gh.calls if c[0] != "threads"], [], body)


class PerAgent(unittest.TestCase):
    """Each named agent runs as its own review job, so each marks its threads with its name and touches only
    those: one agent's run never resolves a thread another agent opened (#646 on #648's jobs)."""

    def test_review_pr_keeps_the_marker_it_always_had(self):
        fp = review_threads.fingerprint(finding())
        self.assertEqual(review_threads.marker("review-pr", fp), review_threads.MARKER.format(fp))
        self.assertEqual(review_threads.resolved_marker("review-pr", fp), review_threads.RESOLVED_MARKER.format(fp))

    def test_another_agent_marks_its_threads_with_its_name(self):
        fp = review_threads.fingerprint(finding())
        gh = FakeGitHub()
        review_threads.sync(report(finding()), [], DIFF, gh, "abc123", warn=[].append, agent="security-reviewer")
        (_, body, _, _), = gh.named("open")
        self.assertTrue(body.startswith("<!-- review-pr-thread:security-reviewer:{} -->\n".format(fp)), body)
        self.assertIn("security-reviewer", body.split("\n", 2)[2])

    def test_one_agent_never_resolves_a_thread_another_agent_opened(self):
        fp = review_threads.fingerprint(finding())
        theirs = thread(fp, body=review_threads.marker("security-reviewer", fp) + "\n\nfinding\n")
        gh = FakeGitHub([theirs])
        review_threads.sync(report(), [theirs], DIFF, gh, "abc123", warn=[].append, agent="review-pr")
        self.assertEqual(gh.calls, [])
        mine = thread(fp)
        gh = FakeGitHub([mine])
        review_threads.sync(report(), [mine], DIFF, gh, "abc123", warn=[].append, agent="security-reviewer")
        self.assertEqual(gh.calls, [])

    def test_an_agent_reuses_its_own_thread_and_resolves_it_with_its_own_marker(self):
        fp = review_threads.fingerprint(finding())
        own = thread(fp, body=review_threads.marker("security-reviewer", fp) + "\n\nfinding\n")
        gh = FakeGitHub([own])
        done = review_threads.sync(report(finding()), [own], DIFF, gh, "abc123", warn=[].append,
                                   agent="security-reviewer")
        self.assertEqual(done["opened"], 0)
        gh = FakeGitHub([own])
        review_threads.sync(report(), [own], DIFF, gh, "abc123", warn=[].append, agent="security-reviewer")
        (_, _, reply), = gh.named("reply")
        self.assertTrue(reply.startswith(review_threads.resolved_marker("security-reviewer", fp)))
        self.assertEqual(len(gh.named("resolve")), 1)

    def test_an_agent_reopens_only_what_it_resolved(self):
        fp = review_threads.fingerprint(finding())
        last = review_threads.resolved_marker("review-pr", fp) + "\n\nno longer reported\n"
        by_review_pr = thread(fp, resolved=True, body=review_threads.marker("security-reviewer", fp) + "\n\nx\n",
                              last_body=last)
        gh = FakeGitHub([by_review_pr])
        review_threads.sync(report(finding()), [by_review_pr], DIFF, gh, "abc123", warn=[].append,
                            agent="security-reviewer")
        self.assertEqual(gh.named("reopen"), [])

    def test_main_takes_the_agent_from_agent_name_and_refuses_one_that_isnt_a_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "report.json").write_text(json.dumps(report(finding())))
            (Path(tmp) / "diff.patch").write_text(DIFF)
            gh, out = FakeGitHub(), []
            code = review_threads.main({"RUNNER_TEMP": tmp, "FAIL_ON": "never", "REVIEW_THREADS": "true",
                                        "HEAD_SHA": "abc123", "AGENT_NAME": "security-reviewer"}, gh=gh,
                                       out=out.append)
            self.assertEqual(code, 0, out)
            (_, body, _, _), = gh.named("open")
            self.assertIn("review-pr-thread:security-reviewer:", body)
            gh, out = FakeGitHub(), []
            code = review_threads.main({"RUNNER_TEMP": tmp, "FAIL_ON": "never", "REVIEW_THREADS": "true",
                                        "HEAD_SHA": "abc123", "AGENT_NAME": "Not A Name"}, gh=gh, out=out.append)
            self.assertEqual(code, 1)
            self.assertEqual(gh.calls, [])
            self.assertTrue(any(line.startswith("::error::") and "AGENT_NAME" in line for line in out), out)


class Cap(unittest.TestCase):
    def test_thirty_blocking_findings_open_twenty_five_threads(self):
        findings = [finding(summary="Problem {}.".format(n)) for n in range(30)]
        gh, done, warnings = sync(report(*findings))
        self.assertEqual(len(gh.named("open")), 25)
        self.assertEqual(done["opened"], 25)
        self.assertEqual(done["skipped"], 5)
        self.assertTrue(any("at most 25" in w for w in warnings))

    def test_threads_already_open_don_t_count_toward_the_cap(self):
        findings = [finding(summary="Problem {}.".format(n)) for n in range(30)]
        existing = [thread(review_threads.fingerprint(f), id="T{}".format(n)) for n, f in enumerate(findings[:10])]
        gh, _, _ = sync(report(*findings), existing)
        self.assertEqual(len(gh.named("open")), 20)


class Main(unittest.TestCase):
    def run_main(self, text, fail_on="never", threads="true", gh=None, diff=DIFF):
        """main() in a temp folder holding report.json as `text` (none when None) and diff.patch."""
        with tempfile.TemporaryDirectory() as tmp:
            if text is not None:
                (Path(tmp) / "report.json").write_text(text)
            (Path(tmp) / "diff.patch").write_text(diff)
            out = []
            gh = gh if gh is not None else FakeGitHub()
            code = review_threads.main({"RUNNER_TEMP": tmp, "FAIL_ON": fail_on, "REVIEW_THREADS": threads,
                                        "HEAD_SHA": "abc123"}, gh=gh, out=out.append)
            return code, out, gh

    def test_fail_on_blocks_exits_one_naming_the_open_blocking_findings(self):
        text = json.dumps(report(finding(), finding(summary="Other."), finding(severity="nit", summary="Nit.")))
        code, out, _ = self.run_main(text, fail_on="blocks")
        self.assertEqual(code, 1)
        self.assertIn("::error::2 blocking findings are open in the review's report.", out)

    def test_fail_on_blocks_counts_past_the_cap(self):
        text = json.dumps(report(*[finding(summary="P {}.".format(n)) for n in range(30)]))
        code, out, gh = self.run_main(text, fail_on="blocks")
        self.assertEqual(code, 1)
        self.assertIn("::error::30 blocking findings are open in the review's report.", out)
        self.assertEqual(len(gh.named("open")), 25)

    def test_fail_on_blocks_with_none_open_exits_zero(self):
        code, out, _ = self.run_main(json.dumps(report(finding(severity="nit"), verdict="ready with nits")),
                                     fail_on="blocks")
        self.assertEqual(code, 0)
        self.assertFalse([line for line in out if line.startswith("::error::")])

    def test_fail_on_never_always_exits_zero(self):
        for text in (json.dumps(report(finding())), "not json", None):
            code, out, _ = self.run_main(text, fail_on="never")
            self.assertEqual(code, 0, text)
            self.assertFalse([line for line in out if line.startswith("::error::")], text)

    def test_failed_github_calls_never_change_the_exit_code(self):
        text = json.dumps(report(finding()))
        for fail_on, expected in (("never", 0), ("blocks", 1)):
            code, out, gh = self.run_main(text, fail_on=fail_on, gh=FakeGitHub(fail=True))
            self.assertEqual(code, expected, fail_on)
            self.assertTrue(any(line.startswith("::warning::") for line in out), fail_on)

    def test_a_failed_call_after_the_listing_is_a_warning(self):
        class FailsWrites(FakeGitHub):
            def _do(self, *call):
                self.calls.append(call)
                if call[0] != "threads":
                    raise review_threads.GitHubError("HTTP 502")

        code, out, _ = self.run_main(json.dumps(report(finding())), gh=FailsWrites())
        self.assertEqual(code, 0)
        self.assertTrue(any(line.startswith("::warning::") for line in out))

    def test_an_unreadable_report_opens_and_resolves_nothing(self):
        fp = review_threads.fingerprint(finding())
        for text in ("Looks fine.", json.dumps({"verdict": "ready"}), None):
            gh = FakeGitHub([thread(fp)])
            code, out, _ = self.run_main(text, gh=gh)
            self.assertEqual(code, 0)
            self.assertEqual(gh.calls, [], text)
            self.assertTrue(any(line.startswith("::warning::") for line in out), text)

    def test_an_unreadable_report_fails_closed_under_fail_on_blocks(self):
        code, out, _ = self.run_main("not json", fail_on="blocks")
        self.assertEqual(code, 1)
        self.assertIn("::error::The review's report couldn't be read, so fail-on: blocks fails this check.", out)

    def test_an_unknown_fail_on_exits_one_naming_both_values(self):
        code, out, gh = self.run_main(json.dumps(report()), fail_on="block")
        self.assertEqual(code, 1)
        self.assertTrue(any(line.startswith("::error::") and "blocks" in line and "never" in line for line in out))
        self.assertEqual(gh.calls, [])

    def test_threads_off_makes_no_github_call(self):
        gh = FakeGitHub()
        code, _, _ = self.run_main(json.dumps(report(finding())), fail_on="blocks", threads="false", gh=gh)
        self.assertEqual(code, 1)
        self.assertEqual(gh.calls, [])

    def test_threads_on_opens_from_the_report_and_the_diff(self):
        code, out, gh = self.run_main(json.dumps(report(finding(line=11))))
        self.assertEqual(code, 0)
        self.assertEqual([(c[2], c[3]) for c in gh.named("open")], [("src/app.py", 11)])
        self.assertIn("Review threads: 1 opened, 0 resolved, 0 reopened.", out)


class RealGitHub(unittest.TestCase):
    """review_threads.GitHub against a stand-in for subprocess.run, so no call leaves the machine."""

    def client(self, answers=None, code=0):
        calls = []
        answers = list(answers or [])

        def run(argv, input=None, **kwargs):
            calls.append((argv, json.loads(input)))
            stdout = json.dumps(answers.pop(0)) if answers else "{}"
            return subprocess.CompletedProcess(argv, code, stdout=stdout, stderr="HTTP 403: nope\n" if code else "")

        return review_threads.GitHub("o/r", "7", "headsha", run=run), calls

    def page(self, nodes, more=False, cursor=None):
        return {"data": {"repository": {"pullRequest": {"reviewThreads": {
            "pageInfo": {"hasNextPage": more, "endCursor": cursor}, "nodes": nodes}}}}}

    def node(self, id, login="github-actions", body="<!-- review-pr-thread:0123456789abcdef -->"):
        return {"id": id, "isResolved": False, "resolvedBy": None,
                "first": {"nodes": [{"databaseId": 5, "author": {"login": login}, "body": body}]},
                "last": {"nodes": [{"author": {"login": login}, "body": body}]}}

    def test_every_call_is_a_review_comment_a_reply_or_a_thread_mutation(self):
        gh, calls = self.client()
        gh.open_thread("b", "src/app.py", 12)
        gh.open_thread("b", "src/app.py")
        gh.reply(5, "r")
        gh.resolve("T1")
        gh.reopen("T1")
        endpoints = [argv[4] for argv, _ in calls]
        self.assertEqual(endpoints, ["repos/o/r/pulls/7/comments", "repos/o/r/pulls/7/comments",
                                     "repos/o/r/pulls/7/comments/5/replies", "graphql", "graphql"])
        for argv, payload in calls:
            self.assertEqual(argv[:4], ["gh", "api", "--method", "POST"])
            text = " ".join(argv) + json.dumps(payload)
            for word in ("/reviews", "/merge", "statuses", "approve", "mergePullRequest", "addPullRequestReview"):
                self.assertNotIn(word, text)
        self.assertEqual(calls[0][1], {"body": "b", "commit_id": "headsha", "path": "src/app.py", "line": 12,
                                       "side": "RIGHT"})
        self.assertEqual(calls[1][1], {"body": "b", "commit_id": "headsha", "path": "src/app.py",
                                       "subject_type": "file"})
        self.assertIn("resolveReviewThread", calls[3][1]["query"])
        self.assertIn("unresolveReviewThread", calls[4][1]["query"])

    def test_the_source_names_no_review_merge_or_status_endpoint(self):
        source = (ROOT / "scripts" / "review_threads.py").read_text()
        for word in ("/reviews", "/merge", "statuses", "mergePullRequest", "addPullRequestReview",
                     "submitPullRequestReview", "--method PUT", "PATCH"):
            self.assertNotIn(word, source)

    def test_threads_are_read_page_by_page(self):
        gh, calls = self.client([self.page([self.node("T1")], more=True, cursor="c1"),
                                 self.page([self.node("T2", login="alice", body="hm")])])
        threads = gh.threads()
        self.assertEqual([t["id"] for t in threads], ["T1", "T2"])
        self.assertEqual(threads[0]["author"], "github-actions")
        self.assertEqual(threads[0]["comment_id"], 5)
        self.assertEqual([payload["variables"]["after"] for _, payload in calls], [None, "c1"])
        self.assertEqual(calls[0][1]["variables"]["number"], 7)
        self.assertEqual(calls[0][1]["variables"]["owner"], "o")

    def test_a_graphql_answer_with_errors_fails(self):
        gh, _ = self.client([{"errors": [{"message": "no"}]}])
        with self.assertRaises(review_threads.GitHubError):
            gh.resolve("T1")

    def test_a_failed_gh_raises_its_last_line(self):
        gh, _ = self.client(code=1)
        with self.assertRaisesRegex(review_threads.GitHubError, "HTTP 403"):
            gh.reply(5, "r")


class WorkflowStep(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text()
        self.code = single.code(self.text)

    def review_steps(self):
        """The steps of the review job, which runs once per agent (#648)."""
        return single.job_steps(single.jobs(self.code)["review"])

    def step(self, name):
        """The one step named `name` in the review job, cut at the job's end."""
        found = [text for each, text in self.review_steps() if each == name]
        self.assertEqual(len(found), 1, "no single step named " + name)
        return found[0]

    def test_it_is_the_last_step_of_each_agents_review_job_and_runs_only_when_asked(self):
        # #648 split the review into one job per agent, gated as a whole on the agents job, so the step
        # follows that agent's comment, and its own condition is the two inputs alone.
        names = [name for name, _ in self.review_steps()]
        self.assertEqual(names[-1], STEP)
        self.assertEqual(names[-2], POST)
        self.assertEqual([name for name, _ in single.job_steps(single.jobs(self.code)["grade"])].count(STEP), 0)
        if_line = [line.strip() for line in self.step(STEP).splitlines() if line.strip().startswith("if:")]
        self.assertEqual(if_line, ["if: inputs.review-threads || inputs.fail-on != 'never'"])

    def test_its_inputs_default_to_off(self):
        on = self.code.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertRegex(on, r"review-threads:\n\s+description: .*\n\s+required: false\n\s+default: false\n"
                             r"\s+type: boolean")
        self.assertRegex(on, r"fail-on:\n\s+description: .*\n\s+required: false\n\s+default: \"never\"\n"
                             r"\s+type: string")

    def test_inputs_reach_it_through_env_and_it_holds_no_secret(self):
        text = self.step(STEP)
        env = text.split("env:\n", 1)[1].split("run: |", 1)[0]
        self.assertEqual(sorted(line.strip() for line in env.splitlines() if line.strip()), sorted([
            "GH_TOKEN: ${{ github.token }}", "REPO: ${{ github.repository }}",
            "PR: ${{ github.event.pull_request.number }}", "HEAD_SHA: ${{ github.event.pull_request.head.sha }}",
            "REVIEW_THREADS: ${{ inputs.review-threads }}", "FAIL_ON: ${{ inputs.fail-on }}",
            "AGENT_NAME: ${{ matrix.agent.name }}"]))
        run = text.split("run: |", 1)[1]
        self.assertNotIn("${{", run)
        self.assertEqual(run.split(), ["python3", "harness/scripts/review_threads.py"])
        self.assertNotIn("secrets.", text)

    def test_the_comment_step_is_unchanged(self):
        post = self.step(POST)
        self.assertNotIn("review_threads", post)
        self.assertNotIn("inputs.", post)
        env = post.split("env:\n", 1)[1].split("run: |", 1)[0]
        # The post step as #648 left it: no input of #646's reaches it.
        self.assertEqual(sorted(line.strip() for line in env.splitlines() if line.strip()), sorted([
            "GH_TOKEN: ${{ github.token }}", "REPO: ${{ github.repository }}",
            "PR: ${{ github.event.pull_request.number }}", "HEAD_SHA: ${{ github.event.pull_request.head.sha }}",
            "AGENT_NAME: ${{ matrix.agent.name }}"]))
        self.assertNotRegex(post, r"(?m)^        if:")

    def test_the_script_is_in_the_sparse_checkout(self):
        self.assertIn("            /scripts/review_threads.py\n", self.step("Check out the harness"))


if __name__ == "__main__":
    unittest.main()
