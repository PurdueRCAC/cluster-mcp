# SPDX-FileCopyrightText: 2025 Purdue University
# SPDX-License-Identifier: MIT

"""The CLI rejects the removed documentation-indexing flags before anything runs."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import pytest
from cmdkit.app import exit_status


REPO_ROOT = Path(__file__).resolve().parents[1]
SANDBOX = REPO_ROOT / 'bin' / 'sandbox.sh'

# The installed console script, which the editable install points at this tree.
CLI = Path(sys.executable).with_name('rcac-mcp')

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


REJECTED = 'CRITICAL [rcac_mcp] unrecognized arguments: --index-docs'


@pytest.mark.unit
@pytest.mark.parametrize(('returncode', 'stdout', 'stderr'), [
    pytest.param(0, '', 'INFO [rcac_mcp] Execution mode: local',
                 id='started'),
    pytest.param(exit_status.bad_argument, '',
                 'INFO [rcac_mcp] Execution mode: ssh\n'
                 'CRITICAL [rcac_mcp] SSH host required: use --ssh-host or set RCAC_SSH_HOST',
                 id='ssh-host'),
    pytest.param(exit_status.bad_argument, '',
                 REJECTED + '\nDBFILE: /tmp/sandbox/.config/rcac-mcp/docs.db',
                 id='db-written'),
    pytest.param(exit_status.bad_argument, 'Documentation index built successfully:\n',
                 REJECTED,
                 id='stdout'),
])
def test_flag_check_catches_silent_accept(returncode: int, stdout: str, stderr: str) -> None:
    assert flag_violations(exit_status.bad_argument, '', REJECTED, ['--index-docs']) == []
    assert flag_violations(returncode, stdout, stderr, ['--index-docs'])
