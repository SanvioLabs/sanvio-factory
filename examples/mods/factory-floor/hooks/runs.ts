// The Tests section's decisions as plain functions: which test suite runs it shows, how each reads, and
// what it says when one ends. The runs come from scripts/run_tests.py's files in .sanvio/tests/.
import { duration, startedWhen } from './logic'
import type { Line, Tone } from './logic'
import type { TestRun } from '../types'

export const TESTS_DIR = '.sanvio/tests'
// A running file not written for this long belongs to a run that has died: the runner writes at least
// every 10 seconds.
export const STALE_MS = 60_000
// How many runs that have ended stay in the section, under those still running.
export const ENDED_SHOWN = 3
// How many of the newest files each read opens. The names start with the run's start time, so they sort
// by it, and a run still going is among the newest.
export const READ_AT_MOST = 20
// The exit code of a run stopped with Ctrl-C.
export const INTERRUPTED = 130

const STATES = new Set(['running', 'passed', 'failed'])
const str = (v: unknown): string => (typeof v === 'string' ? v : '')
const orNull = (v: unknown): string | null => (typeof v === 'string' && v ? v : null)
const count = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : 0)
const countOrNull = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : null)
const time = (v: string | null): number => (v ? Date.parse(v) : Number.NaN)

// The file names a read opens: the newest READ_AT_MOST .json files.
export function runFiles(entries: { name: string; kind: string }[]): string[] {
  return entries
    .filter(e => e.kind === 'file' && e.name.endsWith('.json'))
    .map(e => e.name)
    .sort()
    .reverse()
    .slice(0, READ_AT_MOST)
}

// One run from its file, or null for a file that isn't valid JSON or has no state or start it knows.
export function parseRun(id: string, text: string | null): TestRun | null {
  if (text === null) return null
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return null
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const r = raw as Record<string, unknown>
  if (typeof r.state !== 'string' || !STATES.has(r.state)) return null
  if (!Number.isFinite(time(orNull(r.started)))) return null
  return {
    id,
    state: r.state as TestRun['state'],
    worktree: str(r.worktree),
    branch: str(r.branch),
    started: str(r.started),
    updated: orNull(r.updated),
    ended: orNull(r.ended),
    total: countOrNull(r.total),
    ran: count(r.ran),
    failed: count(r.failed),
    skipped: count(r.skipped),
    exit_code: typeof r.exit_code === 'number' && Number.isInteger(r.exit_code) ? r.exit_code : null,
  }
}

// Still running: its file says so and was written in the last STALE_MS.
export function isLive(run: TestRun, now: number): boolean {
  const at = time(run.updated ?? run.started)
  return run.state === 'running' && Number.isFinite(at) && now - at < STALE_MS
}

const isStopped = (run: TestRun): boolean => run.exit_code === INTERRUPTED
// When a run that isn't live last moved: its end, else its last write, else its start.
const lastMoved = (run: TestRun): number => {
  for (const at of [run.ended, run.updated, run.started].map(time)) if (Number.isFinite(at)) return at
  return 0
}

// What the section lists: every live run, newest start first, then the ENDED_SHOWN that last moved most
// recently of the rest, a run that died included.
export function runsShown(runs: TestRun[], now: number): TestRun[] {
  const live = runs.filter(r => isLive(r, now)).sort((a, b) => time(b.started) - time(a.started))
  const rest = runs.filter(r => !isLive(r, now)).sort((a, b) => lastMoved(b) - lastMoved(a))
  return [...live, ...rest.slice(0, ENDED_SHOWN)]
}

// The worktree's last path part: m657 for .../scratchpad/m657.
export function runPlace(run: TestRun): string {
  const parts = run.worktree.split(/[\\/]+/).filter(Boolean)
  return parts[parts.length - 1] ?? run.worktree
}

// A run's title: m657 · loop/issue-647, or m657 on a detached head.
export function runTitle(run: TestRun): string {
  return run.branch ? `${runPlace(run)} · ${run.branch}` : runPlace(run)
}

// The run's dot: pulsing while live, green once it passed, red for anything else.
export function runDot(run: TestRun, now: number): { tone: Tone; isPulsing: boolean } {
  if (isLive(run, now)) return { tone: 'now', isPulsing: true }
  return { tone: run.state === 'passed' ? 'pass' : 'fail', isPulsing: false }
}

const progress = (run: TestRun): string => (run.total === null ? `${run.ran} run` : `${run.ran} of ${run.total}`)

// The line under the title: when it started, then how far it got or how it ended.
export function runLine(run: TestRun, now: number): Line {
  const from = time(run.started)
  const start = `started ${startedWhen(from, now)}`
  if (isLive(run, now)) return { tone: 'quiet', text: `${start} · running ${duration(now - from)} · ${progress(run)} · ${run.failed} failed` }
  if (run.state === 'running') return { tone: 'fail', text: `${start} · stopped` }
  if (isStopped(run)) return { tone: 'fail', text: `${start} · stopped at ${progress(run)}` }
  if (run.state === 'passed') return { tone: 'pass', text: `${start} · ${run.ran} passed in ${duration(lastMoved(run) - from)}` }
  return { tone: 'fail', text: `${start} · ${run.failed} failed of ${run.total ?? run.ran}` }
}

// The rows the section takes on the terminal: a blank and its heading, then two a run. None when empty.
export function runRows(shown: TestRun[]): number {
  return shown.length ? 2 + 2 * shown.length : 0
}

// A notice for each run that was running at the last read and has now ended. The first read has nothing
// to compare with, so it says nothing, and a run that died without ending says nothing either.
export function runEnded(before: TestRun[] | null, after: TestRun[]): string[] {
  if (!before) return []
  const was = new Set(before.filter(r => r.state === 'running').map(r => r.id))
  const out: string[] = []
  for (const run of after) {
    if (!was.has(run.id) || run.state === 'running') continue
    const what = isStopped(run) ? 'stopped' : run.state === 'passed' ? `${run.ran} passed` : `${run.failed} failed`
    out.push(`Tests on ${runPlace(run)}: ${what}`)
  }
  return out
}
