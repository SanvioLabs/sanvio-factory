import { describe as group, expect, test } from 'claude-code/testing'

import { ACCENT, ACTS, DARK, LANE_PIXELS, LANE_ROWS, LIGHT, MIN_COLUMNS, NOTHING, OUT_MS, RAIL_Y, RUN, STATIONS, SVG_COLUMNS, boardColumns, clip, easeInOut, effectAt, findRoot, headCells, headSvg, inkFor, isCounting, laneAlt, laneCells, laneFit, laneSvg, laneWords, lanesOf, lockPid, parseStatus, place, poseAt, roundText, scene, showsBoard, stageTimes, stationOf, stationX, stepLine, svgColumns, timeText, unitsAt, walkLeft, walkMs, walkingOut, word } from './logic'
import type { Lane, Station, Walk } from './logic'
import type { Row, Seen } from '../types'

const NOW = 1_800_000_000_000
const row = (over: Partial<Row>): Row => ({ number: 1, title: 'A job', step: 'BUILD', state: 'working', round: 1, ...over })
const look = (over: Partial<Seen>): Seen => ({ status: { issues: [] }, isLive: true, ...over })
const reading = (...issues: Row[]): Seen => look({ status: { issues } })
const lane = (station: Station, over: Partial<Row> = {}): Lane => ({ row: row(over), station, walk: null })
const ALL_FRAMES = [...Object.values(ACTS).flat().map(pose => pose.frame), ...RUN]

// The cells back from a Raster's base64, as [code point, foreground, background].
function decode(text: string): [number, number, number][] {
  const bytes = Uint8Array.from(atob(text), c => c.charCodeAt(0))
  const view = new DataView(bytes.buffer)
  const out: [number, number, number][] = []
  for (let i = 0; i < bytes.length; i += 12) out.push([view.getUint32(i, true), view.getUint32(i + 4, true), view.getUint32(i + 8, true)])
  return out
}

// The columns of a lane's top pixel row painted in the head colour: where each figure stands.
function heads(cells: string, columns: number, ink = DARK): number[] {
  return decode(cells).slice(0, columns).flatMap(([code, fg], x) => (code === 0x2580 && fg === ink.head ? [x] : []))
}

// Every pixel colour a lane paints, top and bottom halves.
function colours(cells: string): number[] {
  return decode(cells).flatMap(([code, fg, bg]) => (code === 0x2580 ? [fg, bg] : code === 0x2584 ? [fg] : []))
}

// Two numbers within `by` of each other. The kit has no toBeCloseTo.
const near = (a: number, b: number, by = 1e-6): void => expect(Math.abs(a - b) <= by).toBe(true)

// A number as the Svg writes it, to 3 places.
const svgOf = (value: number): string => String(Math.round(value * 1000) / 1000)

// Where a standing figure's head is: its station's middle, rounded.
const home = (index: number, columns: number): number => Math.round(stationX(index, columns))

group('a step, its station and its word', () => {
  test('each step goes to its station and has its word', () => {
    const steps: [string, Station, string][] = [
      ['SHAPE', 'plan', 'planning'], ['TEST', 'test', 'writing tests'], ['BUILD', 'build', 'building'],
      ['VALIDATE', 'check', 'checking'], ['SCALE', 'ship', 'opening the pull request'],
    ]
    for (const [step, station, text] of steps) {
      expect(stationOf(step)).toBe(station)
      expect(word(step)).toBe(text)
    }
  })
  test('the stations run start to ship, left to right', () => {
    expect(STATIONS).toEqual(['start', 'plan', 'test', 'build', 'check', 'ship'])
  })
  test('an empty step is starting, at the start', () => {
    expect(word('')).toBe('starting')
    expect(stationOf('')).toBe('start')
  })
  test('an unknown step is lowercased as written, at the start', () => {
    expect(word('DEPLOY')).toBe('deploy')
    expect(stationOf('DEPLOY')).toBe('start')
  })
  test("a step named like an object's own property is still unknown", () => {
    expect(word('constructor')).toBe('constructor')
    expect(stationOf('constructor')).toBe('start')
  })
  test('a zero round says nothing, and any other says its number', () => {
    expect(roundText(0)).toBe('')
    expect(roundText(2)).toBe('round 2')
    expect(stepLine(row({ step: 'BUILD', round: 2 }))).toBe('building, round 2')
    expect(stepLine(row({ step: 'SHAPE', round: 0 }))).toBe('planning')
  })
})

