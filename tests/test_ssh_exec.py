# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
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
server signals the exec's process group on a `signal` request while the exec's process runs, as
sshd does, and does not kill a process when its channel closes, as OpenSSH does not; it kills what
is left when the test ends.

The `unit` rows drive the channel loop (`_collect`) with a fake channel: an exit status that arrives
before the end of output is waited on, not spun on, and decides nothing; the read ends at both end
records; a command whose records have not come by the deadline is a timeout, naming its status if
that has arrived; what a command prints after the TERM at its deadline is read; and the command is
asked to KILL once that read is over, never before, and only if its channel has not ended. A
`signal` request waits out a key exchange holding no lock and never follows a close marked while it
waited for the write path. Against the loopback server, which drops the connection for a message on
a channel it has freed, as sshd does, no `signal` request goes on a closed channel, and one on an
open channel is written holding the connection's write path, not the channel's lock; a timed call
returns at its timeout whatever another sender holds on that path, and the TERM still reaches its
command once the path is free. An exec string
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

The silent-link rows put a hop in front of the loopback server that stops forwarding without
closing a socket (`SilentLink`), under a 2 s connect bound, each call under a watchdog counted from
the moment the link went silent: a call that starts on a silent link reconnects, or with the host
gone reads as nothing run, within the reconnect bound, a reconnect that goes silent once made
included; a command running as the link goes silent is lost (`-1003`), with or without a timeout,
unless its timeout comes first, even beside an upload holding the write path, and is never sent
twice; a call beside a stalled one ends in time, and ends the stalled one; a call that starts while
the link is silent gives a quiet command or an upload beside it its own verdict, which they ride out
when the link answers within it and are cut past it; and an idle connection, a quiet command, one
trickling its output through a slow hop, and one through a silent spell shorter than a background
verdict are never cut.
"""

from __future__ import annotations

import base64
import contextlib
import errno
import json
import os
import plistlib
import re
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import tomllib
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator

import paramiko
import pytest
from fabric import Config, Connection

import argv_echo
from conftest import REAL_POPEN, SANDBOX, need_sftp_server, need_shell
from harness import CONTEXT_URIS, Outcome, call, drive, in_memory, read_resource, scheme, shared_server
from cluster_mcp.core.executor import CONNECTION_LOST_EXIT_CODE, NOT_STARTED_EXIT_CODE, TIMEOUT_EXIT_CODE, CommandResult, Executor, UserPath
from cluster_mcp.core.executor import launch, ssh
from cluster_mcp.core.executor.ssh import SSHExecutor
from cluster_mcp.core.site import SiteContext, SiteFile
from cluster_mcp.core.tools.shell import run_command
from ssh_server import (LOOPBACK, RECEIVE_BUFFER, SEND_BUFFER, USER, WINDOW, DroppingSSH, LoopbackSSH, SilentLink,
                        ThrottledSSH, _drop, _key, _Server, narrow_sends)
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


# Each real `hdiutil` step's bound, in seconds.
HDIUTIL_BOUND = 120
# After a step is stopped, how long to wait for its process group to empty, in seconds.
STOP_WAIT = 5
# The one signal that stops a step and everything it started: KILL at once, no TERM first.
STOP_SIGNAL = signal.SIGKILL
# Every `hdiutil` verb the fixture runs.
HDIUTIL_VERBS = ('create', 'attach', 'detach', 'info')


class HostFailure(Exception):
    """A host tool the fixture needs (not a command under test) failed or hung."""


def _bounds(overrides: dict[str, float] | None) -> dict[str, float]:
    """Each verb's bound: `HDIUTIL_BOUND`, unless `overrides` names another."""
    unknown = set(overrides or {}) - set(HDIUTIL_VERBS)
    assert not unknown, f'no such hdiutil verb: {sorted(unknown)}'
    return {verb: HDIUTIL_BOUND for verb in HDIUTIL_VERBS} | dict(overrides or {})


