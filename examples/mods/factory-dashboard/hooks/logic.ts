// The pane's decisions as plain functions, so they can be tested without a session.
import { peak, series, sum } from './charts'
import type { Chart, Point } from './charts'
import type { Doc, Range, Seen } from '../types'

export type Tone = 'pass' | 'fail' | 'now' | 'quiet' | 'plain'
export type Line = { tone: Tone; text: string }
// A table: a header row, then rows, every row as long as the header. The first column is a name,
// the rest are numbers, drawn right-aligned.
// tones, when given, colours each row: a failing check red, say.
export type Table = { key: string; head: string[]; rows: string[][]; tones?: Tone[] }
export type Section = { key: string; title: string; lines: Line[]; tables?: Table[]; chart?: Chart }

export const SCRIPT = 'scripts/dashboard_data.py'
// The document's shape this pane reads: the script's SCHEMA when this pane was written.
export const SCHEMA = 2

export const RANGES: Range[] = [7, 14, 30]
export const DEFAULT_RANGE: Range = 14

// The first day a range counts, YYYY-MM-DD: today and the days before it, in local time, as the
// script counts its days.
export function sinceFor(days: number, now: number): string {
  const at = new Date(now)
  at.setDate(at.getDate() - (days - 1))
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`
}

// The script's command line for the days from `since` to today.
export function argv(since: string): string[] {
  return ['python3', SCRIPT, '--json', '--since', since]
}

type Obj = Record<string, unknown>
const obj = (v: unknown): Obj | null => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Obj) : null)
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null)
const line = (tone: Tone, text: string): Line => ({ tone, text })

// The line under a chart: the days it covers and the busiest one.
function daily(points: Point[], label: (n: number | null) => string): Line {
  const top = peak(points)
  const span = `${day(points[0]?.date ?? null)} to ${day(points[points.length - 1]?.date ?? null)}`
  return line('quiet', `Daily, ${span}: ${top ? `most ${label(top.value)} on ${day(top.date)}` : 'nothing yet'}`)
}

const NO_DAILY = line('quiet', "No daily figures: this dashboard_data.py doesn't give them yet")

// The script's document, or null when the text isn't one: a crash, a traceback, half a line.
export function parseDoc(text: string): Doc | null {
  try {
    const raw = obj(JSON.parse(text))
    return raw && str(raw.generated) ? raw : null
  } catch {
    return null
  }
}

// Why a section is missing, when the script said it is: { value: null, why }.
export function missing(v: unknown): string | null {
  const o = obj(v)
  return o && 'value' in o && o.value === null ? (str(o.why) ?? 'unavailable') : null
}

// 11.1M, 840k, 312: tokens the way a person reads them.
export function tokens(n: number | null): string {
  if (n === null) return '?'
  const whole = Math.round(n)
  if (whole < 1000) return String(whole)
  const k = Math.round(whole / 1000)
  return k < 1000 ? `${k}k` : `${(whole / 1_000_000).toFixed(1)}M`
}

// $16.54, or ? when the runs reported no cost.
export function money(n: number | null): string {
  return n === null ? '?' : `$${n.toFixed(2)}`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
function pad(n: number): string {
  return String(n).padStart(2, '0')
}

// Oct 13, from a YYYY-MM-DD or an ISO time. Read as a calendar date, not a moment, so no zone moves it.
export function day(text: string | null): string {
  const m = text ? /^(\d{4})-(\d{2})-(\d{2})/.exec(text) : null
  return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}` : '?'
}

// 11:43, the local time of a Date.now() value.
export function hhmm(ms: number): string {
  const at = new Date(ms)
  return `${pad(at.getHours())}:${pad(at.getMinutes())}`
}

// The model with a leading claude- dropped, as the loop pane shows it.
export function model(id: string): string {
  return id.startsWith('claude-') ? id.slice('claude-'.length) : id
}

