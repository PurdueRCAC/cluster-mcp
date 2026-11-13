# Research digest — capability-reload-after-failure

Two briefs: [`01-load-module-cache.md`](01-load-module-cache.md) (import semantics, every refusal
family under candidate evictions, the members' imports, the interrupt, the sibling's lines) and
[`02-tests-and-mutants.md`](02-tests-and-mutants.md) (planting helpers, failing kinds, the mutation
runner, the docs that describe today's behaviour, timings). Line numbers are at the GOAL commit
`aa1688a`.

## Decisions

1. **Re-import, don't replay.** A failed load forgets the modules it imported, so a retry imports
   them again and they register again (01 §7: replay needs state that outlives a load and has
   double-registration and ordering cases).
2. **What is forgotten: every module new since the load's snapshot, except one below a regular
   package that was already imported then.** This resolves the briefs' three variants:
   - The planner's candidate (roots at `ep.module`, `capability.tools` and named strays) and P
     (roots widened to the top-most new package) both let a retry *load* a capability the first
     load refused when the offending registration came from a module outside the roots
     (01 table rows 4-7). That breaks R1.
   - H (every new module) passes every probe, but also forgets a library's own lazily imported
     submodule (a submodule of FastMCP, pydantic or the standard library first imported during the
     load). Its parent package keeps an attribute for the forgotten module, so `from parent import
     child` would hand out the old module while the next import creates a new one (01 §1).
   - The chosen rule, H′, keeps exactly those: a new module with an ancestor that was an imported
     *regular* package at the snapshot is that library's, not a capability's. A namespace
     package (`cluster_mcp`, which every member shares, and which has no `__file__`) does not
     protect its descendants, and drops its attribute for each forgotten child. A planted
     prototype of H′ (detached worktree at `aa1688a`) reproduced the first load's message on retry
     in all nine of 01's scenarios, loaded the healthy capability with its one tool once the broken
     one was removed, and did the same beside both real members (members re-imported, 18 tools,
     each once, `cluster_mcp.rcac` rebound).
3. **The snapshot is taken after `_scratch()`.** `_scratch()` constructs a FastMCP server, whose only
   new module in a fresh process is a FastMCP submodule (01 §6), which H′ keeps anyway. Taking the
   snapshot after it keeps the rule independent of what a future FastMCP imports lazily. The line
   sits between `:319` and `:320` and moves one mutation anchor (02 §3).
4. **The cut-back moves into a `finally`, after the refusal is built.** `_cause(exc)` runs a
   capability's `__str__`. Built after the cut-back and the forgetting, a lazy import there would
   re-register an evicted module's tools after the failed load (01 §2). In the `finally`, the
   registry is cut and the modules forgotten whatever `_cause` raises, `KeyboardInterrupt` included.
5. **No `sys.modules` iteration in Python.** `set(sys.modules) - known` is taken in C. Entries are
   removed with `pop(name, None)`, so another thread's import can't turn the handler's work into a
   `RuntimeError` that replaces the refusal (01 §1).
6. **The interrupt is covered as a by-product.** The same handler runs for a `KeyboardInterrupt`.
   The prototype's first load re-raised the interrupt with the registry cut back. Its retry did the
   same, and with the interrupting capability removed the healthy one loaded with its tool. The base
   code refused the healthy one. The uncovered windows (an interrupt inside the handler itself, or
   inside the import system's own cleanup of a failing module) stay with
   `issues/capability-reload-after-interrupt.md`. No R-ID is widened.
7. **Tests.** R5's test reuses `pair()`'s `planted-a-first` and the `unloadable()` /
   `rejected_package()` kinds, and adds two indirect plants from 01 (a stray reached through an
   intermediate module, and a non-tool appended by a helper the entry point imports). Members
   imported by `conftest` sit in the snapshot and are never forgotten (02 §1). The spec-id rule
   (`test_no_spec_ids_in_the_package_or_the_suite`) means the kill's `why` states the contract in
   words, as one prefix shared by the R1 and R2 assertions (02 §3).
8. **Anchors that move:** `capability-scratch-per-capability`, `capability-refusal-keeps-registry`,
   `capability-other-exception-keeps-registry` and `capability-load-failure-passes-re-raises`. All
   four went red in the prototype, and every other `capability` anchor applied. They are re-planted
   in the fix's commit (02 §3).

## Amended after the adversarial review (PLAN § 4a)

- **Capability roots.** H′ alone kept a capability's new modules when the caller had imported the
  capability's own regular package first (`import cluster_mcp.rcac`), and the defect came back. The
  keep rule now applies only outside each capability's root, the outermost regular package holding
  its entry point's module or its tools module. The prototype then passed the reviewer's
  pre-import probe and the nine scenarios.
- **Exact types.** `_unimport` acts only on `str` keys and objects exactly `ModuleType`, reading and
  popping through `vars()`, and the registry cut runs in the innermost `finally`. A replaced or
  subclassed parent module no longer raises over the refusal or runs code after the cut.
- **Re-running a module is a reading (PLAN Q1).** A module-level registration in another library's
  duplicate-refusing state fails the second run; that goes to the sign-off.

## Contradictions resolved

- 01 recommends H or P, and 02 warns that evicting member modules would make them register twice. The
  members were already imported when the load began, so every variant keeps them. H′ is H minus
  library submodules. It keeps 01's coverage and avoids H's stale-parent hazard.
