"""Review cycle 3, N2: the cap on an SFTP session's subsystem and version steps is pinned by the default suite.

Run from anywhere in the worktree:

    UV_PYTHON=3.14 uv run python -I spec/ssh-half-open-link/remediation/F8-session-steps-cap.py both   # or legacy, modern

The finding: an SFTP session opened after a reconnect makes its three steps (the channel, the `sftp`
subsystem, the version exchange) on the worker its call waits for no later than its deadline, but
only the opt-in rows `test_a_late_reconnect_onto_a_link_that_goes_silent_again_ends_in_time
[write_file-subsystem|write_file-version]` (behind `CLUSTER_MCP_TEST_EVERY_KIND=1`, which CI never
sets) saw the two later steps: a cap on the channel alone passed the default suite. The pin is a
unit row in the default suite, `test_an_sftp_session_after_a_reconnect_opens_every_step_on_its_worker
[channel|subsystem|version]`, about a second per era. Checked four ways, in each era asked for:

1. **The pin passes here**: its three rows, each reported passed.
2. **The gap it closes**: the cap on the channel alone (`shol-session-channel-only-on-the-worker`'s
   edit), run against the default suite's rows of the `_sftp` family (the late and live reconnect
   rows for `write_file`, the SFTP open cut at each step, the open outlasting its own timeout, the
   reconnect after a silent link, the worker's units and the doc pin), with the opt-in unset:
   every one passes, so without the pin the plant survives the default suite.
3. **It is the review's plant**: with `CLUSTER_MCP_TEST_EVERY_KIND=1`, the same edit fails both
   opt-in step rows past their bound.
4. **The cases bite**: `shol-session-channel-only-on-the-worker` and `shol-session-version-on-the-call`
   are each reported killed by the pin's rows (`tests/mutants.py`, the opt-in unset).

Exit 0 when all four hold. Footprint: one pytest child at a time (the family's rows start a loopback
SSH server, a silent hop and a sandboxed login bash), under 600 MB, about four minutes per era.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

TOP = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
                          check=True, cwd=Path(__file__).parent).stdout.strip())
sys.path.insert(0, str(TOP / 'tests'))
os.chdir(TOP)

import mutants  # noqa: E402

ERAS = ('legacy', 'modern')
PIN = 'test_an_sftp_session_after_a_reconnect_opens_every_step_on_its_worker'
PIN_ROWS = tuple(f'test_ssh_liveness.py::{PIN}[{step}]' for step in ('channel', 'subsystem', 'version'))
CASES = ('shol-session-channel-only-on-the-worker', 'shol-session-version-on-the-call')
EXEC = 'test_ssh_exec.py'
FAMILY = (
    f'{EXEC}::test_a_late_reconnect_onto_a_link_that_goes_silent_again_ends_in_time[write_file]',
    f'{EXEC}::test_a_late_reconnect_onto_a_live_link_runs_the_call[write_file]',
    *(f'{EXEC}::test_an_sftp_open_cut_by_a_silent_link_reconnects[{step}]' for step in ('channel', 'subsystem', 'version')),
    f'{EXEC}::test_a_channel_open_outlasting_its_own_timeout_on_a_silent_link_reconnects[sftp]',
    f'{EXEC}::test_a_call_on_a_silent_link_reconnects[write_file]',
    'test_ssh_liveness.py::test_an_open_that_ends_after_its_call_gave_up_is_closed',
    'test_ssh_liveness.py::test_an_open_that_ends_in_time_is_the_calls',
    'test_ssh_liveness.py::test_liveness_texts_state_the_monitor',
)
STEP_ROWS = tuple(f'{EXEC}::test_a_late_reconnect_onto_a_link_that_goes_silent_again_ends_in_time[write_file-{step}]'
                  for step in ('subsystem', 'version'))
SURVIVED = ': passed, so the mutant survived it'


def _era(era: str, every_kind: bool) -> None:
    os.environ['CLUSTER_MCP_TEST_ERA'] = era
    if every_kind:
        os.environ['CLUSTER_MCP_TEST_EVERY_KIND'] = '1'
    else:
        os.environ.pop('CLUSTER_MCP_TEST_EVERY_KIND', None)


def pin_problems(era: str) -> list[str]:
    _era(era, False)
    with tempfile.TemporaryDirectory(prefix='f8-pin-') as scratch:
        report = Path(scratch) / 'junit.xml'
        status = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:cacheprovider', f'--junitxml={report}',
                                 *(f'tests/{row}' for row in PIN_ROWS)], cwd=TOP, timeout=300).returncode
        passed = set()
        if report.exists():
            passed = {case.get('name') for case in ET.parse(report).getroot().iter('testcase')
                      if not any(child.tag in ('failure', 'error', 'skipped') for child in case)}
    missing = [row for row in PIN_ROWS if row.split('::')[1] not in passed]
    return [f'{era}: the pin exited {status}, not passed: {missing}'] if status != 0 or missing else []


def _channel_only() -> mutants.Case:
    case = next((case for case in mutants.CASES if case.id == CASES[0]), None)
    assert case is not None, f'no {CASES[0]} case in tests/mutants.py'
    return case


def gap_problems(era: str) -> list[str]:
    _era(era, False)
    planted = dataclasses.replace(_channel_only(), id='f8-gap', targets=FAMILY, why='')
    violations = mutants.run_case(planted)
    survived = {v.removesuffix(SURVIVED) for v in violations if v.endswith(SURVIVED)}
    others = [v for v in violations if not v.endswith(SURVIVED) and v != 'the mutant survived: every target passed']
    if others or survived != set(FAMILY):
        return [f'{era}: the channel-only cap did not pass every default row of the family: '
                f'{"; ".join(others) or sorted(set(FAMILY) - survived)}']
    print(f'survived  the channel-only cap, every default row of the family passing ({len(FAMILY)}), {era}')
    return []


def plant_problems(era: str) -> list[str]:
    _era(era, True)
    planted = dataclasses.replace(_channel_only(), id='f8-review-plant', targets=STEP_ROWS, why='past its')
    violations = mutants.run_case(planted)
    _era(era, False)
    if violations:
        return [f'{era}: the channel-only cap did not fail the opt-in step rows past their bound: '
                f'{"; ".join(violations)}']
    print(f'killed  the channel-only cap by {", ".join(STEP_ROWS)} (opt-in), {era}')
    return []


def case_problems(era: str) -> list[str]:
    _era(era, False)
    found = {case.id: case for case in mutants.CASES if case.id in CASES}
    problems = [f'{era}: no {case_id} case in tests/mutants.py' for case_id in CASES if case_id not in found]
    for case in found.values():
        if set(case.targets) != {f'{row}' for row in PIN_ROWS}:
            problems.append(f'{era}: {case.id} targets {case.targets}, not the pin\'s rows')
        violations = mutants.run_case(case)
        if violations:
            problems.append(f'{era}: {case.id}: {"; ".join(violations)}')
        else:
            print(f'killed  {case.id} by {", ".join(case.targets)} ({case.why!r}), {era}')
    return problems


def main(eras: str) -> int:
    if eras not in (*ERAS, 'both'):
        print(f'usage: F8-session-steps-cap.py legacy|modern|both (got {eras!r})')
        return 2
    problems: list[str] = []
    for era in ERAS if eras == 'both' else (eras,):
        problems += pin_problems(era) + case_problems(era)
        problems += gap_problems(era) if not problems else []
        problems += plant_problems(era) if not problems else []
    for problem in problems:
        print(f'FAILED  {problem}')
    print('ok' if not problems else f'{len(problems)} problems')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) == 2 else ''))
