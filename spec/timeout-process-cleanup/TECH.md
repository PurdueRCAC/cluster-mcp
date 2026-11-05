---
slug: timeout-process-cleanup
title: Stop a timed-out command, and what it started, in every mode
kind: fix
appetite: small
status: done
branch: fix/timeout-process-cleanup
base: develop
current_phase: done
last_updated: '2026-11-04'
phases:
- id: P1
  name: 'The watchdog: local and delegate stopped, and the documents'
  status: done
  satisfies:
  - R2
  - R3
  - R4
  - R5
  - R6
  - R7
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 2
  verify: uv run pytest -q tests/test_timeout_stop.py tests/test_launch.py tests/test_executors.py tests/test_writes.py tests/test_mutations.py tests/test_packaging.py && CI=true uv run pytest -q tests/test_hygiene.py && uv run python -I spec/timeout-process-cleanup/verify/r5-timeout-tests-kept.py && uv run python -I spec/timeout-process-cleanup/verify/develop-fails.py local && uv run python -I spec/timeout-process-cleanup/remediation/term-profile-and-hygiene-rows.py && uv run python -I spec/timeout-process-cleanup/remediation/documented-bound-and-limits.py
- id: P2
  name: 'ssh: the KILL request, the test server acting on signal as sshd does, and the ssh rows'
  status: done
  satisfies:
  - R1
  - R4
  - R5
  - R6
  - R7
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv run pytest -q tests/test_ssh_exec.py && uv run python -I spec/timeout-process-cleanup/verify/r5-timeout-tests-kept.py && uv run python -I spec/timeout-process-cleanup/verify/develop-fails.py ssh && uv run python -I spec/timeout-process-cleanup/remediation/F2-signal-on-open-channel.py
- id: P3
  name: The mutation sweep
  status: done
  satisfies:
  - R4
  - R5
  - R6
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 4
  verify: uv run python -I spec/timeout-process-cleanup/remediation/watchdog-and-hygiene-sweep.py legacy 1 && uv run python -I spec/timeout-process-cleanup/remediation/watchdog-and-hygiene-sweep.py legacy 2 && uv run python -I spec/timeout-process-cleanup/remediation/watchdog-and-hygiene-sweep.py legacy 3 && uv run python -I spec/timeout-process-cleanup/remediation/watchdog-and-hygiene-sweep.py legacy 4 && uv run python -I spec/timeout-process-cleanup/remediation/watchdog-and-hygiene-sweep.py modern 1 && uv run python -I spec/timeout-process-cleanup/remediation/watchdog-and-hygiene-sweep.py modern 2 && uv run python -I spec/timeout-process-cleanup/remediation/watchdog-and-hygiene-sweep.py modern 3 && uv run python -I spec/timeout-process-cleanup/remediation/watchdog-and-hygiene-sweep.py modern 4 && uv run python -I spec/timeout-process-cleanup/remediation/F5-clarification-ids.py
- id: P4
  name: Every login shell, and the deferral ledger
  status: done
  satisfies:
  - R1
  - R6
  depends_on:
  - P3
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: CLUSTER_MCP_TEST_EVERY_KIND=1 uv run python -I spec/timeout-process-cleanup/verify/develop-fails.py all && CLUSTER_MCP_TEST_EVERY_KIND=1 CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_timeout_stop.py
review:
  last_reviewed_commit: 3a4db669067dfc7b99bdf77f53e442526db8a346
  verdict: approved
  blocked_reason: ''
  cycle: 4
---

# TECH.md — Stop a timed-out command, and what it started, in every mode

The **context engine and finite-state machine** for building this fix. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/timeout-process-cleanup/TECH.md`); the per-phase
checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** [`research/00-digest.md`](research/00-digest.md) + briefs 01–06.

## Frontmatter field reference

- `status` (top): `planned | in_progress | blocked | in_review | done` (`done` is stamped by
  `code-publish` after confirmation, just before landing — the terminal state of the retained record)
- `appetite`: `small | big` — caps phase count and build-iteration budget (circuit breaker).
- `branch`, `base`: the cycle's branch (prefix per GOAL `kind`, from the profile's `branches`) and the
  profile's `base`.
- phase `status`: `pending | in_progress | done | blocked`
- `satisfies`: GOAL R-IDs this phase delivers (traceability anchor for `code-review`).
  **Artifact-deliverable R-IDs.** Some requirements are met by a *committed document* — a research
  audit, a protocol doc, an assessment — not by CLI-observable behaviour. Attach such an R-ID to the
  phase that produces and commits the artifact, and give that phase a content `verify:`
  (`test -f …`, a `grep -q` for the sections that must exist) rather than forcing a CLI drive.
  **Say so in the phase body**, because it changes who can grade it: `code-review` blinds its reviewer
  to all of `spec/`, so an R-ID whose evidence lives there is graded by the *orchestrator*, not the
  blind reviewer. Naming it in `TECH.md` is what lets the review skill route it correctly instead of
  reporting an unverifiable requirement.
- `depends_on`: phase ids that must be `done` first (a phase is actionable only when met).
- `parallel`: `true` only for genuinely independent, non-coupled work (docs, tests, isolated leaf
  modules). Any phase touching the profile's `coupled core` is always `false`.
- `hammerable`: `false` marks a correctness/security phase that scope-hammering must **never** cut.
- `hill`: `uphill` (still figuring it out) → `crest` (unknowns resolved) → `downhill` (just
  executing). A phase stuck `uphill` across builds is a raised hand → escalate to the human.
- `attempts`: durable failed-verify counter (absent = 0), bumped by `set_phase.py --phase P<n>
  --record-attempt` on every red verify gate; `next_phase.py` warns at ≥3 — the circuit breaker
  runs on this file, not on session memory.
- `verify`: the exact command that proves the phase (prefer driving the real CLI, not just tests —
  wrap CLI drives in the profile's `throwaway environment` helper, `<helper> sh -c "…"`, so they hit
  a disposable instance, never the developer's real data). A gate carrying `$( )` or quoting the
  calling shell would mangle is set with `set_phase.py --verify-file PATH`, not `--verify`.
- `review.cycle`: completed review passes, auto-incremented by every `set_phase.py --verdict …`;
  REVIEW.md's "Cycle {n}" mirrors it and the ≤3-cycle bound is graded against it. `--verdict approved`
  also clears `review.blocked_reason` unless one is passed explicitly.

## Conventions (apply to every phase)

- Commit conventions, code style, and load-bearing invariants come from the repo's `AGENTS.md` — it
  is the constitution. Walk the sections of its § Invariants that this change touches; that is the
  curated footgun checklist.
- One phase per `code-build` invocation by default; one atomic commit containing **both** the code and
  the `TECH.md` state change. The branch commit subject is code-build's (`$KB/skill/code-build.md` →
  Step 6), not restated here; branch commits are squashed away at `code-publish` per the profile's
  `landing`. Trailers follow the profile's `branch commits`.
- The last phase carries the standing last-phase items: the deferral ledger (`code-plan` Step 6.8),
  and every item the previous cycle's last phase carried for a project-level obligation (mpsearch's
  `## Times` quote, taken as `code-build` Step 4 says). A plan that drops one says why in `PLAN.md`.
