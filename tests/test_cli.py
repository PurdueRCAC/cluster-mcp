# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The CLI: its names, the deprecated `rcac-mcp` command, and the removed documentation flags.

`cluster-mcp` is the command; `rcac-mcp`, the server's old name, runs it unchanged after one
deprecation warning on stderr, stating the window as `harness.DEPRECATION_WINDOW` writes it out, and
never writes to stdout, which carries the stdio transport.
`python -m cluster_mcp.core` is the same entry point. The removed documentation-indexing flags are
rejected before anything runs. Every drive runs under bin/sandbox.sh.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Sequence

import pytest
from cmdkit.app import exit_status

from harness import DEPRECATION_WINDOW


REPO_ROOT = Path(__file__).resolve().parents[1]
SANDBOX = REPO_ROOT / 'bin' / 'sandbox.sh'

# The installed console scripts, which the editable install points at this tree: the command, and
# its deprecated old name.
CLI = Path(sys.executable).with_name('cluster-mcp')
LEGACY_CLI = Path(sys.executable).with_name('rcac-mcp')

# Runs the CLI with no stdin, then reports every database file left under the sandbox HOME
# on stderr, and exits with the CLI's own status.
DRIVE_SCRIPT = """\
"$@" < /dev/null
status=$?
find "$HOME" -type f -name '*.db' | while IFS= read -r path; do
    printf 'DBFILE: %s\\n' "$path" >&2
done
exit "$status"
"""


def flag_violations(returncode: int, stdout: str, stderr: str, flags: Sequence[str]) -> list[str]:
    """Return every way a CLI result differs from a clean rejection of `flags`; empty means clean.

    A clean rejection exits with `exit_status.bad_argument`, names each flag after
    `unrecognized arguments:`, never reaches the server (no `Execution mode` log line), prints
    nothing to stdout, and leaves no database file behind.
    """
    violations: list[str] = []
    if returncode != exit_status.bad_argument:
        violations.append(f'exit status {returncode}, expected {exit_status.bad_argument}')
    for flag in flags:
        pattern = r'unrecognized arguments:.*' + re.escape(flag) + r'(?![\w-])'
        if not re.search(pattern, stderr):
            violations.append(f'stderr does not report {flag!r} as unrecognized')
    if 'Execution mode' in stderr:
        violations.append('the server started (stderr logs an execution mode)')
    if stdout:
        violations.append(f'stdout is not empty: {stdout[:80]!r}')
    for line in stderr.splitlines():
        if line.startswith('DBFILE:'):
            violations.append(f'a database file was written: {line}')
    return violations


