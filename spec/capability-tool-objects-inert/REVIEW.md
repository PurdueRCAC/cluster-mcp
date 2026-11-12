# REVIEW — A capability's registered tool objects run none of its code when they are read

> Adversarial QA by `code-review`, run in an isolated context (a fresh subagent). The correctness pass
> grades the branch diff against [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants **only** —
> it does not see `PLAN.md`/`TECH.md`. Every finding cites an **executed** command, not an assertion.

- **Reviewed commit:** `79c34e0` (the code graded); verdict pinned at `dfff3e8`, which adds only the
  out-of-Scope seed below (`issues/capability-tool-return-type-shapes.md` and its `ROADMAP.md` entry)
  · **Base:** develop · **Date:** 2026-11-12
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md`
- **Mode:** a fresh blind pass over the full spec-excluded diff. One reviewer (the diff touches no
  path of the profile's coupled core, so no debate); no sequential fallback.
- **Contract:** graded against `GOAL.md` as amended by `680c843` (the plan sign-off rulings: R4
  amended, Q-B, Q-C, Q-D), the one GOAL commit after the shape commit. It awaits the maintainer's
  confirmation (`code-review` Step 1.4).

## Verification run

Evidence lives in the worktree's gitignored `.local/review1/` (`orchestrator/` and `reviewer/`).

- The cycle's phase gates, at `79c34e0`, one at a time (orchestrator): `verify/p1.sh` `phase` (1962
  passed in each era), `cli-legacy` and `cli-modern` (every tool-object kind through the CLI,
  `CLUSTER_MCP_TEST_EVERY_KIND=1`: 258 passed each), `replanted-legacy` and `replanted-modern` (108 of
  108 killed each), `mutants-legacy` and `mutants-modern` (34 of 34 killed each, 0 equivalents);
  `verify/p2.sh` `phase` (634 passed in each era) and `ledger` (ok). All exit 0 (`orchestrator/gates.txt`).
- The profile's full `verify`, both eras, at `79c34e0` (reviewer): all ten steps exit 0 (44, 154, 513,
  and 4765 passed with 14 skipped per era; `uv lock --check`; the sandboxed `--help`)
  (`reviewer/verify_summary.log`).
- Tier 2 (reviewer): the 305 cases planting into `core/capabilities.py` or targeting a touched test,
  all killed for the right reason (`reviewer/tier2_{0..3}.log`); `tests/test_mutations.py` passes.
- The diff sweep (reviewer): 56 mutants of the new decisions in `core/capabilities.py`, each run
  against `tests/test_capabilities.py` and `tests/test_surface.py` through the repo runner under
  `bin/sandbox.sh`, at most two workers: 31 killed, 25 survived (`reviewer/sweep_shard{0..3}.log`).
- Reach probes (reviewer; three re-run by the orchestrator, identical): each survivor planted, a
  capability whose tool holds the input it guards loaded beside the Slurm member, a server built, its
  tools listed, every operation of the planted types recorded (`reviewer/reach.log`,
  `orchestrator/reach-rerun.log`).
- CLI drives in the throwaway environment: `tool-subclass-reads-name` and `tool-exact-parameters-value`
  over raw-wire, stdin-closed and http (`reviewer/cli_unloadable.log`); the generic rule's warning,
  once per field per process, naming the field and FastMCP 4.1.4, exit 0 (`reviewer/probe_warn_cli.log`).
- `test_no_spec_ids_in_the_package_or_the_suite` passes, and a grep of the added lines finds no spec id.
- Tree clean on hand-back (`git status --porcelain` empty); no ignored build state mutated (the
  `develop` copy and every mutant ran in temporary scratch copies).

## Requirement → evidence matrix

No R-ID is an artifact deliverable; the blind reviewer graded all seven.

| R-ID | Implemented by | Verified how | Status |
|------|----------------|--------------|--------|
| R1 | `_tool_violation`, `_type_name` (`630b4b6`) | `tool-subclass-*` rows beside each member set; CLI `tool-subclass-reads-name` on three transports; a type whose `__name__` is a `str` subclass, or a metaclass property, named with no code run (`probe_type_name.log`) | ✅ |
| R2 | `TOOL_RULES` and the depth walks (`630b4b6`) | `tool-exact-*`, `tool-default-*`, `tool-state-*` rows; CLI `tool-exact-parameters-value`; sweep 31 of 56 killed | ⚠️ implemented; refusals at depth unpinned (F1, F3) |
| R3 | the load's decision before any read (`630b4b6`); the R3 test (`0f34719`) | `test_a_served_capability_runs_none_of_its_code_but_its_handler`; adversarial `probe_r3_unwalked.py`: nothing ran building or listing, a call ran only its handler | ✅ |
| R4 | `_unnamed`, `_undecided` (`630b4b6`) | `test_every_function_tool_field_has_a_rule`; the CLI warning drive | ⚠️ implemented; the declared-default branch unpinned (F2) |
| R5 | — | `test_served_surface_matches_baseline` with no fixture edit; full verify green | ✅ |
| R6 | rows beside each member set; `CLI_UNLOADABLE` (`630b4b6`) | `TOOL_REGISTRY == before` asserted per row; two CLI kinds driven | ⚠️ some depth refusals have no planted row (F1) |
| R7 | `AGENTS.md` §7, same commit as the check (`630b4b6`) | §7 lists the refusal, says the check holds at load, names `issues/capability-tool-objects-served-copy.md` (exists) | ✅ |

Unmapped changes: `issues/capability-record-checks-metaclass-code.md` and its `ROADMAP.md` entry (a
seed filed at plan sign-off; its Problem reproduces, `probe_seeds.log`; Part I and Safety counts
correct); the load deciding the whole registry, the core's tools included (documented in §7); the
`declared` and `served-tool` timings reworked. All follow from R1/R2 or are deferral records; none is
scope creep.

## Findings

### F1 [MEDIUM/CONFIRMED] Refusals at depth are unpinned; without their guards, capability code runs
- **Where:** `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`: `_return_type_violation`
  (the alias `seen` set, its state not a `dict`, a state key not a `str`, args/module/metadata not
  exact, `Annotated` metadata) and `_same` (a `dict` key not a `str`), as of `79c34e0`.
- **Failure scenario:** each guard's mutant passes the whole of `test_capabilities.py` and
  `test_surface.py`. With the guard removed, a planted capability loads and its code runs:
  `Annotated[str, <own object>]` → the object's `__getattribute__` at load and while building and
  listing (breaks R3); a `_GenericAlias` whose state key `'__origin__'` is a `str` subclass, or a
  `task_config` state keyed by one → its `__eq__` at load and on every build; an alias whose state is a
  `dict` subclass, or whose `__args__`/`__metadata__` is a `tuple` subclass → the checker itself runs
  its `__iter__`/`get`/`__getitem__` (breaks R2's "run none of the value's code in deciding"); a cyclic
  alias, which HEAD loads, never returns (killed by a 60 s alarm, exit 142). HEAD refuses every input
  above, running nothing; the guards are right and the tests do not hold them.
- **Evidence:** `reviewer/sweep_shard{0..3}.log` (`SURVIVED … 0 failing` for R-metadata-never,
  R-state-key-never, S-dict-key-never, R-state-dict-never, R-parts-never, R-parts-args-dropped,
  R-parts-metadata-dropped, R-seen-never); `reviewer/reach.log`, re-run by the orchestrator for three
  pairs with identical output (`orchestrator/reach-rerun.log`). No test carries any of these refusal
  wordings (`grep -rl --exclude-dir=spec` over `tests/` for "whose state is a", "arguments, module or
  metadata", "whose metadata holds", "_AnnotatedAlias": no file).
- **Touches:** R2, R3, R6.

### F2 [LOW/CONFIRMED] R4's "the field's own declared default passes" is unpinned
- **Where:** `core/capabilities.py`, `_unnamed`.
- **Failure scenario:** with the default branch removed, a field no rule names that holds its own
  non-JSON default is warned of as undecided; a newer FastMCP whose new field defaults to a model would
  warn on every start. `test_a_field_no_rule_names_is_checked_by_the_generic_rule` cannot tell: its
  value is already undecided.
- **Evidence:** `reviewer/reach_generic.log`: HEAD `warnings: []`; mutant U-default-not-accepted
  `warnings: ["FunctionTool field 'task_config' of FastMCP 4.1.4 has no rule …"]`.
- **Touches:** R4.

### F3 [LOW/CONFIRMED] Some refusals by a field's rule are unpinned; without their guards an inert value the rule refuses loads
- **Where:** `core/capabilities.py`: `_same` (the set comparison, the dict key order), the alias
  `__module__` check, the `Literal` argument check, the alias origin walk (both alias kinds).
- **Failure scenario:** HEAD refuses and the mutant loads, with no capability code run, for
  `tags={'planted'}`, a renamed `task_config` state key, `Literal[<str subclass>]`, an alias origin of
  the capability's own object, a `__module__` that is a `str` subclass. No code runs before a call, but
  R2's refusal is lost.
- **Evidence:** `reviewer/reach.log` (S-set-ne-dropped, S-dict-keys-never, R-literal-item-never,
  R-origin-unwalked, R-genericalias-origin-dropped, R-parts-module-dropped, R-state-key-never with a
  non-colliding key); each survives the sweep.
- **Touches:** R2, R6.

### Coverage observations (in the routed sweep, not findings)
Survivors that are equivalent on FastMCP 4.1.4 or guard instance state that is no field; each reach
probe loads with zero operations: S-seen-never, S-len-never, S-set-scalars-dropped,
S-model-branch-never, S-other-accepted, S-slotless-accepted, D-validated-factory-never,
R-empty-dropped, T-fields-set-name-never, T-private-privates-dropped. They fall inside the module
sweep routed below, which kills each or records it equivalent with why; none is seeded this cycle.

### Out of Scope: F4, the return-type rule refuses some annotations FastMCP serves (seeded)
The `return_type` allowlist refuses a `NewType`, a `type X = …` alias, a bare `typing.Dict`/`List`,
`Annotated[int, annotated_types.Gt(0)]` and a `typing_extensions.TypedDict`, which FastMCP builds,
serves and calls and `develop` loads (`reviewer/probe_shapes.log`, `probe_defaults.log`,
`probe_load_newtype.log`). Reproduced, but not a defect of this cycle's contract: the rule table was
ruled at plan sign-off (GOAL Q2: "the rules are ruled at the plan gate"), `AGENTS.md` §7 documents the list, no
R-ID asks these shapes to load, and R5 holds. Widening the list needs an inertness decision per shape
(a `type X = …` alias evaluates capability code lazily), which is shaping, not remediation. Seeded as
`issues/capability-tool-return-type-shapes.md` with a `ROADMAP.md` entry in Part I's trade-offs group
(`dfff3e8`). The maintainer may instead rule it in scope at sign-off.

### Notes (not findings)
- **Sibling `capability-reload-after-failure`:** a refusal of a tool changed by code other than the
  refused capability's (a core tool, an earlier capability's) is not undone by the registry cut-back,
  so a retry refuses again with "the registry holds …", naming the retry's first capability; a second
  `load()` in one process also refuses members on their instructions listing, their modules cached.
  The sibling's ground; whichever lands second keeps both contracts (GOAL, Notes).
- **Forward risk, not reproducible here:** the default rule compares eleven fields to their declared
  defaults. If a FastMCP 4.x within range began filling one from `Tool.from_function`, every capability
  would be refused on a git install, which does not read the lock; the suite sees it only on a
  re-lock. For the maintainer's attention at sign-off.

## Routing (to build)

Each finding goes as a property, both ways, over its whole domain. The fix reopens P1, which P2 built
on, so build retunes P2's gate as well.

- **F1 + F3, one class: every refusal the tool rules can make is held by the suite.** Refuse: every
  value a field's rule refuses, at every depth (`_tool_violation`, `_same`, `_json_violation`,
  `_return_type_violation`, the instance-state checks), is refused with its own wording beside each
  member set, running none of its code, and the registry cut back. Accept: every value the rules
  accept today still loads and serves unchanged (the members, `test_served_surface_matches_baseline`,
  the inert-shapes test), and a cyclic alias loads and the load returns (the liveness side, pinned).
  Routed as a mutant sweep over every decision of the tool-rule code in `core/capabilities.py`, each
  mutant run in both eras, each survivor killed or recorded equivalent with why (the coverage
  observations above included). No decision here is computed in two places, so no structural fix
  comes first.
- **F2: R4's generic rule, both ways.** A value of a field no rule names that is JSON-like at every
  depth, or equal to that field's declared default, passes with no warning; any other value is served
  undecided with exactly one warning per field per process; neither refuses. Pin the default branch
  with a non-JSON default.
- **F4:** not routed; seeded (above).

## Human-gate triggers

- **Triggered.** F1–F3 are CONFIRMED on `core/capabilities.py`, a path on § Invariants'
  high-blast-radius list. The maintainer's explicit sign-off is required before `code-publish`,
  whatever later cycles find; it holds until publish.

## Optional completeness sub-pass (separate reviewer; may see TECH.md)

- Not run this cycle.
