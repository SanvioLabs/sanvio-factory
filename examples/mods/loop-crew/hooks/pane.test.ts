import { describe as group, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import { FIGURE_MARK } from './logic'

const ROOT = '/h/starter'
const HARNESS = `${ROOT}/.loop`
const ALPHA = `${ROOT}/.loop/projects/alpha`

const job = (number: number, step: string, over: object = {}) => ({ number, title: `Job ${number}`, step, state: 'working', round: 1, ...over })
const statusText = (...issues: object[]) => JSON.stringify({ running: true, queue: [], issues })

const PANE = {
  plugin: 'loop-crew',
  surface: 'terminal',
  component: 'Pane',
  requestId: 'loop-crew',
  props: { title: 'Loop crew', isFocused: true, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

// A pane of this size, on this surface.
const pane = (bodyColumns: number, bodyRows: number, surface = 'terminal') =>
  ({ ...PANE, surface, props: { ...PANE.props, bodyColumns, scroll: { offset: 0, bodyRows } } }) as unknown as typeof PANE

const WIDE = () => pane(64, 40)

// Work the timers left running; they await the engine a few times.
async function drain(): Promise<void> {
  for (let i = 0; i < 200; i++) await Promise.resolve()
}

// The cells back from a Raster's base64, as [code point, foreground, background].
function decode(text: string): [number, number, number][] {
  const bytes = Uint8Array.from(atob(text), c => c.charCodeAt(0))
  const view = new DataView(bytes.buffer)
  const out: [number, number, number][] = []
  for (let i = 0; i < bytes.length; i += 12) out.push([view.getUint32(i, true), view.getUint32(i + 4, true), view.getUint32(i + 8, true)])
  return out
}

// Where each figure's mark is, as [column, cell row], left to right. It can be in either half of a cell.
function marks(cells: string, columns: number): [number, number][] {
  const found: [number, number][] = []
  decode(cells).forEach(([, fg, bg], i) => {
    if (fg === FIGURE_MARK || bg === FIGURE_MARK) found.push([i % columns, Math.floor(i / columns)])
  })
  return found.sort((a, b) => a[0] - b[0])
}

// A floor's text cells run together, every pixel cell a space.
function textOf(cells: string, columns: number): string {
  const decoded = decode(cells)
  let out = ''
  decoded.forEach(([code], i) => {
    out += code === 0x2580 ? ' ' : String.fromCodePoint(code)
    if ((i + 1) % columns === 0) out += '\n'
  })
  return out
}

type Finds = { find: (query: { key?: string; type?: string }) => Promise<{ props: Record<string, unknown> } | undefined> }
const floorOf = async (ui: Finds): Promise<string> => String((await ui.find({ key: 'floor' }))?.props.cells)
const svgOf = async (ui: Finds): Promise<string> => String((await ui.find({ type: 'Svg' }))?.props.source)

// The engine beneath the mod: a harness whose loop files are `files`, by path, and a pane. The test
// changes `files` between polls, `panes` to stand a pane behind another, and `flip` to refuse a close,
// take the root away or leave the lock's holder gone.
function world(on: On, files: Map<string, string>) {
  const clock = mock.clock(on, { now: 1_800_000_000_000 })
  const ran: string[][] = []
  const reads: string[] = []
  const titles: string[] = []
  const blits: { key: string; cells: string }[] = []
  const invalidated: string[] = []
  const panes: { id: string; isShown: boolean; isPlaced: boolean }[] = []
  const flip = { closeFails: false, rootGone: false, staleLock: false, unplaced: false, closes: 0, blit: 'take' as 'take' | 'deny' | 'none', hold: null as Promise<void> | null }
  const process = (exitCode: number, stderr: string) => ({ value: { exitCode, stdout: '', stderr, isStdoutTruncated: false, isStderrTruncated: false } })
  on('session.root', async () => ({ value: ROOT }))
  on('fs.exists', async (_$, e) => ({ value: (e.path === `${ROOT}/scripts/loop.py` && !flip.rootGone) || files.has(e.path) }))
  on('fs.read', async (_$, e) => {
    reads.push(e.path)
    if (flip.hold && e.path === `${HARNESS}/status.json`) await flip.hold
    const text = files.get(e.path)
    return text === undefined ? { deny: `no ${e.path}` } : { value: text }
  })
  on('fs.list', async (_$, e) => {
    if (e.path !== `${ROOT}/.loop/projects`) return { deny: `no ${e.path}` }
    const names = [...files.keys()].flatMap(p => p.match(/\/\.loop\/projects\/([^/]+)\//)?.[1] ?? [])
    const dirs = [...new Set(names)].map(name => ({ name, kind: 'dir' as const, size: 0 }))
    return { value: [...dirs, { name: 'a-file', kind: 'file' as const, size: 0 }] } as never
  })
  on('process.run', async (_$, e) => {
    ran.push([...e.argv])
    return flip.staleLock ? process(1, `kill: (${e.argv[2]}) - No such process`) : process(0, '')
  })
  on('ui.open', async (_$, e) => {
    titles.push(e.title ?? '')
    if (!panes.some(p => p.isShown)) {
      panes.length = 0
      panes.push({ id: 'loop-crew', isShown: true, isPlaced: true })
    }
    return { value: { isPlaced: !flip.unplaced } }
  })
  on('ui.close', async () => {
    flip.closes++
    if (flip.closeFails) return { deny: 'refused' }
    panes.length = 0
    return { value: undefined }
  })
  on('ui.panes', async () => ({ value: [...panes] }) as never)
  on('ui.invalidate', async (_$, e, next) => {
    invalidated.push(e.event)
    return next(e)
  })
  on('ui.blit', async (_$, e, next) => {
    const args = e as unknown as { key: string; cells: string }
    blits.push({ key: args.key, cells: args.cells })
    if (flip.blit === 'deny') return { deny: 'not mounted' }
    // Left unanswered: nothing sits beneath, so the kit's own "no implementation" rejects it.
    if (flip.blit === 'none') return next(e)
    return { value: {} }
  })
  // Closes the pane, so both timers stop themselves and the next test can start its own.
  const close = async () => {
    panes.length = 0
    await clock.advance(2000)
    await drain()
  }
  return { clock, ran, reads, titles, blits, invalidated, panes, flip, close }
}

type Dollar = { command: { run: (i: object) => Promise<unknown> } }
const say = async ($: unknown, args = ''): Promise<string> => {
  const typed = { command: 'loop-crew', args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } }
  return ((await ($ as Dollar).command.run(typed)) as { text?: string }).text ?? ''
}

const STATUS = `${HARNESS}/status.json`
const twoWorking = () => new Map([
  [STATUS, statusText(job(13, 'VALIDATE', { round: 2 }), job(12, 'BUILD', { round: 0 }))],
  [`${HARNESS}/lock`, '4242'],
])
const working = (...issues: object[]) => new Map([[STATUS, statusText(...issues)], [`${HARNESS}/lock`, '4242']])

group('the floor', () => {
  // Each figure's [column, cell row] of its mark: 2 past its spot, and 4 cell rows down its box.
  const terminals: [string, number, number, number, number, [number, number][]][] = [
    ['a wide terminal', 64, 40, 64, 24, [[24, 16], [46, 16]]],
    ['a compact terminal', 40, 50, 32, 36, [[2, 16], [2, 28]]],
  ]
  for (const [name, columns, bodyRows, floorColumns, floorRows, expected] of terminals) {
    test(`two issues on two steps stand at their stations with their legend lines, on ${name}`, async ($, on) => {
      const { close } = world(on, twoWorking())
      await say($)
      const ui = await $.ui.mount(pane(columns, bodyRows))
      const floor = await ui.find({ key: 'floor' })
      expect(floor?.props.columns).toBe(floorColumns)
      expect(floor?.props.rows).toBe(floorRows)
      const cells = String(floor?.props.cells)
      expect(marks(cells, floorColumns).map(String).sort()).toEqual(expected.map(String).sort())
      const text = textOf(cells, floorColumns)
      for (const word of ['door', 'planning', 'tests', 'workshop', 'review', 'dock', '12', '13']) expect(text).toContain(word)
      const drawn = JSON.stringify(await ui.drawn())
      expect(drawn).toContain('#12 Job 12 · building')
      expect(drawn).toContain('#13 Job 13 · checking, round 2')
      expect(drawn.indexOf('#12 Job 12')).toBeLessThan(drawn.indexOf('#13 Job 13'))
      await ui.unmount()
      await close()
    })
  }
  for (const surface of ['desktop', 'vscode', 'mobile'] as const) {
    test(`two issues on two steps stand at their stations with their legend lines, on ${surface}`, async ($, on) => {
      const { close } = world(on, twoWorking())
      await say($)
      const ui = await $.ui.mount(pane(64, 40, surface))
      const figure = await ui.find({ type: 'Svg' })
      expect(figure?.props.alt).toBe('Issue #12 at workshop, Issue #13 at review')
      expect(figure?.props.width).toBe(256)
      expect(figure?.props.height).toBe(192)
      expect(figure?.props.isInteractive).toBe(true)
      const source = String(figure?.props.source)
      expect(source).toContain('viewBox="0 0 64 48"')
      expect(source).toContain('<g transform="translate(44 32)">')
      expect(source).toContain('<g transform="translate(22 32)">')
      expect(source).toContain('<animate')
      expect(source).not.toContain('Job 12')
      expect(source).not.toContain('<animateTransform')
      const drawn = JSON.stringify(await ui.drawn())
      expect(drawn).toContain('#12 Job 12 · building')
      expect(drawn).toContain('#13 Job 13 · checking, round 2')
      await ui.unmount()
      await close()
    })
  }
  for (const [columns, floorColumns] of [[64, 64], [63, 32], [32, 32]] as const) {
    test(`${columns} columns draws the floor ${floorColumns} wide`, async ($, on) => {
      const { close } = world(on, twoWorking())
      await say($)
      const ui = await $.ui.mount(pane(columns, 60))
      expect((await ui.find({ key: 'floor' }))?.props.columns).toBe(floorColumns)
      await ui.unmount()
      await close()
    })
  }
  test('31 columns draws no floor and paints none, only the legend', async ($, on) => {
    const { clock, blits, close } = world(on, twoWorking())
    await say($)
    const ui = await $.ui.mount(pane(31, 60))
    expect(await ui.find({ key: 'floor' })).toBeUndefined()
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('#12 Job 12')
    expect(drawn).toContain('#13 Job 13')
    await clock.advance(250)
    await drain()
    expect(blits.length).toBe(0)
    await ui.unmount()
    await close()
  })
  test('a default 60 by 30 pane draws the compact floor whole, with one legend line and how many more', async ($, on) => {
    const { close } = world(on, twoWorking())
    await say($)
    const ui = await $.ui.mount(pane(60, 30))
    const floor = await ui.find({ key: 'floor' })
    expect(floor?.props.columns).toBe(32)
    expect(floor?.props.rows).toBe(36)
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('#12 Job 12')
    expect(drawn).not.toContain('#13 Job 13')
    expect(drawn).toContain('and 1 more')
    await ui.unmount()
    await close()
  })
  test('every legend line shows when the height is absent', async ($, on) => {
    const { close } = world(on, twoWorking())
    await say($)
    const { scroll: _scroll, ...props } = PANE.props
    const ui = await $.ui.mount({ ...PANE, props: { ...props, bodyColumns: 64 } } as unknown as typeof PANE)
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('#12 Job 12')
    expect(drawn).toContain('#13 Job 13')
    expect(drawn).not.toContain(' more')
    await ui.unmount()
    await close()
  })
  test('a legend line is cut to the width of the pane', async ($, on) => {
    const issues = [1, 2, 3, 4].map(n => job(n, 'BUILD', { title: 'x'.repeat(100) }))
    const { close } = world(on, working(...issues))
    await say($)
    const ui = await $.ui.mount(pane(40, 20))
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('and 3 more')
    // The whole line is cut to 40, the ellipsis in it.
    expect(drawn).toContain(`#1 ${'x'.repeat(36)}…`)
    expect(drawn).not.toContain('x'.repeat(37))
    await ui.unmount()
    await close()
  })
  test('the desktop shows every line, whatever the height', async ($, on) => {
    const issues = [1, 2, 3, 4, 5].map(n => job(n, 'BUILD'))
    const { close } = world(on, working(...issues))
    await say($)
    const ui = await $.ui.mount(pane(64, 10, 'desktop'))
    expect((await ui.find({ type: 'Svg' }))?.type).toBe('Svg')
    const drawn = JSON.stringify(await ui.drawn())
    for (const n of [1, 2, 3, 4, 5]) expect(drawn).toContain(`#${n} Job ${n}`)
    expect(drawn).not.toContain(' more')
    await ui.unmount()
    await close()
  })
  test('a hidden issue at a full station still has its legend line, on the desktop', async ($, on) => {
    const issues = [1, 2, 3, 4].map(n => job(n, 'BUILD'))
    const { close } = world(on, working(...issues))
    await say($)
    const ui = await $.ui.mount(pane(64, 40, 'desktop'))
    const figure = await ui.find({ type: 'Svg' })
    expect(String(figure?.props.source)).toContain('workshop +1')
    expect(figure?.props.alt).toBe('Issue #1 at workshop, Issue #2 at workshop, Issue #3 at workshop')
    expect(JSON.stringify(await ui.drawn())).toContain('#4 Job 4')
    await ui.unmount()
    await close()
  })
})

group('the walk', () => {
  test('each 125 ms blit moves a walker toward its new spot, between the two at 500 ms and there at 1000 ms', async ($, on) => {
    const files = working(job(12, 'SHAPE'))
    const { clock, blits, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    files.set(STATUS, statusText(job(12, 'TEST')))
    await clock.advance(2000)
    await drain()
    const [from, to] = [24, 46]
    const seen: number[] = []
    for (let i = 0; i < 8; i++) {
      const before = blits.length
      await clock.advance(125)
      await drain()
      expect(blits.length).toBe(before + 1)
      const last = blits[blits.length - 1]!
      expect(last.key).toBe('floor')
      seen.push(marks(last.cells, 64)[0]![0])
    }
    expect(seen[0]!).toBeGreaterThan(from)
    for (let i = 1; i < seen.length; i++) expect(seen[i]!).toBeGreaterThan(seen[i - 1]!)
    expect(seen[3]!).toBeGreaterThan(from)
    expect(seen[3]!).toBeLessThan(to)
    expect(seen[7]!).toBe(to)
    await ui.unmount()
    await close()
  })
  test('a redraw at 500 ms draws the walker where it is at that moment', async ($, on) => {
    const files = working(job(12, 'SHAPE'))
    const { clock, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    files.set(STATUS, statusText(job(12, 'TEST')))
    await clock.advance(2000)
    await drain()
    await clock.advance(500)
    await drain()
    await ui.redraw()
    // Halfway from column 22 to 44, and the mark 2 in from there.
    expect(marks(await floorOf(ui as unknown as Finds), 64)).toEqual([[35, 4]])
    await ui.unmount()
    await close()
  })
  test('the walk is painted, and asks for no redraw of its own', async ($, on) => {
    const files = working(job(12, 'SHAPE'))
    const { clock, invalidated, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    files.set(STATUS, statusText(job(12, 'TEST')))
    await clock.advance(2000)
    await drain()
    const after = invalidated.length
    await clock.advance(1000)
    await drain()
    expect(invalidated.length).toBe(after)
    await ui.unmount()
    await close()
  })
  test('with two standing and nobody walking, each blit differs from the one two ticks before', async ($, on) => {
    const { clock, blits, close } = world(on, working(job(12, 'SHAPE'), job(13, 'BUILD')))
    await say($)
    const ui = await $.ui.mount(WIDE())
    const before = JSON.stringify(await ui.drawn())
    for (let i = 1; i <= 8; i++) {
      await clock.advance(125)
      await drain()
      expect(blits.length).toBe(i)
      expect(blits[i - 1]!.key).toBe('floor')
      if (i > 2) expect(blits[i - 1]!.cells).not.toBe(blits[i - 3]!.cells)
    }
    // Painted, never redrawn.
    expect(JSON.stringify(await ui.drawn())).toBe(before)
    await ui.unmount()
    await close()
  })
  test('opening the pane and switching it walk nobody, even when the issues moved', async ($, on) => {
    const files = twoWorking()
    files.set(`${ALPHA}/status.json`, statusText(job(30, 'BUILD')))
    files.set(`${ALPHA}/lock`, '4242')
    const { close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(pane(64, 40, 'desktop'))
    expect(await svgOf(ui as unknown as Finds)).not.toContain('<animateTransform')
    await say($, 'alpha')
    await ui.redraw()
    expect((await ui.find({ type: 'Svg' }))?.props.alt).toBe('Issue #30 at workshop')
    expect(await svgOf(ui as unknown as Finds)).not.toContain('<animateTransform')
    await say($)
    await ui.redraw()
    expect(await svgOf(ui as unknown as Finds)).not.toContain('<animateTransform')
    // Closed and opened again on what has since moved.
    await say($)
    files.set(STATUS, statusText(job(12, 'SCALE'), job(13, 'SHAPE')))
    await say($)
    await ui.redraw()
    expect((await ui.find({ type: 'Svg' }))?.props.alt).toBe('Issue #12 at dock, Issue #13 at planning')
    expect(await svgOf(ui as unknown as Finds)).not.toContain('<animateTransform')
    await ui.unmount()
    await close()
  })
  test('a new issue walks in from the door', async ($, on) => {
    const files = working(job(12, 'SHAPE'))
    const { clock, blits, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    files.set(STATUS, statusText(job(12, 'SHAPE'), job(14, 'TEST')))
    await clock.advance(2000)
    await drain()
    await clock.advance(125)
    await drain()
    // An eighth of the way from column 0 to 44, the other standing at its spot.
    expect(marks(blits[blits.length - 1]!.cells, 64)).toEqual([[8, 4], [24, 4]])
    await clock.advance(875)
    await drain()
    expect(marks(blits[blits.length - 1]!.cells, 64)).toEqual([[24, 4], [46, 4]])
    await ui.unmount()
    await close()
  })
})

group('walking out', () => {
  test('a row gone to pr walks to the door in the legend, asks for one redraw when it ends, and is gone', async ($, on) => {
    const files = working(job(12, 'BUILD'))
    const { clock, blits, invalidated, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    await drain()
    const first = invalidated.length
    files.set(STATUS, statusText(job(12, 'BUILD', { state: 'pr' })))
    await clock.advance(2000)
    await drain()
    // The read that differs asks for its own redraw, and the floor stays.
    expect(invalidated.length).toBe(first + 1)
    expect(await ui.find({ key: 'floor' })).toBeDefined()
    let drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('#12 Job 12 · opening the pull request, round 1')
    expect(drawn).not.toContain('Nothing being built right now.')

    await clock.advance(500)
    await drain()
    // Halfway from the workshop's first spot, (44, 32), to the door's, (0, 8), at (22, 20).
    expect(marks(blits[blits.length - 1]!.cells, 64)).toEqual([[24, 10]])
    expect(invalidated.length).toBe(first + 1)
    await ui.redraw()
    expect(marks(await floorOf(ui as unknown as Finds), 64)).toEqual([[24, 10]])
    expect(JSON.stringify(await ui.drawn())).toContain('opening the pull request')

    await clock.advance(500)
    await drain()
    expect(invalidated.length).toBe(first + 2)
    expect(await ui.find({ key: 'floor' })).toBeUndefined()
    drawn = JSON.stringify(await ui.drawn())
    expect(drawn).not.toContain('#12 Job 12')
    expect(drawn).toContain('Nothing being built right now.')

    // And no more than that one: the later reads are the same, and nothing paints.
    const painted = blits.length
    await clock.advance(4000)
    await drain()
    expect(invalidated.length).toBe(first + 2)
    expect(blits.length).toBe(painted)
    await ui.unmount()
    await close()
  })
  test('another issue still working keeps the floor after the walk out ends', async ($, on) => {
    const files = working(job(12, 'BUILD'), job(13, 'SHAPE'))
    const { clock, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    files.set(STATUS, statusText(job(12, 'BUILD', { state: 'pr' }), job(13, 'SHAPE')))
    await clock.advance(3000)
    await drain()
    expect(await ui.find({ key: 'floor' })).toBeDefined()
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).not.toContain('#12 Job 12')
    expect(drawn).toContain('#13 Job 13')
    await ui.unmount()
    await close()
  })
  test('a row that leaves working any other way is gone at that read, with no walk', async ($, on) => {
    const files = working(job(12, 'BUILD'))
    const { clock, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    files.set(STATUS, statusText(job(12, 'BUILD', { state: 'blocked' })))
    await clock.advance(2000)
    await drain()
    expect(await ui.find({ key: 'floor' })).toBeUndefined()
    expect(JSON.stringify(await ui.drawn())).toContain('Nothing being built right now.')
    await ui.unmount()
    await close()
  })
  test('a walk out shows on the desktop too, with its one redraw', async ($, on) => {
    const files = working(job(12, 'BUILD'))
    const { clock, invalidated, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(pane(64, 40, 'desktop'))
    await drain()
    const first = invalidated.length
    files.set(STATUS, statusText(job(12, 'BUILD', { state: 'pr' })))
    await clock.advance(2000)
    await drain()
    expect(await svgOf(ui as unknown as Finds)).toContain('<animateTransform')
    expect((await ui.find({ type: 'Svg' }))?.props.alt).toBe('Issue #12 at door')
    await clock.advance(1000)
    await drain()
    expect(invalidated.length).toBe(first + 2)
    expect(await ui.find({ type: 'Svg' })).toBeUndefined()
    expect(JSON.stringify(await ui.drawn())).toContain('Nothing being built right now.')
    await ui.unmount()
    await close()
  })
  test('a switch cancels the redraw of a walk out on the loop it left', async ($, on) => {
    const files = working(job(12, 'BUILD'))
    files.set(`${ALPHA}/status.json`, statusText(job(30, 'BUILD')))
    files.set(`${ALPHA}/lock`, '4242')
    const { clock, invalidated, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    files.set(STATUS, statusText(job(12, 'BUILD', { state: 'pr' })))
    await clock.advance(2000)
    await drain()
    await say($, 'alpha')
    await drain()
    const after = invalidated.length
    await clock.advance(1000)
    await drain()
    expect(invalidated.length).toBe(after)
    await ui.unmount()
    await close()
  })
})

group('painting the floor', () => {
  for (const answer of ['deny', 'none'] as const) {
    test(`a blit on floor answered ${answer === 'deny' ? 'with a deny' : 'by nothing'} changes nothing and throws nothing`, async ($, on) => {
      const { clock, blits, flip, close } = world(on, twoWorking())
      flip.blit = answer
      await say($)
      const ui = await $.ui.mount(WIDE())
      const before = JSON.stringify(await ui.drawn())
      await clock.advance(125)
      await drain()
      await clock.advance(125)
      await drain()
      // Still ticking after the failures.
      expect(blits.map(b => b.key)).toEqual(['floor', 'floor'])
      expect(JSON.stringify(await ui.drawn())).toBe(before)
      await ui.unmount()
      await close()
    })
  }
  test('a redraw after a frame draws what the clock says, not the first frame', async ($, on) => {
    const { clock, close } = world(on, twoWorking())
    await say($)
    const ui = await $.ui.mount(WIDE())
    const first = await floorOf(ui as unknown as Finds)
    await clock.advance(250)
    await drain()
    await ui.redraw()
    expect(await floorOf(ui as unknown as Finds)).not.toBe(first)
    await ui.unmount()
    await close()
  })
  test('a surface that animates by itself runs no timer, and a changed step gives one walker', async ($, on) => {
    const files = twoWorking()
    const { clock, blits, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(pane(64, 40, 'desktop'))
    await clock.advance(1000)
    await drain()
    expect(blits.length).toBe(0)
    files.set(STATUS, statusText(job(12, 'BUILD', { round: 0 }), job(13, 'SCALE', { round: 2 })))
    await clock.advance(1000)
    await drain()
    const source = await svgOf(ui as unknown as Finds)
    expect(source.split('<animateTransform').length - 1).toBe(1)
    expect(source).toContain('<g transform="translate(0 32)">')
    expect(blits.length).toBe(0)
    await ui.unmount()
    await close()
  })
  test('no blit on floor once the pane closes', async ($, on) => {
    const { clock, blits, panes, close } = world(on, twoWorking())
    await say($)
    const ui = await $.ui.mount(WIDE())
    panes.length = 0
    await clock.advance(125)
    await drain()
    await clock.advance(1000)
    await drain()
    expect(blits.length).toBe(0)
    await ui.unmount()
    await close()
  })
})

group('the poll', () => {
  test('an unchanged read asks for no redraw, and a changed status file for one', async ($, on) => {
    const files = twoWorking()
    const { clock, invalidated, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    await drain()
    const first = invalidated.length
    await clock.advance(2000)
    await drain()
    expect(invalidated.length).toBe(first)
    files.set(STATUS, statusText(job(12, 'SCALE')))
    await clock.advance(2000)
    await drain()
    expect(invalidated.length).toBe(first + 1)
    expect(JSON.stringify(await ui.drawn())).toContain('opening the pull request')
    await ui.unmount()
    await close()
  })
  test('it reads nothing once the pane closes, and runs nothing but kill -0', async ($, on) => {
    const { clock, ran, reads, panes, close } = world(on, twoWorking())
    await say($)
    await clock.advance(2000)
    await drain()
    panes.length = 0
    await clock.advance(2000)
    await drain()
    const after = reads.length
    await clock.advance(4000)
    await drain()
    expect(reads.length).toBe(after)
    expect(ran.length).toBeGreaterThan(0)
    for (const argv of ran) expect(argv).toEqual(['kill', '-0', '4242'])
    await close()
  })
  test('a read that a switch overtook is dropped', async ($, on) => {
    const files = twoWorking()
    files.set(`${ALPHA}/status.json`, statusText(job(30, 'BUILD')))
    files.set(`${ALPHA}/lock`, '4242')
    const { clock, flip, close } = world(on, files)
    await say($)
    let release = () => {}
    flip.hold = new Promise<void>(resolve => { release = resolve })
    await clock.advance(2000)
    await drain()
    await say($, 'alpha')
    flip.hold = null
    release()
    await drain()
    const ui = await $.ui.mount(WIDE())
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('#30 Job 30')
    expect(drawn).not.toContain('#12 Job 12')
    await ui.unmount()
    await close()
  })
})

group('what the pane shows, in its order', () => {
  type Mounts = { ui: { mount: (i: typeof PANE) => Promise<Finds & { drawn: () => Promise<unknown>; unmount: () => Promise<void> }> } }
  const shown = async ($: Mounts) => {
    const ui = await $.ui.mount(WIDE())
    const drawn = JSON.stringify(await ui.drawn())
    const floor = await ui.find({ key: 'floor' })
    await ui.unmount()
    return { drawn, floor }
  }
  test('no status file, even with a lock', async ($, on) => {
    const { close } = world(on, new Map([[`${HARNESS}/lock`, '4242']]))
    await say($)
    expect((await shown($ as never)).drawn).toContain('No loop has run here yet.')
    await close()
  })
  test('a status file that cannot be read counts as none', async ($, on) => {
    const { close } = world(on, new Map([[STATUS, '{not json'], [`${HARNESS}/lock`, '4242']]))
    await say($)
    expect((await shown($ as never)).drawn).toContain('No loop has run here yet.')
    await close()
  })
  test('no lock: not running, with no floor, even for rows still at working', async ($, on) => {
    const { close } = world(on, new Map([[STATUS, statusText(job(12, 'BUILD'))]]))
    await say($)
    const { drawn, floor } = await shown($ as never)
    expect(drawn).toContain("The loop isn't running.")
    expect(floor).toBeUndefined()
    await close()
  })
  test("a stale lock: not running, whose holder is gone", async ($, on) => {
    const { flip, close } = world(on, twoWorking())
    flip.staleLock = true
    await say($)
    const { drawn, floor } = await shown($ as never)
    expect(drawn).toContain("The loop isn't running.")
    expect(floor).toBeUndefined()
    await close()
  })
  test('a lock whose pid cannot be read counts as alive', async ($, on) => {
    const { flip, close } = world(on, new Map([[STATUS, statusText(job(12, 'BUILD'))], [`${HARNESS}/lock`, 'nonsense']]))
    flip.staleLock = true
    await say($)
    expect((await shown($ as never)).drawn).toContain('#12 Job 12')
    await close()
  })
  test('a live lock with nothing working', async ($, on) => {
    const { close } = world(on, new Map([[STATUS, statusText(job(12, 'BUILD', { state: 'pr' }))], [`${HARNESS}/lock`, '4242']]))
    await say($)
    const { drawn, floor } = await shown($ as never)
    expect(drawn).toContain('Nothing being built right now.')
    expect(floor).toBeUndefined()
    await close()
  })
  test('a live lock with a job, the floor with one figure', async ($, on) => {
    const { close } = world(on, working(job(12, 'BUILD')))
    await say($)
    const { drawn, floor } = await shown($ as never)
    expect(drawn).toContain('#12 Job 12')
    expect(marks(String(floor?.props.cells), 64).length).toBe(1)
    await close()
  })
})

group('the command', () => {
  const both = () => {
    const files = twoWorking()
    files.set(`${ALPHA}/status.json`, statusText(job(30, 'SHAPE', { round: 0 })))
    files.set(`${ALPHA}/lock`, '4242')
    return files
  }
  test('no argument shows the harness, titled Loop crew', async ($, on) => {
    const { titles, close } = world(on, both())
    expect(await say($)).toBe('Loop crew opened.')
    expect(titles).toEqual(['Loop crew'])
    await close()
  })
  test("a project's name shows that project's loop, titled with its name", async ($, on) => {
    const { titles, close } = world(on, both())
    expect(await say($, 'alpha')).toBe('Loop crew opened.')
    expect(titles).toEqual(['Loop crew: alpha'])
    const ui = await $.ui.mount(WIDE())
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('#30 Job 30')
    expect(drawn).toContain('planning')
    expect(drawn).not.toContain('#12 Job 12')
    await ui.unmount()
    await close()
  })
  for (const name of ['nope', '../x', 'a-file', 'alpha/']) {
    test(`${name} answers no loop and opens or changes nothing`, async ($, on) => {
      const { titles, panes, flip, close } = world(on, both())
      expect(await say($, name)).toBe(`No loop for ${name} under .loop/projects/.`)
      expect(titles).toEqual([])
      expect(panes.length).toBe(0)
      expect(flip.closes).toBe(0)
      await close()
    })
  }
  test('an unknown name leaves an open pane on its loop', async ($, on) => {
    const { titles, panes, close } = world(on, both())
    await say($, 'alpha')
    await say($, '../x')
    expect(titles).toEqual(['Loop crew: alpha'])
    expect(panes.length).toBe(1)
    const ui = await $.ui.mount(WIDE())
    expect(JSON.stringify(await ui.drawn())).toContain('#30 Job 30')
    await ui.unmount()
    await close()
  })
  test('no root answers so and opens nothing', async ($, on) => {
    const { titles, flip, close } = world(on, both())
    flip.rootGone = true
    expect(await say($)).toBe(`No scripts/loop.py at or above ${ROOT}, so there is no loop to show.`)
    expect(titles).toEqual([])
    await close()
  })
  test('a second /loop-crew on the same loop closes the pane', async ($, on) => {
    const { panes, close } = world(on, both())
    await say($)
    expect(await say($)).toBe('Loop crew closed.')
    expect(panes.length).toBe(0)
    await say($, 'alpha')
    expect(await say($, 'alpha')).toBe('Loop crew closed.')
    expect(panes.length).toBe(0)
    await close()
  })
  test('a close that fails says how else to close it', async ($, on) => {
    const { flip, close } = world(on, both())
    await say($)
    flip.closeFails = true
    expect(await say($)).toBe("The loop crew pane couldn't close. The × in its corner closes it.")
    await close()
  })
  test('naming another loop switches the open pane and its title, without closing it', async ($, on) => {
    const { titles, flip, panes, close } = world(on, both())
    await say($)
    await say($, 'alpha')
    expect(titles).toEqual(['Loop crew', 'Loop crew: alpha'])
    expect(flip.closes).toBe(0)
    expect(panes.length).toBe(1)
    const ui = await $.ui.mount(WIDE())
    expect(JSON.stringify(await ui.drawn())).toContain('#30 Job 30')
    await ui.unmount()
    // And no argument, while a project is shown, goes back to the harness.
    await say($)
    expect(titles).toEqual(['Loop crew', 'Loop crew: alpha', 'Loop crew'])
    expect(flip.closes).toBe(0)
    await close()
  })
  test('a pane open but not shown opens on the loop named', async ($, on) => {
    const { titles, panes, flip, close } = world(on, both())
    await say($, 'alpha')
    panes[0]!.isShown = false
    expect(await say($, 'alpha')).toBe('Loop crew opened.')
    expect(titles).toEqual(['Loop crew: alpha', 'Loop crew: alpha'])
    expect(flip.closes).toBe(0)
    await close()
  })
  test('a surface with no room to place it says to widen the terminal', async ($, on) => {
    const { flip, close } = world(on, both())
    flip.unplaced = true
    expect(await say($)).toBe('Loop crew opened. Widen the terminal to see it.')
    await close()
  })
})
