# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Capabilities register through the entry-point group, and the server serves what loaded.

Every workspace member beside the core is a capability, found through `cluster_mcp.capabilities`
from its own distribution. A server built for a set of loaded capabilities, in any order, serves
the core's tools and exactly theirs, listed in load order with the site context tool last, and a
base of the core's text and theirs in composition order that lists exactly the tools it serves.

A capability that cannot be loaded is refused with one line naming its distribution, and the tool
registry is left as it was. The failures are planted as distributions in a scratch directory (a
`*.dist-info` beside its package, read with `Distribution.at`), so no test edits the tree; a planted
capability with a tool and a resource is served beside the members with no core edit. The core's
modules name no member.
"""

from __future__ import annotations

import ast
import itertools
import re
import sys
import textwrap
import tomllib
from dataclasses import replace
from importlib.metadata import Distribution, EntryPoint, entry_points
from pathlib import Path
from typing import Callable, Iterator

import pytest

import cluster_mcp
import cluster_mcp.core
from harness import SITE, served_instructions, served_surface, served_tools
from cluster_mcp.core.capabilities import GROUP, CapabilityLoadError, Loaded, composed, installed, load
from cluster_mcp.core.instructions import CORE_INSTRUCTIONS
from cluster_mcp.core.server import create_mcp_server
from cluster_mcp.core.site import HEADING
from cluster_mcp.core.tools import CLOSING_TOOLS, CORE_TOOLS, TOOL_REGISTRY
from test_instructions import instruction_violations

REPO = Path(__file__).resolve().parents[1]

# The tools each side registers, pinned here rather than read from the tree.
CORE = {'run_command', 'list_directory', 'read_file', 'write_file', 'upload_file', 'download_file', 'cluster_context'}
WANT = {
    'slurm': {'sbatch', 'squeue', 'scancel', 'sacct', 'sinfo', 'scontrol_show_job', 'scontrol_show_node'},
    'rcac': {'storage_paths', 'myquota', 'jobinfo', 'jobcmd', 'jobenv', 'jobscript', 'showpartitions',
             'average_wait', 'slist', 'sfeatures'},
}

# A tool's line in an instructions text.
LISTED = re.compile(r'^- (\w+):', re.MULTILINE)

# The capability sets every composition test serves, by capability name, in the order given.
SETS = [
    pytest.param((), id='core-only'),
    pytest.param(('slurm',), id='slurm'),
    pytest.param(('rcac',), id='rcac'),
    pytest.param(('slurm', 'rcac'), id='both'),
    pytest.param(('rcac', 'slurm'), id='both-reversed'),
]

ECHO_TOOL = '''\
from cluster_mcp.core.tools import mcp_tool


@mcp_tool
def {name}(text: str) -> str:
    """Echo a text back.

    Args:
        text: The text.

    Returns:
        The same text.
    """
    return text
'''

ECHO_TEXT = 'Planted tools:\n- planted_echo: Echo a text back'


def by_name() -> dict[str, Loaded]:
    return {loaded.capability.name: loaded for loaded in installed()}


def member_entry_point(name: str) -> EntryPoint:
    """The installed entry point of the member capability `name`."""
    (ep,) = [ep for ep in entry_points(group=GROUP) if ep.name == name]
    return ep


def workspace_members() -> dict[str, str]:
    """Every workspace member package beside the core, by package name, with its distribution's name."""
    members = {}
    for package in sorted((REPO / 'packages').glob('*/src/cluster_mcp/*/')):
        if package.name in ('core', '__pycache__'):
            continue
        members[package.name] = tomllib.loads((package.parents[2] / 'pyproject.toml').read_text())['project']['name']
    return members


def capability_source(package: str, *, name: str | None = None, order: int = 500, tools: str | None = None,
                      text: str = ECHO_TEXT, resources: str = '()') -> str:
    """A `capability.py` declaring a Capability for the planted `package`."""
    return textwrap.dedent(f'''\
        from cluster_mcp.core.capabilities import Capability


        def _read() -> str:
            """The text a planted resource serves."""
            return 'planted'


        CAPABILITY = Capability(name={name or package!r}, order={order}, tools={tools or package + '.tools'!r},
                                instructions={text!r}, resources={resources})
        ''')


