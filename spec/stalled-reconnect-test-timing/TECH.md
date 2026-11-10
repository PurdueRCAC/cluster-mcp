---
slug: stalled-reconnect-test-timing
title: Real-time tests fail on behaviour, not on a busy host
kind: test
appetite: small
status: in_review
branch: test/stalled-reconnect-test-timing
base: develop
current_phase: done
last_updated: '2026-11-10'
phases:
- id: P1
  name: Row 1 counts each reconnect worker as it starts
  status: done
  satisfies:
  - R1
  - R7
  - R9
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/timing-gate.py row 1
- id: P2
  name: Row 2 measures the call's waits on the row's clock
  status: done
  satisfies:
  - R2
  - R7
  - R9
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/timing-gate.py row 2
- id: P3
  name: Row 3 decides the raised endings on a probe clock
  status: done
  satisfies:
  - R3
  - R7
  - R9
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  verify: UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/timing-gate.py row 3
- id: P4
  name: Row 4 times the start with the collector paused (D1, or (c) as signed)
  status: done
  satisfies:
  - R4
  - R7
  - R9
  depends_on:
  - P3
  parallel: false
  hammerable: false
  hill: uphill
  verify: UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/timing-gate.py row 4
- id: P5
  name: The final sweep on the final tree, every row and the named cases, and R8's figures
  status: done
  satisfies:
  - R6
  - R8
  - R9
  depends_on:
  - P4
  parallel: false
  hammerable: false
  hill: uphill
  verify: UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/timing-gate.py sweep-check && UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/timing-gate.py values 1 2 3 4 && UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/timing-gate.py scope
- id: P6
  name: R5's load protocol, the profile's verify, and the deferral ledger
  status: done
  satisfies:
  - R5
  - R8
  depends_on:
  - P5
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 2
  verify: UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/load-protocol.py check && UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/timing-gate.py profile check && UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/timing-gate.py sweep-check && UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/timing-gate.py scope && UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/timing-gate.py ledger
review:
  last_reviewed_commit: ''
  verdict: none
  blocked_reason: ''
  cycle: 0
---

# TECH.md — Real-time tests fail on behaviour, not on a busy host

The **context engine and finite-state machine** for building this cycle. The YAML frontmatter above
is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/stalled-reconnect-test-timing/TECH.md`);
the per-phase checklists below are the work. `code-build` executes the next actionable phase, runs
its `verify:` command, updates state via `uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`,
and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md) (§ 2 per row, § 6 the fault list and controls).
- **Backing research:** [`research/01-where-the-time-goes.md`](research/01-where-the-time-goes.md).

## Frontmatter field reference

As the template: `status`, `appetite`, `branch`/`base`, phase `status`, `satisfies`, `depends_on`,
`parallel`, `hammerable`, `hill`, `attempts`, `verify` and `review.cycle` mean what
`$KB/skill/_templates/TECH.md` says. R5 (P6) and R6's sweep (P5) are met by records committed under
`verify/`, which the orchestrator grades, not the blind reviewer: `verify/load-runs.txt`,
`verify/sweep.txt`, `verify/profile-verify.txt`.

## Conventions (apply to every phase)

- Commit conventions, code style, and load-bearing invariants come from the repo's `AGENTS.md` — it
  is the constitution. Walk the sections of its § Invariants that this change touches; that is the
  curated footgun checklist.
- One phase per `code-build` invocation by default; one atomic commit containing **both** the code and
  the `TECH.md` state change. The branch commit subject is code-build's (`$KB/skill/code-build.md` →
  Step 6), not restated here; branch commits are squashed away at `code-publish` per the profile's
  `landing`. Trailers follow the profile's `branch commits`.
- The last phase carries the standing last-phase items: the deferral ledger (`code-plan` Step 6.8),
  and every item the previous cycle's last phase carried for a project-level obligation. The previous
  cycle (`suite-ci-time-budget`) carried the ledger; that is the one that applies.
- A PR body (when the profile's `landing` opens one) ends with an attribution naming the actual
  harness, model, and variant.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`). This
  cycle changes no CLI, help text, gate command or workflow: "CI mirrors the gate" holds by not
  touching either side, and `scope` checks it.
- Only `tests/test_ssh_exec.py`, `tests/test_probes.py`, `tests/test_probe_startup.py`, files under
  `spec/stalled-reconnect-test-timing/`, and (only for a deferral) `issues/*.md` and `ROADMAP.md` change.
  Nothing under `packages/`: a phase that finds a product defect stops and reports it for a `fix`
  seed. `tests/mutants.py` changes only to retarget a `Case` R6 needs, named in the commit body; the
  plan needs none.
- Every bound keeps its value (R9). A phase that finds a row cannot hold with its value stops and
  reports the before-and-after figures; it never widens a slack or a deadline on its own.