// The header's right side: reading, when it last read, or that the last refresh failed.
export function state(seen: Seen | null): Line {
  if (!seen || (!seen.doc && seen.isReading)) return line('now', 'Reading… the first read can take a minute')
  if (seen.isReading) return line('now', `Refreshing · ${seen.readAt ? hhmm(seen.readAt) : ''}`)
  if (seen.failedAt) {
    const shown = seen.doc && seen.readAt ? ` · showing ${hhmm(seen.readAt)}` : ''
    return line('fail', `Refresh failed ${hhmm(seen.failedAt)}${shown}`)
  }
  return line('quiet', seen.readAt ? `Updated ${hhmm(seen.readAt)}` : 'Not read yet')
}

// A yellow line under the header when the script's document is a shape this pane doesn't read: newer
// says to update the pane, older to update the factory. Null for the shape it reads, and for a script
// so old it gives no schema: those draw as they always have.
export function newer(doc: Doc): Line | null {
  const schema = num(doc.schema)
  if (schema === null || schema === SCHEMA) return null
  return schema > SCHEMA
    ? line('now', 'This dashboard_data.py is newer than this pane: run /plugin update. Sections it changed may not read')
    : line('now', 'This dashboard_data.py is older than this pane: update the factory. Sections it changed may not read')
}

// The why for a list the script didn't give: its own why, or that it's in a shape this pane can't
// read. Null for a real list, so only a real [] reads as none.
function unread(v: unknown): string | null {
  return Array.isArray(v) ? null : (missing(v) ?? "couldn't read them")
}

// What's waiting on the person: a table of open pull requests, a row red when its checks fail or it
// conflicts, then one of blocked issues with each one's reason under it. A failed read, or a list in
// a shape it doesn't know, says so in red; it never reads as nothing waiting.
export function waiting(doc: Doc): Section {
  const w = obj(doc.waiting)
  const whole = missing(doc.waiting)
  if (whole || !w) return { key: 'waiting', title: 'Waiting on you', lines: [line('quiet', whole ?? 'not in this script')] }
  const out: Line[] = []
  const tables: Table[] = []
  const prsWhy = unread(w.pull_requests)
  const prs = list(w.pull_requests).map(obj).filter((p): p is Obj => !!p)
  if (prsWhy) out.push(line('fail', `Pull requests: ${prsWhy}`))
  if (prs.length) {
    tables.push({ key: 'waiting-prs', head: ['Pull request', 'Waiting', 'Checks', 'Conflicts'],
      rows: prs.map(pr => {
        const hours = num(pr.hours_waited)
        return [`#${num(pr.number) ?? '?'} ${pr.draft === true ? '(draft) ' : ''}${str(pr.title) ?? ''}`,
          hours === null ? '?' : `${hours}h`, str(pr.checks) ?? 'none',
          pr.conflicts === true ? 'yes' : pr.conflicts === false ? 'no' : 'unknown']
      }),
      tones: prs.map(pr => (str(pr.checks) === 'fail' || pr.conflicts === true ? 'fail' : str(pr.checks) === 'pending' ? 'now' : 'plain')) })
  }
  const blockedWhy = unread(w.blocked)
  const blocked = list(w.blocked).map(obj).filter((b): b is Obj => !!b)
  if (blockedWhy) out.push(line('fail', `Blocked issues: ${blockedWhy}`))
  if (blocked.length) {
    tables.push({ key: 'waiting-blocked', head: ['Blocked issue', 'Since'],
      rows: blocked.map(b => [`#${num(b.number) ?? '?'} ${str(b.title) ?? ''}`, day(str(b.updated))]),
      tones: blocked.map(() => 'fail') })
    for (const b of blocked) if (str(b.note)) out.push(line('quiet', `#${num(b.number) ?? '?'}: ${str(b.note)}`))
  }
  if (!tables.length && !out.length) out.push(line('pass', 'Nothing waiting on you'))
  return { key: 'waiting', title: 'Waiting on you', lines: out, tables }
}

const total = (v: unknown): { tokens: number | null; cost: number | null } => {
  const o = obj(v)
  return { tokens: num(o?.tokens), cost: num(o?.cost_usd) }
}

