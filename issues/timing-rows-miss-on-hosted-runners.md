---
status: unshaped
kind: test
appetite: small
lane: public
---

# Two timing rows miss their bound on hosted runners, with nothing else wrong

## Problem

Two real-time rows failed on GitHub-hosted Linux runners on commits whose other CI runs passed. In
each, the row's only failing check was its wall-clock bound; every behaviour check in the row held.

- **The start that follows the site read** (`tests/test_probe_startup.py::test_the_probe_follows_the_site_read_and_is_bounded[slurm]`,
  failing at `tests/test_probe_startup.py:406`). `main` CI run 43252074771, on `ea1b2c4` (the 0.2.0
  release commit), job `suite (modern era, 4 of 4)`, 1 failed and 4381 passed in 212 s:

  > AssertionError: a hung probe was not held to its bound after the site read: the start took 1.58 s, past the site read and the bound

  `develop`'s run 43239019503 on the same commit was green. The row sleeps 0.5 s in the site read,
  hangs the probe with `PROBE_TIMEOUT` at 0.6 s, and requires the whole start in under
  0.5 + 0.6 + 0.3 s = 1.4 s (`:400`), timed by `time.monotonic()` around `MCPServerApp.main` (`start`,
  `:243–248`). It ran 0.18 s past that. Its order (the probe after the site read), its build (every
  capability) and its log lines ("did not answer within 0.6 s") all matched, so the probe was cut at
  its own bound and reported as such.
- **The return of a stopped call** (`tests/test_timeout_stop.py::test_a_timed_out_command_is_stopped[delegate-root-ignores-none]`,
  failing at `tests/test_timeout_stop.py:280`). Run 43259703879 on `94d205d`
  (`fix/sandbox-dirs-left-on-kill`, whose diff does not touch the launch, the executors or the
  timeout stop), job `suite (modern era, 3 of 4)`, 1 failed and 510 passed in 221 s:

  > AssertionError: delegate-root-ignores-none: run returned 0.74 s after the deadline, later than a launcher without the watchdog would (0.5 s)

  Where a launcher without the watchdog would return at the deadline's TERM, `run` must return
  within `AT_ONCE` = `GRACE / 2` = 0.5 s of the deadline (`:91`). The check exists to catch a watchdog
  that holds the output and so holds the call to its KILL, about `GRACE` (1.0 s) later. The deadline
  is `start + TIMEOUT` with `start` taken before the call, so the measured 0.74 s overstates the true
  lateness, if anything. The row's stop check (every process gone within the bound) and its exit code
  both held.

**Read of each, unverified.** Neither failure was reproduced or rerun.

- The site-read row looks like a wall-clock measurement on a loaded runner, not a breach. It is timed
  with the cyclic collector running, in the shard that runs the bulk of the suite, which is the
  mechanism `stalled-reconnect-test-timing` found for its sibling row. That cycle named the bounded
  start as `test_every_ending_without_an_answer_serves_every_capability` and timed it with the
  collector paused (`collector_paused()`, `:410–440`). This row is a different row, outside that
  cycle's scope, and has neither the pause nor a load run behind it. So the cycle's fix did not fail
  here: it was never applied here. The row cannot say where its 1.58 s went (site read, probe wait,
  collector, scheduling), so a late probe deadline would read the same.
- The stop row also looks like a loaded runner, not a breach. 0.74 s lies between returning at the
  TERM and being held to the KILL, which `test_timeout_stop.py:79` records as landing at most 1.09 s
  after the deadline. A call held to the KILL could not return before it. `delegate-root` adds the
  root `sudo` stand-in (`ROOT_RELAY`) to the path, on a hosted runner running the startup and
  launch suites in the same job. The module records a measured margin for `HELD`
  (`:83–87`) and none for `AT_ONCE`.

Both rows are pre-existing on `develop`. The site-read row landed with `capability-probe`
(2026-11-01) and the stop row's `AT_ONCE` check with `timeout-process-cleanup` (2026-11-04).

## Why it was deferred

Both were found on CI runs for other work, a release and a fix branch, and neither is in that work's
scope. Making a row fail only on behaviour is a test cycle of its own, as
`stalled-reconnect-test-timing` was, and any change to a bound or slack is the maintainer's ruling,
not a pass's.

## Outcome / vision

Each row still fails when the behaviour it guards breaks, and no longer fails because a hosted
runner is busy. When it does fail, its message says what was measured against what, so a load miss
and a behaviour miss read differently at the gate.

## Sketch of the acceptance criteria

- **R1**: WHEN a start waits past the site read and the probe's bound, the site-read row SHALL fail;
  WHEN the start is bounded, the row SHALL NOT fail on a hosted runner or under the load protocol
  `stalled-reconnect-test-timing` used.
- **R2**: WHEN `run` holds a call whose top's output has ended until the watchdog's KILL, the
  `ignores-none` stop rows SHALL fail; WHEN `run` returns at the TERM, they SHALL NOT fail on a
  hosted runner or under the load protocol.
- **R3**: WHEN either row fails on time, its message SHALL name the measured span, the bound, and
  any time the row excluded from the measure.
- **R4**: No bound, slack or `TIMEOUT` SHALL be loosened without the maintainer's ruling; a proposed
  change SHALL come with the before-and-after numbers.
- **R5**: The gate's time SHALL stay within the profile's CI budget, and no row SHALL leave the gate.

## Notes

- Related: `spec/stalled-reconnect-test-timing/` (GOAL rows 3 and 4, R4, `collector_paused()`);
  `issues/timing-rows-unrouted-waits.md`; `spec/capability-probe/`; `spec/timeout-process-cleanup/`.
- Found by: an out-of-cycle read of CI, 2026-11-12 (`main` run 43252074771; branch run 43259703879).
