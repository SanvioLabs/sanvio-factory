#!/usr/bin/env python3
"""Fetch a team's standards from Confluence for a CI review, before the prompt lists the standards.

Usage, from the Actions workspace, as .github/workflows/review-pr.yml runs it:
    python3 harness/scripts/fetch_standards.py

The config is standards/confluence.json in the factory checkout this file sits in, never one under base/ or
head/, which the pull request's repo controls. With no config it does nothing, and the review lists the
standards/ folder as it always has. The config names, none of it secret:

    {"api_base": "https://api.atlassian.com/ex/confluence/<cloud id>",
     "user": "the email of the account the token belongs to",
     "pages": ["753665", "753666"]}

api_base is https://api.atlassian.com/ex/confluence/<cloud id> for a scoped API token, which Atlassian
refuses at the site's own address, or https://<site>.atlassian.net for a classic one. Each page is read from
<api_base>/wiki/api/v2/pages/<id>?body-format=storage with basic auth, the user and $STANDARDS_TOKEN, turned
into Markdown, and written to standards/confluence/<id>.md, where the prompt step lists it with the rest.

The token is read from the environment and only sent to api_base, which has to be https (plain http is
allowed to 127.0.0.1 and localhost alone, for the tests). A page whose text holds the token is dropped, not
written. When any page doesn't load, one line saying how many and why goes to $RUNNER_TEMP/standards-fetch.txt
for the post step to put first in the comment. The line never holds the token or a response body. It always
exits 0, so the review runs and posts whatever happens here. Standard library only, Python 3.9.
"""
import base64
import html
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
TIMEOUT_SECONDS = 20  # each request, so a hung wiki can't use up the job's 30 minutes
MAX_PAGES = 50
PAGE_ID = re.compile(r"\d{1,20}")
LOCAL_HOSTS = ("127.0.0.1", "localhost")


class Markdown(HTMLParser):
    """Confluence's storage format, its XHTML with ac: macros, as plain Markdown: headings, paragraphs,
    lists, tables, links, emphasis, inline code and code macros. Anything else keeps its text."""

    BLOCKS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "table", "tr", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.lists = []
        self.href = []
        self.cell = None
        self.row = None
        self.rows = []
        self.code = 0
        self.macro = []

    def text(self, value):
        if self.cell is not None:
            self.cell.append(value)
        else:
            self.out.append(value)

    def newline(self, count=1):
        joined = "".join(self.out)
        have = len(joined) - len(joined.rstrip("\n"))
        if joined.strip():
            self.out.append("\n" * max(0, count - have))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.newline(2)
            self.text("#" * int(tag[1]) + " ")
        elif tag in ("p", "div", "blockquote"):
            if self.cell is None and not self.lists:
                self.newline(2)
        elif tag == "br":
            self.text("\n" if self.cell is None else " ")
        elif tag in ("ul", "ol"):
            if not self.lists:
                self.newline(2)
            self.lists.append([tag, 0])
        elif tag == "li":
            self.newline(1)
            kind = self.lists[-1] if self.lists else ["ul", 0]
            kind[1] += 1
            indent = "  " * max(0, len(self.lists) - 1)
            self.text(indent + ("{}. ".format(kind[1]) if kind[0] == "ol" else "- "))
        elif tag in ("strong", "b"):
            self.text("**")
        elif tag in ("em", "i"):
            self.text("*")
        elif tag == "code" and not self.code:
            self.text("`")
        elif tag == "pre":
            self.newline(2)
            self.text("```\n")
            self.code += 1
        elif tag == "a":
            self.href.append(attrs.get("href") or "")
            self.text("[")
        elif tag == "table":
            self.newline(2)
            self.rows = []
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
        elif tag == "ac:structured-macro":
            self.macro.append(attrs.get("ac:name", ""))

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "blockquote"):
            if self.cell is None and not self.lists:
                self.newline(2)
        elif tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
            if not self.lists:
                self.newline(2)
        elif tag in ("strong", "b"):
            self.text("**")
        elif tag in ("em", "i"):
            self.text("*")
        elif tag == "code" and not self.code:
            self.text("`")
        elif tag == "pre":
            self.code = max(0, self.code - 1)
            self.newline(1)
            self.text("```")
            self.newline(2)
        elif tag == "a":
            href = self.href.pop() if self.href else ""
            self.text("]({})".format(href) if href else "]")
        elif tag in ("td", "th"):
            if self.row is not None and self.cell is not None:
                self.row.append(" ".join("".join(self.cell).split()).replace("|", "\\|"))
            self.cell = None
        elif tag == "tr":
            if self.row is not None:
                self.rows.append(self.row)
            self.row = None
        elif tag == "table":
            if self.rows:
                width = max(len(row) for row in self.rows)
                rows = [row + [""] * (width - len(row)) for row in self.rows]
                lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
                lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
                self.out.append("\n".join(lines))
            self.rows = []
            self.newline(2)
        elif tag == "ac:structured-macro":
            if self.macro:
                self.macro.pop()

    def handle_data(self, data):
        if not self.code and self.cell is None:
            data = re.sub(r"\s+", " ", data)
            joined = "".join(self.out)
            if not joined or joined.endswith(("\n", " ")):
                data = data.lstrip()
        self.text(data)

    def unknown_decl(self, data):
        # <![CDATA[...]]>, which Confluence uses for a code macro's body.
        if data.startswith("CDATA["):
            body = data[len("CDATA["):]
            if self.macro and self.macro[-1] in ("code", "noformat"):
                self.newline(2)
                self.out.append("```\n" + body.rstrip("\n") + "\n```")
                self.newline(2)
            else:
                self.text(body)

    def markdown(self):
        text = "".join(self.out)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"


