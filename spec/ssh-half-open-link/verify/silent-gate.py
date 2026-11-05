"""The silent-link rows pass on this tree, and fail on develop wherever develop misbehaves.

Run from anywhere in the worktree:

    uv run python -I spec/ssh-half-open-link/verify/silent-gate.py commands both    # P1
    uv run python -I spec/ssh-half-open-link/verify/silent-gate.py transfers both   # P2
    uv run python -I spec/ssh-half-open-link/verify/silent-gate.py all both         # P3

The second word is the protocol era, `legacy`, `modern` or `both` (one after the other). With
`CLUSTER_MCP_TEST_EVERY_KIND=1` the reachable-host rows cover every tool, as the suite's do.

For each era:

1. **This tree.** Every row in the mode's table is run by node id, and each must pass. A row that
   is missing, skipped, errored or failed is red. The era log (`CLUSTER_MCP_ERA_LOG`) must show
   at least one in-process connect, every one of them in the era asked for.
2. **Develop.** The tree's tracked and untracked files are copied to a scratch directory, except
   `packages/`, which comes from BASE (the product code on develop); the copy's environment is
   synced from the lock; the same rows run there. A row marked to fail must fail (a JUnit
   `<failure>`, never an error or a skip) with its watchdog's message, `still waiting`, and, for a
   row that goes silent at a named step, that step's name (`at <step>`), so develop is shown to
   hang in the step the row targets. A row marked to pass must pass, so the copy demonstrably ran.

Every child's exit status is checked: a failed sync or a pytest that could not start is reported as
itself. Paths are taken from the worktree's top level. The children's environment is a copy of this
process's, with the project's, the interpreter's and the era's settings removed before the era is
set.

Footprint: one `uv sync` (cache-backed) and one pytest child at a time, each in a process group of
its own, killed on exit; a row starts one in-process SSH server (whose `close()` kills the execs it
started), a stall proxy and a sandboxed login bash. Under 600 MB. Each run's children carry a
token of their own (the scratch directory and `--basetemp`), and nothing carrying it may be left
running afterwards (`pgrep -f`).
"""

from __future__ import annotations

import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

BASE = '13c0e83'
FILE = 'tests/test_ssh_exec.py'
STOP = 'still waiting'
EVERY_KIND = os.environ.get('CLUSTER_MCP_TEST_EVERY_KIND') == '1'
DROPPED = ('VIRTUAL_ENV', 'UV_PROJECT', 'UV_PROJECT_ENVIRONMENT', 'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP',
           'PYTHONSAFEPATH', 'CLUSTER_MCP_TEST_ERA', 'CLUSTER_MCP_ERA_LOG')

FAILS, PASSES = 'fails', 'passes'

COMMAND_TOOLS = ['run', 'run_command', 'sbatch-path', 'read_file', 'list_directory']
TRANSFER_TOOLS = ['write_file', 'upload_file', 'download_file', 'sbatch-content']

# The R2 shapes, each with the step its server hook goes silent at (named in the watchdog's message).
TRANSFER_STEPS = {'put': 'upload', 'get': 'download', 'write-lookup': 'lookup', 'write-stage': 'stage',
                  'write-upload': 'upload', 'write-mkdir': 'mkdir', 'write-place': 'place',
                  'write-place-gone': 'place', 'sbatch': 'upload'}


