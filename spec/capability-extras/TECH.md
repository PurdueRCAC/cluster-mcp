---
slug: capability-extras
title: Capabilities you don't have shouldn't be tools you see
kind: feature
appetite: big
status: in_progress
branch: feature/capability-extras
base: develop
current_phase: P5
last_updated: '2026-10-31'
phases:
- id: P1
  name: The capability contract; Slurm and RCAC register through the entry-point group
  status: done
  satisfies:
  - R2
  - R5
  - R6
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 2
  verify: sh spec/capability-extras/verify/p4.sh && sh spec/capability-extras/verify/p1.sh mutants && uv run python -I spec/capability-extras/remediation/F7-mutant-alternatives.py
- id: P2
  name: The storage resource belongs to the RCAC member; no core module names a member
  status: done
  satisfies:
  - R3
  - R7
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/capability-extras/verify/p2.sh
- id: P3
  name: A capability that fails to load stops startup, naming its distribution
  status: done
  satisfies:
  - R8
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: sh spec/capability-extras/verify/p4.sh phase && sh spec/capability-extras/verify/p3.sh phase && sh spec/capability-extras/verify/p3.sh mutants && sh spec/capability-extras/remediation/F1-contribution-refusal.sh && sh spec/capability-extras/remediation/F4-load-refusal.sh
- id: P4
  name: The extras, the core alone, and the compat root that keeps every tool
  status: done
  satisfies:
  - R1
  - R4
  - R5
  - R9
  - R10
  depends_on:
  - P3
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: sh spec/capability-extras/verify/p4.sh
- id: P5
  name: The whole cycle's gates on the finished tree, the recipe on this head, the deferral ledger
  status: in_progress
  satisfies:
  - R6
  - R9
  - R10
  depends_on:
  - P4
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: sh spec/capability-extras/verify/p5.sh phase && sh spec/capability-extras/verify/p5.sh recipe && sh spec/capability-extras/verify/p5.sh mutants && uv run --no-project python -I spec/capability-extras/remediation/P5-ledger-headings.py && sh spec/capability-extras/verify/p5.sh full && uv run --no-project python -I spec/capability-extras/remediation/F3-timeout-approval.py
review:
  last_reviewed_commit: 2c5ceda
  verdict: changes-requested
  blocked_reason: F1 SystemExit and F2 import-timing escape R8; F3 sort outside refusal; F4 surviving mutants
  cycle: 2
---

# TECH.md — Capabilities you don't have shouldn't be tools you see

The **context engine and finite-state machine** for building this feature. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/capability-extras/TECH.md`); the
per-phase checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** [`research/00-digest.md`](research/00-digest.md) + briefs.

## Frontmatter field reference

- `status` (top): `planned | in_progress | blocked | in_review | done` (`done` is stamped by
  `code-publish` after confirmation, just before landing — the terminal state of the retained record)
- `appetite`: `small | big` — caps phase count and build-iteration budget (circuit breaker).
- `branch`, `base`: the cycle's branch (prefix per GOAL `kind`, from the profile's `branches`) and the
  profile's `base`.
- phase `status`: `pending | in_progress | done | blocked`
- `satisfies`: GOAL R-IDs this phase delivers (traceability anchor for `code-review`).
  **Artifact-deliverable R-IDs.** Some requirements are met by a *committed document* — a research
  audit, a protocol doc, an assessment — not by CLI-observable behaviour. Attach such an R-ID to the
  phase that produces and commits the artifact, and give that phase a content `verify:`
  (`test -f …`, a `grep -q` for the sections that must exist) rather than forcing a CLI drive.
  **Say so in the phase body**, because it changes who can grade it: `code-review` blinds its reviewer
  to all of `spec/`, so an R-ID whose evidence lives there is graded by the *orchestrator*, not the
  blind reviewer. Naming it in `TECH.md` is what lets the review skill route it correctly instead of
  reporting an unverifiable requirement.
- `depends_on`: phase ids that must be `done` first (a phase is actionable only when met).
- `parallel`: `true` only for genuinely independent, non-coupled work (docs, tests, isolated leaf
  modules). Any phase touching the profile's `coupled core` is always `false`.
- `hammerable`: `false` marks a correctness/security phase that scope-hammering must **never** cut.
- `hill`: `uphill` (still figuring it out) → `crest` (unknowns resolved) → `downhill` (just
  executing). A phase stuck `uphill` across builds is a raised hand → escalate to the human.
- `attempts`: durable failed-verify counter (absent = 0), bumped by `set_phase.py --phase P<n>
  --record-attempt` on every red verify gate; `next_phase.py` warns at ≥3 — the circuit breaker
  runs on this file, not on session memory.
- `verify`: the exact command that proves the phase (prefer driving the real CLI, not just tests —
  wrap CLI drives in the profile's `throwaway environment` helper, `<helper> sh -c "…"`, so they hit
  a disposable instance, never the developer's real data). A gate carrying `$( )` or quoting the
  calling shell would mangle is set with `set_phase.py --verify-file PATH`, not `--verify`.
- `review.cycle`: completed review passes, auto-incremented by every `set_phase.py --verdict …`;
  REVIEW.md's "Cycle {n}" mirrors it and the ≤3-cycle bound is graded against it. `--verdict approved`
  also clears `review.blocked_reason` unless one is passed explicitly.

## Conventions (apply to every phase)

- Commit conventions, code style, and load-bearing invariants come from the repo's `AGENTS.md` — it
  is the constitution. Walk the sections of its § Invariants that this change touches; that is the
  curated footgun checklist.
- One phase per `code-build` invocation by default; one atomic commit containing **both** the code and
  the `TECH.md` state change. The branch commit subject is code-build's (`$KB/skill/code-build.md` →
  Step 6), not restated here; branch commits are squashed away at `code-publish` per the profile's
  `landing`. Trailers follow the profile's `branch commits`.
- The last phase carries the standing last-phase items: the deferral ledger (`code-plan` Step 6.8),
  and every item the previous cycle's last phase carried for a project-level obligation (mpsearch's
  `## Times` quote, taken as `code-build` Step 4 says). A plan that drops one says why in `PLAN.md`.
