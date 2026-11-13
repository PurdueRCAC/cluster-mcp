---
slug: annotation-check
title: Nothing would catch the next silently wrong annotation
kind: ci
appetite: small
status: in_review
branch: ci/annotation-check
base: develop
current_phase: done
last_updated: '2026-11-13'
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
  verify: sh spec/annotation-check/verify/gate.sh P1 && .venv/bin/python -I spec/annotation-check/verify/sweep.py && .venv/bin/python -I spec/annotation-check/remediation/F6-F8-review2.py && .venv/bin/python -I spec/annotation-check/remediation/F9-review3.py
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
  last_reviewed_commit: 011c31fe40cd115111ba1f4a22bf62bdd7831fcb
  verdict: changes-requested
  blocked_reason: 'review 3: 4 CONFIRMED (2 MEDIUM: oracle false red on valid TypedDict inheritance and renamed functional forms; def __annotate__ passes unread; 2 LOW: 6 sweep survivors, seed misstates routes); loop bound reached, escalated'
  cycle: 3
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
- **2026-11-12, review cycle 2 remediation** (`REVIEW.md`, changes-requested at `672720d`). A
  foreman ruling scopes it to four fixes and one seed: N1, N2, the `AGENTS.md` sentence N1 names, and
  the tree test's oracle (N3's root cause); N3 to N7's other survivors are seeded. P1 and P2 are
  reopened. The fixes land in one P1 commit with the `AGENTS.md` entry they change, as cycle 1's
  did; P2 closes after the profile's full `verify`, which waits on the foreman's release.
  `gate.sh`, `seen_red.sh` and `sweep.py` are unchanged (every sweep anchor still holds); P1's
  `verify:` is retuned to run, after them, `remediation/F6-F8-review2.py`, the kill evidence of
  review cycle 2's N1 (checker F6), N2 (F7) and the oracle (F8).
  - N1 (F6): a functional class form is read only as one name assigned the call at module or class
    level with its fields written out as a literal. Every other spelling is a position marked
    unreadable and refused: a call in a function body or a method, as a base class, with an
    annotated, chained, tuple, walrus or attribute target; fields in a variable, from a call,
    unpacked, or holding an element that is not a pair; a keyword the check does not read
    (`make_dataclass(namespace=...)`); a `type` namespace not written out, unpacked or setting
    `__annotate__`; a `types.new_class` body callback; a factory bound to another name or passed as
    a value; a factory's name as a string; `__annotations__` or `__annotate__` spelled anywhere but
    a read `type` call's namespace. An alias is taken from a `from ... import ... as ...` of any
    module. An `if TYPE_CHECKING:` body, a class statement's base and a one-argument `type(x)` are
    not refused. 26 spellings, each a row in both modes.
  - N2 (F7): `dataclasses.KW_ONLY` is a qualifier valid only at the top of a class attribute. The
    valid shapes hold two dataclasses using it (one frozen, one by a string annotation); rows refuse
    it on a variable, on a parameter and below the top.
  - The `AGENTS.md` § Testing entry, and the module docstring, state what is read, what is refused
    as unreadable, and what is not read, and name `runtime_positions`.
  - The oracle (F8): the tree test's child also runs `runtime_positions`, which imports every module
    (never a `__main__`) and reads with `annotationlib`, as strings, each module's annotations, those
    of every class reachable from it that names it as its module (less a base's keys), and those of
    every live function compiled from its file (less wrappers and renamed functions). Every position
    it finds must be one the reader read; the per-module count taken from `annotation_positions` is
    gone. On the tree it finds 994 of the reader's 1,009 positions (the other 15 are nested
    functions not alive after import), none missed, in 0.12 s.
  - Kill evidence (`remediation/F6-F8-review2.py`, both eras, committed state): the new rows are red
    against the check as it stood at `9d8c01a` and green now; fourteen mutants that undo part of a
    fix are each red on their named rows; and nine of N3's reader survivors (D10 to D13, D17 to D19,
    B5, B10) pass the old tree test and fail the new one. N3's D20 (`self` and `cls` skipped)
    survives it, since the tree annotates neither.
  - Seed: the 30 survivors of N3 to N7 the oracle cannot reach, `issues/annotation-check-pin-gaps.md`
    with its `ROADMAP.md` entry (Part I's counts move from 28 to 29 entries, gates from twelve to
    thirteen).
  - Foreman ruling (2026-11-12): the forms the check cannot see are not accepted as scope; they are
    a "not read today" section of `issues/annotation-check-pin-gaps.md`, which `AGENTS.md` names.
  - Runs: the build commit holds P1 and P2 `in_progress`. `gate.sh P1` ran green on a dangling
    candidate of the same tree (`SEEN_RED_REV`); `verify/sweep.py`, the checker on the commit, and
    P2's full `verify` run when the foreman releases the host, and close both phases.
  - Run B (2026-11-12, at `8baa949`): `verify/sweep.py`, baseline 268 passed per era, 102 mutants,
    100 killed in both eras, 2 recorded equivalent; `remediation/F6-F8-review2.py` on `0cd4628`, 68
    expectations held (the seed-only commit after it touches no file the checker reads);
    `gate.sh P2`, static, docs and ledger ok, then the profile's full `verify` green in both eras
    (fourth command 4,637 passed and 14 `need_shell` skipped per era), 1,565 s wall.
