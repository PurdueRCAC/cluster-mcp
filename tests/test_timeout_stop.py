# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""A timed-out command is stopped, with what it started, in every mode (AGENTS.md § Invariants §3).

At a timeout, the command's processes (the command, the children and grandchildren it started, and
any of them that ignores TERM, but not a process that has left its process group) have all exited
within 2 × `launch.GRACE` of the deadline, on the server's clock, and `run` returns the call within the
same bound (and within `GRACE / 2` where a launcher with no watchdog would return at the deadline's
TERM). What a call that completed left running is never signalled, whether
its command exited or died of a signal; every process gets at most the deadline's one TERM, so a
command that handles it has `GRACE` to print as it stops, and what it prints is in the result, while
under a non-root `delegate` server, where that TERM reaches only the program, the command's processes
get KILL after the grace and no TERM; a startup file's TERM ignore, `set -C`, `set -m`, `enable -n
trap` or a function over a builtin the launch runs does not keep the command from being stopped,
and neither, over `ssh`, does a remote login shell's own rc file that ignores every catchable
terminating signal before the program starts; a deadline that comes while the program forks its
watchdog (with TERM ignored, so the watchdog is born ignoring it), or before the watchdog has run a
statement, leaves nothing running past the bound, and where the program reads the server's clock
(`local`, `delegate`) starts nothing; a command whose deadline passes while a login initialisation
that ignores TERM still runs is stopped, or, where the program reads the server's clock, never
starts; over `ssh` a connection slower than the timeout still leaves the command its whole timeout;
no variable the program sets reaches the command under a profile's `set -a`; and, on a bash that
hands shell options on (`BASHOPTS`, 4.1 and later; the row runs where bash is 4.4 or later), a
command sees the shell options its profile left.

Every row runs a real launch with no real host, no real `sudo` and no network, through the
`executes` fixture: `local`; `delegate-root`, under the stand-in for a root server's `sudo`
(`ROOT_RELAY`: the command stays in its process group, so the server's signal reaches all of it);
`delegate`, under the stand-in for a non-root server's (`RELAY`: a session of its own, so it is
the only process the server can signal, and it passes on TERM alone, to the command's process);
and `ssh-<shell>`, against the loopback server (`tests/ssh_server.py`) with that login shell, which
acts on a `signal` request as sshd does: the exec's whole process group gets it, only while the
exec's process runs. Its connection is made before the row's clock starts.
Each process a command starts writes its pid first, and each shape's top `exec`s its last command,
so every process of it has a pid file; a row checks each pid gone once the bound has passed, by
`start + timeout + 2 × GRACE + SLACK`, `start` taken just before the call (the real deadline comes
a little later, so the check is, if anything, early). A pid file missing at the deadline fails the
row as a process not started in time, never as a stop. Teardown kills the process group of every
recorded pid, never the runner's own, so a row that fails leaves nothing behind.

The module imports only names the launcher had before its watchdog, so it can also run against
that launcher, where each stop row fails exactly where that code leaves a process running. The
signals asked for over `ssh` are pinned by `tests/test_ssh_exec.py`'s unit rows, not here.
`CLUSTER_MCP_TEST_EVERY_KIND=1` adds the settings kept out of the suite for time: `ssh-zsh`,
`ssh-sh` and `ssh-tcsh`.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterator

import pytest

from conftest import need_shell
from harness import call, drive, in_memory, shared_server
from ssh_server import LoopbackSSH
from cluster_mcp.core.executor import TIMEOUT_EXIT_CODE, CommandResult, Executor
from cluster_mcp.core.executor import launch
from cluster_mcp.core.executor.delegate import DelegatingExecutor
from cluster_mcp.core.executor.shell import LocalShellExecutor

EVERY_KIND = os.environ.get('CLUSTER_MCP_TEST_EVERY_KIND') == '1'
LIMITS = os.environ.get('CLUSTER_MCP_TEST_LIMITS') == '1'

# Each row's timeout: long enough for a slow login to start every process before the deadline.
TIMEOUT = 1.0
# The stop bound (AGENTS.md § Invariants §3), and the scheduling slack a loaded runner is allowed on
# top of it. The watchdog's KILL lands about GRACE after the deadline (measured: at most 1.09 s,
# quiet and under 20-way CPU load), so the check at 2 × GRACE + SLACK has about 1.4 s of margin.
BOUND = 2 * launch.GRACE
SLACK = 0.5
# How long `run` may take past the deadline: the stop's bound, 2 × GRACE (it reads GRACE after the
# TERM and again after the KILL), with the same SLACK. The check's own wait for the server's TERM
# (a command past its deadline) ends within it: measured, the slowest returns, a non-root `delegate`
# server's late start and windows, at most 1.61 s after the deadline quiet and 1.63 s under 20-way
# CPU load, so the check at 2 × GRACE + SLACK has about 0.9 s of margin.
# Where a launcher without the watchdog would return at the deadline's TERM, its output ended,
# `run` must return within GRACE / 2 (a watchdog that held the output would hold the call to its
# KILL, GRACE later).
AT_ONCE = launch.GRACE / 2
HELD = 2 * launch.GRACE + SLACK

# Every catchable signal whose default action ends a process: an ignoring shape survives all of them.
IGNORED = 'HUP INT QUIT ILL TRAP ABRT BUS FPE USR1 SEGV USR2 PIPE ALRM TERM XCPU XFSZ VTALRM PROF SYS'

# The command shapes, each a process tree of `top`, `child` and `grandchild`:
# - `tree`: none ignores TERM, and all hold the command's output;
# - `ignores-holding`: the same tree ignoring every signal in IGNORED;
# - `ignores-none`: a top that does not ignore TERM, with a child and a grandchild that ignore every
#   signal in IGNORED and hold no stream of the call (stdio on /dev/null), so the output ends when
#   the top dies.
PROCESSES = ('top', 'child', 'grandchild')

# The settings, each with the shapes it runs. Over `ssh` one login shell runs in the suite, every
# other behind EVERY_KIND. `ignores-none` runs in `local` and both `delegate` settings, where the
# server's own KILL is skipped once the top's output has ended (or, under a non-root server, reaches
# only `sudo`), so only the watchdog's reaches what the top started.
MODES: dict[str, tuple[str, ...]] = {
    'local': ('tree', 'ignores-holding', 'ignores-none'),
    'delegate-root': ('tree', 'ignores-holding', 'ignores-none'),
    'delegate': ('tree', 'ignores-holding', 'ignores-none'),
    'ssh-bash': ('tree', 'ignores-holding'),
    **({f'ssh-{shell}': ('tree', 'ignores-holding') for shell in ('zsh', 'sh', 'tcsh')} if EVERY_KIND else {}),
}
SETTINGS = list(MODES)
STOP_ROWS = [pytest.param(setting, shape, id=f'{setting}-{shape}') for setting in MODES for shape in MODES[setting]]


def _shape(shape: str, pids: Path) -> str:
    """The `run_command` script of `shape`, its processes writing their pids under `pids`."""
    d = shlex.quote(str(pids))
    leaf = 'echo $$ > "$1/grandchild"; exec /bin/sleep 30'
    child = f'echo $$ > "$1/child"; /bin/sh -c {shlex.quote(leaf)} sh "$1" & exec /bin/sleep 30'
    spawn = f'/bin/sh -c {shlex.quote(child)} sh {d}'
    if shape == 'tree':
        return f'echo $$ > {d}/top; {spawn} & exec /bin/sleep 30'
    if shape == 'ignores-holding':
        return f"echo $$ > {d}/top; trap '' {IGNORED}; {spawn} & exec /bin/sleep 30"
    if shape == 'ignores-none':
        return f"echo $$ > {d}/top; (trap '' {IGNORED}; exec {spawn}) </dev/null >/dev/null 2>&1 & exec /bin/sleep 30"
    raise ValueError(shape)


class Hosts:
    """The loopback server of each `ssh-<shell>` setting a row uses, started on first use, and the
    connected executors of it; `close()` closes both."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.servers: dict[str, LoopbackSSH] = {}
        self.executors: list[Executor] = []

    def server(self, setting: str) -> LoopbackSSH:
        if setting not in self.servers:
            shell = '/bin/' + setting.removeprefix('ssh-')
            need_shell(shell)
            home = (self.root / setting).resolve()
            home.mkdir()
            self.servers[setting] = LoopbackSSH(home, shell, self.root)
        return self.servers[setting]

    def executor(self, setting: str) -> Executor:
        """An executor for the setting's server, already connected: a row's deadline is the command's,
        so its clock must not run while the connection is made."""
        executor = self.server(setting).executor()
        self.executors.append(executor)
        warm = executor.run('true', timeout=30)
        assert warm.exit_code == 0, f'{setting}: the connection did not run a command: {warm!r}'
        return executor

    def close(self) -> None:
        for executor in self.executors:
            executor.close()
        for server in self.servers.values():
            server.close()


@pytest.fixture
def hosts(tmp_path: Path) -> Iterator[Hosts]:
    """The rows' loopback servers; teardown closes them, killing whatever their execs left running."""
    started = Hosts(tmp_path)
    try:
        yield started
    finally:
        started.close()


def _home(executes: Any, hosts: Hosts, setting: str) -> Path:
    if setting.startswith('ssh-'):
        return Path(hosts.server(setting).home)
    return executes.server_home if setting == 'local' else executes.mapped_home


def _executor(executes: Any, hosts: Hosts, setting: str) -> Executor:
    if setting.startswith('ssh-'):
        return hosts.executor(setting)
    if setting == 'local':
        return LocalShellExecutor()
    executes.server_root = setting == 'delegate-root'
    return DelegatingExecutor('carol', {'carol': executes.user})


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _recorded(pids: Path) -> dict[str, int]:
    found = {}
    for path in sorted(pids.iterdir()):
        try:
            found[path.name] = int(path.read_text())
        except ValueError:
            pass
    return found


@pytest.fixture
def pids(tmp_path: Path) -> Iterator[Path]:
    """The directory a row's processes write their pids into; teardown kills each one's process group."""
    where = tmp_path / 'pids'
    where.mkdir()
    yield where
    own = os.getpgrp()
    for pid in _recorded(where).values():
        if not _alive(pid):
            continue
        try:
            group = os.getpgid(pid)
            if group != own:
                os.killpg(group, signal.SIGKILL)
        except OSError:
            pass
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def stop_violations(label: str, pids: Path, names: tuple[str, ...], deadline: float) -> list[str]:
    """Every process of `names` not gone by `deadline + BOUND + SLACK`, or not started by the deadline."""
    recorded = _recorded(pids)
    missing = [name for name in names if name not in recorded]
    if missing:
        return [f'{label}: the {", ".join(missing)} process was not started before the deadline (no pid file '
                f'{time.monotonic() - deadline:.2f} s after it): the row proves nothing about a stop']
    until = deadline + BOUND + SLACK
    while True:
        alive = [name for name in names if _alive(recorded[name])]
        if not alive or time.monotonic() >= until:
            break
        time.sleep(0.05)
    if alive:
        return [f'{label}: {", ".join(alive)} still running {time.monotonic() - deadline:.2f} s after the deadline '
                f'(the bound is {BOUND:g} s, with {SLACK:g} s of slack)']
    return []


def return_violations(label: str, returned: float, deadline: float, allowed: float = HELD) -> list[str]:
    """The call, if `run` returned it more than `allowed` after the deadline: past the bound (`HELD`), or
    later than a launcher without the watchdog would have (`AT_ONCE`)."""
    late = returned - deadline
    if late > allowed:
        why = ('later than a launcher without the watchdog would' if allowed < BOUND
               else f'past the bound on its return ({BOUND:g} s, with {SLACK:g} s of slack)')
        return [f'{label}: run returned {late:.2f} s after the deadline, {why} ({allowed:g} s)']
    return []


@pytest.mark.integration
@pytest.mark.parametrize(('setting', 'shape'), STOP_ROWS)
def test_a_timed_out_command_is_stopped(setting: str, shape: str, executes: Any, hosts: Hosts, pids: Path) -> None:
    executor = _executor(executes, hosts, setting)
    start = time.monotonic()
    result = executor.run(_shape(shape, pids), timeout=TIMEOUT)
    returned = time.monotonic()
    deadline = start + TIMEOUT
    label = f'{setting}-{shape}'
    violations = stop_violations(label, pids, PROCESSES, deadline)
    if result.exit_code != TIMEOUT_EXIT_CODE:
        violations.append(f'{label}: the call did not time out: {result!r}')
    at_once = setting != 'delegate' and shape != 'ignores-holding'
    violations += return_violations(label, returned, deadline, AT_ONCE if at_once else HELD)
    assert violations == [], '\n'.join(violations)


def _job(pids: Path) -> str:
    """A script line that starts a background job holding no stream of the call, and waits for its pid."""
    d = shlex.quote(str(pids))
    return (f"/bin/sh -c 'echo $$ > \"$1/job\"; exec /bin/sleep 30' sh {d} </dev/null >/dev/null 2>&1 & "
            f'while [ ! -s {d}/job ]; do /bin/sleep 0.05; done; ')


def survival_violations(label: str, pids: Path, ended: float) -> list[str]:
    """The job, if a completed call's background job was stopped before `ended + BOUND + SLACK`."""
    job = _recorded(pids).get('job')
    if job is None:
        return [f'{label}: the background job never started']
    until = ended + BOUND + SLACK
    while time.monotonic() < until:
        if not _alive(job):
            return [f"{label}: a completed command's background job was stopped "
                    f'{time.monotonic() - ended:.2f} s after the call returned']
        time.sleep(0.05)
    return []


@pytest.mark.integration
@pytest.mark.parametrize('setting', SETTINGS)
def test_a_completed_command_leaves_its_jobs_running(setting: str, executes: Any, hosts: Hosts, pids: Path) -> None:
    result = _executor(executes, hosts, setting).run(_job(pids) + 'echo done', timeout=20)
    ended = time.monotonic()
    violations = survival_violations(setting, pids, ended)
    if (result.stdout, result.exit_code) != ('done\n', 0):
        violations.append(f'{setting}: the command did not complete: {result!r}')
    assert violations == [], '\n'.join(violations)


@pytest.mark.integration
@pytest.mark.parametrize('setting', SETTINGS)
def test_a_command_that_dies_of_a_signal_leaves_its_jobs_running(setting: str, executes: Any, hosts: Hosts,
                                                                 pids: Path) -> None:
    result = _executor(executes, hosts, setting).run(_job(pids) + 'kill -s USR1 $$', timeout=20)
    ended = time.monotonic()
    violations = survival_violations(setting, pids, ended)
    if result.exit_code != -signal.SIGUSR1:
        violations.append(f'{setting}: the command did not die of USR1: {result!r}')
    assert violations == [], '\n'.join(violations)


# A command that handles TERM gracefully: on its first TERM it stops, which takes it 0.6 s, inside
# GRACE, and prints `stopped cleanly`; a second TERM cuts that short (`second TERM: exiting now`). It
# and a child of it count every TERM they get. The stop's KILL comes no sooner than GRACE after the
# deadline's TERM (an absolute `sleep` bounds the wait from below; measured at 0.96 s or later, quiet
# and under 16-way CPU load), while a stop that waits for nothing, or only for a fork, KILLs within
# about 0.1 s: halfway, the row tells the two apart under load. Its `sleep`s are absolute, because
# the profile below defines a `sleep` function, which the script's bash inherits.
COUNTED = """trap 'echo t >> "$1/terms-child"' TERM; echo $$ > "$1/child"; while :; do /bin/sleep 0.1; done"""
GRACEFUL = ("echo $$ > {d}/top; s=0; trap 'echo t >> {d}/terms-top; s=$((s + 1))' TERM; echo started; "
            "/bin/sh -c " + shlex.quote(COUNTED) + " sh {d} & /bin/sleep 30 & wait; /bin/sleep 0.6 & wait $!; "
            "if [ $s -ge 2 ]; then echo 'second TERM: exiting now'; exit 1; fi; echo 'stopped cleanly'; exit 0")
# Where the deadline's TERM reaches the command's group (every setting but a non-root `delegate`).
GRACE_SETTINGS = [setting for setting in SETTINGS if setting != 'delegate']


def _graceful(executes: Any, hosts: Hosts, setting: str, pids: Path) -> tuple[Executor, str]:
    """The setting's executor, with a profile whose `sleep` function, function named like the
    watchdog's absolute `sleep` and `sleep` first on PATH may not shorten the watchdog's wait, and the
    graceful command writing under `pids`."""
    executor = _executor(executes, hosts, setting)
    home = _home(executes, hosts, setting)
    (home / 'bin').mkdir()
    (home / 'bin' / 'sleep').write_text('#!/bin/sh\nexit 0\n')
    (home / 'bin' / 'sleep').chmod(0o755)
    (home / '.bash_profile').write_text('sleep() { :; }\n/bin/sleep() { :; }\nPATH="$HOME/bin:$PATH"\n')
    return executor, GRACEFUL.format(d=shlex.quote(str(pids)))


def _terms(pids: Path, name: str) -> int:
    path = pids / f'terms-{name}'
    return path.read_text().count('t') if path.exists() else 0


@pytest.mark.integration
@pytest.mark.parametrize('setting', GRACE_SETTINGS)
def test_a_stopping_command_gets_its_grace(setting: str, executes: Any, hosts: Hosts, pids: Path) -> None:
    executor, command = _graceful(executes, hosts, setting, pids)
    start = time.monotonic()
    result = executor.run(command, timeout=TIMEOUT)
    assert isinstance(result, CommandResult) and result.exit_code == TIMEOUT_EXIT_CODE, result
    violations = return_violations(setting, time.monotonic(), start + TIMEOUT)
    terms = {name: _terms(pids, name) for name in ('top', 'child')}
    if terms != {'top': 1, 'child': 1}:
        violations.append(f'{setting}: a process got other than one TERM at the timeout: {terms}')
    if result.stdout != 'started\nstopped cleanly\n':
        violations.append(f'{setting}: the output the command printed as it stopped, within GRACE of its TERM, was '
                          f'lost: {result!r}')
    assert violations == [], '\n'.join(violations)


@pytest.mark.integration
def test_a_non_root_server_kills_after_the_grace_with_no_term(executes: Any, hosts: Hosts, pids: Path) -> None:
    # `sudo` relays the deadline's TERM to the program alone, which dies of it; the command's processes
    # get no TERM, and the watchdog's KILL GRACE later.
    executor, command = _graceful(executes, hosts, 'delegate', pids)
    outcome: list[CommandResult] = []
    start = time.monotonic()
    caller = threading.Thread(target=lambda: outcome.append(executor.run(command, timeout=TIMEOUT)), daemon=True)
    caller.start()
    deadline = start + TIMEOUT
    while time.monotonic() < deadline + launch.GRACE / 2:
        time.sleep(0.02)
    recorded = _recorded(pids)
    early = [name for name in PROCESSES[:2] if name not in recorded or not _alive(recorded[name])]
    violations = []
    if early:
        violations.append(f'{", ".join(early)} not running {time.monotonic() - deadline:.2f} s after the deadline, '
                          f'before the grace was over')
    violations += stop_violations('delegate-graceful', pids, PROCESSES[:2], deadline)
    caller.join(HELD)
    result = outcome[0] if outcome else None
    if result is None or result.exit_code != TIMEOUT_EXIT_CODE:
        violations.append(f'the call did not time out: {result!r}')
    terms = {name: _terms(pids, name) for name in ('top', 'child')}
    if terms != {'top': 0, 'child': 0}:
        violations.append(f'a process got a TERM under a non-root server: {terms}')
    if result is not None and result.stdout != 'started\n':
        violations.append(f'the command printed more than it did before the deadline: {result!r}')
    assert violations == [], '\n'.join(violations)


# A startup file of the program's own login shell (`profile`) that ignores TERM, sets noclobber and
# turns job control on: the program undoes each, so the command is stopped as without it. Over
# `ssh`, a remote login shell's own rc file (`bashrc` for a bash login shell, `zshenv`) that ignores
# every catchable terminating signal before the program starts: the program inherits the ignores and
# cannot undo them, so it lives on past the TERM, and only the KILL asked for after the grace stops
# it (a KILL renamed to any other signal sshd delivers would be ignored too).
STARTUP_FILES = {'profile': ('.bash_profile', "trap '' TERM\nset -C\nset -m\n"),
                 'bashrc': ('.bashrc', f"trap '' {IGNORED}\n"),
                 'zshenv': ('.zshenv', f"trap '' {IGNORED}\n")}
STARTUP_ROWS = [pytest.param(setting, file, id=f'{setting}-{file}')
                for setting, file in (('delegate', 'profile'), ('ssh-bash', 'profile'), ('ssh-bash', 'bashrc'),
                                      ('ssh-zsh', 'zshenv'))]


@pytest.mark.integration
@pytest.mark.parametrize(('setting', 'file'), STARTUP_ROWS)
def test_a_startup_file_ignoring_term_is_undone(setting: str, file: str, executes: Any, hosts: Hosts,
                                                 pids: Path) -> None:
    executor = _executor(executes, hosts, setting)
    name, text = STARTUP_FILES[file]
    (_home(executes, hosts, setting) / name).write_text(text)
    start = time.monotonic()
    result = executor.run(_shape('tree', pids), timeout=TIMEOUT)
    returned = time.monotonic()
    label = f'{setting}-{file}'
    violations = stop_violations(label, pids, PROCESSES, start + TIMEOUT)
    violations += return_violations(label, returned, start + TIMEOUT)
    if result.exit_code != TIMEOUT_EXIT_CODE:
        violations.append(f'{label}: the call did not time out: {result!r}')
    assert violations == [], '\n'.join(violations)


# A login initialisation that ignores every catchable terminating signal and hangs, before the
# program and its watchdog exist. Over `ssh` its launch still lives once the grace is over, so the
# KILL asked for then stops it (under a non-root `delegate` server nothing does: a recorded limit).
HANGS = "trap '' {ignored}\necho $$ > {pids}/login\nexec /bin/sleep 30\n"


@pytest.mark.integration
def test_a_hanging_login_is_stopped_over_ssh(executes: Any, hosts: Hosts, pids: Path) -> None:
    executor = _executor(executes, hosts, 'ssh-bash')
    profile = HANGS.format(ignored=IGNORED, pids=shlex.quote(str(pids)))
    (_home(executes, hosts, 'ssh-bash') / '.bash_profile').write_text(profile)
    start = time.monotonic()
    result = executor.run('echo never', timeout=TIMEOUT)
    returned = time.monotonic()
    violations = stop_violations('ssh-bash-hangs', pids, ('login',), start + TIMEOUT)
    violations += return_violations('ssh-bash-hangs', returned, start + TIMEOUT)
    if (result.stdout, result.exit_code) != ('', TIMEOUT_EXIT_CODE):
        violations.append(f'ssh-bash-hangs: the call was not an empty timeout: {result!r}')
    assert violations == [], '\n'.join(violations)


# A login initialisation that ignores TERM and is still running at the deadline: no process of the
# command runs past the bound, and `run` returns within it. Where the program runs on the server's
# host (`local`, `delegate`), it reads the clock before the command starts, and a command past its
# deadline never starts (under a non-root `delegate` server nothing else would stop it, since the
# relayed TERM went to the startup file); the program then waits up to GRACE for the server's TERM,
# which the server's own drains bound. Over `ssh` the command starts, and the KILL asked for after the
# grace stops it. The startup file also defines functions named like the clock and its absolute
# path, answering the epoch.
LATE = "trap '' TERM\n/bin/date() {{ echo 0; }}\ndate() {{ echo 0; }}\necho $$ > {pids}/login\n/bin/sleep 1.5\n"
TOP = 'echo $$ > {pids}/top; exec /bin/sleep 30'
F3_SETTINGS = ['local', 'delegate-root', 'delegate', 'ssh-bash']


def gone_violations(label: str, pids: Path, needed: tuple[str, ...], since: float) -> list[str]:
    """Every recorded process not gone by `since + BOUND + SLACK`, or a `needed` one never recorded."""
    until = since + BOUND + SLACK
    while True:
        recorded = _recorded(pids)
        alive = [name for name, pid in recorded.items() if not name.startswith('terms') and _alive(pid)]
        if not alive or time.monotonic() >= until:
            break
        time.sleep(0.05)
    missing = [name for name in needed if name not in recorded]
    if missing:
        return [f'{label}: no pid file for {", ".join(missing)}: the row proves nothing']
    if alive:
        return [f'{label}: {", ".join(alive)} still running {time.monotonic() - since:.2f} s after the deadline '
                f'(the bound is {BOUND:g} s, with {SLACK:g} s of slack)']
    return []


@pytest.mark.integration
@pytest.mark.parametrize('setting', F3_SETTINGS)
def test_a_command_past_its_deadline_is_stopped(setting: str, executes: Any, hosts: Hosts, pids: Path) -> None:
    executor = _executor(executes, hosts, setting)
    d = shlex.quote(str(pids))
    (_home(executes, hosts, setting) / '.bash_profile').write_text(LATE.format(pids=d))
    start = time.monotonic()
    result = executor.run(TOP.format(pids=d), timeout=TIMEOUT)
    returned = time.monotonic()
    label = f'{setting}-late-start'
    violations = gone_violations(label, pids, ('login',), start + TIMEOUT)
    violations += return_violations(label, returned, start + TIMEOUT)
    if not setting.startswith('ssh-') and 'top' in _recorded(pids):
        violations.append(f'{label}: the command started after its deadline, on the server\'s own clock')
    if (result.stdout, result.exit_code) != ('', TIMEOUT_EXIT_CODE):
        violations.append(f'{label}: the call was not an empty timeout: {result!r}')
    assert violations == [], '\n'.join(violations)


# The deadline coming while the watchdog is being started, in a window planted 1.5 s wide (opened
# just after the login initialisation, so the deadline of TIMEOUT comes inside it), anchored on the
# decision it tests rather than on the text around it:
# - `program`: in the program, right after the fork, which it makes with TERM ignored, before it
#   takes TERM's default back. The deadline's TERM is lost there: where the program reads the
#   server's clock (`local`, `delegate`) the deadline's check after it refuses the start, and over
#   `ssh` the command starts and the KILL asked for after the grace stops it;
# - `watchdog`: in the watchdog, before its first statement. It is born ignoring TERM, so the
#   deadline's TERM to the group does not end it, and what the command started is stopped.
# The command is the `ignores-none` shape (a child and a grandchild that ignore TERM and hold no stream
# of the call); nothing runs past the bound, and `run` returns within it.
WINDOWS = ('program', 'watchdog')
WINDOW_ROWS = [pytest.param(setting, window, id=f'{setting}-{window}') for window in WINDOWS
               for setting in F3_SETTINGS]


def _fork_end(text: str) -> int:
    """The index just past the watchdog's process substitution, `>( … )`, in `text`."""
    at, depth = text.index('>(') + 2, 1
    while depth:
        depth += {'(': 1, ')': -1}.get(text[at], 0)
        at += 1
    return at


def planted_window(watchdog: str, window: str, pids: str) -> str:
    """`watchdog` with a 1.5 s window in `window`, which first writes its process's pid under `pids`."""
    if window == 'program':
        at = _fork_end(watchdog)
        return f'{watchdog[:at]}; echo $$ > {pids}/program; /bin/sleep 1.5{watchdog[at:]}'
    at = watchdog.index('>(') + 2
    return (f"{watchdog[:at]}/bin/sh -c 'echo $PPID' > {pids}/watchdog; "
            f'/bin/sleep 1.5 </dev/null >/dev/null 2>&1; {watchdog[at:]}')


@pytest.mark.integration
@pytest.mark.parametrize(('setting', 'window'), WINDOW_ROWS)
def test_a_deadline_while_the_watchdog_starts(setting: str, window: str, executes: Any, hosts: Hosts, pids: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    executor = _executor(executes, hosts, setting)
    planted = planted_window(launch.WATCHDOG, window, shlex.quote(str(pids)))
    monkeypatch.setattr(launch, 'WATCHDOG', planted)
    label = f'{setting}-{window}-window'
    outcome: list[tuple[CommandResult, float]] = []
    start = time.monotonic()
    caller = threading.Thread(target=lambda: outcome.append((executor.run(_shape('ignores-none', pids),
                                                                           timeout=TIMEOUT), time.monotonic())),
                              daemon=True)
    caller.start()
    deadline = start + TIMEOUT
    try:
        while window not in _recorded(pids) and time.monotonic() < deadline:
            time.sleep(0.01)
        if window not in _recorded(pids):
            pytest.fail(f'{label}: the window had not opened by the deadline: the row proves nothing')
        violations = gone_violations(label, pids, (window,), deadline)
        if window == 'program' and not setting.startswith('ssh-') and 'top' in _recorded(pids):
            violations.append(f'{label}: the command started after its deadline, on the server\'s own clock')
        caller.join(HELD)
        if not outcome:
            violations.append(f'{label}: run had not returned {time.monotonic() - deadline:.2f} s after the deadline')
        else:
            result, returned = outcome[0]
            violations += return_violations(label, returned, deadline)
            if result.exit_code != TIMEOUT_EXIT_CODE:
                violations.append(f'{label}: the call did not time out: {result!r}')
    finally:
        own = os.getpgrp()
        for pid in _recorded(pids).values():
            try:
                if _alive(pid) and os.getpgid(pid) != own:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
            except OSError:
                pass
        caller.join(2 * BOUND)
    assert violations == [], '\n'.join(violations)


# A startup file that shadows the builtins the launch runs: a function named `unset` (or `unset`
# turned off) beside a function named like the watchdog's `/bin/cat`, which answers at once with the
# arming line. The prologue unsets the functions in posix mode, where the special builtin `unset`
# comes before a function of its name, after turning every builtin it runs back on, so the watchdog
# stops nothing that completes. (A startup file that defeats this, a recorded limit, is a limit row.)
UNSET_SHADOWS = {'unset-function': "unset() { :; }\n/bin/cat() { printf '\\n'; }\n",
                 'unset-disabled': "enable -n unset\n/bin/cat() { printf '\\n'; }\n"}
UNSET_ROWS = [pytest.param(setting, kind, id=f'{setting}-{kind}')
              for setting in (SETTINGS if EVERY_KIND else ['local', 'delegate']) for kind in UNSET_SHADOWS]


@pytest.mark.integration
@pytest.mark.parametrize(('setting', 'kind'), UNSET_ROWS)
def test_a_profile_shadowing_unset_stops_nothing(setting: str, kind: str, executes: Any, hosts: Hosts,
                                                 pids: Path) -> None:
    executor = _executor(executes, hosts, setting)
    (_home(executes, hosts, setting) / '.bash_profile').write_text(UNSET_SHADOWS[kind])
    result = executor.run(_job(pids) + f'/bin/sleep {RUN:g}; echo done')
    violations = completion_violations(f'{setting}-{kind}', result, pids)
    assert violations == [], '\n'.join(violations)


# A startup file that turns off the `trap` the watchdog runs and defines a function named `enable`
# (the prologue unsets it in posix mode, where `unset` comes first, then turns `trap` back on): the
# watchdog is still born ignoring the deadline's TERM and KILLs, so a process that ignores TERM and
# holds no stream of the call is stopped. (An alias over the watchdog's `kill` beside a function
# named `unalias` needs no row: leaving posix mode turns alias expansion off, in bash 3.2 to 5.3, for
# the program's own lines, before the watchdog's is read; the launch checker pins the prologue's
# second `\unalias -a`, which drops the aliases where a bash would keep it on.)
WATCHDOG_SHADOWS = {'enable-n-trap': 'enable -n trap\nenable() { :; }\n'}
WATCHDOG_SHADOW_ROWS = [pytest.param(setting, kind, id=f'{setting}-{kind}')
                        for setting, kind in (('local', 'enable-n-trap'), ('delegate-root', 'enable-n-trap'),
                                              ('ssh-bash', 'enable-n-trap'))]


@pytest.mark.integration
@pytest.mark.parametrize(('setting', 'kind'), WATCHDOG_SHADOW_ROWS)
def test_a_profile_shadowing_the_watchdog_is_undone(setting: str, kind: str, executes: Any, hosts: Hosts,
                                                    pids: Path) -> None:
    executor = _executor(executes, hosts, setting)
    (_home(executes, hosts, setting) / '.bash_profile').write_text(WATCHDOG_SHADOWS[kind])
    start = time.monotonic()
    result = executor.run(_shape('ignores-none', pids), timeout=TIMEOUT)
    returned = time.monotonic()
    label = f'{setting}-{kind}'
    violations = stop_violations(label, pids, PROCESSES, start + TIMEOUT)
    violations += return_violations(label, returned, start + TIMEOUT)
    if result.exit_code != TIMEOUT_EXIT_CODE:
        violations.append(f'{label}: the call did not time out: {result!r}')
    assert violations == [], '\n'.join(violations)


@pytest.mark.integration
def test_run_command_stops_a_timed_out_command(executes: Any, pids: Path) -> None:
    # The real tool path, in `local` mode: a top that dies at the TERM, and an ignoring child and
    # grandchild that hold no stream of the call.
    started: list[float] = []

    async def scenario() -> Any:
        async with in_memory(shared_server(LocalShellExecutor())) as client:
            started.append(time.monotonic())
            return await call(client, 'run_command', {'command': _shape('ignores-none', pids), 'timeout': TIMEOUT})

    outcome = drive(scenario(), timeout=60)
    violations = stop_violations('run_command', pids, PROCESSES, started[0] + TIMEOUT)
    if outcome.is_error or json.loads(outcome.text).get('exit_code') != TIMEOUT_EXIT_CODE:
        violations.append(f'run_command: the call did not time out: {outcome!r}')
    assert violations == [], '\n'.join(violations)


def completion_violations(label: str, result: CommandResult, pids: Path) -> list[str]:
    """The call, if it did not complete with `done` and status 0, or its background job is gone."""
    violations = []
    if (result.stdout, result.exit_code) != ('done\n', 0):
        violations.append(f'{label}: the command did not complete with its output: {result!r}')
    job = _recorded(pids).get('job')
    if job is None or not _alive(job):
        violations.append(f"{label}: the command's background job was stopped while the call ran")
    return violations


# A profile that bounds every wait of the `read` builtin (`TMOUT`, readonly and exported, as a site's
# hardening line sets it) well below the command's run: the watchdog acts on the program's death
# alone, never on time, so a call that outlives `TMOUT` completes with its output and its job,
# with no timeout or with one longer than its run. A watchdog that waited on `read` took the
# timeout for the program's death and stopped the group about `TMOUT` into the run.
TMOUT_PROFILE = 'TMOUT=1\nreadonly TMOUT\nexport TMOUT\n'
RUN = 2.0
LONGER = 20.0
TMOUT_ROWS = [pytest.param(setting, timeout, id=f'{setting}-{"timeout" if timeout else "no-timeout"}')
              for setting in SETTINGS for timeout in (None, LONGER)]


@pytest.mark.integration
@pytest.mark.parametrize(('setting', 'timeout'), TMOUT_ROWS)
def test_a_profile_tmout_stops_nothing(setting: str, timeout: float | None, executes: Any, hosts: Hosts,
                                       pids: Path) -> None:
    executor = _executor(executes, hosts, setting)
    (_home(executes, hosts, setting) / '.bash_profile').write_text(TMOUT_PROFILE)
    result = executor.run(_job(pids) + f'/bin/sleep {RUN:g}; echo done', timeout=timeout)
    violations = completion_violations(f'{setting}-tmout', result, pids)
    assert violations == [], '\n'.join(violations)


@pytest.mark.integration
def test_run_command_outlives_a_profile_tmout(executes: Any, pids: Path) -> None:
    # The real tool path, in `local` mode, with no timeout: the call completes past TMOUT.
    (executes.server_home / '.bash_profile').write_text(TMOUT_PROFILE)

    async def scenario() -> Any:
        async with in_memory(shared_server(LocalShellExecutor())) as client:
            return await call(client, 'run_command', {'command': _job(pids) + f'/bin/sleep {RUN:g}; echo done'})

    outcome = drive(scenario(), timeout=60)
    found = {} if outcome.is_error else json.loads(outcome.text)
    result = CommandResult(stdout=found.get('stdout', ''), stderr=found.get('stderr', ''),
                           exit_code=found.get('exit_code', 0 if not outcome.is_error else 1), hostname='')
    violations = completion_violations('run_command-tmout', result, pids)
    assert violations == [], '\n'.join(violations) + f'\n{outcome!r}'


# A profile that turns the other routes the watchdog's wait could take against it: `read` turned off
# with a plain exported `TMOUT`, so a `read` would run as an external program (macOS's
# `/usr/bin/read`, a shell running the builtin), which takes `TMOUT` from its environment; and a
# function named like the absolute path the wait runs (bash looks a function up before such a path),
# a `cat` function and a `cat` first on PATH, each answering at once with what the arming line is.
# The watchdog stops nothing that completes.
SHADOWS = "TMOUT=1\nexport TMOUT\nenable -n read\n/bin/cat() { printf '\\n'; }\ncat() { printf '\\n'; }\n" \
          'PATH="$HOME/bin:$PATH"\n'
SHADOW_SETTINGS = SETTINGS if EVERY_KIND else ['local', 'delegate']


@pytest.mark.integration
@pytest.mark.parametrize('setting', SHADOW_SETTINGS)
def test_a_profile_cannot_cut_the_watchdogs_wait_short(setting: str, executes: Any, hosts: Hosts,
                                                       pids: Path) -> None:
    executor = _executor(executes, hosts, setting)
    home = _home(executes, hosts, setting)
    (home / 'bin').mkdir()
    (home / 'bin' / 'cat').write_text("#!/bin/sh\nprintf '\\n'\n")
    (home / 'bin' / 'cat').chmod(0o755)
    (home / '.bash_profile').write_text(SHADOWS)
    result = executor.run(_job(pids) + f'/bin/sleep {RUN:g}; echo done', timeout=LONGER)
    violations = completion_violations(f'{setting}-shadows', result, pids)
    assert violations == [], '\n'.join(violations)


@pytest.mark.integration
def test_a_timed_out_call_leaves_the_connection_usable(executes: Any, hosts: Hosts, pids: Path) -> None:
    # A command that dies at the deadline's TERM: its channel closes during the grace, and no request
    # may follow on it (an SSH server drops the connection for one on a channel it has freed). The
    # next call on the same executor runs on the same connection.
    executor = _executor(executes, hosts, 'ssh-bash')
    server = hosts.server('ssh-bash')
    connections = len(server._transports)
    timed_out = executor.run(_shape('tree', pids), timeout=TIMEOUT)
    try:
        again: object = executor.run('echo again', timeout=LONGER)
    except Exception as exc:
        again = exc
    violations = []
    if timed_out.exit_code != TIMEOUT_EXIT_CODE:
        violations.append(f'the first call did not time out: {timed_out!r}')
    if (getattr(again, 'stdout', None), getattr(again, 'exit_code', None)) != ('again\n', 0):
        violations.append(f'the next call on the same executor failed, so the timed-out call lost the shared '
                          f'connection: {again!r}')
    if len(server._transports) != connections:
        violations.append(f'the server accepted {len(server._transports) - connections} more connection(s): the '
                          f'timed-out call lost the shared connection')
    assert violations == [], '\n'.join(violations)


@pytest.mark.integration
def test_a_slow_connect_leaves_an_ssh_command_its_whole_timeout(executes: Any, hosts: Hosts,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    # Over `ssh` the program is given no deadline (the remote clock is not the server's): the call's
    # timeout runs from the command's start, once the connection is made, however long that took. A
    # program that read a deadline taken before the connection would refuse a command a slow connect
    # had made late, and the call would time out without running it.
    executor = _executor(executes, hosts, 'ssh-bash')
    connect = executor._ensure_connected

    def slow(deadline: float) -> Any:
        time.sleep(TIMEOUT + launch.GRACE / 2)
        return connect(deadline)

    monkeypatch.setattr(executor, '_ensure_connected', slow)
    result = executor.run('echo ran', timeout=TIMEOUT)
    assert (result.stdout, result.exit_code) == ('ran\n', 0), \
        f'a command whose connection took longer than its timeout did not run with its whole timeout: {result!r}'


# No variable the program sets reaches the command, whatever a startup file leaves: under `set -a`
# every name assigned after it is exported, and a name a profile exported before it is set is
# exported once set, so each name the program's own lines set (its clock reading, its function-export
# loop) would reach the command's environment unless it is unset first.
# The row compares the names a command sees under a profile that does both (every `cluster_mcp_`
# name in the program's text exported beforehand) with those it sees under none, with a timeout, so
# the program reads its deadline too.
@pytest.mark.integration
@pytest.mark.parametrize('setting', F3_SETTINGS)
def test_no_variable_of_the_program_reaches_the_command(setting: str, executes: Any, hosts: Hosts) -> None:
    executor = _executor(executes, hosts, setting)
    profile = _home(executes, hosts, setting) / '.bash_profile'
    names = sorted(set(re.findall(r'\bcluster_mcp_\w+', launch.program('env', timeout=LONGER)[0])))
    assert names, 'the program sets no name of its own: the row proves nothing'
    seen = []
    for text in ('', f'set -a\nexport {" ".join(names)}\n'):
        profile.write_text(text)
        result = executor.run('env', timeout=LONGER)
        assert result.exit_code == 0 and result.stdout, f'{setting}: the command did not complete: {result!r}'
        seen.append({line.partition('=')[0] for line in result.stdout.splitlines() if '=' in line})
    leaked = sorted(seen[1] - seen[0])
    assert leaked == [], f'{setting}: under a profile\'s `set -a` the command sees the program\'s own {leaked}'


SANDBOX = Path(__file__).resolve().parent.parent / 'bin' / 'sandbox.sh'


def _bash_version() -> tuple[int, ...]:
    shown = subprocess.run([str(SANDBOX), launch.BASH, '--norc', '-c',
                            'echo "${BASH_VERSINFO[0]} ${BASH_VERSINFO[1]}"'],
                           capture_output=True, text=True, timeout=30).stdout.split()
    return tuple(int(part) for part in shown)


# The shell options a completed command can see are the ones its profile left. A bash hands them to
# every bash it starts through `BASHOPTS` once a startup file exports it (bash 4.1 and later). The
# prologue's round trip through posix mode changes the program's own options (bash 4.4 and 5.1, as
# measured, turn `inherit_errexit` on and `expand_aliases` off), but does not refresh `BASHOPTS`, so
# the command's bash still gets the profile's: this row passes on bash 4.4, 5.1 and 5.2 with nothing
# set back. It is the pin that the program runs nothing that refreshes `BASHOPTS` (a `shopt`, say)
# before the command. It is defined where the interpreter is bash 4.4 or later (CI's), so a run on
# bash 3.2, which hands no option on, collects none, never a skip.
OPTIONS_PROFILE = 'shopt -s expand_aliases shift_verbose\nexport BASHOPTS\n'
# `shopt -p` with names exits 1 when any of them is off (bash 4.4 and later), so the row reads the
# listing and ends the command with a status of its own.
OPTIONS_SHOWN = 'shopt -p inherit_errexit expand_aliases shift_verbose; :'
OPTIONS_LEFT = 'shopt -u inherit_errexit\nshopt -s expand_aliases\nshopt -s shift_verbose\n'
if _bash_version() >= (4, 4):
    @pytest.mark.integration
    @pytest.mark.parametrize('setting', F3_SETTINGS)
    def test_a_command_sees_the_shell_options_its_profile_left(setting: str, executes: Any, hosts: Hosts) -> None:
        executor = _executor(executes, hosts, setting)
        (_home(executes, hosts, setting) / '.bash_profile').write_text(OPTIONS_PROFILE)
        result = executor.run(OPTIONS_SHOWN, timeout=LONGER)
        assert (result.stdout, result.exit_code) == (OPTIONS_LEFT, 0), \
            f'{setting}: the command does not see the shell options its profile left: {result!r}'


# The recorded limits (AGENTS.md § Invariants §3, `issues/timeout-stop-limits.md`), each shown per
# setting as it is written down: what runs on past the bound, what is stopped, and what is stopped
# early. They run only with CLUSTER_MCP_TEST_LIMITS=1 (the limits checker sets it): each shows a
# process left running or a command cut short, and the suite pins what is stopped. A case names the
# processes it watches and, per setting, `RUNS_ON` (the named survivors are still running once the
# bound has passed), `STOPPED` (none is) or `CUT_SHORT` (a command with no timeout did not complete).
RUNS_ON, STOPPED, CUT_SHORT = 'runs on', 'stopped', 'cut short'
LIMIT_SETTINGS = ('local', 'delegate-root', 'delegate', 'ssh-bash')


def _hang(child: str = '', holds: bool = True) -> str:
    """A `.bash_profile` that records the login shell's pid and hangs on a foreground child."""
    redirect = '' if holds else ' </dev/null >/dev/null 2>&1 47<&- 48>&- 49>&- 57<&- 58>&- 59>&-'
    leaf = f'echo $$ > "$1/child"; {child}exec /bin/sleep 30'
    return f'echo $$ > {{pids}}/login\n/bin/sh -c {shlex.quote(leaf)} sh {{pids}}{redirect}\n'


LEFT = ('echo $$ > {pids}/top; ' + shlex.quote(sys.executable) + ' -I -c '
        + shlex.quote("import os, sys; os.setsid(); open(sys.argv[1], 'w').write(str(os.getpid())); "
                      "os.execv('/bin/sleep', ['sleep', '30'])")
        + ' {pids}/left </dev/null >/dev/null 2>&1 & exec /bin/sleep 30')
# A startup file that shadows the launch's builtins past what the prologue undoes: `unset` and `trap`
# turned off, and a function named `enable`, so they cannot be turned back on. The watchdog is then
# forked without TERM ignored and dies of the deadline's TERM to the group, so a process that ignores
# TERM and holds no stream of the call runs on (`shadowed-stop`; under a non-root `delegate` server
# no TERM reaches the watchdog, and its KILL comes); and with a function named like its `/bin/cat`
# too, it reads the arming line at once and KILLs a command with no timeout (`shadowed-early`).
SHADOWED = 'enable -n unset trap\nenable() { :; }\n'
EARLY = _job(Path('{pids}')).replace("'{pids}'", '{pids}') + '/bin/sleep 2; echo done'
# Each case: (profile, command, timeout, watched, survivors, expected per setting).
LIMIT_CASES: dict[str, tuple[str, str, float | None, tuple[str, ...], tuple[str, ...], dict[str, str]]] = {
    # A process that has left the command's process group is out of every stop's reach.
    'left-group': ('', LEFT, TIMEOUT, ('top', 'left'), ('left',), dict.fromkeys(LIMIT_SETTINGS, RUNS_ON)),
    # A login initialisation that hangs, before the watchdog exists, as the login shell itself,
    # ignoring every catchable terminating signal and holding the call's streams.
    'hang-ignoring': (f"trap '' {IGNORED}\necho $$ > {{pids}}/login\nexec /bin/sleep 30\n", 'echo never', TIMEOUT,
                      ('login',), ('login',), {'local': STOPPED, 'delegate-root': STOPPED, 'delegate': RUNS_ON,
                                               'ssh-bash': STOPPED}),
    # The same, hanging on a foreground child that does not ignore TERM.
    'hang-child': (_hang(), 'echo never', TIMEOUT, ('login', 'child'), ('child',),
                   {'local': STOPPED, 'delegate-root': STOPPED, 'delegate': RUNS_ON, 'ssh-bash': STOPPED}),
    # The same, its child ignoring every catchable terminating signal and holding the call's streams
    # (it inherits them from the login shell); the login shell does not ignore TERM.
    'hang-child-ignoring': (_hang(f"trap '' {IGNORED}; "), 'echo never', TIMEOUT, ('login', 'child'), ('child',),
                            {'local': STOPPED, 'delegate-root': STOPPED, 'delegate': RUNS_ON, 'ssh-bash': RUNS_ON}),
    # The same, its child holding no stream of the call.
    'hang-child-ignoring-unheld': (_hang(f"trap '' {IGNORED}; ", holds=False), 'echo never', TIMEOUT,
                                   ('login', 'child'), ('child',), dict.fromkeys(LIMIT_SETTINGS, RUNS_ON)),
    'shadowed-stop': (SHADOWED, _shape('ignores-none', Path('{pids}')).replace("'{pids}'", '{pids}'), TIMEOUT,
                      PROCESSES, ('child', 'grandchild'), {'local': RUNS_ON, 'delegate-root': RUNS_ON,
                                                           'delegate': STOPPED, 'ssh-bash': RUNS_ON}),
    'shadowed-early': (SHADOWED + "/bin/cat() { printf '\\n'; }\n", EARLY, None, ('job',), (),
                       dict.fromkeys(LIMIT_SETTINGS, CUT_SHORT)),
}
# A step of the server's wall clock during the login initialisation, simulated by moving the deadline
# the program is given (`time.time_ns()` as the program is rendered), where the program has one: a
# step forward (`clock-forward`, twice a long timeout) refuses at once a command the server would
# still run, so it never completes; a step back (`clock-back`, 10 s) lets a command start past its
# deadline behind a startup file that ignores TERM and runs past it (`LATE`), and the server's KILL
# stops it in `local` and under a root `delegate` server, while under a non-root one it runs on.
CLOCK_STEPS = {'clock-forward': -2 * int(LONGER * 1e9), 'clock-back': 10 * 10**9}
CLOCK_EXPECTED = {'clock-forward': dict.fromkeys(LIMIT_SETTINGS[:3], CUT_SHORT),
                  'clock-back': {'local': STOPPED, 'delegate-root': STOPPED, 'delegate': RUNS_ON}}
LIMIT_ROWS = [pytest.param(case, setting, id=f'{case}-{setting}')
              for case in LIMIT_CASES for setting in LIMIT_SETTINGS] + [pytest.param('deaf-server', 'ssh-bash',
                                                                                      id='deaf-server-ssh-bash')]
LIMIT_ROWS += [pytest.param(case, setting, id=f'{case}-{setting}') for case in CLOCK_STEPS
               for setting in CLOCK_EXPECTED[case]]


class _Deaf(LoopbackSSH):
    """A server that does not act on the `signal` request (it records the name and drops it)."""

    def deliver(self, channel: Any, name: str) -> bool:
        self.signals.append(name)
        return False


def _watched(pids: Path, names: tuple[str, ...], until: float) -> dict[str, str]:
    """Each named process's state at `until`: running, gone, or not started (no pid file)."""
    while time.monotonic() < until:
        time.sleep(0.05)
    recorded = _recorded(pids)
    return {name: ('not started' if name not in recorded else 'running' if _alive(recorded[name]) else 'gone')
            for name in names}


# Defined only with CLUSTER_MCP_TEST_LIMITS=1, so the suite collects no limit row at all (a skip would
# let a row vanish from CI without failing; only `conftest.need_shell` may skip).
if LIMITS:
    @pytest.mark.integration
    @pytest.mark.parametrize(('case', 'setting'), LIMIT_ROWS)
    def test_a_recorded_limit(case: str, setting: str, executes: Any, hosts: Hosts, pids: Path,
                              tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        label = f'{case}-{setting}'
        if case in CLOCK_STEPS:
            executor, home = _executor(executes, hosts, setting), _home(executes, hosts, setting)
            real, step = time.time_ns, CLOCK_STEPS[case]
            monkeypatch.setattr(time, 'time_ns', lambda: real() + step)
            d = shlex.quote(str(pids))
            expected = CLOCK_EXPECTED[case][setting]
            if case == 'clock-forward':
                profile, command, timeout, names, survivors = '', 'echo done', LONGER, (), ()
            else:
                profile, command, timeout, names, survivors = LATE.format(pids=d), TOP.format(pids=d), TIMEOUT, \
                    ('login', 'top'), ('top',)
        elif case == 'deaf-server':
            home = (tmp_path / 'deaf').resolve()
            home.mkdir()
            hosts.servers['deaf'] = _Deaf(home, '/bin/bash', tmp_path)
            executor = hosts.server('deaf').executor()
            hosts.executors.append(executor)
            assert executor.run('true', timeout=30).exit_code == 0
            profile, command, names, survivors, expected = '', _shape('tree', pids), PROCESSES, PROCESSES, RUNS_ON
        else:
            executor = _executor(executes, hosts, setting)
            home = _home(executes, hosts, setting)
            profile, command, timeout, names, survivors, by_setting = LIMIT_CASES[case]
            expected = by_setting[setting]
            d = shlex.quote(str(pids))
            profile, command = profile.replace('{pids}', d), command.replace('{pids}', d)
        if profile:
            (home / '.bash_profile').write_text(profile)
        if expected == CUT_SHORT:
            result = executor.run(command, timeout=timeout)
            if (result.stdout, result.exit_code) == ('done\n', 0):
                pytest.fail(f'{label}: expected the command to be cut short, but it completed: {result!r}')
            if case == 'clock-forward' and result.exit_code != launch.NOT_STARTED_EXIT_CODE:
                pytest.fail(f'{label}: expected the command reported as not started: {result!r}')
            return
        start = time.monotonic()
        result = executor.run(command, timeout=TIMEOUT)
        states = _watched(pids, names, start + TIMEOUT + BOUND + SLACK)
        violations = [] if result.exit_code == TIMEOUT_EXIT_CODE else [f'{label}: the call did not time out: {result!r}']
        if expected == RUNS_ON and any(states[name] != 'running' for name in survivors):
            violations.append(f'{label}: expected {", ".join(survivors)} to run on past the bound: {states}')
        elif expected == STOPPED and any(state == 'running' for state in states.values()):
            violations.append(f'{label}: expected every process stopped within the bound: {states}')
        assert violations == [], '\n'.join(violations)
