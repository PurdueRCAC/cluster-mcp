# Research 01 — what a login node does at a timeout today (Q1)

Measured 2026-11-01, once, by the foreman, under the maintainer's approval of 2026-10-29 (GOAL Q1).
The setting: a RHEL 8 login node of the test cluster, OpenSSH 8.0p1 (the distribution's server
build), reached through a released build of the server in `ssh` mode, by its `run_command` tool
with `timeout=5`. Every process ran under the effort's scratch directory and was removed by literal
pid and path afterwards; nothing is left on the host. The planner did not run anything on a host:
this brief records the foreman's findings.

## Trials

| Trial | Command (5 s timeout) | Result | On the host afterwards |
|---|---|---|---|
| A | a script that starts a child (`bash -c`), which starts a grandchild (`sleep 311`); the script itself then runs `sleep 300` | `TIMEOUT_EXIT_CODE`, empty output | top, child and grandchild all gone 8 s after the result |
| B | the same tree under `trap '' TERM` at the top, inherited by every process (TERM, INT and QUIT ignored) | `TIMEOUT_EXIT_CODE` | top, child, grandchild and the top's `sleep 300` all alive 18 s later (and at 90 s), re-parented to init, still in the session's process group (pgid = sid = the ended login shell). No KILL ever came |
| C | a script trapping TERM, HUP, INT and PIPE, recording which arrives first and when | `TIMEOUT_EXIT_CODE`, stderr `Terminated` | TERM arrived 4.75 s after the script started, at the call's deadline (login time accounts for the rest); no HUP, INT or PIPE before it |
| D | the C recorder started as `(./sig.sh &)` (its parent subshell exits at once, so it is not the command's child), then `sleep 300` | `TIMEOUT_EXIT_CODE`, stderr `Terminated` | the recorder got TERM at the deadline too |

## What it settles

1. **TERM reaches the command's whole process group at the deadline**, not only its top process
   (D). Which component sends it is established from the code in
   [`02-term-delivery.md`](02-term-delivery.md): sshd, acting on the RFC 4254 `signal` request.
2. **Nothing follows TERM.** A process that ignores it, and whatever inherits the ignore, runs on
   with no bound (B). This is R1's gap, and the only one over `ssh` on this OpenSSH: a tree that
   does not ignore TERM is already stopped (A).
3. Nothing else is sent at the deadline or when the channel closes (C): no HUP, INT or PIPE.

## Not measured

- A `delegate` server without root: it needs a service account with a `sudo` rule on a login node,
  outside the effort's dogfood class. R3 rests on the code and the host-free tests (Q1, Q3).
- A process that left the group (`setsid`): out of scope (Q4).
- An OpenSSH that ignores the `signal` request (older than the one measured, or a session with a
  forced command or a subsystem, which sshd refuses to signal): a limit the docs state (PLAN §5).

## What the host-free tests must reproduce

The in-process SSH server (`tests/ssh_server.py`) has to behave as trials A–D show: one `signal`
request delivers its signal to the session's process group, nothing else is sent, and a
TERM-ignoring tree survives without a fix. Its fidelity is in [`04-test-fidelity.md`](04-test-fidelity.md).
