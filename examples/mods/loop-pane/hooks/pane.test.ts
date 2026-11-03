import { describe as group, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import type { Seen } from '../types'

const SEEN = (hasWatchFile: boolean): Seen => ({
  root: '/h/starter',
  status: { running: true, updated: null, tmux: 'loop-starter', queue: [], issues: [] },
  isLocked: true,
  isStaleLock: false,
  isStopping: false,
  hasWatchFile,
})

// Stands in for the pane's last look at the loop's files.
function seed(on: On, seen: Seen): void {
  on('state.get', async (_$, e, next) =>
    e.plugin === 'loop-pane' && e.key === 'seen' ? { value: { value: seen, version: 1 } } : next(e))
}

// The press runs the open in the background; let it finish.
async function drain(): Promise<void> {
  for (let i = 0; i < 20; i++) await Promise.resolve()
}

const PANE = {
  plugin: 'loop-pane',
  surface: 'terminal',
  component: 'Pane',
  requestId: 'loop',
  props: { title: 'Loop', isFocused: true, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

group('the Watch it button', () => {
  test('opens the watch file', async ($, on) => {
    const ran: string[][] = []
    on('process.run', async (_$, e) => {
      ran.push([...e.argv])
      return { value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    })
    seed(on, SEEN(true))
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'watch' })
    await drain()
    expect(ran).toEqual([['open', '/h/starter/.loop/watch.command']])
    await ui.unmount()
  })
  test("copies the read-only attach command when the window can't open", async ($, on) => {
    const copied: string[] = []
    on('process.run', async () => ({ value: { exitCode: 1, stdout: '', stderr: 'no', isStdoutTruncated: false, isStderrTruncated: false } }))
    const toasts: string[] = []
    on('ui.copy', async (_$, e) => {
      copied.push(e.text)
      return { value: { isCopied: true } }
    })
    on('ui.toast', async (_$, e) => {
      toasts.push(e.text)
      return { value: undefined }
    })
    seed(on, SEEN(true))
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'watch' })
    await drain()
    expect(copied).toEqual(["tmux attach -r -t '=loop-starter'"])
    expect(toasts.length).toBe(1)
    await ui.unmount()
  })
  test('is absent without the watch file', async ($, on) => {
    seed(on, SEEN(false))
    const ui = await $.ui.mount(PANE)
    expect(await ui.find({ key: 'watch' })).toBeUndefined()
    expect(await ui.find({ key: 'tmux' })).toBeDefined()
    await ui.unmount()
  })
})

group('the header', () => {
  test('names the repo and the state, with Watch it and Copy attach command on one row and no bare attach line', async ($, on) => {
    seed(on, SEEN(true))
    const ui = await $.ui.mount(PANE)
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('starter')
    // The state's dot is drawn apart from its words, so it can pulse; idle, it doesn't.
    expect(drawn).toContain('" Idle"')
    expect(JSON.stringify(await ui.find({ key: 'header' }))).not.toContain('cyan')
    expect(drawn).not.toContain('tmux attach')
    const row = await ui.find({ key: 'actions' })
    expect(row?.props.flexDirection).toBe('row')
    const inRow = JSON.stringify(row?.children)
    expect(inRow).toContain('Watch it')
    expect(inRow).toContain('Copy attach command')
    await ui.unmount()
  })
  test('takes the same rows above the tabs whether the loop is running or not', async ($, on) => {
    let seen = SEEN(true)
    on('state.get', async (_$, e, next) =>
      e.plugin === 'loop-pane' && e.key === 'seen' ? { value: { value: seen, version: 1 } } : next(e))
    // How many of the pane's lines come before the tabs.
    const above = async (): Promise<number> => {
      const ui = await $.ui.mount(PANE)
      const top = (await ui.drawn()) as unknown as { children: { props?: { key?: string } }[] }
      await ui.unmount()
      return top.children.findIndex(c => JSON.stringify(c).includes('"tab-queue"'))
    }
    const running = await above()
    seen = { ...SEEN(false), isLocked: false, status: { ...SEEN(false).status!, running: false, tmux: null } }
    expect(running).toBeGreaterThan(0)
    expect(await above()).toBe(running)
  })
})

group("a job's Watch button", () => {
  const withWindow: Seen = {
    ...SEEN(false),
    status: {
      running: true, updated: null, tmux: 'loop-starter', queue: [],
      issues: [{ number: 12, title: 'Gate', step: 'BUILD', state: 'working', round: 1, tests: null, review: null,
        pr: null, note: '', window: 'issue-12' }],
    },
  }
  test('opens the job watch file', async ($, on) => {
    const ran: string[][] = []
    on('process.run', async (_$, e) => {
      ran.push([...e.argv])
      return { value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    })
    seed(on, withWindow)
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'watch-12' })
    await drain()
    expect(ran).toEqual([['open', '/h/starter/.loop/issue-12/watch.command']])
    await ui.unmount()
  })
  test("copies the job's read-only attach command when the window can't open", async ($, on) => {
    const copied: string[] = []
    on('process.run', async () => ({ value: { exitCode: 1, stdout: '', stderr: 'no', isStdoutTruncated: false, isStderrTruncated: false } }))
    on('ui.copy', async (_$, e) => {
      copied.push(e.text)
      return { value: { isCopied: true } }
    })
    on('ui.toast', async () => ({ value: undefined }))
    seed(on, withWindow)
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'watch-12' })
    await drain()
    expect(copied).toEqual(["tmux attach -r -t '=loop-starter:issue-12'"])
    await ui.unmount()
  })
  test('a job with no window has none', async ($, on) => {
    seed(on, { ...withWindow, status: { ...withWindow.status!, issues: withWindow.status!.issues.map(r => ({ ...r, window: undefined })) } })
    const ui = await $.ui.mount(PANE)
    expect(await ui.find({ key: 'watch-12' })).toBeUndefined()
    await ui.unmount()
  })
})

// A local time, as loop.py writes it, `hours` ago.
function hoursAgo(hours: number): string {
  const d = new Date(Date.now() - hours * 3600_000)
  const two = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}T${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`
}

const FINISHED = (number: number, hours: number) => ({
  number, title: `job ${number}`, step: 'SCALE', state: 'pr', round: 1, tests: 'passed', review: 'PASS',
  pr: `https://example.test/pull/${number}`, note: '', updated: hoursAgo(hours),
})

const MANY: Seen = {
  root: '/h/starter',
  status: {
    running: false, updated: null, tmux: null,
    queue: [{ number: 30, title: 'next up' }],
    issues: [FINISHED(21, 1), FINISHED(22, 2), FINISHED(23, 3), FINISHED(24, 4), FINISHED(25, 5), FINISHED(9, 30)],
  },
  isLocked: false, isStaleLock: false, isStopping: false, hasWatchFile: false,
}