def drive(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the installed CLI with `argv` inside a fresh bin/sandbox.sh environment."""
    assert CLI.is_file(), f'installed CLI not found at {CLI}'
    assert os.access(SANDBOX, os.X_OK), f'{SANDBOX} is not executable'
    return subprocess.run(
        [str(SANDBOX), 'sh', '-c', DRIVE_SCRIPT, 'sh', str(CLI), *argv],
        capture_output=True, text=True, timeout=60, cwd=cwd,
    )


REMOVED_FLAG_CASES = [
    pytest.param(lambda tmp: ['--index-docs'],
                 ['--index-docs'], id='index-docs'),
    pytest.param(lambda tmp: ['--docs-path', str(tmp)],
                 ['--docs-path'], id='docs-path'),
    pytest.param(lambda tmp: ['--docs-output', str(tmp / 'docs.db')],
                 ['--docs-output'], id='docs-output'),
    pytest.param(lambda tmp: ['--index-docs', '--docs-path', str(tmp),
                              '--docs-output', str(tmp / 'docs.db')],
                 ['--index-docs', '--docs-path', '--docs-output'], id='all-three'),
    pytest.param(lambda tmp: ['-e', 'local', '--index-docs'],
                 ['--index-docs'], id='local-index-docs'),
]


@pytest.mark.integration
@pytest.mark.parametrize(('make_argv', 'flags'), REMOVED_FLAG_CASES)
def test_removed_flag_is_rejected(make_argv, flags: list[str], tmp_path: Path) -> None:
    result = drive(make_argv(tmp_path), cwd=tmp_path)
    assert flag_violations(result.returncode, result.stdout, result.stderr, flags) == []
    assert not (tmp_path / 'docs.db').exists()


@pytest.mark.integration
def test_flag_check_rejects_a_known_flag(tmp_path: Path) -> None:
    # A known flag that still exits bad_argument must not pass as a rejection.
    result = drive(['--generate-token'], cwd=tmp_path)
    assert result.returncode == exit_status.bad_argument
    assert 'JWT_SECRET' in result.stderr
    assert flag_violations(result.returncode, result.stdout, result.stderr, ['--generate-token'])


REJECTED = 'CRITICAL [cluster_mcp.core] unrecognized arguments: --index-docs'


@pytest.mark.unit
@pytest.mark.parametrize(('returncode', 'stdout', 'stderr'), [
    pytest.param(0, '', 'INFO [cluster_mcp.core] Execution mode: local',
                 id='started'),
    pytest.param(exit_status.bad_argument, '',
                 'INFO [cluster_mcp.core] Execution mode: ssh\n'
                 'CRITICAL [cluster_mcp.core] SSH host required: use --ssh-host or set CLUSTER_MCP_SSH_HOST',
                 id='ssh-host'),
    pytest.param(exit_status.bad_argument, '',
                 REJECTED + '\nDBFILE: /tmp/sandbox/.config/cluster-mcp/docs.db',
                 id='db-written'),
    pytest.param(exit_status.bad_argument, 'Documentation index built successfully:\n',
                 REJECTED,
                 id='stdout'),
])
def test_flag_check_catches_silent_accept(returncode: int, stdout: str, stderr: str) -> None:
    assert flag_violations(exit_status.bad_argument, '', REJECTED, ['--index-docs']) == []
    assert flag_violations(returncode, stdout, stderr, ['--index-docs'])


def sandboxed(argv: Sequence[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run `argv` under bin/sandbox.sh with `stdin` (none: at EOF), capturing both streams."""
    return subprocess.run([str(SANDBOX), *argv], input=stdin if stdin is not None else '',
                          capture_output=True, text=True, timeout=60)


# The deprecated command's warning, its window captured: a whole log line on stderr, the level
# (padded) and the logger's name, then the message, with nothing before it and nothing after. It is
# the one stderr line that names `rcac-mcp`, so a second warning, in any words, fails.
COMMAND_WARNING = re.compile(r'^ *WARNING \[[\w.]+\] the rcac-mcp command is (.*): use cluster-mcp instead$',
                             re.MULTILINE)

# The warning as the command prints it, the window written out.
WARNED = f' WARNING [cluster_mcp.core.deprecation] the rcac-mcp command is {DEPRECATION_WINDOW}: use cluster-mcp instead\n'


def window_violations(match: re.Match[str] | None, missing: str) -> list[str]:
    """`missing` when no warning matched, else every way its window is not the published one."""
    if match is None:
        return [missing]
    if match[1] != DEPRECATION_WINDOW:
        return [f'the warning states the window {match[1]!r}, not the published window {DEPRECATION_WINDOW!r}']
    return []


def naming_violations(stderr: str) -> list[str]:
    """A violation unless exactly one line of `stderr` names `rcac-mcp`."""
    named = [line for line in stderr.splitlines() if 'rcac-mcp' in line]
    if len(named) == 1:
        return []
    return [f'{len(named)} stderr lines name rcac-mcp, expected exactly one, the deprecation warning: {named[:4]!r}']


def legacy_violations(new: subprocess.CompletedProcess[str], old: subprocess.CompletedProcess[str]) -> list[str]:
    """Every way the `rcac-mcp` run `old` differs from the `cluster-mcp` run `new` plus one warning.

    The two must exit alike and print identical stdout; `old`'s stderr must be exactly one warning
    line, naming both commands and the published deprecation window, followed by `new`'s stderr, and
    that warning must be its only line naming `rcac-mcp`.
    """
    violations = []
    if old.returncode != new.returncode:
        violations.append(f'exit status {old.returncode} under rcac-mcp, {new.returncode} under cluster-mcp')
    if old.stdout != new.stdout:
        violations.append(f'stdout differs: {old.stdout[:120]!r} under rcac-mcp, {new.stdout[:120]!r} under cluster-mcp')
    warning, _, rest = old.stderr.partition('\n')
    violations += window_violations(COMMAND_WARNING.fullmatch(warning),
                                    f'the first stderr line is not the deprecation warning: {warning!r}')
    violations += naming_violations(old.stderr)
    if rest != new.stderr:
        violations.append(f'stderr after the warning differs from cluster-mcp\'s: {rest[:200]!r} vs {new.stderr[:200]!r}')
    return violations


LEGACY_ARGVS = [
    pytest.param([], id='none'),
    pytest.param(['--help'], id='help'),
    pytest.param(['--version'], id='version'),
    pytest.param(['--bogus'], id='bogus'),
]


@pytest.mark.integration
@pytest.mark.parametrize('argv', LEGACY_ARGVS)
def test_legacy_command_warns_then_runs_cluster_mcp(argv: list[str]) -> None:
    # With no arguments both fail closed (no SSH host in the sandbox); --bogus is a bad argument.
    new, old = sandboxed([str(CLI), *argv]), sandboxed([str(LEGACY_CLI), *argv])
    assert legacy_violations(new, old) == []


@pytest.mark.unit
@pytest.mark.parametrize(('old', 'fragment'), [
    pytest.param(subprocess.CompletedProcess([], 0, 'usage\n', 'INFO [x] started\n'),
                 'not the deprecation warning', id='silent'),
    pytest.param(subprocess.CompletedProcess([], 0, 'usage\n', WARNED + 'INFO [x] started\n'),
                 'exit status 0 under rcac-mcp', id='exit-swallowed'),
    pytest.param(subprocess.CompletedProcess([], 2, 'warning\nusage\n', WARNED + 'INFO [x] started\n'),
                 'stdout differs', id='stdout'),
    pytest.param(subprocess.CompletedProcess([], 2, 'usage\n', WARNED.replace(DEPRECATION_WINDOW, 'deprecated')
                                             + 'INFO [x] started\n'), 'not the published window', id='no-window'),
    pytest.param(subprocess.CompletedProcess([], 2, 'usage\n', WARNED.replace('0.4.0', '0.3.0') + 'INFO [x] started\n'),
                 'not the published window', id='other-window'),
    pytest.param(subprocess.CompletedProcess([], 2, 'usage\n', WARNED + WARNED + 'INFO [x] started\n'),
                 'stderr after the warning differs', id='twice'),
    pytest.param(subprocess.CompletedProcess([], 2, 'usage\n', WARNED.replace('] the', '] removed in 0.3.0; the')
                                             + 'INFO [x] started\n'), 'not the deprecation warning', id='prefixed'),
    pytest.param(subprocess.CompletedProcess([], 2, 'usage\n', 'removed in 0.3.0;' + WARNED + 'INFO [x] started\n'),
                 'not the deprecation warning', id='before-the-level'),
    pytest.param(subprocess.CompletedProcess([], 2, 'usage\n', WARNED.replace('instead', 'instead until 0.3.0')
                                             + 'INFO [x] started\n'), 'not the deprecation warning', id='suffixed'),
    pytest.param(subprocess.CompletedProcess([], 2, 'usage\n', WARNED + WARNED.replace('0.4.0', '0.3.0')
                                             + 'INFO [x] started\n'), '2 stderr lines name rcac-mcp', id='second-warning'),
    pytest.param(subprocess.CompletedProcess([], 2, 'usage\n', WARNED + 'INFO [x] started\n'
                                             + 'INFO [x] rcac-mcp goes in 0.3.0\n'), '2 stderr lines name rcac-mcp',
                 id='second-line-naming-the-command'),
])
def test_legacy_check_catches_drift(old: subprocess.CompletedProcess[str], fragment: str) -> None:
    new = subprocess.CompletedProcess([], 2, 'usage\n', 'INFO [x] started\n')
    good = subprocess.CompletedProcess([], 2, 'usage\n', WARNED + 'INFO [x] started\n')
    assert legacy_violations(new, good) == []
    violations = legacy_violations(new, old)
    assert any(fragment in v for v in violations), violations


INITIALIZE = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                         'params': {'protocolVersion': '2025-06-18', 'capabilities': {},
                                    'clientInfo': {'name': 'test_cli', 'version': '0'}}})


