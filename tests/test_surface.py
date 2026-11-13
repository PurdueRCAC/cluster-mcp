# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The served surface is pinned by a plain snapshot test.

`tests/fixtures/served_surface.json` is the serialization of everything the server serves, in both
protocol eras and under every capability set in `test_capabilities.SETS`, under the harness's site
context and auth mode `none`, as `served_surface` records it: the instructions; every entry of the
tool, resource, resource template and prompt listings, every key at any depth; the server info; and
the advertised capabilities object. `serialization` lays it out field first, then era, then set
(`{listing: {identity: {era: {set: entry}}}}` and `{key: {era: {set: value}}}`), so a change to one
entry shows in `git diff` under that entry's name, and `canonical` writes it indented with its keys
sorted, so one served surface is always the same bytes.

`test_served_surface_matches_baseline` compares those bytes with the fixture's by plain equality:
no tolerated-difference list, no exemption, and a fixture out of canonical form fails too. On a
difference it fails with `report`, one line per differing field, each naming the entry, the era,
the set and the field path (`differences`). The serializer holds the one normalization, named
beside it with its cause (`VERSION_SOURCES`, `version_source`).

`UPDATE_SURFACE=1` turns the same test into the update mode: it writes the fixture from the live
server and never reads the old one, so a conflicted, missing or stale fixture is regenerated. Run it
after a deliberate surface change (`UPDATE_INVOCATION`); the change lands as that fixture diff,
`git diff` on the fixture its delta list in the commit body, reviewed as a surface change. Nothing
else in the suite writes the fixture, and no workflow or `bin/` script turns the update mode on.
"""

from __future__ import annotations

import copy
import functools
import importlib.metadata
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

from harness import ERA, ERAS, SITE, SURFACE_LISTINGS, FastMCP, Middleware, served_surface, surface_record
import test_capabilities
from cluster_mcp.core.server import create_mcp_server

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'served_surface.json'
REPO = FIXTURE.parents[2]
UPDATE = 'UPDATE_SURFACE'
UPDATE_INVOCATION = (f"bin/sandbox.sh sh -c 'cd \"$CLUSTER_MCP_REPO\" && {UPDATE}=1 uv run pytest -q "
                     "tests/test_surface.py::test_served_surface_matches_baseline'")

Surface = dict[str, Any]
FieldPath = tuple[str, ...]
LISTING_KEYS = tuple(key for key, _, _ in SURFACE_LISTINGS)


def served_surfaces() -> dict[tuple[str, str], Surface]:
    """What a server built from each capability set in `test_capabilities.SETS` serves, in each era."""
    loaded = test_capabilities.by_name()
    surfaces: dict[tuple[str, str], Surface] = {}
    for param in test_capabilities.SETS:
        (names,) = param.values
        server = create_mcp_server('none', site=SITE, capabilities=tuple(loaded[name] for name in names))
        for era in ERAS:
            surfaces[(era, param.id)] = served_surface(server, era=era)
    return surfaces


# The one normalization. `serverInfo.version` is the version of an installed distribution: FastMCP's
# today (it reads its version from `fastmcp-slim`), the core's once the server serves its own. It
# moves with every lock bump and release, so it is recorded as the distribution it comes from: a
# version bump is no surface change, and a switch of source is a one-field diff. `fastmcp` is not a
# candidate: it is installed at the same version as `fastmcp-slim`, so it could never be told apart.
VERSION_SOURCES = ('cluster-mcp', 'fastmcp-slim')


def installed_versions() -> dict[str, str | None]:
    """Each of `VERSION_SOURCES` with its installed version, or None when it is not installed."""
    found: dict[str, str | None] = {}
    for name in VERSION_SOURCES:
        try:
            found[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            found[name] = None
    return found


def version_source(served: Any, installed: Mapping[str, str | None]) -> str:
    """The one candidate in `installed` whose version is exactly `served`; none or several raise.

    An uninstalled candidate (None) never matches, and a served value that is not a string matches
    nothing.
    """
    found = [name for name, version in installed.items()
             if isinstance(served, str) and version is not None and version == served]
    if len(found) != 1:
        candidates = ', '.join(f'{name} {version if version is not None else "(not installed)"}'
                               for name, version in installed.items())
        raise ValueError(f'serverInfo.version: the served version {served!r} is the installed version of '
                         f'{len(found)} of the candidates ({candidates}), so its source cannot be recorded')
    return found[0]


def normalized(surface: Mapping[str, Any], installed: Mapping[str, str | None]) -> Surface:
    """`surface` with `serverInfo.version` recorded as `{"distribution": …}`, and nothing else changed."""
    out = dict(surface)
    info = dict(out.get('serverInfo') or {})
    info['version'] = {'distribution': version_source(info.get('version'), installed)}
    out['serverInfo'] = info
    return out


def serialization(surfaces: Mapping[tuple[str, str], Mapping[str, Any]]) -> Surface:
    """The field-first layout of every `(era, set)` surface: each listing keyed by identity, then era,
    then set; every other top-level key by era, then set. Every key of every surface appears, an
    empty listing as `{}`."""
    out: Surface = {}
    for (era, set_id), surface in surfaces.items():
        for key, value in surface.items():
            if key in LISTING_KEYS:
                listing = out.setdefault(key, {})
                for identity, entry in value.items():
                    listing.setdefault(identity, {}).setdefault(era, {})[set_id] = entry
            else:
                out.setdefault(key, {}).setdefault(era, {})[set_id] = value
    return out


def canonical(obj: Any) -> bytes:
    """The one byte form of a serialization: indented, keys sorted, one trailing newline."""
    return (json.dumps(obj, indent=1, sort_keys=True) + '\n').encode()


@functools.cache
def serialized() -> bytes:
    """The canonical serialization of what the server serves now, built once per process."""
    installed = installed_versions()
    return canonical(serialization({at: normalized(surface, installed) for at, surface in served_surfaces().items()}))


IDENTIFIER = re.compile(r'[A-Za-z_][\w-]*')
SHORT = 60


def render_path(path: FieldPath) -> str:
    """`tools.run_command.legacy.both.annotations.readOnlyHint`; a key that is not a plain name is
    quoted, `resources['cluster://storage'].modern.slurm`."""
    text = ''
    for key in path:
        if IDENTIFIER.fullmatch(key):
            text += f'.{key}' if text else key
        else:
            text += f"['{key}']"
    return text or '<root>'


def _short(text: str) -> str:
    return text if len(text) <= SHORT else text[:SHORT - 3] + '...'


def differences(old: Any, new: Any, path: FieldPath = ()) -> list[str]:
    """One line per field that differs from `old` to `new`, descending dicts only: a key only in
    `new` is added, only in `old` removed, and any other leaf (a list included) changed when its JSON
    text differs."""
    if isinstance(old, dict) and isinstance(new, dict):
        lines: list[str] = []
        for key in sorted(set(old) | set(new)):
            if key not in old:
                lines.append(f'- {render_path(path + (key,))}: added')
            elif key not in new:
                lines.append(f'- {render_path(path + (key,))}: removed')
            else:
                lines.extend(differences(old[key], new[key], path + (key,)))
        return lines
    was, now = json.dumps(old, sort_keys=True), json.dumps(new, sort_keys=True)
    return [] if was == now else [f'- {render_path(path)}: changed: {_short(was)} -> {_short(now)}']


def report(fixture: Path, expected: bytes | None, served: bytes) -> str:
    """Why `fixture` fails: a header line naming it and the update invocation, then each differing field."""
    header = (f'{fixture} is not the served surface; after a deliberate surface change, re-take it with '
              f'{UPDATE_INVOCATION}')
    if expected is None:
        return f'{header}\n- the fixture does not exist'
    try:
        old = json.loads(expected)
    except ValueError:
        return f'{header}\n- the fixture is not JSON'
    lines = differences(old, json.loads(served))
    return '\n'.join([header, *(lines or ['- the fixture is not in canonical form (no field differs)'])])


def surface_check(fixture: Path, served: bytes, update: bool) -> None:
    """With `update`, write `served` to `fixture` without reading it; otherwise fail unless the
    fixture's bytes are `served`."""
    if update:
        fixture.write_bytes(served)
        return
    expected = fixture.read_bytes() if fixture.exists() else None
    if expected != served:
        raise AssertionError(report(fixture, expected, served))