const titles = async (ui: { findAll: (q: { type: string; text: RegExp }) => Promise<{ text: string }[]> }) =>
  (await ui.findAll({ type: 'Text', text: /^#\d+ / })).map(t => t.text)

type Drawn = { type: string; props?: { marginTop?: number; height?: number; flexDirection?: string }; children?: (Drawn | string)[] }

// The rows a node takes: its margin and height, or with no height what its children take side by side
// or stacked. A Text is one.
function rowsOf(node: Drawn | string): number {
  if (typeof node === 'string') return 1
  const { marginTop = 0, height, flexDirection } = node.props ?? {}
  if (height !== undefined) return marginTop + height
  if (node.type !== 'Box') return marginTop + 1
  const inside = (node.children ?? []).map(rowsOf)
  return marginTop + (flexDirection === 'row' ? Math.max(0, ...inside) : inside.reduce((a, b) => a + b, 0))
}

// The rows the list takes: the root's children after the line following the tabs' row, up to but not
// including the last.
async function listRows(ui: { drawn: () => Promise<unknown> }): Promise<number> {
  const children = ((await ui.drawn()) as Drawn).children ?? []
  const tabs = children.findIndex(c => JSON.stringify(c).includes('"tab-queue"'))
  expect(tabs).toBeGreaterThan(-1)
  return children.slice(tabs + 2, -1).reduce((rows, c) => rows + rowsOf(c), 0)
}

// A loop with `n` issues waiting and nothing else, so with none it opens on Finished.
const queued = (n: number): Seen => ({
  ...MANY,
  status: { ...MANY.status!, queue: Array.from({ length: n }, (_, i) => ({ number: i + 1, title: `issue ${i + 1}` })), issues: [] },
})

const numbered = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => `#${from + i} issue ${from + i}`)

// The pane, `bodyRows` tall.
const atHeight = (bodyRows: number) => ({ ...PANE, props: { ...PANE.props, scroll: { ...PANE.props.scroll, bodyRows } } })

group('the tabs', () => {
  test('nothing active opens on the queue; finished shows three from the last day, the rest below', async ($, on) => {
    seed(on, MANY)
    const ui = await $.ui.mount(PANE)
    expect((await ui.find({ key: 'tab-queue' }))?.props.label).toBe('Queue 1')
    expect((await ui.find({ key: 'tab-active' }))?.props.label).toBe('Active 0')
    expect((await ui.find({ key: 'tab-finished' }))?.props.label).toBe('Finished 5')
    expect(await titles(ui)).toEqual(['#30 next up'])
    await ui.press({ key: 'tab-finished' })
    await drain()
    expect(await titles(ui)).toEqual(['#21 job 21', '#22 job 22', '#23 job 23'])
    expect((await ui.find({ key: 'down' }))?.props.label).toBe('▼ 2 more')
    expect(await ui.find({ key: 'up' })).toBeUndefined()
    await ui.unmount()
  })
  test('the more line moves the list a job at a time', async ($, on) => {
    seed(on, MANY)
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'tab-finished' })
    await drain()
    await ui.press({ key: 'down' })
    await drain()
    expect(await titles(ui)).toEqual(['#22 job 22', '#23 job 23', '#24 job 24'])
    expect((await ui.find({ key: 'up' }))?.props.label).toBe('▲ 1 more')
    await ui.unmount()
  })
  test('a tab press shows that list', async ($, on) => {
    seed(on, MANY)
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'tab-queue' })
    await drain()
    expect(await titles(ui)).toEqual(['#30 next up'])
    await ui.press({ key: 'tab-active' })
    await drain()
    expect(await ui.find({ text: 'Nothing being worked on.' })).toBeDefined()
    await ui.unmount()
  })
})

group('one height for every tab', () => {
  const WORKING = (number: number) => ({
    number, title: `job ${number}`, step: 'BUILD', state: 'working', round: 1, tests: null, review: null, pr: null, note: '',
  })
  const active: Seen = { ...queued(0), status: { ...queued(0).status!, issues: [WORKING(1), WORKING(2), WORKING(3), WORKING(4)] } }
  const tick = {
    component: 'Pane', requestId: 'loop', offset: 0, bodyRows: 30, contentRows: 60, origin: { kind: 'person' },
  } as const

  test('a full Queue takes 21 rows', async ($, on) => {
    seed(on, queued(30))
    const ui = await $.ui.mount(PANE)
    expect(await listRows(ui)).toBe(21)
    await ui.unmount()
  })
  test('an empty Queue takes 21 rows', async ($, on) => {
    seed(on, queued(0))
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'tab-queue' })
    await drain()
    expect(await ui.find({ text: /^Nothing waiting/ })).toBeDefined()
    expect(await listRows(ui)).toBe(21)
    await ui.unmount()
  })
  test('a full Active takes 21 rows', async ($, on) => {
    seed(on, active)
    const ui = await $.ui.mount(PANE)
    expect(await listRows(ui)).toBe(21)
    await ui.unmount()
  })
  test('an empty Active takes 21 rows', async ($, on) => {
    seed(on, queued(0))
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'tab-active' })
    await drain()
    expect(await listRows(ui)).toBe(21)
    await ui.unmount()
  })
  test('a full Finished takes 21 rows', async ($, on) => {
    seed(on, MANY)
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'tab-finished' })
    await drain()
    expect(await listRows(ui)).toBe(21)
    await ui.unmount()
  })
  test('an empty Finished takes 21 rows', async ($, on) => {
    seed(on, queued(0))
    const ui = await $.ui.mount(PANE)
    expect(await listRows(ui)).toBe(21)
    await ui.unmount()
  })
  test('a queue of 30 shows 21, with the rest below', async ($, on) => {
    seed(on, queued(30))
    const ui = await $.ui.mount(PANE)
    expect(await titles(ui)).toEqual(numbered(1, 21))
    expect((await ui.find({ key: 'down' }))?.props.label).toBe('▼ 9 more')
    expect(await ui.find({ key: 'up' })).toBeUndefined()
    await ui.unmount()
  })
  test('▼ more pages a queue of 30 a line at a time, to its last issue', async ($, on) => {
    seed(on, queued(30))
    const ui = await $.ui.mount(PANE)
    for (let i = 0; i < 9; i++) {
      await ui.press({ key: 'down' })
      await drain()
    }
    expect(await titles(ui)).toEqual(numbered(10, 30))
    expect((await ui.find({ key: 'up' }))?.props.label).toBe('▲ 9 more')
    expect(await ui.find({ key: 'down' })).toBeUndefined()
    expect(await listRows(ui)).toBe(21)
    await ui.unmount()
  })
  test('the wheel pages a queue of 30 to its last issue, then lets the pane scroll', async ($, on) => {
    let passedOn = 0
    on('ui.scroll', async () => {
      passedOn++
      return {}
    })
    seed(on, queued(30))
    const ui = await $.ui.mount(PANE)
    for (let i = 0; i < 9; i++) await $.ui.scroll({ ...tick, by: 1 })
    await drain()
    expect(await titles(ui)).toEqual(numbered(10, 30))
    expect((await ui.find({ key: 'up' }))?.props.label).toBe('▲ 9 more')
    expect(await ui.find({ key: 'down' })).toBeUndefined()
    expect(passedOn).toBe(0)
    await $.ui.scroll({ ...tick, by: 1 })
    expect(passedOn).toBe(1)
    await ui.unmount()
  })

  // More jobs than fit at 60, so a full list there is filled by jobs and not by the rows held open.
  const withIssues = (issues: NonNullable<Seen['status']>['issues']): Seen =>
    ({ ...queued(0), status: { ...queued(0).status!, issues } })
  const working = withIssues(Array.from({ length: 10 }, (_, i) => WORKING(101 + i)))
  const finished = withIssues(Array.from({ length: 10 }, (_, i) => FINISHED(101 + i, i + 1)))

  for (const bodyRows of [60, 60.5]) {
    test(`at ${bodyRows}, Active shows 7 jobs`, async ($, on) => {
      seed(on, working)
      const ui = await $.ui.mount(atHeight(bodyRows))
      expect((await titles(ui)).length).toBe(7)
      expect((await ui.find({ key: 'down' }))?.props.label).toBe('▼ 3 more')
      await ui.unmount()
    })
    test(`at ${bodyRows}, Finished shows 7 jobs`, async ($, on) => {
      seed(on, finished)
      const ui = await $.ui.mount(atHeight(bodyRows))
      expect((await titles(ui)).length).toBe(7)
      expect((await ui.find({ key: 'down' }))?.props.label).toBe('▼ 3 more')
      await ui.unmount()
    })
    test(`at ${bodyRows}, Queue shows 49 issues`, async ($, on) => {
      seed(on, queued(80))
      const ui = await $.ui.mount(atHeight(bodyRows))
      expect(await titles(ui)).toEqual(numbered(1, 49))
      expect((await ui.find({ key: 'down' }))?.props.label).toBe('▼ 31 more')
      await ui.unmount()
    })
  }
  test('the number shown follows the height when the pane is drawn again', async ($, on) => {
    seed(on, queued(80))
    const low = await $.ui.mount(atHeight(30))
    expect((await titles(low)).length).toBe(21)
    await low.unmount()
    const tall = await $.ui.mount(atHeight(60))
    expect((await titles(tall)).length).toBe(49)
    await tall.unmount()
  })
  test('▼ more reaches the last issue at 60', async ($, on) => {
    seed(on, queued(80))
    const ui = await $.ui.mount(atHeight(60))
    for (let i = 0; i < 31; i++) {
      await ui.press({ key: 'down' })
      await drain()
    }
    expect(await titles(ui)).toEqual(numbered(32, 80))
    expect(await ui.find({ key: 'down' })).toBeUndefined()
    await ui.unmount()
  })
  test('the end of the list at 30, drawn at 60, shows 49 with the rest above', async ($, on) => {
    seed(on, queued(80))
    const low = await $.ui.mount(atHeight(30))
    for (let i = 0; i < 59; i++) {
      await low.press({ key: 'down' })
      await drain()
    }
    expect(await titles(low)).toEqual(numbered(60, 80))
    await low.unmount()
    const tall = await $.ui.mount(atHeight(60))
    expect(await titles(tall)).toEqual(numbered(32, 80))
    expect((await tall.find({ key: 'up' }))?.props.label).toBe('▲ 31 more')
    await tall.unmount()
  })
  test('the wheel reaches the last issue at 60, then lets the pane scroll', async ($, on) => {
    let passedOn = 0
    on('ui.scroll', async () => {
      passedOn++
      return {}
    })
    seed(on, queued(80))
    const ui = await $.ui.mount(atHeight(60))
    for (let i = 0; i < 31; i++) await $.ui.scroll({ ...tick, bodyRows: 60, by: 1 })
    await drain()
    expect(await titles(ui)).toEqual(numbered(32, 80))
    expect(passedOn).toBe(0)
    await $.ui.scroll({ ...tick, bodyRows: 60, by: 1 })
    expect(passedOn).toBe(1)
    await ui.unmount()
  })
  for (const { name, seen, tab } of [
    { name: 'a full Queue', seen: queued(80), tab: 'tab-queue' },
    { name: 'an empty Queue', seen: queued(0), tab: 'tab-queue' },
    { name: 'a full Active', seen: working, tab: 'tab-active' },
    { name: 'an empty Active', seen: queued(0), tab: 'tab-active' },
    { name: 'a full Finished', seen: finished, tab: 'tab-finished' },
    { name: 'an empty Finished', seen: queued(0), tab: 'tab-finished' },
  ]) {
    test(`${name} takes 49 rows at 60`, async ($, on) => {
      seed(on, seen)
      const ui = await $.ui.mount(atHeight(60))
      await ui.press({ key: tab })
      await drain()
      expect(await listRows(ui)).toBe(49)
      await ui.unmount()
    })
  }

  // Jobs and a queue together, so one mount shows both minimums.
  const both: Seen = { ...working, status: { ...working.status!, queue: queued(30).status!.queue } }
  for (const { name, pane } of [
    { name: 'at 30', pane: atHeight(30) },
    { name: 'at 29', pane: atHeight(29) },
    { name: 'at 16.5', pane: atHeight(16.5) },
    { name: 'at 0', pane: atHeight(0) },
    { name: 'with no bodyRows', pane: { ...PANE, props: { ...PANE.props, scroll: { offset: 0 } } } },
    { name: 'with no scroll', pane: { ...PANE, props: { ...PANE.props, scroll: undefined } } },
  ]) {
    test(`${name}, the lists keep 3 jobs and 21 issues`, async ($, on) => {
      seed(on, both)
      const ui = await $.ui.mount(pane as never)
      expect((await titles(ui)).length).toBe(3)
      await ui.press({ key: 'tab-queue' })
      await drain()
      expect(await titles(ui)).toEqual(numbered(1, 21))
      await ui.unmount()
    })
  }
})

