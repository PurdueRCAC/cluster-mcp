# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The `ssh` backend's liveness monitor (`ssh._Liveness`), which notices a link that dies silently.

The `unit` rows drive the decision on a fake clock: a probe is due after one connect bound of quiet,
and at once for a call (the poke); with nothing heard since a probe went it is dead at twice the
bound less `VERDICT_MARGIN` for a background probe, or one bound after a waiting call's poke,
whichever is first, and never before; anything heard answers it; a poke stays latched past an answer
to a probe handed over before it, and never moves the probe already out; the priming probe is never
judged; and a probe handed over while the sender is stuck still counts. The activity hook stamps
nothing on a read that raises; the bound is the connection's own; only a Paramiko transport is
watched; a dead verdict closes the outermost gateway hop first; and a poke reaches the monitor of
the transport it is given. The doc pin holds the texts that state the monitor's figures to the code.

The `integration` rows use the loopback server (`tests/ssh_server.py`): the hook, on a real Paramiko
client, stamps every message, `REQUEST_FAILURE` included, but the one read in progress as it went in;
and `close()` leaves no monitor thread running and starts no reconnect for a call it wakes.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import paramiko
import pytest

from cluster_mcp.core.executor import ssh
from cluster_mcp.core.executor.ssh import SSHExecutor
from ssh_server import LOOPBACK, USER, LoopbackSSH, SilentLink, _key

B = 15.0
MARGIN = ssh.VERDICT_MARGIN
MONITOR_THREADS = ('cluster-mcp-liveness', 'cluster-mcp-probe')
# Real seconds a row waits for a thread to end, or for a reply on the loopback link.
THREAD_END = 2.0
REPLY_WAIT = 5.0


class Clock:
    """The monitor's clock, moved by the row."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    made = Clock()
    monkeypatch.setattr(ssh, '_liveness_clock', made)
    return made


class Sends:
    """A transport's stand-in that records each message sent, or holds the send until released."""

    def __init__(self, hold: bool = False) -> None:
        self.sent: list[bytes] = []
        self.started = threading.Event()
        self.release = threading.Event()
        if not hold:
            self.release.set()
        self.active = True
        self.packetizer = SimpleNamespace(read_message=lambda: (0, None))
        self.closed: list[str] = []

    def is_active(self) -> bool:
        return self.active

    def _send_user_message(self, message: paramiko.Message) -> None:
        self.started.set()
        self.release.wait(THREAD_END * 5)
        self.sent.append(message.asbytes())


def _conn(transport: Any = None, connect_timeout: float | None = None, gateway: Any = None) -> SimpleNamespace:
    transport = transport if transport is not None else Sends()
    return SimpleNamespace(transport=transport, connect_timeout=connect_timeout, connect_kwargs={},
                           client=SimpleNamespace(get_transport=lambda: transport), gateway=gateway)


def _monitor(clock: Clock, bound: float = B) -> ssh._Liveness:
    return ssh._Liveness(_conn(connect_timeout=bound), LOOPBACK)


def _sending(monitor: ssh._Liveness) -> None:
    """Start `monitor`'s sender alone, so the row's own steps are the only decisions made."""
    threading.Thread(target=monitor._sender, name='cluster-mcp-probe', daemon=True).start()


# -- The verdict, as a pure function of the state and the time.

@pytest.mark.unit
def test_a_probe_is_due_after_a_bound_of_quiet_and_at_once_for_a_poke() -> None:
    assert ssh._verdict(0.0, None, None, B - 0.01, B) is None, 'a probe went before a bound of quiet'
    assert ssh._verdict(0.0, None, None, B, B) == 'probe', 'no probe went after a bound of quiet'
    assert ssh._verdict(0.0, None, 0.5, 0.5, B) == 'probe', 'a poke must send a probe at once'


@pytest.mark.unit
def test_a_background_probe_is_dead_at_twice_the_bound_less_the_margin() -> None:
    out = 10.0
    due = out + 2 * B - MARGIN
    assert ssh._verdict(out - 1, out, None, due - 0.01, B) is None, 'judged dead before its verdict'
    assert ssh._verdict(out - 1, out, None, due, B) == 'dead', 'a background probe outlived its verdict'
    assert due - out == 29.0, 'the stated background verdict is 29 s at the default bound'


