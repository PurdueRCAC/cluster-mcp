---
status: unshaped
kind: fix
appetite: big
lane: public
---

# Over SSH, a login rc file's background job can write into a result

## Problem

Over `ssh`, a background job started by the remote login shell's own rc file (`.zshenv`, `.cshrc`, a
`.bashrc` that sshd sources) runs before the bootstrap can park anything, so what it writes before
the command's end record reaches the result. It is accepted, documented behaviour since 2026-11-12
(`issues/startup-background-jobs.md`): `AGENTS.md` §3, the README, the `run_command` description and
the `Executor` docstring state it, and `tests/test_ssh_exec.py` pins it. This seed is the later fix.

## The fix sketched

The bootstrap tags each line of the command's output with the per-call nonce, and the backend keeps
only tagged lines, so nothing an rc file's job writes can pass for the command's output.

Its costs:
- about a third more bytes on the wire;
- an encoder running on the login node beside the command;
- output streamed line by line rather than as it arrives.

Open: whether a tagged line can be torn by a concurrent writer once it is longer than `PIPE_BUF`,
which would let a job's bytes land inside a tagged line.

Ruled out: a PTY, which merges the two streams while the rc file's job still writes to the same
terminal. Not taken up here: a session the server owns, which is a separate performance question if
per-call login latency turns out to matter.

## Sketch of the acceptance criteria

- **R1** — WHEN a remote login shell's rc file starts a job that writes while the command runs, none
  of that output SHALL appear in the result, in either stream.
- **R2** — A command's own output SHALL reach the result byte for byte, including lines longer than
  `PIPE_BUF` and output with no final newline.
- **R3** — The accepted-behaviour texts (`AGENTS.md` §3, the README, the `run_command` description,
  the `Executor` docstring) and the row pinning the exception SHALL change in the same commit.

## Notes

- Related: `issues/startup-background-jobs.md` (the accepted behaviour); `spec/safe-execution/`
  (PLAN §2.2a, risk 5).
- Ordered after 0.3.0 (2026-11-12).
