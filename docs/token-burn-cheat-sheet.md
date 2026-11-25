# Token Burn Cheat Sheet

**Spend tokens on judgment, not on re-reading.**

Eight habits that decide what your agents spend, from the factory Sanvio Labs
runs on, which is this repo. The same sheet as a PDF to share, with a diagram for each:
[`token-burn-cheat-sheet.pdf`](token-burn-cheat-sheet.pdf).

Every turn, your agent re-reads everything it's carrying. Most of what you pay
for isn't the question you asked. It's the agent re-reading what it didn't
need, redoing work a script could do, or circling in a loop nobody stopped.

## 1. More agents can mean more cost and less done

Every agent is its own session, re-reading its own context. Every handoff gets
summarized, re-read and sometimes redone. Add agents and you multiply the
reading, not the output.

Start with one agent inside a good factory. Add a second only when you can
name the job the first one can't do.

## 2. Fewer agents, each with one job

- **One role each.** One plans, one builds, one reviews. A reviewer that
  didn't write the code catches what the builder can't.
- **Match the model to the job.** Your strongest model makes decisions and
  writes anything a customer reads. A smaller one does search, sweeps and
  checks.
- **Never downgrade where a miss is silent.** Legal, pricing, security,
  anything going to a customer. A clean report that missed something costs
  more than every token you saved.
- **Don't switch models mid-session.** The prompt cache belongs to the model.
  Switch, and you pay full price to re-send the whole conversation.

## 3. Skills, rules and gates keep it on task

- **Put repeat procedures in skills.** A skill's steps load when its job comes
  up, not in every session.
- **Make deterministic work a script.** Same input, same output? Write the
  code once. A prompt pays for that logic every single time.
- **Gate before you build.** Rework is where the money goes. A check on the
  requirements costs less than three builds.

## 4. Split your instruction files so the agent reads only what applies

One big instructions file gets read in full on every turn, including
everything that has nothing to do with the task in front of it.

- **Keep a short index the agent always reads.** One line per topic, saying
  when it applies: "read when touching infrastructure", "read when pricing".
- **One topic per file.** The agent opens it when its trigger fires, and not
  before.
- **Tie rules to paths.** Infrastructure rules load when the agent touches
  infrastructure files. Nobody has to remember to ask for them.
- **Point at a section, not a file.** Clear headings let the agent read the
  part it needs instead of the whole document.

Loading all 39 of our rule files up front would cost about 46,000 tokens
before anyone typed a word.

## 5. Scale with parallel copies, not more agents

Run the same small crew on several tickets at once, each in its own copy of
the repo. Each copy carries only its own ticket, so throughput goes up and
every run stays cheap.

Cap every run: a maximum number of rounds and a token budget per ticket. A
stuck agent will happily retry all night.

## 6. The flywheel: discover, shape, build, validate, scale, repeat

Each turn starts small and ends at a gate. Discover and shape are cheap. A
build on an unclear ask is the most expensive thing you can run. One workflow
at a time, and the next one starts its own discover.

## 7. Measure where the tokens go, then tighten

You can't cut what you can't see. Every run should leave a record of what it
spent.

- **Log every run.** Run your agent headless and have it report what the run
  used: tokens in and out, cache reads, an estimated cost. Save that with the
  ticket and the step.
- **Add it up by step.** Planning, building, review, retries. The step that
  eats the budget is the process to tighten.
- **Watch the cache.** If cache reads stay low, something keeps changing at
  the front of the context: a switched model, a rule file that keeps moving.
- **Count what produced nothing.** Divide spend by the changes that actually
  merged, not by calls or by the runs that went well. Blocked, retried and
  abandoned runs were paid for too.
- **Change one thing, then compare.** Script a step, split a file, gate
  earlier. Rerun the same job and check the estimate went down.

Estimates are list price, not your bill. Use them to compare runs.

## 8. Quick signs your factory is burning tokens, and the fix

- **Sessions get slower and pricier the longer they run.** Start fresh and
  carry a short summary.
- **The agent re-reads the same files every turn.** Split them and load on
  demand (section 4).
- **Review keeps sending the same work back.** Gate the requirements before
  the build.
- **Your top model runs searches, summaries or watchers.** Hand those to a
  smaller one.
- **Loops hit their cap and nobody asks why.** Read the stuck run before you
  raise the cap.
- **You can't say which step costs the most.** Log every run (section 7).
- **Cost per call drops while the bill climbs.** Measure cost per merged
  change, failed runs included (section 7).
- **You can't say what loads into every session.** Start there.

**A real run, for scale:** one small feature on a demo app. Planned, tests
written first by a separate agent, built in two rounds, reviewed, pull request
opened. Six minutes, 1.4 million tokens, about $3 at API prices.

---

By Pat Santora, Sanvio Labs, [sanviolabs.com](https://sanviolabs.com).
