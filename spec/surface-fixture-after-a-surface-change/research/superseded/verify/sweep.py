"""The comparison, recorder and command sweep of surface-fixture-after-a-surface-change (PLAN § 6).

Usage, from the worktree root:  uv run python -I spec/surface-fixture-after-a-surface-change/verify/sweep.py [MUTANT_ID...]

Each mutant attacks one planned decision of the comparison (`tests/test_surface.py`), the recorder
(`tests/harness.py`) or the surface command (`bin/record_surface.py`). Per mutant, the sweep copies
this worktree's `tests/`, `bin/`, `.github/` and top-level files into a fresh directory, plants the
one edit there (its anchor must occur exactly once), and runs its target in a child under this
worktree's `bin/sandbox.sh`, with this worktree's environment, the child carrying the word
`surface-sweep-child` in its argv:

- a pytest target: the named tests in the copy, judged per test by `mutants.mutation_violations`
  (each must fail, carrying its own `why`, not error or skip);
- a drive target: `command_drive.py all` with `SURFACE_CODE_ROOT` naming the copy, judged by its
  exit status and its FAIL message.

A recorder mutant that ignores the era it is asked for is targeted by the other era's row only: the
selected era's row passes under it by construction, and the handshake-era run kills it.

After every child, the copy's fixture must still be the staged fixture: a mutant that writes the
fixture is killed there. Each mutant's pytest targets run in both protocol eras, and it is killed
when either era kills it. A mutant marked equivalent is run and reported, with the reason no control
can reach it; its survival is not a failure.

Writes `spec/surface-fixture-after-a-surface-change/verify/sweep-report.txt` (verdicts only, no
timings, so a re-run on the same tree writes the same bytes) and exits 1 when any mutant that is
not equivalent survives. One child at a time; each bounded in its own process group (300 s for
pytest, 900 s for the drive). Footprint: one child process tree at a time, under 1 GB.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path.cwd()
SPEC = ROOT / 'spec' / 'surface-fixture-after-a-surface-change'
SANDBOX = ROOT / 'bin' / 'sandbox.sh'
FIXTURE = 'tests/fixtures/served_surface.json'
REPORT = SPEC / 'verify' / 'sweep-report.txt'
MARK = 'surface-sweep-child'
COPIED_DIRS = ('tests', 'bin', '.github')
COPIED_FILES = ('README.md', 'AGENTS.md', 'pyproject.toml', 'uv.lock')
ENVIRON = dict(os.environ)

sys.path.insert(0, str(ROOT / 'tests'))
import mutants  # noqa: E402 - the runner's verdict on a child pytest's JUnit report

TS, HARNESS, COMMAND = 'tests/test_surface.py', 'tests/harness.py', 'bin/record_surface.py'
MATCHED = '_matches('


def drift(*ids: str, why: str = MATCHED) -> tuple[tuple[str, str], ...]:
    return tuple((f'test_surface.py::test_surface_check_catches_drift[{i}]', why) for i in ids)


def sets(*ids: str, why: str = MATCHED) -> tuple[tuple[str, str], ...]:
    return tuple((f'test_surface.py::test_set_check_catches_drift[{i}]', why) for i in ids)


def test(name: str, why: str) -> tuple[tuple[str, str], ...]:
    return ((f'test_surface.py::{name}', why),)


@dataclass(frozen=True)
class Mutant:
    id: str
    decision: str
    file: str
    old: str
    new: str
    targets: tuple[tuple[str, str], ...] = ()
    drive: str | None = None  # a fragment the drive's FAIL output must carry
    fixture_write: bool = False  # killed by the fixture check rather than a failing target
    eras: tuple[str, ...] = ('legacy', 'modern')
    equivalent: str | None = None

    @property
    def drives(self) -> bool:
        return self.drive is not None or (self.fixture_write and not self.targets)


ADDED = "                found.append(Difference(path + (key,), 'added', None, new[key]))\n"
REMOVED = "                found.append(Difference(path + (key,), 'removed', old[key], None))\n"
DICT_LOOP = "        for key in sorted(set(old) | set(new)):\n"
LIST_LOOP = "        for index in range(max(len(old), len(new))):\n"
LEAF = "    elif isinstance(old, (dict, list)) or isinstance(new, (dict, list)) or not _same(old, new):\n"
SAME = "    return type(old) is type(new) and old == new\n"
EXPECTED_ERA = "            expected[ERA_CAPABILITIES[0]] = recorded[era]\n"
VERSION_SHAPE = "        if not isinstance(distribution, str):\n"
RETURN_EXPECTED = "    return expected, problems\n"
SET_CUT = "            expected[listing] = {k: v for k, v in expected[listing].items() if k in served[listing]}\n"
SET_WITHOUT = "    expected, served = _without(expected, 'instructions'), _without(served, 'instructions')\n"
ERA_WITHOUT = "    return surface_violations(_without(legacy, ERA_CAPABILITIES[0]), _without(modern, ERA_CAPABILITIES[0]))\n"
DELTA = "    lines = sorted({f'- {render_path(d.path)}: {d.kind}' for d in surface_differences(old, new)})\n"
BYTES = "    return (json.dumps(fixture, indent=1, sort_keys=True) + '\\n').encode()\n"
SOURCE_LOOP = "    if len(found) != 1:\n"
SETS_LOOP = "    sets = [(param.id, param.values[0]) for param in test_capabilities.SETS]\n"
BASELINE = "    violations = surface_violations(expected, served)\n    assert violations == [], '\\n'.join(violations)\n"
ENTRY = "            entry = dict(served)\n"
DUPLICATE = "            if name in entries:\n"
LISTINGS = "        listings = {key: await _raw_listing(client, request, key) for key, request, _ in SURFACE_LISTINGS}\n"
PAGE_END = "        if cursor is None:\n            return entries\n"
LEGACY_INFO = "        record['serverInfo'] = identity.get('serverInfo')\n"
ERA_CHECK = "    differing = era_violations(records['legacy'], records['modern'])\n"
SELF_CHECK = "    problems = fixture_problems(fixture, records)\n"
COMMAND_DELTA = "    delta = delta_lines(base, fixture)\n"
PYTEST_GUARD = "    if environ.get('PYTEST_CURRENT_TEST'):\n"
# The command's choices, all in `command_main` and its helpers (review cycle 2, N1).
MAIN_REFUSAL = "        if refusal is not None:\n            raise refusal\n"
BASE_AGAINST = "    if against is not None:\n        source = against\n"
BASE_HEAD = "        text = command_head(effects.git)\n"
HEAD_EMPTY = "    if not listed.strip():\n        return None\n"
MAIN_FENCE = "        effects.fence()\n        result = command_result(base, effects.record)\n"
MAIN_OUT = "    effects.out('\\n'.join(result.delta))\n"
MAIN_SOURCE = "{result.summary} against {source}')\n"
# The command file's effects (review cycle 2, N1): each one action, driven.
CMD_WRITE = "    Path(name).write_bytes(data)\n"
CMD_FENCE = "fence=fence,"
CMD_RECORD = "record=surface.command_record,"
CMD_GIT = "['git', '-C', str(ROOT), *args]"
CMD_OUT = "out=print,"
CMD_CALL = "    return surface.command_main(argv, os.environ, effects)\n"
# The walk's key loop, where a tolerated kind would be put back (review cycle 2, N2).
KEY_ADDED = "            elif key not in old:\n"
KEY_REMOVED = "            if key not in new:\n"
KEY_RECURSE = "                _differences(old[key], new[key], path + (key,), found)\n"
ARGUMENT = "len(path) >= 2 and path[-2] == 'properties' and 'inputSchema' in path"
TOOL_TITLE = "key == 'title' and len(path) == 2 and path[0] == 'tools'"
SET_RETURN = "    return surface_violations(expected, served)\n"
SURFACE_ERA = "async def _surface(server: FastMCP, era: str | None) -> dict[str, Any]:\n    era = _era(era)\n"
SERVED_ERA = "    return drive(_surface(server, era))\n"
IDENTITY_BRANCH = "    if era == 'legacy':\n        params = wire.InitializeRequestParams("
MODERN_INFO = "        record['serverInfo'] = (identity.get('_meta') or {}).get(wire.SERVER_INFO_META_KEY)\n"
RECORD_CAPS = "    record['capabilities'] = identity.get('capabilities')\n"
RECORD_INSTRUCTIONS = "    record: dict[str, Any] = {'instructions': identity.get('instructions')}\n"
POP_IDENTITY = "            name = entry.pop(field)\n"
SET_REPORT_LOOP = "        report += set_report(set_id, expected, served)\n"
WORKFLOW_SCAN = "        elif path.startswith('.github/workflows/'):\n"
IMPORT_SCAN = "        elif isinstance(node, ast.Import) and any(COMMAND in alias.name.split('.') for alias in node.names):\n"
KNOWN = "('instructions', 'tools', 'resources', 'resourceTemplates', 'prompts', 'serverInfo', 'capabilities')"


def tolerated(anchor: str, condition: str) -> str:
    """The walk's branch at `anchor` (a key gained, lost, or compared) skipping keys where `condition` holds."""
    indent = ' ' * (len(anchor) - len(anchor.lstrip()) + (4 if anchor.rstrip().endswith(':') else 0))
    skip = f"{indent}if {condition}:\n{indent}    continue\n"
    return anchor + skip if anchor.rstrip().endswith(':') else skip + anchor


