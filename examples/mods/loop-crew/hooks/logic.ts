// The floor's decisions and drawings as plain functions, so they can be tested without a session.
import type { Row, Seen, Status } from '../types'

export const PROJECTS_DIR = '.loop/projects'
export const SCRIPT = 'scripts/loop.py'
export const FRAME_MS = 250

// The folder under the root holding one loop's files: the harness's, or a project's.
export function loopDir(project?: string): string {
  return project ? `${PROJECTS_DIR}/${project}` : '.loop'
}

const str = (v: unknown): string => (typeof v === 'string' ? v : '')
const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)

// The status file, or null when there's none or it can't be read. A row without a number is dropped.
export function parseStatus(text: string | null): Status | null {
  if (!text) return null
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return null
  }
  if (!raw || typeof raw !== 'object') return null
  const rows = (raw as Record<string, unknown>).issues
  const issues: Row[] = (Array.isArray(rows) ? rows : [])
    .filter((r): r is Record<string, unknown> => !!r && typeof r === 'object' && num((r as Record<string, unknown>).number) > 0)
    .map(r => ({ number: num(r.number), title: str(r.title), step: str(r.step), state: str(r.state), round: num(r.round) }))
  return { issues }
}

// The process id in the lock, or null when it isn't a number.
export function lockPid(text: string): number | null {
  const pid = Number.parseInt(text.trim(), 10)
  return Number.isInteger(pid) && pid > 0 ? pid : null
}

// Fit one line to the pane, with an ellipsis where it was cut.
export function clip(text: string, width: number): string {
  if (width < 2) return ''
  return text.length <= width ? text : text.slice(0, width - 1) + '…'
}

// The nearest folder at or above `from` that holds the loop script. None means no loop here.
export async function findRoot(from: string, exists: (path: string) => Promise<boolean>): Promise<string | null> {
  let dir = from.replace(/\/+$/, '')
  while (dir) {
    if (await exists(`${dir}/${SCRIPT}`)) return dir
    dir = dir.slice(0, dir.lastIndexOf('/'))
  }
  return null
}

const WORDS: Record<string, string> = {
  SHAPE: 'planning',
  TEST: 'writing tests',
  BUILD: 'building',
  VALIDATE: 'checking',
  SCALE: 'opening the pull request',
}

// What a step reads as. A step this doesn't know is shown lowercased, as written.
export function word(step: string): string {
  return Object.keys(WORDS).includes(step) ? WORDS[step]! : step.toLowerCase() || 'starting'
}

export function roundText(round: number): string {
  return round > 0 ? `round ${round}` : ''
}

// A legend line's words: building, round 2. The word alone at round 0.
export function stepLine(row: Row): string {
  return [word(row.step), roundText(row.round)].filter(Boolean).join(', ')
}

// What the pane says when nothing is being built, which a walk-out holds back.
export const NOTHING = 'Nothing being built right now.'

// What the pane says instead of figures, or the figures, in issue-number order. The lock is the truth
// about running: rows left at working by a killed run draw nothing.
export function scene(seen: Seen | null): { message: string | null; rows: Row[] } {
  if (!seen?.status) return { message: 'No loop has run here yet.', rows: [] }
  if (!seen.isLive) return { message: "The loop isn't running.", rows: [] }
  const rows = seen.status.issues.filter(r => r.state === 'working').sort((a, b) => a.number - b.number)
  return rows.length ? { message: null, rows } : { message: NOTHING, rows: [] }
}

export type Station = 'door' | 'planning' | 'tests' | 'workshop' | 'review' | 'dock'

// The order along the loop's path.
export const STATIONS: Station[] = ['door', 'planning', 'tests', 'workshop', 'review', 'dock']

const STEP_STATIONS: Record<string, Station> = { SHAPE: 'planning', TEST: 'tests', BUILD: 'workshop', VALIDATE: 'review', SCALE: 'dock' }

