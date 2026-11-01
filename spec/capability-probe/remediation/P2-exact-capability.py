# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The foreman's ruling at P2 (2026-11-01): what an entry point names is exactly a `Capability`.

    uv run python -I spec/capability-probe/remediation/P2-exact-capability.py [checker|coverage|cases|all]
                                                                         from the worktree root

P1's load took any `isinstance(value, Capability)`, so a subclass could override how a field is read,
and its code would run wherever startup or the server reads that field after the load, outside the
load's guard. The load now requires `type(value) is Capability`. The phase gates under `verify/` are
frozen at the plan commit, and `alternatives.py` sweeps only the load's checks of a declared command,
so this checker carries the decision for P2's gate:

- `checker` (seconds, in process, no subprocess): planted distributions, each beside every member
  set, whose entry point names a subclass of `Capability` that runs its own code when one field is
  read, for every field of the record (`dataclasses.fields`, so a field added later is covered), in
  two ways (`__getattribute__`, and a class attribute that is a data descriptor); a subclass adding
  nothing; a frozen dataclass subclass; an object whose `__class__` claims `Capability` (which
  `isinstance` believes); and a class of another module named `Capability`. Each is refused at load
  with `CapabilityLoadError` naming its distribution, as `the entry point names a <type>, not a
  Capability`, on one line, the registry unchanged and none of its code run. A plain `Capability`
  planted the same way loads, as a control.
- `coverage` (seconds): the `if` in `_checked` that tests the record's type, mutated to every
  alternative `alternatives.py`'s rules give it (always, never, negated), and to `isinstance` (the
  check P1 shipped), each turned into the same syntax tree by a case of `tests/mutants.py` that
  targets a row beside every member set.
- `cases` (about 10 s an era): each such case run by `tests/mutants.py --self-check` in the handshake
  era, then in revision 2026-07-28's, each killed.

