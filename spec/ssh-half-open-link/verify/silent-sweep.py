"""P3 gate: every alternative of each decision of the silent-link monitor and its call paths is planted.

Run from the worktree root, once per era, whole or in two halves (each half stays under a 10-minute
command cap; the second half also runs the equivalents):

    uv run python -I spec/ssh-half-open-link/verify/silent-sweep.py legacy [1|2]
    uv run python -I spec/ssh-half-open-link/verify/silent-sweep.py modern [1|2]

`SWEEP` is the coverage: each decision of `ssh._Liveness` (the hook, the priming probe, the verdict,
the poke, the close, the two threads, the tick, the clock), of the open-retry and of the lost
transfer, with every alternative it could take, values handed to calls included, and what became of
it:

- a case id: a `tests/mutants.py` case plants it, and must be killed (its targets and `why` are the
  case's own);
- `EQUIVALENT`: the same behaviour by every row that could tell; planted here and run against the
  rows that kill its neighbours, which must all pass, so the claim is shown, not argued;
- `NOT_PLANTED`: a reason it cannot be run here.

The gate checks the table against `tests/mutants.py` both ways (every case it names exists, and
every `shol-` case is named), runs every named case with `tests/mutants.py` in the era given (each
must be reported killed), then runs each equivalent (each must be reported as surviving, every target
passed). The halves split the named cases by id, sorted, so a case's half never depends on where the
table lists it.

Footprint: one sandboxed pytest child at a time (a row starts a sandbox, a login bash, one in-process
SSH server and a stall proxy), under 600 MB.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'tests'))

import mutants  # noqa: E402
from mutants import Case  # noqa: E402

ERAS = ('legacy', 'modern')
EQUIVALENT = 'equivalent'
NOT_PLANTED = 'not planted'
SSH = 'core/executor/ssh.py'
EXEC = 'test_ssh_exec.py'


def survivor(name: str, edits: tuple[tuple[str, str], ...], targets: tuple[str, ...]) -> Case:
    """An equivalent alternative, planted with the rows that kill its neighbours (all must pass)."""
    return Case(f'equivalent-{name}', SSH, edits, targets, '')


LOST = f'{EXEC}::test_a_command_on_a_link_that_goes_silent_is_lost[no-timeout]'
IDLE = f'{EXEC}::test_an_idle_connection_is_not_taken_for_a_silent_link'
OUTLASTING = tuple(f'{EXEC}::test_a_channel_open_outlasting_its_own_timeout_on_a_silent_link_reconnects[{opens}]'
                   for opens in ('run', 'sftp'))
FAKE_CLOCK = (f'{EXEC}::test_a_reconnect_after_the_host_returns_gives_the_same_result[second-attempt]',
              f'{EXEC}::test_a_reconnect_after_the_host_returns_gives_the_same_result[forty-seconds-in]',
              f'{EXEC}::test_a_failed_reconnect_leaves_the_server_serving')
NO_ROOM = tuple(f'{EXEC}::test_a_write_that_runs_out_of_room_keeps_the_file[{room}]'
                for room in ('8k-free', '32k-free', 'edquot'))
CUT_WRITES = tuple(f'{EXEC}::test_a_transfer_on_a_link_that_goes_silent_may_be_partly_made[{shape}]'
                   for shape in ('write-upload', 'write-place'))

# (decision, alternative, outcome): outcome is a case id, or (EQUIVALENT, why, case planted here),
# or (NOT_PLANTED, why).
SWEEP: list[tuple[str, str, object]] = [
    # The activity hook and the priming probe.
    ('activity hook', 'removed', 'shol-hook-removed'),
    ('activity hook', 'stamps replies only', 'shol-hook-replies-only'),
    ('activity hook', 'stamps a read that raises', 'shol-hook-stamps-a-raise'),
    ('activity hook', 'the verdict read from the probe\'s own reply only',
     (NOT_PLANTED, 'the class of `shol-hook-replies-only`: what counts as heard is the hook\'s, and a stamp on '
                   'replies alone is that alternative; the slow-link row kills it')),
    ('priming probe', 'dropped', 'shol-priming-dropped'),
    # The verdict.
    ('quiet period', '0', 'shol-quiet-zero'),
    ('quiet period', '3B', 'shol-quiet-3b'),
    ('poke\'s verdict', '0', 'shol-poke-verdict-zero'),
    ('poke\'s verdict', '2B − VERDICT_MARGIN', 'shol-poke-verdict-background'),
    ('poke\'s verdict', '3B', 'shol-poke-verdict-3b'),
    ('poke\'s verdict', 'from `poked` alone, not `max(out, poked)`', 'shol-poke-term-alone'),
    ('background verdict', 'B', 'shol-background-b'),
    ('background verdict', '2B', 'shol-background-2b'),
    ('background verdict', '3B', 'shol-background-3b'),
    ('VERDICT_MARGIN', '0', 'shol-margin-zero'),
    ('the earlier verdict', '`max` for `min`', 'shol-min-as-max'),
    ('an answer', '`heard <= out` for `heard < out`', 'shol-answer-not-before'),
    ('the bound handed to the verdict', '`CONNECT_TIMEOUT`, not `_bound(conn)`', 'shol-bound-connect-timeout'),
    ('the bound handed to the verdict', 'doubled', 'shol-bound-doubled'),
    # The poke.
    ('poke', 'removed (the open makes none)', 'shol-poke-removed'),
    ('poke', 'none after a reconnect',
     (NOT_PLANTED, 'the one poke is the open\'s (`opening`), made by every open that follows `_ensure_connected`, '
                   'after a reconnect as after the fast path: there is no separate site to remove; '
                   '`shol-poke-removed` removes it')),
    ('poke latch', 'cleared on any answer', 'shol-latch-cleared-on-answer'),
    ('poke latch', 'not kept while a call waits on an open', 'shol-hold-not-kept'),
    ('poke', 'moves the probe out', 'shol-poke-moves-out'),
    # The close.
    ('close', 'dropped', 'shol-close-dropped'),
    ('close', 'innermost hop first', 'shol-close-innermost-first'),
    # The two threads.
    ('judge', 'sends the probe itself', 'shol-judge-sends'),
    ('hand-over', '`out` stamped after the send', 'shol-out-after-send'),
    ('hand-over', 'refused while the sender is busy', 'shol-handover-refused-busy'),
    # The tick and the clock.
    ('LIVENESS_TICK', '5 s', 'shol-tick-long'),
    ('LIVENESS_TICK', '0.01 s',
     (EQUIVALENT, 'a tick is how late the judge may see a due time; a shorter one only checks more often',
      survivor('tick-short', (('LIVENESS_TICK: Final = 0.1', 'LIVENESS_TICK: Final = 0.01'),), (LOST, IDLE)))),
    ('LIVENESS_TICK', '0',
     (NOT_PLANTED, 'a busy loop on two threads per connection: the 0.01 s equivalent stands for it')),
    ('monitor clock', 'read from the module `time` at each call',
     (EQUIVALENT, 'in production `time` is the monotonic clock either way; the suite replaces `ssh.time` only in '
                  'the fake-clock reconnect rows, and none of them watches a live connection while its clock '
                  'moves, so they pass',
      survivor('clock-from-time',
               (('_liveness_clock = time.monotonic\n',
                 'def _liveness_clock() -> float:\n    return time.monotonic()\n'),), FAKE_CLOCK))),
    # The open, and its retry.
    ('open timeout', '`OPEN_TIMEOUT` alone', 'shol-open-timeout-alone'),
    ('open timeout', '`OPEN_MARGIN` at 0',
     (EQUIVALENT, 'the open then times out at the verdict\'s own instant, and `_gone` waits `SETTLE` for the '
                  'close the verdict makes, so the call reconnects all the same',
      survivor('open-margin-zero', (('OPEN_MARGIN: Final = 1.0', 'OPEN_MARGIN: Final = 0.0'),), OUTLASTING))),
    ('open failure', 'an unanswered probe read as a loss (the rule dropped at P3)',
     (NOT_PLANTED, 'the rule was removed: an open waits past its verdict (`_open_timeout`), so on a dead link the '
                   'verdict closes the transport before the open\'s own timeout, and `shol-open-timeout-alone` '
                   'is killed')),
    ('open-retry', 'removed', 'shol-retry-removed'),
    ('open-retry', 'extended past the exec request', 'shol-retry-past-exec'),
    ('open-retry', 'with a fresh deadline', 'shol-retry-fresh-deadline'),
    ('open-retry', '`_closed` ignored', 'shol-closed-ignored'),
    ('SFTP open-retry', 'removed', 'shol-sftp-retry-removed'),
    ('SFTP open-retry', 'kept at the channel open only', 'shol-sftp-retry-channel-only'),
    ('SFTP open-retry', 'with a fresh deadline', 'shol-sftp-fresh-deadline'),
    # A transfer cut short.
    ('TransferLost', 'reworded without the host', 'shol-lost-transfer-unnamed'),
    ('TransferLost', 'caught by type (`OSError` only)', 'shol-lost-transfer-by-type'),
    ('loss before `Short`', 'dropped (so `_reason` runs on a loss)', 'shol-reason-on-a-loss'),
    ('loss before `_is_dir`\'s answer', 'dropped', 'shol-is-dir-swallows-a-loss'),
    ('loss before `_loops`\' answer', 'dropped', 'shol-loops-swallows-a-loss'),
    ('loss in the staging block', 'not carried with what may remain', 'shol-staging-loss-unnamed'),
    ('parent `mkdir`', '-1003 or -1002 returned', 'shol-mkdir-loss-returned'),
    ('place step', '-1003 or -1002 returned', 'shol-place-loss-returned'),
    ('a write\'s own -1002', 'lost on a live connection too', 'shol-live-not-started-lost'),
    ('an `OSError` on an open channel', 'waits `SETTLE` as any failure does',
     (EQUIVALENT, 'the transport stays active through `SETTLE` on a live link, so the answer is the same, a '
                  'second later',
      survivor('cut-waits', (('    if isinstance(exc, OSError) and not channel.closed:\n        return False\n', ''),),
               NO_ROOM))),
    ('staging removal', 'tried on a lost session too',
     (EQUIVALENT, 'each removal fails at once on the closed session and is swallowed, so the staging directory '
                  'is left as it is when skipped',
      survivor('discard-on-a-loss', (('            if not lost and not _down(transport):\n',
                                       '            if True:\n'),), CUT_WRITES))),
]


def main(era: str, half: str = '') -> int:
    if era not in ERAS or half not in ('', '1', '2'):
        print(f'usage: silent-sweep.py {"|".join(ERAS)} [1|2] (got {era!r} {half!r})')
        return 2
    started = time.monotonic()
    planted = {c.id for c in mutants.CASES if c.id.startswith('shol-')}
    named = [o for _, _, o in SWEEP if isinstance(o, str)]
    problems = [f'{i}: named twice' for i in sorted({i for i in named if named.count(i) > 1})]
    problems += [f'{i}: no such case in tests/mutants.py' for i in named if i not in planted]
    problems += [f'{i}: a case the sweep does not name' for i in sorted(planted - set(named))]
    equivalents = [o[2] for _, _, o in SWEEP if isinstance(o, tuple) and o[0] == EQUIVALENT]
    if problems or not named or not equivalents:
        print('\n'.join(problems or ['the sweep names nothing']))
        return 1
    ids = sorted(named)
    if half:
        middle = (len(ids) + 1) // 2
        ids = ids[:middle] if half == '1' else ids[middle:]
        equivalents = equivalents if half == '2' else []
    os.environ['CLUSTER_MCP_TEST_ERA'] = era
    run = subprocess.run([sys.executable, 'tests/mutants.py', *ids], capture_output=True, text=True)
    print(run.stdout, end='')
    killed = {line.split()[1].rstrip(':') for line in run.stdout.splitlines() if line.startswith('killed ')}
    failed = [i for i in ids if i not in killed]
    if run.returncode != 0 or failed:
        print(f'FAILED  {len(failed)} of {len(ids)} cases not killed: {" ".join(failed)}; exit {run.returncode}')
        print(run.stderr[-2000:], end='')
        return 1
    for survivor_case in equivalents:
        violations = mutants.run_case(survivor_case)
        passed = {v.split(': passed, so the mutant survived it')[0] for v in violations
                  if v.endswith(': passed, so the mutant survived it')}
        others = [v for v in violations
                  if v != 'the mutant survived: every target passed' and not v.endswith('survived it')]
        if others or passed != set(survivor_case.targets):
            failed.append(survivor_case.id)
            print(f'FAILED  {survivor_case.id}: its rows did not all pass: {"; ".join(others) or violations}')
        else:
            print(f'passed  {survivor_case.id}: {", ".join(survivor_case.targets)} passed')
    for decision, alternative, outcome in SWEEP:
        if isinstance(outcome, tuple) and outcome[0] == NOT_PLANTED:
            print(f'not planted  {decision}: {alternative}: {outcome[1]}')
    shown = len(equivalents) - len([f for f in failed if f.startswith('equivalent-')])
    print(f'{era}{" half " + half if half else ""}: {len(ids)} cases killed, {shown} of {len(equivalents)} '
          f'equivalents shown, in {time.monotonic() - started:.0f} s')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:3]) if len(sys.argv) in (2, 3) else main(''))
