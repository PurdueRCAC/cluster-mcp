"""Gate for skip-check-fence-gaps: the new check meets every planted row, and each new row is a gap it closed.

Usage (from the worktree root, after staging):
    uv run python -I spec/skip-check-fence-gaps/verify/planted-rows.py scope|spelling|all
    uv run python -I spec/skip-check-fence-gaps/verify/planted-rows.py controls scope|spelling|all

A mode reads `tests/test_hygiene.py` and every `tests/*.py` from the index (committed state), and
`tests/test_hygiene.py` from the base: the parent of the commit that added this cycle's GOAL.md,
which must be reachable from origin/develop. It checks:
  fence   with renames off, the index differs from the base only in tests/test_hygiene.py, this
          cycle's spec Markdown and this script, and ledger files (issues/*.md, ROADMAP.md); never
          tests/mutants.py; the working copy of tests/test_hygiene.py matches the index;
  bodies  test_only_need_shell_skips, and test_skip_check_catches_planted_skips apart from its row
          list, are the base's, node for node;
  kept    every base row is still there, unchanged; every row is a plain literal (no keyword but id);
  rows    every row this mode requires is there with its pinned expectation and the shape its id names;
  bite    the base check, run from the base's source, meets every base row (so it was extracted
          whole), and admits every required row that expects a report (a gap it had, not one it caught);
  meet    the index's check, run from the index's source, meets every row's expectation;
  suite   the index's check reports nothing over the index's tests/*.py.
`controls` plants mutations in memory and asserts each draws its own kind of refusal.

Footprint: one Python process, git calls in sequence, well under 200 MB; no workers.
"""
from __future__ import annotations

import ast
import copy
import re
import subprocess
import sys
from pathlib import Path

SLUG = 'skip-check-fence-gaps'
TARGET = 'tests/test_hygiene.py'
ROWS_TEST = 'test_skip_check_catches_planted_skips'
SUITE_TEST = 'test_only_need_shell_skips'
HELPERS = {'need_shell', 'need_git'}
SKIPPERS = {'skip', 'skipif', 'importorskip', 'xfail'}
NOT_A_ROW = 'not a plain literal row'


def git(*args: str) -> str:
    return subprocess.run(['git', *args], check=True, capture_output=True, text=True).stdout


def root() -> Path:
    return Path(git('rev-parse', '--show-toplevel').strip()).resolve()


def base_commit() -> str:
    """The parent of the commit that added this cycle's GOAL: the tree the cycle started from, after any rebase."""
    shaped = git('log', '--diff-filter=A', '--format=%H', '--', f'spec/{SLUG}/GOAL.md').split()
    if not shaped:
        raise SystemExit(f'planted-rows: no commit adds spec/{SLUG}/GOAL.md')
    base = git('rev-parse', f'{shaped[-1]}^').strip()
    if subprocess.run(['git', 'merge-base', '--is-ancestor', base, 'origin/develop']).returncode != 0:
        raise SystemExit(f'planted-rows: the base {base[:9]} is not on origin/develop (history rewritten, or fetch it)')
    return base


def rows_of(text: str) -> dict[str, tuple | str]:
    """Each planted row's id mapped to (name, text, found), or NOT_A_ROW for a non-literal or keyworded row."""
    tree = ast.parse(text)
    test = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == ROWS_TEST)
    deco = next(d for d in test.decorator_list if isinstance(d, ast.Call) and ast.unparse(d.func).endswith('parametrize'))
    rows: dict[str, tuple | str] = {}
    for call in deco.args[1].elts:
        ident = next(k.value.value for k in call.keywords if k.arg == 'id')
        if ident in rows:
            raise SystemExit(f'planted-rows: row id {ident!r} appears twice')
        try:
            row = tuple(ast.literal_eval(a) for a in call.args)
        except ValueError:
            row = None
        plain = row is not None and len(row) == 3 and all(k.arg == 'id' for k in call.keywords)
        rows[ident] = row if plain else NOT_A_ROW
    return rows


