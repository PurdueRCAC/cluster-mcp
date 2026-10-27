---
status: unshaped
kind: test
appetite: small
lane: public
---

# Nothing pins that a reconnect's abort and release reach every ProxyJump hop

## Problem

`SSHExecutor` walks a connection's ProxyJump chain (`_links` in `executor/ssh.py`) so that an
abandoned reconnect attempt closes every hop's transport (`_abort`) and a failed one releases every
hop's client (`_release`). Its docstring says an abort ends "a gateway's channel open within about
0.1 s". The code does this, but no test reaches a gateway: the suite's fake connection always has
`gateway = None`, and the in-process SSH server serves one hop.

Reproduced by the `ssh-reconnect-loop` review (cycle 3, 2026-10-27): with `_links` cut to the first
link (`conn = getattr(conn, 'gateway', None)` → `conn = None`), `tests/test_ssh_exec.py`,
`tests/test_startup.py` and `tests/test_executors.py` still pass (232 passed). The call bound still
holds under that mutant, since the call's own deadline enforces it; what would go unnoticed is a hop
left running after its attempt was abandoned.

## Why it was deferred

Found by `ssh-reconnect-loop`'s final review. No R-ID of that cycle asks for hop cleanup, and the
behaviour is correct as written; the gap is a missing pin, filed rather than grown into the cycle.

**Pre-existing:** no. The chain walk was added by `ssh-reconnect-loop`.

## Outcome / vision

A change that stops the abort or the release short of the last hop fails the suite.

## Sketch of the acceptance criteria

- **R1** — WHEN a reconnect attempt through a ProxyJump chain is abandoned, the executor SHALL close
  every hop's transport made so far, and the suite SHALL pin it with a fake chain of at least two
  hops.
- **R2** — WHEN such an attempt fails, the executor SHALL close every hop's client, pinned the same
  way.
- **R3** — The mutant that cuts the chain walk to the first link SHALL be killed, in both protocol
  eras.

## Notes

- Related: `spec/ssh-reconnect-loop/` (REVIEW.md cycle 3); `issues/ssh-half-open-link.md`.
- Found by: `ssh-reconnect-loop` review, cycle 3, 2026-10-27; filed by the foreman.
