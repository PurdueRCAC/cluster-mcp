# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The capability probe: one bounded lookup of every declared command decides each capability.

`cluster_mcp.core.probes.start` looks up every command the given capabilities declare, each once, in
load order, with one call of the registered fixed script `LOOKUP` through the executor it is given,
and gives that call the bound. `Pending.verdicts()` decides each capability once, by the deadline at
the latest: a capability whose commands the answer all finds is served, one with a command it does
not find is withheld naming exactly those, and one that declares none is served with nothing to
report. Every other ending (each exit code, each malformed answer, each thing an executor can return
instead of a result or raise, a worker thread that cannot start, a lookup that hangs) serves every
capability that declares a command, with the reason, and decides it at once unless it is a hang.
The deadline is taken when the probe starts: `verdicts()` first asked for after it has passed decides
at once, and one asked for before an answer that comes within it waits for that answer. Nothing is
looked up when nothing is declared. The outcome rows run against `harness.ProbeExecutor`,
beside each member set (the core alone, each member, both), each with two capabilities made here
beside the members: one that declares a command a member also declares and one of its own, and one
that declares none.

The lookup itself runs through the real executors: through the login bash (`LocalShellExecutor`,
fenced by `executes`) it finds a stub file on PATH and counts as missing a name with no file, an
exported function of that name, a file that is not executable, and anything an exported function
named `type` claims; over the loopback SSH server it finds stand-ins in `~/bin`, and a connection
lost mid-command is no answer.
"""

from __future__ import annotations

import threading
import time
import types
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import pytest

from harness import ProbeExecutor
from cluster_mcp.core import probes
from cluster_mcp.core.capabilities import Capability, Loaded, installed
from cluster_mcp.core.executor.base import (CONNECTION_LOST_EXIT_CODE, NOT_STARTED_EXIT_CODE, TIMEOUT_EXIT_CODE,
                                            CommandResult)
from cluster_mcp.core.executor.shell import LocalShellExecutor
from cluster_mcp.core.scripts import script_of
from cluster_mcp.core.site import READ_TIMEOUT
from ssh_server import DroppingSSH, LoopbackSSH

# The member sets every outcome row runs beside: the core alone, each member alone, and both.
MEMBER_SETS = [
    pytest.param((), id='core-only'),
    pytest.param(('slurm',), id='slurm'),
    pytest.param(('rcac',), id='rcac'),
    pytest.param(('rcac', 'slurm'), id='both'),
]

# The bound the outcome rows give a probe, and how far past it the verdicts may come.
BOUND = 0.3
SLACK = 0.5

# The worker thread's name, by which a row finds the threads a probe started.
WORKER = 'cluster-mcp-probe'


def made(name: str, commands: tuple[str, ...]) -> Loaded:
    """A loaded capability made here, declaring `commands`; nothing serves it, so its tools module is a name."""
    capability = Capability(name=name, order=500, tools=f'{name}.tools', instructions='-', commands=commands)
    return Loaded(capability, f'probe-{name}', ())


# Beside the members: one that shares `sinfo` with the Slurm member and declares one of its own, and
# one that declares none.
EXTRA = made('probe_extra', ('sinfo', 'probe_only'))
QUIET = made('probe_quiet', ())


def members(names: tuple[str, ...]) -> tuple[Loaded, ...]:
    """The installed members named in `names`, in load order."""
    return tuple(c for c in installed() if c.capability.name in names)


def capability_set(names: tuple[str, ...]) -> tuple[Loaded, ...]:
    """The members named in `names`, then the two made here."""
    return (*members(names), EXTRA, QUIET)


def declared(capabilities: tuple[Loaded, ...]) -> list[str]:
    """Every command `capabilities` declare, each once, in load order."""
    return list(dict.fromkeys(n for c in capabilities for n in c.capability.commands))


def shape(verdicts: Any) -> list[tuple[str, bool, str | None]]:
    """Each verdict as `(distribution, served, reason)`."""
    return [(v.loaded.distribution, v.served, v.reason) for v in verdicts]


def expected(capabilities: tuple[Loaded, ...], present: set[str]) -> list[tuple[str, bool, str | None]]:
    """The verdicts an answer finding exactly `present` decides."""
    out = []
    for c in capabilities:
        missing = [n for n in c.capability.commands if n not in present]
        out.append((c.distribution, not missing, f'missing {", ".join(missing)}' if missing else None))
    return out


def unanswered(capabilities: tuple[Loaded, ...], reason: str) -> list[tuple[str, bool, str | None]]:
    """The verdicts of no answer for `reason`: every capability served, those that declare a command with it."""
    return [(c.distribution, True, reason if c.capability.commands else None) for c in capabilities]


def started(why: str, executor: Any, capabilities: tuple[Loaded, ...], timeout: float | None = BOUND) -> probes.Pending:
    """`probes.start(...)`, or a failure carrying `why` when it raises or exits."""
    try:
        return probes.start(executor, capabilities, timeout=timeout)
    except BaseException as exc:
        pytest.fail(f'{why}: start() raised {type(exc).__name__}: {exc}', pytrace=False)


def decided(why: str, pending: probes.Pending) -> list[tuple[str, bool, str | None]]:
    """The shape of `pending.verdicts()`, or a failure carrying `why` when it raises or is no tuple."""
    try:
        verdicts = pending.verdicts()
    except BaseException as exc:
        pytest.fail(f'{why}: verdicts() raised {type(exc).__name__}: {exc}', pytrace=False)
    if not isinstance(verdicts, tuple):
        pytest.fail(f'{why}: verdicts() returned {verdicts!r}, not a tuple', pytrace=False)
    return shape(verdicts)


def answering(present: set[str]) -> Callable[[ProbeExecutor, list[str]], CommandResult]:
    """A responder answering each name it is sent: found when it is in `present`."""
    return lambda executor, names: ProbeExecutor.answer(n in present for n in names)


def probe_threads() -> set[threading.Thread]:
    """The live threads named as a probe's worker."""
    return {t for t in threading.enumerate() if t.name == WORKER}


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_nothing_declared_runs_nothing(names: tuple[str, ...]) -> None:
    why = 'nothing was declared, yet the probe ran or reported'
    # The members as they would be had they declared nothing, and the quiet capability.
    quiet = (*(replace(c, capability=replace(c.capability, commands=())) for c in members(names)), QUIET)
    executor = ProbeExecutor(answering(set()))
    before = probe_threads()
    got = decided(why, started(why, executor, quiet))
    assert executor.calls == [], f'{why}: the executor was called: {executor.calls}'
    assert probe_threads() - before == set(), f'{why}: a worker thread was started'
    assert got == [(c.distribution, True, None) for c in quiet], f'{why}: {got}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_every_declared_command_is_looked_up_once(names: tuple[str, ...]) -> None:
    why = 'the lookup was not one call of every declared command'
    # A third capability made here shares a name with the extra one and one with the Slurm member.
    capabilities = (*capability_set(names), made('probe_double', ('probe_only', 'sbatch')))
    want = declared(capabilities)
    executor = ProbeExecutor(answering(set(want)))
    got = decided(why, started(why, executor, capabilities))
    assert len(executor.calls) == 1, f'{why}: {len(executor.calls)} calls'
    argv, timeout = executor.calls[0]
    assert script_of(argv) == probes.LOOKUP, f'{why}: the call does not run the registered lookup: {argv!r:.200}'
    assert ProbeExecutor.names_of(argv) == want, f'{why}: it looked up {ProbeExecutor.names_of(argv)}, not {want}'
    assert timeout == BOUND, f'{why}: the call was given the timeout {timeout!r}, not the bound {BOUND}'
    assert got == expected(capabilities, set(want)), f'{why}: {got}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_capability_is_withheld_when_one_of_its_commands_is_absent(names: tuple[str, ...]) -> None:
    why = 'the verdict does not follow the answer'
    capabilities = capability_set(names)
    every = declared(capabilities)
    answers = [set(every), set(), {every[0]}, set(every[1:]), *(set(every) - {n} for n in every)]
    for present in answers:
        executor = ProbeExecutor(answering(present))
        got = decided(why, started(why, executor, capabilities))
        want = expected(capabilities, present)
        assert got == want, f'{why}: found {sorted(present)}: {got}, expected {want}'


