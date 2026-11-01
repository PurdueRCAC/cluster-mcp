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

The core serves its two context URIs; `cluster://storage` and its `rcac://storage` alias are the RCAC
capability's, served exactly when it is given, and every alias is listed after every primary URI, a
copy of its target but for the URI. A capability resource must need an executor (it is never open),
must be well formed, and must not take a URI the core or an earlier capability serves.

Whatever a capability declares fails at the load or not at all: every kind of tool or resource a
server would refuse while it is assembled, or would let replace another, is refused at load beside
each member set, and a capability that loads is served whole. The resource kinds' controls show
FastMCP itself refusing each one, or keying the two URIs alike.

The commands a capability needs on the cluster are declared as data: a tuple of plain command names,
exactly those types. Each malformed declaration (another container, a name that is not a plain file
name, one declared twice, a subclass of `tuple` or `str`) is refused at load beside each member set;
a well-formed one loads with no core edit, kept as declared; the members declare theirs.

What an entry point names is exactly a `Capability`: a subclass is refused at load beside each member
set, whichever field its code would read in place of the record (`SUBCLASS_READS`), or none. Every value
in it the core or FastMCP reads is exactly a built-in type too: a value of a type of its own at any site
(`EXACT_SITES`: each field, a command, a resource entry, a key of one, each value of one but its
handler), whose every operation would exit once its record is built, is refused at load for its type
before any of its operations runs, beside each member set, and so is a distribution whose `Name` is a
`str` of a type of its own, so no read of a loaded record runs capability code.
"""

from __future__ import annotations

import ast
import itertools
import re
import sys
import textwrap
import tomllib
from dataclasses import dataclass, fields, replace
from importlib.metadata import Distribution, EntryPoint, entry_points
from pathlib import Path
from typing import Callable, Iterator

import pytest

import cluster_mcp
import cluster_mcp.core
import cluster_mcp.core.capabilities
from harness import SITE, FastMCP, served_instructions, served_surface, served_tools
from cluster_mcp.core.capabilities import GROUP, Capability, CapabilityLoadError, Loaded, composed, installed, load
from cluster_mcp.core.instructions import CORE_INSTRUCTIONS
from cluster_mcp.core.resources import OPEN_RESOURCES, RESOURCE_REGISTRY
from cluster_mcp.core.server import create_mcp_server
from cluster_mcp.core.site import HEADING
from cluster_mcp.core.tools import CLOSING_TOOLS, CORE_TOOLS, TOOL_REGISTRY

REPO = Path(__file__).resolve().parents[1]

# The tools each side registers, pinned here rather than read from the tree.
CORE = {'run_command', 'list_directory', 'read_file', 'write_file', 'upload_file', 'download_file', 'cluster_context'}
WANT = {
    'slurm': {'sbatch', 'squeue', 'scancel', 'sacct', 'sinfo', 'scontrol_show_job', 'scontrol_show_node'},
    'rcac': {'storage_paths', 'myquota', 'jobinfo', 'jobcmd', 'jobenv', 'jobscript', 'showpartitions',
             'average_wait', 'slist', 'sfeatures'},
}

# The resources each side serves, primary URI first, then its deprecated alias.
CONTEXT_URIS = ('cluster://context', 'rcac://context')
STORAGE_URIS = ('cluster://storage', 'rcac://storage')

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


# Resource handlers a planted capability may name beside `_read`: one that takes a parameter, and one
# written as a method, its first parameter `self`.
HANDLERS = '''

def _read_one(path: str) -> str:
    """The text a planted resource serves for `path`."""
    return path


def _read_self(self) -> str:
    """A handler written as a method."""
    return 'planted'
'''


def capability_source(package: str, *, name: str | None = None, order: int = 500, tools: str | None = None,
                      text: str = ECHO_TEXT, resources: str = '()') -> str:
    """A `capability.py` declaring a Capability for the planted `package`."""
    return textwrap.dedent('''\
        from cluster_mcp.core.capabilities import Capability


        def _read() -> str:
            """The text a planted resource serves."""
            return 'planted'
        ''') + HANDLERS + textwrap.dedent(f'''\


        CAPABILITY = Capability(name={name or package!r}, order={order}, tools={tools or package + '.tools'!r},
                                instructions={text!r}, resources={resources})
        ''')


@pytest.fixture
def plant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., EntryPoint]]:
    """Plant a distribution under `tmp_path` and return its entry point in the group.

    `plant(dist, entry, files)` writes `files` (path → text) and a `<dist>-0.0.1.dist-info` declaring
    `entry` (or several, one per line, returned as a tuple), with the directory first on `sys.path`;
    `metadata` (text or bytes) replaces the one its `METADATA` would hold. Afterwards the registry holds
    what it held before the test and every planted module is forgotten, so no planted tool reaches
    another test.
    """
    before = list(TOOL_REGISTRY)
    monkeypatch.syspath_prepend(str(tmp_path))

    def planted(dist: str, entry: str, files: dict[str, str] | None = None,
                metadata: str | bytes | None = None) -> EntryPoint | tuple[EntryPoint, ...]:
        for name, text in (files or {}).items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        info = tmp_path / f"{dist.replace('-', '_')}-0.0.1.dist-info"
        info.mkdir()
        write_metadata(info, dist, metadata)
        (info / 'entry_points.txt').write_text(f'[{GROUP}]\n{entry}\n')
        eps = tuple(Distribution.at(info).entry_points.select(group=GROUP))
        return eps[0] if len(eps) == 1 else eps

    yield planted
    TOOL_REGISTRY[:] = before
    for name, module in list(sys.modules.items()):
        if str(getattr(module, '__file__', None) or '').startswith(str(tmp_path)):
            del sys.modules[name]


def write_metadata(info: Path, dist: str, metadata: str | bytes | None = None) -> None:
    """Write the `METADATA` of the planted dist-info `info`: naming `dist`, or `metadata` as given."""
    text = f'Metadata-Version: 2.1\nName: {dist}\nVersion: 0.0.1\n' if metadata is None else metadata
    (info / 'METADATA').write_bytes(text if isinstance(text, bytes) else text.encode())


def package(module: str, *, tool: str = 'planted_echo', tools_tail: str = '', **capability: object) -> dict[str, str]:
    """The files of a planted package `module`: its capability and a tools module defining `tool`."""
    return {f'{module}/__init__.py': '',
            f'{module}/tools.py': ECHO_TOOL.format(name=tool) + tools_tail,
            f'{module}/capability.py': capability_source(module, **capability)}


def load_error(eps: list[EntryPoint]) -> str:
    """The message of the `CapabilityLoadError` loading `eps` raises, or '' when it loads.

    Anything else it raises or exits with fails the test: a load refuses only with a
    `CapabilityLoadError`.
    """
    try:
        load(eps)
    except CapabilityLoadError as exc:
        return str(exc)
    except KeyboardInterrupt:
        raise
    except BaseException as exc:
        # Its repr, not its text: a capability's exception may raise, exit or interrupt when asked for that.
        pytest.fail(f'the load raised {type(exc).__name__}, not a CapabilityLoadError naming a capability: {exc!r}')
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
    # Imported here: `test_instructions` loads the installed capabilities when it is imported, and the
    # tests of a load that fails must still be collected.
    from test_instructions import instruction_violations
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
        violations += member_import_violations(f.read_text(), str(f.relative_to(core.parent)), parts, members)
    assert violations == [], 'a core module imports a member by name:\n' + '\n'.join(violations)


def resource(at: str = 'cluster://planted', **fields: str | None) -> str:
    """A planted resource entry's source at the URI `at`; `fields` replace its values as source text, None drops one."""
    entry = {'uri': repr(at), 'name': "'planted'", 'description': "'Planted'", 'handler': '_read',
             'executor': 'True', **fields}
    return '{' + ', '.join(f'{key!r}: {value}' for key, value in entry.items() if value is not None) + '}'


@pytest.mark.unit
def test_storage_is_served_only_with_the_rcac_capability() -> None:
    # The core's registry is its context entry and that entry's alias; the storage resource and its
    # alias are the RCAC capability's own.
    assert [entry['uri'] for entry in RESOURCE_REGISTRY] == list(CONTEXT_URIS), RESOURCE_REGISTRY
    assert OPEN_RESOURCES == frozenset(CONTEXT_URIS), sorted(OPEN_RESOURCES)
    assert [entry['uri'] for entry in by_name()['rcac'].capability.resources] == list(STORAGE_URIS)
    assert by_name()['slurm'].capability.resources == ()
    violations = []
    for names in (param.values[0] for param in SETS):
        given = tuple(by_name()[n] for n in names)
        served = list(served_surface(create_mcp_server('none', site=SITE, capabilities=given))['resources'])
        want = [CONTEXT_URIS[0], *STORAGE_URIS[:1], CONTEXT_URIS[1], *STORAGE_URIS[1:]] if 'rcac' in names \
            else list(CONTEXT_URIS)
        if served != want:
            violations.append(f"{'+'.join(names) or 'core only'}: serves resources {served}, expected {want}")
    assert violations == [], 'served beyond or short of the core\'s and the given capabilities\' resources:\n' \
        + '\n'.join(violations)


