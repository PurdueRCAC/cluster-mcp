# cluster-mcp core

The core is the server itself: the `cluster-mcp` command and the tools every install serves. It
works on any cluster. [`SECURITY.md`](../../SECURITY.md#execution-modes-overview) says how to run
it in each mode.

## Install

Install the server with uv, from git. Name the extras your cluster needs in the requirement:

- `[slurm]` adds the [Slurm tools](../slurm/README.md).
- `[rcac]` adds the [Purdue RCAC tools](../rcac/README.md), and the Slurm tools with them.
- With no extra, `cluster-mcp` is the core alone: the shell, file and site-context tools.

The server lists only the tools of what is installed, and its instructions name only those.

In an MCP client's configuration, the requirement is one `args` element, spaces included, as in
the [Quick Start](../../README.md#quick-start). In a shell, quote the requirement, since
`[rcac]` is otherwise a glob:

```bash
uvx --from 'cluster-mcp[rcac] @ git+https://github.com/PurdueRCAC/cluster-mcp#subdirectory=packages/cluster-mcp' cluster-mcp --help
```

Install with uv, not pip. The server is a uv workspace. The extras install its members,
`cluster-mcp-slurm` and `cluster-mcp-rcac`, required by bare name. None of the three is registered
on PyPI. uv builds them from the same git commit. pip, or any install that skips uv's workspace
sources, would look for them on the package index instead, where anyone could register those names.

To leave `--ssh-host` out of the arguments, set `CLUSTER_MCP_SSH_HOST` in your environment.

## Tools

Every install serves these tools.

Shell and files:

- `run_command(command, cwd, timeout)` — Execute a shell command on the remote system
- `list_directory(path, show_hidden)` — List contents of a directory
- `read_file(path, encoding, max_size)` — Read contents of a file
- `write_file(path, content, append, create_dirs, encoding)` — Write content to a file, byte for byte (`encoding="base64"` for binary)
- `upload_file(local_path, remote_path)` — Upload a file to the remote system
- `download_file(remote_path, local_path)` — Download a file from the remote system

Site context:

- `cluster_context()` — The cluster's rules from `/etc/agents.d`, in full, as read at startup

## What it needs on the cluster

- A login bash, `/bin/bash -l`. Every command runs in it.
- In `ssh` mode, an SSH server with SFTP, and your SSH configuration (`~/.ssh/config` and keys).

The core declares no commands of its own. A capability whose commands the cluster lacks is
withheld, on its own and not with the extra that installed it;
see [Which capabilities are served](#which-capabilities-are-served).

## How it behaves

### The connection

In `ssh` mode the server runs commands on the cluster over SSH. If it cannot connect, your client
shows the reason as the error to its first request: `cannot connect to <host>: <cause>`. The cause
is one of:

- unknown host or SSH alias;
- connection refused;
- authentication failed;
- connection closed during authentication;
- timed out, after 15 seconds per step unless your SSH config sets `ConnectTimeout`.

Check that `--ssh-host` names the SSH host or `~/.ssh/config` alias you use with `ssh`, not the MCP
server's name.

Once running, the server keeps one connection to the cluster. A call that finds it lost
reconnects. A link can also die silently, with no reset: a laptop asleep through a network change,
an expired NAT entry, a login node powered off. The server notices that too.

- A reconnecting call gives up with the same `cannot connect to <host>: <cause>` at most 45 s after
  it began. That is three times the connect bound; a longer `ConnectTimeout` raises it.
- The server probes the cluster after 15 s of quiet, and at once when a call starts.
- It takes the link for dead when a probe goes unanswered with nothing heard since: 15 s after a
  call's start, or 29 s after a background probe.
- A call that starts on a dead link reconnects, or gives up as above.
- A command running on it returns `-1003` at most 44.45 s after the last message heard.

A quiet command or a slow transfer is never cut while the cluster answers. At the default bound:

- the cluster must answer a probe within 29 s;
- a transfer must hear some reply at least every 44 s (an upload above about 0.75 KB/s).

A file transfer the lost link cuts short fails with an error naming the host. The error says
the transfer may be partly made, and what may remain:

- an upload's target, or a download's local file, may be truncated;
- a `write_file` (or an `sbatch` job script) leaves its target unchanged while staging;
- once the write was putting the file in place, the target holds the old file or the new one.

A lost write may leave its private staging directory (`.cluster-mcp-…`) beside the target
([`issues/ssh-write-staging-leftover.md`](../../issues/ssh-write-staging-leftover.md)).

### Commands

In every mode a command runs in a login bash (`/bin/bash -l`), whatever the user's login shell. So
`module` and the site's tools behave the same for everyone. No startup file reads a file's content
or changes where a command starts. Nothing the login initialisation prints is returned, with one
exception: over ssh, a background job started by the remote login shell's own rc file (zsh's
`.zshenv`, say) can write into a result while the command runs
([`issues/startup-background-jobs.md`](../../issues/startup-background-jobs.md)).

A result holds all of the command's output, however slowly it arrives. The launcher reports the
command's end on both streams, and the call returns there. So a background job the command or a
startup file leaves running never holds it, and what such a job prints afterwards is not returned.

Exit codes the server sets:

| Exit code | Meaning |
|---|---|
| `-N` | The command was killed by signal N, or exited 128+N. |
| `-1001` | The command exceeded its `timeout`. It returns what it printed so far. |
| `-1002` | The command was not started (see [Timeouts and the stop](#timeouts-and-the-stop)). |
| `-1003` | Over ssh, the connection was lost before the command's end was reported, a link gone silent included. The command may have run, and may still be running. |

### File writes

`write_file` and `sbatch`'s job script are written byte for byte. Over ssh their content never
rides a command's stdin. It goes by SFTP to a private temporary file beside the target. That file
is checked against the bytes sent (its size and checksum), then moved into place. So the file is
replaced whole and keeps its permissions, but setuid and setgid end up as `cat >` leaves them.

A transfer that fails or falls short (a full filesystem, a spent quota) leaves the file untouched
and says why. A write refuses what `cat >` refuses: a file you may not write, or a link whose
target's directory is missing.

### Timeouts and the stop

A command that exceeds its `timeout` returns what it printed so far, and is stopped with
everything it started:

- it returns with exit code `-1001`, within 2 seconds of the deadline;
- it is stopped within the same 2 seconds;
- each process gets at most one TERM signal, so a command that handles it has a second to finish,
  and then KILL;
- in `delegate` mode under a server that is not root, only the launch gets the TERM, and the
  command's processes get KILL a second later.

A command whose deadline passes while a login startup file still runs is not started in `local` or
`delegate` mode. A step of the server's wall clock changes that:

- a step forward reports a command whose deadline has not come as not started, `-1002`;
- a step back lets a late one start, which in `delegate` mode under a server that is not root then
  runs on.

What the stop does not touch, and what it still reaches:

- a command with no timeout, or one that has not reached it, is never signalled by the stop;
- a command that has finished while what reads its output went away (the server killed, the link
  lost) has what it left running stopped too, since its launch dies before it can report the end.

Some processes escape the stop, and some login startup files can trip it early; each case is in
[`issues/timeout-stop-limits.md`](../../issues/timeout-stop-limits.md).

### Which capabilities are served

An installed capability is served only where the cluster has what it needs. At startup in `ssh`
and `local` modes, the server looks up the commands each installed capability declares, once,
before it answers any request. It looks them up on the cluster, through the same login shell its
tools run in:

- the Slurm capability: `sbatch`, `squeue`, `scancel`, `sacct`, `sinfo` and `scontrol`;
- the RCAC capability: `findscratch` and `myquota`.

A capability missing one of its commands is served as if it were not installed: none of its tools,
resources or instructions. The server says so on stderr, one line for each:

```
Capability cluster-mcp-slurm withheld: the cluster is missing sbatch, squeue, scancel, sacct, sinfo, scontrol
```

Each capability is judged on its own, not the extra that installed it. `cluster-mcp[rcac]` installs
the RCAC and Slurm capabilities: on a cluster without `findscratch` or `myquota` it still serves the
Slurm tools, and on one without Slurm's commands it still serves the RCAC tools.

- The lookup takes 10 s at most.
- If it gives no answer in that time, or cannot run, every capability is served, with one line
  each saying why: `Capability <name> served without a probe answer: the probe did not answer within 10 s`.
- To serve every installed capability without looking, pass `--skip-probes`, or set
  `CLUSTER_MCP_SKIP_PROBES` to any non-empty value (`0` included). The server then says the probes
  were skipped.

`delegate` mode never probes: it serves every installed capability, and says so.

### The cluster's rules, in the instructions

Cluster administrators can publish rules for agents as Markdown files in `/etc/agents.d`. The
server reads them once, at startup, and serves them after its own instructions. So the agent sees
the site's rules without asking.

- It reads every `*.md` file directly in that directory except the assembled `AGENTS.md`, which
  repeats the others.
- It reads them on the cluster in `ssh` mode, and on the server's own host in `local` and
  `delegate` modes.
- Files go in whole, each under a `<!-- Source: name.md -->` header, in the byte order of their
  names (`LC_ALL=C sort`). To put a file first, give it a name that sorts first, such as one
  starting `00-`.
- An edit takes effect at the next start.
- A control character in a file name (a line break, for instance) is shown as an escape such as
  `\x0a`, and a backslash as `\x5c`, so a name always stays on its one line.
- Names are shown by their decoded text. Two names that differ only in bytes that are not valid
  UTF-8 (each read as U+FFFD) can show alike; they are still two files.

In `delegate` mode one server serves many accounts, so it serves only what every account could
read:

- the owner, the group and others must each be able to read every file, read and search the
  directory, and search every directory above it (through any symlink on the way);
- none of these may carry an ACL entry.

Otherwise the server serves a line saying the rules could not be read, instead of any of them. In
`local` and `ssh` modes the server reads as the user it serves, and the file system decides.

### The instructions budget

Claude Code cuts long server instructions, so the server keeps its own within a budget. Whatever
does not fit is named, and the `cluster_context` tool (and the `cluster://context` resource)
returns all of it.

- The budget is 4,096 characters by default, because Claude Code cuts server instructions there.
- To serve everything to Claude Code, raise both limits, the server's and Claude Code's:
  - add `"--instructions-budget", "16384"` to the server's `args` (or set
    `CLUSTER_MCP_INSTRUCTIONS_BUDGET=16384`);
  - set `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH=16384` in the shell that starts Claude Code, or in
    the `env` block of its `settings.json`.
- That variable raises Claude Code's limits on server instructions and on tool descriptions
  together. It needs Claude Code 2.1.280 or later; before 2.1.296 the default cut is 2,048
  characters.
- `/context` shows what was loaded.
