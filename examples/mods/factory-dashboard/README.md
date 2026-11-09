# Factory dashboard

The factory's numbers are spread across the loop's records, your usage log,
saved evals, Claude Code's transcripts and GitHub. This mod opens a pane
beside the conversation that brings them together, with what needs you first.
In a terminal pane 66 columns wide, with made-up numbers:

<img src="../../../docs/factory-dashboard.svg" width="480" alt="The Factory pane in a terminal. Under the header, the buttons Refresh, 7 days, 14 days in orange as the one chosen, and 30 days. Waiting on you: four pull requests, one in yellow whose checks are still running and a draft in red whose checks fail and that conflicts, then a blocked issue in red with why. Loop spend: a bar a day from Oct 16 to Oct 27, today's in orange, with Oct 20 and Oct 27 under them, then tables of the spend by period, issue and model. Throughput and rework, with the 67% that needed a commit in yellow. Evals, with a stale reviewer in yellow. Conversations: a bar a day from Oct 15 to Oct 27, then tokens by side and model. Activity: the skills, agents and commands used, each with its tokens and estimated cost, a question mark where there is no figure, and the guard's one refusal in yellow, then what the estimate rests on.">

<details>
<summary>The same pane as text</summary>

```
starter                                              Updated 12:00
[ Refresh ] [ 7 days ] [ 14 days ] [ 30 days ]
──────────────────────────────────────────────────────────────────
Waiting on you
Pull request                             Waiting  Checks Conflicts
#45 Gate: check the fee total               3.2h    pass        no
#44 Loop: retry a flaky test once            25h pending   unknown
#42 (draft) Steering: shorter replies        48h    fail       yes
#46 Examples: a Go project                    1h    none        no

Blocked issue                                                Since
#34 README: link the loop section                           Oct 23

#34: the link check still fails after 5 rounds

──────────────────────────────────────────────────────────────────

Loop spend
Daily, Oct 16 to Oct 27: most $5.80 on Oct 22
                                 ████                ▂▂▂▂
   ▁▁▁▁           ▅▅▅▅ ▄▄▄▄      ████ ████           ████ ▇▇▇▇
   ████           ████ ████ ▄▄▄▄ ████ ████           ████ ████
   ████           ████ ████ ████ ████ ████           ████ ████
   ████           ████ ████ ████ ████ ████           ████ ████
                      Oct 20                             Oct 27

                                                       Cost Tokens
Today                                                 $4.55   3.0M
7 days                                               $22.80  15.3M
Since Oct 15                                         $34.60  23.3M
Per pull request                                     ~$5.77

Costliest issues                                       Cost Tokens
#34                                                   $9.15   6.2M
#33                                                   $6.30   4.2M
#32                                                   $4.75   3.2M
#38                                                   $4.50   3.0M
#36                                                   $4.20   2.8M

Model                                                  Cost Tokens
opus-5-5                                             $25.60  17.3M
sonnet-5-5                                            $9.00   6.0M

The loop's records start Oct 16
Claude Code's estimate at API prices, not a bill

──────────────────────────────────────────────────────────────────

Throughput and rework
8 recent issues                                              Count
Blocked                                                          1
Building                                                         1
Opened a pull request                                            6
Took more than one round                                         2

Merged loop pull requests                                    Count
Merged                                                           3
Needed a commit first                                      2 (67%)
  with a fix                                                     1
  only a merge from main                                         1

──────────────────────────────────────────────────────────────────

Evals
Reviewer                         Stable Flaky Failing  Saved Stale
reviewer                              9     1       0 Oct 25   yes
security-reviewer                     8     0       0 Oct 26    no

reviewer stale: 1 file changed, newest Oct 26. Run it again

──────────────────────────────────────────────────────────────────

Conversations
Daily, Oct 15 to Oct 27: most 11.0M tokens on Oct 26
                                        ▄▄▄▄           ████
                    ▁▁▁▁      ████ ▃▃▃▃ ████           ████ ▇▇▇▇
     ████           ████ ▇▇▇▇ ████ ████ ████           ████ ████
     ████           ████ ████ ████ ████ ████           ████ ████
▆▆▆▆ ████           ████ ████ ████ ████ ████ ▃▃▃▃      ████ ████
                        Oct 20                             Oct 27

                                                   Tokens Sessions
Factory                                             49.4M       10
Loop worktrees                                      18.4M        6

Model                                                Factory  Loop
opus-5-5                                               47.0M 18.4M
haiku-5-5                                               2.4M     0

Since Oct 15, cache reads included

──────────────────────────────────────────────────────────────────

Activity
Skill                                       Times Tokens Est. cost
review-pr                                       9   410k     $0.61
learn                                           2      ?         ?

Agent                                       Times Tokens Est. cost
reviewer                                        2   305k     $0.46
security-reviewer                               1      ?         ?

Command                                     Times Tokens Est. cost
standup                                         9   8.2M    $62.12

Guard refused                                                Times
credential-file                                                  1

Est. cost: an estimate from .sanvio/prices.json, checked Oct 1,
worked out Oct 27 12:00. Skills' and commands' tokens are
attributed from where each started to the next prompt.
Guard asked 2 times, since Oct 15
```

