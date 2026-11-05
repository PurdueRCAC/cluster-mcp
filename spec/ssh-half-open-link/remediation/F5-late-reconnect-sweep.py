"""`verify/silent-sweep.py`, unchanged, with review cycle 1's F1 decisions and review cycle 2's F-A
decisions added to its table.

Run from the worktree root, with the frozen gate's own arguments:

    uv run python -I spec/ssh-half-open-link/remediation/F5-late-reconnect-sweep.py legacy [1|2]
    uv run python -I spec/ssh-half-open-link/remediation/F5-late-reconnect-sweep.py modern [1|2]

Why: review cycle 2's F-A puts every open a call makes after a reconnect or a loss on a worker the
call waits for no later than its deadline (`ssh._Within`), and the foreman's routing asks for the
cap's alternatives as `shol-` cases in `tests/mutants.py`, swept killed in both eras. The frozen gate
checks its table against `tests/mutants.py` both ways, so with those cases planted it reads them as
cases the sweep does not name, and is red for that alone, as it was for cycle 1's F1 cases.

What changes: `remediation/F1-send-path-sweep.py` runs as it is, and the gate it loads has the rows
below appended to its `SWEEP` first: each a decision of the cap with the alternative it could take
and its case, an equivalent (planted and run against its neighbours' killers, which must all pass),
or a reason it cannot be planted. F1's wrapper then appends its own rows and runs the gate's `main`:
the both-ways check, the halves split by sorted id, each case reported killed, each equivalent
shown. Every earlier row is untouched.

Footprint: the frozen gate's, which it imports from its file and runs in this process.
"""

from __future__ import annotations

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
F1_WRAPPER = os.path.join(HERE, 'F1-send-path-sweep.py')


def _module(name: str, path: str) -> object:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f'cannot load {path}'
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows(gate: object) -> list[tuple[str, str, object]]:
    exec_ = gate.EXEC
    late = f'{exec_}::test_a_late_reconnect_onto_a_link_that_goes_silent_again_ends_in_time[write_file]'
    live = f'{exec_}::test_a_late_reconnect_onto_a_live_link_runs_the_call[write_file]'
    neighbours = (late, live, f'{exec_}::test_a_call_on_a_silent_link_reconnects[write_file]',
                  f'{exec_}::test_a_channel_open_outlasting_its_own_timeout_on_a_silent_link_reconnects[sftp]',
                  *(f'{exec_}::test_an_sftp_open_cut_by_a_silent_link_reconnects[{step}]'
                    for step in ('channel', 'subsystem', 'version')),
                  *(f'{exec_}::test_a_slow_transfer_is_not_taken_for_a_silent_link[{shape}]'
                    for shape in ('put', 'get', 'write')))
    rows: list[tuple[str, str, object]] = []
    for where, prefix in (('`_run`', 'shol-cap'), ('`_sftp`', 'shol-sftp-cap')):
        decision = f'the deadline an open after a reconnect or a loss gets ({where})'
        rows += [
            (decision, 'none (the open waits for its own verdict)', f'{prefix}-removed'),
            (decision, 'the first open\'s only', f'{prefix}-first-only'),
            (decision, 'a window from the open\'s start, not the call\'s', f'{prefix}-from-the-open'),
            (decision, 'the call\'s last start', f'{prefix}-at-the-last-start'),
            (f'an open cut at the deadline ({where})', 'reconnects again', f'{prefix}-cut-retried'),
        ]
    rows += [
        ('the deadline an open after a reconnect or a loss gets (`_run`)', 'on the first open too',
         'shol-cap-always'),
        ('the deadline an open after a reconnect or a loss gets (`_sftp`)', 'on the first open too',
         (gate.EQUIVALENT, 'an SFTP session opens only as a call begins, its whole window ahead, and on the '
                           'connection it found live a silent link meets the open\'s own verdict first, B into the '
                           '3B window; only a write\'s later command opens past its deadline, and that open is '
                           '`_run`\'s (`shol-cap-always`)',
          gate.survivor('sftp-cap-always', (('            until = None if transport is found else deadline\n',
                                             '            until = deadline\n'),), neighbours))),
        ('the worker\'s wait (`_Within`)', 'until the open ends', 'shol-within-waits-past-the-deadline'),
        ('an open that ends after its call gave up', 'left open', 'shol-within-late-open-kept'),
        ('an open whose call\'s deadline has passed', 'started all the same', 'shol-within-started-past-the-deadline'),
        ('a worker that cannot start', 'the open made on the call\'s own thread',
         (gate.NOT_PLANTED, 'it needs a process out of threads; the fallback is `_Sends`\'s, and that open is '
                            'bounded by its own verdict as a first open is')),
    ]
    return rows


def main(argv: list[str]) -> int:
    wrapper = _module('f1_send_path_sweep', F1_WRAPPER)
    load = wrapper._load

    def extended() -> object:
        gate = load()
        gate.SWEEP += _rows(gate)
        return gate

    wrapper._load = extended
    return wrapper.main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:3]) if len(sys.argv) in (2, 3) else main(['']))
