# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Where the probe runs in startup, in every mode, and what the server is then built from.

    uv run python -I spec/capability-probe/verify/startup_order.py        from the worktree root

Runs `MCPServerApp.main` in this process with this gate's own stand-ins, never the suite's: the shared
executor (`_create_executor`) is an executor that records each call and answers the probe as told, the
site read records when it starts and ends, `create_mcp_server` records the capabilities it is given
and returns a server whose `run` does nothing, and `probes.start` is wrapped to count its calls. The
lines of the `cluster_mcp.core` logger are captured. `CLUSTER_MCP_SKIP_PROBES` is removed first.

- `local` and `ssh` (R4): exactly one probe call, through the executor `_create_executor` returned,
  after it was created, after the site read and before `create_mcp_server`; the server is built from
  exactly the installed capabilities the answer keeps, for every subset the members' commands can
  answer (each member absent, both, neither); each withheld one has one line naming its distribution,
  and no other line is logged but the start's own (`ALLOWED`) [R1, R3];
- with the bound lowered to 0.6 s, a probe that hangs and a site read that takes 0.5 s, the start
  reaches `create_mcp_server` within the two plus 0.3 s, every capability served, one line each
  [R5, R6];
- `PROBE_TIMEOUT` is one figure, 10 s, no more than `site.READ_TIMEOUT` [R5];
- installed capabilities that declare no command (the members, their commands replaced by none): no
  executor call at all, every capability served, no probe line [R5];
- `delegate` (jwt): `probes.start` never called, every installed capability served, exactly one line
  saying probes are skipped in that mode, also with the override set [R7];
- in `local` and in `ssh` mode, `--skip-probes`, and the variable as `1` and as `0` (any non-empty
  value is set): no executor call, every installed capability served, one line naming what skipped;
  the variable empty: one call [R8];
- a capability that cannot load, an SSH host on a closed loopback port, `--generate-token`, an
  instructions budget of 0, one the environment gives that is not a number, and a budget that holds
  the served base but not every installed capability's: `probes.start` never called, no probe line;
  the last refused (exit 2) whatever the probe would answer, so the refusal never depends on it [R9].

Footprint: one process, no subprocess; the only network use is one connect to a closed loopback port;
under 300 MB; about 5 s.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import re
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import cluster_mcp.core as core
from cluster_mcp.core import probes, site as site_context
from cluster_mcp.core.capabilities import CapabilityLoadError, installed
from cluster_mcp.core.executor.base import CommandResult
from cluster_mcp.core.server import base_instructions

os.environ.pop('CLUSTER_MCP_SKIP_PROBES', None)
# The lines a start logs whatever it probes: the mode, the connect, the delegate middleware, and a
# refusal's own message (each refusal case checks it by exit status).
ALLOWED = re.compile(r'(Execution mode: |SSH connection established to |Delegate mode: executor will be created'
                     r'|cannot load capability |cannot connect to |instructions budget |the instructions budget '
                     r'|CLUSTER_MCP_INSTRUCTIONS_BUDGET must be )')
MEMBERS = installed()
COMMANDS = {m.distribution: m.capability.commands for m in MEMBERS}


