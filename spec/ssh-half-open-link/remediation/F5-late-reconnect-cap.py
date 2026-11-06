"""Review cycle 2, F-A: a call never outlives its reconnect window, whatever the link does after a reconnect.

Run from anywhere in the worktree:

    UV_PYTHON=3.14 uv run python -I spec/ssh-half-open-link/remediation/F5-late-reconnect-cap.py both   # or legacy, modern

The finding's instance: a call met a silent link, reconnected just before its last start onto a link
that then went silent again, and its channel open (`_exec`, and `_sftp`'s the same) waited for the
new connection's own verdict, B after the open began, past the 3B bound. The class: every wait a call
makes once `_ensure_connected` has returned, after a reconnect or a loss, until its work starts (the
exec request, or the first file operation): the channel open, the SFTP subsystem and version steps,
the sends each makes on the connection's write path, and the settle that decides whether a failed
one was a loss (`_gone`). All of it now runs on a worker (`ssh._Within`) the call waits for no later
than its deadline. It is checked three ways, in each era asked for:

1. **The rows pass here.** With `CLUSTER_MCP_TEST_EVERY_KIND=1`, which this script exports and
   whose rows it asserts were collected: the late reconnect onto a link that goes silent again (under
   a 3 s connect bound, the host back 0.2 s before the last start) ends as nothing run, `timed out`,
   within the 9 s bound and the slack, for every tool and at the SFTP subsystem and version steps;
   a late reconnect onto a live link runs the call (`run`, `write_file`); the early reconnect row
   still ends in time. The unit rows for `_Within` and the doc pin pass too.
2. **The late rows are red on the reviewed code** (`82b1f0e`'s `packages/`, this tree's tests and
   lock): each late silent row fails, past its bound, or held past its watchdog; each live row and
   the early row pass there, so the copy demonstrably ran. The copy is made, synced and run by
   `verify/silent-gate.py`'s own `_develop`, its base set to the reviewed commit.
3. **The cases bite**: every `shol-cap-`, `shol-sftp-cap-` and `shol-within-` case in
   `tests/mutants.py` (the cap removed, kept for the first open only, taken from the open's start, at
   the last start, or on every open; a cut open reconnecting again; the worker waiting past the
   deadline, keeping a late open, or starting past it), fourteen, is run through the suite's runner
   and must be reported killed.

Exit 0 when all three hold. Footprint: one `uv sync` of the copy per era and one pytest child at a
time, each in its own process group, killed on exit; a row starts a loopback SSH server, a silent
hop and a sandboxed login bash. Under 600 MB, about 12 minutes for both eras.
"""

from __future__ import annotations

import importlib.util
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

REVIEWED = '82b1f0e'
ERAS = ('legacy', 'modern')
LATE = 'test_a_late_reconnect_onto_a_link_that_goes_silent_again_ends_in_time'
LIVE = 'test_a_late_reconnect_onto_a_live_link_runs_the_call'
EARLY = 'test_a_reconnect_onto_a_link_that_goes_silent_still_ends_in_time'
TOOLS = ('run', 'run_command', 'sbatch-path', 'read_file', 'list_directory', 'write_file', 'upload_file',
         'download_file', 'sbatch-content', 'write_file-subsystem', 'write_file-version')
SILENT_ROWS = tuple(f'{LATE}[{tool}]' for tool in TOOLS)
PASSING_ROWS = (f'{LIVE}[run]', f'{LIVE}[write_file]', EARLY)
UNITS = ('tests/test_ssh_liveness.py::test_an_open_that_ends_after_its_call_gave_up_is_closed',
         'tests/test_ssh_liveness.py::test_an_open_that_ends_in_time_is_the_calls',
         'tests/test_ssh_liveness.py::test_liveness_texts_state_the_monitor')
# What a late silent row's failure on the reviewed code says: past its bound, or held past its watchdog.
RED = ('past its', 'still waiting')
CASE_PREFIXES = ('shol-cap-', 'shol-sftp-cap-', 'shol-within-')


