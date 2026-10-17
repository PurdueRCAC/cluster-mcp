"""Gate-level checks on the planted-violation table and negative controls on the gate's own checkers.

Usage, from the repository root:

    uv run python spec/stack-upgrade/verify/controls.py <n> <baseline-cases.txt>

- Every mutation case present at 3d010ec (`baseline-cases.txt`, one id per line, read by the gate
  from an archive of that commit) is still in `tests/mutants.py`.
- Every case phases 1..n add exists, and every target it names is a test id some phase gate
  requires, so a case cannot be "killed" by a test nobody runs.
- The gate's own checkers reject a planted shape and accept a clean one: `ids_check.problems`,
  `edits.hygiene_violations`, `edits.additions_only_violations` and `era_log.era_log_violations`
  from phase 1; the suite's
  `surface_violations` from phase 3; `audit_violations` in `bin/audit_lock.py` from phase 6. A
  checker that returns "fine" for everything fails here even when every test id shows PASSED.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, 'tests')

import edits  # noqa: E402
import era_log  # noqa: E402
import ids_check  # noqa: E402

PHASE_CASES: dict[int, set[str]] = {
    1: {'tool-error-boundary-dropped', 'boundary-leaks-traceback', 'boundary-catches-base-exception',
        'boundary-reraises-mcp-error', 'ssh-exit-status-dropped', 'delegate-state-session-scoped'},
    2: {'instructions-dropped'},
    3: {'tool-description-summary-only'},
    4: {'sse-transport-unserved'},
    5: {'oidc-check-dropped', 'oidc-secret-not-required', 'oidc-message-incomplete', 'oidc-cimd-enabled',
        'none-mode-installs-provider', 'auth-modes-annotation-slice'},
    6: set(),
    7: set(),
}


def fail(message: str) -> None:
    print(f'controls: {message}', file=sys.stderr)
    raise SystemExit(1)


def junit(*cases: tuple[str, str, str]) -> str:
    body = ''.join(f'<testcase classname="tests.{m}" name="{n}">' + (f'<{t}/>' if t else '') + '</testcase>'
                   for m, n, t in cases)
    return f'<testsuites><testsuite>{body}</testsuite></testsuites>'


def check_cases(n: int, baseline_cases: list[str]) -> None:
    import mutants
    current = {c.id: c for c in mutants.CASES}
    missing = sorted(set(baseline_cases) - set(current))
    if missing:
        fail(f'mutation cases present at 3d010ec are gone: {missing}')
    required = {line for i in range(1, n + 1)
                for line in (HERE / 'ids' / f'P{i}.txt').read_text().splitlines()
                if line and not line.startswith('#')}
    for i in range(1, n + 1):
        for case_id in sorted(PHASE_CASES[i]):
            case = current.get(case_id)
            if case is None:
                fail(f'P{i} owns case {case_id!r}, which tests/mutants.py lacks')
            for target in case.targets:
                if target not in required:
                    fail(f'{case_id}: target {target} is not an id any phase gate up to P{n} requires')


def check_gate_checkers() -> None:
    good = junit(('test_a', 'test_x', ''), ('test_a', 'test_y', ''))
    if ids_check.problems(good, ['tests/test_a.py::test_x'])[1]:
        fail('ids_check rejects a clean report')
    for planted, why in ((junit(('test_a', 'test_y', '')), 'a missing id'),
                         (junit(('test_a', 'test_x', 'skipped')), 'a skipped id'),
                         (junit(('test_a', 'test_x', ''), ('test_a', 'test_z', 'failure')), 'a failure elsewhere'),
                         (junit(('test_a', 'test_x', ''), ('test_a', 'test_x', '')), 'a duplicate id')):
        if not ids_check.problems(planted, ['tests/test_a.py::test_x'])[1]:
            fail(f'ids_check accepts {why}')
    base = 'import os\nSTACK = (1,)\n\n@mark.unit\ndef test_a():\n    assert 1\n'
    if edits.hygiene_violations(base, base.replace('(1,)', '(1, 2)')):
        fail('edits rejects a STACK change in test_hygiene.py')
    for head, why in ((base.replace('assert 1', 'assert 2'), 'an edited test body'),
                      (base.replace('@mark.unit\n', '@mark.integration\n'), 'an edited decorator'),
                      (base.replace('import os\n', ''), 'a removed import')):
        if not edits.hygiene_violations(base, head):
            fail(f'edits accepts {why} in test_hygiene.py')
    if not edits.additions_only_violations('--- a/t.py\n+++ b/t.py\n@@\n-x = 1\n+x = 2\n', 't.py'):
        fail('edits accepts a changed line')
    if edits.additions_only_violations('--- a/t.py\n+++ b/t.py\n@@\n x = 1\n+y = 2\n', 't.py'):
        fail('edits rejects a pure addition')


def check_era_log_checker() -> None:
    modern = ['era=modern version=2026-07-28 first=server/discover'] * 3
    legacy = ['era=legacy version=2025-11-25 first=initialize'] * 3
    if era_log.era_log_violations(modern, 'modern', 3) or era_log.era_log_violations(legacy, 'legacy', 3):
        fail('era_log rejects a clean pass')
    for lines, era, why in ((modern[:2], 'modern', 'too few connects'),
                            (legacy, 'modern', 'a legacy pass offered as modern'),
                            (['era=modern version=2026-07-28 first=tools/list'] * 3, 'modern', 'a version pin'),
                            (['era=modern version=2025-11-25 first=server/discover'] * 3, 'modern', 'a fallback'),
                            (['era=legacy version=2026-07-28 first=initialize'] * 3, 'legacy', 'a modern version'),
                            ([], 'legacy', 'an empty log')):
        if not era_log.era_log_violations(lines, era, 3):
            fail(f'era_log accepts {why}')


def check_surface_checker() -> None:
    import json
    import test_surface
    snapshot = json.loads(Path('tests/fixtures/served_surface.json').read_text())
    if test_surface.surface_violations(snapshot, snapshot):
        fail('surface_violations rejects the baseline against itself')
    planted = json.loads(json.dumps(snapshot))
    name = sorted(planted['tools'])[0]
    planted['tools'][f'{name}_renamed'] = planted['tools'].pop(name)
    if not test_surface.surface_violations(snapshot, planted):
        fail('surface_violations accepts a renamed tool')
    planted = json.loads(json.dumps(snapshot))
    schema = planted['tools']['run_command']['inputSchema']
    schema['properties']['command']['type'] = 'integer'
    if not test_surface.surface_violations(snapshot, planted):
        fail('surface_violations accepts a changed argument type')
    planted = json.loads(json.dumps(snapshot))
    planted['tools']['run_command']['inputSchema']['additionalProperties'] = True
    if not test_surface.surface_violations(snapshot, planted):
        fail('surface_violations accepts additionalProperties: true')


def check_audit_checker() -> None:
    spec = importlib.util.spec_from_file_location('audit_lock', 'bin/audit_lock.py')
    if spec is None or spec.loader is None:
        fail('bin/audit_lock.py is missing')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    lock = Path('uv.lock').read_text()
    pinned = audit.registry_packages(lock)
    clean = f'Found no known vulnerabilities and no adverse project statuses in {pinned} packages\n'
    if audit.audit_violations(0, clean, lock) != (0, []):
        fail('audit_violations rejects a clean audit of the shipped lock')
    for returncode, output, why in (
            (1, 'demo 1.0 has 1 known vulnerability:\n', 'a finding'),
            (0, 'demo 1.0 has 1 known vulnerability:\n' + clean, 'a finding under exit 0'),
            (2, 'error: Auditing requires network access and cannot be performed in offline mode\n', 'offline'),
            (2, "error: unrecognized subcommand 'audit'\n", 'an audit that cannot run'),
            (0, clean.replace(str(pinned), str(pinned - 1)), 'a short audit'),
            (0, '', 'a missing summary')):
        if audit.audit_violations(returncode, output, lock)[0] == 0:
            fail(f'audit_violations accepts {why}')
    command = audit.COMMAND
    if '--project' not in command or command[command.index('--project') + 1] != str(Path.cwd().resolve()):
        fail('the audit does not name this checkout with --project')
    for flag in ('--frozen', '--no-config'):
        if flag not in command:
            fail(f'the audit runs without {flag}')
    env = audit.child_env({'UV_PROJECT': '/elsewhere', 'UV_NO_DEV': '1', 'UV_OFFLINE': '1', 'PATH': '/bin'})
    if 'UV_PROJECT' in env or 'UV_NO_DEV' in env or env.get('UV_OFFLINE') != '1' or env.get('PATH') != '/bin':
        fail(f'the audit environment keeps a selector or drops what it needs: {env}')


def main() -> int:
    n = int(sys.argv[1])
    baseline_cases = [c for c in Path(sys.argv[2]).read_text().split() if c]
    if len(baseline_cases) != 53:
        fail(f'expected the 53 mutation cases present at 3d010ec, read {len(baseline_cases)}')
    check_cases(n, baseline_cases)
    check_gate_checkers()
    check_era_log_checker()
    if n >= 3:
        check_surface_checker()
    if n >= 6:
        check_audit_checker()
    print(f'controls: phases 1..{n} passed', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