`all` (the default) runs the three. Footprint: one process, then one mutant child at a time, under
1 GB; no network.
"""

from __future__ import annotations

import ast
import importlib.util
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
from cluster_mcp.core.tools import TOOL_REGISTRY  # noqa: E402

LOADER = 'core/capabilities.py'
SETS = {'core-only': (), 'slurm': ('slurm',), 'rcac': ('rcac',), 'both': ('rcac', 'slurm')}
EXTRA = (('the load accepts a subclass (isinstance)',
          (('    if type(value) is not Capability:\n', '    if not isinstance(value, Capability):\n'),)),)

TOOLS = '''\
from cluster_mcp.core.tools import mcp_tool


@mcp_tool
def {mod}_echo(text: str) -> str:
    """Echo a text back."""
    return text
'''

# The record's arguments, as every planted kind gives them.
ARGS = "name='{mod}', order=500, tools='{mod}.tools', instructions='Planted tools:\\n- {mod}_echo: Echo a text back'"

# Every kind of record other than exactly a `Capability`: (class source, the type named, how built).
GETATTRIBUTE = '''
class Reads(Capability):
    def __getattribute__(self, name):
        if name == {field!r}:
            RAN.append(name)
        return object.__getattribute__(self, name)
'''
DESCRIPTOR = '''
class _Field:
    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        RAN.append(self.name)
        return instance.__dict__[self.name]

    def __set__(self, instance, value):
        instance.__dict__[self.name] = value


class Reads(Capability):
    {field} = _Field()
'''


def kinds() -> dict[str, tuple[str, str, str]]:
    out: dict[str, tuple[str, str, str]] = {}
    for f in fields(Capability):
        out[f'getattribute-{f.name}'] = (GETATTRIBUTE.format(field=f.name), 'Reads', f'Reads({ARGS})')
        out[f'descriptor-{f.name}'] = (DESCRIPTOR.format(field=f.name), 'Reads', f'Reads({ARGS})')
    out['plain-subclass'] = ('\nclass Plain(Capability):\n    pass\n', 'Plain', f'Plain({ARGS})')
    out['dataclass-subclass'] = ('\nfrom dataclasses import dataclass\n\n\n@dataclass(frozen=True)\n'
                                 'class Frozen(Capability):\n    extra: int = 0\n', 'Frozen', f'Frozen({ARGS})')
    out['claims-its-class'] = ('\nclass Claims:\n    @property\n    def __class__(self):\n        RAN.append("__class__")\n'
                               '        return Capability\n\n    def __init__(self, **kw):\n'
                               '        self.__dict__.update(kw, resources=(), commands=())\n', 'Claims',
                               f'Claims({ARGS})')
    out['named-capability'] = ('\nclass Capability:\n    def __init__(self, **kw):\n'
                               '        self.__dict__.update(kw, resources=(), commands=())\n', 'Capability',
                               f'Capability({ARGS})')
    return out


def plant(root: Path, label: str, source: str, built: str) -> tuple[str, object, str]:
    """A planted distribution `planted-<label>` whose entry point names `built`; its entry point and module."""
    mod = 'planted_exact_' + label.replace('-', '_')
    pkg = root / mod
    pkg.mkdir()
    (pkg / '__init__.py').write_text('')
    (pkg / 'tools.py').write_text(TOOLS.format(mod=mod))
    head = 'from cluster_mcp.core.capabilities import Capability\n\nRAN: list = []\n'
    (pkg / 'capability.py').write_text(head + textwrap.dedent(source) + f'\n\nCAPABILITY = {built.format(mod=mod)}\n')
    dist = f'planted-exact-{label}'
    info = root / f'{mod}-1.0.dist-info'
    info.mkdir()
    (info / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: {dist}\nVersion: 1.0\n')
    (info / 'entry_points.txt').write_text(f'[{GROUP}]\n{mod} = {mod}.capability:CAPABILITY\n')
    (ep,) = [ep for ep in Distribution.at(info).entry_points if ep.group == GROUP]
    return dist, ep, f'{mod}.capability'


def checker() -> list[str]:
    bad: list[str] = []
    # The members' tools register once, here, as at startup; every later load of a member finds them.
    installed()
    members = {ep.name: ep for ep in entry_points(group=GROUP)}
    with tempfile.TemporaryDirectory(prefix='exact-capability-') as scratch:
        root = Path(scratch)
        sys.path.insert(0, scratch)
        planted = {label: plant(root, label, spec[0], spec[2]) for label, spec in kinds().items()}
        named = {label: spec[1] for label, spec in kinds().items()}
        control = plant(root, 'control', '', f'Capability({ARGS})')
        for set_name, names in SETS.items():
            beside = [members[n] for n in names]
            for label, (dist, ep, module) in planted.items():
                before = list(TOOL_REGISTRY)
                try:
                    load([*beside, ep])
                except CapabilityLoadError as exc:
                    want = f'cannot load capability {dist}: the entry point names a {named[label]}, not a Capability'
                    if str(exc) != want:
                        bad.append(f'{label} beside {set_name}: refused as {str(exc)!r}, expected {want!r}')
                except BaseException as exc:
                    bad.append(f'{label} beside {set_name}: {type(exc).__name__} escaped the load: {exc}')
                else:
                    bad.append(f'{label} beside {set_name}: loaded; a record must be exactly a Capability')
                if list(TOOL_REGISTRY) != before:
                    bad.append(f'{label} beside {set_name}: the refusal left the tool registry changed')
                ran = getattr(sys.modules.get(module), 'RAN', None)
                if ran:
                    bad.append(f'{label} beside {set_name}: its code ran during the load: {ran}')
                    ran.clear()
            dist, ep, _ = control
            before = list(TOOL_REGISTRY)
            try:
                loaded = load([*beside, ep])
                if [c.distribution for c in loaded][-1:] != [dist]:
                    bad.append(f'control beside {set_name}: loaded {[c.distribution for c in loaded]}')
            except BaseException as exc:
                bad.append(f'control beside {set_name}: a plain Capability was refused: {exc}')
            # Forget the control, so the next load imports it, and registers its tool, afresh.
            TOOL_REGISTRY[:] = before
            for name in [n for n in sys.modules if n.startswith('planted_exact_control')]:
                del sys.modules[name]
    print(f'checker: {len(kinds())} kinds beside {len(SETS)} member sets, and a control', file=sys.stderr)
    return bad


def the_check(text: str) -> ast.If | None:
    checked = alternatives.function(ast.parse(text), '_checked')
    return next((n for n in checked.body if isinstance(n, ast.If) and 'type(value)' in ast.unparse(n.test)
                 and 'Capability' in ast.unparse(n.test)), None) if checked else None


def coverage() -> tuple[list[str], list[str]]:
    text = alternatives.source(LOADER)
    node = the_check(text)
    if node is None:
        return [], [f'{LOADER}: _checked tests no record type with type(value)']
    alts = alternatives.decisions(text, LOADER, [node])
    for what, edits in EXTRA:
        mutated = alternatives.applied(text, edits)
        if mutated is None:
            return [], [f'{LOADER}: the anchor of "{what}" is not in the file once']
        alts.append(alternatives.Alternative(LOADER, node.lineno, what, alternatives.tree(mutated)))
    own = alternatives.tree(text)
    alts = list({a.tree: a for a in alts if a.tree != own}.values())
    by_tree: dict[str, list[str]] = {}
    for case in mutants.CASES:
        if case.file == LOADER:
            mutated = alternatives.applied(text, case.edits)
            if mutated is not None:
                by_tree.setdefault(alternatives.tree(mutated), []).append(case.id)
    gaps: list[str] = []
    swept: list[str] = []
    known = {case.id: case for case in mutants.CASES}
    for alt in alts:
        names = by_tree.get(alt.tree, [])
        if not names:
            gaps.append(f'{LOADER}:{alt.line}: {alt.what}: no mutant')
        for name in names:
            sets = {alternatives.row_set(t) for t in known[name].targets}
            missing = [s for s in SETS if s not in sets]
            if missing:
                gaps.append(f'{name}: no target row beside {missing}')
        swept += names
    print(f'coverage: {len(alts)} alternatives of the record\'s type check; {len(swept)} cases', file=sys.stderr)
    return list(dict.fromkeys(swept)), gaps


def cases(ids: list[str]) -> list[str]:
    bad: list[str] = []
    for label, era in alternatives.ERAS.items():
        result = subprocess.run([sys.executable, 'tests/mutants.py', '--self-check', *ids],
                                env=alternatives.era_env(era), capture_output=True, text=True)
        killed = [line for line in result.stdout.splitlines() if line.startswith('killed ')]
        print(f'cases, {label} era: {len(killed)} of {len(ids)} killed, exit {result.returncode}', file=sys.stderr)
        if result.returncode != 0 or len(killed) != len(ids):
            bad.append(f'{label} era: {len(killed)} of {len(ids)} killed, exit {result.returncode}: '
                       f'{(result.stdout + result.stderr)[-600:]}')
    return bad


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if mode not in ('checker', 'coverage', 'cases', 'all'):
        raise SystemExit('usage: P2-exact-capability.py [checker|coverage|cases|all]')
    bad: list[str] = []
    if mode in ('checker', 'all'):
        bad += checker()
    if mode in ('coverage', 'cases', 'all'):
        swept, gaps = coverage()
        bad += gaps
        if mode in ('cases', 'all'):
            bad += cases(swept) if swept else ['no case to run']
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'P2-exact-capability: {mode} ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
