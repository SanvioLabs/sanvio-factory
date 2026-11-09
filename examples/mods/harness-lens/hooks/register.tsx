import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import { CONFIG_FILE, STARTER, alwaysSteering, bandSegments, emptyLens, endRun, gateRun, harnessSkill, lensReport, nextSessions, parseConfig, parseScope, planSegment, record, relative, remember, scopeFiles, settleRuns, skillFromPath, startRun, steeringName } from './logic'
import type { Config, Segment, Tone } from './logic'
import type { Lens, Scope } from '../types'

const launchAtom = atom({ plugin: 'harness-lens', key: 'launch' } as const, null)
const lensAtom = atom({ plugin: 'harness-lens', key: 'lens' } as const, null)

const PS_TIMEOUT_MS = 2_000
const AUTH_TIMEOUT_MS = 2_000

// Rebuilt on every load, so a new skill or agent shows up after a reload.
let config: Config = STARTER
let skills: string[] = []
let agents: string[] = []
// The session's Claude plan, read once at session.start. A redraw only reads it.
let plan: Segment = planSegment(null)

const COLORS: Record<Tone, { color?: string; bold?: boolean; dimColor?: boolean }> = {
  now: { color: 'cyan', bold: true },
  pass: { color: 'green', bold: true },
  fail: { color: 'red', bold: true },
  earlier: {},
  quiet: { dimColor: true },
  warn: { color: 'yellow', bold: true },
}

// The plan from `claude auth status`, with the session's own environment, so it reads the config directory
// the session started with. A command that fails, exits non-zero or takes too long gives `unknown`.
async function readPlan($: EngineInterface): Promise<void> {
  const ran = await $.process.run(['claude', 'auth', 'status'], { timeoutMs: AUTH_TIMEOUT_MS }).catch(() => null)
  plan = planSegment(ran && ran.exitCode === 0 ? ran.stdout : null)
}

async function readOr($: EngineInterface, path: string): Promise<string | null> {
  return $.fs.read(path).catch(() => null)
}

// The harness root: the nearest folder above the launch directory with a lens config, or with the
// default shape (AGENTS.md beside steering/). None means this session isn't in a harness.
async function findRoot($: EngineInterface, from: string): Promise<string | null> {
  let dir = from.replace(/\/+$/, '')
  while (dir) {
    if (await $.fs.exists(`${dir}/${CONFIG_FILE}`)) return dir
    if ((await $.fs.exists(`${dir}/AGENTS.md`)) && (await $.fs.exists(`${dir}/steering`))) return dir
    dir = dir.slice(0, dir.lastIndexOf('/'))
  }
  return null
}