// The loop's spend as tables: today, the last 7 days, since the document's date and per pull
// request; the costliest issues; each model; and, when the script gives it, what merged by type and
// what the loop spent on it. Then when its records start, if after that date, and the day-by-day chart.
export function spend(doc: Doc): Section {
  const why = missing(doc.loop_spend)
  const s = obj(doc.loop_spend)
  if (why || !s) return { key: 'spend', title: 'Loop spend', lines: [line('quiet', why ?? 'not in this script')] }
  const cells = (v: unknown): string[] => {
    const t = total(v)
    return [money(t.cost), tokens(t.tokens)]
  }
  const perPr = num(s.cost_per_pr)
  const periods: Table = { key: 'spend-periods', head: ['', 'Cost', 'Tokens'], rows: [
    ['Today', ...cells(s.today)],
    ['7 days', ...cells(s.last_7_days)],
    [`Since ${day(str(doc.since))}`, ...cells(s.since)],
    ['Per pull request', perPr === null ? 'none yet' : `~${money(perPr)}`, ''],
  ] }
  const tables = [periods]
  const issues = Object.entries(obj(s.by_issue) ?? {})
    .map(([name, v]) => ({ name, ...total(v) }))
    .sort((a, b) => (b.cost ?? -1) - (a.cost ?? -1))
    .slice(0, 5)
  if (issues.length) {
    tables.push({ key: 'spend-issues', head: ['Costliest issues', 'Cost', 'Tokens'],
      rows: issues.map(i => [i.name.replace(/(^|\/)issue-/, '$1#'), money(i.cost), tokens(i.tokens)]) })
  }
  const models = Object.entries(obj(s.by_model) ?? {})
    .map(([id, v]) => ({ id, label: str(obj(v)?.label), ...total(v) }))
    .sort((a, b) => (b.cost ?? -1) - (a.cost ?? -1))
  if (models.length) {
    tables.push({ key: 'spend-models', head: ['Model', 'Cost', 'Tokens'],
      rows: models.map(m => [m.id === 'null' ? (m.label ?? 'not recorded') : model(m.id), money(m.cost), tokens(m.tokens)]) })
  }
  const types = workByType(doc)
  tables.push(...types.tables)
  const out: Line[] = []
  const first = str(s.first_run)
  const since = str(doc.since)
  if (first && since && first > since) out.push(line('quiet', `The loop's records start ${day(first)}`))
  // The chart starts where the records do: the days before hold nothing to show.
  const points = series(s.by_day, 'cost_usd')?.filter(p => !first || p.date >= first) ?? null
  if (!points?.length) out.push(NO_DAILY)
  out.push(...types.lines)
  out.push(line('quiet', "Claude Code's estimate at API prices, not a bill"))
  if (!points?.length) return { key: 'spend', title: 'Loop spend', lines: out, tables }
  const alt = `The loop's estimated spend each day, ${day(points[0]?.date ?? null)} to ${day(points[points.length - 1]?.date ?? null)}`
  const used = new Map((series(s.by_day, 'tokens') ?? []).map(p => [p.date, p.value]))
  const labels = points.map(p => [day(p.date), money(p.value), tokens(used.get(p.date) ?? null)])
  return { key: 'spend', title: 'Loop spend', lines: out, tables,
    chart: { key: 'spend-chart', alt, caption: daily(points, money).text, points, unit: 'money', columns: ['Day', 'Cost', 'Tokens'], labels } }
}

