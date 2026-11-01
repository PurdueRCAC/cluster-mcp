# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The probe runner decides every ending on one path, within its bound; its lookup finds what `exec` runs.

    bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run python -I spec/capability-probe/verify/lookups.py'

Part one, in process, against this gate's own executors (never the suite's fakes): `probes.start` over
loaded capabilities (the installed members and two hand-made ones), with a bound of 0.5 s, and
`Pending.verdicts()`:
- no capability declares a command: the executor is never called, every capability served, no reason;
- otherwise exactly one call, a registered fixed script (`scripts.script_of`) given every declared name
  once, in load order, as positional parameters, with a timeout no longer than the bound;
- a well-formed answer: a capability with every name `1` is served with no reason, one with any `0` is
  withheld naming exactly its missing names, one with no commands is served with no reason;
- every other ending serves every probing capability with a reason and serves the others with none:
  the timeout, not-started and connection-lost codes, any other exit (1, 255, -9), each malformed
  answer (empty, a missing or wrong `end`, one line short or long, a `2`, a name echoed, a CR), a
  result that is not a CommandResult (None, a string), `Exception`, `OSError`, `SystemExit` with 0,
  an int and a string, a `BaseException` subclass, and a hang released only after the check;
- `verdicts()` returns within the bound plus 0.5 s, whatever the ending; an ending that raises is
  decided within half the bound and its reason names the type raised (the worker catches
  `BaseException`); a second call to it, or a call after a late answer, gives the same verdicts.

Part two, the lookup itself through `LocalShellExecutor` (the pinned login bash), with this sandbox
HOME's `.bash_profile` putting a stub directory first on PATH: a stub file is `1`; a name with no file
is `0`, also when the profile defines and exports a function of that name, and when it exports a
function named `type` that prints `1`; the answer is in the order sent; a stub that is not executable
is `0`.

