---
status: unshaped
kind: refactor
appetite: big
lane: public
---

# The core is the executor, the transports and the loader, and serves no tool family of its own

## Problem

Since `capability-extras` a bare `cluster-mcp` is "the core alone", but the core is still a server
with opinions about what an agent does: it registers `run_command`, `list_directory`, `read_file`,
`write_file`, `upload_file` and `download_file` beside `cluster_context`, and ships a site's favicon.
So a deployment that installs only the core still serves a shell and the whole file family, and every
capability extra is an addition to that surface rather than the thing that defines it. The tool
families this project is heading for (`[shell]`, `[files]`, the jobs and modules interfaces, a
site's own extra) have nowhere neutral to stand.

**Pre-existing:** the core has registered the shell and the file tools since the first release.

## Why it was deferred

Release 0.2.0 carries no capability reshaping, so every installed surface stays as it is until
0.3.0. This is the first cycle of 0.3.0: each family after it lands on what it leaves.

## Outcome / vision

The core distribution is the machinery every capability is built on, and nothing else:

- the executor and its modes (`ssh`, `local`, `delegate`), the transports and authentication;
- the capability loader and the probe (`AGENTS.md` § Invariants §7);
- the served instructions, composed from what loaded, with `/etc/agents.d` in them (§8);
- `cluster_context`, the one tool it keeps.

A bare install serves no command tool and no file tool. The shell and the file family move out with
`issues/shell-extra.md` and `issues/files-extra.md`, which are shaped with this cycle or right after
it. The `rcac-mcp` compat distribution keeps installing what today's users have.

## Sketch of the acceptance criteria

- **R1** — A bare installation of `cluster-mcp` SHALL register `cluster_context` and no other tool.
- **R2** — No tool that runs a command line or touches a file SHALL be registered by the core.
- **R3** — WHERE only the core is installed, the served instructions SHALL name no tool the server
  does not serve, and SHALL still carry the site context from `/etc/agents.d`.
- **R4** — The `rcac-mcp` compat distribution SHALL install a server that serves what the last
  0.2.x release served, under the aliases decision `issues/tool-surface.md` records.
- **R5** — The executor, the transports, the loader and the probe SHALL stay in the core, so a
  capability extra depends on the core alone.

## Notes

- Release 0.2.0 ships a bare install that serves the shell and the file tools (the README says so
  today); 0.3.0 narrows it. Planning decides how the 0.2.0 notes and the 0.3.0 notes announce that.
- The favicon leaves the core with the `[rcac]` cycle (`issues/site-extras.md`), which adds member
  routes; until then the core still serves it.
- Related: `issues/shell-extra.md`, `issues/files-extra.md`, `issues/tool-surface.md`,
  `spec/capability-extras/`, `spec/capability-probe/`.
- Found by: roadmap revision, 2026-11-09 (out of cycle).
