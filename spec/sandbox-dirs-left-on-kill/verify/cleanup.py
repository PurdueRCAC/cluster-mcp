"""The frozen gate for sandbox-dirs-left-on-kill: a suite run and the mutation runner leave no sandbox directory.

Run from the cycle worktree, staged, as `uv run python -I spec/sandbox-dirs-left-on-kill/verify/cleanup.py MODE…`;
each mode prints `ok  MODE: …` or `FAIL MODE: …` lines and the script exits 1 on any FAIL.

Modes:
  files           R5: bin/sandbox.sh is byte-identical to develop at BASE; the cycle changes only ALLOWED paths.
  units           The suite's own rows for the sweep (tests/test_sandbox_dirs.py) pass in a staged copy.
  kinds           R1: one planted pytest session SIGKILLs a sandbox through each harness kind of the GOAL's
                  Problem items 1–5 (the loopback SSH server's close and a group signal, the launcher's KILL
                  after TERM, the MCP stdio client's stop, a server stopped by group under the run's TMPDIR,
                  under tmp_path and under a directory nested in tmp_path, and a subprocess.run timeout).
                  Each row proves its sandbox made its directory where the run put it and that the kill
                  left it; after the session every one is gone, and no sandbox directory is left under the
                  gate's TMPDIR, and the run's own directory is gone too.
  guards          R3/R4: a second session (another run) holds a leftover while a planted session ends; a
                  directory left before the run (in TMPDIR, in another run's directory, in an older pytest
                  basetemp); a regular file, a link and a wrongly named directory in the run's directory and
                  tmp_path; a sandbox whose wrapper still runs; a sandbox whose command still runs outside
                  its directory after its wrapper was killed. All of them survive the sweep, unchanged; the
                  other run's leftover goes once that run ends.
  runner          R2: a mutation case whose child run (and its tests' sandboxes) dies by SIGKILL before its
                  session ends, for a case on the package and one planting a repository copy: no sandbox
                  directory and no case scratch is left under TMPDIR, and TMPDIR is put back. R4: a child
                  that ends normally leaving a sandbox running keeps that sandbox's directory.
  runner-timeout  R2: the same through the runner's own stop at a patched LIMIT (needs
                  mutant-child-outlives-timeout's stop in tests/mutants.py).
  sample          R6: the mutation sample and --self-check print exactly sample.expected (develop's
                  runner at BASE, on this host).
  rebase          tests/mutants.py merges with mutant-child-outlives-timeout's, in either order, with no
                  conflict (its branch while it exists, else origin/develop).
  cost            Prints the sweep's measured cost: no leftover, and 60 leftovers (the figure for the
                  maintainer, PLAN § 3 row D4); fails only if the sweep leaves one.
  suite           R1/R6: the profile verify's eight suite commands and its last command, under a gate-owned
                  TMPDIR: each exits 0, no sandbox directory is left anywhere under that TMPDIR, and the
                  tests skipped are exactly develop-skips.txt (develop at BASE, on this host).
  mutants         The mutant sweep of the cleanup: each plant in mutants.json, applied to a staged copy,
                  is killed by its named mode with its message; the plan's decision ids are all covered.
  ledger          Every deferral phrase in TECH.md's phase bodies names an issues/ seed that exists and a
                  ROADMAP.md entry.

Footprint: one pytest session at a time (guards: two, one of them idle), each starting at most four
sandboxes; under 1 GB. kinds/guards/runner about 20–40 s each on a development host; sample about
110 s; suite about 26 min (run it in the background); mutants about one kinds/guards/runner run per
plant. Every process a mode starts is in a process group it kills before it returns.
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

BASE = '0bfacae'
SLUG = 'sandbox-dirs-left-on-kill'
SIBLING = 'fix/mutant-child-outlives-timeout'
HERE = Path(__file__).resolve().parent
ROOT = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True, check=True).stdout.strip())
PATTERN = 'cluster-mcp-sandbox.*'
SANDBOX_NAME = re.compile(r'cluster-mcp-sandbox\.[A-Za-z0-9]{6}')
ALLOWED = ('tests/sandbox_dirs.py', 'tests/conftest.py', 'tests/mutants.py', 'tests/test_sandbox_dirs.py',
           'AGENTS.md', f'issues/{SLUG}.md', 'ROADMAP.md')
SAMPLE = ('isolation-module-global', 'auth-middleware-sets-first-call-only', 'read-hook-resolves-storage-only',
          'ssh-timeout-raises', 'delegate-tilde-server-home', 'timeout-sentinel-minus-one', 'sftp-tilde-root',
          'local-record-scan-from-end', 'ladder-rungs-1-2-swapped', 'boundary-leaks-traceback',
          'site-agents-md-included', 'startup-ssh-unbounded', 'launcher-arg-unquoted', 'prologue-unalias-shared-line',
          'legacy-command-silent', 'env-legacy-wins', 'capability-order-from-discovery', 'readme-window-altered',
          'probe-parse-newline-always', 'tpc-watchdog-dropped', 'shol-hook-removed', 'signal-death-not-reraised')
# The decisions the mutant sweep must cover (PLAN § 6); each needs at least one plant in mutants.json.
DECISIONS = ('redirect-set', 'redirect-pinned', 'redirect-restored', 'sweep-run-dir', 'sweep-basetemp', 'sweep-nested',
             'name-exact', 'name-dir-only', 'no-links', 'live-cwd', 'live-env', 'live-realpath', 'run-dir-rmdir',
             'run-dir-kept', 'runner-tmpdir', 'runner-restored', 'runner-live', 'sweep-content', 'no-outside-sweep',
             'harness-not-redirected')
SAVED_ENV = dict(os.environ)
# A repository to run the planted modes in instead of a staged copy (`--repo`: the mutant sweep's planted copy).
REPO: Path | None = None

FAILS: list[str] = []


def ok(mode: str, text: str) -> None:
    print(f'ok   {mode}: {text}', flush=True)


def fail(mode: str, text: str) -> None:
    FAILS.append(f'{mode}: {text}')
    print(f'FAIL {mode}: {text}', flush=True)


def check(mode: str, cond: bool, good: str, bad: str) -> None:
    (ok if cond else fail)(mode, good if cond else bad)


def child_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in SAVED_ENV.items() if k not in ('VIRTUAL_ENV', 'PYTHONPATH')}
    env.update(extra)
    return env


def sandbox_dirs_under(root: Path) -> list[Path]:
    found = []
    for parent, dirs, _ in os.walk(root):
        for name in list(dirs):
            if SANDBOX_NAME.fullmatch(name) and not Path(parent, name).is_symlink():
                found.append(Path(parent, name))
                dirs.remove(name)
    return sorted(found)


def staged_copy(dest: Path) -> Path:
    """The index (what a phase stages) checked out into `dest/repo`."""
    repo = dest / 'repo'
    repo.mkdir(parents=True)
    subprocess.run(['git', '-C', str(ROOT), 'checkout-index', '-a', f'--prefix={repo}/'], check=True)
    return repo


def kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


# --- the planted modules --------------------------------------------------------------------------

PLANT = r'''
import json, os, signal, subprocess, sys, time
from pathlib import Path
import pytest
from conftest import SANDBOX
from harness import ERA, stdio_tools
from ssh_server import LoopbackSSH
from cluster_mcp.core.executor import launch

GATE = Path(os.environ['SDLK_GATE'])
PATTERN = 'cluster-mcp-sandbox.*'


def record(row, paths, **extra):
    with (GATE / 'manifest.jsonl').open('a') as out:
        out.write(json.dumps({'row': row, 'paths': [str(p) for p in paths], **extra}) + '\n')


def run_tmp():
    return Path(os.environ['TMPDIR'])


def snapshot(where):
    return set(where.glob(PATTERN))


def appear(where, before, wanted=1, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        made = sorted(snapshot(where) - before)
        if len(made) >= wanted:
            return made
        time.sleep(0.05)
    pytest.fail(f'no sandbox directory appeared under {where}: the sandbox did not take the TMPDIR given it')


def left(row, made):
    assert made and all(p.is_dir() for p in made), f'{row}: the kill did not leave the directory: {made}'
    record(row, made)


# A leftover that holds content, as a real one does (FastMCP's version cache, files under HOME).
FILL_HOME = 'mkdir -p "$HOME/.cache/x" && echo x > "$HOME/.cache/x/f" && exec sleep 60'


def filled(made, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not all((p / '.cache' / 'x' / 'f').exists() for p in made):
        assert time.monotonic() < deadline, f'the sandbox never wrote under its HOME: {made}'
        time.sleep(0.05)


def group(argv, env=None):
    return subprocess.Popen([str(SANDBOX), *argv], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, env=env, start_new_session=True)


@pytest.mark.integration
def test_run_dir():
    # What a run's own processes leave in its directory besides sandboxes: a lock file uv keeps
    # there, and a link out of it, whose target must survive the directory's removal.
    run = run_tmp()
    (run / 'uv-0000000000000000.lock').write_text('')
    outside = GATE / 'outside-run'
    (outside / 'cluster-mcp-sandbox.Insidr').mkdir(parents=True)
    (outside / 'keep').write_text('keep')
    (run / 'escape').symlink_to(outside, target_is_directory=True)
    record('run-dir', [run])


@pytest.mark.integration
def test_ssh_close(tmp_path):
    where, home = run_tmp(), tmp_path / 'home'
    home.mkdir()
    before = snapshot(where)
    server = LoopbackSSH(home, '/bin/bash', tmp_path)
    server._launch('exec sleep 60')
    made = appear(where, before)
    server.close()
    left('ssh-close', made)


@pytest.mark.integration
def test_ssh_signal(tmp_path):
    where, home = run_tmp(), tmp_path / 'home'
    home.mkdir()
    before = snapshot(where)
    server = LoopbackSSH(home, '/bin/bash', tmp_path)
    try:
        proc = server._launch('exec sleep 60')
        made = appear(where, before)
        os.killpg(proc.pid, signal.SIGQUIT)
        proc.wait(10)
    finally:
        server.close()
    left('ssh-signal', made)


@pytest.mark.integration
def test_launcher_kill():
    where = run_tmp()
    before = snapshot(where)
    launch.run_process([str(SANDBOX), 'sh', '-c', 'trap "" TERM; exec sleep 60'], None, 1.0)
    left('launcher-kill', sorted(snapshot(where) - before))


@pytest.mark.integration
def test_stdio_client_kill():
    where = run_tmp()
    before = snapshot(where)
    with pytest.raises(BaseException):
        stdio_tools([str(SANDBOX), 'sh', '-c', 'trap "" TERM; exec sleep 60'], ERA, timeout=3)
    left('stdio-kill', sorted(snapshot(where) - before))


@pytest.mark.integration
@pytest.mark.parametrize('place', ['run', 'tmp_path', 'nested'])
def test_group_kill(place, tmp_path):
    where = {'run': run_tmp(), 'tmp_path': tmp_path, 'nested': tmp_path / 'a' / 'b'}[place]
    where.mkdir(parents=True, exist_ok=True)
    env = None if place == 'run' else {**os.environ, 'TMPDIR': str(where)}
    before = snapshot(where)
    proc = group(['sh', '-c', FILL_HOME], env)
    made = appear(where, before)
    filled(made)
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait(10)
    left(f'group-kill-{place}', made)


@pytest.mark.integration
def test_run_timeout():
    where = run_tmp()
    before = snapshot(where)
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run([str(SANDBOX), 'sh', '-c', FILL_HOME.replace('sleep 60', 'sleep 3')], capture_output=True, timeout=1)
    made = sorted(snapshot(where) - before)
    time.sleep(3)
    left('run-timeout', made)


@pytest.mark.integration
def test_live_wrapper():
    where = run_tmp()
    before = snapshot(where)
    proc = group(['sleep', '300'])
    made = appear(where, before)
    time.sleep(0.3)
    record('live-wrapper', made, pgid=proc.pid, listing=sorted(os.listdir(made[0])))


@pytest.mark.integration
def test_live_command():
    where = run_tmp()
    before = snapshot(where)
    # A command that is not a system binary: macOS shows no system binary's environment (PLAN § 3 row D2).
    proc = group([sys.executable, '-c', 'import os, time; os.chdir("/"); time.sleep(300)'])
    made = appear(where, before)
    time.sleep(0.5)
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait(10)
    record('live-command', made, pgid=proc.pid, listing=sorted(os.listdir(made[0])))


@pytest.mark.integration
def test_decoys(tmp_path):
    run = run_tmp()
    target = GATE / 'outside'
    target.mkdir()
    (target / 'keep').write_text('keep')
    (target / 'cluster-mcp-sandbox.Insidx').mkdir()
    (run / 'cluster-mcp-sandbox.Filexx').write_text('file')
    (run / 'cluster-mcp-sandbox.Linkxx').symlink_to(target, target_is_directory=True)
    (run / 'cluster-mcp-sandbox.toolong7').mkdir()
    (run / 'other').mkdir()
    (run / 'other' / 'f').write_text('f')
    (tmp_path / 'cluster-mcp-sandbox.Filexy').write_text('file')
    parent = Path(os.environ['SDLK_PARENT'])
    before = snapshot(parent)
    adhoc = group(['sleep', '60'], {**os.environ, 'TMPDIR': str(parent)})
    made = appear(parent, before)
    os.killpg(adhoc.pid, signal.SIGKILL)
    adhoc.wait(10)
    record('adhoc', made)
    record('decoys', [run / 'cluster-mcp-sandbox.Filexx', run / 'cluster-mcp-sandbox.Linkxx',
                      run / 'cluster-mcp-sandbox.toolong7', run / 'other' / 'f', tmp_path / 'cluster-mcp-sandbox.Filexy'],
           run=str(run))


@pytest.mark.integration
def test_hold():
    where = run_tmp()
    before = snapshot(where)
    proc = group(['sleep', '60'])
    made = appear(where, before)
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait(10)
    record('other-run', made, run=str(where))
    deadline = time.monotonic() + 240
    while not (GATE / 'release').exists():
        assert time.monotonic() < deadline, 'never released'
        time.sleep(0.1)


@pytest.mark.integration
def test_die(tmp_path):
    # The mutation runner's child: leave a SIGKILL leftover under the run's TMPDIR and under tmp_path,
    # then die with the sandbox that runs this pytest, before the session can end.
    assert os.environ.get('CLUSTER_MCP_SANDBOX'), 'not inside a sandbox'
    assert os.getppid() != int(os.environ['SDLK_GATE_PID']), 'the parent is the gate'
    made = []
    for where in (run_tmp(), tmp_path):
        before = snapshot(where)
        proc = group(['sleep', '60'], {**os.environ, 'TMPDIR': str(where)})
        made += appear(where, before)
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(10)
    record('child-left', made)
    os.kill(os.getppid(), signal.SIGKILL)
    os.kill(os.getpid(), signal.SIGKILL)


@pytest.mark.integration
def test_orphan():
    # The child ends normally, leaving a sandboxed command running on outside its directory.
    before = snapshot(run_tmp())
    proc = group([sys.executable, '-c', 'import os, time; os.chdir("/"); time.sleep(300)'])
    made = appear(run_tmp(), before)
    time.sleep(0.5)
    record('child-orphan', made, pgid=proc.pid, listing=sorted(os.listdir(made[0])))


@pytest.mark.integration
def test_hang():
    before = snapshot(run_tmp())
    proc = group(['sleep', '60'])
    made = appear(run_tmp(), before)
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait(10)
    live = group(['sleep', '300'])
    record('child-hang', made, pgid=live.pid)
    time.sleep(120)
'''

PLANT_NAME = 'test_zz_sdlk_plant.py'
KINDS = ('ssh-close', 'ssh-signal', 'launcher-kill', 'stdio-kill', 'group-kill-run', 'group-kill-tmp_path',
         'group-kill-nested', 'run-timeout')


class Lab:
    """A gate-owned TMPDIR `tmp` with a staged copy of the repository carrying the planted module."""

    def __init__(self) -> None:
        self.top = Path(tempfile.mkdtemp(prefix='sdlk-gate-'))
        self.tmp = self.top / 't'
        self.gate = self.top / 'g'
        self.tmp.mkdir()
        self.gate.mkdir()
        self.repo = REPO or staged_copy(self.top)
        (self.repo / 'tests' / PLANT_NAME).write_text(PLANT)
        self.groups: list[int] = []

    def env(self, **extra: str) -> dict[str, str]:
        return child_env(TMPDIR=str(self.tmp), SDLK_GATE=str(self.gate), SDLK_GATE_PID=str(os.getpid()),
                         SDLK_PARENT=str(self.tmp), **extra)

    def pytest(self, selector: str, wait: bool = True) -> subprocess.Popen[str] | subprocess.CompletedProcess[str]:
        argv = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', f'tests/{PLANT_NAME}', '-k', selector]
        if not wait:
            proc = subprocess.Popen(argv, cwd=self.repo, env=self.env(), stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, start_new_session=True)
            self.groups.append(proc.pid)
            return proc
        return subprocess.run(argv, cwd=self.repo, env=self.env(), capture_output=True, text=True, timeout=300,
                              start_new_session=True)

    def rows(self) -> list[dict]:
        manifest = self.gate / 'manifest.jsonl'
        return [json.loads(line) for line in manifest.read_text().splitlines()] if manifest.exists() else []

    def close(self) -> None:
        for pgid in self.groups + [r['pgid'] for r in self.rows() if 'pgid' in r]:
            kill_group(pgid)
        time.sleep(0.2)
        shutil.rmtree(self.top, ignore_errors=True)


def leftovers_outside(lab: Lab, allowed: set[Path]) -> list[Path]:
    return [p for p in sandbox_dirs_under(lab.tmp) if p not in allowed]


# --- modes ----------------------------------------------------------------------------------------

def mode_files() -> None:
    same = subprocess.run(['git', '-C', str(ROOT), 'diff', '--quiet', BASE, '--', 'bin/sandbox.sh']).returncode == 0
    staged = subprocess.run(['git', '-C', str(ROOT), 'diff', '--cached', '--quiet', '--', 'bin/sandbox.sh']).returncode == 0
    check('files', same and staged, 'R5: bin/sandbox.sh is byte-identical to develop at ' + BASE,
          'R5: bin/sandbox.sh differs from develop at ' + BASE)
    changed = subprocess.run(['git', '-C', str(ROOT), 'diff', '--cached', '--name-only', BASE], capture_output=True,
                             text=True, check=True).stdout.split()
    stray = [f for f in changed if f not in ALLOWED and not f.startswith(f'spec/{SLUG}/')]
    check('files', not stray, 'the cycle changes only its allowed paths', f'paths outside the allowed set: {stray}')


def mode_kinds() -> None:
    lab = Lab()
    try:
        result = lab.pytest('test_run_dir or test_ssh or test_launcher or test_stdio or test_group_kill or test_run_timeout')
        check('kinds', result.returncode == 0, 'every harness kind made its directory under the TMPDIR given it, and its kill left it',
              f'a planted row failed (exit {result.returncode}): {result.stdout[-1500:]}')
        rows = {r['row']: r for r in lab.rows()}
        missing = [k for k in KINDS if k not in rows]
        check('kinds', not missing, f'all {len(KINDS)} harness kinds ran', f'rows that did not run: {missing}')
        for kind in KINDS:
            if kind in rows:
                still = [p for p in rows[kind]['paths'] if Path(p).exists()]
                check('kinds', not still, f'R1 {kind}: its leftover is gone after the session',
                      f'R1 {kind}: still there after the session: {still}')
        extra = leftovers_outside(lab, set())
        check('kinds', not extra, 'R1: no sandbox directory left anywhere under the TMPDIR',
              f'R1: sandbox directories left under the TMPDIR: {extra}')
        run = Path(rows['run-dir']['paths'][0]) if 'run-dir' in rows else None
        check('kinds', run is not None and run.parent == lab.tmp and run.name.startswith('cluster-mcp-run.'),
              "the session pointed TMPDIR at a directory of its own under the one it was given",
              f"the session's TMPDIR was {run}, not a cluster-mcp-run.* directory under {lab.tmp}")
        runs = sorted(lab.tmp.glob('cluster-mcp-run.*'))
        check('kinds', run is not None and not runs, "the run's own directory is removed, with the lock file its processes left",
              f"the run's directory is still there: {runs} holding {[sorted(os.listdir(r)) for r in runs]}")
        outside = lab.gate / 'outside-run'
        check('kinds', (outside / 'keep').is_file() and (outside / 'cluster-mcp-sandbox.Insidr').is_dir(),
              "R3: a link out of the run's directory is removed, not followed",
              f'R3: removing the run directory reached through its link into {outside}')
    finally:
        lab.close()


def mode_guards() -> None:
    lab = Lab()
    try:
        pre = [lab.tmp / 'cluster-mcp-sandbox.PreXst', lab.tmp / 'cluster-mcp-run.decoy123' / 'cluster-mcp-sandbox.Decoy1',
               lab.tmp / f'pytest-of-{os.environ.get("USER", "u")}' / 'pytest-0' / 'old0' / 'cluster-mcp-sandbox.OldRun']
        for path in pre:
            (path / '.config').mkdir(parents=True)
            (path / 'mark').write_text('pre')
        other = lab.pytest('test_hold', wait=False)
        deadline = time.monotonic() + 120
        while not any(r['row'] == 'other-run' for r in lab.rows()):
            if time.monotonic() > deadline or other.poll() is not None:
                fail('guards', f'the other run never made its leftover: {other.stdout.read() if other.poll() is not None else "timeout"}')
                return
            time.sleep(0.1)
        result = lab.pytest('test_group_kill and run or test_live or test_decoys')
        check('guards', result.returncode == 0, 'the planted session ran', f'a planted row failed: {result.stdout[-1500:]}')
        rows = {r['row']: r for r in lab.rows()}
        held = rows['other-run']['paths']
        check('guards', all(Path(p).is_dir() for p in held), "R3: another run's leftover survives this run's sweep",
              f"R3: this run's sweep removed another run's leftover: {held}")
        check('guards', all((p / 'mark').read_text() == 'pre' for p in pre if p.is_dir()) and all(p.is_dir() for p in pre),
              'R3: directories left before the run (TMPDIR, another run directory, an older basetemp) survive',
              f'R3: a directory left before the run was removed or changed: {[str(p) for p in pre if not p.is_dir()]}')
        for row in ('live-wrapper', 'live-command'):
            if row not in rows:
                fail('guards', f'{row} did not run')
                continue
            path = Path(rows[row]['paths'][0])
            check('guards', path.is_dir() and sorted(os.listdir(path)) == rows[row]['listing'],
                  f'R4 {row}: the directory of a sandbox still running is kept, unchanged',
                  f'R4 {row}: the directory of a sandbox still running was removed or changed: {path}')
        if 'decoys' in rows:
            decoys = [Path(p) for p in rows['decoys']['paths']]
            link = decoys[1]
            intact = (decoys[0].is_file() and link.is_symlink() and (lab.gate / 'outside' / 'keep').read_text() == 'keep'
                      and (lab.gate / 'outside' / 'cluster-mcp-sandbox.Insidx').is_dir()
                      and decoys[2].is_dir() and decoys[3].is_file() and decoys[4].is_file())
            check('guards', intact, 'R3: a file, a link and a wrongly named directory with a sandbox-like name, and other files, survive',
                  f'R3: something that is not a sandbox directory was removed: '
                  f'{[str(d) for d in decoys + [lab.gate / "outside" / "cluster-mcp-sandbox.Insidx"] if not os.path.lexists(d)]}')
        else:
            fail('guards', 'the decoy row did not run')
        own = Path(rows['decoys']['run']) if 'decoys' in rows else None
        check('guards', own is not None and own.is_dir(), "R4: a run directory holding a sandbox still in use is kept",
              f"this run's directory {own} was removed with a sandbox in it still in use")
        if 'adhoc' in rows:
            check('guards', all(Path(p).is_dir() for p in rows['adhoc']['paths']),
                  "R3: a leftover another caller made in the same TMPDIR during the run survives",
                  f"R3: this run's sweep removed another caller's leftover made during the run: {rows['adhoc']['paths']}")
        else:
            fail('guards', 'the ad hoc caller row did not run')
        if 'group-kill-run' in rows:
            check('guards', not any(Path(p).exists() for p in rows['group-kill-run']['paths']),
                  "R1: this run's own leftover is still removed beside them", "R1: this run's own leftover was kept")
        (lab.gate / 'release').write_text('go')
        out, _ = other.communicate(timeout=120)
        check('guards', other.returncode == 0 and not any(Path(p).exists() for p in held),
              "R1: the other run's leftover goes when that run ends", f'the other run ended {other.returncode} leaving {held}: {out[-800:]}')
    finally:
        lab.close()


def fresh_import(repo: Path, name: str):
    """`tests/<name>.py` of `repo`, imported anew: an earlier mode's copy of it (or of what it imports) is gone."""
    import importlib
    for module in ('mutants', 'sandbox_dirs'):
        sys.modules.pop(module, None)
    sys.path[:] = [p for p in sys.path if not p.endswith('/repo/tests')]
    sys.path.insert(0, str(repo / 'tests'))
    return importlib.import_module(name)


