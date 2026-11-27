import { atom, read, update } from 'claude-code'
import type { EngineInterface, RenderElement, RenderInput } from 'claude-code'

import { ALL, DARK, LANE_ROWS, NOTHING, OUT_MS, PROJECTS_DIR, accentText, boardColumns, downOption, findRoot, focusFile, focusName, hasSpend, headCells, headSvg, inkFor, isCounting, laneAlt, laneCells, laneFit, laneSvg, laneWords, lanesOf, isListed, lockPid, loopDir, loopOptions, loopTag, loopValue, parseSpend, parseStatus, pickerOrder, place, projectNames, scene, showsBoard, svgColumns } from './crew-logic'
import type { Ink, Lane, Placement } from './crew-logic'
import { TITLE, single } from './logic'
import type { Down } from './logic'
import type { CrewSpend as Spend, Row, Seen } from '../types'
import { buttonRows, buttonsWidth, issueButtons, loopButtons } from './buttons'
import { pollRemote, remoteLoop, remoteNow, remoteUsage, resetRemote } from './remote'

// The Crew view: loop-crew's hooks/register.tsx moved into factory-floor's pane, with its own saved
// values under factory-floor's name. register.tsx draws it when the person presses Crew. One installed
// mod can't import from another, so this is a copy, and loop-crew stays as it is.

// The one pane factory-floor draws, the List's and the Crew's. Declared here alone: register.tsx imports it.
const PANE = 'factory-floor'
export { PANE }
const POLL_MS = 2000
// A poll that hasn't settled after this many polls were turned away, 16 seconds, is given up on (#759).
const GIVE_UP_POLLS = 8
// 12.5 a second: with the header and at most MAX_LANES lanes that's 112.5 blits a second at most, under
// the 120 the engine takes. A blit that didn't land is sent again in its key's turn, not as well.
const TICK_MS = 80
const MAX_LANES = 8
const HEAD_KEY = 'head'
// A lane's key. One loop's lanes have no prefix, lane-12; under All loops each carries its loop's value,
// lane-alpha#12, so two loops' #12 are two lanes.
const laneKey = (prefix: string, number: number): string => `lane-${prefix}${number}`
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
// The other machines that are down, and the lines saying which machines.json skips, as the last read of
// every loop kept them. Not an atom: storeLoops compares it and asks for the redraw.
let remoteShown: { down: Down[]; refusals: string[] } = { down: [], refusals: [] }

let stopPolling: (() => void) | null = null
let stopBoard: (() => void) | null = null
let stopRedraw: (() => void) | null = null
// Not atoms: a write would redraw the pane, and a walk is painted with no redraw. Each loop on screen
// keeps its own placement, by its picker value: the one loop shown, or under All loops every loop.
let placed: { shown: string; placements: Map<string, Placement> } | null = null
// What the terminal's drawing mounted, by lane key, so a tick paints only those at their size. Null: no
// board is drawn.
let mounted: { columns: number; keys: string[] } | null = null
// What each Raster last showed, so a tick that changes nothing paints nothing.
const painted = new Map<string, string>()
let ink: Ink = DARK
// Counts the reads that open or switch the pane, so a walk-out's timer knows it's been overtaken.
let opens = 0
// Each issue's spend in its current run, by loop and number, with the row fields it was read for and the
// read itself, so two drawings at once share one read. Not an atom: seen stays a copy of the loop's own
// files, and a changed row already redraws the pane. A loop is keyed by its picker value, so another
// machine's project never shares this one's spend.
type Spent = { started: string | undefined; tokens: number | undefined; cost_usd: number | undefined; read: Promise<void>; spend: Spend | null }
const spends = new Map<string, Map<number, Spent>>()
function spendsOf(value: string): Map<number, Spent> {
  const loop = spends.get(value) ?? new Map<number, Spent>()
  spends.set(value, loop)
  return loop
}
const spendOf = (seen: Seen, number: number): Spend | null => spends.get(loopValue(seen))?.get(number)?.spend ?? null
// The lanes the last drawing showed with their spend, by each loop's picker value, and what the view
// showed, a loop's value or ALL: a poll reads usage.json for these only, and a drawing reads it for a lane
// that comes into view.
let drawn: { shown: string; lanes: Map<string, Set<number>> } | null = null
// Whether the pane's last drawing was this view. Only then does a read of the Crew's ask for a redraw:
// the List's drawing reads none of these values.
let isOnScreen = false
// A redraw the Crew would have asked for while the pane was behind another, which the first poll once it's
// shown asks for instead (#759). Whether a read since the poll began asked for one, so that poll asks once.
let missedRedraw = false
let askedRedraw = false

