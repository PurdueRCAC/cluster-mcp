# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The suite half of the planted-violation runner (`mutants.py`): unit rows, and one integration row.

`test_mutation_anchor_applies[<case>]` goes red the moment a change moves the code a planted
violation edits: the contract that case pins has moved, and the case must be re-planted against the
new code before its targets can be trusted again. The `mutation_violations` controls prove the
runner cannot count a child as a kill unless every target failed for the case's stated reason.

The rows after them pin the stop a child run past its limit gets: each decision of `run_members`,
`_wait_gone`, `stop_run`, `run_child`, `child_timeout_violations`, `_processes` and the runner's
signal handling as a unit row on fakes, a stop whose `ps` fails included, and the whole stop as one
integration row that hangs a real child under `bin/sandbox.sh` at a patched limit and checks every
process of the run is gone, and nothing outside it touched, when the case is reported.

Their stand-ins: `Fakes` records every process call the stop makes and answers its `ps` looks from
tables (`RUN` with `OWN`, `RUN_PIDS` and `RUN_GROUPS`, `INIT_TABLE`, `runner_group_table`), `Pipe`
records a pipe's close, and `FakePopen` (installed with `LIMIT` = 7 by the `fake_popen` fixture)
stands in for the child; `failing_stop` runs the real `stop_run` on fakes whose look fails. `KILL`,
`STOP`, `HELD_SIGNALS`, `GONE_WITHIN` and `GONE_POLL` are the signals and figures the rows expect,
stated here rather than imported. The integration row's child is `HANG_TEST`, starting `SLEEPER`s
directly and through `SPAWNER`; `RECORDED` names the processes it writes down, `recorded_pids` reads
them, and `process_state` checks each independently of the runner.
"""

from __future__ import annotations

import ast
import functools
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

import mutants
from mutants import (CASES, CHILD, LIMIT, MEMBERS, REPO_FILES, SANDBOX, SURVIVOR_CONTROL, Case,
                     ChildTimeout, RunnerSignal, apply, apply_repo, child_timeout_violations, die_by, mutation_violations,
                     run_child, run_members, stop_on_signals, stop_run)

TARGETS = ['test_isolation.py::test_a', 'test_isolation.py::test_b']
WHY = 'ran as'


def junit(*cases: tuple[str, str, str]) -> str:
    """A pytest-shaped JUnit report holding (name, child tag or '', message) testcases."""
    body = ''.join(
        f'<testcase classname="tests.test_isolation" name="{name}">'
        + (f'<{tag} message="{message}">{message}</{tag}>' if tag else '')
        + '</testcase>'
        for name, tag, message in cases)
    return f'<testsuites><testsuite name="pytest">{body}</testsuite></testsuites>'


KILLED = junit(('test_a', 'failure', 'AssertionError: echo A ran as ubob, expected ualice'),
               ('test_b', 'failure', 'AssertionError: echo B ran as ualice, expected ubob'))


@pytest.mark.unit
@pytest.mark.parametrize('case', CASES, ids=[c.id for c in CASES])
def test_mutation_anchor_applies(case: Case, tmp_path: Path) -> None:
    src_root = apply(case, tmp_path)
    if case.file:
        mutated = src_root / 'cluster_mcp' / case.file
        compile(mutated.read_text(), str(mutated), 'exec')
    repo = apply_repo(case, tmp_path)
    if repo is not None:
        root = Path(__file__).resolve().parents[1]
        changed = [name for name in REPO_FILES if (repo / name).read_text() != (root / name).read_text()]
        assert changed == sorted({name for name, _, _ in case.repo_edits}), changed
    assert case.targets and case.why and (case.edits or case.repo_edits)


@pytest.mark.unit
def test_mutation_case_files_name_a_member(tmp_path: Path) -> None:
    # A case file is relative to the namespace, its member first, so it names the same file in the
    # copy and in any install; the copy holds every member and, like each member, no __init__.py.
    # A case planting only into repository files has no file, and plants only into `REPO_FILES`.
    repo_only = [c for c in CASES if not c.file and not c.edits and c.repo_edits]
    strays = [f'{c.id}: {c.file}' for c in (*CASES, SURVIVOR_CONTROL)
              if c.file.split('/')[0] not in MEMBERS and c not in repo_only]
    strays += [f'{c.id}: {name}' for c in CASES for name, _, _ in c.repo_edits if name not in REPO_FILES]
    assert strays == [], strays
    assert sorted(MEMBERS) == ['core', 'rcac', 'slurm']
    namespace = apply(SURVIVOR_CONTROL, tmp_path) / 'cluster_mcp'
    assert sorted(p.name for p in namespace.iterdir()) == ['core', 'rcac', 'slurm']
    assert not (namespace / '__init__.py').exists()
    partial = apply(SURVIVOR_CONTROL, tmp_path / 'partial', omit='rcac') / 'cluster_mcp'
    assert sorted(p.name for p in partial.iterdir()) == ['core', 'slurm']


@pytest.mark.unit
def test_mutation_check_accepts_a_clean_kill() -> None:
    assert mutation_violations(1, KILLED, TARGETS, WHY) == []


@pytest.mark.unit
@pytest.mark.parametrize(('returncode', 'report', 'fragment'), [
    pytest.param(0, junit(('test_a', '', ''), ('test_b', '', '')), 'survived', id='all-passed'),
    pytest.param(1, junit(('test_a', 'failure', 'ran as ubob'), ('test_b', '', '')),
                 'test_b: passed', id='target-passed'),
    pytest.param(2, junit(('test_a', 'error', 'collection failure'), ('test_b', 'error', 'collection failure')),
                 'exited 2', id='collection-error'),
    pytest.param(4, None, 'exited 4', id='usage-error'),
    pytest.param(1, junit(('test_a', 'failure', 'ran as ubob')), 'test_b: missing', id='target-missing'),
    pytest.param(97, None, 'wrong import origin', id='wrong-origin'),
    pytest.param(1, junit(('test_a', 'failure', "NameError: name 'FastMCPx' is not defined"),
                          ('test_b', 'failure', 'ran as ualice')),
                 'test_a: killed for the wrong reason', id='wrong-reason'),
    pytest.param(1, junit(('test_a', 'error', 'ran as ubob'), ('test_b', 'failure', 'ran as ualice')),
                 'test_a: error, not a failure', id='error-not-failure'),
    pytest.param(1, junit(('test_a', 'error', 'failed on teardown'), ('test_b', 'failure', 'ran as ualice')),
                 'test_a: error, not a failure', id='teardown-error-only'),
])
def test_mutation_check_flags_survivors(returncode: int, report: str | None, fragment: str) -> None:
    violations = mutation_violations(returncode, report, TARGETS, WHY)
    assert any(fragment in v for v in violations), violations



# --- A child run past its limit -----------------------------------------------------------------

# A run as a process table sees it: the runner (10), the bin/sandbox.sh wrapper leading the run's
# group (100), the child pytest (101), a grandchild in a group of its own (102), an orphan left in the
# wrapper's group (103), a grandchild in a session of its own (104), an orphan left in that
# session's group (105), a child of that orphan in a group of its own (50, a lower number than its
# parent, so only a second pass over the table finds it), and an orphan of nothing in the run (200).
RUN: dict[int, tuple[int, int, str]] = {
    10: (1, 10, 'S'), 100: (10, 100, 'S'), 101: (100, 100, 'S'), 102: (101, 102, 'S'), 103: (1, 100, 'S'),
    104: (101, 104, 'Ss'), 105: (1, 104, 'S'), 50: (105, 50, 'S'), 200: (1, 200, 'S')}
OWN = (10, 10)
RUN_PIDS, RUN_GROUPS = {100, 101, 102, 103, 104, 105, 50}, {100, 102, 104, 50}

# Init (1) and the kernel (0) put in reach of the run, and a child of the pytest in group 1 with an
# orphan beside it: neither number, as a pid or a group, may join the run, or a signal to it would
# go to `kill(0)`, `killpg(0)` or init.
INIT_TABLE: dict[int, tuple[int, int, str]] = {
    0: (0, 100, 'Ss'), 1: (100, 0, 'Ss'), 100: (10, 100, 'S'), 101: (100, 100, 'S'), 106: (101, 1, 'S'),
    107: (1, 1, 'S')}


def runner_group_table() -> tuple[dict[int, tuple[int, int, str]], set[int], set[int]]:
    """The wrapper in the test's own process group, the test's pid placed as the child's child, and a sibling in that group."""
    me, group = os.getpid(), os.getpgrp()
    table = {me: (101, group, 'S'), 100: (me, group, 'S'), 101: (100, group, 'S'), 300: (1, group, 'S')}
    return table, {100, 101}, {100}