def every_key(why: str = 'misses') -> tuple[tuple[str, str], ...]:
    return test('test_every_key_the_fixture_holds_is_compared', why)


def former(kind: str) -> tuple[tuple[str, str], ...]:
    return tuple((f'test_surface.py::test_former_tolerated_kinds_are_differences[{check}-{kind}]', '_key_misses')
                 for check in ('surface', 'set'))


def skip_at_root(condition: str) -> str:
    return DICT_LOOP + f"            if {condition}:\n                continue\n"


def resolve_anywhere(key: str, body: str) -> str:
    """`expected_surface` widened: the carve-out applied at every path holding `key`, not its one path."""
    return ("    def widened(node: Any) -> None:\n"
            "        if isinstance(node, dict):\n"
            "            for k, v in list(node.items()):\n"
            f"                if k == {key!r}:\n{body}"
            "                widened(node[k])\n"
            "        elif isinstance(node, list):\n"
            "            for v in node:\n"
            "                widened(v)\n"
            "    widened(expected)\n" + RETURN_EXPECTED)


MUTANTS: tuple[Mutant, ...] = (
    # The comparison.
    Mutant('comparison-ignores-added', 'an added key is a difference', TS, ADDED, '                pass\n',
           drift('argument-added', 'tool-entry-key-added', 'resource-key-added', 'server-info-field-added',
                 'capabilities-field-added', 'top-level-key-added') + sets('argument-added', 'tool-added')),
    Mutant('comparison-ignores-removed', 'a removed key is a difference', TS, REMOVED, '                pass\n',
           drift('argument-removed', 'tool-entry-key-removed', 'tool-removed', 'server-info-field-removed')),
    Mutant('list-walk-first-two', 'every list index is compared, not the first two', TS, LIST_LOOP,
           "        for index in range(min(2, max(len(old), len(new)))):\n",
           drift('list-item-changed-at-the-last-index', 'list-item-changed-at-a-middle-index', 'list-last-item-removed',
                 'list-order-changed-past-the-start') + sets('list-item-changed-at-the-last-index')),
    Mutant('depth-capped-below-the-fixture', 'every depth is compared, below the fixture\'s deepest too', TS,
           "def _differences(old: Any, new: Any, path: FieldPath, found: list[Difference]) -> None:\n",
           "def _differences(old: Any, new: Any, path: FieldPath, found: list[Difference]) -> None:\n"
           "    if len(path) >= 10:\n        return\n",
           drift('change-below-the-fixtures-deepest-level') + sets('change-below-the-fixtures-deepest-level')),
    Mutant('key-set-from-the-expected-side', 'the keys compared are the union of both sides', TS, DICT_LOOP,
           "        for key in sorted(old):\n            if key not in new:\n                found.append(Difference(path + "
           "(key,), 'removed', old[key], None))\n                continue\n",
           drift('argument-added', 'resource-key-added') + sets('argument-added')),
    Mutant('recursion-capped-at-depth-3', 'every depth is compared', TS,
           "def _differences(old: Any, new: Any, path: FieldPath, found: list[Difference]) -> None:\n",
           "def _differences(old: Any, new: Any, path: FieldPath, found: list[Difference]) -> None:\n"
           "    if len(path) > 3:\n        return\n",
           drift('schema-key-at-depth-added', 'schema-key-at-depth-removed', 'schema-key-at-depth-changed')),
    Mutant('meta-key-skipped', 'no key name is skipped (`_meta`)', TS, DICT_LOOP, DICT_LOOP.replace(
        '\n', "\n            if key == '_meta':\n                continue\n", 1),
           drift('tool-entry-key-changed', 'tool-entry-key-removed')),
    Mutant('prompts-skipped', 'no listing is skipped (prompts)', TS, DICT_LOOP, skip_at_root("path == () and key == 'prompts'"),
           drift('prompt-added', 'prompt-removed', 'prompt-changed') + sets('prompt-added')),
    Mutant('templates-skipped', 'no listing is skipped (resource templates)', TS, DICT_LOOP,
           skip_at_root("path == () and key == 'resourceTemplates'"),
           drift('resource-template-added', 'resource-template-removed', 'resource-template-changed')),
    Mutant('unknown-top-level-skipped', 'a top-level key outside a known set is compared', TS, DICT_LOOP,
           skip_at_root(f"path == () and key not in {KNOWN}"), drift('top-level-key-added') + sets('top-level-key-added')),
    Mutant('loose-equality', 'leaves compare type-strict', TS, SAME, "    return old == new\n",
           drift('value-type-changed', 'value-type-float-to-int') + sets('value-type-changed')),
    Mutant('lists-as-sets', 'lists compare by position', TS, LIST_LOOP,
           "        if sorted(json.dumps(v, sort_keys=True) for v in old) != sorted(json.dumps(v, sort_keys=True) for v in new):\n"
           "            found.append(Difference(path, 'changed', old, new))\n"
           "        return\n" + LIST_LOOP, drift('list-order-changed') + sets('list-order-changed')),
    Mutant('lists-zipped', 'a longer or shorter list is a difference', TS, LIST_LOOP,
           "        for index in range(min(len(old), len(new))):\n",
           drift('list-item-added', 'list-item-removed') + sets('list-item-added', 'list-item-removed')),
    Mutant('leaf-changes-ignored', 'a changed leaf value is a difference', TS, LEAF,
           "    elif isinstance(old, (dict, list)) or isinstance(new, (dict, list)):\n",
           drift('argument-changed', 'description-changed', 'server-info-field-changed', 'instructions-changed')),
    Mutant('server-info-skipped', 'the server info is compared', TS, DICT_LOOP,
           skip_at_root("path == () and key == 'serverInfo'"),
           drift('server-info-field-added', 'server-info-field-removed', 'server-info-field-changed')),
    Mutant('server-info-skipped-but-version', 'every server-info field is compared, not only the version', TS, DICT_LOOP,
           skip_at_root("path == ('serverInfo',) and key != 'version'"),
           drift('server-info-field-added', 'server-info-field-removed', 'server-info-field-changed')),
    Mutant('capabilities-ignored', 'the capabilities are compared', TS, DICT_LOOP,
           skip_at_root("path == () and key == 'capabilities'"),
           drift('capabilities-field-added', 'capabilities-field-removed', 'capabilities-field-changed')
           + test('test_era_carve_out_accepts_only_the_capabilities[other-era]', 'violations')),
    # The carve-outs.
    Mutant('version-literal-accepted', 'a literal version in the fixture is a problem, never a pass', TS, VERSION_SHAPE,
           "        if isinstance(source, str):\n            pass\n        elif not isinstance(distribution, str):\n",
           test('test_version_carve_out_accepts_only_the_served_version[literal-in-fixture]', 'startswith(problem)')),
    Mutant('version-resolved-anywhere', 'the version carve-out resolves its one path only', TS, RETURN_EXPECTED,
           resolve_anywhere('version', "                    if isinstance(v, dict) and set(v) == {'distribution'}:\n"
                                       "                        node[k] = importlib.metadata.version(v['distribution'])\n"),
           test('test_version_carve_out_accepts_only_the_served_version[tool-version]', 'violations')
           + test('test_version_carve_out_accepts_only_the_served_version[nested-version]', 'violations')
           + test('test_version_carve_out_accepts_only_the_served_version[top-level-version]', 'violations')),
    Mutant('capabilities-resolved-anywhere', 'the era carve-out resolves its one path only', TS, RETURN_EXPECTED,
           resolve_anywhere('capabilities', "                    if isinstance(v, dict) and sorted(v) == sorted(ERAS):\n"
                                            "                        node[k] = v[era]\n"),
           test('test_era_carve_out_accepts_only_the_capabilities[nested-capabilities]', 'violations')
           + test('test_era_carve_out_accepts_only_the_capabilities[tool-capabilities]', 'violations')),
    Mutant('expected-ignores-era', 'each era is compared with its own capabilities', TS, EXPECTED_ERA,
           "            expected[ERA_CAPABILITIES[0]] = recorded['legacy']\n",
           test('test_served_surface_matches_baseline', 'capabilities')
           + test('test_era_carve_out_accepts_only_the_capabilities[accepted]', 'violations'),
           eras=('legacy', 'modern')),
    Mutant('era-check-excepts-server-info', 'the era check refuses every difference but the capabilities', TS,
           ERA_WITHOUT, "    return surface_violations(_without(legacy, ERA_CAPABILITIES[0], 'serverInfo'), "
                        "_without(modern, ERA_CAPABILITIES[0], 'serverInfo'))\n",
           test('test_era_check_refuses_every_other_difference[server-info]', 'violations')
           + test('test_era_check_refuses_every_other_difference[server-version]', 'violations')),
    # The per-set check.
    Mutant('set-skips-entries-the-fixture-lacks', 'a set serving an entry the fixture lacks differs', TS, SET_CUT,
           SET_CUT + "            served[listing] = {k: v for k, v in served[listing].items() if k in expected[listing]}\n",
           sets('tool-added', 'resource-added', 'resource-template-added', 'prompt-added')),
    Mutant('set-drops-server-info', 'the per-set check compares the server info', TS, SET_WITHOUT,
           "    expected, served = _without(expected, 'instructions', 'serverInfo'), _without(served, 'instructions', "
           "'serverInfo')\n", sets('server-info-field-added', 'server-info-field-removed', 'server-info-field-changed')),
    Mutant('set-drops-capabilities', 'the per-set check compares the capabilities', TS, SET_WITHOUT,
           "    expected, served = _without(expected, 'instructions', 'capabilities'), _without(served, 'instructions', "
           "'capabilities')\n", sets('capabilities-field-added', 'capabilities-field-removed', 'capabilities-field-changed')),
    Mutant('set-loop-sliced', 'every set in SETS is compared', TS, SETS_LOOP,
           "    sets = [(param.id, param.values[0]) for param in test_capabilities.SETS[1:]]\n",
           test('test_every_capability_set_serves_the_fixtures_entries', 'compared')),
    # The delta and the no-run scan.
    Mutant('delta-omits-added', 'the delta lists added paths', TS, DELTA,
           "    lines = sorted({f'- {render_path(d.path)}: {d.kind}' for d in surface_differences(old, new) "
           "if d.kind != 'added'})\n",
           test('test_delta_lists_every_changed_path', 'delta_lines'), drive='delta: expected exactly one line'),
    Mutant('scan-skips-workflows', 'the no-run scan reads workflow run: commands', TS, WORKFLOW_SCAN,
           "        elif path.startswith('.github/workflows/') and False:\n",
           test('test_command_scan_catches_planted_runs[workflow-inline]', 'runs')
           + test('test_command_scan_catches_planted_runs[workflow-block]', 'runs')),
    Mutant('scan-skips-imports', 'the no-run scan reads imports', TS, IMPORT_SCAN,
           IMPORT_SCAN.replace(' and any(', ' and False and any('),
           test('test_command_scan_catches_planted_runs[import]', 'runs')),
    # The recorder.
    Mutant('recorder-drops-meta', 'the recorder keeps every key (`_meta`)', HARNESS, ENTRY,
           "            entry = {k: v for k, v in served.items() if k != '_meta'}\n",
           test('test_served_surface_matches_baseline', "tool entry lost '_meta'")
           + test('test_recorder_sees_what_the_server_starts_serving[tool-meta]', 'is not recorded as served')),
    Mutant('recorder-fixed-keys', 'the recorder keeps every key, not a fixed list', HARNESS, ENTRY,
           "            entry = {k: v for k, v in served.items() if k in ('description', 'inputSchema', 'outputSchema', "
           "'annotations', 'title', 'name', 'uri', 'mimeType', 'uriTemplate', 'arguments', '_meta')}\n",
           test('test_recorder_sees_what_the_server_starts_serving[tool-icons]', 'is not recorded as served')
           + test('test_record_keeps_keys_no_model_declares[legacy]', 'plantedTool')),
    Mutant('recorder-lists-no-prompts', 'the recorder lists prompts', HARNESS, LISTINGS,
           LISTINGS.replace(' in SURFACE_LISTINGS}', " in SURFACE_LISTINGS if key != 'prompts'}"),
           test('test_recorder_sees_what_the_server_starts_serving[prompt]', 'is not recorded as served')
           + test('test_recorder_follows_every_page', 'planted_p'), eras=('legacy', 'modern')),
    Mutant('recorder-lists-no-templates', 'the recorder lists resource templates', HARNESS, LISTINGS,
           LISTINGS.replace(' in SURFACE_LISTINGS}', " in SURFACE_LISTINGS if key != 'resourceTemplates'}"),
           test('test_recorder_sees_what_the_server_starts_serving[resource-template]', 'is not recorded as served')
           + test('test_recorder_follows_every_page', 'cluster://planted/x'), eras=('legacy', 'modern')),
    Mutant('recorder-collapses-duplicates', 'a name served twice is refused', HARNESS, DUPLICATE,
           "            if False:\n", test('test_recorder_refuses_a_name_served_twice', 'DID NOT RAISE')),
    Mutant('recorder-first-page-only', 'every page of a listing is read', HARNESS, PAGE_END,
           "        if True:\n            return entries\n", test('test_recorder_follows_every_page', 'planted_b'),
           eras=('legacy', 'modern')),
    Mutant('recorder-parsed-server-info', 'the server info is read raw, not from a parsed model', HARNESS, LEGACY_INFO,
           "        record['serverInfo'] = {k: v for k, v in (identity.get('serverInfo') or {}).items() "
           "if k in ('name', 'version', 'title', 'description', 'icons', 'websiteUrl')}\n",
           test('test_record_keeps_keys_no_model_declares[legacy]', 'plantedInfo')),
    Mutant('recorder-records-parsed-models', 'the listings are read raw, not as parsed models', HARNESS,
           "        result = await client.session.send_request(request(params=params), _RAW)\n",
           "        result = (await client.session.send_request(request(params=params), wire.ListToolsResult if key == "
           "'tools' else _RAW))\n        result = result if isinstance(result, dict) else result.model_dump(by_alias=True, "
           "mode='json', exclude_none=True)\n",
           test('test_served_surface_matches_baseline', 'differ'),
           equivalent='the server and the recorder share the SDK models in one process, so no server can be planted to '
                      'send a tool key the model drops; the pure step shows the raw route keeps one '
                      '(test_record_keeps_keys_no_model_declares)'),
    # The recorder's era, and the steps from raw results to the record.
    Mutant('recorder-ignores-era-argument', 'the recorder records the era it is asked for', HARNESS, SURFACE_ERA,
           SURFACE_ERA.replace('_era(era)', '_era(None)'),
           test('test_recorder_serves_each_eras_own_surface[modern]', 'capabilities')),
    Mutant('served-surface-drops-era', 'served_surface passes its era on', HARNESS, SERVED_ERA,
           "    return drive(_surface(server, None))\n",
           test('test_recorder_serves_each_eras_own_surface[modern]', 'capabilities')),
    Mutant('identity-always-handshake', 'the identity is read per era', HARNESS, IDENTITY_BRANCH,
           IDENTITY_BRANCH.replace("if era == 'legacy':", "if True:"),
           test('test_recorder_serves_each_eras_own_surface[modern]', 'capabilities')),
    Mutant('modern-server-info-from-the-wrong-place', 'the 2026-07-28 server info is the discover stamp', HARNESS,
           MODERN_INFO, "        record['serverInfo'] = identity.get('serverInfo')\n",
           test('test_recorder_serves_each_eras_own_surface[modern]', 'violations')
           + test('test_record_keeps_keys_no_model_declares[modern]', 'serverInfo')),
    Mutant('capabilities-not-recorded', 'the capabilities are recorded', HARNESS, RECORD_CAPS,
           "    record['capabilities'] = {}\n", test('test_served_surface_matches_baseline', 'capabilities')),
    Mutant('instructions-not-recorded', 'the instructions are recorded', HARNESS, RECORD_INSTRUCTIONS,
           "    record: dict[str, Any] = {'instructions': None}\n",
           test('test_served_surface_matches_baseline', 'instructions differ')),
    Mutant('identity-kept-in-the-entry', 'an entry\'s identity becomes its key, not a field', HARNESS, POP_IDENTITY,
           "            name = entry[field]\n", test('test_served_surface_matches_baseline', 'gained')),
    Mutant('set-report-discards-one-set', 'every set\'s report is asserted', TS, SET_REPORT_LOOP,
           "        report += [] if set_id == 'core-only' else set_report(set_id, expected, served)\n",
           test('test_every_capability_set_serves_the_fixtures_entries', 'report'),
           equivalent='it mutates the test\'s own assertion, not a decision of the code under test; the plausible '
                      'fault, a set missing from the loop, is killed (set-loop-sliced)'),
    # The command's decisions, made in tests/test_surface.py and covered there.
    Mutant('command-era-check-against-itself', 'the command refuses eras that differ', TS, ERA_CHECK,
           "    differing = era_violations(records['legacy'], records['legacy'])\n",
           test('test_command_result_refuses_eras_that_differ[tool]', 'startswith'),
           drive='eras: the refusal'),
    Mutant('command-skips-era-check', 'the command refuses eras that differ', TS, ERA_CHECK, "    differing = []\n",
           test('test_command_result_refuses_eras_that_differ[tool]', 'startswith')),
    Mutant('command-skips-self-check', 'the command checks the fixture it writes', TS, SELF_CHECK,
           "    problems = []\n", test('test_command_result_checks_the_fixture_it_writes', 'DID NOT RAISE')),
    Mutant('command-delta-against-itself', 'the command lists the delta against its base', TS, COMMAND_DELTA,
           "    delta = delta_lines(fixture, fixture)\n",
           test('test_command_result_lists_the_delta_against_its_base', 'result.delta')
           + test('test_command_result_reproduces_the_committed_fixture', 'added'),
           drive='delta: expected exactly one line'),
    Mutant('command-no-pytest-guard', 'the command refuses under pytest', TS, PYTEST_GUARD, "    if False:\n",
           test('test_command_refuses_outside_the_sandbox_and_under_pytest[under-pytest]', 'refusal'),
           drive="pytest: the command ran"),
    # The command's choices, in tests/test_surface.py: each driven by the suite through stand-ins, and
    # by the drive through the real command (review cycle 2, N1).
    Mutant('command-skips-its-refusal', 'the command acts on its refusal', TS, MAIN_REFUSAL,
           "        if False:\n            raise refusal\n",
           test('test_command_refuses_writing_nothing[no-sandbox]', 'command_main'), drive='sandbox: the command ran'),
    Mutant('command-ignores-against', 'the delta is listed against --against when given', TS, BASE_AGAINST,
           "    if False:\n        source = against\n",
           test('test_command_lists_the_delta_against_the_against_file', 'stand.stdout'),
           drive='against: the delta is not listed against --against'),
    Mutant('command-ignores-head', 'without --against the base is the fixture at HEAD', TS, BASE_HEAD,
           "        text = None\n", test('test_command_lists_the_delta_against_head_without_against', 'stand.stdout'),
           drive='head: without --against'),
    Mutant('command-head-always-present', 'a HEAD with no fixture is an empty base', TS, HEAD_EMPTY,
           "    if False:\n        return None\n",
           test('test_command_lists_every_key_added_when_head_has_no_fixture', 'command_main')),
    Mutant('command-fences-after-recording', 'the fence comes before anything is recorded', TS, MAIN_FENCE,
           "        result = command_result(base, effects.record)\n        effects.fence()\n",
           test('test_command_lists_the_delta_against_head_without_against', 'stand.calls'), drive='run exited'),
    Mutant('command-prints-no-delta', 'the command prints the delta list', TS, MAIN_OUT, "    effects.out('')\n",
           test('test_command_lists_the_delta_against_the_against_file', 'stand.stdout'),
           drive='delta: expected exactly one line'),
    Mutant('command-names-head-always', 'the summary names the base the delta is listed against', TS, MAIN_SOURCE,
           "{result.summary} against HEAD')\n",
           test('test_command_lists_the_delta_against_the_against_file', 'stand.stderr')),
    # The command file: what is left is its effects, each one action with no branch; a branch put back
    # is caught by the suite's scan of its source, and each effect broken by the drive.
    Mutant('command-file-chooses', 'the command file makes no choice of its own', COMMAND, CMD_CALL,
           "    return surface.command_main(argv if argv else None, os.environ, effects)\n",
           test('test_the_surface_command_makes_no_choice', 'command_choices')),
    Mutant('command-skips-the-fence', 'the command fences process launches before recording', COMMAND, CMD_FENCE,
           "fence=lambda: None,", drive='run exited'),
    Mutant('command-records-one-era', 'the command records each era', COMMAND, CMD_RECORD,
           "record=lambda era: surface.command_record('legacy'),", drive='a fresh run differs from the staged'),
    Mutant('command-git-outside-its-checkout', 'the command reads HEAD of its own checkout', COMMAND, CMD_GIT,
           "['git', *args]", drive='run exited'),
    Mutant('command-prints-nothing', 'the command prints what it is handed', COMMAND, CMD_OUT,
           "out=lambda line: None,", drive='delta: expected exactly one line'),
    Mutant('command-unsorted', 'the command writes one canonical byte form', TS, BYTES,
           "    return (json.dumps(fixture, indent=1) + '\\n').encode()\n",
           drive='a fresh run differs from the staged'),
    Mutant('command-writes-default-too', 'the command writes only --out', COMMAND, CMD_WRITE,
           CMD_WRITE + "    (ROOT / 'tests' / 'fixtures' / 'served_surface.json').write_bytes(data)\n",
           drive='at its default path'),
    # A kind the comparison once tolerated, put back: each re-introduces one of the five by name, or
    # exempts a key the hand-picked rows never planted (review cycle 2, N2).
    Mutant('tolerate-argument-description-gained', 'an argument description gained is a difference', TS, KEY_ADDED,
           tolerated(KEY_ADDED, f"key == 'description' and {ARGUMENT}"),
           every_key() + former('argument-description')),
    Mutant('tolerate-argument-description-drift', 'an argument description changed is a difference', TS, KEY_RECURSE,
           tolerated(KEY_RECURSE, f"key == 'description' and {ARGUMENT}"),
           every_key() + former('argument-description')),
    Mutant('tolerate-additional-properties-gained', 'additionalProperties gained is a difference', TS, KEY_ADDED,
           tolerated(KEY_ADDED, "key == 'additionalProperties'"), every_key() + former('additional-properties')),
    Mutant('tolerate-derived-title-gained', 'a tool title gained is a difference', TS, KEY_ADDED,
           tolerated(KEY_ADDED, TOOL_TITLE), every_key() + former('derived-title')),
    Mutant('tolerate-derived-title-lost', 'a tool title lost is a difference', TS, KEY_REMOVED,
           tolerated(KEY_REMOVED, TOOL_TITLE), every_key() + former('derived-title')),
    Mutant('tolerate-output-model-description-gained', 'an output model description gained is a difference', TS,
           KEY_ADDED, tolerated(KEY_ADDED, "key == 'description' and 'outputSchema' in path"),
           former('output-model-description')),
    Mutant('tolerate-output-definitions', 'output `$defs` and `$ref` are compared', TS, DICT_LOOP,
           tolerated(DICT_LOOP, "str(key).startswith('$')"),
           former('output-defs') + former('output-ref')
           + test('test_inlined_output_definitions_are_a_difference', 'found')),
    Mutant('exempt-default', 'an argument default is compared', TS, DICT_LOOP, tolerated(DICT_LOOP, "key == 'default'"),
           every_key()),
    Mutant('exempt-enum', 'an enum is compared', TS, DICT_LOOP, tolerated(DICT_LOOP, "key == 'enum'"), every_key()),
    Mutant('exempt-anyOf', 'an anyOf is compared', TS, DICT_LOOP, tolerated(DICT_LOOP, "key == 'anyOf'"), every_key()),
    Mutant('exempt-icon-src-gained', 'a server icon\'s src gained is a difference', TS, KEY_ADDED,
           tolerated(KEY_ADDED, "key == 'src'"), every_key()),
    Mutant('exempt-version-source-gained', 'the version source is compared in the delta between fixtures', TS,
           KEY_ADDED, tolerated(KEY_ADDED, "key == 'distribution'"), every_key()),
    Mutant('exempt-subscribe-lost', 'a capability flag lost is a difference', TS, KEY_REMOVED,
           tolerated(KEY_REMOVED, "key == 'subscribe'"), every_key()),
    Mutant('set-exempts-a-key', 'the per-set check reports every key', TS, SET_RETURN,
           "    return [line for line in surface_violations(expected, served) if 'mimeType' not in line]\n",
           test('test_set_check_compares_every_key_the_fixture_holds', 'misses')),
    Mutant('version-source-first-candidate', 'the version source is the one candidate installed at the served version',
           TS, SOURCE_LOOP, "    found = [VERSION_SOURCES[0]]\n" + SOURCE_LOOP,
           test('test_command_result_reproduces_the_committed_fixture', 'CommandRefusal'), drive='run exited'),
    Mutant('baseline-writes-fixture', 'the suite never writes the fixture', TS, BASELINE,
           "    FIXTURE.write_text(json.dumps(served))\n" + BASELINE,
           test('test_served_surface_matches_baseline', ''), fixture_write=True),
)


