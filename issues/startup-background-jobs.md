---
status: accepted-behaviour
kind: fix
appetite: small
lane: public
---

# Over SSH, a login rc file's background job can write into a result

## Problem

Since `safe-execution`, every command runs in a login bash, and nothing the login initialisation
prints reaches a result: the launch parks the command's streams while startup files run, and each
program prints a per-call sentinel that the backend cuts at (`AGENTS.md` § Invariants §3). One case
remains outside what the server separates as it launches today. (A second, a startup file's background
process holding the call open, was fixed by the end records on 2026-10-22 and is retired.)

- Over SSH, a background job started by the remote login shell's own rc file (`.zshenv`, `.cshrc`, a
  `.bashrc` that sshd sources), which runs before the bootstrap can park anything, can still write
  into the channel after the sentinel and so into the result.
  - 2026-10-18: still so, and now the one documented exception to the separation: `AGENTS.md` §3,
    the README, the `run_command` description and the `Executor` docstring state it, and
    `tests/test_ssh_exec.py` pins both that it still happens and that every one of those texts says so.
  - 2026-10-22: still so for what such a job writes before the command's end record; what it writes
    after the record is no longer read.

A `run_command` script also runs in a fresh non-login bash, so a profile's unexported shell
variables are not visible to it (exported variables and functions are).

## Ruling

**accepted-behaviour, 2026-11-12.** The SSH rc-file case is the documented behaviour for now:
`AGENTS.md` §3, the README, the `run_command` description, the `Executor` docstring and the row in
`tests/test_ssh_exec.py` that pins it stay as they are. The first case above, a startup file's job
holding the call, is retired: the end records fixed it on 2026-10-22.

The later fix is its own seed, ordered after 0.3.0:
[`issues/startup-output-nonce-tagging.md`](startup-output-nonce-tagging.md), which tags each line of
the command's output with the per-call nonce. A PTY is ruled out: it merges the streams, and the rc
file's job still writes to the same terminal. A session the server owns is not taken up here; if
per-call login latency turns out to matter, that is a separate performance seed.

## Notes

- Related: `spec/safe-execution/` (PLAN §2.2a, risk 5, focused review finding 6).
- Found by: `safe-execution` focused review of the startup separation, filed at P2 (2026-10-17).
