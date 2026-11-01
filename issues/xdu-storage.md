---
status: unshaped
kind: feature
appetite: big
lane: public
---

# Answer storage questions from an xdu index instead of walking the filesystem

## Problem

"Where are my large files", "what's filling my scratch", "find every `*.h5` under this project" are
among the first questions an agent asks on a cluster, and this server has no answer to them but
`run_command("find …")` or `du`. On a parallel filesystem that is the wrong tool twice over: a
recursive walk of a scratch or project space with millions of files is slow, and it is exactly the
long, multi-threaded metadata load that login-node rules forbid. The site's own `/etc/agents.d`
text says so; the agent reads it, or doesn't, and walks anyway.

[xdu](https://github.com/xdu-project/xdu) is the fitting tool. `xdu DIR -o OUTDIR` indexes a tree
into Parquet, partitioned by top-level subdirectory, with `.xdu-complete` marking a clean run; about
100M files take 20–30 minutes on a parallel filesystem. `xdu-find -i IDX` queries the index through
embedded DuckDB — glob or regex, size, access and modification age, owner, group, mode; path-,
size- or atime-sorted; CSV or JSON; with a limit and a count. Two gaps matter here: indexing has
threads (`-j`, default 4) but no I/O throttle, and the query side has **no byte-sum rollup** — no
`du`-style total by prefix or owner.

xdu may or may not be installed on a given cluster. Releases ship as tarballs for x86_64 and
aarch64 (glibc 2.28+), 35–46 MB with DuckDB bundled, with one `SHA256SUMS`.

## Why it was deferred

Not deferred — a roadmap cycle in Part I. It is a capability distribution
([`spec/capability-extras/`](../spec/capability-extras/)), it routes
[`tool-surface.md`](tool-surface.md)'s `file_find`, and it indexes large trees through
[`slurm-capability.md`](slurm-capability.md)'s `job_submit`, so it comes after all three.

**Pre-existing:** n/a — new work.

## Outcome / vision

`cluster-mcp[xdu]`, pulled in by a site extra where the site wants it.

- **Detect.** Look for `xdu` and `xdu-find` on the remote `PATH`. Where they're missing, the tools
  say so and offer the install.
- **Install only with explicit consent.** `storage_index(..., install=True)` downloads a pinned
  release, verifies it against `SHA256SUMS`, and unpacks it into a private prefix under `~/.local`
  (for example `~/.local/share/cluster-mcp/xdu/<version>/`) — no `curl | sh`, nothing in a user's
  home unasked, and nothing that shadows a system install. Where the client supports MCP
  elicitation, the consent can be a real question to the person.
- **Index where the data is cheap to keep.** Indexes go in the user's scratch, not home: an index
  can be hundreds of megabytes against a small home quota. Scratch purges take the index with them,
  which is fine for a cache, so the tools report each index's age.
- **Index politely.** Small trees (home, a single project directory) on the login node at low
  priority with few threads; large trees (scratch, project spaces) as a batch job through the
  scheduler, within limits the site sets.
- **Tools:**
  - `storage_spaces()` — the user's spaces, their quotas and each one's index status;
  - `storage_index(space | path, refresh, install)`;
  - `file_find(...)` — answered from the index when one covers the path, otherwise a bounded `find`
    with a note suggesting an index;
  - `storage_usage(path, by=dir|owner, top)` — byte sums; until xdu has rollups, it falls back to
    the site's quota command and bounded `du` on single directories.
- **Typed operations only.** The tools expose fixed, typed queries and never pass caller-written SQL
  to the index — xdu's own guidance for serving an index to others.

**Byte-sum rollups are an upstream request.** `storage_usage` needs totals by prefix or owner, which
`xdu-find` lacks; that is a typed operation in xdu's own vocabulary, filed as a seed in the xdu
repository when this cycle is shaped.

## Sketch of the acceptance criteria

- **R1** — WHERE the `xdu` capability is installed, the server SHALL detect `xdu` and `xdu-find` on
  the remote host and report their presence and version in `storage_spaces`.
- **R2** — IF `xdu` is absent, THEN no tool SHALL install it unless the call sets `install=True`;
  WHEN it does, the server SHALL install the pinned release only after its checksum verifies, into a
  private prefix under `~/.local`.
- **R3** — `storage_index` SHALL write indexes under the user's scratch, never under home, and SHALL
  submit indexing of a tree above a documented size as a batch job.
- **R4** — WHEN an index covers the requested path, `file_find` SHALL answer from it and SHALL report
  the index's age; otherwise it SHALL run a bounded `find` and say so.
- **R5** — No tool SHALL accept or forward SQL or any other query language from the caller.
- **R6** — `storage_usage` SHALL return totals by directory or owner, stating which source answered.

## Notes

- Where the index root lives is site knowledge. Until [`site-extras.md`](site-extras.md) gives sites
  a hook, a generic default (a flag or environment variable naming the root) stands in.
- `run_command`'s guard rails ([`tool-surface.md`](tool-surface.md)) steer `find` and `du` over
  parallel-filesystem roots toward these tools.
- xdu facts are from the public repository and its v0.5.2 release; the pinned version is chosen at
  shaping.
- Related: [`spec/capability-extras/`](../spec/capability-extras/),
  [`tool-surface.md`](tool-surface.md), [`slurm-capability.md`](slurm-capability.md),
  [`site-extras.md`](site-extras.md),
  [`generalize-storage-discovery.md`](generalize-storage-discovery.md) (the storage-roles model
  `storage_spaces` reports in).
- Found by: roadmap revision, 2026-10-16 (out of cycle).