group('the board', () => {
  test(`a terminal under ${MIN_COLUMNS} columns draws no board, and one wider draws it at most 120 wide`, () => {
    expect(boardColumns(MIN_COLUMNS - 1)).toBeNull()
    expect(boardColumns(MIN_COLUMNS)).toBe(MIN_COLUMNS)
    expect(boardColumns(72)).toBe(72)
    expect(boardColumns(400)).toBe(120)
  })
  test('the stations spread evenly, leaving room after the last for its work', () => {
    for (const columns of [40, 72, 120]) {
      expect(stationX(0, columns)).toBe(2)
      const gaps = STATIONS.slice(1).map((_, i) => stationX(i + 1, columns) - stationX(i, columns))
      for (const gap of gaps) near(gap, gaps[0]!)
      // The last figure's work ends inside the board.
      expect(home(STATIONS.length - 1, columns) - 1 + 5 + 6).toBeLessThan(columns)
    }
  })
  test('a lane is 3 cell rows, 6 pixels, its rail along the bottom pixel row', () => {
    expect(LANE_ROWS).toBe(3)
    expect(LANE_PIXELS).toBe(6)
    expect(RAIL_Y).toBe(5)
  })
})

group('the figures', () => {
  test('every frame is 5 rows, each row the same width of 3 or 4, in its own letters', () => {
    for (const frame of ALL_FRAMES) {
      expect(frame.length).toBe(5)
      const width = frame[0]!.length
      expect([3, 4]).toContain(width)
      for (const line of frame) {
        expect(line.length).toBe(width)
        expect(/^[.hat]+$/.test(line)).toBe(true)
      }
    }
  })
  test('the head is one pixel, at column 1 of the top row, in every frame', () => {
    for (const frame of ALL_FRAMES) {
      const at = frame.flatMap((line, y) => [...line].flatMap((c, x) => (c === 'h' ? [[x, y]] : [])))
      expect(at).toEqual([[1, 0]])
    }
  })
  test('the start has one pose and every other station two to four, each held a while', () => {
    expect(ACTS.start.length).toBe(1)
    for (const station of STATIONS.slice(1)) {
      expect(ACTS[station].length).toBeGreaterThanOrEqual(2)
      expect(ACTS[station].length).toBeLessThanOrEqual(4)
    }
    for (const pose of Object.values(ACTS).flat()) expect(pose.ms).toBeGreaterThan(0)
  })
  test('each pose of a station differs from the one before it, last to first included', () => {
    for (const station of STATIONS.slice(1)) {
      const frames = ACTS[station].map(pose => pose.frame.join('/'))
      frames.forEach((frame, i) => expect(frame).not.toBe(frames[(i + frames.length - 1) % frames.length]))
    }
  })
  test('a pose holds for its time, and the act wraps', () => {
    const [first, second] = ACTS.plan
    expect(poseAt(ACTS.plan, 0)).toBe(0)
    expect(poseAt(ACTS.plan, first!.ms - 1)).toBe(0)
    expect(poseAt(ACTS.plan, first!.ms)).toBe(1)
    expect(poseAt(ACTS.plan, first!.ms + second!.ms)).toBe(0)
  })
  test('a station\'s work stays in the 5 rows above the rail and its 7 columns, and never uses the head colour', () => {
    for (const station of STATIONS) {
      for (let ms = 0; ms < 3000; ms += 40) {
        for (const ink of [DARK, LIGHT]) {
          for (const px of effectAt(station, ms, ink)) {
            expect(px.y).toBeGreaterThanOrEqual(0)
            expect(px.y).toBeLessThan(RAIL_Y)
            expect(px.x).toBeGreaterThanOrEqual(0)
            expect(px.x).toBeLessThan(7)
            expect(px.colour).not.toBe(ink.head)
          }
        }
      }
    }
  })
})