@pytest.mark.unit
@pytest.mark.parametrize(('present', 'absent'), [
    pytest.param({101}, set(), id='child'),
    pytest.param({102}, set(), id='grandchild'),
    pytest.param({103}, set(), id='orphan-in-the-group'),
    pytest.param({104, 105}, set(), id='new-session-group'),
    pytest.param({50}, set(), id='found-later-in-the-table'),
    pytest.param(set(), {200, 10, 1}, id='unrelated-orphan'),
    pytest.param(set(), set(), id='runner-group'),
    pytest.param(set(), set(), id='never-init-or-kernel'),
])
def test_run_members_follow_parents_and_groups(present: set[int], absent: set[int], request: pytest.FixtureRequest) -> None:
    if request.node.callspec.id == 'runner-group':
        table, pids, groups = runner_group_table()
        # The runner's own group is never kept, even when handed in as known.
        found, known = run_members(table, [100], [100, os.getpgrp()])
        assert (set(found), set(known)) == (pids, groups)
        assert os.getpid() not in found and os.getpgrp() not in known
        return
    if request.node.callspec.id == 'never-init-or-kernel':
        found, known = run_members(INIT_TABLE, [100], [100], OWN)
        assert (set(found), set(known)) == ({100, 101, 106}, {100}), (found, known)
        return
    found, known = run_members(RUN, [100], [100], OWN)
    assert present <= set(found) and not absent & set(found), found
    assert (set(found), set(known)) == (RUN_PIDS, RUN_GROUPS), (found, known)


