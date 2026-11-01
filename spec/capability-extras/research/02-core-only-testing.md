# Research 02: testing "core only", two capability sets, and a broken capability

**Recommendation:** two layers. (1) A fast **unit** layer composes the server in-process from an
explicit capability set (`()` and every member). (2) **One integration module** builds a real
core-only venv once per session with `uv sync --package cluster-mcp --no-dev --frozen --offline`
into `tmp_path_factory`, and drives its `cluster-mcp` over stdio in the selected era. The
broken-capability rows use the dev venv's CLI, with a planted dist-info prepended to `PYTHONPATH`.
A warm run costs about 0.35 s for the venv and about 1.2 s per stdio drive, so roughly 3–4 s per
era pass.

All timings are from a scratch copy under `$TMPDIR` (uv 0.13.6, CPython 3.14.6). The copy had the
extras in place, member entry points under a `cluster_mcp.capabilities` group, and a 6-line
prototype loader, re-locked with `uv lock --offline` (0.02 s). Nothing ran in the worktree's venv.

## 1. A real core-only environment

- `UV_PROJECT_ENVIRONMENT=<tmp>/venv uv sync --package cluster-mcp --no-dev --frozen --offline`
  took **0.35 s** cold, including an editable build of the core, and 0.05 s on a re-sync. It works
  fully offline from the dev cache: every locked wheel and hatchling are already there. The result
  is exactly `cluster_mcp-0.1.5.dist-info` and one `.pth` file.
  - `TOOL_REGISTRY` held the seven core tools, the group listed no entry points, and
    `find_spec('cluster_mcp.slurm')` was `None`.
  - `--extra slurm` gave core plus Slurm in 0.11 s. A third set is almost free if the plan wants
    an RCAC-without-Slurm row (Q4).
- **Today, before the cycle,** the same command installs both members (0.40 s), because the
  core hard-depends on them. The real drive therefore turns red on any regression of R1, which no
  in-process simulation can catch.
- **It never touches `$WT/.venv`.** uv targets `UV_PROJECT_ENVIRONMENT`. An inherited
  `VIRTUAL_ENV` (as under `uv run pytest`) only prints a mismatch warning, so drop `VIRTUAL_ENV`
  from the child env. `--frozen` never writes `uv.lock` or re-resolves; lock currency stays
  verify's `uv lock --check`. No build artefacts appeared in the source tree.
- **Run it under `bin/sandbox.sh`** (`[str(SANDBOX), 'uv', 'sync', …]`, which satisfies
  `sandbox_violations`). The sandbox pins `UV_PROJECT` to the repo and keeps the real
  `UV_CACHE_DIR`, so the cache is reachable from the throwaway HOME.
- **Use editable, the default. Never use `--no-editable` without `--reinstall-package cluster-mcp`.**
  The probe: I appended a line to `core/resources.py` and built a fresh non-editable venv.
  - uv reused its cached wheel (no `Built` line), so the venv served **stale code**: a fake pass.
  - Editable venvs read the live source.
  - Editable metadata (scripts, entry points, extras) is rebuilt when `pyproject.toml` changes;
    this was verified.
- **Shape:** a session-scoped fixture that builds the venv once per pytest run under
  `tmp_path_factory`. The venv is about 80 MB, cloned or hard-linked from the cache. Every test that
  uses it is `integration`: the unit guard refuses every process launch.

## 2. In-process or in-dev-venv simulation: what each proves and what it fakes

| Approach | Cost | Proves | Can fake (passes while the real core-only install is broken) |
|---|---|---|---|
| **Pure composition**: build the server or registry from an explicit capability list, served through `harness.served_tools` / `served_instructions` / `served_surface` in-process | ms, `unit`, both eras | composition, ordering, the instructions/registry cross-check, resources gated by capability | R1 deps; entry-point metadata (group, object path); a core module importing a member at import time (the dev venv has every module); the CLI startup path |
| **Patching `entry_points`** in a dev-venv subprocess, plus a meta-path blocker (tested: 0.9 s, gives the core-only and Slurm-only registries) | about 1 s, `integration` | discovery-driven startup without the uv step | R1. It is coupled to how the core imports `entry_points`: the patch must land before the core binds the name. |
| **Filtered site dir** (symlink site-packages minus member dist-infos, `python -S`, core `src` on `PYTHONPATH`) | 0.8 s plus setup | the same as a real venv, minus the extras metadata | R1/R9 metadata. It is fiddly and slower than the real `uv sync`. **Not worth it.** |

**Design consequence for the plan.** Registration today is `@mcp_tool` appending to a module
global at import time. The test session imports every member (`mutants.py` and
`test_packaging.py` do). So a unit test cannot get a core-only registry unless:

- composition is a function of an explicit capability set, and
- the server factory accepts that set (defaulting to the discovered one).

That parameter is a test seam, not a user switch (no CLI flag or env var, per the no-switch
non-goal). Say so in the plan so review does not read it as one.

**Pin R3 statically**, in a unit AST scan of every `.py` file in the core portion for imports of
`cluster_mcp.slurm` or `cluster_mcp.rcac`, lazy in-function imports included (today
`core/resources.py:71`). It is cheap and immune to the dev venv having every module.

## 3. A fabricated broken capability (R8): verified

Plant this in a temp dir:

