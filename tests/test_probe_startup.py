# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Startup probes the cluster once, in `ssh` and `local` modes, and serves only what it has.

In process (`unit`), `MCPServerApp.main` runs with its shared executor a `harness.ProbeExecutor`, the
site read stubbed, and `create_mcp_server` recording what it is given; every step of the start is
recorded in the order it runs (`ORDER`). Each row runs beside each member set (the core alone, each
member, both), with two capabilities made here beside the members: one that declares a command of its
own, and one that declares none. The suite's override (`CLUSTER_MCP_SKIP_PROBES`, set for every test)
is removed first.

- `local` and `ssh` look every declared command up once, through the executor the middleware shares,
  after the load, the ladder, the executor, the budget, the override's resolution, the site read and
  the budget check against every installed capability, and before the server is built from what the
  probe kept: a capability with a missing command is withheld, with one INFO line naming its
  distribution and each missing command, and every other ending (each code, a malformed answer,
  whatever the executor raises or exits with, a hang past the bound) serves every capability, with one
  WARNING line each for those that declare a command, on every transport. Every line is compared with
  the level its record was logged at. An interrupt while the start waits for the answer still
  interrupts it.
- Over each served set the real server's instructions name exactly the tools it serves.
- `delegate` mode runs no probe and says so in one INFO line, the override set or not; `--skip-probes`,
  or the variable with any non-empty value, `0` included, runs none in `local` and `ssh` modes and says
  so in one INFO line naming which; with both set, the flag wins and the line names it; empty, it
  probes.
- No probe runs before a refusal: a capability that cannot load, a failed connect, `--generate-token`
  and every budget refusal (one too small for every installed capability's text included, whatever
  the probe would answer).