// Where a step is worked. An empty step and any step this doesn't know wait at the door.
export function stationOf(step: string): Station {
  return Object.keys(STEP_STATIONS).includes(step) ? STEP_STATIONS[step]! : 'door'
}

export const FLOOR = 0x1a1d23
export const GUTTER = 0x101216
export const TEXT_FG = 0xd8dce3
export const TEXT_BG = FLOOR
// One pixel of every figure, its eye, and nothing else on the floor: how a test finds a figure.
export const FIGURE_MARK = 0x2d1b3e

// A station's name and its furniture: 13 by 6 pixels, each a key in the palette, '.' the open floor.
export type Furniture = { name: string; palette: Record<string, number>; grid: string[] }

export const FURNITURE: Record<Station, Furniture> = {
  door: {
    name: 'door',
    palette: { '.': FLOOR, d: 0x6b4a2b, p: 0x9a6b45, y: 0xe0c060 },
    grid: [
      '..ddddddddd..',
      '..dpppppppd..',
      '..dpppppppd..',
      '..dppppppyd..',
      '..dpppppppd..',
      '..dpppppppd..',
    ],
  },
  planning: {
    name: 'planning',
    palette: { '.': FLOOR, p: 0xe8e0c8, t: 0x8a6a45, w: 0x5f4a30 },
    grid: [
      '.............',
      '...ppp..pp...',
      '.ttttttttttt.',
      '.ttttttttttt.',
      '..w.......w..',
      '..w.......w..',
    ],
  },
  tests: {
    name: 'tests',
    palette: { '.': FLOOR, g: 0x3a9d5d, r: 0xc0392b, b: 0x7a7f88 },
    grid: [
      '...g...r.....',
      '..ggg.rrr..g.',
      '..ggg.rrr.ggg',
      '.bbbbbbbbbbb.',
      '.b.........b.',
      '.b.........b.',
    ],
  },
  workshop: {
    name: 'workshop',
    palette: { '.': FLOOR, a: 0x5a6068, m: 0xa8b0b8, n: 0xd9c9a3, o: 0x8a6a45 },
    grid: [
      '.....a.......',
      '....aaa...mm.',
      '..nn.a....mm.',
      '.ooooooooooo.',
      '.o.........o.',
      '.o.........o.',
    ],
  },
  review: {
    name: 'review',
    palette: { '.': FLOOR, k: 0x4c72b0, l: 0xf2f2ee, q: 0x6b4a2b },
    grid: [
      '..kkk........',
      '..kkk....ll..',
      '...k.....ll..',
      '.qqqqqqqqqqq.',
      '.q.......qqq.',
      '.q.......qqq.',
    ],
  },
  dock: {
    name: 'dock',
    palette: { '.': FLOOR, x: 0xc49a6c, t: 0x8a6a45, y: 0x5a6068 },
    grid: [
      '.xxx.........',
      '.xtx.xxx.....',
      '.xxx.xtx.xxx.',
      '.xxx.xxx.xtx.',
      'yyyyyyyyyyyyy',
      'y.y.y.y.y.y.y',
    ],
  },
}

// The figures' colours, tools included. '.' is the open floor, so a figure standing there shows no box.
export const FIGURE_PALETTE: Record<string, number> = {
  '.': FLOOR,
  M: FIGURE_MARK,
  h: 0x8a5a2b,
  s: 0xe8b88a,
  b: 0x4c72b0,
  l: 0x3f5f8f,
  f: 0x9a6b45,
  w: 0x8a6a45,
  d: 0xd9c9a3,
  g: 0x3a9d5d,
  m: 0xa8b0b8,
  a: 0x5a6068,
  c: 0x8fd3e8,
  x: 0xc49a6c,
}

