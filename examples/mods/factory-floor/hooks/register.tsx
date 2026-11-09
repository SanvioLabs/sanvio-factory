import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import { PAGE,PROJECTS_DIR, TABS, attach, changes, clip, clock, describe, dot, findRoot, firstTab, focusFile, focusName, header, isPulsing, isWebLink, jobAttach, jobWatchFile, lists, lockPid, loopButtonLabel, loopCounts, loopDir, loopOptions, openingLoop, page, parseStatus, projectName, projectNames, sameSeen, waitingOn, watch, watchCommand } from './logic'
import type { Lists, Tone } from './logic'
import { PANE, crewShown, openCrew, renderCrew, stopCrew } from './crew'
import { MIN_COLUMNS } from './crew-logic'
import type { Mode, Row, Seen, Tab, View } from '../types'

// Not /loop: that's Claude Code's own command for running a prompt on a schedule. It sits beside /factory-dashboard.
const COMMAND = 'factory-floor'
// The retired mods' commands, kept until a later release. Each opens this pane in the view that mod
// showed, never closes it, and says the new name.
const ALIASES = [
  { name: 'loop-pane', view: 'list', description: 'Now /factory-floor: opens the loop pane in the List view' },
  { name: 'loop-crew', view: 'crew', description: 'Now /factory-floor: opens the loop pane in the Crew view' },
] as const
const aliasToast = (name: string) => `/${name} is now /${COMMAND}. The old name goes in a later release.`
const POLL_MS = 2000
// The pulse's half beat. The pane redraws this often only while a job's dot is pulsing.
const TICK_MS = 500

const launchAtom = atom({ plugin: 'factory-floor', key: 'launch' } as const, null)
const seenAtom = atom({ plugin: 'factory-floor', key: 'seen' } as const, null)
const viewAtom = atom({ plugin: 'factory-floor', key: 'view' } as const, null)
const loopsAtom = atom({ plugin: 'factory-floor', key: 'loops' } as const, null)
const pickedAtom = atom({ plugin: 'factory-floor', key: 'picked' } as const, null)
// The project in focus as last read from this session's file, or null, so a read can tell it changed.
const focusAtom = atom({ plugin: 'factory-floor', key: 'focus' } as const, null)
// The view the person picked with the List and Crew buttons. Each /factory-floor opens on the List.
const modeAtom = atom({ plugin: 'factory-floor', key: 'mode' } as const, 'list')
// The view the pane last drew. Only that view's poll runs and asks for redraws: the other's values
// wait until it's drawn again. Not an atom: a write would redraw the pane.
let drawnView: Mode | null = null
// A pick saving the focus: how many saves are under way, and a count bumped as each starts and ends.
// Between a save's write and its read back, the file says what the pane already shows, and a read
// landing there mustn't take it for a change.
let saving = 0
let saves = 0

const COLORS: Record<Tone, { color?: string; bold?: boolean; dimColor?: boolean }> = {
  now: { color: 'cyan', bold: true },
  pass: { color: 'green', bold: true },
  fail: { color: 'red', bold: true },
  quiet: { dimColor: true },
  idle: { color: 'green', dimColor: true },
}

// A working job's dot, on alternate ticks. Bright and dim rather than on and off: a dot that vanishes
// every other frame reads as a redraw glitch.
const PULSE = { bright: { color: 'cyan', bold: true }, dim: { color: 'cyan', dimColor: true } } as const
let beat = true

// A job's rows: its title, when it started, where it is, two for the last round's results, and its
// pull request.
const JOB_ROWS = 6

// The rows around the list: the header's two, the buttons, the rule, the loop picker, the tabs, and the
// lines above and below it.
const AROUND_LIST = 8

// How many jobs fit the pane's height, and never fewer than PAGE. The finite check is for Infinity, which
// would otherwise pass the minimum, and for a height that isn't there.
function jobsInView(bodyRows?: number): number {
  const fits = Math.floor(((bodyRows ?? NaN) - AROUND_LIST) / (JOB_ROWS + 1))
  return Number.isFinite(fits) && fits >= PAGE ? fits : PAGE
}

