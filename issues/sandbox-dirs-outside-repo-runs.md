---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A sandbox killed outright where no run's cleanup runs leaves its directory

## Problem

`bin/sandbox.sh` makes its directory with `mktemp -d "${TMPDIR:-/tmp}/cluster-mcp-sandbox.XXXXXX"`
and removes it from a trap on `EXIT HUP INT TERM`. A SIGKILL skips the trap, so the directory stays:
the skeleton the script makes (`.config`, `.cache`, `.local/share`), sometimes with FastMCP's
`version_cache.json` or other files written under the sandbox's `HOME`.

`sandbox-dirs-left-on-kill` cleaned up after the repository's own runs: a pytest run points `TMPDIR`
at a directory of its own and sweeps it when the session ends (`tests/sandbox_dirs.py`, the
`sandbox_tmp` fixture), and the mutation runner makes each case's scratch its child run's `TMPDIR`
(`case_scratch`). It left `bin/sandbox.sh` byte-identical (its R5), so a caller outside those runs
still leaves a directory in two cases, each a non-goal of its GOAL.

**Case 1: a caller outside the repository's own runs** SIGKILLs the wrapper:

> **Callers outside the repository's own runs (known limitation).** A developer's shell, a cycle's
> `spec/*/verify/` gate script (such as `spec/agents-d-instructions/verify/serve_gate.py`, which
> SIGKILLs a sandboxed server), or any other ad hoc caller that kills a sandbox outright still leaves
> its directory, because `bin/sandbox.sh` is unchanged (R5). Earlier cycles' gate scripts are
> records and are not edited.

Such a caller is a person (a shell's `kill -9`, a terminal closed in a way that SIGKILLs the group)
or another tool (a gate script, an editor's task runner, a CI step cancelled outright). Each leftover
lands in that caller's `TMPDIR`, usually the host's, where nothing tells it from another run's.

**Case 2: the run itself is SIGKILLed** before its end, so its own cleanup never runs:

> **A run that is itself killed (known limitation).** If the pytest run or the mutation runner is
> killed before its end (SIGKILL, a cancelled CI job), its own cleanup does not run, and what its
> sandboxes made stays in the location the run gave them.

What stays is one directory per killed run in the `TMPDIR` the run was started with: a suite
session's `cluster-mcp-run.*` directory, or the mutation runner's current `mutant-<case>-*` scratch,
with the sandbox directories and the pytest temporary directories inside it. On a hosted CI runner
the machine is discarded; on a developer's host the directory stays.

**Case 3: a run directory kept for a sandbox still running at the session's end.** The suite's
session cleanup (`own_tmp` in `tests/sandbox_dirs.py`) keeps its `cluster-mcp-run.*` directory
while a sandbox directory in it is in use, as that cycle's GOAL asks (its R4 and the clarification on
the run's own directory). Nothing revisits it afterwards: once the sandbox's command ends, its trap
removes the sandbox's own directory and the run directory stays, empty, in the `TMPDIR` the run was
started with. Every run of the profile's `verify` leaves two this way, one from each era's third
suite command, where `tests/test_launch.py::test_a_local_end_record_split_across_reads_is_found`
leaves a sandbox running `sleep 8` at the session's end. Found by `sandbox-dirs-left-on-kill`'s
review, cycle 1, 2026-11-12; out of that cycle's scope, since its R1–R4 cover sandbox directories.

Pre-existing: the trap came in with the sandbox wrapper itself, before the factory; cases 2 and 3 are
the same exposure one level up, in the cleanup `sandbox-dirs-left-on-kill` added.

## Why it was deferred

`sandbox-dirs-left-on-kill`'s maintainer ruling (its GOAL, Q4, 2026-11-09) kept `bin/sandbox.sh`
unchanged and narrowed the contract to the repository's own runs; the first design, a keeper process
inside the wrapper, was rejected; a run's own cleanup cannot run after the run is SIGKILLed. Filed
as a seed on the foreman's rulings at that cycle's P3 ledger, 2026-11-12, so both known limitations
have a record beyond the GOAL and `AGENTS.md`'s sentence.

## Outcome / vision

A sandbox stopped outright by any caller leaves no directory behind, or what it leaves is found and
removed safely later, without removing another run's directory, one in use, or the leftovers a
developer chooses to keep.

## Sketch of the acceptance criteria

- **R1** — WHEN a caller outside the repository's own runs SIGKILLs `bin/sandbox.sh` (alone or with
  its process group), or a suite run or the mutation runner is SIGKILLed before its end, or a run
  keeps its directory for a sandbox still running at its end, what its sandboxes left SHALL be removed within a bound the maintainer sets, or SHALL be removable by a
  documented step that removes only directories no process uses.
- **R2** — No directory of another sandbox still in use, and nothing that is not a sandbox directory,
  SHALL be removed.
- **R3** — The throwaway-environment contract (`AGENTS.md` § Factory, Throwaway environment) SHALL
  hold as it does today.

## Notes

- **A sketch, not a decision:** a likely remedy for all three cases is clearing stale leftovers on the
  next start: a later suite run, mutation run or sandbox removes `cluster-mcp-sandbox.*`,
  `cluster-mcp-run.*` and `mutant-*` directories under its `TMPDIR` that no process uses, with the
  in-use test `tests/sandbox_dirs.py` already applies. Its open questions: an age or ownership guard
  so a concurrent run's directories are never taken, and whether the host's existing leftovers
  (which `sandbox-dirs-left-on-kill` left to the developer) come into scope.
- `bin/sandbox.sh` is on § Invariants' high-blast-radius list: a change there needs the maintainer.
- The rejected keeper design and its research are kept as a record in
  `spec/sandbox-dirs-left-on-kill/` (`research/00`, `02`–`04`, `verify/keeper.py`, at `8520d9c`).
- Related: `issues/mutant-case-cleanup-interrupted.md` (the mutation runner's own cleanup cut short).
- Found by: `sandbox-dirs-left-on-kill` (GOAL non-goal, 2026-11-09); seeded 2026-11-12.
