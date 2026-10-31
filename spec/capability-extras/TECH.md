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
  verify: sh spec/capability-extras/verify/p4.sh && sh spec/capability-extras/verify/p1.sh mutants && uv run python -I spec/capability-extras/remediation/F2-mutant-sweep.py
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
  verify: sh spec/capability-extras/verify/p4.sh phase && sh spec/capability-extras/verify/p3.sh phase && sh spec/capability-extras/verify/p3.sh mutants && sh spec/capability-extras/remediation/F1-contribution-refusal.sh
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
  verify: sh spec/capability-extras/verify/p5.sh && uv run --no-project python -I spec/capability-extras/remediation/F3-timeout-approval.py
review:
  last_reviewed_commit: '4772784'
  verdict: changes-requested
  blocked_reason: F1 resource rejection outside R8 path; F2 load-refusal mutants; F3 roadmap
  cycle: 1
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