</details>

A line separates each section. A section with a chart starts with it, then its
tables: names on the left, figures in right-aligned columns. A row that needs
you is coloured. Red is a failing check, a conflict, a blocked issue, a failing
eval, or a list the pane couldn't read. Yellow is checks still running, a stale
or flaky eval, an eval count it couldn't read, loop pull requests that needed a
commit before merging, and what the guard refused.

Every number comes from [`scripts/dashboard_data.py`](../../../scripts/dashboard_data.py) `--json`, which the
pane runs and draws. That script says where each one comes from and what it
leaves out; this mod adds nothing to them. The daily charts need the version
that gives figures by day, from 2026-10-27.

It's a Claude Code mod, so it works in Claude Code only. It was built on
Claude Code 2.1.308 and seen working in its terminal on 2026-10-27. Codex and
Kiro don't have mods.

## Open it

Type `/factory-dashboard`. In fullscreen, from 110 columns, the pane docks
beside the conversation. Narrower, it sits above the prompt. Close it with the
`×` in its corner.

It isn't on by default. Load it for one session, from the root:

```
claude --plugin-dir examples/mods/factory-dashboard
```

Or install it from inside a session, at the root:

```
/plugin marketplace add ./
/plugin install factory-dashboard@sanvio-factory
```

A change to what the mod does raises `version` in its [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json), because `/plugin update` keeps an installed copy whose version hasn't changed, and CI checks this on every pull request with [`scripts/check_mod_versions.py`](../../../scripts/check_mod_versions.py).

## Reading it

