import { describe, expect, test } from 'claude-code/testing'

import { LIMIT_MS, QUERY, SESSION, allText, due, failed, focusFile, focusName, oldFocusFile, lineFor, parseCounts, parseRemote, projectName, projectWhy, sectionText } from './logic'
import type { Counts } from '../types'

const REPO = 'SanvioLabs/sanvio-factory'
const NOW = 1_800_000_000_000
const COUNTS: Counts = { running: 2, queued: 0, pulls: 3, issues: 5 }

describe('the remote', () => {
  test('SSH remotes, with and without .git', () => {
    expect(parseRemote('git@github.com:SanvioLabs/sanvio-factory.git\n')).toBe(REPO)
    expect(parseRemote('git@github.com:SanvioLabs/sanvio-factory')).toBe(REPO)
    expect(parseRemote('ssh://git@github.com/SanvioLabs/sanvio-factory.git')).toBe(REPO)
  })
  test('HTTPS remotes, with and without .git', () => {
    expect(parseRemote('https://github.com/SanvioLabs/sanvio-factory')).toBe(REPO)
    expect(parseRemote('https://github.com/SanvioLabs/sanvio-factory.git')).toBe(REPO)
  })
  test('a remote that is not GitHub is none, so gh is never called', () => {
    expect(parseRemote('git@gitlab.com:SanvioLabs/sanvio-factory.git')).toBeNull()
    expect(parseRemote('https://github.com.evil.example/SanvioLabs/sanvio-factory')).toBeNull()
    expect(parseRemote('/Users/someone/repos/starter')).toBeNull()
    expect(parseRemote('')).toBeNull()
  })
})

describe('the answer', () => {
  const graphql = JSON.stringify({ data: { repository: { pullRequests: { totalCount: 3 }, issues: { totalCount: 5 } } } })
  test('counts read from the GraphQL answer and the two run listings', () => {
    expect(parseCounts(graphql, '{"total_count": 2, "workflow_runs": []}', '{"total_count": 1}')).toEqual({ running: 2, queued: 1, pulls: 3, issues: 5 })
  })
  test('the wrong shape is none, never a throw', () => {
    expect(parseCounts('{"errors": [{}]}', '{"total_count": 2}', '{"total_count": 0}')).toBeNull()
    expect(parseCounts(graphql, 'not json', '{"total_count": 0}')).toBeNull()
  })
  test('the query reads issues, which leaves pull requests out, and changes nothing', () => {
    expect(QUERY.startsWith('query')).toBe(true)
    expect(QUERY).not.toContain('mutation')
    expect(QUERY).toContain('issues(states: OPEN)')
  })
})

describe('the line', () => {
  test('counts', () => {
    expect(lineFor({ kind: 'counts', repo: REPO, counts: COUNTS, at: NOW }, NOW)).toEqual({
      text: `${REPO} · 2 actions running · 3 open pull requests · 5 open issues`,
      tone: 'now',
    })
  })
  test('singular at one', () => {
    const one = { running: 1, queued: 0, pulls: 1, issues: 1 }
    expect(lineFor({ kind: 'counts', repo: REPO, counts: one, at: NOW }, NOW).text).toBe(`${REPO} · 1 action running · 1 open pull request · 1 open issue`)
  })
  test('queued runs follow the running count', () => {
    const queued = { ...COUNTS, queued: 4 }
    expect(lineFor({ kind: 'counts', repo: REPO, counts: queued, at: NOW }, NOW).text).toContain('2 actions running (4 queued)')
  })
  test('reading', () => {
    expect(lineFor({ kind: 'reading', repo: REPO }, NOW)).toEqual({ text: `${REPO} · reading…`, tone: 'now' })
  })
  test('unavailable, in yellow', () => {
    const line = lineFor({ kind: 'unavailable', repo: REPO }, NOW)
    expect(line.tone).toBe('warn')
    expect(line.text).toContain('GitHub unavailable')
  })
  test('stale: the last counts, their age, in yellow', () => {
    const line = lineFor({ kind: 'stale', repo: REPO, counts: COUNTS, at: NOW - 7 * 60_000 }, NOW)
    expect(line).toEqual({ text: `${REPO} · 2 actions running · 3 open pull requests · 5 open issues · as of 7m ago`, tone: 'warn' })
  })
  test('no remote, dim', () => {
    expect(lineFor({ kind: 'no-remote' }, NOW)).toEqual({ text: 'no GitHub remote', tone: 'quiet' })
  })
  test('a failed read keeps the last counts as stale, and with none is unavailable', () => {
    expect(failed({ kind: 'counts', repo: REPO, counts: COUNTS, at: NOW }, REPO)).toEqual({ kind: 'stale', repo: REPO, counts: COUNTS, at: NOW })
    expect(failed({ kind: 'reading', repo: REPO }, REPO)).toEqual({ kind: 'unavailable', repo: REPO })
    expect(failed(null, REPO)).toEqual({ kind: 'unavailable', repo: REPO })
  })
})

describe('the limit', () => {
  test('the first read is allowed', () => {
    expect(due(null, NOW)).toBe(true)
  })
  test('a second read inside two minutes is refused', () => {
    expect(due(NOW - LIMIT_MS + 1, NOW)).toBe(false)
  })
  test('one two minutes later is allowed', () => {
    expect(due(NOW - LIMIT_MS, NOW)).toBe(true)
  })
  test('one from /github is allowed whenever', () => {
    expect(due(NOW - 1_000, NOW, true)).toBe(true)
  })
})

