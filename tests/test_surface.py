# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The served surface matches the snapshot taken from the server before the stack move.

`tests/fixtures/served_surface.json` is what the server at `3d010ec` (FastMCP 2.x) served to a
handshake-era client: every tool's description and input and output schemas, every resource's URI,
name, description and MIME type, and the instructions. It was written by
`spec/stack-upgrade/verify/snapshot.py` run in an archive of that commit, in that commit's own
locked environment, never on the current stack; the cycle's gates re-derive it there and require
the committed file to be identical. A deliberate surface change since then is a scripted hand-edit
of the named deltas only, in the snapshot's shape, listed in AGENTS.md § Testing: so far
`run_command.description`, `write_file.description`, `write_file.properties.encoding`,
`sbatch.description`, `sbatch.properties.args`, and `description` and `properties.extra_args` on
each of `sbatch`, `squeue`, `scancel`, `sacct` and `sinfo` (`safe-execution`); `instructions`, the
base composed with the harness's site context, `tools.cluster_context`, the new tool in `myquota`'s
schema shape with its docstring as the description, and `resources.rcac://context.description`
(`agents-d-instructions`); `resources.cluster://context` and `resources.cluster://storage`, each a
copy of its `rcac://` entry, which stays as it was: the `rcac://` URIs are served on as deprecated
aliases; and `instructions`, the base (now the generic core, the Slurm snippet and the RCAC-specific
overlay) composed with the harness's site context (`rename-to-cluster-mcp`). The server's name is
not in the snapshot's shape; `test_protocol.py` pins it.

No tool entry in the snapshot has an `annotations` key: neither `3d010ec` nor 0.1.4 served tool
annotations, and `served_surface` records the key only for a tool served with them. So the
comparison covers annotations with no fixture change: a tool that gains them shows as an entry with
a key the snapshot's lacks. Nor has any a `title` key, the snapshot's shape having none. FastMCP 4,
the stack 0.1.4 already ran on, serves every tool without a title of its own a display title
derived from its name (`run_command` is "Run Command"); `served_surface` records a tool's title
whenever one is served, so that derived title is the one tolerated difference in titles, and the
fixture needs no change.

`surface_violations` compares what a client in the selected era is served now (`served_surface`)
with the snapshot. No tool, argument, required argument, argument type or default, description,
annotation, title, resource or instruction may differ: a tool's annotations differ when either side
has them and the other has not, or when a hint is on one side only or has another value; its title
differs when the snapshot has one and the served tool has none or another, or when the served tool
has one the snapshot lacks other than the title derived from its name. Five kinds of generated
metadata differ on FastMCP 4, each for a stated cause (`TOLERATED`), and each is accepted only in
its own shape: a tool's title derived from its name, only where the snapshot has none; a
`description` added to an argument that had none;
`additionalProperties` added to an input schema, and only as exactly `false`; an output schema's
`$defs` inlined where they were referenced; and a `description` added on an inlined output node,
only where the snapshot had a `$ref`. Anything else is a violation. `tolerated_differences` lists
the accepted differences per tool, for the record of the change.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from harness import CONTEXT_URIS, SITE, STORAGE_URIS, scheme, served_surface
from cluster_mcp.core.server import create_mcp_server
from test_registry import EXPECTED_TOOLS

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'served_surface.json'

# Each accepted difference kind, with its cause.
TOLERATED: dict[str, str] = {
    'derived-title': 'FastMCP 4 serves a tool with no title of its own a display title derived from its name, '
                     'which 0.1.4 served too',
    'argument-description': "FastMCP 4 copies each docstring `Args:` line into that argument's schema as its "
                            '`description`',
    'additional-properties': 'FastMCP 4 advertises `additionalProperties: false`, the rejection of an unknown '
                             'argument that both stacks already enforce',
    'output-defs-inlined': "FastMCP 4 dereferences an output schema's `$defs`, inlining each model where it "
                           'was referenced',
    'output-model-description': "inlining carries a model class's docstring onto the node that was its `$ref`",
}

DEFS_PREFIX = '#/$defs/'


def derived_title(name: str) -> str:
    """The display title FastMCP 4 derives from tool name `name`: each `_` or `-` a space, each word capitalised."""
    return name.replace('_', ' ').replace('-', ' ').title()

