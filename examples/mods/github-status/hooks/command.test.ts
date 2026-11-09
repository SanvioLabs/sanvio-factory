import { describe, expect, mock, test } from 'claude-code/testing'
import type { FsEntry, On } from 'claude-code'

const ROOT = '/h/starter'
const COUNTS = (pulls: number) => JSON.stringify({ data: { repository: { pullRequests: { totalCount: pulls }, issues: { totalCount: 1 } } } })

type Options = {
  betaFails?: boolean
  // This session's id, from a variable a test changes between calls. Null is an id the engine refuses.
  session?: { id: string | null }
  // The factory's folder has no GitHub remote.
  noRemote?: boolean
  // Every fs.write is refused.
  writesFail?: boolean
  // Every gh call fails while this is set.
  gh?: { isDown?: boolean; hold?: Promise<void> | null }
  // Called with each git command as it runs.
  onGit?: ((argv: string[]) => void) | undefined
}

// A factory at ROOT with three folders under projects/: acme and beta are clones on GitHub, notes is a plain folder.
// gh answers each repo with its own pull request count, and fails for beta when beta-fails is set.
// fs.read answers from `files`, fs.write records each path and text and stores it, and fs.stat knows the
// real folders, a file in projects/, a link, and a folder named off.
function stage(on: On, options: Options = {}) {
  const ran: string[][] = []
  const reads: string[] = []
  const exists: string[] = []
  const writes: { path: string; text: string }[] = []
  const files = new Map<string, string>()
  const registered: string[] = []
  const clock = mock.clock(on, { now: 1_800_000_000_000 })
  // The engine beneath the plugins: a session that starts, and a command it takes.
  on('session.start', async (_$, e) => ({ cwd: e.cwd }))
  on('session.root', async () => ({ value: ROOT }))
  on('command.register', async (_$, e) => {
    registered.push(e.name)
    return { value: { command: e.name } }
  })
  on('session.id', async () => {
    const id = options.session?.id ?? null
    return id === null ? { deny: 'no session id' } : { value: id }
  })
  on('fs.read', async (_$, e) => {
    reads.push(e.path)
    const text = files.get(e.path)
    return text === undefined ? { deny: `no ${e.path}` } : { value: text }
  })
  on('fs.write', async (_$, e) => {
    if (options.writesFail) return { deny: 'read-only' }
    writes.push({ path: e.path, text: e.text })
    files.set(e.path, e.text)
    return { value: undefined }
  })
  on('fs.stat', async (_$, e) => {
    const name = e.path.startsWith(`${ROOT}/projects/`) ? e.path.slice(`${ROOT}/projects/`.length) : ''
    if (['acme', 'beta', 'notes', 'off'].includes(name)) return { value: { kind: 'dir', size: 0, mtimeMs: 0, isLink: false } }
    if (name === 'README.md') return { value: { kind: 'file', size: 1, mtimeMs: 0, isLink: false } }
    if (name === 'linked') return { value: { kind: 'dir', size: 0, mtimeMs: 0, isLink: true } }
    return { deny: `no ${e.path}` }
  })
  on('prompt.compose', async () => ({ sections: [{ id: 'intro', text: 'The engine\'s own.', scope: 'shared' }] }))
  on('fs.list', async (_$, e, next) =>
    e.path === `${ROOT}/projects`
      ? { value: [
          ...['acme', 'beta', 'notes', '.cache'].map((name): FsEntry => ({ name, kind: 'dir', size: 0, mtimeMs: 0, isLink: false })),
          { name: 'README.md', kind: 'file', size: 1, mtimeMs: 0, isLink: false } satisfies FsEntry,
        ] }
      : next(e))
  on('fs.exists', async (_$, e, next) => {
    if (!e.path.startsWith(`${ROOT}/projects/`)) return next(e)
    exists.push(e.path)
    return { value: /\/projects\/(acme|beta)\/\.git$/.test(e.path) }
  })
  on('process.run', async (_$, e) => {
    const argv = [...e.argv]
    ran.push(argv)
    const ok = (stdout: string) => ({ value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
    const fail = { value: { exitCode: 1, stdout: '', stderr: 'no', isStdoutTruncated: false, isStderrTruncated: false } }
    if (argv[0] === 'git') {
      options.onGit?.(argv)
      const remotes: Record<string, string> = {
        ...(options.noRemote ? {} : { [ROOT]: 'git@github.com:SanvioLabs/sanvio-factory.git' }),
        [`${ROOT}/projects/acme`]: 'https://github.com/acme/app.git',
        [`${ROOT}/projects/beta`]: 'git@github.com:beta/site.git',
        // Not a clone: git inside it finds the factory's own repo.
        [`${ROOT}/projects/notes`]: 'git@github.com:SanvioLabs/sanvio-factory.git',
      }
      const url = remotes[argv[2] ?? '']
      return url ? ok(url) : fail
    }
    const text = argv.join(' ')
    const hold = options.gh?.hold
    if (hold) await hold
    if (options.gh?.isDown) return fail
    if (options.betaFails && text.includes('beta')) return fail
    if (text.includes('graphql')) return ok(COUNTS(text.includes('owner=acme') ? 4 : text.includes('owner=beta') ? 7 : 2))
    return ok('{"total_count": 0}')
  })
  on('ui.render', async () => ({ type: 'Box', props: {}, children: [] }) as never)
  return { ran, reads, exists, writes, files, registered, clock }
}

const world = (on: On, options: Options = {}): string[][] => stage(on, options).ran

// What the person sees after typing /github with these arguments, as a command run from the prompt.
const typed = (args: string, command = 'github') =>
  ({ command, args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } }) as const

type Dollar = {
  session: { start: (i: { cwd: string; surface: null; isInteractive: boolean }) => Promise<unknown> }
  command: { run: (i: ReturnType<typeof typed>) => Promise<unknown> }
  ui: { mount: (i: never) => Promise<{ drawn: () => Promise<unknown>; unmount: () => Promise<unknown> }> }
  prompt: {
    compose: (i: { model: string; promptModel: string; surfaces: readonly never[]; tools: readonly never[]; outputStyle: null; traits: readonly never[] }) =>
      Promise<{ sections: readonly { id: string; text: string; scope: string }[] }>
  }
}

async function github($: Dollar, args: string): Promise<string> {
  await $.session.start({ cwd: ROOT, surface: null, isInteractive: true })
  const result = await $.command.run(typed(args))
  return (result as { text?: string }).text ?? ''
}

const A = 'aaaaaaaa-1111'
const B = 'bbbbbbbb-2222'
const fileOf = (id: string) => `${ROOT}/.sanvio/project/${id}`
const TICK = 15_000
const LIMIT = 120_000
const ACME = 'acme: acme/app · 0 actions running · 4 open pull requests · 1 open issue'
const BETA = 'beta: beta/site · 0 actions running · 7 open pull requests · 1 open issue'
const HARNESS = 'SanvioLabs/sanvio-factory · 0 actions running · 2 open pull requests · 1 open issue'

const start = ($: Dollar) => $.session.start({ cwd: ROOT, surface: null, isInteractive: true })
const textOf = (result: unknown) => (result as { text?: string }).text ?? ''
const project = async ($: Dollar, args = '') => textOf(await $.command.run(typed(args, 'project')))
const gitHub = async ($: Dollar, args = '') => textOf(await $.command.run(typed(args)))

// What the line above the prompt draws now.
async function drawn($: Dollar): Promise<string> {
  const ui = await $.ui.mount({ plugin: 'github-status', surface: 'terminal', component: 'AbovePrompt', props: {} } as never)
  const text = JSON.stringify(await ui.drawn())
  await ui.unmount()
  return text
}

// How many reads of this owner's repo gh has been asked for: one graphql call per read.
const readsOf = (ran: string[][], owner: string) => ran.filter(a => a[0] === 'gh' && a.join(' ').includes('graphql') && a.join(' ').includes(`owner=${owner}`)).length
const ghCalls = (ran: string[][]) => ran.filter(a => a[0] === 'gh')
// Every fact a render has: next(e) hands them on, and the kit skips a hook whose next() has no outputStyle.
const composed = async ($: Dollar) =>
  (await $.prompt.compose({ model: 'm', promptModel: 'm', surfaces: [], tools: [], outputStyle: null, traits: [] })).sections
const readsOfFile = (reads: string[], path: string) => reads.filter(p => p === path).length

// A gate gh waits at while it's in Options' hold, and what opens it.
function gate(): { hold: Promise<void>; open: () => void } {
  let open = () => {}
  const hold = new Promise<void>(resolve => { open = resolve })
  return { hold, open }
}

// First in the file. Each needs no timer and no repo to start from, so these rely on the kit loading the
// module afresh for each test, which loop-pane's polling tests need too.
describe('/project with no session.start, as after a /clear', () => {
  test('alone looks up the factory and starts the timer', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    expect(await project($)).toBe('No project in focus.')
    await s.clock.advance(TICK)
    expect(readsOf(s.ran, 'SanvioLabs')).toBe(1)
    const line = await drawn($)
    expect(line).toContain(HARNESS)
    expect(line).not.toContain('no GitHub remote')
  })
  test('off looks up the factory and starts the timer', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await project($, 'off')
    await s.clock.settle()
    expect(ghCalls(s.ran)).toEqual([])
    await s.clock.advance(TICK)
    expect(readsOf(s.ran, 'SanvioLabs')).toBe(1)
    expect(await drawn($)).toContain(HARNESS)
  })
  test('saves under the session root, reads, and starts the timer', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    expect(await project($, 'acme')).toBe(ACME)
    expect(s.writes).toEqual([{ path: fileOf(A), text: 'acme\n' }])
    s.files.set(fileOf(A), 'beta\n')
    await s.clock.advance(TICK)
    expect(readsOf(s.ran, 'beta')).toBe(1)
  })
  test('/project off then shows the factory, and /github all names it', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await project($, 'acme')
    await project($, 'off')
    await s.clock.settle()
    expect(await drawn($)).toContain(HARNESS)
    expect((await gitHub($, 'all')).split('\n')[0]).toBe(`factory: ${HARNESS}`)
  })
})