def import_runner(lab: Lab):
    os.environ.update(lab.env())
    tempfile.tempdir = None
    return fresh_import(lab.repo, 'mutants')


def runner_case(mutants, target: str, repo: bool = False):
    readme = (Path(mutants.TESTS).parent / 'README.md').read_text().splitlines()[0]
    edits = (('README.md', readme, readme + ' '),) if repo else ()
    return mutants.Case(id='sdlk-' + target, file='', edits=(), targets=(f'{PLANT_NAME}::{target}',), why='sdlk',
                        repo_edits=edits)


def mode_runner() -> None:
    lab = Lab()
    try:
        mutants = import_runner(lab)
        for repo in (False, True):
            label = 'a case planting a repository copy' if repo else 'a case on the package'
            violations = mutants.run_case(runner_case(mutants, 'test_die', repo))
            check('runner', bool(violations), f'{label}: the killed child is reported', 'the killed child was reported as caught')
            check('runner', os.environ.get('TMPDIR') == str(lab.tmp), "the runner's own TMPDIR is put back after the case",
                  f"the runner's TMPDIR is {os.environ.get('TMPDIR')} after the case, not {lab.tmp}")
            check('runner', sum(r['row'] == 'child-left' for r in lab.rows()) == 1 + repo,
                  f"{label}: the child's tests made leftovers before it died", 'the child row never ran')
            extra = sandbox_dirs_under(lab.tmp)
            check('runner', not extra, f"R2 {label}: nothing of the killed child's sandboxes is left under TMPDIR",
                  f'R2: sandbox directories left under TMPDIR: {extra}')
            scratch = sorted(lab.tmp.glob('mutant-*'))
            check('runner', not scratch, f"{label}: the case's scratch is removed", f'scratch left: {scratch}')
        mutants.run_case(runner_case(mutants, 'test_orphan'))
        rows = {r['row']: r for r in lab.rows()}
        if 'child-orphan' not in rows:
            fail('runner', 'the orphan row never ran')
        else:
            path = Path(rows['child-orphan']['paths'][0])
            check('runner', path.is_dir() and sorted(os.listdir(path)) == rows['child-orphan']['listing'],
                  'R4: a sandbox the child left running keeps its directory past the case',
                  f'R4: the case removed the directory of a sandbox the child left running: {path}')
            kill_group(rows['child-orphan']['pgid'])
    finally:
        os.environ.clear()
        os.environ.update(SAVED_ENV)
        tempfile.tempdir = None
        lab.close()


