"""`verify/silent-sweep.py`, unchanged, with review cycle 1's F1 decisions added to its table.

Run from the worktree root, with the frozen gate's own arguments:

    uv run python -I spec/ssh-half-open-link/remediation/F1-send-path-sweep.py legacy [1|2]
    uv run python -I spec/ssh-half-open-link/remediation/F1-send-path-sweep.py modern [1|2]

Why: review cycle 1's F1 moved every send a call makes once its exec request is answered onto the
call's sender (`ssh._Sends`), and the foreman's routing asks for the new rule's alternatives as
`shol-` cases in `tests/mutants.py`, swept killed in both eras. The frozen gate checks its table
against `tests/mutants.py` both ways, so with those cases planted it reads them as cases the sweep
does not name, and is red for that alone (seen: `shol-…-on-the-call: a case the sweep does not
name`, once per case, before this wrapper).

What changes: the rows below are appended to the frozen gate's `SWEEP` before its `main` runs, each
a decision of the sender with the alternative it could take and its case (or an equivalent, planted
and run against its neighbours' killers, which must all pass). Everything else is the frozen
gate's: the both-ways check, the halves split by sorted id, each case reported killed, each
equivalent shown. Its earlier rows are untouched.

Footprint: the frozen gate's, which it imports from its file and runs in this process.
"""

from __future__ import annotations

import importlib.util
import os
import sys

GATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'verify', 'silent-sweep.py')


def _load() -> object:
    spec = importlib.util.spec_from_file_location('silent_sweep', GATE)
    assert spec is not None and spec.loader is not None, f'cannot load {GATE}'
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    return gate


def main(argv: list[str]) -> int:
    gate = _load()
    exec_ = gate.EXEC
    neighbours = (f'{exec_}::test_a_timed_call_never_waits_on_a_write_path_another_call_holds[held]',
                  f'{exec_}::test_a_timed_call_never_waits_on_a_write_path_another_call_holds[free]',
                  f'{exec_}::test_a_timed_command_beside_a_transfer_stalled_on_a_silent_link_ends_at_its_timeout')
    gate.SWEEP += [
        # Review cycle 1, F1: what a call sends once its exec request is answered goes through its
        # sender, never on its own thread, and the call waits for it only until its own end.
        ('the TERM at a deadline', 'sent on the call\'s thread', 'shol-term-on-the-call'),
        ('the KILL after the GRACE read', 'sent on the call\'s thread', 'shol-kill-on-the-call'),
        ('the end of stdin', 'sent on the call\'s thread', 'shol-eof-on-the-call'),
        ('the channel\'s close', 'sent on the call\'s thread', 'shol-close-on-the-call'),
        ('a window adjust the reads owe', 'sent on the call\'s thread (Paramiko\'s `recv`)',
         'shol-adjust-on-the-call'),
        ('the call\'s wait for its sends', 'past its timeout and GRACE, until they are made',
         'shol-wait-past-the-deadline'),
        ('the KILL\'s grace', 'counted from the call\'s read, not from when the TERM went',
         'shol-kill-grace-from-the-read'),
        ('the call\'s wait for its sends', 'dropped (the call returns as its sends are handed over)',
         (gate.EQUIVALENT, 'with the path free the sender makes each send within moments of its hand-over, so no '
                           'row tells a call that returned just before its close from one that returned just after; '
                           'with it held, neither waits past the timeout and GRACE',
          gate.survivor('sends-unwaited', (('            sends.wait(until)\n', ''),), neighbours))),
    ]
    return gate.main(*(argv[:2] + ['', ''])[:2])


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:3]) if len(sys.argv) in (2, 3) else main(['']))
