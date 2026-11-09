import { describe, expect, test } from 'claude-code/testing'

import { STARTER, alwaysSteering, bandSegments, countSessions, emptyLens, endRun, gateRun, harnessSkill, lensReport, nextSessions, parseConfig, parseScope, planSegment, record, relative, remember, reviewSegment, scopeFiles, scopeText, settleRuns, skillFromPath, startRun, steeringName } from './logic'

const ROOT = '/h/my-harness'

describe('config', () => {
  test('no file is the default layout', () => {
    expect(parseConfig(null)).toEqual(STARTER)
  })
  test('a key given replaces that key only', () => {
    const config = parseConfig('{"steering": [".studio/steering"]}')
    expect(config.steering).toEqual(['.studio/steering'])
    expect(config.skills).toEqual(STARTER.skills)
  })
  test('broken JSON or a wrong shape falls back rather than failing', () => {
    expect(parseConfig('not json')).toEqual(STARTER)
    expect(parseConfig('{"steering": "steering"}').steering).toEqual(STARTER.steering)
  })
})

describe('paths', () => {
  test('inside the root, relative to it', () => {
    expect(relative(`${ROOT}/steering/gates.md`, ROOT)).toBe('steering/gates.md')
  })
  test('a sibling with a shared prefix is outside', () => {
    expect(relative('/h/my-harness-old/steering/gates.md', ROOT)).toBeNull()
  })
  test('a steering file, not its README or a nested file', () => {
    expect(steeringName('steering/gates.md', STARTER)).toBe('gates')
    expect(steeringName('steering/README.md', STARTER)).toBeNull()
    expect(steeringName('steering/old/gates.md', STARTER)).toBeNull()
  })
  test('a skill read from its file, including an example job', () => {
    expect(skillFromPath('skills/learn/SKILL.md', STARTER)).toBe('learn')
    expect(skillFromPath('examples/proposal/skills/draft-proposal/SKILL.md', STARTER)).toBe('draft-proposal')
    expect(skillFromPath('skills/learn/notes.md', STARTER)).toBeNull()
  })
})

describe('always-on steering', () => {
  test('reads the @ lines that name steering files', () => {
    const agents = 'Steering\n\n@steering/operating.md\n@steering/response-style.md\n@company/COMPANY.md\nsee @steering/gates.md inline\n'
    expect(alwaysSteering([agents], STARTER)).toEqual(['operating', 'response-style'])
  })
  test('another layout, from its config', () => {
    const config = parseConfig('{"steering": [".studio/steering"], "always": ["CLAUDE.md"]}')
    expect(alwaysSteering(['@.studio/steering/studio.md\n@.studio/steering/writer.md'], config)).toEqual(['studio', 'writer'])
  })
})

describe('skills', () => {
  test("only the harness's own, so a projector never lists personal plugins", () => {
    expect(harnessSkill('learn', ['learn', 'orientation'], STARTER)).toBe('learn')
    expect(harnessSkill('sales:call-prep', ['learn'], STARTER)).toBeNull()
  })
  test('a configured plugin namespace counts', () => {
    const config = parseConfig('{"skillPrefixes": ["studio:"]}')
    expect(harnessSkill('studio:phase-gate', [], config)).toBe('phase-gate')
  })
})

describe('gates', () => {
  test('a gate that passed', () => {
    expect(gateRun('python3 gates/proposal_gate.py out.md', 'PASS out.md', false, STARTER)).toEqual({ name: 'proposal', ok: true })
  })
  test('a gate that failed, piped through tail so the exit code is lost', () => {
    expect(gateRun('python3 examples/proposal/gates/proposal_gate.py bad.md | tail -20', 'FAIL bad.md\n  missing Fees', false, STARTER)).toEqual({
      name: 'proposal',
      ok: false,
    })
  })
  test('an error exit is a failure whatever it printed', () => {
    expect(gateRun('python3 gates/status_gate.py', '', true, STARTER)).toEqual({ name: 'status', ok: false })
  })
  test("output that doesn't say isn't counted as a pass", () => {
    expect(gateRun('python3 gates/proposal_gate.py out.md > log.txt', '', false, STARTER)).toBeNull()
  })
  test('the pre-commit hook refusing a commit', () => {
    expect(gateRun("git commit -m 'x'", "FAIL a.md\nCommit blocked. Fix what's named above.", false, STARTER)).toEqual({ name: 'pre-commit', ok: false })
  })
  test('a hook that prints its refusal in colour', () => {
    expect(gateRun('git commit -m x', '\x1b[0;31mBLOCKED: 1 violation(s) found.\x1b[0m', false, STARTER)).toEqual({ name: 'pre-commit', ok: false })
  })
  test('a commit that went through says nothing: the hook is silent when it passes', () => {
    expect(gateRun("git commit -m 'x'", '[main 070be4f] x', false, STARTER)).toBeNull()
  })
  test('an ordinary command is no gate', () => {
    expect(gateRun('ls -la', 'PASS', false, STARTER)).toBeNull()
  })
  test('a configured pattern, and a bad one is skipped', () => {
    const config = parseConfig('{"gates": ["(", "check-gates\\\\.sh\\\\s+(\\\\S+)"]}')
    expect(gateRun('.studio/skills/run-gates/scripts/check-gates.sh build_to_validate', '✗ File missing', false, config)).toEqual({
      name: 'build_to_validate',
      ok: false,
    })
  })
})

