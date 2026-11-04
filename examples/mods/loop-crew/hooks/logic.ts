// The board's decisions and drawings as plain functions, so they can be tested without a session.
import type { Row, Seen, Status } from '../types'

export const PROJECTS_DIR = '.loop/projects'
export const SCRIPT = 'scripts/loop.py'

// The folder under the root holding one loop's files: the harness's, or a project's.
export function loopDir(project?: string): string {
  return project ? `${PROJECTS_DIR}/${project}` : '.loop'
}

const str = (v: unknown): string => (typeof v === 'string' ? v : '')
const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
const has = (o: object, key: string): boolean => Object.prototype.hasOwnProperty.call(o, key)

// The steps whose time a lane shows, each with the station it's worked at.
const TIMED_STEPS = ['SHAPE', 'TEST', 'BUILD', 'VALIDATE', 'SCALE']

// A row's time fields, each only when the row has it. Only the timed steps with a time of 0 or more are
// kept, and a step_started that doesn't read as a time is null.
function timeFields(r: Record<string, unknown>): Pick<Row, 'step_seconds' | 'step_started'> {
  const out: Pick<Row, 'step_seconds' | 'step_started'> = {}
  if (has(r, 'step_seconds')) {
    const raw = r.step_seconds
    const seconds: Record<string, number> = {}
    if (raw && typeof raw === 'object') {
      for (const step of TIMED_STEPS) {
        const value = has(raw, step) ? (raw as Record<string, unknown>)[step] : undefined
        if (typeof value === 'number' && Number.isFinite(value) && value >= 0) seconds[step] = value
      }
    }
    out.step_seconds = seconds
  }
  if (has(r, 'step_started')) {
    const raw = r.step_started
    out.step_started = typeof raw === 'string' && !Number.isNaN(Date.parse(raw)) ? raw : null
  }
  return out
}

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
    .map(r => ({ number: num(r.number), title: str(r.title), step: str(r.step), state: str(r.state), round: num(r.round), ...timeFields(r) }))
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

// A lane's step words: building, round 2. The word alone at round 0.
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

export type Station = 'start' | 'plan' | 'test' | 'build' | 'check' | 'ship'

// The order along the loop's path, which is the order left to right.
export const STATIONS: Station[] = ['start', 'plan', 'test', 'build', 'check', 'ship']
const LAST = STATIONS.length - 1

const STEP_STATIONS: Record<string, Station> = { SHAPE: 'plan', TEST: 'test', BUILD: 'build', VALIDATE: 'check', SCALE: 'ship' }

// Where a step is worked. An empty step and any step this doesn't know wait at the start.
export function stationOf(step: string): Station {
  return Object.keys(STEP_STATIONS).includes(step) ? STEP_STATIONS[step]! : 'start'
}

// Each station's colour, cool to warm along the path, so a lane's lit rail shows how far it has come.
export const ACCENT: Record<Station, number> = {
  start: 0x94a3b8,
  plan: 0xa78bfa,
  test: 0x22d3ee,
  build: 0xfbbf24,
  check: 0x34d399,
  ship: 0xf472b6,
}
export const accentText = (station: Station): string => hex(ACCENT[station])

const PASS = 0x34d399

// What the board draws on. Fades blend toward `bg`, the pixels themselves have no background.
export type Ink = { bg: number; head: number; tool: number; dim: number; rail: number }
export const DARK: Ink = { bg: 0x0f1218, head: 0xe6edf3, tool: 0x9aa4b2, dim: 0x5b6472, rail: 0x38404c }
export const LIGHT: Ink = { bg: 0xffffff, head: 0x1f2933, tool: 0x6b7280, dim: 0x8a94a3, rail: 0xc3c9d2 }

// The session's theme, by what its name says. One that doesn't say, `auto` among them, reads as dark.
export const inkFor = (theme: unknown): Ink => (typeof theme === 'string' && theme.includes('light') ? LIGHT : DARK)

// A lane is 6 pixels tall, 3 cell rows. A figure stands on the rail along its bottom pixel row.
export const LANE_ROWS = 3
export const LANE_PIXELS = LANE_ROWS * 2
export const RAIL_Y = LANE_PIXELS - 1
// A figure is 3 pixels wide, a tool reaching one more, and its middle column is where it stands.
const FIGURE_CENTRE = 1
// A station's work plays in the air to the right of its figure, so the last station keeps that room.
const EFFECT_OFFSET = 5
const RIGHT_ROOM = 13
// Under this the header's station names run into each other, and the pane shows only the words.
export const MIN_COLUMNS = 42
const MAX_COLUMNS = 120
// How wide the desktop, the editor and the phone draw, at the least and the most. The surface scales the
// drawing to the pane, so this is its shape, not its size.
export const SVG_COLUMNS = 64
const SVG_MAX_COLUMNS = 240

