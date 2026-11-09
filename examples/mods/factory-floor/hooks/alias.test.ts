import { describe, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const ROOT = '/h/starter'

// root.test.ts's engine: a session whose root is ROOT, a factory there with its loop script and no loop
// files yet, and a pane that opens. Added: what it records, a pane that can start shown, and a
// registration that can be refused by name.
type Options = { refuse?: string; isShown?: boolean }
function world(on: On, options: Options = {}) {
  const clock = mock.clock(on, { now: 1_800_000_000_000 })
  const registered: string[] = []
  const titles: string[] = []
  const toasts: string[] = []
  const stored = new Map<string, unknown>()
  const panes = options.isShown ? [{ id: 'factory-floor', isShown: true, isPlaced: true }] : []
  const flip = { closes: 0 }
  on('session.start', async (_$, e) => ({ cwd: e.cwd }))
  on('session.root', async () => ({ value: ROOT }))
  on('command.register', async (_$, e) => {
    if (e.name === options.refuse) return { deny: `/${e.name} is taken` }
    registered.push(e.name)
    return { value: { command: e.name } }
  })
  on('fs.exists', async (_$, e) => ({ value: e.path === `${ROOT}/scripts/loop.py` }))
  on('fs.read', async (_$, e) => ({ deny: `no ${e.path}` }))
  on('ui.open', async (_$, e) => {
    titles.push(e.title ?? '')
    return { value: { isPlaced: true } }
  })
  on('ui.close', async () => {
    flip.closes++
    panes.length = 0
    return { value: undefined }
  })
  on('ui.panes', async () => ({ value: [...panes] }) as never)
  on('ui.toast', async (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('state.set', async (_$, e, next) => {
    const at = e as unknown as { plugin: string; key: string; value: unknown }
    if (at.plugin === 'factory-floor') stored.set(at.key, at.value)
    return next(e)
  })
  return { clock, registered, titles, toasts, stored, flip }
}

const typed = (command: string) =>
  ({ command, args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } }) as const

type Dollar = {
  session: { start: (i: { cwd: string; surface: null; isInteractive: boolean }) => Promise<unknown> }
  command: { run: (i: ReturnType<typeof typed>) => Promise<unknown> }
}

async function run($: Dollar, command: string): Promise<string> {
  return ((await $.command.run(typed(command))) as { text?: string }).text ?? ''
}

const start = ($: Dollar) => $.session.start({ cwd: ROOT, surface: null, isInteractive: true })

describe('the old names', () => {
  test('session.start registers /factory-floor, then /loop-pane and /loop-crew', async ($, on) => {
    const { registered } = world(on)
    await start($)
    expect(registered).toEqual(['factory-floor', 'loop-pane', 'loop-crew'])
  })
  test('/loop-pane opens the pane in the List view and says the new name', async ($, on) => {
    const { titles, toasts, stored } = world(on)
    await start($)
    expect(await run($, 'loop-pane')).toBe('Loop pane opened.')
    expect(titles).toEqual(['Loop'])
    expect(stored.get('mode')).toBe('list')
    expect(toasts).toEqual(['/loop-pane is now /factory-floor. The old name goes in a later release.'])
  })
  test('/loop-crew opens the pane in the Crew view and says the new name', async ($, on) => {
    const { titles, toasts, stored } = world(on)
    await start($)
    expect(await run($, 'loop-crew')).toBe('Loop pane opened.')
    expect(titles).toEqual(['Loop', 'Loop crew'])
    expect(stored.get('mode')).toBe('crew')
    expect(toasts).toEqual(['/loop-crew is now /factory-floor. The old name goes in a later release.'])
  })
  for (const name of ['loop-pane', 'loop-crew'] as const) {
    test(`/${name} on a pane already shown leaves it open`, async ($, on) => {
      const { titles, flip } = world(on, { isShown: true })
      expect(await run($, name)).toBe('Loop pane opened.')
      expect(flip.closes).toBe(0)
      expect(titles[0]).toBe('Loop')
    })
  }
  for (const [refused, other] of [['loop-pane', 'loop-crew'], ['loop-crew', 'loop-pane']] as const) {
    test(`/${refused} refused leaves /factory-floor and /${other} working`, async ($, on) => {
      const { registered } = world(on, { refuse: refused })
      await start($)
      expect(registered).toEqual(['factory-floor', other])
      expect(await run($, 'factory-floor')).toBe('Loop pane opened.')
    })
  }
})