def to_markdown(storage):
    """Confluence storage format as Markdown."""
    parser = Markdown()
    parser.feed(storage)
    parser.close()
    return parser.markdown()


def load_config(path):
    """(config, None) or (None, why it can't be used). why never quotes the file."""
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "standards/confluence.json isn't valid JSON"
    if not isinstance(cfg, dict):
        return None, "standards/confluence.json isn't a JSON object"
    base, user, pages = cfg.get("api_base"), cfg.get("user"), cfg.get("pages")
    if not isinstance(base, str) or not base.strip():
        return None, "standards/confluence.json has no api_base"
    parsed = urllib.parse.urlparse(base.strip())
    local = parsed.hostname in LOCAL_HOSTS
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        return None, "api_base in standards/confluence.json isn't an https address"
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        return None, "api_base in standards/confluence.json has a query, a fragment or a login in it"
    if not isinstance(user, str) or not user.strip():
        return None, "standards/confluence.json has no user"
    if not isinstance(pages, list) or not pages:
        return None, "standards/confluence.json lists no pages"
    if len(pages) > MAX_PAGES:
        return None, "standards/confluence.json lists more than {} pages".format(MAX_PAGES)
    ids = [str(page) for page in pages]
    if not all(PAGE_ID.fullmatch(page) for page in ids):
        return None, "a page in standards/confluence.json isn't a numeric page id"
    return {"api_base": base.strip().rstrip("/"), "user": user.strip(), "pages": list(dict.fromkeys(ids))}, None


def fetch(cfg, page, token):
    """(title, storage) or raise OSError naming why, in words with no response body in them."""
    url = "{}/wiki/api/v2/pages/{}?body-format=storage".format(cfg["api_base"], page)
    login = base64.b64encode("{}:{}".format(cfg["user"], token).encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": "Basic " + login, "Accept": "application/json"})
    try:
        # api_base is https, or http to loopback for the tests alone: load_config checks it.
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # nosec B310
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        reason = {401: "the token was refused", 403: "the account can't read it", 404: "it wasn't found"}
        raise OSError("{} (HTTP {})".format(reason.get(err.code, "the request was refused"), err.code)) from None
    except (socket.timeout, TimeoutError):
        raise OSError("the request timed out") from None
    except urllib.error.URLError:
        raise OSError("Confluence couldn't be reached") from None
    except ValueError:
        raise OSError("the response wasn't a Confluence page") from None
    try:
        title = str(data.get("title") or "Confluence page {}".format(page))
        storage = data["body"]["storage"]["value"]
    except (AttributeError, KeyError, TypeError):
        raise OSError("the response wasn't a Confluence page") from None
    if not isinstance(storage, str):
        raise OSError("the response wasn't a Confluence page")
    return title, storage


def summary(failed, total, reasons):
    """The one line the comment opens with when any page didn't load."""
    why = "; ".join(dict.fromkeys(reasons))
    return ("{} of {} Confluence standards page{} didn't load ({}), so this review doesn't hold the change "
            "to {}.".format(failed, total, "" if total == 1 else "s", why, "them" if failed > 1 else "it"))


def run(root, environ):
    """Fetch every page the config names into root/standards/confluence/. Returns the line for the comment,
    or None when nothing went wrong or there's no config."""
    path = root / "standards" / "confluence.json"
    if not path.is_file():
        print("No standards/confluence.json, so no standards are fetched from Confluence.")
        return None
    cfg, why = load_config(path)
    if cfg is None:
        return "The Confluence standards weren't fetched: {}.".format(why)
    token = environ.get("STANDARDS_TOKEN", "")
    total = len(cfg["pages"])
    if not token:
        return summary(total, total, ["no STANDARDS_TOKEN secret is set"])
    out = root / "standards" / "confluence"
    out.mkdir(parents=True, exist_ok=True)
    failed, reasons = 0, []
    for page in cfg["pages"]:
        try:
            title, storage = fetch(cfg, page, token)
        except OSError as err:
            failed += 1
            reasons.append(str(err))
            print("::warning::Confluence page {} didn't load: {}".format(page, err))
            continue
        body = to_markdown(storage)
        text = "# {}\n\nFetched from Confluence page {} for this review.\n\n{}".format(
            " ".join(html.unescape(title).split()), page, body)
        if token in text or token in storage:
            failed += 1
            reasons.append("a page held the token, so it was dropped")
            print("::warning::Confluence page {} held the token, so it was dropped.".format(page))
            continue
        (out / "{}.md".format(page)).write_text(text, encoding="utf-8")
        print("Fetched Confluence page {}.".format(page))
    return summary(failed, total, reasons) if failed else None


def main():
    try:
        line = run(HERE.parent, os.environ)
    except Exception as err:  # the review posts whatever happens here
        line = "The Confluence standards weren't fetched: the fetch failed ({}).".format(type(err).__name__)
    if line:
        print("::warning::" + line)
        temp = os.environ.get("RUNNER_TEMP")
        if temp:
            try:
                Path(temp, "standards-fetch.txt").write_text(line + "\n", encoding="utf-8")
            except OSError:
                print("::warning::Couldn't write standards-fetch.txt, so the comment won't open with that line.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
