import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import { DARK, LANE_ROWS, OUT_MS, PROJECTS_DIR, accentText, boardColumns, findRoot, hasSpend, headCells, headSvg, inkFor, isCounting, laneAlt, laneCells, laneFit, laneSvg, laneWords, lanesOf, lockPid, loopDir, parseSpend, parseStatus, place, scene, showsBoard, svgColumns } from './logic'
import type { Ink, Lane, Placement } from './logic'
import type { Seen, Spend } from '../types'

const PANE = 'loop-crew'
const COMMAND = 'loop-crew'
const POLL_MS = 2000
// 12.5 a second: with the header and at most MAX_LANES lanes that's 112.5 blits a second at most, under
// the 120 the engine takes. A blit that didn't land is sent again in its key's turn, not as well.
const TICK_MS = 80
const MAX_LANES = 8
const HEAD_KEY = 'head'
const laneKey = (number: number): string => `lane-${number}`
// How often the other surfaces redraw while a time counts. They don't run the tick.
const REDRAW_MS = 30_000
// What the pane asks for when it opens: a board with room for three lanes. The words take a row a lane,
// the lane its 3 rows, its row of times and its row of spend.
const WANT_COLUMNS = 72
const LANE_HEIGHT = LANE_ROWS + 3
const WANT_ROWS = 1 + 3 * LANE_HEIGHT

const launchAtom = atom({ plugin: 'loop-crew', key: 'launch' } as const, null)
const shownAtom = atom({ plugin: 'loop-crew', key: 'shown' } as const, '')
const seenAtom = atom({ plugin: 'loop-crew', key: 'seen' } as const, null)

let stopPolling: (() => void) | null = null
let stopBoard: (() => void) | null = null
let stopRedraw: (() => void) | null = null
// Not atoms: a write would redraw the pane, and a walk is painted with no redraw.
let placed: { shown: string; placement: Placement } | null = null
// What the terminal's drawing mounted, so a tick paints only those at their size. Null: no board is drawn.
let mounted: { columns: number; numbers: number[] } | null = null
// What each Raster last showed, so a tick that changes nothing paints nothing.
const painted = new Map<string, string>()
let ink: Ink = DARK
// Counts the reads that open or switch the pane, so a walk-out's timer knows it's been overtaken.
let opens = 0
// Each issue's spend in its current run, by loop and number, with the row fields it was read for. Not
// an atom: seen stays a copy of the loop's own files, and a changed row already redraws the pane.
type Spent = { started: string | undefined; tokens: number | undefined; cost_usd: number | undefined; spend: Spend | null }
const spends = new Map<string, Map<number, Spent>>()
function spendsOf(project: string | undefined): Map<number, Spent> {
  const loop = spends.get(project ?? '') ?? new Map<number, Spent>()
  spends.set(project ?? '', loop)
  return loop
}
const spendOf = (seen: Seen, number: number): Spend | null => spends.get(seen.project ?? '')?.get(number)?.spend ?? null

const paneIsUp = async ($: EngineInterface): Promise<boolean> => (await $.ui.panes()).some(pane => pane.id === PANE)

// The placement to draw. Before any read, a draw gets one that walks nobody and doesn't store it, so
// the first read after a reload still walks nobody.
function placementFor(seen: Seen, now: number): Placement {
  return placed && placed.shown === (seen.project ?? '') ? placed.placement : place(seen, null, now)
}

// The session's theme, for what the board fades toward. Not being able to tell draws it dark.
async function readInk($: EngineInterface): Promise<Ink> {
  const rows = await $.config.list().catch(() => [])
  return inkFor(rows.find(row => row.key === 'theme')?.value)
}

// The folder saved at session.start first, then the session's root: a /clear starts a new session
// without a session.start, so the saved folder can be missing or the last session's.
async function rootOf($: EngineInterface): Promise<string | null> {
  const exists = (path: string) => $.fs.exists(path)
  const launch = await read($, launchAtom)
  return (launch && (await findRoot(launch, exists))) || findRoot(await $.session.root(), exists)
}

