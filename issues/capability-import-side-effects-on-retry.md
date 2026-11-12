---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A capability whose import registers into another library's state can't be retried

## Problem

`capability-reload-after-failure` makes a load that fails forget the modules it imported, so a
retry in the same process imports them again and they register again, as a first load in a fresh
process would (`packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`, `load()`'s failure
handler; `AGENTS.md` § Invariants §7). Running a capability's modules a second time is safe only
when its import can be repeated in one process. A module that, at import, registers into another
library's process-wide state that refuses a duplicate (a metrics collector's default registry
keyed by metric name is the common case) fails the second run. The retry then refuses a capability
that loaded cleanly the first time, naming it.

Evidence, from that cycle's adversarial plan review (prototype of the fix, planted capabilities): a
module the caller imported first holds a set of names and refuses a duplicate; the clean
capability `aaa-good`'s tools module registers one name at import; a failing `zzz-broken` sorts
after it.

- First load: `cannot load capability zzz-broken: RuntimeError: planted failure`.
- Retry: `cannot load capability aaa-good: ValueError: Duplicated timeseries in CollectorRegistry: {'a_echo_calls'}`.
- Retry with `zzz-broken` removed: the same refusal of `aaa-good`.

**Pre-existing:** yes, in effect. Before that fix a retry registered nothing for the clean
capability and refused it for a listing violation; the fix removes that cause and leaves this one.
The command line never retries: a load failure stops startup with exit 5.

## Why it was deferred

Ruled at that cycle's plan sign-off (2026-11-12): its R1 and R2 hold for capabilities whose import
can be repeated in one process, and §7 states that as a requirement on capability authors. The
case that needs more was recorded here rather than widening that cycle. Its GOAL's non-goals leave
the state a capability's import sets in other modules alone.

## Outcome / vision

A retry after a failed load behaves as a first load in a fresh process would, even for a capability
whose import has side effects in other libraries that refuse to see them twice; or the project
rules that such a capability is malformed and says how it is refused.

## Sketch of the acceptance criteria

- **R1** — WHEN a load in the same process follows a failed one, and a capability that loaded
  cleanly in the first load registers into another library's duplicate-refusing state at import,
  the load SHALL NOT refuse that capability for the duplicate.
- **R2** — The refusal of a capability that is still broken SHALL stay the one a first load in a
  fresh process raises.

## Notes

- The alternative the plan weighed: replay instead of re-import. On a failure, keep the cut
  registrations of the modules that stay imported, and re-append them on a retry whose import is a
  no-op. It needs per-entry state that outlives a load, and it can't attribute a non-tool entry, or
  a tool whose module the import system dropped, to a module
  (`spec/capability-reload-after-failure/research/01-load-module-cache.md` §7, PLAN § 3 deviation
  row 3).
- The same class covers a library a capability first imports during the failed load: the retry
  imports it again, and a library that refuses a second import in one process (a warning turned
  into an error under `-W error`, say) would fail the retry, naming the capability. The plan's
  research reproduced no such library (PLAN § 5).
- The class has one more path: when an entry the failed load registered can't be traced to a module
  it forgets (`_accounted` in `core/capabilities.py`), every module new since the load began is
  forgotten, a library's own lazy import too, so the retry runs that import again; a library whose
  submodule can't be imported twice in one process then fails the retry, naming a capability
  (review cycle 1 remediation, 2026-11-12, ruled to stand: the forget favours R1).
- Related: `spec/capability-reload-after-failure/` (PLAN § 4a F2, § 5 Q1);
  `issues/capability-reload-after-interrupt.md`; `AGENTS.md` § Invariants §7.
- Found by: `capability-reload-after-failure` plan, adversarial review, 2026-11-12.