describe('the band', () => {
  const lens = { ...emptyLens(ROOT, ['operating', 'response-style', 'data-and-tools']), turn: 2 }

  test('a fresh session: three always on, nothing else yet', () => {
    expect(bandSegments(lens).map(segment => `${segment.label}: ${segment.text}`)).toEqual([
      'steering: 3 always on',
      'skill: none yet',
      'gate: none run',
      'guard: no refusals',
      'review: none yet',
      'running: none',
    ])
  })
  test('what acted this turn stands out, a failure in red', () => {
    const now = {
      ...lens,
      steering: [{ name: 'gates', turn: 2 }],
      skills: [{ name: 'learn', turn: 2 }],
      gates: [{ name: 'proposal', ok: false, turn: 2 }],
      refusals: [{ name: 'Bash', turn: 2 }],
    }
    const segments = bandSegments(now)
    expect(segments[0]).toEqual({ label: 'steering', text: '3 always on + gates', tone: 'now' })
    expect(segments[2]).toEqual({ label: 'gate', text: '✗ proposal', tone: 'fail' })
    expect(segments[3]).toEqual({ label: 'guard', text: '✗ refused Bash', tone: 'fail' })
  })
  test('what acted in an earlier turn is dim, and steering read earlier is counted', () => {
    const earlier = { ...lens, steering: [{ name: 'gates', turn: 1 }], gates: [{ name: 'proposal', ok: true, turn: 1 }] }
    const segments = bandSegments(earlier)
    expect(segments[0]).toEqual({ label: 'steering', text: '3 always on + 1 read', tone: 'earlier' })
    expect(segments[2]?.tone).toBe('earlier')
  })
})