Then the real CLI in `local` mode (`integration`), under `bin/sandbox.sh` with the override removed and
a `.bash_profile` that puts a stub directory first on PATH and logs each login: a withheld member is
missing from what a stdio client lists, with its line on stderr at its level, and every command
present serves everything; a login that ends at once is no answer, and serves every capability; and
both hold with stdin closed and over HTTP. Each drive starts one login. The suite never waits out the
real 10 s bound: `spec/capability-probe/verify/drives.py` does.
"""

from __future__ import annotations

import logging
import os
import re
import signal
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pytest
from cmdkit.app import exit_status

import cluster_mcp.core
import cluster_mcp.core.executor.ssh
from harness import ERA, ProbeExecutor, served_surface, stdio_tools, url_tools
from test_transports import group_alive
from test_cli import CLI, SANDBOX
from cluster_mcp.core import MCPServerApp, probes, site
from cluster_mcp.core.capabilities import Capability, CapabilityLoadError, Loaded, installed
from cluster_mcp.core.executor.base import (CONNECTION_LOST_EXIT_CODE, NOT_STARTED_EXIT_CODE, TIMEOUT_EXIT_CODE,
                                            CommandResult)
from cluster_mcp.core.instructions import CORE_INSTRUCTIONS
from cluster_mcp.core.resources import RESOURCE_REGISTRY
from cluster_mcp.core.server import base_instructions, create_mcp_server
from cluster_mcp.core.site import HEADING
from cluster_mcp.core.tools import CORE_TOOLS

OVERRIDE = 'CLUSTER_MCP_SKIP_PROBES'

# The member sets every row runs beside.
MEMBER_SETS = [
    pytest.param((), id='core-only'),
    pytest.param(('slurm',), id='slurm'),
    pytest.param(('rcac',), id='rcac'),
    pytest.param(('rcac', 'slurm'), id='both'),
]


def made(name: str, commands: tuple[str, ...]) -> Loaded:
    """A loaded capability made here, with no tool, declaring `commands`."""
    text = f'The {name} capability serves no tool.'
    return Loaded(Capability(name=name, order=500, tools=f'{name}.tools', instructions=text, commands=commands),
                  f'planted-{name.replace("_", "-")}', ())


# Beside the members: one that declares a command no host has, and one that declares none.
PLANTED = made('planted_probe', ('planted_probe_command',))
QUIET = made('planted_quiet', ())


def members(names: tuple[str, ...]) -> tuple[Loaded, ...]:
    """The installed members named in `names`, in load order."""
    return tuple(c for c in installed() if c.capability.name in names)


def capability_set(names: tuple[str, ...]) -> tuple[Loaded, ...]:
    """What a start beside `names` loads: those members and the two made here, in load order."""
    return tuple(sorted((*members(names), PLANTED, QUIET), key=lambda c: c.distribution))


def declared(capabilities: tuple[Loaded, ...]) -> list[str]:
    """Every command `capabilities` declare, each once, in load order."""
    return list(dict.fromkeys(n for c in capabilities for n in c.capability.commands))


def answering(absent: set[str]) -> Callable[[ProbeExecutor, list[str]], CommandResult]:
    """A responder finding every name it is sent but those in `absent`."""
    return lambda executor, names: ProbeExecutor.answer(n not in absent for n in names)


# The steps of a start, in the order `run()` takes them, as the spies below record them.
ORDER = ['load', 'ladder', 'executor', 'budget', 'override', 'site', 'check', 'start', 'served', 'serve', 'run']
DELEGATE_ORDER = ['load', 'ladder', 'budget', 'override', 'site', 'check', 'unprobed', 'served', 'serve', 'run']

# The lines a start logs whatever it probes: the mode, the connect and the delegate middleware.
OWN = re.compile(r'(Execution mode: |SSH connection established to |Delegate mode: executor will be created)')

# Each line the probe step logs, as (level, message): a withheld capability and every skip are INFO, a
# capability served without an answer WARNING (AGENTS § Invariants §4).
Line = tuple[str, str]
DELEGATE_LINE: Line = ('INFO', 'Capability probes skipped in delegate mode: every installed capability is served')
SECRET = 'probe-startup-test-secret-0123456789abcdef'
SITE = site.SiteContext.missing('the test')


def skip_line(what: str) -> Line:
    return 'INFO', f'Capability probes skipped ({what}): every installed capability is served'


def withheld_line(loaded: Loaded, missing: list[str]) -> Line:
    return 'INFO', f'Capability {loaded.distribution} withheld: the cluster is missing {", ".join(missing)}'


def unanswered_line(loaded: Loaded, reason: str) -> Line:
    return 'WARNING', f'Capability {loaded.distribution} served without a probe answer: the probe {reason}'


@dataclass
class Started:
    """What one in-process start did."""

    status: int
    events: list[str]
    lines: list[Line]
    critical: list[str]
    executor: ProbeExecutor
    built: tuple[Loaded, ...] | None = None
    checked: list[str] = field(default_factory=list)
    middlewares: list = field(default_factory=list)
    starts: int = 0
    seconds: float = 0.0
    server: Any = None


def start(argv: list[str], capabilities: tuple[Loaded, ...] | Callable[[], Any], responder: Callable,
          monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, *, env: dict[str, str] | None = None,
          site_delay: float = 0.0, real_server: bool = False, real_executor: bool = False) -> Started:
    """Run `cluster-mcp argv` in process with `capabilities` installed and the probe answered by `responder`.

    `capabilities` may instead be a callable standing in for `installed()` (one that raises refuses the
    load). Every step is recorded; `real_server` builds the real server (its `run` still does nothing),
    and `real_executor` keeps the real `_create_executor`.
    """
    monkeypatch.delenv(OVERRIDE, raising=False)
    for name in ('CLUSTER_MCP_INSTRUCTIONS_BUDGET', 'RCAC_INSTRUCTIONS_BUDGET'):
        monkeypatch.delenv(name, raising=False)
    (Path(os.environ['HOME']) / 'user-map').write_text('alice ualice\n')
    monkeypatch.setenv('CLUSTER_MCP_USER_MAP', str(Path(os.environ['HOME']) / 'user-map'))
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    executor = ProbeExecutor(responder)
    observed = Started(-1, [], [], [], executor)
    events = observed.events
    loading = capabilities if callable(capabilities) else (lambda: capabilities)
    monkeypatch.setattr(cluster_mcp.core, 'installed', loading)

    def spy(owner: Any, name: str, event: str) -> None:
        real = getattr(owner, name)

        def recorded(*args: Any, **kwargs: Any) -> Any:
            events.append(event)
            return real(*args, **kwargs)
        monkeypatch.setattr(owner, name, recorded)

    spy(MCPServerApp, '_load_capabilities', 'load')
    spy(MCPServerApp, '_resolve_exec_mode', 'ladder')
    spy(MCPServerApp, '_resolve_budget', 'budget')
    spy(MCPServerApp, '_resolve_skip_probes', 'override')
    spy(MCPServerApp, '_served', 'served')
    spy(probes, 'unprobed', 'unprobed')
    real_start = probes.start

    def started(*args: Any, **kwargs: Any) -> probes.Pending:
        events.append('start')
        observed.starts += 1
        return real_start(*args, **kwargs)
    monkeypatch.setattr(probes, 'start', started)
    real_compose = site.compose

    def check(base: str, *args: Any, **kwargs: Any) -> str:
        events.append('check')
        observed.checked.append(base)
        return real_compose(base, *args, **kwargs)
    monkeypatch.setattr(site, 'compose', check)

    if real_executor:
        spy(MCPServerApp, '_create_executor', 'executor')
    else:
        def create_executor(self: MCPServerApp, mode: str) -> ProbeExecutor:
            events.append('executor')
            return executor
        monkeypatch.setattr(MCPServerApp, '_create_executor', create_executor)

    def read_site(self: MCPServerApp, mode: str, shared: Any) -> site.SiteContext:
        events.append('site')
        time.sleep(site_delay)
        return SITE
    monkeypatch.setattr(MCPServerApp, '_read_site', read_site)

    class Server:
        def run(self, **kwargs: Any) -> None:
            events.append('run')

    def create(auth_mode: str | None = None, middlewares: list | None = None, *, site: site.SiteContext,
               budget: int, capabilities: Any = None) -> Any:
        events.append('serve')
        observed.built = capabilities
        observed.middlewares = list(middlewares or [])
        given = loading() if capabilities is None else capabilities
        if real_server:
            observed.server = create_mcp_server('none', site=site, budget=budget, capabilities=given)
        else:
            real_compose(base_instructions(given), site, budget)
        return Server()
    monkeypatch.setattr(cluster_mcp.core, 'create_mcp_server', create)

    caplog.clear()
    began = time.monotonic()
    try:
        with caplog.at_level(logging.INFO, logger='cluster_mcp.core'):
            observed.status = MCPServerApp.main(argv)
    finally:
        observed.seconds = time.monotonic() - began
        executor.release.set()
    records = [r for r in caplog.records if r.name == 'cluster_mcp.core']
    observed.critical = [r.getMessage() for r in records if r.levelno >= logging.CRITICAL]
    # Each line beyond the start's own, with the level its record was logged at.
    observed.lines = [(r.levelname, r.getMessage()) for r in records
                      if not OWN.match(r.getMessage()) and r.levelno < logging.CRITICAL]
    return observed


def mode_argv(mode: str, transport: str = 'http') -> list[str]:
    """The flags that start `mode` over `transport`."""
    if mode == 'local':
        return ['-t', transport, '-e', 'local']
    if mode == 'ssh':
        return ['-t', transport, '--ssh-host', 'probe.invalid']
    return ['-t', 'http', '-a', 'jwt']


def outcome(capabilities: tuple[Loaded, ...], absent: set[str]) -> tuple[tuple[Loaded, ...], list[Line]]:
    """What an answer missing `absent` serves, and the lines it logs."""
    served, lines = [], []
    for c in capabilities:
        missing = [n for n in c.capability.commands if n in absent]
        if missing:
            lines.append(withheld_line(c, missing))
        else:
            served.append(c)
    return tuple(served), lines


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('mode', ['local', 'ssh'])
def test_local_and_ssh_probe_once_after_the_executor(mode: str, names: tuple[str, ...],
                                                     monkeypatch: pytest.MonkeyPatch,
                                                     caplog: pytest.LogCaptureFixture, guard) -> None:
    capabilities = capability_set(names)
    observed = start(mode_argv(mode), capabilities, answering(set()), monkeypatch, caplog)
    problems = [] if observed.status == 0 else [f'exit {observed.status}: {observed.critical}']
    if observed.events != ORDER:
        problems.append(f'the start ran {observed.events}, expected {ORDER}')
    if observed.starts != 1 or len(observed.executor.calls) != 1:
        problems.append(f'{observed.starts} probes started and {len(observed.executor.calls)} lookups, expected one')
    else:
        argv, timeout = observed.executor.calls[0]
        if ProbeExecutor.names_of(argv) != declared(capabilities):
            problems.append(f'looked up {ProbeExecutor.names_of(argv)}, expected {declared(capabilities)}')
        if timeout != probes.PROBE_TIMEOUT:
            problems.append(f'the lookup was given {timeout} s, expected the bound, {probes.PROBE_TIMEOUT} s')
    shared = [getattr(m, '_executor', None) for m in observed.middlewares]
    if shared != [observed.executor]:
        problems.append(f'the middleware shares {shared}, not the executor the probe ran through')
    if observed.built != capabilities:
        problems.append(f'built from {observed.built}, expected every installed capability')
    if observed.lines:
        problems.append(f'lines beyond the start\'s own: {observed.lines}')
    assert problems == [], 'the probe did not run once after the executor: ' + '; '.join(problems)
    assert guard.refused == []


# Which commands the cluster lacks, by what is missing: nothing; the command of the capability made
# here; each member's commands (beside the core alone, the one made here); every declared command; one
# command alone (the first a member declares, else the one made here).
ABSENT = ['nothing', 'planted', 'each-member', 'everything', 'one-command']


def absent_for(kind: str, capabilities: tuple[Loaded, ...]) -> set[str]:
    every = declared(capabilities)
    if kind == 'nothing':
        return set()
    if kind == 'planted':
        return set(PLANTED.capability.commands)
    if kind == 'each-member':
        return {n for c in capabilities if c not in (PLANTED, QUIET) for n in c.capability.commands} or \
            set(PLANTED.capability.commands)
    if kind == 'everything':
        return set(every)
    return {every[0]}


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('kind', ABSENT)
@pytest.mark.parametrize('mode', ['local', 'ssh'])
def test_the_server_is_built_from_what_the_probe_keeps(mode: str, kind: str, names: tuple[str, ...],
                                                        monkeypatch: pytest.MonkeyPatch,
                                                        caplog: pytest.LogCaptureFixture, guard) -> None:
    capabilities = capability_set(names)
    absent = absent_for(kind, capabilities)
    observed = start(mode_argv(mode), capabilities, answering(absent), monkeypatch, caplog)
    want, lines = outcome(capabilities, absent)
    problems = [] if observed.status == 0 else [f'exit {observed.status}: {observed.critical}']
    if observed.built != want:
        problems.append(f'built from {[c.distribution for c in observed.built or ()]}, '
                        f'expected {[c.distribution for c in want]}')
    if observed.lines != lines:
        problems.append(f'logged {observed.lines}, expected {lines}')
    assert problems == [], 'the server was not built from what the probe kept: ' + '; '.join(problems)
    assert guard.refused == []


LISTED = re.compile(r'^- (\w+):', re.MULTILINE)


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('kind', ['planted', 'each-member', 'everything', 'one-command'])
def test_the_served_instructions_name_exactly_the_served_tools(kind: str, names: tuple[str, ...],
                                                               monkeypatch: pytest.MonkeyPatch,
                                                               caplog: pytest.LogCaptureFixture, guard) -> None:
    capabilities = capability_set(names)
    absent = absent_for(kind, capabilities)
    want, _ = outcome(capabilities, absent)
    withheld = [c for c in capabilities if c not in want]
    assert withheld, 'the row withholds nothing'
    observed = start(mode_argv('local'), capabilities, answering(absent), monkeypatch, caplog, real_server=True)
    assert observed.status == 0 and observed.server is not None, observed.critical
    surface = served_surface(observed.server)
    tools = sorted(surface['tools'])
    want_tools = sorted({t.name for t in CORE_TOOLS} | {t.name for c in want for t in c.tools})
    base, heading, _ = surface['instructions'].partition(f'\n\n{HEADING}\n\n')
    problems = [] if heading else ['the served instructions carry no site section']
    if tools != want_tools:
        problems.append(f'serves {tools}, expected {want_tools}')
    listed = LISTED.findall(base)
    if sorted(listed) != tools or len(listed) != len(set(listed)):
        problems.append(f'the base lists {sorted(listed)}, the server serves {tools}')
    if base != base_instructions(want):
        problems.append('the base is not the core\'s text and each served capability\'s, in order')
    for c in withheld:
        if c.capability.instructions in base:
            problems.append(f'the base carries the text of {c.distribution}, which was withheld')
    want_uris = sorted({e['uri'] for e in RESOURCE_REGISTRY} | {e['uri'] for c in want for e in c.capability.resources})
    if sorted(surface['resources']) != want_uris:
        problems.append(f'serves resources {sorted(surface["resources"])}, expected {want_uris}')
    assert problems == [], 'the served instructions do not name exactly the served tools: ' + '; '.join(problems)
    assert base.startswith(CORE_INSTRUCTIONS)
    assert guard.refused == []


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_the_probe_follows_the_site_read_and_is_bounded(names: tuple[str, ...], monkeypatch: pytest.MonkeyPatch,
                                                        caplog: pytest.LogCaptureFixture, guard) -> None:
    monkeypatch.setattr(probes, 'PROBE_TIMEOUT', 0.6)
    capabilities = capability_set(names)
    observed = start(mode_argv('local'), capabilities, ProbeExecutor.hang, monkeypatch, caplog, site_delay=0.5)
    lines = [unanswered_line(c, 'did not answer within 0.6 s') for c in capabilities if c.capability.commands]
    problems = [] if observed.status == 0 else [f'exit {observed.status}: {observed.critical}']
    if observed.events != ORDER:
        problems.append(f'the start ran {observed.events}, expected {ORDER}')
    if observed.seconds >= 0.5 + 0.6 + 0.3:
        problems.append(f'the start took {observed.seconds:.2f} s, past the site read and the bound')
    if observed.built != capabilities:
        problems.append(f'built from {[c.distribution for c in observed.built or ()]}, expected every capability')
    if observed.lines != lines:
        problems.append(f'logged {observed.lines}, expected {lines}')
    assert problems == [], 'a hung probe was not held to its bound after the site read: ' + '; '.join(problems)
    assert guard.refused == []


@dataclass(frozen=True)
class Ending:
    """How a lookup ends without an answer, and the reason the start logs for it."""

    responder: Callable[[ProbeExecutor, list[str]], Any]
    reason: str


class PlantedStop(BaseException):
    """Neither an Exception nor an exit."""


def raising(exc: BaseException) -> Callable[[ProbeExecutor, list[str]], Any]:
    def respond(executor: ProbeExecutor, names: list[str]) -> Any:
        raise exc
    return respond


def coded(code: int) -> Callable[[ProbeExecutor, list[str]], CommandResult]:
    return lambda executor, names: ProbeExecutor.answer((True for _ in names), code=code, tail='')


# Every ending of the lookup that is no answer, and the reason each is logged with (bound 0.3 s).
ENDINGS = {
    'timeout-code': Ending(coded(TIMEOUT_EXIT_CODE), 'did not answer within 0.3 s'),
    'connection-lost': Ending(coded(CONNECTION_LOST_EXIT_CODE), 'lost the connection'),
    'not-started': Ending(coded(NOT_STARTED_EXIT_CODE), 'could not run: the command did not start'),
    'exit-1': Ending(coded(1), 'could not run: it exited 1'),
    'malformed': Ending(lambda e, names: ProbeExecutor.answer((True for _ in names), tail='end x\n'),
                        'gave an answer that does not parse'),
    'raises': Ending(raising(RuntimeError('planted failure')), 'could not run: RuntimeError: planted failure'),
    'exits-0': Ending(raising(SystemExit(0)), 'could not run: SystemExit: 0'),
    'exits-text': Ending(raising(SystemExit('planted exit')), 'could not run: SystemExit: planted exit'),
    'raises-base': Ending(raising(PlantedStop('planted stop')), 'could not run: PlantedStop: planted stop'),
    'interrupted': Ending(raising(KeyboardInterrupt()), 'could not run: KeyboardInterrupt'),
    'not-a-result': Ending(lambda e, names: None, "could not run: AttributeError: 'NoneType' object has no "
                                                  "attribute 'exit_code'"),
    'hang': Ending(ProbeExecutor.hang, 'did not answer within 0.3 s'),
}


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize(('mode', 'transport'), [('local', 'stdio'), ('local', 'http'), ('ssh', 'stdio'),
                                                 ('ssh', 'sse')])
@pytest.mark.parametrize('ending', list(ENDINGS))
def test_every_ending_without_an_answer_serves_every_capability(ending: str, mode: str, transport: str,
                                                                names: tuple[str, ...],
                                                                monkeypatch: pytest.MonkeyPatch,
                                                                caplog: pytest.LogCaptureFixture, guard) -> None:
    monkeypatch.setattr(probes, 'PROBE_TIMEOUT', 0.3)
    capabilities = capability_set(names)
    case = ENDINGS[ending]
    observed = start(mode_argv(mode, transport), capabilities, case.responder, monkeypatch, caplog)
    lines = [unanswered_line(c, case.reason) for c in capabilities if c.capability.commands]
    problems = [] if observed.status == 0 else [f'exit {observed.status}: {observed.critical}']
    if observed.events != ORDER:
        problems.append(f'the start ran {observed.events}, expected {ORDER}')
    if observed.built != capabilities:
        problems.append(f'built from {[c.distribution for c in observed.built or ()]}, expected every capability')
    if observed.lines != lines:
        problems.append(f'logged {observed.lines}, expected {lines}')
    if observed.seconds >= (0.3 if ending in ('hang', 'timeout-code') else 0) + 0.5:
        problems.append(f'the start took {observed.seconds:.2f} s')
    assert problems == [], 'an ending without an answer did not serve every capability: ' + '; '.join(problems)
    assert guard.refused == []


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
def test_an_interrupt_while_waiting_for_the_probe_interrupts_the_start(names: tuple[str, ...],
                                                                       monkeypatch: pytest.MonkeyPatch,
                                                                       caplog: pytest.LogCaptureFixture,
                                                                       guard) -> None:
    monkeypatch.setattr(probes, 'PROBE_TIMEOUT', 5.0)
    capabilities = capability_set(names)
    # A real SIGINT to the main thread, as Ctrl-C sends, while it waits for the answer.
    timer = threading.Timer(0.2, signal.pthread_kill, (threading.main_thread().ident, signal.SIGINT))

    def hang(executor: ProbeExecutor, names_: list[str]) -> Any:
        timer.start()
        return ProbeExecutor.hang(executor, names_)
    try:
        observed = start(mode_argv('local'), capabilities, hang, monkeypatch, caplog)
    finally:
        timer.cancel()
    problems = [] if observed.status == exit_status.keyboard_interrupt else [f'exit {observed.status}']
    if observed.built is not None:
        problems.append('the server was built')
    if observed.lines:
        problems.append(f'logged {observed.lines}')
    assert problems == [], 'an interrupt while the start waited for the probe did not interrupt it: ' + \
        '; '.join(problems)
    assert guard.refused == []


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('override', [pytest.param(None, id='unset'), pytest.param('1', id='variable'),
                                      pytest.param('--skip-probes', id='flag')])
def test_delegate_runs_no_probe_and_says_so(override: str | None, names: tuple[str, ...],
                                            monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
                                            guard) -> None:
    capabilities = capability_set(names)
    env = {'JWT_SECRET': SECRET, **({OVERRIDE: override} if override == '1' else {})}
    argv = mode_argv('delegate') + (['--skip-probes'] if override == '--skip-probes' else [])
    observed = start(argv, capabilities, answering(set(declared(capabilities))), monkeypatch, caplog, env=env)
    problems = [] if observed.status == 0 else [f'exit {observed.status}: {observed.critical}']
    if observed.events != DELEGATE_ORDER:
        problems.append(f'the start ran {observed.events}, expected {DELEGATE_ORDER}')
    if observed.starts or observed.executor.calls:
        problems.append(f'{observed.starts} probes started, {len(observed.executor.calls)} lookups')
    if observed.built != capabilities:
        problems.append(f'built from {[c.distribution for c in observed.built or ()]}, expected every capability')
    if observed.lines != [DELEGATE_LINE]:
        problems.append(f'logged {observed.lines}, expected [{DELEGATE_LINE!r}]')
    assert problems == [], 'delegate mode probed or did not say it skipped: ' + '; '.join(problems)
    assert guard.refused == []


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('how', ['flag', 'variable-1', 'variable-0', 'variable-space', 'variable-empty',
                                 'flag-and-variable'])
@pytest.mark.parametrize('mode', ['local', 'ssh'])
def test_the_override_skips_every_probe(mode: str, how: str, names: tuple[str, ...],
                                        monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
                                        guard) -> None:
    capabilities = capability_set(names)
    value = {'variable-1': '1', 'variable-0': '0', 'variable-space': ' ', 'variable-empty': '',
             'flag-and-variable': '1'}.get(how)
    env = {} if value is None else {OVERRIDE: value}
    # With both set, the flag wins and the line names it.
    flag = how in ('flag', 'flag-and-variable')
    argv = mode_argv(mode) + (['--skip-probes'] if flag else [])
    absent = set(declared(capabilities))
    observed = start(argv, capabilities, answering(absent), monkeypatch, caplog, env=env)
    problems = [] if observed.status == 0 else [f'exit {observed.status}: {observed.critical}']
    if how == 'variable-empty':
        # Empty counts as unset: the start probes.
        want, lines = outcome(capabilities, absent)
        if observed.starts != 1 or len(observed.executor.calls) != 1:
            problems.append(f'an empty variable skipped the probe: {observed.starts} started')
    else:
        want, lines = capabilities, [skip_line('--skip-probes' if flag else OVERRIDE)]
        expected = [e if e != 'start' else 'unprobed' for e in ORDER]
        if observed.events != expected:
            problems.append(f'the start ran {observed.events}, expected {expected}')
        if observed.starts or observed.executor.calls:
            problems.append(f'{observed.starts} probes started, {len(observed.executor.calls)} lookups')
    if observed.built != want:
        problems.append(f'built from {[c.distribution for c in observed.built or ()]}, '
                        f'expected {[c.distribution for c in want]}')
    if observed.lines != lines:
        problems.append(f'logged {observed.lines}, expected {lines}')
    assert problems == [], 'the override did not skip every probe: ' + '; '.join(problems)
    assert guard.refused == []


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('value', ['0', 'maybe', 'false', 'no', 'off'])
def test_any_non_empty_override_value_skips(value: str, names: tuple[str, ...], monkeypatch: pytest.MonkeyPatch,
                                            caplog: pytest.LogCaptureFixture, guard) -> None:
    # The value is never parsed: any non-empty one is set, and none is refused.
    capabilities = capability_set(names)
    observed = start(mode_argv('local'), capabilities, answering(set(declared(capabilities))), monkeypatch, caplog,
                     env={OVERRIDE: value})
    problems = [] if observed.status == 0 else [f'exit {observed.status}: {observed.critical}']
    if observed.starts or observed.executor.calls or observed.built != capabilities:
        problems.append(f'probed: {observed.starts} started, built from '
                        f'{[c.distribution for c in observed.built or ()]}')
    if observed.lines != [skip_line(OVERRIDE)]:
        problems.append(f'logged {observed.lines}')
    assert problems == [], f'{OVERRIDE}={value!r} did not skip every probe: ' + '; '.join(problems)
    assert guard.refused == []


def full_minimum(capabilities: tuple[Loaded, ...]) -> int:
    return site.minimum_budget(base_instructions(capabilities), SITE)


def refused_load() -> tuple[Loaded, ...]:
    raise CapabilityLoadError('planted-broken', 'planted refusal')


class Refusing:
    """A Fabric connection whose connect is refused."""

    def __init__(self, host: str, **kwargs: Any) -> None:
        pass

    def open(self) -> None:
        raise ConnectionRefusedError(61, 'Connection refused')


# Each refusal: its argv, its environment, and its exit status (None: any but success).
REFUSALS = ['load', 'connect', 'generate-token', 'budget-0', 'budget-not-a-number', 'budget-short-of-every',
            'legacy-budget-short-of-every']


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('refusal', REFUSALS)
def test_no_probe_runs_before_a_refusal(refusal: str, names: tuple[str, ...], monkeypatch: pytest.MonkeyPatch,
                                        caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str],
                                        guard) -> None:
    # A probe that ran would hang, and be abandoned at this bound.
    monkeypatch.setattr(probes, 'PROBE_TIMEOUT', 0.3)
    capabilities = capability_set(names)
    short = str(full_minimum(capabilities) - 1)
    argv, env, status, loading = mode_argv('local'), {}, exit_status.bad_argument, capabilities
    real_executor = False
    if refusal == 'load':
        loading, status = refused_load, exit_status.runtime_error
    elif refusal == 'connect':
        argv, status, real_executor = mode_argv('ssh'), exit_status.runtime_error, True
        monkeypatch.setattr(cluster_mcp.core.executor.ssh, 'Connection', Refusing)
    elif refusal == 'generate-token':
        argv, env, status = ['--generate-token', '--sub', 'planted'], {'JWT_SECRET': SECRET}, exit_status.success
    elif refusal == 'budget-0':
        argv = argv + ['--instructions-budget', '0']
    elif refusal == 'budget-not-a-number':
        env = {'CLUSTER_MCP_INSTRUCTIONS_BUDGET': 'lots'}
    elif refusal == 'budget-short-of-every':
        argv = argv + ['--instructions-budget', short]
    else:
        env = {'RCAC_INSTRUCTIONS_BUDGET': short}
    observed = start(argv, loading, ProbeExecutor.hang, monkeypatch, caplog, env=env, real_executor=real_executor)
    problems = [] if observed.status == status else [f'exit {observed.status}, expected {status}']
    if observed.starts or observed.executor.calls or 'start' in observed.events or 'unprobed' in observed.events:
        problems.append(f'a probe ran: {observed.events}')
    probe_lines = [line for line in observed.lines if line[1].startswith('Capability ')]
    if probe_lines:
        problems.append(f'logged {probe_lines}')
    if observed.built is not None:
        problems.append('the server was built')
    if refusal == 'generate-token' and capsys.readouterr().out.count('.') != 2:
        problems.append('no token was printed')
    assert problems == [], f'a probe ran before the {refusal} refusal: ' + '; '.join(problems)
    assert guard.refused == []


@pytest.mark.unit
@pytest.mark.parametrize('names', MEMBER_SETS)
@pytest.mark.parametrize('answer', ['present', 'absent', 'hang'])
@pytest.mark.parametrize('budget', ['short-of-every', 'every'])
def test_the_budget_never_depends_on_the_answer(budget: str, answer: str, names: tuple[str, ...],
                                                monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
                                                guard) -> None:
    monkeypatch.setattr(probes, 'PROBE_TIMEOUT', 0.2)
    capabilities = capability_set(names)
    full = full_minimum(capabilities)
    least = site.minimum_budget(base_instructions(outcome(capabilities, set(declared(capabilities)))[0]), SITE)
    assert least < full, 'withholding every probed capability frees no budget: the row proves nothing'
    responder = {'present': answering(set()), 'absent': answering(set(declared(capabilities))),
                 'hang': ProbeExecutor.hang}[answer]
    given = full - 1 if budget == 'short-of-every' else full
    observed = start(mode_argv('local') + ['--instructions-budget', str(given)], capabilities, responder,
                     monkeypatch, caplog)
    problems = []
    if observed.checked[:1] != [base_instructions(capabilities)]:
        problems.append('the budget was not checked against every installed capability\'s text first')
    if budget == 'short-of-every':
        if observed.status != exit_status.bad_argument or observed.starts or observed.built is not None:
            problems.append(f'exit {observed.status}, {observed.starts} probes started: a budget short of every '
                            f'capability\'s text started, or probed before it refused')
    elif observed.status != 0 or observed.starts != 1:
        problems.append(f'exit {observed.status}, {observed.starts} probes started: a budget that holds every '
                        f'capability\'s text did not start')
    assert problems == [], f'the budget depends on the answer ({answer}): ' + '; '.join(problems)
    assert guard.refused == []


# The real CLI, in `local` mode, behind a login profile that stubs PATH.

SCRIPT = 'cp "$1" "$HOME/.bash_profile" && err=$2 && shift 2 && exec "$@" 2>"$err"'
STUB_PATH = ('/usr/bin', '/bin')
MEMBER_COMMANDS = {c.distribution: c.capability.commands for c in installed()}
ALL_COMMANDS = [n for commands in MEMBER_COMMANDS.values() for n in commands]
CORE_URIS = {e['uri'] for e in RESOURCE_REGISTRY}


@dataclass
class Host:
    """A login profile for one drive: its file, the stub directory, the login log and the stderr file."""

    profile: Path
    stubs: Path
    log: Path
    err: Path

    def logins(self) -> int:
        return len(self.log.read_text().splitlines()) if self.log.exists() else 0

    def lines(self, stderr: str | None = None) -> list[Line]:
        """The probe's lines on stderr, as the core logger wrote them, each with its level."""
        text = self.err.read_text() if stderr is None else stderr
        return [(m.group(1), m.group(2).strip())
                for m in re.finditer(r'(\w+) \[cluster_mcp\.core\] (.*)$', text, re.M)
                if m.group(2).startswith('Capability ')]


