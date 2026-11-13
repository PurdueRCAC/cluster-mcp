---
slug: capability-reload-after-failure
title: A capability load retried after a failure loads the healthy ones and names the broken one
kind: fix
appetite: small
status: done
branch: fix/capability-reload-after-failure
base: develop
current_phase: done
last_updated: '2026-11-13'
phases:
- id: P1
  name: A failed load refuses every later load in the process
  status: done
  satisfies:
  - R1
  - R2
  - R3
  - R4
  - R5
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: export UV_PYTHON=3.14 && uv run pytest -q tests/test_capabilities.py tests/test_mutations.py tests/test_hygiene.py && uv run pytest -q tests/test_startup.py -k capabilit && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_capabilities.py tests/test_mutations.py tests/test_hygiene.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_startup.py -k capabilit && uv run python tests/mutants.py --self-check capability-retry-imports-nothing capability-refused-load-loads-what-it-is-given capability-refused-load-loads-what-it-finds capability-retry-refusal-says-not-to-restart capability-own-refusal-read-as-the-loads capability-scratch-per-capability capability-refusal-keeps-registry capability-other-exception-escapes capability-other-exception-keeps-registry capability-load-failure-passes-re-raises
- id: P2
  name: The mutation case for today's retry, the ledger, and the full gate
  status: done
  satisfies:
  - R6
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: export UV_PYTHON=3.14 && uv run python tests/mutants.py --self-check capability-retry-imports-nothing capability-refused-load-loads-what-it-is-given capability-refused-load-loads-what-it-finds capability-retry-refusal-says-not-to-restart capability-own-refusal-read-as-the-loads capability-scratch-per-capability capability-refusal-keeps-registry capability-other-exception-escapes capability-other-exception-keeps-registry capability-load-failure-passes-re-raises && uv lock --check && uv run pytest -q tests/test_ssh_exec.py -k silent && uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k silent && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && bin/sandbox.sh uv run cluster-mcp --help
review:
  last_reviewed_commit: 43ae93af8409ffbf45bee8e9c94f3f4bbf5afa54
  verdict: changes-requested
  blocked_reason: 'F-A: R5''s no-import/register/run asserts cannot fail on the planted retries; a load-then-refuse loader on the given-capabilities path survives'
  cycle: 3
---

# TECH.md — A capability load retried after a failure loads the healthy ones and names the broken one

The **context engine and finite-state machine** for building this feature. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/{slug}/TECH.md`); the per-phase
checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** [`research/00-digest.md`](research/00-digest.md) + briefs.

## Frontmatter field reference

See the KB template (`$KB/skill/_templates/TECH.md` → Frontmatter field reference); nothing here
departs from it.

## Conventions (apply to every phase)

- Commit conventions, code style, and load-bearing invariants come from the repo's `AGENTS.md` — it
  is the constitution. Walk the sections of its § Invariants that this change touches; that is the
  curated footgun checklist.
- One phase per `code-build` invocation by default; one atomic commit containing **both** the code and
  the `TECH.md` state change. The branch commit subject is code-build's (`$KB/skill/code-build.md` →
  Step 6), not restated here; branch commits are squashed away at `code-publish` per the profile's
  `landing`. Trailers follow the profile's `branch commits`.
- The last phase carries the standing last-phase items: the deferral ledger (`code-plan` Step 6.8),
  and every item the previous cycle's last phase carried for a project-level obligation (mpsearch's
  `## Times` quote, taken as `code-build` Step 4 says). A plan that drops one says why in `PLAN.md`.