@pytest.mark.unit
@pytest.mark.parametrize('names', SETS)
def test_aliases_follow_every_primary_uri(names: tuple[str, ...]) -> None:
    # Every deprecated `rcac://` alias is listed after every `cluster://` URI, in the same order, and
    # serves what its target serves but for its URI; each capability alias shares its target's handler.
    given = tuple(by_name()[n] for n in names)
    served = served_surface(create_mcp_server('none', site=SITE, capabilities=given))['resources']
    uris = list(served)
    primaries = [uri for uri in uris if uri.startswith('cluster://')]
    aliases = [uri for uri in uris if uri.startswith('rcac://')]
    assert primaries and uris == primaries + aliases, f'an alias is listed before a primary URI: {uris}'
    assert aliases == [uri.replace('cluster://', 'rcac://', 1) for uri in primaries], \
        f'the aliases {aliases} do not follow the primary URIs {primaries} one for one'
    for target in primaries:
        alias = target.replace('cluster://', 'rcac://', 1)
        assert served[alias] == served[target], \
            f'the alias {alias!r} serves {served[alias]}, its target {served[target]}'
    for loaded in given:
        entries = {entry['uri']: entry for entry in loaded.capability.resources}
        for uri, entry in entries.items():
            if uri.startswith('rcac://'):
                target = entries[uri.replace('rcac://', 'cluster://', 1)]
                assert entry['handler'] is target['handler'] and {**entry, 'uri': target['uri']} == target, \
                    f'the alias {uri!r} of {loaded.distribution} is not a copy of its target but for its URI'


@pytest.mark.unit
@pytest.mark.parametrize('executor', [
    pytest.param('False', id='false'),
    pytest.param(None, id='missing'),
    pytest.param('1', id='truthy'),
])
def test_a_capability_resource_must_need_an_executor(executor: str | None, plant: Callable[..., EntryPoint]) -> None:
    # A capability resource is never in the core's open set, so one claiming to run nothing would be
    # silently gated; it is refused instead, naming its distribution.
    ep = plant('planted-open-resource', 'open = planted_open.capability:CAPABILITY',
               package('planted_open', resources=f'({resource(executor=executor)},)'))
    before = list(TOOL_REGISTRY)
    message = load_error([ep])
    assert 'a capability resource is never open' in message, f'an open resource loaded: got {message!r}'
    assert message.startswith("cannot load capability planted-open-resource: its resource 'cluster://planted' "
                              "has executor "), message
    assert TOOL_REGISTRY == before


@pytest.mark.unit
@pytest.mark.parametrize(('uri', 'twice', 'fragment'), [
    pytest.param('cluster://context', False, "resource 'cluster://context' is already registered by the core",
                 id='core'),
    pytest.param('rcac://context', False, "resource 'rcac://context' is already registered by the core",
                 id='core-alias'),
    pytest.param('cluster://storage', False, "resource 'cluster://storage' is already registered by cluster-mcp-rcac",
                 id='member'),
    pytest.param('rcac://storage', False, "resource 'rcac://storage' is already registered by cluster-mcp-rcac",
                 id='member-alias'),
    pytest.param('cluster://planted', True, "resource 'cluster://planted' is declared twice", id='twice'),
])
def test_a_duplicate_resource_uri_is_refused(uri: str, twice: bool, fragment: str,
                                             plant: Callable[..., EntryPoint]) -> None:
    entries = (resource(uri),) * (2 if twice else 1)
    ep = plant('planted-uri', 'uri = planted_uri.capability:CAPABILITY',
               package('planted_uri', resources='(' + ', '.join(entries) + ',)'))
    before = list(TOOL_REGISTRY)
    message = load_error([member_entry_point('rcac'), ep])
    assert fragment in message, f'a duplicate resource URI loaded: expected {fragment!r}, got {message!r}'
    assert message.startswith('cannot load capability planted-uri: '), message
    assert TOOL_REGISTRY == before


@pytest.mark.unit
@pytest.mark.parametrize(('entry', 'fragment'), [
    pytest.param("'cluster://planted'", 'one of its resources is a str, not a dict', id='not-a-dict'),
    pytest.param(resource(uri='42'), 'has a int uri, not a str', id='uri'),
    pytest.param(resource(name=None), "its resource 'cluster://planted' has a NoneType name, not a str", id='name'),
    pytest.param(resource(description='b"Planted"'), "has a bytes description, not a str", id='description'),
    pytest.param(resource(handler="'_read'"), "the handler of its resource 'cluster://planted' is not callable",
                 id='handler'),
])
def test_a_capability_resource_is_validated(entry: str, fragment: str, plant: Callable[..., EntryPoint]) -> None:
    ep = plant('planted-bad-resource', 'bad = planted_bad.capability:CAPABILITY',
               package('planted_bad', resources=f'({entry},)'))
    before = list(TOOL_REGISTRY)
    message = load_error([ep])
    assert fragment in message, f'a malformed resource loaded: expected {fragment!r}, got {message!r}'
    assert message.startswith('cannot load capability planted-bad-resource: '), message
    assert TOOL_REGISTRY == before


# A planted tools module that appends something other than a tool to the registry, and one whose tool
# claims no module (as a tool built at run time can).
NOT_A_TOOL = '''

from cluster_mcp.core.tools import TOOL_REGISTRY


def planted_plain(text: str) -> str:
    return text


TOOL_REGISTRY.append(planted_plain)
'''
NO_MODULE = '\nplanted_echo.fn.__module__ = None\n'

# Every kind of contribution a server built from the loaded capabilities would refuse, or would let
# replace another, while it is assembled: each as a planted capability's resources (or its tools
# module's tail), with the cause its refusal must carry. The load decides each one, so none can fail
# later on another path (after the mode ladder, an SSH connect, or with no answer on stdio).
REJECTED: dict[str, dict[str, str]] = {
    'resource-not-a-url': {
        'resources': f"({resource('planted storage')},)",
        'cause': "its resource 'planted storage' cannot be served: ValidationError: ",
    },
    'resource-handler-takes-a-parameter': {
        'resources': f"({resource(handler='_read_one')},)",
        'cause': "its resource 'cluster://planted' cannot be served: "
                 'ValueError: URI template must contain at least one parameter',
    },
    'resource-template-mismatch': {
        'resources': f"({resource('cluster://planted/{name}', handler='_read_one')},)",
        'cause': "its resource 'cluster://planted/{name}' cannot be served: ValueError: Required function "
                 "arguments {'path'} must be a subset of the URI path parameters {'name'}",
    },
    'resource-handler-is-a-method': {
        'resources': f"({resource(handler='_read_self')},)",
        'cause': "its resource 'cluster://planted' cannot be served: TypeError: The function '_read_self' has "
                 "'self' as its first parameter",
    },
    'resource-handler-takes-no-metadata': {
        'resources': f"({resource(handler='print')},)",
        'cause': "its resource 'cluster://planted' cannot be served: AttributeError: 'builtin_function_or_method' "
                 "object has no attribute '__fastmcp__'",
    },
    'resource-uri-collides': {
        'resources': f"({resource('cluster://planted/a b')}, {resource('cluster://planted/a%20b')})",
        'cause': "its resource 'cluster://planted/a%20b' cannot be served: ValueError: Component already exists: "
                 'resource:cluster://planted/a%20b',
    },
    'resource-uri-collides-with-the-core': {
        'resources': f"({resource('CLUSTER://context')},)",
        'cause': "its resource 'CLUSTER://context' cannot be served: ValueError: Component already exists: "
                 'resource:cluster://context',
    },
    'tool-not-a-tool': {
        'tools_tail': NOT_A_TOOL,
        'cause': 'loading it registered a function, not a FunctionTool',
    },
    'tool-without-a-module': {
        'tools_tail': NO_MODULE,
        'cause': "AttributeError: 'NoneType' object has no attribute 'startswith'",
    },
}

# The member sets every refusal is loaded beside: the core alone, each member alone, and both.
MEMBER_SETS = [
    pytest.param((), id='core-only'),
    pytest.param(('slurm',), id='slurm'),
    pytest.param(('rcac',), id='rcac'),
    pytest.param(('rcac', 'slurm'), id='both'),
]


def rejected_package(kind: str) -> tuple[str, str, dict[str, str]]:
    """The planted distribution of the `REJECTED` kind: its name, its entry point line and its files."""
    module = 'planted_' + kind.replace('-', '_')
    case = REJECTED[kind]
    files = package(module, tools_tail=case.get('tools_tail', ''), resources=case.get('resources', '()'))
    return f'planted-{kind}', f'rejected = {module}.capability:CAPABILITY', files


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('kind', list(REJECTED))
def test_what_a_server_would_refuse_is_refused_at_load(kind: str, names: tuple[str, ...],
                                                      plant: Callable[..., EntryPoint]) -> None:
    dist, entry, files = rejected_package(kind)
    ep = plant(dist, entry, files)
    before = list(TOOL_REGISTRY)
    message = load_error([*(member_entry_point(n) for n in names), ep])
    cause = REJECTED[kind]['cause']
    assert message.startswith(f'cannot load capability {dist}: ') and cause in message, \
        f'a contribution the server would refuse loaded: expected {cause!r}, got {message!r}'
    assert '\n' not in message, f'the refusal is not one line: {message!r}'
    assert TOOL_REGISTRY == before, f'a refused load left {[t for t in TOOL_REGISTRY[len(before):]]} registered'


