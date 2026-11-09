---
status: unshaped
kind: feature
appetite: big
lane: public
---

# A POSIX file family behind the `[files]` extra

## Problem

The file tools are too few and too thin, so agents fall back to the shell for everyday work.

- `list_directory` (`core/tools/filesystem.py`) parses the column text of `ls -l` and misreads some
  entries (`issues/list-directory-parsing.md`, absorbed here).
- `read_file` reads a whole file or its first N bytes, with no offset, no line numbers and no
  truncation flag, and no binary read to match `write_file`'s `base64` encoding.
- There is no stat, find, grep, edit, move or copy tool, so an agent that needs one runs it through
  `run_command`, gets unstructured text back, and on a parallel filesystem may start a recursive walk
  from a root on a shared login node.
- The file tools live in the core, so a deployment can't serve a cluster without them, or a
  different implementation of them (`issues/files-xdu-extra.md`).

**Pre-existing:** the thin tools are on `develop`; the family is new work.

## Why it was deferred

It renames the file tools and moves them out of the core, which is capability reshaping, so it is a
0.3.0 cycle, after `issues/core-extraction.md`. It was first sketched inside
`issues/tool-surface.md`, which now holds only the rules every family follows.

## Outcome / vision

`cluster-mcp[files]` installs a member that serves the POSIX file family, over every execution mode:

- **list** — one call, structured entries, parsed from a machine-readable form, never `ls -l`'s
  columns;
- **find** — bounded; **grep** — bounded content search;
- **stat**;
- **read** — offset and limit, line numbers, a byte cap, a `truncated` flag, binary content the
  same way `write` takes it;
- **write** — byte-exact; create, overwrite or append; makes parent directories;
- **edit** — exact string replacement with a uniqueness check and an mtime guard;
- **move** and **copy**;
- **put** and **get** — SFTP transfer between the client's machine and the cluster.

Each follows `issues/tool-surface.md`'s rules: names a client can allow-list by pattern, honest
annotations, a response budget, and membership in `--profile read-only` for the readers.

## Sketch of the acceptance criteria

- **R1** — WHERE the `[files]` extra is installed, the server SHALL register the family above, each
  tool returning structured results; WHERE neither it nor `[files-xdu]` is installed, no file tool
  SHALL be served.
- **R2** — list SHALL make a bounded number of remote calls regardless of the number of entries,
  SHALL not depend on GNU-only options, and SHALL return each entry's exact name and path
  (`issues/list-directory-parsing.md`).
- **R3** — WHEN edit's target string occurs other than exactly once, or the file's mtime has changed
  since the caller read it, the tool SHALL refuse and say which.
- **R4** — find and grep SHALL be bounded in entries and time, and SHALL say when they stopped short.
- **R5** — A byte-exact round trip (write then read, put then get) SHALL need no shell.

## Notes

- Tool names, and whether today's `list_directory`, `read_file`, `write_file`, `upload_file` and
  `download_file` survive as aliases, follow `issues/tool-surface.md`'s open question.
- `issues/files-xdu-extra.md` serves the same family from an index and conflicts with this extra;
  planning decides whether that member reuses this one's code.
- Planning decides whether a bounded usage tool (a `du` of one directory) belongs here or only in
  `[files-xdu]`.
- Related: `issues/core-extraction.md`, `issues/tool-surface.md`, `spec/safe-execution/` (the argv
  executor, `write_file`'s `base64` encoding).
- Found by: roadmap revision, 2026-11-09 (out of cycle); the problem list is `tool-surface`'s, from
  the roadmap revision of 2026-10-16.
