#!/usr/bin/env python3
"""Factory eval reports, as HTML, Markdown and, where a Chrome-family browser is installed, PDF.

eval_factory.py's report command calls this. A report covers one or more suites. For each it takes one
run, or a group of runs of the same suite (repeat runs), and optionally a run or group to compare against.
A group shows the middle result of its runs and how many runs each check passed in, so a check that
passes only sometimes stands out.

Each suite's part holds a verdict, the headline numbers, each issue with its pull request and time, what
was missed grouped by issue, every check, the stops, the run's details and the comparison. A report on
more than one suite starts with a summary table. Every report ends with an appendix on reading it and
writing a suite.

The PDF is printed by a headless Chrome, Chromium or Edge, found on PATH or in the usual app folders, or
named in EVAL_REPORT_BROWSER (set it empty for no PDF). Each one found is tried in turn. Without one, open
the HTML and print it.

From Sanvio Factory by Sanvio Labs, MIT: https://github.com/SanvioLabs/sanvio-factory
"""
import html
import os
import shutil
import statistics
import subprocess
import tempfile
from pathlib import Path

PDF_TIMEOUT = 120
BROWSER_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
                 "microsoft-edge", "msedge")
BROWSER_PATHS = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 "/Applications/Chromium.app/Contents/MacOS/Chromium",
                 "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")

READING = [
    ("Tests", "Checks from the suite's key, which the factory never sees. Each miss is named by the "
              "behaviour it checks."),
    ("Traps", "Wrong moves the tests can't see, such as editing an existing test until it passes. A trap "
              "miss means the work passed CI and was still wrong."),
    ("Stops", "Each time the run couldn't carry on by itself: a failed start, failed CI, a pull request "
              "closed unmerged, a wait for a person to merge."),
    ("Repeat runs", "With several runs of a suite, the numbers are the middle run's, and each check shows "
                    "how many runs it passed in. One that passes in some runs and not others is flaky: "
                    "don't read much into one run of it."),
    ("Time and cost", "Worth comparing only once tests, traps and stops hold. Cost reads \"not reported\" "
                      "when nothing reported it, never zero."),
    ("Comparing", "Compare runs of the same suite, on the same models, with the same merge setting, so the "
                  "difference is the change you made."),
]
WRITING = [
    "Start one with python3 scripts/eval_factory.py new-suite <folder>, outside the factory.",
    "Seed: the repo before the work, with its CI. Issues: what a person would write, in order. Describe "
    "the problem, not the fix.",
    "Key: score checks behaviour and prints its JSON; reference/ is the right answer; each folder in "
    "wrong/ is one mistake you've seen agents make.",
    "Run validate until the seed fails, each wrong answer fails and the reference passes.",
    "Keep the suite in a private repo its agents can't read. docs/writing-eval-suites.md has the detail.",
]

CSS = """
@page { size: Letter; margin: 0.7in 0.75in; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: #111827; background: #fff;
       font-size: 10.5pt; line-height: 1.45; margin: 24px auto; max-width: 8in; padding: 0 16px; }
@media print { body { margin: 0; padding: 0; max-width: none; } }
h1 { font-size: 20pt; margin: 0 0 2px; }
h2 { font-size: 12.5pt; margin: 22px 0 8px; padding-bottom: 4px; border-bottom: 1px solid #e5e7eb;
     break-after: avoid; }
.sub { color: #6b7280; font-size: 9.5pt; margin-bottom: 14px; }
.verdict { display: inline-block; padding: 3px 10px; border-radius: 999px; font-weight: 600; font-size: 9.5pt; }
.clean { background: #dcfce7; color: #166534; } .unclean { background: #fee2e2; color: #991b1b; }
.tiles { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin: 14px 0 4px; break-inside: avoid; }
.tile { border: 1px solid #e5e7eb; border-radius: 8px; padding: 9px 11px; }
.tile .k { color: #6b7280; font-size: 8.5pt; text-transform: uppercase; letter-spacing: 0.05em; }
.tile .v { font-size: 16pt; font-weight: 650; margin-top: 2px; }
.tile .n { color: #6b7280; font-size: 8pt; }
table { width: 100%; border-collapse: collapse; font-size: 9.5pt; break-inside: avoid; }
th { text-align: left; color: #6b7280; font-weight: 600; font-size: 8.5pt; text-transform: uppercase;
     letter-spacing: 0.04em; padding: 5px 6px; border-bottom: 1px solid #e5e7eb; }
td { padding: 5px 6px; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
.ok { color: #166534; font-weight: 600; } .bad { color: #b91c1c; font-weight: 600; }
.meta td:first-child { color: #6b7280; width: 30%; }
ul { margin: 4px 0 8px; padding-left: 20px; } li { margin: 2px 0; }
.suite, .appendix { page-break-before: always; }
.foot { margin-top: 18px; color: #9ca3af; font-size: 8pt; }
"""