describe('the commands', () => {
  test('session.start registers /github and /project', async ($, on) => {
    const s = stage(on)
    await start($)
    expect(s.registered).toEqual(['github', 'project'])
  })
})

describe('/github on a project', () => {
  test('reads the project folder named, with or without projects/', async ($, on) => {
    world(on)
    expect(await github($, 'acme')).toBe('acme: acme/app · 0 actions running · 4 open pull requests · 1 open issue')
    expect(await github($, 'projects/beta')).toBe('beta: beta/site · 0 actions running · 7 open pull requests · 1 open issue')
  })
  test('a folder with no GitHub remote, or no folder, says so and never calls gh', async ($, on) => {
    const ran = world(on)
    expect(await github($, 'notes')).toBe('projects/notes has no GitHub origin remote, so there\'s nothing to read.')
    expect(await github($, 'nope')).toBe("projects/nope isn't a folder.")
    expect(ran.filter(a => a[0] === 'gh' && a.join(' ').includes('notes'))).toEqual([])
  })
  test('a name that could leave projects/ runs nothing', async ($, on) => {
    const ran = world(on)
    await $.session.start({ cwd: ROOT, surface: null, isInteractive: true })
    const text = ((await $.command.run(typed('../secrets'))) as { text?: string }).text ?? ''
    expect(text).toContain("isn't a project")
    expect(ran.filter(a => a.join(' ').includes('secrets'))).toEqual([])
  })
  test('a failed read shows that repo as unavailable', async ($, on) => {
    world(on, { betaFails: true })
    expect(await github($, 'beta')).toBe('beta: beta/site · GitHub unavailable (is gh installed and signed in?)')
  })
})

