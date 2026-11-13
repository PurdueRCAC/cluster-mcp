---
slug: readme-front-door
title: The README is a front door
kind: docs
appetite: small
status: done
branch: docs/readme-front-door
base: develop
current_phase: done
last_updated: '2026-11-12'
phases:
- id: P1
  name: The pages, one level down, and the tests that read them
  status: done
  satisfies:
  - R1
  - R2
  - R3
  - R4
  - R5
  - R6
  - R7
  - R9
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: export UV_PYTHON=3.14 && uv run -q --with pyyaml python -I spec/readme-front-door/verify/docs-gate.py controls readme pages facts packages paths && uv run pytest -q tests/test_ssh_liveness.py::test_liveness_texts_state_the_monitor tests/test_ssh_exec.py::test_content_texts_state_the_sftp_route tests/test_ssh_exec.py::test_separation_texts_state_the_remote_rc_exception tests/test_deprecation_window.py tests/test_registry.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_liveness.py::test_liveness_texts_state_the_monitor tests/test_ssh_exec.py::test_content_texts_state_the_sftp_route tests/test_ssh_exec.py::test_separation_texts_state_the_remote_rc_exception tests/test_deprecation_window.py tests/test_registry.py
- id: P2
  name: AGENTS.md § Documentation and its pointers, the ledger, and the full gate
  status: done
  satisfies:
  - R8
  - R9
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: export UV_PYTHON=3.14 && uv run -q --with pyyaml python -I spec/readme-front-door/verify/docs-gate.py controls all prepush && uv lock --check && uv run pytest -q tests/test_ssh_exec.py -k silent && uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k silent && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && bin/sandbox.sh uv run cluster-mcp --help
review:
  last_reviewed_commit: ''
  verdict: none
  blocked_reason: ''
  cycle: 0
---

# TECH.md — The README is a front door

The **context engine and finite-state machine** for building this feature. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/readme-front-door/TECH.md`); the per-phase
checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **The gate:** [`verify/docs-gate.py`](verify/docs-gate.py) and the fact map
  [`verify/facts.yaml`](verify/facts.yaml), frozen with this plan. No `research/` (`skip research`).

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

---

## Phase P1 — The pages, one level down, and the tests that read them
**Satisfies:** R1, R2, R3, R4, R5, R6, R7, R9 · **Depends on:** —
**Goal:** `README.md` is the short front door, the three docs pages and `SECURITY.md` hold
everything it no longer does, the package READMEs point at their pages, and the two tests read
`docs/core/README.md`. R4–R6 are graded against the committed fact map in `spec/`, which
`code-review`'s blind reviewer cannot see: the orchestrator grades them (and this cycle's review is
the maintainer's read, GOAL Review mode).

- [x] Write `docs/core/README.md`, `docs/slurm/README.md` and `docs/rcac/README.md` to PLAN § 2's
      outline: H1, lead, `## Tools` (one list line per tool, the baseline's line), `## What it needs
      on the cluster`, `## How it behaves`; the core's `## Install`; the RCAC page's
      `## RCAC documentation`. Every fact `verify/facts.yaml` homes on a page goes there with its
      phrases verbatim, all of one fact's phrases inside one level-2 section, and every baseline
      code line it maps as a line of the page. Every figure line of
      the core page is a list item or a table row. Links into the repository are relative
      (`../../issues/…`).
- [x] Rewrite `README.md` to PLAN § 2: the opening (two or three sentences), `## Quick Start`,
      `## Capabilities`, `## Run modes`, `## Upgrading from rcac-mcp` (byte for byte),
      `## Development`, `## License`; at most 120 lines; no figure outside § Upgrading.
- [x] `SECURITY.md`: the overview says how to run the service, the three modes with the README's
      one-line descriptions inside it; add `## Hosted HTTP server` with the three baseline recipes
      under `### Basic HTTP Server`, `### With JWT Authentication`, `### Docker Compose with TLS`;
      every baseline line outside the overview (lines 6–14) kept word for word.
- [x] Each package README links `https://github.com/PurdueRCAC/cluster-mcp/blob/main/docs/<member>/README.md`
      in place of its "full documentation is the repository's README" line.
- [x] Repoint `tests/test_ssh_liveness.py` (one read) and `tests/test_ssh_exec.py` (two reads):
      `(root / 'README.md')` becomes `(root / 'docs' / 'core' / 'README.md')`; the dict label may
      name the file; nothing else changes (comments aside). The comment above `EXPECTED_TOOLS` in
      `tests/test_registry.py` names its member's docs page.
- [x] If a phrase in the fact map cannot be kept in a short sentence, or a verbatim line cannot be
      kept, stop and report it: the map and the gate are frozen with the plan.
- [x] Stage everything, then run the frontmatter `verify:`.
- **Verify:** the gate's `controls readme pages facts packages paths`, then the five page-reading
  test targets in both eras (about 20 s each).
- **Touches:** `README.md`, `SECURITY.md`, `docs/{core,slurm,rcac}/README.md`,
  `packages/*/README.md`, `tests/test_ssh_liveness.py`, `tests/test_ssh_exec.py`,
  `tests/test_registry.py`.

## Phase P2 — AGENTS.md § Documentation and its pointers, the ledger, and the full gate
**Satisfies:** R8, R9 (and R1–R7 re-graded on the final tree by `all`) · **Depends on:** P1
**Goal:** `AGENTS.md` states the rule this cycle followed and points every reference to moved text
at its new home; the final tree passes every gate mode and the profile's full `verify`.

- [x] Add `## Documentation` after § Packaging, to PLAN § 2 (what each page holds; short sentences;
      a limit only where a user would otherwise get hurt, in one sentence linking its seed; figures
      in a list or table on the docs page, none in the README; edge cases in `issues/` or
      `AGENTS.md`; the tests that read a page).
- [x] §9's same-commit bullet names `docs/<member>/README.md`, the tool's docs page.
- [x] Repoint the moved references PLAN § 2 lists (§ Testing's `EXPECTED_TOOLS`, `rcac-docs-mcp`,
      SFTP-route and liveness-figure notes; §3's separation exception; § Packaging's Docker Compose
      pointer and its same-commit clause, naming `docs/<member>/README.md`; the release recipe's
      install note); § Repository map names `docs/`. Keep `EXCEPTION`, `CONTENT_RULE` and `SECTION_2_TRANSFER` where §2 and §3
      state them.
- [x] The ledger (`code-plan` Step 6.8): walk P1's and P2's bodies, PLAN.md and the branch's commit
      bodies for a deferral; each names an `issues/` seed with a `ROADMAP.md` entry (`prepush`
      checks it). This plan files no seed; the one overlapping seed, `issues/rename-in-docs.md`,
      stays as it is (Q4).
- [x] Stage everything, then run the frontmatter `verify:` through `run_in_background`: `controls`,
      `all`, `prepush`, then the profile's full `verify`, both eras.
- **Verify:** the gate's `controls all prepush`, then the profile's `verify` verbatim.
- **Touches:** `AGENTS.md`.

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
