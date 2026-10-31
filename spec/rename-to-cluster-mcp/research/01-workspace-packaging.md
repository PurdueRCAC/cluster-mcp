# Research 01 — Workspace packaging (R1, R9, R10, R15 packaging side)

Lab: a throwaway three-member workspace (core with `cmdkit` from PyPI; Slurm and RCAC members
each registering one tool through core's decorator), driven with **uv 0.12.17** (the floor and
CI's pin) and **uv 0.13.6** (local), CPython 3.14.6, 2026-10-29. Every claim below marked *lab*
ran on both versions unless it says otherwise. PyPI was reachable.

## Recommendations

1. **Virtual workspace root** (no `[project]` at the root). The root holds only workspace
   furniture:

   ```toml
   # /pyproject.toml
   [tool.uv.workspace]
   members = ["packages/*"]

   [dependency-groups]
   dev = ["pytest>=8.0.0", "pytest-asyncio>=0.23.0"]

   [tool.uv]
   required-version = ">=0.12.17"

   [tool.pytest.ini_options]          # unchanged; tests stay in root tests/
   ```

   A plain `uv sync` at a virtual root installs **every member** (editable) plus the root's dev
   group; `--all-packages` is not needed (*lab*, 0.12.17). `uv sync --locked`, `uv lock --check`,
   `uv run pytest -q` (rootdir = root, `--strict-markers` loaded), `uv run cluster-mcp`,
   `uv run rcac-mcp` and `uv run python -m cluster_mcp.core` all work from the root and with
   `UV_PROJECT=<root>` from another cwd, i.e. under `bin/sandbox.sh` unchanged (*lab*).
   Root-is-core was not chosen: it would put core's sdist root at the repo root, so root
   furniture (`bin/`, `spec/`, `tests/`, the security lane) is back inside an sdist and only the
   exclude list stands between it and a release.

2. **Dependency direction: declared cycle (option a).** Core depends on both members; each
   member depends on core. Lab: `uv lock`, `uv sync`, `uv build --all-packages`,
   `twine check --strict`, `bin/sdist_hygiene.py`, `uv pip install`, and the git
   `#subdirectory=` install all accept it on both uv versions. It is also the forward-compatible
   choice: `capability-extras` only moves core's two member dependencies into extras; the
   members' `cluster-mcp` dependency is already the long-term direction. Option (b) (members
   declare nothing) works mechanically but ships wheel metadata that lies about a hard import
   and must be reversed next cycle.

   ```toml
   # packages/cluster-mcp/pyproject.toml
   [project]
   name = "cluster-mcp"
   version = "0.2.0"
   readme = "README.md"               # must live inside the member (see risks)
   requires-python = ">=3.14"
   dependencies = [
       "fastmcp>=4,<5", "cmdkit>=2.7.7", "pyjwt>=2.0", "fabric>=3.0", "paramiko>=3.2",
       "cluster-mcp-slurm==0.2.0",
       "cluster-mcp-rcac==0.2.0",
   ]
   [project.scripts]
   cluster-mcp = "cluster_mcp.core:main"
   rcac-mcp = "cluster_mcp.core:<deprecated entry>"   # name is the plan's call
   [tool.uv.sources]
   cluster-mcp-slurm = { workspace = true }
   cluster-mcp-rcac = { workspace = true }
   [build-system]
   requires = ["hatchling"]
   build-backend = "hatchling.build"
   [tool.hatch.build.targets.wheel]
   only-include = ["src/cluster_mcp/core"]
   sources = ["src"]
   ```

   Members mirror it with `dependencies = ["cluster-mcp==0.2.0"]`,
   `[tool.uv.sources] cluster-mcp = { workspace = true }`, and
   `only-include = ["src/cluster_mcp/slurm"]` (resp. `rcac`). Distribution names
   `cluster-mcp-slurm` / `cluster-mcp-rcac` match the prior design; the plan may pick others.

3. **Hatch config: `only-include` + `sources = ["src"]`, not `packages = ["src/cluster_mcp"]`.**
   Lab: with a stray `src/cluster_mcp/__init__.py` planted in a member, `packages=` ships
   `cluster_mcp/__init__.py` in the wheel; `only-include` of the subpackage does not. Wheels
   contain exactly `cluster_mcp/<cap>/**` plus dist-info. Package data under the subpackage
   ships with no extra config: `cluster_mcp/core/static/*.ico` was in the wheel and readable via
   `importlib.resources.files('cluster_mcp.core')` and via `Path(__file__).parent`. (Whether the
   Purdue favicon belongs in core or the RCAC member is an R11-adjacent call for the plan.)

