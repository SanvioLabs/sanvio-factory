#!/usr/bin/env python3
"""What got done in a repo over a period, from GitHub and its CHANGELOG, for a work report.

    python3 scripts/work_report.py                       # this repo, since 14 days ago, as Markdown
    python3 scripts/work_report.py --since 2026-10-01
    python3 scripts/work_report.py --project app         # a repo under projects/ instead
    python3 scripts/work_report.py --json

It reads, through gh, in the harness root or the repo under projects/:

    pull_requests  each pull request merged on or after --since, through one GraphQL search: its number,
                   title, address, author's login, when it opened and merged, the issues it closes, the
                   milestones it and those issues are on, who else reviewed it and who else approved it,
                   the specs its closed issues name, and its type. loop_built is true when its branch is loop/issue-N, the branch the loop
                   opens; the loop opens it as whoever runs the loop, so it counts as that login's. A
                   review counts when its author isn't the pull request's and isn't a bot (GitHub's Bot
                   type, which gh's own reviews field doesn't show), and isn't pending or dismissed. An
                   approval is such a review in the APPROVED state, read on its own so a long thread of
                   comments can't push it out of the first REVIEWS. Its type is the first of TYPES
                   among its own labels, or else among its closed issues' labels, or null: never a
                   guess from its branch or title
    totals         counts over those, and the median minutes from opened to merged
    by_person      for each login that authored or reviewed one: the same counts, and reviews_given, how
                   many of the others' pull requests it reviewed
    by_type        merged and loop_built for each of TYPES, then untyped
    by_day         every UTC day from --since to today's UTC date, oldest first, with merged and loop_built
    milestones     GitHub milestones: closed, the ones closed on or after --since, and open, each with
                   how many of what's on it are done and still open (GitHub counts its pull requests
                   with its issues) and its due date
    releases       releases published on or after --since, drafts left out, from the newest RELEASES
    specs          for each spec a closed issue names, the pull requests that closed one. An issue names
                   it with a line "Spec: <path> [requirement ...]", as a bullet or not; the path, its
                   first word, is the spec, and N/A or none names none
    changelog      the entries dated on or after --since in CHANGELOG.md on GitHub's default branch, so
                   only what merged, newest first: what shipped, in words. It reads headings of the shape
                   "## YYYY-MM-DD: Name", and says so when the file has none
    watch          sentences on what a lead would ask about: merged work nobody else approved, work on no
                   milestone or spec, work with no type, a milestone closed late or with issues open, one past its due date,
                   and a search that stopped at its limit

Milestones are only what GitHub records: a release or a closed milestone. It never picks one, and a
CHANGELOG entry is not a milestone.

Unlike the other reports here, this one names people. It prints each pull request's author, reviewers
and approvers by GitHub login, with its number, title and address, because a lead reads it to see who
did what. It never prints an issue's or a pull request's body, beyond the one "Spec:" line's value,
nor a commit message, a diff or an email.

A section whose source is missing or can't be read is {"value": null, "why": ...}, and the script still
exits 0. GitHub's search returns at most LIMIT pull requests; truncated says when there were more, and
then the counts are low. The search gets SEARCH_TIMEOUT seconds in all.
"""
import argparse
import base64
import datetime
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from dashboard_data import LOOP_BRANCH, gh, missing  # noqa: E402 (needs scripts/ on the path first)
from usage_report import since_date  # noqa: E402 (same reason)