// How wide a terminal this wide draws its board. Null: too narrow for one.
export function boardColumns(bodyColumns: number): number | null {
  return bodyColumns >= MIN_COLUMNS ? Math.min(bodyColumns, MAX_COLUMNS) : null
}

// How wide the other surfaces draw the header and the lanes for a pane this many columns wide: three
// times that, between 64 and 240. A width that isn't a number draws 64.
export function svgColumns(bodyColumns: number): number {
  if (!Number.isFinite(bodyColumns)) return SVG_COLUMNS
  return Math.min(SVG_MAX_COLUMNS, Math.max(SVG_COLUMNS, Math.round(bodyColumns * 3)))
}

// The middle of a station, or of a place between two, in pixels from the left.
export function stationX(units: number, columns: number): number {
  return 2 + units * ((columns - RIGHT_ROOM) / LAST)
}

// A figure in 3 or 4 by 5 pixels: h its head, a its body in the colour of where it is, t a tool. The head is
// the only pixel in `ink.head` on a lane, which is how a test finds a figure.
const FIGURE_COLOURS = (ink: Ink, suit: number): Record<string, number> => ({ h: ink.head, a: suit, t: ink.tool })

// A pose and how long it holds. A station's poses play in turn, so a hammer winds up slowly and lands fast.
export type Pose = { ms: number; frame: string[] }

const STAND = ['.h.', 'aaa', '.a.', 'a.a', 'a.a']
export const ACTS: Record<Station, Pose[]> = {
  start: [{ ms: 1000, frame: STAND }],
  plan: [
    { ms: 520, frame: ['.h..', 'aaat', '.a..', 'a.a.', 'a.a.'] },
    { ms: 320, frame: ['.h..', 'aaa.', '.a.t', 'a.a.', 'a.a.'] },
  ],
  test: [
    { ms: 520, frame: ['.h..', 'aaa.', '.a.t', 'a.a.', 'a.a.'] },
    { ms: 260, frame: ['.h.t', 'aaa.', '.a..', 'a.a.', 'a.a.'] },
  ],
  build: [
    { ms: 340, frame: ['.h.t', 'aa.t', '.a..', 'a.a.', 'a.a.'] },
    { ms: 90, frame: ['.h..', 'aatt', '.a..', 'a.a.', 'a.a.'] },
    { ms: 160, frame: ['.h..', 'aaa.', '.a.t', 'a.a.', 'a.a.'] },
  ],
  check: [
    { ms: 700, frame: ['.h.t', 'aaa.', '.a..', 'a.a.', 'a.a.'] },
    { ms: 700, frame: ['.h..', 'aaat', '.a..', 'a.a.', 'a.a.'] },
  ],
  ship: [
    { ms: 260, frame: ['.h..', 'aaat', '.a.t', 'a.a.', 'a.a.'] },
    { ms: 260, frame: ['.h..', 'aaat', '.a.t', '.a..', 'a.a.'] },
  ],
}

// Two strides, facing right with the tool held out in front. A figure going back along the path is
// their mirror image, the tool in front the other way.
export const RUN: string[][] = [
  ['.h.', 'aat', '.a.', 'a.a', 'a.a'],
  ['.h.', 'aat', '.a.', '.a.', '.a.'],
]
const STRIDE_MS = 110

const mirror = (frame: string[]): string[] => frame.map(line => [...line].reverse().join(''))
const cycle = (poses: Pose[]): number => poses.reduce((total, pose) => total + pose.ms, 0)

// The pose showing this far into its act.
export function poseAt(poses: Pose[], ms: number): number {
  let left = ((ms % cycle(poses)) + cycle(poses)) % cycle(poses)
  for (let i = 0; i < poses.length; i++) {
    if (left < poses[i]!.ms) return i
    left -= poses[i]!.ms
  }
  return 0
}

export type Px = { x: number; y: number; colour: number; alpha: number }

const clamp01 = (t: number): number => Math.min(1, Math.max(0, t))
// Symmetric, so the middle of a walk is the middle of its way.
export const easeInOut = (t: number): number => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)
const easeOut = (t: number): number => 1 - (1 - t) ** 3
const easeIn = (t: number): number => t * t * t
const fadeEnd = (ms: number, length: number, last = 280): number => clamp01((length - ms) / last)

const EFFECT_CYCLE: Record<Station, number> = { start: 1200, plan: 1680, test: 2000, build: 2400, check: 1400, ship: 1440 }

