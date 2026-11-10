"""R5's load protocol on macOS: each timing row 20 runs alone, then 20 under four CPU spinners beside a full suite.

Run from the worktree root, on the cycle's final tree (staged and committed; the tree is read from the index):

    UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/load-protocol.py run     # ~20 min: background it
    UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/load-protocol.py check

`run` writes `verify/load-runs.txt`: one line per run (row, alone or loaded, era, verdict, seconds,
the 1-minute load average, whether the beside suite was running) and a summary. Runs alternate eras
(odd runs the handshake era, even runs the modern one). A row is each of its tests in one pytest
process: rows 1 and 2 one test, row 3 its 56 RAISED parameters, row 4 its 192 parameters.

The load is four CPU spinners (`python -c 'while True: pass'`, each its own session, marked by a token
in its argv) and the profile's suite commands run in order beside the loaded runs, cycling to the next
era's when one era ends, so every loaded run has a suite beside it. The suite is never killed: once
the rows are done, `run` waits for the suite command in flight to end, then kills each spinner's
process group and asserts none is left. The beside suite's exit statuses are recorded, not graded
(its own rows may break under the extra load: `issues/loopback-ssh-breaks-under-load.md`).

`check` passes when every protocol run recorded on the staged `tests/` tree (the record is appended,
never overwritten) is a macOS run in which every row passed 20 of 20 alone and 20 of 20 loaded, each
loaded run with one suite command beside the whole of it and the spinners up, and no run failed.

Footprint: 4 spinners (4 cores), the beside suite (one pytest and its sandboxed children, about
1 GB), one row pytest at a time; about 8 processes.
"""

from __future__ import annotations

import os
import platform
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

SLUG = 'stalled-reconnect-test-timing'
RECORD = Path('spec') / SLUG / 'verify' / 'load-runs.txt'
RUNS = 20
SPINNERS = 4
SSH = 'tests/test_ssh_exec.py'
RAISED = ('none', 'a-str', 'stdout-none', 'exception', 'exception-over-lines', 'os-error', 'unprintable', 'exit-0',
          'exit-3', 'exit-text', 'exit-none', 'base-exception', 'interrupt', 'thread-cannot-start')
ROWS = {
    1: [f'{SSH}::test_a_stalled_reconnect_is_abandoned_against_a_real_handshake'],
    2: [f'{SSH}::test_a_reconnect_worker_that_cannot_start_frees_the_attempt'],
    3: [f'tests/test_probes.py::test_every_ending_without_an_answer_serves_the_capability[{e}-{n}]'
        for e in RAISED for n in ('core-only', 'slurm', 'rcac', 'both')],
    4: ['tests/test_probe_startup.py::test_every_ending_without_an_answer_serves_every_capability'],
}
COUNTS = {1: 1, 2: 1, 3: 56, 4: 192}
IGNORED = ('--ignore=tests/test_ssh_exec.py', '--ignore=tests/test_timeout_stop.py', '--ignore=tests/test_startup.py',
           '--ignore=tests/test_launch.py')
# The profile's suite commands, one era's four in order (AGENTS.md § Factory, `verify`).
SUITE = (['pytest', '-q', SSH, '-k', 'silent'], ['pytest', '-q', SSH, '-k', 'not silent'],
         ['pytest', '-q', 'tests/test_timeout_stop.py', 'tests/test_startup.py', 'tests/test_launch.py'],
         ['pytest', '-q', *IGNORED])
ERAS = ({}, {'CLUSTER_MCP_TEST_ERA': 'modern'})


def era_of(i: int) -> dict[str, str]:
    return ERAS[(i + 1) % 2]


def one_run(row: int, env: dict[str, str]) -> tuple[bool, float, str]:
    began = time.monotonic()
    out = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *ROWS[row]],
                         env={**os.environ, **env}, capture_output=True, text=True, timeout=540)
    took = time.monotonic() - began
    tail = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else ''
    passed = out.returncode == 0 and re.search(rf'\b{COUNTS[row]} passed\b', tail) is not None \
        and not re.search(r'failed|error|skipped', tail)
    if not passed:
        tail += ' | ' + ' | '.join(l for l in out.stdout.splitlines() if l.startswith('E ') or 'FAILED' in l)[:600]
    return passed, took, tail


