#!/usr/bin/env python3
"""Draw the factory dashboard's README picture from the pane itself.

    python3 scripts/draw_dashboard.py

Runs the dashboard mod's tests with one more test of its own, which takes the
rows picture() in hooks/picture.test.ts lays out (the pane on the terminal, 66
columns wide, drawing hooks/sample.ts) and fails with them as one line,
PANE-ROWS <json>: a test has no console. This writes those rows as
docs/factory-dashboard.svg and as the text inside the README's <details>. Run it after changing how the
pane draws, or after sample.ts is written again: tests/test_draw_dashboard.py
fails while either is out of date.

The tests run in the machine's own time zone whatever TZ says, so picture()
reads at local noon. Needs Claude Code (claude) on the PATH. Exits 1 when the
tests fail or print no rows, or when its test file is already there, and
writes nothing then.
"""
import base64
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
MODS = ROOT / "examples" / "mods"
MOD = "factory-dashboard"
SVG = ROOT / "docs" / "factory-dashboard.svg"
README = MODS / MOD / "README.md"
MARK = "PANE-ROWS "
TIMEOUT = 120
# The test pane_rows() writes for the length of one run, failing with the rows as its message.
OUT_TEST = MODS / MOD / "hooks" / "draw-picture.test.ts"
OUT_NAME = "rows for scripts/draw_dashboard.py"
OUT_TEST_SOURCE = """import {{ test }} from 'claude-code/testing'

import {{ picture }} from './picture.test'

// Written by scripts/draw_dashboard.py for one run, and deleted after it.
test('{name}', async ($, on) => {{
  throw new Error('{mark}' + JSON.stringify(await picture($, on)))
}})
""".format(name=OUT_NAME, mark=MARK)
# The text version: the code block inside the README's <details>.
DETAILS = re.compile(r"(<details>\s*<summary>[^<]*</summary>\s*```\n)(.*?)(\n```)", re.DOTALL)

TITLE = ("The factory dashboard pane in a terminal, with made-up numbers: what is waiting on you, the loop's "
         "spend with a bar a day, throughput and rework, evals, Claude Code's tokens with a bar a day, and activity")
FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
LEFT = 18  # the pane's left edge, in pixels
CELL = 8.4  # one column's width
ROW = 18  # one row's height
FIRST = 71  # the first row's baseline
ASCENT = 13  # from a row's top to its baseline
# The terminal's colours as the picture paints them: a Text's colour, else dim, bold or plain.
COLOURS = {"red": "#f2555a", "yellow": "#e7c25b", "green": "#6fbf73", "accent": "#e8865a"}
DIM = "#8b909a"
BOLD = "#ffffff"
PLAIN = "#d6d6d6"
RULE = "─"
BLOCKS = "▁▂▃▄▅▆▇█"


def pane_rows():
    """The rows picture() in picture.test.ts lays out, as JSON.

    A test has no console and no file system, so the only way out is a failing
    test's message. This writes a test of its own beside picture.test.ts that
    fails with the rows, runs the mod's tests, and deletes it again. One already
    there is another run's, or left by one that was killed: it's left alone, as
    deleting it could break a run still going. .gitignore keeps it out of a commit.
    """
    command = ["claude", "plugin", "test", MOD]
    try:
        with OUT_TEST.open("x") as out:
            out.write(OUT_TEST_SOURCE)
    except FileExistsError:
        raise RuntimeError("{} is already there: another run is drawing, or one was killed before it could "
                           "delete it. Delete it once no run is going".format(OUT_TEST.relative_to(ROOT)))
    try:
        done = subprocess.run(command, cwd=MODS, capture_output=True, text=True, timeout=TIMEOUT,
                              env=dict(os.environ, TZ="UTC"))
    finally:
        OUT_TEST.unlink(missing_ok=True)
    output = done.stdout + "\n" + done.stderr
    # Its own test fails on purpose, so the exit is never 0: the rows are what counts.
    found = [line for line in output.splitlines() if MARK + "{" in line]
    if len(found) != 1:
        tail = "\n".join(output.splitlines()[-40:])
        raise RuntimeError("{} gave {} {}lines, not 1 (exit {}):\n{}".format(
            " ".join(command), len(found), MARK, done.returncode, tail))
    line = found[0]
    try:
        return json.loads(line[line.index(MARK) + len(MARK):].strip())
    except ValueError as e:
        raise RuntimeError("the {}line came back cut or changed: {}".format(MARK, e))


