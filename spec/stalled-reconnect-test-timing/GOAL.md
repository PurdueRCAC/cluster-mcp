# GOAL — Real-time tests fail on behaviour, not on a busy host

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** stalled-reconnect-test-timing
- **kind:** test
- **appetite:** small

## Problem

Several rows of the suite check a property by wall clock, and each has failed on a busy host and
then passed alone and on re-run of the identical tree. A row that fails on load, not on behaviour,
teaches builders to re-run red gates, and every such re-run is a gate whose verdict nobody trusts.
The record is the seed ([`issues/stalled-reconnect-test-timing.md`](../../issues/stalled-reconnect-test-timing.md));
the rows, their bounds and their sightings, confirmed against `develop` at `0bfacae`:

1. **The stalled reconnect** (`tests/test_ssh_exec.py::test_a_stalled_reconnect_is_abandoned_against_a_real_handshake`,
   `integration`). A real SSH handshake against a silent loopback host must give up within
   `STALL_WINDOW` (3 s) plus `STALL_LATE` (0.5 s) of the call's start, and the abandoned worker must
   end within `STALL_WORKER` (1 s) after (`tests/test_ssh_exec.py:2120–2165`). Six local
   full-suite or union-run failures (2026-10-28, text not kept; 2026-10-30 ×3; 2026-11-05 ×2), never
   on CI. Every failure whose text was kept said **"0 reconnect workers ran, not one"**, which is not a missed
   time bound: the row counts reconnect workers by listing live threads once `executor.run` has
   returned (`:2148`), after the call has given up. Alone, the row's call took 3.04–3.12 s.
2. **The worker that cannot start** (`tests/test_ssh_exec.py::test_a_reconnect_worker_that_cannot_start_frees_the_attempt`).
   The call must give up within `ssh.ATTEMPT_POLL` (0.1 s) of measured time (`:2075`). One local
   full-suite failure (2026-11-04) and one on CI (2026-11-05, "took 0.3 s, not giving up at once").
   Measured on macOS: alone, 19 of 20 on `develop`; alternated under four CPU spinners beside other
   suites (load 22–26), 12 of 20, the same on a branch that changes nothing on the path.
3. **The probe's raised endings** (`tests/test_probes.py::test_every_ending_without_an_answer_serves_the_capability`,
   rows in `RAISED`). A raised ending must be decided in under `BOUND / 2` (0.15 s, `BOUND` 0.3 s;
   `:291`), the row's proof that it was decided when it happened and not at the deadline. Four CI
   failures: 0.20 s (2026-11-01, `interrupt-both`), 0.25 s (2026-11-05, `interrupt-rcac`), 0.18 s
   (2026-11-06, `interrupt-both`), and 0.23 s on a fourth parameter, `exit-0-slurm` (run
   42678748547, job `suite (modern era, 4 of 4)`, "decided only at the deadline (0.23 s)").
4. **The bounded start** (`tests/test_probe_startup.py::test_every_ending_without_an_answer_serves_every_capability`).
   A start must finish in under the probe bound plus 0.5 s (0.8 s for `hang` and `timeout-code`,
   0.5 s otherwise; `:470`). One CI failure: 0.85 s (2026-11-05, `hang-ssh-sse-core-only`).

The seed also records loopback SSH rows that broke under load with Paramiko's `EOFError` or a
socket error, missing no time bound. Their mechanism is unknown and may lie outside the tests; they
are their own `fix` seed, [`issues/loopback-ssh-breaks-under-load.md`](../../issues/loopback-ssh-breaks-under-load.md)
(Clarifications, 2026-11-09).

Rows 1–4 are pre-existing (row 1 landed with `ssh-reconnect-loop`, 2026-10-27; rows 3–4 with
`capability-probe`, 2026-11-01). Each property they guard is real and must stay guarded: the
reconnect gives up in its window and abandons its attempt; a worker that cannot start frees the call
at once; a raised probe ending is decided before the deadline; a start never waits past the probe's
bound. Three failures kept no assertion text, so which bound was missed is unknown for them.

