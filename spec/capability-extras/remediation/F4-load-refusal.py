# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Review cycle 2, F1-F3, routed as one property (checker F4; checker ids number on across cycles, so
cycle 2's F1-F3 are F4-F6 and share this checker): every failure from discovering, ordering or loading
a capability is refused, naming its distribution (its entry point's value when the distribution has no
name), and whether a registration is checked never depends on when the capability's code imported its
tools module.

    uv run python -I spec/capability-extras/remediation/F4-load-refusal.py      from the worktree root

The property, evaluated over a generated domain rather than the pinned rows: each planted capability is
loaded beside each member set (core only, slurm, rcac, both), in process, as scratch distributions on
`sys.path`, and

- each that must be refused is refused with exactly one `CapabilityLoadError`, one line, that begins
  `cannot load capability <name>: ` with the name its distribution's metadata gives (or its entry
  point's value), and the tool registry is left as it was;
- each `KeyboardInterrupt` is raised as it is, the registry left as it was;
- each control loads, with its tool.

The domain:

- what a capability's code raises or exits with: an `Exception` (with text, without, whose text cannot
  be had because its `__str__` raises or exits), `SystemExit` with 0, 1, 3, 255, a string, none, a
  float and a list, `GeneratorExit`, a `BaseException` of its own and a `BaseExceptionGroup` of one;
- when: at its entry point's import (before and after it builds its `Capability`), at its tools
  module's import (before and after its tool registers), in a module its tools module imports, while
  the load reads its declared `tools` (`+` on a `str` of its own), its `name` (`__hash__`) and its
  `instructions` (`strip`), and while FastMCP reads its resource handler;
- a distribution whose metadata has no `Name`, a blank one, one of spaces, no `METADATA` file at all,
  or one that is not UTF-8;
- registrations: a tool or a non-tool registered by the entry-point module, by a module it imports, by
  its tools module or a module that imports, with the tools module imported by the entry-point module,
  by a module the entry point imports, or by the load; and a tool registered in a function the entry
  point's import calls;
- controls: a capability whose entry point imports its tools module (directly, through another module),
  one whose tools module is the entry-point module itself, and one whose tools are already imported.

