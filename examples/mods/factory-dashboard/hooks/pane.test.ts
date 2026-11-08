import { describe as group, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import { sinceFor } from './logic'
import type { Doc, Seen } from '../types'

// Made-up numbers and titles, in the shape the script prints.
const DOC: Doc = {
  generated: '2026-10-27T11:00:00-07:00',
  since: '2026-10-13',
  waiting: { pull_requests: [], blocked: [{ number: 38, title: 'Link the loop section', note: 'still failing' }] },
  loop_spend: { value: null, why: 'no loop records' },
}

const SEEN = (over: Partial<Seen> = {}): Seen => ({
  root: '/h/starter', doc: DOC, readAt: Date.now(), isReading: false, failedAt: null, failure: null, ...over,
})

const PANE = {
  plugin: 'factory-dashboard',
  surface: 'terminal',
  component: 'Pane',
  requestId: 'dashboard',
  props: { title: 'Factory', isFocused: true, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

// Stands in for the pane's last read, and for writes to it, so a press can be watched.
function seed(on: On, seen: Seen | null): { now: () => Seen | null } {
  let value = seen
  let version = 1
  on('state.get', async (_$, e, next) =>
    e.plugin === 'factory-dashboard' && e.key === 'seen' ? { value: { value, version } } : next(e))
  on('state.set', async (_$, e, next) => {
    if (e.plugin !== 'factory-dashboard' || e.key !== 'seen') return next(e)
    value = e.value as Seen
    version += 1
    return { value: { isSet: true as const, version } }
  })
  return { now: () => value }
}

async function drain(): Promise<void> {
  for (let i = 0; i < 40; i++) await Promise.resolve()
}

// A session whose root is the harness root unless given another, with the pane open or not, counting
// the script's runs and how often the pane asks which panes are open.
function session(on: On, open: { now: boolean }, root = '/h/starter'): { runs: () => number; asks: () => number } {
  let runs = 0
  let asks = 0
  on('session.start', async (_$, e) => ({ cwd: e.cwd }))
  on('session.root', async () => ({ value: root }))
  on('command.register', async (_$, e) => ({ value: { command: e.name } }))
  on('fs.exists', async (_$, e) => ({ value: e.path === '/h/starter/scripts/dashboard_data.py' }))
  on('ui.panes', async () => {
    asks += 1
    return { value: open.now ? [{ id: 'dashboard', title: 'Factory', isShown: true, isPlaced: true } as never] : [] }
  })
  on('process.run', async () => {
    runs += 1
    return { value: { exitCode: 0, stdout: JSON.stringify(DOC), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  return { runs: () => runs, asks: () => asks }
}

const START = { cwd: '/h/starter', surface: null, isInteractive: true } as const
const PERIOD = 300_000

group('the timer', () => {
  test('a reload with the pane open starts it, and each period reads once', async ($, on) => {
    const clock = mock.clock(on, { now: 1_800_000_000_000 })
    const s = session(on, { now: true })
    await $.session.start(START)
    await clock.settle()
    expect(s.runs()).toBe(0)
    await clock.advance(PERIOD)
    expect(s.runs()).toBe(1)
    await clock.advance(PERIOD)
    expect(s.runs()).toBe(2)
  })
  test('once the pane is closed, the next period reads nothing and later ones stop asking', async ($, on) => {
    const clock = mock.clock(on, { now: 1_800_000_000_000 })
    const open = { now: true }
    const s = session(on, open)
    await $.session.start(START)
    await clock.advance(PERIOD)
    open.now = false
    await clock.advance(PERIOD)
    const asked = s.asks()
    await clock.advance(PERIOD)
    await clock.advance(PERIOD)
    expect(s.runs()).toBe(1)
    expect(s.asks()).toBe(asked)
  })
  test('a reload with the pane closed starts no timer', async ($, on) => {
    const clock = mock.clock(on, { now: 1_800_000_000_000 })
    const s = session(on, { now: false })
    await $.session.start(START)
    await clock.settle()
    const asked = s.asks()
    await clock.advance(PERIOD)
    await clock.advance(PERIOD)
    expect(s.runs()).toBe(0)
    expect(s.asks()).toBe(asked)
  })
  test('a reload clears a read saved as running, so Refresh works again', async ($, on) => {
    mock.clock(on, { now: 1_800_000_000_000 })
    session(on, { now: false })
    const state = seed(on, SEEN({ isReading: true }))
    await $.session.start(START)
    await drain()
    expect(state.now()?.isReading).toBe(false)
  })
})

group('the pane', () => {
  test('draws each section, what is waiting first, and a missing one with its why', async ($, on) => {
    seed(on, SEEN())
    const ui = await $.ui.mount(PANE)
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('starter')
    expect(drawn.indexOf('Waiting on you')).toBeLessThan(drawn.indexOf('Loop spend'))
    expect(drawn).toContain('Blocked issue')
    expect(drawn).toContain('#38: still failing')
    expect(drawn).toContain('no loop records')
    await ui.unmount()
  })
  test('a line separates each section from the one before, and none sits above the first', async ($, on) => {
    seed(on, SEEN())
    const ui = await $.ui.mount(PANE)
    expect(await ui.find({ key: 'rule-waiting' })).toBeUndefined()
    expect(JSON.stringify(await ui.find({ key: 'rule-spend' }))).toContain('───')
    expect(await ui.find({ key: 'rule-activity' })).toBeDefined()
    await ui.unmount()
  })
  test("a section's chart and its caption come first, above its tables", async ($, on) => {
    const doc: Doc = { ...DOC, loop_spend: { today: {}, last_7_days: {}, since: {}, cost_per_pr: null,
      by_day: [{ day: '2026-10-26', tokens: 1, cost_usd: 1 }, { day: '2026-10-27', tokens: 2, cost_usd: 2 }] } }
    seed(on, SEEN({ doc }))
    const ui = await $.ui.mount(PANE)
    const spend = JSON.stringify(await ui.find({ key: 'spend' }))
    expect(spend.indexOf('Daily, Oct 26 to Oct 27')).toBeGreaterThan(-1)
    expect(spend.indexOf('Daily, Oct 26 to Oct 27')).toBeLessThan(spend.indexOf('"spend-chart"'))
    expect(spend.indexOf('"spend-chart"')).toBeLessThan(spend.indexOf('spend-periods'))
    await ui.unmount()
  })
  test('before the first read ends, it says the read can take a minute', async ($, on) => {
    seed(on, SEEN({ doc: null, readAt: null, isReading: true }))
    const ui = await $.ui.mount(PANE)
    expect(JSON.stringify(await ui.drawn())).toContain('can take a minute')
    await ui.unmount()
  })
  test('after a failed refresh it keeps the last numbers and says why it failed', async ($, on) => {
    seed(on, SEEN({ failedAt: Date.now(), failure: 'the script exited 1' }))
    const ui = await $.ui.mount(PANE)
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('Refresh failed')
    expect(drawn).toContain('Last refresh: the script exited 1')
    expect(drawn).toContain('Waiting on you')
    await ui.unmount()
  })
})

group('the spend tables', () => {
  const spent: Doc = { ...DOC, loop_spend: { today: { tokens: 12_000_000, cost_usd: 16 }, last_7_days: {}, since: {},
    cost_per_pr: 2.5, by_issue: { 'issue-38': { tokens: 4_000_000, cost_usd: 5 } } } }
  test('each row is a name, then numbers in columns the width of their widest cell, right-aligned', async ($, on) => {
    seed(on, SEEN({ doc: spent }))
    const ui = await $.ui.mount(PANE)
    const row = await ui.find({ key: 'spend-periods-0' })
    expect(row?.props.flexDirection).toBe('row')
    expect(JSON.stringify(row)).toContain('Today')
    expect(JSON.stringify(row)).toContain('$16.00')
    const cost = await ui.find({ key: 'spend-periods-0-0' })
    expect(cost?.props.justifyContent).toBe('flex-end')
    // The widest cost is ~$2.50 or $16.00, six characters, and a space before it.
    expect(cost?.props.width).toBe(7)
    expect(JSON.stringify(await ui.find({ key: 'spend-issues' }))).toContain('#38')
    await ui.unmount()
  })
})

group('the tables in a narrow pane', () => {
  type Node = { props?: Record<string, unknown>; children?: (Node | string)[] }
  const text = (n: Node | undefined): Node => n!.children![0] as Node
  const stale: Doc = { ...DOC, evals: { reviewer: { stable: 3, flaky: 0, failing: 0, saved: '2026-10-20', stale: true, why: 'agent changed' } } }
  test("put each row's figures on a line under its name, in the row's colour", async ($, on) => {
    seed(on, SEEN({ doc: stale }))
    // The Evals figures take 34 of 40 columns, leaving 6 for the name.
    const ui = await $.ui.mount({ ...PANE, props: { ...PANE.props, bodyColumns: 40 } })
    const name = await ui.find({ key: 'evals-reviewers-0-name' }) as unknown as Node
    expect(name.props?.flexDirection).toBe('row')
    expect(JSON.stringify(name)).toContain('reviewer')
    let figures = 0
    for (let i = 0; i < 5; i++) figures += Number((await ui.find({ key: `evals-reviewers-0-${i}` }))?.props.width)
    expect(figures).toBeLessThanOrEqual(40)
    expect(await ui.find({ key: 'evals-reviewers-head-name' })).toBeDefined()
    const figure = await ui.find({ key: 'evals-reviewers-0-0' }) as unknown as Node
    expect(text(name).props?.color).toBe('yellow')
    for (const prop of ['color', 'dimColor', 'bold']) expect(text(figure).props?.[prop]).toBe(text(name).props?.[prop])
    await ui.unmount()
  })
})

group('the daily charts', () => {
  const daily: Doc = { ...DOC, loop_spend: { today: {}, last_7_days: {}, since: {}, cost_per_pr: null,
    by_day: [{ day: '2026-10-26', tokens: 1, cost_usd: 1 }, { day: '2026-10-27', tokens: 2, cost_usd: 2 }] } }
  test('the terminal draws them in coloured blocks the width of the pane', async ($, on) => {
    seed(on, SEEN({ doc: daily }))
    const ui = await $.ui.mount(PANE)
    const chart = await ui.find({ key: 'spend-chart' })
    expect(chart?.type).toBe('Raster')
    expect(chart?.props.columns).toBe(60)
    expect(JSON.stringify(await ui.drawn())).toContain('Oct 26')
    await ui.unmount()
  })
  test("writes each bar's day, cost and tokens under it when they fit", async ($, on) => {
    seed(on, SEEN({ doc: daily }))
    const ui = await $.ui.mount(PANE)
    expect(JSON.stringify(await ui.find({ key: 'spend-chart-under-0' }))).toContain('Oct 26')
    expect(JSON.stringify(await ui.find({ key: 'spend-chart-under-1' }))).toContain('$2.00')
    expect(await ui.find({ key: 'spend-chart-days' })).toBeUndefined()
    await ui.unmount()
  })
  test("labels every 7th bar with its day, counting back from today's, when each bar's labels don't fit", async ($, on) => {
    const many: Doc = { ...daily, loop_spend: { ...(daily.loop_spend as object),
      by_day: Array.from({ length: 10 }, (_, i) => ({ day: `2026-10-${10 + i}`, tokens: 1, cost_usd: i + 1 })) } }
    seed(on, SEEN({ doc: many }))
    const ui = await $.ui.mount({ ...PANE, props: { ...PANE.props, bodyColumns: 30 } })
    expect(await ui.find({ key: 'spend-chart-under-0' })).toBeUndefined()
    const shown = JSON.stringify(await ui.find({ key: 'spend-chart-ticks' }))
    expect(shown).toContain('Oct 19')
    expect(shown).toContain('Oct 12')
    expect(shown).not.toContain('Oct 15')
    await ui.unmount()
  })
  test('with more days than columns, the labelled days are among the ones the bars show', async ($, on) => {
    const at = (i: number) => new Date(Date.UTC(2026, 8, 1 + i)).toISOString().slice(0, 10)
    const many: Doc = { ...daily, loop_spend: { ...(daily.loop_spend as object),
      by_day: Array.from({ length: 40 }, (_, i) => ({ day: at(i), tokens: 1, cost_usd: 1 })) } }
    seed(on, SEEN({ doc: many }))
    const ui = await $.ui.mount({ ...PANE, props: { ...PANE.props, bodyColumns: 30 } })
    // 40 days in 30 columns: the oldest 10 drop off, so the bars run Sep 11 to Oct 10.
    const shown = JSON.stringify(await ui.find({ key: 'spend-chart-ticks' }))
    expect(shown).toContain('Oct 10')
    expect(shown).not.toContain('Sep 5')
    await ui.unmount()
  })
  test('Claude Desktop draws them as an Svg that says each day on hover', async ($, on) => {
    seed(on, SEEN({ doc: daily }))
    const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
    // An Svg's key isn't carried into the drawing, so it's found by type.
    const chart = await ui.find({ type: 'Svg' })
    expect(chart?.type).toBe('Svg')
    expect(String(chart?.props.source)).toContain('<title>2026-10-27 $2.00</title>')
    expect(chart?.props.isInteractive).toBe(true)
    await ui.unmount()
  })
})

group('the range buttons', () => {
  test('14 days is the one chosen until another is picked', async ($, on) => {
    seed(on, SEEN())
    const ui = await $.ui.mount(PANE)
    expect((await ui.find({ key: 'range-14' }))?.props.variant).toBe('primary')
    expect((await ui.find({ key: 'range-30' }))?.props.variant).toBeUndefined()
    await ui.unmount()
  })
  test('picking 30 days reads the days from 29 days ago to today, and keeps the choice', async ($, on) => {
    const ran: string[][] = []
    on('process.run', async (_$, e) => {
      ran.push([...e.argv])
      return { value: { exitCode: 0, stdout: JSON.stringify(DOC), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    })
    seed(on, SEEN())
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'range-30' })
    await drain()
    expect(ran).toEqual([['python3', 'scripts/dashboard_data.py', '--json', '--since', sinceFor(30, Date.now())]])
    expect((await ui.find({ key: 'range-30' }))?.props.variant).toBe('primary')
    await ui.unmount()
  })
})

group('the Refresh button', () => {
  test('runs the dashboard script in the root and draws what it printed', async ($, on) => {
    const ran: { argv: string[]; cwd?: string }[] = []
    const fresh = { ...DOC, waiting: { pull_requests: [], blocked: [] } }
    on('process.run', async (_$, e) => {
      ran.push({ argv: [...e.argv], cwd: e.init?.cwd })
      return { value: { exitCode: 0, stdout: JSON.stringify(fresh), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    })
    const state = seed(on, SEEN())
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'refresh' })
    await drain()
    expect(ran).toEqual([{ argv: ['python3', 'scripts/dashboard_data.py', '--json', '--since', sinceFor(14, Date.now())], cwd: '/h/starter' }])
    expect(state.now()?.doc).toEqual(fresh)
    expect(state.now()?.isReading).toBe(false)
    await ui.unmount()
  })
  test('a failed run keeps the last document and records the failure', async ($, on) => {
    on('process.run', async () => ({ value: { exitCode: 1, stdout: '', stderr: 'boom', isStdoutTruncated: false, isStderrTruncated: false } }))
    const state = seed(on, SEEN())
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'refresh' })
    await drain()
    expect(state.now()?.doc).toEqual(DOC)
    expect(state.now()?.failure).toBe('the script exited 1')
    expect(typeof state.now()?.failedAt).toBe('number')
    await ui.unmount()
  })
  test('does nothing while a read is under way', async ($, on) => {
    let runs = 0
    on('process.run', async () => {
      runs += 1
      return { value: { exitCode: 0, stdout: JSON.stringify(DOC), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    })
    seed(on, SEEN({ isReading: true }))
    const ui = await $.ui.mount(PANE)
    await ui.press({ key: 'refresh' })
    await drain()
    expect(runs).toBe(0)
    await ui.unmount()
  })
})

group('/factory-dashboard', () => {
  // A /clear starts a new session with no session.start, so a folder saved there is gone or the last session's.
  test('after a /clear, with no session.start, finds the harness from the session root', async ($, on) => {
    mock.clock(on, { now: 1_800_000_000_000 })
    session(on, { now: false })
    on('ui.open', async () => ({ value: { isPlaced: true } }))
    const typed = { command: 'factory-dashboard', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } } as const
    expect(((await $.command.run(typed)) as { text?: string }).text).toBe('Dashboard opened.')
  })
  test('outside any harness, names the folder it looked from', async ($, on) => {
    mock.clock(on, { now: 1_800_000_000_000 })
    session(on, { now: false }, '/h/elsewhere')
    await $.session.start({ ...START, cwd: '/h/elsewhere' })
    const typed = { command: 'factory-dashboard', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } } as const
    expect(((await $.command.run(typed)) as { text?: string }).text)
      .toBe('No scripts/dashboard_data.py at or above /h/elsewhere, so there are no numbers to show.')
  })
})