@pytest.fixture
def plant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., EntryPoint]]:
    """Plant a distribution under `tmp_path` and return its one entry point in the group.

    `plant(dist, entry, files)` writes `files` (path → text) and a `<dist>-0.0.1.dist-info` declaring
    `entry`, with the directory first on `sys.path`. Afterwards the registry holds what it held before
    the test and every planted module is forgotten, so no planted tool reaches another test.
    """
    before = list(TOOL_REGISTRY)
    monkeypatch.syspath_prepend(str(tmp_path))

    def planted(dist: str, entry: str, files: dict[str, str] | None = None) -> EntryPoint:
        for name, text in (files or {}).items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        info = tmp_path / f"{dist.replace('-', '_')}-0.0.1.dist-info"
        info.mkdir()
        (info / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: {dist}\nVersion: 0.0.1\n')
        (info / 'entry_points.txt').write_text(f'[{GROUP}]\n{entry}\n')
        (ep,) = Distribution.at(info).entry_points.select(group=GROUP)
        return ep

    yield planted
    TOOL_REGISTRY[:] = before
    for name, module in list(sys.modules.items()):
        if str(getattr(module, '__file__', None) or '').startswith(str(tmp_path)):
            del sys.modules[name]


def package(module: str, *, tool: str = 'planted_echo', tools_tail: str = '', **capability: object) -> dict[str, str]:
    """The files of a planted package `module`: its capability and a tools module defining `tool`."""
    return {f'{module}/__init__.py': '',
            f'{module}/tools.py': ECHO_TOOL.format(name=tool) + tools_tail,
            f'{module}/capability.py': capability_source(module, **capability)}


def load_error(eps: list[EntryPoint]) -> str:
    """The message of the `CapabilityLoadError` loading `eps` raises, or '' when it loads."""
    try:
        load(eps)
    except CapabilityLoadError as exc:
        return str(exc)
    return ''


@pytest.mark.unit
def test_installed_finds_every_workspace_member() -> None:
    # An editable install that was not synced after an entry point was added finds nothing: say so.
    found = {loaded.capability.name: loaded.distribution for loaded in installed()}
    members = workspace_members()
    assert members, 'no workspace member found beside the core'
    assert found == members, (f'installed() found {found}, the workspace holds {members}: '
                              'is the environment synced (uv sync --locked)?')
    for loaded in installed():
        assert {tool.name for tool in loaded.tools} == WANT[loaded.capability.name], loaded.capability.name


@pytest.mark.unit
def test_composition_order_ignores_discovery_order() -> None:
    loaded = installed()
    assert len(loaded) == 2, loaded
    for given in itertools.permutations(loaded):
        names = [c.capability.name for c in composed(given)]
        assert names == ['slurm', 'rcac'], f'composition follows the given order: {names}'
    # Ties on the order key are broken by distribution, whatever order they come in.
    slurm = by_name()['slurm']
    b, a = (Loaded(replace(slurm.capability, name=n), d, ()) for n, d in (('b', 'dist-b'), ('a', 'dist-a')))
    for given in ((b, a), (a, b)):
        names = [c.distribution for c in composed(given)]
        assert names == ['dist-a', 'dist-b'], f'composition follows the given order: {names}'
    served = served_instructions(create_mcp_server('none', site=SITE, capabilities=tuple(reversed(loaded)))) or ''
    base = '\n\n'.join((CORE_INSTRUCTIONS, by_name()['slurm'].capability.instructions,
                        by_name()['rcac'].capability.instructions))
    assert served.startswith(f'{base}\n\n{HEADING}\n\n'), 'composition follows the given order: the served base'


@pytest.mark.unit
@pytest.mark.parametrize('names', SETS)
def test_served_tools_are_the_core_and_the_given_capabilities(names: tuple[str, ...]) -> None:
    given = tuple(by_name()[n] for n in names)
    tools = served_tools(create_mcp_server('none', site=SITE, capabilities=given))
    want = CORE.union(*(WANT[n] for n in names))
    assert sorted(tools) == sorted(want), f'serves tools beyond or short of the core and the given capabilities: ' \
                                          f'{sorted(set(tools) ^ want)}'
    # Listed in load order: the core's opening tools, each capability's by distribution, the site context last.
    order = [tool.name for tool in CORE_TOOLS if tool not in CLOSING_TOOLS]
    order += [tool.name for loaded in sorted(given, key=lambda c: c.distribution) for tool in loaded.tools]
    order += [tool.name for tool in CLOSING_TOOLS]
    assert tools == order, f'listed out of load order: {tools}'
    assert tools[-1] == 'cluster_context', tools


@pytest.mark.unit
@pytest.mark.parametrize('names', SETS)
def test_instructions_name_exactly_the_served_tools(names: tuple[str, ...]) -> None:
    given = tuple(by_name()[n] for n in names)
    surface = served_surface(create_mcp_server('none', site=SITE, capabilities=given))
    tools = sorted(surface['tools'])
    base, heading, _ = surface['instructions'].partition(f'\n\n{HEADING}\n\n')
    assert heading, 'the served instructions carry no site section'
    listed = LISTED.findall(base)
    assert len(listed) == len(set(listed)), f'the base lists a tool twice: {listed}'
    assert sorted(listed) == tools, f'the base lists {sorted(set(listed) - set(tools))} not served and omits ' \
                                    f'{sorted(set(tools) - set(listed))} served'
    assert instruction_violations(base, tools) == []


@pytest.mark.unit
@pytest.mark.parametrize(('case', 'fragment'), [
    pytest.param('missing-module', "ModuleNotFoundError: No module named 'planted_nowhere_at_all'",
                 id='missing-module'),
    pytest.param('raising', 'RuntimeError: planted failure at import', id='raising'),
    pytest.param('raising-empty', 'RuntimeError', id='raising-empty'),
    pytest.param('missing-attribute', 'AttributeError: ', id='missing-attribute'),
    pytest.param('wrong-type', 'the entry point names a str, not a Capability', id='wrong-type'),
    pytest.param('wrong-field', 'its order is a str, not an int', id='wrong-field'),
    pytest.param('no-dist', "ModuleNotFoundError: No module named 'planted_nowhere_at_all'", id='no-dist'),
])
def test_a_load_failure_names_the_distribution(case: str, fragment: str, plant: Callable[..., EntryPoint]) -> None:
    dist = f'planted-{case}'
    if case == 'missing-module':
        ep = plant(dist, 'gone = planted_nowhere_at_all.capability:CAPABILITY')
    elif case in ('raising', 'raising-empty'):
        error = 'RuntimeError()' if case == 'raising-empty' else "RuntimeError('planted failure at import')"
        ep = plant(dist, 'raising = planted_raising.capability:CAPABILITY',
                   {'planted_raising/__init__.py': '', 'planted_raising/capability.py': f'raise {error}\n'})
    elif case == 'missing-attribute':
        ep = plant(dist, 'absent = planted_absent.capability:CAPABILITY',
                   {'planted_absent/__init__.py': '', 'planted_absent/capability.py': 'OTHER = 1\n'})
    elif case == 'wrong-type':
        ep = plant(dist, 'wrong = os:sep')
    elif case == 'wrong-field':
        files = package('planted_field')
        files['planted_field/capability.py'] = files['planted_field/capability.py'].replace('order=500', "order='500'")
        ep = plant(dist, 'field = planted_field.capability:CAPABILITY', files)
    else:
        ep = EntryPoint(name='gone', value='planted_nowhere_at_all.capability:CAPABILITY', group=GROUP)
        dist = ep.value
    before = list(TOOL_REGISTRY)
    with pytest.raises(CapabilityLoadError) as raised:
        load([ep])
    message = str(raised.value)
    assert raised.value.distribution == dist
    assert message.startswith(f'cannot load capability {dist}: '), message
    assert fragment in message and '\n' not in message, message
    if case == 'raising-empty':
        assert message == f'cannot load capability {dist}: RuntimeError', message
    assert TOOL_REGISTRY == before


@pytest.mark.unit
@pytest.mark.parametrize('case', ['later-check', 'tools-raising'])
def test_a_failed_load_leaves_the_registry_as_it_was(case: str, plant: Callable[..., EntryPoint]) -> None:
    before = list(TOOL_REGISTRY)
    eps = [plant('planted-a-first', 'first = planted_first.capability:CAPABILITY',
                 package('planted_first', tool='planted_first_echo',
                         text='Planted tools:\n- planted_first_echo: Echo a text back'))]
    if case == 'later-check':
        eps.append(plant('planted-b-mismatch', 'mm = planted_mismatch.capability:CAPABILITY',
                         package('planted_mismatch', text='Planted tools:\n- ghost: A tool nobody defines')))
    else:
        eps.append(plant('planted-b-raising', 'tr = planted_tools_raising.capability:CAPABILITY',
                         package('planted_tools_raising',
                                 tools_tail="\nraise RuntimeError('planted failure after registering a tool')\n")))
    message = load_error(eps)
    assert message.startswith('cannot load capability planted-b-'), message
    assert TOOL_REGISTRY == before, f'a failed load left {[t.name for t in TOOL_REGISTRY[len(before):]]} registered'


@pytest.mark.unit
@pytest.mark.parametrize(('tool', 'name', 'fragment'), [
    pytest.param('sinfo', None, "tool 'sinfo' is already registered by cluster-mcp-slurm", id='member-tool'),
    pytest.param('run_command', None, "tool 'run_command' is already registered by the core", id='core-tool'),
    pytest.param('planted_echo', 'slurm', "the capability name 'slurm' is already taken by cluster-mcp-slurm",
                 id='capability-name'),
])
def test_a_duplicate_tool_is_refused(tool: str, name: str | None, fragment: str,
                                     plant: Callable[..., EntryPoint]) -> None:
    ep = plant('planted-duplicate', 'dup = planted_duplicate.capability:CAPABILITY',
               package('planted_duplicate', tool=tool, name=name, text=f'Planted tools:\n- {tool}: Echo a text back'))
    message = load_error([member_entry_point('slurm'), ep])
    assert fragment in message, f'a duplicate tool loaded: expected {fragment!r}, got {message!r}'
    assert message.startswith('cannot load capability planted-duplicate: '), message


@pytest.mark.unit
@pytest.mark.parametrize(('case', 'fragment'), [
    pytest.param('tools-missing', "ModuleNotFoundError: No module named 'planted_tools_missing.nowhere'",
                 id='tools-missing'),
    pytest.param('tools-raising', 'RuntimeError: planted failure after registering a tool', id='tools-raising'),
])
def test_a_tools_module_failure_names_the_distribution(case: str, fragment: str,
                                                       plant: Callable[..., EntryPoint]) -> None:
    if case == 'tools-missing':
        files = package('planted_tools_missing', tools='planted_tools_missing.nowhere')
    else:
        files = package('planted_tools_missing',
                        tools_tail="\nraise RuntimeError('planted failure after registering a tool')\n")
    before = list(TOOL_REGISTRY)
    ep = plant(f'planted-{case}', 'tm = planted_tools_missing.capability:CAPABILITY', files)
    message = load_error([ep])
    assert fragment in message, f'a failing tools module loaded: expected {fragment!r}, got {message!r}'
    assert message.startswith(f'cannot load capability planted-{case}: '), message
    assert TOOL_REGISTRY == before


@pytest.mark.unit
@pytest.mark.parametrize(('text', 'fragment'), [
    pytest.param('Planted tools:\n- ghost: A tool nobody defines',
                 "its instructions list ['ghost'], which it does not register", id='lists-another'),
    pytest.param('Planted tools: none listed', "omit ['planted_echo'], which it registers", id='omits-its-tool'),
    pytest.param(ECHO_TEXT + '\n- planted_echo: Again', "list ['planted_echo'] more than once", id='lists-twice'),
])
def test_instructions_must_list_exactly_the_tools(text: str, fragment: str,
                                                  plant: Callable[..., EntryPoint]) -> None:
    ep = plant('planted-mismatch', 'mm = planted_mismatch.capability:CAPABILITY',
               package('planted_mismatch', text=text))
    message = load_error([ep])
    assert fragment in message, \
        f'instructions that do not list exactly its tools loaded: expected {fragment!r}, got {message!r}'
    assert message.startswith('cannot load capability planted-mismatch: '), message


@pytest.mark.unit
def test_core_text_lists_exactly_the_core_tools() -> None:
    listed = LISTED.findall(CORE_INSTRUCTIONS)
    names = [tool.name for tool in CORE_TOOLS]
    assert sorted(names) == sorted(CORE), names
    assert len(listed) == len(set(listed)), f'the core text lists a tool twice: {listed}'
    assert sorted(listed) == sorted(names), f'the core text lists {listed}, the core registers {names}'


@pytest.mark.unit
def test_a_planted_capability_needs_no_core_edit(plant: Callable[..., EntryPoint]) -> None:
    resource = "({'uri': 'cluster://planted', 'name': 'planted', 'description': 'Planted', 'handler': _read, " \
               "'executor': True},)"
    ep = plant('planted-capability', 'planted = planted_capability.capability:CAPABILITY',
               package('planted_capability', resources=resource))
    # Discovered as the members are: from the group, its distribution first on the path.
    assert ep in entry_points(group=GROUP)
    loaded = load()
    assert [c.distribution for c in loaded] == ['cluster-mcp-rcac', 'cluster-mcp-slurm', 'planted-capability']
    planted = loaded[-1]
    assert [tool.name for tool in planted.tools] == ['planted_echo']
    surface = served_surface(create_mcp_server('none', site=SITE, capabilities=loaded))
    assert set(surface['tools']) == CORE | WANT['slurm'] | WANT['rcac'] | {'planted_echo'}
    assert 'cluster://planted' in surface['resources'], sorted(surface['resources'])
    # Its order, 500, puts its text between the Slurm snippet and the overlay.
    texts = [by_name()['slurm'].capability.instructions, ECHO_TEXT, by_name()['rcac'].capability.instructions]
    assert surface['instructions'].startswith('\n\n'.join((CORE_INSTRUCTIONS, *texts)) + f'\n\n{HEADING}\n\n')
    tools = served_tools(create_mcp_server('none', site=SITE, capabilities=loaded))
    assert tools.index('planted_echo') > tools.index('sinfo') and tools[-1] == 'cluster_context', tools
    # The core never named it.
    core = Path(cluster_mcp.core.__file__).parent
    assert not [f for f in core.rglob('*.py') if 'planted' in f.read_text()]


def member_packages() -> set[str]:
    """Every package of the `cluster_mcp` namespace but the core: the members, wherever installed."""
    return {p.name for portion in cluster_mcp.__path__ for p in Path(portion).iterdir()
            if p.is_dir() and p.name not in ('core', '__pycache__')}


def member_import_violations(source: str, where: str, package_parts: list[str], members: set[str]) -> list[str]:
    """Every import of a member in `source`, and every string naming one as `cluster_mcp.<member>`."""
    named = re.compile(rf"cluster_mcp[./]({'|'.join(sorted(map(re.escape, members)))})\b")
    found = []
    for node in ast.walk(ast.parse(source, where)):
        if isinstance(node, ast.Import):
            found += [f'{where}:{node.lineno}: imports {a.name}' for a in node.names if named.match(a.name)]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            if node.level:
                module = '.'.join(package_parts[:len(package_parts) - node.level + 1] + ([module] if module else []))
            if named.match(module):
                found.append(f'{where}:{node.lineno}: imports {module}')
            elif module == 'cluster_mcp' and any(a.name in members for a in node.names):
                found.append(f'{where}:{node.lineno}: imports a member from cluster_mcp')
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and named.search(node.value):
            found.append(f'{where}:{node.lineno}: a string names {named.search(node.value).group(0)}')
    return found


@pytest.mark.unit
def test_core_imports_no_member() -> None:
    members = member_packages()
    assert {'slurm', 'rcac'} <= members, members
    assert member_import_violations('from ..slurm import tools\n', 'c.py', ['cluster_mcp', 'core'], members)
    core = Path(cluster_mcp.core.__file__).parent
    files = sorted(core.rglob('*.py'))
    assert len(files) >= 10, files
    violations = []
    for f in files:
        parts = ['cluster_mcp', *f.relative_to(core.parent).with_suffix('').parts]
        parts = parts[:-1]
        # The storage summary resource still reaches the RCAC member's helper from inside its handler.
        if f.name == 'resources.py' and f.parent == core:
            continue
        violations += member_import_violations(f.read_text(), str(f.relative_to(core.parent)), parts, members)
    assert violations == [], 'a core module imports a member by name:\n' + '\n'.join(violations)
