// The pane's decisions as plain functions, so they can be tested without a session.
import type { QueueItem, Row, Seen, Status, Tab } from '../types'

export type Tone = 'now' | 'pass' | 'fail' | 'quiet' | 'idle'
export type Line = { tone: Tone; text: string }

export const PROJECTS_DIR = '.loop/projects'
export const SCRIPT = 'scripts/loop.py'

// The folder under the root holding one loop's files: the factory's, or a project's.
export function loopDir(project?: string): string {
  return project ? `${PROJECTS_DIR}/${project}` : '.loop'
}

// The projects with a loop to show, by name: folders under PROJECTS_DIR that hold a status file.
export async function projectNames(entries: { name: string; kind: string }[], hasStatus: (name: string) => Promise<boolean>): Promise<string[]> {
  const folders = entries.filter(e => e.kind === 'dir').map(e => e.name).sort((a, b) => a.localeCompare(b))
  const held = await Promise.all(folders.map(name => hasStatus(name)))
  return folders.filter((_, i) => held[i])
}

// The loop to open on: the project in focus when it's listed, else the first one running, factory
// first, else the factory.
export function openingLoop(loops: Seen[], focus?: string | null): Seen | undefined {
  const focused = focus ? loops.find(l => l.project === focus) : undefined
  return focused ?? loops.find(l => l.isLocked) ?? loops[0]
}

// The session's project focus, by github-status's rules. One installed mod can't import from another,
// so these are copies of its projectName, SESSION, focusFile and focusName, with the same bodies. Within
// this mod they're the only copies: the Crew view imports them from here.

// The folder under projects/ that a /github argument names: `acme` or `projects/acme`, one folder deep.
// Anything that could reach outside projects/ is refused before anything runs.
export function projectName(arg: string): { name: string } | { why: string } {
  const name = arg.trim().replace(/^projects\//, '').replace(/\/$/, '')
  if (/^[A-Za-z0-9_][A-Za-z0-9_.-]*$/.test(name) && !name.includes('..')) return { name }
  return { why: `"${arg.trim()}" isn't a project: give the name of a folder under projects/, such as /github acme, or /github all.` }
}

// A session id that can name a file: harness-lens's rule. Anything else means no focus.
export const SESSION = /^[0-9a-fA-F-]{8,64}$/

// This session's focus file under the harness root, or null for an id that can't name one.
export function focusFile(root: string, id: string | null): string | null {
  return id !== null && SESSION.test(id) ? `${root}/.sanvio/project/${id}` : null
}

// The project a focus file's text names, before the folder is checked, or null.
export function focusName(text: string): string | null {
  const picked = projectName(text.trim())
  return 'name' in picked ? picked.name : null
}

// What a loop is called: the project's name, or the root's folder for the factory.
export function loopLabel(seen: Seen): string {
  return seen.project ?? seen.root.split('/').filter(Boolean).pop() ?? seen.root
}

// How many jobs a live loop is on. The lock is the truth about running, so with no live lock it's
// none, whatever the file's rows say. A stop request doesn't change it: those jobs are still being worked.
export function workingCount(seen: Seen): number {
  if (!seen.isLocked) return 0
  return seen.status?.issues.filter(r => r.state === 'working').length ?? 0
}

// What a loop's button says: its name, with a marker while it's on a job and a count past one.
export function loopButtonLabel(seen: Seen): string {
  const working = workingCount(seen)
  if (!working) return loopLabel(seen)
  return `● ${loopLabel(seen)}${working > 1 ? ` ${working}` : ''}`
}

// The loop picker's options: the loops on a job first, each group in its own order. A project's
// value is its name, the factory's ''.
export function loopOptions(loops: Seen[]): { value: string; label: string }[] {
  const working = loops.filter(l => workingCount(l) > 0)
  const rest = loops.filter(l => workingCount(l) === 0)
  return [...working, ...rest].map(loop => ({ value: loop.project ?? '', label: loopButtonLabel(loop) }))
}

// What sits beside the dropdown, whose closed face shows only the loop on screen: how many loops are on
// a job and how many live ones have issues waiting, the one on screen included, so a loop can count in
// both. A stopped loop's old queue doesn't count. Null when both are none.
export function loopCounts(loops: Seen[]): string | null {
  const running = loops.filter(l => workingCount(l) > 0).length
  const queued = loops.filter(l => l.isLocked && waiting(l.status).length > 0).length
  if (running && queued) return `● ${running} running · ${queued} queued`
  if (running) return `● ${running} running`
  if (queued) return `${queued} queued`
  return null
}

const STEPS: Record<string, string> = {
  SHAPE: 'planning',
  BUILD: 'building',
  VALIDATE: 'checking',
  SCALE: 'opening the pull request',
}

const ENDED: Record<string, { tone: Tone; text: string }> = {
  pr: { tone: 'pass', text: 'pull request open' },
  blocked: { tone: 'fail', text: 'blocked' },
  stopped: { tone: 'quiet', text: 'stopped' },
  skipped: { tone: 'quiet', text: 'skipped' },
}

const str = (v: unknown): string => (typeof v === 'string' ? v : '')
const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
const orNull = (v: unknown): string | null => (typeof v === 'string' && v ? v : null)
const positive = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : undefined)
// Whether an object has a key of its own, so a key named like Object's own properties never counts.
export const has = (o: object, key: string): boolean => Object.prototype.hasOwnProperty.call(o, key)

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
// Both views read it here: the List draws every field, the Crew its step, round, times and run fields.
export function parseStatus(text: string | null): Status | null {
  if (!text) return null
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return null
  }
  if (!raw || typeof raw !== 'object') return null
  const data = raw as Record<string, unknown>
  const queue: QueueItem[] = (Array.isArray(data.queue) ? data.queue : [])
    .filter((q): q is Record<string, unknown> => !!q && typeof q === 'object' && num((q as Record<string, unknown>).number) > 0)
    .map(q => {
      const item: QueueItem = { number: num(q.number), title: str(q.title) }
      const on = Array.isArray(q.waiting_on) ? q.waiting_on.filter(n => num(n) > 0) : []
      if (on.length) item.waiting_on = on
      return item
    })
  const issues: Row[] = (Array.isArray(data.issues) ? data.issues : [])
    .filter((r): r is Record<string, unknown> => !!r && typeof r === 'object' && num((r as Record<string, unknown>).number) > 0)
    .map(r => ({
      number: num(r.number),
      title: str(r.title),
      step: str(r.step),
      state: str(r.state),
      round: num(r.round),
      max_rounds: num(r.max_rounds) || undefined,
      tests: orNull(r.tests),
      review: orNull(r.review),
      pr: orNull(r.pr),
      note: str(r.note),
      started: orNull(r.started) ?? undefined,
      updated: orNull(r.updated) ?? undefined,
      window: orNull(r.window) ?? undefined,
      tokens: positive(r.tokens),
      cost_usd: positive(r.cost_usd),
      model: orNull(r.model) ?? undefined,
      ...timeFields(r),
    }))
  return {
    running: data.running === true, updated: orNull(data.updated), tmux: orNull(data.tmux),
    started: orNull(data.started), queue, issues,
  }
}

