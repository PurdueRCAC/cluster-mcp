# PLAN — A capability load retried after a failure loads the healthy ones and names the broken one

> **Status:** Draft for review · **Last updated:** 2026-11-12
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Backing detail is in
> [`research/`](research/): `appetite: small`, `kind: fix`, but `core/capabilities.py` is on
> § Invariants' high-blast-radius list, so trigger 2 ran the fan-out. The tests and the mutation case
> are assertion deliverables, so trigger 3's adversarial review ran too (§ 4a).

## 1. Summary

A failed load already cuts `TOOL_REGISTRY` back. It will also forget the modules it imported, so
the next load imports them again and they register again, as they would in a fresh process. A
module is forgotten when it is new since a snapshot taken as the load began, unless it is a
library's own lazy import: a module below a regular package that was already imported then, and
not below any capability's own package. The change is local to `load()`: two lines before the loop,
the failure handler, and four small helpers. A new test plants a clean capability and a failing
one in four package layouts and seven failing kinds. It retries through `load()`, `installed()` and
`create_mcp_server()`, and asserts on messages, returned tools and registrations. A new mutation
case plants today's retry behaviour. One reading of R1 and R2 goes to the sign-off (§ 5, Q1).

## 2. Design

All code changes sit in `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`. Line numbers
are at the GOAL commit `aa1688a`.

**Helpers**, placed after `_below` (`:177-178`). None of them calls `getattr`, `delattr` or
`isinstance` on an object it did not create, so none runs a capability's code:

- `_file(module)`: the `__file__` in `vars(module)` when `type(module) is ModuleType`. Otherwise a
  marker meaning "not plainly a module". A regular package or plain module has a `str` there, and a
  namespace package (`cluster_mcp`) has `None`.
- `_root(name)`: the shortest dotted prefix of `name` whose `sys.modules` entry is plainly a module
  with a `__file__`. For example, `cluster_mcp.rcac.capability` gives `cluster_mcp.rcac`, because
  `cluster_mcp` is a namespace, and `acme.caps.x` gives `acme`. It returns `name` itself when no
  such prefix exists.
- `_roots(ordered, loaded, capability)`: the `_root` of three kinds of name. The first is the module
  part of each `ordered` entry's value, when that value is exactly a `str`. The second is the `tools`
  of each loaded capability. The third is the failing capability's `tools`, when it got past
  `_checked`. All three are exactly `str` by then. It never reads `ep.module`, because that property
  raises on a malformed value, and `ep.load()` reports that today.
- `_unimport(known, roots)`: forgets every module imported since the snapshot `known`.
  - It computes `set(sys.modules) - known` in C. Python never iterates `sys.modules`, where another
    thread's import would raise `RuntimeError` mid-iteration
    ([`research/01`](research/01-load-module-cache.md) §1).
  - It skips any key that is not exactly a `str`.
  - It **keeps** a new module when two things hold. One of its proper ancestors is in `known`, and
    that ancestor is a regular package or is not plainly a module ("when unsure, touch nothing").
    And the module is not `_below` any of `roots`. Such a module is a library's lazy import: a
    FastMCP, pydantic or standard-library submodule, for which the parent keeps an attribute.
  - It **forgets** every other new module with `sys.modules.pop(name, None)`.
  - When the forgotten module's parent is plainly a module, that parent's `vars()` drops the
    attribute that holds it under the leaf name, if the attribute is that same module object. The
    namespace `cluster_mcp` is one such parent. A kept regular package below a root, such as
    `cluster_mcp.rcac` that a caller imported earlier, is another. This drop is what stops
    `from cluster_mcp import rcac` from returning the old module after the retry imports a new one.
  - Its docstring says why each rule holds, and that a module another thread is importing at that
    moment lies outside the loader's model. The loader is not thread-safe today: `TOOL_REGISTRY` is
    a bare list.

