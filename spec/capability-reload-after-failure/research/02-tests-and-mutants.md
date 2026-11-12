# Research 02 — tests and mutants for the retry fix

Read-only survey for the plan. Line numbers are at the worktree's base commit.

## 1. How `tests/test_capabilities.py` plants capabilities

- **`plant` fixture** (`:166-196`): prepends `tmp_path` to `sys.path`; `plant(dist, entry, files, metadata=None)`
  writes the files and a `<dist>-0.0.1.dist-info` and returns the `EntryPoint`(s) via `Distribution.at`.
  Teardown restores `TOOL_REGISTRY[:]` to its pre-test copy and deletes every `sys.modules` entry whose
  `__file__` is under `tmp_path` (`:193-196`). Planted module names are **not** unique per test
  (`planted_first`, `planted_echo` recur); isolation is that teardown. Within one test, a module name is
  fresh until the test itself imports it.
- **Helpers:** `package(module, tool=, tools_tail=, **capability)` (`:205`) builds `__init__`/`tools.py`/`capability.py`;
  `echo_text(tool)` (`:780`) gives a matching instructions text; `members(names)` (`:770`) gives the
  installed member entry points; `load_error(eps)` (`:212`) returns the refusal text or `''`, failing on any
  non-`CapabilityLoadError`; `by_name()` (`:113`) reads `installed()`; `MEMBER_SETS` (`:667`) is
  core-only / slurm / rcac / both.
- **Closest to R5:** `pair(plant, first, second)` (`:774`) plants `planted-a-first` and `planted-b-second`,
  so the first sorts first in (distribution, entry-point name) order — exactly R5's shape. Give the first a
  distinct tool (`tool='planted_first_echo', text=echo_text(...)`, as `:736-739` does).
- **Members are imported before every test:** `tests/conftest.py:45-49` calls `installed()` at import, so
  member tools sit in `TOOL_REGISTRY` before any load's `start`. A cut-back never removes them; an
  eviction that dropped member modules from `sys.modules` would re-register them on retry and trip
  "registered twice" beside every member set.
- **`test_a_failed_load_is_not_cached`** (`:1563-1587`): builds a hand-made `EntryPoint` for a missing
  module, monkeypatches `cluster_mcp.core.capabilities.entry_points` to `lambda group: ... tuple(found)`
  and `_installed` to `None`, calls `installed()` twice (same message), removes the entry, and asserts
  only capability **names** and caching. It never imports a tools module, so it cannot see this defect.
- **R3 entry points:** `installed()` and `create_mcp_server()` both go through that same monkeypatch
  (`_discovered()` calls `entry_points(group=GROUP)`, `core/capabilities.py:150-154`). `create_mcp_server`
  needs `site=` (keyword-only) and an auth mode: `create_mcp_server('none', site=SITE)` with no
  `capabilities` reads `installed()` (`core/server.py:106-129`); read the served tools with
  `served_tools(server)` / `served_surface(server)['tools']` from `harness` (as `test_capabilities.py:265`,
  `test_registry.py:342`). A refusal raises from `create_mcp_server` before any server is built. A
  successful `installed()` caches the planted set; `monkeypatch` restores `_installed` at teardown.

## 2. Failing kinds already planted, and which R5 should use

The kinds live in `UNLOADABLE` (`:1335`, built by `unloadable(kind)` `:1300`) and `REJECTED` (`:619`, built by
`rejected_package(kind)` `:675`). Probed under today's code (failing one alone, then retried in-process):

| Kind | Tools module imported? | Retry's cause today |
|---|---|---|
| `raises-at-entry-point`, `raises-at-tools` | no (failed import leaves `sys.modules`) | same |
| `raises-at-declared`, `raises-at-served`, `raises-at-served-tool`, `stray-imported-by-tools` | yes | `its instructions list ['planted_echo'], which it does not register` |
| `REJECTED` `tool-not-a-tool`, `resource-not-a-url`, `tool-without-a-module` | yes | same listing violation |

With a clean capability first, **every** kind's retry names the clean one
(`cannot load capability aaa-good…: its instructions list [...], which it does not register`), and with the
failing one removed the retry still refuses the clean one (R2 violation). R5 can reuse the tables:
`unloadable(kind)` returns `(dist, entry, files, ...)`, so the test can parametrize over a few kinds and
plant the files under a `b…` distribution name after `pair`'s `planted-a-first`. A small set covers both
sides: one before-import kind (`raises-at-tools`) and after-import kinds (`raises-at-declared`,
`tool-not-a-tool` or `stray-imported-by-tools`). `unloadable()` names the dist `planted-<kind>`, which
sorts after `planted-a-first` for every kind listed, so the clean one stays first.

## 3. `tests/mutants.py`

- **Format** (`:78-96`): `Case(id, file, edits=((old, new), ...), targets=(test ids...), why, repo_edits=())`;
  `file` is namespace-relative (`core/capabilities.py`, alias `LOADER`, `:331`). Helpers: `every_set(test, *kinds)`
  (`:323`) expands to `test[kind-names]` for each `MEMBER_SETS` id; `alternative(id, file, edits, test, kind, why)` (`:335`).
