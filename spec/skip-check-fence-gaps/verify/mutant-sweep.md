# Mutant sweep — `skip_violations` and its helpers (review cycle 1, F3; review cycle 2, A and B)

Every decision in `skip_violations`, `_module_bindings`, `_allowed` and the `.Exception` / `raise`
exemption, reverted one at a time, against the planted rows of `test_skip_check_catches_planted_skips`.
Run 2026-11-09 on the remediation tree, Python 3.14, by the driver at the end of this file.

**How a mutant is planted.** The check (`SKIPPERS`, `SKIP_HELPERS`, `CONFTESTS`, `SCOPES`,
`_module_bindings`, `_allowed`, `skip_violations`) is extracted from the working copy of
`tests/test_hygiene.py`, and each mutant is one exact text replacement in it, anchored on the
decision's own line and required to occur exactly once, so a botched mutant stops the sweep instead
of reading as a survivor. The check's code is the reviewed commit's (`900d9f4`): this remediation
adds rows only.

**What kills a mutant.** A row kills it when the mutant's verdict (`bool(report)`, the very
assertion the row test makes) differs from the row's `found`, or when the check raises. *Suite*
marks a mutant that also reports, or raises, over the tree's `tests/*.py`, which is what
`test_only_need_shell_skips` asserts. The kills are exact verdicts on parsed text: nothing is timed,
so load cannot move them.

**Before and after.** "Reviewed rows" are the 29 rows of `900d9f4` (the commit the review read);
"rows now" are the 46 rows of this remediation. A mutant that survives the reviewed rows and dies
on the rows now is a gap a new row closed; every new row kills at least one such mutant. The
reviewer's M1–M11 keep their numbers (M6 is the finding).

| Mutant | Decision reverted | Killed by, reviewed rows | Killed by, rows now | Suite |
|---|---|---|---|---|
| M1 | conftest by path | `look-alike-conftest`, `another-conftest` | `look-alike-conftest`, `another-conftest` | — |
| M1a | the bare name is the conftest | `need-shell`, `need-git`, `closure-inside-the-helper` | 6 rows, among them `need-shell` | — |
| M1b | the scanned path is the conftest | — | — | yes |
| M6 | a second binding is reported | — | `helper-defined-twice-without-a-skip` | — |
| M26 | only a single binding allows | — | **equivalent** (below) | — |
| M10 | every binding counts, not only defs | — | **equivalent** (below) | — |
| M27 | only a def allows (not a class) | — | `helper-as-a-class` | — |
| M28 | only a def allows (not an async def) | — | `helper-as-an-async-def` | — |
| M3 | the def is top-level | — | **equivalent** (below) | — |
| M29 | the body allows, not decorators or defaults | — | `skip-on-the-helpers-decorator` | — |
| M42 | helpers in sorted order | — | **equivalent** (below) | — |
| M2 | nested helper-named scopes subtracted | `helper-nested-in-the-helper` | `helper-nested-in-the-helper`, `async-helper-nested-in-the-helper` | — |
| M2a | only helper-named scopes subtracted | `closure-inside-the-helper` | `closure-inside-the-helper` | — |
| M2b | only scopes below the top level subtracted | `need-shell`, `need-git`, `closure-inside-the-helper` | 5 rows, among them `need-shell` | yes |
| M20 | SCOPES holds def | `need-shell`, `need-git`, `closure-inside-the-helper` | 6 rows, among them `need-shell` | yes |
| M21 | SCOPES holds async def | — | `async-helper-nested-in-the-helper` | — |
| M22 | SCOPES holds class | — | `helper-rebound-by-a-class` | — |
| M23 | SCOPES holds lambda | — | `helper-name-bound-inside-a-lambda` | — |
| M16 | a def or class of the name binds | `need-shell`, `need-git`, `closure-inside-the-helper` | 6 rows, among them `need-shell` | yes |
| M17 | a scope's body is not module scope | — | `helper-name-local-to-another-function`, `helper-name-bound-inside-a-lambda` | — |
| M18 | a scope's decorators, defaults and bases are module scope | — | `helper-rebound-in-a-default` | — |
| M19 | a lambda's body is one expression | — | `helper-name-bound-inside-a-lambda` | — |
| M24 | statements are walked into | `helper-rebound`, `helper-rebound-by-import` | 9 rows, among them `helper-rebound` | — |
| M9 | a store binds | `helper-rebound` | `helper-rebound`, `helper-rebound-in-a-default`, `helper-deleted` | — |
| M9a | a delete binds | — | `helper-deleted` | — |
| M8 | an import binds | `helper-rebound-by-import` | `helper-rebound-by-import`, `helper-rebound-by-a-dotted-import` | — |
| M8a | an unaliased import binds | — | `helper-rebound-by-a-dotted-import` | — |
| M8b | a dotted import binds its first part | — | `helper-rebound-by-a-dotted-import` | — |
| M12 | except as binds | — | `helper-rebound-by-except` | — |
| M13 | a match capture binds | — | `helper-rebound-by-a-match-capture` | — |
| M14 | a match star binds | — | `helper-rebound-by-a-match-star` | — |
| M15 | a mapping rest binds | — | `helper-rebound-by-a-match-rest` | — |
| M7 | a global binds | `helper-rebound-by-global` | `helper-rebound-by-global` | — |
| M7a | a global anywhere binds | `helper-rebound-by-global` | `helper-rebound-by-global` | — |
| M25 | bindings in line order | — | **equivalent** (below) | — |
| M35 | skip is a skipper | 15 rows, among them `skip` | 18 rows, among them `skip` | — |
| M36 | skipif is a skipper | `skipif` | `skipif`, `skip-on-the-helpers-decorator` | — |
| M37 | importorskip is a skipper | `importorskip` | `importorskip` | — |
| M38 | xfail is a skipper | `raised-xfail-outcome` | `raised-xfail-outcome` | — |
| M40 | need_shell is a helper | `need-shell`, `closure-inside-the-helper` | `need-shell`, `closure-inside-the-helper`, `helper-name-local-to-another-function` | yes |
| M41 | need_git is a helper | `need-git` | `need-git`, `helper-defined-twice-without-a-skip`, `helper-name-bound-inside-a-lambda` | yes |
| M33 | a name is a word | `importorskip`, `raised-outcome-of-a-bare-skip` | `importorskip`, `raised-outcome-of-a-bare-skip` | — |
| M34 | an attribute is a word | 16 rows, among them `skip` | 20 rows, among them `skip` | — |
| M39 | a skip in a helper is allowed | `need-shell`, `need-git`, `closure-inside-the-helper` | 5 rows, among them `need-shell` | yes |
| M32 | the outcome type as a value is exempt | `outcome-type`, `outcome-type-as-an-argument`, `outcome-type-caught` | 4 rows, among them `outcome-type` | yes |
| M32a | the skipper under `.Exception` is the one exempt | `outcome-type`, `outcome-type-as-an-argument`, `outcome-type-caught` | 4 rows, among them `outcome-type` | yes |
| M4 | only `.Exception` names the outcome type | 6 rows, among them `skip-through-an-attribute` | 6 rows, among them `skip-through-an-attribute` | — |
| M5 | a raised outcome type is not exempt | 4 rows, among them `raised-skip-outcome` | 4 rows, among them `raised-skip-outcome` | — |
| M11 | the raise's whole expression is raised | `raised-skip-outcome`, `raised-xfail-outcome`, `raised-outcome-of-a-bare-skip` | `raised-skip-outcome`, `raised-xfail-outcome`, `raised-outcome-of-a-bare-skip` | — |
| M30 | a raise's cause is not raised | — | `outcome-type-as-a-cause` | — |
| M31 | a bare raise raises nothing | — | `bare-reraise` | yes |