// The first line of the pane. The lock is the truth about running: the file's own flag can be left
// true by a run that was killed.
export function headline(seen: Seen): Line {
  if (seen.isLocked && seen.isStopping) return { tone: 'now', text: 'Stopping after this step' }
  if (seen.isLocked) return { tone: 'now', text: 'Running' }
  if (seen.isStaleLock) return { tone: 'fail', text: 'Not running. The last run was killed and left its lock behind' }
  if (!seen.status) return { tone: 'quiet', text: "Hasn't run here yet" }
  if (seen.status.running) return { tone: 'fail', text: "Not running. The last run didn't finish cleanly" }
  return { tone: 'quiet', text: 'Not running' }
}

export type Header = { left: string; right: Line; isPulsing: boolean; wraps: boolean; rows: [string, string] }

// The pane's top: the loop's name on the left, its state on the right. Always two rows: the state
// drops to the second when both don't fit on the first, and the second stays blank when they do, so
// nothing below moves as the state changes. The state's dot pulses while the loop is on a job, like
// that job's own dot.
export function header(seen: Seen, now: number, width: number): Header {
  const left = loopLabel(seen)
  const right = loopState(seen, now)
  const isPulsing = seen.isLocked && !seen.isStopping && !!seen.status?.issues.some(r => r.state === 'working')
  const wraps = left.length + 1 + right.text.length > width
  if (wraps) {
    const state = { tone: right.tone, text: clip(right.text, width) }
    return { left: clip(left, width), right: state, isPulsing, wraps, rows: [clip(left, width), state.text] }
  }
  return { left, right, isPulsing, wraps, rows: [left + ' '.repeat(width - left.length - right.text.length) + right.text, ''] }
}

// The header's state. Running counts the jobs being worked, and says so past one; a run with none is
// idle. Up is how long this run has held the lock, from a loop.py that writes when it started.
function loopState(seen: Seen, now: number): Line {
  const from = seen.status?.started ? Date.parse(seen.status.started) : Number.NaN
  const up = Number.isFinite(from) ? ` · up ${duration(now - from)}` : ''
  if (seen.isLocked && seen.isStopping) return { tone: 'now', text: '● Stopping after this step' }
  if (seen.isLocked) {
    const working = workingCount(seen)
    if (!working) return { tone: 'idle', text: `● Idle${up}` }
    return { tone: 'now', text: `● Running${working > 1 ? ` ${working}` : ''}${up}` }
  }
  const line = headline(seen)
  return { tone: line.tone, text: `○ ${line.text}` }
}

