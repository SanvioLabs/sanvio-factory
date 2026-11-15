import { describe as group, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import { changes, loopOptions } from './logic'
import { REMOTE_WATCH_TOAST } from './buttons'
import { SSH_OPTIONS, WATCH_SSH_OPTIONS, catCommand, hasSessionCommand, killCommand, lsCommand, parseMachines, q, remoteAttach, remoteNames, remoteWatchLine, scrubbed, sshArgv } from './remote'
import type { Machine } from './remote'

// Other machines' loops, read over ssh. No test here opens a connection: every process.run is answered
// by a stand-in that reads a made-up machine's files from a map.

// How a POSIX shell splits a command into words, for what this mod sends: single quotes, a backslash
// outside them, and spaces between words. Anything the shell would treat as an operator outside quotes
// throws, so a value that escaped its quotes fails the test rather than passing as a stray word.
function words(command: string): string[] {
  const out: string[] = []
  let word = ''
  let isInWord = false
  for (let i = 0; i < command.length; ) {
    const c = command[i]!
    if (c === "'") {
      const end = command.indexOf("'", i + 1)
      if (end < 0) throw new Error(`an unclosed quote in ${command}`)
      word += command.slice(i + 1, end)
      isInWord = true
      i = end + 1
    } else if (c === '"') {
      // Inside double quotes a shell still reads $, `, \ and !, so one of them here fails the test.
      const end = command.indexOf('"', i + 1)
      if (end < 0) throw new Error(`an unclosed double quote in ${command}`)
      const inside = command.slice(i + 1, end)
      if (/[$`\\!]/.test(inside)) throw new Error(`a shell would read ${inside} inside double quotes`)
      word += inside
      isInWord = true
      i = end + 1
    } else if (c === '\\') {
      word += command[i + 1] ?? ''
      isInWord = true
      i += 2
    } else if (c === ' ' || c === '\t' || c === '\n') {
      if (isInWord) out.push(word)
      word = ''
      isInWord = false
      i++
    } else if (/[;&|<>()$`*?[\]{}~#!]/.test(c)) {
      throw new Error(`an unquoted ${c} in ${command}`)
    } else {
      word += c
      isInWord = true
      i++
    }
  }
  if (isInWord) out.push(word)
  return out
}

group('machines.json', () => {
  test('a machine with a label, an ssh and an absolute path is read, its trailing / dropped', () => {
    const text = JSON.stringify({ machines: [{ label: 'spare-mac', ssh: 'builder@spare-mac.local', path: '/Users/builder/factory/' }] })
    expect(parseMachines(text)).toEqual({
      machines: [{ index: 0, label: 'spare-mac', ssh: 'builder@spare-mac.local', path: '/Users/builder/factory' }],
      refusals: [],
    })
  })
  test('no file is no machines and nothing to say', () => {
    expect(parseMachines(null)).toEqual({ machines: [], refusals: [] })
  })
  test('a destination starting with - and a path that is not absolute are each skipped with a line, and the rest read', () => {
    const text = JSON.stringify({
      machines: [
        { label: 'evil', ssh: '-oProxyCommand=x', path: '/f' },
        { label: 'tilde', ssh: 'u@tilde', path: '~/factory' },
        { label: 'good', ssh: 'u@good', path: '/g' },
        { label: 'half' },
        { label: 'spaced', ssh: 'u@h %h', path: '/f' },
        { label: 'quoted', ssh: 'u@q', path: "/f'x" },
        { label: 'slashed', ssh: 'u@s', path: '/f\\x' },
      ],
    })
    expect(parseMachines(text)).toEqual({
      machines: [{ index: 2, label: 'good', ssh: 'u@good', path: '/g' }],
      refusals: [
        'machines.json: "-oProxyCommand=x" starts with "-", so evil isn\'t read',
        'machines.json: tilde\'s path "~/factory" isn\'t absolute, so it isn\'t read',
        "machines.json: machine 4 needs a label, an ssh and a path, so it isn't read",
        'machines.json: spaced\'s ssh "u@h %h" holds a character a host name can\'t, so it isn\'t read',
        'machines.json: quoted\'s path "/f\'x" holds a \' or a \\, so it isn\'t read',
        'machines.json: slashed\'s path "/f\\x" holds a \' or a \\, so it isn\'t read',
      ],
    })
  })
  test('a file that is not the shape reads nothing and says so', () => {
    for (const text of ['not json', '[]', '{"machines": {}}']) {
      expect(parseMachines(text).machines).toEqual([])
      expect(parseMachines(text).refusals.length).toBe(1)
    }
  })
})

group('the commands', () => {
  test('ssh never prompts, gives up connecting in 5 seconds, and reads the destination after --', () => {
    expect(sshArgv('u@h', "ls -1A '/f/.loop'")).toEqual(['ssh', ...SSH_OPTIONS, '--', 'u@h', "ls -1A '/f/.loop'"])
    const options = SSH_OPTIONS.join(' ')
    for (const set of ['-n', '-T', 'BatchMode=yes', 'ConnectTimeout=5', 'StrictHostKeyChecking=yes', 'ForwardAgent=no',
      'ForwardX11=no', 'ClearAllForwardings=yes', 'PermitLocalCommand=no', 'ServerAliveInterval=3', 'ServerAliveCountMax=2']) {
      expect(options).toContain(set)
    }
  })
  test('a path and a project with spaces, quotes and ; are one word each', () => {
    const path = "/a b/it's;x"
    const project = "p q;'r"
    expect(words(lsCommand(`${path}/.loop/projects/${project}`))).toEqual(['ls', '-1A', `${path}/.loop/projects/${project}`])
    expect(words(catCommand(`${path}/.loop/status.json`))).toEqual(['cat', `${path}/.loop/status.json`])
    expect(words(q("'"))).toEqual(["'"])
    expect(words(killCommand(4242))).toEqual(['kill', '-0', '4242'])
  })
  test('a listing drops . and .., and any name with a /', () => {
    expect(remoteNames('beta\n.\n..\nalpha\na/b\n\n')).toEqual(['alpha', 'beta'])
  })
  test("a listing keeps only names a project here could have, so none can step out of fish's quotes either", () => {
    expect(remoteNames("a\\';id;#\nok\np q\nx'y\n\u001b]52;c;x\u0007\n-dash\nv1.2_x-y\na..b")).toEqual(['ok', 'v1.2_x-y'])
  })
  test("a remote file's strings lose their control characters, and what isn't JSON reads as nothing", () => {
    expect(scrubbed(JSON.stringify({ issues: [{ title: 'a\u001b]52;c;eA==\u0007b\u009bc', number: 1 }] }))).toBe(
      JSON.stringify({ issues: [{ title: 'a]52;c;eA==bc', number: 1 }] }))
    expect(scrubbed('not json')).toBeNull()
    expect(scrubbed(null)).toBeNull()
  })
})

group('the picker and the notices', () => {
  test("a machine that's down is an option of its own, after the loops, and names no loop", () => {
    const options = loopOptions([], [{ index: 1, label: 'shelf-board', lastReadAt: null }, { index: 2, label: 'spare-mac', lastReadAt: 0 }], 125_000)
    expect(options).toEqual([
      { value: 'ssh:1', label: 'shelf-board · down, never read' },
      { value: 'ssh:2', label: 'spare-mac · down, last read 2m 05s ago' },
    ])
  })
  test("another machine's notice starts with its label", () => {
    const row = { number: 14, title: 'Gate', step: 'SCALE', state: 'working', round: 1, tests: null, review: null, pr: null, note: '' }
    const status = (state: string) => ({ running: true, updated: null, tmux: null, queue: [], issues: [{ ...row, state }] })
    expect(changes(status('working'), status('pr'), 'app', 'spare-mac')).toEqual(['spare-mac · app: #14 has a pull request'])
    expect(changes(status('working'), status('blocked'), undefined, 'spare-mac')).toEqual(['spare-mac: #14 is blocked'])
  })
})

// The pane, end to end, with this machine's factory at ROOT and other machines answering from `remotes`.
const ROOT = '/h/starter'
const MACHINES = `${ROOT}/.sanvio/factory-floor/machines.json`
const statusText = (title: string, extra: object = {}) => JSON.stringify({ running: false, tmux: null, queue: [{ number: 30, title }], issues: [], ...extra })

// A made-up machine: its files by path, the processes alive on it, and whether its ssh never answers.
// sessions are its tmux sessions, for Watch's has-session; tmuxDown makes that one ssh fail to connect.
type Remote = { files: Map<string, string>; pids?: number[]; hangs?: boolean; sessions?: string[]; tmuxDown?: boolean }
type Call = { argv: string[]; init: Record<string, unknown> | undefined }

// The names directly in a remote folder, or null when no file is under it.
function children(files: Map<string, string>, dir: string): string[] | null {
  const prefix = `${dir}/`
  const names = [...files.keys()].filter(p => p.startsWith(prefix)).map(p => p.slice(prefix.length).split('/')[0]!)
  return names.length ? [...new Set(names)] : null
}

function world(on: On, files: Map<string, string>, remotes: Record<string, Remote>) {
  const clock = mock.clock(on, { now: 1_800_000_000_000 })
  const calls: Call[] = []
  const panes: { id: string; isShown: boolean; isPlaced: boolean }[] = []
  const done = (exitCode: number, stdout = '', stderr = '') => ({ value: { exitCode, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false } })
  on('session.root', async () => ({ value: ROOT }))
  on('session.id', async () => ({ deny: 'no session id' }))
  on('fs.exists', async (_$, e) => ({ value: e.path === `${ROOT}/scripts/loop.py` || files.has(e.path) }))
  on('fs.read', async (_$, e) => {
    const text = files.get(e.path)
    return text === undefined ? { deny: `no ${e.path}` } : { value: text }
  })
  on('fs.list', async (_$, e) => ({ deny: `no ${e.path}` }))
  on('fs.stat', async (_$, e) => ({ deny: `no ${e.path}` }))
  on('process.run', async (_$, e) => {
    const argv = [...e.argv]
    if (argv[0] !== 'ssh') return done(0)
    calls.push({ argv, init: e.init as unknown as Record<string, unknown> | undefined })
    const machine = remotes[argv[argv.indexOf('--') + 1] ?? '']
    if (!machine) return done(255, '', 'ssh: Could not resolve hostname')
    if (machine.hangs) return new Promise<never>(() => {})
    const [verb, ...args] = words(argv[argv.length - 1] ?? '')
    if (verb === 'ls') {
      const names = children(machine.files, args[1] ?? '')
      return names ? done(0, names.map(n => `${n}\n`).join('')) : done(2, '', 'ls: No such file or directory')
    }
    if (verb === 'cat') {
      const text = machine.files.get(args[0] ?? '')
      return text === undefined ? done(1, '', 'cat: No such file or directory') : done(0, text)
    }
    if (verb === 'kill') return (machine.pids ?? []).includes(Number(args[1])) ? done(0) : done(1, '', `kill: (${args[1]}) - No such process`)
    if (verb === 'tmux') {
      if (machine.tmuxDown) return done(255, '', 'ssh: connect to host: Connection refused')
      const at = args.indexOf('has-session')
      const session = (args[args.indexOf('-t', at) + 1] ?? '').replace(/^=/, '')
      return at >= 0 && (machine.sessions ?? []).includes(session) ? done(0) : done(1, '', `can't find session: ${session}`)
    }
    return done(127, '', `${verb}: not found`)
  })
  on('ui.open', async () => {
    panes.length = 0
    panes.push({ id: 'factory-floor', isShown: true, isPlaced: true })
    return { value: { isPlaced: true } }
  })
  on('ui.close', async () => {
    panes.length = 0
    return { value: undefined }
  })
  on('ui.panes', async () => ({ value: [...panes] }) as never)
  const toasts: string[] = []
  const copied: string[] = []
  on('ui.toast', async (_$, e) => {
    toasts.push((e as unknown as { text: string }).text)
    return { value: undefined }
  })
  on('ui.copy', async (_$, e) => {
    copied.push(e.text)
    return { value: { isCopied: true } }
  })
  // Closes the pane, so the poll stops itself and the next test can start its own.
  const close = async () => {
    panes.length = 0
    await clock.advance(500)
    await drain()
  }
  return { clock, calls, panes, close, toasts, copied }
}

async function drain(): Promise<void> {
  for (let i = 0; i < 200; i++) await Promise.resolve()
}

const PANE = {
  plugin: 'factory-floor',
  surface: 'terminal',
  component: 'Pane',
  requestId: 'factory-floor',
  // Wide enough that a refusal line is drawn whole.
  props: { title: 'Loop', isFocused: true, bodyColumns: 160, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

type Dollar = { command: { run: (i: object) => Promise<unknown> } }
const typed = { command: 'factory-floor', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } }
const open = async ($: unknown) => {
  await ($ as Dollar).command.run(typed)
}
type Found = { props: Record<string, unknown> }
type Finds = { find: (q: { key: string }) => Promise<Found | undefined>; findAll: (q: { type: string; text: RegExp }) => Promise<{ text: string }[]> }
const options = async (ui: unknown): Promise<{ value: string; label: string }[]> =>
  ((await (ui as Finds).find({ key: 'loop-pick' }))?.props.options as { value: string; label: string }[] | undefined) ?? []
const labels = async (ui: unknown): Promise<string[]> => (await options(ui)).map(o => o.label)

// The List's first read starts the other machines' reads, in the background; its next shows them.
async function pastFirstRead(clock: { advance: (ms: number) => Promise<unknown> }): Promise<void> {
  await clock.advance(500)
  await drain()
  await clock.advance(2000)
  await drain()
}

// A machine whose factory has run, with a project, under `path`. Its loop is live and working #12, so
// the read also cats that issue's usage.json.
function factoryAt(path: string, project: string): Remote {
  const job = { number: 12, title: 'Gate', step: 'BUILD', state: 'working', round: 1, tests: null, review: null, pr: null, note: '', started: '2026-11-03T09:00:00', tokens: 10 }
  return {
    files: new Map([
      [`${path}/.loop/status.json`, statusText('far job', { issues: [job] })],
      [`${path}/.loop/lock`, '77\n'],
      [`${path}/.loop/issue-12/usage.json`, '[]'],
      [`${path}/.loop/projects/${project}/status.json`, statusText('far project job')],
      [`${path}/.loop/projects/not-a-loop/notes`, 'no status file'],
    ]),
    pids: [77],
  }
}

group('reading other machines', () => {
  test('with no machines.json the pane runs no ssh at all', async ($, on) => {
    const files = new Map([[`${ROOT}/.loop/status.json`, statusText('here')]])
    const { clock, calls, close } = world(on, files, { 'u@far': factoryAt('/far', 'app') })
    await open($)
    const ui = await $.ui.mount(PANE)
    await pastFirstRead(clock)
    await clock.advance(60_000)
    await drain()
    expect(calls).toEqual([])
    expect(await ui.find({ key: 'loop-pick' })).toBeUndefined()
    await ui.unmount()
    await close()
  })
  test('every ssh never prompts, times out under the poll, and runs only ls, cat and kill -0, with each value one word', async ($, on) => {
    const path = '/a b/x;y'
    const project = 'p.q-r'
    const files = new Map([
      [`${ROOT}/.loop/status.json`, statusText('here')],
      [MACHINES, JSON.stringify({ machines: [{ label: 'far', ssh: 'u@far', path }] })],
    ])
    const { clock, calls, close } = world(on, files, { 'u@far': factoryAt(path, project) })
    await open($)
    const ui = await $.ui.mount(PANE)
    await pastFirstRead(clock)
    // The odd path and project were each read as one word, so their loops are listed.
    expect(await labels(ui)).toEqual(['All loops', '● far', 'starter', `far · ${project}`])
    expect(calls.length).toBeGreaterThan(0)
    // Watch's has-session is the one command more, and only a press sends it: a poll never does.
    const allowed = [/^ls -1A '.*\/\.loop(\/.*)?'$/s, /^cat '.*\/\.loop\/.*'$/s, /^kill -0 \d+$/, /^tmux( -S '[^']*')? has-session -t '=[^']*'$/]
    for (const { argv, init } of calls) {
      const end = argv.indexOf('--')
      expect(argv.slice(0, end)).toEqual(['ssh', ...SSH_OPTIONS])
      expect(argv[end + 1]).toBe('u@far')
      expect(argv.length).toBe(end + 3)
      expect(Number(init?.timeoutMs)).toBeLessThan(30_000)
      const command = argv[end + 2]!
      expect(allowed.some(pattern => pattern.test(command))).toBe(true)
      const split = words(command)
      expect(split.length).toBe(command.startsWith('cat ') ? 2 : 3)
      if (!command.startsWith('kill ')) expect(split[split.length - 1]!.startsWith(`${path}/.loop`)).toBe(true)
    }
    const commands = calls.map(c => c.argv[c.argv.length - 1])
    expect(commands.filter(c => c?.includes('has-session'))).toEqual([])
    expect(commands).toContain(lsCommand(`${path}/.loop/projects/${project}`))
    expect(commands).toContain('kill -0 77')
    expect(commands).toContain(catCommand(`${path}/.loop/issue-12/usage.json`))
    await ui.unmount()
    await close()
  })
  test('a bad destination and a bad path each get a line under the picker and no ssh, and the other machine is still read', async ($, on) => {
    const files = new Map([
      [`${ROOT}/.loop/status.json`, statusText('here')],
      [MACHINES, JSON.stringify({ machines: [
        { label: 'evil', ssh: '-oProxyCommand=x', path: '/f' },
        { label: 'tilde', ssh: 'u@tilde', path: '~/factory' },
        { label: 'good', ssh: 'u@good', path: '/g' },
      ] })],
    ])
    const { clock, calls, close } = world(on, files, { 'u@good': factoryAt('/g', 'app'), 'u@tilde': factoryAt('/t', 'app') })
    await open($)
    const ui = await $.ui.mount(PANE)
    await pastFirstRead(clock)
    expect(calls.length).toBeGreaterThan(0)
    expect([...new Set(calls.map(c => c.argv[c.argv.indexOf('--') + 1]))]).toEqual(['u@good'])
    expect(calls.some(c => c.argv.some(word => word.includes('ProxyCommand')))).toBe(false)
    const lines = (await (ui as unknown as Finds).findAll({ type: 'Text', text: /^machines\.json/ })).map(t => t.text)
    expect(lines).toEqual([
      'machines.json: "-oProxyCommand=x" starts with "-", so evil isn\'t read',
      'machines.json: tilde\'s path "~/factory" isn\'t absolute, so it isn\'t read',
    ])
    expect(await labels(ui)).toContain('good · app')
    await ui.unmount()
    await close()
  })
  test("a machine that never answers holds up nothing, shows as down after 10 seconds, and the rest still show", async ($, on) => {
    const files = new Map([
      [`${ROOT}/.loop/status.json`, statusText('here')],
      [MACHINES, JSON.stringify({ machines: [
        { label: 'slow', ssh: 'u@slow', path: '/s' },
        { label: 'ok', ssh: 'u@ok', path: '/o' },
      ] })],
    ])
    const { clock, close } = world(on, files, { 'u@slow': { files: new Map(), hangs: true }, 'u@ok': factoryAt('/o', 'app') })
    await open($)
    const ui = await $.ui.mount(PANE)
    // The first look shows this machine's loop, with nothing waiting on ssh.
    expect(await ui.find({ key: 'tab-queue' })).toBeDefined()
    await pastFirstRead(clock)
    expect(await labels(ui)).toEqual(['All loops', '● ok', 'starter', 'ok · app'])
    await clock.advance(10_000)
    await drain()
    await clock.advance(2000)
    await drain()
    expect(await labels(ui)).toEqual(['All loops', '● ok', 'starter', 'ok · app', 'slow · down, never read'])
    // Picking the machine that's down does nothing.
    await (ui as unknown as { select: (t: { key: string; value: string }) => Promise<unknown> }).select({ key: 'loop-pick', value: 'ssh:0' })
    await drain()
    expect((await (ui as unknown as Finds).find({ key: 'loop-pick' }))?.props.value).toBe('')
    await ui.unmount()
    await close()
  })
  test('a machine is read again only once 30 seconds have passed, and not at all once the pane closes', async ($, on) => {
    const files = new Map([
      [`${ROOT}/.loop/status.json`, statusText('here')],
      [MACHINES, JSON.stringify({ machines: [{ label: 'ok', ssh: 'u@ok', path: '/o' }] })],
    ])
    const { clock, calls, panes, close } = world(on, files, { 'u@ok': factoryAt('/o', 'app') })
    const firsts = () => calls.filter(c => c.argv[c.argv.length - 1] === lsCommand('/o/.loop')).length
    await open($)
    const ui = await $.ui.mount(PANE)
    // The first read is at the poll's first tick, half a second in.
    await clock.advance(500)
    await drain()
    expect(firsts()).toBe(1)
    // 28 seconds after it: the reads every two seconds start none.
    for (let i = 0; i < 14; i++) {
      await clock.advance(2000)
      await drain()
    }
    expect(firsts()).toBe(1)
    // 30 seconds after it.
    await clock.advance(2000)
    await drain()
    expect(firsts()).toBe(2)
    await ui.unmount()
    panes.length = 0
    const started = firsts()
    for (let i = 0; i < 40; i++) {
      await clock.advance(2000)
      await drain()
    }
    expect(firsts()).toBe(started)
    await close()
  })
})

group("Watch on another machine's issue", () => {
  const far: Machine = { index: 0, label: 'far', ssh: 'u@far', path: '/f' }

  test('tmux_socket is kept when it is an absolute path of plain characters, and otherwise only Watch is held back', () => {
    const text = JSON.stringify({ machines: [
      { label: 'sock', ssh: 'u@a', path: '/a', tmux_socket: '/tmp/tmux-501/loop sock' },
      { label: 'rel', ssh: 'u@b', path: '/b', tmux_socket: 'tmux-501/default' },
      { label: 'quote', ssh: 'u@c', path: '/c', tmux_socket: "/tmp/it's" },
      { label: 'dollar', ssh: 'u@d', path: '/d', tmux_socket: '/tmp/$(id)' },
      { label: 'bell', ssh: 'u@f', path: '/f', tmux_socket: '/tmp/a\u0007b' },
      { label: 'plain', ssh: 'u@e', path: '/e' },
    ] })
    const { machines, refusals } = parseMachines(text)
    expect(machines.map(m => [m.label, m.socket ?? null, m.canWatch ?? true])).toEqual([
      ['sock', '/tmp/tmux-501/loop sock', true],
      ['rel', null, false],
      ['quote', null, false],
      ['dollar', null, false],
      ['bell', null, false],
      ['plain', null, true],
    ])
    expect(refusals).toEqual(['rel', 'quote', 'dollar', 'bell'].map(l => `machines.json: ${l}'s tmux_socket isn't an absolute path of plain characters, so its issues get no Watch`))
  })

  test("the copied command has a terminal and forwards nothing, unlike the background reads", () => {
    expect(WATCH_SSH_OPTIONS).toContain('-t')
    expect(WATCH_SSH_OPTIONS).not.toContain('-n')
    expect(WATCH_SSH_OPTIONS).not.toContain('-T')
    const options = WATCH_SSH_OPTIONS.join(' ')
    for (const set of ['BatchMode=yes', 'ConnectTimeout=5', 'StrictHostKeyChecking=yes', 'ForwardAgent=no', 'ForwardX11=no', 'ClearAllForwardings=yes', 'PermitLocalCommand=no']) {
      expect(options).toContain(set)
    }
  })

  test("each name arrives whole through this machine's shell and then the remote one", () => {
    const sock = { ...far, socket: '/tmp/tmux 501/loop sock' }
    const line = remoteWatchLine(sock, 'loop-my factory', 'issue-12')!
    const local = words(line)
    expect(local).toEqual(['ssh', ...WATCH_SSH_OPTIONS, '--', 'u@far', remoteAttach(sock, 'loop-my factory', 'issue-12')])
    expect(words(local[local.length - 1]!)).toEqual(['tmux', '-S', '/tmp/tmux 501/loop sock', 'attach', '-r', '-t', '=loop-my factory:=issue-12'])
    expect(words(remoteWatchLine(far, 'loop-a', 'issue-3')!).pop()).toBe("tmux attach -r -t '=loop-a:=issue-3'")
    // The destination is quoted too, so a bracketed host isn't globbed by the shell it's pasted into.
    expect(remoteWatchLine({ ...far, ssh: 'u@[fe80::1]' }, 'loop-a', 'issue-3')).toContain(" -- 'u@[fe80::1]' ")
    expect(words(hasSessionCommand(sock, 'loop-my factory'))).toEqual(['tmux', '-S', '/tmp/tmux 501/loop sock', 'has-session', '-t', '=loop-my factory'])
  })

  test('a session or window name a shell could read builds no command at all', () => {
    for (const bad of ['$(id)', '`id`', 'a;b', "a'b", 'a"b', 'a\\b', 'a!b', 'a:b', 'a\nb', 'a\u001bb', '']) {
      expect(remoteAttach(far, bad, 'issue-1')).toBeNull()
      expect(remoteAttach(far, 'loop-a', bad)).toBeNull()
      expect(remoteWatchLine(far, bad, 'issue-1')).toBeNull()
      expect(remoteWatchLine(far, 'loop-a', bad)).toBeNull()
    }
  })

  // A machine whose factory loop is live in tmux session `session`, working #12 in window issue-12.
  function watchable(session: string, extra: Partial<Remote> = {}): Remote {
    const job = { number: 12, title: 'Gate', step: 'BUILD', state: 'working', round: 1, tests: null, review: null, pr: null, note: '', window: 'issue-12' }
    return {
      files: new Map([
        ['/f/.loop/status.json', statusText('far job', { running: true, tmux: session, issues: [job] })],
        ['/f/.loop/lock', '77\n'],
      ]),
      pids: [77],
      sessions: [session],
      ...extra,
    }
  }
  const machinesFile = (extra: object = {}) => JSON.stringify({ machines: [{ label: 'far', ssh: 'u@far', path: '/f', ...extra }] })
  type Ui = { find: (q: { key: string }) => Promise<unknown>; press: (q: { key: string }) => Promise<unknown>; select: (q: { key: string; value: string }) => Promise<unknown>; unmount: () => Promise<void> }
  async function onFar($: unknown, clock: { advance: (ms: number) => Promise<unknown> }): Promise<Ui> {
    await open($)
    const ui = (await ($ as { ui: { mount: (p: unknown) => Promise<unknown> } }).ui.mount(PANE)) as Ui
    await pastFirstRead(clock)
    await ui.select({ key: 'loop-pick', value: 'ssh:0/' })
    await drain()
    return ui
  }

  test('pressed, it checks the session over ssh, then copies the read-only attach and says so', async ($, on) => {
    const files = new Map([[`${ROOT}/.loop/status.json`, statusText('here')], [MACHINES, machinesFile({ tmux_socket: '/tmp/far sock' })]])
    const { clock, calls, close, toasts, copied } = world(on, files, { 'u@far': watchable('loop-far') })
    const ui = await onFar($, clock)
    expect(await ui.find({ key: 'watch-12' })).toBeDefined()
    expect(calls.some(c => c.argv[c.argv.length - 1]!.includes('has-session'))).toBe(false)
    await ui.press({ key: 'watch-12' })
    await drain()
    const machine: Machine = { index: 0, label: 'far', ssh: 'u@far', path: '/f', socket: '/tmp/far sock' }
    expect(calls.map(c => c.argv[c.argv.length - 1]).filter(c => c!.includes('has-session'))).toEqual([hasSessionCommand(machine, 'loop-far')])
    expect(copied).toEqual([remoteWatchLine(machine, 'loop-far', 'issue-12')])
    expect(toasts).toContain(REMOTE_WATCH_TOAST)
    await ui.unmount()
    await close()
  })

  test("a session that's gone, or a machine that doesn't answer the check, copies nothing and says which", async ($, on) => {
    const files = new Map([[`${ROOT}/.loop/status.json`, statusText('here')], [MACHINES, machinesFile()]])
    const remote = watchable('loop-far', { sessions: [] })
    const { clock, close, toasts, copied } = world(on, files, { 'u@far': remote })
    const ui = await onFar($, clock)
    await ui.press({ key: 'watch-12' })
    await drain()
    expect(copied).toEqual([])
    expect(toasts).toContain('far has no tmux session loop-far now, so nothing was copied')
    remote.tmuxDown = true
    await ui.press({ key: 'watch-12' })
    await drain()
    expect(copied).toEqual([])
    expect(toasts).toContain("far didn't answer, so nothing was copied")
    await ui.unmount()
    await close()
  })

  const noWatch: [string, () => Remote, object][] = [
    ['a loop that is not live', () => watchable('loop-far', { pids: [] }), {}],
    ['a loop not in tmux', () => watchable(''), {}],
    ['a session named past the allowlist', () => watchable('loop;id'), {}],
    ['a refused tmux_socket, though the machine stays listed', () => watchable('loop-far'), { tmux_socket: 'relative/sock' }],
  ]
  for (const [what, remote, extra] of noWatch) {
    test(`no Watch for ${what}`, async ($, on) => {
      const files = new Map([[`${ROOT}/.loop/status.json`, statusText('here')], [MACHINES, machinesFile(extra)]])
      const { clock, close } = world(on, files, { 'u@far': remote() })
      const ui = await onFar($, clock)
      expect((await options(ui)).map(o => o.value)).toContain('ssh:0/')
      expect(await ui.find({ key: 'watch-12' })).toBeUndefined()
      await ui.unmount()
      await close()
    })
  }
})
