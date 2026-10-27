# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""The `ssh` executor against a loopback server that executes what it is sent, under each login shell.

`SSHExecutor` sends every command as the launcher's fixed bootstrap carrying one base64 word, so
whatever the user's login shell (bash, zsh, sh or tcsh here), the command runs under the pinned
login bash and the login shell parses no byte of it. The `integration` rows run it against
`tests/ssh_server.py`, which executes each exec string as `<login shell> -c <string>` inside
`bin/sandbox.sh`, from the user's home, with an sshd-like minimal environment, and serves SFTP over
the same files: the interpreter probe passes for every login shell; a command's stdin is empty and
its end is delivered at once; a timeout returns what was captured and `TIMEOUT_EXIT_CODE`, never an
exception; hostile values arrive literally; nothing a startup file prints reaches a result; a signal
death is reported as one; and `put`/`get` land exactly where named, with `~/` (and `~//`) meaning
the login home and a local name taken literally. A write's content goes by SFTP, never on a
command's stdin, to a private temporary file beside the target that a program moves into place:
byte-exact, atomic, the target's mode kept, a link followed, nothing left behind. No startup file,
the login bash's or the remote login shell's own, moves where a command starts, reads a write's
content or holds the call past the command's end records; the one documented exception, a remote
rc file's background job writing into a result, is pinned with the texts that state it. On a slow
or stalling link the call reads to the end records, however long they take (`ThrottledSSH`). The
server does not kill a process when its channel closes, as OpenSSH does not; it kills what is left
when the test ends.

The `unit` rows drive the channel loop (`_collect`) with a fake channel: an exit status that arrives
before the end of output is waited on, not spun on, and decides nothing; the read ends at both end
records; a command whose records have not come by the deadline is a timeout, naming its status if
that has arrived; and what a command prints after the TERM at its deadline is read. An exec string
over the per-argument limit is refused before connecting.

The `unit` reconnect rows start from a published connection that has gone dead, under a fake clock
that only a calling thread moves: a call that cannot reconnect gives `NOT_STARTED_EXIT_CODE` with
`cannot connect to <host>: <cause>` within its bound (three times the connect bound), never a lost
connection; a refusal gives up at once (every `AuthenticationException` Paramiko raises for one,
and an `AuthFailure` whose every source was refused), and one cut short (the link closed, its own
timeout) is retried; a call past its last start starts and joins no attempt; an attempt that hangs
before it has a transport, or a connection whose building stalls, is abandoned at the bound on its
worker, and its late success is published; calls during a stall share one attempt; an abort and a
publish never cross (a hook at the seam, each way round), an abort spares an attempt another call
has joined since, a call at its deadline takes an outcome that has just come, a connection
published meanwhile stays published, and a shorter connect timeout never lowers the bound. The
declared Paramiko floor is the one the classifier needs.