class Odd(BaseException):
    """Neither an Exception nor an exit."""


class Unprintable(Exception):
    """An exception whose text cannot be had."""

    def __str__(self) -> str:
        raise SystemExit('its text exits')


def raising(exc: BaseException) -> Callable[[ProbeExecutor, list[str]], Any]:
    def respond(executor: ProbeExecutor, names: list[str]) -> Any:
        raise exc
    return respond


def result(stdout: str, code: int = 0) -> Callable[[ProbeExecutor, list[str]], CommandResult]:
    return lambda executor, names: CommandResult(stdout=stdout, stderr='', exit_code=code, hostname='probe.invalid')


def found(names: list[str], tail: str | None = None, code: int = 0) -> CommandResult:
    """Every name found, then `end <count>` or `tail`."""
    return ProbeExecutor.answer((True for _ in names), code=code, tail=tail)


UNPARSED = 'gave an answer that does not parse'

# Each ending with no definite answer: the responder, and the reason every probing capability is
# served with (`thread-cannot-start` has no responder: its worker thread never starts).
ENDINGS: dict[str, tuple[Callable[[ProbeExecutor, list[str]], Any] | None, str]] = {
    'timeout-code': (lambda e, ns: found(ns, code=TIMEOUT_EXIT_CODE), f'did not answer within {BOUND:g} s'),
    'connection-lost-code': (lambda e, ns: found(ns, code=CONNECTION_LOST_EXIT_CODE), 'lost the connection'),
    'not-started-code': (lambda e, ns: found(ns, code=NOT_STARTED_EXIT_CODE), 'could not run: the command did not start'),
    'exit-1': (lambda e, ns: found(ns, code=1), 'could not run: it exited 1'),
    'exit-255': (result('', 255), 'could not run: it exited 255'),
    'signal-9': (result('', -9), 'could not run: it exited -9'),
    'empty': (result(''), UNPARSED),
    'no-end': (lambda e, ns: found(ns, tail=''), UNPARSED),
    'wrong-end': (lambda e, ns: found(ns, tail=f'end {len(ns) + 1}\n'), UNPARSED),
    'end-first': (lambda e, ns: CommandResult(f'end {len(ns)}\n' + '1\n' * len(ns), '', 0, 'probe.invalid'), UNPARSED),
    'end-without-newline': (lambda e, ns: found(ns, tail=f'end {len(ns)}'), UNPARSED),
    'end-ended-by-cr': (lambda e, ns: found(ns, tail=f'end {len(ns)}\r'), UNPARSED),
    'crlf': (lambda e, ns: CommandResult('1\r\n' * len(ns) + f'end {len(ns)}\r\n', '', 0, 'probe.invalid'), UNPARSED),
    'one-short': (lambda e, ns: CommandResult('1\n' * (len(ns) - 1) + f'end {len(ns)}\n', '', 0, 'probe.invalid'),
                  UNPARSED),
    'one-long': (lambda e, ns: CommandResult('1\n' * (len(ns) + 1) + f'end {len(ns)}\n', '', 0, 'probe.invalid'),
                 UNPARSED),
    'a-2': (lambda e, ns: CommandResult('2\n' + '1\n' * (len(ns) - 1) + f'end {len(ns)}\n', '', 0, 'probe.invalid'),
            UNPARSED),
    'a-name-echoed': (lambda e, ns: CommandResult(f'{ns[0]}\n' + '1\n' * (len(ns) - 1) + f'end {len(ns)}\n', '', 0,
                                                  'probe.invalid'), UNPARSED),
    'a-blank-line': (lambda e, ns: CommandResult('\n' + '1\n' * (len(ns) - 1) + f'end {len(ns)}\n', '', 0,
                                                 'probe.invalid'), UNPARSED),
    'none': (lambda e, ns: None, "could not run: AttributeError: 'NoneType' object has no attribute 'exit_code'"),
    'a-str': (lambda e, ns: 'end 0\n', "could not run: AttributeError: 'str' object has no attribute 'exit_code'"),
    'stdout-none': (result(None), "could not run: AttributeError: 'NoneType' object has no attribute 'endswith'"),
    'exception': (raising(RuntimeError('probe failure')), 'could not run: RuntimeError: probe failure'),
    'exception-over-lines': (raising(RuntimeError('probe\nfailure  here')), 'could not run: RuntimeError: probe failure here'),
    'os-error': (raising(OSError('probe failure')), 'could not run: OSError: probe failure'),
    'unprintable': (raising(Unprintable()), 'could not run: Unprintable'),
    'exit-0': (raising(SystemExit(0)), 'could not run: SystemExit: 0'),
    'exit-3': (raising(SystemExit(3)), 'could not run: SystemExit: 3'),
    'exit-text': (raising(SystemExit('probe failure')), 'could not run: SystemExit: probe failure'),
    'exit-none': (raising(SystemExit()), 'could not run: SystemExit'),
    'base-exception': (raising(Odd()), 'could not run: Odd'),
    'interrupt': (raising(KeyboardInterrupt()), 'could not run: KeyboardInterrupt'),
    'thread-cannot-start': (None, "could not run: RuntimeError: can't start new thread"),
}