@pytest.mark.unit
def test_a_waiting_call_has_its_verdict_one_bound_after_its_poke() -> None:
    out, poked = 10.0, 14.0
    assert ssh._verdict(out - 1, out, poked, poked + B - 0.01, B) is None, 'judged dead before the poke was a bound old'
    assert ssh._verdict(out - 1, out, poked, poked + B, B) == 'dead', 'a waiting call outlived its verdict'
    # A poke that predates the probe (the probe it asked for): the verdict is a bound after the probe.
    assert ssh._verdict(9.0, out, 9.5, out + B - 0.01, B) is None, 'judged dead before the probe was a bound old'
    assert ssh._verdict(9.0, out, 9.5, out + B, B) == 'dead', 'a waiting call outlived the verdict on its probe'
    # Whichever comes first: a poke late in a background probe's wait never puts its verdict off.
    late = out + 2 * B - MARGIN - 1
    assert ssh._verdict(9.0, out, late, out + 2 * B - MARGIN, B) == 'dead', 'a late poke put the verdict off'


@pytest.mark.unit
def test_anything_heard_since_the_probe_went_is_an_answer() -> None:
    out = 10.0
    for heard in (out, out + 0.01, out + 3 * B):
        assert ssh._verdict(heard, out, None, out + 3 * B, B) != 'dead', f'heard at {heard} and still judged dead'


# -- The monitor's state, stepped on the fake clock.

@pytest.mark.unit
def test_an_answered_probe_clears_and_the_next_is_due_a_bound_later(clock: Clock) -> None:
    monitor = _monitor(clock)
    clock.now += B
    assert monitor.step(clock.now) == 'probe'
    out = monitor.out
    clock.now += 1
    monitor.heard = clock.now
    assert monitor.step(clock.now) is None and monitor.out is None, 'an answered probe stayed out'
    clock.now += B - 0.01
    assert monitor.step(clock.now) is None
    clock.now += 0.01
    assert monitor.step(clock.now) == 'probe' and monitor.out == clock.now != out


@pytest.mark.unit
def test_a_poke_stays_latched_past_an_answer_to_an_earlier_probe(clock: Clock) -> None:
    monitor = _monitor(clock)
    clock.now += B
    assert monitor.step(clock.now) == 'probe'
    clock.now += 1
    monitor.poke()
    poked = monitor.poked
    # The reply to the probe handed over before the poke: it proves nothing about the link now.
    monitor.heard = clock.now + 0.01
    clock.now += 0.02
    assert monitor.step(clock.now) == 'probe', 'a reply in transit consumed the poke'
    assert monitor.poked == poked and monitor.out == clock.now
    clock.now += 0.5
    monitor.heard = clock.now
    clock.now += 0.01
    monitor.step(clock.now)
    assert monitor.poked is None and monitor.out is None, 'the probe sent for the poke was answered, and it stayed'


@pytest.mark.unit
def test_a_poke_never_moves_the_probe_out(clock: Clock) -> None:
    monitor = _monitor(clock)
    clock.now += B
    monitor.step(clock.now)
    out = monitor.out
    for _ in range(4):
        clock.now += B / 2
        monitor.poke()
        monitor.step(clock.now)
        assert monitor.out == out or monitor.dead, 'a poke moved the probe already out'
    assert monitor.dead, f'calls every {B / 2} s put the verdict off past {2 * B} s'


@pytest.mark.unit
def test_the_priming_probe_is_never_judged(clock: Clock) -> None:
    transport = Sends()
    monitor = ssh._Liveness(_conn(transport), LOOPBACK)
    _sending(monitor)
    try:
        limit = time.monotonic() + THREAD_END
        while not transport.sent:
            assert time.monotonic() < limit, 'no priming probe was sent'
            time.sleep(0.01)
        assert monitor.out is None, 'the priming probe is judged'
        clock.now += B - 0.01
        assert monitor.step(clock.now) is None and not monitor.dead, 'the unanswered priming probe was judged'
        message = paramiko.Message(transport.sent[0])
        assert (message.get_byte(), message.get_text(), message.get_boolean()) == \
            (paramiko.common.cMSG_GLOBAL_REQUEST, ssh.PROBE_REQUEST, True)
    finally:
        monitor.stop()


