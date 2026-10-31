# 05 — Packaging: extras, the compat root, install lines (R1, R9, R10)

Lab: a scratch copy of the worktree under `$TMPDIR`, uv 0.13.6 and the 0.12.17 floor, all offline
from the warm cache; install probes against a throwaway local git snapshot (`git+file://`), run
under the worktree's `bin/sandbox.sh`. Nothing from GitHub.

## Recommendation

- **Core** (`packages/cluster-mcp/pyproject.toml`): drop `cluster-mcp-slurm` and `cluster-mcp-rcac`
  from `dependencies` and the comment above them; add
  `[project.optional-dependencies] slurm = ["cluster-mcp-slurm"]`, `rcac = ["cluster-mcp-rcac"]`;
  **keep** both `{ workspace = true }` sources (they are what makes the extras resolve from the same
  commit).
- **Compat root**: `dependencies = ["cluster-mcp[slurm,rcac]"]`, source unchanged (one
  `cluster-mcp = { workspace = true }`). Better than listing all three: one source, the compat set
  follows the extras by definition, and the rename cycle's "root depends on cluster-mcp alone"
  check (it strips at `[`) still holds. **This dependency is load-bearing for the dev env**, see below.
- `uv lock` in the same commit (§ Conventions).

## What the lab showed

- **Lock diff** is small and mechanical: the core's `dependencies` lose the two members and gain
  `[package.optional-dependencies] rcac/slurm`; `requires-dist` entries carry
  `marker = "extra == 'rcac'"` / `'slurm'`; a `provides-extras = ["slurm", "rcac"]` line; the root's
  dependency becomes `{ name = "cluster-mcp", extra = ["rcac", "slurm"] }`. Still 88 packages.
  `uv lock --check` passes on the new lock under 0.13.6 and 0.12.17, and fails on the stale one
  (and `uv sync --locked` refuses it), so the profile's verify catches a forgotten relock.
- **The cycle core[slurm] → slurm → core is fine** for `uv lock`, `uv sync`, `uv build`,
  `uv pip install` and git installs, as the hard cycle was.
- **Built core wheel METADATA**: `Provides-Extra: rcac`, `Requires-Dist: cluster-mcp-rcac; extra == 'rcac'`,
  `Provides-Extra: slurm`, `Requires-Dist: cluster-mcp-slurm; extra == 'slurm'`, no unconditional
  internal requirement. Root wheel: `Requires-Dist: cluster-mcp[rcac,slurm]` (hatchling sorts the
  extras; single-quoted markers). `uv build --all-packages --no-sources` still gives 4 wheels + 4
  sdists; `twine check --strict` 8 PASSED; `bin/sdist_hygiene.py` clean; the rename cycle's
  `checks.py wheels` scan passes unchanged. Sdist hygiene is unaffected.
- **`uv sync` is exact, and installs only the root and its dependency closure, not "every member".**
  Root → `cluster-mcp[slurm,rcac]`: plain `uv sync` / `uv sync --locked` (the profile's `setup`, CI,
  `mutants.yml`) installs all three members editable. Control: with the root on bare `cluster-mcp`,
  `uv sync` installs the core only and **removes** the members; only `--all-packages` brings them
  back. So no dev-group or setup change is needed, provided the root keeps the extras.
- **Core-only and partial environments without touching `.venv`**:
  `uv run --isolated --package cluster-mcp python …` → only `cluster_mcp.core` importable;
  `… --package cluster-mcp --extra slurm …` → core + slurm. Useful for R4/R5 subprocess tests and
  verify drives (needs the cache or network on CI).
- **Entry points (R2) need no lock change**: adding
  `[project.entry-points."cluster_mcp.capabilities"]` to a member left `uv lock --check` green;
  `uv run` re-installed the editable member and `importlib.metadata.entry_points` saw it; the built
  wheel carries `entry_points.txt`. A venv used without a resync (`.venv/bin/…`, `--no-sync`) will
  not see new entry points until `uv sync`. The mutants harness copies portions onto `PYTHONPATH`
  and keeps the venv's dist-info, so module-path entry points resolve into the mutated copy.
- **Install forms from one commit** (`uv pip install` into fresh venvs, snapshot commit + a later
  commit carrying a marker in the Slurm member; each `direct_url.json` checked):

  | spec | installs (all at the snapshot commit, no later marker) |
  |---|---|
  | `cluster-mcp @ git+…@sha#subdirectory=packages/cluster-mcp` | core only |
  | `cluster-mcp[slurm] @ …` | core + slurm |
  | `cluster-mcp[slurm,rcac] @ …` | core + slurm + rcac |
  | `rcac-mcp @ git+…@sha` (repo root) | root + all three members |

  The same held under uv 0.12.17 for the extras form and the root form. `uvx --from
  'cluster-mcp[slurm,rcac] @ git+…#subdirectory=packages/cluster-mcp' cluster-mcp --help` exits 0;
  `uvx --from <root> rcac-mcp --help` exits 0 with the deprecation warning. **Today's core-only
  `uvx … cluster-mcp --help` dies with `ModuleNotFoundError: cluster_mcp.rcac`** (the registry
  import), the exact failure R2–R4 remove; it is a good red-then-green row.