describe('reviewers while they run', () => {
  const AGENTS = ['reviewer', 'security-reviewer', 'cto', 'gc']
  const NOW = 1_000_000
  const lens = { ...emptyLens(ROOT, ['operating']), turn: 3 }
  const started = (...names: string[]) =>
    names.reduce((l, name, i) => startRun(l, `a${i}`, name, AGENTS, NOW - 80_000), lens)

  test('one running shows its name and how long it has run', () => {
    expect(reviewSegment(started('reviewer'), NOW)).toEqual({ label: 'review', text: '▶ reviewer 1:20', tone: 'now' })
  })
  test('one that ended shows ✓, one that ended in an error ✗, standing out only the turn it ended', () => {
    const passed = endRun(started('reviewer'), 'a0', true, NOW)
    expect(reviewSegment(passed, NOW)).toEqual({ label: 'review', text: '✓ reviewer', tone: 'pass' })
    expect(reviewSegment(endRun(started('reviewer'), 'a0', false, NOW), NOW)).toEqual({ label: 'review', text: '✗ reviewer', tone: 'fail' })
    expect(reviewSegment({ ...passed, turn: 4 }, NOW).tone).toBe('earlier')
  })
  test('two or three running show the count and the names; four, the count alone', () => {
    expect(reviewSegment(started('reviewer', 'security-reviewer'), NOW).text).toBe('▶ 2 reviewer · security-reviewer')
    expect(reviewSegment(started('reviewer', 'security-reviewer', 'cto'), NOW).text).toBe('▶ 3 reviewer · security-reviewer · cto')
    expect(reviewSegment(started('reviewer', 'security-reviewer', 'cto', 'gc'), NOW)).toEqual({ label: 'review', text: '▶ 4', tone: 'now' })
  })
  test('the last to end shows, not the last to start', () => {
    let both = started('reviewer', 'security-reviewer')
    both = endRun(endRun(both, 'a1', true, NOW - 1_000), 'a0', false, NOW)
    expect(reviewSegment(both, NOW).text).toBe('✗ reviewer')
  })
  test("an agent that isn't the harness's, or an end nobody started, changes nothing", () => {
    expect(startRun(lens, 'x', 'Explore', AGENTS, NOW).runs).toEqual([])
    const one = started('reviewer')
    expect(endRun(one, 'other', true, NOW)).toBe(one)
  })
  test('a run the lens missed ending is settled from the agent list: completed ✓, failed or killed ✗', () => {
    expect(reviewSegment(settleRuns(started('reviewer'), [{ id: 'a0', status: 'completed' }], NOW), NOW)).toEqual({ label: 'review', text: '✓ reviewer', tone: 'pass' })
    for (const status of ['failed', 'killed']) {
      expect(reviewSegment(settleRuns(started('reviewer'), [{ id: 'a0', status }], NOW), NOW)).toEqual({ label: 'review', text: '✗ reviewer', tone: 'fail' })
    }
  })
  test('a run gone from the agent list ends with its outcome unknown', () => {
    const gone = settleRuns(started('reviewer'), [], NOW)
    expect(gone.runs[0]).toEqual({ id: 'a0', name: 'reviewer', started: NOW - 80_000, ended: NOW, turn: 3 })
    expect(reviewSegment(gone, NOW)).toEqual({ label: 'review', text: '? reviewer', tone: 'quiet' })
  })
  test('a run the agent list says is still working stays open, and nothing is written', () => {
    for (const status of ['pending', 'running', 'waiting', 'idle']) {
      const one = started('reviewer')
      const after = settleRuns(one, [{ id: 'a0', status }], NOW)
      expect(after).toBe(one)
      expect(reviewSegment(after, NOW).text).toBe('▶ reviewer 1:20')
    }
  })
  test('a run already ended keeps how it ended, whatever the agent list says', () => {
    const ended = endRun(started('reviewer'), 'a0', false, NOW - 5_000)
    const after = settleRuns(ended, [{ id: 'a0', status: 'completed' }], NOW)
    expect(after).toBe(ended)
    expect([after.runs[0]?.ended, after.runs[0]?.ok]).toEqual([NOW - 5_000, false])
  })
  test('one call settles only the runs whose row says they ended', () => {
    const four = started('reviewer', 'security-reviewer', 'cto', 'gc')
    const after = settleRuns(four, [{ id: 'a0', status: 'completed' }, { id: 'a1', status: 'running' }, { id: 'a3', status: 'killed' }], NOW)
    expect(after.runs.map(run => [run.name, run.ended, run.ok])).toEqual([
      ['reviewer', NOW, true],
      ['security-reviewer', undefined, undefined],
      ['cto', NOW, undefined],
      ['gc', NOW, false],
    ])
    expect(reviewSegment(after, NOW).text).toBe('▶ security-reviewer 1:20')
  })
  test('/lens lists what is running now, and says nothing when none is', () => {
    expect(lensReport(started('reviewer', 'cto'), false, NOW)).toContain('  Running now:\n    reviewer 1:20\n    cto 1:20')
    expect(lensReport(endRun(started('reviewer'), 'a0', true, NOW), false, NOW)).toContain('  Running now:\n    no reviewers')
  })
  test('no runs yet keeps the last reviewer seen, and a lens saved before runs still builds the band', () => {
    const seen = { ...lens, reviews: [{ name: 'cto', turn: 3 }] }
    expect(reviewSegment(seen, NOW)).toEqual({ label: 'review', text: 'cto', tone: 'now' })
    const old = JSON.parse(JSON.stringify({ ...seen, runs: undefined })) as typeof seen
    expect('runs' in old).toBe(false)
    expect(bandSegments(old, false, NOW).find(segment => segment.label === 'review')).toEqual({ label: 'review', text: 'cto', tone: 'now' })
    expect(lensReport(old, false, NOW)).toContain('Running now:\n    no reviewers')
    expect(startRun(old, 'a0', 'reviewer', AGENTS, NOW).runs).toEqual([{ id: 'a0', name: 'reviewer', started: NOW }])
  })
})

