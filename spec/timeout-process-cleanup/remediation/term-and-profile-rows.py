"""Review cycle 2, F1, F2, F3 and F4: one TERM per process, the deadline kept by the program, and the
watchdog proof against a startup file's shadows, in every mode and every login shell.

    uv run python -I spec/timeout-process-cleanup/remediation/term-and-profile-rows.py      from the worktree root

It supersedes cycle 1's `F1-never-on-time.py`, which stays as the record: that checker expected the
grace row under a non-root `delegate` server to print as it stops, which it did only because the
watchdog sent a second TERM (review cycle 2's F2; the ruling: KILL only, after the grace).

The properties, evaluated by the rows of `tests/test_timeout_stop.py` with
`CLUSTER_MCP_TEST_EVERY_KIND=1` (which this checker sets, and whose rows it asserts it collected):

- F2: a command that stops gracefully on its first TERM and exits at once on a second gets one TERM,
  as does a child of it, and prints its clean stop, in `local`, `delegate-root` and every
  `ssh-<shell>`; under a non-root `delegate` server they get no TERM and are KILLed after the grace;
- F3: a command whose deadline passes while a startup file that ignores TERM runs leaves nothing
  running past the bound, and never starts where the clock is the server's; a TERM that reaches the
  program while it forks its watchdog ends it before its command starts; both in every mode;
- F1 and F4: the watchdog never acts on time, and a startup file's shadows the prologue undoes (a
  readonly `TMOUT`; `read` off; functions named `/bin/cat`, `cat` or `unset`, or `unset` off; `trap`
  off beside an `enable` function; a function named `unalias` beside an alias over `kill`) neither
  cut a command short nor keep it from being stopped.

It also reads the rendered texts: the watchdog's body runs no shell builtin that waits and sends no
TERM; the prologue unsets the functions over its builtins in posix mode, after turning them back on,
and the functions named like the absolute paths the program runs after it leaves posix mode.

Footprint: one pytest child (each row a sandbox, a login shell, a few `sleep`s and, over `ssh`, one
in-process server), under 500 MB, about 3 minutes.
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
F3_SETTINGS = ('local', 'delegate-root', 'delegate', 'ssh-bash')
EXPECTED = ([f'test_a_profile_tmout_stops_nothing[{s}-{t}]' for s in SETTINGS for t in ('no-timeout', 'timeout')]
            + [f'test_a_profile_cannot_cut_the_watchdogs_wait_short[{s}]' for s in SETTINGS]
            + [f'test_a_profile_shadowing_unset_stops_nothing[{s}-{k}]' for s in SETTINGS
               for k in ('unset-function', 'unset-disabled')]
            + [f'test_a_stopping_command_gets_its_grace[{s}]' for s in SETTINGS if s != 'delegate']
            + ['test_a_non_root_server_kills_after_the_grace_with_no_term']
            + [f'test_a_command_past_its_deadline_is_stopped[{s}]' for s in F3_SETTINGS]
            + [f'test_a_term_while_the_watchdog_forks_is_kept[{s}]' for s in F3_SETTINGS]
            + [f'test_a_profile_shadowing_the_watchdog_is_undone[{s}]'
               for s in ('local-enable-n-trap', 'delegate-root-enable-n-trap', 'ssh-bash-enable-n-trap',
                         'local-kill-alias')]
            + ['test_run_command_outlives_a_profile_tmout'])
SELECT = 'tmout or wait_short or shadowing or grace or non_root or past_its_deadline or forks'


def text_problems() -> list[str]:
    from cluster_mcp.core.executor import launch
    problems = []
    line = launch.WATCHDOG.format(grace=format(launch.GRACE, 'g'))
    body = line.partition('>(')[2].rpartition(')')[0]
    words = set(re.findall(r'(?<![/\w-])([a-z]+)\b', body))
    problems += [f'the watchdog runs the builtin `{word}`, which can wait on time' for word in
                 ('read', 'wait', 'select', 'sleep') if word in words]
    if 'TERM 0' in body or 'TERM -' in body or re.search(r'kill -s (?!KILL)', body):
        problems.append(f'the watchdog sends a signal other than KILL: {body!r}')
    if not body.startswith("trap '' TERM;"):
        problems.append('the watchdog does not ignore TERM from its first statement')
    if not line.startswith('trap - TERM; exec 46>|'):
        problems.append('the program does not take TERM\'s default back before it forks the watchdog')
    posix, _, rest = launch.PROLOGUE.partition('set +euxvTkPm +o errtrace +o posix; ')
    if not rest:
        problems.append('the prologue does not leave posix mode')
    names = launch.BUILTINS.split()
    for name in ('unset', 'trap', 'kill', 'printf', 'exec', 'unalias'):
        if name not in names:
            problems.append(f'`{name}` is not among the builtins the prologue restores')
    want = f'POSIXLY_CORRECT=y; unset -f enable; enable {launch.BUILTINS} || :; unset -f {launch.BUILTINS}; '
    if want not in posix:
        problems.append('the prologue does not unset the functions over its builtins in posix mode, after '
                        'turning them back on')
    unset_paths = rest.partition('; ')[0].split()
    for path in sorted(set(re.findall(r'(/bin/\w+)', line + launch.DEADLINE_CHECK))):
        if unset_paths[:2] != ['unset', '-f'] or path not in unset_paths:
            problems.append(f'{path}: a function by that name is not unset once posix mode is left')
    return problems


def main() -> int:
    problems = text_problems()
    with tempfile.TemporaryDirectory(prefix='tpc-rows-') as scratch:
        report = Path(scratch, 'junit.xml')
        env = dict(os.environ, CLUSTER_MCP_TEST_EVERY_KIND='1')
        code = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-k', SELECT,
                               f'--junitxml={report}', 'tests/test_timeout_stop.py'], env=env).returncode
        outcomes = {c.get('name'): next((t.tag for t in c if t.tag in ('failure', 'error', 'skipped')), 'passed')
                    for c in ET.parse(report).getroot().iter('testcase')}
    problems += [f'{row}: {outcomes.get(row, "not collected")}' for row in EXPECTED if outcomes.get(row) != 'passed']
    problems += [f'{row}: {outcome}' for row, outcome in sorted(outcomes.items()) if outcome != 'passed'
                 and row not in EXPECTED]
    if code and not problems:
        problems.append(f'pytest exit {code}')
    print('\n'.join(problems) or f'F1-F4: {len(EXPECTED)} rows in every mode and login shell passed; the watchdog '
                                 'waits on no builtin and sends KILL alone, and the prologue undoes the shadows '
                                 'it can')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