describe('/github after a /clear', () => {
  // A /clear starts a new session with no session.start, so a folder saved there is gone or the last session's.
  test('with no session.start, reads the project from the session root', async ($, on) => {
    world(on)
    const text = ((await $.command.run(typed('acme'))) as { text?: string }).text ?? ''
    expect(text).toBe('acme: acme/app · 0 actions running · 4 open pull requests · 1 open issue')
  })
})

describe('/github all', () => {
  test('the factory, each project with a remote in name order, and a count of the rest', async ($, on) => {
    world(on, { betaFails: true })
    expect(await github($, 'all')).toBe([
      'factory: SanvioLabs/sanvio-factory · 0 actions running · 2 open pull requests · 1 open issue',
      'acme: acme/app · 0 actions running · 4 open pull requests · 1 open issue',
      'beta: beta/site · GitHub unavailable (is gh installed and signed in?)',
      '1 folder under projects/ has no GitHub remote.',
    ].join('\n'))
  })
  test('the line above the prompt stays the factory\'s', async ($, on) => {
    world(on)
    await github($, 'acme')
    const ui = await $.ui.mount({ plugin: 'github-status', surface: 'terminal', component: 'AbovePrompt', props: {} as never })
    const drawn = JSON.stringify(await ui.drawn())
    expect(drawn).toContain('SanvioLabs/sanvio-factory')
    expect(drawn).not.toContain('acme/app')
    await ui.unmount()
  })
})