def host(tmp_path: Path, present: list[str], ends: bool = False) -> Host:
    """A profile that logs each login and puts stubs of `present`, and nothing else, first on PATH (or,
    with `ends`, ends the login at once)."""
    for name in ALL_COMMANDS:
        found = [d for d in STUB_PATH if os.access(os.path.join(d, name), os.X_OK)]
        if found:
            pytest.fail(f'{name} is installed here ({found[0]}), so a drive cannot make it absent', pytrace=False)
    stubs = tmp_path / 'stubs'
    stubs.mkdir()
    for name in present:
        (stubs / name).write_text('#!/bin/sh\nexit 0\n')
        (stubs / name).chmod(0o755)
    log = tmp_path / 'logins.log'
    text = f"printf 'login\\n' >> '{log}'\nPATH='{stubs}:{':'.join(STUB_PATH)}'\nexport PATH\n"
    if ends:
        text += 'exit 3\n'
    profile = tmp_path / 'profile'
    profile.write_text(text)
    return Host(profile, stubs, log, tmp_path / 'server.err')


def drive_env(tmp_path: Path) -> dict[str, str]:
    """This process's environment without the override, the sandbox under `tmp_path`."""
    env = {k: v for k, v in os.environ.items() if k != OVERRIDE}
    return {**env, 'TMPDIR': str(tmp_path), 'FASTMCP_CHECK_FOR_UPDATES': 'off'}


