import { describe as group, expect, test } from 'claude-code/testing'

import { ACTS, BOX_PIXELS, FIGURE_MARK, FIGURE_PALETTE, FLOOR, FRAME_MS, FURNITURE, GUTTER, LAYOUTS, NOTHING, STATIONS, TEXT_BG, TEXT_FG, WALK, clip, findRoot, floorAlt, floorCells, floorSvg, layoutFor, legend, legendFit, lockPid, numberText, parseStatus, place, positionAt, roundText, scene, showsFloor, spotAt, stationOf, stepLine, word } from './logic'
import type { LayoutName, Station } from './logic'
import type { Row, Seen } from '../types'

const NOW = 1_800_000_000_000
const row = (over: Partial<Row>): Row => ({ number: 1, title: 'A job', step: 'BUILD', state: 'working', round: 1, ...over })
const look = (over: Partial<Seen>): Seen => ({ status: { issues: [] }, isLive: true, ...over })
const reading = (...issues: Row[]): Seen => look({ status: { issues } })
const ALL_FRAMES = [...Object.values(ACTS).flat(), WALK]

// The cells back from a Raster's base64, as [code point, foreground, background].
function decode(text: string): [number, number, number][] {
  const bytes = Uint8Array.from(atob(text), c => c.charCodeAt(0))
  const view = new DataView(bytes.buffer)
  const out: [number, number, number][] = []
  for (let i = 0; i < bytes.length; i += 12) out.push([view.getUint32(i, true), view.getUint32(i + 4, true), view.getUint32(i + 8, true)])
  return out
}

// A floor's text cells as lines, every pixel cell a space.
function textOf(cells: string, columns: number): string[] {
  const decoded = decode(cells)
  const lines: string[] = []
  for (let i = 0; i < decoded.length; i += columns) {
    lines.push(decoded.slice(i, i + columns).map(([code]) => (code === 0x2580 ? ' ' : String.fromCodePoint(code))).join(''))
  }
  return lines
}

group('a step, its station and its word', () => {
  test('each step goes to its station and has its word', () => {
    const steps: [string, Station, string][] = [
      ['SHAPE', 'planning', 'planning'], ['TEST', 'tests', 'writing tests'], ['BUILD', 'workshop', 'building'],
      ['VALIDATE', 'review', 'checking'], ['SCALE', 'dock', 'opening the pull request'],
    ]
    for (const [step, station, text] of steps) {
      expect(stationOf(step)).toBe(station)
      expect(word(step)).toBe(text)
    }
  })
  test('an empty step is starting, at the door', () => {
    expect(word('')).toBe('starting')
    expect(stationOf('')).toBe('door')
  })
  test('an unknown step is lowercased as written, at the door', () => {
    expect(word('DEPLOY')).toBe('deploy')
    expect(stationOf('DEPLOY')).toBe('door')
  })
  test("a step named like an object's own property is still unknown", () => {
    expect(word('constructor')).toBe('constructor')
    expect(stationOf('constructor')).toBe('door')
  })
  test('a zero round says nothing, and any other says its number', () => {
    expect(roundText(0)).toBe('')
    expect(roundText(2)).toBe('round 2')
    expect(stepLine(row({ step: 'BUILD', round: 2 }))).toBe('building, round 2')
    expect(stepLine(row({ step: 'SHAPE', round: 0 }))).toBe('planning')
  })
})

