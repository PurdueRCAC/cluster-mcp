# Review cycle 2, finding 3: every statement this cycle makes about what the static launch check reads
# and what the unit guard leaves open is true of every route an executed probe finds.
#
# Run from the worktree root through remediation/checks.sh, which exports the sentinel below:
#
#   sh spec/integration-marker-wording/remediation/checks.sh F7
#
# The static probe runs the staged `sandbox_violations` on each launch form below, outside a `unit`
# function, and holds the class statement to it: a form is read exactly when it is a call to a
# launcher the check's docstring lists, through the module or a name imported from it. The guard
# probe runs under tests/conftest.py (loaded as a plugin) in a `unit` test, on the routes the
# review's probe found open beyond those verify/guard_claims.py and F1-guard-wording.py prove: names
# below the replaced ones, sends and lookups it does not replace, and values that still name the
# real home. Every route either probe finds open must be named in issues/marker-rule-gaps.md, and
# AGENTS.md must state each check's gap as the class that covers them. Launches go through
# bin/sandbox.sh and run `true`; sockets stay on 127.0.0.1. Staged text is read at import.
#
# Footprint: one pytest process, at most one short child at a time; under 150 MB; nothing outlives it.
from __future__ import annotations

import ast
import ctypes
import os
import posix
import pwd
import site
import socket
import _socket
import subprocess
from pathlib import Path

import pytest

import conftest


def staged(name: str) -> str:
    return subprocess.run(['git', 'show', f':{name}'], capture_output=True, text=True, check=True).stdout


def flat(text: str) -> str:
    return ' '.join(text.split())


SANDBOX = Path(conftest.__file__).resolve().parent.parent / 'bin' / 'sandbox.sh'
AGENTS, GAPS = staged('AGENTS.md'), flat(staged('issues/marker-rule-gaps.md'))
HYGIENE = staged('tests/test_hygiene.py')
STARTED_HOME = os.environ['HOME']  # read at import, before the guard replaces it
SENTINEL = '/nonexistent/marker-f7/GNUPGHOME'

NS: dict = {'ast': ast}
exec(compile(HYGIENE[HYGIENE.index('# Calls that start a process, by module'):HYGIENE.index('@pytest.mark.unit\ndef test_cli_drives_are_sandboxed')],
             'test_hygiene.py', 'exec'), NS)

# Each launch form: (source, a call to a listed launcher through its module or an imported name?, the
# words issues/marker-rule-gaps.md names it by when it is unread).
FORMS: dict[str, tuple[str, bool, str | None]] = {
    'subprocess.run': ('import subprocess\nsubprocess.run(["x"])\n', True, None),
    'aliased module': ('import subprocess as sp\nsp.check_output(["x"])\n', True, None),
    'imported name': ('from subprocess import Popen as P\nP(["x"])\n', True, None),
    'os.system': ('import os\nos.system("x")\n', True, None),
    'os.execv': ('import os\nos.execv("x", ["x"])\n', True, None),
    'os.posix_spawnp': ('import os\nos.posix_spawnp("x", ["x"], {})\n', True, None),
    'asyncio.create_subprocess_shell': ('import asyncio\nasyncio.create_subprocess_shell("x")\n', True, None),
    'conftest.REAL_POPEN': ('from conftest import REAL_POPEN\nREAL_POPEN(["x"])\n', False, 'conftest.REAL_POPEN'),
    'bound by assignment': ('import subprocess\nrun = subprocess.run\nrun(["x"])\n', False, 'bound by assignment'),
    'getattr': ('import subprocess\ngetattr(subprocess, "run")(["x"])\n', False, "getattr(subprocess, 'run')"),
    'Popen subclass': ('import subprocess\nclass P(subprocess.Popen):\n    pass\nP(["x"])\n', False, '`Popen` subclass'),
    'pty.spawn': ('import pty\npty.spawn(["x"])\n', False, '`pty.spawn`'),
    'pty.fork': ('import pty\npty.fork()\n', False, '`pty.fork`'),
    'os.fork': ('import os\nos.fork()\n', False, '`os.fork`'),
    'os.forkpty': ('import os\nos.forkpty()\n', False, '`os.forkpty`'),
    'multiprocessing.Process': ('import multiprocessing\nmultiprocessing.Process(target=print).start()\n', False,
                                '`multiprocessing.Process`'),
    'posix.system': ('import posix\nposix.system("x")\n', False, '`posix.system`'),
    '_posixsubprocess.fork_exec': ('import _posixsubprocess\n_posixsubprocess.fork_exec()\n', False,
                                   '`_posixsubprocess.fork_exec`'),
    'loop.subprocess_exec': ('import asyncio\nasync def f(loop):\n    await loop.subprocess_exec(asyncio.SubprocessProtocol, "x")\n',
                             False, "event loop's `subprocess_exec`"),
}
# The class statement, as each place says it.
STATIC_CLASS = {
    'the commands block': 'It reads only a call to a launcher its docstring lists, through the module or a name '
                          'imported from it, so no other route to a process is read either',
    'the tests/test_hygiene.py entry': 'it reads only a call to a launcher its docstring lists, through the module or a '
                                       'name imported from it, so no other route to a process is read either',
}
GUARD_CLASS = ('The guard refuses by name: a route to a process, the network or the real home that goes through no '
               'name it replaces reaches past it, and the seed lists each one an executed probe found.')