// Two lines of a plan being ruled in. Every effect stays in the 5 rows above the rail, mostly in its
// station's colour, so the work reads at a glance and nothing flickers.
function planEffect(ms: number): Px[] {
  const out: Px[] = []
  const fade = fadeEnd(ms, EFFECT_CYCLE.plan)
  ;[[1, 6, 0], [3, 4, 420]].forEach(([y, length, delay]) => {
    const drawn = Math.floor(easeOut(clamp01((ms - delay!) / 520)) * length!)
    for (let x = 0; x < drawn; x++) out.push({ x, y: y!, colour: ACCENT.plan, alpha: fade })
  })
  return out
}

// Four checks turning green one after another.
function testEffect(ms: number, ink: Ink): Px[] {
  const out: Px[] = []
  const fade = fadeEnd(ms, EFFECT_CYCLE.test)
  for (let k = 0; k < 4; k++) {
    const [left, top] = [(k % 2) * 3, Math.floor(k / 2) * 3]
    const colour = ms < 200 + k * 320 ? ink.rail : PASS
    for (const [dx, dy] of [[0, 0], [1, 0], [0, 1], [1, 1]]) out.push({ x: left + dx!, y: top + dy!, colour, alpha: fade })
  }
  return out
}

// Bricks dropping into a stack of three.
function buildEffect(ms: number): Px[] {
  const out: Px[] = []
  const fade = fadeEnd(ms, EFFECT_CYCLE.build)
  ;[[0, 4], [3, 4], [1, 2]].forEach(([left, bottom], k) => {
    const at = ms - (160 + k * 520)
    if (at < 0) return
    const y = bottom! - Math.round((1 - easeOut(clamp01(at / 200))) * 4)
    for (let dx = 0; dx < 2; dx++) for (const dy of [0, -1]) {
      if (y + dy >= 0) out.push({ x: left! + dx, y: y + dy, colour: ACCENT.build, alpha: fade })
    }
  })
  return out
}

// A page of three lines and a bar reading across and back.
function checkEffect(ms: number, ink: Ink): Px[] {
  const out: Px[] = []
  const t = ms / EFFECT_CYCLE.check
  const bar = Math.round((t < 0.5 ? easeInOut(t * 2) : easeInOut(2 - t * 2)) * 5)
  for (const y of [0, 2, 4]) for (let x = 0; x < 6; x++) out.push({ x, y, colour: x === bar ? ACCENT.check : ink.rail, alpha: 1 })
  return out
}

// A parcel sliding off along the rail, then the next set down.
function shipEffect(ms: number): Px[] {
  const out: Px[] = []
  const go = clamp01(ms / 900)
  const place = ms < 900 ? Math.round(easeIn(go) * 4) : 0
  const alpha = ms < 900 ? (go < 0.8 ? 1 : clamp01((1 - go) / 0.2)) : clamp01((ms - 1100) / 300)
  for (let y = 2; y < 5; y++) for (let x = 0; x < 3; x++) out.push({ x: place + x, y, colour: ACCENT.ship, alpha })
  return out
}

// Three dots taking turns: waiting to begin.
function startEffect(ms: number): Px[] {
  return [0, 1, 2].map(i => {
    const wave = Math.sin(((ms / EFFECT_CYCLE.start) - i / 6) * Math.PI * 2)
    return { x: i * 2, y: 4, colour: ACCENT.start, alpha: 0.25 + 0.75 * Math.max(0, wave) }
  })
}

// What a station's work draws this far into its cycle, in pixels from where the work plays.
export function effectAt(station: Station, ms: number, ink: Ink): Px[] {
  const at = ((ms % EFFECT_CYCLE[station]) + EFFECT_CYCLE[station]) % EFFECT_CYCLE[station]
  const drawn = station === 'plan' ? planEffect(at) : station === 'test' ? testEffect(at, ink) : station === 'build' ? buildEffect(at)
    : station === 'check' ? checkEffect(at, ink) : station === 'ship' ? shipEffect(at) : startEffect(at)
  return drawn.filter(px => px.alpha > 0.01)
}

// A walk along a lane, in stations: 0 at the start, 5 at ship. Walking out, it goes past the board's edge.
export type Walk = { from: number; to: number; start: number; end: number; isOut?: boolean }
export type Placed = { row: Row; station: Station; walk: Walk | null }
export type WalkOut = { row: Row; walk: Walk }
export type Placement = { figures: Placed[]; outs: WalkOut[] }

// A longer way takes longer, but not proportionally: a figure speeds up, not dawdles.
export const walkMs = (from: number, to: number): number => Math.min(1500, 480 + 170 * Math.abs(to - from))
export const OUT_MS = 800

const indexOf = (station: Station): number => STATIONS.indexOf(station)