SCHEMA = 1  # the document's shape; goes up when a section's shape changes
LIMIT = 1000  # GitHub's search returns no more than this
RELEASES = 100  # newest releases read
REVIEWS = 100  # reviews read per pull request, oldest first
SEARCH_TIMEOUT = 120  # seconds for the whole paginated search, about 2 a page of 100
QUERY = """query($q: String!, $endCursor: String) {
  search(query: $q, type: ISSUE, first: 100, after: $endCursor) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest {
      number title url createdAt mergedAt headRefName
      author { __typename login }
      milestone { title }
      labels(first: 20) { nodes { name } }
      closingIssuesReferences(first: 20) { nodes { number body milestone { title } labels(first: 20) { nodes { name } } } }
      reviews(first: %d) { nodes { state author { __typename login } } }
      approvals: reviews(first: 20, states: [APPROVED]) { nodes { author { __typename login } } }
    } }
  }
}""" % REVIEWS
TYPES = ("bug", "enhancement", "documentation", "chore")  # steering/tickets.md's type labels, in this order
COUNTED_REVIEWS = {"APPROVED", "CHANGES_REQUESTED", "COMMENTED"}
SPEC_LINE = re.compile(r"^\s*(?:[-*]\s+)?\**Spec:\**\s*(\S+)", re.M)
NO_SPEC = {"n/a", "none", "-"}
CHANGELOG_HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2}): (\S.*)$", re.M)
SHIPPED_SHOWN = 15  # changelog entries the Markdown lists before "and N more"


def flat(pages):
    """The items of gh's pages, one array per page, or None when any page isn't a list."""
    if pages is None or not all(isinstance(page, list) for page in pages):
        return None
    return [item for page in pages for item in page if isinstance(item, dict)]


def searched(pages):
    """(pull requests, how many the search matched, why not) from the GraphQL search's pages.

    Any page it can't read loses the lot, since a count from part of the pages would read as the whole.
    """
    if pages is None:
        return None, 0, "gh unavailable"
    try:
        found = [page["data"]["search"] for page in pages]
        prs = [node for page in found for node in page["nodes"] if isinstance(node, dict)]
    except (KeyError, TypeError):
        return None, 0, "GitHub's search returned a page it couldn't read"
    matched = found[0].get("issueCount") if found else 0
    return prs, matched if isinstance(matched, int) else 0, None


def nodes(value):
    return [n for n in (value or {}).get("nodes") or [] if isinstance(n, dict)] if isinstance(value, dict) else []


def person(actor):
    """A login, or None for a bot or an account that no longer exists."""
    if not isinstance(actor, dict) or not isinstance(actor.get("login"), str):
        return None
    if actor.get("__typename") == "Bot" or actor["login"].endswith("[bot]"):
        return None
    return actor["login"]


def when(text):
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def spec_of(issue):
    """The path on the first "Spec:" line of an issue's body, or None. Nothing else of the body is kept."""
    body = issue.get("body") if isinstance(issue.get("body"), str) else ""
    found = SPEC_LINE.search(body)
    if not found or found.group(1).lower() in NO_SPEC:
        return None
    return found.group(1)[:120]


def type_of(*labelled):
    """The first of TYPES on the first item in labelled that carries one, or None."""
    for item in labelled:
        names = {label.get("name") for label in nodes(item.get("labels"))}
        for kind in TYPES:
            if kind in names:
                return kind
    return None


def pull_request_rows(prs):
    """One row per merged pull request, oldest merge first."""
    rows = []
    for pr in prs:
        opened, merged = when(pr.get("createdAt")), when(pr.get("mergedAt"))
        if not isinstance(pr.get("number"), int) or merged is None:
            continue
        author = person(pr.get("author")) or (pr.get("author") or {}).get("login") or "ghost"
        issues = [i for i in nodes(pr.get("closingIssuesReferences")) if isinstance(i.get("number"), int)]
        reviews = [(person(r.get("author")), r.get("state")) for r in nodes(pr.get("reviews"))]
        reviews = [(who, state) for who, state in reviews if who and who != author and state in COUNTED_REVIEWS]
        approvers = {person(r.get("author")) for r in nodes(pr.get("approvals"))} - {None, author}
        milestones = {m.get("title") for m in [pr.get("milestone")] + [i.get("milestone") for i in issues]
                      if isinstance(m, dict) and isinstance(m.get("title"), str)}
        branch = pr.get("headRefName") if isinstance(pr.get("headRefName"), str) else ""
        rows.append({
            "number": pr["number"],
            "title": pr.get("title") if isinstance(pr.get("title"), str) else "",
            "url": pr.get("url") if isinstance(pr.get("url"), str) else None,
            "author": author,
            "merged": merged.date().isoformat(),
            "minutes_to_merge": round((merged - opened).total_seconds() / 60, 1) if opened else None,
            "closes": sorted(i["number"] for i in issues),
            "milestones": sorted(milestones),
            "loop_built": bool(LOOP_BRANCH.match(branch)),
            "reviewers": sorted({who for who, _ in reviews} | approvers),
            "approved_by": sorted(approvers),
            "specs": sorted({s for s in map(spec_of, issues) if s}),
            "type": type_of(pr, *issues),
        })
    return sorted(rows, key=lambda r: (r["merged"], r["number"]))


