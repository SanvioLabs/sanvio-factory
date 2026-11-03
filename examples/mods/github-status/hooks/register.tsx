import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import { QUERY, allText, due, failed, focusFile, focusName, lineFor, parseCounts, parseRemote, projectName, projectWhy, sectionText } from './logic'
import type { Tone } from './logic'
import type { Counts, GitHubState } from '../types'

const COMMAND = 'github'
const PROJECT_COMMAND = 'project'
// The only argument that clears the focus, and so a name that can never come into focus by /project.
const OFF = 'off'
const NOT_SAVED = "The focus couldn't be saved, so nothing changed."
// A project's name can't start with `:`, so this is never one.
const HARNESS_KEY = ':harness'
// How often the timer reads this session's file and asks whether a read is due. due() holds reads to one per two minutes.
const TICK_MS = 15_000
const GIT_TIMEOUT_MS = 5_000
const GH_TIMEOUT_MS = 15_000

const launchAtom = atom({ plugin: 'github-status', key: 'launch' } as const, null)
const statusAtom = atom({ plugin: 'github-status', key: 'status' } as const, null)
const attemptAtom = atom({ plugin: 'github-status', key: 'attempt' } as const, null)
const focusAtom = atom({ plugin: 'github-status', key: 'focus' } as const, null)

const COLORS: Record<Tone, { color?: string; dimColor?: boolean }> = {
  quiet: { dimColor: true },
  now: { color: 'cyan' },
  warn: { color: 'yellow' },
}

// Set on session.start from the origin remote. Null means no GitHub remote, and gh is never called for it.
let repo: string | null = null
// Whether repo has been looked up: a /clear fires no session.start, so /project looks it up once.
let isRepoKnown = false
// The focus a read is under way for, HARNESS_KEY for the harness's own. A read for a new focus can start during one for the old.
let reading: string | null = null
let timer: ReturnType<EngineInterface['clock']['every']> | null = null

// A repo to read, and the focus it's read for.
type Target = { focus: string | null; repo: string }

async function originRepo($: EngineInterface, cwd: string): Promise<string | null> {
  const ran = await $.process.run(['git', '-C', cwd, 'remote', 'get-url', 'origin'], { timeoutMs: GIT_TIMEOUT_MS }).catch(() => null)
  return ran && ran.exitCode === 0 ? parseRemote(ran.stdout) : null
}

// A read through gh. Each call is a GET or a GraphQL query: nothing here changes GitHub.
async function gh($: EngineInterface, args: string[]): Promise<string> {
  const ran = await $.process.run(['gh', ...args], { timeoutMs: GH_TIMEOUT_MS })
  if (ran.exitCode !== 0) throw new Error('gh failed')
  return ran.stdout
}

const runs = (name: string, status: 'in_progress' | 'queued') =>
  ['api', '--method', 'GET', `repos/${name}/actions/runs?status=${status}&per_page=1`]

// One repo's counts, from the three reads. Throws when any read fails or answers in the wrong shape.
async function readCounts($: EngineInterface, name: string): Promise<Counts> {
  const [owner, short] = name.split('/') as [string, string]
  const [graphql, running, queued] = await Promise.all([
    gh($, ['api', 'graphql', '-f', `query=${QUERY}`, '-f', `owner=${owner}`, '-f', `name=${short}`]),
    gh($, runs(name, 'in_progress')),
    gh($, runs(name, 'queued')),
  ])
  const counts = parseCounts(graphql, running, queued)
  if (!counts) throw new Error('unexpected answer')
  return counts
}

// A project's line for /github, read now. Unavailable when the read fails.
async function projectLine($: EngineInterface, name: string): Promise<string> {
  try {
    return lineFor({ kind: 'counts', repo: name, counts: await readCounts($, name), at: Date.now() }, Date.now()).text
  } catch {
    return lineFor({ kind: 'unavailable', repo: name }, Date.now()).text
  }
}

// The folders directly under projects/ at the harness root, by name. None when there's no projects/.
async function projectFolders($: EngineInterface, root: string): Promise<string[] | null> {
  const entries = await $.fs.list(`${root}/projects`).catch(() => null)
  if (!entries) return null
  return entries.filter(f => f.kind === 'dir' && !f.name.startsWith('.')).map(f => f.name).sort()
}

// A project folder's GitHub repo, only when the folder is a clone of its own. A plain folder has no .git,
// and git there would answer with the harness's remote instead.
async function projectRepo($: EngineInterface, root: string, name: string): Promise<string | null> {
  const folder = `${root}/projects/${name}`
  return (await $.fs.exists(`${folder}/.git`).catch(() => false)) ? originRepo($, folder) : null
}

// /github <name>: one project's repo.
async function oneProject($: EngineInterface, root: string, name: string): Promise<string> {
  const folders = await projectFolders($, root)
  if (!folders) return "There's no projects/ folder where this session started."
  if (!folders.includes(name)) return `projects/${name} isn't a folder.`
  const found = await projectRepo($, root, name)
  if (!found) return `projects/${name} has no GitHub origin remote, so there's nothing to read.`
  return `${name}: ${await projectLine($, found)}`
}

