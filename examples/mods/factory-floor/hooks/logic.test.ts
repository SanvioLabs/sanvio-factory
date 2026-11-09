import { describe as group, expect, test } from 'claude-code/testing'

import { FINISHED_MS, attach, changes, clip, clock, describe, dot, duration, findRoot, firstTab, focusFile, focusName, header, headline, isPulsing, jobAttach, jobWatchFile, lists, lockPid, loopButtonLabel, loopDir, loopLabel, modelName, openingLoop, page, parseStatus, projectName, projectNames, sameSeen, usage, waiting, waitingOn, watch, watchCommand, workingCount } from './logic'
import type { Row, Seen, Status } from '../types'

const ROW: Row = {
  number: 12, title: 'Gate: a fee row with 0 hours passes', step: 'BUILD', state: 'working', round: 2,
  max_rounds: 5, tests: 'failed (1)', review: 'FIX', pr: null, note: '',
}

function status(rows: Row[], queue = [{ number: 12, title: 'a' }, { number: 15, title: 'b' }], running = true, tmux: string | null = null): Status {
  return { running, updated: '2026-10-09T18:19:55', tmux, queue, issues: rows }
}

function seen(s: Status | null, isLocked: boolean, isStopping = false, isStaleLock = false, hasWatchFile = false): Seen {
  return { root: '/h/starter', status: s, isLocked, isStaleLock, isStopping, hasWatchFile }
}

group('project loops', () => {
  const dir = (name: string) => ({ name, kind: 'dir' })
  const running = (project: string | undefined, isLocked: boolean): Seen => ({ ...seen(status([]), isLocked), ...(project ? { project } : {}) })
  test('a project is a folder holding a status file, sorted by name', async () => {
    const entries = [dir('zeta'), dir('never-ran'), { name: 'notes.txt', kind: 'file' }, { name: 'link', kind: 'other' }, dir('alpha')]
    const held = new Set(['zeta', 'alpha', 'notes.txt', 'link'])
    expect(await projectNames(entries, async name => held.has(name))).toEqual(['alpha', 'zeta'])
    expect(await projectNames([], async () => true)).toEqual([])
  })
  test('the pane opens on the first loop running, factory first, else the factory', () => {
    const open = (...flags: boolean[]) => {
      const [factory = false, a = false, b = false] = flags
      return openingLoop([running(undefined, factory), running('a', a), running('b', b)])?.project
    }
    expect(open(true, true, true)).toBeUndefined()
    expect(open(false, false, true)).toBe('b')
    expect(open(false, true, true)).toBe('a')
    expect(open(false, false, false)).toBeUndefined()
    expect(openingLoop([running(undefined, false), running('a', false)])).toEqual(running(undefined, false))
  })
  test('the pane opens on the project in focus when its loop is listed, and otherwise as it did', () => {
    const loops = [running(undefined, false), running('a', false), running('b', true)]
    expect(openingLoop(loops, 'a')?.project).toBe('a')
    expect(openingLoop([running(undefined, true), running('a', false)], 'a')?.project).toBe('a')
    expect(openingLoop(loops, 'gone')?.project).toBe('b')
    expect(openingLoop(loops, null)?.project).toBe('b')
    expect(openingLoop(loops)?.project).toBe('b')
    expect(openingLoop([running(undefined, false), running('a', false)], 'gone')).toEqual(running(undefined, false))
  })
  test("a project's name is its label and the header's left side; the factory keeps its folder", () => {
    expect(loopLabel(running(undefined, false))).toBe('starter')
    expect(loopLabel(running('app', false))).toBe('app')
    expect(header(running('app', true), 0, 60).left).toBe('app')
  })
  test("a project's paths sit under its own folder, and the factory's don't move", () => {
    expect(loopDir()).toBe('.loop')
    expect(loopDir('app')).toBe('.loop/projects/app')
    expect(jobWatchFile(12, 'app')).toBe('.loop/projects/app/issue-12/watch.command')
    const inTmux = { ...seen(status([ROW], undefined, true, 'loop-app'), true, false, false, true), project: 'app' }
    expect(watch(inTmux)).toBe('/h/starter/.loop/projects/app/watch.command')
  })
  test("a project's toast starts with its name, and the factory's with Loop", () => {
    const before = status([ROW])
    const after = status([{ ...ROW, state: 'pr' }, { ...ROW, number: 9, state: 'blocked' }, { ...ROW, number: 8, state: 'stopped' }])
    expect(changes(before, after, 'app')).toEqual(['app: #12 has a pull request', 'app: #9 is blocked', 'app: #8 stopped'])
    expect(changes(before, after)[0]).toBe('Loop: #12 has a pull request')
  })
})

