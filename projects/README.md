# Projects

Your code repos live here, inside the harness, so every one of them works
under the same rules, skills, gates and guards. Each folder is its own git
clone. This repo tracks nothing in this folder except this file.

```bash
cd projects
git clone <your repo>        # or several
cd ..                         # then start your agent from the harness root
```

![Your factory on disk. my-factory/ is one git repo, the factory: AGENTS.md, steering/ and skills/ hold the rules and skills, agents/ and .claude/hooks/ the reviewers and guards. projects/ is ignored by the factory, and holds billing/ and website/, each its own repo with its own history and CI. Start the agent in my-factory/: it loads the rules, skills, reviewers and guards, then point it at the work, "in projects/billing, fix the failing test". Not in my-factory/projects/billing/: it finds CLAUDE.md in the folder above, but no skills, no reviewers and no guards, and nothing tells you. Commit inside each project: the factory's repo never sees your code, and each project keeps its own hooks and CI.](../docs/projects-layout.png)

## Start the agent at the harness root, not in the project

Then point it at the project: "in projects/billing, fix the failing test".

This matters more than it looks. We tested Claude Code started inside
`projects/<repo>`: it reads the harness's [`CLAUDE.md`](../CLAUDE.md) from the folder above,
but not the [`AGENTS.md`](../AGENTS.md) that file imports, and **none of the harness's
skills, agents or hooks**. No rules, no `/orientation`, no `review-pr`, no
credential guard, and nothing tells you so. [`CLAUDE.md`](../CLAUDE.md) carries one warning
outside the import for exactly this, so the agent says so out loud.

In Kiro, open the harness root as the workspace, for the same reason.

## Why `.ignore` is at the root

This folder is gitignored so this repo never commits your code. Search
tools skip gitignored folders, and Claude Code's Grep did: started at the
root, it found nothing under [`projects/`](./) until [`.ignore`](../.ignore) said to look. Leave
that file in place.

## What each project keeps for itself

- **Its own instructions.** A project's own `AGENTS.md` or `CLAUDE.md` adds
  what's specific to it: how to run it, its architecture, its quirks. It adds
  to the harness's rules and never loosens one.
- **Its own git hooks and CI.** Each project is a separate repo, so the
  harness's [`.githooks/pre-commit`](../.githooks/pre-commit) doesn't run on its commits. Wire the
  project's own checks there, and in its own pipeline.
  [`examples/ci/project-checks.yml`](../examples/ci/project-checks.yml) is a CI file to start from.
- **Its own history.** Commit and push inside the project folder. This repo
  never sees the project's files.

## The loop on a project

[`scripts/loop.py`](../scripts/loop.py) works a project's issues when you give it `--project`,
started from the harness root:

```bash
python3 scripts/loop.py run --project projects/billing
python3 scripts/loop.py stop --project projects/billing
```

The project needs a `loop.json` of its own that sets `test_command`, since the
default tests this repo. For a TypeScript project:

```json
{"test_command": "npm test"}
```

or `node --test` with no `package.json` script. The project's `loop.json` may
set only `test_command`, `test_timeout`, `base`, `ready_label`, `blocked_label`,
`generate_command` and `setup_command`. Every other key (`agent`, `max_workers`, `allow_lockfile_changes`
and the rest) belongs to the factory's `loop.json`, under `"projects"` for one
project, and a project's own file that sets one is refused:

```json
{"projects": {"billing": {"agent": "claude", "max_workers": 2}}}
```

Its `base`, `main` unless it
says otherwise, is where branches start and pull requests go. The clone has to
sit directly in this folder and have its `origin` on GitHub, or the loop
refuses it before it starts. Its state goes in this repo, in
`.loop/projects/billing/`, never in the project's folder. Its checkouts go in
`~/.sanvio-loop/<factory>/billing/`. Its agents get the harness's rules in
their prompts, and a `claude` build agent runs the harness's credential guard.
A `codex` build agent builds without that guard.
[`HOW-IT-WORKS.md`](../HOW-IT-WORKS.md) has the rest.

## One factory, many developers

One person owns the factory and merges changes to it: new rules, skills,
gates. Everyone else clones the factory, clones their projects into this
folder, and pulls the factory to get what's new. A skill someone writes for
themselves goes to the owner as a pull request, so it reaches everyone instead
of living in one person's `~/.claude/skills`.