def mode_units() -> None:
    top = Path(tempfile.mkdtemp(prefix='sdlk-units-'))
    try:
        repo = REPO or staged_copy(top)
        for given in (True, False):
            env = child_env(TMPDIR=str(top)) if given else {k: v for k, v in child_env().items() if k != 'TMPDIR'}
            run = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests/test_sandbox_dirs.py'],
                                 cwd=repo, env=env, capture_output=True, text=True, timeout=300)
            tail = run.stdout.strip().splitlines()[-1:] or ['']
            how = 'with TMPDIR set' if given else 'with TMPDIR unset, as on CI'
            check('units', run.returncode == 0, f"the suite's own rows for the sweep pass {how}: {tail[0]}",
                  f"a row of tests/test_sandbox_dirs.py failed {how}: {run.stdout[-1500:]}")
    finally:
        shutil.rmtree(top, ignore_errors=True)


def mode_runner_timeout() -> None:
    lab = Lab()
    try:
        mutants = import_runner(lab)
        if not hasattr(mutants, 'LIMIT'):
            fail('runner-timeout', "tests/mutants.py has no LIMIT: mutant-child-outlives-timeout's stop is not on this branch")
            return
        mutants.LIMIT = 8
        violations = mutants.run_case(runner_case(mutants, 'test_hang'))
        check('runner-timeout', any('timeout' in v for v in violations), 'the child past its limit is reported as a timeout',
              f'no timeout reported: {violations}')
        extra = sandbox_dirs_under(lab.tmp)
        check('runner-timeout', not extra, 'R2: nothing of the stopped child\'s sandboxes is left under TMPDIR',
              f'R2: sandbox directories left under TMPDIR: {extra}')
        check('runner-timeout', not sorted(lab.tmp.glob('mutant-*')), "the case's scratch is removed", 'scratch left')
    finally:
        os.environ.clear()
        os.environ.update(SAVED_ENV)
        tempfile.tempdir = None
        lab.close()


