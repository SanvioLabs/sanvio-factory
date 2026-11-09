"""The required checks on a returned pull request, and the GitHub reads behind them.

factories.py hands an issue to a factory and reviews what comes back. This module answers one question
for it: do the required checks on the pull request's head pass, read from the base repo, and was none
of the known ways a factory could produce its own checks found? check_report is that answer, and
required_checks is what dispatch warns from. It reads GitHub through forge.py, and the imports run one way:
factories.py imports this module and forge.py, and this module imports only forge.py.
"""

import base64
from urllib.parse import quote

from forge import LOGIN, cant_use, clash, gh, gh_json, not_found, one_line, parsed, repo_args, said, shown, skipped

# What factories.py may import. A test holds its import to these, so the interface stays this narrow.
__all__ = ("CI_PATHS", "check_report", "checks_line", "default_branch", "not_factory_fork", "required_checks")


class Unread(str):
    """A reason that is a read that failed, not something a read showed: check_report counts them as unread,
    whatever their words."""

WORST = {"passing": 0, "pending": 1, "failing": 2}
ACTIONS = 15368  # GitHub Actions' app id
# What CI runs from, at the top of a repo: a change to any of these lets a pull request write its own checks.
# A step's ci_paths adds to these and never takes one away.
CI_PATHS = (".github", ".circleci", ".buildkite", "Jenkinsfile", "azure-pipelines.yml", "azure-pipelines.yaml",
            ".gitlab-ci.yml", ".travis.yml", "appveyor.yml", ".cirrus.yml", ".drone.yml", "bitbucket-pipelines.yml",
            # and what a check-posting app reads from the pull request's own head
            ".pre-commit-config.yaml", "codecov.yml", ".codecov.yml", "netlify.toml", "vercel.json")


def status_state(state):
    """passing, pending or failing, for a commit status's state."""
    state = (state or "").upper()
    return "passing" if state == "SUCCESS" else "pending" if state in ("", "PENDING", "EXPECTED") else "failing"


def rows(out):
    """The lines of a paginated --jq ... | @json answer, one row each. Split at \\n alone: @json leaves U+2028
    and its kind as they are, and splitlines() would break a row there."""
    return [line for line in out.split("\n") if line.strip()]


def run_state(status, conclusion):
    """passing, pending or failing, for a check run: skipped never passes a required check, since then nothing
    checked the commit."""
    if (status or "").upper() != "COMPLETED":
        return "pending"
    return "passing" if (conclusion or "").upper() in ("SUCCESS", "NEUTRAL") else "failing"


def check_runs(repo, sha):
    """[(name, app id, state, check suite id)] for each check run on commit sha in repo itself, or None when they can't be
    read. Read from the base repo, never the pull request's rollup, which can show a fork's own runs; and a run
    whose page isn't in the repo is left out, so only what the repo's own checks posted counts. Every run is read
    (filter=all), and the newest of each name in each check suite stands for it, so a re-run counts within its
    suite and a passing run in another suite never hides a failing one."""
    code, out, _ = gh("api", "--paginate", "repos/{}/commits/{}/check-runs?filter=all&per_page=100".format(repo, sha),
                        "--jq", ".check_runs[] | [.name, .app.id, .status, .conclusion, .html_url, .check_suite.id, .id]"
                                " | @json")
    if code:
        return None
    newest, home = {}, "https://github.com/{}/".format(repo).lower()
    for line in rows(out):
        try:
            name, app, status, conclusion, url, suite, number = parsed(line, marked=False)
        except (ValueError, TypeError):
            cant_use("a check run that isn't the seven fields asked for")
            return None
        if not isinstance(url, str) or not url.lower().startswith(home):
            skipped("the {} check run's page isn't in {}, so it doesn't count".format(shown(name), repo))
            continue
        if not isinstance(number, int) or isinstance(number, bool):
            cant_use("the {} check run has no id".format(shown(name)))
            return None
        key = (name, app, suite)
        if key not in newest or number > newest[key][0]:
            newest[key] = (number, run_state(status, conclusion))
    return [(name, app, state, suite) for (name, app, suite), (_, state) in newest.items()]


