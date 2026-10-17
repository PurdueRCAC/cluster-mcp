# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""The `ssh` executor runs a command over the locked Fabric and Paramiko, against a loopback server.

`SSHExecutor` drives the recommended deployment, and nothing else in the suite runs it. Here it
connects to an in-process Paramiko server bound to 127.0.0.1, with keys generated for the test,
which answers each exec request with canned output and a non-zero exit status; no process is
launched and nothing leaves the machine. The test is isolated from the developer's SSH setup:
`HOME` is under `tmp_path`, `SSH_AUTH_SOCK` is unset, the client neither looks for keys nor asks an
agent, and Fabric is handed an empty SSH config, so no `~/.ssh/config` or `/etc/ssh/ssh_config` is
read.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

import paramiko
import pytest
from fabric import Config

from rcac_mcp.executor.base import CommandResult
from rcac_mcp.executor.ssh import SSHExecutor

LOOPBACK = '127.0.0.1'
EXIT_STATUS = 3
COMMAND = 'echo hi'


def smoke_violations(result: CommandResult, received: list[str], command: str, host: str,
                     exit_status: int) -> list[str]:
    """Every way `result` and the commands the server `received` differ from one exec of `command`."""
    violations: list[str] = []
    if received != [command]:
        violations.append(f'the server received {received!r}, expected [{command!r}]')
    if result.stdout != f'smoke:{command}':
        violations.append(f'stdout differs: {result.stdout!r}, expected {"smoke:" + command!r}')
    if result.exit_code != exit_status:
        violations.append(f'exit status differs: {result.exit_code!r}, expected {exit_status}')
    if result.hostname != host:
        violations.append(f'hostname differs: {result.hostname!r}, expected {host!r}')
    return violations


class _Server(paramiko.ServerInterface):
    """Accept the one client key; answer every exec with `smoke:<command>` and EXIT_STATUS."""

    def __init__(self, client_key: paramiko.PKey, received: list[str]) -> None:
        self.client_key = client_key
        self.received = received

    def get_allowed_auths(self, username: str) -> str:
        return 'publickey'

    def check_auth_publickey(self, username: str, key: paramiko.PKey) -> int:
        same = key.get_base64() == self.client_key.get_base64()
        return paramiko.AUTH_SUCCESSFUL if same else paramiko.AUTH_FAILED

    def check_channel_request(self, kind: str, chanid: int) -> int:
        return paramiko.OPEN_SUCCEEDED

    def check_channel_env_request(self, channel: Any, name: bytes, value: bytes) -> bool:
        return True

    def check_channel_exec_request(self, channel: paramiko.Channel, command: bytes) -> bool:
        self.received.append(command.decode())

        def reply() -> None:
            # Paramiko confirms the exec request after this method returns; answering before that
            # confirmation reaches the client closes the channel under it.
            time.sleep(0.2)
            channel.sendall(b'smoke:' + command)
            channel.send_exit_status(EXIT_STATUS)
            channel.close()

        threading.Thread(target=reply, daemon=True).start()
        return True


@pytest.mark.integration
def test_ssh_executor_runs_over_a_loopback_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.delenv('SSH_AUTH_SOCK', raising=False)
    # Invoke forwards the local stdin to the remote command; pytest's captured stdin refuses reads.
    stdin = open(os.devnull)
    monkeypatch.setattr(sys, 'stdin', stdin)
    host_key = paramiko.RSAKey.generate(2048)
    client_key = paramiko.RSAKey.generate(2048)
    received: list[str] = []
    transports: list[paramiko.Transport] = []

    with socket.socket() as listener:
        listener.bind((LOOPBACK, 0))
        listener.listen(1)
        listener.settimeout(30)
        port = listener.getsockname()[1]

        def serve() -> None:
            conn, _ = listener.accept()
            transport = paramiko.Transport(conn)
            transports.append(transport)
            transport.add_server_key(host_key)
            transport.start_server(server=_Server(client_key, received))

        server = threading.Thread(target=serve, daemon=True)
        server.start()
        executor = SSHExecutor(LOOPBACK, port=port, user='smoke',
                               config=Config(overrides={'load_ssh_configs': False}, ssh_config=paramiko.SSHConfig()),
                               connect_kwargs={'pkey': client_key, 'look_for_keys': False, 'allow_agent': False})
        try:
            result = executor.run(COMMAND, timeout=30)
        finally:
            executor.close()
            server.join(timeout=5)
            for transport in transports:
                transport.close()
            stdin.close()

    violations = smoke_violations(result, received, COMMAND, LOOPBACK, EXIT_STATUS)
    assert violations == [], '\n'.join(violations)


@pytest.mark.unit
@pytest.mark.parametrize(('result', 'received', 'fragment'), [
    pytest.param(CommandResult('smoke:echo hi', '', 0, LOOPBACK), [COMMAND], 'exit status differs', id='exit-dropped'),
    pytest.param(CommandResult('', '', EXIT_STATUS, LOOPBACK), [COMMAND], 'stdout differs', id='stdout-lost'),
    pytest.param(CommandResult('smoke:echo hi', '', EXIT_STATUS, 'cluster.invalid'), [COMMAND], 'hostname differs',
                 id='wrong-host'),
    pytest.param(CommandResult('smoke:echo hi', '', EXIT_STATUS, LOOPBACK), ['cd /tmp && echo hi'],
                 'the server received', id='command-rewritten'),
])
def test_smoke_check_catches_drift(result: CommandResult, received: list[str], fragment: str) -> None:
    clean = CommandResult('smoke:echo hi', '', EXIT_STATUS, LOOPBACK)
    assert smoke_violations(clean, [COMMAND], COMMAND, LOOPBACK, EXIT_STATUS) == []
    violations = smoke_violations(result, received, COMMAND, LOOPBACK, EXIT_STATUS)
    assert any(fragment in v for v in violations), violations