@pytest.mark.unit
@pytest.mark.parametrize('kind', [kind for kind in REJECTED if kind.startswith('resource-')
                                  and not kind.startswith('resource-uri-collides')])
def test_each_refused_resource_is_one_fastmcp_refuses(kind: str) -> None:
    # The control: registered on a bare server, as every server registers a resource, each planted
    # resource of these kinds raises. A FastMCP that accepted one would make its refusal a policy of
    # the load's own, which the row above must then say.
    namespace: dict[str, object] = {}
    exec(capability_source('planted_control').split('\n\nCAPABILITY = ')[0], namespace)
    entries = eval(REJECTED[kind]['resources'], namespace)
    server = FastMCP(name='control')
    with pytest.raises(Exception):
        for entry in entries:
            server.resource(entry['uri'], name=entry['name'], description=entry['description'])(entry['handler'])


@pytest.mark.unit
@pytest.mark.parametrize('kind', ['resource-uri-collides', 'resource-uri-collides-with-the-core'])
def test_a_colliding_uri_would_be_replaced_silently(kind: str) -> None:
    # The control for the two collisions: a server as `create_mcp_server` builds one keeps a single
    # component for both URIs, so without the load's refusal one resource would replace the other.
    namespace: dict[str, object] = {}
    exec(capability_source('planted_control').split('\n\nCAPABILITY = ')[0], namespace)
    entries = list(eval(REJECTED[kind]['resources'], namespace))
    if kind.endswith('with-the-core'):
        entries = [RESOURCE_REGISTRY[0], *entries]
    server = FastMCP(name='control')
    for entry in entries:
        server.resource(entry['uri'], name=entry['name'], description=entry['description'])(entry['handler'])
    served = served_surface(server)['resources']
    assert len(served) == 1, f'the two URIs are served apart: {sorted(served)}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_uri_colliding_with_an_earlier_capability_is_refused(names: tuple[str, ...],
                                                                plant: Callable[..., EntryPoint]) -> None:
    first = plant('planted-a-first', 'first = planted_first.capability:CAPABILITY',
                  package('planted_first', tool='planted_first_echo', resources=f"({resource('cluster://planted/a b')},)",
                          text='Planted tools:\n- planted_first_echo: Echo a text back'))
    second = plant('planted-b-second', 'second = planted_second.capability:CAPABILITY',
                   package('planted_second', resources=f"({resource('cluster://planted/a%20b')},)"))
    message = load_error([*(member_entry_point(n) for n in names), first, second])
    assert message.startswith("cannot load capability planted-b-second: its resource 'cluster://planted/a%20b' "
                              'cannot be served: ValueError: Component already exists'), \
        f'a URI one capability already serves, as FastMCP keys it, loaded: got {message!r}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_what_loads_is_served_whole(names: tuple[str, ...], plant: Callable[..., EntryPoint]) -> None:
    # The other half of the property: a capability the load accepts is served by a server built from
    # it, every declared tool and resource, each under its own URI.
    resources = ', '.join(resource(uri) for uri in ('cluster://planted', 'rcac://planted', 'cluster://planted/a b'))
    ep = plant('planted-capability', 'planted = planted_capability.capability:CAPABILITY',
               package('planted_capability', resources=f'({resources},)'))
    loaded = load([*(member_entry_point(n) for n in names), ep])
    surface = served_surface(create_mcp_server('none', site=SITE, capabilities=loaded))
    want = {*CONTEXT_URIS, 'cluster://planted', 'rcac://planted', 'cluster://planted/a%20b'}
    if 'rcac' in names:
        want |= set(STORAGE_URIS)
    assert set(surface['resources']) == want, \
        f'a capability that loaded is not served whole: resources {sorted(surface["resources"])}, expected {sorted(want)}'
    tools = CORE.union(*(WANT[n] for n in names), {'planted_echo'})
    assert set(surface['tools']) == tools, \
        f'a capability that loaded is not served whole: tools {sorted(surface["tools"])}, expected {sorted(tools)}'


# Every refusal the load makes, and every way it attributes a tool, beside each member set: each row
# asserts the whole message, so a refusal that still happens, but for another reason, is caught.

def members(names: tuple[str, ...]) -> list[EntryPoint]:
    return [member_entry_point(n) for n in names]


def pair(plant: Callable[..., EntryPoint], first: dict[str, str], second: dict[str, str]) -> list[EntryPoint]:
    """Two planted capabilities, `planted-a-first` then `planted-b-second`, from the files of each."""
    return [plant('planted-a-first', 'first = planted_first.capability:CAPABILITY', first),
            plant('planted-b-second', 'second = planted_second.capability:CAPABILITY', second)]


def echo_text(tool: str) -> str:
    return f'Planted tools:\n- {tool}: Echo a text back'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_tool_below_the_tools_module_is_attributed_to_it(names: tuple[str, ...],
                                                         plant: Callable[..., EntryPoint]) -> None:
    files = {'planted_deep/__init__.py': '',
             'planted_deep/tools/__init__.py': 'from planted_deep.tools import more  # noqa: F401\n',
             'planted_deep/tools/more.py': ECHO_TOOL.format(name='planted_deep_echo'),
             'planted_deep/capability.py': capability_source('planted_deep', text=echo_text('planted_deep_echo'))}
    ep = plant('planted-deep', 'deep = planted_deep.capability:CAPABILITY', files)
    try:
        loaded = load([*members(names), ep])
    except CapabilityLoadError as exc:
        pytest.fail(f'a tool below the tools module was refused as outside it: {exc}')
    assert [tool.name for tool in loaded[-1].tools] == ['planted_deep_echo'], loaded[-1].tools


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_tool_outside_the_tools_module_is_refused(names: tuple[str, ...], plant: Callable[..., EntryPoint]) -> None:
    # `planted_sib.toolsmith` shares the tools module's name as a prefix but is not below it.
    files = {'planted_sib/__init__.py': '',
             'planted_sib/tools.py': 'import planted_sib.toolsmith  # noqa: F401\n' + ECHO_TOOL.format(name='planted_echo'),
             'planted_sib/toolsmith.py': ECHO_TOOL.format(name='planted_smith'),
             'planted_sib/capability.py': capability_source('planted_sib')}
    ep = plant('planted-sibling', 'sib = planted_sib.capability:CAPABILITY', files)
    message = load_error([*members(names), ep])
    want = ("cannot load capability planted-sibling: loading it registered ['planted_smith'], which are outside "
            'planted_sib.tools')
    assert message == want, f'a tool outside the tools module loaded: expected {want!r}, got {message!r}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_tool_registered_twice_by_one_capability_is_refused(names: tuple[str, ...],
                                                              plant: Callable[..., EntryPoint]) -> None:
    files = {'planted_twice/__init__.py': '',
             'planted_twice/tools/__init__.py': ECHO_TOOL.format(name='planted_echo')
             + '\n\nfrom planted_twice.tools import again  # noqa: E402, F401\n',
             'planted_twice/tools/again.py': ECHO_TOOL.format(name='planted_echo'),
             'planted_twice/capability.py': capability_source('planted_twice')}
    ep = plant('planted-twice', 'twice = planted_twice.capability:CAPABILITY', files)
    message = load_error([*members(names), ep])
    want = "cannot load capability planted-twice: tool 'planted_echo' is registered twice by planted_twice.tools"
    assert message == want, f'a tool registered twice was not refused as such: expected {want!r}, got {message!r}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('case', ['core', 'earlier'])
def test_a_tool_name_already_taken_is_refused(case: str, names: tuple[str, ...],
                                              plant: Callable[..., EntryPoint]) -> None:
    if case == 'core':
        eps = [plant('planted-b-second', 'second = planted_second.capability:CAPABILITY',
                     package('planted_second', tool='run_command', text=echo_text('run_command')))]
        want = "cannot load capability planted-b-second: tool 'run_command' is already registered by the core"
    else:
        eps = pair(plant, package('planted_first', tool='planted_shared', text=echo_text('planted_shared')),
                   package('planted_second', tool='planted_shared', text=echo_text('planted_shared')))
        want = "cannot load capability planted-b-second: tool 'planted_shared' is already registered by planted-a-first"
    message = load_error([*members(names), *eps])
    assert message == want, f'a duplicate tool loaded: expected {want!r}, got {message!r}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_capability_name_already_taken_is_refused(names: tuple[str, ...], plant: Callable[..., EntryPoint]) -> None:
    eps = pair(plant, package('planted_first', tool='planted_first_echo', name='planted_same',
                              text=echo_text('planted_first_echo')),
               package('planted_second', name='planted_same'))
    message = load_error([*members(names), *eps])
    want = "cannot load capability planted-b-second: the capability name 'planted_same' is already taken by planted-a-first"
    assert message == want, f'a duplicate capability name loaded: expected {want!r}, got {message!r}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('case', ['core', 'core-alias', 'twice', 'earlier'])