// The command that opens the tmux session a running loop is in, or null. A session named by a run
// that's no longer alive is gone, so it isn't offered.
export function attach(seen: Seen): string | null {
  const name = seen.status?.tmux
  if (!seen.isLocked || !name) return null
  return /^[\w.@%+=:,-]+$/.test(name) ? `tmux attach -t ${name}` : `tmux attach -t '${name.replace(/'/g, `'\\''`)}'`
}

// The file that opens a window on the running loop's tmux session, read-only, or null. loop.py
// writes it only on macOS inside tmux, so elsewhere, or with an older loop.py, there's no button.
export function watch(seen: Seen): string | null {
  return attach(seen) && seen.hasWatchFile ? `${seen.root}/${loopDir(seen.project)}/watch.command` : null
}

// What the window runs, to copy when it can't open: read-only, and the name matched exactly. Always
// quoted, because zsh reads a word starting with = as a command lookup.
export function watchCommand(seen: Seen): string | null {
  const name = seen.status?.tmux
  return attach(seen) && name ? `tmux attach -r -t '=${name.replace(/'/g, `'\\''`)}'` : null
}

// The file that opens a window on one job's tmux window, read-only, under the root. loop.py writes it
// only on macOS, when it opens the window, and removes it when the window closes.
export function jobWatchFile(n: number, project?: string): string {
  return `${loopDir(project)}/issue-${n}/watch.command`
}

// What that file runs, to copy when it can't open, or null when the job has no window in a live run.
export function jobAttach(seen: Seen, row: Row): string | null {
  const name = seen.status?.tmux
  if (!attach(seen) || !name || !row.window) return null
  return `tmux attach -r -t '=${`${name}:${row.window}`.replace(/'/g, `'\\''`)}'`
}

// Whether a pull request link is safe to hand to an opener, which would also run a local file or app.
export function isWebLink(link: string): boolean {
  return link.startsWith('https://')
}

// What a queued issue waits on, beside its title: the open issues it depends on. Null when nothing.
export function waitingOn(item: QueueItem): string | null {
  const on = item.waiting_on ?? []
  return on.length ? `waiting on ${on.map(n => `#${n}`).join(', ')}` : null
}

// The fewest jobs in view at once on Active and Finished, the rest scrolling. Queue fits its lines to the same rows.
export const PAGE = 3
// How long a finished job stays on the Finished tab.
export const FINISHED_MS = 24 * 60 * 60 * 1000

export const TABS: { tab: Tab; label: string }[] = [
  { tab: 'queue', label: 'Queue' },
  { tab: 'active', label: 'Active' },
  { tab: 'finished', label: 'Finished' },
]

export type Lists = { queue: QueueItem[]; active: Row[]; finished: Row[] }

// The three tabs' lists. A finished job counts from its last update, which loop.py writes in local
// time; one with no time, or older than a day, is left out.
export function lists(status: Status | null, now: number): Lists {
  const rows = status?.issues ?? []
  const finished = rows.filter(r => {
    if (!ENDED[r.state]) return false
    const at = r.updated ? Date.parse(r.updated) : Number.NaN
    return Number.isFinite(at) && now - at <= FINISHED_MS
  })
  return { queue: waiting(status), active: rows.filter(r => !ENDED[r.state]), finished }
}

// The tab to open on: what's being worked, else what's waiting, else what finished.
export function firstTab(l: Lists): Tab {
  if (l.active.length) return 'active'
  if (l.queue.length) return 'queue'
  return 'finished'
}

// Up to `size` items from `start`, with `start` kept inside the list, and how many sit either side.
export function page<T>(items: T[], start: number, size: number): { shown: T[]; start: number; above: number; below: number } {
  const from = Math.max(0, Math.min(Math.trunc(start) || 0, items.length - size))
  const shown = items.slice(from, from + size)
  return { shown, start: from, above: from, below: items.length - from - shown.length }
}

// Ready issues not already being worked on.
export function waiting(status: Status | null): QueueItem[] {
  if (!status) return []
  const busy = new Set(status.issues.filter(r => r.state === 'working').map(r => r.number))
  return status.queue.filter(q => !busy.has(q.number))
}

// One issue: what it's on, or how it ended, and the last round's results under it.
export function describe(row: Row, isRunning: boolean): { head: Line; detail: string | null } {
  const ended = ENDED[row.state]
  let head: Line
  if (ended) {
    head = ended
  } else if (row.state === 'working' && !isRunning) {
    head = { tone: 'fail', text: `left at ${STEPS[row.step] ?? 'an unknown step'}` }
  } else {
    const step = STEPS[row.step] ?? (row.step.toLowerCase() || 'starting')
    const round = row.round > 0 ? `, round ${row.round}${row.max_rounds ? ` of ${row.max_rounds}` : ''}` : ''
    head = { tone: 'now', text: step + round }
  }
  const results = [row.tests && `tests ${row.tests}`, row.review && `review ${row.review}`].filter(Boolean).join(', ')
  const detail = [results, row.state === 'pr' ? '' : row.note].filter(Boolean).join('. ')
  return { head, detail: detail || null }
}

// The dot beside a job: whether it pulses, and its colour. It pulses only while the loop is alive and
// on that job, so a run that dies mid-step stops it, the same moment the row turns red.
export function dot(row: Row, isRunning: boolean): { tone: Tone; isPulsing: boolean } {
  const ended = ENDED[row.state]
  if (ended) return { tone: ended.tone, isPulsing: false }
  if (row.state === 'working' && !isRunning) return { tone: 'fail', isPulsing: false }
  return { tone: 'now', isPulsing: true }
}

// Whether any dot is pulsing, so the pane only redraws fast while one is.
export function isPulsing(seen: Seen | null): boolean {
  return !!seen?.isLocked && !!seen.status?.issues.some(r => dot(r, true).isPulsing)
}

const pad = (n: number): string => String(n).padStart(2, '0')
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// How long, the way a person reads it: 42s, 6m 05s, 1h 04m.
export function duration(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${pad(s % 60)}s`
  return `${Math.floor(m / 60)}h ${pad(m % 60)}m`
}

