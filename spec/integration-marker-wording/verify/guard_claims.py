# Executed probe: every claim the marker descriptions make about the unit guard, run against
# tests/conftest.py itself (loaded as a plugin), plus the routes the guard leaves open, so the
# wording claims nothing the guard does not refuse.
#
# Run from the worktree root (the name is not test_*.py, so the suite never collects it):
#
#   PYTHONPATH=tests uv run pytest -q -p no:cacheprovider -p conftest -c pyproject.toml \
#       --rootdir=. spec/integration-marker-wording/verify/guard_claims.py
#
# Footprint: one pytest process; the `integration` rows start at most one short child each
# (`true` through bin/sandbox.sh) and open one loopback socket pair; under 200 MB. Nothing reaches
# a host other than 127.0.0.1, and nothing outlives the run.
from __future__ import annotations

import asyncio
import concurrent.futures
import multiprocessing
import os
import pwd
import socket
import _socket
import subprocess
import tomllib
from pathlib import Path

import pytest

import conftest

ROOT = Path(conftest.__file__).resolve().parent.parent
SANDBOX = ROOT / 'bin' / 'sandbox.sh'
EARLY_POPEN = subprocess.Popen  # bound at import, before any guard replaces the attribute
EARLY_GETADDRINFO = socket.getaddrinfo


def _child() -> None:
    pass


def _listener() -> tuple[socket.socket, int]:
    srv = socket.socket()
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    return srv, srv.getsockname()[1]


def _raw_connect() -> None:
    srv, port = _listener()
    raw = _socket.socket()
    try:
        raw.connect(('127.0.0.1', port))
    finally:
        raw.close()
        srv.close()


def _udp_send() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.sendto(b'probe', ('127.0.0.1', 9))


async def _async_exec() -> None:
    proc = await asyncio.create_subprocess_exec('true')
    await proc.wait()


async def _async_connect(port: int) -> None:
    await asyncio.open_connection('127.0.0.1', port)


async def _async_lookup() -> None:
    await asyncio.get_running_loop().getaddrinfo('localhost', 80)


# "starts no process": each route a unit test could start one by.
PROCESS = {
    'subprocess.run': lambda: subprocess.run(['true'], check=True),
    'os.system': lambda: os.system('true'),
    'os.fork': lambda: os.fork(),
    'os.posix_spawnp': lambda: os.posix_spawnp('true', ['true'], {}),
    'multiprocessing fork': lambda: multiprocessing.get_context('fork').Process(target=_child).start(),
    'multiprocessing spawn': lambda: multiprocessing.get_context('spawn').Process(target=_child).start(),
    'process pool': lambda: concurrent.futures.ProcessPoolExecutor(1).submit(_child).result(timeout=30),
    'asyncio subprocess': lambda: asyncio.run(_async_exec()),
}

# "opens no network connection (a name lookup included)".
NETWORK = {
    'create_connection loopback': lambda port: socket.create_connection(('127.0.0.1', port), timeout=5),
    'socket.connect loopback': lambda port: socket.socket().connect(('127.0.0.1', port)),
    'asyncio open_connection': lambda port: asyncio.run(_async_connect(port)),
    'getaddrinfo': lambda port: socket.getaddrinfo('localhost', port),
    'asyncio getaddrinfo': lambda port: asyncio.run(_async_lookup()),
}

# Routes the guard leaves open: AGENTS.md names them beside the guard, and the descriptions claim
# no more than a rule. The guard replaces names, so what was bound before the test or sits below the
# names is not refused: a Popen class bound earlier launches, because `subprocess` binds
# `_posixsubprocess.fork_exec` at import; `_socket` connects below `socket.socket.connect`; UDP
# sends without connecting; an early-bound `getaddrinfo` and the gethostbyname family look names up.
OPEN = {
    'early-bound Popen': lambda: EARLY_POPEN([str(SANDBOX), 'true']).wait(),
    'conftest.REAL_POPEN': lambda: conftest.REAL_POPEN([str(SANDBOX), 'true']).wait(),
    'raw _socket connect': _raw_connect,
    'udp sendto': _udp_send,
    'early-bound getaddrinfo': lambda: EARLY_GETADDRINFO('localhost', 80),
    'gethostbyname': lambda: socket.gethostbyname('localhost'),
    'gethostbyname_ex': lambda: socket.gethostbyname_ex('localhost'),
    'gethostbyaddr': lambda: socket.gethostbyaddr('127.0.0.1'),
    'getnameinfo': lambda: socket.getnameinfo(('127.0.0.1', 80), 0),
}


