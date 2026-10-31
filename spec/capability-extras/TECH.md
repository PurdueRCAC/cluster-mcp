---
slug: capability-extras
title: Capabilities you don't have shouldn't be tools you see
kind: feature
appetite: big
status: in_progress
branch: feature/capability-extras
base: develop
current_phase: P2
last_updated: '2026-10-31'
phases:
- id: P1
  name: The capability contract; Slurm and RCAC register through the entry-point group
  status: done
  satisfies:
  - R2
  - R5
  - R6
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/capability-extras/verify/p1.sh
- id: P2
  name: The storage resource belongs to the RCAC member; no core module names a member
  status: pending
  satisfies:
  - R3
  - R7
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/capability-extras/verify/p2.sh
- id: P3
  name: A capability that fails to load stops startup, naming its distribution
  status: pending
  satisfies:
  - R8
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/capability-extras/verify/p3.sh
- id: P4
  name: The extras, the core alone, and the compat root that keeps every tool
  status: pending
  satisfies:
  - R1
  - R4
  - R5
  - R9
  - R10
  depends_on:
  - P3
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/capability-extras/verify/p4.sh
- id: P5
  name: The whole cycle's gates on the finished tree, the recipe on this head, the deferral ledger
  status: pending
  satisfies:
  - R6
  - R9
  - R10
  depends_on:
  - P4
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/capability-extras/verify/p5.sh
review:
  last_reviewed_commit: ''
  verdict: none
  blocked_reason: ''
  cycle: 0
---

# TECH.md — Capabilities you don't have shouldn't be tools you see