// A station's act: its frames in turn, each 6 by 8 pixels in the figures' palette. M is only ever at
// column 2 of row 1, counted from 0. A frame differs from the one before it, last to first included.
export const ACTS: Record<Station, string[][]> = {
  door: [
    ['.hhh..', '.sMs..', 'sbbbs.', 'sbbbs.', '.bbb..', '.l.l..', '.l.l..', '.f.f..'],
  ],
  planning: [
    ['.hhh..', '.sMs..', '.bbb..', '.bbbs.', '.bbwww', '.l.lw.', '.l.lw.', '.f.fw.'],
    ['.hhh..', '.sMs..', '.bbbs.', '.bbb..', '.bbwww', '.l.lw.', '.l.lw.', '.f.fw.'],
  ],
  tests: [
    ['.hhh..', '.sMs..', '.bbb..', '.bbbsd', '.bbddd', '.l.ww.', '.l.w.w', '.f.w.w'],
    ['.hhh..', '.sMs..', '.bbb..', '.bbbsg', '.bbddd', '.l.ww.', '.l.w.w', '.f.w.w'],
    ['.hhh..', '.sMs..', '.bbb..', '.bbsgg', '.bbddd', '.l.ww.', '.l.w.w', '.f.w.w'],
  ],
  workshop: [
    ['.hhh.m', '.sMs.w', '.bbbsw', '.bbb..', '.bbb..', '.l.l..', '.l.l.a', '.f.faa'],
    ['.hhh..', '.sMs..', '.bbbwm', '.bbb.m', '.bbb..', '.l.l..', '.l.l.a', '.f.faa'],
    ['.hhh..', '.sMs..', '.bbb..', '.bbbs.', '.bbb.w', '.l.l.m', '.l.l.a', '.f.faa'],
  ],
  review: [
    ['.hhhcc', '.sMscc', '.bbbw.', '.bbs..', '.bbb..', '.l.l..', '.l.l..', '.f.f..'],
    ['.hhh..', '.sMscc', '.bbbcc', '.bbsw.', '.bbb..', '.l.l..', '.l.l..', '.f.f..'],
  ],
  dock: [
    ['.hhh..', '.sMs..', '.bbb..', '.bbsxx', '.bbbxx', '.lll..', '.l.l..', '.f.f..'],
    ['.hhh..', '.sMs..', '.bbb..', '.bbsxx', '.bbbxx', '.lll..', 'l...l.', 'f...f.'],
  ],
}

// The one frame a figure shows from the start of a walk to its end.
export const WALK = ['.hhh..', '.sMs..', '.bbb..', 'sbbbs.', '.bbb..', '.ll...', 'l..l..', 'f..f..']

export const FIGURE_PIXELS = 8
export const BOX_PIXELS = 24
// A box's rows, in pixels from its top: its name, then furniture, then figures, then their numbers.
const FURNITURE_TOP = 2
const FIGURE_TOP = 8
export const WALK_MS = 1000

export type Point = { x: number; y: number }
export type LayoutName = 'wide' | 'compact'

// A floor's size in cells, and its boxes and their spots in pixels: 1 a column, 2 a cell row.
export type Layout = { columns: number; rows: number; boxColumns: number; spots: number[]; boxes: Record<Station, Point> }

export const LAYOUTS: Record<LayoutName, Layout> = {
  wide: {
    columns: 64,
    rows: 24,
    boxColumns: 20,
    spots: [0, 7, 14],
    boxes: {
      door: { x: 0, y: 0 },
      planning: { x: 22, y: 0 },
      tests: { x: 44, y: 0 },
      workshop: { x: 44, y: 24 },
      review: { x: 22, y: 24 },
      dock: { x: 0, y: 24 },
    },
  },
  compact: {
    columns: 32,
    rows: 36,
    boxColumns: 15,
    spots: [0, 7],
    boxes: {
      door: { x: 0, y: 0 },
      planning: { x: 17, y: 0 },
      workshop: { x: 0, y: 24 },
      tests: { x: 17, y: 24 },
      review: { x: 0, y: 48 },
      dock: { x: 17, y: 48 },
    },
  },
}

// Which floor a terminal this wide draws. Null: too narrow for one, so the legend stands alone.
export function layoutFor(bodyColumns: number): LayoutName | null {
  if (bodyColumns >= LAYOUTS.wide.columns) return 'wide'
  return bodyColumns >= LAYOUTS.compact.columns ? 'compact' : null
}

