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
  // When the current run began. usage.json stamps each entry with it, as run_started.
  started?: string
  // The issue's tokens and cost over every run, as loop.py totals usage.json. Only read to tell
  // when usage.json has changed.
  tokens?: number
  cost_usd?: number
}

// Each station's tokens and cost in the current run, from usage.json. Null: no entry reported one.
// The stations are logic.ts's Station, written out: this contract has to stand alone.
export type Spend = Record<'start' | 'plan' | 'test' | 'build' | 'check' | 'ship', { tokens: number | null; cost: number | null }>

export type Status = { issues: Row[] }

// One look at one loop's files.
export type Seen = {
  // The project under .loop/projects/ this loop belongs to. Unset for the harness's own.
  project?: string
  status: Status | null
  // A lock whose holder is alive: the loop is running.
  isLive: boolean
}

// One loop as the picker lists it: the root it's under, its project (unset for the harness's own), its
// status file, and whether a live process holds its lock.
export type Loop = { root: string; project?: string; status: Status | null; isLocked: boolean }

declare module 'claude-code' {
  interface PluginState {
    // launch: the folder the session started in. shown: the loop on screen, a project's name or ''
    // for the harness. seen: that loop's last look, null until the first. loops: every loop the picker
    // lists, the harness first, null until the first read.
    'loop-crew': { launch: string | null; shown: string; seen: Seen | null; loops: Loop[] | null }
  }
}