- **Amendment, review cycle 1 (F1), 2026-11-12.** The keep rule alone kept a library's submodule
  whose import registered a stray tool, so a retry never ran it again and loaded the capability a
  first load refuses. `_unimport(known, roots, registered)` now takes the failed load's
  registrations, `TOOL_REGISTRY[start:]` read in the handler before the cut, and a helper
  `_accounted` decides whether any library import may be kept: every entry must be a function, or a
  tool of one (through each `__wrapped__`), whose `__globals__` is a module the load forgets or one
  the import system dropped as it raised, and none a module it would keep. Otherwise every new
  module is forgotten, since which module registered the entry, or which kept module imported that
  one, cannot be told. `_library` holds the keep test the loop held. Identities only, and `vars()`
  of exact `ModuleType`, `FunctionTool` and function objects, so no capability code runs. Still
  outside `:320-382`.

**`load()`:**

- Right after `scratch = _scratch()` (`:319`) and before `try:` (`:320`), two lines:
  `known = set(sys.modules)` and `capability: Capability | None = None`. Taking the snapshot after
  `_scratch()` keeps the rule independent of what constructing a FastMCP server imports lazily
  ([`research/00`](research/00-digest.md) decision 3).
- The failure handler (`:383-387`) becomes:

  ```python
  except BaseException as exc:
      try:
          if isinstance(exc, (CapabilityLoadError, KeyboardInterrupt)):
              raise
          raise CapabilityLoadError(distribution, _cause(exc)) from exc
      finally:
          try:
              _unimport(known, _roots(ordered, loaded, capability))
          finally:
              del TOOL_REGISTRY[start:]
  ```

  - The refusal is built first. `_cause` runs a capability's `__str__`, and a lazy import there is
    then forgotten and its tools cut.
  - The registry is cut last. It is cut even if `_unimport` raises, and a `KeyboardInterrupt` in
    `_cause` runs both steps too.
  - The refusal's text, type, `__cause__`, `__context__` and distribution are as today (R4; the
    adversarial review checked each).
- Nothing in `:320-382` changes, and a successful load forgets nothing. A second `load()` after a
  successful one still finds the first load's tools in the registry and registers nothing new.

**Docs, in the same commit** (§ Conventions, "Point to a rule; don't restate it"):

- `capabilities.py`:
  - the module docstring (`:15-19`) and `load()`'s docstring (`:305-307`) say a failed load also
    forgets the modules it imported, so a later load imports them again;
  - `installed()`'s docstring (`:398-399`) says a failed load raises again on the next call,
    importing again.
- AGENTS.md:
  - §7 (`:2820-2823`): the same sentence beside the cut-back, naming the library rule, and a
    requirement on capability authors: a retry imports a capability's modules again, so a
    capability's import must be repeatable in one process (the plan sign-off's ruling on Q1, GOAL
    Clarifications);
  - §7, the `installed()` bullet (`:2833-2834`): names the new test;
  - the footgun note on `capabilities.py` (`:2193-2195`): "a second `load()` after a successful one
    registers nothing new; after a failed one it imports the capabilities again";
  - § Testing (`:395-405`): names the new test beside `test_a_failed_load_is_not_cached`;
  - the repository map's `capabilities.py` row (`:167`): "a failure rolls the tool registry back
    and forgets the modules it imported".
- `tests/mutants.py`: the comment above `ROLLBACK` (`:306-307`).

**Test (R5).** `test_a_load_retried_after_a_failure_is_a_first_load` in
`tests/test_capabilities.py` is marked `@pytest.mark.unit` and parametrized as
`entry` × `kind` × `layout` × `names`, 3 × 7 × 4 × 4 = 336 rows:

- **`entry`:** `load`, `installed` or `server`.
  - `installed` and `server` monkeypatch `cluster_mcp.core.capabilities.entry_points` and
    `_installed`, as `test_a_failed_load_is_not_cached` does.
  - `server` calls `create_mcp_server('none', site=SITE)` with no capabilities and reads
    `served_tools`.
  - The member tools each row expects come from `by_name()`, read once before anything is
    monkeypatched.
- **`kind`**, from the existing tables plus three new plants:
  - `raises-at-tools` fails before its tools module has imported.
  - `raises-at-declared`, `stray-imported-by-tools` and `tool-not-a-tool` fail after it has
    imported.
  - `stray-through-a-helper` is new: the tools module imports a helper that imports the module
    defining the stray tool.
  - `non-tool-from-a-helper` is new: the entry point's module imports a helper that appends a
    non-tool.
  - `registers-in-its-text` is new: the tools module raises an exception whose `__str__` imports a
    module that registers a tool. This kind pins the order of the handler.
