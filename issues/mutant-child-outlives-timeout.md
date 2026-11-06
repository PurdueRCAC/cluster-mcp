---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A mutant's child run outlives its timeout

## Problem

`tests/mutants.py`'s `run_child` runs a case's targets as `bin/sandbox.sh sh -c … python -m pytest …`
through `subprocess.run(..., timeout=300)`. When the timeout fires, `subprocess.run` kills the
process it started, the sandbox wrapper, and nothing below it: the child `sh` has `exec`ed pytest, and
that pytest is reparented to init and keeps running, holding its loopback servers, its silent hop and
its scratch copy until it ends by itself. The runner then raises `TimeoutExpired` out of `run_case`
rather than reporting the case as a failure, so a sweep stops at that case.

Seen on 2026-11-05: a case that hung its target for the full 300 s left its pytest running, parent
PID 1, more than seven minutes later, until it was killed by hand. The hang itself was a defect in
the mutated code, which is what a mutant is for; the runner's handling of it is the problem.

**Pre-existing:** yes, the timeout and its handling are on `develop`.

## Why it was deferred

Found by the `ssh-half-open-link` review cycle 2 remediation, whose scope is the liveness cap and the
hygiene check's id pattern. `tests/mutants.py`'s runner serves every cycle's sweep and the mutants
workflow, so a change to how it starts and stops children is a change of its own.

## Outcome / vision

A case whose child runs past its time limit leaves nothing running, and is reported as that case's
failure (a timeout), so a sweep goes on to its next case.

## Sketch of the acceptance criteria

- **R1** — WHEN a mutant's child run passes its time limit, the runner SHALL stop every process the
  run started (the child is started in a session of its own and its process group killed), and
  nothing of the run SHALL remain afterwards.
- **R2** — WHEN that happens, the runner SHALL report the case as not killed, naming the timeout,
  and go on to the next case.

## Notes

- Related: `issues/mutants-workflow-timeout.md` (the workflow's own 30-minute job);
  `spec/ssh-half-open-link/` (where it was seen).
- Found by: `ssh-half-open-link` review cycle 2 remediation, P1's cheap mutant pass.