def mode_sample() -> None:
    expected = (HERE / 'sample.expected').read_text()
    run = subprocess.run(['uv', 'run', 'python', 'tests/mutants.py', '--self-check', *SAMPLE], cwd=ROOT, env=child_env(),
                         capture_output=True, text=True, timeout=600)
    check('sample', run.stdout == expected and run.returncode == 0,
          f'R6: {len(SAMPLE)} sample cases and the three controls print what develop printed',
          f'R6: the runner printed something else (exit {run.returncode}):\n{run.stdout}\n{run.stderr[-800:]}')


def mode_rebase() -> None:
    have = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--verify', '-q', SIBLING], capture_output=True, text=True)
    other = SIBLING if have.returncode == 0 else 'origin/develop'
    base = subprocess.run(['git', '-C', str(ROOT), 'merge-base', 'HEAD', other], capture_output=True, text=True, check=True).stdout.strip()
    lab = Path(tempfile.mkdtemp(prefix='sdlk-rebase-'))
    try:
        for name, rev in (('base', base), ('theirs', other)):
            (lab / name).write_text(subprocess.run(['git', '-C', str(ROOT), 'show', f'{rev}:tests/mutants.py'],
                                                   capture_output=True, text=True, check=True).stdout)
        ours = subprocess.run(['git', '-C', str(ROOT), 'show', ':tests/mutants.py'], capture_output=True, text=True, check=True).stdout
        results = []
        for first, second in (('ours', 'theirs'), ('theirs', 'ours')):
            (lab / 'ours').write_text(ours)
            shutil.copy(lab / first, lab / 'merged')
            results.append(subprocess.run(['git', 'merge-file', '-q', str(lab / 'merged'), str(lab / 'base'), str(lab / second)]).returncode)
        check('rebase', results == [0, 0], f'tests/mutants.py merges with {other} cleanly in either order',
              f'tests/mutants.py conflicts with {other}: merge-file exits {results}')
    finally:
        shutil.rmtree(lab, ignore_errors=True)