## Outcome / vision

Each in-scope row still fails when the behaviour it guards breaks, and no longer fails because the
host is busy. When a real-time row does fail, its message says what was measured against what, so a
load miss and a behaviour miss read differently at the gate. The gate's time stays within the
profile's CI budget, and no row leaves the gate.

## Acceptance criteria (the contract)

In scope: rows 1–4 of Problem (Clarifications, 2026-11-09). "The load protocol" is the one
Clarifications records: 20 runs alone and 20 under four CPU spinners beside a full-suite run, on
macOS.

- **R1** — WHEN the stalled-reconnect row runs and one attempt reaches the silent host, the row
  SHALL count that attempt's reconnect worker, whether or not the worker has ended by the time the
  call returns; it SHALL still fail when the call does not give up within its window plus its
  allowed lateness, when no attempt or more than one worker runs, and when the abandoned attempt is
  still running past its allowed time after the give-up.
- **R2** — The worker-cannot-start row SHALL still fail when a call whose reconnect worker could not
  start waits for an attempt before giving up, and SHALL NOT fail on a host under the load
  protocol when the call gives up at once.
- **R3** — The probe's raised-ending rows SHALL still fail when a raised ending is decided only at
  the probe's deadline, and SHALL NOT fail on a host under the load protocol when it is
  decided as it happens.
- **R4** — The bounded-start rows SHALL still fail when a start waits past the probe's bound, and
  SHALL NOT fail on a host under the load protocol when the start is bounded.
- **R5** — Each in-scope row SHALL pass 20 of 20 runs alone and 20 of 20 runs under four CPU
  spinners beside a full-suite run, on macOS, on the cycle's final tree, with the runs and their
  pass counts recorded under `spec/stalled-reconnect-test-timing/`. No extra CI dispatch is part of
  this criterion.
- **R6** — For each property R1–R4 says a row SHALL still catch, a planted fault that breaks it
  SHALL turn the row red, shown on the cycle's final tree; an existing `mutants.CASES` entry that
  names a changed row (`ssh-reconnect-unstarted-worker-holds-slot` names row 2) SHALL still be killed.
- **R7** — IF an in-scope row fails on a measured interval, THEN its failure message SHALL name the
  interval measured, its value and the bound it missed.
- **R8** — Every suite job SHALL stay within the profile's `ci budget` row (10 minutes each), the
  gate's commands and its partition SHALL be unchanged, and every in-scope row SHALL still run once
  per era in the gate.
- **R9** — Every in-scope row's bound SHALL keep its value (row 1: 3.0 s + 0.5 s, then 1.0 s; row
  2: 0.1 s; row 3: 0.15 s against a 0.3 s deadline; row 4: 0.8 s or 0.5 s); what changes is the
  point it is measured from or against. A value MAY change only by the fallback the Clarifications
  name for that row, and only after its before-and-after figures, CI time included, are signed off.

## Non-goals (no-gos)

- **Passing by proving less.** No in-scope row drops an assertion, is skipped, `xfail`ed, marked
  flaky, re-run on failure or moved out of the gate; and no bound is widened so far that the broken
  behaviour it guards would pass. A change that makes a row green by loosening what it proves fails
  this GOAL, whatever its pass rate.
- **Product behaviour and its bounds.** No change under `packages/`: `RECONNECT_FACTOR`,
  `ATTEMPT_POLL`, `CONNECT_TIMEOUT`, `PROBE_TIMEOUT`, the reconnect window arithmetic in
  `executor/ssh.py` and the probe's bound in `core/probes.py` stay as they are. If the plan finds a
  product defect behind a row, the cycle stops and the defect becomes a `fix` seed.
- **The CI budget and the gate's shape.** The `ci budget` row, the verify command, the job split and
  `timeout-minutes` are not changed here.