@pytest.mark.unit
def test_a_probe_handed_over_while_the_sender_is_stuck_counts(clock: Clock) -> None:
    transport = Sends(hold=True)
    monitor = ssh._Liveness(_conn(transport), LOOPBACK)
    _sending(monitor)
    try:
        assert transport.started.wait(THREAD_END), 'the sender never began the priming probe'
        clock.now += 1
        monitor.poke()
        assert monitor.step(clock.now) == 'probe', 'a probe handed over to a stuck sender did not count'
        assert monitor.out == clock.now, 'a probe handed over to a stuck sender did not count'
        clock.now += B
        assert monitor.step(clock.now) == 'dead', 'the stuck probe never met its verdict'
        transport.release.set()
        limit = time.monotonic() + THREAD_END
        while len(transport.sent) < 2:
            assert time.monotonic() < limit, f'the freed sender sent {len(transport.sent)} probes, not the one more'
            time.sleep(0.01)
    finally:
        monitor.stop()
        transport.release.set()


@pytest.mark.unit
def test_a_call_waiting_on_an_open_keeps_its_poke(clock: Clock) -> None:
    # A reply to one step of an open answers the probe, but the call still waits on the next step:
    # the poke stays, the next probe goes at once, and each is judged a bound after it went.
    monitor = _monitor(clock)
    clock.now += 1
    with monitor.opening():
        assert monitor.step(clock.now) == 'probe'
        clock.now += 0.01
        monitor.heard = clock.now
        clock.now += 0.01
        assert monitor.step(clock.now) == 'probe', 'an answer during an open cleared the waiting poke'
        out = monitor.out
        clock.now += B - 0.01
        assert monitor.step(clock.now) is None
        clock.now += 0.01
        assert monitor.step(clock.now) == 'dead' and clock.now == out + B
    second = _monitor(clock)
    with second.opening():
        second.step(clock.now)
    clock.now += 0.01
    second.heard = clock.now
    clock.now += 0.01
    assert second.step(clock.now) is None and second.poked is None, 'the poke outlived the open'


@pytest.mark.unit
def test_the_hook_stamps_nothing_on_a_read_that_raises(clock: Clock) -> None:
    def read() -> Any:
        raise paramiko.ssh_exception.SSHException('a pending key exchange')

    packetizer = SimpleNamespace(read_message=read)
    monitor = SimpleNamespace(heard=0.0)
    ssh._hook(packetizer, monitor)  # type: ignore[arg-type]
    with pytest.raises(paramiko.ssh_exception.SSHException):
        packetizer.read_message()
    assert monitor.heard == 0.0, 'a read that raised was stamped as heard'
    packetizer_ok = SimpleNamespace(read_message=lambda: (82, None))
    ssh._hook(packetizer_ok, monitor)  # type: ignore[arg-type]
    assert packetizer_ok.read_message() == (82, None) and monitor.heard == clock.now


@pytest.mark.unit
def test_the_monitor_takes_the_connections_own_bound(clock: Clock) -> None:
    monitor = ssh._Liveness(_conn(connect_timeout=40), LOOPBACK)
    assert monitor.bound == 40, f'a 40 s connect timeout gave the monitor a {monitor.bound} s bound'
    clock.now += 39
    assert monitor.step(clock.now) is None
    clock.now += 1
    assert monitor.step(clock.now) == 'probe'
    clock.now += 2 * 40 - MARGIN
    assert monitor.step(clock.now) == 'dead'


@pytest.mark.unit
def test_a_fake_connection_gets_no_monitor() -> None:
    fake = SimpleNamespace(transport=SimpleNamespace(active=True), connect_timeout=None, connect_kwargs={})
    assert ssh._Liveness.of(fake, LOOPBACK) is None
    assert ssh._monitor_of(fake.transport) is None


class Hop:
    """A transport's stand-in that records when it was closed."""

    def __init__(self, name: str, order: list[str]) -> None:
        self.name, self.order = name, order

    def close(self) -> None:
        self.order.append(self.name)


