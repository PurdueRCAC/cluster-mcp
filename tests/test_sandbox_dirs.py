# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""A suite run's sandboxes make their directories in a directory of the run's own, and the sweep at its end
removes what a killed sandbox left there, and nothing else."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

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