// The Crew's own redraws: only for a pane on show, and remembered for one behind another pane.
function redraw($: EngineInterface, isShown = true): void {
  if (!isShown) {
    missedRedraw = true
    return
  }
  askedRedraw = true
  $.ui.invalidate('ui.render')
}

// A function declaration, not an arrow bound to a const: the validator follows $ into the first only.
async function paneIsUp($: EngineInterface): Promise<boolean> {
  return (await $.ui.panes()).some(pane => pane.id === PANE)
}

// The placement to draw for one loop on screen. Before any read, a draw gets one that walks nobody and
// doesn't store it, so the first read after a reload still walks nobody. Under All loops the placements
// kept are every loop's, else the one loop's.
function placementFor(seen: Seen, now: number, isAll = false): Placement {
  const shown = isAll ? ALL : loopValue(seen)
  return (placed?.shown === shown ? placed.placements.get(loopValue(seen)) : undefined) ?? place(seen, null, now)
}

// One lane on screen, with the loop it's from. Under All loops it has that loop's tag and a key prefix
// holding the loop's value; for one loop, neither, so its keys are as they always were.
type OnScreen = { seen: Seen; lane: Lane; prefix: string; tag: string | null }

// Every lane on screen, loop by loop in the order given, each loop's in issue-number order.
function onScreen(seens: Seen[], isAll: boolean, now: number): OnScreen[] {
  return seens.flatMap(seen => {
    const prefix = isAll ? `${loopValue(seen)}#` : ''
    const tag = isAll ? loopTag(seen) : null
    return lanesOf(placementFor(seen, now, isAll), now).map((lane): OnScreen => ({ seen, lane, prefix, tag }))
  })
}

// The loops the Crew has on screen: the shown loop's last look, or under All loops every loop the picker
// lists, in its order.
async function shownLoops($: EngineInterface): Promise<{ isAll: boolean; seens: Seen[] }> {
  if ((await read($, shownAtom)) === ALL) return { isAll: true, seens: pickerOrder((await read($, loopsAtom)) ?? []) }
  const seen = await read($, seenAtom)
  return { isAll: false, seens: seen ? [seen] : [] }
}

