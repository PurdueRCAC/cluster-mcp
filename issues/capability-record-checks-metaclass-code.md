---
status: unshaped
kind: fix
appetite: small
lane: public
---

# The record checks can run a metaclass's code while they word a refusal

## Problem

The load's checks of a capability's record name the type of a value they refuse with
`type(value).__name__` inside an f-string (`_checked`, `_check_resource`, in
`packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`), and `_shown` decides how to show an
`executor` value with `type(value) in (bool, int, type(None))`. Each of these runs code of the value's
metaclass:

- `type(value).__name__` finds a `__name__` property, or a `__getattribute__`, that a metaclass of the
  capability's own defines, and runs it; a `__name__` that is a `str` subclass runs its `__format__`
  when the f-string formats it.
- `in` on a tuple of types falls back to `==`, and tries a metaclass's `__eq__` first.

So a capability whose entry point names a value of a class with a metaclass of its own runs that
metaclass's code while the load decides or words its refusal. It runs at load, inside the load's guard,
so what it raises is still a refusal naming the distribution, but the message can lie and the code
runs where § Invariants §7 says none does. `capability-tool-objects-inert` names a type through `type`'s
own descriptor (`str.__str__(type.__dict__['__name__'].__get__(kind))`) and tests types with `is`
alone; the record checks predate that.

**Pre-existing:** yes, since the exact record checks landed with `capability-probe`.

## Outcome / vision

The record checks name a refused value's type, and decide `_shown`'s form, running none of the value's
or its metaclass's code, as the tool-object check does.

## Sketch of the acceptance criteria

- **R1** — WHEN the load refuses a capability's record, or a value in it, whose type has a metaclass of
  its own, deciding and wording the refusal SHALL run none of that metaclass's code, and the message
  SHALL name the type by its own name.
- **R2** — The refusals of every other record value SHALL be worded as today.

## Notes

- Related: `spec/capability-tool-objects-inert/` (PLAN § 5, and `research/02-inert-reads-and-generic-rule.md`
  § 2, which probed both reads); `AGENTS.md` § Invariants §7; `core/capabilities.py`.
- Found by: `capability-tool-objects-inert` planning, 2026-11-12; seeded at its plan sign-off.