class Fakes:
    """Recorded stand-ins for every process call the stop makes; `tables` are what each `ps` look returns."""

    def __init__(self, tables: list[Any], pid: int = 100) -> None:
        self.tables = list(tables)
        self.calls: list[tuple[Any, ...]] = []
        self.now = 0.0
        self.pid = pid
        self.stdout, self.stderr = Pipe(self.calls, 'stdout'), Pipe(self.calls, 'stderr')

    def processes(self) -> dict[int, tuple[int, int, str]]:
        self.calls.append(('table',))
        table = self.tables.pop(0) if len(self.tables) > 1 else self.tables[0]
        if isinstance(table, BaseException):
            raise table
        return dict(table)

    def kill(self, pid: int, signum: int) -> None:
        self.calls.append(('kill', pid, signum))

    def killpg(self, group: int, signum: int) -> None:
        self.calls.append(('killpg', group, signum))
        if group == self.pid and signum == signal.SIGSTOP and getattr(self, 'wrapper_gone', False):
            raise ProcessLookupError(group)

    def mask(self, how: int, signals: Any) -> None:
        self.calls.append(('mask', how, frozenset(signals)))

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.calls.append(('sleep', seconds))
        self.now += seconds

    def wait(self) -> int:
        self.calls.append(('wait',))
        return -9

    def gone(self, pids: list[int], groups: list[int]) -> list[int]:
        return mutants._wait_gone(pids, groups, processes=self.processes, kill=self.kill, clock=self.clock,
                                  sleep=self.sleep, own=OWN)

    def stop(self) -> list[int]:
        return stop_run(self, processes=self.processes, kill=self.kill, killpg=self.killpg,  # type: ignore[arg-type]
                        mask=self.mask, clock=self.clock, sleep=self.sleep)


class Pipe:
    def __init__(self, calls: list[tuple[Any, ...]], name: str) -> None:
        self.calls, self.name = calls, name

    def close(self) -> None:
        self.calls.append(('close', self.name))


KILL, STOP = signal.SIGKILL, signal.SIGSTOP
# The stop's figures as the maintainer approved them, stated here so a changed constant shows in the rows
# that use them, not only in `test_the_stop_figures`.
GONE_WITHIN, GONE_POLL = 10, 0.1
HELD_SIGNALS = frozenset({signal.SIGINT, signal.SIGTERM, signal.SIGHUP})


@pytest.mark.unit
@pytest.mark.parametrize(('tables', 'pids', 'groups', 'left', 'kills', 'sleeps'), [
    pytest.param([{}], [101], [100], [], [], 0, id='gone-at-once'),
    pytest.param([{101: (100, 100, 'Z+')}], [101], [100], [], [], 0, id='zombie-is-gone'),
    pytest.param([{101: (100, 100, 'S')}, {101: (100, 100, 'R')}, {}], [101], [100], [], [101, 101], 2,
                 id='gone-after-polls'),
    pytest.param([{101: (1, 100, 'S')}, {101: (1, 100, 'Z'), 102: (1, 100, 'S'), 103: (101, 300, 'S')}, {}],
                 [101], [100], [], [101, 102, 103], 2, id='new-member-in-a-group'),
    pytest.param([{101: (1, 100, 'S'), 102: (1, 100, 'S')}, {101: (1, 100, 'S')}, {101: (1, 100, 'S'), 102: (1, 100, 'S')}],
                 [101, 102], [100], [101], None, None, id='still-running'),
    # 102 and 104 end, and 104's group with it; then 102's number comes back with a child (106), and
    # a process (107) carries 104's group number: neither is the run's, so neither is signalled.
    pytest.param([{101: (1, 100, 'S'), 102: (1, 100, 'S'), 104: (1, 104, 'S')}, {101: (1, 100, 'S')},
                  {101: (1, 100, 'S'), 102: (1, 100, 'S'), 106: (102, 600, 'S'), 107: (1, 104, 'S')}, {}],
                 [101, 102, 104], [100, 104], [], [101, 102, 104, 101, 101], 3, id='gone-numbers-never-followed'),
    # The deadline counts from the first look, not from the clock's zero: with the clock far from zero,
    # a member still running at the first look is killed and looked for again.
    pytest.param([{101: (100, 100, 'S')}, {}], [101], [100], [], [101], 1, id='clock-not-at-zero'),
])
def test_gone_waits_until_every_process_ends(tables: list[Any], pids: list[int], groups: list[int], left: list[int],
                                             kills: list[int] | None, sleeps: int | None,
                                             request: pytest.FixtureRequest) -> None:
    fakes = Fakes(tables)
    if request.node.callspec.id == 'clock-not-at-zero':
        fakes.now = 5000.0
    assert fakes.gone(pids, groups) == left
    killed = [c[1] for c in fakes.calls if c[0] == 'kill']
    assert all(c[2] == KILL for c in fakes.calls if c[0] == 'kill')
    slept = [c[1] for c in fakes.calls if c[0] == 'sleep']
    assert all(s == GONE_POLL for s in slept), slept
    if kills is not None:
        assert (killed, len(slept)) == (kills, sleeps), fakes.calls
        return
    # Still running: looked every GONE_POLL until GONE_WITHIN had passed, and 102, once absent, never
    # signalled again although a later table shows that number in a group of the run.
    assert GONE_WITHIN <= fakes.now < GONE_WITHIN + 2 * GONE_POLL, fakes.now
    assert killed.count(102) == 1 and killed.count(101) == len(slept), killed


