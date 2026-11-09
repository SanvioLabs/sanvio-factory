import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import { bars, encode, svg, ticks, under } from './charts'
import type { Chart } from './charts'
import { DEFAULT_RANGE, RANGES, argv, clip, findRoot, money, newer, outcome, sections, sinceFor, state, tokens } from './logic'
import type { Table, Tone } from './logic'
import type { Range, Seen } from '../types'

const PANE = 'dashboard'
const COMMAND = 'factory-dashboard'
// The numbers move slowly, and each refresh calls GitHub, reads git and rewrites the caches, so every
// five minutes is enough; Refresh reads now.
const REFRESH_MS = 300_000
// A cold first read goes through every transcript once; the most process.run allows.
const TIMEOUT_MS = 600_000
// A chart's height in the terminal, in rows; each row draws eighths, so 5 rows is 40 steps.
const CHART_ROWS = 5

const launchAtom = atom({ plugin: 'factory-dashboard', key: 'launch' } as const, null)
const seenAtom = atom({ plugin: 'factory-dashboard', key: 'seen' } as const, null)
const rangeAtom = atom({ plugin: 'factory-dashboard', key: 'range' } as const, null)
// More days than this and the Svg labels every 7th bar, as the terminal does when it runs out of room.
const SVG_EVERY_DAY = 14

const COLORS: Record<Tone, { color?: string; bold?: boolean; dimColor?: boolean }> = {
  pass: { color: 'green' },
  fail: { color: 'red' },
  now: { color: 'yellow' },
  quiet: { dimColor: true },
  plain: {},
}

let stopPolling: (() => void) | null = null
// One read at a time: a refresh asked for while one runs is the same refresh.
let reading: Promise<void> | null = null

// The folder saved at session.start first, then the session's root: a /clear starts a new session
// without a session.start, so the saved folder can be missing or the last session's.
async function rootOf($: EngineInterface): Promise<string | null> {
  const exists = (path: string) => $.fs.exists(path)
  const launch = await read($, launchAtom)
  return (launch && (await findRoot(launch, exists))) || findRoot(await $.session.root(), exists)
}

// The first day the chosen range counts.
async function since($: EngineInterface): Promise<string> {
  return sinceFor((await read($, rangeAtom)) ?? DEFAULT_RANGE, Date.now())
}

// Run the script and keep what it printed. A failure keeps the last good document and says when.
function refresh($: EngineInterface, root: string): Promise<void> {
  reading ??= (async () => {
    await update($, seenAtom, prev => ({
      root, doc: prev?.doc ?? null, readAt: prev?.readAt ?? null, failedAt: prev?.failedAt ?? null,
      failure: prev?.failure ?? null, isReading: true,
    }))
    $.ui.invalidate('ui.render')
    let done = false
    try {
      // A range picked while a read runs is read straight after it.
      let from = await since($)
      let got = outcome(await $.process.run(argv(from), { cwd: root, timeoutMs: TIMEOUT_MS }).catch(() => null))
      while (from !== (await since($))) {
        from = await since($)
        got = outcome(await $.process.run(argv(from), { cwd: root, timeoutMs: TIMEOUT_MS }).catch(() => null))
      }
      const at = Date.now()
      await update($, seenAtom, prev => {
        const base = prev ?? { root, doc: null, readAt: null, failedAt: null, failure: null, isReading: false }
        return 'doc' in got
          ? { ...base, doc: got.doc, readAt: at, failedAt: null, failure: null, isReading: false }
          : { ...base, failedAt: at, failure: got.failure, isReading: false }
      })
      done = true
    } finally {
      // Whatever went wrong on the way, the pane isn't left saying Reading… with Refresh dead. A test
      // can't drive this: the engine skips a state hook that throws rather than failing the write.
      if (!done) await update($, seenAtom, prev => (prev ? { ...prev, isReading: false, failedAt: Date.now(), failure: "the read didn't finish" } : prev)).catch(() => {})
      $.ui.invalidate('ui.render')
    }
  })().finally(() => {
    reading = null
  })
  return reading
}

