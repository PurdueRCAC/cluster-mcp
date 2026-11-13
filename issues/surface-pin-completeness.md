---
status: unshaped
kind: test
appetite: small
lane: public
---

# The surface pin's recorder has two layers no row plants, and its report three details

## Problem

The served-surface fixture is a plain snapshot test (`tests/test_surface.py`): the serialization of
what `served_surface` (`tests/harness.py`) records, compared by plain equality of bytes. Equality
catches any change in what the recorder records, but not a recorder that stops recording a key: a
key it dropped would pass once an update run had written the fixture without it. The recorder rows
(`test_recorder_sees_what_the_server_starts_serving` and its neighbours) hold most of that, and two
layers survive hand-made mutants of the recorder in both protocol eras
(`spec/surface-fixture-after-a-surface-change/REVIEW.md`, review cycle 2, coverage observations):

- **The `execution` key.** `rec-drop-execution`: the rows plant `icons`, `_meta`, annotations,
  titles, a resource's title and annotations, a prompt, a resource template, an experimental
  capability and two server-info fields, but no tool served with `execution`, which the cycle's
  GOAL names. A recorder that dropped it would pass every row.
- **The repeated cursor.** `rec-no-cursor-guard`: no row serves a listing that returns the same
  cursor twice, so a recorder without its guard hangs until the harness's 30 s timeout instead of
  refusing; loud, not a silent pass.
- **What a failure prints.** Three mutants of the snapshot test change only the text of a failure,
  never its verdict or the entry and field it names, and survive in both eras (the same REVIEW.md,
  the re-shape's review 1, coverage observations): `ver-uninstalled-empty-string` records an
  uninstalled candidate as `''`, which changes only the error text for it (every candidate is
  installed in the workspace); `diff-leaf-no-sort-keys` writes a leaf's JSON text without sorted
  keys, which differs only for a fixture out of canonical form with dict keys out of order inside a
  list; `short-limit-6` cuts each value to 6 characters instead of the 60 `AGENTS.md` documents.

None is a wrong verdict today; each is behaviour a later edit could break without a row failing.

## Why it was deferred

Each is a deeper layer of a class the cycle already pins (the recorder's keep-every-key rule, its
paging, the report's line per differing field). Under the cycle's grading rule a hand-made mutant
of a deeper layer is a coverage observation and is seeded, not a finding.

**Pre-existing:** no. The raw recorder was introduced by `surface-fixture-after-a-surface-change`;
the gaps are in its pins, not its behaviour.

## Outcome / vision

Every key the surface's GOAL names is planted through a recorder row, and a listing that repeats
its cursor is refused by the recorder, named, under a row that would hang without the guard. A
failure's text is pinned as well as its verdict: an uninstalled candidate named as such, a leaf's
text independent of key order, and the documented cut of a value.

## Sketch of the acceptance criteria

- **R1** — The recorder rows SHALL plant a tool served with `execution`, and the serialization of
  the planted surface SHALL differ from the unplanted one by exactly that key.
- **R2** — A listing that returns the same cursor twice SHALL be refused by the recorder with an
  error naming the listing and the cursor, under a row bounded well below the harness's timeout.
- **R3** — The error for an uninstalled candidate SHALL name it as not installed under a row that
  plants one; a fixture whose only difference is dict keys out of order inside a list SHALL be
  reported as out of canonical form, with no changed line; a value longer than the documented cut
  SHALL be shown cut at it.
- **R4** — A sweep of the five mutants above SHALL kill each in both eras.

## Notes

- Related: `spec/surface-fixture-after-a-surface-change/` (REVIEW cycle 2 and the re-shape's
  review 1, coverage observations);
  `issues/skip-check-pin-completeness.md`, the same shape for the skip check.
- Found by: `surface-fixture-after-a-surface-change` review cycle 2, 2026-11-10. Re-checked
  2026-11-12 against the snapshot-test re-shape: the comparison's depth bound, the version source
  accepting a version two candidates share, the check of each capability set and the scan for runs
  of the command lost their ground (bytes equality, the version control, every set serialized, the
  command removed) and were dropped. The report's three details were added 2026-11-12 from the
  re-shape's review 1.