group('the walks', () => {
  test('a longer way takes longer, up to 1.5 seconds', () => {
    expect(walkMs(1, 2)).toBe(650)
    expect(walkMs(0, 5)).toBe(1330)
    expect(walkMs(0, 50)).toBe(1500)
  })
  test('a walk eases: its middle is halfway, and it ends where it was going', () => {
    const walk = { from: 1, to: 2, start: NOW, end: NOW + 650 }
    expect(unitsAt(walk, NOW)).toBe(1)
    near(unitsAt(walk, NOW + 325), 1.5)
    expect(unitsAt(walk, NOW + 650)).toBe(2)
    expect(unitsAt(walk, NOW + 5000)).toBe(2)
    expect(easeInOut(0.25)).toBeLessThan(0.25)
  })
  test('no previous placement walks nobody, as after a reload, an open or a switch', () => {
    const placement = place(reading(row({ number: 1, step: 'TEST' }), row({ number: 2, step: 'SCALE' })), null, NOW)
    expect(placement.figures.map(f => f.walk)).toEqual([null, null])
  })
  test('a new step walks from the old station to the new', () => {
    const before = place(reading(row({ step: 'SHAPE' })), null, NOW)
    const after = place(reading(row({ step: 'TEST' })), before, NOW + 100)
    expect(after.figures[0]!.walk).toEqual({ from: 1, to: 2, start: NOW + 100, end: NOW + 750 })
  })
  test('the same station walks nobody, and a walk under way there keeps its record', () => {
    const before = place(reading(row({ step: 'SHAPE' })), null, NOW)
    const walking = place(reading(row({ step: 'TEST' })), before, NOW)
    expect(place(reading(row({ step: 'SHAPE' })), before, NOW).figures[0]!.walk).toBeNull()
    expect(place(reading(row({ step: 'TEST' })), walking, NOW + 300).figures[0]!.walk).toBe(walking.figures[0]!.walk)
    expect(place(reading(row({ step: 'TEST' })), walking, NOW + 5000).figures[0]!.walk).toBeNull()
  })
  test('a step that changes mid-walk carries on from where the figure is, with no jump back', () => {
    const before = place(reading(row({ step: 'SHAPE' })), null, NOW)
    const walking = place(reading(row({ step: 'BUILD' })), before, NOW)
    const midway = unitsAt(walking.figures[0]!.walk!, NOW + 300)
    const turned = place(reading(row({ step: 'VALIDATE' })), walking, NOW + 300)
    near(turned.figures[0]!.walk!.from, midway)
    expect(turned.figures[0]!.walk!.to).toBe(4)
  })
  test('an issue missing from the previous read walks in from the start, unless it is starting', () => {
    const before = place(reading(row({ number: 1, step: 'SHAPE' })), null, NOW)
    const after = place(reading(row({ number: 1, step: 'SHAPE' }), row({ number: 2, step: 'TEST' }), row({ number: 3, step: '' })), before, NOW)
    expect(after.figures.map(f => f.walk && [f.walk.from, f.walk.to])).toEqual([null, [0, 2], null])
  })
  test('a walker stands at its station once there, and goes back as the mirror image of going forward', () => {
    const walk = { from: 3, to: 1, start: NOW, end: NOW + 820 }
    const columns = 72
    const at = (ms: number) => heads(laneCells({ row: row({}), station: 'plan', walk }, columns, NOW + ms), columns)
    expect(at(0)).toEqual([home(3, columns)])
    expect(at(410)[0]!).toBeLessThan(home(3, columns))
    expect(at(410)[0]!).toBeGreaterThan(home(1, columns))
    expect(at(820)).toEqual([home(1, columns)])
    near(walkLeft(walk, columns, NOW + 410), stationX(2, columns) - 1)
  })
  test('a walker carries its tool in front: right of its head going forward, left going back', () => {
    const columns = 72
    for (const [from, to, side] of [[1, 3, 1], [3, 1, -1]] as const) {
      const cells = laneCells({ row: row({}), station: 'plan', walk: { from, to, start: NOW, end: NOW + 820 } }, columns, NOW + 300)
      const [head] = heads(cells, columns)
      // The tool is in the second pixel row: the lower half of the top row of cells.
      const tools = decode(cells).slice(0, columns).flatMap(([code, fg, bg], x) =>
        (code === 0x2584 && fg === DARK.tool) || (code === 0x2580 && bg === DARK.tool) ? [x] : [])
      expect(tools).toEqual([head! + side])
    }
    for (const frame of RUN) expect(frame.map(line => [...line].reverse().join(''))).not.toEqual(frame)
  })
})

group('walking out', () => {
  const before = place(reading(row({ number: 12, step: 'BUILD' })), null, NOW)
  const out = place(reading(row({ number: 12, step: 'BUILD', state: 'pr' })), before, NOW)
  test('a row gone to pr walks from its station off past the last one, and is no longer a figure', () => {
    expect(out.figures).toEqual([])
    expect(out.outs.map(o => [o.row.number, o.walk.from, o.walk.to, o.walk.isOut, o.walk.end - NOW])).toEqual([[12, 3, 5, true, OUT_MS]])
  })
  test('its lane says it is opening the pull request, keeping its round, until the walk ends', () => {
    expect(lanesOf(out, NOW).map(l => [l.row.number, l.station, stepLine(l.row)])).toEqual([[12, 'ship', 'opening the pull request, round 1']])
    expect(lanesOf(out, NOW + OUT_MS)).toEqual([])
  })
  test('it holds back only the one message, and only until the walk ends', () => {
    expect(showsBoard(NOTHING, out, NOW)).toBe(true)
    expect(showsBoard(NOTHING, out, NOW + OUT_MS)).toBe(false)
    expect(showsBoard("The loop isn't running.", out, NOW)).toBe(false)
    expect(walkingOut(out, NOW + OUT_MS - 1).length).toBe(1)
  })
  test('a later read keeps its walk until it ends', () => {
    const later = place(reading(row({ number: 12, step: 'BUILD', state: 'pr' })), out, NOW + 400)
    expect(later.outs.map(o => o.walk)).toEqual(out.outs.map(o => o.walk))
    expect(place(reading(row({ number: 12, step: 'BUILD', state: 'pr' })), out, NOW + OUT_MS).outs).toEqual([])
  })
  test('it walks past the board\'s edge', () => {
    const walk = out.outs[0]!.walk
    expect(walkLeft(walk, 72, NOW + OUT_MS)).toBe(73)
    expect(heads(laneCells(lanesOf(out, NOW)[0]!, 72, NOW + OUT_MS - 1), 72)).toEqual([])
  })
  test('a row leaving working any other way is gone with no walk', () => {
    const gone = place(reading(row({ number: 12, step: 'BUILD', state: 'blocked' })), before, NOW)
    expect(gone).toEqual({ figures: [], outs: [] })
  })
})

