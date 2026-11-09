import { expect, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

import { SAMPLE } from './sample'

// The README's picture: the pane on the terminal, 66 columns wide, drawing SAMPLE with 14 days chosen,
// its drawn tree laid out as rows of text. A test has no console and no file system, so
// scripts/draw_dashboard.py gets the rows out through a test of its own that imports picture() and
// fails with them as its message. It runs the tests with TZ=UTC: the header's time is local.
const COLUMNS = 66

type Node = { type: string; props?: Record<string, unknown>; children?: (Node | string)[] }
// One run of text on a row, from column `col`, in a Text's colour and styles.
type Seg = { col: number; text: string; color?: string; dim?: true; bold?: true }
// A Raster's cells as it drew them, base64, over `rows` rows from row `row`, column `col`.
type Cells = { row: number; col: number; columns: number; rows: number; cells: string }
type Block = { rows: Seg[][]; rasters: Cells[] }

const length = (s: string): number => [...s].length
const words = (n: Node | string): string => (typeof n === 'string' ? n : (n.children ?? []).map(words).join(''))
const gap = (p: Record<string, unknown>): number => Number(p.columnGap ?? p.gap ?? 0)
const isColumn = (p: Record<string, unknown>): boolean => p.flexDirection === 'column'

function style(p: Record<string, unknown>): Omit<Seg, 'col' | 'text'> {
  return {
    ...(typeof p.color === 'string' ? { color: p.color } : {}),
    ...(p.dimColor ? { dim: true as const } : {}),
    ...(p.bold ? { bold: true as const } : {}),
  }
}

// How wide a node draws when nothing stretches it.
function natural(n: Node | string): number {
  if (typeof n === 'string') return length(n)
  const p = n.props ?? {}
  if (typeof p.width === 'number') return p.width
  if (n.type === 'Text') return length(words(n))
  if (n.type === 'Button') return length(String(p.label)) + 4
  if (n.type === 'Raster') return Number(p.columns)
  const kids = (n.children ?? []).map(natural)
  if (isColumn(p)) return Math.max(0, ...kids)
  return kids.reduce((a, w) => a + w, 0) + gap(p) * Math.max(0, kids.length - 1)
}

// `inner` placed `down` rows and `across` columns into `outer`.
function place(outer: Block, inner: Block, down: number, across: number): void {
  inner.rows.forEach((segs, i) => {
    while (outer.rows.length <= down + i) outer.rows.push([])
    outer.rows[down + i]!.push(...segs.map(s => ({ ...s, col: s.col + across })))
  })
  outer.rasters.push(...inner.rasters.map(r => ({ ...r, row: r.row + down, col: r.col + across })))
}

// A node laid out `width` columns wide, as the terminal's flexbox does for the props this pane uses.
function draw(n: Node | string, width: number): Block {
  if (typeof n === 'string') return { rows: [[{ col: 0, text: n }]], rasters: [] }
  const p = n.props ?? {}
  if (n.type === 'Text') return { rows: [[{ col: 0, text: words(n), ...style(p) }]], rasters: [] }
  if (n.type === 'Button') {
    const look = p.variant === 'primary' ? { color: 'accent', bold: true as const } : style(p)
    return { rows: [[{ col: 0, text: `[ ${String(p.label)} ]`, ...look }]], rasters: [] }
  }
  if (n.type === 'Raster') {
    const rows = Number(p.rows)
    return { rows: Array.from({ length: rows }, () => []), rasters: [{ row: 0, col: 0, columns: Number(p.columns), rows, cells: String(p.cells) }] }
  }
  const room = typeof p.width === 'number' ? p.width : width
  const out: Block = { rows: [], rasters: [] }
  for (let i = 0; i < Number(p.marginTop ?? 0); i++) out.rows.push([])
  const top = out.rows.length
  const kids = n.children ?? []
  if (isColumn(p)) {
    for (const kid of kids) place(out, draw(kid, room), out.rows.length, 0)
  } else {
    // A row: fixed widths and natural ones first, what's left to the ones that grow, then placed by
    // justifyContent.
    const grows = (k: Node | string) => typeof k !== 'string' && Number(k.props?.flexGrow ?? 0) > 0 && typeof k.props?.width !== 'number'
    const gaps = gap(p) * Math.max(0, kids.length - 1)
    const fixed = kids.filter(k => !grows(k)).reduce((a, k) => a + natural(k), 0)
    const growing = kids.filter(grows).length
    const widths = kids.map(k => (grows(k) ? Math.max(0, Math.floor((room - fixed - gaps) / growing)) : natural(k)))
    const free = Math.max(0, room - widths.reduce((a, w) => a + w, 0) - gaps)
    let x = p.justifyContent === 'flex-end' ? free : 0
    kids.forEach((kid, i) => {
      const spread = p.justifyContent === 'space-between' && kids.length > 1 ? Math.floor((i * free) / (kids.length - 1)) : 0
      place(out, draw(kid, widths[i]!), top, x + spread)
      x += widths[i]! + gap(p)
    })
  }
  for (let i = 0; i < Number(p.marginBottom ?? 0); i++) out.rows.push([])
  return out
}

// The pane as the README pictures it, laid out as rows.
export type Picture = Block & { columns: number }

// Noon on the sample's day in this machine's own zone, so the header reads 12:00 wherever it's drawn:
// the tests run in the machine's zone whatever TZ says.
const READ_AT = new Date(2026, 9, 27, 12, 0).getTime()

export async function picture($: Engine, on: On): Promise<Picture> {
  on('state.get', async (_$, e, next) =>
    e.plugin === 'factory-dashboard' && e.key === 'seen'
      ? { value: { value: { root: '/h/starter', doc: SAMPLE, readAt: READ_AT, isReading: false, failedAt: null, failure: null }, version: 1 } }
      : next(e))
  const ui = await $.ui.mount({
    plugin: 'factory-dashboard', surface: 'terminal', component: 'Pane', requestId: 'dashboard',
    props: { title: 'Factory', isFocused: true, bodyColumns: COLUMNS, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
  } as const)
  const pane = draw((await ui.drawn()) as unknown as Node, COLUMNS)
  await ui.unmount()
  return { columns: COLUMNS, ...pane }
}

test('the README picture fits 66 columns, with both charts', async ($, on) => {
  const pane = await picture($, on)
  expect(pane.rows.length).toBeGreaterThan(0)
  for (const segs of pane.rows) for (const s of segs) expect(s.col + length(s.text)).toBeLessThanOrEqual(COLUMNS)
  for (const r of pane.rasters) expect(r.col + r.columns).toBeLessThanOrEqual(COLUMNS)
  // Loop spend's chart and Conversations'.
  expect(pane.rasters).toHaveLength(2)
})