- **`layout`:**
  - `top-level`: both planted packages are top-level, and nothing is imported first.
  - `clean-imported-first`: the test imports the clean capability's package before the first load.
  - `failing-imported-first`: the test imports the failing capability's package before the first
    load.
  - `namespace`: the clean capability is planted as a portion of the `cluster_mcp` namespace
    (`cluster_mcp/planted_first/` under `tmp_path`). The row also asserts that `vars(cluster_mcp)`
    holds no stale attribute for it after the failed load.
- **`names`:** `MEMBER_SETS`, with the members given beside the planted pair.

Each row plants `pair()`'s clean `planted-a-first`, with a tool of its own, and the failing kind
under a distribution that sorts after it. It first asserts that the clean tools module is not in
`sys.modules` before the first load. Then it runs three steps:

1. **First load (R4).** Record the message. Assert that it names the failing distribution, and that
   `TOOL_REGISTRY` equals its pre-load copy. These messages start with **"a failed first load
   changed"**.
2. **Retry with the failing one present (R1).** The message equals the first load's, and the
   registry equals its pre-load copy again.
3. **Retry with the failing one removed (R2).** The load succeeds, and a refusal here is wrapped in
   `pytest.fail`. The planted capability comes back with exactly its own tool, by name, and each
   member with the tools read before the monkeypatching. Every returned tool is in `TOOL_REGISTRY`
   exactly once, by name and by identity. In the `server` leg, `served_tools` lists the planted
   tool once.

Steps 2 and 3 share one fragment at the start of every failure message: **"a load retried after a
failure is not a first load"**. That fragment is the mutation case's `why`. No message carries a
spec id. Teardown removes any `cluster_mcp` attribute a `namespace` row left behind (the `plant`
fixture already removes the planted modules by `__file__`).

**Mutation case (R6).** `capability-retry-imports-nothing` in `tests/mutants.py`, `file=LOADER`:

- It replaces the inner `try:` / `_unimport(…)` / `finally:` with the bare cut-back. That is
  today's retry behaviour in the new handler shape, and R4's cases still hold.
- Its targets are every row of the R5 test beside the `both` member set: `entry` × `kind` ×
  `layout`, 84 rows. Its `why` is the shared retry fragment.
- Under the mutant, every row's retry refuses the clean capability, because it sorts first, so every
  row fails at step 2.
- The four anchors this cycle moves are re-planted against the new text in the fix's commit, each
  breaking the same contract as before: `capability-scratch-per-capability`,
  `capability-refusal-keeps-registry`, `capability-other-exception-keeps-registry` and
  `capability-load-failure-passes-re-raises`, with `ROLLBACK`.
