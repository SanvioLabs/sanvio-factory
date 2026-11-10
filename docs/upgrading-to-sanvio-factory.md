# Upgrading to Sanvio Factory

For anyone whose copy was taken before 2026-11-08, when this repo was
`SanvioLabs/sanvio-harness-starter`. It's now `SanvioLabs/sanvio-factory`, and
the names inside it changed with it. This page puts the 2026-11-08 rename
entries in [`CHANGELOG.md`](../CHANGELOG.md) into one order, for taking them together.

The factory is the repo you own and everything that runs between sessions, so
the names that mean the whole repo changed. The harness is what one agent
session works inside, so harness-lens, the harness root and the review
workflow's `harness/` checkout keep their names.

**The old names no longer work.** Nothing reads `.harness/`, a `HARNESS_`
variable, `bin/harness` or the old home folders any more, so do every step
below in one sitting when you take the rename. Two old switches still count,
because each only ever makes things stricter: `HARNESS_HEADLESS=1` keeps a run
headless, and `HARNESS_USAGE_LOG=off` keeps the usage log off.

One thing is already broken before you pull: a product repo whose CI runs the
review workflow straight from the public repo, as
`SanvioLabs/sanvio-harness-starter/...@main` or
`SanvioLabs/sanvio-factory/...@main`, has been failing since 2026-11-08. Fix
those callers first, with step 9.

## What changed

| Old | New |
|---|---|
| `SanvioLabs/sanvio-harness-starter` | `SanvioLabs/sanvio-factory`. GitHub redirects the old address |
| `.harness/` | `.sanvio/`, moved for you by the next session (step 3) |
| `HARNESS_PULSE_FOLDER`, `HARNESS_RETRO`, `HARNESS_USAGE_LOG`, `HARNESS_EVALS_HOME` | `SANVIO_` with the same ending |
| `bin/harness` | [`bin/factory`](../bin/factory) |
| `bin/harness-tools` | [`bin/factory-tools`](../bin/factory-tools) |
| `~/.harness-loop/`, `~/.harness-evals/` | `~/.sanvio-loop/`, `~/.sanvio-evals/` |
| Marketplace `sanvio-harness-starter` | `sanvio-factory` |
| `harness-dashboard` mod, `/harness-dashboard` | `factory-dashboard`, `/factory-dashboard` |
| The dashboard's `Harness` column, and the key `harness` in [`scripts/dashboard_data.py`](../scripts/dashboard_data.py)'s output | `Factory`, and `factory` |
| `harness-trends` skill, "harness trends", "my harness report" | `factory-trends`, "factory trends", "my factory report" |
| The pulse chip `Harness` | `Factory`. The sprint report no longer counts votes cast under the old chip, so take this between sprints if you can |
| `/github all`'s `harness:` line | `factory:` |
| `scripts/eval_harness.py`, `--harness` | [`scripts/eval_factory.py`](../scripts/eval_factory.py), `--factory` |
| Eval runs in `.sanvio/harness-evals/`, the result's `harness_commit` and the scorecard's `Harness` row | `.sanvio/factory-evals/`, `factory_commit` and `Factory` |
| `docs/harness-in-ci.md`, `docs/harness-evals.md` | [`docs/factory-in-ci.md`](factory-in-ci.md), [`docs/factory-evals.md`](factory-evals.md) |
| CI input `harness-repo`, secret `HARNESS_DEPLOY_KEY` | `factory-repo`, `FACTORY_DEPLOY_KEY` |
| [`scripts/token_report.py`](../scripts/token_report.py)'s root row `This harness` | `This repo` |

## Which kind of copy you have

**Your copy shares history with Sanvio Factory**, because you cloned it, or
forked it, and pull its `main` into yours. Follow the steps below as written.

**Your copy takes changes file by file with "check the starter"**, because
you made it from the template or adapted it heavily. Its
[`skills/starter-updates/`](../skills/starter-updates/) still reaches Sanvio Factory through GitHub's
redirect, so leave its address as it is: taking this release brings the new
one. In place of step 2:

