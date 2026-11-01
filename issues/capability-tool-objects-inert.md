---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A capability's registered tool objects can run its code when they are read

## Problem

Each tool a capability registers is a FastMCP `FunctionTool`: `@mcp_tool` (`core/tools/__init__.py`)
appends `Tool.from_function(...)` to `TOOL_REGISTRY`, which a capability's tools module imports. The
load accepts what the module registered by `isinstance`, not by exact type
(`core/capabilities.py:330-332`, `isinstance(entry, FunctionTool)`). So a tools module can append a
subclass of `FunctionTool`, or set a field of a real one, after construction, to a value of a type of
its own (a `str` subclass for `name`, a `dict` subclass for `parameters`), and that code runs whenever
the field is read:

- at the load: `tool.fn.__module__` for each registered entry (`:333-334`, `:341`), `tool.name`
  compared, listed and recorded (`:342-347`, `:360`, `:380`), and the tool registered on the load's
  scratch server through `serve()` (`:363-369`; `serve()` at `:264-272` calls `server.add_tool`);
- at server build: `create_mcp_server` registers the same objects through `serve()` again
  (`core/server.py:148`);
- after that, whenever FastMCP reads the tool to list or call it.

The load's guard turns what such code raises at the load into a refusal naming the distribution; it
does not reach the second registration or any later read, and code that runs on a read can answer
differently each time. AGENTS § Invariants §7 already says so: a capability's tools (each a
`FunctionTool` holding its function) are its code, read by FastMCP as it registers them, on the
load's scratch server and on each server built after. Since `capability-probe` the capability record
is exact (`type(value) is Capability`, every value the core or FastMCP reads exactly a built-in type),
so the tool objects are the one part of what a capability hands the core still taken by `isinstance`.

**Pre-existing:** yes. The `isinstance` check came with `capability-extras`; `capability-probe` made
the record exact and left the tools as they were.

## Why it was deferred

The maintainer's ruling at `capability-probe`'s review-cycle-2 bound (2026-11-01): seed a future
cycle that makes the tool objects inert, with no code change in that cycle. The fix changes what the
load accepts from every capability's tools module (§7, a high-blast-radius path), and needs its own
sweep: which `FunctionTool` fields the core and the pinned FastMCP read, and the exact type each
holds.

## Outcome / vision

Every tool a capability registers is decided at load to be inert: exactly a `FunctionTool`, with every
field the core or FastMCP reads holding a value of the exact type FastMCP gives it, checked before
anything reads it. The handler (`fn`) is excepted: it is the capability's code by design, and a
request calls it. A tool that fails the check refuses its capability at load, naming the
distribution, as every other §7 refusal does.

## Sketch of the acceptance criteria

- **R1** — WHEN a capability's tools module registers an object whose type is not exactly
  `FunctionTool`, the load SHALL refuse the capability, naming its distribution, with none of that
  object's code run.
- **R2** — WHEN a field of a registered `FunctionTool` other than `fn` holds a value whose type is not
  exactly the one FastMCP gives that field (a subclass of `str`, `dict`, `list` or a FastMCP model
  included), the load SHALL refuse the capability the same way, before the core reads that field.
- **R3** — The fields checked SHALL be derived from the pinned FastMCP's `FunctionTool` model, so a
  field an upgrade adds is checked or fails the check, never passes unread.

## Notes

- Open: whether the load should serve a copy it made, so a later change to a tool object by the
  capability's own code (from a handler, at request time) cannot reach the served tool.
- Related: `AGENTS.md` § Invariants §7; `spec/capability-probe/` (TECH P2, review cycle 1's F1;
  REVIEW, cycle 2's rulings).
- Found by: `capability-probe` review cycle 1 remediation, 2026-11-01.