- The mutation gate is graded per `method/mutation-testing.md` § When a review is done, in the
  operator's KB.

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1   | `_unimport` in the handler's `finally`. The failing capability's modules and helpers are imported again, and so is any of its package that a caller imported first (the roots). Every refusal decided after its tools module imported (registry scans, odd entries, strays, listing, serving, the refusal's own text) is therefore decided on the same registrations. The clean capability sorts first and registers again, so it is never named. Read under Q1 (§ 5). |
| R2   | The same forgetting. The clean capability's tools module runs again and registers its tools once, and the `:341` scan returns them as in a fresh process. The members, already imported, keep their pre-load registrations, which the cut-back never touched. Read under Q1. |
| R3   | The fix is inside `load()`. `installed()` calls it uncached after a failure, and `create_mcp_server()` with no capabilities calls `installed()` (`core/server.py:129`). The test's `entry` axis drives all three. |
| R4   | Nothing in `:320-382` changes. The refusal is built from the same values with the same chaining, the cut-back is unchanged, and a success forgets nothing. On the prototype, the existing 711 `test_capabilities.py` rows and the 46 `test_startup.py -k capabilit` rows passed unchanged. The test's step 1 asserts the cut-back, and `registers-in-its-text` pins it against a lazy import in the refusal's text. |
| R5   | `test_a_load_retried_after_a_failure_is_a_first_load`, described above. |
| R6   | `capability-retry-imports-nothing`, described above. |

## 3. Invariant gate (AGENTS.md constitution check)

The design was walked against the invariants before research and again after it was drafted. It
touches §7 and § Conventions. §9 is unaffected: `composed()` and the order of the texts do not
change.

- **§7, the load's refusals and their text:** unchanged. Every check in `:320-382` is untouched, and
  the handler builds the same `CapabilityLoadError(distribution, _cause(exc))`.
- **§7, the cut-back "to what it held before the load began":** kept. The forgetting is added
  beside it, and §7's text says so (§ 2 Docs). A `KeyboardInterrupt` is still not a refusal: it is
  raised as it is, after the same cut-back.
- **§7, `installed()` caches a success and never a failure:** unchanged.
- **§7, "No read of a loaded record runs capability code":** the new code reads only `str` fields
  of exact `Capability` records, `sys.modules` keys, and the `__dict__` of objects whose type is
  exactly `ModuleType`. It calls no `getattr`, `delattr` or `isinstance` on anything else.
- **§7, no core module imports a member:** unchanged. The helpers import nothing.
- **§ Conventions:** docs in the same commit; comments state the why, with no spec ids; the test is
  marked `unit`; each verify names the test ids it depends on.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| The cut-back moves into a `finally` that runs after the refusal is built, and after `_unimport`. Today it runs before the refusal is formatted. | `_cause` runs capability code. A lazy import there must be forgotten and its tools cut. A raise or interrupt inside `_unimport` must still leave the registry cut (R4). | Forgetting before formatting, today's order plus one call, leaves a lazy registration standing after the failure (research/01 §2; review G2). |
| `_unimport` keeps a library's lazy imports, and roots each capability at its outermost regular package. A bare "forget everything new" (H) has no such rule. | Under H, a library's lazily imported submodule would coexist with the old one held by its parent's attribute (research/01 §1). Without the roots, a caller that imported a capability's package first (`import cluster_mcp.rcac`) gets today's defect back (review F1). | H is shorter, but it carries that hazard into every failed load. Roots only at `ep.module` and `tools` (the candidate, or P) fail R1 open: the retry *loads* a capability the first load refused, when a helper made the registration (research/01, table rows 4-7). |
| **A reading of R1 and R2 (Q1):** a retry *runs a capability's modules again*. R1 and R2 hold for a capability whose import can be repeated in one process. | A module-level registration in another library, such as a metrics collector that refuses a duplicate name, fails the second run. The retry then names a capability that loaded cleanly (review F2, probe: `cannot load capability aaa-good: ValueError: Duplicated timeseries …`). | The alternative is replay: keep each still-imported module's cut registrations and re-append them on a retry whose import is a no-op. It needs per-entry state that outlives a load. It cannot attribute a non-tool entry, or a tool whose module was dropped by the import system, to a module. It also adds loop lines inside the sibling's range (research/01 §7). The GOAL's non-goal leaves such state alone and does not undo it, but R1 as worded does not excuse it. |
| **Step 5's prototype full-suite dry run is not run in the plan step;** P2's full `verify` stands in for it (foreman ruling at the plan sign-off, 2026-11-12: the host is shared and full runs are scheduled). | Code-plan Step 5 asks for the prototype's full suite once; this plan step was told to stop before any full run. | Running it here would take a heavy run the foreman schedules; targeted runs on the prototype were green but for the four anchors P1 re-plants. |

Each row was read against the wording of R1 to R6. Rows 1 and 2 bend no R-ID: the refusal's text is
the same (R1, R4), and the registry ends where it does today (R4). Row 3 is a reading of R1 and R2
that the GOAL did not state; the plan sign-off accepted it (GOAL Clarifications, 2026-11-12) and
the rest is seeded as `issues/capability-import-side-effects-on-retry.md`. Row 4 records a
foreman ruling on the plan step itself and bends no R-ID.

## 4. Rabbit holes (resolved)

- **Which modules to forget.** The rule in § 2: keep library lazy imports, and forget everything
  else new, including whatever lies below a capability's root. The candidate and P fail R1 open. H
  forgets library submodules. Pre-root H′ missed a capability whose package was imported first. The
  final rule was prototyped:
  - All nine research/01 scenarios gave the first load's message on retry, and with the broken
    capability removed, `aaa-good` loaded with `a_echo` registered once.
  - The reviewer's pre-import probe (`import cluster_mcp.rcac` first, both members beside a clean
    and a broken capability) refused `zzz-broken` both times. Without the broken one, 25 tools
    registered, each once.
  - The replaced-parent, module-subclass and lazy-text probes, each under three hash seeds, raised
    the refusal on the first load and on the retry, with nothing left registered.

  Sources: [`research/01`](research/01-load-module-cache.md), [`research/00`](research/00-digest.md)
  decision 2.
