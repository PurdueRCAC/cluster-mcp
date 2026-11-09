---
status: unshaped
kind: feature
appetite: big
lane: public
---

# Every tool family follows one set of rules: names, annotations, budgets, a read-only profile

## Problem

The server's tools are not honest about what they do, and nothing sets the rules a new family must
follow, so each capability would invent its own.

- **No tool carries annotations.** `readOnlyHint`, `destructiveHint` and `idempotentHint` are absent
  everywhere, so a client can't tell `read_file` from `write_file` from `run_command` without
  reading prose. Clients that match permissions by tool name (Claude Code allow-lists
  `mcp__<server>__<tool>`, with globs after the prefix) can pre-approve a read-only family only if
  its names let a pattern select it.
- **No response budgets.** Tools return whatever the command printed. Clients enforce their own
  limits — Claude Code warns at 10K tokens of output, stops at 25K by default and keeps only the
  ends of a long error — so an unbounded listing is truncated by the client, not by the tool that
  knows how to page it.
- **No profile narrows what is served.** A deployment that wants only the read-only tools has no
  way to say so.
- **Context cost is measured, not guessed.** Today 25 tools carry about 25.6K characters of
  definitions (about 6.4K tokens) on every turn; `sbatch` alone is 2.9K.

*Re-scoped 2026-11-09.* This seed first held the file family and `run_command`'s steering too. The
file family moved to `issues/files-extra.md` (0.3.0), and the steering to `issues/shell-rails.md`
(0.4.0). What stays here is the rules, which the `[shell]` and `[files]` cycles apply first and
every later family follows.

## Why it was deferred

Not deferred — a roadmap cycle in Part II (0.3.0). It renames tools, so it comes after the rename
([`spec/rename-to-cluster-mcp/`](../spec/rename-to-cluster-mcp/), landed 2026-10-30) and
`capability-extras` ([`spec/capability-extras/`](../spec/capability-extras/), landed 2026-11-01;
every import and registration moves once), and it is built on the argv executor from
[`spec/safe-execution/`](../spec/safe-execution/).

**Pre-existing:** the missing annotations and budgets are on `main`.

## Outcome / vision

**Bespoke first, shell last.** A bespoke tool earns its place by doing something the shell can't:
**exactness** (byte-exact writes, structured results, one interpreter's semantics), **politeness**
(a site's rules live in the tool rather than in prose the model may skip), or **permission
granularity** (a tool whose behaviour is fixed can carry an honest `readOnlyHint`; `run_command`
can't). Every family 0.3.0 builds follows the same rules:

- **Names a client can allow-list by pattern**, so a read-only family can be pre-approved with one
  glob.
- **Honest annotations** on every tool; `run_command` never carries `readOnlyHint`.
- **Response budgets** below common client limits, each saying when it truncated and how to get the
  rest.
- **`--profile read-only`** registers only tools with `readOnlyHint`, for deployments that want one.
  Dropping the shell alone constrains nothing while file writes and job submission remain.

The rules are recorded where they bind (`AGENTS.md` § Invariants §9, beside the served surface) by
the first cycle that applies them, so each later family is graded against them.

Open questions for shaping:

1. **Aliases or a clean break.** Tool names are part of the agent-facing API (`AGENTS.md`
   § Invariants §9). Keep `list_directory`, `read_file`, `write_file` and the Slurm and RCAC names
   as aliases through a deprecation window, or break cleanly in 0.3.0? This one is the
   maintainer's.
2. **Names a client can select by pattern.** Resource-first names (`file_read`, `file_write`) read
   well, but a glob can't separate readers from writers. Is a naming scheme that lets a client
   allow-list the read-only family by pattern worth the cost in readability?
3. **Tool search.** FastMCP 4's server-side tool search, evaluated against clients' own.

## Sketch of the acceptance criteria

- **R1** — Every tool SHALL carry MCP annotations that match its behaviour; `run_command` SHALL NOT
  carry `readOnlyHint`.
- **R2** — WHEN a result would exceed the tool's documented budget, the tool SHALL truncate it, set a
  truncation flag and say how to page.
- **R3** — WHERE `--profile read-only` is set, only tools with `readOnlyHint` SHALL register.
- **R4** — The read-only tools of each family SHALL be selectable by one name pattern, if shaping
  keeps that rule.
- **R5** — The total size of tool definitions SHALL be measured in a test and reported against the
  6.4K-token baseline.

## Notes

- Related: [`files-extra.md`](files-extra.md) and [`shell-extra.md`](shell-extra.md) (the first
  families that apply the rules), [`shell-rails.md`](shell-rails.md) (the steering, moved),
  [`jobs-interface.md`](jobs-interface.md), [`modules-interface.md`](modules-interface.md) and
  [`site-interfaces.md`](site-interfaces.md) (later families), [`spec/safe-execution/`](../spec/safe-execution/)
  (the executor this builds on), [`spec/stack-upgrade/`](../spec/stack-upgrade/) (annotations and
  `_meta` on the current API).
- Found by: roadmap revision, 2026-10-16 (out of cycle).
- 2026-10-16: the docs strip removed `doc_search` and `doc_load`, so 23 tools remain. A JSON count of
  each served tool's MCP definition gives 26.5K characters for the 25 tools before and 23.5K for the
  23 after (the two were about 3.0K), so the 25.6K-character, 6.4K-token baseline above is about 11%
  high: re-measure it before R5 reports against it.
- 2026-10-23: `safe-execution` gave `write_file` a `base64` encoding for binary content and left
  the matching binary read to this family (its GOAL non-goals); that is now `files-extra.md`'s.
- 2026-11-04: whether a server offers `run_command` at all becomes the deployment's choice, made at
  installation through a `[shell]` extra ([`shell-extra.md`](shell-extra.md)). Leaving the shell out
  is not containment; it is a real choice of scope for an operator serving other users.