// What the period's merges were, by type, and what the loop spent on the issues they close: a row for
// bug, enhancement, documentation and chore, then Untyped, a cost the records don't give as ?. A section
// the script couldn't fill says why in a line, and a search that stopped at its limit says the counts are
// low. A script that doesn't give the section draws nothing for it.
export function workByType(doc: Doc): { tables: Table[]; lines: Line[] } {
  if (doc.work_by_type === undefined) return { tables: [], lines: [] }
  const why = missing(doc.work_by_type)
  const w = obj(doc.work_by_type)
  const rows = list(w?.types).map(obj).filter((r): r is Obj => !!r)
  if (why || !w || !rows.length) return { tables: [], lines: [line('quiet', `Work by type: ${why ?? "couldn't read it"}`)] }
  const name = (v: unknown) => {
    const kind = str(v)
    return kind ? kind[0]!.toUpperCase() + kind.slice(1) : 'Untyped'
  }
  const table: Table = { key: 'spend-types', head: ['Merged by type', 'Merged', 'By the loop', 'Cost'],
    rows: rows.map(r => [name(r.type), String(num(r.merged) ?? '?'), String(num(r.loop_built) ?? '?'), money(num(r.cost_usd))]) }
  const lines = w.truncated === true ? [line('now', 'Work by type: the search hit its limit, so counts are low')] : []
  return { tables: [table], lines }
}

// How the loop's recent issues ended, then how many of its merged pull requests needed a commit from
// someone else first, split into fixes and merges from main, then how long each stage takes.
export function throughput(doc: Doc): Section {
  const out: Line[] = []
  const tables: Table[] = []
  const tWhy = missing(doc.loop_throughput)
  const t = obj(doc.loop_throughput)
  if (tWhy || !t) out.push(line('quiet', `Issues: ${tWhy ?? 'not in this script'}`))
  else {
    const states = Object.entries(obj(t.by_state) ?? {}).map(([name, n]) => [name === 'pr' ? 'Opened a pull request' : name[0]!.toUpperCase() + name.slice(1), String(num(n) ?? '?')])
    const again = num(t.more_than_one_round)
    tables.push({ key: 'throughput-issues', head: [`${num(t.issues) ?? '?'} recent issues`, 'Count'],
      rows: [...states, ...(again === null ? [] : [['Took more than one round', String(again)]])] })
  }
  const rWhy = missing(doc.loop_rework)
  const r = obj(doc.loop_rework)
  if (rWhy || !r) out.push(line('quiet', `Rework: ${rWhy ?? 'not in this script'}`))
  else {
    const merged = num(r.merged)
    const reworked = list(r.pull_requests).map(obj).filter((p): p is Obj => !!p)
    const mergeOnly = reworked.filter(p => (num(p.other_commits) ?? 0) === 0).length
    if (merged === null) out.push(line('quiet', "Rework: couldn't read it"))
    else if (!merged) out.push(line('quiet', `No loop pull requests merged since ${day(str(doc.since))}`))
    else {
      const pct = Math.round((reworked.length / merged) * 100)
      tables.push({ key: 'throughput-rework', head: ['Merged loop pull requests', 'Count'], rows: [
        ['Merged', String(merged)],
        ['Needed a commit first', `${reworked.length} (${pct}%)`],
        ['  with a fix', String(reworked.length - mergeOnly)],
        ['  only a merge from main', String(mergeOnly)],
      ], tones: ['plain', reworked.length ? 'now' : 'pass', 'plain', 'plain'] })
    }
  }
  const stages = stageTimes(doc)
  tables.push(...stages.tables)
  out.push(...stages.lines)
  return { key: 'throughput', title: 'Throughput and rework', lines: out, tables }
}

// A stage's median as a person reads it: whole minutes under an hour, then hours, to a tenth under 10.
// A stage with nothing behind it is -, never 0m.
export function duration(minutes: number | null, count: number | null): string {
  if (!count || minutes === null) return '-'
  if (Math.round(minutes) < 60) return `${Math.round(minutes)}m`
  const hours = minutes / 60
  return hours < 10 ? `${hours.toFixed(1)}h` : `${Math.round(hours)}h`
}

const STEPS = [['SHAPE', 'Shape'], ['BUILD', 'Build'], ['VALIDATE', 'Validate'], ['SCALE', 'Scale']] as const

