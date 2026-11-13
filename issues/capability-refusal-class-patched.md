---
status: unshaped
kind: test
appetite: small
lane: public
---

# Nothing pins that the failed load's refusal is read past a patched `CapabilityLoadError`

## Problem

A failed capability load keeps its refusal as plain text for the loads after it: `_failure` in
`packages/cluster-mcp/src/cluster_mcp/core/capabilities.py` reads the distribution through `vars()`
and the message from `args[0]`, so no capability code runs to read it (AGENTS.md § Invariants §7).
A capability's import can also patch the core's own class, say a `distribution` property or a
`__str__` set on `CapabilityLoadError` itself. A read through the attribute (`refusal.distribution`)
or through `str(refusal)` would then run that code while the failure is kept, and nothing in the
suite tells the two reads apart: both hand mutants survived the `capability-reload-after-failure`
review-cycle-2 remediation's sweep (`refusal.distribution` for the `vars()` read, `str(refusal)` for
`args[0]`). With the class unpatched they are equivalent.

**Pre-existing:** no; `_failure` came with that remediation, and reads correctly. This is a missing
pin at a deeper layer of a class already pinned (`test_a_load_after_a_capabilitys_own_refusal_runs_none_of_its_code`
pins a capability's own refusal object). Only a capability's own code, acting on purpose, reaches it,
and capability code runs at import anyway.

## Why it was deferred

Graded per the review method: a hand mutant that pins a deeper layer of an already pinned class is
seeded. A pin has to patch a core class for one test and restore it, which the cycle did not take on.

## Outcome / vision

A capability that patches `CapabilityLoadError` runs none of that code while a failed load's refusal
is kept or a later load is refused.

## Sketch of the acceptance criteria

- **R1** — A test SHALL plant a capability whose import sets a `distribution` property and a `__str__`
  on `CapabilityLoadError`, recording each run, and whose tools module then raises; it SHALL assert
  that neither runs as the load fails or as a later load is refused, and SHALL restore the class.
- **R2** — `tests/mutants.py` cases SHALL plant `refusal.distribution` and `str(refusal)` in
  `_failure`, each killed by R1's test.

## Notes

- Related: `spec/capability-reload-after-failure/` (TECH P1, review cycle 2 amendment: the sweep);
  `AGENTS.md` § Invariants §7.
- Found by: `capability-reload-after-failure` review cycle 2 remediation sweep, 2026-11-12.