@pytest.mark.unit
def test_a_dead_verdict_closes_the_outermost_hop_first() -> None:
    order: list[str] = []
    outer = SimpleNamespace(client=SimpleNamespace(get_transport=lambda: Hop('outer', order)), gateway=None)
    middle = SimpleNamespace(client=SimpleNamespace(get_transport=lambda: Hop('middle', order)), gateway=outer)
    inner = Sends()
    conn = SimpleNamespace(transport=inner, connect_timeout=None, connect_kwargs={}, gateway=middle,
                           client=SimpleNamespace(get_transport=lambda: Hop('inner', order)))
    ssh._Liveness(conn, LOOPBACK)._close()
    assert order == ['outer', 'middle', 'inner'], f'the hops were closed {order}, not the outermost first'


@pytest.mark.unit
def test_a_poke_reaches_the_monitor_of_the_transport_given(clock: Clock) -> None:
    one, other = _monitor(clock), _monitor(clock)
    with ssh._opening(one.transport):
        assert (one.poked, other.poked, one.waiting, other.waiting) == (clock.now, None, 1, 0), \
            'an open poked another monitor, or not its own'
    assert one.waiting == 0
    with ssh._opening(SimpleNamespace()):
        pass


# What a transfer cut short says it may leave, by what was cut.
TRANSFER_TEXTS = {
    'upload': ('upload', 'x.txt may be truncated or hold part of the file'),
    'download': ('download', '/tmp/got may be truncated or hold part of the file'),
    'write': ('write', '~/x is unchanged, and its staging directory ./.cluster-mcp-0 may remain'),
}


@pytest.mark.unit
@pytest.mark.parametrize('cut', list(TRANSFER_TEXTS))
def test_a_lost_transfer_names_the_host_and_what_may_remain(cut: str) -> None:
    during, remains = TRANSFER_TEXTS[cut]
    lost = ssh.TransferLost('login.example', during, remains)
    assert isinstance(lost, ConnectionError) and isinstance(lost, OSError)
    assert str(lost) == (f'the connection to login.example was lost during the {during}; the transfer may be '
                         f'partly made: {remains}')
    assert ssh._remains('~/x is unchanged', None) == '~/x is unchanged'
    assert ssh._remains('~/x is unchanged', 'd') == '~/x is unchanged, and its staging directory d may remain'


class LostSession:
    """An SFTP session whose connection is gone: every request fails as a send on a closed channel
    does, with no errno (Paramiko's `Socket is closed`)."""

    def __init__(self) -> None:
        transport = SimpleNamespace(is_active=lambda: False, join=lambda timeout=None: None)
        self.channel = SimpleNamespace(closed=True, get_transport=lambda: transport)

    def get_channel(self) -> SimpleNamespace:
        return self.channel

    def _closed(self, *args: Any, **kwargs: Any) -> Any:
        raise OSError('Socket is closed')

    stat = lstat = normalize = readlink = chmod = _closed

    def open(self, *args: Any) -> SimpleNamespace:
        return SimpleNamespace(set_pipelined=self._closed, write=self._closed, flush=self._closed,
                               close=lambda: None)


# Each SFTP step that reads a failure as the server's answer, and the call that meets a lost session.
LOSS_SITES = {
    'upload': lambda sftp: ssh._upload(sftp, 'staged', b'data'),
    'is-dir': lambda sftp: ssh._is_dir(sftp, 'somewhere'),
    'loops': lambda sftp: ssh._loops(sftp, 'a/b'),
}


@pytest.mark.unit
@pytest.mark.parametrize('site', list(LOSS_SITES))
def test_a_lost_session_is_never_read_as_the_servers_answer(site: str) -> None:
    # The loss is decided before the step's own reading of a failure: a short transfer (whose cause
    # the write would then ask a reconnect for), a path that is not a directory, a path with no loop.
    try:
        got: Any = LOSS_SITES[site](LostSession())
    except OSError as exc:
        got = exc
    if not (type(got) is OSError and str(got) == 'Socket is closed'):
        pytest.fail(f"{site} read a lost session as the server's answer: {got!r}")


# -- Against the loopback server.

@pytest.fixture
def server(tmp_path: Path) -> Iterator[LoopbackSSH]:
    home = (tmp_path / 'home').resolve()
    home.mkdir()
    with LoopbackSSH(home, '/bin/bash', tmp_path) as made:
        yield made


