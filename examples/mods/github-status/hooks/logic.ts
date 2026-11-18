// The decisions, as pure functions. register.tsx runs git and gh and draws the line, then calls in here,
// because the test kit can't stand in for a process.

import type { Counts, GitHubState } from '../types'

// At most one read of GitHub per repo in this long, unless the person asks with /github.
export const LIMIT_MS = 2 * 60_000

const PART = '[A-Za-z0-9_.-]+'
const REMOTES = [
  new RegExp(`^git@github\\.com:(${PART})/(${PART}?)(?:\\.git)?/?$`),
  new RegExp(`^ssh://git@github\\.com(?::\\d+)?/(${PART})/(${PART}?)(?:\\.git)?/?$`),
  new RegExp(`^https://(?:[^@/]+@)?github\\.com/(${PART})/(${PART}?)(?:\\.git)?/?$`),
]

// `owner/name` for a github.com remote, over SSH or HTTPS. Anything else is none, and gh is never called.
export function parseRemote(url: string): string | null {
  const text = url.trim()
  for (const pattern of REMOTES) {
    const match = text.match(pattern)
    const owner = match?.[1]
    const name = match?.[2]
    if (!owner || !name || [owner, name].some(part => part === '.' || part === '..')) continue
    return `${owner}/${name}`
  }
  return null
}

// The GraphQL read, a query and never a mutation. issues(states: OPEN) leaves pull requests out.
export const QUERY =
  'query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { pullRequests(states: OPEN) { totalCount } issues(states: OPEN) { totalCount } } }'