group('the words', () => {
  test('a lane says its number, its title and where it has got to', () => {
    expect(laneWords(row({ number: 12, title: 'Job 12', step: 'BUILD', round: 2 }))).toEqual({ number: '#12', title: 'Job 12', status: '· building, round 2' })
  })
  test('cut to a width, the title gives way and the status never does', () => {
    const words = laneWords(row({ number: 1, title: 'x'.repeat(100), step: 'BUILD', round: 1 }), 40)
    expect(words.status).toBe('· building, round 1')
    expect(words.title).toBe(`${'x'.repeat(16)}…`)
    expect(words.number.length + words.title.length + words.status.length + 2).toBe(40)
  })
  test('as many lanes as fit, or as many as leave one row for "and n more", never fewer than one', () => {
    expect(laneFit(3, 4, 12)).toBe(3)
    expect(laneFit(3, 4, 11)).toBe(2)
    expect(laneFit(3, 4, 2)).toBe(1)
    expect(laneFit(3, 4, undefined)).toBe(3)
    expect(laneFit(3, 4, Number.NaN)).toBe(3)
  })
})

group('the Raster cells', () => {
  for (const station of STATIONS) {
    test(`a lane at ${station} decodes to its width by 3 rows of half blocks or spaces, one head at its station`, () => {
      const columns = 72
      const cells = decode(laneCells(lane(station), columns, NOW))
      expect(cells.length).toBe(columns * (LANE_ROWS + 1))
      for (const [code] of cells.slice(0, columns * LANE_ROWS)) expect([0x20, 0x2580, 0x2584]).toContain(code)
      expect(heads(laneCells(lane(station), columns, NOW), columns)).toEqual([home(STATIONS.indexOf(station), columns)])
    })
  }
  test('the head colour is in a lane once, wherever its figure is', () => {
    for (const station of STATIONS) {
      for (let ms = 0; ms < 2000; ms += 160) {
        expect(colours(laneCells(lane(station), 72, NOW + ms)).filter(c => c === DARK.head).length).toBe(1)
      }
    }
  })
  test('the rail is lit in the colour of each station up to the figure, and dotted after it', () => {
    const cells = decode(laneCells(lane('test'), 72, NOW))
    const bottom = cells.slice(2 * 72, 3 * 72).map(([code, fg, bg]) => (code === 0x2580 ? bg : code === 0x2584 ? fg : -1))
    expect(bottom[home(0, 72)]).toBe(ACCENT.start)
    expect(bottom[home(1, 72)]).toBe(ACCENT.plan)
    expect(bottom[home(4, 72)]).toBe(DARK.rail)
  })
  test('a light theme paints its own head and rail colours', () => {
    const cells = laneCells(lane('build'), 72, NOW, LIGHT)
    expect(heads(cells, 72, LIGHT)).toEqual([home(3, 72)])
    expect(colours(cells)).toContain(LIGHT.rail)
    expect(colours(cells)).not.toContain(DARK.head)
  })
  test('the theme is light only when its name says so', () => {
    expect(inkFor('light')).toBe(LIGHT)
    expect(inkFor('light-daltonized')).toBe(LIGHT)
    expect(inkFor('dark')).toBe(DARK)
    expect(inkFor('auto')).toBe(DARK)
    expect(inkFor(undefined)).toBe(DARK)
  })
  test(`at ${MIN_COLUMNS} columns and over, the header's station names never touch`, () => {
    for (let columns = MIN_COLUMNS; columns <= 120; columns++) {
      const text = decode(headCells([], columns)).map(([code]) => String.fromCodePoint(code)).join('')
      expect(text.trim().split(/ +/)).toEqual(STATIONS)
    }
  })
  test(`at ${MIN_COLUMNS} columns and over, a station's work never covers the next station's node`, () => {
    for (const columns of [MIN_COLUMNS, 48, 56, 64, 72]) {
      STATIONS.forEach((station, reached) => {
        for (let ms = 0; ms < 2400; ms += 40) {
          const top = decode(laneCells(lane(station), columns, NOW + ms)).slice(2 * columns, 3 * columns)
          STATIONS.forEach((other, i) => {
            const [code, fg] = top[Math.round(stationX(i, columns))]!
            expect([code, fg]).toEqual([0x2580, i <= reached ? ACCENT[other] : DARK.rail])
          })
        }
      })
    }
  })
  test('the header names every station over its node, in its colour while busy and dim otherwise', () => {
    const columns = 72
    const cells = decode(headCells([lane('build')], columns))
    const text = cells.map(([code]) => String.fromCodePoint(code)).join('')
    STATIONS.forEach((station, i) => {
      const at = Math.max(0, home(i, columns) - 2)
      expect(text.slice(at, at + station.length)).toBe(station)
      expect(cells[at]![1]).toBe(station === 'build' ? ACCENT.build : DARK.dim)
    })
  })
})

