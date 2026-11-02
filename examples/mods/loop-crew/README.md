# Loop crew

The [loop pane](../loop-pane/) tells you what the loop is doing in words. This mod shows it: a pane
with a map of a work floor, a station for each loop step, and a small figure for each issue being
worked on. A figure walks to its step's station when the step changes and acts out the work there.

| Station | Furniture | Step | The figure | The words |
|---|---|---|---|---|
| `door` | A door | No step yet, or any other step | Standing still | `starting`, or the step lowercased |
| `planning` | A planning table | `SHAPE` | At a table | `planning` |
| `tests` | A test bench | `TEST` | Writing at the bench | `writing tests` |
| `workshop` | A workbench | `BUILD` | Swinging a hammer | `building` |
| `review` | A review desk | `VALIDATE` | Holding up a glass | `checking` |
| `dock` | A loading dock with boxes | `SCALE` | Carrying a box | `opening the pull request` |

Under each figure is its issue number, cut to the last 4 digits (`12345` shows `2345`). Under the
floor is the legend, one line an issue in number order: `#<n> <title> · <step's words>, round <r>`,
with the round left off at 0.

It's a Claude Code mod, so it works in Claude Code only. No surface has been tried yet. It's built
from the types and tested with `claude plugin test`. The animation on the mobile app is expected but
untried: the app draws an Svg in a web view, and nobody has checked that SMIL runs there. Nobody has
checked that a new Svg starts its walk from the beginning either, because the types don't say whether
a new `source` restarts its animations. The Svg is built so a figure stands at its new spot without
SMIL.

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
| `The loop isn't running.` | There's no lock, or its holder has gone. Rows left at `working` by a killed run draw no floor |
| `Nothing being built right now.` | The loop is running with no issue at `working`, and none still walking out |
| The floor and the legend | A figure for each issue at `working` and each walking out |

## The floor

| Layout | Size | Boxes | Shows on |
|---|---|---|---|
| Wide | 64 columns by 24 rows | `door`, `planning`, `tests` on top, then `workshop`, `review`, `dock` back along the bottom, three spots a box | A terminal at least 64 columns wide, and every other surface |
| Compact | 32 columns by 36 rows | `door`, `planning`; `workshop`, `tests`; `review`, `dock`, snaking down, two spots a box | A terminal 32 to 63 columns wide |

Below 32 columns the pane shows the legend alone. The floor is always drawn whole, even where it's
taller than the pane. Under it a terminal shows the legend lines that fit, at least one, then
`and <n> more`, each cut to the pane's width. Other surfaces show every line, wrapped.

At a station, issues take its spots in number order. A station with more issues than spots draws the
lowest numbers and shows `+<n>` after its name for the rest, and they keep their legend lines.

## The walk

When a read finds an issue on a different spot from the last read of the same loop, its figure walks
in a straight line to the new spot over a second, its number moving with it, then acts there.

- A new issue walks in from the door.
- A hidden issue that gains a spot appears there without walking, and one whose new station has no
  spot for it isn't drawn walking.
- An issue whose row goes from `working` to `pr` walks to the door and is gone. While it walks it stays
  on the floor and in the legend as `opening the pull request`, so `Nothing being built right now.`
  waits for it. A row that leaves `working` any other way is gone at the next read, with no walk.
- The read `/loop-crew` makes when it opens or switches the pane, and the first read after a reload,
  place every figure at its spot without walking.

## What it doesn't do

It only reads. Every 2 seconds while the pane is open it reads the shown loop's `status.json` and
`lock`, and it stops once the pane closes. The one process it runs is `kill -0 <pid>`, to check the
lock's holder. It never writes a file, never runs [`scripts/loop.py`](../../../scripts/loop.py) or `gh`, and spends no model
tokens. Controls such as stop stay in the [loop pane](../loop-pane/). It shows one loop at a time, and
doesn't show issues that are queued, blocked or ended. The floor doesn't scroll or zoom.

## How the animation works

Each station's furniture and act live once in [`hooks/logic.ts`](hooks/logic.ts). Furniture is 13 by 6 pixels. An act is
one to four frames of 6 by 8 pixels in the figures' palette, and a walking figure shows one `WALK` frame.
An act moves to its next frame every 250 ms. One colour, `FIGURE_MARK`, is at one pixel of every figure
and nowhere else on the floor, which is how the tests find a figure.

- **Terminal:** the whole floor is one `Raster` keyed `floor`, half-block pixels with the names, counts
  and numbers as text in its cells. A 125 ms timer paints the floor as it stands at that moment with
  `$.ui.blit`, so the pane isn't redrawn for a frame or a step of a walk, and a redraw draws the same
  moment. A blit that fails is ignored. The timer stops once the pane is gone.
- **Desktop, VS Code and mobile:** the floor is one `Svg`, each act defined once and each figure placed
  with `<use>`, its frames shown in turn by SMIL. A walking figure slides from where it is to its spot
  over the walk's time left. No timer paints there. Where SMIL doesn't run, every figure stands at its
  spot on its first frame.

Spots and walks are kept in the module, not in `$.state`, and worked out by `place`, from the last
placement and the new read. Each read works out both layouts, so a resize never causes a walk.

## Changing it

[`hooks/logic.ts`](hooks/logic.ts) holds the stations, layouts, acts and decisions as plain functions, so they can be tested.
[`hooks/register.tsx`](hooks/register.tsx) reads the files and draws the pane. From [`examples/mods/`](../):

```bash
claude plugin validate loop-crew
claude plugin test loop-crew
```

`python3 -m unittest discover -s tests`, and so the loop, runs these wherever Claude Code is installed. CI doesn't install Claude Code, so it skips them.