HOME_CLASS = ('so does any other variable the shell exported with a path under it (`GNUPGHOME`, say), and a value '
              'computed from it before the test (`site.USER_BASE`) keeps it')


def _udp_sendmsg() -> None:
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(('127.0.0.1', 0))
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
            tx.sendmsg([b'probe'], [], 0, rx.getsockname())
    finally:
        rx.close()


def _posix_spawn() -> int:
    pid = posix.posix_spawn(str(SANDBOX), [str(SANDBOX), 'true'], dict(os.environ))
    return os.waitpid(pid, 0)[1]


# Routes beyond those the frozen probe proves, each with the words the seed names it by.
OPEN = {
    'posix.system': (lambda: posix.system(f'{SANDBOX} true'), '`posix.system`'),
    'posix.posix_spawn': (_posix_spawn, '`posix.posix_spawn`'),
    'ctypes system': (lambda: ctypes.CDLL(None).system(f'{SANDBOX} true'.encode()), '`ctypes`'),
    'udp sendmsg': (_udp_sendmsg, '`sendmsg`'),
    '_socket.getaddrinfo': (lambda: _socket.getaddrinfo('localhost', 80), '`_socket.getaddrinfo`'),
    'getfqdn': (lambda: socket.getfqdn('localhost'), '`getfqdn`'),
}


def section(heading: str) -> str:
    start = AGENTS.index(f'\n{heading}\n')
    level = heading.split(' ', 1)[0]
    ends = [AGENTS.find(f'\n{"#" * n} ', start + 1) for n in range(1, len(level) + 1)]
    return AGENTS[start:min([e for e in ends if e != -1], default=len(AGENTS))]


@pytest.mark.unit
def test_the_static_check_reads_exactly_the_launchers_it_lists() -> None:
    read = {form: NS['sandbox_violations'](source, 'f.py') != [] for form, (source, _, _) in FORMS.items()}
    assert {f: r for f, r in read.items() if r != FORMS[f][1]} == {}
    assert any(read.values()) and not all(read.values())
    unnamed = [f for f, (_, named, words) in FORMS.items() if not named and words not in GAPS]
    assert unnamed == [], unnamed


@pytest.mark.unit
def test_the_static_check_gap_is_stated_as_a_class() -> None:
    commands = AGENTS[AGENTS.index('\n## Commands\n'):AGENTS.index('\n## Repository map')]
    comments = flat(' '.join(line.split('#', 1)[1] for line in commands.splitlines() if '#' in line))
    testing = flat(section('## Testing'))
    assert STATIC_CLASS['the commands block'] in comments
    assert STATIC_CLASS['the tests/test_hygiene.py entry'] in testing
    assert 'reads `subprocess`, `os` and `asyncio` calls and bare names imported from them' not in GAPS
    assert 'reads a call to a launcher its docstring lists' in GAPS


@pytest.mark.unit
@pytest.mark.parametrize('route', sorted(OPEN))
def test_the_guard_leaves_a_route_open_the_seed_names(route: str, guard) -> None:
    probe, words = OPEN[route]
    probe()
    assert guard.refused == [], route
    assert words in GAPS, (route, words)


@pytest.mark.unit
def test_values_naming_the_real_home_reach_a_unit_test(tmp_path: Path) -> None:
    assert os.environ.get('GNUPGHOME') == SENTINEL, 'run through remediation/checks.sh, which exports the sentinel'
    assert os.environ['HOME'] == str(tmp_path / 'home') != STARTED_HOME
    assert Path(site.USER_BASE).is_relative_to(STARTED_HOME) and not Path(site.USER_BASE).is_relative_to(tmp_path)
    assert Path(site.getuserbase()).is_relative_to(STARTED_HOME)
    real = pwd.getpwuid(os.getuid()).pw_dir
    assert os.path.expanduser(f'~{pwd.getpwuid(os.getuid()).pw_name}') == real
    for words in ('`GNUPGHOME`', '`site.USER_BASE`', '`site.getuserbase()`', 'password database', '`~user`'):
        assert words in GAPS, words


@pytest.mark.unit
def test_the_guard_gap_is_stated_as_a_class() -> None:
    testing = flat(section('## Testing'))
    assert GUARD_CLASS in testing
    assert HOME_CLASS in testing