@pytest.mark.unit
def test_served_surface_matches_baseline() -> None:
    surface_check(FIXTURE, serialized(), update=os.environ.get(UPDATE) == '1')


# A field changed at depth fails, one line per differing field naming its entry, era, set and field,
# and no line for a field that does not differ. The fixture holds the real serialization, which
# passes as it is; the served bytes carry the row's plants, chosen from the serialization itself. One
# row per way a field can differ, since one plant cannot tell a verdict that ignores JSON types from a
# report that drops added or removed keys; a row whose only difference is whitespace inside a string,
# since a verdict that compares tokens instead of bytes passes it; and a row with two differences in
# two entries, since a report that stops at the first line names one. Each row writes its expected
# lines by hand, never through `render_path`, so a line pins the path's form: the era and set named,
# a key that is not a plain name quoted.

def _deepest(node: Any, keep: Any, path: FieldPath = ()) -> tuple[int, FieldPath] | None:
    """The deepest path, descending dicts only, whose value `keep` accepts; the first in sort order."""
    best = (len(path), path) if path and keep(node) else None
    if isinstance(node, dict):
        for key in sorted(node):
            found = _deepest(node[key], keep, path + (key,))
            if found is not None and (best is None or found[0] > best[0]):
                best = found
    return best


def _holder(tree: Any, path: FieldPath) -> Any:
    for key in path:
        tree = tree[key]
    return tree