const walkFrom = (from: number, to: number, now: number): Walk => ({ from, to, start: now, end: now + walkMs(from, to) })

// A walk's place this moment, in stations, eased and not rounded.
export function unitsAt(walk: Walk, now: number): number {
  return walk.from + (walk.to - walk.from) * easeInOut(clamp01((now - walk.start) / (walk.end - walk.start)))
}

function arrival(old: Placed | undefined, station: Station, now: number): Walk | null {
  const to = indexOf(station)
  if (!old) return to === 0 ? null : walkFrom(0, to, now)
  if (old.station === station) return old.walk && now < old.walk.end ? old.walk : null
  // From where the figure is, so a walk overtaken by the next read carries on without a jump.
  return walkFrom(old.walk ? unitsAt(old.walk, now) : indexOf(old.station), to, now)
}

// Each issue's station for a new read, and who walks. No previous placement (the read that opens or
// switches the pane, or the first after a reload) walks nobody.
export function place(seen: Seen | null, previous: Placement | null, now: number): Placement {
  const before = new Map((previous?.figures ?? []).map(f => [f.row.number, f]))
  const figures = scene(seen).rows.map((row): Placed => {
    const station = stationOf(row.step)
    return { row, station, walk: previous ? arrival(before.get(row.number), station, now) : null }
  })
  const read = seen?.status && seen.isLive ? seen.status.issues : []
  const opening = new Map(read.filter(r => r.state === 'pr').map(r => [r.number, r]))
  const outs: WalkOut[] = (previous?.outs ?? []).filter(out => now < out.walk.end && opening.has(out.row.number))
  for (const old of previous?.figures ?? []) {
    const row = opening.get(old.row.number)
    if (!row) continue
    const from = old.walk ? unitsAt(old.walk, now) : indexOf(old.station)
    outs.push({ row: { ...row, step: 'SCALE' }, walk: { from, to: LAST, start: now, end: now + OUT_MS, isOut: true } })
  }
  return { figures, outs }
}

export function walkingOut(placement: Placement, now: number): WalkOut[] {
  return placement.outs.filter(out => now < out.walk.end)
}

// Whether the board shows at this moment: when there's no message, and over the one message a walk-out
// holds back. The other two messages still win.
export function showsBoard(message: string | null, placement: Placement, now: number): boolean {
  return message === null || (message === NOTHING && walkingOut(placement, now).length > 0)
}

// One issue's row on the board.
export type Lane = { row: Row; station: Station; walk: Walk | null }

export function lanesOf(placement: Placement, now: number): Lane[] {
  const out = walkingOut(placement, now).map((o): Lane => ({ row: o.row, station: 'ship', walk: o.walk }))
  return [...placement.figures, ...out].sort((a, b) => a.row.number - b.row.number)
}

// The step each station's time comes from. The start has none.
const STATION_STEPS: Record<Station, string | null> = { start: null, plan: 'SHAPE', test: 'TEST', build: 'BUILD', check: 'VALIDATE', ship: 'SCALE' }

// Whether a lane's current step is still being timed: not walking out, past the start, and started at a
// time Date.parse reads. A Row built in code can carry one it can't, and that one never counts.
export function isCounting(lane: Lane): boolean {
  const started = lane.row.step_started
  return !lane.walk?.isOut && lane.station !== 'start' && typeof started === 'string' && !Number.isNaN(Date.parse(started))
}

// Each station's time in seconds, or null for none. The current step, while it counts, adds the time
// since it began, as of `now`, in whole seconds and never below 0. A row from a loop that doesn't record
// times has none.
export function stageTimes(lane: Lane, now: number): Record<Station, number | null> {
  const seconds = lane.row.step_seconds ?? {}
  const started = isCounting(lane) ? Date.parse(lane.row.step_started!) : Number.NaN
  const out = {} as Record<Station, number | null>
  for (const station of STATIONS) {
    const step = STATION_STEPS[station]
    const spent = step !== null && has(seconds, step) && Number.isFinite(seconds[step]) ? seconds[step]! : null
    out[station] = station === lane.station && Number.isFinite(started)
      ? (spent ?? 0) + Math.max(0, Math.floor((now - started) / 1000))
      : spent
  }
  return out
}

// What no time reads as: an em dash, U+2014, written by its code so the source holds none.
const NO_TIME = String.fromCharCode(0x2014)

// A time as it reads: whole seconds under a minute, whole minutes under an hour, then hours and two-digit
// minutes, all floored. No time reads as a dash.
export function timeText(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return NO_TIME
  const whole = Math.max(0, Math.floor(seconds))
  if (whole < 60) return `${whole}s`
  if (whole < 3600) return `${Math.floor(whole / 60)}m`
  return `${Math.floor(whole / 3600)}h${String(Math.floor((whole % 3600) / 60)).padStart(2, '0')}`
}

