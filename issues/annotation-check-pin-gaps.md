---
status: unshaped
kind: test
appetite: small
lane: public
---

# The annotation check behaves correctly on shapes its rows do not pin

## Problem

`tests/test_annotations.py` refuses every planted defect `annotation-check`'s second review tried,
but some of that behaviour has no row that fails when it changes: a mutant of the check can stop
reading a shape, or stop walking a form, and pass every row in both eras while a planted defect of
that shape goes unrefused. The review recorded 39 such survivors (`spec/annotation-check/REVIEW.md`,
cycle 2, N3 to N7), each replayed as a real planted defect that the unmutated check refuses and the
mutated check passes. The review cycle 2 remediation gave the tree test an expected set of positions
read from what the interpreter keeps, which kills the nine whose shape the tree holds (functions
with an attribute or a call decorator, classmethods, properties, `_private` functions, dunder
methods, parameters with a default, a class with a call decorator such as `@dataclass(frozen=True)`,
`_private` class attributes; `spec/annotation-check/remediation/F6-F8-review2.py`). Thirty remain:

- **The position reader** (N3): `self` and `cls` parameters (D20; the tree annotates neither); an
  `if NAME:` or `if a.b:` body treated as `if TYPE_CHECKING:` (T3, T4); the `else` of a `for` or
  `while` (K1); `async for` (K2) and `async with` (K2b) bodies; `try*` (K3); `match` cases after the
  first (K12); a functional form's fields in a tuple rather than a list (F10) and its pairs written
  as lists (F11); an alias imported from a module other than `typing` and `dataclasses` (P2; the
  reader now maps an alias from any module, and no row imports one from another).
- **The type walker** (N4): the argument of `ClassVar`, `Required`, `NotRequired` or `ReadOnly`
  (G3a to G3d; only `Final`'s is planted), `type[...]` (G13), `Unpack[...]` (G15), a
  `collections.abc` generic such as `Mapping` (G16), `set` and `frozenset` (G19), and a
  `Callable`'s parameters after the first (G22).
- **Shadow detection** (N5): names bound by `except ... as` (S5), a `match` capture (S6) and a
  mapping pattern's `**rest` (S7); the base of an `Annotated` (N3) and a subscript's head (N5), as
  names an annotation reads.
- **Exception classes** (N6): an `AttributeError` (V3; `x: os.NoSuchThing` is realistic), a
  `RecursionError` (V7) or a `LookupError` (V8) while resolving, and a `SystemExit` at import (MC5),
  each passed by a carve-out.
- **The refusal line** (N7): the annotation as written, blanked (A6), still passes every row.

None of these is a wrong verdict today; each is behaviour a later edit could break with no row
failing. The tree-test oracle cannot reach any of them: the tree holds none of these shapes, so
only planted rows pin them.

### Not read today

The check reads a functional class form, and refuses one it cannot read, only where the source
spells the factory's name, `__annotations__` or `__annotate__`. Three routes spell none of them, so
a slice that Python keeps on the class they build passes, unread and unrefused:

- a factory or an annotations name built at run time: `getattr(typing, 'Typed' + 'Dict')`, a name
  joined from parts, `f'__{"annotations"}__'`;
- a lookup through a namespace: `globals()['TypedDict']`, `vars(typing)[name]`,
  `typing.__dict__[name]`;
- a metaclass, or `type` bound to another name, called with a namespace built elsewhere (a
  variable, a function's return, another module's dict) that carries `__annotations__`.

None occurs today. The `AGENTS.md` § Testing entry names this as not read and points here. The
outcome is that each route is read or refused, never passed: by refusing the lookup forms
outright, or by an oracle over run-time classes that includes the planted rows' scratch modules.

## Why it was deferred

`annotation-check` reached its second review with these open, each the next layer of a class its
earlier rounds had pinned (cycle 1's F3 and F4). The foreman's ruling for the cycle 2 remediation
(2026-11-12) fixed the functional-form detection gap, the `KW_ONLY` false refusal, the `AGENTS.md`
line and the tree test's oracle, and seeded the remaining survivors here as one seed, by the rule
that a hand-made deeper layer of a class already pinned is seeded, not a finding.

**Pre-existing:** no. The check is new in `annotation-check`; the gaps are in its rows, not its
behaviour on the tree.

## Outcome / vision

Every shape the reader distinguishes, every form the walker walks, every binding form shadow
detection reads, every exception class at resolution and at import, and every field of the refusal
line has a planted row that fails when it flips, and a module-wide sweep over each of those domains,
additive mutants included, leaves only recorded equivalents, in both eras.

## Sketch of the acceptance criteria

- **R1** — For every block kind the reader descends (`if`/`else`, `for`/`while` and their `else`,
  `async for`, `with`, `async with`, `try`, `try*` and each of their parts, every `match` case),
  and every parameter kind including `self` and `cls`, a slice planted there SHALL be refused, and a
  mutant that skips it SHALL fail a named row.
- **R2** — For every qualifier and every generic form the walker walks (`ClassVar`, `Required`,
  `NotRequired`, `ReadOnly`, `type`, `Unpack`, `collections.abc` generics, `set`, `frozenset`, each
  `Callable` parameter), a slice inside it SHALL be refused by a named row.
- **R3** — For every binding form shadow detection reads, and every part of an annotation it reads
  names from, a scope-dependent annotation SHALL be refused by a named row.
- **R4** — WHEN resolving raises any exception, or an import raises `SystemExit`, the check SHALL
  refuse it, each exception class pinned by a named row.
- **R5** — A refusal line SHALL name the annotation as written, asserted by a row.
- **R6** — WHEN a class whose annotations Python keeps is built through a factory or annotations
  name the source does not spell (built at run time, looked up in a namespace, or a metaclass given
  a namespace built elsewhere), the check SHALL read its annotations or refuse it, never pass it.

## Notes

- Related: [`spec/annotation-check/`](../spec/annotation-check/) (REVIEW cycle 2, N3 to N7;
  `remediation/F6-F8-review2.py`); `issues/skip-check-pin-completeness.md` (the same shape for the
  skip check).
- Found by: `annotation-check` review cycle 2; seeded by the cycle 2 remediation.
