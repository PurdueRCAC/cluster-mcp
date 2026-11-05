# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""SSH-based command executor: Fabric for the connection, a raw Paramiko channel per command.

A file's content never travels on a command's stdin here: `write` sends it by SFTP into a private
directory beside the target, every write's reply and the close checked, and a program then checks
its size and checksum against the bytes sent before it moves it into place. A connection lost
before a command's end records arrived is reported as such (`CONNECTION_LOST_EXIT_CODE`), never as
a command that did not start.

A call that finds the connection lost reconnects within a deadline (`SSHExecutor` states the bound):
every attempt runs on a worker thread the call stops waiting for at its deadline, at most one
attempt is in flight at a time, and a call that cannot reconnect reports
`cannot connect to <host>: <cause>` as a command that was not run (`NOT_STARTED_EXIT_CODE`), never
as a lost connection.

A link that dies silently, with no reset, still reads as connected, so each published connection
has a liveness monitor (`_Liveness`) that notices it: it probes the peer when nothing has been heard
for the connect bound, and at once when a call starts, and closes the connection when a probe goes
unanswered with nothing at all heard since. Every wait on the connection then ends, and the call
reads the closed connection as any lost one.
"""

# Type annotations
from __future__ import annotations
from collections.abc import Iterator, Sequence
from typing import Any, Final, Optional, Type
from types import TracebackType

# Standard libs
import contextlib
import errno
import os
import posixpath
import secrets
import select
import socket
import stat
import threading
import time
import zlib

# External libs
from fabric import Config, Connection
from paramiko import AuthFailure, SFTPClient, Transport
from paramiko.common import cMSG_CHANNEL_REQUEST, cMSG_GLOBAL_REQUEST
from paramiko.file import BufferedFile
from paramiko.message import Message
from paramiko.sftp import CMD_CLOSE
from paramiko.ssh_exception import (AuthenticationException, BadAuthenticationType, NoValidConnectionsError,
                                    PartialAuthentication, PasswordRequiredException, SSHException)

# Internal libs
from cluster_mcp.core.executor import launch
from cluster_mcp.core.executor.base import (CONNECTION_LOST_EXIT_CODE, NOT_STARTED_EXIT_CODE, TIMEOUT_EXIT_CODE,
                                    CommandResult, UserPath)

# Public interface
__all__ = ['SSHExecutor', 'connect_failure_message']


# The backoff between reconnect attempts: the first wait, doubled after each failure up to the most.
MAX_RECONNECT_DELAY: float = 10.0
INITIAL_RECONNECT_DELAY: float = 0.5

# A call that has to reconnect gives up this many times the connect bound (`_bound`) after it began.
RECONNECT_FACTOR: Final = 3

# How often, in seconds, a call waiting on a connect attempt checks its own deadline.
ATTEMPT_POLL: Final = 0.1

# A call starts or joins a connect attempt only until this many seconds before its deadline, so a
# host that is back by then is used, and never later: past that, it gives up at once.
FINAL_ATTEMPT_LEAD: Final = 2.0

# How far down an exception's cause and context chain the failure class is looked for.
CHAIN_DEPTH: Final = 8

# Paramiko's words for the two ways an authentication ends without the server's answer
# (`AuthHandler.wait_for_response`): the link closed while it waited (a lost host, or an abort
# closing the transport), or its auth timeout ran out. Every other `AuthenticationException` is a
# refusal (`_auth_ending`).
AUTH_CLOSED: Final = 'Authentication failed: transport shut down or saw EOF'
AUTH_TIMED_OUT: Final = 'Authentication timeout.'

# The oldest Paramiko whose authentication outcomes `_auth_ending` can tell apart: 3.2 gave a link
# closed during authentication its own text (`AUTH_CLOSED`), where earlier releases raised the
# refusal's `Authentication failed.`, and added `AuthFailure`. `pyproject.toml` declares this floor.
PARAMIKO_FLOOR: Final = (3, 2)

# The `AuthenticationException` subclasses that are refusals by their class: the server allows none
# of the methods tried (`BadAuthenticationType`) or wants more than was offered
# (`PartialAuthentication`), or a key needs a passphrase that was not given
# (`PasswordRequiredException`).
REFUSALS: Final = (BadAuthenticationType, PartialAuthentication, PasswordRequiredException)

# Seconds to wait for the server to open a session channel, at the least: a channel open on a watched
# connection waits `OPEN_MARGIN` past its connect bound when that is longer (`_open_timeout`), so on a
# dead link the liveness monitor's close always comes first.
OPEN_TIMEOUT: Final = 30.0
OPEN_MARGIN: Final = 1.0

# Seconds a transport is given to finish closing once an exec request fails. Paramiko wakes the wait
# on the request before it marks a lost connection inactive, so only a transport still active after
# this long is a live server that refused the request.
SETTLE: Final = 1.0

# How many symbolic links a path may pass through before it is a loop, as Linux counts them (ELOOP).
MAX_LINKS: Final = 40

# Default bound, in seconds, on each step of connecting: the TCP connect, the server's SSH banner and
# authentication. A whole number: Fabric truncates the connect timeout to an int, and 0 means none.
CONNECT_TIMEOUT: Final = 15

# How long one wait for output lasts: a select on the channel before its output ends, a short
# sleep once its output has ended or its exit status is in (the channel then reads as ready forever).
SELECT_WAIT: Final = 0.1
SLEEP_WAIT: Final = 0.02

# A read from the channel, per call.
CHUNK: Final = 65536

# The global request a liveness probe sends, wanting a reply: the one OpenSSH's own
# `ServerAliveInterval` sends. sshd and Paramiko's server answer a request they do not know with
# `REQUEST_FAILURE`, and any message from the peer, that one included, proves the link live.
PROBE_REQUEST: Final = 'keepalive@openssh.com'

# The most, in seconds, the liveness monitor waits between two decisions.
LIVENESS_TICK: Final = 0.1

# What a background probe's verdict leaves of the reconnect bound for what follows it, in seconds:
# the probe's due time and the verdict each seen up to a tick late, the close, the wake of every wait
# and the channel loop's poll (`SELECT_WAIT`), 0.45 s at most together.
VERDICT_MARGIN: Final = 1.0

# The attribute of a watched transport that holds its liveness monitor.
WATCHED: Final = '_cluster_mcp_liveness'

# The liveness monitor's clock, bound at import: never `time`, which a test may replace.
_liveness_clock = time.monotonic

# Where a write stages its content: a directory of this name and a fresh token, mode 0700, beside
# the target (so the move into place is a rename within one filesystem), holding the content and its
# expected checksum, each a file of mode 0600. The checksum is staged, never passed in an argv, so no
# other user can read even that of the content.
STAGE_PREFIX: Final = '.cluster-mcp-'
STAGED: Final = 'content'
EXPECTED: Final = 'expected'

# The programs that put a staged file in place, "$1" the staged file, "$2" the target, "$3" the mode
# the target keeps (its own without setuid and setgid, or `=rw`, which a new file's umask narrows, as
# `cat >` would leave it), "$4" the staged checksum. Each first checks that the staged file is what
# was sent (`VERIFY`: its POSIX `cksum`, CRC and size, against the staged one), and an overwrite of an
# existing file first checks that the user may write it (`WRITABLE`), as `cat >` would; either check
# failing leaves the target untouched. An overwrite then moves the file into place, atomically; an
# append adds its bytes to the target; a target that is not a regular file (a FIFO, a device) is
# written through, as `cat >` would.
VERIFY: Final = ('[ "$(cksum <"$1")" = "$(cat -- "$4")" ] || { printf "%s\\n" '
                 '"cluster-mcp: the content staged for $2 is not what was sent, so the file is unchanged" >&2; '
                 'exit 1; }\n')
WRITABLE: Final = '[ -w "$2" ] || { printf "%s: Permission denied\\n" "$2" >&2; exit 1; }\n'
PLACE: Final = 'chmod -- "$3" "$1" && mv -f -- "$1" "$2"'
PLACE_APPEND: Final = 'cat -- "$1" >>"$2"'
PLACE_THROUGH: Final = 'cat -- "$1" >"$2"'
PLACE_EXECUTABLE: Final = ' && chmod -- +x "$2"'
MAKE_PARENT: Final = 'mkdir -p -- "$1"'

# The permission bits a replaced file never keeps: a write by its user clears setuid and setgid, so
# `cat >` leaves a file without them.
SET_ID: Final = stat.S_ISUID | stat.S_ISGID

# After a failed transfer, the remote filesystem is asked why: this many zero bytes appended to the
# staged file (discarded with it) fail as the transfer did, and the error names the cause (`No space
# left on device`, `Disk quota exceeded`). SFTP version 3, which OpenSSH speaks, reports only
# `Failure`.
PROBE: Final = 'head -c 65536 </dev/zero >>"$1"'

# The errors that leave a directory closed to a new entry (no write permission), while a writable
# target in it can still be written through.
CLOSED: Final = (errno.EACCES, errno.EPERM)


def _drain(chan: Any, out: bytearray, err: bytearray) -> None:
    while chan.recv_ready():
        out += chan.recv(CHUNK)
    while chan.recv_stderr_ready():
        err += chan.recv_stderr(CHUNK)


def _signal(chan: Any, name: str) -> None:
    """Ask the server to deliver signal `name` to the command (RFC 4254 §6.9), on an open channel
    only; best effort.

    The request never goes on a channel the client has closed or begun to close: OpenSSH answers a
    request on a channel it has freed by dropping the connection (`server_input_channel_req`, "unknown
    channel"), which every call and transfer shares. Paramiko marks a channel closed under the
    channel's lock before it sends its own close, whether this side closes it or answers the server's,
    so the check and the send are made holding that lock, and a close waits for the request to be on
    the wire. The wait for a key exchange to finish is made without that lock, as Paramiko's own sends
    make it, since its transport thread takes the lock to deliver what arrives meanwhile.

    OpenSSH signals the session's whole process group, and only while the session's process (the
    program, which the bootstrap `exec`s into) lives: the program dies of a TERM, and its watchdog
    stops what is left of the group. A program that ignored TERM from its entry (the remote login
    shell's own rc file ignored it before the bootstrap ran, and bash cannot undo an ignore it
    started with) lives on, so it and its group are reached by a KILL request.
    """
    try:
        message = Message()
        message.add_byte(cMSG_CHANNEL_REQUEST)
        message.add_int(chan.remote_chanid)
        message.add_string('signal')
        message.add_boolean(False)
        message.add_string(name)
        transport = chan.transport
        give_up = time.monotonic() + transport.clear_to_send_timeout
        while transport.is_active() and time.monotonic() < give_up:
            transport.clear_to_send.wait(SELECT_WAIT)
            with chan.lock:
                if chan.closed:
                    return
                with transport.clear_to_send_lock:
                    if transport.clear_to_send.is_set():
                        transport._send_message(message)
                        return
    except Exception:
        pass


def _ended(chan: Any) -> bool:
    """The channel has closed, or has delivered both its end of output and its exit status."""
    return chan.closed or (chan.eof_received and chan.exit_status_ready())


def _lost(chan: Any) -> bool:
    """The channel closed without its end of output: the connection went, not the command's output.

    sshd sends the end of a channel's output before it closes the channel; a channel that closes
    without it was closed by the transport, when the connection was lost.
    """
    return chan.closed and not chan.eof_received


def _wait(chan: Any, left: float | None) -> None:
    """Wait for more from the channel, at most `left` seconds, without spinning.

    A select on the channel while output may still come; a short sleep once its output has ended or
    its exit status is in (the channel then reads as ready forever).
    """
    if chan.eof_received or chan.exit_status_ready():
        wait = SLEEP_WAIT if left is None else min(SLEEP_WAIT, left)
        time.sleep(wait)
    else:
        select.select([chan], [], [], SELECT_WAIT if left is None else min(SELECT_WAIT, left))


def _stopped(chan: Any, out: bytearray, err: bytearray) -> None:
    """After the TERM at a deadline: keep reading what the command prints as it stops, for `GRACE`."""
    end = time.monotonic() + launch.GRACE
    while True:
        _drain(chan, out, err)
        left = end - time.monotonic()
        if _ended(chan) or left <= 0:
            return
        _wait(chan, left)


def _collect(chan: Any, timeout: float | None, end: bytes | None = None) -> tuple[bytes, bytes, int, bytes]:
    """Read the channel's stdout and stderr until both have carried their end record; return them,
    the status and a note.

    Given the program's end nonce `end`, the output is complete once each stream has carried its end
    record, however long it takes to arrive: sshd sends the exit status as soon as the command exits,
    ahead of output still queued on a slow link, so the status is never a reason to stop. The read
    then stops and the channel is closed, so nothing left running holds the call. A channel that ends
    first (`_ended`) ends the read too, with everything it carried; one that closed without its end of
    output (`_lost`), before both records arrived, lost its connection, and the code is
    `CONNECTION_LOST_EXIT_CODE` with `launch.LOST_NOTE`: the command may have run. At the deadline the code is
    `TIMEOUT_EXIT_CODE`: a command whose exit status has arrived is asked nothing and the note
    (`launch.LATE_NOTE`) names that status; otherwise the command is asked to TERM, what it prints
    as it stops is read for `GRACE`, and then, unless the channel has ended meanwhile (closed, or its
    output and exit status both in: the launch has exited), it is asked to KILL, which adds no wait;
    `_signal` sends nothing on a channel that has closed. sshd acts on the KILL only while the launch
    lives, which after that read means its program ignored TERM from its entry; otherwise it refuses
    it, and the program's watchdog stops the group. The status beside complete
    output is the channel's if it has arrived, else -1, as Paramiko reports a signal death or a lost
    status; the record is the command's.
    """
    out, err = bytearray(), bytearray()
    deadline = None if timeout is None else time.monotonic() + timeout
    scanned = [0, 0]
    while True:
        _drain(chan, out, err)
        if end is not None:
            for i, buf in enumerate((out, err)):
                if scanned[i] >= 0:
                    found = launch.record(buf, end, scanned[i])
                    scanned[i] = -1 if found else max(0, len(buf) - len(end) - 5)
            if scanned == [-1, -1]:
                return bytes(out), bytes(err), chan.recv_exit_status() if chan.exit_status_ready() else -1, b''
        if _ended(chan):
            _drain(chan, out, err)
            if _lost(chan) and not (end is not None and launch.record(out, end) and launch.record(err, end)):
                return bytes(out), bytes(err), CONNECTION_LOST_EXIT_CODE, launch.LOST_NOTE
            return bytes(out), bytes(err), chan.recv_exit_status(), b''
        now = time.monotonic()
        if deadline is not None and now >= deadline:
            if chan.exit_status_ready():
                note = launch.LATE_NOTE.format(code=chan.recv_exit_status()).encode()
                return bytes(out), bytes(err), TIMEOUT_EXIT_CODE, note
            _signal(chan, 'TERM')
            _stopped(chan, out, err)
            if not _ended(chan):
                _signal(chan, 'KILL')
            return bytes(out), bytes(err), TIMEOUT_EXIT_CODE, b''
        _wait(chan, None if deadline is None else deadline - now)


def _remote(path: str) -> str:
    """A command-side path for SFTP, which starts in the login home and expands nothing.

    `~` is `.` and `~/rest` is `rest`, with the leading slashes of `rest` collapsed so the path
    stays in the home; any other path is passed as given.
    """
    if path == '~':
        return '.'
    if path.startswith('~/'):
        return path[2:].lstrip('/') or '.'
    return path


def _bounded(connect_kwargs: dict) -> dict:
    """`connect_kwargs` for Fabric's `Connection`, with every step of connecting bounded by default.

    The connect timeout goes in as Fabric's config default, so an ssh_config `ConnectTimeout` and an
    explicit `connect_timeout` still win; the banner and auth timeouts join the connect arguments
    unless they are already set. A `timeout` already among the connect arguments is left alone.
    """
    kwargs = dict(connect_kwargs)
    given = kwargs.get('config')
    config = Config() if given is None else given.clone(into=None if isinstance(given, Config) else Config)
    explicit = dict(kwargs.get('connect_kwargs') or {})
    if 'timeout' not in explicit and 'timeout' not in config.connect_kwargs and config.timeouts.connect is None:
        config.timeouts.connect = CONNECT_TIMEOUT
    for key in ('banner_timeout', 'auth_timeout'):
        if key not in config.connect_kwargs:
            config.connect_kwargs[key] = CONNECT_TIMEOUT
        if explicit and key not in explicit:
            explicit[key] = CONNECT_TIMEOUT
    kwargs['config'] = config
    if explicit:
        kwargs['connect_kwargs'] = explicit
    return kwargs


def _bound(conn: Any) -> float:
    """The connect bound of `conn`, in seconds: `CONNECT_TIMEOUT`, or a longer one it was given.

    Fabric has already resolved the connection's connect timeout from the caller's
    `connect_timeout`, the ssh_config `ConnectTimeout` or `_bounded`'s default; an explicit `timeout`
    among its connect arguments counts too. A shorter bound never lowers `CONNECT_TIMEOUT`.
    """
    explicit = (getattr(conn, 'connect_kwargs', None) or {}).get('timeout')
    return max(CONNECT_TIMEOUT, getattr(conn, 'connect_timeout', None) or 0, explicit or 0)


def _live(conn: Any) -> Transport | None:
    """The transport of `conn` while it is open and connected, else None."""
    if conn is None or not conn.is_connected:
        return None
    return getattr(conn, 'transport', None)


def _links(conn: Any) -> Iterator[Any]:
    """`conn`, then each gateway `Connection` it reaches its host through (a ProxyJump chain)."""
    seen: set[int] = set()
    while conn is not None and not isinstance(conn, str) and id(conn) not in seen:
        seen.add(id(conn))
        yield conn
        conn = getattr(conn, 'gateway', None)


def _release(conn: Any) -> None:
    """Let `conn` go, best effort: close its client and every gateway's in its chain.

    Fabric's own `close()` does nothing for a connection whose transport never opened or has died,
    which would leave a half-made transport, or a ProxyJump hop's session, running.
    """
    for link in _links(conn):
        try:
            link.client.close()
        except Exception:
            pass


def _transports(conn: Any) -> list[Transport]:
    """The transports `conn`'s client and each gateway's in its chain have made so far.

    A client makes its transport as its connect begins; Fabric's `conn.transport` stays None until
    `open()` returns, so it is never one of them.
    """
    found = []
    for link in _links(conn):
        try:
            transport = link.client.get_transport()
        except Exception:
            continue
        if transport is not None:
            found.append(transport)
    return found


def _await(event: threading.Event, seconds: float) -> bool:
    """Wait up to `seconds` for `event`; return whether it is set."""
    return event.wait(seconds)


def _chain(exc: BaseException) -> Iterator[BaseException]:
    """`exc`, then the exceptions it was raised from or while handling, nearest first."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(seen) < CHAIN_DEPTH:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _refused(exc: BaseException) -> bool:
    if isinstance(exc, ConnectionRefusedError):
        return True
    if isinstance(exc, NoValidConnectionsError):
        return bool(exc.errors) and all(isinstance(e, ConnectionRefusedError) for e in exc.errors.values())
    return False


def _auth_cause(exc: BaseException) -> BaseException:
    """The failure that decides how the authentication that raised `exc` ended.

    An `AuthFailure` (raised under an `AuthStrategy`, which Fabric's `authentication.strategy_class`
    opts into) carries each source's result: the first source that failed for any reason but a
    refusal decides it, else the last source's refusal (the `AuthFailure` itself when it tried
    none). Any other exception is its own cause.
    """
    if not isinstance(exc, AuthFailure):
        return exc
    results = (getattr(source, 'result', None) for source in getattr(exc, 'result', None) or ())
    failures = [result for result in results if isinstance(result, BaseException)]
    for failure in failures:
        if _auth_ending(failure) != 'refused':
            return _auth_cause(failure)
    return failures[-1] if failures else exc


def _auth_ending(exc: BaseException) -> str | None:
    """How the authentication that raised `exc` ended, by its cause; None for any other failure.

    `closed` when the link closed before the server answered (the host lost, or the transport closed
    under it); `timed out` when the auth timeout ran out first; `refused` for every other
    `AuthenticationException`: the server rejected the credentials, allows none of the methods
    tried or wants more than was offered, or a key could not be used. Only `refused` ends a
    reconnect at once: a retry cannot change it, while the other two say nothing about the
    credentials. An `AuthFailure` ends as its deciding source did (`_auth_cause`): `refused` only
    when every source was refused.
    """
    if isinstance(exc, AuthFailure):
        cause = _auth_cause(exc)
        return 'refused' if cause is exc else _auth_ending(cause)
    if not isinstance(exc, AuthenticationException):
        return None
    if isinstance(exc, REFUSALS):
        return 'refused'
    if str(exc) == AUTH_CLOSED:
        return 'closed'
    if str(exc) == AUTH_TIMED_OUT:
        return 'timed out'
    return 'refused'


def _cause_class(exc: BaseException) -> str | None:
    """The class of a connect failure, or None when it is none of the known ones."""
    for link in _chain(exc):
        link = _auth_cause(link)
        ending = _auth_ending(link)
        if ending == 'refused':
            return 'authentication failed'
        if ending == 'closed':
            return 'connection closed during authentication'
        if ending == 'timed out':
            return 'timed out'
        if isinstance(link, socket.gaierror):
            return 'unknown host or SSH alias'
        if _refused(link):
            return 'connection refused'
        if isinstance(link, TimeoutError):
            return 'timed out'
        # Paramiko's report when the key exchange has not finished by the connect timeout: the
        # negotiation stopped waiting while the transport was still alive.
        if type(link) is SSHException and str(link) == 'No existing session':
            return 'timed out'
    return None


def _detail(exc: BaseException) -> str:
    exc = _auth_cause(exc)
    if isinstance(exc, OSError) and exc.strerror:
        return str(exc.strerror)
    if _auth_ending(exc) == 'closed':
        # Paramiko's text calls it a failed authentication, which it was not.
        return ''
    return str(exc)


def connect_failure_message(host: str, exc: BaseException) -> str:
    """`cannot connect to <host>: <cause>`, naming the host as given and the class of failure.

    The class is one of `unknown host or SSH alias`, `connection refused`, `authentication failed`
    (a refusal: the server rejected the credentials or allows none of the methods tried, or a key
    could not be used), `connection closed during authentication` or `timed out` (an
    authentication's own timeout included), followed by the exception's own text in parentheses
    when it says more; a failure of no known class is described by that text, or by the exception's
    type when it has none. A server that cannot connect at startup reports it, and so does a call
    that cannot reconnect.
    """
    cause = _cause_class(exc)
    detail = _detail(exc).strip()
    if cause is None:
        return f'cannot connect to {host}: {detail or type(exc).__name__}'
    if detail and detail.lower().rstrip('.') != cause:
        return f'cannot connect to {host}: {cause} ({detail})'
    return f'cannot connect to {host}: {cause}'


class _Pending:
    """One connect attempt in flight, shared by every call waiting on it.

    The worker running the attempt sets `conn` once it has built the connection, records the
    outcome (`transport` on success, else `error`) and then sets `done`. `waiters` counts the calls
    still waiting, and `aborted` says the last of them closed the attempt's transports as it left;
    both change only under the executor's lock.
    """

    def __init__(self) -> None:
        self.done = threading.Event()
        self.transport: Transport | None = None
        self.error: BaseException | None = None
        self.conn: Any = None
        self.waiters = 1
        self.aborted = False


def _verdict(heard: float, out: float | None, poked: float | None, now: float, bound: float) -> str | None:
    """What the liveness monitor does at `now`: `'probe'`, `'dead'` or nothing (None).

    `heard` is when the last message arrived from the peer, `out` when the judged probe still
    unanswered was handed over (None when there is none), `poked` when the oldest call still
    waiting on a fresh probe started (None when none waits), and `bound` the connection's connect
    bound. A probe with nothing at all heard since it went is judged dead after twice the bound less
    `VERDICT_MARGIN` (a background probe), or one bound after the poke of a call that started while
    it was out, whichever comes first. With no probe out, one is due at once for a call, or after a
    bound of quiet.
    """
    if out is not None and heard < out:
        due = out + 2 * bound - VERDICT_MARGIN
        if poked is not None:
            due = min(due, max(out, poked) + bound)
        return 'dead' if now >= due else None
    if poked is not None or now - heard >= bound:
        return 'probe'
    return None


def _hook(packetizer: Any, monitor: _Liveness) -> None:
    """Stamp `monitor.heard` after every message `packetizer` reads, by an instance wrapper on its
    `read_message`, which the transport's thread looks up on every pass of its loop.

    A read that raises stamps nothing (a pending key exchange on a dead link raises about every
    0.1 s). The read in progress as the wrapper goes in returns its message unstamped: the monitor
    therefore sends a priming probe it never judges.
    """
    read = packetizer.read_message

    def read_message() -> Any:
        message = read()
        monitor.heard = _liveness_clock()
        return message

    packetizer.read_message = read_message


def _monitor_of(transport: Any) -> _Liveness | None:
    """The liveness monitor watching `transport`, or None."""
    return getattr(transport, WATCHED, None)


def _poked(transport: Any) -> Any:
    """`transport`, its liveness monitor told that a call is about to use it."""
    monitor = _monitor_of(transport)
    if monitor is not None:
        monitor.poke()
    return transport


def _opening(transport: Any) -> contextlib.AbstractContextManager[None]:
    """While a call waits on a channel or session to open on `transport` (`_Liveness.opening`)."""
    monitor = _monitor_of(transport)
    return contextlib.nullcontext() if monitor is None else monitor.opening()


def _open_timeout(transport: Any) -> float:
    """How long a channel open on `transport` waits: `OPEN_TIMEOUT`, or `OPEN_MARGIN` past its
    monitor's bound (a call's verdict) when that is longer."""
    monitor = _monitor_of(transport)
    return max(OPEN_TIMEOUT, (CONNECT_TIMEOUT if monitor is None else monitor.bound) + OPEN_MARGIN)


def _gone(transport: Any) -> bool:
    """Whether a failure on `transport` was its connection's loss, decided by state, never by the
    exception's type (the waiters of a closed transport see `EOFError`, `SSHException` or `OSError`).

    It was when the liveness monitor found the link dead, when the transport is no longer active
    `SETTLE` after the failure (Paramiko wakes a wait before it marks a lost connection inactive), or
    when the monitor's judged probe is still unanswered: the link is unproven, and the verdict on it
    is near.
    """
    monitor = _monitor_of(transport)
    if monitor is not None and monitor.dead:
        return True
    transport.join(SETTLE)
    if not transport.is_active():
        return True
    return monitor is not None and monitor.unanswered()


def _down(transport: Any) -> bool:
    """Whether `transport` is known lost now: its monitor found the link dead, or it is inactive."""
    monitor = _monitor_of(transport)
    return (monitor is not None and monitor.dead) or not transport.is_active()


def _cut(sftp: SFTPClient, exc: BaseException) -> bool:
    """Whether `exc`, raised by a step of an SFTP session, came from its connection's loss.

    Decided by state, never by the exception's type: a lost session's waits raise `EOFError`,
    `SSHException` or an `OSError` such as `Socket is closed`. An `OSError` carrying an errno other
    than a connection's is the server's own answer, so the link was live; `Short` was decided on a
    live link. Otherwise the loss is the monitor's verdict, or the transport inactive. An `OSError`
    on a channel still open is the server's answer too (OpenSSH reports a full filesystem as a bare
    `Failure`), since a lost connection closes its channels; any other failure waits `SETTLE` for the
    transport to go inactive (Paramiko wakes a wait before it marks a lost connection inactive).
    """
    if isinstance(exc, Short) or (isinstance(exc, OSError) and exc.errno is not None
                                  and not isinstance(exc, ConnectionError)):
        return False
    channel = sftp.get_channel()
    transport = channel.get_transport()
    if _down(transport):
        return True
    if isinstance(exc, OSError) and not channel.closed:
        return False
    transport.join(SETTLE)
    return not transport.is_active()


class TransferLost(ConnectionError):
    """A transfer whose connection was lost once its SFTP session had opened: it may be partly made.

    The text names the host, says the transfer may be partly made, and says what may remain.
    """

    def __init__(self, host: str, during: str, remains: str) -> None:
        super().__init__(f'the connection to {host} was lost during the {during}; the transfer may be partly '
                         f'made: {remains}')


class _Lost(Exception):
    """Inside `write`: a later command of the write found the connection lost; `left` says what may remain."""

    def __init__(self, left: str) -> None:
        super().__init__(left)
        self.left = left


def _remains(what: str, directory: str | None) -> str:
    """`what`, and the staging directory `directory` that may remain, when one was made."""
    return what if directory is None else f'{what}, and its staging directory {directory} may remain'


def _lost_to(result: CommandResult, transport: Any) -> bool:
    """Whether a write's own command met its connection lost: it may have run (`-1003`), or it was
    not run (`-1002`) because the write's connection is gone and no reconnect came. A `-1002` on a
    live connection is a program that did not start, the write's own failure."""
    return result.exit_code == CONNECTION_LOST_EXIT_CODE or (result.exit_code == NOT_STARTED_EXIT_CODE
                                                            and _down(transport))


def _said(result: CommandResult) -> str:
    """What a write's own command reported, without the server's prefix."""
    return result.stderr.strip().removeprefix('cluster-mcp: ')


class _Liveness:
    """The liveness monitor of one published connection, which notices a link that has gone silent
    with no reset.

    Every message read from the peer is stamped (`_hook`). A probe (`PROBE_REQUEST`) is due once
    nothing has been heard for the connection's connect bound, and at once when a call starts using
    the connection (`poke`); `_verdict` judges it. On a dead verdict the monitor marks the
    connection dead and closes its transports, the outermost gateway hop first, so an inner close
    never blocks behind a gateway's stuck write; every wait on the connection then ends within
    about 0.1 s.

    Two threads, so no lock can stall a verdict: the judge (`cluster-mcp-liveness`) decides, taking
    no transport lock, and hands each probe to the sender (`cluster-mcp-probe`), which sends it as
    `_signal` sends a request and swallows every error. A send blocks on a dead link's full buffer or
    during a key exchange, so the probe counts from its hand-over, even while the sender is still
    busy with an earlier one; the sender then sends one more when it is free. The first probe, the
    priming one, is never judged. The monitor reads its own clock (`_liveness_clock`), and its threads
    are daemons that end within a tick of the transport going inactive or of `stop`.
    """

    def __init__(self, conn: Any, host: str) -> None:
        self.conn = conn
        self.host = host
        self.transport = conn.transport
        self.bound = _bound(conn)
        self.heard = _liveness_clock()
        self.out: float | None = None
        self.poked: float | None = None
        # How many calls are waiting on a channel or session to open (`opening`).
        self.waiting = 0
        self.dead = False
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._send = threading.Event()
        self._stopped = False
        setattr(self.transport, WATCHED, self)

    @classmethod
    def of(cls, conn: Any, host: str) -> _Liveness | None:
        """A monitor for `conn`, just opened, or None when its transport is not a Paramiko `Transport`."""
        return cls(conn, host) if isinstance(getattr(conn, 'transport', None), Transport) else None

    def start(self) -> None:
        """Install the activity hook and start both threads; the sender sends the priming probe first."""
        _hook(self.transport.packetizer, self)
        try:
            threading.Thread(target=self._sender, name='cluster-mcp-probe', daemon=True).start()
            threading.Thread(target=self._judge, name='cluster-mcp-liveness', daemon=True).start()
        except RuntimeError:
            # A process out of threads leaves the connection unwatched, as before there was a monitor.
            self.stop()

    def stop(self) -> None:
        """End both threads within a tick; never waits for them."""
        self._stopped = True
        self._wake.set()
        self._send.set()

    def poke(self) -> None:
        """A call is about to use the connection: a probe goes at once, unless one is out already,
        and the call's verdict comes one bound after this poke at the latest."""
        with self._lock:
            if self.poked is None:
                self.poked = _liveness_clock()
        self._wake.set()

    @contextlib.contextmanager
    def opening(self) -> Iterator[None]:
        """A call waits on a channel or an SFTP session to open: the poke stays while it waits.

        An open takes several waits on the peer, and a reply to one of them can answer the probe the
        call's poke sent before the next wait has begun; so while a call waits, an answer clears
        nothing, and the next probe goes at once, each judged a bound after it is handed over.
        """
        with self._lock:
            self.waiting += 1
            if self.poked is None:
                self.poked = _liveness_clock()
        self._wake.set()
        try:
            yield
        finally:
            with self._lock:
                self.waiting -= 1

    def unanswered(self) -> bool:
        """Whether a judged probe is out with nothing heard since it was handed over."""
        with self._lock:
            return self.out is not None and self.heard < self.out

    def step(self, now: float) -> str | None:
        """One decision at `now`, `_verdict`'s, made on the state as the messages heard leave it.

        A probe is answered once anything has been heard since it was handed over; that clears the
        poke only when the probe was handed over at or after it, since a reply already on its way
        as the link went silent proves nothing about the link a call is waiting on. A probe due is
        handed over here, and a poke never moves the probe already out.
        """
        with self._lock:
            if self.out is not None and self.heard >= self.out:
                if self.poked is not None and self.out >= self.poked and not self.waiting:
                    self.poked = None
                self.out = None
            action = _verdict(self.heard, self.out, self.poked, now, self.bound)
            if action == 'probe':
                self.out = now
            elif action == 'dead':
                self.dead = True
        if action == 'probe':
            self._send.set()
        return action

    def _judge(self) -> None:
        while not self._stopped and self.transport.is_active():
            self._wake.wait(LIVENESS_TICK)
            self._wake.clear()
            if self._stopped:
                return
            if self.step(_liveness_clock()) == 'dead':
                self._close()
                return

    def _close(self) -> None:
        for transport in reversed(_transports(self.conn)):
            try:
                transport.close()
            except Exception:
                pass

    def _sender(self) -> None:
        primed = False
        while not self._stopped and self.transport.is_active():
            if primed:
                if not self._send.wait(LIVENESS_TICK):
                    continue
                self._send.clear()
                if self._stopped:
                    return
            primed = True
            try:
                message = Message()
                message.add_byte(cMSG_GLOBAL_REQUEST)
                message.add_string(PROBE_REQUEST)
                message.add_boolean(True)
                self.transport._send_user_message(message)
            except Exception:
                pass


def _is_dir(sftp: SFTPClient, path: str) -> bool:
    try:
        return stat.S_ISDIR(sftp.stat(path).st_mode or 0)
    except OSError as exc:
        if _cut(sftp, exc):
            raise
        return False


def _loops(sftp: SFTPClient, path: str) -> bool:
    """Whether resolving SFTP path `path` passes through more than `MAX_LINKS` symbolic links.

    The path is resolved here, a component at a time, by the links' own text, as a kernel resolves
    it: a server's SFTP reports a loop as a missing file (OpenSSH) or a bare `Failure`. A component
    that cannot be read ends the walk: that path does not loop.
    """
    try:
        done = '/' if path.startswith('/') else sftp.normalize('.')
        todo = [part for part in reversed(path.split('/')) if part]
        links = 0
        while todo:
            part = todo.pop()
            if part == '.':
                continue
            if part == '..':
                done = posixpath.dirname(done)
                continue
            step = posixpath.join(done, part)
            if not stat.S_ISLNK(sftp.lstat(step).st_mode or 0):
                done = step
                continue
            links += 1
            if links > MAX_LINKS:
                return True
            names = sftp.readlink(step) or ''
            if names.startswith('/'):
                done = '/'
            todo.extend(reversed([part for part in names.split('/') if part]))
    except OSError as exc:
        if _cut(sftp, exc):
            raise
        return False
    return False


def _staging(sftp: SFTPClient, path: str) -> tuple[str, str | None, bool]:
    """Where a write of SFTP path `path` lands, the mode it keeps, and whether it is written through.

    A symbolic link is followed to the file it names (the server resolves it), as a shell's `>`
    follows it: a link to a missing file in an existing directory creates that file, and one whose
    target's directory does not exist is refused, naming that target, and stays a link. An existing
    regular file keeps its permission bits but setuid and setgid (`SET_ID`); a missing one gets a
    new file's (None). A target that exists and is not a regular file is written through; a
    directory is refused.
    """
    try:
        link = stat.S_ISLNK(sftp.lstat(path).st_mode or 0)
    except FileNotFoundError:
        return path, None, False
    if link:
        try:
            resolved = sftp.normalize(path)
        except FileNotFoundError:
            resolved = None
        if resolved is None or not _is_dir(sftp, posixpath.dirname(resolved) or '/'):
            try:
                names = sftp.readlink(path) or '?'
            except OSError as exc:
                if _cut(sftp, exc):
                    raise
                names = '?'
            raise FileNotFoundError(errno.ENOENT, f'No such file or directory: the symbolic link names {names!r}, '
                                    'whose directory does not exist', path)
        path = resolved
    try:
        mode = sftp.stat(path).st_mode or 0
    except FileNotFoundError:
        return path, None, False
    if stat.S_ISDIR(mode):
        raise IsADirectoryError(errno.EISDIR, 'Is a directory', sftp.normalize(path))
    return path, f'{stat.S_IMODE(mode) & ~SET_ID:o}', not stat.S_ISREG(mode)


def _stage_in(near: str) -> str:
    """A fresh name for a staging directory in `near`."""
    return posixpath.join(near, STAGE_PREFIX + secrets.token_hex(8))


def _stage(sftp: SFTPClient, directory: str) -> str:
    """Make the private directory `directory`; return the path of the file to stage there.

    The directory is made mode 0700, so no other user can reach what it holds.
    """
    sftp.mkdir(directory, 0o700)
    return posixpath.join(directory, STAGED)


class Short(OSError):
    """A transfer that failed or fell short: the staged file is not what was sent."""


def _close(sftp: SFTPClient, handle: Any) -> None:
    """Close an SFTP file, raising when the server reports that the close failed.

    Paramiko's own close discards that report, and a close is where a filesystem that defers its
    writes (NFS, a quota checked at close) reports a write that did not land.
    """
    BufferedFile.close(handle)
    sftp._request(CMD_CLOSE, handle.handle)


def _upload(sftp: SFTPClient, staged: str, data: bytes) -> None:
    """Create `staged` exclusively, make it mode 0600 before any byte is written, then write `data`.

    Every write waits for its reply, which raises on a failure: Paramiko files a pipelined write's
    reply where nothing reads it, so a pipelined transfer that fails reports success. The close's
    reply is checked too, and then the staged file's size. Any of them failing raises `Short`.
    """
    handle = sftp.open(staged, 'wbx')
    try:
        try:
            sftp.chmod(staged, 0o600)
            handle.set_pipelined(False)
            handle.write(data)
            handle.flush()
        except BaseException:
            handle.close()
            raise
        _close(sftp, handle)
        size = sftp.stat(staged).st_size
    except OSError as exc:
        if _cut(sftp, exc):
            raise
        raise Short(exc.strerror or str(exc) or 'Failure') from exc
    if size != len(data):
        raise Short(f'{size} of {len(data)} bytes arrived')


def cksum(data: bytes) -> str:
    """What POSIX `cksum` prints for `data` read on its stdin: the CRC and the size.

    The CRC is POSIX's (polynomial 0x04C11DB7, not reflected, the length appended, then inverted),
    computed through zlib's reflected CRC-32 on the bit-reversed bytes.
    """
    size, length = len(data), b''
    while size:
        length += bytes([size & 0xFF])
        size >>= 8
    value = zlib.crc32((data + length).translate(_REVERSED), 0xFFFFFFFF)
    return f'{int(f"{value:032b}"[::-1], 2)} {len(data)}'


_REVERSED: Final = bytes(int(f'{i:08b}'[::-1], 2) for i in range(256))


def _discard(sftp: SFTPClient, directory: str, *staged: str) -> None:
    """Remove a staging directory and what is left in it (the checksum, once a move has taken the file),
    best effort: a session lost meanwhile leaves it."""
    for remove, target in (*((sftp.remove, path) for path in staged), (sftp.rmdir, directory)):
        try:
            remove(target)
        except (OSError, EOFError, SSHException):
            pass


class SSHExecutor:
    """
    Execute commands on a remote host via SSH.

    Uses Fabric's Connection which auto-loads ~/.ssh/config for host aliases,
    identity files, and proxy commands. Maintains a persistent connection with
    automatic reconnection on failure. Each step of connecting is bounded (`CONNECT_TIMEOUT` unless
    the SSH config or the caller sets it), so an unreachable host fails within a bound a client waits for.

    A call that finds the connection lost keeps trying to reconnect, with backoff, and gives up at
    most three times the connect bound after the call began: 45 s with the default 15 s
    (`CONNECT_TIMEOUT`). It starts or joins no attempt later than 2 s before that: one that finds the
    connection lost after then, as a `write`'s later command can, gives up at once. An ssh_config
    `ConnectTimeout` (or a caller's `connect_timeout`) longer than 15 s raises the bound to three times
    that value; a shorter one never lowers it. A refused authentication, the server rejecting the
    credentials or a key that cannot be used, gives up at once; one cut short by a lost link or its
    own timeout is retried, and no call takes the failure of an attempt aborted at another call's
    deadline as its own. The call then reports `cannot connect to <host>: <cause>` and runs nothing,
    and the next call tries again.

    The bound holds for each call to the executor (`run`, `write`, `put`, `get`). Every connect
    attempt runs on a worker thread, so no step of it (name resolution, an SSH agent, several keys,
    a ProxyJump hop) holds a call past its deadline; at most one attempt is in flight at a time,
    and a call that arrives during one joins it. The last call to give up on an attempt aborts it,
    unless its outcome has come or another call has joined it, so an abort never closes a
    published connection.

    A link that dies with no reset still reads as connected, so a liveness monitor watches each
    published connection. It stamps every message the peer sends, and sends a probe
    (`PROBE_REQUEST`, a global request that wants a reply) once nothing has been heard for the
    connect bound B, and at once when a call starts using the connection; the first probe is never
    judged. A probe with nothing at all heard since it went is judged dead B after the poke of a
    call that started while it was out, so a call that starts on a silent link notices it at most B
    after its start, and a background probe after 2B − `VERDICT_MARGIN` (29 s with the default
    bound), so a call in flight ends at most 3B − 0.55 s after the last message heard, inside the 3B
    bound. A call that starts during a stall ends the stalled call too, at its own verdict. On a dead
    verdict the monitor closes the connection's transports, the outermost gateway hop first, and
    every wait on it ends: a channel open that fails on a lost connection has sent nothing, so the
    call reconnects within its deadline; from the exec request on nothing is retried, and a command
    cut short returns `CONNECTION_LOST_EXIT_CODE`, with or without a timeout, unless its own timeout
    came first. Nothing merely quiet is cut, since any message proves the link live, while the peer
    answers within the background verdict: at the default bound, a quiet command survives the peer
    answering nothing for 29 s after a probe, and a transfer while some reply arrives at least every
    44 s.

    A transfer's SFTP session opens with the same retry, its three steps (the channel, the `sftp`
    subsystem and the version exchange) holding the call's poke, so each probe sent while it waits is
    judged B after it went. Once the session has opened, a loss raises `TransferLost`, a
    `ConnectionError` naming the host that says the transfer may be partly made and what may remain:
    for `put`, the remote target, truncated or holding part of the file; for `get`, the local file,
    likewise; for `write`, the target unchanged and the staging directory that may remain, or, when
    its parent's `mkdir` or its place step meets the loss, what that step can leave (an overwrite is
    the old file or the new one, an append or a write-through may be partial). The loss is decided by
    state before any handler that would read it as the server's answer, and a lost write leaves its
    staging directory (`issues/ssh-write-staging-leftover.md`).
    """

    _host: str
    _conn: Optional[Connection]
    _connect_kwargs: dict
    _lock: threading.Lock
    _window: float
    _inflight: Optional[_Pending]
    _monitor: Optional[_Liveness]
    _closed: bool

    def __init__(self, host: str, **connect_kwargs) -> None:
        """
        Initialize SSH executor and establish connection.

        Args:
            host: Hostname or SSH config alias to connect to.
            **connect_kwargs: Additional arguments passed to Fabric Connection
                              (e.g., user, port, connect_timeout).
        """
        self._host = host
        self._conn = None
        self._connect_kwargs = connect_kwargs
        # The published connection, the reconnect window and the one attempt in flight (and its
        # waiters and abort) change only under this lock, and it is held only for that bookkeeping,
        # never across a connect or a close.
        self._lock = threading.Lock()
        self._window = RECONNECT_FACTOR * CONNECT_TIMEOUT
        self._inflight = None
        # The liveness monitor of the published connection, replaced with it under the lock.
        self._monitor = None
        # Set by `close()` and cleared by `open()`: a call that a close woke never reconnects.
        self._closed = False
        # Establish connection immediately
        self.open()

    @property
    def hostname(self) -> str:
        """Return the configured host."""
        return self._host

    def open(self) -> None:
        """Establish SSH connection (single attempt, no retry).

        The attempt runs on the calling thread; a failure releases what it made and raises its own
        exception, which a server that cannot start reports.
        """
        self._closed = False
        if self._conn is not None and self._conn.is_connected:
            return
        conn = self._new()
        try:
            conn.open()
        except BaseException:
            _release(conn)
            raise
        with self._lock:
            _, dropped, watch = self._publish(conn)
        if watch is not None:
            watch.start()
        if dropped is not None:
            _release(dropped)

    def close(self) -> None:
        """Close the SSH connection, and stop its liveness monitor.

        A call that the close wakes raises, or reports its command lost, as it would without one,
        and starts no reconnect, so no connection or monitor outlives the close.
        """
        with self._lock:
            self._closed = True
            monitor, self._monitor = self._monitor, None
        if monitor is not None:
            monitor.stop()
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _new(self) -> Connection:
        """A new, unopened connection to the host, every step of connecting bounded.

        Building one is not free: Fabric's ssh_config lookup runs any `Match exec` command and, with
        `CanonicalizeHostname`, resolves names. A reconnect builds one only inside an attempt.
        """
        return Connection(self._host, **_bounded(self._connect_kwargs))

    def _publish(self, conn: Connection) -> tuple[Transport, Connection | None, _Liveness | None]:
        """Make `conn`, just opened, the executor's connection; called with the lock held.

        Returns the transport calls use, the connection to release once the lock is let go and the
        liveness monitor to start then: `conn` itself is released, with no monitor, when another live
        connection is already published (whose transport is then the one returned); otherwise the
        dead one `conn` replaces is, its monitor stopped first, and `conn` gets a monitor of its own.
        The reconnect window is taken from the connection published.
        """
        current = _live(self._conn)
        if current is not None:
            return current, conn, None
        dropped, self._conn = self._conn, conn
        self._window = RECONNECT_FACTOR * _bound(conn)
        if self._monitor is not None:
            self._monitor.stop()
        self._monitor = _Liveness.of(conn, self._host)
        return getattr(conn, 'transport', None), dropped, self._monitor

    def _attempt(self, pending: _Pending) -> Connection:
        """One connect: build a connection and open it. Runs on a worker thread.

        The connection is shared through `pending.conn` as soon as it is built, so the last call to
        stop waiting can abort it. A failure releases it and raises. `self._conn` is never touched.
        """
        conn = None
        try:
            conn = self._new()
            with self._lock:
                pending.conn = conn
            conn.open()
        except BaseException:
            if conn is not None:
                _release(conn)
            raise
        return conn

    def _settle(self, pending: _Pending) -> None:
        """Run the attempt `pending` and record its outcome; the worker thread's body.

        The worker owns the outcome whether or not any call still waits: under the lock it
        publishes a success (or hands back the live connection already published, releasing its
        own) or records the failure, then frees the slot and sets `done`. An attempt aborted
        (`_abort`) is never published, even one that opened before its transports were closed: it
        is recorded as failed and released. Every release, and the start of a published
        connection's monitor, happens once the lock is let go.
        """
        try:
            conn = self._attempt(pending)
        except BaseException as exc:
            with self._lock:
                pending.error = exc
                if self._inflight is pending:
                    self._inflight = None
                pending.done.set()
            return
        watch = None
        with self._lock:
            if pending.aborted:
                pending.error = ConnectionAbortedError('the connect attempt was aborted')
                dropped = conn
            else:
                pending.transport, dropped, watch = self._publish(conn)
            if self._inflight is pending:
                self._inflight = None
            pending.done.set()
        if watch is not None:
            watch.start()
        if dropped is not None:
            _release(dropped)

    def _leave(self, pending: _Pending) -> bool:
        """Stop waiting on `pending` at the call's deadline; False when its outcome has just come.

        The last call to leave aborts the attempt (`_abort`), outside the lock. The slot stays
        taken until the worker ends, so a later call joins that same attempt rather than start one.
        """
        with self._lock:
            if pending.done.is_set():
                return False
            pending.waiters -= 1
            last = pending.waiters == 0
        if last:
            self._abort(pending)
        return True

    def _abort(self, pending: _Pending) -> None:
        """End the attempt `pending`, which its last waiting call has just left: close its client's
        transport and every gateway's (`_transports`).

        That ends a key exchange, an authentication or a gateway's channel open within about 0.1 s.
        A step before the client has made its transport (building the connection, name resolution,
        the TCP connect) has nothing to close: it runs to its own end, and its late success is
        published. A step that waits on something else once the transport exists (an SSH-agent
        query, during authentication) has its transport closed, but runs on until that answers; the
        attempt is aborted, so its late outcome, success or failure, is discarded.

        The decision is taken again under the lock, at the moment the abort acts: an attempt whose
        outcome has come is left alone, so a connection it published is never closed, and so is one
        a call has joined since. An attempt with transports to close is marked `aborted` under the
        lock before they are closed, outside it: its worker then never publishes it, and a call that
        joins it never takes its failure as its own.
        """
        with self._lock:
            if pending.done.is_set() or pending.waiters:
                return
            transports = _transports(pending.conn)
            if not transports:
                return
            pending.aborted = True
        for transport in transports:
            try:
                transport.close()
            except Exception:
                pass

    def _ensure_connected(self, deadline: float) -> Transport | str:
        """
        The live transport, reconnecting until `deadline` if the connection is lost; or, on giving
        up, the message `cannot connect to <host>: <cause>`.

        A live connection's transport is returned at once, captured here so another call's reconnect
        cannot swap it out. Every transport returned pokes its connection's liveness monitor
        (`_poked`), so a link that has gone silent is judged dead at most one connect bound after the
        call began. Otherwise the call joins the connect attempt in flight, or starts one on
        a worker thread named `cluster-mcp-reconnect` when there is none, and waits on it
        `ATTEMPT_POLL` at a time, checking its own deadline between waits. After a failure it sleeps
        its backoff, which ends no later than its last start (`FINAL_ATTEMPT_LEAD` before the
        deadline), and tries again. It starts or joins no attempt after that last start: a call
        that reaches it later, as a `write`'s later command can, or whose attempt failed past it,
        gives up at once. It also gives up at the deadline, or at once on a refused authentication
        (`_auth_ending`), with the last cause it saw (`timed out` when none came); an
        authentication the link's loss or its own timeout cut short is retried like any other
        failure. An attempt aborted at another call's deadline is no outcome of this call's: the
        call starts or joins a fresh one at once, unless its last start has passed. A worker that
        cannot start frees the slot and gives up at once with that failure, so the next call starts
        a fresh attempt. An outcome that is not an `Exception` (an interrupt) is raised.
        """
        transport = _live(self._conn)
        if transport is not None:
            return _poked(transport)
        delay = INITIAL_RECONNECT_DELAY
        cause: BaseException = TimeoutError('timed out')
        # Whether the call has just slept a backoff, which ends no later than its last start.
        scheduled = False
        while True:
            with self._lock:
                pending = self._inflight
                if pending is None:
                    transport = _live(self._conn)
                    if transport is not None:
                        return _poked(transport)
                if not scheduled and time.monotonic() >= deadline - FINAL_ATTEMPT_LEAD:
                    return connect_failure_message(self._host, cause)
                scheduled = False
                if pending is not None:
                    pending.waiters += 1
                else:
                    pending = self._inflight = _Pending()
                    try:
                        threading.Thread(target=self._settle, args=(pending,), name='cluster-mcp-reconnect',
                                         daemon=True).start()
                    except BaseException as exc:
                        # A worker that never started would hold the slot for good, and every later
                        # call would wait out its deadline on it: free the slot and end the attempt
                        # with the failure, for this call and any joined to it.
                        self._inflight = None
                        pending.error = exc
                        pending.done.set()
                        if not isinstance(exc, Exception):
                            raise
                        return connect_failure_message(self._host, exc)
            while not _await(pending.done, max(0.0, min(ATTEMPT_POLL, deadline - time.monotonic()))):
                if time.monotonic() >= deadline and self._leave(pending):
                    return connect_failure_message(self._host, cause)
            if pending.error is None:
                return _poked(pending.transport)
            if not isinstance(pending.error, Exception):
                raise pending.error
            if pending.aborted:
                continue
            cause = pending.error
            if _auth_ending(cause) == 'refused':
                return connect_failure_message(self._host, cause)
            now = time.monotonic()
            if now >= deadline - FINAL_ATTEMPT_LEAD:
                return connect_failure_message(self._host, cause)
            time.sleep(min(delay, deadline - FINAL_ATTEMPT_LEAD - now))
            delay = min(delay * 2, MAX_RECONNECT_DELAY)
            scheduled = True

    def _not_run(self, message: str) -> CommandResult:
        """The result of a command that was not run because the call could not reconnect."""
        return CommandResult('', f'cluster-mcp: {message}; the command was not run\n', NOT_STARTED_EXIT_CODE,
                             self._host)

    def run(
        self,
        command: Sequence[str] | str,
        cwd: str | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        """
        Run a command on the remote host under the pinned login bash (see `Executor.run`).

        The program travels as the launcher's fixed bootstrap carrying one base64 word, so the
        remote login shell parses none of it. It starts in the login home (`$HOME`), whatever a
        startup file `cd`s to. Its stdin is empty: the end of it is sent at once, so a remote rc
        file that reads stdin reads nothing. The output is read up to the program's end records,
        however long it takes to arrive after the exit status (`_collect`). A lost connection is
        re-established first, within the bound the class states, and so is one found dead as the
        channel opens (a link gone silent, which the liveness monitor closes): nothing was sent.
        A call that cannot reconnect runs nothing and returns `NOT_STARTED_EXIT_CODE`, its stderr
        `cluster-mcp: cannot connect to <host>: <cause>; the command was not run`. A connection
        lost once the exec request has gone, a silent one included, returns
        `CONNECTION_LOST_EXIT_CODE` with `launch.LOST_NOTE`, never a retry.

        Args:
            command: An argv (each element one literal argument) or a bash script.
            cwd: Working directory; a leading `~` or `~/` is the remote user's home.
            timeout: Seconds to wait; at the deadline the result carries `TIMEOUT_EXIT_CODE`. It
                bounds the command once it has been sent, never the reconnect.

        Returns:
            CommandResult with stdout, stderr, exit_code, and hostname.

        Raises:
            ValueError: The exec string is over the per-argument limit, before connecting.
        """
        return self._run(command, cwd, timeout, deadline=time.monotonic() + self._window)

    def _run(self, command: Sequence[str] | str, cwd: str | None = None, timeout: float | None = None, *,
             deadline: float) -> CommandResult:
        """`run`, reconnecting no later than `deadline`, which the calling method took at its entry."""
        timeout = launch.check_timeout(timeout)
        # The program is given no deadline: the remote clock is not the server's, and `timeout` runs
        # from the command's start, once the connection is made, however long that takes.
        prog, marks = launch.program(command, cwd, start='home')
        wire = launch.ssh_command(prog)
        # A channel that could not open on a lost connection sent nothing, so the call goes back to
        # reconnecting, within the same deadline.
        ran = None
        while ran is None:
            transport = self._ensure_connected(deadline)
            if isinstance(transport, str):
                return self._not_run(transport)
            ran = self._exec(transport, wire, timeout, marks.end)
        out, err, code, note = ran
        out, err, code = launch.separate(out, err, code, marks, note)
        return CommandResult(stdout=launch.decode(out), stderr=launch.decode(err), exit_code=code,
                             hostname=self._host)

    def _exec(self, transport: Transport, wire: str, timeout: float | None,
              end: bytes) -> tuple[bytes, bytes, int, bytes] | None:
        """Run the exec string `wire` on a fresh session channel and collect its output.

        A channel open that fails because the connection was lost (`_gone`) returns None: nothing
        was sent, and the call may reconnect, unless the executor was closed, when it raises. One
        that fails on a live connection raises. The open waits `_open_timeout`. The end of stdin goes
        at once: the channel carries no byte to the command, so nothing the remote login shell's rc
        files run can read anything from it. A connection lost once the request has gone returns
        `CONNECTION_LOST_EXIT_CODE`: the command may have run. A request that fails while the
        connection stays up (`SETTLE` after the failure) was refused: it raises.
        """
        try:
            with _opening(transport):
                chan = transport.open_session(timeout=_open_timeout(transport))
        except (SSHException, EOFError, OSError):
            if self._closed or not _gone(transport):
                raise
            return None
        try:
            try:
                chan.exec_command(wire)
                chan.shutdown_write()
            except (SSHException, EOFError, OSError):
                # Refused by a live server, the command never ran; but once the request has gone on a
                # connection that is then lost, it may have. The transport is first let finish closing:
                # Paramiko wakes this wait before it marks a lost connection inactive.
                transport.join(SETTLE)
                if transport.is_active():
                    raise
                return b'', b'', CONNECTION_LOST_EXIT_CODE, launch.LOST_NOTE
            return _collect(chan, timeout, end)
        finally:
            chan.close()

    def _sftp(self, deadline: float) -> tuple[Transport, SFTPClient] | str:
        """A transport and an SFTP session open on it, reconnecting no later than `deadline`; or, on
        giving up, the message `cannot connect to <host>: <cause>`.

        The session opens in three steps, each a wait on the peer: the channel (waiting
        `_open_timeout`), the `sftp` subsystem, and the version exchange, all made holding the
        connection's liveness monitor's poke (`_opening`). A loss at any of them (`_gone`) has sent no
        file operation, so the call reconnects within its deadline, unless the executor was closed;
        a failure on a live connection raises.
        """
        while True:
            transport = self._ensure_connected(deadline)
            if isinstance(transport, str):
                return transport
            chan = None
            try:
                with _opening(transport):
                    chan = transport.open_session(timeout=_open_timeout(transport))
                    chan.invoke_subsystem('sftp')
                    return transport, SFTPClient(chan)
            except (SSHException, EOFError, OSError):
                if chan is not None:
                    try:
                        chan.close()
                    except Exception:
                        pass
                if self._closed or not _gone(transport):
                    raise

    def write(self, path: str, data: bytes, append: bool = False, parent: str | None = None,
              executable: bool = False) -> CommandResult:
        """
        Write `data` to the remote file `path`, exactly (see `Executor.write`).

        The bytes go by SFTP, never on a command's stdin, into a file of their own (mode 0600) in a
        private directory (mode 0700) made beside the target, on the target's filesystem, every
        write's reply and the close checked, and then its size; their POSIX checksum goes beside
        them. A fixed program then checks the staged file's checksum against it and moves the file
        into place, a rename, so the target is replaced whole or not at all, and keeps its
        permission bits but setuid and setgid (a new file gets the mode `cat >` would give it). An
        existing target the user may not write is refused, as `cat >` refuses it. An append adds
        the staged bytes to the target. A symbolic link is followed to the file it names; one whose
        target's directory does not exist is refused, and stays, and a path that passes through a
        loop of links is refused as `cat >` refuses it (`Too many levels of symbolic links`). A target that is not a regular
        file, or a regular file in a directory this user may not add to, is written through
        instead, from a staging directory in the login home. A transfer that fails or falls short
        leaves the target untouched; the remote filesystem is then asked the reason (`PROBE`). The
        staging directory is removed afterwards, except when the host is lost after the content is
        staged: removing it needs the connection, so the directory (mode 0700, the user's own) can
        then remain beside the target, or in the login home. A connection lost once the SFTP
        session has opened, a silent one included, raises `TransferLost` naming what may remain,
        and so does one the parent's `mkdir` or the place step meets. A lost connection is
        re-established first, and every command the write runs shares one deadline, so a write
        spends at most one reconnect window; one that cannot reconnect writes nothing to the target
        and returns `NOT_STARTED_EXIT_CODE`, as `run` does.

        Raises:
            OSError: The content could not be staged (the target is a directory or a link whose
                target's directory does not exist, its path passes through a loop of links
                (`ELOOP`), its directory is missing or closed, a transfer
                failed or fell short, with the reason); nothing was written.
            TransferLost: The connection was lost once the SFTP session had opened: the transfer
                may be partly made. The target is unchanged while the content is staged, and its
                staging directory may remain; once the place step may have run, an overwrite is
                the old file or the new one, and an append or a write-through may be partial.
        """
        deadline = time.monotonic() + self._window
        if not path:
            # As a shell's `>` with an empty name.
            raise FileNotFoundError(errno.ENOENT, 'No such file or directory', path)
        reached = self._sftp(deadline)
        if isinstance(reached, str):
            return self._not_run(reached)
        transport, sftp = reached
        with sftp:
            try:
                return self._write(sftp, transport, path, data, append, parent, executable, deadline)
            except _Lost as lost:
                raise TransferLost(self._host, 'write', lost.left) from lost
            except (OSError, EOFError, SSHException) as exc:
                if not _cut(sftp, exc):
                    raise
                # What a lost connection may leave, as far as the write had gone.
                raise TransferLost(self._host, 'write', getattr(exc, 'left', f'{path} is unchanged')) from exc

    def _write(self, sftp: SFTPClient, transport: Transport, path: str, data: bytes, append: bool,
               parent: str | None, executable: bool, deadline: float) -> CommandResult:
        """`write`'s body, on its open SFTP session `sftp`: a loss of the connection on the way is
        raised as `_Lost`, or as the step's own exception carrying what it may leave (`left`)."""
        unchanged = f'{path} is unchanged'
        # A parent that is already a directory needs no command, and no login shell's start.
        if parent is not None and not _is_dir(sftp, _remote(parent)):
            made = self._run(launch.fixed_argv(MAKE_PARENT, 'cluster-mcp-write', UserPath(parent)),
                             deadline=deadline)
            if _lost_to(made, transport):
                maybe = 'its parent directory may have been made, and ' if made.exit_code == CONNECTION_LOST_EXIT_CODE else ''
                raise _Lost(f'{maybe}{unchanged} ({_said(made)})')
            if made.exit_code != 0:
                return made
        remote = _remote(path)
        directory = None
        try:
            target, mode, through = _staging(sftp, remote)
            near = '.' if through else posixpath.dirname(target) or '.'
            try:
                directory = _stage_in(near)
                staged = _stage(sftp, directory)
            except OSError as exc:
                if exc.errno not in CLOSED or mode is None or through:
                    raise
                # A writable file in a directory closed to new entries: written through, as before.
                through = True
                directory = _stage_in('.')
                staged = _stage(sftp, directory)
        except (OSError, EOFError, SSHException) as exc:
            if _cut(sftp, exc):
                exc.left = _remains(unchanged, directory)  # type: ignore[union-attr]
                raise
            if not isinstance(exc, OSError):
                raise
            # SFTP reports a loop as a missing file or a bare failure: name it, as `cat >` does.
            if _loops(sftp, remote):
                raise OSError(errno.ELOOP, 'Too many levels of symbolic links', path) from None
            raise
        expected = posixpath.join(directory, EXPECTED)
        lost = False
        try:
            try:
                _upload(sftp, staged, data)
                _upload(sftp, expected, cksum(data).encode('ascii'))
            except Short as exc:
                raise Short(f'the transfer of {len(data)} bytes to {target!r} failed: '
                            f'{self._reason(staged, deadline) or exc}; the file is unchanged') from None
            except (OSError, EOFError, SSHException) as exc:
                lost = _cut(sftp, exc)
                if lost:
                    exc.left = _remains(unchanged, directory)  # type: ignore[union-attr]
                raise
            if append:
                script = PLACE_APPEND
            elif through:
                script = PLACE_THROUGH
            elif mode is not None:
                script = WRITABLE + PLACE
            else:
                script = PLACE
            if executable:
                script += PLACE_EXECUTABLE
            placed = self._run(launch.fixed_argv(VERIFY + script, 'cluster-mcp-write', UserPath(staged),
                                                 UserPath(target), mode or '=rw', UserPath(expected)),
                               deadline=deadline)
            if _lost_to(placed, transport):
                lost = True
                if placed.exit_code == NOT_STARTED_EXIT_CODE:
                    became = unchanged
                elif append:
                    became = f'{target} may hold part of what was appended'
                elif through:
                    became = f'{target} may be truncated or hold part of the file'
                else:
                    became = f'{target} is either the old file or the new one'
                if executable and placed.exit_code == CONNECTION_LOST_EXIT_CODE:
                    became += ', and may not be executable yet'
                raise _Lost(f'{_remains(became, directory)} ({_said(placed)})')
            return placed
        finally:
            # The removal needs the session: on a lost one the staging directory is left
            # (`issues/ssh-write-staging-leftover.md`).
            if not lost and not _down(transport):
                _discard(sftp, directory, staged, expected)

    def _reason(self, staged: str, deadline: float) -> str | None:
        """Why a transfer into `staged` failed, in the remote filesystem's words, or None.

        `PROBE` appends zero bytes to the staged file, which is discarded; when the filesystem is
        full or the quota spent, that fails as the transfer did, and its error names the cause. A
        probe that did not run (no reconnect by the write's `deadline`) gives no reason.
        """
        try:
            probe = self._run(launch.fixed_argv(PROBE, 'cluster-mcp-write', UserPath(staged)), timeout=60,
                              deadline=deadline)
        except Exception:
            return None
        lines = [line for line in probe.stderr.splitlines() if line.strip()]
        if probe.exit_code in (0, TIMEOUT_EXIT_CODE, CONNECTION_LOST_EXIT_CODE, NOT_STARTED_EXIT_CODE) or not lines:
            return None
        return lines[-1].rsplit(': ', 1)[-1].strip() or None

    def put(self, local_path: str, remote_path: str) -> str:
        """
        Upload a file over SFTP and return the absolute remote path written, in the SFTP server's
        canonical form (OpenSSH resolves it through symlinks).

        `local_path` is on the server's side: only a leading `~` or `~/` expands, to this process's
        HOME. In `remote_path` a leading `~` or `~/` is the login home and nothing else expands; a
        remote directory receives the file under its own name.

        Args:
            local_path: Path to local file.
            remote_path: Destination path on remote system.

        Raises:
            ConnectionError: The lost connection could not be re-established within the bound the
                class states: `cannot connect to <host>: <cause>; nothing was transferred`.
            TransferLost: The connection was lost once the SFTP session had opened: the remote
                target may be truncated or hold part of the file.
        """
        deadline = time.monotonic() + self._window
        local = launch.expand_local(local_path)
        reached = self._sftp(deadline)
        if isinstance(reached, str):
            raise ConnectionError(f'{reached}; nothing was transferred')
        _, sftp = reached
        remote = _remote(remote_path)
        with sftp:
            try:
                if _is_dir(sftp, remote):
                    remote = posixpath.join(remote, os.path.basename(local))
                sftp.put(local, remote)
                return sftp.normalize(remote)
            except (OSError, EOFError, SSHException) as exc:
                if not _cut(sftp, exc):
                    raise
                raise TransferLost(self._host, 'upload',
                                   f'{remote} may be truncated or hold part of the file') from exc

    def get(self, remote_path: str, local_path: str) -> str:
        """
        Download a file over SFTP and return the absolute local path written.

        In `remote_path` a leading `~` or `~/` is the login home and nothing else expands.
        `local_path` is on the server's side and taken literally, but for a leading `~` or `~/`
        (this process's HOME); a local directory receives the file under its own name.

        Args:
            remote_path: Path to file on remote system.
            local_path: Destination path on local system.

        Raises:
            ConnectionError: The lost connection could not be re-established within the bound the
                class states: `cannot connect to <host>: <cause>; nothing was transferred`.
            TransferLost: The connection was lost once the SFTP session had opened: the local file
                may be truncated or hold part of the file.
        """
        deadline = time.monotonic() + self._window
        local = launch.expand_local(local_path)
        reached = self._sftp(deadline)
        if isinstance(reached, str):
            raise ConnectionError(f'{reached}; nothing was transferred')
        _, sftp = reached
        remote = _remote(remote_path)
        if os.path.isdir(local):
            local = os.path.join(local, posixpath.basename(remote))
        with sftp:
            try:
                sftp.get(remote, local)
            except (OSError, EOFError, SSHException) as exc:
                if not _cut(sftp, exc):
                    raise
                raise TransferLost(self._host, 'download',
                                   f'{local} may be truncated or hold part of the file') from exc
        return os.path.abspath(local)

    def __enter__(self) -> SSHExecutor:
        """Context manager entry - opens connection."""
        self.open()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Context manager exit - closes connection."""
        self.close()
