# Loop crew

The [loop pane](../loop-pane/) tells you what the loop is doing in words. This mod shows it: a pane
with a lane for each issue being worked on, the loop's steps left to right along it, and a small
figure that runs to its step's station when the step changes and works there.

| Station | Step | The figure | The work beside it | The words |
|---|---|---|---|---|
| `start` | No step yet, or any other step | Standing | Three dots taking turns | `starting`, or the step lowercased |
| `plan` | `SHAPE` | Holding a pen | Two lines being ruled | `planning` |
| `test` | `TEST` | Raising and lowering a pen | Four checks turning green | `writing tests` |
| `build` | `BUILD` | Swinging a hammer | Bricks dropping into a stack | `building` |
| `check` | `VALIDATE` | Holding something up to read | A bar reading across a page | `checking` |
| `ship` | `SCALE` | Stepping with a parcel | A parcel sliding off along the rail | `opening the pull request` |

Over the lanes, a header names the stations, each in its colour while an issue is working there and
dim otherwise. Each lane has a line of words, `#<n> <title> · <step's words>, round <r>`, with the
round left off at 0 and the step's words in its station's colour, then the lane itself: a rail lit in
the stations' colours up to the figure and dotted beyond it, a node at each station, and the figure
in its station's colour.

Two issues on a 64-column terminal look like this, the shapes without their colours: #12 swinging
its hammer at `build` beside a stack of bricks, #13 reading a page at `check`.

```text
start     plan      test       build     check     ship
#12 Add a retry to the upload · building, round 1
                                ▄█ █  ▄▄
                                ▄▀▄  ▄█▀▄▄
 ▄█▄▄▄▄▄▄▄▄▄█▄▄▄▄▄▄▄▄▄█▄▄▄▄▄▄▄▄▄███ ▄▀█ █▀▄█▄ ▄ ▄ ▄ ▄█▄
#13 Show the round in the pane · checking, round 2
                                          ▄█▄▀ ▀▀▀▀▀▀
                                          ▄▀▄  ▀▀▀▀▀▀
 ▄█▄▄▄▄▄▄▄▄▄█▄▄▄▄▄▄▄▄▄█▄▄▄▄▄▄▄▄▄▄█▄▄▄▄▄▄▄▄███ ▄▀█▀█▀██▄
```

It's a Claude Code mod, so it works in Claude Code only. It has been seen in the terminal, in Claude
Code run in VS Code's integrated terminal, against a pretend loop. The VS Code extension, Claude
Desktop and the mobile app haven't been tried. It's built from the types and tested with
`claude plugin test`. The types say the desktop runs SMIL in an Svg drawn with `isInteractive` and
the extension draws an Svg as an image where SMIL can run. The mobile app draws one in a web view, and
nobody has checked that SMIL runs there. Nobody has checked that a new Svg starts its walk from the
beginning either, because the types don't say whether a new `source` restarts its animations. The Svg
is built so a figure stands at its station without SMIL.

## Turn it on

It loads by itself: the harness's [`.claude/settings.json`](../../../.claude/settings.json) turns it on. If `/loop-crew`
isn't there, install it from inside a session, at the root, or run `/reload-plugins`:

```
/plugin marketplace add ./
/plugin install loop-crew@sanvio-harness-starter
```

A change to what the mod does raises `version` in its [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json).

To turn it off just for you:

```bash
claude plugin disable loop-crew@sanvio-harness-starter --scope local
```

## Using it

| Type | Does |
|---|---|
| `/loop-crew` | Opens the pane on the harness's loop, titled `Loop crew` |
| `/loop-crew <name>` | Opens it on the project's loop in `.loop/projects/<name>/`, titled `Loop crew: <name>` |
| The same again | Closes the pane |
| Another loop's name, or no name while a project is shown | Switches the open pane to that loop |

A name must be exactly a folder under `.loop/projects/`. Anything else, `../x` included, answers
`No loop for <name> under .loop/projects/.` and changes nothing.

## What the pane says

Checked in this order:

| The pane says | Means |
|---|---|
| `No loop has run here yet.` | There's no `status.json`, or it can't be read |
| `The loop isn't running.` | There's no lock, or its holder has gone. Rows left at `working` by a killed run draw no lanes |
| `Nothing being built right now.` | The loop is running with no issue at `working`, and none still walking out |
| The header and the lanes | A lane for each issue at `working` and each walking out, in number order |

