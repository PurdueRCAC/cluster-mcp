"""Kill evidence for review cycle 3's N10 (checker F9): a name bound by a statement or pattern.

Review cycle 3 (`REVIEW.md`) found `def __annotate__` in a class body passing unread and unrefused
(N10): the check refused `__annotations__` and `__annotate__` as a string, a keyword, an attribute
or a name, never as the name a `def` binds. The class is every node that spells the name it binds
in a field of its own: a `def` (at module level, in a class, decorated, in a class inside a
function), an `async def`, a `class`, an import (its name or its alias) and a `match` capture, star
or mapping rest. This checker shows the fix has teeth, in both protocol eras, reading committed state:

- after: the rows at REV are green, the tree test among them (the control: the unmutated tree
  passes, so the new refusal refuses nothing the tree holds);
- before: the new rows run against the check as it stood at BEFORE (its functions, with REV's rows)
  are red, each one: the reviewed check passed every one of them;
- each mutant undoes one part of the fix at REV, and the rows named for it are red. AK2 is review
  cycle 3's N11 survivor of that name (`__annotate__` dropped from the keys), which the new rows
  kill; F9k is the one-line refusal text;
- the sweep over the new decision: carve-outs that skip one place a binding can be written (module
  level, a decorated `def`, a class inside a function, a plain `import`) are each red on the row for
  that place; the one carve-out no row kills (C5, a `def` whose parameters are not one positional
  name) must survive the whole module, and is seeded in `issues/annotation-check-pin-gaps.md`.

Usage: .venv/bin/python -I spec/annotation-check/remediation/F9-review3.py [--rev REV] [--before REV]
                                                                         [--worktree-module] [ID...]
  --worktree-module  use the worktree's uncommitted module over REV's tree (a cheap pass while rows are
                     written; evidence reads committed state only)
It reuses `F6-F8-review2.py`'s runners (one pytest at a time, each in a session of its own). A row
prefix named red means every collected row with that prefix fails. Exit 0 when every expectation
holds. The scratch tree is left in place and its path printed. Footprint: one pytest at a time (plus
the tree test's child interpreter); about 40 runs of 2 to 4 s.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_spec = importlib.util.spec_from_file_location('review2', Path(__file__).resolve().with_name('F6-F8-review2.py'))
assert _spec is not None and _spec.loader is not None
review2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(review2)

MODULE = review2.MODULE
ERAS = review2.ERAS
BEFORE = '011c31f'
TREE, FORMS, VALID, HIDDEN, PLANTED = review2.TREE, review2.FORMS, review2.VALID, review2.HIDDEN, review2.PLANTED
mutant = review2.mutant

DEF = f'{FORMS}[annotate-def-'
LOCAL = f'{FORMS}[annotate-def-local-class-'
MODULE_DEF = f'{FORMS}[annotate-def-module-'
STATIC = f'{FORMS}[annotate-staticmethod-'
IMPORT_AS = f'{FORMS}[annotations-import-as-'
ASYNC = f'{FORMS}[annotate-async-def-'
CLASS = f'{FORMS}[annotate-class-'
IMPORTED = f'{FORMS}[annotate-imported-'
IMPORTED_AS = f'{FORMS}[annotations-imported-as-'
CAPTURE = f'{FORMS}[annotations-match-capture-'
STAR = f'{FORMS}[annotations-match-star-'
REST = f'{FORMS}[annotations-match-rest-'
# The rows the fix added, which must each be red against the check at BEFORE.
NEW_ROWS = [DEF, LOCAL, MODULE_DEF, STATIC, ASYNC, CLASS, IMPORTED, IMPORTED_AS, IMPORT_AS, CAPTURE, STAR, REST]

FIELDS = 'NAME_FIELDS: dict[type[ast.AST], tuple[str, ...]] = {\n'
ASKED = '            if (spelled := _spelled(node)) is not None:\n'
VISIT = '    def visit(node: ast.AST, prefix: str) -> None:\n'


def field(ident: str, what: str, entry: str, red: list[str]) -> dict:
    """A mutant that drops one entry of `NAME_FIELDS`."""
    return mutant(ident, what, entry, '', [FORMS], red)


MUTANTS = [
    mutant('F9a', 'a def or class statement never asked what it binds',
           '            if (spelled := _spelled(node)) is not None:\n                found.append(refused(node, prefix, spelled))\n',
           '', [FORMS], [DEF, LOCAL, MODULE_DEF, STATIC, ASYNC, CLASS]),
    field('F9b', 'a def name not read', ' ast.FunctionDef: (\'name\',),', [DEF, LOCAL, MODULE_DEF, STATIC]),
    field('F9c', 'an async def name not read', ' ast.AsyncFunctionDef: (\'name\',),', [ASYNC]),
    field('F9d', 'a class name not read', "    ast.ClassDef: ('name',),", [CLASS]),
    mutant('F9e', 'an imported name not read', " ast.alias: ('name', 'asname'),", " ast.alias: ('asname',),",
           [FORMS], [IMPORTED]),
    mutant('F9f', 'an import alias not read', " ast.alias: ('name', 'asname'),", " ast.alias: ('name',),",
           [FORMS], [IMPORTED_AS, IMPORT_AS]),
    field('F9g', 'a match capture not read', " ast.MatchAs: ('name',),", [CAPTURE]),
    field('F9h', 'a match star not read', " ast.MatchStar: ('name',),", [STAR]),
    field('F9i', "a match mapping's rest not read", "    ast.MatchMapping: ('rest',),\n", [REST]),
    mutant('F9j', 'an attribute spelling __annotations__ not read',
           '        return ast.unparse(node) if node.attr in ANNOTATION_KEYS else None\n', '        return None\n',
           [FORMS], [f'{FORMS}[annotations-assigned-']),
    mutant('F9k', 'a def or class shown whole, not by its first line',
           '        text = text.splitlines()[0] if isinstance(node, ast.stmt) else text\n', '',
           [FORMS], [DEF, LOCAL, MODULE_DEF, STATIC, ASYNC, CLASS]),
    # Review cycle 3's N11 survivor AK2, killed by the new rows.
    mutant('AK2', '__annotate__ dropped from the annotation keys',
           "ANNOTATION_KEYS = frozenset({'__annotations__', '__annotate__'})\n",
           "ANNOTATION_KEYS = frozenset({'__annotations__'})\n", [FORMS], [DEF, LOCAL, MODULE_DEF, STATIC, ASYNC, CLASS, IMPORTED]),
    # The sweep's carve-outs: each skips one place a binding can be written.
    mutant('C1', 'module level skipped', ASKED, ASKED.replace(':\n', ' and prefix:\n'), [FORMS], [MODULE_DEF]),
    mutant('C2', 'a decorated def or class skipped', ASKED, ASKED.replace(':\n', ' and not node.decorator_list:\n'),
           [FORMS], [STATIC]),
    mutant('C3', 'a class inside a function or class skipped', ASKED,
           ASKED.replace(':\n', " and prefix.count('.') < 2:\n"), [FORMS], [LOCAL]),
    mutant('C4', 'a plain import skipped', VISIT, VISIT + '        if isinstance(node, ast.Import):\n            return\n',
           [FORMS], [IMPORT_AS]),
]

# Carve-outs no row kills: each must survive the whole module, and is seeded.
SURVIVORS = [
    mutant('C5', 'a def whose parameters are not one positional name skipped', ASKED,
           ASKED.replace(':\n', ' and not (isinstance(node, ast.FunctionDef) and len(node.args.args) != 1):\n'),
           [], None),
]


def hybrid(before: str, after: str) -> str:
    """BEFORE's check functions with REV's rows: the check as reviewed, graded by the new rows."""
    marker = '\n# The tree.\n'
    return before.split(marker, 1)[0] + marker + after.split(marker, 1)[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--rev', default='HEAD')
    parser.add_argument('--before', default=BEFORE)
    parser.add_argument('--worktree-module', action='store_true')
    parser.add_argument('ids', nargs='*')
    args = parser.parse_args()
    repo = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
                               check=True).stdout.strip())
    rev = subprocess.run(['git', 'rev-parse', '--short', args.rev], cwd=repo, capture_output=True, text=True,
                         check=True).stdout.strip()
    before = subprocess.run(['git', 'show', f'{args.before}:{MODULE}'], cwd=repo, capture_output=True, text=True,
                            check=True).stdout
    tree = Path(tempfile.mkdtemp(prefix='ac-f9.'))
    os.environ.setdefault('UV_PYTHON', '3.14')
    failures: list[str] = []

    def whole(label: str) -> None:
        """Run the whole module in both eras: it must stay green (a recorded survivor)."""
        for era in ERAS:
            env = dict(os.environ)
            env.pop('CLUSTER_MCP_TEST_ERA', None)
            if era == 'modern':
                env['CLUSTER_MCP_TEST_ERA'] = 'modern'
            code, out = review2.sh([str(tree / '.venv' / 'bin' / 'python'), '-m', 'pytest', '-q', '-p',
                                    'no:cacheprovider', MODULE], tree, env)
            summary = next((line for line in reversed(out.splitlines())
                            if re.search(r'\d+ (passed|failed|error)', line)), '')
            print(f'{"ok  " if code == 0 else "FAIL"} {label} [{era}] {summary}', flush=True)
            if code != 0:
                failures.append(f'{label} [{era}]: killed, so re-judge it and its seed: {summary}')

    def expect(label: str, tests: list[str], red: list[str] | None) -> None:
        """Run `tests` in both eras: green when `red` is None, else every row of each prefix in `red` failed."""
        rows = review2.collected(tree, tests)
        wanted = [r for r in rows if red is not None and any(r.startswith(p) for p in red)]
        if red is not None and not all(any(r.startswith(p) for r in rows) for p in red):
            failures.append(f'{label}: a row named red is not collected: {red}')
        for era in ERAS:
            start = time.monotonic()
            code, failed, summary = review2.run(tree, era, tests)
            took = time.monotonic() - start
            if red is None:
                ok = code == 0 and not failed
            else:
                ok = code != 0 and bool(wanted) and set(wanted) <= set(failed)
            print(f'{"ok  " if ok else "FAIL"} {label} [{era}] {summary} ({took:.1f} s)'
                  + (f' red: {len(failed)}' if failed else ''), flush=True)
            if not ok:
                failures.append(f'{label} [{era}]: {summary}; failed {failed[:8]}')

    try:
        archive = subprocess.Popen(['git', 'archive', rev], cwd=repo, stdout=subprocess.PIPE)
        subprocess.run(['tar', '-x', '-C', str(tree)], stdin=archive.stdout, check=True)
        archive.wait()
        if subprocess.run(['uv', 'sync', '--locked', '--offline', '-q'], cwd=tree).returncode != 0:
            subprocess.run(['uv', 'sync', '--locked', '-q'], cwd=tree, check=True)
        target = tree / MODULE
        if args.worktree_module:
            target.write_text((repo / MODULE).read_text())
        after = target.read_text()
        if after.count(FIELDS) != 1:
            failures.append('NAME_FIELDS is not defined once at REV')
        everything = [TREE, FORMS, VALID, HIDDEN, PLANTED]
        print(f'F9: rev {rev}, before {args.before}', flush=True)
        if not args.ids:
            expect('after: the rows at REV, the tree test the control', everything, None)
            target.write_text(hybrid(before, after))
            expect('before: the new rows against the check at BEFORE', [FORMS], NEW_ROWS)
            target.write_text(after)
        for m in [*MUTANTS, *SURVIVORS]:
            if args.ids and m['id'] not in args.ids:
                continue
            count = after.count(m['old'])
            if count != 1:
                failures.append(f"{m['id']}: its anchor occurs {count} times at REV")
                print(f"FAIL {m['id']}: anchor occurs {count} times", flush=True)
                continue
            target.write_text(after.replace(m['old'], m['new']))
            if target.read_text() == after:
                failures.append(f"{m['id']}: the mutation did not land")
                continue
            if m in SURVIVORS:
                whole(f"{m['id']} {m['what']} (REV, survives, seeded)")
            else:
                expect(f"{m['id']} {m['what']} (REV)", m['tests'], m['red'])
            target.write_text(after)
        if target.read_text() != after:
            failures.append('the scratch module was not restored')
    finally:
        print(f'F9: scratch tree left at {tree}', flush=True)
    for line in failures:
        print(f'F9: FAIL {line}', file=sys.stderr)
    print(f'F9: {"FAIL" if failures else "ok"} ({len(failures)} failures)')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
