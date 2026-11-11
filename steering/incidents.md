# Incidents

What to do in the first hour when an agent or a person finds an exposure (a
secret, customer data or company data somewhere it shouldn't be) or a change
nobody asked for. Work through the five steps in order. Stopping comes first,
because everything after it is easier once nothing new is happening.

## Stop the agent and the loop

1. End the agent's session first: the one that caused it, or the one that
   found it if it's still acting.
2. If the loop is running, stop it in the order
   [`skills/loop-control/SKILL.md`](../skills/loop-control/SKILL.md) gives under *Stop it*. Stopping
   alone lets it take the issue straight back.
   1. Take the ready label off every issue whose row in `.loop/status.json`
      (`.loop/projects/<name>/status.json` for a project's loop) has
      `state: "working"`: `gh issue edit <N> --remove-label <ready label>`,
      with `--repo <owner>/<repo>` for a project's issue.
   2. Then `python3 scripts/loop.py stop`, with `--project projects/<name>`
      for a project's loop. It ends at its next step, not mid-step.
   3. For an immediate halt, `tmux kill-session -t <name>`. It can leave a
      half-done branch or worktree behind.
3. The round already running may still push and open a pull request. Say so,
   and check for one before you call the loop stopped.

## Who to tell, and how soon

Take who to tell, and the deadline for telling them, from the `## Incidents`
section of `company/COMPANY.md`. If that file is missing, or the section is
missing or empty, ask the person running this session who to tell and by
when. Never name a default contact, and never guess one.

`company/COMPANY.md` is gitignored. Never quote it into a tracked file, this
one included.

## Rotate secrets and record it

Rotate every secret the exposure touched. Also rotate the token of each
connector in `company/DATA.md` the agent used during the incident, whether or
not it looks touched.

Record only the secret's name, the date it was rotated and who rotated it,
never its value. That record goes in the incident note kept by the contact
from *Who to tell, and how soon*, not in this repo.
[*Secrets: the hard line*](data-and-tools.md#secrets-the-hard-line) in
[`data-and-tools.md`](data-and-tools.md) still applies throughout: refer to each secret by name,
and don't open a file to see its value.

## Where the records are

| Record | Where |
|---|---|
| Usage log | `.sanvio/usage/<user>.jsonl` |
| Loop log | `.loop/loop.log` |
| Each issue's agent log | `.loop/issue-<N>/agent.log` |
| Loop status | `.loop/status.json` |
| A project's loop, all three | `.loop/projects/<name>/` |
| Session records | `~/.claude/projects` |
| Retro captures | `local-data/retro/`, when `SANVIO_RETRO=on` |

## What to keep

Before anything is cleaned up, keep every record above, plus the worktree and
branch of the issue involved, and its pull request and comments. Don't delete
or rewrite any of them, even to remove what was exposed, until the contact
says the investigation has what it needs.

Don't copy customer data anywhere beyond what the investigation needs.
[*No copies beyond the purpose*](data-and-tools.md#standing-rules) holds during an incident too.
