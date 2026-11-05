"""Review cycle 3, B2, B3, B4, N1, N3 and B1's return pin, and the `kill-alias` row removed: every
alternative of the stop's decisions is planted and killed, in one protocol era, this remediation's
decisions with them: the TERM disposition the watchdog is forked with and the default taken back
after the fork (B3), the names the program unsets before its command (B2), `_signal`'s check and
send under the transport's `clear_to_send_lock` (B4), the program given no deadline over `ssh` (N1),
and `run`'s return within the bound (B1).

    uv run python -I spec/timeout-process-cleanup/remediation/watchdog-and-hygiene-sweep.py legacy [1|2|3|4]
    uv run python -I spec/timeout-process-cleanup/remediation/watchdog-and-hygiene-sweep.py modern [1|2|3|4]

Run from the worktree root, once per era, whole or in four parts (each part stays under a
10-minute command cap; the fourth also runs the equivalents).

It supersedes review cycle 2's `watchdog-sweep.py`, which stays as the record: its table plants the
watchdog forked once TERM's default was back and ignoring TERM from its own first statement, the
design review cycle 3's B3 retired (the watchdog was born with TERM at its default), names the
`kill-alias` row the review found pins nothing, and leaves the key-exchange lock unplanted (B4). Its
runner is kept below; the table is this cycle's.

Review cycle 3 verification, N3: not reproduced. The posix-mode round trip changes the program's own
shell options but does not refresh `BASHOPTS`, so a bash the command starts gets the options the
login initialisation left (measured on bash 4.4, 5.1 and 5.2), and the options restore is removed.
Its decisions leave the table (the list saved, set back in the subshell, its names unset, `shopt`
among the builtins, and the `-behaviour` cases on bash 4.4 or later); what stays is a decision not
planted: the program refreshes no `BASHOPTS` before its command.

`SWEEP` is the coverage: each decision of the watchdog (its place, its statements' order, the TERM
disposition it is forked with and the default taken back after, its open, descriptor and streams,
its wait and trigger, its arming and release, its one signal, group and delay), the prologue's
posix-mode unset, its re-enabling of builtins and its unset of the functions named like its paths,
the `BASHOPTS` it never refreshes, the names the program unsets, the deadline's
check (its place, clock, comparison, refusal and value, and the backends that give it), the
job-control reset, `run`'s return within the bound, and over `ssh` the KILL request, its guard,
`_signal`'s open-channel check under the channel's lock, its wait for a key exchange and its check
and send under the transport's lock, with every alternative it could take and what became of it:

- a case id: a `tests/mutants.py` case plants it, and must be killed (its targets and `why` are the
  case's own);
- `EQUIVALENT`: the same behaviour by every row that could tell; planted here and run against the
  rows that kill its neighbours, which must all pass, so the claim is shown, not argued;
- `NOT_PLANTED`: a reason it cannot be run here.

The gate checks the table against `tests/mutants.py` both ways (every case it names exists, and
every `tpc-` case is named), runs every named case with `tests/mutants.py` in the era given (each
must be reported killed), then runs each equivalent (each must be reported as surviving, every
target passed). `tpc-clobber` exists on macOS only (bash 3.2): elsewhere it is skipped, and the gate
says so.

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
    # Its line's four statements: TERM ignored, fork, TERM's default back, arm.
    *(('watchdog statement order', ', '.join(order), f'tpc-watchdog-order-{"-".join(order)}')
      for order in M.statement_orders() if order != M.ORDER_EQUIVALENT),
    ('watchdog statement order', ', '.join(M.ORDER_EQUIVALENT),
     (EQUIVALENT, 'the window in which a TERM is lost spans the arming `printf` too; the deadline\'s check '
                  'covers it as it covers the fork, and over `ssh` the KILL request',
      survivor('order-arm-before-restore', M.reordered(M.ORDER_EQUIVALENT),
               M.PROGRAM_WINDOW + M.WATCHDOG_WINDOW[:1] + M.JOBS_KEPT[:1]))),
    # Forked with TERM ignored, so the watchdog is born ignoring it.
    ('TERM ignored at the fork', 'dropped', 'tpc-fork-ignore-dropped'),
    ('TERM ignored at the fork', 'INT ignored instead', 'tpc-fork-ignore-int'),
    ('TERM ignored at the fork', 'HUP ignored instead', 'tpc-fork-ignore-hup'),
    ('TERM ignored at the fork', 'TERM\'s default back before the fork, the watchdog ignoring TERM from its first '
                                 'statement (review cycle 2\'s line, review cycle 3\'s B3)', 'tpc-born-with-term'),
    ('TERM ignored at the fork', 'a handler around the fork, re-raised after it (bash resets it in the watchdog)',
     'tpc-handler-at-fork'),
    ('TERM ignored at the fork', 'and again by the watchdog, its first statement',
     (EQUIVALENT, 'the watchdog is born ignoring TERM, so ignoring it again changes nothing',
      survivor('fork-ignore-and-child-ignore', ((M.OPENED, "TERM; exec 46>| >(trap '' TERM; "),),
               M.WATCHDOG_WINDOW[:1] + IGNORERS + M.JOBS_KEPT[:1]))),
    ('TERM ignored at the fork', 'any other catchable name ignored instead',
     (NOT_PLANTED, 'the same class as INT and HUP: the watchdog is then born with TERM at its default, which only '
                   'the name TERM decides')),
    # TERM's default taken back right after the fork, which also undoes a startup file's TERM trap or ignore.
    ('TERM default after the fork', 'dropped', 'tpc-restore-dropped'),
    ('TERM default after the fork', 'INT restored instead', 'tpc-restore-int'),
    ('TERM default after the fork', 'HUP restored instead', 'tpc-restore-hup'),
    ('TERM default after the fork', 'after the arming',
     (NOT_PLANTED, 'the statement order `ignore, fork, arm, restore` above, planted there as an equivalent')),
    ('TERM default after the fork', 'after the deadline\'s check, on its line',
     (NOT_PLANTED, 'the window would span the check, and a TERM in the instant between the clock\'s reading and '
                   'the sentinel would be lost after the check passed, which no row can time; the default comes '
                   'back on the watchdog\'s own line, which the launch checker pins')),
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
     (EQUIVALENT, 'leaving posix mode turns alias expansion off for the program\'s own lines, on bash 3.2 '
                  '(measured) to 5.3 (read from its source by review cycle 3), and nothing in the program turns '
                  'it back on; so no alias beside a function named `unalias` reaches the watchdog\'s line (the '
                  '`kill-alias` row, which showed nothing on any of them, is removed)',
      survivor('builtins-without-unalias', ((M.BUILTIN_NAMES, M.BUILTIN_NAMES.replace(' unalias', '')),),
               M.TRAP_SHADOWED[:1] + M.UNSET_SHADOWED[:1]))),
    ('builtins listed', 'without `trap`', 'tpc-builtins-without-trap'),
    ('builtins listed', 'without any other name',
     (NOT_PLANTED, 'cycle 1\'s list, pinned name by name by `test_profile_cannot_hijack_the_prologue` where a '
                   'profile can shadow it (`prologue-read-function-kept` and its kin); the three above are the names '
                   'this cycle added or the watchdog needs')),
    ('aliases dropped again', 'dropped (a function named `unalias` kept the profile\'s aliases)',
     (EQUIVALENT, 'the `unalias` class above: leaving posix mode turns alias expansion off for the program\'s own '
                  'lines on bash 3.2 to 5.3; `tpc-aliases-kept-text` is the launch checker pinning the second reset',
      survivor('aliases-kept', ((M.POSIX_ON, M.POSIX_ON.replace(' \\\\unalias -a; ', ' ')),),
               M.TRAP_SHADOWED[:1] + M.UNSET_SHADOWED[:1]))),
    ('aliases dropped again', 'dropped, text', 'tpc-aliases-kept-text'),
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
    ('deadline check', 'given over `ssh` (a deadline taken before the connection is made)', 'tpc-ssh-deadline-given'),
    ('deadline check', 'dropped (a deadline\'s TERM lost while the program forks the watchdog)',
     'tpc-check-dropped-fork-window'),
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
      survivor('refusal-at-once', ((M.REFUSED, "'{{ kill -s TERM $$; kill -s KILL $$; }} ;; esac; unset cluster_mcp_n')"),),
               M.LATE_STARTS))),
    ('refusal', 'no KILL after the TERM',
     (EQUIVALENT, 'it differs only for a program that started with TERM ignored, which no setting launches',
      survivor('refusal-term-only', ((M.REFUSED, "'{{ /bin/sleep {grace}; kill -s TERM $$; }} ;; esac; unset cluster_mcp_n')"),),
               M.LATE_STARTS))),
    ('refusal', 'TERM to the group',
     (EQUIVALENT, 'the program dies of it as of its own, the watchdog ignores it, and the command never started',
      survivor('refusal-group', ((M.REFUSED, "'{{ /bin/sleep {grace}; kill -s TERM 0; kill -s KILL $$; }} ;; esac; unset cluster_mcp_n')"),),
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
     'tpc-ssh-signal-exchange-unlocked'),
    # No name the program sets reaches the command: each unset before it starts.
    ('names unset', 'the clock reading kept', 'tpc-clock-reading-kept'),
    ('names unset', 'the function export\'s name kept', 'tpc-function-name-kept'),
    ('names unset', 'allexport turned off instead (`set +a`), the names kept', 'tpc-allexport-off-instead'),
    ('names unset', 'the clock read inline, no name at all',
     (NOT_PLANTED, 'the same outcome for the command by another route; it would read the clock twice or lose the '
                   'seconds-only fallback, and the rows show a name kept, not how it is avoided')),
    # The shell options a command sees: the program refreshes no `BASHOPTS` (review cycle 3
    # verification, N3).
    ('BASHOPTS not refreshed', 'a `shopt` (or anything else that refreshes `BASHOPTS`) in the program before '
                               'the command',
     (NOT_PLANTED, 'it would hand the posix-mode round trip\'s options on; the row that shows it, '
                   '`test_a_command_sees_the_shell_options_its_profile_left`, exists only where the interpreter is '
                   'bash 4.4 or later (CI\'s), which this host is not, and the launch checker\'s fixed copy of the '
                   'program refuses any text added to it')),
    # `run` returns a timed-out call within 2 × GRACE: the drains, and over `ssh` the GRACE read, bound it.
    ('run\'s return', 'the `ssh` read after the TERM three times as long', 'tpc-return-grace-read-tripled'),
    ('run\'s return', '`run_process`\'s drains three times as long',
     (NOT_PLANTED, 'in `local` and `delegate` the watchdog or the deadline\'s check ends the output before the '
                   'drains do in every row of the suite; only a login initialisation that hangs ignoring TERM, a '
                   'recorded limit whose rows check no return, would show it')),
]

# On macOS only (bash 3.2 tells `>` from `>|`).
MACOS_ONLY = {'tpc-clobber'}


PARTS = ('1', '2', '3', '4')


def main(era: str, part: str = '') -> int:
    if era not in ERAS or part not in ('', *PARTS):
        print(f'usage: watchdog-and-hygiene-sweep.py {"|".join(ERAS)} [{"|".join(PARTS)}] (got {era!r} {part!r})')
        return 2
    started = time.monotonic()
    planted = {c.id for c in mutants.CASES if c.id.startswith('tpc-')}
    named = [o for _, _, o in SWEEP if isinstance(o, str)]
    problems = [f'{i}: named twice' for i in sorted({i for i in named if named.count(i) > 1})]
    skipped = sorted(set() if sys.platform == 'darwin' else MACOS_ONLY)
    ids = [i for i in named if i not in skipped]
    problems += [f'{i}: no such case in tests/mutants.py' for i in ids if i not in planted]
    problems += [f'{i}: a case the sweep does not name' for i in sorted(planted - set(named))]
    equivalents = [o[2] for _, _, o in SWEEP if isinstance(o, tuple) and o[0] == EQUIVALENT]
    if problems or not ids or not equivalents:
        print('\n'.join(problems or ['the sweep names nothing']))
        return 1
    if part:
        size = -(-len(ids) // len(PARTS))
        at = PARTS.index(part) * size
        ids = ids[at:at + size]
        equivalents = equivalents if part == PARTS[-1] else []
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
    print(f'{era}{" part " + part if part else ""}: {len(ids)} cases killed, {shown} of {len(equivalents)} '
          f'equivalents shown, in {time.monotonic() - started:.0f} s')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:3]) if len(sys.argv) in (2, 3) else main(''))