- **Stage, then verify.** Every gate mode reads the staged tree (`git write-tree`), and a mode that runs
  tests refuses a working copy that differs from it. Records (`sweep.txt`, `load-runs.txt`,
  `profile-verify.txt`) name the staged `tests/` tree, and `sweep.txt` the gate's own blobs.
- **The gate is pinned at sign-off.** A change to a script under `verify/` after the plan commit is
  named, with its reason, in `verify/amendments.txt` (`scope` checks it), and every sweep part is re-run
  under the changed gate. A fault or a fragment is never edited to fit a row.
- Run every suite command with `UV_PYTHON=3.14` on this host. A gate mode near or over the Bash
  tool's 10-minute cap runs through `run_in_background`; never a disowned launch.
- **Row 4's sign-off decision.** PLAN § 2 proposes D1 (the collector paused for the timed start) and
  gives fallback (c)'s figures (§ 5). P4 builds what the PLAN/TECH sign-off records; this file assumes
  D1. If (c) is signed instead, the plan is amended before P4 (the slack value, `KEPT[4]` and
  `BUILT[4]` in `timing-gate.py`, and the row-4 fault sizes) and re-signed.

## Amendments

- **2026-11-09, the PLAN/TECH gate's rulings.** GOAL (`abe12e3`) and PLAN/TECH (`758e7d1`) signed
  for P1–P3. D2–D7 accepted. D1 (row 4: the collector paused for the timed start, or fallback (c))
  is with the maintainer: P4 does not start until he rules, and if he picks (c), PLAN and TECH are
  amended as Conventions says and re-signed before P4.
- **2026-11-09, P2 (accepted at its gate).** `ensured` is the sum of every span from an entry to
  `SSHExecutor._ensure_connected` to its return during the first call (`math.inf` when there is
  none): should the call enter its reconnect more than once, each entry counts toward the 0.1 s.
- **2026-11-09, the maintainer at the PLAN/TECH gate: D1 approved.** Row 4 times its start with the
  cyclic collector paused; its bounds stay 0.8 s (`hang`, `timeout-code`) and 0.5 s. He added one
  requirement: a row-4 failure reports the collector's pause time in its message, so a later red
  can be attributed. `collector_paused()` yields a record of the seconds any collection still took
  inside the block (an explicit one; the automatic collector is off), timed first among
  `gc.callbacks`, and the row's message ends `the collector pausing it {p:.2f} s of that`. Pinned by
  a fault added to the gate, `4/collects-slowly-in-the-start` (a 0.6 s collection planted inside the
  start; fragment `the collector pausing it 0.6`), and by `MESSAGES[4]`; named in
  `verify/amendments.txt`. PLAN § 2 (row 4) and § 6 follow.
- **2026-11-10, P6: rebased onto `origin/develop`.** The branch moved from `0bfacae` to `146cbc6`
  (no change under `packages/` or to the four rows; `tests/test_hygiene.py` changed), with one
  ROADMAP conflict resolved by keeping both sides (29 Part I entries). The GOAL sign-off is now
  `af1012e` and the plan commit `64137f6`. `timing-gate.py` finds BASE by its subject at run time
  (`verify/amendments.txt`). The re-run sweep on the rebased tree went red at part 4:
  `4/collects-slowly-in-the-start` was killed for the wrong reason, its fragment
  `the collector pausing it 0.6` against a reported pause of 0.67-0.71 s (the planted 0.6 s plus
  the explicit full collection itself). Recorded as an attempt; P6 waits on the fix to that fault.
- **2026-11-10, P6: the fault's fix, as ruled.** `4/collects-slowly-in-the-start` keeps its 0.6 s plant
  and is killed on a predicate, not a digit prefix: each target's failure carries the start-took line
  and a reported collector pause of at least 0.6 s (`planted_pause_reported`, `verify/amendments.txt`).
  The predicate's first draft missed the message (a comma inside its parentheses), caught when shown
  both ways before any run, recorded as an attempt, and fixed. The frozen records citing `abe12e3`
  and `758e7d1` stand; on the rebased branch they are `af1012e` and `64137f6`.

---

## Phase P1 — Row 1 counts each reconnect worker as it starts
**Satisfies:** R1, R7, R9 · **Depends on:** —
**Goal:** the stalled-reconnect row counts the one reconnect worker whether or not it has ended by the
time the call returns, and still fails on each fault in PLAN § 6's row-1 list.

- [x] In `test_a_stalled_reconnect_is_abandoned_against_a_real_handshake`, replace the `before`
  snapshot and the `threading.enumerate()` listing with a `Thread.start` hook
  (`monkeypatch.setattr(threading.Thread, 'start', start)`) that records each thread named `WORKER`
  whose `_target` is `executor._settle`, once its real start returns; keep it on until the joins
  below are done, then restore the real `start` (and in the `finally`). Message: `'{n} reconnect
  workers started during the call, not one'`.
