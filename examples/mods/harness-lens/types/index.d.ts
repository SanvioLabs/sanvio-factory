// One thing seen: a steering file read, a skill followed, a gate run, a tool a guard refused, a reviewer.
// `turn` is the session's turn it happened in, so the band can tell this turn from earlier ones.
export type Hit = { name: string; turn: number }
export type GateHit = Hit & { ok: boolean }

// The harness's declared scope for this session: a client its guard enforces, or a project or area it
// only names. Read from the files `scope` lists in .claude/harness-lens.json; this repo declares none.
export type Scope = { kind: string; name: string }

// One of the harness's agents the main session sent to work, by the subagent id its spawn answered.
// `started` and `ended` are milliseconds; `ok` is false when it ended in an error, a refusal or a stop,
// and unset when it ended without the lens seeing how, as during a reload.
// `turn` is the main session's turn it ended in, so its ✓ or ✗ stands out only that turn.
export type Run = { id: string; name: string; started: number; ended?: number; ok?: boolean; turn?: number }

export type Lens = {
  root: string
  turn: number
  always: string[]
  steering: Hit[]
  skills: Hit[]
  gates: GateHit[]
  // The tool a guard refused, never its reason: a reason can name a file or a customer.
  refusals: Hit[]
  reviews: Hit[]
  // A lens saved before runs were kept has none, so every reader takes `lens.runs ?? []`.
  runs: Run[]
  scope: Scope | null
  // The headless sessions running, by `running` label, from the last `ps` that answered. None before the
  // first, and a label with none running is left out.
  sessions?: Record<string, number>
}

declare module 'claude-code' {
  interface PluginState {
    'harness-lens': { launch: string | null; lens: Lens | null }
  }
}