class Stamps:
    """A monitor's stand-in that counts what the hook stamps."""

    def __init__(self) -> None:
        self.count = 0

    @property
    def heard(self) -> float:
        return 0.0

    @heard.setter
    def heard(self, value: float) -> None:
        self.count += 1


def _probe(transport: paramiko.Transport) -> None:
    message = paramiko.Message()
    message.add_byte(paramiko.common.cMSG_GLOBAL_REQUEST)
    message.add_string(ssh.PROBE_REQUEST)
    message.add_boolean(True)
    transport._send_user_message(message)


@pytest.mark.integration
def test_the_hook_stamps_every_message_on_a_real_client(server: LoopbackSSH) -> None:
    # The installed Paramiko reads every message at the one call site the hook wraps: each probe's
    # `REQUEST_FAILURE` is stamped, but the read already in progress as the hook goes in.
    sock = socket.create_connection((LOOPBACK, server.port))
    transport = paramiko.Transport(sock)
    try:
        transport.start_client(timeout=REPLY_WAIT)
        transport.auth_publickey(USER, _key('client'))
        stamps, kinds = Stamps(), []
        ssh._hook(transport.packetizer, stamps)  # type: ignore[arg-type]
        inner = transport.packetizer.read_message

        def recorded() -> Any:
            got = inner()
            kinds.append(got[0])
            return got

        transport.packetizer.read_message = recorded
        for _ in range(3):
            _probe(transport)
        limit = time.monotonic() + REPLY_WAIT
        while stamps.count < 2:
            assert time.monotonic() < limit, f'{stamps.count} of the replies after the first were stamped'
            time.sleep(0.01)
        time.sleep(0.2)
        assert stamps.count == 2, f'{stamps.count} replies stamped of three: the read in progress is the one missed'
        assert kinds == [paramiko.common.MSG_REQUEST_FAILURE] * 2, f'the replies read were {kinds}'
    finally:
        transport.close()


@pytest.mark.integration
def test_close_leaves_no_monitor_and_starts_no_reconnect(server: LoopbackSSH, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh, 'CONNECT_TIMEOUT', 2)
    link = SilentLink(server)
    before = set(threading.enumerate())
    executor = link.executor()
    try:
        assert [t.name for t in threading.enumerate() if t.name in MONITOR_THREADS and t not in before], \
            'no liveness monitor runs for a published connection'
        link.go_silent()
        raised: list[BaseException] = []

        def calling() -> None:
            try:
                executor.run(['true'])
            except BaseException as exc:
                raised.append(exc)

        call = threading.Thread(target=calling, daemon=True)
        call.start()
        time.sleep(0.3)
        executor.close()
        call.join(THREAD_END)
        assert not call.is_alive(), 'a call close() woke still runs'
        assert raised, 'a call that close() woke returned, as if it had run'
        limit = time.monotonic() + THREAD_END
        while left := [t.name for t in threading.enumerate() if t not in before and t.is_alive()
                       and (t.name in MONITOR_THREADS or t.name == 'cluster-mcp-reconnect')]:
            assert time.monotonic() < limit, f'threads still running {THREAD_END} s after close(): {left}'
            time.sleep(0.01)
        assert (len(link.opened), link.held) == (1, 0), \
            f'a call close() woke reconnected: {len(link.opened) + link.held} connections made'
    finally:
        executor.close()
        link.close()


# -- The doc pin.

# The silent link, as the SSHExecutor docstring and the AGENTS.md footgun state it, word for word.
LIVENESS_TEXT = (
    'A link that dies with no reset still reads as connected, so a liveness monitor watches each published '
    'connection. It stamps every message the peer sends, and sends a probe (`PROBE_REQUEST`, a global request '
    'that wants a reply) once nothing has been heard for the connect bound B, and at once when a call starts using '
    'the connection; the first probe is never judged. A probe with nothing at all heard since it went is judged '
    'dead B after the poke of a call that started while it was out, so a call that starts on a silent link notices '
    'it at most B after its start, and a background probe after 2B − `VERDICT_MARGIN` (29 s with the default '
    'bound), so a call in flight ends at most 3B − 0.55 s after the last message heard, inside the 3B bound. A '
    'call that starts during a stall ends the stalled call too, at its own verdict. On a dead verdict the monitor '
    "closes the connection's transports, the outermost gateway hop first, and every wait on it ends: a channel "
    'open that fails on a lost connection has sent nothing, so the call reconnects within its deadline; from the '
    'exec request on nothing is retried, and a command cut short returns `CONNECTION_LOST_EXIT_CODE`, with or '
    'without a timeout, unless its own timeout came first. Nothing merely quiet is cut, since any message proves '
    'the link live, while the peer answers within the background verdict: at the default bound, a quiet command '
    'survives the peer answering nothing for 29 s after a probe, and a transfer while some reply arrives at least '
    'every 44 s.')

