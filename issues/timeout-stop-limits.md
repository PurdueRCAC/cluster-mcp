---
status: unshaped
kind: fix
appetite: small
lane: public
---

# What a timeout still cannot stop

## Problem

`timeout-process-cleanup` stops a timed-out command's processes in every mode with a watchdog the
launch program starts after the login initialisation: when the program bash dies after arming it
and before releasing it (as it does at the deadline's TERM), the watchdog waits `GRACE` and sends
KILL to the process group, never TERM; it waits on its pipe through `/bin/cat`, never a shell
builtin, so it acts on the program's death alone, never on time; and where the program runs on the
server's host it reads the server's clock and never starts a command past its deadline
(`AGENTS.md` § Invariants §2, §3). Five cases stay outside it. Each is shown in every mode by
`tests/test_timeout_stop.py`'s `test_a_recorded_limit` rows (run with `CLUSTER_MCP_TEST_LIMITS=1`),
as written here:

- **A login initialisation that hangs**, before the program and its watchdog exist. The result is
  already an empty timeout (`tests/test_launch.py`, `test_a_profile_that_hangs_is_a_timeout`), but
  what the startup file started may run on:
  - in `local` and under a root `delegate` server, the server's TERM reaches the group and its KILL
    follows while anything still holds the call's output, so only a process the startup file
    started that ignores TERM and holds no stream of the call runs on;
  - over `ssh`, sshd's TERM reaches the session's group and the KILL `signal` request follows while
    the channel is open, which stops a login shell that ignores TERM and holds the streams; but once
    the login shell has died of the TERM sshd refuses the KILL, so a process it started that ignores
    TERM runs on, whether it holds the streams or not;
  - under a non-root `delegate` server, `sudo` relays TERM to the login shell alone and KILL cannot
    be relayed, so whatever the startup file started runs on, ignoring TERM or not, and the login
    shell too if it ignores TERM.
- **An SSH server that does not act on the RFC 4254 `signal` request** (an OpenSSH older than the
  one the test cluster runs, a session with a forced command, which sshd refuses to signal, or
  another server). The program bash is never signalled at the deadline, so it never dies, and the
  watchdog never fires; the command runs on as before this fix. The measured OpenSSH 8.0p1 acts on
  the request (`spec/timeout-process-cleanup/research/01-login-node-measurement.md`).
- **A startup file that shadows the launch's builtins past what the prologue undoes.** The prologue
  turns the builtins the program runs back on and unsets the functions named after them in posix
  mode, where `unset` comes before a function of its name, and then the functions named like the
  absolute paths it runs; it cannot undo a readonly function, a function named `enable` beside a
  disabled `unset`, `enable -n enable`, or aliases on its own second line. Such a file can make the
  stop fail and can stop a command early, as it can already break the launch itself, and it only
  ever affects its own user's commands. With `unset` and `trap` turned off and a function named
  `enable` (`shadowed-stop`), the watchdog is not TERM-proof and dies of the deadline's TERM, so in
  `local`, under a root `delegate` server and over `ssh` a process that ignores TERM and holds no
  stream of the call runs on (under a non-root `delegate` server no TERM reaches the watchdog, and it
  KILLs); with a function named `/bin/cat` beside them (`shadowed-early`), the watchdog reads its
  arming line at once as the program's death and KILLs the group `GRACE` into the run, with or
  without a timeout.
- **A step of the server's wall clock during the login initialisation.** The program's deadline is
  on the wall clock (`time.time_ns()` when the program is rendered; the program reads `/bin/date
  +%s%N`, nanoseconds from GNU `date` and microseconds from macOS's), the server's own on the
  monotonic clock, so a step between the rendering and the check moves one against the other. A
  step forward refuses a command whose deadline has not come: it did not start (`-1002`), about
  `GRACE` into the call (`clock-forward`). A step back lets a command start past its deadline
  (`clock-back`, a startup file that ignores TERM delaying it): in `local` and under a root
  `delegate` server the server's KILL after the grace stops it, and under a non-root `delegate`
  server, whose relayed TERM went to the startup file, it runs on. Over `ssh` the program is given
  no deadline, so no step reaches it. The rows simulate the step by moving the deadline the program
  is given.
- **A process that has left the command's process group** (`setsid`, a daemon) is reached by no
  stop in any mode (`left-group`); it is a non-goal of `timeout-process-cleanup` (its GOAL's Q4),
  listed here because the same rows show it.

## Why it was deferred

Each is outside `timeout-process-cleanup`'s GOAL as ruled: the first concerns processes that are
not "the command's processes" when the deadline comes (the command has not started); the second
rests on the remote server, and R1 is graded on host-free tests of the measured behaviour (Q1); the
third was ruled a documented limit at the cycle's review bound (2026-11-04), its cheap cases closed;
the fourth was ruled a documented limit past the bound (2026-11-04: the program's clock is the wall
clock, which a host can step, and the server's is not); the fifth is the GOAL's Q4. **Pre-existing**
for the first two and the fifth (develop stopped none of them either); the third widens a
pre-existing one (such a file could already break the launch) to the stop; the fourth comes with the
deadline's check, which develop did not have (develop started every late command).

## Outcome / vision

A timed-out call stops everything it started on the host, whatever the startup files do and
whether or not the SSH server honours `signal`.

## Sketch of the acceptance criteria

- **R1** — WHEN a login initialisation is still running at the deadline, in any mode, it and what
  it started SHALL have exited within 2 × `GRACE`.
- **R2** — WHEN the SSH server ignores the `signal` request, a timed-out command SHALL still be
  stopped on the host within a stated bound (for instance by a remote fallback keyed on the
  channel's close).
- **R3** — WHEN a startup file shadows the launch's builtins, the stop SHALL neither fail nor end a
  command before its deadline (for instance by a watchdog that is a fixed program, not shell text).
- **R4** — WHEN the server's wall clock steps during a login initialisation, a command SHALL start
  exactly when its deadline on the server's monotonic clock has not passed (for instance a deadline
  the program measures from its own start, given the time already spent).

## Notes

- Related: `spec/timeout-process-cleanup/` (PLAN §5, research 03); `issues/startup-background-jobs.md`;
  `issues/local-command-outlives-server.md`; `AGENTS.md` § Invariants §3.
- Found by: `timeout-process-cleanup` planning research, 2026-11-01; the hanging startup file's
  cases over `ssh` and the measured rows by its review cycle 1, 2026-11-02; the shadowed builtins by
  its review cycle 2, 2026-11-04; the clock step by its review cycle 3, 2026-11-04.
