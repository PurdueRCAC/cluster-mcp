---
slug: annotation-check
title: Nothing would catch the next silently wrong annotation
kind: ci
appetite: small
status: blocked
branch: ci/annotation-check
base: develop
current_phase: done
last_updated: '2026-11-10'
phases:
- id: P1
  name: The annotation check and its controls, seen red in each kind of position
  status: done
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
  verify: sh spec/annotation-check/verify/gate.sh P1 && .venv/bin/python -I spec/annotation-check/verify/sweep.py
- id: P2
  name: AGENTS.md names the check, and the full gate in both eras
  status: done
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
  last_reviewed_commit: 672720d3acf65a26fefed4d7a3e3b218416a05ce
  verdict: changes-requested
  blocked_reason: 'review 2: 7 CONFIRMED (1 MEDIUM functional forms read in one context only, 6 LOW: KW_ONLY refused, 39 surviving mutants; tree-test oracle shares the reader); does not converge, escalated'
  cycle: 2
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

## Amendments

- **2026-11-09, rulings at the PLAN/TECH gate.** The foreman accepted deviation rows 1 to 5 of
  PLAN § 3, among them row 4's reading of R2 (a `__main__` module that holds an annotation is
  refused unimported, as one the check cannot evaluate without running the program) and row 5's
  scope-dependence refusal. The maintainer approved the CI cost (2026-11-09): about 5 s per era in
  `suite-legacy-4` and `suite-modern-4`, about 7:27 and 7:38 of the 10:00 budget. A hosted figure
  above 15 s in either job goes back to the maintainer before landing; P1's report records the
  module's local wall time per era as the reference.