@pytest.fixture(scope='module')
def launched_before_the_guard() -> int:
    # A wider fixture runs before the function-scoped guard is active.
    return subprocess.run([str(SANDBOX), 'true']).returncode


@pytest.mark.unit
@pytest.mark.parametrize('route', sorted(PROCESS))
def test_unit_refuses_process(route: str, guard) -> None:
    with pytest.raises(OSError, match='unit guard'):
        PROCESS[route]()
    assert guard.refused, route
    guard.refused.clear()


@pytest.mark.unit
@pytest.mark.parametrize('route', sorted(NETWORK))
def test_unit_refuses_connection_and_lookup(route: str, guard) -> None:
    srv, port = _listener()  # listening is not refused; reaching it is
    try:
        with pytest.raises(OSError, match='unit guard'):
            NETWORK[route](port)
    finally:
        srv.close()
    assert guard.refused, route
    guard.refused.clear()


@pytest.mark.unit
@pytest.mark.parametrize('route', sorted(OPEN))
def test_unit_leaves_open(route: str, guard) -> None:
    OPEN[route]()
    assert guard.refused == [], route


@pytest.mark.unit
def test_unit_leaves_open_a_wider_fixture(launched_before_the_guard: int, guard) -> None:
    assert launched_before_the_guard == 0 and guard.active and guard.refused == []


@pytest.mark.unit
def test_unit_sees_no_real_home(tmp_path: Path) -> None:
    real = pwd.getpwuid(os.getuid()).pw_dir
    assert os.environ['HOME'] == str(tmp_path / 'home') != real
    assert Path.home() == tmp_path / 'home' and os.path.expanduser('~') != real
    for var in ('XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
        assert Path(os.environ[var]).is_relative_to(tmp_path / 'home'), var
    for var in conftest.BLANKED_ENV:
        assert var not in os.environ, var
    # Left open, so not claimed: the password database still names the real home directory.
    assert pwd.getpwuid(os.getuid()).pw_dir == real


@pytest.mark.integration
def test_integration_guard_is_inactive(guard) -> None:
    assert guard.active is False
    assert subprocess.run([str(SANDBOX), 'true']).returncode == 0
    srv, port = _listener()
    try:
        socket.create_connection(('127.0.0.1', port), timeout=5).close()
    finally:
        srv.close()


@pytest.mark.integration
def test_integration_cannot_take_executes_as_unit() -> None:
    # The executes fixture refuses a unit test; integration is what may launch for real.
    text = Path(conftest.__file__).read_text()
    assert "raise pytest.UsageError('executes launches processes: mark the test integration')" in text


@pytest.mark.unit
def test_the_static_launch_check_does_not_read_real_popen() -> None:
    # tests/test_ssh_exec.py's `_host` runs hdiutil this way, outside bin/sandbox.sh.
    import test_hygiene
    source = "from conftest import REAL_POPEN\n\ndef test_x():\n    REAL_POPEN(['hdiutil', 'info'])\n"
    assert test_hygiene.sandbox_violations(source, 'planted.py') == []
    assert test_hygiene.sandbox_violations(source.replace('REAL_POPEN(', 'subprocess.Popen(').replace(
        'from conftest import REAL_POPEN', 'import subprocess'), 'planted.py') != []


# What each description claims, and the rows above that prove it. Every claim must appear in the
# description word for word; a claim not listed here is not proven.
CLAIMS = {
    'unit': ['starts no process', 'opens no network connection (a name lookup included)', 'sees no real HOME',
             'the unit guard holds it to that'],
    'integration': ['needs what a unit test is refused', 'a process', 'a network connection or name lookup',
                    'the real HOME', 'itself or through a fixture or helper',
                    'every process it launches goes through bin/sandbox.sh'],
}
REFUSED_WORDS = {'unit': ['fast'], 'integration': ['CLI', 'drives']}


@pytest.mark.unit
@pytest.mark.parametrize('name', sorted(CLAIMS))
def test_the_descriptions_make_the_proven_claims(name: str) -> None:
    markers = tomllib.loads((ROOT / 'pyproject.toml').read_text())['tool']['pytest']['ini_options']['markers']
    described = dict(m.split(': ', 1) for m in markers)
    assert sorted(described) == ['integration', 'unit']
    missing = [claim for claim in CLAIMS[name] if claim not in described[name]]
    assert missing == [], missing
    kept = [word for word in REFUSED_WORDS[name] if word.lower() in described[name].lower()]
    assert kept == [], kept