// How many items a tab shows at once. Queue's are a line each, so it fits as many as that many jobs' rows hold.
const pageSize = (tab: Tab, bodyRows?: number): number =>
  tab === 'queue' ? jobsInView(bodyRows) * (JOB_ROWS + 1) : jobsInView(bodyRows)

const EMPTY: Record<Tab, string> = {
  queue: 'Nothing waiting. Label an issue loop-ready to queue it.',
  active: 'Nothing being worked on.',
  finished: 'Nothing finished in the last 24 hours.',
}

let stopPolling: (() => void) | null = null

// A watch file opens a read-only Terminal window; closing it leaves the loop running. When it can't
// open, the buttons copy the command that does the same.
const WATCH_TOAST = "Couldn't open a window, so the read-only attach command is copied"

// Open a target with the first opener that works; when none does, copy what stands in for it and say
// so. A rejected run counts as that opener failing, so a missing `open` still reaches the next.
function openOrCopy($: EngineInterface, target: string, openers: string[], copy: () => Promise<unknown>, toast: string): void {
  void (async () => {
    for (const opener of openers) {
      const ran = await $.process.run([opener, target]).catch(() => null)
      if (ran?.exitCode === 0) return
    }
    await copy()
    $.ui.toast(toast)
  })().catch(() => {})
}

// Open a job's pull request in the browser. A link that isn't a web link reaches no opener, since
// `open` would run a local file or app: it's only copied.
function openPullRequest($: EngineInterface, link: string, surface: Parameters<EngineInterface['ui']['copy']>[0]['surface']): void {
  const copy = () => $.ui.copy({ text: link, surface })
  if (!isWebLink(link)) openOrCopy($, link, [], copy, "That pull request link isn't a web link, so it's copied")
  else openOrCopy($, link, ['open', 'xdg-open'], copy, "Couldn't open the browser, so the pull request link is copied")
}

// The tab in view and its first job, kept inside the list. Before the person picks, the busiest tab.
function current(view: View | null, l: Lists, bodyRows?: number): View {
  const tab = view?.tab ?? firstTab(l)
  return { tab, start: page(l[tab], view?.tab ? view.start : 0, pageSize(tab, bodyRows)).start }
}

// Move the tab's list by `by`: jobs on Active and Finished, lines on Queue. Says whether it moved: at
// either end it doesn't.
async function move($: EngineInterface, by: number, bodyRows?: number): Promise<boolean> {
  const seen = await read($, seenAtom)
  const l = lists(seen?.status ?? null, Date.now())
  const now = current(await read($, viewAtom), l, bodyRows)
  const next = page(l[now.tab], now.start + by, pageSize(now.tab, bodyRows)).start
  if (next === now.start) return false
  await update($, viewAtom, () => ({ tab: now.tab, start: next }))
  return true
}

// The folder saved at session.start first, then the session's root: a /clear starts a new session
// without a session.start, so the saved folder can be missing or the last session's.
async function rootOf($: EngineInterface): Promise<string | null> {
  const exists = (path: string) => $.fs.exists(path)
  const launch = await read($, launchAtom)
  return (launch && (await findRoot(launch, exists))) || findRoot(await $.session.root(), exists)
}

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