// A time's colour: the current station's accent, the tool colour for any other with a time, and dim for none.
function timeColour(lane: Lane, station: Station, seconds: number | null, ink: Ink): number {
  if (seconds === null) return ink.dim
  return station === lane.station ? ACCENT[station] : ink.tool
}

// A lane's words: its number, its title cut to what's left of the width, and where it has got to, which
// is never cut here: a pane too narrow for it wraps it. No width leaves the title whole, for a surface
// that wraps.
export function laneWords(row: Row, width?: number): { number: string; title: string; status: string } {
  const number = `#${row.number}`
  const status = `· ${stepLine(row)}`
  const room = width === undefined ? row.title.length : width - number.length - status.length - 2
  return { number, title: clip(row.title, room), status }
}

// How many of `count` lanes fit in `room` rows, each taking `rows` and one row left for "and n more"
// when some don't fit. Never fewer than one. A height that isn't there shows them all.
export function laneFit(count: number, rows: number, room?: number): number {
  if (room === undefined || !Number.isFinite(room)) return count
  const all = Math.floor(room / rows)
  return count <= all ? count : Math.min(count, Math.max(1, Math.floor((room - 1) / rows)))
}

const DEFAULT_COLOUR = 0x01000000
const UPPER_HALF = 0x2580
const LOWER_HALF = 0x2584
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

function mix(a: number, b: number, t: number): number {
  const channel = (shift: number) => Math.round(((a >> shift) & 255) + (((b >> shift) & 255) - ((a >> shift) & 255)) * t)
  return (channel(16) << 16) | (channel(8) << 8) | channel(0)
}

// A painting of a lane: each pixel a colour, or -1 where nothing is, so the pane shows through.
type Canvas = { columns: number; pixels: Int32Array; ink: Ink }

function put(canvas: Canvas, x: number, y: number, colour: number, alpha = 1): void {
  if (x < 0 || x >= canvas.columns || y < 0 || y >= LANE_PIXELS || alpha <= 0) return
  const i = y * canvas.columns + x
  const under = canvas.pixels[i]!
  canvas.pixels[i] = alpha >= 1 ? colour : mix(under < 0 ? canvas.ink.bg : under, colour, alpha)
}

// The rail: lit in each station's colour up to `reached`, dashed beyond it, a node at every station.
function paintRail(canvas: Canvas, reached: number): void {
  const { columns, ink } = canvas
  const [first, last] = [Math.round(stationX(0, columns)), Math.round(stationX(LAST, columns))]
  const at = stationX(reached, columns)
  for (let x = first; x <= last; x++) {
    const units = ((x - first) / (last - first)) * LAST
    const below = Math.min(LAST, Math.floor(units))
    const colour = mix(ACCENT[STATIONS[below]!], ACCENT[STATIONS[Math.min(LAST, below + 1)]!], units - below)
    if (x <= at) put(canvas, x, RAIL_Y, colour)
    else if (x % 2 === 0) put(canvas, x, RAIL_Y, ink.rail)
  }
  STATIONS.forEach((station, i) => {
    const x = Math.round(stationX(i, columns))
    const colour = i <= reached ? ACCENT[station] : ink.rail
    for (const dx of [-1, 0, 1]) put(canvas, x + dx, RAIL_Y, colour)
    put(canvas, x, RAIL_Y - 1, colour)
  })
}

function paintFrame(canvas: Canvas, frame: string[], x: number, suit: number, alpha = 1): void {
  const colours = FIGURE_COLOURS(canvas.ink, suit)
  frame.forEach((line, dy) => {
    for (let dx = 0; dx < line.length; dx++) {
      const colour = colours[line[dx]!]
      if (colour !== undefined) put(canvas, x + dx, dy, colour, alpha)
    }
  })
}

const suitAt = (units: number): number => {
  const below = Math.max(0, Math.min(LAST, Math.floor(units)))
  return mix(ACCENT[STATIONS[below]!], ACCENT[STATIONS[Math.min(LAST, below + 1)]!], clamp01(units - below))
}

// Where a walk has its figure this moment, in pixels: its left edge, not rounded.
export function walkLeft(walk: Walk, columns: number, now: number): number {
  if (!walk.isOut) return stationX(unitsAt(walk, now), columns) - FIGURE_CENTRE
  const from = stationX(walk.from, columns) - FIGURE_CENTRE
  return from + (columns + 1 - from) * easeInOut(clamp01((now - walk.start) / (walk.end - walk.start)))
}