Every mutant is killed by a planted row except M1b and the five equivalents.

**M1b** (the scanned absolute path `tests/conftest.py` is the conftest) is killed only by
`test_only_need_shell_skips`: with it reverted, the real `need_shell` and `need_git` skips are
reported. No planted row can carry that path: it is the checkout's own absolute path, and a row is a
plain literal (the gate's `kept` check).

## Equivalent mutants

Each was run over every row of both sets and every `tests/*.py` module: the verdict differs on none.

- **M3, the helper must be a top-level `def`.** Dropping the `tree.body` membership test lets a
  single `def` binding under an `if`, `try` or `with` allow its body, but `_allowed`'s last loop then
  subtracts the whole subtree of every helper-named `def`, `async def` or class that is not a direct
  member of `tree.body`, and the body that was added is inside that subtree. The two tests are
  redundant by construction: the reports are identical on every input, not only the verdicts (0
  differing reports). `helper-below-the-top-level` is the row for the decision; it holds through
  either test, and dies only when both go (M2 + M3).
- **M10, every binding counts (not only `def`s), and M26, only a single binding allows.** Both
  change which binding allows when a helper is bound more than once. In that case the `defined
  again` report is already in the list, so the verdict is a violation either way; what changes is
  only whether the skip lines inside the first binding are listed too (18 inputs differ in report
  text, none in verdict). `test_only_need_shell_skips` asserts the list is empty and the row test
  asserts its truth, so neither can see the difference, and the fence fails the same file either
  way. Pinning the report text would mean changing the row test's body, which R6 and the gate's
  `bodies` check keep as it is.
- **M25, bindings sorted by line.** The order only decides which binding's line goes unnamed (the
  first); `single` is read only when there is exactly one binding, and the count of `defined again`
  reports is the same. Verdicts never differ; 17 reports differ in the line they name.
- **M42, helpers taken in sorted order.** `allowed` is a union and the reports are compared as a
  set: the order changes nothing (0 differing reports). It makes the report order deterministic.

## Driver

Saved as a file outside the worktree and run from the worktree root, with the reviewed rows taken
from the reviewed commit:

```
git show 900d9f4:tests/test_hygiene.py > "$TMPDIR/reviewed_hygiene.py"
uv run python -I "$TMPDIR/sweep.py" "$TMPDIR/reviewed_hygiene.py" tests/test_hygiene.py
```

Each output line is `mutant | decision | killers, first rows file | killers, second | suite |
differing verdicts and reports over every row and suite module`.