def counts(rows):
    minutes = [r["minutes_to_merge"] for r in rows if r["minutes_to_merge"] is not None]
    return {"merged": len(rows),
            "loop_built": sum(1 for r in rows if r["loop_built"]),
            "hand_built": sum(1 for r in rows if not r["loop_built"]),
            "issues_closed": len({n for r in rows for n in r["closes"]}),
            "approved_by_another": sum(1 for r in rows if r["approved_by"]),
            "on_a_milestone_or_spec": sum(1 for r in rows if r["milestones"] or r["specs"]),
            "median_minutes_to_merge": round(statistics.median(minutes), 1) if minutes else None}


def by_person(rows):
    logins = {r["author"] for r in rows} | {who for r in rows for who in r["reviewers"]}
    people = [dict(counts([r for r in rows if r["author"] == who]), login=who,
                   reviews_given=sum(1 for r in rows if who in r["reviewers"])) for who in logins]
    return sorted(people, key=lambda p: (-p["merged"], -p["reviews_given"], p["login"]))


def by_type(rows):
    return [{"type": kind, "merged": sum(1 for r in rows if r["type"] == kind),
             "loop_built": sum(1 for r in rows if r["type"] == kind and r["loop_built"])} for kind in TYPES + (None,)]


def by_day(rows, since, today):
    days = {}
    day = datetime.date.fromisoformat(since)
    while day <= today:
        days[day.isoformat()] = {"day": day.isoformat(), "merged": 0, "loop_built": 0}
        day += datetime.timedelta(days=1)
    for row in rows:
        if row["merged"] in days:
            days[row["merged"]]["merged"] += 1
            days[row["merged"]]["loop_built"] += int(row["loop_built"])
    return list(days.values())


def milestone_rows(raw, since):
    closed, open_ = [], []
    for m in raw:
        row = {"title": m.get("title") if isinstance(m.get("title"), str) else "",
               "url": m.get("html_url") if isinstance(m.get("html_url"), str) else None,
               "issues_closed": m.get("closed_issues") if isinstance(m.get("closed_issues"), int) else 0,
               "issues_open": m.get("open_issues") if isinstance(m.get("open_issues"), int) else 0,
               "due": m["due_on"][:10] if isinstance(m.get("due_on"), str) else None}
        if m.get("state") == "closed" and isinstance(m.get("closed_at"), str):
            if m["closed_at"][:10] >= since:
                closed.append(dict(row, closed=m["closed_at"][:10]))
        elif m.get("state") == "open":
            open_.append(row)
    return {"closed": sorted(closed, key=lambda r: r["closed"]),
            "open": sorted(open_, key=lambda r: (r["due"] or "~", r["title"]))}


def release_rows(raw, since):
    out = [{"name": r.get("name") or r.get("tagName") or "", "tag": r.get("tagName"), "published": r["publishedAt"][:10]}
           for r in raw if isinstance(r.get("publishedAt"), str) and r["publishedAt"][:10] >= since and not r.get("isDraft")]
    return sorted(out, key=lambda r: r["published"])


def changelog_rows(text, since):
    found = CHANGELOG_HEADING.findall(text)
    if not found:
        return missing("no '## YYYY-MM-DD: Name' headings in CHANGELOG.md")
    return [{"date": d, "name": n.strip()} for d, n in found if d >= since]


