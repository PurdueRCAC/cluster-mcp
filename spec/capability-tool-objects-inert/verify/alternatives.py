# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Every decision the tool-object check adds to the load is mutated to every alternative it could
take, and every mutant is caught beside every member set, in both protocol eras.

    uv run python -I spec/capability-tool-objects-inert/verify/alternatives.py [coverage|cases|equivalents|all] [p1|all] [both|handshake|modern] [K/N]
                                                                            from the worktree root

Adapted from `spec/capability-probe/verify/alternatives.py` (the settled-tree comparison and the case
matching are that script's). At the plan's sign-off (2026-11-12, Q-E) the sweep is the narrow set, not
every node kind: the rule and family decisions, plus the node kinds the adversarial design review found
unswept in the depth walks. Found by parsing `core/capabilities.py` (`extra()`):

- each named rule of `TOOL_RULES` replaced by no check (`NAMED_RULES`);
- each default-rule field left to the generic rule, and the default rule replaced by no check
  (`DEFAULT_FIELDS`);
- the undecided warning for a field no rule names dropped, and given on every load;
- the fields walked from the rule table instead of the installed model;
- the type named through its own (metaclass's) `__name__`;
- the registry walk over only what this capability's load registered;
- each of `load()`'s decisions of the registry dropped (`DECISIONS_IN_LOAD`);
- in each depth walk (`DEPTH_WALKS`), the push that descends deleted, its `while` never entered, and its
  first answer but None turned to the other answer.

Every other alternative is graded at review from the diff sweep (the factory's mutation-testing method,
§ When a review is done).

An alternative is mutated when a case of `tests/mutants.py`, or an equivalent recorded below, turns
the file into the same syntax tree. `coverage` (seconds): every alternative mutated, and every such
case targets a row beside each member set (`mutants.MEMBER_SETS`) unless `SET_EQUIVALENT` says why
that set cannot observe it; any gap fails, naming it. `cases`: each such case run by
`tests/mutants.py --self-check` in the era given, killed. `equivalents`: each recorded equivalent
planted, `EQUIVALENT_TARGETS` passing in each era. K/N runs shard K of N of the cases.

Footprint: one mutant child at a time, under 1 GB; `coverage` seconds; `cases` about 3 s a case per
era (three loader cases measured at 9 s handshake and 8 s modern at the plan, 2026-11-12): 34 cases,
about 2 min an era.
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
LOADER = 'core/capabilities.py'
FILES = {'p1': (LOADER,), 'all': (LOADER,)}
ERAS = {'handshake': None, 'modern': 'modern'}
SETS = tuple(mutants.MEMBER_SETS)

# The table of field rules; the fields it names; the fields it gives the default rule; a rule that checks
# nothing (what a mutant puts in a rule's place); the warning for a field no rule names.
RULES, NO_CHECK, WARN = 'TOOL_RULES', 'lambda value, info: None', '_undecided'
NAMED_RULES = ('name', 'description', 'parameters', 'output_schema', 'return_type', 'fn')
DEFAULT_FIELDS = ('version', 'title', 'icons', 'tags', 'meta', 'task_config', 'annotations', 'execution', 'auth',
                  'timeout', 'run_in_thread')
# How many times load() decides the registry: after its tools module's import, and after its resources
# are assembled (PLAN.md § 2).
DECISIONS_IN_LOAD = 2
# The depth walks, each with the push by which it descends (PLAN.md § 5, Q-E).
DEPTH_WALKS = {'_json_violation': 'stack.extend(node.values())', '_same': 'stack.extend(zip(a, b))',
               '_return_type_violation': 'stack.extend(args)'}

# Mutants that change no behaviour, each with why; filled by build as it finds them: name -> ((old,
# new), why), planted in LOADER.
EQUIVALENT: dict[str, tuple[tuple[str, str], str]] = {}
FILE_OF: dict[str, str] = {}
EQUIVALENT_TARGETS = ('test_capabilities.py', 'test_startup.py', 'test_registry.py', 'test_surface.py')
SET_EQUIVALENT: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {}


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


def applied(text: str, edits) -> str | None:
    for old, new in edits:
        if text.count(old) != 1:
            return None
        text = text.replace(old, new)
    return text


def _assigned(module: ast.Module, name: str) -> ast.AST | None:
    for node in module.body:
        targets = [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, 'targets', [])
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            return node.value
    return None


def _at(t: ast.Module, scope: str, kind: type, key: tuple) -> ast.AST:
    return next(n for n in ast.walk(function(t, scope)) if isinstance(n, kind) and (n.lineno, n.col_offset) == key)


def _without(t: ast.Module, scope: str, key: tuple) -> None:
    """Delete the statement at `key` from `scope`, leaving `pass` where a body would empty."""
    for parent in ast.walk(function(t, scope)):
        for field in ('body', 'orelse', 'finalbody'):
            body = getattr(parent, field, None)
            if isinstance(body, list) and body and isinstance(body[0], ast.stmt):
                kept = [s for s in body if (s.lineno, s.col_offset) != key]
                if len(kept) != len(body):
                    setattr(parent, field, kept or [ast.Pass()])


def extra(text: str) -> tuple[list[Alternative], list[str]]:
    """The narrow set (`NARROW`, PLAN.md § 5 Q-E), each found by parsing (so a reformatted line is
    still found, and a missing one is a gap)."""
    found: list[Alternative] = []
    gaps: list[str] = []
    module = ast.parse(text)

    def mutated(what: str, line: int, change) -> None:
        tree_ = ast.parse(text)
        change(tree_)
        found.append(Alternative(LOADER, line, what, settled(ast.fix_missing_locations(tree_))))

    rules = _assigned(module, RULES)
    if not isinstance(rules, ast.Dict):
        return found, [f'{LOADER}: {RULES} is not a dict literal']
    named = [k.value for k in rules.keys if isinstance(k, ast.Constant)]
    if sorted(named) != sorted(NAMED_RULES):
        gaps.append(f'{LOADER}: {RULES} names {sorted(named)}, not {sorted(NAMED_RULES)}')
    for i, (key, value) in enumerate(zip(rules.keys, rules.values)):
        if isinstance(key, ast.Constant):
            def unchecked(t: ast.Module, i: int = i) -> None:
                _assigned(t, RULES).values[i] = expr(NO_CHECK)
            mutated(f'{RULES}: {key.value} unchecked', key.lineno, unchecked)
        elif key is None and isinstance(value, ast.DictComp):
            elts = value.generators[0].iter.elts if isinstance(value.generators[0].iter, ast.Tuple) else []
            if sorted(e.value for e in elts) != sorted(DEFAULT_FIELDS):
                gaps.append(f'{LOADER}: the default-rule fields are not {sorted(DEFAULT_FIELDS)}')
            for j, e in enumerate(elts):
                def generic(t: ast.Module, i: int = i, j: int = j) -> None:
                    del _assigned(t, RULES).values[i].generators[0].iter.elts[j]
                mutated(f'{RULES}: {e.value} left to the generic rule', e.lineno, generic)

            def none(t: ast.Module, i: int = i) -> None:
                _assigned(t, RULES).values[i].value = expr(NO_CHECK)
            mutated(f'{RULES}: the default-rule fields unchecked', value.lineno, none)
    check = function(module, '_tool_violation')
    if check is None:
        return found, gaps + [f'{LOADER}: no _tool_violation']
    warns = [n for n in ast.walk(check) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
             and getattr(n.value.func, 'id', None) == WARN]
    if len(warns) != 1:
        gaps.append(f'{LOADER}: _tool_violation does not call {WARN}(field) once')
    else:
        key = (warns[0].lineno, warns[0].col_offset)
        mutated('a field no rule names served undecided with no warning', warns[0].lineno,
                lambda t, key=key: _without(t, '_tool_violation', key))
    warner = function(module, WARN)
    ifs = [n for n in warner.body if isinstance(n, ast.If)] if warner else []
    if not ifs:
        gaps.append(f'{LOADER}: {WARN} has no warned-once check')
    else:
        key = (ifs[0].lineno, ifs[0].col_offset)

        def every_time(t: ast.Module, key: tuple = key) -> None:
            _at(t, WARN, ast.If, key).test = ast.Constant(False)
        mutated('a field no rule names warned on every load', ifs[0].lineno, every_time)
    loops = [n for n in ast.walk(check) if isinstance(n, ast.For) and ast.unparse(n.iter).endswith('.items()')
             and any(isinstance(m, ast.Attribute) and m.attr == 'get' and ast.unparse(m.value) == RULES
                     for m in ast.walk(n))]
    if len(loops) != 1:
        gaps.append(f'{LOADER}: _tool_violation has no one loop over the installed model\'s fields')
    else:
        key = (loops[0].lineno, loops[0].col_offset)

        def from_table(t: ast.Module) -> None:
            loop = _at(t, '_tool_violation', ast.For, key)
            fields = loop.iter.func.value
            loop.iter = expr(f'((f, {ast.unparse(fields)}[f]) for f in {RULES} if f in {ast.unparse(fields)})')
        mutated("the fields walked from the rule table, not the installed model", loops[0].lineno, from_table)
    namer = function(module, '_type_name')
    if namer is None or not namer.args.args:
        gaps.append(f'{LOADER}: no _type_name(kind)')
    else:
        arg = namer.args.args[0].arg

        def own_name(t: ast.Module) -> None:
            function(t, '_type_name').body = [ast.parse(f'return {arg}.__name__').body[0]]
        mutated("a type named through its own __name__", namer.lineno, own_name)
    registry = function(module, '_registry_violation')
    entries = [n for n in ast.walk(registry) if isinstance(n, ast.For) and 'TOOL_REGISTRY' in ast.unparse(n.iter)
               and '_tool_violation' in ast.unparse(n)] if registry else []
    if len(entries) != 1:
        gaps.append(f'{LOADER}: _registry_violation has no one loop handing registry entries to _tool_violation')
    else:
        key = (entries[0].lineno, entries[0].col_offset)

        def only_new(t: ast.Module) -> None:
            loop = _at(t, '_registry_violation', ast.For, key)
            for n in list(ast.walk(loop.iter)):
                for field, value in ast.iter_fields(n):
                    if isinstance(value, ast.Name) and value.id == 'TOOL_REGISTRY':
                        setattr(n, field, expr('TOOL_REGISTRY[before:]'))
                    elif isinstance(value, list):
                        setattr(n, field, [expr('TOOL_REGISTRY[before:]') if isinstance(v, ast.Name)
                                           and v.id == 'TOOL_REGISTRY' else v for v in value])
        mutated('only what this capability\'s load registered is decided', entries[0].lineno, only_new)
    load = function(module, 'load')
    sites = [n for n in ast.walk(load) if isinstance(n, ast.If) and '_registry_violation' in ast.unparse(n.test)] if load else []
    if len(sites) != DECISIONS_IN_LOAD:
        gaps.append(f'{LOADER}: load() decides the registry {len(sites)} times, not {DECISIONS_IN_LOAD}')
    for site in sites:
        key = (site.lineno, site.col_offset)
        mutated(f'load(): the registry not decided at line {site.lineno}', site.lineno,
                lambda t, key=key: _without(t, 'load', key))
    # In each depth walk: the push that descends deleted, the walk's loop never entered, and its first
    # returned answer but None turned to the other answer.
    for name, push in DEPTH_WALKS.items():
        walk = function(module, name)
        if walk is None:
            gaps.append(f'{LOADER}: no depth walk {name}')
            continue
        pushes = [n for n in ast.walk(walk) if isinstance(n, ast.Expr) and ast.unparse(n) == push]
        if len(pushes) != 1:
            gaps.append(f'{LOADER}: {name} does not hold {push} once')
        else:
            key = (pushes[0].lineno, pushes[0].col_offset)
            mutated(f'{name}: {push} dropped', pushes[0].lineno, lambda t, key=key, name=name: _without(t, name, key))
        loops = [n for n in ast.walk(walk) if isinstance(n, ast.While)]
        if len(loops) != 1:
            gaps.append(f'{LOADER}: {name} has no one while loop')
        else:
            key = (loops[0].lineno, loops[0].col_offset)

            def never(t: ast.Module, key: tuple = key, name: str = name) -> None:
                _at(t, name, ast.While, key).test = ast.Constant(False)
            mutated(f'{name}: its while loop never runs', loops[0].lineno, never)
        answers = sorted((n for n in ast.walk(walk) if isinstance(n, ast.Return) and n.value is not None
                          and not (isinstance(n.value, ast.Constant) and n.value.value is None)),
                         key=lambda n: (n.lineno, n.col_offset))
        if not answers:
            gaps.append(f'{LOADER}: {name} returns no answer but None')
        else:
            first = answers[0]
            key = (first.lineno, first.col_offset)
            other = ast.Constant(True) if isinstance(first.value, ast.Constant) and first.value.value is False \
                else ast.Constant(False) if isinstance(first.value, ast.Constant) and first.value.value is True \
                else ast.Constant(None)

            def answered(t: ast.Module, key: tuple = key, name: str = name, other: ast.AST = other) -> None:
                _at(t, name, ast.Return, key).value = copy.deepcopy(other)
            mutated(f'{name}: line {first.lineno} returns {ast.unparse(other)}', first.lineno, answered)
    return found, gaps


def alternatives(phase: str) -> tuple[list[Alternative], list[str]]:
    if not (NAMESPACE / LOADER).exists():
        return [], [f'{LOADER}: missing']
    text = source(LOADER)
    found, gaps = extra(text)
    own = tree(text)
    unique: dict[tuple[str, str], Alternative] = {}
    for alt in found:
        if alt.tree == own:
            gaps.append(f'{alt.file}:{alt.line}: {alt.what}: changes nothing')
        else:
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
        f = FILE_OF.get(name, LOADER)
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
        case = mutants.Case(name, FILE_OF.get(name, LOADER), (edit,), EQUIVALENT_TARGETS, '')
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
    phase = sys.argv[2] if len(sys.argv) > 2 else 'p1'
    era = sys.argv[3] if len(sys.argv) > 3 else 'both'
    shard = sys.argv[4] if len(sys.argv) > 4 else '1/1'
    try:
        k, n = (int(x) for x in shard.split('/'))
    except ValueError:
        k, n = 0, 0
    if mode not in ('coverage', 'cases', 'equivalents', 'all') or phase not in FILES or \
            era not in ('both', *ERAS) or not 1 <= k <= n:
        raise SystemExit('usage: alternatives.py [coverage|cases|equivalents|all] [p1|all] '
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
