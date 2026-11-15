#!/usr/bin/env python3
"""A factory eval run's report, as HTML, Markdown and, where a Chrome-family browser is installed, PDF.

eval_factory.py's report command calls this. It reads one run's result.json, and a second one to compare
against when given, and builds the same report in each format: a verdict, the headline numbers, each issue
with its pull request and time, what was missed grouped by issue, every check, the stops, the run's
details, an optional comparison, and an appendix on reading the report and writing a suite.

The PDF is printed by a headless Chrome, Chromium or Edge, found on PATH or in the usual app folders, or
named in EVAL_REPORT_BROWSER (set it empty for no PDF). Without one, open the HTML and print it.

From Sanvio Factory by Sanvio Labs, MIT: https://github.com/SanvioLabs/sanvio-factory
"""
import html
import os
import shutil
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
    ("Time and cost", "Worth comparing only once tests, traps and stops hold. Cost reads \"not reported\" "
                      "when nothing reported it, never zero."),
    ("Comparing", "Compare runs of the same suite, on the same models, with the same merge setting. Runs "
                  "vary, so compare the middle of three runs each way before keeping a change."),
]
WRITING = [
    "Start one with python3 scripts/eval_factory.py new-suite <folder>, outside the factory.",
    "Seed: the repo before the work, with its CI. Issues: what a person would write, in order. Describe "
    "the problem, not the fix.",
    "Key: score checks behaviour and prints its JSON; reference/ is the right answer; each folder in "
    "wrong/ is one mistake you've seen agents make.",
    "Run validate until the seed fails, each wrong answer fails and the reference passes.",
    "Keep the suite in a private repo its agents can't read. docs/eval-walkthrough.md step 6 has the detail.",
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
.appendix { page-break-before: always; }
.foot { margin-top: 18px; color: #9ca3af; font-size: 8pt; }
"""


def minutes(seconds):
    return "{:.1f} min".format(seconds / 60) if isinstance(seconds, (int, float)) else str(seconds)


def money(cost):
    return "${:.2f}".format(cost) if isinstance(cost, (int, float)) else str(cost)


def tally(items, field):
    return sum(1 for item in items if item[field]), len(items)


def clean(result):
    tests_ok, tests_n = tally(result.get("tests", []), "passed")
    traps_ok, traps_n = tally(result.get("traps", []), "avoided")
    return (not result.get("not_scored") and tests_n > 0 and tests_ok == tests_n and traps_ok == traps_n
            and not result.get("key_leaks") and not result.get("stops"))


def stop_text(stop):
    return stop.get("why", "") if isinstance(stop, dict) else str(stop)


def checks(result):
    """Every test and trap as (kind, name, ok, issue position or None)."""
    found = [("test", t["name"], t["passed"], t.get("issue")) for t in result.get("tests", [])]
    return found + [("trap", t["name"], t["avoided"], t.get("issue")) for t in result.get("traps", [])]


def issue_label(result, position):
    """'Issue 2: its title' for the issue at that 1-based position in the suite, as far as the result knows."""
    issues = result.get("issues") or []
    if isinstance(position, int) and 1 <= position <= len(issues):
        title = issues[position - 1].get("title")
        return "Issue {}: {}".format(position, title) if title else "Issue {}".format(position)
    return "Issue {}".format(position)


def misses_by_issue(result):
    """[(label, [(kind, name)])] for every miss, grouped by the issue it was tagged with, in suite order."""
    groups = {}
    for kind, name, ok, position in checks(result):
        if not ok:
            groups.setdefault(position if isinstance(position, int) else None, []).append((kind, name))
    tagged = sorted(key for key in groups if key is not None)
    out = [(issue_label(result, key), groups[key]) for key in tagged]
    if None in groups:
        out.append(("Across the run" if tagged else "", groups[None]))
    return out


def moved(a, b):
    """(worse, better) checks between two results, by kind and name."""
    before = {(kind, name): ok for kind, name, ok, _ in checks(a)}
    after = {(kind, name): ok for kind, name, ok, _ in checks(b)}
    shared = [key for key in after if key in before]
    return ([key for key in shared if before[key] and not after[key]],
            [key for key in shared if after[key] and not before[key]])


def verdict(result):
    if result.get("not_scored"):
        return "Not scored: {}".format(result["not_scored"])
    if clean(result):
        return "Clean run: every test passed, every trap avoided, no stops"
    return "Not clean: see what was missed"


def headline(result):
    tests_ok, tests_n = tally(result.get("tests", []), "passed")
    traps_ok, traps_n = tally(result.get("traps", []), "avoided")
    return [("Tests", "{}/{}".format(tests_ok, tests_n), "hidden checks passed"),
            ("Traps", "{}/{}".format(traps_ok, traps_n), "wrong moves avoided"),
            ("Stops", str(len(result.get("stops", []))), "times a person was needed"),
            ("Time", minutes(result.get("seconds")), "wall clock, merges included"),
            ("Cost", money(result.get("cost")), "as reported to the run")]


def issue_rows(result):
    """(number, title, pull request, outcome, time) for each issue the result records."""
    rows = []
    for issue in result.get("issues") or []:
        outcome = {"done": "Merged", "open": "Open, not merged", "pending": "Not started"}.get(
            issue.get("state"), str(issue.get("state")))
        rows.append((issue.get("number"), issue.get("title") or "", "#{}".format(issue["pr"]) if issue.get("pr")
                     else "none", outcome, minutes(issue.get("seconds")) if issue.get("seconds") else "not recorded"))
    return rows


def details(result):
    commit = (result.get("factory_commit") or "")[:12]
    return [("Run", result.get("run")), ("Run repo", result.get("repo", "")),
            ("Factory commit", commit + (" (with uncommitted changes)" if result.get("factory_dirty") else "")),
            ("Scored at", result.get("scored_at", "")), ("Key leaks", ", ".join(result.get("key_leaks", [])) or "none"),
            ("Rounds", result.get("rounds", "not reported")), ("Tokens", result.get("tokens", "not reported"))]


def to_html(result, other=None):
    e = html.escape
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           '<title>Factory eval report: {}</title><style>{}</style></head><body>'.format(e(str(result.get("run"))), CSS),
           '<h1>Factory eval report</h1>',
           '<div class="sub">Suite <b>{}</b> &middot; run {}</div>'.format(e(str(result.get("suite"))), e(str(result.get("run")))),
           '<span class="verdict {}">{}</span>'.format("clean" if clean(result) else "unclean", e(verdict(result))),
           '<div class="tiles">']
    for label, value, note in headline(result):
        out.append('<div class="tile"><div class="k">{}</div><div class="v">{}</div><div class="n">{}</div></div>'
                   .format(e(label), e(value), e(note)))
    out.append('</div>')

    rows = issue_rows(result)
    if rows:
        out.append('<h2>Issues</h2><table><tr><th>#</th><th>Issue</th><th>Pull request</th><th>Outcome</th>'
                   '<th>Time</th></tr>')
        for number, title, pr, outcome, time in rows:
            out.append('<tr><td>{}</td><td>{}</td><td>{}</td><td class="{}">{}</td><td>{}</td></tr>'.format(
                e(str(number)), e(title), e(pr), "ok" if outcome == "Merged" else "bad", e(outcome), e(time)))
        out.append('</table>')

    out.append('<h2>What was missed</h2>')
    groups = misses_by_issue(result)
    if not groups:
        out.append('<p>Nothing. Every test passed and every trap was avoided.</p>')
    for label, items in groups:
        if label:
            out.append('<p><b>{}</b></p>'.format(e(label)))
        out.append('<ul>{}</ul>'.format("".join('<li><span class="bad">{}</span> {}</li>'.format(
            "failed" if kind == "test" else "fell in", e(name)) for kind, name in items)))

    tagged = any(position is not None for _, _, _, position in checks(result))
    out.append('<h2>Every check</h2><table><tr><th>Check</th><th>Kind</th>{}<th>Result</th></tr>'.format(
        "<th>Issue</th>" if tagged else ""))
    for kind, name, ok, position in checks(result):
        word = ("Passed" if ok else "Failed") if kind == "test" else ("Avoided" if ok else "Fell in")
        out.append('<tr><td>{}</td><td>{}</td>{}<td class="{}">{}</td></tr>'.format(
            e(name), kind, "<td>{}</td>".format(e(str(position)) if position is not None else "") if tagged else "",
            "ok" if ok else "bad", word))
    out.append('</table>')

    out.append('<h2>Stops</h2>')
    stops = result.get("stops", [])
    out.append('<ul>{}</ul>'.format("".join("<li>{}</li>".format(e(stop_text(s))) for s in stops)) if stops
               else '<p>None. The run went from the first issue to the score without a person.</p>')

    out.append('<h2>Run details</h2><table class="meta">')
    for label, value in details(result):
        out.append('<tr><td>{}</td><td>{}</td></tr>'.format(e(label), e(str(value))))
    out.append('</table>')

    if other is not None:
        out.append('<h2>Compared with {}</h2>'.format(e(str(other.get("run")))))
        out.append('<table><tr><th></th><th>This run</th><th>{}</th></tr>'.format(e(str(other.get("run")))))
        for (label, mine, _), (_, theirs, _) in zip(headline(result), headline(other)):
            out.append('<tr><td>{}</td><td>{}</td><td>{}</td></tr>'.format(e(label), e(mine), e(theirs)))
        out.append('</table>')
        worse, better = moved(other, result)
        for label, items, cls in (("Worse in this run", worse, "bad"), ("Better in this run", better, "ok")):
            out.append('<p><b>{} ({})</b></p>'.format(label, len(items)))
            out.append('<ul>{}</ul>'.format("".join('<li><span class="{}">{}</span> {}</li>'.format(cls, k, e(n))
                                                      for k, n in items)) if items else '<p>Nothing.</p>')

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


def to_markdown(result, other=None):
    out = ["# Factory eval report", "",
           "Suite **{}**, run {}".format(cell(result.get("suite")), cell(result.get("run"))), "",
           "**{}**".format(cell(verdict(result))), "", "| " + " | ".join(h[0] for h in headline(result)) + " |",
           "|" + "---|" * len(headline(result)), "| " + " | ".join(cell(h[1]) for h in headline(result)) + " |", ""]
    rows = issue_rows(result)
    if rows:
        out += ["## Issues", "", "| # | Issue | Pull request | Outcome | Time |", "|---|---|---|---|---|"]
        out += ["| {} | {} | {} | {} | {} |".format(*(cell(v) for v in row)) for row in rows]
        out.append("")
    out += ["## What was missed", ""]
    groups = misses_by_issue(result)
    if not groups:
        out += ["Nothing. Every test passed and every trap was avoided.", ""]
    for label, items in groups:
        if label:
            out += ["**{}**".format(cell(label)), ""]
        out += ["- {}: {}".format("failed" if kind == "test" else "fell in", cell(name)) for kind, name in items]
        out.append("")
    out += ["## Every check", "", "| Check | Kind | Issue | Result |", "|---|---|---|---|"]
    for kind, name, ok, position in checks(result):
        word = ("Passed" if ok else "Failed") if kind == "test" else ("Avoided" if ok else "Fell in")
        out.append("| {} | {} | {} | {} |".format(cell(name), kind, "" if position is None else position, word))
    out += ["", "## Stops", ""]
    stops = result.get("stops", [])
    out += ["- {}".format(cell(stop_text(s))) for s in stops] if stops else ["None."]
    out += ["", "## Run details", "", "| | |", "|---|---|"]
    out += ["| {} | {} |".format(cell(label), cell(value)) for label, value in details(result)]
    if other is not None:
        out += ["", "## Compared with {}".format(cell(other.get("run"))), "",
                "| | This run | {} |".format(cell(other.get("run"))), "|---|---|---|"]
        out += ["| {} | {} | {} |".format(m[0], cell(m[1]), cell(t[1])) for m, t in zip(headline(result), headline(other))]
        worse, better = moved(other, result)
        out += ["", "Worse in this run: {}".format(len(worse))] + ["- {} {}".format(k, cell(n)) for k, n in worse]
        out += ["", "Better in this run: {}".format(len(better))] + ["- {} {}".format(k, cell(n)) for k, n in better]
    out += ["", "## How to read this report", ""] + ["- **{}:** {}".format(label, text) for label, text in READING]
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


def write(result, folder, other=None):
    """Write report.html and report.md into folder, and report.pdf when a browser can print it.
    Returns (paths written, why there's no PDF or "")."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    page, notes = folder / "report.html", folder / "report.md"
    page.write_text(to_html(result, other))
    notes.write_text(to_markdown(result, other))
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
