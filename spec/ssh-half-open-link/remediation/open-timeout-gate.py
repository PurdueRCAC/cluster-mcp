"""`verify/silent-gate.py`, unchanged, but with one row whose develop failure may be a raise.

Run from anywhere in the worktree, with the frozen gate's own arguments:

    uv run python -I spec/ssh-half-open-link/remediation/open-timeout-gate.py commands both   # P1
    uv run python -I spec/ssh-half-open-link/remediation/open-timeout-gate.py all both        # P3

Why (the foreman's ruling at P1's build, 2026-11-05): the frozen gate requires every row marked to
fail on develop to fail with its watchdog's text, `still waiting`, as a call that hangs does.
`test_a_channel_open_outlasting_its_own_timeout_on_a_silent_link_reconnects[run]` patches
`OPEN_TIMEOUT` below `B - SETTLE`, so on develop the channel open raises Paramiko's
`Timeout opening channel.` within a second, before any watchdog: develop fails that row against the
requirement (it neither reconnects nor fails naming the host), but by a raise, not a hang. No row
can make develop hang there and still exercise the open's own timeout.

What changes: for that one row id, and only in the develop runs, a JUnit failure whose text carries
`Timeout opening channel` is accepted as the gate's failure. It is done by marking that failure's
text with the gate's `still waiting` before the frozen predicate reads it. Every other row, every
run on this tree, and every other check of the gate (the era proof, the exit statuses, the `pgrep`
of leftovers) are the frozen gate's own. The row must still pass on this tree, and must still fail
on develop: a pass there, or a failure with neither text, stays red.

Footprint: the frozen gate's, which it imports from its file and runs in this process.
"""

from __future__ import annotations

import importlib.util
import os
import sys

ROW = 'test_a_channel_open_outlasting_its_own_timeout_on_a_silent_link_reconnects[run]'
RAISED = 'Timeout opening channel'
GATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'verify', 'silent-gate.py')


def _load() -> object:
    spec = importlib.util.spec_from_file_location('silent_gate', GATE)
    assert spec is not None and spec.loader is not None, f'cannot load {GATE}'
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    return gate


def main(argv: list[str]) -> int:
    gate = _load()
    outcomes = gate._outcomes

    def widened(cwd, env, rows, basetemp, sync, problems, where):
        found = outcomes(cwd, env, rows, basetemp, sync, problems, where)
        if where.endswith('develop') and ROW in found:
            outcome, message = found[ROW]
            if outcome == 'failure' and RAISED in message and gate.STOP not in message:
                found[ROW] = (outcome, f'{message}\n[{gate.STOP}: accepted as {RAISED!r} for this row only]')
        return found

    gate._outcomes = widened
    return gate.main(*(argv[:2] + ['', ''])[:2])


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