def inside(h: Host, *flags: str) -> list[str]:
    """What `bin/sandbox.sh` runs for a drive behind `h`: the profile put in place, then the CLI in `local`
    mode with `flags`, its stderr to `h.err`."""
    return ['sh', '-c', SCRIPT, 'sh', str(h.profile), str(h.err), str(CLI), '-e', 'local', *flags]


def withheld_of(absent: set[str]) -> tuple[Loaded, ...]:
    return tuple(c for c in installed() if set(c.capability.commands) & absent)


def surface_violations(tools: tuple[str, ...], resources: tuple[str, ...], instructions: str | None,
                       withheld: tuple[Loaded, ...]) -> list[str]:
    """Every way what a client listed differs from a server serving every installed member but `withheld`."""
    served = tuple(c for c in installed() if c not in withheld)
    want_tools = {t.name for t in CORE_TOOLS} | {t.name for c in served for t in c.tools}
    want_uris = CORE_URIS | {e['uri'] for c in served for e in c.capability.resources}
    problems = []
    if sorted(tools) != sorted(want_tools):
        problems.append(f'tools {sorted(set(tools) ^ want_tools)} differ')
    if sorted(resources) != sorted(want_uris):
        problems.append(f'resources {sorted(set(resources) ^ want_uris)} differ')
    base = (instructions or '').partition(f'\n\n{HEADING}\n\n')[0]
    if base != base_instructions(served):
        problems.append('the base is not the texts of what is served')
    return problems