def copy_tree(dest: Path, staged: bytes) -> Path:
    """The copy a mutant is planted in: a repository of its own whose `HEAD` holds the staged fixture
    (the command reads its base from `HEAD` of the checkout it lives in)."""
    repo = dest / 'repo'
    for name in COPIED_DIRS:
        shutil.copytree(ROOT / name, repo / name, ignore=shutil.ignore_patterns('__pycache__'))
    for name in COPIED_FILES:
        shutil.copy2(ROOT / name, repo / name)
    (repo / FIXTURE).write_bytes(staged)
    git = ['git', '-C', str(repo), '-c', 'user.name=sweep', '-c', 'user.email=sweep@invalid', '-c', 'commit.gpgsign=false']
    for argv in (['init', '-q'], ['add', FIXTURE], ['commit', '-q', '-m', 'the staged fixture']):
        done = subprocess.run([*git, *argv], capture_output=True, text=True, env=ENVIRON)
        if done.returncode != 0:
            raise SystemExit(f'sweep: cannot make the copy a repository: {done.stderr.strip()}')
    return repo


def plant(repo: Path, mutant: Mutant) -> None:
    path = repo / mutant.file
    text = path.read_text()
    count = text.count(mutant.old)
    if count != 1:
        raise SystemExit(f'sweep: {mutant.id}: the anchor occurs {count} times in {mutant.file}: {mutant.old[:80]!r}')
    path.write_text(text.replace(mutant.old, mutant.new))