// Whether the process named in the lock is alive. A killed run leaves its lock behind.
async function lockHolderAlive($: EngineInterface, root: string, project?: string): Promise<boolean | null> {
  const text = await $.fs.read(`${root}/${loopDir(project)}/lock`).catch(() => null)
  if (text === null) return null
  const pid = lockPid(text)
  if (pid === null) return true
  const ran = await $.process.run(['kill', '-0', String(pid)]).catch(() => null)
  // kill -0 also fails on another user's process; count only "no such process" as gone.
  return !ran || ran.exitCode === 0 || !/no such process/i.test(ran.stderr)
}

// One look at one loop's files. It only reads: the loop is the only writer.
async function look($: EngineInterface, root: string, project?: string): Promise<Seen> {
  const text = await $.fs.read(`${root}/${loopDir(project)}/status.json`).catch(() => null)
  const isLive = (await lockHolderAlive($, root, project)) === true
  return { ...(project ? { project } : {}), status: parseStatus(text), isLive }
}

// Read usage.json again for each issue with a lane whose run, tokens or cost has changed since the last
// read, and only for those. A file that's missing or can't be read is no spend. An issue this loop's
// status file no longer lists is forgotten, so the cache holds no more than the loops' status files do.
// One still listed is kept, so a lane walking out keeps its spend.
async function readSpends($: EngineInterface, root: string, seen: Seen): Promise<void> {
  const loop = spendsOf(seen.project)
  const listed = new Set((seen.status?.issues ?? []).map(row => row.number))
  for (const number of [...loop.keys()]) if (!listed.has(number)) loop.delete(number)
  for (const row of scene(seen).rows) {
    const known = loop.get(row.number)
    if (known && known.started === row.started && known.tokens === row.tokens && known.cost_usd === row.cost_usd) continue
    const text = await $.fs.read(`${root}/${loopDir(seen.project)}/issue-${row.number}/usage.json`).catch(() => null)
    const spend = parseSpend(text, row.started)
    loop.set(row.number, { started: row.started, tokens: row.tokens, cost_usd: row.cost_usd, spend: hasSpend(spend) ? spend : null })
  }
}

// When an issue's walk out ends, one redraw takes its lane away. It does nothing once a newer open or
// switch has replaced the placement or the pane is gone.
function endWalkOuts($: EngineInterface, known: Placement | null, fresh: Placement): void {
  const already = new Set((known?.outs ?? []).map(out => out.row.number))
  const open = opens
  for (const out of fresh.outs) {
    if (already.has(out.row.number)) continue
    $.clock.after(OUT_MS, () => {
      void (async () => {
        if (open === opens && (await paneIsUp($))) $.ui.invalidate('ui.render')
      })().catch(() => {})
    })
  }
}

// Read the shown loop, place its issues, and ask for a redraw only when the read differs from the last.
// A read that a switch overtook is dropped. The project is part of what's compared, so a switch always
// counts. `isOpening` is the read the command makes: it has no previous placement, even when it equals
// the last read, because a reopen can read the same data. A placement from another loop is none either.
async function refresh($: EngineInterface, isOpening = false): Promise<void> {
  const root = await rootOf($)
  if (!root) return
  const name = await read($, shownAtom)
  const next = await look($, root, name || undefined)
  await readSpends($, root, next)
  const now = await $.clock.now()
  if ((await read($, shownAtom)) !== name) return
  if (isOpening) opens++
  const known = !isOpening && placed?.shown === name ? placed : null
  const placement = place(next, known?.placement ?? null, now)
  placed = { shown: name, placement }
  endWalkOuts($, known?.placement ?? null, placement)
  if (JSON.stringify(await read($, seenAtom)) === JSON.stringify(next)) return
  await update($, seenAtom, () => next)
  $.ui.invalidate('ui.render')
}

// Poll only while the pane is up, so a session that never opens it reads nothing.
function startPolling($: EngineInterface): void {
  if (stopPolling) return
  const timer = $.clock.every(POLL_MS, () => {
    void (async () => {
      if (await paneIsUp($)) return refresh($)
      stopPolling?.()
      stopPolling = null
      endRedraws()
    })().catch(() => {})
  })
  stopPolling = () => timer.cancel()
}

