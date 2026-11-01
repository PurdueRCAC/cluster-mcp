# 03 — What the served surface pins, and how composition must reproduce it

Paths are relative to the worktree. `C` = `packages/cluster-mcp/src/cluster_mcp/core`.

## 1. Consumers, and what assumes import-time population

Core package:
- `C/tools/__init__.py:22,71` defines/appends `TOOL_REGISTRY`; `:81-82` import `cluster_mcp.rcac`/`.slurm` tools (R3 violations).
- `C/server.py:22-28` imports the three texts (`:27-28` are R3 violations); `:71` `SERVER_INSTRUCTIONS` is a module `Final`; `:95` `compose(SERVER_INSTRUCTIONS, …)`; `:110` iterates `TOOL_REGISTRY`; `:114` `RESOURCE_REGISTRY`.
- `C/resources.py:71` lazy `from cluster_mcp.rcac.tools import resolve_storage_paths`. A string module name inside a function still counts as importing a member by name (R3).
- `C/middleware.py:20,232` uses `OPEN_RESOURCES`. It is bound by a from-import when the module loads.
- `C/__init__.py:24` imports `server` at the top, so anything done at `server.py` import time runs on `--help`/`--version` and raises before `main` can print R8's clean message. **Loading must not happen at import**. Do it in `create_mcp_server` (or in `main` just before it).

Tests that read a registry **without building a server** (they break if registration moves to start):
- `tests/test_registry.py:29,333-336`: `len(TOOL_REGISTRY) == 24`.
- `tests/test_instructions.py:26,83,168`: `tools_by_member()` over `TOOL_REGISTRY`. `:212-227` per-member listings. `:206` `MEMBERS == ('core','slurm','rcac')` is hard-coded.
- `tests/test_tools.py:458`: `optional_scalars(TOOL_REGISTRY)`.
- `tests/test_storage_resource.py:59`, plus module-level `:182` `REGISTRY_OPEN`. `:319-336` expects 4 entries and `OPEN_RESOURCES == CONTEXT_URIS`. `:601,665` read the served set from `RESOURCE_REGISTRY`.
- `SERVER_INSTRUCTIONS` read as a constant at import: `test_protocol.py:54,61` (module level), `test_transports.py:30,34` (module level), `test_site.py:47,405` (default arg), `test_site_startup.py:24`, `test_context.py:33`, `test_instructions.py:24`.
- Direct member imports that register tools as a side effect: `test_sbatch.py:43,472`, `test_tools.py:467-468`, `test_hygiene.py:37-38,623`, `mutants.py:44-45,55`.

**Least-churn shape:**
- `@mcp_tool` keeps appending (the §7 non-goal leaves it untouched).
- Add `load_capabilities()` in a new core module (e.g. `C/capabilities.py`). It is idempotent (a module-level cache) and loads in a fixed order (see §2). Each entry point's `load()` imports the member's tool module (the decorators append), contributes its resources, and returns its text.
- `create_mcp_server` calls it.
- `tests/conftest.py` calls it once at import, before any test module imports a member. That fixes the registry order across collection orders and keeps every no-server read above at 24 tools and 4 resources.
- Keep the name `SERVER_INSTRUCTIONS` as a PEP 562 module `__getattr__` in `server.py` returning `base_instructions(load_capabilities())`. The seven test imports keep working and nothing loads on `--help`. The alternative, a function `server_instructions()`, edits those 7 files.
- Idempotence is required: `create_mcp_server` runs hundreds of times per suite, and a second append duplicates every capability tool (`registry_violations`).
- Footgun: editable installs carry `entry_points.txt` from the last `uv sync`. Adding `[project.entry-points]` without re-syncing finds no capability and silently serves the core only. A test should assert the discovered set equals the workspace members.

## 2. What the surface test compares, and ordering

- `tests/harness.py:442-455` `_surface` turns tools and resources into **dicts keyed by name/URI** and keeps instructions as one string.
- `tests/test_surface.py:134-144,248-256` compare tools and resources by sorted key sets and per-key values. **Order-free for tools and resources, exact for instructions.** `:276` builds the server itself.
- `served_tools` (`harness.py:417`) returns the served order, but its only caller sorts it (`test_registry.py:341`).
- `test_protocol.py:304-309` compares sets plus duplicates.
- No test pins listing order.

FastMCP 4.1.4 lists in **insertion order**: `server/providers/local_provider/local_provider.py:107,349,373` hold a plain `dict`, with no sort anywhere in `server/`. Verified empirically: the served order equals the registry order (shell, filesystem, transfer, rcac 10, slurm 7, `cluster_context` last). Resources come back as cluster://context, cluster://storage, rcac://context, rcac://storage.

Under "core first, then capabilities in a fixed order":
- **Tool order changes**: `cluster_context` moves from 24th to 7th, and Slurm moves ahead of RCAC.
- **Resource order changes** if aliases are derived per contributor (§4): context, rcac context, storage, rcac storage.
- No test fails. R6 pins "tool names and descriptions … instructions text and order, and resources", so order is pinned for the instructions only. The plan should state outright that listing order is not part of the surface, since the fixture's shape cannot express it.

