import { describe, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const ROOT = '/h/starter'
const START = { cwd: ROOT, surface: null, isInteractive: true } as const
const TICK = 3_000

// Made up, and carrying an email and an org id, so a band that showed either would fail.
const STATUS = (fields: Record<string, unknown>) =>
  JSON.stringify({ loggedIn: true, authMethod: 'claude.ai', email: 'leak@x.test', orgId: 'org-LEAK-123', ...fields })

type Ran = { argv: string[]; init: Record<string, unknown> | undefined }
// How `claude auth status` answers: what it printed and how it exited, or a call the engine refused,
// which is how a command that can't start or runs past its timeout comes back.
type Auth = { stdout: string; exitCode: number } | 'refused'

// A harness at ROOT (AGENTS.md beside steering/) with no skills or agents, a session that starts there,
// and an engine beneath the band that draws nothing. `ps` finds no headless sessions.
function stage(on: On, auth: Auth): { ran: Ran[]; clock: ReturnType<typeof mock.clock> } {
  const ran: Ran[] = []
  const clock = mock.clock(on, { now: 1_800_000_000_000 })
  on('session.start', async (_$, e) => ({ cwd: e.cwd }))
  on('session.root', async () => ({ value: ROOT }))
  on('command.register', async (_$, e) => ({ value: { command: e.name } }))
  on('fs.exists', async (_$, e) => ({ value: e.path === `${ROOT}/AGENTS.md` || e.path === `${ROOT}/steering` }))
  on('fs.read', async (_$, e) => (e.path === `${ROOT}/AGENTS.md` ? { value: '@steering/operating.md\n' } : { deny: `no ${e.path}` }))
  on('fs.list', async () => ({ value: [] }))
  on('process.run', async (_$, e) => {
    const argv = [...e.argv]
    ran.push({ argv, init: e.init as unknown as Record<string, unknown> | undefined })
    const done = (exitCode: number, stdout: string) => ({ value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
    if (argv[0] !== 'claude') return done(0, '  PID  PPID COMMAND\n')
    return auth === 'refused' ? { deny: 'timed out' } : done(auth.exitCode, auth.stdout)
  })
  on('ui.render', async () => ({ type: 'Box', props: {}, children: [] }) as never)
  return { ran, clock }
}

type Node = { type: string; props?: Record<string, unknown>; children?: (Node | string)[] }
const words = (n: Node | string): string => (typeof n === 'string' ? n : (n.children ?? []).map(words).join(''))
// The innermost node whose text is exactly `text`.
function holding(n: Node | string, text: string): Node | null {
  if (typeof n === 'string') return null
  for (const kid of n.children ?? []) {
    const found = holding(kid, text)
    if (found) return found
  }
  return words(n) === text ? n : null
}

type Dollar = {
  session: { start: (i: typeof START) => Promise<unknown> }
  ui: { mount: (i: never) => Promise<{ drawn: () => Promise<unknown>; unmount: () => Promise<unknown> }> }
}

// The band above the prompt, as drawn now.
async function band($: Dollar): Promise<Node> {
  const ui = await $.ui.mount({ plugin: 'harness-lens', surface: 'terminal', component: 'AbovePrompt', props: {} } as never)
  const drawn = (await ui.drawn()) as unknown as Node
  await ui.unmount()
  return drawn
}

const authCalls = (ran: Ran[]) => ran.filter(run => run.argv[0] === 'claude')

describe('the plan on the band', () => {
  test('session.start runs claude auth status once, with a two-second timeout and the session\'s own environment', async ($, on) => {
    const s = stage(on, { exitCode: 0, stdout: STATUS({ subscriptionType: 'team', orgName: 'Acme' }) })
    await $.session.start(START)
    await s.clock.settle()
    const calls = authCalls(s.ran)
    expect(calls.map(call => call.argv)).toEqual([['claude', 'auth', 'status']])
    expect(calls[0]?.init?.timeoutMs).toBe(2_000)
    expect(calls[0]?.init?.env).toBeUndefined()
  })
  test('a business plan shows with its organisation, first, and never the email or the org id', async ($, on) => {
    const s = stage(on, { exitCode: 0, stdout: STATUS({ subscriptionType: 'team', orgName: 'Acme' }) })
    await $.session.start(START)
    await s.clock.settle()
    const drawn = await band($)
    const text = words(drawn)
    expect(text).toContain('plan: Team · Acme')
    expect(text.indexOf('plan: ')).toBeLessThan(text.indexOf('steering: '))
    expect(text).not.toContain('leak@x.test')
    expect(text).not.toContain('org-LEAK-123')
  })
  test('a personal plan is drawn in yellow and bold', async ($, on) => {
    const s = stage(on, { exitCode: 0, stdout: STATUS({ subscriptionType: 'pro', orgName: "pat@example.com's Organization" }) })
    await $.session.start(START)
    await s.clock.settle()
    const drawn = await band($)
    const props = holding(drawn, 'Pro (personal)')?.props ?? {}
    expect([props.color, props.bold]).toEqual(['yellow', true])
    expect(words(drawn)).not.toContain('@')
  })
  test('a command that exits non-zero shows unknown, whatever it printed', async ($, on) => {
    const s = stage(on, { exitCode: 1, stdout: STATUS({ subscriptionType: 'team', orgName: 'Acme' }) })
    await $.session.start(START)
    await s.clock.settle()
    const text = words(await band($))
    expect(text).toContain('plan: unknown')
    expect(text).not.toContain('Team')
  })
  test('a command that fails or times out shows unknown, and the rest of session.start still runs', async ($, on) => {
    const s = stage(on, 'refused')
    await $.session.start(START)
    await s.clock.settle()
    expect(words(await band($))).toContain('plan: unknown')
    // The timer started after the plan was read: its first tick runs ps.
    await s.clock.advance(TICK)
    expect(s.ran.some(run => run.argv[0] === 'ps')).toBe(true)
  })
  test('a redraw or a tick never runs the command again, and a reload reads it once more', async ($, on) => {
    const s = stage(on, { exitCode: 0, stdout: STATUS({ subscriptionType: 'max' }) })
    await $.session.start(START)
    await s.clock.settle()
    await band($)
    await s.clock.advance(TICK)
    await band($)
    expect(authCalls(s.ran).length).toBe(1)
    await $.session.start(START)
    await s.clock.settle()
    expect(authCalls(s.ran).length).toBe(2)
    expect(words(await band($))).toContain('plan: Max (personal)')
  })
})