The **context engine and finite-state machine** for building this feature. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/capability-extras/TECH.md`); the
per-phase checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** [`research/00-digest.md`](research/00-digest.md) + briefs.

## Frontmatter field reference

- `status` (top): `planned | in_progress | blocked | in_review | done` (`done` is stamped by
  `code-publish` after confirmation, just before landing — the terminal state of the retained record)
- `appetite`: `small | big` — caps phase count and build-iteration budget (circuit breaker).
- `branch`, `base`: the cycle's branch (prefix per GOAL `kind`, from the profile's `branches`) and the
  profile's `base`.
- phase `status`: `pending | in_progress | done | blocked`
- `satisfies`: GOAL R-IDs this phase delivers (traceability anchor for `code-review`).
  **Artifact-deliverable R-IDs.** Some requirements are met by a *committed document* — a research
  audit, a protocol doc, an assessment — not by CLI-observable behaviour. Attach such an R-ID to the
  phase that produces and commits the artifact, and give that phase a content `verify:`
  (`test -f …`, a `grep -q` for the sections that must exist) rather than forcing a CLI drive.
  **Say so in the phase body**, because it changes who can grade it: `code-review` blinds its reviewer
  to all of `spec/`, so an R-ID whose evidence lives there is graded by the *orchestrator*, not the
  blind reviewer. Naming it in `TECH.md` is what lets the review skill route it correctly instead of
  reporting an unverifiable requirement.
- `depends_on`: phase ids that must be `done` first (a phase is actionable only when met).
- `parallel`: `true` only for genuinely independent, non-coupled work (docs, tests, isolated leaf
  modules). Any phase touching the profile's `coupled core` is always `false`.
- `hammerable`: `false` marks a correctness/security phase that scope-hammering must **never** cut.
- `hill`: `uphill` (still figuring it out) → `crest` (unknowns resolved) → `downhill` (just
  executing). A phase stuck `uphill` across builds is a raised hand → escalate to the human.
- `attempts`: durable failed-verify counter (absent = 0), bumped by `set_phase.py --phase P<n>
  --record-attempt` on every red verify gate; `next_phase.py` warns at ≥3 — the circuit breaker
  runs on this file, not on session memory.
- `verify`: the exact command that proves the phase (prefer driving the real CLI, not just tests —
  wrap CLI drives in the profile's `throwaway environment` helper, `<helper> sh -c "…"`, so they hit
  a disposable instance, never the developer's real data). A gate carrying `$( )` or quoting the
  calling shell would mangle is set with `set_phase.py --verify-file PATH`, not `--verify`.
- `review.cycle`: completed review passes, auto-incremented by every `set_phase.py --verdict …`;
  REVIEW.md's "Cycle {n}" mirrors it and the ≤3-cycle bound is graded against it. `--verdict approved`
  also clears `review.blocked_reason` unless one is passed explicitly.

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

**This cycle's own conventions.**

- Gates live in `spec/capability-extras/verify/`: `p<n>.sh [phase|mutants|full|…]`, each mode
  runnable alone (a mutant run targets only its phase's checks). The design they pin (the
  `Capability` fields, `installed()`, `create_mcp_server(..., capabilities=...)`, the message
  `cannot load capability <dist>: `, the entry points `<name> = cluster_mcp.<name>.capability:CAPABILITY`,
  orders 100 and 900) is PLAN §2; a gate is amended only with the design, never to pass.
- Each phase keeps true the AGENTS.md and README.md text its change touches (§ Conventions: one
  commit). R10's "same commit" is the cycle's squash landing, which carries every phase.
- New tests carry `@mark.unit` or `@mark.integration`; every process launch goes through
  `bin/sandbox.sh`; new stdio drives set `FASTMCP_CHECK_FOR_UPDATES=off`; no comment or test name
  carries a spec id (`tests/test_hygiene.py`).
- A test function or mutation case that disappears fails `baseline.sh`, unless
  `verify/retired.txt` names it with its reason (commit body says it too).
- Mutation cases are added to `tests/mutants.py` with ids exactly as the gates name them; a case
  anchored on a moved line is re-anchored with its id and `why` kept.
- Run `uv sync --locked` after any `pyproject.toml` edit: entry points reach an editable install
  only through a sync.

---

## Phase P1 — The capability contract; Slurm and RCAC register through the entry-point group
**Satisfies:** R2, R5, R6 · **Depends on:** —
**Goal:** the core composes tools and base instructions from the capabilities loaded through
`cluster_mcp.capabilities` at startup; with every member installed the surface is today's.

- [x] `C/capabilities.py` (new): `GROUP`, `Capability`, `Loaded`, `CapabilityLoadError`, `load()`,
      `installed()`, `composed()` as PLAN §2.1 — the type checks, a failing `ep.load()` or tools
      import, tool attribution by module, the instructions-list-exactly-its-tools check, the
      duplicate tool and capability-name checks, the rollback, the message shape. (Resource checks
      land in P2; startup wiring in P3.)
- [x] `C/tools/__init__.py`: drop the two member imports; `CORE_TOOLS` and `CLOSING_TOOLS`.
- [x] `C/server.py`: drop the member imports and `SERVER_INSTRUCTIONS`; `base_instructions()`;
      `create_mcp_server(..., capabilities=None)` registering tools and resources in today's listing
      order (PLAN §2.3: load order, `CLOSING_TOOLS` last; primaries then aliases). Capability
      resources are served from this phase (the planted capability carries one); the core's storage
      entry stays until P2.
- [x] `S/capability.py`, `RC/capability.py` (orders 100, 900; no resources yet); the entry point in
      each member's `pyproject.toml`; `uv sync --locked`; docstrings of the two member
      `instructions.py` (texts untouched).
- [x] `tests/conftest.py` loads once; `tests/test_capabilities.py` with the P1 ids `p1.sh` names;
      the seven `SERVER_INSTRUCTIONS` importers, `test_instructions.py` (members from the loaded
      capabilities), `test_registry.py` re-pointed; mutants re-anchored; new cases
      `capability-order-from-discovery` (the composer keeps discovery order),
      `capability-tools-unfiltered` (the server registers all of `TOOL_REGISTRY`, ignoring the given
      set), `core-imports-member-by-name` (a member import back in `core/tools/__init__.py`),
      `capability-duplicate-tool-allowed` (the duplicate-tool check removed),
      `capability-tools-import-swallowed` (a failing tools import skipped) and
      `capability-instructions-unchecked` (the text check removed).
      *Amended at build:* `core-imports-member-by-name` needs a target this phase, so
      `test_core_imports_no_member` (named by `p2.sh`) lands here, its AST scan skipping
      `C/resources.py`, whose storage handler still imports the RCAC member's helper until P2.
- [x] AGENTS.md: §7 and §9 rewritten (PLAN §3), the footgun and repository-map rows for
      `tools/__init__.py` and `server.py`, the high-blast-radius list widened with
      `core/capabilities.py` and both `capability.py` files.
- **Verify:** `sh spec/capability-extras/verify/p1.sh`.
- **Touches:** `C/capabilities.py`, `C/tools/__init__.py`, `C/server.py`, `S/`, `RC/`, both member
  `pyproject.toml`, `uv.lock` (if it moves), `tests/`, `AGENTS.md`.

## Phase P2 — The storage resource belongs to the RCAC member; no core module names a member
**Satisfies:** R3, R7 · **Depends on:** P1
**Goal:** `cluster://storage` and its `rcac://storage` alias are the RCAC capability's, served only
with it; the core's resources and open set are its context URIs; the core names no member.

- [ ] `C/resources.py`: `legacy_aliases()`; the core's registry is the context entry and its alias;
      the storage entry and its member import go; `OPEN_RESOURCES` unchanged.
- [ ] `RC/resources.py` (new): the storage handler and entry, moved verbatim; `RC/capability.py`
      carries `(STORAGE, *legacy_aliases((STORAGE,)))`.
- [ ] `C/capabilities.py`: the resource checks (a dict with `str` `uri`, `name`, `description`, a
      callable `handler`, `executor` exactly `True`; URI unique against the core and earlier
      capabilities).
- [ ] `tests/test_capabilities.py::test_core_imports_no_member` stops skipping `C/resources.py`,
      and AGENTS.md § Testing's note of the skip goes with it (amended at P1's build).