## The board

On a terminal the board is as wide as the pane, from 42 columns to 120, and wider panes leave the
rest empty. The header takes a row and each lane four: its words, then three rows of lane. The pane
shows the lanes that fit, at least one and at most 8, then `and <n> more`. The mod cuts only the
title, to the pane's width. In a pane too narrow for where the issue has got to, those words wrap.
Below 42 columns the pane shows the words alone, a line an issue.
`/loop-crew` asks for 72 columns by 13 rows when it opens, room for three lanes, and a terminal gives
what it has.

Every other surface draws the header as an Svg 256 by 16 pixels and each lane as one 256 by 24,
shows every lane, and wraps the words.

The board reads the session's theme when the session starts. A theme with `light` in its name draws it
for a light background, and any other theme, or none it can read, for a dark one.

## The walk

When a read finds an issue at a different station from the last read of the same loop, its figure
runs along its lane to the new one, easing in and out, its tool held out in front. It takes 480 ms
plus 170 ms a station, up to 1.5 seconds. Going back along the path, it faces the other way. On a
terminal the rail lights up behind it as it runs, and the figure takes on the colour of where it has
got to. Elsewhere the rail is lit to where it's going from the start, and the figure is in that
station's colour.

- A new issue runs in from `start`.
- A walk overtaken by the next read carries on from where the figure is, with no jump.
- An issue whose row goes from `working` to `pr` runs off the right end of its lane over 0.8 seconds
  and is gone. While it runs it keeps its lane and its words, as `opening the pull request`, so
  `Nothing being built right now.` waits for it. A row that leaves `working` any other way is gone
  at the next read, with no walk.
- The read `/loop-crew` makes when it opens or switches the pane, and the first read after a reload,
  place every figure at its station without walking.

## What it doesn't do

It only reads. Every 2 seconds while the pane is open it reads the shown loop's `status.json` and
`lock`, and it stops once the pane closes. The one process it runs is `kill -0 <pid>`, to check the
lock's holder. It never writes a file, never runs [`scripts/loop.py`](../../../scripts/loop.py) or `gh`, and spends no model
tokens. Controls such as stop stay in the [loop pane](../loop-pane/). It shows one loop at a time, and
doesn't show issues that are queued, blocked or ended. The board doesn't scroll or zoom.

## How the animation works

Each station's poses and work live once in [`hooks/logic.ts`](hooks/logic.ts). A figure is 3 or 4 by 5 pixels, a head, a
body in its station's colour and a tool. A station's poses play in turn, each held for its own time, so
a hammer winds up slowly and lands fast, and a running figure shows two strides. The work is drawn in
the 7 pixels to the figure's right, above the rail, and on a narrow board never over the next station's node. A figure's head is the only pixel on a lane in the
head's colour, which is how the tests find a figure.

- **Terminal:** the header is one `Raster` keyed `head` and each lane one keyed `lane-<n>`, half-block
  pixels with the station names as text in the header's cells. An 80 ms timer paints each that changed
  with `$.ui.blit`, so the pane isn't redrawn for a pose or a step of a walk, and a redraw draws the
  same moment. A blit that doesn't land is painted again on the next tick. With the header and 8
  lanes that's at most 112.5 blits a second, under the 120 the engine takes. A pane behind another
  paints nothing, and the timer stops once the pane is gone.
- **Desktop, the VS Code extension and mobile:** each lane is one `Svg` with its poses and its work
  sampled into frames for SMIL to show in turn. It's built so a running figure slides from where it
  is to its station over the walk's time left, on the same curve as the terminal. No timer paints
  there. Where SMIL doesn't run, every figure stands at its station on its first pose.

Stations and walks are kept in the module, not in `$.state`, and worked out by `place`, from the last
placement and the new read. A walk is kept in stations, not pixels, so a resize never causes one.

## Changing it

[`hooks/logic.ts`](hooks/logic.ts) holds the stations, poses, drawings and decisions as plain functions, so they can be tested.
[`hooks/register.tsx`](hooks/register.tsx) reads the files and draws the pane. From [`examples/mods/`](../):

```bash
claude plugin validate loop-crew
claude plugin test loop-crew
```

`python3 -m unittest discover -s tests`, and so the loop, runs these wherever Claude Code is installed. CI doesn't install Claude Code, so it skips them.
