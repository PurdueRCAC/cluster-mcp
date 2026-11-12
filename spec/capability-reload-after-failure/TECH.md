---
slug: capability-reload-after-failure
title: A capability load retried after a failure loads the healthy ones and names the broken one
kind: fix
appetite: small
status: in_progress
branch: fix/capability-reload-after-failure
base: develop
current_phase: P2
last_updated: '2026-11-12'
phases:
- id: P1
  name: A failed load forgets the modules it imported, and a retry is a first load
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
  verify: export UV_PYTHON=3.14 && uv run pytest -q tests/test_capabilities.py tests/test_mutations.py tests/test_hygiene.py && uv run pytest -q tests/test_capabilities.py::test_a_load_retried_after_a_failure_is_a_first_load && uv run pytest -q tests/test_startup.py -k capabilit && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_capabilities.py tests/test_mutations.py tests/test_hygiene.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_startup.py -k capabilit && uv run python tests/mutants.py --self-check capability-scratch-per-capability capability-refusal-keeps-registry capability-other-exception-keeps-registry capability-load-failure-passes-re-raises
- id: P2
  name: The mutation case for today's retry, the ledger, and the full gate
  status: pending
  satisfies:
  - R6
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: export UV_PYTHON=3.14 && uv run python tests/mutants.py --self-check capability-retry-imports-nothing capability-scratch-per-capability capability-refusal-keeps-registry capability-other-exception-keeps-registry capability-load-failure-passes-re-raises && uv lock --check && uv run pytest -q tests/test_ssh_exec.py -k silent && uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k silent && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && bin/sandbox.sh uv run cluster-mcp --help
review:
  last_reviewed_commit: ''
  verdict: none
  blocked_reason: ''
  cycle: 0
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
- **Verify:** both eras of `test_capabilities.py`, `test_mutations.py` and `test_hygiene.py`; the
  new test by node id; `test_startup.py -k capabilit` (the CLI path still stops with exit 5) in
  both eras; the four re-planted mutation cases with the runner's controls.
- **Touches:** `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`,
  `tests/test_capabilities.py`, `tests/mutants.py`, `AGENTS.md`.

## Phase P2 — The mutation case for today's retry, the ledger, and the full gate
**Satisfies:** R6 · **Depends on:** P1
**Goal:** a mutation case plants today's retry behaviour and R5's test kills it, naming the
contract; every deferral is recorded; the profile's full `verify` is green.

- [ ] `tests/mutants.py`: `capability-retry-imports-nothing`, `file=LOADER`, targets every row
      of `test_a_load_retried_after_a_failure_is_a_first_load` beside the `both` member set
      (`entry` × `kind` × `layout`, 84 rows), `why` "a load retried after a failure is not a first
      load". It replaces the inner `try:` / `_unimport(…)` / `finally:` with the bare cut-back.
      The mutation gate is graded per `method/mutation-testing.md` § When a review is done, in the
      operator's KB.
- [ ] **Deferral ledger** (last-phase item): walk P1's and P2's bodies, PLAN §§ 4–5 and Notes, and
      the branch's commit bodies for "do not fix here", "known limitation", "left as a follow-up",
      "deferred", "limit" and "not covered"; each must have an `issues/` seed and a `ROADMAP.md`
      entry. Expected: `issues/capability-import-side-effects-on-retry.md`, filed by the plan with its
      `ROADMAP.md` entry (Q1's remainder), and nothing new. The interrupt windows PLAN Notes names
      belong to the existing `issues/capability-reload-after-interrupt.md`, and PLAN § 5's other
      risks are review risks, not deferrals. An unrecorded deferral fails the phase.
- [ ] Standing last-phase items: the previous cycle's last phase carried no project-level
      obligation beyond the ledger (no `## Times` quote in this repo).
- [ ] Stage, then run the `verify:`.
- **Verify:** the new case and the four re-planted ones with the runner's controls, then the
  profile's full `verify`, both eras and the sandboxed `cluster-mcp --help`.
- **Touches:** `tests/mutants.py`.

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
