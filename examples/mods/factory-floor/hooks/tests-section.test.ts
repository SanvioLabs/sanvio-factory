import { describe as group, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

// The List's Tests section, drawn from the files scripts/run_tests.py keeps in .sanvio/tests/.
const ROOT = '/h/starter'
const TESTS = `${ROOT}/.sanvio/tests`
const HARNESS = `${ROOT}/.loop`
const ALPHA = `${ROOT}/.loop/projects/alpha`
const NOW = 1_800_000_000_000
const MIN = 60_000
const POLL = 2000
const iso = (ms: number) => new Date(ms).toISOString().replace('Z', '+00:00')

const PANE = {
  plugin: 'factory-floor',
  surface: 'terminal',
  component: 'Pane',
  requestId: 'factory-floor',
  props: { title: 'Loop', isFocused: true, bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

const statusText = (title: string) => JSON.stringify({ running: false, tmux: null, queue: [{ number: 30, title }], issues: [] })

// A run file as the runner writes it, started 11m 52s before `at`, last written 2 seconds before it.
const runText = (at: number, over: object = {}) => JSON.stringify({
  state: 'running', worktree: '/tmp/scratchpad/m657', branch: 'loop/issue-647', pid: 4242,
  started: iso(at - 11 * MIN - 52_000), updated: iso(at - 2000), total: 3005, ran: 1204, failed: 0, skipped: 0, ...over,
})
const passedText = (at: number) => runText(at, { state: 'passed', ran: 3005, exit_code: 0, ended: iso(at), updated: iso(at) })

// The engine beneath the plugin: a factory whose files are `files`, by path, and an open pane. fs.list
// answers for .loop/projects and .sanvio/tests from those paths. Nothing touches the disk.
function world(on: On, files: Map<string, string>) {
  const clock = mock.clock(on, { now: NOW })
  const toasts: string[] = []
  const panes: { id: string; isShown: boolean; isPlaced: boolean }[] = []
  on('session.root', async () => ({ value: ROOT }))
  on('session.id', async () => ({ deny: 'no session id' }))
  on('fs.exists', async (_$, e) => ({ value: e.path === `${ROOT}/scripts/loop.py` || files.has(e.path) }))
  on('fs.read', async (_$, e) => {
    const text = files.get(e.path)
    return text === undefined ? { deny: `no ${e.path}` } : { value: text }
  })
  on('fs.stat', async (_$, e) => ({ deny: `no ${e.path}` }))
  on('fs.list', async (_$, e) => {
    if (e.path === `${ROOT}/.loop/projects`) {
      const names = [...files.keys()].flatMap(p => p.match(/\/\.loop\/projects\/([^/]+)\//)?.[1] ?? [])
      return { value: [...new Set(names)].map(name => ({ name, kind: 'dir' as const, size: 0 })) } as never
    }
    if (e.path === TESTS) {
      const names = [...files.keys()].filter(p => p.startsWith(`${TESTS}/`)).map(p => p.slice(TESTS.length + 1))
      if (!names.length) return { deny: `no ${e.path}` }
      return { value: names.map(name => ({ name, kind: 'file' as const, size: 1 })) } as never
    }
    return { deny: `no ${e.path}` }
  })
  on('process.run', async () => ({ value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  on('ui.open', async () => {
    panes.length = 0
    panes.push({ id: 'factory-floor', isShown: true, isPlaced: true })
    return { value: { isPlaced: true } }
  })
  on('ui.close', async () => {
    panes.length = 0
    return { value: undefined }
  })
  on('ui.panes', async () => ({ value: [...panes] }) as never)
  on('ui.toast', async (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  // Closes the pane, so the poll stops itself and the next test can start its own.
  const close = async () => {
    panes.length = 0
    await clock.advance(500)
  }
  return { clock, toasts, close }
}

type Dollar = { command: { run: (i: object) => Promise<unknown> } }
const typed = { command: 'factory-floor', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } }
const open = async ($: Dollar) => { await $.command.run(typed) }

type Found = { props: Record<string, unknown>; children?: unknown[] } | undefined
type Ui = { find: (q: { key: string }) => Promise<unknown>; drawn: () => Promise<unknown> }
const text = async (ui: Ui, key: string) => JSON.stringify(await ui.find({ key }))

group('the Tests section', () => {
  test('with no files there is no section, not even its heading', async ($, on) => {
    const { close } = world(on, new Map([[`${HARNESS}/status.json`, statusText('factory job')]]))
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect(await ui.find({ key: 'tests' })).toBeUndefined()
    expect(JSON.stringify(await ui.drawn())).not.toContain('"Tests"')
    await ui.unmount()
    await close()
  })

  test('a running run shows under the list with its title, clock, progress and failures', async ($, on) => {
    const files = new Map([
      [`${HARNESS}/status.json`, statusText('factory job')],
      [`${TESTS}/20270115-084000-4242.json`, runText(NOW)],
    ])
    const { close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    const section = await text(ui, 'tests')
    expect(section).toContain('Tests')
    expect(section).toContain('m657 · loop/issue-647')
    expect(await text(ui, 'test-line-20270115-084000-4242')).toMatch(/started [^"]+ · running 11m 52s · 1204 of 3005 · 0 failed/)
    // Under the list: after the tabs and the line below the jobs.
    const top = (await ui.drawn()) as unknown as { children: unknown[] }
    const at = (needle: string) => top.children.findIndex(c => JSON.stringify(c).includes(needle))
    expect(at('"tests"')).toBeGreaterThan(at('"tab-queue"'))
    expect(at('"tests"')).toBe(top.children.length - 1)
    await ui.unmount()
    await close()
  })

  test('the section counts among the rows, so fewer jobs fit the pane', async ($, on) => {
    const job = (n: number) => ({ number: n, title: `job ${n}`, step: 'BUILD', state: 'working', round: 1, tests: null, review: null, pr: null, note: '' })
    const busy = JSON.stringify({ running: true, tmux: null, queue: [], issues: Array.from({ length: 6 }, (_, i) => job(i + 1)) })
    const files = new Map([[`${HARNESS}/status.json`, busy]])
    const { clock, close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    const jobs = async () => JSON.stringify(await ui.drawn()).match(/"issue-\d+"/g)?.length ?? 0
    const without = await jobs()
    files.set(`${TESTS}/a.json`, runText(NOW + POLL))
    files.set(`${TESTS}/b.json`, passedText(NOW))
    await clock.advance(POLL)
    expect(await ui.find({ key: 'tests' })).toBeDefined()
    expect(await jobs()).toBeLessThan(without)
    await ui.unmount()
    await close()
  })

  test('a run that ends while the pane is open raises one toast; one already ended at opening raises none', async ($, on) => {
    const files = new Map([
      [`${HARNESS}/status.json`, statusText('factory job')],
      [`${TESTS}/old.json`, passedText(NOW - 30 * MIN)],
      [`${TESTS}/now.json`, runText(NOW)],
    ])
    const { clock, toasts, close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    await clock.advance(POLL)
    expect(toasts).toEqual([])
    files.set(`${TESTS}/now.json`, passedText(NOW + POLL))
    await clock.advance(POLL)
    expect(toasts).toEqual(['Tests on m657: 3005 passed'])
    expect(await text(ui, 'test-line-now')).toContain('3005 passed in')
    await clock.advance(POLL)
    expect(toasts.length).toBe(1)
    await ui.unmount()
    await close()
  })

  test('a run stopped with Ctrl-C toasts stopped, and one that stops writing turns red without a toast', async ($, on) => {
    const files = new Map([
      [`${HARNESS}/status.json`, statusText('factory job')],
      [`${TESTS}/ctrlc.json`, runText(NOW)],
      [`${TESTS}/died.json`, runText(NOW, { worktree: '/tmp/i681', branch: '' })],
    ])
    const { clock, toasts, close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    files.set(`${TESTS}/ctrlc.json`, runText(NOW, { state: 'failed', exit_code: 130, ended: iso(NOW + 1000), updated: iso(NOW + 1000) }))
    await clock.advance(2 * MIN)
    expect(toasts).toEqual(['Tests on m657: stopped'])
    expect(await text(ui, 'test-line-ctrlc')).toContain('stopped at 1204 of 3005')
    expect(await text(ui, 'test-line-died')).toMatch(/started [^"]+ · stopped"/)
    expect(await text(ui, 'test-line-died')).toContain('red')
    await ui.unmount()
    await close()
  })

  test('a run that ends while the Crew is drawn raises no toast, then or back in the List', async ($, on) => {
    const files = new Map([
      [`${HARNESS}/status.json`, statusText('factory job')],
      [`${TESTS}/now.json`, runText(NOW)],
    ])
    const { clock, toasts, close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'mode-crew' })
    files.set(`${TESTS}/now.json`, passedText(NOW + POLL))
    await clock.advance(POLL)
    await ui.press({ key: 'mode-list' })
    await clock.advance(POLL)
    expect(toasts).toEqual([])
    expect(await text(ui, 'test-line-now')).toContain('3005 passed in')
    await ui.unmount()
    await close()
  })

  test('a file that does not parse is left out and the rest still show', async ($, on) => {
    const files = new Map([
      [`${HARNESS}/status.json`, statusText('factory job')],
      [`${TESTS}/bad.json`, '{half a fi'],
      [`${TESTS}/nostate.json`, JSON.stringify({ started: iso(NOW) })],
      [`${TESTS}/good.json`, runText(NOW)],
    ])
    const { close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect(await ui.find({ key: 'test-good' })).toBeDefined()
    expect(await ui.find({ key: 'test-bad' })).toBeUndefined()
    expect(await ui.find({ key: 'test-nostate' })).toBeUndefined()
    await ui.unmount()
    await close()
  })

  test('the section shows whichever loop is picked, All loops included', async ($, on) => {
    const files = new Map([
      [`${HARNESS}/status.json`, statusText('factory job')],
      [`${ALPHA}/status.json`, statusText('alpha job')],
      [`${TESTS}/r.json`, runText(NOW)],
    ])
    const { close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = (await $.ui.mount(PANE)) as unknown as Ui & { select: (q: { key: string; value: string }) => Promise<void>; unmount: () => Promise<void> }
    for (const value of ['alpha', '*']) {
      await ui.select({ key: 'loop-pick', value })
      for (let i = 0; i < 20; i++) await Promise.resolve()
      expect((await ui.find({ key: 'test-r' })) as Found).toBeDefined()
    }
    await ui.unmount()
    await close()
  })
})
