import type { ButtonProps, ElementConstructor, EngineInterface, RenderElement } from 'claude-code'

import { attach, isWebLink, jobAttach, jobWatchFile, watch, watchCommand } from './logic'
import type { Row, Seen } from '../types'

// The buttons on a loop and on an issue, the one copy the List and the Crew both draw, so a person can
// watch the loop or open a pull request from either view.

type Button = ElementConstructor<ButtonProps>
type Surface = Parameters<EngineInterface['ui']['copy']>[0]['surface']

// What a row of buttons is: their labels, which say how wide the terminal draws them, and the buttons.
export type Buttons = { labels: string[]; elements: RenderElement[] }

// A watch file opens a read-only Terminal window; closing it leaves the loop running. When it can't
// open, the buttons copy the command that does the same.
export const WATCH_TOAST = "Couldn't open a window, so the read-only attach command is copied"

// Open a target with the first opener that works; when none does, copy what stands in for it and say
// so. A rejected run counts as that opener failing, so a missing `open` still reaches the next.
export function openOrCopy($: EngineInterface, target: string, openers: string[], copy: () => Promise<unknown>, toast: string): void {
  void (async () => {
    for (const opener of openers) {
      const ran = await $.process.run([opener, target]).catch(() => null)
      if (ran?.exitCode === 0) return
    }
    await copy()
    $.ui.toast(toast)
  })().catch(() => {})
}

// Open a job's pull request in the browser. A link that isn't a web link reaches no opener, since
// `open` would run a local file or app: it's only copied.
export function openPullRequest($: EngineInterface, link: string, surface: Surface): void {
  const copy = () => $.ui.copy({ text: link, surface })
  if (!isWebLink(link)) openOrCopy($, link, [], copy, "That pull request link isn't a web link, so it's copied")
  else openOrCopy($, link, ['open', 'xdg-open'], copy, "Couldn't open the browser, so the pull request link is copied")
}

// Watch it and Copy attach command, while the loop runs in tmux. None otherwise.
export function loopButtons($: EngineInterface, Button: Button, seen: Seen): Buttons {
  const tmux = attach(seen)
  const watchFile = watch(seen)
  const out: Buttons = { labels: [], elements: [] }
  if (tmux && watchFile) {
    out.labels.push('Watch it')
    out.elements.push(
      <Button
        key="watch"
        label="Watch it"
        onPress={press =>
          openOrCopy($, watchFile, ['open'], () => $.ui.copy({ text: watchCommand(seen) ?? '', surface: press.surface }), WATCH_TOAST)}
      />,
    )
  }
  if (tmux) {
    out.labels.push('Copy attach command')
    out.elements.push(<Button key="tmux" label="Copy attach command" onPress={press => $.ui.copy({ text: tmux, surface: press.surface })} />)
  }
  return out
}

// Watch, while the issue has its own tmux window, and Open pull request, once it has one. prLabel is
// the pull request button's label, which the List cuts to its width.
export function issueButtons($: EngineInterface, Button: Button, seen: Seen, row: Row, prLabel = 'Open pull request'): Buttons {
  const jobCommand = jobAttach(seen, row)
  const out: Buttons = { labels: [], elements: [] }
  if (jobCommand) {
    out.labels.push('Watch')
    out.elements.push(
      <Button
        key={`watch-${row.number}`}
        label="Watch"
        onPress={press =>
          openOrCopy($, `${seen.root}/${jobWatchFile(row.number, seen.project)}`, ['open'], () =>
            $.ui.copy({ text: jobCommand, surface: press.surface }), WATCH_TOAST)}
      />,
    )
  }
  if (row.pr) {
    out.labels.push(prLabel)
    out.elements.push(<Button key={`pr-${row.number}`} label={prLabel} onPress={press => openPullRequest($, row.pr ?? '', press.surface)} />)
  }
  return out
}

// How many columns a row of these buttons takes on the terminal, which draws each as `[ label ]`, one
// column apart. None take none.
export function buttonsWidth(labels: string[]): number {
  return labels.reduce((sum, label) => sum + [...label].length + 4, 0) + Math.max(0, labels.length - 1)
}

// How many rows a wrapping row of these buttons takes in `columns`: each goes on the row it fits on,
// else starts the next. One at the least, since the row is drawn either way.
export function buttonRows(labels: string[], columns: number): number {
  let rows = 1
  let used = 0
  for (const label of labels) {
    const width = buttonsWidth([label])
    if (used > 0 && used + 1 + width > columns) {
      rows += 1
      used = width
    } else {
      used += (used > 0 ? 1 : 0) + width
    }
  }
  return rows
}
