"""Review cycle 1, F1: the watchdog acts only on the program's death or its release, never on time.

    uv run python -I spec/timeout-process-cleanup/remediation/F1-never-on-time.py      from the worktree root

The property, evaluated in every mode and every login shell rather than read from one line: under a
startup file that bounds or interrupts a shell builtin's wait (a readonly, exported `TMOUT` below
the command's run; `read` turned off beside an exported `TMOUT`; functions named like the paths the
watchdog runs and like `cat`, a `cat` first on PATH), a command that has not reached its deadline,
or has no timeout, completes with its output and its background job. The rows are
`tests/test_timeout_stop.py`'s profile rows with `CLUSTER_MCP_TEST_EVERY_KIND=1` (which this checker
sets and asserts it collected): `test_a_profile_tmout_stops_nothing` with no timeout and a longer
one, and `test_a_profile_cannot_cut_the_watchdogs_wait_short`, in `local`, `delegate-root`,
`delegate` and every `ssh-<shell>`; `test_run_command_outlives_a_profile_tmout` through the tool;
and the grace rows, whose profile's `sleep` function, `/bin/sleep` function and PATH `sleep` must
not shorten the watchdog's wait.

It also checks the text the rows exercise: the watchdog's rendered line runs no shell builtin that
waits (`read`, `wait`, `select`, `sleep`) and names its external programs by absolute path, unset
as functions before the fork. Green when every expected row was collected and passed and the text
holds. Footprint: one pytest child, under 500 MB, about a minute.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SETTINGS = ('local', 'delegate-root', 'delegate', 'ssh-bash', 'ssh-zsh', 'ssh-sh', 'ssh-tcsh')
EXPECTED = ([f'test_a_profile_tmout_stops_nothing[{s}-{t}]' for s in SETTINGS for t in ('no-timeout', 'timeout')]
            + [f'test_a_profile_cannot_cut_the_watchdogs_wait_short[{s}]' for s in SETTINGS]
            + [f'test_a_stopping_command_gets_its_grace[{s}]' for s in SETTINGS]
            + ['test_run_command_outlives_a_profile_tmout'])


def text_problems() -> list[str]:
    from cluster_mcp.core.executor import launch
    line = launch.WATCHDOG.format(grace=format(launch.GRACE, 'g'))
    body = line.partition('>(')[2].rpartition('); trap - TERM')[0]
    problems = []
    words = set(re.findall(r'(?<![/\w-])([a-z]+)\b', body))
    problems += [f'the watchdog runs the builtin `{word}`, which can wait on time' for word in
                 ('read', 'wait', 'select', 'sleep') if word in words]
    for path in sorted(set(re.findall(r'(/bin/\w+)', body))):
        if f'unset -f' not in line.partition("trap '' TERM")[0] or path not in line.partition("trap '' TERM")[0]:
            problems.append(f'{path}: a function by that name is not unset before the fork')
    return problems


def main() -> int:
    problems = text_problems()
    with tempfile.TemporaryDirectory(prefix='tpc-f1-') as scratch:
        report = Path(scratch, 'junit.xml')
        env = dict(os.environ, CLUSTER_MCP_TEST_EVERY_KIND='1')
        code = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-k',
                               'tmout or wait_short or grace', f'--junitxml={report}', 'tests/test_timeout_stop.py'],
                              env=env).returncode
        outcomes = {c.get('name'): next((t.tag for t in c if t.tag in ('failure', 'error', 'skipped')), 'passed')
                    for c in ET.parse(report).getroot().iter('testcase')}
    problems += [f'{row}: {outcomes.get(row, "not collected")}' for row in EXPECTED if outcomes.get(row) != 'passed']
    if code and not problems:
        problems.append(f'pytest exit {code}')
    print('\n'.join(problems) or f'F1: {len(EXPECTED)} profile rows in every mode and login shell passed; the '
                                 'watchdog waits on no builtin and runs no function in place of its paths')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