- A PR body (when the profile's `landing` opens one) ends with an attribution naming the actual
  harness, model, and variant.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`): the
  help text, docs, or generated files it names change **in the same commit**.

---

## Phase P1 — A failed load forgets the modules it imported, and a retry is a first load
**Satisfies:** R1, R2, R3, R4, R5 · **Depends on:** —
**Goal:** a load that fails cuts the registry back and forgets every module it imported but a
library's own lazy imports, so a retry through `load()`, `installed()` or `create_mcp_server()`
refuses as a first load does, or loads every capability with its tools, each registered once. The
new test pins it on messages, tools and registrations. Every moved mutation anchor is re-planted,
and the docs say what is now true.

- [x] `core/capabilities.py`: `import sys`, `from types import ModuleType`, and the helpers
      `_file`, `_root`, `_roots` and `_unimport` after `_below`, as PLAN § 2 describes. Keep a new
      name only when an ancestor in `known` is a regular package (or not plainly a module) and the
      name is below no capability root. `pop` every other name. Drop the parent's attribute when the
      parent is exactly a `ModuleType` whose `vars()` holds the popped module under the leaf. Act only
      on `str` keys and exact `ModuleType` objects, read through `vars()`, never `getattr`,
      `delattr` or `isinstance`, and never iterate `sys.modules` in Python. The docstrings say why
      each rule holds, and that a concurrent import is outside the loader's model.
- [x] `load()`: `known = set(sys.modules)` and `capability: Capability | None = None` right after
      `scratch = _scratch()`; the handler as PLAN § 2's code block (refusal built first; an outer
      `finally` whose inner `try` forgets and whose inner `finally` cuts the registry). Nothing in
      the loop body changes.
- [x] `tests/test_capabilities.py`: `test_a_load_retried_after_a_failure_is_a_first_load`,
      `@pytest.mark.unit`, parametrized `entry` (`load`, `installed`, `server`) × `kind`
      (`raises-at-tools`, `raises-at-declared`, `stray-imported-by-tools`, `tool-not-a-tool`,
      `stray-through-a-helper`, `non-tool-from-a-helper`, `registers-in-its-text`) × `layout`
      (`top-level`, `clean-imported-first`, `failing-imported-first`, `namespace`) × `names`
      (`MEMBER_SETS`), 336 rows, with the precondition and the three steps of PLAN § 2. Member
      tools come from `by_name()` read before any monkeypatch. Step 1's messages start "a failed
      first load changed"; steps 2 and 3 start "a load retried after a failure is not a first
      load", step 3's refusal wrapped in `pytest.fail`. The `namespace` row asserts no stale
      attribute on `cluster_mcp` and its teardown removes any it left. Report the test's wall time
      in the commit body.
- [x] `tests/mutants.py`: re-plant `ROLLBACK` and the cases `capability-scratch-per-capability`,
      `capability-refusal-keeps-registry`, `capability-other-exception-keeps-registry` and
      `capability-load-failure-passes-re-raises` against the new text, each breaking the same
      contract with the same `why` as before; update the comment above `ROLLBACK`.
- [x] Docs, PLAN § 2 "Docs": the module, `load()` and `installed()` docstrings; AGENTS.md §7 (with
      the requirement on capability authors that a capability's import be repeatable in one
      process, per the GOAL's plan-sign-off Clarification), the footgun note on `capabilities.py`, § Testing beside `test_a_failed_load_is_not_cached`, and
      the repository map's `capabilities.py` row.
- [x] Check that `tests/test_packaging.py`'s pure-namespace checks pass after a `namespace` row
      (PLAN § 5).
- [x] Stage, then run the `verify:`.
- [x] **Remediation, review cycle 1 (2026-11-12): F1 and F2.** P1 and P2 reopened together: the
      fix moves the handler line `ROLLBACK` anchors, so the re-planted and new mutation cases ride
      in P1's commit (the `test_mutation_anchor_applies` lockstep), and P2 keeps the full gate.
      - **F1 (R1):** a failed load kept a library's submodule whose import registered (a stray tool
        from below a regular package a caller imported first), so the retry never ran it again and
        loaded, or passed over, the capability a first load refuses. The property: a retry runs
        again every module whose import registered anything, wherever it lies; a library's lazy
        import that registered nothing stays kept. `_unimport` now takes the failed load's
        registrations (`TOOL_REGISTRY[start:]`, read in the handler before the cut) and keeps a
        library's lazy imports only while `_accounted` finds every entry a function, or a tool of
        one, defined in a module it forgets or one the import system dropped as it raised, and none
        defined in a module it would keep; otherwise nothing new is kept. It compares identities
        and reads only exact `ModuleType`, `FunctionTool` and function objects through `vars()`. The
        loop's registered-entry checks (the sibling's lines) are untouched.
      - `tests/test_capabilities.py`: `test_a_retry_runs_again_a_library_module_that_registered`,
        `entry` × `kind` (`bound`, `unbound`, `bound-then-another-fails`) × `names`, 36 rows, F1's
        layout: the library's package imported first, its submodule registering a stray tool,
        bound by `@mcp_tool` or registered without a binding, and the wrong-distribution variant
        with a second failing distribution after the first. The keep side stays pinned by the 84
        `library-imported-first` rows.
      - `tests/mutants.py`: `capability-failure-keeps-a-registering-library-module` deletes the
        forced forget, killed by the new test's 9 rows beside `both` with "a load retried after a
        failure is not a first load"; `ROLLBACK`, and with it every case built on it
        (`capability-retry-imports-nothing` included), re-planted for the handler's new argument;
        `capability-failure-forgets-every-new-module` re-planted on the `kept` set.
      - Gate (2026-11-12, the retuned `verify:`): 2528 passed in each era (2451 before; the 76 new
        rows run in 1.4 s), the three retry tests 496 in each era, `test_startup.py -k capabilit`
        46 in each, and all seven of the cycle's cases killed with the runner's controls reported.
      - **F2:** `test_a_load_retried_after_an_interrupt_is_a_first_load`, `how` × `when` × `names`,
        40 rows: an interrupt cuts the load short after a clean capability, a retry is interrupted
        again, and without the interrupting one every capability loads with its tools, each once.
        `issues/capability-reload-after-interrupt.md` (this cycle's seed, not on `develop`) is
        restated in place to what stays open, an interrupt inside the handler's cleanup or the
        import system's, with its `ROADMAP.md` entry and the Safety group's line; the Part I count
        (31) and the group count (five) are unchanged, and every seed stays paired.
      - Docs: AGENTS.md §7 says the retry registers again what the failed load registered, wherever
        the module lies, names `_accounted`'s rule, both new tests and the interrupted retry, and
        says other state an import changed stays changed; § Testing names both new tests.
- [x] **Remediation, review cycle 2 (2026-11-12): the design is replaced; refuse, don't reload.**
      P1 and P2 reopened together and committed as one, as in cycle 1: the handler's text that
      `ROLLBACK` anchors moves, so the re-planted cases and the new ones ride with the code (the
      `test_mutation_anchor_applies` lockstep), and P2 keeps the full gate.
      - **The contract:** `GOAL.md` R2 re-scoped in its own commit (`cde0a99`), R1 and R5 following
        it: after a failed load, every later load in the process is refused, whatever it is given,
        with a `CapabilityLoadError` naming the first failure's distribution, its message the first
        one's followed by `(refused by an earlier load in this process; restart the process to load
        capabilities again)`; the refused load imports, registers and runs nothing; a fresh process
        loads as a first load. **The plan-sign-off clarification of `d985301` (R1 and R2 hold for
        repeatable imports) lapses with it**: a later load imports nothing, so no import is repeated.
      - **Removed, since it served only a reload after a failure:** from `core/capabilities.py`, the
        helpers `_NOT_PLAIN`, `_file`, `_root`, `_roots`, `_library`, `_accounted` and `_unimport`;
        `load()`'s `known = set(sys.modules)` snapshot and `capability` pre-binding; the handler's
        forgetting step (`_unimport` in a `finally`); the imports `sys`, `FunctionType` and
        `ModuleType`; and the module, `load()` and `installed()` docstring text saying a later load
        imports again. From `tests/test_capabilities.py`,
        `test_a_load_retried_after_a_failure_is_a_first_load`,
        `test_a_retry_runs_again_a_library_module_that_registered` and
        `test_a_load_retried_after_an_interrupt_is_a_first_load`, with their helpers
        (`LIBRARY_STRAYS`, `library_stray`, `assert_loads_with_its_tools`, the `library-imported-first`
        layout). From `tests/mutants.py`, `capability-failure-forgets-every-new-module` and
        `capability-failure-keeps-a-registering-library-module`, and the `retried()` targets of the
        removed test. From `AGENTS.md`, §7's forgetting rule, its keep rule for a library's lazy
        import, its requirement that a capability's import be repeatable, and the § Testing text for
        the removed tests. `issues/capability-import-side-effects-on-retry.md` and its `ROADMAP.md`
        entry are deleted (this cycle's own seed, never on `develop`): no import is repeated now.
      - **Kept from the earlier build:** the handler builds the refusal before it cuts the registry
        (`try`/`finally`), so a tool the refusal's own text registers is cut too (R4: no tool a
        failed load registered stays registered). Without it `registers-in-its-text` leaves its tool
        registered, as `develop` does.
      - **Built:** `load()` is now a guard around `_load()`, the former body, unchanged but for the
        handler. A module global `_failed` holds the first failure as plain text, `(distribution,
        message)`, read by `_failure` without running capability code: through `vars()` and `args`,
        and only from exactly a `CapabilityLoadError` holding exactly a `str` of each, else named by
        `GROUP` (`cannot load capability cluster_mcp.capabilities: a capability raised a
        CapabilityLoadError of its own`). A `KeyboardInterrupt` records nothing.
      - **Tests:** `test_a_failed_load_is_not_cached` now asserts the second call is refused with the
        restart text, discovering nothing, and that a fresh process (the state reset) loads and
        caches. `test_a_load_after_a_failed_one_is_refused_for_it`, `entry` × `kind` (the seven
        cycle-1 kinds and `plants-a-module-key`, review 2's A) × `layout` (`top-level`,
        `clean-imported-first`, `failing-imported-first`, `namespace`, `registered-by-a-library`,
        review 2's B) × `names`, 480 rows: the first refusal as before, then a retry with the failing
        capability and one without it, each refused with the first message and the restart text,
        naming the same distribution, with `sys.modules` and the registry unchanged and no planted
        function called (`sys.settrace`). `test_a_load_after_a_capabilitys_own_refusal_runs_none_of_its_code`,
        `entry` × four kinds × `names`, 48 rows. `test_an_interrupted_load_leaves_no_refusal`, 8 rows.
        `test_a_fresh_process_after_a_failed_load_loads_as_a_first_load` (integration, two sandboxed
        children). `conftest.py`'s autouse `no_failed_load` starts each test with `_failed` unset.
      - **Mutation:** `ROLLBACK` and the three cases built on it re-planted for the `try`/`finally`
        handler (`capability-load-failure-passes-re-raises` among them), and
        `capability-scratch-per-capability` back on `develop`'s anchor, the code there `develop`'s. `capability-retry-imports-nothing`
        now plants today's retry by disabling the guard, killed by the 120 `both` rows with "a load
        after a failed one was not refused for that failure". New:
        `capability-retry-refusal-says-not-to-restart` and `capability-own-refusal-read-as-the-loads`.
      - **Hand sweep over the new decision** (18 mutants of `load()`'s guard and record, `_failure`
        and the handler's order, each run against the four tests above,
        `test_a_capability_that_cannot_load_is_refused_naming_it` and
        `test_what_a_server_would_refuse_is_refused_at_load`, 852 rows, in each era): 16 killed. Two
        survive, equivalent while `CapabilityLoadError` is unpatched: `refusal.distribution` for the
        `vars()` read and `str(refusal)` for `args[0]`. They differ only when a capability's import
        patches the core's own class, a deeper layer of the class the own-refusal test pins, so they
        are seeded: `issues/capability-refusal-class-patched.md` with its `ROADMAP.md` entry (Part I,
        safety). The widened catch (a `KeyboardInterrupt` kept as a failure) is what
        `test_an_interrupted_load_leaves_no_refusal` was added to kill.
      - Gate (2026-11-12, the retuned `verify:`, 2 min 43 s): 2569 passed in each era (no skips),
        `test_startup.py -k capabilit` 46 in each, and all eight cases killed with the runner's three
        controls reported.
      - **Docs:** AGENTS.md §7, the `installed()` bullet, the footgun note on `capabilities.py`, the
        repository map's row and § Testing; the interrupt seed and its `ROADMAP.md` entry restated to
        HEAD (an interrupted load leaves its modules imported and no refusal); the cycle's seed gains
        a dated line that a reload, if Part II's hosted mode needs one, is shaped there; PLAN carries a
        supersession note.
- [x] **Remediation, review cycle 3 (2026-11-13): F-A (LOW, fixed rather than seeded).** P1 and P2
      reopened together and committed as one, as in cycles 1 and 2: the test's new layout and the
      mutation cases built on its rows ride together (`tests/mutants.py` mirrors `LAYOUTS`, and the
      `test_mutation_anchor_applies` lockstep holds the new cases' anchors).
      - **The property, both sides:** a refused load imports nothing, registers nothing and runs no
        capability's code, on inputs where a load would show it; and it is still refused naming the
        first failure, its cause and the restart text, for the new inputs too.
      - `tests/test_capabilities.py`, `test_a_load_after_a_failed_one_is_refused_for_it`: a sixth
        layout, `failing-sorts-first` (the clean capability's distribution `planted-zz-last`, so the
        first load stops before it and never imports it; asserted), 480 → 576 rows; and a third retry
        in every row, given a capability no load imported (`planted-0-new`, sorting before every other
        planted one, its absence from `sys.modules` asserted first). `refused_again` now reports what
        the refused load changed in one violation, `the refused load imported, registered or ran
        something: it imported […], forgot […], registered […] and ran […]`, comparing modules and
        tools by identity (a planted key's comparison raises), the order of each included; the message
        and distribution asserts follow it, unchanged.
      - `tests/mutants.py`: `RETRY_LAYOUTS` gains the layout. New permanent cases, `why` the violation
        above: `capability-refused-load-loads-what-it-is-given` (the review's H2b: the guard loads the
        capabilities it is given, swallows what that raises, then raises the right refusal), its
        targets the 48 `load` rows beside `both`; and its discovered twin
        `capability-refused-load-loads-what-it-finds` (the review's H2n), the 144 rows beside `both`.
        `installed()` and `create_mcp_server()` always call `load()` with no capabilities, so on those
        entry points H2b runs exactly HEAD's code and no test can tell them apart; the twin is H2b's
        behaviour there. `capability-retry-refusal-says-not-to-restart` also targets the new layout.
      - **Red under H2b, green on HEAD** (`.local/build4/h2b-rows-default.log`, `rows-modern.log`, every
        row of the retry test, both eras): H2b fails all 192 `load` rows with the violation above (the
        new-capability retry naming its imports and its run, 160 rows; the `failing-sorts-first`
        layout naming the failing capability's tools code run again, 12 rows, or the clean one's
        imports, registration and run, 20 rows); its `installed`/`server` rows pass, being HEAD's
        code. H2n fails all 576 rows the same way, through every entry point. HEAD passes all 576.
        Before this change H2b passed the test 0/480 (`.local/review3/reviewer/hand-default-2.log`).
      - Docs: AGENTS.md § Testing names the new layout, the new retry, and the two mutation cases.
      - Gate (2026-11-13, the retuned `verify:`, 3 min 27 s): 2667 passed in each era (no skips;
        2569 before, 96 new rows and the two new cases' anchor rows), `test_startup.py -k capabilit`
        46 in each, and all ten cases killed with the runner's three controls reported. The retry test
        runs about 3 s longer per era (6.7 s → 9.8 s, under the full gate's concurrent load).
- **Verify:** both eras of `test_capabilities.py`, `test_mutations.py` and `test_hygiene.py`; the
  new test by node id; `test_startup.py -k capabilit` (the CLI path still stops with exit 5) in
  both eras; the four re-planted mutation cases with the runner's controls.
- **Touches:** `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`,
  `tests/test_capabilities.py`, `tests/mutants.py`, `AGENTS.md`.

## Phase P2 — The mutation case for today's retry, the ledger, and the full gate
**Satisfies:** R6 · **Depends on:** P1
**Goal:** a mutation case plants today's retry behaviour and R5's test kills it, naming the
contract; every deferral is recorded; the profile's full `verify` is green.

- [x] `tests/mutants.py`: `capability-retry-imports-nothing`, `file=LOADER`, targets every row
      of `test_a_load_retried_after_a_failure_is_a_first_load` beside the `both` member set
      (`entry` × `kind` × `layout`, 84 rows; 105 with the layout the amendment below adds), `why`
      "a load retried after a failure is not a first load". It replaces the inner `try:` /
      `_unimport(…)` / `finally:` with the bare cut-back. The mutation gate is graded per
      `method/mutation-testing.md` § When a review is done, in the operator's KB.
- [x] **Amendment (foreman, 2026-11-12): a failed load keeps a library's own lazy import.** P1's
      build found no row that fails when the load forgets every module new since `known`: a library's
      lazy submodule the load imported (below a regular package already imported then, outside every
      capability root) was forgotten with the rest and nothing noticed. Under that mutant all 84
      rows above passed. Added:
      - `tests/test_capabilities.py`: a fifth `layout`, `library-imported-first` (336 → 420 rows).
        The test imports a planted library's regular package `planted_library` first, and the clean
        capability's tools module imports its submodule `planted_library.lazy`, which records each
        run in the package's `RUNS`. After the failed first load the submodule is still in
        `sys.modules`, still bound on its package, and has run once; after the retries it is the
        same module and has still run once. These messages start "a failed load forgot a library's
        own lazy import".
      - `tests/mutants.py`: `capability-failure-forgets-every-new-module`, `file=LOADER`, deletes
        `_unimport`'s keep rule (`if library and not any(_below(name, root) for root in roots):
        continue`), so every new module is forgotten. Its targets are the `library-imported-first`
        rows beside `both` (`entry` × `kind`, 21 rows), `why` the fragment above. It joins the
        P2 `verify:` self-check list.
      - AGENTS.md: § Testing names the new layout and the kept submodule; §7 points the keep rule at
        those rows.
- [x] **Deferral ledger** (last-phase item): walk P1's and P2's bodies, PLAN §§ 4–5 and Notes, and
      the branch's commit bodies for "do not fix here", "known limitation", "left as a follow-up",
      "deferred", "limit" and "not covered"; each must have an `issues/` seed and a `ROADMAP.md`
      entry. Expected: `issues/capability-import-side-effects-on-retry.md`, filed by the plan with its
      `ROADMAP.md` entry (Q1's remainder), and nothing new. The interrupt windows PLAN Notes names
      belong to the existing `issues/capability-reload-after-interrupt.md`, and PLAN § 5's other
      risks are review risks, not deferrals. An unrecorded deferral fails the phase.
      Result: as expected. Both seeds exist with their `ROADMAP.md` entries
      (`capability-import-side-effects-on-retry`, `capability-reload-after-interrupt`), and no other
      deferral turned up in P1, P2, PLAN §§ 4–5 and Notes, or the commit bodies. PLAN § 5 says Q1
      also covers a library a capability first imports in the failed load and that refuses a second
      import; the seed, this cycle's own and not yet on `develop`, now says so in its Notes.
- [x] Standing last-phase items: the previous cycle's last phase carried no project-level
      obligation beyond the ledger (no `## Times` quote in this repo).
- [x] Stage, then run the `verify:`.
- [x] **Remediation, review cycle 1:** P2's `verify:` self-checks
      `capability-failure-keeps-a-registering-library-module` too. The ledger is walked again: the
      restated interrupt seed keeps its entry, and the remediation adds no deferral.
- [x] Run the full `verify:` on the remediated tree (the foreman schedules it). Green on
      `131db35`, 2026-11-12: the seven cases killed with the runner's controls, the lock check, both
      eras' four suite commands (44, 154, 507 and 4868 passed, 14 skipped, in each), and the
      sandboxed `cluster-mcp --help`.
- [x] **Remediation, review cycle 2:** P2's `verify:` self-checks the cycle's cases as they now stand
      (P1's amendment). The ledger is walked again: `issues/capability-import-side-effects-on-retry.md`
      is gone with the design it recorded, the interrupt seed keeps its entry (restated), and the
      sweep's two survivors are seeded as `issues/capability-refusal-class-patched.md`. Part I is 31
      entries, Safety five.
- [x] Run the full `verify:` on the remediated tree. Green on `2bcfa50`, 2026-11-12, 27 min 34 s
      wall: the eight cases killed with the runner's three controls reported, the lock check, both
      eras' four suite commands (44, 154, 507 and 4909 passed, 14 skipped, in each), and the
      sandboxed `cluster-mcp --help`.
- [x] **Remediation, review cycle 3:** P2's `verify:` self-checks the two new cases too (P1's
      amendment). The ledger is walked again: the remediation adds no deferral, and the seeds stand as
      cycle 2 left them (`capability-reload-after-interrupt`, `capability-refusal-class-patched`).
- [x] Run the full `verify:` on the remediated tree. Green on the cycle-3 remediation tree (the
      commit that carries this line, but for this line and the phase states), 2026-11-13, 28 min 2 s
      wall with another heavy run on the host (load average about 5): the ten cases killed with the
      runner's three controls reported, the lock check, both eras' four suite commands (44, 154, 507
      and 5007 passed, 14 skipped, in each; 5007 is 4909 and 98 new), and the sandboxed
      `cluster-mcp --help`, which printed its usage.
- **Verify:** the new case and the four re-planted ones with the runner's controls, then the
  profile's full `verify`, both eras and the sandboxed `cluster-mcp --help`.
- **Touches:** `tests/mutants.py`; by the amendment, `tests/test_capabilities.py`, `AGENTS.md` and
  `issues/capability-import-side-effects-on-retry.md`.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[fix]` commit; stop and report.
