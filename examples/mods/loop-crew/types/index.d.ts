// The part of what scripts/loop.py writes to status.json that the figures draw from.
// step_seconds and step_started are there only when the loop that wrote the row records them.
export type Row = {
  number: number
  title: string
  step: string
  state: string
  round: number
  // Whole seconds spent on each step in the current run, by step name.
  step_seconds?: Record<string, number>
  // When the current step began, as loop.py writes it, or null once the row has left working.
  step_started?: string | null
}

export type Status = { issues: Row[] }

// One look at one loop's files.
export type Seen = {
  // The project under .loop/projects/ this loop belongs to. Unset for the harness's own.
  project?: string
  status: Status | null
  // A lock whose holder is alive: the loop is running.
  isLive: boolean
}

declare module 'claude-code' {
  interface PluginState {
    // launch: the folder the session started in. shown: the loop on screen, a project's name or ''
    // for the harness. seen: that loop's last look, null until the first.
    'loop-crew': { launch: string | null; shown: string; seen: Seen | null }
  }
}