// A walking figure: its strides, in the colour of where it has got to.
function paintRunner(canvas: Canvas, lane: Lane, now: number): void {
  const walk = lane.walk!
  const left = walkLeft(walk, canvas.columns, now)
  const suit = walk.isOut ? ACCENT.ship : suitAt(unitsAt(walk, now))
  const stride = RUN[Math.floor((now - walk.start) / STRIDE_MS) % RUN.length]!
  paintFrame(canvas, walk.to < walk.from ? mirror(stride) : stride, Math.round(left), suit)
}

// The work at a station: the figure's pose and the work beside it.
function paintWorker(canvas: Canvas, lane: Lane, now: number): void {
  const left = Math.round(stationX(indexOf(lane.station), canvas.columns)) - FIGURE_CENTRE
  const phase = now + lane.row.number * 271
  const poses = ACTS[lane.station]
  // On a narrow board the work reaches the next station: it never covers that station's node.
  const nodes = new Set(STATIONS.map((_, i) => Math.round(stationX(i, canvas.columns))))
  for (const px of effectAt(lane.station, phase, canvas.ink)) {
    const x = left + EFFECT_OFFSET + px.x
    if (!(px.y === RAIL_Y - 1 && nodes.has(x))) put(canvas, x, px.y, px.colour, px.alpha)
  }
  paintFrame(canvas, poses[poseAt(poses, phase)]!.frame, left, ACCENT[lane.station])
}

const isRunning = (walk: Walk | null, now: number): walk is Walk => !!walk && now < walk.end

function paintLane(canvas: Canvas, lane: Lane, now: number): void {
  const running = isRunning(lane.walk, now)
  const reached = !running ? indexOf(lane.station) : lane.walk!.isOut ? LAST : unitsAt(lane.walk!, now)
  paintRail(canvas, reached)
  if (running) paintRunner(canvas, lane, now)
  else paintWorker(canvas, lane, now)
}

const canvasFor = (columns: number, ink: Ink): Canvas => ({ columns, ink, pixels: new Int32Array(columns * LANE_PIXELS).fill(-1) })

// One lane as it stands at this moment, as a Raster's cells: its 3 rows of half blocks, so each cell is
// two pixels, and the lower one where only the bottom pixel is painted, so the top keeps the pane's own
// background. Then a row of each station's time, under its name in the header.
export function laneCells(lane: Lane, columns: number, now: number, ink: Ink = DARK): string {
  const canvas = canvasFor(columns, ink)
  paintLane(canvas, lane, now)
  const out = new Uint32Array(columns * (LANE_ROWS + 1) * 3)
  out.set(timeCells(lane, columns, now, ink), columns * LANE_ROWS * 3)
  for (let row = 0; row < LANE_ROWS; row++) {
    for (let x = 0; x < columns; x++) {
      const top = canvas.pixels[row * 2 * columns + x]!
      const bottom = canvas.pixels[(row * 2 + 1) * columns + x]!
      const cell = (row * columns + x) * 3
      if (top < 0 && bottom < 0) out.set([0x20, DEFAULT_COLOUR, DEFAULT_COLOUR], cell)
      else if (top < 0) out.set([LOWER_HALF, bottom, DEFAULT_COLOUR], cell)
      else out.set([UPPER_HALF, top, bottom < 0 ? DEFAULT_COLOUR : bottom], cell)
    }
  }
  return encode(out)
}

// Which column a station's label starts at, under its node and kept on the board.
const labelColumn = (index: number, columns: number): number => Math.max(0, Math.round(stationX(index, columns)) - 2)

// A lane's row of times, as a Raster's cells: each station's from the column its name starts at in the
// header, cut so a blank column always comes before the next station's.
export function timeCells(lane: Lane, columns: number, now: number, ink: Ink = DARK): Uint32Array {
  const out = new Uint32Array(columns * 3)
  for (let x = 0; x < columns; x++) out.set([0x20, DEFAULT_COLOUR, DEFAULT_COLOUR], x * 3)
  const times = stageTimes(lane, now)
  STATIONS.forEach((station, index) => {
    const start = labelColumn(index, columns)
    const room = (index < LAST ? labelColumn(index + 1, columns) - 1 : columns) - start
    const colour = timeColour(lane, station, times[station], ink)
    ;[...clip(timeText(times[station]), room)].forEach((letter, i) => {
      if (start + i < columns) out.set([letter.codePointAt(0)!, colour, DEFAULT_COLOUR], (start + i) * 3)
    })
  })
  return out
}

