---
spec: SPEC-003
status: draft
created: 2026-11-13
updated: 2026-11-13
---

# Tasks: SPEC-003

Execution state for this spec. A fresh session resumes from this file's
checkboxes and the Requirement Traceability table. Task IDs run across the whole
spec. Built by hand, never on the loop (the spec's Constraints). `TESTS` below
means:

```
python3 -m unittest tests.test_loop tests.test_agent_hooks
```

## Phase 1: Fork push and rounds (#421)

- [x] T001 Add the `fork` machine key. At start, check it's `OWNER/NAME`, reachable, a fork of `origin`, and owned by the login the loop runs as. Otherwise block each issue with a comment saying why, and push nothing
  - Requirements: REQ-001, REQ-003
  - Acceptance: AC-001
  - Security: SEC-002
  - Depends on: None
  - Verification: `TESTS`
  - Done 2026-11-13: `fork` in `DEFAULTS`, a machine key like the others, a project's entry over the factory's top-level value. `Loop.fork_problem()` and `check_fork()` check it before `worktree()` in `process()`; `TestForkPush` and `TestForkKey`
- [x] T002 With `fork` set, add it as a `fork` remote in the clone and push each `loop/issue-N` there (line 3312), never to `origin`. The merge pass that keeps both [`CHANGELOG.md`](../../../CHANGELOG.md) entries (line 3535) pushes there too
  - Requirements: REQ-001
  - Acceptance: AC-001
  - Depends on: T001
  - Verification: `TESTS`, with two bare local remotes
  - Done 2026-11-13: `Loop.fork_remote()` adds or repoints the `fork` remote; `scale()` and `merge_changelog()` push to `Loop.remote()`; `TestForkPush`, with origin and the fork as two bare remotes
- [x] T003 Open the pull request into `origin`'s base from `<fork owner>:loop/issue-N`
  - Requirements: REQ-001
  - Acceptance: AC-001
  - Depends on: T002
  - Verification: `TESTS`
  - Done 2026-11-13: `gh pr create --head` from `Loop.head_ref()`, and with `fork` set `work()` pins every `gh` call to `origin`'s repo; `TestForkPush`
- [x] T004 `open_pr` checks the fork for the branch, and takes a cross-repository pull request only when its head repository is the configured fork. Any other fork's is still refused
  - Requirements: REQ-002
  - Acceptance: AC-001
  - Depends on: T003
  - Verification: `TESTS`
  - Done 2026-11-13: `open_pr()` asks `ls-remote` on the fork and adds `headRepository,headRepositoryOwner`; `Loop.from_us()` takes only the configured fork's pull request; `TestForkPush`
- [x] T005 A round resets from the fork's branch, not `origin`'s, and updates the same pull request
  - Requirements: REQ-002
  - Acceptance: AC-001
  - Depends on: T004
  - Verification: `TESTS`
  - Done 2026-11-13: `from_remote()`, renamed from `from_origin()`, fetches and resets from the fork's branch; `TestForkPush`
- [x] T006 Without `fork`, the loop pushes to `origin` as today, and every existing test passes unchanged
  - Requirements: NFR-002
  - Depends on: T005
  - Verification: `python3 -m unittest discover -s tests`
  - Done 2026-11-13: `TestWithoutFork`, and `python3 -m unittest discover -s tests`: 2255 tests OK, 3 skipped, with every test that was there before unchanged

## Phase 2: Caller intake

- [x] T007 Add the `caller`, `accept_label`, `acceptors` and `account_tier` machine keys. In caller mode, take `ready_label` and `blocked_label` from the factory's entry and ignore them in the project's own `loop.json`. Refuse to start a caller project with no `network_allow`, a `max_issue_tokens` of 0, or no `account_tier`
  - Requirements: REQ-004, REQ-009
  - Acceptance: AC-006
  - Security: SEC-004
  - Depends on: None
  - Verification: `TESTS`
  - Done 2026-11-13: the four keys in `DEFAULTS`, machine keys. `load_project_config()` takes a caller project's `ready_label` and `blocked_label` from the factory's top level then its entry, never the project's own file, and `project_root()` lets a caller's entry name them. `caller_config_problem()` refuses at start, before `sandbox_problem()`, a `caller` that isn't a bool and a caller project with no `network_allow`, no `max_issue_tokens` budget, no `account_tier`, or `acceptors` or `accept_label` it can't read; `TestCallerKeys`, `TestAcceptance`, `TestCallerIntake`
- [x] T008 Add `actor { login }` to `ISSUE_QUERY`'s `LabeledEvent`. In caller mode, hold an issue (a queue row, a `HELD` log line, no comment) until it carries `accept_label` added by a login in `acceptors`
  - Requirements: REQ-005
  - Acceptance: AC-002
  - Security: SEC-001
  - Depends on: T007
  - Verification: `TESTS`
  - Done 2026-11-13: the hold sits in `discover()` (`Loop.accepted()`), ahead of the dependency check and the pick, so an unaccepted issue is never picked, never starts a worker, and can't hold up an accepted one behind it. `accepted_by()` reads the newest event adding `accept_label` and its actor; GitHub is asked only when the label is on the issue. `fresh()` checks again on its re-read and holds, not blocks, one no longer accepted. `HELD` and `ACCEPT` log lines, the reason as `note` on the queue row; `TestAcceptance`, `TestCallerIntake`
- [x] T009 In caller mode, block an accepted issue that changed after the accept label or holds an HTML comment, naming which, whoever wrote it
  - Requirements: REQ-006
  - Acceptance: AC-003
  - Security: SEC-001
  - Depends on: T008
  - Verification: `TESTS`
  - Done 2026-11-13: `caller_problem()` in `fresh()`, measured from the newest acceptance with no `authorAssociation` trust. It shares `unread()` with `vouch()`, whose behaviour is unchanged; `TestAcceptance`, `TestCallerIntake`
- [x] T010 The work-order check: before the plan step, a caller issue needs `## Objective`, `## Acceptance Criteria`, `## Scope` and `## Verification` sections, each with text. One that doesn't is blocked naming what's missing, before any agent runs
  - Requirements: REQ-007
  - Acceptance: AC-004
  - Depends on: T009
  - Verification: `TESTS`, recording every agent call
  - Done 2026-11-13: `work_order_missing()`, a regex over `##` headings read as `SCOPE` reads Scope, in `fresh()` after acceptance and before any worktree or agent. An `ORDER` line says `complete` or names what's missing, and the block names it; `TestWorkOrder`, `TestCallerIntake`

## Phase 3: Isolation

- [x] T011 For a caller project's build and tester agents, add to `--settings`: sandbox `denyRead` and `permissions.deny` `Read(...)` rules for the factory's private folders and `loop.json`, every other project's clone, and every other project's state folder and worktrees. Set `SANVIO_CONFINE` to the issue's worktree and the clone's `.git`
  - Requirements: REQ-008
  - Acceptance: AC-005
  - Security: SEC-003
  - Depends on: T007
  - Verification: `TESTS`, reading the settings `argv()` builds
  - Done 2026-11-13: `caller_denied()` lists, as written and resolved, the root's private folders, `loop.json` and `.claude/settings.local.json` (`CALLER_ROOT_DENIED`), then each other entry under [`projects/`](../../../projects/) as listed when the settings are built: its clone, its state folder, and its worktree folder under its entry's `worktree_dir`, the top-level one and the default. A path that doesn't exist yet is named anyway. `Loop.argv()` adds them to the sandbox's `denyRead` and, as `Read(//...)` and `Edit(//...)` rules with and without `/**` (`caller_deny_rules()`), to `permissions.deny`. `Loop.held_to()` gives the worktree and the clone's `.git`, resolved, which `env_for_agents(held_to=)` sets as `SANVIO_CONFINE` from `agent()` and `stream()`. The caller's own clone, its `.git`, its worktrees and its state are never named. Outside caller mode, and for a reader or an agent that isn't claude, the settings and environment are as before; `TestCallerConfinement`
- [x] T012 In the guard, with `SANVIO_CONFINE` set, refuse a Read, Edit, Write, Grep or Glob path outside the named folders, and a Bash command naming one
  - Requirements: REQ-008
  - Acceptance: AC-005
  - Depends on: None
  - Verification: `python3 -m unittest tests.test_agent_hooks`
  - Done 2026-11-13: [`.claude/hooks/guard.py`](../../../.claude/hooks/guard.py), job 5. `confined_folders()` reads `SANVIO_CONFINE`; `confined_outside()` refuses a Read, Edit, Write, MultiEdit, NotebookEdit, Grep or Glob whose path, resolved from cwd with links followed, is outside the folders (a Glob by its fixed parts, and any `..` after a wildcard), except a Read of its own session folder under `~/.claude/projects/`, where Claude Code keeps a tool output too long to show. `shell_outside()` refuses a command naming an absolute, `~` or `$HOME` path outside the folders and `SYSTEM_PATHS`, the tool homes and the guard's own Python prefix, any path in the factory's root outside them even under temp, and any `..` that climbs out. An absolute path is checked only when its first folder exists, so `grep '/api/users'` and `awk '/^x/'` pass. A backstop: a path a command builds at run time isn't seen. Unset or empty, nothing changes; `Confined`
- [x] T013 Live check on this machine's Claude Code, with T011's settings in a scratch layout of two projects: the shell's `cat` and the Read tool on the sibling's file are both refused, and the agent's own worktree works. Record the Claude Code version and the result here
  - Requirements: REQ-008
  - Acceptance: AC-005
  - Depends on: T011, T012
  - Verification: the recorded run
  - Done 2026-11-13 on Claude Code 2.1.325 (`claude --version`), macOS, model `claude-haiku-5-5`. A scratch factory under the session's temp folder held `projects/a` and `projects/b`, each its own git repo with one file of made-up text, `loop.json` naming `worktree_dir`, and copies of [`.claude/hooks/guard.py`](../../../.claude/hooks/guard.py) and [`.claude/settings.json`](../../../.claude/settings.json); `a`'s worktree for issue 1 sat outside it, as `~/.sanvio-loop` keeps them. The command and settings came from `Loop(factory, cfg, project=projects/a).argv("agent")` with `caller: true`, `network_allow: []` and `agent` set to `claude -p --permission-mode acceptEdits --model haiku`, and the environment from `env_for_agents(os.environ, (), held_to("agent", worktree))`, less `CLAUDECODE` and every `CLAUDE_CODE_*` variable but the sign-in token, so the run behaved as one started from a terminal rather than from inside the session doing the check. Each probe was one run, cwd the worktree, a one-line prompt naming one tool call, and the outcome read from the tool result: `claude -p --permission-mode acceptEdits --model haiku --settings '<the JSON argv() built>' --output-format stream-json --verbose --max-turns 3`, with `--allowedTools Read,Grep,Glob,Bash(cat:*),Bash(python3:*)` added for the rows that say the tools were allowed, and for a one-layer row `--settings` holding only that layer's key. The sessions' own folders under `~/.claude/projects/` were named as the guard's `session_folder()` works them out. Refusals are each layer's own message:

    | Settings | Probe | Result |
    |---|---|---|
    | As `argv()` builds them | Read `b`'s file | refused: "File is in a directory that is denied by your permission settings" (the deny rules) |
    | As `argv()` builds them | `cat` `b`'s file, and `cat` the factory's `loop.json` | refused by the guard: "is outside this build's worktree" |
    | As `argv()` builds them | Read the factory's `loop.json` | refused by the deny rules |
    | As `argv()` builds them | Read and `cat` its own worktree's file | read |
    | Those, plus `--allowedTools Read,Grep,Glob,Bash(cat:*),Bash(python3:*)` | Read, Grep, Glob and `python3 -c "open(...)"` on `b`, Read on `loop.json` | all refused: Read by the deny rules, the rest by the guard |
    | Deny rules alone, the tools allowed | Read `b`'s file and `loop.json`; Grep and Glob on `b`'s folder | all refused: "denied by your permission settings", and for Grep and Glob "Permission to read ... has been denied", so a `Read(//...)` rule holds both |
    | Guard and `SANVIO_CONFINE` alone, the tools allowed | Read, Grep, Glob and `python3 -c "open(...)"` on `b` | all refused by the guard; its own file read |
    | Sandbox block alone, `Bash(python3:*)` allowed | `python3 -c "open(...)"` on `b`'s file and on `loop.json` | both `PermissionError: [Errno 1] Operation not permitted`; its own file read |
    | Control: `caller: false`, the same tools allowed | Read, Grep and `python3 -c "open(...)"` on `b` | all three read `b`'s text |
    | Control: `caller: false`, as `argv()` builds them | Read and `cat` on `b` | both refused by Claude Code itself: the Read asks for permission, which `-p` can't give, and `cat` outside the working folders is blocked whatever is allowed |

    So each layer refuses the sibling on its own, and the control shows that without them an allowed tool reads it. The control also shows `-p` already refuses an unallowed Read and any `cat` outside the working folders, which is why the per-layer runs allow the tools first. The sandbox started with `denyRead` paths that didn't exist, and with the sandbox on, `cat` on the worktree's own file ran with no `--allowedTools`. With the settings as built, haiku once answered the Grep probe with `ToolSearch` instead of calling Grep; the runs with Grep allowed cover it

## Phase 4: What comes back

- [ ] T014 `auto_merge` never acts on a caller project, whatever its `bases`
  - Requirements: REQ-010
  - Acceptance: AC-007
  - Depends on: T007
  - Verification: `TESTS`, recording every `gh` call
- [ ] T015 A caller's pull request body gets a *Built by* block: the factory's commit, each step's model from the usage record, `account_tier`, and tokens and cost, with cost reading `not reported` where it wasn't
  - Requirements: REQ-011
  - Acceptance: AC-008
  - Depends on: T007
  - Verification: `TESTS`
- [ ] T016 A whole caller run, recorded call by call, posts only its pull request, its review and the comments a hold, block or round needs, each passed through `safe_to_post()`
  - Requirements: REQ-012
  - Depends on: T010, T015
  - Verification: `TESTS`
- [ ] T017 Check that the dashboard shows a caller project's spend as it does any project's. Change nothing if it does
  - Requirements: OBS-002
  - Depends on: T015
  - Verification: `python3 scripts/dashboard_data.py` against a scratch caller project

## Phase 5: The page, and the live runs

- [ ] T018 Write `docs/factory-interface.md`: invented data only (PRIV-001); the account to grant triage to; the labels; the fork workflow settings from *Getting to ready*; what a work order needs; what comes back; how to send it back for a round. Point [`factories/README.md`](../../../factories/README.md) to it and replace "still to decide". Add the keys to [`HOW-IT-WORKS.md`](../../../HOW-IT-WORKS.md), a row to [`README.md`](../../../README.md), and one [`CHANGELOG.md`](../../../CHANGELOG.md) entry
  - Requirements: REQ-013
  - Security: PRIV-001, PRIV-002
  - Depends on: T016
  - Verification: `python3 scripts/link_files.py --check` and `python3 -m unittest tests.test_changelog`
- [ ] T019 A person creates the machine user, a private sandbox caller repo holding invented data, and the fork, and sets the caller entry in this factory's `loop.json`. Nothing tracked names them
  - Requirements: Q5, PRIV-002
  - Depends on: T018
  - Verification: `python3 scripts/check_setup.py` and `loop.py run --dry-run`
- [ ] T020 Live: an outside setup labels one work order in the sandbox repo, a person here accepts it, and a pull request comes back from the fork that the caller's `factories.py status` reads `ready for a person`. Record the run here
  - Requirements: REQ-001 to REQ-013
  - Acceptance: AC-009
  - Depends on: T019
  - Verification: the recorded run
- [ ] T021 Live: someone who has never used this factory follows `docs/factory-interface.md` alone to T020's result. Record every question they had to ask, and fix the page for each
  - Requirements: REQ-013
  - Acceptance: AC-010
  - Depends on: T020
  - Verification: the recorded run

## Requirement Traceability

| Requirement | Tasks | Acceptance | Status |
|---|---|---|---|
| REQ-001 | T001, T002, T003 | AC-001 | done |
| REQ-002 | T004, T005 | AC-001 | done |
| REQ-003 | T001 | AC-001 | done |
| REQ-004 | T007 | AC-002 | done |
| REQ-005 | T008 | AC-002 | done |
| REQ-006 | T009 | AC-003 | done |
| REQ-007 | T010 | AC-004 | done |
| REQ-008 | T011, T012, T013 | AC-005 | done |
| REQ-009 | T007 | AC-006 | done |
| REQ-010 | T014 | AC-007 | open |
| REQ-011 | T015 | AC-008 | open |
| REQ-012 | T016 | none | open |
| REQ-013 | T018, T021 | AC-010 | open |
| AC-009 | T020 | AC-009 | open |
| NFR-002 | T006 | none | done |