- A PR body (when the profile's `landing` opens one) ends with an attribution naming the actual
  harness, model, and variant.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`): the
  help text, docs, or generated files it names change **in the same commit**.

Cycle-specific:

- **Touches the coupled core and a high-blast-radius path** (`core/executor/launch.py`): every phase is
  `parallel: false`, `hammerable: false`.
- **Gate scripts** in `spec/timeout-process-cleanup/verify/` run with `uv run python -I`; each states
  its footprint and runs one pytest child at a time. `tests/mutants.py` is the repo's own runner and
  runs as its usage says (`uv run python tests/mutants.py …`).
- **`tests/test_timeout_stop.py` imports only names that exist on develop at `c8843b2`** (no
  `launch.WATCHDOG` and the like): `develop-fails.py` runs it against develop's `packages/`, and a
  collection error there would make every row fail for the wrong reason. Text-level tests of the new
  constants live in `tests/test_launch.py`.
- **Row names are the gates' interface.** `develop-fails.py` names rows by id
  (`test_a_timed_out_command_is_stopped[<setting>-<shape>]` and the three others in PLAN §2). A
  renamed row changes the gate in the same commit.
- **Measured times** (prototype, macOS, quiet): the new module ≈ 80 s for its 27 representative rows
  (each stop row 3.5 s, survival row 2.6 s, grace row 1.3 s; 79 s measured with the drains row); every
  login shell adds 12 ssh rows (≈ 35 s).
  Time to gone after the deadline: max 1.09 s quiet and under 20-way load; `SLACK = 0.5`. Gates: P1
  ≈ 3.3 min (module 50 s, the four files 66 s, `r5-timeout-tests-kept.py` 25–40 s, `develop-fails.py
  local` 53 s); P2 ≈ 4 min (module 80 s, `test_ssh_exec.py` 115 s, R5 25–40 s, `develop-fails.py ssh`
  29 s); P3 ≈ 5 min (34 mutation cases, estimated from the prototype sweep's per-row times); P4 ≈ 3.5
  min (`develop-fails.py all` with every shell 104 s; the module with every shell, modern era, 95 s).
- Deferrals in this cycle go to `issues/timeout-stop-limits.md` (filed with the plan) and its
  `ROADMAP.md` entry; anything else deferred gets its own seed and entry, never `spec/`.

---

## Phase P1 — The watchdog: local and delegate stopped, and the documents
**Satisfies:** R2, R3, R4, R5, R6, R7 · **Depends on:** —
**Goal:** every program starts the watchdog (PLAN §2); in `local`, root `delegate` and non-root
`delegate` a timed-out command's processes are all gone within `2 × GRACE` of the deadline, pinned
host-free against faithful `sudo` stand-ins; the documents say so in the same commit.

- [x] `launch.py`: add `WATCHDOG` (with `>|`, the arming line, `/bin/sleep` and `GRACE` rendered
      with `format(GRACE, 'g')` at `program()` time), `RELEASE`, and `46>&-` on `SUBSHELL`'s close,
      each a constant of its own; add `m` to `PROLOGUE`'s `set +euxvTkP` (job control off, PLAN §2); `program()` joins `PROLOGUE, WATCHDOG…, sentinel line, …,
      record_line(end), RELEASE, RERAISE`. Keep the watchdog line before the sentinel and starting
      with `trap` (`harness.launched_script` reads `'\nexec '` after the sentinel). Update the module
      docstring, the `GRACE` and `SUBSHELL` comments, and `run_process`'s docstring (the KILL it
      skips at EOF is now the watchdog's).
- [x] `tests/conftest.py`: `RELAY` relays TERM alone with `os.kill(child.pid, …)`; `ROOT_RELAY` (no
      session of its own), with an import-time `assert ROOT_RELAY != RELAY`; `Executions.server_root`
      selects it; fix the comment ("relays only TERM to
      the command's process, as sudo's no-pty path does").
- [x] `tests/test_timeout_stop.py` (new): the `local`, `delegate-root` and `delegate` rows of PLAN §2
      (stop rows with their shapes; both survival rows, the exit and the signal death; grace; the
      startup-file row `[delegate-profile]` with `trap '' TERM`, `set -C` and `set -m`; and
      `test_run_command_stops_a_timed_out_command` through `harness.call` in `local` mode). Each
      shape's top `exec`s its last command; teardown kills each recorded pid's process group (never
      the runner's). Pids written first; a missing pid file fails as "not started before the deadline"; the stop message
      is `still running … after the deadline`; the survival message names "a completed command's
      background job was stopped"; the grace row's message names the lost output. Mode list and
      `EVERY_KIND` hook ready for P2's `ssh-*` settings.
- [x] `tests/test_launch.py`: the launch checker's fixed copies (`PROLOGUE` with `m`; the watchdog
      line; `SUBSHELL_CLOSE` with `46>&-`; the release line between the record and `RERAISE`) and their
      planted cases; `test_the_watchdog_waits_grace` (GRACE patched to 2.5 →
      `/bin/sleep 2.5;`);
      `test_a_watchdog_that_cannot_start_stops_nothing` (the watchdog's process-substitution body, taken
      from the constant, run with stdin already at end of file in a session of its own beside a
      sleeping sibling: the sibling is alive `2 × GRACE` later; a profile cannot reproduce the case,
      PLAN §2). `tests/test_executors.py`'s argv checker likewise (`test_sudo_argv`, `DRIFTS`).
- [x] `tests/mutants.py`: re-anchor `command-exec-in-place` on the new join line, and any prologue
      anchor the `m` moves (`test_mutations.py`'s anchor rows go green).
- [x] Documents, in this commit (R7; PLAN §2 "Documents that change", research 06 for lines): AGENTS §2
      (the watchdog bullet), §3 (replace "A timed-out command may outlive the call" with what is
      stopped, the R4 bound and every limit, linking `issues/timeout-stop-limits.md`; rewrite the
      killed-from-outside limit and the outlives-server bullet), §5 (sudo relays TERM to the launch;
      the watchdog stops the rest, inside the rule), the `launch.py` footgun; README's timeout
      sentence; `ssh._signal`'s and `base.Executor.run`'s docstrings;
      `issues/local-command-outlives-server.md`'s "only the call … signals it". Keep every phrase the
      doc-pinning tests read (`test_separation_texts…`, `test_content_texts…`,
      `test_reconnect_texts…`, research 06). `SECURITY.md` needs no edit (no non-root limit remains):
      say so in the commit body.
- [x] Remove nothing a recorded limit still needs: the `setsid` limit (Q4) stays in §3 as a limit.
- **Verify:** `uv run pytest -q tests/test_timeout_stop.py tests/test_launch.py tests/test_executors.py tests/test_writes.py tests/test_mutations.py && uv run python -I spec/timeout-process-cleanup/verify/r5-timeout-tests-kept.py && uv run python -I spec/timeout-process-cleanup/verify/develop-fails.py local`
  (measured on the P1-cut prototype: see the plan report).
- **Touches:** `packages/cluster-mcp/src/cluster_mcp/core/executor/launch.py`, `…/executor/ssh.py`
  and `…/executor/base.py` (docstrings only), `tests/conftest.py`, `tests/test_timeout_stop.py`,
  `tests/test_launch.py`, `tests/test_executors.py`, `tests/mutants.py`, `AGENTS.md`, `README.md`,
  `issues/local-command-outlives-server.md`, `SECURITY.md` (amendment 1).
- **Amendments at build (2026-11-01):**
  1. `SECURITY.md` gains one sentence, where the plan said none. R3 holds in full, so Q3's
     narrowing does not arise, but two limits remain that only a non-root server has (a login
     initialisation that ignores TERM and hangs; a TERM lost in the watchdog's fork window, both in
     `issues/timeout-stop-limits.md`), and R7 asks a non-root limit to be stated where an operator
     choosing a service account reads it: "For Multi-User Production".
  2. `issues/local-command-outlives-server.md`: a dated, append-only correction under its cases
     (code-build Step 2.3: an `issues/` entry is point-in-time evidence), not a rewrite of the
     sentence.
  3. AGENTS §3 and the README name, until P2, a TERM ignored by a remote login shell's own rc file
     as a limit over `ssh`, so the documents are true of P1's code; P2's KILL request removes it
     from both (add to P2's document item).
  4. The grace row's TERM handler first ignores TERM: otherwise the watchdog's second TERM, ms after
     the deadline's, kills the handler's `sleep` and the row passes with no wait (planting a zero
     delay left `[local]` green). Survival and grace rows run in all three P1 settings.
  5. `test_executors.py`'s `DRIFTS` gains `no-watchdog` and `no-release`; the launch checker gains
     planted `job-control-kept`, `no-watchdog`, `watchdog-clobber`, `watchdog-descriptor-kept`,
     `no-release`, `release-before-record`, `release-after-reraise`. AGENTS § Testing describes the
     new module, the watchdog rows and both `sudo` stand-ins.
  6. `issues/stalled-reconnect-test-timing.md` gains a dated note (PLAN §5): the loopback flake
     `test_startup_output_is_separated` failed once on `[bash]` in a local full-suite run of this
     branch (modern era), and passed three times alone; it is not in any P1 gate.

- **Remediation, review cycle 1 (2026-11-02; F1, F3, F4; bundled with P2, below).** Reopened with
  `set_phase.py`. P1 and P2 commit together: R7 puts the documents in the commit of the code they
  describe, and AGENTS §3, the README and the limits seed state both the watchdog's wait (F1, here)
  and the KILL request's guard (F2, P2). The gate is the frozen one, then the checkers
  `remediation/F1-never-on-time.py` and `remediation/F3-documented-limits.py`.
  - [x] **F1, the class (found by reading).** Every builtin the watchdog's line ran, and how a
        startup file can make it return early: `read` takes `TMOUT` as its default timeout (a readonly
        `TMOUT` cannot be unset or shadowed by `local`, and bash 4 and later accept a fractional one);
        `enable -n read` hands the wait to an external `read` (macOS's `/usr/bin/read`, a shell running
        the builtin, which takes an exported `TMOUT`); bash looks a function up before an absolute
        path, so a profile's `/bin/sleep` (measured, bash 3.2) or `/bin/cat` function runs in its place,
        and the prologue's `unset -f` list named neither. Ruled out by reading: a trap (a subshell resets
        every trap, keeping only ignores, so no handler runs in the watchdog and SIGCHLD, SIGWINCH or
        SIGALRM interrupt nothing; `$( )`'s read of its pipe retries on EINTR); a readonly
        `cluster_mcp_w` (bash 3.2's `read` reports the error and returns 0).
  - [x] **F1, the fix.** `WATCHDOG` waits through `[[ $(/bin/cat && printf .) == $'\n.' ]]`: `cat`
        reads the pipe to its end, which only the program's exit brings, and the stop runs only when what
        it read is the arming line alone and `cat` read to the end (nothing read, or both lines, or a
        `cat` that did not finish, stops nothing). The line first unsets the functions `/bin/cat` and
        `/bin/sleep`, after the prologue's `set +o posix` (a posix-mode bash refuses such names to
        `unset -f`). No builtin waits, so it holds in bash 3.2 (measured), 4.4 and 5.x (no construct newer
        than bash 2: `$( )`, `[[ ]]`, `$'…'`; the CI era jobs run bash 5 on Linux), in every login shell
        (the program is bash whatever the login shell; `EVERY_KIND` rows). The watchdog now exits when
        the program does, not at the release.
  - [x] **F1, pins** (`tests/test_timeout_stop.py`): `test_a_profile_tmout_stops_nothing[<setting>-no-timeout|timeout]`
        (a `.bash_profile` with `TMOUT=1`, readonly and exported; a command that starts a background job
        and runs 2 s; with no timeout and with 20 s: output `done`, exit 0, job alive), in `local`,
        `delegate-root`, `delegate`, `ssh-bash` (every `ssh-<shell>` under `EVERY_KIND`);
        `test_run_command_outlives_a_profile_tmout` (the tool, `local`, no timeout); the other routes,
        `test_a_profile_cannot_cut_the_watchdogs_wait_short[local|delegate]` (`read` off beside an
        exported `TMOUT`, functions `/bin/cat` and `cat` and a PATH `cat` answering the arming line;
        every setting under `EVERY_KIND`); the grace rows' profile gains a `/bin/sleep` function.
  - [x] **F1, red first on `386efa3`** (tests from this tree, `packages/` from `386efa3`, scratch copy):
        all eight `test_a_profile_tmout_stops_nothing` rows and the tool row fail, each "the command did
        not complete with its output", stdout empty, exit 143 in every mode, `Terminated: 15` and the
        unfinished note, and "background job was stopped"; both
        `test_a_profile_cannot_cut_the_watchdogs_wait_short` rows fail the same way (the external
        `read` took `TMOUT`); all four grace rows fail "was lost" (the `/bin/sleep` function). The
        sweep's `tpc-unset-*` and `tpc-wait-*` cases show the new routes red on this tree with the
        defence removed.
  - [x] **F3.** AGENTS §2 (the watchdog's wait), §3 (the wait, the KILL's guard, and the limits as a
        list, each per mode), §5 (a pointer to the limits under a non-root server), the `launch.py` and
        `ssh.py` footguns, § Testing; the README's timeout sentence; `SECURITY.md`'s non-root edges (three:
        the hanging startup file, a command a TERM-ignoring startup file starts after the deadline,
        the forking window); `issues/timeout-stop-limits.md` and its `ROADMAP.md` entry rewritten in
        place (unlanded, so no dated notes), the seed's own dated notes folded in. Each limit was
        measured before it was written: `test_a_recorded_limit` (37 rows, run with
        `CLUSTER_MCP_TEST_LIMITS=1`) shows, per mode, what runs on past the bound and what is stopped,
        and the reviewers' two cases are its `hang-child-ignoring-ssh-bash` (runs on) and
        `late-start-delegate` (the command starts after the deadline and runs on) rows. New by
        measurement: in `local` and under a root server too, a startup file's process that ignores TERM
        and holds no stream of the call runs on (`hang-child-ignoring-unheld`). The checker maps every
        documented limit to its rows and its phrase in each document.
  - [x] **F4.** `MODES['delegate']` gains `ignores-none`: `test_a_timed_out_command_is_stopped[delegate-ignores-none]`.
  - **Gate, green** (macOS, bash 3.2, legacy era; each distinct step of P1's and P2's gates run once on
    the final tree, logged): the five files, 1,546 passed and 37 skipped (the `test_a_recorded_limit`
    rows, which run only with `CLUSTER_MCP_TEST_LIMITS=1`, as the F3 checker runs them) in 149 s; the
    R5 gate, "17 timeout tests and 290 names unchanged since c8843b2, 32 rows, every one passed", 27 s
    (it stands in for P2's identical step); `develop-fails.py local`, 76 s; the F1 checker, 29 profile
    rows in every mode and login shell, 62 s; the F3 checker, 7 limits and 37 rows, 133 s.
    That run made P1 done at `47154af`; P3's red (below) reopened it with these changes.
  - **Attempts 2 and 3, recorded with `set_phase.py`; P1 reopened.**
    - *CI on `35b6773`* (the foreman pushed it for a Linux bash 5 run), both era jobs:
      `test_hygiene.py::test_only_need_shell_skips` failed, "a test can skip on CI without failing:
      tests/test_timeout_stop.py:577: skipif", the limit rows' `skipif`. It bites only with
      `CI=true`, so the local P1 run passed it. Every other row passed on Linux bash 5 (4,749 passed,
      37 skipped per era; 7 min 42 s and 9 min 17 s): the new wait, the `TMOUT` rows and the F2 rows
      held there. Fix: `test_a_recorded_limit` is defined only under `CLUSTER_MCP_TEST_LIMITS=1` (an
      `if LIMITS:` at module level), so the suite collects no limit row and skips nothing; the F3
      checker sets the variable. P1's gate gains `CI=true uv run pytest -q tests/test_hygiene.py`.
    - *A rerun after P3's fix*: the F3 checker failed `test_a_recorded_limit[term-twice-ssh-bash]`,
      "the command handled TERM 1 time(s), not 2" (it counted 2 in the first run). The deadline's TERM
      and the watchdog's come milliseconds apart, and the kernel merges the second into the first when
      it comes before the first is handled. The limit is "may get it twice": the row accepts 1 or 2
      where both TERMs reach the handler and exactly 1 under a non-root `delegate` server, and AGENTS
      §3, the seed, its ROADMAP entry and the checker's map say "may get it twice".
  - **Gate, green, rerun** (every step of P1's, P2's, P3's and P4's gates once, from the start, on the
    final tree, logged, host load 1–4.5): the five files, 1,546 passed and none skipped, in 150 s;
    `CI=true` hygiene, 74 passed, 2 s; the R5 gate, "17 timeout tests and 290 names unchanged since
    c8843b2, 32 rows, every one passed", 26 s (standing in for P2's identical step);
    `develop-fails.py local`, 81 s; the F1 checker, 29 profile rows, 61 s; the F3 checker, 7 limits and
    37 rows, every row passed, 133 s.

- **Remediation, review cycle 2 (2026-11-04; F1–F4, F6–F8; the maintainer's rulings at the bound: "Fix +
  scoped review", F2 "KILL only, after grace", F1 and F4 "Document the limit").** Reopened with
  `set_phase.py`; its gate retuned with `--verify-file`: the frozen steps, `tests/test_packaging.py`
  added to the files, then `remediation/term-and-profile-rows.py` and `remediation/documented-stop.py`,
  which supersede cycle 1's `F1-never-on-time.py` and `F3-documented-limits.py` (kept as the record:
  the first expected the non-root grace row to print, which only the second TERM made it do; the
  second mapped four limits this cycle closed or ruled). `tests/mutants.py` moves in this commit too:
  its anchors on the program text and on the backends' `program(…)` lines are what
  `tests/test_mutations.py`, in this gate, applies.
  - [x] **F2, the class (found by reading).** Every signal a timeout sends and to whom: the server's
        TERM (`run_process` to the group; `sudo`'s relay to the program; sshd to the group), the
        server's KILL (`run_process`; the KILL request), and the watchdog's TERM and KILL. Only the
        watchdog's TERM is ever a process's second. The fix: the watchdog waits `GRACE` and sends KILL
        alone (`{ /bin/sleep G; kill -s KILL 0; }`); a command past its deadline (F3) kills only the
        program. Statements of it: AGENTS §2, §3 (and the limit), §5, the `launch.py` footgun, README,
        `SECURITY.md`, the seed and its `ROADMAP.md` entry, the branch's own note in
        `issues/local-command-outlives-server.md`, `launch.py`'s module docstring, the `GRACE` comment
        and `run_process`'s docstring; all rewritten.
  - [x] **F3, the class.** Every moment between the deadline and the command's start at which the
        program's TERM disposition is not the default, so the deadline's TERM can be lost: the login
        initialisation (a startup file's trap or ignore) and the fork (cycle 1's `trap '' TERM` around
        it). The fix: the watchdog's line takes TERM's default back first and forks after it, the
        watchdog ignoring TERM from its own first statement, so a TERM that reaches the program at any
        point from there ends it (simpler than the review's handler around the fork, with the same
        outcome for the command, which has not started; no deferred state a startup file's variable
        could preset); and where the program runs on the server's host (`local`, `delegate`),
        `program(…, timeout=…)` writes the server's deadline (epoch nanoseconds, taken before
        `run_process` takes its own) into `DEADLINE_CHECK`, which reads `/bin/date +%s%N` once TERM's
        default is back and never starts a command past it: it waits up to `GRACE` for the server's
        TERM (so the call reads as the timeout it is), then TERM, then KILL, on itself. No right
        beyond `SECURITY.md`'s sudo rule: everything runs as the mapped user in the program. Over
        `ssh` the clock is not shared, and the KILL request after the grace stops a late command (the
        row shows it). A `date` with seconds only delays the check by under a second; an unreadable
        one skips it (both stated in the constant's comment).
  - [x] **F1 and F4, the class.** Every builtin and absolute path the program's own lines run, and
        each way a startup file can shadow one: a function over a builtin (`unset`, `unalias` and
        `enable` included), `enable -n`, an alias, a function named like a path (`/bin/cat`,
        `/bin/sleep`, and now `/bin/date`), a readonly function. Closed (the cheap cases): the prologue
        enters posix mode by assignment (`POSIXLY_CORRECT=y`, which no function can shadow), unsets a
        function named `enable`, turns `BUILTINS` back on, unsets their functions (posix mode finds the
        special builtin `unset` before a function of its name), drops aliases again, leaves posix mode,
        then unsets the path functions. Measured on bash 3.2: a slash-named function still runs in
        posix mode, and `unset -f` refuses it there (so that step stays out of posix mode); posix mode
        has no process substitution in bash before 5.1 (so the watchdog's line runs after it);
        `set +o posix` unbinds `POSIXLY_CORRECT`, as the prologue already did, and turns alias
        expansion off on 3.2, so the alias route the second `\unalias -a` closes matters only where a
        newer bash restores the profile's setting on leaving posix mode (not run here). Argued
        for 4.4 and 5.x from the manual: the special builtins come first in posix mode since 2.x,
        `POSIXLY_CORRECT` set while running enables it, `enable` re-enables a disabled builtin.
        Recorded as the limit: a readonly function, an `enable` function beside a disabled `unset`,
        `enable -n enable`, aliases on the prologue's own second line. Every statement of the promise
        made true: §3's "the command's processes have all exited…" and "no startup file's…" sentences
        qualified by the limit, README's "never signalled by the stop" likewise, §2 gains a prologue
        bullet and its watchdog bullet loses the unset; the limit (both effects, a stop that fails and
        a command stopped early) in §3, README, the seed and its entry.
  - [x] **F6.** AGENTS § Testing and § Conventions name `Q#` beside `R#`, `P#`.
  - [x] **F7.** AGENTS §3 (beside "a launch that dies before its records") and the README: a lost
        reader's program dies of SIGPIPE writing its end record once the command ends, before the
        release, so the group is stopped, background jobs included. No code change.
  - [x] **F8.** The `Dockerfile` installs `tini` and runs `ENTRYPOINT ["/usr/bin/tini", "--",
        "cluster-mcp"]`: it holds for `docker run` and for `compose.yml`, which builds the image and
        overrides only `command:` (`--init` would hold only where stated). Pinned by
        `tests/test_packaging.py::test_the_image_runs_an_init_that_reaps_orphans`. That the server, as
        PID 1, accumulates zombies is reasoned, not measured: no Linux container or subreaper here;
        the server waits only for the children `subprocess` started, and a watchdog or a command's
        job that outlives its program is re-parented to PID 1.
  - [x] **Pins** (`tests/test_timeout_stop.py` unless named): `test_a_stopping_command_gets_its_grace`
        (`local`, `delegate-root`, `ssh-*`: a handler that stops on its first TERM and exits at once on
        a second prints `stopped cleanly`; it and a child count one TERM each);
        `test_a_non_root_server_kills_after_the_grace_with_no_term` (no TERM, both alive `GRACE / 2`
        after the deadline, gone by the bound); `test_a_command_past_its_deadline_is_stopped[4]`
        (`trap '' TERM`, functions `date` and `/bin/date` answering 0, a 1.5 s login: nothing runs past
        the bound; the command never starts in `local` and both `delegate`);
        `test_a_term_while_the_watchdog_forks_is_kept[4]` (a startup file's TERM ignore, the window
        planted 1.5 s before the fork, a TERM sent to the program alone, no deadline to fall back on);
        `test_a_profile_shadowing_unset_stops_nothing[local|delegate-unset-function|unset-disabled]`
        (every setting under `EVERY_KIND`); `test_a_profile_shadowing_the_watchdog_is_undone`
        (`enable -n trap` beside an `enable` function in `local`, `delegate-root`, `ssh-bash`; an
        `unalias` function and `alias kill=:` in `local`); the limit rows `shadowed-stop-*` and
        `shadowed-early-*`; `tests/test_launch.py`: the fixed copies, `test_a_program_given_a_timeout_checks_its_deadline`,
        the planted `builtins-unset-out-of-posix-mode`, `builtins-not-enabled`, `path-functions-kept`,
        `watchdog-term`, `watchdog-restored-after-fork`, and the deadline check's wait in
        `test_the_watchdog_waits_grace`. Removed: the limit rows `term-twice`, `late-start`,
        `fork-window` and `enable-n-trap`, now the pins above.
  - [x] **Red first on `50a1ad3`** (this tree's tests, `50a1ad3`'s `packages/` and `Dockerfile`, a
        scratch copy; 19 failed, 2 passed): the three grace rows ("other than one TERM: {'top': 2,
        'child': 2}", stdout `started\nsecond TERM: exiting now`); the non-root row ("a TERM under a
        non-root server: {'top': 1, 'child': 1}"); late start in `local` and `delegate-root` ("started
        after its deadline") and `delegate` ("login, top still running 2.52 s after the deadline");
        the fork window in all four settings (every process "still running", the call went on); the
        four shadowed-`unset` rows (exit 143, "background job was stopped"); the three `enable -n trap`
        rows (child and grandchild still running); the image row (`["cluster-mcp"]`). Passed, as
        expected: late start over `ssh` (stopped there before) and the kill-alias row (bash 3.2's
        `set +o posix`, already in `50a1ad3`'s prologue, turns alias expansion off).
  - **Gate, green** (macOS, bash 3.2, legacy era unless named, host load 1.6–3.7, every step once on the final tree, each logged; the run after P3's attempt 2): the six files, 1,611 passed, none
    skipped, 181 s; `CI=true` hygiene, 74 passed, 2 s; the R5 gate, "17 timeout tests and 290 names
    unchanged since c8843b2, 32 rows, every one passed", 27 s (it stands in for P2's identical
    step); `develop-fails.py local`, 106 s; `term-and-profile-rows.py`, 55 rows in every mode and
    login shell, 113 s; `documented-stop.py`, 4 limits shown by 29 rows, 22 promises, nothing stale,
    94 s. Before the gates, the whole suite once (legacy era): 4,797 passed and 14 skipped (the bash
    4.1 rows CI runs), 522 s.
  - **Suite growth per era**, from the added rows alone (the suite's JUnit times against the node
    ids `50a1ad3` collects): 86 rows new (60 of them mutation-anchor rows of milliseconds), 31 s,
    about 6 % of the 520 s suite here; CI's era jobs ran ≈ 8 min each against their 20-minute
    timeout on `50a1ad3`.

- **Remediation, review cycle 3 (2026-11-04; B1–B5, N1, N3 and the `kill-alias` row; bundled with P2,
  below; past the review bound, the maintainer's rulings "Fix, I verify, land", B1 "Reword R4 to the
  bound", B5 "Document the limit", and the foreman's routes for the rest).** Reopened with
  `set_phase.py`. P1 and P2 commit together: R7 puts the documents in the commit of the code they
  describe, and AGENTS §3 states both the fork window's two sides (the deadline's check here, the
  KILL request over `ssh`, P2) and the program given no deadline over `ssh` (N1, P2); the stop
  module, which both gates run, carries both phases' rows. The gate is retuned with `--verify-file`:
  the frozen steps, then `remediation/term-profile-and-hygiene-rows.py` and
  `remediation/documented-bound-and-limits.py`, which supersede cycle 2's `term-and-profile-rows.py`
  and `documented-stop.py` (kept as the record: the first read the watchdog line review cycle 3's B3
  retired and expected the fork-window rows and the `kill-alias` row; the second promised that a TERM
  while the program forks ends it before its command starts, kept "no later than before" and "to the
  nanosecond", and lacked the clock's limit). `tests/mutants.py` moves in this commit too (its
  anchors are what `tests/test_mutations.py` applies).
  - [x] **B1, the class (by reading).** Every statement that `run` returns a timed-out call no later
        than before the watchdog, or than a launcher without it: AGENTS §3 (≈2255) and § Testing, the
        stop module's docstring and its return message. README, `SECURITY.md`, the seed and the
        docstrings made no such claim. **Fix:** the check's `GRACE` wait stays (the ruling); §3 says
        `run` returns a timed-out call within 2 × `GRACE` of the deadline (the server's drains, or
        the `GRACE` read over `ssh`, bound it whatever the program does), as do README's timeout
        sentence, `Executor.run`'s docstring, `launch.py`'s docstring and `GRACE` comment, and the
        stop module. **Pins:** `return_violations` now checks the bound (`HELD`, 2 × `GRACE` +
        `SLACK`) in every timed-out row that measures cheaply: the late-start rows in every setting,
        the window rows, the startup-file, hanging-login, grace and watchdog-shadow rows (the stop
        rows already checked it, or `GRACE / 2` where a launcher without the watchdog returns at
        once). **Measured** (the reviewer's repro, profile `trap '' TERM; /bin/sleep 1.3`, `echo ran`,
        timeout 1, five calls each, from the call): on `c16f19b` `local` 2.00–2.01 s, root `delegate`
        2.00–2.01 s, non-root `delegate` 2.35–2.37 s, `ssh-bash` 1.35 s; on this tree 2.00, 2.00–2.01,
        2.36–2.37 and 1.34–1.39 s (the same: the wait stays); under 20-way CPU load 2.01, 2.00–2.01,
        2.41–2.44 and 1.40–1.42 s. Every timed-out row's return, the stop module run whole: at most
        1.61 s after the deadline quiet and 1.63 s under 20-way load (non-root `delegate`, late start
        and windows), against 2.5 s. No program-side change can push the return past the bound while
        the drains stand, so the pins are red only for a server-side one: `tpc-return-grace-read-tripled`
        (P3).
  - [x] **B2, the class (by reading the rendered program).** Every name the program's lines set before
        the command: the prologue's (`POSIXLY_CORRECT`, unbound by leaving posix mode, and now
        `cluster_mcp_o`), the subshell's restore loop (`cluster_mcp_x`), the deadline's check
        (`cluster_mcp_n`, never unset) and the function export (`cluster_mcp_fn`, unset). `set -a`
        exports each as assigned, and a profile's `export` of the name beforehand does the same; the
        watchdog line sets none. **Fix:** each is unset before the command starts (`unset
        cluster_mcp_n` ends the check's line; the restore ends with `unset cluster_mcp_o
        cluster_mcp_x`). Out of the class (pre-existing, the same on `develop`): `BASH_ENV=` and
        `ENV=`, set on purpose for the script's bash; `PWD` and `OLDPWD`, which the subshell's `cd`
        sets as any shell's does. **Pin:** `test_no_variable_of_the_program_reaches_the_command[local|
        delegate-root|delegate|ssh-bash]`: the names a command's `env` shows under a profile that sets
        `-a` and exports every `cluster_mcp_` name the program's text holds, against those under no
        profile, with a timeout. **Red first on `c16f19b`** (the rows from this tree): `local`,
        `delegate-root` and `delegate` fail, "under a profile's `set -a` the command sees the
        program's own ['cluster_mcp_n']"; `ssh-bash` passes (no deadline there).
  - [x] **B3, the class.** Every instant from the fork to the watchdog's own ignore at which a TERM to
        the group could end it: on `c16f19b` the program took TERM's default back and forked, the
        child ignoring TERM only from its first statement. **Fix** (the suggested shape): the program
        forks the watchdog with TERM ignored, so it is born ignoring it, then takes TERM's default back
        (which still undoes a startup file's trap or ignore). A TERM that reaches the program in
        between is lost; the server sends TERM only at the deadline, so in `local` and `delegate` the
        deadline's check, the next line, refuses the start (cycle 2's F3 property holds there: the
        TERM ends the program before its command starts, or the command never starts). **Over `ssh`**
        there is no check: the command starts, and since the program lives, the channel is open after
        the `GRACE` read and the KILL request goes, which sshd delivers to the session's whole group
        (`session_signal_req`, `killpg`), so the command and the watchdog are KILLed `GRACE` after the
        deadline. A TERM sent by anything but the server, with no deadline near, is now lost in that
        window: cycle 2's fork-window rows sent exactly that and are replaced. **Pins:**
        `test_a_deadline_while_the_watchdog_starts[<setting>-program|<setting>-watchdog]` in `local`,
        `delegate-root`, `delegate`, `ssh-bash`: a 1.5 s window planted right after the fork, found by
        matching the process substitution's parentheses (`program`), or right after `>(`, before the
        watchdog's first statement (`watchdog`); the deadline of 1 s comes inside it; the command is
        the `ignores-none` shape. Each row checks the window opened before the deadline, every
        recorded process gone by the bound, the call a timeout returned within the bound, and, for
        `program` off `ssh`, the command never started. **Red first on `c16f19b`** (the reviewer's
        plant, as `watchdog`): `local-watchdog`, `delegate-root-watchdog` and `ssh-bash-watchdog` fail,
        "child, grandchild still running 2.51 / 2.55 / 2.56 s after the deadline"; `delegate-watchdog`
        passes (no TERM reaches the group there); every `program` row passes (that window was at
        TERM's default there). `test_launch.py`'s checker gains `watchdog-born-with-term` and
        `watchdog-term-left-ignored`.
  - [x] **N3, the class.** Every shell option the prologue's posix-mode round trip changes that a
        command can see: through `BASHOPTS`, exported by a startup file, every bash the command starts
        takes them (bash 4.1 and later); on leaving posix mode bash 4.4 and later leave
        `inherit_errexit` on and turn `expand_aliases` and `shift_verbose` off, saving nothing for
        posix mode entered by an assignment (read from bash's source by the reviewer; not run here).
        **Fix:** the prologue saves `BASHOPTS` first (`cluster_mcp_o`, empty before 4.1); the command's
        subshell, as its first line (`RESTORE_OPTIONS`), turns off every option on now but not then and
        turns on every one on then but not now, errors to `/dev/null`, then unsets both names; `shopt`
        joins `BUILTINS`. It runs in the subshell alone, so the program's own lines keep alias
        expansion off (which is why the second `\unalias -a` stays an equivalent). **Pins:** on this
        host (bash 3.2, which has no `BASHOPTS` to hand on) the launch checker's fixed copy of the
        restore line right after the subshell opens and the saved list in the prologue, with planted
        `options-not-restored`, `option-names-kept`, `options-not-saved` and
        `aliases-not-dropped-again`; where the interpreter is bash 4.4 or later (CI's bash 5),
        `test_a_command_sees_the_shell_options_its_profile_left[<setting>]`, every setting, defined at
        collection by the version (never a skip): a profile `shopt -s expand_aliases shift_verbose;
        export BASHOPTS`, a command `shopt -p inherit_errexit expand_aliases shift_verbose`, expected
        `-u`, `-s`, `-s`. **Not run here:** that row, and the restore on any bash with `BASHOPTS`; run
        here: the restore's logic against a stub `shopt` and an assigned `BASHOPTS` on bash 3.2 (it
        turned off `d` and on `a` for a saved `a b c` and a current `b c d`, and unset both names).
        - 2026-11-04: review cycle 3 verification: N3 not reproduced (the round trip does not refresh
          `BASHOPTS`); the restore is removed, the row kept as a regression pin (below).
  - [x] **B5, the ruling's documents.** §3 states the clocks exactly (the program's deadline on the
        wall clock, `time.time_ns()` at rendering, against `run_process`'s monotonic one; `/bin/date
        +%s%N`, nanoseconds from GNU `date`, microseconds from macOS's, measured here) and a fifth
        limit, the wall clock's step during the login initialisation: forward, a command refused
        early (`-1002`); back, a late one started, stopped by the server's KILL in `local` and under a
        root server, running on under a non-root one; not over `ssh`. The seed gains it (with an R4 in
        its sketch), its `ROADMAP.md` entry and README and `SECURITY.md` (the non-root edge) say it.
        **Limit rows** (`CLUSTER_MCP_TEST_LIMITS=1` only): `clock-forward-<setting>` and
        `clock-back-<setting>`, `local`, `delegate-root`, `delegate`, the step simulated by moving
        `time.time_ns()` as the program is rendered.
  - [x] **`kill-alias`, removed** from `WATCHDOG_SHADOWS`: it pins nothing on bash 3.2–5.3. The
        launch checker's copy of the prologue pins the second `\unalias -a`, with a planted
        `aliases-not-dropped-again`; the sweep records the drop as an equivalent (P3).
  - **Gate:** see P2's entry below (one run for both, every step of P1's, P2's and P3's gates once).

- **Remediation, review cycle 3 verification (2026-11-04; N3 not reproduced; under the maintainer's
  "Fix, I verify, land", the foreman's ruling: remove the restore, keep the behaviour row as a
  regression pin).** Reopened with `set_phase.py`; its gate unchanged (the frozen steps and the two
  remediation-3 checkers, edited in place, each now saying "review cycle 3 verification, N3").
  - **The measurement (the foreman's, binding).** Read-only probes on the test clusters (`bash
    --norc --noprofile -c`: `shopt -s expand_aliases shift_verbose; shopt -u inherit_errexit`, then
    `POSIXLY_CORRECT=y; set +o posix`, then `export BASHOPTS` and a child `bash --norc`): on bash
    4.4.20 the shell shows `inherit_errexit` on and `expand_aliases` off after the round trip, and
    the child the original options; on 5.1.8 the same, with `shift_verbose` off in the shell too.
    `set +o posix` resets the options internally and does not refresh `BASHOPTS`, so a fresh bash
    imports the stale (the login's) list. On CI's bash 5.2 a throwaway branch with the restore's
    line dropped passed all four `test_a_command_sees_the_shell_options_its_profile_left` rows; only
    the text pins failed. `$BASHOPTS` always equalled the saved list, so the restore's loops did
    nothing.
  - [x] **Removed.** `RESTORE_OPTIONS` and its place as the subshell's first line (`lines = []`, as
        on `076ade4`); the prologue's `cluster_mcp_o` save; `shopt` from `BUILTINS` (added only for
        the restore); `cluster_mcp_o` and `cluster_mcp_x` from B2's class (B2's pin still holds for
        every name that remains, `cluster_mcp_n` and `cluster_mcp_fn`). The launch checker's
        `RESTORE_LINE` and its planted `options-not-restored`, `option-names-kept` and
        `options-not-saved`. In `tests/mutants.py`: `tpc-option-names-kept`,
        `tpc-builtins-without-shopt`, the six `tpc-options-*` cases and the five `-behaviour` cases,
        with `OPTIONS_KEPT` and the bash-version probe that defined them; the restore's edit inside
        `tpc-allexport-off-instead`; the anchors of `prologue-unalias-shared-line` and
        `prologue-read-function-kept` back to `076ade4`'s.
  - [x] **Kept.** `test_a_command_sees_the_shell_options_its_profile_left[<setting>]` (bash 4.4 or
        later, defined at collection, never a skip), its comment corrected: the row passes with
        nothing set back, and is the pin that the program runs nothing that refreshes `BASHOPTS`
        before the command. `aliases-not-dropped-again` and `tpc-aliases-kept-text`, which pin the
        second `\unalias -a`, independent of the restore.
  - [x] **The fact, stated once.** `launch.py`'s prologue comment and AGENTS § Invariants (the
        prologue's bullet): the round trip changes the program's own options (`expand_aliases`
        off in bash 3.2, 4.4 and 5.1; `inherit_errexit` on in 4.4 and 5.1; `shift_verbose` off in
        5.1); it does not refresh `BASHOPTS`, so a bash the command starts gets the login's options
        (4.4, 5.1, 5.2); so the program never runs `shopt`, or anything else that refreshes
        `BASHOPTS`, before the command. AGENTS' launcher list (§ Invariants) and § Testing's
        launch-checker sentence lose the restore; the stop module's B2 comment loses the saved
        options.
  - [x] **Argv commands (reasoned, and measured here).** An argv runs as `exec 'a' …` in the
        command's subshell, and `exec` runs a file, never a builtin, so no argv command runs in the
        program's own shell. Measured on this host's bash 3.2 (`bin/sandbox.sh`,
        `LocalShellExecutor`, a profile `shopt -s expand_aliases`): `['shopt', '-p',
        'expand_aliases']` exits 127, "exec: shopt: not found"; `['/usr/bin/command', '-v',
        'shopt']` runs macOS's `/bin/sh` wrapper, a fresh shell; the script `shopt -p
        expand_aliases; :` and `['/bin/bash', '--norc', '-c', 'shopt -p expand_aliases; :']` each
        print `shopt -u expand_aliases` (bash 3.2 hands nothing on), while the program's own shell
        has it off after the round trip (`shopt -s expand_aliases; POSIXLY_CORRECT=y; set +o posix`
        leaves `-u`). Not even `shopt`'s own listing reaches the program's shell through an argv: no
        code, recorded in the comment and in AGENTS beside B2.
  - [x] **The checkers.** `term-profile-and-hygiene-rows.py` no longer reads the saved list, the
        subshell's restore line or `shopt` among the builtins; it reads that the rendered program
        names no `shopt` and no `BASHOPTS` before its command. Seen red once: `shopt -u nullglob;`
        planted in the prologue, "the program names `shopt` before its command" for the argv and the
        script; restored with `cp`, `cmp` clean. `documented-bound-and-limits.py`'s N3 promise is
        the measured fact (AGENTS, `launch.py`), and `STALE_N3` refuses the restore's names in
        AGENTS, `launch.py`, the launch checker and the stop module.
  - **Gate, green** (macOS, bash 3.2, legacy era, host load 1.5–3.2, every step once, each logged
    outside the repo): setup; the six files, 1,633 passed, none skipped, 201 s (11 fewer than
    remediation 3's 1,644: the launch checker's three planted cases and the eight retired cases'
    anchor rows); `CI=true` hygiene, 74 passed, 2 s; the R5 gate, "17 timeout tests and 290 names
    unchanged since c8843b2, 32 rows, every one passed", 28 s; `develop-fails.py local`, R6 green,
    102 s; `term-profile-and-hygiene-rows.py`, 63 rows in every mode and login shell (the
    shell-option rows not defined on bash 3.2, as it says), 132 s; `documented-bound-and-limits.py`,
    5 limits shown by 35 rows, 36 promises, nothing stale, 109 s. P2's gate is not rerun: nothing
    it reads changed.
  - **Suite per era:** see P3's entry below (the whole suite ran once per era after P3's gate).

## Phase P2 — ssh: the KILL request, the test server acting on signal as sshd does, and the ssh rows
**Satisfies:** R1, R4, R5, R6, R7 · **Depends on:** P1
**Goal:** over `ssh` a timed-out command's processes are all gone within `2 × GRACE`, including when
a remote login shell's own rc file made them ignore TERM before the bootstrap (GOAL Q6); the
in-process SSH server delivers a `signal` request as OpenSSH 8.0p1 does (research 04); R1 pinned
host-free.

- [x] `ssh._collect`: `_signal(chan, 'KILL')` right after `_stopped`, before returning
      (`ssh.py:253-255`), unconditionally (sshd refuses it once the launch has exited, so a condition
      would be an equivalent mutant). `_collect`'s and `_signal`'s docstrings, AGENTS §3's timeout
      text and the `ssh.py` footgun say the sequence (TERM, the `GRACE` read, KILL, close) and why
      the KILL (sshd acts on it only while the launch lives: a TERM ignored from the launch's entry).
      AGENTS §3's limits and the README's timeout sentence stop naming a remote rc file's TERM
      ignore as a limit, and §3's "Pinned in …" names the `ssh` rows (P1 amendment 3).
- [x] `tests/test_ssh_exec.py`: `test_a_timeout_drains_what_follows_the_term`'s signal assertion
      becomes `['TERM', 'KILL']`, its text otherwise untouched (R5 as amended, Q6; the R5 gate allows
      exactly that change); add `test_a_timeout_asks_for_kill_after_its_grace` (the same fake
      channel, held open: the names are `['TERM', 'KILL']` and the KILL comes at least `GRACE − 0.05`
      after the TERM).
- [x] `tests/ssh_server.py`: a per-transport `MSG_CHANNEL_REQUEST` handler (save `m.packet.tell()`,
      read the name; `signal` → `owner.deliver(channel, name)`; anything else rewound and passed to
      `Channel._handle_request`); `deliver` maps the channel to its exec's process (set where `execute`
      launches it, in `LoopbackSSH` and in `ThrottledSSH`), `killpg`s it for HUP INT KILL QUIT TERM
      USR1 USR2 while it runs, ignores anything else, and records the name in `signals`. Rewrite the
      module docstring's "the server does not kill the process" (and any AGENTS § Testing text that
      repeats it) to say what it does, citing `session_signal_req`.
- [x] `tests/test_timeout_stop.py`: `ssh-bash` joins `MODES` (shapes `tree`, `ignores-holding`), both
      survival rows, grace, `[ssh-bash-profile]`, `[ssh-bash-bashrc]` and `[ssh-zsh-zshenv]` (a remote
      login shell's own rc file ignoring every catchable terminating signal); `ssh-zsh`, `ssh-sh`,
      `ssh-tcsh` behind `CLUSTER_MCP_TEST_EVERY_KIND=1`. The stop rows assert no signal list (they also
      run against develop); the unit rows above pin it.
- [x] Confirm the four existing ssh timeout rows (`test_ssh_exec.py:164`) still pass unchanged (the
      R5 gate runs them).
- **Verify:** `uv run pytest -q tests/test_timeout_stop.py tests/test_ssh_exec.py && uv run python -I spec/timeout-process-cleanup/verify/r5-timeout-tests-kept.py && uv run python -I spec/timeout-process-cleanup/verify/develop-fails.py ssh`.
- **Touches:** `packages/cluster-mcp/src/cluster_mcp/core/executor/ssh.py`, `tests/ssh_server.py`,
  `tests/test_ssh_exec.py`, `tests/test_timeout_stop.py`, `AGENTS.md` (§3, the `ssh.py` footgun;
  § Testing only if it describes the server's handling of a closed channel or of signals);
  `README.md`, `issues/timeout-stop-limits.md` and `ROADMAP.md` (amendment 1).
- **Amendments at build (2026-11-02):**
  1. The KILL request also stops, over `ssh`, a login initialisation that ignores TERM and hangs
     before the program starts (its launch still lives after the `GRACE` read, so sshd acts on the
     request), which P1's documents named a limit over `ssh`. So that the documents stay true of
     the code: AGENTS §3 and the README name that limit under a non-root `delegate` server only;
     `issues/timeout-stop-limits.md` and its `ROADMAP.md` entry get a dated, append-only note
     (code-build Step 2.3); and a row pins it, `test_a_hanging_login_is_stopped_over_ssh` (a
     `.bash_profile` that ignores every catchable terminating signal, writes its pid and `exec`s a
     sleep: gone within the bound, the result an empty timeout). Planting the KILL request's
     removal turns it red. It runs in the suite (≈ 3 s per era).
  2. An `ssh` row's executor runs `true` before the row's clock starts (`Hosts.executor`): the
     deadline is `_collect`'s, which starts after the connection and the exec request, so a
     connection made inside `run` would count against the stop bound and, for the rows that
     return at once, against `AT_ONCE` (`GRACE / 2`). Startup files are written after that
     warm-up, so it runs under none of them.
  3. The server's channel mapping is set by `_launch(wire, channel)`, which both `execute`
     methods call (`DroppingSSH`'s unsent runs pass none, so a request on them is ignored); a
     request with `want_reply` is answered success or failure, as sshd answers it (the client
     asks for none).
  4. With `CLUSTER_MCP_TEST_EVERY_KIND=1`, `ssh-zsh`, `ssh-sh` and `ssh-tcsh` run the survival and
     grace rows as well as the two stop shapes (every setting in `MODES` runs them): 15 rows, where
     the plan estimated 12; P4 measures them.
  5. `tests/test_ssh_exec.py`'s module docstring, and AGENTS § Testing's text on the server, the
     stop module and the channel loop's unit rows, say what the server and the rows now do.

- **Remediation, review cycle 1 (2026-11-02; F2; bundled with P1, above).** Reopened with
  `set_phase.py`; the gate is the frozen one, then `remediation/F2-signal-on-open-channel.py`. GOAL
  Q6 and R5 as amended on 2026-11-02.
  - [x] **F2, the fix.** `_signal` writes the request holding the channel's lock and only while the
        channel is not closed: Paramiko marks a channel closed under that lock before it sends its own
        close (`_close_internal`, from `close()` and from `_handle_close` alike), so a request either
        goes first or not at all. The wait for a key exchange is made outside the lock (a
        `clear_to_send` loop bounded by Paramiko's `clear_to_send_timeout`, the send under
        `clear_to_send_lock`), as Paramiko's own `_send` does, since its transport thread takes the lock
        to deliver what arrives. `_collect` asks for KILL only when the channel has not ended (`_ended`:
        closed, or the end of output and the exit status both in, when the launch has exited); a launch
        that ignored TERM still gets it.
  - [x] **F2, the test server.** `tests/ssh_server.py` gives each server transport a `channels_seen`
        that never matches (`_Forgotten`), so a message for a channel it has freed drops the connection,
        as sshd's "unknown channel" does, where Paramiko ignores it.
  - [x] **F2, pins.** `tests/test_ssh_exec.py`: `test_a_timeout_drains_what_follows_the_term` back to
        `c8843b2`'s text (`['TERM']`; the R5 gate passes it unchanged); `test_a_timeout_asks_for_kill_after_its_grace`
        (channel open after the grace: KILL); `test_no_signal_is_asked_for_on_a_closed_channel` (both
        sides closed, the server's copy freed: `_signal` sends nothing and the next call runs on the same
        connection); `test_a_signal_request_goes_while_the_channel_is_held_open` (the request written
        with the lock held, the channel open). `tests/test_timeout_stop.py`:
        `test_a_timed_out_call_leaves_the_connection_usable` (`ssh-bash`: a `tree` timeout, then `echo
        again` on the same executor, no new connection). The KILL on an open channel stays pinned by
        `[ssh-bash-bashrc]` and `test_a_hanging_login_is_stopped_over_ssh`.
  - [x] **F2, red first on `386efa3`** with this tree's server: the usable row (the second call
        raised `ConnectionResetError`; the server logged "Channel request for unknown channel 1"), the
        closed-channel row (connection lost), the held-open row (`[(False, False)]`: written without the
        lock) and the drains row (`[('TERM', 0.30), ('KILL', 0.61)]`) fail.
  - **Gate, green**, in the same run as P1's: the two files, 182 passed and 37 skipped (the limit rows)
    in 206 s; the R5 gate, P1's run standing in (same command, same tree); `develop-fails.py ssh`,
    35 s; the F2 checker, 29 `signal` requests over 178 rows (7 KILL), every one on an open channel
    and written holding its lock, no connection dropped for a freed channel, 192 s.
  - **Gate, green, rerun** with P1's (its inputs changed: the stop module): the two files, 182 passed
    and none skipped, in 210 s; the R5 gate, P1's rerun standing in; `develop-fails.py ssh`, 35 s; the
    F2 checker, 29 requests over 178 rows (7 KILL), every one on an open channel with its lock held, no
    connection dropped, 194 s.

- **Remediation, review cycle 2 (2026-11-04; F5).** Reopened with `set_phase.py`; its gate unchanged
  (the frozen steps and cycle 1's `F2-signal-on-open-channel.py`, which still holds: the KILL
  request and its guard did not change).
  - [x] **F5, the class (found by reading).** Every decision of `_signal`'s loop: the wait for a key
        exchange, the check that it ended, holding the transport's `clear_to_send_lock`, the bound
        (Paramiko's `clear_to_send_timeout`), the transport's liveness, and the wait made without the
        channel's lock. None was pinned: the suite never runs a key exchange.
  - [x] **F5, pins** (`tests/test_ssh_exec.py`, `unit`, a fake transport whose `clear_to_send` is
        clear until the test ends the exchange, and whose `_send_user_message` waits as Paramiko's
        does): `test_a_signal_request_waits_out_a_key_exchange` (nothing sent during the exchange,
        sent once after it, no wait made holding the channel's lock);
        `test_a_signal_request_gives_up_on_a_key_exchange[exchange-never-ends|transport-gone]` (the
        caller held no longer than the bound, or not at all, and nothing sent). No code change.
  - [x] **F5, red first:** the reviewer's mutant (the wait and its check dropped, the send under the
        channel's lock only) is `tpc-ssh-signal-no-key-exchange-wait`, killed by the first pin ("sent
        during the key exchange"); its five neighbours are in P3's sweep.
  - **Gate, green**, in the same run as P1's: the two files, 201 passed, none skipped, 241 s; the R5
    gate, P1's run standing in; `develop-fails.py ssh`, 43 s; `F2-signal-on-open-channel.py`, 36
    requests over 192 rows (12 KILL), every one on an open channel with its lock held, no connection
    dropped, 221 s.

- **Remediation, review cycle 3 (2026-11-04; B3's `ssh` side, B4, N1; bundled with P1, above).**
  Reopened with `set_phase.py`; its gate retuned with `--verify-file` to drop
  `tests/test_timeout_stop.py` from its pytest step, which P1's gate runs whole (so each distinct
  step runs once): `tests/test_ssh_exec.py`, the R5 gate, `develop-fails.py ssh`, and cycle 1's
  `F2-signal-on-open-channel.py`, which still holds (the KILL request and its guard did not change).
  - [x] **B3 over `ssh`:** argued in P1's entry; pinned by the `ssh-bash` window rows.
  - [x] **B4, the class.** `_signal`'s check that no key exchange runs and its send: one step only
        under the transport's `clear_to_send_lock`, which Paramiko's transport thread takes to clear
        `clear_to_send` as an exchange starts. **Pin:**
        `test_a_signal_request_never_goes_as_a_key_exchange_starts` (`unit`): a fake `clear_to_send`
        whose first check hands a stand-in transport thread the exchange's start, under that lock, and
        gives it 0.2 s before answering; the request must go before the exchange started. **Red
        first:** the reviewer's mutant (the lock dropped, the check kept), planted by hand on this
        tree: "the signal request was sent as the key exchange started: [False]"; restored with `cp`,
        `cmp` clean. It is `tpc-ssh-signal-exchange-unlocked` in the sweep.
  - [x] **N1, the class.** The program over `ssh` is given no deadline (the remote clock is not the
        server's; the call's timeout runs from the command's start, after the connection). **Pin:**
        `test_a_slow_connect_leaves_an_ssh_command_its_whole_timeout`: `_ensure_connected` delayed
        1.5 s, `run('echo ran', timeout=1)` must return `ran`, 0. A comment at `_run`'s `program(…)`
        says why. The mutant (`timeout=timeout` passed there) is `tpc-ssh-deadline-given`.
  - **Attempt recorded on P3** (the run's own unfinished work): the first gate run stopped at P3's
    first sweep part, a `TypeError` in the new sweep's skip list (a list joined to a set); fixed,
    its bookkeeping dry-run per part, the five cases and 22 equivalents not yet run in a dev run
    executed alone (all held), then every step of P1's, P2's and P3's gates ran again from the start.
  - **Gate, green** (macOS, bash 3.2, legacy era unless named, host load 2–4, every step once on the
    final tree, each logged outside the repo): setup; P1's six files, 1,644 passed, none skipped,
    203 s; `CI=true` hygiene, 74 passed, 3 s; the R5 gate, "17 timeout tests and 290 names unchanged
    since c8843b2, 32 rows, every one passed", 27 s (it stands in for P2's identical step);
    `develop-fails.py local`, R6 green, 102 s; `term-profile-and-hygiene-rows.py`, 63 rows in every
    mode and login shell (the shell-option rows not defined on bash 3.2, as it says), 130 s;
    `documented-bound-and-limits.py`, 5 limits shown by 35 rows, 34 promises, nothing stale, 108 s;
    P2's `tests/test_ssh_exec.py`, 145 passed, 120 s (P1's run of the stop module stands in for the
    file P2's gate dropped); `develop-fails.py ssh`, R6 green, 45 s; `F2-signal-on-open-channel.py`,
    39 requests over 196 rows (13 KILL), every one on an open channel with its lock held, no
    connection dropped, 224 s. Before the gates, the whole suite once per era: legacy 4,830 passed and
    14 skipped (the bash 4.1 rows CI runs), 551 s; modern the same, 536 s.
  - **Suite growth per era**, from the added rows alone (JUnit times against the node ids `c16f19b`
    collects): 49 rows new (the window rows 8, the variable rows 4, the slow-connect row, the B4 unit
    row, the checker's planted cases and the mutation-anchor rows), 22.0 s legacy and 21.9 s modern,
    about 4 % of the ≈ 540 s suite here; 15 rows retired (the four fork-window rows, `kill-alias`, and
    retired cases' anchor rows). CI adds the four shell-option rows (bash 5), under a second. CI's era
    jobs ran 8.5–8.9 min on `c16f19b` against their 20-minute timeout.

## Phase P3 — The mutation sweep
**Satisfies:** R4, R5, R6 · **Depends on:** P2
**Goal:** every decision of PLAN §2 is planted to each alternative it could take and killed by the
rows meant to kill it.

- [x] `tests/mutants.py`: one `Case` per mutant below, each naming its targets and the `why` fragment
      the target's failure carries (`still running`, `was stopped`, the grace row's lost-output
      message, `returned`, the text and unit tests' messages). Self-check each. Ids, edits, and the
      rows that must kill them:
      - the watchdog: `tpc-watchdog-dropped` (the line removed: stop rows), `tpc-arm-dropped` (no
        arming line: survival + stop rows), `tpc-release-dropped` (survival), `tpc-release-before-command`
        (stop rows), `tpc-release-after-reraise` (the signal-death survival rows), `tpc-trigger-inverted`
        (second `||` → `&&`: survival), `tpc-unarmed-stops` (first `|| exit` → the stop:
        `test_a_watchdog_that_cannot_start_stops_nothing`);
      - its signals: `tpc-term-dropped`, `tpc-term-int`, `tpc-term-hup` (grace row `[delegate]`),
        `tpc-kill-term`, `tpc-kill-hup`, `tpc-kill-stop` (stop rows with ignoring shapes),
        `tpc-group-self` (`0` → `$$`: stop rows);
      - its delay: `tpc-delay-zero` (grace rows), `tpc-delay-doubled` and `tpc-delay-fixed`
        (`test_the_watchdog_waits_grace`), `tpc-plain-sleep` (`/bin/sleep` → `sleep`: grace rows, whose
        profile defines `sleep`);
      - its isolation: `tpc-fd-left-open` (`46>&-` dropped: stop `[local-ignores-none]`),
        `tpc-holds-output` (its `/dev/null` dropped: the return-time check on `[local-tree]`,
        `[ssh-bash-tree]`), `tpc-ignore-at-fork-dropped` (stop `[local-ignores-none]`),
        `tpc-restore-dropped` (`trap - TERM` dropped: stop `[delegate-tree]`), `tpc-clobber` (`>|` →
        `>`: `[delegate-profile]`, whose profile sets `-C`, and `test_writes`' fixed-script row; macOS
        bash 3.2 only, where this phase runs), `tpc-monitor-kept` (`m` dropped from the prologue:
        `[delegate-profile]`, whose profile sets `-m`);
      - the KILL request (Q6): `tpc-ssh-kill-dropped` (`[ssh-bash-bashrc]`, the drains row),
        `tpc-ssh-kill-before-term` and `tpc-ssh-kill-before-grace` (`test_a_timeout_asks_for_kill_after_its_grace`,
        grace `[ssh-bash]`), and the name: `tpc-ssh-kill-term`, `-hup`, `-int`, `-quit`, `-usr1`,
        `-usr2` (every other name sshd accepts) and `-stop` (one it refuses), each killed by the
        drains and order rows and by `[ssh-bash-bashrc]`, whose rc file ignores every catchable one.
      A mutant no row can kill is either given a row or argued equivalent in the commit body.
- **Verify:** the frontmatter's (planned: 34 cases, ≈ 5 min; as built, amendment 2: 101 cases and 7
  equivalents per era, measured on macOS before the phase commit: legacy 266 s + 399 s, modern
  265 s + 415 s, 22.4 min in all).
- **Touches:** `tests/mutants.py`, and a row file only if a mutant needs a row.
- **Amendments at build (2026-11-02):**
  1. **The sweep covers every alternative, not the plan's 34.** A coverage pass over the watchdog,
     its arming and release, the prologue's `m` and the KILL request found decisions the 34 ids do
     not reach: the watchdog and the release at every other place in the program's join; the
     watchdog line's four statements in every order one move from its own; TERM → KILL, STOP; KILL
     dropped; the group target for one signal only, and `-$$`; the delay halved; `command sleep`;
     the descriptor renumbered at each place it is named, everywhere to a free one (45) and to one the
     program re-points (59), and not kept (`exec` dropped); `<(…)` for `>(…)`; stdout or stderr kept
     alone, and the quieting redirection without `exec`; the first read dropped or its `exit`
     inverted, the second read dropped; the arming and release lines unterminated and written with
     `echo`; the ignore and the restore naming INT or HUP; the subshell's redirections reordered.
     Each is a `tpc-` case (101 on macOS, 100 elsewhere). A case carries one `why`, so a mutant the
     plan said two families kill is planted once per family: `tpc-arm-dropped` (survival) and
     `-stop`; `tpc-ssh-kill-dropped` and each `tpc-ssh-kill-<name>` ([ssh-bash-bashrc] and the
     hanging-login row) and their `-unit` twins (the drains and order rows, `why` the list of names
     asked for); `tpc-ssh-kill-before-term` (unit rows) and `-output` (grace [ssh-bash]); likewise
     `tpc-ssh-kill-before-grace`. `tpc-release-before-command` is the release placed right before
     the subshell (after the sentinel); the release right after the arming is
     `tpc-release-after-watchdog`.
  2. **The gate is `verify/sweep.py`, per era, in halves.** Its `SWEEP` table is the coverage:
     each decision, each alternative and the case that plants it, or an equivalent planted in the
     gate with the rows that kill its neighbours, which must all pass (arming before the restore;
     the descriptor renumbered to 45; `46>&-` first; `>>` for `>|`; `read` without `-r`; a fixed
     `1` while GRACE is 1; the KILL request guarded by `exit_status_ready()`), or a reason it is not
     planted (`-1`/`$PPID` as the target would signal the runner; `/usr/bin/sleep` differs by
     platform; the remaining signal names are the planted names' classes). It checks the table
     against `tests/mutants.py` both ways. The runner's children inherit `CLUSTER_MCP_TEST_ERA`, so
     each era is its own run, and each era runs in two halves to stay under a 10-minute call
     (capability-probe ran its sweep the same way).
  3. **Re-anchored targets.** Every target row runs in the suite (none only under `EVERY_KIND`):
     the `ssh-bash` rows, never `ssh-zsh`. `tpc-clobber` is killed by `[delegate-profile]` alone:
     `test_writes`' fixed-script rows all pass under `>` on this tree, so they are not targets. It
     is defined on macOS only (`sys.platform == 'darwin'`): Linux bash allows `>` onto the pipe, so it
     would survive `mutants.yml` on ubuntu. The TERM's alternatives are killed by grace `[delegate]`,
     where the watchdog's TERM is the command's first; two of the statement orders by
     `[delegate-tree]` alone (in `local` the server's KILL still ends the group, late).
     `tpc-command-sleep` passes the `[local]` grace row (measured; the cause is not established) and
     is killed by the other three settings'.
  4. **A row change.** `test_a_stopping_command_gets_its_grace`'s profile also puts a `sleep` that
     returns at once first on `PATH`, so a watchdog that resolves `sleep` through `PATH` loses the
     grace (`tpc-command-sleep`). A hash entry did not do (every row passed under the mutant);
     the likely cause is the suite's `BASH_ENV`, which reassigns `PATH` after the profile, and an
     assignment to `PATH` empties bash's hash table. The row is not in the R5 gate's files and not
     in `develop-fails.py`'s sets.
  5. **Suite growth:** 101 `test_mutation_anchor_applies[tpc-…]` rows, ≈ 2 s per era; the grace
     rows' extra file adds nothing measurable. The sweep itself runs only on demand: it adds ≈ 11
     min per era to `mutants.yml`, already past its 30-minute job (`issues/mutants-workflow-timeout.md`).

- **Remediation, review cycle 1 (2026-11-02; the F1 and F2 sweep, F5).** Reopened with
  `set_phase.py`.
  - [x] **The frozen gate is superseded.** `verify/sweep.py`'s table plants the watchdog's two `read`s
        and the unconditional KILL request, both retired by F1 and F2; run on this tree it fails at
        import (`AttributeError: module 'mutants' has no attribute 'FIRST_READ'`). No wrapper can restore
        what it plants, so `remediation/F1-F2-stop-sweep.py` supersedes it, its runner kept verbatim and
        its table this cycle's; the frozen file stays as the record. The gate runs the new sweep per era
        in halves, then `remediation/F5-clarification-ids.py`.
  - [x] **Cases** (`tests/mutants.py`, 121 `tpc-` cases on macOS): new, the wait (`tpc-wait-no-stop-mark`,
        `-first-line`, `-read` and `-bounded`, killed by the `TMOUT` rows, `-plain-cat`, `-command-cat`),
        the trigger (`tpc-trigger-on-release`, `tpc-stop-or`, `tpc-stop-unconditional`; `tpc-unarmed-stops`
        and `tpc-trigger-inverted` re-anchored), the unset (`tpc-unset-dropped` and `-dropped-grace`,
        `-cat-only`, `-sleep-only`, `-not-functions`, `-after-fork`), the KILL guard
        (`tpc-ssh-kill-unguarded`, `-guard-inverted` and `-behaviour`, `-guard-status`) and `_signal`
        (`tpc-ssh-signal-unchecked`, `-active-checked`, `-unlocked`, `-checked-then-sent`); retired with
        the `read`s, `tpc-first-read-dropped`, `tpc-first-exit-inverted`, `tpc-second-read-dropped`;
        re-targeted, `tpc-arm-unterminated` (stop rows: any byte arms now), `tpc-release-unterminated`
        (the launch checker; its behaviour an equivalent) and the KILL's `-unit` twins (the order row
        alone: the drains row's channel has ended, so it asks for TERM alone whatever the KILL is). Ten
        equivalents are planted with their neighbours' rows. All 47 new or changed cases were seen
        killed, and every equivalent surviving, in development runs before the gate.
  - [x] **F5.** `tests/test_hygiene.py`'s `SPEC_ID` takes `Q#` (`[RPQ]`), with a planted
        `clarification` row and wider look-alikes (`Q100 QUIT SIGQUIT IQ3 Q3PO`); `tests/mutants.py`'s
        comment names no clarification. The F5 checker flags the reviewed commit's comment and planted
        `Q3`s, and nothing today.
  - **Gate red, attempt 1.** Legacy half 1: 61 cases killed, 319 s. Legacy half 2: 59 of 60 killed,
    376 s: `tpc-command-sleep` (`command sleep {grace}` in the watchdog, a `sleep` that returns at once
    first on the grace rows' PATH) survived `test_a_stopping_command_gets_its_grace[delegate-root]`
    ("passed, so the mutant survived it"); its other two targets failed. The case and its targets are
    P3's, unchanged here. Diagnosis on the identical tree, not a gate run: the case alone was killed
    four times in four. Its kill is a race: under the mutant the watchdog's KILL follows its TERM by a
    fork of `/bin/sh` for the PATH `sleep`, which a loaded host can stretch past the 0.3 s the grace
    row's handler waits before it prints (P3's amendment 3 already records it surviving `[local]`,
    cause not established). It is not one of the seeded loopback flakes, so the build stopped here;
    the modern halves, the F5 checker and P4's gate did not run.
  - **The fix (the foreman's ruling (b), 2026-11-02).** A kill that rests on fork timing is a weak
    pin, so the grace row's handler now prints 0.6 s into the stop, not 0.3 s. Measured before
    choosing (a throwaway probe, not committed: a handler stamping the time every 0.02 s from its
    first TERM until the KILL, in the four suite settings, the real watchdog and the mutant): quiet,
    the real KILL came 0.96–1.00 s after the handler's first TERM and the mutant's 0.00–0.12 s; under
    16 CPU-bound processes on 10 cores (load 19), 0.96–1.01 s and 0.00–0.08 s. The real KILL cannot
    come sooner than `GRACE` after the TERM (the absolute `sleep` bounds it from below), so 0.6 s
    leaves the row about 0.35 s for its own `sleep` and `echo` under load, and the mutant's KILL about
    0.5 s of margin. With it, `tpc-command-sleep` was killed by the `[local]` grace row too (twice in
    two; P3's amendment 3 recorded it surviving there), so its targets are all four grace rows.
    `AGENTS.md` § Testing says 0.6 s. Every step whose inputs the change touches reruns: P1's and
    P2's gates (the stop module), the sweep's four halves, the F5 checker and P4's gate.
  - **A rerun interrupted.** The third full run (P1's attempt 3 fixed) was cut off by the build's
    session limit after the legacy halves passed, and the host restarted meanwhile, which cleared
    its logs; it counts for nothing. The run below is every step from the start.
  - **Gate, green** (attempt 2, the same run as P1's rerun): legacy half 1, 61 cases killed, 315 s;
    legacy half 2, 60 killed and 10 of 10 equivalents shown, 469 s; modern half 1, 61 killed, 315 s;
    modern half 2, 60 killed and 10 of 10 equivalents, 466 s; the F5 checker, "Q# flagged where
    planted and at 386efa3, nowhere in 78 files today, never on a look-alike", 2 s. `tpc-clobber` ran
    (macOS).

- **Remediation, review cycle 2 (2026-11-04; F2, F3, F1/F4 and F5 swept again).** Reopened with
  `set_phase.py`; its gate retuned with `--verify-file` to `remediation/watchdog-sweep.py` (both eras,
  each in two halves) and cycle 1's `F5-clarification-ids.py`. The new sweep supersedes
  `F1-F2-stop-sweep.py`, kept as the record: its table planted the watchdog's TERM, its ignore around
  the fork and its unset, all retired here. `tests/mutants.py`'s `tpc-` section is rewritten for the
  new texts (in P1's commit, since `tests/test_mutations.py`, in P1's gate, applies its anchors).
  - [x] **The table** (decision, every alternative, what kills it): the watchdog's place (11), its
        statements' order (4, each one move away), TERM's default before the fork (4: dropped, INT,
        HUP, cycle 1's ignore in the program), the watchdog's own ignore (5), the open, descriptor and
        streams (as cycle 1), the wait and trigger (as cycle 1), arming and release (as cycle 1, with
        the new place after the check), the one signal (dropped; TERM, HUP or STOP for KILL; a TERM
        first, under a non-root server and as a second TERM), its group (`$$`, `-$$`), its delay (0
        twice, doubled, halved, fixed, plain and `command` `sleep`), the prologue's posix-mode unset,
        re-enable, `enable` function, listed names and path functions (12), the deadline check's
        place (11), its backends (2), clock (2), comparison (3), refusal (2) and value (4), and over
        `ssh` cycle 1's KILL-request and `_signal` cases with six for the key-exchange wait (F5).
        Equivalents planted and shown (their neighbours' rows pass): the watchdog's ignore after its
        redirection; `>>`; descriptor 45; `46>&-` first; the release's other byte; `;` for `&&`; a
        TERM after the KILL; the fixed delay; `enable` without `|| :`; the list without `unalias` and
        the second `\unalias -a` (bash 3.2 leaves posix mode with alias expansion off); the clock's
        seconds-only fallback and its guard; `<=`; the refusal without its wait, without its KILL, and
        to the group; cycle 1's two KILL-guard equivalents. Not planted, with the reason in the table:
        a handler around the fork; other signal names; `-1`/`$PPID`; `/usr/bin/sleep`; parked
        descriptors; the rest of cycle 1's builtin list; the limit's own shadows; the check over
        `ssh`; a deadline taken after the server's; a TERM just before the KILL; the
        `clear_to_send_lock` race.
  - **Attempt 2, recorded with `set_phase.py`** (the run's own unfinished work, fixed in the run):
    the first gate run's sweep, legacy half 1, killed 77 of 78 cases; `tpc-term-after-grace` (`{
    sleep G; kill -s TERM 0; kill -s KILL 0; }`) survived the non-root row, since the KILL lands before
    a handler runs. It is a race no row can time, not a decision a row can tell: moved to the table's
    not-planted list with that reason, its case removed. Before the rerun, an exploratory run of the
    second half (not a gate) found `tpc-refusal-lives-on` surviving its `local` and `delegate-root`
    targets: there the server's KILL ends the waiting program before it would start the command, so
    only the non-root row can show it, and its target is now that row alone (killed, "started after
    its deadline"); the 19 equivalents, run alone, all held. Every gate step then ran again from the
    start.
  - **Gate, green**, in the same run: `watchdog-sweep.py` legacy 77 + 77 cases killed and 19 of 19
    equivalents shown (581 s, 546 s), modern the same (581 s, 540 s), `tpc-clobber` included (macOS);
    `F5-clarification-ids.py`, 2 s.

- **Remediation, review cycle 3 (2026-11-04; the decisions this remediation changes swept again).**
  Reopened with `set_phase.py`; its gate retuned with `--verify-file` to
  `remediation/watchdog-and-hygiene-sweep.py` (both eras, each in four parts, each under the
  10-minute command cap) and cycle 1's `F5-clarification-ids.py`. The new sweep supersedes cycle 2's
  `watchdog-sweep.py`, kept as the record (its table plants the watchdog line B3 retired, names the
  `kill-alias` row and leaves the key-exchange lock unplanted).
  - [x] **The table, what changed:** the watchdog's four statements in every order one move away
        (9: 8 killed, `ignore, fork, arm, restore` an equivalent); the TERM ignored at the fork
        (dropped, INT, HUP, cycle 2's line, a handler around the fork; the watchdog's own ignore
        besides an equivalent); TERM's default after the fork (dropped, INT, HUP; after the check not
        planted); the names unset (the clock reading, the saved options, the function export's name,
        `set +a` instead); the shell options set back (dropped, not saved, saved in posix mode, either
        loop dropped, as text and, on bash 4.4 or later, as what a command sees; in the program
        instead, text, with its behaviour an equivalent; errors not silenced, an equivalent); `shopt`
        among the builtins; the deadline's check over `ssh` (was not planted) and dropped behind the
        fork window; `_signal`'s check and send without `clear_to_send_lock` (was not planted);
        `run`'s return (the `ssh` read tripled); the second `\unalias -a` (text, and its behaviour an
        equivalent, now against the rows that kill its neighbours). Cycle 2's `tpc-child-ignore-*`,
        `tpc-ignore-in-program-at-fork` and the old order cases are retired with the design.
  - **Attempt 3, recorded with `set_phase.py`** (the run's own unfinished work, fixed in the run):
    see P2's entry above.
  - **Gate, green**, in the same run: `watchdog-and-hygiene-sweep.py` legacy 44 + 44 + 44 + 42 cases
    killed and 22 of 22 equivalents shown (256, 359, 220, 372 s), modern the same (252, 359, 220,
    371 s); `tpc-clobber` included (macOS); the five `-behaviour` cases of the shell options skipped,
    as the gate says (their rows exist only on bash 4.4 or later; not run anywhere yet);
    `F5-clarification-ids.py`, 2 s.

- **Remediation, review cycle 3 verification (2026-11-04; N3 not reproduced; the decisions it
  removes leave the sweep).** Reopened with `set_phase.py`; its gate unchanged.
  `watchdog-and-hygiene-sweep.py` is edited in place and says "review cycle 3 verification, N3":
  the options decisions leave the table (`tpc-option-names-kept`, `tpc-builtins-without-shopt`, the
  six `tpc-options-*`, the five `-behaviour` cases and the two option equivalents), the `unalias`
  equivalent's reason no longer leans on the restore, and a `NOT_PLANTED` entry records that the
  program refreshes no `BASHOPTS` before its command (its row exists only on bash 4.4 or later; the
  launch checker's fixed copy of the program refuses any added text). 166 cases and 20 equivalents,
  from 174 and 22.
  - **Attempt 4, recorded with `set_phase.py` (red, not the run's own work: a STOP).** Legacy parts 1
    and 2 green (42 + 42 cases killed, 236 and 364 s); part 3 red: `tpc-command-sleep` (`command
    sleep {grace}` in the watchdog) survived `test_a_stopping_command_gets_its_grace[ssh-bash]`, the
    row passing; `local` and `delegate-root` killed it. Every earlier sweep killed it in all three
    settings, on the same watchdog text; this cycle's change touches neither the watchdog, the `ssh`
    wire nor the grace rows, so the kill over `ssh-bash` looks timing-dependent. Not re-run (not a
    seeded flake); parts 4 and the modern era, `F5-clarification-ids.py` and the whole suite per era
    not run. The circuit breaker had already warned at 3 attempts.
  - **The foreman's ruling on attempt 4: a flake.** `tests/mutants.py tpc-command-sleep`, run alone
    three times at host load 2.4, was killed 3 of 3 in `local`, `delegate-root` and `ssh-bash`
    ("within GRACE of its TERM, was lost"; `tpc-logs/n3-revert/foreman-command-sleep-{1,2,3}.log`
    beside the worktree). A load-sensitive kill, the race class of remediation 1's ruling on this
    case (the handler at 0.6 s); this change does not touch the watchdog. No further attempt
    recorded; the case and the row are unchanged. The gate carried on from where it stopped.
  - **Gate, green** (macOS, bash 3.2, host load 1.9–2.9, each step logged outside the repo): legacy
    parts 1–4, 42 + 42 + 41 (part 3: `tpc-command-sleep` survived under the sweep's load, the flake
    above) + 40 cases killed and 20 of 20 equivalents shown (236, 364, 215, 377 s); modern parts
    1–4, 42 + 42 + 42 + 40 killed, `tpc-command-sleep` among them, and 20 of 20 equivalents (233,
    363, 213, 376 s); `tpc-clobber` included (macOS); no re-run was needed; `F5-clarification-ids.py`,
    2 s. Then the whole suite once per era: legacy 4,819 passed and 14 skipped (the bash 4.1 rows CI
    runs), 538 s; modern the same, 521 s.
  - **Suite per era** (JUnit against remediation 3's whole-suite runs):
    11 rows fewer per era (the launch checker's three planted cases and eight retired cases' anchor
    rows), 0.1 s; nothing added. On CI's bash 5 the five `-behaviour` anchor rows go too; the four
    shell-option rows stay.

## Phase P4 — Every login shell, and the deferral ledger
**Satisfies:** R1, R6 · **Depends on:** P3
**Goal:** the stop module passes with every login shell in the modern era, develop fails it with
every shell, and nothing deferred is unrecorded.

- [x] Run the stop module with `CLUSTER_MCP_TEST_EVERY_KIND=1` (every login shell) in the modern era,
      and `develop-fails.py all` with the same flag.
- [x] **Deferral ledger** (last-phase item): walk P1–P4's bodies and the commit messages for "do not
      fix here", "known limitation", "left as a follow-up", "limit" and "deferred"; each must have an
      `issues/` seed and a `ROADMAP.md` entry. Expected: `issues/timeout-stop-limits.md` (filed with
      the plan): the startup-file hang, an SSH server that ignores `signal`, the double TERM, the
      forking window, `enable -n`. Q4's `setsid` and Q5's lost link are GOAL non-goals, not
      deferrals. An unrecorded deferral fails the phase.
- [x] Standing last-phase items: the previous cycle's last phase carried no project-level obligation
      beyond the ledger (no `## Times` quote in this repo).
- **Verify:** the frontmatter's (≈ 3.5 min: `develop-fails.py all` with every shell 104 s, the module
  with every shell 95 s, measured). `publish` runs the profile's full `verify` and reads CI, whose
  two era jobs are the Linux bash 5 evidence.
- **Touches:** nothing but a seed or entry the ledger finds missing (as built, amendment 1:
  `AGENTS.md`, `README.md`, `SECURITY.md`, `ROADMAP.md` and four `issues/` seeds).
- **Amendments at build (2026-11-02):**
  1. **The documents were not all true of the code; fixed here.** Measured with throwaway rows
     (the module's own fixtures, not committed): under a non-root `delegate` server a startup file
     that hangs need not ignore TERM for what it started to run on (`sudo` relays the TERM to the
     login shell alone; a `.bash_profile`'s foreground `/bin/sh -c 'sleep 30'` was still running
     2.5 s after the deadline, and gone in time in the three other settings); `enable -n trap`
     disarms the watchdog in all four settings (forked without TERM ignored, it dies of its own
     TERM; ignoring children ran on under `delegate` and `ssh-bash`, and in `local` and
     `delegate-root` where they hold no output), while `enable -n kill` and `enable -n read` did
     not on macOS (`/bin/kill`, `/usr/bin/read` stand in). AGENTS §3's limits and `SECURITY.md`'s
     edge now say the first; §3 says the second; the README's list of what is not stopped, read as
     complete, gains the two narrow edges (`enable -n trap`; the forking window under a non-root
     server). Dated, append-only notes (code-build Step 2.3) carry both to
     `issues/timeout-stop-limits.md` and its `ROADMAP.md` entry.
  2. **Ledger.** Every deferral of P1–P4 and the commit bodies lands in
     `issues/timeout-stop-limits.md` (five cases) or is a GOAL non-goal (Q4's `setsid`, Q5's lost
     link; §3's pre-existing "held until the timeout over `ssh`" limit is Q4's and
     `issues/startup-background-jobs.md`'s). Two entries were no longer true of the code and get a
     dated note: `ROADMAP.md`'s `local-command-outlives-server` entry ("only its call ever signals",
     now the watchdog too; its seed had the note since P1), and `issues/mutants-workflow-timeout.md`
     with its entry (P3 amendment 5 deferred the sweep's growth there: 101 cases, 1,032 in all,
     ≈ 11 min per era). PLAN §5's `sudo` with a PTY is an unmodelled risk, not a deferral.
  3. **Gate red, attempt 1.** `develop-fails.py all` with every shell was green (114 s: 15 rows fail
     on `c8843b2` with `still running`, the controls pass). The module with every shell, modern era,
     had one failure, `test_a_command_that_dies_of_a_signal_leaves_its_jobs_running[ssh-sh]` (81 s,
     42 passed), with paramiko's `Socket exception: Bad file descriptor` in the captured log; its
     assertion text was not kept. The host ran at load 6 with two unrelated processes spinning.
     Diagnosis on the identical tree, not a gate run: the row passed six times alone, and the
     module three times whole (83 s each). It is not one of the seeded loopback flakes, so the build
     stopped here; the sighting is a dated note on `issues/stalled-reconnect-test-timing.md` and
     its `ROADMAP.md` entry.
  4. **Gate re-run, green** (the foreman's ruling: one re-run on the identical tree, `a8a138b`; a
     second failure of any row of the module would be a finding, not a flake). Every run's full
     output was kept. `develop-fails.py all` with every shell: green, the same 15 rows failing on
     `c8843b2` with `still running` and the controls passing; the module with every shell, modern
     era: 43 passed in 83 s, no skips; 197 s in all. Then the profile's full `verify`, green:
     `uv lock --check`; the suite, 4,701 passed and 14 skipped per era (`bash 4.1 or later is not
     installed here`: the macOS host has bash 3.2 only; CI's ubuntu runners run them); the
     sandboxed `cluster-mcp --help`.
  5. **Suite time per era.** Measured back to back against `c8843b2` (a detached throwaway worktree,
     removed after) on a host that other sessions loaded heavily (load 5 at the base's legacy run,
     8–25 through the branch runs): legacy 468 s base, 605 s branch; modern 433 s base, 686 s
     branch. The load confounds the difference. The growth this cycle adds, measured alone:
     `tests/test_timeout_stop.py` as the suite runs it, 63 s per era (28 rows), plus 101 anchor
     rows (≈ 2 s) and a handful of unit and text rows; about 15% of the base. CI's two era jobs
     ran the same tests at `511c4c0` (P4 changes no test or code) in 7 min 13 s and 7 min 24 s,
     against `c8843b2`'s 8 min 36 s and 8 min 57 s, of the 20-minute timeout. The every-shell rows
     stay behind `CLUSTER_MCP_TEST_EVERY_KIND=1`.
- **Remediation, review cycle 1 (2026-11-02).** Reopened with `set_phase.py`; the gate is the frozen
  one, unchanged (the module with every login shell now runs the profile rows in every setting too).
  - [x] **Deferral ledger.** `issues/timeout-stop-limits.md` and its `ROADMAP.md` entry, corrected in
        place (unlanded), hold every limit F3 measured. Two pre-existing defects found while building
        the remediation, filed by the foreman's ruling as unshaped seeds with Part III `ROADMAP.md`
        entries: `issues/ssh-open-session-reset-raises.md` (a reset while a call opens its channel
        raises Paramiko's `ConnectionResetError` out of `SSHExecutor.run`, seen in P2's red-first run;
        it should report the command as not run, by analogy with `CONNECTION_LOST_EXIT_CODE`) and
        `issues/script-function-export-tmout.md` (the program's function-export loop is a `read`, so a
        sub-second `TMOUT` on bash 4 and later could drop exported functions; unmeasured, with the
        measurement a shaping step needs). No other deferral; every seed has its entry.
  - **Gate, green** (the same run): `develop-fails.py all` with every login shell, R6 green, 167 s; the
    module with every login shell, modern era, 67 passed and none skipped, 137 s.
  - **Suite growth per era**, measured alone: the rows this remediation adds (15 behaviour rows; the
    limit rows are no longer collected) take 27 s in each era, plus 20 anchor rows and one hygiene row
    (well under a second). CI ran `35b6773`'s suite at 7 min 42 s and 9 min 17 s per era (the foreman's
    push), before the hygiene fix, which adds no row to the suite: about 8 and 9.5 min of the 20-minute
    timeout.

---

- **Remediation, review cycle 2 (2026-11-04).** Reopened with `set_phase.py` to prove the changed
  program under every login shell; its gate unchanged.
  - [x] **Ledger.** Review cycle 2 closed three of `issues/timeout-stop-limits.md`'s cases (the
        double TERM, the forking window, `enable -n trap`) and one more of AGENTS §3's (the late start
        under a non-root server), and ruled one new (a startup file that shadows the launch's builtins
        past what the prologue undoes). The seed and its `ROADMAP.md` entry, unlanded, are rewritten
        in place in P1's commit (R7: with the code), as cycle 1 did; no other deferral arose.
        The `unalias` decisions that bash 3.2 cannot show are a sweep equivalent, not a deferral.
  - **Gate, green**, in the same run: `develop-fails.py all` with every shell, 224 s (the rows that
    fail on `c8843b2` fail with "still running", the controls pass); the module with every shell,
    modern era, 93 passed, none skipped, 194 s.

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[fix]` commit; stop and report.