group('the loop buttons', () => {
  const app = (s: Status | null, isLocked: boolean, isStopping = false, isStaleLock = false): Seen =>
    ({ ...seen(s, isLocked, isStopping, isStaleLock), project: 'app' })
  const two = [ROW, { ...ROW, number: 13 }]
  const state = (s: Seen) => header(s, 0, 60).right.text
  test("the label's count agrees with the header's", () => {
    expect(loopButtonLabel(app(status([ROW]), true))).toBe('● app')
    expect(state(app(status([ROW]), true))).toBe('● Running')
    expect(loopButtonLabel(app(status(two), true))).toBe('● app 2')
    expect(state(app(status(two), true))).toBe('● Running 2')
    expect(loopButtonLabel(app(status([]), true))).toBe('app')
    expect(state(app(status([]), true))).toBe('● Idle')
  })
  test("the factory's button marks its folder's name", () => {
    expect(loopButtonLabel(seen(status([ROW]), true))).toBe('● starter')
  })
  test('no status, a stale lock, no lock, or only ended rows: the name alone', () => {
    expect(loopButtonLabel(app(null, false))).toBe('app')
    expect(loopButtonLabel(app(null, true))).toBe('app')
    expect(loopButtonLabel(app(status(two, undefined, true), false, false, true))).toBe('app')
    expect(loopButtonLabel(app(status(two, undefined, true), false))).toBe('app')
    for (const ended of ['pr', 'blocked', 'stopped', 'skipped']) {
      expect(loopButtonLabel(app(status([{ ...ROW, state: ended }]), true))).toBe('app')
    }
  })
  test('a working row left by an old run counts under a new live lock, on both', () => {
    const leftover = status([{ ...ROW, started: '2026-10-01T09:00:00' }])
    expect(workingCount(app(leftover, true))).toBe(1)
    expect(loopButtonLabel(app(leftover, true))).toBe('● app')
    expect(state(app(leftover, true))).toBe('● Running')
  })
  test('stopping keeps the marker and count on the button, and none in the header', () => {
    expect(workingCount(app(status(two), true, true))).toBe(2)
    expect(loopButtonLabel(app(status(two), true, true))).toBe('● app 2')
    expect(state(app(status(two), true, true))).toBe('● Stopping after this step')
  })
})

group('the status file', () => {
  test('what loop.py writes reads back', () => {
    const text = JSON.stringify({ running: false, updated: 'x', queue: [{ number: 3, title: 't' }], issues: [ROW] })
    const parsed = parseStatus(text)
    expect(parsed?.queue).toEqual([{ number: 3, title: 't' }])
    expect(parsed?.issues[0]?.round).toBe(2)
    expect(parsed?.issues[0]?.tests).toBe('failed (1)')
  })
  test('no file, broken JSON or the wrong shape is null or empty, never a throw', () => {
    expect(parseStatus(null)).toBeNull()
    expect(parseStatus('{half')).toBeNull()
    expect(parseStatus('[1, 2]')?.issues).toEqual([])
    expect(parseStatus('{"issues": [{"title": "no number"}, 7]}')?.issues).toEqual([])
  })
})

