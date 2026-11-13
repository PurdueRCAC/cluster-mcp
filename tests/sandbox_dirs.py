# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Where a suite run's sandboxes make their directories, and the sweep that removes what they left.

`bin/sandbox.sh` removes its directory from a trap, which a SIGKILL never runs, and the suite's
harnesses stop sandboxes that way. So a run points `TMPDIR`, for every process it starts, at a
directory of its own (`own_tmp`), and when the run ends it removes every sandbox directory left
there or in the run's pytest temporary directory (`sweep`): only a directory named as
`bin/sandbox.sh` names them, and only while no process still has its working directory in it or
names it in its environment. A test stopped while it held a directory closed (mode `0o555` or `0`)
leaves it so; `remove` opens what it removes, and the cleanup never raises: what it cannot remove,
or cannot tell is free, it keeps and names on stderr.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterable, Iterator

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


def reopen(root: Path) -> None:
    """Open, for the owner, each directory under `root` a test left closed, so a scan can see inside it.

    Only a real directory the owner cannot list or enter is opened; a link is never followed, and a sandbox
    directory, and all inside it, is never touched. It is run only on a directory the run's own processes
    alone were given, which is removed whole unless a sandbox directory in it is still in use.
    """
    for parent, dirs, _ in os.walk(root):
        for name in list(dirs):
            path = os.path.join(parent, name)
            if SANDBOX_NAME.fullmatch(name):
                dirs.remove(name)
                continue
            try:
                mode = os.lstat(path).st_mode
                if stat.S_ISDIR(mode) and mode & 0o500 != 0o500:
                    os.chmod(path, stat.S_IMODE(mode) | 0o700)
            except OSError:
                pass


def remove(path: Path) -> OSError | None:
    """Remove the directory tree at `path`; return the error that left part of it, or None once it is gone.

    A directory a test left closed in the tree is opened for the owner first, and so is the directory
    holding `path` when it is closed, which then gets its mode back. Nothing is followed through a link,
    and nothing is raised.
    """
    error = _rmtree(path)
    if error is None:
        return None
    holder = path.parent
    restore = None
    try:
        mode = os.lstat(holder).st_mode
        if stat.S_ISDIR(mode) and mode & 0o300 != 0o300:
            os.chmod(holder, stat.S_IMODE(mode) | 0o300)
            restore = stat.S_IMODE(mode)
    except OSError:
        pass
    try:
        _open_tree(path)
        return _rmtree(path)
    finally:
        if restore is not None:
            try:
                os.chmod(holder, restore)
            except OSError:
                pass


def _rmtree(path: Path) -> OSError | None:
    errors: list[OSError] = []

    def note(_function: object, _path: str, exc: BaseException) -> None:
        if not isinstance(exc, FileNotFoundError):
            errors.append(exc if isinstance(exc, OSError) else OSError(str(exc)))

    shutil.rmtree(path, onexc=note)
    return errors[0] if errors else None


def _open_tree(root: Path) -> None:
    pending = [str(root)]
    while pending:
        directory = pending.pop()
        try:
            mode = os.lstat(directory).st_mode
            if not stat.S_ISDIR(mode):
                continue
            if mode & 0o700 != 0o700:
                os.chmod(directory, stat.S_IMODE(mode) | 0o700)
            with os.scandir(directory) as entries:
                pending.extend(entry.path for entry in entries if entry.is_dir(follow_symlinks=False))
        except OSError:
            continue


def say(line: str) -> None:
    """Name on stderr what the cleanup kept."""
    print(line, file=sys.stderr, flush=True)


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


def sweep(roots: Iterable[Path], tell: Callable[[str], None] = say) -> list[Path]:
    """Remove every sandbox directory under `roots` that no process uses; return those kept.

    When the processes cannot be listed, every one found is kept; one that cannot be removed is kept too.
    `tell` names on stderr each one kept for either reason, never one kept because it is in use.
    """
    found = leftovers(roots)
    if not found:
        return []
    try:
        busy = in_use(found, processes())
    except Exception as exc:
        for path in found:
            tell(f'kept {path}: its processes could not be listed ({type(exc).__name__}: {exc})')
        return sorted(found)
    kept = set(busy)
    for path in found:
        if path not in busy:
            error = remove(path)
            if error is not None:
                kept.add(path)
                tell(f'kept {path}: it could not all be removed ({type(error).__name__}: {error})')
    return sorted(kept)


@contextmanager
def own_tmp(basetemp: Path, tell: Callable[[str], None] = say) -> Iterator[Path]:
    """Point `TMPDIR` at a new directory of this run's while the block runs; then sweep it and `basetemp`.

    In-process temporary files keep the directory they had: `tempfile` resolved it, at the latest
    when it made the run's directory. The run's directory, which only this run's processes were
    given, is removed afterwards with whatever they left in it (a lock file `uv` keeps there), unless
    a sandbox directory in it is kept. `tell` names on stderr what the sweep kept other than for
    being in use, and the run's directory when it cannot all be removed.
    """
    run = Path(tempfile.mkdtemp(prefix=RUN_PREFIX))
    saved = os.environ.get('TMPDIR')
    os.environ['TMPDIR'] = str(run)
    try:
        yield run
    finally:
        try:
            reopen(run)
            kept = sweep([run, basetemp], tell)
        finally:
            if saved is None:
                os.environ.pop('TMPDIR', None)
            else:
                os.environ['TMPDIR'] = saved
        if not any(run in path.parents for path in kept):
            error = remove(run)
            if error is not None:
                tell(f'kept {run}: it could not all be removed ({type(error).__name__}: {error})')
