import { describe as group, expect, test } from 'claude-code/testing'

import { ENDED_SHOWN, READ_AT_MOST, STALE_MS, isLive, parseRun, runDot, runEnded, runFiles, runLine, runPlace, runRows, runTitle, runsShown } from './runs'
import { startedWhen } from './logic'
import type { TestRun } from '../types'

const NOW = 1_800_000_000_000
// As scripts/run_tests.py writes a time: UTC with its offset.
const iso = (ms: number) => new Date(ms).toISOString().replace('Z', '+00:00')
const MIN = 60_000

function run(over: Partial<TestRun> = {}): TestRun {
  return {
    id: '20270115-084000-4242', state: 'running', worktree: '/tmp/scratchpad/m657', branch: 'loop/issue-647',
    started: iso(NOW - 11 * MIN - 52_000), updated: iso(NOW - 2000), ended: null,
    total: 3005, ran: 1204, failed: 0, skipped: 0, exit_code: null, ...over,
  }
}
const passed = (over: Partial<TestRun> = {}) =>
  run({ state: 'passed', ran: 3005, exit_code: 0, ended: iso(NOW - 5 * MIN), updated: iso(NOW - 5 * MIN),
    started: iso(NOW - 5 * MIN - 16 * MIN - 36_000), ...over })
const failed = (over: Partial<TestRun> = {}) =>
  run({ state: 'failed', ran: 3005, failed: 2, exit_code: 1, ended: iso(NOW - MIN), updated: iso(NOW - MIN), ...over })

group('reading a run', () => {
  test('a run file reads whole, with its name less .json as its id', () => {
    const text = JSON.stringify({ ...run(), id: undefined })
    expect(parseRun('20270115-084000-4242', text)).toEqual(run())
  })
  test('a file that is not JSON, not an object, or lacks a known state or a start is left out', () => {
    for (const text of ['{not json', '[]', 'null', '"x"', JSON.stringify({ started: iso(NOW) }),
      JSON.stringify({ state: 'odd', started: iso(NOW) }), JSON.stringify({ state: 'running' }),
      JSON.stringify({ state: 'running', started: 'yesterday' })]) {
      expect(parseRun('a', text)).toBeNull()
    }
    expect(parseRun('a', null)).toBeNull()
  })
  test('missing counts read as 0, a missing total as null, and fields of the wrong type as missing', () => {
    const r = parseRun('a', JSON.stringify({ state: 'running', started: iso(NOW), total: 'many', ran: -1, branch: 7, exit_code: 1.5 }))
    expect(r).toEqual({ id: 'a', state: 'running', worktree: '', branch: '', started: iso(NOW), updated: null, ended: null,
      total: null, ran: 0, failed: 0, skipped: 0, exit_code: null })
  })
  test('a read opens the newest .json files only, newest first', () => {
    const files = Array.from({ length: READ_AT_MOST + 5 }, (_, i) => ({ name: `2027011${String(i).padStart(2, '0')}.json`, kind: 'file' }))
    const picked = runFiles([...files, { name: 'notes.txt', kind: 'file' }, { name: 'zz.json', kind: 'dir' }, { name: 'a.json.tmp', kind: 'file' }])
    expect(picked.length).toBe(READ_AT_MOST)
    expect(picked[0]).toBe(files[files.length - 1]!.name)
    expect(picked.every(n => n.endsWith('.json'))).toBe(true)
  })
})

group('which runs show', () => {
  test('a running file written in the last minute is live; one older, or one that ended, is not', () => {
    expect(isLive(run(), NOW)).toBe(true)
    expect(isLive(run({ updated: iso(NOW - STALE_MS + 1) }), NOW)).toBe(true)
    expect(isLive(run({ updated: iso(NOW - STALE_MS) }), NOW)).toBe(false)
    expect(isLive(passed(), NOW)).toBe(false)
  })
  test('live runs come first, newest start first, then the three that ended or died most recently', () => {
    const a = run({ id: 'a', started: iso(NOW - 20 * MIN) })
    const b = run({ id: 'b', started: iso(NOW - 2 * MIN) })
    const dead = run({ id: 'dead', updated: iso(NOW - 3 * MIN) })
    const old = passed({ id: 'old', ended: iso(NOW - 60 * MIN) })
    const newer = passed({ id: 'newer', ended: iso(NOW - 10 * MIN) })
    const newest = failed({ id: 'newest', ended: iso(NOW - MIN) })
    const shown = runsShown([old, a, dead, newest, b, newer], NOW).map(r => r.id)
    expect(shown).toEqual(['b', 'a', 'newest', 'dead', 'newer'])
    expect(shown.length).toBe(2 + ENDED_SHOWN)
  })
  test('with no runs the section takes no rows; otherwise a blank, its heading and two a run', () => {
    expect(runRows([])).toBe(0)
    expect(runRows([run(), passed()])).toBe(6)
  })
})