class Beside:
    """The profile's suite commands, cycling eras, run one at a time in their own session."""

    def __init__(self) -> None:
        self.index = 0
        self.child: subprocess.Popen | None = None
        self.log: list[str] = []
        self._next()

    def _next(self) -> None:
        era = ERAS[(self.index // len(SUITE)) % 2]
        argv = [sys.executable, '-m', *SUITE[self.index % len(SUITE)]]
        self.current = (' '.join(f'{k}={v}' for k, v in era.items()) + ' ' + ' '.join(argv[2:])).strip()
        self.began = time.monotonic()
        self.child = subprocess.Popen(argv, env={**os.environ, **era}, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL, start_new_session=True)
        self.index += 1

    def running(self) -> int | None:
        """The index of the suite command running now, or None; one that has ended is logged and the next
        started, so a run that spans two commands reads two indices."""
        if self.child.poll() is not None:
            self.log.append(f'beside: {self.current} · exit {self.child.returncode} · '
                            f'{time.monotonic() - self.began:.0f} s')
            self._next()
        return self.index if self.child.poll() is None else None

    def finish(self) -> None:
        self.child.wait()
        self.log.append(f'beside: {self.current} · exit {self.child.returncode} · {time.monotonic() - self.began:.0f} s')


def spinners(token: str) -> list[subprocess.Popen]:
    return [subprocess.Popen([sys.executable, '-I', '-c', f'# {token}\nwhile True: pass'], start_new_session=True)
            for _ in range(SPINNERS)]


def stop(procs: list[subprocess.Popen]) -> list[str]:
    for proc in procs:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
    left = []
    for proc in procs:
        try:
            os.killpg(proc.pid, 0)
            left.append(proc.pid)
        except ProcessLookupError:
            pass
    return [f'spinner group {pid} still has a process' for pid in left]


def tests_tree() -> str:
    tree = subprocess.run(['git', 'write-tree'], check=True, capture_output=True, text=True).stdout.strip()
    return subprocess.run(['git', 'rev-parse', f'{tree}:tests'], check=True, capture_output=True, text=True).stdout.strip()


def run() -> int:
    lines = [f'# R5 load protocol · {time.strftime("%Y-%m-%d %H:%M")} · macOS {platform.mac_ver()[0]} · '
             f'{os.cpu_count()} cores · HEAD {subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()} '
             f'· tests tree {tests_tree()}']
    for row in ROWS:
        for i in range(1, RUNS + 1):
            env = era_of(i)
            ok, took, tail = one_run(row, env)
            lines.append(f'row {row} · alone · run {i} · {env.get("CLUSTER_MCP_TEST_ERA", "handshake")} · '
                         f'{"pass" if ok else "FAIL"} · {took:.1f} s · load {os.getloadavg()[0]:.1f} · {tail}')
    token = f'srtt-spin-{uuid.uuid4().hex[:8]}'
    spun = spinners(token)
    beside = Beside()
    problems: list[str] = []
    try:
        time.sleep(5)
        for row in ROWS:
            # A run counts only when one suite command ran beside the whole of it; a run across a
            # command's end is recorded (a failure there is still a failure) and made again.
            i = attempts = 0
            while i < RUNS and attempts < 2 * RUNS:
                attempts += 1
                env = era_of(i + 1)
                before = beside.running()
                ok, took, tail = one_run(row, env)
                whole = before is not None and beside.child.poll() is None and beside.running() == before
                up = all(p.poll() is None for p in spun)
                i += 1 if whole and up else 0
                lines.append(f'row {row} · loaded · run {i if whole and up else "x"} · '
                             f'{env.get("CLUSTER_MCP_TEST_ERA", "handshake")} · {"pass" if ok else "FAIL"} · '
                             f'{took:.1f} s · load {os.getloadavg()[0]:.1f} · suite {"yes" if whole else "partly"} · '
                             f'spinners {"up" if up else "down"} · {tail}')
        beside.finish()
    finally:
        problems += stop(spun)
    lines += beside.log
    for row in ROWS:
        for kind in ('alone', 'loaded'):
            got = [l for l in lines if l.startswith(f'row {row} · {kind} ·')]
            good = [l for l in got if ' · pass · ' in l and (kind == 'alone' or (' · suite yes · ' in l and
                                                                                 ' · spinners up · ' in l))]
            lines.append(f'summary · row {row} · {kind} · {len(good)} of {RUNS}')
    lines += [f'problem · {p}' for p in problems]
    # Appended, never overwritten: every run on a tree stays on the record (`check` grades them all).
    with RECORD.open('a', encoding='utf-8') as handle:
        handle.write('\n'.join(lines) + '\n')
    print('\n'.join(l for l in lines if l.startswith(('summary', 'problem', 'beside'))))
    return 1 if problems else 0


def check() -> int:
    if not RECORD.exists():
        print(f'{RECORD}: missing')
        return 1
    text = RECORD.read_text(encoding='utf-8')
    # Every protocol run on this tree, each a section from its header line.
    sections = [s for s in re.split(r'(?m)^(?=# R5 load protocol)', text) if s.startswith('# R5')]
    mine = [s for s in sections if f'tests tree {tests_tree()}' in s.splitlines()[0]]
    problems = [] if mine else [f'{RECORD}: no run on the staged tests tree {tests_tree()}']
    for section in mine:
        lines = section.splitlines()
        if ' · macOS ' not in lines[0] or ' · macOS  ·' in lines[0]:
            problems.append(f'{lines[0]}: not a macOS run')
        problems += [f'a failed run: {l[:160]}' for l in lines if ' · FAIL · ' in l]
        problems += [l for l in lines if l.startswith('problem')]
        for row in ROWS:
            alone = [l for l in lines if l.startswith(f'row {row} · alone · run ') and ' · pass · ' in l]
            loaded = [l for l in lines if l.startswith(f'row {row} · loaded · run ') and ' · pass · ' in l
                      and ' · suite yes · ' in l and ' · spinners up · ' in l and ' · run x · ' not in l]
            if len(alone) < RUNS or len(loaded) < RUNS:
                problems.append(f'{lines[0][:60]}: row {row} {len(alone)} alone and {len(loaded)} loaded of {RUNS}')
    print('\n'.join(problems) or f'load protocol: every row {RUNS} of {RUNS} alone and loaded on this tests tree')
    return 1 if problems else 0


if __name__ == '__main__':
    # `run --runs N` is a planning dry run of the mechanics only: `check` still wants RUNS of RUNS.
    if sys.argv[1] == 'run' and sys.argv[2:4] and sys.argv[2] == '--runs':
        RUNS = int(sys.argv[3])
    sys.exit({'run': run, 'check': check}[sys.argv[1]]())
