import { describe as group, expect, test } from 'claude-code/testing'

import { activity, argv, conversations, day, duration, evals, findRoot, missing, money, newer, outcome, parseDoc, sections, sinceFor, spend, stageTimes, state, throughput, tokens, waiting } from './logic'
import type { Doc, Seen } from '../types'

// The shape scripts/dashboard_data.py --json prints, with every section filled. The numbers and
// titles are made up.
const DOC: Doc = {
  generated: '2026-10-27T11:00:00-07:00',
  since: '2026-10-13',
  loop_spend: {
    today: { tokens: 12_000_000, cost_usd: 16 },
    last_7_days: { tokens: 60_000_000, cost_usd: 70 },
    since: { tokens: 60_000_000, cost_usd: 70 },
    by_issue: { 'issue-11': { tokens: 3_000_000, cost_usd: 3.5 }, 'issue-12': { tokens: 3_600_000, cost_usd: 5 },
      'issue-13': { tokens: 1_000_000, cost_usd: 2 }, 'app/issue-3': { tokens: 5, cost_usd: 0.25 } },
    by_step: { build: { tokens: 1, cost_usd: 1 } },
    by_model: { 'claude-opus-5-5': { tokens: 3, cost_usd: 5, label: 'claude-opus-5-5' },
      null: { tokens: 2, cost_usd: 20, label: 'model not recorded' } },
    cost_per_pr: 2.5,
  },
  loop_throughput: { issues: 20, by_state: { pr: 19, blocked: 1 }, rounds: {}, more_than_one_round: 4 },
  activity: { skills: { 'review-pr': 5, learn: 1 }, agents: { reviewer: 5 }, commands: {},
    guard_refusals: { 'credential-file': 3 }, asks: 2 },
  evals: {
    reviewer: { saved: '2026-10-26T09:00:00+00:00', stable: 9, flaky: 0, failing: 1, failing_cases: ['03-c'],
      stale: true, changed: ['agents/reviewer.md', 'scripts/eval_agents.py'], newest_change: '2026-10-27T08:30:00-07:00' },
    'security-reviewer': { saved: '2026-10-27T10:00:00-07:00', stable: 10, flaky: 0, failing: 0, failing_cases: [],
      stale: false, changed: [], newest_change: null },
  },
  conversations: {
    factory: { by_model: { 'claude-opus-5-5': { total: 3_000_000 }, '<synthetic>': { total: 0 }, 'claude-haiku-5-5': { total: 450_000 } }, sessions: 30 },
    loop: { by_model: { 'claude-opus-5-5': { total: 20_000_000 } }, sessions: 40 },
  },
  waiting: {
    pull_requests: [
      { number: 41, title: 'Add a gate', opened: 'x', hours_waited: 2, loop_issue: 31, draft: false, checks: 'pass', conflicts: null },
      { number: 42, title: 'Fix the docs', opened: 'x', hours_waited: 3.5, loop_issue: 32, draft: false, checks: 'fail', conflicts: true },
    ],
    blocked: [{ issue: 'issue-38', number: 38, title: 'Link the loop section', note: 'still failing after 5 rounds', updated: 'x' }],
  },
  loop_rework: { merged: 10, reworked: 2, pull_requests: [
    { number: 21, title: 'a', merges_from_base: 0, other_commits: 1 },
    { number: 22, title: 'b', merges_from_base: 1, other_commits: 0 },
  ] },
}

const GONE = (why: string) => ({ value: null, why })
const text = (lines: { text: string }[]) => lines.map(l => l.text).join('\n')