def withheld_lines(absent: set[str]) -> list[Line]:
    return [withheld_line(c, [n for n in c.capability.commands if n in absent]) for c in withheld_of(absent)]


UNANSWERED = [unanswered_line(c, 'could not run: the command did not start') for c in installed()
              if c.capability.commands]


@pytest.mark.integration
@pytest.mark.parametrize('absent', [
    pytest.param((), id='nothing'),
    pytest.param(('cluster-mcp-slurm',), id='slurm'),
    pytest.param(('cluster-mcp-rcac',), id='rcac'),
    pytest.param(('cluster-mcp-rcac', 'cluster-mcp-slurm'), id='both'),
])
def test_a_withheld_capability_is_not_served_over_stdio(absent: tuple[str, ...], tmp_path: Path) -> None:
    missing = {n for d in absent for n in MEMBER_COMMANDS[d]}
    h = host(tmp_path, [n for n in ALL_COMMANDS if n not in missing])
    listed = stdio_tools([str(SANDBOX), *inside(h)], ERA, env=drive_env(tmp_path))
    problems = surface_violations(listed.tools, listed.resources, listed.instructions, withheld_of(missing))
    if h.lines() != withheld_lines(missing):
        problems.append(f'stderr says {h.lines()}, expected {withheld_lines(missing)}')
    if h.logins() != 1:
        problems.append(f'{h.logins()} logins, expected one probe')
    assert problems == [], 'a withheld capability was served over stdio: ' + '; '.join(problems)