def minutes(seconds):
    return "{:.1f} min".format(seconds / 60) if isinstance(seconds, (int, float)) else str(seconds)


def money(cost):
    return "${:.2f}".format(cost) if isinstance(cost, (int, float)) else str(cost)


def middle(values):
    """The median of values when every one is a number, else None."""
    numbers = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return statistics.median(numbers) if numbers and len(numbers) == len(values) else None


def stop_text(stop):
    return stop.get("why", "") if isinstance(stop, dict) else str(stop)


def summarize(results):
    """One suite's runs, as what a report shows: a group of one is a single run."""
    checks, order = {}, []
    for result in results:
        found = [("test", t["name"], t["passed"], t.get("issue")) for t in result.get("tests", [])]
        found += [("trap", t["name"], t["avoided"], t.get("issue")) for t in result.get("traps", [])]
        for kind, name, ok, issue in found:
            key = (kind, name)
            if key not in checks:
                checks[key] = {"kind": kind, "name": name, "issue": issue, "passed": 0, "of": 0}
                order.append(key)
            checks[key]["passed"] += 1 if ok else 0
            checks[key]["of"] += 1
    scored = [r for r in results if not r.get("not_scored")]

    def counted(kind, field):
        values = [sum(1 for item in r.get(kind, []) if item[field]) for r in scored]
        totals = [len(r.get(kind, [])) for r in scored]
        return (middle(values), max(totals) if totals else 0)

    return {"suite": results[0].get("suite"), "runs": [r.get("run") for r in results], "n": len(results),
            "results": results, "checks": [checks[key] for key in order],
            "tests": counted("tests", "passed"), "traps": counted("traps", "avoided"),
            "stops": middle([len(r.get("stops", [])) for r in results]),
            "seconds": middle([r.get("seconds") for r in results]),
            "cost": middle([r.get("cost") for r in results]),
            "not_scored": [(r.get("run"), r["not_scored"]) for r in results if r.get("not_scored")],
            "key_leaks": sorted({leak for r in results for leak in r.get("key_leaks", [])})}


def fraction(pair):
    done, total = pair
    if done is None:
        return "not scored"
    return "{:g}/{}".format(done, total)


def clean(subject):
    return (not subject["not_scored"] and subject["tests"][1] > 0 and not subject["key_leaks"]
            and all(c["passed"] == subject["n"] for c in subject["checks"])
            and all(not r.get("stops") for r in subject["results"]))


def verdict(subject):
    if subject["not_scored"]:
        return "Not scored: {}".format("; ".join("{}: {}".format(run, why) for run, why in subject["not_scored"]))
    if clean(subject):
        if subject["n"] == 1:
            return "Clean run: every test passed, every trap avoided, no stops"
        return "Clean in all {} runs: every test passed, every trap avoided, no stops".format(subject["n"])
    return "Not clean: see what was missed"


def headline(subject):
    note = "" if subject["n"] == 1 else ", middle of {} runs".format(subject["n"])
    stops = subject["stops"]
    return [("Tests", fraction(subject["tests"]), "hidden checks passed" + note),
            ("Traps", fraction(subject["traps"]), "wrong moves avoided" + note),
            ("Stops", "{:g}".format(stops) if stops is not None else "not recorded", "times a person was needed" + note),
            ("Time", minutes(subject["seconds"]) if subject["seconds"] is not None else "not recorded",
             "wall clock, merges included" + note),
            ("Cost", money(subject["cost"]) if subject["cost"] is not None else "not reported",
             "as reported to the run" + note)]