// Read every five minutes, and only while the pane is up, so a session that never opens it runs nothing.
function startPolling($: EngineInterface, root: string): void {
  if (stopPolling) return
  // every() hands back a timer, not a function: the loop pane learned that calling it throws.
  const timer = $.clock.every(REFRESH_MS, () => {
    void (async () => {
      if (!(await $.ui.panes()).some(pane => pane.id === PANE)) {
        stopPolling?.()
        stopPolling = null
        return
      }
      await refresh($, root)
    })().catch(() => {})
  })
  stopPolling = () => timer.cancel()
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    // A reload fires session.start again; the directory the session started in is the first one.
    await update($, launchAtom, prev => prev ?? e.cwd)
    // A reload ends any read under way, so one saved as running isn't: let Refresh work again.
    await update($, seenAtom, prev => (prev?.isReading ? { ...prev, isReading: false } : prev))
    await $.command.register({
      name: COMMAND,
      description: "Open a pane with the factory's numbers: what's waiting on you, the loop's spend and rework, evals, tokens",
    })
    // A pane left open across a reload keeps updating.
    if ((await $.ui.panes()).some(pane => pane.id === PANE)) {
      const root = await rootOf($)
      if (root) startPolling($, root)
    }
    return next(e)
  })

  on('command.run', { command: COMMAND }, async $ => {
    try {
      const root = await rootOf($)
      if (!root) return { text: `No scripts/dashboard_data.py at or above ${await $.session.root()}, so there are no numbers to show.` }
      const opened = await $.ui.open({ id: PANE, title: 'Factory' })
      void refresh($, root).catch(() => {})
      startPolling($, root)
      return { text: opened.isPlaced ? 'Dashboard opened.' : 'Dashboard opened. Widen the terminal to see it.' }
    } catch {
      return { text: "The dashboard couldn't open. python3 scripts/dashboard_data.py --json prints the same numbers." }
    }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const elements = $.ui.resolve(e)
    const { Box, Button, Text } = elements
    const seen: Seen | null = await read($, seenAtom)
    const range: Range = (await read($, rangeAtom)) ?? DEFAULT_RANGE
    const width = Math.max(10, e.props.bodyColumns)
    // Claude Desktop and VS Code wrap text, so there a long line shows whole instead of being cut.
    const wraps = e.surface === 'desktop' || e.surface === 'vscode'
    const fit = (s: string) => (wraps ? s : clip(s, width))
    const top = state(seen)
    const ahead = seen?.doc ? newer(seen.doc) : null

    // A table: the name column takes what's left, each number column the width of its widest cell,
    // right-aligned, one space between. A name too long for what's left is cut, not wrapped. When
    // fewer than 8 columns are left for the name, each row goes on two lines: the name across the
    // whole pane, then its figures right-aligned under it, both in the row's colour.
    const table = (t: Table) => {
      const widths = t.head.map((h, i) => Math.max(h.length, ...t.rows.map(r => (r[i] ?? '').length)))
      const numbers = widths.slice(1).reduce((a, w) => a + w + 1, 0)
      const stacked = width - numbers < 8
      const name = Math.max(4, width - numbers)
      const row = (cells: string[], key: string, head: boolean, tone: Tone = 'plain') => {
        const colors = head ? COLORS.quiet : COLORS[tone]
        const figures = cells.slice(1).map((c, i) => (
          <Box key={`${key}-${i}`} width={(widths[i + 1] ?? 0) + 1} justifyContent="flex-end" flexShrink={0}>
            <Text {...colors}>{c}</Text>
          </Box>
        ))
        if (stacked) {
          return (
            <Box key={key} flexDirection="column">
              <Box key={`${key}-name`} flexDirection="row">
                <Text {...colors}>{wraps ? (cells[0] ?? '') : clip(cells[0] ?? '', width)}</Text>
              </Box>
              <Box key={`${key}-figures`} flexDirection="row" justifyContent="flex-end">
                {figures}
              </Box>
            </Box>
          )
        }
        return (
          <Box key={key} flexDirection="row">
            <Box flexGrow={1} flexShrink={1}>
              <Text {...colors}>{wraps ? (cells[0] ?? '') : clip(cells[0] ?? '', name)}</Text>
            </Box>
            {figures}
          </Box>
        )
      }
      return (
        <Box key={t.key} flexDirection="column" marginBottom={1}>
          {row(t.head, `${t.key}-head`, true)}
          {t.rows.map((r, i) => row(r, `${t.key}-${i}`, false, t.tones?.[i]))}
        </Box>
      )
    }

    // A day-by-day chart, oldest on the left, today in orange. The terminal draws block characters in
    // colour; every other surface draws an Svg whose bars say their day and value on hover.
    const chart = (c: Chart) => {
      const values = c.points.map(p => p.value)
      const label = c.unit === 'money' ? money : (n: number | null) => `${tokens(n)} tokens`
      const columns = Math.min(512, width)
      const dates = c.labels.map(l => l[0] ?? '')
      // By surface, not by what resolve() hands back: a surface without an element still resolves it,
      // to a placeholder that draws nothing.
      if (e.surface === 'terminal' && 'Raster' in elements) {
        const { Raster } = elements
        // Each label row under the bars: the days, then the figures. When they don't all fit, the
        // day alone under every 7th bar, counting back from today's.
        const rows = c.columns.map((_, i) => under(c.labels.map(l => l[i] ?? ''), columns))
        const fits = rows.every((r): r is string => r !== null)
        return (
          <Box key={`${c.key}-box`} flexDirection="column">
            <Raster key={c.key} columns={columns} rows={CHART_ROWS} cells={encode(bars(values, columns, CHART_ROWS))} />
            {fits
              ? rows.map((r, i) => <Box key={`${c.key}-under-${i}`}><Text dimColor={i > 0}>{r || ' '}</Text></Box>)
              : <Box key={`${c.key}-ticks`}><Text>{ticks(dates, columns) || ' '}</Text></Box>}
          </Box>
        )
      }
      if ('Svg' in elements) {
        const { Svg } = elements
        const sparse = c.points.length > SVG_EVERY_DAY
        const source = sparse ? svg(c.points, label, dates.map(d => [d]), 7) : svg(c.points, label, c.labels)
        return (
          <Box key={`${c.key}-box`} flexDirection="column">
            <Svg key={c.key} source={source} alt={c.alt} isInteractive />
          </Box>
        )
      }
      // A terminal without Raster: the figures, as a table.
      return table({ key: `${c.key}-days`, head: c.columns, rows: c.labels })
    }

    return (
      <Box flexDirection="column">
        <Box key="header" flexDirection="row" flexWrap="wrap" justifyContent="space-between" columnGap={1}>
          <Text bold>{fit(seen ? (seen.root.split('/').filter(Boolean).pop() ?? seen.root) : 'Factory')}</Text>
          <Text {...COLORS[top.tone]}>{fit(top.text)}</Text>
        </Box>
        <Box key="actions" flexDirection="row" columnGap={1}>
          <Button
            key="refresh"
            label={seen?.isReading ? 'Reading…' : 'Refresh'}
            dimColor={!!seen?.isReading}
            onPress={() => {
              if (seen && !seen.isReading) void refresh($, seen.root).catch(() => {})
            }}
          />
          {/* The days counted. Picking one reads now; a read already running reads it straight after. */}
          {RANGES.map(n => (
            <Button
              key={`range-${n}`}
              label={`${n} days`}
              variant={n === range ? 'primary' : undefined}
              dimColor={n !== range}
              onPress={() => {
                void (async () => {
                  await update($, rangeAtom, () => n)
                  if (seen) await refresh($, seen.root)
                })().catch(() => {})
              }}
            />
          ))}
        </Box>
        {seen?.failure ? <Text key="failure" color="red">{fit(`Last refresh: ${seen.failure}`)}</Text> : null}
        {ahead ? <Text key="newer" {...COLORS[ahead.tone]}>{fit(ahead.text)}</Text> : null}
        <Text dimColor>{'─'.repeat(width)}</Text>
        {seen?.doc
          ? sections(seen.doc).map((section, i) => (
              <Box key={section.key} flexDirection="column">
                {/* A line between sections; the header's own rule sits above the first. */}
                {i > 0 ? <Box key={`rule-${section.key}`} marginBottom={1}><Text dimColor>{'─'.repeat(width)}</Text></Box> : null}
                <Text bold>{fit(section.title)}</Text>
                {/* The chart first, under its caption, then the tables and notes. */}
                {section.chart ? (
                  <Box key={`${section.key}-chart-area`} flexDirection="column" marginBottom={1}>
                    <Text dimColor>{fit(section.chart.caption)}</Text>
                    {chart(section.chart)}
                  </Box>
                ) : null}
                {(section.tables ?? []).map(table)}
                {section.lines.map((l, n) => (
                  <Text key={`${section.key}-${n}`} {...COLORS[l.tone]}>{fit(l.text)}</Text>
                ))}
                {/* A table already leaves a line under itself; notes need one before the next rule. */}
                {section.lines.length ? <Box key={`${section.key}-end`} marginBottom={1} /> : null}
              </Box>
            ))
          : <Text dimColor>{fit(seen?.failure ? 'Nothing read yet. Refresh tries again.' : 'Nothing to show until the first read ends.')}</Text>}
      </Box>
    )
  })
}
