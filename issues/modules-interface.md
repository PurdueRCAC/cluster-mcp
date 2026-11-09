---
status: unshaped
kind: feature
appetite: big
lane: public
---

# An abstract `module_*` interface a module-system extra implements

## Problem

On a cluster with a module system an agent cannot discover what software is installed, what
versions exist, or what loading a module would change, so it guesses, and the served instructions
compensate with prose that goes stale (`issues/lmod-tool-group.md` has the evidence). And module
state does not persist between calls: each call is a fresh shell, so a `module load` in one call is
gone by the next. LMOD is common, not universal: Tcl Environment Modules and other hierarchies
exist (`AGENTS.md` § Direction).

## Why it was deferred

It adds a capability family, so it is a 0.3.0 cycle, after `issues/core-extraction.md`. Its first
implementation is `[lmod]` (`issues/lmod-tool-group.md`). **Pre-existing:** n/a — new work.

## Outcome / vision

The `module_*` family is defined once, as an interface a module-system extra implements:

- **search** — what is installed, and what versions exist and what they require;
- **list** — what a call's environment has loaded;
- **show** — what loading a module would change;
- **modules loaded into a call's environment** — a `modules` parameter, on `run_command` and on job
  submission, that loads the listed modules in the same invocation, since state does not persist.

`[lmod]` is the first implementation. The interface is written so that a second one (Environment
Modules) is a contribution, not a redesign; this project documents how to write one and does not
build it. The family follows `issues/tool-surface.md`'s rules.

## Sketch of the acceptance criteria

- **R1** — The interface SHALL be defined in one place a module-system member implements, naming
  each tool, its parameters and its result shape.
- **R2** — WHERE a module-system implementation is installed and probed, the server SHALL serve the
  `module_*` family through it, and `run_command` and job submission SHALL accept `modules`.
- **R3** — WHEN a call passes `modules`, the listed modules SHALL be loaded in that call's
  environment before its command runs, and a module that fails to load SHALL fail the call, naming
  it.
- **R4** — The docs SHALL describe what a second implementation provides, in enough detail that
  adding one touches no core module and no other member.

## Notes

- Open for shaping: how `modules` reaches a tool another member serves (`run_command` in `[shell]`,
  submit in `[slurm]`) without that member depending on a module system; a shared parameter the core
  defines and an implementation fills is one shape.
- Related: `issues/lmod-tool-group.md`, `issues/jobs-interface.md`, `issues/shell-extra.md`,
  `issues/tool-surface.md`, `issues/shell-rails.md` (steers a bare `module load` here, 0.4.0).
- Found by: roadmap revision, 2026-11-09 (out of cycle).
