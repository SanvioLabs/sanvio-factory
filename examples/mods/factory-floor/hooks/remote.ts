// Other machines' loops, read over SSH: the one place in this mod that builds or runs ssh. Both views
// take what it last read from here. Only their polls start a read, and a read runs in the background,
// so a machine that's slow or gone never holds up this machine's two-second read or a drawing.
//
// It only reads. Every remote command is one of four: ls -1A of a folder under the machine's .loop/,
// cat of a file under it, kill -0 on the process its lock names, and, only when a person presses Watch on
// one of its issues, tmux has-session on that issue's session. Watch itself runs nothing: it copies a
// read-only attach command for the person to paste. Each runs as its own ssh, with
// every value from machines.json or the machine single-quoted for the remote shell. Those values are
// held to characters that need no escaping inside single quotes, so the quoting holds in a login shell
// that isn't POSIX, such as fish, too. ls and cat follow a link, so a link the machine puts under .loop/
// can make them read a file elsewhere there. What they read only ever lands in this pane.
import type { EngineInterface } from 'claude-code'

import { PROJECTS_DIR, lockPid, loopDir, loopValue, parseStatus, projectName } from './logic'
import type { Down } from './logic'
import type { Row, Seen } from '../types'

// The list of other machines, under the harness root. Git ignores .sanvio/, so it stays on this machine.
export const MACHINES_FILE = '.sanvio/factory-floor/machines.json'
// A machine is read at most this often.
export const READ_EVERY_MS = 30_000
// One ssh is given up after this long, by the engine and by the clock both, and its machine counts as down.
export const READ_TIMEOUT_MS = 10_000
const CONNECT_TIMEOUT_S = 5

// One machine from machines.json: its place in the file's list, what the picker calls it, where ssh
// connects, and the factory's folder there.
// socket is its tmux_socket, for a loop whose tmux server isn't on the default socket. canWatch is false when
// tmux_socket was given and refused, so its issues get no Watch, though the machine is still read.
export type Machine = { index: number; label: string; ssh: string; path: string; socket?: string; canWatch?: boolean }

// Control characters, C1's among them: a remote machine's text could otherwise steer the terminal.
const CONTROL = /[\x00-\x1f\x7f-\x9f]/g
// A value worth reading: text with something in it and no control characters, a newline among them.
const isText = (v: unknown): v is string => typeof v === 'string' && v.trim() !== '' && !new RegExp(CONTROL.source).test(v)
// What an ssh destination may hold: a host name or address, a user before @ and a port after :. Nothing
// a shell, or ssh's own %-tokens in a ProxyCommand, would read as anything else.
const SSH_DEST = /^[A-Za-z0-9._@:[\]-]+$/
// What a tmux session or window name, and a tmux_socket after its leading /, may hold for Watch: characters
// no shell reads as anything inside quotes, single or double, POSIX or fish. loop.py names an issue's window
// issue-N, and loop-control names the session loop-<folder>. No : either, which would split session from
// window. A name with anything else gets no Watch.
const TMUX_NAME = /^[A-Za-z0-9_.@%+, -]+$/
const SOCKET = /^\/[A-Za-z0-9_.@%+,:\/ -]*$/

