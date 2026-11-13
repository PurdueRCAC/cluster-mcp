# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""A suite run's sandboxes make their directories in a directory of the run's own, and the sweep at its end
removes what a killed sandbox left there, and nothing else; the mutation runner's case scratch the same.

Both cleanups remove directories a stopped test left closed (mode `0o555` or `0`), never raise, and keep and
name on stderr what they cannot remove or cannot tell is free."""

from __future__ import annotations

import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

import sandbox_dirs
from conftest import SANDBOX


def sandbox_like(parent: Path, name: str) -> Path:
    path = parent / name
    for sub in ('.config', '.cache', '.local/share'):
        (path / sub).mkdir(parents=True)
    return path


@pytest.mark.unit
def test_leftovers_are_directories_with_a_sandbox_name(tmp_path: Path) -> None:
    found = [sandbox_like(tmp_path, 'cluster-mcp-sandbox.Ab12Cd'), sandbox_like(tmp_path / 'a' / 'b', 'cluster-mcp-sandbox.Zz9yX8')]
    sandbox_like(tmp_path, 'cluster-mcp-sandbox.toolong7')
    sandbox_like(tmp_path, 'cluster-mcp-sandbox.short')
    sandbox_like(tmp_path, 'other')
    (tmp_path / 'cluster-mcp-sandbox.Filexx').write_text('a file')
    (tmp_path / 'cluster-mcp-sandbox.Linkxx').symlink_to(found[0], target_is_directory=True)
    assert sorted(sandbox_dirs.leftovers([tmp_path])) == sorted(found)


@pytest.mark.unit
@pytest.mark.parametrize('cwd, environment, busy', [
    pytest.param('{d}', '', True, id='cwd-in-it'),
    pytest.param('{d}/sub', '', True, id='cwd-below-it'),
    pytest.param('{real}', '', True, id='cwd-by-its-real-path'),
    pytest.param('{d}x', '', False, id='cwd-beside-it'),
    pytest.param('/', 'HOME={d}', True, id='named-in-the-environment'),
    pytest.param('/', 'TMPDIR={parent}', False, id='only-its-parent-named'),
    pytest.param('/', '', False, id='unrelated'),
])
def test_a_directory_in_use_is_kept(tmp_path: Path, cwd: str, environment: str, busy: bool) -> None:
    real = tmp_path / 'real'
    real.mkdir()
    (tmp_path / 'link').symlink_to(real, target_is_directory=True)
    directory = sandbox_like(tmp_path / 'link', 'cluster-mcp-sandbox.Ab12Cd')
    fill = {'d': str(directory), 'real': os.path.realpath(directory), 'parent': str(directory.parent)}
    table = [(cwd.format(**fill), environment.format(**fill))]
    assert sandbox_dirs.in_use([directory], table) == ({directory} if busy else set())


@pytest.mark.integration
def test_this_run_points_its_sandboxes_at_a_directory_of_its_own() -> None:
    run = Path(os.environ['TMPDIR'])
    assert run.name.startswith(sandbox_dirs.RUN_PREFIX), run
    shown = subprocess.run([str(SANDBOX), 'sh', '-c', 'printf %s "$CLUSTER_MCP_SANDBOX"'], capture_output=True, text=True,
                           timeout=60, check=True)
    assert Path(shown.stdout).parent == run, shown.stdout


@pytest.mark.integration
def test_the_sweep_keeps_a_running_sandbox_and_removes_it_once_killed(tmp_path: Path) -> None:
    env = {**os.environ, 'TMPDIR': str(tmp_path)}
    proc = subprocess.Popen([str(SANDBOX), 'sh', '-c', 'mkdir -p "$HOME/.cache/x" && echo x > "$HOME/.cache/x/f" && exec sleep 60'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, env=env, start_new_session=True)
    try:
        deadline = time.monotonic() + 20
        while not sandbox_dirs.leftovers([tmp_path]):
            assert time.monotonic() < deadline, 'the sandbox never made its directory'
            time.sleep(0.05)
        made = sandbox_dirs.leftovers([tmp_path])
        assert sandbox_dirs.sweep([tmp_path]) == made
        assert all(path.is_dir() for path in made)
    finally:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(10)
    assert all(path.is_dir() for path in made), 'the trap ran: the row did not leave a directory'
    assert sandbox_dirs.sweep([tmp_path]) == []
    assert not any(path.exists() for path in made)


@pytest.mark.integration
def test_own_tmp_redirects_children_only_and_puts_tmpdir_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tempfile
    monkeypatch.setenv('TMPDIR', str(tmp_path))
    monkeypatch.setattr(tempfile, 'tempdir', None)
    with sandbox_dirs.own_tmp(tmp_path / 'basetemp') as run:
        assert os.environ['TMPDIR'] == str(run) and run.parent == tmp_path
        assert tempfile.gettempdir() == str(tmp_path)
        sandbox_like(run, 'cluster-mcp-sandbox.Ab12Cd')
    assert os.environ['TMPDIR'] == str(tmp_path)
    assert not run.exists()


@pytest.mark.integration
def test_the_sweep_keeps_a_sandbox_whose_command_runs_on_elsewhere(tmp_path: Path) -> None:
    env = {**os.environ, 'TMPDIR': str(tmp_path)}
    proc = subprocess.Popen([str(SANDBOX), sys.executable, '-c', 'import os, time; os.chdir("/"); time.sleep(60)'],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                            start_new_session=True)
    try:
        deadline = time.monotonic() + 20
        while not sandbox_dirs.leftovers([tmp_path]):
            assert time.monotonic() < deadline, 'the sandbox never made its directory'
            time.sleep(0.05)
        time.sleep(0.5)
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(10)
        made = sandbox_dirs.leftovers([tmp_path])
        assert sandbox_dirs.sweep([tmp_path]) == made, 'the directory of a command still running was removed'
    finally:
        os.killpg(proc.pid, signal.SIGKILL)
    assert all(path.is_dir() for path in made)


@pytest.mark.unit
def test_a_case_scratch_whose_processes_cannot_be_listed_is_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                 capsys: pytest.CaptureFixture[str]) -> None:
    # The mutation runner never guesses that a sandbox directory is free: a failed listing keeps the case's scratch.
    import tempfile

    import mutants

    def unlisted() -> list[tuple[str, str]]:
        raise RuntimeError('cannot list the processes using sandbox directories')

    monkeypatch.setenv('TMPDIR', str(tmp_path))
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    monkeypatch.setattr(sandbox_dirs, 'processes', unlisted)
    with mutants.case_scratch('unlisted') as scratch:
        assert os.environ['TMPDIR'] == scratch and Path(scratch).parent == tmp_path
        left = sandbox_like(Path(scratch), 'cluster-mcp-sandbox.Ab12Cd')
    assert os.environ['TMPDIR'] == str(tmp_path)
    assert left.is_dir(), 'the scratch was removed although its processes could not be listed'
    assert capsys.readouterr().err == (f'kept {scratch}: its processes could not be listed '
                                       '(RuntimeError: cannot list the processes using sandbox directories)\n')


# --- directories a stopped test left closed, and what the cleanup cannot remove or cannot tell is free ---

CLOSED = [pytest.param(0o555, id='0o555'), pytest.param(0o000, id='0')]
LISTING_FAILS = 'cannot list the processes using sandbox directories'


def closed(parent: Path, mode: int) -> Path:
    """A directory a test was stopped holding closed: a file and a directory inside it, then `mode`."""
    path = parent / 'closed'
    (path / 'sub').mkdir(parents=True)
    (path / 'sub' / 'f').write_text('x')
    (path / 'f').write_text('x')
    path.chmod(mode)
    return path


def mode_of(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def nothing_runs() -> list[tuple[str, str]]:
    return []


def unlisted() -> list[tuple[str, str]]:
    raise RuntimeError(LISTING_FAILS)


@contextmanager
def no_raise(cleanup: str) -> Iterator[None]:
    """Fail the row, naming the contract, when `cleanup` raises instead of keeping and naming what it cannot remove."""
    try:
        yield
    except Exception as exc:
        pytest.fail(f'{cleanup} raised instead of keeping and naming what it could not remove: {exc!r}')


def outside_the_run(parent: Path, mode: int) -> tuple[Path, Path]:
    """A directory outside the cleanup's reach holding a closed one; return both, to link to from inside."""
    outside = parent / 'outside'
    return outside, closed(outside, mode)