group('the document', () => {
  test("reads what the script prints, and nothing that isn't it", () => {
    expect(parseDoc(JSON.stringify(DOC))?.since).toBe('2026-10-13')
    expect(parseDoc('Traceback (most recent call last):')).toBeNull()
    expect(parseDoc('[1, 2]')).toBeNull()
    expect(parseDoc('{"since": "2026-10-13"}')).toBeNull()
  })
  test('a section the script says is missing gives its why', () => {
    expect(missing(GONE('gh unavailable'))).toBe('gh unavailable')
    expect(missing({ value: null })).toBe('unavailable')
    expect(missing({ today: {} })).toBeNull()
    expect(missing([])).toBeNull()
  })
  test("a run that failed, was cut off or printed something else is a failure, not a document", () => {
    const run = (exitCode: number, stdout: string, isStdoutTruncated = false) => ({ exitCode, stdout, isStdoutTruncated })
    expect('doc' in outcome(run(0, JSON.stringify(DOC)))).toBe(true)
    expect(outcome(null)).toEqual({ failure: "the script didn't finish" })
    expect(outcome(run(1, ''))).toEqual({ failure: 'the script exited 1' })
    expect(outcome(run(0, JSON.stringify(DOC), true))).toEqual({ failure: 'the output was cut off' })
    expect(outcome(run(0, 'hello'))).toEqual({ failure: "the output wasn't the dashboard's JSON" })
  })
  test('the sections come in order, what needs the person first', () => {
    expect(sections(DOC).map(s => s.key)).toEqual(['waiting', 'spend', 'throughput', 'evals', 'conversations', 'activity'])
  })
  test('a document from an older script, with none of the sections, still draws', () => {
    for (const s of sections({ generated: 'x' })) expect(s.lines.length).toBeGreaterThan(0)
  })
})

group('newer', () => {
  test('a document from a newer script says so in yellow', () => {
    const found = newer({ ...DOC, schema: 3 })
    expect(found?.tone).toBe('now')
    expect(found?.text).toContain('dashboard_data.py is newer')
  })
  test('a document from an older script says so in yellow', () => {
    const found = newer({ ...DOC, schema: 1 })
    expect(found?.tone).toBe('now')
    expect(found?.text).toContain('older than this pane')
  })
  test('one with no schema, or the one this pane reads, says nothing', () => {
    expect(newer(DOC)).toBeNull()
    expect(newer({ ...DOC, schema: 2 })).toBeNull()
  })
  test('a newer or older document still draws every section', () => {
    expect(sections({ ...DOC, schema: 1 })).toEqual(sections(DOC))
    expect(sections({ ...DOC, schema: 3 })).toEqual(sections(DOC))
  })
})

group('numbers', () => {
  test('tokens, dollars and days read the way a person reads them', () => {
    expect(tokens(312)).toBe('312')
    expect(tokens(840_400)).toBe('840k')
    expect(tokens(12_000_000)).toBe('12.0M')
    expect(tokens(null)).toBe('?')
    expect(money(16)).toBe('$16.00')
    expect(money(null)).toBe('?')
    expect(day('2026-10-13')).toBe('Oct 13')
    expect(day('2026-10-27T08:30:00-07:00')).toBe('Oct 27')
    expect(day(null)).toBe('?')
  })
})

group('the header', () => {
  const seen = (over: Partial<Seen>): Seen => ({ root: '/h/starter', doc: DOC, readAt: Date.parse('2026-10-27T11:43:00'), isReading: false, failedAt: null, failure: null, ...over })
  test('says the first read can take a while', () => {
    expect(state(null).text).toContain('can take a minute')
    expect(state(seen({ doc: null, isReading: true })).text).toContain('can take a minute')
  })
  test('says when it last read, and when a refresh failed it says so and what it still shows', () => {
    expect(state(seen({})).text).toBe('Updated 11:43')
    const failed = state(seen({ failedAt: Date.parse('2026-10-27T11:45:00'), failure: 'the script exited 1' }))
    expect(failed).toEqual({ tone: 'fail', text: 'Refresh failed 11:45 · showing 11:43' })
  })
})

