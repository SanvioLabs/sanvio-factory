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
below when you take the rename. One thing breaks before you even pull: a
product repo whose CI runs this repo's review workflow straight from
`SanvioLabs/sanvio-harness-starter/...@main` or
`SanvioLabs/sanvio-factory/...@main` has been failing since 2026-11-08. Fix
that first (step 9).

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
| The dashboard's `Harness` column | `Factory` |
| `harness-trends` skill, "harness trends", "my harness report" | `factory-trends`, "factory trends", "my factory report" |
| `/github all`'s `harness:` line | `factory:` |
| `scripts/eval_harness.py`, `--harness` | [`scripts/eval_factory.py`](../scripts/eval_factory.py), `--factory` |
| `docs/harness-in-ci.md`, `docs/harness-evals.md` | [`docs/factory-in-ci.md`](factory-in-ci.md), [`docs/factory-evals.md`](factory-evals.md) |
| CI input `harness-repo`, secret `HARNESS_DEPLOY_KEY` | `factory-repo`, `FACTORY_DEPLOY_KEY` |
| [`scripts/token_report.py`](../scripts/token_report.py)'s root row `This harness` | `This repo` |

One old name still counts: `HARNESS_HEADLESS=1` keeps a run headless, because
reading it only ever makes the guard stricter.

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
4. Copying a file never deletes the old one, so remove what moved:
   `bin/harness`, `bin/harness-tools` (after you've carried any lines you
   added into [`bin/factory-tools`](../bin/factory-tools)), `examples/mods/harness-dashboard/`,
   `skills/harness-trends/`, `scripts/eval_harness.py`,
   `tests/test_eval_harness.py`, `docs/harness-in-ci.md`,
   `docs/harness-in-ci.gif`, `docs/harness-evals.md` and
   `docs/harness-evals.gif`.
5. Commit, so step 4's `git checkout .claude/settings.json` can't undo what
   you copied.

## The steps

1. **Stop the loop** if it or its review watcher is running:
   `python3 scripts/loop.py stop`, with the same `--project projects/<name>`
   for one you started on a project. It stops at its next step, so wait until
   it has exited. A loop still running old code writes to `.harness/` after
   step 3 has moved it.
2. **Take the changes** from the remote that points at Sanvio Factory, for
   example `git pull upstream main`, or `git pull` if `origin` is still
   Sanvio Factory itself. The old address works. Commit any lines you added to
   `bin/harness-tools` first: git carries committed changes across the move.
3. **Start one Claude Code session at the repo root.** It moves `.harness/` to
   `.sanvio/`, any live factory runs with it, and says so in its setup
   message. If it offers to add the `sanvio-factory` marketplace, decline for
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
5. **Rename your variables.** In your shell profile, on each machine you use,
   change each `HARNESS_` variable in the table to its `SANVIO_` name. The old
   ones do nothing now. If `company/DATA.md`'s `Pulse folder` row names the old
   variable, change it there too.
6. **Check your tools.** Any alias or script that runs `bin/harness` should
   run [`bin/factory`](../bin/factory), and any that runs `eval_harness.py` should run
   [`scripts/eval_factory.py`](../scripts/eval_factory.py) with `--factory` in place of `--harness`. Check
   that any lines you added to `bin/harness-tools` are in
   [`bin/factory-tools`](../bin/factory-tools).
7. **Move off the old home folders**, on each machine that ran the loop or an
   eval:
   - The loop makes its checkouts in `~/.sanvio-loop/` now, and no longer
     sees `~/.harness-loop/`. Remove each checkout in the old folder with
     `git worktree remove <path>` from the clone or project it belongs to
     (it refuses one with uncommitted changes, so commit or copy those
     first), then delete the folder.
   - Rename `~/.harness-evals` to `~/.sanvio-evals`. Eval runs made before
     the rename can't be read by `compare`: rerun the ones you need.
8. **Push to your own repo**, if your copy has one. Everyone else who pulls it
   then repeats steps 1 and 3 to 7 in their own clone.
9. **Update CI callers**, only if a product repo calls
   [`.github/workflows/review-pr.yml`](../.github/workflows/review-pr.yml). A caller of your own factory's
   `@main` runs whatever that `main` holds, so change it straight after step 8.
   In each caller's workflow file:
   - `uses: SanvioLabs/sanvio-harness-starter/...` becomes
     `uses: SanvioLabs/sanvio-factory/...`, if it names this repo
   - `harness-repo:` becomes `factory-repo:`
   - the secret line becomes
     `FACTORY_DEPLOY_KEY: ${{ secrets.FACTORY_DEPLOY_KEY }}`

   Then store the same deploy key's private half under the new name:

   ```bash
   gh secret set FACTORY_DEPLOY_KEY --repo your-org/product < review-pr-deploy-key
   ```

   Set for the whole organisation? Use
   `gh secret set FACTORY_DEPLOY_KEY --org your-org --repos product-a,product-b < review-pr-deploy-key`.
   A caller pinned to `review-pr.yml@<sha>` keeps reading the old names until
   you move its pin, so delete `HARNESS_DEPLOY_KEY` only once no caller names
   it: `gh secret delete HARNESS_DEPLOY_KEY --repo your-org/product`, or
   `--org your-org`. Lost the key file? Add a new read-only deploy key as
   *The secret* in [`examples/ci/README.md`](../examples/ci/README.md) says, and remove the old one.
10. **Start the loop again** the way you started it before.
11. **Check, from a new terminal:** `python3 scripts/check_setup.py` names any
    old variable still set and any `.harness/` still there. It doesn't check
    your mods, CI callers, scripts or home folders: those are steps 4, 9, 6
    and 7.

Point any remote that names the old address at the new one, for example
`git remote set-url upstream https://github.com/SanvioLabs/sanvio-factory`.
The setup check only recognises the public repo by its new address.

Stuck on a step? Run `python3 scripts/check_setup.py`, and check the step
against its entry in [`CHANGELOG.md`](../CHANGELOG.md): each one has a **Do:** line.