- A PR body (when the profile's `landing` opens one) ends with an attribution naming the actual
  harness, model, and variant.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`): the
  help text, docs, or generated files it names change **in the same commit**.

**This cycle's own conventions.**

- Gates live in `spec/capability-extras/verify/`: `p<n>.sh [phase|mutants|full|…]`, each mode
  runnable alone (a mutant run targets only its phase's checks). The design they pin (the
  `Capability` fields, `installed()`, `create_mcp_server(..., capabilities=...)`, the message
  `cannot load capability <dist>: `, the entry points `<name> = cluster_mcp.<name>.capability:CAPABILITY`,
  orders 100 and 900) is PLAN §2; a gate is amended only with the design, never to pass.
- Each phase keeps true the AGENTS.md and README.md text its change touches (§ Conventions: one
  commit). R10's "same commit" is the cycle's squash landing, which carries every phase.
- New tests carry `@mark.unit` or `@mark.integration`; every process launch goes through
  `bin/sandbox.sh`; new stdio drives set `FASTMCP_CHECK_FOR_UPDATES=off`; no comment or test name
  carries a spec id (`tests/test_hygiene.py`).
- A test function or mutation case that disappears fails `baseline.sh`, unless
  `verify/retired.txt` names it with its reason (commit body says it too).
- Mutation cases are added to `tests/mutants.py` with ids exactly as the gates name them; a case
  anchored on a moved line is re-anchored with its id and `why` kept.
- Run `uv sync --locked` after any `pyproject.toml` edit: entry points reach an editable install
  only through a sync.

---

## Phase P1 — The capability contract; Slurm and RCAC register through the entry-point group
**Satisfies:** R2, R5, R6 · **Depends on:** —
**Goal:** the core composes tools and base instructions from the capabilities loaded through
`cluster_mcp.capabilities` at startup; with every member installed the surface is today's.

- [x] `C/capabilities.py` (new): `GROUP`, `Capability`, `Loaded`, `CapabilityLoadError`, `load()`,
      `installed()`, `composed()` as PLAN §2.1 — the type checks, a failing `ep.load()` or tools
      import, tool attribution by module, the instructions-list-exactly-its-tools check, the
      duplicate tool and capability-name checks, the rollback, the message shape. (Resource checks
      land in P2; startup wiring in P3.)
- [x] `C/tools/__init__.py`: drop the two member imports; `CORE_TOOLS` and `CLOSING_TOOLS`.
- [x] `C/server.py`: drop the member imports and `SERVER_INSTRUCTIONS`; `base_instructions()`;
      `create_mcp_server(..., capabilities=None)` registering tools and resources in today's listing
      order (PLAN §2.3: load order, `CLOSING_TOOLS` last; primaries then aliases). Capability
      resources are served from this phase (the planted capability carries one); the core's storage
      entry stays until P2.
- [x] `S/capability.py`, `RC/capability.py` (orders 100, 900; no resources yet); the entry point in
      each member's `pyproject.toml`; `uv sync --locked`; docstrings of the two member
      `instructions.py` (texts untouched).
- [x] `tests/conftest.py` loads once; `tests/test_capabilities.py` with the P1 ids `p1.sh` names;
      the seven `SERVER_INSTRUCTIONS` importers, `test_instructions.py` (members from the loaded
      capabilities), `test_registry.py` re-pointed; mutants re-anchored; new cases
      `capability-order-from-discovery` (the composer keeps discovery order),
      `capability-tools-unfiltered` (the server registers all of `TOOL_REGISTRY`, ignoring the given
      set), `core-imports-member-by-name` (a member import back in `core/tools/__init__.py`),
      `capability-duplicate-tool-allowed` (the duplicate-tool check removed),
      `capability-tools-import-swallowed` (a failing tools import skipped) and
      `capability-instructions-unchecked` (the text check removed).
      *Amended at build:* `core-imports-member-by-name` needs a target this phase, so
      `test_core_imports_no_member` (named by `p2.sh`) lands here, its AST scan skipping
      `C/resources.py`, whose storage handler still imports the RCAC member's helper until P2.
- [x] AGENTS.md: §7 and §9 rewritten (PLAN §3), the footgun and repository-map rows for
      `tools/__init__.py` and `server.py`, the high-blast-radius list widened with
      `core/capabilities.py` and both `capability.py` files.
- **Verify:** `sh spec/capability-extras/verify/p1.sh` (until review cycle 1; see below).
- **Touches:** `C/capabilities.py`, `C/tools/__init__.py`, `C/server.py`, `S/`, `RC/`, both member
  `pyproject.toml`, `uv.lock` (if it moves), `tests/`, `AGENTS.md`.

### Reopened at review cycle 1 — F2 (R5): a mutant sweep over every decision of the loader

*Amended at remediation (2026-10-31).* REVIEW.md F2: three documented refusals of `load()` survived
behaviour-changing mutants (the stray-tool refusal, the same-capability duplicate, attribution to
"that module or below it"). The class is every decision in `C/capabilities.py`, the ones F1's fix
adds included, so this phase is committed with P3 in one commit, as if `bundle` had been passed: the
sweep must cover the decisions F1 adds, in the same file.

- [x] Every decision enumerated by parsing the file (each `if`, conditional expression, boolean
      operator, comparison, comprehension condition, `except` clause and sort key: 41, one per
      line) and mutated: 56 new cases in `tests/mutants.py` (`capability-message-not-one-line` …
      `capability-composition-tie-unbroken`), plus the six P1–P3 cases planting into the file, two
      of them re-anchored where F1 moved their line (`capability-tools-unfiltered` on `serve(...)`
      in `C/server.py`; `title-at-add-tool` now plants into `C/capabilities.py`, where `serve()`
      adds each tool), ids and `why` kept. The P1–P3 capability cases gain the rows beside every
      member set as targets.
- [x] Each new case's targets are the rows of its killing test beside every member set
      (`MEMBER_SETS`: core only, slurm, rcac, both; `every_set()` in `tests/mutants.py`), and the
      sweep runs every case in both eras. New set-wide tests in `tests/test_capabilities.py`, each
      asserting the whole refusal message: a tool below the tools module attributed to it; a tool in
      a sibling module sharing its prefix refused as outside it; a tool registered twice by one
      capability; a tool name taken by the core or an earlier capability; a capability name taken;
      a resource URI taken by the core, its alias, the capability itself or an earlier one; sixteen
      malformed capabilities and resources (`MALFORMED`); the three instruction mismatches; a failing
      capability module and a failing tools module with their causes; a hand-built entry point named
      by its value; the load order by (distribution, entry-point name); a capability whose tools
      module was already imported keeps its tools. `load_error()` now fails a test on any exception
      that is not a `CapabilityLoadError`, so a mutant that lets one escape fails with a reason.
- [x] Equivalent mutants, recorded with why in the sweep (`EQUIVALENT`) and run against the whole
      capability selection in both eras to show they pass: `installed()`'s cache dropped (a second
      load registers nothing new); the scratch assembly of each tool dropped (every tool reaching it
      has a name the three name refusals already made unique, and FastMCP 4.1.4's `add_tool` refuses
      only a held key or versioned beside unversioned under one name; kept as the path a later
      FastMCP's refusal would take); the scratch server without the core's tools (a core-named tool
      is refused before the assembly); the listing check's duplicate clause dropped (names are
      distinct by then).
- **Verify (retuned at remediation):** P1 is earlier than P4, the latest done phase, so its gate is
  P4's, then the frozen P1 mutants, then the class checker:
  `sh spec/capability-extras/verify/p4.sh && sh spec/capability-extras/verify/p1.sh mutants && uv run python -I spec/capability-extras/remediation/F2-mutant-sweep.py`.
  `F2-mutant-sweep.py coverage` fails on any decision of the file no mutant edits (seen red with
  two cases and one equivalent withheld: lines 221, 229 and 285 reported).
  *Observed at remediation (2026-10-31), P1 and P3 run together, each distinct step once (P3's
  `p4.sh phase` is P4's `phase`; `p1.sh mutants` and `p3.sh mutants` are subsets of `p5.sh
  mutants`, which ran instead):* `p4.sh phase` green (pyprojects, docs, coreonly for core, slurm,
  rcac and both, probe's five installs and both compares, baseline); `full` 3043 passed and 14
  skipped in each era (the 14 are the bash 4.1 `need_shell` rows of
  `test_site.py::test_remote_read_ignores_exported_shell_options`, which CI runs); `p5.sh mutants`
  122 killed, none survived, 3 controls reported; `F2-mutant-sweep.py`: coverage 41 of 41
  decisions, 63 of 63 cases killed in each era, the 4 equivalents passing the 555-test capability
  selection in each era. The three known survivors are killed beside every member set in both
  eras: `capability-stray-allowed`, `capability-same-capability-duplicate-allowed`,
  `capability-attribution-exact-module`.

### Reopened at review cycle 2 — F4 (R5, R6, R8): every alternative of every decision, not one

*Amended at remediation (2026-10-31; the route was ruled at the human gate: a scoped fix, verified by the foreman,
then landed).* REVIEW.md cycle 2, F4: four mutants survived cycle 1's sweep, each a sibling of a
decision that had one mutant (the composition's tie by capability name, `installed()` caching a
failed load as no capability, the load above the `--generate-token` branch, the opening tools'
partition taken above the `transfer` import). The class is every alternative of every decision in
`C/capabilities.py`, of the load's place in `C/__init__.py` and of the opening/closing partition in
`C/tools/__init__.py`. P1 and P3 are committed together, as in cycle 1: the sweep must cover the
decisions P3's fix adds, in the same file.

- [x] The decisions and their alternatives, by parsing the three files (the checker's docstring
      gives the rules): each condition always, never and negated; each boolean operator without
      each operand and with the other; each comparison negated (an ordering one to every other
      ordering); each `except` to `Exception`, to `BaseException` and re-raising; each type of an
      `isinstance` tuple dropped; each sort key to every key of one or two of its fields (the load's:
      distribution, entry-point name, value; the composition's: order, distribution, name, tools
      module), to no sort and to the reverse; `installed()` caching a failure as no capability or as
      its error; the registration check begun after the entry point loads or after the tools import;
      `run()`'s load at every other statement boundary of its body and of its `try`, and not at
      all; the partition at every other index of `CORE_TOOLS` (0-7), before every other tool-module
      import, and with its halves exchanged. 218 alternatives, each as one tree.
- [x] 177 new cases in `tests/mutants.py` (`alternative(...)`, `partition_alternative(...)`), each
      killed beside every member set: the composition and load order by
      `test_composition_breaks_ties_by_distribution` and
      `test_entry_points_load_by_distribution_then_name_not_value`, the cache by
      `test_a_failed_load_is_not_cached` (one, `installed()` reloading when the cached load found
      nothing, only beside the core alone), the placement by
      `test_a_token_is_generated_before_any_capability_loads` and
      `test_capabilities_load_before_the_mode_ladder_beside_every_set`, the partition by
      `test_the_listing_opens_and_closes_with_the_core_tools_by_name` (the core tools by name, not
      from `CORE_TOOLS`/`CLOSING_TOOLS`), the rest by the load's tests. Twelve cycle-1 cases
      re-anchored where the fix moved their lines, ids and `why` kept (but
      `capability-named-by-missing-distribution`, whose mutant now refuses rather than raises: its
      `why` is now `is not named by its value`); three gain per-set rows
      (`capability-order-from-discovery`, `capability-composition-tie-unbroken`,
      `capability-load-after-ladder`).
- [x] `tests/conftest.py` no longer stops collection when the installed capabilities fail to load:
      the header names the failure and each test that needs them fails with it. Without that, a
      mutant that refuses the members could only die at collection, which the runner counts as a
      survivor. `test_capabilities.py` imports `test_instructions` (which loads at import) inside
      the one test that needs it, for the same reason.
- [x] Equivalents, each run against the whole capability selection in both eras: two of F2's
      (the scratch server without the core's tools; the listing check's duplicate clause), and
      six new (`!= 1` for `> 1` in the listing's twice-count; `BaseException` for `Exception` where metadata or entry points are
      read, four sites, none of which runs a capability's code; the CLI catching every `Exception`
      where the load raises only a `CapabilityLoadError` or a `KeyboardInterrupt`). F2's other two
      are now killed and are cases: `installed()` uncached (the cache is pinned) and the tool
      assembly dropped (a `FunctionTool` of a capability's own class runs its code when FastMCP
      reads it). Set-equivalents, whose rows of those sets must pass under the case: the eleven
      partition-index cases beside the core alone (the listing is the core's tools in registration
      order wherever the partition falls; its halves exchanged is killed there too), and
      `installed()` reloading when empty beside each member set (the cache holds whenever a member
      loaded).
- **Verify (retuned at review cycle 2):** `F7-mutant-alternatives.py` supersedes
  `F2-mutant-sweep.py`, which stays as cycle 1's record and leaves the gate:
  `sh spec/capability-extras/verify/p4.sh && sh spec/capability-extras/verify/p1.sh mutants && uv run python -I spec/capability-extras/remediation/F7-mutant-alternatives.py`.
  Its `coverage` step fails on any alternative no case or equivalent mutates, and on any swept case
  without a row beside each member set; seen red with the four survivors' alternatives withheld
  and `capability-load-after-ladder`'s per-set rows dropped (each named).
  *Attempt 1 (red, 2026-10-31):* coverage ok and 241 of 241 cases killed in each era, but every
  equivalent failed: the checker's own child lost `HOME` (it read the environment after clearing
  it). Fixed. *Attempt 2 (red):* its equivalents step then showed
  `capability-partition-halves-exchanged` killed beside the core alone too (the site context tool
  moves first), so it is a four-set case, not a set-equivalent; every other equivalent and
  set-equivalent passed in each era.
  *Observed at remediation (2026-10-31), P1, P3 and P5 together, each distinct step once on the
  final tree, the earlier runs standing in where a step's inputs did not change:* `p4.sh` (all
  modes): `phase` green (lock check, pyprojects, docs, coreonly for core, slurm, rcac and both,
  probe's five installs and both compares at 24 tools, 4 resources and 1477 characters, baseline
  with 452 functions and 417 cases kept and 0 retired, P4's tests 1281 passed in each era),
  `mutants` (`core-imports-member-by-name` killed, 3 controls), `full` 3660 passed and 14 skipped
  in each era (the bash 4.1 `need_shell` rows, which CI runs) with `cluster-mcp --help` exit 0.
  `p1.sh mutants` and `p3.sh mutants` stand in by `p5.sh mutants`, their superset: 299 killed, 3
  controls. `F7-mutant-alternatives.py` all, on the final tree: see P5's record.

## Phase P2 — The storage resource belongs to the RCAC member; no core module names a member
**Satisfies:** R3, R7 · **Depends on:** P1
**Goal:** `cluster://storage` and its `rcac://storage` alias are the RCAC capability's, served only
with it; the core's resources and open set are its context URIs; the core names no member.

- [x] `C/resources.py`: `legacy_aliases()`; the core's registry is the context entry and its alias;
      the storage entry and its member import go; `OPEN_RESOURCES` unchanged.
- [x] `RC/resources.py` (new): the storage handler and entry, moved verbatim; `RC/capability.py`
      carries `(STORAGE, *legacy_aliases((STORAGE,)))`.
- [x] `C/capabilities.py`: the resource checks (a dict with `str` `uri`, `name`, `description`, a
      callable `handler`, `executor` exactly `True`; URI unique against the core and earlier
      capabilities).
- [x] `tests/test_capabilities.py::test_core_imports_no_member` stops skipping `C/resources.py`,
      and AGENTS.md § Testing's note of the skip goes with it (amended at P1's build).