group('waiting on you', () => {
  test('a table of pull requests, red when checks fail or it conflicts, then the blocked issues and why', () => {
    const section = waiting(DOC)
    const [prs, blocked] = section.tables ?? []
    expect(prs?.head).toEqual(['Pull request', 'Waiting', 'Checks', 'Conflicts'])
    expect(prs?.rows).toEqual([['#41 Add a gate', '2h', 'pass', 'unknown'], ['#42 Fix the docs', '3.5h', 'fail', 'yes']])
    expect(prs?.tones).toEqual(['plain', 'fail'])
    expect(blocked?.head).toEqual(['Blocked issue', 'Since'])
    expect(blocked?.rows[0]?.[0]).toBe('#38 Link the loop section')
    expect(text(section.lines)).toBe('#38: still failing after 5 rounds')
  })
  test("pull requests gh couldn't read say so in red, and never read as nothing waiting", () => {
    const section = waiting({ ...DOC, waiting: { pull_requests: GONE('gh unavailable'), blocked: [] } })
    expect(section.lines).toEqual([{ tone: 'fail', text: 'Pull requests: gh unavailable' }])
    expect(section.tables).toEqual([])
  })
  test("a list in a shape it doesn't know, or none at all, is unreadable, not empty", () => {
    for (const pull_requests of [undefined, { items: [] }, 'none']) {
      const section = waiting({ ...DOC, waiting: { pull_requests, blocked: [] } })
      expect(section.lines).toEqual([{ tone: 'fail', text: "Pull requests: couldn't read them" }])
    }
    expect(text(waiting({ ...DOC, waiting: { pull_requests: [] } }).lines)).toBe("Blocked issues: couldn't read them")
  })
  test('nothing open and nothing blocked says nothing is waiting', () => {
    expect(text(waiting({ ...DOC, waiting: { pull_requests: [], blocked: [] } }).lines)).toBe('Nothing waiting on you')
  })
})

group('loop spend', () => {
  test('a table of today, the week, since the date and per pull request, each with its cost and tokens', () => {
    const periods = spend(DOC).tables?.[0]
    expect(periods?.head).toEqual(['', 'Cost', 'Tokens'])
    expect(periods?.rows).toEqual([
      ['Today', '$16.00', '12.0M'], ['7 days', '$70.00', '60.0M'], ['Since Oct 13', '$70.00', '60.0M'],
      ['Per pull request', '~$2.50', '']])
  })
  test('a table of the costliest issues, a project issue keeping its project, then one of each model', () => {
    const [, issues, models] = spend(DOC).tables ?? []
    expect(issues?.head).toEqual(['Costliest issues', 'Cost', 'Tokens'])
    expect(issues?.rows).toEqual([['#12', '$5.00', '3.6M'], ['#11', '$3.50', '3.0M'], ['#13', '$2.00', '1.0M'],
      ['app/#3', '$0.25', '5']])
    expect(models?.rows).toEqual([['model not recorded', '$20.00', '2'], ['opus-5-5', '$5.00', '3']])
    expect(text(spend(DOC).lines)).toContain('not a bill')
  })
  test('every table row is as long as its header', () => {
    for (const t of spend(DOC).tables ?? []) for (const r of t.rows) expect(r.length).toBe(t.head.length)
  })
  test('no pull request yet says so rather than showing nothing', () => {
    const doc = { ...DOC, loop_spend: { ...(DOC.loop_spend as object), cost_per_pr: null } }
    expect(spend(doc).tables?.[0]?.rows[3]).toEqual(['Per pull request', 'none yet', ''])
  })
  test("the chart starts on the day the loop's records do", () => {
    const by_day = [{ day: '2026-10-21', tokens: 0, cost_usd: 0 }, { day: '2026-10-22', tokens: 5, cost_usd: 2.5 }]
    const section = spend({ ...DOC, loop_spend: { ...(DOC.loop_spend as object), by_day, first_run: '2026-10-22' } })
    expect(section.chart?.points).toEqual([{ date: '2026-10-22', value: 2.5 }])
  })
  test("says when the loop's records start, only when that's after the date counted from", () => {
    const at = (first_run: string | null) => text(spend({ ...DOC, loop_spend: { ...(DOC.loop_spend as object), first_run } }).lines)
    expect(at('2026-10-22')).toContain("The loop's records start Oct 22")
    expect(at('2026-10-13')).not.toContain('records start')
    expect(at(null)).not.toContain('records start')
  })
  test('a missing section shows its why', () => {
    expect(text(spend({ ...DOC, loop_spend: GONE('no loop records') }).lines)).toBe('no loop records')
  })
  test('with daily figures it carries a chart of the dollars and names the busiest day', () => {
    const by_day = [{ day: '2026-10-26', tokens: 9, cost_usd: 1.5 }, { day: '2026-10-27', tokens: 3, cost_usd: 16 }]
    const section = spend({ ...DOC, loop_spend: { ...(DOC.loop_spend as object), by_day } })
    expect(section.chart?.points).toEqual([{ date: '2026-10-26', value: 1.5 }, { date: '2026-10-27', value: 16 }])
    expect(section.chart?.unit).toBe('money')
    expect(section.chart?.caption).toBe('Daily, Oct 26 to Oct 27: most $16.00 on Oct 27')
    expect(text(section.lines)).not.toContain('Daily')
  })
  test("each bar is labelled with its day, its cost and its tokens", () => {
    const by_day = [{ day: '2026-10-26', tokens: 9_000_000, cost_usd: 1.5 }, { day: '2026-10-27', tokens: 300, cost_usd: 16 }]
    const chart = spend({ ...DOC, loop_spend: { ...(DOC.loop_spend as object), by_day } }).chart
    expect(chart?.columns).toEqual(['Day', 'Cost', 'Tokens'])
    expect(chart?.labels).toEqual([['Oct 26', '$1.50', '9.0M'], ['Oct 27', '$16.00', '300']])
  })
  test("a day whose runs recorded no cost is labelled ?, never $0.00, and isn't the busiest", () => {
    const by_day = [{ day: '2026-10-26', tokens: 9_000_000, cost_usd: null }, { day: '2026-10-27', tokens: 300, cost_usd: 1 }]
    const chart = spend({ ...DOC, loop_spend: { ...(DOC.loop_spend as object), by_day } }).chart
    expect(chart?.labels[0]).toEqual(['Oct 26', '?', '9.0M'])
    expect(chart?.caption).toBe('Daily, Oct 26 to Oct 27: most $1.00 on Oct 27')
  })
  test("without them it says the script doesn't give them yet, and draws no chart", () => {
    const section = spend(DOC)
    expect(section.chart).toBeUndefined()
    expect(text(section.lines)).toContain("No daily figures: this dashboard_data.py doesn't give them yet")
  })
})

