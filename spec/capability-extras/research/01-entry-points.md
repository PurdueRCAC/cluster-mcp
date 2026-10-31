# Research 01: entry-point mechanics and the registration payload

Evidence from a scratch copy of the worktree synced with `UV_PROJECT_ENVIRONMENT` set to a scratch
venv (uv 0.13.6, hatchling 1.30.1, CPython 3.14.6, FastMCP 4.1.4). The worktree was not modified.

## 1. Declaring and installing entry points

- A member declares `[project.entry-points."cluster_mcp.capabilities"]` with `slurm =
  "cluster_mcp.slurm.capability:CAPABILITY"` (PEP 621). Hatchling validates it in
  `hatchling/metadata/core.py:1115-1160` (string refs only; `console_scripts` refused there) and
  writes `entry_points.txt` in `builders/wheel.py:738` → `write_entry_points_file` (`:766-770`). The
  editable builders (`build_editable_detection` `:541`, `build_editable_explicit` `:625`) go
  through the same `write_metadata`, so editables carry it.
- **Experiment:** adding the table to the Slurm and RCAC members and running `uv sync` wrote
  `cluster_mcp_{slurm,rcac}-0.1.5.dist-info/entry_points.txt`, and
  `importlib.metadata.entry_points(group='cluster_mcp.capabilities')` returned both, each `.dist.name`
  being `cluster-mcp-slurm` / `cluster-mcp-rcac` (the name as written in `pyproject.toml`).
- **A pyproject edit needs a re-sync.** After changing an entry-point value with no sync, the old
  value was still served. `uv sync` (and `uv run`, which syncs implicitly) reinstalled just that
  member (`~ cluster-mcp-slurm`). uv's default cache key includes `pyproject.toml` (see
  `uv_cache.json` in each dist-info); touching a source file does not reinstall, and does not need
  to. So: `uv run pytest` refreshes it; a bare `.venv/bin/python` does not.
