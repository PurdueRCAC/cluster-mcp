# PLAN — Capabilities you don't have shouldn't be tools you see

> **Status:** Draft for review · **Last updated:** 2026-10-31
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Backing detail is in
> [`research/`](research/) ([`00-digest.md`](research/00-digest.md) first). Every design element
> traces to a GOAL R-ID.

## 1. Summary

Each capability member declares one entry point in the group `cluster_mcp.capabilities`, naming a
`Capability` value: its name, an explicit order, its tools module, its instructions text and its
resources. At startup the core loads every installed one (never at import), refuses to start on any
load failure with a message naming the distribution, and composes the served tools, resources and
base instructions from the core's own and each loaded capability's, in fixed orders that reproduce
today's surface exactly: the base text byte for byte, and the tool and resource listings in today's
order. The members become the core's extras `slurm` and `rcac`; the
compat root depends on `cluster-mcp[slurm,rcac]`, so every existing install line serves what it
serves today. Big appetite: five phases, the contract first.

## 2. Design

Paths: `C` = `packages/cluster-mcp/src/cluster_mcp/core/`, `S` = `packages/cluster-mcp-slurm/src/cluster_mcp/slurm/`,
`RC` = `packages/cluster-mcp-rcac/src/cluster_mcp/rcac/`.

### 2.1 The contract: `C/capabilities.py` (new)

```python
GROUP: Final = 'cluster_mcp.capabilities'

@dataclass(frozen=True)
class Capability:
    name: str                      # 'slurm', 'rcac': unique among loaded capabilities
    order: int                     # place in the composed base; lower first; a site overlay sorts last
    tools: str                     # dotted name of the module whose @mcp_tool functions are its tools
    instructions: str              # its part of the base: lists exactly its tools (and resources)
    resources: tuple[dict, ...] = ()   # RESOURCE_REGISTRY-shaped entries, each 'executor': True

@dataclass(frozen=True)
class Loaded:
    capability: Capability
    distribution: str              # ep.dist.name, e.g. 'cluster-mcp-rcac' (ep.value when dist is None)
    tools: tuple[Tool, ...]        # its tools, in registration order

class CapabilityLoadError(RuntimeError):   # .distribution; str() is the one-line message
    ...

def load(entry_points: Iterable[EntryPoint] | None = None) -> tuple[Loaded, ...]   # uncached
def installed() -> tuple[Loaded, ...]      # load() over entry_points(group=GROUP), cached once loaded
def composed(capabilities: Iterable[Loaded]) -> tuple[Loaded, ...]   # sorted by (order, distribution)
```

`load()`:
- takes the group's entry points (or the given ones), sorted by `(distribution, entry-point name)`,
  so which failure is reported first never depends on `sys.path` or directory order;