// The header: the stations left to right, over their nodes, each in its colour while anyone is working
// there and dim otherwise.
export function headCells(lanes: Lane[], columns: number, ink: Ink = DARK): string {
  const out = new Uint32Array(columns * 3)
  for (let x = 0; x < columns; x++) out.set([0x20, DEFAULT_COLOUR, DEFAULT_COLOUR], x * 3)
  const busy = new Set(lanes.map(lane => lane.station))
  STATIONS.forEach((station, index) => {
    const start = labelColumn(index, columns)
    const colour = busy.has(station) ? ACCENT[station] : ink.dim
    ;[...station].forEach((letter, i) => {
      if (start + i < columns) out.set([letter.charCodeAt(0), colour, DEFAULT_COLOUR], (start + i) * 3)
    })
  })
  return encode(out)
}

function hex(colour: number): string {
  return `#${colour.toString(16).padStart(6, '0')}`
}
const svgNumber = (value: number): string => String(Math.round(value * 1000) / 1000)

// A frame's pixels as solid shapes: each run of one colour on a row is one rect, and the rects overlap
// a hair so no seam shows between rows once the drawing is smoothed.
function frameRects(frame: string[], colours: Record<string, number>, ox = 0): string {
  let out = ''
  frame.forEach((line, y) => {
    for (let x = 0; x < line.length;) {
      let end = x + 1
      while (line[end] === line[x]) end++
      const colour = colours[line[x]!]
      if (colour !== undefined) out += `<rect x="${ox + x}" y="${y}" width="${end - x}" height="1.05" rx="0.2" fill="${hex(colour)}"/>`
      x = end
    }
  })
  return out
}

// A frame's turn in a loop of frames that hold for different times, as a discrete animation of its visibility.
function turn(i: number, durations: number[]): string {
  const total = durations.reduce((sum, ms) => sum + ms, 0)
  const before = durations.slice(0, i).reduce((sum, ms) => sum + ms, 0)
  const [from, to] = [before / total, (before + durations[i]!) / total]
  const times = [...(i > 0 ? [0] : []), from, ...(to < 1 ? [to] : [])]
  const values = [...(i > 0 ? ['hidden'] : []), 'visible', ...(to < 1 ? ['hidden'] : [])]
  return `<animate attributeName="visibility" calcMode="discrete" values="${values.join(';')}" ` +
    `keyTimes="${times.map(t => t.toFixed(4)).join(';')}" dur="${total}ms" repeatCount="indefinite"/>`
}

// Groups shown in turn with SMIL. Where SMIL doesn't run the first stands still.
function inTurn(groups: string[], durations: number[]): string {
  return groups.map((group, i) => `<g${i > 0 ? ' visibility="hidden"' : ''}>${group}${groups.length > 1 ? turn(i, durations) : ''}</g>`).join('')
}

const EFFECT_SAMPLES = 12

// A station's work pixels as solid shapes: a run of one colour and opacity on a row is one rect.
function pxRects(pixels: Px[], ox: number): string {
  const runs = [...pixels].sort((p, q) => p.y - q.y || p.x - q.x)
  let out = ''
  for (let i = 0; i < runs.length;) {
    const first = runs[i]!
    let end = i + 1
    while (end < runs.length && runs[end]!.y === first.y && runs[end]!.x === first.x + (end - i) &&
      runs[end]!.colour === first.colour && runs[end]!.alpha === first.alpha) end++
    const opacity = first.alpha < 1 ? ` opacity="${svgNumber(first.alpha)}"` : ''
    out += `<rect x="${ox + first.x}" y="${first.y}" width="${end - i}" height="1" rx="0.2" fill="${hex(first.colour)}"${opacity}/>`
    i = end
  }
  return out
}

// A station's work, sampled, since a document can't run its code. The figure's poses in the same way.
function workSvg(station: Station, x: number, ink: Ink): string {
  const colours = FIGURE_COLOURS(ink, ACCENT[station])
  const poses = ACTS[station]
  const figure = inTurn(poses.map(pose => frameRects(pose.frame, colours, x)), poses.map(pose => pose.ms))
  const length = EFFECT_CYCLE[station]
  const samples = Array.from({ length: EFFECT_SAMPLES }, (_, i) => pxRects(effectAt(station, (i * length) / EFFECT_SAMPLES, ink), x + EFFECT_OFFSET))
  return figure + inTurn(samples, samples.map(() => length / EFFECT_SAMPLES))
}

const WALK_SAMPLES = 12