describe('/project <name>', () => {
  test('writes the name and a newline to this session\'s file, then prints the line, read now', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await start($)
    await s.clock.settle()
    expect(await project($, 'acme')).toBe(ACME)
    expect(s.writes).toEqual([{ path: fileOf(A), text: 'acme\n' }])
    expect(readsOf(s.ran, 'acme')).toBe(1)
    expect(await drawn($)).toContain(ACME)
  })
  test('takes projects/<name> and writes the bare name', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await start($)
    expect(await project($, 'projects/beta')).toBe(BETA)
    expect(s.writes).toEqual([{ path: fileOf(A), text: 'beta\n' }])
  })
  test('counts as the read of that repo for the limit', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await start($)
    await s.clock.settle()
    await project($, 'acme')
    await s.clock.advance(LIMIT - 1_000)
    expect(readsOf(s.ran, 'acme')).toBe(1)
    await s.clock.advance(1_000 + TICK)
    expect(readsOf(s.ran, 'acme')).toBe(2)
  })
  test('prints its own project\'s line when the focus moves during the read, and the line stays out of it', async ($, on) => {
    const gh: NonNullable<Options['gh']> = {}
    const s = stage(on, { session: { id: A }, gh })
    await start($)
    await s.clock.settle()
    const held = gate()
    gh.hold = held.hold
    const printed = project($, 'acme')
    await s.clock.settle()
    expect(readsOf(s.ran, 'acme')).toBe(1)
    gh.hold = null
    s.files.set(fileOf(A), 'beta\n')
    held.open()
    expect(await printed).toBe(ACME)
    expect(await drawn($)).not.toContain(ACME)
    await s.clock.advance(TICK)
    expect(await drawn($)).toContain(BETA)
  })
  test('a name that fails the rule says why in /project\'s words, writes nothing and calls no gh', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await start($)
    await s.clock.settle()
    const before = ghCalls(s.ran).length
    for (const arg of ['README.md', 'linked', 'nope', '../secrets', 'projects/off', 'off/', 'two words']) {
      const text = await project($, arg)
      expect(text).toContain('/project')
      expect(text).not.toContain('/github')
    }
    expect(s.writes).toEqual([])
    expect(ghCalls(s.ran).length).toBe(before)
  })
  test('a write that fails says the focus couldn\'t be saved, changes nothing and calls no gh', async ($, on) => {
    const s = stage(on, { session: { id: A }, writesFail: true })
    await start($)
    await s.clock.settle()
    const before = ghCalls(s.ran).length
    expect(await project($, 'acme')).toContain("couldn't be saved")
    expect(await project($, 'off')).toContain("couldn't be saved")
    expect(s.writes).toEqual([])
    expect(ghCalls(s.ran).length).toBe(before)
    expect(await drawn($)).toContain(HARNESS)
    expect(await project($)).toBe('No project in focus.')
  })
})