def test_a_resource_uri_already_taken_is_refused(case: str, names: tuple[str, ...],
                                                 plant: Callable[..., EntryPoint]) -> None:
    if case == 'earlier':
        eps = pair(plant, package('planted_first', tool='planted_first_echo', text=echo_text('planted_first_echo'),
                                  resources=f'({resource()},)'),
                   package('planted_second', resources=f'({resource()},)'))
        want = "cannot load capability planted-b-second: resource 'cluster://planted' is already registered by planted-a-first"
    else:
        uri = {'core': 'cluster://context', 'core-alias': 'rcac://context', 'twice': 'cluster://planted'}[case]
        entries = (resource(uri),) * (2 if case == 'twice' else 1)
        eps = [plant('planted-b-second', 'second = planted_second.capability:CAPABILITY',
                     package('planted_second', resources='(' + ', '.join(entries) + ',)'))]
        why = 'is declared twice' if case == 'twice' else 'is already registered by the core'
        want = f'cannot load capability planted-b-second: resource {uri!r} {why}'
    message = load_error([*members(names), *eps])
    assert message == want, f'a duplicate resource URI loaded: expected {want!r}, got {message!r}'


# A planted capability whose `capability.py` is edited from the default (`old` → `new`, source text),
# and the cause its refusal must carry.
MALFORMED = {
    'not-a-capability': (None, None, 'the entry point names a str, not a Capability'),
    'name-not-a-str': ("name='planted_field'", 'name=1', 'its name is a int, not a str'),
    'tools-not-a-str': ("tools='planted_field.tools'", 'tools=42', 'its tools is a int, not a str'),
    'instructions-not-a-str': (f'instructions={ECHO_TEXT!r}', 'instructions=None',
                               'its instructions is a NoneType, not a str'),
    'resources-not-a-tuple': ('resources=()', 'resources=[]', 'its resources is a list, not a tuple'),
    'order-not-an-int': ('order=500', "order='500'", 'its order is a str, not an int'),
    'order-a-bool': ('order=500', 'order=True', 'its order is a bool, not an int'),
    'name-empty': ("name='planted_field'", "name=''", 'its name is empty'),
    'instructions-blank': (f'instructions={ECHO_TEXT!r}', "instructions=' \\n '", 'its instructions are empty'),
    'resource-not-a-dict': ('resources=()', "resources=('cluster://planted',)",
                            'one of its resources is a str, not a dict'),
    'resource-uri-not-a-str': ('resources=()', f"resources=({resource(uri='42')},)",
                               'one of its resources has a int uri, not a str'),
    'resource-name-not-a-str': ('resources=()', f'resources=({resource(name=None)},)',
                                "its resource 'cluster://planted' has a NoneType name, not a str"),
    'resource-description-not-a-str': ('resources=()', f"resources=({resource(description='b\"Planted\"')},)",
                                       "its resource 'cluster://planted' has a bytes description, not a str"),
    'resource-handler-not-callable': ('resources=()', f"resources=({resource(handler=repr('_read'))},)",
                                      "the handler of its resource 'cluster://planted' is not callable"),
    'resource-open': ('resources=()', f"resources=({resource(executor='False')},)",
                      "its resource 'cluster://planted' has executor False, not True: a capability resource is never open"),
    'resource-open-truthy': ('resources=()', f"resources=({resource(executor='1')},)",
                             "its resource 'cluster://planted' has executor 1, not True: a capability resource is never open"),
    'resource-open-unmarked': ('resources=()', f"resources=({resource(executor=None)},)",
                               "its resource 'cluster://planted' has executor None, not True: a capability resource is "
                               'never open'),
}


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('case', list(MALFORMED))
def test_a_malformed_capability_is_refused_as_such(case: str, names: tuple[str, ...],
                                                   plant: Callable[..., EntryPoint]) -> None:
    old, new, cause = MALFORMED[case]
    if old is None:
        ep = plant('planted-field', 'wrong = os:sep')
    else:
        files = package('planted_field')
        source = files['planted_field/capability.py']
        assert source.count(old) == 1, f'the planted source no longer holds {old!r}'
        files['planted_field/capability.py'] = source.replace(old, new)
        ep = plant('planted-field', 'field = planted_field.capability:CAPABILITY', files)
    message = load_error([*members(names), ep])
    want = f'cannot load capability planted-field: {cause}'
    label = 'an open resource loaded' if case.startswith('resource-open') else 'a malformed capability was not refused as such'
    assert message == want, f'{label}: expected {want!r}, got {message!r}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize(('text', 'cause'), [
    pytest.param('Planted tools:\n- ghost: A tool nobody defines',
                 "its instructions list ['ghost'], which it does not register, and omit ['planted_echo'], which it "
                 'registers', id='lists-another'),
    pytest.param('Planted tools: none listed', "its instructions omit ['planted_echo'], which it registers",
                 id='omits-its-tool'),
    pytest.param(ECHO_TEXT + '\n- planted_echo: Again', "its instructions list ['planted_echo'] more than once",
                 id='lists-twice'),
])
def test_instructions_that_do_not_list_exactly_its_tools_are_refused(text: str, cause: str, names: tuple[str, ...],
                                                                     plant: Callable[..., EntryPoint]) -> None:
    ep = plant('planted-mismatch', 'mm = planted_mismatch.capability:CAPABILITY', package('planted_mismatch', text=text))
    message = load_error([*members(names), ep])
    want = f'cannot load capability planted-mismatch: {cause}'
    assert message == want, f'instructions that do not list exactly its tools loaded: expected {want!r}, got {message!r}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize(('error', 'cause'), [
    pytest.param("RuntimeError('planted failure at import')", 'RuntimeError: planted failure at import', id='raising'),
    pytest.param('RuntimeError()', 'RuntimeError', id='raising-empty'),
])
def test_a_failing_capability_module_is_refused_with_its_cause(error: str, cause: str, names: tuple[str, ...],
                                                               plant: Callable[..., EntryPoint]) -> None:
    ep = plant('planted-raising', 'raising = planted_raising.capability:CAPABILITY',
               {'planted_raising/__init__.py': '', 'planted_raising/capability.py': f'raise {error}\n'})
    message = load_error([*members(names), ep])
    want = f'cannot load capability planted-raising: {cause}'
    assert message == want, \
        f'a failing capability module does not name the distribution with its cause: expected {want!r}, got {message!r}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize(('case', 'cause'), [
    pytest.param('tools-missing', "ModuleNotFoundError: No module named 'planted_tools_failing.nowhere'",
                 id='tools-missing'),
    pytest.param('tools-raising', 'RuntimeError: planted failure after registering a tool', id='tools-raising'),
])
def test_a_failing_tools_module_is_refused_with_its_cause(case: str, cause: str, names: tuple[str, ...],
                                                          plant: Callable[..., EntryPoint]) -> None:
    if case == 'tools-missing':
        files = package('planted_tools_failing', tools='planted_tools_failing.nowhere')
    else:
        files = package('planted_tools_failing',
                        tools_tail="\nraise RuntimeError('planted failure after registering a tool')\n")
    before = list(TOOL_REGISTRY)
    ep = plant('planted-tools-failing', 'tf = planted_tools_failing.capability:CAPABILITY', files)
    message = load_error([*members(names), ep])
    want = f'cannot load capability planted-tools-failing: {cause}'
    assert message == want, f'a failing tools module loaded, or was refused with another cause: expected {want!r}, ' \
                            f'got {message!r}'
    assert TOOL_REGISTRY == before, f'a refused load left {[t for t in TOOL_REGISTRY[len(before):]]} registered'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_hand_built_entry_point_is_named_by_its_value(names: tuple[str, ...]) -> None:
    ep = EntryPoint(name='gone', value='planted_nowhere_at_all.capability:CAPABILITY', group=GROUP)
    message = load_error([*members(names), ep])
    want = ("cannot load capability planted_nowhere_at_all.capability:CAPABILITY: ModuleNotFoundError: No module "
            "named 'planted_nowhere_at_all'")
    assert message == want, f'an entry point with no distribution is not named by its value: expected {want!r}, ' \
                            f'got {message!r}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_capabilities_load_by_distribution_then_entry_point_name(names: tuple[str, ...],
                                                                 plant: Callable[..., EntryPoint]) -> None:
    # Given in reverse: `planted-b` (entry `aa`) before `planted-a`, whose entries `zz` and `yy` come
    # in that order; loaded, `planted-a`'s come first, `yy` before `zz`, then `planted-b`'s.
    files: dict[str, str] = {}
    for module in ('planted_aa', 'planted_yy', 'planted_zz'):
        files |= package(module, tool=f'{module}_echo', name=module.removeprefix('planted_'),
                         text=echo_text(f'{module}_echo'))
    b = plant('planted-b', 'aa = planted_aa.capability:CAPABILITY', {k: v for k, v in files.items() if 'aa' in k})
    a = plant('planted-a', 'zz = planted_zz.capability:CAPABILITY\nyy = planted_yy.capability:CAPABILITY',
              {k: v for k, v in files.items() if 'aa' not in k})
    a = sorted(a, key=lambda ep: ep.name, reverse=True)
    loaded = load([*reversed(members(names)), b, *a])
    got = [(c.distribution, c.capability.name) for c in loaded]
    want = [*sorted((member_entry_point(n).dist.name, n) for n in names),
            ('planted-a', 'yy'), ('planted-a', 'zz'), ('planted-b', 'aa')]
    assert got == want, f'the load does not follow (distribution, entry-point name): {got}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_capability_whose_tools_are_already_imported_keeps_them(names: tuple[str, ...],
                                                                 plant: Callable[..., EntryPoint]) -> None:
    # A second load, as the members get in every test, imports nothing new: its tools are found in the
    # registry by the module that defined them, not by what the import added.
    ep = plant('planted-imported', 'imported = planted_imported.capability:CAPABILITY', package('planted_imported'))
    __import__('planted_imported.tools')
    try:
        loaded = load([*members(names), ep])
    except CapabilityLoadError as exc:
        pytest.fail(f'a capability whose tools module was already imported lost its tools: {exc}')
    assert [tool.name for tool in loaded[-1].tools] == ['planted_echo'], \
        f'a capability whose tools module was already imported lost its tools: {loaded[-1].tools}'