group('throughput and rework', () => {
  test('a table of how recent issues ended and the repeats, then one of rework split into fixes and merges', () => {
    const [issues, rework] = throughput(DOC).tables ?? []
    expect(issues?.head).toEqual(['20 recent issues', 'Count'])
    expect(issues?.rows).toEqual([['Opened a pull request', '19'], ['Blocked', '1'], ['Took more than one round', '4']])
    expect(rework?.rows).toEqual([['Merged', '10'], ['Needed a commit first', '2 (20%)'], ['  with a fix', '1'], ['  only a merge from main', '1']])
  })
  test("rework gh couldn't read says so, beside the issues it could", () => {
    const section = throughput({ ...DOC, loop_rework: GONE('gh failed') })
    expect(section.tables?.map(t => t.key)).toEqual(['throughput-issues'])
    expect(text(section.lines)).toBe('Rework: gh failed')
  })
  test("a merged count it can't read says so, not that nothing merged", () => {
    expect(text(throughput({ ...DOC, loop_rework: { pull_requests: [] } }).lines)).toBe("Rework: couldn't read it")
  })
})

group('stage times', () => {
  const STEPS = { SHAPE: { median_minutes: 4.2, issues: 5 }, BUILD: { median_minutes: 12, issues: 5 },
    VALIDATE: { median_minutes: 31, issues: 5 }, SCALE: { median_minutes: null, issues: 0 } }
  const PRS = { merged: 4, median_hours_to_merge: 20, reviewed: 3, median_hours_to_first_review: 5.2 }
  const timed = (over: object = {}): Doc => ({ ...DOC, stage_times: { loop_steps: STEPS, pull_requests: PRS, slowest: 'merge', ...over } })

  test('a table of each stage with its median and how many it rests on, the slowest marked in yellow', () => {
    const t = stageTimes(timed()).tables[0]
    expect(t?.head).toEqual(['Stage times', 'Median', 'Count'])
    expect(t?.rows).toEqual([['Shape', '4m', '5'], ['Build', '12m', '5'], ['Validate', '31m', '5'], ['Scale', '-', '0'],
      ['First review', '5.2h', '3'], ['Merge (slowest)', '20h', '4']])
    expect(t?.tones).toEqual(['plain', 'plain', 'plain', 'plain', 'plain', 'now'])
    for (const r of t?.rows ?? []) expect(r.length).toBe(3)
  })
  test('a step can be the slowest too', () => {
    const t = stageTimes(timed({ slowest: 'VALIDATE' })).tables[0]
    expect(t?.rows[2]).toEqual(['Validate (slowest)', '31m', '5'])
    expect(t?.tones?.filter(tone => tone === 'now')).toHaveLength(1)
  })
  test('under an hour reads in minutes, from an hour in hours, to a tenth under 10', () => {
    expect(duration(4.2, 5)).toBe('4m')
    expect(duration(59.4, 5)).toBe('59m')
    expect(duration(59.6, 5)).toBe('1.0h')
    expect(duration(90, 5)).toBe('1.5h')
    expect(duration(600, 5)).toBe('10h')
    expect(duration(1200, 5)).toBe('20h')
  })
  test('a stage with none behind it is -, never 0m', () => {
    expect(duration(null, 0)).toBe('-')
    expect(duration(12, 0)).toBe('-')
    expect(duration(null, null)).toBe('-')
  })
  test('with no slowest stage none is marked', () => {
    const t = stageTimes(timed({ slowest: null })).tables[0]
    expect(t?.rows.some(r => r[0]?.includes('slowest'))).toBe(false)
    expect(t?.tones?.every(tone => tone === 'plain')).toBe(true)
  })
  test('a half the script couldn\'t read says why in place of its stages, and the other half still shows', () => {
    const noPrs = stageTimes(timed({ pull_requests: GONE('gh failed'), slowest: 'VALIDATE' }))
    expect(noPrs.tables[0]?.rows.map(r => r[0])).toEqual(['Shape', 'Build', 'Validate (slowest)', 'Scale'])
    expect(text(noPrs.lines)).toBe('Pull request times: gh failed')
    const noSteps = stageTimes(timed({ loop_steps: GONE('no status.json') }))
    expect(noSteps.tables[0]?.rows.map(r => r[0])).toEqual(['First review', 'Merge (slowest)'])
    expect(text(noSteps.lines)).toBe('Loop step times: no status.json')
    const neither = stageTimes(timed({ loop_steps: GONE('unreadable'), pull_requests: GONE('gh failed'), slowest: null }))
    expect(neither.tables).toEqual([])
    expect(text(neither.lines)).toBe('Loop step times: unreadable\nPull request times: gh failed')
  })
  test('comes after rework in throughput, its whys after the others', () => {
    const section = throughput(timed({ pull_requests: GONE('gh failed') }))
    expect(section.tables?.map(t => t.key)).toEqual(['throughput-issues', 'throughput-rework', 'throughput-stages'])
    expect(text(throughput({ ...timed({ pull_requests: GONE('gh failed') }), loop_rework: GONE('gh failed') }).lines))
      .toBe('Rework: gh failed\nPull request times: gh failed')
  })
  test('a script that gives no stage times draws throughput as it did', () => {
    expect(stageTimes(DOC)).toEqual({ tables: [], lines: [] })
    expect(throughput(DOC).tables?.map(t => t.key)).toEqual(['throughput-issues', 'throughput-rework'])
  })
})

