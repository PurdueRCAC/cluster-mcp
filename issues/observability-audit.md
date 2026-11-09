---
status: unshaped
kind: feature
appetite: big
lane: public
---

# Records of what the server did, kept on the machine where the commands ran

## Problem

The server keeps no record of what it did. A user can't answer "what did my agent run on the
cluster yesterday, and what came back", an operator of a `delegate` deployment can't answer "what
ran as whom", and nobody can measure which tools agents use or where calls fail. Logs today are
whatever the transport prints on the server's stderr, on whichever machine the server runs: in the
default deployment, the user's laptop, not the cluster.

## Why it was deferred

It records the surface 0.3.0 builds, so it is 0.4.0's, with `issues/shell-rails.md`.
**Pre-existing:** n/a — new work.

## Outcome / vision

Every call leaves a record — the tool, its arguments, the identity it ran as, when, how long, and
how it ended — on the machine where the command ran, so the record sits beside what it describes:

- **`ssh` mode:** on the destination cluster, under `$XDG_DATA_HOME/cluster_mcp/` (by default
  `~/.local/share/cluster_mcp/`), written as the user.
- **`local` mode and the single-user token mode** (`issues/https-token-mode.md`): the same path, as
  the user.
- **`delegate` mode:** each user's records in their own path, written as that user; plus a
  server-side copy of every user's records and a system event log (startup, shutdown, refusals,
  reconnects). Planning proposes where those two live.

Observability (counts, durations, failures by tool) is read from the same records, not from a second
channel.

Cluster tests point `XDG_DATA_HOME` into a scratch directory, so a test run never writes into a real
user's records.

## Sketch of the acceptance criteria

- **R1** — WHEN a tool call ends, in any mode, the server SHALL append one record of it in the
  calling user's records on the host where the command ran.
- **R2** — In `ssh`, `local` and token modes the records SHALL be written under
  `$XDG_DATA_HOME/cluster_mcp/`, defaulting to `~/.local/share/cluster_mcp/`, as the user.
- **R3** — In `delegate` mode each user's records SHALL be written as that user in their own path,
  and the server SHALL also keep a copy of every user's records and a system event log.
- **R4** — Cluster tests SHALL set `XDG_DATA_HOME` to a scratch directory.

## Notes

- Open for shaping: the record format and rotation; what is redacted (file content, a write's
  payload, anything secret-shaped in a command line); whether a record is written in the same remote
  call as the command or after it; the server-side location in `delegate` mode; whether a record
  that cannot be written fails the call (an audit log may need to, in `delegate` mode) or is only
  reported.
- 0.4.0's design must cover the hosted single-user token mode (`issues/https-token-mode.md`), which
  is not yet ordered, so its records follow the `local` rule whenever it lands.
- `delegate` mode writes as other users from a privileged process: every write path is a
  high-blast-radius change (`AGENTS.md` § Invariants §5).
- Related: `issues/shell-rails.md`, `issues/https-token-mode.md`.
- Found by: roadmap revision, 2026-11-09 (out of cycle).