def mode_cost() -> None:
    top = Path(tempfile.mkdtemp(prefix='sdlk-cost-'))
    try:
        sandbox_dirs = fresh_import(REPO or staged_copy(top), 'sandbox_dirs')
        run, base = top / 'run', top / 'base'
        run.mkdir()
        for i in range(200):
            (base / f'test_{i}0' / 'sub').mkdir(parents=True)
            (base / f'test_{i}0' / 'sub' / 'f').write_text('x')
        began = time.monotonic()
        sandbox_dirs.sweep([run, base])
        empty = time.monotonic() - began
        made = []
        for i in range(60):
            path = Path(tempfile.mkdtemp(prefix='cluster-mcp-sandbox.', dir=run))
            path = path.rename(run / f'cluster-mcp-sandbox.{i:06d}') if not SANDBOX_NAME.fullmatch(path.name) else path
            for sub in ('.config', '.cache', '.local/share'):
                (path / sub).mkdir(parents=True)
            made.append(path)
        began = time.monotonic()
        kept = sandbox_dirs.sweep([run, base])
        sixty = time.monotonic() - began
        print(f'cost: sweep with no leftover {empty * 1000:.0f} ms; with 60 leftovers {sixty * 1000:.0f} ms', flush=True)
        check('cost', not kept and not any(p.exists() for p in made), 'the sweep removed all 60', f'kept {kept}')
    finally:
        shutil.rmtree(top, ignore_errors=True)


