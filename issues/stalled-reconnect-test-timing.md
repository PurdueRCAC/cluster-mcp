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
- 2026-11-01: the class reaches beyond SSH. `capability-probe`'s
  `tests/test_probes.py::test_every_ending_without_an_answer_serves_the_capability[interrupt-both]`
  failed on CI (run 41377031448, handshake era, `ci/split-eras` at `c8843b2`): a raised ending must be
  decided in under `BOUND / 2` (0.15 s) and took 0.20 s. 4573 others passed, and the same commit
  passed in both eras on `develop` (run 41377033067). It is a wall-clock bound a busy runner can
  miss, like the reconnect row's; shaping should sweep every such bound in the suite, not one test.
- 2026-10-30: during `rename-to-cluster-mcp`, the test failed in local full-suite runs at two
  phase gates (macOS), once at P2 and twice in a row at P5's remediation (modern era); each time
  it passed alone and on a further identical-tree run. The failing assertion was "0 reconnect
  workers ran, not one": the reconnect worker never started, so the miss is not only the
  give-up bound.
- 2026-11-01: `test_startup_output_is_separated[bash]` failed once in a local full-suite run
  (macOS, modern era, branch `fix/timeout-process-cleanup` before its first build commit) with the
  same paramiko `EOFError`, raised by the client's `chan.close()` after a broken pipe; 4589 others
  passed, and the row passed three times in a row run alone. The base's full run in the same
  session, both eras, did not show it. First sighting on the bash row.
- 2026-11-02: a third loopback row, `test_timeout_stop.py`'s
  `test_a_command_that_dies_of_a_signal_leaves_its_jobs_running[ssh-sh]`, which runs only with
  `CLUSTER_MCP_TEST_EVERY_KIND=1`, failed once in a run of that module alone (macOS, modern era,
  branch `fix/timeout-process-cleanup`, its P4 gate), on a host at load 6 with two unrelated
  processes spinning. The captured log showed paramiko's `Socket exception: Bad file descriptor`;
  the assertion text was not kept. The row then passed six times alone and the module passed three
  times whole on the same tree.
- 2026-11-04: `test_ssh_exec.py`'s `test_a_reconnect_worker_that_cannot_start_frees_the_attempt`
  failed once in a local full-suite run (macOS, modern era, the `timeout-process-cleanup` squash
  before it landed), at load about 4.5 with another session's gates running; the assertion text was
  not kept. It passed five times alone, the modern era passed whole on the identical tree, and CI
  passed it in both eras. First sighting of that row; the branch does not touch it.
- 2026-11-05: `spec/ssh-half-open-link/` P2: `test_a_stalled_reconnect_is_abandoned_against_a_real_handshake`
  failed once in a local full-suite run (macOS, handshake era, load about 2.3 with another session's
  suites running) with "0 reconnect workers ran, not one", as on 2026-10-30; 4880 others passed. It
  passed three times run alone (7.1 s, 10.3 s, 3.1 s). The branch adds a liveness monitor to every
  published connection (threads `cluster-mcp-liveness` and `cluster-mcp-probe`, never counted as
  reconnect workers); the row's own window is unchanged.

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
