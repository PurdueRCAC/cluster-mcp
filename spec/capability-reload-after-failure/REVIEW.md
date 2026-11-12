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
