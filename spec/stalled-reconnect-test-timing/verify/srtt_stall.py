"""A pytest plugin that stalls one timing row inside the interval it measures, as a busy host does.

Loaded by `timing-gate.py controls <row>` as `-p srtt_stall`, with this directory on PYTHONPATH and
`SRTT_STALL` naming the row. It patches the product from outside the row, so the same plant runs
against the cycle's tree and the base's:

- `1`: once `SSHExecutor.run` has returned, the main thread stalls `STALL` s at its next
  `threading.enumerate()` (the base row's listing) or `Thread.join` (the cycle row's join): after the
  row has read the call's time, before it counts the workers (the abandoned worker ends 0-0.11 s
  after the call returns).
- `2`: the call stalls `STALL` s after the executor has given up, inside the MCP call the base row
  times (`SSHExecutor._not_run`).
- `3`: the probe's worker stalls `STALL_ENDING` s as it handles a raised ending (`probes._why`): past
  the base row's 0.15 s cut, short of the 0.3 s deadline, as the sightings were (0.18-0.25 s).
- `4`: while a start runs, the first collection the cyclic collector makes takes `STALL_GC` s more
  (the first threshold lowered to 200 so one comes), as a full suite's heap makes a generation-2 collection slow.

A row that measures the property, not the host, stays green under its stall; the base's row goes red.
Footprint: in the pytest process; no child, no thread.
"""

from __future__ import annotations

import gc
import os
# Taken at import: a row may route `time.sleep` to a clock of its own, and a stall is the host's
# time passing, never a sleep of the code under test.
from time import sleep as _stall

STALL = 0.3
STALL_ENDING = 0.2
STALL_GC = 0.6

_ROW = os.environ.get('SRTT_STALL', '')
_undo: list = []
_armed = [False]


def _patch(owner, name, make):
    """Replace `owner.name` with `make(the current one)`; teardown puts back what `owner` itself held."""
    held = owner.__dict__.get(name, _undo)
    setattr(owner, name, make(getattr(owner, name)))
    _undo.append(lambda: delattr(owner, name) if held is _undo else setattr(owner, name, held))


def _slow_collection(phase, info):
    if phase == 'start' and _armed[0]:
        _armed[0] = False
        _stall(STALL_GC)


def pytest_runtest_setup(item):
    if _ROW == '1':
        import threading
        from cluster_mcp.core.executor.ssh import SSHExecutor

        def run(real):
            def arming(self, *args, **kwargs):
                try:
                    return real(self, *args, **kwargs)
                finally:
                    _armed[0] = True
            return arming
        _patch(SSHExecutor, 'run', run)

        def stalls(real):
            def stalled(*args, **kwargs):
                if _armed[0] and threading.current_thread() is threading.main_thread():
                    _armed[0] = False
                    _stall(STALL)
                return real(*args, **kwargs)
            return stalled
        _patch(threading, 'enumerate', stalls)
        _patch(threading.Thread, 'join', stalls)
    elif _ROW == '2':
        from cluster_mcp.core.executor.ssh import SSHExecutor

        def not_run(real):
            def stalled(self, *args, **kwargs):
                _stall(STALL)
                return real(self, *args, **kwargs)
            return stalled
        _patch(SSHExecutor, '_not_run', not_run)
    elif _ROW == '3':
        from cluster_mcp.core import probes

        def why(real):
            def stalled(*args, **kwargs):
                _stall(STALL_ENDING)
                return real(*args, **kwargs)
            return stalled
        _patch(probes, '_why', why)
    elif _ROW == '4':
        from cluster_mcp.core import MCPServerApp, probes
        thresholds = gc.get_threshold()
        gc.callbacks.append(_slow_collection)
        _undo.append(lambda: gc.callbacks.remove(_slow_collection))
        _undo.append(lambda: gc.set_threshold(*thresholds))

        def start(real):
            def armed(*args, **kwargs):
                gc.set_threshold(200, 10, 10)
                _armed[0] = True
                return real(*args, **kwargs)
            return armed
        _patch(probes, 'start', start)

        def main(real):
            def disarmed(*args, **kwargs):
                try:
                    return real(*args, **kwargs)
                finally:
                    _armed[0] = False
                    gc.set_threshold(*thresholds)
            return disarmed
        _patch(MCPServerApp, 'main', main)


def pytest_runtest_teardown(item):
    _armed[0] = False
    while _undo:
        _undo.pop()()
