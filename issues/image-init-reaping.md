---
status: unshaped
kind: fix
appetite: small
lane: public
---

# The image's init is pinned by its recipe, not by what it reaps

## Problem

Since `timeout-process-cleanup`, every command runs under a watchdog that exits after the program,
orphaned. In the shipped image the server runs in `local` mode by default, so each completed call
leaves an orphan that re-parents to PID 1. The `Dockerfile` now runs `tini` as PID 1
(`ENTRYPOINT ["/usr/bin/tini", "--", "cluster-mcp"]`), which reaps them. Only a text check of the
recipe pins it (`tests/test_packaging.py::test_the_image_runs_an_init_that_reaps_orphans`). Nothing
builds the image or counts the zombies after many calls, so a recipe that names an init but does not
reap (a wrong path, a package that moves the binary, a compose file that overrides `entrypoint:`)
would pass.

**Unmeasured.** No Linux container runtime was available on the development host. Debian trixie's
`tini` package ships `/usr/bin/tini` (its file list), so the recipe is expected to run.

## Why it was deferred

Review cycle 2 of `timeout-process-cleanup` routed the init (F8) with "where CI can, a count of
zombies after many calls". Building the image in CI is a job of its own and outside that cycle's
appetite. The init is in place; this seed is the behavioural pin.

## Outcome / vision

A CI job builds the image and shows that a server running many completed calls in it leaves no
zombie behind.

## Sketch of the acceptance criteria

Left unshaped. A shaping step decides where it runs (a CI job of its own, or an opt-in row) and its
cost against the era jobs' 20-minute limit.

- **R1** — WHEN the shipped image serves N completed `local` calls, its process table SHALL hold no
  zombie afterwards.
- **R2** — The pin SHALL fail on a recipe with no init as PID 1.

## Notes

- Related: [`timeout-stop-limits.md`](timeout-stop-limits.md); `Dockerfile`; `compose.yaml` if any.
- Found by: `timeout-process-cleanup` review cycle 3 (B6), 2026-11-04.