group('the Svg', () => {
  const standing = laneSvg(lane('build', { number: 12 }), NOW)
  test(`a lane is ${SVG_COLUMNS} by 14 in its viewBox, with no size of its own, smooth`, () => {
    const root = /<svg[^>]*>/.exec(standing)![0]
    expect(root).toContain(`viewBox="0 0 ${SVG_COLUMNS} 14"`)
    expect(root).not.toContain('width=')
    expect(root).not.toContain('height=')
    expect(standing).not.toContain('crispEdges')
  })
  test('its rail is a gradient line up to the figure, dotted after, with a round node at every station', () => {
    expect(standing).toContain('<linearGradient id="lit"')
    expect(standing).toContain('stroke="url(#lit)"')
    expect(standing).toContain('stroke-dasharray')
    expect(standing.split('<circle').length - 1).toBe(STATIONS.length)
  })
  test('a figure standing has no motion, and its poses take turns', () => {
    expect(standing).not.toContain('<animateTransform')
    expect(standing).toContain('<animate attributeName="visibility"')
    expect(standing).toContain(`<g transform="translate(${svgOf(stationX(3, SVG_COLUMNS) - 1)} 0)">`)
  })
  test('a walking figure stands at its new station and slides there from where it is, then works', () => {
    const walk = { from: 1, to: 3, start: NOW, end: NOW + 820 }
    const source = laneSvg({ row: row({}), station: 'build', walk }, NOW)
    const target = stationX(3, SVG_COLUMNS) - 1
    expect(source).toContain(`<g transform="translate(${svgOf(target)} 0)">`)
    const values = /type="translate" values="([^"]+)" dur="820ms" fill="freeze"/.exec(source)![1]!.split(';')
    near(Number(values[0]!.split(' ')[0]), stationX(1, SVG_COLUMNS) - 1 - target, 0.01)
    expect(values[values.length - 1]).toBe('0 0')
    expect(source).toContain('<set attributeName="display" to="none" dur="820ms"/>')
    expect(source).toContain('<set attributeName="display" to="inline" dur="820ms"/>')
  })
  test('a figure walking out slides off past the edge and does no work', () => {
    const walk = { from: 3, to: 5, start: NOW, end: NOW + OUT_MS, isOut: true }
    const source = laneSvg({ row: row({}), station: 'ship', walk }, NOW)
    expect(source).toContain(`<g transform="translate(${SVG_COLUMNS + 1} 0)">`)
    expect(source).not.toContain('to="none"')
  })
  test('no title or unknown step reaches a source or alt, only the number and the station', () => {
    const odd = lane('start', { number: 7, title: '<script>alert(1)</script>', step: '<b>X</b>' })
    for (const text of [laneSvg(odd, NOW), headSvg([odd]), laneAlt(odd)]) {
      expect(text).not.toContain('script')
      expect(text).not.toContain('<b>')
      expect(text).not.toContain('alert')
    }
    expect(laneAlt(odd)).toBe('Issue #7 at start')
    // Nor text in the times: a step name, a value or a start time, whether a Row built in code carries it
    // or the status file does.
    const times = { step_seconds: { '<script>alert(1)</script>': 5, BUILD: '<b>X</b>' as unknown as number }, step_started: '<b>X</b><script>alert(1)</script>' }
    const parsed = parseStatus(JSON.stringify({ issues: [{ number: 7, step: 'BUILD', state: 'working', ...times }] }))!.issues[0]!
    const carrying: Lane[] = [lane('build', { number: 7, ...times }), { row: parsed, station: 'build', walk: null }]
    for (const odder of carrying) {
      const row4 = decode(laneCells(odder, 72, NOW)).slice(72 * LANE_ROWS).map(([code]) => String.fromCodePoint(code)).join('')
      expect(/^[0-9smh—… ]*$/.test(row4)).toBe(true)
      for (const text of [laneSvg(odder, NOW), laneSvg(odder, NOW, DARK, 126), headSvg([odder]), laneAlt(odder), row4]) {
        expect(text).not.toContain('script')
        expect(text).not.toContain('<b>')
        expect(text).not.toContain('alert')
      }
    }
  })
  test('the header names every station, busy ones in their colour', () => {
    const source = headSvg([lane('test')])
    for (const station of STATIONS) expect(source).toContain(`>${station}</text>`)
    expect(source).toContain(`fill="#${ACCENT.test.toString(16)}">test<`)
  })
})

