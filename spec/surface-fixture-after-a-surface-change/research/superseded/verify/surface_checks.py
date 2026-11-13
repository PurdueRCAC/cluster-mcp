"""Gate helpers for surface-fixture-after-a-surface-change. Run from the worktree root with `python -I`.

Modes:
  ids full|sets|all  every required drift-control row ran and passed, in each era (JUnit outcome): `test_surface_check_catches_drift`
                     (full) and `test_set_check_catches_drift` (sets) each carry, by parameter id, a row
                     for every kind GOAL R3 names, additions as well as removals and changes (R7)
  surface-cases      print the ids of every mutation case that plants into the served-surface fixture
                     or targets a test in tests/test_surface.py, for `tests/mutants.py --self-check`
  era-proof          the baseline test, run once per era with the harness's era log, connected in that
                     era (a test that returned before connecting would log nothing)

Footprint: one child process at a time (pytest), under 1 GB.

A row's id is not proof of its content: the sweep (PLAN § 6) attacks what each kind's rows plant.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path.cwd()
TESTS = ROOT / 'tests'
SURFACE = 'tests/fixtures/served_surface.json'
BASELINE = 'tests/test_surface.py::test_served_surface_matches_baseline'

# Each kind GOAL R3 names, with the changes a control must plant for it (R7).
FULL = {
    'tool': ('added', 'removed', 'renamed'),
    'argument': ('added', 'removed', 'changed'),
    'schema-key-at-depth': ('added', 'removed', 'changed'),
    'annotation-hint': ('added', 'removed', 'changed'),
    'tool-entry-key': ('added', 'removed', 'changed'),
    'resource': ('added', 'removed', 'renamed'),
    'resource-key': ('added', 'removed', 'changed'),
    'resource-template': ('added', 'removed', 'changed'),
    'prompt': ('added', 'removed', 'changed'),
    'server-info-field': ('added', 'removed', 'changed'),
    'capabilities-field': ('added', 'removed', 'changed'),
    'top-level-key': ('added', 'removed'),
    'description': ('changed',),
    'instructions': ('changed',),
    'value-type': ('changed',),
    'list-order': ('changed',),
    'list-item': ('added', 'removed'),
}
FULL_IDS = {f'{kind}-{change}' for kind, changes in FULL.items() for change in changes}

# A set may lack a whole entry, and its instructions are its own (pinned elsewhere), so the per-set
# check carries every other row: every addition, every key lost inside an entry, every change.
SET_EXEMPT = {'tool-removed', 'resource-removed', 'resource-template-removed', 'prompt-removed',
              'instructions-changed'}
SET_IDS = (FULL_IDS - SET_EXEMPT) | {'subset-passes'}

TESTS_BY_SCOPE = {
    'full': ('tests/test_surface.py::test_surface_check_catches_drift', FULL_IDS),
    'sets': ('tests/test_surface.py::test_set_check_catches_drift', SET_IDS),
}


def fail(message: str) -> int:
    print(f'surface_checks: FAIL: {message}', file=sys.stderr)
    return 1


def passed(node: str, era: str) -> set[str]:
    """The parameter ids of test function `node` that ran and passed in `era`: skipped, xfailed,
    failed and errored rows do not count, so a row with the right id cannot be hollow by marking."""
    with tempfile.TemporaryDirectory(prefix='surface-ids-') as scratch:
        report = Path(scratch) / 'report.xml'
        run = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:cacheprovider', f'--junitxml={report}', node],
                             capture_output=True, text=True, env={**ENVIRON, 'CLUSTER_MCP_TEST_ERA': era})
        if not report.exists():
            raise SystemExit(fail(f'{node} wrote no report in the {era} era:\n{run.stdout}{run.stderr}'))
        tree = ET.parse(report)
    function = node.rsplit('::', 1)[1]
    ids = set()
    for case in tree.iter('testcase'):
        name = case.get('name', '')
        # A passing testcase carries no `failure`, `error` or `skipped` child (an xfail is a `skipped`).
        if name.startswith(function + '[') and all(child.tag in ('system-out', 'system-err') for child in case):
            ids.add(name[len(function) + 1:-1])
    return ids


def ids(scope: str) -> int:
    scopes = ('full', 'sets') if scope == 'all' else (scope,)
    problems = []
    for name in scopes:
        node, want = TESTS_BY_SCOPE[name]
        for era in ('legacy', 'modern'):
            missing = sorted(want - passed(node, era))
            if missing:
                problems.append(f'{node} has no passing row, in the {era} era, for {missing}')
    if problems:
        return fail('\n'.join(problems))
    print(f'surface_checks: ok: every required control row ran and passed in both eras ({", ".join(scopes)})', file=sys.stderr)
    return 0


def surface_cases() -> int:
    sys.path.insert(0, str(TESTS))
    import mutants  # noqa: E402 - the runner lives in tests/
    chosen = [case.id for case in mutants.CASES
              if any(t.startswith('test_surface.py::') for t in case.targets)
              or any(name == SURFACE for name, _, _ in case.repo_edits)]
    if not chosen:
        return fail('no mutation case plants into the fixture or targets tests/test_surface.py')
    print(' '.join(chosen))
    return 0


def era_proof() -> int:
    with tempfile.TemporaryDirectory(prefix='surface-era-') as scratch:
        log = Path(scratch) / 'era.log'
        for era in ('legacy', 'modern'):
            env = {**ENVIRON, 'CLUSTER_MCP_ERA_LOG': str(log), 'CLUSTER_MCP_TEST_ERA': era}
            run = subprocess.run(['uv', 'run', 'pytest', '-q', BASELINE], env=env)
            if run.returncode != 0:
                return fail(f'{BASELINE} failed in the {era} era')
        lines = log.read_text().splitlines() if log.exists() else []
    want = {'legacy': lambda line: line.startswith('era=legacy version=') and 'version=2026-07-28' not in line,
            'modern': lambda line: line.startswith('era=modern version=2026-07-28 ')}
    missing = [era for era, seen in want.items() if not any(seen(line) for line in lines)]
    if missing:
        return fail(f'no connect logged in the {", ".join(missing)} era: {lines}')
    print('surface_checks: ok: the baseline test connected in each era', file=sys.stderr)
    return 0


ENVIRON = dict(os.environ)


def main(argv: list[str]) -> int:
    if argv[:1] == ['ids'] and len(argv) == 2 and argv[1] in ('full', 'sets', 'all'):
        return ids(argv[1])
    if argv == ['surface-cases']:
        return surface_cases()
    if argv == ['era-proof']:
        return era_proof()
    return fail('usage: surface_checks.py ids full|sets|all | surface-cases | era-proof')


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
