---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A capability can change a tool object after the load has checked it

## Problem

The load serves the objects the capability built, so capability code can change one after the load;
serving a copy rebuilt from the checked values would close it.

`capability-tool-objects-inert` decides at load that every tool a capability registers is exactly a
`FunctionTool` holding values of the exact types FastMCP gives its fields
(`spec/capability-tool-objects-inert/GOAL.md`). The check holds at load only. The objects the load
checks are the ones it then hands to `serve()`, on the load's scratch server and again on each server
`create_mcp_server` builds (`packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`, `load` and
`serve`; `core/server.py`, `create_mcp_server`). The capability still holds a reference to each of
them: its tools module keeps the `FunctionTool` that `@mcp_tool` returned, and a handler can reach it
at request time. Code that sets a field of its own tool after the load, to a value of a type of its
own, puts back exactly what the load refused, and FastMCP runs that type's code the next time it
reads the field (listing or calling the tool).

**Pre-existing:** yes. The load has served the capability's own objects since `capability-extras`;
`capability-tool-objects-inert` makes them exact at load and leaves them shared.

## Why it was deferred

Ruled out of `capability-tool-objects-inert`'s scope at its GOAL sign-off (2026-11-12): that cycle
decides the objects as they stand at load, and this one was filed instead of being recorded as an
accepted limit. Serving a copy changes which object every server registers, on a high-blast-radius
path (`AGENTS.md` § Invariants §7), and wants its own sign-off.

## Outcome / vision

What the server serves for a capability's tool is a copy the load built from the values it checked,
so nothing the capability holds is what FastMCP reads. A change a capability makes to its own tool
objects after the load reaches no served tool.

## Sketch of the acceptance criteria

- **R1** — WHEN a capability's code changes a field of a tool object it registered, after its load
  succeeded, the served tool SHALL be unchanged, and listing or calling it SHALL run none of the
  capability's code but the handler.
- **R2** — The served surface SHALL be unchanged for the Slurm and RCAC members
  (`test_served_surface_matches_baseline` with no fixture edit).

## Notes

- Related: `spec/capability-tool-objects-inert/` (GOAL, Q1 and R7); `AGENTS.md` § Invariants §7;
  `issues/capability-reload-after-failure.md` (the other change to `load()`).
- Found by: `capability-tool-objects-inert` shaping, 2026-11-12.
