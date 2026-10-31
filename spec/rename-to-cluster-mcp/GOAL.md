# GOAL — Rename rcac-mcp to cluster-mcp

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** rename-to-cluster-mcp
- **kind:** refactor
- **appetite:** big

## Problem

The project is generalizing from *the Purdue RCAC MCP server* to *an MCP server for HPC clusters*
(`AGENTS.md` § Direction), and its name says the opposite. "rcac" is load-bearing in more places
than a rename usually reaches, and they don't all want the same treatment:

- **Mechanical but user-visible.** The distribution `rcac-mcp` (`pyproject.toml:2`), the console
  script `rcac-mcp` (`:18`), the package `src/rcac_mcp` (`:25`), `get_version('rcac-mcp')` and
  `__website__` (`src/rcac_mcp/__init__.py:33-34`), the `RCAC MCP Server` version banner (`:62`),
  the FastMCP server name `'RCAC'` (`server.py:127`), the Dockerfile entry point and the CI verify
  step. Every README install line and every user's MCP client config names one of these.
- **Protocol surface.** The resource URIs `rcac://context` and `rcac://storage`
  (`resources.py:47`, `:91`) are identifiers a client may have persisted.
- **Environment variables, the sharp edge.** `RCAC_SSH_HOST`, `RCAC_USER_MAP` and
  `RCAC_INSTRUCTIONS_BUDGET` (§ Configuration). `RCAC_SSH_HOST` sits in every user's client config,
  and `bin/sandbox.sh:68` unsets it **by name** so a bare server fails closed instead of reaching a
  production cluster. Rename the variable without the sandbox and every factory verify command
  silently loses its most important guarantee.
- **Judgement calls, not renames.** `tools/rcac.py` (`myquota`, `jobinfo`, `slist`, `sfeatures`, …)
  genuinely *is* Purdue-specific and keeps a site-flavoured identity rather than being laundered into
  a generic name. `SERVER_INSTRUCTIONS` (`server.py:66-104`) is still partly a Purdue document: since
  `agents-d-instructions` moved the site's quota and path facts into the site context, what remains
  is a tool list that opens with "RCAC MCP Server", labels three tools "(RCAC)", and lists the
  Purdue tools beside the generic ones.
- **Attribution and location.** 93 tracked files carry `SPDX-FileCopyrightText: 2025 Purdue
  University` (21) or `2026 Purdue University` (72). The repository URL is hardcoded in the README,
  `__website__`, and the release recipe's `post_verify` and `ci-mirror-no-index` caveat.

The roadmap folds the uv-workspace restructure into this cycle (ROADMAP § *Nothing here should
assume Purdue*): a core `cluster-mcp` distribution providing `cluster_mcp.core` in a PEP 420
namespace, with Slurm and RCAC members beside it, so that every import moves once instead of twice
when `capability-extras` arrives. The cycle comes after the docs strip and Part 0's releases (0.1.3,
0.1.4), and before `capability-extras`, whose extras are named `cluster-mcp[…]`.

**Pre-existing:** n/a — new work, not a defect.

## Outcome / vision

A user installs and runs the server as `cluster-mcp` from `PurdueRCAC/cluster-mcp`, with the
`#subdirectory=packages/cluster-mcp` git form. An existing user's `rcac-mcp` command, `RCAC_*`
variables and `rcac://` URIs keep working through a stated deprecation window, each with a warning
that names its replacement. The tree is a uv workspace whose core reads as generic. The Purdue
parts stay clearly labelled as Purdue's, in their own member and their own instructions overlay.
A default install serves the same tools as 0.1.4.

## Acceptance criteria (the contract)

**Names**

- **R1** — The core distribution SHALL be named `cluster-mcp`, its code SHALL import as
  `cluster_mcp.core`, and it SHALL install a `cluster-mcp` console script. `cluster_mcp` SHALL be a
  pure PEP 420 namespace: no built wheel of any workspace member contains `cluster_mcp/__init__.py`.
  `__version__` SHALL resolve from the installed `cluster-mcp` metadata, with no hardcoded version.
  The `python -m` invocation `AGENTS.md` documents SHALL run the same entry point under the new
  module path.
- **R2** — The server SHALL identify itself as `cluster-mcp`, not RCAC: in the server name its MCP
  server info carries, and in its `--version` and `--help` output.
- **R3** — WHEN the server is started through the `rcac-mcp` console script, it SHALL print a
  deprecation warning on stderr naming `cluster-mcp` and the window in R16, then behave exactly as
  `cluster-mcp` would with the same arguments, exit status included. Nothing it prints SHALL go to
  stdout, which carries the stdio transport.

**Environment**

- **R4** — Each of `RCAC_SSH_HOST`, `RCAC_USER_MAP` and `RCAC_INSTRUCTIONS_BUDGET` SHALL have a
  replacement: `CLUSTER_MCP_SSH_HOST`, `CLUSTER_MCP_USER_MAP` and `CLUSTER_MCP_INSTRUCTIONS_BUDGET`
  respectively, and the server SHALL read the replacement wherever it read the legacy name.