def issue_rows(subject):
    """(number, title, pull request, outcome, time) for each issue, from the runs that recorded them."""
    recorded = [r.get("issues") or [] for r in subject["results"]]
    longest = max((len(issues) for issues in recorded), default=0)
    rows = []
    for index in range(longest):
        seen = [issues[index] for issues in recorded if index < len(issues)]
        first = seen[0]
        merged = sum(1 for issue in seen if issue.get("state") == "done")
        times = [issue.get("seconds") for issue in seen]
        time = middle(times)
        if subject["n"] == 1:
            outcome = {"done": "Merged", "open": "Open, not merged", "pending": "Not started"}.get(
                first.get("state"), str(first.get("state")))
            pr = "#{}".format(first["pr"]) if first.get("pr") else "none"
        else:
            outcome = "Merged in {} of {}".format(merged, len(seen))
            pr = "one per run"
        rows.append((first.get("number"), first.get("title") or "", pr, outcome,
                     minutes(time) if time else "not recorded", merged == len(seen)))
    return rows


def issue_label(subject, position):
    """'Issue 2: its title' for the issue at that 1-based position in the suite, as far as the runs know."""
    for result in subject["results"]:
        issues = result.get("issues") or []
        if isinstance(position, int) and 1 <= position <= len(issues) and issues[position - 1].get("title"):
            return "Issue {}: {}".format(position, issues[position - 1]["title"])
    return "Issue {}".format(position)


def miss_word(check, n):
    if n == 1:
        return "failed" if check["kind"] == "test" else "fell in"
    verb = "failed" if check["kind"] == "test" else "fell in"
    return "{} in {} of {}".format(verb, check["of"] - check["passed"], check["of"])


def misses_by_issue(subject):
    """[(label, [check])] for each check missed in any run, grouped by the issue it was tagged with."""
    groups = {}
    for check in subject["checks"]:
        if check["passed"] < check["of"]:
            position = check["issue"] if isinstance(check["issue"], int) else None
            groups.setdefault(position, []).append(check)
    tagged = sorted(key for key in groups if key is not None)
    out = [(issue_label(subject, key), groups[key]) for key in tagged]
    if None in groups:
        out.append(("Across the run" if tagged else "", groups[None]))
    return out


def result_word(check, n):
    if n == 1:
        if check["kind"] == "test":
            return "Passed" if check["passed"] else "Failed"
        return "Avoided" if check["passed"] else "Fell in"
    return "{} of {}".format(check["passed"], check["of"])


def moved(before, after):
    """(worse, better): (kind, name, was, now) for each check whose pass rate changed, as text."""
    was = {(c["kind"], c["name"]): c for c in before["checks"]}
    worse, better = [], []
    for check in after["checks"]:
        old = was.get((check["kind"], check["name"]))
        if not old or not old["of"] or not check["of"]:
            continue
        a, b = old["passed"] / old["of"], check["passed"] / check["of"]
        if a == b:
            continue
        change = (check["kind"], check["name"], "{}/{}".format(old["passed"], old["of"]),
                  "{}/{}".format(check["passed"], check["of"]))
        (worse if b < a else better).append(change)
    return worse, better


def change_text(change, single):
    kind, name, was, now = change
    return "{} {}".format(kind, name) if single else "{} {} (from {} to {})".format(kind, name, was, now)


def details(subject):
    if subject["n"] == 1:
        result = subject["results"][0]
        commit = (result.get("factory_commit") or "")[:12]
        return [("Run", result.get("run")), ("Run repo", result.get("repo", "")),
                ("Factory commit", commit + (" (with uncommitted changes)" if result.get("factory_dirty") else "")),
                ("Scored at", result.get("scored_at", "")), ("Key leaks", ", ".join(subject["key_leaks"]) or "none"),
                ("Rounds", result.get("rounds", "not reported")), ("Tokens", result.get("tokens", "not reported"))]
    commits = sorted({(r.get("factory_commit") or "")[:12] for r in subject["results"]})
    return [("Runs", ", ".join(str(run) for run in subject["runs"])),
            ("Run repos", ", ".join(str(r.get("repo", "")) for r in subject["results"])),
            ("Factory commits", ", ".join(commits)), ("Key leaks", ", ".join(subject["key_leaks"]) or "none")]


def subjects_for(groups, compare_groups=None):
    subjects = [summarize(group) for group in groups]
    others = [summarize(group) for group in compare_groups] if compare_groups else [None] * len(subjects)
    return list(zip(subjects, others))


def title_of(pairs):
    if len(pairs) == 1:
        subject = pairs[0][0]
        runs = subject["runs"][0] if subject["n"] == 1 else "{} runs".format(subject["n"])
        return "Suite {}, {}".format(subject["suite"], runs)
    return "{} suites: {}".format(len(pairs), ", ".join(str(s["suite"]) for s, _ in pairs))