group("a job's pull request button", () => {
  const WEB = 'https://example.test/pull/12'
  // Nothing active or waiting, so the pane opens on Finished, where the job is.
  const finished = (pr: string): Seen => ({ ...MANY, status: { ...MANY.status!, queue: [], issues: [{ ...FINISHED(12, 1), pr }] } })

  // Press the button with each opener exiting as `exits` says, and record what came of it. Two openers
  // and a copy take more turns than one drain gives, and a check that nothing was copied mustn't run early.
  type Mounted = { press: (q: { key: string }) => Promise<unknown>; unmount: () => Promise<unknown> }
  async function press(mount: () => Promise<Mounted>, on: On, pr: string, exits: Record<string, number>) {
    const ran: string[][] = []
    const copied: string[] = []
    const toasts: string[] = []
    on('process.run', async (_$, e) => {
      ran.push([...e.argv])
      return { value: { exitCode: exits[e.argv[0] ?? ''] ?? 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    })
    on('ui.copy', async (_$, e) => {
      copied.push(e.text)
      return { value: { isCopied: true } }
    })
    on('ui.toast', async (_$, e) => {
      toasts.push(e.text)
      return { value: undefined }
    })
    seed(on, finished(pr))
    const ui = await mount()
    await ui.press({ key: 'pr-12' })
    await drain()
    await drain()
    await ui.unmount()
    return { ran, copied, toasts }
  }

  test('an https link opens in the browser and nothing is copied', async ($, on) => {
    const { ran, copied, toasts } = await press(() => $.ui.mount(PANE), on, WEB, { open: 0 })
    expect(ran).toEqual([['open', WEB]])
    expect(copied).toEqual([])
    expect(toasts).toEqual([])
  })
  test('any other link reaches no opener and is copied', async ($, on) => {
    const local = '/Applications/Calculator.app'
    const { ran, copied, toasts } = await press(() => $.ui.mount(PANE), on, local, {})
    expect(ran.filter(argv => argv.includes(local))).toEqual([])
    expect(copied).toEqual([local])
    expect(toasts).toEqual(["That pull request link isn't a web link, so it's copied"])
  })
  test('with no opener working, the link is copied and the toast says so', async ($, on) => {
    const { ran, copied, toasts } = await press(() => $.ui.mount(PANE), on, WEB, {})
    expect(ran).toEqual([['open', WEB], ['xdg-open', WEB]])
    expect(copied).toEqual([WEB])
    expect(toasts).toEqual(["Couldn't open the browser, so the pull request link is copied"])
  })
  test('when open fails and xdg-open works, nothing is copied', async ($, on) => {
    const { ran, copied, toasts } = await press(() => $.ui.mount(PANE), on, WEB, { 'xdg-open': 0 })
    expect(ran).toEqual([['open', WEB], ['xdg-open', WEB]])
    expect(copied).toEqual([])
    expect(toasts).toEqual([])
  })
})

group('a job in the pane', () => {
  // Six minutes and twelve seconds ago, as loop.py writes it: local, to the second, with no zone.
  const d = new Date(Math.floor(Date.now() / 1000) * 1000 - 372_000)
  const p = (n: number) => String(n).padStart(2, '0')
  const started = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  const working: Seen = {
    ...SEEN(false),
    status: {
      running: true, updated: null, tmux: 'loop-starter', queue: [],
      issues: [{ number: 12, title: 'Gate', step: 'BUILD', state: 'working', round: 2, max_rounds: 5,
        tests: null, review: null, pr: null, note: '', started }],
    },
  }
  test('has a dot and says when it started and how long it has been running', async ($, on) => {
    seed(on, working)
    const ui = await $.ui.mount(PANE)
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('●')
    expect(drawn).toContain(`started ${p(d.getHours())}:${p(d.getMinutes())} · running 6m 1`)
    await ui.unmount()
  })
  test('the clock has a line of its own under the title, apart from the step', async ($, on) => {
    seed(on, working)
    const ui = await $.ui.mount(PANE)
    const clockRow = JSON.stringify(await ui.find({ key: 'clock-12' }))
    expect(clockRow).toContain(`started ${p(d.getHours())}:${p(d.getMinutes())}`)
    expect(clockRow).not.toContain('building')
    expect(JSON.stringify(await ui.drawn())).not.toContain(' · started')
    await ui.unmount()
  })
  test('tokens and cost follow the time in the same single-line clock text', async ($, on) => {
    // Two jobs at once, one with usage and one without, so one mount compares their heights.
    const job = working.status!.issues[0]
    seed(on, { ...working, status: { ...working.status!, issues: [
      { ...job, tokens: 840_000, cost_usd: 3.4 }, { ...job, number: 13, title: 'Other' }] } })
    const ui = await $.ui.mount(PANE)
    const height = async (key: string) =>
      ((await ui.find({ key })) as unknown as { props?: { height?: number } } | undefined)?.props?.height
    // The job keeps the rows it has without usage.
    expect(await height('issue-12')).toBeDefined()
    expect(await height('issue-12')).toBe(await height('issue-13'))
    // One string in one Text under the clock key: usage is part of the time's line, not a row of its own.
    expect(JSON.stringify(await ui.find({ key: 'clock-12' }))).toMatch(/"started [^"]* · running [^"]* · 840k tokens · ~\$3\.40"/)
    expect(JSON.stringify(await ui.find({ key: 'clock-13' }))).not.toContain('tokens')
    await ui.unmount()
  })
  test('a job with no clock keeps the line, so every job takes the same rows', async ($, on) => {
    const old = { ...working, status: { ...working.status!, issues: [{ ...working.status!.issues[0], started: undefined }] } }
    seed(on, old)
    const ui = await $.ui.mount(PANE)
    expect(await ui.find({ key: 'clock-12' })).toBeDefined()
    expect(JSON.stringify(await ui.drawn())).not.toContain('started')
    await ui.unmount()
  })
  test("the header's Running dot pulses with the job's", async ($, on) => {
    seed(on, working)
    const ui = await $.ui.mount(PANE)
    type Node = { props?: Record<string, unknown>; children?: (Node | string)[] }
    const first = (n: Node | string | undefined): Node => (n as Node).children![0] as Node
    // The header's state is its second child: the dot, then the words. A job's dot leads its first row.
    const state = (await ui.find({ key: 'header' }) as unknown as Node).children![1] as Node
    const headerDot = first(state)
    const jobDot = first(first(await ui.find({ key: 'issue-12' }) as unknown as Node))
    expect(headerDot.children).toEqual(['●'])
    expect(JSON.stringify(state.children![1])).toContain(' Running')
    // Drawn from the same beat, so the two dots brighten and dim together.
    expect(headerDot.props).toEqual(jobDot.props)
    await ui.unmount()
  })
})

group('project loops', () => {
  const ROOT = '/h/starter'
  const HARNESS = `${ROOT}/.loop`
  const ALPHA = `${ROOT}/.loop/projects/alpha`
  const BETA = `${ROOT}/.loop/projects/beta`
  const statusText = (title: string, extra: object = {}) =>
    JSON.stringify({ running: false, tmux: null, queue: [{ number: 30, title }], issues: [], ...extra })
  const JOB = { number: 12, title: 'Gate', step: 'BUILD', state: 'working', round: 1, tests: null, review: null, pr: null, note: '', window: 'issue-12' }

  // What fs.stat finds directly under the harness's projects/, by name. Anything not named isn't there.
  type Kinds = Record<string, 'dir' | 'file' | 'link'>
  type Focus = {
    // This session's id, from a variable the test can change. Null is an id the engine refuses, the default.
    session?: { id: string | null }
    projects?: Kinds
  }

  // The engine beneath the plugin: a harness whose loop files are `files`, by path, and an open pane.
  // The folders under .loop/projects come from those paths. The test changes `files` between polls,
  // `panes` to stand a pane behind another, and `flip` to refuse a close, take the root away, refuse
  // every write or hold one open. fs.read records each path it reads, and fs.write each path and text, storing the text
  // in `files`. Nothing touches the disk.
  function world(on: On, files: Map<string, string>, focus: Focus = {}) {
    const clock = mock.clock(on, { now: 1_800_000_000_000 })
    const toasts: string[] = []
    const ran: string[][] = []
    const reads: string[] = []
    const stats: string[] = []
    const writes: { path: string; text: string }[] = []
    const session = focus.session ?? { id: null }
    let idsAsked = 0
    const panes: { id: string; isShown: boolean; isPlaced: boolean }[] = []
    const flip = { closeFails: false, rootGone: false, writesFail: false, held: null as Promise<void> | null }
    on('session.root', async () => ({ value: ROOT }))
    on('session.id', async () => {
      idsAsked++
      return session.id === null ? { deny: 'no session id' } : { value: session.id }
    })
    on('fs.exists', async (_$, e) => ({ value: (e.path === `${ROOT}/scripts/loop.py` && !flip.rootGone) || files.has(e.path) }))
    on('fs.read', async (_$, e) => {
      reads.push(e.path)
      const text = files.get(e.path)
      return text === undefined ? { deny: `no ${e.path}` } : { value: text }
    })
    on('fs.write', async (_$, e) => {
      if (flip.writesFail) return { deny: 'read-only' }
      writes.push({ path: e.path, text: e.text })
      files.set(e.path, e.text)
      // A held write has stored its text but not yet returned, until the test lets it go.
      if (flip.held) await flip.held
      return { value: undefined }
    })
    on('fs.stat', async (_$, e) => {
      stats.push(e.path)
      const name = e.path.startsWith(`${ROOT}/projects/`) ? e.path.slice(`${ROOT}/projects/`.length) : ''
      const kind = (focus.projects ?? {})[name]
      if (kind === 'dir') return { value: { kind: 'dir', size: 0, mtimeMs: 0, isLink: false } }
      if (kind === 'file') return { value: { kind: 'file', size: 1, mtimeMs: 0, isLink: false } }
      if (kind === 'link') return { value: { kind: 'dir', size: 0, mtimeMs: 0, isLink: true } }
      return { deny: `no ${e.path}` }
    })
    on('fs.list', async (_$, e) => {
      if (e.path !== `${ROOT}/.loop/projects`) return { deny: `no ${e.path}` }
      const names = [...files.keys()].flatMap(p => p.match(/\/\.loop\/projects\/([^/]+)\//)?.[1] ?? [])
      return { value: [...new Set(names)].map(name => ({ name, kind: 'dir' as const, size: 0 })) } as never
    })
    on('process.run', async (_$, e) => {
      ran.push([...e.argv])
      return { value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    })
    on('ui.open', async () => {
      panes.length = 0
      panes.push({ id: 'loop', isShown: true, isPlaced: true })
      return { value: { isPlaced: true } }
    })
    on('ui.close', async () => {
      if (flip.closeFails) return { deny: 'refused' }
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
    return {
      clock, toasts, panes, flip, close, reads, stats, writes, session,
      idsAsked: () => idsAsked,
      opened: () => ran.filter(argv => argv[0] === 'open'),
    }
  }

  type Dollar = { command: { run: (i: object) => Promise<unknown> } }
  const typed = { command: 'loop-pane', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } }
  const open = async ($: Dollar) => { await $.command.run(typed) }
  // The command again, for what it says.
  const say = async ($: Dollar) => ((await $.command.run(typed)) as { text?: string }).text ?? ''
  // Past the poll's next read of the loop's files.
  const POLL = 2000

  const twoLoops = () => new Map([
    [`${HARNESS}/status.json`, statusText('harness job')],
    [`${ALPHA}/status.json`, statusText('alpha job')],
  ])
  const threeLoops = () => new Map([
    [`${HARNESS}/status.json`, statusText('harness job')],
    [`${ALPHA}/status.json`, statusText('alpha job')],
    [`${BETA}/status.json`, statusText('beta job')],
    [`${ROOT}/.loop/projects/never-ran/notes`, 'a clone with no status file'],
  ])
  const left = async (ui: { find: (q: { key: string }) => Promise<unknown> }) => JSON.stringify(await ui.find({ key: 'header' }))
  // The dropdown's options as drawn now.
  const pickOptions = async (ui: { find: (q: { key: string }) => Promise<unknown> }) =>
    ((await ui.find({ key: 'loop-pick' })) as { props: { options: { value: string; label: string }[] } }).props.options

  test('there is no row without projects', async ($, on) => {
    const { close } = world(on, new Map([[`${HARNESS}/status.json`, statusText('harness job')]]))
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect(await ui.find({ key: 'loops' })).toBeUndefined()
    expect(await ui.find({ key: 'loop-pick' })).toBeUndefined()
    expect(await ui.find({ key: 'tab-queue' })).toBeDefined()
    await ui.unmount()
    await close()
  })
  test('with projects, the row names the harness then each project in order, above the tabs', async ($, on) => {
    const { close } = world(on, threeLoops())
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect((await pickOptions(ui)).map(o => o.label)).toEqual(['starter', 'alpha', 'beta'])
    const top = (await ui.drawn()) as unknown as { children: unknown[] }
    const at = (needle: string) => top.children.findIndex(c => JSON.stringify(c).includes(needle))
    expect(at('"loop-pick"')).toBeGreaterThan(-1)
    expect(at('"loop-pick"')).toBeLessThan(at('"tab-queue"'))
    await ui.unmount()
    await close()
  })
  test('with the row showing, the whole pane fits its height on every tab', async ($, on) => {
    const { close } = world(on, twoLoops())
    await open($ as unknown as Dollar)
    for (const bodyRows of [30, 45, 60]) {
      const ui = await $.ui.mount(atHeight(bodyRows))
      expect(await ui.find({ key: 'loop-pick' })).toBeDefined()
      for (const key of ['tab-queue', 'tab-active', 'tab-finished']) {
        await ui.press({ key })
        await drain()
        expect(rowsOf((await ui.drawn()) as unknown as Drawn)).toBeLessThan(bodyRows + 1)
      }
      await ui.unmount()
    }
    await close()
  })
  test('a loop on one job marks its button, and on two adds the count', async ($, on) => {
    const files = threeLoops()
    files.set(`${ALPHA}/status.json`, statusText('alpha job', { issues: [JOB] }))
    files.set(`${ALPHA}/lock`, '4242')
    const { clock, close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    const label = async (value: string) => (await pickOptions(ui)).find(o => o.value === value)?.label
    expect(await label('alpha')).toBe('● alpha')
    expect(await label('beta')).toBe('beta')
    files.set(`${ALPHA}/status.json`, statusText('alpha job', { issues: [JOB, { ...JOB, number: 13 }] }))
    await clock.advance(POLL)
    expect(await label('alpha')).toBe('● alpha 2')
    await ui.unmount()
    await close()
  })
  test("a loop off screen shows its marker without its button lighting, and the header's left side has none", async ($, on) => {
    const files = threeLoops()
    for (const dir of [ALPHA, BETA]) {
      files.set(`${dir}/status.json`, statusText('a job', { issues: [JOB] }))
      files.set(`${dir}/lock`, '4242')
    }
    const { close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount({ ...PANE, surface: 'mobile' })
    await ui.press({ key: 'loop-beta' })
    await drain()
    const alpha = await ui.find({ key: 'loop-alpha' })
    expect(alpha?.props.label).toBe('● alpha')
    expect(alpha?.props.variant).toBeUndefined()
    expect(alpha?.props.dimColor).toBe(true)
    const beta = await ui.find({ key: 'loop-beta' })
    expect(beta?.props.label).toBe('● beta')
    expect(beta?.props.variant).toBe('primary')
    const header = (await ui.find({ key: 'header' })) as unknown as { children: { children: string[] }[] }
    expect(header.children[0]?.children).toEqual(['beta'])
    await ui.unmount()
    await close()
  })
  test("pressing a project shows its queue, and its STOP shows as stopping", async ($, on) => {
    const files = threeLoops()
    files.set(`${ALPHA}/lock`, '4242')
    files.set(`${ALPHA}/STOP`, '')
    files.set(`${HARNESS}/lock`, '4242')
    const { close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect(await titles(ui)).toEqual(['#30 harness job'])
    await ui.select({ key: 'loop-pick', value: 'alpha' })
    await drain()
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    const head = await left(ui)
    expect(head).toContain('alpha')
    expect(head).toContain('Stopping after this step')
    await ui.unmount()
    await close()
  })
  test("Watch it and a job's Watch open the project's own files", async ($, on) => {
    const files = threeLoops()
    files.set(`${ALPHA}/status.json`, statusText('alpha job', { tmux: 'loop-alpha', issues: [JOB] }))
    files.set(`${ALPHA}/lock`, '4242')
    files.set(`${ALPHA}/watch.command`, '')
    const { opened, close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'watch' })
    await ui.press({ key: 'watch-12' })
    await drain()
    expect(opened()).toEqual([['open', `${ALPHA}/watch.command`], ['open', `${ALPHA}/issue-12/watch.command`]])
    await ui.unmount()
    await close()
  })
  test('the pane opens on a running project, the pick then holds, and closing and reopening picks again', async ($, on) => {
    const files = threeLoops()
    files.set(`${BETA}/lock`, '4242')
    const { clock, close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect(await titles(ui)).toEqual(['#30 beta job'])
    // The harness starts: it comes first when opening, but the pane doesn't jump to it.
    files.set(`${HARNESS}/lock`, '4242')
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 beta job'])
    // On a showing pane the command closes it, which isn't a new pick.
    await open($ as unknown as Dollar)
    expect(await titles(ui)).toEqual(['#30 beta job'])
    await clock.advance(500)
    await open($ as unknown as Dollar)
    expect(await titles(ui)).toEqual(['#30 harness job'])
    await ui.unmount()
    await close()
  })
  test('/loop-pane closes a showing pane and says so', async ($, on) => {
    const { panes, close } = world(on, threeLoops())
    await open($ as unknown as Dollar)
    expect(await say($ as unknown as Dollar)).toBe('Loop pane closed.')
    expect(panes).toEqual([])
    await close()
  })
  test('a close that fails points at the ×, keeps the pick and keeps polling', async ($, on) => {
    const files = threeLoops()
    const { clock, panes, flip, close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    await ui.select({ key: 'loop-pick', value: 'beta' })
    await drain()
    flip.closeFails = true
    expect(await say($ as unknown as Dollar)).toBe("The loop pane couldn't close. The × in its corner closes it.")
    expect(panes.length).toBe(1)
    expect(await titles(ui)).toEqual(['#30 beta job'])
    files.set(`${BETA}/status.json`, statusText('beta changed'))
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 beta changed'])
    await ui.unmount()
    await close()
  })
  test('a showing pane whose root has gone still closes', async ($, on) => {
    const { panes, flip, close } = world(on, threeLoops())
    await open($ as unknown as Dollar)
    flip.rootGone = true
    expect(await say($ as unknown as Dollar)).toBe('Loop pane closed.')
    expect(panes).toEqual([])
    await close()
  })
  test('a pane behind another opens instead of closing', async ($, on) => {
    const { panes, close } = world(on, threeLoops())
    await open($ as unknown as Dollar)
    panes[0] = { id: 'loop', isShown: false, isPlaced: true }
    expect(await say($ as unknown as Dollar)).toBe('Loop pane opened.')
    expect(panes).toEqual([{ id: 'loop', isShown: true, isPlaced: true }])
    await close()
  })
  test('a pane not placed opens instead of closing', async ($, on) => {
    const { panes, close } = world(on, threeLoops())
    await open($ as unknown as Dollar)
    panes[0] = { id: 'loop', isShown: false, isPlaced: false }
    expect(await say($ as unknown as Dollar)).toBe('Loop pane opened.')
    expect(panes).toEqual([{ id: 'loop', isShown: true, isPlaced: true }])
    await close()
  })
  test('closed and reopened, the pane polls again', async ($, on) => {
    const files = threeLoops()
    const { clock, close } = world(on, files)
    await open($ as unknown as Dollar)
    expect(await say($ as unknown as Dollar)).toBe('Loop pane closed.')
    await clock.advance(500)
    expect(await say($ as unknown as Dollar)).toBe('Loop pane opened.')
    const ui = await $.ui.mount(PANE)
    files.set(`${HARNESS}/status.json`, statusText('harness changed'))
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 harness changed'])
    await ui.unmount()
    await close()
  })
  test("a picked project whose folder has gone falls back to the harness, on the harness's busiest tab", async ($, on) => {
    const files = threeLoops()
    const { clock, close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    await ui.select({ key: 'loop-pick', value: 'alpha' })
    await drain()
    await ui.press({ key: 'tab-finished' })
    await drain()
    files.delete(`${ALPHA}/status.json`)
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 harness job'])
    expect((await pickOptions(ui)).map(o => o.value)).toEqual(['', 'beta'])
    expect((await ui.find({ key: 'loop-pick' }))?.props.value).toBe('')
    await ui.unmount()
    await close()
  })
  test('switching loops raises no toast, and a change in a loop off screen raises one with its name', async ($, on) => {
    const files = threeLoops()
    const issues = [{ ...JOB, state: 'working' }]
    files.set(`${HARNESS}/status.json`, statusText('harness job', { issues }))
    files.set(`${BETA}/status.json`, statusText('beta job', { issues }))
    const { clock, toasts, close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    await ui.select({ key: 'loop-pick', value: 'alpha' })
    await drain()
    await clock.advance(POLL)
    await ui.select({ key: 'loop-pick', value: '' })
    await drain()
    await clock.advance(POLL)
    expect(toasts).toEqual([])
    files.set(`${BETA}/status.json`, statusText('beta job', { issues: [{ ...JOB, state: 'pr', pr: 'https://x/pull/2' }] }))
    await clock.advance(POLL)
    expect(toasts).toEqual(['beta: #12 has a pull request'])
    await ui.unmount()
    await close()
  })

  // The harness and four projects, by name alpha, beta, delta, gamma.
  const project = (name: string) => `${ROOT}/.loop/projects/${name}`
  const fiveLoops = () => new Map<string, string>([
    ...threeLoops(),
    [`${project('delta')}/status.json`, statusText('delta job')],
    [`${project('gamma')}/status.json`, statusText('gamma job')],
  ])
  const sixLoops = () => new Map<string, string>([...fiveLoops(), [`${project('omega')}/status.json`, statusText('omega job')]])
  const fourLoops = () => {
    const files = fiveLoops()
    files.delete(`${project('gamma')}/status.json`)
    return files
  }
  const onAJob = (files: Map<string, string>, name: string) => {
    files.set(`${project(name)}/status.json`, statusText(`${name} job`, { issues: [JOB] }))
    files.set(`${project(name)}/lock`, '4242')
  }
  const onAJobWithNothingWaiting = (files: Map<string, string>, name: string) => {
    files.set(`${project(name)}/status.json`, statusText(`${name} job`, { queue: [], issues: [JOB] }))
    files.set(`${project(name)}/lock`, '4242')
  }
  // The line beside the dropdown. Anchored and case-sensitive, so the header's "● Running" can't match.
  const COUNT_LINE = /^(● \d+ running|\d+ queued)/
  const PICKER_SURFACES = ['terminal', 'vscode', 'desktop'] as const

  for (const surface of PICKER_SURFACES) {
    test(`two loops on ${surface} have the dropdown and no row of buttons`, async ($, on) => {
      const { close } = world(on, twoLoops())
      await open($ as unknown as Dollar)
      const ui = await $.ui.mount({ ...PANE, surface })
      expect((await pickOptions(ui)).map(o => o.value)).toEqual(['', 'alpha'])
      expect(await ui.find({ key: 'loops' })).toBeUndefined()
      await ui.unmount()
      await close()
    })
  }
  for (const surface of PICKER_SURFACES) {
    test(`more than one loop on ${surface}, a dropdown takes the buttons' row, with the working loops first`, async ($, on) => {
      const files = fiveLoops()
      onAJob(files, 'beta')
      onAJob(files, 'gamma')
      const { close } = world(on, files)
      await open($ as unknown as Dollar)
      const ui = await $.ui.mount({ ...PANE, surface })
      expect(await ui.find({ key: 'loops' })).toBeUndefined()
      expect(await ui.find({ key: 'loop-alpha' })).toBeUndefined()
      const pick = await ui.find({ key: 'loop-pick' })
      expect(pick?.props.options).toEqual([
        { value: 'beta', label: '● beta' },
        { value: 'gamma', label: '● gamma' },
        { value: '', label: 'starter' },
        { value: 'alpha', label: 'alpha' },
        { value: 'delta', label: 'delta' },
      ])
      expect(pick?.props.value).toBe('beta')
      expect(pick?.props.label).toBeUndefined()
      // One row between them, the dropdown and the count line, so the list below keeps its place.
      const children = ((await ui.drawn()) as unknown as Drawn).children ?? []
      const row = children.find(c => JSON.stringify(c).includes('"loop-pick"'))
      expect(JSON.stringify(row)).toContain('● 2 running · 2 queued')
      expect(rowsOf(row as Drawn)).toBe(1)
      await ui.unmount()
      await close()
    })
  }
  test('picking a project shows it, and picking the harness comes back', async ($, on) => {
    const { close } = world(on, fiveLoops())
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    await ui.select({ key: 'loop-pick', value: 'alpha' })
    await drain()
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    expect((await ui.find({ key: 'loop-pick' }))?.props.value).toBe('alpha')
    await ui.select({ key: 'loop-pick', value: '' })
    await drain()
    expect(await titles(ui)).toEqual(['#30 harness job'])
    expect((await ui.find({ key: 'loop-pick' }))?.props.value).toBe('')
    await ui.unmount()
    await close()
  })
  for (const { working, count } of [
    { working: ['alpha', 'beta'], count: ['● 2 running · 2 queued'] },
    { working: ['alpha', 'beta', 'delta', 'gamma'], count: ['● 4 running · 4 queued'] },
    { working: ['alpha'], count: ['● 1 running · 1 queued'] },
  ]) {
    test(`with ${working.length} on a job, the pane opens on the first and the count line says ${count[0]}`, async ($, on) => {
      const files = fiveLoops()
      for (const name of working) onAJob(files, name)
      const { close } = world(on, files)
      await open($ as unknown as Dollar)
      const ui = await $.ui.mount(PANE)
      expect((await ui.find({ key: 'loop-pick' }))?.props.value).toBe('alpha')
      const lines = await ui.findAll({ type: 'Text', text: COUNT_LINE })
      expect(lines.map(t => t.text)).toEqual(count)
      await ui.unmount()
      await close()
    })
  }
  test('the count line counts running and queued loops apart', async ($, on) => {
    const files = fiveLoops()
    onAJobWithNothingWaiting(files, 'alpha')
    onAJobWithNothingWaiting(files, 'beta')
    files.set(`${project('delta')}/lock`, '4242')
    const { close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    const lines = await ui.findAll({ type: 'Text', text: COUNT_LINE })
    expect(lines.map(t => t.text)).toEqual(['● 2 running · 1 queued'])
    await ui.unmount()
    await close()
  })
  test('the loop on screen counts, and with nothing queued the line says only running', async ($, on) => {
    const files = fiveLoops()
    onAJobWithNothingWaiting(files, 'alpha')
    const { close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect((await ui.find({ key: 'loop-pick' }))?.props.value).toBe('alpha')
    const lines = await ui.findAll({ type: 'Text', text: COUNT_LINE })
    expect(lines.map(t => t.text)).toEqual(['● 1 running'])
    await ui.unmount()
    await close()
  })
  test('a live loop with a queue and no job says only queued', async ($, on) => {
    const files = fiveLoops()
    files.set(`${project('alpha')}/lock`, '4242')
    const { close } = world(on, files)
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    const lines = await ui.findAll({ type: 'Text', text: COUNT_LINE })
    expect(lines.map(t => t.text)).toEqual(['1 queued'])
    await ui.unmount()
    await close()
  })
  test('queues with no live lock add nothing, so there is no count line', async ($, on) => {
    const { close } = world(on, fiveLoops())
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect(await ui.findAll({ type: 'Text', text: COUNT_LINE })).toEqual([])
    await ui.unmount()
    await close()
  })
  test("a pick opens on that loop's busiest tab and holds through the next poll", async ($, on) => {
    const { clock, close } = world(on, fiveLoops())
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'tab-finished' })
    await drain()
    await ui.select({ key: 'loop-pick', value: 'alpha' })
    await drain()
    expect((await ui.find({ key: 'tab-queue' }))?.props.variant).toBe('primary')
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    await clock.advance(POLL)
    expect((await ui.find({ key: 'tab-queue' }))?.props.variant).toBe('primary')
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    await ui.unmount()
    await close()
  })
  test('four loops on mobile keep their buttons', async ($, on) => {
    const { close } = world(on, fourLoops())
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount({ ...PANE, surface: 'mobile' })
    expect(await ui.find({ key: 'loop-pick' })).toBeUndefined()
    const row = await ui.find({ key: 'loops' })
    const labels = (row?.children as unknown as { props: { label: string } }[]).map(c => c.props.label)
    expect(labels).toEqual(['starter', 'alpha', 'beta', 'delta'])
    await ui.unmount()
    await close()
  })
  test('six loops on mobile keep their buttons, since the app draws no dropdown', async ($, on) => {
    const { close } = world(on, sixLoops())
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount({ ...PANE, surface: 'mobile' })
    expect(await ui.find({ key: 'loop-pick' })).toBeUndefined()
    const row = await ui.find({ key: 'loops' })
    const labels = (row?.children as unknown as { props: { label: string } }[]).map(c => c.props.label)
    expect(labels).toEqual(['starter', 'alpha', 'beta', 'delta', 'gamma', 'omega'])
    await ui.unmount()
    await close()
  })
  test('with the dropdown showing, the whole pane fits its height on every tab', async ($, on) => {
    const { close } = world(on, sixLoops())
    await open($ as unknown as Dollar)
    for (const bodyRows of [30, 45, 60]) {
      const ui = await $.ui.mount(atHeight(bodyRows))
      expect(await ui.find({ key: 'loop-pick' })).toBeDefined()
      for (const key of ['tab-queue', 'tab-active', 'tab-finished']) {
        await ui.press({ key })
        await drain()
        expect(rowsOf((await ui.drawn()) as unknown as Drawn)).toBeLessThan(bodyRows + 1)
      }
      await ui.unmount()
    }
    await close()
  })
  test('the end of the list at 30, drawn at 60, moves up one from what it shows', async ($, on) => {
    seed(on, queued(80))
    const low = await $.ui.mount(atHeight(30))
    for (let i = 0; i < 59; i++) {
      await low.press({ key: 'down' })
      await drain()
    }
    await low.unmount()
    const tall = await $.ui.mount(atHeight(60))
    await tall.press({ key: 'up' })
    await drain()
    expect((await tall.find({ key: 'up' }))?.props.label).toBe('▲ 30 more')
    await tall.unmount()
  })

  // The session's project focus, the file /project and the GitHub line keep at .harness/project/<id>.
  const A = 'aaaaaaaa-1111'
  const B = 'bbbbbbbb-2222'
  const FOCUS = (id: string) => `${ROOT}/.harness/project/${id}`
  const underFocus = (path: string) => path.includes('/.harness/project/')
  // A pick switches, then writes and reads the focus back: several engine calls, so wait out more turns.
  const settle = async () => {
    for (let i = 0; i < 10; i++) await drain()
  }
  const FOLDERS: Kinds = { alpha: 'dir', beta: 'dir', gamma: 'dir' }
  const pickValue = async (ui: { find: (q: { key: string }) => Promise<unknown> }) =>
    ((await ui.find({ key: 'loop-pick' })) as { props: { value?: unknown } } | undefined)?.props.value
  // threeLoops, with beta running, so an opening with no focus shows beta.
  const betaRunning = () => {
    const files = threeLoops()
    files.set(`${BETA}/lock`, '4242')
    return files
  }

  test('a pane opened with a project in focus shows it, and opening writes nothing', async ($, on) => {
    const files = betaRunning()
    files.set(FOCUS(A), 'alpha\n')
    const { clock, writes, close } = world(on, files, { session: { id: A }, projects: FOLDERS })
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    expect(await pickValue(ui)).toBe('alpha')
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    expect(files.get(FOCUS(A))).toBe('alpha\n')
    expect(writes).toEqual([])
    await ui.unmount()
    await close()
  })
  const unusable: { why: string; text: string; projects: Kinds; stat?: string }[] = [
    { why: 'a project with no loop listed', text: 'gamma\n', projects: FOLDERS, stat: `${ROOT}/projects/gamma` },
    { why: 'a projects/ entry that is a link', text: 'alpha\n', projects: { alpha: 'link' }, stat: `${ROOT}/projects/alpha` },
    { why: 'a projects/ entry that is a file', text: 'alpha\n', projects: { alpha: 'file' }, stat: `${ROOT}/projects/alpha` },
    { why: 'file text ../x', text: '../x\n', projects: FOLDERS },
  ]
  for (const { why, text, projects, stat } of unusable) {
    test(`a focus on ${why} is read, and the pane opens as it did`, async ($, on) => {
      const files = betaRunning()
      files.set(FOCUS(A), text)
      const { reads, stats, writes, close } = world(on, files, { session: { id: A }, projects })
      await open($ as unknown as Dollar)
      const ui = await $.ui.mount(PANE)
      expect(await titles(ui)).toEqual(['#30 beta job'])
      expect(reads).toContain(FOCUS(A))
      if (stat) expect(stats).toContain(stat)
      else expect(stats.filter(p => p.startsWith(`${ROOT}/projects/`))).toEqual([])
      expect(writes).toEqual([])
      await ui.unmount()
      await close()
    })
  }
  for (const { why, id } of [{ why: 'refused', id: null }, { why: "'../x'", id: '../x' }]) {
    test(`a session id ${why} is asked for, no focus file is read or written, and a pick still switches`, async ($, on) => {
      const files = threeLoops()
      files.set(FOCUS(A), 'alpha\n')
      const { clock, reads, writes, idsAsked, close } = world(on, files, { session: { id }, projects: FOLDERS })
      await open($ as unknown as Dollar)
      const ui = await $.ui.mount(PANE)
      expect(await titles(ui)).toEqual(['#30 harness job'])
      await ui.select({ key: 'loop-pick', value: 'alpha' })
      await settle()
      expect(await titles(ui)).toEqual(['#30 alpha job'])
      await clock.advance(POLL)
      expect(await titles(ui)).toEqual(['#30 alpha job'])
      expect(idsAsked()).toBeGreaterThan(0)
      expect(reads.filter(underFocus)).toEqual([])
      expect(writes.filter(w => underFocus(w.path))).toEqual([])
      await ui.unmount()
      await close()
    })
  }
  test('a change of focus moves the pane at the next read, and a cleared focus moves it to the harness', async ($, on) => {
    const files = threeLoops()
    files.set(FOCUS(A), 'alpha\n')
    const { clock, writes, close } = world(on, files, { session: { id: A }, projects: FOLDERS })
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    files.set(FOCUS(A), 'beta\n')
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 beta job'])
    expect(await pickValue(ui)).toBe('beta')
    files.set(FOCUS(A), '')
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 harness job'])
    expect(await pickValue(ui)).toBe('')
    expect(writes).toEqual([])
    await ui.unmount()
    await close()
  })
  test("a focus on a project with no loop leaves the pane where it is, even once that loop appears", async ($, on) => {
    const files = threeLoops()
    files.set(FOCUS(A), 'alpha\n')
    const { clock, close } = world(on, files, { session: { id: A }, projects: FOLDERS })
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    files.set(FOCUS(A), 'gamma\n')
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    files.set(`${project('gamma')}/status.json`, statusText('gamma job'))
    await clock.advance(POLL)
    expect((await pickOptions(ui)).map(o => o.value)).toContain('gamma')
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    await ui.unmount()
    await close()
  })
  test('with the focus unchanged, a pick holds across reads, a loop with no projects/ folder included', async ($, on) => {
    const files = threeLoops()
    files.set(FOCUS(A), 'alpha\n')
    // beta has a loop but no folder under projects/, so the file naming it means no focus.
    const { clock, close } = world(on, files, { session: { id: A }, projects: { alpha: 'dir' } })
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    await ui.select({ key: 'loop-pick', value: 'beta' })
    await settle()
    expect(files.get(FOCUS(A))).toBe('beta\n')
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 beta job'])
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 beta job'])
    expect(await pickValue(ui)).toBe('beta')
    await ui.unmount()
    await close()
  })
  test('a pick in the dropdown or on a mobile button writes the focus, and the harness writes it empty', async ($, on) => {
    const { writes, close } = world(on, threeLoops(), { session: { id: A }, projects: FOLDERS })
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    await ui.select({ key: 'loop-pick', value: 'alpha' })
    await settle()
    await ui.unmount()
    expect(writes).toEqual([{ path: FOCUS(A), text: 'alpha\n' }])
    const phone = await $.ui.mount({ ...PANE, surface: 'mobile' })
    await phone.press({ key: 'loop' })
    await settle()
    await phone.press({ key: 'loop-alpha' })
    await settle()
    expect(writes).toEqual([
      { path: FOCUS(A), text: 'alpha\n' },
      { path: FOCUS(A), text: '' },
      { path: FOCUS(A), text: 'alpha\n' },
    ])
    await phone.unmount()
    await close()
  })
  test('a pick whose write fails still switches the pane, and holds across the next read', async ($, on) => {
    const files = threeLoops()
    files.set(FOCUS(A), 'alpha\n')
    const { clock, flip, writes, close } = world(on, files, { session: { id: A }, projects: FOLDERS })
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    flip.writesFail = true
    await ui.select({ key: 'loop-pick', value: 'beta' })
    await settle()
    expect(await titles(ui)).toEqual(['#30 beta job'])
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 beta job'])
    expect(writes).toEqual([])
    expect(files.get(FOCUS(A))).toBe('alpha\n')
    await ui.unmount()
    await close()
  })
  // Folders under .loop/projects/ whose names projectName refuses, or changes: ` acme` passes once
  // trimmed, and would be read back as acme, another project.
  for (const odd of ['.hidden', 'a..b', ' acme']) {
    test(`a pick of a loop named ${JSON.stringify(odd)} switches the pane, writes no focus, and holds`, async ($, on) => {
      const files = threeLoops()
      files.set(FOCUS(A), 'alpha\n')
      files.set(`${project(odd)}/status.json`, statusText('odd job'))
      const { clock, writes, close } = world(on, files, { session: { id: A }, projects: { ...FOLDERS, acme: 'dir', [odd]: 'dir' } })
      await open($ as unknown as Dollar)
      const ui = await $.ui.mount(PANE)
      expect(await titles(ui)).toEqual(['#30 alpha job'])
      await ui.select({ key: 'loop-pick', value: odd })
      await settle()
      expect(await titles(ui)).toEqual(['#30 odd job'])
      expect(writes).toEqual([])
      expect(files.get(FOCUS(A))).toBe('alpha\n')
      await clock.advance(POLL)
      expect(await titles(ui)).toEqual(['#30 odd job'])
      expect(await pickValue(ui)).toBe(odd)
      expect(writes).toEqual([])
      await ui.unmount()
      await close()
    })
  }
  test('a read landing while a pick saves the focus leaves the pane on the pick', async ($, on) => {
    const files = threeLoops()
    files.set(FOCUS(A), 'alpha\n')
    // beta has a loop but no folder under projects/, so once the pick writes it the file means no focus.
    const { clock, flip, reads, close } = world(on, files, { session: { id: A }, projects: { alpha: 'dir' } })
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    let release: () => void = () => {}
    flip.held = new Promise<void>(resolve => {
      release = () => resolve()
    })
    const picking = ui.select({ key: 'loop-pick', value: 'beta' })
    await settle()
    expect(files.get(FOCUS(A))).toBe('beta\n')
    // A read lands with beta written and the save not yet back.
    const focusReads = () => reads.filter(p => p === FOCUS(A)).length
    const before = focusReads()
    await clock.advance(POLL)
    expect(focusReads()).toBeGreaterThan(before)
    expect(await titles(ui)).toEqual(['#30 beta job'])
    flip.held = null
    release()
    await picking
    await settle()
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 beta job'])
    expect(await pickValue(ui)).toBe('beta')
    await ui.unmount()
    await close()
  })
  test('a picked loop that disappears falls back to the harness and writes nothing', async ($, on) => {
    const files = threeLoops()
    const { clock, writes, close } = world(on, files, { session: { id: A }, projects: FOLDERS })
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    await ui.select({ key: 'loop-pick', value: 'alpha' })
    await settle()
    expect(writes).toEqual([{ path: FOCUS(A), text: 'alpha\n' }])
    files.delete(`${ALPHA}/status.json`)
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 harness job'])
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 harness job'])
    expect(writes).toEqual([{ path: FOCUS(A), text: 'alpha\n' }])
    await ui.unmount()
    await close()
  })
  test("each session reads and writes only its own focus file", async ($, on) => {
    const files = threeLoops()
    files.set(FOCUS(A), 'alpha\n')
    files.set(FOCUS(B), 'beta\n')
    const { clock, reads, writes, close } = world(on, files, { session: { id: B }, projects: FOLDERS })
    await open($ as unknown as Dollar)
    const ui = await $.ui.mount(PANE)
    expect(await titles(ui)).toEqual(['#30 beta job'])
    await ui.select({ key: 'loop-pick', value: 'alpha' })
    await settle()
    await clock.advance(POLL)
    expect(await titles(ui)).toEqual(['#30 alpha job'])
    expect([...new Set(reads.filter(underFocus))]).toEqual([FOCUS(B)])
    expect(writes).toEqual([{ path: FOCUS(B), text: 'alpha\n' }])
    expect(files.get(FOCUS(A))).toBe('alpha\n')
    await ui.unmount()
    await close()
  })
})

group('on Claude Desktop', () => {
  const DESKTOP = { ...PANE, surface: 'desktop' } as const
  const working: Seen = {
    ...SEEN(true),
    status: {
      running: true, updated: null, tmux: 'loop-starter', queue: [],
      issues: [{ number: 12, title: 'Gate', step: 'BUILD', state: 'working', round: 1, tests: null, review: null,
        pr: null, note: '', window: 'issue-12' }],
    },
  }
  test('draws the header, the buttons and a job with its Watch button', async ($, on) => {
    seed(on, working)
    const ui = await $.ui.mount(DESKTOP)
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('starter')
    expect(drawn).toContain(' Running')
    expect(drawn).toContain('#12 Gate')
    expect(await ui.find({ key: 'watch' })).toBeDefined()
    expect(await ui.find({ key: 'watch-12' })).toBeDefined()
    await ui.unmount()
  })
  test('the header pushes the state right by layout, not by padding', async ($, on) => {
    seed(on, working)
    const ui = await $.ui.mount(DESKTOP)
    const header = await ui.find({ key: 'header' })
    expect(header?.props.justifyContent).toBe('space-between')
    expect(JSON.stringify(header?.children)).not.toMatch(/"\s{3,}"/)
    await ui.unmount()
  })
  test('a short queue holds no more than three list rows open', async ($, on) => {
    seed(on, queued(1))
    const ui = await $.ui.mount(DESKTOP)
    expect(await listRows(ui)).toBe(3)
    await ui.unmount()
  })
  test('a queue past three draws without holding any rows open', async ($, on) => {
    seed(on, queued(30))
    const ui = await $.ui.mount(DESKTOP)
    expect(await titles(ui)).toEqual(numbered(1, 21))
    expect(await listRows(ui)).toBe(21)
    await ui.unmount()
  })
  for (const surface of ['desktop', 'vscode'] as const) {
    test(`on ${surface} long titles and lines show whole, not cut`, async ($, on) => {
      const title = 'A title that is much longer than the sixty columns the pane body has to draw it in'
      const queued = 'A queued title that is also much longer than the sixty columns the body has'
      const note = 'a long note that runs on well past two rows of the sixty columns the pane body has to show it in'
      seed(on, {
        ...working,
        status: {
          ...working.status!,
          queue: [{ number: 31, title: queued, waiting_on: [12] }],
          issues: [{ ...working.status!.issues[0], title, note }],
        },
      })
      const ui = await $.ui.mount({ ...DESKTOP, surface })
      const drawn = JSON.stringify(await ui.drawn())
      expect(drawn).toContain(`#12 ${title}`)
      expect(drawn).toContain(note)
      expect(drawn).not.toContain('…')
      expect((await ui.find({ key: 'issue-12' }))?.props.height).toBeUndefined()
      const detail = await ui.find({ key: 'detail-12' })
      expect(detail?.props.height).toBeUndefined()
      expect(detail?.props.overflow).toBeUndefined()
      await ui.press({ key: 'tab-queue' })
      await drain()
      const queue = JSON.stringify(await ui.drawn())
      expect(queue).toContain(`#31 ${queued}`)
      expect(queue).toContain('waiting on #12')
      expect(queue).not.toContain('…')
      await ui.unmount()
    })
  }
})
