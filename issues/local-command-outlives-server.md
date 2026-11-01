---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A local command in flight can outlive the server that launched it

## Problem

In `local` mode every command is launched in a session of its own (`start_new_session=True`,
`core/executor/launch.py`, `run_process`), so that its timeout can signal the whole process group: at
the deadline `run_process` sends the group SIGTERM, reads for `GRACE` (1 s), and, unless the output
has ended by then, sends SIGKILL and reads for `GRACE` again. Only the call that launched a group
ever signals it, from the thread that runs that call. Two ways of ending the server leave a group
running:

- **The server is killed.** When the server process itself is killed while a command runs (a client
  that gives up and sends SIGTERM, say), no thread is left to signal the group, and the command runs
  on to its own end. Observed by `capability-probe`'s plan-time adversarial review: a `local` server
  started with a login profile that hangs (`sleep 61`) was sent SIGTERM 3 s into its startup probe.
  It exited -15, and the probe's process group was still alive a second later. A tool call in flight
  behaves the same way.
- **The server exits normally between an abandoned call's SIGTERM and its SIGKILL.** The startup
  probe (`core/probes.py`) runs its lookup on a daemon thread, which startup abandons at the probe's
  deadline, failing open. That thread's executor call reaches its own deadline at about the same
  moment and sends the group SIGTERM. When the client closes stdin within the next `GRACE`, the
  server's stdio loop ends, the interpreter exits, and the daemon thread dies with it before it sends
  SIGKILL. A group that ignores SIGTERM (a login profile that runs `trap '' TERM` and then hangs; what
  the shell starts inherits the ignored signal) runs on, its login shell re-parented to init. Found by
  `capability-probe`'s review, cycle 1 (`trap '' TERM` then a hang: the server failed open and exited
  0 at about 10.9 s, and the probe's login shell and its child were still running), and diagnosed in
  cycle 2: a client that held the server 2.5 s past its first answer left nothing behind, since the
  worker's SIGKILL had landed.

Whether a tool call still running when the server exits normally is waited for, signalled or
abandoned has not been measured.

**Pre-existing:** yes, for every `local` tool call when the server is killed. `capability-probe` adds
the startup probe, whose command normally ends in milliseconds (a `type -P` lookup): only a profile
that hangs keeps it alive past a kill, and only one that also ignores SIGTERM outlives a normal exit.

## Why it was deferred

No R-ID of `capability-probe` covers what happens when the server exits with a command in flight, and
the fix (reaping the process groups the server started when it exits: from a signal handler, an
`atexit` hook or the end of `run()`) touches the launcher, a high-blast-radius path, for every
command, not only the probe.

## Outcome / vision

When the server exits for any reason, no command it launched in `local` mode keeps running.

## Sketch of the acceptance criteria

- **R1** — WHEN the server process exits, normally (stdin closed, its transport stopped) or on
  SIGTERM or SIGINT, while a process group it started in `local` mode is still running, the startup
  probe's and an in-flight tool call's alike, the server SHALL end that group (SIGTERM, then SIGKILL
  after `GRACE`) before the interpreter exits, whether or not the call's own timeout has begun to
  signal it.

## Notes

- Related: [`issues/timeout-process-cleanup.md`](timeout-process-cleanup.md) (a timed-out command
  that keeps running); `spec/capability-probe/` (PLAN §5).
- Found by: `capability-probe` plan step, adversarial review, 2026-11-01.
- 2026-11-01: `capability-probe` review cycle 1 found the same leak on a *normal* exit. A `local`
  probe whose login profile ignores SIGTERM (`trap '' TERM`) and then hangs outlives a server that
  failed open at the bound and exited 0: the probe's login shell and its child keep running in their
  own process group (`start_new_session=True`). The executor's timeout sends SIGTERM and, after
  `GRACE`, SIGKILL; the probe's worker, a daemon thread abandoned at the deadline, is cut off by the
  interpreter's exit within that grace, before its SIGKILL (Problem, second case). The Outcome above
  ("exits for any reason") covers it, and R1 names the normal exit.