| Section | Shows |
|---|---|
| The header | The factory's folder, and when the numbers were read. **7 days**, **14 days** and **30 days** pick how many days it counts, today among them: 14 until you pick another, and the pick is kept across reloads. Picking one reads straight away, and works out what each skill, agent and command spent again, because only the last range's is kept. **Reading…** on the Refresh button during any read, and the numbers shown stay the last range's until it ends. The first read can take a minute or more, because it goes through every Claude Code transcript and keeps what it found in `.sanvio/cache/`; later reads use that again. What each skill, agent and command spent is kept for 15 minutes, then worked out from the transcripts again. Measured on one machine on 2026-10-30, a read took about 2 seconds with that kept, and 23 to 29 seconds when it was worked out again. Expect that to grow with how many transcripts you have. **Refresh failed** in red when the last refresh didn't work, with the time of the numbers still shown and why under it |
| **Waiting on you** | Each open pull request, how long it has waited, whether it's a draft, its checks and whether it conflicts with its base, then each issue the loop blocked, with why. Red when checks fail or it conflicts, yellow while they run. **conflicts unknown** while GitHub hasn't worked it out. Without `gh`, signed out, or a list in a shape it doesn't know, it says in red that it couldn't read them: never that nothing is waiting |
| **Loop spend** | Three tables: the loop's estimated dollars and tokens today, over the last 7 days, since the date the numbers start and per pull request it opened; the five issues that cost most; and each model, costliest first. Runs that recorded no model show as **model not recorded**. When the loop's records start later than that date, it says when, and the chart starts there |
| **Throughput and rework** | How the loop's recent issues ended and how many took more than one round, then how many of its merged pull requests needed someone else's commit before merging, split into fixes and merges from main |
| **Evals** | Each reviewer's newest saved eval: stable, flaky and failing cases, which ones fail, and **stale** when the agent, a brief, a case or the eval script changed after it was saved. **stale: unknown** when git couldn't say |
| The daily charts | At the top of **Loop spend** and **Conversations**: one bar per day, today in orange, under a line naming the busiest day. The terminal draws them in coloured blocks the width of the pane, with each day and its figures under its bar when the pane has 7 columns a day: cost and tokens for spend, tokens for conversations. Narrower, as for Conversations above, it writes only the day, under every 7th bar counting back from today's. A day whose runs recorded no cost shows **?**, not $0.00. On other surfaces it draws them as a picture whose bars say their day and value when you hover, with every bar's figures under it up to 14 days and every 7th bar's day beyond that; the tests cover Claude Desktop's, and nobody has looked at it in VS Code or the mobile app yet. A `dashboard_data.py` that doesn't give daily figures says so instead |
| **Conversations** | Claude Code's tokens in the factory and in the loop's worktrees, with sessions and the four biggest models. Cache reads are most of it. Its chart covers every day counted, since the factory's own sessions start before the loop's |
| **Activity** | The skills, agents and slash commands you used most, what the guard refused and how often it asked, from your usage log. Skills, agents and commands also show **Tokens** and **Est. cost**, from the transcripts of sessions started at the factory's root, including after they move into [`projects/`](../../../projects/). A session started under [`projects/`](../../../projects/) isn't counted. A subagent's are measured, and a skill's or command's are attributed from where it started to the next prompt. **Est. cost** prices those tokens from `.sanvio/prices.json`, a file you keep yourself: copy [`scripts/prices.example.json`](../../../scripts/prices.example.json), then put in each model you use, from your provider's price list, with the date you checked it. The example's own model and date price nothing of yours. The lines under the tables say when its prices were checked and when the figures were worked out. **?** means no figure, never $0.00: a name the transcripts don't list, or a model with no price. With no price file it says to fill one. **Times** and **Tokens** come from different sources, so don't divide one by the other. A `dashboard_data.py` that doesn't give these figures, or couldn't read the transcripts, draws just **Times** |

A section whose source is missing or can't be read says why, dimmed, and the
rest still show. The range sets every section but **Throughput and rework**'s
issues, which are always the loop's 20 most recent. The loop's spend only goes
back as far as the loop's own records: a run before the loop recorded its usage
isn't in it, so **Since** can match **7 days** in a young factory.

## What it costs and touches

It spends no model tokens: it runs a Python script and draws what it prints.
It runs `python3 scripts/dashboard_data.py --json --since <the range's first day>` once when it opens, then
every five minutes while it's open, and **Refresh** reads now. About every 15 minutes, and when you pick another
range, a read goes through every transcript again. One read runs at
a time, and a refresh that fails keeps the last numbers it had. After you close
the pane it stops at the next five-minute mark; a read already running then
finishes.

The script reads the loop's `.loop/` files, your usage log, `.sanvio/evals/`,
git and every transcript under `~/.claude/projects`, and writes only its own
caches under `.sanvio/cache/`, which is gitignored. Each refresh calls GitHub
through `gh` twice, for the open pull requests and the merged ones, and the
first time it sees a merged loop pull request, once more for its commits. The
[`github-status`](../github-status/) mod reads the same pull requests every two minutes, so the two
can differ for a few minutes.

It runs the script in the nearest folder at or above the one the session
started in that has [`scripts/dashboard_data.py`](../../../scripts/dashboard_data.py). Installed beyond this repo,
`/factory-dashboard` in another repo would run that repo's copy, so open it
only in a repo you trust.

## Changing it

[`hooks/logic.ts`](hooks/logic.ts) turns the script's JSON into the pane's sections, as plain
functions, so they can be tested, and [`hooks/charts.ts`](hooks/charts.ts) draws the daily
charts. [`hooks/register.tsx`](hooks/register.tsx) runs the script and draws the pane. From [`examples/mods/`](../):

```bash
claude plugin validate factory-dashboard
claude plugin test factory-dashboard
```

`python3 -m unittest discover -s tests`, and so the loop, runs these wherever Claude Code is installed. CI doesn't install Claude Code, so it skips them.

After changing how the pane draws, run `python3 scripts/draw_dashboard.py` from the root. It redraws the picture above and its text from [`hooks/sample.ts`](hooks/sample.ts), and [`tests/test_draw_dashboard.py`](../../../tests/test_draw_dashboard.py) fails until you do.
