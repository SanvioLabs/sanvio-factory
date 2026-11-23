# Install Sanvio Factory

This is the procedure an agent follows when a person asks it to install Sanvio
Factory from a session outside the factory. Follow the steps in order. Show the
person each command before you run it, and stop wherever a step says to.

Codex and Kiro follow the same steps, but nobody has tried them there yet.

## 1. Ask before anything runs

Ask the person two things:

- which folder the copy goes in
- what to call it

That gives you the copy's path, `<path>`, and its name, `<name>`. If `<path>`
already exists and isn't empty, refuse it and ask for another. Run nothing
until you have a path that's free.

## 2. Check the prerequisites

The copy needs `git` and Python 3.9 or newer, and no packages.

```bash
git --version
python3 --version
```

On Windows the Python command may be `py` or `python` rather than `python3`.
Try `python3`, then `py`, then `python`, and use the first that reports 3.9 or
newer. That command is `<python>` in every step below.

If `git` is missing, or none of them reports 3.9 or newer, stop. Tell the
person what's missing and run nothing else.

## 3. Clone it

```bash
git clone https://github.com/SanvioLabs/sanvio-factory <path>
```

On Windows, clone it this way instead:

```bash
git clone -c core.symlinks=true https://github.com/SanvioLabs/sanvio-factory <path>
```

The factory uses symbolic links, and on Windows they arrive as links only when
Developer Mode is on. Tell the person to turn it on in Windows Settings before
the clone if it isn't.

## 4. Turn on the hooks and run the setup check

In the copy, run these two:

```bash
cd <path>
git config core.hooksPath .githooks
<python> scripts/check_setup.py
```

The first points git at the factory's pre-commit hook. Without it, every check
in that hook silently does nothing. The second is
[`scripts/check_setup.py`](scripts/check_setup.py), which prints one PASS, WARN
or FAIL line per check. Show the person its whole output.

Then tell them what it means:

- Three warnings are expected on a fresh copy, before the folder is trusted:
  the `remote:` warning that `origin` is the public Sanvio Factory, the
  `company:` warning that there's no company record yet, and the `mods:`
  warning about mods not installed.
- Their notes name commands. Run none of them. The person runs those, or
  `/orientation` covers them later.
- On any FAIL, stop. Show the person that line and the fix printed under it,
  and go no further until they've fixed it.

## 5. Make a private copy

Ask whether to make a private copy of the factory on GitHub. Anything they push
to a public repo is public, and their own work goes in this copy.

Check whether `gh` is installed and logged in by running `gh auth status` and
reading only its exit code: 0 means logged in. Never show or read its output.

**If they say yes and `gh` is logged in:** ask which GitHub account or
organisation owns the copy. That's `<owner>`. Don't take it from `gh`. The repo
is called `<name>` from step 1 unless they want another name. Show them these
three commands, and run them only on a second yes:

```bash
gh repo create <owner>/<name> --private
git remote set-url origin https://github.com/<owner>/<name>.git
git push -u origin main
```

Then run `<python> scripts/check_setup.py` again and show the person its
`remote:` line, which now names the new repo.

**If they say yes and `gh` isn't installed or isn't logged in:** tell them what
to set up: install the GitHub CLI, `gh`, and run `gh auth login` themselves.
Then come back to this step. Never ask for a token, and never ask them to paste
one.

**If they say no:** tell them the copy's `origin` is still the public Sanvio
Factory, and pushing their work there would make it public.

## 6. Open the copy

Tell the person this session can't use the factory. Claude Code loads a
folder's settings, hooks, skills and mods only in a session started in that
folder. They open the copy at its root in one of these:

- **The terminal:** `cd <path> && claude`
- **The VS Code extension:** open the folder `<path>` in VS Code, then start
  Claude Code there.
- **The Desktop app:** use its Code tab, not its chat, and pick `<path>` as the
  folder.

When Claude Code asks whether they trust the folder, they say yes. Then they
run `/orientation`, which gets the factory ready for their job.

## What the install doesn't do

The install stops at step 6. It doesn't:

- write anything in `company/`
- add a connector or an MCP server
- install a mod by hand
- label an issue for the loop or start the loop

`/orientation` and the factory's own skills do those, in a session opened in
the copy.