# What a capability's own code can raise or exit with, as a statement planted in it, and the cause its
# refusal carries. Each is refused naming the distribution whenever the code runs. A
# `KeyboardInterrupt` is not one of them: it still interrupts.
PLANTED_STOP = '''import sys


class PlantedStop(BaseException):
    """Neither an Exception nor an exit."""


class Unprintable(Exception):
    """An exception whose text cannot be had: asked for it, it exits."""

    def __str__(self) -> str:
        raise SystemExit(1)
'''
RAISED = {
    'raises': ("raise RuntimeError('planted failure')", 'RuntimeError: planted failure'),
    'exits-0': ('raise SystemExit(0)', 'SystemExit: 0'),
    'exits-int': ('raise SystemExit(3)', 'SystemExit: 3'),
    'exits-text': ("sys.exit('this capability needs another platform')",
                   'SystemExit: this capability needs another platform'),
    'exits-bare': ('sys.exit()', 'SystemExit'),
    'exits-none': ('sys.exit(None)', 'SystemExit'),
    'raises-base': ("raise PlantedStop('planted stop')", 'PlantedStop: planted stop'),
    'raises-unprintable': ("raise Unprintable('planted')", 'Unprintable'),
}

# When it runs: while its entry point's module is imported; while its tools module is, after its tool
# registered; once both are, while the load reads what it declared (the module its tool names, a `str`
# whose `==` runs the statement, as the load's attribution of each registered tool compares it: the
# record's own values are exact types, refused before any of their code could run, `exact-<site>`); or
# while its resource is assembled (a handler that runs it on any attribute it lacks, as FastMCP reads
# one) or its tool is (a `FunctionTool` of its own that runs it when FastMCP reads its version).
WHEN = ('entry-point', 'tools', 'declared', 'served', 'served-tool')

# The tools module's tail that replaces its registered tool with one of its own class, which runs
# `{statement}` when its version is read.
ODD_TOOL = '''

from fastmcp.tools.function_tool import FunctionTool  # noqa: E402
from cluster_mcp.core.tools import TOOL_REGISTRY  # noqa: E402


class _Odd(FunctionTool):
    def __getattribute__(self, name: str) -> object:
        if name == 'version':
            {statement}
        return super().__getattribute__(name)

    def __repr__(self) -> str:
        return '_Odd()'


TOOL_REGISTRY[-1] = _Odd(**{{field: getattr(planted_echo, field) for field in type(planted_echo).model_fields}})
'''

# A module beside the tools module that registers a tool, and what it is called.
HELPER = ECHO_TOOL.format(name='planted_helper')

# Registrations the load checks whenever they happen: from the entry point's module itself, from a
# module it imports, or from its tools module imported by it (at the entry point's import) rather
# than by the load. Each is refused as a registration outside the tools module, or as not a tool.
TIMING: dict[str, dict[str, str]] = {
    'stray-imported-by-the-entry-point': {'entry': 'import {m}.helper  # noqa: F401\n', 'helper': HELPER},
    'stray-defined-in-the-entry-point': {'entry': HELPER},
    'stray-imported-by-tools-imported-by-the-entry-point': {'entry': 'import {m}.tools  # noqa: F401\n',
                                                            'tail': '\nimport {m}.helper  # noqa: E402, F401\n',
                                                            'helper': HELPER},
    'stray-imported-by-tools': {'tail': '\nimport {m}.helper  # noqa: E402, F401\n', 'helper': HELPER},
    'not-a-tool-from-the-entry-point': {'entry': NOT_A_TOOL},
    'not-a-tool-from-tools-imported-by-the-entry-point': {'entry': 'import {m}.tools  # noqa: F401\n',
                                                          'tail': NOT_A_TOOL},
}

# A distribution whose metadata names none: refused, named by its entry point's value, before any of
# its code runs (its capability is otherwise well formed).
NAMELESS = {
    'no-name': ('Metadata-Version: 2.1\nVersion: 0.0.1\n', 'its distribution metadata has no Name'),
    'blank-name': ('Metadata-Version: 2.1\nName: \nVersion: 0.0.1\n', 'its distribution metadata has no Name'),
    'unreadable': (b'Metadata-Version: 2.1\nName: planted-\xff\nVersion: 0.0.1\n',
                   "its distribution metadata cannot be read: UnicodeDecodeError: 'utf-8' codec can't decode byte "
                   '0xff in position 36: invalid start byte'),
}


# A subclass of `Capability` whose code runs whenever `<field>` is read, or, for `nothing`, one that
# adds no code at all: the load refuses each, its type named, before any field is read. Every field of
# the record has a row, so a field added later is pinned too.
SUBCLASS_READS = ('nothing', *(f.name for f in fields(Capability)))

SUBCLASS = '''

class {cls}(Capability):
    """A record whose code runs when its `{field}` is read: it hands back what was declared."""

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name == {field!r}:
            _READS.append(name)
        return value


_READS: list[str] = []
'''


def subclass_files(module: str, field: str) -> tuple[dict[str, str], str]:
    """A planted package `module` whose entry point names a subclass of `Capability` reading `field`
    through its own code (none for `nothing`), well formed otherwise; and the subclass's name."""
    cls = 'Reads' + ''.join(part.title() for part in field.split('_'))
    files = package(module)
    source = files[f'{module}/capability.py']
    head, _, tail = source.partition('\n\nCAPABILITY = Capability(')
    assert tail, source
    stub = f'\n\nclass {cls}(Capability):\n    """A subclass adding nothing."""\n' if field == 'nothing' else \
        SUBCLASS.format(cls=cls, field=field)
    files[f'{module}/capability.py'] = head + stub + f'\n\nCAPABILITY = {cls}(' + tail
    return files, cls


# What a record holds as an exact built-in type, given a type of its own: a subclass of `str`, `int`,
# `tuple` or `dict` whose every operation below exits once the entry point's module has built its
# record, as one that reads `order.__eq__` once did after the load, ending the start with exit 0 and no
# message. These are the operations the core, FastMCP and Python's own comparisons, hashes, iteration,
# formatting and method calls reach a value through.
OPERATIONS = {
    'str': ('__eq__', '__ne__', '__lt__', '__le__', '__gt__', '__ge__', '__hash__', '__len__', '__iter__',
            '__contains__', '__getitem__', '__add__', '__mul__', '__mod__', '__format__', '__str__', '__repr__',
            'startswith', 'endswith', 'strip', 'lstrip', 'rstrip', 'split', 'rsplit', 'partition', 'rpartition',
            'splitlines', 'replace', 'lower', 'upper', 'casefold', 'encode', 'join', 'format', 'find', 'index',
            'count', 'expandtabs', 'removeprefix', 'removesuffix', 'isidentifier'),
    'int': ('__eq__', '__ne__', '__lt__', '__le__', '__gt__', '__ge__', '__hash__', '__bool__', '__index__',
            '__int__', '__float__', '__add__', '__radd__', '__sub__', '__rsub__', '__mul__', '__neg__', '__abs__',
            '__format__', '__str__', '__repr__', '__round__', '__trunc__'),
    'tuple': ('__eq__', '__ne__', '__lt__', '__le__', '__gt__', '__ge__', '__hash__', '__len__', '__iter__',
              '__contains__', '__getitem__', '__add__', '__mul__', '__format__', '__str__', '__repr__', 'count',
              'index'),
    'dict': ('__eq__', '__ne__', '__len__', '__iter__', '__contains__', '__getitem__', '__setitem__', '__or__',
             '__ror__', '__reversed__', '__format__', '__str__', '__repr__', 'get', 'keys', 'values', 'items',
             'copy', 'setdefault', 'pop'),
}

# The planted classes, each named `Planted<Type>`: `_RAN` records each operation run once `_ARMED`
# holds a value, which the entry point's module appends as its last statement.
PLANTED_TYPES = f'''

_RAN: list[str] = []
_ARMED: list[bool] = []
_OPERATIONS = {OPERATIONS!r}


def _planted(base: type) -> type:
    """A subclass of `base` whose every operation in `_OPERATIONS` exits once `_ARMED` holds a value."""
    def operation(name: str):
        def run(self, *args, **kwargs):
            if _ARMED:
                _RAN.append(name)
                raise SystemExit(0)
            return getattr(base, name)(self, *args, **kwargs)
        return run
    return type('Planted' + base.__name__.title(), (base,),
                {{name: operation(name) for name in _OPERATIONS[base.__name__]}})


PlantedStr, PlantedInt, PlantedTuple, PlantedDict = (_planted(t) for t in (str, int, tuple, dict))
'''