def commit_statuses(repo, sha):
    """[(context, state, who posted it)] for every commit status on sha in repo, newest first, as GitHub
    lists them, or None when they can't be read. One read serves both the checks and who posted them."""
    code, out, _ = gh("api", "--paginate", "repos/{}/commits/{}/statuses?per_page=100".format(repo, sha),
                        "--jq", ".[] | [.context, .state, .creator.node_id] | @json")
    if code:
        return None
    found = []
    for line in rows(out):
        try:
            context, state, creator = parsed(line, marked=False)
        except (ValueError, TypeError):
            cant_use("a commit status that isn't the three fields asked for")
            return None
        found.append((context, status_state(state), creator))
    return found


def newest_statuses(statuses):
    """[(context, state)], the newest status of each context: the first GitHub lists."""
    newest = {}
    for context, state, _ in statuses:
        newest.setdefault(context, state)
    return list(newest.items())


def can_write(repo, login):
    """Why login's permission on repo makes its checks not independent, or None when it's read or triage.
    Fails closed: a permission that can't be read is a reason, and a login that isn't one never reaches a path."""
    if not isinstance(login, str) or not LOGIN.fullmatch(login):
        return "{!r} isn't a GitHub login, so its access to {} wasn't read".format(login, repo)
    found, why = gh_json("api", "repos/{}/collaborators/{}/permission".format(repo, login),
                         "--jq", "[.permission, .role_name]", shape=list)
    permission, role = found if found is not None and len(found) == 2 else (None, None)
    if permission in ("read", "none") and role in ("read", "triage", "none", None):
        return None
    if not isinstance(permission, str):
        if not why:
            cant_use("no permission came back")
        return Unread("couldn't read {}'s permission on {}: {}".format(login, repo, why or "no permission came back"))
    return "{} has {} access to {}, so it could post a passing status on its own commit".format(
        login, role or permission, repo)


def runs_pull_request_code(repo, base):
    """Why a workflow on the base branch makes Actions checks not independent, or None: a pull_request_target
    or workflow_run workflow can run a pull request's code with a token that posts checks as Actions."""
    ref = quote(base, safe="")
    code, out, err = gh("api", "repos/{}/contents/.github/workflows?ref={}".format(repo, ref),
                        "--jq", '.[] | select(.type != "dir") | .path')
    if code:
        return None if not_found(out) else Unread("couldn't read {}'s workflows: {}".format(base, said(code, out, err)))
    for path in out.split():
        code, text, err = gh("api", "repos/{}/contents/{}?ref={}".format(repo, quote(path), ref), "--jq", ".content")
        try:
            text = base64.b64decode(text).decode("utf-8", "replace") if not code and text.strip() else None
        except ValueError:
            text = None
        if text is None:
            if not code:
                cant_use("{}'s content wasn't base64".format(shown(path)))
            return Unread("couldn't read {} on {}".format(shown(path), base))
        for trigger in ("pull_request_target", "workflow_run"):
            if trigger in text:
                return ("{} on {} runs on {}, which can run a pull request's code with a token that posts checks "
                        "as GitHub Actions".format(shown(path), base, trigger))
    return None