@pytest.mark.unit
def test_stop_run_freezes_then_kills_the_whole_run() -> None:
    first = {100: (10, 100, 'S'), 101: (100, 100, 'T'), 104: (101, 104, 'Ts')}
    second = {**first, 105: (1, 104, 'T')}
    fakes = Fakes([first, second, second, {100: (10, 100, 'Z')}])
    assert fakes.stop() == []
    assert fakes.calls == [
        ('mask', signal.SIG_BLOCK, HELD_SIGNALS),
        ('killpg', 100, STOP),
        ('table',), ('kill', 101, STOP), ('killpg', 104, STOP), ('kill', 104, STOP),
        ('table',), ('kill', 105, STOP),
        ('table',),
        ('kill', 105, KILL), ('kill', 104, KILL), ('killpg', 104, KILL), ('kill', 101, KILL), ('killpg', 100, KILL),
        ('table',),
        ('wait',),
        ('mask', signal.SIG_UNBLOCK, HELD_SIGNALS),
    ]


@pytest.mark.unit
def test_stop_run_waits_for_every_process_it_found() -> None:
    # After the kill, the orphan 105 is still running; its parent is gone and its group's leader too,
    # so only the stop's own record of it (and of group 104) links it to the run.
    first = {100: (10, 100, 'S'), 101: (100, 100, 'T'), 104: (101, 104, 'Ts'), 105: (1, 104, 'T')}
    fakes = Fakes([first, first, {100: (10, 100, 'Z'), 105: (1, 104, 'S')}, {100: (10, 100, 'Z')}])
    assert fakes.stop() == []
    confirm = fakes.calls[fakes.calls.index(('killpg', 100, KILL)) + 1:]
    assert confirm == [('table',), ('kill', 105, KILL), ('sleep', GONE_POLL), ('table',), ('wait',),
                       ('mask', signal.SIG_UNBLOCK, HELD_SIGNALS)], confirm


@pytest.mark.unit
@pytest.mark.parametrize('cut', ['table-fails', 'wrapper-gone'])
def test_stop_run_kills_what_it_found_when_it_is_cut_short(cut: str) -> None:
    if cut == 'table-fails':
        fakes = Fakes([{101: (100, 100, 'T')}, RuntimeError('ps failed')])
        with pytest.raises(RuntimeError, match='ps failed'):
            fakes.stop()
        assert fakes.calls == [
            ('mask', signal.SIG_BLOCK, HELD_SIGNALS), ('killpg', 100, STOP),
            ('table',), ('kill', 101, STOP), ('table',),
            ('kill', 101, KILL), ('killpg', 100, KILL), ('wait',), ('mask', signal.SIG_UNBLOCK, HELD_SIGNALS)]
        return
    fakes = Fakes([{}])
    fakes.wrapper_gone = True  # type: ignore[attr-defined]
    assert fakes.stop() == []
    assert fakes.calls == [
        ('mask', signal.SIG_BLOCK, HELD_SIGNALS), ('killpg', 100, STOP), ('table',), ('killpg', 100, KILL),
        ('table',), ('wait',), ('mask', signal.SIG_UNBLOCK, HELD_SIGNALS)]


@pytest.mark.unit
def test_the_stop_figures() -> None:
    assert (LIMIT, mutants.GONE_WITHIN, mutants.GONE_POLL) == (300, GONE_WITHIN, GONE_POLL)


