"""Deployed routes from API Gateway v2 `route_key` values in Terraform or OpenTofu.

Reads only literal keys, one `route_key = "METHOD /path"` per line, in `.tf` and `.tofu` files under
the configured paths. Comments, string contents and heredoc bodies are masked before anything is
read, so a brace or a `route_key` inside one changes nothing. Everything it cannot read fails
closed, because the check cannot say which routes it serves and refuses to guess:

- an interpolated or computed key (`${...}`, `each.key`, `local.x`, a conditional) or the
  `$default` catch-all;
- a `route_key` sharing its line with other syntax, or written as a quoted attribute name;
- JSON Terraform (`*.tf.json`, `*.tofu.json`) anywhere in the repository;
- a route defined outside the configured paths;
- a module from anywhere but a plain local folder (`./` or `../`, not into `.terraform` or
  `node_modules`);
- an unterminated string, comment or heredoc, or a heredoc marker it cannot read: the mask would
  lose its place, so it refuses rather than guess where the code resumes;
- anywhere in the repository, a front door this adapter does not read: a Lambda function URL, a
  REST API (v1) resource, or an HTTP API built from an OpenAPI `body` or a quick-create `target`.

This is a pattern reader, not an HCL parser, so three invariants make any misreading fail closed
rather than hide code: characters Python and Terraform read differently (controls, Unicode spaces,
format characters, combining marks, `\\u` escapes) are refused before masking; every `resource`
or `module` that starts a line must parse as a header; and wherever the raw text starts a block
or sets `route_key`, `source`, `body` or `target`, the mask must not have blanked it, outside a
line that is a `#` or `//` comment. A reader that holds against a deliberate adversary, rather
than a mistake, is the follow-up to SPEC-034. Projects that build routes dynamically use the
dispatch adapter instead.
"""
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Iterator, List, Set, Tuple

from . import AdapterError, parse_route_key

SUFFIXES = (".tf", ".tofu")
JSON_SUFFIXES = (".tf.json", ".tofu.json")
SKIP = {".terraform", ".git", "node_modules"}  # derived or vendored; a module sourced from one is refused
LABEL = r'("[^"\n]*"|[^\s{}"=]+)'
# `resource` or `module` starting a line, not followed by what an attribute or a reference would be
# (`resource = ...`, `module.x.arn`): a block header, or something the check refuses.
NOT_HEADER = r'(?![^\S\n]*[=.,)\]\[}:?+*/%<>!&|-])'
BLOCK_START = re.compile(r'^[^\S\n]*(resource|module)\b' + NOT_HEADER, re.M)
RESOURCE_HEADER = re.compile(r'resource[^\S\n]+' + LABEL + r'[^\S\n]+' + LABEL + r'[^\S\n]*\{')
MODULE_HEADER = re.compile(r'module[^\S\n]+' + LABEL + r'[^\S\n]*\{')
ANY_HEADER = re.compile(r'[A-Za-z_][\w-]*(?:[^\S\n]+(?:"[^"\n]*"|[^\s{}"=]+))*[^\S\n]*\{')
PLAIN_SOURCE = re.compile(r'\.{1,2}/[\w./-]*')
# Resource types that deploy a route, an API or a URL by another road than the v2 resources read
# here: CloudFormation, Cloud Control, the awscc provider, and any API Gateway or function URL type.
OTHER_ROADS = re.compile(r'^(?:awscc_|aws_cloudformation_|aws_cloudcontrolapi_|'
                         r'aws_serverlessapplicationrepository_)|apigateway|api_gateway_|function_url|lambda_url')
READ_TYPES = re.compile(r'^aws_apigatewayv2_[a-z_]+$|^aws_api_gateway_account$')
# What deploys a route or a front door: a block, or an attribute the adapter reads. A reference to a
# resource (`aws_apigatewayv2_api.x.api_endpoint` inside a heredoc) is not one.
TOKEN = re.compile(r'\broute_key"?[^\S\n]*=|^[^\S\n]*(?:module|resource)\b' + NOT_HEADER + '|'
                   r'^[^\S\n]*"?(?:source|body|target)"?[^\S\n]*=', re.M)