def using(*paths: Path):
    """A process table in which one process names each of `paths` in its environment."""
    return lambda: [('', f'HOME={path}') for path in paths]


@pytest.fixture
def own(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """`TMPDIR` is `tmp_path`, as the caller's; afterwards every directory under it is opened, for pytest's own cleanup."""
    monkeypatch.setenv('TMPDIR', str(tmp_path))
    monkeypatch.setattr(tempfile, 'tempdir', None)
    yield tmp_path
    for parent, dirs, _ in os.walk(tmp_path):
        for name in dirs:
            path = Path(parent, name)
            if not path.is_symlink():
                path.chmod(0o755)


@pytest.mark.unit
@pytest.mark.parametrize('mode', CLOSED)
def test_the_sweep_removes_what_a_stopped_test_left_closed(own: Path, mode: int, monkeypatch: pytest.MonkeyPatch,
                                                           capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sandbox_dirs, 'processes', nothing_runs)
    basetemp = own / 'basetemp'
    outside, target = outside_the_run(own, mode)
    with no_raise('the sweep'), sandbox_dirs.own_tmp(basetemp) as run:
        killed = sandbox_like(run, 'cluster-mcp-sandbox.Ab12Cd')
        closed(killed / '.cache', mode)
        closed(run / 'test_left', mode)
        (run / 'link').symlink_to(outside, target_is_directory=True)
        (run / 'link_closed').symlink_to(target, target_is_directory=True)
        in_base = sandbox_like(basetemp / 'test_x0', 'cluster-mcp-sandbox.Zz9yX8')
        closed(in_base / '.config', mode)
        holder = basetemp / 'test_y0' / 'held'
        held = sandbox_like(holder, 'cluster-mcp-sandbox.Hh7gF6')
        holder.chmod(0o555)
        other = closed(basetemp / 'test_z0', mode)
    assert os.environ['TMPDIR'] == str(own)
    assert capsys.readouterr().err == '', 'the sweep kept something it could remove'
    assert not run.exists(), "the run's directory was not removed with what a stopped test left closed in it"
    assert not in_base.exists(), "a killed sandbox's directory holding a closed directory was left in the pytest temporary directory"
    assert not held.exists(), "a killed sandbox's directory in a closed directory was left"
    assert mode_of(holder) == 0o555, 'the closed directory holding a removed sandbox directory did not get its mode back'
    assert mode_of(other) == mode, 'a closed directory in the pytest temporary directory, not a sandbox directory, was altered'
    assert mode_of(target) == mode, "a closed directory reached through a link out of the run's directory was altered"


@pytest.mark.unit
@pytest.mark.parametrize('where', ['sandbox', 'run'])
def test_what_the_sweep_cannot_remove_is_kept_and_named(own: Path, where: str, monkeypatch: pytest.MonkeyPatch,
                                                        capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sandbox_dirs, 'processes', nothing_runs)
    unlink = os.unlink

    def stuck(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if os.path.basename(path) == 'stuck':
            raise PermissionError(13, 'Operation not permitted', path)
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        with no_raise('the sweep'), sandbox_dirs.own_tmp(own / 'basetemp') as run:
            killed = sandbox_like(run, 'cluster-mcp-sandbox.Ab12Cd')
            (killed / 'stuck' if where == 'sandbox' else run / 'stuck').write_text('x')
            closed(run / 'test_left', 0o000)
            patch.setattr(os, 'unlink', stuck)
    assert os.environ['TMPDIR'] == str(own)
    left = killed if where == 'sandbox' else run
    assert (left / 'stuck').exists(), 'the file that could not be removed is gone: the row proves nothing'
    err = capsys.readouterr().err
    assert err.startswith(f'kept {left}: it could not all be removed (PermissionError: ') and err.count('\n') == 1, \
        f'what the sweep could not remove was not named on stderr: {err!r}'


@pytest.mark.unit
def test_the_sweep_keeps_what_it_finds_when_its_processes_cannot_be_listed(own: Path, monkeypatch: pytest.MonkeyPatch,
                                                                         capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sandbox_dirs, 'processes', unlisted)
    basetemp = own / 'basetemp'
    with no_raise('the sweep'), sandbox_dirs.own_tmp(basetemp) as run:
        in_run = sandbox_like(run, 'cluster-mcp-sandbox.Ab12Cd')
        in_base = sandbox_like(basetemp / 'test_x0', 'cluster-mcp-sandbox.Zz9yX8')
    assert os.environ['TMPDIR'] == str(own)
    assert in_run.is_dir() and in_base.is_dir(), 'the sweep removed a sandbox directory although its processes could not be listed'
    assert run.is_dir(), "the run's directory was removed although its processes could not be listed"
    assert capsys.readouterr().err == ''.join(f'kept {path}: its processes could not be listed (RuntimeError: {LISTING_FAILS})\n'
                                              for path in (in_run, in_base)), 'what the sweep kept was not named on stderr'


@pytest.mark.unit
def test_the_sweep_takes_the_runs_pytest_temporary_directory(own: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sandbox_dirs, 'processes', nothing_runs)
    basetemp = own / 'basetemp'
    with sandbox_dirs.own_tmp(basetemp):
        killed = sandbox_like(basetemp / 'test_x0' / 'deep', 'cluster-mcp-sandbox.Zz9yX8')
        kept = sandbox_like(basetemp / 'test_x0', 'other')
    assert not killed.exists(), "the sweep left a killed sandbox's directory in the run's pytest temporary directory"
    assert kept.is_dir(), 'the sweep removed a directory in the pytest temporary directory that is not a sandbox directory'


@pytest.mark.unit
def test_a_run_directory_holding_a_sandbox_in_use_is_kept(own: Path, monkeypatch: pytest.MonkeyPatch,
                                                          capsys: pytest.CaptureFixture[str]) -> None:
    with sandbox_dirs.own_tmp(own / 'basetemp') as run:
        running = sandbox_like(run, 'cluster-mcp-sandbox.Ab12Cd')
        (run / 'uv.lock').write_text('')
        monkeypatch.setattr(sandbox_dirs, 'processes', using(running))
    assert run.is_dir() and (run / 'uv.lock').exists(), "the run's directory was removed while a sandbox directory in it was in use"
    assert sorted(os.listdir(running)) == ['.cache', '.config', '.local'], 'a sandbox directory still in use was changed'
    assert capsys.readouterr().err == '', 'a sandbox directory kept for being in use was named as a failure'


@pytest.mark.unit
def test_a_sandbox_in_use_under_a_directory_left_closed_is_seen(own: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with sandbox_dirs.own_tmp(own / 'basetemp') as run:
        hidden = run / 'test_left'
        running = sandbox_like(hidden, 'cluster-mcp-sandbox.Ab12Cd')
        inner = closed(running / '.cache', 0o000)
        hidden.chmod(0o000)
        monkeypatch.setattr(sandbox_dirs, 'processes', using(running))
    assert run.is_dir(), "the run's directory was removed with a sandbox in use hidden under a directory a test left closed"
    assert running.is_dir() and mode_of(inner) == 0o000, 'a sandbox directory in use was removed or changed'


# --- the mutation runner's case scratch ---


@pytest.mark.unit
@pytest.mark.parametrize('mode', CLOSED)
def test_a_case_scratch_a_stopped_test_left_closed_is_removed(own: Path, mode: int, monkeypatch: pytest.MonkeyPatch,
                                                             capsys: pytest.CaptureFixture[str]) -> None:
    import mutants

    monkeypatch.setattr(sandbox_dirs, 'processes', nothing_runs)
    outside, target = outside_the_run(own, mode)
    with no_raise('the case scratch'), mutants.case_scratch('closed') as scratch:
        closed(Path(scratch, 'pytest-of-x', 'pytest-0', 'test_x0'), mode)
        killed = sandbox_like(Path(scratch), 'cluster-mcp-sandbox.Ab12Cd')
        closed(killed / '.cache', mode)
        Path(scratch, 'link').symlink_to(outside, target_is_directory=True)
        Path(scratch, 'link_closed').symlink_to(target, target_is_directory=True)
    assert os.environ['TMPDIR'] == str(own)
    assert capsys.readouterr().err == '', 'the case scratch was kept although nothing in it was in use'
    assert not os.path.exists(scratch), 'a case scratch holding a directory a stopped test left closed was not removed'
    assert mode_of(target) == mode, 'a closed directory reached through a link out of the case scratch was altered'


@pytest.mark.unit
def test_what_a_case_scratch_cannot_remove_is_kept_and_named(own: Path, monkeypatch: pytest.MonkeyPatch,
                                                            capsys: pytest.CaptureFixture[str]) -> None:
    import mutants

    monkeypatch.setattr(sandbox_dirs, 'processes', nothing_runs)
    unlink = os.unlink

    def stuck(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if os.path.basename(path) == 'stuck':
            raise PermissionError(13, 'Operation not permitted', path)
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        with no_raise('the case scratch'), mutants.case_scratch('stuck') as scratch:
            Path(scratch, 'stuck').write_text('x')
            closed(Path(scratch), 0o000)
            patch.setattr(os, 'unlink', stuck)
    assert os.environ['TMPDIR'] == str(own)
    assert Path(scratch, 'stuck').exists(), 'the file that could not be removed is gone: the row proves nothing'
    err = capsys.readouterr().err
    assert err.startswith(f'kept {scratch}: it could not all be removed (PermissionError: ') and err.count('\n') == 1, \
        f'what the case scratch could not remove was not named on stderr: {err!r}'


@pytest.mark.unit
def test_a_case_scratch_holding_a_sandbox_in_use_is_kept(own: Path, monkeypatch: pytest.MonkeyPatch,
                                                        capsys: pytest.CaptureFixture[str]) -> None:
    import mutants

    with mutants.case_scratch('busy') as scratch:
        running = sandbox_like(Path(scratch), 'cluster-mcp-sandbox.Ab12Cd')
        monkeypatch.setattr(sandbox_dirs, 'processes', using(running))
    assert running.is_dir(), "the case's scratch was removed while a sandbox directory in it was in use"
    assert capsys.readouterr().err == f'kept {scratch}: a process of the child run still uses a sandbox directory in it\n', \
        'the case scratch kept for a sandbox in use was not named on stderr'


@pytest.mark.unit
def test_a_case_scratch_with_a_sandbox_in_use_under_a_directory_left_closed_is_kept(own: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import mutants

    with mutants.case_scratch('hidden') as scratch:
        hidden = Path(scratch, 'pytest-of-x', 'pytest-0', 'test_x0')
        running = sandbox_like(hidden, 'cluster-mcp-sandbox.Ab12Cd')
        inner = closed(running / '.cache', 0o000)
        hidden.chmod(0o000)
        monkeypatch.setattr(sandbox_dirs, 'processes', using(running))
    assert running.is_dir(), "the case's scratch was removed with a sandbox in use hidden under a directory a test left closed"
    assert mode_of(inner) == 0o000, 'a sandbox directory in use was changed'
