---
status: unshaped
kind: test
appetite: small
lane: public
---

# The static skip check admits a renamed skipper and a subclassed outcome type

## Problem

`tests/test_hygiene.py`'s `skip_violations` (run over every `tests/*.py` by
`test_only_need_shell_skips`) reads skips by the word of a `Name` or `Attribute` node. Two
statically visible skips get past it:

- **A skipper renamed on import.** `from pytest import skip as go`, then `go("x")`. The call's
  word is `go`; the import alias (`alias.name == 'skip'`) is never read. The same holds for
  `xfail`, `skipif` and `importorskip`. Renaming the module is caught (`import pytest as pt`, then
  `pt.skip(...)`): the attribute's word is still `skip`.
- **The outcome type subclassed, then raised.** `class S(pytest.skip.Exception): pass`, then
  `raise S("x")`. `pytest.skip.Exception` among a class's bases is the outcome type read as a value,
  which the check admits by design (it is how `pytest.param(..., pytest.skip.Exception)` and
  `pytest.raises(pytest.xfail.Exception)` name the outcome), and `raise S(...)` names no skipper.

Both probes report nothing on the check before and after `skip-check-fence-gaps` (2026-11-09).
None exists in the suite today; either would let a row vanish from CI without failing.

## Why it was deferred

Found while planning `skip-check-fence-gaps`. Its GOAL names neither shape: the import alias is
not among its dynamic-lookup non-goals, but no requirement covers it, and reporting a subclassed
outcome type reads against that GOAL's rule that the outcome type referenced as a value, never
raised, stays admitted. The sign-off kept both out of that cycle and seeded them here.

**Pre-existing:** yes, on `develop` since `safe-execution` added the check.

## Outcome / vision

The check resolves an import alias of a skipper to the skipper, and treats a class whose bases
name a skipper's outcome type as that outcome type, so raising it is reported, while naming the
outcome type as a value stays admitted.

## Sketch of the acceptance criteria

- **R1** — WHEN a module imports a skipper under another name (`from pytest import skip as go`)
  and uses that name, the check SHALL report the use.
- **R2** — WHEN a class lists a skipper's outcome type among its bases, the check SHALL report it
  (or report raising that class; the shaping conversation picks which).
- **R3** — The outcome type read as a value (`pytest.param`, `pytest.raises`) SHALL stay admitted,
  and each new shape SHALL have a planted row in `test_skip_check_catches_planted_skips`.

## Notes

- Related: `spec/skip-check-fence-gaps/` (PLAN § 5, Q1; the `skip_violations` docstring names both
  shapes among what the check cannot see); `issues/skip-check-deselection.md`.
- Found by: `skip-check-fence-gaps` plan, adversarial review, 2026-11-09.
