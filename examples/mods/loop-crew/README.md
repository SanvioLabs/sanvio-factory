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
in its station's colour. Under the lane is a row of times, one under each station's name: how long
the issue has spent at that step. Under the times is a row of spend: what each step has cost and
how many tokens it used. [The times](#the-times) and [the spend](#the-spend) say where they come
from.

Two issues on a 64-column terminal look like this, the shapes without their colours: #12 swinging
its hammer at `build` beside a stack of bricks, 3 minutes in, #13 reading a page at `check`, 48
seconds in. Where a station has no time or no spend the board draws a dash (U+2014). The picture
shows a hyphen there instead.

```text
start     plan      test       build     check     ship
#12 Add a retry to the upload · building, round 1
                                ▄█ █  ▄▄
                                ▄▀▄  ▄█▀▄▄
 ▄█▄▄▄▄▄▄▄▄▄█▄▄▄▄▄▄▄▄▄█▄▄▄▄▄▄▄▄▄███ ▄▀█ █▀▄█▄ ▄ ▄ ▄ ▄█▄
-         4m        12m        3m        -         -
-         $0.29 85k $1.15 253k -         -         -
#13 Show the round in the pane · checking, round 2
                                          ▄█▄▀ ▀▀▀▀▀▀
                                          ▄▀▄  ▀▀▀▀▀▀
 ▄█▄▄▄▄▄▄▄▄▄█▄▄▄▄▄▄▄▄▄█▄▄▄▄▄▄▄▄▄▄█▄▄▄▄▄▄▄▄███ ▄▀█▀█▀██▄
-         5m        20m        1h12      48s       -
-         $0.31 92k $1.40 310k $4.22     $0.52 96k -
```

It's a Claude Code mod, so it works in Claude Code only. It has been seen in the terminal, in Claude
Code run in VS Code's integrated terminal, against a pretend loop. Loop crew 0.3.0 has been seen in
the VS Code extension's pane, and a probe showed that an Svg sized as this one is fills it. Claude
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

When there's more than one loop, a picker sits above the header, and above the pane's message when
there's no board. It lists the harness, by its folder's name, and each folder under
`.loop/projects/` with a `status.json` that parses, the loops on a job first, each marked `●` with
its count past one. Picking a loop switches the pane to it and retitles it, as `/loop-crew <name>`
does. Picking the loop already shown changes nothing, and a pick never closes the pane. The mobile
app draws no picker; there the command switches.

On a terminal the board is as wide as the pane, from 42 columns to 120, and wider panes leave the
rest empty. The picker takes a row when it's there, the header a row and each lane 6: its words,
three rows of lane, its row of times, then its row of spend. The pane shows the lanes that fit, at
least one and at most 8, then `and <n> more`. The mod cuts only the title, to the pane's width. In a
pane too narrow for where the issue has got to, those words wrap. Below 42 columns the pane shows the
words alone, a line an issue. `/loop-crew` asks for 72 columns by 20 rows when it opens, room for the
picker and three lanes, and a terminal gives what it has.

Every other surface draws the header and each lane as an Svg with a viewBox and no size of its own,
so the drawing fills the pane's width at its own shape. It's drawn three columns wide for each of the
pane's, between 64 and 240, and 64 when the pane's width isn't known: 126 at the 42 columns the VS
Code extension's docked pane reported. Every station's place, the rail, the walks and the work are
worked out at that width. Under each lane are the station names, the lane's own in its colour and
the rest dim, then the times, then the spend. These surfaces show every lane and wrap the words.

The board reads the session's theme when the session starts. A theme with `light` in its name draws it
for a light background, and any other theme, or none it can read, for a dark one.

## The times

Each station's time is how long the issue's current run has spent on that station's step, rounds
added together. The loop writes them to `status.json`: `step_seconds` holds the whole seconds for
each step finished, and `step_started` says when the current step began. A loop older than the one
that added them (#367) writes neither, and its lanes show a dash (U+2014) under every station.

| Station | Its time comes from |
|---|---|
| `start` | Nothing: it always shows a dash |
| `plan`, `test`, `build`, `check`, `ship` | `step_seconds` for `SHAPE`, `TEST`, `BUILD`, `VALIDATE` and `SCALE` |

While the issue is working past `start` and its step has begun, the current station adds the time
since `step_started`. Any other station without an entry shows a dash. Times are floored:

| Time | Reads |
|---|---|
| Under a minute | Whole seconds: `0s`, `42s`, `59s` |
| A minute to an hour | Whole minutes: `1m`, `59m` |
| An hour or more | Hours and two-digit minutes: `1h00`, `1h05` |
| None | A dash (U+2014) |

The current station's time is in its colour, any other station's in the tool grey, and a dash dim.

- **Terminal:** the times are the lane's 4th row, and the spend its 5th, each starting at the column
  where its station's name starts in the header. A time that would run into the next station's is
  cut with `…`, so a blank column always comes between two. The current time counts up as the
  board is painted, with no redraw.
- **Desktop, the VS Code extension and mobile:** a time is as of the drawing. While any lane's time
  is counting, the pane is redrawn every 30 seconds, and otherwise never for the times. Each of those
  redraws starts every pose and every piece of work from its first frame, and a figure mid-walk
  carries on from where it is.

An issue walking out keeps its times, with nothing counting.

## The spend

Under the times, each station shows what its step has cost in the issue's current run and how many
tokens it used. The figures come from `<loop dir>/issue-<N>/usage.json`, which the loop adds an
entry to after each agent run: `.loop/issue-<N>/usage.json` for the harness's loop, and
`.loop/projects/<name>/issue-<N>/usage.json` for a project's. They are the current run's only: an
entry counts when its `run_started` is the row's `started` in `status.json`, as the loop counts its
own token budget, so a relabelled issue starts again from nothing. The cost is Claude Code's own
estimate at API prices, not a bill.

| Station | Its spend comes from |
|---|---|
| `start` and `ship` | Nothing: they always show a dash |
| `plan`, `test`, `build`, `check` | The entries whose `step` is `plan`, `test`, `build` and `review`, rounds added together |

A `retro` entry counts for no station. A station's tokens are its entries' input, output,
cache-write and cache-read tokens added together. A run that reported nothing adds nothing, so a
station whose only runs reported nothing shows a dash. Figures are floored:

| Figure | Reads |
|---|---|
| A cost | Dollars and whole cents: `0.004` reads `$0.00`, `0.29` reads `$0.29`, `1.15` reads `$1.15`, `1.729` reads `$1.72`, `12.4` reads `$12.40` |
| Tokens under 1,000 | The number |
| Tokens under a million | Whole thousands: `253,898` reads `253k` |
| A million tokens or more | Millions to one place: `6,208,489` reads `6.2M`, `6,000,000` reads `6.0M` |

A stage shows its cost and its tokens, `$1.72 6.2M`, when both fit before the next station's
column. If they don't, it shows the cost alone, `$1.72`, cut with `…` if even that doesn't fit. A
stage with tokens and no cost shows the tokens. A stage with no spend shows a dash (U+2014), as a
stage with no time does. The colours are the times': the current station's in its colour, any other
station's in the tool grey, and a dash dim.

- **Terminal:** the spend is the lane's 5th row, in the same columns as the times, with a blank
  column before the next station's.
- **Desktop, the VS Code extension and mobile:** the spend is the Svg's row under the times, given
  room for as many letters as fit before the next station's name.

The pane reads an issue's `usage.json` when its lane first appears, then again only when its
`started`, `tokens` or `cost_usd` in `status.json` changes, which the loop does each time it adds an
entry. A lane the pane doesn't draw isn't read: on a terminal, that's the issues behind `and N more`,
and every issue when the pane is too narrow for a board. An issue `status.json` stops listing is
forgotten, and read afresh if it comes back. A `usage.json` that's missing or can't be read shows a
dash under every stage.

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

It only reads. Every 2 seconds while the pane is open it reads every loop's `status.json` and `lock`,
for the board and the picker, and the `usage.json` of each issue whose lane it draws when
[the spend](#the-spend) has changed, and it stops once the pane closes. It doesn't read or set the
session's `/project` focus. The one process it runs is `kill -0 <pid>`, to check the
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
  pixels with the station names as text in the header's cells. A lane's Raster is 5 rows: 3 of
  pixels, 1 of its times as text and 1 of its spend. An 80 ms timer paints each that changed
  with `$.ui.blit`, so the pane isn't redrawn for a pose or a step of a walk, and a redraw draws the
  same moment. A blit that doesn't land is painted again on the next tick. With the header and 8
  lanes that's at most 112.5 blits a second, under the 120 the engine takes. A pane behind another
  paints nothing, and the timer stops once the pane is gone.
- **Desktop, the VS Code extension and mobile:** each lane is one `Svg` with its poses and its work
  sampled into frames for SMIL to show in turn. It's built so a running figure slides from where it
  is to its station over the walk's time left, on the same curve as the terminal. No timer paints
  there. The one timer is the 30-second redraw while a time counts, which stops once the pane is
  gone. Where SMIL doesn't run, every figure stands at its station on its first pose.

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