NodePath = tuple[Any, ...]


def load_fixture() -> dict[str, Any]:
    """The snapshot of the surface served before the stack move."""
    return json.loads(FIXTURE.read_text())


def inline_defs(schema: Any) -> tuple[Any, set[NodePath]]:
    """`schema` with each local `$ref` replaced by its `$defs` entry and `$defs` dropped.

    Also returns the paths (key and index tuples from the root) of the nodes that were a `$ref`. A
    schema without `$defs` comes back as a copy, with no paths. A model that refers to itself keeps
    its inner `$ref`.
    """
    if not isinstance(schema, dict) or '$defs' not in schema:
        return copy.deepcopy(schema), set()
    defs = schema['$defs']
    targets: set[NodePath] = set()

    def walk(node: Any, path: NodePath, active: frozenset[str]) -> Any:
        if isinstance(node, dict):
            ref = node.get('$ref')
            if isinstance(ref, str) and ref.startswith(DEFS_PREFIX):
                name = ref[len(DEFS_PREFIX):]
                if name in defs and name not in active:
                    targets.add(path)
                    merged = {**defs[name], **{k: v for k, v in node.items() if k != '$ref'}}
                    return walk(merged, path, active | {name})
            return {k: walk(v, path + (k,), active) for k, v in node.items() if not (path == () and k == '$defs')}
        if isinstance(node, list):
            return [walk(v, path + (i,), active) for i, v in enumerate(node)]
        return copy.deepcopy(node)

    return walk(schema, (), frozenset()), targets


def _where(path: NodePath) -> str:
    return '.'.join(str(p) for p in path) or '(root)'