- **2026-11-09, P1 build.** The controls' `scratch` fixture forgets the modules loaded from the
  scratch tree (by file, or by the per-case `scratch_` package prefix), not every module imported
  during the case: forgetting a standard-library module a scratch import loaded first would leave a
  second copy of it for later tests. The module holds 112 tests (PLAN § 4's prototype held 87): the
  controls are parametrized per position kind and per evaluation mode.
- **2026-11-09, review cycle 1 remediation** (`REVIEW.md`, changes-requested at `82f5744`; the branch
  rebased onto develop `e378c33` before it). P1 and P2 are reopened: F2 to F5 fall under P1 (R1, R4,
  R5), F1 under P2's `AGENTS.md` entry. They land in one commit (a foreman ruling): F1's entry
  describes the functions F2 to F5 change, so each is checked against the other. P1's `verify:` is
  retuned to run the frozen gate, then `verify/sweep.py`; `gate.sh` and `seen_red.sh` are unchanged.
  P2's full `verify` waits on the foreman's release (the host is at its limit of heavy runs);
  `gate.sh phase` runs now.
  - F1: the `AGENTS.md` § Testing entry credits each named function with only what it does:
    `workspace_violations` returns the refusal lines, `annotation_positions` returns positions and
    imports nothing, an unresolvable name is refused at evaluation, and `type_expression_violations`
    returns reasons and names no position. Each sentence was checked against the code.
  - F2 to F4: `verify/sweep.py`, a mutant sweep of 102 mutants over every decision of the module
    (discovery, the position reader, scope and evaluation, the failed-import fallback, the type
    walk), additive carve-outs included, each run on the whole module in both eras, reading
    committed state. Its record is `verify/sweep-record.md`. The rows that kill the survivors the
    review named: a package `__init__`, a module at depth five, namespace directories, a private
    module, a module that does not parse, the root's own `src/` and a second `members` glob; every
    member checked whatever its place, in fixed directory order (`a-`, `m-`, `z-`), and a member added
    later sorting before and after the first; a `Callable` return and parameters, a `tuple[X, ...]`
    element, a `Concatenate` prefix, a `ParamSpec` generic's list argument, an `InitVar`, a
    subscripted `type` alias; `try`, `except`, `else`, `finally`, `with`, `for`, `while` and `match`
    blocks; aliased functional imports; a failed package `__init__`, whose traceback holds no frame
    of the module checked; and scratch members imported through a symbolic link, so frame and file
    matching is pinned on resolved paths. The review's coverage notes are re-judged and killed:
    M22 by a hint whose walk raises (refused, never passed) and M31 by a module that does not
    parse. Two mutants are recorded equivalent, with the reason in the record: the position filter's
    decorator lines (no decorator holds an annotation) and `Concatenate`'s last-argument check
    (typing refuses to build one with any other last argument).
  - F5: the reader takes every functional class form whose annotations Python keeps:
    `make_dataclass` (positional or `fields=`, pairs and triples), keyword-form `NamedTuple`, and a
    three-argument `type` whose namespace literal holds `__annotations__`, alongside `TypedDict` and
    positional `NamedTuple`, bare, as an attribute or by an imported alias. Each is pinned by a
    planted red row, in both modes.
  - The redundant `local_class` guard in `module_check` is gone: the reader leaves `owner` empty for
    a class defined inside a function, which is what the guard decided.

---

## Phase P1 — The annotation check and its controls, seen red in each kind of position
**Satisfies:** R1, R2, R3, R4, R5, R7 · **Depends on:** —
**Goal:** `tests/test_annotations.py` refuses every kept annotation that does not resolve to a type,
across every workspace member, naming where; green on the tree, red on a slice planted in each kind
of position in the core and in other members.

- [x] Write `tests/test_annotations.py` per PLAN § 2: `workspace_members`, `member_modules`,
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
- [x] The tree test `test_every_kept_annotation_in_the_workspace_is_a_type` (`integration`) runs the
      check in a child, `[str(SANDBOX), sys.executable, '-I', '-c', CHILD, str(ROOT)]`, and asserts
      no violation, a module from every member with a `src/`, and `AUTH_MODES` among the positions.
      The child starts in a session of its own, and a timeout kills its whole process group.
      `test_the_members_are_the_locked_workspace` (`unit`) holds the members to `uv.lock`'s manifest.
- [x] The `unit` controls, under exactly the names `gate.sh`'s `IDS` lists (PLAN § 2, Controls),
      each against scratch workspaces under `tmp_path` with unique package names, forgetting what
      they imported.
- [x] The module carries no spec id, launches only through `bin/sandbox.sh`, never skips, and
      imports no stack module (`test_hygiene.py`'s rails); comments are declarative sentences.
- [x] If the tree test is red on the current tree, STOP: report each flagged annotation (R7).
- **Verify:** `sh spec/annotation-check/verify/gate.sh P1` (about 2 min, 113 s in the plan's dry
  run; it runs `verify/seen_red.sh`, R5's evidence, 35 plants, and prints the module's wall time,
  the figure PLAN § 5 quotes), then `verify/sweep.py` (review cycle 1 remediation: 102 mutants in
  both eras, about 12 min, reading committed state; its record is `verify/sweep-record.md`).
- **Touches:** `tests/test_annotations.py`; `spec/annotation-check/verify/sweep.py` and its record
  (remediation).

## Phase P2 — AGENTS.md names the check, and the full gate in both eras
**Satisfies:** R6, R7 · **Depends on:** P1
**Goal:** the operating manual describes the new check, the deferral ledger is clean, and the
profile's full `verify` passes with the check in its fourth command of each era.

- [x] Add a `tests/test_annotations.py` (`unit`, `integration`) entry to AGENTS.md § Testing, beside
      `tests/test_auth_modes.py`'s: what it checks, its check functions (`workspace_violations`,
      `annotation_positions`, `type_expression_violations`), why the tree check runs in a fresh
      interpreter, and that `AUTH_MODES`'s exact-shape pin stays. Point to rules; don't restate
      them. Leave § Factory untouched (`gate.sh static` compares it).
- [x] Deferral ledger: walk P1's and this phase's bodies, and PLAN, for every deferral (the
      phrases `code-plan` Step 6.7 names, which `gate.sh` → `ledger` greps for); each needs an
      `issues/` seed, pre-shaped from the KB's `ISSUE.md`, and a `ROADMAP.md` entry. The plan
      files none.
- [x] Run `sh spec/annotation-check/verify/gate.sh phase` first (fast), then the full gate in the
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
