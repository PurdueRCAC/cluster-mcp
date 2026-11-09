---
status: unshaped
kind: feature
appetite: big
lane: public
---

# The xdu index behind `[files-xdu]`: detect, keep, build, query

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

*Re-scoped 2026-11-09.* Absorbed by `issues/files-xdu-extra.md`, which serves the file family from
this index under the `[files-xdu]` extra. This seed keeps the xdu evidence and the index's
mechanics. Two things changed: the member uses the system xdu and never installs it (installing
anything into a user's home is ruled out), and a space's quota is a site interface's answer
(`issues/site-interfaces.md`), not this index's.

## Why it was deferred

Not deferred — a roadmap cycle in Part II (0.3.0), absorbed by `issues/files-xdu-extra.md`. It
implements [`files-extra.md`](files-extra.md)'s family a second way, and it indexes large trees
through [`jobs-interface.md`](jobs-interface.md), so it comes after both.

**Pre-existing:** n/a — new work.

## Outcome / vision

The index behind `cluster-mcp[files-xdu]`, which `[rcac]` pulls in.

- **Detect.** Look for `xdu` and `xdu-find` on the remote `PATH`. Where they're missing, the tools
  say so; nothing offers an install.
- **Index where the data is cheap to keep.** Indexes go in the user's scratch, not home: an index
  can be hundreds of megabytes against a small home quota. Scratch purges take the index with them,
  which is fine for a cache, so the tools report each index's age.
- **Index politely.** Small trees (home, a single project directory) on the login node at low
  priority with few threads; large trees (scratch, project spaces) as a batch job through the jobs
  interface, within limits the site sets.
- **Operations,** as first sketched (names follow the file family's):
  - an index operation (`space | path`, `refresh`) and each index's status and age;
  - find — answered from the index when one covers the path, otherwise a bounded `find` with a note
    suggesting an index;
  - usage (`path`, `by=dir|owner`, `top`) — byte sums; until xdu has rollups, it falls back to a
    bounded `du` on single directories.
- **Typed operations only.** The tools expose fixed, typed queries and never pass caller-written SQL
  to the index — xdu's own guidance for serving an index to others.

**Byte-sum rollups are an upstream request.** Usage needs totals by prefix or owner, which
`xdu-find` lacks; that is a typed operation in xdu's own vocabulary, filed as a seed in the xdu
repository when this cycle is shaped.

## Sketch of the acceptance criteria

- **R1** — WHERE `[files-xdu]` is installed, the server SHALL detect `xdu` and `xdu-find` on the
  remote host and report their presence and version.
- **R2** — IF `xdu` is absent, THEN no tool SHALL install it, and the index-backed answers SHALL say
  it is absent.
- **R3** — Indexing SHALL write indexes under the user's scratch, never under home, and SHALL
  submit indexing of a tree above a documented size as a batch job through the jobs interface.
- **R4** — WHEN an index covers the requested path, find SHALL answer from it and SHALL report the
  index's age; otherwise it SHALL run a bounded `find` and say so.
- **R5** — No tool SHALL accept or forward SQL or any other query language from the caller.
- **R6** — Usage SHALL return totals by directory or owner, stating which source answered.

## Notes

- Where the index root lives is site knowledge. Until a site interface
  ([`site-interfaces.md`](site-interfaces.md)) supplies it, a generic default (a flag or environment
  variable naming the root) stands in.
- 2026-11-09: as first filed, this seed installed a pinned, checksum-verified release into a
  private prefix under `~/.local` with the user's consent, and reported quotas in a
  `storage_spaces` tool. Both are out: the system xdu only, and quotas through `site_quota`.
- `run_command`'s rails ([`shell-rails.md`](shell-rails.md), 0.4.0) steer `find` and `du` over
  parallel-filesystem roots toward these tools.
- xdu facts are from the public repository and its v0.5.2 release; the oldest system xdu the member
  supports is chosen at shaping.
- Related: [`files-xdu-extra.md`](files-xdu-extra.md) (absorbs this seed),
  [`spec/capability-extras/`](../spec/capability-extras/),
  [`tool-surface.md`](tool-surface.md), [`slurm-capability.md`](slurm-capability.md),
  [`site-extras.md`](site-extras.md),
  [`generalize-storage-discovery.md`](generalize-storage-discovery.md) (the storage-roles model
  an index's spaces are named in).
- Found by: roadmap revision, 2026-10-16 (out of cycle).
- 2026-11-01: [`spec/capability-probe/`](../spec/capability-probe/) serves an installed capability
  only where the cluster has the commands its `Capability.commands` declares. This capability should
  declare none: its tools are meant to work where `xdu` is missing (answering without the index and
  saying so), and a declared `xdu` would withhold exactly those tools there (`AGENTS.md`
  § Invariants §7). *Reworded 2026-11-09:* as first filed, the reason was the install offer.
