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

function countsText(repo: string, c: Counts): string {
  const actions = `${plural(c.running, 'action', 'actions')} running${c.queued ? ` (${c.queued} queued)` : ''}`
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

// What /github all prints: the factory's line, each project's in name order, then the folders it couldn't read.
export function allText(factory: string, projects: { name: string; text: string }[], withoutRemote: number, folders: number): string {
  const lines = [`factory: ${factory}`, ...projects.map(p => `${p.name}: ${p.text}`)]
  if (folders === 0) lines.push('No folders under projects/.')
  else if (withoutRemote > 0) {
    lines.push(`${withoutRemote} ${withoutRemote === 1 ? 'folder' : 'folders'} under projects/ ${withoutRemote === 1 ? 'has' : 'have'} no GitHub remote.`)
  }
  return lines.join('\n')
}