def body_dumps(text: str) -> dict[str, str]:
    """The two tests that run the check, as node dumps, the row test's row list emptied."""
    dumps = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef) and node.name in {ROWS_TEST, SUITE_TEST}:
            node = copy.deepcopy(node)
            for deco in node.decorator_list:
                if isinstance(deco, ast.Call) and ast.unparse(deco.func).endswith('parametrize'):
                    deco.args[1] = ast.List(elts=[], ctx=ast.Load())
            dumps[node.name] = ast.dump(node)
    return dumps


def check_of(text: str, tests: Path):
    """`skip_violations` from `text`, run with the top-level names it reaches; `TESTS` is the real tests dir."""
    tree = ast.parse(text)
    tops: dict[str, ast.stmt] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            tops[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                if isinstance(target, ast.Name):
                    tops[target.id] = node
    seen: set[str] = set()
    need = ['skip_violations']
    while need:
        word = need.pop()
        if word in seen or word not in tops or word == 'TESTS':
            continue
        seen.add(word)
        need += [n.id for n in ast.walk(tops[word]) if isinstance(n, ast.Name)]
    keep = [n for n in tree.body if any(tops[w] is n for w in seen)]
    space: dict = {'ast': ast, 're': re, 'Path': Path, 'TESTS': tests}
    exec(compile(ast.Module(body=keep, type_ignores=[]), 'extracted-check', 'exec'), space)
    return space['skip_violations']


def _skipper(node: ast.AST, word: str | None = None) -> bool:
    found = node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None
    return found in SKIPPERS and (word is None or found == word)


def _has_skip(node: ast.AST) -> bool:
    return any(_skipper(n) for n in ast.walk(node))


def _helper_defs(nodes) -> list[ast.FunctionDef]:
    return [n for n in nodes if isinstance(n, ast.FunctionDef) and n.name in HELPERS]


def _top(name: str, tree: ast.Module) -> list[ast.FunctionDef]:
    return _helper_defs(tree.body) if name == 'conftest.py' else []


def _nested(name, tree):
    return name == 'conftest.py' and any(
        inner is not outer and _has_skip(inner)
        for outer in tree.body if isinstance(outer, ast.FunctionDef) and outer.name not in HELPERS
        for inner in _helper_defs(ast.walk(outer)))


def _nested_in_helper(name, tree):
    return any(inner is not outer and _has_skip(inner) for outer in _top(name, tree)
               for inner in _helper_defs(ast.walk(outer)))


def _closure_in_helper(name, tree):
    return any(isinstance(inner, ast.FunctionDef) and inner.name not in HELPERS and _has_skip(inner)
               for outer in _top(name, tree) for inner in ast.walk(outer) if inner is not outer)


def _method(name, tree):
    return name == 'conftest.py' and any(
        _has_skip(m) for c in tree.body if isinstance(c, ast.ClassDef) for m in _helper_defs(c.body))


def _twice(with_skip_in_second: bool):
    def shape(name, tree):
        for helper in HELPERS:
            defs = [d for d in _top(name, tree) if d.name == helper]
            if len(defs) > 1 and _has_skip(defs[0]) and _has_skip(defs[1]) is with_skip_in_second:
                return True
        return False
    return shape


def _rebound(name, tree):
    return bool(_top(name, tree)) and any(
        isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in HELPERS for t in n.targets)
        for n in tree.body)


def _rebound_by_global(name, tree):
    return bool(_top(name, tree)) and any(isinstance(n, ast.Global) and set(n.names) & HELPERS for n in ast.walk(tree))


def _rebound_by_import(name, tree):
    return bool(_top(name, tree)) and any(
        isinstance(n, (ast.Import, ast.ImportFrom)) and any((a.asname or a.name) in HELPERS for a in n.names)
        for n in tree.body)