group('the layouts', () => {
  for (const name of ['wide', 'compact'] as LayoutName[]) {
    const layout = LAYOUTS[name]
    test(`${name}: every box sits inside the floor`, () => {
      for (const station of STATIONS) {
        const box = layout.boxes[station]
        expect(box.x).toBeGreaterThan(-1)
        expect(box.y).toBeGreaterThan(-1)
        expect(box.x + layout.boxColumns).toBeLessThan(layout.columns + 1)
        expect(box.y + BOX_PIXELS).toBeLessThan(layout.rows * 2 + 1)
      }
    })
    test(`${name}: each station's box touches the next along the path`, () => {
      const step = layout.boxColumns + 2
      for (let i = 1; i < STATIONS.length; i++) {
        const a = layout.boxes[STATIONS[i - 1]!]
        const b = layout.boxes[STATIONS[i]!]
        expect(Math.abs(a.x - b.x) / step + Math.abs(a.y - b.y) / BOX_PIXELS).toBe(1)
      }
    })
    test(`${name}: a spot's figure and its 4-digit number fit its box`, () => {
      for (const spot of layout.spots) expect(spot + 6).toBeLessThan(layout.boxColumns + 1)
    })
  }
  test('the wide floor is 64 by 24, door to tests along the top and workshop to dock back along the bottom', () => {
    const { columns, rows, boxes, spots } = LAYOUTS.wide
    expect([columns, rows]).toEqual([64, 24])
    expect(spots).toEqual([0, 7, 14])
    expect(STATIONS.map(s => [boxes[s].x, boxes[s].y])).toEqual([[0, 0], [22, 0], [44, 0], [44, 24], [22, 24], [0, 24]])
  })
  test('the compact floor is 32 by 36, snaking down', () => {
    const { columns, rows, boxes, spots } = LAYOUTS.compact
    expect([columns, rows]).toEqual([32, 36])
    expect(spots).toEqual([0, 7])
    expect(STATIONS.map(s => [boxes[s].x, boxes[s].y])).toEqual([[0, 0], [17, 0], [17, 24], [0, 24], [0, 48], [17, 48]])
  })
  test('the width picks the floor, at each edge', () => {
    expect(layoutFor(64)).toBe('wide')
    expect(layoutFor(63)).toBe('compact')
    expect(layoutFor(32)).toBe('compact')
    expect(layoutFor(31)).toBeNull()
  })
})

group('the drawings', () => {
  test('every furniture grid is 13 by 6, each pixel naming a colour in its palette', () => {
    for (const station of STATIONS) {
      const { grid, palette, name } = FURNITURE[station]
      expect(name).toBe(station)
      expect(grid.length).toBe(6)
      for (const line of grid) {
        expect(line.length).toBe(13)
        for (const pixel of line) expect(palette[pixel]).toBeDefined()
      }
    }
  })
  test('every act frame and the WALK frame is 6 by 8, each pixel naming a colour in the palette', () => {
    for (const frame of ALL_FRAMES) {
      expect(frame.length).toBe(8)
      for (const line of frame) {
        expect(line.length).toBe(6)
        for (const pixel of line) expect(FIGURE_PALETTE[pixel]).toBeDefined()
      }
    }
  })
  test('the door has one frame and every other act two to four', () => {
    expect(ACTS.door.length).toBe(1)
    for (const station of STATIONS.filter(s => s !== 'door')) {
      expect(ACTS[station].length).toBeGreaterThan(1)
      expect(ACTS[station].length).toBeLessThan(5)
    }
  })
  test('each frame of an act differs from the one before, last to first included', () => {
    for (const station of STATIONS.filter(s => s !== 'door')) {
      const frames = ACTS[station]
      frames.forEach((frame, i) => expect(frame.join()).not.toBe(frames[(i + 1) % frames.length]!.join()))
    }
  })
  test('FIGURE_MARK is at column 2 of row 1 of every frame, and nowhere else in any', () => {
    for (const frame of ALL_FRAMES) {
      frame.forEach((line, y) => {
        for (let x = 0; x < line.length; x++) expect(FIGURE_PALETTE[line[x]!] === FIGURE_MARK).toBe(x === 2 && y === 1)
      })
    }
  })
  test('nothing else on the floor uses FIGURE_MARK', () => {
    expect(Object.values(FIGURE_PALETTE).filter(colour => colour === FIGURE_MARK).length).toBe(1)
    for (const station of STATIONS) expect(Object.values(FURNITURE[station].palette)).not.toContain(FIGURE_MARK)
    for (const colour of [FLOOR, GUTTER, TEXT_FG, TEXT_BG]) expect(colour).not.toBe(FIGURE_MARK)
  })
})

group('the spots', () => {
  const spots = (name: LayoutName, seen: Seen) => place(name, seen, null, NOW).figures.map(f => [f.row.number, f.station, f.spot])
  const four = reading(row({ number: 9 }), row({ number: 3 }), row({ number: 7 }), row({ number: 5 }))
  test('wide: issues take a station\'s three spots in number order, the rest hidden', () => {
    expect(spots('wide', four)).toEqual([[3, 'workshop', 0], [5, 'workshop', 1], [7, 'workshop', 2], [9, 'workshop', null]])
    expect(textOf(floorCells(place('wide', four, null, NOW), NOW), 64).join('\n')).toContain('workshop +1')
  })
  test('compact: two spots, so two are hidden', () => {
    expect(spots('compact', four)).toEqual([[3, 'workshop', 0], [5, 'workshop', 1], [7, 'workshop', null], [9, 'workshop', null]])
    expect(textOf(floorCells(place('compact', four, null, NOW), NOW), 32).join('\n')).toContain('workshop +2')
  })
  test('an unknown step is placed at the door', () => {
    expect(spots('wide', reading(row({ step: 'DEPLOY' })))).toEqual([[1, 'door', 0]])
  })
  test('the rows a scene leaves out take no spot', () => {
    expect(spots('wide', reading(row({ state: 'blocked' })))).toEqual([])
    expect(spots('wide', look({ isLive: false, status: { issues: [row({})] } }))).toEqual([])
  })
})

