---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A version the lock lifts never reaches a user who installs from git

## Problem

`uv.lock` pins what `uv sync` installs: the development environment and CI (`uv sync --locked`).
Nothing a user runs reads it. A `git+https://…` install, a `uvx --from 'cluster-mcp[…] @ git+…'`
install (the README's Quick Start) and the container image (`uv pip install --system -e .` in the
`Dockerfile`) each resolve the dependency tree fresh, within the ranges the four `pyproject.toml`
files declare, and take whatever the resolver finds: the newest release on the index, or the newest
in a warm cache.

So a fix that only lifts a locked version (a `uv lock --upgrade-package`, say, because a newer
release of a dependency matters) changes what the tests and CI run and nothing a user receives. A
user's install may already have the newer version, or may resolve an older one the declared range
still admits, and nothing in the repository says which. Where the lifted version matters, only a
floor in the declared requirement carries it to users. The release gate's lock audit
(`bin/audit_lock.py`) audits the tree the lock resolves, so it says nothing about that one either.

**Observed instance.** `capability-extras` P4's install probe installed the compat root with
`uv pip install` from a throwaway git snapshot, offline: it resolved a newer pydantic from the cache
than the one `uv.lock` pins, and the served tools' output schemas gained a `description` field. The
cycle's own change was not the cause (the base commit's install line, resolved the same way, showed
the same field); the probe now compares within one resolution mode.

## Why it was deferred

Outside the `capability-extras` GOAL, which changes how capabilities install, not how dependencies
resolve. **Pre-existing:** present on `develop` before that cycle, for every install line the README
has documented.

## Outcome / vision

A version the project needs a user to have is required by a declared floor, not only by the lock;
the docs say plainly which installs the lock pins and which it does not; and a lock change that
lifts a version for a reason a user must see has a checked path to a floor.

## Sketch of the acceptance criteria

- **R1** — WHEN a change lifts a locked version because users need the newer release, the same
  commit SHALL raise the declared requirement's floor to at least that version.
- **R2** — The install documentation SHALL state that a git or `uvx` install resolves within the
  declared ranges and does not read `uv.lock`.
- **R3** — A check SHALL fail WHEN a requirement the project marks as user-critical is satisfied by
  the lock at a version below the declared floor the project records for it.

## Notes

- Related: `AGENTS.md` § Packaging (the `uv.lock` bullet) and § Factory → Release recipe (`lock`
  and `audit` caveats); `spec/capability-extras/` (TECH P4, PLAN §5).
- Open for shaping: whether the container image should install from the lock (`uv sync --locked`
  into the system environment) instead, which would move it from the unpinned side to the pinned.
- Found by: `capability-extras` P4 (the install probe's surface compare), filed at the foreman's
  ruling, 2026-10-31.
