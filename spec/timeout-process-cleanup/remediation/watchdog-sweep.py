"""Review cycle 2, F2, F3, F1 and F4, and F5: every alternative of the stop's decisions is planted and
killed, in one protocol era: the watchdog that sends KILL alone (F2), the program's TERM default taken
back before the fork and the deadline's check (F3), the prologue's undoing of shadowed builtins (F1,
F4), and `_signal`'s wait for a key exchange (F5).

    uv run python -I spec/timeout-process-cleanup/remediation/watchdog-sweep.py legacy [1|2]
    uv run python -I spec/timeout-process-cleanup/remediation/watchdog-sweep.py modern [1|2]

Run from the worktree root, once per era, whole or in two halves (each half stays under a 10-minute
command cap; the second half also runs the equivalents).

It supersedes cycle 1's `F1-F2-stop-sweep.py`, which stays as the record: that table plants the
watchdog's TERM, its ignore around the fork and its unset of the functions over its paths, all
retired by review cycle 2 (F2: the watchdog's TERM was a second TERM; F3: a TERM in the fork was
lost; F1: the unset moved to the prologue, under posix mode). Its runner is kept below; the table is
this cycle's.

`SWEEP` is the coverage: each decision of the watchdog (its place, its statements' order, the TERM
default taken back before the fork, its own TERM ignore, its open, descriptor and streams, its wait
and trigger, its arming and release, its one signal, group and delay), the prologue's posix-mode
unset, its re-enabling of builtins and its unset of the functions named like its paths, the
deadline's check (its place, clock, comparison, refusal and value, and the backends that give it),
the job-control reset, and over `ssh` the KILL request, its guard, `_signal`'s open-channel check
under the channel's lock and its wait for a key exchange, with every alternative it could take and
what became of it:

- a case id: a `tests/mutants.py` case plants it, and must be killed (its targets and `why` are the
  case's own);
- `EQUIVALENT`: the same behaviour by every row that could tell; planted here and run against the
  rows that kill its neighbours, which must all pass, so the claim is shown, not argued;
- `NOT_PLANTED`: a reason it cannot be run here.

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

M = mutants
SSH = 'core/executor/ssh.py'


def case(case_id: str) -> Case:
    return next(c for c in mutants.CASES if c.id == case_id)


def survivor(name: str, edits: tuple[tuple[str, str], ...], targets: tuple[str, ...],
             file: str = mutants.LAUNCH) -> Case:
    """An equivalent alternative, planted with the rows that kill its neighbours (all must pass)."""
    return Case(f'equivalent-{name}', file, edits, targets, '')


def edits_of(case_id: str) -> tuple[tuple[str, str], ...]:
    return case(case_id).edits


GUARD_ROWS = (M.KILL_DRAINS, M.KILL_ORDER, M.BASHRC_UNDONE, M.HANGING_LOGIN, M.CONNECTION_KEPT)
IGNORERS = M.stopped('local-ignores-none', 'delegate-root-ignores-none')
LATE_ROWS = M.LATE_STARTS + M.JOBS_KEPT[:1]

SWEEP: list[tuple[str, str, object]] = [
    # The watchdog started, right after the prologue.
    ('watchdog started', 'dropped', 'tpc-watchdog-dropped'),
    *(('watchdog started', f'placed {place}', f'tpc-watchdog-{place}')
      for place in ('before-prologue', 'after-check', 'after-sentinel', 'in-subshell-first', 'in-subshell-last',
                    'after-subshell', 'after-status', 'after-record', 'after-release', 'after-reraise')),
    # Its line's three statements: TERM's default back, fork, arm.
    *(('watchdog statement order', ', '.join(order), f'tpc-watchdog-order-{"-".join(order)}')
      for order in M.statement_orders()),
    # TERM's default taken back before the fork, which undoes a startup file's TERM trap or ignore.
    ('TERM default before the fork', 'dropped', 'tpc-restore-dropped'),
    ('TERM default before the fork', 'INT restored instead', 'tpc-restore-int'),
    ('TERM default before the fork', 'HUP restored instead', 'tpc-restore-hup'),
    ('TERM default before the fork', 'TERM ignored in the program while it forks (cycle 1)',
     'tpc-ignore-in-program-at-fork'),
    ('TERM default before the fork', 'a handler around the fork, re-raised after the arming',
     (NOT_PLANTED, 'the same outcome for the command, which has not started: the program dies at the TERM either '
                   'way, the handler only defers it past the arming (the fork-window rows show the TERM kept); '
                   'it would add a state a startup file\'s variable could preset')),
    # The watchdog's own TERM ignore, its first statement.
    ('watchdog TERM ignore', 'dropped', 'tpc-child-ignore-dropped'),
    ('watchdog TERM ignore', 'INT ignored instead', 'tpc-child-ignore-int'),
    ('watchdog TERM ignore', 'HUP ignored instead', 'tpc-child-ignore-hup'),
    ('watchdog TERM ignore', 'after its wait (before the stop)', 'tpc-child-ignore-after-wait'),
    ('watchdog TERM ignore', 'after its stream redirection',
     (EQUIVALENT, 'one statement later, before anything waits: the deadline\'s TERM comes after the arming, and '
                  'the program is still forking until the ignore has run either way',
      survivor('child-ignore-after-quiet',
               ((M.CHILD_IGNORE + ' 2>&1; ', "TERM; exec 46>| >(exec >/dev/null 2>&1; trap '' TERM; "),),
               IGNORERS + M.JOBS_KEPT[:1]))),
    ('watchdog TERM ignore', 'any other catchable name ignored instead',
     (NOT_PLANTED, 'the same class as INT and HUP: the watchdog is then not TERM-proof, which only the name TERM '
                   'decides')),
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
     (EQUIVALENT, '`cat` ends only at the pipe\'s end or by a signal; the watchdog ignores TERM, which `cat` '
                  'inherits, and a KILL to the group ends the watchdog\'s own shell too; the guard keeps a `cat` '
                  'killed alone from reading as the program\'s death',
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
      for place in ('before-prologue', 'before-watchdog', 'after-watchdog', 'after-check', 'in-subshell-first',
                    'in-subshell-last', 'after-subshell', 'after-status')),
    ('release', 'placed before the command (after the sentinel)', 'tpc-release-before-command'),
    ('release', 'placed after the re-raise', 'tpc-release-after-reraise'),
    ('release', 'another byte than the newline, text', 'tpc-release-unterminated'),
    ('release', 'another byte than the newline',
     (EQUIVALENT, 'any second byte makes what the wait reads other than the arming line alone; '
                  '`tpc-release-unterminated` is the launch checker pinning the text',
      survivor('release-other-byte', edits_of('tpc-release-unterminated'), M.JOBS_KEPT + M.NOTHING_STOPPED[:1]))),
    ('release', 'written with `echo`', 'tpc-release-echo'),
    # The stop: KILL alone, GRACE after the program's death, to group 0.
    ('signal', 'dropped', 'tpc-kill-dropped'),
    *(('signal', f'{name} for KILL', f'tpc-kill-{name.lower()}') for name in ('TERM', 'HUP', 'STOP')),
    ('signal', 'any other name for KILL',
     (NOT_PLANTED, 'the ignoring shapes ignore every catchable terminating signal (the TERM and HUP class); '
                   'a non-terminating one ends nothing (the STOP class)')),
    ('signal', 'a TERM first, then GRACE, then KILL (cycle 1): under a non-root server', 'tpc-term-first'),
    ('signal', 'a TERM first, then GRACE, then KILL (cycle 1): a second TERM', 'tpc-term-first-grace'),
    ('signal', 'a TERM after GRACE, just before the KILL',
     (NOT_PLANTED, 'the KILL follows in the same breath, so the TERM reaches a handler only in the microseconds '
                   'before the KILL lands, which no row can time (planted, it survived the non-root row: the '
                   'handler never ran); the TERMs that leave a handler time to act, before the grace, are killed')),
    ('signal', 'a TERM after the KILL',
     (EQUIVALENT, 'the watchdog is in the group it KILLs, so nothing of it runs after its KILL',
      survivor('term-after-kill', ((M.STOP, '{{ /bin/sleep {grace}; kill -s KILL 0; kill -s TERM 0; }}'),),
               M.NON_ROOT + M.GRACE_KEPT[:1]))),
    ('target', '`$$` (the program, dead by then)', 'tpc-group-self'),
    ('target', '`-$$` (the program\'s group, which it leads but under a root server\'s `sudo`)', 'tpc-group-leader'),
    ('target', '`-1` or `$PPID`',
     (NOT_PLANTED, 'they signal outside the command (every process of the user, or the server, here the test '
                   'runner), so no child can run them safely; the launch checker pins `0`')),
    ('delay', '0 (rows where the TERM reached the group)', 'tpc-delay-zero'),
    ('delay', '0 (under a non-root server)', 'tpc-delay-zero-non-root'),
    ('delay', '2 × GRACE', 'tpc-delay-doubled'),
    ('delay', 'GRACE / 2', 'tpc-delay-halved'),
    ('delay', 'a fixed 1', 'tpc-delay-fixed'),
    ('delay', 'a fixed 1, behaviour',
     (EQUIVALENT, 'the same program while GRACE is 1; `tpc-delay-fixed` is the text row that renders GRACE 2.5',
      survivor('delay-fixed', edits_of('tpc-delay-fixed'), M.GRACE_KEPT + M.NON_ROOT))),
    ('sleep', '`sleep` (a profile function)', 'tpc-plain-sleep'),
    ('sleep', '`command sleep` (PATH)', 'tpc-command-sleep'),
    ('sleep', 'another absolute path (`/usr/bin/sleep`)',
     (NOT_PLANTED, 'equivalent where that file is a sleep (merged-/usr Linux); absent on macOS, where it is the '
                   'zero delay `tpc-delay-zero` plants')),
    # The prologue's job-control reset.
    ('prologue `m`', 'dropped', 'tpc-monitor-kept'),
    # The prologue's undoing of what a startup file shadows.
    ('posix-mode unset', 'out of posix mode (a function named `unset` runs)', 'tpc-posix-dropped'),
    ('posix-mode unset', 'the functions over the builtins kept', 'tpc-builtins-unset-dropped'),
    ('builtins enabled', 'dropped (`unset` stays off)', 'tpc-enable-dropped'),
    ('builtins enabled', 'dropped (`trap` stays off)', 'tpc-enable-dropped-trap'),
    ('builtins enabled', 'a function named `enable` kept', 'tpc-enable-function-kept'),
    ('builtins enabled', 'without `|| :`',
     (EQUIVALENT, '`enable` fails only for a name this bash has no builtin for, and every name is a builtin of '
                  'bash 3.2 and later',
      survivor('enable-unguarded', ((M.POSIX_ON, M.POSIX_ON.replace(' || :; ', '; ')),),
               M.UNSET_SHADOWED + M.TRAP_SHADOWED[:1]))),
    ('builtins listed', 'without `unset`', 'tpc-builtins-without-unset'),
    ('builtins listed', 'without `unalias`',
     (EQUIVALENT, 'on bash 3.2 (measured) leaving posix mode turns alias expansion off whatever a profile set, '
                  'so no alias reaches a later line; a bash that restores the profile\'s setting there (not run '
                  'here) would keep an alias over the watchdog\'s `kill` beside a function named `unalias`, which '
                  'the kill-alias row then shows',
      survivor('builtins-without-unalias', ((M.BUILTIN_NAMES, M.BUILTIN_NAMES.replace(' unalias', '')),),
               M.KILL_ALIASED + M.TRAP_SHADOWED[:1]))),
    ('builtins listed', 'without `trap`', 'tpc-builtins-without-trap'),
    ('builtins listed', 'without any other name',
     (NOT_PLANTED, 'cycle 1\'s list, pinned name by name by `test_profile_cannot_hijack_the_prologue` where a '
                   'profile can shadow it (`prologue-read-function-kept` and its kin); the three above are the names '
                   'this cycle added or the watchdog needs')),
    ('aliases dropped again', 'dropped (a function named `unalias` kept the profile\'s aliases)',
     (EQUIVALENT, 'the `unalias` class above: equivalent where leaving posix mode turns alias expansion off',
      survivor('aliases-kept', ((M.POSIX_ON, M.POSIX_ON.replace(' \\\\unalias -a; ', ' ')),), M.KILL_ALIASED))),
    ('posix mode left', 'kept (bash 3.2 has no process substitution in it)', 'tpc-posix-kept'),
    ('path functions unset', 'dropped', 'tpc-paths-unset-dropped'),
    ('path functions unset', 'without `/bin/cat`', 'tpc-paths-without-cat'),
    ('path functions unset', 'without `/bin/sleep`', 'tpc-paths-without-sleep'),
    ('path functions unset', 'without `/bin/date`', 'tpc-paths-without-date'),
    ('path functions unset', 'in posix mode (refused there)', 'tpc-paths-unset-in-posix-mode'),
    ('path functions unset', 'without `-f` (a name that is no variable is refused)', 'tpc-paths-not-functions'),
    ('shadowing undone', 'a readonly function, a function named `enable` beside a disabled `unset`, `enable -n '
                         'enable`, aliases on the prologue\'s own second line',
     (NOT_PLANTED, 'the recorded limit, not a decision: nothing the program runs can undo them; '
                   '`test_a_recorded_limit[shadowed-*]` shows the stop failing and a command cut short')),
    # The deadline's check, right after the watchdog, where the program runs on the server's host.
    ('deadline check', 'dropped', 'tpc-check-dropped'),
    *(('deadline check', f'placed {place}', f'tpc-check-{place}')
      for place in ('before-prologue', 'before-watchdog', 'after-sentinel', 'in-subshell-first', 'in-subshell-last',
                    'after-subshell', 'after-status', 'after-record', 'after-release', 'after-reraise')),
    ('deadline check', 'not given under `delegate`', 'tpc-check-not-given-delegate'),
    ('deadline check', 'not given in `local`', 'tpc-check-not-given-local'),
    ('deadline check', 'given over `ssh`',
     (NOT_PLANTED, 'the remote host\'s clock is not the server\'s; over `ssh` the KILL request after the grace '
                   'stops a command that starts late (`test_a_command_past_its_deadline_is_stopped[ssh-bash]`)')),
    ('clock', 'seconds (`+%s`)', 'tpc-clock-seconds'),
    ('clock', '`date` (a profile function)', 'tpc-clock-plain-date'),
    ('clock', 'without the seconds-only fallback',
     (EQUIVALENT, 'it differs only where `date` cannot print nanoseconds (here and on CI\'s GNU `date` it can)',
      survivor('clock-no-fallback', ((M.FALLBACK, "''"),), LATE_ROWS))),
    ('clock', 'without the guard on an unreadable clock',
     (EQUIVALENT, 'it differs only where `date` prints no number: arithmetic on it fails, and every call would be '
                  'refused',
      survivor('clock-unguarded', ((M.COMPARED, '''"case $cluster_mcp_n in *) (( cluster_mcp_n < {deadline} )) || "'''),),
               LATE_ROWS))),
    ('comparison', 'inverted', 'tpc-check-inverted'),
    ('comparison', 'always refuses', 'tpc-check-always-refuses'),
    ('comparison', 'never refuses', 'tpc-check-never-refuses'),
    ('comparison', '`<=` for `<`',
     (EQUIVALENT, 'one nanosecond apart',
      survivor('check-at-deadline', ((M.COMPARED, M.COMPARED.replace(' < {deadline}', ' <= {deadline}')),),
               LATE_ROWS))),
    ('refusal', 'the command starts after the wait', 'tpc-refusal-lives-on'),
    ('refusal', 'the wait doubled', 'tpc-refusal-wait-doubled'),
    ('refusal', 'no wait for the server\'s TERM',
     (EQUIVALENT, 'it differs only when the program reads the clock in the instant between its deadline and the '
                  'server\'s, which no row can time: the call would then end as a launch that died, not a timeout',
      survivor('refusal-at-once', ((M.REFUSED, "'{{ kill -s TERM $$; kill -s KILL $$; }} ;; esac')"),),
               M.LATE_STARTS))),
    ('refusal', 'no KILL after the TERM',
     (EQUIVALENT, 'it differs only for a program that started with TERM ignored, which no setting launches',
      survivor('refusal-term-only', ((M.REFUSED, "'{{ /bin/sleep {grace}; kill -s TERM $$; }} ;; esac')"),),
               M.LATE_STARTS))),
    ('refusal', 'TERM to the group',
     (EQUIVALENT, 'the program dies of it as of its own, the watchdog ignores it, and the command never started',
      survivor('refusal-group', ((M.REFUSED, "'{{ /bin/sleep {grace}; kill -s TERM 0; kill -s KILL $$; }} ;; esac')"),),
               M.LATE_STARTS))),
    ('deadline value', 'now', 'tpc-deadline-now'),
    ('deadline value', 'a second early', 'tpc-deadline-a-second-early'),
    ('deadline value', 'a second late', 'tpc-deadline-a-second-late'),
    ('deadline value', 'in seconds', 'tpc-deadline-seconds'),
    ('deadline value', 'taken after the server\'s own',
     (NOT_PLANTED, 'the program is rendered before `run_process` starts and takes its deadline; a later program '
                   'deadline is the `tpc-deadline-a-second-late` class')),
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
    # `_signal`: nothing on a closed channel, checked and sent holding the channel's lock, and only once a
    # key exchange has ended.
    ('open-channel check', 'dropped', 'tpc-ssh-signal-unchecked'),
    ('open-channel check', '`not chan.active` for `chan.closed`', 'tpc-ssh-signal-active-checked'),
    ('open-channel check', 'without the channel\'s lock', 'tpc-ssh-signal-unlocked'),
    ('open-channel check', 'checked under the lock, sent after it', 'tpc-ssh-signal-checked-then-sent'),
    ('key-exchange wait', 'dropped, with its check (sent under the channel\'s lock only)',
     'tpc-ssh-signal-no-key-exchange-wait'),
    ('key-exchange wait', 'its check dropped (sent once the wait times out)', 'tpc-ssh-signal-key-exchange-unchecked'),
    ('key-exchange wait', 'made holding the channel\'s lock', 'tpc-ssh-signal-wait-locked'),
    ('key-exchange wait', 'Paramiko\'s `_send_user_message`, the channel\'s lock held', 'tpc-ssh-signal-user-message'),
    ('key-exchange wait', 'unbounded', 'tpc-ssh-signal-unbounded'),
    ('key-exchange wait', 'on a transport that has gone', 'tpc-ssh-signal-transport-unchecked'),
    ('key-exchange wait', 'the check and send without the transport\'s `clear_to_send_lock`',
     (NOT_PLANTED, 'a race between the check and the transport thread clearing the flag as an exchange starts, '
                   'which no row can time; Paramiko\'s own sends take that lock for the same reason')),
]

# On macOS only (bash 3.2 tells `>` from `>|`).
MACOS_ONLY = {'tpc-clobber'}


def main(era: str, half: str = '') -> int:
    if era not in ERAS or half not in ('', '1', '2'):
        print(f'usage: watchdog-sweep.py {"|".join(ERAS)} [1|2] (got {era!r} {half!r})')
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