class _Comparison:
    """Every violation, and every tolerated difference per tool, between a snapshot and a served surface."""

    def __init__(self) -> None:
        self.violations: list[str] = []
        self.tolerated: dict[str, list[str]] = {}

    def tolerate(self, tool: str, kind: str, detail: str = '') -> None:
        assert kind in TOLERATED, kind
        self.tolerated.setdefault(tool, []).append(f'{kind}: {detail}' if detail else kind)

    def surface(self, snapshot: dict[str, Any], served: dict[str, Any]) -> None:
        if snapshot.get('instructions') != served.get('instructions'):
            self.violations.append('instructions differ')
        base_tools, head_tools = snapshot.get('tools', {}), served.get('tools', {})
        for name in sorted(set(base_tools) - set(head_tools)):
            self.violations.append(f'tool missing: {name}')
        for name in sorted(set(head_tools) - set(base_tools)):
            self.violations.append(f'tool added: {name}')
        for name in sorted(set(base_tools) & set(head_tools)):
            self.tool(name, base_tools[name], head_tools[name])
        self.resources(snapshot.get('resources', {}), served.get('resources', {}))

    def tool(self, name: str, base: dict[str, Any], head: dict[str, Any]) -> None:
        for key in sorted((set(base) ^ set(head)) - {'title'}):
            self.violations.append(f'{name}: tool entry {"lost" if key in base else "gained"} {key!r}')
        self.title(name, base.get('title'), head.get('title'))
        if base.get('description') != head.get('description'):
            self.violations.append(f'{name}: description differs')
        self.annotations(name, base.get('annotations'), head.get('annotations'))
        self.input_schema(name, base.get('inputSchema') or {}, head.get('inputSchema') or {})
        self.output_schema(name, base.get('outputSchema'), head.get('outputSchema'))

    def title(self, tool: str, base: Any, head: Any) -> None:
        if base is None and head is None:
            return
        if base is None and head == derived_title(tool):
            self.tolerate(tool, 'derived-title', repr(head))
        elif base is None:
            self.violations.append(f'{tool}: tool entry gained the title {head!r}, not the derived {derived_title(tool)!r}')
        elif head is None:
            self.violations.append(f'{tool}: tool entry lost the title {base!r}')
        elif base != head:
            self.violations.append(f'{tool}: title differs: {base!r} -> {head!r}')

    def annotations(self, tool: str, base: Any, head: Any) -> None:
        if not (isinstance(base, dict) and isinstance(head, dict)):
            if base != head:
                self.violations.append(f'{tool}: annotations differ: {base!r} -> {head!r}')
            return
        for hint in sorted(set(base) | set(head)):
            if hint not in base:
                self.violations.append(f'{tool}: annotations gained hint {hint!r}')
            elif hint not in head:
                self.violations.append(f'{tool}: annotations lost hint {hint!r}')
            elif base[hint] != head[hint]:
                self.violations.append(f'{tool}: annotation {hint} differs: {base[hint]!r} -> {head[hint]!r}')

    def input_schema(self, tool: str, base: dict[str, Any], head: dict[str, Any]) -> None:
        for key in sorted(set(base) | set(head)):
            if key in ('properties', 'required'):
                continue
            if key == 'additionalProperties' and key not in base:
                if head[key] is False:
                    self.tolerate(tool, 'additional-properties')
                else:
                    self.violations.append(f'{tool}: additionalProperties is {head[key]!r}, expected false')
            elif key not in base:
                self.violations.append(f'{tool}: input schema gained untolerated key {key!r}')
            elif key not in head:
                self.violations.append(f'{tool}: input schema lost key {key!r}')
            elif base[key] != head[key]:
                self.violations.append(f'{tool}: input schema {key} differs: {base[key]!r} -> {head[key]!r}')
        if base.get('required', []) != head.get('required', []):
            self.violations.append(f'{tool}: required differs: {base.get("required", [])} -> {head.get("required", [])}')
        base_props, head_props = base.get('properties', {}), head.get('properties', {})
        for arg in sorted(set(base_props) - set(head_props)):
            self.violations.append(f'{tool}: argument dropped: {arg}')
        for arg in sorted(set(head_props) - set(base_props)):
            self.violations.append(f'{tool}: argument added: {arg}')
        described: list[str] = []
        for arg in [a for a in head_props if a in base_props]:
            old, new = base_props[arg], head_props[arg]
            for key in sorted(set(old) | set(new)):
                if key == 'description' and key not in old and isinstance(new[key], str):
                    described.append(arg)
                elif key not in old:
                    self.violations.append(f'{tool}: argument {arg} gained untolerated key {key!r}')
                elif key not in new:
                    self.violations.append(f'{tool}: argument {arg} lost {key!r}')
                elif old[key] != new[key]:
                    self.violations.append(f'{tool}: argument {arg} {key} differs: {old[key]!r} -> {new[key]!r}')
        if described:
            self.tolerate(tool, 'argument-description', ', '.join(described))

    def output_schema(self, tool: str, base: Any, head: Any) -> None:
        if base is None or head is None:
            if base != head:
                self.violations.append(f'{tool}: output schema differs: {base!r} -> {head!r}')
            return
        inlined, targets = inline_defs(base)
        served, _ = inline_defs(head)
        if '$defs' in base and '$defs' not in head:
            self.tolerate(tool, 'output-defs-inlined', ', '.join(sorted(base['$defs'])))
        self.output_node(tool, inlined, served, (), targets)

    def output_node(self, tool: str, base: Any, head: Any, path: NodePath, targets: set[NodePath]) -> None:
        if isinstance(base, dict) and isinstance(head, dict):
            for key in sorted(set(base) | set(head)):
                if key not in base:
                    if key == 'description' and path in targets and isinstance(head[key], str):
                        self.tolerate(tool, 'output-model-description', _where(path))
                    else:
                        self.violations.append(f'{tool}: output schema at {_where(path)} gained untolerated key {key!r}')
                elif key not in head:
                    self.violations.append(f'{tool}: output schema at {_where(path)} lost {key!r}')
                else:
                    self.output_node(tool, base[key], head[key], path + (key,), targets)
        elif isinstance(base, list) and isinstance(head, list) and len(base) == len(head):
            for i, (old, new) in enumerate(zip(base, head)):
                self.output_node(tool, old, new, path + (i,), targets)
        elif base != head:
            self.violations.append(f'{tool}: output schema at {_where(path)} differs: {base!r} -> {head!r}')

    def resources(self, base: dict[str, Any], head: dict[str, Any]) -> None:
        for uri in sorted(set(base) - set(head)):
            self.violations.append(f'resource missing: {uri}')
        for uri in sorted(set(head) - set(base)):
            self.violations.append(f'resource added: {uri}')
        for uri in sorted(set(base) & set(head)):
            for key in sorted(set(base[uri]) | set(head[uri])):
                if base[uri].get(key) != head[uri].get(key):
                    self.violations.append(f'resource {uri}: {key} differs')