The recovery rows take the loopback server down (`refuse`) and bring it back (`serve_again`): a
host that returns within the window is used, with the unbroken connection's result; a call that
gave up leaves the server serving, and the next call runs; an attempt stalled in a real
handshake is abandoned at the bound; an authentication the server cuts short, by closing the link or
outlasting the auth timeout, is retried, and the attempt it failed releases its connection; a call
that joins an attempt aborted in its authentication starts a fresh one; and a write whose own
command meets the lost host spends one window, and starts no attempt past its last start. Each
tool reports a reconnect that gave up as nothing run, within one window, and one never changes the
cluster context the server serves.
"""

from __future__ import annotations

import base64
import contextlib
import errno
import json
import os
import re
import socket
import stat
import sys
import threading
import time
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator

import paramiko
import pytest
from fabric import Config, Connection

import argv_echo
from conftest import REAL_POPEN, need_sftp_server, need_shell
from harness import Outcome, call, drive, in_memory, read_resource, shared_server
from rcac_mcp.executor import CONNECTION_LOST_EXIT_CODE, NOT_STARTED_EXIT_CODE, TIMEOUT_EXIT_CODE, CommandResult, Executor, UserPath
from rcac_mcp.executor import launch, ssh
from rcac_mcp.executor.ssh import SSHExecutor
from rcac_mcp.site import SiteContext, SiteFile
from rcac_mcp.tools.shell import run_command
from ssh_server import LOOPBACK, USER, DroppingSSH, LoopbackSSH, ThrottledSSH, _drop, _key, _Server
from test_executors import (LOGIN_MARKER, PROBE, WRITER, held_violations, timed, timeout_violations,
                            writer_violations)
from test_launch import HOSTILE, LEAVES_A_WRITER, SEPARATION_CASES, chatty_home

LOGIN_SHELLS = [pytest.param(shell, id=Path(shell).name) for shell in ('/bin/bash', '/bin/zsh', '/bin/sh', '/bin/tcsh')]


@pytest.fixture
def serve(tmp_path: Path) -> Iterator[Callable[..., LoopbackSSH]]:
    """Start loopback servers for the test (a home per name, under `tmp_path`); stop them after."""
    servers: list[LoopbackSSH] = []

    def start(shell: str, name: str = 'home') -> LoopbackSSH:
        need_shell(shell)
        home = (tmp_path / name).resolve()
        home.mkdir(exist_ok=True)
        servers.append(LoopbackSSH(home, shell, tmp_path))
        return servers[-1]

    try:
        yield start
    finally:
        for server in servers:
            server.close()


def _run(server: LoopbackSSH, *args: Any, **kwargs: Any) -> CommandResult:
    executor = server.executor()
    try:
        return executor.run(*args, **kwargs)
    finally:
        executor.close()


@pytest.mark.integration
@pytest.mark.parametrize('shell', LOGIN_SHELLS)
def test_bash_runs_whatever_the_login_shell(shell: str, serve: Callable[..., LoopbackSSH]) -> None:
    server = serve(shell)
    (Path(server.home) / '.bash_profile').write_text(LOGIN_MARKER)
    result = _run(server, PROBE, timeout=20)
    assert result.exit_code == 0, f'{shell}: the probe failed, so the command did not run under the pinned interpreter: {result!r}'


@pytest.mark.integration
@pytest.mark.parametrize('shell', LOGIN_SHELLS)
def test_stdin_is_empty_and_ends_at_once(shell: str, serve: Callable[..., LoopbackSSH]) -> None:
    server = serve(shell)
    result = _run(server, ['cat'], timeout=8)
    if result.exit_code == TIMEOUT_EXIT_CODE:
        pytest.fail(f'{shell}: cat did not return: the end of stdin (EOF) was not delivered')
    assert (result.stdout, result.exit_code) == ('', 0), f'{shell}: cat read {result!r:.200}: stdin was not empty'
    assert server.stdin_bytes == [[0]], f'{shell}: the channel carried stdin bytes: {server.stdin_bytes!r}'


# A program that never starts: the channel ends with no record, and its own status names the exit.
@pytest.mark.integration
def test_a_profile_that_exits_is_not_started(serve: Callable[..., LoopbackSSH]) -> None:
    server = serve('/bin/bash')
    (Path(server.home) / '.bash_profile').write_text('exit 7\n')
    result = _run(server, 'echo ran', timeout=20)
    note = 'cluster-mcp: the command did not start (exit 7); the server log has the details\n'
    assert (result.stdout, result.stderr, result.exit_code) == ('', note, launch.NOT_STARTED_EXIT_CODE), \
        f"the channel's status was not the one read: {result!r}"


# A command killed by a signal, over ssh too: the end record reports the signal (Paramiko reports
# only a lost status for a signal death), and the launch dies of it.
@pytest.mark.integration
@pytest.mark.parametrize('shell', ['/bin/bash', '/bin/zsh'])
def test_a_signal_death_is_reported(shell: str, serve: Callable[..., LoopbackSSH]) -> None:
    server = serve(shell)
    got = [_run(server, command, timeout=20) for command in ('echo before; kill -s TERM $$', ['/bin/sh', '-c', 'kill -s HUP $$'])]
    assert [(r.stdout, r.stderr, r.exit_code) for r in got] == [('before\n', '', -15), ('', '', -1)], \
        f'{shell}: a signal death was not reported as one: {got!r}'


@pytest.mark.integration
@pytest.mark.parametrize('shell', LOGIN_SHELLS)
def test_timeout_returns_the_captured_output(shell: str, serve: Callable[..., LoopbackSSH]) -> None:
    server = serve(shell)
    start = time.monotonic()
    try:
        result: CommandResult | BaseException = _run(server, 'echo part; echo perr >&2; sleep 30', timeout=1.5)
    except Exception as exc:
        result = exc
    violations = timeout_violations(result, time.monotonic() - start, 1.5 + 3)
    assert violations == [], f'{shell}: ' + '\n'.join(violations)


@pytest.mark.integration
@pytest.mark.parametrize('shell', LOGIN_SHELLS)
def test_values_arrive_literally(shell: str, serve: Callable[..., LoopbackSSH]) -> None:
    result = _run(serve(shell), ['printf', '%s\\0', *HOSTILE], timeout=20)
    want = ''.join(v + '\0' for v in HOSTILE)
    assert (result.stdout, result.stderr, result.exit_code) == (want, '', 0), \
        f'{shell}: a value reaches the command as {result.stdout!r}, not {want!r}; {result.stderr!r}'


# What each separation case returns from a quiet home, whatever the login shell.
QUIET = {
    'argv': ('a b\0c\0', '', 0),
    'exit': ('out\n', 'err\n', 4),
    'stdin': ('line one\nline two\n\0�', '', 0),
    'empty': ('', '', 0),
    'slow': ('slow\n', '', 0),
}


@pytest.mark.integration
@pytest.mark.parametrize('shell', LOGIN_SHELLS)
def test_startup_output_is_separated(shell: str, serve: Callable[..., LoopbackSSH]) -> None:
    quiet, chatty = serve(shell, 'quiet'), serve(shell, 'chatty')
    chatty_home(Path(chatty.home))
    violations = []
    for case, (command, stdin) in SEPARATION_CASES.items():
        if stdin is not None:
            # Content reaches a command only through a write; read it back.
            command = ['cat', '--', UserPath('~/separated')]
            for server in (quiet, chatty):
                executor = server.executor()
                try:
                    executor.write('~/separated', stdin)
                finally:
                    executor.close()
        want = _run(quiet, command, timeout=20)
        got = _run(chatty, command, timeout=20)
        if case in QUIET and (want.stdout, want.stderr, want.exit_code) != QUIET[case]:
            violations.append(f'{case}: the result differs from the quiet home\'s known result: {want!r}')
        if (got.stdout, got.stderr, got.exit_code) != (want.stdout, want.stderr, want.exit_code):
            violations.append(f'{case}: the result differs from the quiet home: {got!r:.300} != {want!r:.300}')
    assert violations == [], f'{shell}: ' + '\n'.join(violations)


# A startup file changes nothing about where a command starts, what it reads or how long it takes:
# neither the login bash's own (.bash_profile) nor the remote login shell's, which runs before the
# bootstrap (zsh's .zshenv).
STARTUP_FILES = {
    'bash-profile': ('/bin/bash', '.bash_profile'),
    'zshenv': ('/bin/zsh', '.zshenv'),
}


@pytest.mark.integration
@pytest.mark.parametrize('startup', list(STARTUP_FILES))
def test_a_startup_cd_does_not_move_the_start(startup: str, serve: Callable[..., LoopbackSSH]) -> None:
    shell, name = STARTUP_FILES[startup]
    server = serve(shell)
    home = Path(server.home)
    (home / 'elsewhere').mkdir()
    (home / 'rel').write_text('at the start\n')
    (home / 'elsewhere' / 'rel').write_text('where the startup file went\n')
    (home / name).write_text('cd "$HOME/elsewhere"\n')
    got = [_run(server, ['pwd'], timeout=20), _run(server, ['cat', UserPath('rel')], timeout=20)]
    want = [(f'{home}\n', '', 0), ('at the start\n', '', 0)]
    assert [(r.stdout, r.stderr, r.exit_code) for r in got] == want, \
        f'ssh-{startup}: a startup cd moved where the command started: {got!r}, not the login home'


# The remote login shell's own rc file, which runs before the bootstrap: zsh's .zshenv, and the
# .bashrc a bash built to read it for a shell sshd started reads (RHEL's, Debian's and macOS's are;
# the loopback server sets SSH_CLIENT, as sshd does). (login shell, rc file)
REMOTE_RCS = {
    'zshenv': ('/bin/zsh', '.zshenv'),
    'bashrc': ('/bin/bash', '.bashrc'),
}

# The remote login shell's rc file runs before the bootstrap, on the channel's own stdin: in the
# foreground, and from a background job, which zsh, unlike bash, sh and ksh, starts on the real stdin.
RC_READS = ('read -r line; printf %s "$line" > "$HOME/rc-read"\n'
            'head -c 1 > "$HOME/rc-took" &\n')


def _settled(path: Path, within: float = 5) -> None:
    deadline = time.monotonic() + within
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)


@pytest.mark.integration
@pytest.mark.parametrize('rc', list(REMOTE_RCS))
def test_a_remote_rc_never_reads_a_writes_content(rc: str, serve: Callable[..., LoopbackSSH], executes: Any) -> None:
    shell, name = REMOTE_RCS[rc]
    quiet, reader = serve(shell, 'quiet'), serve(shell, 'reader')
    home = Path(reader.home)
    (home / name).write_text(RC_READS)
    argv_echo.install(home, 'sbatch')
    violations = []
    # A command's stdin is empty, its end sent at once: the rc file reads nothing and the command runs.
    for case in ('argv', 'exit', 'empty'):
        command, _ = SEPARATION_CASES[case]
        want, got = _run(quiet, command, timeout=20), _run(reader, command, timeout=20)
        if (got.stdout, got.stderr, got.exit_code) != (want.stdout, want.stderr, want.exit_code):
            violations.append(f'{case}: the result differs from the quiet home: {got!r} != {want!r}')
    # A write's content goes by SFTP: the file holds every byte, and the rc file read none of it.
    sent = bytes(range(256)) * 625
    script = '#!/bin/bash\necho hi\n' * 4000
    executor = reader.executor()
    try:
        wrote = _tool(executor, 'write_file', {'path': '~/written', 'content': base64.b64encode(sent).decode(),
                                               'encoding': 'base64'})
        submitted = _tool(executor, 'sbatch', {'script_content': script, 'job_name': 'took'})
    finally:
        executor.close()
    if wrote.is_error or (home / 'written').read_bytes() != sent:
        violations.append(f'write_file: {wrote!r:.200}; the file holds {len((home / "written").read_bytes())} '
                          f'of {len(sent)} bytes, or other bytes')
    jobs = sorted((home / 'jobs').glob('took_*'))
    if submitted.is_error or len(jobs) != 1 or jobs[0].read_bytes() != script.encode():
        violations.append(f'sbatch: {submitted!r:.200}; job scripts {[j.name for j in jobs]!r}')
    _settled(home / 'rc-took')
    for seen in ('rc-read', 'rc-took'):
        if (home / seen).exists() and (home / seen).read_bytes() != b'':
            violations.append(f"the rc file read a write's content: {seen} holds {(home / seen).read_bytes()!r}")
    carried = [n for (n,) in reader.stdin_bytes if n]
    if carried:
        violations.append(f'a channel carried {carried!r} bytes of stdin: content rode a command\'s stdin')
    assert violations == [], '\n'.join(violations)


HOLDERS = {
    # (login shell, startup file, a background job that holds the output open)
    'bash-profile': ('/bin/bash', '.bash_profile', 'sleep 6 &\n'),
    'zshenv': ('/bin/zsh', '.zshenv', 'sleep 6 &!\n'),
}


@pytest.mark.integration
@pytest.mark.parametrize('startup', list(HOLDERS))
def test_a_startup_background_job_does_not_hold_the_call(startup: str, serve: Callable[..., LoopbackSSH]) -> None:
    shell, name, text = HOLDERS[startup]
    server = serve(shell)
    command = 'echo out; echo err >&2; exit 3'
    quiet = timed(lambda: _run(server, command, timeout=30))
    (Path(server.home) / name).write_text(text)
    held = timed(lambda: _run(server, command, timeout=30))
    assert (quiet[0].stdout, quiet[0].exit_code) == ('out\n', 3), quiet
    violations = held_violations(f'ssh-{startup}', quiet, held)
    assert violations == [], '\n'.join(violations)


# The documented exception to the separation: over SSH, a background job the remote login shell's
# own rc file starts, before anything is parked, can write into a result while the command runs
# (issues/startup-background-jobs.md). The code row shows it still holds; the text row that every
# text promising separation states it, so neither can change without the other.
LEAK = '(sleep 1; echo RC-LEAK-OUT; echo RC-LEAK-ERR >&2) &\n'
EXCEPTION = "a background job started by the remote login shell's own rc file"


@pytest.mark.integration
@pytest.mark.parametrize('rc', list(REMOTE_RCS))
def test_a_remote_rc_background_job_can_write_into_a_result(rc: str, serve: Callable[..., LoopbackSSH]) -> None:
    shell, name = REMOTE_RCS[rc]
    server = serve(shell)
    (Path(server.home) / name).write_text(LEAK)
    result = _run(server, 'sleep 2; echo command-output', timeout=20)
    assert (result.stdout, result.stderr, result.exit_code) == ('RC-LEAK-OUT\ncommand-output\n', 'RC-LEAK-ERR\n', 0), \
        (f'the documented exception no longer holds: {result!r}; the texts that state it (AGENTS.md §3, '
         'README.md, the run_command and Executor docstrings) must change with the code')


def _section(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end)]


# What a caller is told about a write's content over ssh (the rows above and below).
CONTENT_RULE = 'by SFTP to a private temporary file'


@pytest.mark.unit
def test_content_texts_state_the_sftp_route() -> None:
    root = Path(__file__).resolve().parent.parent
    texts = {
        'AGENTS.md §2': _section((root / 'AGENTS.md').read_text(), '### 2. ', '### 3. '),
        'README.md': (root / 'README.md').read_text(),
        'the Executor.write docstring': Executor.write.__doc__ or '',
    }
    missing = [name for name, text in texts.items() if CONTENT_RULE not in ' '.join(text.split())]
    assert missing == [], f'a text describing content over ssh does not state its route ({CONTENT_RULE!r}): {missing}'


@pytest.mark.unit
def test_separation_texts_state_the_remote_rc_exception() -> None:
    root = Path(__file__).resolve().parent.parent
    texts = {
        'AGENTS.md §3': _section((root / 'AGENTS.md').read_text(), '### 3. ', '### 4. '),
        'README.md': (root / 'README.md').read_text(),
        'the run_command description': run_command.description or '',
        'the Executor docstring': Executor.__doc__ or '',
    }
    missing = [name for name, text in texts.items() if EXCEPTION not in ' '.join(text.split())]
    assert missing == [], f'a text that promises separation does not state the exception ({EXCEPTION!r}): {missing}'


TRANSFERS = {
    # (operation, remote, local, where the copy must land: ('home' | 'local', relative path))
    'put-tilde': ('put', '~/x', 'local src', ('home', 'x')),
    'put-tilde-double-slash': ('put', '~//x', 'local src', ('home', 'x')),
    'put-into-directory': ('put', '~/dir', 'local src', ('home', 'dir/local src')),
    'get-tilde-double-slash': ('get', '~//there', 'got', ('local', 'got')),
    'get-brace-local-name': ('get', 'there', '{host}.out', ('local', '{host}.out')),
    'get-local-tilde': ('get', '~/there', '~/got', ('server', 'got')),
}


@pytest.mark.integration
@pytest.mark.parametrize('transfer', list(TRANSFERS))
def test_transfers_land_where_named(transfer: str, serve: Callable[..., LoopbackSSH], tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    op, remote, local, (side, lands) = TRANSFERS[transfer]
    server = serve('/bin/bash')
    home = Path(server.home)
    work = (tmp_path / 'work').resolve()
    server_home = (tmp_path / 'server-home').resolve()
    for path in (work, server_home, home / 'dir'):
        path.mkdir()
    monkeypatch.setenv('HOME', str(server_home))
    monkeypatch.chdir(work)
    (work / 'local src').write_bytes(b'from the server\n')
    (home / 'there').write_bytes(b'from the cluster\n')
    want = {'home': home, 'local': work, 'server': server_home}[side] / lands
    executor = server.executor()
    try:
        if op == 'put':
            returned = executor.put(str(work / local), remote)
        else:
            returned = executor.get(remote, local)
        detail = ''
    except Exception as exc:
        returned, detail = None, f'it raised {exc!r}'
    finally:
        executor.close()
    content = b'from the server\n' if op == 'put' else b'from the cluster\n'
    violations = []
    if not (want.is_file() and want.read_bytes() == content):
        violations.append(f'{op}({remote!r}, {local!r}) did not land at {str(want)!r} {detail}')
    elif returned is None or Path(returned).resolve() != want.resolve() or not Path(returned).is_absolute():
        violations.append(f'{op}({remote!r}, {local!r}) returned {returned!r}, not the destination {str(want)!r}')
    assert violations == [], '\n'.join(violations)


# A result is complete exactly when both end records have arrived, however slow the link. On a slow
# link sshd sends the exit status as soon as the command exits, while up to a window of its output
# is still queued behind it: the status decides nothing, and the call reads on to the records.
# Each rate: (bytes a second, bytes read). At the slowest the whole output is queued at the exit; at
# 1 MiB/s a full window (2 MiB) is, two seconds of it; at 4 MiB/s the window drains within a second.
SLOW_LINKS = {
    '256KiBps': (256 * 1024, 640 * 1024),
    '1MiBps': (1024 * 1024, 3 * 1024 * 1024),
    '4MiBps': (4 * 1024 * 1024, 6 * 1024 * 1024),
}

# Links that stall, and links that deliver whole 32 KiB packets slowly: (rate in bytes a second,
# bytes read, packet size, a stall right after the exit status, a stall once so many bytes have gone).
STALLING_LINKS = {
    'stall-1.6s-after-exit': (512 * 1024, 1024 * 1024, 8192, 1.6, None),
    'stall-1.2s-after-exit': (512 * 1024, 1024 * 1024, 8192, 1.2, None),
    'stall-5s-mid-result': (512 * 1024, 1024 * 1024, 8192, 0.0, (256 * 1024, 5.0)),
    'packets-6000Bps': (6000, 48 * 1024, 32 * 1024, 1.6, None),
    'packets-24000Bps': (24000, 256 * 1024, 32 * 1024, 1.6, None),
}


def _numbered(size: int) -> bytes:
    """`size` bytes of numbered lines, so a cut anywhere shows."""
    lines = b''.join(b'%011d\n' % i for i in range(size // 12 + 1))
    return lines[:size]


@pytest.fixture
def slow(tmp_path: Path) -> Iterator[Callable[..., ThrottledSSH]]:
    """Start slow-link servers for the test (a home per name, under `tmp_path`); stop them after."""
    servers: list[ThrottledSSH] = []

    def start(shell: str, rate: int, name: str = 'home', **link: Any) -> ThrottledSSH:
        need_shell(shell)
        home = (tmp_path / name).resolve()
        home.mkdir(exist_ok=True)
        servers.append(ThrottledSSH(home, shell, tmp_path, rate, **link))
        return servers[-1]

    try:
        yield start
    finally:
        for server in servers:
            server.close()


def _tool(executor: Executor, tool: str, args: dict[str, Any]) -> Outcome:
    async def scenario() -> Outcome:
        async with in_memory(shared_server(executor)) as client:
            return await call(client, tool, args)
    return drive(scenario(), timeout=120)


@pytest.mark.integration
@pytest.mark.parametrize('link', list(SLOW_LINKS))
def test_a_slow_link_returns_the_whole_file(link: str, slow: Callable[..., ThrottledSSH], executes: Any) -> None:
    rate, size = SLOW_LINKS[link]
    server = slow('/bin/bash', rate)
    data = _numbered(size)
    (Path(server.home) / 'big.txt').write_bytes(data)
    executor = server.executor()
    try:
        outcome = _tool(executor, 'read_file', {'path': '~/big.txt'})
    finally:
        executor.close()
    got = outcome.text.encode()
    assert (outcome.is_error, len(got), got == data) == (False, size, True), \
        (f'{link}: read_file returned {len(got)} of {size} bytes (error: {outcome.is_error}): the result was cut '
         f'before its end records, while the output was still arriving; it ends {got[-40:]!r}')


@pytest.mark.integration
@pytest.mark.parametrize('link', list(STALLING_LINKS))
def test_a_stalling_link_returns_the_whole_file(link: str, slow: Callable[..., ThrottledSSH], executes: Any) -> None:
    rate, size, piece, after_exit, stall_at = STALLING_LINKS[link]
    server = slow('/bin/bash', rate, piece=piece, stall_after_exit=after_exit, stall_at=stall_at)
    data = _numbered(size)
    (Path(server.home) / 'big.txt').write_bytes(data)
    executor = server.executor()
    try:
        outcome = _tool(executor, 'read_file', {'path': '~/big.txt'})
    finally:
        executor.close()
    got = outcome.text.encode()
    assert (outcome.is_error, len(got), got == data) == (False, size, True), \
        (f'{link}: read_file returned {len(got)} of {size} bytes (error: {outcome.is_error}): the result was cut '
         f'before its end records, on a link that stalled or delivered whole packets slowly; it ends {got[-40:]!r}')


# The double-submit case: a chatty remote rc file (40 KB) ahead of the program on a slow link of
# whole 32 KiB packets that stalls after the exit status. The sentinel arrives seconds after sshd
# sent the exit status; a submission that ran must read as submitted, never as "did not start".
@pytest.mark.integration
def test_a_job_that_ran_is_never_reported_as_not_started(slow: Callable[..., ThrottledSSH], executes: Any) -> None:
    server = slow('/bin/bash', 6000, piece=32 * 1024, stall_after_exit=1.6)
    home = Path(server.home)
    (home / '.bashrc').write_text("head -c 40000 /dev/zero | tr '\\0' z\n")
    argv_echo.install(home, 'sbatch')
    (home / 'job.sh').write_text('#!/bin/bash\necho hi\n')
    executor = server.executor()
    try:
        outcome = _tool(executor, 'sbatch', {'script_path': '~/job.sh'})
    finally:
        executor.close()
    calls = argv_echo.calls(home)
    assert (outcome.is_error, outcome.text, len(calls)) == (False, argv_echo.JOB_ID, 1), \
        (f'a submission that ran read as {outcome!r:.300}; sbatch was called {len(calls)} times: the result was cut '
         'before its end records')


# The timeout bounds a call whose records do not come: the command exited at once (its status is
# in), but its output, and its end records behind it, are still queued on a slow link at the
# deadline. The call is a timeout, with the output read so far and a note naming the status.
@pytest.mark.integration
def test_a_timeout_before_the_records_names_the_status(slow: Callable[..., ThrottledSSH]) -> None:
    server = slow('/bin/bash', 64 * 1024)
    data = _numbered(1024 * 1024)
    (Path(server.home) / 'big.txt').write_bytes(data)
    result = _run(server, ['cat', '--', UserPath('~/big.txt')], timeout=2)
    got = result.stdout.encode()
    assert result.exit_code == TIMEOUT_EXIT_CODE, f'the call ended {result.exit_code}, not as a timeout'
    assert 0 < len(got) < len(data) and data.startswith(got), f'the output read so far was lost: {len(got)} bytes'
    assert result.stderr.endswith(launch.LATE_NOTE.format(code=0)), \
        f'the timeout does not name the status that had arrived: stderr {result.stderr[-200:]!r}'


@pytest.mark.integration
def test_a_slow_link_returns_both_streams_whole(slow: Callable[..., ThrottledSSH]) -> None:
    rate, size = SLOW_LINKS['256KiBps']
    server = slow('/bin/bash', rate)
    data = _numbered(size)
    (Path(server.home) / 'big.txt').write_bytes(data)
    result = _run(server, 'cat big.txt; echo DONE >&2', timeout=60)
    got = result.stdout.encode()
    assert (len(got), got == data, result.stderr, result.exit_code) == (size, True, 'DONE\n', 0), \
        (f'the result was cut before its end records, while the output was still arriving: stdout {len(got)} of {size} bytes, '
         f'stderr {result.stderr!r}, exit code {result.exit_code}')


# A chatty remote rc file (1 MiB, as the suite's chatty home prints) ahead of the program on a slow
# link: the sentinel arrives seconds after sshd sent the exit status of a short command.
CHATTY_RC = "head -c 1048576 /dev/zero | tr '\\0' z\n"


@pytest.mark.integration
@pytest.mark.parametrize('rc', list(REMOTE_RCS))
def test_a_late_sentinel_still_counts_as_started(rc: str, slow: Callable[..., ThrottledSSH]) -> None:
    shell, name = REMOTE_RCS[rc]
    server = slow(shell, 512 * 1024)
    home = Path(server.home)
    (home / name).write_text(CHATTY_RC)
    ran = _run(server, ['touch', '--', UserPath('~/ran')], timeout=60)
    sent = b'line one\nline two\n\0\xff'
    executor = server.executor()
    try:
        wrote = executor.write('~/written', sent)
    finally:
        executor.close()
    violations = []
    if (ran.stdout, ran.stderr, ran.exit_code) != ('', '', 0) or not (home / 'ran').exists():
        violations.append(f'a command that ran was reported as {ran!r} (~/ran exists: {(home / "ran").exists()})')
    if (wrote.stdout, wrote.stderr, wrote.exit_code) != ('', '', 0) or (home / 'written').read_bytes() != sent:
        violations.append(f'a late start lost the write: {wrote!r}')
    assert violations == [], ('a late sentinel was not counted as started (the result was cut before its end records): '
                              + '\n'.join(violations))


@pytest.mark.integration
@pytest.mark.parametrize('shell', ['/bin/bash', '/bin/zsh'])
def test_a_background_writer_does_not_hold_the_call(shell: str, serve: Callable[..., LoopbackSSH]) -> None:
    server = serve(shell)
    result, elapsed = timed(lambda: _run(server, WRITER, timeout=10))
    violations = writer_violations('ssh', result, elapsed)
    later, later_s = timed(lambda: _run(server, LEAVES_A_WRITER, timeout=20))
    if (later.stdout, later.stderr, later.exit_code) != ('now\n', '', 0) or later_s > 2:
        violations.append(f'ssh: what a background job printed after the end reached the result, or held the call '
                          f'{later_s:.1f} s: {later!r}')
    assert violations == [], '\n'.join(violations)


# Writes over ssh: the content goes by SFTP into a private directory beside the target, and a
# program moves it into place.

def _write(server: LoopbackSSH, *args: Any, **kwargs: Any) -> CommandResult:
    executor = server.executor()
    try:
        return executor.write(*args, **kwargs)
    finally:
        executor.close()


def _staging_left(*directories: Path) -> list[str]:
    return [str(p) for d in directories for p in d.iterdir() if p.name.startswith(ssh.STAGE_PREFIX)]


@pytest.mark.integration
def test_an_ssh_write_replaces_the_file_whole_and_keeps_its_mode(serve: Callable[..., LoopbackSSH]) -> None:
    server = serve('/bin/bash')
    home = Path(server.home)
    target = home / 'kept.sh'
    target.write_bytes(b'old content\n')
    target.chmod(0o750)
    before = target.stat().st_ino
    with open(target, 'rb') as reader:
        result = _write(server, '~/kept.sh', b'new content, no final newline')
        old_view = reader.read()
    violations = []
    if (result.stdout, result.stderr, result.exit_code) != ('', '', 0):
        violations.append(f'the write returned {result!r}')
    if target.read_bytes() != b'new content, no final newline':
        violations.append(f'the file holds {target.read_bytes()!r}')
    if target.stat().st_ino == before or old_view != b'old content\n':
        violations.append('the file was rewritten in place, not replaced whole: a reader saw '
                          f'{old_view!r} through the old file')
    if stat.S_IMODE(target.stat().st_mode) != 0o750:
        violations.append(f'the file lost its mode: {stat.S_IMODE(target.stat().st_mode):o}, not 750')
    umask = int(_run(server, 'umask', timeout=20).stdout, 8)
    fresh = _write(server, '~/fresh', b'x')
    if fresh.exit_code != 0 or stat.S_IMODE((home / 'fresh').stat().st_mode) != 0o666 & ~umask:
        violations.append(f'a new file has mode {stat.S_IMODE((home / "fresh").stat().st_mode):o}, not what '
                          f'`cat >` gives under umask {umask:o}: {fresh!r}')
    if _staging_left(home):
        violations.append(f'a write left its staging behind: {_staging_left(home)!r}')
    assert violations == [], '\n'.join(violations)


@pytest.mark.integration
def test_an_ssh_write_stages_its_content_privately(serve: Callable[..., LoopbackSSH],
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    server = serve('/bin/bash')
    home = Path(server.home)
    (home / 'sub').mkdir()
    seen: list[tuple[str, int, int, str]] = []
    upload = ssh._upload

    def watched(sftp: Any, staged: str, data: bytes) -> None:
        upload(sftp, staged, data)
        path = home / staged
        seen.append((str(path.parent.parent), stat.S_IMODE(path.parent.stat().st_mode), stat.S_IMODE(path.stat().st_mode),
                     path.parent.name))
    monkeypatch.setattr(ssh, '_upload', watched)
    first, second = _write(server, '~/sub/a', b'one'), _write(server, '~/sub/a', b'two')
    assert (first.exit_code, second.exit_code, (home / 'sub' / 'a').read_bytes()) == (0, 0, b'two'), (first, second)
    # Each write stages its content and its checksum, both private, in one directory of its own.
    assert [(where, d, f) for where, d, f, _ in seen] == [(str(home / 'sub'), 0o700, 0o600)] * 4, \
        f'the content was not staged privately beside the target: {seen!r}'
    assert len({name for *_, name in seen}) == 2, f'two writes shared a staging name: {seen!r}'


@pytest.mark.integration
def test_an_ssh_write_follows_a_link(serve: Callable[..., LoopbackSSH]) -> None:
    server = serve('/bin/bash')
    home = Path(server.home)
    (home / 'real').mkdir()
    (home / 'real' / 'file').write_bytes(b'old\n')
    (home / 'link').symlink_to(home / 'real' / 'file')
    result = _write(server, '~/link', b'through the link\n')
    assert result.exit_code == 0, result
    assert (home / 'link').is_symlink() and (home / 'real' / 'file').read_bytes() == b'through the link\n', \
        'the write replaced the link instead of writing the file it names'
    assert _staging_left(home, home / 'real') == [], 'a write left its staging behind'


@pytest.mark.integration
def test_an_ssh_write_into_a_closed_directory_writes_through(serve: Callable[..., LoopbackSSH]) -> None:
    server = serve('/bin/bash')
    home = Path(server.home)
    closed = home / 'closed'
    closed.mkdir()
    (closed / 'file').write_bytes(b'old\n')
    (closed / 'file').chmod(0o640)
    closed.chmod(0o555)
    try:
        result = _write(server, '~/closed/file', b'new\n')
        appended = _write(server, '~/closed/file', b'more\n', append=True)
        missing = None
        try:
            missing = _write(server, '~/closed/other', b'x')
        except OSError as exc:
            missing = exc
    finally:
        closed.chmod(0o755)
    assert (result.exit_code, appended.exit_code) == (0, 0), (result, appended)
    assert (closed / 'file').read_bytes() == b'new\nmore\n'
    assert stat.S_IMODE((closed / 'file').stat().st_mode) == 0o640
    assert isinstance(missing, PermissionError) and not (closed / 'other').exists(), missing
    assert _staging_left(home, closed) == [], 'a write left its staging behind'


@pytest.mark.integration
def test_a_failed_ssh_write_leaves_nothing_behind(serve: Callable[..., LoopbackSSH]) -> None:
    # A transfer that fails is pinned against a real one: OpenSSH's sftp-server on a full volume, and
    # injected faults (`test_a_write_that_runs_out_of_room_keeps_the_file`,
    # `test_a_staged_file_that_is_not_what_was_sent_is_never_placed`).
    server = serve('/bin/bash')
    home = Path(server.home)
    (home / 'a dir').mkdir()
    (home / 'file').write_bytes(b'unchanged\n')
    violations = []
    # The target is a directory: refused before anything is staged.
    try:
        _write(server, '~/a dir', b'x')
        violations.append('a write to a directory was not refused')
    except IsADirectoryError:
        pass
    # The placing program does not start (a profile that exits).
    (home / '.bash_profile').write_text('exit 0\n')
    result = _write(server, '~/file', b'replacement')
    if result.exit_code != launch.NOT_STARTED_EXIT_CODE:
        violations.append(f'a write whose program never started returned {result!r}')
    if (home / 'file').read_bytes() != b'unchanged\n':
        violations.append(f'a failed write changed the file: {(home / "file").read_bytes()!r}')
    if _staging_left(home, home / 'a dir'):
        violations.append(f'a failed write left its staging behind: {_staging_left(home, home / "a dir")!r}')
    assert violations == [], '\n'.join(violations)


# ---------------------------------------------------------------------------------------------
# A transfer that fails: on a full filesystem, at a quota, short or changed on its way to disk.

# A job script longer than the room left: 32 KiB and a little, as a write of it reaches the disk.
SCRIPT_BYTES = 36_027

# What the target held before: a write that fails must leave exactly this.
KEPT = b'the file before the write\n' * 16


def _host(*argv: str) -> None:
    """Run a host tool the fixture needs (not a command under test), and check it succeeded."""
    proc = REAL_POPEN(list(argv), stdout=-1, stderr=-1)
    out, err = proc.communicate(timeout=120)
    assert proc.returncode == 0, f'{argv[:2]!r} failed: {err.decode(errors="replace")[-400:]}'


@contextlib.contextmanager
def full_volume(where: Path, free: int) -> Iterator[Path]:
    """A 4 MB HFS+ volume attached at `where` (macOS), filled until `free` bytes are left; detached
    and its image removed afterwards."""
    image = where.parent / f'{where.name}.dmg'
    _host('hdiutil', 'create', '-size', '4m', '-fs', 'HFS+', '-volname', 'cluster-mcp-full', str(image))
    where.mkdir()
    _host('hdiutil', 'attach', '-nobrowse', '-noautoopen', '-mountpoint', str(where), str(image))
    try:
        room = os.statvfs(where)
        with open(where / 'filler', 'wb') as filler:
            filler.write(b'\0' * (room.f_bavail * room.f_frsize - free))
        room = os.statvfs(where)
        assert room.f_bavail * room.f_frsize == free, f'the volume has {room.f_bavail * room.f_frsize} bytes free'
        yield where
    finally:
        _host('hdiutil', 'detach', '-force', str(where))
        image.unlink()


ROOM = {
    # (the failure, the room before it, in bytes)
    '8k-free': (errno.ENOSPC, 8 * 1024),
    '32k-free': (errno.ENOSPC, 32 * 1024),
    'edquot': (errno.EDQUOT, 32 * 1024),
}


@pytest.mark.integration
@pytest.mark.parametrize('room', list(ROOM))
def test_a_write_that_runs_out_of_room_keeps_the_file(room: str, tmp_path: Path, executes: Any) -> None:
    """A full filesystem or a spent quota fails the write with its reason, and touches nothing.

    On macOS a full filesystem is real: a 4 MB HFS+ image, attached by the test and filled to 8 KiB
    or 32 KiB free, served by OpenSSH's own sftp-server, which reports only `Failure`; the remote
    filesystem then names the cause. The Linux runner cannot attach a filesystem without root, so
    there the in-process subsystem fails the write at that many bytes with ENOSPC instead, as a
    full filesystem does. EDQUOT is injected that way everywhere.
    """
    failure, free = ROOM[room]
    home = (tmp_path / 'home').resolve()
    home.mkdir()
    real = failure == errno.ENOSPC and sys.platform == 'darwin'
    with contextlib.ExitStack() as stack:
        volume = stack.enter_context(full_volume(home / 'vol', free)) if real else home / 'vol'
        volume.mkdir(exist_ok=True)
        (volume / 'jobs').mkdir()
        (home / 'jobs').symlink_to(volume / 'jobs')
        (volume / 'job.sh').write_bytes(KEPT)
        argv_echo.install(home, 'sbatch')
        server = stack.enter_context(LoopbackSSH(home, '/bin/bash', tmp_path,
                                                 sftp_server=need_sftp_server() if real else None))
        if not real:
            server.write_limit = (free, failure)
        executor = server.executor()
        stack.callback(executor.close)
        violations = []
        try:
            result = executor.write('~/vol/job.sh', b'#' * SCRIPT_BYTES)
            violations.append(f'a write that ran out of room returned {result!r}')
        except OSError as exc:
            message = str(exc)
            if f'the transfer of {SCRIPT_BYTES} bytes' not in message or 'the file is unchanged' not in message:
                violations.append(f'the failure does not say what failed: {message!r}')
            # The remote filesystem names a real cause; an injected one reaches only the SFTP server's word.
            cause = 'No space left on device' if real else 'Failure'
            if cause not in message:
                violations.append(f'the failure does not name its cause ({cause!r}): {message!r}')
        held = (volume / 'job.sh').read_bytes()
        if held != KEPT:
            violations.append(f'a write that ran out of room changed the file: it holds {len(held)} bytes, '
                              f'not the {len(KEPT)} it held')
        submitted = _tool(executor, 'sbatch', {'script_content': '#' * SCRIPT_BYTES, 'job_name': 'full'})
        if not submitted.is_error or 'Failed to write job script' not in submitted.text:
            violations.append(f'sbatch of a job script that did not fit: {submitted!r:.300}')
        if argv_echo.calls(home):
            violations.append(f'a job script that did not fit was submitted: {argv_echo.calls(home)!r:.300}')
        if list((volume / 'jobs').iterdir()):
            violations.append(f'a job script that did not fit was left: {sorted(p.name for p in (volume / "jobs").iterdir())}')
        if _staging_left(home, volume, volume / 'jobs'):
            violations.append(f'a write left its staging behind: {_staging_left(home, volume, volume / "jobs")!r}')
    assert violations == [], f'{room}:\n' + '\n'.join(violations)


FAULTS = {
    # (how the staged file goes wrong, what the failure says)
    'short': ('short', f'32768 of {SCRIPT_BYTES} bytes arrived'),
    'changed': ('flip', 'is not what was sent'),
    'close-fails': ('close', 'failed: Failure;'),
}


@pytest.mark.integration
@pytest.mark.parametrize('fault', list(FAULTS))
def test_a_staged_file_that_is_not_what_was_sent_is_never_placed(fault: str, serve: Callable[..., LoopbackSSH]) -> None:
    """A staged file that fell short with no error reported, or whose bytes changed on the way to
    disk, is caught by its size or its checksum before the move, and a close the server fails is a
    failed transfer: the target keeps its bytes."""
    how, says = FAULTS[fault]
    server = serve('/bin/bash')
    home = Path(server.home)
    (home / 'job.sh').write_bytes(KEPT)
    if how == 'short':
        server.write_limit = (32 * 1024, None)
    elif how == 'flip':
        server.write_flip = True
    else:
        server.close_failure = True
    text = ''
    try:
        result = _write(server, '~/job.sh', b'#' * SCRIPT_BYTES)
        text = result.stderr if result.exit_code != 0 else ''
    except OSError as exc:
        text = str(exc)
    assert says in text, f'{fault}: the write was not refused for its staged file: {text!r}'
    assert (home / 'job.sh').read_bytes() == KEPT, f'{fault}: the target changed'
    assert _staging_left(home) == [], f'{fault}: a write left its staging behind'


@pytest.mark.unit
def test_cksum_is_posix_cksum() -> None:
    # Values from POSIX cksum (GNU coreutils and BSD agree): the empty input, and one known string.
    assert ssh.cksum(b'') == '4294967295 0'
    assert ssh.cksum(b'abc') == '1219131554 3'
    assert ssh.cksum(b'123456789') == '930766865 9'


@pytest.mark.integration
def test_cksum_matches_the_hosts_cksum(serve: Callable[..., LoopbackSSH]) -> None:
    server = serve('/bin/bash')
    home = Path(server.home)
    for size in (1, 255, 256, 65_537, 1_048_576):
        data = os.urandom(size)
        (home / 'sample').write_bytes(data)
        got = _run(server, 'cksum <sample', timeout=20)
        assert got.stdout.strip() == ssh.cksum(data), f'{size} bytes: the host says {got!r}, not {ssh.cksum(data)}'


# ---------------------------------------------------------------------------------------------
# A lost connection: the command may have run, so it is never reported as not started.

LOST_NOTE = launch.LOST_NOTE.decode()


@pytest.mark.integration
@pytest.mark.parametrize('when', ['after-the-command', 'before-the-reply'])
def test_a_lost_connection_is_never_did_not_start(when: str, tmp_path: Path, executes: Any) -> None:
    home = (tmp_path / 'home').resolve()
    home.mkdir()
    argv_echo.install(home, 'sbatch')
    (home / 'job.sh').write_text('#!/bin/bash\necho hi\n')
    with DroppingSSH(home, '/bin/bash', tmp_path, when, drops=2) as server:
        executor = server.executor()
        violations = []
        try:
            try:
                result = executor.run(['touch', '--', 'ran'], timeout=30)
            except Exception as exc:
                violations.append(f'a command whose connection was lost raised {exc!r} instead of returning')
                result = CommandResult('', '', 0, '')
            submitted = _tool(executor, 'sbatch', {'script_path': '~/job.sh'})
        finally:
            executor.close()
    if not (home / 'ran').exists():
        violations.append('the command did not run, so the drop proves nothing')
    if (result.stdout, result.stderr, result.exit_code) != ('', LOST_NOTE, CONNECTION_LOST_EXIT_CODE):
        violations.append(f'a command whose connection was lost after it ran returned {result!r}, not '
                          f'{CONNECTION_LOST_EXIT_CODE} with {LOST_NOTE!r}')
    if result.exit_code == NOT_STARTED_EXIT_CODE or 'did not start' in result.stderr:
        violations.append('a command that ran was reported as not started')
    if len(argv_echo.calls(home)) != 1:
        violations.append(f'sbatch ran {len(argv_echo.calls(home))} times, not once')
    if not submitted.is_error or 'may have been submitted' not in submitted.text or 'Failed' in submitted.text:
        violations.append(f'a submission whose connection was lost read as {submitted!r:.300}: it must say the job '
                          'may have been submitted, never that it failed')
    assert violations == [], f'{when}:\n' + '\n'.join(violations)


# How long the client's transport is held, once it has woken the channels of a lost connection,
# before it marks itself inactive (Paramiko does the two in that order).
UNWIND = 0.05


@pytest.mark.integration
def test_a_lost_link_at_exec_is_lost_while_the_transport_unwinds(tmp_path: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    # The wait on the exec request wakes while the transport still reads as active: a lost link
    # there is still lost, never a refusal raised.
    unlink = paramiko.Transport._unlink_channel

    def held(transport: paramiko.Transport, chanid: int) -> None:
        if not transport.server_mode:
            time.sleep(UNWIND)
        unlink(transport, chanid)

    monkeypatch.setattr(paramiko.Transport, '_unlink_channel', held)
    home = (tmp_path / 'home').resolve()
    home.mkdir()
    with DroppingSSH(home, '/bin/bash', tmp_path, 'before-the-reply') as server:
        executor = server.executor()
        try:
            result = executor.run(['touch', '--', 'ran'], timeout=30)
        except Exception as exc:
            pytest.fail(f'a command whose connection was lost before the reply raised {exc!r} instead of returning')
        finally:
            executor.close()
    assert (home / 'ran').exists(), 'the command did not run, so the drop proves nothing'
    assert (result.stdout, result.stderr, result.exit_code) == ('', LOST_NOTE, CONNECTION_LOST_EXIT_CODE), result


# ---------------------------------------------------------------------------------------------
# A reconnect: a call that finds the connection lost reconnects within its bound, or runs nothing
# and reports `cannot connect to <host>: <cause>` as a command that was not run, never as a lost
# connection. Every row starts from a published connection that has gone dead, and reads time
# through a fake clock that only a calling thread moves, so a 45 s bound costs no real wait.

RECONNECT_HOST = 'alias.example'
RECONNECT_BOUND = ssh.RECONNECT_FACTOR * ssh.CONNECT_TIMEOUT
# The real time a row's fake clock also counts, at most, past the bound it checks.
RECONNECT_SLACK = 0.5
# Real seconds a row waits for a worker thread to park or end before it fails, and that a parked
# worker waits to be released.
SETTLE_LIMIT = 10.0
PARK_LIMIT = 60.0
WORKER = 'cluster-mcp-reconnect'
_REAL_MONOTONIC = time.monotonic
_REAL_SLEEP = time.sleep


class Runaway(BaseException):
    """The fake clock ran past its ceiling: the call is still reconnecting.

    A `BaseException`, so no `except Exception` in the executor can swallow it; it is raised only on
    a calling thread, never on a worker.
    """


class FakeClock:
    """Real time plus an offset, read by `ssh` as its `time`; `wait` stands in for `ssh._await`.

    Only a calling thread moves the clock: a backoff `sleep` advances it, and so does a wait on an
    attempt. Before and after each advance the wait lets every reconnect worker either end or park
    (`park`), so an attempt's outcome lands at a fake time that does not depend on scheduling. A
    parked worker wakes when fake time reaches its due time, or at `release`.
    Short sleeps (the channel loop's) pass through to the real sleep. Past `ceiling` fake seconds
    from `rebase`, the clock raises `Runaway` on the calling thread.
    """

    def __init__(self, ceiling: float) -> None:
        self.offset = 0.0
        self.ceiling = ceiling
        self.start = _REAL_MONOTONIC()
        self.sleeps: list[float] = []
        self.lock = threading.Lock()
        self.gates: list[tuple[float | None, threading.Event, int]] = []
        self.parked: set[int] = set()
        self.before = set(threading.enumerate())

    def monotonic(self) -> float:
        return _REAL_MONOTONIC() + self.offset

    def elapsed(self) -> float:
        return self.monotonic() - self.start

    def rebase(self, ceiling: float | None = None) -> None:
        self.start = self.monotonic()
        if ceiling is not None:
            self.ceiling = ceiling

    def _open(self, due: Callable[[float | None], bool]) -> None:
        with self.lock:
            opened = [gate for gate in self.gates if due(gate[0])]
            self.gates = [gate for gate in self.gates if not due(gate[0])]
            for _, event, ident in opened:
                self.parked.discard(ident)
                event.set()

    def advance(self, seconds: float) -> None:
        with self.lock:
            self.offset += max(0.0, seconds)
        now = self.monotonic()
        self._open(lambda at: at is not None and at <= now)
        if self.elapsed() > self.ceiling:
            raise Runaway(f'still reconnecting {self.elapsed():.0f} s after the call started')

    def sleep(self, seconds: float) -> None:
        if seconds <= ssh.SLEEP_WAIT:
            _REAL_SLEEP(seconds)
            return
        self.sleeps.append(seconds)
        self.advance(seconds)

    def park(self, at: float | None) -> None:
        """On a worker: block until fake time reaches `at` (since `rebase`), or until `release`."""
        event = threading.Event()
        ident = threading.get_ident()
        with self.lock:
            self.gates.append((None if at is None else self.start + at, event, ident))
            self.parked.add(ident)
        if not event.wait(PARK_LIMIT):
            raise RuntimeError('a parked attempt was never released')

    def release(self) -> None:
        """Wake every parked worker, due or not."""
        self._open(lambda at: True)

    def workers(self) -> list[threading.Thread]:
        return [t for t in threading.enumerate() if t.name == WORKER and t not in self.before and t.is_alive()]

    def settle(self, event: threading.Event) -> None:
        limit = _REAL_MONOTONIC() + SETTLE_LIMIT
        while not event.is_set():
            with self.lock:
                parked = set(self.parked)
            if all(t.ident in parked for t in self.workers()):
                return
            if _REAL_MONOTONIC() > limit:
                raise AssertionError('a reconnect worker neither ended nor parked')
            _REAL_SLEEP(0.0005)

    def wait(self, event: threading.Event, seconds: float) -> bool:
        self.settle(event)
        if event.is_set():
            return True
        self.advance(seconds)
        self.settle(event)
        return event.is_set()


class FakeTransport:
    def __init__(self) -> None:
        self.active = True

    def is_active(self) -> bool:
        return self.active

    def close(self) -> None:
        self.active = False


class FakeClient:
    """A Paramiko client's stand-in: no transport until the connection opens."""

    def __init__(self) -> None:
        self.transport: FakeTransport | None = None
        self.closed = False

    def get_transport(self) -> FakeTransport | None:
        return self.transport

    def close(self) -> None:
        self.closed = True
        if self.transport is not None:
            self.transport.close()


# A connect step: 'ok' opens at once; 'hang' blocks, as name resolution can, until the row releases
# it, then opens; 'shake' makes the client's transport and then blocks, as an authentication can,
# until the row releases it, then opens on that transport unless it was closed meanwhile; ('at', t)
# opens at fake time t; ('build', make) raises make() as the connection is built; (spent, make)
# spends `spent` fake seconds, then raises make().
Step = Any


class Scripted:
    """Stands in for Fabric's `Connection`: each one built takes the next step of the rig's script,
    the last step repeating."""

    rig: ReconnectRig

    def __init__(self, host: str, **kwargs: Any) -> None:
        rig = self.rig
        with rig.lock:
            self.step: Step = rig.script.pop(0) if len(rig.script) > 1 else rig.script[0]
            rig.made.append(self)
        self.host = host
        self.connect_timeout = kwargs.get('connect_timeout') or kwargs['config'].timeouts.connect
        self.connect_kwargs = dict(kwargs.get('connect_kwargs') or {})
        self.client = FakeClient()
        self.transport: FakeTransport | None = None
        self.gateway = None
        self.started: float | None = None
        if isinstance(self.step, tuple) and self.step[0] == 'build':
            raise self.step[1]()

    @property
    def is_connected(self) -> bool:
        return self.transport.active if self.transport else False

    def open(self) -> None:
        clock = self.rig.clock
        self.started = clock.elapsed()
        if self.step == 'hang':
            clock.park(None)
        elif self.step == 'shake':
            self.client.transport = FakeTransport()
            clock.park(None)
            if not self.client.transport.active:
                raise paramiko.AuthenticationException(ssh.AUTH_CLOSED)
        elif isinstance(self.step, tuple) and self.step[0] == 'at':
            clock.park(self.step[1])
        elif self.step != 'ok':
            spent, make = self.step
            if spent:
                clock.park(self.started + spent)
            raise make()
        if self.client.transport is None:
            self.client.transport = FakeTransport()
        self.transport = self.client.transport

    def close(self) -> None:
        self.client.close()


class OpenFree(Connection):
    """Fabric's real `Connection`, built as the executor builds it, whose `open()` reaches no host."""

    def open(self) -> None:
        self.transport = FakeTransport()  # type: ignore[assignment]


class ReconnectRig:
    """The fake clock, the scripted connections and the executor of one reconnect row."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch = monkeypatch
        self.clock = FakeClock(2 * RECONNECT_BOUND)
        self.lock = threading.Lock()
        self.script: list[Step] = ['ok']
        self.made: list[Any] = []
        # (the thread, fake seconds since `rebase`) of every connection a reconnect built
        self.built: list[tuple[str, float]] = []

    def executor(self, script: list[Step] | None = None, connection: type = Scripted, **kwargs: Any) -> SSHExecutor:
        """An executor whose published connection has gone dead, with the fake clock installed."""
        if script is not None:
            self.script = list(script)
            self.monkeypatch.setattr(ssh, 'Connection', type('Scripted', (Scripted,), {'rig': self}))
        else:
            self.monkeypatch.setattr(ssh, 'Connection', connection)
        executor = SSHExecutor(RECONNECT_HOST, **kwargs)
        assert ssh._live(executor._conn) is not None, 'the executor did not start connected'
        executor._conn.transport.active = False
        new = SSHExecutor._new

        def counted(this: SSHExecutor) -> Any:
            self.built.append((threading.current_thread().name, self.clock.elapsed()))
            return new(this)

        self.monkeypatch.setattr(SSHExecutor, '_new', counted)
        self.monkeypatch.setattr(ssh, 'time', self.clock)
        self.monkeypatch.setattr(ssh, '_await', self.clock.wait)
        self.clock.rebase(2 * executor._window)
        return executor

    @property
    def attempts(self) -> list[Any]:
        return self.made[1:]

    def finish(self) -> None:
        """Release every parked attempt and wait for every worker to end."""
        self.clock.release()
        for worker in self.clock.workers():
            worker.join(5)


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch) -> Iterator[ReconnectRig]:
    made = ReconnectRig(monkeypatch)
    try:
        yield made
    finally:
        made.finish()


def not_run_violations(result: CommandResult, cause: str, elapsed: float, bound: float, host: str = RECONNECT_HOST,
                       slack: float = RECONNECT_SLACK) -> list[str]:
    """Every way `result` is not a reconnect that gave up within `bound` (and `slack`), naming `host`
    and `cause`."""
    violations = []
    if result.exit_code == CONNECTION_LOST_EXIT_CODE:
        violations.append(f'a failed reconnect read as a lost connection: {result!r}')
    elif result.exit_code != NOT_STARTED_EXIT_CODE:
        violations.append(f'a failed reconnect returned {result.exit_code}, not {NOT_STARTED_EXIT_CODE}: {result!r}')
    head = f'cluster-mcp: cannot connect to {host}: {cause}'
    if not (result.stderr.startswith(head) and result.stderr.endswith('; the command was not run\n')):
        violations.append(f'a failed reconnect did not say {head!r} and that the command was not run: '
                          f'{result.stderr!r}')
    if result.stdout:
        violations.append(f'a command that was not run has output: {result.stdout!r}')
    if elapsed > bound + slack:
        violations.append(f'the call gave up {elapsed:.1f} s after it began, past its {bound} s bound')
    return violations


def refused() -> BaseException:
    return paramiko.ssh_exception.NoValidConnectionsError({('192.0.2.1', 22): ConnectionRefusedError(61, 'Connection refused')})


def auth_failure(*results: BaseException) -> paramiko.AuthFailure:
    """What Paramiko's `AuthStrategy` raises when no source succeeded: each source's failure, in order."""
    from paramiko.auth_strategy import AuthResult, NoneAuth, SourceResult
    return paramiko.AuthFailure(AuthResult(None, [SourceResult(NoneAuth(USER), result) for result in results]))


RECONNECT_FAILURES = {
    # (the step every attempt takes, the cause the message names)
    'refused': ((0, refused), 'connection refused'),
    'timed-out': ((ssh.CONNECT_TIMEOUT, lambda: TimeoutError('timed out')), 'timed out'),
    'no-banner': ((ssh.CONNECT_TIMEOUT, lambda: paramiko.SSHException('No existing session')), 'timed out'),
    'unknown-host': ((0, lambda: socket.gaierror(8, 'nodename nor servname provided, or not known')),
                     'unknown host or SSH alias'),
    'building-fails': (('build', lambda: ValueError('Match exec failed')), 'Match exec failed'),
    # An authentication cut short is no refusal: retried, and named for what cut it.
    'auth-closed': ((0, lambda: paramiko.AuthenticationException(ssh.AUTH_CLOSED)),
                    'connection closed during authentication'),
    'auth-timed-out': ((ssh.CONNECT_TIMEOUT, lambda: paramiko.AuthenticationException(ssh.AUTH_TIMED_OUT)),
                       'timed out'),
    # An `AuthFailure` is no refusal when a source failed for another reason: named for that one.
    'auth-failure-closed': ((0, lambda: auth_failure(paramiko.AuthenticationException('Authentication failed.'),
                                                     paramiko.AuthenticationException(ssh.AUTH_CLOSED))),
                            'connection closed during authentication'),
    'auth-failure-agent': ((0, lambda: auth_failure(paramiko.SSHException('lost ssh-agent'))), 'lost ssh-agent'),
}


@pytest.mark.unit
@pytest.mark.parametrize('failure', list(RECONNECT_FAILURES))
def test_a_reconnect_that_cannot_succeed_fails_within_the_bound(failure: str, rig: ReconnectRig, guard) -> None:
    step, cause = RECONNECT_FAILURES[failure]
    executor = rig.executor(['ok', step])
    result = executor.run(['true'])
    elapsed = rig.clock.elapsed()
    violations = not_run_violations(result, cause, elapsed, RECONNECT_BOUND)
    starts = [at for _, at in rig.built]
    if len(rig.built) < 2:
        violations.append(f'the call made {len(rig.built)} attempts in its window, so it never retried')
    if starts and max(starts) > RECONNECT_BOUND - ssh.FINAL_ATTEMPT_LEAD + RECONNECT_SLACK:
        violations.append(f'the last attempt started {max(starts):.1f} s after the call began, later than '
                          f'{ssh.FINAL_ATTEMPT_LEAD} s before its {RECONNECT_BOUND} s bound')
    if {name for name, _ in rig.built} != {WORKER}:
        violations.append(f'a connection was built outside the reconnect worker: {rig.built}')
    assert violations == [], f'{failure}:\n' + '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_a_reconnect_refused_authentication_fails_at_once(rig: ReconnectRig, guard) -> None:
    executor = rig.executor(['ok', (0, lambda: paramiko.AuthenticationException('Authentication failed.'))])
    result = executor.run(['true'])
    violations = not_run_violations(result, 'authentication failed', rig.clock.elapsed(), RECONNECT_BOUND)
    if len(rig.attempts) != 1:
        violations.append(f'a refused authentication was retried: {len(rig.attempts)} attempts, not one')
    if rig.clock.elapsed() > 1:
        violations.append(f'a refused authentication took {rig.clock.elapsed():.1f} s to give up, not at once')
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


# Each `AuthenticationException` Paramiko raises for a refusal, beyond the plain one: the server allows
# none of the methods tried, or wants more than was offered; a key needs a passphrase; and an
# `AuthFailure` whose every source was refused.
REFUSALS = {
    'bad-type': lambda: paramiko.BadAuthenticationType('Bad authentication type', ['password']),
    'partial': lambda: paramiko.ssh_exception.PartialAuthentication(['keyboard-interactive']),
    'password-required': lambda: paramiko.PasswordRequiredException('Private key file is encrypted'),
    'auth-failure': lambda: auth_failure(paramiko.AuthenticationException('Authentication failed.'),
                                         paramiko.BadAuthenticationType('Bad authentication type', ['password'])),
}


@pytest.mark.unit
@pytest.mark.parametrize('refusal', list(REFUSALS))
def test_every_refusal_ends_the_reconnect_at_once(refusal: str, rig: ReconnectRig, guard) -> None:
    executor = rig.executor(['ok', (0, REFUSALS[refusal])])
    result = executor.run(['true'])
    violations = not_run_violations(result, 'authentication failed', rig.clock.elapsed(), RECONNECT_BOUND)
    if len(rig.attempts) != 1:
        violations.append(f'a refusal ({refusal}) was retried: {len(rig.attempts)} attempts, not one')
    if rig.clock.elapsed() > 1:
        violations.append(f'a refusal ({refusal}) took {rig.clock.elapsed():.1f} s to give up, not at once')
    assert violations == [], f'{refusal}:\n' + '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_the_declared_paramiko_floor_matches_the_classifier() -> None:
    root = Path(__file__).resolve().parent.parent
    dependencies = tomllib.loads((root / 'pyproject.toml').read_text())['project']['dependencies']
    floors = [re.fullmatch(r'paramiko\s*>=\s*([0-9.]+)\s*(,.*)?', dependency) for dependency in dependencies]
    found = [match.group(1) for match in floors if match]
    assert len(found) == 1, f'pyproject.toml declares no one paramiko floor: {dependencies}'
    declared = tuple(int(part) for part in found[0].split('.'))
    assert declared == ssh.PARAMIKO_FLOOR, \
        f'the declared paramiko floor {declared} and the classifier\'s ({ssh.PARAMIKO_FLOOR}) disagree'
    installed = tuple(int(part) for part in paramiko.__version__.split('.')[:2])
    assert installed >= ssh.PARAMIKO_FLOOR, f'paramiko {paramiko.__version__} is below the floor'
    import inspect
    waits = inspect.getsource(paramiko.auth_handler.AuthHandler.wait_for_response)
    missing = [text for text in (ssh.AUTH_CLOSED, ssh.AUTH_TIMED_OUT) if f'"{text}"' not in waits]
    assert missing == [], f'paramiko {paramiko.__version__} no longer raises {missing}: the classifier and it disagree'


# How a call meets its last start: with no attempt in flight, or with one another call started.
LATE = ['none-in-flight', 'one-in-flight']


@pytest.mark.unit
@pytest.mark.parametrize('inflight', LATE)
def test_a_call_past_its_last_start_starts_no_attempt(inflight: str, rig: ReconnectRig, guard) -> None:
    executor = rig.executor(['ok', 'ok'])
    held = executor._inflight = ssh._Pending() if inflight == 'one-in-flight' else None
    try:
        got = executor._ensure_connected(rig.clock.monotonic() + ssh.FINAL_ATTEMPT_LEAD - 0.5)
    finally:
        executor._inflight = None
    violations = []
    if got != f'cannot connect to {RECONNECT_HOST}: timed out':
        violations.append(f'a call past its last start gave {got!r}, not `cannot connect to <host>: timed out`')
    if rig.attempts:
        violations.append(f'a call past its last start started {len(rig.attempts)} attempts')
    if held is not None and held.waiters != 1:
        violations.append(f'a call past its last start joined the attempt in flight ({held.waiters} waiters)')
    if rig.clock.elapsed() > RECONNECT_SLACK:
        violations.append(f'a call past its last start gave up {rig.clock.elapsed():.1f} s later, not at once')
    assert violations == [], f'{inflight}:\n' + '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_a_reconnect_bound_grows_with_a_longer_connect_timeout(rig: ReconnectRig, guard) -> None:
    executor = rig.executor(['ok', (0, refused)], connect_timeout=30)
    result = executor.run(['true'])
    bound = ssh.RECONNECT_FACTOR * 30
    violations = not_run_violations(result, 'connection refused', rig.clock.elapsed(), bound)
    starts = [c.started for c in rig.attempts if c.started is not None]
    if not any(start > RECONNECT_BOUND for start in starts):
        violations.append(f'no attempt started after {RECONNECT_BOUND} s, so a 30 s connect timeout did not '
                          f'raise the bound to {bound} s: attempts at {[round(s, 1) for s in starts]}')
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


QUIET_SSH = {'load_ssh_configs': False}


@pytest.mark.unit
@pytest.mark.parametrize('given', ['ssh-config', 'connect-kwargs'])
def test_a_reconnect_bound_reads_the_connect_timeout(given: str, rig: ReconnectRig, guard) -> None:
    if given == 'ssh-config':
        kwargs: dict[str, Any] = {'config': Config(overrides=QUIET_SSH,
                                                   ssh_config=paramiko.SSHConfig.from_text('Host *\n  ConnectTimeout 30\n'))}
    else:
        kwargs = {'config': Config(overrides=QUIET_SSH, ssh_config=paramiko.SSHConfig()), 'connect_kwargs': {'timeout': 30}}
    executor = rig.executor(connection=OpenFree, **kwargs)
    assert (ssh._bound(executor._conn), executor._window) == (30, ssh.RECONNECT_FACTOR * 30), \
        f'{given}: a connect timeout of 30 s gave a bound of {ssh._bound(executor._conn)} and a window of {executor._window}'
    assert guard.refused == []


@pytest.mark.unit
def test_a_reconnect_attempt_that_hangs_is_abandoned_at_the_bound(rig: ReconnectRig, guard) -> None:
    executor = rig.executor(['ok', 'hang'])
    dead = executor._conn
    result = executor.run(['true'])
    violations = not_run_violations(result, 'timed out', rig.clock.elapsed(), RECONNECT_BOUND)
    rig.finish()
    late = rig.attempts[0] if rig.attempts else None
    if late is None or executor._conn is not late or ssh._live(executor._conn) is None:
        violations.append(f'the late success was leaked: the executor holds {executor._conn!r}, not the attempt '
                          f'that opened after its caller left')
    if not dead.client.closed:
        violations.append('the dead connection the late success replaced was not released')
    if executor._inflight is not None:
        violations.append('the attempt slot stayed taken after the attempt ended')
    if late is not None and executor._ensure_connected(rig.clock.monotonic() + 1) is not late.transport:
        violations.append('the next call did not use the published connection')
    if len(rig.attempts) != 1:
        violations.append(f'{len(rig.attempts)} attempts were made, not one')
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


class Canonicalising:
    """`socket.gethostbyname` for a ssh_config that canonicalises: no name resolves, and once
    `blocking`, each lookup parks, as a stalled resolver does, until the row releases it."""

    def __init__(self, rig: ReconnectRig) -> None:
        self.rig = rig
        self.blocking = False
        self.threads: list[str] = []

    def __call__(self, name: str) -> str:
        if not self.blocking:
            raise socket.gaierror(8, 'nodename nor servname provided, or not known')
        self.threads.append(threading.current_thread().name)
        self.rig.clock.park(None)
        raise OSError('the stalled lookup was released')


CANONICALISING = 'Host *\n  CanonicalizeHostname yes\n  CanonicalDomains example.invalid\n'


def canonicalising(rig: ReconnectRig, monkeypatch: pytest.MonkeyPatch) -> tuple[SSHExecutor, Canonicalising]:
    """An executor that builds real connections whose ssh_config canonicalises, through a resolver
    that stalls."""
    resolver = Canonicalising(rig)
    monkeypatch.setattr(socket, 'gethostbyname', resolver)
    config = Config(overrides=QUIET_SSH, ssh_config=paramiko.SSHConfig.from_text(CANONICALISING))
    executor = rig.executor(connection=OpenFree, config=config)
    resolver.blocking = True
    return executor, resolver


@pytest.mark.unit
def test_a_reconnect_that_blocks_building_the_connection_is_abandoned(rig: ReconnectRig, monkeypatch: pytest.MonkeyPatch,
                                                                       guard) -> None:
    executor, resolver = canonicalising(rig, monkeypatch)
    result = executor.run(['true'])
    violations = not_run_violations(result, 'timed out', rig.clock.elapsed(), RECONNECT_BOUND)
    if resolver.threads != [WORKER]:
        violations.append(f'the connection was built on {resolver.threads}, not on one reconnect worker')
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_concurrent_reconnects_publish_one_connection(rig: ReconnectRig, guard) -> None:
    executor = rig.executor(['ok', ('at', 1.0)])
    got: list[Any] = [None] * 4

    def call(i: int) -> None:
        try:
            got[i] = executor._ensure_connected(rig.clock.monotonic() + RECONNECT_BOUND)
        except BaseException as exc:
            got[i] = exc

    threads = [threading.Thread(target=call, args=(i,)) for i in range(len(got))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    violations = []
    if len(rig.attempts) != 1 or executor._conn is not rig.attempts[0]:
        violations.append(f'{len(rig.attempts)} connections were made for concurrent reconnects, not one published')
    elif any(transport is not rig.attempts[0].transport for transport in got):
        violations.append(f'a concurrent reconnect was handed something other than the published transport: {got!r}')
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


# Calls that arrive while one attempt is stuck where nothing can abort it.
STALLED_CALLS = 4


@pytest.mark.unit
@pytest.mark.parametrize('stall', ['hang', 'canonicalisation'])
def test_concurrent_calls_during_a_stall_start_one_attempt(stall: str, rig: ReconnectRig,
                                                           monkeypatch: pytest.MonkeyPatch, guard) -> None:
    if stall == 'hang':
        executor = rig.executor(['ok', 'hang'])
    else:
        executor, _ = canonicalising(rig, monkeypatch)
    rig.clock.rebase(4 * RECONNECT_BOUND)
    # Fake time moves only once every call has taken its deadline: a thread that starts late would
    # otherwise begin after the others had spent their whole windows in a millisecond of real time.
    arrived: list[None] = []
    all_in = threading.Event()
    ensure, wait = SSHExecutor._ensure_connected, ssh._await

    def arriving(this: SSHExecutor, deadline: float) -> Any:
        with rig.lock:
            arrived.append(None)
            if len(arrived) >= STALLED_CALLS:
                all_in.set()
        return ensure(this, deadline)

    def latched(event: threading.Event, seconds: float) -> bool:
        if not all_in.wait(SETTLE_LIMIT):
            raise AssertionError(f'only {len(arrived)} of {STALLED_CALLS} calls arrived')
        return wait(event, seconds)

    monkeypatch.setattr(SSHExecutor, '_ensure_connected', arriving)
    monkeypatch.setattr(ssh, '_await', latched)
    got: list[Any] = [None] * STALLED_CALLS

    def call(i: int) -> None:
        began = rig.clock.monotonic()
        try:
            got[i] = (executor.run(['true']), rig.clock.monotonic() - began)
        except BaseException as exc:
            got[i] = exc

    threads = [threading.Thread(target=call, args=(i,)) for i in range(STALLED_CALLS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    violations = []
    bound = RECONNECT_BOUND + STALLED_CALLS * ssh.ATTEMPT_POLL
    for i, outcome in enumerate(got):
        if not isinstance(outcome, tuple):
            violations.append(f'call {i} raised {outcome!r}')
            continue
        result, elapsed = outcome
        violations += [f'call {i}: {v}' for v in not_run_violations(result, 'timed out', elapsed, bound)]
    during = len(rig.built)
    rig.clock.rebase()
    after = executor.run(['true'])
    if after.exit_code != NOT_STARTED_EXIT_CODE:
        violations.append(f'a call after the others left returned {after!r}')
    if (during, len(rig.built)) != (1, 1):
        violations.append(f'{STALLED_CALLS} calls during a stall started {during} attempts, and a call after them '
                          f'{len(rig.built) - during} more: not one')
    rig.finish()
    if executor._inflight is not None:
        violations.append('the attempt slot stayed taken after the stalled attempt ended')
    assert violations == [], f'{stall}:\n' + '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_a_reconnect_that_succeeds_at_the_deadline_is_owned_once(rig: ReconnectRig, guard) -> None:
    executor = rig.executor(['ok', ('at', RECONNECT_BOUND)])
    got = executor._ensure_connected(rig.clock.monotonic() + RECONNECT_BOUND)
    rig.finish()
    violations = []
    opened = rig.attempts[0] if rig.attempts else None
    if opened is None or executor._conn is not opened or opened.client.closed:
        violations.append(f'a success at the deadline was not owned by the executor: it holds {executor._conn!r}')
    if not (isinstance(got, str) or (opened is not None and got is opened.transport)):
        violations.append(f'the call was handed {got!r}, neither the success nor a message')
    if len(rig.attempts) != 1 or executor._inflight is not None:
        violations.append(f'{len(rig.attempts)} attempts, and the slot is {executor._inflight!r}')
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_a_failed_reconnect_of_a_transfer_raises_naming_the_host(rig: ReconnectRig, tmp_path: Path, guard) -> None:
    executor = rig.executor(['ok', (0, refused)])
    head = f'cannot connect to {RECONNECT_HOST}: connection refused'
    violations = []
    for name, transfer in (('put', lambda: executor.put(str(tmp_path / 'x'), '~/x')),
                           ('get', lambda: executor.get('~/x', str(tmp_path / 'x')))):
        rig.clock.rebase()
        try:
            transfer()
        except ConnectionError as exc:
            if not (str(exc).startswith(head) and str(exc).endswith('; nothing was transferred')):
                violations.append(f'{name} raised {str(exc)!r}, not naming the host, the cause and that nothing was '
                                  'transferred')
            if rig.clock.elapsed() > RECONNECT_BOUND + RECONNECT_SLACK:
                violations.append(f'{name} gave up {rig.clock.elapsed():.1f} s after it began')
        else:
            violations.append(f'{name} returned instead of raising ConnectionError')
    rig.clock.rebase()
    written = executor.write('~/x', b'data')
    violations += [f'write: {v}' for v in not_run_violations(written, 'connection refused', rig.clock.elapsed(),
                                                               RECONNECT_BOUND)]
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


# Where an abort and a publish meet: the attempt publishes between the last call's decision to abort
# and the abort itself, or it opens before the abort closes it and reaches its publish only after.
CROSSINGS = ['published-first', 'opened-first']


@pytest.mark.unit
@pytest.mark.parametrize('crossing', CROSSINGS)
def test_an_abort_and_a_publish_never_cross(crossing: str, rig: ReconnectRig, monkeypatch: pytest.MonkeyPatch,
                                            guard) -> None:
    executor = rig.executor(['ok', 'hang' if crossing == 'published-first' else 'ok'])
    abort, attempt = SSHExecutor._abort, SSHExecutor._attempt
    acted = threading.Event()

    def seam(this: SSHExecutor, pending: Any) -> None:
        """The last call has decided to abort; the attempt's outcome lands before the abort acts."""
        if crossing == 'published-first':
            rig.clock.release()
            if not pending.done.wait(SETTLE_LIMIT):
                raise AssertionError('the released attempt never published')
        abort(this, pending)
        acted.set()
        rig.clock.release()

    def opening(this: SSHExecutor, pending: Any) -> Any:
        """The attempt, which once opened waits for the abort before it reaches its publish."""
        conn = attempt(this, pending)
        if crossing == 'opened-first':
            rig.clock.park(None)
        return conn

    monkeypatch.setattr(SSHExecutor, '_abort', seam)
    monkeypatch.setattr(SSHExecutor, '_attempt', opening)
    executor._ensure_connected(rig.clock.monotonic() + RECONNECT_BOUND)
    rig.finish()
    opened = rig.attempts[0] if rig.attempts else None
    violations = []
    if not acted.is_set():
        violations.append('the call never reached its abort, so nothing crossed')
    if opened is None or opened.transport is None:
        violations.append('the attempt never opened')
    elif crossing == 'published-first':
        if executor._conn is not opened or not opened.transport.active:
            violations.append(f'the abort closed a published connection: the executor holds {executor._conn!r}, '
                              f'its transport active={opened.transport.active}')
        elif executor._ensure_connected(rig.clock.monotonic() + 1) is not opened.transport:
            violations.append('the next call did not use the published connection')
    else:
        if executor._conn is opened:
            violations.append('the worker published a connection the abort closed')
        if opened.transport.active:
            violations.append('the abort left the attempt it aborted open')
    if executor._inflight is not None:
        violations.append('the attempt slot stayed taken after the attempt ended')
    assert violations == [], f'{crossing}:\n' + '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_an_abort_spares_an_attempt_another_call_joined_since(rig: ReconnectRig, monkeypatch: pytest.MonkeyPatch,
                                                              guard) -> None:
    # The initial connection, an attempt held in its authentication with its transport made, and a
    # fresh one, which the joining call starts only if the held attempt was aborted under it.
    executor = rig.executor(['ok', 'shake', 'ok'])
    abort, wait = SSHExecutor._abort, ssh._await
    joined: list[Any] = []
    seen: dict[str, Any] = {}

    def call() -> None:
        try:
            joined.append(executor._ensure_connected(rig.clock.monotonic() + RECONNECT_BOUND))
        except BaseException as exc:
            joined.append(exc)

    joiner = threading.Thread(target=call)

    def waiting(event: threading.Event, seconds: float) -> bool:
        """The joining call waits on the attempt in real time, so it never moves the clock."""
        if threading.current_thread() is joiner:
            return event.wait(SETTLE_LIMIT)
        return wait(event, seconds)

    def seam(this: SSHExecutor, pending: Any) -> None:
        """The last call has decided to abort; another call joins the attempt before the abort acts."""
        joiner.start()
        limit = _REAL_MONOTONIC() + SETTLE_LIMIT
        while pending.waiters == 0:
            if _REAL_MONOTONIC() > limit:
                raise AssertionError('the second call never joined the attempt')
            _REAL_SLEEP(0.001)
        abort(this, pending)
        transport = pending.conn.client.get_transport() if pending.conn is not None else None
        seen.update(transport=transport, active=transport is not None and transport.active, aborted=pending.aborted)
        rig.clock.release()

    monkeypatch.setattr(ssh, '_await', waiting)
    monkeypatch.setattr(SSHExecutor, '_abort', seam)
    first = executor._ensure_connected(rig.clock.monotonic() + RECONNECT_BOUND)
    joiner.join(SETTLE_LIMIT)
    rig.finish()
    held = rig.attempts[0] if rig.attempts else None
    violations = []
    if not seen:
        violations.append('the first call never reached its abort, so no call joined since')
    elif seen['transport'] is None:
        violations.append('the held attempt had no transport, so the abort had nothing to spare')
    elif not seen['active'] or seen['aborted']:
        violations.append('the abort closed an attempt another call had joined since')
    if first != f'cannot connect to {RECONNECT_HOST}: timed out':
        violations.append(f'the call that left gave {first!r}, not its own give-up')
    if held is None or joined != [held.transport] or executor._conn is not held:
        violations.append(f'the call that joined since was handed {joined!r}, not the held attempt published')
    if len(rig.attempts) != 1:
        violations.append(f'{len(rig.attempts)} attempts ran, not one: the call that joined since had to start '
                          'another')
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_a_call_at_its_deadline_takes_an_outcome_that_has_come(rig: ReconnectRig, monkeypatch: pytest.MonkeyPatch,
                                                                guard) -> None:
    executor = rig.executor(['ok', 'hang'])
    leave = SSHExecutor._leave

    def late(this: SSHExecutor, pending: Any) -> bool:
        """The call's last wait has run out; the attempt's success lands before the call leaves."""
        rig.clock.release()
        if not pending.done.wait(SETTLE_LIMIT):
            raise AssertionError('the released attempt never ended')
        return leave(this, pending)

    monkeypatch.setattr(SSHExecutor, '_leave', late)
    got = executor._ensure_connected(rig.clock.monotonic() + RECONNECT_BOUND)
    rig.finish()
    opened = rig.attempts[0] if rig.attempts else None
    violations = []
    if opened is None or got is not opened.transport:
        violations.append(f'a call whose attempt succeeded as it reached its deadline reported a failure: {got!r}')
    if opened is not None and (executor._conn is not opened or opened.transport is None
                               or not opened.transport.active):
        violations.append(f'the success was not kept published: the executor holds {executor._conn!r}')
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_a_reconnect_keeps_a_connection_published_meanwhile(rig: ReconnectRig, monkeypatch: pytest.MonkeyPatch,
                                                            guard) -> None:
    # The initial connection, the reconnect's attempt (held), then `open()` on this thread meanwhile.
    executor = rig.executor(['ok', 'hang', 'ok'])
    opened = threading.Event()
    wait = ssh._await

    def held(event: threading.Event, seconds: float) -> bool:
        if not opened.wait(SETTLE_LIMIT):
            raise AssertionError('no connection was opened meanwhile')
        return wait(event, seconds)

    monkeypatch.setattr(ssh, '_await', held)
    got: list[Any] = []

    def call() -> None:
        try:
            got.append(executor._ensure_connected(rig.clock.monotonic() + RECONNECT_BOUND))
        except BaseException as exc:
            got.append(exc)

    caller = threading.Thread(target=call)
    caller.start()
    limit = _REAL_MONOTONIC() + SETTLE_LIMIT
    while not rig.clock.parked:
        if _REAL_MONOTONIC() > limit:
            raise AssertionError('the reconnect attempt never started')
        _REAL_SLEEP(0.001)
    executor.open()
    meanwhile = executor._conn
    rig.clock.release()
    opened.set()
    caller.join(SETTLE_LIMIT)
    rig.finish()
    violations = []
    if len(rig.made) != 3 or meanwhile is not rig.made[2]:
        violations.append(f'{len(rig.made)} connections were made, not the initial one, the attempt and one opened '
                          'meanwhile')
    else:
        attempt = rig.made[1]
        if executor._conn is not meanwhile or meanwhile.client.closed or not ssh._live(meanwhile):
            violations.append(f'the connection published meanwhile was closed or replaced: the executor holds '
                              f'{executor._conn!r}')
        if got != [meanwhile.transport]:
            violations.append(f'the call was handed {got!r}, not the connection published meanwhile')
        if not attempt.client.closed:
            violations.append("the attempt's own connection, not published, was never released")
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
@pytest.mark.parametrize('given', ['ssh-config', 'connect-kwargs', 'connect-timeout'])
def test_a_reconnect_bound_never_falls_below_the_default(given: str, rig: ReconnectRig, guard) -> None:
    quiet = paramiko.SSHConfig()
    if given == 'ssh-config':
        kwargs: dict[str, Any] = {'config': Config(overrides=QUIET_SSH,
                                                   ssh_config=paramiko.SSHConfig.from_text('Host *\n  ConnectTimeout 5\n'))}
    elif given == 'connect-kwargs':
        kwargs = {'config': Config(overrides=QUIET_SSH, ssh_config=quiet), 'connect_kwargs': {'timeout': 5}}
    else:
        kwargs = {'config': Config(overrides=QUIET_SSH, ssh_config=quiet), 'connect_timeout': 5}
    executor = rig.executor(connection=OpenFree, **kwargs)
    bound, window = ssh._bound(executor._conn), executor._window
    assert (bound, window) == (ssh.CONNECT_TIMEOUT, RECONNECT_BOUND), \
        f'{given}: a 5 s connect timeout lowered the bound to {bound} s and the window to {window} s'
    assert guard.refused == []


