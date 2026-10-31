# GOAL — Capabilities you don't have shouldn't be tools you see

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** capability-extras
- **kind:** feature
- **appetite:** big

## Problem

Every tool registers unconditionally, and every install carries every capability. The core
distribution hard-depends on both capability members
(`packages/cluster-mcp/pyproject.toml:15-17`, with workspace sources at `:23-25`: "the core's tool
registry imports them"). `core/tools/__init__.py` defines `TOOL_REGISTRY` and `mcp_tool`, then
imports every tool module at the bottom of the file, the Slurm and RCAC members included
(`packages/cluster-mcp/src/cluster_mcp/core/tools/__init__.py:76-83`; `rcac` at `:81`, `slurm` at
`:82`); `@mcp_tool` appends at decoration time. There is no condition anywhere. A cluster with no
Slurm still advertises `sbatch`, `squeue`, `scancel`, `sacct`, `sinfo`, `scontrol_show_job` and
`scontrol_show_node` (the Slurm member), and every non-Purdue cluster still advertises the RCAC
member's ten tools — `myquota`, `storage_paths`, `jobinfo`, `jobcmd`, `jobenv`, `jobscript`,
`showpartitions`, `average_wait`, `slist`, `sfeatures` (the seed listed `slist` and `sfeatures` as
Slurm tools; the rename moved them into the RCAC member). Each is an invitation to a connecting
model to compose a workflow that cannot run. LMOD tools will have the same problem the moment they
exist.

The instructions are just as fixed. `core/server.py` imports `CORE_INSTRUCTIONS`,
`SLURM_INSTRUCTIONS` and `RCAC_INSTRUCTIONS` by name (`core/server.py:22`, `:27-28`) and joins them
into one `Final[str]` constant (`:71`), so the text every model reads first names tools whether or
not they could work. The core reaches into the RCAC member in one more place: the
`cluster://storage` resource and its `rcac://storage` alias call the member's
`resolve_storage_paths()` from inside their handler (`core/resources.py:71`, registered at `:95`,
aliased at `:106`).

`AGENTS.md` § *Direction* commits to `cluster-mcp[slurm,lmod]` as the shape of the answer: you
install the capabilities you have. The rename cycle built the workspace that makes this possible —
each capability is its own distribution under the shared PEP 420 `cluster_mcp` namespace — but
nothing yet lets a capability be absent. This collides with a documented invariant rather than
sitting beside it: `AGENTS.md` § Invariants §7 states that registration is an import-time side
effect of a hardcoded import list, and §9 states that the base instructions are exactly three texts
joined in a fixed order. This cycle **replaces** both contracts. **Pre-existing:** n/a — new work.

## Outcome / vision

You install the capabilities your cluster has. `cluster-mcp[slurm]` adds the scheduler group to the
generic core; a capability that is not installed is not imported, not registered, and not named in
the served instructions, so a connecting model sees exactly the tools that exist. A capability
distribution registers itself through one entry-point group, so the next one (LMOD, xdu, a site's
own tools) plugs in without editing the core. The instructions every model reads are composed at
startup from what actually loaded. With every capability installed, the server serves exactly what
it serves today, and nobody running the old install line notices a thing.

## Acceptance criteria (the contract)

- **R1** — The core distribution `cluster-mcp` SHALL depend on no capability member
  unconditionally, and SHALL declare the optional extras `slurm` and `rcac`, each of which installs
  that member's distribution (`cluster-mcp-slurm`, `cluster-mcp-rcac`).
- **R2** — WHEN the server starts, it SHALL register the tools of every installed capability
  distribution discovered through one entry-point group, and SHALL import and register nothing from
  a capability distribution that is not installed. The Slurm and RCAC members SHALL both register
  this way.
- **R3** — No core module SHALL import a capability member by name. Adding a capability distribution
  SHALL require no edit to any core module.
- **R4** — WHERE only the core distribution is installed, the server SHALL start without error, and
  `TOOL_REGISTRY` SHALL hold exactly the core's tools (`run_command`, `list_directory`, `read_file`,
  `write_file`, `upload_file`, `download_file`, `cluster_context`).
- **R5** — The served base instructions SHALL be composed at startup from the core's text and the
  text of each registered capability, and SHALL name exactly the tools in `TOOL_REGISTRY`, verified
  by a test that cross-checks the two under at least two capability sets (core only, and every
  member).
- **R6** — WHEN every capability member is installed, the served surface SHALL be unchanged: tool
  names and descriptions, instructions text and order, and resources match today's, and
  `test_served_surface_matches_baseline` passes with no fixture edit.
- **R7** — The `cluster://storage` resource and its `rcac://storage` alias SHALL be registered by
  the RCAC member through the same entry-point group as its tools, and SHALL be served only WHERE
  that member is installed.
- **R8** — IF an installed capability distribution fails to load, THEN the server SHALL exit at
  startup with a message naming that distribution, and SHALL NOT start with the capability silently
  missing.
- **R9** — The `rcac-mcp` compat distribution SHALL install the core, Slurm and RCAC members, so
  that WHEN an existing client config names the `rcac-mcp` command or the repository-root git
  install, the server SHALL serve exactly the tools, instructions and resources it serves today.
- **R10** — In the same commit that lands the new registration and composition contract,
  `AGENTS.md` § Invariants §7 and §9 and § Packaging SHALL describe it, and `README.md`'s install
  line SHALL name the extras a Purdue user needs (`cluster-mcp[slurm,rcac]`), with its tool
  inventory saying which extra serves which tool.

## Non-goals (no-gos)

