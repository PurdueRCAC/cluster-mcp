---
status: unshaped
kind: feature
appetite: small
lane: public
---

# The shell is a capability a deployment chooses, not one every server serves

## Problem

Every `cluster-mcp` server serves `run_command`, whatever else is installed. It is the one tool
that does anything the account can do, and the one no client can reason about from its name. Today
a deployment cannot leave it out short of patching the server. Someone running a hosted server for
other users, in `delegate` mode or under the hosted token mode, can't offer "the cluster's files,
jobs and storage, through named tools" without also offering "and any command line".

The roadmap puts the bespoke tools first and the shell last, and keeps the shell, because on a
cluster running code is the product. That is the right default for a user running the server for
themselves. It leaves no choice for an administrator who wants the named tools only.

**Pre-existing:** yes. The core has registered `run_command` since the first release.

## Outcome / vision

**`run_command` moves out of the core into a member of its own, installed by the `[shell]` extra.**
This is the same mechanism that serves `[slurm]` and `[rcac]` (`capability-extras`). Whether a
server offers a shell is then decided where every other capability is: at installation, by the
operator.

*Re-scoped 2026-11-09.* The member is a remote shell and nothing about HPC: `run_command` over the
executor (the SSH bridge in the default mode), with instructions that name no scheduler, module
system or filesystem. `cluster-mcp[shell]` alone is a remote shell, useful on any host the bridge
reaches. Lexing and steering on `run_command` are not part of this cycle; they are
`issues/shell-rails.md`'s, in 0.4.0.

- **The executor stays in the core** (`issues/core-extraction.md`). Every tool is built on
  `Executor.run`; only the MCP tool and its instructions move. A server without the extra still runs
  commands, but only the ones its named tools compose.
- **The instructions follow what is loaded.** Without the member, no served text names
  `run_command`. The core's text says what to do when no tool fits: tell the user the server has no
  shell, and do not route around its absence.
- **Existing installs keep their surface.** The `rcac-mcp` compatibility distribution pulls
  `[shell]` along with `[slurm,rcac]`, so the deprecated name serves exactly what it serves today.
  Whether a site extra (`site-extras`) pulls `[shell]` is that site's choice, stated in its README.
- **The guarantee is stated exactly, because absence is not containment.** Without the shell:
  - `file_write` can still write a login startup file, which the login initialisation of the next
    call runs.
  - Job submission (`[slurm]`) still runs any script on a compute node.

  What leaving it out does give: every action is a named tool with honest annotations, which a
  client can allow-list tool by tool and an audit log reads as intent; and the easiest path to an
  arbitrary command is gone. The combination that does confine is the shell left out *and*
  `--profile read-only` (`issues/tool-surface.md`). The docs name that combination and say plainly
  that the shell's absence alone is a choice of scope, not a security boundary (the boundary remains
  the Unix account).
- **Installation widens, a profile narrows.** A runtime profile may serve less than is installed;
  it may never serve a tool that isn't installed. So no flag adds a shell to a server installed
  without one.

**Sequencing.** It lands in 0.3.0, with or right after `issues/core-extraction.md`, beside
`issues/files-extra.md`, whose file family makes a server without a shell useful. *Corrected
2026-11-09:* this seed first argued for 0.2.0, the first release under the `cluster-mcp` name,
since changing the bare default then would break no one. Release 0.2.0 now carries no capability
reshaping, so its bare install still serves the shell, and 0.3.0 narrows it; the release notes of
both say so.

Open questions for shaping:

1. **The bare default.** *Ruled by Geoffrey, 2026-11-04:* a bare `pip install cluster-mcp` serves
   no shell. The docs present `[shell]` as the obvious opt-in most users will want: every
   single-user quick-start installs it, and the README says what leaving it out means.
2. **The shipped image.** The container image installs every member. Does it ship with the shell,
   and if so, how does an operator of that image leave it out: a second image, a build argument, or
   a narrowing profile (`--profile no-shell`)?
3. **The distribution's name.** *Ruled by Geoffrey, 2026-11-04:* the extra is `[shell]`. The
   member's distribution name follows the others (`cluster-mcp-shell`).
4. **Startup files.** Without the shell, should `file_write` refuse to write the account's login
   startup files, which would close the cheapest way back to an arbitrary command? It narrows a
   general tool for one case, and the account can still write them by other routes (job scripts),
   so the seed leans no: document it instead.

## Sketch of the acceptance criteria

- **R1** — `run_command` SHALL be registered only by the `[shell]` member; no other distribution
  SHALL serve a tool that takes a free-form command line.
- **R2** — WHERE the shell member is not installed, no served instruction, resource or tool
  description SHALL name `run_command`, and the core's instructions SHALL say that the server has
  no shell.
- **R3** — The `rcac-mcp` compatibility distribution SHALL serve the same tool surface as before
  this change.
- **R4** — No runtime option SHALL serve a tool whose member is not installed.
- **R5** — The docs SHALL state what the shell's absence does and does not prevent (startup files,
  job scripts) and which installation and profile together confine an agent to named tools.
- **R6** — A bare installation of `cluster-mcp` SHALL serve no shell. The README's quick-starts for
  a user running their own server SHALL install `[shell]`, and the README SHALL present it as the
  opt-in such a user will want.

## Notes

- Related: [`core-extraction.md`](core-extraction.md) (what stays in the core),
  [`tool-surface.md`](tool-surface.md) (names, annotations, `--profile read-only`),
  [`files-extra.md`](files-extra.md) (the file family), [`shell-rails.md`](shell-rails.md) (lexing and
  steering, 0.4.0), [`site-extras.md`](site-extras.md) (`[rcac]` pulls `[shell]`),
  [`slurm-capability.md`](slurm-capability.md) (job scripts run anything),
  `spec/capability-extras/` (the member mechanism; Q1 and Q3 rulings),
  [`https-token-mode.md`](https-token-mode.md) (hosted, where an operator chooses for other users).
- Found by: Geoffrey, 2026-11-04 (roadmap review, out of cycle).