SUITE = (
    ('legacy', ['tests/test_ssh_exec.py', '-k', 'silent']),
    ('legacy', ['tests/test_ssh_exec.py', '-k', 'not silent']),
    ('legacy', ['tests/test_timeout_stop.py', 'tests/test_startup.py', 'tests/test_launch.py']),
    ('legacy', ['--ignore=tests/test_ssh_exec.py', '--ignore=tests/test_timeout_stop.py', '--ignore=tests/test_startup.py',
                '--ignore=tests/test_launch.py']),
)


# How long the suite mode lets a sandbox still running at a session's end finish by itself.
SETTLE = 30


def mode_suite() -> None:
    top = Path(tempfile.mkdtemp(prefix='sdlk-suite-'))
    skipped: set[str] = set()
    try:
        for era in ('legacy', 'modern'):
            for i, (_, args) in enumerate(SUITE, 1):
                junit = top / f'{era}-{i}.xml'
                env = child_env(TMPDIR=str(top))
                if era == 'modern':
                    env['CLUSTER_MCP_TEST_ERA'] = 'modern'
                shared = set(Path('/tmp').glob(PATTERN))
                began = time.monotonic()
                run = subprocess.run(['uv', 'run', 'pytest', '-q', f'--junitxml={junit}', *args], cwd=ROOT, env=env,
                                     capture_output=True, text=True)
                dropped = sorted(set(Path('/tmp').glob(PATTERN)) - shared)
                check('suite', not dropped, f'R1: {era} command {i} made no sandbox directory in /tmp (no launch dropped TMPDIR)',
                      f'R1: {era} command {i}: new sandbox directories in /tmp, a launch that dropped TMPDIR '
                      f'(or another caller on this host): {dropped[:5]}')
                tail = run.stdout.strip().splitlines()[-1:] or ['']
                check('suite', run.returncode == 0, f'{era} command {i} passed in {time.monotonic() - began:.0f} s: {tail[0]}',
                      f'{era} command {i} exited {run.returncode}: {run.stdout[-1500:]}')
                # A sandbox still running when the session ends keeps its directory (R4) and removes it
                # itself when its command ends (test_launch's split-end-record row leaves `sleep 8`).
                settled = time.monotonic()
                left = sandbox_dirs_under(top)
                while left and time.monotonic() - settled < SETTLE:
                    time.sleep(0.5)
                    left = sandbox_dirs_under(top)
                waited = f' (after {time.monotonic() - settled:.0f} s for running sandboxes to end)' if time.monotonic() - settled > 1 else ''
                check('suite', not left, f'R1: {era} command {i} left no sandbox directory{waited}',
                      f'R1: {era} command {i} left {len(left)} after {SETTLE} s: {left[:5]}')
                for path in left:
                    shutil.rmtree(path, ignore_errors=True)
                text = junit.read_text() if junit.exists() else ''
                for match in re.finditer(r'<testcase classname="([^"]*)" name="([^"]*)"[^>]*>\s*<skipped', text):
                    skipped.add(f'{era} {match.group(1)}::{match.group(2)}')
        last = subprocess.run(['bin/sandbox.sh', 'uv', 'run', 'cluster-mcp', '--help'], cwd=ROOT, env=child_env(TMPDIR=str(top)),
                              capture_output=True, text=True)
        check('suite', last.returncode == 0 and not sandbox_dirs_under(top), "verify's last command passed and left nothing",
              f'the last command exited {last.returncode}')
        expected = set((HERE / 'develop-skips.txt').read_text().splitlines()) - {''}
        check('suite', skipped == expected, f'R6: the {len(skipped)} tests skipped are the ones develop skips',
              f'R6: skips differ from develop: new {sorted(skipped - expected)[:10]}, gone {sorted(expected - skipped)[:10]}')
        runs = sorted(top.glob('cluster-mcp-run.*'))
        print(f'suite: run directories left (not sandbox directories) {len(runs)}: '
              f'{[sorted(os.listdir(r))[:5] for r in runs][:5]}', flush=True)
    finally:
        shutil.rmtree(top, ignore_errors=True)