def html_subject(subject, other, e):
    out = ['<span class="verdict {}">{}</span>'.format("clean" if clean(subject) else "unclean", e(verdict(subject))),
           '<div class="tiles">']
    for label, value, note in headline(subject):
        out.append('<div class="tile"><div class="k">{}</div><div class="v">{}</div><div class="n">{}</div></div>'
                   .format(e(label), e(value), e(note)))
    out.append('</div>')
    rows = issue_rows(subject)
    if rows:
        out.append('<h2>Issues</h2><table><tr><th>#</th><th>Issue</th><th>Pull request</th><th>Outcome</th>'
                   '<th>Time</th></tr>')
        for number, title, pr, outcome, time, ok in rows:
            out.append('<tr><td>{}</td><td>{}</td><td>{}</td><td class="{}">{}</td><td>{}</td></tr>'.format(
                e(str(number)), e(title), e(pr), "ok" if ok else "bad", e(outcome), e(time)))
        out.append('</table>')
    out.append('<h2>What was missed</h2>')
    groups = misses_by_issue(subject)
    if not groups:
        out.append('<p>Nothing. Every test passed and every trap was avoided{}.</p>'.format(
            "" if subject["n"] == 1 else ", in every run"))
    for label, checks in groups:
        if label:
            out.append('<p><b>{}</b></p>'.format(e(label)))
        out.append('<ul>{}</ul>'.format("".join('<li><span class="bad">{}</span> {}</li>'.format(
            e(miss_word(c, subject["n"])), e(c["name"])) for c in checks)))
    tagged = any(c["issue"] is not None for c in subject["checks"])
    out.append('<h2>Every check</h2><table><tr><th>Check</th><th>Kind</th>{}<th>{}</th></tr>'.format(
        "<th>Issue</th>" if tagged else "", "Result" if subject["n"] == 1 else "Passed in"))
    for c in subject["checks"]:
        out.append('<tr><td>{}</td><td>{}</td>{}<td class="{}">{}</td></tr>'.format(
            e(c["name"]), c["kind"],
            "<td>{}</td>".format(e(str(c["issue"])) if c["issue"] is not None else "") if tagged else "",
            "ok" if c["passed"] == c["of"] else "bad", e(result_word(c, subject["n"]))))
    out.append('</table><h2>Stops</h2>')
    stops = [(r.get("run"), s) for r in subject["results"] for s in r.get("stops", [])]
    if stops:
        out.append('<ul>{}</ul>'.format("".join("<li>{}{}</li>".format(
            "" if subject["n"] == 1 else e(str(run)) + ": ", e(stop_text(s))) for run, s in stops)))
    else:
        out.append('<p>None. {} went from the first issue to the score without a person.</p>'.format(
            "The run" if subject["n"] == 1 else "Every run"))
    out.append('<h2>Run details</h2><table class="meta">')
    for label, value in details(subject):
        out.append('<tr><td>{}</td><td>{}</td></tr>'.format(e(label), e(str(value))))
    out.append('</table>')
    if other is not None:
        name = other["runs"][0] if other["n"] == 1 else "{} runs".format(other["n"])
        mine = "This run" if subject["n"] == 1 else "These {} runs".format(subject["n"])
        out.append('<h2>Compared with {}</h2>'.format(e(str(name))))
        if other["suite"] != subject["suite"]:
            out.append('<p class="bad">That\'s suite {}, not {}: the difference may be the suite.</p>'.format(
                e(str(other["suite"])), e(str(subject["suite"]))))
        out.append('<table><tr><th></th><th>{}</th><th>{}</th></tr>'.format(e(mine), e(str(name))))
        for (label, a, _), (_, b, _) in zip(headline(subject), headline(other)):
            out.append('<tr><td>{}</td><td>{}</td><td>{}</td></tr>'.format(e(label), e(a), e(b)))
        out.append('</table>')
        worse, better = moved(other, subject)
        single = subject["n"] == 1 and other["n"] == 1
        for label, items, cls in (("Worse in " + mine.lower(), worse, "bad"), ("Better in " + mine.lower(), better, "ok")):
            out.append('<p><b>{} ({})</b></p>'.format(e(label), len(items)))
            out.append('<ul>{}</ul>'.format("".join('<li><span class="{}">{}</span> {}</li>'.format(
                cls, ch[0], e(change_text(ch, single).split(" ", 1)[1])) for ch in items)) if items else '<p>Nothing.</p>')
    return "\n".join(out)


