---
status: unshaped
kind: feature
appetite: big
lane: public
---

# Introduce site extras, starting with cluster-mcp[rcac]

## Problem

A user at Purdue should be able to install one thing — `cluster-mcp[rcac]` — and get the right
capability extras plus Purdue's own tools and context, without first knowing that Gautschi runs Slurm
and LMOD. That is the second half of the packaging direction in `AGENTS.md`, and it is what makes
`cluster-mcp[alcf]`, `[ncsa]` and `[tacc]` a matter of contribution rather than redesign.

A site extra is two things at once, and conflating them is the trap:

1. **A dependency alias** — `rcac = ["cluster-mcp[slurm]", "cluster-mcp[lmod]"]`. Cheap, mechanical.
2. **A point of view** — the site's own tools and the site's own agent-facing context. Today that is
   the `cluster-mcp-rcac` member's `rcac/tools.py` (`myquota`, `storage_paths`, `jobinfo`, `jobcmd`,
   `jobenv`, `jobscript`, `showpartitions`, `average_wait`, `slist`, `sfeatures`) and its
   `RCAC_INSTRUCTIONS` — the 25GB home quota, `/depot/<group>`, `$CLUSTER_SCRATCH`, `findscratch`.

The rename ([`spec/rename-to-cluster-mcp/`](../spec/rename-to-cluster-mcp/)) drew the first
boundary: `slist` and `sfeatures` left the Slurm member for the RCAC one, and the instructions
became `CORE_INSTRUCTIONS`, `SLURM_INSTRUCTIONS` and `RCAC_INSTRUCTIONS`. `capability-extras`
([`spec/capability-extras/`](../spec/capability-extras/)) made the RCAC member an optional `[rcac]`
extra that registers its tools, its instructions and its storage resource through the entry-point
group, so the core no longer imports it. What is left is the contract: the bundle alias, what a
*contributor* writes to add a site, and how packaged site context composes with `/etc/agents.d`.

## Why it was deferred

Not deferred — sequenced after `capability-extras`
([`spec/capability-extras/`](../spec/capability-extras/), landed 2026-11-01), whose mechanism it
consumes. Filed separately because the interesting work here is the **contribution boundary**, not the
Purdue code: what exactly does a new center have to write, and where does it put it?

**Pre-existing:** n/a — new work.

## Outcome / vision

`cluster-mcp[rcac]` installs cleanly and behaves exactly as the server does today for a Purdue user.
More importantly, the repository documents a site-extra contract concrete enough that someone at TACC
can add `cluster-mcp[tacc]` by writing one module and one context file, without touching the core —
and the review for that contribution has something to grade against.

The `/etc/agents.d/*.md` convention is the other half of this story and is deliberately *not* being
replaced. Static, packaged site context (what ships in the extra) and dynamic, admin-supplied cluster
context (what the resource loads at runtime) answer different questions and should stay distinct; the
plan should say plainly how they compose, because a contributor will ask.

## Sketch of the acceptance criteria

- **R1** — `pyproject.toml` SHALL define an `rcac` extra that pulls the capability extras Purdue needs;
  `cluster-mcp[rcac]` SHALL register the Purdue tool group in addition to those capabilities.
- **R2** — WHERE the `rcac` extra is not installed, no Purdue-specific tool SHALL appear in
  `TOOL_REGISTRY` and no Purdue-specific path, quota figure, or command name SHALL appear in
  `SERVER_INSTRUCTIONS`.
- **R3** — `slist` and `sfeatures` SHALL move out of the generic Slurm group into the site group.
- **R4** — Site context SHALL be contributed as data alongside the site's tools, not by editing a core
  constant.
- **R5** — The repository SHALL document what a new site extra must provide, in enough detail that a
  contributor adding one touches no core module.
- **R6** — The composition of packaged site context with runtime `/etc/agents.d/*.md` context SHALL be
  documented and SHALL be deterministic.

## Notes

- Naming: an extra called `rcac` inside a distribution called `cluster-mcp` is the intended shape.
  Whether the *module* keeps `rcac` or becomes `sites/rcac.py` is a plan-level call.
- Related: [`spec/capability-extras/`](../spec/capability-extras/) (strict prerequisite, landed),
  [`lmod-tool-group.md`](lmod-tool-group.md) (pulled in by the site extra),
  [`generalize-storage-discovery.md`](generalize-storage-discovery.md) (the site hook this establishes
  is where a discovery implementation lands).
- Found by: the harness port, 2026-08-26 (out of cycle).
- 2026-10-16: absorbs [`generalize-storage-discovery.md`](generalize-storage-discovery.md). With
  capabilities as separate distributions ([`spec/capability-extras/`](../spec/capability-extras/),
  GOAL Clarifications), the `rcac` alias lists distribution names (`cluster-mcp-slurm`, …) rather
  than the self-referencing extras sketched in the Problem above.
- 2026-10-30: the rename moved `slist` and `sfeatures` into the RCAC member, so R3 is met on
  `develop`; R2 and R4 stand, since the core still imports and joins every member's instructions.
- 2026-11-01: `capability-extras` meets R2 and R4 on `develop`. Without the RCAC member no Purdue
  tool registers, and the served instructions are composed from the core and Slurm texts, which name
  no Purdue path, quota figure or command (R2). The member declares `RCAC_INSTRUCTIONS` on its own
  capability record beside its tools, and no core constant holds it (R4). R1 is half met: the `rcac`
  extra exists but installs only the RCAC member, so the bundle alias stands, with R5 and R6.
