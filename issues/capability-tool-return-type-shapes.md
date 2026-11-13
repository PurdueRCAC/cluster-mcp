---
status: unshaped
kind: fix
appetite: small
lane: public
---

# The load refuses some return annotations FastMCP serves

## Problem

`capability-tool-objects-inert` decides a registered tool's `return_type` by an allowlist
(`_RETURN_CLASSES` and `_RETURN_ALIASES`, `_return_type_violation`, in
`packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`; `AGENTS.md` § Invariants §7 lists it):
a class of a metaclass it names, or an alias it names whose parts pass in turn, an `Annotated`'s
metadata exactly pydantic's `FieldInfo` or JSON-like. Some return annotations that `Tool.from_function`
builds, and that FastMCP 4.1.4 serves and calls without error, fall outside it, so a capability whose
tool returns one is refused at load and stops startup:

- a `typing.NewType` (`holds a NewType, not a class or an alias it accepts`);
- a `type X = …` alias (`holds a TypeAliasType, …`);
- a bare `typing.Dict` or `typing.List` (`holds a _SpecialGenericAlias, …`);
- `Annotated[int, annotated_types.Gt(0)]` (`… whose metadata holds a Gt`);
- a `typing_extensions.TypedDict` (`holds a _TypedDictMeta, …`).

`develop` before that cycle loads each of them (a capability returning a `NewType` loads beside the
Slurm and RCAC members there, and is refused on the cycle's branch). Neither workspace member returns
one, so the served surface is unchanged.

**Pre-existing:** no. Introduced by `capability-tool-objects-inert`, whose rule table, ruled at its
plan sign-off, accepts only the shapes it could show inert. Found by its review cycle 1 (F4,
2026-11-12), recorded there as out of Scope.

## Why it was deferred

No requirement of that cycle asks for these shapes to load, and widening the allowlist is not a
one-line change: each shape needs its own inertness decision before the load may accept it. A
`type X = …` alias evaluates its value lazily by calling code the capability defined; a `NewType`
carries a supertype of the capability's choosing; `annotated_types` metadata are objects whose reads
are their classes' code. Deciding which of them can be read inertly, and how, is shaping work, not a
remediation.

## Outcome / vision

A capability may return any annotation in common use that the load can decide inert without running
its code, and the load's refusal of the others names the shape and says why. §7's rule list says
which shapes are accepted.

## Sketch of the acceptance criteria

- **R1** — WHEN a capability's tool returns a `NewType`, a bare `typing` generic, or an `Annotated`
  whose metadata are `annotated_types` constraints, the load SHALL accept it, deciding it by exact
  types and running none of the capability's code.
- **R2** — WHERE a shape cannot be decided without running capability code (a lazily evaluated
  `type X = …` alias is the candidate), the load SHALL keep refusing it, and `AGENTS.md` §7 SHALL say
  so.

## Notes

- Related: `spec/capability-tool-objects-inert/` (REVIEW cycle 1, F4; GOAL Q2 and the plan sign-off
  rulings); `AGENTS.md` § Invariants §7; `core/capabilities.py` (`_return_type_violation`).
- Found by: `capability-tool-objects-inert` review cycle 1, 2026-11-12.