It is not vacuous: it fails unless every kind above was planted and reached its verdict beside each
member set. Footprint: one process, no network, under 300 MB, about 10 s.
"""

from __future__ import annotations

import itertools
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from importlib.metadata import Distribution, EntryPoint, entry_points
from pathlib import Path

from cluster_mcp.core.capabilities import GROUP, CapabilityLoadError, installed, load
from cluster_mcp.core.tools import TOOL_REGISTRY

MEMBER_SETS = {'core-only': (), 'slurm': ('slurm',), 'rcac': ('rcac',), 'both': ('rcac', 'slurm')}

TOOL = '''
from cluster_mcp.core.tools import mcp_tool


@mcp_tool
def {name}(text: str) -> str:
    """Echo a text back.

    Args:
        text: The text.
    """
    return text
'''
NOT_A_TOOL = '''
from cluster_mcp.core.tools import TOOL_REGISTRY


def {name}(text: str) -> str:
    return text


TOOL_REGISTRY.append({name})
'''
KINDS = '''
import sys


class Stop(BaseException):
    pass


class Unprintable(Exception):
    def __str__(self) -> str:
        raise RuntimeError('no text')


class Exiting(Exception):
    def __str__(self) -> str:
        raise SystemExit(2)
'''

# What a capability's code does, and the cause its refusal carries (None: a KeyboardInterrupt, raised as is).
RAISED = {
    'exception': ("raise RuntimeError('planted')", 'RuntimeError: planted'),
    'exception-empty': ('raise RuntimeError()', 'RuntimeError'),
    'exception-unprintable': ("raise Unprintable('x')", 'Unprintable'),
    'exception-exiting-text': ("raise Exiting('x')", 'Exiting'),
    'exit-0': ('sys.exit(0)', 'SystemExit: 0'),
    'exit-1': ('sys.exit(1)', 'SystemExit: 1'),
    'exit-3': ('raise SystemExit(3)', 'SystemExit: 3'),
    'exit-255': ('sys.exit(255)', 'SystemExit: 255'),
    'exit-text': ("sys.exit('needs another platform')", 'SystemExit: needs another platform'),
    'exit-none': ('sys.exit(None)', 'SystemExit'),
    'exit-bare': ('sys.exit()', 'SystemExit'),
    'exit-float': ('sys.exit(1.5)', 'SystemExit: 1.5'),
    'exit-list': ('sys.exit([1, 2])', 'SystemExit: [1, 2]'),
    'generator-exit': ("raise GeneratorExit('planted')", 'GeneratorExit: planted'),
    'base-exception': ("raise Stop('planted')", 'Stop: planted'),
    'exception-group': ("raise BaseExceptionGroup('planted', [Stop('inner')])", 'BaseExceptionGroup: planted (1 sub-exception)'),
    'keyboard-interrupt': ('raise KeyboardInterrupt', None),
}
WHEN = ('entry-before', 'entry-after', 'tools-before', 'tools-after', 'tools-imports', 'declared-tools',
        'declared-name', 'declared-instructions', 'served')

NAMELESS = {
    'no-name': 'Metadata-Version: 2.1\nVersion: 0.0.1\n',
    'blank-name': 'Metadata-Version: 2.1\nName: \nVersion: 0.0.1\n',
    'spaces-name': 'Metadata-Version: 2.1\nName:    \nVersion: 0.0.1\n',
    'no-metadata': None,
    'not-utf-8': b'Metadata-Version: 2.1\nName: planted-\xff\nVersion: 0.0.1\n',
}


@dataclass
class Plant:
    kind: str
    files: dict[str, str]
    entry: str
    named: str | None = None          # None: the distribution's own name
    cause: str | None = None          # refused with this cause; None: see `verdict`
    verdict: str = 'refused'          # refused | interrupted | loads
    metadata: str | bytes | None = ''  # '' : the default naming the distribution
    preimport: str | None = None
    extra_eps: list[str] = field(default_factory=list)


def package(m: str, tool: str, *, entry_head: str = '', entry_tail: str = '', tools_head: str = '', tools_tail: str = '',
            tools: str | None = None, name: str | None = None, instructions: str | None = None,
            resources: str = '()', prelude: str = '') -> dict[str, str]:
    """A planted package `m`: its capability, declaring `tool`, and its tools module defining it."""
    text = instructions or repr(f'Planted tools:\n- {tool}: Echo a text back')
    capability = (f'from cluster_mcp.core.capabilities import Capability\n\n{prelude}\n\n'
                  f'CAPABILITY = Capability(name={name or repr(m)}, order=500, tools={tools or repr(m + ".tools")}, '
                  f'instructions={text}, resources={resources})\n')
    return {f'{m}/__init__.py': '',
            f'{m}/capability.py': KINDS + entry_head + '\n' + capability + entry_tail,
            f'{m}/tools.py': KINDS + tools_head + TOOL.format(name=tool) + tools_tail}


def indent(statement: str, by: int) -> str:
    return textwrap.indent(statement, ' ' * by)


def raising(kind: str, when: str) -> Plant:
    statement, cause = RAISED[kind]
    m = f'f4_{kind}_{when}'.replace('-', '_')
    tool = f'{m}_echo'
    spec: dict[str, str] = {}
    if when == 'entry-before':
        spec['entry_head'] = statement + '\n'
    elif when == 'entry-after':
        spec['entry_tail'] = statement + '\n'
    elif when == 'tools-before':
        spec['tools_head'] = statement + '\n'
    elif when == 'tools-after':
        spec['tools_tail'] = statement + '\n'
    elif when == 'tools-imports':
        spec['tools_tail'] = f'import {m}.deeper  # noqa\n'
    elif when == 'declared-tools':
        spec['prelude'] = f'class _Tools(str):\n    def __add__(self, other):\n{indent(statement, 8)}\n'
        spec['tools'] = f'_Tools({m + ".tools"!r})'
    elif when == 'declared-name':
        spec['prelude'] = f'class _Name(str):\n    def __hash__(self):\n{indent(statement, 8)}\n'
        spec['name'] = f'_Name({m!r})'
    elif when == 'declared-instructions':
        spec['prelude'] = f'class _Text(str):\n    def strip(self, *args):\n{indent(statement, 8)}\n'
        spec['instructions'] = f"_Text({f'Planted tools:{chr(10)}- {tool}: Echo a text back'!r})"
    elif when == 'served':
        spec['prelude'] = (f'class _Handler:\n    def __call__(self):\n        return "planted"\n\n'
                           f'    def __getattr__(self, name):\n{indent(statement, 8)}\n')
        spec['resources'] = ("({'uri': 'cluster://f4', 'name': 'f4', 'description': 'F4', 'handler': _Handler(), "
                             "'executor': True},)")
    files = package(m, tool, **spec)
    if when == 'tools-imports':
        files[f'{m}/deeper.py'] = KINDS + statement + '\n'
    if when == 'served' and cause:
        cause = f"its resource 'cluster://f4' cannot be served: {cause}"
    return Plant(f'{kind}@{when}', files, f'cap = {m}.capability:CAPABILITY', cause=cause,
                 verdict='interrupted' if cause is None else 'refused')


def nameless(kind: str) -> Plant:
    m = f'f4_nameless_{kind}'.replace('-', '_')
    value = f'{m}.capability:CAPABILITY'
    cause = ('its distribution metadata cannot be read: UnicodeDecodeError' if kind == 'not-utf-8'
             else 'its distribution metadata has no Name')
    # Its code would exit if it ran: the refusal comes first.
    return Plant(f'nameless-{kind}', package(m, f'{m}_echo', entry_head='sys.exit(9)\n'), f'cap = {value}',
                 named=value, cause=cause, metadata=NAMELESS[kind])


def registering(kind: str, where: str) -> Plant:
    """A registration of `kind` (tool, non-tool) made `where`, outside the tools module."""
    m = f'f4_{kind}_{where}'.replace('-', '_')
    tool = f'{m}_echo'
    stray = f'{m}_stray'
    body = (TOOL if kind == 'tool' else NOT_A_TOOL).format(name=stray)
    files = package(m, tool)
    head = ''
    if where == 'entry-module':
        head = body
    elif where == 'entry-imports':
        files[f'{m}/helper.py'] = body
        head = f'import {m}.helper  # noqa\n'
    elif where == 'entry-imports-tools':
        files[f'{m}/helper.py'] = body
        files[f'{m}/tools.py'] += f'\nimport {m}.helper  # noqa\n'
        head = f'import {m}.tools  # noqa\n'
    elif where == 'entry-imports-a-module-importing-tools':
        files[f'{m}/helper.py'] = body
        files[f'{m}/tools.py'] += f'\nimport {m}.helper  # noqa\n'
        files[f'{m}/glue.py'] = f'import {m}.tools  # noqa\n'
        head = f'import {m}.glue  # noqa\n'
    elif where == 'tools-imports':
        files[f'{m}/helper.py'] = body
        files[f'{m}/tools.py'] += f'\nimport {m}.helper  # noqa\n'
    elif where == 'entry-calls':
        files[f'{m}/helper.py'] = f'def register():\n    import {m}.late  # noqa\n'
        files[f'{m}/late.py'] = body
        head = f'import {m}.helper\n{m}.helper.register()\n'
    files[f'{m}/capability.py'] = head + '\n' + files[f'{m}/capability.py']
    cause = (f"loading it registered ['{stray}'], which are outside {m}.tools" if kind == 'tool'
             else 'loading it registered a function, not a FunctionTool')
    return Plant(f'{kind}-{where}', files, f'cap = {m}.capability:CAPABILITY', cause=cause)


def controls() -> list[Plant]:
    out = []
    m = 'f4_control_entry_imports_tools'
    files = package(m, f'{m}_echo', entry_head=f'import {m}.tools  # noqa\n')
    out.append(Plant('control-entry-imports-tools', files, f'cap = {m}.capability:CAPABILITY', verdict='loads'))
    m = 'f4_control_entry_imports_glue'
    files = package(m, f'{m}_echo', entry_head=f'import {m}.glue  # noqa\n')
    files[f'{m}/glue.py'] = f'import {m}.tools  # noqa\n'
    out.append(Plant('control-entry-imports-a-module-importing-tools', files, f'cap = {m}.capability:CAPABILITY',
                     verdict='loads'))
    m = 'f4_control_tools_is_entry'
    files = package(m, f'{m}_echo', tools=repr(f'{m}.capability'), entry_head=TOOL.format(name=f'{m}_echo'))
    files[f'{m}/tools.py'] = ''
    out.append(Plant('control-tools-module-is-the-entry-point-module', files, f'cap = {m}.capability:CAPABILITY',
                     verdict='loads'))
    m = 'f4_control_preimported'
    out.append(Plant('control-tools-already-imported', package(m, f'{m}_echo'), f'cap = {m}.capability:CAPABILITY',
                     verdict='loads', preimport=f'{m}.tools'))
    return out


def domain() -> list[Plant]:
    plants = [raising(kind, when) for kind, when in itertools.product(RAISED, WHEN)]
    plants += [nameless(kind) for kind in NAMELESS]
    plants += [registering(kind, where) for kind in ('tool', 'non-tool')
               for where in ('entry-module', 'entry-imports', 'entry-imports-tools',
                             'entry-imports-a-module-importing-tools', 'tools-imports', 'entry-calls')]
    return plants + controls()


def planted(root: Path, plant: Plant) -> EntryPoint:
    for name, text in plant.files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    dist = 'f4-' + plant.kind.replace('@', '-at-')
    info = root / f"{dist.replace('-', '_')}-0.0.1.dist-info"
    info.mkdir()
    if plant.metadata == '':
        (info / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: {dist}\nVersion: 0.0.1\n')
    elif plant.metadata is not None:
        (info / 'METADATA').write_bytes(plant.metadata if isinstance(plant.metadata, bytes) else plant.metadata.encode())
    (info / 'entry_points.txt').write_text(f'[{GROUP}]\n{plant.entry}\n')
    if plant.named is None:
        plant.named = dist
    (ep,) = Distribution.at(info).entry_points.select(group=GROUP)
    return ep


def forget(root: Path) -> None:
    for name, module in list(sys.modules.items()):
        if str(getattr(module, '__file__', None) or '').startswith(str(root)):
            del sys.modules[name]


def verdict(plant: Plant, eps: list[EntryPoint]) -> str | None:
    """None when the load did what `plant` requires; otherwise what it did."""
    before = list(TOOL_REGISTRY)
    try:
        loaded = load(eps)
    except CapabilityLoadError as exc:
        message = str(exc)
        if TOOL_REGISTRY != before:
            return f'refused, but left {len(TOOL_REGISTRY) - len(before)} registered'
        if plant.verdict != 'refused':
            return f'refused: {message}'
        want = f'cannot load capability {plant.named}: {plant.cause}'
        if '\n' in message or not message.startswith(want):
            return f'refused as {message!r}, expected {want!r}'
        return None
    except KeyboardInterrupt:
        if TOOL_REGISTRY != before:
            return 'interrupted, but left tools registered'
        return None if plant.verdict == 'interrupted' else 'interrupted'
    except BaseException as exc:  # noqa: BLE001 - every escape is the violation this checks for
        return f'raised {type(exc).__name__}: {exc!r}'
    if plant.verdict != 'loads':
        return f'loaded {[c.distribution for c in loaded]}'
    if not loaded or not loaded[-1].tools:
        return 'loaded without its tool'
    return None


def main() -> int:
    installed()
    members = {ep.name: ep for ep in entry_points(group=GROUP)}
    plants = domain()
    bad: list[str] = []
    reached: dict[str, int] = {}
    for set_name, names in MEMBER_SETS.items():
        for plant in plants:
            with tempfile.TemporaryDirectory(prefix='f4-') as scratch:
                root = Path(scratch)
                sys.path.insert(0, scratch)
                registry = list(TOOL_REGISTRY)
                try:
                    ep = planted(root, plant)
                    if plant.preimport:
                        __import__(plant.preimport)
                    why = verdict(plant, [*(members[n] for n in names), ep])
                finally:
                    sys.path.remove(scratch)
                    forget(root)
                    TOOL_REGISTRY[:] = registry
            if why:
                bad.append(f'{plant.kind} beside {set_name}: {why}')
            else:
                reached[plant.kind] = reached.get(plant.kind, 0) + 1
    unreached = [p.kind for p in plants if reached.get(p.kind) != len(MEMBER_SETS)]
    counts = {v: sum(1 for p in plants if p.verdict == v) for v in ('refused', 'interrupted', 'loads')}
    print(f'F4: {len(plants)} kinds beside {len(MEMBER_SETS)} member sets: {counts["refused"]} refused naming '
          f'their distribution, {counts["interrupted"]} interrupted, {counts["loads"]} controls loaded; '
          f'{len(bad)} violations', file=sys.stderr)
    print(*bad, sep='\n', file=sys.stderr)
    if unreached and not bad:
        print(f'F4: kinds that did not reach their verdict beside every set: {unreached}', file=sys.stderr)
    return 1 if bad or unreached else 0


if __name__ == '__main__':
    sys.exit(main())
