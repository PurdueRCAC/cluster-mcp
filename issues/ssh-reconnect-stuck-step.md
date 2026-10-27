---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A reconnect stuck in DNS or the SSH agent blocks fresh reconnects until it returns

## Problem

`ssh-reconnect-loop` bounds every call's wait on a lost connection and keeps at most one connect
attempt in flight (its R7). When the last waiting call leaves, it closes the attempt's transport,
which ends key exchange, authentication or a jump host's channel within about 0.1 s. Inside a DNS
lookup, a `Match exec` command or the TCP connect there is no transport yet, so nothing to close: the
worker runs until that step returns (for the TCP connect, the connect bound), and its late success
is published. An SSH-agent query comes during authentication, so its transport exists and the abort
closes it, but the worker stays blocked reading the agent until it answers; the attempt is aborted,
so that late outcome, success or failure, is discarded. Calls that arrive meanwhile join the stuck
attempt, so while it lasts each fails at its own bound even if the host has come back. Once the step
returns, the slot clears and the next call tries again.

- 2026-10-26: corrected. As first filed, this said an SSH-agent query has nothing to close and that
  its late success is published; an agent that never answers showed the attempt has a transport,
  the abort closes it, and its eventual outcome is discarded. The stuck slot it describes is
  unchanged.

## Why it was deferred

The cost of R7, accepted at that cycle's plan gate (PLAN §5 risk 3): without a single attempt in
flight, stuck workers pile up, one per call. Ending a stuck DNS or agent step needs a resolver or
agent client with its own deadline, or a separate process per attempt, beyond that cycle's appetite.

**Pre-existing:** no; it replaces an unbounded hang with this bounded one.

## Outcome / vision

A reconnect stuck in a step the executor cannot interrupt no longer delays a fresh attempt once the
host is reachable again, and never leaves more than a bounded number of stuck workers.

## Sketch of the acceptance criteria

- **R1** — WHEN a connect attempt is stuck in a step that cannot be closed AND the host is
  reachable, a new call SHALL be able to connect within its own bound.
- **R2** — The number of stuck connect workers SHALL stay bounded by a stated constant.

## Notes

- Related: `spec/ssh-reconnect-loop/` (PLAN §5 risk 3, R7); `issues/ssh-half-open-link.md`.
- Found by: `ssh-reconnect-loop` plan, 2026-10-23; filed at its P3 ledger, 2026-10-26.