# The reconnect bound, as the SSHExecutor docstring and the AGENTS.md footgun state it, word for word.
RECONNECT_BOUND_TEXT = (
    'A call that finds the connection lost keeps trying to reconnect, with backoff, and gives up at most three '
    'times the connect bound after the call began: 45 s with the default 15 s (`CONNECT_TIMEOUT`). It starts or '
    'joins no attempt later than 2 s before that: one that finds the connection lost after then, as a `write`\'s '
    'later command can, gives up at once. An ssh_config `ConnectTimeout` (or a caller\'s `connect_timeout`) '
    'longer than 15 s raises the bound to three times that value; a shorter one never lowers it. A refused '
    'authentication, the server rejecting the credentials or a key that cannot be used, gives up at once; one cut '
    'short by a lost link or its own timeout is retried, and no call takes the failure of an attempt aborted at '
    'another call\'s deadline as its own. The call then reports `cannot connect to <host>: <cause>` and runs '
    'nothing, and the next call tries again.')


@pytest.mark.unit
def test_reconnect_texts_state_the_bound() -> None:
    root = Path(__file__).resolve().parent.parent
    agents = (root / 'AGENTS.md').read_text()
    texts = {
        'the SSHExecutor docstring': SSHExecutor.__doc__ or '',
        "AGENTS.md's executor/ssh.py footgun": _section(agents, '- **`executor/ssh.py`**', '- **`__init__.py`**'),
    }
    missing = [name for name, text in texts.items() if RECONNECT_BOUND_TEXT not in ' '.join(text.split())]
    assert missing == [], f'a text does not state the reconnect bound: {missing}'
    assert 'never gives up' not in agents, 'AGENTS.md still says the reconnect never gives up'
    numbers = (ssh.RECONNECT_FACTOR * ssh.CONNECT_TIMEOUT, ssh.CONNECT_TIMEOUT, ssh.FINAL_ATTEMPT_LEAD)
    assert numbers == (45, 15, 2.0), f'the texts state 45 s, 15 s and 2 s, but the code has {numbers}'