// /github all: the harness, then every project with a GitHub origin.
async function allProjects($: EngineInterface, root: string): Promise<string> {
  // Read now, like the projects, rather than through the line's state: a read already under way
  // would leave that empty.
  const harness = repo ? await projectLine($, repo) : lineFor({ kind: 'no-remote' }, Date.now()).text
  const folders = (await projectFolders($, root)) ?? []
  const remotes = await Promise.all(folders.map(async name => ({ name, found: await projectRepo($, root, name) })))
  const withRemote = remotes.filter((r): r is { name: string; found: string } => r.found !== null)
  const projects = await Promise.all(withRemote.map(async r => ({ name: r.name, text: await projectLine($, r.found) })))
  return allText(harness, projects, folders.length - withRemote.length, folders.length)
}

// The folder saved at session.start, else the session's root: a /clear starts a new session without one.
async function rootOf($: EngineInterface): Promise<string> {
  return (await read($, launchAtom)) ?? (await $.session.root())
}

// A real folder directly under projects/. A file, a link or a missing path isn't one.
async function isProject($: EngineInterface, root: string, name: string): Promise<boolean> {
  const stat = await $.fs.stat(`${root}/projects/${name}`).catch(() => null)
  return stat !== null && stat.kind === 'dir' && !stat.isLink
}

// This session's file, or null when its id is refused or can't name one. The id is read each time.
async function sessionFile($: EngineInterface, root: string): Promise<string | null> {
  return focusFile(root, await $.session.id().catch(() => null))
}

// The project in focus, from this session's file. Any failure means none. Never cached.
async function readFocus($: EngineInterface): Promise<string | null> {
  try {
    const root = await rootOf($)
    const file = await sessionFile($, root)
    if (!file) return null
    const name = focusName(await $.fs.read(file))
    return name && (await isProject($, root, name)) ? name : null
  } catch {
    return null
  }
}

// Writes this session's file. False, with nothing written, when the id or the write fails.
async function saveFocus($: EngineInterface, root: string, text: string): Promise<boolean> {
  const file = await sessionFile($, root)
  if (!file) return false
  return $.fs.write(file, text).then(() => true, () => false)
}

const tagged = (focus: string | null) => (focus ? { project: focus } : {})
const keyOf = (focus: string | null) => focus ?? HARNESS_KEY

const showNoRemote = ($: EngineInterface, focus: string | null) =>
  update($, statusAtom, (prev): GitHubState | null =>
    prev?.kind === 'no-remote' && prev.project === (focus ?? undefined) ? prev : { kind: 'no-remote', ...tagged(focus) })

// Marks a read as started: it counts for the limit from here, and the line says so unless it already
// shows this repo for this focus.
async function startRead($: EngineInterface, target: Target, now: number): Promise<void> {
  await update($, attemptAtom, () => now)
  await update($, statusAtom, (prev): GitHubState | null =>
    prev && prev.kind !== 'no-remote' && prev.repo === target.repo && prev.project === (target.focus ?? undefined)
      ? prev
      : { kind: 'reading', repo: target.repo, ...tagged(target.focus) })
  // Last, so an update that fails can't leave a read marked as under way.
  reading = keyOf(target.focus)
}

// The read itself, and what it found. A failed read shows as unavailable, or as stale counts. A read for
// a focus that's gone by the time it finishes writes nothing to the line, and still answers for its repo.
async function finishRead($: EngineInterface, target: Target): Promise<GitHubState> {
  const { focus, repo: name } = target
  try {
    let state: GitHubState
    try {
      state = { kind: 'counts', repo: name, counts: await readCounts($, name), at: Date.now(), ...tagged(focus) }
    } catch {
      state = failed(await read($, statusAtom), name, focus ?? undefined)
    }
    if ((await readFocus($)) === focus) await update($, statusAtom, () => state).catch(() => {})
    return state
  } finally {
    if (reading === keyOf(focus)) reading = null
  }
}

// Everything before gh: what's in focus, whether a read is due, and which repo it's for. Null when no
// read starts. A focus that changed reads straight away, whatever the limit says.
async function beginSync($: EngineInterface, isAsked = false): Promise<Target | null> {
  const focus = await readFocus($)
  const isChanged = focus !== (await read($, focusAtom))
  if (isChanged) await update($, focusAtom, () => focus)
  if (!focus && !repo) {
    await showNoRemote($, null)
    return null
  }
  const now = await $.clock.now()
  if (!due(await read($, attemptAtom), now, isAsked || isChanged)) return null
  // Only when a read is due, so a tick doesn't run git every 15 seconds. Never bare originRepo for a
  // focus: a plain folder would answer with the harness's remote.
  const name = focus ? await projectRepo($, await rootOf($), focus) : repo
  if ((await readFocus($)) !== focus) return null
  if (!name) {
    await update($, attemptAtom, () => now)
    await showNoRemote($, focus)
    return null
  }
  if (reading === keyOf(focus)) return null
  const target = { focus, repo: name }
  await startRead($, target, now)
  return target
}

async function sync($: EngineInterface, isAsked = false): Promise<void> {
  const target = await beginSync($, isAsked)
  if (target) await finishRead($, target)
}