def _in_tools(tree: Surface, era: str, set_id: str, keep: Any) -> FieldPath:
    """The deepest path `keep` accepts inside any tool's copy under `era` and `set_id`."""
    found = []
    for name in sorted(tree['tools']):
        held = tree['tools'][name].get(era, {}).get(set_id)
        hit = _deepest(held, keep) if held is not None else None
        if hit is not None:
            found.append((hit[0], ('tools', name, era, set_id) + hit[1]))
    assert found, f'no plant site under {era}, {set_id}'
    return max(found, key=lambda f: f[0])[1]


def _dotted(path: FieldPath) -> str:
    """The path written out by hand, not by `render_path`: each key a plain name, joined with `.`."""
    assert all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', key) for key in path), f'not a plain-name path: {path}'
    return '.'.join(path)


def _type_twin(tree: Surface) -> list[str]:
    at = _in_tools(tree, ERAS[-1], 'slurm', lambda v: isinstance(v, (bool, int)))
    value = _holder(tree, at)
    _holder(tree, at[:-1])[at[-1]] = int(value) if isinstance(value, bool) else float(value)
    return [f'- {_dotted(at)}: changed: {json.dumps(value)} -> {json.dumps(_holder(tree, at))}']


def _gained(tree: Surface) -> list[str]:
    at = _in_tools(tree, ERAS[0], 'both', lambda v: isinstance(v, dict))
    _holder(tree, at)['x-planted'] = 1
    return [f'- {_dotted(at)}.x-planted: added']


def _lost(tree: Surface) -> list[str]:
    del tree['resources']['cluster://context']['modern']['slurm']['mimeType']
    return ["- resources['cluster://context'].modern.slurm.mimeType: removed"]


