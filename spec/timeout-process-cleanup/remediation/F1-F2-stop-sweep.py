"""Review cycle 1, F1 and F2: every alternative of the stop's decisions, the new wait and the KILL
request's open-channel guard included, is planted and killed, in one protocol era.

    uv run python -I spec/timeout-process-cleanup/remediation/F1-F2-stop-sweep.py legacy [1|2]
    uv run python -I spec/timeout-process-cleanup/remediation/F1-F2-stop-sweep.py modern [1|2]

Run from the worktree root, once per era, whole or in two halves (each half stays under a 10-minute
command cap; the second half also runs the equivalents).

It supersedes the frozen P3 gate, `verify/sweep.py`, which stays as the record: that table plants
the watchdog's two `read`s and the unconditional KILL request, both retired by review cycle 1 (F1:
a profile's `TMOUT` ends a `read`, so the watchdog took time for the program's death; F2: the KILL
went on channels the client had closed). Its runner is kept verbatim below; the table is this
cycle's.

`SWEEP` is the coverage: each decision of the watchdog (its unset, its statements, its wait and
trigger, its arming and release, its signals, group, delay and descriptor), the prologue's
job-control reset, and over `ssh` the KILL request, its guard on an open channel and `_signal`'s
check under the channel's lock, with every alternative it could take and what became of it:

- a case id: a `tests/mutants.py` case plants it, and must be killed (its targets and `why` are the
  case's own);
- `EQUIVALENT`: the same behaviour by every row that could tell; planted here and run against the
  rows that kill its neighbours, which must all pass, so the claim is shown, not argued;
- `NOT_PLANTED`: a reason it cannot be run here.

The new wait's alternatives that add a bound to it (`tpc-wait-read`, through a profile's `TMOUT`;
`tpc-wait-bounded`, a timeout of its own) are killed by behaviour rows, the profile rows that run a
command past `TMOUT` with the watchdog armed, not by a text pin.

The gate checks the table against `tests/mutants.py` both ways (every case it names exists, and
every `tpc-` case is named), runs every named case with `tests/mutants.py` in the era given (each
must be reported killed), then runs each equivalent (each must be reported as surviving, every
target passed). `tpc-clobber` exists on macOS only (bash 3.2): elsewhere its row is skipped, and the
gate says so.

Footprint: one sandboxed pytest child at a time (a row starts a sandbox, a login bash, up to four
`sleep`s and, over `ssh`, one in-process server), under 500 MB.
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

# (decision, alternative, outcome): outcome is a case id, or (EQUIVALENT, why, case planted here),
# or (NOT_PLANTED, why).
SWEEP: list[tuple[str, str, object]] = []


def case(case_id: str) -> Case:
    return next(c for c in mutants.CASES if c.id == case_id)


def survivor(name: str, edits: tuple[tuple[str, str], ...], targets: tuple[str, ...],
             file: str = mutants.LAUNCH) -> Case:
    """An equivalent alternative, planted with the rows that kill its neighbours (all must pass)."""
    return Case(f'equivalent-{name}', file, edits, targets, '')


def edits_of(case_id: str) -> tuple[tuple[str, str], ...]:
    return case(case_id).edits


M = mutants
SSH = 'core/executor/ssh.py'
# Paramiko's own wait for a key exchange, in place of `_signal`'s: the same send, the lock held.
USER_MESSAGE = M.CHECKED.replace('                with transport.clear_to_send_lock:\n'
                                 '                    if transport.clear_to_send.is_set():\n'
                                 '                        transport._send_message(message)\n'
                                 '                        return\n',
                                 '                transport._send_user_message(message)\n'
                                 '                return\n')
GUARD_ROWS = (M.KILL_DRAINS, M.KILL_ORDER, M.BASHRC_UNDONE, M.HANGING_LOGIN, M.CONNECTION_KEPT)

SWEEP += [
    # The watchdog started, right after the prologue.
    ('watchdog started', 'dropped', 'tpc-watchdog-dropped'),
    *(('watchdog started', f'placed {place}', f'tpc-watchdog-{place}')
      for place in ('before-prologue', 'after-sentinel', 'in-subshell-first', 'in-subshell-last', 'after-subshell',
                    'after-status', 'after-record', 'after-release', 'after-reraise')),
    # The functions bash would run in place of the paths the watchdog runs, unset before the fork.
    ('unset', 'dropped (profile rows)', 'tpc-unset-dropped'),
    ('unset', 'dropped (grace rows)', 'tpc-unset-dropped-grace'),
    ('unset', '`/bin/cat` alone', 'tpc-unset-cat-only'),
    ('unset', '`/bin/sleep` alone', 'tpc-unset-sleep-only'),
    ('unset', 'without `-f` (a name that is no variable is refused)', 'tpc-unset-not-functions'),
    ('unset', 'after the fork', 'tpc-unset-after-fork'),
    # Its line's four statements: ignore TERM, fork, restore TERM, arm.
    *(('watchdog statement order', ', '.join(order), f'tpc-watchdog-order-{"-".join(order)}')
      for order in M.statement_orders() if order != ('ignore', 'fork', 'arm', 'restore')),
    ('watchdog statement order', 'ignore, fork, arm, restore, text', 'tpc-watchdog-order-ignore-fork-arm-restore'),
    ('watchdog statement order', 'ignore, fork, arm, restore',
     (EQUIVALENT, 'the arming line written while TERM is still ignored: the same program a few microseconds '
                  'longer TERM-proof; killed by the launch checker as `tpc-watchdog-order-ignore-fork-arm-restore`',
      survivor('order-arm-before-restore', M.reordered(('ignore', 'fork', 'arm', 'restore')),
               M.NOTHING_STOPPED + M.JOBS_KEPT[:1] + M.GRACE_KEPT[2:3]))),
    # TERM ignored while the program forks it.
    ('ignore at fork', 'dropped', 'tpc-ignore-at-fork-dropped'),
    ('ignore at fork', 'INT ignored instead', 'tpc-ignore-at-fork-int'),
    ('ignore at fork', 'HUP ignored instead', 'tpc-ignore-at-fork-hup'),
    ('ignore at fork', 'any other catchable name ignored instead',
     (NOT_PLANTED, 'the same class as INT and HUP: the watchdog is then not TERM-proof, which only the name TERM '
                   'decides')),
    # TERM's default taken back after the fork.
    ('restore after fork', 'dropped', 'tpc-restore-dropped'),
    ('restore after fork', 'INT restored instead', 'tpc-restore-int'),
    ('restore after fork', 'HUP restored instead', 'tpc-restore-hup'),
    # The open of the pipe: `exec 46>| >(…)`.
    ('the open', '`>` for `>|` (noclobber refuses it on bash 3.2)', 'tpc-clobber'),
    ('the open', '`>>` for `>|`',
     (EQUIVALENT, 'noclobber allows an append, and the pipe has no end to append at',
      survivor('append', ((M.OPENED, 'TERM; exec 46>> >('),), (M.PROFILE_UNDONE,) + M.NOTHING_STOPPED[:1]))),
    ('the open', 'without `exec` (the descriptor not kept)', 'tpc-fd-not-kept'),
    ('the open', '`<(…)` for `>(…)`', 'tpc-substitution-reversed'),
    # The descriptor's number, at each place it is named.
    ('descriptor', 'opened on another', 'tpc-fd-opened-other'),
    ('descriptor', 'armed on another', 'tpc-fd-armed-other'),
    ('descriptor', 'released on another', 'tpc-fd-released-other'),
    ('descriptor', 'closed by the subshell: dropped', 'tpc-fd-left-open'),
    ('descriptor', 'closed by the subshell: another', 'tpc-fd-closed-other'),
    ('descriptor', 'every place: another free one (45)', 'tpc-fd-45'),
    ('descriptor', 'every place: another free one (45), behaviour',
     (EQUIVALENT, 'a free descriptor is the same program; `tpc-fd-45` is the launch checker pinning the number',
      survivor('fd-45', edits_of('tpc-fd-45'), M.NOTHING_STOPPED + M.JOBS_KEPT[:1]))),
    ('descriptor', 'every place: one the program re-points (59)', 'tpc-fd-59'),
    ('descriptor', 'every place: 0, 1 or 2, or one the prologue parks (47–49, 57–58)',
     (NOT_PLANTED, '0–2 replace the call\'s own streams, and 47–49 and 57–58 are closed by the prologue before the '
                   'watchdog opens its pipe, so they are free there (the 45 class); the launch checker pins the '
                   'number')),
    ('subshell redirections', '`46>&-` first',
     (EQUIVALENT, 'the same subshell; `tpc-close-first` is the launch checker pinning the text',
      survivor('close-first', edits_of('tpc-close-first'), M.NOTHING_STOPPED[:1] + M.JOBS_KEPT[:1]))),
    ('subshell redirections', '`46>&-` first, text', 'tpc-close-first'),
    # The streams it must not hold.
    ('holds no stream', 'both kept', 'tpc-holds-output'),
    ('holds no stream', 'stdout kept', 'tpc-holds-stdout'),
    ('holds no stream', 'stderr kept', 'tpc-holds-stderr'),
    ('holds no stream', 'redirection without `exec`', 'tpc-quiet-not-kept'),
    # The wait: `/bin/cat` to the pipe's end, then a full stop once it read to the end.
    ('wait', 'no full stop (`$( )` drops the arming line\'s newline)', 'tpc-wait-no-stop-mark'),
    ('wait', 'ended at the first line', 'tpc-wait-first-line'),
    ('wait', 'through the `read` builtin (a profile\'s `TMOUT` bounds it)', 'tpc-wait-read'),
    ('wait', 'bounded by a timeout of its own', 'tpc-wait-bounded'),
    ('wait', '`cat` (a profile function)', 'tpc-wait-plain-cat'),
    ('wait', '`command cat` (PATH)', 'tpc-wait-command-cat'),
    ('wait', 'the full stop whatever `cat` returned (`;` for `&&`)',
     (EQUIVALENT, '`cat` ends only at the pipe\'s end or by a signal, and a signal that ends it, sent to the '
                  'group, ends the watchdog\'s own shell too (a subshell resets traps, and keeps only ignores, '
                  'which `cat` inherits); the guard keeps a `cat` killed alone from reading as the program\'s death',
      survivor('wait-status-ignored', ((M.WAIT, '$(/bin/cat; printf .)'),),
               M.JOBS_KEPT[:1] + M.NOTHING_STOPPED[:1] + M.TMOUT_KEPT[:2]))),
    ('wait', 'another reader to the end (`dd`, `head -c` of all of it, a `read` loop with no timeout under a '
             'readonly-free profile)',
     (NOT_PLANTED, 'the same predicate where nothing bounds it; a builtin reader is the `tpc-wait-read` class, and '
                   'an absolute path other than `/bin/cat` is a file that differs by platform')),
    # The trigger: the arming line alone, read to the end; anything else stops nothing.
    ('trigger', 'also when nothing was read', 'tpc-unarmed-stops'),
    ('trigger', 'inverted', 'tpc-trigger-inverted'),
    ('trigger', 'on both lines (the release)', 'tpc-trigger-on-release'),
    ('trigger', '`||` for `&&` (the stop unless armed and dead)', 'tpc-stop-or'),
    ('trigger', 'dropped (the stop at every end of file)', 'tpc-stop-unconditional'),
    # The arming and release lines.
    ('arming', 'dropped (stop rows)', 'tpc-arm-dropped-stop'),
    ('arming', 'dropped (survival rows)', 'tpc-arm-dropped'),
    ('arming', 'another byte than the newline', 'tpc-arm-unterminated'),
    ('arming', 'written with `echo`', 'tpc-arm-echo'),
    ('release', 'dropped', 'tpc-release-dropped'),
    *(('release', f'placed {place}', f'tpc-release-{place}')
      for place in ('before-prologue', 'before-watchdog', 'after-watchdog', 'in-subshell-first',
                    'in-subshell-last', 'after-subshell', 'after-status')),
    ('release', 'placed before the command (after the sentinel)', 'tpc-release-before-command'),
    ('release', 'placed after the re-raise', 'tpc-release-after-reraise'),
    ('release', 'another byte than the newline, text', 'tpc-release-unterminated'),
    ('release', 'another byte than the newline',
     (EQUIVALENT, 'any second byte makes what the wait reads other than the arming line alone; '
                  '`tpc-release-unterminated` is the launch checker pinning the text',
      survivor('release-other-byte', edits_of('tpc-release-unterminated'), M.JOBS_KEPT + M.NOTHING_STOPPED[:1]))),
    ('release', 'written with `echo`', 'tpc-release-echo'),
    # The stop: TERM, GRACE, KILL, to group 0.
    ('first signal', 'dropped', 'tpc-term-dropped'),
    *(('first signal', f'{name} for TERM', f'tpc-term-{name.lower()}') for name in ('INT', 'HUP', 'KILL', 'STOP')),
    ('first signal', 'any other name for TERM',
     (NOT_PLANTED, 'catchable names end the handler that TERM should reach (the INT and HUP class), KILL ends '
                   'it at once, and non-terminating names never reach it (the STOP class)')),
    ('last signal', 'dropped', 'tpc-kill-dropped'),
    *(('last signal', f'{name} for KILL', f'tpc-kill-{name.lower()}') for name in ('TERM', 'HUP', 'STOP')),
    ('last signal', 'any other name for KILL',
     (NOT_PLANTED, 'the ignoring shapes ignore every catchable terminating signal (the TERM and HUP class); '
                   'a non-terminating one ends nothing (the STOP class)')),
    ('target', '`$$` for both', 'tpc-group-self'),
    ('target', '`$$` for the TERM', 'tpc-group-self-term'),
    ('target', '`$$` for the KILL', 'tpc-group-self-kill'),
    ('target', '`-$$` for both', 'tpc-group-leader'),
    ('target', '`-1` or `$PPID`',
     (NOT_PLANTED, 'they signal outside the command (every process of the user, or the server, here the test '
                   'runner), so no child can run them safely; the launch checker pins `0`')),
    ('delay', '0', 'tpc-delay-zero'),
    ('delay', '2 × GRACE', 'tpc-delay-doubled'),
    ('delay', 'GRACE / 2', 'tpc-delay-halved'),
    ('delay', 'a fixed 1', 'tpc-delay-fixed'),
    ('delay', 'a fixed 1, behaviour',
     (EQUIVALENT, 'the same program while GRACE is 1; `tpc-delay-fixed` is the text row that renders GRACE 2.5',
      survivor('delay-fixed', edits_of('tpc-delay-fixed'), M.GRACE_KEPT))),
    ('sleep', '`sleep` (a profile function)', 'tpc-plain-sleep'),
    ('sleep', '`command sleep` (PATH)', 'tpc-command-sleep'),
    ('sleep', 'another absolute path (`/usr/bin/sleep`)',
     (NOT_PLANTED, 'equivalent where that file is a sleep (merged-/usr Linux); absent on macOS, where it is the '
                   'zero delay `tpc-delay-zero` plants')),
    # The prologue's job-control reset.
    ('prologue `m`', 'dropped', 'tpc-monitor-kept'),
    # The KILL request over ssh, after the grace read, unless the channel has ended.
    ('KILL request', 'dropped (behaviour)', 'tpc-ssh-kill-dropped'),
    ('KILL request', 'dropped (unit row)', 'tpc-ssh-kill-dropped-unit'),
    ('KILL request', 'before the TERM, unguarded (unit rows)', 'tpc-ssh-kill-before-term'),
    ('KILL request', 'before the TERM, unguarded (grace row)', 'tpc-ssh-kill-before-term-output'),
    ('KILL request', 'before the GRACE read (unit row)', 'tpc-ssh-kill-before-grace'),
    ('KILL request', 'before the GRACE read (grace row)', 'tpc-ssh-kill-before-grace-output'),
    *(('KILL request', f'named {name} ({rows})', f'tpc-ssh-kill-{name.lower()}{suffix}')
      for name in M.SSH_NAMES for rows, suffix in (('behaviour', ''), ('unit row', '-unit'))),
    ('KILL guard', 'dropped (KILL after the channel ended)', 'tpc-ssh-kill-unguarded'),
    ('KILL guard', 'inverted (unit row)', 'tpc-ssh-kill-guard-inverted'),
    ('KILL guard', 'inverted (behaviour)', 'tpc-ssh-kill-guard-inverted-behaviour'),
    ('KILL guard', 'no exit status yet, for not ended', 'tpc-ssh-kill-guard-status'),
    ('KILL guard', 'the channel not closed, for not ended',
     (EQUIVALENT, 'it differs only when the end of output and the exit status have come before the close, when '
                  'the launch has exited and sshd refuses the KILL, so nothing is signalled either way (the '
                  'request goes on a channel still open, which `_signal` checks)',
      survivor('ssh-kill-guard-closed',
               M.kill_request(M.TERM_LINE, M.GRACE_LINE, '            if not chan.closed:\n', M.GUARDED_KILL),
               GUARD_ROWS, SSH))),
    ('KILL guard', 'no end of output yet, for not ended',
     (EQUIVALENT, 'it differs only when the output has ended before the close: nothing still holds the channel '
                  'then, and the launch has exited or holds no stream, so the same rows show the same',
      survivor('ssh-kill-guard-eof',
               M.kill_request(M.TERM_LINE, M.GRACE_LINE, '            if not chan.eof_received:\n', M.GUARDED_KILL),
               GUARD_ROWS, SSH))),
    # `_signal`: nothing on a closed channel, checked and sent holding the channel's lock.
    ('open-channel check', 'dropped', 'tpc-ssh-signal-unchecked'),
    ('open-channel check', '`not chan.active` for `chan.closed`', 'tpc-ssh-signal-active-checked'),
    ('open-channel check', 'without the channel\'s lock', 'tpc-ssh-signal-unlocked'),
    ('open-channel check', 'checked under the lock, sent after it', 'tpc-ssh-signal-checked-then-sent'),
    ('open-channel check', 'sent through Paramiko\'s `_send_user_message`, the lock held',
     (EQUIVALENT, 'the same send in every row; it differs only during a key exchange, which no row runs, where it '
                  'would hold the channel\'s lock through Paramiko\'s wait for the exchange while the transport '
                  'thread needs that lock to deliver what arrives (Paramiko\'s own sends release it first)',
      survivor('ssh-signal-user-message', ((M.CHECKED, USER_MESSAGE),),
               (M.CLOSED_ASKED, M.LOCK_HELD, M.CONNECTION_KEPT, M.BASHRC_UNDONE), SSH))),
]

# On macOS only (bash 3.2 tells `>` from `>|`).
MACOS_ONLY = {'tpc-clobber'}


def main(era: str, half: str = '') -> int:
    if era not in ERAS or half not in ('', '1', '2'):
        print(f'usage: sweep.py {"|".join(ERAS)} [1|2] (got {era!r} {half!r})')
        return 2
    started = time.monotonic()
    planted = {c.id for c in mutants.CASES if c.id.startswith('tpc-')}
    named = [o for _, _, o in SWEEP if isinstance(o, str)]
    problems = [f'{i}: named twice' for i in sorted({i for i in named if named.count(i) > 1})]
    skipped = [] if sys.platform == 'darwin' else sorted(MACOS_ONLY)
    ids = [i for i in named if i not in skipped]
    problems += [f'{i}: no such case in tests/mutants.py' for i in ids if i not in planted]
    problems += [f'{i}: a case the sweep does not name' for i in sorted(planted - set(named))]
    equivalents = [o[2] for _, _, o in SWEEP if isinstance(o, tuple) and o[0] == EQUIVALENT]
    if problems or not ids or not equivalents:
        print('\n'.join(problems or ['the sweep names nothing']))
        return 1
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
    if skipped:
        print(f'skipped (macOS only): {" ".join(skipped)}')
    shown = len(equivalents) - len([f for f in failed if f.startswith('equivalent-')])
    print(f'{era}{" half " + half if half else ""}: {len(ids)} cases killed, {shown} of {len(equivalents)} '
          f'equivalents shown, in {time.monotonic() - started:.0f} s')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:3]) if len(sys.argv) in (2, 3) else main(''))