def check_report(record, head, current=None):
    """The required checks on the pull request's head, apart from any verdict: a result and its detail, by
    what factories/README.md's *Getting to ready* says ready requires."""
    repo, sha = record["repo"], head.get("headRefOid", "")
    name, branch, required, problem = required_checks(repo, record["base"])
    if problem:
        return unknown(problem)
    listed = sorted(one_line(check) for check in required)  # what a return before the clash check records
    ci, problem = ci_changed(record, sha)
    if problem:
        return unknown(problem)
    if ci:
        return {"result": "changes CI", "required": listed, "failing": [], "pending": [], "unread": False,
                "note": "it changes {}, which CI runs from, so its own checks can't stand as independent".format(
                    ", ".join(ci))}
    if current is None:  # read again: a review just took minutes, and the head may have moved
        current, problem = pr_owner(record)
        if problem:
            return unknown(problem)
    if current.get("headRefOid") != sha:
        return {"result": "checks pending", "required": listed, "failing": [], "pending": [], "unread": False,
                "note": "the head moved since the review, to {}; the next status reviews it".format(
                    str(current.get("headRefOid"))[:7])}
    if current.get("baseRefName") != record["base"]:  # retargeted while the review ran, or unsaid: read as moved
        return {"result": "checks pending", "required": listed, "failing": [], "pending": [], "unread": False,
                "note": "its base changed since the review, to {}; the next status reads it again".format(
                    shown(current.get("baseRefName") or "a base GitHub didn't say"))}
    runs = check_runs(repo, sha)
    if runs is None:
        return unknown("couldn't read the check runs on its head from {}".format(repo))
    statuses = commit_statuses(repo, sha)
    if statuses is None:
        return unknown("couldn't read the commit statuses on its head from {}".format(repo))
    # Read as GitHub sent them, and marked only now: two names that read the same once marked could pass for
    # each other, so neither stands.
    pair = clash(list(required) + [run[0] for run in runs] + [status[0] for status in statuses])
    if pair:
        return unknown("two check names GitHub sent, {} and {}, read the same once marked, so neither can stand "
                       "for the other".format(*(repr(shown(name)) for name in pair)))
    required = {one_line(check): apps for check, apps in required.items()}
    runs = [(one_line(name), app, state, suite) for name, app, state, suite in runs]
    statuses = [(one_line(context), state, creator) for context, state, creator in statuses]
    states = {}
    for check, apps in required.items():
        if apps:  # each app it's pinned to has to pass it
            seen = [max([state for run, app, state, _ in runs if run == check and app == want] or ["pending"],
                        key=WORST.get) for want in apps]
        else:
            seen = ([state for run, app, state, _ in runs if run == check] +
                    [state for context, state in newest_statuses(statuses) if context == check])
        states[check] = max(seen, key=WORST.get) if seen else "pending"  # the worst entry of that name
    failing = sorted(check for check, state in states.items() if state == "failing")
    pending = sorted(check for check, state in states.items() if state == "pending")
    note, unread = "", False
    if failing or pending:
        result = "checks failing" if failing else "checks pending"
    elif not required:
        result = "no required check"
        note = "nothing independent checked it: {}'s {} requires no status check".format(name, branch)
    else:
        note, unread = not_independent(record, current, required, runs, statuses)
        result = "checks pass, not independent" if note else "ready for a person"
        if not note:
            note = ("none of the ways a factory could produce its own checks was found, but GitHub can't show who "
                    "posted a status through an integration, or which workflow set or edited a check run's result, "
                    "so read the diff")
    return {"result": result, "required": sorted(required), "failing": failing, "pending": pending, "note": note,
            "unread": unread}


def pr_owner(record):
    """(the pull request's head commit, whether it's a fork, and the fork's owner, as GitHub has them now,
    None), or ({}, why they couldn't be read)."""
    found, why = gh_json("pr", "view", str(record["pr"]), *repo_args(record["repo"]),
                         "--json", "headRefOid,baseRefName,isCrossRepository,headRepositoryOwner")
    if why:
        return {}, "couldn't read pull request #{} again: {}".format(record["pr"], why)
    return found, None