**Instructions order is the trap.** It must stay CORE, SLURM, RCAC (`test_instructions.py:196`, `base_violations`; mutant `overlay-dropped`, `mutants.py:2243`). `importlib.metadata` discovery order is filesystem order (`FastPath.children` → `os.listdir`), so it is unspecified, and sorting by entry-point name gives `rcac` < `slurm`, which is wrong. Each capability needs an explicit sort key, e.g. an integer `order` with ties broken by distribution name: Slurm low, the RCAC site overlay last, directly above the site context. Load tools in the same order so registry order is deterministic too.

## 3. `tests/test_instructions.py` today and under R5

Today:
- `instruction_violations` (`:56-79`) cross-checks a text against registered names: every tool listed, nothing unregistered named, no docs guidance. It runs on the constant and on the served text (`:99-103`).
- `tools_by_member` (`:164-171`) maps each tool to `cluster_mcp.<member>` via `tool.fn.__module__`, which still works after the move.
- `listing_violations` checks that each text lists exactly its member's tools.
- `core_violations` checks that the core names no site and no RCAC tool.
- `test_every_tool_belongs_to_a_member` asserts exactly 3 members.

R5 rewrite:
- (a) **Every member:** keep the served cross-check (server built in process; tools and instructions both from the client). Replace the hard-coded `MEMBERS` and `base_violations`' fixed join with the loaded capability list: base = core text, then each capability's text in load order, joined by `\n\n`.
- (b) **Core only:** in process, `instruction_violations(base_instructions(()), tools_by_member()['core'])` checks the composition function. It cannot use a served server, because member tools already sit in the global registry. The faithful check is a subprocess in a core-only install, which also proves R4. It lists the served tools and instructions and runs the same `instruction_violations`. It belongs to the packaging/startup worker, and the plan should make that test count for R5.
- Keep the mutant rows (`:238-260`), re-expressed over the loaded list.

## 4. Resources (R7) without editing `middleware.py`

Today `resources.py:106-107` derives an alias for **every** entry, and `:113-114` computes `OPEN_RESOURCES` afterwards. Running that derivation over capability entries would give a future LMOD resource an `rcac://` alias.

Proposal:
- Move the derivation into a core helper, `legacy_aliases(entries)`: a copy with only the scheme changed, the same code as today.
- Core: `RESOURCE_REGISTRY = [context]`, then `+= legacy_aliases(...)`, then `OPEN_RESOURCES` over that. So `OPEN_RESOURCES` is still exactly `{cluster://context, rcac://context}`, computed at import, and middleware's import is untouched.
- The RCAC member's capability declares its storage entry and calls `legacy_aliases` on its own entries. The alias stays derived, never hand-written. A capability that does not call it gets no `rcac://` URI.
- The storage handler and `resolve_storage_paths` move into the RCAC member, which removes `resources.py:71`.

Fail-closed check: `middleware.py:232` runs `_install` (identity resolution, refusal, §5) for any URI **not** in `OPEN_RESOURCES`. A capability resource is never in the core's open set, so in delegate mode it is always resolved. That is fail-closed by construction. A capability entry marked `executor: False` would be silently gated rather than open. `load_capabilities` should reject any capability resource whose `executor` is not `True` as a load failure naming the distribution (R8), keeping §8's "missing key fails, never silently open".

Test anchors:
- `harness.CONTEXT_URIS`/`STORAGE_URIS` (`:139-140`) are hand-written; that is fine.
- `test_storage_resource.py:319-336` (4 entries, shared handler, open set) passes once conftest has loaded.
- **`tests/mutants.py` anchors on exact `resources.py` text**: `DERIVATION`/`OPEN_SET` (`:194-197`), `resource-calls-decorated-tool` (`:369-371`), `storage-read-left-open`, `alias-*`, `open-set-*` (`:565-626`). Server anchors are `:1451` and `:2243`. All of these must be re-anchored, or moved to `rcac/…` files, in the same commit.

## 5. AGENTS.md text that must change

- §7 (`AGENTS.md:2009-2031`): the title, "import list", "missing … fails silently", and the storage helper's location.
- §8 (`:2035-2052`): "`RESOURCE_REGISTRY` exposes … storage". The rule "keep every entry, the alias line and OPEN_RESOURCES in this one module, in that order" must become "the core's entries, its alias line, then the open set; capability resources come after, are never open, and alias themselves only through the helper". **§8 must change too**, though R10 does not name it.
- §9 (`:2147-2161`): "three texts … in this order" becomes composition in capability order.
- § Packaging (`:1230-1237`): "core depends on both members".
- Also: the repo map rows at `:155,162,169`, the module list at `:1654-1656`, and § Testing (`:319-334,552`).

## 6. RCAC in core

`grep -rni rcac` over the core source finds:
- **Member imports:** `tools/__init__.py:81-82`, `server.py:27-28`, `resources.py:71`. These are the R3 targets.
- **Not member imports:** the `rcac://` alias scheme (`resources.py`), token `ISSUER`/`AUDIENCE` `'rcac-mcp'` (`token.py:22-23`), state keys `rcac_user`/`rcac_local_user` (`middleware.py:211-212`), the `rcac-mcp` legacy command (`__init__.py:312`), and SPDX headers.

The favicon and the custom routes (`server.py:55-66`) stay in core.

An R3 test should scan core ASTs for `Import`/`ImportFrom` of `cluster_mcp.<x>` where `x != core`, plus string literals passed to `import_module`/`__import__`. A plain substring grep for `rcac` would hit the legitimate cases above.