function startTimer($: EngineInterface): void {
  timer = $.clock.every(TICK_MS, () => {
    void sync($).catch(() => {})
  })
}

// What every saved /project needs after a /clear, which fires no session.start: the harness's repo, for
// a later /project off and /github all, and the timer.
async function afterClear($: EngineInterface, root: string): Promise<void> {
  if (!isRepoKnown) {
    repo = await originRepo($, root)
    isRepoKnown = true
  }
  if (!timer) startTimer($)
}

// /project <name>: saved, then read now. The read fills the line and counts for the limit.
async function focusOn($: EngineInterface, arg: string): Promise<string> {
  const root = await rootOf($)
  const picked = projectName(arg)
  const name = 'name' in picked && picked.name !== OFF && (await isProject($, root, picked.name)) ? picked.name : null
  if (!name) return projectWhy(arg)
  if (!(await saveFocus($, root, `${name}\n`))) return NOT_SAVED
  await update($, focusAtom, () => name)
  await afterClear($, root)
  const now = await $.clock.now()
  const found = await projectRepo($, root, name)
  if (!found) {
    await update($, attemptAtom, () => now)
    await showNoRemote($, name)
    return lineFor({ kind: 'no-remote', project: name }, Date.now()).text
  }
  const target = { focus: name, repo: found }
  await startRead($, target, now)
  // This read's own answer, not the line's: the focus may have moved on while it ran.
  return lineFor(await finishRead($, target), Date.now()).text
}

// /project off: the file is left empty, and the line stops showing the project at once. The harness's
// read isn't waited for.
async function focusOff($: EngineInterface): Promise<string> {
  const root = await rootOf($)
  if (!(await saveFocus($, root, ''))) return NOT_SAVED
  const had = await read($, focusAtom)
  await update($, focusAtom, () => null)
  await afterClear($, root)
  if (had !== null) {
    if (!repo) await showNoRemote($, null)
    else {
      const target = { focus: null, repo }
      await startRead($, target, await $.clock.now())
      void finishRead($, target).catch(() => {})
    }
  }
  return 'No project in focus. The GitHub line shows the harness again.'
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    // A reload fires session.start again; the directory the session started in is the first one.
    await update($, launchAtom, prev => prev ?? e.cwd)
    await $.command.register({
      name: COMMAND,
      description: "Read GitHub now: the repo's running actions, open pull requests and open issues. /github <project> or /github all for repos under projects/",
    })
    await $.command.register({
      name: PROJECT_COMMAND,
      description: 'Put a project in focus for this session: /project <name> under projects/, /project off to clear it, /project alone to see which',
    })
    const launch = await read($, launchAtom)
    repo = launch ? await originRepo($, launch) : null
    isRepoKnown = true
    timer?.cancel()
    reading = null
    startTimer($)
    // The focus settles before the session goes on, so a reload never flashes the harness's line. GitHub isn't waited for.
    const target = await beginSync($).catch(() => null)
    if (target) void finishRead($, target).catch(() => {})
    return next(e)
  })

  on('command.run', { command: PROJECT_COMMAND }, async ($, e) => {
    const arg = e.args.trim()
    if (arg === OFF) return { text: await focusOff($) }
    if (arg) return { text: await focusOn($, arg) }
    await afterClear($, await rootOf($))
    const focus = await readFocus($)
    return { text: focus ? `In focus: projects/${focus}.` : 'No project in focus.' }
  })

  // The system prompt is rendered from this: the file is read each time, and the atom is left alone so
  // the next tick still sees a change.
  on('prompt.compose', async ($, e, next) => {
    const result = await next(e)
    const focus = await readFocus($)
    if (!focus) return result
    return { ...result, sections: [...result.sections, { id: 'github-status:project', scope: 'session' as const, text: sectionText(focus) }] }
  })

  on('command.run', { command: COMMAND }, async ($, e) => {
    const arg = e.args.trim()
    if (arg) {
      // Another repo, read once now. The line above the prompt stays as it is.
      const root = await rootOf($)
      if (arg === 'all') return { text: await allProjects($, root) }
      const picked = projectName(arg)
      if ('why' in picked) return { text: picked.why }
      return { text: await oneProject($, root, picked.name) }
    }
    await sync($, true).catch(() => {})
    if (!(await read($, focusAtom)) && !repo) return { text: "This session's folder has no GitHub origin remote, so there's nothing to read." }
    const status = await read($, statusAtom)
    return { text: status ? lineFor(status, Date.now()).text : 'Nothing read yet.' }
  })

  // Drawn above the prompt, then whatever another mod draws there: two bands stack, neither hides the other.
  // It only reads the atom: GitHub is read on the timer and by /github, never while drawing.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const status = await read($, statusAtom)
    if (!status || e.props.hasSurvey) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const line = lineFor(status, Date.now())
    const below = await next(e)
    return (
      <Box flexDirection="column">
        <Box flexWrap="wrap" columnGap={2}>
          <Text bold>◆ github</Text>
          <Text {...COLORS[line.tone]}>{line.text}</Text>
        </Box>
        {below}
      </Box>
    )
  })
}