group('the walks', () => {
  const first = (seen: Seen, name: LayoutName = 'wide') => place(name, seen, null, NOW)
  const planning = reading(row({ number: 12, step: 'SHAPE' }))
  const tests = reading(row({ number: 12, step: 'TEST' }))
  test('a walk runs straight from the old spot to the new over 1000 ms', () => {
    const walk = place('wide', tests, first(planning), NOW).figures[0]!.walk!
    expect(walk).toEqual({ from: { x: 22, y: 8 }, to: { x: 44, y: 8 }, start: NOW, end: NOW + 1000 })
    expect(positionAt(walk, NOW)).toEqual({ x: 22, y: 8 })
    expect(positionAt(walk, NOW + 500)).toEqual({ x: 33, y: 8 })
    expect(positionAt(walk, NOW + 1000)).toEqual({ x: 44, y: 8 })
    expect(positionAt(walk, NOW + 5000)).toEqual({ x: 44, y: 8 })
  })
  test('no previous placement walks nobody, as after a reload', () => {
    const placement = place('wide', tests, null, NOW)
    expect(placement.figures[0]!.walk).toBeNull()
    expect(placement.outs).toEqual([])
    expect(place('wide', reading(row({ number: 12, state: 'pr' })), null, NOW).outs).toEqual([])
  })
  test('the same spot walks nobody', () => {
    expect(place('wide', planning, first(planning), NOW + 2000).figures[0]!.walk).toBeNull()
  })
  test('a walk under way on an unchanged spot keeps its record, and a finished one is dropped', () => {
    const walking = place('wide', tests, first(planning), NOW)
    expect(place('wide', tests, walking, NOW + 400).figures[0]!.walk).toEqual(walking.figures[0]!.walk)
    expect(place('wide', tests, walking, NOW + 1000).figures[0]!.walk).toBeNull()
  })
  test('a new walk starts from the previous placement\'s spot', () => {
    const walking = place('wide', tests, first(planning), NOW)
    const again = place('wide', reading(row({ number: 12, step: 'BUILD' })), walking, NOW + 400).figures[0]!.walk!
    expect(again.from).toEqual(spotAt(LAYOUTS.wide, 'tests', 0))
    expect(again.to).toEqual(spotAt(LAYOUTS.wide, 'workshop', 0))
    expect(again.end).toBe(NOW + 1400)
  })
  test('spots shifting at a station walks the figures that moved', () => {
    const two = reading(row({ number: 5, step: 'SHAPE' }), row({ number: 12, step: 'SHAPE' }))
    const walk = place('wide', reading(row({ number: 12, step: 'SHAPE' })), first(two), NOW).figures[0]!.walk!
    expect(walk.from).toEqual(spotAt(LAYOUTS.wide, 'planning', 1))
    expect(walk.to).toEqual(spotAt(LAYOUTS.wide, 'planning', 0))
  })
  test('an issue missing from the previous read walks in from the door\'s first spot', () => {
    const empty = first(reading())
    expect(place('wide', tests, empty, NOW).figures[0]!.walk!.from).toEqual(spotAt(LAYOUTS.wide, 'door', 0))
  })
  test('one arriving at the door\'s first spot has nowhere to walk', () => {
    expect(place('wide', reading(row({ step: '' })), first(reading()), NOW).figures[0]!.walk).toBeNull()
  })
  test('each layout walks between its own spots', () => {
    const walk = place('compact', tests, first(planning, 'compact'), NOW).figures[0]!.walk!
    expect(walk.from).toEqual({ x: 17, y: 8 })
    expect(walk.to).toEqual({ x: 17, y: 32 })
  })
  test('a hidden issue that gains a spot appears there without walking', () => {
    const four = [1, 2, 3, 4].map(number => row({ number }))
    const next = place('wide', reading(...four.slice(1)), first(reading(...four)), NOW)
    expect(next.figures.map(f => f.spot)).toEqual([0, 1, 2])
    expect(next.figures[2]!.row.number).toBe(4)
    expect(next.figures[2]!.walk).toBeNull()
  })
  test('one whose new station has no spot for it is not drawn walking', () => {
    const full = [1, 2, 3].map(number => row({ number }))
    const before = first(reading(...full, row({ number: 8, step: 'SHAPE' })))
    const next = place('wide', reading(...full, row({ number: 8, step: 'BUILD' })), before, NOW)
    expect(next.figures[3]!.spot).toBeNull()
    expect(next.figures[3]!.walk).toBeNull()
    expect(floorSvg(next, NOW)).not.toContain('<animateTransform')
  })
})