@pytest.mark.integration
def test_a_probe_without_an_answer_serves_every_capability_over_stdio(tmp_path: Path) -> None:
    h = host(tmp_path, [], ends=True)
    listed = stdio_tools([str(SANDBOX), *inside(h)], ERA, env=drive_env(tmp_path))
    problems = surface_violations(listed.tools, listed.resources, listed.instructions, ())
    if h.lines() != UNANSWERED:
        problems.append(f'stderr says {h.lines()}, expected {UNANSWERED}')
    if h.logins() != 1:
        problems.append(f'{h.logins()} logins, expected one probe')
    assert problems == [], 'a probe without an answer did not serve every capability: ' + '; '.join(problems)


def free_port() -> int:
    """A loopback port nothing listens on, outside the ports this host keeps for other servers."""
    while True:
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        if not 54001 <= port <= 54004:
            return port


def over_http(h: Host, tmp_path: Path) -> tuple[Any, list[str]]:
    """Start the server over HTTP behind `h`, list it, stop it by process group; the listing and leftovers."""
    port = free_port()
    server = subprocess.Popen([str(SANDBOX), *inside(h, '-t', 'http', '-H', '127.0.0.1', '-p', str(port))], stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=drive_env(tmp_path),
                              start_new_session=True)
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                socket.create_connection(('127.0.0.1', port), timeout=0.5).close()
                break
            except OSError:
                if server.poll() is not None or time.monotonic() > deadline:
                    pytest.fail(f'the server did not listen (exit {server.poll()}): {h.err.read_text()[-600:]}',
                                pytrace=False)
                time.sleep(0.1)
        listed = url_tools(f'http://127.0.0.1:{port}/mcp', 'http', ERA)
    finally:
        try:
            os.killpg(server.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        server.wait(10)
    deadline = time.monotonic() + 10
    while group_alive(server.pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    leftovers = [f'the server process group {server.pid} outlived the stop'] if group_alive(server.pid) else []
    return listed, leftovers


@pytest.mark.integration
@pytest.mark.parametrize('ending', ['slurm-absent', 'no-answer'])
@pytest.mark.parametrize('drive', ['stdin-closed', 'http'])
def test_withheld_with_stdin_closed_and_over_http(drive: str, ending: str, tmp_path: Path) -> None:
    missing = set(MEMBER_COMMANDS['cluster-mcp-slurm']) if ending == 'slurm-absent' else set()
    h = host(tmp_path, [n for n in ALL_COMMANDS if n not in missing], ends=ending == 'no-answer')
    lines = withheld_lines(missing) if missing else UNANSWERED
    problems: list[str] = []
    if drive == 'stdin-closed':
        try:
            done = subprocess.run([str(SANDBOX), *inside(h)], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  env=drive_env(tmp_path), timeout=60, start_new_session=True)
        except subprocess.TimeoutExpired:
            pytest.fail('the server did not exit with stdin closed', pytrace=False)
        if done.returncode != 0:
            problems.append(f'exit {done.returncode}: {h.err.read_text()[-400:]}')
    else:
        listed, leftovers = over_http(h, tmp_path)
        problems += leftovers + surface_violations(listed.tools, listed.resources, listed.instructions,
                                                   withheld_of(missing))
    if h.lines() != lines:
        problems.append(f'stderr says {h.lines()}, expected {lines}')
    if h.logins() != 1:
        problems.append(f'{h.logins()} logins, expected one probe')
    assert problems == [], f'{drive}, {ending}: ' + '; '.join(problems)
