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

## Review cycle 1 remediation: the module-wide sweep

Run 2026-11-09 by `remediation/checks.sh F2` (`remediation/F2-marker-check-sweep.py`) on the staged
remediation tree over commit `78eaa24`, `tests/test_hygiene.py` blob `577a9e013368`. Python 3.14. Every mutant
is killed; none is recorded as equivalent. The frozen sweep above was re-run on the same tree by
`gate.sh prepush`: `34 mutants, 0 not killed`.

```
unmutated: 66 drift rows (15 narrower), 4 accept rows, live test passed, not passed: []
always-true: killed [plain] by case-in-pyproject, case-in-testing, changed-in-conventions, changed-in-pyproject …
only-first-marker: killed [plain] by clause-at-end-in-pyproject, clause-at-end-in-testing, curly-quote-in-testing, markup-in-testing …
zip-common-prefix: killed [plain] by one-missing-from-pyproject, one-missing-from-testing, repeated-in-pyproject, repeated-in-testing …
only-described-count: killed [additive:third-marker-in-agents] by one-missing-from-pyproject, repeated-in-testing, third-marker-in-testing
only-stated-count: killed [additive:third-marker-in-pyproject] by one-missing-from-testing, repeated-in-pyproject, statement-without-items, third-marker-in-pyproject
names-only: killed [plain] by case-in-pyproject, case-in-testing, changed-in-conventions, changed-in-pyproject …
texts-only: killed [plain] by name-case-in-testing, name-changed-in-testing
skip-conventions: killed [plain] by changed-in-conventions, missing-from-conventions
skip-testing: killed [plain] by case-in-testing, changed-in-testing, clause-after-a-blank-in-last-item, clause-at-end-in-testing …
stop-at-first-line(ignore wraps): killed [plain] by +as-planted, +paragraph-after-a-blank, +rewrapped, +unwrapped …
end-problems-never: killed [plain] by clause-after-a-blank-in-last-item, clause-at-item-indent-after-last-item, clause-lazy-after-last-item, clause-over-indented-after-last-item …
drop-statement-problems: killed [plain] by clause-after-a-blank-in-last-item, clause-at-item-indent-after-last-item, clause-lazy-after-last-item, clause-over-indented-after-last-item …
drop-no-markers-line: killed [plain] by no-markers-anywhere
no-markers-returns-empty: killed [plain] by missing-from-pyproject, no-markers-anywhere
first-of-duplicate-statements: killed [plain] by stated-twice
skip-bad-item-line: killed [plain] by exception-bullet-after-the-items-in-testing, third-marker-without-backticks-in-testing
whole-file-sections: killed [plain] by +as-planted, +paragraph-after-a-blank, +rewrapped, +unwrapped …
section-ends-at-same-level-only: killed [plain] by +as-planted, +paragraph-after-a-blank, +rewrapped, +unwrapped …
set-compare(order+repeat): killed [additive:order/repeat] by reordered-in-testing, repeated-in-pyproject, repeated-in-testing
sorted-compare(order): killed [additive:order] by reordered-in-testing
dedupe(repeat): killed [additive:repeat] by repeated-in-pyproject, repeated-in-testing
casefold(names+texts): killed [additive:case] by case-in-pyproject, case-in-testing, name-case-in-testing
casefold(texts): killed [additive:case] by case-in-pyproject, case-in-testing
casefold(names): killed [additive:case] by name-case-in-testing
strip-all-punctuation: killed [additive:punctuation] by curly-quote-in-testing, emphasis-in-testing, hyphen-dropped-in-testing, markup-in-testing …
strip-trailing-punctuation: killed [additive:punctuation] by trailing-period-in-testing
ignore-commas: killed [additive:punctuation] by punctuation-in-pyproject
ignore-semicolons-as-commas: killed [additive:punctuation] by punctuation-in-testing
ignore-periods: killed [additive:punctuation] by trailing-period-in-testing
ignore-parens-chars: killed [additive:punctuation] by parentheses-dropped-in-testing
ignore-slashes-hyphens: killed [additive:punctuation] by slash-dropped-in-pyproject, hyphen-dropped-in-testing
curly-to-straight-quotes: killed [additive:unicode/punctuation] by curly-quote-in-testing
strip-markup(`*_): killed [additive:markup] by emphasis-in-testing, markup-in-testing
collapse-all-whitespace: killed [additive:whitespace] by double-space-in-pyproject, double-space-in-testing, name-changed-in-testing, no-break-space-in-testing …
collapse-space-runs: killed [additive:whitespace] by double-space-in-pyproject, double-space-in-testing, trailing-space-at-wrap-in-testing
tabs-to-space: killed [additive:whitespace] by tab-in-testing
strip-ends: killed [additive:whitespace] by name-changed-in-testing, trailing-space-in-pyproject, two-spaces-after-name-in-testing
rstrip-ends: killed [additive:whitespace] by name-changed-in-testing, trailing-space-in-pyproject
lstrip-ends: killed [additive:whitespace] by two-spaces-after-name-in-testing
rstrip-each-line-before-join: killed [additive:whitespace] by trailing-space-at-wrap-in-testing
nbsp-to-space: killed [additive:unicode/whitespace] by no-break-space-in-testing
nfkc: killed [additive:unicode] by decomposed-in-testing, no-break-space-in-testing
nfc: killed [additive:unicode] by decomposed-in-testing
nfd: killed [additive:unicode] by decomposed-in-testing
lenient-name-space(`:\s*`): killed [additive:whitespace] by two-spaces-after-name-in-testing
pyproject-split-at-colon+strip: killed [additive:whitespace] by no-space-after-name-in-pyproject, trailing-space-in-pyproject
name-without-backticks-ok: killed [additive:markup] by item-without-backticks-in-testing
name-strip: killed [additive:whitespace] by name-changed-in-testing
prefix-match(trailing clause): killed [additive:clause-end] by clause-at-end-in-pyproject, clause-at-end-in-testing, sentence-after-the-last-in-testing, trailing-period-in-testing …
suffix-match(leading clause): killed [additive:clause-start] by clause-at-start-in-pyproject, clause-at-start-in-testing, two-spaces-after-name-in-testing
containment(any clause): killed [additive:clause] by clause-at-end-in-pyproject, clause-at-end-in-testing, clause-at-start-in-pyproject, clause-at-start-in-testing …
word-subsequence(middle clause): killed [additive:clause-middle] by clause-at-end-in-pyproject, clause-at-end-in-testing, clause-at-start-in-pyproject, clause-at-start-in-testing …
ignore-parenthesised-text: killed [additive:clause-middle] by parenthesised-phrase-changed-in-testing
ignore-after-last-semicolon: killed [additive:clause-end] by clause-at-end-in-pyproject, clause-at-end-in-testing, markup-in-testing, sentence-after-the-last-in-testing …
ignore-before-first-semicolon: killed [additive:clause-start] by case-in-pyproject, case-in-testing, changed-in-conventions, changed-in-pyproject …
ignore-except-clauses: killed [additive:clause] by clause-at-end-in-pyproject, clause-at-end-in-testing, clause-at-start-in-pyproject, clause-at-start-in-testing …
ignore-after-last-sentence-period: killed [additive:clause-after] by sentence-after-the-last-in-testing
lazy-wrap-joins(equivalent?): killed [additive:lazy] by lazy-wrap-in-testing
lazy-continuation-ok: killed [additive:lazy] by clause-lazy-after-last-item
same-depth-other-bullet-ends: killed [additive:bullet] by third-marker-other-bullet-in-testing
same-depth-any-item-ends: killed [additive:bullet] by third-marker-other-bullet-in-testing
anything-after-blank-ok: killed [additive:paragraph] by clause-after-a-blank-in-last-item, third-marker-after-a-blank-in-testing
after-blank-same-depth-item-ok: killed [additive:paragraph] by third-marker-after-a-blank-in-testing
other-bullets-are-items: killed [additive:bullet] by star-bullets-in-testing
deeper-wrap-ok: killed [additive:whitespace] by over-indented-wrap-in-testing
wrap-joins-tab-indent: killed [additive:whitespace] by over-indented-wrap-in-testing
statement-line-strip(): killed [additive:whitespace] by statement-line-tab-indented-items-follow-in-testing, statement-line-trailing-space-in-testing
statement-line-lstrip(): killed [additive:whitespace] by statement-line-tab-indented-items-follow-in-testing
statement-line-substring: killed [additive:statement] by statement-line-quoted-in-testing
statement-line-prefix: killed [additive:statement] by statement-line-tail-changed-in-testing
statement-line-casefold: killed [additive:case] by statement-line-lower-case-in-testing
ignore-slashes: killed [additive:punctuation] by slash-dropped-in-pyproject
ignore-hyphens: killed [additive:punctuation] by hyphen-dropped-in-testing
ignore-apostrophes: killed [additive:punctuation] by curly-quote-in-testing
74 mutants, 0 not killed
```
