# Mutant sweep — `skip_violations` and its helpers (review cycle 1, F3)

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
