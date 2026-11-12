"""P2's checker for the runner's signal ends: a signal to tests/mutants.py leaves no sandbox directory.

The frozen gate (verify/cleanup.py) drives a case's child run killed before its session ends (`runner`) and
the runner's stop past LIMIT (`runner-timeout`). Since mutant-child-outlives-timeout landed, the runner also
stops the run whole when it gets SIGTERM, SIGHUP or SIGINT (Ctrl-C), and the seed names those three ends too.
The frozen gate has no row for them; this checker is that row, one per signal:

  the runner (a driver that runs `mutants.main` as `tests/mutants.py`'s `__main__` does, over one planted
  case) is started under a checker-owned TMPDIR, in a session of its own; the case's child test leaves a
  SIGKILL leftover (a sandbox group it kills) and keeps a second sandbox running, records both, and waits;
  the signal goes to the runner alone. Then: the runner ended by that signal; the leftover and the running
  sandbox's directory were made inside the case's scratch; no process the child recorded is still running;
  no sandbox directory and no `mutant-*` scratch is left under the TMPDIR.

Run from the cycle worktree, staged, as
`uv run python -I spec/sandbox-dirs-left-on-kill/remediation/runner-signals.py [--runner-from REV]`;
it prints `ok`/`FAIL` lines and exits 1 on any FAIL. `--runner-from REV` puts REV's tests/mutants.py in
the staged copy instead (the control: on origin/develop the rows must fail). About 10 s a row.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True, check=True).stdout.strip())
SANDBOX_NAME = re.compile(r'cluster-mcp-sandbox\.[A-Za-z0-9]{6}')
SIGNALS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)
PLANT_NAME = 'test_zz_sdlk_signal.py'
FAILS: list[str] = []

PLANT = r'''
import json, os, signal, subprocess, time
from pathlib import Path
import pytest
from conftest import SANDBOX

OUT = Path(os.environ['SDLK_SIGNAL_OUT'])


def group(argv):
    return subprocess.Popen([str(SANDBOX), *argv], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)


def appear(where, before):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        made = sorted(set(where.glob('cluster-mcp-sandbox.*')) - before)
        if made:
            return made[0]
        time.sleep(0.05)
    pytest.fail(f'no sandbox directory appeared under {where}')


@pytest.mark.integration
def test_wait():
    where = Path(os.environ['TMPDIR'])
    before = set(where.glob('cluster-mcp-sandbox.*'))
    dead = group(['sleep', '60'])
    left = appear(where, before)
    os.killpg(dead.pid, signal.SIGKILL)
    dead.wait(10)
    live = group(['sleep', '300'])
    running = appear(where, before | {left})
    (OUT / 'record.json').write_text(json.dumps({'left': str(left), 'running': str(running),
                                                 'pids': [os.getpid(), live.pid]}))
    (OUT / 'ready').touch()
    time.sleep(120)
'''

DRIVER = r'''
import signal, sys
sys.path.insert(0, 'tests')
import mutants
case = mutants.Case(id='sdlk-signal', file='', edits=(), targets=('test_zz_sdlk_signal.py::test_wait',), why='sdlk')
mutants.CASES = (case,)
# As at a terminal: a Ctrl-C raises KeyboardInterrupt, whatever disposition the checker's caller left.
signal.signal(signal.SIGINT, signal.default_int_handler)
mutants.stop_on_signals()
try:
    sys.exit(mutants.main([case.id]))
except mutants.RunnerSignal as caught:
    mutants.die_by(caught.signum)
'''


def check(cond: bool, good: str, bad: str) -> None:
    if cond:
        print(f'ok   runner-signals: {good}', flush=True)
    else:
        FAILS.append(bad)
        print(f'FAIL runner-signals: {bad}', flush=True)


def sandbox_dirs_under(root: Path) -> list[Path]:
    found = []
    for parent, dirs, _ in os.walk(root):
        for name in list(dirs):
            if SANDBOX_NAME.fullmatch(name) and not Path(parent, name).is_symlink():
                found.append(Path(parent, name))
                dirs.remove(name)
    return sorted(found)


def running(pid: int) -> bool:
    ps = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
    return ps.returncode == 0 and 'Z' not in ps.stdout


def kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def row(repo: Path, signum: int) -> None:
    name = signal.Signals(signum).name
    top = Path(tempfile.mkdtemp(prefix='sdlk-signal-'))
    tmp, out = top / 't', top / 'o'
    tmp.mkdir()
    out.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ('VIRTUAL_ENV', 'PYTHONPATH')}
    env.update(TMPDIR=str(tmp), SDLK_SIGNAL_OUT=str(out))
    proc = subprocess.Popen([sys.executable, '-c', DRIVER], cwd=repo, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    record: dict = {}
    try:
        deadline = time.monotonic() + 120
        while not (out / 'ready').exists():
            if proc.poll() is not None or time.monotonic() > deadline:
                stdout, stderr = proc.communicate(timeout=30)
                check(False, '', f'{name}: the child never got ready (runner exit {proc.returncode}): '
                                 f'{stdout[-600:]!r} {stderr[-600:]!r}')
                return
            time.sleep(0.05)
        record = json.loads((out / 'record.json').read_text())
        left, live = Path(record['left']), Path(record['running'])
        scratch = sorted(tmp.glob('mutant-sdlk-signal-*'))
        check(len(scratch) == 1 and all(scratch[0] in p.parents for p in (left, live)) and left.is_dir() and live.is_dir(),
              f"{name}: the child's leftover and its running sandbox are in the case's scratch",
              f"{name}: the child's sandbox directories are not in the case's scratch {scratch}: {left}, {live}")
        os.kill(proc.pid, signum)
        stdout, stderr = proc.communicate(timeout=90)
        check(proc.returncode == -signum, f'{name}: the runner ended by {name}',
              f'{name}: the runner exited {proc.returncode}, not by {name}: {stdout[-400:]!r} {stderr[-600:]!r}')
        alive = [pid for pid in record['pids'] if running(pid)]
        check(not alive, f"{name}: no process the child recorded is still running",
              f'{name}: still running after the runner ended: {alive}')
        extra = sandbox_dirs_under(tmp)
        check(not extra, f"{name}: no sandbox directory of the run is left under the runner's TMPDIR",
              f"{name}: sandbox directories left under the runner's TMPDIR: {extra}")
        scratch = sorted(tmp.glob('mutant-*'))
        check(not scratch, f"{name}: the case's scratch is removed", f'{name}: scratch left: {scratch}')
    finally:
        if proc.poll() is None:
            kill_group(proc.pid)
            proc.communicate(timeout=30)
        for pid in record.get('pids', []):
            kill_group(pid)
        time.sleep(0.2)
        shutil.rmtree(top, ignore_errors=True)


def main(argv: list[str]) -> int:
    runner_from = None
    if argv[:1] == ['--runner-from'] and len(argv) == 2:
        runner_from = argv[1]
    elif argv:
        print(f'usage: {Path(__file__).name} [--runner-from REV]', file=sys.stderr)
        return 2
    top = Path(tempfile.mkdtemp(prefix='sdlk-signal-repo-'))
    try:
        repo = top / 'repo'
        repo.mkdir()
        subprocess.run(['git', '-C', str(ROOT), 'checkout-index', '-a', f'--prefix={repo}/'], check=True)
        (repo / 'tests' / PLANT_NAME).write_text(PLANT)
        if runner_from:
            text = subprocess.run(['git', '-C', str(ROOT), 'show', f'{runner_from}:tests/mutants.py'],
                                  capture_output=True, text=True, check=True).stdout
            (repo / 'tests' / 'mutants.py').write_text(text)
            print(f'note runner-signals: tests/mutants.py from {runner_from}', flush=True)
        for signum in SIGNALS:
            row(repo, signum)
    finally:
        shutil.rmtree(top, ignore_errors=True)
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
