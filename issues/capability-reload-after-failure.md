---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A second capability load after a failed one registers nothing and names the wrong distribution

## Problem

`load()` in `core/capabilities.py` loads capabilities in order and, when one fails, cuts
`TOOL_REGISTRY` back to what it held before the load. The tools modules it imported stay in
`sys.modules`, though. A second load in the same process re-imports nothing for a capability that had
loaded cleanly, so its tools are never registered again, and the instructions check then refuses it:
the error names the healthy distribution instead of the broken one.

Observed with two planted distributions, `aaa-good` (loads) and `bbb-broken` (raises): the first load
reports `cannot load capability bbb-broken: …`; a second load in the same process reports
`cannot load capability aaa-good: its instructions list ['a_echo'], which it does not register`.

**Pre-existing:** no — introduced with the entry-point loader (`capability-extras`). It is not
reachable from the command line: a load failure stops startup with exit 5, and nothing loads twice.
Only a library caller that catches the error and calls `installed()` or `create_mcp_server()` again
sees it.

## Why it was deferred

Found by `capability-extras`' review (cycle 1) and judged out of that cycle's scope: no requirement
covers a retry after a failed load, and the product path never makes one.

## Outcome / vision

A failed load leaves the process as if no load had happened, so a retry loads the healthy
capabilities again and names only the one that fails.

## Sketch of the acceptance criteria

- **R1** — WHEN a load fails and is retried in the same process, the retry SHALL register every
  capability that loads cleanly and SHALL name only the failing distribution.
- **R2** — A test SHALL plant a healthy and a failing capability and load twice.

## Notes

- Related: `spec/capability-extras/` (REVIEW, cycle 1); `AGENTS.md` § Invariants §7.
- Found by: `capability-extras` review cycle 1, 2026-10-31.
