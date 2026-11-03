// The decisions, as pure functions. register.tsx reads files and watches events, then calls in here,
// because the test kit can't stand in for the filesystem.

import type { GateHit, Hit, Lens, Run, Scope } from '../types'

// Where a harness keeps each layer, relative to its root. A harness with another layout says so in
// .claude/harness-lens.json, with any of these keys; a key left out keeps the starter's value.
export type Config = {
  // Folders of steering files.
  steering: string[]
  // Files whose `@path` lines load steering into every session.
  always: string[]
  // Folders whose subfolders are the harness's own skills. `*` stands for one folder name.
  skills: string[]
  // Plugin namespaces whose skills count as the harness's too: `studio:` for `studio:phase-gate`.
  skillPrefixes: string[]
  // Folders whose `<name>.md` files are the harness's agents.
  agents: string[]
  // Patterns for a shell command that runs a gate. The first group, if any, is the gate's name.
  gates: string[]
  // Files that hold this session's scope, read in order until one names it. `{session}` stands for the
  // session id. Put a file a guard enforces first, so a looser one never shows over it. The starter has none.
  scope: string[]
  // Headless sessions to count, by label: a `claude` process counts under the first label whose pattern
  // matches the command of a process it runs beneath.
  running: Record<string, string>
}

export const STARTER: Config = {
  steering: ['steering'],
  always: ['AGENTS.md'],
  skills: ['skills', 'examples/*/skills'],
  skillPrefixes: [],
  agents: ['agents'],
  gates: ['([\\w-]+)_gate\\.py'],
  scope: [],
  running: { loop: 'scripts/loop\\.py', eval: 'scripts/eval_agents\\.py' },
}

export const CONFIG_FILE = '.claude/harness-lens.json'

type ListKey = Exclude<keyof Config, 'running'>
const KEYS = Object.keys(STARTER).filter(key => key !== 'running') as ListKey[]

function compile(pattern: string): RegExp | null {
  if (!pattern) return null
  try {
    return new RegExp(pattern)
  } catch {
    return null
  }
}

export function parseConfig(text: string | null): Config {
  if (text === null) return STARTER
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return STARTER
  }
  const given = (raw ?? {}) as Record<string, unknown>
  const config = { ...STARTER }
  for (const key of KEYS) {
    const value = given[key]
    if (Array.isArray(value) && value.every(item => typeof item === 'string')) config[key] = value as string[]
  }
  // An empty pattern or one that doesn't compile is dropped, rather than matching everything or nothing.
  const labels = given.running
  if (labels && typeof labels === 'object' && !Array.isArray(labels) && Object.values(labels).every(item => typeof item === 'string')) {
    config.running = Object.fromEntries(Object.entries(labels as Record<string, string>).filter(([, pattern]) => compile(pattern)))
  }
  return config
}

