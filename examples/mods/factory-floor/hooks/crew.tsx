import { atom, read, update } from 'claude-code'
import type { EngineInterface, RenderElement, RenderInput } from 'claude-code'

import { DARK, LANE_ROWS, OUT_MS, PROJECTS_DIR, accentText, boardColumns, findRoot, focusFile, focusName, hasSpend, headCells, headSvg, inkFor, isCounting, laneAlt, laneCells, laneFit, laneSvg, laneWords, lanesOf, isListed, lockPid, loopDir, loopOptions, parseSpend, parseStatus, place, projectNames, scene, showsBoard, svgColumns } from './crew-logic'
import type { Ink, Lane, Placement } from './crew-logic'
import type { CrewSpend as Spend, Row, Seen } from '../types'
import { buttonRows, buttonsWidth, issueButtons, loopButtons } from './buttons'

// The Crew view: loop-crew's hooks/register.tsx moved into factory-floor's pane, with its own saved
// values under factory-floor's name. register.tsx draws it when the person presses Crew. One installed
// mod can't import from another, so this is a copy, and loop-crew stays as it is.

// The one pane factory-floor draws, the List's and the Crew's. Declared here alone: register.tsx imports it.
const PANE = 'factory-floor'
export { PANE }
const POLL_MS = 2000
// 12.5 a second: with the header and at most MAX_LANES lanes that's 112.5 blits a second at most, under
// the 120 the engine takes. A blit that didn't land is sent again in its key's turn, not as well.
const TICK_MS = 80
const MAX_LANES = 8
const HEAD_KEY = 'head'
const laneKey = (number: number): string => `lane-${number}`
// How often the other surfaces redraw while a time counts. They don't run the tick.
const REDRAW_MS = 30_000
// What the pane asks for when it opens: a board with room for three lanes. One row is the loop picker's
// and one the header's. The words take a row a lane, the lane its 3 rows, its row of times and its row of
// spend.
const WANT_COLUMNS = 72
const LANE_HEIGHT = LANE_ROWS + 3
const WANT_ROWS = 2 + 3 * LANE_HEIGHT

// The folder the session started in, which the List saves at session.start: the same value, so one key.
const launchAtom = atom({ plugin: 'factory-floor', key: 'launch' } as const, null)
const shownAtom = atom({ plugin: 'factory-floor', key: 'crew-shown' } as const, '')
const seenAtom = atom({ plugin: 'factory-floor', key: 'crew-seen' } as const, null)
// Every loop the picker lists, compared on its own: seen stays a copy of the shown loop's files, and a
// loop off screen still changes its option.
const loopsAtom = atom({ plugin: 'factory-floor', key: 'crew-loops' } as const, null)
// The session's /project focus as last read, so a poll moves the pane only when the focus has changed.
const focusAtom = atom({ plugin: 'factory-floor', key: 'crew-focus' } as const, null)
// Counts the reads of every loop, so a switch's, which nothing waits for, doesn't overwrite a newer one
// when it ends later.
let loopReads = 0

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
// Each issue's spend in its current run, by loop and number, with the row fields it was read for and the
// read itself, so two drawings at once share one read. Not an atom: seen stays a copy of the loop's own
// files, and a changed row already redraws the pane.
type Spent = { started: string | undefined; tokens: number | undefined; cost_usd: number | undefined; read: Promise<void>; spend: Spend | null }
const spends = new Map<string, Map<number, Spent>>()
function spendsOf(project: string | undefined): Map<number, Spent> {
  const loop = spends.get(project ?? '') ?? new Map<number, Spent>()
  spends.set(project ?? '', loop)
  return loop
}
const spendOf = (seen: Seen, number: number): Spend | null => spends.get(seen.project ?? '')?.get(number)?.spend ?? null
// The lanes the last drawing showed with their spend, and whose loop they were: a poll reads usage.json
// for these only, and a drawing reads it for a lane that comes into view.
let drawn: { shown: string; numbers: Set<number> } | null = null
// Whether the pane's last drawing was this view. Only then does a read of the Crew's ask for a redraw:
// the List's drawing reads none of these values.
let isOnScreen = false

