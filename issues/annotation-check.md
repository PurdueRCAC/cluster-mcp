---
status: unshaped
kind: ci
appetite: small
lane: public
---

# Nothing would catch the next silently wrong annotation

## Problem

`src/rcac_mcp/auth.py` declared `AUTH_MODES: Final[Dict[str, Callable[[], AuthProvider]]:]`. The
`:` before the final `]` made the subscript a slice expression, so the annotation was
`Final[slice(Dict[...], None, None)]` rather than the intended mapping type. It was not loud:
`typing.get_type_hints` resolved it without error, and so did eager evaluation, which no longer
rejects a non-type argument there. It sat on `main` for months, in a module on the
high-blast-radius list (`AGENTS.md` § Invariants), the one that decides whether a request is
authenticated at all.

It was fixed only because the `stack-upgrade` cycle happened to rewrite `auth.py`
([`spec/stack-upgrade/`](../spec/stack-upgrade/), R7, seen red by a mutation case under R9). That
pins one annotation in one module. Nothing in the suite or the release recipe's `gate` checks
annotations anywhere else in `src/`, so the next one of the same kind would ship the same way.

## Why it was deferred

The defect's own seed asked whether to add the general check alongside its one-character fix, and
`stack-upgrade` declined to: its GOAL lists "a repo-wide type checker or `get_type_hints` sweep" as
a non-goal that belongs with `ci-workflow`. `ci-workflow`'s GOAL, shaped earlier, never took it up,
so it is carried here at the retirement of `stack-upgrade`'s seeds.

**Pre-existing:** yes — no type checker or annotation check has ever run on this repository.

## Outcome / vision

A gate step, or a standing test, that type-checks `src/`, or at least evaluates every annotation in
`src/rcac_mcp` and rejects any that resolves to a non-type object such as a slice. Which tool
(pyright, mypy, or a `get_type_hints` sweep) is the plan's call. It runs where the gate runs; CI
has mirrored the gate since `ci-workflow` landed on `develop` (2026-10-18), so it runs there too.

## Sketch of the acceptance criteria

- **R1** — WHEN any annotation in `src/rcac_mcp` resolves to an object that is not a type
  expression (a slice, as in `AUTH_MODES` before `stack-upgrade`), the check SHALL fail and name
  the module and the annotation.
- **R2** — The check SHALL be shown red against a planted slice annotation before it lands, and
  green on the current tree.
- **R3** — It SHALL run in the release recipe's `gate` or in the collected suite, so CI picks it up
  through its mirror of the gate.

## Notes

- A criterion that only asserts evaluation succeeds passes on the broken code; the check has to
  assert the shape of what resolves.
- Related: [`spec/stack-upgrade/`](../spec/stack-upgrade/) (R7, R9: the one pinned annotation);
  [`spec/ci-workflow/`](../spec/ci-workflow/) (CI mirrors the gate).
- Found by: `stack-upgrade`'s GOAL non-goals, carried at retirement, 2026-10-17.