group('walking out', () => {
  const working = reading(row({ number: 12, step: 'BUILD', round: 2 }))
  const opened = reading(row({ number: 12, step: 'BUILD', round: 2, state: 'pr' }))
  const before = place('wide', working, null, NOW)
  test('a row gone to pr walks from its spot to the door\'s first spot', () => {
    const { figures, outs } = place('wide', opened, before, NOW)
    expect(figures).toEqual([])
    expect(outs[0]!.walk).toEqual({ from: spotAt(LAYOUTS.wide, 'workshop', 0), to: spotAt(LAYOUTS.wide, 'door', 0), start: NOW, end: NOW + 1000 })
  })
  test('its legend line says it\'s opening the pull request, keeping its round, until the walk ends', () => {
    const placement = place('wide', opened, before, NOW)
    expect(legend(placement, NOW + 999).map(l => l.line)).toEqual(['#12 A job · opening the pull request, round 2'])
    expect(legend(placement, NOW + 1000)).toEqual([])
  })
  test('it holds back only the one message, and only until the walk ends', () => {
    const placement = place('wide', opened, before, NOW)
    expect(showsFloor(NOTHING, placement, NOW + 999)).toBe(true)
    expect(showsFloor(NOTHING, placement, NOW + 1000)).toBe(false)
    expect(showsFloor("The loop isn't running.", placement, NOW + 500)).toBe(false)
    expect(showsFloor(null, placement, NOW + 5000)).toBe(true)
  })
  test('it takes no spot from a station', () => {
    const two = place('wide', reading(row({ number: 12 }), row({ number: 13 })), null, NOW)
    const next = place('wide', reading(row({ number: 12, state: 'pr' }), row({ number: 13 })), two, NOW)
    expect(next.figures[0]!.spot).toBe(0)
    expect(next.outs.length).toBe(1)
  })
  test('a later read keeps its walk until it ends', () => {
    const placement = place('wide', opened, before, NOW)
    expect(place('wide', opened, placement, NOW + 500).outs).toEqual(placement.outs)
    expect(place('wide', opened, placement, NOW + 1000).outs).toEqual([])
  })
  test('a hidden row going to pr is gone at that read', () => {
    const four = [1, 2, 3, 4].map(number => row({ number }))
    const next = place('wide', reading(...four.slice(0, 3), row({ number: 4, state: 'pr' })), place('wide', reading(...four), null, NOW), NOW)
    expect(next.outs).toEqual([])
    expect(legend(next, NOW).map(l => l.number)).toEqual([1, 2, 3])
  })
  test('a row leaving working any other way is gone with no walk', () => {
    expect(place('wide', reading(row({ number: 12, state: 'blocked' })), before, NOW).outs).toEqual([])
    expect(place('wide', reading(), before, NOW).outs).toEqual([])
    expect(place('wide', look({ isLive: false, status: opened.status }), before, NOW).outs).toEqual([])
  })
})

group('the legend', () => {
  test('one line per issue in number order, hidden ones too, the round left off at 0', () => {
    const issues = [row({ number: 4, title: 'Four', round: 0 }), row({ number: 1, title: 'One' }), row({ number: 2 }), row({ number: 3 })]
    const lines = legend(place('wide', reading(...issues), null, NOW), NOW)
    expect(lines.map(l => l.number)).toEqual([1, 2, 3, 4])
    expect(lines[0]!.line).toBe('#1 One · building, round 1')
    expect(lines[3]!.line).toBe('#4 Four · building')
  })
  test('all the lines that fit', () => {
    expect(legendFit(3, 3)).toBe(3)
    expect(legendFit(1, 1)).toBe(1)
  })
  test('otherwise as many as leave one row for "and n more"', () => {
    expect(legendFit(3, 2)).toBe(1)
    expect(legendFit(5, 4)).toBe(3)
  })
  test('never fewer than one', () => {
    expect(legendFit(2, -6)).toBe(1)
    expect(legendFit(1, -6)).toBe(1)
  })
  test('every line when the height is absent or not a number', () => {
    expect(legendFit(5)).toBe(5)
    expect(legendFit(5, Number.NaN)).toBe(5)
    expect(legendFit(5, Number.POSITIVE_INFINITY)).toBe(5)
  })
})