- [x] Tests: `test_storage_resource.py` reads served resources from composed servers;
      `tests/test_capabilities.py` P2 ids; mutants re-anchored; new cases
      `storage-resource-unconditional` (the core registers the storage entry again) and
      `capability-resource-open-allowed` (the executor check removed).
      *Amended at build:* a core registry entry at `cluster://storage` is now refused at load as a
      duplicate of the RCAC capability's, which a mutant child sees as a collection error (a
      survivor), so `storage-resource-unconditional` plants in `C/server.py` instead: the server
      lists every installed capability's resources whatever set it is given. A capability
      resource's `executor` flag no longer decides openness (only the core's `OPEN_RESOURCES` does,
      and the loader refuses a flag that is not `True`), so `storage-read-left-open` and
      `alias-flag-hand-set-open` re-anchor on the core's open set, which they grow by the storage
      URIs; `alias-handler-differs` gives every alias a constant handler, since each
      `legacy_aliases()` call now derives one alias and a handler swap between entries no longer
      applies. Ids, targets and `why` are kept.
- [x] AGENTS.md §8 (PLAN §3, deviation row 1) and the `resources.py` repository-map row (with the
      rows for `capabilities.py`, the new `cluster_mcp.rcac.resources` and `cluster_mcp.rcac.capability`,
      §7's refusal list and helper home, and § Testing's notes, which the move made false).
