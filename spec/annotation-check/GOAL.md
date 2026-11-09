# GOAL — Nothing would catch the next silently wrong annotation

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** annotation-check
- **kind:** ci
- **appetite:** small

## Problem

`auth.py` declared `AUTH_MODES: Final[Dict[str, Callable[[], AuthProvider]]:]`. The `:` before the
final `]` made the subscript a slice expression, so the annotation was `Final[slice(Dict[...], None,
None)]` rather than the intended mapping type. Nothing complained: `typing.get_type_hints` resolved
it, and so did eager evaluation, which no longer rejects a non-type argument there. It sat on `main`
for months in a high-blast-radius module (`AGENTS.md` § Invariants), the one that decides whether a
request is authenticated at all.

It was fixed only because [`stack-upgrade`](../stack-upgrade/) happened to rewrite the file (R7,
seen red by a mutation case under R9). Today that one annotation is pinned by
`tests/test_auth_modes.py` (`annotation_violations`, § Testing): `get_type_hints` of
`cluster_mcp.core.auth` must give `AUTH_MODES` its exact shape. Nothing in the suite or the release
recipe's `gate` checks any other annotation, so the next one of the same kind would ship the same
way. **Pre-existing:** no type checker or annotation check has ever run on this repository.

Since the seed was written, the code moved: `src/rcac_mcp/` became a uv workspace of three members,
each with its own `packages/<member>/src/cluster_mcp/…` tree (the core, `cluster-mcp-slurm`,
`cluster-mcp-rcac`); the root compat distribution ships no code. `AUTH_MODES` is now at
`packages/cluster-mcp/src/cluster_mcp/core/auth.py:67`. Most modules use
`from __future__ import annotations`, so their annotations are strings until something evaluates
them, and a defect inside one is invisible until then.

Part II (0.3.0) adds tool families as new members and modules. A check that names today's modules
would miss them.

## Outcome / vision

A standing check, run wherever the gate runs and so on CI, that evaluates the annotations in every
workspace member's `src/` and rejects any that resolves to something other than a type, naming
where it is. It finds its modules from the workspace itself, so every member and family added later
is covered on arrival. It changes no code under `src/`: it is a gate, not a cleanup. Which tool or
mechanism (a `get_type_hints` sweep, an AST pass, a type checker in a narrow configuration) is the
plan's call, within what Q1 settles.

## Acceptance criteria (the contract)

- **R1** — WHEN an annotation Python keeps at run time (a module variable's, a class attribute's,
  or a function's or method's parameter or return annotation), in any module under any workspace
  member's `src/`, resolves to an object that is not a valid type expression (a `slice` inside a
  subscript, as `AUTH_MODES` carried before `stack-upgrade`, or any other non-type value), the
  check SHALL fail.
- **R2** — IF such an annotation cannot be resolved at all (it names something that does not exist
  where it is evaluated, such as a name imported only under `TYPE_CHECKING`), THEN the check SHALL
  fail as it does for a non-type.
- **R3** — WHEN the check fails, its output SHALL name, for each annotation it rejects, the module,
  the annotated name (qualified by its class or function), and the annotation as written or as it
  resolved.
- **R4** — The check SHALL take the members and modules it checks from the workspace as it stands
  when it runs, with no list of modules or members of its own: a module, family or member added
  later is checked with no edit to the check.
- **R5** — Before it lands, the check SHALL be seen red against a planted slice annotation in each
  kind of position it covers, in a module of the core and in a module of another member, and SHALL
  pass on the current tree.
- **R6** — The check SHALL run in the release recipe's `gate` or in the collected suite, so CI runs
  it through its mirror of the gate. It SHALL need no network and no cluster, and every CI job SHALL
  stay within the profile's `ci budget`.
- **R7** — The cycle SHALL change no file under any member's `src/`; `tests/fixtures/served_surface.json`
  stays unchanged and `test_served_surface_matches_baseline` passes. IF the check flags an annotation
  on the current tree, THEN the cycle SHALL report it at the gate instead of changing it: a tool's
  parameter and return annotations become the served input and output schemas (§ Invariants 9, human
  gate), and other flagged annotations may sit in a high-blast-radius path.

## Non-goals (no-gos)

- **MCP tool annotations** (`readOnlyHint`, `destructiveHint`, `idempotentHint`). Those are the
  "honest annotations" of [`issues/tool-surface.md`](../../issues/tool-surface.md) (R1), applied
  family by family in 0.3.0. They share the word and nothing else: this check reads Python type
  annotations, and `tests/test_surface.py` already compares the served hints.
- Changing any served annotation, schema, docstring or instruction, and how the served-surface
  fixture follows a deliberate change
  ([`issues/surface-fixture-after-a-surface-change.md`](../../issues/surface-fixture-after-a-surface-change.md)).
- Making `src/` clean under a general type checker, fixing type errors other than an annotation
  that resolves to a non-type or not at all, and function-local annotations (Q1).
- Annotations under `tests/`, `bin/` or `spec/`.
- Replacing `AUTH_MODES`'s exact-shape pin in `tests/test_auth_modes.py`: it asserts more about that
  one annotation than a general check can, and it stays.
- Checking values against their annotations at run time.

## Clarifications

- **Q1:** Which annotations does the check cover? — **A:** the annotations Python keeps at run
  time: module variables, class attributes, and function and method signatures. Function-local
  annotations, which are never evaluated, are out, and so is a full static type check of `src/`;
  neither is seeded (resolved 2026-11-09, foreman ruling at the GOAL gate).
- **Q2:** What does the check do with an annotation it cannot resolve (an undefined name, or one
  imported only under `TYPE_CHECKING`)? — **A:** it fails like a non-type, with no exemption list.
  This forbids annotations that need a `TYPE_CHECKING`-only import; none exist in `src/` today
  (resolved 2026-11-09, foreman ruling at the GOAL gate).

## Related materials

- Seed: [`issues/annotation-check.md`](../../issues/annotation-check.md) (promoted 2026-11-09).
- [`spec/stack-upgrade/`](../stack-upgrade/) (R7, R9: the one pinned annotation, and the non-goal
  this seed carries); [`spec/ci-workflow/`](../ci-workflow/) (CI mirrors the gate);
  [`spec/rename-to-cluster-mcp/`](../rename-to-cluster-mcp/) (the workspace layout the seed's paths
  predate).
- Overlaps: [`issues/tool-surface.md`](../../issues/tool-surface.md) (0.3.0; MCP hints, a different
  thing, see Non-goals; its families' modules are what R4 covers on arrival);
  [`issues/surface-fixture-after-a-surface-change.md`](../../issues/surface-fixture-after-a-surface-change.md)
  (0.2.0; owns any change to the served surface, see R7).
- Source: `packages/cluster-mcp/src/cluster_mcp/core/auth.py` (`AUTH_MODES`);
  `tests/test_auth_modes.py` (`annotation_violations`); `AGENTS.md` § Factory (Profile `ci budget`,
  Release recipe `gate`), § Invariants 9, § Conventions ("CI mirrors the gate").
- Trap for the plan: Python synthesizes some annotated members whose annotations do not evaluate in
  their own module (the `__new__` of a `NamedTuple`, such as `cluster_mcp.core.capabilities._Entry`).
  They are not annotations the source contains; R5's pass on the current tree has to survive them.
