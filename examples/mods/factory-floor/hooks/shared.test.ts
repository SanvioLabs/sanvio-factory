import { describe as group, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

// The List and the Crew read loops through one copy of the reading code, logic.ts's. A test here can't
// read the mod's source, so that each name is defined once is checked by tests/test_factory_floor.py;
// this file checks that the Crew's names are logic.ts's own functions, and that both views behave the
// same over the same files.
import {
  PROJECTS_DIR, SESSION, clip, findRoot, focusFile, focusName, lockPid, loopButtonLabel, loopCounts, loopDir, loopOptions,
  parseStatus, projectName, projectNames,
} from './logic'
import {
  PROJECTS_DIR as crewProjectsDir, SESSION as crewSession, clip as crewClip, findRoot as crewFindRoot, focusFile as crewFocusFile,
  focusName as crewFocusName, lockPid as crewLockPid, loopButtonLabel as crewLoopButtonLabel, loopDir as crewLoopDir,
  loopOptions as crewLoopOptions, parseStatus as crewParseStatus, projectName as crewProjectName, projectNames as crewProjectNames,
} from './crew-logic'
import type { Seen } from '../types'

group('one copy', () => {
  test("every reading and focus name the Crew uses is logic.ts's own", () => {
    const pairs: [string, unknown, unknown][] = [
      ['PROJECTS_DIR', crewProjectsDir, PROJECTS_DIR], ['SESSION', crewSession, SESSION], ['clip', crewClip, clip],
      ['findRoot', crewFindRoot, findRoot], ['focusFile', crewFocusFile, focusFile], ['focusName', crewFocusName, focusName],
      ['lockPid', crewLockPid, lockPid], ['loopButtonLabel', crewLoopButtonLabel, loopButtonLabel], ['loopDir', crewLoopDir, loopDir],
      ['loopOptions', crewLoopOptions, loopOptions], ['parseStatus', crewParseStatus, parseStatus],
      ['projectName', crewProjectName, projectName], ['projectNames', crewProjectNames, projectNames],
    ]
    for (const [name, theirs, ours] of pairs) expect(`${name}: ${theirs === ours}`).toBe(`${name}: true`)
  })
})

const ROOT = '/h/starter'
const HARNESS = `${ROOT}/.loop`
const ALPHA = `${ROOT}/.loop/projects/alpha`
const BETA = `${ROOT}/.loop/projects/beta`
const ID = '0123abcd-4567'
const FOCUS = `${ROOT}/.sanvio/project/${ID}`
// alpha, beta and gamma are folders under projects/, but only alpha and beta have a loop.
const FOLDERS: Record<string, 'dir'> = { alpha: 'dir', beta: 'dir', gamma: 'dir' }

const job = (number: number, title: string) =>
  ({ number, title, step: 'BUILD', state: 'working', round: 1, tests: null, review: null, pr: null, note: '' })
const statusText = (issues: object[], queue: object[]) => JSON.stringify({ running: true, tmux: null, queue, issues })

// The factory, stopped and with nothing waiting, and alpha and beta, each live with a job being worked
// and another waiting, so each counts once as running and once as queued.
const busy = () => new Map([
  [`${HARNESS}/status.json`, JSON.stringify({ running: false, tmux: null, queue: [], issues: [] })],
  [`${ALPHA}/status.json`, statusText([job(30, 'alpha job')], [{ number: 31, title: 'alpha next' }])],
  [`${ALPHA}/lock`, '4242'],
  [`${BETA}/status.json`, statusText([job(40, 'beta job')], [{ number: 41, title: 'beta next' }])],
  [`${BETA}/lock`, '4242'],
])

// The picker's options both views must draw: the busy loops first, the factory by its folder.
const OPTIONS = [
  { value: 'alpha', label: '● alpha' },
  { value: 'beta', label: '● beta' },
  { value: '', label: 'starter' },
]
const COUNTS = '● 2 running · 2 queued'

// Work the timers left running; they await the engine a few times.
async function drain(): Promise<void> {
  for (let i = 0; i < 200; i++) await Promise.resolve()
}

// The engine beneath the mod: a factory whose loop files are `files`, by path, and a pane. `session`
// gives the session's id, null refusing it. fs.write is recorded and refused: the tests check what
// either view tried to write. Every lock's holder is alive.
function world(on: On, files: Map<string, string>, session: { id: string | null } = { id: null }) {
  const clock = mock.clock(on, { now: 1_800_000_000_000 })
  const writes: { path: string; text: string }[] = []
  const titles: string[] = []
  const stored = new Map<string, unknown>()
  const panes: { id: string; isShown: boolean; isPlaced: boolean }[] = []
  on('session.root', async () => ({ value: ROOT }))
  on('session.id', async () => (session.id === null ? { deny: 'no session id' } : { value: session.id }))
  on('fs.stat', async (_$, e) => {
    const name = e.path.startsWith(`${ROOT}/projects/`) ? e.path.slice(`${ROOT}/projects/`.length) : ''
    return FOLDERS[name] ? { value: { kind: 'dir', size: 0, mtimeMs: 0, isLink: false } } : { deny: `no ${e.path}` }
  })
  on('fs.write', async (_$, e) => {
    writes.push({ path: e.path, text: e.text })
    return { deny: 'read-only' }
  })
  on('fs.exists', async (_$, e) => ({ value: e.path === `${ROOT}/scripts/loop.py` || files.has(e.path) }))
  on('fs.read', async (_$, e) => {
    const text = files.get(e.path)
    return text === undefined ? { deny: `no ${e.path}` } : { value: text }
  })
  on('fs.list', async (_$, e) => {
    if (e.path !== `${ROOT}/${PROJECTS_DIR}`) return { deny: `no ${e.path}` }
    const names = [...files.keys()].flatMap(p => p.match(/\/\.loop\/projects\/([^/]+)\//)?.[1] ?? [])
    return { value: [...new Set(names)].map(name => ({ name, kind: 'dir' as const, size: 0 })) } as never
  })
  on('process.run', async () => ({ value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  on('ui.open', async (_$, e) => {
    titles.push(e.title ?? '')
    if (!panes.some(p => p.isShown)) {
      panes.length = 0
      panes.push({ id: 'factory-floor', isShown: true, isPlaced: true })
    }
    return { value: { isPlaced: true } }
  })
  on('ui.close', async () => {
    panes.length = 0
    return { value: undefined }
  })
  on('ui.panes', async () => ({ value: [...panes] }) as never)
  on('ui.toast', async () => ({ value: undefined }))
  on('ui.blit', async () => ({ value: {} }) as never)
  // Every value the mod stores, by key, as the last write left it.
  on('state.set', async (_$, e, next) => {
    const at = e as unknown as { plugin: string; key: string; value: unknown }
    if (at.plugin === 'factory-floor') stored.set(at.key, at.value)
    return next(e)
  })
  // Closes the pane, so every timer stops itself and the next test can start its own.
  const close = async () => {
    panes.length = 0
    await clock.advance(2000)
    await drain()
  }
  return { clock, writes, titles, stored, close }
}

const PANE = {
  plugin: 'factory-floor',
  surface: 'terminal',
  component: 'Pane',
  requestId: 'factory-floor',
  props: { title: 'Loop', isFocused: true, bodyColumns: 72, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

type Found = { props: Record<string, unknown>; children?: unknown }
type Mounted = {
  find: (query: { key: string }) => Promise<Found | undefined>
  press: (target: { key: string }) => Promise<unknown>
  redraw: () => Promise<void>
  unmount: () => Promise<void>
}
type Dollar = { command: { run: (i: object) => Promise<unknown> } }
const typed = { command: 'factory-floor', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } }
const open = async ($: unknown): Promise<void> => {
  await ($ as Dollar).command.run(typed)
}

const pickOptions = async (ui: Mounted) => (await ui.find({ key: 'loop-pick' }))?.props.options
const pickValue = async (ui: Mounted) => (await ui.find({ key: 'loop-pick' }))?.props.value
const last = (titles: string[]): string | undefined => titles[titles.length - 1]
// Past the next read of either view's poll, and the switch it may make.
const poll = async (clock: { advance: (ms: number) => Promise<unknown> }): Promise<void> => {
  await clock.advance(2000)
  for (let i = 0; i < 4; i++) await drain()
}
// What a focus change must never write: the focus file, or anything of a loop's.
const forbidden = (writes: { path: string }[]) => writes.filter(w => w.path.includes('/.sanvio/project/') || w.path.includes('/.loop/'))

group('the picker and the count line', () => {
  test('the List and the Crew list the same loops with the same labels, and count them the same', async ($, on) => {
    const { stored, close } = world(on, busy())
    await open($)
    const ui = (await $.ui.mount(PANE)) as unknown as Mounted
    expect(await ui.find({ key: 'tab-queue' })).toBeDefined()
    expect(await pickOptions(ui)).toEqual(OPTIONS)
    expect(JSON.stringify((await ui.find({ key: 'loop-picker' }))?.children)).toContain(COUNTS)
    await ui.press({ key: 'mode-crew' })
    await drain()
    await ui.redraw()
    expect(await ui.find({ key: 'tab-queue' })).toBeUndefined()
    expect(await pickOptions(ui)).toEqual(OPTIONS)
    // The Crew draws no count line, so the same count is taken from the loops it read.
    const loops = stored.get('crew-loops') as Seen[] | undefined
    expect(loops?.length).toBe(3)
    expect(loopCounts(loops ?? [])).toBe(COUNTS)
    await ui.unmount()
    await close()
  })
})

group('following the focus', () => {
  test('in the List, a focus on beta moves the pane there, one on gamma with no loop moves nothing, and a cleared one moves it to the factory', async ($, on) => {
    const files = busy()
    const { clock, writes, close } = world(on, files, { id: ID })
    await open($)
    const ui = (await $.ui.mount(PANE)) as unknown as Mounted
    expect(await pickValue(ui)).toBe('alpha')
    files.set(FOCUS, 'beta\n')
    await poll(clock)
    expect(await pickValue(ui)).toBe('beta')
    files.set(FOCUS, 'gamma\n')
    await poll(clock)
    expect(await pickValue(ui)).toBe('beta')
    files.set(FOCUS, '')
    await poll(clock)
    expect(await pickValue(ui)).toBe('')
    expect(forbidden(writes)).toEqual([])
    await ui.unmount()
    await close()
  })
  test('in the Crew, a focus on beta moves the pane there, one on gamma with no loop moves nothing, and a cleared one moves it to the factory', async ($, on) => {
    const files = busy()
    const { clock, writes, titles, close } = world(on, files, { id: ID })
    await open($)
    const ui = (await $.ui.mount(PANE)) as unknown as Mounted
    await ui.press({ key: 'mode-crew' })
    await drain()
    expect(last(titles)).toBe('Loop crew: alpha')
    files.set(FOCUS, 'beta\n')
    await poll(clock)
    expect(last(titles)).toBe('Loop crew: beta')
    // On beta, the other loops keep their own labels.
    await ui.redraw()
    expect(await pickValue(ui)).toBe('beta')
    expect(await pickOptions(ui)).toEqual(OPTIONS)
    files.set(FOCUS, 'gamma\n')
    await poll(clock)
    expect(last(titles)).toBe('Loop crew: beta')
    files.set(FOCUS, '')
    await poll(clock)
    expect(last(titles)).toBe('Loop crew')
    expect(forbidden(writes)).toEqual([])
    await ui.unmount()
    await close()
  })
})