def _compare(snapshot: dict[str, Any], served: dict[str, Any]) -> _Comparison:
    comparison = _Comparison()
    comparison.surface(snapshot, served)
    return comparison


def surface_violations(snapshot: dict[str, Any], served: dict[str, Any]) -> list[str]:
    """Every way `served` differs from `snapshot` that no `TOLERATED` kind accounts for."""
    return _compare(snapshot, served).violations


def tolerated_differences(snapshot: dict[str, Any], served: dict[str, Any]) -> dict[str, list[str]]:
    """Per tool, each accepted difference between `snapshot` and `served`: `<kind>[: <detail>]`."""
    return _compare(snapshot, served).tolerated


@pytest.mark.unit
def test_served_surface_matches_baseline() -> None:
    served = served_surface(create_mcp_server('none', site=SITE))
    assert served['tools'], 'the server listed no tools'
    violations = surface_violations(load_fixture(), served)
    assert violations == [], '\n'.join(violations)
    # 0.1.4 served every tool a title, FastMCP 4's derived one. The snapshot's shape has none, so this
    # is what fails on one lost.
    untitled = sorted(name for name, tool in served['tools'].items() if 'title' not in tool)
    assert untitled == [], f'served without the title 0.1.4 served: {untitled}'


@pytest.mark.unit
def test_surface_fixture_is_the_baseline_shape() -> None:
    snapshot = load_fixture()
    assert sorted(snapshot) == ['instructions', 'resources', 'tools']
    assert isinstance(snapshot['instructions'], str) and snapshot['instructions']
    assert sorted(snapshot['tools']) == sorted(EXPECTED_TOOLS)
    assert sorted(snapshot['resources']) == sorted((*CONTEXT_URIS, *STORAGE_URIS))
    for name, tool in snapshot['tools'].items():
        # No `annotations` key: no tool was served with annotations; and no `title` key, which the
        # snapshot's shape lacks.
        assert sorted(tool) == ['description', 'inputSchema', 'outputSchema'], name
        assert isinstance(tool['description'], str) and tool['description'], name
        # The metadata FastMCP 4 adds is absent: the snapshot was not taken on the new stack.
        assert 'additionalProperties' not in tool['inputSchema'], name
        assert all('description' not in arg for arg in tool['inputSchema'].get('properties', {}).values()), name
    # The output models are referenced through `$defs`, as FastMCP 2.x served them.
    assert any('$defs' in (tool['outputSchema'] or {}) for tool in snapshot['tools'].values())


