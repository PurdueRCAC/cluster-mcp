---
status: unshaped
kind: test
appetite: small
lane: public
---

# The static skip check admits a skip it should catch

## Problem

`tests/test_hygiene.py`'s `skip_violations` (run by `test_only_need_shell_skips`) is the fence that
keeps a test from skipping on CI unseen: only the bodies of `conftest.need_shell` and
`conftest.need_git` may skip, and both fail instead on CI. A planted-skip probe found four shapes it
admits:

- a helper of an allowed name nested inside a conftest fixture, or defined as a class method;
- a second definition of an allowed name in conftest, shadowing the first;
- a test module whose file name merely ends in `conftest.py` (`tests/test_conftest.py`), since the
  check matches the name with `endswith('conftest.py')`;
- a skip called as `pytest.skip.__call__(...)`.

Any of them would let a row vanish from CI without failing. None exists in the suite today.

## Why it was deferred

Found by the blind check of the merge that landed `absence-check-leftover-classification`
(2026-10-23), which only extended the allowed set to `need_git`; the shapes come from the check
`safe-execution` added, and fixing them was outside that merge's scope.

**Pre-existing:** yes, on `develop` since `safe-execution` landed.

## Outcome / vision

The check admits a skip only inside the top-level, single definition of an allowed helper in
`tests/conftest.py` itself, and catches every spelling of a skip call.

## Sketch of the acceptance criteria

- **R1** — WHEN an allowed helper's name is nested, redefined, or defined in a module other than
  `tests/conftest.py`, the check SHALL report the skip inside it.
- **R2** — WHEN a skip is reached through an attribute of a skipper (`pytest.skip.__call__`), the
  check SHALL report it.
- **R3** — Each shape SHALL have a planted row in `test_skip_check_catches_planted_skips`.

## Notes

- Related: `spec/absence-check-leftover-classification/REVIEW.md` (landing merge);
  `spec/safe-execution/` (the check's origin); `AGENTS.md` § Testing.
- Found by: the landing-merge check of `absence-check-leftover-classification`, 2026-10-23.
