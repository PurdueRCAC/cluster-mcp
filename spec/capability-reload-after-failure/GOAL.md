# GOAL — A capability load retried after a failure loads the healthy ones and names the broken one

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** capability-reload-after-failure
- **kind:** fix
- **appetite:** small

## Problem

A library caller that catches a `CapabilityLoadError` and loads again in the same process gets a
wrong answer. `load()` (`packages/cluster-mcp/src/cluster_mcp/core/capabilities.py:290-388`) loads
the capabilities in (distribution, entry-point name) order. It imports each one's tools module
(`:329`), and on the first failure it cuts `TOOL_REGISTRY` back to what it held when the load
began (`:312`, `:384`). The tools modules it imported stay imported. A retry therefore registers
nothing for a capability that loaded cleanly the first time, and the load then refuses that healthy
capability because its instructions list tools it no longer registers. The error names the wrong
distribution.

Observed with two planted distributions, `aaa-good` (loads) and `bbb-broken` (raises). The first
load reports `cannot load capability bbb-broken: …`. A second load in the same process reports
`cannot load capability aaa-good: its instructions list ['a_echo'], which it does not register`.

**Pre-existing:** no. The defect came in with the entry-point loader (`capability-extras`, landed in
`4e772ec`, 2026-11-01). The command line can't reach it, because a load failure stops startup with
exit 5 and nothing loads twice. It reaches a library caller that calls `installed()` or
`create_mcp_server()` again after catching the error. `installed()` deliberately never caches a
failure, so every one of its retries goes through this path (AGENTS.md § Invariants §7). The test
that covers that rule, `test_a_failed_load_is_not_cached` (`tests/test_capabilities.py:1566`),
checks the capability names the retry returns, not their tools. This matters beyond the two members
that exist today, because every capability family the roadmap adds will register through this
loader.

## Outcome / vision

A load that fails leaves the process in a state where a retry behaves as a first load in a fresh
process would. If the broken capability is still there, the retry refuses it with the same message.
If it has gone or been mended, the retry loads every capability, each with its tools.

## Acceptance criteria (the contract)

- **R1** — IF a load fails, THEN a later load in the same process over the same capabilities SHALL
  raise the refusal a first load in a fresh process raises: a `CapabilityLoadError` naming the same
  distribution with the same cause, so its message is identical to the first load's. It SHALL never
  name a capability that loaded cleanly in the first load.
- **R2** — WHEN a load in the same process follows a failed one and every capability it is given
  loads cleanly (the failing one removed or mended), the load SHALL succeed. It SHALL return each
  capability with the same tools a load in a fresh process returns it with, and SHALL leave each of
  those tools registered exactly once.
- **R3** — R1 and R2 SHALL hold whichever library entry point makes the retry: `load()`,
  `installed()`, or `create_mcp_server()` when it is given no capabilities.
- **R4** — A first load SHALL behave as it does today: the same capabilities load, the same ones
  are refused with the same message, and no tool it registered stays registered after it fails.
- **R5** — A test SHALL plant a capability that loads cleanly and one that fails, with the clean
  one's tools first registered by the failing load. It SHALL then load again twice, once with the
  failing one still present (R1) and once with it removed (R2). It SHALL assert that the retry's
  refusal message equals the first load's, and on the tools returned and registered, not only on
  the capability names. Among the failing capabilities it plants SHALL be one that fails after its
  tools module has imported, where a retry's cause could differ.
- **R6** — A case in `tests/mutants.py` SHALL plant today's retry behaviour, and R5's test SHALL
  kill it with the violation that names R1 or R2. The mutation gate is graded per
  `method/mutation-testing.md` § When a review is done, in the operator's KB (AGENTS.md § Factory).

## Non-goals (no-gos)

- **Making the tool objects inert:** exact-type checks of what a tools module registers, and
  whether the load serves a copy. That is the sibling cycle `capability-tool-objects-inert`.
- Any change to what a first load accepts or refuses, or to the text of its refusals (R4 holds it
  still).
- Any change to the command-line path. A load failure still stops startup with exit 5, and startup
  gains no retry.
- Any change to `installed()`'s caching: a success is cached and a failure is not.
- Undoing anything else a capability's import did to the process, such as state it set in other
  modules or dependencies it imported. The contract covers only which capabilities load, which tools
  they register, and which distribution a refusal names.
- A retry after a load that a `KeyboardInterrupt` cut short. It is seeded as
  `issues/capability-reload-after-interrupt.md` (Part I, safety).
- Reloading a capability whose source changed between loads (hot reload). A second load after a
  successful one is also out of scope, since `installed()` caches the success.

## Clarifications

- 2026-11-12 · foreman ruling at GOAL sign-off: **Q:** must a retry's refusal carry the first
  load's cause, or only name the right distribution? **A:** (a), the refusal is identical (same
  distribution, same cause, same message): a retry behaves as a first load in a fresh process
  would. R1 and R5 say so.
- 2026-11-12 · foreman ruling at GOAL sign-off: **Q:** does the contract cover a load a
  `KeyboardInterrupt` cut short? **A:** (a), failures only. The interrupted case is seeded as
  `issues/capability-reload-after-interrupt.md` (Part I, safety) and is a Non-goal here.
- 2026-11-12 · foreman ruling at GOAL sign-off: R6 (the mutation case) stays.

## Related materials

- Seed: [`issues/capability-reload-after-failure.md`](../../issues/capability-reload-after-failure.md)
  (found by `capability-extras` review cycle 1, 2026-10-31).
- `spec/capability-extras/` (REVIEW, cycle 1): the cycle that shipped the loader.
- `AGENTS.md` § Invariants §7, which covers the load, the cut-back and `installed()` never caching a
  failure. Its footgun note on `capabilities.py` (§ Invariants, Footguns) says "a second `load()`
  of the same capabilities registers nothing new".
- Seeded from this shaping: [`issues/capability-reload-after-interrupt.md`](../../issues/capability-reload-after-interrupt.md).
- Source: `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py` (`load()` `:290-388`,
  `installed()` `:395-404`); `packages/cluster-mcp/src/cluster_mcp/core/server.py:129`
  (`create_mcp_server` → `installed()`); `tests/test_capabilities.py:1566`.

## Notes

- **Overlap with `capability-tool-objects-inert`**, shaped at the same time. Both cycles change
  `load()` in `core/capabilities.py`. That cycle changes how the load checks what a tools module
  registered (`:330-334`, `:341`), the same `TOOL_REGISTRY` scan that decides which tools this
  cycle's retry finds. Whichever cycle lands second rebases onto the other and re-runs the other's
  tests. Each keeps its own scope.
- Several `tests/mutants.py` cases anchor in `core/capabilities.py` (`capability-load-failure-swallowed`
  and others). If the fix moves that code, `test_mutation_anchor_applies` turns red, and the moved
  cases are re-planted in the same commit (AGENTS.md § Testing, the mutation runner).
- **Human gate.** `core/capabilities.py` is a high-blast-radius path (AGENTS.md § Invariants,
  High-blast-radius paths), so this cycle's review takes the human gate.
- The §7 text and the footgun note on `capabilities.py` describe the load's registry
  behaviour, so the fix may need a same-commit doc update. That is the plan's call.