- **2026-11-13, review cycle 3 remediation** (`REVIEW.md`, changes-requested at `011c31f`, the loop's
  bound reached and escalated). The maintainer's ruling (route b): fix N10 and N12; seed N9 and N11
  into the cycle's existing seed, `issues/annotation-check-pin-gaps.md`, with `ROADMAP.md` in step;
  land with no further review. Standing rule for this effort: a false refusal on a shape no file
  uses, which lets nothing invalid through, is graded LOW and seeded; N9 falls under it (noted in
  `REVIEW.md`). P1 and P2 are reopened and land in one P1 commit, as in cycles 1 and 2. P1's
  `verify:` is retuned to run, after the cycle 2 checker, `remediation/F9-review3.py`, the kill
  evidence of review cycle 3's N10 (checker F9). `gate.sh`, `seen_red.sh`, `sweep.py` and
  `F6-F8-review2.py` are unchanged; every anchor of the last two still holds.
  - N10 (F9): the check refused `__annotations__` and `__annotate__` as a string, a keyword, an
    attribute or a name, never as the name a statement binds, so `def __annotate__` in a class body
    passed. The class is every node that spells the name it binds in a field of its own:
    `NAME_FIELDS` lists them (a keyword, a name, a `def`, an `async def`, a `class`, an import's name
    and alias, a `match` capture, star and mapping rest), and `_spelled` reads each; a `def` or
    `class` is asked before its body is walked, and is shown by its first line. An `except ... as`
    name is not among them: Python unbinds it when its handler ends. Twelve new rows of
    `test_an_unreadable_functional_form_is_refused`, in both modes: `def __annotate__` in a class at
    module level, in a class inside a function (the review's case), at module level, as a
    `staticmethod`; `async def` and `class` named `__annotate__`; `from dataclasses import
    __annotate__`; `__annotations__` bound by `from ... import ... as`, `import ... as`, and a
    `match` capture, star and mapping rest. Each row's refusal is on one line.
  - The `AGENTS.md` § Testing entry and the reader's docstring list exactly those spellings; the
    sentence that said "spelled anywhere" is gone.
  - Kill evidence (`remediation/F9-review3.py`, both eras, committed state): the rows at REV pass, the
    tree test among them (the control: the unmutated tree passes, so the new refusal refuses nothing
    the tree holds); the twelve new rows are each red against the check at `011c31f`; eleven mutants
    that undo part of the fix (F9a to F9k) are each red on their named rows; review cycle 3's N11
    survivor AK2 (`__annotate__` dropped from the keys) is now red on seven of them. The sweep over
    the new decision adds four carve-outs, each red on its row (C1 module level, C2 a decorated
    `def`, C3 a class inside a function, C4 a plain `import`), and records one survivor, C5 (a
    `def __annotate__` whose parameters are not one positional name), which the checker requires to
    survive the whole module; it is seeded in `issues/annotation-check-pin-gaps.md`.
  - N12: the seed's "Not read today" now says what the review reproduced. A namespace lookup, and a
    namespace given to a metaclass or a renamed `type`, are refused wherever the name or key is
    written in `src/`; only names built at run time pass. It names `def __annotate__` as refused.
  - Seeded in `issues/annotation-check-pin-gaps.md`, with its `ROADMAP.md` entry rewritten in step:
    N9 (the tree test's oracle red on a `TypedDict` subclassing another, a functional form bound to
    another name, and one assigned in a class body; it fails closed and no file uses them), N11's
    five other survivors (U6, UC6, UC10, UFi10, UFi2), and C5, with acceptance criteria R7 and R8.
  - Runs: `gate.sh P1`, `verify/sweep.py`, `remediation/F6-F8-review2.py` and
    `remediation/F9-review3.py` ran green on a candidate tree of this commit's content (the module
    byte-identical to the commit's); P2 stays `in_progress` until the profile's full `verify`, which
    waits on the foreman's release of the host.
  - Run B (2026-11-13, at `2ba12c1`): `gate.sh P2`, static, docs and ledger ok, then the profile's
    full `verify` green in both eras (fourth command 4,661 passed and 14 skipped per era, the same
    skip count as cycle 2's run), 1,555 s wall. P2 closes.

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
  both eras, about 12 min, reading committed state; its record is `verify/sweep-record.md`), then
  `remediation/F6-F8-review2.py` (review cycle 2 remediation: the kill evidence of N1, N2 and the
  oracle, both eras, about 4 min, reading committed state), then `remediation/F9-review3.py` (review
  cycle 3 remediation: the kill evidence of N10 and the sweep over its decision, both eras, about
  2 min, reading committed state).
- **Touches:** `tests/test_annotations.py`; `spec/annotation-check/verify/sweep.py` and its record
  (review cycle 1 remediation); `spec/annotation-check/remediation/F6-F8-review2.py` (review cycle 2
  remediation); `spec/annotation-check/remediation/F9-review3.py` (review cycle 3 remediation).

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
      files none; review cycle 2's remediation files `issues/annotation-check-pin-gaps.md`.
- [x] Run `sh spec/annotation-check/verify/gate.sh phase` first (fast), then the full gate in the
      background (the profile's `verify`, about 26 min).
- **Verify:** `sh spec/annotation-check/verify/gate.sh P2` (static, docs, ledger, then the profile's
  full `verify`, read from AGENTS.md § Factory at run time). R6's CI-budget clause is graded at
  publish on the cycle branch's CI run, not here.
- **Touches:** `AGENTS.md` (§ Testing only); `issues/annotation-check-pin-gaps.md` and its
  `ROADMAP.md` entry (review cycle 2 remediation; extended in review cycle 3's).

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