- **A runtime capability probe** (asking the cluster whether, say, `sinfo` exists, so an installed
  capability with nothing behind it advertises nothing). Deferred to
  [`issues/capability-probe.md`](../../issues/capability-probe.md), filed in this cycle's shape
  commit.
- **Any switch beyond installation**, including a per-capability opt-out on an installed member, a
  CLI flag or an environment variable. Installation is the only switch; "installed but nothing
  behind it" is the probe seed's question.
- **The site-extra contract** (`site-extras`): `cluster-mcp[rcac]` as a bundle alias of capability
  extras (LMOD, xdu), the documented pattern another center copies to add its own extra, packaged
  site context as data and its composition with `/etc/agents.d/*.md`. Making the RCAC member *a
  capability like any other* is not that contract.
- **Storage discovery beyond Purdue** (`generalize-storage-discovery`, absorbed by `site-extras`):
  `resolve_storage_paths()` keeps parsing `myquota` and `findscratch`; it only moves with its
  member's registration (R7).
- **Any new tool or tool family**: the `file_*` family, annotations, response budgets and
  `--profile read-only` (`tool-surface`); the `job_*` family (`slurm-capability`); the LMOD group
  (`lmod-tool-group`); the xdu group (`xdu-storage`). No existing tool is renamed, reworded or
  removed; R6 pins that.
- **Other centers' extras** (`alcf`, `ncsa`, `tacc`).
- **Member-registered HTTP routes and icons** (the favicon, `rename-leftover-identity-strings`).
- **Changing `@mcp_tool`'s `FunctionTool` behaviour.** That a decorated tool is not callable is a
  property of the decorator and survives any registration redesign (§ Invariants §7).
- **Publishing to PyPI** or changing the git-install-with-uv model (§ Packaging).
- **Removing the legacy names** (`remove-legacy-names`).

## Clarifications

- **Q:** What does an extra actually gate, since these tools shell out and need no Python
  dependency? — **A:** Each capability is its own distribution in the uv workspace, sharing the PEP
  420 `cluster_mcp` namespace, so an extra such as `slurm = ["cluster-mcp-slurm"]` installs real
  code, and an entry-point group registers it (resolved 2026-10-16; the workspace landed with the
  rename, 2026-10-30).
- **Q1:** What does a bare `cluster-mcp` install include, and what does the `rcac-mcp` compat
  install include? — **A:** Bare `cluster-mcp` is the core only. The `rcac-mcp` compat install
  pulls core + Slurm + RCAC, so every existing config serves exactly what it does today. The
  README's install line, in the same commit, names the extras a Purdue user needs
  (`cluster-mcp[slurm,rcac]`); R9 and R10 carry this (ruled by the foreman, 2026-10-31).
- **Q2:** Is a runtime capability probe in scope? — **A:** No. It puts a remote round trip on the
  startup path of a server whose SSH connection is established eagerly, behaves differently in
  `local` mode, and has no user to probe as in `delegate` mode over HTTP. It is a non-goal with a
  destination, [`issues/capability-probe.md`](../../issues/capability-probe.md), filed with its
  `ROADMAP.md` entry in the shape commit (ruled by the foreman, 2026-10-31).
- **Q3:** Is there any enable/disable switch beyond installation? — **A:** No. Installation is the
  only switch, and R8 covers load failure only; a per-capability opt-out is a non-goal (ruled by the
  foreman, 2026-10-31).
- **Q4:** Does the RCAC member become optional in this cycle, or wait for `site-extras`? — **A:** It
  becomes an ordinary optional capability with a `[rcac]` extra, registered only through the
  entry-point group with its tools, its instructions and the storage resources (`cluster://storage`
  and its `rcac://` alias). `site-extras` keeps the bundle alias, the contributor contract, storage
  generalization and site-context composition. Whether the RCAC member declares a dependency on
  the Slurm member (several RCAC tools take a Slurm job id) is left to the plan (ruled by the
  foreman, 2026-10-31).

## Related materials

- Seed: [`issues/capability-extras.md`](../../issues/capability-extras.md)
- Deferred here: [`issues/capability-probe.md`](../../issues/capability-probe.md) (Q2)
- ROADMAP: Part I, "Capabilities you don't have shouldn't be tools you see"
- Prior cycle: [`spec/rename-to-cluster-mcp/`](../rename-to-cluster-mcp/) (the workspace, the three
  instruction texts)
- Downstream seeds this leaves room for: [`issues/site-extras.md`](../../issues/site-extras.md),
  [`issues/generalize-storage-discovery.md`](../../issues/generalize-storage-discovery.md),
  [`issues/tool-surface.md`](../../issues/tool-surface.md),
  [`issues/slurm-capability.md`](../../issues/slurm-capability.md),
  [`issues/lmod-tool-group.md`](../../issues/lmod-tool-group.md),
  [`issues/xdu-storage.md`](../../issues/xdu-storage.md)
- `AGENTS.md` § Direction, § Packaging, § Invariants §7, §8, §9
- Source: `pyproject.toml` (the compat root), `packages/cluster-mcp/pyproject.toml`,
  `packages/cluster-mcp/src/cluster_mcp/core/tools/__init__.py`,
  `packages/cluster-mcp/src/cluster_mcp/core/server.py`,
  `packages/cluster-mcp/src/cluster_mcp/core/resources.py`,
  `packages/cluster-mcp-slurm/`, `packages/cluster-mcp-rcac/`
- Tests: `tests/test_surface.py`, `tests/test_instructions.py`, `tests/test_packaging.py`
