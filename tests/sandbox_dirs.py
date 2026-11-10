# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Where a suite run's sandboxes make their directories, and the sweep that removes what they left.

`bin/sandbox.sh` removes its directory from a trap, which a SIGKILL never runs, and the suite's
harnesses stop sandboxes that way. So a run points `TMPDIR`, for every process it starts, at a
directory of its own (`own_tmp`), and when the run ends it removes every sandbox directory left
there or in the run's pytest temporary directory (`sweep`): only a directory named as
`bin/sandbox.sh` names them, and only while no process still has its working directory in it or
names it in its environment.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

SANDBOX = Path(__file__).resolve().parent.parent / 'bin' / 'sandbox.sh'

# `bin/sandbox.sh` makes its directory with mktemp's six-character template.
SANDBOX_NAME = re.compile(r'cluster-mcp-sandbox\.[A-Za-z0-9]{6}')
RUN_PREFIX = 'cluster-mcp-run.'


def leftovers(roots: Iterable[Path]) -> list[Path]:
    """Every sandbox directory under `roots`: a real directory (not a link) with a sandbox's name."""
    found: list[Path] = []
    for root in roots:
        for parent, dirs, _ in os.walk(root):
            for name in list(dirs):
                path = Path(parent, name)
                if SANDBOX_NAME.fullmatch(name) and not path.is_symlink():
                    found.append(path)
                    dirs.remove(name)
    return found


def in_use(candidates: Iterable[Path], table: Iterable[tuple[str, str]]) -> set[Path]:
    """The candidates some process still uses: its working directory is in one, or its environment names one.

    `table` holds one `(cwd, environment)` pair per process, as `processes` reads them.
    """
    rows = list(table)
    busy: set[Path] = set()
    for candidate in candidates:
        names = {str(candidate), os.path.realpath(candidate)}
        for cwd, environment in rows:
            if any(cwd == name or cwd.startswith(name + os.sep) or name in environment for name in names):
                busy.add(candidate)
                break
    return busy


def processes() -> list[tuple[str, str]]:
    """The working directory and environment of every process of this account that can be read."""
    if sys.platform.startswith('linux'):
        return list(_proc_table())
    cwds = subprocess.run([str(SANDBOX), '/usr/sbin/lsof', '-b', '-a', '-d', 'cwd', '-u', str(os.getuid()), '-n', '-P', '-Fn'],
                          capture_output=True, text=True, timeout=60)
    environments = subprocess.run([str(SANDBOX), '/bin/ps', '-E', '-ww', '-U', str(os.getuid()), '-o', 'command='],
                                  capture_output=True, text=True, timeout=60)
    if environments.returncode != 0 or not cwds.stdout:
        raise RuntimeError(f'cannot list the processes using sandbox directories: lsof exited {cwds.returncode}, '
                           f'ps exited {environments.returncode}: {(cwds.stderr + environments.stderr)[-400:]!r}')
    table = [(line[1:], '') for line in cwds.stdout.splitlines() if line.startswith('n')]
    return table + [('', line) for line in environments.stdout.splitlines()]


def _proc_table() -> Iterator[tuple[str, str]]:
    for entry in os.scandir('/proc'):
        if not entry.name.isdigit():
            continue
        try:
            cwd = os.readlink(f'/proc/{entry.name}/cwd')
        except OSError:
            cwd = ''
        try:
            environment = Path(f'/proc/{entry.name}/environ').read_bytes().decode(errors='replace')
        except OSError:
            environment = ''
        yield cwd, environment


def sweep(roots: Iterable[Path]) -> list[Path]:
    """Remove every sandbox directory under `roots` that no process uses; return those kept."""
    found = leftovers(roots)
    if not found:
        return []
    busy = in_use(found, processes())
    for path in found:
        if path not in busy:
            shutil.rmtree(path)
    return sorted(busy)


@contextmanager
def own_tmp(basetemp: Path) -> Iterator[Path]:
    """Point `TMPDIR` at a new directory of this run's while the block runs; then sweep it and `basetemp`.

    In-process temporary files keep the directory they had: `tempfile` resolved it, at the latest
    when it made the run's directory. The run's directory, which only this run's processes were
    given, is removed afterwards with whatever they left in it (a lock file `uv` keeps there), unless
    a sandbox directory in it is still in use.
    """
    run = Path(tempfile.mkdtemp(prefix=RUN_PREFIX))
    saved = os.environ.get('TMPDIR')
    os.environ['TMPDIR'] = str(run)
    try:
        yield run
    finally:
        try:
            kept = sweep([run, basetemp])
        finally:
            if saved is None:
                os.environ.pop('TMPDIR', None)
            else:
                os.environ['TMPDIR'] = saved
        if not any(run in path.parents for path in kept):
            shutil.rmtree(run, ignore_errors=True)