def _gate() -> object:
    """`verify/silent-gate.py`, loaded from its file (unchanged), its base set to the reviewed commit."""
    path = TOP / 'spec/ssh-half-open-link/verify/silent-gate.py'
    spec = importlib.util.spec_from_file_location('silent_gate', path)
    assert spec is not None and spec.loader is not None, f'cannot load {path}'
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    gate.BASE = REVIEWED
    return gate


def _units(gate: object, era: str, scratch: str, problems: list[str]) -> None:
    report = os.path.join(scratch, f'{era}-units.xml')
    env = gate._env(era, os.path.join(scratch, f'{era}-units.log'))
    status = gate._child(['uv', 'run', 'pytest', '-q', '-p', 'no:cacheprovider', f'--junitxml={report}', *UNITS],
                         str(TOP), env)
    passed = set()
    if os.path.exists(report):
        passed = {case.get('name') for case in ET.parse(report).getroot().iter('testcase')
                  if not any(child.tag in ('failure', 'error', 'skipped') for child in case)}
    missing = [unit for unit in UNITS if unit.split('::')[1] not in passed]
    if status != 0 or missing:
        problems.append(f'{era}: the unit rows exited {status}, not passed: {missing}')


def row_problems(gate: object, era: str, scratch: str) -> list[str]:
    problems: list[str] = []
    rows = [*SILENT_ROWS, *PASSING_ROWS]
    log = os.path.join(scratch, f'{era}-here.log')
    here = gate._outcomes(str(TOP), gate._env(era, log), rows, os.path.join(scratch, f'{era}-here'), True,
                          problems, f'{era} here')
    gate._era_proof(log, era, f'{era} here', problems)
    for row in rows:
        outcome, message = here.get(row, ('not collected', ''))
        if outcome != 'passed':
            problems.append(f'{era}: {row}: expected to pass here, got {outcome}: {message[:300]}')
    _units(gate, era, scratch, problems)
    there = gate._develop(str(TOP), scratch, era, rows, problems)
    for row in rows:
        outcome, message = there.get(row, ('not run', ''))
        if row in SILENT_ROWS and (outcome != 'failure' or not any(red in message for red in RED)):
            problems.append(f'{era}: {row}: expected to fail on {REVIEWED} past its bound, got {outcome}: '
                            f'{message[:300]}')
        if row in PASSING_ROWS and outcome != 'passed':
            problems.append(f'{era}: {row}: expected to pass on {REVIEWED} (the copy must run), got {outcome}')
        print(f'{era:6} here {here.get(row, ("not run",))[0]:8} {REVIEWED} {outcome:8} {row}')
        if row in SILENT_ROWS and outcome == 'failure':
            print(f'{"":6} {REVIEWED}: {" ".join(message.split())[:200]}')
    return problems


def case_problems(era: str) -> list[str]:
    os.environ['CLUSTER_MCP_TEST_ERA'] = era
    os.environ.pop('CLUSTER_MCP_TEST_EVERY_KIND', None)
    cases = [case for case in mutants.CASES if case.id.startswith(CASE_PREFIXES)]
    problems = [] if len(cases) == 14 else [f'{era}: {len(cases)} cases found, not the 14 of the cap']
    for case in cases:
        violations = mutants.run_case(case)
        if violations:
            problems.append(f'{era}: {case.id}: {"; ".join(violations)}')
        else:
            print(f'killed  {case.id} by {", ".join(case.targets)} ({case.why!r}), {era}')
    return problems


def main(eras: str) -> int:
    if eras not in (*ERAS, 'both'):
        print(f'usage: F5-late-reconnect-cap.py legacy|modern|both (got {eras!r})')
        return 2
    gate = _gate()
    problems: list[str] = []
    for era in ERAS if eras == 'both' else (eras,):
        os.environ['CLUSTER_MCP_TEST_EVERY_KIND'] = '1'
        with tempfile.TemporaryDirectory(prefix='f5-late-cap-') as scratch:
            problems += row_problems(gate, era, scratch)
        problems += case_problems(era)
    for problem in problems:
        print(f'FAILED  {problem}')
    print('ok' if not problems else f'{len(problems)} problems')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) == 2 else ''))