# ---------------------------------------------------------------------------------------------
# A host that goes down and comes back (`LoopbackSSH.refuse`, `serve_again`): a reconnect uses the
# host once it is back, a failure leaves the server serving the next call, and a stalled handshake
# is abandoned at the bound. Then every tool, in the selected era, reports a reconnect that gave up
# as nothing run, spending one window, and the cluster context is never cached from one.

# The command the recovery rows run, and the real seconds a row waits for the client to see a drop.
RECOVERY_COMMAND = ['printf', '%s|%s', 'back', 'again']
DROP_SEEN = 5.0
# Real seconds a tool row may take before the watchdog calls it still reconnecting.
WATCHDOG = 10.0


def _wait_dropped(executor: SSHExecutor) -> None:
    """Wait until the client's transport reads inactive, as the next call would find it."""
    limit = _REAL_MONOTONIC() + DROP_SEEN
    while ssh._live(executor._conn) is not None:
        if _REAL_MONOTONIC() > limit:
            raise AssertionError(f'the client still saw its connection as live {DROP_SEEN} s after the drop')
        _REAL_SLEEP(0.01)


def _fake_time(monkeypatch: pytest.MonkeyPatch, executor: SSHExecutor) -> FakeClock:
    """Install a fake clock for `executor`'s reconnects (`ssh.time`, `ssh._await`), started now."""
    clock = FakeClock(2 * executor._window)
    monkeypatch.setattr(ssh, 'time', clock)
    monkeypatch.setattr(ssh, '_await', clock.wait)
    clock.rebase()
    return clock


