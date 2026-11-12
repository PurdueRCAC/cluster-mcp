---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A sandbox killed outright by a caller outside the repository's own runs leaves its directory

## Problem

`bin/sandbox.sh` makes its directory with `mktemp -d "${TMPDIR:-/tmp}/cluster-mcp-sandbox.XXXXXX"`
and removes it from a trap on `EXIT HUP INT TERM`. A SIGKILL skips the trap, so the directory stays:
the skeleton the script makes (`.config`, `.cache`, `.local/share`), sometimes with FastMCP's
`version_cache.json` or other files written under the sandbox's `HOME`.

`sandbox-dirs-left-on-kill` cleaned up after the repository's own runs: a pytest run points `TMPDIR`
at a directory of its own and sweeps it when the session ends (`tests/sandbox_dirs.py`, the
`sandbox_tmp` fixture), and the mutation runner makes each case's scratch its child run's `TMPDIR`
(`case_scratch`). It left `bin/sandbox.sh` byte-identical (its R5), so a caller outside those runs
still leaves a directory when it SIGKILLs the wrapper. Its GOAL records this as a non-goal:

> **Callers outside the repository's own runs (known limitation).** A developer's shell, a cycle's
> `spec/*/verify/` gate script (such as `spec/agents-d-instructions/verify/serve_gate.py`, which
> SIGKILLs a sandboxed server), or any other ad hoc caller that kills a sandbox outright still leaves
> its directory, because `bin/sandbox.sh` is unchanged (R5). Earlier cycles' gate scripts are
> records and are not edited.

Such a caller is a person (a shell's `kill -9`, a terminal closed in a way that SIGKILLs the group)
or another tool (a gate script, an editor's task runner, a CI step cancelled outright). Each leftover
lands in that caller's `TMPDIR`, usually the host's, where nothing tells it from another run's.

Pre-existing: the trap came in with the sandbox wrapper itself, before the factory.

## Why it was deferred

`sandbox-dirs-left-on-kill`'s maintainer ruling (its GOAL, Q4, 2026-11-09) kept `bin/sandbox.sh`
unchanged and narrowed the contract to the repository's own runs; the first design, a keeper process
inside the wrapper, was rejected. Filed as a seed on the foreman's ruling at that cycle's P3 ledger,
2026-11-12, so the known limitation has a record beyond `AGENTS.md`'s sentence.

## Outcome / vision

A sandbox stopped outright by any caller leaves no directory behind, or what it leaves is found and
removed safely later, without removing another run's directory, one in use, or the leftovers a
developer chooses to keep.

## Sketch of the acceptance criteria

- **R1** — WHEN a caller outside the repository's own runs SIGKILLs `bin/sandbox.sh` (alone or with
  its process group), its sandbox directory SHALL be removed within a bound the maintainer sets, or
  SHALL be removable by a documented step that removes only directories no process uses.
- **R2** — No directory of another sandbox still in use, and nothing that is not a sandbox directory,
  SHALL be removed.
- **R3** — The throwaway-environment contract (`AGENTS.md` § Factory, Throwaway environment) SHALL
  hold as it does today.

## Notes

- `bin/sandbox.sh` is on § Invariants' high-blast-radius list: a change there needs the maintainer.
- The rejected keeper design and its research are kept as a record in
  `spec/sandbox-dirs-left-on-kill/` (`research/00`, `02`–`04`, `verify/keeper.py`, at `8520d9c`).
- Related: `issues/mutant-case-cleanup-interrupted.md` (the mutation runner's own cleanup cut short).
- Found by: `sandbox-dirs-left-on-kill` (GOAL non-goal, 2026-11-09); seeded 2026-11-12.