// The median time at each of the loop's steps, then to a first review and to merging, as one table with
// how many each rests on, the slowest stage marked and in yellow. A table, not a line: six stages don't
// fit the pane's 66 columns. A half the script couldn't read says why in place of its rows. A script
// that doesn't give stage times draws nothing for them.
export function stageTimes(doc: Doc): { tables: Table[]; lines: Line[] } {
  if (doc.stage_times === undefined) return { tables: [], lines: [] }
  const whole = missing(doc.stage_times)
  const s = obj(doc.stage_times)
  if (whole || !s) return { tables: [], lines: [line('quiet', `Stage times: ${whole ?? "couldn't read them"}`)] }
  const slowest = str(s.slowest)
  const rows: string[][] = []
  const tones: Tone[] = []
  const out: Line[] = []
  const add = (key: string, label: string, minutes: number | null, count: number | null) => {
    rows.push([key === slowest ? `${label} (slowest)` : label, duration(minutes, count), String(count ?? '?')])
    tones.push(key === slowest ? 'now' : 'plain')
  }
  const stepsWhy = missing(s.loop_steps)
  const steps = obj(s.loop_steps)
  if (stepsWhy || !steps) out.push(line('quiet', `Loop step times: ${stepsWhy ?? "couldn't read them"}`))
  else for (const [key, label] of STEPS) {
    const step = obj(steps[key])
    add(key, label, num(step?.median_minutes), num(step?.issues))
  }
  const prsWhy = missing(s.pull_requests)
  const prs = obj(s.pull_requests)
  if (prsWhy || !prs) out.push(line('quiet', `Pull request times: ${prsWhy ?? "couldn't read them"}`))
  else {
    const minutes = (v: unknown) => {
      const hours = num(v)
      return hours === null ? null : hours * 60
    }
    add('first_review', 'First review', minutes(prs.median_hours_to_first_review), num(prs.reviewed))
    add('merge', 'Merge', minutes(prs.median_hours_to_merge), num(prs.merged))
  }
  const tables: Table[] = rows.length ? [{ key: 'throughput-stages', head: ['Stage times', 'Median', 'Count'], rows, tones }] : []
  return { tables, lines: out }
}

// Each reviewer's newest saved eval as a table row, red when a case fails and yellow when it's stale,
// then each failing case and stale reason under it.
export function evals(doc: Doc): Section {
  const why = missing(doc.evals)
  const e = obj(doc.evals)
  if (why || !e) {
    const lines = [line('quiet', why ?? 'not in this script')]
    if (why === 'no saved evals') lines.push(line('quiet', 'python3 scripts/eval_agents.py --save saves one'))
    return { key: 'evals', title: 'Evals', lines }
  }
  const rows: string[][] = []
  const tones: Tone[] = []
  const out: Line[] = []
  for (const [reviewer, v] of Object.entries(e)) {
    const r = obj(v)
    if (!r) continue
    // A count it couldn't read is ?, in yellow: never 0, which would read as passing.
    const failing = num(r.failing)
    const stale = r.stale === true ? 'yes' : r.stale === false ? 'no' : 'unknown'
    rows.push([reviewer, String(num(r.stable) ?? '?'), String(num(r.flaky) ?? '?'), String(failing ?? '?'), day(str(r.saved)), stale])
    tones.push(failing ? 'fail' : failing === null || r.stale === true || (num(r.flaky) ?? 0) ? 'now' : 'plain')
    const cases = list(r.failing_cases).filter((c): c is string => typeof c === 'string')
    if (cases.length) out.push(line('fail', `${reviewer} failing: ${cases.join(', ')}`))
    if (r.stale === true) {
      const changed = list(r.changed).length
      const reason = str(r.why) ?? (changed ? `${changed} file${changed === 1 ? '' : 's'} changed, newest ${day(str(r.newest_change))}` : 'changed')
      out.push(line('now', `${reviewer} stale: ${reason}. Run it again`))
    } else if (r.stale === null && str(r.why)) out.push(line('quiet', `${reviewer} stale unknown: ${str(r.why)}`))
  }
  if (!rows.length) return { key: 'evals', title: 'Evals', lines: [line('quiet', 'no reviewers')] }
  return { key: 'evals', title: 'Evals', lines: out,
    tables: [{ key: 'evals-reviewers', head: ['Reviewer', 'Stable', 'Flaky', 'Failing', 'Saved', 'Stale'], rows, tones }] }
}

