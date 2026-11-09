---
slug: annotation-check
title: Nothing would catch the next silently wrong annotation
kind: ci
appetite: small
status: in_progress
branch: ci/annotation-check
base: develop
current_phase: P1
last_updated: '2026-11-09'
phases:
- id: P1
  name: The annotation check and its controls, seen red in each kind of position
  status: pending
  satisfies:
  - R1
  - R2
  - R3
  - R4
  - R5
  - R7
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/annotation-check/verify/gate.sh P1
- id: P2
  name: AGENTS.md names the check, and the full gate in both eras
  status: pending
  satisfies:
  - R6
  - R7
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/annotation-check/verify/gate.sh P2
review:
  last_reviewed_commit: ''
  verdict: none
  blocked_reason: ''
  cycle: 0
---

# TECH.md — Nothing would catch the next silently wrong annotation

The **context engine and finite-state machine** for building this feature. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/annotation-check/TECH.md`); the
per-phase checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** none (lean path); the prototype findings are in PLAN § 4.

## Frontmatter field reference

As the KB template words it (`$KB/skill/_templates/TECH.md` → Frontmatter field reference).

## Conventions (apply to every phase)

- Commit conventions, code style, and load-bearing invariants come from the repo's `AGENTS.md` — it
  is the constitution. Walk the sections of its § Invariants that this change touches; that is the
  curated footgun checklist.
- One phase per `code-build` invocation by default; one atomic commit containing **both** the code and
  the `TECH.md` state change. The branch commit subject is code-build's (`$KB/skill/code-build.md` →
  Step 6), not restated here; branch commits are squashed away at `code-publish` per the profile's
  `landing`. Trailers follow the profile's `branch commits`.
- The last phase carries the standing last-phase items: the deferral ledger (`code-plan` Step 6.8),
  and every item the previous cycle's last phase carried for a project-level obligation. This repo
  carries none beyond the ledger and the profile's full `verify`.
- A PR body (when the profile's `landing` opens one) ends with an attribution naming the actual
  harness, model, and variant.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`): the
  help text, docs, or generated files it names change **in the same commit**.
- **Footprint (both phases).** Only `tests/test_annotations.py`, `AGENTS.md` outside § Factory,
  `spec/annotation-check/`, and a deferral seed with its `ROADMAP.md` entry may change
  (`gate.sh static`). Nothing under `packages/` (R7), no lock or `pyproject.toml`, no workflow, no
  fixture, no `bin/`, and neither `tests/mutants.py` nor `tests/test_hygiene.py` (sibling cycles).
  If the check flags an annotation on the tree, STOP and report it (R7): never change it here.

---

## Phase P1 — The annotation check and its controls, seen red in each kind of position
**Satisfies:** R1, R2, R3, R4, R5, R7 · **Depends on:** —
**Goal:** `tests/test_annotations.py` refuses every kept annotation that does not resolve to a type,
across every workspace member, naming where; green on the tree, red on a slice planted in each kind
of position in the core and in other members.

- [ ] Write `tests/test_annotations.py` per PLAN § 2: `workspace_members`, `member_modules`,
      `annotation_positions`, `type_expression_violations`, the evaluation through
      `typing.get_type_hints` on a one-string holder, the import step (`__main__` refused unimported
      when annotated, `__file__` equality, the failed-import fallback), `workspace_violations`, and
      the one-line refusal format `{module}:{line}: {qualified name}: {text!r}: {why}`. Include
      every fold of the adversarial review (PLAN § 4a): the scope-dependence refusal, identity
      comparisons and per-position validator exceptions, qualifiers by kind of position, `type`
      alias values and `NewType` supertypes walked, slices in `Annotated` metadata refused,
      function-local classes and functional `TypedDict`/`NamedTuple` read, `if TYPE_CHECKING:`
      bodies skipped, a member without `src/` refused, the class lookup checked by `__qualname__`
      and `__module__`, and the failed-import fallback's innermost statement, resolved paths and
      metaclass namespaces.
- [ ] The tree test `test_every_kept_annotation_in_the_workspace_is_a_type` (`integration`) runs the
      check in a child, `[str(SANDBOX), sys.executable, '-I', '-c', CHILD, str(ROOT)]`, and asserts
      no violation, a module from every member with a `src/`, and `AUTH_MODES` among the positions.
      The child starts in a session of its own, and a timeout kills its whole process group.
      `test_the_members_are_the_locked_workspace` (`unit`) holds the members to `uv.lock`'s manifest.
- [ ] The `unit` controls, under exactly the names `gate.sh`'s `IDS` lists (PLAN § 2, Controls),
      each against scratch workspaces under `tmp_path` with unique package names, forgetting what
      they imported.
- [ ] The module carries no spec id, launches only through `bin/sandbox.sh`, never skips, and
      imports no stack module (`test_hygiene.py`'s rails); comments are declarative sentences.
- [ ] If the tree test is red on the current tree, STOP: report each flagged annotation (R7).
- **Verify:** `sh spec/annotation-check/verify/gate.sh P1` (about 2 min, 113 s in the plan's dry
  run; it runs `verify/seen_red.sh`, R5's evidence, 35 plants, and prints the module's wall time,
  the figure PLAN § 5 quotes).
- **Touches:** `tests/test_annotations.py`.

## Phase P2 — AGENTS.md names the check, and the full gate in both eras
**Satisfies:** R6, R7 · **Depends on:** P1
**Goal:** the operating manual describes the new check, the deferral ledger is clean, and the
profile's full `verify` passes with the check in its fourth command of each era.

- [ ] Add a `tests/test_annotations.py` (`unit`, `integration`) entry to AGENTS.md § Testing, beside
      `tests/test_auth_modes.py`'s: what it checks, its check functions (`workspace_violations`,
      `annotation_positions`, `type_expression_violations`), why the tree check runs in a fresh
      interpreter, and that `AUTH_MODES`'s exact-shape pin stays. Point to rules; don't restate
      them. Leave § Factory untouched (`gate.sh static` compares it).
- [ ] Deferral ledger: walk P1's and this phase's bodies, and PLAN, for every deferral (the
      phrases `code-plan` Step 6.7 names, which `gate.sh` → `ledger` greps for); each needs an
      `issues/` seed, pre-shaped from the KB's `ISSUE.md`, and a `ROADMAP.md` entry. The plan
      files none.
- [ ] Run `sh spec/annotation-check/verify/gate.sh phase` first (fast), then the full gate in the
      background (the profile's `verify`, about 26 min).
- **Verify:** `sh spec/annotation-check/verify/gate.sh P2` (static, docs, ledger, then the profile's
  full `verify`, read from AGENTS.md § Factory at run time). R6's CI-budget clause is graded at
  publish on the cycle branch's CI run, not here.
- **Touches:** `AGENTS.md` (§ Testing only).

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[ci]` commit; stop and report.
