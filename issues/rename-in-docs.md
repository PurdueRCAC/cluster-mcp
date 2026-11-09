---
status: unshaped
kind: docs
appetite: small
lane: public
---

# Every in-repo doc says cluster-mcp

## Problem

`rename-to-cluster-mcp` renamed the code and the install lines, and most of the README, `SECURITY.md`
and the members' READMEs now say `cluster-mcp`. What it left is the docs' point of view: in places
they still read as the documentation of a Purdue server rather than of a general one with Purdue as
one supported site.

- `SECURITY.md` shows a token's `iss` and `aud` as `rcac-mcp`, which is true until
  `issues/rename-leftover-identity-strings.md` moves the claims under their window, and has to change
  with them.
- The README's examples take a Purdue host as the default `--ssh-host`, its TLS section names a
  Purdue development host, and a section on the site's documentation service sits among the
  server's own sections.
- Where the old name is legitimately still in a doc (the upgrading section, the compat
  distribution, the deprecated command), nothing says the rest of the doc may not use it.

## Why it was deferred

The rename's GOAL renamed names, not prose, and its R-IDs listed what moved. **Pre-existing**: every
instance above is on `develop` today.

## Outcome / vision

Every tracked document outside `spec/` presents the project as `cluster-mcp`. The old name appears
only where a doc describes the deprecation window, the `rcac-mcp` compat distribution or the
deprecated command, and Purdue appears only where a doc describes the `[rcac]` extra or labels an
example as a Purdue one.

## Sketch of the acceptance criteria

- **R1** — Every tracked `*.md` outside `spec/` and `issues/` SHALL name the server `cluster-mcp`;
  the old name SHALL appear only in text that describes the deprecation window or the compat
  distribution.
- **R2** — WHERE a doc's example names a site-specific host or path, the doc SHALL label it as that
  site's example.
- **R3** — `SECURITY.md`'s token claims SHALL match what `issues/rename-leftover-identity-strings.md`
  ships, in the same commit as that change.

## Notes

- Planning decides whether a test pins R1 (a list of the files and passages allowed the old name),
  and how it sits beside the README window checks `AGENTS.md` § Testing already describes.
- `spec/` is never edited: its records name what was true when they were written.
- Related: `issues/rename-leftover-identity-strings.md`, `spec/rename-to-cluster-mcp/`.
- Found by: roadmap revision, 2026-11-09 (out of cycle).