```python
"""Mutant sweep over every decision in `skip_violations` and its helpers.

Usage (from the worktree root):
    uv run python -I sweep.py ROWS_SOURCE [ROWS_SOURCE ...]

The check is extracted from the working copy of tests/test_hygiene.py; each mutant is one exact
text replacement in it, which must occur exactly once (so a botched mutant fails loudly). Each
ROWS_SOURCE is a test_hygiene.py whose planted rows are run against every mutant: a row kills a
mutant when the mutant's verdict (`bool(report)`) differs from the row's `found`, or the check
raises. `suite` kills a mutant when it reports anything, or raises, over the working tree's
tests/*.py (what `test_only_need_shell_skips` asserts).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path.cwd()
TESTS = ROOT / 'tests'
SRC = (TESTS / 'test_hygiene.py').read_text()
NAMES = {'SKIPPERS', 'SKIP_HELPERS', 'CONFTESTS', 'SCOPES', '_module_bindings', '_allowed', 'skip_violations'}
CHECK = '\n\n'.join(ast.get_source_segment(SRC, n) for n in ast.parse(SRC).body
                    if (isinstance(n, ast.FunctionDef) and n.name in NAMES)
                    or (isinstance(n, ast.Assign) and any(getattr(t, 'id', None) in NAMES for t in n.targets)))

M = {
    # _allowed: which module is the suite's conftest
    'M1': ('conftest by path', "if Path(name) not in CONFTESTS:", "if not name.endswith('conftest.py'):"),
    'M1a': ('the bare name is the conftest', "CONFTESTS = {Path('conftest.py'), TESTS / 'conftest.py'}",
            "CONFTESTS = {TESTS / 'conftest.py'}"),
    'M1b': ('the scanned path is the conftest', "CONFTESTS = {Path('conftest.py'), TESTS / 'conftest.py'}",
            "CONFTESTS = {Path('conftest.py')}"),
    # _allowed: one binding, a top-level def, its body
    'M6': ('a second binding is reported',
           "found.extend(f'{name}:{n.lineno}: {helper} defined again' for n in bindings[1:])", "pass"),
    'M26': ('only a single binding allows', "single = bindings[0] if len(bindings) == 1 else None",
            "single = bindings[0] if bindings else None"),
    'M10': ('every binding counts, not only defs', "single = bindings[0] if len(bindings) == 1 else None",
            "single = next((b for b in bindings if isinstance(b, ast.FunctionDef)), None)"),
    'M27': ('only a def allows (not a class)', "if isinstance(single, ast.FunctionDef) and",
            "if isinstance(single, (ast.FunctionDef, ast.ClassDef)) and"),
    'M28': ('only a def allows (not an async def)', "if isinstance(single, ast.FunctionDef) and",
            "if isinstance(single, (ast.FunctionDef, ast.AsyncFunctionDef)) and"),
    'M3': ('the def is top-level', "if isinstance(single, ast.FunctionDef) and any(single is n for n in tree.body):",
           "if isinstance(single, ast.FunctionDef):"),
    'M29': ('the body allows, not decorators or defaults',
            "allowed |= {id(n) for statement in single.body for n in ast.walk(statement)}",
            "allowed |= {id(n) for n in ast.walk(single)}"),
    'M42': ('helpers in sorted order', "for helper in sorted(SKIP_HELPERS):", "for helper in SKIP_HELPERS:"),
    # _allowed: a helper's name below the top level is never the helper
    'M2': ('nested helper-named scopes subtracted', "            allowed -= {id(n) for n in ast.walk(node)}",
           "            pass"),
    'M2a': ('only helper-named scopes subtracted', "and getattr(node, 'name', None) in SKIP_HELPERS\n", "\n"),
    'M2b': ('only scopes below the top level subtracted', "                and not any(node is n for n in tree.body)):",
            "                ):"),
    # _module_bindings: where module scope ends
    'M20': ('SCOPES holds def', "SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)",
            "SCOPES = (ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)"),
    'M21': ('SCOPES holds async def', "SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)",
            "SCOPES = (ast.FunctionDef, ast.ClassDef, ast.Lambda)"),
    'M22': ('SCOPES holds class', "SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)",
            "SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)"),
    'M23': ('SCOPES holds lambda', "SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)",
            "SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)"),
    'M16': ('a def or class of the name binds', "if getattr(node, 'name', None) == helper:", "if False:"),
    'M17': ("a scope's body is not module scope",
            "pending += [c for c in ast.iter_child_nodes(node) if not any(c is b for b in body)]",
            "pending += ast.iter_child_nodes(node)"),
    'M18': ("a scope's decorators, defaults and bases are module scope",
            "pending += [c for c in ast.iter_child_nodes(node) if not any(c is b for b in body)]", "pass"),
    'M19': ("a lambda's body is one expression", "body = node.body if isinstance(node.body, list) else [node.body]",
            "body = node.body if isinstance(node.body, list) else []"),
    'M24': ('statements are walked into', "pending += ast.iter_child_nodes(node)\n", "pass\n"),
    # _module_bindings: what binds
    'M9': ('a store binds', "bound = node.id if not isinstance(node.ctx, ast.Load) else None", "bound = None"),
    'M9a': ('a delete binds', "bound = node.id if not isinstance(node.ctx, ast.Load) else None",
            "bound = node.id if isinstance(node.ctx, ast.Store) else None"),
    'M8': ('an import binds', "bound = node.asname or node.name.split('.')[0]", "bound = None"),
    'M8a': ('an unaliased import binds', "bound = node.asname or node.name.split('.')[0]", "bound = node.asname"),
    'M8b': ('a dotted import binds its first part', "bound = node.asname or node.name.split('.')[0]",
            "bound = node.asname or node.name"),
    'M12': ('except as binds', "(ast.ExceptHandler, ast.MatchAs, ast.MatchStar)", "(ast.MatchAs, ast.MatchStar)"),
    'M13': ('a match capture binds', "(ast.ExceptHandler, ast.MatchAs, ast.MatchStar)",
            "(ast.ExceptHandler, ast.MatchStar)"),
    'M14': ('a match star binds', "(ast.ExceptHandler, ast.MatchAs, ast.MatchStar)",
            "(ast.ExceptHandler, ast.MatchAs)"),
    'M15': ('a mapping rest binds', "bound = node.rest", "bound = None"),
    'M7': ('a global binds', "bindings += [n for n in ast.walk(tree) if isinstance(n, ast.Global) and helper in n.names]",
           "pass"),
    'M7a': ('a global anywhere binds', "for n in ast.walk(tree) if isinstance(n, ast.Global)",
            "for n in tree.body if isinstance(n, ast.Global)"),
    'M25': ('bindings in line order', "return sorted(bindings, key=lambda n: (n.lineno, n.col_offset))",
            "return bindings"),
    # skip_violations: what counts as a skip
    'M35': ('skip is a skipper', "SKIPPERS = {'skip', 'skipif', 'importorskip', 'xfail'}",
            "SKIPPERS = {'skipif', 'importorskip', 'xfail'}"),
    'M36': ('skipif is a skipper', "SKIPPERS = {'skip', 'skipif', 'importorskip', 'xfail'}",
            "SKIPPERS = {'skip', 'importorskip', 'xfail'}"),
    'M37': ('importorskip is a skipper', "SKIPPERS = {'skip', 'skipif', 'importorskip', 'xfail'}",
            "SKIPPERS = {'skip', 'skipif', 'xfail'}"),
    'M38': ('xfail is a skipper', "SKIPPERS = {'skip', 'skipif', 'importorskip', 'xfail'}",
            "SKIPPERS = {'skip', 'skipif', 'importorskip'}"),
    'M40': ('need_shell is a helper', "SKIP_HELPERS = {'need_shell', 'need_git'}", "SKIP_HELPERS = {'need_git'}"),
    'M41': ('need_git is a helper', "SKIP_HELPERS = {'need_shell', 'need_git'}", "SKIP_HELPERS = {'need_shell'}"),
    'M33': ('a name is a word', "word = node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None",
            "word = node.attr if isinstance(node, ast.Attribute) else None"),
    'M34': ('an attribute is a word', "word = node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None",
            "word = node.id if isinstance(node, ast.Name) else None"),
    'M39': ('a skip in a helper is allowed', "and id(node) not in allowed and", "and"),
    # skip_violations: the `.Exception` exemption and `raise`
    'M32': ('the outcome type as a value is exempt', " and id(node) not in named:", ":"),
    'M32a': ("the skipper under `.Exception` is the one exempt", "named = {id(node.value) for node", "named = {id(node) for node"),
    'M4': ('only `.Exception` names the outcome type',
           "if isinstance(node, ast.Attribute) and node.attr == 'Exception' and id(node) not in raised}",
           "if isinstance(node, ast.Attribute)}"),
    'M5': ('a raised outcome type is not exempt', "and node.attr == 'Exception' and id(node) not in raised}",
           "and node.attr == 'Exception'}"),
    'M11': ("the raise's whole expression is raised", "for n in ast.walk(r.exc)}", "for n in [r.exc]}"),
    'M30': ("a raise's cause is not raised", "for n in ast.walk(r.exc)}", "for n in ast.walk(r)}"),
    'M31': ('a bare raise raises nothing', "if isinstance(r, ast.Raise) and r.exc is not None for n",
            "if isinstance(r, ast.Raise) for n"),
}


def build(src: str):
    space = {'ast': ast, 'Path': Path, 'TESTS': TESTS}
    exec(compile(src, 'check', 'exec'), space)
    return space['skip_violations']


def rows(path: Path) -> list[tuple[str, str, str, bool]]:
    tree = ast.parse(path.read_text())
    test = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'test_skip_check_catches_planted_skips')
    deco = next(d for d in test.decorator_list if isinstance(d, ast.Call) and ast.unparse(d.func).endswith('parametrize'))
    return [(next(k.value.value for k in p.keywords if k.arg == 'id'), *(ast.literal_eval(a) for a in p.args))
            for p in deco.args[1].elts]


def verdict(check, name, text):
    try:
        return bool(check(name, text))
    except Exception as error:  # A check that raises fails the row.
        return f'raises {type(error).__name__}'


SUITE = {str(f): f.read_text() for f in sorted(TESTS.glob('*.py'))}


def suite_kills(check) -> bool:
    try:
        return any(check(n, t) for n, t in SUITE.items())
    except Exception:
        return True


def main(sources: list[str]) -> int:
    row_sets = {s: rows(Path(s)) for s in sources}
    shipped = build(CHECK)
    assert not suite_kills(shipped), 'the unmutated check reports in the suite'
    for s, rs in row_sets.items():
        bad = [r[0] for r in rs if verdict(shipped, r[1], r[2]) is not r[3]]
        assert rs and not bad, (s, bad)
        print(f'rows {s}: {len(rs)}, all met by the unmutated check')
    probes = [(n, t) for rs in row_sets.values() for _, n, t, _ in rs] + list(SUITE.items())
    for key, (decision, old, new) in M.items():
        if CHECK.count(old) != 1:
            print(f'{key}: anchor occurs {CHECK.count(old)} times: {old!r}')
            return 1
        mutant = CHECK.replace(old, new)
        assert mutant != CHECK
        check = build(mutant)
        cells = []
        for s, rs in row_sets.items():
            killers = [rid for rid, n, t, f in rs if verdict(check, n, t) is not f]
            cells.append(','.join(killers) or '-')
        suite = 'suite' if suite_kills(check) else '-'
        diff = sum(verdict(check, n, t) != verdict(shipped, n, t) for n, t in probes)
        reports = sum(_report(check, n, t) != _report(shipped, n, t) for n, t in probes)
        print(f'{key:5} | {decision} | ' + ' | '.join(cells) + f' | {suite} | verdicts differ {diff}, reports {reports}')
    return 0


def _report(check, name, text):
    try:
        return sorted(check(name, text))
    except Exception as error:
        return type(error).__name__


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
```

