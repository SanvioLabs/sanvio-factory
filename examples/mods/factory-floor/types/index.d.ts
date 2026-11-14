// What scripts/loop.py writes to .loop/status.json. Every field is optional here: an older or
// half-written file still draws, with what it has.
// waiting_on: the open issues it depends on, while the loop waits for them to close.
export type QueueItem = { number: number; title: string; waiting_on?: number[] }

export type Row = {
  number: number
  title: string
  step: string
  state: string
  round: number
  max_rounds?: number
  tests: string | null
  review: string | null
  pr: string | null
  note: string
  // When this run of the issue began, in local time. An older loop.py doesn't write it. usage.json
  // stamps each entry with it, as run_started.
  started?: string
  updated?: string
  // Totals over every run of the issue. A loop.py older than #179 doesn't write them.
  tokens?: number
  cost_usd?: number
  // The model the issue's latest agent run used. A loop.py older than #257 doesn't write it.
  model?: string
  // The issue's tmux window, issue-N, while it's open.
  window?: string
  // Whole seconds spent on each step in the current run, by step name. There only when the loop that
  // wrote the row records it.
  step_seconds?: Record<string, number>
  // When the current step began, as loop.py writes it, or null once the row has left working. There
  // only when the loop that wrote the row records it.
  step_started?: string | null
}

export type Status = {
  running: boolean
  updated: string | null
  // The tmux session a running loop is in, when it was started in one.
  tmux: string | null
  // When the running loop started, in UTC with its offset. An older loop.py doesn't write it.
  started?: string | null
  queue: QueueItem[]
  issues: Row[]
}

// What the pane draws from: the status file, plus whether the lock and a stop request are there.
export type Seen = {
  root: string
  // The project under .loop/projects/ this loop belongs to. Unset for the factory's own.
  project?: string
  status: Status | null
  // A lock whose process is alive: the loop is running.
  isLocked: boolean
  // A lock left by a process that's gone: the last run was killed. The next run replaces it.
  isStaleLock: boolean
  isStopping: boolean
  // The loop's watch.command is there: loop.py wrote it, on macOS inside tmux, for the Watch it button.
  hasWatchFile: boolean
}

// Which tab the pane shows, and the first job of its list in view. Null until the person picks a tab.
export type Tab = 'queue' | 'active' | 'finished'
export type View = { tab: Tab; start: number }

// Which view the pane draws: the List of tabs, or the Crew's lanes.
export type Mode = 'list' | 'crew'

declare module 'claude-code' {
  interface PluginState {
    // seen: the loop on screen. loops: every loop's last look, the factory first. picked: the loop to
    // show, a project's name or '' for the factory, null until the pane has opened on one. focus: the
    // project last read from this session's .sanvio/project/<id>, or null, so a read can see it change.
    // mode: the view the person picked. The crew- keys are the Crew view's own, as loop-crew keeps them:
    // crew-shown the loop it shows, crew-seen that loop's last look, crew-loops every loop its picker
    // lists, crew-focus the focus as it last read it. Both views look at a loop the same way, as a Seen.
    // The Crew view shares launch with the List.
    'factory-floor': {
      launch: string | null; seen: Seen | null; view: View | null; loops: Seen[] | null; picked: string | null; focus: string | null
      mode: Mode
      'crew-shown': string; 'crew-seen': Seen | null; 'crew-loops': Seen[] | null; 'crew-focus': string | null
    }
  }
}

// Each station's tokens and cost in the current run, from usage.json. Null: no entry reported one.
// The stations are crew-logic.ts's Station, written out: this contract has to stand alone.
export type CrewSpend = Record<'discover' | 'shape' | 'test' | 'build' | 'validate' | 'scale', { tokens: number | null; cost: number | null }>