# The endings decided when they happen, never by the deadline: those raised in the worker or at its start.
RAISED = ('none', 'a-str', 'stdout-none', 'exception', 'exception-over-lines', 'os-error', 'unprintable', 'exit-0',
          'exit-3', 'exit-text', 'exit-none', 'base-exception', 'interrupt', 'thread-cannot-start')


def threading_whose_start_raises(exc: BaseException) -> types.ModuleType:
    """A stand-in for the `threading` module whose `Thread.start` raises `exc`, the rest as it is."""
    class Unstartable(threading.Thread):
        def start(self) -> None:
            raise exc

    proxy = types.ModuleType('threading')
    proxy.__dict__.update(threading.__dict__)
    proxy.Thread = Unstartable  # type: ignore[attr-defined]
    return proxy


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('ending', list(ENDINGS))
def test_every_ending_without_an_answer_serves_the_capability(ending: str, names: tuple[str, ...],
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    why = 'an ending without an answer did not serve the capability with its reason'
    capabilities = capability_set(names)
    respond, reason = ENDINGS[ending]
    if respond is None:
        monkeypatch.setattr(probes, 'threading', threading_whose_start_raises(RuntimeError("can't start new thread")))
        respond = answering(set())
    executor = ProbeExecutor(respond)
    began = time.monotonic()
    pending = started(why, executor, capabilities)
    got = decided(why, pending)
    took = time.monotonic() - began
    assert got == unanswered(capabilities, reason), f'{why}: {ending}: {got}'
    assert took <= BOUND + SLACK, f'{why}: {ending}: the verdicts took {took:.2f} s'
    if ending in RAISED:
        assert took < BOUND / 2, f'{why}: {ending}: decided only at the deadline ({took:.2f} s), not when it happened'
    assert len(executor.calls) == (0 if ending == 'thread-cannot-start' else 1), f'{why}: {ending}: {executor.calls}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_an_interrupt_while_the_probe_starts_still_interrupts(names: tuple[str, ...],
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    # An interrupt is no ending of the probe: it reaches the caller, as anywhere else at startup.
    why = 'an interrupt while the probe started did not interrupt'
    monkeypatch.setattr(probes, 'threading', threading_whose_start_raises(KeyboardInterrupt()))
    executor = ProbeExecutor(answering(set()))
    try:
        pending = probes.start(executor, capability_set(names), timeout=BOUND)
    except KeyboardInterrupt:
        pass
    except BaseException as exc:
        pytest.fail(f'{why}: start() raised {type(exc).__name__}: {exc}', pytrace=False)
    else:
        pytest.fail(f'{why}: start() returned, deciding {shape(pending.verdicts())}', pytrace=False)
    assert executor.calls == [], f'{why}: the executor was called: {executor.calls}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_a_hung_probe_is_abandoned_at_the_bound(names: tuple[str, ...], monkeypatch: pytest.MonkeyPatch) -> None:
    why = 'a hung probe was not abandoned at the bound'
    # The bound is the documented 10 s, and no more than the site read's; this row then shortens it,
    # and the probe reads it when it starts.
    assert probes.PROBE_TIMEOUT == 10.0, f'{why}: PROBE_TIMEOUT is {probes.PROBE_TIMEOUT}, not 10 s'
    assert probes.PROBE_TIMEOUT <= READ_TIMEOUT, f'{why}: PROBE_TIMEOUT is above the site read bound'
    monkeypatch.setattr(probes, 'PROBE_TIMEOUT', BOUND)
    capabilities = capability_set(names)
    executor = ProbeExecutor(ProbeExecutor.hang)
    before = probe_threads()
    try:
        began = time.monotonic()
        pending = started(why, executor, capabilities, timeout=None)
        workers = probe_threads() - before
        got = decided(why, pending)
        took = time.monotonic() - began
        assert workers and all(t.daemon for t in workers), \
            f'{why}: its worker is not a daemon thread, so it would hold the process open: {workers}'
        assert executor.calls and executor.calls[0][1] == BOUND, \
            f'{why}: the lookup was not given the bound {BOUND}: {executor.calls}'
        assert got == unanswered(capabilities, f'did not answer within {BOUND:g} s'), f'{why}: {got}'
        assert took <= BOUND + SLACK, f'{why}: the verdicts took {took:.2f} s'
        assert not executor.returned.is_set(), f'{why}: the hung lookup returned before the release'
    finally:
        executor.release.set()


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_the_verdicts_are_decided_once(names: tuple[str, ...]) -> None:
    why = 'the verdicts changed on a later call'
    capabilities = capability_set(names)
    every = declared(capabilities)
    # A definite answer: every later call gives the same verdicts.
    pending = started(why, ProbeExecutor(answering(set(every[1:]))), capabilities)
    first = decided(why, pending)
    assert first == expected(capabilities, set(every[1:])), f'{why}: the first verdicts are wrong: {first}'
    assert decided(why, pending) == first, f'{why}: a definite answer'
    # An answer that comes only after the deadline changes nothing.
    executor = ProbeExecutor(ProbeExecutor.hang)
    before = probe_threads()
    try:
        pending = started(why, executor, capabilities)
        workers = probe_threads() - before
        first = decided(why, pending)
    finally:
        executor.release.set()
    for worker in workers:
        worker.join(5)
    assert executor.returned.is_set() and not any(w.is_alive() for w in workers), \
        f'{why}: the late answer never came, so the row proves nothing'
    assert first == unanswered(capabilities, f'did not answer within {BOUND:g} s'), f'{why}: {first}'
    assert decided(why, pending) == first, f'{why}: a late answer'


# The deadline the late rows give a probe, how long past it `verdicts()` is first called, and how long a
# call that finds the deadline passed may take; a mutant that waits the bound again from the call takes
# the whole `LATE_BOUND`. A hung lookup is released after `LATE_RELEASE` whatever happens, so a wait
# with no bound still ends.
LATE_BOUND = 0.6
LATE_CALL = 0.7
LATE_SLACK = 0.3
LATE_RELEASE = 3.0
EARLY_ANSWER = 0.2


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_the_deadline_is_taken_when_the_probe_starts(names: tuple[str, ...]) -> None:
    why = 'the deadline was not taken when the probe started'
    capabilities = capability_set(names)
    # `verdicts()` first called after the deadline has passed, the lookup still hung: it decides at once,
    # never waiting the bound again from the call.
    executor = ProbeExecutor(ProbeExecutor.hang)
    release = threading.Timer(LATE_RELEASE, executor.release.set)
    release.start()
    try:
        pending = started(why, executor, capabilities, timeout=LATE_BOUND)
        time.sleep(LATE_CALL)
        began = time.monotonic()
        got = decided(why, pending)
        took = time.monotonic() - began
    finally:
        executor.release.set()
        release.cancel()
    assert got == unanswered(capabilities, f'did not answer within {LATE_BOUND:g} s'), f'{why}: {got}'
    assert took <= LATE_SLACK, f'{why}: called {LATE_CALL} s after a {LATE_BOUND} s bound, verdicts() took {took:.2f} s'
    # Called at once, with the answer coming after the call but before the deadline: it waits for it.
    every = declared(capabilities)

    def slow(executor: ProbeExecutor, looked_up: list[str]) -> CommandResult:
        time.sleep(EARLY_ANSWER)
        return ProbeExecutor.answer(n in every[1:] for n in looked_up)

    pending = started(why, ProbeExecutor(slow), capabilities, timeout=LATE_BOUND)
    got = decided(why, pending)
    assert got == expected(capabilities, set(every[1:])), \
        f'{why}: an answer {EARLY_ANSWER} s into a {LATE_BOUND} s bound was not waited for: {got}'


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_unprobed_serves_every_capability_and_runs_nothing(names: tuple[str, ...]) -> None:
    why = 'an unprobed start probed or withheld'
    capabilities = capability_set(names)
    before = probe_threads()
    got = decided(why, probes.unprobed(capabilities))
    assert got == [(c.distribution, True, None) for c in capabilities], f'{why}: {got}'
    assert probe_threads() - before == set(), f'{why}: a worker thread was started'


# The lookup through the real login bash. Stubs on PATH, put first by the login profile: two files
# that are executable, one that is not; a name the profile defines only as an exported function; and
# an exported function named `type` that claims every name.
STUBS = ('probe_cmd_one', 'probe_cmd_two')
NOT_EXECUTABLE = 'probe_not_exec'
FUNCTION_ONLY = 'probe_fn_only'
LOOKED_UP = (made('probe_present', STUBS), made('probe_missing', ('probe_cmd_one', 'probe_absent')),
             made('probe_function', (FUNCTION_ONLY,)), made('probe_unexecutable', (NOT_EXECUTABLE,)))


def stub_home(home: Path, present: tuple[str, ...], unexecutable: tuple[str, ...] = ()) -> None:
    """Stubs under `home/bin` for `present` (executable) and `unexecutable`, and a login profile putting
    them first on PATH, exporting a function named `FUNCTION_ONLY` and one named `type` that claims
    every name."""
    stubs = home / 'bin'
    stubs.mkdir(parents=True, exist_ok=True)
    for name in (*present, *unexecutable):
        stub = stubs / name
        stub.write_text('#!/bin/sh\nexit 0\n')
        stub.chmod(0o755 if name in present else 0o644)
    profile = home / '.bash_profile'
    profile.write_text((profile.read_text() if profile.exists() else '') + (
        f'PATH="{stubs}:$PATH"\nexport PATH\n'
        f'{FUNCTION_ONLY}() {{ :; }}\nexport -f {FUNCTION_ONLY}\n'
        'type() { printf "1\\n"; return 0; }\nexport -f type\n'))


@pytest.mark.integration
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_the_lookup_finds_only_what_exec_runs(names: tuple[str, ...], executes: Any) -> None:
    why = 'the lookup did not find exactly what exec runs'
    present = members(names)
    stub_home(executes.server_home, (*STUBS, *declared(present)), (NOT_EXECUTABLE,))
    capabilities = (*present, *LOOKED_UP)
    got = decided(why, started(why, LocalShellExecutor(), capabilities, timeout=probes.PROBE_TIMEOUT))
    want = expected(capabilities, {*STUBS, *declared(present)})
    assert got == want, f'{why}: {got}, expected {want}'
    assert want[-3:] == [('probe-probe_missing', False, 'missing probe_absent'),
                         ('probe-probe_function', False, f'missing {FUNCTION_ONLY}'),
                         ('probe-probe_unexecutable', False, f'missing {NOT_EXECUTABLE}')], want


@pytest.mark.integration
@pytest.mark.parametrize('case', ['present', 'absent', 'lost'])
def test_the_lookup_over_ssh(case: str, tmp_path: Path) -> None:
    why = 'the lookup over ssh did not decide as the cluster answered'
    capabilities = (*members(('rcac', 'slurm')), EXTRA, QUIET)
    every = declared(capabilities)
    present = set(every) - ({'myquota', 'probe_only'} if case == 'absent' else set())
    home = (tmp_path / 'ssh-home').resolve()
    home.mkdir()
    stub_home(home, tuple(n for n in every if n in present))
    if case == 'lost':
        server: LoopbackSSH = DroppingSSH(home, '/bin/bash', tmp_path, 'after-the-command')
    else:
        server = LoopbackSSH(home, '/bin/bash', tmp_path)
    with server:
        executor = server.executor()
        try:
            got = decided(why, started(why, executor, capabilities, timeout=probes.PROBE_TIMEOUT))
        finally:
            executor.close()
    want = unanswered(capabilities, 'lost the connection') if case == 'lost' else expected(capabilities, present)
    assert got == want, f'{why}: {case}: {got}, expected {want}'
    if case == 'absent':
        assert ('cluster-mcp-rcac', False, 'missing myquota') in got and \
               ('probe-probe_extra', False, 'missing probe_only') in got, got
