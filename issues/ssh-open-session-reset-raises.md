---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A connection reset while a call opens its channel escapes as a raw exception

## Problem

`SSHExecutor._exec` (`core/executor/ssh.py`) opens a fresh session channel for every command with
`transport.open_session(timeout=OPEN_TIMEOUT)`, before its `try`. Only the exec request and the end
of stdin after it are guarded: there an `SSHException`, `EOFError` or `OSError` on a connection that
is then lost becomes `CONNECTION_LOST_EXIT_CODE` with `launch.LOST_NOTE` (the command may have run),
and on a live one it is raised as a refusal. Nothing catches what `open_session` raises, so a
connection that `_ensure_connected` found active but that resets while the channel opens takes the
call down with Paramiko's own exception.

Observed on a developer Mac, 2026-11-02, while checking `timeout-process-cleanup`'s review fix
against the code it replaced (`386efa3`): the loopback test server dropped the shared connection,
as sshd does, after a `signal` request on a channel it had freed. The next `SSHExecutor.run` on the
same executor raised `ConnectionResetError: [Errno 54] Connection reset by peer` from Paramiko's
socket read, out of `run`, instead of returning a result. The trigger is that cycle's (and fixed
there); the escape is not.

**Pre-existing:** yes. The unguarded `open_session` is on `develop` at `c8843b2`. Whether the SFTP
paths (`write`, `put`, `get`, each opening `transport.open_sftp_client()`) escape the same way was
not checked.

## Why it was deferred

Found while building `timeout-process-cleanup`'s review remediation; it sits outside that cycle's
GOAL (a connection lost before the deadline, or before the command was sent, is a non-goal there).
The fix touches `core/executor/ssh.py`'s reconnect and result contract, a change of its own.

## Outcome / vision

A call whose connection is lost before its exec request has gone returns a result, as every other
lost connection does, and never raises. By analogy with `CONNECTION_LOST_EXIT_CODE`, which says
"the command may have run" because the request had gone: here the request never went, so the result
should say the command did not run, in the shape a failed reconnect already reports
(`NOT_STARTED_EXIT_CODE`, its stderr naming the host and the cause), unless a reconnect inside the
call's bound runs it after all. Which of the two, and where the guard sits, is left to shaping.

## Sketch of the acceptance criteria

- **R1** — WHEN the connection is lost while a call opens its channel, `SSHExecutor.run` SHALL
  return a `CommandResult` and SHALL NOT raise; the result SHALL say the command was not run, or
  carry the command's result if a reconnect within the call's bound ran it.
- **R2** — A test with no real host SHALL pin R1 by dropping the loopback server's connection
  between `_ensure_connected` and the channel's open.

## Notes

- Related: [`spec/ssh-half-open-link/`](../spec/ssh-half-open-link/) (a silent dead link, noticed
  within the reconnect bound since it landed on 2026-11-06; before it, `open_session` timed out
  after 30 s with Paramiko's error rather than the host's name),
  [`ssh-reconnect-stuck-step.md`](ssh-reconnect-stuck-step.md).
- Found by: `timeout-process-cleanup` review-cycle-1 remediation, 2026-11-02.
- 2026-11-05: `spec/ssh-half-open-link/` retries a channel or SFTP-session open that fails on a lost connection (`_gone`: the liveness monitor's verdict, or the transport inactive `SETTLE` after the failure), back into the reconnect within the call's deadline, so a reset while a channel opens now reconnects or reports the command not run; no row drops the link at that instant, so R2 above is still unpinned.