group('how a run reads', () => {
  test('a live run: its worktree and branch, then its start, clock, progress and failures, and a pulsing dot', () => {
    const r = run()
    expect(runTitle(r)).toBe('m657 · loop/issue-647')
    expect(runLine(r, NOW)).toEqual({ tone: 'quiet', text: `started ${startedWhen(Date.parse(r.started), NOW)} · running 11m 52s · 1204 of 3005 · 0 failed` })
    expect(runDot(r, NOW)).toEqual({ tone: 'now', isPulsing: true })
  })
  test('a detached head drops the branch, and a trailing slash or a Windows path still gives the last part', () => {
    expect(runTitle(run({ branch: '' }))).toBe('m657')
    expect(runPlace(run({ worktree: '/a/b/m657/' }))).toBe('m657')
    expect(runPlace(run({ worktree: 'C:\\work\\m657' }))).toBe('m657')
  })
  test('a run started on another day carries its date, as a job row does', () => {
    const r = run({ started: iso(NOW - 3 * 24 * 60 * MIN), updated: iso(NOW - 1000) })
    expect(runLine(r, NOW).text).toContain(`started ${startedWhen(Date.parse(r.started), NOW)} ·`)
    expect(startedWhen(Date.parse(r.started), NOW)).toMatch(/^[A-Z][a-z]{2} \d+ \d\d:\d\d$/)
  })
  test('a run still loading its suite shows how many ran, with no total', () => {
    expect(runLine(run({ total: null, ran: 0 }), NOW).text).toContain('· 0 run · 0 failed')
  })
  test('a passed run: a still green dot and how many passed in how long', () => {
    const r = passed()
    expect(runLine(r, NOW)).toEqual({ tone: 'pass', text: `started ${startedWhen(Date.parse(r.started), NOW)} · 3005 passed in 16m 36s` })
    expect(runDot(r, NOW)).toEqual({ tone: 'pass', isPulsing: false })
  })
  test('a failed run: a still red dot and how many failed of how many', () => {
    const r = failed()
    expect(runLine(r, NOW).text).toMatch(/ · 2 failed of 3005$/)
    expect(runLine(r, NOW).tone).toBe('fail')
    expect(runDot(r, NOW)).toEqual({ tone: 'fail', isPulsing: false })
  })
  test('a run that stopped writing shows red and stopped, not a clock', () => {
    const r = run({ updated: iso(NOW - 2 * MIN) })
    expect(runLine(r, NOW)).toEqual({ tone: 'fail', text: `started ${startedWhen(Date.parse(r.started), NOW)} · stopped` })
    expect(runDot(r, NOW)).toEqual({ tone: 'fail', isPulsing: false })
  })
  test('a run stopped with Ctrl-C shows red and how far it got, never 0 failed', () => {
    const r = failed({ exit_code: 130, ran: 1204, failed: 0 })
    expect(runLine(r, NOW).text).toMatch(/ · stopped at 1204 of 3005$/)
    expect(runLine(r, NOW).tone).toBe('fail')
    expect(runDot(r, NOW)).toEqual({ tone: 'fail', isPulsing: false })
  })
})

group('when a run ends', () => {
  test('a run seen running that has passed, failed or stopped raises one notice each', () => {
    const before = [run({ id: 'a' }), run({ id: 'b' }), run({ id: 'c' }), run({ id: 'd' })]
    const after = [passed({ id: 'a' }), failed({ id: 'b' }), failed({ id: 'c', exit_code: 130 }), run({ id: 'd' })]
    expect(runEnded(before, after)).toEqual(['Tests on m657: 3005 passed', 'Tests on m657: 2 failed', 'Tests on m657: stopped'])
  })
  test('the first read, a run already ended, a new run and one that died say nothing', () => {
    expect(runEnded(null, [passed()])).toEqual([])
    expect(runEnded([passed({ id: 'a' })], [passed({ id: 'a' })])).toEqual([])
    expect(runEnded([], [passed({ id: 'new' })])).toEqual([])
    expect(runEnded([run({ id: 'a' })], [run({ id: 'a', updated: iso(NOW - 5 * MIN) })])).toEqual([])
    expect(runEnded([run({ id: 'a' })], [])).toEqual([])
  })
})