- **Verify:** `sh spec/capability-extras/verify/p2.sh`.
- **Touches:** `C/resources.py`, `C/capabilities.py`, `C/server.py`, `RC/`, `tests/`, `AGENTS.md`.

## Phase P3 — A capability that fails to load stops startup, naming its distribution
**Satisfies:** R8 · **Depends on:** P2
**Goal:** `run()` loads before the mode ladder; a failure is reported as an SSH connect failure is
(stderr once, the stdio error answer until EOF) and exits 5; `--help` and `--version` unaffected.

- [x] `C/__init__.py` `run()`: `installed()` after the `--generate-token` branch, before
      `_resolve_exec_mode()`; `CapabilityLoadError` → `_report_startup_failure` → `StartupFailure`.
      `_resolve_exec_mode()` is not edited (§4, human gate).
- [x] `C/startup.py` docstring; AGENTS.md §4's startup-refusal bullet and §7 name the message.
- [x] Tests: `tests/test_startup.py` P3 ids (planted dist-infos prepended to `PYTHONPATH`, both
      eras, the raw wire; `run_app` for the order; an HTTP start that exits 5 before binding); the
      `rcac-mcp` command once. New cases
      `capability-load-failure-swallowed` (the loader skips a failing entry point) and
      `capability-load-after-ladder` (the load moved after `_resolve_exec_mode()`).