- **R5** — WHERE a legacy `RCAC_*` variable is set and its replacement is not, the server SHALL
  honour the legacy value and print a deprecation warning on stderr naming the replacement. WHERE
  both are set, the replacement SHALL take effect.
- **R6** — `bin/sandbox.sh` SHALL unset the legacy and the replacement names of both the SSH-host
  and the user-map variable. WHEN either SSH-host variable is exported in the calling shell, a bare
  `cluster-mcp` and a bare `rcac-mcp` run under the sandbox SHALL each still fail closed: a nonzero
  exit and the "SSH host required" message, which names the replacement variable.

**Protocol surface**

- **R7** — The server SHALL serve its context resource as `cluster://context` and its storage
  resource as `cluster://storage`. WHEN a client reads `rcac://context` or `rcac://storage` within
  the window, the server SHALL return the same content as its `cluster://` replacement. Each alias SHALL keep its target's executor
  handling in every execution mode (§8): the context resource runs nothing and stays open in
  `delegate` mode, and the storage resource runs on the request's executor.
- **R8** — A default install SHALL register the same tool names, argument schemas and annotations
  as 0.1.4. The served-surface fixture (`tests/fixtures/served_surface.json`) SHALL change only by
  deltas listed in the commit body and in § Testing: the instructions, the resource URIs, and the
  server name.

**Workspace**

- **R9** — The repository SHALL be a uv workspace with the core member at `packages/cluster-mcp`
  and a Slurm member and an RCAC member contributing `cluster_mcp.slurm` and `cluster_mcp.rcac`. The
  Purdue-specific tools SHALL live in the RCAC member, under their current names.
- **R10** — WHEN `packages/cluster-mcp` is installed with the git `#subdirectory=` form from a
  commit of this repository, uv SHALL build the Slurm and RCAC members from that same commit, and
  `cluster-mcp --help` SHALL run under `bin/sandbox.sh`. Until the GitHub rename the probe runs
  against a local clone; the release's `post_verify` runs it against `PurdueRCAC/cluster-mcp`.

**Instructions**

- **R11** — The generic core of the served instructions SHALL contain neither "RCAC" nor "Purdue",
  and SHALL name no tool the RCAC member provides.
- **R12** — The served instructions of a default install SHALL name every tool that registers. The
  RCAC member's tools SHALL be listed in a site overlay labelled as RCAC-specific. Core plus overlay
  SHALL form the uncut base (§9), with the site context after it within the instructions budget, as
  today.

**Repository text**

- **R13** — Every repository URL the tree carries, outside the point-in-time records in `spec/`,
  SHALL name `PurdueRCAC/cluster-mcp`: the README, `__website__` or its successor, the release
  recipe's `post_verify` and caveats, and the compose and container docs.
- **R14** — Every `SPDX-FileCopyrightText` header line SHALL read exactly
  `SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors`. Every `SPDX-License-Identifier` line
  SHALL be unchanged.
- **R15** — `AGENTS.md`, `README.md`, `SECURITY.md`, `INSTRUCTIONS.md`, `compose.yml`, the
  `Dockerfile` and `.github/workflows/ci.yml` SHALL use the new names in the same commit as the code
  they describe. That includes the profile's `verify`, `coupled core` and `throwaway environment`;
  the release recipe's version source, bump files, diff rule, gate, tag message and `post_verify`;
  and the high-blast-radius list, which gains each moved file's new home and keeps the old entry
  (§ Invariants). The release recipe's gate SHALL pass on the cycle's head.
- **R16** — `README.md` SHALL state, in one place, the three deprecations (the `rcac-mcp` command,
  the `RCAC_*` variables, the `rcac://` URIs), each one's replacement, and the window: deprecated in
  0.2.0, removed no earlier than 0.4.0. The R3 and R5 warnings SHALL name the same window.

## Non-goals (no-gos)

- **The GitHub repository rename itself.** A separate, human-approved action at the 0.2.0 release;
  this cycle only moves the URLs the tree carries (R13).
- **PyPI.** Registering or uploading any distribution; installs stay git-based.
- **Capability extras.** Making the Slurm or RCAC member optional, entry-point registration, runtime
  probes, composing instructions from what loaded: `capability-extras`. In this cycle a default
  install still carries every member, so nothing changes for a user (R8).
- **More members.** LMOD and xdu members are later cycles.
- **Renaming, consolidating or re-scoping any tool.** `myquota`, `jobinfo`, `slist` and the rest
  keep their names (`tool-surface`, `slurm-capability`, `site-extras`).
- **The Purdue overlay as a documented pattern for other sites.** This cycle splits the text;
  `site-extras` finishes the overlay and documents it.
- **Removing the legacy names.** The `rcac-mcp` script, the `RCAC_*` variables and the `rcac://`
  aliases are removed in a later cycle, after the window.