def merged_changelog(root):
    """CHANGELOG.md's text on GitHub's default branch, or None when gh can't read it."""
    found = gh(root, "api", "repos/{owner}/{repo}/contents/CHANGELOG.md")
    page = found[0] if found and isinstance(found[0], dict) else {}
    if page.get("encoding") != "base64" or not isinstance(page.get("content"), str):
        return None
    try:
        return base64.b64decode(page["content"]).decode("utf-8")
    except ValueError:
        return None


def spec_rows(rows):
    specs = defaultdict(list)
    for row in rows:
        for spec in row["specs"]:
            specs[spec].append(row["number"])
    return [{"spec": s, "pull_requests": numbers} for s, numbers in sorted(specs.items())]


def short(day, year=True):
    """Oct 6 2026, built by hand because %-d isn't there on Windows."""
    d = datetime.date.fromisoformat(day)
    return "{} {}".format(d.strftime("%b"), d.day) + (" {}".format(d.year) if year else "")


def watch(doc, today):
    """What a lead would ask about, one sentence each, from the sections that could be read."""
    out = []
    if doc["truncated"]:
        out.append("GitHub's search stopped at {} pull requests, so every count here is low.".format(LIMIT))
    totals = doc["totals"]
    if "merged" in totals and totals["merged"]:
        n = totals["merged"]
        unapproved = n - totals["approved_by_another"]
        if unapproved:
            out.append("{} of {} merged pull requests weren't approved by anyone but their author.".format(unapproved, n))
        untyped = next(t["merged"] for t in doc["by_type"] if t["type"] is None)
        if untyped:
            out.append("{} of {} merged pull requests have no type label ({}).".format(
                untyped, n, ", ".join(TYPES[:-1]) + " or " + TYPES[-1]))
        unlinked = n - totals["on_a_milestone_or_spec"]
        if unlinked:
            out.append("{} of {} merged pull requests are on no milestone and name no spec.".format(unlinked, n))
    milestones = doc["milestones"]
    if "closed" in milestones:
        for m in milestones["closed"]:
            if m["issues_open"]:
                out.append("{} closed with {} of {} still open.".format(
                    m["title"], m["issues_open"], m["issues_open"] + m["issues_closed"]))
            if m["due"] and m["closed"] > m["due"]:
                out.append("{} closed on {}, after its due date of {}.".format(m["title"], short(m["closed"]), short(m["due"])))
        for m in milestones["open"]:
            if m["due"] and m["due"] < today.isoformat():
                out.append("{} is past its due date of {}, with {} of {} still open.".format(
                    m["title"], short(m["due"]), m["issues_open"], m["issues_open"] + m["issues_closed"]))
    return out


def build(root, since, today, name=None, now=None):
    now = now or datetime.datetime.now().astimezone()
    repo = gh(root, "repo", "view", "--json", "nameWithOwner")
    name = (repo[0].get("nameWithOwner") if repo and isinstance(repo[0], dict) else None) or name or Path(root).name
    prs, matched, why = searched(gh(root, "api", "graphql", "--paginate",
                                    "-F", "q=repo:{{owner}}/{{repo}} is:pr is:merged merged:>={}".format(since),
                                    "-f", "query=" + QUERY, timeout=SEARCH_TIMEOUT))
    doc = {"schema": SCHEMA, "generated": now.isoformat(timespec="seconds"), "repo": name,
           "since": since, "until": today.isoformat(), "truncated": matched > LIMIT}
    if prs is None:
        for key in ("pull_requests", "totals", "by_person", "by_type", "by_day", "specs"):
            doc[key] = missing(why)
    else:
        rows = pull_request_rows(prs)
        doc.update(pull_requests=rows, totals=counts(rows), by_person=by_person(rows), by_type=by_type(rows),
                   by_day=by_day(rows, since, today), specs=spec_rows(rows))
    raw = flat(gh(root, "api", "repos/{owner}/{repo}/milestones?state=all&per_page=100", "--paginate"))
    doc["milestones"] = milestone_rows(raw, since) if raw is not None else missing("gh unavailable")
    raw = flat(gh(root, "release", "list", "--json", "name,tagName,publishedAt,isDraft", "--limit", str(RELEASES)))
    doc["releases"] = release_rows(raw, since) if raw is not None else missing("gh unavailable")
    text = merged_changelog(root)
    doc["changelog"] = changelog_rows(text, since) if text is not None else missing("no CHANGELOG.md on the default branch gh can read")
    doc["watch"] = watch(doc, today)
    return doc


