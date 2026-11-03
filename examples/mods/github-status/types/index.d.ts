// What one read of GitHub found: workflow runs in progress and queued, open pull requests, open issues.
export type Counts = { running: number; queued: number; pulls: number; issues: number }

// The line's state. `repo` is `owner/name`, from the origin remote of the session's folder or of the
// project in focus. `project` names that project, and the line then starts with it. `at` is when the
// counts were read, in milliseconds. Stale is a later read that failed: the last counts, with their age.
export type GitHubState =
  | { kind: 'no-remote'; project?: string }
  | { kind: 'reading'; repo: string; project?: string }
  | { kind: 'counts'; repo: string; counts: Counts; at: number; project?: string }
  | { kind: 'unavailable'; repo: string; project?: string }
  | { kind: 'stale'; repo: string; counts: Counts; at: number; project?: string }

declare module 'claude-code' {
  interface PluginState {
    // `attempt` is when the last read of GitHub began, so a reload doesn't read again early.
    // `focus` is the project last read from or written to this session's file, so a tick can see it change.
    'github-status': { launch: string | null; status: GitHubState | null; attempt: number | null; focus: string | null }
  }
}
