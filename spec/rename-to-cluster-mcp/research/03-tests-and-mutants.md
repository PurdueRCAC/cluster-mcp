# Research 03 — tests, mutants and the mechanical rename

Assumes the planned layout: `cluster_mcp.core` (core member), `cluster_mcp.slurm`, `cluster_mcp.rcac`;
tests stay in root `tests/`.

## Recommendations

1. **Mutation cases name files relative to the `cluster_mcp` namespace root**: `core/middleware.py`,
   `slurm/<mod>.py`, `rcac/<mod>.py`. Do not use repo-root paths. The runner copies the *imported*
   package, never `src/` (AGENTS.md § Testing). A namespace-relative name is the same in the copy and in
   any install layout. The re-plant is mechanical: `tools/slurm.py` (16 cases) → `slurm/…`,
   `tools/rcac.py` (2) → `rcac/…`, everything else (288) → `core/…`. If the storage resource follows
   `resolve_storage_paths` into the RCAC member, `resource-calls-decorated-tool` and
   `storage-read-left-open` move with it.
2. **`apply()` copies every member portion**:
   `for m in ('core','slurm','rcac'): copytree(Path(import_module(f'cluster_mcp.{m}').__file__).parent, src_root/'cluster_mcp'/m)`.
   Write no `cluster_mcp/__init__.py` into the copy. **CHILD's origin check** must require
   *all three* subpackages to resolve under `root`. Under PEP 420, a member missing from the copy would
   load silently from the editable tree. Add a `--self-check` control for this: a copy that lacks one
   member must be reported `wrong import origin`. `test_mutations.py:42` becomes
   `src_root / 'cluster_mcp' / case.file`.
3. **Orphan gate.** `test_mutation_anchor_applies` already goes red on a missing file
   (`FileNotFoundError`) or an anchor count ≠ 1 (`mutants.py:2019-2022`), so the suite cannot orphan
   a case silently. Add three things:
   - (a) a unit assertion that `case.file.split('/')[0] in {'core','slurm','rcac'}`.
   - (b) a phase-gate check that the head's `CASES` ids ⊇ the base commit's ids, with each removal
     named in the commit body.
   - (c) a `pytest --collect-only` over the union of all case targets, because a renamed test id
     shows up only as "missing from the report" when the case runs.

   Run every case (killed == count, as `mutants.yml` does) after the workspace move and again after
   the URI and env phases.
4. **`test_hygiene.py` is the right home for source-level rails.** Add:
   - **Namespace (source level):** no `packages/*/src/cluster_mcp/__init__.py`;
     `cluster_mcp.__file__ is None`; `{p.name for p in …}` of the portions is exactly
     `{core, slurm, rcac}`. The R1 wording is about **built wheels**, so prove that in the phase/verify gate:
     `uv build --all-packages`, then list each wheel with `zipfile`. `bin/sdist_hygiene.py` is the natural
     place to grow a wheel check, since the release gate already runs it.
   - **SPDX:** walk the repo (skip `.git`, `.venv`, `.worktrees`, `dist`). Every line matching
     `^\s*(#|//|<!--)\s*SPDX-FileCopyrightText:` must equal the exact header text, and each such file
     keeps `SPDX-License-Identifier: MIT`. The comment-prefix anchor skips the backticked prose in GOAL
     and the seed. A file walk keeps it `unit` (no git subprocess). **Never write a spec id in that test's
     comments:** `test_no_spec_ids_in_the_package_or_the_suite` would flag it.
   - **Spec-id scan** (`test_hygiene.py:569`): scan every portion of `cluster_mcp.__path__`, not
     `rcac_mcp.__file__`'s directory. Otherwise the Slurm/RCAC members escape it. Assert three portions
     so the scan cannot shrink.