function endRedraws(): void {
  stopRedraw?.()
  stopRedraw = null
}

// Redraw the other surfaces every 30 seconds while a lane's time counts, so it moves on, and not at all
// otherwise. Started from a non-terminal drawing, as startBoard is from a terminal one, and stopped once
// the pane is gone, here or by the poll.
function startRedraw($: EngineInterface): void {
  if (stopRedraw) return
  const timer = $.clock.every(REDRAW_MS, () => {
    void (async () => {
      if (!(await paneIsUp($))) return endRedraws()
      const seen = await read($, seenAtom)
      const now = await $.clock.now()
      if (seen && lanesOf(placementFor(seen, now), now).some(isCounting)) $.ui.invalidate('ui.render')
    })().catch(() => {})
  })
  stopRedraw = () => timer.cancel()
}

// A Raster that isn't mounted, or one the terminal has since resized, answers with a deny or a rejection.
// Neither matters: it isn't counted as painted, so the next tick paints it again.
async function paint($: EngineInterface, key: string, cells: string): Promise<void> {
  if (painted.get(key) === cells) return
  try {
    const answer = await $.ui.blit({ requestId: PANE, key, cells })
    if (!(answer && typeof answer === 'object' && 'deny' in answer)) painted.set(key, cells)
  } catch {
    // Ignored, as above.
  }
}

