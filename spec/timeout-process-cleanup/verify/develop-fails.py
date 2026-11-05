"""R6 gate: the stop rows fail against the code on develop wherever it leaves a process running.

Run from the worktree root:

    uv run python -I spec/timeout-process-cleanup/verify/develop-fails.py local   # P1: local and delegate rows
    uv run python -I spec/timeout-process-cleanup/verify/develop-fails.py ssh     # P2: ssh rows
    uv run python -I spec/timeout-process-cleanup/verify/develop-fails.py all     # P3; with CLUSTER_MCP_TEST_EVERY_KIND=1, every login shell

It copies the working tree's tracked and untracked files (not ignored ones) to a scratch
directory, except `packages/`, which it takes from `BASE` (the product code on develop), syncs that
copy's environment from the lock, and runs `tests/test_timeout_stop.py` there. Then:

- every row in EXPECTED_FAIL for the mode must have run and failed (a JUnit `<failure>`, not an
  `<error>` or a skip) with the stop message, `still running`: a row that fails for another reason
  (an import, a fixture, a pid file not written) is not proof;
- every row in EXPECTED_PASS must have run and passed, so the copy demonstrably ran on develop's
  code with working stand-ins (a gate whose every row fails would prove nothing).

Footprint: one `uv sync` (cache-backed), then one pytest child (a row starts a sandbox, a login
bash, three `sleep`s and, over ssh, one in-process server), under 500 MB. Measured on the prototype
(macOS), the sync included: local 53 s, ssh 19 s, all with CLUSTER_MCP_TEST_EVERY_KIND=1 104 s.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

BASE = 'c8843b2'
STOP = 'test_a_timed_out_command_is_stopped'
TRAP = 'test_a_startup_file_ignoring_term_is_undone'
JOBS = 'test_a_completed_command_leaves_its_jobs_running'
DIED = 'test_a_command_that_dies_of_a_signal_leaves_its_jobs_running'
TOOL = 'test_run_command_stops_a_timed_out_command'  # local mode, the ignores-none shape
EVERY_KIND = os.environ.get('CLUSTER_MCP_TEST_EVERY_KIND') == '1'
SHELLS = ['bash', 'zsh', 'sh', 'tcsh'] if EVERY_KIND else ['bash']

EXPECTED_FAIL = {
    'local': [f'{STOP}[local-ignores-none]', f'{STOP}[delegate-root-ignores-none]', f'{STOP}[delegate-tree]',
              f'{STOP}[delegate-ignores-holding]', f'{TRAP}[delegate-profile]', TOOL],
    # A remote login shell's own rc file ignoring TERM: stopped only by the KILL request (GOAL Q6).
    'ssh': [*(f'{STOP}[ssh-{shell}-ignores-holding]' for shell in SHELLS), f'{TRAP}[ssh-bash-profile]',
            f'{TRAP}[ssh-bash-bashrc]', f'{TRAP}[ssh-zsh-zshenv]'],
}
EXPECTED_PASS = {
    'local': [f'{STOP}[local-tree]', f'{STOP}[local-ignores-holding]', f'{STOP}[delegate-root-tree]',
              f'{JOBS}[local]', f'{JOBS}[delegate]', f'{DIED}[local]', f'{DIED}[delegate]'],
    'ssh': [*(f'{STOP}[ssh-{shell}-tree]' for shell in SHELLS), f'{JOBS}[ssh-bash]', f'{DIED}[ssh-bash]'],
}
SELECT = {'local': 'local or delegate or run_command', 'ssh': 'ssh'}


def main(mode: str) -> int:
    modes = ['local', 'ssh'] if mode == 'all' else [mode]
    if any(m not in SELECT for m in modes):
        print(f'usage: develop-fails.py local|ssh|all (got {mode!r})')
        return 2
    listed = subprocess.run(['git', 'ls-files', '-co', '--exclude-standard', '-z'], check=True,
                            capture_output=True).stdout.decode().split('\0')
    with tempfile.TemporaryDirectory(prefix='tpc-develop-') as scratch:
        for name in filter(None, listed):
            if name.startswith('packages/') or not os.path.lexists(name):
                continue
            target = os.path.join(scratch, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(name, target, follow_symlinks=False)
        archive = subprocess.run(['git', 'archive', BASE, 'packages'], check=True, capture_output=True).stdout
        subprocess.run(['tar', '-x', '-C', scratch], input=archive, check=True)
        # The child's environment: a copy of ours, then this project's settings dropped.
        env = dict(os.environ)
        for key in ('VIRTUAL_ENV', 'UV_PROJECT', 'UV_PROJECT_ENVIRONMENT'):
            env.pop(key, None)
        subprocess.run(['uv', 'sync', '--locked', '--quiet'], cwd=scratch, env=env, check=True)
        report = os.path.join(scratch, 'junit.xml')
        selection = ' or '.join(f'({SELECT[m]})' for m in modes)
        subprocess.run(['uv', 'run', '--no-sync', 'pytest', '-q', '-p', 'no:cacheprovider', '-k', selection,
                        f'--junitxml={report}', 'tests/test_timeout_stop.py'], cwd=scratch, env=env)
        outcomes: dict[str, tuple[str, str]] = {}
        for case in ET.parse(report).getroot().iter('testcase'):
            # A failure wins over a teardown error beside it: the row's own assertion is what counts.
            found = {child.tag: (child.get('message') or '') + (child.text or '') for child in case}
            outcome = next((tag for tag in ('failure', 'error', 'skipped') if tag in found), 'passed')
            outcomes[case.get('name', '')] = (outcome, found.get(outcome, ''))
    problems: list[str] = []
    for m in modes:
        for row in EXPECTED_FAIL[m]:
            outcome, message = outcomes.get(row, ('not run', ''))
            if outcome != 'failure' or 'still running' not in message:
                problems.append(f'{row}: expected to fail on {BASE} with "still running", got {outcome}')
        for row in EXPECTED_PASS[m]:
            outcome, _ = outcomes.get(row, ('not run', ''))
            if outcome != 'passed':
                problems.append(f'{row}: expected to pass on {BASE} (the copy must run), got {outcome}')
    for row, (outcome, _) in sorted(outcomes.items()):
        print(f'{outcome:8} {row}')
    print('\n'.join(problems) or f'R6: every stop row fails on {BASE} where it leaves a process running')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ''))