# A resource entry's source, every key and value given as source text.
EXACT_ENTRY = {"'uri'": "'cluster://planted'", "'name'": "'planted'", "'description'": "'Planted'",
               "'handler'": '_read', "'executor'": 'True'}

# Where a value of a type of its own sits, as `exact-<site>`: each field of the record (from
# `dataclasses.fields`, so a field added later gets a kind), a declared command, a resource entry, a
# key of one, and each value of one but its handler (from the core's own entries, so a key added later
# gets one); the handler is the capability's code, which FastMCP registers and a request calls.
EXACT_FIELD_TYPES = {'name': 'str', 'order': 'int', 'tools': 'str', 'instructions': 'str', 'resources': 'tuple',
                     'commands': 'tuple'}
EXACT_ENTRY_KEYS = tuple(key for key in RESOURCE_REGISTRY[0] if key != 'handler')
EXACT_SITES = (*(f.name for f in fields(Capability)), 'command', 'resource', 'resource-key',
               *(f'resource-{key}' for key in EXACT_ENTRY_KEYS))


def exact_files(module: str, site: str) -> tuple[dict[str, str], str]:
    """A planted package `module` whose record holds a value of a type of its own at `site`, well formed
    otherwise; and the cause its refusal carries."""
    entry = dict(EXACT_ENTRY)
    record = {'name': repr(module), 'order': '500', 'tools': repr(f'{module}.tools'), 'instructions': repr(ECHO_TEXT),
              'resources': '', 'commands': "('planted_cmd',)"}
    shown = "its resource 'cluster://planted'"
    if site in EXACT_FIELD_TYPES:
        kind = EXACT_FIELD_TYPES[site]
        planted = f'Planted{kind.title()}'
        if site != 'resources':
            record[site] = f'{planted}({record[site]})'
        cause = f'its {site} is a {planted}, not {"an" if kind == "int" else "a"} {kind}'
    elif site == 'command':
        record['commands'] = "(PlantedStr('planted_cmd'),)"
        cause = 'one of its commands is a PlantedStr, not a str'
    elif site == 'resource':
        cause = 'one of its resources is a PlantedDict, not a dict'
    elif site == 'resource-key':
        entry = {("PlantedStr('uri')" if key == "'uri'" else key): value for key, value in entry.items()}
        cause = 'one of its resources has a PlantedStr key, not a str'
    elif site == 'resource-executor':
        entry["'executor'"] = 'PlantedInt(1)'
        cause = f'{shown} has executor a PlantedInt, not True: a capability resource is never open'
    else:
        key = site.removeprefix('resource-')
        entry[repr(key)] = f'PlantedStr({entry[repr(key)]})'
        cause = ('one of its resources has a PlantedStr uri, not a str' if key == 'uri'
                 else f'{shown} has a PlantedStr {key}, not a str')
    source = '{' + ', '.join(f'{key}: {value}' for key, value in entry.items()) + '}'
    if site == 'resource':
        source = f'PlantedDict({source})'
    record['resources'] = f'PlantedTuple(({source},))' if site == 'resources' else f'({source},)'
    files = package(module)
    head, _, tail = files[f'{module}/capability.py'].partition('\n\nCAPABILITY = Capability(')
    assert tail, files[f'{module}/capability.py']
    files[f'{module}/capability.py'] = (head + PLANTED_TYPES + '\n\nCAPABILITY = Capability('
                                        + ', '.join(f'{key}={value}' for key, value in record.items())
                                        + ')\n\n_ARMED.append(True)\n')
    return files, cause


@dataclass(frozen=True)
class Unloadable:
    """A planted capability the load must refuse: its distribution, entry point line, files, metadata
    (None: the default, naming it), the name its refusal carries and the cause after that name."""

    dist: str
    entry: str
    files: dict[str, str]
    metadata: str | bytes | None
    named: str
    cause: str


def raising_files(module: str, statement: str, when: str) -> dict[str, str]:
    """A planted package `module` whose code runs `statement` at `when`, a well-formed capability otherwise."""
    if when == 'tools':
        return package(module, tools_tail='\n' + PLANTED_STOP + '\n' + statement + '\n')
    if when == 'served-tool':
        return package(module, tools_tail='\n' + PLANTED_STOP + ODD_TOOL.format(statement=statement))
    files = package(module)
    source = files[f'{module}/capability.py']
    if when == 'entry-point':
        files[f'{module}/capability.py'] = PLANTED_STOP + '\n' + statement + '\n\n' + source
    elif when == 'served':
        stub = ('\n\nclass _Handler:\n    def __call__(self) -> str:\n        return "planted"\n\n'
                f'    def __getattr__(self, name: str) -> object:\n        {statement}\n')
        head, _, tail = source.partition('\n\nCAPABILITY = ')
        assert 'resources=()' in tail, tail
        files[f'{module}/capability.py'] = (PLANTED_STOP + '\n' + head + stub + '\n\nCAPABILITY = '
                                            + tail.replace('resources=()', f"resources=({resource(handler='_Handler()')},)"))
    else:
        tail = (f'\n\nclass _Module(str):\n    def __eq__(self, other: object) -> bool:\n        {statement}\n\n'
                '    __hash__ = str.__hash__\n\n\nplanted_echo.fn.__module__ = _Module(planted_echo.fn.__module__)\n')
        files = package(module, tools_tail='\n' + PLANTED_STOP + tail)
    return files


def unloadable(kind: str) -> Unloadable:
    """The planted capability of `kind`: `<raised>-at-<when>`, a `TIMING` kind, `nameless-<NAMELESS kind>`,
    `subclass-reads-<SUBCLASS_READS field>`, or `exact-<EXACT_SITES site>`."""
    module = 'planted_' + kind.replace('-', '_')
    dist = f'planted-{kind}'
    entry = f'cap = {module}.capability:CAPABILITY'
    if kind.startswith('nameless-'):
        metadata, cause = NAMELESS[kind.removeprefix('nameless-')]
        return Unloadable(dist, entry, package(module), metadata, entry.split(' = ')[1], cause)
    if kind.startswith('subclass-reads-'):
        files, cls = subclass_files(module, kind.removeprefix('subclass-reads-'))
        return Unloadable(dist, entry, files, None, dist, f'the entry point names a {cls}, not a Capability')
    if kind.startswith('exact-'):
        files, cause = exact_files(module, kind.removeprefix('exact-'))
        return Unloadable(dist, entry, files, None, dist, cause)
    if kind in TIMING:
        spec = {key: text.replace('{m}', module) for key, text in TIMING[kind].items()}
        files = package(module, tools_tail=spec.get('tail', ''))
        files[f'{module}/capability.py'] = spec.get('entry', '') + '\n\n' + files[f'{module}/capability.py']
        if 'helper' in spec:
            files[f'{module}/helper.py'] = spec['helper']
        if 'not-a-tool' in kind:
            cause = 'loading it registered a function, not a FunctionTool'
        else:
            cause = f"loading it registered ['planted_helper'], which are outside {module}.tools"
        return Unloadable(dist, entry, files, None, dist, cause)
    raised, _, when = kind.partition('-at-')
    statement, cause = RAISED[raised]
    if when == 'served':
        cause = f"its resource 'cluster://planted' cannot be served: {cause}"
    if when == 'served-tool':
        cause = f"its tool 'planted_echo' cannot be served: {cause}"
    return Unloadable(dist, entry, raising_files(module, statement, when), None, dist, cause)


UNLOADABLE = [*(f'{raised}-at-{when}' for when in WHEN for raised in RAISED), *TIMING,
              *(f'nameless-{kind}' for kind in NAMELESS), *(f'subclass-reads-{field}' for field in SUBCLASS_READS),
              *(f'exact-{site}' for site in EXACT_SITES)]


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('kind', UNLOADABLE)
def test_a_capability_that_cannot_load_is_refused_naming_it(kind: str, names: tuple[str, ...],
                                                            plant: Callable[..., EntryPoint]) -> None:
    case = unloadable(kind)
    ep = plant(case.dist, case.entry, case.files, case.metadata)
    before = list(TOOL_REGISTRY)
    message = load_error([*members(names), ep])
    want = f'cannot load capability {case.named}: {case.cause}'
    assert message == want, f'a capability that cannot load was not refused naming it: expected {want!r}, got {message!r}'
    assert TOOL_REGISTRY == before, f'a refused load left {[t for t in TOOL_REGISTRY[len(before):]]} registered'
    # A value of a type of its own is refused for its type before any of its operations runs.
    ran = getattr(sys.modules.get(case.entry.split(' = ')[1].split(':')[0]), '_RAN', None)
    assert not ran, f'a capability that cannot load was not refused naming it: its code ran during the load: {ran}'