def stdio_violations(stdout: str, stderr: str) -> list[str]:
    """Every way a stdio session's output is not pure JSON-RPC on stdout with the warning, whole, as stderr's one line naming `rcac-mcp`."""
    violations = []
    answered = False
    for line in stdout.splitlines():
        try:
            message = json.loads(line)
        except ValueError:
            message = None
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0':
            violations.append(f'stdout carries a line that is not JSON-RPC: {line[:120]!r}')
        elif message.get('id') == 1 and 'result' in message:
            answered = True
    if not answered:
        violations.append(f'no answer to initialize on stdout: {stdout[:200]!r} (stderr {stderr[-300:]!r})')
    named = [line for line in stderr.splitlines() if 'rcac-mcp' in line]
    violations += naming_violations(stderr)
    violations += window_violations(COMMAND_WARNING.fullmatch(named[0]) if named else None,
                                    f'no stderr line is the deprecation warning: {stderr[:200]!r}')
    return violations


@pytest.mark.integration
def test_legacy_command_keeps_stdout_clean_on_stdio() -> None:
    # One initialize request, then EOF: the server answers and exits, and only the answer is stdout.
    result = sandboxed([str(LEGACY_CLI), '-e', 'local'], stdin=INITIALIZE + '\n')
    assert stdio_violations(result.stdout, result.stderr) == []


