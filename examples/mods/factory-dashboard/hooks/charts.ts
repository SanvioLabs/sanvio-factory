// The day-by-day charts, as plain functions: the series out of the script's JSON, and the two ways
// to draw it. The terminal draws a Raster of block characters, every other surface an Svg.

// value is null on a day the script couldn't count: its runs recorded no cost, say. It draws as no
// bar and is labelled ?, never as 0.
export type Point = { date: string; value: number | null }
// labels: for each point, what to write under its bar, as a row of the day-by-day table whose
// header is `columns`, the day first: ['Oct 22', '$2.69', '4.4M'] under ['Day', 'Cost', 'Tokens'].
// caption: the line drawn with the chart, saying the days it covers and the busiest.
export type Chart = { key: string; alt: string; caption: string; points: Point[]; unit: 'money' | 'tokens'; columns: string[]; labels: string[][] }

type Obj = Record<string, unknown>
const obj = (v: unknown): Obj | null => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Obj) : null)
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
const DATE = /^\d{4}-\d{2}-\d{2}$/

// A by_day series, oldest first, from the rows the script prints: [{ day, <field>, ... }]. A day
// whose field isn't a number is null. Null when there's no series, so the pane can say so rather
// than draw an empty chart.
export function series(v: unknown, field: string): Point[] | null {
  const points = (Array.isArray(v) ? v : [])
    .map(obj)
    .filter((r): r is Obj => !!r && typeof r.day === 'string' && DATE.test(r.day))
    .map(r => ({ date: r.day as string, value: num(r[field]) === null ? null : Math.max(0, num(r[field])!) }))
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
  return points.length ? points : null
}

// Two series added day by day: the harness's conversations and the loop's. A day is null only
// when neither side counted it.
export function sum(a: Point[] | null, b: Point[] | null): Point[] | null {
  if (!a || !b) return a ?? b
  const by = new Map<string, number | null>(a.map(p => [p.date, p.value]))
  for (const p of b) {
    const had = by.get(p.date) ?? null
    by.set(p.date, had === null && p.value === null ? null : (had ?? 0) + (p.value ?? 0))
  }
  return [...by.entries()].sort((x, y) => (x[0] < y[0] ? -1 : 1)).map(([date, value]) => ({ date, value }))
}

const BLOCKS = '▁▂▃▄▅▆▇█'

// The day with the most, for the label beside a chart.
export function peak(points: Point[]): Point | null {
  return points.reduce<Point | null>((best, p) => ((p.value ?? 0) > 0 && (!best || p.value! > best.value!) ? p : best), null)
}

const DEFAULT = 0x01000000 // the terminal's own colour
export const BAR = 0x4c72b0
export const TODAY = 0xdd8452

// A Raster's cells for a bar chart: one bar per day, newest on the right in TODAY's colour, each bar
// as tall as its value against the tallest, to an eighth of a row. Days that don't fit drop off the
// left. Every cell is [code point, foreground, background], row-major.
// Where n days' bars sit in `columns`: how many fit, each one's slot and bar width, and the left margin
// that centres them. The bars and the labels under them both come from this, so they line up.
export function layout(n: number, columns: number): { count: number; slot: number; width: number; offset: number } {
  const count = Math.min(n, columns)
  const slot = Math.max(1, Math.floor(columns / Math.max(1, count)))
  return { count, slot, width: slot > 2 ? slot - 1 : slot, offset: Math.floor((columns - slot * count) / 2) }
}

export function bars(values: (number | null)[], columns: number, rows: number): Uint32Array {
  const cells = new Uint32Array(columns * rows * 3)
  for (let i = 0; i < columns * rows; i++) cells.set([0x20, DEFAULT, DEFAULT], i * 3)
  const { count, slot, width, offset } = layout(values.length, columns)
  const shown = values.slice(values.length - count).map(v => v ?? 0)
  const max = Math.max(0, ...shown)
  shown.forEach((v, day) => {
    if (!(v > 0 && max > 0)) return
    const eighths = Math.max(1, Math.round((v / max) * rows * 8))
    const colour = day === shown.length - 1 ? TODAY : BAR
    for (let up = 0; up < rows; up++) {
      const left = eighths - up * 8
      if (left <= 0) break
      const char = BLOCKS.codePointAt(Math.min(8, left) - 1) ?? 0x2588
      const row = rows - 1 - up
      for (let x = 0; x < width; x++) {
        const col = offset + day * slot + x
        if (col < columns) cells.set([char, colour, DEFAULT], (row * columns + col) * 3)
      }
    }
  })
  return cells
}

