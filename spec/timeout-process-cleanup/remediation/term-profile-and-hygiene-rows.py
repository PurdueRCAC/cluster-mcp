"""Review cycle 3, B1, B2, B3, N1 and N3, and the `kill-alias` row removed: the watchdog born ignoring
TERM, a deadline while it is started kept, `run`'s return within the bound, no name of the
program's reaching a command, the shell options a command sees its profile's, and over `ssh` the
whole timeout after a slow connect, beside cycle 2's one TERM per process, deadline kept by the
program and watchdog proof against a startup file's shadows, in every mode and every login shell.

    uv run python -I spec/timeout-process-cleanup/remediation/term-profile-and-hygiene-rows.py      from the worktree root

It supersedes review cycle 2's `term-and-profile-rows.py`, which stays as the record: that checker
read the watchdog's body as starting with its own `trap '' TERM` and the program's line as taking
TERM's default back before the fork (the shape review cycle 3's B3 found born with TERM at its
default), expected the fork-window rows that sent the program a TERM with no deadline to fall back
on (a TERM the program now ignores while it forks, which only the deadline's check covers), and the
`kill-alias` row, which pins nothing on bash 3.2 to 5.3.

Review cycle 3 verification, N3: not reproduced. The posix-mode round trip changes the program's own
shell options but does not refresh `BASHOPTS`, so a bash the command starts gets the options the
login initialisation left (measured on bash 4.4, 5.1 and 5.2, the last by CI with nothing set
back). The options restore is removed; this checker no longer reads its saved list, its subshell
line or `shopt` among the builtins, and reads instead that the program runs no `shopt` and names no
`BASHOPTS` before its command. The shell-option rows stay, as the pin that nothing does.

The properties, evaluated by the rows of `tests/test_timeout_stop.py` with
`CLUSTER_MCP_TEST_EVERY_KIND=1` (which this checker sets, and whose rows it asserts it collected):

- B3: a deadline that comes while the program forks its watchdog (a window planted right after the
  fork, before TERM's default is back) starts nothing where the program reads the server's clock
  and is stopped over `ssh`; one that comes before the watchdog's first statement (a window planted
  there) ends nothing of the watchdog, and the command's processes are stopped; in every mode;
- B1: every timed-out row these select returns within `2 × GRACE` of the deadline, with the
  module's slack, the late-start rows included, in every mode;
- B2: under a profile's `set -a`, with every name of the program's exported beforehand, a command's
  environment holds no name it does not hold under no profile, in every mode;
- N3 (review cycle 3 verification): where the interpreter is bash 4.4 or later (CI's), a command
  sees the shell options a profile that exports `BASHOPTS` left, in every mode, with nothing set
  back; on an older bash the rows are not defined, and this checker says so;
- N1: over `ssh` a connection slower than the timeout still runs the command;
- and cycle 2's: one TERM per process and a clean stop, the deadline kept by the program, the
  watchdog never acting on time, and the shadows the prologue undoes.

It also reads the rendered texts: the watchdog's body runs no shell builtin that waits and sends no
TERM; the program forks it with TERM ignored and takes TERM's default back right after the fork; the
prologue unsets the functions over its builtins in posix mode, and the functions named like the
absolute paths the program runs after it leaves posix mode; the program runs no `shopt` and names no
`BASHOPTS` before its command (either could hand the round trip's options on); and every
`cluster_mcp_` name the program sets before its command is unset before the command line.

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


def bash_version() -> tuple[int, ...]:
    shown = subprocess.run(['/bin/bash', '--norc', '-c', 'echo "${BASH_VERSINFO[0]} ${BASH_VERSINFO[1]}"'],
                           capture_output=True, text=True, timeout=30).stdout.split()
    return tuple(int(part) for part in shown)


MODERN_BASH = bash_version() >= (4, 4)
EXPECTED = ([f'test_a_profile_tmout_stops_nothing[{s}-{t}]' for s in SETTINGS for t in ('no-timeout', 'timeout')]
            + [f'test_a_profile_cannot_cut_the_watchdogs_wait_short[{s}]' for s in SETTINGS]
            + [f'test_a_profile_shadowing_unset_stops_nothing[{s}-{k}]' for s in SETTINGS
               for k in ('unset-function', 'unset-disabled')]
            + [f'test_a_stopping_command_gets_its_grace[{s}]' for s in SETTINGS if s != 'delegate']
            + ['test_a_non_root_server_kills_after_the_grace_with_no_term']
            + [f'test_a_command_past_its_deadline_is_stopped[{s}]' for s in F3_SETTINGS]
            + [f'test_a_deadline_while_the_watchdog_starts[{s}-{w}]' for w in ('program', 'watchdog')
               for s in F3_SETTINGS]
            + [f'test_a_profile_shadowing_the_watchdog_is_undone[{s}-enable-n-trap]'
               for s in ('local', 'delegate-root', 'ssh-bash')]
            + [f'test_no_variable_of_the_program_reaches_the_command[{s}]' for s in F3_SETTINGS]
            + ([f'test_a_command_sees_the_shell_options_its_profile_left[{s}]' for s in F3_SETTINGS]
               if MODERN_BASH else [])
            + ['test_a_slow_connect_leaves_an_ssh_command_its_whole_timeout',
               'test_run_command_outlives_a_profile_tmout'])
# Rows that must not come back: what review cycle 3 retired.
RETIRED = ('test_a_term_while_the_watchdog_forks_is_kept', 'kill-alias')
SELECT = ('tmout or wait_short or shadowing or grace or non_root or past_its_deadline or watchdog_starts '
          'or no_variable or shell_options or slow_connect')


def fork_end(text: str) -> int:
    at, depth = text.index('>(') + 2, 1
    while depth:
        depth += {'(': 1, ')': -1}.get(text[at], 0)
        at += 1
    return at


def text_problems() -> list[str]:
    from cluster_mcp.core.executor import launch
    problems = []
    line = launch.WATCHDOG.format(grace=format(launch.GRACE, 'g'))
    body = line[line.index('>(') + 2:fork_end(line) - 1]
    words = set(re.findall(r'(?<![/\w-])([a-z]+)\b', body))
    problems += [f'the watchdog runs the builtin `{word}`, which can wait on time' for word in
                 ('read', 'wait', 'select', 'sleep') if word in words]
    if 'TERM 0' in body or 'TERM -' in body or re.search(r'kill -s (?!KILL)', body):
        problems.append(f'the watchdog sends a signal other than KILL: {body!r}')
    if not line.startswith("trap '' TERM; exec 46>| >("):
        problems.append('the program does not fork the watchdog with TERM ignored')
    if not line[fork_end(line):].startswith('; trap - TERM; '):
        problems.append('the program does not take TERM\'s default back right after the fork')
    if 'trap' in body:
        problems.append(f'the watchdog sets a trap of its own: {body!r}')
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
    for command in (['env'], 'env'):
        prog, _ = launch.program(command, timeout=5)
        opened = prog.index('\n(\n') + 3
        at = prog.index('exec ' if isinstance(command, list) else 'BASH_ENV= ENV= exec ', opened)
        before = prog[:at]
        for word in ('shopt', 'BASHOPTS'):
            if re.search(rf'\b{word}\b', before):
                problems.append(f'{command!r}: the program names `{word}` before its command, which could hand '
                                'the posix-mode round trip\'s shell options on')
        for name in sorted(set(re.findall(r'\b(cluster_mcp_\w+)', before))):
            if not re.search(rf'\bunset [^;\n]*\b{name}\b', before):
                problems.append(f'{command!r}: `{name}` is set before the command and not unset before it')
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
    problems += [f'{row}: a row review cycle 3 retired is back' for row in sorted(outcomes)
                 if any(retired in row for retired in RETIRED)]
    if not MODERN_BASH:
        options = [row for row in outcomes if row.startswith('test_a_command_sees_the_shell_options')]
        if options:
            problems.append(f'shell-option rows collected on a bash before 4.4: {options}')
    if code and not problems:
        problems.append(f'pytest exit {code}')
    note = '' if MODERN_BASH else ' (the shell-option rows are defined only on bash 4.4 or later: not run here)'
    print('\n'.join(problems) or f'B1-B3, N1, N3 and cycle 2\'s F1-F4: {len(EXPECTED)} rows in every mode and login '
                                 f'shell passed{note}; the watchdog is forked with TERM ignored and waits on no '
                                 'builtin, the prologue undoes the shadows it can, the program runs no `shopt`, '
                                 'and every name the program sets is unset before its command')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