describe('/project off and /project alone', () => {
  test('off writes the file empty, says the line is the factory\'s, and the line stops showing the project', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await start($)
    await project($, 'acme')
    expect(await project($, 'off')).toContain("shows the factory's repo again")
    expect(s.writes.at(-1)).toEqual({ path: fileOf(A), text: '' })
    expect(s.files.get(fileOf(A))).toBe('')
    await s.clock.settle()
    const line = await drawn($)
    expect(line).toContain(HARNESS)
    expect(line).not.toContain('acme')
    expect(await project($)).toBe('No project in focus.')
  })
  test('off doesn\'t wait for the factory\'s read, and the project is gone from the line at once', async ($, on) => {
    const gh: NonNullable<Options['gh']> = {}
    const s = stage(on, { session: { id: A }, gh })
    await start($)
    await project($, 'acme')
    let release = () => {}
    gh.hold = new Promise<void>(resolve => { release = resolve })
    await project($, 'off')
    const line = await drawn($)
    expect(line).toContain('SanvioLabs/sanvio-factory · reading…')
    expect(line).not.toContain('acme')
    gh.hold = null
    release()
    await s.clock.settle()
    expect(await drawn($)).toContain(HARNESS)
  })
  test('off with no project in focus starts no read', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await start($)
    await s.clock.settle()
    const before = ghCalls(s.ran).length
    await project($, 'off')
    await s.clock.settle()
    expect(ghCalls(s.ran).length).toBe(before)
  })
  test('off on a factory with no remote shows that at once', async ($, on) => {
    const s = stage(on, { session: { id: A }, noRemote: true })
    await start($)
    await project($, 'acme')
    expect(await project($, 'off')).toContain("shows the factory's repo again")
    const line = await drawn($)
    expect(line).toContain('no GitHub remote')
    expect(line).not.toContain('acme')
    await s.clock.settle()
    expect(readsOf(s.ran, 'SanvioLabs')).toBe(0)
  })
  test('alone prints the project in focus, or that there\'s none', async ($, on) => {
    stage(on, { session: { id: A } })
    await start($)
    expect(await project($)).toBe('No project in focus.')
    await project($, 'acme')
    expect(await project($)).toBe('In focus: projects/acme.')
  })
})

describe('the session\'s file', () => {
  test('one session\'s focus is never read or written by the other', async ($, on) => {
    const session: { id: string | null } = { id: A }
    const s = stage(on, { session })
    await start($)
    await s.clock.settle()
    await project($, 'acme')
    await composed($)
    await s.clock.advance(TICK)
    expect(s.writes.map(w => w.path)).toEqual([fileOf(A)])
    expect(s.reads.filter(p => p === fileOf(B))).toEqual([])

    session.id = B
    s.reads.length = 0
    s.writes.length = 0
    expect(await project($)).toBe('No project in focus.')
    expect((await composed($)).map(x => x.id)).toEqual(['intro'])
    await project($, 'beta')
    await s.clock.advance(TICK)
    expect(s.writes).toEqual([{ path: fileOf(B), text: 'beta\n' }])
    expect(s.reads.filter(p => p === fileOf(A))).toEqual([])
    expect(s.reads).toContain(fileOf(B))

    session.id = A
    s.reads.length = 0
    s.writes.length = 0
    expect(await project($)).toBe('In focus: projects/acme.')
    expect(s.writes).toEqual([])
    expect(s.reads.filter(p => p === fileOf(B))).toEqual([])
  })
  for (const [why, id] of [['refused', null], ['failing the pattern', '../../etc/passwd'], ['too short', 'abc']] as const) {
    test(`a session id ${why} means no focus, and nothing is read or written`, async ($, on) => {
      const s = stage(on, { session: { id } })
      await start($)
      await s.clock.advance(TICK)
      expect(await project($)).toBe('No project in focus.')
      expect(await project($, 'acme')).toContain("couldn't be saved")
      expect(await project($, 'off')).toContain("couldn't be saved")
      expect((await composed($)).map(x => x.id)).toEqual(['intro'])
      expect(s.reads).toEqual([])
      expect(s.writes).toEqual([])
      expect(readsOf(s.ran, 'acme')).toBe(0)
    })
  }
  test('a bad name gets its own reason even with a bad id', async ($, on) => {
    stage(on, { session: { id: null } })
    await start($)
    expect(await project($, 'nope')).toContain("can't go in focus")
  })
  test('the file\'s text, trimmed, is the focus when it names a real folder', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await start($)
    for (const [text, want] of [['acme\n', 'acme'], ['  beta  \n', 'beta'], ['projects/acme', 'acme']] as const) {
      s.files.set(fileOf(A), text)
      expect(await project($)).toBe(`In focus: projects/${want}.`)
    }
  })
  test('anything else is no focus', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await start($)
    expect(await project($)).toBe('No project in focus.')
    for (const text of ['', '  \n', '../secrets', 'a/b', 'README.md', 'linked', 'nope']) {
      s.files.set(fileOf(A), text)
      expect(await project($)).toBe('No project in focus.')
      expect((await composed($)).map(x => x.id)).toEqual(['intro'])
    }
  })
})