- **A suite-wide sweep** of every wall-clock read (about 180 `monotonic()` reads across 13 test
  modules).
- **The loopback SSH breaks**: [`issues/loopback-ssh-breaks-under-load.md`](../../issues/loopback-ssh-breaks-under-load.md).
- **The mutation runner and the skip check.** `tests/mutants.py`'s runner and `tests/test_hygiene.py`'s
  skip check belong to sibling cycles (`mutants-workflow-timeout`, `mutant-child-outlives-timeout`,
  `skip-check-fence-gaps`); this cycle adds or retargets `mutants.CASES` entries only where R6 needs
  one.

## Clarifications

- **Q:** Which rows does this cycle cover? — **A:** Rows 1–4, the four wall-clock rows, with the
  `exit-0-slurm` sighting of row 3 added to Problem. The loopback SSH breaks become their own `fix`
  seed, `issues/loopback-ssh-breaks-under-load.md`. A single row, all five groups and a suite-wide
  sweep were declined (resolved 2026-11-09).
- **Q:** Under what load, how many runs and what pass count make R2–R5 hold? — **A:** 20 of 20 run
  alone and 20 of 20 under four CPU spinners beside a full-suite run, on macOS; no extra CI
  dispatches. Before: row 2 passed 19 of 20 alone and 12 of 20 alternated under that kind of load
  (load 22–26); rows 1, 3 and 4 have sightings only (resolved 2026-11-09).
- **Q:** May the plan change a row's bound? — **A:** Row 1 needs no bound change: its kept failures
  are the worker count (R1). Rows 2–4 keep every value and change the reference point: what the
  interval is measured from (for instance the moment the attempt reaches the host) or against (the
  deadline the same run sets), or a clock the test controls where the property is an ordering, not a
  duration. Fallbacks, a constraint on the plan: rows 2 and 3 may instead raise the deadline the row
  sets so that "decided as it happens" and "decided at the deadline" lie further apart (row 3: for
  instance a 3 s deadline with a 1.5 s cut, before 0.3 s and 0.15 s); row 4 alone may widen its
  scheduling slack (before 0.5 s, so 0.8 s or 0.5 s in all). A fallback comes back to the maintainer
  with before-and-after figures, the CI job times against the `ci budget` row included, before it
  lands (resolved 2026-11-09).

## Related materials

- Seed: [`issues/stalled-reconnect-test-timing.md`](../../issues/stalled-reconnect-test-timing.md)
- Split out: [`issues/loopback-ssh-breaks-under-load.md`](../../issues/loopback-ssh-breaks-under-load.md)
- `tests/test_ssh_exec.py` (`STALL_WINDOW`, `STALL_LATE`, `STALL_WORKER`, `not_run_violations`,
  `_fake_time`, `test_a_reconnect_worker_that_cannot_start_frees_the_attempt`)
- `tests/test_probes.py` (`BOUND`, `SLACK`, `RAISED`); `tests/test_probe_startup.py` (`ENDINGS`)
- `tests/mutants.py` (`ssh-reconnect-unstarted-worker-holds-slot`)
- `AGENTS.md` § Factory (`ci budget`, `verify`), § Conventions ("CI mirrors the gate")
- Prior cycles: [`spec/ssh-reconnect-loop/`](../ssh-reconnect-loop/), [`spec/capability-probe/`](../capability-probe/),
  [`spec/ssh-half-open-link/`](../ssh-half-open-link/) (P3's alternated load measurement of row 2),
  [`spec/suite-ci-time-budget/`](../suite-ci-time-budget/)
- Sibling 0.2.0 gate cycles that touch the same files: `mutants-workflow-timeout` and
  `mutant-child-outlives-timeout` (`tests/mutants.py`, if R6 adds a case), `skip-check-fence-gaps`
  (`tests/test_hygiene.py`, if the plan adds a static check)