group('evals', () => {
  test('a table row per reviewer, red with a failing case and plain when current, then what fails and why it is stale', () => {
    const section = evals(DOC)
    const t = section.tables?.[0]
    expect(t?.head).toEqual(['Reviewer', 'Stable', 'Flaky', 'Failing', 'Saved', 'Stale'])
    expect(t?.rows).toEqual([['reviewer', '9', '0', '1', 'Oct 26', 'yes'], ['security-reviewer', '10', '0', '0', 'Oct 27', 'no']])
    expect(t?.tones).toEqual(['fail', 'plain'])
    expect(text(section.lines)).toContain('reviewer failing: 03-c')
    expect(text(section.lines)).toContain('reviewer stale: 2 files changed, newest Oct 27. Run it again')
  })
  test("one git couldn't check is unknown, not current", () => {
    const doc = { ...DOC, evals: { reviewer: { saved: 'x', stable: 1, flaky: 0, failing: 0, stale: null, why: 'no git' } } }
    expect(evals(doc).tables?.[0]?.rows[0]?.[5]).toBe('unknown')
    expect(text(evals(doc).lines)).toContain('reviewer stale unknown: no git')
  })
  test("a failing count it can't read is ?, in yellow, not a pass", () => {
    const t = evals({ ...DOC, evals: { reviewer: { saved: 'x', stable: 1, flaky: 0, stale: false } } }).tables?.[0]
    expect(t?.rows[0]?.[3]).toBe('?')
    expect(t?.tones).toEqual(['now'])
  })
  test('none saved says how to save one', () => {
    expect(text(evals({ ...DOC, evals: GONE('no saved evals') }).lines)).toContain('eval_agents.py --save')
  })
})