```
broken_capability-0.1.0.dist-info/METADATA        Metadata-Version: 2.1 / Name: broken-capability / Version: 0.1.0
broken_capability-0.1.0.dist-info/entry_points.txt [cluster_mcp.capabilities]\nbroken = brokencap.tools
brokencap/__init__.py, brokencap/tools.py         raise RuntimeError('planted load failure')
```

With `PYTHONPATH=<dir>`, `entry_points(group=…)` yields it with `ep.dist.name ==
'broken-capability'`. It is listed beside the real members in the full venv, so **R8 needs no
core-only venv.** The prototype CLI exited 1 with `cannot load capability broken-capability: …`
in 0.8 s.

Rows worth having:

- the module raises on import;
- the entry point names a **missing module** (`ModuleNotFoundError`). This is the case a loader
  that treats `ImportError` as "not installed" would swallow, and an installed dist is never
  absent;
- the entry point names a missing attribute (`module:attr`).

Assert a nonzero exit, the dist name on stderr, and no tools served. For a unit row, use
`PathDistribution(Path(dist_info)).entry_points`: those entry points carry `.dist`. Combine it with
`monkeypatch.syspath_prepend` and no process. A bare `EntryPoint(...)` has `dist is None`, so the
loader's message must not crash on that.

**Mutation-runner caveat.** A mutant child runs with `PYTHONPATH=<mutated copy>`. A drive must
**prepend** its planted dir (`os.pathsep.join([planted, os.environ.get('PYTHONPATH', '')])`). If it
replaces `PYTHONPATH`, the CLI loads the unmutated editable install, and every loader mutant
survives.

## 4. Fit with eras, markers, hygiene and mutants

- **Eras.** `harness.stdio_tools([SANDBOX, <venv>/bin/cluster-mcp, '-e', 'local'], ERA)` returns
  tools, instructions and the negotiated era (`Listed`). Both eras gave the same seven tools and
  666 characters of instructions. Run the R5 cross-check on that one listing with
  `test_instructions.instruction_violations`.
  - Use the selected `ERA` (the gate runs both passes), or pin each era on its own row as
    `test_transports` does.
  - `Listed` holds no resources. R7's core-only "storage not served" needs either a harness
    extension (only `harness.py` may import the stack) or the unit composition layer.
- **Markers.** Composition is `unit`. Every venv build, CLI drive or planted-dist drive is
  `integration`.
- **Hygiene.**
  - Every launch starts `[str(SANDBOX), …]`.
  - No `R#`/`P#` token anywhere: `\b[RP][0-9]{1,2}\b` scans tests and the package, so name the
    planted dist and its entry point accordingly.
  - Add no new skip: a missing `uv` should fail, not skip.
- **Mutants.** The runner copies only the namespace. It cannot mutate `pyproject.toml` (extras,
  entry points), and `repo_edits` only reaches `README.md` and the surface fixture. So R1, R9 and
  the entry-point declarations need unit tomllib checks over the four pyprojects (and
  `distribution(...).requires`) plus the real drive.
  - Under a mutant, the core-only drive inherits the copy's three members on `PYTHONPATH`, but it
    has no member metadata. Discovery is unaffected and the mutated core is what runs, so the drive
    is a valid target.
  - Assert on served output, never on `find_spec('cluster_mcp.slurm') is None`, which is false
    under the runner.

  Suggested cases:

  1. **`capability-order-from-discovery`**: the composer drops its explicit order key. Target: a
     unit test composing from reversed and shuffled capability lists. The why names the order.
     - Today, instructions run core, Slurm, RCAC, but `TOOL_REGISTRY` runs core, RCAC, Slurm,
       `cluster_context` (import order).
     - `entry_points()` order follows `sys.path` and directory listing. A name sort puts `rcac`
       before `slurm` and breaks `test_base_is_core_slurm_then_overlay`.
     - The key must be explicit. The tool order is not pinned today (the checks use sets), so
       decide whether to pin it.
  2. **`capability-load-failure-swallowed`**: `except Exception: continue` (or
     `except ImportError`) in the loader. Targets: the broken-dist CLI drive and the
     `PathDistribution` unit row.
  3. **`storage-resource-unconditional`**: the core registers `cluster://storage` and its alias
     itself. Target: the core-only resources check (unit composition with `()`).
  4. **`core-imports-member-by-name`**: re-add `from cluster_mcp.slurm import tools` in core.
     Targets: the static R3 scan and the core-only drive (under the runner the copy's Slurm
     module registers, so the tool list has unexpected tools).

  Optional: `capability-group-renamed` (the group string in core). It is killed by
  `test_registry` in the dev venv, because nothing is discovered.

## 5. CI

`ci.yml` runs `uv sync --locked` before pytest. That fills the runner's uv cache with every locked
wheel and with hatchling (every member's build backend). The core-only set is a subset of that,
so the `--offline` sync inside the suite needs **no network**. `enable-cache: false` only skips
cross-run persistence. The sandbox keeps whatever `UV_CACHE_DIR` the step has, and the interpreter
is local. No workflow change is needed.

**Pre-existing finding, out of scope but relevant to "offline".** Every stdio CLI drive, today's
`test_transports` and `test_cli` included, makes FastMCP fetch `https://pypi.org/pypi/fastmcp/json`
for its banner update check. It showed in the drive's stderr. The new drives should set
`FASTMCP_CHECK_FOR_UPDATES=off` in the child env. Making that suite-wide, through the sandbox or
the harness, is a candidate seed.