export function spotAt(layout: Layout, station: Station, spot: number): Point {
  const box = layout.boxes[station]
  return { x: box.x + layout.spots[spot]!, y: box.y + FIGURE_TOP }
}

export type Walk = { from: Point; to: Point; start: number; end: number }
// `spot` null is hidden behind its station's +<n>, which isn't the same as missing: a hidden issue
// that gains a spot appears there, and a missing one walks in from the door.
export type Placed = { row: Row; station: Station; spot: number | null; walk: Walk | null }
export type WalkOut = { row: Row; walk: Walk }
export type Placement = { layout: LayoutName; figures: Placed[]; outs: WalkOut[] }

const walkFrom = (from: Point, to: Point, now: number): Walk => ({ from, to, start: now, end: now + WALK_MS })

function arrival(layout: Layout, old: Placed | undefined, station: Station, spot: number | null, now: number): Walk | null {
  if (spot === null) return null
  const to = spotAt(layout, station, spot)
  if (!old) {
    const door = spotAt(layout, 'door', 0)
    return door.x === to.x && door.y === to.y ? null : walkFrom(door, to, now)
  }
  if (old.spot === null) return null
  if (old.station === station && old.spot === spot) return old.walk && now < old.walk.end ? old.walk : null
  return walkFrom(spotAt(layout, old.station, old.spot), to, now)
}

// Each issue's spot for a new read, and who walks. No previous placement (the read that opens or
// switches the pane, or the first after a reload) walks nobody. A walk under way on an unchanged spot
// goes on, and a new one starts from the previous placement's spot.
export function place(name: LayoutName, seen: Seen | null, previous: Placement | null, now: number): Placement {
  const layout = LAYOUTS[name]
  const before = new Map((previous?.figures ?? []).map(f => [f.row.number, f]))
  const taken = new Map<Station, number>()
  const figures = scene(seen).rows.map((row): Placed => {
    const station = stationOf(row.step)
    const next = taken.get(station) ?? 0
    taken.set(station, next + 1)
    const spot = next < layout.spots.length ? next : null
    return { row, station, spot, walk: previous ? arrival(layout, before.get(row.number), station, spot, now) : null }
  })
  const read = seen?.status && seen.isLive ? seen.status.issues : []
  const opening = new Map(read.filter(r => r.state === 'pr').map(r => [r.number, r]))
  const door = spotAt(layout, 'door', 0)
  const outs: WalkOut[] = []
  for (const out of previous?.outs ?? []) {
    if (now < out.walk.end && opening.has(out.row.number)) outs.push(out)
  }
  // A hidden row has no spot to walk from, so it's gone at this read.
  for (const old of previous?.figures ?? []) {
    const row = opening.get(old.row.number)
    if (row && old.spot !== null) outs.push({ row: { ...row, step: 'SCALE' }, walk: walkFrom(spotAt(layout, old.station, old.spot), door, now) })
  }
  return { layout: name, figures, outs }
}

// A walk's position at this moment, in pixels and not rounded. Rounding is for the Raster alone.
export function positionAt(walk: Walk, now: number): Point {
  const t = Math.min(1, Math.max(0, (now - walk.start) / (walk.end - walk.start)))
  return { x: walk.from.x + (walk.to.x - walk.from.x) * t, y: walk.from.y + (walk.to.y - walk.from.y) * t }
}

const isWalking = (walk: Walk | null, now: number): walk is Walk => !!walk && now < walk.end

export function walkingOut(placement: Placement, now: number): WalkOut[] {
  return placement.outs.filter(out => now < out.walk.end)
}

// Whether the floor shows at this moment: when there's no message, and over the one message a walk-out
// holds back. The other two messages still win.
export function showsFloor(message: string | null, placement: Placement, now: number): boolean {
  return message === null || (message === NOTHING && walkingOut(placement, now).length > 0)
}