describe('headless sessions', () => {
  const PS = [
    '  PID  PPID COMMAND',
    '    1     0 /sbin/launchd',
    '  400     1 /bin/zsh -l',
    '  500   400 python3 scripts/eval_agents.py --agent claude',
    '  501   500 claude -p --output-format json',
    '  502   500 /usr/local/bin/claude -p --output-format json',
    '  600   400 python3 /h/other-clone/scripts/loop.py run',
    '  601   600 sandbox-exec -f /tmp/held.sb claude -p',
    '  602   601 claude -p --permission-mode acceptEdits',
    '  700   400 claude',
    '  800   801 claude -p',
    '  801   800 claude -p',
  ].join('\n')

  test('the default counts claude under the eval and under any clone\'s loop, not one under a shell', () => {
    expect(countSessions(PS, STARTER)).toEqual({ eval: 2, loop: 1 })
  })
  test('a loop in the rows ends the walk rather than hanging it', () => {
    expect(countSessions('  10    11 claude -p\n  11    10 bash', STARTER)).toEqual({})
  })
  test('a ps that failed keeps the last counts, and the same counts come back as the same object', () => {
    const prev = { loop: 1 }
    expect(nextSessions(prev, null, STARTER)).toBe(prev)
    expect(nextSessions(prev, '  600     1 python3 scripts/loop.py\n  601   600 claude -p', STARTER)).toBe(prev)
    expect(nextSessions(prev, '', STARTER)).toEqual({})
    expect(nextSessions(undefined, null, STARTER)).toBeUndefined()
  })
  test('the config keeps the default labels when left out or wrong, and a custom map replaces them', () => {
    expect(parseConfig('{}').running).toEqual(STARTER.running)
    expect(parseConfig('{"running": ["scripts/loop\\\\.py"]}').running).toEqual(STARTER.running)
    expect(parseConfig('{"running": {"loop": 3}}').running).toEqual(STARTER.running)
    expect(parseConfig('{"running": {"runner": "loop-runner", "bad": "(", "empty": ""}}').running).toEqual({ runner: 'loop-runner' })
    expect(countSessions(PS, parseConfig('{"running": {"clone": "other-clone"}}'))).toEqual({ clone: 1 })
  })
  test('the band lists the labels in order with their counts, or none', () => {
    const lens = { ...emptyLens(ROOT, []), sessions: { loop: 1, eval: 2, runner: 0 } }
    expect(bandSegments(lens).at(-1)).toEqual({ label: 'running', text: 'eval 2 · loop 1', tone: 'now' })
    expect(bandSegments({ ...lens, sessions: { loop: 0 } }).at(-1)).toEqual({ label: 'running', text: 'none', tone: 'quiet' })
  })
  test('/lens has a row for each configured label, a zero included', () => {
    const lens = { ...emptyLens(ROOT, []), sessions: { eval: 2 } }
    expect(lensReport(lens)).toContain('    no reviewers\n    loop sessions: 0\n    eval sessions: 2')
    expect(lensReport(lens, false, Date.now(), ['runner'])).toContain('    no reviewers\n    runner sessions: 0')
  })
})

describe('lists and the report', () => {
  test('a name seen again moves to the end', () => {
    expect(remember([{ name: 'a', turn: 1 }, { name: 'b', turn: 1 }], { name: 'a', turn: 2 }).map(hit => hit.name)).toEqual(['b', 'a'])
  })
  test('/lens counts repeat gates and never shows a reason', () => {
    let lens = emptyLens(ROOT, ['operating'])
    lens = { ...lens, gates: record(record(lens.gates, { name: 'proposal', ok: false, turn: 1 }), { name: 'proposal', ok: true, turn: 2 }) }
    lens = { ...lens, refusals: record(record(lens.refusals, { name: 'Bash', turn: 1 }), { name: 'Bash', turn: 2 }) }
    const report = lensReport(lens)
    expect(report).toContain('Gates: passed proposal; failed proposal')
    expect(report).toContain('Guard refusals: Bash ×2 (the reasons are in the transcript)')
  })
})