- for each: `ep.load()`, a type check (`Capability`, each field's type, a non-empty `instructions`),
  `import_module(cap.tools)`; any `Exception` from either is a failure (the tools import is where a
  member's missing dependency surfaces);
- attributes to the capability every `TOOL_REGISTRY` entry whose `fn.__module__` is `cap.tools` or
  below it; a tool appended during the import that it cannot attribute is a failure, and so is a
  tool name taken by the core (`CORE_TOOLS`) or an earlier capability, a capability name taken
  earlier, a resource URI taken by the core's `RESOURCE_REGISTRY` or an earlier capability, a
  resource that is not a dict with a `str` `uri`, `name` and `description`, a callable `handler` and
  `executor` exactly `True`, and an `instructions` text whose `- name:` lines are not exactly the
  capability's own tools, each once (R5 then holds for any capability, not only the two members;
  the core's own text is held to `CORE_TOOLS` by a test);
- on a failure, truncates `TOOL_REGISTRY` to its length before this `load()` began and raises
  `CapabilityLoadError`: `cannot load capability <distribution>: <cause>`, one line, `<cause>`
  being `<ExcType>: <text>` (the type alone for an empty text) or the validation sentence (e.g.
  `tool 'sinfo' is already registered by cluster-mcp-slurm`); it reports the first failure only.

`installed()` caches a successful load (`functools.cache` semantics, a failure not cached) so the
CLI, `create_mcp_server` and the tests share one registry and nothing registers twice (01 §3, 04 §1).
The module imports `core.tools` (for `TOOL_REGISTRY`, `CORE_TOOLS`, `Tool`) and `core.resources`; it
imports no member, and no core module imports it at import time but `server.py` and `__init__.py`,
which only *call* `installed()` from functions.

### 2.2 The members

- `S/capability.py`, `RC/capability.py` (new): `CAPABILITY = Capability(name='slurm', order=100,
  tools='cluster_mcp.slurm.tools', instructions=SLURM_INSTRUCTIONS)` and `Capability(name='rcac',
  order=900, tools='cluster_mcp.rcac.tools', instructions=RCAC_INSTRUCTIONS,
  resources=(STORAGE, *legacy_aliases((STORAGE,))))`. Each imports only the core contract, its own
  `instructions` and (RCAC) its `resources` module; importing it registers no tool.
- `RC/resources.py` (new): `_storage_paths_resource` moves here verbatim from `C/resources.py` (its
  output unchanged), calling `resolve_storage_paths()` from `RC/tools.py`; `STORAGE` is today's
  `cluster://storage` entry, `'executor': True`.
- The two `instructions.py` texts are unchanged byte for byte (R6); only their docstrings stop
  saying the core imports them.
- Each member's `pyproject.toml`: `[project.entry-points."cluster_mcp.capabilities"]`
  `<name> = "cluster_mcp.<name>.capability:CAPABILITY"`. The RCAC member does **not** depend on the
  Slurm member ([01 §4](research/01-entry-points.md)): no Python coupling, and the bundle alias
  belongs to `site-extras`. README says to install `[rcac]` with `[slurm]`.

### 2.3 The core

- `C/tools/__init__.py`: the member imports go. The core's own modules are imported in today's
  order (shell, filesystem, transfer, then context), and two snapshots record them:
  `CORE_TOOLS: Final` (every core tool, for the duplicate check) and `CLOSING_TOOLS: Final` (the
  tools of the context module, `cluster_context`). `TOOL_REGISTRY` and `@mcp_tool` are otherwise
  unchanged (the decorator's `FunctionTool` behaviour is a non-goal; its append is kept).
- `C/resources.py`: `legacy_aliases(entries)` holds today's derivation (a copy with only the scheme
  changed, `cluster://` → `rcac://`); `RESOURCE_REGISTRY` is the core's `cluster://context` entry
  plus `legacy_aliases(RESOURCE_REGISTRY)`; `OPEN_RESOURCES` is computed after, as today, and is
  unchanged: `{cluster://context, rcac://context}`. The storage entry and its lazy member import go.
  `middleware.py` is not edited: a capability resource is never in `OPEN_RESOURCES`, so in
  `delegate` mode its read always resolves the caller (fail-closed, [03 §4](research/03-surface-and-composition.md)).
- `C/server.py`: the member imports and `SERVER_INSTRUCTIONS` go. `base_instructions(capabilities)`
  returns `CORE_INSTRUCTIONS` and each composed capability's text joined by a blank line.
  `create_mcp_server(auth_mode=None, middlewares=None, *, site, budget=DEFAULT_BUDGET,
  capabilities=None)`: `capabilities=None` means `installed()`; the given set is passed through
  `composed()`, so its order never matters. It composes `base_instructions(...)` with the site as
  today, and registers, in today's listing order:
  - tools: the core's but `CLOSING_TOOLS`, then each capability's in **load** order (distribution
    name: `cluster-mcp-rcac` before `cluster-mcp-slurm`, as today's import list had them), then
    `CLOSING_TOOLS` — the site-context tool closes the list as the site section closes the
    instructions;
  - resources: every primary (`cluster://`) entry, the core's then each capability's in load order,
    then every deprecated `rcac://` alias in the same order — so today's `cluster://context`,
    `cluster://storage`, `rcac://context`, `rcac://storage`.
  The base orders texts by `(order, distribution)`; the listings by load order. Two keys, because
  today's surface has two orders (Slurm's text before RCAC's, RCAC's tools before Slurm's), and R6
  keeps both. The parameter is a test seam, not a switch: no CLI flag or environment variable
  reaches it (GOAL non-goals).
- `C/__init__.py` (`MCPServerApp.run`): right after the `--generate-token` branch and before
  `_resolve_exec_mode()`, `installed()` runs; a `CapabilityLoadError` is reported through
  `_report_startup_failure(str(exc))` and re-raised as `StartupFailure` (exit 5; on stdio the
  message is the error to every request until EOF, then exit 5, exactly as an SSH connect failure).
  `--help` and `--version` never reach `run()`, and nothing on the import chain loads a capability,
  so they work with a broken capability installed. `_resolve_exec_mode()` is not edited.
- `C/startup.py`: docstring only (it now reports a capability failure too).

### 2.4 Packaging

- `packages/cluster-mcp/pyproject.toml`: `dependencies` lose both members;
  `[project.optional-dependencies] slurm = ["cluster-mcp-slurm"]`, `rcac = ["cluster-mcp-rcac"]`;
  both workspace sources stay. Root `pyproject.toml`: `dependencies = ["cluster-mcp[slurm,rcac]"]`
  (header comment and description updated). `uv lock` in the same commit. The root's extras are
  what keep `uv sync` (the profile's `setup`, CI, `mutants.yml`, the Dockerfile) installing every
  member ([05](research/05-packaging-and-extras.md)).
- `AGENTS.md` § Factory → Release recipe: `post_verify` line 1 becomes the extras install
  (`'cluster-mcp[slurm,rcac] @ git+https://github.com/PurdueRCAC/cluster-mcp@{v}#subdirectory=packages/cluster-mcp'`),
  a core-only `--help` line is added, the root `rcac-mcp` line stays; the `install-probe` and
  `ci-mirror-no-index` caveats follow.

### 2.5 Tests

- `tests/conftest.py` calls `installed()` once at import, so every test sees the full registry in a
  fixed order whatever it imports first.
- New `tests/test_capabilities.py` (`unit`): discovery of exactly the two members from their
  distributions; composition from explicit sets (none, each, both, both orders) through
  `harness.served_*` in both eras; the R5 cross-check per set; load failures through
  `Distribution.at(tmp dist-info).entry_points` (missing module, raising module, missing attribute,
  wrong type, a hand-built `EntryPoint` with no `dist`), duplicate tool, resource and capability
  name, an open resource; registry rollback; a planted capability that needs no core edit; the R3
  AST scan of the core.
- New `tests/test_core_only.py` (`integration`): a session-scoped core-only environment (as
  §2.6's `coreonly.sh`), driven over stdio in the selected era: exactly the seven core tools, the
  instructions naming exactly them, no storage resource.
- `tests/test_startup.py`: a planted broken capability stops startup (`integration`, through
  `harness.stdio_refusal` and the raw wire), `--help` unaffected, the load before the mode ladder
  (`unit`, `run_app`).
- Edited, not weakened: `test_instructions.py` (members from the loaded capabilities, not a
  hard-coded triple), `test_registry.py`, `test_storage_resource.py` (served resources from a
  composed server, not `RESOURCE_REGISTRY`), `test_packaging.py` (the extras and the root's
  `cluster-mcp[rcac,slurm]`), the seven importers of `SERVER_INSTRUCTIONS`, `harness.py` (a
  resources listing for stdio drives). `tests/mutants.py` cases anchored on moved lines are
  re-anchored with the same id and `why`; eight new cases (TECH).

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1   | §2.4: core `optional-dependencies` `slurm`/`rcac`, no unconditional member dependency; gate `pyprojects.py p4`, `probe.sh` (built metadata, the four install lines) |
| R2   | §2.1 `load`/`installed` over `GROUP`, called at startup (§2.3); §2.2 both members' entry points; `registry.py` (nothing imported from an absent member); `planted.sh extra` |
| R3   | §2.3: no member import in `tools/__init__.py`, `server.py`, `resources.py`; `imports.py p2` (AST and string scan); a planted third-party capability served with no core edit (`planted.sh extra`, `test_a_planted_capability_needs_no_core_edit`) |
| R4   | §2.3 nothing on the import chain needs a member; `coreonly.sh` / `test_core_only.py`: a real core-only install starts and `TOOL_REGISTRY` holds exactly the seven |
| R5   | §2.3 `base_instructions(composed(...))`; §2.1 `load()` refuses a capability whose text does not list exactly its tools; the cross-check under core only (in process, and a real core-only install), each member alone, and every member (`compose.py`, `coreonly.sh`, `test_instructions_name_exactly_the_served_tools`, `test_core_only_instructions_name_exactly_its_tools`) |
| R6   | Orders Slurm 100 < RCAC 900 reproduce today's base byte for byte; load order and `CLOSING_TOOLS` reproduce today's listings (§2.3); `baseline.sh` (the whole surface against `f62e3b5`, order included, fixture untouched), `test_served_surface_matches_baseline` with no fixture edit |
| R7   | §2.2 `RC/resources.py` + `legacy_aliases`; §2.3 core registry holds only the context URIs; `compose.py p2`, `coreonly.sh`, `test_storage_is_served_only_with_the_rcac_capability` |
| R8   | §2.1 `CapabilityLoadError`; §2.3 `run()` reports and exits 5 before the mode ladder; `planted.sh broken` (seven cases, both commands, stdio answer), `test_a_broken_capability_stops_startup` |
| R9   | §2.4 root `cluster-mcp[slurm,rcac]`; `probe.sh` (root install: every member from one commit, surface equal to `f62e3b5`'s; `uvx … rcac-mcp --help`) |
| R10  | AGENTS.md §7, §9 (and §4, §8, the footgun and high-blast-radius lists, the repository map), § Packaging; README install line and inventory by extra — each phase updates the text it makes true; the cycle lands as one squash commit (profile `landing: squash-local`), which is "the same commit" R10 names; `docs.py p1…p4` |

## 3. Invariant gate (AGENTS.md constitution check)

Gate #1 (before research): the intent touches §7 and §9 (replaced, as the GOAL says), §8 (the storage
resource moves), §4 (the startup path in `__init__.py`, human-gated), § Packaging, § Conventions
(same-commit, comments, markers, sandbox, CI mirror) and the high-blast-radius paths `server.py`,
`core/__init__.py` and the three `instructions.py` — so research trigger 2 fired. §1, §5 and §6 are
touched only through `middleware.py`'s use of `OPEN_RESOURCES`, which the design keeps unchanged.
Nothing in the GOAL is at odds with an invariant; it replaces §7 and §9 by design.

Gate #2 (after design):

- §1 (executor isolation) — untouched: the storage handler moves member but keeps calling
  `resolve_storage_paths()` on the request's executor; no new state, no module global but the
  registries that already exist and `installed()`'s cache, which holds definitions, never a request's
  executor or identity.
- §4 [human gate] — `run()` gains one step before `_resolve_exec_mode()`; the ladder itself is not
  edited. A capability failure now takes precedence over "SSH host required" (the load runs first),
  which is the R8 order.
- §5, §6 — untouched. `middleware.py` is not edited; a capability resource is outside
  `OPEN_RESOURCES`, so every `delegate` read of it resolves and checks the caller.
- §7 — rewritten (R10): registration is a startup load through the group; `@mcp_tool`'s
  `FunctionTool` behaviour and full-docstring description are kept; the helper-sharing rule
  (`resolve_storage_paths`) stays, its resource now in the member.
- §8 — rewritten for the move: the core's entries, its alias line and `OPEN_RESOURCES` stay in one
  module in that order; a capability's resources come after, are never open, and alias themselves
  only through `legacy_aliases`. The `/etc/agents.d` rules are untouched.
- §9 [human gate] — rewritten (R10): the base is the core's text then each loaded capability's, by
  `(order, distribution)`; with every member installed it is today's text byte for byte. The
  same-commit rule for a tool change now names the member's own `instructions.py`. The fixture is
  not edited.
- High-blast-radius list — widens with `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`
  (it now decides what loads and what the base says) and the two members' `capability.py` files
  (each selects its tools and text); nothing is removed.
- § Packaging, § Conventions — extras and lock in one commit; CI and `setup` unchanged
  (`uv sync --locked` still installs every member through the root's extras); comments carry no
  spec ids; new tests carry markers; every CLI drive is under `bin/sandbox.sh`.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| §8's "keep every entry, the alias line and `OPEN_RESOURCES` in this one module" no longer holds for the storage entry (R10 names §7, §9 and § Packaging; §8 is rewritten too) | R7 requires the RCAC member to register `cluster://storage` and its alias | Deriving every capability resource's alias in the core would give a future capability a `rcac://` URI that never existed; computing `OPEN_RESOURCES` from capability entries would edit `middleware.py`'s contract. Read against R7: it does exactly what R7 SHALL; against R10: §8 is described in the same commit too, which R10 does not forbid |
| On stdio, a capability load failure answers every request with its message until the client closes stdin, then exits 5, rather than exiting the instant it is detected | A stdio client that discards stderr would otherwise see only a closed connection; this is the codebase's one startup-refusal path (the SSH connect failure, §4) | A bare log-and-exit is simpler, but loses the message for exactly the clients R8's "message naming that distribution" is for. Read against R8: the server never builds, registers or serves anything, opens no connection, and its exit is decided at startup; with stdin closed (`< /dev/null`) it exits 5 at once. GOAL leaves "how R8's load failure is … reported" to the plan. **Flagged for the PLAN/TECH sign-off** (the adversarial review read it as a GOAL clarification) |

## 4. Rabbit holes (resolved)

- **Entry-point discovery order and de-duplication** → unspecified (`sys.path` then directory
  listing); a name sort is wrong (`rcac` < `slurm`); one shadowing copy of a distribution wins
  silently. Explicit `order` key; load in distribution-name order ([01](research/01-entry-points.md) §2).
- **Load at import or at start** → at start: an import-time load breaks `--help` and turns R8 into a
  traceback ([04](research/04-startup-and-failure.md) §1, [03](research/03-surface-and-composition.md) §1);
  digest decision 2.
- **Tests that read registries without a server** → `conftest.py` loads once; the explicit capability
  set is a parameter of `create_mcp_server` ([03](research/03-surface-and-composition.md) §1, [02](research/02-core-only-testing.md) §2).
- **"Core only" when the dev environment has every member** → a real editable core-only environment
  built offline in 0.35 s, never touching `.venv`; a non-editable one serves a stale cached wheel
  ([02](research/02-core-only-testing.md) §1).
- **R8 detection** → any `Exception` from `ep.load()` or the tools import, plus type, duplicate and
  open-resource checks; `ep.dist` is `None` for a hand-built entry point
  ([04](research/04-startup-and-failure.md) §3, [01](research/01-entry-points.md) §2).
- **Extras in a uv workspace** → lock, build, git installs from one commit and `uvx --from
  'cluster-mcp[slurm,rcac] @ git+…#subdirectory=…'` all work, under uv 0.13 and the 0.12.17 floor;
  the root's extras keep `uv sync` full ([05](research/05-packaging-and-extras.md)).
- **Adversarial design review** (trigger 3: the core-only environment and the R5 cross-check are
  test infrastructure) → ran against this design and the drafted gates; findings and what changed
  are in §5.

## 5. Risks & open questions

- **Stale editable install.** Adding entry points needs a `uv sync`; an unsynced `.venv` serves the
  core alone. Every gate starts with `uv sync --locked`, and
  `test_installed_finds_every_workspace_member` fails loudly in that state.
- **A member installed without an entry point is silently absent** (a pre-cycle member wheel beside
  a newer core). Residual, not deferred: supported installs build every member from one commit
  ([digest](research/00-digest.md), last section).
- **Mutation anchors.** `tests/mutants.py` cases anchored on `C/resources.py` and `C/server.py` lines
  move; re-anchoring keeps each id and `why`. `baseline.sh` fails if a case id or a test function
  disappears, unless `verify/retired.txt` names it with a reason (empty today).
- **Listing order** is kept exactly (§2.3), at the cost of two order keys; `compare.py` pins it.
- **The `#subdirectory=packages/cluster-mcp` install line** in today's README drops to the core alone
  after this cycle. It has never been in a release (0.1.5's tree has no `packages/`; its README
  installs the repository root, which R9 keeps whole), so no released client config uses it; the
  README's install note says so and names the extras.
- **The FastMCP update check** makes stdio drives fetch from the network; new drives turn it off,
  and the suite-wide fix stays with `issues/fastmcp-update-check.md`.
- **Adversarial review** (fresh subagent, GOAL + this design + the drafted gates, with a scratch
  prototype worktree). Three HIGH, six MEDIUM and five LOW findings, every one folded in:
  - H1, a loader that swallows a failing *tools* import passed every planted case → `planted.sh`
    adds `tools-missing` and `tools-raising`; mutant `capability-tools-import-swallowed`.
  - H2, R5 held only for the two members → `load()` requires a capability's text to list exactly
    its tools; planted `instructions-mismatch`; mutant `capability-instructions-unchecked`.
  - H3, `imports.py` missed relative imports (`from ..slurm import tools` reaches across PEP 420
    portions), `'.slurm.tools'` strings, string building and namespace walks → resolved and
    flagged, each with a control.
  - M1, a core special-casing a member by bare name → `imports.py` flags a string equal to a member
    name; the planted capability now carries a resource.
  - M2, resources validated only for `executor` and URI → full shape check; planted `bad-resource`.
  - M3, a mutant child carries every member on `PYTHONPATH`, so no core-only drive can kill a core
    mutant → `core-imports-member-by-name` targets the static scans; `coreonly.sh`, `probe.sh` and
    `baseline.sh` drop `PYTHONPATH`.
  - M4, `compare.py` kept chosen fields only → it compares whole dumps (`_meta`, titles), resource
    templates, prompts and server capabilities.
  - M5, the old line's `rcac-mcp` was never listed over stdio → `probe.sh` drives it.
  - M6, the listing-order change read as a change to R6 → the order is now reproduced (§2.3), the
    deviation row is gone, and `compare.py` pins order.
  - L1, the split between the three texts was unpinned → `compare.py` pins each text.
  - L2, the suite could be weakened past `baseline.sh` → `retired.txt` lines name a phase,
    `tests/test_surface.py` is pinned, skip and xfail marks may not grow.
  - L3, raw-string metadata checks → canonical names, extras as sets, markers evaluated.
  - L4, R8 over HTTP undriven → one HTTP drive that must exit 5 before binding.
  - L5, empty texts, a loose §9 check, an online `uvx` → refused, tightened, `--offline`.
  The stdio answer-until-EOF reading of R8 stays a plan decision, flagged for sign-off (§3).

## 6. Verification strategy

Each phase's `verify:` is `sh spec/capability-extras/verify/p<n>.sh` (modes `phase`, `mutants`,
`full`, and in P5 `ledger` and `recipe`), sourcing `lib.sh`. The independent checks, none of them
the suite's own tests:

- `baseline.sh` — `f62e3b5`'s tree in its own environment vs this tree, every member installed:
  the served surface equal whole, listing order and the three texts included (`surface.py`,
  `compare.py`); no test function or mutation case lost (`kept.py`, `retired.txt`); the fixture and
  `tests/test_surface.py` byte-identical; no more skip or xfail marks (R6).
- `compose.py` — in process, every capability subset in every order: tools, base, cross-check,
  order independence; from p2 the storage URIs (R5, R6, R7).
- `imports.py` — AST and string scan of every core module for a member's package or distribution
  name, checked against controls first (R3).
- `planted.sh extra|broken` — a planted third-party capability, with a tool and a resource, served
  with its text between Slurm's and RCAC's by its order, with no core edit (R2, R3, R5); eleven
  planted failures through `cluster-mcp` and `rcac-mcp`, and one over HTTP (R8).
- `coreonly.sh` + `registry.py` + `served.py` — real editable environments for the core alone,
  each extra alone and both, offline: installed distributions, importability, entry points,
  `TOOL_REGISTRY`, and a stdio drive's tools, resources and base (R1, R2, R4, R5, R7).
- `probe.sh` — a snapshot commit's built metadata, and the four install lines plus the old one into
  fresh venvs from that commit; the old line's surface against `f62e3b5`'s, and its `rcac-mcp`
  over stdio; the README's `uvx` line (R1, R9).
- `pyprojects.py`, `docs.py`, `ledger.py` — the declarations, the R10 text, the deferral ledger.

Every CLI drive runs under `bin/sandbox.sh`. Each gate was dry-run on today's tree: `baseline.sh`
passes (nothing changed yet) and catches a reworded instruction or a lost resource in a control;
`imports.py` finds exactly today's five member imports; `planted.sh`, `coreonly.sh`, `probe.sh`,
`pyprojects.py` and `docs.py` fail for the reasons each phase must remove.

---

*Backing research: [`research/00-digest.md`](research/00-digest.md).*
