import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import { LAYOUTS, PROJECTS_DIR, WALK_MS, clip, findRoot, floorAlt, floorCells, floorSvg, layoutFor, legend, legendFit, lockPid, loopDir, parseStatus, place, scene, showsFloor } from './logic'
import type { LayoutName, Placement } from './logic'
import type { Seen } from '../types'

const PANE = 'loop-crew'
const COMMAND = 'loop-crew'
const POLL_MS = 2000
const TICK_MS = 125
const FLOOR_KEY = 'floor'

const launchAtom = atom({ plugin: 'loop-crew', key: 'launch' } as const, null)
const shownAtom = atom({ plugin: 'loop-crew', key: 'shown' } as const, '')
const seenAtom = atom({ plugin: 'loop-crew', key: 'seen' } as const, null)

let stopPolling: (() => void) | null = null
let stopFloor: (() => void) | null = null
// Not atoms: a write would redraw the pane, and a walk is painted with no redraw. Each read places the
// issues for both layouts, because it doesn't know the pane's size, so a resize never causes a walk.
let placed: { shown: string; wide: Placement; compact: Placement } | null = null
// Which floor the terminal's drawing mounted, so a blit paints its size. Null: no floor is drawn.
let mounted: LayoutName | null = null
// Counts the reads that open or switch the pane, so a walk-out's timer knows it's been overtaken.
let opens = 0

const paneIsUp = async ($: EngineInterface): Promise<boolean> => (await $.ui.panes()).some(pane => pane.id === PANE)

// The placement to draw. Before any read, a draw gets one that walks nobody and doesn't store it, so
// the first read after a reload still walks nobody.
function placementFor(seen: Seen, name: LayoutName, now: number): Placement {
  return placed && placed.shown === (seen.project ?? '') ? placed[name] : place(name, seen, null, now)
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

// When an issue's walk out ends, one redraw takes it off the floor and the legend. One timer an issue,
// across both layouts, and it does nothing once a newer open or switch has replaced the placement or
// the pane is gone.
function endWalkOuts($: EngineInterface, known: Placement[], fresh: Placement[]): void {
  const already = new Set(known.flatMap(placement => placement.outs.map(out => out.row.number)))
  const started = new Set(fresh.flatMap(placement => placement.outs.map(out => out.row.number)))
  const open = opens
  for (const number of started) {
    if (already.has(number)) continue
    $.clock.after(WALK_MS, () => {
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
  const now = await $.clock.now()
  if ((await read($, shownAtom)) !== name) return
  if (isOpening) opens++
  const known = !isOpening && placed?.shown === name ? placed : null
  const wide = place('wide', next, known?.wide ?? null, now)
  const compact = place('compact', next, known?.compact ?? null, now)
  placed = { shown: name, wide, compact }
  endWalkOuts($, known ? [known.wide, known.compact] : [], [wide, compact])
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
    })().catch(() => {})
  })
  stopPolling = () => timer.cancel()
}

// A floor that isn't mounted, or one the terminal has since resized, answers with a deny or a rejection.
// Neither matters: the next tick paints again.
async function paint($: EngineInterface, cells: string): Promise<void> {
  try {
    await $.ui.blit({ requestId: PANE, key: FLOOR_KEY, cells })
  } catch {
    // Ignored, as above.
  }
}

// Paint the floor as it stands, never by redrawing the pane. Started from a terminal drawing, so other
// surfaces, where SMIL does this, run no timer.
function startFloor($: EngineInterface): void {
  if (stopFloor) return
  const timer = $.clock.every(TICK_MS, () => {
    void (async () => {
      if (!(await paneIsUp($))) {
        stopFloor?.()
        stopFloor = null
        return
      }
      const seen = await read($, seenAtom)
      const now = await $.clock.now()
      if (!mounted || !seen) return
      const placement = placementFor(seen, mounted, now)
      if (showsFloor(scene(seen).message, placement, now)) await paint($, floorCells(placement, now))
    })().catch(() => {})
  })
  stopFloor = () => timer.cancel()
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    // A reload fires session.start again; the directory the session started in is the first one.
    await update($, launchAtom, prev => prev ?? e.cwd)
    await $.command.register({
      name: COMMAND,
      description: 'A pane of animated figures, one for each issue the loop is working on, each acting out its step',
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
      const opened = await $.ui.open({ id: PANE, title: name ? `Loop crew: ${name}` : 'Loop crew' })
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
    if (isTerminal) startFloor($)
    const seen = await read($, seenAtom)
    const floor = isTerminal ? layoutFor(e.props.bodyColumns) : 'wide'
    if (isTerminal) mounted = null
    if (!seen) return <Text dimColor>Looking for the loop…</Text>
    const { message } = scene(seen)
    const now = await $.clock.now()
    // Too narrow for a floor, the legend still needs the issues: it reads the compact placement.
    const placement = placementFor(seen, floor ?? 'compact', now)
    if (message && !showsFloor(message, placement, now)) return <Text key="message" dimColor>{message}</Text>
    const lines = legend(placement, now)

    // The terminal draws the floor whole, even taller than the pane, and the lines that fit under it,
    // each cut to the pane's width.
    if (isTerminal && 'Raster' in elements) {
      const { Raster } = elements
      mounted = floor
      const size = floor ? LAYOUTS[floor] : null
      const bodyRows = e.props.scroll?.bodyRows
      const shown = lines.slice(0, legendFit(lines.length, bodyRows === undefined ? undefined : bodyRows - (size?.rows ?? 0)))
      return (
        <Box flexDirection="column">
          {size && <Raster key={FLOOR_KEY} columns={size.columns} rows={size.rows} cells={floorCells(placement, now)} />}
          {shown.map(({ number, line }) => <Text key={`line-${number}`}>{clip(line, e.props.bodyColumns)}</Text>)}
          {shown.length < lines.length && <Text key="more" dimColor>{`and ${lines.length - shown.length} more`}</Text>}
        </Box>
      )
    }

    // Every other surface shows the wide floor, animated by the document itself, and every line, wrapped.
    const Svg = 'Svg' in elements ? elements.Svg : null
    return (
      <Box flexDirection="column" rowGap={1}>
        {Svg && <Svg key={FLOOR_KEY} source={floorSvg(placement, now)} alt={floorAlt(placement, now)} width={256} height={192} isInteractive />}
        <Box flexDirection="column">
          {lines.map(({ number, line }) => <Text key={`line-${number}`}>{line}</Text>)}
        </Box>
      </Box>
    )
  })
}
