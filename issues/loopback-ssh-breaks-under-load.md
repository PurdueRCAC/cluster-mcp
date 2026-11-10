---
status: unshaped
kind: fix
appetite: small
lane: public
---

# Loopback SSH rows break under load, with no time bound missed

## Problem

Three loopback SSH rows have failed on a busy host, then passed alone and on a re-run of the same
tree. None of them checks a time bound: the link to the in-process test server
(`tests/ssh_server.py`, `LoopbackSSH`) broke while the row was using it. It is not known whether the
break is in the test server, in Paramiko, or in the executor's own handling of a reset link.

- 2026-10-29: `tests/test_ssh_exec.py::test_startup_output_is_separated[tcsh]` failed on CI (run
  40812003663, modern era, branch `fix/resource-reads-without-executor` at `344a3a3`) with
  `EOFError` from Paramiko's packet reader; 2214 others passed, and the re-run of the same commit
  passed 2215 in both eras. That branch changes no SSH code.
- 2026-11-01: the same row failed again on CI with the same `EOFError` (run 41375322079, handshake
  era, branch `ci/split-eras` at `3a87f35`, which changes only the workflow and `AGENTS.md`); the
  server side logged `Connection reset by peer`. 4573 others passed, and the re-run of the failed job
  passed.
- 2026-11-01: `test_startup_output_is_separated[bash]` failed once in a local full-suite run
  (macOS, modern era, branch `fix/timeout-process-cleanup` before its first build commit) with the
  same `EOFError`, raised by the client's `chan.close()` after a broken pipe; 4589 others passed,
  and the row passed three times in a row run alone. The base's full run in the same session, both
  eras, did not show it.
- 2026-11-02: `tests/test_timeout_stop.py::test_a_command_that_dies_of_a_signal_leaves_its_jobs_running[ssh-sh]`,
  which runs only with `CLUSTER_MCP_TEST_EVERY_KIND=1`, failed once in a run of that module alone
  (macOS, modern era, branch `fix/timeout-process-cleanup`, its P4 gate), on a host at load 6 with
  two unrelated processes spinning. The captured log showed Paramiko's `Socket exception: Bad file
  descriptor`; the assertion text was not kept. The row then passed six times alone and the module
  passed three times whole on the same tree.

Two of the four sightings are on hosted CI, where a red job is re-run; a row that breaks on load,
not on behaviour, teaches builders to re-run red gates. If the break is in the executor (an `EOFError`
escaping `chan.close()`, for instance), a user on a flaky link sees it too.

## Why it was deferred

Recorded first in the seed of `stalled-reconnect-test-timing` (retired; its account is `spec/stalled-reconnect-test-timing/`) as part of one load-sensitivity class.
Shaping that cycle on 2026-11-09 split it out: those rows miss wall-clock bounds, these break a
link, by a mechanism nobody has found, possibly outside the tests. The maintainer ruled it a `fix`
seed of its own.

**Pre-existing:** yes. The rows predate every branch they failed on, and none of those branches
changes the SSH code under them.

## Outcome / vision

Each row fails only when the behaviour it checks is wrong. Where the break is in the executor, a
reset or closed link during a command reads as the documented lost-connection result, never as a
raw exception; where it is in the test server, the server no longer drops a link under load.

## Sketch of the acceptance criteria

- **R1** — WHILE the host runs the suite under load, the startup-separation rows over SSH and the
  `ssh-*` signal-death row SHALL not fail with `EOFError` or a socket error from the loopback link.
- **R2** — IF the link to the host is reset while a command runs or its channel closes, THEN the
  call SHALL return the executor's lost-connection result rather than raise.
- **R3** — Each row SHALL still fail when the behaviour it checks breaks.

## Notes

- Related: `spec/stalled-reconnect-test-timing/` (landed on `develop` 2026-11-10; the wall-clock rows),
  `issues/ssh-open-session-reset-raises.md` (a reset while a call opens its channel raises).
- Sources: `tests/ssh_server.py` (`LoopbackSSH`), `tests/test_ssh_exec.py`
  (`test_startup_output_is_separated`), `tests/test_timeout_stop.py`,
  `packages/cluster-mcp/src/cluster_mcp/core/executor/ssh.py`.
- Found by: the final gate of `resource-reads-without-executor` and the gates of
  `timeout-process-cleanup`; split out at `stalled-reconnect-test-timing`'s GOAL gate, 2026-11-09.