def _whitespace(tree: Surface) -> list[str]:
    # A doubled space inside a string at depth, in this pass's era. The values are shown as the
    # report cuts them: the row pins the verdict and the field, not the cut.
    at = _in_tools(tree, ERA, 'both', lambda v: isinstance(v, str) and ' ' in v)
    value = _holder(tree, at)
    _holder(tree, at[:-1])[at[-1]] = value.replace(' ', '  ', 1)
    return [f'- {_dotted(at)}: changed: {_short(json.dumps(value))} -> {_short(json.dumps(_holder(tree, at)))}']


def _two_entries(tree: Surface) -> list[str]:
    # A key gained by one tool and a key lost by another, in this pass's era: two lines, in the
    # report's order (sorted by name), and none for the entries between or around them.
    first, second = [name for name in sorted(tree['tools']) if 'both' in tree['tools'][name].get(ERA, {})][:2]
    tree['tools'][first][ERA]['both']['x-planted'] = 1
    del tree['tools'][second][ERA]['both']['description']
    return [f'- {_dotted(("tools", first, ERA, "both", "x-planted"))}: added',
            f'- {_dotted(("tools", second, ERA, "both", "description"))}: removed']


@pytest.mark.unit
@pytest.mark.parametrize('plant', [
    pytest.param(_type_twin, id='changed-type'),
    pytest.param(_gained, id='gained'),
    pytest.param(_lost, id='lost'),
    pytest.param(_whitespace, id='whitespace'),
    pytest.param(_two_entries, id='two-entries'),
])
def test_a_field_changed_at_depth_fails_naming_its_entry_and_field(plant: Any, tmp_path: Path) -> None:
    fixture = tmp_path / 'served_surface.json'
    fixture.write_bytes(serialized())
    surface_check(fixture, serialized(), update=False)
    tree = json.loads(serialized())
    lines = plant(tree)
    with pytest.raises(AssertionError) as failed:
        surface_check(fixture, canonical(tree), update=False)
    assert str(failed.value).splitlines()[1:] == lines, str(failed.value)


@pytest.mark.unit
def test_update_mode_regenerates_a_conflicted_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    served = serialized()
    # A fixture holding merge-conflict markers around two JSON halves is written, never read.
    text = served.decode()
    half = len(text) // 2
    conflicted = tmp_path / 'conflicted.json'
    conflicted.write_text(f'<<<<<<< ours\n{text[:half]}\n=======\n{text[half:]}>>>>>>> theirs\n')
    surface_check(conflicted, served, update=True)
    assert conflicted.read_bytes() == served
    surface_check(conflicted, served, update=False)
    # A missing fixture fails with the mode off and creates nothing; the mode writes it.
    missing = tmp_path / 'missing.json'
    with pytest.raises(AssertionError, match='the fixture does not exist'):
        surface_check(missing, served, update=False)
    assert not missing.exists()
    surface_check(missing, served, update=True)
    assert missing.read_bytes() == served
    # Unless the variable is exactly `1`, the baseline compares, fails on a difference and writes nothing.
    planted = tmp_path / 'planted.json'
    planted_bytes = served.replace(b'"cluster-mcp: tools for', b'"planted: tools for', 1)
    assert planted_bytes != served
    planted.write_bytes(planted_bytes)
    monkeypatch.setattr(sys.modules[__name__], 'FIXTURE', planted)
    for value in (None, '0', ''):
        if value is None:
            monkeypatch.delenv(UPDATE, raising=False)
        else:
            monkeypatch.setenv(UPDATE, value)
        with pytest.raises(AssertionError, match='instructions'):
            test_served_surface_matches_baseline()
        assert planted.read_bytes() == planted_bytes, f'{UPDATE}={value!r} wrote the fixture'