group('the headline', () => {
  test('the lock decides running, not the file', () => {
    expect(headline(seen(status([ROW], undefined, false), true)).text).toBe('Running')
    expect(headline(seen(status([ROW], undefined, true), false)).text).toContain("didn't finish cleanly")
    expect(headline(seen(status([ROW], undefined, false), false)).text).toBe('Not running')
  })
  test('a stop request while running, and a loop that never ran', () => {
    expect(headline(seen(status([ROW]), true, true)).text).toBe('Stopping after this step')
    expect(headline(seen(null, false)).text).toBe("Hasn't run here yet")
  })
  test('a lock whose process is gone is a killed run, in red', () => {
    const line = headline(seen(status([ROW], undefined, true), false, false, true))
    expect(line.tone).toBe('fail')
    expect(line.text).toContain('killed')
  })
  test('the pid in the lock file', () => {
    expect(lockPid('4242\n')).toBe(4242)
    expect(lockPid('')).toBeNull()
    expect(lockPid('abc')).toBeNull()
  })
})

group('the tmux session', () => {
  test('the status file names it', () => {
    expect(parseStatus(JSON.stringify({ tmux: 'loop-starter', issues: [] }))?.tmux).toBe('loop-starter')
    expect(parseStatus('{"issues": []}')?.tmux).toBeNull()
  })
  test('a running loop in tmux offers the attach command', () => {
    expect(attach(seen(status([ROW], undefined, true, 'loop-starter'), true))).toBe('tmux attach -t loop-starter')
  })
  test('a name with a space is quoted', () => {
    expect(attach(seen(status([ROW], undefined, true, 'my loop'), true))).toBe("tmux attach -t 'my loop'")
  })
  test('no session, or a run that is no longer alive, offers nothing', () => {
    expect(attach(seen(status([ROW]), true))).toBeNull()
    expect(attach(seen(status([ROW], undefined, true, 'loop-starter'), false))).toBeNull()
  })
})

group('watching it', () => {
  const inTmux = (isLocked: boolean, hasWatchFile: boolean, name = 'loop-starter') =>
    seen(status([ROW], undefined, true, name), isLocked, false, false, hasWatchFile)
  test('a running loop with a watch file offers it', () => {
    expect(watch(inTmux(true, true))).toBe('/h/starter/.loop/watch.command')
  })
  test('no watch file (not macOS, or an older loop.py), no session, or not running: no button', () => {
    expect(watch(inTmux(true, false))).toBeNull()
    expect(watch(seen(status([ROW]), true, false, false, true))).toBeNull()
    expect(watch(inTmux(false, true))).toBeNull()
  })
  test('the fallback command is read-only, exact and always quoted', () => {
    expect(watchCommand(inTmux(true, true))).toBe("tmux attach -r -t '=loop-starter'")
    expect(watchCommand(inTmux(true, true, "it's"))).toBe("tmux attach -r -t '=it'\\''s'")
    expect(watchCommand(inTmux(false, true))).toBeNull()
  })
})