1. Ask your agent to "check the starter", and take the rename's files.
2. Before step 3, make sure you've taken [`scripts/names.py`](../scripts/names.py) and
   [`.claude/hooks/session_start.py`](../.claude/hooks/session_start.py): they move `.harness/`.
3. Before step 4, make sure you've taken
   [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) and the plugin lines of
   [`.claude/settings.json`](../.claude/settings.json), or step 4 registers the old name again.
   If your copy publishes its mods under its own marketplace name, take the
   new `marketplace.json` but keep your own `name` line in it.
4. Copying a file never deletes the old one, so remove what moved. Carry any
   lines you added to `bin/harness-tools` into [`bin/factory-tools`](../bin/factory-tools) first.
   - `bin/harness` and `bin/harness-tools`
   - `examples/mods/harness-dashboard/` and `docs/harness-dashboard.svg`
   - `skills/harness-trends/`
   - `scripts/eval_harness.py` and `tests/test_eval_harness.py`
   - `tests/test_harness_cli.py`
   - `docs/harness-in-ci.md`, `docs/harness-in-ci.gif`,
     `docs/harness-evals.md` and `docs/harness-evals.gif`
5. Commit, so step 4's `git checkout .claude/settings.json` can't undo what
   you copied.

## The steps

1. **Stop what's running.** Stop the loop and its review watcher if they're
   running: `python3 scripts/loop.py stop`, with the same
   `--project projects/<name>` for one you started on a project. It stops at
   its next step, so wait until it has exited: a loop still running old code
   writes to `.harness/` after step 3 has moved it. Finish any eval run, or
   end it with `python3 scripts/eval_harness.py resume <run> --end`: once
   you've taken the rename, a run started before it can't be resumed.
2. **Take the changes.** Commit any lines you added to `bin/harness-tools`
   first: git carries committed changes across the move. Point any remote that
   names the old address at the new one, for example
   `git remote set-url upstream https://github.com/SanvioLabs/sanvio-factory`,
   since the setup check only recognises the public repo by its new address.
   Then pull from the remote that points at Sanvio Factory, for example
   `git pull upstream main`, or `git pull` if `origin` is Sanvio Factory
   itself.
3. **Start one Claude Code session at the repo root.** It moves `.harness/` to
   `.sanvio/`, any live factory runs with it, and says so in its setup
   message, under the first line if the setup check found something else
   first. If it offers to add the `sanvio-factory` marketplace, decline for
   now: adding it while `sanvio-harness-starter` is still registered keeps the
   old name.
4. **Register the marketplace under its new name**, in that session, in this
   order:
   1. `/plugin marketplace remove sanvio-harness-starter`. This removes its
      plugins too, and it applies to every clone on this machine.
   2. `/plugin marketplace add ./`, and accept the mods it turns on. Install
      any it doesn't offer with `/plugin install <name>@sanvio-factory`.
   3. Used the dashboard? `/plugin install factory-dashboard@sanvio-factory`.
   4. `/reload-plugins`, or start a new session.

   This installs every mod at its current version, so skip the separate
   `claude plugin update` lines in the rename entries. If Claude Code writes
   [`.claude/settings.json`](../.claude/settings.json) back in a different order,
   `git checkout .claude/settings.json` puts it back.

   **Your copy publishes its mods under its own marketplace name?** Then it
   has no `sanvio-harness-starter` to remove and no `sanvio-factory` to add.
   Skip 4.1 to 4.3, and keep your own `name` in
   [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json). Because nothing is removed and
   added again, the line above about skipping `claude plugin update` doesn't
   apply to you: run `claude plugin update <mod>@<your marketplace>` for every
   mod you have installed, then do 4.4. Wherever this page says
   `@sanvio-factory`, use your own marketplace name.