// Writes this session's focus file. False, with nothing written, when the id or the write fails.
async function saveFocus($: EngineInterface, root: string, text: string): Promise<boolean> {
  const file = await sessionFile($, root)
  if (!file) return false
  return $.fs.write(file, text).then(() => true, () => false)
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

// Look at every loop and show the picked one. Each loop is compared with its own last look: against
// the one on screen, every switch would look like a change, and a loop off screen would never tell.
async function refresh($: EngineInterface): Promise<void> {
  const root = await rootOf($)
  if (!root) return
  const entries = await $.fs.list(`${root}/${PROJECTS_DIR}`).catch(() => [])
  const names = await projectNames(entries, name => $.fs.exists(`${root}/${loopDir(name)}/status.json`))
  const factory = await look($, root)
  const loops = [factory, ...(await Promise.all(names.map(name => look($, root, name))))]
  const was = (await read($, loopsAtom)) ?? []
  const before = await read($, seenAtom)
  const stored = await read($, pickedAtom)
  let picked = stored
  // Once a loop is on screen, a change in the session's focus moves the pane: to the project now in
  // focus when it has a loop listed, to the factory when the focus is cleared. A focus on a project
  // with no loop listed is remembered and moves nothing, so the loop appearing later doesn't either.
  // A read that overlaps a pick's save is left alone: the save sets the remembered focus itself.
  if (picked !== null) {
    const at = saves
    const focus = await readFocus($, root)
    const known = await read($, focusAtom)
    if (saving === 0 && at === saves && focus !== known) {
      await update($, focusAtom, () => focus)
      if (focus === null) picked = ''
      else if (loops.some(l => l.project === focus)) picked = focus
    }
  }
  // No pick yet is an opening, on the focus read as the pane opened. A pick whose project has gone
  // falls back to the factory.
  const shown =
    (picked === null ? openingLoop(loops, await read($, focusAtom)) : loops.find(l => (l.project ?? '') === picked)) ?? factory
  const pick = shown.project ?? ''
  if (stored !== pick) await update($, pickedAtom, () => pick)
  if (sameSeen(before, shown) && JSON.stringify(was) === JSON.stringify(loops)) return
  // Another loop opens on its busiest tab, as it does when pressed.
  if (before?.project !== shown.project) await update($, viewAtom, () => null)
  await update($, loopsAtom, () => loops)
  await update($, seenAtom, () => shown)
  for (const loop of loops) {
    const last = was.find(l => l.project === loop.project)
    for (const line of changes(last?.status ?? null, loop.status, loop.project)) $.ui.toast(line)
  }
  if (drawnView !== 'crew') $.ui.invalidate('ui.render')
}

// Show another loop, from its last look, on its busiest tab. The pick holds until the pane is closed and
// opened again, which picks again, or the session's focus changes.
async function show($: EngineInterface, loop: Seen): Promise<void> {
  await update($, pickedAtom, () => loop.project ?? '')
  await update($, seenAtom, () => loop)
  await update($, viewAtom, () => null)
  // Then the pick becomes the session's focus, after the switch so a failed or slow write never holds
  // it up. A project whose name isn't one projectName passes as it stands is never written: ` acme`
  // would be read back as acme, another project.
  const name = loop.project
  const parsed = name ? projectName(name) : null
  const text = !name ? '' : parsed && 'name' in parsed && parsed.name === name ? `${name}\n` : null
  if (text === null) return
  saving++
  saves++
  try {
    const root = await rootOf($)
    if (!root || !(await saveFocus($, root, text))) return
    // What the file now means, not the name picked: a loop with no projects/<name> folder means none.
    const focus = await readFocus($, root)
    await update($, focusAtom, () => focus)
  } catch {
    // The pane has already switched; a focus that can't be saved leaves the remembered one alone.
  } finally {
    saving--
    saves++
  }
}

// Poll only while the pane is up, so a session that never opens it reads nothing.
function startPolling($: EngineInterface): void {
  if (stopPolling) return
  // every() hands back a timer, not a function: calling it threw, so the poll outlived the pane.
  // It ticks at the pulse's pace and reads the loop's files on every POLL_MS / TICK_MS-th tick.
  let ticks = 0
  const timer = $.clock.every(TICK_MS, () => {
    void (async () => {
      const isUp = (await $.ui.panes()).some(pane => pane.id === PANE)
      if (!isUp) {
        stopPolling?.()
        stopPolling = null
        return
      }
      beat = !beat
      const isRead = ticks++ % (POLL_MS / TICK_MS) === 0
      if (isRead) await refresh($)
      // The dot and the running clock move between reads, so redraw for them while a job is on. The
      // header's uptime moves too, so a live loop redraws at least at every read.
      const seen = await read($, seenAtom)
      if (drawnView !== 'crew' && (isPulsing(seen) || (isRead && seen?.isLocked))) $.ui.invalidate('ui.render')
    })().catch(() => {})
  })
  stopPolling = () => timer.cancel()
}

// While the Crew is drawn the List reads nothing: its tick looks for the pane twice a second.
function stopList(): void {
  stopPolling?.()
  stopPolling = null
}

// The Crew button: the loop the List has on screen, in the Crew's lanes. The Crew reads it before the
// view changes, so its reads ask for no redraws of their own; the change of mode draws it.
async function toCrew($: EngineInterface): Promise<void> {
  if (drawnView === 'crew') return
  const seen = await read($, seenAtom)
  await openCrew($, seen?.project ?? '')
  await update($, modeAtom, () => 'crew')
}

// The List button: the loop the Crew has on screen, in the List, without writing the session's focus.
// The focus as it stands is kept, so the List's next read doesn't move it off that loop. Neither button
// closes the pane.
async function toList($: EngineInterface): Promise<void> {
  if (drawnView === 'list' && (await read($, modeAtom)) === 'list') return
  const shown = await crewShown($)
  await update($, pickedAtom, () => shown)
  const root = await rootOf($)
  if (root) {
    const focus = await readFocus($, root)
    await update($, focusAtom, () => focus)
  }
  stopCrew()
  await update($, modeAtom, () => 'list')
  await $.ui.open({ id: PANE, title: 'Loop' })
  await refresh($)
  startPolling($)
}

const CANT_OPEN = "The loop pane couldn't open. .loop/loop.log has the same story: tail -f .loop/loop.log"

// Open the pane on the List, whether or not it's up: /factory-floor's open and the aliases'. Opening
// picks again: the project in focus when it has a loop, else the first loop running, else the factory.
// The focus read here is remembered, so it isn't a change, and opening writes nothing. It opens on the
// List, also after the × closed the pane in the Crew view.
async function openPane($: EngineInterface): Promise<{ text: string; isOpen: boolean }> {
  try {
    const root = await rootOf($)
    if (!root) return { text: `No scripts/loop.py at or above ${await $.session.root()}, so there is no loop to show.`, isOpen: false }
    stopCrew()
    drawnView = null
    await update($, modeAtom, () => 'list')
    await update($, pickedAtom, () => null)
    const focus = await readFocus($, root)
    await update($, focusAtom, () => focus)
    await refresh($)
    const opened = await $.ui.open({ id: PANE, title: 'Loop' })
    startPolling($)
    return { text: opened.isPlaced ? 'Loop pane opened.' : 'Loop pane opened. Widen the terminal to see it.', isOpen: true }
  } catch {
    return { text: CANT_OPEN, isOpen: false }
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    // A reload fires session.start again; the directory the session started in is the first one.
    await update($, launchAtom, prev => prev ?? e.cwd)
    await $.command.register({
      name: COMMAND,
      description: "Open or close a pane showing the loop: what's waiting, what each issue is on, and its pull request",
    })
    // Each alias on its own: one refused, say while the old mod is still on, leaves the other and
    // /factory-floor working.
    for (const alias of ALIASES) {
      try {
        await $.command.register({ name: alias.name, description: alias.description })
      } catch {
        // The old name stays with whatever holds it.
      }
    }
    // A pane left open across a reload keeps updating.
    if ((await $.ui.panes()).some(pane => pane.id === PANE)) startPolling($)
    return next(e)
  })

  on('command.run', { command: COMMAND }, async $ => {
    try {
      // A pane in view closes, before the root is looked for: one whose root has gone still closes. One
      // behind another or not placed isn't in view, so it opens. The poll stops itself once it's gone.
      if ((await $.ui.panes()).some(pane => pane.id === PANE && pane.isShown)) {
        try {
          await $.ui.close({ id: PANE })
          // Closed in either view, it opens on the List next time.
          stopCrew()
          drawnView = null
          await update($, modeAtom, () => 'list')
          return { text: 'Loop pane closed.' }
        } catch {
          return { text: "The loop pane couldn't close. The × in its corner closes it." }
        }
      }
    } catch {
      return { text: CANT_OPEN }
    }
    return { text: (await openPane($)).text }
  })

  // An alias opens, never closes: someone typing the old name wants the pane. /loop-crew then moves the
  // List's loop into the Crew, as the Crew button does.
  for (const alias of ALIASES) {
    on('command.run', { command: alias.name }, async $ => {
      const opened = await openPane($)
      if (opened.isOpen && alias.view === 'crew') await toCrew($).catch(() => {})
      try {
        await $.ui.toast(aliasToast(alias.name))
      } catch {
        // A notice that can't show leaves the pane as it opened.
      }
      return { text: opened.text }
    })
  }

  // The wheel and scroll keys move the tab's list, under a header that stays put. At either end of the
  // list, or with nothing to move, the pane scrolls as usual.
  on('ui.scroll', { component: 'Pane', requestId: PANE }, async ($, e, next) => {
    // The Crew's lanes have no list to move: the pane scrolls as usual.
    if (drawnView === 'crew') return next(e)
    const moved = e.by !== 0 && (await move($, Math.sign(e.by), e.bodyRows).catch(() => false))
    return moved ? {} : next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    // The Crew view, when picked and there's room. A terminal under MIN_COLUMNS has no room for its
    // board, so the List stands in until it's widened, and the mode stays Crew so widening brings it
    // back. The other surfaces draw the board at any width.
    const mode = await read($, modeAtom)
    const isCrew = mode === 'crew' && (e.surface !== 'terminal' || e.props.bodyColumns >= MIN_COLUMNS)
    const modeButtons = [
      <Button
        key="mode-list"
        label="List"
        variant={isCrew ? undefined : 'primary'}
        dimColor={isCrew}
        onPress={() => toList($)}
      />,
      <Button
        key="mode-crew"
        label="Crew"
        variant={isCrew ? 'primary' : undefined}
        dimColor={!isCrew}
        onPress={() => toCrew($)}
      />,
    ]
    if (isCrew) {
      drawnView = 'crew'
      stopList()
      return renderCrew($, e, (
        <Box key="modes" flexDirection="row" columnGap={1}>
          {modeButtons}
        </Box>
      ))
    }
    drawnView = 'list'
    stopCrew()
    // Standing in for the Crew on a narrow terminal, the List reads the loop itself.
    if (mode === 'crew') startPolling($)
    // The mobile app draws no Select, so there the loops stay as buttons however many there are.
    const Select = e.surface === 'mobile' ? null : $.ui.resolve(e).Select
    const seen = await read($, seenAtom)
    const loops = (await read($, loopsAtom)) ?? []
    const width = Math.max(10, e.props.bodyColumns)
    const bodyRows = e.props.scroll?.bodyRows
    // A job's lines sit under its title, past the dot.
    const inner = width - 2
    const now = Date.now()
    // Claude Desktop and VS Code wrap text, so there a long line shows whole instead of being cut.
    const wraps = e.surface === 'desktop' || e.surface === 'vscode'
    const fit = (s: string, n: number) => (wraps ? s : clip(s, n))

    if (!seen) return <Text dimColor>Looking for the loop…</Text>

    const top = header(seen, now, width)
    // The state's dot is its first character, drawn on its own so it can pulse with the jobs' dots.
    const state = (
      <Box flexDirection="row">
        <Text {...(top.isPulsing ? PULSE[beat ? 'bright' : 'dim'] : COLORS[top.right.tone])}>{top.right.text.slice(0, 1)}</Text>
        <Text {...COLORS[top.right.tone]}>{top.right.text.slice(1)}</Text>
      </Box>
    )
    const tmux = attach(seen)
    const watchFile = watch(seen)
    const l = lists(seen.status, now)
    const view = current(await read($, viewAtom), l, bodyRows)
    const queue = page(l.queue, view.start, pageSize('queue', bodyRows))
    const jobs = view.tab === 'queue' ? null : page(l[view.tab], view.start, pageSize(view.tab, bodyRows))
    const { above, below } = jobs ?? queue
    const isEmpty = (jobs ?? queue).shown.length === 0

    // On the terminal every job takes the same rows, and every tab's list takes as many jobs' worth as
    // fit the pane, so nothing below it moves as jobs scroll by, gain a result or the tab changes. Desktop
    // and VS Code wrap instead, so a job takes the rows its text needs, and Queue holds only three lines open.
    const job = (row: Row) => {
      const { head: state, detail } = describe(row, seen.isLocked)
      const mark = dot(row, seen.isLocked)
      const time = clock(row, seen.isLocked, now)
      const stateText = fit(state.text, inner)
      const jobCommand = jobAttach(seen, row)
      // Every job has a dot, in the same column, so a title never moves as its job starts or ends.
      return (
        <Box key={`issue-${row.number}`} flexDirection="column" marginTop={1} height={wraps ? undefined : JOB_ROWS}>
          <Box flexDirection="row" columnGap={1}>
            <Text {...(mark.isPulsing ? PULSE[beat ? 'bright' : 'dim'] : COLORS[mark.tone])}>●</Text>
            <Text bold>{fit(`#${row.number} ${row.title}`, inner)}</Text>
          </Box>
          <Box flexDirection="column" marginLeft={2}>
            {/* Blank for a job from a loop.py that writes no start, so every job takes the same rows. */}
            <Box key={`clock-${row.number}`}>
              <Text dimColor>{time ? fit(time, inner) : ' '}</Text>
            </Box>
            <Text {...COLORS[state.tone]}>{stateText}</Text>
            <Box key={`detail-${row.number}`} height={wraps ? undefined : 2} overflow={wraps ? undefined : 'hidden'}>
              <Text dimColor>{detail ? fit(detail, inner * 2) : ' '}</Text>
            </Box>
            {jobCommand || row.pr ? (
              <Box flexDirection="row" columnGap={1}>
                {jobCommand && (
                  <Button
                    key={`watch-${row.number}`}
                    label="Watch"
                    onPress={press =>
                      openOrCopy($, `${seen.root}/${jobWatchFile(row.number, seen.project)}`, ['open'], () =>
                        $.ui.copy({ text: jobCommand, surface: press.surface }), WATCH_TOAST)}
                  />
                )}
                {row.pr ? (
                  <Button
                    key={`pr-${row.number}`}
                    label={fit('Open pull request', inner)}
                    onPress={press => openPullRequest($, row.pr ?? '', press.surface)}
                  />
                ) : null}
              </Box>
            ) : (
              <Text> </Text>
            )}
          </Box>
        </Box>
      )
    }
    const gap = (n: number, rows: number) =>
      Array.from({ length: n }, (_, i) => <Box key={`gap-${i}`} marginTop={rows > 1 ? 1 : 0} height={rows} />)
    const shownCount = (jobs ?? queue).shown.length
    const held = wraps && !jobs ? PAGE : pageSize(view.tab, bodyRows)
    const counts = loopCounts(loops)

    return (
      <Box flexDirection="column">
        {/* Two rows whatever the state, so nothing under the header moves when it wraps. */}
        {/* The layout pushes the state to the right edge, not padding: Claude Desktop's font needn't be monospace. */}
        <Box key="header" flexDirection="row" justifyContent="space-between">
          <Text bold>{top.left}</Text>
          {!top.wraps && state}
        </Box>
        {top.wraps ? state : <Text> </Text>}
        {/* The buttons' row, with the view buttons first, stays whether or not the loop runs in tmux, so */}
        {/* the tabs don't move as the loop starts or stops. It's the view buttons' row in the List, so */}
        {/* the List takes no row more than before. */}
        <Box key="actions" flexDirection="row" flexWrap="wrap" columnGap={1}>
          {modeButtons}
          {tmux && watchFile && (
            <Button
              key="watch"
              label="Watch it"
              onPress={press =>
                openOrCopy($, watchFile, ['open'], () => $.ui.copy({ text: watchCommand(seen) ?? '', surface: press.surface }), WATCH_TOAST)}
            />
          )}
          {tmux && (
            <Button
              key="tmux"
              label="Copy attach command"
              onPress={press => $.ui.copy({ text: tmux, surface: press.surface })}
            />
          )}
        </Box>
        <Text dimColor>{'─'.repeat(width)}</Text>
        {Select && loops.length > 1 ? (
          <Box key="loop-picker" flexDirection="row" columnGap={1}>
            <Select
              key="loop-pick"
              options={loopOptions(loops)}
              value={seen.project ?? ''}
              onSelect={value => {
                const loop = loops.find(l => (l.project ?? '') === value)
                return loop && show($, loop)
              }}
            />
            {counts && <Text dimColor>{counts}</Text>}
          </Box>
        ) : (
          loops.length > 1 && (
            <Box key="loops" flexDirection="row" flexWrap="wrap" columnGap={1}>
              {loops.map(loop => (
                <Button
                  key={loop.project ? `loop-${loop.project}` : 'loop'}
                  label={loopButtonLabel(loop)}
                  variant={loop.project === seen.project ? 'primary' : undefined}
                  dimColor={loop.project !== seen.project}
                  onPress={() => show($, loop)}
                />
              ))}
            </Box>
          )
        )}
        <Box flexDirection="row" flexWrap="wrap" columnGap={1}>
          {TABS.map(({ tab, label }) => (
            <Button
              key={`tab-${tab}`}
              label={`${label} ${l[tab].length}`}
              variant={tab === view.tab ? 'primary' : undefined}
              dimColor={tab !== view.tab}
              onPress={() => update($, viewAtom, () => ({ tab, start: 0 }))}
            />
          ))}
        </Box>
        {/* The lines above and below the list are always there, so it doesn't jump as it scrolls. */}
        {above > 0 ? (
          <Button key="up" plain label={`▲ ${above} more`} dimColor onPress={() => move($, -1, bodyRows)} />
        ) : (
          <Text> </Text>
        )}
        {isEmpty && (
          <Box marginTop={jobs ? 1 : 0} height={jobs ? JOB_ROWS : 1} overflow="hidden">
            <Text dimColor>{clip(EMPTY[view.tab], width)}</Text>
          </Box>
        )}
        {jobs
          ? jobs.shown.map(job)
          : queue.shown.map(q => {
              // The title gives way to what it waits on, down to a short stub.
              const note = waitingOn(q)
              const tag = note ? ` · ${note}` : ''
              const full = `#${q.number} ${q.title}`
              const title = wraps ? full : clip(full, Math.max(width - tag.length, Math.min(width, 16)))
              return (
                <Box key={`queue-${q.number}`} flexDirection="row">
                  <Text>{title}</Text>
                  {tag ? <Text dimColor>{fit(tag, width - title.length)}</Text> : null}
                </Box>
              )
            })}
        {gap(Math.max(0, held - shownCount - (isEmpty ? 1 : 0)), jobs ? JOB_ROWS : 1)}
        {below > 0 ? (
          <Button key="down" plain label={`▼ ${below} more`} dimColor onPress={() => move($, 1, bodyRows)} />
        ) : (
          <Text> </Text>
        )}
      </Box>
    )
  })
}