function json(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

const count = (value: unknown): number | null => (typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null)

// The counts from the GraphQL answer and the two workflow-run listings. None when any is the wrong shape.
export function parseCounts(graphqlJson: string, runningJson: string, queuedJson: string): Counts | null {
  const repo = (json(graphqlJson) as { data?: { repository?: Record<string, { totalCount?: unknown } | undefined> } } | null)?.data?.repository
  const pulls = count(repo?.pullRequests?.totalCount)
  const issues = count(repo?.issues?.totalCount)
  const running = count((json(runningJson) as { total_count?: unknown } | null)?.total_count)
  const queued = count((json(queuedJson) as { total_count?: unknown } | null)?.total_count)
  if (pulls === null || issues === null || running === null || queued === null) return null
  return { running, queued, pulls, issues }
}

// Whether a read may start: the first one, one two minutes after the last, or one the person asked for.
export function due(lastAttempt: number | null, now: number, isAsked = false): boolean {
  return isAsked || lastAttempt === null || now - lastAttempt >= LIMIT_MS
}

// A read that failed keeps the last counts, marked stale, when they're for this repo and this focus.
// With none to keep, GitHub is unavailable.
export function failed(state: GitHubState | null, repo: string, project?: string): GitHubState {
  const tag = project ? { project } : {}
  return state && (state.kind === 'counts' || state.kind === 'stale') && state.repo === repo && state.project === project
    ? { kind: 'stale', repo, counts: state.counts, at: state.at, ...tag }
    : { kind: 'unavailable', repo, ...tag }
}

export type Tone = 'quiet' | 'now' | 'warn'
export type Line = { text: string; tone: Tone }

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

// How often the wave moves on. A band redraws ten times a second at most.
export const FRAME_MS = 100
// How far the wave's crest moves a frame, in cells, and how far either side of it a cell still glows.
const SPEED = 0.75
const HALF_WIDTH = 4.5
// Frames the text rests unlit between waves.
const REST_FRAMES = 8
// The brightest shade, at the crest. 0 is the line's own color.
export const SHADES = 5

// How bright each of `length` cells is at frame n, from 0 to SHADES: a soft wave whose crest flows left to
// right, so each cell fades in as it nears and back out once it's past, then the text rests unlit.
export function wave(length: number, frame: number): number[] {
  const crossing = Math.ceil((length + 2 * HALF_WIDTH) / SPEED)
  const cycle = crossing + REST_FRAMES
  const n = ((Math.floor(frame) % cycle) + cycle) % cycle
  if (n >= crossing) return Array<number>(length).fill(0)
  const crest = n * SPEED - HALF_WIDTH
  return Array.from({ length }, (_, i) => {
    const away = Math.abs(i - crest)
    return away >= HALF_WIDTH ? 0 : Math.round((SHADES * (1 + Math.cos((Math.PI * away) / HALF_WIDTH))) / 2)
  })
}

export type Scheme = 'dark' | 'light'

// Whether the person's theme setting is a dark or a light one. Anything else, such as auto, is neither.
export function schemeOf(value: unknown): Scheme | null {
  if (typeof value !== 'string') return null
  return value.startsWith('dark') ? 'dark' : value.startsWith('light') ? 'light' : null
}

// Cyan up to white on a dark theme, and up to deep teal on a light one, a step a shade.
const RAMPS: Record<Scheme, readonly string[]> = {
  dark: ['#6fd9e6', '#94e3ee', '#b8edf4', '#dcf6fa', '#ffffff'],
  light: ['#137f8c', '#0f6874', '#0b525c', '#073c44', '#03262c'],
}

// How a cell at `level` is drawn. 0 is the line's own color. Without a theme to go on, two bold steps that
// show on any terminal: cyan, then the theme's own text color.
export function shade(level: number, scheme: Scheme | null): { color?: string; bold?: boolean } {
  if (level <= 0) return {}
  const top = Math.min(level, SHADES)
  if (!scheme) return { color: top < 3 ? 'cyan' : 'text', bold: true }
  return { color: RAMPS[scheme][top - 1]!, ...(top >= 3 ? { bold: true } : {}) }
}

// Whether the line shows actions running now: fresh counts with one in progress. Stale counts don't
// animate, since nobody knows they're still running.
export function isRunning(state: GitHubState | null): boolean {
  return state?.kind === 'counts' && state.counts.running > 0
}

const runningText = (c: Counts) => `${plural(c.running, 'action', 'actions')} running`

function countsText(repo: string, c: Counts): string {
  const actions = `${runningText(c)}${c.queued ? ` (${c.queued} queued)` : ''}`
  return `${repo} · ${actions} · ${plural(c.pulls, 'open pull request', 'open pull requests')} · ${plural(c.issues, 'open issue', 'open issues')}`
}

function age(ms: number): string {
  const minutes = Math.max(0, Math.floor(ms / 60_000))
  return minutes < 60 ? `${minutes}m` : `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

// The line above the prompt, after its `◆ github` label. A project in focus starts it in every state.
export function lineFor(state: GitHubState, now: number): Line {
  const line = plainLine(state, now)
  return state.project ? { ...line, text: `${state.project}: ${line.text}` } : line
}

function plainLine(state: GitHubState, now: number): Line {
  switch (state.kind) {
    case 'no-remote':
      return { text: 'no GitHub remote', tone: 'quiet' }
    case 'reading':
      return { text: `${state.repo} · reading…`, tone: 'now' }
    case 'counts':
      return { text: countsText(state.repo, state.counts), tone: 'now' }
    case 'unavailable':
      return { text: `${state.repo} · GitHub unavailable (is gh installed and signed in?)`, tone: 'warn' }
    case 'stale':
      return { text: `${countsText(state.repo, state.counts)} · as of ${age(now - state.at)} ago`, tone: 'warn' }
  }
}

// The folder under projects/ that a /github argument names: `acme` or `projects/acme`, one folder deep.
// Anything that could reach outside projects/ is refused before anything runs.
export function projectName(arg: string): { name: string } | { why: string } {
  const name = arg.trim().replace(/^projects\//, '').replace(/\/$/, '')
  if (/^[A-Za-z0-9_][A-Za-z0-9_.-]*$/.test(name) && !name.includes('..')) return { name }
  return { why: `"${arg.trim()}" isn't a project: give the name of a folder under projects/, such as /github acme, or /github all.` }
}

// A session id that can name a file: harness-lens's rule. Anything else means no focus.
export const SESSION = /^[0-9a-fA-F-]{8,64}$/

// This session's focus file under the harness root, or null for an id that can't name one.
export function focusFile(root: string, id: string | null): string | null {
  return id !== null && SESSION.test(id) ? `${root}/.sanvio/project/${id}` : null
}

// The project a focus file's text names, before the folder is checked, or null.
export function focusName(text: string): string | null {
  const picked = projectName(text.trim())
  return 'name' in picked ? picked.name : null
}

// Why /project refused a name, in its own words.
export function projectWhy(arg: string): string {
  return `"${arg.trim()}" can't go in focus: give the name of a folder under projects/, such as /project acme, or /project off to clear the focus.`
}

// What the model reads while a project is in focus.
export function sectionText(name: string): string {
  return `The person has put projects/${name} in focus. When they ask about the project, its pull requests, its issues or its loop without naming one, they mean projects/${name}.`
}

// The line in pieces at frame n, each with how bright it is: the wave flows across `2 actions running` while
// fresh counts have an action in progress, and the pieces always read as lineFor's text. Anything else is
// one unlit piece.
export function sweepLine(state: GitHubState, now: number, frame: number): { text: string; glow: number }[] {
  const text = lineFor(state, now).text
  if (state.kind !== 'counts' || !isRunning(state)) return [{ text, glow: 0 }]
  const phrase = runningText(state.counts)
  const at = text.indexOf(phrase)
  if (at < 0) return [{ text, glow: 0 }]
  const glows = [...Array<number>(at).fill(0), ...wave(phrase.length, frame), ...Array<number>(text.length - at - phrase.length).fill(0)]
  const pieces: { text: string; glow: number }[] = []
  glows.forEach((glow, i) => {
    const last = pieces[pieces.length - 1]
    if (last && last.glow === glow) last.text += text[i]
    else pieces.push({ text: text[i] ?? '', glow })
  })
  return pieces
}

// What /github all prints: the factory's line, each project's in name order, then the folders it couldn't read.
export function allText(factory: string, projects: { name: string; text: string }[], withoutRemote: number, folders: number): string {
  const lines = [`factory: ${factory}`, ...projects.map(p => `${p.name}: ${p.text}`)]
  if (folders === 0) lines.push('No folders under projects/.')
  else if (withoutRemote > 0) {
    lines.push(`${withoutRemote} ${withoutRemote === 1 ? 'folder' : 'folders'} under projects/ ${withoutRemote === 1 ? 'has' : 'have'} no GitHub remote.`)
  }
  return lines.join('\n')
}
