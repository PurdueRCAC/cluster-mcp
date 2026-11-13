---
status: unshaped
kind: test
appetite: small
lane: public
---

# Two of the shard ledger's guards are pinned by no row

## Problem

`report_violations` in `tests/mutants.py` is the shard ledger: it reads a shard's report and names
each case without exactly one kill and each control that did not pass. Two of its guards never fire
on a report the runner can print, so no row in `tests/test_mutant_shards.py` feeds them, and a
mutant that drops either one passes every row:

- `if word not in ('killed', 'FAILED', 'control') or not name:` (`tests/mutants.py:6073`). The
  `or not name` skips a verdict line with an empty name (`killed  `, or `FAILED  : why`). Dropped,
  such a line becomes a verdict for the case `''`, and the ledger fails the shard with
  `: not a case of this shard`. The runner never prints a verdict line without a case id.
- `elif word != 'control':` (`tests/mutants.py:6077`). It keeps a `control` line whose text is not
  one of `CONTROLS` out of the verdicts. Turned into `else:`, such a line becomes a verdict for a
  case named by that text, and the ledger fails the shard with `<text>: not a case of this shard`.
  The runner prints `control` lines only for the texts in `CONTROLS`.

Either mutant can only add ledger failures, and only on a report shape the runner does not produce.
The code is correct as it stands; the gap is that a change that drops either guard would pass the
rows unseen.

Evidence: the review of `mutants-workflow-timeout` (cycle 1, 2026-11-12) planted 44 hand-made
mutants into the cycle's runner and workflow code, in a detached copy, killed against
`tests/test_mutant_shards.py` with a pristine control (12 of 12 passed). These two, `ledger-empty-name`
and `ledger-control-else`, survived (12 passed each). The review graded them as coverage
observations: each removes a guard that never fires on reachable input.

## Why it was deferred

The method rules a hand-made mutant that pins no R-ID's check and no reachable behaviour a coverage
observation, which is seeded rather than fixed in the review cycle that found it. The cycle that
found it, `mutants-workflow-timeout`, was in remediation for its budget row only, with no code change.

It is **introduced by that cycle**: `report_violations` is new in it. The behaviour is correct; only
the pins are missing.

## Outcome / vision

Each guard is either pinned or gone, by decision:
- a row feeds the ledger the shape the guard handles and asserts the outcome the code has today (an
  empty-name verdict line ignored; a `control` line outside `CONTROLS` not counted as a case); or
- the maintainer rules the shape unreachable and the guard is removed, with the reason recorded.

Possible fix shapes, for shaping to choose between:
- two `unit` rows in `tests/test_mutant_shards.py`, one per shape, each killing its mutant;
- a single row of malformed lines (empty name, foreign control text, a single-space separator)
  that the ledger must ignore, in the spirit of the docstring's "Other lines ... cannot make a case
  pass".

## Sketch of the acceptance criteria

- **R1** — WHEN a shard's report holds a `killed` or `FAILED` line with an empty name, the ledger
  SHALL ignore it, and a row SHALL fail if it does not.
- **R2** — WHEN a shard's report holds a `control` line whose text is not one of `CONTROLS`, the
  ledger SHALL not count it as a case's verdict, and a row SHALL fail if it does.
- **R3** — WHEN the ledger's guards are unchanged, every existing row SHALL pass as it does today.

## Notes

- Related: `issues/mutant-runner-stop-pins.md` (the runner's stop path, the same kind of deeper
  pin); `spec/mutants-workflow-timeout/` (REVIEW cycle 1, mutation grading; TECH Amendments,
  2026-11-12, review cycle 1 remediation).
- Found by: `mutants-workflow-timeout`, review cycle 1 (2026-11-12).
