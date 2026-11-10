"""Mutant sweep of tests/test_annotations.py: every decision of the check, run in both eras.

Each mutant changes one decision in the check (discovery, the position reader, evaluation and the
failed-import fallback, the type walk), additive carve-outs included: places the check could grow a
blind spot. Each runs the whole module in each protocol era. A mutant is killed when the module is
red in both eras; the record names the rows that killed it. A mutant recorded as equivalent carries
the reason no reachable input tells it apart, and must survive: a killed equivalent is re-judged.

Reads committed state: the module is taken from `git archive` of REV (HEAD by default) into a
scratch tree synced offline into its own environment, so a mutant never touches the worktree.

Usage: .venv/bin/python -I spec/annotation-check/verify/sweep.py [--rev REV] [--record PATH] [--check]
                                                                  [--worktree-module] [ID...]
  --check            validate every anchor against the worktree's module and exit (no runs)
  --worktree-module  sweep the worktree's uncommitted module over REV's tree (a cheap pass while
                     rows are written; a recorded sweep reads committed state only)
  ID...     run only the named mutants (the baseline always runs)
Exit 0 when the baseline is green in both eras, every non-equivalent mutant is killed in both, and
every equivalent survives. Footprint: one pytest at a time (plus the tree test's child interpreter);
about 85 mutants x 2 eras x ~4 s.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MODULE = 'tests/test_annotations.py'
TIMEOUT = 300
ERAS = ('legacy', 'modern')

FN_ARGS = ("        for arg in [*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg]:\n"
           "            if arg is not None and arg.annotation is not None:")
DEF_BRANCH = ("            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):\n"
              "                function(statement, scopes)")
CLASS_BRANCH = "            elif isinstance(statement, ast.ClassDef):\n"
ADD_POSITION = "        found.append(Position(module, annotation.lineno, name, kind, text, expr, owner, local_class,\n"
RGLOB = "    for file in sorted(src.rglob('*.py')):\n"


def mutant(ident: str, what: str, old: str, new: str, equivalent: str = '') -> dict[str, str]:
    return {'id': ident, 'what': what, 'old': old, 'new': new, 'equivalent': equivalent}


MUTANTS = [
    # Discovery.
    mutant('D01', 'exclude globs ignored',
           "    excluded = {p.resolve() for pattern in workspace.get('exclude', []) for p in root.glob(pattern)}",
           '    excluded = set()'),
    mutant('D02', 'the root is not a member', '    members = {root}\n', '    members = set()\n'),
    mutant('D03', 'package __init__ modules skipped',
           "        if parts and parts[-1] == '__init__':\n            parts = parts[:-1]\n",
           "        if parts and parts[-1] == '__init__':\n            continue\n"),
    mutant('D04', 'modules read only to depth 3', RGLOB,
           "    for file in sorted(f for f in src.rglob('*.py') if len(f.relative_to(src).parts) <= 3):\n"),
    mutant('D05', 'modules only in regular packages (namespace directories skipped)', RGLOB,
           "    for file in sorted(f for f in src.rglob('*.py') if (f.parent / '__init__.py').exists()):\n"),
    mutant('D06', 'private modules skipped', "        if parts:\n            modules.append(",
           "        if parts and not parts[-1].startswith('_'):\n            modules.append("),
    mutant('D07', 'a member without src/ passes silently',
           "            if member != root:\n                report['violations'].append(",
           "            if False:\n                report['violations'].append("),
    mutant('D08', 'only the first member with positions is checked',
           "        for name, file in modules:\n            positions, refusals = module_check(name, file)",
           "        for name, file in (modules if not report['positions'] else []):\n"
           "            positions, refusals = module_check(name, file)"),
    mutant('D09', 'the last member is skipped', '    for member in workspace_members(root):\n',
           '    for member in workspace_members(root)[:-1]:\n'),
    mutant('D10', 'only the first members glob is read', "    for pattern in workspace.get('members', []):\n",
           "    for pattern in workspace.get('members', [])[:1]:\n"),
    mutant('D11', 'modules with postponed annotations skipped', '    source = path.read_text()\n',
           "    source = path.read_text()\n    if 'from __future__ import annotations' in source:\n        return [], []\n"),
    mutant('D12', 'modules with eager annotations skipped', '    source = path.read_text()\n',
           "    source = path.read_text()\n    if 'from __future__ import annotations' not in source:\n        return [], []\n"),
    mutant('D13', 'a module that does not parse passes silently',
           "        return [], [f'{module}:{exc.lineno}: the module does not parse: {exc.msg}']",
           '        return [], []'),
    mutant('D14', 'a __main__ module with annotations passes silently',
           '        return positions, [_refusal(p, why) for p in positions]', '        return positions, []'),
    mutant('D15', 'a __main__ module is imported like any other', "    if module.rsplit('.', 1)[-1] == '__main__':\n",
           '    if False:\n'),
    mutant('D16', 'a module with no positions is imported too', '    if not positions:\n        return positions, []\n', ''),
    mutant('D17', 'a module loaded from another file is accepted',
           '    if file is None or Path(file).resolve() != path.resolve():', '    if False:'),
    mutant('D18', 'the loaded file is compared without resolving links',
           '    if file is None or Path(file).resolve() != path.resolve():', '    if file is None or file != str(path):'),
    # The position reader.
    mutant('R01', 'module variables skipped', "if where != 'function' and statement.simple",
           "if where not in ('function', 'module') and statement.simple"),
    mutant('R02', 'class attributes skipped', "if where != 'function' and statement.simple",
           "if where not in ('function', 'class') and statement.simple"),
    mutant('R03', 'parameters skipped', FN_ARGS, FN_ARGS.replace('if arg is not None and', 'if False and')),
    mutant('R04', 'returns skipped', '        if node.returns is not None:\n', '        if False:\n'),
    mutant('R05', '*args and **kwargs skipped', FN_ARGS, FN_ARGS.replace('args.vararg, ', '').replace(', args.kwarg]', ']')),
    mutant('R06', 'positional-only and keyword-only parameters skipped', FN_ARGS,
           FN_ARGS.replace('*args.posonlyargs, ', '').replace('*args.kwonlyargs, ', '')),
    mutant('R07', 'functional class forms skipped', '        target = statement.targets[0].id\n',
           '        pairs = []\n        target = statement.targets[0].id\n'),
    mutant('R08', 'list-of-pairs fields skipped', '    if isinstance(fields, (ast.List, ast.Tuple)):\n        return [',
           '    if False:\n        return ['),
    mutant('R09', 'dict fields skipped', '    if isinstance(fields, ast.Dict):\n        return [',
           '    if False:\n        return ['),
    mutant('R10', 'aliased functional imports ignored',
           '            forms.update((a.asname, a.name) for a in node.names if a.name in FUNCTIONAL_FORMS and a.asname)',
           '            pass'),
    mutant('R11', 'a functional form called as an attribute ignored',
           'else func.attr if isinstance(func, ast.Attribute) and func.attr in FUNCTIONAL_FORMS else None)',
           'else None)'),
    mutant('R12', 'keyword-form NamedTuple fields ignored', '                pairs += list(keywords.items())\n',
           '                pass\n'),
    mutant('R13', "make_dataclass's fields= keyword ignored",
           "keywords.get('fields') if form == 'make_dataclass' else None", 'None'),
    mutant('R14', 'make_dataclass (name, type, field) triples ignored', 'len(e.elts) in (2, 3)', 'len(e.elts) == 2'),
    mutant('R15', "three-argument type()'s __annotations__ ignored", '                        pairs += _field_pairs(value)\n',
           '                        pass\n'),
    mutant('R16', 'functional forms in class bodies ignored',
           "                if where != 'function':\n                    functional(",
           "                if where == 'module':\n                    functional("),
    mutant('R17', 'classes nested in classes skipped', CLASS_BRANCH,
           CLASS_BRANCH + "                if where == 'class':\n                    continue\n"),
    mutant('R18', 'classes defined in functions skipped', CLASS_BRANCH,
           CLASS_BRANCH + "                if where == 'function':\n                    continue\n"),
    mutant('R19', 'decorated classes skipped', CLASS_BRANCH,
           CLASS_BRANCH + '                if statement.decorator_list:\n                    continue\n'),
    mutant('R20', 'nested functions skipped', DEF_BRANCH,
           DEF_BRANCH.replace('                function(', "                if where != 'function':\n                    function(")),
    mutant('R21', 'methods skipped', DEF_BRANCH,
           DEF_BRANCH.replace('                function(', "                if where != 'class':\n                    function(")),
    mutant('R22', 'async functions skipped', DEF_BRANCH,
           DEF_BRANCH.replace('(ast.FunctionDef, ast.AsyncFunctionDef)', 'ast.FunctionDef')),
    mutant('R23', 'decorated functions skipped', DEF_BRANCH,
           DEF_BRANCH.replace('                function(', '                if not statement.decorator_list:\n                    function(')),
    mutant('R24', 'if bodies skipped', '                if not _is_type_checking(statement.test):\n', '                if False:\n'),
    mutant('R25', 'else branches skipped', '                body(statement.orelse, scopes, where)\n', '                pass\n'),
    mutant('R26', 'typing.TYPE_CHECKING bodies read',
           "or (isinstance(test, ast.Attribute) and test.attr == 'TYPE_CHECKING'))", 'or False)'),
    mutant('R27', 'try blocks skipped', '    if isinstance(statement, (ast.Try, ast.TryStar)):\n        return [',
           '    if isinstance(statement, (ast.Try, ast.TryStar)):\n        return []\n        return ['),
    mutant('R28', 'except handlers skipped', '*(h.body for h in statement.handlers), ', ''),
    mutant('R29', 'try else and finally skipped', ', statement.orelse, statement.finalbody]', ']'),
    mutant('R30', 'with blocks skipped', '    if isinstance(statement, (ast.With, ast.AsyncWith)):\n        return [statement.body]',
           '    if isinstance(statement, (ast.With, ast.AsyncWith)):\n        return []'),
    mutant('R31', 'for and while blocks skipped',
           '    if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):\n        return [statement.body, statement.orelse]',
           '    if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):\n        return []'),
    mutant('R32', 'match blocks skipped', '        return [case.body for case in statement.cases]', '        return []'),
    mutant('R33', 'private names skipped', ADD_POSITION,
           "        if name.rsplit('.', 1)[-1].startswith('_'):\n            return\n" + ADD_POSITION),
    mutant('R34', 'string annotations skipped', ADD_POSITION,
           '        if isinstance(annotation, ast.Constant):\n            return\n' + ADD_POSITION),
    mutant('R35', 'multi-line annotations skipped', ADD_POSITION,
           '        if annotation.end_lineno != annotation.lineno:\n            return\n' + ADD_POSITION),
    # Scope, evaluation, refusal.
    mutant('E01', 'no scope-dependence refusal', '    if position.shadowed:\n', '    if False:\n'),
    mutant('E02', 'enclosing-scope imports not bound', "        elif isinstance(n, ast.alias) and n.name != '*':\n",
           '        elif False:\n'),
    mutant('E03', 'enclosing-function parameters not bound',
           '            if arg is not None:\n                names.add(arg.arg)\n', '            pass\n'),
    mutant('E04', 'enclosing-scope def and class names not bound', '            names.add(n.name)\n            return\n',
           '            return\n'),
    mutant('E05', 'string forward references not read for names',
           "                visit(ast.parse(n.value.strip(), mode='eval').body)\n", '                pass\n'),
    mutant('E06', 'subscript arguments not read for names', '            visit(n.slice)\n        else:', '            pass\n        else:'),
    mutant('E07', 'an unresolvable annotation passes', "        return f'does not resolve: {type(exc).__name__}: {exc}'",
           '        return None'),
    mutant('E08', 'a hint the walk cannot check passes',
           "        return f'could not be checked: {type(exc).__name__}: {exc}, resolving to {_shown(hint)}'",
           '        return None'),
    mutant('E09', 'an unreachable class is evaluated with the globals',
           "        return (f'its class {qualname} cannot be reached as itself",
           "        return {}\n        return (f'its class {qualname} cannot be reached as itself"),
    mutant('E10', "a class's qualified name is not compared",
           "    if (not isinstance(found, type) or getattr(found, '__qualname__', None) != qualname\n",
           '    if (not isinstance(found, type)\n'),
    mutant('E11', "a class's module is not compared",
           "            or getattr(found, '__module__', None) != position.module):", '            ):'),
    mutant('E12', "attributes evaluated without their class's namespace", '    return dict(vars(found))\n', '    return {}\n'),
    mutant('E13', 'type parameters left unbound', '        scope[name] = TYPE_PARAMETER_KINDS[kind](name)\n', '        pass\n'),
    mutant('E14', 'a failed import passes silently',
           '        return positions, _failed_import(module, path, source, positions, exc)', '        return positions, []'),
    mutant('E15', "a failed import's positions are not evaluated",
           '    for position in positions:\n        if not start <= position.line <= end:',
           '    for position in []:\n        if not start <= position.line <= end:'),
    mutant('E16', "a failed import outside the module's own frame passes silently",
           "    if not own:\n        return [f'{module}: the import raised {type(exc).__name__}: {message}']",
           '    if not own:\n        return []'),
    mutant('E17', "a failed import's frame matched by an unresolved path",
           'Path(f.f_code.co_filename).resolve() == resolved', 'f.f_code.co_filename == str(path)'),
    mutant('E18', 'the outermost statement taken, not the innermost',
           '                inner = _innermost_statement(block, line)\n                if inner is not None:\n                    return inner\n',
           '                pass\n'),
    mutant('E19', 'only the first refusal of a failed statement',
           '            refusals.append(_refusal(position, why))\n    return refusals\n',
           '            refusals.append(_refusal(position, why))\n            break\n    return refusals\n'),
    mutant('E20', "the traceback's class namespace ignored", '            localns = _traceback_namespace(position, frames)\n',
           '            localns = None\n'),
    mutant('E21', "decorator lines not part of a statement's span (frame lookup)",
           "        start = min([statement.lineno, *(d.lineno for d in getattr(statement, 'decorator_list', ()))])\n"
           '        if start <= line',
           '        start = statement.lineno\n        if start <= line'),
    mutant('E22', "decorator lines not part of a statement's span (position filter)",
           "    start = min([statement.lineno, *(d.lineno for d in getattr(statement, 'decorator_list', ()))])\n    end =",
           '    start = statement.lineno\n    end =',
           equivalent='a decorator holds no annotation, so every position of a decorated statement is on or after '
                      'its def or class line: the filter selects the same positions with or without the decorator lines'),
    # The type walk.
    mutant('W01', 'a slice accepted', '        if h is Ellipsis:\n',
           '        if isinstance(h, slice):\n            return\n        if h is Ellipsis:\n'),
    mutant('W02', '... accepted anywhere', "        if h is Ellipsis:\n            bad(",
           '        if h is Ellipsis:\n            return\n            bad('),
    mutant('W03', 'a list argument accepted anywhere', '        elif isinstance(h, (list, tuple)):\n            bad(',
           '        elif isinstance(h, (list, tuple)):\n            return\n            bad('),
    mutant('W04', 'a string left unresolved accepted', '        elif isinstance(h, (str, typing.ForwardRef)):\n            bad(',
           '        elif isinstance(h, (str, typing.ForwardRef)):\n            return\n            bad('),
    mutant('W05', 'unsubscripted special forms accepted', '        if any(h is form for form in BARE_FORMS):\n',
           '        if False:\n'),
    mutant('W06', "Annotated's type unchecked", '            walk(args[0], top)\n', '            pass\n'),
    mutant('W07', "a slice in Annotated's metadata accepted", '                if isinstance(meta, slice):', '                if False:'),
    mutant('W08', "a type alias's value not walked", '                walk(h.__value__, False)\n', '                pass\n'),
    mutant('W09', "a subscripted type alias's value not walked",
           '        if isinstance(origin, typing.TypeAliasType):\n            walk(origin, False)\n',
           '        if isinstance(origin, typing.TypeAliasType):\n            pass\n'),
    mutant('W10', "a NewType's supertype not walked", '                walk(h.__supertype__, False)\n', '                pass\n'),
    mutant('W11', "an alias walked again however often it recurs",
           '            if not any(h is w for w in walked):\n                walked.append(h)\n                walk(h.__value__, False)\n',
           '            walked.append(h)\n            walk(h.__value__, False)\n'),
    mutant('W12', "a Callable's parameters not walked", '                parameters(args[0])\n', '                pass\n'),
    mutant('W13', "a Callable's return not walked", '                walk(args[-1], False)\n', '                pass\n'),
    mutant('W14', "a Callable's parameter list not walked",
           '        elif isinstance(given, list):\n            for item in given:\n                walk(item, False)\n',
           '        elif isinstance(given, list):\n            pass\n'),
    mutant('W15', "a Concatenate's prefix not walked", '            for arg in args[:-1]:\n                walk(arg, False)\n',
           '            for arg in args[:-1]:\n                pass\n'),
    mutant('W16', "a Concatenate's last argument unchecked",
           '            if args and not (args[-1] is Ellipsis or isinstance(args[-1], typing.ParamSpec)):',
           '            if False:',
           equivalent='typing refuses to build a Concatenate whose last argument is neither a ParamSpec nor ..., '
                      'so no resolved hint reaches this branch with one'),
    mutant('W17', 'a tuple[X, ...] element not walked',
           '        if origin is tuple and len(args) == 2 and args[1] is Ellipsis:\n            walk(args[0], False)\n',
           '        if origin is tuple and len(args) == 2 and args[1] is Ellipsis:\n            pass\n'),
    mutant('W18', "a ParamSpec generic's list argument not walked", '                for item in arg:\n                    walk(item, False)\n',
           '                for item in arg:\n                    pass\n'),
    mutant('W19', 'a list argument refused even over a ParamSpec',
           '        over_paramspec = isinstance(declared, tuple) and any(', '        over_paramspec = False and any('),
    mutant('W20', 'only the first generic argument walked', '        for arg in args:\n            if isinstance(arg, (list, tuple)) and over_paramspec:',
           '        for arg in args[:1]:\n            if isinstance(arg, (list, tuple)) and over_paramspec:'),
    mutant('W21', 'builtin containers accepted unwalked', '        if origin is not None:\n            generic(h, origin, typing.get_args(h), top)\n',
           '        if origin in (dict, list):\n            return\n        if origin is not None:\n            generic(h, origin, typing.get_args(h), top)\n'),
    mutant('W22', 'Literal values unchecked', '                if not (arg is None or isinstance(arg, LITERAL_VALUES)):', '                if False:'),
    mutant('W23', 'a qualifier accepted anywhere', '        if top and kind in kinds:\n', '        if True:\n'),
    mutant('W24', 'a qualifier accepted in any kind of position', '        if top and kind in kinds:\n', '        if top:\n'),
    mutant('W25', "a qualifier's argument not walked", '            if placed(*q, top):\n                for arg in args:\n                    walk(arg, True)\n',
           '            if placed(*q, top):\n                pass\n'),
    mutant('W26', "InitVar's argument not walked", '                walk(h.type, False)\n', '                pass\n'),
    mutant('W27', 'type parameters refused', '        if any(h is form for form in BARE_TYPES) or isinstance(h, TYPE_PARAMETERS):\n',
           '        if any(h is form for form in BARE_TYPES):\n'),
]


def sh(argv: list[str], cwd: Path, env: dict[str, str] | None = None) -> tuple[int, str, float]:
    start = time.monotonic()
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
        return -1, out + f'\n(timed out after {TIMEOUT} s)', time.monotonic() - start
    return proc.returncode, out, time.monotonic() - start


def run_module(tree: Path, era: str) -> tuple[int, list[str], str]:
    env = dict(os.environ)
    env.pop('CLUSTER_MCP_TEST_ERA', None)
    if era == 'modern':
        env['CLUSTER_MCP_TEST_ERA'] = 'modern'
    code, out, _ = sh([str(tree / '.venv' / 'bin' / 'python'), '-m', 'pytest', '-q', '-p', 'no:cacheprovider', MODULE],
                      tree, env)
    failed = sorted({m.group(1).split('::', 1)[1] for m in re.finditer(r'^(?:FAILED|ERROR) (\S+)', out, re.M)})
    summary = next((line for line in reversed(out.splitlines()) if re.search(r'\d+ (passed|failed|error)', line)), '')
    return code, failed, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--rev', default='HEAD')
    parser.add_argument('--record')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--worktree-module', action='store_true')
    parser.add_argument('ids', nargs='*')
    args = parser.parse_args()
    repo = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
                               check=True).stdout.strip())
    ids = [m['id'] for m in MUTANTS]
    assert len(set(ids)) == len(ids), 'duplicate mutant ids'
    unknown = [i for i in args.ids if i not in ids]
    if unknown:
        print(f'sweep: FAIL no mutant is named {unknown}', file=sys.stderr)
        return 1
    if args.check:
        text = (repo / MODULE).read_text()
        stale = [(m['id'], text.count(m['old'])) for m in MUTANTS if text.count(m['old']) != 1]
        for ident, count in stale:
            print(f'sweep: FAIL {ident}: its anchor occurs {count} times in {MODULE}', file=sys.stderr)
        print(f'sweep: {"FAIL" if stale else "ok"} anchors ({len(MUTANTS)} mutants)')
        return 1 if stale else 0

    rev = subprocess.run(['git', 'rev-parse', '--short', args.rev], cwd=repo, capture_output=True, text=True,
                         check=True).stdout.strip()
    tree = Path(tempfile.mkdtemp(prefix='ac-sweep.'))
    os.environ.setdefault('UV_PYTHON', '3.14')
    try:
        archive = subprocess.Popen(['git', 'archive', rev], cwd=repo, stdout=subprocess.PIPE)
        subprocess.run(['tar', '-x', '-C', str(tree)], stdin=archive.stdout, check=True)
        archive.wait()
        if args.worktree_module:
            if args.record:
                print('sweep: FAIL a record reads committed state: drop --worktree-module', file=sys.stderr)
                return 1
            shutil.copyfile(repo / MODULE, tree / MODULE)
        if sh(['uv', 'sync', '--locked', '--offline', '-q'], tree)[0] != 0:
            code, out, _ = sh(['uv', 'sync', '--locked', '-q'], tree)
            if code != 0:
                print(f'sweep: FAIL setup: {out[-2000:]}', file=sys.stderr)
                return 1
        target = tree / MODULE
        original = target.read_text()
        rows: list[dict[str, object]] = []
        bad: list[str] = []
        base = {era: run_module(tree, era) for era in ERAS}
        for era, (code, failed, summary) in base.items():
            print(f'sweep: baseline {era}: exit {code}, {summary}', flush=True)
            if code != 0:
                bad.append(f'baseline red in the {era} era: {failed}')
        chosen = [m for m in MUTANTS if not args.ids or m['id'] in args.ids]
        for m in chosen if not bad else []:
            if original.count(m['old']) != 1:
                bad.append(f'{m["id"]}: its anchor occurs {original.count(m["old"])} times')
                print(f'sweep: FAIL {m["id"]}: stale anchor', flush=True)
                continue
            target.write_text(original.replace(m['old'], m['new']))
            try:
                if target.read_text() == original:
                    bad.append(f'{m["id"]}: the mutation did not land')
                    continue
                results = {era: run_module(tree, era) for era in ERAS}
            finally:
                target.write_text(original)
            assert target.read_text() == original, 'the module was not restored'
            killed = all(code != 0 for code, _, _ in results.values())
            survived_in = [era for era, (code, _, _) in results.items() if code == 0]
            if m['equivalent']:
                verdict = 'equivalent (survives)' if not killed and len(survived_in) == 2 else 'equivalent KILLED: re-judge'
            else:
                verdict = 'killed' if killed else f'SURVIVED ({", ".join(survived_in)})'
            if verdict not in ('killed', 'equivalent (survives)'):
                bad.append(f'{m["id"]} {m["what"]}: {verdict}')
            killers = sorted(set(results['legacy'][1]) & set(results['modern'][1])) or sorted(
                set(results['legacy'][1]) | set(results['modern'][1]))
            rows.append({'id': m['id'], 'what': m['what'], 'verdict': verdict, 'killers': killers,
                         'equivalent': m['equivalent'],
                         'summaries': {era: results[era][2] for era in ERAS}})
            print(f'sweep: {m["id"]} {verdict}: {", ".join(killers[:3]) or "-"}', flush=True)
        if args.record:
            write_record(Path(args.record), rev, base, rows, bad)
        for line in bad:
            print(f'sweep: FAIL {line}', file=sys.stderr)
        print(f'sweep: {"FAIL" if bad else "ok"} {len(rows)} mutants, '
              f'{sum(r["verdict"] == "killed" for r in rows)} killed in both eras, '
              f'{sum(str(r["verdict"]).startswith("equivalent (") for r in rows)} equivalent')
        return 1 if bad else 0
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def write_record(path: Path, rev: str, base: dict[str, tuple[int, list[str], str]], rows: list[dict[str, object]],
                 bad: list[str]) -> None:
    lines = [
        '# Mutant sweep record: tests/test_annotations.py',
        '',
        f'Written by `verify/sweep.py` on {datetime.date.today().isoformat()}, over the module at `{rev}`, '
        f'Python {sys.version.split()[0]}. Each mutant ran the whole module in each era; killed means red in '
        'both. "Rows" are the tests red in both eras (the first five).',
        '',
        f'- Baseline: legacy `{base["legacy"][2]}`; modern `{base["modern"][2]}`.',
        f'- Result: {len(rows)} mutants, {sum(r["verdict"] == "killed" for r in rows)} killed in both eras, '
        f'{sum(str(r["verdict"]).startswith("equivalent (") for r in rows)} equivalent, '
        f'{len(bad)} failures{": " + "; ".join(bad) if bad else ""}.',
        '',
        '| Id | Mutant | Verdict | Rows |',
        '|----|--------|---------|------|',
    ]
    for r in rows:
        killers = ', '.join(f'`{k}`' for k in list(r['killers'])[:5]) + (
            f' (+{len(r["killers"]) - 5})' if len(r['killers']) > 5 else '')
        lines.append(f'| {r["id"]} | {r["what"]} | {r["verdict"]} | {killers or "-"} |')
    equivalents = [r for r in rows if r['equivalent']]
    if equivalents:
        lines += ['', '## Equivalent mutants', '']
        lines += [f'- **{r["id"]}** ({r["what"]}): {r["equivalent"]}.' for r in equivalents]
    path.write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    sys.exit(main())