# Only a version equal to the served one matches. The decoys are near misses both ways: versions
# that hold the served value as a prefix, a suffix or a part (`4.1.40`, `14.1.4`), and versions that
# are themselves a prefix, a part or a suffix of it (`4.1`, `.1.`, `1.4`).
@pytest.mark.unit
@pytest.mark.parametrize(('served', 'installed', 'source'), [
    pytest.param('4.1.4', {'a': '4.1.40', 'b': '4.1.4', 'c': '14.1.4', 'd': None, 'e': '4.1', 'f': '.1.', 'g': '1.4'},
                 'b', id='one'),
    pytest.param(None, {'a': '4.1.40', 'b': '14.1.4', 'd': None, 'e': '4.1', 'f': '.1.', 'g': '1.4'}, None, id='none'),
    pytest.param('4.1.4', {'a': '4.1.4', 'b': '4.1.4', 'c': '4.1.40', 'd': None}, None, id='several'),
])
def test_version_source_names_exactly_one_distribution(served: Any, installed: dict[str, str | None],
                                                       source: str | None) -> None:
    if source is not None:
        assert version_source(served, installed) == source
        return
    with pytest.raises(ValueError) as refused:
        version_source(served, installed)
    message = str(refused.value)
    assert repr(served) in message, message
    for name, version in installed.items():
        assert f'{name} {version if version is not None else "(not installed)"}' in message, message


@pytest.mark.unit
def test_no_workflow_or_script_turns_the_update_mode_on() -> None:
    # A line that names the variable sets or exports it, but for a shell `unset` of it.
    names = re.compile(rf'\b{UPDATE}\b')
    unsets = re.compile(rf'^\s*unset\b[^#\n]*\b{UPDATE}\b')

    def turns_on(text: str) -> list[str]:
        return [line for line in text.splitlines() if names.search(line) and not unsets.match(line)]

    for sample in (f'export {UPDATE}=1', f'      {UPDATE}: "1"', f'{UPDATE}=1 uv run pytest',
                   f"os.environ['{UPDATE}'] = '1'"):
        assert turns_on(sample) == [sample], sample
    assert turns_on(f'unset MCP_BASE_URL {UPDATE}') == []
    files = [p for d in ('.github/workflows', 'bin') for p in sorted((REPO / d).glob('*')) if p.is_file()]
    assert any(p.parent.name == 'workflows' for p in files) and any(p.parent.name == 'bin' for p in files), files
    found = {str(p.relative_to(REPO)): hits for p in files
             if (hits := turns_on(p.read_text(encoding='utf-8', errors='replace')))}
    assert found == {}, found


# What the server starts serving reaches the serialization with no change to the recorder or the
# serializer. Each row plants through FastMCP's public API (a component registered with the key, a
# server option) or a listing middleware that serves an existing entry with a key added, never by
# touching the recorder; the row names where the planted value is recorded and the one line it adds
# to the serialization, under the selected era and a set id of the rows' own.

def planted_echo(text: str) -> str:
    """Echo `text` back."""
    return text


def planted_text() -> str:
    """A planted resource."""
    return 'planted'


def planted_item(item: str) -> str:
    """A planted resource template."""
    return item


def planted_prompt(topic: str) -> str:
    """A planted prompt."""
    return topic


ICON = {'src': 'https://planted.invalid/icon.png'}
PLANTED_TEMPLATE = 'cluster://planted/{item}'
PLANTED_SET = 'planted'


class Relisted(Middleware):
    """Serve each listed tool and resource with `update` applied to those named in it (`{name: fields}`):
    what a server starting to serve a key looks like."""

    def __init__(self, update: dict[str, dict[str, Any]]) -> None:
        super().__init__()
        self.update = update

    def _relist(self, items: Any, key: Any) -> list[Any]:
        return [item.model_copy(update=self.update[key(item)]) if key(item) in self.update else item for item in items]

    async def on_list_tools(self, context: Any, call_next: Any) -> Any:
        return self._relist(await call_next(context), lambda tool: tool.name)

    async def on_list_resources(self, context: Any, call_next: Any) -> Any:
        return self._relist(await call_next(context), lambda resource: str(resource.uri))


