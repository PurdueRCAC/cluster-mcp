---
status: unshaped
kind: feature
appetite: big
lane: public
---

# Rails on `run_command` that steer a command toward the tool that fits

## Problem

Once 0.3.0 has built the bespoke families, an agent with a shell can still ignore them. A recursive
`find`, `du` or `ls -R` over a parallel-filesystem root is the long metadata walk login-node rules
forbid; a bare `module load` is gone by the next call, since each call is a fresh shell; an
interactive program with no TTY hangs until the timeout; and a loop of hundreds of `sbatch` calls
floods the scheduler when one many-task submission would do. The site's `/etc/agents.d` text says
so, and the agent reads it or doesn't. `run_command` itself knows nothing about what it runs.

## Why it was deferred

Steering needs the tools it steers toward. It was first sketched in `issues/tool-surface.md` and
moved here, to 0.4.0, once the families exist (0.3.0). **Pre-existing:** `run_command` has run
every command unexamined since the first release.

## Outcome / vision

`run_command` parses each command with `shlex` into argv per pipeline segment and checks it against
a short policy. A match returns an actionable note naming the right tool or form:

- a recursive walk over a filesystem root → the file family's bounded find, or the index
  (`issues/files-extra.md`, `issues/files-xdu-extra.md`);
- a bare `module load` → the `modules` parameter (`issues/modules-interface.md`);
- an interactive program with no TTY → it would hang;
- many `sbatch` calls in one command → HyperShell's `hs submit`, which runs many tasks under one
  submission.

Very little is refused outright (as first sketched: a recursive delete or `chmod` of a home, scratch
or project root, fork-bomb shapes, and `sudo`, which can't prompt; shaping decides the list). A command that does not parse runs unsteered. **Rules are site-extensible**: a site's extra
adds its own, so a center's policy lives beside its tools.

The docs say plainly what this is: **a net for a cooperative agent's mistakes, not a security
boundary.** The boundary is the Unix account.

## Sketch of the acceptance criteria

- **R1** — WHEN a command matches a steering rule, `run_command` SHALL return a note naming the
  preferred tool or form, and SHALL say whether the command ran.
- **R2** — WHEN a command does not parse, `run_command` SHALL run it unsteered.
- **R3** — A site extra SHALL be able to add rules without editing the shell member.
- **R4** — WHEN a command submits many batch jobs, the note SHALL name `hs submit` as the form that
  submits them as one.
- **R5** — The docs and `run_command`'s description SHALL state that the rails are not a security
  boundary.

## Notes

- Open for shaping: which matches only note and which refuse; how a rule names a tool the server
  does not serve (the instructions follow what loaded); whether the "many `sbatch`" rule counts
  calls in one command only or across a session (the second needs state the server keeps).
- The HyperShell rule steers toward a command, not a tool: a HyperShell capability
  (`issues/hypershell-capability.md`) is unordered and need not exist first.
- Related: `issues/shell-extra.md` (the member the rails live in), `issues/tool-surface.md` (where
  this was first sketched), `issues/observability-audit.md` (0.4.0's other half).
- Found by: roadmap revision, 2026-10-16 (inside `tool-surface`); split out 2026-11-09 (out of
  cycle).
