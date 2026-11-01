# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Review cycle 2, F4 (checker F7: checker ids number on across cycles, so cycle 2's F1-F4 are F4-F7):
every decision of the capability load is mutated to every alternative it could take, and every mutant
is caught under every capability set, in both protocol eras.

    uv run python -I spec/capability-extras/remediation/F7-mutant-alternatives.py [coverage|cases|equivalents|all]
                                                                              from the worktree root

It supersedes `F2-mutant-sweep.py` (review cycle 1), which stays as that cycle's record and is no
longer run: F2 required a mutant on every decision's line, and one mutant per line let each decision's
sibling alternatives survive (cycle 2's F4). Every decision F2 found has its alternatives here, so its
line coverage is implied; its equivalents are carried over below, but the one a test now kills.

The decisions, found by parsing the files, and the alternatives each could take:

- `core/capabilities.py`, every decision: each `if`, conditional expression and comprehension
  condition, to always, never and its negation; each boolean operator to each of its operands alone
  and to the other operator; each comparison not the whole of a condition to its negation (an
  ordering comparison to each other ordering); each `except` clause to `Exception`, to
  `BaseException`, and to a body that re-raises (the clause dropped); each `isinstance` over a tuple
  of types to the tuple without each one; each sort key to every key of one or two of its domain's
  fields (`KEY_DOMAINS`) other than its own, to no sort at all and to the reverse order; and the
  decisions no node kind names (`EXTRA`): what `installed()` caches when a load fails, and where a
  capability's registrations begin to be checked.
- `core/__init__.py`: where `run()` loads the capabilities, at every other boundary between the
  statements of its body and of the `try` in it, and not at all; and `_load_capabilities`'s `except`.
- `core/tools/__init__.py`: the partition between the core tools that open the listing and those that
  close it, at every other index of `CORE_TOOLS` (0 to 7), at every other place among the tool-module
  imports, and with the halves exchanged.

An alternative is mutated when a case of `tests/mutants.py`, or an equivalent mutant recorded below,
turns the file into the same syntax tree.

`coverage` (seconds): every alternative above mutated; every case that mutates one targets a row beside each member set (core only, slurm, rcac, both) unless
`SET_EQUIVALENT` records why that set cannot observe it. Any gap fails, naming it.

`cases` (about 25 min): every such case, run by `tests/mutants.py` (with its controls) in the handshake
era, then in revision 2026-07-28's; each must be killed, every target failing with its `why`.

`equivalents` (about 8 min): each equivalent mutant is planted and `EQUIVALENT_TARGETS` runs against
it in each era, and each set-equivalent case's rows for that set, which must pass: that is what
recording them claims. The CLI drives among them run over every kind (`CLUSTER_MCP_TEST_EVERY_KIND`,
which the suite never sets). One that fails is no longer equivalent and needs a case.

`all` (the default) runs the three. Footprint: one mutant child at a time, under 1 GB.
"""

from __future__ import annotations

import ast
import copy
import itertools
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
LOADER, CLI, TOOLS = 'core/capabilities.py', 'core/__init__.py', 'core/tools/__init__.py'
ERAS = {'handshake': None, 'modern': 'modern'}
SETS = ('core-only', 'slurm', 'rcac', 'both')

# The fields each sort key may be built from: the load's order of entry points, and the composition's
# order of loaded capabilities.
KEY_DOMAINS = {
    'each': ('each.distribution', 'each.ep.name', 'each.ep.value'),
    'c': ('c.capability.order', 'c.distribution', 'c.capability.name', 'c.capability.tools'),
}

INSTALLED = ('    if _installed is None:\n'
             '        _installed = load()\n'
             '    return _installed\n')
CHECKED_FROM = ('            before = len(TOOL_REGISTRY)\n'
                '            try:\n'
                '                capability = _checked(ep.load())\n'
                '            except _Invalid as exc:\n'
                '                raise CapabilityLoadError(distribution, str(exc)) from exc\n'
                '            import_module(capability.tools)\n')

# Decisions no node kind names, each alternative as (label, file, ((old, new), ...)).
EXTRA = (
    ('installed() caches a failed load as no capability', LOADER,
     ((INSTALLED, '    if _installed is None:\n'
                  '        try:\n'
                  '            _installed = load()\n'
                  '        except CapabilityLoadError:\n'
                  '            _installed = ()\n'
                  '            raise\n'
                  '    return _installed\n'),)),
    ('installed() caches a failed load as its error, raised again', LOADER,
     ((INSTALLED, '    if _installed is None:\n'
                  '        try:\n'
                  '            _installed = load()\n'
                  '        except CapabilityLoadError as exc:\n'
                  '            _installed = exc\n'
                  '    if isinstance(_installed, CapabilityLoadError):\n'
                  '        raise _installed\n'
                  '    return _installed\n'),)),
    ('registrations checked from after the entry point loads', LOADER,
     ((CHECKED_FROM, CHECKED_FROM.replace('            before = len(TOOL_REGISTRY)\n', '').replace(
         '            import_module(capability.tools)\n',
         '            before = len(TOOL_REGISTRY)\n            import_module(capability.tools)\n')),)),
    ('registrations checked from after the tools module is imported', LOADER,
     ((CHECKED_FROM, CHECKED_FROM.replace('            before = len(TOOL_REGISTRY)\n', '').replace(
         '            import_module(capability.tools)\n',
         '            import_module(capability.tools)\n            before = len(TOOL_REGISTRY)\n')),)),
)

# Mutants that change no behaviour, each with why. `edit` is (old, new), as a case's. The first two are
# F2's; F2's other two are killed now, so they are cases: `installed()` uncached (the cache is pinned,
# `test_a_failed_load_is_not_cached` counts the discoveries) and the tool assembly dropped (a tool of a
# capability's own class runs its code when FastMCP reads it, `...-at-served-tool`).
EQUIVALENT = {
    'capability-scratch-without-core-tools': (
        ('    serve(server, CORE_TOOLS, RESOURCE_REGISTRY)\n', '    serve(server, (), RESOURCE_REGISTRY)\n'),
        'A capability tool named as a core tool is refused by the core-name check before the assembly, '
        'so the scratch server never meets a tool that would collide with a core one.'),
    'capability-listing-duplicates-unchecked': (
        ('    if sorted(listed) == sorted(names) and len(set(listed)) == len(listed):\n',
         '    if sorted(listed) == sorted(names):\n'),
        'The tool names are distinct by then (the duplicate-tool refusals run first), so a text whose '
        'sorted names equal them lists none twice.'),
    'capability-metadata-unreadable-base-exception': (
        ("    except Exception as exc:\n        return ep.value, f'its distribution metadata cannot be read: {_cause(exc)}'\n",
         "    except BaseException as exc:\n        return ep.value, f'its distribution metadata cannot be read: {_cause(exc)}'\n"),
        "Reading a distribution's metadata runs no capability's code: it reads and parses a file, and "
        'raises nothing but an Exception.'),
    'capability-named-metadata-base-exception': (
        ('    except Exception:\n        name = None\n', '    except BaseException:\n        name = None\n'),
        "As above: reading a distribution's metadata raises nothing but an Exception."),
    'capability-discovery-base-exception': (
        ('    except Exception as exc:\n        unreadable = exc\n', '    except BaseException as exc:\n        unreadable = exc\n'),
        'Discovering the group reads every distribution\'s entry points and runs no capability\'s code: it '
        'raises nothing but an Exception.'),
    'capability-entry-points-unreadable-base-exception': (
        ('        except Exception as exc:\n            raise CapabilityLoadError(_named(dist), ',
         '        except BaseException as exc:\n            raise CapabilityLoadError(_named(dist), '),
        "As above, for one distribution's entry points."),
    'capability-listing-twice-not-once': (
        ('    twice = sorted({n for n in listed if listed.count(n) > 1})\n',
         '    twice = sorted({n for n in listed if listed.count(n) != 1})\n'),
        'Each name it counts is drawn from the list it counts in, so its count is at least 1: `!= 1` and `> 1` '
        'select the same names.'),
    'capability-cli-catches-every-exception': (
        ('        except CapabilityLoadError as exc:\n            message = str(exc)\n',
         '        except Exception as exc:\n            message = str(exc)\n'),
        'The load raises a CapabilityLoadError or a KeyboardInterrupt, which is not an Exception: whatever '
        'else a capability raises or exits with becomes the former.'),
}
EQUIVALENT_FILES = {'capability-cli-catches-every-exception': CLI}

# What an equivalent mutant must pass: every test of the loader, the composed surface and the startup.
EQUIVALENT_TARGETS = (
    'test_capabilities.py', 'test_instructions.py', 'test_registry.py', 'test_surface.py', 'test_storage_resource.py',
    'test_startup.py::test_a_broken_capability_stops_startup',
    'test_startup.py::test_capabilities_load_before_the_mode_ladder',
    'test_startup.py::test_http_load_failure_exits_before_binding',
    'test_startup.py::test_a_contribution_the_server_would_refuse_stops_startup',
    'test_startup.py::test_a_keyboard_interrupt_while_loading_interrupts_the_start_beside_every_set',
    'test_startup.py::test_a_capability_that_cannot_load_stops_startup',
                      'test_startup.py::test_a_keyboard_interrupt_while_loading_still_interrupts_the_start',
                      'test_startup.py::test_a_token_is_generated_before_any_capability_loads',
                      'test_startup.py::test_capabilities_load_before_the_mode_ladder_beside_every_set')

# Cases some member sets cannot observe: the sets, the rows of those sets that must pass under the case,
# and why.
LISTING = 'test_capabilities.py::test_the_listing_opens_and_closes_with_the_core_tools_by_name'
SERVED = 'test_capabilities.py::test_served_tools_are_the_core_and_the_given_capabilities'
PARTITION_UNOBSERVABLE = (
    ('core-only',), (f'{LISTING}[core-only]', f'{SERVED}[core-only]'),
    'With the core alone the listing is every core tool in registration order, wherever the partition '
    'falls: the opening tools, then the closing ones.')
CACHED = 'test_capabilities.py::test_a_failed_load_is_not_cached'
RELOAD_UNOBSERVABLE = (
    ('slurm', 'rcac', 'both'), tuple(f'{CACHED}[{s}]' for s in ('slurm', 'rcac', 'both')),
    'It loads again only when the cached load found no capability, so beside a member the cache holds '
    'and nothing differs; with the core alone every call discovers the group again.')


@dataclass(frozen=True)
class Alternative:
    """One alternative of one decision: where, what, and the syntax tree of the file it gives."""

    file: str
    line: int
    what: str
    tree: str


class _Settled(ast.NodeTransformer):
    """A tree with every decided `if` settled: `if False:` without `else` and a bare `pass` are no
    statement, `if True:` is its body, and `a if True else b` is `a` (`b` for False). So a case that
    deletes a check matches the alternative "never", and one that keeps only its body "always"."""

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
                settled: list[ast.stmt] = []
                for s in statements:
                    if isinstance(s, ast.Pass):
                        continue
                    if isinstance(s, ast.If) and isinstance(s.test, ast.Constant) and s.test.value in (True, False):
                        settled.extend(s.body if s.test.value else s.orelse)
                        continue
                    settled.append(s)
                setattr(node, field, settled)
        return node


def settled(module: ast.AST) -> str:
    return ast.dump(_Settled().visit(module))


def tree(text: str) -> str:
    return settled(ast.parse(text))


def source(file: str) -> str:
    return (NAMESPACE / file).read_text()


class _At(ast.NodeTransformer):
    """Replace the node at a position, found by its kind, line and column, with what `make` returns."""

    def __init__(self, target: ast.AST, make) -> None:
        self.key = (type(target), target.lineno, target.col_offset, getattr(target, 'end_col_offset', None))
        self.make = make

    def visit(self, node: ast.AST):
        if (type(node), getattr(node, 'lineno', None), getattr(node, 'col_offset', None),
                getattr(node, 'end_col_offset', None)) == self.key:
            return self.make(copy.deepcopy(node))
        return self.generic_visit(node)


def replaced(text: str, target: ast.AST, make) -> str:
    module = _At(target, make).visit(ast.parse(text))
    return settled(ast.fix_missing_locations(module))


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


def conditions(module: ast.Module) -> set[int]:
    """The ids of the nodes that are a whole condition (of an `if`, a conditional expression or a
    comprehension): their own alternatives already cover a comparison there."""
    whole: set[int] = set()
    for node in ast.walk(module):
        if isinstance(node, (ast.If, ast.IfExp)):
            whole.add(id(node.test))
        elif isinstance(node, ast.comprehension):
            whole.update(id(c) for c in node.ifs)
    return whole


def loader_alternatives(text: str) -> list[Alternative]:
    module = ast.parse(text)
    whole = conditions(module)
    found: list[Alternative] = []

    def add(node: ast.AST, what: str, make) -> None:
        found.append(Alternative(LOADER, node.lineno, what, replaced(text, node, make)))

    def condition(node: ast.expr, kind: str) -> None:
        add(node, f'{kind}: always', lambda n: ast.Constant(True))
        add(node, f'{kind}: never', lambda n: ast.Constant(False))
        add(node, f'{kind}: negated', negation)

    for node in ast.walk(module):
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
            add(node, 'boolean operator: the other operator', lambda n, other=other: ast.BoolOp(op=other(), values=n.values))
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            op = type(node.ops[0])
            others = [o for o in ORDERING if o is not op] if op in ORDERING[:4] else [NEGATED[op]]
            if id(node) in whole:
                others = [o for o in others if o is not NEGATED.get(op, OPPOSITE.get(op))]
            for o in others:
                add(node, f'comparison: {o.__name__}', lambda n, o=o: ast.Compare(left=n.left, ops=[o()], comparators=n.comparators))
        if isinstance(node, ast.ExceptHandler):
            held = ast.unparse(node.type) if node.type else ''
            for kind in ('Exception', 'BaseException'):
                if held != kind:
                    add(node, f'except: {kind}', lambda n, kind=kind: ast.ExceptHandler(type=expr(kind), name=n.name, body=n.body))
            add(node, 'except: re-raises', lambda n: ast.ExceptHandler(type=n.type, name=n.name, body=[ast.Raise()]))
        if (isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'isinstance'
                and isinstance(node.args[1], ast.Tuple)):
            for i, element in enumerate(node.args[1].elts):
                def without(n: ast.Call, i: int = i) -> ast.Call:
                    rest = [e for j, e in enumerate(n.args[1].elts) if j != i]
                    kinds = rest[0] if len(rest) == 1 else ast.Tuple(elts=rest, ctx=ast.Load())
                    return ast.Call(func=n.func, args=[n.args[0], kinds], keywords=[])
                add(node, f'isinstance: without {ast.unparse(element)}', without)
        if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'sorted' and node.keywords:
            key = next(k for k in node.keywords if k.arg == 'key')
            var = key.value.args.args[0].arg
            own = ast.unparse(key.value.body)
            fields = KEY_DOMAINS[var]
            for size in (1, 2):
                for chosen in itertools.permutations(fields, size):
                    body = chosen[0] if size == 1 else f'({", ".join(chosen)})'
                    if ast.unparse(expr(body)) == own:
                        continue
                    add(node, f'sort key: {body}', lambda n, body=body, var=var: ast.Call(
                        func=n.func, args=n.args, keywords=[ast.keyword(arg='key', value=expr(f'lambda {var}: {body}'))]))
            add(node, 'sort: none, the given order', lambda n: n.args[0])
            add(node, 'sort: reversed', lambda n: ast.Call(func=n.func, args=n.args, keywords=[
                *n.keywords, ast.keyword(arg='reverse', value=ast.Constant(True))]))
    for what, file, edits in EXTRA:
        if file == LOADER:
            found.append(Alternative(LOADER, first_line(text, edits[0][0]), what, tree(applied(text, edits))))
    return found


def first_line(text: str, old: str) -> int:
    return text[:text.index(old)].count('\n') + 1


def applied(text: str, edits) -> str:
    for old, new in edits:
        if text.count(old) != 1:
            raise SystemExit(f'F7: an anchor occurs {text.count(old)} times: {old[:70]!r}')
        text = text.replace(old, new)
    return text


def method(module: ast.Module, cls: str, name: str) -> ast.FunctionDef:
    klass = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == cls)
    return next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == name)


def cli_alternatives(text: str) -> list[Alternative]:
    found: list[Alternative] = []
    module = ast.parse(text)
    run = method(module, 'MCPServerApp', 'run')
    load = next(i for i, s in enumerate(run.body) if isinstance(s, ast.Expr) and '_load_capabilities' in ast.unparse(s))
    rest = [s for i, s in enumerate(run.body) if i != load]
    trying = next(s for s in rest if isinstance(s, ast.Try))
    placements = [(f'run(): the load before statement {p + 1} of its body' if p < len(rest) else
                   'run(): the load at the end of its body', 'body', p) for p in range(len(rest) + 1) if p != load]
    placements += [(f'run(): the load before statement {p + 1} of its try' if p < len(trying.body) else
                    'run(): the load at the end of its try', 'try', p) for p in range(len(trying.body) + 1)]
    placements.append(('run(): no load', None, None))
    for what, where, p in placements:
        mutated = ast.parse(text)
        mrun = method(mutated, 'MCPServerApp', 'run')
        statement = mrun.body.pop(load)
        if where == 'body':
            mrun.body.insert(p, statement)
        elif where == 'try':
            next(s for s in mrun.body if isinstance(s, ast.Try)).body.insert(p, statement)
        found.append(Alternative(CLI, run.body[load].lineno, what, settled(mutated)))
    loading = method(module, 'MCPServerApp', '_load_capabilities')
    handler = next(n for n in ast.walk(loading) if isinstance(n, ast.ExceptHandler))
    for kind in ('Exception', 'BaseException'):
        found.append(Alternative(CLI, handler.lineno, f'_load_capabilities: except {kind}', replaced(
            text, handler, lambda n, kind=kind: ast.ExceptHandler(type=expr(kind), name=n.name, body=n.body))))
    found.append(Alternative(CLI, handler.lineno, '_load_capabilities: except re-raises', replaced(
        text, handler, lambda n: ast.ExceptHandler(type=n.type, name=n.name, body=[ast.Raise()]))))
    return found


def tools_alternatives(text: str) -> list[Alternative]:
    found: list[Alternative] = []
    module = ast.parse(text)
    body = module.body
    at = next(i for i, s in enumerate(body) if isinstance(s, ast.Assign) and ast.unparse(s.targets[0]) == '_OPENING')
    imports = [i for i, s in enumerate(body) if isinstance(s, ast.ImportFrom) and s.module == 'cluster_mcp.core.tools']
    line = body[at].lineno
    for p in range(imports[0], imports[-1] + 2):
        if p in (at, at + 1):
            continue
        mutated = ast.parse(text)
        statement = mutated.body.pop(at)
        mutated.body.insert(p if p < at else p - 1, statement)
        found.append(Alternative(TOOLS, line, f'partition: taken before statement {p + 1}', settled(mutated)))
    for index in range(8):
        if index == 6:
            continue
        offset = index - 6
        value = f'len(TOOL_REGISTRY) {"+" if offset > 0 else "-"} {abs(offset)}'
        found.append(Alternative(TOOLS, line, f'partition: at index {index}', replaced(
            text, body[at], lambda n, value=value: ast.Assign(targets=n.targets, value=expr(value)))))
    closing = next(s for s in body if isinstance(s, ast.AnnAssign) and ast.unparse(s.target) == 'CLOSING_TOOLS')
    found.append(Alternative(TOOLS, closing.lineno, 'partition: the halves exchanged', replaced(
        text, closing, lambda n: ast.AnnAssign(target=n.target, annotation=n.annotation,
                                               value=expr('CORE_TOOLS[:_OPENING]'), simple=n.simple))))
    return found


def alternatives() -> list[Alternative]:
    """Every alternative, once per distinct tree, none the file as it is."""
    found: dict[tuple[str, str], Alternative] = {}
    own = {file: tree(source(file)) for file in (LOADER, CLI, TOOLS)}
    for alt in (*loader_alternatives(source(LOADER)), *cli_alternatives(source(CLI)), *tools_alternatives(source(TOOLS))):
        if alt.tree != own[alt.file]:
            found.setdefault((alt.file, alt.tree), alt)
    return list(found.values())


def case_trees() -> dict[str, tuple[str, str]]:
    """Every case planting into the three files, and every equivalent: its file and the tree it gives."""
    texts = {file: source(file) for file in (LOADER, CLI, TOOLS)}
    out: dict[str, tuple[str, str]] = {}
    for case in mutants.CASES:
        if case.file in texts:
            out[case.id] = (case.file, tree(applied(texts[case.file], case.edits)))
    for name, (edit, _) in EQUIVALENT.items():
        file = EQUIVALENT_FILES.get(name, LOADER)
        out[f'{name} (equivalent)'] = (file, tree(applied(texts[file], (edit,))))
    return out


def row_set(target: str) -> str | None:
    """The member set a test row runs beside, read off its parameters; None for a row of no set."""
    params = target.rpartition('[')[2].rstrip(']') if target.endswith(']') else ''
    return next((s for s in SETS if params == s or params.endswith(f'-{s}')), None)


def sweep() -> tuple[dict[Alternative, list[str]], list[str]]:
    """Each alternative with the cases (or equivalents) that mutate it, and every gap."""
    trees = case_trees()
    by_tree: dict[tuple[str, str], list[str]] = {}
    for name, key in trees.items():
        by_tree.setdefault(key, []).append(name)
    mapping = {alt: by_tree.get((alt.file, alt.tree), []) for alt in alternatives()}
    gaps = [f'{alt.file}:{alt.line}: {alt.what}: no mutant' for alt, names in mapping.items() if not names]
    known = {case.id: case for case in mutants.CASES}
    for name in swept_cases(mapping):
        if name in NOT_DECISIONS:
            continue
        case = known[name]
        missing = [s for s in SETS if s not in {row_set(t) for t in case.targets}]
        excused = set(SET_EQUIVALENT[name][0]) if name in SET_EQUIVALENT else set()
        missing = [s for s in missing if s not in excused]
        if missing:
            gaps.append(f'{name}: no target row beside {missing}')
    return mapping, gaps


def swept_cases(mapping: dict[Alternative, list[str]]) -> list[str]:
    """The cases this sweep runs: every case planting into the loader, and every case on the other two
    files that mutates one of their alternatives."""
    named = {n for names in mapping.values() for n in names if not n.endswith('(equivalent)')}
    loader = [case.id for case in mutants.CASES if case.file == LOADER]
    return list(dict.fromkeys([*loader, *(case.id for case in mutants.CASES if case.id in named)]))


# Each partition case, with the core-only rows that must pass under it, and why.
SET_EQUIVALENT: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    **{case.id: PARTITION_UNOBSERVABLE for case in mutants.CASES
       if case.id.startswith('capability-partition-') and case.id != 'capability-partition-halves-exchanged'},
    'capability-installed-reloads-when-empty': RELOAD_UNOBSERVABLE}

# Cases planting into the loader that mutate no decision of it, so need no row beside each set, and why.
NOT_DECISIONS = {
    'title-at-add-tool': 'It gives every served tool a title where `serve()` adds each one: a contract of the served '
                         'surface, pinned against the whole surface (every capability installed), not a decision of '
                         'the load.',
}


def coverage() -> tuple[dict[Alternative, list[str]], list[str]]:
    mapping, gaps = sweep()
    print(f'F7 coverage: {len(mapping)} alternatives of the decisions in {LOADER}, {CLI} (the load\'s '
          f'placement) and {TOOLS} (the partition); {len(swept_cases(mapping))} cases, {len(EQUIVALENT)} '
          f'equivalents', file=sys.stderr)
    for alt, names in mapping.items():
        print(f'  {alt.file}:{alt.line:<4} {alt.what:64} {", ".join(names) or "-"}', file=sys.stderr)
    return mapping, gaps


def era_env(era: str | None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != 'CLUSTER_MCP_TEST_ERA'}
    if era:
        env['CLUSTER_MCP_TEST_ERA'] = era
    return env


def run_cases(ids: list[str]) -> list[str]:
    bad: list[str] = []
    for label, era in ERAS.items():
        result = subprocess.run([sys.executable, 'tests/mutants.py', '--self-check', *ids], env=era_env(era),
                                capture_output=True, text=True)
        killed = [line for line in result.stdout.splitlines() if line.startswith('killed ')]
        failed = [line for line in result.stdout.splitlines() if line.startswith('FAILED')]
        print(f'F7 cases, {label} era: {len(killed)} of {len(ids)} killed, exit {result.returncode}', file=sys.stderr)
        bad += [f'{label} era: {line}' for line in failed]
        if result.returncode != 0 and not failed:
            bad.append(f'{label} era: the runner exited {result.returncode}: {result.stderr[-400:]}')
        if len(killed) != len(ids):
            bad.append(f'{label} era: {len(killed)} of {len(ids)} cases reported killed')
    return bad


def must_pass(name: str, case: mutants.Case, targets: tuple[str, ...]) -> list[str]:
    bad: list[str] = []
    for label, era in ERAS.items():
        with tempfile.TemporaryDirectory(prefix=f'equivalent-{name}-') as scratch:
            dest = Path(scratch)
            src_root = mutants.apply(case, dest)
            # The CLI drives among the targets run over every kind, not the suite's one per family.
            saved, wanted = os.environ.copy(), {**era_env(era), 'CLUSTER_MCP_TEST_EVERY_KIND': '1'}
            os.environ.clear()
            os.environ.update(wanted)
            try:
                child = mutants.run_child(src_root, targets, dest / 'junit.xml')
            finally:
                os.environ.clear()
                os.environ.update(saved)
        tail = child.stdout.strip().splitlines()[-1:] or ['']
        print(f'F7 equivalent {name}, {label} era: exit {child.returncode}, {tail[0]}', file=sys.stderr)
        if child.returncode == mutants.WRONG_ORIGIN:
            bad.append(f'{name}, {label} era: the child did not import the mutated copy')
        elif child.returncode != 0:
            failing = [line for line in child.stdout.splitlines() if line.startswith('FAILED')]
            bad.append(f'{name}, {label} era: recorded as equivalent, but its rows fail: '
                       f'{failing[:5] or (child.stdout + child.stderr)[-400:]}')
    return bad


def run_equivalents() -> list[str]:
    bad: list[str] = []
    for name, (edit, _) in EQUIVALENT.items():
        case = mutants.Case(name, EQUIVALENT_FILES.get(name, LOADER), (edit,), EQUIVALENT_TARGETS, '')
        bad += must_pass(name, case, EQUIVALENT_TARGETS)
    known = {case.id: case for case in mutants.CASES}
    for name, (sets, rows, _) in SET_EQUIVALENT.items():
        bad += must_pass(f'{name} beside {", ".join(sets)}', known[name], rows)
    return bad


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if mode not in ('coverage', 'cases', 'equivalents', 'all'):
        raise SystemExit('usage: F7-mutant-alternatives.py [coverage|cases|equivalents|all]')
    mapping, bad = coverage()
    if mode in ('cases', 'all'):
        bad += run_cases(swept_cases(mapping))
    if mode in ('equivalents', 'all'):
        bad += run_equivalents()
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'F7: {mode} ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