// What a job has used, over every run: 840k tokens · ~$3.40. The cost is Claude Code's estimate at API
// prices and shows only beside tokens. Null when the row has none, as from an older loop.py.
export function usage(row: Row): string | null {
  const t = row.tokens
  if (t === undefined || !(t > 0)) return null
  const whole = Math.round(t)
  const thousands = Math.round(whole / 1000)
  const tokens = whole < 1000 ? String(whole) : thousands < 1000 ? `${thousands}k` : `${(whole / 1_000_000).toFixed(1)}M`
  return `${tokens} tokens${row.cost_usd && row.cost_usd > 0 ? ` · ~$${row.cost_usd.toFixed(2)}` : ''}`
}

// The model a job's latest run used, with a leading claude- dropped: opus-5-5. Any other id, an
// ollama model's say, shows whole. Null when the row has none, as from a loop.py older than #257.
export function modelName(row: Row): string | null {
  if (!row.model) return null
  return row.model.startsWith('claude-') ? row.model.slice('claude-'.length) : row.model
}

// When a job started and how long it has been running, or took, then what it has used, then its
// model. loop.py writes local time with no zone, which Date.parse reads as local too. A start on
// another day carries its date. A row from an older loop.py has no start, so no clock.
export function clock(row: Row, isRunning: boolean, now: number): string | null {
  const from = row.started ? Date.parse(row.started) : Number.NaN
  if (!Number.isFinite(from)) return null
  const at = new Date(from)
  const time = `${pad(at.getHours())}:${pad(at.getMinutes())}`
  const when = at.toDateString() === new Date(now).toDateString() ? time : `${MONTHS[at.getMonth()]} ${at.getDate()} ${time}`
  const end = row.updated ? Date.parse(row.updated) : Number.NaN
  let line = `started ${when}`
  if (dot(row, isRunning).isPulsing) line += ` · running ${duration(now - from)}`
  else if (Number.isFinite(end)) line += ` · ${ENDED[row.state] ? 'took' : 'ran'} ${duration(end - from)}`
  return [line, usage(row), modelName(row)].filter(Boolean).join(' · ')
}

// A short line for each issue that has just reached an end: a pull request, a block or a stop.
// The first look has nothing to compare with, so it says nothing: opening the pane isn't news. A
// project's line starts with its name, since its loop may not be the one on screen.
export function changes(before: Status | null, after: Status | null, project?: string): string[] {
  if (!before || !after) return []
  const was = new Map((before?.issues ?? []).map(r => [r.number, r.state]))
  const from = project ? `${project}:` : 'Loop:'
  const out: string[] = []
  for (const row of after.issues) {
    if (was.get(row.number) === row.state) continue
    if (row.state === 'pr') out.push(`${from} #${row.number} has a pull request`)
    else if (row.state === 'blocked') out.push(`${from} #${row.number} is blocked`)
    else if (row.state === 'stopped') out.push(`${from} #${row.number} stopped`)
  }
  return out
}

// The process id in .loop/lock, or null when it isn't a number.
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

// Whether two looks differ in anything the pane draws.
export function sameSeen(a: Seen | null, b: Seen | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}