def _rows(mode: str) -> dict[str, tuple[str, str | None]]:
    """Each row the mode names, by test id, with what it must do on develop and the step it targets."""
    rows: dict[str, tuple[str, str | None]] = {}
    if mode in ('commands', 'all'):
        for tool in COMMAND_TOOLS if EVERY_KIND else ['run', 'run_command']:
            rows[f'test_a_call_on_a_silent_link_reconnects[{tool}]'] = (FAILS, None)
        for tool in COMMAND_TOOLS:
            rows[f'test_a_call_on_a_silent_link_to_a_gone_host_is_not_run[{tool}]'] = (FAILS, None)
        rows['test_a_channel_open_outlasting_its_own_timeout_on_a_silent_link_reconnects[run]'] = (FAILS, None)
        rows['test_a_reconnect_onto_a_link_that_goes_silent_still_ends_in_time'] = (FAILS, None)
        for shape in ('no-timeout', 'later-timeout'):
            rows[f'test_a_command_on_a_link_that_goes_silent_is_lost[{shape}]'] = (FAILS, None)
        for tool in ('run', 'sbatch-path'):
            rows[f'test_a_command_cut_by_a_silent_link_is_never_run_twice[{tool}]'] = (FAILS, None)
        rows['test_a_command_on_a_link_that_goes_silent_ends_at_its_timeout'] = (PASSES, None)
        for shape in ('quiet', 'slow-link'):
            rows[f'test_a_quiet_command_is_not_taken_for_a_silent_link[{shape}]'] = (PASSES, None)
        rows['test_an_idle_connection_is_not_taken_for_a_silent_link'] = (PASSES, None)
        rows['test_a_call_beside_a_command_on_a_silent_link_ends_in_time'] = (FAILS, None)
    if mode in ('transfers', 'all'):
        for tool in TRANSFER_TOOLS if EVERY_KIND else ['write_file']:
            rows[f'test_a_call_on_a_silent_link_reconnects[{tool}]'] = (FAILS, None)
        for tool in TRANSFER_TOOLS:
            rows[f'test_a_call_on_a_silent_link_to_a_gone_host_is_not_run[{tool}]'] = (FAILS, None)
        for step in ('channel', 'subsystem', 'version'):
            rows[f'test_an_sftp_open_cut_by_a_silent_link_reconnects[{step}]'] = (FAILS, step)
        rows['test_a_channel_open_outlasting_its_own_timeout_on_a_silent_link_reconnects[sftp]'] = (FAILS, None)
        for shape, step in TRANSFER_STEPS.items():
            rows[f'test_a_transfer_on_a_link_that_goes_silent_may_be_partly_made[{shape}]'] = (FAILS, step)
        for shape in ('put', 'get', 'write'):
            rows[f'test_a_slow_transfer_is_not_taken_for_a_silent_link[{shape}]'] = (PASSES, None)
        rows['test_a_call_beside_a_transfer_stalled_on_a_silent_link_ends_in_time'] = (FAILS, 'upload')
    return rows


def _env(era: str, log: str) -> dict[str, str]:
    """The children's environment: a copy of ours, these settings removed, then the era and its log."""
    env = dict(os.environ)
    for key in DROPPED:
        env.pop(key, None)
    if era == 'modern':
        env['CLUSTER_MCP_TEST_ERA'] = 'modern'
    env['CLUSTER_MCP_ERA_LOG'] = log
    return env


def _child(argv: list[str], cwd: str, env: dict[str, str]) -> int:
    """Run one child in a process group of its own, kill that group whatever happens, return its status."""
    proc = subprocess.Popen(argv, cwd=cwd, env=env, start_new_session=True)
    try:
        return proc.wait()
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _outcomes(cwd: str, env: dict[str, str], rows: list[str], basetemp: str, sync: bool,
              problems: list[str], where: str) -> dict[str, tuple[str, str]]:
    report = os.path.join(basetemp + '-report', 'junit.xml')
    argv = ['uv', 'run', *([] if sync else ['--no-sync']), 'pytest', '-q', '-p', 'no:cacheprovider',
            f'--basetemp={basetemp}', f'--junitxml={report}', *(f'{FILE}::{row}' for row in rows)]
    status = _child(argv, cwd, env)
    if status not in (0, 1):
        # 0 all passed, 1 some failed: anything else is a run that did not happen as asked.
        problems.append(f'{where}: pytest exited {status} (not a test outcome)')
    outcomes: dict[str, tuple[str, str]] = {}
    if not os.path.exists(report):
        return outcomes
    for case in ET.parse(report).getroot().iter('testcase'):
        # A failure wins over a teardown error beside it: the row's own assertion is what counts.
        found = {child.tag: (child.get('message') or '') + (child.text or '') for child in case}
        outcome = next((tag for tag in ('failure', 'error', 'skipped') if tag in found), 'passed')
        outcomes[case.get('name', '')] = (outcome, found.get(outcome, ''))
    return outcomes