def _below_top(name, tree):
    return name == 'conftest.py' and not _top(name, tree) and any(
        _has_skip(d) for n in tree.body if isinstance(n, (ast.If, ast.Try, ast.With)) for d in _helper_defs(ast.walk(n)))


def _skipping_helper_in(pred):
    def shape(name, tree):
        return pred(name) and any(_has_skip(d) for d in _helper_defs(tree.body))
    return shape


def _twice_without_a_skip(name, tree):
    return any(len(defs) > 1 and not any(_has_skip(d) for d in defs)
               for defs in ([d for d in _top(name, tree) if d.name == h] for h in HELPERS))


def _binds(node: ast.AST) -> str | None:
    """The name `node` binds, as Python reads it (written apart from the check's own code)."""
    if isinstance(node, ast.Name):
        return node.id if not isinstance(node.ctx, ast.Load) else None
    if isinstance(node, ast.alias):
        return node.asname or node.name.split('.')[0]
    if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
        return node.name
    if isinstance(node, ast.MatchMapping):
        return node.rest
    return node.name if isinstance(node, ast.ClassDef) else None


def _rebound_by(kind, where=lambda node, tree: True):
    """A top-level helper, and a node of `kind` (meeting `where`) that binds a helper's name."""
    def shape(name, tree):
        return bool(_top(name, tree)) and any(
            isinstance(n, kind) and _binds(n) in HELPERS and where(n, tree) for n in ast.walk(tree))
    return shape


def _rebound_in_a_default(name, tree):
    return bool(_top(name, tree)) and any(
        isinstance(f, ast.FunctionDef) and f.name not in HELPERS and any(
            isinstance(e, ast.NamedExpr) and _binds(e.target) in HELPERS for d in f.args.defaults for e in ast.walk(d))
        for f in tree.body)


def _async_nested_in_helper(name, tree):
    return any(isinstance(inner, ast.AsyncFunctionDef) and inner.name in HELPERS and _has_skip(inner)
               for outer in _top(name, tree) for inner in ast.walk(outer))


def _attribute(name, tree):
    return any(isinstance(n, ast.Attribute) and n.attr != 'Exception' and _skipper(n.value) for n in ast.walk(tree))


def _outcome(e: ast.AST, word: str | None = None) -> bool:
    """`X.Exception`, `X.Exception(...)`, or that call with `.with_traceback(...)` chained, X a skipper."""
    while True:
        if isinstance(e, ast.Call):
            e = e.func
        elif isinstance(e, ast.Attribute) and e.attr == 'with_traceback' and isinstance(e.value, ast.Call):
            e = e.value
        else:
            break
    return isinstance(e, ast.Attribute) and e.attr == 'Exception' and _skipper(e.value, word)


def _raised(word: str, cause: bool = False):
    """`raise` of the outcome (`_outcome`), with a `from` cause when `cause`."""
    def shape(name, tree):
        return any(isinstance(r, ast.Raise) and r.exc is not None and _outcome(r.exc, word)
                   and (r.cause is not None or not cause) for r in ast.walk(tree))
    return shape


def _raised_in(kind, field: str):
    """`raise` of a `kind` expression whose `field` (one node or a list) holds the outcome."""
    def shape(name, tree):
        for r in ast.walk(tree):
            if isinstance(r, ast.Raise) and isinstance(r.exc, kind):
                part = getattr(r.exc, field)
                if any(_outcome(p) for p in (part if isinstance(part, list) else [part])):
                    return True
        return False
    return shape


def _value_in_a_raise(where):
    """A skipper's `.Exception` inside a raise's exception expression, at the place `where(exc, value)` names."""
    def shape(name, tree):
        return any(isinstance(v, ast.Attribute) and v.attr == 'Exception' and _skipper(v.value) and where(r.exc, v)
                   for r in ast.walk(tree) if isinstance(r, ast.Raise) and r.exc is not None
                   for v in ast.walk(r.exc))
    return shape