// What stands on the floor and what walks on it, each in number order.
type Drawn = { number: number; station: Station; spot: Point; walk: Walk | null }

function onFloor(placement: Placement, now: number): { standing: Drawn[]; walking: Drawn[] } {
  const layout = LAYOUTS[placement.layout]
  const standing: Drawn[] = []
  const walking: Drawn[] = []
  for (const f of placement.figures) {
    if (f.spot === null) continue
    const spot = spotAt(layout, f.station, f.spot)
    if (isWalking(f.walk, now)) walking.push({ number: f.row.number, station: f.station, spot, walk: f.walk })
    else standing.push({ number: f.row.number, station: f.station, spot, walk: null })
  }
  for (const out of walkingOut(placement, now)) walking.push({ number: out.row.number, station: 'door', spot: out.walk.to, walk: out.walk })
  walking.sort((a, b) => a.number - b.number)
  return { standing, walking }
}

// A station's name and how many issues it hides.
function title(placement: Placement, station: Station): string {
  const hidden = placement.figures.filter(f => f.station === station && f.spot === null).length
  return hidden ? `${FURNITURE[station].name} +${hidden}` : FURNITURE[station].name
}

// The last 4 digits of an issue's number, with no #.
export function numberText(number: number): string {
  return String(number).slice(-4)
}

// One line per working issue, hidden ones too, and one per issue walking out, in number order.
export function legend(placement: Placement, now: number): { number: number; line: string }[] {
  return [...placement.figures.map(f => f.row), ...walkingOut(placement, now).map(out => out.row)]
    .sort((a, b) => a.number - b.number)
    .map(row => ({ number: row.number, line: `#${row.number} ${row.title} · ${stepLine(row)}` }))
}

// How many of `count` legend lines to show in `room` rows: all that fit, or as many as leave a row for
// "and n more", and never fewer than one. A height that isn't there shows them all.
export function legendFit(count: number, room?: number): number {
  if (room === undefined || !Number.isFinite(room)) return count
  return count <= room ? count : Math.min(count, Math.max(1, room - 1))
}

const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

// The cells as a Raster takes them: little-endian u32s, as padded base64.
export function encode(cells: Uint32Array): string {
  const bytes = new Uint8Array(cells.length * 4)
  const view = new DataView(bytes.buffer)
  cells.forEach((word, i) => view.setUint32(i * 4, word, true))
  let out = ''
  for (let i = 0; i < bytes.length; i += 3) {
    const [a, b, c] = [bytes[i] ?? 0, bytes[i + 1] ?? 0, bytes[i + 2] ?? 0]
    const n = (a << 16) | (b << 8) | c
    out += ALPHABET[(n >> 18) & 63]! + ALPHABET[(n >> 12) & 63]!
    out += i + 1 < bytes.length ? ALPHABET[(n >> 6) & 63]! : '='
    out += i + 2 < bytes.length ? ALPHABET[n & 63]! : '='
  }
  return out
}

const UPPER_HALF = 0x2580

// A painting: each cell's top and bottom pixel, and the character it shows instead, if any.
type Canvas = { columns: number; rows: number; top: Uint32Array; bottom: Uint32Array; text: Uint32Array }

// Painting a pixel clears its cell's text, so a walker passing over a name leaves no stray letters.
function paintPixel(canvas: Canvas, x: number, y: number, colour: number): void {
  const row = Math.floor(y / 2)
  if (x < 0 || x >= canvas.columns || row < 0 || row >= canvas.rows) return
  const cell = row * canvas.columns + x
  canvas.text[cell] = 0
  if (y % 2 === 0) canvas.top[cell] = colour
  else canvas.bottom[cell] = colour
}

function paintGrid(canvas: Canvas, grid: string[], palette: Record<string, number>, x: number, y: number): void {
  grid.forEach((line, dy) => {
    for (let dx = 0; dx < line.length; dx++) paintPixel(canvas, x + dx, y + dy, palette[line[dx]!] ?? FLOOR)
  })
}