// Claude Code's own tokens: a table of the factory and the loop's worktrees, one of the biggest
// models on each side, then the day-by-day chart.
export function conversations(doc: Doc): Section {
  const why = missing(doc.conversations)
  const c = obj(doc.conversations)
  if (why || !c) return { key: 'conversations', title: 'Conversations', lines: [line('quiet', why ?? 'not in this script')] }
  const sides = [['factory', 'Factory'], ['loop', 'Loop worktrees']] as const
  const totals = (side: string) => {
    const by = obj(obj(c[side])?.by_model) ?? {}
    return new Map(Object.entries(by).map(([id, v]) => [id, num(obj(v)?.total) ?? 0] as const).filter(([, n]) => n > 0))
  }
  const per = { factory: totals('factory'), loop: totals('loop') }
  const tables: Table[] = [{ key: 'conversations-sides', head: ['', 'Tokens', 'Sessions'],
    rows: sides.filter(([side]) => obj(c[side])).map(([side, label]) =>
      [label, tokens([...per[side].values()].reduce((a, n) => a + n, 0)), String(num(obj(c[side])?.sessions) ?? '?')]) }]
  const ids = [...new Set([...per.factory.keys(), ...per.loop.keys()])]
    .sort((a, b) => ((per.factory.get(b) ?? 0) + (per.loop.get(b) ?? 0)) - ((per.factory.get(a) ?? 0) + (per.loop.get(a) ?? 0)))
    .slice(0, 4)
  if (ids.length) {
    tables.push({ key: 'conversations-models', head: ['Model', 'Factory', 'Loop'],
      rows: ids.map(id => [model(id), tokens(per.factory.get(id) ?? 0), tokens(per.loop.get(id) ?? 0)]) })
  }
  const out = [line('quiet', `Since ${day(str(doc.since))}, cache reads included`)]
  const points = sum(series(obj(c.factory)?.by_day, 'tokens'), series(obj(c.loop)?.by_day, 'tokens'))
  if (!points) return { key: 'conversations', title: 'Conversations', lines: [...out, NO_DAILY], tables }
  const alt = `Claude Code's tokens each day, factory and loop together, ${day(points[0]?.date ?? null)} to ${day(points[points.length - 1]?.date ?? null)}`
  const labels = points.map(p => [day(p.date), tokens(p.value)])
  return { key: 'conversations', title: 'Conversations', lines: out, tables,
    chart: { key: 'conversations-chart', alt, caption: daily(points, n => `${tokens(n)} tokens`).text, points, unit: 'tokens', columns: ['Day', 'Tokens'], labels } }
}

// The top few names in a { name: count } object, as table rows, most used first.
function top(v: unknown, n = 5): string[][] {
  return Object.entries(obj(v) ?? {})
    .map(([name, c]) => ({ name, c: num(c) ?? 0 }))
    .sort((a, b) => b.c - a.c)
    .slice(0, n)
    .map(e => [e.name, String(e.c)])
}

// Oct 27 12:00, read from an ISO time's own text: hhmm() would give each machine's own zone.
function stamp(text: string | null): string {
  const clock = text ? /T(\d{2}:\d{2})/.exec(text)?.[1] : null
  return clock ? `${day(text)} ${clock}` : day(text)
}

// What the estimate rests on. Several lines, each within the 66 columns the terminal's pane has,
// because a line wider than the pane is clipped. The last says what to do when no model has a price
// only because there's no price file. A model missing from a file that exists is the README's to explain.
function estimate(a: Obj): Line[] {
  const whys = Object.values(obj(a.unpriced) ?? {})
  return [
    line('quiet', `Est. cost: an estimate from .sanvio/prices.json, checked ${day(str(a.prices_checked))},`),
    line('quiet', `worked out ${stamp(str(a.spend_at))}. Skills' and commands' tokens are`),
    line('quiet', 'attributed from where each started to the next prompt.'),
    ...(whys.length && whys.every(w => w === 'no prices.json') ? [line('quiet', 'Fill .sanvio/prices.json to see dollars')] : []),
  ]
}