def to_html(pairs):
    e = html.escape
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           '<title>Factory eval report: {}</title><style>{}</style></head><body>'.format(e(title_of(pairs)), CSS),
           '<h1>Factory eval report</h1>', '<div class="sub">{}</div>'.format(e(title_of(pairs)))]
    if len(pairs) == 1:
        out.append(html_subject(pairs[0][0], pairs[0][1], e))
    else:
        compared = any(other is not None for _, other in pairs)
        out.append('<h2>Summary</h2><table><tr><th>Suite</th><th>Runs</th><th>Tests</th><th>Traps</th><th>Stops</th>'
                   '<th>Time</th><th>Cost</th>{}</tr>'.format("<th>Compared with</th>" if compared else ""))
        for subject, other in pairs:
            numbers = [h[1] for h in headline(subject)]
            then = ""
            if compared:
                then = "<td>{}</td>".format(e("tests {}, traps {}".format(*[h[1] for h in headline(other)[:2]]))
                                            if other else "")
            out.append('<tr><td>{}</td><td>{}</td>{}{}</tr>'.format(
                e(str(subject["suite"])), subject["n"], "".join("<td>{}</td>".format(e(n)) for n in numbers), then))
        out.append('</table>')
        for subject, other in pairs:
            out.append('<div class="suite"><h1>{}</h1>'.format(e(str(subject["suite"]))))
            out.append(html_subject(subject, other, e))
            out.append('</div>')
    out.append('<div class="appendix"><h2>How to read this report</h2><table class="meta">')
    for label, text in READING:
        out.append('<tr><td>{}</td><td>{}</td></tr>'.format(e(label), e(text)))
    out.append('</table><h2>Write a suite of your own</h2><ol>')
    out.extend("<li>{}</li>".format(e(step)) for step in WRITING)
    out.append('</ol></div><div class="foot">Made by scripts/eval_factory.py report. From Sanvio Factory, MIT.</div>')
    out.append('</body></html>')
    return "\n".join(out)


def cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def md_subject(subject, other):
    heads = headline(subject)
    out = ["**{}**".format(cell(verdict(subject))), "", "| " + " | ".join(h[0] for h in heads) + " |",
           "|" + "---|" * len(heads), "| " + " | ".join(cell(h[1]) for h in heads) + " |", ""]
    if subject["n"] > 1:
        out += ["The middle of {} runs: {}.".format(subject["n"], ", ".join(cell(r) for r in subject["runs"])), ""]
    rows = issue_rows(subject)
    if rows:
        out += ["## Issues", "", "| # | Issue | Pull request | Outcome | Time |", "|---|---|---|---|---|"]
        out += ["| {} | {} | {} | {} | {} |".format(*(cell(v) for v in row[:5])) for row in rows]
        out.append("")
    out += ["## What was missed", ""]
    groups = misses_by_issue(subject)
    if not groups:
        out += ["Nothing. Every test passed and every trap was avoided{}.".format(
            "" if subject["n"] == 1 else ", in every run"), ""]
    for label, checks in groups:
        if label:
            out += ["**{}**".format(cell(label)), ""]
        out += ["- {}: {}".format(miss_word(c, subject["n"]), cell(c["name"])) for c in checks]
        out.append("")
    out += ["## Every check", "", "| Check | Kind | Issue | {} |".format(
        "Result" if subject["n"] == 1 else "Passed in"), "|---|---|---|---|"]
    out += ["| {} | {} | {} | {} |".format(cell(c["name"]), c["kind"], "" if c["issue"] is None else c["issue"],
                                           result_word(c, subject["n"])) for c in subject["checks"]]
    out += ["", "## Stops", ""]
    stops = [(r.get("run"), s) for r in subject["results"] for s in r.get("stops", [])]
    out += ["- {}{}".format("" if subject["n"] == 1 else cell(run) + ": ", cell(stop_text(s))) for run, s in stops] \
        if stops else ["None."]
    out += ["", "## Run details", "", "| | |", "|---|---|"]
    out += ["| {} | {} |".format(cell(label), cell(value)) for label, value in details(subject)]
    if other is not None:
        name = other["runs"][0] if other["n"] == 1 else "{} runs".format(other["n"])
        mine = "This run" if subject["n"] == 1 else "These {} runs".format(subject["n"])
        out += ["", "## Compared with {}".format(cell(name)), ""]
        if other["suite"] != subject["suite"]:
            out += ["That's suite {}, not {}: the difference may be the suite.".format(
                cell(other["suite"]), cell(subject["suite"])), ""]
        out += ["| | {} | {} |".format(mine, cell(name)), "|---|---|---|"]
        out += ["| {} | {} | {} |".format(m[0], cell(m[1]), cell(t[1])) for m, t in zip(headline(subject), headline(other))]
        worse, better = moved(other, subject)
        single = subject["n"] == 1 and other["n"] == 1
        out += ["", "Worse in {}: {}".format(mine.lower(), len(worse))] + ["- " + cell(change_text(c, single)) for c in worse]
        out += ["", "Better in {}: {}".format(mine.lower(), len(better))] + ["- " + cell(change_text(c, single)) for c in better]
    out.append("")
    return out