// Each loop's lanes among `lanes`, by its picker value, for drawn.
function lanesByLoop(seens: Seen[], lanes: OnScreen[]): Map<string, Set<number>> {
  return new Map(seens.map((seen): [string, Set<number>] => [loopValue(seen), new Set(lanes.filter(s => s.seen === seen).map(s => s.lane.row.number))]))
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
// name, then other machines' loops as their last background read left them. A loop whose status file
// can't be read or doesn't parse is left out, the factory's too. A folder that can't be listed gives the
// factory alone, or nothing when it's left out too. Nothing here waits on ssh.
async function readLoops($: EngineInterface, root: string): Promise<Seen[]> {
  const entries = await $.fs.list(`${root}/${PROJECTS_DIR}`).catch(() => [])
  const names = await projectNames(entries, name => $.fs.exists(`${root}/${loopDir(name)}/status.json`).catch(() => false))
  const loops = await Promise.all([look($, root), ...names.map(name => look($, root, name))])
  return [...loops, ...remoteNow().loops].filter(loop => loop.status !== null)
}

// The loop a picker value names: another machine's as last read, or null once that machine isn't
// listed or answering, else this machine's, read now. All loops names no one loop, so it's null: refresh
// reads every loop for it.
async function lookShown($: EngineInterface, root: string, name: string): Promise<Seen | null> {
  if (name === ALL) return null
  if (name.includes('/')) return remoteLoop(name)
  return look($, root, name || undefined)
}

// Keep a read of every loop when no newer one has started and it, or what's known of the machines that
// are down or skipped, differs from the last. Says whether it was kept, so the caller asks for the redraw.
async function storeLoops($: EngineInterface, at: number, loops: Seen[]): Promise<boolean> {
  if (at !== loopReads) return false
  const { down, refusals } = remoteNow()
  const extras = { down, refusals }
  const sameLoops = JSON.stringify(await read($, loopsAtom)) === JSON.stringify(loops)
  if (sameLoops && JSON.stringify(extras) === JSON.stringify(remoteShown)) return false
  remoteShown = extras
  if (!sameLoops) await update($, loopsAtom, () => loops)
  return true
}

// Read usage.json for each lane drawn, or about to be, that has no read yet, or whose run, tokens or cost
// has changed since its last read, and for no other: a lane a short terminal pane leaves out is never
// read. A file that's missing or can't be read is no spend. Another machine's lane takes what its
// usage.json held at the read that gave its row, which remote.ts read with cat over ssh in the background:
// a drawing never waits on ssh.
async function readSpends($: EngineInterface, seen: Seen, rows: Row[], rootKnown?: string): Promise<void> {
  const loop = spendsOf(loopValue(seen))
  const isStale = (row: Row): boolean => {
    const known = loop.get(row.number)
    return !known || known.started !== row.started || known.tokens !== row.tokens || known.cost_usd !== row.cost_usd
  }
  const stale = rows.filter(isStale)
  if (seen.machineIndex !== undefined) {
    for (const row of stale) {
      const spend = parseSpend(remoteUsage(seen, row), row.started)
      loop.set(row.number, { started: row.started, tokens: row.tokens, cost_usd: row.cost_usd, read: Promise.resolve(), spend: hasSpend(spend) ? spend : null })
    }
    return
  }
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
  const loop = spendsOf(loopValue(seen))
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
        if (open !== opens || !isOnScreen) return
        const pane = (await $.ui.panes()).find(p => p.id === PANE)
        if (pane) redraw($, pane.isShown)
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
// redraw: the values are kept for when the Crew is drawn. Behind another pane it reads and writes nothing,
// since a write would redraw the pane; the first read once it's shown writes what changed (#759).
async function refresh($: EngineInterface, isOpening = false, isShown = true): Promise<void> {
  const root = await rootOf($)
  if (!root) return
  let name = await read($, shownAtom)
  // Another machine's loop that's no longer listed or answering falls back to the factory, as the List's does.
  if (name.includes('/') && !remoteLoop(name)) {
    name = ''
    if (isShown) await update($, shownAtom, () => name)
  }
  const at = ++loopReads
  const reading = readLoops($, root)
  // All loops draws every loop's lanes, so it waits for every loop. With fewer than two loops it falls
  // back to the factory, as the List's does.
  if (name === ALL) {
    const loops = await reading
    if (isListed(loops, ALL)) return isShown ? refreshAll($, root, at, loops, isOpening) : undefined
    name = ''
    if (isShown) await update($, shownAtom, () => name)
  }
  const isSwitch = isOpening && (await paneIsUp($))
  if (isSwitch) {
    void reading
      .then(loops => storeLoops($, at, loops))
      .then(kept => kept && isOnScreen && $.ui.invalidate('ui.render'))
      .catch(() => {})
  }
  const [shown, loops] = await Promise.all([lookShown($, root, name), isSwitch ? null : reading])
  if (!isShown) return
  const now = await $.clock.now()
  if ((await read($, shownAtom)) !== name || !shown) return
  const next = shown
  forgetUnlisted(next)
  // Spend for the lanes on show whose row changed, so the redraw this read asks for has it. A switch
  // during these reads drops this one too.
  const onShow = drawn?.shown === name ? (drawn.lanes.get(name) ?? null) : null
  if (onShow) {
    await readSpends($, next, scene(next).rows.filter(row => onShow.has(row.number)), root)
    if ((await read($, shownAtom)) !== name) return
  }
  if (isOpening) opens++
  const known = !isOpening && placed?.shown === name ? (placed.placements.get(name) ?? null) : null
  const placement = place(next, known, now)
  placed = { shown: name, placements: new Map([[name, placement]]) }
  endWalkOuts($, known, placement)
  const loopsKept = loops !== null && (await storeLoops($, at, loops))
  const seenChanged = JSON.stringify(await read($, seenAtom)) !== JSON.stringify(next)
  if (seenChanged) await update($, seenAtom, () => next)
  if ((seenChanged || loopsKept) && isOnScreen) redraw($)
}

// refresh under All loops, with every loop read: each loop is placed against its own last placement, so a
// lane walks as it would on its own loop, and the spend of each lane on show is read as one loop's is.
// The loops it draws are the ones kept, so a change in any asks for the redraw, and so does an open.
async function refreshAll($: EngineInterface, root: string, at: number, loops: Seen[], isOpening: boolean): Promise<void> {
  const now = await $.clock.now()
  if ((await read($, shownAtom)) !== ALL) return
  for (const seen of loops) forgetUnlisted(seen)
  const onShow = drawn?.shown === ALL ? drawn.lanes : null
  if (onShow) {
    await Promise.all(loops.map(seen => readSpends($, seen, scene(seen).rows.filter(row => onShow.get(loopValue(seen))?.has(row.number)), root)))
    if ((await read($, shownAtom)) !== ALL) return
  }
  if (isOpening) opens++
  const known = !isOpening && placed?.shown === ALL ? placed.placements : null
  const placements = new Map<string, Placement>()
  for (const seen of loops) {
    const before = known?.get(loopValue(seen)) ?? null
    const placement = place(seen, before, now)
    placements.set(loopValue(seen), placement)
    endWalkOuts($, before, placement)
  }
  placed = { shown: ALL, placements }
  const kept = await storeLoops($, at, loops)
  if ((kept || isOpening) && isOnScreen) redraw($)
}

// Show a loop, by its picker value: a project's name, '' for the factory, ssh:<i>/… for another
// machine's, or ALL for every loop. An open's and a pick's. The title stays the mod's whichever loop is
// shown: the picker says which.
async function show($: EngineInterface, name: string) {
  await update($, shownAtom, () => name)
  await refresh($, true)
  const opened = await $.ui.open({ id: PANE, title: TITLE, rows: WANT_ROWS, columns: WANT_COLUMNS })
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
  // One poll's work at a time: a poll that fires while the last is still reading does nothing (#759).
  const poll = single(async () => {
    const pane = (await $.ui.panes()).find(p => p.id === PANE)
    if (pane) {
      // Other machines are read only from here and the List's poll, at most every 30 seconds each, in
      // the background.
      const root = await rootOf($)
      if (root) await pollRemote($, root).catch(() => {})
      // Behind another pane the focus isn't followed either: a pick would write and redraw.
      if (!pane.isShown) return refresh($, false, false)
      await follow($).catch(() => {})
      askedRedraw = false
      await refresh($)
      if (missedRedraw && !askedRedraw && isOnScreen) $.ui.invalidate('ui.render')
      missedRedraw = false
      return
    }
    stopPolling?.()
    stopPolling = null
    drawn = null
    endRedraws()
    resetRemote()
  }, GIVE_UP_POLLS)
  const timer = $.clock.every(POLL_MS, () => {
    void poll().catch(() => {})
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
      const pane = (await $.ui.panes()).find(p => p.id === PANE)
      if (!pane) return endRedraws()
      const { isAll, seens } = await shownLoops($)
      const now = await $.clock.now()
      // Behind another pane, a moving time waits until it's shown again.
      if (onScreen(seens, isAll, now).some(s => isCounting(s.lane))) redraw($, pane.isShown)
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
      const { isAll, seens } = await shownLoops($)
      const now = await $.clock.now()
      const first = seens[0]
      if (!mounted || !first || !pane.isShown) return
      // Under All loops the board shows while any loop has a lane; one loop's shows by its own message.
      const lanes = onScreen(seens, isAll, now)
      if (isAll ? !lanes.length : !showsBoard(scene(first).message, placementFor(first, now), now)) return
      await paint($, HEAD_KEY, headCells(lanes.map(s => s.lane), mounted.columns, ink))
      for (const key of mounted.keys) {
        const s = lanes.find(l => laneKey(l.prefix, l.lane.row.number) === key)
        if (s) await paint($, key, laneCells(s.lane, mounted.columns, now, ink, spendOf(s.seen, s.lane.row.number)))
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

// The loop the Crew shows, by its picker value, ALL for every loop, for the List button to keep.
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
  missedRedraw = false
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
  // The loops on screen: the one shown, or under All loops every loop, which has no buttons of one loop's own.
  const { isAll, seens } = await shownLoops($)
  const seen = isAll ? null : (seens[0] ?? null)
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
  const first = seens[0]
  if (!first) {
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
  // A machine that's down is an option too, and picking it does nothing: isListed doesn't list it.
  const { down, refusals } = remoteShown
  const picks = !!Select && loops.length + down.length > 1
  // How long ago a machine that's down answered, for its option and, under All loops, its line.
  const downNow = down.length && (picks || isAll) ? await $.clock.now() : 0
  const options = picks ? loopOptions(loops, down, downNow) : []
  const picker = picks && Select && (
    <Select key="loop-pick" options={options} value={isAll ? ALL : loopValue(first)} onSelect={value => pick($, value, loops)} />
  )
  // Each machine machines.json skips, and why, under the picker, a row each. Under All loops, each machine
  // that's down adds no lanes, and a row says so and when it last answered.
  const skipped = [
    ...refusals.map((line, i) => (
      <Text key={`refusal-${i}`} dimColor>
        {line}
      </Text>
    )),
    ...(isAll ? down : []).map(d => (
      <Text key={`down-${d.index}`} dimColor>
        {downOption(d, downNow).label}
      </Text>
    )),
  ]
  const now = await $.clock.now()
  // Under All loops the lanes are every loop's, and with none the pane says nothing is being built. One
  // loop's say what its own scene says.
  const lanes = onScreen(seens, isAll, now)
  const message = isAll ? (lanes.length ? null : NOTHING) : scene(first).message
  if (message && (isAll || !showsBoard(message, placementFor(first, now), now))) {
    return (
      <Box flexDirection="column">
        {top}
        {picker}
        {skipped}
        <Text key="message" dimColor>{message}</Text>
      </Box>
    )
  }

  // A lane's words: under All loops its loop's tag first, then where it has got to in the colour of that
  // step, and on a terminal never the part cut. Then the issue's own buttons, Watch and Open pull request,
  // as the List has them: on a terminal the title gives way to them, so the lane keeps its one line.
  const words = ({ seen: loop, lane, prefix, tag }: OnScreen, width?: number) => {
    const buttons = issueButtons($, Button, loop, lane.row, 'Open pull request', prefix)
    const room = width === undefined || !buttons.labels.length ? width : width - buttonsWidth(buttons.labels) - 1
    const tagged = tag === null ? 0 : tag.length + 1
    const { number, title, status } = laneWords(lane.row, room === undefined ? room : room - tagged)
    return (
      <Box key={`line-${prefix}${lane.row.number}`} flexDirection="row" columnGap={1}>
        <Text weight="bold">{tag === null ? number : `${tag} ${number}`}</Text>
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
    // The buttons' rows, the header's, the picker's and a row for each machine machines.json skips, or
    // under All loops that's down, come out of the room.
    const room = bodyRows === undefined ? undefined : bodyRows - topRows - (columns ? 1 : 0) - (picks ? 1 : 0) - skipped.length
    const fit = laneFit(lanes.length, columns ? LANE_HEIGHT : 1, room)
    const shown = lanes.slice(0, columns ? Math.min(fit, MAX_LANES) : fit)
    const more = lanes.length - shown.length
    // Only a lane with its board drawn shows spend.
    const spent = columns ? shown : []
    drawn = { shown: isAll ? ALL : loopValue(first), lanes: lanesByLoop(seens, spent) }
    await Promise.all(seens.map(loop => readSpends($, loop, spent.filter(s => s.seen === loop).map(s => s.lane.row))))
    mounted = columns ? { columns, keys: shown.map(s => laneKey(s.prefix, s.lane.row.number)) } : null
    const head = columns ? headCells(lanes.map(s => s.lane), columns, ink) : ''
    if (columns) painted.set(HEAD_KEY, head)
    return (
      <Box flexDirection="column">
        {top}
        {picker}
        {skipped}
        {columns && <Raster key={HEAD_KEY} columns={columns} rows={1} cells={head} />}
        {shown.map(s => {
          const key = laneKey(s.prefix, s.lane.row.number)
          const cells = columns ? laneCells(s.lane, columns, now, ink, spendOf(s.seen, s.lane.row.number)) : ''
          if (columns) painted.set(key, cells)
          return (
            <Box key={`lane-box-${s.prefix}${s.lane.row.number}`} flexDirection="column">
              {words(s, e.props.bodyColumns)}
              {columns && <Raster key={key} columns={columns} rows={LANE_ROWS + 2} cells={cells} />}
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
  drawn = { shown: isAll ? ALL : loopValue(first), lanes: lanesByLoop(seens, lanes) }
  await Promise.all(seens.map(loop => readSpends($, loop, lanes.filter(s => s.seen === loop).map(s => s.lane.row))))
  return (
    <Box flexDirection="column" rowGap={1}>
      {top}
      {picker}
      {skipped}
      {Svg && <Svg key={HEAD_KEY} source={headSvg(lanes.map(s => s.lane), ink, columns)} alt="The loop's steps, left to right" />}
      {lanes.map(s => (
        <Box key={`lane-box-${s.prefix}${s.lane.row.number}`} flexDirection="column">
          {words(s)}
          {Svg && <Svg key={laneKey(s.prefix, s.lane.row.number)} source={laneSvg(s.lane, now, ink, columns, spendOf(s.seen, s.lane.row.number))} alt={laneAlt(s.lane)} isInteractive />}
        </Box>
      ))}
    </Box>
  )
}
