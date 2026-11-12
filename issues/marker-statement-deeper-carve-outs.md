---
status: unshaped
kind: test
appetite: small
lane: public
---

# The marker-statement check passes three shapes CommonMark renders differently

## Problem

Once `integration-marker-wording` lands, `tests/test_hygiene.py`'s `marker_statement_violations`
holds `AGENTS.md`'s statement of the two markers to `pyproject.toml` word for word, line wrapping the
only freedom. `test_marker_statement_check_refuses_every_edit` pins the comparison over its whole
domain (every one-place edit of a planted statement: each character deleted or replaced, each span
between word boundaries dropped, each character of `EDIT_ALPHABET` inserted), and
`test_marker_statement_ends_where_markdown_ends_it` pins where the statement ends for each
whitespace form a following line can start with. The mutant sweep run after that
(`spec/integration-marker-wording/remediation/F8-marker-check-sweep.py`, 220 mutants, 2026-11-12)
left two survivors, and a CommonMark probe (markdown-it-py) found a third shape. Each is a deeper
layer of a class a row or the control already pins:

1. **A fold of two characters the pinned folds do not cover.** A check that folds an em or en dash
   to a hyphen before comparing (`cmp-dash-fold`) passes a statement that writes `-` where
   `pyproject.toml` writes `—`. Case, curly quotes and the Unicode normal forms are pinned by rows;
   the control replaces each character by its other case or by a letter, never by a look-alike, so
   any pair of distinct characters a normalisation could merge is open in the same way.
2. **A statement indented past its bullet's text.** The check reads the items at the statement
   line's indentation and ends the statement at a less indented item. CommonMark continues the same
   list with an item anywhere from the bullet's text column to three columns deeper, so a statement
   at four spaces in a bullet whose text starts at two, followed by `  - `beta`: a third`, passes
   and renders a third marker. The mutant `sm-rstrip` (trailing spaces on the statement line, which
   move the indentation the items are read at) reaches the same shape. Both live statements sit at
   their bullet's text column, so neither is affected today.
3. **A wrap whose next line Markdown reads as the start of a block.** Joining a wrap by one space
   restores the words, so a description wrapped just before ` - it to that` passes; CommonMark
   renders a nested list inside the item. The same holds for a wrapped line starting with an
   ordered marker numbered 1, `>`, `#` or a fence.

## Why it was deferred

`integration-marker-wording`'s review converged under the mutation method's rule for a finished
review: a survivor that is a deeper layer of a class already pinned is seeded, not a finding, so no
cycle chases an endless series of deeper layers. These three are that remainder.

**Pre-existing:** no; the check is new in `integration-marker-wording`.

## Outcome / vision

The check reads a statement as CommonMark renders it, for any statement shape: either it renders
the section with a CommonMark parser and compares the rendered items, or it refuses every shape
outside the canonical one (the statement at its bullet's text column, wraps that start no block).
The comparison is held against every pair of distinct characters in a stated alphabet, not only the
pairs a row names.

## Sketch of the acceptance criteria

- **R1** — The check SHALL refuse a statement whose items CommonMark renders differently from the
  joined lines it compares, for each shape above, each with a planted row.
- **R2** — A control SHALL refuse a statement that differs from `pyproject.toml` by one character
  replaced with any other character of `EDIT_ALPHABET`, within a stated time budget.
- **R3** — The probe that grounds the rows in CommonMark (`F6-statement-end-commonmark.py` in the
  cycle's `remediation/`) SHALL cover statement shapes as well as following lines, and move into the
  suite or CI if the parser does.

## Notes

- Related: `spec/integration-marker-wording/` (REVIEW, cycle 2; TECH, amendments);
  `issues/marker-rule-gaps.md`; `tests/test_hygiene.py` (`marker_statement_violations`,
  `statement_end_problems`, `stated_markers`).
- Found by: `integration-marker-wording` review cycle 2 remediation, 2026-11-12.
