---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A second signal to the mutation runner can cut a case's cleanup short

## Problem

`tests/mutants.py` cleans up after each case on the way out of `run_case`: `case_scratch` puts the
runner's `TMPDIR` back, lists the processes when a sandbox directory is left in the case's scratch,
and removes the scratch (or keeps it, named on stderr, when a sandbox directory in it is still in use
or the processes cannot be listed). A SIGTERM, SIGHUP or SIGINT to the runner reaches that cleanup on
its way out: `stop_run` stops the run with those signals held (`HELD_SIGNALS`), then `run_child`
re-raises (`RunnerSignal`, `KeyboardInterrupt`) through `case_scratch`.

The cleanup itself holds no signal. A second SIGTERM, SIGHUP or Ctrl-C that arrives while it runs
(during the process listing, which launches `lsof` and `ps` through `bin/sandbox.sh` on macOS, or
during the removal) raises inside it, and the cleanup stops where it is: the scratch, with the
sandbox directories and the child pytest's temporary directory in it, stays partly or wholly in the
runner's `TMPDIR`, and `TMPDIR` may not have been put back before the runner ends.

Pre-existing: the scratch was a `tempfile.TemporaryDirectory` before `sandbox-dirs-left-on-kill`,
whose cleanup a second signal cut short in the same way. That cycle kept the behaviour as it was.

## Why it was deferred

Out of `sandbox-dirs-left-on-kill`'s scope: its GOAL covers a runner that runs to its end and leaves
a run that is itself killed as a known limitation, and its change to the cleanup kept the old
exposure to a second signal rather than adding one. Ruled a seed by the foreman at that cycle's P2
gate, 2026-11-12.

## Outcome / vision

A second SIGTERM, SIGHUP or SIGINT to the runner during a case's cleanup does not stop the cleanup
part-way: the scratch is removed (or kept and named, on the rules `case_scratch` already follows),
`TMPDIR` is put back, and the runner then ends by the signal it got, as it does today.

## Sketch of the acceptance criteria

- **R1** — WHEN the runner gets a SIGTERM, SIGHUP or SIGINT while a case's cleanup runs, the cleanup
  SHALL finish before the runner acts on that signal, and no sandbox directory or case scratch the
  cleanup would have removed SHALL be left.
- **R2** — The runner SHALL still end by the signal it got, with the exit `die_by` (TERM, HUP) or
  Python (Ctrl-C) gives it today, and no timing figure (`LIMIT`, `GONE_WITHIN`, `GONE_POLL`) SHALL
  change.

## Notes

- A hold like `stop_run`'s (`HELD_SIGNALS` blocked with `pthread_sigmask`) is one shape; the process
  listing it would cover starts processes, which inherit the blocked mask.
- Related: `issues/mutant-runner-stop-pins.md` (the stop path's deeper pins);
  `spec/sandbox-dirs-left-on-kill/` (TECH, P2 and P3 amendments; `remediation/runner-signals.py`
  drives one signal per row).
- Found by: `sandbox-dirs-left-on-kill`, P2 build (2026-11-12).