def _processes() -> list[tuple[int, int, str, str]]:
    """Every process on the host, as (pid, process group, state, command).

    A listing that does not show this process, with its command, is refused: `ps` answered in a
    shape this parse does not read, and an empty reading would say nothing runs.
    """
    proc = REAL_POPEN([str(SANDBOX), 'ps', '-A', '-ww', '-o', 'pid=', '-o', 'pgid=', '-o', 'stat=', '-o', 'args='],
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = proc.communicate(timeout=30)
    listed = []
    for line in out.decode(errors='replace').splitlines():
        fields = line.split(None, 3)
        if len(fields) >= 3 and fields[0].isdigit() and fields[1].isdigit():
            listed.append((int(fields[0]), int(fields[1]), fields[2], fields[3] if len(fields) > 3 else ''))
    if not any(pid == os.getpid() and command for pid, _, _, command in listed):
        raise HostFailure(f'ps listed no process {os.getpid()} with its command (status {proc.returncode}): '
                          f'{out.decode(errors="replace")[:400]!r} {err.decode(errors="replace")[-400:]!r}')
    return listed


def _group(pgid: int) -> list[tuple[int, str]]:
    """The processes of group `pgid` still running (a zombie is not), as (pid, command)."""
    return [(pid, command) for pid, group, state, command in _processes() if group == pgid and not state.startswith('Z')]


def _stop(proc: subprocess.Popen[bytes]) -> str:
    """Stop a step and everything it started (its process group), then wait up to `STOP_WAIT` for
    them to exit; name each process still running then."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        # macOS answers EPERM for a group that holds only zombies.
        os.killpg(proc.pid, STOP_SIGNAL)
    deadline = time.monotonic() + STOP_WAIT
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=max(0.0, deadline - time.monotonic()))
    for stream in (proc.stdout, proc.stderr):
        if stream is not None:
            stream.close()
    while (left := _group(proc.pid)) and time.monotonic() < deadline:
        time.sleep(0.05)
    if not left:
        return ''
    return f'; still running {STOP_WAIT} s after it was stopped: ' + ', '.join(f'pid {pid} ({command})' for pid, command in left)


def _step(hdiutil: tuple[str, ...], verb: str, bound: float, *args: str) -> tuple[str | None, bytes]:
    """Run one `hdiutil` verb as the leader of a process group of its own, up to `bound` seconds.

    It returns (None, its output) when it succeeded. A step that runs past its bound, or exits
    with a failure, is stopped with everything it started, and the failure text names the verb and
    how it ended (the bound, or the exit status and the tail of its standard error).
    """
    proc = REAL_POPEN([*hdiutil, verb, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=bound)
    except subprocess.TimeoutExpired:
        return f'{verb}: ran past its bound of {bound} s and was stopped' + _stop(proc), b''
    if proc.returncode != 0:
        left = _stop(proc)
        return f'{verb}: exited with status {proc.returncode}: {err.decode(errors="replace")[-400:].strip()}' + left, out
    return None, out


def _clean_up(hdiutil: tuple[str, ...], bound: dict[str, float], image: Path) -> list[str]:
    """After a `create` or `attach` that failed or hung: detach every device backed by `image`, then
    remove it. It returns what is left to report, in order: nothing when all went.

    The devices are the ones `hdiutil info` lists for the image (by real path; `hdiutil` reports the
    path as it was handed over), each detached by its whole disk. When `info` fails or answers with
    no listing, nothing is removed. When a detach fails, there is no further attempt: the device
    and the image are kept and named.
    """
    failure, out = _step(hdiutil, 'info', bound['info'], '-plist')
    listing: Any = None
    if failure is None:
        try:
            listing = plistlib.loads(out)
        except Exception as exc:
            failure = f'info: answered with no listing ({type(exc).__name__}: {exc})'
        else:
            if not isinstance(listing, dict):
                failure = f'info: answered with no listing ({type(listing).__name__})'
    if failure is not None:
        return [failure, f'the image is kept at {image}, and any device made from it stays attached']
    for entry in listing.get('images', []):
        if os.path.realpath(entry.get('image-path', '')) != os.path.realpath(image):
            continue
        entities = entry.get('system-entities', [])
        devices = [e['dev-entry'] for e in entities if 'dev-entry' in e]
        if not devices:
            continue
        device = min(devices, key=len)
        failure, _ = _step(hdiutil, 'detach', bound['detach'], '-force', device)
        if failure is not None:
            mounts = [e['mount-point'] for e in entities if e.get('mount-point')]
            at = f' at {mounts[0]}' if mounts else ', not mounted'
            return [failure, f'{device} stays attached{at}, and its image is kept at {image}']
    image.unlink(missing_ok=True)
    return []


@contextlib.contextmanager
def attached_image(where: Path, hdiutil: tuple[str, ...] = ('hdiutil',),
                   bounds: dict[str, float] | None = None) -> Iterator[Path]:
    """A 4 MB HFS+ image beside `where`, attached at `where` (macOS); detached and removed afterwards.

    `hdiutil` is the argv that runs the tool (a stand-in's, in the rows that pin this). Every step
    runs through `_step`. A `create` or `attach` that fails or hangs raises `HostFailure` naming it,
    then what `_clean_up` left. After the body the volume is detached, once: a detach that fails
    raises its failure and names the volume and the image it keeps (caused by the body's exception,
    when the body raised), and one that succeeds removes the image, then raises an exception from the
    body unchanged.
    """
    bound = _bounds(bounds)
    image = where.parent / f'{where.name}.dmg'
    failure, _ = _step(hdiutil, 'create', bound['create'], '-size', '4m', '-fs', 'HFS+', '-volname', 'cluster-mcp-full',
                       str(image))
    if failure is None:
        where.mkdir()
        failure, _ = _step(hdiutil, 'attach', bound['attach'], '-nobrowse', '-noautoopen', '-mountpoint', str(where),
                           str(image))
    if failure is not None:
        raise HostFailure('\n'.join([failure, *_clean_up(hdiutil, bound, image)]))
    left = f'the volume stays attached at {where}, and its image is kept at {image}'
    try:
        yield where
    except BaseException as body:
        failure, _ = _step(hdiutil, 'detach', bound['detach'], '-force', str(where))
        if failure is not None:
            raise HostFailure(f'{failure}\n{left}') from body
        image.unlink()
        raise
    failure, _ = _step(hdiutil, 'detach', bound['detach'], '-force', str(where))
    if failure is not None:
        raise HostFailure(f'{failure}\n{left}')
    image.unlink()


@contextlib.contextmanager
def full_volume(where: Path, free: int) -> Iterator[Path]:
    """A 4 MB HFS+ volume attached at `where` (macOS), filled until `free` bytes are left; detached
    and its image removed afterwards."""
    with attached_image(where):
        room = os.statvfs(where)
        with open(where / 'filler', 'wb') as filler:
            filler.write(b'\0' * (room.f_bavail * room.f_frsize - free))
        room = os.statvfs(where)
        assert room.f_bavail * room.f_frsize == free, f'the volume has {room.f_bavail * room.f_frsize} bytes free'
        yield where


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


# The stand-in that plays `hdiutil` in the rows below, run through bin/sandbox.sh.
HDIUTIL_STANDIN = Path(__file__).resolve().parent / 'hdiutil_standin.py'
# The bound a hanging stand-in verb meets, in seconds (the stand-in reaches its hang in ~25 ms).
SHORT_BOUND = 1
# The bound every other stand-in verb gets, in seconds: never met.
EASY_BOUND = 30
# A row's whole run, at most, in seconds.
ROW_LIMIT = 10
PAST = f'ran past its bound of {SHORT_BOUND} s and was stopped'
# Every failing and every hanging plan starts a child, so the stop is pinned whichever way a step ends.
FAILS = {'end': 'fail', 'child': True}
HANGS = {'end': 'hang', 'child': True}
# What a failing stand-in step says last, as `hdiutil` does.
STANDIN_FAILURE = 'failed - stand-in failure'
BODY_FAILURE = 'the body failed'
# What a row's report says of what a failed detach leaves (`{where}` and `{image}` are the row's).
STAYS = 'the volume stays attached at {where}, and its image is kept at {image}'
KEPT_DEVICE = '/dev/standin2 stays attached at {where}, and its image is kept at {image}'

DISK_IMAGE_ROWS = {
    # (each verb's plans, whether the body raises, the row's own devices left, whether the image is
    #  left, what is raised: None, 'body' (the body's own exception) or 'failure', and the texts the
    #  report carries, in order)
    'create-hangs': ({'create': [HANGS]}, False, 0, False, 'failure', [f'create: {PAST}']),
    'create-fails': ({'create': [FAILS]}, False, 0, False, 'failure',
                     ['create: exited with status 1: ', f'create {STANDIN_FAILURE}']),
    'every-step-succeeds': ({}, False, 0, False, None, []),
    'body-fails': ({}, True, 0, False, 'body', [BODY_FAILURE]),
    'create-hangs-with-device': ({'create': [{**HANGS, 'image': True, 'device': True}]}, False, 0, False, 'failure',
                                 [f'create: {PAST}']),
    'create-fails-with-device': ({'create': [{**FAILS, 'image': True, 'device': True}]}, False, 0, False, 'failure',
                                 ['create: exited with status 1: ', f'create {STANDIN_FAILURE}']),
    'attach-hangs': ({'attach': [HANGS]}, False, 0, False, 'failure', [f'attach: {PAST}']),
    'attach-hangs-with-device': ({'attach': [{**HANGS, 'device': True}]}, False, 0, False, 'failure',
                                 [f'attach: {PAST}']),
    'attach-fails': ({'attach': [FAILS]}, False, 0, False, 'failure',
                     ['attach: exited with status 1: ', f'attach {STANDIN_FAILURE}']),
    'attach-fails-with-device': ({'attach': [{**FAILS, 'device': True}]}, False, 0, False, 'failure',
                                 ['attach: exited with status 1: ', f'attach {STANDIN_FAILURE}']),
    'detach-hangs': ({'detach': [HANGS]}, False, 1, True, 'failure', [f'detach: {PAST}', STAYS]),
    'detach-fails': ({'detach': [FAILS]}, False, 1, True, 'failure',
                     ['detach: exited with status 1: ', f'detach {STANDIN_FAILURE}', STAYS]),
    'body-and-detach-fail': ({'detach': [FAILS]}, True, 1, True, 'failure',
                             [BODY_FAILURE, 'detach: exited with status 1: ', f'detach {STANDIN_FAILURE}', STAYS]),
    'cleanup-detach-hangs': ({'attach': [{**HANGS, 'device': True}], 'detach': [HANGS]}, False, 1, True, 'failure',
                             [f'attach: {PAST}', f'detach: {PAST}', KEPT_DEVICE]),
    'cleanup-detach-fails': ({'attach': [{**FAILS, 'device': True}], 'detach': [FAILS]}, False, 1, True, 'failure',
                             ['attach: exited with status 1: ', 'detach: exited with status 1: ',
                              f'detach {STANDIN_FAILURE}', KEPT_DEVICE]),
    'info-fails-in-cleanup': ({'attach': [{**FAILS, 'device': True}], 'info': [FAILS]}, False, 1, True, 'failure',
                              ['attach: exited with status 1: ', 'info: exited with status 1: ', f'info {STANDIN_FAILURE}',
                               'the image is kept at {image}, and any device made from it stays attached']),
    'info-answers-garbled': ({'attach': [{**FAILS, 'device': True}], 'info': [{'garbled': True}]}, False, 1, True,
                             'failure', ['attach: exited with status 1: ', 'info: answered with no listing (',
                                         'the image is kept at {image}, and any device made from it stays attached']),
}

# A device no row made, from an image of the same name in another directory: no cleanup may touch it.
FOREIGN = '/dev/standin1'


def _stand_in(tmp_path: Path, plan: dict[str, list[dict[str, Any]]]) -> Path:
    """The stand-in's state directory for one row: its plan, and the foreign device already attached."""
    state = tmp_path / 'hdiutil-state'
    state.mkdir()
    (state / 'plan.json').write_text(json.dumps(plan))
    elsewhere = tmp_path / 'elsewhere'
    (state / 'devices.json').write_text(json.dumps([{'dev-entry': FOREIGN, 'image-path': str(elsewhere / 'vol.dmg'),
                                                      'mount-point': str(elsewhere / 'vol')}]))
    (state / 'pids').write_text('')
    return state


def _standin_devices(state: Path) -> list[dict[str, Any]]:
    return json.loads((state / 'devices.json').read_text())


def _left_running(state: Path) -> list[tuple[int, str]]:
    """Every process still running whose command names the stand-in's state, as (pid, command)."""
    return [(pid, command) for pid, _, status, command in _processes()
            if str(state) in command and not status.startswith('Z')]


def _kill_recorded(state: Path) -> None:
    """KILL what the stand-in started that is still running (never a pid reused since)."""
    for pid, _ in _left_running(state):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGKILL)


def _drive_image(state: Path, where: Path, plan: dict[str, list[dict[str, Any]]],
                 body_raises: bool) -> tuple[BaseException | None, BaseException | None, list[str]]:
    """Run `attached_image` against the stand-in: (what it raised, what the body raised, the
    mount points the body saw)."""
    hdiutil = (str(SANDBOX), sys.executable, '-I', str(HDIUTIL_STANDIN), str(state))
    bounds = {verb: SHORT_BOUND if any(p.get('end') == 'hang' for p in plan.get(verb, [])) else EASY_BOUND
              for verb in HDIUTIL_VERBS}
    body: BaseException | None = None
    seen: list[str] = []
    try:
        with attached_image(where, hdiutil, bounds) as at:
            seen = [d['mount-point'] for d in _standin_devices(state) if d['mount-point'] == str(at)]
            if body_raises:
                body = AssertionError(BODY_FAILURE)
                raise body
    except Exception as exc:
        return exc, body, seen
    return None, body, seen


def _hangs_reached(state: Path, plan: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Each verb whose planned hangs the stand-in did not all reach (a hang's child is recorded)."""
    recorded = [line.split()[1:] for line in (state / 'pids').read_text().splitlines()]
    return [verb for verb, plans in plan.items()
            if recorded.count(['child', verb, 'hang']) != sum(1 for p in plans if p.get('end') == 'hang')]


@pytest.mark.integration
@pytest.mark.parametrize('row', list(DISK_IMAGE_ROWS))
def test_a_disk_image_step_that_fails_or_hangs_leaves_nothing_running(row: str, tmp_path: Path,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """However an `hdiutil` step ends, nothing it started still runs, and the failure names the step.

    A stand-in plays `hdiutil` through bin/sandbox.sh (no disk image, on every platform): a step that
    hangs meets a short bound, and one that fails exits 1; each starts a child that runs until it is
    killed. When the fixture has returned or raised, no stand-in process is left, the row's own
    devices and image are as expected, a device it did not make is untouched, and the report names
    each step that went wrong and how, in order, and names no survivor. No TERM is sent before the
    KILL, the row ends within its limit, and the stand-in reached each hang it was planned to.
    """
    plan, body_raises, devices_left, image_left, outcome, texts = DISK_IMAGE_ROWS[row]
    # bin/sandbox.sh makes its directory under TMPDIR: under the row's, it goes with the row.
    monkeypatch.setenv('TMPDIR', str(tmp_path))
    state = _stand_in(tmp_path, plan)
    where, image = tmp_path / 'vol', tmp_path / 'vol.dmg'
    says = [text.format(where=where, image=image) for text in texts]
    try:
        started = time.monotonic()
        raised, body, seen = _drive_image(state, where, plan, body_raises)
        took = time.monotonic() - started
        violations = []
        if _left_running(state):
            violations.append(f'still running after the fixture: {_left_running(state)!r}')
        unreached = _hangs_reached(state, plan)
        if unreached:
            violations.append(f'the stand-in did not reach its planned hang of {unreached} within {SHORT_BOUND} s '
                              f'(a host too loaded to start it?)')
        listed = _standin_devices(state)
        own = [d for d in listed if d['dev-entry'] != FOREIGN]
        if len(own) != devices_left:
            violations.append(f'{len(own)} of its own devices left attached, not {devices_left}: {own!r}')
        if not any(d['dev-entry'] == FOREIGN for d in listed):
            violations.append(f'the device {FOREIGN} it did not make was detached')
        if image.exists() != image_left:
            violations.append(f'the image {"was left" if image.exists() else "is gone"}: {image}')
        terms = [line for line in (state / 'pids').read_text().splitlines() if line.startswith('term ')]
        if terms:
            violations.append(f'a stand-in process was sent TERM: {terms!r}')
        if took >= ROW_LIMIT:
            violations.append(f'the row took {took:.1f} s, past its limit of {ROW_LIMIT} s')
        body_runs = not any(p.get('end') in ('fail', 'hang') for verb in ('create', 'attach') for p in plan.get(verb, [])[:1])
        if bool(seen) != body_runs:
            violations.append(f'the body ran with a device at {where}: {bool(seen)}; it should have: {body_runs}')
        report = ''.join(traceback.format_exception(raised)) if raised is not None else ''
        if outcome is None and raised is not None:
            violations.append(f'raised although every step succeeded: {report}')
        elif outcome == 'body' and (raised is not body or raised.__cause__ is not None):
            violations.append(f'the body\'s own failure was not raised unchanged: {report or "nothing raised"}')
        elif outcome == 'failure' and not isinstance(raised, HostFailure):
            violations.append(f'raised no HostFailure: {report or "nothing raised"}')
        elif outcome == 'failure' and body_raises and (body is None or raised.__cause__ is not body):
            violations.append(f'the failure is not caused by the body\'s own: {report}')
        at = 0
        for text in says:
            found = report.find(text, at)
            if found < 0:
                violations.append(f'the report does not carry {text!r} (in order, after offset {at}): {report}')
                break
            at = found + len(text)
        if 'still running' in report:
            violations.append(f'the report names a survivor where none was left: {report}')
        assert violations == [], f'{row}:\n' + '\n'.join(violations)
    finally:
        _kill_recorded(state)


@pytest.mark.integration
def test_a_stopped_step_still_running_is_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stopped step whose processes outlive the wait after the stop is named, pid and command, and
    the wait is bounded.

    No process outlives KILL portably, so the stop here is CONT (which ends nothing) and the wait
    0.5 s: `create` hangs past its bound with its child, and both are still running when it ends.
    """
    monkeypatch.setattr(sys.modules[__name__], 'STOP_SIGNAL', signal.SIGCONT)
    monkeypatch.setattr(sys.modules[__name__], 'STOP_WAIT', 0.5)
    monkeypatch.setenv('TMPDIR', str(tmp_path))
    plan = {'create': [HANGS]}
    state = _stand_in(tmp_path, plan)
    try:
        started = time.monotonic()
        raised, _, _ = _drive_image(state, tmp_path / 'vol', plan, False)
        took = time.monotonic() - started
        report = ''.join(traceback.format_exception(raised)) if raised is not None else 'nothing raised'
        recorded = [line.split() for line in (state / 'pids').read_text().splitlines()]
        pids = [int(line[0]) for line in recorded if line[1:3] in (['step', 'create'], ['child', 'create'])]
        violations = []
        if len(pids) != 2:
            violations.append(f'the stand-in recorded {recorded!r}, not a step and its child')
        if f'create: {PAST}; still running 0.5 s after it was stopped: ' not in report:
            violations.append(f'the report does not say what is still running: {report}')
        for pid in pids:
            if not re.search(rf'pid {pid} \([^)]*{re.escape(str(HDIUTIL_STANDIN))} {re.escape(str(state))} create', report):
                violations.append(f'pid {pid} is not named with its command: {report}')
        if not SHORT_BOUND + 0.5 <= took < SHORT_BOUND + 3.5:
            violations.append(f'the run took {took:.2f} s, outside [{SHORT_BOUND + 0.5}, {SHORT_BOUND + 3.5})')
        assert violations == [], '\n'.join(violations)
    finally:
        _kill_recorded(state)


@pytest.mark.unit
def test_the_disk_image_figures() -> None:
    """Each real `hdiutil` step's bound is 120 s; a stopped step is KILLed at once, its group then
    waited on for 5 s; a hanging stand-in meets a bound of 1 s."""
    assert _bounds(None) == {'create': 120, 'attach': 120, 'detach': 120, 'info': 120}
    assert STOP_WAIT == 5
    assert STOP_SIGNAL is signal.SIGKILL
    assert SHORT_BOUND == 1


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
    dependencies = tomllib.loads((root / 'packages' / 'cluster-mcp' / 'pyproject.toml').read_text())['project']['dependencies']
    floors = [re.fullmatch(r'paramiko\s*>=\s*([0-9.]+)\s*(,.*)?', dependency) for dependency in dependencies]
    found = [match.group(1) for match in floors if match]
    assert len(found) == 1, f'packages/cluster-mcp/pyproject.toml declares no one paramiko floor: {dependencies}'
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


def lost_write_violations(outcome: Any, cause: str) -> list[str]:
    """Every way `outcome` is not a write whose own command could not reconnect: a `ConnectionError`
    naming the host, saying the transfer may be partly made, the target unchanged, and the cause."""
    text = str(outcome)
    said = (f'the connection to {LOOPBACK} was lost during the write; the transfer may be partly made',
            'is unchanged', f'cannot connect to {LOOPBACK}: {cause}')
    if not isinstance(outcome, ConnectionError) or not all(part in text for part in said):
        return [f'the write gave {outcome!r:.400}, not a lost transfer saying {said}']
    return []


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
    else:
        # The session had opened: a write whose own command cannot reconnect may be partly made.
        violations += lost_write_violations(outcome, 'connection refused')
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
        try:
            outcome: Any = executor.write('~/x', b'content\n')
        except OSError as exc:
            outcome = exc
        spent = clock.elapsed()
    finally:
        executor.close()
    violations = []
    if not (met and any(ssh.VERIFY in str(part) for part in met[0])):
        violations.append(f'the first command the write ran was {met!r:.300}, not its placing program')
    violations += lost_write_violations(outcome, 'timed out')
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
@pytest.mark.parametrize('uri', CONTEXT_URIS, ids=scheme)
def test_a_reconnect_failure_never_changes_the_cluster_context(uri: str, rig: ReconnectRig, guard) -> None:
    """The site context is the startup read, so a `-1002` from another tool never reaches what
    `cluster_context` and the context resource serve, under either URI, and neither read starts a
    connect attempt."""
    executor = rig.executor(['ok', (0, refused)])
    # Room for a window on each of the five calls, so a read that does reconnect fails the row by its
    # text, not by running away.
    rig.clock.rebase(6 * RECONNECT_BOUND)

    async def scenario() -> tuple[list[Outcome], Outcome, int, list[Outcome]]:
        async with in_memory(shared_server(executor, site=RECONNECT_SITE)) as client:
            before = [await call(client, 'cluster_context', {}), await read_resource(client, uri)]
            built = len(rig.built)
            failed = await call(client, 'run_command', {'command': 'true'})
            after = [await call(client, 'cluster_context', {}), await read_resource(client, uri)]
            return before, failed, built, after

    before, failed, built, after = drive(scenario(), timeout=WATCHDOG)
    violations = []
    if built:
        violations.append(f'reading the cluster context started {built} connect attempts')
    if failed.is_error or _command_result(failed).get('exit_code') != NOT_STARTED_EXIT_CODE:
        violations.append(f'run_command gave {failed!r:.400}, not {NOT_STARTED_EXIT_CODE}')
    for when, outcomes in (('before', before), ('after', after)):
        for read, outcome in zip(('cluster_context', uri), outcomes):
            if outcome.is_error or outcome.text != RECONNECT_SITE.text:
                violations.append(f'{read} {when} a failed reconnect served {outcome!r:.400}, '
                                  f'not the startup read {RECONNECT_SITE.text!r}')
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


# ---------------------------------------------------------------------------------------------
# A link that dies silently (`SilentLink`): no reset comes, so the connection still reads as
# connected. A call that starts on it reconnects, or fails as a failed reconnect does; a command
# running on it ends as lost; a call beside a stalled one ends too; and nothing that is merely quiet
# is cut. Every row runs under a 2 s connect bound (a 6 s reconnect bound), its call on a thread under
# a watchdog that counts from the moment the link went silent: its figure plus `SILENT_SLACK`.

# The connect bound the silent rows patch in, and the reconnect bound it gives.
SILENT_BOUND = 2
SILENT_WINDOW = ssh.RECONNECT_FACTOR * SILENT_BOUND
# Real seconds past a row's figure before its watchdog fails it, and that a thread gets to end.
SILENT_SLACK = 1.0
THREAD_END = 2.0
# The threads a connection's liveness monitor runs.
MONITOR_THREADS = ('cluster-mcp-liveness', 'cluster-mcp-probe')
# What the rows read and list, and the text a call that cannot reconnect names.
SILENT_DATA = 'what the silent rows read\n'
GONE = f'cannot connect to {LOOPBACK}: timed out'
# How long after its exec request arrives a row's command is taken to be running.
RUNNING = 0.3
# The command a quiet row runs: silent for longer than the reconnect bound, then one word.
QUIET_COMMAND = f'sleep {SILENT_WINDOW + 1}; printf %s done'
EVERY_KIND = os.environ.get('CLUSTER_MCP_TEST_EVERY_KIND') == '1'
# The slow link: its rate each way, and the output that takes longer than the reconnect bound on it.
SLOW_RATE = 32 * 1024
SLOW_BYTES = 256 * 1024
# Real seconds a quiet row's command may take, at most.
QUIET_FIGURE = 4 * SILENT_WINDOW
# How long the silent spell lasts: past a call's verdict, inside a background probe's.
SPELL = SILENT_BOUND + 0.5


class Silenced:
    """One silent row's loopback server, its silent link and its executor (through the link)."""

    def __init__(self, server: LoopbackSSH, link: SilentLink, executor: SSHExecutor) -> None:
        self.server, self.link, self.executor = server, link, executor

    @property
    def home(self) -> Path:
        return Path(self.server.home)

    @property
    def local(self) -> Path:
        """The server's own side of a transfer: where an upload is read from, a download written."""
        return self.home.parent / 'local'

    def go_silent(self) -> float:
        """Make the link silent; return when it went (real seconds)."""
        self.link.go_silent()
        return self.link.silenced or _REAL_MONOTONIC()


@pytest.fixture
def silenced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Silenced]]:
    """Start a loopback server behind a silent link under a 2 s connect bound, and an executor
    through it; stop them after. A liveness thread's exception fails the row."""
    monkeypatch.setattr(ssh, 'CONNECT_TIMEOUT', SILENT_BOUND)
    broken: list[str] = []
    hook = threading.excepthook

    def caught(args: Any) -> None:
        if args.thread is not None and args.thread.name in MONITOR_THREADS:
            broken.append(f'{args.thread.name}: {args.exc_type.__name__}: {args.exc_value}')
        hook(args)

    monkeypatch.setattr(threading, 'excepthook', caught)
    made: list[Silenced] = []

    def start(rate: int | None = None) -> Silenced:
        home = (tmp_path / 'home').resolve()
        home.mkdir(exist_ok=True)
        argv_echo.install(home, 'sbatch')
        (home / 'job.sh').write_text('#!/bin/bash\necho hi\n')
        (home / 'data.txt').write_text(SILENT_DATA)
        (home / 'listed').mkdir(exist_ok=True)
        (home / 'listed' / 'entry').write_text('')
        (home.parent / 'local').mkdir(exist_ok=True)
        (home.parent / 'local' / 'upload.txt').write_text(SILENT_DATA)
        server = LoopbackSSH(home, '/bin/bash', tmp_path)
        link = SilentLink(server, rate=rate)
        try:
            executor = link.executor()
        except BaseException:
            link.close()
            server.close()
            raise
        made.append(Silenced(server, link, executor))
        return made[-1]

    try:
        yield start
    finally:
        for each in made:
            each.executor.close()
            each.link.close()
            each.server.close()
    assert broken == [], f'a liveness thread raised: {broken}'


class Watched:
    """A call on a thread of its own, started now, and when it ended."""

    def __init__(self, call: Callable[[], Any]) -> None:
        self.got: list[Any] = []
        self.ended: float | None = None
        self.thread = threading.Thread(target=self._calling, args=(call,), daemon=True)
        self.thread.start()

    def _calling(self, call: Callable[[], Any]) -> None:
        try:
            self.got.append(call())
        except BaseException as exc:
            self.got.append(exc)
        self.ended = _REAL_MONOTONIC()

    def result(self, link: SilentLink, figure: float, since: float) -> tuple[Any, float]:
        """The call's outcome, and when it ended in seconds after `since`, the moment the link went
        silent. A call still running `figure` + `SILENT_SLACK` s after `since` fails the row, naming
        the step the link went silent at, and is then released by cutting the link."""
        self.thread.join(max(0.0, since + figure + SILENT_SLACK - _REAL_MONOTONIC()))
        if self.thread.is_alive():
            waited = _REAL_MONOTONIC() - since
            link.close()
            self.thread.join(THREAD_END)
            at = f' at {link.step}' if link.step else ''
            pytest.fail(f'still waiting {waited:.1f} s after the link went silent{at}, allowed {figure} s and '
                        f'{SILENT_SLACK} s of slack')
        if isinstance(self.got[0], BaseException):
            raise self.got[0]
        assert self.ended is not None
        return self.got[0], self.ended - since


def _silent_tool(executor: SSHExecutor, tool: str, local: Path | None = None) -> Callable[[], Any]:
    """The call a silent row makes for `tool`: `run` or `write` itself, or the tool through an
    in-process server, its local paths in `local`."""
    if tool == 'run':
        return lambda: executor.run(RECOVERY_COMMAND)
    if tool == 'write':
        return lambda: executor.write('~/written.txt', SILENT_DATA.encode())
    name, given = SILENT_TOOLS[tool]
    args = {key: value.replace('{local}', str(local)) for key, value in given.items()}
    return lambda: _tool(executor, name, args)


# Each tool a silent row calls through an in-process server, and what it is given.
SILENT_TOOLS: dict[str, tuple[str, dict[str, str]]] = {
    'run_command': ('run_command', {'command': 'printf %s back'}),
    'sbatch-path': ('sbatch', {'script_path': '~/job.sh'}),
    'read_file': ('read_file', {'path': '~/data.txt'}),
    'list_directory': ('list_directory', {'path': '~/listed'}),
    'write_file': ('write_file', {'path': '~/written.txt', 'content': SILENT_DATA}),
    'upload_file': ('upload_file', {'local_path': '{local}/upload.txt', 'remote_path': '~/uploaded.txt'}),
    'download_file': ('download_file', {'remote_path': '~/data.txt', 'local_path': '{local}/downloaded.txt'}),
    'sbatch-content': ('sbatch', {'script_content': '#!/bin/bash\necho hi\n'}),
}
SILENT_COMMAND_TOOLS = ['run', 'run_command', 'sbatch-path', 'read_file', 'list_directory']
SILENT_TRANSFER_TOOLS = ['write_file', 'upload_file', 'download_file', 'sbatch-content']


def _completed_violations(tool: str, outcome: Any, rig: Silenced | None = None) -> list[str]:
    """Every way `outcome` is not `tool`'s call run to its end (its files in `rig`'s trees)."""
    if tool == 'run':
        ok = _same(outcome) == ('back|again', '', 0)
    elif tool in ('write', 'write_file'):
        ok = (getattr(outcome, 'exit_code', None) == 0 if tool == 'write' else not outcome.is_error)
        ok = ok and rig is not None and (rig.home / 'written.txt').read_text() == SILENT_DATA
    elif tool == 'upload_file':
        ok = not outcome.is_error and rig is not None and (rig.home / 'uploaded.txt').read_text() == SILENT_DATA
    elif tool == 'download_file':
        ok = not outcome.is_error and rig is not None and (rig.local / 'downloaded.txt').read_text() == SILENT_DATA
    elif tool == 'run_command':
        ok = not outcome.is_error and _command_result(outcome).get('stdout') == 'back'
    elif tool in ('sbatch-path', 'sbatch-content'):
        ok = not outcome.is_error and outcome.text.strip() == argv_echo.JOB_ID
    elif tool == 'read_file':
        ok = not outcome.is_error and outcome.text == SILENT_DATA
    else:
        # The listing runs GNU `ls`; where the host's `ls` is BSD's (macOS) it refuses the options, and
        # that refusal, the remote program's own, shows the call ran there all the same.
        ran = 'entry' in outcome.text or 'Failed to list directory: ls: ' in outcome.text
        ok = ran and (not outcome.is_error or 'Failed to list directory: ls: ' in outcome.text)
    return [] if ok else [f'{tool} gave {outcome!r:.400}, not its call run to its end']


def _not_run_violations(tool: str, outcome: Any, took: float = 0.0, window: float = SILENT_WINDOW) -> list[str]:
    """Every way `outcome` is not `tool`'s report of a call that could not reconnect, naming the host,
    within the reconnect bound `window` (and `RECONNECT_SLACK`) of the call's start, `took` seconds
    before."""
    if tool == 'run':
        return not_run_violations(outcome, 'timed out', took, window, host=LOOPBACK)
    if took > window + RECONNECT_SLACK:
        return [f'{tool} gave up {took:.1f} s after it began, past its {window} s bound']
    if tool == 'run_command':
        got = _command_result(outcome)
        ok = (not outcome.is_error and got.get('exit_code') == NOT_STARTED_EXIT_CODE
              and str(got.get('stderr')).startswith(f'cluster-mcp: {GONE}'))
    else:
        said = {'sbatch-path': 'The job was not submitted', 'sbatch-content': 'The job was not submitted',
                'upload_file': 'nothing was transferred', 'download_file': 'nothing was transferred'}
        ok = outcome.is_error and GONE in outcome.text and said.get(tool, 'the command was not run') in outcome.text
        ok = ok and 'may have been submitted' not in outcome.text
    return [] if ok else [f'{tool} read as {outcome!r:.400}: it must say {GONE!r} and that nothing was run']


@pytest.mark.integration
@pytest.mark.parametrize('tool', [*SILENT_COMMAND_TOOLS, *SILENT_TRANSFER_TOOLS] if EVERY_KIND
                         else ['run', 'run_command', 'write_file'])
def test_a_call_on_a_silent_link_reconnects(tool: str, silenced: Callable[..., Silenced], executes: Any) -> None:
    rig = silenced()
    since = rig.go_silent()
    rig.link.come_back()
    outcome, took = Watched(_silent_tool(rig.executor, tool, rig.local)).result(rig.link, SILENT_BOUND, since)
    violations = _completed_violations(tool, outcome, rig)
    fresh = [round(at - since, 2) for at in rig.link.opened[1:]]
    if not (len(fresh) == 1 and 0 <= fresh[0] <= SILENT_BOUND + SILENT_SLACK):
        violations.append(f'new connections were made {fresh} s after the call began, not one within '
                          f'{SILENT_BOUND + SILENT_SLACK} s')
    assert violations == [], f'{tool} (ended {took:.2f} s after the link went silent):\n' + '\n'.join(violations)


@pytest.mark.integration
@pytest.mark.parametrize('tool', [*SILENT_COMMAND_TOOLS, *SILENT_TRANSFER_TOOLS])
def test_a_call_on_a_silent_link_to_a_gone_host_is_not_run(tool: str, silenced: Callable[..., Silenced],
                                                           executes: Any) -> None:
    rig = silenced()
    since = rig.go_silent()
    outcome, took = Watched(_silent_tool(rig.executor, tool, rig.local)).result(rig.link, SILENT_WINDOW, since)
    violations = _not_run_violations(tool, outcome, took)
    if rig.server.received:
        violations.append(f'the server received {rig.server.received!r:.300}, so something ran')
    if rig.link.held < 1:
        violations.append('no reconnect attempt reached the gone host, so none was made')
    if argv_echo.calls(rig.home):
        violations.append('sbatch ran')
    written = [name for name in ('written.txt', 'uploaded.txt') if (rig.home / name).exists()]
    written += ['downloaded.txt'] if (rig.local / 'downloaded.txt').exists() else []
    if written:
        violations.append(f'a call that was not run left {written}')
    assert violations == [], f'{tool} (ended {took:.2f} s after the link went silent):\n' + '\n'.join(violations)


@pytest.mark.integration
@pytest.mark.parametrize('opens', ['run', 'sftp'])
def test_a_channel_open_outlasting_its_own_timeout_on_a_silent_link_reconnects(
        opens: str, silenced: Callable[..., Silenced], monkeypatch: pytest.MonkeyPatch) -> None:
    # The open's own timeout comes before the call's verdict, and before `SETTLE` after it: the open
    # waits past the verdict, so the call reconnects rather than raise Paramiko's timeout.
    rig = silenced()
    monkeypatch.setattr(ssh, 'OPEN_TIMEOUT', (SILENT_BOUND - ssh.SETTLE) / 2)
    since = rig.go_silent()
    rig.link.come_back()
    call = 'run' if opens == 'run' else 'write'
    outcome, took = Watched(_silent_tool(rig.executor, call)).result(rig.link, SILENT_BOUND, since)
    violations = _completed_violations(call, outcome, rig)
    if len(rig.link.opened) != 2:
        violations.append(f'the server was reached by {len(rig.link.opened)} connections, not a new one')
    assert violations == [], f'{opens} (ended {took:.2f} s after the link went silent):\n' + '\n'.join(violations)


@pytest.mark.integration
def test_a_reconnect_onto_a_link_that_goes_silent_still_ends_in_time(silenced: Callable[..., Silenced]) -> None:
    rig = silenced()
    since = rig.go_silent()
    rig.link.come_back()
    rig.link.silent_after_handshake = True
    outcome, took = Watched(_silent_tool(rig.executor, 'run')).result(rig.link, SILENT_WINDOW, since)
    violations = _not_run_violations('run', outcome)
    if len(rig.link.opened) != 2 or rig.link.step != 'handshake':
        violations.append(f'{len(rig.link.opened)} connections were made and the link went silent at '
                          f'{rig.link.step}, not one reconnect that went silent once made')
    if rig.server.received:
        violations.append(f'the server received {rig.server.received!r:.300}, so something ran')
    assert violations == [], f'ended {took:.2f} s after the link went silent:\n' + '\n'.join(violations)


# A late reconnect: the host comes back just before the call's last start, so the reconnect lands
# within `FINAL_ATTEMPT_LEAD` of the call's deadline. Under a 3 s connect bound an open after it that
# waited for its own verdict would end a second past the 9 s bound (at 2 s, never past the slack), so
# the silent rows take that bound. `LATE_RETURN` is how long before the last start the host returns.
LATE_BOUND = 3
LATE_WINDOW = ssh.RECONNECT_FACTOR * LATE_BOUND
LATE_RETURN = 0.2
# The tools a late row calls; with `CLUSTER_MCP_TEST_EVERY_KIND=1` every tool, and a write whose new
# link goes silent at its SFTP subsystem or version step.
LATE_TOOLS = [*SILENT_COMMAND_TOOLS, *SILENT_TRANSFER_TOOLS, 'write_file-subsystem', 'write_file-version'] \
    if EVERY_KIND else ['run', 'write_file']


def _late(rig: Silenced, window: float, call: Callable[[], Any]) -> tuple[Watched, float]:
    """Start `call` on `rig`'s silent link with the host down, and bring the host back `LATE_RETURN` s
    before the call's last start; the call, and when it began."""
    rig.go_silent()
    rig.server.refuse()
    rig.link.come_back()
    began = _REAL_MONOTONIC()
    watched = Watched(call)
    _REAL_SLEEP(max(0.0, began + window - ssh.FINAL_ATTEMPT_LEAD - LATE_RETURN - _REAL_MONOTONIC()))
    rig.server.serve_again()
    return watched, began


def _late_violations(rig: Silenced, began: float, window: float) -> list[str]:
    """Every way the call's reconnect on `rig` was not one late connection, made after the host came
    back and with less than a connect bound of its window left, so the row tests what it names."""
    late = [round(at - began, 2) for at in rig.link.opened[1:]]
    if len(late) != 1 or late[0] < window - ssh.FINAL_ATTEMPT_LEAD - LATE_RETURN:
        return [f'the reconnects landed {late} s after the call began, not one at its last start '
                f'({window - ssh.FINAL_ATTEMPT_LEAD} s)']
    return []


@pytest.mark.integration
@pytest.mark.parametrize('tool', LATE_TOOLS)
def test_a_late_reconnect_onto_a_link_that_goes_silent_again_ends_in_time(
        tool: str, silenced: Callable[..., Silenced], executes: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # The open after the reconnect is cut at the call's deadline, not left to its own verdict.
    monkeypatch.setattr(ssh, 'CONNECT_TIMEOUT', LATE_BOUND)
    rig = silenced()
    called, _, step = tool.rpartition('-') if tool.endswith(('-subsystem', '-version')) else (tool, '', '')
    # Only the new connection reaches the server: the first stays silent, so its requests never do.
    if step:
        rig.link.silent_at(step)
    else:
        rig.link.silent_after_handshake = True
    watched, began = _late(rig, LATE_WINDOW, _silent_tool(rig.executor, called, rig.local))
    # The watchdog only stops a hang: an open left to its own verdict ends a bound past the window.
    outcome, took = watched.result(rig.link, LATE_WINDOW + LATE_BOUND, began)
    violations = _not_run_violations(called, outcome, took, LATE_WINDOW) + _late_violations(rig, began, LATE_WINDOW)
    if rig.link.step != (step or 'handshake'):
        violations.append(f'the new link went silent at {rig.link.step}, not at {step or "its handshake"}')
    if rig.server.received:
        violations.append(f'the server received {rig.server.received!r:.300}, so something ran')
    assert violations == [], f'{tool} (ended {took:.2f} s after it began):\n' + '\n'.join(violations)


@pytest.mark.integration
@pytest.mark.parametrize('tool', ['run', 'write_file'])
def test_a_late_reconnect_onto_a_live_link_runs_the_call(tool: str, silenced: Callable[..., Silenced],
                                                         executes: Any) -> None:
    # The reconnect lands with under a connect bound of the window left: the open there still runs.
    rig = silenced()
    watched, began = _late(rig, SILENT_WINDOW, _silent_tool(rig.executor, tool, rig.local))
    outcome, took = watched.result(rig.link, SILENT_WINDOW, began)
    violations = _completed_violations(tool, outcome, rig) + _late_violations(rig, began, SILENT_WINDOW)
    assert violations == [], f'{tool} (ended {took:.2f} s after it began):\n' + '\n'.join(violations)


# A write's own command after a late reconnect: the write's session opens on the new link, which goes
# silent at the channel open of the write's parent's `mkdir` or of its place step, the second channel
# the server sees on it. That command takes the write's connection as found live, so its open waits
# for its own verdict, B after it began, past the write's deadline; the write is a lost transfer,
# the target unchanged, within the bound after the silence. Only with `CLUSTER_MCP_TEST_EVERY_KIND=1`.
if EVERY_KIND:
    @pytest.mark.integration
    @pytest.mark.parametrize('command', ['mkdir', 'place'])
    def test_a_write_cut_at_its_own_command_after_a_late_reconnect_is_a_lost_transfer(
            command: str, silenced: Callable[..., Silenced], executes: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ssh, 'CONNECT_TIMEOUT', LATE_BOUND)
        rig = silenced()
        target = rig.home / ('new/x.txt' if command == 'mkdir' else 'x.txt')
        if command == 'place':
            target.write_text(BEFORE)
        earlier = list(rig.server._transports)
        hook = rig.server.on_step
        channels: list[str] = []

        def at_step(step: str, detail: str, transport: Any) -> None:
            if step == 'channel' and transport not in earlier:
                channels.append(detail)
                if len(channels) == 2:
                    rig.link.step = command
                    rig.link.go_silent()
                    return
            if hook is not None:
                hook(step, detail, transport)

        rig.server.on_step = at_step
        parent = '~/new' if command == 'mkdir' else None

        def calling() -> list[Any]:
            # The raise a lost transfer gives is its outcome, so it comes back as a value.
            try:
                return [rig.executor.write('~/new/x.txt' if parent else '~/x.txt', SILENT_DATA.encode(), parent=parent)]
            except OSError as exc:
                return [exc]

        watched, began = _late(rig, LATE_WINDOW, calling)
        since = _silent_at(rig.link, command)
        (outcome,), took = watched.result(rig.link, 3 * LATE_BOUND, since)
        text = str(outcome)
        violations = _late_violations(rig, began, LATE_WINDOW)
        if not (isinstance(outcome, ConnectionError) and LOST_DURING in text and PARTLY in text
                and 'is unchanged' in text):
            violations.append(f'gave {outcome!r:.400}, not a lost transfer saying the target is unchanged')
        if (target.read_text() != BEFORE) if command == 'place' else target.exists():
            violations.append('the target changed')
        if not LATE_BOUND - RECONNECT_SLACK <= took <= 3 * LATE_BOUND + RECONNECT_SLACK:
            violations.append(f'ended {took:.2f} s after the silence, not once its open\'s own verdict came '
                              f'({LATE_BOUND} s) and within the bound after it ({3 * LATE_BOUND} s)')
        if rig.server.received:
            violations.append(f'the server received {rig.server.received!r:.300}, so something ran')
        assert violations == [], (f'{command} (ended {took:.2f} s after the silence, '
                                  f'{since + took - began:.2f} s after the write began):\n' + '\n'.join(violations))


def _running(server: LoopbackSSH, count: int = 1) -> None:
    """Wait until `count` exec requests have reached `server`, and then `RUNNING` more."""
    limit = _REAL_MONOTONIC() + DROP_SEEN
    while len(server.received) < count:
        if _REAL_MONOTONIC() > limit:
            raise AssertionError(f'no exec request reached the server within {DROP_SEEN} s')
        _REAL_SLEEP(0.01)
    _REAL_SLEEP(RUNNING)


def _silent_at(link: SilentLink, step: str) -> float:
    """Wait until `link` has gone silent at the server's `step`; return when it went (real seconds)."""
    limit = _REAL_MONOTONIC() + DROP_SEEN
    while link.step != step:
        if _REAL_MONOTONIC() > limit:
            raise AssertionError(f'the link did not go silent at {step} within {DROP_SEEN} s')
        _REAL_SLEEP(0.01)
    assert link.silenced is not None
    return link.silenced


@pytest.mark.integration
@pytest.mark.parametrize('tool', ['run', 'sbatch-path'])
def test_a_command_cut_by_a_silent_link_is_never_run_twice(tool: str, silenced: Callable[..., Silenced],
                                                           executes: Any) -> None:
    # The host is reachable again before the verdict: the command may have run, so it is reported
    # lost and never sent again.
    rig = silenced()
    call = (lambda: rig.executor.run(['sh', '-c', 'touch -- "$HOME/ran"; sleep 30'])) if tool == 'run' \
        else _silent_tool(rig.executor, tool)
    rig.link.silent_at('exec')
    watched = Watched(call)
    since = _silent_at(rig.link, 'exec')
    rig.link.come_back()
    outcome, took = watched.result(rig.link, SILENT_WINDOW, since)
    violations = []
    if tool == 'run':
        if (outcome.exit_code, outcome.stderr.endswith(LOST_NOTE)) != (CONNECTION_LOST_EXIT_CODE, True):
            violations.append(f'the command cut short gave {outcome!r}, not {CONNECTION_LOST_EXIT_CODE} with {LOST_NOTE!r}')
        if not (rig.home / 'ran').exists():
            violations.append('the command never ran, so the row proves nothing')
    elif not outcome.is_error or 'may have been submitted' not in outcome.text:
        violations.append(f'the submission cut short read as {outcome!r:.300}: it must say the job may have been '
                          'submitted')
    if len(rig.server.received) != 1 or (tool == 'sbatch-path' and len(argv_echo.calls(rig.home)) != 1):
        violations.append(f'the command reached the server {len(rig.server.received)} times '
                          f'(sbatch ran {len(argv_echo.calls(rig.home))}), not once')
    assert violations == [], f'{tool} (ended {took:.2f} s after the link went silent):\n' + '\n'.join(violations)


@pytest.mark.integration
def test_an_idle_connection_is_not_taken_for_a_silent_link(silenced: Callable[..., Silenced]) -> None:
    rig = silenced()
    _REAL_SLEEP(SILENT_WINDOW + SILENT_SLACK)
    began = _REAL_MONOTONIC()
    outcome, took = Watched(_silent_tool(rig.executor, 'run')).result(rig.link, SILENT_BOUND, began)
    violations = _completed_violations('run', outcome)
    if len(rig.link.opened) != 1:
        violations.append(f'{len(rig.link.opened)} connections were made: an idle live connection was taken for dead')
    assert violations == [], f'ended {took:.2f} s after it began:\n' + '\n'.join(violations)


@pytest.mark.integration
@pytest.mark.parametrize('timed', ['no-timeout', 'later-timeout'])
def test_a_command_on_a_link_that_goes_silent_is_lost(timed: str, silenced: Callable[..., Silenced]) -> None:
    rig = silenced()
    # A timeout that outlasts the row's watchdog, so a call that never notices the link waits it out.
    timeout = None if timed == 'no-timeout' else SILENT_WINDOW + SILENT_SLACK + 3
    watched = Watched(lambda: rig.executor.run(['sleep', '30'], timeout=timeout))
    _running(rig.server)
    since = rig.go_silent()
    outcome, took = watched.result(rig.link, SILENT_WINDOW, since)
    assert (outcome.exit_code, outcome.stderr.endswith(LOST_NOTE)) == (CONNECTION_LOST_EXIT_CODE, True), \
        (f'{timed}: a command on a link that went silent gave {outcome!r} {took:.2f} s later, not '
         f'{CONNECTION_LOST_EXIT_CODE} with {LOST_NOTE!r}')


@pytest.mark.integration
def test_a_command_on_a_link_that_goes_silent_ends_at_its_timeout(silenced: Callable[..., Silenced]) -> None:
    # Its timeout comes before the link is noticed dead: it is a timeout, as on a live link.
    rig = silenced()
    timeout = 1.0
    watched = Watched(lambda: rig.executor.run(['sleep', '30'], timeout=timeout))
    _running(rig.server)
    since = rig.go_silent()
    outcome, took = watched.result(rig.link, timeout + launch.GRACE, since)
    assert outcome.exit_code == TIMEOUT_EXIT_CODE, \
        f'a command whose timeout came first gave {outcome!r} {took:.2f} s after the link went silent, not a timeout'


@pytest.mark.integration
@pytest.mark.parametrize('link', ['quiet', 'slow-link'])
def test_a_quiet_command_is_not_taken_for_a_silent_link(link: str, silenced: Callable[..., Silenced]) -> None:
    # Quiet: nothing printed for longer than the reconnect bound. Slow: the output trickles in through
    # a slow link for longer than that, so every probe's reply queues behind it, as behind sshd.
    rig = silenced(rate=None if link == 'quiet' else SLOW_RATE)
    command = QUIET_COMMAND if link == 'quiet' else f'head -c {SLOW_BYTES} /dev/zero | tr "\\0" z'
    expected = 'done' if link == 'quiet' else 'z' * SLOW_BYTES
    began = _REAL_MONOTONIC()
    outcome, took = Watched(lambda: rig.executor.run(command)).result(rig.link, QUIET_FIGURE, began)
    violations = []
    if (outcome.stdout == expected, outcome.stderr, outcome.exit_code) != (True, '', 0):
        violations.append(f'gave {len(outcome.stdout)} bytes, {outcome.stderr!r}, exit {outcome.exit_code}: '
                          'not the whole result')
    if len(rig.link.opened) != 1:
        violations.append(f'{len(rig.link.opened)} connections were made: a quiet live link was taken for dead')
    if took < SILENT_WINDOW:
        violations.append(f'it took {took:.1f} s, not longer than the {SILENT_WINDOW} s bound, so it proves nothing')
    assert violations == [], f'{link} (ended {took:.2f} s after it began):\n' + '\n'.join(violations)


@pytest.mark.integration
def test_a_quiet_command_rides_out_a_silent_spell_shorter_than_its_verdict(silenced: Callable[..., Silenced]) -> None:
    # The link goes silent as a background probe arrives and comes back `SPELL` later, held bytes and
    # all: past a call's verdict, inside the background probe's, so the quiet command runs on.
    rig = silenced()
    assert SILENT_BOUND < SPELL < 2 * SILENT_BOUND - ssh.VERDICT_MARGIN
    watched = Watched(lambda: rig.executor.run(QUIET_COMMAND))
    _running(rig.server)
    rig.link.silent_at('probe', ssh.PROBE_REQUEST)
    limit = _REAL_MONOTONIC() + 2 * SILENT_BOUND
    while rig.link.step != 'probe':
        assert _REAL_MONOTONIC() < limit, f'no background probe arrived within {2 * SILENT_BOUND} s'
        _REAL_SLEEP(0.01)
    since = rig.link.silenced or _REAL_MONOTONIC()
    _REAL_SLEEP(max(0.0, since + SPELL - _REAL_MONOTONIC()))
    rig.link.resume()
    outcome, took = watched.result(rig.link, QUIET_FIGURE, since)
    violations = []
    if _same(outcome) != ('done', '', 0):
        violations.append(f'the quiet command gave {outcome!r}, not its result')
    if len(rig.link.opened) != 1:
        violations.append(f'{len(rig.link.opened)} connections were made: a {SPELL} s silent spell was taken for dead')
    assert violations == [], f'ended {took:.2f} s after the spell began:\n' + '\n'.join(violations)


@pytest.mark.integration
def test_a_call_beside_a_command_on_a_silent_link_ends_in_time(silenced: Callable[..., Silenced]) -> None:
    # The new call's verdict ends the stalled command too, at once.
    rig = silenced()
    stalled = Watched(lambda: rig.executor.run(['sleep', '30']))
    _running(rig.server)
    rig.go_silent()
    rig.link.come_back()
    began = _REAL_MONOTONIC()
    outcome, took = Watched(_silent_tool(rig.executor, 'run')).result(rig.link, SILENT_BOUND, began)
    cut, cut_took = stalled.result(rig.link, SILENT_BOUND, began)
    violations = _completed_violations('run', outcome)
    if (cut.exit_code, cut.stderr.endswith(LOST_NOTE)) != (CONNECTION_LOST_EXIT_CODE, True):
        violations.append(f'the stalled command gave {cut!r}, not {CONNECTION_LOST_EXIT_CODE}')
    assert violations == [], (f'the new call ended {took:.2f} s and the stalled one {cut_took:.2f} s after the new '
                              'call began:\n' + '\n'.join(violations))


# When the link answers again after a call starts beside quiet work: within that call's verdict (B
# after its start), or past it and still inside a background probe's (2B less the margin), which
# the work would ride out alone. The quiet command outlasts both.
ANSWERS = {'answered': SILENT_BOUND / 2, 'unanswered': SILENT_BOUND + 0.8}
BESIDE_COMMAND = 'sleep 4; printf %s done'


def _answer_beside(rig: Silenced, answer: str, since: float) -> tuple[Any, float]:
    """Start a call beside the quiet work as the link went silent at `since`, the host reachable
    again for a new connection; let the held connection answer `ANSWERS[answer]` s later; return the
    call's outcome and when it ended, after `since`."""
    assert ANSWERS['answered'] < SILENT_BOUND < ANSWERS['unanswered'] < 2 * SILENT_BOUND - ssh.VERDICT_MARGIN
    rig.link.come_back()
    call = Watched(_silent_tool(rig.executor, 'run'))
    _REAL_SLEEP(max(0.0, since + ANSWERS[answer] - _REAL_MONOTONIC()))
    rig.link.resume()
    return call.result(rig.link, SILENT_WINDOW, since)


@pytest.mark.integration
@pytest.mark.parametrize('answer', list(ANSWERS))
def test_a_quiet_command_beside_a_starting_call_has_that_calls_verdict(answer: str,
                                                                        silenced: Callable[..., Silenced]) -> None:
    # A call that starts while the link is silent judges it B after its start, and that verdict
    # covers the quiet command already running: an answer within it keeps both on the connection,
    # one past it ends the command as lost, though the command alone would ride it out.
    rig = silenced()
    quiet = Watched(lambda: rig.executor.run(BESIDE_COMMAND))
    _running(rig.server)
    since = rig.go_silent()
    outcome, took = _answer_beside(rig, answer, since)
    kept, kept_took = quiet.result(rig.link, QUIET_FIGURE, since)
    violations = _completed_violations('run', outcome)
    if answer == 'answered':
        if _same(kept) != ('done', '', 0):
            violations.append(f'the quiet command gave {kept!r}, not its result')
        if len(rig.link.opened) != 1:
            violations.append(f'{len(rig.link.opened)} connections were made: an answer within the verdict was missed')
    else:
        if (kept.exit_code, kept.stderr.endswith(LOST_NOTE)) != (CONNECTION_LOST_EXIT_CODE, True):
            violations.append(f'the quiet command gave {kept!r}, not {CONNECTION_LOST_EXIT_CODE}')
        if kept_took > SILENT_BOUND + SILENT_SLACK:
            violations.append(f'the quiet command was lost {kept_took:.2f} s after the silence, not at the call\'s verdict')
        if len(rig.link.opened) != 2:
            violations.append(f'{len(rig.link.opened)} connections were made, not one new one')
    assert violations == [], (f'{answer}: the call ended {took:.2f} s and the quiet command {kept_took:.2f} s after '
                              'the silence:\n' + '\n'.join(violations))


@pytest.mark.integration
@pytest.mark.parametrize('step', ['channel', 'subsystem', 'version'])
def test_an_sftp_open_cut_by_a_silent_link_reconnects(step: str, silenced: Callable[..., Silenced]) -> None:
    # The link goes silent at one step of a write's SFTP session open, the host back at once: no file
    # operation has gone, so the write reconnects and lands whole.
    rig = silenced()
    rig.link.silent_at(step)
    watched = Watched(_silent_tool(rig.executor, 'write'))
    since = _silent_at(rig.link, step)
    rig.link.come_back()
    outcome, took = watched.result(rig.link, SILENT_BOUND, since)
    violations = _completed_violations('write', outcome, rig)
    if len(rig.link.opened) != 2:
        violations.append(f'{len(rig.link.opened)} connections were made, not one new one')
    assert violations == [], f'{step} (ended {took:.2f} s after the link went silent):\n' + '\n'.join(violations)


# What the target held before a transfer cut short: a cut write must leave it as it was.
BEFORE = 'the target before the transfer\n'
# A transfer too large to finish on what the hop forwarded before it went silent.
LARGE = 4 * 1024 * 1024
LOST_DURING = f'the connection to {LOOPBACK} was lost during the'
PARTLY = 'the transfer may be partly made'

# Each transfer a silent link cuts: the server step it goes silent at (an exec's by what its program
# runs), what that step is called, and whether the host is back at once.
CUT_TRANSFERS: dict[str, tuple[str, str | None, str, bool]] = {
    'put': ('upload', None, 'upload', False),
    'get': ('download', None, 'download', False),
    'write-lookup': ('lookup', None, 'lookup', False),
    'write-stage': ('stage', None, 'stage', False),
    'write-upload': ('upload', None, 'upload', False),
    'write-mkdir': ('exec', 'mkdir -p --', 'mkdir', False),
    'write-place': ('exec', 'cksum', 'place', True),
    'write-place-gone': ('exec', 'cksum', 'place', False),
    'sbatch': ('upload', None, 'upload', False),
}


def _staging_named(text: str) -> str | None:
    """The staging directory a lost write's message names, if any."""
    found = re.search(r'its staging directory (\S+) may remain', text)
    return found.group(1) if found else None


@pytest.mark.integration
@pytest.mark.parametrize('shape', list(CUT_TRANSFERS))
def test_a_transfer_on_a_link_that_goes_silent_may_be_partly_made(shape: str, silenced: Callable[..., Silenced],
                                                                  executes: Any) -> None:
    rig = silenced()
    step, detail, named, back = CUT_TRANSFERS[shape]
    target = rig.home / ('new/x.txt' if shape == 'write-mkdir' else 'x.txt')
    if shape != 'write-mkdir':
        target.write_text(BEFORE)
    # A large upload or download outlasts what the hop forwarded; a write's content need not.
    data = _numbered(LARGE if shape in ('put', 'get') else 64 * 1024)
    local = rig.local / 'big.bin'
    if shape == 'put':
        local.write_bytes(data)
        call: Callable[[], Any] = lambda: rig.executor.put(str(local), '~/x.txt')
    elif shape == 'get':
        (rig.home / 'big.bin').write_bytes(data)
        local.write_text(BEFORE)
        call = lambda: rig.executor.get('~/big.bin', str(local))
    elif shape == 'sbatch':
        call = lambda: _tool(rig.executor, 'sbatch', {'script_content': '#!/bin/bash\n' + 'echo hi\n' * 1000})
    else:
        parent = '~/new' if shape == 'write-mkdir' else None
        path = '~/new/x.txt' if parent else '~/x.txt'
        call = lambda: rig.executor.write(path, data, parent=parent)
    rig.link.silent_at(step, detail, named)

    def calling() -> list[Any]:
        # The raise a lost transfer gives is its outcome, so it comes back as a value.
        try:
            return [call()]
        except OSError as exc:
            return [exc]

    watched = Watched(calling)
    since = _silent_at(rig.link, named)
    if back:
        rig.link.come_back()
    (outcome,), took = watched.result(rig.link, SILENT_WINDOW, since)
    text = outcome.text if shape == 'sbatch' else str(outcome)
    violations = []
    lost = shape == 'sbatch' or isinstance(outcome, ConnectionError)
    if not (lost and LOST_DURING in text and PARTLY in text):
        violations.append(f'gave {outcome!r:.500}, not a lost transfer naming the host and saying {PARTLY!r}')
    if shape == 'put' and not (target.exists() and target.stat().st_size < LARGE and 'x.txt' in text):
        violations.append('the upload says the target may be truncated, but it is whole or gone')
    if shape == 'get' and not (local.exists() and local.stat().st_size < LARGE and str(local) in text):
        violations.append(f'the download names {str(local)!r} as partly made, but it is whole or gone, or unnamed')
    if shape.startswith('write'):
        staging = _staging_named(text)
        if shape == 'write-mkdir':
            if target.exists() or 'is unchanged' not in text:
                violations.append('a write cut at its parent mkdir changed the target, or said it might have')
        elif shape.startswith('write-place'):
            if target.read_text() not in (BEFORE, data.decode()):
                violations.append('a write cut at its place step left the target neither old nor new')
            if 'is either the old file or the new one' not in text:
                violations.append('a write cut at its place step does not say the target is old or new')
        elif target.read_text() != BEFORE or 'is unchanged' not in text:
            violations.append('a write cut while staging changed the target, or did not say it is unchanged')
        if shape in ('write-stage', 'write-upload', 'write-place', 'write-place-gone') and not (
                staging and _staging_left(rig.home)):
            violations.append(f'the staging directory left was not named ({staging}) or is not there '
                              f'({_staging_left(rig.home)})')
    if shape == 'sbatch':
        if not outcome.is_error or 'Failed to write job script' not in text or argv_echo.calls(rig.home):
            violations.append('sbatch, its script cut short, must say the script failed and submit nothing')
    assert violations == [], f'{shape} (ended {took:.2f} s after the link went silent):\n' + '\n'.join(violations)


# A slow transfer: its size, past the reconnect bound at the slow hop's rate.
SLOW_TRANSFER = 7 * SLOW_RATE


@pytest.mark.integration
@pytest.mark.parametrize('shape', ['put', 'get', 'write'])
def test_a_slow_transfer_is_not_taken_for_a_silent_link(shape: str, silenced: Callable[..., Silenced]) -> None:
    # Each reply arrives a write or a read at a time through the slow hop, never a bound apart.
    rig = silenced(rate=SLOW_RATE)
    data = _numbered(SLOW_TRANSFER)
    local, remote = rig.local / 'slow.bin', rig.home / 'slow.bin'
    (local if shape == 'put' else remote).write_bytes(data)
    calls: dict[str, Callable[[], Any]] = {
        'put': lambda: rig.executor.put(str(local), '~/slow.bin'),
        'get': lambda: rig.executor.get('~/slow.bin', str(local)),
        'write': lambda: rig.executor.write('~/slow.bin', data),
    }
    began = _REAL_MONOTONIC()
    outcome, took = Watched(calls[shape]).result(rig.link, QUIET_FIGURE, began)
    landed = (remote if shape != 'get' else local).read_bytes()
    violations = []
    if landed != data or (shape == 'write' and outcome.exit_code != 0):
        violations.append(f'{len(landed)} of {len(data)} bytes landed, {outcome!r:.200}: not the whole transfer')
    if len(rig.link.opened) != 1:
        violations.append(f'{len(rig.link.opened)} connections were made: a slow live transfer was taken for dead')
    if took < SILENT_WINDOW:
        violations.append(f'it took {took:.1f} s, not longer than the {SILENT_WINDOW} s bound, so it proves nothing')
    assert violations == [], f'{shape} (ended {took:.2f} s after it began):\n' + '\n'.join(violations)


@pytest.mark.integration
@pytest.mark.parametrize('answer', list(ANSWERS))
def test_a_slow_transfer_beside_a_starting_call_has_that_calls_verdict(answer: str,
                                                                        silenced: Callable[..., Silenced]) -> None:
    # An upload whose replies stop coming as it writes, while a call starts: an answer within that
    # call's verdict lands the upload whole beside it on the connection; one past it cuts the upload,
    # which alone would wait out a background probe's verdict.
    rig = silenced()
    data = _numbered(LARGE)
    local = rig.local / 'big.bin'
    local.write_bytes(data)
    rig.link.silent_at('upload')
    upload = Watched(lambda: rig.executor.put(str(local), '~/big.bin'))
    since = _silent_at(rig.link, 'upload')
    outcome, took = _answer_beside(rig, answer, since)
    try:
        moved, moved_took = upload.result(rig.link, QUIET_FIGURE, since)
    except OSError as exc:
        moved, moved_took = exc, _REAL_MONOTONIC() - since
    violations = _completed_violations('run', outcome)
    landed = (rig.home / 'big.bin').read_bytes() if (rig.home / 'big.bin').exists() else b''
    if answer == 'answered':
        if isinstance(moved, BaseException) or landed != data:
            violations.append(f'the upload gave {moved!r:.300} with {len(landed)} of {len(data)} bytes, not the whole file')
        if len(rig.link.opened) != 1:
            violations.append(f'{len(rig.link.opened)} connections were made: an answer within the verdict was missed')
    else:
        if not (isinstance(moved, ConnectionError) and PARTLY in str(moved)):
            violations.append(f'the upload gave {moved!r:.300}, not a lost transfer')
        if moved_took > SILENT_BOUND + SILENT_SLACK:
            violations.append(f'the upload was cut {moved_took:.2f} s after the silence, not at the call\'s verdict')
        if len(rig.link.opened) != 2:
            violations.append(f'{len(rig.link.opened)} connections were made, not one new one')
    assert violations == [], (f'{answer}: the call ended {took:.2f} s and the upload {moved_took:.2f} s after the '
                              'silence:\n' + '\n'.join(violations))


# How long a helper's send on the held write path must still be blocked to show it held, and how
# long the upload has, from the moment the link went silent, to fill what the path can take.
HELD = 0.5
HELD_WITHIN = 3.0


def _stall_an_upload(rig: Silenced) -> tuple[Watched, float]:
    """Start a 4 MiB upload that goes silent at its first write, and return once it holds the
    connection's write path (a send on it still blocked `HELD` s later), with when the link went
    silent. A path not held within `HELD_WITHIN` s fails the row, never skips it."""
    local = rig.local / 'big.bin'
    local.write_bytes(_numbered(LARGE))
    transport = rig.executor._conn.transport
    # What the held path can take before a send blocks: the client's send buffer and the hop's
    # receive buffer, each doubled at most by the kernel, set rather than autotuned. The upload is
    # far larger, and the channel's window too, so the send blocks on the socket, never the window.
    holds = 2 * (SEND_BUFFER + RECEIVE_BUFFER)
    assert 4 * holds < WINDOW < LARGE, (holds, WINDOW, LARGE)
    narrow_sends(transport.sock)
    rig.link.silent_at('upload')
    stalled = Watched(lambda: rig.executor.put(str(local), '~/big.bin'))
    since = _silent_at(rig.link, 'upload')

    def ignore() -> None:
        with contextlib.suppress(Exception):
            transport.send_ignore()

    # The upload goes on filling the path after the link goes silent: a send that returns found room
    # still, and the next is tried, until one stays blocked or the upload has had its time.
    filled = _REAL_MONOTONIC() + HELD_WITHIN
    while True:
        probe = threading.Thread(target=ignore, daemon=True)
        probe.start()
        probe.join(HELD)
        if probe.is_alive():
            return stalled, since
        if _REAL_MONOTONIC() > filled:
            rig.link.close()
            pytest.fail(f'the write path was not held: a send on it still returned within {HELD} s, '
                        f'{HELD_WITHIN} s after the link went silent, so the row proves nothing')


@pytest.mark.integration
def test_a_call_beside_a_transfer_stalled_on_a_silent_link_ends_in_time(silenced: Callable[..., Silenced]) -> None:
    # An upload holds the connection's write path on the silent link, so every other sender queues
    # behind it: the new call's verdict, counted from its hand-over, still comes, and ends both.
    rig = silenced()
    stalled, _ = _stall_an_upload(rig)
    rig.link.come_back()
    began = _REAL_MONOTONIC()
    outcome, took = Watched(_silent_tool(rig.executor, 'run')).result(rig.link, SILENT_BOUND, began)
    try:
        cut, cut_took = stalled.result(rig.link, SILENT_BOUND, began)
    except OSError as exc:
        cut, cut_took = exc, _REAL_MONOTONIC() - began
    violations = _completed_violations('run', outcome)
    if not (isinstance(cut, ConnectionError) and PARTLY in str(cut)):
        violations.append(f'the stalled upload gave {cut!r:.300}, not a lost transfer')
    assert violations == [], (f'the new call ended {took:.2f} s and the upload {cut_took:.2f} s after the new call '
                              'began:\n' + '\n'.join(violations))


# The connect bound of the row whose command times out beside a stalled upload: long enough that the
# connection's verdict (a background probe's, B after the silence and 2B less the margin after that)
# comes well after the command's own timeout, which comes once the upload holds the write path.
STALL_BOUND = 3
STALL_TIMEOUT = 3.0


@pytest.mark.integration
def test_a_timed_command_beside_a_transfer_stalled_on_a_silent_link_ends_at_its_timeout(
        silenced: Callable[..., Silenced], monkeypatch: pytest.MonkeyPatch) -> None:
    # The upload holds the write path until the verdict. The command's own timeout comes first, and
    # nothing the call sends then (its TERM, its KILL, its close) waits on that path: it returns at
    # its timeout, after its `GRACE` read.
    monkeypatch.setattr(ssh, 'CONNECT_TIMEOUT', STALL_BOUND)
    rig = silenced()
    began = _REAL_MONOTONIC()
    timed = Watched(lambda: rig.executor.run(['sleep', '30'], timeout=STALL_TIMEOUT))
    _running(rig.server)
    _, since = _stall_an_upload(rig)
    deadline = began + STALL_TIMEOUT
    verdict = since + 3 * STALL_BOUND - ssh.VERDICT_MARGIN
    assert _REAL_MONOTONIC() < deadline < deadline + launch.GRACE + SILENT_SLACK < verdict, \
        f'the upload held the path {_REAL_MONOTONIC() - began:.2f} s after the command began, past its timeout'
    outcome, took = timed.result(rig.link, deadline + launch.GRACE - since, since)
    assert outcome.exit_code == TIMEOUT_EXIT_CODE, \
        f'the timed command gave {outcome!r} {took:.2f} s after the silence, not a timeout'


# The command a timed call runs beside a held write path: output past the window's adjust threshold,
# then a TERM handler that prints more than the channel's window as it stops, then a wait that only a
# signal ends. What it prints as it stops is read whole only while the window adjusts its reads owe
# go out during the `GRACE` read.
BIG_OUTPUT = 600_000
STOP_OUTPUT = 2_500_000
STOPPING = (f"head -c {BIG_OUTPUT} /dev/zero | tr '\\0' z; "
            f"trap 'head -c {STOP_OUTPUT} /dev/zero | tr \"\\0\" y; exit 0' TERM; while :; do sleep 0.05; done")
HELD_TIMEOUT = 1.0


@pytest.mark.integration
@pytest.mark.parametrize('path', ['held', 'free'])
def test_a_timed_call_never_waits_on_a_write_path_another_call_holds(path: str, serve: Callable[..., LoopbackSSH],
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    # Held: another sender takes the connection's write path (`clear_to_send_lock`) as the exec
    # request is answered, before the end of stdin, and keeps it past the call's timeout. The call
    # returns at its timeout with all it read, owing the server its end of stdin, the window's
    # adjust, the TERM, the KILL and the close; once the path is free the TERM still reaches the
    # command, and the KILL `GRACE` after it, the command's stop held up by its unread output. Free:
    # the TERM reaches the command at the deadline, all it prints as it stops is read, and it ends
    # before any KILL.
    assert STOP_OUTPUT > WINDOW
    server = serve('/bin/bash')
    executor = server.executor()
    asked: list[tuple[str, float]] = []
    deliver = server.deliver

    def delivering(channel: paramiko.Channel, name: str) -> bool:
        asked.append((name, time.monotonic()))
        return deliver(channel, name)

    monkeypatch.setattr(server, 'deliver', delivering)
    holding, release = threading.Event(), threading.Event()
    answered = paramiko.Channel.exec_command

    def hold(lock: Any) -> None:
        with lock:
            holding.set()
            release.wait(30)

    def exec_command(chan: paramiko.Channel, command: str) -> None:
        answered(chan, command)
        threading.Thread(target=hold, args=(chan.transport.clear_to_send_lock,), daemon=True).start()
        assert holding.wait(5), 'the write path was not taken'

    if path == 'held':
        monkeypatch.setattr(paramiko.Channel, 'exec_command', exec_command)
    got: list[Any] = []

    def calling() -> None:
        try:
            got.append(executor.run(STOPPING, timeout=HELD_TIMEOUT))
        except BaseException as exc:
            got.append(exc)

    call = threading.Thread(target=calling, daemon=True)
    try:
        began = time.monotonic()
        call.start()
        call.join(HELD_TIMEOUT + launch.GRACE + SILENT_SLACK)
        took = time.monotonic() - began
        release.set()
        if call.is_alive():
            call.join(THREAD_END)
            pytest.fail(f'{path}: still waiting {took:.1f} s after the call began, its timeout {HELD_TIMEOUT} s, '
                        f'allowed {launch.GRACE} s of grace and {SILENT_SLACK} s of slack')
        if isinstance(got[0], BaseException):
            raise got[0]
        result = got[0]
        names = ['TERM', 'KILL'] if path == 'held' else ['TERM']
        until = time.monotonic() + DROP_SEEN
        while len(asked) < len(names) and time.monotonic() < until:
            time.sleep(0.02)
        # Room for a KILL that should not come.
        time.sleep(0 if path == 'held' else launch.GRACE + 0.5)
        stopped = '' if path == 'held' else 'y' * STOP_OUTPUT
        violations = []
        if (result.stdout == 'z' * BIG_OUTPUT + stopped, result.exit_code) != (True, TIMEOUT_EXIT_CODE):
            violations.append(f'gave {len(result.stdout)} bytes ending {result.stdout[-20:]!r}, exit '
                              f'{result.exit_code}: not all it printed, as a timeout')
        if [name for name, _ in asked] != names:
            violations.append(f'the command was asked for {[name for name, _ in asked]}, not {names}')
        elif path == 'held' and asked[1][1] - asked[0][1] < launch.GRACE - 0.05:
            violations.append(f'the KILL came {asked[1][1] - asked[0][1]:.2f} s after the late TERM, inside its '
                              f'{launch.GRACE:g} s grace')
        assert violations == [], f'{path} (returned {took:.2f} s after it began):\n' + '\n'.join(violations)
    finally:
        release.set()
        executor.close()


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
    sends = ssh._Sends(channel)
    try:
        out, err, code, _ = ssh._collect(channel, 0.3, sends=sends)
        sends.wait(None)
    finally:
        channel.release()
    assert [name for name, _ in sent] == ['TERM'] and sent[0][1] < 0.5, sent
    assert (out, code) == (b'stopping\n', TIMEOUT_EXIT_CODE), \
        f'the timeout lost what followed the TERM: {out!r}, exit code {code}'


@pytest.mark.unit
def test_a_timeout_asks_for_kill_after_its_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    # The command neither prints nor ends after the TERM, as one whose launch ignored TERM from its
    # entry: the read waits out GRACE, and only then is the command asked to KILL.
    channel = LateChannel(60.0, b'')
    sent: list[tuple[str, float]] = []
    monkeypatch.setattr(ssh, '_signal', lambda chan, name: sent.append((name, channel.now())))
    sends = ssh._Sends(channel)
    try:
        out, err, code, _ = ssh._collect(channel, 0.3, sends=sends)
        sends.wait(None)
    finally:
        channel.release()
    assert [name for name, _ in sent] == ['TERM', 'KILL'], \
        f'a timeout asked for {[name for name, _ in sent]}, not TERM and then KILL'
    waited = sent[1][1] - sent[0][1]
    assert waited >= launch.GRACE - 0.05, \
        f'the KILL was asked for {waited:.2f} s after the TERM, before the GRACE read was over ({launch.GRACE:g} s)'
    assert (out, err, code) == (b'', b'', TIMEOUT_EXIT_CODE), (out, err, code)


def _session(server: LoopbackSSH, executor: SSHExecutor, wire: str) -> paramiko.Channel:
    """A channel of `executor`'s connection running `wire`, its process started by the server."""
    assert executor.run('true', timeout=30).exit_code == 0
    started = len(server.processes)
    chan = executor._conn.client.get_transport().open_session(timeout=30)
    chan.exec_command(wire)
    until = time.monotonic() + 10
    while len(server.processes) == started and time.monotonic() < until:
        time.sleep(0.02)
    return chan


@pytest.mark.integration
def test_no_signal_is_asked_for_on_a_closed_channel(serve: Callable[..., LoopbackSSH]) -> None:
    # A channel both sides have closed, the server's copy freed: the server drops the connection for
    # a request on it, as sshd does ("unknown channel"), so none may go, and the next call runs on the
    # same connection.
    server = serve('/bin/bash')
    executor = server.executor()
    try:
        chan = _session(server, executor, 'exit 0')
        until = time.monotonic() + 10
        while (not chan.closed or server._transports[0]._channels.values()) and time.monotonic() < until:
            time.sleep(0.02)
        assert chan.closed and not server._transports[0]._channels.values(), 'the channel did not close on both sides'
        ssh._signal(chan, 'KILL')
        try:
            again: object = executor.run('echo again', timeout=30)
        except Exception as exc:
            again = exc
        found = (getattr(again, 'stdout', None), getattr(again, 'exit_code', None), len(server._transports))
        assert found == ('again\n', 0, 1), \
            f'a signal request went on a closed channel and the connection was lost: {again!r}, ' \
            f'{len(server._transports)} connections'
    finally:
        executor.close()


@pytest.mark.integration
def test_a_signal_request_goes_while_the_channel_is_held_open(serve: Callable[..., LoopbackSSH],
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    # Paramiko marks a channel closed before it sends its own close, and sends that close through the
    # connection's write path: a request checked and written holding that path (`clear_to_send_lock`),
    # the channel open, is on the wire before any close can be. The channel's own lock is not held.
    server = serve('/bin/bash')
    executor = server.executor()
    try:
        chan = _session(server, executor, 'exec /bin/sleep 30')
        transport = chan.transport
        send, seen = transport._send_message, []

        def watched(data: paramiko.Message) -> None:
            m = paramiko.Message(data.asbytes())
            if (m.get_byte(), m.get_int(), m.get_text()) == (paramiko.common.cMSG_CHANNEL_REQUEST, chan.remote_chanid,
                                                            'signal'):
                seen.append((transport.clear_to_send_lock.locked(), chan.lock.locked(), chan.closed))
            send(data)

        monkeypatch.setattr(transport, '_send_message', watched)
        ssh._signal(chan, 'TERM')
        until = time.monotonic() + 10
        while not chan.closed and time.monotonic() < until:
            time.sleep(0.02)
        assert seen == [(True, False, False)], \
            ('the signal request was not written holding the write path alone on an open channel: '
             f'(path held, channel locked, closed) {seen}')
        assert server.signals == ['TERM'] and chan.closed, \
            f'the server did not end the command on the request: {server.signals}, closed {chan.closed}'
    finally:
        executor.close()


class _KeyExchange(threading.Event):
    """A transport's `clear_to_send` during a key exchange: clear until the exchange ends (`set`). Each
    wait records whether the channel's lock was held while it waited."""

    def __init__(self, lock: Any) -> None:
        super().__init__()
        self.lock, self.held = lock, []

    def wait(self, timeout: float | None = None) -> bool:
        self.held.append(self.lock.locked())
        return super().wait(timeout)


def _rekeying(active: bool = True, give_up: float = 10.0) -> SimpleNamespace:
    """A channel on a fake transport in the middle of a key exchange; `sent` records, for each message
    the transport was asked to send, whether the exchange had ended."""
    chan = SimpleNamespace(remote_chanid=7, closed=False, lock=threading.Lock())
    chan.transport = SimpleNamespace(clear_to_send=_KeyExchange(chan.lock), clear_to_send_lock=threading.Lock(),
                                     clear_to_send_timeout=give_up, is_active=lambda: active)
    chan.sent = []
    transport = chan.transport
    transport._send_message = lambda message: chan.sent.append(transport.clear_to_send.is_set())

    def send_user_message(message: Any) -> None:
        # Paramiko's own wait, made by whatever thread sends: until the exchange ends or its bound passes.
        give_up = time.monotonic() + transport.clear_to_send_timeout
        while time.monotonic() < give_up:
            transport.clear_to_send.wait(0.1)
            with transport.clear_to_send_lock:
                if transport.clear_to_send.is_set():
                    transport._send_message(message)
                    return

    transport._send_user_message = send_user_message
    return chan


@pytest.mark.unit
def test_a_signal_request_waits_out_a_key_exchange() -> None:
    # RFC 4253 §7.1: nothing but the exchange's own messages goes while a key exchange runs. The
    # request waits for it to end, without holding the channel's lock (the transport thread takes it
    # to deliver what arrives meanwhile), then goes.
    chan = _rekeying()
    sender = threading.Thread(target=ssh._signal, args=(chan, 'TERM'), daemon=True)
    sender.start()
    time.sleep(0.5)
    during = list(chan.sent)
    chan.transport.clear_to_send.set()
    sender.join(5)
    assert during == [], f'the signal request was sent during the key exchange: {during}'
    assert not sender.is_alive() and chan.sent == [True], \
        f'the signal request did not go once the key exchange ended: {chan.sent}, waiting {sender.is_alive()}'
    held = chan.transport.clear_to_send.held
    assert held and not any(held), f'the wait for the key exchange held the channel\'s lock: {held}'


class _ExchangeStarts(threading.Event):
    """A transport's `clear_to_send`, no key exchange running, whose first check starts one: the check
    hands the transport thread its start, which clears the event under `clear_to_send_lock` as
    Paramiko's does, and gives it `held` seconds to begin before it answers."""

    def __init__(self, lock: Any, held: float) -> None:
        super().__init__()
        self.set()
        self.lock, self.held, self.started = lock, held, False

    def is_set(self) -> bool:
        answer = super().is_set()
        if answer and not self.started:
            self.started = True
            transport_thread = threading.Thread(target=self._start, daemon=True)
            transport_thread.start()
            transport_thread.join(self.held)
        return answer

    def _start(self) -> None:
        with self.lock:
            self.clear()


@pytest.mark.unit
def test_a_signal_request_never_goes_as_a_key_exchange_starts() -> None:
    # The check that no key exchange runs and the send are one step against the transport thread,
    # which starts an exchange by clearing `clear_to_send` under `clear_to_send_lock`: the request is
    # sent holding that lock, so an exchange that starts as it is checked starts only once it is on
    # the wire, never between the check and the send (RFC 4253 §7.1).
    chan = _rekeying()
    transport = chan.transport
    transport.clear_to_send = _ExchangeStarts(transport.clear_to_send_lock, held=0.2)
    transport._send_message = lambda message: chan.sent.append(threading.Event.is_set(transport.clear_to_send))
    sender = threading.Thread(target=ssh._signal, args=(chan, 'TERM'), daemon=True)
    sender.start()
    sender.join(5)
    assert transport.clear_to_send.started, 'the signal request never checked for a key exchange'
    assert not sender.is_alive() and chan.sent == [True], \
        f'the signal request was sent as the key exchange started: {chan.sent}, waiting {sender.is_alive()}'


class _ClosedAsItWaits:
    """A transport's `clear_to_send_lock` that a close takes first: the channel is marked closed, and
    its close sent, while the signal request waits for the write path."""

    def __init__(self, chan: Any) -> None:
        self.chan, self.lock = chan, threading.Lock()

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        self.chan.closed = True
        return self.lock.acquire(blocking, timeout)

    def release(self) -> None:
        self.lock.release()

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *exc: Any) -> None:
        self.release()


@pytest.mark.unit
def test_a_signal_request_never_follows_a_close_made_as_it_waits() -> None:
    # A close marked while the request waits for the write path goes out first, through that path: the
    # request checks the channel once it holds the path, and so never follows the close (OpenSSH drops
    # the connection for a request on a channel it has freed).
    chan = _rekeying()
    chan.transport.clear_to_send.set()
    chan.transport.clear_to_send_lock = _ClosedAsItWaits(chan)
    sender = threading.Thread(target=ssh._signal, args=(chan, 'TERM'), daemon=True)
    sender.start()
    sender.join(5)
    assert not sender.is_alive() and chan.sent == [], f'the signal request went after a close: {chan.sent}'


@pytest.mark.unit
@pytest.mark.parametrize(('active', 'give_up', 'held'), [pytest.param(True, 0.5, 1.5, id='exchange-never-ends'),
                                                          pytest.param(False, 10.0, 1.0, id='transport-gone')])
def test_a_signal_request_gives_up_on_a_key_exchange(active: bool, give_up: float, held: float) -> None:
    # A key exchange that does not end within Paramiko's own bound, or a transport that has gone: the
    # request is dropped, best effort, and the caller is held no longer than that bound, or not at all.
    chan = _rekeying(active, give_up)
    sender = threading.Thread(target=ssh._signal, args=(chan, 'KILL'), daemon=True)
    started = time.monotonic()
    sender.start()
    sender.join(give_up + 2)
    took = time.monotonic() - started
    assert not sender.is_alive() and took < held, f'the signal request held its caller {took:.2f} s'
    assert chan.sent == [], f'the signal request was sent with no key exchange ended: {chan.sent}'


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
