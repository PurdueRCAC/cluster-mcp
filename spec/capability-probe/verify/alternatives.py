# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Every decision the probe adds is mutated to every alternative it could take, and every mutant is
caught under every capability set, in both protocol eras.

    uv run python -I spec/capability-probe/verify/alternatives.py [coverage|cases|equivalents|all] [p1|p2|all] [both|handshake|modern]
                                                                            from the worktree root

The era argument (default both) splits `cases` and `equivalents` by era, and K/N (default 1/1) runs
shard K of N of the cases, so each run fits a caller's 10-minute command cap: a case costs about 6 s
(three measured together on the plan's prototype, 18.7 s), so 93 cases are about 9 min an era
unsharded.

The shape of `spec/capability-extras/remediation/F7-mutant-alternatives.py` (that cycle's review
lesson: one mutant per decision lets its sibling alternatives survive), over this cycle's decisions,
found by parsing the files:

- p1 — `core/probes.py`, every decision; `core/capabilities.py`, the decisions that check a declared
  command (the `if` that checks the field is exactly a tuple, and each check inside the loop over the
  commands);
- p2 — `core/__init__.py`: every decision of `_resolve_skip_probes`, `_probe` and
  `_served`; where `run()` takes each probe statement (the override's resolution, the probe and the
  wait for its verdicts, the budget check against every installed capability), at every other
  boundary of the `try` in `run()` and of its body, and not at all; `core/deprecation.py`: the branch
  of `env_setting` for a variable with no legacy name;
- all — both, for the last phase's whole-cycle coverage. Each phase runs its own cases, so no mode
  repeats an earlier phase's (the cost of a cumulative sweep is its coverage, seconds).

The alternatives of a decision: each `if`, conditional expression and comprehension condition to
always, never and its negation; each boolean operator to each of its operands alone and to the other
operator; each comparison not the whole of a condition to its negation (an ordering comparison to each
other ordering); each `except` clause to `Exception`, to `BaseException`, and to a body that re-raises;
each element of a tuple tested with `in` dropped, and moved to the other tuple of the same function
when there is one; each element of an `isinstance` tuple dropped; and the decisions no node kind names
(`EXTRA`): the bound's figure, the worker thread's `daemon`, the timeout the lookup is given, the
lookup's words, the skip branches' order and what they serve, and what the server is built from.

An alternative is mutated when a case of `tests/mutants.py`, or an equivalent recorded below, turns the
file into the same syntax tree. `coverage` (seconds): every alternative of the phase mutated, and every
such case targets a row beside each member set (`mutants.MEMBER_SETS`) unless `SET_EQUIVALENT` says
why that set cannot observe it; any gap fails, naming it. `cases`: each such case run by
`tests/mutants.py --self-check` in the handshake era, then in revision 2026-07-28's, each killed.
`equivalents`: each recorded equivalent planted, `EQUIVALENT_TARGETS` passing in each era. `all` (the
default) runs the three. Footprint: one mutant child at a time, under 1 GB; `coverage` seconds, `cases`
about 6 s a case per era.
"""

from __future__ import annotations

import ast
import copy
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'tests'))
import mutants  # noqa: E402

NAMESPACE = ROOT / 'packages/cluster-mcp/src/cluster_mcp'
PROBES, LOADER, CLI, DEPRECATION = ('core/probes.py', 'core/capabilities.py', 'core/__init__.py',
                                    'core/deprecation.py')
FILES = {'p1': (PROBES, LOADER), 'p2': (CLI, DEPRECATION), 'all': (PROBES, LOADER, CLI, DEPRECATION)}
ERAS = {'handshake': None, 'modern': 'modern'}
SETS = tuple(mutants.MEMBER_SETS)
CLI_METHODS = ('_resolve_skip_probes', '_probe', '_served')
# The statements of run() this cycle adds, by a word each holds.
PROBE_STATEMENTS = ('_resolve_skip_probes', 'self._served(', 'base_instructions(installed())')

# Decisions no node kind names: (phase, label, file, ((old, new), ...)). An anchor that is not in the
# file is reported as a gap of its own, so a renamed line cannot drop a decision silently.
EXTRA = (
    *(('p1', f'the bound is {v} s', PROBES, (('PROBE_TIMEOUT: Final = 10.0\n', f'PROBE_TIMEOUT: Final = {v}\n'),))
      for v in ('5.0', '9.0', '11.0', '20.0')),
    ('p1', 'the worker thread is not a daemon', PROBES, (("daemon=True", "daemon=False"),)),
    ('p1', 'the lookup is given no timeout', PROBES, (('timeout=timeout)', 'timeout=None)'),)),
    ('p1', 'the lookup is given twice the bound', PROBES, (('timeout=timeout)', 'timeout=2 * timeout)'),)),
    ('p1', 'the lookup finds functions and builtins (command -v)', PROBES,
     (('if type -P -- "$n" >/dev/null 2>&1', 'if command -v -- "$n" >/dev/null 2>&1'),)),
    ('p1', 'the lookup finds functions and builtins (type -t)', PROBES,
     (('if type -P -- "$n" >/dev/null 2>&1', 'if type -t -- "$n" >/dev/null 2>&1'),)),
    ('p1', 'a function named type is not undone', PROBES, (("    'unset -f type\\n'\n", ''),)),
    ('p1', 'the lookup answers 1 and 0 the other way', PROBES,
     (('printf "1\\\\n"; else printf "0\\\\n"', 'printf "0\\\\n"; else printf "1\\\\n"'),)),
    ('p1', 'the lookup prints no count', PROBES, (("    'printf \"end %s\\\\n\" \"$#\"\\n'\n", ''),)),
    ('p2', 'delegate probes', CLI, (("        if exec_mode == 'delegate':\n"
                                     "            log.info('Capability probes skipped in delegate mode: every installed capability is served')\n"
                                     "            return probes.unprobed(loaded)\n", ''),)),
    ('p2', 'the override is read after delegate is decided, and delegate after it', CLI,
     (("        if exec_mode == 'delegate':\n"
       "            log.info('Capability probes skipped in delegate mode: every installed capability is served')\n"
       "            return probes.unprobed(loaded)\n"
       "        if skipped:\n"
       "            log.info(f'Capability probes skipped ({skipped}): every installed capability is served')\n"
       "            return probes.unprobed(loaded)\n",
       "        if skipped:\n"
       "            log.info(f'Capability probes skipped ({skipped}): every installed capability is served')\n"
       "            return probes.unprobed(loaded)\n"
       "        if exec_mode == 'delegate':\n"
       "            log.info('Capability probes skipped in delegate mode: every installed capability is served')\n"
       "            return probes.unprobed(loaded)\n"),)),
    ('p2', 'a skip still probes (delegate)', CLI,
     (("            log.info('Capability probes skipped in delegate mode: every installed capability is served')\n"
       "            return probes.unprobed(loaded)\n",
       "            log.info('Capability probes skipped in delegate mode: every installed capability is served')\n"
       "            return probes.start(executor, loaded)\n"),)),
    ('p2', 'a skip still probes (override)', CLI,
     (("            log.info(f'Capability probes skipped ({skipped}): every installed capability is served')\n"
       "            return probes.unprobed(loaded)\n",
       "            log.info(f'Capability probes skipped ({skipped}): every installed capability is served')\n"
       "            return probes.start(executor, loaded)\n"),)),
    ('p2', 'the server is built from every installed capability', CLI,
     (('                                    capabilities=served)', '                                    capabilities=None)'),)),
    ('p2', 'the budget is checked against the core alone', CLI,
     (('site_context.compose(base_instructions(installed()), site, budget)',
       'site_context.compose(base_instructions(()), site, budget)'),)),
    ('p2', 'the flag is read after the variable', CLI,
     (("        if self.skip_probes:\n            return '--skip-probes'\n", ''),)),
)

# Mutants that change no behaviour, each with why; filled by build as it finds them: name -> ((old,
# new), why), planted in FILE_OF[name] (PROBES when absent).
EQUIVALENT: dict[str, tuple[tuple[str, str], str]] = {}
FILE_OF: dict[str, str] = {}
EQUIVALENT_TARGETS = ('test_probes.py', 'test_startup.py', 'test_capabilities.py', 'test_env.py')
SET_EQUIVALENT: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    'env-no-legacy-value-empty-kept': (
        SETS, (),
        '`env_setting` hands an empty CLUSTER_MCP_SKIP_PROBES back as itself rather than None. Its one reader, '
        '`_resolve_skip_probes`, counts both as unset, so no start, beside any member set, can tell the two '
        'apart; the resolver reads no capability, and its own row (test_env.py, empty) kills it.'),
}


@dataclass(frozen=True)
class Alternative:
    file: str
    line: int
    what: str
    tree: str


class _Settled(ast.NodeTransformer):
    """`if True:` is its body, `if False:` its else, a bare `pass` no statement, `a if True else b` is `a`."""

    def visit_IfExp(self, node: ast.IfExp) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.test, ast.Constant) and node.test.value in (True, False):
            return node.body if node.test.value else node.orelse
        return node

    def generic_visit(self, node: ast.AST) -> ast.AST:
        super().generic_visit(node)
        for field in ('body', 'orelse', 'finalbody'):
            statements = getattr(node, field, None)
            if isinstance(statements, list) and statements and isinstance(statements[0], ast.stmt):
                out: list[ast.stmt] = []
                for s in statements:
                    if isinstance(s, ast.Pass):
                        continue
                    if isinstance(s, ast.If) and isinstance(s.test, ast.Constant) and s.test.value in (True, False):
                        out.extend(s.body if s.test.value else s.orelse)
                        continue
                    out.append(s)
                setattr(node, field, out)
        return node


def settled(module: ast.AST) -> str:
    return ast.dump(_Settled().visit(module))


def tree(text: str) -> str:
    return settled(ast.parse(text))


def source(file: str) -> str:
    return (NAMESPACE / file).read_text()


class _At(ast.NodeTransformer):
    def __init__(self, target: ast.AST, make) -> None:
        self.key = (type(target), target.lineno, target.col_offset, getattr(target, 'end_col_offset', None))
        self.make = make

    def visit(self, node: ast.AST):
        if (type(node), getattr(node, 'lineno', None), getattr(node, 'col_offset', None),
                getattr(node, 'end_col_offset', None)) == self.key:
            return self.make(copy.deepcopy(node))
        return self.generic_visit(node)


def replaced(text: str, target: ast.AST, make) -> str:
    return settled(ast.fix_missing_locations(_At(target, make).visit(ast.parse(text))))


def expr(text: str) -> ast.expr:
    return ast.parse(text, mode='eval').body


NEGATED = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot,
           ast.IsNot: ast.Is}
ORDERING = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)
OPPOSITE = {ast.Lt: ast.GtE, ast.LtE: ast.Gt, ast.Gt: ast.LtE, ast.GtE: ast.Lt}


def negation(node: ast.expr) -> ast.expr:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return node.operand
    return ast.UnaryOp(op=ast.Not(), operand=node)


def decisions(text: str, file: str, scopes: list[ast.AST]) -> list[Alternative]:
    """Every alternative of every decision inside the nodes `scopes` of `text`."""
    module = ast.parse(text)
    found: list[Alternative] = []
    whole: set[tuple] = set()
    wanted = {(type(s), s.lineno, s.col_offset) for s in scopes}
    inside: list[ast.AST] = []
    for node in ast.walk(module):
        if (type(node), getattr(node, 'lineno', None), getattr(node, 'col_offset', None)) in wanted:
            inside.extend(ast.walk(node))
    for node in inside:
        if isinstance(node, (ast.If, ast.IfExp)):
            whole.add((node.test.lineno, node.test.col_offset))
        elif isinstance(node, ast.comprehension):
            whole.update((c.lineno, c.col_offset) for c in node.ifs)

    def add(node: ast.AST, what: str, make) -> None:
        found.append(Alternative(file, node.lineno, what, replaced(text, node, make)))

    def condition(node: ast.expr, kind: str) -> None:
        add(node, f'{kind}: always', lambda n: ast.Constant(True))
        add(node, f'{kind}: never', lambda n: ast.Constant(False))
        add(node, f'{kind}: negated', negation)

    tuples_in = [n for n in inside if isinstance(n, ast.Compare) and len(n.ops) == 1
                 and isinstance(n.ops[0], (ast.In, ast.NotIn)) and isinstance(n.comparators[0], ast.Tuple)]
    for node in inside:
        if isinstance(node, (ast.If, ast.IfExp)):
            condition(node.test, 'if' if isinstance(node, ast.If) else 'conditional expression')
        if isinstance(node, ast.IfExp):
            add(node, 'conditional expression: its value always', lambda n: n.body)
            add(node, 'conditional expression: its other value always', lambda n: n.orelse)
        if isinstance(node, ast.comprehension):
            for c in node.ifs:
                condition(c, 'comprehension condition')
        if isinstance(node, ast.BoolOp):
            for i in range(len(node.values)):
                def drop(n: ast.BoolOp, i: int = i) -> ast.expr:
                    rest = [v for j, v in enumerate(n.values) if j != i]
                    return rest[0] if len(rest) == 1 else ast.BoolOp(op=n.op, values=rest)
                add(node, f'boolean operator: without operand {i + 1}', drop)
            other = ast.Or if isinstance(node.op, ast.And) else ast.And
            add(node, 'boolean operator: the other operator',
                lambda n, other=other: ast.BoolOp(op=other(), values=n.values))
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            op = type(node.ops[0])
            others = [o for o in ORDERING if o is not op] if op in ORDERING[:4] else [NEGATED[op]]
            if (node.lineno, node.col_offset) in whole:
                others = [o for o in others if o is not NEGATED.get(op, OPPOSITE.get(op))]
            for o in others:
                add(node, f'comparison: {o.__name__}',
                    lambda n, o=o: ast.Compare(left=n.left, ops=[o()], comparators=n.comparators))
        if node in tuples_in:
            elts = node.comparators[0].elts
            for i, e in enumerate(elts):
                if len(elts) > 1:
                    add(node, f'in: without {ast.unparse(e)}', lambda n, i=i: ast.Compare(
                        left=n.left, ops=n.ops, comparators=[ast.Tuple(
                            elts=[x for j, x in enumerate(n.comparators[0].elts) if j != i], ctx=ast.Load())]))
        if isinstance(node, ast.ExceptHandler):
            held = ast.unparse(node.type) if node.type else ''
            for kind in ('Exception', 'BaseException'):
                if held != kind:
                    add(node, f'except: {kind}',
                        lambda n, kind=kind: ast.ExceptHandler(type=expr(kind), name=n.name, body=n.body))
            add(node, 'except: re-raises', lambda n: ast.ExceptHandler(type=n.type, name=n.name, body=[ast.Raise()]))
        if (isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'isinstance'
                and isinstance(node.args[1], ast.Tuple)):
            for i, element in enumerate(node.args[1].elts):
                def without(n: ast.Call, i: int = i) -> ast.Call:
                    rest = [e for j, e in enumerate(n.args[1].elts) if j != i]
                    kinds = rest[0] if len(rest) == 1 else ast.Tuple(elts=rest, ctx=ast.Load())
                    return ast.Call(func=n.func, args=[n.args[0], kinds], keywords=[])
                add(node, f'isinstance: without {ast.unparse(element)}', without)
    # An element of one `in` tuple moved to another `in` tuple of the same scope.
    for a in tuples_in:
        for b in tuples_in:
            if a is b:
                continue
            for e in a.comparators[0].elts:
                text_a = text
                moved = ast.parse(text_a)
                ta = next(n for n in ast.walk(moved) if isinstance(n, ast.Compare)
                          and (n.lineno, n.col_offset) == (a.lineno, a.col_offset))
                tb = next(n for n in ast.walk(moved) if isinstance(n, ast.Compare)
                          and (n.lineno, n.col_offset) == (b.lineno, b.col_offset))
                ta.comparators[0].elts = [x for x in ta.comparators[0].elts if ast.dump(x) != ast.dump(e)]
                tb.comparators[0].elts.append(copy.deepcopy(e))
                found.append(Alternative(file, a.lineno, f'in: {ast.unparse(e)} moved to line {b.lineno}',
                                         settled(ast.fix_missing_locations(moved))))
    return found


def method(module: ast.Module, cls: str, name: str) -> ast.FunctionDef | None:
    klass = next((n for n in module.body if isinstance(n, ast.ClassDef) and n.name == cls), None)
    return next((n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == name), None) if klass else None


def function(module: ast.Module, name: str) -> ast.FunctionDef | None:
    return next((n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == name), None)


def placements(text: str) -> tuple[list[Alternative], list[str]]:
    """Each probe statement of run() at every other boundary of its body and of its try, and not at all."""
    found: list[Alternative] = []
    gaps: list[str] = []
    module = ast.parse(text)
    run = method(module, 'MCPServerApp', 'run')
    trying = next((s for s in run.body if isinstance(s, ast.Try)), None) if run else None
    if trying is None:
        return [], ['core/__init__.py: run() has no try to place the probe in']
    for word in PROBE_STATEMENTS:
        at = next((i for i, s in enumerate(trying.body) if word in ast.unparse(s)), None)
        if at is None:
            gaps.append(f'core/__init__.py: no statement of run()\'s try holds {word!r}')
            continue
        line = trying.body[at].lineno
        spots = [('try', p) for p in range(len(trying.body)) if p != at] + \
                [('body', p) for p in range(len(run.body) + 1)] + [(None, None)]
        for where, p in spots:
            mutated = ast.parse(text)
            mrun = method(mutated, 'MCPServerApp', 'run')
            mtry = next(s for s in mrun.body if isinstance(s, ast.Try))
            statement = mtry.body.pop(at)
            if where == 'try':
                mtry.body.insert(p, statement)
            elif where == 'body':
                mrun.body.insert(p, statement)
            what = f'run(): {word} ' + ('dropped' if where is None else f'before statement {p + 1} of its {where}')
            found.append(Alternative(CLI, line, what, settled(ast.fix_missing_locations(mutated))))
    return found, gaps


def applied(text: str, edits) -> str | None:
    for old, new in edits:
        if text.count(old) != 1:
            return None
        text = text.replace(old, new)
    return text


def alternatives(phase: str) -> tuple[list[Alternative], list[str]]:
    files = FILES[phase]
    found: list[Alternative] = []
    gaps: list[str] = []
    texts = {f: source(f) for f in files if (NAMESPACE / f).exists()}
    for f in files:
        if f not in texts:
            gaps.append(f'{f}: missing')
    if PROBES in texts:
        module = ast.parse(texts[PROBES])
        found += decisions(texts[PROBES], PROBES, [n for n in module.body])
    if LOADER in texts:
        module = ast.parse(texts[LOADER])
        checked = function(module, '_checked')
        loops = [n for n in ast.walk(checked) if isinstance(n, ast.For) and 'commands' in ast.unparse(n.iter)] if checked else []
        if not loops:
            gaps.append(f'{LOADER}: _checked has no loop over the declared commands')
        # The field's own check, outside the loop: an `if` on `value.commands` itself.
        fields = [n for n in checked.body if isinstance(n, ast.If) and 'value.commands' in ast.unparse(n.test)] if checked else []
        if not fields:
            gaps.append(f'{LOADER}: _checked does not type-check the commands field')
        found += decisions(texts[LOADER], LOADER, loops + fields)
    if CLI in texts:
        module = ast.parse(texts[CLI])
        scopes = [m for m in (method(module, 'MCPServerApp', n) for n in CLI_METHODS) if m]
        if len(scopes) != len(CLI_METHODS):
            gaps.append(f'{CLI}: expected the methods {CLI_METHODS}')
        found += decisions(texts[CLI], CLI, scopes)
        more, missing = placements(texts[CLI])
        found += more
        gaps += missing
    if DEPRECATION in texts:
        module = ast.parse(texts[DEPRECATION])
        resolver = function(module, 'env_setting')
        ifs = [n for n in ast.walk(resolver) if isinstance(n, ast.If) and 'None' in ast.unparse(n.test)] if resolver else []
        if not ifs:
            gaps.append(f'{DEPRECATION}: env_setting has no branch for a variable without a legacy name')
        found += decisions(texts[DEPRECATION], DEPRECATION, ifs)
    for when, what, f, edits in EXTRA:
        if f not in FILES[phase]:
            continue
        if f not in texts:
            continue
        text = applied(texts[f], edits)
        if text is None:
            gaps.append(f'{f}: the anchor of "{what}" is not in the file once')
            continue
        found.append(Alternative(f, texts[f][:texts[f].index(edits[0][0])].count('\n') + 1, what, tree(text)))
    own = {f: tree(t) for f, t in texts.items()}
    unique: dict[tuple[str, str], Alternative] = {}
    for alt in found:
        if alt.tree != own[alt.file]:
            unique.setdefault((alt.file, alt.tree), alt)
    return list(unique.values()), gaps


def case_trees(files: tuple[str, ...]) -> dict[str, tuple[str, str]]:
    texts = {f: source(f) for f in files if (NAMESPACE / f).exists()}
    out: dict[str, tuple[str, str]] = {}
    for case in mutants.CASES:
        if case.file in texts:
            text = applied(texts[case.file], case.edits)
            if text is not None:
                out[case.id] = (case.file, tree(text))
    for name, (edit, _) in EQUIVALENT.items():
        f = FILE_OF.get(name, PROBES)
        text = applied(texts[f], (edit,))
        if text is not None:
            out[f'{name} (equivalent)'] = (f, tree(text))
    return out


def row_set(target: str) -> str | None:
    params = target.rpartition('[')[2].rstrip(']') if target.endswith(']') else ''
    return next((s for s in SETS if params == s or params.endswith(f'-{s}')), None)


def coverage(phase: str) -> tuple[list[str], list[str]]:
    alts, gaps = alternatives(phase)
    by_tree: dict[tuple[str, str], list[str]] = {}
    for name, key in case_trees(FILES[phase]).items():
        by_tree.setdefault(key, []).append(name)
    swept: list[str] = []
    for alt in alts:
        names = by_tree.get((alt.file, alt.tree), [])
        if not names:
            gaps.append(f'{alt.file}:{alt.line}: {alt.what}: no mutant')
        swept += [n for n in names if not n.endswith('(equivalent)')]
    swept = list(dict.fromkeys(swept))
    known = {case.id: case for case in mutants.CASES}
    for name in swept:
        missing = [s for s in SETS if s not in {row_set(t) for t in known[name].targets}]
        missing = [s for s in missing if s not in (SET_EQUIVALENT.get(name, ((), (), ''))[0])]
        if missing:
            gaps.append(f'{name}: no target row beside {missing}')
    print(f'alternatives {phase}: {len(alts)} alternatives in {", ".join(FILES[phase])}; {len(swept)} cases, '
          f'{len(EQUIVALENT)} equivalents', file=sys.stderr)
    return swept, gaps


def era_env(era: str | None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ('CLUSTER_MCP_TEST_ERA', 'CLUSTER_MCP_SKIP_PROBES')}
    if era:
        env['CLUSTER_MCP_TEST_ERA'] = era
    return env


def run_cases(ids: list[str], eras: dict[str, str | None]) -> list[str]:
    bad: list[str] = []
    if not ids:
        return ['no case to run']
    for label, era in eras.items():
        result = subprocess.run([sys.executable, 'tests/mutants.py', '--self-check', *ids], env=era_env(era),
                                capture_output=True, text=True)
        killed = [line for line in result.stdout.splitlines() if line.startswith('killed ')]
        failed = [line for line in result.stdout.splitlines() if line.startswith('FAILED')]
        print(f'alternatives cases, {label} era: {len(killed)} of {len(ids)} killed, exit {result.returncode}',
              file=sys.stderr)
        bad += [f'{label} era: {line}' for line in failed]
        if result.returncode != 0 and not failed:
            bad.append(f'{label} era: the runner exited {result.returncode}: {result.stderr[-400:]}')
        if len(killed) != len(ids):
            bad.append(f'{label} era: {len(killed)} of {len(ids)} cases reported killed')
    return bad


def run_equivalents(eras: dict[str, str | None]) -> list[str]:
    bad: list[str] = []
    for name, (edit, _) in EQUIVALENT.items():
        case = mutants.Case(name, FILE_OF.get(name, PROBES), (edit,), EQUIVALENT_TARGETS, '')
        for label, era in eras.items():
            with tempfile.TemporaryDirectory(prefix=f'equivalent-{name}-') as scratch:
                src_root = mutants.apply(case, Path(scratch))
                saved = os.environ.copy()
                os.environ.clear()
                os.environ.update(era_env(era))
                try:
                    child = mutants.run_child(src_root, EQUIVALENT_TARGETS, Path(scratch) / 'junit.xml')
                finally:
                    os.environ.clear()
                    os.environ.update(saved)
            if child.returncode != 0:
                bad.append(f'{name}, {label} era: recorded as equivalent, but its targets fail')
    return bad


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    phase = sys.argv[2] if len(sys.argv) > 2 else 'p2'
    era = sys.argv[3] if len(sys.argv) > 3 else 'both'
    shard = sys.argv[4] if len(sys.argv) > 4 else '1/1'
    try:
        k, n = (int(x) for x in shard.split('/'))
    except ValueError:
        k, n = 0, 0
    if mode not in ('coverage', 'cases', 'equivalents', 'all') or phase not in FILES or \
            era not in ('both', *ERAS) or not 1 <= k <= n:
        raise SystemExit('usage: alternatives.py [coverage|cases|equivalents|all] [p1|p2|all] '
                         '[both|handshake|modern] [K/N]')
    eras = ERAS if era == 'both' else {era: ERAS[era]}
    swept, bad = coverage(phase)
    if mode in ('cases', 'all'):
        # Shard K of N: every Nth case from the Kth, in the sweep's order; the N shards together run each once.
        bad += run_cases(swept[k - 1::n], eras)
    if mode in ('equivalents', 'all'):
        bad += run_equivalents(eras)
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'alternatives: {mode} {phase} ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