def not_independent(record, current, required, runs, statuses):
    """Why passing checks don't stand as independent of the factory, or '' when they do: each condition
    factories/README.md's *Getting to ready* lists under independent, read here. Failing to read one is a
    reason, and every reason found is named, so one status shows all there is to change. Returns that line,
    or '', and whether any reason was a read that failed."""
    factory, login = record["factory"], record.get("factory_login")
    if not record.get("factory_id"):
        return ("the run records no account for {}, so nothing shows the pull request is the factory's; a person "
                "decides what the checks are worth".format(login or factory)), False
    if not_factory_fork(record, current):
        return ("it's from a branch {0} could push to, or not from the fork of the account dispatch recorded, so "
                "{0} could have posted a passing status itself; a person decides what the checks are worth".format(
                    factory)), False
    repo, sha = record["repo"], current["headRefOid"]
    why = [reason for reason in (
        can_write(repo, login),
        actions_provenance(repo, sha, record["factory_id"], [run for run in runs if run[0] in required]),
        factory_statuses(statuses, record["factory_id"], login),
        shared_head(record, sha),
        fork_write_tokens(repo),
        runs_pull_request_code(repo, record["base"])) if reason]
    if not why:
        return "", False
    return ("{}; a person decides what the checks are worth".format("; ".join(why)),
            any(isinstance(reason, Unread) for reason in why))


def not_factory_fork(record, pr):
    """None when pull request pr comes from a fork owned by the account dispatch recorded: factory_login, and
    factory_id where the run has one. Otherwise why not. Whether a branch in the repo will do is the caller's
    call: a run follows one, and its checks never stand as independent."""
    login, owner = record.get("factory_login"), pr.get("headRepositoryOwner") or {}
    if pr.get("isCrossRepository") is not True:
        return "it's from a branch in the repo, not a fork"
    if not login:
        return "it's from a fork, and the step names no factory_login to say whose fork is the factory's"
    if str(owner.get("login") or "").lower() != login.lower():
        return "it's from {}'s fork, not {}'s".format(owner.get("login") or "an unknown owner", login)
    if record.get("factory_id") and owner.get("id") != record["factory_id"]:
        return "it's from a fork owned by an account that isn't the one {} named at dispatch".format(login)
    return None


def actions_provenance(repo, sha, account, runs):
    """Why an Actions run of a required check doesn't count, or None: each has to come from the factory's
    fork's own pull_request run. Any other event (a comment, a push, pull_request_target, a workflow on another
    branch) can run the pull request's code with a token that posts checks as Actions."""
    actions = [run for run in runs if run[1] == ACTIONS]
    if not actions:
        return None
    code, out, err = gh("api", "--paginate", "repos/{}/actions/runs?head_sha={}&per_page=100".format(repo, sha),
                        "--jq", ".workflow_runs[] | [.check_suite_id, .event, .head_repository.owner.node_id] | @json")
    if code:
        return Unread("couldn't read the workflow runs behind its checks: {}".format(said(code, out, err)))
    made = {}
    for line in rows(out):
        try:
            suite, event, owner = parsed(line)
        except (ValueError, TypeError):
            return Unread("couldn't read the workflow runs behind its checks: " + cant_use(
                "a workflow run that isn't the three fields asked for"))
        made[suite] = (event, owner)
    for name, _, _, suite in actions:
        event, owner = made.get(suite, (None, None))
        if event is None:
            return "no workflow run could be found behind the {} check".format(shown(name))
        if event != "pull_request" or owner != account:
            return "the {} check came from a {} run{}, not the fork's own pull request".format(
                shown(name), shown(event), "" if owner == account else " from another repo")
    return None


def factory_statuses(statuses, account, login):
    """Why a commit status on the head doesn't count, or None: none may be the factory account's own."""
    for context, _, creator in statuses:
        if creator == account:
            return "{} posted the {} status on its own commit".format(login, shown(context))
    return None


