# 00 — Digest: the decisions the briefs settle

Three briefs, 2026-11-09: [01](01-callers-and-contract.md) (every caller of `bin/sandbox.sh` and the
contracts a fix must keep), [02](02-sibling-stops.md) (what the sibling cycles' stops reach and
assume), [03](03-detach-primitives.md) (detach primitives on macOS and dash, measured). The planner's
prototype (a detached worktree, removed after the PLAN/TECH sign-off) settled what the briefs left
open; PLAN.md § 4 records it.

## Decisions

1. **A keeper, not a sweep.** The fix is a per-sandbox process that outlives a SIGKILL of the wrapper
   and removes the directory once the wrapper and its command have both ended (GOAL Q1). A sweep at
   the next start was ruled out at the GOAL gate.
2. **Detached by a double fork and a process group of its own, through perl's builtins.** `setsid(1)`
   is absent on macOS, `set -m` gives no new group under dash, `python3` is a Command Line Tools stub
   on a bare Mac, and `perl -MPOSIX` costs ~6 ms more a start than bare perl (03 § 1). perl ships with
   macOS and is Essential on Ubuntu (`perl-base`); the keeper uses builtins only (`fork`, `setpgrp`,
   `pipe`, `kill`, `select`, `exec`). Without perl on `PATH` the wrapper behaves as on develop.
   A new group is enough: the sibling's stop follows parent and group links and never reads sessions
   (02 § 1).
3. **The keeper makes the directory.** A wrapper that makes it before the keeper has left the group
   leaks it to a kill in the first ~5–18 ms (15/100 and 14/100 in 03 § 7). Made by the keeper after it
   has left, and only after a `ready`/`go` exchange with the running wrapper, a kill at any moment
   either finds no directory or reaches a keeper that is out of reach; the exchange also covers a
   stop that froze the wrapper and saw the keeper still inside the run (prototype, PLAN § 4).
4. **Pipes, not FIFOs.** Brief 03 used FIFOs inside the directory; the prototype instead re-runs the
   script once under perl, which opens two anonymous pipes before it execs the shell again. Nothing
   appears in `HOME`, nothing can block on a FIFO open (03 § "Key findings": an orphan blocked 17 min
   on one), and the wrapper's death is the end of file on a pipe only it holds.
5. **The command's pid comes from a perl shim that reports it and `exec`s the command.** The keeper
   must know when the command has ended after the wrapper has gone (wrapper killed alone, 01 group A).
   The shim keeps the command the wrapper's child and holds nothing of the caller's once it has become
   the command. When `exec` fails, the shim hands the command to `/bin/sh -c '"$@"'`, so the shell's
   own status and message come out (a `/bin/sh` shim's failed `exec` changes them, 03 § 7 and the
   prototype). Builtins and missing commands run in the wrapper as on develop. A shim that ran the
   command without `exec` held the caller's descriptors for the command's life (the prototype's gate,
   pipes scenario), and was dropped.
6. **Zombies and polls.** `kill -0` answers for a zombie (03 § 4). The keeper waits on pids only after
   the wrapper has gone, so its pids are orphans that launchd or init reaps within ~1 ms; on Linux it
   also reads `/proc/<pid>/stat`. Polls back off from 5 ms to 0.1 s (03 § 6: the fixed-interval tail is
   one interval). The wrapper never waits for the keeper while its own child may be unreaped (the
   prototype deadlocked on bash-sh's fatal-signal exit trap until this rule).
7. **No pipe reaches the command or the caller.** The command gets none of the keeper's pipes (a
   background job holding one held removal off 2.8 s, 03 § 3); the keeper keeps none of the caller's
   descriptors (01 § 2: EOF waiters in groups A, C and F are unbounded).
8. **Sibling cycles.** `mutant-child-outlives-timeout`'s stop does not reach the keeper (02 § 1); its
   integration row asserts nothing about sandbox homes, so its outcome is unchanged (02 § 3). Several
   of its sentences say the home stays; they become stale when this lands (02 § 3), which is that
   cycle's text. `tests/mutants.py` is observed only.

## Contradictions resolved

- 03 recommends FIFOs in the directory with a 1 s `alarm`; the prototype's pipes need neither (4).
- 03 keeps the command the wrapper's child through a `/bin/sh` `exec` shim and reports an R7 status
  change on a failed exec; the plan's shim is perl, with a `/bin/sh` fallback for a failed exec (5,
  PLAN § 3 D3).
- 02 notes the GOAL's Clarification says the sibling's build does not rewrite the seed sentence,
  while the sibling's PLAN schedules a rewrite. This cycle does not edit the seed; the foreman owns
  the order (PLAN § 5).
