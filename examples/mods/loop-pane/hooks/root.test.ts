import { describe, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const ROOT = '/h/starter'

// The engine beneath the plugin: a session whose root is `root`, a factory at ROOT with its loop
// script and no loop files yet, and a pane that opens.
function world(on: On, root: string): void {
  mock.clock(on, { now: 1_800_000_000_000 })
  on('session.start', async (_$, e) => ({ cwd: e.cwd }))
  on('session.root', async () => ({ value: root }))
  on('command.register', async (_$, e) => ({ value: { command: e.name } }))
  on('fs.exists', async (_$, e) => ({ value: e.path === `${ROOT}/scripts/loop.py` }))
  on('fs.read', async (_$, e) => ({ deny: `no ${e.path}` }))
  on('ui.open', async () => ({ value: { isPlaced: true } }))
  on('ui.panes', async () => ({ value: [] }))
}

const typed = { command: 'loop-pane', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } } as const

type Dollar = {
  session: { start: (i: { cwd: string; surface: null; isInteractive: boolean }) => Promise<unknown> }
  command: { run: (i: typeof typed) => Promise<unknown> }
}

async function loopPane($: Dollar): Promise<string> {
  return ((await $.command.run(typed)) as { text?: string }).text ?? ''
}

describe('/loop-pane after a /clear', () => {
  // A /clear starts a new session with no session.start, so a folder saved there is gone or the last session's.
  test('with no session.start, finds the loop from the session root', async ($, on) => {
    world(on, ROOT)
    expect(await loopPane($)).toBe('Loop pane opened.')
  })
  test('when the saved folder is outside any factory, finds it from the session root', async ($, on) => {
    world(on, ROOT)
    await $.session.start({ cwd: '/h/elsewhere', surface: null, isInteractive: true })
    expect(await loopPane($)).toBe('Loop pane opened.')
  })
  test('from a folder below the harness root', async ($, on) => {
    world(on, `${ROOT}/projects/app`)
    await $.session.start({ cwd: `${ROOT}/projects/app`, surface: null, isInteractive: true })
    expect(await loopPane($)).toBe('Loop pane opened.')
  })
  test('outside any factory, names the folder it looked from', async ($, on) => {
    world(on, '/h/elsewhere')
    await $.session.start({ cwd: '/h/elsewhere', surface: null, isInteractive: true })
    expect(await loopPane($)).toBe('No scripts/loop.py at or above /h/elsewhere, so there is no loop to show.')
  })
})
