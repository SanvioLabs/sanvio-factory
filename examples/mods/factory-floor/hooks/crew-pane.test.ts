import { describe as group, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

// loop-crew's hooks/pane.test.ts, run against factory-floor's Crew view. What changed: the plugin and
// pane, the import paths, and opening, which is /factory-floor and the Crew button (say, below). The
// tests of the /loop-crew command are left out, as factory-floor has none. The tests that differ for
// the Crew's place in factory-floor's pane say so where they stand.
import { ACCENT, DARK, OUT_MS, STATIONS, stationX, walkMs } from './crew-logic'

const ROOT = '/h/starter'
const HARNESS = `${ROOT}/.loop`
const ALPHA = `${ROOT}/.loop/projects/alpha`

const job = (number: number, step: string, over: object = {}) => ({ number, title: `Job ${number}`, step, state: 'working', round: 1, ...over })
const statusText = (...issues: object[]) => JSON.stringify({ running: true, queue: [], issues })

const PANE = {
  plugin: 'factory-floor',
  surface: 'terminal',
  component: 'Pane',
  requestId: 'factory-floor',
  props: { title: 'Loop crew', isFocused: true, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

// A pane of this size, on this surface.
const pane = (bodyColumns: number, bodyRows: number, surface = 'terminal') =>
  ({ ...PANE, surface, props: { ...PANE.props, bodyColumns, scroll: { offset: 0, bodyRows } } }) as unknown as typeof PANE

const WIDE = () => pane(72, 40)

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

// The columns of a lane's top pixel row in the head colour: where its figure is. Nothing else uses it.
function heads(cells: string, columns: number): number[] {
  return decode(cells).slice(0, columns).flatMap(([code, fg], x) => (code === 0x2580 && fg === DARK.head ? [x] : []))
}

// Where a standing figure's head is: its station's middle, rounded.
const home = (index: number, columns: number): number => Math.round(stationX(index, columns))
const at = (station: string): number => STATIONS.indexOf(station as never)

type Found = { props: Record<string, unknown> }
type Finds = { find: (query: { key?: string; type?: string }) => Promise<Found | undefined>; findAll: (query: { type?: string }) => Promise<Found[]> }
const cellsOf = async (ui: unknown, key: string): Promise<string> => String((await (ui as Finds).find({ key }))?.props.cells)
// Every Svg drawn, the header first, then a lane each.
const svgs = async (ui: unknown): Promise<Found[]> => (ui as Finds).findAll({ type: 'Svg' })
const laneSvgs = async (ui: unknown): Promise<Found[]> => (await svgs(ui)).filter(s => String(s.props.alt).startsWith('Issue'))
const lastBlit = (blits: { key: string; cells: string }[], key: string): string | undefined => blits.filter(b => b.key === key).pop()?.cells

// The engine beneath the mod: a factory whose loop files are `files`, by path, and a pane. The test
// changes `files` between polls, `panes` to stand a pane behind another, and `flip` to refuse a close,
// take the root away, leave the lock's holder gone or fail the listing of .loop/projects/. `focus`
// gives the session's id, which the test can change and null refuses, the default, and what fs.stat
// finds directly under projects/. fs.write, the one change to files the engine offers, is recorded and
// never answered with a write.
type Kinds = Record<string, 'dir' | 'file' | 'link'>
type Focus = { session?: { id: string | null }; projects?: Kinds }
function world(on: On, files: Map<string, string>, focus: Focus = {}) {
  const clock = mock.clock(on, { now: 1_800_000_000_000 })
  const ran: string[][] = []
  const reads: string[] = []
  const writes: { path: string; text: string }[] = []
  const session = focus.session ?? { id: null }
  const titles: string[] = []
  const sizes: [number | undefined, number | undefined][] = []
  const blits: { key: string; cells: string }[] = []
  const invalidated: string[] = []
  const panes: { id: string; isShown: boolean; isPlaced: boolean }[] = []
  panesNow = panes
  const flip = { closeFails: false, rootGone: false, staleLock: false, unplaced: false, listFails: false, closes: 0, paneReads: 0, blit: 'take' as 'take' | 'deny' | 'none', hold: null as Promise<void> | null }
  const process = (exitCode: number, stderr: string) => ({ value: { exitCode, stdout: '', stderr, isStdoutTruncated: false, isStderrTruncated: false } })
  on('session.root', async () => ({ value: ROOT }))
  on('session.id', async () => (session.id === null ? { deny: 'no session id' } : { value: session.id }))
  on('fs.stat', async (_$, e) => {
    const name = e.path.startsWith(`${ROOT}/projects/`) ? e.path.slice(`${ROOT}/projects/`.length) : ''
    const kind = (focus.projects ?? {})[name]
    if (kind === 'dir') return { value: { kind: 'dir', size: 0, mtimeMs: 0, isLink: false } }
    if (kind === 'file') return { value: { kind: 'file', size: 1, mtimeMs: 0, isLink: false } }
    if (kind === 'link') return { value: { kind: 'dir', size: 0, mtimeMs: 0, isLink: true } }
    return { deny: `no ${e.path}` }
  })
  on('fs.write', async (_$, e) => {
    writes.push({ path: e.path, text: e.text })
    return { deny: 'read-only' }
  })
  on('fs.exists', async (_$, e) => ({ value: (e.path === `${ROOT}/scripts/loop.py` && !flip.rootGone) || files.has(e.path) }))
  on('fs.read', async (_$, e) => {
    reads.push(e.path)
    if (flip.hold && e.path === `${HARNESS}/status.json`) await flip.hold
    const text = files.get(e.path)
    return text === undefined ? { deny: `no ${e.path}` } : { value: text }
  })
  on('fs.list', async (_$, e) => {
    if (flip.listFails || e.path !== `${ROOT}/.loop/projects`) return { deny: `no ${e.path}` }
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
    sizes.push([(e as { rows?: number }).rows, (e as { columns?: number }).columns])
    if (!panes.some(p => p.isShown)) {
      panes.length = 0
      panes.push({ id: 'factory-floor', isShown: true, isPlaced: true })
    }
    return { value: { isPlaced: !flip.unplaced } }
  })
  on('ui.close', async () => {
    flip.closes++
    if (flip.closeFails) return { deny: 'refused' }
    panes.length = 0
    return { value: undefined }
  })
  on('ui.panes', async () => {
    flip.paneReads++
    return { value: [...panes] } as never
  })
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
  return { clock, ran, reads, writes, session, titles, sizes, blits, invalidated, panes, flip, close }
}

// The pane as the current test's world has it, for say to tell whether /factory-floor would open it.
let panesNow: { id: string; isShown: boolean }[] = []

type Pressed = Finds & {
  press: (target: { key: string }) => Promise<unknown>
  select: (target: { key: string; value: string }) => Promise<unknown>
  unmount: () => Promise<void>
}
type Dollar = { command: { run: (i: object) => Promise<unknown> }; ui: { mount: (i: typeof PANE) => Promise<Pressed> } }
const typed = { command: 'factory-floor', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } }

// Open the Crew view on a loop, '' for the factory, as a person does: /factory-floor when the pane isn't
// up, then on the pane, `at`, a pick of the loop in its picker and a press of Crew. With no name, the
// List keeps the loop it opened on, the focus's as /loop-crew's was, and the Crew goes back to the
// factory, as /loop-crew did. A press waits for everything it starts, so the pane `at` is the one the
// test mounts next: its drawing reads usage.json and starts the timers of its surface. Crew on the
// Crew view does nothing. A test that holds the pane mounted passes it as `mounted`: the kit refuses a
// second mount of one pane on one surface, where loop-crew's say ran a command and mounted nothing.
const say = async ($: unknown, name?: string, at: typeof PANE = WIDE(), mounted?: Pressed): Promise<void> => {
  const engine = $ as Dollar
  if (!panesNow.some(p => p.isShown)) await engine.command.run(typed)
  const ui = mounted ?? await engine.ui.mount(at)
  const isList = (await ui.find({ key: 'tab-queue' })) !== undefined
  const target = isList ? name : (name ?? '')
  const picker = await ui.find({ key: 'loop-pick' })
  if (picker && target !== undefined && picker.props.value !== target) await ui.select({ key: 'loop-pick', value: target })
  await ui.press({ key: 'mode-crew' })
  if (!mounted) await ui.unmount()
}

// /factory-floor on an open pane: it closes.
const shut = async ($: unknown): Promise<void> => {
  await ($ as Dollar).command.run(typed)
}

const STATUS = `${HARNESS}/status.json`
const twoWorking = () => new Map([
  [STATUS, statusText(job(13, 'VALIDATE', { round: 2 }), job(12, 'BUILD', { round: 0 }))],
  [`${HARNESS}/lock`, '4242'],
])
const working = (...issues: object[]) => new Map([[STATUS, statusText(...issues)], [`${HARNESS}/lock`, '4242']])

group('the board', () => {
  test('two issues on two steps each get a lane, under a header naming the stations, on a terminal', async ($, on) => {
    const { close } = world(on, twoWorking())
    await say($)
    const ui = await $.ui.mount(WIDE())
    const head = await (ui as unknown as Finds).find({ key: 'head' })
    expect([head?.props.columns, head?.props.rows]).toEqual([72, 1])
    const label = decode(String(head?.props.cells)).map(([code]) => String.fromCodePoint(code)).join('')
    for (const station of STATIONS) expect(label).toContain(station)
    for (const [number, station] of [[12, 'build'], [13, 'validate']] as const) {
      const lane = await (ui as unknown as Finds).find({ key: `lane-${number}` })
      expect([lane?.props.columns, lane?.props.rows]).toEqual([72, 5])
      expect(heads(String(lane?.props.cells), 72)).toEqual([home(at(station), 72)])
    }
    const drawn = JSON.stringify(await ui.drawn())
    for (const words of ['#12', 'Job 12', '· build', '#13', 'Job 13', '· validate, round 2']) expect(drawn).toContain(words)
    expect(drawn.indexOf('lane-12')).toBeLessThan(drawn.indexOf('lane-13'))
    await ui.unmount()
    await close()
  })
  for (const surface of ['desktop', 'vscode', 'mobile'] as const) {
    test(`two issues on two steps each get a lane Svg under a header Svg, on ${surface}`, async ($, on) => {
      const { close } = world(on, twoWorking())
      await say($, '', pane(72, 40, surface))
      const ui = await $.ui.mount(pane(72, 40, surface))
      const all = await svgs(ui)
      expect(all.map(s => s.props.alt)).toEqual(["The loop's steps, left to right", 'Issue #12 at build', 'Issue #13 at validate'])
      for (const lane of all.slice(1)) {
        expect([lane.props.width, lane.props.height, lane.props.isInteractive]).toEqual([undefined, undefined, true])
        const source = String(lane.props.source)
        expect(source).toContain('<animate')
        expect(source).not.toContain('Job 1')
        expect(source).not.toContain('<animateTransform')
      }
      const drawn = JSON.stringify(await ui.drawn())
      for (const words of ['#12', 'Job 12', '· build', '#13', '· validate, round 2']) expect(drawn).toContain(words)
      await ui.unmount()
      await close()
    })
  }
  for (const [columns, board] of [[42, 42], [72, 72], [200, 120]] as const) {
    test(`${columns} columns draws the board ${board} wide`, async ($, on) => {
      const { close } = world(on, twoWorking())
      await say($)
      const ui = await $.ui.mount(pane(columns, 60))
      expect((await (ui as unknown as Finds).find({ key: 'head' }))?.props.columns).toBe(board)
      expect((await (ui as unknown as Finds).find({ key: 'lane-12' }))?.props.columns).toBe(board)
      await ui.unmount()
      await close()
    })
  }
  // In place of loop-crew's 41-column test: under 42 columns factory-floor draws the List, not
  // loop-crew's words-only lanes, and 42 brings the board back with no press.
  test('in the Crew view 41 columns shows the List and paints nothing, and 42 brings the board back', async ($, on) => {
    const { clock, blits, close } = world(on, twoWorking())
    await say($, '', pane(41, 60))
    const ui = await $.ui.mount(pane(41, 60))
    expect(await (ui as unknown as Finds).find({ key: 'tab-active' })).toBeDefined()
    expect(await (ui as unknown as Finds).find({ key: 'head' })).toBeUndefined()
    expect(await (ui as unknown as Finds).find({ key: 'lane-12' })).toBeUndefined()
    await clock.advance(400)
    await drain()
    expect(blits.length).toBe(0)
    await ui.unmount()
    const wide = await $.ui.mount(pane(42, 60))
    expect(await (wide as unknown as Finds).find({ key: 'head' })).toBeDefined()
    expect(await (wide as unknown as Finds).find({ key: 'lane-12' })).toBeDefined()
    await wide.unmount()
    await close()
  })
  test('a short pane shows the lanes that fit and how many more', async ($, on) => {
    const { close } = world(on, working(job(1, 'BUILD'), job(2, 'TEST'), job(3, 'SHAPE')))
    await say($)
    // The view buttons' row and the header's, then 6 rows a lane: 7 left of 9 is room for 1, and one row
    // kept for the rest.
    const ui = await $.ui.mount(pane(72, 9))
    expect(await (ui as unknown as Finds).find({ key: 'lane-1' })).toBeDefined()
    expect(await (ui as unknown as Finds).find({ key: 'lane-2' })).toBeUndefined()
    expect(JSON.stringify(await ui.drawn())).toContain('and 2 more')
    await ui.unmount()
    await close()
  })
  test('a terminal paints at most 8 lanes, however tall, and says how many more', async ($, on) => {
    const { clock, blits, close } = world(on, working(...Array.from({ length: 10 }, (_, i) => job(i + 1, 'BUILD'))))
    await say($)
    const ui = await $.ui.mount(pane(72, 100))
    for (let n = 1; n <= 8; n++) expect(await (ui as unknown as Finds).find({ key: `lane-${n}` })).toBeDefined()
    for (const n of [9, 10]) expect(await (ui as unknown as Finds).find({ key: `lane-${n}` })).toBeUndefined()
    expect(JSON.stringify(await ui.drawn())).toContain('and 2 more')
    await clock.advance(400)
    await drain()
    expect(new Set(blits.map(b => b.key)).has('lane-9')).toBe(false)
    await ui.unmount()
    await close()
  })
  test('every lane shows when the height is absent', async ($, on) => {
    const { close } = world(on, working(job(1, 'BUILD'), job(2, 'TEST'), job(3, 'SHAPE')))
    await say($)
    const { scroll: _scroll, ...props } = PANE.props
    const ui = await $.ui.mount({ ...PANE, props: { ...props, bodyColumns: 72 } } as unknown as typeof PANE)
    for (const n of [1, 2, 3]) expect(await (ui as unknown as Finds).find({ key: `lane-${n}` })).toBeDefined()
    expect(JSON.stringify(await ui.drawn())).not.toContain(' more')
    await ui.unmount()
    await close()
  })
  test("a lane's title is cut to fit the pane, and where it has got to never is", async ($, on) => {
    // At 42 columns, not loop-crew's 40: under 42 factory-floor draws the List.
    const { close } = world(on, working(job(1, 'BUILD', { title: 'x'.repeat(100) })))
    await say($, '', pane(42, 20))
    const ui = await $.ui.mount(pane(42, 20))
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain(`${'x'.repeat(21)}…`)
    expect(drawn).not.toContain('x'.repeat(22))
    expect(drawn).toContain('· build, round 1')
    await ui.unmount()
    await close()
  })
  test('the desktop shows every lane, whatever the height', async ($, on) => {
    const { close } = world(on, working(...[1, 2, 3, 4, 5].map(n => job(n, 'BUILD'))))
    await say($, '', pane(72, 10, 'desktop'))
    const ui = await $.ui.mount(pane(72, 10, 'desktop'))
    expect((await laneSvgs(ui)).length).toBe(5)
    expect(JSON.stringify(await ui.drawn())).not.toContain(' more')
    await ui.unmount()
    await close()
  })
  test('the pane asks for room for three lanes when it opens: 20 rows by 72 columns', async ($, on) => {
    const { sizes, close } = world(on, twoWorking())
    await say($)
    // The List's open first, which asks for no size.
    expect(sizes).toEqual([[undefined, undefined], [20, 72]])
    await close()
  })
})

group('the walk', () => {
  test('a walker moves only forward, is between the stations halfway, and stands at the new one at the end', async ($, on) => {
    const files = working(job(12, 'SHAPE'))
    const { clock, blits, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    files.set(STATUS, statusText(job(12, 'TEST')))
    await clock.advance(2000)
    await drain()
    const [from, to] = [home(at('shape'), 72), home(at('test'), 72)]
    const seen: number[] = []
    for (let i = 0; i < 10; i++) {
      await clock.advance(80)
      await drain()
      const cells = lastBlit(blits, 'lane-12')
      if (cells) seen.push(heads(cells, 72)[0]!)
    }
    expect(seen.length).toBeGreaterThan(3)
    for (let i = 1; i < seen.length; i++) expect(seen[i]!).toBeGreaterThanOrEqual(seen[i - 1]!)
    expect(seen[seen.length - 1]).toBe(to)
    expect(seen.some(x => x > from && x < to)).toBe(true)
    await ui.unmount()
    await close()
  })
  test('a redraw halfway through the walk draws the walker where it is at that moment', async ($, on) => {
    const files = working(job(12, 'SHAPE'))
    const { clock, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    files.set(STATUS, statusText(job(12, 'TEST')))
    await clock.advance(2000)
    await drain()
    await clock.advance(walkMs(1, 2) / 2)
    await drain()
    await ui.redraw()
    // Halfway, eased, from plan to test: stationX(1.5), its head one in from its left edge.
    expect(heads(await cellsOf(ui, 'lane-12'), 72)).toEqual([Math.round(stationX(1.5, 72) - 1) + 1])
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
    await clock.advance(1500)
    await drain()
    expect(invalidated.length).toBe(after)
    await ui.unmount()
    await close()
  })
  test('with nobody walking, work at a station is painted as it changes, never redrawn', async ($, on) => {
    const { clock, blits, close } = world(on, working(job(12, 'BUILD')))
    await say($)
    const ui = await $.ui.mount(WIDE())
    const before = JSON.stringify(await ui.drawn())
    for (let i = 0; i < 15; i++) {
      await clock.advance(80)
      await drain()
    }
    const painted = blits.filter(b => b.key === 'lane-12').map(b => b.cells)
    expect(painted.length).toBeGreaterThan(2)
    // A blit goes out only when the lane changed.
    for (let i = 1; i < painted.length; i++) expect(painted[i]).not.toBe(painted[i - 1])
    expect(JSON.stringify(await ui.drawn())).toBe(before)
    await ui.unmount()
    await close()
  })
  test('opening the pane and switching it walk nobody, even when the issues moved', async ($, on) => {
    const files = twoWorking()
    files.set(`${ALPHA}/status.json`, statusText(job(30, 'BUILD')))
    files.set(`${ALPHA}/lock`, '4242')
    const { close } = world(on, files)
    const walks = async (ui: unknown) => (await laneSvgs(ui)).filter(s => String(s.props.source).includes('<animateTransform')).length
    const desk = pane(72, 40, 'desktop')
    await say($, '', desk)
    const ui = await $.ui.mount(desk)
    expect(await walks(ui)).toBe(0)
    await say($, 'alpha', desk, ui)
    await ui.redraw()
    expect((await laneSvgs(ui)).map(s => s.props.alt)).toEqual(['Issue #30 at build'])
    expect(await walks(ui)).toBe(0)
    await say($, '', desk, ui)
    await ui.redraw()
    expect(await walks(ui)).toBe(0)
    // Closed and opened again on what has since moved. /factory-floor closes it, where loop-crew's test
    // ran /loop-crew a second time.
    await shut($)
    files.set(STATUS, statusText(job(12, 'SCALE'), job(13, 'SHAPE')))
    await say($, '', desk, ui)
    await ui.redraw()
    expect((await laneSvgs(ui)).map(s => s.props.alt)).toEqual(['Issue #12 at scale', 'Issue #13 at shape'])
    expect(await walks(ui)).toBe(0)
    await ui.unmount()
    await close()
  })
  test('a new issue walks in from discover', async ($, on) => {
    const files = working(job(12, 'SHAPE'))
    const { clock, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    files.set(STATUS, statusText(job(12, 'SHAPE'), job(14, 'TEST')))
    await clock.advance(2000)
    await drain()
    await clock.advance(walkMs(0, 2) / 2)
    await drain()
    await ui.redraw()
    const midway = heads(await cellsOf(ui, 'lane-14'), 72)[0]!
    expect(midway).toBeGreaterThan(home(at('discover'), 72))
    expect(midway).toBeLessThan(home(at('test'), 72))
    expect(heads(await cellsOf(ui, 'lane-12'), 72)).toEqual([home(at('shape'), 72)])
    await clock.advance(walkMs(0, 2))
    await drain()
    await ui.redraw()
    expect(heads(await cellsOf(ui, 'lane-14'), 72)).toEqual([home(at('test'), 72)])
    await ui.unmount()
    await close()
  })
})

group('walking out', () => {
  test('a row gone to pr walks off the end of its lane, asks for one redraw when it ends, and is gone', async ($, on) => {
    const files = working(job(12, 'BUILD'))
    const { clock, blits, invalidated, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    await drain()
    const first = invalidated.length
    files.set(STATUS, statusText(job(12, 'BUILD', { state: 'pr' })))
    await clock.advance(2000)
    await drain()
    // The read that differs asks for its own redraw, and the lane stays.
    expect(invalidated.length).toBe(first + 1)
    expect(await (ui as unknown as Finds).find({ key: 'lane-12' })).toBeDefined()
    let drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('· scale, round 1')
    expect(drawn).not.toContain('Nothing being built right now.')

    await clock.advance(OUT_MS / 2)
    await drain()
    expect(heads(lastBlit(blits, 'lane-12')!, 72)[0]!).toBeGreaterThan(home(at('build'), 72))
    expect(invalidated.length).toBe(first + 1)

    await clock.advance(OUT_MS / 2)
    await drain()
    expect(invalidated.length).toBe(first + 2)
    expect(await (ui as unknown as Finds).find({ key: 'lane-12' })).toBeUndefined()
    drawn = JSON.stringify(await ui.drawn())
    expect(drawn).not.toContain('Job 12')
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
  test('another issue still working keeps the board after the walk out ends', async ($, on) => {
    const files = working(job(12, 'BUILD'), job(13, 'SHAPE'))
    const { clock, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    files.set(STATUS, statusText(job(12, 'BUILD', { state: 'pr' }), job(13, 'SHAPE')))
    await clock.advance(3000)
    await drain()
    expect(await (ui as unknown as Finds).find({ key: 'lane-13' })).toBeDefined()
    expect(await (ui as unknown as Finds).find({ key: 'lane-12' })).toBeUndefined()
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).not.toContain('Job 12')
    expect(drawn).toContain('Job 13')
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
    expect(await (ui as unknown as Finds).find({ key: 'lane-12' })).toBeUndefined()
    expect(JSON.stringify(await ui.drawn())).toContain('Nothing being built right now.')
    await ui.unmount()
    await close()
  })
  test('a walk out shows on the desktop too, with its one redraw', async ($, on) => {
    const files = working(job(12, 'BUILD'))
    const { clock, invalidated, close } = world(on, files)
    await say($, '', pane(72, 40, 'desktop'))
    const ui = await $.ui.mount(pane(72, 40, 'desktop'))
    await drain()
    const first = invalidated.length
    files.set(STATUS, statusText(job(12, 'BUILD', { state: 'pr' })))
    await clock.advance(2000)
    await drain()
    const lanes = await laneSvgs(ui)
    expect(lanes.map(s => s.props.alt)).toEqual(['Issue #12 at scale'])
    expect(String(lanes[0]!.props.source)).toContain('<animateTransform')
    await clock.advance(OUT_MS)
    await drain()
    expect(invalidated.length).toBe(first + 2)
    expect(await laneSvgs(ui)).toEqual([])
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
    await say($, 'alpha', WIDE(), ui)
    await drain()
    const after = invalidated.length
    await clock.advance(OUT_MS)
    await drain()
    expect(invalidated.length).toBe(after)
    await ui.unmount()
    await close()
  })
})

group('painting the board', () => {
  test('the header, drawn with the pane, is not painted while no station changes', async ($, on) => {
    const { clock, blits, close } = world(on, working(job(12, 'SHAPE')))
    await say($)
    const ui = await $.ui.mount(WIDE())
    for (let i = 0; i < 4; i++) {
      await clock.advance(80)
      await drain()
    }
    // The header doesn't move: drawn once, never painted.
    expect(blits.filter(b => b.key === 'head').length).toBe(0)
    await ui.unmount()
    await close()
  })
  for (const answer of ['deny', 'none'] as const) {
    test(`a blit answered ${answer === 'deny' ? 'with a deny' : 'by nothing'} throws nothing and is tried again on the next tick`, async ($, on) => {
      const { clock, blits, flip, close } = world(on, working(job(12, 'SHAPE')))
      flip.blit = answer
      await say($)
      const ui = await $.ui.mount(WIDE())
      const before = JSON.stringify(await ui.drawn())
      for (let i = 0; i < 20; i++) {
        await clock.advance(80)
        await drain()
      }
      // A pose lasts longer than a tick. A blit that landed isn't sent again; one that didn't goes out again.
      const painted = blits.filter(b => b.key === 'lane-12').map(b => b.cells)
      expect(painted.length).toBeGreaterThanOrEqual(19)
      expect(painted.some((cells, i) => i > 0 && cells === painted[i - 1])).toBe(true)
      expect(JSON.stringify(await ui.drawn())).toBe(before)
      await ui.unmount()
      await close()
    })
  }
  test('a pane behind another paints nothing', async ($, on) => {
    const { clock, blits, panes, close } = world(on, twoWorking())
    await say($)
    const ui = await $.ui.mount(WIDE())
    panes[0]!.isShown = false
    await clock.advance(800)
    await drain()
    expect(blits.length).toBe(0)
    await ui.unmount()
    await close()
  })
  test('a redraw after a while draws what the clock says, not the first pose', async ($, on) => {
    const { clock, close } = world(on, working(job(12, 'BUILD')))
    await say($)
    const ui = await $.ui.mount(WIDE())
    const first = await cellsOf(ui, 'lane-12')
    await clock.advance(400)
    await drain()
    await ui.redraw()
    expect(await cellsOf(ui, 'lane-12')).not.toBe(first)
    await ui.unmount()
    await close()
  })
  test('a surface that animates by itself runs no timer, and a changed step gives one walker', async ($, on) => {
    const files = twoWorking()
    const { clock, blits, flip, close } = world(on, files)
    await say($, '', pane(72, 40, 'desktop'))
    const ui = await $.ui.mount(pane(72, 40, 'desktop'))
    await drain()
    // A board timer looks for the pane on every tick, 12 times in this second. The 2 s poll looks at most once.
    flip.paneReads = 0
    await clock.advance(1000)
    await drain()
    expect(flip.paneReads).toBeLessThan(2)
    expect(blits.length).toBe(0)
    files.set(STATUS, statusText(job(12, 'BUILD', { round: 0 }), job(13, 'SCALE', { round: 2 })))
    await clock.advance(1000)
    await drain()
    const sources = (await laneSvgs(ui)).map(s => String(s.props.source))
    expect(sources.filter(s => s.includes('<animateTransform')).length).toBe(1)
    expect(blits.length).toBe(0)
    await ui.unmount()
    await close()
  })
  test('no blit once the pane closes', async ($, on) => {
    const { clock, blits, panes, close } = world(on, twoWorking())
    await say($)
    const ui = await $.ui.mount(WIDE())
    panes.length = 0
    await clock.advance(80)
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
    expect(JSON.stringify(await ui.drawn())).toContain('· scale')
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
    // The hold ends for new reads before the switch, where loop-crew's test ended it after: a press
    // waits for the reads it starts, so a held one would never let it end. The poll's read stays held.
    flip.hold = null
    await say($, 'alpha')
    release()
    await drain()
    const ui = await $.ui.mount(WIDE())
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('Job 30')
    expect(drawn).not.toContain('Job 12')
    await ui.unmount()
    await close()
  })
})

group('what the pane shows, in its order', () => {
  type Mounts = { ui: { mount: (i: typeof PANE) => Promise<Finds & { drawn: () => Promise<unknown>; unmount: () => Promise<void> }> } }
  const shown = async ($: Mounts) => {
    const ui = await $.ui.mount(WIDE())
    const drawn = JSON.stringify(await ui.drawn())
    const lane = await ui.find({ key: 'lane-12' })
    await ui.unmount()
    return { drawn, lane }
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
  test('no lock: not running, with no lanes, even for rows still at working', async ($, on) => {
    const { close } = world(on, new Map([[STATUS, statusText(job(12, 'BUILD'))]]))
    await say($)
    const { drawn, lane } = await shown($ as never)
    expect(drawn).toContain("The loop isn't running.")
    expect(lane).toBeUndefined()
    await close()
  })
  test("a stale lock: not running, whose holder is gone", async ($, on) => {
    const { flip, close } = world(on, twoWorking())
    flip.staleLock = true
    await say($)
    const { drawn, lane } = await shown($ as never)
    expect(drawn).toContain("The loop isn't running.")
    expect(lane).toBeUndefined()
    await close()
  })
  test('a lock whose pid cannot be read counts as alive', async ($, on) => {
    const { flip, close } = world(on, new Map([[STATUS, statusText(job(12, 'BUILD'))], [`${HARNESS}/lock`, 'nonsense']]))
    flip.staleLock = true
    await say($)
    expect((await shown($ as never)).drawn).toContain('Job 12')
    await close()
  })
  test('a live lock with nothing working', async ($, on) => {
    const { close } = world(on, new Map([[STATUS, statusText(job(12, 'BUILD', { state: 'pr' }))], [`${HARNESS}/lock`, '4242']]))
    await say($)
    const { drawn, lane } = await shown($ as never)
    expect(drawn).toContain('Nothing being built right now.')
    expect(lane).toBeUndefined()
    await close()
  })
  test('a live lock with a job, a lane with one figure', async ($, on) => {
    const { close } = world(on, working(job(12, 'BUILD')))
    await say($)
    const { drawn, lane } = await shown($ as never)
    expect(drawn).toContain('#12')
    expect(drawn).toContain('Job 12')
    expect(heads(String(lane?.props.cells), 72)).toEqual([home(3, 72)])
    await close()
  })
})

group('the loop picker', () => {
  const BETA = `${ROOT}/.loop/projects/beta`
  // The factory idle under a live lock. alpha live with two at working, beta with no lock and one at
  // working, and gamma a folder with no status file.
  const four = () => new Map([
    [STATUS, statusText(job(12, 'BUILD', { state: 'pr' }))],
    [`${HARNESS}/lock`, '4242'],
    [`${ALPHA}/status.json`, statusText(job(30, 'BUILD'), job(31, 'SHAPE'))],
    [`${ALPHA}/lock`, '4242'],
    [`${BETA}/status.json`, statusText(job(40, 'TEST'))],
    [`${ROOT}/.loop/projects/gamma/notes.txt`, ''],
  ])
  // The factory with two at working, and alpha beside it with one.
  const two = () => {
    const files = twoWorking()
    files.set(`${ALPHA}/status.json`, statusText(job(30, 'BUILD')))
    files.set(`${ALPHA}/lock`, '4242')
    return files
  }
  type Picks = Finds & { select: (query: { key: string; value: string }) => Promise<unknown>; redraw: () => Promise<void>; drawn: () => Promise<unknown>; unmount: () => Promise<void> }
  // Open the pane and let the read of every loop, which the command doesn't wait for, land.
  const open = async ($: unknown, args = ''): Promise<void> => {
    await say($, args)
    await drain()
    await drain()
  }
  const picker = async (ui: Picks): Promise<Found | undefined> => ui.find({ key: 'loop-pick' })
  const values = async (ui: Picks): Promise<string[]> => ((await picker(ui))?.props.options as { value: string }[]).map(o => o.value)
  // Which of the pane's top children first holds `needle`, as loop-pane's tests find its row.
  const childAt = async (ui: Picks, needle: string): Promise<number> => {
    const top = (await ui.drawn()) as { children?: unknown[] }
    return (top.children ?? []).findIndex(c => JSON.stringify(c).includes(needle))
  }
  const choose = async (ui: Picks, value: string): Promise<void> => {
    await ui.select({ key: 'loop-pick', value })
    await drain()
    await drain()
    await ui.redraw()
  }

  test('it lists the loops on a job first, the factory by its folder, and leaves out a folder with no status file', async ($, on) => {
    const { close } = world(on, four())
    await open($)
    const ui = (await $.ui.mount(WIDE())) as unknown as Picks
    const options = (await picker(ui))?.props.options as { value: string; label: string }[]
    expect(options.map(o => o.label)).toEqual(['● alpha 2', 'starter', 'beta'])
    expect(options.map(o => o.value)).toEqual(['alpha', '', 'beta'])
    expect((await picker(ui))?.props.value).toBe('')
    await ui.unmount()
    await close()
  })
  test("a project whose status file won't parse is left out, and the board still draws", async ($, on) => {
    const files = two()
    files.set(`${ROOT}/.loop/projects/delta/status.json`, '{not json')
    const { close } = world(on, files)
    await open($)
    const ui = (await $.ui.mount(WIDE())) as unknown as Picks
    expect(((await picker(ui))?.props.options as { value: string }[]).map(o => o.value)).toEqual(['', 'alpha'])
    expect(await ui.find({ key: 'lane-12' })).toBeDefined()
    expect(await ui.find({ key: 'lane-13' })).toBeDefined()
    await ui.unmount()
    await close()
  })
  test('the picker sits above the message when nothing is being built', async ($, on) => {
    const { close } = world(on, four())
    await open($)
    const ui = (await $.ui.mount(WIDE())) as unknown as Picks
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('Nothing being built right now.')
    expect(drawn.indexOf('loop-pick')).toBeGreaterThan(-1)
    expect(drawn.indexOf('loop-pick')).toBeLessThan(drawn.indexOf('Nothing being built right now.'))
    await ui.unmount()
    await close()
  })
  test('with only the factory there is no picker', async ($, on) => {
    const { close } = world(on, twoWorking())
    await open($)
    const ui = (await $.ui.mount(WIDE())) as unknown as Picks
    expect(await picker(ui)).toBeUndefined()
    expect(await ui.find({ key: 'lane-12' })).toBeDefined()
    await ui.unmount()
    await close()
  })
  // The picker is the second child here, under factory-floor's row of view buttons, where loop-crew's is
  // the first.
  test('with two loops the mobile app has no picker, and the desktop has one under the view buttons, above the header', async ($, on) => {
    const { close } = world(on, two())
    await open($)
    const phone = (await $.ui.mount(pane(72, 40, 'mobile'))) as unknown as Picks
    expect(await picker(phone)).toBeUndefined()
    expect((await laneSvgs(phone)).length).toBe(2)
    await phone.unmount()
    const desk = (await $.ui.mount(pane(72, 40, 'desktop'))) as unknown as Picks
    expect(await picker(desk)).toBeDefined()
    expect(await childAt(desk, '"mode-crew"')).toBe(0)
    expect(await childAt(desk, '"loop-pick"')).toBe(1)
    expect(await childAt(desk, '#12')).toBeGreaterThan(1)
    await desk.unmount()
    await close()
  })
  test('on a terminal the picker is under the view buttons, above the header and the lanes', async ($, on) => {
    const { close } = world(on, two())
    await open($)
    const ui = (await $.ui.mount(WIDE())) as unknown as Picks
    expect(await ui.find({ key: 'head' })).toBeDefined()
    expect(await childAt(ui, '"mode-crew"')).toBe(0)
    expect(await childAt(ui, '"loop-pick"')).toBe(1)
    expect(await childAt(ui, '#12')).toBeGreaterThan(1)
    await ui.unmount()
    await close()
  })
  test('an open keeps every loop before it compares the shown one: the picker at once, and one redraw', async ($, on) => {
    const { invalidated, close } = world(on, two())
    await say($)
    const ui = (await $.ui.mount(WIDE())) as unknown as Picks
    expect(await picker(ui)).toBeDefined()
    await drain()
    await drain()
    expect(invalidated.length).toBe(1)
    await ui.unmount()
    await close()
  })
  for (const [what, text] of [['missing', undefined], ["one that won't parse", '{not json']] as const) {
    test(`the factory is left out of the picker when its status file is ${what}`, async ($, on) => {
      const files = new Map([
        [`${HARNESS}/lock`, '4242'],
        [`${ALPHA}/status.json`, statusText(job(30, 'BUILD'))],
        [`${ALPHA}/lock`, '4242'],
        [`${BETA}/status.json`, statusText(job(40, 'TEST'))],
      ])
      if (text !== undefined) files.set(STATUS, text)
      const { close } = world(on, files)
      await open($)
      const ui = (await $.ui.mount(WIDE())) as unknown as Picks
      expect(await values(ui)).toEqual(['alpha', 'beta'])
      await ui.unmount()
      await close()
    })
  }
  test("a value that isn't one of the options switches nothing, even a folder the command would take", async ($, on) => {
    const { titles, flip, close } = world(on, four())
    await open($)
    const ui = (await $.ui.mount(WIDE())) as unknown as Picks
    const opened = titles.length
    // The kit refuses a value the Select doesn't list, as a surface sends only its options. The mod's own
    // guard, isListed, is tested in logic.test.ts. Either way nothing switches.
    for (const value of ['gamma', 'nope']) await ui.select({ key: 'loop-pick', value }).catch(() => undefined)
    await drain()
    await ui.redraw()
    expect(titles.length).toBe(opened)
    expect(flip.closes).toBe(0)
    expect((await picker(ui))?.props.value).toBe('')
    expect(JSON.stringify(await ui.drawn())).toContain('Nothing being built right now.')
    await ui.unmount()
    await close()
  })
  test("a projects folder that can't be listed gives the factory alone, so the picker goes", async ($, on) => {
    const { clock, flip, reads, close } = world(on, two())
    await open($)
    const ui = (await $.ui.mount(WIDE())) as unknown as Picks
    expect(await picker(ui)).toBeDefined()
    const alphaReads = () => reads.filter(path => path === `${ALPHA}/status.json`).length
    const before = alphaReads()
    flip.listFails = true
    await clock.advance(2000)
    await drain()
    await ui.redraw()
    expect(await picker(ui)).toBeUndefined()
    expect(await ui.find({ key: 'lane-12' })).toBeDefined()
    expect(alphaReads()).toBe(before)
    await ui.unmount()
    await close()
  })
  // loop-crew's "a switch's read of every loop that ends after a newer one is dropped" is left out: it
  // holds the read a switch starts, and a press or a pick waits for every read it starts, so the switch
  // can't end while that read is held. loop-crew's own test still covers the same code.
  test("picking alpha retitles the pane and draws alpha's lanes, and picking the factory goes back", async ($, on) => {
    const { titles, close } = world(on, two())
    await open($)
    const ui = (await $.ui.mount(WIDE())) as unknown as Picks
    await choose(ui, 'alpha')
    expect(titles[titles.length - 1]).toBe('Loop crew: alpha')
    expect(await ui.find({ key: 'lane-30' })).toBeDefined()
    expect(await ui.find({ key: 'lane-12' })).toBeUndefined()
    expect((await picker(ui))?.props.value).toBe('alpha')
    await choose(ui, '')
    expect(titles[titles.length - 1]).toBe('Loop crew')
    expect(await ui.find({ key: 'lane-12' })).toBeDefined()
    expect(await ui.find({ key: 'lane-30' })).toBeUndefined()
    await ui.unmount()
    await close()
  })
  test('picking the loop on screen opens and closes nothing, no pick closes the pane, and none reads a focus', async ($, on) => {
    const { titles, panes, flip, reads, close } = world(on, two())
    await open($)
    const ui = (await $.ui.mount(WIDE())) as unknown as Picks
    const opened = titles.length
    await choose(ui, '')
    expect(titles.length).toBe(opened)
    await choose(ui, 'alpha')
    await choose(ui, 'alpha')
    expect(titles.length).toBe(opened + 1)
    expect(flip.closes).toBe(0)
    expect(panes.length).toBe(1)
    expect(reads.filter(path => path.includes('/.sanvio/project/'))).toEqual([])
    await ui.unmount()
    await close()
  })
  // At 15 rows, not loop-crew's 14: factory-floor's row of view buttons takes one.
  test('the picker takes a row: three working lanes at 15 rows show one fewer lane with it than without', async ($, on) => {
    const lanes = async (ui: Picks): Promise<number> => (await Promise.all([1, 2, 3].map(n => ui.find({ key: `lane-${n}` })))).filter(Boolean).length
    const files = working(job(1, 'BUILD'), job(2, 'TEST'), job(3, 'SHAPE'))
    const { clock, close } = world(on, files)
    await open($)
    const ui = (await $.ui.mount(pane(72, 15))) as unknown as Picks
    expect(await picker(ui)).toBeUndefined()
    expect(await lanes(ui)).toBe(2)
    // A second loop appears, and the next poll brings the picker.
    files.set(`${ALPHA}/status.json`, statusText(job(30, 'BUILD')))
    files.set(`${ALPHA}/lock`, '4242')
    await clock.advance(2000)
    await drain()
    await ui.redraw()
    expect(await picker(ui)).toBeDefined()
    expect(await lanes(ui)).toBe(1)
    await ui.unmount()
    await close()
  })
})

// A time as loop.py writes it: local, to the second, with no zone. As loop-pane's tests build it, so
// these pass in any time zone.
function local(ms: number): string {
  const d = new Date(ms)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
// The mock clock's start, which world() sets.
const START = 1_800_000_000_000
// No time reads as an em dash, U+2014, built from its code so this file holds none.
const DASH = String.fromCharCode(0x2014)

// A lane's 4th row of cells, under its 3 rows of lane, and the text in some cells.
const rowFour = (cells: string, columns: number): [number, number, number][] => decode(cells).slice(3 * columns, 4 * columns)
const textOf = (cells: [number, number, number][]): string => cells.map(([code]) => String.fromCodePoint(code)).join('')
// Where a station's name starts in the header.
const labelAt = (index: number, columns: number): number => Math.max(0, home(index, columns) - 2)
const rootTag = (source: string): string => /<svg[^>]*>/.exec(source)![0]
const svgOf = (value: number): string => String(Math.round(value * 1000) / 1000)

// Advance the clock `ms` in steps of `step`, working the timers after each.
async function wait(clock: { advance: (ms: number) => Promise<unknown> }, ms: number, step: number): Promise<void> {
  for (let done = 0; done < ms; done += step) {
    await clock.advance(Math.min(step, ms - done))
    await drain()
  }
}

// #12 building, its plan and tests done, its build begun 42 seconds before the clock's start.
const counting = (over: object = {}) =>
  job(12, 'BUILD', { step_seconds: { SHAPE: 90, TEST: 3900, BUILD: 0 }, step_started: local(START - 42_000), ...over })

group('the times', () => {
  test('on vscode at 42 columns the header and each lane are an Svg with no size, drawn 126 wide', async ($, on) => {
    const { close } = world(on, twoWorking())
    await say($, '', pane(72, 40, 'vscode'))
    const ui = await $.ui.mount(pane(42, 40, 'vscode'))
    const [head, ...lanes] = await svgs(ui)
    expect([head!.props.width, head!.props.height]).toEqual([undefined, undefined])
    expect(rootTag(String(head!.props.source))).toBe('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 126 4">')
    expect(lanes.length).toBe(2)
    for (const lane of lanes) {
      expect([lane.props.width, lane.props.height]).toEqual([undefined, undefined])
      const root = rootTag(String(lane.props.source))
      expect(root).toContain('viewBox="0 0 126 18"')
      expect(root).not.toContain('width=')
      expect(root).not.toContain('height=')
    }
    // #12 is at build, its place worked out at that width.
    expect(String(lanes[0]!.props.source)).toContain(`<g transform="translate(${svgOf(stationX(3, 126) - 1)} 0)">`)
    await ui.unmount()
    await close()
  })
  for (const [columns, drawn] of [[10, 64], [200, 240], [Number.NaN, 64]] as const) {
    test(`on vscode ${columns} columns draws ${drawn} wide`, async ($, on) => {
      const { close } = world(on, twoWorking())
      // Opened on a pane of the List's usual width: only the drawing mounted next is that wide.
      await say($, '', pane(72, 40, 'vscode'))
      const ui = await $.ui.mount(pane(columns, 40, 'vscode'))
      const [head, ...lanes] = await svgs(ui)
      expect(rootTag(String(head!.props.source))).toContain(`viewBox="0 0 ${drawn} 4"`)
      for (const lane of lanes) expect(rootTag(String(lane.props.source))).toContain(`viewBox="0 0 ${drawn} 18"`)
      await ui.unmount()
      await close()
    })
  }
  test("on a terminal at 72 columns a lane's 4th row has each time under its stage, in its colour, counting with no redraw", async ($, on) => {
    const { clock, blits, invalidated, close } = world(on, working(counting()))
    await say($)
    const ui = await $.ui.mount(WIDE())
    await drain()
    const first = invalidated.length
    const head = textOf(decode(await cellsOf(ui, 'head')))
    const check = (cells: string, build: string): void => {
      const times = rowFour(cells, 72)
      const expected: [string, number][] = [[DASH, DARK.dim], ['1m', DARK.tool], ['1h05', DARK.tool], [build, ACCENT.build], [DASH, DARK.dim], [DASH, DARK.dim]]
      expected.forEach(([text, colour], i) => {
        const at = labelAt(i, 72)
        expect(head.slice(at, at + STATIONS[i]!.length)).toBe(STATIONS[i]!)
        expect(textOf(times.slice(at, at + text.length))).toBe(text)
        for (const [, fg] of times.slice(at, at + text.length)) expect(fg).toBe(colour)
      })
    }
    check(await cellsOf(ui, 'lane-12'), '42s')
    await wait(clock, 1040, 80)
    check(lastBlit(blits, 'lane-12')!, '43s')
    await wait(clock, 16_960, 80)
    check(lastBlit(blits, 'lane-12')!, '1m')
    expect(invalidated.length).toBe(first)
    await ui.unmount()
    await close()
  })
  test("a counting lane leaves another lane's times as they were", async ($, on) => {
    const { clock, blits, close } = world(on, working(counting(), job(13, 'VALIDATE', { step_seconds: { SHAPE: 90 }, step_started: null })))
    await say($)
    const ui = await $.ui.mount(WIDE())
    const before = textOf(rowFour(await cellsOf(ui, 'lane-13'), 72))
    const counted = textOf(rowFour(await cellsOf(ui, 'lane-12'), 72))
    await wait(clock, 3040, 80)
    const painted13 = blits.filter(b => b.key === 'lane-13')
    expect(painted13.length).toBeGreaterThan(0)
    for (const b of painted13) expect(textOf(rowFour(b.cells, 72))).toBe(before)
    expect(textOf(rowFour(lastBlit(blits, 'lane-12')!, 72))).not.toBe(counted)
    await ui.unmount()
    await close()
  })
  test('a lane walking out shows its times with nothing counting', async ($, on) => {
    const files = working(counting())
    const { clock, blits, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    files.set(STATUS, statusText(counting({ state: 'pr', step_seconds: { SHAPE: 90, TEST: 3900, BUILD: 50 } })))
    await wait(clock, 2000, 80)
    const from = blits.length
    await wait(clock, OUT_MS - 80, 80)
    const rows = blits.slice(from).filter(b => b.key === 'lane-12').map(b => rowFour(b.cells, 72))
    expect(rows.length).toBeGreaterThan(2)
    for (const times of rows) {
      expect(textOf(times.slice(labelAt(3, 72), labelAt(3, 72) + 3))).toBe('50s')
      expect(times[labelAt(3, 72)]![1]).toBe(DARK.tool)
      expect(textOf(times.slice(labelAt(5, 72), labelAt(5, 72) + 1))).toBe(DASH)
      expect(times).toEqual(rows[0]!)
    }
    await ui.unmount()
    await close()
  })
  test('a row with neither field, from an older loop, shows a dash under every stage', async ($, on) => {
    const { close } = world(on, working(job(12, 'BUILD')))
    await say($)
    const ui = await $.ui.mount(WIDE())
    const times = rowFour(await cellsOf(ui, 'lane-12'), 72)
    STATIONS.forEach((_, i) => expect([textOf(times.slice(labelAt(i, 72), labelAt(i, 72) + 1)), times[labelAt(i, 72)]![1]]).toEqual([DASH, DARK.dim]))
    expect(times.filter(([code]) => code !== 0x20).length).toBe(STATIONS.length)
    await ui.unmount()
    await close()
  })
  test('at 42 columns a test time of 36,300 seconds is cut, leaving a blank column before the build time', async ($, on) => {
    const { close } = world(on, working(job(12, 'BUILD', { step_seconds: { TEST: 36_300 }, step_started: null })))
    await say($)
    const ui = await $.ui.mount(pane(42, 60))
    const times = rowFour(await cellsOf(ui, 'lane-12'), 42)
    const [test, build] = [labelAt(2, 42), labelAt(3, 42)]
    expect(textOf(times.slice(test, build - 1))).toBe('10h…')
    expect(times[build - 1]![0]).toBe(0x20)
    expect(textOf(times.slice(build, build + 1))).toBe(DASH)
    await ui.unmount()
    await close()
  })
  test('on the desktop, with nothing changing, a counting lane redraws at 30 seconds and again at 60, and no sooner', async ($, on) => {
    const { clock, invalidated, close } = world(on, working(counting()))
    await say($, '', pane(72, 40, 'desktop'))
    const ui = await $.ui.mount(pane(72, 40, 'desktop'))
    await drain()
    // The time after build's name: the text at y 13 that follows it.
    const buildTime = async () => /<text x="\d+" y="13"[^>]*>([^<]*)<\/text>/.exec(String((await laneSvgs(ui))[0]!.props.source).split('>build<')[1]!)![1]
    expect(await buildTime()).toBe('42s')
    const first = invalidated.length
    await wait(clock, 29_900, 2000)
    expect(invalidated.length).toBe(first)
    await wait(clock, 100, 100)
    expect(invalidated.length).toBe(first + 1)
    await wait(clock, 30_000, 2000)
    expect(invalidated.length).toBe(first + 2)
    // Each drawing gives the time as of when it's drawn.
    await ui.redraw()
    expect(await buildTime()).toBe('1m')
    await ui.unmount()
    await close()
  })
  test('on the desktop, drawing the pane again keeps one 30-second timer, so the redraws never stack', async ($, on) => {
    const { clock, invalidated, close } = world(on, working(counting()))
    await say($, '', pane(72, 40, 'desktop'))
    const ui = await $.ui.mount(pane(72, 40, 'desktop'))
    await drain()
    // Each drawing asks to start the timer. Without the guard the drawings at 2, 4 and 6 seconds would
    // each add one, firing at 32, 34 and 36 seconds, so 60 seconds would bring five redraws, not two.
    for (let i = 0; i < 3; i++) {
      await wait(clock, 2000, 2000)
      await ui.redraw()
    }
    await drain()
    const first = invalidated.length
    await wait(clock, 24_000, 2000)
    expect(invalidated.length).toBe(first + 1)
    await wait(clock, 30_000, 2000)
    expect(invalidated.length).toBe(first + 2)
    await ui.unmount()
    await close()
  })
  test('on the desktop, with nothing counting, there is no redraw over 60 seconds', async ($, on) => {
    const stopped = job(12, 'BUILD', { step_seconds: { BUILD: 30 }, step_started: null })
    const waiting = job(13, '', { step_seconds: {}, step_started: local(START - 5000) })
    const { clock, invalidated, close } = world(on, working(stopped, waiting, job(14, 'TEST')))
    await say($, '', pane(72, 40, 'desktop'))
    const ui = await $.ui.mount(pane(72, 40, 'desktop'))
    await drain()
    const first = invalidated.length
    await wait(clock, 60_000, 2000)
    expect(invalidated.length).toBe(first)
    await ui.unmount()
    await close()
  })
  test('the 30-second redraw stops once the pane is gone', async ($, on) => {
    const { clock, invalidated, panes, close } = world(on, working(counting()))
    await say($, '', pane(72, 40, 'desktop'))
    const ui = await $.ui.mount(pane(72, 40, 'desktop'))
    await drain()
    const first = invalidated.length
    panes.length = 0
    await wait(clock, 60_000, 2000)
    expect(invalidated.length).toBe(first)
    await ui.unmount()
    await close()
  })
  test('on a terminal the 30-second redraw never runs, even while a lane counts', async ($, on) => {
    const { clock, invalidated, close } = world(on, working(counting()))
    await say($)
    const ui = await $.ui.mount(WIDE())
    await drain()
    const first = invalidated.length
    await wait(clock, 60_000, 2000)
    expect(invalidated.length).toBe(first)
    await ui.unmount()
    await close()
  })
})

// The current run's start, as status.json's started and usage.json's run_started write it.
const THIS_RUN = '2026-11-03T09:00:00'
// A usage.json entry as loop.py writes one, its tokens all as input.
const use = (step: string, round: number, run: string, tokens: number | null, cost: number | null, over: object = {}) => ({
  step, round, run_started: run, reported: tokens !== null, model: 'claude-sonnet-5-5',
  input_tokens: tokens, output_tokens: tokens === null ? null : 0, cache_write_tokens: tokens === null ? null : 0,
  cache_read_tokens: tokens === null ? null : 0, cost_usd: cost, ...over,
})
const usageText = (...entries: object[]): string => JSON.stringify(entries)
const usagePath = (loop: string, number: number): string => `${loop}/issue-${number}/usage.json`
// Two runs of #12. The current one has two rounds of build and two of review, the second unreported,
// and a retro.
const SPENT = usageText(
  use('plan', 0, '2026-11-01T09:00:00', 999_999, 9),
  use('plan', 0, THIS_RUN, 85_000, 0.29),
  use('test', 0, THIS_RUN, 253_898, 1.15),
  use('build', 1, THIS_RUN, 3_000_000, 1),
  use('build', 2, THIS_RUN, 3_208_489, 0.729),
  use('review', 1, THIS_RUN, 40_000, 0.2),
  use('review', 2, THIS_RUN, null, null),
  use('retro', 0, THIS_RUN, 500, 0.5),
)
// An issue building in the current run, with the totals status.json carries. The spend is kept by the
// module across tests, so each test's tokens come from fresh(), and no test sees another's.
let serial = 0
const fresh = (): number => 1_000_000 + ++serial
const spending = (tokens: number, number = 12, over: object = {}) => job(number, 'BUILD', { started: THIS_RUN, tokens, cost_usd: 3.869, ...over })
const withSpend = (tokens: number): Map<string, string> => {
  const files = working(spending(tokens))
  files.set(usagePath(HARNESS, 12), SPENT)
  return files
}
// A lane's 5th row of cells, under its row of times.
const rowFive = (cells: string, columns: number): [number, number, number][] => decode(cells).slice(4 * columns, 5 * columns)
const readsOf = (reads: string[], path: string): number => reads.filter(p => p === path).length

group('the spend', () => {
  test("on a terminal at 72 columns a lane's 5th row has each stage's spend under its time, painted as drawn", async ($, on) => {
    const { clock, blits, reads, close } = world(on, withSpend(fresh()))
    await say($)
    const ui = await $.ui.mount(WIDE())
    const expected: [string, number][] = [
      [DASH, DARK.dim], ['$0.29 85k', DARK.tool], ['$1.15 253k', DARK.tool], ['$1.72 6.2M', ACCENT.build], ['$0.20 40k', DARK.tool], [DASH, DARK.dim],
    ]
    const check = (cells: string): void => {
      const times = rowFour(cells, 72)
      const spend = rowFive(cells, 72)
      expected.forEach(([text, colour], i) => {
        const at = labelAt(i, 72)
        expect(times[at]![0]).not.toBe(0x20)
        expect(textOf(spend.slice(at, at + text.length))).toBe(text)
        for (const [, fg] of spend.slice(at, at + text.length)) expect(fg).toBe(colour)
      })
      expect(textOf(spend.slice(labelAt(2, 72), labelAt(3, 72))).trimEnd().length).toBeLessThanOrEqual(10)
    }
    check(await cellsOf(ui, 'lane-12'))
    // The tick paints it the same, and never reads the file.
    await wait(clock, 400, 80)
    check(lastBlit(blits, 'lane-12')!)
    expect(readsOf(reads, usagePath(HARNESS, 12))).toBe(1)
    await ui.unmount()
    await close()
  })
  test('at 42 columns build reads $1.72 alone, followed by a blank column', async ($, on) => {
    const { close } = world(on, withSpend(fresh()))
    await say($)
    const ui = await $.ui.mount(pane(42, 60))
    const spend = rowFive(await cellsOf(ui, 'lane-12'), 42)
    const [build, check] = [labelAt(3, 42), labelAt(4, 42)]
    expect(textOf(spend.slice(build, check - 1))).toBe('$1.72')
    expect(spend[check - 1]![0]).toBe(0x20)
    await ui.unmount()
    await close()
  })
  test('usage.json is read once for an unchanged row, again when tokens change, and again when only cost_usd does', async ($, on) => {
    const seed = fresh()
    const files = withSpend(seed)
    const { clock, reads, close } = world(on, files)
    const path = usagePath(HARNESS, 12)
    await say($)
    const ui = await $.ui.mount(WIDE())
    await wait(clock, 6000, 2000)
    expect(readsOf(reads, path)).toBe(1)
    files.set(path, usageText(use('build', 1, THIS_RUN, 2000, 12.4)))
    files.set(STATUS, statusText(spending(seed + 1)))
    await wait(clock, 2000, 2000)
    expect(readsOf(reads, path)).toBe(2)
    await ui.redraw()
    expect(textOf(rowFive(await cellsOf(ui, 'lane-12'), 72).slice(labelAt(3, 72), labelAt(4, 72) - 1)).trimEnd()).toBe('$12.40 2k')
    files.set(STATUS, statusText(spending(seed + 1, 12, { cost_usd: 12.5 })))
    await wait(clock, 2000, 2000)
    expect(readsOf(reads, path)).toBe(3)
    await wait(clock, 4000, 2000)
    expect(readsOf(reads, path)).toBe(3)
    await ui.unmount()
    await close()
  })
  test('usage.json is read again when only started changes, and shows that run alone', async ($, on) => {
    const seed = fresh()
    const files = withSpend(seed)
    const { clock, reads, close } = world(on, files)
    const path = usagePath(HARNESS, 12)
    const stage = async (ui: unknown, index: number): Promise<string> =>
      textOf(rowFive(await cellsOf(ui, 'lane-12'), 72).slice(labelAt(index, 72), labelAt(index + 1, 72) - 1)).trimEnd()
    await say($)
    const ui = await $.ui.mount(WIDE())
    expect([await stage(ui, 1), await stage(ui, 3)]).toEqual(['$0.29 85k', '$1.72 6.2M'])
    // Relabelled: the same totals, with the earlier run's start.
    files.set(STATUS, statusText(spending(seed, 12, { started: '2026-11-01T09:00:00' })))
    await wait(clock, 2000, 2000)
    expect(readsOf(reads, path)).toBe(2)
    await ui.redraw()
    expect([await stage(ui, 1), await stage(ui, 3)]).toEqual(['$9.00 999k', DASH])
    await wait(clock, 4000, 2000)
    expect(readsOf(reads, path)).toBe(2)
    await ui.unmount()
    await close()
  })
  test('an issue the status file stops listing is forgotten, so listing it again reads its usage.json again', async ($, on) => {
    const seed = fresh()
    const files = working(spending(seed, 12), spending(seed, 13))
    files.set(usagePath(HARNESS, 12), SPENT)
    files.set(usagePath(HARNESS, 13), usageText(use('build', 1, THIS_RUN, 5000, 0.05)))
    const { clock, reads, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    files.set(STATUS, statusText(spending(seed, 12)))
    await wait(clock, 2000, 2000)
    files.set(STATUS, statusText(spending(seed, 12), spending(seed, 13)))
    await wait(clock, 2000, 2000)
    // #13's lane comes back into view, so the drawing reads it; a second drawing doesn't read it again.
    await ui.redraw()
    expect([readsOf(reads, usagePath(HARNESS, 12)), readsOf(reads, usagePath(HARNESS, 13))]).toEqual([1, 2])
    await ui.unmount()
    await close()
  })
  test("one issue's change doesn't read another's usage.json again", async ($, on) => {
    const seed = fresh()
    const files = working(spending(seed, 12), spending(seed, 13))
    files.set(usagePath(HARNESS, 12), SPENT)
    files.set(usagePath(HARNESS, 13), usageText(use('build', 1, THIS_RUN, 5000, 0.05)))
    const { clock, reads, close } = world(on, files)
    await say($)
    const ui = await $.ui.mount(WIDE())
    files.set(STATUS, statusText(spending(seed + 1, 12), spending(seed, 13)))
    await wait(clock, 4000, 2000)
    expect([readsOf(reads, usagePath(HARNESS, 12)), readsOf(reads, usagePath(HARNESS, 13))]).toEqual([2, 1])
    await ui.redraw()
    expect(textOf(rowFive(await cellsOf(ui, 'lane-13'), 72).slice(labelAt(3, 72), labelAt(4, 72) - 1)).trimEnd()).toBe('$0.05 5k')
    await ui.unmount()
    await close()
  })
  test("a short pane reads only the usage.json of the lane it shows, and a lane's when it comes into view", async ($, on) => {
    const seed = fresh()
    const files = working(spending(seed, 1), spending(seed, 2), spending(seed, 3))
    for (const n of [1, 2, 3]) files.set(usagePath(HARNESS, n), SPENT)
    const { clock, reads, close } = world(on, files)
    const readCounts = (): number[] => [1, 2, 3].map(n => readsOf(reads, usagePath(HARNESS, n)))
    await say($, '', pane(72, 9))
    // Room for lane 1 and "and 2 more", as in the board's short pane.
    const short = await $.ui.mount(pane(72, 9))
    expect(JSON.stringify(await short.drawn())).toContain('and 2 more')
    expect(readCounts()).toEqual([1, 0, 0])
    // The polls, and a change to a hidden lane's row, read nothing for the lanes left out.
    files.set(STATUS, statusText(spending(seed, 1), spending(seed + 1, 2), spending(seed, 3)))
    await wait(clock, 4000, 2000)
    expect(readCounts()).toEqual([1, 0, 0])
    await short.unmount()
    const tall = await $.ui.mount(WIDE())
    expect(readCounts()).toEqual([1, 1, 1])
    expect(textOf(rowFive(await cellsOf(tall, 'lane-2'), 72).slice(labelAt(3, 72), labelAt(4, 72) - 1)).trimEnd()).toBe('$1.72 6.2M')
    await wait(clock, 4000, 2000)
    expect(readCounts()).toEqual([1, 1, 1])
    await tall.unmount()
    await close()
  })
  // In place of loop-crew's test of the same name: under 42 columns factory-floor draws the List.
  test('in the Crew view a terminal too narrow for a board shows the List and reads no usage.json, and 42 shows the board', async ($, on) => {
    const { clock, reads, close } = world(on, withSpend(fresh()))
    await say($, '', pane(41, 60))
    const ui = await $.ui.mount(pane(41, 60))
    expect(await (ui as unknown as Finds).find({ key: 'tab-active' })).toBeDefined()
    expect(await (ui as unknown as Finds).find({ key: 'head' })).toBeUndefined()
    await wait(clock, 4000, 2000)
    expect(readsOf(reads, usagePath(HARNESS, 12))).toBe(0)
    await ui.unmount()
    const wide = await $.ui.mount(pane(42, 60))
    expect(await (wide as unknown as Finds).find({ key: 'head' })).toBeDefined()
    expect(await (wide as unknown as Finds).find({ key: 'lane-12' })).toBeDefined()
    await wide.unmount()
    await close()
  })
  test('the same issue number under another project keeps its own figures and its own file', async ($, on) => {
    const seed = fresh()
    const files = withSpend(seed)
    files.set(`${ALPHA}/status.json`, statusText(spending(seed)))
    files.set(`${ALPHA}/lock`, '4242')
    files.set(usagePath(ALPHA, 12), usageText(use('build', 1, THIS_RUN, 2000, 12.4)))
    const { reads, close } = world(on, files)
    const buildSpend = async (ui: unknown): Promise<string> =>
      textOf(rowFive(await cellsOf(ui, 'lane-12'), 72).slice(labelAt(3, 72), labelAt(4, 72) - 1)).trimEnd()
    await say($)
    const ui = await $.ui.mount(WIDE())
    expect(await buildSpend(ui)).toBe('$1.72 6.2M')
    await say($, 'alpha', WIDE(), ui)
    await ui.redraw()
    expect(await buildSpend(ui)).toBe('$12.40 2k')
    await say($, undefined, WIDE(), ui)
    await ui.redraw()
    expect(await buildSpend(ui)).toBe('$1.72 6.2M')
    expect([readsOf(reads, usagePath(HARNESS, 12)), readsOf(reads, usagePath(ALPHA, 12))]).toEqual([1, 1])
    await ui.unmount()
    await close()
  })
  for (const [name, text] of [['missing', undefined], ['unreadable', '{not json']] as const) {
    test(`a ${name} usage.json gives the no-time mark under every stage, and the pane still draws`, async ($, on) => {
      const files = working(spending(fresh()))
      if (text !== undefined) files.set(usagePath(HARNESS, 12), text)
      const { clock, reads, close } = world(on, files)
      await say($)
      const ui = await $.ui.mount(WIDE())
      expect(await (ui as unknown as Finds).find({ key: 'head' })).toBeDefined()
      expect(JSON.stringify(await ui.drawn())).toContain('Job 12')
      const spend = rowFive(await cellsOf(ui, 'lane-12'), 72)
      STATIONS.forEach((_, i) => expect([spend[labelAt(i, 72)]![0], spend[labelAt(i, 72)]![1]]).toEqual([0x2014, DARK.dim]))
      expect(spend.filter(([code]) => code !== 0x20).length).toBe(STATIONS.length)
      // Not read again on every poll.
      await wait(clock, 4000, 2000)
      expect(readsOf(reads, usagePath(HARNESS, 12))).toBe(1)
      await ui.unmount()
      await close()
    })
  }
  test("on the desktop a lane's Svg gives the spend at y 17, and no step, model or session id reaches any drawing", async ($, on) => {
    const bad = '<script>alert(1)</script>'
    const files = working(spending(fresh()))
    files.set(usagePath(HARNESS, 12), usageText(
      use('build', 1, THIS_RUN, 3_000_000, 1, { model: bad, session_id: '<b>X</b>' }),
      use(bad, 1, THIS_RUN, 5, 5, { model: '<b>X</b>', session_id: bad }),
    ))
    const { close } = world(on, files)
    await say($, '', pane(72, 40, 'desktop'))
    for (const surface of ['desktop', 'terminal'] as const) {
      const ui = await $.ui.mount(pane(72, 40, surface))
      if (surface === 'desktop') {
        const source = String((await laneSvgs(ui))[0]!.props.source)
        expect(source).toContain(`y="17" font-family="monospace" font-size="2.6" fill="#${ACCENT.build.toString(16)}">$1.00 3.0M</text>`)
        for (const drawn of [source, ...(await svgs(ui)).map(s => String(s.props.source) + String(s.props.alt))]) {
          expect(drawn).not.toContain('script')
          expect(drawn).not.toContain('<b>')
        }
      } else {
        const rows = textOf(decode(await cellsOf(ui, 'lane-12')).slice(3 * 72))
        expect(rows).toContain('$1.00 3.0M')
        expect(new RegExp(`^[0-9smhkM$.${DASH}… ]*$`).test(rows)).toBe(true)
      }
      await ui.unmount()
    }
    await close()
  })
})

group('the project in focus', () => {
  const APP = `${ROOT}/.loop/projects/app`
  const OTHER = `${ROOT}/.loop/projects/other`
  const LOST = `${ROOT}/.loop/projects/lost`
  const ID = '0123abcd-4567'
  const FOCUS = `${ROOT}/.sanvio/project/${ID}`
  // What fs.stat finds under projects/: app, other and lost are folders, though lost has no loop yet.
  const PROJECTS: Kinds = { app: 'dir', other: 'dir', lost: 'dir', linked: 'link', plain: 'file' }
  // The factory, app and other, each running with its own job, so the lanes say which loop is on screen.
  const loops = () => new Map([
    [STATUS, statusText(job(12, 'BUILD'))],
    [`${HARNESS}/lock`, '4242'],
    [`${APP}/status.json`, statusText(job(30, 'BUILD'))],
    [`${APP}/lock`, '4242'],
    [`${OTHER}/status.json`, statusText(job(40, 'TEST'))],
    [`${OTHER}/lock`, '4242'],
  ])
  // A world whose session has this id, and whose focus file holds `text`, or no file for null.
  const focused = (on: On, text: string | null, id: string | null = ID, files = loops()) => {
    if (text !== null) files.set(FOCUS, text)
    return { files, ...world(on, files, { session: { id }, projects: PROJECTS }) }
  }
  type Clock = { advance: (ms: number) => Promise<unknown> }
  // Past the next poll, and the switch it may make.
  const poll = async (clock: Clock): Promise<void> => {
    await clock.advance(2000)
    for (let i = 0; i < 4; i++) await drain()
  }
  const last = (titles: string[]): string | undefined => titles[titles.length - 1]
  type Picks = Finds & { select: (query: { key: string; value: string }) => Promise<unknown>; redraw: () => Promise<void>; unmount: () => Promise<void> }

  for (const [what, text, title] of [
    ['on a listed project opens on it', 'app', 'Loop crew: app'],
    ['given as projects/app opens on it', 'projects/app\n', 'Loop crew: app'],
    ['on a project with no loop opens on the factory', 'lost', 'Loop crew'],
    ['missing opens on the factory', null, 'Loop crew'],
  ] as const) {
    // Every title list here starts with the List's: /factory-floor opens the pane titled Loop.
    test(`the focus ${what}`, async ($, on) => {
      const { titles, writes, close } = focused(on, text)
      await say($)
      expect(titles).toEqual(['Loop', title])
      expect(writes).toEqual([])
      await close()
    })
  }
  for (const [what, text, id] of [
    ['names a link', 'linked', ID],
    ['names a file', 'plain', ID],
    ['names a folder that is missing', 'gone', ID],
    ['names ../x', '../x', ID],
    ['is named by an id the engine refuses', 'app', null],
    ['is named by an id SESSION refuses', 'app', 'not an id'],
  ] as const) {
    test(`a focus that ${what} opens on the factory, and polls don't move it`, async ($, on) => {
      const { clock, titles, writes, close } = focused(on, text, id)
      await say($)
      expect(titles).toEqual(['Loop', 'Loop crew'])
      await poll(clock)
      await poll(clock)
      expect(titles).toEqual(['Loop', 'Loop crew'])
      expect(writes).toEqual([])
      await close()
    })
  }
  // loop-crew's "/loop-crew other with the focus on app" and "/loop-crew twice with the focus set" are
  // left out with its command group: factory-floor's command takes no name, and its close is its own test.
  test('a focus changed between polls switches the pane, and a cleared one goes back to the factory', async ($, on) => {
    const { clock, files, titles, flip, writes, close } = focused(on, 'app')
    await say($)
    files.set(FOCUS, 'other')
    await poll(clock)
    expect(last(titles)).toBe('Loop crew: other')
    files.delete(FOCUS)
    await poll(clock)
    expect(titles).toEqual(['Loop', 'Loop crew: app', 'Loop crew: other', 'Loop crew'])
    expect(flip.closes).toBe(0)
    expect(writes).toEqual([])
    await close()
  })
  test('a focus on a project with no loop switches nothing, nor does its loop appearing later', async ($, on) => {
    const { clock, files, titles, writes, close } = focused(on, 'app')
    await say($)
    files.set(FOCUS, 'lost')
    await poll(clock)
    expect(titles).toEqual(['Loop', 'Loop crew: app'])
    files.set(`${LOST}/status.json`, statusText(job(50, 'BUILD')))
    for (let i = 0; i < 3; i++) await poll(clock)
    expect(titles).toEqual(['Loop', 'Loop crew: app'])
    expect(writes).toEqual([])
    await close()
  })
  test('a pick in the dropdown stays put across 3 polls while the focus is unchanged', async ($, on) => {
    const { clock, titles, writes, close } = focused(on, 'app')
    await say($)
    await drain()
    const ui = (await $.ui.mount(WIDE())) as unknown as Picks
    await ui.select({ key: 'loop-pick', value: 'other' })
    await drain()
    await drain()
    expect(last(titles)).toBe('Loop crew: other')
    for (let i = 0; i < 3; i++) await poll(clock)
    await ui.redraw()
    expect(titles).toEqual(['Loop', 'Loop crew: app', 'Loop crew: other'])
    expect(await ui.find({ key: 'lane-40' })).toBeDefined()
    expect(writes).toEqual([])
    await ui.unmount()
    await close()
  })
  test('a focus changed after the pane closes reopens nothing and switches nothing', async ($, on) => {
    const { clock, files, titles, reads, panes, writes, close } = focused(on, 'app')
    await say($)
    // /factory-floor closes it, where loop-crew's test ran /loop-crew a second time.
    await shut($)
    const before = reads.length
    files.set(FOCUS, 'other')
    for (let i = 0; i < 3; i++) await poll(clock)
    expect(titles).toEqual(['Loop', 'Loop crew: app'])
    expect(panes).toEqual([])
    expect(reads.slice(before)).not.toContain(FOCUS)
    expect(writes).toEqual([])
    await close()
  })
})

// factory-floor's own: the List and Crew buttons, and the Crew's saved values.
group('the List and Crew buttons', () => {
  const two = () => {
    const files = twoWorking()
    files.set(`${ALPHA}/status.json`, statusText(job(30, 'BUILD')))
    files.set(`${ALPHA}/lock`, '4242')
    return files
  }
  type Views = Finds & { press: (target: { key: string }) => Promise<unknown>; drawn: () => Promise<unknown>; unmount: () => Promise<void> }

  test('Crew then List never closes the pane, and the loop picked in the List stays on screen both ways', async ($, on) => {
    const { titles, flip, panes, close } = world(on, two())
    await say($, 'alpha')
    const ui = (await $.ui.mount(WIDE())) as unknown as Views
    expect(await ui.find({ key: 'lane-30' })).toBeDefined()
    expect(await ui.find({ key: 'lane-12' })).toBeUndefined()
    await ui.press({ key: 'mode-list' })
    expect(await ui.find({ key: 'tab-active' })).toBeDefined()
    expect((await ui.find({ key: 'loop-pick' }))?.props.value).toBe('alpha')
    const list = JSON.stringify(await ui.drawn())
    expect(list).toContain('#30 Job 30')
    expect(list).not.toContain('Job 12')
    await ui.press({ key: 'mode-crew' })
    expect(await ui.find({ key: 'lane-30' })).toBeDefined()
    expect(await ui.find({ key: 'tab-active' })).toBeUndefined()
    expect(flip.closes).toBe(0)
    expect(panes.length).toBe(1)
    expect(titles).toEqual(['Loop', 'Loop crew: alpha', 'Loop', 'Loop crew: alpha'])
    await ui.unmount()
    await close()
  })
  test("the Crew keeps its values under factory-floor, and loop-crew's stored loop doesn't move it", async ($, on) => {
    const { close } = world(on, two())
    const written: string[] = []
    // loop-crew's own stored loop is alpha. The Crew never reads it, so it opens where the List was.
    on('state.get', async (_$, e, next) => {
      const at = e as unknown as { plugin: string; key: string }
      return at.plugin === 'loop-crew' && at.key === 'shown' ? ({ value: { value: 'alpha', version: 1 } } as never) : next(e)
    })
    on('state.set', async (_$, e, next) => {
      const at = e as unknown as { plugin: string; key: string }
      written.push(`${at.plugin}/${at.key}`)
      return next(e)
    })
    await say($)
    const ui = (await $.ui.mount(WIDE())) as unknown as Views
    expect(await ui.find({ key: 'lane-12' })).toBeDefined()
    expect(await ui.find({ key: 'lane-30' })).toBeUndefined()
    expect(written).toContain('factory-floor/crew-seen')
    expect(written).toContain('factory-floor/mode')
    expect(written.filter(w => !w.startsWith('factory-floor/'))).toEqual([])
    await ui.unmount()
    await close()
  })
  test("in the List the Crew's timers paint nothing", async ($, on) => {
    const { clock, blits, close } = world(on, working(job(12, 'BUILD')))
    await say($)
    const ui = (await $.ui.mount(WIDE())) as unknown as Views
    // The Crew paints work at a station as it changes.
    await wait(clock, 1200, 80)
    expect(blits.length).toBeGreaterThan(0)
    await ui.press({ key: 'mode-list' })
    expect(await ui.find({ key: 'tab-active' })).toBeDefined()
    const from = blits.length
    await wait(clock, 1200, 80)
    expect(blits.length).toBe(from)
    await ui.unmount()
    await close()
  })
})
