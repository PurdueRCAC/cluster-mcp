---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A write whose host is lost after staging leaves its staging directory behind

## Problem

Over `ssh`, `SSHExecutor.write` stages the content by SFTP in a fresh directory of mode 0700 beside
the target (`.cluster-mcp-<hex>/`, holding `content` and `expected`), or in the login home for a
target written through, then runs a fixed program that checks the staged file and puts it in
place. The `finally` that removes the staging (`_discard`) runs on the write's own SFTP session.
When the host is lost after the content is staged, that session is dead: the removal fails
silently, and the directory stays.

Reproduced by the `ssh-reconnect-loop` review (cycle 1, 2026-10-26) against the in-process SSH
server: drop the link after staging, keep the host down; the write returns `-1002` (`cannot connect
to <host>: <cause>; the command was not run`), the target is untouched, and
`.cluster-mcp-<hex>/{content,expected}` remains beside it. With the host back at once, the place
step reconnects and the write succeeds, but `.cluster-mcp-<hex>/expected` is still left, since the
removal uses the first, dead session (rerun by its remediation build, same day).

What remains is the user's own content, in a 0700 directory the user owns, beside the file they
were writing: a leftover, not a disclosure. It accumulates only across lost connections.

## Why it was deferred

Found by `ssh-reconnect-loop`'s review; that cycle's appetite is the reconnect bound, and the fix
changes the write path (§ Invariants §2, human-gated). The cycle corrected the texts instead: the
`write` docstrings and § Invariants §2 now say the staging can remain when the host is lost after
staging.

**Pre-existing:** yes. On `develop` at `d34de62`, a drop after staging also left the directory (and
the write raised rather than returning `-1002`).

## Outcome / vision

A write that loses its host after staging leaves no staging behind once the host is reachable
again, or names what it left so the user can remove it.

## Sketch of the acceptance criteria

- **R1** — WHEN a write's connection is lost after its content is staged AND a later connection to
  the host succeeds, the executor SHALL remove that staging directory (for instance on the write's
  own reconnect, or the next one), never touching the target.
- **R2** — WHEN a write cannot remove its staging, its result or error SHALL name the directory
  left behind.
- **R3** — The suite SHALL pin both against the in-process SSH server, in both protocol eras.

## Notes

- Related: `spec/ssh-reconnect-loop/` (REVIEW.md cycle 1, the write finding);
  `issues/ssh-half-open-link.md`; `AGENTS.md` § Invariants §2.
- Found by: `ssh-reconnect-loop` review, cycle 1, 2026-10-26; filed by its remediation build.
