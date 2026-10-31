# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""F7 (review 2): every function `READ_SITE` relies on is reset by the script, and pinned.

`uv run python spec/agents-d-instructions/remediation/F7-read-site-functions.py`, from the tree root.

- Oracle: bash itself. `READ_SITE` runs under `set -x` on planted directories in every state it
  answers (files, missing, not a directory, unreadable directory, unreadable file); every command
  the trace shows that is not a POSIX special builtin must be unset as a function in front of it,
  by `launch.FIXED_RESET` or by the script's first line, and `[` must not run at all.
- Hijack: the fixed argv run with a function exported over each such command and `[`, alone and all
  at once (the `BASH_FUNC_<name>%%` form a profile's `export -f` gives), reads what `read_local`
  reads. A control runs the same functions against the script with both resets taken away and must
  read something else, so the hijack is known to bite.
- Login shells: the suite's own rows, a login profile exporting those functions under the in-process
  and the loopback login bash (`test_a_profile_cannot_change_the_remote_read[local|ssh]`), and the
  static check (`test_every_command_the_remote_read_runs_is_reset`). `READ_SITE` runs only in `ssh`
  mode, which no sandboxed CLI drive reaches (the sandbox fails closed on SSH); the loopback row is
  that drive.
- The class's mutant: `site-reset-dropped`.

Footprint: one Python process, about 40 sandboxed bash children, one pytest child, one mutation
child; about 30 s, under 200 MB.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

from common import SANDBOX, check, finish, mutants, plant, site, unlock

from rcac_mcp.executor.launch import FIXED_RESET
from rcac_mcp.scripts import script_argv

SPECIAL = {'unset', 'set', 'exit', 'continue', 'break', 'return', 'eval', 'exec', 'export', 'readonly', 'shift',
           'trap', 'times', '.', ':'}
# Compound commands bash traces by their keyword; no function can be named for one.
KEYWORDS = {'for', 'if', 'while', 'until', 'case', 'select', '[[', '(('}
FILES = {'a.md': 'Alpha.\n', 'b.md': 'Bravo.\n', '.h.md': 'Hidden.\n'}


def run(root: Path, script: str, env: tuple[str, ...] = (), trace: bool = False) -> subprocess.CompletedProcess[str]:
    argv = script_argv(site.READ_SITE, 'cluster_context', str(root))
    c = argv.index('-c')
    argv[c + 1] = ('set -x\n' if trace else '') + script
    return subprocess.run([str(SANDBOX), 'env', *env, *argv], capture_output=True, text=True, timeout=60,
                          stdin=subprocess.DEVNULL)


def states(tmp: Path) -> dict[str, Path]:
    out = {'files': plant(tmp / 'files', FILES), 'missing': tmp / 'missing'}
    (tmp / 'notdir').write_text('x')
    out['notdir'] = tmp / 'notdir'
    out['unreadable-dir'] = plant(tmp / 'unreadable-dir', FILES, {'.': 0})
    out['unreadable-file'] = plant(tmp / 'unreadable-file', FILES, {'b.md': 0})
    return out


def resets() -> set[str]:
    first = site.READ_SITE.splitlines()[0].split()
    check(first[:2] == ['unset', '-f'], f'the first line of READ_SITE is not its function reset: {first}')
    return set(FIXED_RESET.split(';')[0].split()[2:]) | set(first[2:])


def traced(tmp: Path) -> set[str]:
    words = set()
    for label, root in states(tmp).items():
        done = run(root, FIXED_RESET + site.READ_SITE, trace=True)
        check(done.returncode == 0, f'trace {label}: exit {done.returncode}')
        for line in done.stderr.splitlines():
            match = re.match(r'^\++ (\S+)', line)
            if match and not re.fullmatch(r'\w+=.*', match.group(1)):
                words.add(match.group(1))
    return words


def hijacks(tmp: Path, names: list[str]) -> None:
    root = tmp / 'files'
    expected = site.read_local('this host', str(root))
    check(len(expected.files) == 3, f'the planted directory read as {expected}')
    body = '() {{ echo hijacked-{0}; return 0; }}'
    for group in [[n] for n in names] + [names]:
        env = tuple(f'BASH_FUNC_{n}%%={body.format(n)}' for n in group)
        done = run(root, FIXED_RESET + site.READ_SITE, env)
        got = site.parse_remote(done.stdout, 'this host')
        check(got == expected, f'functions over {group} changed the read: {got}')
    bare = '\n'.join(site.READ_SITE.splitlines()[1:]) + '\n'
    env = tuple(f'BASH_FUNC_{n}%%={body.format(n)}' for n in names)
    got = site.parse_remote(run(root, bare, env).stdout, 'this host')
    check(got != expected, 'control: with both resets taken away the functions changed nothing; the hijack is hollow')


def suite() -> None:
    t = 'tests/test_site.py'
    done = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                           f'{t}::test_a_profile_cannot_change_the_remote_read[local]',
                           f'{t}::test_a_profile_cannot_change_the_remote_read[ssh]',
                           f'{t}::test_every_command_the_remote_read_runs_is_reset'],
                          capture_output=True, text=True, timeout=600)
    check(done.returncode == 0 and '3 passed' in done.stdout, f'the suite rows: {done.stdout[-400:]}')


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='f7-') as name:
        tmp = Path(name)
        try:
            words = traced(tmp)
            replaceable = sorted(words - SPECIAL - KEYWORDS)
            check({'base64', 'tr', 'printf', 'test', 'cd', 'shopt'} <= words, f'the trace saw only {sorted(words)}')
            check('[' not in words, 'READ_SITE runs `[`, which `unset -f` cannot take in POSIX mode')
            check(set(replaceable) - resets() == set(),
                  f'READ_SITE runs {sorted(set(replaceable) - resets())} with no function reset')
            hijacks(tmp, [*replaceable, '['])
        finally:
            for label in ('unreadable-dir', 'unreadable-file'):
                unlock(tmp / label)
    suite()
    mutants('site-reset-dropped')
    return finish('F7 read site functions')


if __name__ == '__main__':
    sys.exit(main())