5. **Rename your variables.** In your shell profile, on each machine you use,
   change each `HARNESS_` variable in the table to its `SANVIO_` name. The old
   ones do nothing now, except that `HARNESS_USAGE_LOG=off` still keeps the log
   off. If `company/DATA.md`'s `Pulse folder` row names the old variable,
   change it there too.
6. **Check your tools.** Any alias or script that runs `bin/harness` should
   run [`bin/factory`](../bin/factory), and any that runs `eval_harness.py` should run
   [`scripts/eval_factory.py`](../scripts/eval_factory.py) with `--factory` in place of `--harness`.
   Anything that reads the dashboard data, an eval result or the token report
   reads the new names in the table. Check that any lines you added to
   `bin/harness-tools` are in [`bin/factory-tools`](../bin/factory-tools).
7. **Move off the old home folders**, on each machine that ran the loop or an
   eval:
   - The loop makes its checkouts in `~/.sanvio-loop/` now. Its old ones are
     in `~/.harness-loop/<this folder's name>/`: remove each with
     `git worktree remove <path>` from the clone or project it belongs to (it
     refuses one with uncommitted changes, so commit or copy those first),
     then delete that folder. Delete `~/.harness-loop/` itself only once every
     clone on this machine has upgraded: an older one still uses it.
   - `~/.harness-evals` holds the sealed copies of runs from before the
     rename, which can't be resumed. Delete it once every clone on this
     machine has upgraded.
8. **Push to your own repo**, if your copy has one. Everyone else who pulls it
   then does steps 1 and 3 to 7, 10 and 11 in their own clone.
9. **Update CI callers**, if a product repo calls
   [`.github/workflows/review-pr.yml`](../.github/workflows/review-pr.yml). A caller of the public repo
   is failing now, so do it first. A caller of your own factory's `@main` runs
   whatever that `main` holds, so do it straight after step 8. For each
   product repo, store the same deploy key's private half under the new name
   first:

   ```bash
   gh secret set FACTORY_DEPLOY_KEY --repo your-org/product < review-pr-deploy-key
   ```

   Set for the whole organisation? Use
   `gh secret set FACTORY_DEPLOY_KEY --org your-org --repos product-a,product-b < review-pr-deploy-key`.
   Lost the key file? Add a new read-only deploy key as *The secret* in
   [`examples/ci/README.md`](../examples/ci/README.md) says, and remove the old one.

   Then, in each caller's workflow file:
   - `uses: SanvioLabs/sanvio-harness-starter/...` becomes
     `uses: SanvioLabs/sanvio-factory/...`, if it names the public repo
   - `harness-repo:` becomes `factory-repo:`
   - the secret line becomes
     `FACTORY_DEPLOY_KEY: ${{ secrets.FACTORY_DEPLOY_KEY }}`

   A caller pinned to `review-pr.yml@<sha>` keeps reading the old names until
   you move its pin, so delete `HARNESS_DEPLOY_KEY` only once no caller names
   it: `gh secret delete HARNESS_DEPLOY_KEY --repo your-org/product`, or
   `--org your-org`.
10. **Start the loop again** the way you started it before.
11. **Check, from a new terminal:** `python3 scripts/check_setup.py` names any
    old variable still set and any `.harness/` still there. It doesn't check
    your mods, CI callers, scripts or home folders: those are steps 4, 9, 6
    and 7.

## If your copy changes a mod

A copy that changes what a mod does, including where it reads a file from,
bumps `version` in that mod's `.claude-plugin/plugin.json` in the same change.
If the version stays the same, installed copies can stay on the old code even
after `claude plugin update`. That happened to a status-line mod reading a
moved focus file: github-status still read `.harness/project/` after the
move to `.sanvio/project/`.

Stuck on a step? Run `python3 scripts/check_setup.py`, and check the step
against its entry in [`CHANGELOG.md`](../CHANGELOG.md): each one has a **Do:** line.
