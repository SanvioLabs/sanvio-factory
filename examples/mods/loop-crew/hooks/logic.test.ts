import { describe as group, expect, test } from 'claude-code/testing'

import { ACCENT, ACTS, DARK, LANE_PIXELS, LANE_ROWS, LIGHT, MIN_COLUMNS, NOTHING, OUT_MS, RAIL_Y, RUN, STATIONS, SVG_COLUMNS, SVG_SCALE, boardColumns, clip, easeInOut, effectAt, findRoot, headCells, headSvg, inkFor, laneAlt, laneCells, laneFit, laneSvg, laneWords, lanesOf, lockPid, parseStatus, place, poseAt, roundText, scene, showsBoard, stationOf, stationX, stepLine, unitsAt, walkLeft, walkMs, walkingOut, word } from './logic'
import type { Lane, Station } from './logic'
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
      expect(cells.length).toBe(columns * LANE_ROWS)
      for (const [code] of cells) expect([0x20, 0x2580, 0x2584]).toContain(code)
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
  test(`a lane is ${SVG_COLUMNS} by 6 in its viewBox, drawn at ${SVG_SCALE} times that, smooth`, () => {
    expect(standing).toContain(`viewBox="0 0 ${SVG_COLUMNS} 6"`)
    expect(standing).toContain(`width="${SVG_COLUMNS * SVG_SCALE}" height="${6 * SVG_SCALE}"`)
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
  })
  test('the header names every station, busy ones in their colour', () => {
    const source = headSvg([lane('test')])
    for (const station of STATIONS) expect(source).toContain(`>${station}</text>`)
    expect(source).toContain(`fill="#${ACCENT.test.toString(16)}">test<`)
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