# A transfer the silent link cuts, as the SSHExecutor docstring and the AGENTS.md footgun state it.
TRANSFER_TEXT = (
    "A transfer's SFTP session opens with the same retry, its three steps (the channel, the `sftp` subsystem and "
    "the version exchange) holding the call's poke, so each probe sent while it waits is judged B after it went. "
    'Once the session has opened, a loss raises `TransferLost`, a `ConnectionError` naming the host that says the '
    'transfer may be partly made and what may remain: for `put`, the remote target, truncated or holding part of '
    'the file; for `get`, the local file, likewise; for `write`, the target unchanged and the staging directory '
    "that may remain, or, when its parent's `mkdir` or its place step meets the loss, what that step can leave (an "
    'overwrite is the old file or the new one, an append or a write-through may be partial). The loss is decided '
    "by state before any handler that would read it as the server's answer, and a lost write leaves its staging "
    'directory (`issues/ssh-write-staging-leftover.md`).')

# What AGENTS.md §2 and the README say of a transfer cut short.
SECTION_2_TRANSFER = ('raises `ssh.TransferLost`', 'may be partly made', 'the staging directory named',
                      "`put`'s remote target, or `get`'s local file, may be truncated")
README_TRANSFER = ('the transfer may be partly made', 'issues/ssh-write-staging-leftover.md')

# The figures the README states, at the default bound.
README_FIGURES = ('15 s of quiet', "15 s after a\ncall's start", '29 s after a background probe', '44.45 s',
                  'within 29 s', 'every 44 s', '45 s')


def _section(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end, text.index(start))]


@pytest.mark.unit
def test_liveness_texts_state_the_monitor() -> None:
    root = Path(__file__).resolve().parent.parent
    agents = (root / 'AGENTS.md').read_text()
    texts = {
        'the SSHExecutor docstring': SSHExecutor.__doc__ or '',
        "AGENTS.md's executor/ssh.py footgun": _section(agents, '- **`executor/ssh.py`**', '- **`__init__.py`**'),
    }
    missing = [name for name, text in texts.items() if LIVENESS_TEXT not in ' '.join(text.split())]
    assert missing == [], f'a text does not state the silent link as the monitor does: {missing}'
    missing = [name for name, text in texts.items() if TRANSFER_TEXT not in ' '.join(text.split())]
    assert missing == [], f'a text does not state what a transfer cut short raises and leaves: {missing}'
    section = ' '.join(_section(agents, '### 2. Executor Protocol', '### 3.').split())
    assert [part for part in SECTION_2_TRANSFER if part not in section] == [], 'AGENTS.md §2 does not state TransferLost'
    readme = (root / 'README.md').read_text()
    assert [part for part in README_TRANSFER if part not in readme] == [], 'the README does not state a transfer cut short'
    assert ssh.TransferLost.__mro__[1] is ConnectionError
    absent = [figure for figure in README_FIGURES if ' '.join(figure.split()) not in ' '.join(readme.split())]
    assert absent == [], f'the README does not state {absent}'
    bound = ssh.CONNECT_TIMEOUT
    figures = (bound, 2 * bound - ssh.VERDICT_MARGIN, 3 * bound - ssh.VERDICT_MARGIN,
               ssh.RECONNECT_FACTOR * bound, round(ssh.VERDICT_MARGIN - 0.45, 2), ssh.PROBE_REQUEST)
    assert figures == (15, 29.0, 44.0, 45, 0.55, 'keepalive@openssh.com'), \
        f'the texts state 15 s, 29 s, 44 s, 45 s, 0.55 s and the probe, but the code has {figures}'