5. **Ordered substitution map** (most specific first; review each hunk, never a blind tree-wide sed):
   1. `rcac_mcp.tools.rcac` → `cluster_mcp.rcac.<mod>`; `rcac_mcp.tools.slurm` → `cluster_mcp.slurm.<mod>`
   2. by hand: `from rcac_mcp.tools import slurm` (`test_sbatch.py:44,473`) and
      `from rcac_mcp.tools import rcac, slurm` (`test_tools.py:467`). The dotted rule misses them.
   3. by hand: `rcac_mcp.__file__` uses (`test_sbatch.py:483,490`, should use `cluster_mcp.slurm`;
      `test_hygiene.py:569`; `mutants.py:38,55,2016`)
   4. `rcac_mcp` → `cluster_mcp.core`: imports, `monkeypatch.setattr` targets, `__import__('rcac_mcp.…')`
      in 9 mutant anchors, and logger names. The app logger is `__name__`, so stderr lines read
      `[cluster_mcp.core]` (`test_cli.py:103-112`, `test_tokens.py:200,208`; `caplog` and `r.name`
      in `test_exec_mode`, `test_startup`, `test_site_startup`, `test_launch`)
   5. `rcac-mcp` → `cluster-mcp` for the console script (`test_cli.py:23`, `test_tokens.py:46`,
      `ci.yml:44`, `sandbox.sh` comments). Add `LEGACY_CLI = …with_name('rcac-mcp')` for the R3 rows.
   6. env, `rcac://` and the fixture: **additive, not substitution** (below).

## Inventory (tests/, bin/, workflows)

| File | Hits | Edit |
|---|---|---|
| harness.py, conftest.py, ssh_server.py, and the 20 test modules importing the package | ~140 `rcac_mcp` | imports and patch targets, mechanical (rules 4/1) |
| conftest.py:57, test_hygiene.py:399 | `RCAC_SSH_HOST`, `RCAC_USER_MAP` blank lists | **add** the `CLUSTER_MCP_*` names; keep the legacy ones |
| test_exec_mode.py (7), test_site_startup.py (6), test_cli.py:112 | `RCAC_*` env rows, "SSH host required" text | primary rows → new names; **add** legacy-honoured, both-set and warning rows (R5); delenv both budget names (`test_site_startup.py:61,140`) |
| test_context (15), test_storage_resource (22), test_protocol (3), test_ssh_exec (4), test_surface (3) | `rcac://` | reads → `cluster://`. `NOT_OPEN`/`NORMALISED` (`test_storage_resource.py:80-156`) **keep** the rcac shapes and **add** cluster twins. `OPEN_URI` → `cluster://context`, plus an alias-is-open assertion. `test_surface.py:237,278` pin the resource list |
| fixtures/served_surface.json | instructions banner, 2 URIs | scripted delta, as `spec/agents-d-instructions/verify/fixture_deltas.py` did. The fixture has **no server-name slot**, so R8's "server name" delta needs a new key (update `test_surface_fixture_is_the_baseline_shape`) or a separate R2 test |
| test_registry.py:364-365 | `rcac_mcp.docs`, `rcac_mcp.tools.docs` | **not mechanical**: with `rcac_mcp` gone, importing `rcac_mcp.docs` raises with `.name == 'rcac_mcp'`, so `excinfo.value.name == name` fails. Replace with `cluster_mcp.core.docs` and `cluster_mcp.core.tools.docs`, plus a **`rcac_mcp`** row. That row is the useful one: a leftover `src/rcac_mcp/__pycache__` after the move imports as a namespace package, which is exactly the leftover class `absence_violations` classifies. Old *and* new prefixes are covered this way |
| mutants.py | 17 `rcac_mcp`, 5 `RCAC_`, 30 `rcac://` | see Mutants |
| test_hygiene.py:172-184, 295-297; test_audit.py:118; test_sdist_hygiene.py:31-52,203; test_cli.py:115 | synthetic `rcac-mcp`/`rcac_mcp` strings in planted sources and fixtures | cosmetic; rename for grep-cleanliness. The audit lock fixture may need the two extra editable members if `bin/audit_lock.py`'s "every entry but the project's own" count is per-member |
| test_writes.py:84 | `RCAC_MCP_EOF` | test data; **leave** (a blind `RCAC_` sed yields `CLUSTER_MCP_MCP_EOF`) |
| bin/sandbox.sh:16-30,68 | unset and comments | R6: unset both names of both vars |
| test_tokens.py:17; `token.py:22-23` | JWT `ISSUER`/`AUDIENCE == 'rcac-mcp'` | **judgement, not covered by GOAL**: renaming invalidates tokens already minted by deployments. Keep, or rename with a stated reason |

