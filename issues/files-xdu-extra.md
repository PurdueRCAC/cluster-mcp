---
status: unshaped
kind: feature
appetite: big
lane: public
---

# `[files-xdu]`: the file family answered from an xdu index where one helps

## Problem

"What's filling my scratch", "find every `*.h5` under this project" and a listing of a tree with
millions of entries end, with the `[files]` family alone, in a bounded walk that stops short, and
without it in a recursive `find` or `du` through the shell: on a parallel filesystem, the long
metadata load login-node rules forbid. [xdu](https://github.com/xdu-project/xdu) answers these
from a cached index (`issues/xdu-storage.md` has its facts and gaps).

## Why it was deferred

It is a second implementation of the file family, so it follows `issues/files-extra.md`, and it
indexes large trees through `issues/jobs-interface.md`. A 0.3.0 cycle. **Pre-existing:** n/a — new
work.

## Outcome / vision

`cluster-mcp[files-xdu]` serves the same file family as `[files]`, the same names and shapes, and
answers from xdu's index where a cached index helps: find, usage, and listing large trees. Where no
index covers a path, it answers as `[files]` does and says an index would help.

- **The system xdu, detected, never installed.** The member looks for `xdu` and `xdu-find` on the
  host; where they are missing the index-backed answers say so and the rest of the family works.
  Installing anything into a user's home is ruled out.
- **Indexes live in scratch**, not home, and report their age. Large trees are indexed through the
  jobs interface, within limits the site sets; small ones at low priority.
- **Typed operations only.** No tool accepts or forwards SQL or any other query language from the
  caller.
- **It conflicts with `[files]`.** Both serve the same tool names, so the conflict is declared in
  packaging, and because pip and `uvx` never read uv's conflict declaration, the load also refuses
  when both distributions arrive, naming both.

## Sketch of the acceptance criteria

- **R1** — WHERE `[files-xdu]` is installed, the server SHALL serve the file family under the same
  names and shapes as `[files]`.
- **R2** — WHEN an index covers the requested path, find, usage and list SHALL answer from it and
  SHALL report the index's age; otherwise they SHALL answer without it and say so.
- **R3** — IF `xdu` is absent on the host, THEN no tool SHALL install it, and each index-backed
  answer SHALL say it is absent.
- **R4** — Indexes SHALL be written under the user's scratch, never under home, and indexing a tree
  above a documented size SHALL go through the jobs interface.
- **R5** — No tool SHALL accept or forward SQL or any other query language from the caller.
- **R6** — The packaging SHALL declare `[files]` and `[files-xdu]` as conflicting, and WHEN both
  distributions are installed the load SHALL refuse, naming both.

## Notes

- Where the index root lives is site knowledge: a site interface or the site's extra supplies it
  (`issues/site-interfaces.md`); a generic default stands in until then.
- Byte-sum rollups are missing from `xdu-find`; usage needs them, as an upstream request
  (`issues/xdu-storage.md`).
- Planning decides whether this member reuses `[files]`'s code (a dependency on it would make the
  conflict a self-conflict) or a shared library both depend on.
- Related: `issues/xdu-storage.md` (absorbed here), `issues/files-extra.md`,
  `issues/jobs-interface.md`, `issues/site-extras.md` (`[rcac]` pulls this extra).
- Found by: roadmap revision, 2026-11-09 (out of cycle).
