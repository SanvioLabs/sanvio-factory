#!/usr/bin/env python3
"""Check the CI review's JSON report against its schema, and write the Markdown comment from it.

Usage, from the Actions workspace, as .github/workflows/review-pr.yml runs it:
    python3 harness/scripts/review_report.py

It reads $RUNNER_TEMP/report.json, which the model wrote, and the schema at skills/review-pr/report.schema.json
in the factory checkout this file sits in (harness/), never one under base/ or head/, which the pull request's
repo controls. It writes $RUNNER_TEMP/report.md. A report that isn't JSON, or doesn't match the schema, posts no
findings: report.md then holds only UNREADABLE.

The comment is built here, not by the model: fixed text, then one line per finding, each model-written field
put through clean() first, then the verdict. So a finding can't open a heading, forge the comment's marker or
trailer, mention someone, show an image or render HTML.

The validator handles only the keywords in SUPPORTED, and refuses a schema with any other, so a keyword added to
the schema can't go unenforced without a test failing. Standard library only.
"""
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = HERE.parent / "skills" / "review-pr" / "report.schema.json"
SUPPORTED = ("type", "enum", "required", "properties", "additionalProperties", "items", "minLength", "minimum")
TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool}
UNREADABLE = "The review's report couldn't be read, so no findings are posted."
NOT_RUN = ("This review didn't run the tests: it has no shell, and the tests run in the pull request's "
           "other checks.")
# The last line of a rendered report, which a grade in another job reads back (rendered_verdict).
VERDICT_LINE = "Verdict: {}"
FENCE = re.compile(r"\A```json[ \t]*\n(.*)\n```\Z", re.S)
# Every @ in a run before a name, so @@name leaves no @; ASCII word characters only, so é@name loses its @ too.
MENTION = re.compile(r"(?<!\w)@+(?=\w)", re.ASCII)


class Unsupported(ValueError):
    """The schema uses a keyword validate() doesn't handle."""


def keywords(schema):
    """Every keyword the schema uses, at any depth. A name under properties is a property, not a keyword."""
    found = set(schema)
    for name, value in schema.items():
        if name == "properties":
            for sub in value.values():
                found |= keywords(sub)
        elif name in ("items", "additionalProperties") and isinstance(value, dict):
            found |= keywords(value)
    return found


def is_type(data, name):
    if name not in TYPES:
        raise Unsupported("type {!r}".format(name))
    if isinstance(data, bool) and name in ("integer", "number"):
        return False  # bool is an int to Python, never to JSON
    return isinstance(data, TYPES[name])


def validate(data, schema, where="$"):
    """Raise ValueError when data doesn't match schema. The message names the place, never the value, since the
    value is the model's and the message goes to the log."""
    # At the top, every keyword at any depth, so one under a property the data leaves out is still refused.
    unknown = sorted((keywords(schema) if where == "$" else set(schema)) - set(SUPPORTED))
    if unknown:
        raise Unsupported("the schema uses {}, which this validator doesn't handle".format(", ".join(unknown)))
    if "type" in schema and not is_type(data, schema["type"]):
        raise ValueError("{} isn't of type {}".format(where, schema["type"]))
    if "enum" in schema and not any(data == item and type(data) is type(item) for item in schema["enum"]):
        raise ValueError("{} isn't one of the allowed values".format(where))
    if "minLength" in schema and isinstance(data, str) and len(data) < schema["minLength"]:
        raise ValueError("{} is shorter than {}".format(where, schema["minLength"]))
    if "minimum" in schema and is_type(data, "number") and data < schema["minimum"]:
        raise ValueError("{} is less than {}".format(where, schema["minimum"]))
    if isinstance(data, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", ()):
            if name not in data:
                raise ValueError("{} has no {}".format(where, name))
        for name, value in data.items():
            if name in properties:
                validate(value, properties[name], "{}.{}".format(where, name))
            elif schema.get("additionalProperties", True) is False:
                raise ValueError("{} has a key the schema doesn't list".format(where))
            elif isinstance(schema.get("additionalProperties"), dict):
                validate(value, schema["additionalProperties"], "{}[a key]".format(where))
    if isinstance(data, list) and "items" in schema:
        for number, item in enumerate(data):
            validate(item, schema["items"], "{}[{}]".format(where, number))


def check(text, schema):
    """(the report, None) or (None, why it can't be read)."""
    text = text.strip()
    fenced = FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):  # nested too deep for the parser counts as not JSON
        return None, "it isn't JSON"
    try:
        validate(data, schema)
    except ValueError as error:
        return None, str(error)
    return data, None


def load(text, schema):
    """The report, or None when text isn't JSON or doesn't match schema. One ```json fence around the whole of
    it is taken off, and nothing else."""
    return check(text, schema)[0]


def clean(field):
    """A model-written field as text that renders as itself on one line: no line breaks, so it can't start a
    heading, a marker or a trailer; &, < and > escaped, so no HTML; no ![, so no image; and no @ before a
    name, so nobody is mentioned. An @ with a word character before it, as in a@b.com, stays."""
    text = " ".join(str(field).splitlines())
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("![", "! [")
    return MENTION.sub("", text)


def render(report):
    """The comment's report, as Markdown."""
    lines = [NOT_RUN, ""]
    findings = report["findings"]
    for finding in findings:
        place = clean(finding["file"])
        if "line" in finding:
            place += ":{}".format(int(finding["line"]))
        rule = clean(finding["rule"]).strip()
        lines.append("- **{}** {}{}: {}".format(clean(finding["severity"]), place,
                                                " ({})".format(rule) if rule else "", clean(finding["summary"])))
    if not findings:
        lines.append("No findings.")
    lines += ["", VERDICT_LINE.format(clean(report["verdict"]))]
    return "\n".join(lines) + "\n"


def rendered_verdict(text, schema):
    """The verdict render() wrote on a report's last line, read back from that report as a comment carries it,
    for a grade in another job than the check: one of the schema's verdicts, on a line exactly as render()
    writes it, or unreadable. A finding can't forge the line, since clean() keeps each finding on its own
    "- " line, and UNREADABLE, or a last line of anything else, reads as unreadable."""
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    allowed = ((schema.get("properties") or {}).get("verdict") or {}).get("enum") or ()
    for verdict in allowed:
        if lines and isinstance(verdict, str) and lines[-1] == VERDICT_LINE.format(verdict):
            return verdict
    return "unreadable"


def schema():
    """The factory's own report schema, from beside this file."""
    return json.loads(SCHEMA.read_text())


def main(environ=None):
    environ = os.environ if environ is None else environ
    temp = Path(environ.get("RUNNER_TEMP", "."))
    report = None
    try:
        text = (temp / "report.json").read_text()
    except (OSError, ValueError) as error:  # missing, or not text
        why = "report.json couldn't be read ({})".format(type(error).__name__)
    else:
        try:
            rules = schema()
        except (OSError, ValueError) as error:  # missing, or not JSON: fail closed
            why = "{} couldn't be read ({})".format(SCHEMA.name, type(error).__name__)
        else:
            report, why = check(text, rules)
    text = render(report) if report is not None else UNREADABLE + "\n"
    if report is None:
        print("::warning::{} The check said: {}.".format(UNREADABLE, why))
    try:
        (temp / "report.md").write_text(text)
    except OSError as error:
        print("::error::report.md couldn't be written: {}".format(error))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