// A time as loop.py writes it: local, to the second, with no zone. As loop-pane's tests build it, so
// these pass in any time zone.
function local(ms: number): string {
  const d = new Date(ms)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

const STEP_OF: Record<Station, string> = { start: '', plan: 'SHAPE', test: 'TEST', build: 'BUILD', check: 'VALIDATE', ship: 'SCALE' }

// A lane whose row records times, its current step begun `ago` ms before NOW, or not counting at null.
const timed = (station: Station, seconds: Record<string, number>, ago: number | null, walk: Walk | null = null): Lane =>
  ({ row: row({ step: STEP_OF[station], step_seconds: seconds, step_started: ago === null ? null : local(NOW - ago) }), station, walk })

// A lane's 4th row of cells, under its 3 rows of lane.
const timeRowOf = (cells: string, columns: number): [number, number, number][] => decode(cells).slice(LANE_ROWS * columns, (LANE_ROWS + 1) * columns)
const textOf = (cells: [number, number, number][]): string => cells.map(([code]) => String.fromCodePoint(code)).join('')
// Where a station's name starts in the header.
const labelAt = (index: number, columns: number): number => Math.max(0, home(index, columns) - 2)
const hexOf = (colour: number): string => `#${colour.toString(16).padStart(6, '0')}`

// Every text in an Svg, as [x, y, fill, words].
function svgTexts(source: string): [number, number, string, string][] {
  const out: [number, number, string, string][] = []
  const re = /<text x="([\d.]+)" y="(\d+)" font-family="monospace" font-size="2\.6" fill="(#[0-9a-f]{6})">([^<]*)<\/text>/g
  for (let m = re.exec(source); m; m = re.exec(source)) out.push([Number(m[1]!), Number(m[2]!), m[3]!, m[4]!])
  return out
}

const OUT = { from: 3, to: 5, start: NOW, end: NOW + OUT_MS, isOut: true }

group('the times', () => {
  test("the status file keeps a row's times only when it has them, and only the five steps at 0 or more", () => {
    const text = '{"issues": [' +
      '{"number": 4, "title": "T", "step": "BUILD", "state": "working", "round": 1, ' +
      '"step_seconds": {"SHAPE": 30, "TEST": 0, "BUILD": 1.5, "VALIDATE": -1, "SCALE": 1e999, "DEPLOY": 9, "constructor": 3, "__proto__": 5}, ' +
      '"step_started": "2027-01-15T08:00:00"}, ' +
      '{"number": 5, "step_seconds": {"SCALE": "60"}, "step_started": "soon"}, ' +
      '{"number": 6, "step_seconds": [5], "step_started": 1800000000}, ' +
      '{"number": 7, "step_seconds": null, "step_started": null}, ' +
      '{"number": 8, "step_started": "2027-01-15T08:00:00"}, ' +
      '{"number": 9}]}'
    const [a, b, c, d, e, f] = parseStatus(text)!.issues
    expect(a).toEqual({ number: 4, title: 'T', step: 'BUILD', state: 'working', round: 1, step_seconds: { SHAPE: 30, TEST: 0, BUILD: 1.5 }, step_started: '2027-01-15T08:00:00' })
    expect([b!.step_seconds, b!.step_started]).toEqual([{}, null])
    expect([c!.step_seconds, c!.step_started]).toEqual([{}, null])
    expect([d!.step_seconds, d!.step_started]).toEqual([{}, null])
    expect('step_seconds' in e!).toBe(false)
    expect(e!.step_started).toBe('2027-01-15T08:00:00')
    // A row with neither, as an older loop writes, parses as it always has.
    expect(f).toEqual({ number: 9, title: '', step: '', state: '', round: 0 })
    expect('step_seconds' in f! || 'step_started' in f!).toBe(false)
  })
  test('a time reads in seconds, then minutes, then hours and two-digit minutes, floored, and none as a dash', () => {
    const cases: [number | null, string][] = [
      [0, '0s'], [42, '42s'], [59, '59s'], [60, '1m'], [3599, '59m'], [3600, '1h00'], [3900, '1h05'],
      [59.9, '59s'], [36_300, '10h05'], [null, '—'],
    ]
    for (const [seconds, text] of cases) expect(timeText(seconds)).toBe(text)
  })
  test('each station takes its time from its step, and the start never has one', () => {
    const all = { SHAPE: 10, TEST: 20, BUILD: 30, VALIDATE: 40, SCALE: 50 }
    expect(stageTimes(timed('build', all, null), NOW)).toEqual({ start: null, plan: 10, test: 20, build: 30, check: 40, ship: 50 })
    expect(stageTimes(timed('start', all, 5000), NOW)).toEqual({ start: null, plan: 10, test: 20, build: 30, check: 40, ship: 50 })
  })
  test('a station with no entry has no time, unless it is the current one and counting', () => {
    expect(stageTimes(timed('build', { SHAPE: 10 }, null), NOW)).toEqual({ start: null, plan: 10, test: null, build: null, check: null, ship: null })
    expect(stageTimes(timed('build', { SHAPE: 10 }, 5000), NOW)).toEqual({ start: null, plan: 10, test: null, build: 5, check: null, ship: null })
  })
  test('a row from an older loop, with neither field, has no times at all', () => {
    for (const station of STATIONS) {
      expect(Object.values(stageTimes(lane(station), NOW)).every(t => t === null)).toBe(true)
      expect(isCounting(lane(station))).toBe(false)
    }
  })
  test('the current step adds the time since it began, by the clock it is given, floored and never below 0', () => {
    const counting = timed('build', { SHAPE: 10, BUILD: 30 }, 42_000)
    expect(stageTimes(counting, NOW).build).toBe(72)
    expect(stageTimes(counting, NOW + 999).build).toBe(72)
    expect(stageTimes(counting, NOW + 1000).build).toBe(73)
    // Only the current step counts.
    expect(stageTimes(counting, NOW + 60_000).plan).toBe(10)
    expect(stageTimes(counting, NOW + 60_000).test).toBeNull()
    // A step begun after the clock's now adds nothing.
    expect(stageTimes(timed('build', { BUILD: 30 }, -60_000), NOW).build).toBe(30)
  })
  test("a step_started that doesn't read as a time adds nothing", () => {
    const odd: Lane = { row: row({ step_seconds: { BUILD: 30 }, step_started: 'soon' }), station: 'build', walk: null }
    expect(stageTimes(odd, NOW).build).toBe(30)
  })
  test('a lane counts when it is not walking out, is past the start, and its step has begun', () => {
    expect(isCounting(timed('build', {}, 1000))).toBe(true)
    expect(isCounting(timed('build', {}, 1000, { from: 1, to: 3, start: NOW, end: NOW + 820 }))).toBe(true)
    expect(isCounting(timed('start', {}, 1000))).toBe(false)
    expect(isCounting(timed('build', {}, null))).toBe(false)
    expect(isCounting(timed('ship', {}, 1000, OUT))).toBe(false)
  })
  test('a lane walking out shows its times with nothing counting', () => {
    const leaving = timed('ship', { BUILD: 300, SCALE: 4 }, 1000, OUT)
    expect(stageTimes(leaving, NOW)).toEqual({ start: null, plan: null, test: null, build: 300, check: null, ship: 4 })
    expect(stageTimes(leaving, NOW + 60_000)).toEqual(stageTimes(leaving, NOW))
    expect(timeRowOf(laneCells(leaving, 72, NOW + 600), 72)).toEqual(timeRowOf(laneCells(leaving, 72, NOW), 72))
    // Its current stage is ship, in ship's colour.
    expect(timeRowOf(laneCells(leaving, 72, NOW), 72)[labelAt(5, 72)]![1]).toBe(ACCENT.ship)
  })
  test("the other surfaces draw 3 columns for each of the pane's, from 64 to 240", () => {
    expect(svgColumns(42)).toBe(126)
    expect(svgColumns(10)).toBe(64)
    expect(svgColumns(200)).toBe(240)
    expect(svgColumns(50.3)).toBe(151)
    expect(svgColumns(Number.NaN)).toBe(64)
    expect(svgColumns(Number.POSITIVE_INFINITY)).toBe(64)
  })
  test("on a terminal each time is in the lane's 4th row, from where its station's name starts, in its colour", () => {
    const columns = 72
    const counting = timed('build', { SHAPE: 90, TEST: 3900, BUILD: 0 }, 42_000)
    const times = timeRowOf(laneCells(counting, columns, NOW), columns)
    const head = textOf(decode(headCells([counting], columns)))
    const expected: [string, number][] = [['—', DARK.dim], ['1m', DARK.tool], ['1h05', DARK.tool], ['42s', ACCENT.build], ['—', DARK.dim], ['—', DARK.dim]]
    expected.forEach(([text, colour], i) => {
      const at = labelAt(i, columns)
      expect(head.slice(at, at + STATIONS[i]!.length)).toBe(STATIONS[i]!)
      expect(textOf(times.slice(at, at + text.length))).toBe(text)
      for (const [, fg, bg] of times.slice(at, at + text.length)) expect([fg, bg]).toEqual([colour, 0x01000000])
    })
    // The rest of the row is blank.
    expect(times.filter(([code]) => code !== 0x20).length).toBe(expected.reduce((n, [text]) => n + text.length, 0))
    // And a light theme uses its own.
    const light = timeRowOf(laneCells(counting, columns, NOW, LIGHT), columns)
    expect([light[labelAt(0, columns)]![1], light[labelAt(1, columns)]![1]]).toEqual([LIGHT.dim, LIGHT.tool])
  })
  test('a time that would reach the next station is cut, leaving a blank column before it', () => {
    const columns = 42
    const times = timeRowOf(laneCells(timed('build', { TEST: 36_300 }, null), columns, NOW), columns)
    const [test, build] = [labelAt(2, columns), labelAt(3, columns)]
    expect(textOf(times.slice(test, build - 1))).toBe('10h…')
    expect(times[build - 1]![0]).toBe(0x20)
    expect(textOf(times.slice(build, build + 1))).toBe('—')
    const long = { SHAPE: 363_000, TEST: 363_000, BUILD: 363_000, VALIDATE: 363_000, SCALE: 363_000 }
    for (let width = MIN_COLUMNS; width <= 120; width++) {
      const row4 = timeRowOf(laneCells(timed('build', long, null), width, NOW), width)
      for (let i = 1; i < STATIONS.length; i++) expect(row4[labelAt(i, width) - 1]![0]).toBe(0x20)
    }
  })
  test("the times leave the lane's 3 rows and the header as they were", () => {
    for (const station of STATIONS) {
      for (let ms = 0; ms < 2000; ms += 160) {
        const plain = decode(laneCells(lane(station), 72, NOW + ms)).slice(0, 72 * LANE_ROWS)
        const withTimes = decode(laneCells(timed(station, { SHAPE: 5, BUILD: 7 }, 3000), 72, NOW + ms)).slice(0, 72 * LANE_ROWS)
        expect(withTimes).toEqual(plain)
      }
    }
    expect(headCells([timed('build', { BUILD: 7 }, 3000)], 72)).toBe(headCells([lane('build')], 72))
  })
  test("a lane's Svg names each station at y 9 and gives its time at y 13, as of the drawing", () => {
    const columns = 126
    const counting = timed('build', { SHAPE: 90, TEST: 3900, BUILD: 0 }, 42_000)
    const at = (now: number) => svgTexts(laneSvg(counting, now, DARK, columns))
    const times: [string, number][] = [['—', DARK.dim], ['1m', DARK.tool], ['1h05', DARK.tool], ['42s', ACCENT.build], ['—', DARK.dim], ['—', DARK.dim]]
    expect(at(NOW)).toEqual(STATIONS.flatMap((station, i): [number, number, string, string][] => [
      [labelAt(i, columns), 9, hexOf(station === 'build' ? ACCENT.build : DARK.dim), station],
      [labelAt(i, columns), 13, hexOf(times[i]![1]), times[i]![0]],
    ]))
    expect(at(NOW + 60_000).find(([x, y]) => y === 13 && x === labelAt(3, columns))![3]).toBe('1m')
  })
  test('an Svg drawn wider works out every place at that width', () => {
    const source = laneSvg(lane('build'), NOW, DARK, 126)
    expect(/<svg[^>]*>/.exec(source)![0]).toBe('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 126 14">')
    expect(source).toContain(`<g transform="translate(${svgOf(stationX(3, 126) - 1)} 0)">`)
    expect(source).toContain(`<circle cx="${svgOf(stationX(5, 126))}"`)
    expect(headSvg([], DARK, 126)).toBe(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 126 4">${
      STATIONS.map((station, i) => `<text x="${labelAt(i, 126)}" y="3" font-family="monospace" font-size="2.6" fill="${hexOf(DARK.dim)}">${station}</text>`).join('')}</svg>`)
  })
  test('an Svg drawn mid-walk starts its slide where the figure is, for the walk\'s time left', () => {
    const walk = { from: 1, to: 3, start: NOW, end: NOW + 820 }
    const source = laneSvg({ row: row({}), station: 'build', walk }, NOW + 410, DARK, 126)
    const values = /type="translate" values="([^"]+)" dur="410ms" fill="freeze"/.exec(source)![1]!.split(';')
    near(Number(values[0]!.split(' ')[0]), walkLeft(walk, 126, NOW + 410) - (stationX(3, 126) - 1), 0.01)
    expect(values[values.length - 1]).toBe('0 0')
  })
})

group('the scene', () => {
  test('no status file comes first, even with a live lock', () => {
    expect(scene(look({ status: null })).message).toBe('No loop has run here yet.')
    expect(scene(null).message).toBe('No loop has run here yet.')
  })
  test('with no live lock there are no figures, even for rows left at working', () => {
    const seen = look({ isLive: false, status: { issues: [row({})] } })
    expect(scene(seen)).toEqual({ message: "The loop isn't running.", rows: [] })
  })
  test('with nothing working it says so', () => {
    expect(scene(look({ status: { issues: [row({ state: 'pr' })] } })).message).toBe('Nothing being built right now.')
  })
  test('working rows come in issue-number order, and others are left out', () => {
    const issues = [row({ number: 9 }), row({ number: 3 }), row({ number: 5, state: 'blocked' })]
    expect(scene(look({ status: { issues } })).rows.map(r => r.number)).toEqual([3, 9])
  })
})

group('the copied helpers', () => {
  test('the status file: a bad one is none, and a row without a number is dropped', () => {
    expect(parseStatus(null)).toBeNull()
    expect(parseStatus('{not json')).toBeNull()
    expect(parseStatus(JSON.stringify({ issues: [{ title: 'no number' }, { number: 4, title: 'T', step: 'BUILD', state: 'working', round: 2, pr: 'x' }] })))
      .toEqual({ issues: [{ number: 4, title: 'T', step: 'BUILD', state: 'working', round: 2 }] })
  })
  test("the lock's pid", () => {
    expect(lockPid('4242\n')).toBe(4242)
    expect(lockPid('nonsense')).toBeNull()
  })
  test('a clip cuts with an ellipsis', () => {
    expect(clip('abcdef', 4)).toBe('abc…')
    expect(clip('abc', 4)).toBe('abc')
  })
  test('the root is the nearest folder holding the script', async () => {
    const exists = async (path: string) => path === '/h/starter/scripts/loop.py'
    expect(await findRoot('/h/starter/projects/acme', exists)).toBe('/h/starter')
    expect(await findRoot('/elsewhere', exists)).toBeNull()
  })
})
