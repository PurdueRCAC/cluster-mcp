---
status: unshaped
kind: fix
appetite: small
lane: public
---

# An interrupt that lands inside a failed load's cleanup may leave a retry registering nothing

## Problem

A `KeyboardInterrupt` that cuts a capability load short is not a refusal, and the load cleans up
after it as it does after a failure. `load()`'s handler
(`packages/cluster-mcp/src/cluster_mcp/core/capabilities.py:511-522`) forgets the modules the load
imported (`_unimport`) and then, in an inner `finally`, cuts `TOOL_REGISTRY` back to what it held
when the load began, and the interrupt is raised as it is (AGENTS.md § Invariants §7). A library
caller that catches the interrupt and loads again in the same process therefore gets a first load:
with the interrupting capability removed, a capability that loaded before it comes back with its
tools, each registered once. `test_a_load_retried_after_an_interrupt_is_a_first_load` pins that.

What is still open is an interrupt that lands inside that cleanup, or inside the import system's:

- **Inside the handler.** A second interrupt raised while `_unimport` runs (`:269`) stops it partway:
  the registry is still cut, but some of the modules the load imported stay imported. A retry then
  finds them imported and runs none of them again, so a capability that loaded cleanly registers
  nothing and is refused because its instructions list tools it no longer registers. The same holds
  for an interrupt while `_roots` or `_accounted` runs, before any module is forgotten.
- **Inside the import system's cleanup.** An interrupt that lands while the import system removes a
  module whose import raised can leave that module in `sys.modules`. Whether a retry then meets the
  defect depends on where it lands.

Both are read from the code, not observed: each needs a second signal timed inside the cleanup.
**Pre-existing:** yes, since the entry-point loader (`capability-extras`); before
`capability-reload-after-failure` every interrupted load left its modules imported. The command line
can't reach it, because an interrupt stops the server (`exit_status.keyboard_interrupt`) and nothing
loads twice.

## Why it was deferred

`capability-reload-after-failure` was scoped to failed loads at its GOAL sign-off (2026-11-12
ruling: failures only), and the interrupted case was recorded here. Its fix turned out to cover an
interrupt that cuts the load short, which its review cycle 1 confirmed and its remediation pinned.
The windows above are what it does not cover.

## Outcome / vision

A load that an interrupt cuts short, wherever the interrupt lands, leaves the process in a state
where a retry behaves as a first load in a fresh process would.

## Sketch of the acceptance criteria

- **R1** — WHEN an interrupt lands while a failed or interrupted load forgets what it imported, and a
  later load in the same process is given capabilities that all load cleanly, the later load SHALL
  return each with the tools a load in a fresh process returns it with, each registered exactly once.
- **R2** — The interrupt itself SHALL still propagate as it is, never as a refusal, and the registry
  SHALL still be cut back.

## Notes

- Related: `spec/capability-reload-after-failure/` (PLAN Notes, the interrupted load; REVIEW cycle 1,
  F2); `AGENTS.md` § Invariants §7.
- A test has to raise the second interrupt from inside the cleanup without running capability code
  where the loader refuses to; how is the shaping's call.
- Found by: `capability-reload-after-failure` shaping, 2026-11-12; restated by its review cycle 1
  remediation, 2026-11-12.