const tidy = (path: string) => path.replace(/^\.\//, '').replace(/\/+$/, '')
const escape = (text: string) => text.replace(/[.+?^${}()|[\]\\]/g, '\\$&')
const folderPattern = (folder: string) =>
  tidy(folder).split('/').map(part => (part === '*' ? '[^/]+' : escape(part))).join('/')

// A path inside the root, relative to it. Anything outside is none of the lens's business.
export function relative(path: string, root: string): string | null {
  const base = `${root.replace(/\/+$/, '')}/`
  return path.startsWith(base) ? path.slice(base.length) : null
}

export function steeringName(rel: string, config: Config): string | null {
  for (const folder of config.steering) {
    const match = rel.match(new RegExp(`^${folderPattern(folder)}/([^/]+)\\.md$`))
    const name = match?.[1]
    if (name && name.toLowerCase() !== 'readme') return name
  }
  return null
}

// The steering every session gets: each `@path` line in the always-loaded files that names a steering file.
export function alwaysSteering(texts: readonly string[], config: Config): string[] {
  const names: string[] = []
  for (const text of texts) {
    for (const line of text.split('\n')) {
      const match = line.trim().match(/^@(\S+)$/)
      const path = match?.[1]
      const name = path ? steeringName(tidy(path), config) : null
      if (name && !names.includes(name)) names.push(name)
    }
  }
  return names
}

// A skill followed by reading its file, which is how Codex, Kiro and a model that skips the Skill tool do it.
export function skillFromPath(rel: string, config: Config): string | null {
  for (const folder of config.skills) {
    const name = rel.match(new RegExp(`^${folderPattern(folder)}/([^/]+)/SKILL\\.md$`))?.[1]
    if (name) return name
  }
  return null
}

// skill.prompt names every skill a session expands, a machine-wide plugin's too. Only the harness's own
// show, so a projector never lists someone's personal plugins.
export function harnessSkill(name: string, known: readonly string[], config: Config): string | null {
  if (known.includes(name)) return name
  for (const prefix of config.skillPrefixes) {
    if (prefix && name.startsWith(prefix)) return name.slice(prefix.length)
  }
  return null
}

export type GateRun = { name: string; ok: boolean }

// A line may open with a colour code, as a hook that prints in red does.
const FAILED = /^(\x1b\[[0-9;]*m)*(FAIL|BLOCKED)\b|Commit blocked|✗/m
const PASSED = /^(\x1b\[[0-9;]*m)*PASS\b|✓/m
const REFUSED = /^(\x1b\[[0-9;]*m)*BLOCKED\b|Commit blocked/m

// A shell command that ran a gate, and how it went. None when the command ran no gate, or when the output
// can't say: a gate piped somewhere else doesn't count as a pass.
export function gateRun(command: string, output: string, isError: boolean, config: Config): GateRun | null {
  for (const pattern of config.gates) {
    let match: RegExpMatchArray | null
    try {
      match = command.match(new RegExp(pattern))
    } catch {
      continue
    }
    if (!match) continue
    const name = match[1] ?? 'gate'
    if (isError || FAILED.test(output)) return { name, ok: false }
    if (PASSED.test(output)) return { name, ok: true }
    return null
  }
  // The pre-commit hook is silent when it passes, so only a refusal can be seen.
  if (/\bgit\s+commit\b/.test(command) && REFUSED.test(output)) return { name: 'pre-commit', ok: false }
  return null
}

export function emptyLens(root: string, always: string[]): Lens {
  return { root, turn: 0, always, steering: [], skills: [], gates: [], refusals: [], reviews: [], runs: [], scope: null }
}

const SESSION = /^[0-9a-fA-F-]{8,64}$/

// The scope files to try, relative to the root. A pattern that needs the session id is skipped without
// one, rather than read with a guess.
export function scopeFiles(config: Config, sessionId: string | null): string[] {
  const id = sessionId && SESSION.test(sessionId) ? sessionId : null
  const out: string[] = []
  for (const pattern of config.scope) {
    if (pattern.includes('{session}') && !id) continue
    const path = tidy(id ? pattern.split('{session}').join(id) : pattern)
    if (path && !path.split('/').includes('..') && !out.includes(path)) out.push(path)
  }
  return out
}

// One scope file: `{"client": "acme"}` from a client guard, or `{"kind": "partner", "name": "fabrikam"}`.
export function parseScope(text: string): Scope | null {
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    return null
  }
  if (!data || typeof data !== 'object') return null
  const { client, kind, name } = data as Record<string, unknown>
  if (typeof client === 'string' && client.trim()) return { kind: 'client', name: client.trim().toLowerCase() }
  if (typeof kind === 'string' && kind.trim() && typeof name === 'string' && name.trim()) return { kind: kind.trim(), name: name.trim() }
  return null
}

export function scopeText(scope: Scope): string {
  return scope.kind === scope.name ? scope.name : `${scope.kind} ${scope.name}`
}

const KEEP = 50

// Newest last. A name seen again moves to the end, so the list reads as what happened most recently.
export function remember<T extends Hit>(list: readonly T[], hit: T): T[] {
  return [...list.filter(item => item.name !== hit.name), hit].slice(-KEEP)
}

// Every gate run counts, a repeat included, so the report can say passed 3, failed 1.
export function record<T extends Hit>(list: readonly T[], hit: T): T[] {
  return [...list, hit].slice(-KEEP)
}

// A subagent started. Only the harness's own agents count, so an Explore or a plugin's agent never shows.
// A resumed agent comes back under its id, so it replaces its earlier run rather than adding a second.
export function startRun(lens: Lens, agentId: string, subagentType: string, agents: readonly string[], now: number): Lens {
  if (!agentId || !agents.includes(subagentType)) return lens
  const runs = (lens.runs ?? []).filter(run => run.id !== agentId)
  return { ...lens, runs: [...runs, { id: agentId, name: subagentType, started: now }].slice(-KEEP) }
}

// A subagent's run ended. Only a run still open under that id changes: any other agent's end is ignored.
export function endRun(lens: Lens, agentId: string, ok: boolean, now: number): Lens {
  const runs = lens.runs ?? []
  if (!runs.some(run => run.id === agentId && run.ended === undefined)) return lens
  return {
    ...lens,
    runs: runs.map(run => (run.id === agentId && run.ended === undefined ? { ...run, ended: now, ok, turn: lens.turn } : run)),
  }
}

// How a status in the session's agent list ends a run. A status not here is still working.
const SETTLED = new Map([['completed', true], ['failed', false], ['killed', false]])

// Runs whose end the lens didn't hear, as when one ends during a reload, settled from the session's agent
// list. A run the list no longer has ends with its outcome unknown. A run already ended is never touched,
// and nothing to settle comes back as the same object, so nothing is written.
export function settleRuns(lens: Lens, rows: readonly { id: string; status: string }[], now: number): Lens {
  const status = new Map(rows.map(row => [row.id, row.status]))
  let changed = false
  const runs = (lens.runs ?? []).map(run => {
    if (run.ended !== undefined) return run
    const said = status.get(run.id)
    if (said === undefined) {
      changed = true
      return { ...run, ended: now, turn: lens.turn }
    }
    const ok = SETTLED.get(said)
    if (ok === undefined) return run
    changed = true
    return { ...run, ended: now, ok, turn: lens.turn }
  })
  return changed ? { ...lens, runs } : lens
}

const running = (lens: Lens) => (lens.runs ?? []).filter(run => run.ended === undefined)

// 80 seconds is 1:20.
export function elapsed(run: Run, now: number): string {
  const seconds = Math.max(0, Math.floor((now - run.started) / 1000))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

// A `claude` command, by path or through node: `claude -p`, `/usr/local/bin/claude`, `node …/claude`.
const CLAUDE = /^(?:(?:\S*\/)?node\s+)?(?:\S*\/)?claude(?:\s|$)/

// The headless sessions running, by label, from `ps -axo pid,ppid,command`. Each `claude` process counts
// under the label of the nearest process above it whose command matches a pattern, and not at all when
// none does, so an interactive session under a shell is left out. A label with none isn't in the result.
export function countSessions(ps: string, config: Config): Record<string, number> {
  const parent = new Map<number, number>()
  const command = new Map<number, string>()
  for (const line of ps.split('\n')) {
    // The header, and anything else that isn't a row, doesn't match.
    const match = line.trim().match(/^(\d+)\s+(\d+)\s+(.+)$/)
    if (!match) continue
    parent.set(Number(match[1]), Number(match[2]))
    command.set(Number(match[1]), match[3]!)
  }
  const patterns: Array<[string, RegExp]> = []
  for (const [label, pattern] of Object.entries(config.running)) {
    const re = compile(pattern)
    if (re) patterns.push([label, re])
  }
  const counts: Record<string, number> = {}
  for (const [pid, text] of command) {
    if (!CLAUDE.test(text)) continue
    // Up the chain to pid 1. A pid seen before ends the walk, so a loop in the rows can't hang it.
    const seen = new Set([pid])
    let at = parent.get(pid)
    while (at !== undefined && at > 1 && !seen.has(at)) {
      seen.add(at)
      const above = command.get(at) ?? ''
      const label = patterns.find(([, re]) => re.test(above))?.[0]
      if (label) {
        counts[label] = (counts[label] ?? 0) + 1
        break
      }
      at = parent.get(at)
    }
  }
  return counts
}

const sameCounts = (a: Record<string, number>, b: Record<string, number>) =>
  Object.keys(a).length === Object.keys(b).length && Object.entries(a).every(([label, n]) => b[label] === n)

// The counts after a `ps`. A null output is a `ps` that failed or timed out, and keeps the last counts.
// Counts that haven't changed come back as the same object, so nothing is written.
export function nextSessions(prev: Record<string, number> | undefined, output: string | null, config: Config): Record<string, number> | undefined {
  if (output === null) return prev
  const counts = countSessions(output, config)
  return prev && sameCounts(prev, counts) ? prev : counts
}

const sessionText = (sessions: Record<string, number>) =>
  Object.entries(sessions)
    .filter(([, n]) => n > 0)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([label, n]) => `${label} ${n}`)
    .join(' · ')

export type Tone = 'now' | 'pass' | 'fail' | 'earlier' | 'quiet' | 'warn'
export type Segment = { label: string; text: string; tone: Tone }

// Maps, so a subscriptionType such as `constructor` finds nothing rather than an object's own property.
const BUSINESS = new Map([['team', 'Team'], ['enterprise', 'Enterprise']])
const PERSONAL = new Map([['pro', 'Pro'], ['max', 'Max'], ['free', 'Free']])

// The plan segment, from the stdout of `claude auth status`. A null output is a command that failed,
// exited non-zero or timed out. Only loggedIn, authMethod, subscriptionType and orgName are read: never
// the email or the org id. A personal plan's orgName holds the person's email, so it's never read there.
export function planSegment(output: string | null): Segment {
  const unknown: Segment = { label: 'plan', text: 'unknown', tone: 'quiet' }
  if (output === null) return unknown
  let data: unknown
  try {
    data = JSON.parse(output)
  } catch {
    return unknown
  }
  if (!data || typeof data !== 'object' || Array.isArray(data)) return unknown
  const { loggedIn, authMethod, subscriptionType, orgName } = data as Record<string, unknown>
  if (loggedIn !== true) return unknown
  // An API key login has no plan, so it's checked first.
  if (typeof authMethod === 'string' && /api.?key/i.test(authMethod)) return { label: 'plan', text: 'API key', tone: 'earlier' }
  const kind = typeof subscriptionType === 'string' ? subscriptionType.trim().toLowerCase() : ''
  const business = BUSINESS.get(kind)
  if (business) {
    const org = typeof orgName === 'string' && orgName.trim() && !orgName.includes('@') ? ` · ${orgName.trim()}` : ''
    return { label: 'plan', text: `${business}${org}`, tone: 'earlier' }
  }
  const personal = PERSONAL.get(kind)
  if (personal) return { label: 'plan', text: `${personal} (personal)`, tone: 'warn' }
  return unknown
}

// The review segment: what is running now, else how the last one to end went, else the last reviewer seen.
export function reviewSegment(lens: Lens, now: number): Segment {
  const open = running(lens)
  if (open.length === 1) return { label: 'review', text: `▶ ${open[0]!.name} ${elapsed(open[0]!, now)}`, tone: 'now' }
  if (open.length > 3) return { label: 'review', text: `▶ ${open.length}`, tone: 'now' }
  if (open.length) return { label: 'review', text: `▶ ${open.length} ${open.map(run => run.name).join(' · ')}`, tone: 'now' }
  // The last to end, not the last to start: a reviewer started first can finish last.
  const last = (lens.runs ?? []).reduce<Run | undefined>((latest, run) => (latest === undefined || run.ended! >= latest.ended! ? run : latest), undefined)
  if (last) {
    // Ended without the lens seeing how, so neither ✓ nor ✗.
    if (last.ok === undefined) return { label: 'review', text: `? ${last.name}`, tone: 'quiet' }
    return {
      label: 'review',
      text: `${last.ok ? '✓' : '✗'} ${last.name}`,
      tone: last.turn === lens.turn ? (last.ok ? 'pass' : 'fail') : 'earlier',
    }
  }
  const review = lens.reviews.at(-1)
  return { label: 'review', text: review?.name ?? 'none yet', tone: review ? (review.turn === lens.turn ? 'now' : 'earlier') : 'quiet' }
}

// The band: one segment per layer. A layer that acted this turn stands out; one that acted earlier is dim.
// The session's plan, when given, goes after the scope and before steering.
export function bandSegments(lens: Lens, showScope = false, now = Date.now(), plan: Segment | null = null): Segment[] {
  const thisTurn = (hit: Hit | undefined) => hit !== undefined && hit.turn === lens.turn
  const readNow = lens.steering.filter(thisTurn).map(hit => hit.name)
  const always = lens.always.length ? `${lens.always.length} always on` : 'none always on'
  const steering: Segment = readNow.length
    ? { label: 'steering', text: `${always} + ${readNow.join(' · ')}`, tone: 'now' }
    : { label: 'steering', text: lens.steering.length ? `${always} + ${lens.steering.length} read` : always, tone: 'earlier' }

  const skill = lens.skills.at(-1)
  const gate = lens.gates.at(-1)
  const refusal = lens.refusals.at(-1)
  const sessions = sessionText(lens.sessions ?? {})
  // Only a harness that declares where its scope lives gets the segment, so the starter's band is unchanged.
  const scope: Segment[] = showScope
    ? [lens.scope ? { label: 'scope', text: scopeText(lens.scope), tone: 'earlier' } : { label: 'scope', text: 'none', tone: 'quiet' }]
    : []
  return [
    ...scope,
    ...(plan ? [plan] : []),
    steering,
    { label: 'skill', text: skill?.name ?? 'none yet', tone: thisTurn(skill) ? 'now' : skill ? 'earlier' : 'quiet' },
    {
      label: 'gate',
      text: gate ? `${gate.ok ? '✓' : '✗'} ${gate.name}` : 'none run',
      tone: thisTurn(gate) ? (gate!.ok ? 'pass' : 'fail') : gate ? 'earlier' : 'quiet',
    },
    {
      label: 'guard',
      text: refusal ? `✗ refused ${refusal.name}` : 'no refusals',
      tone: thisTurn(refusal) ? 'fail' : refusal ? 'earlier' : 'quiet',
    },
    reviewSegment(lens, now),
    sessions ? { label: 'running', text: sessions, tone: 'now' } : { label: 'running', text: 'none', tone: 'quiet' },
  ]
}

function counts(list: readonly Hit[]): string {
  const seen = new Map<string, number>()
  for (const hit of list) seen.set(hit.name, (seen.get(hit.name) ?? 0) + 1)
  return [...seen].map(([name, n]) => (n > 1 ? `${name} ×${n}` : name)).join(', ')
}

// What /lens prints: the whole session, layer by layer. `labels` are the configured `running` labels,
// each listed with its count, a zero included.
export function lensReport(lens: Lens, showScope = false, now = Date.now(), labels: readonly string[] = Object.keys(STARTER.running)): string {
  const open = running(lens)
  const names = (list: readonly Hit[]) => (list.length ? list.map(hit => hit.name).join(', ') : 'none')
  const passed = lens.gates.filter(gate => gate.ok)
  const failed = lens.gates.filter(gate => !gate.ok)
  const gates = lens.gates.length
    ? [passed.length ? `passed ${counts(passed)}` : '', failed.length ? `failed ${counts(failed)}` : ''].filter(Boolean).join('; ')
    : 'none run'
  return [
    'What the harness did this session:',
    ...(showScope ? [`  Scope: ${lens.scope ? scopeText(lens.scope) : 'none'}`] : []),
    `  Steering, always on: ${lens.always.length ? lens.always.join(', ') : 'none'}`,
    `  Steering, read when it applied: ${names(lens.steering)}`,
    `  Skills followed: ${names(lens.skills)}`,
    `  Gates: ${gates}`,
    `  Guard refusals: ${lens.refusals.length ? counts(lens.refusals) : 'none'} (the reasons are in the transcript)`,
    `  Reviewers: ${names(lens.reviews)}`,
    '  Running now:',
    ...(open.length ? open.map(run => `    ${run.name} ${elapsed(run, now)}`) : ['    no reviewers']),
    ...labels.map(label => `    ${label} sessions: ${lens.sessions?.[label] ?? 0}`),
  ].join('\n')
}
