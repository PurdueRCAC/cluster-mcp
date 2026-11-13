"""Kill evidence for review cycle 2's N1 (checker F6), N2 (F7) and the tree test's oracle (F8).

Review cycle 2 (`REVIEW.md`) found the functional class forms read in one spelling only, other
spellings passing silently (N1); the dataclass `_: KW_ONLY` marker refused (N2); and the tree
test's expected positions taken from the syntax reader it checks (N3's root cause). This checker
shows each fix has teeth, in both protocol eras, reading committed state:

- before: the new rows run against the check as it stood at BEFORE (its functions, with REV's
  rows and oracle) are red: every unreadable spelling passes there, and `KW_ONLY` is refused;
- after: the same rows are green at REV;
- each mutant undoes one part of a fix at REV, and the rows named for it are red;
- the reader mutants the review recorded as surviving the old tree test (N3) are applied to both
  modules: at BEFORE the tree test stays green, at REV it is red, because its expected positions now
  come from what the interpreter keeps, not from the reader.

Usage: .venv/bin/python -I spec/annotation-check/remediation/F6-F8-review2.py [--rev REV] [--before REV]
                                                                             [--worktree-module] [ID...]
  --worktree-module  use the worktree's uncommitted module over REV's tree (a cheap pass while rows are
                     written; evidence reads committed state only)
A row prefix named red means every collected row with that prefix fails. Exit 0 when every
expectation holds. The scratch tree is left in place and its path printed. Footprint: one pytest at
a time (plus the tree test's child interpreter); about 60 runs of 2 to 4 s.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MODULE = 'tests/test_annotations.py'
TIMEOUT = 300
ERAS = ('legacy', 'modern')
BEFORE = '9d8c01a'
TREE = 'test_every_kept_annotation_in_the_workspace_is_a_type'
FORMS = 'test_an_unreadable_functional_form_is_refused'
VALID = 'test_valid_shapes_pass'
QUALIFIER = 'test_a_qualifier_out_of_its_place_is_named'
TABLE = 'test_non_types_are_named'
HIDDEN = 'test_a_type_checking_only_declaration_is_not_read'
PLANTED = 'test_a_planted_slice_is_refused_naming_where'

# The rows the fixes added, which must be red against the check at BEFORE.
NEW_ROWS = [f'{FORMS}[', f'{VALID}[', f'{QUALIFIER}[kw-only-', f'{TABLE}[kw-only-']


def mutant(ident: str, what: str, old: str, new: str, tests: list[str], red: list[str]) -> dict:
    return {'id': ident, 'what': what, 'old': old, 'new': new, 'tests': tests, 'red': red}


OWN = '        own = _type_params(node)\n'
ARGS_READ = ('        for arg in [*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg]:\n'
             '            if arg is not None and arg.annotation is not None:')
CLASS_BODY = "                body(statement.body, [*scopes, inner], 'class')"
ANN = "                if where != 'function' and statement.simple and isinstance(statement.target, ast.Name):"

MUTANTS = [
    # F6 (N1): every spelling read or refused.
    mutant('F6a', 'no unreadable form refused', '    for node, name, why in _unread_forms(tree, forms, read):\n',
           '    for node, name, why in []:\n', [FORMS], [f'{FORMS}[']),
    mutant('F6b', 'a reference to a factory not refused',
           "        elif (form := form_of(node)) is not None and form != 'type' and id(node) not in allowed:",
           '        elif False:', [FORMS], [f'{FORMS}[assigned-alias-', f'{FORMS}[passed-as-a-value-']),
    mutant('F6c', '__annotations__, __annotate__ or a factory spelled outside a read call not refused',
           '        elif id(node) not in read and id(node) not in allowed and (spelled := _spelled(node)) is not None:',
           '        elif False:', [FORMS],
           [f'{FORMS}[namespace-dict-', f'{FORMS}[namespace-keyword-', f'{FORMS}[annotations-assigned-',
            f'{FORMS}[annotations-in-a-class-body-', f'{FORMS}[factory-named-by-a-string-']),
    mutant('F6d', "a call's arguments read whatever they hold",
           '        if form is None or not _builds_a_class(form, call) or _unreadable_call(form, call):\n',
           '        if form is None or not _builds_a_class(form, call):\n', [FORMS],
           [f'{FORMS}[fields-in-a-variable-', f'{FORMS}[fields-from-a-call-', f'{FORMS}[field-in-a-variable-',
            f'{FORMS}[make-dataclass-namespace-', f'{FORMS}[type-namespace-in-a-variable-']),
    mutant('F6e', 'an unread keyword accepted', "            return f'it takes the keyword {extra[0]}, which the check does not read'",
           "            return ''", [FORMS], [f'{FORMS}[make-dataclass-namespace-']),
    mutant('F6f', 'an if TYPE_CHECKING body searched for forms',
           '        if isinstance(node, ast.If) and _is_type_checking(node.test):\n', '        if False:\n',
           [HIDDEN], [f'{HIDDEN}[']),
    mutant('F6g', "a class statement's base refused", '                allowed.update(id(base) for base in node.bases)\n',
           '                pass\n', [VALID], [f'{VALID}[']),
    mutant('F6i', "a read type call's namespace keys refused as spelled",
           '                read.update(id(key) for key in namespace.keys if key is not None)\n', '', [PLANTED],
           [f'{PLANTED}[type-namespace-']),
    mutant('F6j', "a refused call's arguments refused again on their own",
           '                allowed.update(id(n) for arg in [*node.args, *node.keywords] for n in ast.walk(arg))\n',
           '                pass\n', [FORMS],
           [f'{FORMS}[make-dataclass-namespace-', f'{FORMS}[type-annotate-', f'{FORMS}[new-class-',
            f'{FORMS}[type-namespace-unpacked-']),
    mutant('F6h', 'a one-argument type() taken for a class form', "        return unpacked or len(call.args) == 3\n",
           '        return True\n', [VALID], [f'{VALID}[']),
    # F7 (N2): KW_ONLY accepted on a class attribute, and only there.
    mutant('F7a', 'KW_ONLY refused as a non-type', "    (dataclasses.KW_ONLY, 'KW_ONLY', frozenset({ATTRIBUTE})),\n", '',
           [VALID, TABLE], [f'{VALID}[', f'{TABLE}[kw-only-parameter]']),
    mutant('F7b', 'KW_ONLY accepted in any kind of position',
           "    (dataclasses.KW_ONLY, 'KW_ONLY', frozenset({ATTRIBUTE})),\n",
           "    (dataclasses.KW_ONLY, 'KW_ONLY', frozenset({VARIABLE, ATTRIBUTE, PARAMETER, RETURN})),\n",
           [QUALIFIER, TABLE], [f'{QUALIFIER}[kw-only-variable-', f'{QUALIFIER}[kw-only-parameter-',
                                f'{TABLE}[kw-only-parameter]']),
    # F8: the oracle itself is not vacuous.
    mutant('F8a', 'the oracle finds nothing', "    return {'positions': sorted(kept), 'unreadable': unreadable}\n",
           "    return {'positions': [], 'unreadable': unreadable}\n", [TREE], [TREE]),
    mutant('F8b', 'the oracle reads no function', '        if not isinstance(obj, types.FunctionType):\n',
           '        if True:\n', [TREE], [TREE]),
]

# The reader mutants review cycle 2 recorded as surviving (its N3) that skip a shape the tree holds,
# anchored on text the reader keeps unchanged between BEFORE and REV. Its D20 (`self` and `cls`
# skipped) is not here: the tree annotates neither, so no oracle over the tree can tell it apart.
READER = [
    mutant('D10', 'functions with an attribute decorator skipped', OWN,
           OWN + '        if any(isinstance(d, ast.Attribute) for d in node.decorator_list):\n            return\n', [TREE], [TREE]),
    mutant('D11', 'functions with a call decorator skipped', OWN,
           OWN + '        if any(isinstance(d, ast.Call) for d in node.decorator_list):\n            return\n', [TREE], [TREE]),
    mutant('D12', 'classmethods skipped', OWN,
           OWN + "        if any(isinstance(d, ast.Name) and d.id == 'classmethod' for d in node.decorator_list):\n"
           '            return\n', [TREE], [TREE]),
    mutant('D13', 'properties skipped', OWN,
           OWN + "        if any(isinstance(d, ast.Name) and d.id == 'property' for d in node.decorator_list):\n"
           '            return\n', [TREE], [TREE]),
    mutant('D17', 'private functions skipped', OWN,
           OWN + "        if node.name.startswith('_') and not node.name.startswith('__'):\n            return\n", [TREE], [TREE]),
    mutant('D18', 'dunder methods skipped', OWN, OWN + "        if node.name.startswith('__'):\n            return\n",
           [TREE], [TREE]),
    mutant('D19', 'parameters with a default skipped', ARGS_READ,
           '        _n = [*args.posonlyargs, *args.args]\n'
           '        _skip = ({a.arg for a in _n[len(_n) - len(args.defaults):]}\n'
           '                 | {a.arg for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is not None})\n'
           + ARGS_READ.replace('arg.annotation is not None:', 'arg.annotation is not None and arg.arg not in _skip:'),
           [TREE], [TREE]),
    mutant('B5', 'classes with a call decorator skipped', CLASS_BODY,
           '                if not any(isinstance(d, ast.Call) for d in statement.decorator_list):\n    ' + CLASS_BODY,
           [TREE], [TREE]),
    mutant('B10', 'private class attributes skipped', ANN,
           ANN.rstrip(':') + " and not (where == 'class' and statement.target.id.startswith('_')):", [TREE], [TREE]),
]


def sh(argv: list[str], cwd: Path, env: dict[str, str] | None = None) -> tuple[int, str]:
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
        return -1, out + f'\n(timed out after {TIMEOUT} s)'
    return proc.returncode, out


def run(tree: Path, era: str, tests: list[str]) -> tuple[int, list[str], str]:
    env = dict(os.environ)
    env.pop('CLUSTER_MCP_TEST_ERA', None)
    if era == 'modern':
        env['CLUSTER_MCP_TEST_ERA'] = 'modern'
    code, out = sh([str(tree / '.venv' / 'bin' / 'python'), '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                    *[f'{MODULE}::{t}' for t in tests]], tree, env)
    failed = sorted({m.group(1).split('::', 1)[1] for m in re.finditer(r'^(?:FAILED|ERROR) (\S+)', out, re.M)})
    summary = next((line for line in reversed(out.splitlines()) if re.search(r'\d+ (passed|failed|error)', line)), '')
    return code, failed, summary


def collected(tree: Path, tests: list[str]) -> list[str]:
    code, out = sh([str(tree / '.venv' / 'bin' / 'python'), '-m', 'pytest', '-q', '--collect-only', '-p',
                    'no:cacheprovider', *[f'{MODULE}::{t}' for t in tests]], tree)
    return [line.split('::', 1)[1] for line in out.splitlines() if line.startswith(f'{MODULE}::')]


def hybrid(before: str, after: str) -> str:
    """BEFORE's check functions with REV's rows and oracle: the check as it stood, graded by the new rows."""
    head = before.split('\n# The tree.\n', 1)[0]
    tail = after.split('\n# The tree.\n', 1)[1]
    tree = ast.parse(after)
    oracle = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'runtime_positions')
    unreadable = next(n for n in tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'UNREADABLE' for t in n.targets))
    added = ['import annotationlib', 'import gc', ast.get_source_segment(after, unreadable),
             ast.get_source_segment(after, oracle)]
    head = head.replace('from __future__ import annotations\n', 'from __future__ import annotations\n'
                        + '\n'.join(added[:2]) + '\n', 1)
    return head + '\n\n' + '\n\n\n'.join(added[2:]) + '\n\n\n# The tree.\n' + tail


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
    tree = Path(tempfile.mkdtemp(prefix='ac-f6f8.'))
    os.environ.setdefault('UV_PYTHON', '3.14')
    failures: list[str] = []

    def expect(label: str, tests: list[str], red: list[str] | None) -> None:
        """Run `tests` in both eras: green when `red` is None, else every prefix in `red` among the failures."""
        rows = collected(tree, tests)
        wanted = [r for r in rows if red is not None and any(r.startswith(p) for p in red)]
        if red is not None and not all(any(r.startswith(p) for r in rows) for p in red):
            failures.append(f'{label}: a row named red is not collected: {red}')
        for era in ERAS:
            start = time.monotonic()
            code, failed, summary = run(tree, era, tests)
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
        everything = [TREE, FORMS, VALID, QUALIFIER, TABLE, HIDDEN, PLANTED]
        print(f'F6-F8: rev {rev}, before {args.before}', flush=True)
        if not args.ids:
            expect('after: the rows at REV', everything, None)
            target.write_text(hybrid(before, after))
            expect('before: the rows against the check at BEFORE', everything, NEW_ROWS)
            target.write_text(after)
        for m in [*MUTANTS, *READER]:
            if args.ids and m['id'] not in args.ids:
                continue
            count = after.count(m['old'])
            if count != 1:
                failures.append(f"{m['id']}: its anchor occurs {count} times at REV")
                print(f"FAIL {m['id']}: anchor occurs {count} times", flush=True)
                continue
            target.write_text(after.replace(m['old'], m['new']))
            expect(f"{m['id']} {m['what']} (REV)", m['tests'], m['red'])
            if m in READER:
                if before.count(m['old']) != 1:
                    failures.append(f"{m['id']}: its anchor occurs {before.count(m['old'])} times at BEFORE")
                else:
                    target.write_text(before.replace(m['old'], m['new']))
                    expect(f"{m['id']} {m['what']} (BEFORE: survives the old tree test)", [TREE], None)
            target.write_text(after)
        if target.read_text() != after:
            failures.append('the scratch module was not restored')
    finally:
        print(f'F6-F8: scratch tree left at {tree}', flush=True)
    for line in failures:
        print(f'F6-F8: FAIL {line}', file=sys.stderr)
    print(f'F6-F8: {"FAIL" if failures else "ok"} ({len(failures)} failures)')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