def _within(kind, test=lambda n: True):
    """`where` for `_value_in_a_raise`: the value sits inside a `kind` node meeting `test`."""
    return lambda exc, v: any(isinstance(n, kind) and test(n) and any(m is v for m in ast.walk(n))
                              for n in ast.walk(exc))


def _top_level(kind, test):
    """A top-level helper, and a top-level `kind` statement meeting `test`."""
    def shape(name, tree):
        return bool(_top(name, tree)) and any(isinstance(s, kind) and test(s) for s in tree.body)
    return shape


def _loads_helper(s: ast.AST) -> bool:
    names = [n for n in ast.walk(s) if isinstance(n, ast.Name) and n.id in HELPERS]
    return bool(names) and all(isinstance(n.ctx, ast.Load) for n in names)


def _stores_helper(f: ast.AST) -> bool:
    return any(_binds(n) in HELPERS for n in ast.walk(f) if n is not f)


def _global_in(f: ast.AST, of_helper: bool) -> bool:
    return any(isinstance(n, ast.Global) and bool(set(n.names) & HELPERS) is of_helper for n in f.body)


def _comprehension_binds(where: str):
    """A top-level helper, and a comprehension whose `where` ('target', or a walrus in 'ifs') binds a helper."""
    def shape(name, tree):
        def binds(part):
            return any(_binds(n.target if isinstance(n, ast.NamedExpr) else n) in HELPERS
                       for p in (part if isinstance(part, list) else [part]) for n in ast.walk(p)
                       if where == 'target' or isinstance(n, ast.NamedExpr))
        return bool(_top(name, tree)) and any(isinstance(c, ast.comprehension) and binds(getattr(c, where))
                                              for c in ast.walk(tree))
    return shape


def _class_in_helper(name, tree):
    return any(isinstance(inner, ast.ClassDef) and inner.name in HELPERS and _has_skip(inner)
               for outer in _top(name, tree) for inner in ast.walk(outer))


def _skip_on_the_helpers_line(name, tree):
    return any(any(_skipper(n) and n.lineno == d.body[0].lineno for a in d.args.defaults for n in ast.walk(a))
               for d in _top(name, tree))


def _as_value(name, tree):
    return not any(isinstance(r, ast.Raise) for r in ast.walk(tree)) and any(
        isinstance(n, ast.Attribute) and n.attr == 'Exception' and _skipper(n.value) for n in ast.walk(tree))