group('the header', () => {
  const NOW = Date.parse('2026-10-15T15:00:00Z')
  // As loop.py writes it: UTC, with its offset. 1h 04m before NOW.
  const STARTED = new Date(NOW - 64 * 60_000).toISOString().replace(/\.\d+Z$/, '+00:00')
  const up = (s: Status): Status => ({ ...s, started: STARTED })
  const two = [ROW, { ...ROW, number: 13 }]
  test('the repo on the left, the state on the right, with its tone', () => {
    const h = header(seen(up(status([ROW])), true), NOW, 60)
    expect(h.left).toBe('starter')
    expect(h.right).toEqual({ tone: 'now', text: '● Running · up 1h 04m' })
  })
  test('running says how many jobs past one', () => {
    expect(header(seen(up(status(two)), true), NOW, 60).right.text).toBe('● Running 2 · up 1h 04m')
  })
  test('a live loop with nothing being worked is idle, in dim green', () => {
    expect(header(seen(up(status([{ ...ROW, state: 'pr' }])), true), NOW, 60).right).toEqual({ tone: 'idle', text: '● Idle · up 1h 04m' })
  })
  test('stopping, not running, killed, unclean, and never run', () => {
    expect(header(seen(up(status([ROW])), true, true), NOW, 60).right).toEqual({ tone: 'now', text: '● Stopping after this step' })
    expect(header(seen(status([ROW], undefined, false), false), NOW, 60).right).toEqual({ tone: 'quiet', text: '○ Not running' })
    const killed = header(seen(status([ROW], undefined, true), false, false, true), NOW, 80).right
    expect(killed).toEqual({ tone: 'fail', text: '○ Not running. The last run was killed and left its lock behind' })
    expect(header(seen(status([ROW], undefined, true), false), NOW, 80).right).toEqual({ tone: 'fail', text: "○ Not running. The last run didn't finish cleanly" })
    expect(header(seen(null, false), NOW, 60).right.text).toBe("○ Hasn't run here yet")
  })
  test('an older loop.py, with no start, has no uptime', () => {
    expect(header(seen(status([ROW]), true), NOW, 60).right.text).toBe('● Running')
  })
  test('the dot pulses only while the loop is on a job', () => {
    expect(header(seen(up(status([ROW])), true), NOW, 60).isPulsing).toBe(true)
    expect(header(seen(up(status(two)), true), NOW, 24).isPulsing).toBe(true)
    expect(header(seen(up(status([{ ...ROW, state: 'pr' }])), true), NOW, 60).isPulsing).toBe(false)
    expect(header(seen(up(status([ROW])), true, true), NOW, 60).isPulsing).toBe(false)
    expect(header(seen(status([ROW], undefined, true), false), NOW, 80).isPulsing).toBe(false)
    expect(header(seen(null, false), NOW, 60).isPulsing).toBe(false)
  })
  test('two rows at any width: one when it fits, the state on the second when it does not, uncut', () => {
    const s = seen(up(status(two)), true)
    const wide = header(s, NOW, 60)
    const narrow = header(s, NOW, 24)
    expect(wide.rows.length).toBe(narrow.rows.length)
    expect(wide.wraps).toBe(false)
    expect(wide.rows[0]).toBe(`starter${' '.repeat(60 - 7 - 23)}● Running 2 · up 1h 04m`)
    expect(wide.rows[1]).toBe('')
    expect(narrow.wraps).toBe(true)
    expect(narrow.rows).toEqual(['starter', '● Running 2 · up 1h 04m'])
  })
  test('the start survives the status file', () => {
    expect(parseStatus(JSON.stringify({ started: STARTED, issues: [] }))?.started).toBe(STARTED)
    expect(parseStatus('{"issues": []}')?.started).toBeNull()
  })
})

group("a job's own window", () => {
  const inTmux = (isLocked: boolean, name = 'loop-starter') => seen(status([ROW], undefined, true, name), isLocked)
  test('its watch file, and the read-only command that opens its window', () => {
    expect(jobWatchFile(12)).toBe('.loop/issue-12/watch.command')
    expect(jobAttach(inTmux(true), { ...ROW, window: 'issue-12' })).toBe("tmux attach -r -t '=loop-starter:issue-12'")
    expect(jobAttach(inTmux(true, "it's"), { ...ROW, window: 'issue-12' })).toBe("tmux attach -r -t '=it'\\''s:issue-12'")
  })
  test('no window, no session, or no live run: nothing to watch', () => {
    expect(jobAttach(inTmux(true), ROW)).toBeNull()
    expect(jobAttach(seen(status([ROW]), true), { ...ROW, window: 'issue-12' })).toBeNull()
    expect(jobAttach(inTmux(false), { ...ROW, window: 'issue-12' })).toBeNull()
  })
  test('the window survives the status file', () => {
    expect(parseStatus(JSON.stringify({ issues: [{ ...ROW, window: 'issue-12' }] }))?.issues[0]?.window).toBe('issue-12')
  })
})