// Paint the board as it stands, never by redrawing the pane. Started from a terminal drawing, so other
// surfaces, where SMIL does this, run no timer. A pane behind another paints nothing.
function startBoard($: EngineInterface): void {
  if (stopBoard) return
  const timer = $.clock.every(TICK_MS, () => {
    void (async () => {
      const pane = (await $.ui.panes()).find(p => p.id === PANE)
      if (!pane) {
        stopBoard?.()
        stopBoard = null
        return
      }
      const seen = await read($, seenAtom)
      const now = await $.clock.now()
      if (!mounted || !seen || !pane.isShown) return
      const placement = placementFor(seen, now)
      if (!showsBoard(scene(seen).message, placement, now)) return
      const lanes = lanesOf(placement, now)
      await paint($, HEAD_KEY, headCells(lanes, mounted.columns, ink))
      for (const number of mounted.numbers) {
        const lane = lanes.find(l => l.row.number === number)
        if (lane) await paint($, laneKey(number), laneCells(lane, mounted.columns, now, ink, spendOf(seen, number)))
      }
    })().catch(() => {})
  })
  stopBoard = () => timer.cancel()
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    // A reload fires session.start again; the directory the session started in is the first one.
    await update($, launchAtom, prev => prev ?? e.cwd)
    ink = await readInk($)
    await $.command.register({
      name: COMMAND,
      description: 'A lane for each issue the loop is working on, and a figure running to its step and working there',
      argumentHint: '[project]',
    })
    // A pane left open across a reload keeps updating. The load's own drawing restarts its timer.
    if (await paneIsUp($)) startPolling($)
    return next(e)
  })

  on('command.run', { command: COMMAND }, async ($, e) => {
    try {
      const name = e.args.trim()
      const root = await rootOf($)
      if (!root) return { text: `No scripts/loop.py at or above ${await $.session.root()}, so there is no loop to show.` }
      if (name) {
        // Only a name the folder lists, exactly, so nothing typed can reach outside it.
        const entries = await $.fs.list(`${root}/${PROJECTS_DIR}`).catch(() => [])
        if (!entries.some(entry => entry.kind === 'dir' && entry.name === name)) {
          return { text: `No loop for ${name} under .loop/projects/.` }
        }
      }
      const isShown = (await $.ui.panes()).some(pane => pane.id === PANE && pane.isShown)
      if (isShown && (await read($, shownAtom)) === name) {
        try {
          await $.ui.close({ id: PANE })
          return { text: 'Loop crew closed.' }
        } catch {
          return { text: "The loop crew pane couldn't close. The × in its corner closes it." }
        }
      }
      await update($, shownAtom, () => name)
      await refresh($, true)
      // On a pane already open this retitles it.
      const opened = await $.ui.open({ id: PANE, title: name ? `Loop crew: ${name}` : 'Loop crew', rows: WANT_ROWS, columns: WANT_COLUMNS })
      startPolling($)
      return { text: opened.isPlaced ? 'Loop crew opened.' : 'Loop crew opened. Widen the terminal to see it.' }
    } catch {
      return { text: "The loop crew pane couldn't open." }
    }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const elements = $.ui.resolve(e)
    const { Box, Text } = elements
    const isTerminal = e.surface === 'terminal'
    if (isTerminal) startBoard($)
    else startRedraw($)
    const seen = await read($, seenAtom)
    if (isTerminal) mounted = null
    if (!seen) return <Text dimColor>Looking for the loop…</Text>
    const { message } = scene(seen)
    const now = await $.clock.now()
    const placement = placementFor(seen, now)
    if (message && !showsBoard(message, placement, now)) return <Text key="message" dimColor>{message}</Text>
    const lanes = lanesOf(placement, now)

    // A lane's words: where it has got to in the colour of that step, and on a terminal never the part cut.
    const words = (lane: Lane, width?: number) => {
      const { number, title, status } = laneWords(lane.row, width)
      return (
        <Box key={`line-${lane.row.number}`} flexDirection="row" columnGap={1}>
          <Text weight="bold">{number}</Text>
          <Text>{title}</Text>
          <Text color={accentText(lane.station)}>{status}</Text>
        </Box>
      )
    }

    // The terminal draws the lanes that fit, each with its words over it, and how many more there are.
    if (isTerminal && 'Raster' in elements) {
      const { Raster } = elements
      const columns = boardColumns(e.props.bodyColumns)
      const bodyRows = e.props.scroll?.bodyRows
      const room = bodyRows === undefined ? undefined : bodyRows - (columns ? 1 : 0)
      const fit = laneFit(lanes.length, columns ? LANE_HEIGHT : 1, room)
      const shown = lanes.slice(0, columns ? Math.min(fit, MAX_LANES) : fit)
      const more = lanes.length - shown.length
      mounted = columns ? { columns, numbers: shown.map(lane => lane.row.number) } : null
      const head = columns ? headCells(lanes, columns, ink) : ''
      if (columns) painted.set(HEAD_KEY, head)
      return (
        <Box flexDirection="column">
          {columns && <Raster key={HEAD_KEY} columns={columns} rows={1} cells={head} />}
          {shown.map(lane => {
            const cells = columns ? laneCells(lane, columns, now, ink, spendOf(seen, lane.row.number)) : ''
            if (columns) painted.set(laneKey(lane.row.number), cells)
            return (
              <Box key={`lane-box-${lane.row.number}`} flexDirection="column">
                {words(lane, e.props.bodyColumns)}
                {columns && <Raster key={laneKey(lane.row.number)} columns={columns} rows={LANE_ROWS + 2} cells={cells} />}
              </Box>
            )
          })}
          {more > 0 && <Text key="more" dimColor>{`and ${more} more`}</Text>}
        </Box>
      )
    }

    // Every other surface shows every lane, animated by the document itself, its words wrapped. Each Svg
    // has no size, so the surface draws it across the pane at the shape its viewBox gives.
    const Svg = 'Svg' in elements ? elements.Svg : null
    const columns = svgColumns(e.props.bodyColumns)
    return (
      <Box flexDirection="column" rowGap={1}>
        {Svg && <Svg key={HEAD_KEY} source={headSvg(lanes, ink, columns)} alt="The loop's steps, left to right" />}
        {lanes.map(lane => (
          <Box key={`lane-box-${lane.row.number}`} flexDirection="column">
            {words(lane)}
            {Svg && <Svg key={laneKey(lane.row.number)} source={laneSvg(lane, now, ink, columns, spendOf(seen, lane.row.number))} alt={laneAlt(lane)} isInteractive />}
          </Box>
        ))}
      </Box>
    )
  })
}