group('the Raster cells', () => {
  const issues = [row({ number: 12345, step: 'SHAPE' }), row({ number: 13, step: 'BUILD' })]
  for (const [name, columns, rows] of [['wide', 64, 24], ['compact', 32, 36]] as [LayoutName, number, number][]) {
    const cells = floorCells(place(name, reading(...issues), null, NOW), NOW)
    test(`${name}: decode to ${columns} by ${rows} triplets of half blocks or printable ASCII`, () => {
      const decoded = decode(cells)
      expect(decoded.length).toBe(columns * rows)
      for (const [code, fg, bg] of decoded) {
        expect(code === 0x2580 || (code >= 0x20 && code <= 0x7e)).toBe(true)
        expect(fg).toBeLessThan(0x01000000)
        expect(bg).toBeLessThan(0x01000000)
      }
    })
    test(`${name}: every station's name and each issue number reads as text, cut to 4 digits`, () => {
      const text = textOf(cells, columns).join('\n')
      for (const station of STATIONS) expect(text).toContain(station)
      expect(text).toContain('2345')
      expect(text).not.toContain('12345')
      expect(text).toContain('13')
    })
    test(`${name}: one FIGURE_MARK per figure, in no text cell`, () => {
      const marks = decode(cells).filter(([, fg, bg]) => fg === FIGURE_MARK || bg === FIGURE_MARK)
      expect(marks.length).toBe(2)
      for (const [code] of marks) expect(code).toBe(0x2580)
    })
  }
  test('a number has its last 4 digits, with no #', () => {
    expect(numberText(12345)).toBe('2345')
    expect(numberText(13)).toBe('13')
  })
  test("a cell's top pixel is its foreground and its bottom pixel its background", () => {
    const cells = decode(floorCells(place('wide', reading(row({ number: 1, step: 'SHAPE' })), null, NOW), NOW))
    // The mark is at pixel (24, 9): the bottom half of cell row 4.
    const cell = cells[4 * 64 + 24]!
    expect(cell[2]).toBe(FIGURE_MARK)
    expect(cell[1]).toBe(FIGURE_PALETTE.h)
  })
  test('the frame comes from the clock, and wraps', () => {
    const placement = place('wide', reading(row({ step: 'BUILD' })), null, NOW)
    const n = ACTS.workshop.length
    expect(floorCells(placement, NOW + FRAME_MS)).not.toBe(floorCells(placement, NOW))
    expect(floorCells(placement, NOW + FRAME_MS - 1)).toBe(floorCells(placement, NOW))
    expect(floorCells(placement, NOW + n * FRAME_MS)).toBe(floorCells(placement, NOW))
  })
  test('the door stands still', () => {
    const placement = place('wide', reading(row({ step: '' })), null, NOW)
    expect(floorCells(placement, NOW + FRAME_MS)).toBe(floorCells(placement, NOW))
  })
  test('a walker passing over a name leaves no stray letters, and walkers draw on top', () => {
    // At the top of the door's box, the walker covers the cells of the door's name.
    const walk = { from: { x: 0, y: 0 }, to: { x: 0, y: 8 }, start: NOW, end: NOW + 1000 }
    const placement = { layout: 'wide' as const, figures: [], outs: [{ row: row({ number: 77 }), walk }] }
    const text = textOf(floorCells(placement, NOW), 64)
    expect(text[0]!.slice(0, 6)).toBe('      ')
    expect(text.join('\n')).toContain('77')
  })
})