describe('the line with a project in focus', () => {
  test('counts: the project\'s repo, its name first', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    s.files.set(fileOf(A), 'acme\n')
    await start($)
    await s.clock.settle()
    expect(await drawn($)).toContain(ACME)
  })
  test('reading, then unavailable', async ($, on) => {
    const gh: NonNullable<Options['gh']> = { isDown: true }
    let release = () => {}
    gh.hold = new Promise<void>(resolve => { release = resolve })
    const s = stage(on, { session: { id: A }, gh })
    s.files.set(fileOf(A), 'acme\n')
    await start($)
    expect(await drawn($)).toContain('acme: acme/app · reading…')
    gh.hold = null
    release()
    await s.clock.settle()
    expect(await drawn($)).toContain('acme: acme/app · GitHub unavailable')
  })
  test('stale: a later read that fails keeps the project\'s counts', async ($, on) => {
    const gh: NonNullable<Options['gh']> = {}
    const s = stage(on, { session: { id: A }, gh })
    await start($)
    await project($, 'acme')
    gh.isDown = true
    await s.clock.advance(LIMIT)
    expect(await drawn($)).toContain(`${ACME} · as of`)
  })
  test('a folder with no GitHub origin says so, and gh isn\'t called for it', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await start($)
    await s.clock.settle()
    const before = ghCalls(s.ran).length
    expect(await project($, 'notes')).toBe('notes: no GitHub remote')
    expect(await drawn($)).toContain('notes: no GitHub remote')
    await s.clock.advance(LIMIT + TICK)
    expect(await drawn($)).toContain('notes: no GitHub remote')
    expect(ghCalls(s.ran).length).toBe(before)
  })
  test('a read for a focus that has gone by when it finishes writes nothing to the line', async ($, on) => {
    const gh: NonNullable<Options['gh']> = {}
    let release = () => {}
    gh.hold = new Promise<void>(resolve => { release = resolve })
    const s = stage(on, { session: { id: A }, gh })
    s.files.set(fileOf(A), 'acme\n')
    await start($)
    await s.clock.settle()
    expect(readsOf(s.ran, 'acme')).toBe(1)
    // The focus moves on while acme's read is held open, and beta's read isn't.
    gh.hold = null
    s.files.set(fileOf(A), 'beta\n')
    await s.clock.advance(TICK)
    expect(await drawn($)).toContain(BETA)
    release()
    await s.clock.settle()
    const line = await drawn($)
    expect(line).toContain(BETA)
    expect(line).not.toContain('acme')
  })
  test('with no focus it\'s the factory\'s, with no prefix', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await start($)
    await s.clock.settle()
    const line = await drawn($)
    expect(line).toContain(HARNESS)
    expect(line).not.toContain(': SanvioLabs')
  })
  test('a reload with a focus never shows the factory', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    s.files.set(fileOf(A), 'acme\n')
    await start($)
    await s.clock.settle()
    await start($)
    expect(await drawn($)).toContain(ACME)
    await s.clock.settle()
    expect(readsOf(s.ran, 'SanvioLabs')).toBe(0)
  })
})