def shared_head(record, sha):
    """Why the head's checks may be another pull request's, or None: check runs belong to a commit, so a pull
    request with the same head into another branch, or this one's base changed and back, could have produced
    them under that branch's workflows."""
    found, why = gh_json("pr", "list", *repo_args(record["repo"]), "--state", "all", "--search", sha,
                         "--json", "number,headRefOid", "--limit", "100", shape=list)
    if why:
        return Unread("couldn't read which pull requests share its head: {}".format(why))
    for pr in found:
        if not isinstance(pr, dict):
            skipped("a pull request that isn't an object")
    others = sorted(pr.get("number") for pr in found
                    if isinstance(pr, dict) and pr.get("headRefOid") == sha and pr.get("number") != record["pr"])
    if others:
        return "pull request {} shares its head, so its checks may be that one's".format(
            ", ".join("#{}".format(number) for number in others))
    code, out, err = gh("api", "--paginate", "repos/{}/issues/{}/timeline?per_page=100".format(record["repo"], record["pr"]),
                        "--jq", '.[] | select(.event == "base_ref_changed") | .event')
    if code:
        return Unread("couldn't read whether its base changed: {}".format(said(code, out, err)))
    if out.strip():
        return "its base branch was changed, so its checks may have run against another branch's workflows"
    return None


def fork_write_tokens(repo):
    """Why a repo that isn't public may hand a fork's own code a write token or its secrets, or None."""
    code, out, err = gh("api", "repos/{}".format(repo), "--jq", ".visibility")
    if code:
        return Unread("couldn't read whether {} is public: {}".format(repo, said(code, out, err)))
    if out.strip() == "public":
        return None
    found, why = gh_json("api", "repos/{}/actions/permissions/fork-pr-workflows-private-repos".format(repo),
                         "--jq", "[.send_write_tokens_to_workflows, .send_secrets_and_variables]", shape=list)
    tokens, secrets = found if found is not None and len(found) == 2 else (None, None)
    if tokens is False and secrets is False:
        return None
    if not isinstance(tokens, bool) or not isinstance(secrets, bool):
        if not why:
            cant_use("no setting came back")
        return Unread("couldn't read whether {} sends fork workflows a write token or its secrets: {}".format(
            repo, why or "not answered"))
    return ("{} sends fork pull request workflows {}, so the fork's own code could post its checks".format(
        repo, "a write token" if tokens else "its secrets"))


def ci_changed(record, sha):
    """([each of the record's ci_paths that differs between the merge base and sha], None), or
    ([], why that couldn't be read). Compared by tree, so a rename or a removal counts as a change."""
    paths = sorted(set(CI_PATHS) | set(record.get("ci_paths") or []))  # today's defaults, whenever dispatched
    found, why = gh_json("api", "repos/{}/compare/{}...{}".format(record["repo"], quote(record["base"], safe=""), sha))
    base = (found or {}).get("merge_base_commit") or {}
    base = base.get("sha") if isinstance(base, dict) else None
    if not isinstance(base, str) or not base:
        if not why:
            cant_use("no merge base came back")
        return [], "couldn't find where it leaves {}, so it can't be shown to leave CI alone: {}".format(
            record["base"], why or "no merge base")
    tops = []
    for commit in (base, sha):
        found, why = gh_json("api", "repos/{}/git/trees/{}".format(record["repo"], commit), marked=False)
        entries = (found or {}).get("tree")
        if why or found.get("truncated") or not isinstance(entries, list) or not all(
                isinstance(entry, dict) and "path" in entry and "sha" in entry for entry in entries):
            if not why:
                cant_use("a truncated tree, or entries with no path or sha")
            return [], "couldn't read the files at {}, so it can't be shown to leave CI alone{}".format(
                commit[:7], ": " + why if why else "")
        names = [entry["path"] for entry in entries]
        if clash(names) or len(set(names)) != len(names):
            cant_use("two top-level names that read the same")
            return [], "two top-level names at {} read the same once marked, so it can't be shown to leave CI " \
                       "alone".format(commit[:7])
        tops.append({entry["path"]: entry["sha"] for entry in entries})
    return sorted(path for path in paths if tops[0].get(path) != tops[1].get(path)), None


def unknown(why):
    return {"result": "checks unknown", "required": [], "failing": [], "pending": [], "note": why, "unread": True}


