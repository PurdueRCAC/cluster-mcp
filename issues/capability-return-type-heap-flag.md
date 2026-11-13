---
status: unshaped
kind: fix
appetite: small
lane: public
---

# The return-type rule's exemption for static types is decided by a flag a capability's own code can set

## Problem

A tool's return type is accepted only when every class it holds carries its own `__module__`, exactly a
`str`, in its own namespace (`_return_type_violation`, the class branch, in
`packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`). A class without the heap-type flag
(`Py_TPFLAGS_HEAPTYPE`, read through `type`'s own `__flags__` descriptor) is exempt, because a static type
such as `str` or `dict` has no `__module__` in its namespace: `type` reads it from the type's name. The
flag stands in for "a class whose `__module__` read runs no capability code", and the two can part only
through the capability's own native code:

- **Accepted, and capability code runs.** A capability that clears the flag on a class of its own
  (through `ctypes`, writing `tp_flags`), after deleting its `__module__` and giving it a base whose
  `__module__` is a `str` subclass of its own, passes the rule. On a metaclass the load accepts other
  than `type` (`abc`'s, pydantic's, `enum`'s), FastMCP's `getattr(cls, '__module__', '')` while adding
  the tool resolves along the MRO to the base's value and compares it, so the capability's `__eq__` and
  `startswith` run in the load's scratch build and on every server built after it.
- **Refused, though nothing of the capability's runs.** A heap type a C extension makes with
  `PyType_FromSpec` from an undotted name has no `__module__` at all; the rule refuses it, while FastMCP
  reads `''` for it. No installed class has that shape.

Both were reproduced in `capability-tool-objects-inert` review cycle 3, which graded them LOW and seeded
them: a capability's own code acting on purpose, which already runs at import, and a refusal of a shape
no file uses. No class a Python statement, `type()`, a dataclass, `NamedTuple`, `TypedDict`, `Enum`,
`pydantic.create_model`, `abc` or `Generic` makes lacks the flag.

**Pre-existing:** no; the exemption is `capability-tool-objects-inert`'s rule.

## Outcome / vision

The class branch decides a class's `__module__` the way FastMCP's read resolves it, or names the static
types it exempts, so that neither a flag nor a name the capability can change decides whether its code
runs.

## Sketch of the acceptance criteria

- **R1** — WHEN a class a tool's return type holds lacks the heap-type flag, the load SHALL accept it
  only if FastMCP's read of its `__module__` runs none of the capability's code, and SHALL refuse it
  otherwise, naming the distribution and the field.
- **R2** — Every return type the members use SHALL load and serve unchanged.

## Notes

- Related: `spec/capability-tool-objects-inert/` (REVIEW cycle 3); `AGENTS.md` § Invariants §7;
  `core/capabilities.py`.
- Found by: `capability-tool-objects-inert` review cycle 3, 2026-11-13.