# id -> (expected found, shape). Each shape is the one its id names.
SCOPE_ROWS = {
    'helper-nested-in-a-fixture': (True, _nested),
    'helper-as-a-method': (True, _method),
    'helper-nested-in-the-helper': (True, _nested_in_helper),
    'closure-inside-the-helper': (False, _closure_in_helper),
    'helper-defined-twice': (True, _twice(True)),
    'helper-redefined-without-a-skip': (True, _twice(False)),
    'helper-rebound': (True, _rebound),
    'helper-rebound-by-global': (True, _rebound_by_global),
    'helper-rebound-by-import': (True, _rebound_by_import),
    'helper-below-the-top-level': (True, _below_top),
    'look-alike-conftest': (True, _skipping_helper_in(lambda n: n.endswith('conftest.py')
                                                      and Path(n).name != 'conftest.py')),
    'another-conftest': (True, _skipping_helper_in(lambda n: Path(n).name == 'conftest.py' and n != 'conftest.py'
                                                   and not Path(n).is_absolute())),
    # Review cycle 1: R2's own report on a skip-less double definition, and each binding form and
    # scope kind the check reads, each a gap the base had (the mutant sweep, verify/mutant-sweep.md).
    'helper-defined-twice-without-a-skip': (True, _twice_without_a_skip),
    'helper-rebound-in-a-default': (True, _rebound_in_a_default),
    'helper-deleted': (True, _rebound_by(ast.Name, lambda n, t: isinstance(n.ctx, ast.Del))),
    'helper-rebound-by-a-dotted-import': (True, _rebound_by(ast.alias, lambda n, t: not n.asname and '.' in n.name)),
    'helper-rebound-by-except': (True, _rebound_by(ast.ExceptHandler)),
    'helper-rebound-by-a-match-capture': (True, _rebound_by(ast.MatchAs)),
    'helper-rebound-by-a-match-star': (True, _rebound_by(ast.MatchStar)),
    'helper-rebound-by-a-match-rest': (True, _rebound_by(ast.MatchMapping)),
    'helper-rebound-by-a-class': (True, _rebound_by(ast.ClassDef, lambda n, t: any(n is s for s in t.body))),
    'async-helper-nested-in-the-helper': (True, _async_nested_in_helper),
    # Review cycle 2: only a module-scope store rebinds a helper. Each store form below is a gap the
    # base had; each non-store beside it the reviewed check reported (verify/mutant-sweep.md).
    'helper-rebound-by-an-annotated-assignment': (True, _top_level(
        ast.AnnAssign, lambda s: _binds(s.target) in HELPERS and s.value is not None)),
    'helper-rebound-by-a-walrus-in-a-comprehension': (True, _comprehension_binds('ifs')),
    'helper-rebound-by-global-in-a-method': (True, _top_level(ast.ClassDef, lambda c: any(
        isinstance(f, ast.FunctionDef) and _global_in(f, True) and _stores_helper(f) for f in c.body))),
    'helper-named-class-in-the-helper': (True, _class_in_helper),
    'skip-in-a-one-line-helpers-default': (True, _skip_on_the_helpers_line),
    'helper-read-at-module-scope': (False, _top_level((ast.Assign, ast.Expr), _loads_helper)),
    'helper-annotated-without-a-value': (False, _top_level(
        ast.AnnAssign, lambda s: _binds(s.target) in HELPERS and s.value is None)),
    'helper-name-in-a-comprehension': (False, _comprehension_binds('target')),
    'helper-declared-global-without-a-store': (False, _top_level(
        ast.FunctionDef, lambda f: f.name not in HELPERS and _global_in(f, True) and not _stores_helper(f))),
    'helper-declared-global-at-module-scope': (False, _top_level(ast.Global, lambda s: bool(set(s.names) & HELPERS))),
    'helper-stored-beside-another-global': (False, _top_level(
        ast.FunctionDef, lambda f: f.name not in HELPERS and _global_in(f, False) and _stores_helper(f))),
}
SPELLING_ROWS = {
    'skip-through-an-attribute': (True, _attribute),
    'mark-through-an-attribute': (True, _attribute),
    'raised-skip-outcome': (True, _raised('skip')),
    'raised-xfail-outcome': (True, _raised('xfail')),
    'raised-outcome-type': (True, _raised('skip')),
    'raised-outcome-of-a-bare-skip': (True, _raised('skip')),
    'outcome-type-as-an-argument': (False, _as_value),
    'outcome-type-caught': (False, _as_value),
    # Review cycle 2: a raise whose exception is the outcome, each a gap the base had; the outcome type
    # as any other value in a raise, each one the reviewed check reported.
    'raised-outcome-with-a-cause': (True, _raised('skip', cause=True)),
    'raised-outcome-in-a-conditional': (True, _raised_in(ast.IfExp, 'body')),
    'raised-outcome-in-a-conditionals-else': (True, _raised_in(ast.IfExp, 'orelse')),
    'raised-outcome-through-a-walrus': (True, _raised_in(ast.NamedExpr, 'value')),
    'raised-outcome-in-a-boolean': (True, _raised_in(ast.BoolOp, 'values')),
    'outcome-type-in-a-raised-argument': (False, _value_in_a_raise(
        lambda exc, v: isinstance(exc, ast.Call) and any(a is v for a in exc.args))),
    'outcome-type-in-a-raised-message': (False, _value_in_a_raise(_within(ast.JoinedStr))),
    'outcome-type-in-a-raised-repr': (False, _value_in_a_raise(
        _within(ast.Call, lambda c: isinstance(c.func, ast.Name) and c.func.id == 'repr'))),
    'outcome-types-attribute-raised': (False, _value_in_a_raise(
        lambda exc, v: isinstance(exc, ast.Attribute) and exc.value is v)),
    'outcome-type-as-a-conditionals-test': (False, _value_in_a_raise(
        lambda exc, v: isinstance(exc, ast.IfExp) and exc.test is v)),
}
MODES = {'scope': SCOPE_ROWS, 'spelling': SPELLING_ROWS, 'all': SCOPE_ROWS | SPELLING_ROWS}