group('conversations', () => {
  test('a table of each side with its tokens and sessions, then one of the biggest models, none that used nothing', () => {
    const [sides, models] = conversations(DOC).tables ?? []
    expect(sides?.rows).toEqual([['Factory', '3.5M', '30'], ['Loop worktrees', '20.0M', '40']])
    expect(models?.head).toEqual(['Model', 'Factory', 'Loop'])
    expect(models?.rows).toEqual([['opus-5-5', '3.0M', '20.0M'], ['haiku-5-5', '450k', '0']])
  })
  test("with daily figures its chart adds the factory's and the loop's tokens day by day", () => {
    const c = DOC.conversations as { factory: object; loop: object }
    const doc = { ...DOC, conversations: {
      factory: { ...c.factory, by_day: [{ day: '2026-10-26', tokens: 10 }, { day: '2026-10-27', tokens: 20 }] },
      loop: { ...c.loop, by_day: [{ day: '2026-10-27', tokens: 5 }] } } }
    expect(conversations(doc).chart?.points).toEqual([{ date: '2026-10-26', value: 10 }, { date: '2026-10-27', value: 25 }])
    expect(conversations(DOC).chart).toBeUndefined()
  })
})

group('activity', () => {
  test('a table each of skills, agents and what the guard refused, none for an empty one, then the asks', () => {
    const section = activity(DOC)
    expect(section.tables?.map(t => t.head[0])).toEqual(['Skill', 'Agent', 'Guard refused'])
    expect(section.tables?.[0]?.rows).toEqual([['review-pr', '5'], ['learn', '1']])
    expect(section.tables?.[2]?.rows).toEqual([['credential-file', '3']])
    expect(text(section.lines)).toBe('Guard asked 2 times, since Oct 13')
  })

  const SKILLS = { 'review-pr': { tokens: 410_000, cost_usd: 0.62 }, learn: { tokens: 0, cost_usd: 0 } }
  const spending = (over: object = {}): Doc => ({ ...DOC, activity: { ...(DOC.activity as object), skill_spend: SKILLS,
    agent_spend: { reviewer: { tokens: 305_000, cost_usd: 0.45 } }, command_spend: {}, unpriced: {},
    prices_checked: '2026-10-01', spend_at: '2026-10-27T12:00:00+00:00', ...over } })

  test('skills and agents add their tokens and estimated cost, and what the guard refused stays two columns', () => {
    const [skills, agents, guard] = activity(spending()).tables ?? []
    expect(skills?.head).toEqual(['Skill', 'Times', 'Tokens', 'Est. cost'])
    expect(skills?.rows).toEqual([['review-pr', '5', '410k', '$0.62'], ['learn', '1', '0', '$0.00']])
    expect(agents?.head).toEqual(['Agent', 'Times', 'Tokens', 'Est. cost'])
    expect(agents?.rows).toEqual([['reviewer', '5', '305k', '$0.45']])
    expect(guard?.head).toEqual(['Guard refused', 'Times'])
    expect(guard?.rows).toEqual([['credential-file', '3']])
  })
  test('a command adds them too, and the top five stay in order of use', () => {
    const commands = { a: 1, b: 2, c: 3, d: 4, e: 5, f: 6 }
    const t = activity(spending({ commands, command_spend: { f: { tokens: 1, cost_usd: 0 }, a: { tokens: 9_000_000, cost_usd: 99 } } })).tables?.[2]
    expect(t?.head).toEqual(['Command', 'Times', 'Tokens', 'Est. cost'])
    expect(t?.rows).toEqual([['f', '6', '1', '$0.00'], ['e', '5', '?', '?'], ['d', '4', '?', '?'], ['c', '3', '?', '?'], ['b', '2', '?', '?']])
  })
  test("a name the spend doesn't list shows ?, never 0 or $0.00", () => {
    const t = activity(spending({ skill_spend: { 'review-pr': SKILLS['review-pr'] } })).tables?.[0]
    expect(t?.rows).toEqual([['review-pr', '5', '410k', '$0.62'], ['learn', '1', '?', '?']])
  })
  test("a cost with no price shows ?, beside the tokens it read", () => {
    const t = activity(spending({ skill_spend: { 'review-pr': { tokens: 410_000, cost_usd: null } } })).tables?.[0]
    expect(t?.rows[0]).toEqual(['review-pr', '5', '410k', '?'])
  })
  test('each list reads its own field: one the script left out stays two columns', () => {
    for (const agent_spend of [undefined, null, []]) {
      const [skills, agents] = activity(spending({ agent_spend })).tables ?? []
      expect(skills?.head.length).toBe(4)
      expect(agents?.head).toEqual(['Agent', 'Times'])
    }
  })
  test('says what the estimate rests on, ahead of the asks, with the time as the document wrote it', () => {
    expect(activity(spending()).lines).toEqual([
      { tone: 'quiet', text: 'Est. cost: an estimate from .sanvio/prices.json, checked Oct 1,' },
      { tone: 'quiet', text: "worked out Oct 27 12:00. Skills' and commands' tokens are" },
      { tone: 'quiet', text: 'attributed from where each started to the next prompt.' },
      { tone: 'quiet', text: 'Guard asked 2 times, since Oct 13' },
    ])
    expect(text(activity(spending({ spend_at: '2026-10-27T23:30:00-07:00' })).lines)).toContain('worked out Oct 27 23:30.')
  })
  test("a price file with no date, or no time for the split, says ?", () => {
    const lines = text(activity(spending({ prices_checked: null, spend_at: null })).lines)
    expect(lines).toContain('checked ?,')
    expect(lines).toContain('worked out ?.')
  })
  test('each line fits the 66 columns of the pane, even with the longest dates', () => {
    const doc = spending({ prices_checked: '2026-09-30', spend_at: '2026-09-30T23:59:00-07:00', unpriced: { a: 'no prices.json' } })
    for (const l of activity(doc).lines) expect(l.text.length <= 66).toBe(true)
  })
  test('says to fill the price file only when that is why every unpriced model has no price', () => {
    const lines = (unpriced: object) => text(activity(spending({ unpriced })).lines)
    const fill = 'Fill .sanvio/prices.json to see dollars'
    expect(lines({ a: 'no prices.json', b: 'no prices.json' })).toContain(`next prompt.\n${fill}\nGuard asked`)
    expect(lines({})).not.toContain(fill)
    expect(lines({ a: 'not in prices.json' })).not.toContain(fill)
    expect(lines({ a: 'unreadable' })).not.toContain(fill)
    expect(lines({ a: 'no prices.json', b: 'not in prices.json' })).not.toContain(fill)
  })
  test('with no spend fields it draws as it did, and with no table to carry them no estimate either', () => {
    const before = activity(DOC)
    expect(before.tables?.every(t => t.head.length === 2)).toBe(true)
    expect(text(before.lines)).toBe('Guard asked 2 times, since Oct 13')
    const unused = activity(spending({ skills: {}, agents: {}, commands: {} }))
    expect(unused.tables?.map(t => t.head[0])).toEqual(['Guard refused'])
    expect(text(unused.lines)).toBe('Guard asked 2 times, since Oct 13')
  })
  test("the loop's spend doesn't change with them", () => {
    expect(spend(spending())).toEqual(spend(DOC))
  })
})

group('the range', () => {
  test('counts today and the days before it, in local time, and asks the script for them', () => {
    const noon = new Date(2026, 9, 27, 12).getTime()
    expect(sinceFor(7, noon)).toBe('2026-10-21')
    expect(sinceFor(14, noon)).toBe('2026-10-14')
    expect(sinceFor(30, noon)).toBe('2026-09-28')
    expect(argv('2026-10-21')).toEqual(['python3', 'scripts/dashboard_data.py', '--json', '--since', '2026-10-21'])
  })
})

group('the root', () => {
  test('is the nearest folder up that has the dashboard script', async () => {
    const has = new Set(['/h/starter/scripts/dashboard_data.py'])
    expect(await findRoot('/h/starter/projects/app/', async p => has.has(p))).toBe('/h/starter')
    expect(await findRoot('/elsewhere', async p => has.has(p))).toBeNull()
  })
})