describe('the tick', () => {
  test('runs with no remote on the factory, and reads the file each time', async ($, on) => {
    const s = stage(on, { session: { id: A }, noRemote: true })
    await start($)
    await s.clock.settle()
    expect(ghCalls(s.ran)).toEqual([])
    s.files.set(fileOf(A), 'acme\n')
    await s.clock.advance(TICK)
    expect(readsOf(s.ran, 'acme')).toBe(1)
    expect(await drawn($)).toContain(ACME)
  })
  test('a focus that changed reads straight away, inside the limit', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    s.files.set(fileOf(A), 'acme\n')
    await start($)
    await s.clock.settle()
    expect(readsOf(s.ran, 'acme')).toBe(1)
    s.files.set(fileOf(A), 'beta\n')
    await s.clock.advance(TICK)
    expect(readsOf(s.ran, 'beta')).toBe(1)
    expect(await drawn($)).toContain(BETA)
  })
  test('a focus going away reads the factory straight away', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    s.files.set(fileOf(A), 'acme\n')
    await start($)
    await s.clock.settle()
    s.files.set(fileOf(A), '')
    await s.clock.advance(TICK)
    expect(readsOf(s.ran, 'SanvioLabs')).toBe(1)
    expect(await drawn($)).toContain(HARNESS)
  })
  test('inside two minutes of a read of the same repo calls no gh, and at two minutes reads once', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    s.files.set(fileOf(A), 'acme\n')
    await start($)
    await s.clock.settle()
    for (let i = 0; i < 7; i++) await s.clock.advance(TICK)
    expect(readsOf(s.ran, 'acme')).toBe(1)
    await s.clock.advance(TICK)
    expect(readsOf(s.ran, 'acme')).toBe(2)
  })
  test('a focused folder\'s origin is looked up when a read is due, not each tick', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await start($)
    await project($, 'acme')
    const gitsIn = () => s.ran.filter(a => a[0] === 'git' && a[2] === `${ROOT}/projects/acme`).length
    const before = gitsIn()
    await s.clock.advance(TICK)
    await s.clock.advance(TICK)
    expect(gitsIn()).toBe(before)
  })
  test('a focused folder with no GitHub origin counts for the limit, so its origin is looked up once in two minutes', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await start($)
    await s.clock.settle()
    const lookups = () => s.exists.filter(path => path === `${ROOT}/projects/notes/.git`).length
    s.files.set(fileOf(A), 'notes\n')
    await s.clock.advance(TICK)
    expect(lookups()).toBe(1)
    for (let i = 0; i < 7; i++) await s.clock.advance(TICK)
    expect(lookups()).toBe(1)
    await s.clock.advance(TICK)
    expect(lookups()).toBe(2)
  })
  test('a factory with no remote and no focus never calls gh', async ($, on) => {
    const s = stage(on, { session: { id: A }, noRemote: true })
    await start($)
    for (let i = 0; i < 10; i++) await s.clock.advance(TICK)
    expect(ghCalls(s.ran)).toEqual([])
    expect(await drawn($)).toContain('no GitHub remote')
  })
  test('each session.start cancels the timer before it, so a reload leaves one', async ($, on) => {
    const s = stage(on, { session: { id: A }, noRemote: true })
    await start($)
    await start($)
    await start($)
    await s.clock.settle()
    const before = readsOfFile(s.reads, fileOf(A))
    await s.clock.advance(TICK)
    expect(readsOfFile(s.reads, fileOf(A))).toBe(before + 1)
  })
  test('/project with a timer running starts no second one', async ($, on) => {
    const s = stage(on, { session: { id: A }, noRemote: true })
    await start($)
    await project($)
    await s.clock.settle()
    const before = readsOfFile(s.reads, fileOf(A))
    await s.clock.advance(TICK)
    expect(readsOfFile(s.reads, fileOf(A))).toBe(before + 1)
  })
  test('a read already under way for the focus doesn\'t start a second', async ($, on) => {
    const held = gate()
    const gh: NonNullable<Options['gh']> = { hold: held.hold }
    const s = stage(on, { session: { id: A }, gh })
    s.files.set(fileOf(A), 'acme\n')
    await start($)
    await s.clock.settle()
    expect(await gitHub($)).toBe('acme: acme/app · reading…')
    expect(readsOf(s.ran, 'acme')).toBe(1)
    gh.hold = null
    held.open()
    await s.clock.settle()
    expect(await drawn($)).toContain(ACME)
  })
  test('an old focus\'s read that ends leaves the new focus\'s read marked as under way', async ($, on) => {
    const first = gate()
    const second = gate()
    const gh: NonNullable<Options['gh']> = { hold: first.hold }
    const s = stage(on, { session: { id: A }, gh })
    s.files.set(fileOf(A), 'acme\n')
    await start($)
    await s.clock.settle()
    gh.hold = second.hold
    s.files.set(fileOf(A), 'beta\n')
    await s.clock.advance(TICK)
    expect(readsOf(s.ran, 'beta')).toBe(1)
    first.open()
    await s.clock.settle()
    await gitHub($)
    expect(readsOf(s.ran, 'beta')).toBe(1)
    expect(await drawn($)).toContain('beta: beta/site · reading…')
    gh.hold = null
    second.open()
    await s.clock.settle()
    expect(await drawn($)).toContain(BETA)
  })
  test('a reload forgets a read that was under way, so the next one due can start', async ($, on) => {
    const held = gate()
    const gh: NonNullable<Options['gh']> = { hold: held.hold }
    const s = stage(on, { session: { id: A }, gh })
    await start($)
    await s.clock.settle()
    expect(readsOf(s.ran, 'SanvioLabs')).toBe(1)
    await start($)
    await s.clock.advance(LIMIT)
    expect(readsOf(s.ran, 'SanvioLabs')).toBe(2)
    gh.hold = null
    held.open()
    await s.clock.settle()
  })
  test('a focus that moves while its origin is looked up starts no read for the old one', async ($, on) => {
    const options: Options = { session: { id: A } }
    const s = stage(on, options)
    s.files.set(fileOf(A), 'acme\n')
    await start($)
    await s.clock.settle()
    options.onGit = argv => {
      if (argv[2] === `${ROOT}/projects/acme`) s.files.set(fileOf(A), 'beta\n')
    }
    await gitHub($)
    expect(readsOf(s.ran, 'acme')).toBe(1)
    expect(readsOf(s.ran, 'beta')).toBe(0)
    options.onGit = undefined
    await s.clock.advance(TICK)
    expect(readsOf(s.ran, 'beta')).toBe(1)
    expect(await drawn($)).toContain(BETA)
  })
  test('a prompt.compose call doesn\'t stop the next tick seeing a change', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    s.files.set(fileOf(A), 'acme\n')
    await start($)
    await s.clock.settle()
    s.files.set(fileOf(A), 'beta\n')
    await composed($)
    await s.clock.advance(TICK)
    expect(readsOf(s.ran, 'beta')).toBe(1)
  })
})