def fence(base: str) -> list[str]:
    changed = git('diff', '--cached', '--no-renames', '--name-only', base).split()

    def allowed(f: str) -> bool:
        return (f in {TARGET, 'ROADMAP.md', f'spec/{SLUG}/verify/planted-rows.py'}
                or (f.startswith('issues/') and f.endswith('.md'))
                or (f.startswith(f'spec/{SLUG}/') and f.endswith('.md')))

    problems = [f'fence: {f} changed' for f in changed if not allowed(f)]
    if 'tests/mutants.py' in changed:
        problems.append('fence: tests/mutants.py changed (two sibling cycles own it)')
    if TARGET not in changed:
        problems.append(f'fence: {TARGET} is unchanged from the base {base[:9]}')
    if subprocess.run(['git', 'diff', '--quiet', '--', TARGET]).returncode != 0:
        problems.append(f'fence: the working copy of {TARGET} differs from the index (stage it)')
    return problems


def judge(new: dict, old: dict, new_text: str, base_text: str, required: dict, suite: dict[str, str],
          tests: Path) -> list[str]:
    problems: list[str] = []
    new_bodies = body_dumps(new_text)
    for test, dump in body_dumps(base_text).items():
        if new_bodies.get(test) != dump:
            problems.append(f'bodies: {test} differs from the base')
    for ident, row in old.items():
        if new.get(ident, 'missing') != row:
            problems.append(f'kept: base row {ident!r} is {"gone" if ident not in new else "changed"}')
    problems += [f'kept: row {i!r} is {NOT_A_ROW}' for i, r in new.items()
                 if r == NOT_A_ROW and i not in required and i not in old]
    base = check_of(base_text, tests)
    for ident, row in old.items():
        if row != NOT_A_ROW and bool(base(row[0], row[1])) != row[2]:
            problems.append(f'bite: the base check does not meet base row {ident!r}: extraction is broken')
    for ident, (found, shape) in required.items():
        row = new.get(ident, 'missing')
        if row in ('missing', NOT_A_ROW):
            problems.append(f'rows: required row {ident!r} is {row}')
            continue
        name, text, expect = row
        if expect is not found:
            problems.append(f'rows: row {ident!r} expects {expect}, pinned {found}')
        if not shape(name, ast.parse(text)):
            problems.append(f'rows: row {ident!r} does not have the shape its id names')
        if found and base(name, text):
            problems.append(f'bite: the base check already reports row {ident!r}, so it closes no gap')
    try:
        check = check_of(new_text, tests)
        met = [(ident, bool(check(row[0], row[1])) == row[2]) for ident, row in new.items() if row != NOT_A_ROW]
        scanned = [v for path, text in sorted(suite.items()) for v in check(str(tests.parent / path), text)]
    except Exception as error:  # A check the gate cannot run is a red gate, named.
        return problems + [f'meet: the index check does not run on its own: {error!r}']
    problems += [f'meet: the index check does not meet row {ident!r}' for ident, ok in met if not ok]
    problems += [f'suite: {v}' for v in scanned]
    return problems


