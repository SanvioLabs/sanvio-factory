# Upgrading to Sanvio Factory

The links and paths on this page point at Sanvio Factory's own files, and your
copy may not have them. Read this guide on GitHub, at
[`https://github.com/SanvioLabs/sanvio-factory/blob/main/docs/upgrading-to-sanvio-factory.md`](https://github.com/SanvioLabs/sanvio-factory/blob/main/docs/upgrading-to-sanvio-factory.md),
and don't copy it into your repo. A copy that takes changes file by file gets
step 3's move only once it has the files named in *Which kind of copy you
have*, or makes it by hand, as that section says.

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
one. In place of step 2, and for item 6 also step 11:

1. Ask your agent to "check the starter", and take the rename's files.
2. Before step 3, make sure you've taken [`scripts/names.py`](../scripts/names.py),
   [`scripts/old_names.py`](../scripts/old_names.py) and
   [`.claude/hooks/session_start.py`](../.claude/hooks/session_start.py): they move `.harness/`.
   If your copy doesn't take that hook, make step 3's move yourself, from the
   repo root, once step 1 has stopped the loop. First see which of the two
   folders exist:

   ```bash
   ls -A .harness .sanvio
   ```

   If only `.harness/` exists, rename it:

   ```bash
   mv .harness .sanvio
   ```

   If only `.sanvio/` exists, or neither does, there's nothing to move.

   If both exist, copy across anything `.sanvio/` doesn't already have. This
   keeps `.sanvio/`'s own files:

   ```bash
   cp -Rn .harness/. .sanvio/
   ```

   Then look through `.sanvio/`, and only after that run `rm -r .harness`.
   Nothing reads `.harness/` any more, only `.sanvio/`.
3. Before step 4, make sure you've taken
   [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) and the plugin lines of
   [`.claude/settings.json`](../.claude/settings.json), or step 4 registers the old name again.
   If your copy publishes its mods under its own marketplace name, take the
   new `marketplace.json` but keep your own `name` line in it, and in
   `settings.json` keep your own name in the `extraKnownMarketplaces` key and
   at the end of every `enabledPlugins` key, where the new lines say
   `sanvio-factory`.
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
6. No [`scripts/check_setup.py`](../scripts/check_setup.py)? In place of step 11, check from a new
   terminal, at the repo root:

   ```bash
   ls -d .harness
   env | grep -E '^HARNESS_(PULSE_FOLDER|RETRO|USAGE_LOG|EVALS_HOME)='
   git grep -n -e 'bin/harness' -e 'eval_harness' -- ':!CHANGELOG.md' ':!docs/upgrading-to-sanvio-factory.md' ':!docs/specs/'
   grep -n 'bin/harness' ~/.zshrc ~/.bashrc ~/.profile 2>/dev/null
   ```

   The first should say there's no such file, and the other three should
   print nothing, except that `git grep` may list a test that only checks
   `bin/harness` is gone. That isn't a caller, so leave it. The search leaves
   out the changelog, this guide and [`docs/specs/`](specs/), which name the old
   files as history. `HARNESS_HEADLESS` is left out on purpose, because it
   still counts. If `env` prints `HARNESS_USAGE_LOG=off`, rename it anyway,
   as step 5 says.

### What else the rename's files carry

Some of the rename's files also carry changes from other features. Taking
those files brings these changes too. The table covers changes whose
[`CHANGELOG.md`](../CHANGELOG.md) heading is dated 2026-11-08 or 2026-11-09, each
named by its entry so you can read its **Do:** line. For anything later, the
starter-updates skill lists each other commit on a file it names as "also
brings".

| File | Also brings | Entry |
|---|---|---|
| [`.claude/hooks/guard.py`](../.claude/hooks/guard.py) | A headless run is kept out of [`factories/`](../factories/), as it is `company/` | `2026-11-08: Hand an issue to another factory` |
| [`.claude/hooks/guard.py`](../.claude/hooks/guard.py) | A headless `Grep` leaves out `company/`, `local-data/`, `.inbox/` and [`factories/`](../factories/) | `2026-11-08: A headless search leaves out company/ and factories/` |
| [`.gitignore`](../.gitignore) | `factories.json` is ignored | `2026-11-08: Hand an issue to another factory` |
| [`.gitignore`](../.gitignore) | `reports/standup/*` is ignored | `2026-11-08: Standup remembers what you already settled` |
| [`scripts/factories.py`](../scripts/factories.py) | The whole dispatch feature, and its later fixes | `2026-11-08: Hand an issue to another factory`, `2026-11-08: A hand-edited record that hides what it merges no longer reads`, `2026-11-08: A review that posts no verdict waits for a new commit` |
| [`scripts/loop.py`](../scripts/loop.py), [`scripts/check_setup.py`](../scripts/check_setup.py) | A round on an open pull request, and `review --pr N` | `2026-11-08: The loop takes a round on an open pull request` |
| [`skills/starter-updates/capabilities.md`](../skills/starter-updates/capabilities.md) | The Factories row | `2026-11-08: Hand an issue to another factory` |
| [`README.md`](../README.md), [`HOW-IT-WORKS.md`](../HOW-IT-WORKS.md), [`AGENTS.md`](../AGENTS.md) | Text for dispatch and the headless search | `2026-11-08: Hand an issue to another factory`, `2026-11-08: A headless search leaves out company/ and factories/` |
| [`HOW-IT-WORKS.md`](../HOW-IT-WORKS.md) | Text for a round on an open pull request | `2026-11-08: The loop takes a round on an open pull request` |
| [`skills/standup/SKILL.md`](../skills/standup/SKILL.md) | Standup keeps its answers in `reports/standup/answers.jsonl` and doesn't ask again about an item you settled | `2026-11-08: Standup remembers what you already settled` |
| [`.gitignore`](../.gitignore) | [`factories/`](../factories/) is ignored apart from its README | `2026-11-08: Hand an issue to another factory` |
| [`.ignore`](../.ignore) | A comment saying searches leave out [`factories/`](../factories/) | `2026-11-08: Hand an issue to another factory` |
| [`skills/dispatch/SKILL.md`](../skills/dispatch/SKILL.md), [`docs/maintaining.md`](maintaining.md) | The whole file: each is new with dispatch | `2026-11-08: Hand an issue to another factory` |
| [`factories/README.md`](../factories/README.md) | The whole page, new with dispatch, and its *What the factory must do* | `2026-11-08: Hand an issue to another factory`, `2026-11-08: A headless search leaves out company/ and factories/` |
| [`tests/test_agent_hooks.py`](../tests/test_agent_hooks.py) | The tests for the guard's two changes above | `2026-11-08: Hand an issue to another factory`, `2026-11-08: A headless search leaves out company/ and factories/` |
| [`tests/test_factories.py`](../tests/test_factories.py) | The tests for dispatch and its later fixes | `2026-11-08: Hand an issue to another factory`, `2026-11-08: A hand-edited record that hides what it merges no longer reads`, `2026-11-08: A review that posts no verdict waits for a new commit` |
| [`tests/test_loop.py`](../tests/test_loop.py), [`tests/test_check_setup.py`](../tests/test_check_setup.py) | The tests for a round on an open pull request | `2026-11-08: The loop takes a round on an open pull request` |
| [`.claude/settings.json`](../.claude/settings.json), [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) | factory-floor switched on, and the two loop mods it replaced switched off and no longer listed | `2026-11-09: Factory floor` |

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
   has no `sanvio-harness-starter` to remove and no `sanvio-factory` to add,
   so skip 4.1 and 4.2. With your own name kept in
   [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) and in
   [`.claude/settings.json`](../.claude/settings.json), as sub-step 3 says, no session offers to add
   `sanvio-factory`; if one does, a `sanvio-factory` key is still in
   `settings.json`, so rename it to yours. Still do 4.3 if you used the
   dashboard, with your own marketplace name:
   `/plugin install factory-dashboard@<your marketplace>`. `factory-dashboard`
   replaces `harness-dashboard`, which the marketplace no longer lists, so no
   update moves you to it; `/plugin uninstall harness-dashboard@<your marketplace>`
   then removes the old one, which still reads `.harness/`. Because nothing
   is removed and added again, the line above about skipping
   `claude plugin update` doesn't apply to you: run
   `claude plugin update <mod>@<your marketplace>` for every mod you have
   installed that your `marketplace.json` still lists, then do 4.4. Wherever
   this page says `@sanvio-factory`, use your own marketplace name.
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
