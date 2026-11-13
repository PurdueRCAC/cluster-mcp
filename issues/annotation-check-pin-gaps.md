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

The third review (cycle 3, N11) swept the unreadable-form detection added by the cycle 2
remediation and found six more survivors; the cycle 3 remediation's rows for names a statement binds
kill one of them (AK2, `__annotate__` dropped from the keys of a class namespace;
`spec/annotation-check/remediation/F9-review3.py`). Five remain. At module level the tree-test
oracle would catch each; inside a function-local class, where it cannot reach, only a row can:

- **Unreadable-form detection** (N11): the `else` of an `if TYPE_CHECKING:` not searched for forms
  (U6, in `_unread_forms`); a `type` call's namespace `__annotations__` value not checked for
  readable fields (UC6), and `make_dataclass`'s `fields=` keyword not checked (UC10), both in
  `_unreadable_call`; a field name that is not a string constant (UFi10), and a `TypedDict` field key
  that is not one (UFi2), not checked in `_unreadable_fields`.
- **Names a statement binds** (the cycle 3 remediation's own sweep, C5): a `def __annotate__`
  whose parameters are not one positional name (`def __annotate__(*args)`, or a second parameter
  with a default) skipped. Python calls it with the format as its one argument, so a slice it
  returns is kept; no row plants one.

None of these is a wrong verdict today; each is behaviour a later edit could break with no row
failing. The tree-test oracle cannot reach any of them: the tree holds none of these shapes, so
only planted rows pin them.

### The tree test's oracle goes red on valid shapes

The oracle (`runtime_positions`) expects every position Python keeps on an imported class, less
the keys a base in `__mro__` also holds, named by the class's `__qualname__`. Three valid shapes
turn `test_every_kept_annotation_in_the_workspace_is_a_type` red, in both eras, with "annotations
Python keeps that the check did not read" (review cycle 3, N9):

- a `TypedDict` that subclasses another: its `__annotations__` merge the base's keys, but the base is
  not in its `__mro__` (`(C, dict, object)`; the bases are in `__orig_bases__`), so the inherited key
  is expected as the child's own;
- a functional form bound to a name other than its typename (`_Row = NamedTuple('Row', ...)`): the
  class's `__qualname__` is the typename, while the reader names its fields by the bound name;
- a functional form assigned in a class body (`class H: Row = NamedTuple('Row', ...)`), a shape the
  reader reads: the class's `__qualname__` is `Row`, not `H.Row`.

It fails closed: nothing invalid passes, and no file uses these shapes today (the tree test is green
on the tree). The first such shape in a later module or member forces an edit to the check. It
falls under the maintainer's standing rule for this effort (2026-11-13): a false refusal on a shape
no file uses, which lets nothing invalid through, is graded LOW and seeded.

### Not read today

The check reads a functional class form, and refuses one it cannot read, wherever the source spells
the factory's name (as a name, an attribute or a string) or `__annotations__` or `__annotate__` (as
a string, a name, an attribute, a keyword, or the name a `def`, `class`, import or `match` pattern
binds). So a lookup through a namespace is refused whenever its key is written out
(`globals()['TypedDict']`), and so are `vars(typing)[name]` and `typing.__dict__[name]` whenever the
name is a literal anywhere in `src/`; a metaclass, or `type` bound to another name, given a
namespace built elsewhere is refused wherever that namespace's `__annotations__` key is written in
`src/`; and
`def __annotate__` in a class body is refused (review cycle 3, N10, fixed in its remediation).

One route spells none of them, so a slice that Python keeps on the class it builds passes, unread
and unrefused: a factory or an annotations name built at run time (`getattr(typing, 'Typed' +
'Dict')`, a name joined from parts, `f'__{"annotations"}__'`), whether it is then called, looked up
in a namespace, or used as a key of a namespace the check does not read (one given to a metaclass,
or to `type` bound to another name).

None occurs today. The `AGENTS.md` § Testing entry names this as not read and points here. The
outcome is that each route is read or refused, never passed: by refusing the lookup forms
outright, or by an oracle over run-time classes that includes the planted rows' scratch modules.
(Review cycle 3, N12, corrected this section: it had listed namespace lookups and namespaces built
elsewhere as passing, which the check refuses wherever the name or key is written.)

## Why it was deferred

`annotation-check` reached its second review with these open, each the next layer of a class its
earlier rounds had pinned (cycle 1's F3 and F4). The foreman's ruling for the cycle 2 remediation
(2026-11-12) fixed the functional-form detection gap, the `KW_ONLY` false refusal, the `AGENTS.md`
line and the tree test's oracle, and seeded the remaining survivors here as one seed, by the rule
that a hand-made deeper layer of a class already pinned is seeded, not a finding.

The third review, the last the loop allows, found four more (cycle 3, N9 to N12). The maintainer's
ruling (2026-11-13) fixed `def __annotate__` passing unrefused and this section's wording of the
routes that pass, and seeded here the oracle's false red on valid shapes (N9), graded LOW by the
standing rule above, and the sweep survivors (N11, with the remediation's own C5).

**Pre-existing:** no. The check is new in `annotation-check`; the gaps are in its rows, not its
behaviour on the tree.

## Outcome / vision

Every shape the reader distinguishes, every form the walker walks, every binding form shadow
detection reads, every exception class at resolution and at import, and every field of the refusal
line has a planted row that fails when it flips, and a module-wide sweep over each of those domains,
additive mutants included, leaves only recorded equivalents, in both eras. The tree test passes
every valid shape a later module may hold, and stays red on every kept position the reader missed.

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
  name the source does not spell (a name built at run time), the check SHALL read its annotations or
  refuse it, never pass it.
- **R7** — WHEN valid code holds a `TypedDict` subclassing another, a functional form bound to a
  name other than its typename, or a functional form assigned in a class body, the tree test SHALL
  pass, and SHALL still fail on every position Python keeps that the reader missed.
- **R8** — For every decision of the unreadable-form detection (each block of an `if TYPE_CHECKING:`
  statement, a `type` namespace's annotations, each keyword of a form, each field name and key, and
  every parameter shape of a `def __annotate__`), a mutant that skips it SHALL fail a named row.

## Notes

- Related: [`spec/annotation-check/`](../spec/annotation-check/) (REVIEW cycle 2, N3 to N7;
  cycle 3, N9, N11 and N12; `remediation/F6-F8-review2.py`, `remediation/F9-review3.py`);
  `issues/skip-check-pin-completeness.md` (the same shape for the skip check).
- Found by: `annotation-check` review cycles 2 and 3; seeded by their remediations.
