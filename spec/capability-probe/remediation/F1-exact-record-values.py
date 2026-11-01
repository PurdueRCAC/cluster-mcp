# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Review cycle 1, F1: after the load, no read of a loaded record runs capability code.

    uv run python -I spec/capability-probe/remediation/F1-exact-record-values.py [checker|coverage|cases|cli|all]
                                                                              from the worktree root

The record had to be exactly a `Capability` (P2's ruling, `P2-exact-capability.py`), but the values in
it were `isinstance` checks: an `order` that is an `int` of a type of its own loaded, and composing the
base after the load ran its `__eq__`, which could end the start with exit 0 and no message. Every value
the core or FastMCP reads from a loaded record is now an exact built-in type, decided at the load and
refused naming the distribution: the record's `name`, `tools` and `instructions` (`str`), `order`
(`int`, never a `bool`), `resources` and `commands` (`tuple`), each command (`str`), each resource
entry (`dict`), each key of one (`str`), its `uri`, `name` and `description` (`str`) and its `executor`
(exactly `True`), and the distribution's name the load orders and composes by (`str`). A resource's
handler is the capability's code, which FastMCP registers and a request calls, and is not checked.

- `checker` (seconds, in process): the property over a generated domain. Each site (every field of the
  record, from `dataclasses.fields`, so a field added later is covered; a command; a resource entry; a
  key of one; each value of one but the handler, from the core's own entry, so a key added later is
  covered; the distribution's name) is given a value of each shape of a type of its own (a subclass
  adding nothing, and one whose every operation, as `OPERATIONS` lists them, records and exits once
  the record is built; for `order` a `bool` too), beside every member set (core only, slurm, rcac,
  both). Each is refused with exactly one `CapabilityLoadError` naming its distribution (or its entry
  point's value, for a name that is no name) with the cause the site gives, the tool registry left as
  it was and none of the value's operations run. Controls: a capability whose every site holds an
  exact value loads beside each set, and every value of every record that loaded, the members' too,
  is exactly its type.
- `coverage` (seconds): each exact check the load makes, mutated to every alternative
  `alternatives.py`'s rules give it (always, never, negated, each operand and the other operator, each
  comparison inside an operator negated, each type of an `in` tuple dropped), each field or key of the
  tuple a check loops over dropped, and each check put back to `isinstance` (for `order`, the
  `isinstance` that refused a `bool`): every alternative a case of `tests/mutants.py` turns into the
  same syntax tree, each case targeting a row beside every member set.
- `cases` (about 6 s a case an era): each such case run by `tests/mutants.py --self-check`, in the
  handshake era, then in revision 2026-07-28's, each killed.
- `cli` (about 1 min an era): with `CLUSTER_MCP_TEST_EVERY_KIND=1`, every `exact-<site>` kind of
  `test_capabilities.UNLOADABLE` driven through the CLI over the raw wire, with stdin closed and over
  HTTP (`test_startup.py::test_a_capability_that_cannot_load_stops_startup`), in each era; the drives
  collected must number three per kind. The suite drives one of them, `exact-order`.

`all` (the default) runs the four. Footprint: one process, then one mutant child or pytest at a time,
the CLI drives under bin/sandbox.sh each in its own process group, under 1 GB; no network.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import os
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import fields
from importlib.metadata import Distribution, entry_points
from pathlib import Path

ROOT = Path.cwd()
VERIFY = ROOT / 'spec/capability-probe/verify'
_spec = importlib.util.spec_from_file_location('capability_probe_alternatives', VERIFY / 'alternatives.py')
alternatives = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = alternatives
_spec.loader.exec_module(alternatives)
mutants = alternatives.mutants

from cluster_mcp.core.capabilities import GROUP, Capability, CapabilityLoadError, installed, load  # noqa: E402
from cluster_mcp.core.resources import RESOURCE_REGISTRY  # noqa: E402
from cluster_mcp.core.tools import TOOL_REGISTRY  # noqa: E402

LOADER = 'core/capabilities.py'
SETS = {'core-only': (), 'slurm': ('slurm',), 'rcac': ('rcac',), 'both': ('rcac', 'slurm')}

# The operations of each type a subclass of it overrides, as the suite's `exact-<site>` kinds do.
OPERATIONS = {
    'str': ('__eq__', '__ne__', '__lt__', '__le__', '__gt__', '__ge__', '__hash__', '__len__', '__iter__',
            '__contains__', '__getitem__', '__add__', '__mul__', '__mod__', '__format__', '__str__', '__repr__',
            'startswith', 'endswith', 'strip', 'lstrip', 'rstrip', 'split', 'rsplit', 'partition', 'rpartition',
            'splitlines', 'replace', 'lower', 'upper', 'casefold', 'encode', 'join', 'format', 'find', 'index',
            'count', 'expandtabs', 'removeprefix', 'removesuffix', 'isidentifier', 'isascii', 'isdigit'),
    'int': ('__eq__', '__ne__', '__lt__', '__le__', '__gt__', '__ge__', '__hash__', '__bool__', '__index__',
            '__int__', '__float__', '__add__', '__radd__', '__sub__', '__rsub__', '__mul__', '__neg__', '__abs__',
            '__format__', '__str__', '__repr__', '__round__', '__trunc__', 'bit_length'),
    'tuple': ('__eq__', '__ne__', '__lt__', '__le__', '__gt__', '__ge__', '__hash__', '__len__', '__iter__',
              '__contains__', '__getitem__', '__add__', '__mul__', '__format__', '__str__', '__repr__', 'count',
              'index'),
    'dict': ('__eq__', '__ne__', '__len__', '__iter__', '__contains__', '__getitem__', '__setitem__', '__or__',
             '__ror__', '__reversed__', '__format__', '__str__', '__repr__', 'get', 'keys', 'values', 'items',
             'copy', 'setdefault', 'pop', 'update'),
}

TOOLS = '''\
from cluster_mcp.core.tools import mcp_tool


@mcp_tool
def {mod}_echo(text: str) -> str:
    """Echo a text back."""
    return text
'''

TYPES = f'''
RAN: list = []
ARMED: list = []
_OPERATIONS = {OPERATIONS!r}


def _read() -> str:
    """The text a planted resource serves."""
    return 'planted'


def _subclass(base, shape):
    def operation(name):
        def run(self, *args, **kwargs):
            if ARMED:
                RAN.append(name)
                raise SystemExit(0)
            return getattr(base, name)(self, *args, **kwargs)
        return run
    body = {{}} if shape == 'plain' else {{name: operation(name) for name in _OPERATIONS[base.__name__]}}
    return type(('Plain' if shape == 'plain' else 'Planted') + base.__name__.title(), (base,), body)
'''

# Each field's built-in type, from its annotation; a field whose annotation names none of these is a gap.
BUILTIN = {'str': str, 'int': int, 'tuple': tuple, 'dict': dict}


def field_types() -> dict[str, type]:
    out = {}
    for f in fields(Capability):
        head = str(f.type).split('[', 1)[0]
        out[f.name] = BUILTIN.get(head)
    return out


ENTRY_KEYS = tuple(key for key in RESOURCE_REGISTRY[0] if key != 'handler')
ENTRY_TYPES = {'uri': str, 'name': str, 'description': str, 'executor': int}


def sites() -> dict[str, type]:
    """Every site the load checks for an exact type, with the built-in type a subclass is made of."""
    out = {f'field-{name}': kind for name, kind in field_types().items()}
    out |= {'command': str, 'resource': dict, 'resource-key': str}
    out |= {f'resource-{key}': ENTRY_TYPES.get(key) for key in ENTRY_KEYS}
    out['distribution'] = str
    return out


def shapes(site: str) -> tuple[str, ...]:
    return ('plain', 'planted', 'bool') if site == 'field-order' else ('plain', 'planted')


def article(kind: str) -> str:
    return 'an' if kind == 'int' else 'a'


def record_source(mod: str, site: str, value: str | None) -> tuple[str, str | None]:
    """The record's source with the site's value `value` (None: every value exact), and the cause."""
    entry = {"'uri'": "'cluster://planted'", "'name'": "'planted'", "'description'": "'Planted'",
             "'handler'": '_read', "'executor'": 'True'}
    record = {'name': repr(mod), 'order': '500', 'tools': repr(f'{mod}.tools'),
              'instructions': repr(f'Planted tools:\n- {mod}_echo: Echo a text back'), 'resources': '',
              'commands': "('planted_cmd',)"}
    cause = None
    tname = value.split('(', 1)[0] if value else ''
    shown = "its resource 'cluster://planted'"
    if value is None:
        pass
    elif site.startswith('field-'):
        name = site.removeprefix('field-')
        kind = field_types()[name].__name__
        if name != 'resources':
            record[name] = value.format(record[name]) if '{}' in value else value
        cause = f'its {name} is a {tname}, not {article(kind)} {kind}'
    elif site == 'command':
        record['commands'] = f"({value.format(repr('planted_cmd'))},)"
        cause = f'one of its commands is a {tname}, not a str'
    elif site == 'resource':
        cause = f'one of its resources is a {tname}, not a dict'
    elif site == 'resource-key':
        entry = {(value.format("'uri'") if key == "'uri'" else key): v for key, v in entry.items()}
        cause = f'one of its resources has a {tname} key, not a str'
    elif site == 'resource-executor':
        entry["'executor'"] = value.format('1')
        cause = f'{shown} has executor a {tname}, not True: a capability resource is never open'
    elif site.startswith('resource-'):
        key = site.removeprefix('resource-')
        entry[repr(key)] = value.format(entry[repr(key)])
        cause = (f'one of its resources has a {tname} uri, not a str' if key == 'uri'
                 else f'{shown} has a {tname} {key}, not a str')
    source = '{' + ', '.join(f'{key}: {v}' for key, v in entry.items()) + '}'
    if site == 'resource' and value is not None:
        source = value.format(source)
    record['resources'] = (value.format(f'({source},)') if site == 'field-resources' and value is not None
                           else f'({source},)')
    return 'Capability(' + ', '.join(f'{k}={v}' for k, v in record.items()) + ')', cause


class Named(Distribution):
    """A distribution whose `Name` is the value its module's `NAME` holds."""

    def __init__(self, info: Path, name: object) -> None:
        self.info = info
        self._name = name

    def read_text(self, filename: str) -> str | None:
        path = self.info / filename
        return path.read_text() if path.is_file() else None

    def locate_file(self, path: str) -> Path:
        return self.info.parent / path

    @property
    def name(self) -> object:
        return self._name


def plant(root: Path, label: str, site: str, shape: str | None):
    """A planted distribution whose `site` holds a value of `shape` (None: every value exact): its entry
    point, the name its refusal carries, its capability module, the cause, and the namespace of a
    distribution name's type (None for the others)."""
    mod = 'planted_exact_' + label.replace('-', '_')
    pkg = root / mod
    pkg.mkdir()
    (pkg / '__init__.py').write_text('')
    (pkg / 'tools.py').write_text(TOOLS.format(mod=mod))
    if shape is None or site == 'distribution':
        record, cause = record_source(mod, site, None)
    elif shape == 'bool':
        record, _ = record_source(mod, site, 'True')
        cause = 'its order is a bool, not an int'
    else:
        cls = ('Plain' if shape == 'plain' else 'Planted') + sites()[site].__name__.title()
        record, cause = record_source(mod, site, f'{cls}({{}})')
    head = 'from cluster_mcp.core.capabilities import Capability\n' + TYPES + ''.join(
        f'\n{("Plain" if s == "plain" else "Planted") + b.title()} = _subclass({b}, {s!r})'
        for b in ('str', 'int', 'tuple', 'dict') for s in ('plain', 'planted')) + '\n'
    (pkg / 'capability.py').write_text(head + f'\n\nCAPABILITY = {record}\n\nARMED.append(True)\n')
    dist = f'planted-exact-{label}'
    info = root / f'{mod}-1.0.dist-info'
    info.mkdir()
    (info / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: {dist}\nVersion: 1.0\n')
    (info / 'entry_points.txt').write_text(f'[{GROUP}]\n{mod} = {mod}.capability:CAPABILITY\n')
    if site == 'distribution' and shape is not None:
        types_ns: dict = {}
        exec(compile(TYPES, f'<{mod} types>', 'exec'), types_ns)
        (ep,) = [e for e in Named(info, types_ns['_subclass'](str, shape)(dist)).entry_points if e.group == GROUP]
        return ep, ep.value, f'{mod}.capability', 'its distribution metadata has no Name', types_ns
    (ep,) = [e for e in Distribution.at(info).entry_points if e.group == GROUP]
    return ep, dist, f'{mod}.capability', cause, None


def exactly(value: object, kind: type) -> bool:
    return type(value) is kind


def record_violations(loaded) -> list[str]:
    """Every value of a loaded record that is not exactly its type."""
    bad = []
    cap = loaded.capability
    where = loaded.distribution if type(loaded.distribution) is str else '<a distribution>'
    if type(cap) is not Capability:
        bad.append(f'{where}: the record is a {type(cap).__name__}')
    if type(loaded.distribution) is not str:
        bad.append(f'{where}: its distribution name is a {type(loaded.distribution).__name__}')
    for name, kind in field_types().items():
        if not exactly(getattr(cap, name), kind):
            bad.append(f'{where}: its {name} is a {type(getattr(cap, name)).__name__}')
    for command in cap.commands:
        if type(command) is not str:
            bad.append(f'{where}: a command is a {type(command).__name__}')
    for entry in cap.resources:
        if type(entry) is not dict:
            bad.append(f'{where}: a resource is a {type(entry).__name__}')
            continue
        bad += [f'{where}: a resource key is a {type(k).__name__}' for k in entry if type(k) is not str]
        bad += [f'{where}: a resource {k} is a {type(entry.get(k)).__name__}' for k in ('uri', 'name', 'description')
                if type(entry.get(k)) is not str]
        if entry.get('executor') is not True:
            bad.append(f'{where}: a resource executor is {type(entry.get("executor")).__name__}')
    return bad


def checker() -> list[str]:
    bad: list[str] = []
    installed()
    members = {ep.name: ep for ep in entry_points(group=GROUP)}
    domain = [(site, shape) for site, kind in sites().items() for shape in shapes(site)]
    gaps = [site for site, kind in sites().items() if kind is None]
    if gaps:
        return [f'a site with no built-in type to make a subclass of: {gaps}']
    with tempfile.TemporaryDirectory(prefix='exact-values-') as scratch:
        root = Path(scratch)
        sys.path.insert(0, scratch)
        planted = {f'{site}-{shape}': (site, plant(root, f'{site}-{shape}', site, shape)) for site, shape in domain}
        control = plant(root, 'control', 'field-name', None)
        reached = 0
        for set_name, names in SETS.items():
            beside = [members[n] for n in names]
            for label, (site, (ep, named, module, cause, types_ns)) in planted.items():
                before = list(TOOL_REGISTRY)
                if types_ns is not None:
                    types_ns['ARMED'].append(True)
                try:
                    load([*beside, ep])
                except CapabilityLoadError as exc:
                    want = f'cannot load capability {named}: {cause}'
                    if str(exc) != want:
                        bad.append(f'{label} beside {set_name}: refused as {str(exc)!r}, expected {want!r}')
                    else:
                        reached += 1
                except KeyboardInterrupt:
                    raise
                except BaseException as exc:
                    bad.append(f'{label} beside {set_name}: {type(exc).__name__} escaped the load: {exc!r}')
                else:
                    bad.append(f'{label} beside {set_name}: loaded; its {site} must be exactly a {sites()[site].__name__}')
                finally:
                    if types_ns is not None:
                        types_ns['ARMED'].clear()
                if list(TOOL_REGISTRY) != before:
                    bad.append(f'{label} beside {set_name}: the refusal left the tool registry changed')
                    TOOL_REGISTRY[:] = before
                ran = types_ns['RAN'] if types_ns is not None else getattr(sys.modules.get(module), 'RAN', None)
                if ran:
                    bad.append(f'{label} beside {set_name}: its value\'s code ran during the load: {ran}')
                    ran.clear()
                # Forget it, so the next set imports it afresh, as a start would.
                package = module.split('.', 1)[0]
                for name in [n for n in sys.modules if n == package or n.startswith(package + '.')]:
                    del sys.modules[name]
            ep, *_ = control
            before = list(TOOL_REGISTRY)
            try:
                loaded = load([*beside, ep])
                bad += record_violations_all(loaded, set_name)
                if [c.distribution for c in loaded][-1:] != ['planted-exact-control']:
                    bad.append(f'control beside {set_name}: loaded {[c.distribution for c in loaded]}')
            except BaseException as exc:
                bad.append(f'control beside {set_name}: an exact record was refused: {exc}')
            TOOL_REGISTRY[:] = before
            for name in [n for n in sys.modules if n.startswith('planted_exact_control')]:
                del sys.modules[name]
    want = len(domain) * len(SETS)
    if reached != want:
        bad.append(f'only {reached} of {want} planted values reached their refusal')
    print(f'checker: {len(sites())} sites, {len(domain)} values, beside {len(SETS)} member sets, '
          f'{reached} refused as expected; a control per set', file=sys.stderr)
    return bad


def record_violations_all(loaded, set_name: str) -> list[str]:
    return [f'control beside {set_name}: {v}' for c in loaded for v in record_violations(c)]


# The exact checks: (function, a word its `if` or `return` holds), and each alternative beyond the rules.
CHECKS = (('_identity', 'type(name) is not str'), ('_checked', 'type(getattr(value, field)) is not kind'),
          ('_checked', 'type(value.order) is not int'), ('_shown', 'type(value) in'),
          ('_check_resource', 'type(entry) is not dict'), ('_check_resource', 'type(key) is not str'),
          ("_check_resource", "type(entry.get('uri')) is not str"),
          ('_check_resource', 'type(entry.get(key)) is not str'))


def nodes(module: ast.Module) -> tuple[list[ast.AST], list[str]]:
    found, gaps = [], []
    for func, word in CHECKS:
        fn = alternatives.function(module, func)
        hits = [n for n in ast.walk(fn) if isinstance(n, (ast.If, ast.IfExp)) and word in ast.unparse(n.test)] \
            if fn else []
        if len(hits) != 1:
            gaps.append(f'{LOADER}: {func} holds {len(hits)} checks of {word!r}, expected one')
        found += hits
    return found, gaps


class _ToIsinstance(ast.NodeTransformer):
    """`type(x) is not T` to `not isinstance(x, T)` (and `type(x) is T` to `isinstance(x, T)`)."""

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        if (len(node.ops) == 1 and isinstance(node.ops[0], (ast.Is, ast.IsNot)) and isinstance(node.left, ast.Call)
                and getattr(node.left.func, 'id', None) == 'type'):
            call = ast.Call(func=ast.Name('isinstance', ast.Load()), args=[node.left.args[0], node.comparators[0]],
                            keywords=[])
            return ast.UnaryOp(ast.Not(), call) if isinstance(node.ops[0], ast.IsNot) else call
        return node


def extra(text: str, checks: list[ast.AST]) -> list[alternatives.Alternative]:
    """Each check put back to `isinstance`; the old `order` check; each element of a checked tuple dropped."""
    out = []
    for check in checks:
        if not isinstance(check, ast.If) or 'type(' not in ast.unparse(check.test) or ' in (' in ast.unparse(check.test):
            continue
        out.append(alternatives.Alternative(LOADER, check.lineno, 'isinstance', alternatives.replaced(
            text, check.test, lambda n: _ToIsinstance().visit(n))))
    old_order = alternatives.applied(text, (('    if type(value.order) is not int:\n',
                                             '    if not isinstance(value.order, int) or isinstance(value.order, bool):\n'),))
    if old_order is None:
        out.append(alternatives.Alternative(LOADER, 0, 'GAP: the order check is not in the file once', ''))
    else:
        out.append(alternatives.Alternative(LOADER, 0, 'order: isinstance refusing a bool', alternatives.tree(old_order)))
    module = ast.parse(text)
    for func in ('_checked', '_check_resource'):
        for loop in ast.walk(alternatives.function(module, func)):
            if isinstance(loop, ast.For) and isinstance(loop.iter, ast.Tuple) and any(
                    'type(' in ast.unparse(n.test) for n in ast.walk(loop) if isinstance(n, ast.If)):
                for i, element in enumerate(loop.iter.elts):
                    def drop(n: ast.For, i: int = i) -> ast.For:
                        n = copy.deepcopy(n)
                        n.iter = ast.Tuple(elts=[e for j, e in enumerate(n.iter.elts) if j != i], ctx=ast.Load())
                        return n
                    out.append(alternatives.Alternative(LOADER, loop.lineno, f'without {ast.unparse(element)}',
                                                        alternatives.replaced(text, loop, drop)))
    return out


def coverage() -> tuple[list[str], list[str]]:
    text = alternatives.source(LOADER)
    module = ast.parse(text)
    checks, gaps = nodes(module)
    alts = alternatives.decisions(text, LOADER, checks) + extra(text, checks)
    gaps += [a.what.removeprefix('GAP: ') for a in alts if a.what.startswith('GAP: ')]
    own = alternatives.tree(text)
    alts = list({a.tree: a for a in alts if a.tree and a.tree != own}.values())
    by_tree: dict[str, list[str]] = {}
    for case in mutants.CASES:
        if case.file == LOADER:
            mutated = alternatives.applied(text, case.edits)
            if mutated is not None:
                by_tree.setdefault(alternatives.tree(mutated), []).append(case.id)
    known = {case.id: case for case in mutants.CASES}
    swept: list[str] = []
    for alt in alts:
        names = by_tree.get(alt.tree, [])
        if not names:
            gaps.append(f'{LOADER}:{alt.line}: {alt.what}: no mutant')
        for name in names:
            missing = [s for s in SETS if s not in {alternatives.row_set(t) for t in known[name].targets}]
            if missing:
                gaps.append(f'{name}: no target row beside {missing}')
        swept += names
    swept = list(dict.fromkeys(swept))
    print(f'coverage: {len(checks)} exact checks, {len(alts)} alternatives, {len(swept)} cases', file=sys.stderr)
    return swept, gaps


def cases(ids: list[str]) -> list[str]:
    bad: list[str] = []
    for label, era in alternatives.ERAS.items():
        result = subprocess.run([sys.executable, 'tests/mutants.py', '--self-check', *ids],
                                env=alternatives.era_env(era), capture_output=True, text=True)
        killed = [line for line in result.stdout.splitlines() if line.startswith('killed ')]
        print(f'cases, {label} era: {len(killed)} of {len(ids)} killed, exit {result.returncode}', file=sys.stderr)
        if result.returncode != 0 or len(killed) != len(ids):
            bad.append(f'{label} era: {len(killed)} of {len(ids)} killed, exit {result.returncode}: '
                       f'{(result.stdout + result.stderr)[-800:]}')
    return bad


def cli() -> list[str]:
    bad: list[str] = []
    drive = 'tests/test_startup.py::test_a_capability_that_cannot_load_stops_startup'
    kinds = subprocess.run([sys.executable, '-c', 'import sys; sys.path.insert(0, "tests"); '
                            'from test_capabilities import UNLOADABLE; '
                            'print(*[k for k in UNLOADABLE if k.startswith("exact-")])'],
                           capture_output=True, text=True, check=True).stdout.split()
    for label, era in alternatives.ERAS.items():
        env = {**alternatives.era_env(era), 'CLUSTER_MCP_TEST_EVERY_KIND': '1'}
        listed = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--collect-only',
                                 drive, '-k', 'exact-'], env=env, capture_output=True, text=True)
        collected = [line for line in listed.stdout.splitlines() if '::' in line]
        if len(collected) != 3 * len(kinds) or not kinds:
            bad.append(f'{label} era: {len(collected)} CLI drives collected, not three for each of {len(kinds)} kinds')
            continue
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', drive, '-k', 'exact-'],
                                env=env, capture_output=True, text=True)
        summary = (result.stdout.strip().splitlines() or [''])[-1]
        print(f'cli, {label} era: {len(kinds)} kinds, {len(collected)} drives: {summary}', file=sys.stderr)
        if result.returncode != 0 or f'{len(collected)} passed' not in summary:
            bad.append(f'{label} era: {summary}: {result.stdout[-1200:]}')
    return bad


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if mode not in ('checker', 'coverage', 'cases', 'cli', 'all'):
        raise SystemExit('usage: F1-exact-record-values.py [checker|coverage|cases|cli|all]')
    bad: list[str] = []
    if mode in ('checker', 'all'):
        bad += checker()
    if mode in ('coverage', 'cases', 'all'):
        swept, gaps = coverage()
        bad += gaps
        if mode in ('cases', 'all'):
            bad += cases(swept) if swept else ['no case to run']
    if mode in ('cli', 'all'):
        bad += cli()
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'F1-exact-record-values: {mode} ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