def to_markdown(pairs):
    out = ["# Factory eval report", "", cell(title_of(pairs)), ""]
    if len(pairs) == 1:
        out += md_subject(pairs[0][0], pairs[0][1])
    else:
        compared = any(other is not None for _, other in pairs)
        out += ["## Summary", "", "| Suite | Runs | Tests | Traps | Stops | Time | Cost |{}".format(
            " Compared with |" if compared else ""), "|---|---|---|---|---|---|---|{}".format("---|" if compared else "")]
        for subject, other in pairs:
            then = ""
            if compared:
                then = " {} |".format("tests {}, traps {}".format(*[h[1] for h in headline(other)[:2]]) if other else "")
            out.append("| {} | {} | {} |{}".format(cell(subject["suite"]), subject["n"],
                                                  " | ".join(cell(h[1]) for h in headline(subject)), then))
        out.append("")
        for subject, other in pairs:
            out += ["# {}".format(cell(subject["suite"])), ""] + md_subject(subject, other)
    out += ["## How to read this report", ""] + ["- **{}:** {}".format(label, text) for label, text in READING]
    out += ["", "## Write a suite of your own", ""] + ["{}. {}".format(i, s) for i, s in enumerate(WRITING, 1)]
    return "\n".join(out) + "\n"


def find_browsers():
    """Chrome-family browsers that could print the PDF, in the order to try them. EVAL_REPORT_BROWSER names
    the only one, or is empty for none. More than one, because a command on PATH can outlive its app."""
    named = os.environ.get("EVAL_REPORT_BROWSER")
    if named is not None:
        return [named] if named else []
    found = [shutil.which(name) for name in BROWSER_NAMES] + [path for path in BROWSER_PATHS if Path(path).is_file()]
    unique = []
    for path in found:
        if path and path not in unique:
            unique.append(path)
    return unique


def print_pdf(browser, page, pdf):
    """Print page (an HTML file) to pdf with a headless browser on a throwaway profile. Returns why it failed,
    or "" when the PDF exists."""
    with tempfile.TemporaryDirectory() as profile:
        try:
            done = subprocess.run([browser, "--headless", "--disable-gpu", "--no-first-run",
                                   "--user-data-dir={}".format(profile), "--no-pdf-header-footer",
                                   "--print-to-pdf-no-header", "--print-to-pdf={}".format(pdf),
                                   Path(page).resolve().as_uri()],
                                  capture_output=True, text=True, timeout=PDF_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as err:
            return "the browser didn't finish: {}".format(err)
    if done.returncode or not Path(pdf).is_file():
        return "the browser exited {} without a PDF".format(done.returncode)
    return ""


def write(groups, folder, compare_groups=None):
    """Write report.html and report.md into folder, and report.pdf when a browser can print it. groups is a
    list of suites, each a list of one or more results; compare_groups lines up with it, or is None.
    Returns (paths written, why there's no PDF or "")."""
    pairs = subjects_for(groups, compare_groups)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    page, notes = folder / "report.html", folder / "report.md"
    page.write_text(to_html(pairs))
    notes.write_text(to_markdown(pairs))
    written = [page, notes]
    browsers = find_browsers()
    if not browsers:
        return written, "no Chrome, Chromium or Edge found, so no PDF: open report.html and print it to PDF"
    pdf = folder / "report.pdf"
    why = ""
    for browser in browsers:
        why = print_pdf(browser, page, pdf)
        if not why:
            written.append(pdf)
            return written, ""
    return written, "{}. Open report.html and print it to PDF".format(why)
