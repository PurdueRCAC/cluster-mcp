---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A capability load retried after an interrupt may register nothing and blame the wrong distribution

## Problem

A `KeyboardInterrupt` that cuts a capability load short is not a refusal. `_load()`'s handler
(`packages/cluster-mcp/src/cluster_mcp/core/capabilities.py:432-440`) cuts `TOOL_REGISTRY` back to
what it held when the load began and raises the interrupt as it is, and `load()` (`:315-336`) keeps
a refusal for the later loads only of a `CapabilityLoadError` (AGENTS.md § Invariants §7). The tools
modules the interrupted load imported stay imported. A library caller that catches the interrupt and
loads again in the same process therefore meets the defect `capability-reload-after-failure` closed
for a failed load: a capability that loaded cleanly before the interrupt registers nothing on the
retry, and the load refuses it because its instructions list tools it no longer registers. That
refusal names the healthy capability, and, being a failed load, it is then what every later load in
the process is refused for.

Observed with two planted distributions, `aaa-good` (loads) and `zzz-int` (its tools module raises
`KeyboardInterrupt`): the first load is interrupted; a retry with `aaa-good` alone reports
`cannot load capability aaa-good: its instructions list ['a_echo'], which it does not register`; and
the load after that is refused for it, with the instruction to restart. **Pre-existing:** yes, since the entry-point loader
(`capability-extras`). The command line can't reach it, because an interrupt stops the server
(`exit_status.keyboard_interrupt`) and nothing loads twice.

## Why it was deferred

`capability-reload-after-failure` was scoped to failed loads at its GOAL sign-off (2026-11-12
ruling: failures only), and the interrupted case was recorded here. That cycle settled on refusing
every load after a failed one, with no reload in the process; an interrupted load leaves no refusal
(`test_an_interrupted_load_leaves_no_refusal`).

## Outcome / vision

A retry after an interrupted load never names a capability that loaded cleanly: it is refused as a
load after a failed one is, naming the interrupted load and saying to restart the process, or it
behaves as a first load in a fresh process would.

## Sketch of the acceptance criteria

- **R1** — WHEN a load is cut short by a `KeyboardInterrupt`, a later load in the same process SHALL
  be refused, naming the distribution the interrupted load was at and saying to restart the
  process, and SHALL import, register and run nothing.
- **R2** — The interrupt itself SHALL still propagate as it is, never as a refusal, and the registry
  SHALL still be cut back.

## Notes

- Related: `spec/capability-reload-after-failure/` (PLAN Notes, the interrupted load; REVIEW cycle 1,
  F2); `AGENTS.md` § Invariants §7. The refusal `load()` already keeps for a failed load is the
  likely mechanism: R1 is the same rule widened to an interrupt.
- Found by: `capability-reload-after-failure` shaping, 2026-11-12; restated by its review cycle 1
  remediation and again by its review cycle 2 remediation, 2026-11-12.