describe('scope', () => {
  const config = parseConfig(JSON.stringify({
    scope: ['.studio/hooks/.client-scope.{session}.json', '.studio/hooks/.client-scope.shared.json', '.studio/hooks/.focus.{session}.json'],
  }))
  test('the default declares no scope, so its band and report are unchanged', () => {
    expect(STARTER.scope).toEqual([])
    const lens = emptyLens(ROOT, [])
    expect(bandSegments(lens).map(s => s.label)).not.toContain('scope')
    expect(lensReport(lens)).not.toContain('Scope')
  })
  test('the session id fills {session}, in the order given', () => {
    expect(scopeFiles(config, '0a1d3a7a-eccd')).toEqual([
      '.studio/hooks/.client-scope.0a1d3a7a-eccd.json',
      '.studio/hooks/.client-scope.shared.json',
      '.studio/hooks/.focus.0a1d3a7a-eccd.json',
    ])
  })
  test('without a usable session id, a pattern that needs one is skipped', () => {
    expect(scopeFiles(config, null)).toEqual(['.studio/hooks/.client-scope.shared.json'])
    expect(scopeFiles(config, '../../etc')).toEqual(['.studio/hooks/.client-scope.shared.json'])
  })
  test('a pattern climbing out of the root is never read', () => {
    expect(scopeFiles(parseConfig('{"scope": ["../outside.json"]}'), null)).toEqual([])
  })
  test('a client guard file and a focus file both read', () => {
    expect(parseScope('{"client": " Acme "}')).toEqual({ kind: 'client', name: 'acme' })
    expect(parseScope('{"kind": "partner", "name": "fabrikam", "path": "partners/fabrikam"}')).toEqual({ kind: 'partner', name: 'fabrikam' })
    expect(parseScope('{"client": ""}')).toBeNull()
    expect(parseScope('not json')).toBeNull()
  })
  test('the segment comes first, names the kind, and says none when nothing is set', () => {
    const lens = { ...emptyLens(ROOT, []), scope: { kind: 'partner', name: 'fabrikam' } }
    expect(bandSegments(lens, true)[0]).toEqual({ label: 'scope', text: 'partner fabrikam', tone: 'earlier' })
    expect(bandSegments(emptyLens(ROOT, []), true)[0]).toEqual({ label: 'scope', text: 'none', tone: 'quiet' })
    expect(scopeText({ kind: 'harness', name: 'harness' })).toBe('harness')
    expect(lensReport(lens, true)).toContain('Scope: partner fabrikam')
  })
})