- **Rewriting history.** The retained `spec/` records and seed prose that quote the old names
  stay as written.
- **The license.** `SPDX-License-Identifier: MIT` is unchanged.
- **The RCAC-Docs `mcp_servers.md` page.** A separate repository with its own harness.
- **A neutral GitHub org.** The repository stays under `PurdueRCAC`.

## Clarifications

- **Q:** Is the GitHub repository rename in scope, and what is the new location? — **A:** The repo is
  renamed in place to `PurdueRCAC/cluster-mcp` at the 0.2.0 release, relying on GitHub's redirect.
  The rename itself is a separate human-approved action at release time, not a cycle deliverable;
  the cycle moves every URL the repo carries (README, the recipe's `post_verify`, caveats,
  compose/docs) to the new name (Geoffrey, resolved 2026-10-29).
- **Q:** Does 0.2.0 register on PyPI? — **A:** No. Installs stay git-based with the
  `#subdirectory=` form; PyPI registration is a non-goal (Geoffrey, resolved 2026-10-29).
- **Q:** What happens to the `rcac-mcp` command? — **A:** It stays as a second entry point that
  prints a deprecation warning naming `cluster-mcp` and then runs it, through a stated deprecation
  window, matching the treatment of `RCAC_*` environment variables (honoured with a warning when the
  counterpart is unset) and `rcac://` URIs (aliased) (Geoffrey, resolved 2026-10-29).
- **Q:** What does the SPDX copyright header become? — **A:** Every SPDX copyright header becomes
  `SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors`, replacing `2025 Purdue University`
  and any other year variant. The license identifier is unchanged (Geoffrey, resolved 2026-10-29).
- **Q:** Where does this cycle sit? — **A:** Part 0 shipped as 0.1.3 and 0.1.4; Part I ships as
  0.2.0; this cycle precedes `capability-extras`, so the extras are named once (settled roadmap,
  restated 2026-10-29).
- **Q:** The contract is 16 R-IDs across three deliverables (rename, uv-workspace restructure,
  instructions core/site-overlay split), past the size circuit-breaker. Split it? — **A:** No; the
  pilot + follow-ups split was offered and declined. All three stay in this cycle, as the roadmap
  planned: every import moves once; the instructions split is now small (`agents-d-instructions`
  already moved the site's quota and path facts into the site context, leaving only the tool list);
  and it pairs with moving the RCAC tools into their own member (Geoffrey, resolved 2026-10-29).
- **Q:** What do the `RCAC_*` variables become? — **A:** The `CLUSTER_MCP_*` prefix:
  `CLUSTER_MCP_SSH_HOST`, `CLUSTER_MCP_USER_MAP`, `CLUSTER_MCP_INSTRUCTIONS_BUDGET`, matching the
  existing `CLUSTER_MCP_REPO` / `CLUSTER_MCP_SANDBOX` / `CLUSTER_MCP_TEST_ERA` and staying clear of
  site variables such as `$CLUSTER_SCRATCH` (Geoffrey, resolved 2026-10-29).
- **Q:** Does the storage resource move too, or keep a site-flavoured `rcac://` name? — **A:** It
  moves to `cluster://storage`, with `rcac://storage` aliased through the window and keeping its
  executor handling (Geoffrey, resolved 2026-10-29).
- **Q:** How long is the deprecation window? — **A:** Deprecated in 0.2.0, removed no earlier than
  0.4.0; the warnings and the README name it (Geoffrey, resolved 2026-10-29).
- **Q:** What does the release need from this cycle's URL move? — **A:** Nothing beyond R13, but an
  ordering constraint for the release: R13 points `post_verify` and the install docs at
  `PurdueRCAC/cluster-mcp`, which does not exist until the repository rename. At 0.2.0 the rename
  must happen before `post_verify` runs, and any release cut from `develop` between this cycle's
  landing and the rename would fail its `post_verify` (noted for the release, not a requirement;
  2026-10-29).

## Related materials

- Seed: `issues/rename-to-cluster-mcp.md`
- Roadmap: `ROADMAP.md` § *Nothing here should assume Purdue*
- Neighbouring seeds (boundaries only): `issues/capability-extras.md`, `issues/site-extras.md`
- `AGENTS.md` § Direction, § Configuration, § Packaging, § Factory (Profile, Release recipe,
  Throwaway environment), § Invariants (high-blast-radius list, §8 resources, §9 agent-facing
  surface), § Conventions
- Source anchors: `pyproject.toml:2,18,25`; `src/rcac_mcp/__init__.py:33-34,62`;
  `src/rcac_mcp/server.py:66-104,127`; `src/rcac_mcp/resources.py:47,91`; `bin/sandbox.sh:68`;
  `Dockerfile:16`; `compose.yml:17`; `.github/workflows/ci.yml:44`;
  `tests/fixtures/served_surface.json`
