# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Capability probes: whether the cluster has the commands each installed capability declares.

A capability declares the commands it needs as data (`Capability.commands`, checked when it loads),
never as code, so no capability code runs when the cluster is probed. `start()` looks every declared
name up at once: one registered fixed script (`LOOKUP`), run through the given executor on a daemon
thread, under one deadline (`PROBE_TIMEOUT`, or the bound given) however many capabilities declare
commands. A capability set that declares none runs nothing. `Pending.verdicts()` waits for the answer
until that deadline at most, and decides each capability once:

- one that declares no command is served, with nothing to report;
- one whose every command the answer finds is served, with nothing to report;
- one with a command the answer does not find is withheld, its reason naming each missing command;
- every other ending (no answer by the deadline; the lookup timing out, not starting, losing its
  connection or exiting nonzero; an answer that does not parse; anything the executor returns
  instead of a result, or raises, whatever it is) serves each capability that declares a command,
  its reason saying why.

`unprobed()` serves every capability, with nothing to report and no lookup run. Nothing here runs at
import, and nothing here decides what startup does with a verdict.
"""

# Type annotations
from __future__ import annotations
from typing import Final, Iterable

# Standard libs
import threading
import time
from dataclasses import dataclass

# Internal libs
from cluster_mcp.core.capabilities import Loaded, _cause
from cluster_mcp.core.executor.base import (CONNECTION_LOST_EXIT_CODE, NOT_STARTED_EXIT_CODE, TIMEOUT_EXIT_CODE,
                                            Executor)
from cluster_mcp.core.scripts import fixed, script_argv

# Public interface
__all__ = ['PROBE_TIMEOUT', 'LOOKUP', 'Verdict', 'Pending', 'start', 'unprobed']

# The one bound, in seconds, on every probe of a start together: no more than the site read's. It is
# read when a probe starts, and no setting changes it.
PROBE_TIMEOUT: Final = 10.0

# One line per name, in the order given: `1` when a file of that name is on PATH, which is what a
# tool's `exec` runs (`type -P`, never a function, builtin or alias), and `0` when none is; then the
# count, which the answer is checked against. A function named `type` is undone first, and
# `FIXED_RESET` undoes one named `printf`. No name is echoed, so no name can forge a line.
LOOKUP: Final = fixed(
    'unset -f type\n'
    'for n do if type -P -- "$n" >/dev/null 2>&1; then printf "1\\n"; else printf "0\\n"; fi; done\n'
    'printf "end %s\\n" "$#"\n'
)


@dataclass(frozen=True)
class Verdict:
    """What the probe decided for one capability: served or withheld, and why (None: nothing to report)."""

    loaded: Loaded
    served: bool
    reason: str | None


def _names(capabilities: Iterable[Loaded]) -> list[str]:
    """Every command `capabilities` declare, each once, in load order."""
    return list(dict.fromkeys(name for loaded in capabilities for name in loaded.capability.commands))


def _parse(stdout: str, count: int) -> list[bool] | None:
    """Whether each of `count` names was found, read from exactly `count` lines of `0` or `1` and then
    `end <count>`, each ended by a newline alone; None for any other text."""
    if not stdout.endswith('\n'):
        return None
    lines = stdout[:-1].split('\n')
    if len(lines) != count + 1 or lines[-1] != f'end {count}':
        return None
    if any(line not in ('0', '1') for line in lines[:-1]):
        return None
    return [line == '1' for line in lines[:-1]]


def _ask(executor: Executor, names: list[str], timeout: float) -> dict[str, bool] | str:
    """Whether each of `names` is on the cluster, or why there is no answer."""
    result = executor.run(script_argv(LOOKUP, 'cluster-mcp-probe', *names), timeout=timeout)
    if result.exit_code == TIMEOUT_EXIT_CODE:
        return f'did not answer within {timeout:g} s'
    if result.exit_code == CONNECTION_LOST_EXIT_CODE:
        return 'lost the connection'
    if result.exit_code == NOT_STARTED_EXIT_CODE:
        return 'could not run: the command did not start'
    if result.exit_code != 0:
        return f'could not run: it exited {result.exit_code}'
    found = _parse(result.stdout, len(names))
    if found is None:
        return 'gave an answer that does not parse'
    return dict(zip(names, found))


def _why(exc: BaseException) -> str:
    """The reason for a lookup that raised `exc`, on one line."""
    return 'could not run: ' + ' '.join(_cause(exc).split())


def _verdict(loaded: Loaded, answer: dict[str, bool] | str) -> Verdict:
    """The verdict on `loaded` given the lookup's `answer`, or why there is none."""
    commands = loaded.capability.commands
    if isinstance(answer, str):
        return Verdict(loaded, True, answer if commands else None)
    missing = [name for name in commands if not answer[name]]
    return Verdict(loaded, not missing, f'missing {", ".join(missing)}' if missing else None)


class Pending:
    """A probe of `capabilities`, under way or done; `verdicts()` waits for it until its deadline at most."""

    def __init__(self, capabilities: tuple[Loaded, ...], bound: float) -> None:
        self.capabilities = capabilities
        self._bound = bound
        # The deadline is taken when the probe starts, never when its verdicts are asked for.
        self._deadline = time.monotonic() + bound
        self._answered = threading.Event()
        self._answer: dict[str, bool] | str = {}
        self._verdicts: tuple[Verdict, ...] | None = None

    def _post(self, answer: dict[str, bool] | str) -> None:
        """Record the lookup's answer, or why there is none. One posted after the verdicts changes nothing."""
        self._answer = answer
        self._answered.set()

    def verdicts(self) -> tuple[Verdict, ...]:
        """One verdict per capability, in the order given: decided at the first call, by the deadline at
        the latest, and the same at every later call."""
        if self._verdicts is None:
            answer = (self._answer if self._answered.wait(self._deadline - time.monotonic())
                      else f'did not answer within {self._bound:g} s')
            self._verdicts = tuple(_verdict(loaded, answer) for loaded in self.capabilities)
        return self._verdicts


def start(executor: Executor, capabilities: Iterable[Loaded], timeout: float | None = None) -> Pending:
    """Start probing `capabilities` through `executor`: one lookup of every declared command, or none.

    `timeout` is the bound in seconds, `PROBE_TIMEOUT` when None; the executor is given it too, so the
    command itself stops at the bound wherever the executor can stop it.
    """
    bound = PROBE_TIMEOUT if timeout is None else timeout
    pending = Pending(tuple(capabilities), bound)
    names = _names(pending.capabilities)
    if not names:
        pending._post({})
        return pending

    def work() -> None:
        # Whatever the lookup raises or exits with is a reason, posted at once: the thread never dies
        # with the answer unposted.
        try:
            answer = _ask(executor, names, bound)
        except BaseException as exc:
            answer = _why(exc)
        pending._post(answer)

    try:
        threading.Thread(target=work, name='cluster-mcp-probe', daemon=True).start()
    except Exception as exc:
        pending._post(_why(exc))
    return pending


def unprobed(capabilities: Iterable[Loaded]) -> Pending:
    """Every one of `capabilities` served, with nothing to report and no lookup run."""
    pending = Pending(tuple(capabilities), PROBE_TIMEOUT)
    pending._post(dict.fromkeys(_names(pending.capabilities), True))
    return pending