describe('plan', () => {
  // Every fixture carries an email and an org id, so a case that showed either would fail.
  const status = (fields: Record<string, unknown>) =>
    JSON.stringify({ loggedIn: true, authMethod: 'claude.ai', email: 'leak@x.test', orgId: 'org-LEAK-123', ...fields })
  const cases: Array<[string | null, string]> = [
    [status({ subscriptionType: 'team', orgName: 'Acme' }), 'Team · Acme'],
    [status({ subscriptionType: 'enterprise', orgName: 'Acme' }), 'Enterprise · Acme'],
    [status({ subscriptionType: 'pro', orgName: "pat@example.com's Organization" }), 'Pro (personal)'],
    [status({ subscriptionType: 'max', orgName: "pat@example.com's Organization" }), 'Max (personal)'],
    [status({ subscriptionType: 'free', orgName: "pat@example.com's Organization" }), 'Free (personal)'],
    [status({ authMethod: 'api_key' }), 'API key'],
    [status({ authMethod: 'api_key', subscriptionType: 'team', orgName: 'Acme' }), 'API key'],
    [status({ subscriptionType: 'team', orgName: "pat@example.com's Organization" }), 'Team'],
    [status({ subscriptionType: 'enterprise', orgName: '   ' }), 'Enterprise'],
    [status({ subscriptionType: 'team' }), 'Team'],
    [status({ subscriptionType: 'student', orgName: 'Acme' }), 'unknown'],
    [status({ orgName: 'Acme' }), 'unknown'],
    [status({ loggedIn: false, subscriptionType: 'team', orgName: 'Acme' }), 'unknown'],
    [null, 'unknown'],
    ['not json', 'unknown'],
  ]

  test('a business plan shows with its organisation', () => {
    expect(planSegment(status({ subscriptionType: 'team', orgName: 'Acme' }))).toEqual({ label: 'plan', text: 'Team · Acme', tone: 'earlier' })
    expect(planSegment(status({ subscriptionType: 'Enterprise', orgName: 'Acme' })).text).toBe('Enterprise · Acme')
  })
  test('a personal plan is yellow and never shows the organisation name', () => {
    for (const [type, text] of [['pro', 'Pro (personal)'], ['max', 'Max (personal)'], ['free', 'Free (personal)']]) {
      const segment = planSegment(status({ subscriptionType: type, orgName: "pat@example.com's Organization" }))
      expect(segment).toEqual({ label: 'plan', text: text!, tone: 'warn' })
      expect(segment.text).not.toContain('@')
      expect(segment.text).not.toContain('pat@example.com')
    }
  })
  test('a business plan leaves out an organisation name that is blank, missing or holds an @', () => {
    for (const orgName of ["pat@example.com's Organization", 'ops@acme.test', '', '   ', undefined, 42]) {
      expect(planSegment(status({ subscriptionType: 'team', orgName }))).toEqual({ label: 'plan', text: 'Team', tone: 'earlier' })
      expect(planSegment(status({ subscriptionType: 'enterprise', orgName }))).toEqual({ label: 'plan', text: 'Enterprise', tone: 'earlier' })
    }
  })
  test('the plan name is read in any case and with spaces around it, and the organisation name is trimmed', () => {
    for (const type of ['PRO', ' pro ', 'Pro']) expect(planSegment(status({ subscriptionType: type }))).toEqual({ label: 'plan', text: 'Pro (personal)', tone: 'warn' })
    expect(planSegment(status({ subscriptionType: ' TEAM ', orgName: '  Acme  ' }))).toEqual({ label: 'plan', text: 'Team · Acme', tone: 'earlier' })
  })
  test('an API key login shows as an API key', () => {
    expect(planSegment(status({ authMethod: 'api_key' }))).toEqual({ label: 'plan', text: 'API key', tone: 'earlier' })
    expect(planSegment(status({ authMethod: 'API Key' })).text).toBe('API key')
    expect(planSegment(status({ authMethod: 'apiKey' })).text).toBe('API key')
  })
  test('an API key wins over a subscription type, because an API key login has no plan', () => {
    for (const subscriptionType of ['team', 'enterprise', 'pro', 'max', 'free']) {
      expect(planSegment(status({ authMethod: 'api_key', subscriptionType, orgName: 'Acme' }))).toEqual({ label: 'plan', text: 'API key', tone: 'earlier' })
    }
  })
  test('a subscription type it does not know, or none, is unknown', () => {
    for (const subscriptionType of ['student', 'constructor', 'toString', '', 7, null, undefined]) {
      expect(planSegment(status({ subscriptionType, orgName: 'Acme' }))).toEqual({ label: 'plan', text: 'unknown', tone: 'quiet' })
    }
  })
  test('signed out, a failed or timed-out command, and output that is not JSON are unknown', () => {
    for (const output of [status({ loggedIn: false }), status({ loggedIn: 'true', subscriptionType: 'team' }), null, 'not json', '']) {
      expect(planSegment(output)).toEqual({ label: 'plan', text: 'unknown', tone: 'quiet' })
    }
  })
  test('JSON that is not an object is unknown', () => {
    for (const output of ['5', '[]', '[{"loggedIn": true, "subscriptionType": "team"}]', 'null', '"team"', 'true']) {
      expect(planSegment(output)).toEqual({ label: 'plan', text: 'unknown', tone: 'quiet' })
    }
  })
  test('every case gives the text it should, and none shows the email or the org id', () => {
    for (const [output, text] of cases) {
      const shown = planSegment(output).text
      expect(shown).toBe(text)
      expect(shown).not.toContain('leak@x.test')
      expect(shown).not.toContain('org-LEAK-123')
    }
  })
  test('the plan goes first and leaves the rest of the line as it was', () => {
    const lens = emptyLens(ROOT, ['operating'])
    const labels = bandSegments(lens, false, 1_000_000, planSegment(null)).map(segment => segment.label)
    expect(labels).toEqual(['plan', 'steering', 'skill', 'gate', 'guard', 'review', 'running'])
    expect(bandSegments(lens).map(segment => segment.label)).not.toContain('plan')
  })
  test('with a scope, the plan goes after it and before steering', () => {
    const lens = { ...emptyLens(ROOT, ['operating']), scope: { kind: 'client', name: 'acme' } }
    const plan = planSegment(JSON.stringify({ loggedIn: true, subscriptionType: 'team', orgName: 'Acme' }))
    const segments = bandSegments(lens, true, 1_000_000, plan)
    expect(segments.map(segment => segment.label)).toEqual(['scope', 'plan', 'steering', 'skill', 'gate', 'guard', 'review', 'running'])
    expect(segments[1]).toEqual({ label: 'plan', text: 'Team · Acme', tone: 'earlier' })
    expect(bandSegments(lens, true, 1_000_000).map(segment => segment.label)).toEqual(['scope', 'steering', 'skill', 'gate', 'guard', 'review', 'running'])
  })
})