- **Extras in the workspace work:** with the core's member dependencies moved to
  `[project.optional-dependencies] slurm = ["cluster-mcp-slurm"]`, `rcac = ["cluster-mcp-rcac"]`
  (keeping the core's `[tool.uv.sources]` workspace entries) and the root changed to
  `dependencies = ["cluster-mcp[slurm,rcac]"]`, `uv lock`/`uv sync` resolved offline and the
  group held both members (R9). `uv sync --package cluster-mcp` removed both members (group empty);
  `--extra slurm` added only Slurm. `uv sync --package cluster-mcp --group dev` keeps pytest,
  which gives a real core-only test lane in a separate environment. Today, importing
  `cluster_mcp.core.tools` in that core-only venv fails with `ModuleNotFoundError: cluster_mcp.rcac`
  (the R4 baseline failure).

## 2. `entry_points(group=…)` semantics in 3.14 (`importlib/metadata/__init__.py`)

- **Order:** not guaranteed. `entry_points()` (`:999-1010`) chains `dist.entry_points` over
  `_unique(distributions())`. Distributions come in `sys.path` order (`_search_paths` `:887`), and
  within one directory in `os.listdir` order (`FastPath.children` `:742-744`, `Lookup` grouped
  into a dict). Inside one dist, hatchling writes names sorted. The experiment happened to yield
  `rcac` before `slurm`, the reverse of today's instructions. **Sort explicitly.**
- **De-duplication:** `_unique` = `unique_everseen` keyed on `_normalized_name` (`:990-993`).
  The same distribution on `sys.path` twice (a stale or shadow copy on `PYTHONPATH` ahead of
  site-packages) collapses to the **first** one on `sys.path`, and its entry points win silently.
  This was confirmed by planting a shadow `cluster_mcp_slurm-0.1.5.dist-info` whose `slurm` entry
  pointed elsewhere. *Different* distributions are never de-duplicated: two dists that both declare
  `slurm` both appear in the result, and `EntryPoints['slurm']` (`:257`) returns only the first.
- **`EntryPoint.dist`:** always set for entry points from `entry_points()`
  (`_from_text_for` → `ep._for(dist)`, `:201-203`, `:295`). It is `None` for one constructed by
  hand (`EntryPoint(name, value, group)`), which is what a test that injects fakes builds, so the
  loader needs a fallback. `dist.name` is the raw `Name:` metadata (`:474`), not normalised (a
  planted `Name: Other_Cap` came back as `Other_Cap`). For our hatchling-built members it is
  exactly `cluster-mcp-rcac`, which is good enough for the R8 message. `_normalized_name` is private.
- **`load()`** (`:173-181`) is `import_module(module)` and then `getattr`. A missing module raises
  `ModuleNotFoundError` (an `ImportError`), a missing attribute raises `AttributeError`, and any
  exception the module raises at import propagates unchanged (the experiment got `RuntimeError`).
  R8 therefore has to catch `Exception` around `load()` and the tool-module import, not just
  `ImportError`, and re-raise one typed error naming `ep.dist.name` (falling back to `ep.value`).

## 3. Recommendation: group, payload and composition

- **Group:** `cluster_mcp.capabilities`. It is the namespace-qualified, plural PEP 420 package
  convention, and it matches the `cluster_mcp.<member>` package names.
- **Payload:** the entry point names a module attribute that is a frozen dataclass defined in a new
  **leaf** core module, `cluster_mcp/core/capability.py`. That module imports only `dataclasses` and
  `typing`, nothing from `core.tools` or `core.server`:
  `Capability(name: str, order: int, tools: str, instructions: str, resources: tuple[Resource, ...] = ())`.
  `tools` is the dotted name of the member's tools module, imported later.
  The attribute lives in a dedicated `cluster_mcp/<member>/capability.py` that imports only the
  core leaf module, the member's `instructions` (already import-free, per its docstring), and a
  resource handler module whose `rcac.tools` import is deferred, as `core/resources.py:70-71` does
  today. Member `__init__.py` files stay empty.
- **Two phases, which keep import cycles out:**
  1. `discover()` loads the `Capability` objects only. It is cheap, cycle-free and cached, because
     nothing it imports touches `core.tools`. It then sorts and checks for duplicates.
     `server.py` (instructions) and `resources.py` (the storage entries, the `rcac://` alias
     derivation and `OPEN_RESOURCES`) consume this phase.
  2. Registration: the bottom of `core/tools/__init__.py` imports each `cap.tools` in sorted order,
     replacing `:81-82`. This keeps today's working pattern: members import `mcp_tool`, which is
     already defined at that point, and `core.context`. It keeps the `@mcp_tool` decoration-time
     append, so the decorator is unchanged (a non-goal) and the many tests that import
     `TOOL_REGISTRY`, `RESOURCE_REGISTRY`, `OPEN_RESOURCES` and `SERVER_INSTRUCTIONS` as module
     constants keep working. To attribute tools to a capability (for the duplicate check and the
     R5 cross-check), scan the imported module's `vars()` for `Tool` objects rather than taking a
     slice of the registry. A slice is wrong if a test imported the module first.
  
  R3 holds: no core module names `slurm` or `rcac`. Only the group string appears.
- **Explicit `register` list vs side effect:** an explicit `tools=(sbatch, …)` tuple would force
  `@mcp_tool` to stop appending (otherwise every tool is registered twice) and add a list to every
  core tool module too. That is more churn for no gain under R2 and R6. Recommend the side effect,
  scoped by the loader, plus the attribution scan.
- **Composition order:** `CORE_INSTRUCTIONS` is always first (it is not a capability). After it
  come the capabilities sorted by `(order, name)`. Use Slurm `order=100` and RCAC `order=900`,
  documented as "a site overlay sorts last, directly above the site context" (`server.py:69-70`).
  Discovery order never matters. Alphabetical order alone would put `rcac` before `slurm` and
  break R6. A boolean `overlay` flag is the alternative, but an integer is more general and leaves
  `site-extras` free.
- **Ordering note:** today `TOOL_REGISTRY` is shell, filesystem, transfer, rcac, slurm, context.
  Loading after `context` changes the list order. The baseline compares tools as a name-keyed dict
  (`tests/test_surface.py:276-280`), but the plan should confirm nothing else pins list order. If
  something does, load before the `context` import.
- **Testability (R5, R8):** let `discover()` take an injectable iterable of entry points (default
  `entry_points(group=…)`), so a test can pass fake `EntryPoint`s for core-only, all-members and
  broken sets in-process. Add one real core-only lane through `uv sync --package cluster-mcp
  --group dev` in a scratch environment.

## 4. Should `cluster-mcp-rcac` depend on `cluster-mcp-slurm`?

No Python coupling. `rcac/tools.py` imports only `cluster_mcp.core.tools.mcp_tool` and
`core.context.get_executor` (`:18-19`). Every tool runs a site command (`myquota`, `jobinfo`,
`jobcmd`, `jobenv`, `jobscript`, `showpartitions`, `average_wait`, `findscratch`, `slist`,
`sfeatures`; `:54-431`), and none runs a Slurm-member tool. `rcac/instructions.py` names no
Slurm-member tool; "Slurm" appears only as prose (`:20`, docstrings). The coupling is semantic:
the job tools take a Slurm job id, which concerns the *cluster's* scheduler, not the Python member.

**Recommend: no dependency.**
- **For:** it keeps `[rcac]` an ordinary capability (Q4); it leaves the bundle alias
  (`cluster-mcp[rcac]` pulling `slurm`, `lmod`, `xdu`) to `site-extras` without having to undo a
  hard edge; and a Purdue install is `cluster-mcp[slurm,rcac]` (R10) while the compat root pulls
  both (R9).
- **Against:** `[rcac]` alone serves job-id tools with no `squeue`/`sbatch` to obtain an id, though
  `run_command` can still do it. The README extras table should say "use with `slurm`".

## 5. Duplicates

- **Same distribution twice on `sys.path`:** the stdlib already collapses it to the first copy
  (§2). No action is needed.
- **Same entry-point name from two distributions, or two capabilities with the same `name`:**
  refuse at startup (an R8-style exit) naming both distributions. Never pick the first silently.
- **Same tool name from two capabilities, or a capability shadowing a core tool:** refuse at startup
  naming both distributions and the tool. FastMCP's default `on_duplicate` is `"warn"`
  (`fastmcp/server/server.py:358`), which would let one tool silently replace the other. Check in
  the loader before `add_tool`, or construct `FastMCP(on_duplicate="error")` as a backstop, which
  would also cover resources. The same applies to resource URIs (`cluster://storage` claimed
  twice).