def bounded(argv: list[str], env: dict[str, str], timeout: int, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    """Run `argv` in its own process group, killing the whole group on expiry."""
    process = subprocess.Popen(argv, env=env, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               start_new_session=True)
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        out, err = process.communicate()
        err += f'\nsweep: killed after {timeout} s'
    return subprocess.CompletedProcess(argv, process.returncode, out, err)


def pytest_verdict(repo: Path, mutant: Mutant, era: str, scratch: Path) -> list[str]:
    junit = scratch / f'junit-{era}.xml'
    targets = [target for target, _ in mutant.targets]
    child = bounded([str(SANDBOX), 'sh', '-c', 'cd "$1" || exit 96; shift; "$@"', MARK, str(repo), sys.executable,
                     '-m', 'pytest', '-q', '-rA', '-p', 'no:cacheprovider', f'--junitxml={junit}',
                     *[f'tests/{t}' for t in targets]], {**ENVIRON, 'CLUSTER_MCP_TEST_ERA': era}, 300)
    report = junit.read_text() if junit.exists() else None
    problems = []
    for target, why in mutant.targets:
        problems += mutants.mutation_violations(child.returncode, report, [target], why)
    return sorted(set(problems))


def drive_verdict(repo: Path, mutant: Mutant) -> list[str]:
    child = bounded(['sh', '-c', '"$@"', MARK, sys.executable, '-I', str(SPEC / 'verify' / 'command_drive.py'), 'all'],
                    {**ENVIRON, 'SURFACE_CODE_ROOT': str(repo)}, 900)
    if child.returncode == 0:
        return ['the drive passed']
    if mutant.drive and mutant.drive not in child.stderr:
        return [f'the drive failed without {mutant.drive!r}: {child.stderr.strip()[-300:]!r}']
    return []


def run(mutant: Mutant, staged: bytes) -> tuple[str, str]:
    """(verdict, detail): `killed`, `survived` or `equivalent`. Each kind of target the mutant has (its
    pytest targets, its drive) must kill it, in at least one of its eras for the pytest targets."""
    with tempfile.TemporaryDirectory(prefix=f'surface-sweep-{mutant.id}-') as name:
        scratch = Path(name)
        repo = copy_tree(scratch, staged)
        plant(repo, mutant)
        found: dict[str, list[str]] = {}
        killed: set[str] = set()
        if mutant.targets:
            for era in mutant.eras:
                problems = pytest_verdict(repo, mutant, era, scratch)
                if (repo / FIXTURE).read_bytes() != staged:
                    killed.add('pytest')
                    found.setdefault('pytest', []).append(f'{era}: the fixture was written')
                    (repo / FIXTURE).write_bytes(staged)
                elif not problems and not mutant.fixture_write:
                    killed.add('pytest')
                    found.setdefault('pytest', []).append(f'{era}: each target failed for its reason')
                else:
                    found.setdefault('pytest', []).append(
                        f'{era}: ' + ('; '.join(problems) if not mutant.fixture_write else 'the fixture was not written'))
        if mutant.drives:
            problems = drive_verdict(repo, mutant)
            if (repo / FIXTURE).read_bytes() != staged:
                killed.add('drive')
                found.setdefault('drive', []).append('drive: the fixture was written')
            elif mutant.drive is not None and not problems:
                killed.add('drive')
                found.setdefault('drive', []).append(f'drive: failed with {mutant.drive!r}')
            else:
                found.setdefault('drive', []).append('drive: ' + ('; '.join(problems) or 'the fixture was not written'))
    kinds = set(found)
    detail = '; '.join(line for kind in sorted(found) for line in found[kind])
    if kinds and kinds <= killed:
        return 'killed', detail
    if mutant.equivalent is not None:
        return 'equivalent', f'{mutant.equivalent} (observed: {detail})'
    return 'survived', detail or 'no target'


def main(argv: list[str]) -> int:
    chosen = [m for m in MUTANTS if not argv or m.id in argv]
    unknown = sorted(set(argv) - {m.id for m in MUTANTS})
    if unknown or not chosen:
        print(f'sweep: no such mutant: {unknown}', file=sys.stderr)
        return 2
    shown = subprocess.run(['git', 'show', f':{FIXTURE}'], capture_output=True, env=ENVIRON)
    if shown.returncode != 0:
        print(f'sweep: cannot read the staged {FIXTURE}', file=sys.stderr)
        return 2
    lines = ['# Comparison, recorder and command sweep (PLAN section 6)', '']
    failed = []
    for mutant in chosen:
        start = time.monotonic()
        verdict, detail = run(mutant, shown.stdout)
        print(f'sweep: {verdict:10} {mutant.id} ({time.monotonic() - start:.0f} s): {detail}', file=sys.stderr)
        lines.append(f'{verdict:10} {mutant.id}: {mutant.decision}')
        lines.append(f'           {detail}')
        if verdict == 'survived':
            failed.append(mutant.id)
    counts = {v: sum(line.startswith(v) for line in lines) for v in ('killed', 'survived', 'equivalent')}
    lines += ['', f'{len(chosen)} mutants: {counts["killed"]} killed, {counts["survived"]} survived, '
                  f'{counts["equivalent"]} equivalent']
    if not argv:
        REPORT.write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    if failed:
        print(f'sweep: FAIL: survived: {", ".join(failed)}', file=sys.stderr)
        return 1
    print('sweep: ok: every mutant killed or recorded as equivalent', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
