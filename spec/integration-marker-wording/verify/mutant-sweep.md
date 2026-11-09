# Mutant sweep record

Run 2026-11-09 by `gate.sh P2` (`sweep` part, `verify/marker_mutants.py`) on the staged P2 tree over
commit `31a766c`, `tests/test_hygiene.py` blob `8d1adfc1efe4` (the blob P2 commits). Python 3.14.

```
unmutated: 51 drift rows, 4 accept rows, live test passed, not passed: []
testing-only: killed (reads § Testing alone) by changed-in-conventions, missing-from-conventions
conventions-only: killed (reads § Conventions alone) by changed-in-testing, missing-from-testing
whole-file-first-statement: killed (reads the first statement anywhere in AGENTS.md) by missing-from-testing, changed-in-conventions
first-of-several: killed (takes the first of several statements in a section) by stated-twice
silent-section-passes: killed (lets a section that states nothing pass) by missing-from-testing, missing-from-conventions, statement-without-items, statement-line-reworded, item-without-backticks-in-testing
silent-pyproject-passes: killed (lets a pyproject.toml with no markers pass) by missing-from-pyproject
order-free: killed (compares the markers in any order) by reordered-in-testing
mapping: killed (compares name-to-description mappings, so a repeat collapses) by repeated-in-pyproject, repeated-in-testing, reordered-in-testing
names-only: killed (compares names alone) by changed-in-pyproject, changed-in-testing, changed-in-conventions
extra-stated-ignored: killed (ignores a marker AGENTS.md states beyond pyproject.toml) by third-marker-in-testing
extra-described-ignored: killed (ignores a marker pyproject.toml describes beyond AGENTS.md) by third-marker-in-pyproject, one-missing-from-testing
extra-stated-ignored-too: killed (ignores a marker AGENTS.md states beyond pyproject.toml (one missing there)) by one-missing-from-pyproject
section-runs-to-end: killed (reads from the heading to the end of AGENTS.md) by +as-planted
two-markers-only: killed (compares the first two markers only) by third-marker-in-pyproject, third-marker-in-testing
item-indent-free: killed (takes an item at any indentation) by item-over-indented-in-testing
casefold: killed (ignores case) by case-in-pyproject, case-in-testing
punctuation-free: killed (ignores punctuation) by punctuation-in-pyproject, punctuation-in-testing
markup-free: killed (ignores Markdown markup in a description) by markup-in-testing, emphasis-in-testing
unicode-compatible: killed (compares descriptions after NFKC normalisation) by no-break-space-in-testing, decomposed-in-testing
whitespace-free: killed (ignores whitespace beyond wrapping, as the id-rule check does) by double-space-in-pyproject, double-space-in-testing, tab-in-testing, trailing-space-in-pyproject, trailing-space-at-wrap-in-testing, two-spaces-after-name-in-testing, no-break-space-in-testing
wrap-indent-free: killed (takes a wrapped line at any deeper indentation) by over-indented-wrap-in-testing
trailing-clause: killed (ignores a clause one side adds at the end) by clause-at-end-in-pyproject, clause-at-end-in-testing
leading-clause: killed (ignores a clause one side adds at the start) by clause-at-start-in-pyproject, clause-at-start-in-testing
middle-clause: killed (ignores words one side adds anywhere, the other side read in order) by clause-in-middle-in-pyproject, clause-in-middle-in-testing, clause-at-start-in-pyproject, clause-at-start-in-testing, clause-at-end-in-pyproject, clause-at-end-in-testing
separator-free: killed (splits a pyproject.toml entry at its first ':' and strips it, as pytest does) by no-space-after-name-in-pyproject, trailing-space-in-pyproject
statement-end-free: killed (ends the statement silently at any line it does not read) by clause-lazy-after-last-item, clause-at-item-indent-after-last-item, clause-over-indented-after-last-item, clause-after-a-blank-in-last-item, third-marker-after-a-blank-in-testing, third-marker-other-bullet-in-testing
blank-ends-statement: killed (takes a blank line as the end of the statement, whatever follows) by clause-after-a-blank-in-last-item, third-marker-after-a-blank-in-testing
name-casefold: killed (ignores the case of a name) by name-case-in-testing
trailing-period-free: killed (ignores a trailing period) by trailing-period-in-testing
composed-equal: killed (compares descriptions after NFC normalisation) by decomposed-in-testing
statement-line-whitespace-free: killed (finds the statement line whatever whitespace surrounds it) by statement-line-trailing-space-in-testing, statement-line-tab-indented-in-testing
statement-line-free: killed (finds the statement line by its opening words) by statement-line-reworded
name-stripped: killed (strips a stated marker's name) by name-changed-in-testing
name-shape-free: killed (takes an item whose name is not in backticks) by item-without-backticks-in-testing
34 mutants, 0 not killed
```
