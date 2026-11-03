# Harness lens

A harness works where you can't see it. The session just behaves better, and
nobody can say which part did that. This mod draws one line above the prompt
naming the layer that just acted:

```
◆ harness  plan: Team · Acme  steering: 3 always on + gates  skill: review-tests  gate: ✗ proposal  guard: ✗ refused Bash  review: reviewer  running: loop 1
```

It's a Claude Code mod, so it works in Claude Code only: it was seen working in
the terminal, the VS Code extension and Claude Desktop's Code tab on
2026-10-23, with Claude Code 2.1.309. It was built and
tested on Claude Code 2.1.295. Codex and Kiro don't have mods.

## It's on already

In Claude Code, the lens loads by itself. The harness's
[`.claude/settings.json`](../../../.claude/settings.json) names this repo as a plugin marketplace (the listing
is [`.claude-plugin/marketplace.json`](../../../.claude-plugin/marketplace.json)) and turns the lens on, so the line
is there the first time you start Claude Code at the root and trust the
folder.

Don't see it? Install it from inside a session, at the root:

```
/plugin marketplace add ./
/plugin install harness-lens@sanvio-harness-starter
```

It's active as soon as the install says so, no restart. Or load it for one
session with `claude --plugin-dir examples/mods/harness-lens`.

A change to what the mod does raises `version` in its [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json), because `/plugin update` keeps an installed copy whose version hasn't changed, and CI checks this on every pull request with [`scripts/check_mod_versions.py`](../../../scripts/check_mod_versions.py).

To turn it off just for you, without changing the file everyone shares:

```bash
claude plugin disable harness-lens@sanvio-harness-starter --scope local
```

## Reading the band