No test today runs `python -m rcac_mcp`. R1's `python -m cluster_mcp.core` needs a new sandboxed drive.

## Mutants specifics

- **Literal names in edits (15 cases).** These need **re-planting** against the new env helper, not
  substitution: `ladder-rungs-3-4-swapped`, `ladder-explicit-yields-to-env-host` and
  `ladder-env-host-ignored`, which anchor on `os.environ.get('RCAC_SSH_HOST')`. Three more are
  judgement calls: `read-hook-resolves-storage-only` (`== 'rcac://storage'`), `read-hook-rcac-scheme-only`
  (make it cluster-scheme-only, add an rcac-scheme-only twin) and `read-hook-defaults-scheme`. The
  remaining 9 are `__import__('rcac_mcp.…')`, which is mechanical.
- **`why` fragments (31 cases)** quote shapes such as `'xrcac://context'` and `'RCAC://storage'`. They
  match only while the shape is a key of `NOT_OPEN`/`NEAR_OPEN`. `report()` joins every violation
  untruncated (`test_no_executor.py:96`), so any surviving key works. Keeping the rcac shapes in
  `NOT_OPEN` keeps all 31 valid. Dropping them turns 31 kills into "wrong reason".
- **New cases worth adding:** the alias storage entry marked `executor: False`; the alias context
  closed; legacy env winning when both are set; the deprecation warning dropped or sent to stdout;
  `rcac-mcp` changing the exit status.
- `spec/resource-reads-without-executor/remediation/sweep.py:23,87` hardcodes `src/rcac_mcp/`. It is a
  point-in-time record; leave it to break (non-goal).

## Runtime (for phase budgets)

- Full verify (both eras + sandboxed `--help`): **about 7–8 min** on a dev laptop, under 1 GB
  (`spec/agents-d-instructions/verify/p4.sh:6`, `spec/resource-reads-without-executor/verify/p3.sh:7`).
- All 306 mutation cases, sequential, about 2 s each: **6–10 min**. AGENTS.md:994's "about 3 minutes" is
  stale; `spec/absence-check-leftover-classification/verify/check.py:23` measured about 6 min.
- `test_near_open_read_is_refused` reads about 5,700 shapes (4–5 s per row). If the aliases are
  `RESOURCE_REGISTRY` entries, the neighbourhood doubles (the `≥ 2500 × served` floor scales with it):
  about 11.5k reads per row.

## Risks

- **Packaging coupling.** `mutants.yml` and `ci.yml` run `uv sync --locked`. In a virtual workspace root
  that installs no members, so the id-listing step fails with "no mutation cases found". The sync needs
  `--all-packages` or a root that depends on the members.
- **Dependency direction.** The core's `resources.py:67` and `tools/__init__.py:80-81` import the
  RCAC and Slurm tools. That is a core→member dependency the packaging plan must resolve, and the
  `resources.py` and `tools/__init__.py` mutant anchors move with whatever replaces it.
- **Env prefix.** The sandbox already exports `CLUSTER_MCP_SANDBOX` and `CLUSTER_MCP_REPO`. Any
  prefix-scanning env logic (`CLUSTER_MCP_*`) would see them.
- **SPDX scope.** 29 of the 93 header lines sit in `spec/` scripts. R14 says "every", and GOAL's 93
  count includes them. The history non-goal covers quoted names, not headers. Plan should state the
  choice explicitly.
- **Stale-import gate.** Use an AST scan of `tests/`, `packages/` and `bin/` (Import, ImportFrom, and
  string literals passed to `__import__`/`import_module`/`monkeypatch`) that finds zero `rcac_mcp`
  outside the `test_registry` absence row. Add `git grep` allowlists, excluding `spec/`, `issues/` and
  ROADMAP, for `RCAC_(SSH_HOST|USER_MAP|INSTRUCTIONS_BUDGET)` (legacy fallback, sandbox unset, blank
  lists, legacy rows, README) and `rcac://` (alias definitions, legacy shapes, `why` fragments). Keep
  the allowlists in the cycle's verify script, not the suite, since they encode the window.
