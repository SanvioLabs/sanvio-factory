import { describe as group, expect, test } from 'claude-code/testing'

import { missing, sections } from './logic'
import { SAMPLE } from './sample'

// SAMPLE is what scripts/dashboard_data.py printed, written by tests/test_dashboard_data.py, so a field
// the script renames or moves shows here as a section the pane can't read.
const KEYS = ['loop_spend', 'loop_throughput', 'activity', 'evals', 'conversations', 'waiting', 'loop_rework']
// What the pane says when a field isn't where it looks.
const UNREAD = ["couldn't read", 'not in this script', "doesn't give them yet"]
// Every why the script gives a missing section, and the one missing() gives when it has none.
const WHYS = ['no loop records', 'unreadable', 'no status.json', 'no usage log', 'no saved evals', 'no transcripts',
  'gh unavailable', 'gh failed', 'unavailable']
// Every why the script gives when it can't tell whether a reviewer's saved result is stale.
const STALE_WHYS = ['folder missing', 'no saved time', 'no git']

const texts = () => sections(SAMPLE).flatMap(s => s.lines.map(l => l.text))

group("the script's own document", () => {
  test('has every section, and both halves of waiting, none of them missing', () => {
    const w = SAMPLE.waiting as Record<string, unknown>
    for (const v of [...KEYS.map(k => SAMPLE[k]), w.pull_requests, w.blocked]) {
      expect(v).not.toBeUndefined()
      expect(missing(v)).toBeNull()
    }
  })
  test('draws one section for each, in order', () => {
    expect(sections(SAMPLE).map(s => s.key)).toEqual(['waiting', 'spend', 'throughput', 'evals', 'conversations', 'activity'])
  })
  test("no line says a field couldn't be read", () => {
    for (const text of texts()) for (const phrase of UNREAD) expect(text).not.toContain(phrase)
  })
  test('no line is only the reason a section is missing', () => {
    for (const text of texts()) expect(WHYS.some(why => text === why || text.endsWith(`: ${why}`))).toBe(false)
  })
  test("no reviewer's staleness is only a why", () => {
    for (const text of texts()) for (const why of STALE_WHYS) expect(text).not.toContain(why)
  })
})