def emptied_check(text: str) -> str:
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'skip_violations':
            node.body = [ast.Return(value=ast.List(elts=[], ctx=ast.Load()))]
    return ast.unparse(ast.fix_missing_locations(tree))


def loosened_test(text: str) -> str:
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == ROWS_TEST:
            node.body = [ast.Assert(test=ast.Constant(value=True))]
    return ast.unparse(ast.fix_missing_locations(tree))


def controls(new: dict, old: dict, new_text: str, base_text: str, required: dict, suite: dict[str, str],
             tests: Path) -> list[str]:
    """Each planted mutation must draw the refusal its kind names; `meet` may join a row mutation."""
    kept = next(i for i, r in old.items() if r != NOT_A_ROW)
    first = next(iter(required))
    name, text, found = new[first]
    cases: list[tuple] = []

    def add(what, kind, rows=new, ntext=new_text, btext=base_text, st=suite, also=('meet',)):
        cases.append((what, kind, {kind, *also}, rows, ntext, btext, st))

    add('a required row deleted', 'rows', {k: v for k, v in new.items() if k != first})
    add('a required row flipped', 'rows', new | {first: (name, text, not found)})
    add('a required row keyworded', 'rows', new | {first: NOT_A_ROW})
    for ident, (pinned, _) in required.items():
        n, t, f = new[ident]
        add(f'row {ident!r} of the wrong shape', 'rows', new | {ident: (n, 'x = 1\n', f)})
        if pinned:
            add(f'row {ident!r} the base check already reports', 'bite',
                new | {ident: (n, 'import pytest\npytest.skip("x")\n' + t, f)})
    add('a base row changed', 'kept', new | {kept: (old[kept][0], old[kept][1], not old[kept][2])})
    add('a base row gone', 'kept', {k: v for k, v in new.items() if k != kept})
    add('a base row keyworded', 'kept', new | {kept: NOT_A_ROW})
    add('an index check that reports nothing', 'meet', ntext=emptied_check(new_text), also=())
    add('a row test that asserts nothing', 'bodies', ntext=loosened_test(new_text), also=())
    add('a suite module that skips', 'suite',
        st=suite | {'tests/test_planted.py': 'import pytest\npytest.skip("x")\n'}, also=())
    add('a base check that reports nothing', 'bite', btext=emptied_check(base_text), also=('bodies',))
    misses = []
    for what, kind, allowed, rows, ntext, btext, st in cases:
        refusals = judge(rows, old, ntext, btext, required, st, tests)
        kinds = {r.split(':', 1)[0] for r in refusals}
        if kind not in kinds or not kinds <= allowed:
            misses.append(f'controls: {what}: expected {kind!r} (within {sorted(allowed)}), got {refusals}')
    return misses


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == 'controls' and argv[1] in MODES:
        run_controls, mode = True, argv[1]
    elif len(argv) == 1 and argv[0] in MODES:
        run_controls, mode = False, argv[0]
    else:
        print(__doc__, file=sys.stderr)
        return 2
    base, tests = base_commit(), root() / 'tests'
    new_text, base_text = git('show', f':{TARGET}'), git('show', f'{base}:{TARGET}')
    suite = {f: git('show', f':{f}') for f in git('ls-files', '--', 'tests/').split()
             if f.endswith('.py') and f.count('/') == 1}
    new, old, required = rows_of(new_text), rows_of(base_text), MODES[mode]
    args = (new, old, new_text, base_text, required, suite, tests)
    problems = controls(*args) if run_controls else fence(base) + judge(*args)
    for line in problems:
        print(line, file=sys.stderr)
    detail = '' if run_controls else f', {len(suite)} suite modules'
    print(f'planted-rows {" ".join(argv)}: {"FAIL" if problems else "ok"} (base {base[:9]}, {len(required)} rows{detail})')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