ESCAPE = re.compile(r'(?<!\\)(?:\\\\)*\\[uU]')
TOP_ATTR = re.compile(r'(?:^|[\s{;])(body|target)\s*=')
SOURCE = re.compile(r'(?:^|[\s{;])source\s*=\s*"([^"]*)"')
ROUTE_LINE = re.compile(r'^[ \t]*route_key[ \t]*=[ \t]*(\S.*?)[ \t]*$', re.M)
ANY_ROUTE_KEY = re.compile(r'\broute_key"?\s*=')
LITERAL = re.compile(r'^"(?:[^"\\$%]|%(?!\{))*"$')
HEREDOC = re.compile(r'<<-?([^\W\d][\w-]*)[^\S\n]*\n')
SPECIAL = set('{}#/*="\\')


def mask(text: str) -> str:
    """`text` with comments and heredoc bodies blanked and the characters that carry syntax blanked
    inside strings, newlines and length kept, so positions in the result index the original. An
    interpolation inside a string is read as code, nested strings included."""
    out = list(text)
    i, n = 0, len(text)
    stack: List[str] = []  # "s" inside a string, "i" inside a ${...} that opened in a string
    depth: List[int] = []  # brace depth within each open interpolation

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = text[i]
        if stack and stack[-1] == "s":
            if text.startswith(("$${", "%%{"), i):  # escaped: a literal ${ or %{, not a template
                blank(i, i + 3)
                i += 3
            elif c == "\n":
                raise AdapterError("a quoted string runs past the end of its line")
            elif c == "\\" and i + 1 < n:
                blank(i, i + 2)
                i += 2
            elif c == '"':
                stack.pop()
                i += 1
            elif text.startswith("${", i) or text.startswith("%{", i):
                stack.append("i")
                depth.append(0)
                blank(i, i + 2)  # its closing brace is blanked too, so block braces stay balanced
                i += 2
            else:
                if c in SPECIAL:
                    out[i] = " "
                i += 1
            continue
        if c == '"':
            stack.append("s")
            i += 1
        elif c == "#" or text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            blank(i, end)
            i = end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise AdapterError("a /* comment never closes")
            end += 2
            blank(i, end)
            i = end
        elif text.startswith("<<", i):
            m = HEREDOC.match(text, i)
            if m is None:
                raise AdapterError("a heredoc marker the check cannot read")
            # Terraform trims any whitespace around the closing marker, form feeds and NBSP included
            close = re.compile(r'^[^\S\n]*' + re.escape(m.group(1)) + r'[^\S\n]*$', re.M)
            end_m = close.search(text, m.end())
            if end_m is None:
                raise AdapterError(f"heredoc {m.group(1)} never closes")
            end = end_m.end()
            _one_line_templates(text, m.end(), end_m.start())
            blank(m.end(), end)
            i = end
        elif stack and stack[-1] == "i" and c in "{}":
            if c == "{":
                depth[-1] += 1
            elif depth[-1]:
                depth[-1] -= 1
            else:  # closes the interpolation: back inside the string
                stack.pop()
                depth.pop()
            out[i] = " "
            i += 1
        else:
            i += 1
    if stack:
        raise AdapterError("a quoted string or interpolation never closes")
    return "".join(out)


def _one_line_templates(text: str, a: int, b: int) -> None:
    """Refuses a `${` or `%{` in a heredoc body that does not close on its own line: Terraform reads
    it as code, where a line that looks like the closing marker does not close the heredoc."""
    level = 0
    i = a
    while i < b:
        if text.startswith(("$${", "%%{"), i):
            i += 3
            continue
        c = text[i]
        if text.startswith(("${", "%{"), i):
            level += 1
            i += 2
            continue
        if level and c == "{":
            level += 1
        elif level and c == "}":
            level -= 1
        elif c == "\n" and level:
            raise AdapterError("a template sequence in a heredoc runs past the end of its line")
        i += 1