// A function declaration, not an arrow bound to a const: the validator follows $ into the first only.
async function paneIsUp($: EngineInterface): Promise<boolean> {
  return (await $.ui.panes()).some(pane => pane.id === PANE)
}

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

// Copied from loop-pane's hooks/register.tsx, with the same bodies: one installed mod can't import from
// another. They only read.

// This session's focus file, the one /project and the GitHub line use, or null when the id is refused
// or can't name one. The id is asked for each time.
async function sessionFile($: EngineInterface, root: string): Promise<string | null> {
  return focusFile(root, await $.session.id().catch(() => null))
}

// The project in focus: a real folder directly under projects/ that this session's file names. A file,
// a link, a missing folder, or any failure means none. Never cached.
async function readFocus($: EngineInterface, root: string): Promise<string | null> {
  try {
    const file = await sessionFile($, root)
    if (!file) return null
    const name = focusName(await $.fs.read(file))
    if (!name) return null
    const stat = await $.fs.stat(`${root}/projects/${name}`).catch(() => null)
    return stat !== null && stat.kind === 'dir' && !stat.isLink ? name : null
  } catch {
    return null
  }
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

// One look at one loop's files, as the List takes it in register.tsx. It only reads: the loop is the
// only writer.
async function look($: EngineInterface, root: string, project?: string): Promise<Seen> {
  const dir = `${root}/${loopDir(project)}`
  const text = await $.fs.read(`${dir}/status.json`).catch(() => null)
  const alive = await lockHolderAlive($, root, project)
  return {
    root,
    ...(project ? { project } : {}),
    status: parseStatus(text),
    isLocked: alive === true,
    isStaleLock: alive === false,
    isStopping: await $.fs.exists(`${dir}/STOP`),
    hasWatchFile: await $.fs.exists(`${dir}/watch.command`),
  }
}

// Every loop the picker lists: the factory first, then each project folder holding a status file, by
// name. A loop whose status file can't be read or doesn't parse is left out, the factory's too. A
// folder that can't be listed gives the factory alone, or nothing when it's left out too.
async function readLoops($: EngineInterface, root: string): Promise<Seen[]> {
  const entries = await $.fs.list(`${root}/${PROJECTS_DIR}`).catch(() => [])
  const names = await projectNames(entries, name => $.fs.exists(`${root}/${loopDir(name)}/status.json`).catch(() => false))
  const loops = await Promise.all([look($, root), ...names.map(name => look($, root, name))])
  return loops.filter(loop => loop.status !== null)
}

// Keep a read of every loop when no newer one has started and it differs from the last. Says whether
// it was kept, so the caller asks for the redraw.
async function storeLoops($: EngineInterface, at: number, loops: Seen[]): Promise<boolean> {
  if (at !== loopReads || JSON.stringify(await read($, loopsAtom)) === JSON.stringify(loops)) return false
  await update($, loopsAtom, () => loops)
  return true
}

// Read usage.json for each lane drawn, or about to be, that has no read yet, or whose run, tokens or cost
// has changed since its last read, and for no other: a lane a short terminal pane leaves out is never
// read. A file that's missing or can't be read is no spend.
async function readSpends($: EngineInterface, seen: Seen, rows: Row[], rootKnown?: string): Promise<void> {
  const loop = spendsOf(seen.project)
  const isStale = (row: Row): boolean => {
    const known = loop.get(row.number)
    return !known || known.started !== row.started || known.tokens !== row.tokens || known.cost_usd !== row.cost_usd
  }
  const stale = rows.filter(isStale)
  const root = stale.length ? (rootKnown ?? (await rootOf($))) : null
  if (root) {
    for (const row of stale.filter(isStale)) {
      const entry: Spent = { started: row.started, tokens: row.tokens, cost_usd: row.cost_usd, read: Promise.resolve(), spend: null }
      entry.read = $.fs.read(`${root}/${loopDir(seen.project)}/issue-${row.number}/usage.json`).then(
        text => {
          const spend = parseSpend(text, row.started)
          entry.spend = hasSpend(spend) ? spend : null
        },
        () => {},
      )
      loop.set(row.number, entry)
    }
  }
  await Promise.all(rows.map(row => loop.get(row.number)?.read))
}

// An issue this loop's status file no longer lists is forgotten, so the cache holds no more than the
// loops' status files do. One still listed is kept, so a lane walking out keeps its spend.
function forgetUnlisted(seen: Seen): void {
  const loop = spendsOf(seen.project)
  const listed = new Set((seen.status?.issues ?? []).map(row => row.number))
  for (const number of [...loop.keys()]) if (!listed.has(number)) loop.delete(number)
}

// When an issue's walk out ends, one redraw takes its lane away. It does nothing once a newer open or
// switch has replaced the placement, the pane is gone, or the List is on screen.
function endWalkOuts($: EngineInterface, known: Placement | null, fresh: Placement): void {
  const already = new Set((known?.outs ?? []).map(out => out.row.number))
  const open = opens
  for (const out of fresh.outs) {
    if (already.has(out.row.number)) continue
    $.clock.after(OUT_MS, () => {
      void (async () => {
        if (open === opens && isOnScreen && (await paneIsUp($))) $.ui.invalidate('ui.render')
      })().catch(() => {})
    })
  }
}

// Read the shown loop, place its issues, and ask for a redraw only when the read differs from the last.
// A read that a switch overtook is dropped. The project is part of what's compared, so a switch always
// counts. `isOpening` is the read an open makes: it has no previous placement, even when it equals
// the last read, because a reopen can read the same data. A placement from another loop is none either.
// Every run reads every loop too, for the picker. A poll and an open wait for them, so the list is kept
// before the seen comparison and a change in either asks for one redraw between them. A switch on a
// pane already up doesn't wait: a slow read of another loop doesn't hold up the pane, and the picker
// follows with its own redraw when it differs. While the List is on screen nothing here asks for a
// redraw: the values are kept for when the Crew is drawn.
async function refresh($: EngineInterface, isOpening = false): Promise<void> {
  const root = await rootOf($)
  if (!root) return
  const name = await read($, shownAtom)
  const at = ++loopReads
  const reading = readLoops($, root)
  const isSwitch = isOpening && (await paneIsUp($))
  if (isSwitch) {
    void reading
      .then(loops => storeLoops($, at, loops))
      .then(kept => kept && isOnScreen && $.ui.invalidate('ui.render'))
      .catch(() => {})
  }
  const [next, loops] = await Promise.all([look($, root, name || undefined), isSwitch ? null : reading])
  const now = await $.clock.now()
  if ((await read($, shownAtom)) !== name) return
  forgetUnlisted(next)
  // Spend for the lanes on show whose row changed, so the redraw this read asks for has it. A switch
  // during these reads drops this one too.
  const onShow = drawn?.shown === name ? drawn.numbers : null
  if (onShow) {
    await readSpends($, next, scene(next).rows.filter(row => onShow.has(row.number)), root)
    if ((await read($, shownAtom)) !== name) return
  }
  if (isOpening) opens++
  const known = !isOpening && placed?.shown === name ? placed : null
  const placement = place(next, known?.placement ?? null, now)
  placed = { shown: name, placement }
  endWalkOuts($, known?.placement ?? null, placement)
  const loopsKept = loops !== null && (await storeLoops($, at, loops))
  const seenChanged = JSON.stringify(await read($, seenAtom)) !== JSON.stringify(next)
  if (seenChanged) await update($, seenAtom, () => next)
  if ((seenChanged || loopsKept) && isOnScreen) $.ui.invalidate('ui.render')
}

// Show a loop, by its project's name or '' for the factory: an open's and a pick's. On a pane already
// open this retitles it.
async function show($: EngineInterface, name: string) {
  await update($, shownAtom, () => name)
  await refresh($, true)
  const opened = await $.ui.open({ id: PANE, title: name ? `Loop crew: ${name}` : 'Loop crew', rows: WANT_ROWS, columns: WANT_COLUMNS })
  startPolling($)
  return opened
}

// A pick from the dropdown. Only a loop it lists, and one not already on screen, switches the pane. A
// pick never closes the pane.
async function pick($: EngineInterface, value: string, loops: Seen[]): Promise<void> {
  if (!isListed(loops, value)) return
  if ((await read($, shownAtom)) === value) return
  await show($, value)
}

// Follow the session's /project focus. Only a focus that differs from the last read moves the pane: to
// that project's loop when the picker lists it, or to the factory when the focus is cleared. Moving goes
// through a pick, so it never closes the pane. A pick holds until the focus changes.
async function follow($: EngineInterface): Promise<void> {
  const root = await rootOf($)
  if (!root) return
  const focus = await readFocus($, root)
  if (focus === (await read($, focusAtom))) return
  await update($, focusAtom, () => focus)
  await pick($, focus ?? '', await readLoops($, root))
}

// Poll only while the pane is up, so a session that never opens it reads nothing.
function startPolling($: EngineInterface): void {
  if (stopPolling) return
  const timer = $.clock.every(POLL_MS, () => {
    void (async () => {
      if (await paneIsUp($)) {
        await follow($).catch(() => {})
        return refresh($)
      }
      stopPolling?.()
      stopPolling = null
      drawn = null
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

// The Crew button: show `name`'s loop, '' for the factory, in the pane already open. The focus as it
// stands is kept, so the first poll doesn't move the pane off the loop the List had on screen. The
// theme is read here, where loop-crew read it at session.start, so a change shows on the next open.
export async function openCrew($: EngineInterface, name: string) {
  ink = await readInk($)
  const root = await rootOf($)
  if (root) {
    const focus = await readFocus($, root)
    await update($, focusAtom, () => focus)
  }
  return show($, name)
}

// The loop the Crew shows, a project's name or '' for the factory, for the List button to keep.
export async function crewShown($: EngineInterface): Promise<string> {
  return read($, shownAtom)
}

// Stop every timer the Crew runs and forget what it drew, so nothing paints, polls or reads usage.json
// while the List is on screen. Its next drawing starts them again.
export function stopCrew(): void {
  stopPolling?.()
  stopPolling = null
  stopBoard?.()
  stopBoard = null
  endRedraws()
  mounted = null
  drawn = null
  isOnScreen = false
}

// The pane's drawing in the Crew view, loop-crew's ui.render as it stood. `modes` is register.tsx's List
// and Crew buttons, drawn first with the loop's own buttons beside them, as in the List, and the rows
// they take are counted out of the room for lanes.
export async function renderCrew($: EngineInterface, e: RenderInput<'Pane'>, modes: RenderElement[]) {
  isOnScreen = true
  startPolling($)
  const elements = $.ui.resolve(e)
  const { Box, Button, Text } = elements
  const isTerminal = e.surface === 'terminal'
  if (isTerminal) startBoard($)
  else startRedraw($)
  const seen = await read($, seenAtom)
  if (isTerminal) mounted = null
  const loopRow = seen ? loopButtons($, Button, seen) : { labels: [], elements: [] }
  const top = (
    <Box key="modes" flexDirection="row" flexWrap="wrap" columnGap={1}>
      {modes}
      {loopRow.elements}
    </Box>
  )
  // On the terminal, the rows the view and loop buttons take: one, or two once they wrap.
  const topRows = isTerminal ? buttonRows(['List', 'Crew', ...loopRow.labels], e.props.bodyColumns) : 1
  if (!seen) {
    return (
      <Box flexDirection="column">
        {top}
        <Text dimColor>Looking for the loop…</Text>
      </Box>
    )
  }
  // The loop picker, above everything else but the view buttons, when there's more than one loop. The
  // mobile app draws no Select, so there the List's buttons are the only way to switch.
  const Select = e.surface === 'mobile' ? null : elements.Select
  const loops = (await read($, loopsAtom)) ?? []
  const picks = !!Select && loops.length > 1
  const picker = picks && Select && (
    <Select key="loop-pick" options={loopOptions(loops)} value={seen.project ?? ''} onSelect={value => pick($, value, loops)} />
  )
  const { message } = scene(seen)
  const now = await $.clock.now()
  const placement = placementFor(seen, now)
  if (message && !showsBoard(message, placement, now)) {
    return (
      <Box flexDirection="column">
        {top}
        {picker}
        <Text key="message" dimColor>{message}</Text>
      </Box>
    )
  }
  const lanes = lanesOf(placement, now)

  // A lane's words: where it has got to in the colour of that step, and on a terminal never the part cut.
  // Then the issue's own buttons, Watch and Open pull request, as the List has them: on a terminal the
  // title gives way to them, so the lane keeps its one line.
  const words = (lane: Lane, width?: number) => {
    const buttons = issueButtons($, Button, seen, lane.row)
    const room = width === undefined || !buttons.labels.length ? width : width - buttonsWidth(buttons.labels) - 1
    const { number, title, status } = laneWords(lane.row, room)
    return (
      <Box key={`line-${lane.row.number}`} flexDirection="row" columnGap={1}>
        <Text weight="bold">{number}</Text>
        <Text>{title}</Text>
        <Text color={accentText(lane.station)}>{status}</Text>
        {buttons.elements}
      </Box>
    )
  }

  // The terminal draws the lanes that fit, each with its words over it, and how many more there are.
  if (isTerminal && 'Raster' in elements) {
    const { Raster } = elements
    const columns = boardColumns(e.props.bodyColumns)
    const bodyRows = e.props.scroll?.bodyRows
    // The buttons' rows, the header's and the picker's come out of the room.
    const room = bodyRows === undefined ? undefined : bodyRows - topRows - (columns ? 1 : 0) - (picks ? 1 : 0)
    const fit = laneFit(lanes.length, columns ? LANE_HEIGHT : 1, room)
    const shown = lanes.slice(0, columns ? Math.min(fit, MAX_LANES) : fit)
    const more = lanes.length - shown.length
    // Only a lane with its board drawn shows spend.
    const spent = columns ? shown : []
    drawn = { shown: seen.project ?? '', numbers: new Set(spent.map(lane => lane.row.number)) }
    await readSpends($, seen, spent.map(lane => lane.row))
    mounted = columns ? { columns, numbers: shown.map(lane => lane.row.number) } : null
    const head = columns ? headCells(lanes, columns, ink) : ''
    if (columns) painted.set(HEAD_KEY, head)
    return (
      <Box flexDirection="column">
        {top}
        {picker}
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
  drawn = { shown: seen.project ?? '', numbers: new Set(lanes.map(lane => lane.row.number)) }
  await readSpends($, seen, lanes.map(lane => lane.row))
  return (
    <Box flexDirection="column" rowGap={1}>
      {top}
      {picker}
      {Svg && <Svg key={HEAD_KEY} source={headSvg(lanes, ink, columns)} alt="The loop's steps, left to right" />}
      {lanes.map(lane => (
        <Box key={`lane-box-${lane.row.number}`} flexDirection="column">
          {words(lane)}
          {Svg && <Svg key={laneKey(lane.row.number)} source={laneSvg(lane, now, ink, columns, spendOf(seen, lane.row.number))} alt={laneAlt(lane)} isInteractive />}
        </Box>
      ))}
    </Box>
  )
}
