---
status: unshaped
kind: test
appetite: small
lane: public
---

# `ssh-returns-at-exit-status` is killed for its reason in one hosted run and not the next

## Problem

The mutation case `ssh-returns-at-exit-status` (`tests/mutants.py:933`) makes the SSH executor's
read loop return as soon as the channel's exit status is ready, before the end records arrive. Its
six targets in `tests/test_ssh_exec.py` must each fail with the `why` "cut before its end records":

- `test_a_slow_link_returns_the_whole_file[256KiBps]`
- `test_a_stalling_link_returns_the_whole_file[stall-1.6s-after-exit]`
- `test_a_stalling_link_returns_the_whole_file[packets-6000Bps]`
- `test_a_slow_link_returns_both_streams_whole`
- `test_a_late_sentinel_still_counts_as_started[bashrc]`
- `test_a_job_that_ran_is_never_reported_as_not_started`

The case gave different verdicts in two hosted runs of the same code:

- **Run 1** (run `43255195424` at `aff08bd`, 2026-11-12, shard 3 of 78): killed. All six targets
  failed with the `why`.
- **Run 2** (run `43260825655` at `32e1d5c`, which differs from `aff08bd` only in records,
  2026-11-12, shard 3 of 78): reported `FAILED`. Five targets failed with the `why`, but
  `test_a_late_sentinel_still_counts_as_started[bashrc]` failed "for the wrong reason (no 'cut
  before its end records' in the failure)".
- **macOS at `aff08bd`**, run alone (`uv run python tests/mutants.py ssh-returns-at-exit-status`):
  killed, all six targets with the `why`, in 10 s.

So in every run the rows caught the mutant. What varied was the reason one row gave. Under the
runner's rule (every target fails, and with the `why`), that single row decides whether the case is
reported killed.

**Likely cause (unverified):** the row is timing-dependent under the mutant.
- `[bashrc]` runs over a throttled 512 KiB/s link behind a 1 MiB chatty `~/.bashrc`, so the
  sentinel arrives seconds after the exit status of a short command (`tests/test_ssh_exec.py:588-613`).
- Under the mutant the call returns at the exit status. Depending on when that status arrives
  relative to the late sentinel, the row may stop at an exception from `_run` or `executor.write`
  before it reaches the assertion that carries the `why`.

The runner's line does not quote the row's failure text, so which failure it was is unknown.

## Why it was deferred

The cycle that found it, `mutants-workflow-timeout`, has a non-goal: it changes no case, target or
`why`. The foreman ruled that across its runs 2 and 3, a case killed in one run and not in another
is reported as a flaky case and seeded.

The case and its rows are **pre-existing**: both are older than the cycle.

## Outcome / vision

`ssh-returns-at-exit-status` gets the same verdict on every run of the same code, on the hosted
runner and on macOS. The executor's behaviour and the row's checks on unmutated code are unchanged.

Possible fix shapes, for shaping to choose between:
- make every failure path of `test_a_late_sentinel_still_counts_as_started[bashrc]` under the mutant
  carry the `why`. For example, catch the call's exception and report it inside the row's own
  assertion, which names "cut before its end records";
- drop `[bashrc]` from the case's targets, since the other five pin the same mutant with its `why`
  on both runs.

## Sketch of the acceptance criteria

- **R1** — WHEN `ssh-returns-at-exit-status` is applied, on the hosted Linux runner or macOS, every
  target of the case SHALL fail with "cut before its end records" on every run.
- **R2** — WHEN it is not applied, its target rows SHALL pass as they do today.

## Notes

- Related: `issues/timing-rows-miss-on-hosted-runners.md` (on `develop`). A related cause, timing
  on a loaded hosted runner, but a different mechanism: there, unmutated rows miss a wall-clock
  bound; here, a mutant's failure path varies with timing.
- Related: `issues/mutants-linux-bashrc-norc.md`, `issues/mutants-linux-posix-paths.md`,
  `issues/mutants-linux-fd-59.md`, `issues/mutants-linux-transfer-cause.md`: the stable Linux-only
  survivors of the same runs. `spec/mutants-workflow-timeout/` (TECH Amendments, 2026-11-12, P4 run 2)
  holds the run's figures.
- Found by: mutants-workflow-timeout P4, the second hosted run (2026-11-12).