4. **Sdists are member-scoped.** Each sdist contains only `src/…`, `README.md`,
   `pyproject.toml`, `PKG-INFO` of its member dir; root furniture cannot reach it. Keep the
   current `exclude` list in each member's `[tool.hatch.build.targets.sdist]` as defense in
   depth (cheap, and the § Packaging prose names it), and keep `bin/sdist_hygiene.py` as the
   one definition. It already iterates every `*.tar.gz` in `dist/` and roots each at the
   tarball name; lab: clean on all three, exit 0, unchanged. Only its docstring example
   (`rcac_mcp-0.1.0/`) needs the new name. Optional hardening: fail when fewer sdists than
   members are present.

5. **Release gate / CI build step: `uv build --all-packages -o dist/`.** Plain `uv build` at a
   virtual root fails (it tries to build the root with setuptools' legacy backend) (*lab*).
   `--all-packages` builds three sdists and three wheels, each wheel from its sdist (so a file
   missing from an sdist breaks the build, which is good). `uvx twine check --strict dist/*` and
   `uv run python bin/sdist_hygiene.py dist/` need no change. Built wheel metadata carries
   `Requires-Dist: cluster-mcp-slurm==0.2.0` etc. (sources dropped), so the `no-sources`
   caveat stays true as written only if it is updated: there now **is** a `[tool.uv.sources]`,
   but only `workspace = true` entries, which `uv build` drops from metadata; `--no-sources`
   would instead make the build resolve siblings from PyPI. Rewrite that caveat rather than
   add the flag.

6. **One version, lockstep.** All three members carry the same version, and every
   inter-member requirement pins `==` that version. Lab finding: **`uv lock` does not check
   those pins against workspace members** (bumping one member to 0.2.1 while core pinned
   `==0.2.0` locked cleanly), so drift is only caught by a test. Add a unit test that reads the
   three `pyproject.toml` with `tomllib` and asserts one version and matching `==` pins. A
   shared dynamic version file is out: hatchling reads only inside the member root, and a file
   outside it is absent from the sdist the wheel is built from (same failure mode as the
   readme, below). Recipe:

   ```yaml
   version:
     source: packages/cluster-mcp/pyproject.toml project.version
   bump:
     lock: uv lock
     lockstep: [packages/cluster-mcp-slurm/pyproject.toml, packages/cluster-mcp-rcac/pyproject.toml]
     files: [packages/cluster-mcp/pyproject.toml, packages/cluster-mcp-slurm/pyproject.toml,
             packages/cluster-mcp-rcac/pyproject.toml, uv.lock]
     diff_rule: >-
       only project.version and the ==-pinned workspace-member requirements in the three member
       pyproject.toml files, and the three member version entries in uv.lock, change
   tag:
     message: "cluster-mcp {v}"
   post_verify:
     - bin/sandbox.sh uvx --from "git+https://github.com/PurdueRCAC/cluster-mcp@{v}#subdirectory=packages/cluster-mcp" cluster-mcp --help
   ```

   In `uv.lock` a bump changes exactly the three `version = "…"` lines of the
   `cluster-mcp*` `[[package]]` entries; the `==` pins do not appear there (workspace deps lock
   as `editable = "packages/…"`, no specifier). `uv version --package <name> --bump` exists in
   0.12.17 but bumps one member's version only, not the pins; a bump is 3 versions + 4 pins.

7. **`python -m cluster_mcp.core`** works via `packages/cluster-mcp/src/cluster_mcp/core/__main__.py`
   (`from cluster_mcp.core import main; sys.exit(main())`), both in the dev env and from a git
   install (*lab*). The namespace parent breaks nothing there; `python -m cluster_mcp` has no
   `__main__` and must not get one (it would need a `cluster_mcp/` file). `__version__ =
   importlib.metadata.version('cluster-mcp')` resolved `0.2.0` in dev and installed.

8. **Namespace hygiene: two layers.** (a) A unit test in root `tests/` that
   `packages/*/src/cluster_mcp/__init__.py` matches nothing (and, cheaply, that each member's
   `src/cluster_mcp/` holds only its own subpackage). Milliseconds; runs in every phase's
   `uv run pytest`. This layer matters most: lab shows a stray `__init__.py` in **one** member's
   source breaks the editable dev env (`ModuleNotFoundError: No module named
   'cluster_mcp.core'`) even though `only-include` keeps it out of that member's wheel. (b) For
   R1's literal "no built wheel contains", scan the wheels the release gate already builds:
   `uv build --all-packages` took ~0.6 s wall in the lab, so a wheel scan (`zipfile`, reject any
   `cluster_mcp/__init__.py`) is affordable in the gate; fold it into an existing `bin/` script
   or a test that builds into `tmp_path`, plan's choice.

9. **R10 probe**, from a local clone at a commit, under the sandbox:

   ```sh
   sha=$(git rev-parse HEAD)
   bin/sandbox.sh uvx --from "git+file://${CLUSTER_MCP_REPO:-$PWD}@${sha}#subdirectory=packages/cluster-mcp" cluster-mcp --help
   ```

   (The sandbox exports `CLUSTER_MCP_REPO`; outside it use the absolute checkout path.) Lab: on
   0.12.17 and 0.13.6, uv built `cluster-mcp-slurm` and `cluster-mcp-rcac` as
   `git+file://…@<sha>#subdirectory=packages/cluster-mcp-<cap>`. Proof of same-commit, two
   ways that both worked: **(i)** each installed sibling's `direct_url.json` carries
   `vcs_info.commit_id == <sha>` and its own `subdirectory` —
   `uv run --no-project --with "<spec>" python -I -c "…importlib.metadata.distribution('cluster-mcp-slurm').read_text('direct_url.json')…"`;
   **(ii)** a marker: the lab pinned an older commit whose members carried a different marker
   string than HEAD, and the installed tool printed the older marker. (i) is the durable gate
   assertion; it needs no planted marker. The probe needs the network on a cold cache (PyPI for
   hatchling and the dependency tree); with a warm cache `UV_OFFLINE=1` re-ran it. Note that
   `uvx --from` resolves fresh and does **not** read `uv.lock` (as today's `post_verify`).
   Changelog: the release that introduced workspace sources inside git-subdirectory installs
   was not pinned down; it predates the floor, and the floor itself was exercised.

10. **Docker.** Copy the workspace, not one package:
    `COPY pyproject.toml uv.lock README.md ./` + `COPY packages/ packages/`, then either
    `uv pip install --system -e packages/cluster-mcp` (lab: installs core editable and builds
    both siblings from the workspace sources; lock not used) or, lock-faithful,
    `uv sync --locked --no-dev --no-editable` with `UV_PROJECT_ENVIRONMENT` pointed at the
    system prefix or a venv on `PATH` (lab: works, into a separate env). `ENTRYPOINT
    ["cluster-mcp"]`. Any member's `README.md` must be in the build context.

## Residual risks

- **Member `readme` must be inside the member.** Lab: `readme = "../../README.md"` fails the
  sdist build (`Readme path must be within the project directory`). Each member needs its own
  short `README.md` (or no `readme`); the root README stays the user doc. `twine check
  --strict` passed with one-line READMEs.
- **Unchecked `==` pins** (rec 6): without the lockstep test, a partial bump locks and builds
  clean and ships inconsistent metadata.
- **Runtime import cycle** mirrors the declared one: core's tool registry imports the members'
  tool modules at its bottom while those import `mcp_tool` from core. It works (lab, and it is
  today's pattern within one package) only while `mcp_tool`/`TOOL_REGISTRY` are defined before
  the member imports; a member must never import core's top-level `cluster_mcp.core` package
  for something defined after that line.
- **`uv lock` lock-file churn:** the new lock has a `[manifest] members` table and three
  editable entries; the old `rcac-mcp` entry disappears. A 0.12.17-written lock passed
  `uv lock --check` under 0.13.6 (lab).
- **Network:** `bin/audit_lock.py` and the R10 probe need it on a cold cache; phase gates that
  include the probe are not offline-capable unless the cache is warm.
- **pip** cannot install from the git subdirectory form (workspace sources are uv-only), as the
  prior design noted; README install lines must stay uv/uvx.