def checks_line(checks):
    detail = ("failing " + ", ".join(map(shown, checks["failing"])) if checks["failing"] else
              "waiting on " + ", ".join(map(shown, checks["pending"])) if checks["pending"] else "")
    return "; ".join(part for part in (checks["result"], detail, checks["note"]) if part)


def default_branch(repo):
    """(GitHub's OWNER/NAME for repo, or None when none came back, its default branch, None) for repo, or this
    clone's repo when it's None, or (None, None, why it couldn't be read). The one read of a repo's default
    branch: dispatch records it, and the required checks are read from it under GitHub's own name."""
    data, why = gh_json("repo", "view", *([repo] if repo else []), "--json", "nameWithOwner,defaultBranchRef")
    try:
        branch = data["defaultBranchRef"]["name"]
    except (TypeError, KeyError):
        if not why:
            cant_use("no default branch came back")
        return None, None, why or "gh's answer had no name or default branch"
    name = data.get("nameWithOwner")
    if not isinstance(name, str) or not name:
        cant_use("no name came back")
        name = None
    return name, branch, None


def required_checks(repo, base=None):
    """(repo name, the branch, {required check: {each app it's pinned to}, empty for any app}, None), or
    (..., why they couldn't be read), for base, or the default branch when base is None. Classic protection
    and rulesets both count, and every pin is kept. The checks are named as GitHub sent them: check_report
    refuses two that clash and marks them after, and dispatch's warning prints none.

    Read from the branch, which anyone who can read the repo sees, and never from its protection endpoint,
    which answers a 404 to anyone without admin rights whether the branch is protected or not. A failed gh api
    call prints its error as JSON on stdout, so each answer is parsed only when gh exited 0."""
    name, default, why = default_branch(repo)
    if why or not name:
        return repo or "this repo", "its default branch", {}, "couldn't read the repo: {}".format(
            why or "gh's answer had no name or default branch")
    branch, found = base or default, {}
    data, why = gh_json("api", "repos/{}/branches/{}".format(name, quote(branch, safe="")), marked=False)
    if why:
        return name, branch, found, "couldn't read its branch: {}".format(why)
    def require(check, app):
        if not isinstance(check, str) or not check:
            skipped("a required check with no name")
        else:
            pins = found.setdefault(check, set())
            if isinstance(app, int) and not isinstance(app, bool) and app > 0:  # -1 or none: any app
                pins.add(app)

    protection = data.get("protection") if data.get("protected") else {"enabled": False}
    if not isinstance(protection, dict):
        cant_use("its protection isn't an object")
        return name, branch, found, "couldn't read which checks its protected branch requires"
    if protection.get("enabled") is not False:
        checks = protection.get("required_status_checks")
        if not isinstance(checks, dict):
            cant_use("its required status checks aren't an object")
            return name, branch, found, "couldn't read which checks its protected branch requires"
        for check in checks.get("contexts") or []:
            require(check, None)
        for check in checks.get("checks") or []:
            if isinstance(check, dict):
                require(check.get("context"), check.get("app_id"))
    # Classic protection off leaves the rulesets to decide: a branch can be protected by them alone.
    code, out, err = gh("api", "--paginate", "repos/{}/rules/branches/{}?per_page=100".format(name, quote(branch, safe="")),
                        "--jq", '.[] | select(.type == "required_status_checks")'
                                ' | .parameters.required_status_checks[] | @json')
    if code:
        if not not_found(out):
            return name, branch, found, "couldn't read its rulesets: {}".format(said(code, out, err))
    else:
        for line in rows(out):
            try:
                check = parsed(line, marked=False)
            except ValueError:
                return name, branch, found, "couldn't read its rulesets: " + cant_use("a rule that isn't JSON")
            if isinstance(check, dict):
                require(check.get("context"), check.get("integration_id"))
            else:
                skipped("a required check that isn't an object")
    return name, branch, found, None