group('the Svg', () => {
  const planning = reading(row({ number: 12, step: 'SHAPE' }))
  const tests = reading(row({ number: 12, step: 'TEST' }))
  const walking = place('wide', tests, place('wide', planning, null, NOW), NOW)
  const walkingUse = /<use href="#walk"[^>]*>(.*?)<\/use>/
  const actUse = /<use href="#act-tests"[^>]*>(.*?)<\/use>/
  test('it is 64 by 48 in its viewBox, and the acts are defined once in its defs', () => {
    const source = floorSvg(place('wide', planning, null, NOW), NOW)
    expect(source).toContain('viewBox="0 0 64 48"')
    expect(source).toContain('width="256"')
    expect(source).toContain('height="192"')
    const defs = source.slice(source.indexOf('<defs>'), source.indexOf('</defs>'))
    for (const station of STATIONS) expect(defs.split(`id="act-${station}"`).length).toBe(2)
    expect(defs.split('id="walk"').length).toBe(2)
  })
  test('a walking figure has its outer translate at its new spot and an animateTransform from old less new', () => {
    const source = floorSvg(walking, NOW)
    expect(source).toContain('<g transform="translate(44 8)">')
    expect(source).toContain('<animateTransform attributeName="transform" type="translate" from="-22 0" to="0 0" dur="1000ms" fill="freeze"/>')
  })
  test('drawn mid-walk, the animateTransform starts from where it is, over the time left', () => {
    expect(floorSvg(walking, NOW + 500)).toContain('from="-11 0" to="0 0" dur="500ms" fill="freeze"')
  })
  test('a walking figure\'s act shows without its <set>, hidden only for the walk\'s time left', () => {
    const source = floorSvg(walking, NOW + 250)
    const act = source.match(actUse)!
    expect(act[0]).not.toContain('visibility=')
    expect(act[0].split('>')[0]).not.toContain('display=')
    expect(act[1]).toBe('<set attributeName="display" to="none" dur="750ms"/>')
  })
  test('its WALK frame is the reverse: hidden without its <set>, shown for the time left', () => {
    const source = floorSvg(walking, NOW + 250)
    const walk = source.match(walkingUse)!
    expect(walk[0].split('>')[0]).toContain('visibility="hidden"')
    expect(walk[1]).toBe('<set attributeName="visibility" to="visible" dur="750ms"/>')
  })
  test('a figure not walking has none of these', () => {
    for (const source of [floorSvg(place('wide', planning, null, NOW), NOW), floorSvg(walking, NOW + 1000)]) {
      expect(source).not.toContain('<animateTransform')
      expect(source).not.toContain('<set ')
      expect(source).not.toContain('href="#walk"')
    }
  })
  test('no title or unknown step reaches the source or alt, only numbers and station names', () => {
    const secret = reading(row({ number: 12, title: 'Secret <title>', step: 'SECRET-STEP' }))
    const placement = place('wide', secret, null, NOW)
    for (const text of [floorSvg(placement, NOW), floorAlt(placement, NOW)]) {
      expect(text).not.toContain('Secret')
      expect(text.toLowerCase()).not.toContain('secret-step')
    }
    expect(floorAlt(placement, NOW)).toBe('Issue #12 at door')
  })
  test('alt names each figure\'s issue and station, walking out included', () => {
    const two = reading(row({ number: 12, step: 'SHAPE' }), row({ number: 13, step: 'BUILD' }))
    const next = place('wide', reading(row({ number: 12, state: 'pr' }), row({ number: 13, step: 'BUILD' })), place('wide', two, null, NOW), NOW)
    expect(floorAlt(next, NOW)).toBe('Issue #12 at door, Issue #13 at workshop')
  })
  test('with all 18 spots filled and two walking out it fits, one animateTransform a walker, and no script', () => {
    const steps = ['SHAPE', 'TEST', 'BUILD', 'VALIDATE', 'SCALE', '']
    const fill = (shift: number, start: number) => [0, 1, 2, 3, 4, 5].flatMap(s =>
      [0, 1, 2].map(i => row({ number: start + s * 3 + i, step: steps[(s + shift) % 6]! })))
    const before = place('wide', reading(...fill(0, 1)), null, NOW)
    // Every issue moves on a station. Two walk out of planning, and two new ones fill the spots at tests
    // that their moving on leaves.
    const moved = fill(1, 1).slice(2)
    const issues = [row({ number: 1, state: 'pr' }), row({ number: 2, state: 'pr' }), ...moved, row({ number: 500, step: 'TEST' }), row({ number: 501, step: 'TEST' })]
    const after = place('wide', reading(...issues), before, NOW)
    expect(after.figures.filter(f => f.spot !== null).length).toBe(18)
    expect(after.outs.length).toBe(2)
    const walkers = after.figures.filter(f => f.walk).length + 2
    const source = floorSvg(after, NOW)
    expect(source.length).toBeLessThan(131073)
    expect(source.split('<animateTransform').length - 1).toBe(walkers)
    expect(source).not.toContain('<script')
    expect(/\son\w*=/.test(source)).toBe(false)
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