def _top_level_blocks(rel: Path, masked: str) -> None:
    """Refuses anything at the top level of a file but whole blocks. A block that ended early in the
    mask's reading leaves its last lines, or a stray brace, out here."""
    i, n = 0, len(masked)
    while True:
        while i < n and masked[i].isspace():
            i += 1
        if i >= n:
            return
        m = ANY_HEADER.match(masked, i)
        if m is None:
            line = masked.count("\n", 0, i) + 1
            raise AdapterError(f"{rel}:{line}: something other than a block at the top level; the check "
                               "cannot tell where the blocks around it begin and end")
        _, i = _block(masked, m.end(), "top-level", rel)
        i += 1


def _block(masked: str, start: int, what: str, rel: Path) -> Tuple[int, int]:
    """Span of the body of the block whose `{` ends just before `start`."""
    level, i = 1, start
    while i < len(masked) and level:
        level += {"{": 1, "}": -1}.get(masked[i], 0)
        i += 1
    if level:
        raise AdapterError(f"{rel}: a {what} block does not close; the check cannot read it")
    return start, i - 1


def _top_level(masked: str, a: int, b: int) -> str:
    """The text of a block body at its own level, nested blocks blanked."""
    out, level = [], 0
    for c in masked[a:b]:
        if c == "{":
            level += 1
        out.append(c if level == 0 else " ")
        if c == "}":
            level -= 1
    return "".join(out)


def _unreadable_character(text: str) -> str:
    """A character Python and Terraform may read differently, or "" when there is none."""
    for k, c in enumerate(text):
        o = ord(c)
        if (o < 32 and c not in "\t\n\r") or 0x7F <= o <= 0x9F or (c == "\r" and text[k + 1:k + 2] != "\n") \
                or (o > 127 and unicodedata.category(c)[0] in "ZCM"):
            return f"U+{o:04X} at line {text.count(chr(10), 0, k) + 1}"
    m = ESCAPE.search(text)
    return f"a \\u escape at line {text.count(chr(10), 0, m.start()) + 1}" if m else ""


def _hidden(text: str, masked: str) -> str:
    """The first line where the mask blanked a block start or an attribute the adapter reads,
    outside a comment line, or "". However the mask was fooled, code it hid is refused here."""
    for m in TOKEN.finditer(text):
        if masked[m.start():m.end()] == text[m.start():m.end()]:
            continue
        start = text.rfind("\n", 0, m.start()) + 1
        if text[start:].lstrip(" \t").startswith(("#", "//")):
            continue
        return str(text.count("\n", 0, m.start()) + 1)
    return ""


def _headers(rel: Path, masked: str) -> List[Tuple[str, str, int, int]]:
    """(kind, resource type or module name, body start, body end) for every block that starts a
    line. A `resource` or `module` line that does not parse as a header is refused."""
    out = []
    for m in BLOCK_START.finditer(masked):
        kind = m.group(1)
        h = (RESOURCE_HEADER if kind == "resource" else MODULE_HEADER).match(masked, m.start(1))
        if h is None:
            line = masked.count("\n", 0, m.start()) + 1
            raise AdapterError(f"{rel}:{line}: a `{kind}` the check cannot read as a block header")
        a, b = _block(masked, h.end(), kind, rel)
        out.append((kind, h.group(1).strip('"').strip(), a, b))
    return out


def _files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name.endswith(SUFFIXES + JSON_SUFFIXES) \
                and not SKIP.intersection(path.relative_to(root).parts):
            yield path