- **Stale parent attributes.** A parent drops its attribute for a forgotten child (research/01
  §1). On the prototype, `cluster_mcp.rcac` was rebound after the retry.
- **Members registering twice.** Members are imported by `tests/conftest.py`, and at the command
  line by the one `installed()` call, before any retried load. A module in the snapshot is never
  forgotten ([`research/02`](research/02-tests-and-mutants.md) §1).
- **Mutation anchors.** Four move, all named above. Every other `capability` anchor applied on the
  prototype (research/02 §3).
- **Naming R1/R2 in a kill.** The spec-id hygiene rule forbids the id, so a fragment states the
  contract in words. It is distinct from step 1's R4 fragment (research/02 §3; review G3).

### 4a. Adversarial review outcome

One reviewer pass, with GOAL and this design, attacked the prototype with five probes.

| Finding | Severity | What it found | Folded in |
|---|---|---|---|
| F1 | HIGH | A caller that imported a capability's own regular package first got the defect back. | The roots rule, plus the `clean-imported-first` and `failing-imported-first` layouts. § 5's earlier claim that this case behaves like the pre-imported-tools test was wrong, and is removed. |
| F2 | MEDIUM | A process-wide duplicate registry in another library makes the retry name a healthy capability. | Deviation row 3, and Q1 at the sign-off. |
| F3 | MEDIUM | A replaced or subclassed parent module made `_unimport` raise over the refusal, or run capability code after the cut. | Exact `ModuleType` and `str` checks, dictionary reads and pops only, and the cut-back in the innermost `finally`. |
| G1 | MEDIUM | No row covered a capability below a known namespace, or the attribute drop. | The `namespace` layout. |
| G2 | MEDIUM | Nothing pinned the order of the handler. | The `registers-in-its-text` kind. |
| G3 | LOW | One shared fragment could not tell a first-load failure from a retry failure. | R4's own fragment, and step 3 wrapped in `pytest.fail`. |
| G4 | MEDIUM | Calling `by_name()` after the monkeypatching runs the planted load, or reads the row's own cache. | It is read once before the monkeypatching. |

Reviewed and found sound:

- the R6 case, and the kinds;
- the isolation the `plant` fixture gives;
- first-load chaining (`__cause__`, `__context__`, `__suppress_context__`);
- the distribution name.

No security finding.

## 5. Risks & open questions

- **Q1 (sign-off).** Does R1/R2 hold only for capabilities whose import can be repeated in one
  process, as deviation row 3 reads it? Or must it also hold for one that registers into another
  library's duplicate-refusing state at import, which would mean replay instead of re-import (a
  larger change)? The default here is the first reading, recorded as a GOAL clarification at the
  sign-off if accepted. If the second is ruled, the plan goes back to design. **Ruled 2026-11-12:**
  the first reading (GOAL Clarifications); the rest is seeded as
  `issues/capability-import-side-effects-on-retry.md`, indexed in `ROADMAP.md` (Part I, safety).
- **Third-party modules first imported during a failed load are imported again on the retry,**
  as a fresh process would import them, once. That includes a new top-level library a capability
  pulls in. A library that refuses a second import (numpy warns, and under `-W error` that warning
  is an error) would then fail the retry, naming the capability. Research and review reproduced no
  such case: `rpds`, `cryptography`, `yaml` and `ctypes` re-imported cleanly under `-W error`. Q1
  covers this case too.
- **Other threads.** A module another thread first imports while the load runs is new too. On
  failure it is forgotten, unless the library rule keeps it, and is imported again on its next use.
  The docstring states this, and the loader is already single-threaded.
- **A `namespace` row adds a `tmp_path` portion to `cluster_mcp`.** The namespace path recomputes
  from `sys.path`, which the `plant` fixture restores. Build checks that `tests/test_packaging.py`'s
  pure-namespace checks don't see the portion when they run after it.