describe('a project name', () => {
  test('a folder under projects/, with or without the prefix', () => {
    expect(projectName('acme')).toEqual({ name: 'acme' })
    expect(projectName(' projects/acme-app/ ')).toEqual({ name: 'acme-app' })
    expect(projectName('web_2.0')).toEqual({ name: 'web_2.0' })
  })
  test('anything that could reach outside projects/ is refused', () => {
    for (const arg of ['../secrets', 'acme/sub', '/etc', '.hidden', 'projects/../x', 'a..b', '~/x', 'two words']) {
      expect('why' in projectName(arg)).toBe(true)
    }
  })
})

describe('/github all', () => {
  test('the factory first, then each project, then the folders without a remote', () => {
    expect(allText('h/r · 0 actions running', [{ name: 'acme', text: 'a/b · 1 action running' }], 2, 3)).toBe(
      'factory: h/r · 0 actions running\nacme: a/b · 1 action running\n2 folders under projects/ have no GitHub remote.')
  })
  test('one folder without a remote, and none under projects/', () => {
    expect(allText('x', [], 1, 1)).toBe('factory: x\n1 folder under projects/ has no GitHub remote.')
    expect(allText('x', [], 0, 0)).toBe('factory: x\nNo folders under projects/.')
  })
})

describe('the focus file', () => {
  test('an id matching the pattern names a file under .sanvio/project', () => {
    expect(focusFile('/h', 'aaaaaaaa-1111')).toBe('/h/.sanvio/project/aaaaaaaa-1111')
    expect(oldFocusFile('/h/.sanvio/project/aaaaaaaa-1111')).toBe('/h/.harness/project/aaaaaaaa-1111')
    expect(focusFile('/h', 'A'.repeat(64))).toBe(`/h/.sanvio/project/${'A'.repeat(64)}`)
  })
  test('anything else names none', () => {
    for (const id of [null, '', 'abc', '../../etc/passwd', 'aaaaaaaa/1111', 'g'.repeat(8), 'a'.repeat(65)]) {
      expect(focusFile('/h', id)).toBeNull()
    }
    expect(SESSION.test('aaaaaaaa\n')).toBe(false)
  })
  test('the text, trimmed, is what projectName accepts', () => {
    expect(focusName('acme\n')).toBe('acme')
    expect(focusName('  projects/acme  ')).toBe('acme')
    for (const text of ['', '  \n', '../x', 'a/b', '.hidden', 'two words']) expect(focusName(text)).toBeNull()
  })
})

describe('/project\'s words', () => {
  test('a refusal names /project and never /github', () => {
    const why = projectWhy(' ../x ')
    expect(why).toContain('"../x"')
    expect(why).toContain('/project')
    expect(why).not.toContain('/github')
  })
  test('/github\'s own refusal stays as it was', () => {
    expect(projectName('../x')).toEqual({ why: '"../x" isn\'t a project: give the name of a folder under projects/, such as /github acme, or /github all.' })
  })
  test('the section names the project', () => {
    expect(sectionText('acme')).toBe('The person has put projects/acme in focus. When they ask about the project, its pull requests, its issues or its loop without naming one, they mean projects/acme.')
  })
})

describe('the line with a project', () => {
  const project = 'acme'
  test('every state starts with the name, and keeps its tone', () => {
    expect(lineFor({ kind: 'no-remote', project }, NOW)).toEqual({ text: 'acme: no GitHub remote', tone: 'quiet' })
    expect(lineFor({ kind: 'reading', repo: REPO, project }, NOW)).toEqual({ text: `acme: ${REPO} · reading…`, tone: 'now' })
    expect(lineFor({ kind: 'counts', repo: REPO, counts: COUNTS, at: NOW, project }, NOW)).toEqual({ text: `acme: ${REPO} · 2 actions running · 3 open pull requests · 5 open issues`, tone: 'now' })
    expect(lineFor({ kind: 'unavailable', repo: REPO, project }, NOW).text).toBe(`acme: ${REPO} · GitHub unavailable (is gh installed and signed in?)`)
    const stale = lineFor({ kind: 'stale', repo: REPO, counts: COUNTS, at: NOW - 60_000, project }, NOW)
    expect(stale).toEqual({ text: `acme: ${REPO} · 2 actions running · 3 open pull requests · 5 open issues · as of 1m ago`, tone: 'warn' })
  })
  test('a failed read keeps counts only for the same repo and the same project', () => {
    const counts = { kind: 'counts', repo: REPO, counts: COUNTS, at: NOW, project } as const
    expect(failed(counts, REPO, 'acme')).toEqual({ kind: 'stale', repo: REPO, counts: COUNTS, at: NOW, project })
    expect(failed(counts, REPO, 'beta')).toEqual({ kind: 'unavailable', repo: REPO, project: 'beta' })
    expect(failed(counts, REPO)).toEqual({ kind: 'unavailable', repo: REPO })
    expect(failed(counts, 'other/repo', 'acme')).toEqual({ kind: 'unavailable', repo: 'other/repo', project })
  })
})