// The machines machines.json lists that can be read, and a line for each one it skips, saying why. No
// file is no machines and nothing to say.
export function parseMachines(text: string | null): { machines: Machine[]; refusals: string[] } {
  if (text === null) return { machines: [], refusals: [] }
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    raw = null
  }
  const list = raw && typeof raw === 'object' ? (raw as { machines?: unknown }).machines : undefined
  if (!Array.isArray(list)) return { machines: [], refusals: [`machines.json isn't { "machines": [...] }, so no other machine is read`] }
  const machines: Machine[] = []
  const refusals: string[] = []
  list.forEach((item: unknown, index: number) => {
    const fields = item && typeof item === 'object' ? (item as Record<string, unknown>) : {}
    const { label, ssh, path, tmux_socket: socket } = fields
    if (!isText(label) || !isText(ssh) || !isText(path)) {
      refusals.push(`machines.json: machine ${index + 1} needs a label, an ssh and a path, so it isn't read`)
    } else if (ssh.startsWith('-')) {
      // ssh would read it as an option, -oProxyCommand=… among them, not as where to connect.
      refusals.push(`machines.json: "${ssh}" starts with "-", so ${label} isn't read`)
    } else if (!SSH_DEST.test(ssh)) {
      refusals.push(`machines.json: ${label}'s ssh "${ssh}" holds a character a host name can't, so it isn't read`)
    } else if (!path.startsWith('/')) {
      // A ~ or a relative path would be read by the remote shell or from the login folder: neither is quoted.
      refusals.push(`machines.json: ${label}'s path "${path}" isn't absolute, so it isn't read`)
    } else if (/['\\]/.test(path)) {
      // A shell that isn't POSIX, such as fish, reads a backslash inside single quotes, so neither goes in one.
      refusals.push(`machines.json: ${label}'s path "${path}" holds a ' or a \\, so it isn't read`)
    } else if (socket !== undefined && !(typeof socket === 'string' && SOCKET.test(socket))) {
      // The machine is still read; only Watch, which is all the socket is for, is held back.
      refusals.push(`machines.json: ${label}'s tmux_socket isn't an absolute path of plain characters, so its issues get no Watch`)
      machines.push({ index, label, ssh, path: path.replace(/\/+$/, '') || '/', canWatch: false })
    } else {
      machines.push({ index, label, ssh, path: path.replace(/\/+$/, '') || '/', ...(typeof socket === 'string' ? { socket } : {}) })
    }
  })
  return { machines, refusals }
}