def mode_mutants() -> None:
    listing = Path(os.environ.get('SDLK_MUTANTS', HERE / 'mutants.json'))
    if not listing.exists():
        fail('mutants', f'no plant list: {listing} (the last phase writes it)')
        return
    plants = json.loads(listing.read_text())
    covered = {p['decision'] for p in plants}
    missing = [d for d in DECISIONS if d not in covered]
    check('mutants', not missing, f'every decision of PLAN § 6 has a plant ({len(plants)} plants)', f'decisions with no plant: {missing}')
    for plant in plants:
        top = Path(tempfile.mkdtemp(prefix='sdlk-mutant-'))
        try:
            repo = staged_copy(top)
            path = repo / plant['file']
            text = path.read_text()
            if text.count(plant['old']) != 1:
                fail('mutants', f'{plant["id"]}: its anchor occurs {text.count(plant["old"])} times in {plant["file"]}')
                continue
            path.write_text(text.replace(plant['old'], plant['new']))
            argv = [sys.executable, '-I', str(Path(__file__).resolve()), '--repo', str(repo), plant['mode']]
            run = subprocess.run(argv, cwd=ROOT, env=child_env(), capture_output=True, text=True, timeout=600)
            killed = run.returncode == 1 and any(plant['why'] in line for line in run.stdout.splitlines() if line.startswith('FAIL'))
            check('mutants', killed, f'{plant["id"]} ({plant["decision"]}) killed by {plant["mode"]}',
                  f'{plant["id"]} ({plant["decision"]}) survived {plant["mode"]} (exit {run.returncode}): '
                  f'{[l for l in run.stdout.splitlines() if l.startswith("FAIL")][:3]}')
        finally:
            shutil.rmtree(top, ignore_errors=True)


