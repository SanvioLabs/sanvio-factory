# GitHub status

Whether a pull request is waiting or a workflow is still running lives on
GitHub, a browser tab away from the session. This mod draws one line above the
prompt with the repo's running actions, open pull requests and open issues:

```
◆ github  SanvioLabs/sanvio-harness-starter · 1 action running (2 queued) · 3 open pull requests · 5 open issues
```

It's a Claude Code mod, so it works in Claude Code only: it was seen working in
the terminal, the VS Code extension and Claude Desktop's Code tab on
2026-10-23, with Claude Code 2.1.309. It was built on
Claude Code 2.1.301. Codex and Kiro don't have mods.

## Turn it on

It loads by itself, the same way as the [harness lens](../harness-lens/): the harness's
[`.claude/settings.json`](../../../.claude/settings.json) turns it on. Don't see the line? Install it from
inside a session, at the root:

```
/plugin marketplace add ./
/plugin install github-status@sanvio-harness-starter
```

It's active as soon as the install says so, no restart. Or load it for one
session with `claude --plugin-dir examples/mods/github-status`.

A change to what the mod does raises `version` in its [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json), because `/plugin update` keeps an installed copy whose version hasn't changed, and CI checks this on every pull request with [`scripts/check_mod_versions.py`](../../../scripts/check_mod_versions.py).

It reads GitHub through the [`gh`](https://cli.github.com/) command line, so
`gh` has to be installed and signed in (`gh auth status` says).

To turn it off just for you:

```bash
claude plugin disable github-status@sanvio-harness-starter --scope local
```

## Reading the line

| The line says | Means |
|---|---|
| `owner/name · reading…`, cyan | The first read of GitHub is under way |
| `owner/name · 2 actions running (1 queued) · 3 open pull requests · 5 open issues`, cyan | What the last read found. Actions are workflow runs in progress, and the queued count shows only when there is one. Issues don't include pull requests |
| `… · as of 7m ago`, yellow | The last read failed, so these are the counts from the one before, and how old they are |
| `owner/name · GitHub unavailable (is gh installed and signed in?)`, yellow | No read has worked yet this session. `gh` is missing, signed out, offline, or can't see the repo |
| `no GitHub remote`, dim | The session's folder has no `origin` remote on github.com, so the mod never calls `gh`. With a project in focus it's `<name>: no GitHub remote`: that project's folder has no GitHub `origin`, and `gh` isn't called for it |

While a project is in focus (see *Your projects*), every row is about that
project's repo and starts with its name: `acme: acme/app · reading…`, or
`notes: no GitHub remote` for a folder with no GitHub `origin`.

`/github` reads GitHub straight away and prints the line.

## Your projects

The line is the harness's repo, unless you put a project in focus. Then it's
that project's `origin` repo, with `<name>: ` at the start. Repos cloned under
[`projects/`](../../../projects/) are read with these commands, from a session at the harness root:

| Type | Does |
|---|---|
| `/github acme` (or `/github projects/acme`) | Prints the line for the repo cloned in `projects/acme`, read now |
| `/github all` | Prints the harness's line, then one per folder under [`projects/`](../../../projects/) with a GitHub `origin`, in name order, then how many folders have none |
| `/project <name>` (or `/project projects/<name>`) | Puts that project in focus and prints its line, read now |
| `/project off` | Clears the focus, and the line shows the harness again |
| `/project` | Prints the project in focus, or that there's none |

```
harness: SanvioLabs/sanvio-harness-starter · 0 actions running · 2 open pull requests · 5 open issues
acme: acme/app · 1 action running · 4 open pull requests · 12 open issues
1 folder under projects/ has no GitHub remote.
```

A name is one folder directly under [`projects/`](../../../projects/). Anything that could reach
outside it, such as `../x`, `a/b` or a leading `.`, is refused before anything
runs. A folder with no GitHub `origin` says so and `gh` isn't called. A repo
whose read fails says GitHub is unavailable on its own line, and the others
still print. `/github <name>` and `/github all` never change the line above
the prompt, and `/github all`'s `harness:` line is the harness's own repo
whatever is in focus. `/github` alone reads the repo in focus.

The focus is the session's own, so another session's line doesn't move, and a
`/clear` drops it, because the new session has a new id. It lives in the file
`.harness/project/<id>`, under the harness root, where `<id>` is the session's
id. An id that doesn't match `^[0-9a-fA-F-]{8,64}$` means no focus, and nothing
is read or written.

The file's text, trimmed, is the project in focus when it's a name `/github`
would accept and `projects/<name>` is a real folder, not a link. Anything else
is no focus: an empty or whitespace-only file, a missing or unreadable one, or
text naming something `projectName` refuses or that isn't such a folder. The
timer reads the file every 15 seconds, so a focus another tool writes there
shows on the next tick, and reads that repo straight away even inside the
two-minute limit. A read that's still under way for a repo that's left focus
is dropped.

While a project is in focus, the mod also tells the model, in one section of
the system prompt, that a question about the project, its pull requests, its
issues or its loop means that project unless another is named.

## What it doesn't do

It writes `.harness/project/<id>` and nothing else, and it never changes
anything on GitHub. One file is left behind for each session that used
`/project`, because the mod doesn't delete them. When the session starts it
runs `git remote get-url origin` in the folder the session started in (and,
for `/github <name>`, `/github all` or a project in focus, in each folder under
[`projects/`](../../../projects/) it reads), and on a github.com remote, at most once every two
minutes, it makes three reads through `gh`, each with a time limit:

- `gh api graphql` with a query (never a mutation) for the open pull request
  and open issue counts
- `gh api --method GET repos/owner/name/actions/runs`, once for runs in
  progress and once for queued ones

`/github` and `/project <name>` read whenever you type them, and a focus that
changes reads straight away. Drawing the line never calls `gh`. A read that
fails, for any reason, shows as unavailable or stale and stops nothing.

The line shows the repo the session started in, from its `origin` remote, or
while a project is in focus, that project's `origin` repo with `<name>: ` at
the start. A focused folder with no GitHub `origin` shows
`<name>: no GitHub remote`, and `gh` isn't called for it. Other repos are read
only through `/github <name>` and `/github all`, from folders under [`projects/`](../../../projects/).
It doesn't choose another remote, list workflows one by one, or link to GitHub.

## Changing it

[`hooks/logic.ts`](hooks/logic.ts) holds the decisions as plain functions, so they can be tested.
[`hooks/register.tsx`](hooks/register.tsx) runs `git` and `gh` and draws the line. From
[`examples/mods/`](../):

```bash
claude plugin validate github-status
claude plugin test github-status
```

`python3 -m unittest discover -s tests`, and so the loop, runs these wherever Claude Code is installed. CI doesn't install Claude Code, so it skips them.
