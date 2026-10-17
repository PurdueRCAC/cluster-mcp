# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""A delegated command starts exactly one `sudo` argv, and every backend satisfies `Executor`.

`DelegatingExecutor.run` must launch `sudo -n -H -u <local user> <shell> -c <command line>`
(§ Invariants §5). `-n` keeps a missing sudoers rule an error instead of a hang on a TTY nobody
has; `-H` gives the target user their own HOME. The shell is the server process's `$SHELL`,
captured when the executor is built, never re-read per command from an environment a caller might
influence. A `cwd` is quoted as one shell word, while the command itself passes through unquoted,
because it *is* a shell command. The argv is recorded at `subprocess.Popen` by the `launches`
fixture, so nothing here runs `sudo`. These argv rows pin today's launch on purpose: the
`safe-execution` seed replaces the executor API, and rewriting them is that cycle's deliberate
work, not breakage.

The three backends (`SSHExecutor`, `LocalShellExecutor`, `DelegatingExecutor`) must each satisfy
the runtime-checkable `Executor` protocol (§ Invariants §2), which checks member presence only.
`SSHExecutor` connects in its constructor, so its row replaces the module global
`rcac_mcp.executor.ssh.Connection` (an `rcac_mcp` internal, bound to Fabric) with a fake that
records it was built and opened for the host: no host is reached.
"""

from __future__ import annotations

import shlex
from typing import Any, Sequence

import pytest

import rcac_mcp.executor.ssh
from rcac_mcp.executor.base import Executor
from rcac_mcp.executor.delegate import DelegatingExecutor
from rcac_mcp.executor.shell import LocalShellExecutor
from rcac_mcp.executor.ssh import SSHExecutor

SHELL_A = '/opt/test-shell-a'
SHELL_B = '/opt/test-shell-b'
COMMAND = 'echo $HOME; ls *'
USER_MAP = {'bob': 'ubob'}

# The protocol's members, named in a failure so a missing one is visible.
PROTOCOL_MEMBERS = ('hostname', 'run', 'put', 'get', 'open', 'close', '__enter__', '__exit__')

# The position of each element in the expected argv, for naming a difference.
ARGV_ROLES = ('program', 'non-interactive flag', 'HOME flag', 'user flag', 'local user', 'shell',
              'shell flag', 'command line')


def sudo_argv_violations(argv: Sequence[str], user: str, shell: str, command_line: str) -> list[str]:
    """Return every difference between `argv` and the delegated launch; empty means exact.

    The expected argv is `['sudo', '-n', '-H', '-u', user, shell, '-c', command_line]`, element
    for element: a dropped or added flag, another user or shell, or a command line quoted or
    rewritten in any way is a difference.
    """
    got = list(argv)
    expected = ['sudo', '-n', '-H', '-u', user, shell, '-c', command_line]
    if got == expected:
        return []
    if len(got) != len(expected):
        missing = [part for part in expected if part not in got]
        extra = [part for part in got if part not in expected]
        return [f'argv differs: {len(got)} elements, expected {len(expected)}; '
                f'missing {missing!r}, extra {extra!r}: {got!r}']
    return [f'argv differs at {i} ({role}): {g!r}, expected {e!r}'
            for i, (role, g, e) in enumerate(zip(ARGV_ROLES, got, expected)) if g != e]


def command_line_for(cwd: str | None) -> str:
    return COMMAND if cwd is None else f'cd {shlex.quote(cwd)} && {COMMAND}'


@pytest.mark.unit
@pytest.mark.parametrize('cwd', [
    pytest.param(None, id='no-cwd'),
    pytest.param('/data/my dir', id='cwd-spaces'),
    pytest.param("/data/x; rm -rf / $(id) 'q'", id='cwd-metacharacters'),
])
def test_sudo_argv(cwd: str | None, monkeypatch: pytest.MonkeyPatch, launches: list[list[str]], guard) -> None:
    monkeypatch.setenv('SHELL', SHELL_A)
    result = DelegatingExecutor('bob', USER_MAP).run(COMMAND, cwd=cwd)
    assert len(launches) == 1, f'launch count {len(launches)}, expected 1: {launches!r}'
    argv = launches[0]
    command_line = command_line_for(cwd)
    violations = sudo_argv_violations(argv, 'ubob', SHELL_A, command_line)
    if cwd is not None:
        # The shell must see the cwd as one word, whatever it holds.
        words = shlex.split(argv[-1])[:3]
        if words != ['cd', cwd, '&&']:
            violations.append(f'argv differs: the command line does not cd into the cwd as one word: {words!r}')
    assert violations == [], '\n'.join(violations)
    assert result.stdout == f'ubob|{command_line}', f'result lacks the launch marker: {result.stdout!r}'
    assert guard.refused == []


@pytest.mark.unit
def test_shell_is_captured_at_construction(monkeypatch: pytest.MonkeyPatch, launches: list[list[str]], guard) -> None:
    monkeypatch.setenv('SHELL', SHELL_A)
    executor = DelegatingExecutor('bob', USER_MAP)
    monkeypatch.setenv('SHELL', SHELL_B)
    executor.run(COMMAND)
    assert len(launches) == 1, f'launch count {len(launches)}, expected 1: {launches!r}'
    violations = sudo_argv_violations(launches[0], 'ubob', SHELL_A, COMMAND)
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


GOOD_ARGV = ['sudo', '-n', '-H', '-u', 'ubob', SHELL_A, '-c', command_line_for('/data/my dir')]


@pytest.mark.unit
@pytest.mark.parametrize(('argv', 'fragment'), [
    pytest.param([a for a in GOOD_ARGV if a != '-n'], "missing ['-n']", id='n-dropped'),
    pytest.param([a for a in GOOD_ARGV if a != '-H'], "missing ['-H']", id='H-dropped'),
    pytest.param(GOOD_ARGV[:-1] + [shlex.quote(GOOD_ARGV[-1])], '(command line)', id='command-quoted'),
    pytest.param(GOOD_ARGV[:-1] + [f'cd /data/my dir && {COMMAND}'], '(command line)', id='cwd-unquoted'),
    pytest.param(GOOD_ARGV[:5] + [SHELL_B] + GOOD_ARGV[6:], '(shell)', id='wrong-shell'),
    pytest.param(GOOD_ARGV[:4] + ['ualice'] + GOOD_ARGV[5:], '(local user)', id='wrong-user'),
])
def test_argv_check_catches_drift(argv: list[str], fragment: str) -> None:
    clean = sudo_argv_violations(GOOD_ARGV, 'ubob', SHELL_A, GOOD_ARGV[-1])
    assert clean == [], clean
    violations = sudo_argv_violations(argv, 'ubob', SHELL_A, GOOD_ARGV[-1])
    assert any('argv differs' in v and fragment in v for v in violations), violations


class FakeConnection:
    """Stands in for `fabric.Connection`: records that it was built and opened, reaches no host."""

    made: list[FakeConnection]

    def __init__(self, host: str, **kwargs: Any) -> None:
        self.host = host
        self.kwargs = kwargs
        self.opened = 0
        self.is_connected = False
        self.made.append(self)

    def open(self) -> None:
        self.opened += 1
        self.is_connected = True

    def close(self) -> None:
        self.is_connected = False

    def run(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError('the fake connection runs nothing')

    def put(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError('the fake connection transfers nothing')

    def get(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError('the fake connection transfers nothing')


BACKENDS = {
    'ssh': lambda: SSHExecutor('cluster.invalid'),
    'local': LocalShellExecutor,
    'delegate': lambda: DelegatingExecutor('bob', USER_MAP),
}


@pytest.mark.unit
@pytest.mark.parametrize('backend', list(BACKENDS))
def test_backend_satisfies_executor_protocol(backend: str, monkeypatch: pytest.MonkeyPatch, guard) -> None:
    made: list[FakeConnection] = []
    monkeypatch.setattr(rcac_mcp.executor.ssh, 'Connection', type('FakeConnection', (FakeConnection,), {'made': made}))
    executor = BACKENDS[backend]()
    missing = [name for name in PROTOCOL_MEMBERS if not hasattr(executor, name)]
    assert isinstance(executor, Executor), f'{type(executor).__name__} does not satisfy Executor; missing {missing}'
    if backend == 'ssh':
        built = [(c.host, c.opened) for c in made]
        assert built == [('cluster.invalid', 1)], f'expected one fake connection opened once for the host: {built!r}'
    assert guard.refused == []
