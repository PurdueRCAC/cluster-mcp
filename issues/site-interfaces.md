---
status: unshaped
kind: feature
appetite: big
lane: public
---

# Site interfaces: abstract tools a center implements in its own extra

## Problem

Some questions every cluster user asks have a site-specific answer: how much storage is left, and
how much allocation is left to spend. Today the only answers are Purdue's commands wrapped as Purdue
tools (`myquota`, `slist` and the storage discovery in the RCAC member), so an agent on another
center's cluster has no tool at all, and an agent that learns Purdue's tools learns nothing that
carries over. `issues/generalize-storage-discovery.md` (absorbed here) has the evidence for storage:
a parser written against one site's column layout, a data model with one site's vocabulary in it,
and no honest "unknown".

A site also has tools of its own that only make sense beside its `/etc/agents.d` text, and no
contract says how a center adds one.

## Why it was deferred

It is capability reshaping, so it is a 0.3.0 cycle; `[rcac]` (`issues/site-extras.md`) is its first
implementation and follows it. **Pre-existing:** the Purdue-only storage assumptions are on
`develop`; the interfaces are new work.

## Outcome / vision

The core, or a small member, defines abstract site tools that a center implements in its own extra,
starting with two:

- **storage quota** — the user's storage spaces by role (home, scratch, project, archive), each with
  its usage and limit, and "unknown" as an honest value;
- **allocation balance** — the user's accounts and what each has left.

Working names are `site_quota` and `site_balance`, open to better ones; planning proposes the
starting surface and the names. `[rcac]` implements them over `myquota` and `mybalance`.

A site can also add **custom tools** that work with its `/etc/agents.d` text: the contract says how a
site's extra registers them, how their instructions compose with the site context, and what review
grades them against.

Each interface is written so a second implementation (another center's extra) is a contribution,
not a redesign. This project documents the pattern for other centers and does not build their
extras.

## Sketch of the acceptance criteria

- **R1** — The site interfaces SHALL be defined in one place a site extra implements, naming each
  tool, its parameters and its result shape.
- **R2** — WHERE no site implementation is installed, no site interface tool SHALL be served, and
  the served instructions SHALL name none.
- **R3** — The storage result SHALL express storage roles rather than one site's vocabulary, and
  SHALL represent an unknown quota distinctly from a zero one.
- **R4** — IF a site's command is absent or fails, THEN the tool SHALL say the site does not expose
  the information, naming the command it tried, never a raw parse error.
- **R5** — The docs SHALL describe what a center writes to implement the interfaces and add custom
  tools, in enough detail that it touches no core module.

## Notes

- Open for shaping: the names; whether the interfaces live in the core or in a member of their own;
  whether `cluster://storage` becomes the storage interface's resource; which other interfaces are
  worth starting with.
- Related: `issues/generalize-storage-discovery.md` (absorbed), `issues/site-extras.md` (`[rcac]`,
  the first implementation), `issues/jobs-interface.md` and `issues/modules-interface.md` (the same
  pattern), `AGENTS.md` § Invariants §8 (`/etc/agents.d`).
- Found by: roadmap revision, 2026-11-09 (out of cycle).