group('a waiting issue', () => {
  test('names what it waits on', () => {
    expect(waitingOn({ number: 16, title: 't', waiting_on: [14] })).toBe('waiting on #14')
    expect(waitingOn({ number: 16, title: 't', waiting_on: [14, 15] })).toBe('waiting on #14, #15')
    expect(waitingOn({ number: 16, title: 't' })).toBeNull()
  })
  test('what it waits on survives the status file', () => {
    const text = JSON.stringify({ queue: [{ number: 16, title: 't', waiting_on: [14, 15] }, { number: 17, title: 'u' }], issues: [] })
    expect(parseStatus(text)?.queue).toEqual([{ number: 16, title: 't', waiting_on: [14, 15] }, { number: 17, title: 'u' }])
  })
})

group('an issue', () => {
  test('in progress: the step and the round, and the last round under it', () => {
    const { head, detail } = describe(ROW, true)
    expect(head).toEqual({ tone: 'now', text: 'building, round 2 of 5' })
    expect(detail).toBe('tests failed (1), review FIX')
  })
  test('planning has no round yet', () => {
    expect(describe({ ...ROW, step: 'SHAPE', round: 0, tests: null, review: null }, true)).toEqual({
      head: { tone: 'now', text: 'planning' }, detail: null,
    })
  })
  test('ended: a pull request, a block with its reason', () => {
    expect(describe({ ...ROW, state: 'pr', pr: 'https://x/pull/2', tests: 'passed', review: 'PASS' }, false).head.text).toBe('pull request open')
    const blocked = describe({ ...ROW, state: 'blocked', note: 'still failing after 5 rounds' }, false)
    expect(blocked.head.tone).toBe('fail')
    expect(blocked.detail).toBe('tests failed (1), review FIX. still failing after 5 rounds')
  })
  test('working with no loop running was left part way', () => {
    expect(describe(ROW, false).head).toEqual({ tone: 'fail', text: 'left at building' })
  })
})

group('what to tell the person', () => {
  test('only an issue that just reached an end', () => {
    const before = status([ROW])
    const after = status([{ ...ROW, state: 'pr', pr: 'u' }, { ...ROW, number: 9, state: 'blocked' }])
    expect(changes(before, after)).toEqual(['Loop: #12 has a pull request', 'Loop: #9 is blocked'])
    expect(changes(after, after)).toEqual([])
    expect(changes(null, after)).toEqual([])
    expect(changes(before, status([{ ...ROW, round: 3 }]))).toEqual([])
  })
  test('waiting leaves out the issue being worked on', () => {
    expect(waiting(status([ROW])).map(q => q.number)).toEqual([15])
    expect(waiting(null)).toEqual([])
  })
})

group('fitting and finding', () => {
  test('a long line is cut with an ellipsis', () => {
    expect(clip('abcdef', 4)).toBe('abc…')
    expect(clip('abc', 4)).toBe('abc')
  })
  test('the root is the nearest folder holding the loop script', async () => {
    const files = new Set(['/h/starter/scripts/loop.py'])
    const exists = async (p: string) => files.has(p)
    expect(await findRoot('/h/starter/examples/proposal', exists)).toBe('/h/starter')
    expect(await findRoot('/h/elsewhere', exists)).toBeNull()
  })
  test('two looks with the same content are the same', () => {
    expect(sameSeen(seen(status([ROW]), true), seen(status([ROW]), true))).toBe(true)
    expect(sameSeen(seen(status([ROW]), true), seen(status([ROW]), false))).toBe(false)
  })
})

