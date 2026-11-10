---
status: unshaped
kind: test
appetite: small
lane: public
---

# Two timing rows miss a wait made outside the clock they control

## Problem

Two real-time rows now measure their property on a clock the test controls, not on the wall clock.
Each still misses a deeper variant of the fault it pins: a wait made through a primitive that the
row's clock does not route.

- **The probe's raised endings** (`tests/test_probes.py::test_every_ending_without_an_answer_serves_the_capability`,
  the `RAISED` rows; `ProbeClock` at `tests/test_probes.py:277`). The row proves a raised ending is
  decided as it happens and not at the probe's deadline: only the probe's own waits move its clock.
  A probe that binds the real `time.sleep` at import (`_wall_sleep = time.sleep`) and sleeps out the
  deadline before posting its answer leaves all 14 raised rows green, because a module-level alias
  taken before the row installs its clock waits in real time and is never seen. On `develop` before
  this change, the same fault turns every raised row red, through its reason check or "decided
  only at the deadline (0.31 s)". The plainer bypasses are already caught: a probe that imports `monotonic` or `Event` directly
  turns the row red through its check that the clock was engaged, and a deadline wait on the routed
  primitives is killed by the row's planted faults.
- **The worker that cannot start** (`tests/test_ssh_exec.py::test_a_reconnect_worker_that_cannot_start_frees_the_attempt`,
  line 2035). The row proves a call whose reconnect worker could not start gives up at once: it
  counts the call's waits on the row's clock, through `_await` (`packages/cluster-mcp/src/cluster_mcp/core/executor/ssh.py:531`).
  A wait shorter than a poll made directly on the attempt's event (`pending.done.wait(0.05)`),
  bypassing `_await`, leaves the row green. On `develop` before this change the same fault went
  red ("took 0.1 s, not giving up at once"), but only because that row timed the whole call by wall
  clock, the measure that made it fail on a busy host. Waits of a full poll, half a poll and a real
  poll through `_await`, and a back-off sleep, are all caught.

Both were found by hand-planted faults in a blind review, on a tree whose rows pass 20 of 20 alone
and under load. Neither is a defect in the product: each is a fault a future change could
introduce that the row would not notice.

## Why it was deferred

Each is a deeper layer of a property the row already pins with planted faults that it kills, so the
review recorded them as coverage observations rather than blocking. Closing them means deciding how
far a test-controlled clock should reach (aliases bound at import, every `Event.wait` in the
module), which is a design question for its own cycle. Introduced with the clocks these rows gained
in `stalled-reconnect-test-timing`; the wall-clock rows before it caught both faults, at the price
of failing under load.

## Outcome / vision

A raised probe ending decided only at the deadline, and a call that waits on its attempt at all after
its worker could not start, turn the row red whatever primitive the wait goes through, and the rows
still pass on a busy host.

## Sketch of the acceptance criteria

- WHEN a probe sleeps or waits out its deadline through a real-time primitive bound before the row
  installs its clock, the raised-ending rows SHALL fail.
- WHEN a call whose reconnect worker could not start waits on the attempt's event directly, for any
  time, before giving up, the worker-cannot-start row SHALL fail.
- Both rows SHALL keep their bounds and pass under the load protocol their cycle used.

## Notes

- Related: `spec/stalled-reconnect-test-timing/` (REVIEW.md, cycle 1, coverage observations);
  `tests/mutants.py` (a kept case per fault, if the cycle wants them pinned there).
- Found by: `stalled-reconnect-test-timing`, review cycle 1 (blind reviewer's hand-planted faults).
