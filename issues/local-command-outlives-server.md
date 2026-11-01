---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A local command in flight outlives a server that is killed

## Problem

In `local` mode every command is launched in a session of its own (`start_new_session=True`,
`core/executor/launch.py`, `run_process`), so that its timeout can signal the whole process group. Only
the call that launched it ever signals that group. When the server process itself is killed while a
command runs (a client that gives up and sends SIGTERM, say), no thread is left to do so, and the
command's group runs on to its own end.

Observed by `capability-probe`'s plan-time adversarial review: a `local` server started with a login
profile that hangs (`sleep 61`) was sent SIGTERM 3 s into its startup probe. It exited -15, and the
probe's process group was still alive a second later. A tool call in flight behaves the same way.

**Pre-existing:** yes, for every `local` tool call. `capability-probe` adds one instance on the startup
path, where the probe's own command normally ends in milliseconds (a `type -P` lookup) and only a
profile that hangs keeps it alive.

## Why it was deferred

No R-ID of `capability-probe` covers what happens when the server is killed, and the fix (reaping
in-flight process groups at exit, from a signal handler or `atexit`) touches the launcher, a
high-blast-radius path, for every command, not only the probe.

## Outcome / vision

When the server exits for any reason, no command it launched in `local` mode keeps running.

## Sketch of the acceptance criteria

- **R1** — WHEN the server process receives SIGTERM or SIGINT while a `local` command runs, the
  command's process group SHALL be signalled before the server exits.

## Notes

- Related: [`issues/timeout-process-cleanup.md`](timeout-process-cleanup.md) (a timed-out command
  that keeps running); `spec/capability-probe/` (PLAN §5).
- Found by: `capability-probe` plan step, adversarial review, 2026-11-01.