## Review cycle 2 (A, B)

Run 2026-11-09 on this remediation's tree, Python 3.14, by the second driver below. The check's code
changes in this remediation: `_scope_bindings` reads stores per scope, `_module_bindings` counts a
`global` only beside a store, and `_raised` follows what a raise hands on as its exception. The
cycle-1 mutants are re-anchored on the new code where it moved (M7, M7a, M11, M17–M19, M24, M30,
M31); the new decisions are B1–B9 (bindings) and R1–R9 (raises); M43 and M44 are the reviewer's
surviving V54 and V40.

**Two ways of killing, both eras.** Each mutant is planted twice. In process, as before: a row kills
it when the mutant's verdict differs from the row's `found`, and *suite* when it reports over the
tree's `tests/*.py`. Under pytest: the mutant is written into the working copy of
`tests/test_hygiene.py`, `test_skip_check_catches_planted_skips` and `test_only_need_shell_skips`
run in the handshake era and again with `CLUSTER_MCP_TEST_ERA=modern`, and the file is restored and
compared byte for byte after each (it was). The two agree on every mutant: 67 of 74 red in each era,
and the seven equivalents green. The check is a parse of text, so the era changes nothing; the
pytest pass is the proof that the in-process verdict is the suite's.

**The reviewed checks against the rows now.** The check extracted from `900d9f4` and from `fb96211`
each fails 9 of the 67 rows, exactly the review's A and its sibling: `outcome-type-in-a-raised-argument`,
`-message`, `-repr`, `outcome-types-attribute-raised`, `outcome-type-as-a-conditionals-test`,
`helper-annotated-without-a-value`, `helper-name-in-a-comprehension`,
`helper-declared-global-without-a-store` and `helper-declared-global-at-module-scope`. The base
check (`0bfacae27`) fails 38: every added row that expects a report, except `helper-as-a-class`
and `helper-as-an-async-def`, which the base reported too.
`helper-read-at-module-scope` and `helper-stored-beside-another-global` pass on the reviewed check:
they pin decisions it already made, and kill B1 (the reviewer's V16) and B6.

| Mutant | Decision reverted | Killed by, rows of `fb96211` | Killed by, rows now | Suite | pytest, handshake · modern |
|---|---|---|---|---|---|
| M1 | conftest by path | `look-alike-conftest`, `another-conftest` | `look-alike-conftest`, `another-conftest` | — | red · red |
| M1a | the bare name is the conftest | 6 rows, among them `need-shell` | 12 rows, among them `need-shell` | — | red · red |
| M1b | the scanned path is the conftest | — | — | yes | red · red |
| M6 | a second binding is reported | `helper-defined-twice-without-a-skip` | `helper-defined-twice-without-a-skip` | — | red · red |
| M26 | only a single binding allows | — | **equivalent** (below) | — | green · green |
| M10 | every binding counts, not only defs | — | **equivalent** (below) | — | green · green |
| M27 | only a def allows (not a class) | `helper-as-a-class` | `helper-as-a-class` | — | red · red |
| M28 | only a def allows (not an async def) | `helper-as-an-async-def` | `helper-as-an-async-def` | — | red · red |
| M3 | the def is top-level | — | **equivalent** (below) | — | green · green |
| M29 | the body allows, not decorators or defaults | `skip-on-the-helpers-decorator` | `skip-on-the-helpers-decorator`, `skip-in-a-one-line-helpers-default` | — | red · red |
| M43 | allowed by node, not by line (V54) | — | `skip-in-a-one-line-helpers-default` | — | red · red |
| M42 | helpers in sorted order | — | **equivalent** (below) | — | green · green |
| M2 | nested helper-named scopes subtracted | `helper-nested-in-the-helper`, `async-helper-nested-in-the-helper` | 3 rows, among them `helper-nested-in-the-helper` | — | red · red |
| M44 | a helper-named class is subtracted too (V40) | — | `helper-named-class-in-the-helper` | — | red · red |
| M2a | only helper-named scopes subtracted | `closure-inside-the-helper` | `closure-inside-the-helper` | — | red · red |
| M2b | only scopes below the top level subtracted | 5 rows, among them `need-shell` | 11 rows, among them `need-shell` | yes | red · red |
| M20 | SCOPES holds def | 6 rows, among them `need-shell` | 12 rows, among them `need-shell` | yes | red · red |
| M21 | SCOPES holds async def | `async-helper-nested-in-the-helper` | `async-helper-nested-in-the-helper` | — | red · red |
| M22 | SCOPES holds class | `helper-rebound-by-a-class` | `helper-rebound-by-a-class`, `helper-named-class-in-the-helper` | — | red · red |
| M23 | SCOPES holds lambda | `helper-name-bound-inside-a-lambda` | `helper-name-bound-inside-a-lambda` | — | red · red |
| M16 | a def or class of the name binds | 6 rows, among them `need-shell` | 12 rows, among them `need-shell` | yes | red · red |
| M17 | a scope's body is not the enclosing scope | `helper-name-local-to-another-function`, `helper-name-bound-inside-a-lambda` | 3 rows, among them `helper-name-local-to-another-function` | — | red · red |
| M18 | a scope's decorators, defaults and bases are the enclosing scope | `helper-rebound-in-a-default` | `helper-rebound-in-a-default` | — | red · red |
| M19 | a lambda's body is one expression | `helper-name-bound-inside-a-lambda` | `helper-name-bound-inside-a-lambda` | — | red · red |
| M24 | statements are walked into | 10 rows, among them `helper-rebound` | 13 rows, among them `helper-rebound` | — | red · red |
| M9 | a store binds | 4 rows, among them `helper-rebound` | 7 rows, among them `helper-rebound` | — | red · red |
| M9a | a delete binds | `helper-deleted` | `helper-deleted` | — | red · red |
| B1 | a load binds nothing (V16) | — | 3 rows, among them `helper-read-at-module-scope` | — | red · red |
| B2 | a comprehension's own variable binds nothing | — | `helper-name-in-a-comprehension` | — | red · red |
| B3 | an annotation with no value binds nothing | — | `helper-annotated-without-a-value` | — | red · red |
| B4 | an annotation with a value binds | — | `helper-rebound-by-an-annotated-assignment` | — | red · red |
| B5 | a comprehension's iterables and conditions are the enclosing scope | — | `helper-rebound-by-a-walrus-in-a-comprehension` | — | red · red |
| B5a | a comprehension or bare annotation stops there | — | `helper-annotated-without-a-value`, `helper-name-in-a-comprehension` | — | red · red |
| M8 | an import binds | `helper-rebound-by-import`, `helper-rebound-by-a-dotted-import` | `helper-rebound-by-import`, `helper-rebound-by-a-dotted-import` | — | red · red |
| M8a | an unaliased import binds | `helper-rebound-by-a-dotted-import` | `helper-rebound-by-a-dotted-import` | — | red · red |
| M8b | a dotted import binds its first part | `helper-rebound-by-a-dotted-import` | `helper-rebound-by-a-dotted-import` | — | red · red |
| M12 | except as binds | `helper-rebound-by-except` | `helper-rebound-by-except` | — | red · red |
| M13 | a match capture binds | `helper-rebound-by-a-match-capture` | `helper-rebound-by-a-match-capture` | — | red · red |
| M14 | a match star binds | `helper-rebound-by-a-match-star` | `helper-rebound-by-a-match-star` | — | red · red |
| M15 | a mapping rest binds | `helper-rebound-by-a-match-rest` | `helper-rebound-by-a-match-rest` | — | red · red |
| M7 | a global with a store binds | `helper-rebound-by-global` | `helper-rebound-by-global`, `helper-rebound-by-global-in-a-method` | — | red · red |
| M7b | a global is declared in its scope | `helper-rebound-by-global` | `helper-rebound-by-global`, `helper-rebound-by-global-in-a-method` | — | red · red |
| B6 | only a global naming the helper | — | `helper-stored-beside-another-global` | — | red · red |
| B6a | a global stops there | — | **equivalent** (below) | — | green · green |
| B7 | only a global paired with a store | — | `helper-declared-global-without-a-store` | — | red · red |
| B8 | the module's own globals bind nothing | — | `helper-declared-global-at-module-scope` | — | red · red |
| M7a | a global at any depth counts | — | `helper-rebound-by-global-in-a-method` | — | red · red |
| B9 | a lambda holds no global | `helper-name-bound-inside-a-lambda` | `helper-name-bound-inside-a-lambda` | — | red · red |
| M25 | bindings in line order | — | **equivalent** (below) | — | green · green |
| M35 | skip is a skipper | 18 rows, among them `skip` | 23 rows, among them `skip` | — | red · red |
| M36 | skipif is a skipper | `skipif`, `skip-on-the-helpers-decorator` | `skipif`, `skip-on-the-helpers-decorator` | — | red · red |
| M37 | importorskip is a skipper | `importorskip` | `importorskip` | — | red · red |
| M38 | xfail is a skipper | `raised-xfail-outcome` | 3 rows, among them `raised-xfail-outcome` | — | red · red |
| M40 | need_shell is a helper | 3 rows, among them `need-shell` | 3 rows, among them `need-shell` | yes | red · red |
| M41 | need_git is a helper | 3 rows, among them `need-git` | 10 rows, among them `need-git` | yes | red · red |
| M33 | a name is a word | `importorskip`, `raised-outcome-of-a-bare-skip` | `importorskip`, `raised-outcome-of-a-bare-skip` | — | red · red |
| M34 | an attribute is a word | 20 rows, among them `skip` | 27 rows, among them `skip` | — | red · red |
| M39 | a skip in a helper is allowed | 5 rows, among them `need-shell` | 11 rows, among them `need-shell` | yes | red · red |
| M32 | the outcome type as a value is exempt | 4 rows, among them `outcome-type` | 9 rows, among them `outcome-type` | yes | red · red |
| M32a | the skipper under `.Exception` is the one exempt | 4 rows, among them `outcome-type` | 9 rows, among them `outcome-type` | yes | red · red |
| M4 | only `.Exception` names the outcome type | 6 rows, among them `skip-through-an-attribute` | 11 rows, among them `skip-through-an-attribute` | — | red · red |
| M5 | a raised outcome type is not exempt | 4 rows, among them `raised-skip-outcome` | 9 rows, among them `raised-skip-outcome` | — | red · red |
| M11 | everything under a raise's exception is raised (the reviewed rule) | — | 5 rows, among them `outcome-type-in-a-raised-argument` | — | red · red |
| M30 | a raise's cause is not raised | `outcome-type-as-a-cause` | `outcome-type-as-a-cause` | — | red · red |
| M31 | a bare raise raises nothing | — | **equivalent** (below) | — | green · green |
| R1 | a call hands on what it calls | 3 rows, among them `raised-skip-outcome` | 8 rows, among them `raised-skip-outcome` | — | red · red |
| R2 | a called method hands on its value | `raised-outcome-of-a-bare-skip` | `raised-outcome-of-a-bare-skip` | — | red · red |
| R3 | only a called attribute hands on its value | — | `outcome-types-attribute-raised` | — | red · red |
| R4 | an argument is not raised | — | `outcome-type-in-a-raised-argument`, `outcome-type-in-a-raised-repr` | — | red · red |
| R5 | a conditional's body is raised | — | `raised-outcome-in-a-conditional` | — | red · red |
| R6 | a conditional's else is raised | — | `raised-outcome-in-a-conditionals-else` | — | red · red |
| R7 | a conditional's test is not raised | — | `outcome-type-as-a-conditionals-test` | — | red · red |
| R8 | a walrus hands on its value | — | `raised-outcome-through-a-walrus` | — | red · red |
| R9 | a boolean hands on each operand | — | `raised-outcome-in-a-boolean` | — | red · red |

Every mutant is killed by a planted row except M1b, killed by `test_only_need_shell_skips` as in
cycle 1, and the seven equivalents. No survivor breaks an R-ID.

**The reviewer's survivors.** V16 (a load binds) is B1, killed by `helper-read-at-module-scope`. V40
(the subtraction ignores a class) is M44, killed by `helper-named-class-in-the-helper`: PLAN § 2
step 5 subtracts a helper-named class too. V54 (admission by line, not node) is M43, killed by
`skip-in-a-one-line-helpers-default`. V26, V32/V33, V35 and V42 are M25, M26/M10, M3 and M42,
equivalent as cycle 1 recorded, and re-run here with the same result (0 differing verdicts). V45
(a bare raise unguarded) is M31, equivalent now (below).

### Equivalent mutants, review cycle 2

M3, M10, M26, M25 and M42 stand as recorded above, each re-run over the 67 rows and every suite
module: 0 differing verdicts. Two are new.

- **M31, a bare raise raises nothing.** Without the `r.exc is not None` guard, a bare `raise` puts
  `None` on `_raised`'s list; `id(None)` joins the set and no `isinstance` branch matches it.
  `named` is keyed on the ids of `.Exception` attribute nodes, and `None` is never one, so no
  verdict or report changes (0 differing reports). Under cycle 1's code the same mutant crashed
  `ast.walk(None)`, which is why `bare-reraise` killed it then. The guard stays: it keeps a
  non-node out of a set of node ids.
- **B6a, a `global` stops there.** Without the `continue` after a `global`, the node falls through
  to the store branches, none of which matches an `ast.Global`, and it has no child nodes to push.
  0 differing reports.

One branch has no mutant of its own: for an annotation with no value, `_scope_bindings` still walks
the annotation. No binding can sit there in code Python compiles: a walrus in an annotation is a
`SyntaxError` ("named expression cannot be used within an annotation", Python 3.14), and an
annotation holds no statement. Likewise a comprehension's first iterable can hold no binding
("assignment expression cannot be used in a comprehension iterable expression"), so B5 (iterables
and conditions are the enclosing scope) is killed through the conditions, by
`helper-rebound-by-a-walrus-in-a-comprehension`.

### Driver, review cycle 2

Saved as a file outside the worktree and run from the worktree root, the row sets taken from the
two reviewed commits:

```
git show 900d9f4:tests/test_hygiene.py > "$TMPDIR/reviewed1_hygiene.py"
git show fb96211:tests/test_hygiene.py > "$TMPDIR/reviewed_hygiene.py"
uv run python -I "$TMPDIR/sweep.py" rows "$TMPDIR/reviewed1_hygiene.py" "$TMPDIR/reviewed_hygiene.py"
uv run python -I "$TMPDIR/sweep.py" checks "$TMPDIR/base_hygiene.py" "$TMPDIR/reviewed1_hygiene.py" "$TMPDIR/reviewed_hygiene.py"
uv run python -I "$TMPDIR/sweep.py" pytest legacy "$TMPDIR/pytest-legacy.log"
uv run python -I "$TMPDIR/sweep.py" pytest modern "$TMPDIR/pytest-modern.log"
```

(`base_hygiene.py` is `git show 0bfacae27:tests/test_hygiene.py`.) In the table, a row column lists
the rows that kill the mutant; the pytest column is the two skip-check tests' result with the
mutant planted.

```python
"""Mutant sweep over every decision in `skip_violations` and its helpers (review cycle 2).

Usage (from the worktree root):
    uv run python -I sweep.py rows ROWS_SOURCE [ROWS_SOURCE ...]
    uv run python -I sweep.py checks CHECK_SOURCE [CHECK_SOURCE ...]
    uv run python -I sweep.py pytest ERA OUT

`rows`: the check is extracted from the working copy of tests/test_hygiene.py; each mutant is one
exact text replacement in it, which must occur exactly once in the check and in the whole file (so
a botched mutant fails loudly). Each ROWS_SOURCE is a test_hygiene.py whose planted rows are run
against every mutant: a row kills a mutant when the mutant's verdict (`bool(report)`) differs from
the row's `found`, or the check raises. `suite` kills a mutant when it reports anything, or raises,
over the working tree's tests/*.py (what `test_only_need_shell_skips` asserts).

`checks`: the check extracted from each CHECK_SOURCE (an earlier commit's test_hygiene.py), run
against the working copy's rows: the rows it fails.

`pytest`: each mutant planted into the working copy of tests/test_hygiene.py in turn, the two
skip-check tests run by pytest in the era ERA (`legacy` or `modern`), and the file restored (and
compared byte for byte) after each; one line per mutant, `red` or `green`, is written to OUT.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
TESTS = ROOT / 'tests'
FILE = TESTS / 'test_hygiene.py'
SRC = FILE.read_text()
NAMES = {'SKIPPERS', 'SKIP_HELPERS', 'CONFTESTS', 'SCOPES', '_scope_bindings', '_module_bindings', '_allowed',
         '_raised', 'skip_violations'}


def extract(src: str) -> str:
    return '\n\n'.join(ast.get_source_segment(src, n) for n in ast.parse(src).body
                       if (isinstance(n, ast.FunctionDef) and n.name in NAMES)
                       or (isinstance(n, ast.Assign) and any(getattr(t, 'id', None) in NAMES for t in n.targets)))


CHECK = extract(SRC)
SCOPE_ANCHOR = "            pending += [c for c in ast.iter_child_nodes(node) if not any(c is b for b in inner)]"

M = {
    # _allowed: which module is the suite's conftest
    'M1': ('conftest by path', "if Path(name) not in CONFTESTS:", "if not name.endswith('conftest.py'):"),
    'M1a': ('the bare name is the conftest', "CONFTESTS = {Path('conftest.py'), TESTS / 'conftest.py'}",
            "CONFTESTS = {TESTS / 'conftest.py'}"),
    'M1b': ('the scanned path is the conftest', "CONFTESTS = {Path('conftest.py'), TESTS / 'conftest.py'}",
            "CONFTESTS = {Path('conftest.py')}"),
    # _allowed: one binding, a top-level def, its body
    'M6': ('a second binding is reported',
           "found.extend(f'{name}:{n.lineno}: {helper} defined again' for n in bindings[1:])", "pass"),
    'M26': ('only a single binding allows', "single = bindings[0] if len(bindings) == 1 else None",
            "single = bindings[0] if bindings else None"),
    'M10': ('every binding counts, not only defs', "single = bindings[0] if len(bindings) == 1 else None",
            "single = next((b for b in bindings if isinstance(b, ast.FunctionDef)), None)"),
    'M27': ('only a def allows (not a class)', "if isinstance(single, ast.FunctionDef) and",
            "if isinstance(single, (ast.FunctionDef, ast.ClassDef)) and"),
    'M28': ('only a def allows (not an async def)', "if isinstance(single, ast.FunctionDef) and",
            "if isinstance(single, (ast.FunctionDef, ast.AsyncFunctionDef)) and"),
    'M3': ('the def is top-level', "if isinstance(single, ast.FunctionDef) and any(single is n for n in tree.body):",
           "if isinstance(single, ast.FunctionDef):"),
    'M29': ('the body allows, not decorators or defaults',
            "allowed |= {id(n) for statement in single.body for n in ast.walk(statement)}",
            "allowed |= {id(n) for n in ast.walk(single)}"),
    'M43': ('allowed by node, not by line (V54)',
            "allowed |= {id(n) for statement in single.body for n in ast.walk(statement)}",
            "allowed |= {id(n) for n in ast.walk(tree) if getattr(n, 'lineno', 0) in "
            "{m.lineno for s in single.body for m in ast.walk(s) if hasattr(m, 'lineno')}}"),
    'M42': ('helpers in sorted order', "for helper in sorted(SKIP_HELPERS):", "for helper in SKIP_HELPERS:"),
    # _allowed: a helper's name below the top level is never the helper
    'M2': ('nested helper-named scopes subtracted', "            allowed -= {id(n) for n in ast.walk(node)}",
           "            pass"),
    'M44': ('a helper-named class is subtracted too (V40)',
            "if (isinstance(node, SCOPES) and getattr(node, 'name', None) in SKIP_HELPERS",
            "if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))"
            " and getattr(node, 'name', None) in SKIP_HELPERS"),
    'M2a': ('only helper-named scopes subtracted', "and getattr(node, 'name', None) in SKIP_HELPERS\n", "\n"),
    'M2b': ('only scopes below the top level subtracted', "                and not any(node is n for n in tree.body)):",
            "                ):"),
    # _scope_bindings: where a scope ends
    'M20': ('SCOPES holds def', "SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)",
            "SCOPES = (ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)"),
    'M21': ('SCOPES holds async def', "SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)",
            "SCOPES = (ast.FunctionDef, ast.ClassDef, ast.Lambda)"),
    'M22': ('SCOPES holds class', "SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)",
            "SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)"),
    'M23': ('SCOPES holds lambda', "SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)",
            "SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)"),
    'M16': ('a def or class of the name binds', "if getattr(node, 'name', None) == helper:", "if False:"),
    'M17': ("a scope's body is not the enclosing scope", SCOPE_ANCHOR,
            "            pending += ast.iter_child_nodes(node)"),
    'M18': ("a scope's decorators, defaults and bases are the enclosing scope", SCOPE_ANCHOR, "            pass"),
    'M19': ("a lambda's body is one expression", "inner = node.body if isinstance(node.body, list) else [node.body]",
            "inner = node.body if isinstance(node.body, list) else []"),
    'M24': ('statements are walked into', "        pending += ast.iter_child_nodes(node)\n    return stores",
            "        pass\n    return stores"),
    # _scope_bindings: what stores (review cycle 2: B1-B5)
    'M9': ('a store binds', "bound = node.id if not isinstance(node.ctx, ast.Load) else None", "bound = None"),
    'M9a': ('a delete binds', "bound = node.id if not isinstance(node.ctx, ast.Load) else None",
            "bound = node.id if isinstance(node.ctx, ast.Store) else None"),
    'B1': ('a load binds nothing (V16)', "bound = node.id if not isinstance(node.ctx, ast.Load) else None",
           "bound = node.id"),
    'B2': ("a comprehension's own variable binds nothing",
           "if isinstance(node, ast.comprehension) or (isinstance(node, ast.AnnAssign) and node.value is None):",
           "if isinstance(node, ast.AnnAssign) and node.value is None:"),
    'B3': ('an annotation with no value binds nothing',
           "if isinstance(node, ast.comprehension) or (isinstance(node, ast.AnnAssign) and node.value is None):",
           "if isinstance(node, ast.comprehension):"),
    'B4': ('an annotation with a value binds', "(isinstance(node, ast.AnnAssign) and node.value is None)",
           "isinstance(node, ast.AnnAssign)"),
    'B5': ("a comprehension's iterables and conditions are the enclosing scope",
           "            pending += [c for c in ast.iter_child_nodes(node) if c is not node.target]\n            continue",
           "            continue"),
    'B5a': ("a comprehension or bare annotation stops there",
            "            pending += [c for c in ast.iter_child_nodes(node) if c is not node.target]\n            continue",
            "            pending += [c for c in ast.iter_child_nodes(node) if c is not node.target]"),
    'M8': ('an import binds', "bound = node.asname or node.name.split('.')[0]", "bound = None"),
    'M8a': ('an unaliased import binds', "bound = node.asname or node.name.split('.')[0]", "bound = node.asname"),
    'M8b': ('a dotted import binds its first part', "bound = node.asname or node.name.split('.')[0]",
            "bound = node.asname or node.name"),
    'M12': ('except as binds', "(ast.ExceptHandler, ast.MatchAs, ast.MatchStar)", "(ast.MatchAs, ast.MatchStar)"),
    'M13': ('a match capture binds', "(ast.ExceptHandler, ast.MatchAs, ast.MatchStar)",
            "(ast.ExceptHandler, ast.MatchStar)"),
    'M14': ('a match star binds', "(ast.ExceptHandler, ast.MatchAs, ast.MatchStar)",
            "(ast.ExceptHandler, ast.MatchAs)"),
    'M15': ('a mapping rest binds', "bound = node.rest", "bound = None"),
    # _scope_bindings and _module_bindings: `global` (review cycle 2: B6-B11)
    'M7': ('a global with a store binds', "bindings += declared if stores else []", "pass"),
    'M7b': ('a global is declared in its scope', "declared += [node] if helper in node.names else []", "pass"),
    'B6': ('only a global naming the helper', "declared += [node] if helper in node.names else []",
           "declared += [node]"),
    'B6a': ('a global stops there', "            declared += [node] if helper in node.names else []\n            continue",
            "            declared += [node] if helper in node.names else []"),
    'B7': ('only a global paired with a store', "bindings += declared if stores else []", "bindings += declared"),
    'B8': ("the module's own globals bind nothing", "bindings, _ = _scope_bindings(tree.body, helper)",
           "stores, declared = _scope_bindings(tree.body, helper)\n    bindings = stores + declared"),
    'M7a': ('a global at any depth counts', "    for node in ast.walk(tree):\n        if isinstance(node, SCOPES) and isinstance(node.body, list):",
            "    for node in tree.body:\n        if isinstance(node, SCOPES) and isinstance(node.body, list):"),
    'B9': ('a lambda holds no global', "if isinstance(node, SCOPES) and isinstance(node.body, list):",
           "if isinstance(node, SCOPES):"),
    'M25': ('bindings in line order', "return sorted(bindings, key=lambda n: (n.lineno, n.col_offset))",
            "return bindings"),
    # skip_violations: what counts as a skip
    'M35': ('skip is a skipper', "SKIPPERS = {'skip', 'skipif', 'importorskip', 'xfail'}",
            "SKIPPERS = {'skipif', 'importorskip', 'xfail'}"),
    'M36': ('skipif is a skipper', "SKIPPERS = {'skip', 'skipif', 'importorskip', 'xfail'}",
            "SKIPPERS = {'skip', 'importorskip', 'xfail'}"),
    'M37': ('importorskip is a skipper', "SKIPPERS = {'skip', 'skipif', 'importorskip', 'xfail'}",
            "SKIPPERS = {'skip', 'skipif', 'xfail'}"),
    'M38': ('xfail is a skipper', "SKIPPERS = {'skip', 'skipif', 'importorskip', 'xfail'}",
            "SKIPPERS = {'skip', 'skipif', 'importorskip'}"),
    'M40': ('need_shell is a helper', "SKIP_HELPERS = {'need_shell', 'need_git'}", "SKIP_HELPERS = {'need_git'}"),
    'M41': ('need_git is a helper', "SKIP_HELPERS = {'need_shell', 'need_git'}", "SKIP_HELPERS = {'need_shell'}"),
    'M33': ('a name is a word', "word = node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None",
            "word = node.attr if isinstance(node, ast.Attribute) else None"),
    'M34': ('an attribute is a word', "word = node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None",
            "word = node.id if isinstance(node, ast.Name) else None"),
    'M39': ('a skip in a helper is allowed', "and id(node) not in allowed and", "and"),
    # skip_violations: the `.Exception` exemption
    'M32': ('the outcome type as a value is exempt', " and id(node) not in named:", ":"),
    'M32a': ("the skipper under `.Exception` is the one exempt", "named = {id(node.value) for node", "named = {id(node) for node"),
    'M4': ('only `.Exception` names the outcome type',
           "if isinstance(node, ast.Attribute) and node.attr == 'Exception' and id(node) not in raised}",
           "if isinstance(node, ast.Attribute)}"),
    'M5': ('a raised outcome type is not exempt', "and node.attr == 'Exception' and id(node) not in raised}",
           "and node.attr == 'Exception'}"),
    # _raised: what a raise raises (review cycle 2: R1-R9)
    'M11': ("everything under a raise's exception is raised (the reviewed rule)", "        raised.add(id(node))\n",
            "        raised.update(id(n) for n in ast.walk(node))\n"),
    'M30': ("a raise's cause is not raised",
            "pending = [r.exc for r in ast.walk(tree) if isinstance(r, ast.Raise) and r.exc is not None]",
            "pending = [n for r in ast.walk(tree) if isinstance(r, ast.Raise) for n in (r.exc, r.cause) if n is not None]"),
    'M31': ('a bare raise raises nothing', "if isinstance(r, ast.Raise) and r.exc is not None]",
            "if isinstance(r, ast.Raise)]"),
    'R1': ('a call hands on what it calls', "            pending.append(node.func)\n", "            pass\n"),
    'R2': ('a called method hands on its value', "                pending.append(node.func.value)\n",
           "                pass\n"),
    'R3': ('only a called attribute hands on its value', "        elif isinstance(node, ast.IfExp):",
           "        elif isinstance(node, ast.Attribute):\n            pending.append(node.value)\n"
           "        elif isinstance(node, ast.IfExp):"),
    'R4': ("an argument is not raised", "            pending.append(node.func)\n",
           "            pending += ast.iter_child_nodes(node)\n"),
    'R5': ("a conditional's body is raised", "pending += [node.body, node.orelse]", "pending += [node.orelse]"),
    'R6': ("a conditional's else is raised", "pending += [node.body, node.orelse]", "pending += [node.body]"),
    'R7': ("a conditional's test is not raised", "pending += [node.body, node.orelse]",
           "pending += ast.iter_child_nodes(node)"),
    'R8': ("a walrus hands on its value", "            pending.append(node.value)\n", "            pass\n"),
    'R9': ("a boolean hands on each operand", "            pending += node.values\n", "            pass\n"),
}


def build(src: str):
    space = {'ast': ast, 'Path': Path, 'TESTS': TESTS}
    exec(compile(src, 'check', 'exec'), space)
    return space['skip_violations']


def rows(path: Path) -> list[tuple[str, str, str, bool]]:
    tree = ast.parse(path.read_text())
    test = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'test_skip_check_catches_planted_skips')
    deco = next(d for d in test.decorator_list if isinstance(d, ast.Call) and ast.unparse(d.func).endswith('parametrize'))
    return [(next(k.value.value for k in p.keywords if k.arg == 'id'), *(ast.literal_eval(a) for a in p.args))
            for p in deco.args[1].elts]


def verdict(check, name, text):
    try:
        return bool(check(name, text))
    except Exception as error:  # A check that raises fails the row.
        return f'raises {type(error).__name__}'


def _report(check, name, text):
    try:
        return sorted(check(name, text))
    except Exception as error:
        return type(error).__name__


SUITE = {str(f): f.read_text() for f in sorted(TESTS.glob('*.py'))}


def suite_kills(check) -> bool:
    try:
        return any(check(n, t) for n, t in SUITE.items())
    except Exception:
        return True


def mutants():
    for key, (decision, old, new) in M.items():
        if CHECK.count(old) != 1 or SRC.count(old) != 1:
            raise SystemExit(f'{key}: anchor occurs {CHECK.count(old)} times in the check, '
                             f'{SRC.count(old)} in the file: {old!r}')
        assert CHECK.replace(old, new) != CHECK
        yield key, decision, old, new


def main_rows(sources: list[str]) -> int:
    row_sets = {s: rows(Path(s)) for s in sources}
    shipped = build(CHECK)
    assert not suite_kills(shipped), 'the unmutated check reports in the suite'
    for s, rs in row_sets.items():
        print(f'rows {s}: {len(rs)}')
    now = rows(FILE)
    bad = [r[0] for r in now if verdict(shipped, r[1], r[2]) is not r[3]]
    assert now and not bad, bad
    print(f'rows now: {len(now)}, all met by the unmutated check')
    probes = [(n, t) for rs in [*row_sets.values(), now] for _, n, t, _ in rs] + list(SUITE.items())
    for key, decision, old, new in mutants():
        check = build(CHECK.replace(old, new))
        cells = []
        for rs in [*row_sets.values(), now]:
            killers = [rid for rid, n, t, f in rs if verdict(check, n, t) is not f]
            cells.append(','.join(killers) or '-')
        suite = 'suite' if suite_kills(check) else '-'
        diff = sum(verdict(check, n, t) != verdict(shipped, n, t) for n, t in probes)
        reports = sum(_report(check, n, t) != _report(shipped, n, t) for n, t in probes)
        print(f'{key:5} | {decision} | ' + ' | '.join(cells) + f' | {suite} | verdicts differ {diff}, reports {reports}')
    return 0


def main_checks(sources: list[str]) -> int:
    now = rows(FILE)
    for s in sources:
        check = build(extract(Path(s).read_text()))
        failed = [rid for rid, n, t, f in now if verdict(check, n, t) is not f]
        print(f'check of {s}: fails {len(failed)} of {len(now)} rows: {",".join(failed) or "-"}')
    return 0


def main_pytest(era: str, out: str) -> int:
    env = {k: v for k, v in os.environ.items() if k != 'CLUSTER_MCP_TEST_ERA'}
    if era == 'modern':
        env['CLUSTER_MCP_TEST_ERA'] = 'modern'
    command = ['uv', 'run', 'pytest', '-q', '-p', 'no:cacheprovider', str(FILE.relative_to(ROOT)),
               '-k', 'skip_check_catches_planted_skips or only_need_shell_skips']
    lines = []
    try:
        clean = subprocess.run(command, env=env, capture_output=True, text=True)
        lines.append(f'unmutated | {"green" if clean.returncode == 0 else "red"} | {clean.stdout.strip().splitlines()[-1]}')
        for key, decision, old, new in mutants():
            FILE.write_text(SRC.replace(old, new))
            run = subprocess.run(command, env=env, capture_output=True, text=True)
            tail = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else run.stderr.strip()[-200:]
            lines.append(f'{key} | {"green" if run.returncode == 0 else "red"} | {tail}')
    finally:
        FILE.write_text(SRC)
    assert FILE.read_text() == SRC, 'restore failed'
    Path(out).write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    mode, *args = sys.argv[1:]
    sys.exit({'rows': main_rows, 'checks': main_checks}[mode](args) if mode != 'pytest' else main_pytest(*args))
```
