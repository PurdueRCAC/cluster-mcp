---
status: unshaped
kind: test
appetite: small
lane: public
---

# The mutation runner's stop path is pinned for its main layer, not its deeper ones

## Problem

`mutant-child-outlives-timeout` gave `tests/mutants.py` a stop path: `run_child` starts a case's
child in a session of its own, and at the 300 s limit, or on the runner's own SIGTERM, SIGHUP or
SIGINT, `stop_run` finds every process of the run (`run_members`), stops it, and waits for it to be
gone (`_wait_gone`) before `run_case` reports the case. Its fast tests in `tests/test_mutations.py`
and its integration row pin each behaviour the GOAL asks for, and every mutant that breaks an R-ID's
check is killed.

Review cycle 3 left 13 survivors that each pin a deeper layer of a class already pinned. The code is
correct on each (the review's real drives show it); a change of the kind each mutant makes would pass
every row:

- `rm-skip-zombies` (additive) — `run_members` skipping zombies: no walk table has one, so an orphan
  reachable only through a zombie session leader's group could be left running under "was stopped".
- `wg-swallow-look` — `_wait_gone` swallowing a failed look: no row makes a look fail inside the wait,
  only at the walk's looks (`ps-cannot-start`, `ps-fails-mid-walk`).
- `wg-swallow-look-left` — the same, with the processes still left: the same missing row.
- `rc-stop-catch-two` — `run_child`'s catch around the stop narrowed: pinned for `BlockingIOError`
  and `CalledProcessError` only, not for other `OSError` or `Exception`.
- `rc-stop-catch-oserror` — the same catch narrowed to `OSError`: the same gap.
- `rc-notstarted-blocking-only` — the launch-failure catch narrowed to `BlockingIOError`: pinned for
  `BlockingIOError` and `SubprocessError` only.
- `rs-exception-base` — `RunnerSignal` based on `Exception`: it would be reported as a failed look
  and the sweep would go on; "a signal is not a failed look" is pinned for `KeyboardInterrupt` only.
- `wg-deadline-first` (reorder) — `_wait_gone` checking its deadline before its last look: the report
  may name a pid that died in the last poll; the "left" class is pinned by `gone_waits…[still-running]`.
- `rcase-broad-catch` (additive) — an `except Exception` around `run_child` in `run_case`: a decode
  error of a child's output would become a `FAILED` line where `develop` crashes, and the gate that
  holds the runner byte-identical exempts `run_case`.
- `sr-wait-gone-groups-wrapper-only` — `stop_run` waiting on the wrapper's group only: it matters only
  for a fork racing SIGSTOP into another group.
- `send-no-swallow-perm` — `_send` not swallowing `EPERM`: reaching it needs another real uid, which
  an unprivileged run cannot start.
- `sos-valueerror-propagates` — `stop_on_signals` letting its `ValueError` out: reached only off the
  main thread, which never happens today.
- `main-extra-sigint-ignore` (additive) — an extra SIGINT ignore in `main`: no R-ID, and the
  documented Ctrl-C behaviour is not pinned against extra statements.

The ids are the review's; its tables give each mutant's edit and evidence.

## Why it was deferred

Each is a hand-made mutant that pins a deeper layer of a class already pinned, so it is a coverage
observation, not a finding: the factory's mutation method (`method/mutation-testing.md` § When a
review is done, in the operator's KB) seeds such survivors, so that a review converges instead of
chasing an endless series of deeper layers. The maintainer's standing ruling of 2026-11-12 applies:
a round with only LOW findings and deeper-layer survivors fixes the findings, seeds the survivors
and lands. Introduced with the stop path in `mutant-child-outlives-timeout`; not pre-existing,
since `develop` before it had no stop path.

## Outcome / vision

Each survivor is killed by a row, or ruled equivalent with its reason, and the runner's behaviour and
its 300 s limit are unchanged.

## Sketch of the acceptance criteria

- **R1** — WHEN any of the 13 mutants above is applied to `tests/mutants.py`, at least one row of
  `tests/test_mutations.py` or the runner's integration row SHALL fail, unless the cycle rules it
  equivalent with the reason recorded.
- **R2** — WHEN no mutant is applied, every runner row SHALL pass as it does today, and no timing
  figure (`LIMIT`, `GONE_WITHIN`, `GONE_POLL`) SHALL change.

## Notes

- Related: `spec/mutant-child-outlives-timeout/` (REVIEW.md, cycle 3, "Mutant sweep: survivors",
  coverage observations); `issues/sandbox-dirs-left-on-kill.md` (the same stop path's leftover
  sandbox home); `issues/mutants-workflow-timeout.md` (the workflow that runs the runner).
- Found by: `mutant-child-outlives-timeout`, review cycle 3 (2026-11-10).