// A configured folder, with each `*` part expanded to the folders actually there.
async function folders($: EngineInterface, root: string, pattern: string): Promise<string[]> {
  let found = [root]
  for (const part of pattern.replace(/^\.\//, '').replace(/\/+$/, '').split('/')) {
    const next: string[] = []
    for (const dir of found) {
      if (part !== '*') {
        next.push(`${dir}/${part}`)
        continue
      }
      const entries = await $.fs.list(dir).catch(() => [])
      for (const entry of entries) if (entry.kind === 'dir') next.push(`${dir}/${entry.name}`)
    }
    found = next
  }
  return found
}

async function names($: EngineInterface, root: string, patterns: readonly string[], kind: 'skill' | 'agent'): Promise<string[]> {
  const out: string[] = []
  for (const pattern of patterns) {
    for (const dir of await folders($, root, pattern)) {
      for (const entry of await $.fs.list(dir).catch(() => [])) {
        const name = kind === 'skill' ? (entry.kind !== 'file' ? entry.name : null) : entry.name.endsWith('.md') ? entry.name.slice(0, -3) : null
        if (name && name.toLowerCase() !== 'readme' && !out.includes(name)) out.push(name)
      }
    }
  }
  return out
}

async function load($: EngineInterface): Promise<void> {
  // The folder saved at session.start first, then the session's root: a /clear starts a new session
  // without a session.start, so the saved folder can be missing or the last session's.
  const launch = await read($, launchAtom)
  const root = (launch && (await findRoot($, launch))) || (await findRoot($, await $.session.root()))
  if (!root) {
    await update($, lensAtom, () => null)
    return
  }
  config = parseConfig(await readOr($, `${root}/${CONFIG_FILE}`))
  skills = await names($, root, config.skills, 'skill')
  agents = await names($, root, config.agents, 'agent')
  const texts: string[] = []
  for (const file of config.always) {
    const text = await readOr($, `${root}/${file}`)
    if (text !== null) texts.push(text)
  }
  const always = alwaysSteering(texts, config)
  // A reload keeps what the session has already seen; a new root starts clean.
  await update($, lensAtom, prev => (prev && prev.root === root ? { ...prev, always } : emptyLens(root, always)))
}

// This session's scope, from the first file `scope` lists that names one. A file can change from a Bash
// call or another mod's command, so this runs after each Bash call, each turn, and every few seconds.
async function refreshScope($: EngineInterface): Promise<void> {
  if (!config.scope.length) return
  const lens = await read($, lensAtom)
  if (!lens) return
  const sessionId = await $.session.id().catch(() => null)
  let scope: Scope | null = null
  for (const rel of scopeFiles(config, sessionId)) {
    const text = await readOr($, `${lens.root}/${rel}`)
    scope = text === null ? null : parseScope(text)
    if (scope) break
  }
  const same = (a: Scope | null, b: Scope | null) => a?.kind === b?.kind && a?.name === b?.name
  if (!same(scope, lens.scope ?? null)) await update($, lensAtom, prev => (prev ? { ...prev, scope } : prev))
}

async function change($: EngineInterface, edit: (lens: Lens) => Lens): Promise<void> {
  await update($, lensAtom, prev => (prev ? edit(prev) : prev))
}

// The headless sessions under each `running` pattern, from ps. A ps that fails or takes too long keeps
// the last counts, and counts that haven't changed write nothing.
async function refreshSessions($: EngineInterface): Promise<void> {
  const lens = await read($, lensAtom)
  if (!lens) return
  const ran = await $.process.run(['ps', '-axo', 'pid,ppid,command'], { timeoutMs: PS_TIMEOUT_MS }).catch(() => null)
  const sessions = nextSessions(lens.sessions, ran && ran.exitCode === 0 ? ran.stdout : null, config)
  if (sessions !== lens.sessions) await change($, l => ({ ...l, sessions }))
}

// Every few seconds: the scope, the headless sessions, and while a reviewer runs, a redraw so its time moves.
async function tick($: EngineInterface): Promise<void> {
  await refreshScope($).catch(() => {})
  await refreshSessions($).catch(() => {})
  const lens = await read($, lensAtom)
  if (!lens || !(lens.runs ?? []).some(run => run.ended === undefined)) return
  // A reviewer can end without the lens hearing, as during a reload, so the session's agent list settles it.
  // A list that fails changes nothing. The redraw still runs, so a run settled now shows how it ended.
  try {
    const rows = await $.agent.list()
    await change($, l => settleRuns(l, rows, Date.now()))
  } catch {}
  $.ui.invalidate('ui.render')
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    // A reload fires session.start again; the directory the session started in is the first one.
    await update($, launchAtom, prev => prev ?? e.cwd)
    await $.command.register({
      name: 'lens',
      description: 'Show what the harness did this session: steering, skills, gates, guard refusals, reviewers and headless sessions',
    })
    await load($).catch(() => {})
    await readPlan($).catch(() => {})
    await refreshScope($).catch(() => {})
    $.clock.every(3_000, () => void tick($).catch(() => {}))
    return next(e)
  })

  on('command.run', { command: 'lens' }, async $ => {
    const lens = await read($, lensAtom)
    return { text: lens ? lensReport(lens, config.scope.length > 0, Date.now(), Object.keys(config.running)) :"This session didn't start inside a harness, so there's nothing to show." }
  })

  on('turn.start', async ($, e, next) => {
    // A subagent's run is a turn too. Only the main session's turns count, or each reviewer would dim the band.
    if (e.agentId !== undefined) return next(e)
    await change($, lens => ({ ...lens, turn: lens.turn + 1 }))
    await refreshScope($).catch(() => {})
    return next(e)
  })

  on('skill.prompt', async ($, e, next) => {
    const out = await next(e)
    const name = harnessSkill(e.skill, skills, config)
    if (name) await change($, lens => ({ ...lens, skills: remember(lens.skills, { name, turn: lens.turn }) })).catch(() => {})
    return out
  })

  // The harness's guards run beneath this hook, and their answer goes back exactly as it came: the lens
  // only looks. No .catch on purpose: a hook that throws is skipped and the guards' decision stands.
  on('classic.PreToolUse', async ($, e, next) => {
    const decision = await next(e)
    if (decision.deny) {
      try {
        const tool = String(e.tool)
        await change($, lens => ({ ...lens, refusals: record(lens.refusals, { name: tool, turn: lens.turn }) }))
        $.ui.toast(`🛡 The guard refused ${tool}`)
      } catch {}
    }
    return decision
  })

  on('tool.call', async ($, e, next) => {
    const result = await next(e)
    try {
      const lens = await read($, lensAtom)
      // A subagent's own reads are its business. The main session's are what the band is about.
      if (!lens || result.deny || (e as { agentId?: string }).agentId) return result
      const input = e as unknown as Record<string, unknown>
      const tool = String(e.tool)
      if (tool === 'Read' && typeof input.file_path === 'string') {
        const rel = relative(input.file_path, lens.root)
        const steering = rel ? steeringName(rel, config) : null
        const skill = rel ? skillFromPath(rel, config) : null
        if (steering && !lens.always.includes(steering)) {
          await change($, l => ({ ...l, steering: remember(l.steering, { name: steering, turn: l.turn }) }))
        }
        if (skill) await change($, l => ({ ...l, skills: remember(l.skills, { name: skill, turn: l.turn }) }))
      } else if (tool === 'Bash' && typeof input.command === 'string') {
        await refreshScope($)
        const run = gateRun(input.command, String(result.text ?? ''), Boolean(result.isError), config)
        if (run) {
          await change($, l => ({ ...l, gates: record(l.gates, { ...run, turn: l.turn }) }))
          if (!run.ok) $.ui.toast(`✗ The ${run.name} gate failed`)
        }
      } else if (tool === 'Agent' && typeof input.subagent_type === 'string' && agents.includes(input.subagent_type)) {
        const name = input.subagent_type
        await change($, l => ({ ...l, reviews: remember(l.reviews, { name, turn: l.turn }) }))
      }
    } catch {}
    return result
  })

  // A reviewer the main session sent, from the moment it starts. A subagent's own spawns are its business.
  on('agent.spawn', async ($, e, next) => {
    const result = await next(e)
    try {
      const id = result.agentId
      if (id && !result.deny && e.parentAgentId === undefined) {
        await change($, l => startRun(l, id, e.subagentType, agents, Date.now()))
      }
    } catch {}
    return result
  })

  // A subagent's run ends with its own turn.complete. Only an answer is a ✓: an error, a refusal or a stop is ✗.
  on('turn.complete', async ($, e, next) => {
    const out = await next(e)
    const id = e.agentId
    if (id) await change($, l => endRun(l, id, e.reason === 'answer', Date.now())).catch(() => {})
    return out
  })

  // Drawn above the prompt, then whatever another mod draws there: two bands stack, neither hides the other.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const lens = await read($, lensAtom)
    if (!lens || e.props.hasSurvey) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const below = await next(e)
    return (
      <Box flexDirection="column">
        <Box flexWrap="wrap" columnGap={2}>
          <Text bold>◆ harness</Text>
          {bandSegments(lens, config.scope.length > 0, Date.now(), plan).map(segment => (
            <Text key={segment.label}>
              <Text dimColor>{segment.label}: </Text>
              <Text {...COLORS[segment.tone]}>{segment.text}</Text>
            </Text>
          ))}
        </Box>
        {below}
      </Box>
    )
  })
}
