---
status: unshaped
kind: test
appetite: small
lane: public
---

# The marker-statement check: two shapes it reads otherwise than CommonMark, and carve-outs its rows leave unpinned

## Problem

Once `integration-marker-wording` lands, `tests/test_hygiene.py`'s `marker_statement_violations`
holds `AGENTS.md`'s statement of the two markers to `pyproject.toml` word for word, line wrapping the
only freedom. `test_marker_statement_check_refuses_every_edit` refuses every one-place edit of a
planted statement in its alphabet (each character deleted or replaced, each span between word
boundaries dropped, each character of `EDIT_ALPHABET` inserted), and
`test_marker_statement_ends_where_markdown_ends_it` pins where the statement ends for each
whitespace form a following line can start with. Three sources found what is left:

- the cycle's own mutant sweep
  (`spec/integration-marker-wording/remediation/F8-marker-check-sweep.py`, 2026-11-12) left two
  survivors;
- a CommonMark probe (markdown-it-py) found two shapes;
- the third review's sweep (119 mutants, `spec/integration-marker-wording/REVIEW.md`, review cycle 3,
  2026-11-12) left eight more survivors, and it noted refusals of shapes CommonMark accepts.

They fall into three groups.

### Shapes the check reads otherwise than CommonMark renders, letting a drift through

1. **A statement indented past its bullet's text.** The check reads the items at the statement
   line's indentation and ends the statement at a less indented item. CommonMark continues the same
   list with an item anywhere from the bullet's text column to three columns deeper, so a statement
   at four spaces in a bullet whose text starts at two, followed by `  - `beta`: a third`, passes
   and renders a third marker. The mutant `sm-rstrip` (trailing spaces on the statement line, which
   move the indentation the items are read at) reaches the same shape. Both live statements sit at
   their bullet's text column, so neither is affected today.
2. **A wrap whose next line Markdown reads as the start of a block.** Joining a wrap by one space
   restores the words, so a description wrapped just before ` - it to that` passes; CommonMark
   renders a nested list inside the item. The same holds for a wrapped line starting with an
   ordered marker numbered 1, `>`, `#` or a fence.

### Coverage gaps: drifts the check refuses that no row pins

Each is a drift the unmodified check refuses, but which a check carrying the named carve-out would
pass with every row and the control still green. Each is a deeper layer of a class a row or the
control already pins.

3. **A fold of two characters the pinned folds do not cover** (`cmp-dash-fold`). A check that folds
   an em or en dash to a hyphen before comparing passes a statement that writes `-` where
   `pyproject.toml` writes `—`. Case, curly quotes and the Unicode normal forms are pinned by rows;
   the control replaces each character by its other case or by a letter, never by a look-alike, so
   any pair of distinct characters a normalisation could merge is open in the same way.
4. **A character outside `EDIT_ALPHABET` stripped before comparing** (`cmp-strip-arrows`,
   `cmp-strip-cjk-punct`). The control inserts only the characters of its alphabet, so a check that
   drops `→` or `、` passes a statement with one inserted.
5. **A name-only `markers` entry skipped** (`desc-name-only-skipped`). A check that skips an entry
   with no description passes a bare `"beta"` added to `pyproject.toml`'s `markers`; the
   third-marker rows add only entries with one.
6. **A statement line quoted at its indentation** (`sm-strip-quote-marker`). A check that strips
   `>` before matching the statement line, and reads the items at that line's own leading spaces,
   passes `  > Each marker means…`, which CommonMark renders as a blockquote before the list; the
   row `statement-line-quoted-in-testing` quotes the line at the margin only.
7. **A line of spaces splitting a description** (`sm-blank-wrap-ok`). A check that joins a wrap
   across a line of spaces passes a description CommonMark renders as two paragraphs; the
   blank-wrap and whitespace rows plant a line of spaces only after the last item.
8. **Two blank lines, then a clause in the last item** (`end-follow-next-line-only`). A check that
   reads only the line after the first blank passes a clause after a second blank line; the row
   `clause-after-a-blank-in-last-item` plants one blank line.
9. **A bare `-` line that renders a third item** (`li-no-eol`). A check whose list-marker pattern
   needs text after the marker passes a lone `-` line after a blank line, which CommonMark renders
   as an empty third item; the third-marker-after-a-blank rows plant an item with text.
10. **A second, drifted statement under a deeper heading** (`sec-any-level`). A check that ends
    § Testing at a heading of any level passes a drifted second statement under a `###` inside
    it; the row `stated-twice` plants the second statement with no heading between.

### Refusals of shapes CommonMark places after the list

11. **Some block starters after the statement.** The check refuses some lines that start a block
    CommonMark places after the list, outside the statement: a quote (`> x`), a fence, a thematic
    break, an HTML comment, a heading one column in (` # x`), and a `*` item at the items' indent.
    No drift gets through; it is a false red on a layout no file uses. By the maintainer's standing
    rule for this effort, a false refusal on a shape no file uses that lets nothing invalid through
    is graded LOW and seeded. The row `third-marker-other-bullet-in-testing` asks for the last
    refusal.

## Why it was deferred

`integration-marker-wording`'s review converged under the mutation method's rule for a finished
review: a survivor that is a deeper layer of a class already pinned is seeded, not a finding, so no
cycle chases an endless series of deeper layers. Items 1 to 10 are that remainder; item 11 is
seeded under the standing rule above.

**Pre-existing:** no; the check is new in `integration-marker-wording`.

## Outcome / vision

The check reads a statement as CommonMark renders it, for any statement shape: either it renders
the section with a CommonMark parser and compares the rendered items, or it refuses every shape
outside the canonical one (the statement at its bullet's text column, wraps that start no block).
The comparison is held against every pair of distinct characters in a stated alphabet, and every
character outside it, not only the pairs a row names. Each deeper layer above has a planted row
that kills it.

## Sketch of the acceptance criteria

- **R1** — The check SHALL refuse a statement whose items CommonMark renders differently from the
  joined lines it compares, for each shape in items 1 and 2, each with a planted row.
- **R2** — A control SHALL refuse a statement that differs from `pyproject.toml` by one character
  replaced with any other character of `EDIT_ALPHABET`, or by one character outside it inserted,
  within a stated time budget.
- **R3** — Items 5 to 10 SHALL each have a planted row that a check carrying the named carve-out
  fails.
- **R4** — The check SHOULD accept each block starter in item 11 that CommonMark places after the
  list, or `AGENTS.md` SHALL keep naming those refusals.
- **R5** — The probe that grounds the rows in CommonMark (`F6-statement-end-commonmark.py` in the
  cycle's `remediation/`) SHALL cover statement shapes as well as following lines, and move into the
  suite or CI if the parser does.

## Notes

- Related: `spec/integration-marker-wording/` (REVIEW, cycles 2 and 3; TECH, amendments);
  `issues/marker-rule-gaps.md`; `tests/test_hygiene.py` (`marker_statement_violations`,
  `statement_end_problems`, `stated_markers`).
- The mutant names are those of the sweep that found each: `F8-marker-check-sweep.py` for items 1
  and 3, the review's for the rest (REVIEW, review cycle 3, *Surviving mutants*).
- Found by: `integration-marker-wording` review cycle 2 remediation, 2026-11-12; items 4 to 11 by
  its review cycle 3, 2026-11-12.
