# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""What a server that cannot start tells its client: the reason, as the answer to every request.

A server refuses to start for one of two reasons: an installed capability that cannot load, or a
failed SSH connect. Either is reported three ways: once on stderr, which a client may discard; on
stdio, as a JSON-RPC error carrying the same message in answer to every request the client sends
until it closes the stream; and as a nonzero exit status. Every request is answered, not only the
first, because a client of protocol revision 2026-07-28 swallows the error to its `server/discover`
probe and retries with `initialize`; an answer to that retry is the one it shows.

This module needs no MCP stack: it speaks newline-delimited JSON-RPC directly, the stdio framing
both protocol eras share, so it behaves the same whichever era the client speaks. The messages are
their owners': `cannot load capability <distribution>: <cause>` is the capability loader's
(`capabilities.CapabilityLoadError`), and `cannot connect to <host>: <cause>` is the SSH backend's
(`executor.ssh.connect_failure_message`), which a call that cannot reconnect reports too.
"""

# Type annotations
from __future__ import annotations
from typing import Any, Final, TextIO

# Standard libs
import json

# Internal libs
from cluster_mcp.core.executor.ssh import connect_failure_message

# Public interface
__all__ = ['StartupFailure', 'answer_until_eof', 'connect_failure_message', 'refusal', 'INTERNAL_ERROR']


# JSON-RPC's internal-error code: standard, accurate, and read by no client as protocol-version
# evidence or as a transport failure of its own.
INTERNAL_ERROR: Final = -32603


class StartupFailure(RuntimeError):
    """The server could not start; the message has already been reported."""


def refusal(request_id: Any, message: str) -> str:
    """The JSON-RPC error line answering the request `request_id` with `message`."""
    error = {'jsonrpc': '2.0', 'id': request_id, 'error': {'code': INTERNAL_ERROR, 'message': message}}
    return json.dumps(error, separators=(',', ':')) + '\n'


def _request_id(line: str) -> tuple[bool, Any]:
    """Whether `line` is a JSON-RPC request, and its id when it is."""
    try:
        message = json.loads(line)
    except ValueError:
        return False, None
    if not isinstance(message, dict) or not isinstance(message.get('method'), str):
        return False, None
    request_id = message.get('id')
    if isinstance(request_id, bool) or not isinstance(request_id, (str, int)):
        return False, None
    return True, request_id


def answer_until_eof(stdin: TextIO, stdout: TextIO, message: str) -> None:
    """Answer every request read from `stdin` with `message` as an error on `stdout`, until EOF.

    Input is newline-delimited JSON-RPC. A request (an object with a `method` and a string or integer
    `id`) is answered with an internal error carrying `message` and the request's own id; a
    notification, a response, a blank or unreadable line is skipped. Nothing else is written. A
    terminal on stdin is no client, so nothing is read from one; a closed stdout ends the answers.
    """
    if stdin.isatty():
        return
    while line := stdin.readline():
        is_request, request_id = _request_id(line)
        if not is_request:
            continue
        try:
            stdout.write(refusal(request_id, message))
            stdout.flush()
        except (BrokenPipeError, ValueError):
            return