def cells(raster):
    """A Raster's cells, row by row: (code point, foreground) for each column."""
    words = struct.unpack("<{}I".format(raster["columns"] * raster["rows"] * 3), base64.b64decode(raster["cells"]))
    flat = [(words[i], words[i + 1]) for i in range(0, len(words), 3)]
    return [flat[r * raster["columns"]:(r + 1) * raster["columns"]] for r in range(raster["rows"])]


def text(pane):
    """The pane as plain text, one line a row, trailing spaces and blank rows dropped."""
    grid = [[" "] * pane["columns"] for _ in pane["rows"]]
    for r, segs in enumerate(pane["rows"]):
        for seg in segs:
            for i, char in enumerate(seg["text"]):
                grid[r][seg["col"] + i] = char
    for raster in pane["rasters"]:
        for r, row in enumerate(cells(raster)):
            for c, (point, _) in enumerate(row):
                grid[raster["row"] + r][raster["col"] + c] = chr(point)
    return "\n".join("".join(row).rstrip() for row in grid).rstrip("\n")


def fill(seg):
    if seg.get("color") in COLOURS:
        return COLOURS[seg["color"]]
    return DIM if seg.get("dim") else BOLD if seg.get("bold") else PLAIN


def svg(pane):
    """The pane in a terminal frame: each word at its column, rules as lines, chart cells as rectangles."""
    columns = pane["columns"]
    count = len(text(pane).split("\n"))
    width = round(2 * LEFT + columns * CELL)
    height = ROW * count + FIRST + 1

    def baseline(r):
        return FIRST + ROW * r

    def x(col):
        return "{:.1f}".format(LEFT + col * CELL)

    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        'font-family="{f}" font-size="13.5">'.format(w=width, h=height, f=FONT),
        "<title>{}</title>".format(escape(TITLE)),
        '<rect x="0.5" y="0.5" width="{}" height="{}" rx="10" fill="#1b1d22" stroke="#3a3f4b"/>'.format(width - 1, height - 1),
        '<path d="M0.5 40 V10.5 a10 10 0 0 1 10 -10 H{} a10 10 0 0 1 10 10 V40 Z" fill="#23262d" stroke="#3a3f4b"/>'.format(width - 10),
        '<text x="{}" y="25.0" fill="{}" font-weight="700">Factory</text>'.format(LEFT, PLAIN),
        '<text x="{}" y="25.0" fill="{}">×</text>'.format(x(columns - 1), DIM),
    ]
    for r, segs in enumerate(pane["rows"][:count]):
        y = baseline(r)
        line = []
        for seg in segs:
            if seg["text"] and set(seg["text"]) == {RULE}:
                line.append('<line x1="{}" y1="{:.1f}" x2="{}" y2="{:.1f}" stroke="#4a4f5a"/>'.format(
                    x(seg["col"]), y - 4, x(seg["col"] + len(seg["text"])), y - 4))
                continue
            weight = ' font-weight="700"' if seg.get("bold") else ""
            for word in re.finditer(r"\S+", seg["text"]):
                line.append('<text x="{}" y="{:.1f}" fill="{}"{}>{}</text>'.format(
                    x(seg["col"] + word.start()), y, fill(seg), weight, escape(word.group())))
        if line:
            out.append("".join(line))
    for raster in pane["rasters"]:
        for r, row in enumerate(cells(raster)):
            top = baseline(raster["row"] + r) - ASCENT
            for c, (point, colour) in enumerate(row):
                char = chr(point)
                if char not in BLOCKS:
                    continue
                tall = (BLOCKS.index(char) + 1) * ROW / 8
                out.append('<rect x="{}" y="{:.1f}" width="{:.1f}" height="{:.1f}" fill="#{:06x}"/>'.format(
                    x(raster["col"] + c), top + ROW - tall, CELL + 0.4, tall + 0.4, colour & 0xFFFFFF))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def details(readme):
    """The text version as the README has it now."""
    found = DETAILS.search(readme)
    if not found:
        raise RuntimeError("{} has no code block inside <details>".format(README.relative_to(ROOT)))
    return found.group(2)


def drawn():
    """(svg, text): the picture and its text version, drawn from the pane now. Writes nothing."""
    pane = pane_rows()
    return svg(pane), text(pane)


def main():
    try:
        picture, plain = drawn()
        readme = README.read_text()
        details(readme)
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as e:
        print("draw_dashboard: {}".format(e), file=sys.stderr)
        return 1
    SVG.write_text(picture)
    README.write_text(DETAILS.sub(lambda m: m.group(1) + plain + m.group(3), readme, count=1))
    print("Wrote {} and the text in {}".format(SVG.relative_to(ROOT), README.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