def unavailable(section):
    return isinstance(section, dict) and section.get("value") is None and "why" in section


def duration(minutes):
    if minutes is None:
        return "n/a"
    return "{} min".format(round(minutes)) if minutes < 60 else "{:.1f} h".format(minutes / 60)


def cell(text):
    return str(text).replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", " ")


def chart(days):
    """A Mermaid bar chart of merges, a day a bar up to 31 days and a week a bar after that, with a line for the loop's."""
    if len(days) > 31:
        days = [{"day": days[i]["day"], "merged": sum(d["merged"] for d in days[i:i + 7]),
                 "loop_built": sum(d["loop_built"] for d in days[i:i + 7])} for i in range(0, len(days), 7)]
        unit = "week, starting the day shown"
    else:
        unit = "UTC day"
    top = max([d["merged"] for d in days] + [1])
    return "\n".join([
        "```mermaid",
        "xychart-beta",
        '    x-axis [{}]'.format(", ".join('"{}"'.format(short(d["day"], year=False)) for d in days)),
        '    y-axis "Merged" 0 --> {}'.format(top),
        "    bar [{}]".format(", ".join(str(d["merged"]) for d in days)),
        "    line [{}]".format(", ".join(str(d["loop_built"]) for d in days)),
        "```",
        "",
        "Each bar is the pull requests merged in a {}; the line is the ones the loop built.".format(unit),
    ])