- [ ] Tests: `test_storage_resource.py` reads served resources from composed servers;
      `tests/test_capabilities.py` P2 ids; mutants re-anchored; new cases
      `storage-resource-unconditional` (the core registers the storage entry again) and
      `capability-resource-open-allowed` (the executor check removed).
- [ ] AGENTS.md §8 (PLAN §3, deviation row 1) and the `resources.py` repository-map row.
- **Verify:** `sh spec/capability-extras/verify/p2.sh`.
- **Touches:** `C/resources.py`, `C/capabilities.py`, `C/server.py`, `RC/`, `tests/`, `AGENTS.md`.

## Phase P3 — A capability that fails to load stops startup, naming its distribution
**Satisfies:** R8 · **Depends on:** P2
**Goal:** `run()` loads before the mode ladder; a failure is reported as an SSH connect failure is
(stderr once, the stdio error answer until EOF) and exits 5; `--help` and `--version` unaffected.

- [ ] `C/__init__.py` `run()`: `installed()` after the `--generate-token` branch, before
      `_resolve_exec_mode()`; `CapabilityLoadError` → `_report_startup_failure` → `StartupFailure`.
      `_resolve_exec_mode()` is not edited (§4, human gate).
- [ ] `C/startup.py` docstring; AGENTS.md §4's startup-refusal bullet and §7 name the message.
- [ ] Tests: `tests/test_startup.py` P3 ids (planted dist-infos prepended to `PYTHONPATH`, both
      eras, the raw wire; `run_app` for the order; an HTTP start that exits 5 before binding); the
      `rcac-mcp` command once. New cases
      `capability-load-failure-swallowed` (the loader skips a failing entry point) and
      `capability-load-after-ladder` (the load moved after `_resolve_exec_mode()`).
- **Verify:** `sh spec/capability-extras/verify/p3.sh`.
- **Touches:** `C/__init__.py`, `C/startup.py`, `C/capabilities.py` (if a check needs it), `tests/`,
  `AGENTS.md`.

## Phase P4 — The extras, the core alone, and the compat root that keeps every tool
**Satisfies:** R1, R4, R5, R9, R10 · **Depends on:** P3
**Goal:** the members become the core's extras; a bare core install starts and serves the core;
the root installs every capability; the docs name the extras.

- [ ] `packages/cluster-mcp/pyproject.toml` extras; root `dependencies = ["cluster-mcp[slurm,rcac]"]`
      (header comment, description); `uv lock`; `uv sync --locked` — one commit with the docs below.
- [ ] `tests/test_core_only.py` (`integration`; session-scoped editable core-only environment under
      the sandbox, `VIRTUAL_ENV` dropped, offline); `harness.py` gains a resources listing for stdio
      drives if the test needs it; `tests/test_packaging.py` pins (the extras, the workspace
      sources, the root's `cluster-mcp[rcac,slurm]`, `Provides-Extra`).
- [ ] README.md: the intro, Quick Start (`cluster-mcp[slurm,rcac] @ git+…#subdirectory=packages/cluster-mcp`,
      one `args` element), the install note, the inventory headings naming `[slurm]` and `[rcac]`
      (and that `[rcac]` goes with `[slurm]`), development `uv sync`; the three member READMEs;
      the Dockerfile comment.
- [ ] AGENTS.md § Packaging, § Project and § Commands where they say the core carries the members,
      the release recipe's `post_verify` and its `install-probe` and `ci-mirror-no-index` caveats
      (PLAN §2.4).
- **Verify:** `sh spec/capability-extras/verify/p4.sh`.
- **Touches:** the four `pyproject.toml`, `uv.lock`, `README.md`, `packages/*/README.md`,
  `Dockerfile`, `AGENTS.md`, `tests/`.

## Phase P5 — The whole cycle's gates on the finished tree, the recipe on this head, the deferral ledger
**Satisfies:** R6, R9, R10 · **Depends on:** P4
**Goal:** every independent check passes on the finished tree, the release recipe's offline gate
steps pass on this head, and every deferral has its record.

- [ ] Run `p5.sh phase` and fix what it finds in the phase that owns it (amend this file and say so
      in the commit body).
- [ ] The deferral ledger: walk every earlier phase body, PLAN.md and REVIEW.md (if any) for "do not
      fix here", "known limitation", "deferred", "follow-up", "out of scope"; each must name an
      `issues/{slug}.md` (pre-shaped from the KB `ISSUE.md` template) with its `ROADMAP.md` entry
      (the gitignored security lane instead for a sensitive item). `p5.sh ledger`
      checks the links; the walk is this item's.
- [ ] `p5.sh recipe`: build, `twine check --strict`, sdist hygiene on this head.
- [ ] `verify/retired.txt` empty, or each line justified in its phase's commit body.
- **Verify:** `sh spec/capability-extras/verify/p5.sh`.
- **Touches:** whatever a failing check names; `issues/`, `ROADMAP.md` only for a deferral.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[{category}]` commit; stop and report.