| Segment | Shows |
|---|---|
| **plan** | The Claude plan this session is signed in with, and on a business plan its organisation. A personal plan shows in yellow. See [The plan segment](#the-plan-segment) |
| **steering** | How many steering files load into every session (the `@` lines in [`AGENTS.md`](../../../AGENTS.md)), plus any the agent read because they applied |
| **skill** | The last of this harness's skills the agent followed, whether you typed `/name` or it read the `SKILL.md` |
| **gate** | The last gate run and how it went. A commit the pre-commit hook refused shows as `✗ pre-commit`. A commit that got through shows nothing, because the hook is silent when it passes |
| **guard** | The last tool a guard refused. Never the reason: that's in the transcript, and it can name a file |
| **review** | The reviewer agents working now, else how the last one went. See [The review segment](#the-review-segment) |
| **running** | The headless sessions the loop and the agent eval are running now: `eval 2 · loop 1`, or `none`. See [The running segment](#the-running-segment) |
| **scope** | Only in a harness that declares one (see [Another layout](#another-layout)): the client, project or area this session is scoped to, first on the line. `none` when nothing is set |

Cyan means it happened this turn. A gate or guard result this turn is green or
red. Yellow is a personal plan. Plain text happened earlier in the session, and dim means nothing yet. A
guard refusal and a failed gate also pop up a short notice.

`/lens` prints the whole session, layer by layer: every steering file read,
every skill followed, each gate with how many times it passed and failed, the
refusals by tool, the reviewers running now with how long each has run, and
how many headless sessions each `running` label has, a zero included.

### The plan segment

The lens reads the plan once, when the session starts, by running `claude
auth status` with the config directory the session started with. A reload
reads it again.

| Shows | Means |
|---|---|
| `Team · <org>` | A Team plan, with its organisation's name. Just `Team` when the name is blank or holds an `@`, so an email never shows |
| `Enterprise · <org>` | An Enterprise plan, with its organisation's name. Just `Enterprise` when the name is blank or holds an `@` |
| `Pro (personal)`, `Max (personal)`, `Free (personal)` | A personal plan, in yellow. No organisation name, because on a personal plan that holds the person's email |
| `API key` | Signed in with an API key |
| `unknown` | Signed out, or `claude auth status` failed or took longer than two seconds. Dim |

It only shows the plan. It doesn't block anything on a personal plan.

### The review segment

It shows one of this harness's agents (those in [`agents/`](../../../agents/)) from the moment
the session you're driving sends it to work, background or not. An `Explore`
or a plugin's agent never shows, and nor does an agent a subagent starts.

| State | Example | Means |
|---|---|---|
| One running | `▶ reviewer 1:20` | It has run for a minute and twenty seconds. The time moves every few seconds |
| Two or three running | `▶ 2 reviewer · security-reviewer` | How many, and which |
| More than three running | `▶ 4` | How many. `/lens` lists them |
| Ended well | `✓ reviewer` | The last one to end gave its answer. Green the turn it ended, plain after |
| Ended badly | `✗ reviewer` | The last one to end stopped on an error, a refusal or an interrupt. Red the turn it ended, plain after |
| Outcome unknown | `? reviewer` | It ended without the lens seeing how, for example during a reload. Dim |
| None sent yet | `none yet` | No reviewer has started this session |

### The running segment

Every few seconds the lens runs `ps` and counts the `claude` processes running
beneath [`scripts/loop.py`](../../../scripts/loop.py) (as `loop`) and beneath [`scripts/eval_agents.py`](../../../scripts/eval_agents.py) (as
`eval`). Labels with a count are listed in alphabetical order, and a label with
none is left out: `eval 2 · loop 1`. When nothing counts it shows `none`.

A `claude` with neither above it isn't counted, so an interactive session in a
terminal never shows. The match is on the command alone, so any clone's
[`scripts/loop.py`](../../../scripts/loop.py) counts under `loop`, not only this one's. If `ps` fails or
takes longer than two seconds, the segment keeps the last counts.

The labels and what they match come from the `running` key (see
[Another layout](#another-layout)).

## Try it

Load it, then:

1. Ask for something a steering file covers ("read the gates steering"), and
   watch **steering** pick it up.
2. Run the example's gate on a proposal with a `{{placeholder}}` in it, and
   watch **gate** go red.
3. Ask the agent to print `.env`. Usually it refuses on its own, because the
   steering says so, and the band can't show a refusal that never became a
   tool call. **guard** goes red only when a call actually reaches the guard
   and the guard says no.
4. Type `/review-tests`, then hand the work to the `reviewer` agent, and
   watch **review** show `▶ reviewer` and its time until it ends.
5. Type `/lens`.

## What it doesn't do

It only looks. It never blocks a call or changes one: the guard in
[`.claude/hooks/guard.py`](../../../.claude/hooks/guard.py) and the gates do that, and they work without it.

It shows only this harness's own skills and agents. A skill from a plugin on
your machine never appears unless `skillPrefixes` names that plugin (the
starter names Stelliad), so the band is safe to put on a projector. A
subagent's own file reads don't count either. The band is about the session
you're driving.

## Another layout

It looks for the starter's shape: [`AGENTS.md`](../../../AGENTS.md) beside [`steering/`](../../../steering/), skills in
[`skills/`](../../../skills/) and `examples/*/skills/`, agents in [`agents/`](../../../agents/), gates named
`*_gate.py`. A harness laid out differently says where its layers live in
[`.claude/harness-lens.json`](../../../.claude/harness-lens.json) at its root. Every key is optional, and a key left
out keeps the starter's value:

```json
{
  "steering": [".studio/steering"],
  "always": ["CLAUDE.md"],
  "skills": [".studio/skills"],
  "skillPrefixes": ["studio:"],
  "agents": [".claude/agents"],
  "gates": ["check-gates\\.sh\\s+(\\S+)"],
  "scope": [".studio/hooks/.client-scope.{session}.json", ".studio/hooks/.focus.{session}.json"],
  "running": { "loop": "loop-runner", "eval": "scripts/eval_agents\\.py" }
}
```

The starter's own [`.claude/harness-lens.json`](../../../.claude/harness-lens.json) sets only `skillPrefixes` to
`["stelliad:"]`, so a skill from the Stelliad plugin it switches on shows as
the harness's.

`gates` are patterns for the shell command that runs a gate. The first group
in the pattern is the gate's name.

`scope` lists the files that hold the session's scope, if your harness has
one. `{session}` stands for the session id. The lens reads them in order and
shows the first that names a scope: `{"client": "acme"}`, or `{"kind":
"partner", "name": "fabrikam"}`. Put the file a guard enforces first, so a
looser one never shows over it. The starter has no scope, so its band has no
`scope` segment.

`running` maps each label to a pattern for the command of a process that
starts headless sessions. A `claude` process counts under the first label
whose pattern matches a process above it. A map you give replaces the
starter's `{"loop": "scripts/loop\\.py", "eval": "scripts/eval_agents\\.py"}`
whole, and a pattern that's empty or doesn't compile is dropped.

## Changing it

[`hooks/logic.ts`](hooks/logic.ts) holds the decisions as plain functions, so they can be tested.
[`hooks/register.tsx`](hooks/register.tsx) reads files, watches the session and calls into them.
From [`examples/mods/`](../):

```bash
claude plugin validate harness-lens
claude plugin test harness-lens
```

`python3 -m unittest discover -s tests`, and so the loop, runs these wherever Claude Code is installed. CI doesn't install Claude Code, so it skips them.