- **Kill rule:** child exits 1 and every target holds a JUnit `<failure>` whose text carries `why`
  (`mutation_violations`, `:5708-5746`). An error, skip or wrong-reason failure is a survivor.
- **Anchor check:** `test_mutation_anchor_applies` (`tests/test_mutations.py:40`) runs `apply()`
  (`mutants.py:5640-5664`), which raises unless each `old` occurs exactly once in the file, then compiles it.
- **Cases anchored where the fix will likely land** (in `core/capabilities.py`):
  - `ROLLBACK` constant (`mutants.py:308-312`, the whole `except BaseException` block `:383-387`): used by
    `capability-refusal-keeps-registry` (`:2610`) and `capability-other-exception-keeps-registry` (`:2618`).
  - Inline copy of the same block: `capability-load-failure-passes-re-raises` (`:2944-2955`).
  - `loaded.append(...)\n    except BaseException as exc:\n`: `capability-load-baseexception-exception` (`:2940`).
  - `    scratch = _scratch()\n    try:\n        for distribution, nameless, ep in ordered:\n`:
    `capability-scratch-per-capability` (`:2513`) — breaks if a snapshot line goes between `scratch` and `try`.
  - `before = len(TOOL_REGISTRY)` … `import_module(capability.tools)`: `:3418`, `:3433`; `import_module` alone: `:2334`.
  - `tools = tuple(tool for tool in TOOL_REGISTRY if ...)`: `capability-tools-only-from-the-import` (`:2565`), `:3383`.
  - `installed()` body: `:2750-2766`, `:3390-3416`, `capability-installed-reloads-when-empty` (`:3713`).
  - `capability-load-failure-swallowed` (`:2368`) anchors the `_checked(ep.load())` try block (`:328-331`), not the cut-back.
  - Nothing anchors `start = len(TOOL_REGISTRY)` (`:312`) by itself.
  A moved anchor is re-planted in the same commit (AGENTS.md § Testing, mutation runner bullet).
- **Planting today's retry behaviour:** once the fix adds an eviction (say a `sys.modules` snapshot at load
  start and a deletion in the failure exit), the case deletes the eviction (anchor: the deletion line or the
  fix's whole failure block; `new` = the block without it), leaving the cut-back alone so R4's cases still
  hold. Targets: R5's test rows (`every_set(...)` if it is parametrized by `MEMBER_SETS` and kind).
- **Naming R1/R2 in the kill:** the suite cannot carry the spec ids. `test_no_spec_ids_in_the_package_or_the_suite`
  (`tests/test_hygiene.py:658`) scans every `.py` directly in `tests/` (so `mutants.py` and the test) for
  `R`/`P`/`Q`/`F` plus one or two digits (AGENTS.md § Conventions, comments bullet). So `why` must be a fragment
  of R5's assertion message that states R1's or R2's contract in words, e.g. a "retried load did not refuse as a
  first load does" message for the still-present row and a "retried load ... lost its tools" one for the removed
  row. One `why` must match every target, so either give both assertions a shared prefix or target only one row
  family. The mutation-gate grading is `method/mutation-testing.md` § When a review is done (operator's KB).
- **Cost of one case:** `uv run python tests/mutants.py capability-installed-installed-never` killed its 4 targets
  in **3.5 s** wall.

## 4. Text a same-commit doc update must keep consistent

No test pins the §7 or footgun text (`test_hygiene.py` reads AGENTS.md only for the id rule, `:690`). Sites that
describe today's behaviour:

- AGENTS.md `:2193-2195` footgun: "`installed()` is the one load: a second `load()` of the same capabilities
  registers nothing new" (true for a second load after success; after a failure it is the defect).
- AGENTS.md §7 `:2820-2823` (cut-back "to what it held before the load began") and `:2833-2834` (failure not cached).
- AGENTS.md § Testing `:399` ("the registry cut back") and `:403-405` (names `test_a_failed_load_is_not_cached`;
  a new test belongs in this paragraph).
- `core/capabilities.py:303-306` `load()` docstring and `:398-401` `installed()` docstring; `mutants.py:306-307` comment.
- `test_a_capability_whose_tools_are_already_imported_keeps_them` (`:1022-1038`) pins that a tools module imported
  before the load keeps its tools; the fix must not evict modules imported before `start`.

## 5. Narrowed verify

Measured, one era each:

- `uv run pytest -q tests/test_capabilities.py` — 711 passed, **7.7 s** wall.
- `uv run pytest -q tests/test_mutations.py -k "mutation_anchor_applies and capability"` — 287 passed, **4.5 s**.
- `-k failed_load_is_not_cached` alone — 4 passed, 2.0 s.
- Modern era: `CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_capabilities.py tests/test_mutations.py` — 1876 passed, **25 s**.

Suggested phase verify (both eras): `tests/test_capabilities.py`, `tests/test_mutations.py`,
`tests/test_hygiene.py -k spec_id`, and the startup capability rows (`tests/test_startup.py -k capabilit`,
not timed here), plus the new mutation case and every re-planted case through `tests/mutants.py --self-check`
(about 3.5 s each).
