---
status: unshaped
kind: test
appetite: small
lane: public
---

# A real-time reconnect test fails under full-suite load

## Problem

`tests/test_ssh_exec.py::test_a_stalled_reconnect_is_abandoned_against_a_real_handshake` drives a
real SSH handshake against a silent loopback host and checks the call gives up within its window
(`STALL_WINDOW`, 3 s) plus `STALL_LATE` (0.5 s) of slack, then that the abandoned worker ends within
`STALL_WORKER` (1 s). These are wall-clock bounds.

On 2026-10-28 it failed once during a full local `pytest -q` (handshake era, macOS, 1 failed /
2127 passed), then passed three times run alone and in the next full run. CI has not shown it. The
assertion text of the failing run was not kept, so which bound was missed is unknown.

A test that fails on load, not on behaviour, teaches builders to re-run red gates.

- 2026-10-29: a second loopback test, `test_startup_output_is_separated[tcsh]`, failed on CI (run
  40812003663, modern era, branch `fix/resource-reads-without-executor` at `344a3a3`) with
  `EOFError` from paramiko's packet reader; 2214 others passed, and the re-run of the same commit
  passed 2215 in both eras. That branch changes no SSH code. So the class may be wider than one
  wall-clock bound: the loopback SSH server under load. Shaping should check both.
- 2026-11-01: `test_startup_output_is_separated[tcsh]` failed again on CI with the same paramiko
  `EOFError` (run 41375322079, handshake era, branch `ci/split-eras` at `3a87f35`, which changes
  only the workflow and AGENTS.md); the server side logged `Connection reset by peer`. 4573 others
  passed, and the re-run of the failed job passed. It is the second CI failure of this row.
- 2026-10-30: during `rename-to-cluster-mcp`, the test failed in local full-suite runs at two
  phase gates (macOS), once at P2 and twice in a row at P5's remediation (modern era); each time
  it passed alone and on a further identical-tree run. The failing assertion was "0 reconnect
  workers ran, not one": the reconnect worker never started, so the miss is not only the
  give-up bound.

## Why it was deferred

Seen during `resource-reads-without-executor`'s final gate. That cycle touches no SSH code, and the
test passed on re-run, so it was filed, not grown into that cycle.

**Pre-existing:** yes. The test was added by `ssh-reconnect-loop` (landed 2026-10-27).

## Outcome / vision

The test still fails if the call's give-up or the worker's abort stops working. It no longer fails
because the host is busy. Possible directions: bound the measured interval from the moment the
attempt reaches the silent host, rather than from the call; widen only the slack that measures
scheduling; or mark it so that a load-sensitive failure reports its measured times.

## Non-goals

- Changing the reconnect bound or the window arithmetic in `executor/ssh.py`.

## Related materials

- `tests/test_ssh_exec.py` (`STALL_WINDOW`, `STALL_LATE`, `STALL_WORKER`, `not_run_violations`).
- `spec/ssh-reconnect-loop/`.
