"""Review cycle 1, F1: a directory a stopped test left closed (mode 0o555 or 0) never stops the cleanup.

The frozen gate (verify/cleanup.py) has no row in which a test holds a directory closed when it is stopped,
so its `runner`, `runner-timeout` and `kinds` modes could not see the finding: a bare `shutil.rmtree` raised
`PermissionError` out of the mutation runner's `case_scratch` and out of the suite's sweep. This checker is
those rows, one per site and stop:

  runner limit   `mutants.main` over two planted cases at a patched LIMIT: the first case's test makes
                 closed directories (in its tmp_path, in the case's TMPDIR, and in the HOME of a sandbox it
                 SIGKILLs) and hangs; the second fails as planted. Both cases are reported (the stopped one
                 as a timeout), the runner prints no traceback and keeps nothing, and nothing at all is
                 left under its TMPDIR.
  runner signal  The first case alone, at the default LIMIT; once the closed directories are made the
                 runner gets SIGTERM, SIGHUP or SIGINT. It ends by that signal, prints no traceback, and
                 leaves nothing under its TMPDIR.
  sweep limit    A planted pytest session whose test makes the same closed directories, in the run's own
                 directory and its tmp_path, and stops a sandbox the way a `subprocess.run` timeout does
                 (the wrapper SIGKILLed alone) while that sandbox's HOME holds closed directories. The
                 session passes, names nothing kept, and leaves no sandbox directory and no run directory.
  sweep signal   The same test, which then waits; the session gets SIGINT (Ctrl-C) and its sweep still
                 runs: no sandbox directory and no run directory left, and nothing named kept.
  sweep named    (macOS) A sandbox SIGKILLed while its HOME holds a file the owner made immutable: the
                 session still passes, and its output names the sandbox directory as kept, past pytest's
                 capture of the session's end. Elsewhere this row prints a `skip` line.

Run from the cycle worktree, staged, as
`uv run python -I spec/sandbox-dirs-left-on-kill/remediation/F1-closed-dirs.py [--from REV]`; it prints
`ok`/`FAIL` lines and exits 1 on any FAIL. `--from REV` puts REV's tests/sandbox_dirs.py, tests/mutants.py and
tests/conftest.py in the staged copy instead (the control: at the reviewed commit the rows must fail). About
60 s in all. Every process it starts is in a process group it kills before it returns, and it removes the
`mkdtemp` trees it made, opening what its own rows closed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True, check=True).stdout.strip())
SANDBOX_NAME = re.compile(r'cluster-mcp-sandbox\.[A-Za-z0-9]{6}')
SIGNALS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)
PLANT_NAME = 'test_zz_sdlk_closed.py'
FROM_REV = ('tests/sandbox_dirs.py', 'tests/mutants.py', 'tests/conftest.py')
FAILS: list[str] = []

PLANT = r'''
import os, signal, stat, subprocess, sys, time
from pathlib import Path
import pytest
from conftest import SANDBOX

OUT = Path(os.environ['SDLK_CLOSED_OUT'])
# A sandbox whose command closes two directories in its HOME before it waits.
CLOSE_HOME = ('mkdir -p "$HOME/shut/sub" "$HOME/zero" && echo x > "$HOME/shut/f" && echo x > "$HOME/zero/f" && '
              'chmod 555 "$HOME/shut" && chmod 0 "$HOME/zero" && exec sleep {}')


def closed(parent, mode):
    path = parent / f'closed-{mode:o}'
    (path / 'sub').mkdir(parents=True)
    (path / 'sub' / 'f').write_text('x')
    (path / 'f').write_text('x')
    path.chmod(mode)


def sandboxes(where):
    return set(where.glob('cluster-mcp-sandbox.*'))


def appear(where, before):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        made = sorted(sandboxes(where) - before)
        if made and (made[0] / 'zero').exists():
            return made[0]
        time.sleep(0.05)
    pytest.fail(f'no sandbox directory with a closed HOME appeared under {where}')


def killed_closed(where):
    """A sandbox SIGKILLed by group while the directories its command closed are still closed."""
    before = sandboxes(where)
    proc = subprocess.Popen([str(SANDBOX), 'sh', '-c', CLOSE_HOME.format(60)], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                            env={**os.environ, 'TMPDIR': str(where)})
    made = appear(where, before)
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait(10)
    return made


def timed_out_closed(where):
    """A sandbox stopped as a subprocess.run timeout stops one: its wrapper SIGKILLed alone, its command ending later."""
    before = sandboxes(where)
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run([str(SANDBOX), 'sh', '-c', CLOSE_HOME.format(2)], capture_output=True, timeout=1,
                       env={**os.environ, 'TMPDIR': str(where)})
    made = sorted(sandboxes(where) - before)
    time.sleep(2.5)
    return made


def leave(tmp_path):
    run = Path(os.environ['TMPDIR'])
    made = [killed_closed(run), killed_closed(tmp_path)]
    for mode in (0o555, 0o000):
        closed(run, mode)
        closed(tmp_path, mode)
    return made


@pytest.mark.integration
def test_closed_and_hung(tmp_path):
    # The mutation runner's child: a test stopped while it holds directories closed.
    leave(tmp_path)
    (OUT / 'ready').touch()
    time.sleep(120)


@pytest.mark.integration
def test_quick():
    assert False, 'planted'


@pytest.mark.integration
def test_closed_at_a_limit(tmp_path):
    made = leave(tmp_path) + timed_out_closed(Path(os.environ['TMPDIR']))
    assert all(p.is_dir() for p in made), made


@pytest.mark.integration
def test_closed_then_interrupted(tmp_path):
    leave(tmp_path)
    (OUT / 'ready').touch()
    time.sleep(120)


@pytest.mark.integration
def test_immutable():
    made = killed_closed(Path(os.environ['TMPDIR']))
    stuck = made / 'stuck'
    stuck.write_text('x')
    os.chflags(stuck, stat.UF_IMMUTABLE)
    (OUT / 'stuck').write_text(str(stuck))
'''

DRIVER = r'''
import os, signal, sys
sys.path.insert(0, 'tests')
import mutants
control = mutants.SURVIVOR_CONTROL
mutants.CASES = (
    mutants.Case('closed', control.file, control.edits, ('test_zz_sdlk_closed.py::test_closed_and_hung',), 'hung'),
    mutants.Case('quick', control.file, control.edits, ('test_zz_sdlk_closed.py::test_quick',), 'planted'))
mutants.LIMIT = float(os.environ['SDLK_LIMIT'])
# As at a terminal: a Ctrl-C raises KeyboardInterrupt, whatever disposition the checker's caller left.
signal.signal(signal.SIGINT, signal.default_int_handler)
mutants.stop_on_signals()
try:
    sys.exit(mutants.main(sys.argv[1:]))
except mutants.RunnerSignal as caught:
    mutants.die_by(caught.signum)
'''

SESSION = r'''
import signal, sys
import pytest
signal.signal(signal.SIGINT, signal.default_int_handler)
sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', *sys.argv[1:]]))
'''


def check(cond: bool, good: str, bad: str) -> None:
    if cond:
        print(f'ok   F1-closed-dirs: {good}', flush=True)
    else:
        FAILS.append(bad)
        print(f'FAIL F1-closed-dirs: {bad}', flush=True)


def everything_under(root: Path) -> list[str]:
    found = []
    for parent, dirs, files in os.walk(root):
        for name in dirs:
            path = Path(parent, name)
            if not path.is_symlink() and not os.access(path, os.R_OK | os.X_OK):
                path.chmod(0o755)
        found += [os.path.relpath(Path(parent, name), root) for name in dirs + files]
    return sorted(found)


def sandbox_dirs_under(root: Path) -> list[Path]:
    return [root / p for p in everything_under(root) if SANDBOX_NAME.fullmatch(Path(p).name)]


def scrub(top: Path) -> None:
    """Remove a tree this checker made with mkdtemp, opening first what its rows closed or made immutable."""
    for parent, dirs, files in os.walk(top):
        for name in dirs + files:
            path = Path(parent, name)
            if path.is_symlink():
                continue
            if hasattr(os, 'chflags'):
                try:
                    os.chflags(path, 0)
                except OSError:
                    pass
            if path.is_dir():
                path.chmod(0o755)
    shutil.rmtree(top, ignore_errors=True)


def kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


class Lab:
    def __init__(self, repo: Path, name: str) -> None:
        self.repo, self.name = repo, name
        self.top = Path(tempfile.mkdtemp(prefix=f'sdlk-f1-{name}-'))
        self.tmp, self.out = self.top / 't', self.top / 'o'
        self.tmp.mkdir()
        self.out.mkdir()

    def env(self, **extra: str) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k not in ('VIRTUAL_ENV', 'PYTHONPATH')}
        env.update(TMPDIR=str(self.tmp), SDLK_CLOSED_OUT=str(self.out), **extra)
        return env

    def start(self, argv: list[str], **extra: str) -> subprocess.Popen[str]:
        return subprocess.Popen(argv, cwd=self.repo, env=self.env(**extra), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)

    def wait_ready(self, proc: subprocess.Popen[str]) -> bool:
        deadline = time.monotonic() + 120
        while not (self.out / 'ready').exists():
            if proc.poll() is not None or time.monotonic() > deadline:
                return False
            time.sleep(0.05)
        time.sleep(0.3)
        return True

    def finish(self, proc: subprocess.Popen[str], timeout: float = 120) -> tuple[str, str]:
        try:
            return proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_group(proc.pid)
            return proc.communicate(timeout=30)

    def close(self, proc: subprocess.Popen[str] | None) -> None:
        if proc is not None and proc.poll() is None:
            kill_group(proc.pid)
            proc.communicate(timeout=30)
        time.sleep(0.2)
        scrub(self.top)


def nothing_left(lab: Lab, label: str) -> None:
    left = everything_under(lab.tmp)
    check(not left, f"{label}: nothing is left under the runner's TMPDIR",
          f"{label}: left under the runner's TMPDIR: {left[:8]}")


def no_traceback(label: str, stdout: str, stderr: str, interrupted: bool = False) -> None:
    # A Ctrl-C ends the runner by Python's own exit, which prints the KeyboardInterrupt's traceback.
    text = stdout + stderr
    own = interrupted and text.rstrip().endswith('KeyboardInterrupt') and text.count('Traceback') == 1
    check(('Traceback' not in text or own) and 'PermissionError' not in text, f'{label}: no traceback, no PermissionError',
          f'{label}: a traceback or PermissionError was printed: {text[-800:]!r}')
    check(not re.search(r'^kept ', text, re.M), f'{label}: nothing named as kept',
          f'{label}: something was kept: {[l for l in text.splitlines() if l.startswith("kept ")][:3]}')


def runner_limit(repo: Path) -> None:
    lab = Lab(repo, 'limit')
    proc = None
    try:
        proc = lab.start([sys.executable, '-c', DRIVER, 'closed', 'quick'], SDLK_LIMIT='8')
        stdout, stderr = lab.finish(proc)
        label = 'runner limit'
        check(proc.returncode == 1, f'{label}: the runner ends with its own verdict (exit 1)',
              f'{label}: the runner exited {proc.returncode}: {stdout[-400:]!r} {stderr[-800:]!r}')
        check(re.search(r'^FAILED +closed: timeout', stdout, re.M) is not None,
              f'{label}: the stopped case is reported as a timeout', f'{label}: the stopped case was not reported: {stdout[-600:]!r}')
        check(re.search(r'^killed +quick:', stdout, re.M) is not None, f'{label}: the case after it ran and was reported',
              f'{label}: the case after the stopped one was not reported: {stdout[-600:]!r}')
        no_traceback(label, stdout, stderr)
        nothing_left(lab, label)
    finally:
        lab.close(proc)


def runner_signal(repo: Path, signum: int) -> None:
    name = signal.Signals(signum).name
    label = f'runner {name}'
    lab = Lab(repo, f'sig{signum}')
    proc = None
    try:
        proc = lab.start([sys.executable, '-c', DRIVER, 'closed', 'quick'], SDLK_LIMIT='300')
        if not lab.wait_ready(proc):
            stdout, stderr = lab.finish(proc, 30)
            check(False, '', f'{label}: the child never made its closed directories: {stdout[-400:]!r} {stderr[-600:]!r}')
            return
        os.kill(proc.pid, signum)
        stdout, stderr = lab.finish(proc, 90)
        check(proc.returncode == -signum, f'{label}: the runner ended by {name}',
              f'{label}: the runner exited {proc.returncode}, not by {name}: {stdout[-400:]!r} {stderr[-800:]!r}')
        no_traceback(label, stdout, stderr, interrupted=signum == signal.SIGINT)
        nothing_left(lab, label)
    finally:
        lab.close(proc)


def session_left(lab: Lab, label: str) -> None:
    left = sandbox_dirs_under(lab.tmp)
    check(not left, f'{label}: no sandbox directory is left anywhere under the TMPDIR', f'{label}: sandbox directories left: {left[:5]}')
    runs = sorted(lab.tmp.glob('cluster-mcp-run.*'))
    check(not runs, f"{label}: the run's directory is removed", f"{label}: the run's directory is left: {runs}")


def sweep_limit(repo: Path) -> None:
    lab = Lab(repo, 'sweep-limit')
    proc = None
    label = 'sweep limit'
    try:
        proc = lab.start([sys.executable, '-c', SESSION, f'tests/{PLANT_NAME}::test_closed_at_a_limit'])
        stdout, stderr = lab.finish(proc)
        check(proc.returncode == 0, f'{label}: the session passed', f'{label}: the session exited {proc.returncode}: '
              f'{stdout[-1200:]!r} {stderr[-600:]!r}')
        no_traceback(label, stdout, stderr)
        session_left(lab, label)
    finally:
        lab.close(proc)


def sweep_signal(repo: Path) -> None:
    lab = Lab(repo, 'sweep-sigint')
    proc = None
    label = 'sweep SIGINT'
    try:
        proc = lab.start([sys.executable, '-c', SESSION, f'tests/{PLANT_NAME}::test_closed_then_interrupted'])
        if not lab.wait_ready(proc):
            stdout, stderr = lab.finish(proc, 30)
            check(False, '', f'{label}: the test never made its closed directories: {stdout[-600:]!r} {stderr[-600:]!r}')
            return
        os.kill(proc.pid, signal.SIGINT)
        stdout, stderr = lab.finish(proc, 90)
        check(proc.returncode == 2 and 'KeyboardInterrupt' in stdout, f'{label}: the session was interrupted (exit 2)',
              f'{label}: the session exited {proc.returncode}: {stdout[-1200:]!r} {stderr[-600:]!r}')
        check('PermissionError' not in stdout + stderr and not re.search(r'^kept ', stdout + stderr, re.M),
              f'{label}: no PermissionError, nothing named as kept',
              f'{label}: the sweep raised or kept something: {(stdout + stderr)[-800:]!r}')
        session_left(lab, label)
    finally:
        lab.close(proc)


def sweep_named(repo: Path) -> None:
    label = 'sweep named'
    if not hasattr(os, 'chflags') or not hasattr(stat, 'UF_IMMUTABLE') or sys.platform != 'darwin':
        print(f'skip F1-closed-dirs: {label}: no owner-settable immutable flag on this platform', flush=True)
        return
    lab = Lab(repo, 'sweep-named')
    proc = None
    try:
        proc = lab.start([sys.executable, '-c', SESSION, f'tests/{PLANT_NAME}::test_immutable'])
        stdout, stderr = lab.finish(proc)
        stuck = Path((lab.out / 'stuck').read_text()) if (lab.out / 'stuck').exists() else None
        check(proc.returncode == 0, f'{label}: the session passed', f'{label}: the session exited {proc.returncode}: '
              f'{stdout[-1200:]!r} {stderr[-600:]!r}')
        named = stuck is not None and f'kept {stuck.parent}: it could not all be removed (PermissionError: ' in stdout + stderr
        check(named, f"{label}: the sandbox directory it could not remove is named in the session's output",
              f"{label}: the sandbox directory it could not remove was not named: {(stdout + stderr)[-800:]!r}")
        check(stuck is not None and stuck.exists(), f'{label}: what it could not remove is kept',
              f'{label}: the immutable file is gone: the row proves nothing')
    finally:
        lab.close(proc)


def main(argv: list[str]) -> int:
    from_rev = None
    if argv[:1] == ['--from'] and len(argv) == 2:
        from_rev = argv[1]
    elif argv:
        print(f'usage: {Path(__file__).name} [--from REV]', file=sys.stderr)
        return 2
    top = Path(tempfile.mkdtemp(prefix='sdlk-f1-repo-'))
    try:
        repo = top / 'repo'
        repo.mkdir()
        subprocess.run(['git', '-C', str(ROOT), 'checkout-index', '-a', f'--prefix={repo}/'], check=True)
        (repo / 'tests' / PLANT_NAME).write_text(PLANT)
        if from_rev:
            for name in FROM_REV:
                text = subprocess.run(['git', '-C', str(ROOT), 'show', f'{from_rev}:{name}'], capture_output=True,
                                      text=True, check=True).stdout
                (repo / name).write_text(text)
            print(f'note F1-closed-dirs: {", ".join(FROM_REV)} from {from_rev}', flush=True)
        runner_limit(repo)
        for signum in SIGNALS:
            runner_signal(repo, signum)
        sweep_limit(repo)
        sweep_signal(repo)
        sweep_named(repo)
    finally:
        scrub(top)
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