- **Verify:** `sh spec/capability-extras/verify/p3.sh` (until review cycle 1; see below).
- **Touches:** `C/__init__.py`, `C/startup.py`, `C/capabilities.py` (if a check needs it), `tests/`,
  `AGENTS.md`.

### Reopened at review cycle 1 — F1 (R8, Q5): whatever a capability declares fails at the load or not at all

*Amended at remediation (2026-10-31; the foreman ruled F1 a fix as judge at the human gate on the
high-blast-radius paths).* REVIEW.md F1: a resource FastMCP rejects passed the load's shape checks
and failed while the server was built, after the mode ladder, exit 2, unanswered on stdio. The class,
read off how the server builds tools and resources from a capability: every way FastMCP refuses a
resource (`server.resource(...)`: a URI that is not a URL, a parameter on a static URI, a template
its handler does not match, a method's `self`, a handler that cannot carry FastMCP's metadata), two
URIs FastMCP keys alike (`a b` and `a%20b`, a scheme's case, surrounding space), which a served server
(`on_duplicate` "warn") would let replace one another silently, and a tools import that registers
something the load cannot read (not a `FunctionTool`, a tool with no module), which raised out of the
load uncaught (exit 6, unanswered). Committed with P1 (see P1's amendment).

- [x] `C/capabilities.py`: `serve(server, tools, resources)`, the one way every server registers
      tools and resources; `create_mcp_server` calls it. `load()` assembles each capability's
      tools and resources through it on a scratch server (`_scratch()`: the core's tools and
      resources, `on_duplicate='error'`) that keeps every earlier capability's, and refuses what it
      refuses: `its resource <uri> cannot be served: <cause>` (`its tool …` likewise). It refuses a
      registry entry that is not a `FunctionTool`, and turns any other exception while loading a
      capability into the refusal, rolling the registry back.
- [x] Pins (each seen red on the unfixed loader): `REJECTED` in `tests/test_capabilities.py`, nine
      kinds, refused at load beside every member set
      (`test_what_a_server_would_refuse_is_refused_at_load`, 36 rows); controls showing FastMCP
      refuses each resource kind on a bare server, and keys each collision as one; a URI keyed as an
      earlier capability's; a capability that loads served whole. `tests/test_startup.py`
      `test_a_contribution_the_server_would_refuse_stops_startup`: each kind through the CLI in
      `local` mode over the raw wire (each request answered, exit 5), with stdin closed (exit 5 at
      once) and over HTTP (exit 5 before binding), 27 drives, each in its own process group killed
      whole past its bound. Red first on the unfixed code: 27 of 27 failed — exit 2 for the URL and
      template kinds, exit 6 for the method, no-metadata and tool kinds, and for the two collisions
      a server that started and served (exit 0 on stdio; over HTTP it bound and was killed at 60 s).
- [x] AGENTS.md §7 narrowed to what the load decides (and that the instructions budget is not one
      of them: a base too long for it is refused at build, as a budget too small, whatever made it
      long); its restatements in the repository map's `capabilities.py` row, §8's capability-resource
      bullet and § Testing's `test_capabilities.py` and `test_startup.py` rows follow.
- **Verify (retuned at remediation):** P3 is earlier than P4, so P4's phase checks, then the frozen
  P3 checks, then the class checker:
  `sh spec/capability-extras/verify/p4.sh phase && sh spec/capability-extras/verify/p3.sh phase && sh spec/capability-extras/verify/p3.sh mutants && sh spec/capability-extras/remediation/F1-contribution-refusal.sh`.
  The checker evaluates the property over a generated domain (19 URIs × 11 handlers, every ordered
  pair of 11 URIs in one capability and split across two, the two odd tools modules) beside each
  member set: each case is refused in one line naming its capability, or a server built from what
  loaded serves every declared resource under its own key. Seen red on the unfixed loader and
  server (1,233 violations: servers that failed to build with `ValueError`, `ValidationError`,
  `AttributeError` and `TypeError`, collisions served as one, and loads that raised).
  *Observed at remediation (2026-10-31), with P1 (see there):* `p3.sh phase` green (planted
  `broken`'s eleven cases and the HTTP one, planted `extra`, docs p3, P3's tests in both eras);
  `F1-contribution-refusal.sh` green: 432 accepted and served whole, 1,292 refused naming the
  capability over 4 member sets, then its pins in both eras.

### Reopened at review cycle 2 — F1-F3 (R8, Q5): whatever a capability's code does while it loads is refused, naming it

*Amended at remediation (2026-10-31; the route was ruled at the human gate).* REVIEW.md cycle 2: a capability
that exits while loading bypassed the refusal (F1: `SystemExit` is not an `Exception`); a tool its
entry point's import registered outside its tools module escaped the stray and non-tool guards
(F2: `before` was taken after `ep.load()`); and ordering ran outside the refusal (F3: a
distribution with no `Name` made the sort raise `TypeError`). The class, read off the load: every
point a capability's own code runs (its entry point's import, its tools module's and the modules
either imports, the load's reading of what it declared, FastMCP's reading of its tools and
handlers) and anything it can raise or exit with there; every registration since its load began,
whoever imported what; and discovering and ordering. Committed with P1 (see P1's amendment).

- [x] `C/capabilities.py`: one exit for a failure, `except BaseException`: the registry is cut
      back, a `CapabilityLoadError` or `KeyboardInterrupt` is raised as it is, anything else is
      refused naming the capability (`_cause`: the type and its text, the type alone when its text
      is empty or its `__str__` raises or exits). The assembly's two clauses catch the same, so a
      tool or resource that exits is refused as one that cannot be served. `before` is taken before
      `ep.load()`, and the two guards say `loading it registered …`. `_identity()` names each entry
      point's distribution by its `name` (a missing `Name` read as none, whether this Python warns
      or raises `KeyError` for it), its entry point's value when it has none or the metadata cannot
      be read, and such a distribution is refused before any of its code runs. The load orders
      `_Entry` tuples (that name, the reason, the entry point) by that name and the entry-point name,
      so ordering cannot raise and needs no entry point to be hashable. `_discovered()` refuses a distribution whose entry points cannot be read,
      named by its `Name` or its path. `installed()` is unchanged.
- [x] Pins (each seen red on `2c5ceda`'s code, below): `test_capabilities.py`
      `test_a_capability_that_cannot_load_is_refused_naming_it` (`UNLOADABLE`: eight raised or exit
      kinds at five times, six registration timings, three nameless metadata, beside every member
      set), `test_a_keyboard_interrupt_while_loading_still_interrupts`,
      `test_a_capability_whose_entry_point_imports_its_tools_loads`,
      `test_entry_points_that_cannot_be_read_are_refused_naming_their_distribution`,
      `test_a_discovery_that_fails_with_every_distribution_readable_is_refused_naming_the_group`;
      `test_startup.py` `test_a_capability_that_cannot_load_stops_startup` (each `UNLOADABLE` kind
      over the raw wire, with stdin closed and over HTTP, each drive in its own process group),
      `test_a_keyboard_interrupt_while_loading_still_interrupts_the_start`, and in process beside
      every set `test_a_keyboard_interrupt_while_loading_interrupts_the_start_beside_every_set`.
- [x] AGENTS.md §7 states what the load decides (a list: metadata, code that raises or exits and
      when, the `Capability` and its resources, registrations whenever made, names and URIs taken
      and the listing, what FastMCP refuses), discovery's refusal and the command line's earlier
      failure at import, `KeyboardInterrupt`, and `installed()`'s cache; §4's refusal bullet, the
      repository map's `capabilities.py` row and § Testing's `test_capabilities.py`,
      `test_startup.py` and `conftest.py` notes follow.
- [x] Class checker `remediation/F4-load-refusal.py` (+ `.sh`, which then runs the pins by id in
      both eras): the property over a generated domain beside each member set, in process: 17
      raised or exit kinds (an `Exception` with and without text, one whose text raises, one whose
      text exits, `SystemExit` with 0, 1, 3, 255, a string, none, bare, a float and a list,
      `GeneratorExit`, a `BaseException` of its own, a `BaseExceptionGroup`, `KeyboardInterrupt`)
      at 9 times, 5 nameless metadata (no `Name`, blank, spaces, no `METADATA`, not UTF-8; each
      capability would exit if its code ran), a tool and a non-tool registered from 6 places, and 4
      controls that must load: 174 kinds, 696 verdicts.
- **Verify (retuned at review cycle 2):**
  `sh spec/capability-extras/verify/p4.sh phase && sh spec/capability-extras/verify/p3.sh phase && sh spec/capability-extras/verify/p3.sh mutants && sh spec/capability-extras/remediation/F1-contribution-refusal.sh && sh spec/capability-extras/remediation/F4-load-refusal.sh`.
  *Attempt 1 (red, 2026-10-31), fixed in this remediation before any commit:* `p4.sh` (all modes)
  and `p3.sh phase` green, then cycle 1's `F1-contribution-refusal.py` failed every case: its
  hand-built entry points are unhashable and their distributions carry only a `name`, and the load
  first keyed a dict by entry point and read `metadata.get('Name')`. The load now orders `_Entry`
  tuples and reads `name`; every step reran from the start on the fixed tree (below). A pin for a
  `name` that raises `KeyError` (`test_a_name_missing_as_a_key_error_is_no_name`) came with it.
  *Observed (2026-10-31), on the fixed tree:* `p4.sh phase` stands in by P1's `p4.sh` run (all
  modes); `p3.sh phase` green (planted `broken`'s eleven cases and the HTTP one, `extra`,
  `bad-resource`, `shadow`, docs p3, P3's tests 1649 passed in each era); `p3.sh mutants` by
  `p5.sh mutants`; `F1-contribution-refusal.sh` green (432 accepted and served whole, 1292 refused
  naming the capability, over 4 member sets; its pins 78 passed in each era);
  `F4-load-refusal.sh` green (174 kinds beside 4 member sets, 0 violations; its pins 460 passed in
  each era). Red first on `2c5ceda`'s loader: the F4 checker found 592 violations over 148 of its
  174 kinds (`SystemExit` and other `BaseException`s escaping the load, nameless distributions
  raising `TypeError` from the sort or loading under the name `''`, registrations at the entry
  point's import loading unchecked or refused with an incidental `AttributeError`, interrupted
  loads leaving tools registered); the 26 that held are the 4 controls and the `Exception` kinds
  the old `except Exception` already refused with this text. The pins likewise: every `UNLOADABLE`
  row but the plain `RuntimeError` ones failed in
  process beside every set (e.g. `the load raised SystemExit, not a CapabilityLoadError`), and over
  the CLI each exit kind exited 0, 1 or 3 with nothing on stderr and no answer, `raises-base`
  exited 1 with a traceback, the entry-point-time strays and a blank `Name` started the server
  (exit 0 on stdio; over HTTP it bound and was killed at 60 s), and no `Name` exited 6 with
  `'<' not supported between instances of 'NoneType' and 'str'`. The in-process placement and
  interrupt-at-entry-point rows held on `2c5ceda` (its placement was right; F4's mutants kill
  them).

## Phase P4 — The extras, the core alone, and the compat root that keeps every tool
**Satisfies:** R1, R4, R5, R9, R10 · **Depends on:** P3
**Goal:** the members become the core's extras; a bare core install starts and serves the core;
the root installs every capability; the docs name the extras.

- [x] `packages/cluster-mcp/pyproject.toml` extras; root `dependencies = ["cluster-mcp[slurm,rcac]"]`
      (header comment, description); `uv lock`; `uv sync --locked` — one commit with the docs below.
- [x] `tests/test_core_only.py` (`integration`; session-scoped editable core-only environment under
      the sandbox, `VIRTUAL_ENV` dropped, offline); `harness.py` gains a resources listing for stdio
      drives if the test needs it; `tests/test_packaging.py` pins (the extras, the workspace
      sources, the root's `cluster-mcp[rcac,slurm]`, `Provides-Extra`).
- [x] README.md: the intro, Quick Start (`cluster-mcp[slurm,rcac] @ git+…#subdirectory=packages/cluster-mcp`,
      one `args` element), the install note, the inventory headings naming `[slurm]` and `[rcac]`
      (and that `[rcac]` goes with `[slurm]`), development `uv sync`; the three member READMEs;
      the Dockerfile comment.
- [x] AGENTS.md § Packaging, § Project and § Commands where they say the core carries the members,
      the release recipe's `post_verify` and its `install-probe` and `ci-mirror-no-index` caveats
      (PLAN §2.4).
- [x] *Amended at build (foreman's ruling, 2026-10-31):* `issues/unlocked-install-floors.md` and its
      `ROADMAP.md` Part III entry; § Packaging's `uv.lock` bullet and the recipe's `lock` caveat
      say what the lock pins (`uv sync`: development, CI) and what it does not (a `git+…` or
      `uvx --from` install, and the container image's `uv pip install`, which resolve within the
      declared ranges).
- *Also amended at build:* the edits made true more text than the list above names, each in this
  commit: AGENTS.md § Direction (the extras bullet says what has landed), the repository-map note,
  § Testing's rows for `test_packaging.py`, `test_core_only.py` and the harness's `Listed`; the
  README's upgrade-section compat sentence and the hosted section's install line; and
  `tests/mutants.py`'s upgrade-section anchor, re-anchored on that sentence with its ids and `why`
  kept. `test_core_only.py` carries a third test, the registry in the core-only environment.
- **Verify:** `sh spec/capability-extras/verify/p4.sh`.
  *Attempt 1 (red, 2026-10-31):* every step green but `probe.sh`'s compare of the root install's
  surface with `BASE_REF`'s: `outputSchema` of `run_command`, `list_directory` and `storage_paths`
  carries a `description`. The probe's `uv pip install` ignores `uv.lock` and resolved a newer
  pydantic from the cache than the lock pins, while `base.json` comes from a locked sync. The
  defect is the gate's: its compare mixed resolution modes. The evidence, each from one offline
  run under the sandbox:

  | Compared | Result |
  |---|---|
  | `BASE_REF`'s root, lock-free, vs this tree's root, lock-free | equal |
  | `base.json` (locked sync) vs this tree's root with the exported lock as constraints | equal |
  | `base.json` (locked sync) vs `BASE_REF`'s root, lock-free | differs exactly as the red |

  *Gate amended at the foreman's ruling (2026-10-31); the original compare mixed resolution
  modes.* `probe.sh` step 3 now makes two compares, both fatal: (a) lock-free, the root install
  against `BASE_REF`'s root installed the same way from the same offline cache in the same run
  (R9's reading: the old install line serves what it served before); (b) lock-pinned, the root
  installed with the snapshot's `uv.lock` exported as constraints against `base.json`. Each was
  seen red first under a description change planted into the probe's snapshot only. The attempt
  stays recorded.
- **Touches:** the four `pyproject.toml`, `uv.lock`, `README.md`, `packages/*/README.md`,
  `Dockerfile`, `AGENTS.md`, `tests/`; at the ruling, `verify/probe.sh`, `issues/`, `ROADMAP.md`.

## Phase P5 — The whole cycle's gates on the finished tree, the recipe on this head, the deferral ledger
**Satisfies:** R6, R9, R10 · **Depends on:** P4
**Goal:** every independent check passes on the finished tree, the release recipe's offline gate
steps pass on this head, and every deferral has its record.

- [x] Run `p5.sh phase` and fix what it finds in the phase that owns it (amend this file and say so
      in the commit body).
- [x] The deferral ledger: walk every earlier phase body, PLAN.md and REVIEW.md (if any) for "do not
      fix here", "known limitation", "deferred", "follow-up", "out of scope"; each must name an
      `issues/{slug}.md` (pre-shaped from the KB `ISSUE.md` template) with its `ROADMAP.md` entry
      (the gitignored security lane instead for a sensitive item). `p5.sh ledger`
      checks the links; the walk is this item's.
- [x] `p5.sh recipe`: build, `twine check --strict`, sdist hygiene on this head.
- [x] `verify/retired.txt` empty, or each line justified in its phase's commit body.
- **Verify:** `sh spec/capability-extras/verify/p5.sh`.
  *Observed at build (2026-10-31), each mode run alone on `0cf635f`'s tree, nothing to fix:*
  `phase` green on every step (pyprojects p4, imports, compose over 4 capability sets, docs p4,
  planted `extra` and 11 `broken` cases plus one over HTTP, coreonly for core, slurm, rcac and
  both, probe's five installs with the lock-free and lock-pinned compares at 24 tools, 4 resources
  and 1477 characters of instructions, baseline with 452 functions and 417 cases kept, 0 retired);
  `ledger` ok, and seen red first on a copy outside the worktree (a planted unseeded deferral, a
  seed dropped from `ROADMAP.md`); `recipe` built 4 wheels and 4 sdists, `twine check --strict`
  passed each, sdist hygiene clean; `mutants` 66 killed, none survived, 3 controls reported;
  `full` 2765 passed and 14 skipped in each era. The 14 skips are
  `test_site.py::test_remote_read_ignores_exported_shell_options`, which needs bash 4.1 or later
  (`need_shell`); the CI runner has it, and there `need_shell` fails rather than skips.
  The walk found two deferrals, each seeded and in `ROADMAP.md`: the runtime probe (GOAL Q2,
  `issues/capability-probe.md`, filed at the shape commit) and the lock that pins no user install
  (P4's ruling, `issues/unlocked-install-floors.md`). PLAN §5's member-without-an-entry-point risk
  is residual by design, and the FastMCP update check points at its existing seed,
  `issues/fastmcp-update-check.md`.
- **Touches:** whatever a failing check names; `issues/`, `ROADMAP.md` only for a deferral.

### Reopened at review cycle 1 — F3: the roadmap agrees that the timeout measurement is approved

*Amended at remediation (2026-10-31).* REVIEW.md F3: Part I's intro says the timeout measurement is
approved, its entry said it still waited for approval. It was approved on 2026-10-29.

- [x] `ROADMAP.md`, "A timed-out command may keep running after its call returns": its prose and
      its Horizon line say the measurement was approved on 2026-10-29. The sweep's other live site,
      `issues/timeout-process-cleanup.md`'s "Why it was deferred", gets a dated, append-only
      correction beneath it (`- 2026-10-29: the measurement was approved.`), its history kept.
- [x] This phase is also the cycle's last, so its frozen gate runs again on the remediated tree.
- **Verify (retuned at remediation):**
  `sh spec/capability-extras/verify/p5.sh && uv run --no-project python -I spec/capability-extras/remediation/F3-timeout-approval.py`.
  The checker reads every tracked Markdown file outside `spec/` for a claim that the measurement
  still waits for approval with no dated correction after it, and the entry and its Horizon line
  for the approval and its date. Seen red on `HEAD` (the entry's three claims, the seed's, and both
  missing statements).
  *Attempt 1 (red, 2026-10-31), stopped for the foreman's ruling:* every step green but `p5.sh
  ledger` — `phase` (pyprojects, imports, compose, docs, planted `extra` and `broken`, coreonly,
  probe, baseline), `recipe` (4 wheels and 4 sdists, `twine check --strict`, hygiene clean), `full`
  3043 passed and 14 skipped in each era, `mutants` 122 killed with 3 controls, and the F3 checker.
  `ledger.py` reports `REVIEW.md: defers without a seed: ### Out of scope (recorded, not
  blocking)`: it reads the review's heading as a deferral block of its own. The red is on the
  review commit `54ff4fc` already, and `ledger.py` passes on `4772784`, before REVIEW.md existed;
  this remediation does not touch it. The one deferral under the heading links
  `issues/capability-reload-after-failure.md`, which exists and has its `ROADMAP.md` entry. The
  gate is frozen and is not amended; the attempt stays recorded until the foreman rules (a
  recorded wrapper under `remediation/`, or another reading).
  *Ruled by the foreman, as judge, 2026-10-31:* a false positive. The property the ledger guards
  holds (the deferral under the heading is seeded and in `ROADMAP.md`); the frozen `ledger.py`
  reads a heading line as a block of its own, and the review template writes one that says "Out of
  scope". It runs unchanged under `remediation/P5-ledger-headings.py`, which loads it by path,
  wraps its `blocks()` to drop Markdown heading lines and calls its `main()`. Seen red first: on a
  copy of the spec, `ROADMAP.md` and `issues/` outside the worktree, with an unseeded deferral item
  planted under that heading in REVIEW.md, the wrapper fails naming the planted item (and not the
  heading); on this tree it passes, where the frozen `ledger.py` alone fails on the heading. The
  instructions budget's floor stays with the operator, decided after the ladder as §7 says: no §4
  change in this cycle and no seed (same ruling).
- **Verify (retuned at the ruling):**
  `sh spec/capability-extras/verify/p5.sh phase && sh spec/capability-extras/verify/p5.sh recipe && sh spec/capability-extras/verify/p5.sh mutants && uv run --no-project python -I spec/capability-extras/remediation/P5-ledger-headings.py && sh spec/capability-extras/verify/p5.sh full && uv run --no-project python -I spec/capability-extras/remediation/F3-timeout-approval.py`.
  *Observed (2026-10-31):* `phase`, `recipe`, `mutants` (122 killed, 3 controls) and `full` (3043
  passed and 14 skipped in each era) stand in from attempt 1's run, on the tree `10c5ee5` commits
  (the code, tests, docs, ROADMAP and seed it holds; only TECH.md differed, and none of those steps
  reads it). Rerun after this amendment, as the only steps it can touch (each reads TECH.md or
  the wrapper): the wrapper (`ledger: ok`) and the F3 checker (ok).

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[{category}]` commit; stop and report.