describe('/github with a project in focus', () => {
  test('no argument reads the repo in focus', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    s.files.set(fileOf(A), 'acme\n')
    await start($)
    await s.clock.settle()
    expect(await gitHub($)).toBe(ACME)
    expect(readsOf(s.ran, 'acme')).toBe(2)
  })
  test('no argument reads it when the factory has no remote too', async ($, on) => {
    const s = stage(on, { session: { id: A }, noRemote: true })
    s.files.set(fileOf(A), 'acme\n')
    await start($)
    await s.clock.settle()
    expect(await gitHub($)).toBe(ACME)
  })
  test('no argument, a factory with no remote and no focus, says so', async ($, on) => {
    const s = stage(on, { session: { id: A }, noRemote: true })
    await start($)
    expect(await gitHub($)).toBe("This session's folder has no GitHub origin remote, so there's nothing to read.")
    expect(ghCalls(s.ran)).toEqual([])
  })
  test('/github <name> prints what it does now and leaves the line and the focus alone', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    s.files.set(fileOf(A), 'beta\n')
    await start($)
    await s.clock.settle()
    expect(await gitHub($, 'acme')).toBe(ACME)
    expect(await drawn($)).toContain(BETA)
    expect(await project($)).toBe('In focus: projects/beta.')
    expect(s.writes).toEqual([])
    // Had the focus been touched, this tick would read beta again.
    await s.clock.advance(TICK)
    expect(readsOf(s.ran, 'beta')).toBe(1)
  })
  test('/github all keeps the factory\'s own repo on factory:', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    s.files.set(fileOf(A), 'beta\n')
    await start($)
    await s.clock.settle()
    expect(await gitHub($, 'all')).toBe([`factory: ${HARNESS}`, ACME, BETA, '1 folder under projects/ has no GitHub remote.'].join('\n'))
  })
})

describe('the section', () => {
  test('one section while a project is in focus, last, on the session\'s side', async ($, on) => {
    const s = stage(on, { session: { id: A } })
    await start($)
    expect((await composed($)).map(x => x.id)).toEqual(['intro'])
    s.files.set(fileOf(A), 'acme\n')
    expect(await composed($)).toEqual([
      { id: 'intro', text: 'The engine\'s own.', scope: 'shared' },
      {
        id: 'github-status:project',
        scope: 'session',
        text: 'The person has put projects/acme in focus. When they ask about the project, its pull requests, its issues or its loop without naming one, they mean projects/acme.',
      },
    ])
  })
})