Footprint: this process, at most one bash launch at a time, under 300 MB; about 10 s.
"""

from __future__ import annotations

import os
import stat
import sys
import threading
import time
from pathlib import Path

from cluster_mcp.core import probes, scripts
from cluster_mcp.core.capabilities import Capability, Loaded, installed
from cluster_mcp.core.executor.base import (CONNECTION_LOST_EXIT_CODE, NOT_STARTED_EXIT_CODE,
                                            TIMEOUT_EXIT_CODE, CommandResult)

BOUND = 0.5
SLACK = 0.5
# Each ending that raises in the worker, and the type its reason must name.
RAISES = {'Exception': 'RuntimeError', 'OSError': 'OSError', 'SystemExit 0': 'SystemExit',
          'SystemExit 3': 'SystemExit', 'SystemExit str': 'SystemExit', 'BaseException': 'Odd'}


class Odd(BaseException):
    """A BaseException that is neither an Exception nor a SystemExit."""


class Gate:
    """An executor whose one answer is `answer(names)`: a CommandResult, anything else, or a raise."""

    def __init__(self, answer) -> None:
        self.answer = answer
        self.calls: list[tuple[list[str], float | None]] = []
        self.release = threading.Event()

    hostname = 'gate'

    def run(self, command, cwd=None, timeout=None):
        self.calls.append((list(command), timeout))
        names = list(command)[list(command).index('-c') + 3:]
        return self.answer(self, names)


def result(stdout: str, code: int = 0) -> CommandResult:
    return CommandResult(stdout, '', code, 'gate')


def lines(found) -> str:
    return ''.join('1\n' if f else '0\n' for f in found)


def answer_from(present: set[str]):
    return lambda g, names: result(lines(n in present for n in names) + f'end {len(names)}\n')


def raising(exc):
    def go(g, names):
        raise exc
    return go


def hanging(g, names):
    g.release.wait(30)
    return result(lines(True for _ in names) + f'end {len(names)}\n')


def made(name: str, commands: tuple[str, ...]) -> Loaded:
    cap = Capability(name=name, order=500, tools=f'gate_{name}.tools', instructions='-', commands=commands)
    return Loaded(cap, f'gate-{name}', ())


def capability_sets() -> dict[str, tuple[Loaded, ...]]:
    members = installed()
    extra = made('extra', ('sinfo', 'gate_only'))
    quiet = made('quiet', ())
    return {'members': members, 'members+extra+quiet': (*members, extra, quiet), 'quiet': (quiet,)}


def check_set(label: str, caps: tuple[Loaded, ...]) -> list[str]:
    bad: list[str] = []
    names = list(dict.fromkeys(n for c in caps for n in c.capability.commands))
    probing = [c for c in caps if c.capability.commands]

    def verdicts(executor) -> tuple[tuple, float]:
        began = time.monotonic()
        got = probes.start(executor, caps, timeout=BOUND).verdicts()
        return got, time.monotonic() - began

    if not names:
        g = Gate(answer_from(set()))
        got, _ = verdicts(g)
        if g.calls:
            bad.append(f'{label}: nothing declared, yet the executor was called: {g.calls}')
        if any(not v.served or v.reason for v in got):
            bad.append(f'{label}: nothing declared, yet {[(v.loaded.distribution, v.served, v.reason) for v in got]}')
        return bad

    # Definite answers: each subset of the names present.
    for present in (set(names), set(), {names[0]}, set(names[1:])):
        g = Gate(answer_from(present))
        got, took = verdicts(g)
        if len(g.calls) != 1:
            bad.append(f'{label} {sorted(present)}: {len(g.calls)} calls, expected 1')
            continue
        argv, timeout = g.calls[0]
        if scripts.script_of(argv) != probes.LOOKUP or argv[argv.index('-c') + 3:] != names:
            bad.append(f'{label}: the call is not LOOKUP over {names}: {argv}')
        if timeout is None or timeout > BOUND:
            bad.append(f'{label}: the call waits {timeout!r}, beyond the bound {BOUND}')
        for v in got:
            missing = [n for n in v.loaded.capability.commands if n not in present]
            if not v.loaded.capability.commands:
                ok = v.served and v.reason is None
            elif missing:
                ok = (not v.served and v.reason is not None and all(n in v.reason for n in missing)
                      and not any(n in v.reason.split() for n in v.loaded.capability.commands if n in present))
            else:
                ok = v.served and v.reason is None
            if not ok:
                bad.append(f'{label} present={sorted(present)}: {v.loaded.distribution} served={v.served} '
                           f'reason={v.reason!r}')

    # No definite answer: every probing capability served with a reason, the others with none.
    n = len(names)
    endings = {
        'timeout code': lambda g, ns: result('', TIMEOUT_EXIT_CODE),
        'not-started code': lambda g, ns: result('', NOT_STARTED_EXIT_CODE),
        'connection-lost code': lambda g, ns: result(lines(True for _ in ns), CONNECTION_LOST_EXIT_CODE),
        'exit 1': lambda g, ns: result(lines(True for _ in ns) + f'end {n}\n', 1),
        'exit 255': lambda g, ns: result('', 255),
        'signal 9': lambda g, ns: result('', -9),
        'empty': lambda g, ns: result(''),
        'no end': lambda g, ns: result(lines(True for _ in ns)),
        'wrong end': lambda g, ns: result(lines(True for _ in ns) + f'end {n + 1}\n'),
        'one short': lambda g, ns: result(lines(True for _ in ns[1:]) + f'end {n}\n'),
        'one long': lambda g, ns: result(lines(True for _ in ns) + f'1\nend {n}\n'),
        'a 2': lambda g, ns: result('2\n' + lines(True for _ in ns[1:]) + f'end {n}\n'),
        'a name echoed': lambda g, ns: result(f'{ns[0]}\n' + lines(True for _ in ns[1:]) + f'end {n}\n'),
        'a CR': lambda g, ns: result(lines(True for _ in ns).replace('\n', '\r\n') + f'end {n}\r\n'),
        'end first': lambda g, ns: result(f'end {n}\n' + lines(True for _ in ns)),
        'None': lambda g, ns: None,
        'a str': lambda g, ns: 'end 0\n',
        'Exception': raising(RuntimeError('gate')),
        'OSError': raising(OSError('gate')),
        'SystemExit 0': raising(SystemExit(0)),
        'SystemExit 3': raising(SystemExit(3)),
        'SystemExit str': raising(SystemExit('gate')),
        'BaseException': raising(Odd()),
        'hang': hanging,
    }
    for ending, answer in endings.items():
        g = Gate(answer)
        try:
            pending = probes.start(g, caps, timeout=BOUND)
            began = time.monotonic()
            got = pending.verdicts()
            took = time.monotonic() - began
            again = pending.verdicts()
        except BaseException as exc:
            bad.append(f'{label} {ending}: {type(exc).__name__} escaped the runner: {exc}')
            g.release.set()
            continue
        g.release.set()
        time.sleep(0.05)
        late = pending.verdicts()
        if took > BOUND + SLACK:
            bad.append(f'{label} {ending}: verdicts took {took:.2f} s, beyond {BOUND} + {SLACK}')
        if ending in RAISES:
            # A raise is decided when it happens, never by the deadline, and its reason names it.
            if took >= BOUND / 2:
                bad.append(f'{label} {ending}: a raise took {took:.2f} s to decide; the worker must catch it')
            if any(v.reason and RAISES[ending] not in v.reason for v in got if v.loaded.capability.commands):
                bad.append(f'{label} {ending}: the reason does not name {RAISES[ending]}: '
                           f'{[v.reason for v in got]}')
        for v in got:
            want_reason = bool(v.loaded.capability.commands)
            if not v.served or bool(v.reason) != want_reason:
                bad.append(f'{label} {ending}: {v.loaded.distribution} served={v.served} reason={v.reason!r}')
        if [(v.served, v.reason) for v in again] != [(v.served, v.reason) for v in got] or \
                [(v.served, v.reason) for v in late] != [(v.served, v.reason) for v in got]:
            bad.append(f'{label} {ending}: the verdicts changed on a later call')
    if not probing:
        bad.append(f'{label}: no probing capability in the set')
    return bad


def stub_home(present: list[str], function_only: list[str], unexecutable: list[str]) -> None:
    home = Path(os.environ['HOME'])
    stubs = home / 'stubs'
    stubs.mkdir(exist_ok=True)
    for f in stubs.iterdir():
        f.unlink()
    for name in present + unexecutable:
        f = stubs / name
        f.write_text('#!/bin/sh\nexit 0\n')
        if name in present:
            f.chmod(f.stat().st_mode | stat.S_IXUSR)
    profile = [f'PATH="{stubs}:$PATH"', 'export PATH']
    for name in function_only:
        profile += [f'{name}() {{ :; }}', f'export -f {name}']
    profile += ['type() { printf "1\\n"; }', 'export -f type']
    (home / '.bash_profile').write_text('\n'.join(profile) + '\n')


def check_bash() -> list[str]:
    from cluster_mcp.core.executor.shell import LocalShellExecutor
    bad: list[str] = []
    present = ['gate_cmd_one', 'gate_cmd_two']
    function_only = ['gate_fn_only']
    unexecutable = ['gate_not_exec']
    stub_home(present, function_only, unexecutable)
    names = ['gate_cmd_two', 'gate_missing', 'gate_fn_only', 'gate_cmd_one', 'gate_not_exec']
    want = [True, False, False, True, False]
    executor = LocalShellExecutor()
    caps = tuple(made(f'n{i}', (name,)) for i, name in enumerate(names))
    got = probes.start(executor, caps, timeout=probes.PROBE_TIMEOUT).verdicts()
    for v, name, expected in zip(got, names, want):
        if v.reason and not v.reason.startswith('missing'):
            bad.append(f'bash: {name}: no definite answer: {v.reason}')
        elif v.served != expected:
            bad.append(f'bash: {name}: served={v.served}, expected {expected} ({v.reason})')
    return bad


def main() -> int:
    if not os.environ.get('CLUSTER_MCP_SANDBOX'):
        raise SystemExit('lookups: run inside bin/sandbox.sh (it writes the HOME .bash_profile)')
    bad: list[str] = []
    for label, caps in capability_sets().items():
        bad += check_set(label, caps)
    bad += check_bash()
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print('lookups: ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
