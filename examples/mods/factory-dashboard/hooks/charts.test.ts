import { describe as group, expect, test } from 'claude-code/testing'

import { BAR, TODAY, bars, encode, layout, peak, series, sum, svg, ticks, under } from './charts'

// The cells back from a Raster's base64, as [character, foreground] per cell.
function decode(text: string): [string, number][] {
  const bytes = Uint8Array.from(atob(text), c => c.charCodeAt(0))
  const view = new DataView(bytes.buffer)
  const out: [string, number][] = []
  for (let i = 0; i < bytes.length; i += 12) out.push([String.fromCodePoint(view.getUint32(i, true)), view.getUint32(i + 4, true)])
  return out
}

group('the series', () => {
  test("reads the script's rows, oldest first, a field at a time", () => {
    const rows = [{ day: '2026-10-27', tokens: 5, cost_usd: 2 }, { day: '2026-10-26', tokens: 3, cost_usd: 1 }]
    expect(series(rows, 'cost_usd')).toEqual([{ date: '2026-10-26', value: 1 }, { date: '2026-10-27', value: 2 }])
    expect(series(rows, 'tokens')).toEqual([{ date: '2026-10-26', value: 3 }, { date: '2026-10-27', value: 5 }])
  })
  test("a day without a number is null, not 0; no rows is no series", () => {
    expect(series([{ day: '2026-10-26', cost_usd: null }, { day: '2026-10-27', cost_usd: 1 }], 'cost_usd')?.[0]?.value).toBeNull()
    expect(series([{ day: 'x', cost_usd: 1 }, { day: '2026-1-1', cost_usd: 2 }], 'cost_usd')).toBeNull()
    expect(series(undefined, 'cost_usd')).toBeNull()
    expect(series({ value: null, why: 'no loop records' }, 'cost_usd')).toBeNull()
  })
  test('two series add up day by day, and one alone stands', () => {
    const a = [{ date: '2026-10-26', value: 1 }, { date: '2026-10-27', value: 2 }]
    const b = [{ date: '2026-10-27', value: 3 }]
    expect(sum(a, b)).toEqual([{ date: '2026-10-26', value: 1 }, { date: '2026-10-27', value: 5 }])
    expect(sum(a, null)).toEqual(a)
    expect(sum(null, null)).toBeNull()
    expect(sum([{ date: 'd', value: null }], [{ date: 'd', value: null }])).toEqual([{ date: 'd', value: null }])
  })
  test('peak is the busiest day, never one it could not count, and none when nothing happened', () => {
    expect(peak([{ date: 'a', value: 1 }, { date: 'b', value: 3 }, { date: 'c', value: null }])?.date).toBe('b')
    expect(peak([{ date: 'a', value: 0 }, { date: 'b', value: null }])).toBeNull()
  })
})

group('the terminal bars', () => {
  test("one bar per day, as tall as its share of the busiest, today's in its own colour", () => {
    // Two days in 4 columns and 2 rows: each day gets 2 columns, the busiest fills both rows.
    const cells = decode(encode(bars([1, 2], 4, 2)))
    const rows = [cells.slice(0, 4), cells.slice(4, 8)].map(r => r.map(c => c[0]).join(''))
    expect(rows).toEqual(['  ██', '████'])
    expect(cells[4]?.[1]).toBe(BAR)
    expect(cells[7]?.[1]).toBe(TODAY)
  })
  test('a part row uses the eighths, and a day with nothing stays blank', () => {
    const cells = decode(encode(bars([0, 3, 4], 3, 1)))
    expect(cells.map(c => c[0]).join('')).toBe(' ▆█')
  })
  test('days that do not fit drop off the left, and the cells are columns × rows', () => {
    const cells = decode(encode(bars([5, 1, 2], 2, 1)))
    expect(cells.length).toBe(2)
    expect(cells.map(c => c[0]).join('')).toBe('▄█')
  })
})

group('the labels under the bars', () => {
  test('each is centred on its own bar, so it sits under it', () => {
    // Two days in 20 columns: slots of 10, bars 9 wide at 0 and 10.
    expect(layout(2, 20)).toEqual({ count: 2, slot: 10, width: 9, offset: 0 })
    expect(under(['Oct 26', 'Oct 27'], 20)).toBe(' Oct 26    Oct 27')
    expect(under(['$1.00', '$21.84'], 20)).toBe('  $1.00    $21.84')
  })
  test("are null when one fills a bar's room with no space to spare, so the pane shows the table instead", () => {
    expect(under(['Oct 26', 'Oct 27', 'Oct 28'], 12)).toBeNull()
    // Slots of 6 for labels of 6 would read Oct 26Oct 27.
    expect(under(['Oct 26', 'Oct 27'], 12)).toBeNull()
    expect(under(['Oct 26', 'Oct 27'], 14)).toBe('Oct 26 Oct 27')
  })
  test('are null when the pane is narrower than the days, since the bars then touch', () => {
    expect(under(['a', 'b', 'c'], 2)).toBeNull()
  })
  test("without room for each bar's, every 7th bar gets its day, counting back from today's", () => {
    const labels = Array.from({ length: 15 }, (_, i) => String.fromCharCode(97 + i))
    // 15 days in 30 columns: slots of 2, bars 2 wide, so a bar's middle is at its slot's second column.
    expect(ticks(labels, 30)).toBe(' a' + ' '.repeat(13) + 'h' + ' '.repeat(13) + 'o')
  })
  test("leaves out a day that would run into the newer one, so today's always shows", () => {
    // Three days in 12 columns, every one labelled: Oct 2 would touch Oct 3, so it goes.
    expect(ticks(['Oct 1', 'Oct 2', 'Oct 3'], 12, 1)).toBe('Oct 1  Oct 3')
    expect(ticks(['Oct 1'], 3)).toBe('')
  })
})

group('the Svg bars', () => {
  test('writes each line of labels under its bar', () => {
    const drawn = svg([{ date: '2026-10-27', value: 2 }], n => `$${n}`, [['Oct 27', '$2.00', '4.4M']])
    expect(drawn.match(/<text/g)?.length).toBe(3)
    expect(drawn).toContain('>Oct 27</text>')
    expect(drawn).toContain('>4.4M</text>')
  })
  test('has a bar per day titled with its day and value, today in its own colour', () => {
    const drawn = svg([{ date: '2026-10-26', value: 1 }, { date: '2026-10-27', value: 2 }], n => `$${n?.toFixed(2)}`)
    expect(drawn.startsWith('<svg')).toBe(true)
    expect(drawn.match(/<rect/g)?.length).toBe(2)
    expect(drawn).toContain('<title>2026-10-27 $2.00</title>')
    expect(drawn).toContain('#dd8452')
    expect(drawn).not.toContain('<script')
  })
  test('with every 7, only every 7th bar back from today has its lines, and the bars sit closer', () => {
    const points = Array.from({ length: 15 }, (_, i) => ({ date: `2026-10-${13 + i}`, value: 1 }))
    const drawn = svg(points, n => `${n}`, points.map(p => [p.date.slice(5)]), 7)
    expect(drawn.match(/<text/g)?.length).toBe(3)
    expect(drawn).toContain('>10-27</text>')
    expect(drawn).toContain('>10-20</text>')
    expect(drawn).toContain('viewBox="0 0 300 ')
  })
  test('escapes a label so it stays text', () => {
    expect(svg([{ date: '2026-10-27', value: 1 }], () => '<b>&')).toContain('&lt;b&gt;&amp;')
  })
})