@pytest.mark.unit
@pytest.mark.parametrize(('exc', 'violations'), [
    pytest.param(ChildTimeout(8, []), ['timeout: the child ran past its 8 s limit and was stopped'], id='gone'),
    pytest.param(ChildTimeout(300, [4242, 4343]), ['timeout: the child ran past its 300 s limit and was stopped',
                                                   'still running 10 s after the stop: pids 4242, 4343'], id='left'),
    # A stop that could not look never says the run was stopped, and names what may be left.
    pytest.param(ChildTimeout(8, [], 'BlockingIOError: [Errno 35] Resource temporarily unavailable'),
                 ['timeout: the child ran past its 8 s limit',
                  "the stop could not finish (BlockingIOError: [Errno 35] Resource temporarily unavailable): it killed "
                  "the wrapper's process group and every process it had found, and others of the run may still be "
                  'running'], id='unfinished'),
])
def test_a_timeout_reason_names_the_limit(exc: ChildTimeout, violations: list[str]) -> None:
    assert child_timeout_violations(exc) == violations


class FakePopen:
    """A stand-in for `subprocess.Popen` that records how the child was started; `first` is what communicate does once."""

    made: list[FakePopen] = []
    first: Any = None
    # What each next instance's communicate does, in turn, before `first` applies.
    plan: list[Any] = []

    def __init__(self, args: list[str], **kwargs: Any) -> None:
        self.args, self.kwargs, self.pid, self.returncode = args, kwargs, 4100, None
        self.calls: list[tuple[Any, ...]] = []
        self.stdout, self.stderr = Pipe(self.calls, 'stdout'), Pipe(self.calls, 'stderr')
        self.raises = FakePopen.plan.pop(0) if FakePopen.plan else FakePopen.first
        FakePopen.made.append(self)

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        self.calls.append(('communicate', timeout))
        if self.raises is not None:
            raise self.raises
        self.returncode = 3
        return 'out', 'err'

    def wait(self) -> int:
        self.calls.append(('wait',))
        return -9