class Reordered(Middleware):
    """List the tools in the opposite order on every second listing: a listing that changed between
    two pages, so a paginating client is served the same tool on both."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def on_list_tools(self, context: Any, call_next: Any) -> Any:
        tools = list(await call_next(context))
        self.calls += 1
        return tools if self.calls % 2 else tools[::-1]


def _full(plant: Any) -> Any:
    def build() -> Any:
        server = create_mcp_server('none', site=SITE)
        plant(server)
        return server
    return build


def _middleware(update: dict[str, dict[str, Any]]) -> Any:
    return _full(lambda server: server.add_middleware(Relisted(update)))


# (server builder, path of the planted value in the record, the value, the path removed to unplant
# it, the one line the plant adds to the serialization).
RECORDER = [
    pytest.param(_middleware({'run_command': {'icons': [ICON]}}), ('tools', 'run_command', 'icons'), [ICON],
                 ('tools', 'run_command', 'icons'), f'- tools.run_command.{ERA}.{PLANTED_SET}.icons: added',
                 id='tool-icons'),
    pytest.param(_middleware({'run_command': {'meta': {'planted': True}}}), ('tools', 'run_command', '_meta', 'planted'),
                 True, ('tools', 'run_command', '_meta', 'planted'),
                 f'- tools.run_command.{ERA}.{PLANTED_SET}._meta.planted: added', id='tool-meta'),
    pytest.param(_full(lambda s: s.tool(planted_echo, annotations={'readOnlyHint': True})),
                 ('tools', 'planted_echo', 'annotations'), {'readOnlyHint': True}, ('tools', 'planted_echo'),
                 '- tools.planted_echo: added', id='tool-annotations'),
    pytest.param(_middleware({'cluster://storage': {'title': 'Storage'}}), ('resources', 'cluster://storage', 'title'),
                 'Storage', ('resources', 'cluster://storage', 'title'),
                 f"- resources['cluster://storage'].{ERA}.{PLANTED_SET}.title: added", id='resource-title'),
    pytest.param(_full(lambda s: s.resource('cluster://planted', annotations={'priority': 0.5})(planted_text)),
                 ('resources', 'cluster://planted', 'annotations'), {'priority': 0.5},
                 ('resources', 'cluster://planted'), "- resources['cluster://planted']: added",
                 id='resource-annotations'),
    pytest.param(_full(lambda s: s.prompt(planted_prompt)), ('prompts', 'planted_prompt', 'description'),
                 'A planted prompt.', ('prompts', 'planted_prompt'), '- prompts.planted_prompt: added', id='prompt'),
    pytest.param(_full(lambda s: s.resource(PLANTED_TEMPLATE)(planted_item)),
                 ('resourceTemplates', PLANTED_TEMPLATE, 'description'), 'A planted resource template.',
                 ('resourceTemplates', PLANTED_TEMPLATE), f"- resourceTemplates['{PLANTED_TEMPLATE}']: added",
                 id='resource-template'),
    pytest.param(_full(lambda s: s.experimental_capabilities.update(planted={'level': 1})),
                 ('capabilities', 'experimental', 'planted'), {'level': 1}, ('capabilities', 'experimental'),
                 f'- capabilities.{ERA}.{PLANTED_SET}.experimental: added', id='experimental-capability'),
    pytest.param(lambda: FastMCP(name='cluster-mcp', version='9.9.9+planted'), ('serverInfo', 'version'),
                 '9.9.9+planted', ('serverInfo', 'version'), f'- serverInfo.{ERA}.{PLANTED_SET}.version: added',
                 id='server-version'),
    pytest.param(lambda: FastMCP(name='cluster-mcp', website_url='https://planted.invalid'),
                 ('serverInfo', 'websiteUrl'), 'https://planted.invalid', ('serverInfo', 'websiteUrl'),
                 f'- serverInfo.{ERA}.{PLANTED_SET}.websiteUrl: added', id='server-website-url'),
]


@pytest.mark.unit
@pytest.mark.parametrize(('build', 'path', 'value', 'unplant', 'line'), RECORDER)
def test_recorder_sees_what_the_server_starts_serving(build: Any, path: FieldPath, value: Any, unplant: FieldPath,
                                                      line: str) -> None:
    served = served_surface(build())
    assert _holder(served, path[:-1]).get(path[-1], KeyError) == value, \
        f'{render_path(path)} is not recorded as served: {_holder(served, path[:1])!r}'
    unplanted = copy.deepcopy(served)
    del _holder(unplanted, unplant[:-1])[unplant[-1]]
    assert differences(serialization({(ERA, PLANTED_SET): unplanted}),
                       serialization({(ERA, PLANTED_SET): served})) == [line]


@pytest.mark.unit
def test_recorder_follows_every_page() -> None:
    server = FastMCP(name='paged', list_page_size=1)
    for name in ('planted_a', 'planted_b', 'planted_c'):
        server.tool(planted_echo, name=name)
    for uri in ('cluster://planted/a', 'cluster://planted/b'):
        server.resource(uri)(planted_text)
    for template in ('cluster://planted/x/{item}', 'cluster://planted/y/{item}'):
        server.resource(template)(planted_item)
    for name in ('planted_p', 'planted_q'):
        server.prompt(planted_prompt, name=name)
    served = served_surface(server)
    assert list(served['tools']) == ['planted_a', 'planted_b', 'planted_c']
    assert list(served['resources']) == ['cluster://planted/a', 'cluster://planted/b']
    assert list(served['resourceTemplates']) == ['cluster://planted/x/{item}', 'cluster://planted/y/{item}']
    assert list(served['prompts']) == ['planted_p', 'planted_q']


@pytest.mark.unit
def test_recorder_refuses_a_name_served_twice() -> None:
    server = FastMCP(name='paged', list_page_size=1, middleware=[Reordered()])
    for name in ('planted_a', 'planted_b'):
        server.tool(planted_echo, name=name)
    with pytest.raises(ValueError, match="the tools listing serves name 'planted_a' twice"):
        served_surface(server)


SERVER_INFO_META = 'io.modelcontextprotocol/serverInfo'


@pytest.mark.unit
@pytest.mark.parametrize('era', ERAS)
def test_record_keeps_keys_no_model_declares(era: str) -> None:
    # No server can be made to send a key the SDK's models lack (the server and the client share them),
    # so the pure step from raw results is fed one, at every place the record reads.
    info = {'name': 'cluster-mcp', 'version': '1', 'plantedInfo': {'deep': [1]}}
    capabilities = {'tools': {'listChanged': True, 'plantedInTools': 1}, 'plantedCapability': {}}
    identity = ({'serverInfo': info, 'capabilities': capabilities, 'instructions': 'i'} if era == 'legacy' else
                {'_meta': {SERVER_INFO_META: info}, 'capabilities': capabilities, 'instructions': 'i'})
    listings = {'tools': [{'name': 't', 'plantedTool': 1, 'inputSchema': {'type': 'object', 'x-planted': [2]}}],
                'resources': [{'uri': 'cluster://u', 'plantedResource': {'a': None}}],
                'resourceTemplates': [{'uriTemplate': 'cluster://u/{x}', 'plantedTemplate': True}],
                'prompts': [{'name': 'p', 'plantedPrompt': 0}]}
    record = surface_record(listings, identity, era)
    assert record == {
        'instructions': 'i',
        'tools': {'t': {'plantedTool': 1, 'inputSchema': {'type': 'object', 'x-planted': [2]}}},
        'resources': {'cluster://u': {'plantedResource': {'a': None}}},
        'resourceTemplates': {'cluster://u/{x}': {'plantedTemplate': True}},
        'prompts': {'p': {'plantedPrompt': 0}},
        'serverInfo': info,
        'capabilities': capabilities,
    }
