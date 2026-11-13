---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A signal to the mutation runner during a case's cleanup cuts the cleanup short

## Problem

`tests/mutants.py` cleans up after each case on the way out of `run_case`: `case_scratch` reopens
directories a stopped test left closed, lists the processes when a sandbox directory is left in the
case's scratch, puts the runner's `TMPDIR` back, and removes the scratch (or keeps it, named on
stderr, when a sandbox directory in it is still in use, the processes cannot be listed, or it cannot
all be removed). The cleanup holds no signal, and the signals the runner acts on are not errors it
catches: a SIGTERM or SIGHUP raises `RunnerSignal` where it lands and a Ctrl-C raises
`KeyboardInterrupt`, both `BaseException`s, while `case_scratch` catches only `Exception`.

So any SIGTERM, SIGHUP or SIGINT that arrives while a case's cleanup runs, first or second, raises
inside it, and the cleanup stops where it is. Two paths reach it:

- a second signal after a stop: the first one stopped the run (`stop_run` holds `HELD_SIGNALS` while
  it stops, then `run_child` re-raises through `case_scratch`), and the second lands in the cleanup;
- a single signal that lands during the cleanup of a case whose child ended on its own: no stop ran
  and nothing was held.

Either way:

- the case is never reported: on the single-signal path its verdict was already computed, and the
  signal replaces `run_case`'s return before `main` prints it;
- the scratch stays in the runner's `TMPDIR`, partly or wholly, with the sandbox directories and the
  child pytest's temporary directory in it, and nothing names it on stderr;
- a signal during the process listing (on macOS, `lsof` and `ps` launched through `bin/sandbox.sh`)
  ends that `subprocess.run`, which kills its child with SIGKILL on the way out, so the listing
  sandbox's trap never runs and its own directory stays in the scratch too;
- `TMPDIR` is put back on most paths (the listing step restores it in a `finally`), but not on a
  signal that lands just before or during the restore itself.

The runner still ends by the signal it got. Review cycle 2 of `sandbox-dirs-left-on-kill` showed the
single-signal path: one SIGTERM, sent as the cleanup's listing sandbox appeared in the scratch of a
case whose child had ended on its own, ended the runner with -15, printed no line for the case, named
nothing on stderr, and left the scratch with four sandbox directories: three at its top, the
listing's among them, and one in the child pytest's temporary directory
(`spec/sandbox-dirs-left-on-kill/REVIEW.md`, review cycle 2, F-B).

Pre-existing in kind: the scratch was a `tempfile.TemporaryDirectory` before
`sandbox-dirs-left-on-kill`, whose cleanup a signal landing in it, first or second, cut short in the
same way, with the case unreported and the scratch left. That cycle added one step to the cleanup,
the process listing, which runs only when a sandbox directory is left in the scratch; it lengthens
the window, and when it is cut short it leaves the listing's own sandbox directory.

## Why it was deferred

Out of `sandbox-dirs-left-on-kill`'s scope: its GOAL covers a runner that runs to its end and leaves
a run that is itself killed as a known limitation, and a signal that ends the runner during a case's
cleanup is one way it does not run to its end. Ruled a seed by the foreman at that cycle's P2 gate,
2026-11-12, for a second signal; widened to any signal by that cycle's review, cycle 2 (F-B), on the
maintainer's ruling, 2026-11-12.

## Outcome / vision

A SIGTERM, SIGHUP or SIGINT to the runner that arrives during a case's cleanup, first or second, does
not stop the cleanup part-way: a case whose child ended is reported, the scratch is removed (or kept
and named, on the rules `case_scratch` already follows), the process listing leaves no sandbox
directory of its own, `TMPDIR` is put back, and the runner then ends by the signal it got, as it does
today.

## Sketch of the acceptance criteria

- **R1** — WHEN the runner gets a SIGTERM, SIGHUP or SIGINT while a case's cleanup runs, whether or
  not a stop came before it, the cleanup SHALL finish before the runner acts on that signal, no
  sandbox directory (the process listing's own included) or case scratch the cleanup would have
  removed SHALL be left, and a scratch it keeps SHALL be named on stderr.
- **R2** — WHEN that case's child ended on its own, the case SHALL be reported before the runner
  ends.
- **R3** — The runner SHALL still end by the signal it got, with the exit `die_by` (TERM, HUP) or
  Python (Ctrl-C) gives it today, and no timing figure (`LIMIT`, `GONE_WITHIN`, `GONE_POLL`) SHALL
  change.

## Notes

- A hold like `stop_run`'s (`HELD_SIGNALS` blocked with `pthread_sigmask`) is one shape; the process
  listing it would cover starts processes, which inherit the blocked mask.
- Related: `issues/mutant-runner-stop-pins.md` (the stop path's deeper pins);
  `spec/sandbox-dirs-left-on-kill/` (TECH, P2 and P3 amendments; `remediation/runner-signals.py`
  drives one signal per row; REVIEW cycle 2, F-B, the single-signal path).
- Found by: `sandbox-dirs-left-on-kill`, P2 build (2026-11-12); its whole domain by that cycle's
  review, cycle 2 (2026-11-12).