- **Human gate.** `core/capabilities.py` is a high-blast-radius path (§ Invariants), so a CONFIRMED
  review finding in it needs a human decision before landing.
- **This plan step did not run the prototype's full suite.** The host is shared, and the foreman
  schedules full runs. The targeted runs on the prototype were green, apart from the four anchors
  named above. Ruled at the plan sign-off: P2's full `verify` stands in for it (deviation row 4).

## 6. Verification strategy

- **P1:**
  - both eras of `tests/test_capabilities.py`, `tests/test_mutations.py` and
    `tests/test_hygiene.py`;
  - the new test by node id, so that a missing test fails the gate rather than passing empty;
  - `tests/test_startup.py -k capabilit` in both eras. It drives a capability that cannot load
    through the CLI, which pins the command-line path as unchanged (exit 5);
  - the four re-planted mutation cases through `tests/mutants.py --self-check`.
- **P2:** the new case and the four re-planted cases through `tests/mutants.py --self-check`, then
  the profile's full `verify`, which ends with the sandboxed `cluster-mcp --help`.

Measured on the prototype, one era each:

| Run | Wall time |
|---|---|
| `test_capabilities.py` | 5.6 s |
| capability anchors | 3.3 s |
| `test_startup.py -k capabilit` | 31 s |
| one mutation case | about 3.5 s (research/02 §5) |

The new test's 336 rows are not measured yet. Build reports their time in the P1 commit body.

## Notes

- **Shared lines with the sibling `capability-tool-objects-inert`.** That cycle changes `load()`'s
  registered-entry checks and the registry scan (`:330-349`). This cycle touches none of
  `:320-382`. Its lines are:
  - the imports `import sys` and `from types import ModuleType` (`:33-37`);
  - the four helpers, after `:178`;
  - two lines between `:319` and `:320`;
  - the handler, `:383-387`.

  The textual overlaps lie elsewhere:
  - in `load()`'s docstring, the sibling's registered-entry sentence (`:298-299`) and this
    cycle's failure sentence (`:305-307`) are in one paragraph;
  - the module docstring;
  - AGENTS.md §7, where the sibling's registered-entry bullet sits a few lines above this
    cycle's cut-back sentence;
  - the footgun note on `capabilities.py` (`:2193-2200`), which both cycles edit;
  - `tests/mutants.py`, where both cycles add cases and this one re-plants `ROLLBACK` and three
    others.

  Whichever cycle lands second rebases onto the other and re-runs the other's tests and mutation
  cases. It resolves those paragraphs by keeping both sentences. Semantically, this fix reads no
  registry entry, so the sibling's exact-type checks don't change which modules it forgets.
- **The interrupted load is covered too, as a by-product, outside the R-IDs.** The same `finally`
  runs for a `KeyboardInterrupt`. The prototype probe planted a clean capability and, after it, one
  whose tools module raises `KeyboardInterrupt`:

  | Step | Base code | Prototype |
  |---|---|---|
  | First load | interrupted, registry cut back | interrupted, registry cut back |
  | Retry | refused the clean `aaa-good` | interrupted again |
  | Retry with the interrupting one removed | refused the clean `aaa-good` | loaded `aaa-good` with its tool |

  The windows left open are an interrupt inside the handler itself, and one inside the import
  system's own cleanup of a failing module. `issues/capability-reload-after-interrupt.md` can be
  confirmed against this when it is shaped. This cycle adds no interrupt row, and the seed stays
  as filed.
  - 2026-11-12, review cycle 1 (F2): the seed misstated this, so the remediation pins the covered
    case (`test_a_load_retried_after_an_interrupt_is_a_first_load`) and restates the seed to the two
    windows above.
- **Prototype.** The prototype was a detached worktree, `capability-reload-after-failure-proto`.
  It was cut at the GOAL commit `aa1688a`, not at `origin/develop`, so that it carried the cycle's
  GOAL, and it was closed before the sign-off. A build-time prototype or mutation copy freezes
  GOAL, PLAN and `verify/` from the parent of the first build commit, which is the plan commit.

---

*Backing research: [`research/00-digest.md`](research/00-digest.md).*