def _plant(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    planted = load_fixture()
    change(planted)
    return planted


def _rename(s: dict[str, Any]) -> None:
    s['tools']['run_command_v2'] = s['tools'].pop('run_command')


def _input(s: dict[str, Any]) -> dict[str, Any]:
    return s['tools']['run_command']['inputSchema']


def _summary_only(s: dict[str, Any]) -> None:
    tool = s['tools']['run_command']
    tool['description'] = tool['description'].split('\n\n')[0]


# Annotations as a server would send them for one tool: two hints.
HINTS = {'readOnlyHint': True, 'destructiveHint': False}


def _annotate(s: dict[str, Any], tool: str = 'run_command', hints: dict[str, Any] | None = None) -> None:
    s['tools'][tool]['annotations'] = dict(HINTS if hints is None else hints)


def _annotate_all(s: dict[str, Any]) -> None:
    for name in s['tools']:
        _annotate(s, name)


def _both_annotated(head: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The snapshot and `head`, each with `run_command` served with `HINTS` beforehand."""
    return _plant(_annotate), head


# Each way a tool's annotations can differ, as (snapshot, served): annotations on one side only,
# either side; a hint on one side only, either side; a hint's value; and empty annotations against none.
ANNOTATION_DRIFT = [
    pytest.param(lambda: (load_fixture(), _plant(_annotate_all)), "tool entry gained 'annotations'",
                 id='annotations-added-to-every-tool'),
    pytest.param(lambda: (load_fixture(), _plant(_annotate)), "run_command: tool entry gained 'annotations'",
                 id='annotations-added-to-one-tool'),
    pytest.param(lambda: (_plant(_annotate), load_fixture()), "run_command: tool entry lost 'annotations'",
                 id='annotations-removed'),
    pytest.param(lambda: (load_fixture(), _plant(lambda s: _annotate(s, hints={}))),
                 "run_command: tool entry gained 'annotations'", id='empty-annotations-added'),
    pytest.param(lambda: _both_annotated(_plant(lambda s: _annotate(s, hints={**HINTS, 'readOnlyHint': False}))),
                 'run_command: annotation readOnlyHint differs: True -> False', id='hint-flipped'),
    pytest.param(lambda: _both_annotated(_plant(lambda s: _annotate(s, hints={'readOnlyHint': True}))),
                 "run_command: annotations lost hint 'destructiveHint'", id='hint-removed'),
    pytest.param(lambda: _both_annotated(_plant(lambda s: _annotate(s, hints={**HINTS, 'idempotentHint': True}))),
                 "run_command: annotations gained hint 'idempotentHint'", id='hint-added'),
    pytest.param(lambda: _both_annotated(_plant(lambda s: _annotate(s, hints={**HINTS, 'readOnlyHint': None}))),
                 'run_command: annotation readOnlyHint differs: True -> None', id='hint-nulled'),
    pytest.param(lambda: _both_annotated(_plant(lambda s: _annotate(s, hints={}))),
                 "run_command: annotations lost hint 'readOnlyHint'", id='hints-emptied'),
]


def _title(s: dict[str, Any], tool: str = 'run_command', title: str = 'Run a command') -> None:
    s['tools'][tool]['title'] = title


def _title_all(s: dict[str, Any]) -> None:
    for name in s['tools']:
        _title(s, name, name)


# Each way a tool's top-level title can differ, as (snapshot, served): a title other than the derived
# one, on one tool or every tool, an empty one, the derived one's case changed; a title the snapshot
# has, lost, replaced by the derived one, or changed.
TITLE_DRIFT = [
    pytest.param(lambda: (load_fixture(), _plant(_title_all)), "tool entry gained the title 'run_command'",
                 id='title-added-to-every-tool'),
    pytest.param(lambda: (load_fixture(), _plant(_title)),
                 "run_command: tool entry gained the title 'Run a command', not the derived 'Run Command'",
                 id='title-added-to-one-tool'),
    pytest.param(lambda: (load_fixture(), _plant(lambda s: _title(s, title=''))), "run_command: tool entry gained the title ''",
                 id='empty-title-added'),
    pytest.param(lambda: (load_fixture(), _plant(lambda s: _title(s, title='Run command'))),
                 "run_command: tool entry gained the title 'Run command'", id='derived-title-recased'),
    pytest.param(lambda: (_plant(_title), load_fixture()), "run_command: tool entry lost the title 'Run a command'",
                 id='title-removed'),
    pytest.param(lambda: (_plant(_title), _plant(lambda s: _title(s, title='Run Command'))),
                 "run_command: title differs: 'Run a command' -> 'Run Command'", id='title-replaced-by-derived'),
    pytest.param(lambda: (_plant(_title), _plant(lambda s: _title(s, title='Run command'))),
                 "run_command: title differs: 'Run a command' -> 'Run command'", id='title-changed'),
]


def _drift_violations(pair: Callable[[], tuple[dict[str, Any], dict[str, Any]]]) -> list[str]:
    snapshot, served = pair()
    assert snapshot != served, 'the planted difference did not land'
    assert surface_violations(snapshot, snapshot) == [] and surface_violations(served, served) == []
    return surface_violations(snapshot, served)


@pytest.mark.unit
@pytest.mark.parametrize(('pair', 'fragment'), ANNOTATION_DRIFT)
def test_surface_check_catches_annotation_drift(pair: Callable[[], tuple[dict[str, Any], dict[str, Any]]],
                                                fragment: str) -> None:
    violations = _drift_violations(pair)
    assert any(fragment in v for v in violations), violations


@pytest.mark.unit
@pytest.mark.parametrize(('pair', 'fragment'), TITLE_DRIFT)
def test_surface_check_catches_title_drift(pair: Callable[[], tuple[dict[str, Any], dict[str, Any]]],
                                           fragment: str) -> None:
    violations = _drift_violations(pair)
    assert any(fragment in v for v in violations), violations


@pytest.mark.unit
@pytest.mark.parametrize(('change', 'fragment'), [
    pytest.param(_rename, 'tool missing: run_command', id='renamed-tool'),
    pytest.param(lambda s: _input(s)['properties'].pop('cwd'), 'run_command: argument dropped: cwd',
                 id='dropped-argument'),
    pytest.param(lambda s: _input(s).update(required=[]), 'run_command: required differs', id='required-changed'),
    pytest.param(lambda s: _input(s)['properties']['command'].update(type='integer'),
                 'run_command: argument command type differs', id='type-changed'),
    pytest.param(lambda s: _input(s)['properties']['cwd'].update(default='~'),
                 'run_command: argument cwd default differs', id='default-changed'),
    pytest.param(_summary_only, 'run_command: description differs', id='description-changed'),
    *(pytest.param(lambda s, uri=uri: s['resources'].pop(uri), f'resource missing: {uri}',
                   id=f'resource-dropped-{scheme(uri)}') for uri in STORAGE_URIS),
    pytest.param(lambda s: s.update(instructions=s['instructions'] + '\nUse the docs tool.'), 'instructions differ',
                 id='instructions-changed'),
    pytest.param(lambda s: s['tools']['run_command']['outputSchema']['properties']['exit_code'].update(type='string'),
                 'run_command: output schema at properties.exit_code.type differs', id='output-changed'),
    pytest.param(lambda s: _input(s).update(title='run_commandArguments'),
                 "run_command: input schema gained untolerated key 'title'", id='untolerated-key'),
    pytest.param(lambda s: _input(s).update(additionalProperties=True),
                 'run_command: additionalProperties is True, expected false', id='additional-properties-true'),
    pytest.param(lambda s: s['tools']['run_command']['outputSchema']['properties']['stdout'].update(description='Out.'),
                 "run_command: output schema at properties.stdout gained untolerated key 'description'",
                 id='output-description-on-a-plain-node'),
])
def test_surface_check_catches_drift(change: Callable[[dict[str, Any]], None], fragment: str) -> None:
    snapshot = load_fixture()
    assert surface_violations(snapshot, load_fixture()) == []
    violations = surface_violations(snapshot, _plant(change))
    assert any(fragment in v for v in violations), violations


def _describe_argument(s: dict[str, Any]) -> None:
    _input(s)['properties']['command']['description'] = 'The shell command to execute.'


def _inline_listing(s: dict[str, Any]) -> None:
    tool = s['tools']['list_directory']
    tool['outputSchema'] = inline_defs(tool['outputSchema'])[0]


def _describe_model(s: dict[str, Any]) -> None:
    _inline_listing(s)
    s['tools']['list_directory']['outputSchema']['properties']['result']['items']['description'] = 'One entry.'


@pytest.mark.unit
@pytest.mark.parametrize(('change', 'tool', 'kind'), [
    pytest.param(_describe_argument, 'run_command', 'argument-description: command', id='argument-description'),
    pytest.param(lambda s: _input(s).update(additionalProperties=False), 'run_command', 'additional-properties',
                 id='additional-properties'),
    pytest.param(_inline_listing, 'list_directory', 'output-defs-inlined: FileInfo', id='output-defs-inlined'),
    pytest.param(_describe_model, 'list_directory', 'output-model-description: properties.result.items',
                 id='output-model-description'),
    pytest.param(lambda s: _title(s, title='Run Command'), 'run_command', "derived-title: 'Run Command'", id='derived-title'),
    pytest.param(lambda s: _title(s, 'scontrol_show_job', 'Scontrol Show Job'), 'scontrol_show_job',
                 "derived-title: 'Scontrol Show Job'", id='derived-title-of-three-words'),
])
def test_surface_check_tolerates_listed_differences(change: Callable[[dict[str, Any]], None], tool: str,
                                                    kind: str) -> None:
    snapshot = load_fixture()
    planted = _plant(change)
    assert planted != snapshot, 'the planted difference did not land'
    assert surface_violations(snapshot, planted) == []
    tolerated = tolerated_differences(snapshot, planted)
    assert kind in tolerated.get(tool, []), tolerated
    assert all(entry.split(':')[0] in TOLERATED for entries in tolerated.values() for entry in entries)