@pytest.fixture
def fake_popen(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Patch in `FakePopen`, `LIMIT` = 7, and a recording `stop_run` that reports pid 4242 still running."""
    stops: list[tuple[Any, ...]] = []
    FakePopen.made, FakePopen.first, FakePopen.plan = [], None, []
    monkeypatch.setattr(subprocess, 'Popen', FakePopen)
    monkeypatch.setattr(mutants, 'LIMIT', 7)

    def recorded(proc: FakePopen) -> list[int]:
        stops.append(('stop_run', proc))
        proc.calls.append(('stop_run',))
        return [4242]
    monkeypatch.setattr(mutants, 'stop_run', recorded)
    return stops


@pytest.mark.unit
def test_run_child_returns_what_the_child_returned(fake_popen: list[tuple[Any, ...]], tmp_path: Path) -> None:
    src, junit, repo = tmp_path / 'src', tmp_path / 'junit.xml', tmp_path / 'repo'
    got = run_child(src, ['test_x.py::test_y'], junit, repo)
    proc, = FakePopen.made
    argv = [str(SANDBOX), 'sh', '-c', CHILD, 'sh', sys.executable, str(src), str(junit), str(repo), 'tests/test_x.py::test_y']
    assert proc.args == argv
    env = proc.kwargs.pop('env')
    assert (env['PYTHONPATH'], env['PYTHONDONTWRITEBYTECODE']) == (str(src), '1')
    assert proc.kwargs == {'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE, 'text': True, 'start_new_session': True}
    assert proc.calls == [('communicate', 7)]
    assert isinstance(got, subprocess.CompletedProcess)
    assert (got.args, got.returncode, got.stdout, got.stderr) == (argv, 3, 'out', 'err')
    assert fake_popen == []


@pytest.mark.unit
@pytest.mark.parametrize('exit_', ['timeout', 'interrupt', 'signal'])
def test_run_child_stops_the_run_on_every_early_exit(exit_: str, fake_popen: list[tuple[Any, ...]], tmp_path: Path) -> None:
    raised = {'timeout': subprocess.TimeoutExpired('sh', 7), 'interrupt': KeyboardInterrupt(),
              'signal': RunnerSignal(signal.SIGTERM)}[exit_]
    FakePopen.first = raised
    expected: type[BaseException] = ChildTimeout if exit_ == 'timeout' else type(raised)
    with pytest.raises(expected) as caught:
        run_child(tmp_path / 'src', ['test_x.py::test_y'], tmp_path / 'junit.xml')
    proc, = FakePopen.made
    assert proc.calls == [('communicate', 7), ('stop_run',), ('close', 'stdout'), ('close', 'stderr')]
    assert len(fake_popen) == 1
    if exit_ == 'timeout':
        assert (caught.value.limit, caught.value.left) == (7, [4242])  # type: ignore[attr-defined]
    elif exit_ == 'signal':
        assert caught.value.signum == signal.SIGTERM  # type: ignore[attr-defined]


def failing_stop(tables: list[Any]) -> tuple[Fakes, Any]:
    """The real `stop_run` on fakes whose `ps` looks return `tables` in turn (an exception in it is raised)."""
    fakes = Fakes(tables, pid=4100)
    return fakes, functools.partial(stop_run, processes=fakes.processes, kill=fakes.kill, killpg=fakes.killpg,
                                    mask=fakes.mask, clock=fakes.clock, sleep=fakes.sleep)


@pytest.mark.unit
@pytest.mark.parametrize('cut', ['ps-cannot-start', 'ps-fails-mid-walk', 'interrupt-during-stop'])
def test_run_child_reports_a_stop_that_could_not_finish(cut: str, fake_popen: list[tuple[Any, ...]], tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    FakePopen.first = subprocess.TimeoutExpired('sh', 7)
    if cut == 'ps-cannot-start':
        fakes, stop = failing_stop([BlockingIOError(35, 'Resource temporarily unavailable')])
        cause, killed = 'BlockingIOError: [Errno 35] Resource temporarily unavailable', [('killpg', 4100, KILL)]
    elif cut == 'ps-fails-mid-walk':
        fakes, stop = failing_stop([{4101: (4100, 4100, 'T'), 4104: (4101, 4104, 'Ts')},
                                    subprocess.CalledProcessError(1, ['ps'])])
        cause = "CalledProcessError: Command '['ps']' returned non-zero exit status 1."
        killed = [('kill', 4104, KILL), ('killpg', 4104, KILL), ('kill', 4101, KILL), ('killpg', 4100, KILL)]
    else:
        # A Ctrl-C or a signal to the runner is not a failed look: it goes on, and ends the sweep.
        fakes, stop = failing_stop([KeyboardInterrupt()])
        cause, killed = None, [('killpg', 4100, KILL)]
    monkeypatch.setattr(mutants, 'stop_run', stop)
    with pytest.raises(ChildTimeout if cause else KeyboardInterrupt) as caught:
        run_child(tmp_path / 'src', ['test_x.py::test_y'], tmp_path / 'junit.xml')
    # Whatever cut the look short, the stop killed the wrapper's group and everything it had found.
    assert [c for c in fakes.calls if c[0] in ('kill', 'killpg') and c[2] == KILL] == killed, fakes.calls
    proc, = FakePopen.made
    assert proc.calls == [('communicate', 7), ('wait',), ('close', 'stdout'), ('close', 'stderr')] or cause is None
    if cause:
        assert (caught.value.limit, caught.value.left, caught.value.unfinished) == (7, [], cause)  # type: ignore[attr-defined]


@pytest.mark.unit
def test_a_stop_that_could_not_finish_is_reported_and_the_sweep_goes_on(fake_popen: list[tuple[Any, ...]],
                                                                         monkeypatch: pytest.MonkeyPatch,
                                                                         capsys: pytest.CaptureFixture[str]) -> None:
    FakePopen.plan = [subprocess.TimeoutExpired('sh', 7)]
    fakes, stop = failing_stop([BlockingIOError(35, 'Resource temporarily unavailable')])
    monkeypatch.setattr(mutants, 'stop_run', stop)
    control = SURVIVOR_CONTROL
    monkeypatch.setattr(mutants, 'CASES', (Case('hang', control.file, control.edits, ('test_x.py::test_y',), 'hung'),
                                           Case('next', control.file, control.edits, ('test_x.py::test_y',), 'why')))
    assert mutants.main(['hang', 'next']) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == ('FAILED  hang: timeout: the child ran past its 7 s limit; the stop could not finish '
                        "(BlockingIOError: [Errno 35] Resource temporarily unavailable): it killed the wrapper's "
                        'process group and every process it had found, and others of the run may still be running')
    assert len(lines) == 2 and lines[1].startswith('FAILED  next: '), lines
    assert len(FakePopen.made) == 2


@pytest.mark.unit
def test_a_failed_ps_is_an_error_not_an_empty_table(monkeypatch: pytest.MonkeyPatch) -> None:
    runs: list[tuple[Any, ...]] = []
    answers = [(0, '  12     1    12 Ss\n  13    12    12 S+\n'), (1, '')]

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        runs.append((argv, kwargs))
        code, out = answers.pop(0)
        if kwargs.get('check') and code:
            raise subprocess.CalledProcessError(code, argv)
        return subprocess.CompletedProcess(argv, code, out, '')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    assert mutants._processes() == {12: (1, 12, 'Ss'), 13: (12, 12, 'S+')}
    with pytest.raises(subprocess.CalledProcessError):
        mutants._processes()
    assert runs[0][0] == [str(SANDBOX), 'ps', '-A', '-o', 'pid=,ppid=,pgid=,stat=']


@pytest.mark.unit
@pytest.mark.parametrize('signum', [signal.SIGTERM, signal.SIGHUP], ids=['term', 'hup'])
def test_a_runner_signal_exits_through_the_stop(signum: int, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, ...]] = []
    installed: dict[int, Any] = {}

    def record_signal(sig: int, handler: Any) -> None:
        calls.append(('signal', sig, handler))
        installed[sig] = handler
    monkeypatch.setattr(signal, 'signal', record_signal)
    monkeypatch.setattr(os, 'kill', lambda pid, sig: calls.append(('kill', pid, sig)))
    stop_on_signals()
    assert sorted(installed) == sorted([signal.SIGTERM, signal.SIGHUP])
    with pytest.raises(RunnerSignal) as caught:
        installed[signum](signum, None)
    assert caught.value.signum == signum
    calls.clear()
    with pytest.raises(SystemExit):
        die_by(signum)
    assert calls == [('signal', signum, signal.SIG_DFL), ('kill', os.getpid(), signum)]


@pytest.mark.unit
def test_the_script_installs_the_signal_stop() -> None:
    tree = ast.parse(Path(mutants.__file__).read_text())
    block = tree.body[-1]
    assert isinstance(block, ast.If) and ast.unparse(block.test) == "__name__ == '__main__'"
    texts = [ast.unparse(statement) for statement in block.body]
    assert texts[0] == 'stop_on_signals()', texts
    tried, = [s for s in block.body if isinstance(s, ast.Try)]
    assert block.body.index(tried) > 0 and [ast.unparse(s) for s in tried.body] == ['sys.exit(main())']
    handler, = tried.handlers
    assert ast.unparse(handler.type) == 'RunnerSignal'
    assert any(isinstance(n, ast.Call) and ast.unparse(n.func) == 'die_by' for n in ast.walk(handler))


# The child run the integration row hangs: the pytest starts a child in its own group, a child in a
# session of its own, and an orphan left in its group (its spawner, which outlives the orphan's start,
# gone) that then starts a child in a session of its own, reachable only through the orphan's group.
# Each is a sleeper that writes `pid ppid pgrp sid spawner` once in place; then the pytest records
# itself and its PYTHONPATH, writes a ready file, and sleeps past any limit the row sets.
SLEEPER = """\
import os, subprocess, sys, time
spawner = int(sys.argv[3])
end = time.monotonic() + 20
while os.getppid() == spawner and time.monotonic() < end:
    time.sleep(0.01)
if len(sys.argv) > 4:
    subprocess.Popen([sys.executable, '-c', sys.argv[5], sys.argv[4], sys.argv[2], '0'], start_new_session=True)
with open(sys.argv[1] + '.part', 'w') as out:
    out.write(f'{os.getpid()} {os.getppid()} {os.getpgrp()} {os.getsid(0)} {spawner}')
os.replace(sys.argv[1] + '.part', sys.argv[1])
time.sleep(60)
"""
SPAWNER = """\
import os, subprocess, sys, time
subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2], sys.argv[3], str(os.getpid()), sys.argv[4], sys.argv[1]])
time.sleep(0.3)
"""
HANG_TEST = """\
import os, subprocess, sys, time
from pathlib import Path