// Days after a log review when the next one is due: the review is monthly.
const REVIEW_DUE = 30

// When the person last ran the monthly log review, usage_report.py --review. Nothing from a script that
// doesn't say. None yet is two lines, so the command fits the pane's 66 columns.
function lastReview(doc: Doc): Line[] {
  if (doc.last_review === undefined) return []
  const why = missing(doc.last_review)
  if (why === 'no review yet') {
    return [line('quiet', 'Last log review: none yet'), line('quiet', 'python3 scripts/usage_report.py --review runs one')]
  }
  const r = obj(doc.last_review)
  const days = num(r?.days_since)
  if (why || !r || days === null) return [line('quiet', `Last log review: ${why ?? "couldn't read it"}`)]
  return [line(days > REVIEW_DUE ? 'now' : 'quiet', `Last log review: ${day(str(r.date))}, ${days} ${days === 1 ? 'day' : 'days'} ago`)]
}

// What the harness did in the person's sessions, a table each: skills, agents, commands and what the
// guard refused, then how often it asked, then when the logs were last reviewed. A script that says what
// each name spent adds its tokens and estimated cost, ? where it has no figure, and what the estimate rests on.
export function activity(doc: Doc): Section {
  const why = missing(doc.activity)
  const a = obj(doc.activity)
  if (why || !a) return { key: 'activity', title: 'Activity', lines: [line('quiet', why ?? 'not in this script'), ...lastReview(doc)] }
  const tables: Table[] = []
  let estimated = false
  for (const [field, label, spentField] of [['skills', 'Skill', 'skill_spend'], ['agents', 'Agent', 'agent_spend'], ['commands', 'Command', 'command_spend'], ['guard_refusals', 'Guard refused', null]] as const) {
    const rows = top(a[field])
    if (!rows.length) continue
    const spent = spentField && obj(a[spentField])
    estimated ||= !!spent
    tables.push({ key: `activity-${field}`, head: spent ? [label, 'Times', 'Tokens', 'Est. cost'] : [label, 'Times'],
      rows: spent ? rows.map(r => {
        const t = total(spent[r[0]!])
        return [...r, tokens(t.tokens), money(t.cost)]
      }) : rows,
      tones: field === 'guard_refusals' ? rows.map(() => 'now') : undefined })
  }
  const out = [...(estimated ? estimate(a) : []), line('quiet', `Guard asked ${num(a.asks) ?? 0} times, since ${day(str(doc.since))}`)]
  if (!tables.length) out.unshift(line('quiet', 'Nothing used yet'))
  return { key: 'activity', title: 'Activity', lines: [...out, ...lastReview(doc)], tables }
}

// The sections in the pane's order: what needs the person first.
export function sections(doc: Doc): Section[] {
  return [waiting(doc), spend(doc), throughput(doc), evals(doc), conversations(doc), activity(doc)]
}

// What a refresh came to: the document, or a few words on why there's none.
export function outcome(run: { exitCode: number; stdout: string; isStdoutTruncated: boolean } | null): { doc: Doc } | { failure: string } {
  if (!run) return { failure: "the script didn't finish" }
  if (run.exitCode !== 0) return { failure: `the script exited ${run.exitCode}` }
  if (run.isStdoutTruncated) return { failure: 'the output was cut off' }
  const doc = parseDoc(run.stdout)
  return doc ? { doc } : { failure: "the output wasn't the dashboard's JSON" }
}

// Fit one line to the pane, with an ellipsis where it was cut.
export function clip(text: string, width: number): string {
  if (width < 2) return ''
  return text.length <= width ? text : text.slice(0, width - 1) + '…'
}

// The nearest folder at or above `from` that holds the dashboard script. None means nothing to show.
export async function findRoot(from: string, exists: (path: string) => Promise<boolean>): Promise<string | null> {
  let dir = from.replace(/\/+$/, '')
  while (dir) {
    if (await exists(`${dir}/${SCRIPT}`)) return dir
    dir = dir.slice(0, dir.lastIndexOf('/'))
  }
  return null
}