- **Dockerfile** (`uv pip install --system -e .` at the root): with the root on extras the image
  gets all four distributions; with a bare root dependency it would get the core only and silently
  lose 17 tools. So the container is safe only through R9's root change; its comment ("builds
  cluster-mcp and its Slurm and RCAC members") should name the extras. `compose.yml` needs nothing.

## README syntax (R10)

uv takes a PEP 508 direct reference with extras in `--from`:

```
uvx --from 'cluster-mcp[slurm,rcac] @ git+https://github.com/PurdueRCAC/cluster-mcp#subdirectory=packages/cluster-mcp' cluster-mcp …
```

In the client JSON it is one `args` element (spaces included). In a shell it **must be quoted**:
unquoted `[slurm,rcac]` is a glob (zsh aborts with `nomatch`). pip remains wrong: the extras'
member names are still bare names unregistered on PyPI, so the dependency-confusion note stays
(a core-only install resolves no internal name at all).

## Release recipe `post_verify`

Line 1 becomes the README line (`'cluster-mcp[slurm,rcac] @ git+https://github.com/PurdueRCAC/cluster-mcp@{v}#subdirectory=packages/cluster-mcp'`);
add a core-only line (the bare `git+…@{v}#subdirectory=packages/cluster-mcp`, `cluster-mcp --help`)
so the release proves R4's install too; keep the root `rcac-mcp --help` line (R9). Rewrite the
`install-probe` caveat to match. `--help` exit 0 proves install and import only; if R2 defers
discovery to server start, `--help` no longer exercises it, so the cycle's own probe must check
the registry per install form (below). `ci-mirror-no-index` names the bare core URL: it stays
true as a core install; decide whether it should name the extras form.

## Spots that state or perform the default install

- `packages/cluster-mcp/pyproject.toml:15-17` (deps + comment), `:23-25` (sources: keep).
- `pyproject.toml:1-3` (header comment), `:7` description, `:10` dependency.
- `README.md:3-5` ("carries the Slurm tools and the Purdue RCAC-specific tools beside its core"),
  `:17` Quick Start args, `:27-31` install note ("`cluster-mcp` depends on its Slurm and RCAC
  members"), `:88-91` compat note, `:170-213` inventory (three groups → say core / `[slurm]` /
  `[rcac]`), `:128-131` hosted examples (say how the binary was installed), `:217-219` `uv sync`.
- `packages/cluster-mcp/README.md:7-12` ("A default install also carries…" and its uvx line);
  `packages/cluster-mcp-{slurm,rcac}/README.md` ("installed with `cluster-mcp`, not on its own" →
  through the extra).
- `AGENTS.md:93` (`uv sync` comment), § Packaging `:1233-1237` (core depends on both members;
  "`uv sync` installs every member": now via the root's extras) and `:1276` install URL;
  recipe `post_verify` `:1393-1394` and caveats `ci-mirror-no-index`, `pypi`, `install-probe`.
- `Dockerfile:12-13` comment. No change: `compose.yml`, `.github/workflows/*.yml` (`uv sync --locked`).

## `tests/test_packaging.py`

Pins today: namespace (no `cluster_mcp/__init__.py`, `only-include`/`sources`), the four versions
equal, `__version__` from metadata, console scripts, and `distribution('rcac-mcp').requires ==
['cluster-mcp']` (`:133`), which **breaks**: it becomes `['cluster-mcp[rcac,slurm]']` (sorted). It
pins no core dependency today; that lived in the rename cycle's `checks.py source`, which now fails
("does not depend on cluster-mcp-slurm"). Add, from `tomllib`: no internal name in the core's
`dependencies`; `optional-dependencies == {'slurm': ['cluster-mcp-slurm'], 'rcac': ['cluster-mcp-rcac']}`;
both workspace sources kept; the root's dependencies `== ['cluster-mcp[slurm,rcac]']`; from installed
metadata, `Provides-Extra` `['rcac', 'slurm']` and each member conditional on its extra. Update the
module docstring. `test_each_member_holds_only_its_own_subpackage` imports every portion, so it
relies on the root's extras keeping the dev env full.

## Reusable rename-cycle gates (`spec/rename-to-cluster-mcp/verify/`)

Reuse as-is: the build + `checks.py wheels` + `twine` + `sdist_hygiene.py` block of `p1.sh`;
`members.py` (full install, R6); `failclosed.sh`; `legacy_cli.sh`; `lib.sh` (`pytest_both`,
`run_mutants`, `full_*`). Adapt, not reuse: `probe.sh` (snapshot repo + later-commit marker +
`direct_url.json` check is the right shape; step 2's `cluster-mcp @ $spec` now installs the core
only — make it the extras spec, and add core-only and `[slurm]` rows asserting the registered tool
set per row); `checks.py source` (core deps rule), `profile` (`POST_VERIFY` constant), `readme`
(install-line rule). `baseline.sh`/`compare.py` are tied to 0.1.4; this cycle's baseline is 0.1.5.
Rename-cycle lessons that carry over: drive both protocol eras; never let a gate be a marker
selection; a probe needs a fresh HOME so no cache entry is reused across content; the networked
lock audit stays out of `verify`.

Open for the plan: if the RCAC member declares a dependency on the Slurm member (GOAL Q4), it needs
its own `cluster-mcp-slurm = { workspace = true }` source and a relock, and `cluster-mcp[rcac]`
then pulls Slurm too.
