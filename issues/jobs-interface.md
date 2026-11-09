---
status: unshaped
kind: feature
appetite: big
lane: public
---

# An abstract `job_*` interface a scheduler extra implements

## Problem

The job tools are Slurm's command-line programs, one tool each (`sbatch`, `squeue`, `scancel`,
`sacct`, `sinfo`, `scontrol_show_job`), plus Purdue wrappers. An agent that learns them has learned
Slurm, not "submit a job, watch it, read its output". A cluster running PBS or Flux would need a
second set of tools with other names and other shapes, and every client permission, instruction
and habit built on the first set would not carry over. The project's direction is any HPC cluster,
not necessarily Slurm (`AGENTS.md` § Direction).

## Why it was deferred

It reshapes a capability, so it is a 0.3.0 cycle, after `issues/core-extraction.md`. Its first
implementation is `[slurm]` (`issues/slurm-capability.md`), which carries the findings about what a
model naturally sends. **Pre-existing:** n/a — new work.

## Outcome / vision

The `job_*` family is defined once, as an interface: its tool names, parameters, result shapes,
annotations and error forms. A scheduler extra implements it; `[slurm]` is the first. The interface
is written so that a second implementation (PBS, Flux) is a contribution — one member, no core edit
and no change to the interface — not a redesign. This project documents how to write one and does
not build it.

The sketch from `issues/slurm-capability.md` is the starting surface: submit, list, history, one
consolidated info view, output, cancel, and a bounded wait considered. Parameters accept what a model
naturally sends (an int or a string, a scalar or a list), and errors say what to send instead. The
family follows `issues/tool-surface.md`'s rules.

## Sketch of the acceptance criteria

- **R1** — The interface SHALL be defined in one place a scheduler member implements, naming each
  tool, its parameters and its result shape.
- **R2** — WHERE exactly one scheduler implementation is installed and probed, the server SHALL serve
  the `job_*` family through it; WHERE none is, no `job_*` tool SHALL be served.
- **R3** — The docs SHALL describe what a second scheduler implementation provides, in enough
  detail that adding one touches no core module and no other member.
- **R4** — Every `job_*` tool SHALL carry the same name, parameters and annotations whichever
  implementation serves it.

## Notes

- Open for shaping: what happens when two scheduler implementations are installed (a conflict like
  `[files]` and `[files-xdu]`, or a choice at startup); where scheduler-specific views (`sinfo`, node
  details) sit, inside the interface or beside it in the implementation.
- Large trees are indexed through this interface (`issues/files-xdu-extra.md`), so it comes before
  that cycle.
- Related: `issues/slurm-capability.md`, `issues/tool-surface.md`, `issues/modules-interface.md`
  (the `modules` parameter on submit), `issues/site-interfaces.md` (the same pattern for site tools).
- Found by: roadmap revision, 2026-11-09 (out of cycle).
