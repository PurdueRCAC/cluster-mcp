---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A capability load retried after an interrupt may register nothing and blame the wrong distribution

## Problem

A `KeyboardInterrupt` that cuts a capability load short is not a refusal. `load()`
(`packages/cluster-mcp/src/cluster_mcp/core/capabilities.py:383-386`) cuts `TOOL_REGISTRY` back to
what it held when the load began and re-raises the interrupt as it is (AGENTS.md § Invariants §7).
That cut-back is the same one a failed load makes, and it leaves the tools modules the load had
already imported still imported. A library caller that catches the interrupt and loads again in the
same process can therefore meet the defect `capability-reload-after-failure` fixes for a failed
load. A capability that loaded cleanly before the interrupt registers nothing on the retry, and the
load refuses it because its instructions list tools it no longer registers.

This was read from the code, not observed. **Pre-existing:** yes, since the entry-point loader
(`capability-extras`). The command line can't reach it, because an interrupt stops the server
(`exit_status.keyboard_interrupt`) and nothing loads twice.

## Why it was deferred

`capability-reload-after-failure` was scoped to failed loads at its GOAL sign-off (2026-11-12
ruling: failures only). The interrupted case was recorded here rather than widening that cycle.

## Outcome / vision

An interrupted load leaves the process in a state where a retry behaves as a first load in a fresh
process would, just as a failed load does once `capability-reload-after-failure` lands.

## Sketch of the acceptance criteria

- **R1** — WHEN a load is cut short by a `KeyboardInterrupt` and a later load in the same process is
  given capabilities that all load cleanly, the later load SHALL return each with the tools a load
  in a fresh process returns it with, each registered exactly once.
- **R2** — IF a later load after an interrupted one meets a capability that fails, THEN its refusal
  SHALL be the one a first load in a fresh process would raise.
- **R3** — The interrupt itself SHALL still propagate as it is, never as a refusal.

## Notes

- Related: `issues/capability-reload-after-failure.md` and `spec/capability-reload-after-failure/`
  (the failed-load case, whose fix may already cover this one; confirm before shaping);
  `AGENTS.md` § Invariants §7.
- Found by: `capability-reload-after-failure` shaping, 2026-11-12.