OUT = Path(@OUT@)
SLEEPER = @SLEEPER@
SPAWNER = @SPAWNER@


def test_hang():
    py = sys.executable
    subprocess.Popen([py, '-c', SLEEPER, str(OUT / 'child'), 'mutant-hang-child', '0'])
    subprocess.Popen([py, '-c', SLEEPER, str(OUT / 'session'), 'mutant-hang-session', '0'], start_new_session=True)
    subprocess.Popen([py, '-c', SPAWNER, SLEEPER, str(OUT / 'orphan'), 'mutant-hang-orphan', str(OUT / 'orphan-session')]).wait()
    end = time.monotonic() + 30
    while not all((OUT / name).exists() for name in ('child', 'session', 'orphan', 'orphan-session')):
        assert time.monotonic() < end, 'the sleepers never wrote'
        time.sleep(0.01)
    (OUT / 'pytest').write_text(f'{os.getpid()} {os.getppid()} {os.getpgrp()} {os.getsid(0)}')
    (OUT / 'pythonpath').write_text(os.environ.get('PYTHONPATH', ''))
    (OUT / 'ready').write_text('')
    time.sleep(60)
"""
RECORDED = ('pytest', 'wrapper', 'child', 'session', 'orphan', 'orphan-session')


def process_state(pid: int) -> str:
    """'gone' for a process that has ended (absent, or a zombie), else its `ps` state letters."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return 'gone'
    except PermissionError:
        return 'not ours'
    stat = subprocess.run([str(SANDBOX), 'ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True).stdout.strip()
    return 'gone' if not stat or stat.startswith('Z') else stat


def recorded_pids(out: Path) -> dict[str, int]:
    """The run's processes the hang child wrote down, by role; the wrapper is the pytest's parent."""
    pids: dict[str, int] = {}
    for name in ('pytest', 'child', 'session', 'orphan', 'orphan-session', 'sentinel-group', 'sentinel-session'):
        if (out / name).exists():
            pids[name] = int((out / name).read_text().split()[0])
    if (out / 'pytest').exists():
        pids['wrapper'] = int((out / 'pytest').read_text().split()[1])
    return pids


@pytest.mark.integration
def test_a_child_past_its_limit_is_stopped_whole_and_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                              capsys: pytest.CaptureFixture[str]) -> None:
    repo, out, scratch, tmp = tmp_path / 'repo', tmp_path / 'out', tmp_path / 'scratch', tmp_path / 'tmp'
    for directory in (repo / 'tests', out, scratch, tmp):
        directory.mkdir(parents=True)
    (repo / 'pytest.ini').write_text('[pytest]\n')
    (repo / 'tests' / 'test_hang.py').write_text(
        HANG_TEST.replace('@OUT@', repr(str(out))).replace('@SLEEPER@', repr(SLEEPER)).replace('@SPAWNER@', repr(SPAWNER)))
    (repo / 'tests' / 'test_quick.py').write_text("def test_quick():\n    assert False, 'planted'\n")
    # The sandbox homes the killed wrappers leave go with tmp_path, not into the host's temporary directory.
    monkeypatch.setenv('TMPDIR', str(tmp))
    monkeypatch.setattr(tempfile, 'tempdir', str(scratch))
    monkeypatch.setattr(mutants, 'LIMIT', 8)
    monkeypatch.setattr(mutants, 'TESTS', repo / 'tests')
    control = SURVIVOR_CONTROL
    monkeypatch.setattr(mutants, 'CASES', (
        Case('hang', control.file, control.edits, ('test_hang.py::test_hang',), 'hung'),
        Case('quick', control.file, control.edits, ('test_quick.py::test_quick',), 'planted')))
    sentinels = [
        subprocess.Popen([str(SANDBOX), sys.executable, '-c', SLEEPER, str(out / 'sentinel-group'), 'mutant-hang-sentinel', '0']),
        subprocess.Popen([str(SANDBOX), sys.executable, '-c', SLEEPER, str(out / 'sentinel-session'), 'mutant-hang-sentinel', '0'],
                         start_new_session=True)]
    seen: dict[str, Any] = {}
    real = mutants.run_case

    def watched(case: Case, *args: Any, **kwargs: Any) -> list[str]:
        start = time.monotonic()
        result = real(case, *args, **kwargs)
        if case.id == 'hang':
            seen['took'] = time.monotonic() - start
            seen['ready'] = (out / 'ready').exists()
            pids = recorded_pids(out)
            seen['run'] = {name: process_state(pids[name]) for name in RECORDED if name in pids}
            seen['sentinels'] = [process_state(p.pid) for p in sentinels] + [
                process_state(pids[name]) for name in ('sentinel-group', 'sentinel-session') if name in pids]
            seen['scratch'] = sorted(p.name for p in scratch.iterdir())
        return result
    monkeypatch.setattr(mutants, 'run_case', watched)
    try:
        end = time.monotonic() + 30
        while not ((out / 'sentinel-group').exists() and (out / 'sentinel-session').exists()):
            assert time.monotonic() < end, 'the sentinels never started'
            time.sleep(0.01)
        code = mutants.main(['hang', 'quick'])
        printed = capsys.readouterr().out
        assert seen.get('ready'), f'the child never got ready: {seen}'
        rec = {name: tuple(int(f) for f in (out / name).read_text().split()) for name in RECORDED if name != 'wrapper'}
        pytest_pid, wrapper = rec['pytest'][:2]
        layout = {'pytest in the wrapper group': rec['pytest'][2] == wrapper,
                  'child in the wrapper group': rec['child'][2] == wrapper,
                  'orphan parent neither the pytest nor its spawner': rec['orphan'][1] not in (pytest_pid, rec['orphan'][4]),
                  'orphan in the wrapper group': rec['orphan'][2] == wrapper,
                  'session child leads its own group and session': rec['session'][0] == rec['session'][2] == rec['session'][3],
                  "orphan's child is its own and leads a session": (rec['orphan-session'][1] == rec['orphan'][0]
                                                                    and rec['orphan-session'][0] == rec['orphan-session'][2]
                                                                    == rec['orphan-session'][3])}
        assert all(layout.values()), f'layout not as planned: {layout}'
        pythonpath = os.path.realpath((out / 'pythonpath').read_text())
        assert pythonpath.startswith(os.path.realpath(scratch) + os.sep), pythonpath
        assert seen['run'] == {name: 'gone' for name in RECORDED}, seen
        assert seen['scratch'] == [], seen
        assert seen['took'] < mutants.LIMIT + 5, seen
        assert len(seen['sentinels']) == 4 and all(s not in ('gone', 'not ours') and 'T' not in s for s in seen['sentinels']), seen
        assert printed == ('FAILED  hang: timeout: the child ran past its 8 s limit and was stopped\n'
                           "killed  quick: test_quick.py::test_quick failed with 'planted'\n"), printed
        assert code == 1
    finally:
        pids = recorded_pids(out)
        for pid in [*pids.values(), *(p.pid for p in sentinels)]:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        for sentinel in sentinels:
            try:
                sentinel.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        end = time.monotonic() + 2
        for pid in pids.values():
            while time.monotonic() < end:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.02)
