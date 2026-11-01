# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""A server that cannot start says why, to the client, in both protocol eras.

A failed SSH connect is reported three ways: once on stderr, as `cannot connect to <host>: <cause>`; on stdio,
as a JSON-RPC internal error carrying the same message in answer to every request until the client
closes the stream; and as exit status `exit_status.runtime_error`. Every request is answered because a
2026-07-28 client swallows the error to its `server/discover` probe and retries with `initialize`.

- The responder on its own, over in-memory streams, read by `startup_refusal_violations`, with
  planted negatives it must reject.
- The raw wire, through the installed CLI under `bin/sandbox.sh` against a closed loopback port: a
  `server/discover` request, a notification and an `initialize` request go in, and exactly two error
  lines, the message on stderr and the exit status come out. Only here are the discover answer and
  the exit status both observable.
- A real client in each era (`test_startup_failure_is_answered[legacy|modern]`), each era on its own
  row whatever era the run selected, through the harness verb `stdio_refusal`.
- The cause classes, in-process with the connection stubbed (unit), and the connect bound: the
  defaults reach Fabric and an ssh_config `ConnectTimeout` still wins (unit), and a loopback listener
  that never sends an SSH banner is answered "timed out" within the bound (integration, with the
  bound lowered so the row is fast; Paramiko's own banner wait would answer it only after 15 s).

An installed capability that cannot load takes the same path, with `cannot load capability
<distribution>: <cause>` as the message, before the mode ladder runs. A distribution whose entry point
names a missing module is planted in a scratch directory put first on `PYTHONPATH` (or `sys.path`
in process): over the raw wire, with stdin closed, through a real client in each era and through the
deprecated `rcac-mcp` command, the start is refused, naming it; `--help` and `--version` still work;
in process the ladder is never consulted; and over HTTP the server exits before it serves. Each kind
of contribution the server would refuse while it is assembled is planted too, and refused at
startup the same way, over the raw wire, with stdin closed and over HTTP; so is each kind of
capability that cannot load. Through the CLI the suite drives one kind of each family
(`CLI_REJECTED`, `CLI_UNLOADABLE`); every kind is refused in process beside every member set, and
setting `CLUSTER_MCP_TEST_EVERY_KIND=1` drives every kind through the CLI as well.
"""

from __future__ import annotations

import io
import json
import logging
import os
import signal
import socket
import subprocess
import threading
import time
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Any, Sequence

import paramiko
import pytest
from cmdkit.app import exit_status
from fabric import Config, Connection
from paramiko.ssh_exception import (AuthenticationException, BadAuthenticationType, NoValidConnectionsError,
                                    SSHException)

import cluster_mcp.core
import cluster_mcp.core.capabilities
import cluster_mcp.core.executor.ssh
import cluster_mcp.core.tools
from harness import Refused, stdio_refusal
from cluster_mcp.core import MCPServerApp
from cluster_mcp.core.capabilities import GROUP
from cluster_mcp.core.startup import answer_until_eof
from test_capabilities import MEMBER_SETS, REJECTED, UNLOADABLE, rejected_package, unloadable, write_metadata
from test_cli import CLI, LEGACY_CLI, SANDBOX

INTERNAL_ERROR = -32603
MESSAGE = 'cannot connect to alias.example: connection refused'
LOOPBACK = '127.0.0.1'

DISCOVER = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'server/discover', 'params': {}})
NOTIFICATION = json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
INITIALIZE = json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'initialize', 'params': {}})
RAW_WIRE_IN = [DISCOVER, NOTIFICATION, INITIALIZE]

# Every shape the responder must skip or answer, for the in-memory row.
MIXED_IN = [
    DISCOVER,
    NOTIFICATION,
    json.dumps({'jsonrpc': '2.0', 'id': 'two', 'method': 'initialize', 'params': {}}),
    json.dumps({'jsonrpc': '2.0', 'id': 7, 'result': {}}),
    'not json at all',
    '',
    json.dumps({'jsonrpc': '2.0', 'id': 0, 'method': 'tools/list'}),
]


def _requests(lines_in: Sequence[str]) -> list[Any]:
    """The ids of the JSON-RPC requests among `lines_in`, in order."""
    ids = []
    for line in lines_in:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if isinstance(message, dict) and 'method' in message and 'id' in message:
            ids.append(message['id'])
    return ids


def startup_refusal_violations(lines_in: Sequence[str], lines_out: Sequence[str], message: str) -> list[str]:
    """Every way `lines_out` differs from answering each request in `lines_in` with `message`.

    Each request gets exactly one line, in order: a JSON-RPC 2.0 error with the request's own id,
    code -32603 and exactly `message`. No other line may appear on stdout.
    """
    violations: list[str] = []
    answered: list[Any] = []
    for n, line in enumerate(lines_out, 1):
        try:
            answer = json.loads(line)
        except ValueError:
            answer = None
        error = answer.get('error') if isinstance(answer, dict) else None
        if not isinstance(error, dict) or answer.get('jsonrpc') != '2.0' or 'id' not in answer:
            violations.append(f'stdout line {n} is not an error response: {line[:120]!r}')
            continue
        answered.append(answer['id'])
        if error.get('code') != INTERNAL_ERROR:
            violations.append(f'the answer to {answer["id"]!r} has code {error.get("code")!r}, expected {INTERNAL_ERROR}')
        if error.get('message') != message:
            violations.append(f'the answer to {answer["id"]!r} carries {error.get("message")!r}, not {message!r}')
    expected = _requests(lines_in)
    for request_id in expected:
        if request_id not in answered:
            violations.append(f'request {request_id!r} not answered')
    for request_id in answered:
        if request_id not in expected:
            violations.append(f'answered id {request_id!r}, which no request carried')
    if not violations and answered != expected:
        violations.append(f'answered {answered!r}, expected each of {expected!r} once, in order')
    return violations


def respond(lines_in: Sequence[str], message: str = MESSAGE) -> list[str]:
    stdout = io.StringIO()
    answer_until_eof(io.StringIO(''.join(line + '\n' for line in lines_in)), stdout, message)
    return stdout.getvalue().splitlines()


def error_line(request_id: Any, message: str = MESSAGE, code: int = INTERNAL_ERROR) -> str:
    return json.dumps({'jsonrpc': '2.0', 'id': request_id, 'error': {'code': code, 'message': message}})


@pytest.mark.unit
def test_responder_answers_every_request(guard) -> None:
    lines_out = respond(MIXED_IN)
    assert lines_out, 'the responder wrote nothing'
    violations = startup_refusal_violations(MIXED_IN, lines_out, MESSAGE)
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.mark.unit
def test_responder_reads_nothing_from_a_terminal(guard) -> None:
    stdin, stdout = Terminal(DISCOVER + '\n'), io.StringIO()
    answer_until_eof(stdin, stdout, MESSAGE)
    assert stdin.tell() == 0 and stdout.getvalue() == ''


@pytest.mark.unit
@pytest.mark.parametrize(('lines_out', 'fragment'), [
    pytest.param([error_line(1)], "request 2 not answered", id='first-request-only'),
    pytest.param([error_line(1), error_line(None), error_line(2)], 'which no request carried', id='notification-answered'),
    pytest.param([error_line(1), error_line(3)], 'request 2 not answered', id='wrong-id'),
    pytest.param([MESSAGE, error_line(1), error_line(2)], 'is not an error response', id='extra-stdout'),
    pytest.param([error_line(1), error_line(2, code=-32601)], 'has code -32601', id='wrong-code'),
    pytest.param([error_line(1), error_line(2, message='Connection closed')], "carries 'Connection closed'", id='wrong-message'),
    pytest.param([error_line(2), error_line(1)], 'in order', id='out-of-order'),
])
def test_startup_refusal_check_rejects(lines_out: list[str], fragment: str) -> None:
    violations = startup_refusal_violations(RAW_WIRE_IN, lines_out, MESSAGE)
    assert any(fragment in v for v in violations), violations


def closed_port() -> int:
    """A loopback port nothing listens on: bound once to pick it, then closed."""
    with socket.socket() as sock:
        sock.bind((LOOPBACK, 0))
        return sock.getsockname()[1]


def raw_wire_violations(result: subprocess.CompletedProcess[str], host: str, cause: str,
                        lines_in: Sequence[str]) -> list[str]:
    """Every way a CLI run that failed to connect to `host` differs from the reported startup failure.

    It exits `exit_status.runtime_error`; stderr carries one line `cannot connect to <host>: <cause>…`;
    stdout carries exactly the answers to the requests in `lines_in`, each with that same message.
    """
    violations: list[str] = []
    if result.returncode != exit_status.runtime_error:
        violations.append(f'exit status {result.returncode}, expected {exit_status.runtime_error}')
    reported = [line.split('] ', 1)[-1] for line in result.stderr.splitlines() if 'cannot connect' in line]
    if len(reported) != 1:
        violations.append(f'stderr reports the failure {len(reported)} times, expected once: {result.stderr[-400:]!r}')
    if not any(line.startswith(f'cannot connect to {host}: ') for line in reported):
        violations.append(f'stderr does not name the host {host}: {result.stderr[-400:]!r}')
    if not any(cause in line for line in reported):
        violations.append(f'stderr does not name the cause {cause!r}: {result.stderr[-400:]!r}')
    message = reported[0] if reported else ''
    violations.extend(startup_refusal_violations(lines_in, result.stdout.splitlines(), message))
    return violations


@pytest.mark.integration
def test_raw_wire_answers_every_request() -> None:
    host = f'{LOOPBACK}:{closed_port()}'
    result = subprocess.run([str(SANDBOX), str(CLI), '--ssh-host', host],
                            input=''.join(line + '\n' for line in RAW_WIRE_IN),
                            capture_output=True, text=True, timeout=60)
    assert result.stdout, f'nothing on stdout; stderr: {result.stderr[-400:]!r}'
    violations = raw_wire_violations(result, host, 'connection refused', RAW_WIRE_IN)
    assert violations == [], '\n'.join(violations)


def refused_violations(refused: Refused, host: str, cause: str) -> list[str]:
    """Every way the error a client got differs from the startup message for `host` and `cause`."""
    violations: list[str] = []
    if refused.code != INTERNAL_ERROR:
        violations.append(f'the client got code {refused.code}, expected {INTERNAL_ERROR}')
    if not refused.message.startswith(f'cannot connect to {host}: {cause}'):
        violations.append(f'the client was not answered with the startup message: got {refused.message!r}')
    return violations


@pytest.mark.integration
@pytest.mark.parametrize('era', ['legacy', 'modern'])
def test_startup_failure_is_answered(era: str) -> None:
    host = f'{LOOPBACK}:{closed_port()}'
    refused = stdio_refusal([str(SANDBOX), str(CLI), '--ssh-host', host], era)
    violations = refused_violations(refused, host, 'connection refused')
    assert violations == [], '\n'.join(violations)


@pytest.mark.unit
def test_harness_refuses_an_unsandboxed_refusal(guard) -> None:
    # A unit test: were the refusal missing, the unit guard would refuse the launch and record it.
    for argv in ([str(CLI), '--ssh-host', 'h'], ['sh', str(SANDBOX), str(CLI)], []):
        with pytest.raises(ValueError, match='must start with'):
            stdio_refusal(argv, 'legacy')
    assert guard.refused == []


@pytest.mark.unit
def test_refused_check_rejects_a_closed_connection() -> None:
    violations = refused_violations(Refused(-32000, 'Connection closed'), 'h:1', 'connection refused')
    assert any('not answered' in v for v in violations) and any('code -32000' in v for v in violations)


def _banner_timeout() -> SSHException:
    try:
        try:
            raise TimeoutError('timed out')
        except TimeoutError as exc:
            raise SSHException('Error reading SSH protocol banner') from exc
    except SSHException as exc:
        return exc


def _auth_failure(*results: BaseException) -> paramiko.AuthFailure:
    """What Paramiko's `AuthStrategy` raises when no source succeeded: each source's failure, in order."""
    from paramiko.auth_strategy import AuthResult, NoneAuth, SourceResult
    return paramiko.AuthFailure(AuthResult(None, [SourceResult(NoneAuth('user'), result) for result in results]))


CAUSES = [
    pytest.param(socket.gaierror(8, 'nodename nor servname provided, or not known'),
                 'unknown host or SSH alias', id='unknown-host'),
    pytest.param(NoValidConnectionsError({(LOOPBACK, 22): ConnectionRefusedError(61, 'Connection refused')}),
                 'connection refused', id='refused'),
    pytest.param(AuthenticationException('Authentication failed.'), 'authentication failed', id='authentication'),
    pytest.param(AuthenticationException('Authentication failed: transport shut down or saw EOF'),
                 'connection closed during authentication', id='authentication-closed'),
    pytest.param(AuthenticationException('Authentication timeout.'), 'timed out', id='authentication-timeout'),
    pytest.param(BadAuthenticationType('Bad authentication type', ['password']), 'authentication failed',
                 id='authentication-type'),
    pytest.param(paramiko.ssh_exception.PartialAuthentication(['keyboard-interactive']), 'authentication failed',
                 id='authentication-partial'),
    pytest.param(paramiko.PasswordRequiredException('Private key file is encrypted'), 'authentication failed',
                 id='authentication-passphrase'),
    pytest.param(_auth_failure(AuthenticationException('Authentication failed.')), 'authentication failed',
                 id='authentication-strategy-refused'),
    pytest.param(_auth_failure(AuthenticationException('Authentication failed.'),
                               AuthenticationException('Authentication failed: transport shut down or saw EOF')),
                 'connection closed during authentication', id='authentication-strategy-closed'),
    pytest.param(_auth_failure(SSHException('lost ssh-agent')), 'lost ssh-agent', id='authentication-strategy-agent'),
    pytest.param(TimeoutError('timed out'), 'timed out', id='timeout'),
    pytest.param(SSHException('No existing session'), 'timed out', id='negotiation-timeout'),
    pytest.param(_banner_timeout(), 'timed out', id='banner-timeout'),
    pytest.param(SSHException('No authentication methods available'), 'No authentication methods available',
                 id='other'),
]


def run_app(argv: list[str], lines_in: Sequence[str], monkeypatch: pytest.MonkeyPatch,
            caplog: pytest.LogCaptureFixture) -> dict:
    """Run the app in-process with `lines_in` on stdin; return its status, stdout lines and logs."""
    started: list[Any] = []
    monkeypatch.setattr(cluster_mcp.core, 'create_mcp_server', lambda *a, **k: started.append(a) or pytest.fail('server built'))
    stdin, stdout = io.StringIO(''.join(line + '\n' for line in lines_in)), io.StringIO()
    monkeypatch.setattr('sys.stdin', stdin)
    monkeypatch.setattr('sys.stdout', stdout)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger='cluster_mcp.core'):
        status = MCPServerApp.main(argv)
    return {
        'status': status,
        'stdout': stdout.getvalue().splitlines(),
        'read': stdin.tell(),
        'critical': [r.getMessage() for r in caplog.records if r.name == 'cluster_mcp.core' and r.levelno >= logging.CRITICAL],
        'started': bool(started),
    }


def startup_failure_violations(observed: dict, host: str, cause: str, lines_in: Sequence[str]) -> list[str]:
    """Every way an in-process run that failed to connect differs from the reported startup failure."""
    violations: list[str] = []
    if observed['status'] != exit_status.runtime_error:
        violations.append(f'exit status {observed["status"]}, expected {exit_status.runtime_error}')
    if observed['started']:
        violations.append('the server was built')
    if len(observed['critical']) != 1:
        violations.append(f'stderr reports the failure {len(observed["critical"])} times, expected once: {observed["critical"]}')
    message = observed['critical'][0] if observed['critical'] else ''
    if not message.startswith(f'cannot connect to {host}: '):
        violations.append(f'the message does not name the host {host}: {message!r}')
    if cause not in message:
        violations.append(f'the message does not name the cause {cause!r}: {message!r}')
    violations.extend(startup_refusal_violations(lines_in, observed['stdout'], message))
    return violations


@pytest.mark.unit
@pytest.mark.parametrize(('exc', 'cause'), CAUSES)
def test_connect_failure_names_host_and_cause(exc: BaseException, cause: str, monkeypatch: pytest.MonkeyPatch,
                                              caplog: pytest.LogCaptureFixture, guard) -> None:
    class Failing:
        def __init__(self, host: str, **kwargs: Any) -> None:
            pass

        def open(self) -> None:
            raise exc

    monkeypatch.setattr(cluster_mcp.core.executor.ssh, 'Connection', Failing)
    observed = run_app(['--ssh-host', 'alias.example'], RAW_WIRE_IN, monkeypatch, caplog)
    violations = startup_failure_violations(observed, 'alias.example', cause, RAW_WIRE_IN)
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_http_startup_failure_exits_without_reading_stdin(monkeypatch: pytest.MonkeyPatch,
                                                          caplog: pytest.LogCaptureFixture, guard) -> None:
    class Refusing:
        def __init__(self, host: str, **kwargs: Any) -> None:
            pass

        def open(self) -> None:
            raise ConnectionRefusedError(61, 'Connection refused')

    monkeypatch.setattr(cluster_mcp.core.executor.ssh, 'Connection', Refusing)
    observed = run_app(['-t', 'http', '--ssh-host', 'alias.example'], RAW_WIRE_IN, monkeypatch, caplog)
    assert observed['status'] == exit_status.runtime_error, observed
    assert observed['critical'] == ['cannot connect to alias.example: connection refused'], observed
    assert observed['stdout'] == [] and observed['read'] == 0 and not observed['started'], observed
    assert guard.refused == []


class Unopened(Connection):
    """Fabric's real `Connection`, built as the executor builds it, that never opens."""

    made: list[Connection] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        Unopened.made.append(self)

    def open(self) -> None:
        pass


BOUND = cluster_mcp.core.executor.ssh.CONNECT_TIMEOUT
QUIET_CONFIG = {'load_ssh_configs': False}


def bound_violations(conn: Connection, connect: int, banner: int, auth: int) -> list[str]:
    """Every way the connection's timeouts differ from the expected bound on each step."""
    violations: list[str] = []
    observed = (conn.connect_timeout, conn.connect_kwargs.get('banner_timeout'), conn.connect_kwargs.get('auth_timeout'))
    if observed != (connect, banner, auth):
        violations.append(f'the connect has no bound: connect, banner and auth timeouts are {observed}, '
                          f'expected {(connect, banner, auth)}')
    return violations


@pytest.mark.unit
@pytest.mark.parametrize(('kwargs', 'expected'), [
    pytest.param({}, (BOUND, BOUND, BOUND), id='default'),
    pytest.param({'config': Config(overrides=QUIET_CONFIG, ssh_config=paramiko.SSHConfig.from_text('Host *\n  ConnectTimeout 7\n'))},
                 (7, BOUND, BOUND), id='ssh-config-wins'),
    pytest.param({'connect_timeout': 3}, (3, BOUND, BOUND), id='explicit-wins'),
    pytest.param({'config': Config(overrides=QUIET_CONFIG, ssh_config=paramiko.SSHConfig()),
                  'connect_kwargs': {'look_for_keys': False}}, (BOUND, BOUND, BOUND), id='own-connect-kwargs'),
])
def test_connect_is_bounded(kwargs: dict, expected: tuple[int, int, int], monkeypatch: pytest.MonkeyPatch, guard) -> None:
    Unopened.made = []
    monkeypatch.setattr(cluster_mcp.core.executor.ssh, 'Connection', Unopened)
    cluster_mcp.core.executor.ssh.SSHExecutor('alias.example', **kwargs)
    assert len(Unopened.made) == 1
    violations = bound_violations(Unopened.made[0], *expected)
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


# The lowered bound for the silent-banner row, and how long the row waits for its answer: well
# under Paramiko's own 15 s banner wait, which answers it only when no bound is set.
SILENT_BOUND = 1
SILENT_DEADLINE = 8.0


@pytest.mark.integration
def test_silent_banner_is_answered_within_the_bound(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
                                                    tmp_path: Path) -> None:
    held: list[socket.socket] = []
    listener = socket.socket()
    listener.bind((LOOPBACK, 0))
    listener.listen(1)
    listener.settimeout(30)

    def accept() -> None:
        try:
            held.append(listener.accept()[0])
        except OSError:
            pass

    acceptor = threading.Thread(target=accept, daemon=True)
    acceptor.start()
    host = f'{LOOPBACK}:{listener.getsockname()[1]}'
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.delenv('SSH_AUTH_SOCK', raising=False)
    monkeypatch.setattr(cluster_mcp.core.executor.ssh, 'CONNECT_TIMEOUT', SILENT_BOUND)
    try:
        began = time.monotonic()
        observed = run_app(['--ssh-host', host], [INITIALIZE], monkeypatch, caplog)
        elapsed = time.monotonic() - began
    finally:
        listener.close()
        acceptor.join(timeout=5)
        for sock in held:
            sock.close()
    assert held, 'the listener was never reached'
    violations = startup_failure_violations(observed, host, 'timed out', [INITIALIZE])
    if elapsed >= SILENT_DEADLINE:
        violations.append(f'the connect has no bound: answered after {elapsed:.1f} s, '
                          f'expected within {SILENT_DEADLINE} s of a {SILENT_BOUND} s bound')
    assert violations == [], '\n'.join(violations)


# An installed capability that cannot load: a distribution whose entry point names a module that
# does not exist, planted beside nothing else in a scratch directory put first on the path.
BROKEN = 'planted-broken'
BROKEN_MESSAGE = f"cannot load capability {BROKEN}: ModuleNotFoundError: No module named 'planted_nowhere_at_all'"

# What the mode ladder writes once it has run, and what it raises when stdio has no SSH host.
LADDER = ('Execution mode', 'SSH host required')


def plant_broken(root: Path) -> Path:
    """Plant the broken capability's distribution under `root` and return the directory to put on the path."""
    info = root / f"{BROKEN.replace('-', '_')}-0.0.1.dist-info"
    info.mkdir(parents=True)
    (info / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: {BROKEN}\nVersion: 0.0.1\n')
    (info / 'entry_points.txt').write_text('[cluster_mcp.capabilities]\nbroken = planted_nowhere_at_all.capability:CAPABILITY\n')
    return root


def broken_env(root: Path) -> dict[str, str]:
    """This environment with the broken capability first on PYTHONPATH, whatever it already held kept after it."""
    held = os.environ.get('PYTHONPATH')
    planted = str(plant_broken(root))
    return {**os.environ, 'PYTHONPATH': planted + (os.pathsep + held if held else ''), 'FASTMCP_CHECK_FOR_UPDATES': 'off'}


def load_refusal_violations(status: int, stderr: Sequence[str], stdout: Sequence[str],
                            lines_in: Sequence[str], message: str = BROKEN_MESSAGE) -> list[str]:
    """Every way a start with a capability that cannot load differs from refusing to start for it.

    It exits `exit_status.runtime_error`; stderr reports `message`, naming the distribution, once, and
    nothing the mode ladder says, because the load comes before it; stdout carries exactly the answers
    to the requests in `lines_in`, each with that message.
    """
    violations: list[str] = []
    if status != exit_status.runtime_error:
        violations.append(f'exit status {status}, expected {exit_status.runtime_error}')
    reported = [line.split('] ', 1)[-1] for line in stderr if 'cannot load capability' in line]
    if reported != [message]:
        dist = message.removeprefix('cannot load capability ').split(':', 1)[0]
        violations.append(f'stderr does not name the distribution {dist} once with its cause: {list(stderr)[-6:]!r}')
    ladder = [line for line in stderr if any(said in line for said in LADDER)]
    if ladder:
        violations.append(f'the mode ladder ran before the capability load: {ladder!r}')
    violations.extend(startup_refusal_violations(lines_in, stdout, message))
    return violations


@pytest.mark.integration
@pytest.mark.parametrize(('command', 'drive'), [
    pytest.param('cluster-mcp', 'raw-wire', id='raw-wire'),
    pytest.param('cluster-mcp', 'stdin-closed', id='stdin-closed'),
    pytest.param('cluster-mcp', 'legacy', id='legacy'),
    pytest.param('cluster-mcp', 'modern', id='modern'),
    pytest.param('rcac-mcp', 'raw-wire', id='rcac-mcp'),
])
def test_a_broken_capability_stops_startup(command: str, drive: str, tmp_path: Path) -> None:
    # No SSH host is configured (the sandbox unsets it), so a start that reached the mode ladder would
    # refuse for that instead.
    env = broken_env(tmp_path / 'planted')
    cli = CLI if command == 'cluster-mcp' else LEGACY_CLI
    if drive in ('legacy', 'modern'):
        refused = stdio_refusal([str(SANDBOX), str(cli)], drive, env=env)
        violations = [] if refused.code == INTERNAL_ERROR else [f'the client got code {refused.code}, expected {INTERNAL_ERROR}']
        if refused.message != BROKEN_MESSAGE:
            violations.append(f'the answer the client got does not name the distribution {BROKEN}: {refused.message!r}')
        assert violations == [], '\n'.join(violations)
        return
    lines_in = RAW_WIRE_IN if drive == 'raw-wire' else []
    began = time.monotonic()
    result = subprocess.run([str(SANDBOX), str(cli)], input=''.join(line + '\n' for line in lines_in),
                            capture_output=True, text=True, timeout=60, env=env)
    elapsed = time.monotonic() - began
    violations = load_refusal_violations(result.returncode, result.stderr.splitlines(), result.stdout.splitlines(),
                                         lines_in)
    if command == 'rcac-mcp' and 'the rcac-mcp command is' not in result.stderr:
        violations.append(f'rcac-mcp did not warn before refusing: {result.stderr[-400:]!r}')
    assert violations == [], '\n'.join(violations)
    assert elapsed < 30, f'with stdin closed the refusal took {elapsed:.1f} s'


@pytest.mark.integration
@pytest.mark.parametrize('flag', ['--help', '--version'])
def test_help_works_with_a_broken_capability(flag: str, tmp_path: Path) -> None:
    result = subprocess.run([str(SANDBOX), str(CLI), flag], input='', capture_output=True, text=True, timeout=60,
                            env=broken_env(tmp_path / 'planted'))
    assert result.returncode == 0, result.stderr[-400:]
    assert result.stdout.startswith(('Usage:\n  cluster-mcp', 'cluster-mcp v')), result.stdout[:80]
    assert 'cannot load capability' not in result.stdout + result.stderr, result.stderr[-400:]


@pytest.mark.unit
def test_capabilities_load_before_the_mode_ladder(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
                                                  tmp_path: Path, guard) -> None:
    # The suite loaded every member once at startup; forget it, so this start loads again and finds
    # the planted distribution too. The cache is restored when the test ends.
    monkeypatch.syspath_prepend(str(plant_broken(tmp_path / 'planted')))
    monkeypatch.setattr(cluster_mcp.core.capabilities, '_installed', None)
    before = list(cluster_mcp.core.tools.TOOL_REGISTRY)
    consulted: list[str] = []
    ladder = MCPServerApp._resolve_exec_mode
    monkeypatch.setattr(MCPServerApp, '_resolve_exec_mode', lambda self: consulted.append('ladder') or ladder(self))
    observed = run_app([], RAW_WIRE_IN, monkeypatch, caplog)
    logged = [r.getMessage() for r in caplog.records if r.name == 'cluster_mcp.core']
    stderr = [*(line for line in logged if any(said in line for said in LADDER)), *observed['critical']]
    violations = load_refusal_violations(observed['status'], stderr, observed['stdout'], RAW_WIRE_IN)
    if consulted:
        violations.append('the mode ladder ran before the capability load: _resolve_exec_mode was called')
    if observed['started']:
        violations.append('the server was built')
    assert violations == [], '\n'.join(violations)
    assert cluster_mcp.core.tools.TOOL_REGISTRY == before
    assert guard.refused == []


@pytest.mark.integration
def test_http_load_failure_exits_before_binding(tmp_path: Path) -> None:
    port = closed_port()
    result = subprocess.run([str(SANDBOX), str(CLI), '-e', 'local', '-t', 'http', '-H', LOOPBACK, '-p', str(port)],
                            input=''.join(line + '\n' for line in RAW_WIRE_IN), capture_output=True, text=True,
                            timeout=60, env=broken_env(tmp_path / 'planted'))
    # Over HTTP nothing reads stdin: the requests on it go unanswered, and stdout stays empty.
    violations = load_refusal_violations(result.returncode, result.stderr.splitlines(), [], [])
    if result.stdout:
        violations.append(f'stdout is not empty over http: {result.stdout[:200]!r}')
    if 'Starting MCP server' in result.stderr or 'Uvicorn running' in result.stderr:
        violations.append(f'the server began serving before it refused: {result.stderr[-400:]!r}')
    assert violations == [], '\n'.join(violations)


def run_bounded(args: list[str], stdin: str, env: dict[str, str], timeout: float = 60) -> subprocess.CompletedProcess[str]:
    """Run `args` under `bin/sandbox.sh` in its own process group, feeding `stdin`; past `timeout`, kill
    the whole group and fail.

    A server that starts instead of refusing (over HTTP it would serve until killed) leaves nothing
    running behind the test: `subprocess.run` kills only the sandbox script on a timeout.
    """
    proc = subprocess.Popen([str(SANDBOX), *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env=env, start_new_session=True)
    try:
        out, err = proc.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        pytest.fail(f'the server was still running after {timeout} s instead of refusing to start: {err[-400:]!r}')
    return subprocess.CompletedProcess(args, proc.returncode, out, err)


# Whether the CLI drives below run over every kind, not one kind of each family. The suite never sets
# it; the class checkers under `spec/capability-extras/remediation/` (`F1-contribution-refusal.sh`,
# `F4-load-refusal.sh`) do. After the load the CLI's handling does not depend on the kind: the load
# raises a `CapabilityLoadError` or a `KeyboardInterrupt`, and `_load_capabilities` handles those. The
# full matrix lives there, and in process every kind is refused beside every member set
# (`test_capabilities.py`).
EVERY_KIND = os.environ.get('CLUSTER_MCP_TEST_EVERY_KIND') == '1'

# The `REJECTED` kinds the suite drives through the CLI: a resource FastMCP refuses, a URI collision
# and a registration that is not a tool.
CLI_REJECTED = ('resource-not-a-url', 'resource-uri-collides', 'tool-not-a-tool')

# The `UNLOADABLE` kinds the suite drives through the CLI, one of each family, at each of the five
# times between them: an `Exception`; `SystemExit` with 0, an int and a string; a `BaseException` of
# its own; a stray tool registered at the entry point's import; a registration that is not a tool;
# and a distribution with no `Name`.
CLI_UNLOADABLE = ('raises-at-entry-point', 'exits-0-at-tools', 'exits-int-at-declared', 'exits-text-at-served',
                  'raises-base-at-served-tool', 'stray-imported-by-the-entry-point', 'not-a-tool-from-the-entry-point',
                  'nameless-no-name')


@pytest.mark.unit
def test_the_cli_drives_name_kinds_that_exist() -> None:
    # A kind renamed or dropped from `REJECTED` or `UNLOADABLE` would leave the CLI drives naming a
    # kind that is not there.
    unknown = sorted({*CLI_REJECTED} - {*REJECTED}) + sorted({*CLI_UNLOADABLE} - {*UNLOADABLE})
    assert unknown == [], f'the CLI drives name kinds that are not planted: {unknown}'


def plant_rejected(root: Path, kind: str) -> tuple[Path, str]:
    """Plant the `REJECTED` capability `kind` (its package and distribution) under `root`; return the
    directory to put on the path and the distribution's name."""
    dist, entry, files = rejected_package(kind)
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    info = root / f"{dist.replace('-', '_')}-0.0.1.dist-info"
    info.mkdir(parents=True)
    (info / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: {dist}\nVersion: 0.0.1\n')
    (info / 'entry_points.txt').write_text(f'[cluster_mcp.capabilities]\n{entry}\n')
    return root, dist


@pytest.mark.integration
@pytest.mark.parametrize('drive', ['raw-wire', 'stdin-closed', 'http'])
@pytest.mark.parametrize('kind', list(REJECTED) if EVERY_KIND else CLI_REJECTED)
def test_a_contribution_the_server_would_refuse_stops_startup(kind: str, drive: str, tmp_path: Path) -> None:
    # Started in `local` mode, the server would build itself without the load's refusal and fail
    # there, after the mode ladder, with no answer on stdio; the load refuses first instead.
    root, dist = plant_rejected(tmp_path / 'planted', kind)
    violations = refused_start_violations(root, dist, REJECTED[kind]['cause'], drive)
    assert violations == [], '\n'.join(violations)


def refused_start_violations(root: Path, named: str, cause: str, drive: str) -> list[str]:
    """Every way a `local` start over `drive`, with `root` first on PYTHONPATH, differs from refusing
    to start for the capability `named`, its message carrying `cause`.

    Over the raw wire each request is answered with the refusal; with stdin closed the server exits at
    once; over HTTP it exits before binding, stdout empty. Each exits `exit_status.runtime_error`.
    """
    held = os.environ.get('PYTHONPATH')
    env = {**os.environ, 'PYTHONPATH': str(root) + (os.pathsep + held if held else ''),
           'FASTMCP_CHECK_FOR_UPDATES': 'off'}
    port = closed_port()
    argv = [str(CLI), '-e', 'local']
    argv += ['-t', 'http', '-H', LOOPBACK, '-p', str(port)] if drive == 'http' else []
    lines_in = RAW_WIRE_IN if drive != 'stdin-closed' else []
    began = time.monotonic()
    result = run_bounded(argv, ''.join(line + '\n' for line in lines_in), env)
    elapsed = time.monotonic() - began
    stderr = result.stderr.splitlines()
    reported = [line.split('] ', 1)[-1] for line in stderr if 'cannot load capability' in line]
    message = reported[0] if reported else ''
    violations = [] if message.startswith(f'cannot load capability {named}: ') and cause in message else \
        [f'the start was not refused naming {named} with {cause!r}: status {result.returncode}, {stderr[-6:]!r}']
    # Over HTTP nothing reads stdin: the requests on it go unanswered, and stdout stays empty.
    stdout = result.stdout.splitlines() if drive != 'http' else []
    violations += load_refusal_violations(result.returncode, stderr, stdout, [] if drive == 'http' else lines_in,
                                          message)
    if drive == 'http':
        if result.stdout:
            violations.append(f'stdout is not empty over http: {result.stdout[:200]!r}')
        if 'Starting MCP server' in result.stderr or 'Uvicorn running' in result.stderr:
            violations.append(f'the server began serving before it refused: {result.stderr[-400:]!r}')
    if elapsed >= 30:
        violations.append(f'the refusal took {elapsed:.1f} s')
    return violations


def plant_unloadable(root: Path, kind: str) -> tuple[Path, str, str]:
    """Plant the `UNLOADABLE` capability `kind` under `root`; return the directory to put on the path,
    the name its refusal carries and its cause."""
    case = unloadable(kind)
    for name, text in case.files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    info = root / f"{case.dist.replace('-', '_')}-0.0.1.dist-info"
    info.mkdir(parents=True)
    write_metadata(info, case.dist, case.metadata)
    (info / 'entry_points.txt').write_text(f'[cluster_mcp.capabilities]\n{case.entry}\n')
    return root, case.named, case.cause


@pytest.mark.integration
@pytest.mark.parametrize('drive', ['raw-wire', 'stdin-closed', 'http'])
@pytest.mark.parametrize('kind', UNLOADABLE if EVERY_KIND else CLI_UNLOADABLE)
def test_a_capability_that_cannot_load_stops_startup(kind: str, drive: str, tmp_path: Path) -> None:
    # Whatever its code raised or exited with, whenever it ran, a nameless distribution, a registration
    # outside its tools module made at its entry point's import: the start is refused, naming it, as
    # for any capability that cannot load.
    root, named, cause = plant_unloadable(tmp_path / 'planted', kind)
    violations = refused_start_violations(root, named, cause, drive)
    assert violations == [], '\n'.join(violations)


@pytest.mark.integration
def test_a_keyboard_interrupt_while_loading_still_interrupts_the_start(tmp_path: Path) -> None:
    root = tmp_path / 'planted'
    module = 'planted_interrupt'
    files = {f'{module}/__init__.py': '', f'{module}/capability.py': 'raise KeyboardInterrupt\n'}
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    info = root / 'planted_interrupt-0.0.1.dist-info'
    info.mkdir()
    write_metadata(info, 'planted-interrupt')
    (info / 'entry_points.txt').write_text(f'[cluster_mcp.capabilities]\ncap = {module}.capability:CAPABILITY\n')
    held = os.environ.get('PYTHONPATH')
    env = {**os.environ, 'PYTHONPATH': str(root) + (os.pathsep + held if held else ''), 'FASTMCP_CHECK_FOR_UPDATES': 'off'}
    result = run_bounded([str(CLI), '-e', 'local'], ''.join(line + '\n' for line in RAW_WIRE_IN), env)
    assert result.returncode == exit_status.keyboard_interrupt, \
        f'a keyboard interrupt did not interrupt the start: exit {result.returncode}, {result.stderr[-400:]!r}'
    assert 'cannot load capability' not in result.stderr + result.stdout, \
        f'a keyboard interrupt was refused as a capability that cannot load: {result.stderr[-400:]!r}'


# A capability that cannot load, found beside a member set: the group as `entry_points` would give it.
GONE = 'planted_nowhere_at_all.capability:CAPABILITY'
GONE_MESSAGE = f"cannot load capability {GONE}: ModuleNotFoundError: No module named 'planted_nowhere_at_all'"


def discover_beside_gone(names: tuple[str, ...], monkeypatch: pytest.MonkeyPatch, value: str = GONE) -> None:
    """Make the next load find the members in `names` and the capability `value` names (by default one
    that cannot load), uncached."""
    found = (*(ep for ep in entry_points(group=GROUP) if ep.name in names), EntryPoint('planted', value, GROUP))
    monkeypatch.setattr(cluster_mcp.core.capabilities, 'entry_points', lambda group: found)
    monkeypatch.setattr(cluster_mcp.core.capabilities, '_installed', None)


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_token_is_generated_before_any_capability_loads(names: tuple[str, ...], monkeypatch: pytest.MonkeyPatch,
                                                          caplog: pytest.LogCaptureFixture, guard) -> None:
    discover_beside_gone(names, monkeypatch)
    monkeypatch.setenv('JWT_SECRET', 'a planted secret of at least thirty-two characters')
    observed = run_app(['--generate-token', '--sub', 'planted'], [], monkeypatch, caplog)
    token = observed['stdout']
    violations = [] if observed['status'] == exit_status.success else [f"exit status {observed['status']}"]
    if len(token) != 1 or token[0].count('.') != 2:
        violations.append(f'no token printed: {token!r}')
    if observed['critical']:
        violations.append(f"reported {observed['critical']!r}")
    assert violations == [], 'the capability load ran before the token was generated: ' + '; '.join(violations)


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_keyboard_interrupt_while_loading_interrupts_the_start_beside_every_set(
        names: tuple[str, ...], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path,
        guard) -> None:
    package = tmp_path / 'planted' / 'planted_interrupting'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('')
    (package / 'capability.py').write_text('raise KeyboardInterrupt\n')
    monkeypatch.syspath_prepend(str(package.parent))
    discover_beside_gone(names, monkeypatch, 'planted_interrupting.capability:CAPABILITY')
    observed = run_app([], RAW_WIRE_IN, monkeypatch, caplog)
    refused = [line for line in observed['critical'] if 'cannot load capability' in line]
    assert observed['status'] == exit_status.keyboard_interrupt and not refused and not observed['stdout'], \
        f"a keyboard interrupt did not interrupt the start: exit {observed['status']}, {observed['critical']!r}"


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_capabilities_load_before_the_mode_ladder_beside_every_set(names: tuple[str, ...],
                                                                   monkeypatch: pytest.MonkeyPatch,
                                                                   caplog: pytest.LogCaptureFixture, guard) -> None:
    discover_beside_gone(names, monkeypatch)
    before = list(cluster_mcp.core.tools.TOOL_REGISTRY)
    consulted: list[str] = []
    ladder = MCPServerApp._resolve_exec_mode
    monkeypatch.setattr(MCPServerApp, '_resolve_exec_mode', lambda self: consulted.append('ladder') or ladder(self))
    observed = run_app([], RAW_WIRE_IN, monkeypatch, caplog)
    logged = [r.getMessage() for r in caplog.records if r.name == 'cluster_mcp.core']
    stderr = [*(line for line in logged if any(said in line for said in LADDER)), *observed['critical']]
    violations = load_refusal_violations(observed['status'], stderr, observed['stdout'], RAW_WIRE_IN, GONE_MESSAGE)
    if consulted:
        violations.append('the mode ladder ran before the capability load: _resolve_exec_mode was called')
    if observed['started']:
        violations.append('the server was built')
    assert violations == [], '\n'.join(violations)
    assert cluster_mcp.core.tools.TOOL_REGISTRY == before
    assert guard.refused == []