group('the tabs', () => {
  const NOW = Date.parse('2026-10-14T12:00:00')
  const ended = (number: number, state: string, updated?: string): Row => ({ ...ROW, number, state, updated })
  test('finished keeps an ended job from the last 24 hours, and drops an older or undated one', () => {
    const rows = [
      ended(1, 'pr', '2026-10-14T09:00:00'),
      ended(2, 'blocked', '2026-10-13T12:00:00'),
      ended(3, 'pr', '2026-10-12T12:23:36'),
      ended(4, 'stopped'),
    ]
    expect(lists(status(rows), NOW).finished.map(r => r.number)).toEqual([1, 2])
    expect(NOW - Date.parse('2026-10-13T12:00:00')).toBe(FINISHED_MS)
  })
  test('active is what is being worked; queue leaves it out', () => {
    const l = lists(status([ROW, ended(3, 'pr', '2026-10-14T09:00:00')]), NOW)
    expect(l.active.map(r => r.number)).toEqual([12])
    expect(l.queue.map(q => q.number)).toEqual([15])
  })
  test('opens on active, else queue, else finished', () => {
    expect(firstTab(lists(status([ROW]), NOW))).toBe('active')
    expect(firstTab(lists(status([]), NOW))).toBe('queue')
    expect(firstTab(lists(status([], []), NOW))).toBe('finished')
  })
  test('three at a time, with the start kept inside the list', () => {
    const five = [1, 2, 3, 4, 5]
    expect(page(five, 0, 3)).toEqual({ shown: [1, 2, 3], start: 0, above: 0, below: 2 })
    expect(page(five, 1, 3)).toEqual({ shown: [2, 3, 4], start: 1, above: 1, below: 1 })
    expect(page(five, 9, 3).start).toBe(2)
    expect(page(five, -4, 3).start).toBe(0)
    expect(page([1, 2], 1, 3)).toEqual({ shown: [1, 2], start: 0, above: 0, below: 0 })
    expect(page([], 3, 3)).toEqual({ shown: [], start: 0, above: 0, below: 0 })
  })
  test('the size sets both how many show and where the start stops', () => {
    const thirty = Array.from({ length: 30 }, (_, i) => i + 1)
    const first = page(thirty, 0, 21)
    expect(first.shown.length).toBe(21)
    expect(first.below).toBe(9)
    const last = page(thirty, 99, 21)
    expect(last.start).toBe(9)
    expect(last.shown[20]).toBe(30)
    expect(last.above).toBe(9)
    expect(last.below).toBe(0)
  })
})