# A keyboard interrupt raised, and one raised while the load reads the text of what a capability raised.
INTERRUPTS = {
    'raised': 'raise KeyboardInterrupt',
    'in-its-text': "raise type('Interrupting', (Exception,), {'__str__': lambda self: exec('raise KeyboardInterrupt')})()",
}


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('when', WHEN)
@pytest.mark.parametrize('how', list(INTERRUPTS))
def test_a_keyboard_interrupt_while_loading_still_interrupts(how: str, when: str, names: tuple[str, ...],
                                                             plant: Callable[..., EntryPoint]) -> None:
    module = f'planted_interrupt_{how.replace("-", "_")}_{when.replace("-", "_")}'
    ep = plant(f'planted-interrupt-{how}-{when}', f'cap = {module}.capability:CAPABILITY',
               raising_files(module, INTERRUPTS[how], when))
    before = list(TOOL_REGISTRY)
    try:
        load([*members(names), ep])
    except KeyboardInterrupt:
        pass
    except BaseException as exc:
        pytest.fail(f'a keyboard interrupt did not interrupt the load: it raised {exc!r}')
    else:
        pytest.fail('a keyboard interrupt did not interrupt the load: it loaded')
    assert TOOL_REGISTRY == before, f'an interrupted load left {[t.name for t in TOOL_REGISTRY[len(before):]]} registered'


class KeyedDistribution:
    """A distribution whose metadata has no `Name`, read as the Pythons that raise for one do."""

    @property
    def name(self) -> str:
        raise KeyError('Name')


class NamedDistribution(Distribution):
    """A distribution whose `Name` is a `str` of a type of its own (as a distribution finder of its own
    could hand back), every operation of which is recorded once the row arms it."""

    RAN: list[str] = []
    ARMED: list[bool] = []

    def __init__(self, info: Path) -> None:
        self.info = info

    def read_text(self, filename: str) -> str | None:
        path = self.info / filename
        return path.read_text() if path.is_file() else None

    def locate_file(self, path: str) -> Path:
        return self.info.parent / path

    @property
    def name(self) -> str:
        def operation(op: str) -> Callable[..., object]:
            def run(value: str, *args: object, **kwargs: object) -> object:
                if NamedDistribution.ARMED:
                    NamedDistribution.RAN.append(op)
                return getattr(str, op)(value, *args, **kwargs)
            return run
        planted = type('PlantedStr', (str,), {op: operation(op) for op in OPERATIONS['str']})
        return planted(self.read_text('METADATA').split('Name: ', 1)[1].split('\n', 1)[0])


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_distribution_name_of_a_type_of_its_own_is_no_name(names: tuple[str, ...],
                                                            plant: Callable[..., EntryPoint]) -> None:
    # The name is ordered against the others and composed after the load, so it must be exactly a
    # `str`: one of a type of its own is no name, and the capability is named by its entry point's
    # value, before any of the name's operations runs.
    why = 'a distribution name of a type of its own was read as a name'
    planted = plant('planted-named', 'named = planted_named.capability:CAPABILITY', package('planted_named'))
    (ep,) = NamedDistribution(Path(planted.dist._path)).entry_points.select(group=GROUP)
    before = list(TOOL_REGISTRY)
    NamedDistribution.RAN.clear()
    NamedDistribution.ARMED.append(True)
    try:
        message = load_error([*members(names), ep])
    finally:
        NamedDistribution.ARMED.clear()
    want = 'cannot load capability planted_named.capability:CAPABILITY: its distribution metadata has no Name'
    assert message == want, f'{why}: expected {want!r}, got {message!r}'
    assert NamedDistribution.RAN == [], f'{why}: its operations ran during the load: {NamedDistribution.RAN}'
    assert TOOL_REGISTRY == before, f'{why}: the refusal left {TOOL_REGISTRY[len(before):]} registered'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_name_missing_as_a_key_error_is_no_name(names: tuple[str, ...]) -> None:
    ep = EntryPoint(name='keyed', value='planted_nowhere_at_all.capability:CAPABILITY', group=GROUP)._for(KeyedDistribution())
    message = load_error([*members(names), ep])
    want = 'cannot load capability planted_nowhere_at_all.capability:CAPABILITY: its distribution metadata has no Name'
    assert message == want, f'a capability that cannot load was not refused naming it: expected {want!r}, got {message!r}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_capability_whose_entry_point_imports_its_tools_loads(names: tuple[str, ...],
                                                                plant: Callable[..., EntryPoint]) -> None:
    # Its tools register while its entry point loads, before the load imports its tools module: they
    # are its own, and checked as such.
    files = package('planted_early')
    files['planted_early/capability.py'] = 'import planted_early.tools  # noqa: F401\n\n' + files['planted_early/capability.py']
    ep = plant('planted-early', 'early = planted_early.capability:CAPABILITY', files)
    try:
        loaded = load([*members(names), ep])
    except CapabilityLoadError as exc:
        pytest.fail(f'a well-formed capability was refused: {exc}')
    assert [tool.name for tool in loaded[-1].tools] == ['planted_echo'], \
        f'a well-formed capability was refused its tools: {loaded[-1].tools}'


# A distribution whose entry points cannot be read: a line with no `=`. Every installed distribution's
# entry points are read while the group is discovered.
UNREADABLE_ENTRY_POINTS = '[cluster_mcp.capabilities]\nno equals sign here\n'
UNREADABLE_CAUSE = "its entry points cannot be read: TypeError: Pair.__new__() missing 1 required positional argument: 'value'"


def discovered_as(names: tuple[str, ...]) -> Callable[..., object]:
    """The group as `entry_points` discovers it, but for the members outside `names`: its real discovery runs."""
    def discover(group: str) -> tuple[EntryPoint, ...]:
        return tuple(ep for ep in entry_points(group=group)
                     if ep.dist is None or ep.dist.metadata.get('Name') not in OTHER_MEMBERS[names])
    return discover


# The member distributions a member set leaves out.
OTHER_MEMBERS = {(): {'cluster-mcp-slurm', 'cluster-mcp-rcac'}, ('slurm',): {'cluster-mcp-rcac'},
                 ('rcac',): {'cluster-mcp-slurm'}, ('rcac', 'slurm'): set()}


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('case', ['named', 'nameless', 'blank-name', 'metadata-unreadable'])
def test_entry_points_that_cannot_be_read_are_refused_naming_their_distribution(
        case: str, names: tuple[str, ...], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Named by its metadata's `Name`, or where it is installed when its metadata names none.
    info = tmp_path / 'planted_unreadable-0.0.1.dist-info'
    info.mkdir()
    metadata = {'named': None, 'nameless': NAMELESS['no-name'][0], 'blank-name': NAMELESS['blank-name'][0],
                'metadata-unreadable': NAMELESS['unreadable'][0]}
    write_metadata(info, 'planted-unreadable', metadata[case])
    (info / 'entry_points.txt').write_text(UNREADABLE_ENTRY_POINTS)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(cluster_mcp.core.capabilities, 'entry_points', discovered_as(names))
    message = load_error(None)
    named = 'planted-unreadable' if case == 'named' else str(info)
    want = f'cannot load capability {named}: {UNREADABLE_CAUSE}'
    assert message == want, f'unreadable entry points were not refused naming their distribution: expected {want!r}, ' \
                            f'got {message!r}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_discovery_that_fails_with_every_distribution_readable_is_refused_naming_the_group(
        names: tuple[str, ...], monkeypatch: pytest.MonkeyPatch) -> None:
    def discover(group: str) -> tuple[EntryPoint, ...]:
        raise RuntimeError('planted discovery failure')
    monkeypatch.setattr(cluster_mcp.core.capabilities, 'entry_points', discover)
    message = load_error(None)
    want = f'cannot load capability {GROUP}: its entry points cannot be read: RuntimeError: planted discovery failure'
    assert message == want, f'a failed discovery was not refused: expected {want!r}, got {message!r}'


