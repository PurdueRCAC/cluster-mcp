---
status: unshaped
kind: feature
appetite: big
lane: public
---

# A HyperShell capability

## Problem

An agent with many small tasks to run on a cluster reaches for a loop of job submissions, which
floods the scheduler. [HyperShell](https://github.com/hypershell/hypershell) runs many tasks under
one submission (`hs submit` and its cluster mode), but nothing in this server knows about it beyond
the note `issues/shell-rails.md` plans to return.

## Why it was deferred

Filed as a placeholder so the roadmap can index it: it is after 0.3.0 and not yet ordered.
**Pre-existing:** n/a — new work.

## Outcome / vision

Unshaped. Plausibly a capability extra that serves task submission and status through HyperShell
where it is installed, following the interface pattern of `issues/jobs-interface.md`. Shaping
decides what it serves, whether it is an implementation of an interface or a family of its own,
and how it relates to the scheduler extras.

## Sketch of the acceptance criteria

- **R1** — WHERE the HyperShell capability is installed and HyperShell is present on the host, the
  server SHALL serve tools to submit a set of tasks as one submission and to read their status.

## Notes

- Related: `issues/shell-rails.md` (steers an `sbatch` flood toward `hs submit`),
  `issues/jobs-interface.md`.
- Found by: roadmap revision, 2026-11-09 (out of cycle).