function paintText(canvas: Canvas, text: string, column: number, row: number): void {
  for (let i = 0; i < text.length; i++) {
    const x = column + i
    if (x >= 0 && x < canvas.columns && row >= 0 && row < canvas.rows) canvas.text[row * canvas.columns + x] = text.charCodeAt(i)
  }
}

// One figure and its number, the number on the cell row under it.
function paintFigure(canvas: Canvas, frame: string[], number: number, at: Point): void {
  const [x, y] = [Math.round(at.x), Math.round(at.y)]
  paintGrid(canvas, frame, FIGURE_PALETTE, x, y)
  paintText(canvas, numberText(number), x, Math.ceil((y + FIGURE_PIXELS) / 2))
}

// The whole floor as it stands at this moment, as a Raster's cells: open floor, furniture, names,
// standing figures with their numbers, then walking figures with theirs on top. An act's frame comes
// from the clock, so a redraw and a blit at one moment agree. Text cells use fixed colours, never ones
// from the pixels beneath.
export function floorCells(placement: Placement, now: number): string {
  const layout = LAYOUTS[placement.layout]
  const size = layout.columns * layout.rows
  const canvas: Canvas = {
    columns: layout.columns,
    rows: layout.rows,
    top: new Uint32Array(size).fill(GUTTER),
    bottom: new Uint32Array(size).fill(GUTTER),
    text: new Uint32Array(size),
  }
  for (const station of STATIONS) {
    const box = layout.boxes[station]
    for (let y = 0; y < BOX_PIXELS; y++) {
      for (let x = 0; x < layout.boxColumns; x++) paintPixel(canvas, box.x + x, box.y + y, FLOOR)
    }
  }
  for (const station of STATIONS) {
    const box = layout.boxes[station]
    const { grid, palette } = FURNITURE[station]
    paintGrid(canvas, grid, palette, box.x, box.y + FURNITURE_TOP)
  }
  for (const station of STATIONS) {
    const box = layout.boxes[station]
    paintText(canvas, title(placement, station), box.x, box.y / 2)
  }
  const { standing, walking } = onFloor(placement, now)
  for (const figure of standing) {
    const frames = ACTS[figure.station]
    paintFigure(canvas, frames[Math.floor(now / FRAME_MS) % frames.length]!, figure.number, figure.spot)
  }
  for (const figure of walking) paintFigure(canvas, WALK, figure.number, positionAt(figure.walk!, now))
  const out = new Uint32Array(size * 3)
  for (let i = 0; i < size; i++) {
    if (canvas.text[i]) out.set([canvas.text[i]!, TEXT_FG, TEXT_BG], i * 3)
    else out.set([UPPER_HALF, canvas.top[i]!, canvas.bottom[i]!], i * 3)
  }
  return encode(out)
}

const hex = (colour: number): string => `#${colour.toString(16).padStart(6, '0')}`
const svgNumber = (value: number): string => String(Math.round(value * 1000) / 1000)

// A grid's pixels as rects, a run of one colour on a row being one rect.
function rects(grid: string[], palette: Record<string, number>, ox = 0, oy = 0): string {
  let out = ''
  grid.forEach((line, y) => {
    for (let x = 0; x < line.length;) {
      let end = x + 1
      while (line[end] === line[x]) end++
      out += `<rect x="${ox + x}" y="${oy + y}" width="${end - x}" height="1" fill="${hex(palette[line[x]!] ?? FLOOR)}"/>`
      x = end
    }
  })
  return out
}

// A frame's turn in the loop of n, as a discrete animation of its visibility.
function turn(i: number, n: number): string {
  const times = [...(i > 0 ? [0] : []), i / n, ...(i + 1 < n ? [(i + 1) / n] : [])]
  const values = [...(i > 0 ? ['hidden'] : []), 'visible', ...(i + 1 < n ? ['hidden'] : [])]
  return `<animate attributeName="visibility" calcMode="discrete" values="${values.join(';')}" ` +
    `keyTimes="${times.map(t => t.toFixed(4)).join(';')}" dur="${n * FRAME_MS}ms" repeatCount="indefinite"/>`
}