def _blocks(root: Path, tf: Path, rel: Path, text: str, masked: str) -> None:
    """Refuses, wherever it is in the repository, a front door this adapter cannot read and a module
    that is not a plain local folder inside the repository."""
    for kind, name, a, b in _headers(rel, masked):
        if kind == "resource" and name == "aws_lambda_function_url":
            raise AdapterError(f"{rel}: a Lambda function URL is a front door the check cannot see")
        if kind == "resource" and name.startswith("aws_api_gateway_") and name != "aws_api_gateway_account":
            # the account resource sets the CloudWatch logging role for every API, and serves nothing
            raise AdapterError(f"{rel}: a REST API (v1) resource; only HTTP API v2 routes are read")
        if kind == "resource" and OTHER_ROADS.search(name) and not READ_TYPES.match(name):
            raise AdapterError(f"{rel}: a `{name}` resource can deploy routes or a URL the check cannot read")
        if kind == "resource" and name == "aws_apigatewayv2_api":
            attr = TOP_ATTR.search(_top_level(masked, a, b))
            if attr:
                raise AdapterError(f"{rel}: an HTTP API with `{attr.group(1)} =` defines routes this "
                                   "adapter cannot read")
        if kind == "module":
            src = SOURCE.search(_top_level(masked, a, b))
            source = text[a + src.start(1):a + src.end(1)] if src else ""
            target = (tf.parent / source).resolve()
            inside = PLAIN_SOURCE.fullmatch(source) is not None and target.is_relative_to(root.resolve())
            if not inside or SKIP.intersection(target.relative_to(root.resolve()).parts):
                raise AdapterError(f"{rel}: module {source or '(no source)'!r} is not a plain local folder "
                                   "in this repository, so the check cannot read what it deploys; vendor "
                                   "it under the configured paths")


def deployed_routes(root: Path, paths: Iterable[str]) -> Set[Tuple[str, str]]:
    root = Path(root)
    bases: List[Path] = []
    for rel in paths:
        base = root / rel
        if not base.is_dir():
            raise AdapterError(f"terraform path {rel!r} does not exist under {root}")
        bases.append(base.resolve())
        for p in base.rglob("*"):  # rglob does not follow a linked folder, so its files go unread
            if p.is_symlink():
                raise AdapterError(f"{p.relative_to(root)}: a symlink under the terraform paths; the "
                                   "check reads only real files")

    found: Set[Tuple[str, str]] = set()
    for tf in _files(root):
        rel = tf.relative_to(root)
        text = tf.read_text(encoding="utf-8")
        inside = any(tf.resolve().is_relative_to(b) for b in bases)
        if tf.name.endswith(JSON_SUFFIXES):
            raise AdapterError(f"{rel}: JSON Terraform cannot be read; write it as .tf")
        odd = _unreadable_character(text)
        if odd:
            raise AdapterError(f"{rel}: {odd} may read differently to Terraform; the check refuses it")
        try:
            masked = mask(text)
        except AdapterError as exc:
            raise AdapterError(f"{rel}: {exc}; the check cannot read this file") from None
        hidden = _hidden(text, masked)
        if hidden:
            raise AdapterError(f"{rel}:{hidden}: code the check would not read (inside what it took for a "
                               "string, heredoc or comment); the check cannot read this file")
        _top_level_blocks(rel, masked)
        _blocks(root, tf, rel, text, masked)
        if not inside:
            if ANY_ROUTE_KEY.search(masked) or "aws_apigatewayv2_route" in masked:
                raise AdapterError(f"{rel}: defines a route outside the configured terraform paths; "
                                   "add its directory to security/config.json adapter.paths")
            continue
        lines = list(ROUTE_LINE.finditer(masked))
        if len(lines) != len(ANY_ROUTE_KEY.findall(masked)):
            raise AdapterError(f"{rel}: a route_key shares its line with other syntax or is written as a "
                               "quoted name; put each on its own line as `route_key = \"METHOD /path\"`")
        for m in lines:
            where = f"{rel}:{text.count(chr(10), 0, m.start()) + 1}"
            raw = text[m.start(1):m.end(1)]
            if not LITERAL.match(raw):
                raise AdapterError(f"{where}: route_key {raw} is not one literal string; the check cannot verify it")
            found.add(parse_route_key(raw[1:-1], where))
    return found