def markdown(doc):
    out = ["# Work report: {}, {} to {}".format(doc["repo"], short(doc["since"]), short(doc["until"])), "", "## In numbers", ""]
    totals = doc["totals"]
    if unavailable(totals):
        out += ["Not available: {}.".format(totals["why"])]
    else:
        n = totals["merged"]
        out += ["| | |", "|---|---:|",
                "| Pull requests merged | {} |".format(n),
                "| Built by the loop | {} |".format(totals["loop_built"]),
                "| Built by hand | {} |".format(totals["hand_built"]),
                "| Issues closed by a merge | {} |".format(totals["issues_closed"]),
                "| Approved by someone other than the author | {} of {} |".format(totals["approved_by_another"], n),
                "| On a milestone or a spec | {} of {} |".format(totals["on_a_milestone_or_spec"], n),
                "| Median time from opened to merged | {} |".format(duration(totals["median_minutes_to_merge"])),
                "", "## Merges", "", chart(doc["by_day"])]
    out += ["", "## To watch", ""]
    out += ["- " + line for line in doc["watch"]] or ["Nothing in these numbers."]
    out += ["", "## Milestones", ""]
    releases, milestones = doc["releases"], doc["milestones"]
    reached = [] if unavailable(releases) else ["- {} · Release {}".format(short(r["published"]), r["name"]) for r in releases]
    if not unavailable(milestones):
        reached += ["- {} · {} closed: {} of {} done{}{}".format(
            short(m["closed"]), m["title"], m["issues_closed"], m["issues_closed"] + m["issues_open"],
            ", due " + short(m["due"]) if m["due"] else "", " " + m["url"] if m["url"] else "") for m in milestones["closed"]]
    out += reached or ["None reached in this period."]
    for section, what in ((releases, "Releases"), (milestones, "GitHub milestones")):
        if unavailable(section):
            out += ["", "{} not available: {}.".format(what, section["why"])]
    if not unavailable(milestones) and milestones["open"]:
        out += ["", "Open:", ""]
        out += ["- {}: {} of {} done{}".format(m["title"], m["issues_closed"], m["issues_closed"] + m["issues_open"],
                                                        ", due " + short(m["due"]) if m["due"] else "") for m in milestones["open"]]
    out += ["", "## By type", ""]
    if unavailable(doc["by_type"]):
        out += ["Not available: {}.".format(doc["by_type"]["why"])]
    else:
        out += ["| Type | Merged | By the loop |", "|---|---:|---:|"]
        out += ["| {} | {} | {} |".format(t["type"] or "untyped", t["merged"], t["loop_built"]) for t in doc["by_type"]]
    out += ["", "## By person", ""]
    if unavailable(doc["by_person"]):
        out += ["Not available: {}.".format(doc["by_person"]["why"])]
    elif not doc["by_person"]:
        out += ["Nobody merged a pull request in this period."]
    else:
        out += ["Loop-built pull requests count as the login the loop runs as. Reviews given counts the others' "
                "merged pull requests each login reviewed.", "",
                "| Login | Merged | By hand | By the loop | Issues closed | Approved by another | Reviews given | Median to merge |",
                "|---|---:|---:|---:|---:|---:|---:|---:|"]
        out += ["| {login} | {merged} | {hand_built} | {loop_built} | {issues_closed} | {approved_by_another} | {reviews_given} | {m} |".format(
            m=duration(p["median_minutes_to_merge"]), **p) for p in doc["by_person"]]
    out += ["", "## Specs", ""]
    if unavailable(doc["specs"]):
        out += ["Not available: {}.".format(doc["specs"]["why"])]
    elif not doc["specs"]:
        out += ["No closed issue named a spec. An issue names one with a `Spec:` line in its References."]
    else:
        out += ["- {}: {} pull request{}".format(s["spec"], len(s["pull_requests"]), "" if len(s["pull_requests"]) == 1 else "s")
                for s in doc["specs"]]
    out += ["", "## What shipped", ""]
    shipped = doc["changelog"]
    if unavailable(shipped):
        out += ["Not available: {}.".format(shipped["why"])]
    elif not shipped:
        out += ["No CHANGELOG.md entries in this period."]
    else:
        out += ["- {} · {}".format(short(e["date"]), e["name"]) for e in shipped[:SHIPPED_SHOWN]]
        if len(shipped) > SHIPPED_SHOWN:
            out += ["- and {} more in CHANGELOG.md".format(len(shipped) - SHIPPED_SHOWN)]
    if not unavailable(doc["pull_requests"]) and doc["pull_requests"]:
        out += ["", "## Pull requests", "",
                "| # | Title | Type | Author | Built | Reviewed by | Merged |", "|---:|---|---|---|---|---|---|"]
        out += ["| {} | {} | {} | {} | {} | {} | {} |".format(
            "[{}]({})".format(r["number"], r["url"]) if r["url"] else r["number"], cell(r["title"]), r["type"] or "untyped", r["author"],
            "loop" if r["loop_built"] else "hand",
            ", ".join(w + (" (approved)" if w in r["approved_by"] else "") for w in r["reviewers"]) or "nobody else",
            r["merged"]) for r in reversed(doc["pull_requests"])]
    return "\n".join(out) + "\n"


def main(argv=None, root=ROOT):
    now = datetime.datetime.now().astimezone()
    today = now.astimezone(datetime.timezone.utc).date()  # merges are dated in UTC, so the period is too
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=since_date, default=(today - datetime.timedelta(days=14)).isoformat(),
                        help="the first day to count, as YYYY-MM-DD (default: 14 days ago)")
    parser.add_argument("--project", help="a repo under projects/ to report on instead of this repo")
    parser.add_argument("--json", action="store_true", help="print the numbers as JSON instead of Markdown")
    args = parser.parse_args(argv)
    if args.since > today.isoformat():
        parser.error("--since {} is after today, {} in UTC".format(args.since, today.isoformat()))
    repo = Path(root)
    if args.project:
        repo = Path(root) / "projects" / args.project
        if Path(args.project).name != args.project or args.project in (".", "..") or not (repo / ".git").exists():
            parser.error("no repo at projects/{}".format(args.project))
    doc = build(repo, args.since, today, args.project, now)
    print(json.dumps(doc, indent=2) if args.json else markdown(doc), end="\n" if args.json else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