def _same(result: CommandResult) -> tuple[str, str, int]:
    return result.stdout, result.stderr, result.exit_code


# When the host comes back: on the second attempt, or on the first attempt 40 s or more into the window.
RETURNS: dict[str, Callable[[int, float], bool]] = {
    'second-attempt': lambda attempt, at: attempt == 2,
    'forty-seconds-in': lambda attempt, at: at >= 40,
}


@pytest.mark.integration
@pytest.mark.parametrize('returns', list(RETURNS))
def test_a_reconnect_after_the_host_returns_gives_the_same_result(returns: str, serve: Callable[..., LoopbackSSH],
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    server = serve('/bin/bash')
    executor = server.executor()
    attempts: list[float] = []
    served: list[float] = []
    try:
        baseline = executor.run(RECOVERY_COMMAND)
        dead = executor._conn
        server.refuse()
        _wait_dropped(executor)
        clock = _fake_time(monkeypatch, executor)
        back = RETURNS[returns]

        class Returning(Connection):
            """Fabric's `Connection`, whose open brings the host back on the attempt `returns` names."""

            def open(self) -> Any:
                attempts.append(clock.elapsed())
                if not served and back(len(attempts), attempts[-1]):
                    served.append(attempts[-1])
                    server.serve_again()
                return super().open()

        monkeypatch.setattr(ssh, 'Connection', Returning)
        result = executor.run(RECOVERY_COMMAND)
        elapsed = clock.elapsed()
    finally:
        executor.close()
    violations = []
    if _same(baseline) != ('back|again', '', 0):
        violations.append(f'the unbroken connection gave {baseline!r}, so there is no baseline')
    if _same(result) != _same(baseline):
        violations.append(f'after the host returned the call gave {result!r}, not the baseline {baseline!r}')
    if len(server._transports) != 2:
        violations.append(f'the server accepted {len(server._transports)} connections, not a second one')
    if executor._conn is dead:
        violations.append('the executor still holds the connection that dropped')
    if returns == 'second-attempt' and len(attempts) != 2:
        violations.append(f'{len(attempts)} attempts were made, not two')
    if returns == 'forty-seconds-in' and not (attempts and attempts[-1] >= 40):
        violations.append(f'no attempt started 40 s into the window: attempts at {[round(a, 1) for a in attempts]}')
    if elapsed > RECONNECT_BOUND + RECONNECT_SLACK:
        violations.append(f'the reconnect took {elapsed:.1f} s, past its {RECONNECT_BOUND} s bound')
    assert violations == [], f'{returns}:\n' + '\n'.join(violations)


def _command_result(outcome: Outcome) -> dict[str, Any]:
    """The `CommandResult` a `run_command` call returned, as the client read it."""
    try:
        return json.loads(outcome.text)
    except ValueError:
        return {'unreadable': outcome.text}


@pytest.mark.integration
def test_a_failed_reconnect_leaves_the_server_serving(serve: Callable[..., LoopbackSSH],
                                                      monkeypatch: pytest.MonkeyPatch, executes: Any) -> None:
    server = serve('/bin/bash')
    executor = server.executor()
    command = 'printf %s back'

    async def scenario() -> tuple[Outcome, float, Outcome]:
        async with in_memory(shared_server(executor)) as client:
            server.refuse()
            _wait_dropped(executor)
            clock = _fake_time(monkeypatch, executor)
            failed = await call(client, 'run_command', {'command': command})
            spent = clock.elapsed()
            server.serve_again()
            clock.rebase()
            again = await call(client, 'run_command', {'command': command})
            return failed, spent, again

    try:
        failed, spent, again = drive(scenario(), timeout=60)
    finally:
        executor.close()
    first, second = _command_result(failed), _command_result(again)
    violations = []
    head = f'cluster-mcp: cannot connect to {LOOPBACK}: connection refused'
    if failed.is_error or first.get('exit_code') != NOT_STARTED_EXIT_CODE or not str(first.get('stderr')).startswith(head):
        violations.append(f'the call while the host was down gave {failed!r:.400}, not {NOT_STARTED_EXIT_CODE} '
                          f'with {head!r}')
    if spent > RECONNECT_BOUND + RECONNECT_SLACK:
        violations.append(f'the failed call took {spent:.1f} s, past its {RECONNECT_BOUND} s bound')
    if again.is_error or (second.get('stdout'), second.get('exit_code')) != ('back', 0):
        violations.append(f'after the host returned, the next call on the same server gave {again!r:.400}, '
                          'not the command run')
    if len(server._transports) != 2:
        violations.append(f'the server accepted {len(server._transports)} connections, not a second one')
    assert violations == [], '\n'.join(violations)


# What `Thread.start` raises when the process cannot make another thread.
NO_THREAD = "can't start new thread"


@pytest.mark.integration
def test_a_reconnect_worker_that_cannot_start_frees_the_attempt(serve: Callable[..., LoopbackSSH],
                                                                monkeypatch: pytest.MonkeyPatch, executes: Any) -> None:
    server = serve('/bin/bash')
    executor = server.executor()
    command = 'printf %s back'
    real_start = threading.Thread.start
    refused: list[str] = []
    started: list[str] = []

    def start(thread: threading.Thread) -> None:
        """`Thread.start`, refusing the first reconnect worker as a process out of threads would."""
        if thread.name == WORKER:
            if not refused:
                refused.append(thread.name)
                raise RuntimeError(NO_THREAD)
            started.append(thread.name)
        real_start(thread)

    async def scenario() -> tuple[Outcome, float, bool, Outcome]:
        async with in_memory(shared_server(executor)) as client:
            server.refuse()
            _wait_dropped(executor)
            server.serve_again()
            clock = _fake_time(monkeypatch, executor)
            monkeypatch.setattr(threading.Thread, 'start', start)
            failed = await call(client, 'run_command', {'command': command})
            spent = clock.elapsed()
            held = executor._inflight is not None
            clock.rebase()
            again = await call(client, 'run_command', {'command': command})
            return failed, spent, held, again

    try:
        failed, spent, held, again = drive(scenario(), timeout=60)
    finally:
        executor.close()
    first, second = _command_result(failed), _command_result(again)
    violations = []
    head = f'cluster-mcp: cannot connect to {LOOPBACK}: {NO_THREAD}; the command was not run'
    if failed.is_error or first.get('exit_code') != NOT_STARTED_EXIT_CODE or not str(first.get('stderr')).startswith(head):
        violations.append(f'the call whose worker could not start gave {failed!r:.400}, not {NOT_STARTED_EXIT_CODE} '
                          f'with {head!r}')
    if spent > ssh.ATTEMPT_POLL:
        violations.append(f'the call whose worker could not start took {spent:.1f} s, not giving up at once')
    if held:
        violations.append('the slot of an attempt whose worker never started stayed taken')
    if again.is_error or (second.get('stdout'), second.get('exit_code')) != ('back', 0):
        violations.append(f'the next call gave {again!r:.400}, not the command run on a fresh attempt')
    if (refused, started) != ([WORKER], [WORKER]):
        violations.append(f'{len(refused)} workers were refused and {len(started)} started, not one each')
    if len(server._transports) != 2:
        violations.append(f'the server accepted {len(server._transports)} connections, not a second one')
    assert violations == [], '\n'.join(violations)


class Silent:
    """A listener on `port` that accepts every connection and sends nothing, as a host whose sshd
    hangs before its banner does."""

    def __init__(self, port: int) -> None:
        self.held: list[socket.socket] = []
        self.listener = socket.socket()
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind((LOOPBACK, port))
        self.listener.listen(8)
        self.thread = threading.Thread(target=self._hold, daemon=True)
        self.thread.start()

    def _hold(self) -> None:
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            self.held.append(conn)

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.listener.shutdown(socket.SHUT_RDWR)
        self.listener.close()
        self.thread.join(5)
        for conn in self.held:
            conn.close()


# Real seconds: the window a 1 s connect bound gives, how late past it the call may return, and how
# long the abandoned worker may outlive the call.
STALL_WINDOW = ssh.RECONNECT_FACTOR * 1
STALL_LATE = 0.5
STALL_WORKER = 1.0


@pytest.mark.integration
def test_a_stalled_reconnect_is_abandoned_against_a_real_handshake(serve: Callable[..., LoopbackSSH],
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    # The executor is built, and its window taken, under a 1 s connect bound; the attempt is then built
    # under the real 15 s one, so its handshake waits on the silent host far past the 3 s window
    # unless the call's give-up aborts it.
    server = serve('/bin/bash')
    connect_timeout = ssh.CONNECT_TIMEOUT
    monkeypatch.setattr(ssh, 'CONNECT_TIMEOUT', 1)
    executor = SSHExecutor(LOOPBACK, port=server.port, user=USER,
                           config=Config(overrides={'load_ssh_configs': False}, ssh_config=paramiko.SSHConfig()),
                           connect_kwargs={'pkey': _key('client'), 'look_for_keys': False, 'allow_agent': False,
                                           'banner_timeout': 30})
    monkeypatch.setattr(ssh, 'CONNECT_TIMEOUT', connect_timeout)
    before = set(threading.enumerate())
    window = executor._window
    server.refuse()
    _wait_dropped(executor)
    silent = Silent(server.port)
    try:
        began = _REAL_MONOTONIC()
        result = executor.run(['true'])
        took = _REAL_MONOTONIC() - began
        workers = [t for t in threading.enumerate() if t.name == WORKER and t not in before]
        for worker in workers:
            worker.join(STALL_WORKER)
        lingered = [worker for worker in workers if worker.is_alive()]
        held = len(silent.held)
    finally:
        silent.close()
        executor.close()
    violations = []
    if window != STALL_WINDOW:
        violations.append(f'a 1 s connect bound gave a {window} s window, not {STALL_WINDOW} s')
    violations += not_run_violations(result, 'timed out', took, STALL_WINDOW, host=LOOPBACK, slack=STALL_LATE)
    if not held:
        violations.append('no attempt reached the silent host, so nothing stalled')
    if len(workers) != 1:
        violations.append(f'{len(workers)} reconnect workers ran, not one')
    if lingered:
        violations.append(f'the abandoned attempt was still running {STALL_WORKER} s after the call gave up')
    assert violations == [], '\n'.join(violations)


# How the loopback server cuts an authentication short, and what the attempt's failure is named:
# it closes the link while the client waits for its answer, or answers after the client's auth
# timeout (`AUTH_TIMEOUT` real seconds) has run out.
CUT_SHORT = {
    'closed': 'connection closed during authentication',
    'timed-out': 'timed out',
}
AUTH_TIMEOUT = 1
# Real seconds a server holds an authentication it cuts short or stalls, unless the row ends first.
AUTH_HOLD = 10.0


def _auth_rig(monkeypatch: pytest.MonkeyPatch, hold: threading.Event,
              cut: Callable[[Any], None] | None = None) -> list[None]:
    """Make the server's next authentication run `cut` on its transport, then wait on `hold`; return
    the list to arm it with (one item arms the next authentication)."""
    armed: list[None] = []
    check = _Server.check_auth_publickey

    def checking(this: _Server, username: str, key: paramiko.PKey) -> int:
        if armed:
            armed.clear()
            if cut is not None:
                cut(next(t for t in this.owner._transports if t.server_object is this))
            hold.wait(AUTH_HOLD)
        return check(this, username, key)

    monkeypatch.setattr(_Server, 'check_auth_publickey', checking)
    return armed


@pytest.mark.integration
@pytest.mark.parametrize('how', list(CUT_SHORT))
def test_an_authentication_cut_short_is_retried(how: str, serve: Callable[..., LoopbackSSH],
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    server = serve('/bin/bash')
    executor = SSHExecutor(LOOPBACK, port=server.port, user=USER,
                           config=Config(overrides={'load_ssh_configs': False}, ssh_config=paramiko.SSHConfig()),
                           connect_kwargs={'pkey': _key('client'), 'look_for_keys': False, 'allow_agent': False,
                                           'auth_timeout': AUTH_TIMEOUT})
    hold = threading.Event()
    failures: list[BaseException] = []
    attempt = SSHExecutor._attempt

    def recorded(this: SSHExecutor, pending: Any) -> Any:
        try:
            return attempt(this, pending)
        except BaseException as exc:
            failures.append(exc)
            raise

    try:
        baseline = executor.run(RECOVERY_COMMAND)
        server.refuse()
        _wait_dropped(executor)
        server.serve_again()
        armed = _auth_rig(monkeypatch, hold, _drop if how == 'closed' else None)
        monkeypatch.setattr(SSHExecutor, '_attempt', recorded)
        clock = _fake_time(monkeypatch, executor)
        armed.append(None)
        result = executor.run(RECOVERY_COMMAND)
        elapsed = clock.elapsed()
    finally:
        hold.set()
        executor.close()
    violations = []
    if _same(baseline) != ('back|again', '', 0):
        violations.append(f'the unbroken connection gave {baseline!r}, so there is no baseline')
    if result.exit_code == NOT_STARTED_EXIT_CODE and 'authentication failed' in result.stderr:
        violations.append(f'an authentication {how} was taken for a refusal: the call gave {result!r}')
    elif _same(result) != _same(baseline):
        violations.append(f'after an authentication {how}, the call gave {result!r}, not the baseline')
    causes = [ssh._cause_class(exc) for exc in failures]
    if causes != [CUT_SHORT[how]]:
        violations.append(f'the attempts failed as {causes} ({failures!r}), not once as {CUT_SHORT[how]!r}')
    if len(server._transports) != 3:
        violations.append(f'the server accepted {len(server._transports)} connections, not a retry after the one '
                          'cut short')
    if elapsed > RECONNECT_BOUND + RECONNECT_SLACK:
        violations.append(f'the reconnect took {elapsed:.1f} s, past its {RECONNECT_BOUND} s bound')
    assert violations == [], f'{how}:\n' + '\n'.join(violations)


@pytest.mark.integration
def test_a_call_never_inherits_an_aborted_attempt(serve: Callable[..., LoopbackSSH],
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    # The executor is built under a 1 s connect bound (a 3 s window); attempts are then built under
    # the real 15 s one, so the first, its authentication held by the server, outlasts the first
    # call's window, and that call's give-up aborts it.
    server = serve('/bin/bash')
    connect_timeout = ssh.CONNECT_TIMEOUT
    monkeypatch.setattr(ssh, 'CONNECT_TIMEOUT', 1)
    executor = server.executor()
    monkeypatch.setattr(ssh, 'CONNECT_TIMEOUT', connect_timeout)
    window = executor._window
    hold = threading.Event()
    failures: list[BaseException] = []
    joined: list[int] = []
    slept: list[float] = []
    attempt = SSHExecutor._attempt

    def holding(this: SSHExecutor, pending: Any) -> Any:
        """The attempt; an aborted one's failure waits until the next call has joined it."""
        try:
            return attempt(this, pending)
        except BaseException as exc:
            failures.append(exc)
            if pending.aborted:
                limit = _REAL_MONOTONIC() + SETTLE_LIMIT
                while pending.waiters == 0 and _REAL_MONOTONIC() < limit:
                    _REAL_SLEEP(0.005)
                joined.append(pending.waiters)
            raise

    def sleep(seconds: float) -> None:
        if seconds > ssh.SLEEP_WAIT:
            slept.append(seconds)
        _REAL_SLEEP(seconds)

    try:
        server.refuse()
        _wait_dropped(executor)
        armed = _auth_rig(monkeypatch, hold)
        server.serve_again()
        monkeypatch.setattr(SSHExecutor, '_attempt', holding)
        monkeypatch.setattr(ssh, 'time', SimpleNamespace(monotonic=_REAL_MONOTONIC, sleep=sleep))
        armed.append(None)
        began = _REAL_MONOTONIC()
        first = executor.run(['true'])
        took = _REAL_MONOTONIC() - began
        second = executor.run(RECOVERY_COMMAND)
    finally:
        hold.set()
        executor.close()
    violations = []
    if window != STALL_WINDOW:
        violations.append(f'a 1 s connect bound gave a {window} s window, not {STALL_WINDOW} s')
    violations += [f'first call: {v}' for v in not_run_violations(first, 'timed out', took, STALL_WINDOW,
                                                                    host=LOOPBACK, slack=STALL_LATE)]
    causes = [ssh._cause_class(exc) for exc in failures]
    if causes != ['connection closed during authentication']:
        violations.append(f'the attempts failed as {causes} ({failures!r}), not once, closed in its '
                          'authentication by the abort')
    if joined != [1]:
        violations.append(f'the next call never joined the aborted attempt ({joined}), so nothing was inherited')
    if _same(second) != ('back|again', '', 0):
        violations.append(f'the call that joined the aborted attempt gave {second!r}, not the command run')
    if slept:
        violations.append(f'the call that joined the aborted attempt slept a backoff of {slept} s: it took that '
                          "attempt's failure as its own")
    if len(server._transports) != 3:
        violations.append(f'the server accepted {len(server._transports)} connections, not a fresh one after the '
                          'aborted attempt')
    assert violations == [], '\n'.join(violations)


@pytest.mark.integration
def test_a_failed_attempt_releases_its_connection(serve: Callable[..., LoopbackSSH],
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    # The server holds the first authentication past the client's auth timeout, so that attempt
    # fails with its transport still up; the next attempt succeeds.
    server = serve('/bin/bash')
    executor = SSHExecutor(LOOPBACK, port=server.port, user=USER,
                           config=Config(overrides={'load_ssh_configs': False}, ssh_config=paramiko.SSHConfig()),
                           connect_kwargs={'pkey': _key('client'), 'look_for_keys': False, 'allow_agent': False,
                                           'auth_timeout': AUTH_TIMEOUT})
    hold = threading.Event()
    made: list[Any] = []
    new = SSHExecutor._new

    def tracked(this: SSHExecutor) -> Any:
        conn = new(this)
        made.append(conn)
        return conn

    try:
        server.refuse()
        _wait_dropped(executor)
        server.serve_again()
        armed = _auth_rig(monkeypatch, hold)
        monkeypatch.setattr(SSHExecutor, '_new', tracked)
        _fake_time(monkeypatch, executor)
        armed.append(None)
        result = executor.run(RECOVERY_COMMAND)
        failed = made[:-1]
        left = [conn for conn in failed if (transport := conn.client.get_transport()) is not None
                and transport.is_active()]
    finally:
        hold.set()
        executor.close()
    violations = []
    if _same(result) != ('back|again', '', 0):
        violations.append(f'the reconnect after the failed attempt gave {result!r}, not the command run')
    if len(failed) != 1:
        violations.append(f'{len(failed)} attempts failed, not the one whose authentication was held')
    if left:
        violations.append(f'a failed attempt left its connection open: {len(left)} of {len(failed)} transports still '
                          'active after the call')
    assert violations == [], '\n'.join(violations)


# Which of a write's own commands meets the lost host: the parent's `mkdir`, the program that puts
# the file in place, or the probe that asks why a transfer failed; and the fake seconds the write
# has spent by then.
WRITE_STEPS = {'parent': ssh.MAKE_PARENT, 'place': ssh.VERIFY, 'probe': ssh.PROBE}
WRITE_SPENT = 30.0


@pytest.mark.integration
@pytest.mark.parametrize('step', list(WRITE_STEPS))
def test_a_write_spends_one_reconnect_window(step: str, serve: Callable[..., LoopbackSSH],
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    server = serve('/bin/bash')
    executor = server.executor()
    if step == 'probe':
        server.write_limit = (4, errno.ENOSPC)
    ensure, run = SSHExecutor._ensure_connected, SSHExecutor._run
    connected: list[None] = []
    met: list[Any] = []

    def spending(this: SSHExecutor, deadline: float) -> Any:
        """The write's own connection, after which it spends `WRITE_SPENT` s before its first command."""
        got = ensure(this, deadline)
        if not connected:
            connected.append(None)
            clock.advance(WRITE_SPENT)
        return got

    def losing(this: SSHExecutor, command: Any, *args: Any, **kwargs: Any) -> CommandResult:
        """The write's first own command, which meets the host gone down."""
        if not met:
            met.append(command)
            server.refuse()
            _wait_dropped(this)
        return run(this, command, *args, **kwargs)

    # Only the parent row names a parent, which is missing, so its `mkdir` is the first command.
    parent = '~/sub' if step == 'parent' else None
    target = Path(server.home) / ('sub/x' if parent else 'x')
    try:
        monkeypatch.setattr(SSHExecutor, '_ensure_connected', spending)
        monkeypatch.setattr(SSHExecutor, '_run', losing)
        clock = _fake_time(monkeypatch, executor)
        try:
            outcome: Any = executor.write('~/sub/x' if parent else '~/x', b'content\n', parent=parent)
        except OSError as exc:
            outcome = exc
        spent = clock.elapsed()
    finally:
        executor.close()
    violations = []
    if not (met and any(WRITE_STEPS[step] in str(part) for part in met[0])):
        violations.append(f'the first command the write ran was {met!r:.300}, not its {step}')
    if step == 'probe':
        if not isinstance(outcome, OSError):
            violations.append(f'a write whose transfer failed gave {outcome!r}, not the OSError naming it')
    elif not isinstance(outcome, CommandResult):
        violations.append(f'the write raised {outcome!r}')
    else:
        violations += not_run_violations(outcome, 'connection refused', 0, RECONNECT_BOUND, host=LOOPBACK)
    if target.exists():
        violations.append('a write that could not reconnect changed the target')
    if spent > RECONNECT_BOUND + RECONNECT_SLACK:
        violations.append(f'the write spent {spent:.1f} s, more than one reconnect window ({RECONNECT_BOUND} s): its '
                          f'{step} took a deadline of its own')
    assert violations == [], f'{step}:\n' + '\n'.join(violations)


# How far into its window a write's placing command meets the lost host: past its last start.
WRITE_LATE = RECONNECT_BOUND - ssh.FINAL_ATTEMPT_LEAD + 1


@pytest.mark.integration
def test_a_write_command_past_its_last_start_starts_no_attempt(serve: Callable[..., LoopbackSSH],
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    server = serve('/bin/bash')
    executor = server.executor()
    ensure, run, new = SSHExecutor._ensure_connected, SSHExecutor._run, SSHExecutor._new
    connected: list[None] = []
    met: list[Any] = []
    made: list[Any] = []

    def spending(this: SSHExecutor, deadline: float) -> Any:
        """The write's own connection, after which it spends `WRITE_LATE` s before its first command."""
        got = ensure(this, deadline)
        if not connected:
            connected.append(None)
            clock.advance(WRITE_LATE)
        return got

    def losing(this: SSHExecutor, command: Any, *args: Any, **kwargs: Any) -> CommandResult:
        """The write's placing command, which meets the host gone down."""
        if not met:
            met.append(command)
            server.refuse()
            _wait_dropped(this)
        return run(this, command, *args, **kwargs)

    def tracked(this: SSHExecutor) -> Any:
        made.append(None)
        return new(this)

    target = Path(server.home) / 'x'
    try:
        monkeypatch.setattr(SSHExecutor, '_ensure_connected', spending)
        monkeypatch.setattr(SSHExecutor, '_run', losing)
        monkeypatch.setattr(SSHExecutor, '_new', tracked)
        clock = _fake_time(monkeypatch, executor)
        outcome = executor.write('~/x', b'content\n')
        spent = clock.elapsed()
    finally:
        executor.close()
    violations = []
    if not (met and any(ssh.VERIFY in str(part) for part in met[0])):
        violations.append(f'the first command the write ran was {met!r:.300}, not its placing program')
    violations += not_run_violations(outcome, 'timed out', 0, RECONNECT_BOUND, host=LOOPBACK)
    if made:
        violations.append(f'a write command past its last start started {len(made)} connect attempts')
    if spent > WRITE_LATE + RECONNECT_SLACK:
        violations.append(f'a write command past its last start gave up {spent - WRITE_LATE:.1f} s later, not at once')
    if target.exists():
        violations.append('a write that could not reconnect changed the target')
    assert violations == [], '\n'.join(violations)


def _watched(executor: Executor, tool: str, args: dict[str, Any]) -> Outcome:
    """`_tool`, under a real-time watchdog: a call still running after `WATCHDOG` s fails the row."""
    got: list[Any] = []

    def calling() -> None:
        try:
            got.append(_tool(executor, tool, args))
        except BaseException as exc:
            got.append(exc)

    thread = threading.Thread(target=calling, daemon=True)
    thread.start()
    thread.join(WATCHDOG)
    if thread.is_alive():
        pytest.fail(f'{tool}: still reconnecting {WATCHDOG} s after the call began')
    if isinstance(got[0], BaseException):
        raise got[0]
    return got[0]


# Each tool's call, and the text its failed reconnect must carry; `{tmp}` is the row's temporary tree.
RECONNECT_TOOLS: dict[str, tuple[str, dict[str, str], str]] = {
    'run_command': ('run_command', {'command': 'true'}, 'the command was not run'),
    'sbatch-script-path': ('sbatch', {'script_path': '~/job.sh'}, 'The job was not submitted'),
    'sbatch-script-content': ('sbatch', {'script_content': '#!/bin/bash\necho hi\n'}, 'The job was not submitted'),
    'write_file': ('write_file', {'path': '~/x', 'content': 'data'}, 'the command was not run'),
    'upload_file': ('upload_file', {'local_path': '{tmp}/x', 'remote_path': '~/x'}, 'nothing was transferred'),
    'download_file': ('download_file', {'remote_path': '~/x', 'local_path': '{tmp}/x'}, 'nothing was transferred'),
}


@pytest.mark.unit
@pytest.mark.parametrize('tool', list(RECONNECT_TOOLS))
def test_a_reconnect_failure_reaches_each_tool_as_not_run(tool: str, rig: ReconnectRig, tmp_path: Path, guard) -> None:
    name, given, said = RECONNECT_TOOLS[tool]
    executor = rig.executor(['ok', (0, refused)])
    args = {key: value.replace('{tmp}', str(tmp_path)) for key, value in given.items()}
    offset = rig.clock.offset
    outcome = _watched(executor, name, args)
    spent = rig.clock.offset - offset
    head = f'cannot connect to {RECONNECT_HOST}: connection refused'
    violations = []
    if name == 'run_command':
        got = _command_result(outcome)
        if outcome.is_error or got.get('exit_code') != NOT_STARTED_EXIT_CODE:
            violations.append(f'run_command gave {outcome!r:.400}, not {NOT_STARTED_EXIT_CODE}')
    elif not outcome.is_error:
        violations.append(f'{tool} succeeded with no connection: {outcome!r:.400}')
    if head not in outcome.text or said not in outcome.text:
        violations.append(f'{tool} read as {outcome.text!r:.400}: it must name {head!r} and say {said!r}')
    if name == 'sbatch' and ('may have been submitted' in outcome.text or 'Failed' in outcome.text):
        violations.append(f'{tool} read as {outcome.text!r:.400}: it must say the job was not submitted, never that '
                          'it failed or may have been submitted')
    if spent > RECONNECT_BOUND:
        violations.append(f'{tool} spent {spent:.1f} s reconnecting, more than one reconnect window ({RECONNECT_BOUND} s)')
    assert violations == [], f'{tool}:\n' + '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_sacct_spends_one_reconnect_window(rig: ReconnectRig, guard) -> None:
    executor = rig.executor(['ok', (0, refused)])
    rig.clock.rebase(4 * RECONNECT_BOUND)
    offset = rig.clock.offset
    outcome = _watched(executor, 'sacct', {})
    spent = rig.clock.offset - offset
    head = f'cannot connect to {RECONNECT_HOST}: connection refused'
    violations = []
    if not outcome.is_error or 'Failed to get the current user' not in outcome.text or head not in outcome.text:
        violations.append(f'sacct read as {outcome.text!r:.400}: it must stop at the failed whoami, naming {head!r}')
    if spent > RECONNECT_BOUND:
        violations.append(f'sacct spent {spent:.1f} s reconnecting, more than one reconnect window ({RECONNECT_BOUND} s)')
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


# The site context the context row's server was built with: what it must serve before and after.
RECONNECT_SITE = SiteContext(files=(SiteFile('a.md', 'Alpha rule.'), SiteFile('b.md', 'Bravo rule.')))


@pytest.mark.unit
def test_a_reconnect_failure_never_changes_the_cluster_context(rig: ReconnectRig, guard) -> None:
    """The site context is the startup read, so a `-1002` from another tool never reaches what
    `cluster_context` and `rcac://context` serve, and neither read starts a connect attempt."""
    executor = rig.executor(['ok', (0, refused)])
    # Room for a window on each of the five calls, so a read that does reconnect fails the row by its
    # text, not by running away.
    rig.clock.rebase(6 * RECONNECT_BOUND)

    async def scenario() -> tuple[list[Outcome], Outcome, int, list[Outcome]]:
        async with in_memory(shared_server(executor, site=RECONNECT_SITE)) as client:
            before = [await call(client, 'cluster_context', {}), await read_resource(client, 'rcac://context')]
            built = len(rig.built)
            failed = await call(client, 'run_command', {'command': 'true'})
            after = [await call(client, 'cluster_context', {}), await read_resource(client, 'rcac://context')]
            return before, failed, built, after

    before, failed, built, after = drive(scenario(), timeout=WATCHDOG)
    violations = []
    if built:
        violations.append(f'reading the cluster context started {built} connect attempts')
    if failed.is_error or _command_result(failed).get('exit_code') != NOT_STARTED_EXIT_CODE:
        violations.append(f'run_command gave {failed!r:.400}, not {NOT_STARTED_EXIT_CODE}')
    for when, outcomes in (('before', before), ('after', after)):
        for read, outcome in zip(('cluster_context', 'rcac://context'), outcomes):
            if outcome.is_error or outcome.text != RECONNECT_SITE.text:
                violations.append(f'{read} {when} a failed reconnect served {outcome!r:.400}, '
                                  f'not the startup read {RECONNECT_SITE.text!r}')
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


# ---------------------------------------------------------------------------------------------
# The channel loop (unit), against a fake channel.

class FakeChannel:
    """A channel whose exit status, output and end of output arrive at set times after creation."""

    def __init__(self, status: int, status_at: float, eof_at: float | None, data: bytes = b'out',
                 err: bytes = b'') -> None:
        self.start = time.monotonic()
        self.status, self.status_at, self.eof_at = status, status_at, eof_at
        self.data, self.err = data, err
        self.polls = 0
        self.closed = False

    def _now(self) -> float:
        return time.monotonic() - self.start

    @property
    def eof_received(self) -> bool:
        return self.eof_at is not None and self._now() >= self.eof_at

    def recv_ready(self) -> bool:
        self.polls += 1
        return bool(self.data)

    def recv(self, n: int) -> bytes:
        data, self.data = self.data[:n], self.data[n:]
        return data

    def recv_stderr_ready(self) -> bool:
        return bool(self.err)

    def recv_stderr(self, n: int) -> bytes:
        err, self.err = self.err[:n], self.err[n:]
        return err

    def exit_status_ready(self) -> bool:
        return self._now() >= self.status_at

    def recv_exit_status(self) -> int:
        return self.status if self.exit_status_ready() else -1

    def fileno(self) -> int:
        raise AssertionError('the loop selected on a channel whose exit status had arrived')


# A program's end nonce, and its records.
END = b'0123456789abcdeffedcba9876543210'
RECORD = END + b'x0.'



@pytest.mark.unit
def test_drain_waits_instead_of_spinning() -> None:
    # The exit status arrives at once; the end of output 0.5 s later.
    channel = FakeChannel(7, 0.0, 0.5)
    out, err, code, note = ssh._collect(channel, 5)
    assert (out, err, code, note) == (b'out', b'', 7, b''), (out, err, code, note)
    assert channel.polls < 100, f'the loop busy-waited: {channel.polls} polls in 0.5 s'


@pytest.mark.unit
def test_the_read_ends_at_both_records() -> None:
    # Both records are in at once; the output never ends and no exit status comes: a background job
    # holds the channel. The read ends at the records, at once.
    channel = FakeChannel(0, 60.0, None, b'out' + RECORD + b'late', RECORD + b'late-err')
    start = time.monotonic()
    out, err, code, note = ssh._collect(channel, 30, END)
    assert (out, err, note) == (b'out' + RECORD + b'late', RECORD + b'late-err', b''), (out, err, note)
    assert time.monotonic() - start < 1, 'the read went on past both end records'
    assert code == -1, f'with no exit status in, the status is unknown (-1), not {code}: the record carries it'


@pytest.mark.unit
def test_one_record_is_not_the_end() -> None:
    # stdout's record is in and the exit status too; stderr's record never comes: the call reads on
    # to its deadline, a timeout naming the status that arrived.
    channel = FakeChannel(0, 0.0, None, b'out' + RECORD, b'err')
    out, err, code, note = ssh._collect(channel, 0.5, END)
    assert (out, err, code) == (b'out' + RECORD, b'err', TIMEOUT_EXIT_CODE), (out, err, code)
    assert note == launch.LATE_NOTE.format(code=0).encode(), note


@pytest.mark.unit
def test_a_command_whose_records_have_not_come_by_the_deadline_is_a_timeout() -> None:
    # The command exited (its status is in), but its records are still queued on the link at the
    # deadline: a timeout, with the output read so far and a note naming the command's status.
    channel = FakeChannel(0, 0.0, None)
    start = time.monotonic()
    out, err, code, note = ssh._collect(channel, 0.3, END)
    assert (out, code) == (b'out', TIMEOUT_EXIT_CODE), (out, code)
    assert note == launch.LATE_NOTE.format(code=0).encode() and time.monotonic() - start < 2, note


class TrickleChannel(FakeChannel):
    """A channel whose exit status is in at once, and whose output arrives a piece every `every` s."""

    def __init__(self, pieces: list[bytes], every: float) -> None:
        super().__init__(0, 0.0, every * (len(pieces) + 0.5), b'')
        self.pieces, self.every, self.released = pieces, every, 0

    def recv_ready(self) -> bool:
        self.polls += 1
        due = min(len(self.pieces), int(self._now() / self.every))
        self.data += b''.join(self.pieces[self.released:due])
        self.released = max(self.released, due)
        return bool(self.data)


@pytest.mark.unit
def test_output_after_the_exit_status_is_read_to_the_end() -> None:
    # The exit status arrives at once; the output follows a piece every 0.4 s for 2.4 s, its record
    # last; stderr's record is in at once. The channel's output never ends.
    pieces = [b'%d\n' % i for i in range(6)] + [RECORD]
    channel = TrickleChannel(pieces, 0.4)
    channel.eof_at = None
    channel.err = RECORD
    out, err, code, note = ssh._collect(channel, 30, END)
    assert (out, code, note) == (b''.join(pieces), 0, b''), \
        f'output arriving after the exit status was cut: {out!r} of {b"".join(pieces)!r}, note {note!r}'


@pytest.mark.unit
def test_a_lost_status_stays_minus_one() -> None:
    channel = FakeChannel(-1, 0.0, 0.0)
    channel.closed = True
    assert ssh._collect(channel, 5) == (b'out', b'', -1, b'')


class LateChannel:
    """A channel that has no exit status and whose output arrives only after `data_at`: what a command
    prints as the TERM at the deadline stops it. Its descriptor never becomes readable."""

    def __init__(self, data_at: float, data: bytes) -> None:
        self.start = time.monotonic()
        self.data_at, self.data = data_at, data
        self._read, self._write = os.pipe()

    def now(self) -> float:
        return time.monotonic() - self.start

    @property
    def closed(self) -> bool:
        return self.now() >= self.data_at + 0.05

    @property
    def eof_received(self) -> bool:
        return self.closed

    def recv_ready(self) -> bool:
        return self.now() >= self.data_at and bool(self.data)

    def recv(self, n: int) -> bytes:
        data, self.data = self.data[:n], self.data[n:]
        return data

    def recv_stderr_ready(self) -> bool:
        return False

    def recv_stderr(self, n: int) -> bytes:
        return b''

    def exit_status_ready(self) -> bool:
        return False

    def recv_exit_status(self) -> int:
        return -1

    def fileno(self) -> int:
        return self._read

    def release(self) -> None:
        os.close(self._read)
        os.close(self._write)


@pytest.mark.unit
def test_a_timeout_drains_what_follows_the_term(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = LateChannel(0.5, b'stopping\n')
    sent: list[tuple[str, float]] = []
    monkeypatch.setattr(ssh, '_signal', lambda chan, name: sent.append((name, channel.now())))
    try:
        out, err, code, _ = ssh._collect(channel, 0.3)
    finally:
        channel.release()
    assert [name for name, _ in sent] == ['TERM'] and sent[0][1] < 0.5, sent
    assert (out, code) == (b'stopping\n', TIMEOUT_EXIT_CODE), \
        f'the timeout lost what followed the TERM: {out!r}, exit code {code}'


@pytest.mark.unit
def test_an_oversize_program_is_refused_before_connecting(monkeypatch: pytest.MonkeyPatch) -> None:
    # A script whose program fits a local launch but whose SSH exec string, bootstrap and base64 word
    # included, is over Linux's 131,072-byte per-argument limit.
    executor = object.__new__(SSHExecutor)
    executor._host, executor._conn, executor._connect_kwargs = 'stub', None, {}
    executor._window = ssh.RECONNECT_FACTOR * ssh.CONNECT_TIMEOUT
    reached: list[str] = []
    monkeypatch.setattr(SSHExecutor, '_ensure_connected', lambda self, deadline: reached.append('connect') or pytest.fail(
        'a program over the per-argument limit reached the connection instead of a ValueError naming it'))
    script = '#' * (98_200 - len(ssh.launch.program('')[0]))
    with pytest.raises(ValueError, match='131072-byte per-argument limit'):
        executor.run(script)
    assert reached == []


class ClosedChannel(FakeChannel):
    """A channel the transport closed: its output so far is in, and no end of output came."""

    def __init__(self, data: bytes, err: bytes = b'') -> None:
        super().__init__(-1, 0.0, None, data, err)
        self.closed = True


@pytest.mark.unit
def test_a_channel_closed_without_its_end_is_a_lost_connection() -> None:
    # Nothing arrived, so the start sentinel was not seen: the command may have run all the same.
    marks = launch.Marks(b'a' * 32, END)
    out, err, code, note = ssh._collect(ClosedChannel(b''), 5, END)
    assert (code, note) == (CONNECTION_LOST_EXIT_CODE, launch.LOST_NOTE), (code, note)
    assert launch.separate(out, err, code, marks, note) == (b'', launch.LOST_NOTE, CONNECTION_LOST_EXIT_CODE)
    # The sentinel arrived and part of the output, but no records: lost, with what arrived.
    started = ClosedChannel(marks.start + b'part', marks.start)
    out, err, code, note = ssh._collect(started, 5, END)
    assert launch.separate(out, err, code, marks, note) == (b'part', launch.LOST_NOTE, CONNECTION_LOST_EXIT_CODE)
    # Both records arrived before the close: complete, at the record's status.
    whole = ClosedChannel(marks.start + b'all' + END + b'x3.', marks.start + END + b'x3.')
    out, err, code, note = ssh._collect(whole, 5, END)
    assert launch.separate(out, err, code, marks, note) == (b'all', b'', 3)


class PiecesChannel(FakeChannel):
    """A channel that delivers stdout in `pieces`, one each `every` seconds, whose output never ends
    and whose exit status never comes: a background job holds it open."""

    def __init__(self, pieces: list[bytes], err: bytes, every: float = 0.15) -> None:
        super().__init__(0, 1e9, None, b'', err)
        self.pieces, self.every, self.released = pieces, every, 0

    def recv_ready(self) -> bool:
        self.polls += 1
        due = min(len(self.pieces), int(self._now() / self.every) + 1)
        self.data += b''.join(self.pieces[self.released:due])
        self.released = max(self.released, due)
        return bool(self.data)

    def fileno(self) -> int:
        return _NEVER_READY


_NEVER_READY = os.open(os.devnull, os.O_RDONLY)

# An end record split across reads: its nonce, then its status without the full stop, then the stop.
SPLIT = [b'out' + END[:10], END[10:] + b'x1', b'3.']


@pytest.mark.unit
def test_an_end_record_split_across_reads_is_found() -> None:
    marks = launch.Marks(b'a' * 32, END)
    channel = PiecesChannel([marks.start + SPLIT[0], *SPLIT[1:]], marks.start + END + b'x13.')
    start = time.monotonic()
    out, err, code, note = ssh._collect(channel, 5, END)
    result = launch.separate(out, err, code, marks, note)
    assert time.monotonic() - start < 3, 'a record split across reads was not found: the read ran to the deadline'
    assert result == (b'out', b'', 13), f'a record split across reads was misread: {result!r}, not exit 13'