// The rail as lines: lit up to `reached` with a gradient through the stations' colours, dotted beyond
// it, and a round node at each station.
function railSvg(reached: number, columns: number, ink: Ink): string {
  const y = RAIL_Y + 0.5
  const [first, last] = [stationX(0, columns), stationX(LAST, columns)]
  const at = stationX(reached, columns)
  const stops = STATIONS.map((station, i) => `<stop offset="${svgNumber(i / LAST)}" stop-color="${hex(ACCENT[station])}"/>`).join('')
  const nodes = STATIONS.map((station, i) =>
    `<circle cx="${svgNumber(stationX(i, columns))}" cy="${y}" r="0.5" fill="${hex(i <= reached ? ACCENT[station] : ink.rail)}"/>`).join('')
  return `<defs><linearGradient id="lit" gradientUnits="userSpaceOnUse" x1="${svgNumber(first)}" y1="0" x2="${svgNumber(last)}" y2="0">${stops}</linearGradient></defs>` +
    `<line x1="${svgNumber(at)}" y1="${y}" x2="${svgNumber(last)}" y2="${y}" stroke="${hex(ink.rail)}" stroke-width="0.5" stroke-dasharray="0.6 1" stroke-linecap="round"/>` +
    (at > first ? `<line x1="${svgNumber(first)}" y1="${y}" x2="${svgNumber(at)}" y2="${y}" stroke="url(#lit)" stroke-width="0.6" stroke-linecap="round"/>` : '') +
    nodes
}

// A lane's Svg: its 6 units of lane, then a row of names and a row of times.
const LANE_SVG_HEIGHT = 14

// One word at a station's label column, as the header writes it.
const svgLabel = (index: number, columns: number, y: number, colour: number, text: string): string =>
  `<text x="${labelColumn(index, columns)}" y="${y}" font-family="monospace" font-size="2.6" fill="${hex(colour)}">${text}</text>`

// A lane as one Svg document, as it stands at this moment. The rail is drawn where the figure is going.
// A walking figure's group slides from where it is, on the same curve the terminal uses, showing its
// strides for the walk's time left and then its work. Without SMIL nothing moves and the work's first
// frame stands at its station. Under the lane, each station's name, in its colour where the lane is, and
// its time as of `now`. It has a viewBox and no size, so a surface draws it across the pane at its own
// shape. Nothing from the status file is in it: the times are written from numbers.
export function laneSvg(lane: Lane, now: number, ink: Ink = DARK, columns = SVG_COLUMNS): string {
  const index = indexOf(lane.station)
  // Not rounded: a vector figure stands exactly over its node, and a walk ends exactly there.
  const home = stationX(index, columns) - FIGURE_CENTRE
  const running = isRunning(lane.walk, now) ? lane.walk : null
  const target = running?.isOut ? columns + 1 : home
  let inner = ''
  if (running) {
    const left = running.end - now
    const stride = RUN.map(frame => frameRects(running.to < running.from ? mirror(frame) : frame, FIGURE_COLOURS(ink, ACCENT[lane.station])))
    const values = Array.from({ length: WALK_SAMPLES + 1 }, (_, i) =>
      `${svgNumber(walkLeft(running, columns, now + (left * i) / WALK_SAMPLES) - target)} 0`).join(';')
    inner += `<animateTransform attributeName="transform" type="translate" values="${values}" dur="${svgNumber(left)}ms" fill="freeze"/>`
    inner += `<g display="none"><set attributeName="display" to="inline" dur="${svgNumber(left)}ms"/>${inTurn(stride, stride.map(() => STRIDE_MS))}</g>`
    if (!running.isOut) inner += `<g><set attributeName="display" to="none" dur="${svgNumber(left)}ms"/>${workSvg(lane.station, 0, ink)}</g>`
  } else {
    inner += workSvg(lane.station, 0, ink)
  }
  const times = stageTimes(lane, now)
  const rows = STATIONS.map((station, index) =>
    svgLabel(index, columns, 9, station === lane.station ? ACCENT[station] : ink.dim, station) +
    svgLabel(index, columns, 13, timeColour(lane, station, times[station], ink), timeText(times[station]))).join('')
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${columns} ${LANE_SVG_HEIGHT}">` +
    `${railSvg(index, columns, ink)}<g transform="translate(${svgNumber(target)} 0)"><g>${inner}</g></g>${rows}</svg>`
}

// The header as one Svg document, with a viewBox and no size, as a lane has.
export function headSvg(lanes: Lane[], ink: Ink = DARK, columns = SVG_COLUMNS): string {
  const busy = new Set(lanes.map(lane => lane.station))
  const labels = STATIONS.map((station, index) => svgLabel(index, columns, 3, busy.has(station) ? ACCENT[station] : ink.dim, station))
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${columns} 4">${labels.join('')}</svg>`
}

// What a lane's Svg says for a reader who can't see it: by station name, never the raw step, which is
// status-file text when loop-crew doesn't know it.
export const laneAlt = (lane: Lane): string => `Issue #${lane.row.number} at ${lane.station}`