// A time as loop.py writes it: local, to the second, with no zone.
function local(ms: number): string {
  const d = new Date(ms)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

group('the dot', () => {
  test('pulses only on a job the running loop is on', () => {
    expect(dot(ROW, true)).toEqual({ tone: 'now', isPulsing: true })
    expect(dot(ROW, false)).toEqual({ tone: 'fail', isPulsing: false })
    expect(dot({ ...ROW, state: 'pr' }, true)).toEqual({ tone: 'pass', isPulsing: false })
    expect(dot({ ...ROW, state: 'blocked' }, true)).toEqual({ tone: 'fail', isPulsing: false })
    expect(dot({ ...ROW, state: 'skipped' }, true)).toEqual({ tone: 'quiet', isPulsing: false })
  })
  test('the pane redraws fast only while a dot pulses', () => {
    expect(isPulsing(seen(status([ROW]), true))).toBe(true)
    expect(isPulsing(seen(status([ROW]), false))).toBe(false)
    expect(isPulsing(seen(status([{ ...ROW, state: 'pr' }]), true))).toBe(false)
    expect(isPulsing(null)).toBe(false)
  })
})

group('the clock', () => {
  const START = new Date(2026, 9, 15, 14, 22, 5).getTime()
  test('reads like a person says it', () => {
    expect(duration(42_000)).toBe('42s')
    expect(duration(6 * 60_000 + 5_000)).toBe('6m 05s')
    expect(duration(64 * 60_000)).toBe('1h 04m')
    expect(duration(-5)).toBe('0s')
  })
  test('a job being worked shows when it started and how long it has been running', () => {
    const row = { ...ROW, started: local(START) }
    expect(clock(row, true, START + 372_000)).toBe('started 14:22 · running 6m 12s')
  })
  test('an ended job shows how long it took, and one left by a dead run how long it ran', () => {
    const done = { ...ROW, state: 'pr', started: local(START), updated: local(START + 18 * 60_000) }
    expect(clock(done, true, START + 3_600_000)).toBe('started 14:22 · took 18m 00s')
    const left = { ...ROW, started: local(START), updated: local(START + 90_000) }
    expect(clock(left, false, START + 3_600_000)).toBe('started 14:22 · ran 1m 30s')
  })
  test('a start on another day carries its date', () => {
    const row = { ...ROW, started: local(START) }
    expect(clock(row, true, START + 24 * 3_600_000)).toBe('started Oct 15 14:22 · running 24h 00m')
  })
  test('a row from an older loop.py, with no start, has no clock', () => {
    expect(clock(ROW, true, START)).toBeNull()
    expect(clock({ ...ROW, started: 'soon' }, true, START)).toBeNull()
  })
  test('tokens follow the time, and the cost follows the tokens', () => {
    const run = { ...ROW, started: local(START) }
    const at = START + 372_000
    expect(clock({ ...run, tokens: 840_000 }, true, at)).toBe('started 14:22 · running 6m 12s · 840k tokens')
    expect(clock({ ...run, tokens: 1_200_000, cost_usd: 3.4 }, true, at)).toBe('started 14:22 · running 6m 12s · 1.2M tokens · ~$3.40')
    expect(clock({ ...run, tokens: 950 }, true, at)).toBe('started 14:22 · running 6m 12s · 950 tokens')
    const done = { ...ROW, state: 'pr', started: local(START), updated: local(START + 18 * 60_000), tokens: 840_000, cost_usd: 3.4 }
    expect(clock(done, true, at)).toBe('started 14:22 · took 18m 00s · 840k tokens · ~$3.40')
    expect(clock({ ...run, state: 'blocked', tokens: 840_000 }, false, at)).toBe('started 14:22 · 840k tokens')
  })
  test('a token count rounds to the unit it is read in', () => {
    expect(usage({ ...ROW, tokens: 999 })).toBe('999 tokens')
    expect(usage({ ...ROW, tokens: 1_000 })).toBe('1k tokens')
    expect(usage({ ...ROW, tokens: 999_499 })).toBe('999k tokens')
    expect(usage({ ...ROW, tokens: 999_500 })).toBe('1.0M tokens')
    expect(usage({ ...ROW, tokens: 1_000_000 })).toBe('1.0M tokens')
    expect(usage({ ...ROW, tokens: 12_345_678 })).toBe('12.3M tokens')
  })
  test('null, missing or zero usage leaves the line as it was', () => {
    const run = { ...ROW, started: local(START) }
    const plain = 'started 14:22 · running 6m 12s'
    expect(clock({ ...run, tokens: undefined }, true, START + 372_000)).toBe(plain)
    expect(clock({ ...run, tokens: 0, cost_usd: 0 }, true, START + 372_000)).toBe(plain)
    expect(clock({ ...run, cost_usd: 3.4 }, true, START + 372_000)).toBe(plain)
    expect(usage(ROW)).toBeNull()
  })
  test('usage survives the status file only as a number above zero', () => {
    const read = (extra: object) => parseStatus(JSON.stringify({ issues: [{ ...ROW, started: '2026-10-15T14:22:05', ...extra }] }))?.issues[0]
    expect(read({ tokens: 840000, cost_usd: 3.4 })).toMatchObject({ tokens: 840000, cost_usd: 3.4 })
    for (const bad of ['12', 'NaN', null, 0, -5, {}, [], true]) {
      const row = read({ tokens: bad, cost_usd: bad })
      expect(row?.tokens).toBeUndefined()
      expect(row?.cost_usd).toBeUndefined()
      const line = clock(row!, true, START + 372_000) ?? ''
      expect(line).not.toContain('NaN')
      expect(line).not.toContain('undefined')
      expect(line).toBe('started 14:22 · running 6m 12s')
    }
  })
  test('in a narrow pane the usage is what gets cut', () => {
    const line = clock({ ...ROW, started: local(START), tokens: 840_000, cost_usd: 3.4 }, true, START + 372_000)!
    const clipped = clip(line, 40)
    expect(clipped.startsWith('started 14:22 · running 6m 12s')).toBe(true)
    expect(clipped.endsWith('…')).toBe(true)
    expect(clipped).not.toContain('~$')
  })
  test('the model follows the usage, without its claude- prefix', () => {
    const run = { ...ROW, started: local(START), tokens: 840_000, cost_usd: 3.4 }
    expect(clock({ ...run, model: 'claude-opus-5-5' }, true, START + 372_000)).toBe('started 14:22 · running 6m 12s · 840k tokens · ~$3.40 · opus-5-5')
    expect(clock({ ...run, model: 'llama3.1:8b' }, true, START + 372_000)).toBe('started 14:22 · running 6m 12s · 840k tokens · ~$3.40 · llama3.1:8b')
  })
  test('a model with no tokens still shows after the time', () => {
    const run = { ...ROW, started: local(START), model: 'claude-opus-5-5' }
    expect(clock(run, true, START + 372_000)).toBe('started 14:22 · running 6m 12s · opus-5-5')
  })
  test('no model leaves the line as it was', () => {
    const run = { ...ROW, started: local(START), tokens: 840_000, cost_usd: 3.4 }
    expect(clock({ ...run, model: undefined }, true, START + 372_000)).toBe('started 14:22 · running 6m 12s · 840k tokens · ~$3.40')
    expect(modelName(ROW)).toBeNull()
  })
  test('only a leading claude- is dropped', () => {
    expect(modelName({ ...ROW, model: 'claude' })).toBe('claude')
    expect(modelName({ ...ROW, model: 'my-claude-opus' })).toBe('my-claude-opus')
    expect(modelName({ ...ROW, model: 'claude-sonnet-5-5' })).toBe('sonnet-5-5')
  })
  test('the model survives the status file only as a non-empty string', () => {
    const read = (extra: object) => parseStatus(JSON.stringify({ issues: [{ ...ROW, ...extra }] }))?.issues[0]
    expect(read({ model: 'claude-opus-5-5' })?.model).toBe('claude-opus-5-5')
    expect(read({})?.model).toBeUndefined()
    for (const bad of [null, '', 5, {}, [], true]) expect(read({ model: bad })?.model).toBeUndefined()
  })
  test('the start survives the status file', () => {
    const text = JSON.stringify({ issues: [{ ...ROW, started: '2026-10-15T14:22:05' }] })
    expect(parseStatus(text)?.issues[0]?.started).toBe('2026-10-15T14:22:05')
  })
})

// The same cases as github-status's, so the two mods hold the focus to the same rules.
group('the project in focus', () => {
  test('a folder under projects/, with or without the prefix', () => {
    expect(projectName('acme')).toEqual({ name: 'acme' })
    expect(projectName(' projects/acme-app/ ')).toEqual({ name: 'acme-app' })
    expect(projectName('web_2.0')).toEqual({ name: 'web_2.0' })
  })
  test('anything that could reach outside projects/ is refused', () => {
    for (const arg of ['../secrets', 'acme/sub', '/etc', '.hidden', 'projects/../x', 'a..b', '~/x', 'two words']) {
      expect('why' in projectName(arg)).toBe(true)
    }
  })
  test('an id matching the pattern names a file under .sanvio/project', () => {
    expect(focusFile('/h', 'aaaaaaaa-1111')).toBe('/h/.sanvio/project/aaaaaaaa-1111')
  })
  test('anything else names none', () => {
    for (const id of [null, '', 'abc', '../../etc/passwd', 'aaaaaaaa/1111', 'g'.repeat(8), 'a'.repeat(65)]) {
      expect(focusFile('/h', id)).toBeNull()
    }
  })
  test("the file's text, trimmed, is what projectName accepts", () => {
    expect(focusName('acme\n')).toBe('acme')
    for (const text of ['', '../x', 'a/b', '.hidden']) expect(focusName(text)).toBeNull()
  })
})
