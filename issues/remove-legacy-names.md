---
status: unshaped
kind: refactor
appetite: small
lane: public
---

# Remove the names the rename kept through its deprecation window

## Problem

`rename-to-cluster-mcp` ([`spec/rename-to-cluster-mcp/`](../spec/rename-to-cluster-mcp/)) renamed
the server without breaking anyone: every old name keeps working through a window the README states
as deprecated in 0.2.0, removed no earlier than 0.4.0 (`WINDOW` in `core/deprecation.py`).

- **The `rcac-mcp` command** (`legacy_main`) and the root compat distribution `rcac-mcp`, which
  installs `cluster-mcp` so the install line in every existing client config keeps resolving.
- **The `RCAC_*` variables**: `RCAC_SSH_HOST`, `RCAC_USER_MAP` and `RCAC_INSTRUCTIONS_BUDGET`, each
  honoured in place of its `CLUSTER_MCP_*` name with a warning (`LEGACY_ENV`).
- **The `rcac://` resource URIs**: every `cluster://` resource is also served under its old URI, with
  no warning of its own.

Each is a compatibility path the code, the tests and `AGENTS.md` all carry until it goes.

## Why it was deferred

A non-goal of the rename: the window has to open, in 0.2.0, before it can close.

**Pre-existing:** n/a — scheduled removal, not a defect.

## Outcome / vision

At a release no earlier than 0.4.0, the old names stop working, and the release notes say so: what
was removed, and the one line to change in a client config for each.

## Sketch of the acceptance criteria

- **R1** — The `rcac-mcp` command, the `RCAC_*` variables and the `rcac://` aliases SHALL be removed,
  with the README's upgrading section rewritten to describe a completed migration.
- **R2** — `bin/sandbox.sh` SHALL still make a bare `cluster-mcp` fail closed.
- **R3** — The release that carries the removal SHALL be 0.4.0 or later, and its notes SHALL name each
  removed name and its replacement.

## Notes

- Whether the `rcac-mcp` compat distribution also goes, or stays as an empty pointer at
  `cluster-mcp`, is the promotion conversation's call; removing it breaks the install line in every
  config that was never updated.
- The repository was renamed to `PurdueRCAC/cluster-mcp` on 2026-10-31. Its redirect from the old
  name is GitHub's to keep, not this cycle's: removing the names above does not remove it.
- Found by: `rename-to-cluster-mcp` GOAL non-goals, carried at retirement, 2026-10-30.