- [x] Join each recorded worker for `STALL_WORKER`; message `'the abandoned attempt was still running
  {STALL_WORKER} s after the call gave up, past its {STALL_WORKER} s bound'`.
- [x] `not_run_violations`: the time message becomes `'the call gave up {elapsed:.2f} s after it began,
  past its {bound} s bound and {slack} s of slack'` (D4). Its check, and row 1's call of it with
  `slack=STALL_LATE`, unchanged.
- [x] Keep `STALL_WINDOW`, `STALL_LATE`, `STALL_WORKER`, the window check and `held` as they are.
- **Verify:** `timing-gate.py row 1`: values (R9, no skip/xfail/early return), scope, the row in both
  eras, faults 1/* (five, ~30 s), control 1 in each era (the tree passes; the base fails with
  `reconnect workers ran, not one`). Measured on the prototype: about 1 min.
- **Touches:** `tests/test_ssh_exec.py`.

## Phase P2 — Row 2 measures the call's waits on the row's clock
**Satisfies:** R2, R7, R9 · **Depends on:** P1
**Goal:** the worker-cannot-start row reads what the call waited on an attempt from `FakeClock`'s
offset, which the MCP round trip never moves, and fails on any such wait.

- [x] In `test_a_reconnect_worker_that_cannot_start_frees_the_attempt`, after `_fake_time`, wrap
  `ssh._await` (`monkeypatch.setattr(ssh, '_await', wait)`) to record each wait the first call makes on
  an unfinished attempt (`seconds > 0`, event unset), then call `clock.wait`.
- [x] `spent` = `clock.offset` after the first call minus before it. Fail on `round(spent, 9) >=
  ssh.ATTEMPT_POLL` (D2) with `'the call whose worker could not start waited {spent:.2f} s for an
  attempt on the row's clock, not giving up within ATTEMPT_POLL ({ATTEMPT_POLL} s)'`, and on any
  recorded wait with `'the call whose worker could not start waited on an attempt ({n} waits, the first
  asking {w:.2f} s), not giving up at once without one'`.
- [x] Wrap `SSHExecutor._ensure_connected` for the first call only, timing it on `_REAL_MONOTONIC`
  into `ensured`; fail on `ensured >= ssh.ATTEMPT_POLL` with `'the executor took {x:.3f} s from
  entering its reconnect to giving up, on the real clock, not under ATTEMPT_POLL ({ATTEMPT_POLL} s)'`
  (`math.inf` when it never ran).
- [x] Keep the message, `held` (`'stayed taken'`), the next call, the refused/started counts and the
  connection count as they are.
- **Verify:** `timing-gate.py row 2`: values, scope, the row in both eras, faults 2/* (five, ~13 s),
  control 2 in each era (the base fails with `not giving up at once`). Prototype: about 35 s.
- **Touches:** `tests/test_ssh_exec.py`.

## Phase P3 — Row 3 decides the raised endings on a probe clock
**Satisfies:** R3, R7, R9 · **Depends on:** P2
**Goal:** a raised ending's "decided when it happened" is read on a clock only the probe's waits move,
and the row proves the probe read it.

- [x] Add `ProbeClock` (`ORIGIN` 100.0, `SETTLE` 10.0 real seconds) to `tests/test_probes.py`, as
  PLAN § 2 describes: proxies for `probes.time` (`monotonic`, `perf_counter`, `monotonic_ns`, and a
  `sleep` that waits for the other probe workers to end before it advances) and `probes.threading`
  (`Event` whose `wait` returns at once when set, and advances the clock by its timeout once every
  other probe worker has ended with it unset; `Thread` that records each worker, or raises
  `unstartable`), and `routed_sleep` for the real `time.sleep` (the clock on the main thread and the
  probe's workers, the real sleep elsewhere).
- [x] In `test_every_ending_without_an_answer_serves_the_capability`, install both proxies for every
  ending (`thread-cannot-start` through `unstartable`; keep `threading_whose_start_raises` for the
  interrupt row). Keep the reason check and `took <= BOUND + SLACK`, its message naming both
  (`'the verdicts took {took:.2f} s, past the bound ({BOUND} s) and its slack ({SLACK} s)'`). Add the
  engagement check (D3), wanting a recorded worker for every ending but `thread-cannot-start`, and
  route `time.sleep` (`monkeypatch.setattr(time, 'sleep', clock.routed_sleep)`). For RAISED endings, `waited < BOUND / 2` on the clock, with the message of
  PLAN § 2 (it keeps `decided only at the deadline`).
- [x] Keep `BOUND`, `SLACK`, `RAISED` and the executor-call count as they are.
- **Verify:** `timing-gate.py row 3`: values, scope, the 56 RAISED tests in both eras, faults 3/*
  (six, ~12 s), control 3 in each era (the base's 56 fail with `decided only at the deadline`).
  Prototype: about 1 min.
- **Touches:** `tests/test_probes.py`.

## Phase P4 — Row 4 times the start with the collector paused
**Satisfies:** R4, R7, R9 · **Depends on:** P3
**Goal:** a timed start is charged no collector pause, and still fails on any wait past the probe's
bound and its slack. (As signed: D1 assumed; see Conventions.)

- [x] Add `collector_paused()` (a context manager: `gc.disable()`, re-enabled after only if it was on)
  to `tests/test_probe_startup.py`, and wrap the row's `start(...)` call in it. It yields the
  seconds any collection still took inside the block (Amendments, the maintainer's requirement).
- [x] Keep the comparison `observed.seconds >= (0.3 if ending in ('hang', 'timeout-code') else 0) + 0.5`;
  the message becomes `"the start took {s:.2f} s, past its {b + 0.5:g} s bound (the probe's own wait,
  {b:g} s, and 0.5 s of slack), the collector pausing it {p:.2f} s of that"`.
- **Verify:** `timing-gate.py row 4`: values, scope, the 192 tests in both eras, faults 4/* (four, with
  `collects-slowly-in-the-start`),
  control 4 (the base fails with `the start took`; ~2 min, the base's 192 starts each taking a 0.6 s
  collection, in each era). Prototype: about 4.5 min (the base's controls about 3.5 min of it).
- **Touches:** `tests/test_probe_startup.py`.

## Phase P5 — The final sweep on the final tree, every row and the named cases, and R8's figures
**Satisfies:** R6, R8, R9 · **Depends on:** P4
**Goal:** R6 shown on the final tree, recorded: every planted fault of every row red, every control
green on the tree and red on the base, the 32 existing cases that name the rows (and the 11 that
quote the reworded give-up message) still killed; and each
touched module's local time before and after.

- [x] Commit the final row code first (nothing in `tests/` changes after this phase's runs).
- [x] Run `timing-gate.py sweep 1`, `sweep 2`, `sweep 3`, `sweep 4`, `sweep cases`, `sweep times`, one
  at a time (measured on the prototype: under 2 min each for parts 1–3, about 4.5 min for part 4 and
  for `times`, 198 s for `cases`; any in the background if a measured run nears 10 min). Each appends its line, with the staged `tests/` tree and
  the gate's blobs, to `verify/sweep.txt`. A red part on the final tree goes to the foreman with its
  line: `sweep-check` keeps failing on it, and a later green on the same tree does not wash it out.
- [x] Note in this phase's commit body the `times` lines (R8: per-module seconds, base and HEAD).
- **Verify:** `sweep-check`, `values 1 2 3 4`, `scope`. R6 is graded from `verify/sweep.txt` by the
  orchestrator.
- **Touches:** `spec/stalled-reconnect-test-timing/verify/sweep.txt`.

## Phase P6 — R5's load protocol, the profile's verify, and the deferral ledger
**Satisfies:** R5, R8 · **Depends on:** P5
**Goal:** R5's protocol on the final tree, recorded; the full gate green once; every deferral seeded.

- [x] With the tree committed and nothing else of this cycle running, run
  `verify/load-protocol.py run` with `run_in_background` (about 20 min: 20 runs alone per row, then
  four spinners and the profile's suite commands beside 20 loaded runs per row). The load comes from
  the four spinners (four cores) and the beside suite; record the host's load averages as the script
  does. If a row fails a run, stop: it is a finding for the gate, not a re-run.
- [x] Then, alone, `timing-gate.py profile run` with `run_in_background` (the profile's `verify`,
  about 25 min), recorded in `verify/profile-verify.txt`.
- [x] Deferral ledger: walk P1–P6 and this cycle's commit bodies for "do not fix here", "known
  limitation", "left as a follow-up", "deferred" and "not fixed"; each needs an `issues/` seed and a
  ROADMAP entry (`timing-gate.py ledger`). The plan defers nothing; a deferral a phase adds files its
  seed in that phase's commit.
- [x] Standing last-phase items: the ledger, as `suite-ci-time-budget`'s last phase carried.
- **Verify:** `load-protocol.py check`, `profile check`, `sweep-check`, `scope`, `ledger`. R5 is
  graded from `verify/load-runs.txt` by the orchestrator.
- **Touches:** `spec/stalled-reconnect-test-timing/verify/load-runs.txt`,
  `spec/stalled-reconnect-test-timing/verify/profile-verify.txt`.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[test]` commit; stop and report.