// A value as one word for the remote shell: single-quoted, with each ' closed, escaped and reopened.
export function q(s: string): string {
  return `'${s.replace(/'/g, `'\\''`)}'`
}

// ssh's options. BatchMode never asks for a password, so a machine without key-based SSH fails at once
// instead of waiting on a prompt nobody sees, and StrictHostKeyChecking only connects to a host already in
// known_hosts. The rest override the person's own ssh config, which applies to every read in the background:
// no agent, X11 or port forwarding for a machine that may be compromised, no local command, no terminal and
// no stdin, and a connection that stops answering is dropped in about 6 seconds. ControlPath=none shares no
// connection: a master your config opened earlier, with agent forwarding or after a prompt you answered,
// never carries a read, and no read leaves a master behind.
export const SSH_OPTIONS = [
  '-n', '-T',
  '-o', 'BatchMode=yes', '-o', `ConnectTimeout=${CONNECT_TIMEOUT_S}`, '-o', 'StrictHostKeyChecking=yes',
  '-o', 'ForwardAgent=no', '-o', 'ForwardX11=no', '-o', 'ClearAllForwardings=yes', '-o', 'PermitLocalCommand=no',
  '-o', 'ServerAliveInterval=3', '-o', 'ServerAliveCountMax=2', '-o', 'ControlPath=none',
]

// The whole ssh command line. -- ends ssh's options, so the destination is only ever read as one.
export function sshArgv(dest: string, command: string): string[] {
  return ['ssh', ...SSH_OPTIONS, '--', dest, command]
}

// The three remote commands, and the only ones this file builds.
export const lsCommand = (dir: string): string => `ls -1A ${q(dir)}`
export const catCommand = (file: string): string => `cat ${q(file)}`
export const killCommand = (pid: number): string => `kill -0 ${Math.trunc(pid)}`

// The folders a remote ls of .loop/projects/ names that a project here could be called, by projectName's
// rule: letters, digits, _, . and -, and no .. . Anything else is dropped, a quote, a backslash, a / or a
// control character among them, so no name a machine makes can step out of its quotes.
export function remoteNames(listing: string): string[] {
  return listing
    .split('\n')
    .filter(name => {
      const named = projectName(name)
      return 'name' in named && named.name === name
    })
    .sort((a, b) => a.localeCompare(b))
}

// A remote JSON file with every control character taken out of its strings, or null when it isn't JSON.
// The views draw these strings, and a machine could otherwise put terminal escapes in a title.
export function scrubbed(text: string | null): string | null {
  if (text === null) return null
  const clean = (v: unknown): unknown =>
    typeof v === 'string' ? v.replace(CONTROL, '')
      : Array.isArray(v) ? v.map(clean)
      : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k.replace(CONTROL, ''), clean(x)]))
      : v
  try {
    return JSON.stringify(clean(JSON.parse(text)))
  } catch {
    return null
  }
}

type Ran = { exitCode: number; stdout: string; stderr: string }

// What a failed ssh throws: no answer within READ_TIMEOUT_MS, a run that couldn't start, or ssh's own
// exit code, 255, for a connection that failed. A command that ran and failed, a missing file's cat
// say, isn't one.
const DOWN = new Error('the machine did not answer')

// One remote command, raced against the clock as well as the engine's timeout, so a run that never
// ends still ends the read.
async function ssh($: EngineInterface, machine: Machine, command: string): Promise<Ran> {
  const stop = new Promise<null>(resolve => {
    $.clock.after(READ_TIMEOUT_MS, () => resolve(null))
  })
  const run = $.process.run(sshArgv(machine.ssh, command), { timeoutMs: READ_TIMEOUT_MS }).catch(() => null)
  const ran = await Promise.race([run, stop])
  if (!ran || typeof ran.exitCode !== 'number' || ran.exitCode === 255) throw DOWN
  return { exitCode: ran.exitCode, stdout: ran.stdout ?? '', stderr: ran.stderr ?? '' }
}

// One loop on a machine, as the List's look takes one here, from the names its folder's ls gave.
async function lookRemote($: EngineInterface, machine: Machine, project: string | undefined, names: Set<string>): Promise<Seen> {
  const dir = `${machine.path}/${loopDir(project)}`
  const status = names.has('status.json') ? await ssh($, machine, catCommand(`${dir}/status.json`)) : null
  let alive: boolean | null = null
  if (names.has('lock')) {
    const lock = await ssh($, machine, catCommand(`${dir}/lock`))
    if (lock.exitCode === 0) {
      const pid = lockPid(lock.stdout)
      if (pid === null) alive = true
      else {
        const ran = await ssh($, machine, killCommand(pid))
        // kill -0 also fails on another user's process; count only "no such process" as gone.
        alive = ran.exitCode === 0 || !/no such process/i.test(ran.stderr)
      }
    }
  }
  return {
    root: machine.path,
    ...(project ? { project } : {}),
    machine: machine.label,
    machineIndex: machine.index,
    status: parseStatus(scrubbed(status && status.exitCode === 0 ? status.stdout : null)),
    isLocked: alive === true,
    isStaleLock: alive === false,
    isStopping: names.has('STOP'),
    hasWatchFile: false,
  }
}

// What an issue's usage.json held, with the row fields it was read for, so it's read again only when
// the row moves on.
type Usage = { started: string | undefined; tokens: number | undefined; cost_usd: number | undefined; text: string | null }
const usageKey = (seen: Seen, number: number): string => `${loopValue(seen)}#${number}`
const sameRun = (usage: Usage | undefined, row: Row): usage is Usage =>
  !!usage && usage.started === row.started && usage.tokens === row.tokens && usage.cost_usd === row.cost_usd

// Every loop on one machine: its factory's, then each project folder holding a status file, by name.
// A machine with no .loop/ yet has its factory's alone, with no status. The usage.json of each issue a
// live loop is working is read too, for the Crew's spend, unless its row hasn't changed since the last.
// One ssh at a time, the first alone: a machine that's gone costs one timeout, not one per command.
async function readMachine($: EngineInterface, machine: Machine, before: Map<string, Usage>): Promise<{ loops: Seen[]; usage: Map<string, Usage> }> {
  const top = await ssh($, machine, lsCommand(`${machine.path}/.loop`))
  const topNames = new Set(top.exitCode === 0 ? top.stdout.split('\n') : [])
  const loops = [await lookRemote($, machine, undefined, topNames)]
  if (topNames.has('projects')) {
    const listed = await ssh($, machine, lsCommand(`${machine.path}/${PROJECTS_DIR}`))
    for (const name of listed.exitCode === 0 ? remoteNames(listed.stdout) : []) {
      const inside = await ssh($, machine, lsCommand(`${machine.path}/${loopDir(name)}`))
      const names = new Set(inside.exitCode === 0 ? inside.stdout.split('\n') : [])
      if (names.has('status.json')) loops.push(await lookRemote($, machine, name, names))
    }
  }
  const usage = new Map<string, Usage>()
  for (const seen of loops) {
    if (!seen.isLocked) continue
    for (const row of seen.status?.issues ?? []) {
      if (row.state !== 'working') continue
      const key = usageKey(seen, row.number)
      const known = before.get(key)
      if (sameRun(known, row)) {
        usage.set(key, known)
        continue
      }
      const read = await ssh($, machine, catCommand(`${seen.root}/${loopDir(seen.project)}/issue-${row.number}/usage.json`))
      usage.set(key, { started: row.started, tokens: row.tokens, cost_usd: row.cost_usd, text: scrubbed(read.exitCode === 0 ? read.stdout : null) })
    }
  }
  return { loops, usage }
}

// What's known of one machine: its loops and their spend as last read, when it last answered, whether
// its last read failed, when a read last started, and whether one is under way.
type Entry = { loops: Seen[]; usage: Map<string, Usage>; lastReadAt: number | null; isDown: boolean; triedAt: number | null; isReading: boolean }

// The machines.json last read, and what's known of each machine it lists. A machine is keyed by all it
// says, so an edited line starts again. A reset bumps the generation, and a read started before it lands
// nowhere: its entry is no longer in the cache.
let known: { machines: Machine[]; refusals: string[] } = { machines: [], refusals: [] }
let cache = new Map<string, Entry>()
let generation = 0
const keyOf = (machine: Machine): string => JSON.stringify([machine.index, machine.label, machine.ssh, machine.path])

// Forget every machine and every read under way: the pane has closed, or is opening again.
export function resetRemote(): void {
  generation++
  cache = new Map()
  known = { machines: [], refusals: [] }
}

// A poll's turn: read machines.json again and start a read of each machine whose last began 30 seconds
// ago or more and isn't still running. It waits on no ssh. With no machines.json it runs nothing.
export async function pollRemote($: EngineInterface, root: string): Promise<void> {
  const parsed = parseMachines(await $.fs.read(`${root}/${MACHINES_FILE}`).catch(() => null))
  known = parsed
  const listed = new Set(parsed.machines.map(keyOf))
  for (const key of [...cache.keys()]) if (!listed.has(key)) cache.delete(key)
  if (!parsed.machines.length) return
  const now = await $.clock.now()
  for (const machine of parsed.machines) {
    const key = keyOf(machine)
    const entry: Entry = cache.get(key) ?? { loops: [], usage: new Map(), lastReadAt: null, isDown: false, triedAt: null, isReading: false }
    cache.set(key, entry)
    if (entry.isReading || (entry.triedAt !== null && now - entry.triedAt < READ_EVERY_MS)) continue
    entry.triedAt = now
    entry.isReading = true
    const at = generation
    void readMachine($, machine, entry.usage)
      .then(
        got => {
          if (at !== generation) return
          entry.loops = got.loops
          entry.usage = got.usage
          entry.lastReadAt = now
          entry.isDown = false
        },
        () => {
          if (at !== generation) return
          entry.loops = []
          entry.usage = new Map()
          entry.isDown = true
        },
      )
      .finally(() => {
        entry.isReading = false
      })
  }
}

// What the views draw from: every machine's loops as last read, in machines.json's order, each machine
// whose last read failed, and the lines saying which machines machines.json skips. A machine whose first
// read hasn't ended yet shows nothing.
export function remoteNow(): { loops: Seen[]; down: Down[]; refusals: string[] } {
  const loops: Seen[] = []
  const down: Down[] = []
  for (const machine of known.machines) {
    const entry = cache.get(keyOf(machine))
    if (!entry) continue
    if (entry.isDown) down.push({ index: machine.index, label: machine.label, lastReadAt: entry.lastReadAt })
    else loops.push(...entry.loops)
  }
  return { loops, down, refusals: [...known.refusals] }
}

// Another machine's loop as last read, by its picker value, or null when its machine isn't listed or answering.
export function remoteLoop(value: string): Seen | null {
  return remoteNow().loops.find(loop => loopValue(loop) === value) ?? null
}

// What an issue's usage.json on another machine held at the read that gave this row, or null.
export function remoteUsage(seen: Seen, row: Row): string | null {
  const machine = known.machines.find(m => m.index === seen.machineIndex)
  const usage = machine ? cache.get(keyOf(machine))?.usage.get(usageKey(seen, row.number)) : undefined
  return sameRun(usage, row) ? usage.text : null
}

// The ssh options for Watch's copied command, which a person runs in a terminal: -t for the terminal tmux
// needs, and, as for the reads, no password prompt, a known host only and nothing forwarded, so watching a
// machine that may be compromised hands it no agent. ControlPath=none overrides your ssh config's connection
// sharing, so Watch never rides a master opened earlier with agent forwarding and leaves none behind.
// Not SSH_OPTIONS: its -n and -T would stop the attach.
export const WATCH_SSH_OPTIONS = [
  '-t',
  '-o', 'BatchMode=yes', '-o', `ConnectTimeout=${CONNECT_TIMEOUT_S}`, '-o', 'StrictHostKeyChecking=yes',
  '-o', 'ForwardAgent=no', '-o', 'ForwardX11=no', '-o', 'ClearAllForwardings=yes', '-o', 'PermitLocalCommand=no',
  '-o', 'ControlPath=none',
]

// tmux on a machine, with its tmux_socket when it has one.
const tmuxOn = (machine: Machine): string => (machine.socket ? `tmux -S ${q(machine.socket)}` : 'tmux')

// What an issue on another machine attaches to, or null when it gets no Watch: its loop isn't live, isn't in
// tmux or gave the issue no window, its machine's tmux_socket was refused, or a name holds a character
// outside TMUX_NAME. The machine is looked up by its place in machines.json and has to carry the label the
// loop was read under, so an edit to the file between the read and a press can't pair one machine's session
// name with another machine.
export function remoteTarget(seen: Seen, row: Row): { machine: Machine; session: string; window: string } | null {
  if (seen.machineIndex === undefined || !seen.isLocked) return null
  const session = seen.status?.tmux
  const window = row.window
  const machine = known.machines.find(m => m.index === seen.machineIndex)
  if (!machine || machine.label !== seen.machine || machine.canWatch === false || !session || !window) return null
  return TMUX_NAME.test(session) && TMUX_NAME.test(window) ? { machine, session, window } : null
}

// The remote shell's command for Watch: attach read-only to the issue's window, the session and the window
// each matched exactly, so a window issue-1 that's gone never matches issue-12. The = is quoted, since zsh
// reads a word starting with = as a command lookup.
export function remoteAttach(machine: Machine, session: string, window: string): string | null {
  if (!TMUX_NAME.test(session) || !TMUX_NAME.test(window)) return null
  return `${tmuxOn(machine)} attach -r -t ${q(`=${session}:=${window}`)}`
}

// The line Watch copies, for the person's own shell. The destination is single-quoted, since SSH_DEST
// allows [ and ], which bash would glob. The remote command goes in double quotes: it holds single quotes,
// and nothing TMUX_NAME and SOCKET allow means anything to a shell inside double quotes. Null for a name
// outside them, so no name can reach a shell any other way.
export function remoteWatchLine(machine: Machine, session: string, window: string): string | null {
  const remote = remoteAttach(machine, session, window)
  if (remote === null || !SSH_DEST.test(machine.ssh) || machine.ssh.startsWith('-')) return null
  return ['ssh', ...WATCH_SSH_OPTIONS, '--', q(machine.ssh), `"${remote}"`].join(' ')
}

// The check Watch makes before copying: that the session is there.
export const hasSessionCommand = (machine: Machine, session: string): string => `${tmuxOn(machine)} has-session -t ${q(`=${session}`)}`

// Watch on another machine's issue, when a person presses it: the line to copy, or why there's none. It
// asks the machine first, so a session that's gone isn't copied.
export async function remoteWatch($: EngineInterface, seen: Seen, row: Row): Promise<{ line: string } | { why: string }> {
  const target = remoteTarget(seen, row)
  const line = target ? remoteWatchLine(target.machine, target.session, target.window) : null
  if (!target || line === null) return { why: "That issue's tmux window can't be watched from here" }
  try {
    const ran = await ssh($, target.machine, hasSessionCommand(target.machine, target.session))
    if (ran.exitCode !== 0) return { why: `${target.machine.label} has no tmux session ${target.session} now, so nothing was copied` }
  } catch {
    return { why: `${target.machine.label} didn't answer, so nothing was copied` }
  }
  return { line }
}