DEFERRAL = re.compile(r'do not fix here|known limitation|left as a follow-up|follow-up cycle|deferred to', re.I)


def mode_ledger() -> None:
    tech = (ROOT / 'spec' / SLUG / 'TECH.md').read_text()
    body = tech.split('\n---\n', 1)[1]
    roadmap = (ROOT / 'ROADMAP.md').read_text()
    found = 0
    for line in body.splitlines():
        if line.lstrip().startswith('#') or not DEFERRAL.search(line):
            continue
        found += 1
        seeds = re.findall(r'issues/([a-z0-9-]+)\.md', line)
        good = bool(seeds) and all((ROOT / 'issues' / f'{s}.md').exists() and f'issues/{s}.md' in roadmap for s in seeds)
        check('ledger', good, f'deferral names its seed and roadmap entry: {line.strip()[:80]}',
              f'deferral with no seed or roadmap entry: {line.strip()[:120]}')
    ok('ledger', f'{found} deferral lines walked')


MODES = {'files': mode_files, 'units': mode_units, 'kinds': mode_kinds, 'guards': mode_guards, 'runner': mode_runner,
         'runner-timeout': mode_runner_timeout, 'sample': mode_sample, 'rebase': mode_rebase, 'cost': mode_cost,
         'suite': mode_suite, 'mutants': mode_mutants, 'ledger': mode_ledger}


def main(argv: list[str]) -> int:
    global REPO
    if argv[:1] == ['--repo']:
        REPO, argv = Path(argv[1]), argv[2:]
    unknown = [m for m in argv if m not in MODES]
    if not argv or unknown:
        print(f'usage: cleanup.py [--repo DIR] MODE…  (modes: {", ".join(MODES)}); unknown: {unknown}')
        return 2
    for mode in argv:
        MODES[mode]()
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
