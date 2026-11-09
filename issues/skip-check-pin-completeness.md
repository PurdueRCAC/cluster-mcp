---
status: unshaped
kind: test
appetite: small
lane: public
---

# The static skip check's behaviour is pinned for some forms and positions, not all

## Problem

`skip-check-fence-gaps` left `skip_violations` in `tests/test_hygiene.py` behaving correctly on
every reachable input its third review tried, but some of that behaviour has no planted row in
`test_skip_check_catches_planted_skips`: a mutant can change it, pass all 68 skip-check rows in
both eras, and flip the check's verdict on a reachable input. The review recorded three such gaps
(`spec/skip-check-fence-gaps/REVIEW.md`, cycle 3, G1–G3):

- **G1, the "defined again" report** (`_scope_bindings`, `_module_bindings`). A second module-scope
  binding of a helper's name in conftest is reported, but only some binding forms are pinned. An
  `async def need_git` after the real `def need_git` is reported, and a mutant that stops counting
  an `async def` as a binding passes every row. So does one that stops looking for a `global
  need_git; need_git = ...` store inside an `async def` or a class body. Additive survivors drop a
  binding form outright: `for need_git in ()`, `need_git += 1`, `with ... as need_git`,
  `type need_git = int`. The check reports each; the mutants do not.
- **G2, the raise side** (`_raised`). `raise pytest.skip.Exception("x") or ValueError()` skips its
  row at run time (exit 0, one passed and one skipped, under pytest, 2026-11-09), and the check
  reports it. A mutant that follows only an `or`'s last operand passes every row: the one boolean
  row (`raise None or ...`) pins the last operand alone.
- **G3, the admission side** (`_raised`, `_scope_bindings`). The outcome type as a keyword argument
  of a raised call (`raise Mismatch(expected=pytest.skip.Exception)`) is admitted; a mutant that
  reports it passes every row, while its positional sibling is pinned. Additive survivors count
  non-bindings as bindings in conftest, so the mutant reports "defined again" and stops admitting
  the real helper's skip: a parameter (`def run(need_git=None)`), a keyword name
  (`f(need_git=1)`), an attribute store (`tools.need_git = need_git`). The check admits all three.

None of these is a wrong verdict today; each is behaviour a later edit could break without a row
failing. Evidence: the cycle's review-3 mutant sweep (99 mutants, 80 killed, 19 survived, every
survivor re-run under real pytest in both eras), and real scans of planted copies of `tests/`.

## Why it was deferred

The cycle reached its review bound with these three findings open, each the next layer of a class
its earlier rounds had already pinned (pin gaps in the skip check, now from additive mutants). The
maintainer ruled (2026-11-09) to land the cycle at its reviewed head by overriding the review
rubric for G1–G3 and to seed them here: a cycle's diff sweep is the complete list a review works
through, and hand-made deeper layers of a class already pinned become seeds, not findings.

**Pre-existing:** no. The binding, raise and admission logic was introduced by
`skip-check-fence-gaps`; the gaps are in its pins, not its behaviour.

## Outcome / vision

Every form and position the check distinguishes has a planted row that fails if that form or
position flips, and a module-wide mutant sweep that includes additive mutants (a binding or raise
position dropped or added, one per form) leaves only recorded equivalents, in both eras.

## Sketch of the acceptance criteria

- **R1** — For every way Python binds a module-scope name in conftest (def, async def, class, every
  assignment and target form, augmented assignment, `for` and `with` targets, import,
  `except ... as`, match capture, `type`, and a `global` store from any function, async function or
  class body), there SHALL be one planted row that fails if that form stops counting as a binding.
- **R2** — For every operand a raised expression can hand on as the exception (each operand of
  `and` / `or`, either branch of a conditional, a walrus value, a called or method-called outcome),
  there SHALL be one planted row that fails if that position stops being reported.
- **R3** — For every admitted value position inside a raise (positional, keyword, starred, message,
  cause, conditional test) and every name occurrence that binds nothing at module scope (load, bare
  annotation, comprehension variable, parameter, keyword name, attribute store, type parameter),
  there SHALL be one planted row that fails if the check starts reporting it.
- **R4** — A mutant sweep over `_scope_bindings`, `_module_bindings`, `_allowed`, `_raised` and
  `skip_violations` that includes additive mutants SHALL kill every non-equivalent mutant in both
  eras, with each equivalent recorded and its reason stated.

## Notes

- Related: `spec/skip-check-fence-gaps/` (REVIEW cycle 3: G1–G3, Routing, Coverage observations);
  `issues/skip-check-import-aliases.md`; `issues/skip-check-deselection.md`.
- Found by: `skip-check-fence-gaps` review cycle 3, 2026-11-09.
