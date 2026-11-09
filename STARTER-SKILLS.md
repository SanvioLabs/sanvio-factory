# Starter skills

A short list of skills worth bringing into your harness in the first few weeks,
where to find more, and how to make any of them your own. Everything here works
in Claude Code. Start with the first group, and pull from the others when the
work calls for them.

## Make it yours: review first, then build your own

Don't install a skill straight from someone else's repo. A skill is someone
else's instructions running with your permissions, and the bad ones don't look
bad. Review it, then have your harness write its own version.

**1. Review it.** Ask your agent: "Review this skill: <link>." The
`review-skill` skill in this repo does the following:

- Copies the skill into `~/skill-quarantine/`, never into [`skills/`](skills/), and doesn't run or
  load anything in it.
- Reads every file, scripts included, and lists what it would make an agent do:
  commands, URLs, files read or written, anything installed.
- Stops and asks you if it finds any of these:
  - instructions to skip your rules, gates or hooks
  - anything that touches credentials, `.env` files or keys
  - `curl | sh` or other download-and-run
  - writes outside the repo
  - hidden text: HTML comments, zero-width, bidi and tag characters, base64
  - files an agent loads by itself: `<skill>/CLAUDE.md`, `<skill>/AGENTS.md`, a `<skill>/.claude/` folder
  - symlinks and binaries
  - sending local files out
  - persistence: shell profiles, scheduled jobs, agent settings
  - permission-mode flags
  - a description so broad it fires on everything
- Sorts everything the skill does into **covered** (you already have it),
  **gap** (you don't) or **conflict** (it contradicts your rules).
- Drafts the smallest change that closes each gap, and applies nothing.

**2. Check the licence.** It decides what you're allowed to do:

| Licence | What you can do |
|---|---|
| MIT, Apache 2.0 | Adapt it freely. Keep the notice at the top of your version |
| CC BY-SA | Adapt it, but your version carries the same licence and credits the original |
| None | Read it for ideas. Don't copy it. Have your harness write its own from scratch |

**3. Make it yours.** If you want what it does, say: "Make me a local version of
that, in our conventions." Your version follows your rules and names your
tools, and nobody else's update can change it under you. Put the source link,
commit and licence at the top.

**4. Commit it.** Everyone who checks out the factory gets it.

Each skill takes a few minutes this way. Doing it every time matters more than
which skills you pick.

**Stelliad is the exception.** [`.claude/settings.json`](.claude/settings.json) switches its plugin on, so
every skill below marked Stelliad arrives when you trust the folder, with no
separate prompt. They run as `stelliad:<name>`: `/stelliad:create-ticket`,
`/stelliad:create-spec`. That skips steps 1 and 3. It's pinned to one Stelliad
commit, so it can't change under you until someone moves the pin. The [README](README.md#borrowing-other-peoples-skills)
says what that trusts and how to keep it off. Where this repo has a skill of
the same name, such as `review-skill`, the one in [`skills/`](skills/) is the one
[`AGENTS.md`](AGENTS.md) points at. Everything else here goes through the four steps above.

## Start here

| Skill | What it does for you | Where |
|---|---|---|
| `review-skill` | Vets an outside skill before it gets anywhere near your agent | [This repo](skills/review-skill/), also in [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/review-skill) |
| `standup` | One morning read of what's on you, from GitHub, the loop and whatever calendar, email or tracker your harness reaches, with a suggested order for the day. Reads only | [This repo](skills/standup/) |
| `skill-creator` | Writes and tests your own skills, and tunes their descriptions so they fire when they should | [Anthropic](https://github.com/anthropics/skills/tree/main/skills/skill-creator) (Apache 2.0) |
| `find-skill` | Searches the public catalogues for a skill that does what you're about to do by hand | [fockus/claude-skill-find-skill](https://github.com/fockus/claude-skill-find-skill). No licence, so build your own version |
| `verify-done` | "Done" means the command that proves it ran and passed, not that the agent says so | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/verify-done) |
| `create-ticket` | Turns a rough idea into a ticket an agent or a developer can pick up without coming back to ask | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/create-ticket) |
| `review-ticket` | Grades a ticket READY, NEEDS_REFINEMENT or BLOCKED, and names what's missing | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/review-ticket) |
| `secret-scan` | Finds exposed credentials before an agent starts reading your repos | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/secret-scan) |
| `run-gates` | Turns your checkpoints into checks that block instead of advise | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/run-gates) |

