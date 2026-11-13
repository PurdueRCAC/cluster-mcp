# REVIEW — A capability load retried after a failure loads the healthy ones and names the broken one

> Adversarial QA by `code-review`, run in an isolated context (a fresh subagent). The correctness
> pass grades the branch diff against [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants
> **only**: it did not see `PLAN.md`/`TECH.md`. Every finding cites an **executed** command.

- **Reviewed commit:** 425bf499f2a0acddb7fa91d8b1f30c1aeac3836b  ·  **Base:** develop  ·  **Date:** 2026-11-12
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 (mirrors `review.cycle` in `TECH.md`)
- **Mode:** fresh blind pass over the full spec-excluded diff. The sequential fallback did not run.
- **Maintainer sign-off before publish: required.** This cycle changes `core/capabilities.py`, a
  high-blast-radius path (`AGENTS.md` § Invariants, High-blast-radius paths), and two CONFIRMED
  findings stand against it. See Human-gate triggers.

Evidence paths below are under the worktree's gitignored `.local/review1/` (`reviewer/` for the
blind pass, `orchestrator/` for the orchestrator's runs).

## Verification run

- **The full gate (the profile's `verify`)** ran green on `a79cc97`, P2's build commit. `425bf49`
  changes only `spec/capability-reload-after-failure/TECH.md` (`git diff --stat a79cc97 425bf49`),
  so the source tree is the one graded. The results:
  - lock check passed;
  - both protocol eras passed their four suite commands: 44, 154, 507 and 4791 tests, 14 skipped;
  - `bin/sandbox.sh uv run cluster-mcp --help` printed its usage.
- **The phase gates at `425bf49`** (`orchestrator/gates.log`, exit 0):
  - `test_capabilities.py`, `test_mutations.py` and `test_hygiene.py` passed 2451 in each era;
  - `test_a_load_retried_after_a_failure_is_a_first_load` passed 420;
  - `test_startup.py -k capabilit` passed 46 in each era (51 deselected);
  - `tests/mutants.py --self-check` killed all six of P2's cases, and its three controls reported;
  - `uv lock --check` passed.
- **Reviewer runs, with the output read:**
  - `uv lock --check` passed.
  - `test_capabilities.py` passed 1131 in each era (`reviewer/gate-test_capabilities-{legacy,modern}.log`).
  - `test_mutations.py` passed 1178, anchors included.
  - A narrow hygiene run passed 50: the spec-id test, `test_a_failed_load_is_not_cached` and the
    interrupt tests (`reviewer/gate-hygiene-narrow.log`).
  - The sandboxed `cluster-mcp --help` printed its usage (`reviewer/gate-help.out`).
- **Drives through `bin/sandbox.sh`:**
  - Fresh-process baseline vs. same-process retry, per entry point (`load`, `installed`,
    `create_mcp_server`), with members first imported by the failed load:
    `reviewer/fresh-baseline-*.json` and `reviewer/fresh-retry-*-{listing,raise}.json`.
  - A dependency mended between loads: `reviewer/mended.json`.
  - The CLI with a broken distribution, which exits 5 with `cannot load capability zzz-broken:
    RuntimeError: planted failure` (`reviewer/cli-broken.{err,exit}`).
  - The F1 and F2 probes. The orchestrator re-ran both at `425bf49` and got the same results:
    `orchestrator/f1-rerun.json` and `orchestrator/f2-rerun.json`.
- **Mutation** (`method/mutation-testing.md` § When a review is done):
  - **Tier 2:** the 12 tier-2 cases the diff touches are all killed for the right reason, and the
    runner's controls report (`reviewer/mutants-touched.log`, `reviewer/touched-cases.txt`). They
    are the six re-planted or new cases and six more anchored on lines the diff added.
  - `capability-retry-imports-nothing` is killed by 105 targets, with the violation "a load
    retried after a failure is not a first load".
  - `capability-failure-forgets-every-new-module` is killed by 21 targets.
  - **Tier 3a diff sweep: not run, because no tool is available.** The repo has no generated-mutant
    tool yet (the method's Python tool is still to be chosen by its trial). This is an unclosed gap,
    not a pass.
- **Spec-id grep** (`grep -rnE` for R#/P# ids in source, spec excluded): empty (`reviewer/specid-grep.txt`).
- **Tree:** `git status --porcelain` was empty after the reviewer handed back. It mutated no build
  state.

## Requirement → evidence matrix

No R-ID's deliverable is a committed `spec/` artifact, so the blind reviewer graded all six. The
orchestrator re-ran the F1 and F2 probes.

| R-ID | Implemented by | Verified how | Status |
|------|----------------|--------------|--------|
| R1 | `core/capabilities.py`: `_unimport`, `_roots`, `load()`'s handler | the 420 rows of the retry test; fresh-process probes per entry point; F1's probe | ❌ fails on F1's layout; ✅ for every other layout probed |
| R2 | same | fresh-process baseline vs. retry, comparing tools, descriptions, schemas and the served list; `mended.json` | ✅ |
| R3 | same; `installed()` and `create_mcp_server()` reach it | the test's `load`/`installed`/`server` axes; per-entry-point probes | ✅ (R1's F1 gap holds through every entry point) |
| R4 | the first-load path is unchanged | existing `test_capabilities.py` bodies, 1131 passed in each era; CLI drive, exit 5 | ✅ |
| R5 | `tests/test_capabilities.py::test_a_load_retried_after_a_failure_is_a_first_load` | read the test; `reviewer/retried-kinds.txt` | ✅ It asserts message equality and tools returned and registered, and includes failures after the tools import |
| R6 | `tests/mutants.py` `capability-retry-imports-nothing` | `reviewer/mutants-touched.log`; `orchestrator/gates.log` | ✅ killed, with the R1/R2 violation text |

Unmapped changes:
- `load()` now forgets imported modules after a `KeyboardInterrupt` too. A retry after an interrupt
  is a GOAL non-goal. The change does no harm, but it is what makes the interrupt seed stale (F2).

## Findings

### [MEDIUM/CONFIRMED] F1 · A retry loads a capability a fresh process refuses, when the failing capability's stray tool comes from a library submodule the failed load keeps

- **Where:**
  - `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py:255-256`: `_unimport` keeps a
    library's lazy import.
  - `:420-424`: the stray-registration refusal.
  - `AGENTS.md` § Invariants §7 (`AGENTS.md:2831`) says a retry "is refused, or loads, as a first
    load in a fresh process would".
- **Failure scenario:**
  1. A caller imports a regular package `toolkit` before the load. `toolkit` is no capability's root.
  2. A failing capability `zzz-bad` imports `toolkit.extra`, which registers a tool at import. The
     first load refuses `zzz-bad`: `loading it registered ['toolkit_echo'], which are outside
     zzz_bad.tools`. A first load in a fresh process refuses it the same way.
  3. `_unimport` keeps `toolkit.extra` as a library's own lazy import, so the retry never runs it
     again.
  4. The retry therefore **loads** `zzz-bad`, returning
     `{"aaa-good": ["a_echo"], "zzz-bad": ["z_echo"]}`.
  5. In a variant with a second failing distribution after it, the first load names `yyy-bad` and
     the retry names `zzz-bad2`. That is the wrong-distribution defect the GOAL exists to remove.
- **Evidence:**
  - `bin/sandbox.sh uv run python .local/review1/reviewer/probe_library_stray.py head|control`
    produced `reviewer/library-stray-{head,control}.json`.
  - `probe_library_stray2.py head` produced `reviewer/library-stray2-head.json`.
  - The orchestrator's re-run: `orchestrator/f1-rerun.json`.
- **Touches:**
  - R1 ("SHALL raise the refusal a first load in a fresh process raises").
  - §7's new sentence overclaims for this case.
  - The plan-sign-off clarification and `issues/capability-import-side-effects-on-retry.md` do not
    cover it. They concern imports that *cannot* be repeated; here the load chooses not to repeat
    one that can.
- **Severity:** MEDIUM, a bug on an edge layout. The maintainer may raise it to HIGH at triage,
  since it is R1 wrong.
- **Not SECURITY:** the module that registers is the capability's own installed code, which runs at
  import anyway.

### [MEDIUM/CONFIRMED] F2 · The interrupt seed and its ROADMAP entry describe a defect this diff already fixes

- **Where:**
  - `issues/capability-reload-after-interrupt.md`, Problem. It cites `capabilities.py:383-386`,
    which at HEAD is inside `load()`'s docstring; the handler is at `:462-480`.
  - `ROADMAP.md:345-353`.
- **Failure scenario:** both say an interrupted load leaves the tools modules imported, so a clean
  capability "registers nothing on the retry". At HEAD the handler's `finally` runs `_unimport` on
  a `KeyboardInterrupt` too. §7, in this same diff, says so: "the modules are forgotten".
- **Evidence:** `bin/sandbox.sh uv run python .local/review1/reviewer/probe_interrupt.py head|control`
  (`reviewer/interrupt-{head,control}.json`, `reviewer/interrupt-seed-evidence.txt`).
  - At HEAD the retry without the interrupting capability loads `aaa-good` with `a_echo`.
  - The control, with forgetting turned off (develop's behaviour), refuses `aaa-good`.
  - The orchestrator's re-run: `orchestrator/f2-rerun.json`.
- **Touches:** the rubric's seed-as-prose rule (a seed that misstates the defect is a real finding).
  It is also operating-manual drift outside § Invariants.

### Out of Scope (reproduced, inside an already-seeded class)

- **What happens:** a clean capability whose import first loads stdlib `curses` cannot be retried.
  Both retries give `cannot load capability aaa-good: ImportError: module 'curses' can only be
  loaded once per process`. That is true with the broken capability still present and with it
  removed.
- **Evidence:** `reviewer/curses.json`, `reviewer/reimport-stdlib.json`.
- **Not a regression:** develop also names `aaa-good` here.
- **Where it belongs:** the class of imports that cannot be repeated, which the plan-sign-off
  ruling sets outside R1/R2. Its home is the existing seed
  `issues/capability-import-side-effects-on-retry.md`, whose Problem holds at HEAD
  (`reviewer/side-effects.json`). No new seed. The stdlib case is a concrete example for that
  seed's triage.

### Sibling overlap (not a finding)

- `capability-tool-objects-inert` changes the registered-entry checks at `:420-442`. That is the
  same scan F1 slips past on a retry. Whichever cycle lands second re-runs F1's probe.
- Both cycles anchor mutation cases in `load()`'s handler, so the second to land re-plants them.

## Routing (cycle 1 → build)

Each finding is routed as a property over its whole domain, not as the instance.

- **F1 (R1, `core/capabilities.py`, §7):**
  - **Property:** a retry after a failed load reaches the same verdict as a first load in a fresh
    process, for every module the failed load ran whose import registers a tool or otherwise
    decides the load's outcome, whatever package that module sits under.
  - **The other side of the trade:** a library's own lazy import that decides nothing about the
    load stays kept, as today's `library-imported-first` rows pin. Pin both sides.
  - **Docs:** §7's "is refused, or loads, as a first load in a fresh process would" is made true
    or narrowed in the same commit.
- **F2 (seed prose):**
  - **Property:** every seed and ROADMAP entry this cycle touches states HEAD's behaviour at the
    lines it cites.
  - If this diff now covers the interrupt case, a test pins it and the seed is retired or restated
    accordingly. Which one is build's call, with the GOAL's non-goal in view.

## Human-gate triggers

- **Triggered.** F1 is CONFIRMED against `core/capabilities.py`, a path on § Invariants'
  high-blast-radius list. The maintainer signs off before publish, however later cycles come out.
- **Contract drift, pending the maintainer's confirmation (code-review Step 1.4):** `GOAL.md`
  changed after shape in `d985301`, which added the plan-sign-off clarification on repeatable
  imports. This review graded the GOAL as it stands at HEAD, clarification included.

## Optional completeness sub-pass

Not run.

## Review cycle 2 — changes-requested (2026-11-12)

- **Reviewed commit:** 3f763abcdddeeb741f048eaa7da1bc41b5e14cfc  ·  **Base:** develop
- **Mode:** a fresh blind pass over the full spec-excluded diff, which also checked that cycle 1's
  F1 and F2 are closed as properties. The sequential fallback did not run.
- **Remediation graded:** `7c1ecd8`, `131db35` and `3f763ab` (`3f763ab` changes only `TECH.md`).
- **Convergence:** none. This is the second cycle with CONFIRMED findings against `load()`, so the
  cycle goes to the maintainer before any further build.
- **Maintainer sign-off before publish: required.** See Human-gate triggers.

Evidence paths below are under the worktree's gitignored `.local/review2/` (`reviewer/` for the
blind pass, `orchestrator/` for the orchestrator's runs).

### Verification run

- **The full gate (the profile's `verify`)** ran green on `131db35` (both eras; 4868 passed and
  14 skipped in each era's last suite command). `3f763ab` changes only `TECH.md`, so the source
  tree graded is the one that ran.
- **P1's phase gate at `3f763ab`** (`orchestrator/p1-gate.log`, exit 0):
  - in each era, `test_capabilities.py`, `test_mutations.py` and `test_hygiene.py` passed 2528;
  - the three retry tests (after a failure, after a library module registered, after an
    interrupt) passed 496;
  - `test_startup.py -k capabilit` passed 46 (51 deselected);
  - `tests/mutants.py --self-check` killed all seven of the cycle's cases, each with its expected
    violation, and its three controls reported;
  - `uv lock --check` passed.
- **Reviewer runs, with the output read:**
  - `uv lock --check` passed.
  - `test_capabilities.py` and `test_mutations.py` passed 2386 in each era
    (`reviewer/gate-capabilities-{legacy,modern}.log`).
  - `test_startup.py -k capability` passed 41 (`reviewer/gate-startup-capability.log`).
  - The sandboxed `cluster-mcp --help` printed its usage (`reviewer/gate-help.out`).
- **Drives through `bin/sandbox.sh`:**
  - first loads in a fresh process (the controls) against same-process retries, in new layouts
    (`reviewer/probe_f1_layouts.py`, `reviewer/probe_r2_registrar.py`);
  - develop's loader, run on a copy built with `tests/mutants.py`'s `apply`, against HEAD's
    (`reviewer/probe_key_code.py`);
  - the CLI with a planted distribution, at HEAD and on develop (`reviewer/cli-*`);
  - the re-runs of cycle 1's F1 and F2 probes (`reviewer/rerun-*`).
- **The orchestrator re-ran the key probes for A and B at `3f763ab`.** It got the reviewer's results:
  `orchestrator/a-key-code-{head-raise,head-exit0,develop-raise}.json`,
  `orchestrator/b-r2-registrar-{head,control}.json`, `orchestrator/b-f1-registrar-{head,control}.json`.
- **Mutation** (`method/mutation-testing.md` § When a review is done):
  - **Tier 2:** the reviewer ran, one at a time, the 7 cases anchored on changed code plus
    `capability-other-exception-escapes`. It found all 8 killed for the right reason, and the
    runner's 3 controls passed (`reviewer/mutants-touched.log`).
  - **Tier 3a diff sweep: not run, because no tool is available.** The repo has no
    generated-mutant tool, and none is on the host. This is an unclosed gap, not a pass.
  - **A hand sweep stood in for it.** The reviewer planted 14 mutants of the cycle-2 code, ran with
    2 workers, and ran each mutant against all 500 retry rows (`reviewer/hand_mutants.py`,
    `reviewer/hand-mutants.log`). The results:
    - 7 killed;
    - 1 equivalent (M8);
    - 1 equivalent within the contract (M9: it differs only for a mended capability, which is hot
      reload, a Non-goal);
    - 1 coverage observation (M10, on side (b) only);
    - 4 surviving mutants that break a behaviour HEAD gets right on reachable input (finding C).
- **Spec-id grep** (`reviewer/specid-grep.txt`): no R, P, Q or F ids in `packages/` or `tests/`.
  Ids appear only in seed sketches and in ROADMAP references to `spec/`.
- **Tree:** `git status --porcelain` was empty after the reviewer handed back, and after the
  orchestrator's re-runs. The reviewer mutated no build state. The copy of develop's loader and
  the CLI plants live only under `.local/review2/reviewer/`.

### Cycle 1's findings

- **F1: not closed.**
  - Cycle 1's instances are fixed. `probe_library_stray.py` and `probe_library_stray2.py` now get
    the first load's refusal on the retry (`reviewer/rerun-library-stray{,2}-{head,control}.json`).
  - **Side (a)**, that a retry reaches the verdict a fresh process reaches for every module whose
    import registers a tool, **fails on new layouts.** That is finding B.
  - **Side (b) holds.** A library's lazy import that decides nothing is kept and runs once; the
    `library-imported-first` rows pin it. The one narrowing that §7 and the side-effects seed state
    (an entry the load cannot trace makes it forget every new module) reproduces
    (`reviewer/seed-unaccounted.json`).
  - §7's retry claim is still not true (finding B).
- **F2: closed.**
  - `issues/capability-reload-after-interrupt.md` cites lines that match HEAD, and its "Inside the
    handler" claim reproduces (`reviewer/seed-interrupt-in-cleanup.json`).
  - The case the diff covers is pinned by `test_a_load_retried_after_an_interrupt_is_a_first_load`
    (`reviewer/rerun-interrupt-head.json`).
  - The evidence in `issues/capability-import-side-effects-on-retry.md` reproduces verbatim at
    HEAD (`reviewer/seed-side-effects.json`).
  - The ROADMAP counts check, and every `issues/` file it references exists.

### Requirement → evidence matrix

No R-ID's deliverable is a committed `spec/` artifact, so the blind reviewer graded all six. The
orchestrator re-ran the probes behind A and B.

| R-ID | Implemented by | Verified how | Status |
|------|----------------|--------------|--------|
| R1 | `core/capabilities.py`: `_root`, `_roots`, `_library`, `_accounted`, `_unimport`, `load()`'s handler | suite green in both eras; `reviewer/f1-*-head.json`; `reviewer/r2-registrar-head.json`; the orchestrator's re-runs | ❌ partial: fails on B's layouts |
| R2 | same | `reviewer/r2-registrar-head*.json`; `orchestrator/b-r2-registrar-*.json` | ❌ partial (B) |
| R3 | `installed()` and `create_mcp_server()` go through `load()` | the test's `load`/`installed`/`server` axes; `reviewer/r2-registrar-head-{installed,server}.json` | ✅ for the entry points; inherits R1's and R2's gaps |
| R4 | the refusal is built first and the registry is cut last | `reviewer/gate-startup-capability.log`; `reviewer/key-code-*.json`; `reviewer/cli-*`; `orchestrator/a-key-code-*.json` | ❌ partial: a first-load regression (A) |
| R5 | `test_a_load_retried_after_a_failure_is_a_first_load`: 7 failing kinds, 4 of them failing after the tools module imported | gate logs | ✅ It asserts message equality, and tools by name and identity, each registered once |
| R6 | `tests/mutants.py` `capability-retry-imports-nothing` | `reviewer/mutants-touched.log`; `orchestrator/p1-gate.log` | ✅ killed, with the R1/R2 violation; graded with the tier-3a tool gap |

Unmapped changes:
- `load()` also forgets on a `KeyboardInterrupt`, and a test pins it. A retry after an interrupt is
  a GOAL Non-goal. The change preserves behaviour (the interrupt still propagates), and the
  interrupt seed records it.

### Findings

#### [CRITICAL/CONFIRMED] A · Capability code runs inside the failure handler, outside the refusal conversion: a first-load regression from develop

- **Where:**
  - `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py:292`: `set(sys.modules) - known`.
    The `sys.modules.get(...)` lookups at `:210` and `:236` have the same exposure.
  - `:511-522`: the handler runs `_unimport` in a `finally`, after the `CapabilityLoadError` is
    built.
- **Failure scenario:**
  1. A failing capability's tools module puts into `sys.modules` a key of a `str` subclass. The
     key's hash equals `hash('sys')`, and its `__eq__`, once armed, raises or exits.
  2. The module then raises.
  3. `_unimport`'s set difference compares that key with `'sys'`, which runs the capability's
     `__eq__` inside the handler.
  4. Whatever `__eq__` raises replaces the refusal.
- **Evidence:**
  - Through `load()`, HEAD raises `ValueError` or `SystemExit: 0` in place of a refusal. develop's
    loader refuses both with `cannot load capability zzz-bad: RuntimeError: planted failure`
    (`reviewer/key-code-{head,develop}-*.json`; the orchestrator's re-run is
    `orchestrator/a-key-code-*.json`).
  - Through the sandboxed CLI, HEAD exits **0** with no message, or exits 2. develop exits **5**
    naming the capability (`reviewer/cli-{head,develop}-{exit0,raise}.{err,exit}`).
- **Touches:**
  - § Invariants §7: a capability whose code raises or exits at any point of its load is refused
    naming it.
  - R4.
  - The Non-goal that a load failure still stops startup with exit 5.
  - The new docstrings of `_file` and `_accounted`, which say no capability code runs there.
- **Severity:** CRITICAL by the rubric (a § Invariants violation).
  - Reachability is pathological: it needs an adversarial `sys.modules` key.
  - But the suite already pins the same class, an exception whose `__str__` exits.
- **Not a security weakness:** capability code runs at import anyway and can end the process
  regardless.

#### [HIGH/CONFIRMED] B · F1 is not closed as a property: a retry keeps a library module whose import registered a tool, when the registered function is defined elsewhere

- **Where:** `capabilities.py:240-266` (`_accounted`) and `:293-294`.
- **Cause:** a registration is traced to the module that *defines* the function (its
  `__globals__`), not to the module whose import made the registration. So a new module below a
  regular package the caller imported first is kept, and the retry never runs it again.
- **Failure scenarios** (each control is a first load in a fresh process):
  - **Layouts `registrar`, `registrar-toplevel`, `via-library`, `exec-globals`:**
    - A first load refuses `zzz-bad` (`loading it registered ['zzz_helper_echo'], which are outside
      zzz_bad.tools`).
    - The retry in the same process **loads** it, with `['z_echo']` (`reviewer/f1-*-{control,head}.json`;
      `orchestrator/b-f1-registrar-*.json`).
  - **The GOAL's headline defect returns** (`reviewer/probe_r2_registrar.py`). The clean
    capability's own tool is registered by a library submodule.
    - The first load gives `cannot load capability zzz-bad: RuntimeError: planted failure`.
    - Both retries, with `zzz-bad` and without it, give `cannot load capability aaa-good: its
      instructions list ['a_echo'], which it does not register`.
    - A fresh process loads `aaa-good` with `a_echo`.
    - This reproduces through `load()`, `installed()` and `create_mcp_server()`
      (`reviewer/r2-registrar-head{,-installed,-server}.json`, `orchestrator/b-r2-registrar-*.json`).
- **Touches:**
  - R1, including "SHALL never name a capability that loaded cleanly"; R2; R3.
  - `AGENTS.md:2836-2838` (§7) says a retry "registers again what the failed load registered,
    wherever the module that registered it lies, and is refused, or loads, as a first load in a
    fresh process would". That is false for these layouts.
  - The module docstring at `capabilities.py:19` overstates it the same way.
- **Not in the plan-sign-off exclusion:** every module in these layouts can be imported again; it
  is the load that chooses to keep it.
- **Severity:** HIGH, an R-ID unmet. The §7 overclaim is the same defect seen from the map.

#### [LOW/CONFIRMED] C · Surviving hand mutants of the cycle-2 code, each breaking a behaviour HEAD gets right on reachable input

- **M1 and M2** (`live = set()`; or dropping the "defined in no forgotten module" disjunct).
  - Input: a library submodule registers a function defined in its own package, which existed
    before the load.
  - HEAD keeps R1. Both mutants load the failing capability (`reviewer/m2-reach-*.json`).
- **M11** (`_library` counts packages that are new since the snapshot).
  - Input: the clean capability first imports a fresh package with a submodule.
  - HEAD is correct. The mutant refuses `aaa-good` on the retry, with and without the failing
    capability (`reviewer/m11-reach-*.json`).
- **M13** (no `seen` guard).
  - Input: a self-wrapped tool function.
  - HEAD refuses it. The mutant hangs the first load past a 20 s bound (`reviewer/m13-reach-*.json`).
- **Grading:** tier 3a has no tool, so the reviewer's hand sweep stands as this cycle's
  enumeration. M1 and M2 sit inside B's class and may be subsumed by B's fix. That is the
  maintainer's call at triage.

### Notes (not findings)

- **`issues/capability-import-side-effects-on-retry.md`** says no library that cannot be imported
  twice was reproduced. Stdlib `curses` is one: a second import raises `ImportError: module 'curses'
  can only be loaded once per process`. It is the only such library among 101 installed top-level
  modules (`reviewer/reimport-libs.json`). Cycle 1 recorded the same example for that seed's triage.
- **Sibling overlap:** `capability-tool-objects-inert` also changes `load()`, in the checks that
  decide what a registered entry is. That is the same scan `_accounted` relies on, and A is the same
  family as that cycle's subject. Whichever cycle lands second re-runs the other's probes and
  re-plants the mutation cases anchored in the handler.

### Routing (cycle 2)

Held for the maintainer. The bounded loop has not converged, so this cycle does not route straight
to build. The properties a remediation would carry, over their whole domain:

- **A (R4, §7):**
  - **Property:** nothing a capability left behind runs between the failure and the refusal
    reaching the caller. Whatever forgetting does, the caller gets the refusal that names the
    failing distribution, and the CLI exits 5.
  - **The other side:** forgetting still happens; the A fix must not stop modules being forgotten.
    Pin both sides.
- **B (R1, R2, R3, §7):**
  - **Property:** a retry reaches a fresh process's verdict for every module whose import, directly
    or through what it imported, made the failed load register, whatever package that module sits
    under and wherever the registered function is defined.
  - **The other side** (cycle 1's side (b)): a library's lazy import that registered nothing stays
    kept.
  - **Docs:** §7 and the module docstring are made true, or narrowed to what is true, in the same
    commit.
- **C:**
  - A mutant sweep over every decision in the failure handler's helpers, each mutant run under
    every configuration the GOAL names, with equivalent mutants recorded and why.
  - B's structural fix comes first, since it changes the decisions the sweep would enumerate.

### Human-gate triggers

- **Triggered.** A, B and C are CONFIRMED against `core/capabilities.py`, a path on § Invariants'
  high-blast-radius list. The maintainer signs off before publish, however later cycles come out.
  The trigger from cycle 1 stands.
- **Non-convergence.** Cycle 2 reopened F1's class (B) and found a new first-load regression (A).
  It goes to the maintainer before any further build.
- **Contract drift, pending the maintainer's confirmation (code-review Step 1.4):** `d985301` (the
  plan-sign-off clarification on repeatable imports) is still unconfirmed. This cycle graded the
  GOAL as it stands at HEAD.

## Review cycle 3 — changes-requested (2026-11-13)

- **Reviewed commit:** 43ae93af8409ffbf45bee8e9c94f3f4bbf5afa54  ·  **Base:** develop
- **Mode:** a fresh blind pass over the full spec-excluded diff, at xhigh effort. The sequential
  fallback did not run. The reviewer got GOAL's R-IDs, Non-goals and Clarifications verbatim; the
  template header, Related materials and the sibling-overlap note were left out of its prompt.
- **Remediation graded:** `cde0a99` (the contract change below), `2bcfa50` (the refusal design) and
  `43ae93a` (it changes only `TECH.md`).
- **Contract change, recorded at Step 1.4 as directed by the maintainer:** after review cycle 2 the
  cycle was re-shaped. `cde0a99` re-scopes R2: after a failed load, every later load in the process
  is refused, naming the first failure and saying to restart, and nothing is imported or reloaded.
  R1, R5, the title, the Outcome and the first GOAL-sign-off clarification are amended only as far
  as R2 forces. The earlier post-shape change `d985301` (repeatable imports) lapses with it. Cycle 2's
  pending drift item is closed by this ruling. This cycle grades the GOAL as it stands at HEAD.
- **Maintainer sign-off before publish: required** (Human-gate triggers).

Evidence paths below are under the worktree's gitignored `.local/review3/` (`reviewer/` for the
blind pass, `orchestrator/` for the orchestrator's runs).

### Verification run

- **The full gate (the profile's `verify`)**:
  - ran green on `2bcfa50` in 27:34 at build (`.local/build3/p2-gate.log`, exit 0); `43ae93a`
    changes only `TECH.md` (`git diff --stat 2bcfa50 43ae93a`), so that run stands for HEAD;
  - the reviewer ran it once more at `43ae93a`: exit 0, each era's last suite command 4909 passed
    and 14 skipped, the sandboxed `--help` printed its usage (`reviewer/verify-full.log`).
- **P1's phase gate at `43ae93a`** (`orchestrator/p1-gate.log`, exit 0):
  - in each era, `test_capabilities.py`, `test_mutations.py` and `test_hygiene.py` passed 2569;
  - `test_startup.py -k capabilit` passed 46 in each era;
  - `tests/mutants.py --self-check` killed all eight named cases, each with its expected violation,
    and its three controls reported.
- **Reviewer runs, with the output read:** `test_capabilities.py` and `test_mutations.py` passed
  2427 in each era (`reviewer/narrow-{default,modern}.log`); the runner's touched cases killed in
  both eras (`reviewer/runner-{default,modern}.log`).
- **Drives through `bin/sandbox.sh`:** a retry with the failing capability present, with it
  removed, and with a new capability, on HEAD and on a mutated copy (`reviewer/probe_retry.log`,
  `reviewer/probe_refused_runs.log`); the interrupt seed's Problem (`reviewer/probe_interrupt.log`).
- **Mutation** (`method/mutation-testing.md` § When a review is done):
  - **Tier 2:** the cycle's touched runner cases, all killed in both eras with their expected
    violation.
  - **Tier 3a diff sweep: not run, because no generated-mutant tool is available.** This is an
    unclosed gap, not a pass. A hand sweep stood in for it: 18 mutants across the guard in `load()`,
    the recorded first failure, `_failure`'s safe read and the failure handler's order, each run in
    both eras, kills counted only from the failure message (`reviewer/hand_mutants.py`,
    `reviewer/hand-{default,default-2,modern}.log`). 15 killed; H14 and H15 survive as equivalent
    unless a capability patches the class (already seeded: `issues/capability-refusal-class-patched.md`);
    H2b survives (F-A).
- **Seeds graded as prose:** `issues/capability-reload-after-interrupt.md` cites lines that match
  the code, and its Problem reproduces; `issues/capability-refusal-class-patched.md` matches H14
  and H15; the ROADMAP counts match its headings.
- **Spec-id grep:** no ids in the added source or test lines.
- **Tree:** `git status --porcelain` was empty after the reviewer handed back. The reviewer
  mutated no build state; mutants ran only in scratch copies.

### Cycle 2's findings

- **A** (the failure handler ran a capability's leftovers before the refusal) and **B** (a retry
  that re-imported did not reach a fresh process's verdict) are closed by the contract change:
  a later load imports and runs nothing. The handler now builds the refusal before it cuts the
  registry; H17 (the old order) is killed.
- **C** (surviving mutants in the handler's helpers): the reviewer's sweep over the new decisions
  is above. All but H2b, H14 and H15 are killed.

### Requirement → evidence matrix

| R-ID | Implemented | Verified by (who) |
|---|---|---|
| R1 | Yes | Reviewer: the probe's retry names `bbb-broken`, never `aaa-good`, with the restart text; retry test 480/480 in both eras; H5, H6, H9 killed |
| R2 | Yes | Reviewer: the retry without the broken capability is refused, 0 imports and 0 registrations; H1, H4, H7, H10 killed. Its import/run clause is pinned only through discovery (F-A) |
| R3 | Yes | Reviewer: the retry and own-refusal tests run through `load()`, `installed()` and `create_mcp_server()` |
| R4 | Yes | Reviewer: full verify green; H17 and H8 killed |
| R5 | Yes; its no-import, no-register, no-run asserts lack a control (F-A, LOW) | Reviewer, orchestrator re-read: the planted cases are there; those asserts cannot fail on the inputs planted |
| R6 | Yes | Reviewer and orchestrator: `capability-retry-imports-nothing` is killed with "a load after a failed one was not refused for that failure", both eras |

No R-ID is met by a `spec/` artifact. No scope creep and no operating-manual drift were found.

### Findings

#### [LOW/CONFIRMED, re-graded from MEDIUM] F-A · R5's "a retry imports, registers and runs nothing" checks cannot fail on the inputs the test plants

- **Where:** `tests/test_capabilities.py`, `refused_again` and
  `test_a_load_after_a_failed_one_is_refused_for_it`.
- **Scenario:** both retries plant the clean capability first, and its tools module is already
  imported. A loader that loads what it is given before it refuses fails on that capability at
  once, imports nothing new and runs no planted code, so the asserts pass whether the guard comes
  before the load or after it.
- **Evidence:** H2b, a loader that loads the capabilities it is given and then raises the correct
  refusal, passes every relevant test in both eras: retry test 0/480, own-refusal test 0/48,
  `test_a_failed_load_is_not_cached` 0/4, fresh-process test 0/1 (`reviewer/hand-default-2.log`,
  `reviewer/hand-modern.log`). On H2b a retry with a new capability gets the right message but
  imports `ccc_new`, `ccc_new.capability` and `ccc_new.tools` and leaves `c_echo` registered, and a
  retry whose failing capability sorts first runs its tools code again
  (`reviewer/probe_refused_runs.log`). HEAD does neither. The orchestrator read both logs.
- **Grading:** CONFIRMED, not a coverage observation. R5 states the check, and H2b breaks R2's
  stated behaviour on reachable input. The sibling mutants H2n and H3n are killed only by a
  discovery counter on the default path, so nothing pins the property on the path that is given
  its capabilities. The reviewer graded it MEDIUM: a requirement met but still fragile.
- **Re-graded MEDIUM to LOW by the foreman, as gate judge (2026-11-13).** HEAD behaves as R5
  requires; the reviewer's own probes show it (`reviewer/probe_refused_runs.log`, the real-tree
  rows). What is missing is a control on inputs where a load would show. That is the rubric's
  "missing but non-blocking test coverage of an R-ID", which is LOW. The same re-grade was upheld
  for another cycle's identical finding the same day. The ruling: fix it, don't seed it, since the
  fix is cheap and pins the property properly. It stays CONFIRMED, so the verdict stays
  changes-requested.

#### Coverage observations (already seeded)

- H14 (`vars(...).get('distribution')` to attribute access) and H15 (`args[0]` to `str()`) in
  `_failure` survive; they are equivalent unless a capability patches the class, which
  `issues/capability-refusal-class-patched.md` already records.

### Routing (cycle 3)

To build, for F-A (LOW/CONFIRMED, fixed rather than seeded, by the foreman's ruling). The
property, over its whole domain, both sides:

- **Property (R2, R5):** a refused load imports nothing, registers nothing and runs no capability's
  code, whatever capabilities it is given and whichever entry point makes it, discovered or given
  explicitly. Pin it on inputs where a load would show: a capability no earlier load imported, and
  a failing capability that sorts before the clean one. The pin must kill a loader that loads what
  it is given and then raises the correct refusal (H2b) on every entry point, with the violation
  that names the import, registration or run.
- **The other side:** the refusal still names the first failure, with its cause and the restart
  text, for every input, the new inputs included. It is already pinned; keep it pinned.
- **Not to build:** H14 and H15 are already seeded (`issues/capability-refusal-class-patched.md`).
- **Open gap, unchanged:** the tier 3a diff sweep did not run, because no generated-mutant tool is
  available; the hand sweep above stood in for it.

### Human-gate triggers

- **Triggered (standing).** Cycles 1 and 2 found CONFIRMED findings against
  `core/capabilities.py`, a path on § Invariants' high-blast-radius list. The maintainer pre-approved publish
  for a LOW-only result in this cycle. F-A itself sits in a test file and guards that path.
- **Bounded loop.** This is the third review cycle without a clean pass. The foreman ruled on
  it (the re-grade above) and routed F-A to build.

## Publish sign-off (human gate)

- 2026-11-12, the maintainer: one review; if it finds only LOW, publish `core/capabilities.py`
  without coming back.
- The foreman's re-grade of F-A from MEDIUM to LOW made review cycle 3 LOW-only, and `9c5581f` is
  the fix round that closed it.
