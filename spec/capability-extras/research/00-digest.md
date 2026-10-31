# 00 — Digest: the decisions the five briefs settle

Briefs: [01 entry points](01-entry-points.md) · [02 core-only testing](02-core-only-testing.md) ·
[03 surface and composition](03-surface-and-composition.md) · [04 startup and failure](04-startup-and-failure.md) ·
[05 packaging and extras](05-packaging-and-extras.md).

## Decisions

1. **Group and payload.** One entry-point group, `cluster_mcp.capabilities`. Each member declares one
   entry point, named for its package, at `cluster_mcp.<member>.capability:CAPABILITY`, a frozen
   `Capability(name, order, tools, instructions, resources=())` defined in a new core module
   `core/capabilities.py`. `tools` is the dotted name of the member's tools module (01 §3).
2. **When loading happens: at startup, never at import.** *Contradiction resolved.* 01 put the tools
   imports at the bottom of `core/tools/__init__.py` (import time, least churn); 03 and 04 showed
   that `import cluster_mcp.core` runs on `--help` and `--version`, so an import-time load turns R8's
   message into a traceback there (04 §1, confirmed). **Recommendation: 03/04.** `installed()`, a
   cached load, runs in `MCPServerApp.run()` after `--generate-token` and before the mode ladder,
   and in `create_mcp_server` when no capability set is passed. Nothing on the import chain of
   `cluster_mcp.core` imports a member. Tests get a full registry from `tests/conftest.py`
   calling `installed()` once at import (03 §1).
3. **Registration stays the decorator's append.** `@mcp_tool` is untouched (a GOAL non-goal keeps its
   `FunctionTool` behaviour; its append is kept too, for least churn, 01 §3). The loader imports a
   capability's `tools` module and attributes to it every registered tool defined in that module or
   below; a tool appended during the import that it cannot attribute fails the load. A failed load
   truncates `TOOL_REGISTRY` back to its length before the attempt (04 §3.4).
4. **Order is explicit.** Discovery order follows `sys.path` and directory listing (01 §2); a name
   sort puts `rcac` before `slurm` (01, 02, 03). The base is `CORE_INSTRUCTIONS`, then each loaded
   capability's text sorted by `(order, distribution name)`: Slurm 100, RCAC 900 ("a site overlay
   sorts last, directly above the site context"). Loading itself (and so which failure is reported
   first, and the listing order, decision 5) runs in `(distribution name, entry-point name)` order.
5. **Listing order is kept** (revised after the adversarial review read a changed order as a change
   to R6). FastMCP lists in insertion order (03 §2, verified). Today: shell, filesystem, transfer,
   RCAC, Slurm, `cluster_context`; resources `cluster://context`, `cluster://storage`,
   `rcac://context`, `rcac://storage`. The server reproduces both: the core's tools but the context
   module's, then each capability's in load order (distribution name: RCAC before Slurm), then
   `cluster_context`; every primary `cluster://` resource (core, then capabilities in load order),
   then every `rcac://` alias in the same order. The base keeps its own order key (Slurm's text
   before RCAC's). PLAN §2.3.
6. **R8 reporting reuses the SSH precedent** (04 §2): `CapabilityLoadError(RuntimeError)` from the
   loader, carrying the distribution, message `cannot load capability <dist>: <cause>` on one line;
   `run()` reports it through `_report_startup_failure` (stderr once; on stdio, the message as the
   error to every request until EOF) and raises `StartupFailure` (exit 5). A load failure is any
   `Exception` from `ep.load()` or the tools import, a payload that is not a `Capability`, a tool
   name, resource URI or capability name already taken, or a capability resource not marked
   `executor: True`.
7. **Resources (R7).** The alias derivation becomes one core helper, `legacy_aliases(entries)`, used
   by the core for its context entry and by the RCAC capability for its storage entry; a future
   capability gets no `rcac://` URI unless it asks. `RESOURCE_REGISTRY` and `OPEN_RESOURCES` become
   the core's alone (the open set is unchanged), so `middleware.py` is untouched: a capability
   resource is never open, and the loader refuses one that claims to be (03 §4, fail-closed).
8. **No `SERVER_INSTRUCTIONS` constant.** It becomes `base_instructions(capabilities)`; the seven test
   files that import the constant are edited. 03's PEP 562 lazy attribute is rejected: an attribute
   read that loads distributions is a hidden side effect.
9. **The test seam.** `create_mcp_server(..., capabilities=None)` takes a set of loaded
   capabilities; `None` means `installed()`. No CLI flag or environment variable reaches it (the
   GOAL's no-switch non-goal) (02 §2).
10. **Packaging (05).** Core: members move to `[project.optional-dependencies]` `slurm`/`rcac`, the
    workspace sources kept. Root: `dependencies = ["cluster-mcp[slurm,rcac]"]`, which also keeps
    `uv sync` (the profile's `setup`, CI, the Dockerfile) installing every member. No RCAC → Slurm
    dependency (01 §4: no Python coupling; the bundle alias is `site-extras`'). `uv lock` in the same
    commit.
11. **Testing (02).** Two layers: in-process composition from explicit capability sets (`unit`, both
    eras), and a real core-only environment (`uv sync --package cluster-mcp --no-dev --frozen
    --offline` into `UV_PROJECT_ENVIRONMENT`, editable, under the sandbox) driven over stdio
    (`integration`). Broken capabilities are planted dist-infos prepended to `PYTHONPATH`, or
    `Distribution.at(path).entry_points` in process. New drives set `FASTMCP_CHECK_FOR_UPDATES=off`;
    the suite-wide fix is the existing seed `issues/fastmcp-update-check.md`.

## Residual gap (not deferred: an accepted property)

A capability distribution installed without an entry point in the group (a member wheel from
before this cycle beside a newer core) is silently absent: there is nothing to fail on (04 §3). The
supported installs build every member from one commit, and the suite's
`test_installed_finds_every_workspace_member` catches the development form of it (an editable
install not re-synced after the entry points were added, 03 §1).