## Once you're building with it

| Skill | What it does for you | Where |
|---|---|---|
| `test-first` | No code without a failing test first. The single biggest guard on agent-written code | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/test-first) |
| `systematic-debugging` | Root cause before fixes, so the agent stops patching symptoms | [Superpowers](https://github.com/obra/superpowers/tree/main/skills/systematic-debugging) (MIT) |
| `create-spec`, `plan-spec`, `implement-spec`, `review-spec` | The spec loop: idea to spec, spec to plan, plan to code one verified task at a time, then an independent review | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills) |
| `review-intake` | Works through PR review feedback properly: verifies each comment, fixes what's right, pushes back with evidence on what isn't | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/review-intake) |
| `review-principles` | Reviews code for DRY, KISS and single responsibility, with findings tied to a consequence rather than taste | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/review-principles) |
| `repo-audit` | Checks a repo against a security and quality baseline before you point agents at it | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/repo-audit) |
| `webapp-testing` | Drives your web app in a real browser with Playwright to check a change works | [Anthropic](https://github.com/anthropics/skills/tree/main/skills/webapp-testing) (Apache 2.0) |
| `mcp-builder` | Builds an MCP server when your agent needs a system no connector reaches yet | [Anthropic](https://github.com/anthropics/skills/tree/main/skills/mcp-builder) (Apache 2.0) |
| `generate-readme` | Writes a README from what the code actually does | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/generate-readme) |

## When you need them

| Skill | Reach for it when | Where |
|---|---|---|
| `archify` | You need an architecture or flow diagram you can click into, for your team or your customers | [tt-a1i/archify](https://github.com/tt-a1i/archify) (MIT) |
| `stress-test-plan` | You're about to commit a quarter to a plan and want its weakest assumption first | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/stress-test-plan) |
| `coverage-gaps` | You want to know which risky code no test touches | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/coverage-gaps) |
| `find-dead-code` | You've inherited a codebase, or it's grown faster than anyone pruned it | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/find-dead-code) |
| `triage-alert` | An alert fires and you want it traced to the commit that caused it | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/triage-alert) |
| `supply-chain-risk-auditor`, `insecure-defaults`, `static-analysis` | You want a security team's eye on dependencies, config defaults and code | [Trail of Bits](https://github.com/trailofbits/skills/tree/main/plugins) (CC BY-SA 4.0) |
| `third-party-compliance` | Someone asks "can we use this vendor?" under HIPAA, SOC 2, COPPA, GDPR or FERPA | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/third-party-compliance) |
| `ai-contract-audit` | You want to check your contracts match how your team actually builds with AI | [Stelliad](https://github.com/Stelliad/stelliad-skills/tree/main/skills/ai-contract-audit) |

## Where to find more

The skills above come from these, and there's a lot more in each. Run anything
you find through step 1 first.

| Source | What's there | Licence |
|---|---|---|
| [anthropics/skills](https://github.com/anthropics/skills) | Anthropic's own: documents, MCP servers, testing, skill authoring | Per skill. Check each one's `LICENSE.txt` |
| [obra/superpowers](https://github.com/obra/superpowers) | A disciplined development workflow: planning, TDD, debugging, code review | MIT |
| [Stelliad/stelliad-skills](https://github.com/Stelliad/stelliad-skills) | Delivery skills: specs, tickets, gates, review, security | MIT |
| [trailofbits/skills](https://github.com/trailofbits/skills) | Security review from a security firm | CC BY-SA 4.0 |
| [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) | React and Vercel practices | No licence: ideas only |
| [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills), [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code), [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | Big curated lists pointing at hundreds more | The list's licence says nothing about what it links to. Check each skill |

A list with thousands of stars isn't a review. Popular skills get copied into
lists without anyone reading them, so step 1 applies to every one.

## Keep it small

You'll find good skills everywhere, and it's easy to end up with eighty. Every
skill is one more thing the agent has to choose between. When two start
overlapping, merge them. A harness with twelve skills you trust beats one with
eighty you don't.

What do you do by hand every week? That's your next skill.