class Lines(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


class Recorder:
    def __init__(self, absent: set[str], hang: bool = False, site_delay: float = 0.0) -> None:
        self.absent, self.hang, self.site_delay = absent, hang, site_delay
        self.events: list[str] = []
        self.runs = 0
        self.served = None
        self.starts = 0
        self.release = threading.Event()

    # The shared executor.
    hostname = 'gate'

    def run(self, command, cwd=None, timeout=None):
        self.runs += 1
        self.events.append('probe')
        names = list(command)[list(command).index('-c') + 3:]
        if self.hang:
            self.release.wait(30)
        return CommandResult(''.join('0\n' if n in self.absent else '1\n' for n in names) + f'end {len(names)}\n',
                             '', 0, 'gate')

    def close(self) -> None:
        pass


def drive(argv: list[str], rec: Recorder, *, environ: dict[str, str] | None = None, loaded=None,
          real_executor: bool = False) -> tuple[int, list[str], float]:
    """Run `cluster-mcp argv` in process with the stand-ins; its exit status, its log lines, its time."""
    saved = {name: getattr(core.MCPServerApp, name) for name in ('_create_executor', '_read_site')}
    saved_create, saved_start, saved_installed = core.create_mcp_server, probes.start, core.installed
    handler = Lines()
    logger = logging.getLogger('cluster_mcp')
    logger.addHandler(handler)
    old_env = dict(os.environ)
    os.environ.update(environ or {})

    def create_executor(self, mode):
        if real_executor:
            return saved['_create_executor'](self, mode)
        rec.events.append('executor')
        return rec

    def read_site(self, mode, executor):
        rec.events.append('site')
        time.sleep(rec.site_delay)
        rec.events.append('site-done')
        return site_context.SiteContext.missing('the gate')

    class Server:
        def run(self, **kwargs) -> None:
            pass

    def create(*args, capabilities=None, site=None, budget=None, **kwargs):
        rec.events.append('serve')
        rec.served = capabilities
        site_context.compose(base_instructions(capabilities if capabilities is not None else installed()), site, budget)
        return Server()

    def start(*args, **kwargs):
        rec.starts += 1
        return saved_start(*args, **kwargs)

    core.MCPServerApp._create_executor = create_executor
    core.MCPServerApp._read_site = read_site
    core.create_mcp_server = create
    probes.start = start
    if loaded is not None:
        core.installed = lambda: loaded
    began = time.monotonic()
    try:
        status = core.MCPServerApp.main(argv)
    finally:
        took = time.monotonic() - began
        for name, value in saved.items():
            setattr(core.MCPServerApp, name, value)
        core.create_mcp_server, probes.start, core.installed = saved_create, saved_start, saved_installed
        logger.removeHandler(handler)
        os.environ.clear()
        os.environ.update(old_env)
        rec.release.set()
    # Every line the start logged but the start's own: the probe's lines, and anything else, which the
    # callers count as a fault.
    return status, [line for line in handler.lines if not ALLOWED.match(line)], took


def closed_port() -> int:
    """A loopback port nothing listens on, outside the ports this host keeps for other servers."""
    while True:
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        if not 54001 <= port <= 54004:
            return port


def names(served) -> list[str]:
    return sorted(m.distribution for m in served) if served is not None else ['<every installed>']


def main() -> int:
    bad: list[str] = []
    every = sorted(m.distribution for m in MEMBERS)

    for mode in ('local', 'ssh'):
        for absent_dists in ((), ('cluster-mcp-slurm',), ('cluster-mcp-rcac',), tuple(every)):
            absent = {c for d in absent_dists for c in COMMANDS[d]}
            rec = Recorder(absent)
            extra = ['--ssh-host', 'gate.invalid'] if mode == 'ssh' else []
            status, lines, _ = drive(['-t', 'http', '-e', mode, *extra], rec)
            label = f'{mode}, {list(absent_dists) or "nothing"} absent'
            if status != 0:
                bad.append(f'{label}: exit {status}')
            if rec.events != ['executor', 'site', 'site-done', 'probe', 'serve']:
                bad.append(f'{label}: events {rec.events}, expected the executor, the site read, one probe, '
                           f'then the server')
            want = [d for d in every if d not in absent_dists]
            if names(rec.served) != want:
                bad.append(f'{label}: built from {names(rec.served)}, expected {want}')
            for d in every:
                mine = [line for line in lines if d in line]
                if len(mine) != (1 if d in absent_dists else 0):
                    bad.append(f'{label}: lines for {d}: {mine}')
            if len(lines) != len(absent_dists):
                bad.append(f'{label}: {len(lines)} lines beyond the start\'s own, expected {len(absent_dists)}: {lines}')

    saved_bound = probes.PROBE_TIMEOUT
    probes.PROBE_TIMEOUT = 0.6
    try:
        rec = Recorder(set(), hang=True, site_delay=0.5)
        status, lines, took = drive(['-t', 'http', '-e', 'local'], rec)
    finally:
        probes.PROBE_TIMEOUT = saved_bound
    if status != 0 or took >= 0.5 + 0.6 + 0.3 or names(rec.served) != every or len(lines) != len(every):
        bad.append(f'hang: exit {status}, {took:.2f} s, built from {names(rec.served)}, lines {lines}: the probe '
                   f'is not held to its bound, or not served open')
    if not (probes.PROBE_TIMEOUT == 10.0 and probes.PROBE_TIMEOUT <= site_context.READ_TIMEOUT):
        bad.append(f'PROBE_TIMEOUT is {probes.PROBE_TIMEOUT!r}, expected 10.0 and no more than READ_TIMEOUT')

    quiet = tuple(dataclasses.replace(m, capability=dataclasses.replace(m.capability, commands=())) for m in MEMBERS)
    rec = Recorder(set(every))
    status, lines, _ = drive(['-t', 'http', '-e', 'local'], rec, loaded=quiet)
    if status != 0 or rec.runs or names(rec.served) != every or lines:
        bad.append(f'nothing declared: exit {status}, {rec.runs} calls, built from {names(rec.served)}, lines {lines}')

    with tempfile.TemporaryDirectory(prefix='startup-order-') as scratch:
        users = Path(scratch) / 'users'
        users.write_text('gate gate\n')
        for label, environ in (('delegate', {}), ('delegate, override set', {'CLUSTER_MCP_SKIP_PROBES': '1'})):
            rec = Recorder(set(every))
            status, lines, _ = drive(['-t', 'http', '-a', 'jwt', '-e', 'delegate'], rec,
                                     environ={'JWT_SECRET': 'x' * 40, 'CLUSTER_MCP_USER_MAP': str(users), **environ})
            if status != 0 or rec.starts or rec.runs or names(rec.served) != every:
                bad.append(f'{label}: exit {status}, {rec.starts} starts, built from {names(rec.served)}')
            if len(lines) != 1 or 'delegate' not in lines[0]:
                bad.append(f'{label}: expected one line saying probes are skipped in delegate mode: {lines}')

    for mode, extra in (('local', []), ('ssh', ['--ssh-host', 'gate.invalid'])):
        for label, argv, environ in (('--skip-probes', ['--skip-probes'], {}),
                                     ('variable 1', [], {'CLUSTER_MCP_SKIP_PROBES': '1'}),
                                     ('variable 0', [], {'CLUSTER_MCP_SKIP_PROBES': '0'})):
            rec = Recorder(set(every))
            status, lines, _ = drive(['-t', 'http', '-e', mode, *extra, *argv], rec, environ=environ)
            if status != 0 or rec.runs or rec.starts or names(rec.served) != every or len(lines) != 1 \
                    or 'skip' not in lines[0].lower():
                bad.append(f'{mode}, {label}: exit {status}, {rec.runs} calls, built from {names(rec.served)}, '
                           f'lines {lines}')
        rec = Recorder(set())
        status, lines, _ = drive(['-t', 'http', '-e', mode, *extra], rec, environ={'CLUSTER_MCP_SKIP_PROBES': ''})
        if status != 0 or rec.runs != 1 or lines:
            bad.append(f'{mode}, variable empty: exit {status}, {rec.runs} calls, lines {lines}; expected 0, one, none')

    def refused_load():
        raise CapabilityLoadError('gate-broken', 'planted')

    closed = closed_port()
    site = site_context.SiteContext.missing('the gate')
    full = site_context.minimum_budget(base_instructions(MEMBERS), site)
    for label, argv, kwargs in (
            ('load refusal', ['-t', 'http', '-e', 'local'], {'loaded': None}),
            ('connect failure', ['-t', 'http', '--ssh-host', f'127.0.0.1:{closed}'], {'real_executor': True}),
            ('--generate-token', ['--generate-token'], {'environ': {'JWT_SECRET': 'x' * 40}}),
            ('budget 0', ['-t', 'http', '-e', 'local', '--instructions-budget', '0'], {}),
            ('budget not a number', ['-t', 'http', '-e', 'local'],
             {'environ': {'CLUSTER_MCP_INSTRUCTIONS_BUDGET': 'lots'}}),
            ('budget short of every capability', ['-t', 'http', '-e', 'local', '--instructions-budget',
                                                  str(full - 1)], {})):
        rec = Recorder(set())
        if label == 'load refusal':
            saved_installed = core.installed
            core.installed = refused_load
            try:
                status, lines, _ = drive(argv, rec)
            finally:
                core.installed = saved_installed
        else:
            status, lines, _ = drive(argv, rec, **kwargs)
        if rec.starts or rec.runs or lines:
            bad.append(f'{label}: probes started ({rec.starts}) or ran ({rec.runs}), lines {lines}')
        if label.startswith('budget') and status != 2:
            bad.append(f'{label}: exit {status}, expected 2')
    least = site_context.minimum_budget(base_instructions(()), site)
    if not least < full:
        bad.append(f'the served base alone needs {least}, not less than every capability\'s {full}: the budget '
                   f'case proves nothing')

    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print('startup_order: ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