// An act, defined once: a group per frame, shown in turn with SMIL. Where SMIL doesn't run the first
// frame stands still, and a one-frame act has nothing to animate.
function actDefinition(station: Station): string {
  const frames = ACTS[station]
  const groups = frames.map((frame, i) =>
    `<g${i > 0 ? ' visibility="hidden"' : ''}>${rects(frame, FIGURE_PALETTE)}${frames.length > 1 ? turn(i, frames.length) : ''}</g>`)
  return `<g id="act-${station}">${groups.join('')}</g>`
}

const svgText = (text: string, x: number, y: number): string =>
  `<text x="${x}" y="${y}" font-family="monospace" font-size="2" fill="${hex(TEXT_FG)}">${text}</text>`

// A figure: an outer group at its spot around an inner one. A walking figure's inner group slides in
// from where it is now and shows WALK for the walk's time left, then its act. Its act is hidden with
// `display`, because a frame's own animated visibility would override a hidden parent. Without SMIL
// nothing moves and the act shows, at the spot.
function figureSvg(figure: Drawn, now: number): string {
  const number = svgText(numberText(figure.number), 0, FIGURE_PIXELS + 1.7)
  const act = `#act-${figure.station}`
  const open = `<g transform="translate(${figure.spot.x} ${figure.spot.y})"><g>`
  if (!figure.walk) return `${open}<use href="${act}"/>${number}</g></g>`
  const left = `${svgNumber(figure.walk.end - now)}ms`
  const at = positionAt(figure.walk, now)
  const from = `${svgNumber(at.x - figure.spot.x)} ${svgNumber(at.y - figure.spot.y)}`
  return `${open}<animateTransform attributeName="transform" type="translate" from="${from}" to="0 0" dur="${left}" fill="freeze"/>` +
    `<use href="#walk" visibility="hidden"><set attributeName="visibility" to="visible" dur="${left}"/></use>` +
    `<use href="${act}"><set attributeName="display" to="none" dur="${left}"/></use>` +
    `${number}</g></g>`
}

// The floor as one Svg document, as it stands at this moment. The only text from the status file in
// it is issue numbers.
export function floorSvg(placement: Placement, now: number): string {
  const layout = LAYOUTS[placement.layout]
  const width = layout.columns
  const height = layout.rows * 2
  const defs = `<defs>${STATIONS.map(actDefinition).join('')}<g id="walk">${rects(WALK, FIGURE_PALETTE)}</g></defs>`
  const stations = STATIONS.map(station => {
    const box = layout.boxes[station]
    const { grid, palette } = FURNITURE[station]
    return `<rect x="${box.x}" y="${box.y}" width="${layout.boxColumns}" height="${BOX_PIXELS}" fill="${hex(FLOOR)}"/>` +
      rects(grid, palette, box.x, box.y + FURNITURE_TOP) +
      svgText(title(placement, station), box.x, box.y + 1.7)
  })
  const { standing, walking } = onFloor(placement, now)
  const figures = [...standing, ...walking].map(figure => figureSvg(figure, now))
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width * 4}" height="${height * 4}" shape-rendering="crispEdges">` +
    `<rect width="${width}" height="${height}" fill="${hex(GUTTER)}"/>${defs}${stations.join('')}${figures.join('')}</svg>`
}

// What the Svg says for a reader who can't see it: each figure's issue and station, by station name
// and never the raw step, which is status-file text when loop-crew doesn't know it.
export function floorAlt(placement: Placement, now: number): string {
  const { standing, walking } = onFloor(placement, now)
  const figures = [...standing, ...walking].sort((a, b) => a.number - b.number)
  return figures.length ? figures.map(f => `Issue #${f.number} at ${FURNITURE[f.station].name}`).join(', ') : 'An empty work floor'
}