def _era_proof(log: str, era: str, where: str, problems: list[str]) -> None:
    try:
        with open(log, encoding='utf-8') as handle:
            lines = [line for line in handle.read().splitlines() if line.strip()]
    except FileNotFoundError:
        lines = []
    if not lines:
        problems.append(f'{where}: no in-process connect was logged, so the era was never shown')
    wrong = [line for line in lines if not line.startswith(f'era={era} ')]
    if wrong:
        problems.append(f'{where}: {len(wrong)} connect(s) not in the {era} era, first: {wrong[0]}')


def _develop(top: str, scratch: str, era: str, rows: list[str], problems: list[str]) -> dict[str, tuple[str, str]]:
    copy = os.path.join(scratch, f'{era}-develop')
    listed = subprocess.run(['git', 'ls-files', '-co', '--exclude-standard', '-z'], cwd=top, check=True,
                            capture_output=True).stdout.decode().split('\0')
    for name in filter(None, listed):
        source = os.path.join(top, name)
        if name.startswith('packages/') or not os.path.lexists(source):
            continue
        target = os.path.join(copy, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=False)
    archive = subprocess.run(['git', 'archive', BASE, 'packages'], cwd=top, check=True, capture_output=True).stdout
    subprocess.run(['tar', '-x', '-C', copy], input=archive, check=True)
    log = os.path.join(scratch, f'{era}-develop.log')
    env = _env(era, log)
    status = _child(['uv', 'sync', '--locked', '--quiet'], copy, env)
    if status != 0:
        problems.append(f'{era} develop: uv sync --locked exited {status}; its rows did not run')
        return {}
    outcomes = _outcomes(copy, env, rows, os.path.join(scratch, f'{era}-develop-tmp'), False, problems,
                         f'{era} develop')
    _era_proof(log, era, f'{era} develop', problems)
    return outcomes


def main(mode: str, eras: str) -> int:
    if mode not in ('commands', 'transfers', 'all') or eras not in ('legacy', 'modern', 'both'):
        print('usage: silent-gate.py commands|transfers|all legacy|modern|both')
        return 2
    top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], check=True, capture_output=True,
                         text=True).stdout.strip()
    rows = _rows(mode)
    problems: list[str] = []
    token = f'shol-gate-{secrets.token_hex(4)}-'
    with tempfile.TemporaryDirectory(prefix=token) as scratch:
        for era in (['legacy', 'modern'] if eras == 'both' else [eras]):
            log = os.path.join(scratch, f'{era}-here.log')
            here = _outcomes(top, _env(era, log), list(rows), os.path.join(scratch, f'{era}-here'), True,
                             problems, f'{era} here')
            _era_proof(log, era, f'{era} here', problems)
            for row in rows:
                outcome, _ = here.get(row, ('not run', ''))
                if outcome != 'passed':
                    problems.append(f'{era}: {row}: expected to pass on this tree, got {outcome}')
            there = _develop(top, scratch, era, list(rows), problems)
            for row, (expected, step) in rows.items():
                outcome, message = there.get(row, ('not run', ''))
                if expected == FAILS and (outcome != 'failure' or STOP not in message
                                          or (step is not None and f'at {step}' not in message)):
                    want = STOP + (f'" at "{step}' if step else '')
                    problems.append(f'{era}: {row}: expected to fail on {BASE} with "{want}", got {outcome}')
                if expected == PASSES and outcome != 'passed':
                    problems.append(f'{era}: {row}: expected to pass on {BASE} (the copy must run), got {outcome}')
            for row in sorted(rows):
                print(f'{era:6} here {here.get(row, ("not run",))[0]:8} '
                      f'{BASE} {there.get(row, ("not run",))[0]:8} {row}')
        left = subprocess.run(['pgrep', '-f', token], capture_output=True, text=True).stdout.split()
    if left:
        problems.append(f'processes of this gate still running: {" ".join(left)}')
    print('\n'.join(problems) or f'every {mode} row passes here and does what it must on {BASE}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(*(sys.argv[1:3] + ['', ''])[:2]))
