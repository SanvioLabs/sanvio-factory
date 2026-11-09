# Upgrading to Sanvio Factory

For anyone whose copy was taken before 2026-11-08, when this repo was
`SanvioLabs/sanvio-harness-starter`. It's now `SanvioLabs/sanvio-factory`, and
the names inside it changed with it. This page puts the five rename entries in
[`CHANGELOG.md`](../CHANGELOG.md) into one order, for taking them together.

The factory is the repo you own and everything that runs between sessions, so
the names that mean the whole repo changed. The harness is what one agent
session works inside, so harness-lens, the harness root and the review
workflow's `harness/` checkout keep their names.

The state folder, the variables, [`bin/harness`](../bin/harness) and the home folders keep
working under their old names until a later release, whose CHANGELOG entry
will say it drops them. Two things don't wait:

- **Your mods.** After you take the changes, [`.claude/settings.json`](../.claude/settings.json) turns
  on each mod as `<name>@sanvio-factory`, and Claude Code won't find them
  until you register the marketplace under that name (step 4).
- **A product repo whose CI calls the review workflow.** Its input and secret
  changed names with no fallback (step 8). A caller that runs
  `SanvioLabs/sanvio-harness-starter/...@main` or
  `SanvioLabs/sanvio-factory/...@main` straight from the public repo has been
  failing since 2026-11-08: fix it first.

## What changed

| Old | New | Old one still works? |
|---|---|---|
| `SanvioLabs/sanvio-harness-starter` | `SanvioLabs/sanvio-factory` | Yes, GitHub redirects it |
| `.harness/` | `.sanvio/` | Moved for you by the next session (step 3) |
| `HARNESS_PULSE_FOLDER`, `HARNESS_RETRO`, `HARNESS_USAGE_LOG`, `HARNESS_EVALS_HOME` | `SANVIO_` with the same ending | Until a later release, with a warning |
| [`bin/harness`](../bin/harness) | [`bin/factory`](../bin/factory) | Until a later release, with a warning |
| `bin/harness-tools` | [`bin/factory-tools`](../bin/factory-tools) | No: it moved |
| `~/.harness-loop/`, `~/.harness-evals/` | `~/.sanvio-loop/`, `~/.sanvio-evals/` | Until a later release |
| Marketplace `sanvio-harness-starter` | `sanvio-factory` | No |
| `harness-dashboard` mod, `/harness-dashboard` | `factory-dashboard`, `/factory-dashboard` | No |
| `harness-trends` skill | `factory-trends` | "harness trends" still reaches it |
| CI input `harness-repo`, secret `HARNESS_DEPLOY_KEY` | `factory-repo`, `FACTORY_DEPLOY_KEY` | No |
| [`scripts/token_report.py`](../scripts/token_report.py)'s root row `This harness` | `This repo` | Only matters if something reads its output |

## Which kind of copy you have

**Your copy shares history with Sanvio Factory**, because you cloned it, or
forked it, and pull its `main` into yours. Follow the steps below as written.

**Your copy takes changes file by file with "check the starter"**, because
you made it from the template or adapted it heavily. Leave the address in your
copy's [`skills/starter-updates/`](../skills/starter-updates/) as it is: it still reaches Sanvio
Factory through GitHub's redirect, and taking this release brings the new
address. In place of step 2:

1. Ask your agent to "check the starter", and take the rename's files.
2. Before step 3, make sure you've taken [`scripts/names.py`](../scripts/names.py) and
   [`.claude/hooks/session_start.py`](../.claude/hooks/session_start.py): they move `.harness/`.
3. Before step 4, make sure you've taken
   [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) and the plugin lines of
   [`.claude/settings.json`](../.claude/settings.json), or step 4 registers the old name again.
4. Copying a file never deletes the old one, so remove what moved:
   `examples/mods/harness-dashboard/`, `skills/harness-trends/` and
   `bin/harness-tools`, after you've carried any lines you added there into
   [`bin/factory-tools`](../bin/factory-tools).
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
   change each `HARNESS_` variable in the table to its `SANVIO_` name. If
   `company/DATA.md`'s `Pulse folder` row names the old variable, change it
   there too.
6. **Check your tools.** Any alias or script that runs [`bin/harness`](../bin/harness) should
   run [`bin/factory`](../bin/factory). Check that any lines you added to
   `bin/harness-tools` are in [`bin/factory-tools`](../bin/factory-tools).
7. **Push to your own repo**, if your copy has one. Everyone else who pulls it
   then repeats steps 1 and 3 to 6 in their own clone.
8. **Update CI callers**, only if a product repo calls
   [`.github/workflows/review-pr.yml`](../.github/workflows/review-pr.yml). A caller of your own factory's
   `@main` runs whatever that `main` holds, so change it straight after step 7.
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
9. **Start the loop again** the way you started it before.
10. **Check, from a new terminal:** `python3 scripts/check_setup.py` names any
    old variable still set and any `.harness/` still there. It doesn't check
    your mods, CI callers, scripts or home folders: those are steps 4, 8, 6
    and the section below.

When it suits you, point any remote that names the old address at the new one,
for example
`git remote set-url upstream https://github.com/SanvioLabs/sanvio-factory`.

## Before the release that drops the old names

- **Move off `~/.harness-loop/`.** The loop keeps using it while it's there.
  With the loop stopped, remove each checkout in it with `git worktree remove`
  from the clone or project it belongs to (it refuses one with uncommitted
  changes), then delete the folder. The loop makes new checkouts in
  `~/.sanvio-loop/`.
- **Rename `~/.harness-evals` to `~/.sanvio-evals`.** It holds only results.
- **Check nothing still calls [`bin/harness`](../bin/harness)** or sets a `HARNESS_` variable.

Stuck on a step? Run `python3 scripts/check_setup.py`, and check the step
against its entry in [`CHANGELOG.md`](../CHANGELOG.md): each one has a **Do:** line.