// One line of labels under the bars, each centred on its own bar, or null when one doesn't fit its
// bar's room with a space to spare, so the pane can show a table instead of labels that run together.
export function under(labels: string[], columns: number): string | null {
  const { count, slot, width, offset } = layout(labels.length, columns)
  const shown = labels.slice(labels.length - count)
  if (shown.some(l => l.length >= slot)) return null
  const out = Array.from({ length: columns }, () => ' ')
  shown.forEach((l, day) => {
    const start = Math.min(columns - l.length, offset + day * slot + Math.max(0, Math.floor((width - l.length) / 2)))
    for (let i = 0; i < l.length; i++) out[start + i] = l[i]!
  })
  return out.join('').replace(/\s+$/, '')
}

// The days alone, under every `every`-th bar counting back from today's, for a pane too narrow to
// write each bar's day and figures under it. Placed from today's back, so a day that would run into
// the newer one beside it is the one left out, and today's always shows.
export function ticks(labels: string[], columns: number, every = 7): string {
  const { count, slot, width, offset } = layout(labels.length, columns)
  const shown = labels.slice(labels.length - count)
  const out = Array.from({ length: columns }, () => ' ')
  let limit = columns + 1
  for (let day = shown.length - 1; day >= 0; day -= every) {
    const l = shown[day]!
    const centre = offset + day * slot + Math.floor(width / 2)
    const start = Math.max(0, Math.min(columns - l.length, centre - Math.floor(l.length / 2)))
    if (l.length > columns || start + l.length >= limit) continue
    for (let i = 0; i < l.length; i++) out[start + i] = l[i]!
    limit = start
  }
  return out.join('').replace(/\s+$/, '')
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

const hex = (colour: number): string => `#${colour.toString(16).padStart(6, '0')}`
const escape = (s: string): string => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

// An Svg bar chart of the same days, each bar titled with its day and value, so hovering one in an
// interactive frame says what it is, and with `lines` written under it, one row of text each.
// `label` writes a value the way the pane does. With `every` above 1, only every `every`-th bar
// counting back from today's gets its lines, and the bars sit closer.
export function svg(points: Point[], label: (n: number | null) => string, lines: string[][] = [], every = 1): string {
  const widest = Math.max(0, ...lines.flat().map(l => l.length))
  const slot = Math.max(20, Math.ceil((widest * 7) / every))
  const height = 80
  const rows = Math.max(0, ...lines.map(l => l.length))
  const max = Math.max(0, ...points.map(p => p.value ?? 0))
  const shapes = points.map((p, i) => {
    const h = (p.value ?? 0) > 0 && max > 0 ? Math.max(1, Math.round((p.value! / max) * height)) : 0
    const fill = hex(i === points.length - 1 ? TODAY : BAR)
    return `<rect x="${i * slot + slot / 2 - 8}" y="${height - h}" width="16" height="${h}" fill="${fill}"><title>${escape(`${p.date} ${label(p.value)}`)}</title></rect>`
  })
  const text = lines.flatMap((l, i) => ((points.length - 1 - i) % every ? [] : l).map((t, row) =>
    `<text x="${i * slot + slot / 2}" y="${height + 14 + row * 13}" text-anchor="middle" font-size="10" font-family="sans-serif" fill="#888">${escape(t)}</text>`))
  const width = Math.max(slot, points.length * slot)
  const tall = height + 1 + (rows ? rows * 13 + 4 : 0)
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${tall}" width="${width}" height="${tall}">` +
    `${shapes.join('')}<line x1="0" y1="${height + 0.5}" x2="${width}" y2="${height + 0.5}" stroke="#888" stroke-width="1"/>${text.join('')}</svg>`
}