@pytest.mark.unit
def test_stdio_check_catches_a_stray_line() -> None:
    answer = '{"jsonrpc": "2.0", "id": 1, "result": {}}\n'
    assert stdio_violations(answer, WARNED) == []
    assert any('not JSON-RPC' in v for v in stdio_violations(WARNED + answer, ''))
    assert any('no answer' in v for v in stdio_violations('', WARNED))
    assert any('is the deprecation warning' in v for v in stdio_violations(answer, ''))
    other = WARNED.replace('0.4.0', '0.3.0')
    assert other != WARNED
    assert any('not the published window' in v for v in stdio_violations(answer, other))
    prefixed = WARNED.replace('] the', '] removed in 0.3.0; the')
    assert prefixed != WARNED
    assert any('is the deprecation warning' in v for v in stdio_violations(answer, prefixed))
    for twice in (WARNED + other, WARNED + WARNED, other + WARNED, WARNED + 'INFO [x] rcac-mcp goes in 0.3.0\n'):
        assert any('2 stderr lines name rcac-mcp' in v for v in stdio_violations(answer, twice)), twice


@pytest.mark.integration
@pytest.mark.parametrize('argv', [pytest.param(['--help'], id='help'), pytest.param(['--version'], id='version'),
                                  pytest.param(['--bogus'], id='bogus')])
def test_python_m_runs_the_entry_point(argv: list[str]) -> None:
    command = sandboxed([str(CLI), *argv])
    module = sandboxed([sys.executable, '-m', 'cluster_mcp.core', *argv])
    assert (module.returncode, module.stdout, module.stderr) == (command.returncode, command.stdout, command.stderr)
    assert command.stdout or command.stderr


@pytest.mark.integration
@pytest.mark.parametrize('command', [pytest.param(CLI, id='cluster-mcp'), pytest.param(LEGACY_CLI, id='rcac-mcp')])
@pytest.mark.parametrize('names', [pytest.param(('CLUSTER_MCP_SSH_HOST',), id='replacement'),
                                   pytest.param(('RCAC_SSH_HOST',), id='legacy'),
                                   pytest.param(('CLUSTER_MCP_SSH_HOST', 'RCAC_SSH_HOST'), id='both')])
def test_sandbox_fails_closed_with_either_host_exported(command: Path, names: tuple[str, ...]) -> None:
    # The host leaks from the calling environment; the sandbox unsets both names, so the bare
    # command (stdio, hence ssh) refuses to start instead of connecting anywhere.
    env = {**os.environ, **{name: f'leak-{name.lower()}.invalid' for name in names}}
    result = subprocess.run([str(SANDBOX), str(command)], input='', capture_output=True, text=True, timeout=60, env=env)
    assert result.returncode == exit_status.bad_argument, result.stderr
    assert 'SSH host required: use --ssh-host or set CLUSTER_MCP_SSH_HOST' in result.stderr, result.stderr
    assert 'leak-' not in result.stderr and 'cannot connect' not in result.stderr, result.stderr
    assert result.stdout == ''


@pytest.mark.integration
def test_version_identifies_as_cluster_mcp() -> None:
    shown = sandboxed([str(CLI), '--version'])
    usage = sandboxed([str(CLI), '--help'])
    assert shown.returncode == 0 and usage.returncode == 0, (shown.stderr, usage.stderr)
    assert shown.stdout.startswith(f'cluster-mcp v{version("cluster-mcp")} ('), shown.stdout
    assert usage.stdout.startswith('Usage:\n  cluster-mcp [-h]'), usage.stdout[:80]
    for text in (shown.stdout, usage.stdout):
        assert 'RCAC MCP Server' not in text and 'Purdue' not in text, text