# Ties and keys: every way to order capabilities other than the documented one gives another order
# here. Four capabilities beside the members, whose names, tools modules and distributions each sort
# differently, one of them at the Slurm member's order.
TIED = (('d', 'planted_z.tools', 'dist-z', 100), ('c', 'planted_b.tools', 'dist-a', 500),
        ('a', 'planted_c.tools', 'dist-b', 500), ('b', 'planted_a.tools', 'dist-c', 500))


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_composition_breaks_ties_by_distribution(names: tuple[str, ...]) -> None:
    template = by_name()['slurm'].capability
    tied = [Loaded(replace(template, name=name, tools=tools, order=order), dist, ()) for name, tools, dist, order in TIED]
    given = [*(by_name()[n] for n in names), *tied]
    want = [*(['cluster-mcp-slurm'] if 'slurm' in names else []), 'dist-z', 'dist-a', 'dist-b', 'dist-c',
            *(['cluster-mcp-rcac'] if 'rcac' in names else [])]
    for order in itertools.permutations(given):
        got = [c.distribution for c in composed(order)]
        assert got == want, f'composed out of (order, distribution), so the composition follows the given order: ' \
                            f'{got}, expected {want}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_entry_points_load_by_distribution_then_name_not_value(names: tuple[str, ...],
                                                               plant: Callable[..., EntryPoint]) -> None:
    # `planted-a`'s entry points sort one way by name and the other by value; `planted-b`'s sorts
    # between them by name and first by value.
    files: dict[str, str] = {}
    for module in ('planted_xx', 'planted_yy', 'planted_zz'):
        files |= package(module, tool=f'{module}_echo', name=module.removeprefix('planted_'),
                         text=echo_text(f'{module}_echo'))
    a = plant('planted-a', 'aa = planted_zz.capability:CAPABILITY\nbb = planted_yy.capability:CAPABILITY',
              {k: v for k, v in files.items() if 'xx' not in k})
    b = plant('planted-b', 'ab = planted_xx.capability:CAPABILITY', {k: v for k, v in files.items() if 'xx' in k})
    loaded = load([b, *reversed(a), *reversed(members(names))])
    got = [(c.distribution, c.capability.name) for c in loaded]
    want = [member for member in (('cluster-mcp-rcac', 'rcac'), ('cluster-mcp-slurm', 'slurm')) if member[1] in names]
    want += [('planted-a', 'zz'), ('planted-a', 'yy'), ('planted-b', 'xx')]
    assert got == want, f'the load does not follow (distribution, entry-point name): {got}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_failed_load_is_not_cached(names: tuple[str, ...], monkeypatch: pytest.MonkeyPatch) -> None:
    gone = EntryPoint(name='gone', value='planted_nowhere_at_all.capability:CAPABILITY', group=GROUP)
    found = [*members(names), gone]
    discoveries: list[str] = []
    monkeypatch.setattr(cluster_mcp.core.capabilities, 'entry_points',
                        lambda group: discoveries.append(group) or tuple(found))
    monkeypatch.setattr(cluster_mcp.core.capabilities, '_installed', None)
    want = "cannot load capability planted_nowhere_at_all.capability:CAPABILITY: ModuleNotFoundError: No module " \
           "named 'planted_nowhere_at_all'"
    for attempt in ('first', 'second'):
        try:
            got = installed()
        except CapabilityLoadError as exc:
            assert str(exc) == want, f'a failed load was cached: the {attempt} call raised {exc}'
            continue
        pytest.fail(f'a failed load was cached: the {attempt} call returned {got}')
    found.remove(gone)
    try:
        loaded = installed()
    except CapabilityLoadError as exc:
        pytest.fail(f'a failed load was cached: with the capability gone, the next call still raised {exc}')
    assert [c.capability.name for c in loaded] == sorted(names), f'a failed load was cached: {loaded}'
    assert installed() is loaded and len(discoveries) == 3, \
        f'a load that succeeded was not cached: {len(discoveries)} discoveries for 4 calls'


# The core's tools that open and close every listing, by name, as clients have always seen them.
OPENING = ('run_command', 'list_directory', 'read_file', 'write_file', 'upload_file', 'download_file')
CLOSING = ('cluster_context',)


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_the_listing_opens_and_closes_with_the_core_tools_by_name(names: tuple[str, ...]) -> None:
    given = tuple(by_name()[n] for n in names)
    tools = served_tools(create_mcp_server('none', site=SITE, capabilities=given))
    middle = [tool.name for loaded in sorted(given, key=lambda c: c.distribution) for tool in loaded.tools]
    want = [*OPENING, *middle, *CLOSING]
    assert tools == want, f'the core tools do not open and close the listing: {tools}, expected {want}'


# Each malformed command declaration, as the source a planted capability passes as `commands=`, and the
# cause its refusal carries. A subclass of `tuple` or `str` is refused for its type: the probe iterates
# and hashes the names after the load, where its code would run.
NOT_A_NAME = "its command {!r} is not a command name"
COMMAND_DECLARATIONS = {
    'bare-string': ("'sinfo'", 'its commands is a str, not a tuple'),
    'list': ("['sinfo']", 'its commands is a list, not a tuple'),
    'not-a-str': ('(1,)', 'one of its commands is a int, not a str'),
    'bytes': ("(b'sinfo',)", 'one of its commands is a bytes, not a str'),
    'empty': ("('',)", NOT_A_NAME.format('')),
    'slash': ("('/usr/bin/sinfo',)", NOT_A_NAME.format('/usr/bin/sinfo')),
    'relative-slash': ("('bin/sinfo',)", NOT_A_NAME.format('bin/sinfo')),
    'space': ("('s info',)", NOT_A_NAME.format('s info')),
    'tab': ("('s\\tinfo',)", NOT_A_NAME.format('s\tinfo')),
    'newline': ("('sinfo\\n',)", NOT_A_NAME.format('sinfo\n')),
    'nul': ("('sin\\x00fo',)", NOT_A_NAME.format('sin\x00fo')),
    'leading-dash': ("('-sinfo',)", NOT_A_NAME.format('-sinfo')),
    'leading-dot': ("('.sinfo',)", NOT_A_NAME.format('.sinfo')),
    'non-ascii': ("('s\u00efnfo',)", NOT_A_NAME.format('s\u00efnfo')),
    'semicolon': ("('a;b',)", NOT_A_NAME.format('a;b')),
    'dollar': ("('$x',)", NOT_A_NAME.format('$x')),
    'backtick': ("('`x`',)", NOT_A_NAME.format('`x`')),
    'star': ("('s*',)", NOT_A_NAME.format('s*')),
    'quote': ('("a\'b",)', NOT_A_NAME.format("a'b")),
    'too-long': (repr(('x' * 256,)), NOT_A_NAME.format('x' * 256)),
    'twice': ("('sinfo', 'squeue', 'sinfo')", "its command 'sinfo' is declared twice"),
    'tuple-subclass': ("type('T', (tuple,), {})(('sinfo',))", 'its commands is a T, not a tuple'),
    'str-subclass': ("(type('S', (str,), {})('sinfo'),)", 'one of its commands is a S, not a str'),
}

# Well-formed declarations, each loading with exactly the commands it declares.
WELL_FORMED_COMMANDS = {
    'plain': ("('planted_cmd_a', 'planted_cmd_b')", ('planted_cmd_a', 'planted_cmd_b')),
    'inner-marks': ("('a.b+c-d_e', '_x', '9z')", ('a.b+c-d_e', '_x', '9z')),
    'longest': (repr(('x' * 255,)), ('x' * 255,)),
    'none': (None, ()),
}


def declaring(module: str, commands: str | None, **capability: object) -> dict[str, str]:
    """The files of a planted package `module` whose capability declares `commands` (source), or none."""
    files = package(module, **capability)
    source = files[f'{module}/capability.py']
    assert source.count('resources=()') == 1, 'the planted source no longer holds resources=()'
    if commands is not None:
        files[f'{module}/capability.py'] = source.replace('resources=()', f'resources=(), commands={commands}')
    return files


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('kind', list(COMMAND_DECLARATIONS))
def test_a_malformed_command_declaration_is_refused_at_load(kind: str, names: tuple[str, ...],
                                                            plant: Callable[..., EntryPoint]) -> None:
    declared, cause = COMMAND_DECLARATIONS[kind]
    before = list(TOOL_REGISTRY)
    ep = plant('planted-commands', 'commands = planted_commands.capability:CAPABILITY',
               declaring('planted_commands', declared))
    message = load_error([*members(names), ep])
    want = f'cannot load capability planted-commands: {cause}'
    assert message == want, f'a malformed command declaration was not refused as such: expected {want!r}, got {message!r}'
    assert TOOL_REGISTRY == before, \
        f'a malformed command declaration was not refused as such: it left {TOOL_REGISTRY[len(before):]} registered'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_planted_capability_declares_commands_with_no_core_edit(names: tuple[str, ...],
                                                                 plant: Callable[..., EntryPoint]) -> None:
    for kind, (declared, want) in WELL_FORMED_COMMANDS.items():
        module = f"planted_{kind.replace('-', '_')}"
        tool = f'{module}_echo'
        files = declaring(module, declared, tool=tool, text=echo_text(tool))
        ep = plant(f"planted-{kind}", f'{kind.replace("-", "_")} = {module}.capability:CAPABILITY', files)
        try:
            loaded = load([*members(names), ep])
        except CapabilityLoadError as exc:
            pytest.fail(f'a well-formed command declaration was refused: {kind}: {exc}')
        got = {c.distribution: c.capability.commands for c in loaded}
        assert got[f'planted-{kind}'] == want, \
            f'a well-formed command declaration was refused or changed: {kind}: {got[f"planted-{kind}"]!r}, declared {want!r}'
        assert [c.capability.name for c in loaded[:-1]] == sorted(names), \
            f'a well-formed command declaration was refused beside {names}: {loaded}'
    # Built positionally, as the five fields were before commands existed, a capability declares none.
    template = by_name()['slurm'].capability
    old = type(template)(template.name, template.order, template.tools, template.instructions, template.resources)
    assert old.commands == (), f'a well-formed command declaration was refused or changed: positional {old.commands!r}'


@pytest.mark.unit
def test_the_members_declare_their_commands() -> None:
    declared = {ep.dist.name: ep.load().commands for ep in entry_points(group=GROUP)}
    assert declared == {'cluster-mcp-slurm': ('sbatch', 'squeue', 'scancel', 'sacct', 'sinfo', 'scontrol'),
                        'cluster-mcp-rcac': ('findscratch', 'myquota')}, declared
    loaded = {c.distribution: c.capability.commands for c in installed()}
    assert loaded == declared, f'the members load other commands than they declare: {loaded}'
