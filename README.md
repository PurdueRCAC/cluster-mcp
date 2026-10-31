# cluster-mcp

An MCP server for HPC clusters: shell, files, jobs and storage for AI agents. It runs commands on a
cluster over SSH for one user, or serves many users from a shared host. Its core serves shell and
file tools on any cluster; the rest are capabilities you install as extras, for what your cluster
has: the Slurm tools (`[slurm]`) and the Purdue RCAC-specific tools (`[rcac]`).

## Quick Start (Desktop Clients)

For MCP-enabled desktop applications like Claude Desktop, Cursor, or Warp, add this server
to your MCP configuration with an SSH host pointing at your cluster:

```json
{
  "mcpServers": {
    "cluster": {
      "command": "uvx",
      "args": ["--from", "cluster-mcp[slurm,rcac] @ git+https://github.com/PurdueRCAC/cluster-mcp#subdirectory=packages/cluster-mcp",
               "cluster-mcp", "--ssh-host", "cluster.rcac.purdue.edu"]
    }
  }
}
```

This runs the server locally in `stdio` mode, executing commands on the cluster over SSH
using your existing `~/.ssh/config` and keys.

Install with uv, from git, as above, naming the extras your cluster needs in the requirement (one
`args` element, spaces included): `[slurm]` adds the Slurm tools, `[rcac]` the Purdue RCAC-specific
tools, which go with `[slurm]`, so a Purdue cluster takes `cluster-mcp[slurm,rcac]`, as above.
`cluster-mcp` with no extra is the core alone: the shell, file and site-context tools. The server
lists only the tools of what is installed, and its instructions name only those. In a shell, quote
the requirement, since `[slurm,rcac]` is otherwise a glob:

```bash
uvx --from 'cluster-mcp[slurm,rcac] @ git+https://github.com/PurdueRCAC/cluster-mcp#subdirectory=packages/cluster-mcp' cluster-mcp --help
```

The server is a uv workspace: each extra installs one member, `cluster-mcp-slurm` or
`cluster-mcp-rcac`, required by bare name, and none of the three is registered on PyPI. uv builds
them from the same git commit; pip, or any install that skips uv's workspace sources, would look for
them on the package index instead, where anyone could register those names.

Alternatively, set `CLUSTER_MCP_SSH_HOST` in your environment and omit `--ssh-host` from the args.

If the server cannot connect, your client shows the reason as the error to its first request:
`cannot connect to <host>: <cause>` (unknown host or SSH alias, connection refused, authentication
failed, connection closed during authentication, or timed out after 15 seconds per step unless your
SSH config sets `ConnectTimeout`). Check
that `--ssh-host` names the SSH host or `~/.ssh/config` alias you use with `ssh`, not the MCP
server's name.

### The cluster's rules, in the instructions

Cluster administrators can publish rules for agents as Markdown files in `/etc/agents.d`. At
startup the server reads every `*.md` file directly in that directory except the assembled
`AGENTS.md` (which repeats the others), once (on the cluster in `ssh` mode, on the server's own host
in `local` and `delegate` modes), and serves them after its own instructions, so the agent sees the
site's rules without asking. Files go in whole, each under a
`<!-- Source: name.md -->` header, in the byte order of their names (`LC_ALL=C sort`): an
administrator who wants a file first gives it a name that sorts first, such as one starting `00-`.
An edit takes effect at the next start. A control character in a file name (a line break, for
instance) is shown as an escape such as `\x0a`, and a backslash as `\x5c`, so a name always stays
on its one line. Names are shown by their decoded text, so two names that differ only in bytes that
are not valid UTF-8 (each read as U+FFFD) can show alike; they are still two files.

In `delegate` mode one server serves many accounts, so it serves only what every account could
read: the owner, the group and others must each be able to read every file, read and search the
directory, and search every directory above it (through any symlink on the way), and none of these
may carry an ACL entry. Otherwise the server serves a line saying the rules could not be read
instead of any of them. In `local` and `ssh` modes the server reads as the user it serves, and the
file system decides.

The instructions stay within 4,096 characters by default, because Claude Code cuts server
instructions there. Whatever does not fit is named, and the `cluster_context` tool (and the
`cluster://context` resource) returns all of it. To serve everything to Claude Code, raise both
limits, the server's and Claude Code's:

- add `"--instructions-budget", "16384"` to the server's `args` (or set
  `CLUSTER_MCP_INSTRUCTIONS_BUDGET=16384`);
- set `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH=16384` in the shell that starts Claude Code, or in
  the `env` block of its `settings.json`. It raises Claude Code's limits on server instructions and
  on tool descriptions together (the variable needs Claude Code 2.1.280 or later; before 2.1.296 the
  default cut is 2,048 characters). `/context` shows what was loaded.

## Upgrading from rcac-mcp

In 0.2.0 the server was renamed from `rcac-mcp` to `cluster-mcp`. Each old name is
deprecated in 0.2.0, removed no earlier than 0.4.0, and keeps working until it is removed:

| Deprecated | Replacement |
|---|---|
| the `rcac-mcp` command | `cluster-mcp` |
| `RCAC_SSH_HOST`, `RCAC_USER_MAP`, `RCAC_INSTRUCTIONS_BUDGET` | `CLUSTER_MCP_SSH_HOST`, `CLUSTER_MCP_USER_MAP`, `CLUSTER_MCP_INSTRUCTIONS_BUDGET` |
| the `rcac://context` and `rcac://storage` resources | `cluster://context` and `cluster://storage` |

The command and each old variable print a warning on stderr naming the replacement and the window.
When an old and a new variable are both set, the new one wins, and the warning says the old one is
ignored. An `rcac://` URI returns the same content as its `cluster://` replacement. The install
line earlier releases documented keeps working through the window too: it installs a compatibility
distribution that carries every capability (`cluster-mcp[slurm,rcac]`) and runs the deprecated
`rcac-mcp` command. Update your MCP client
configuration to the Quick Start form above.

## Execution Modes

The server supports three execution modes:

- **`ssh`** (default for stdio) — Execute commands on a remote HPC cluster via SSH.
- **`local`** — Execute commands locally under bash. For development/testing only.
- **`delegate`** — Multi-user mode; run as a privileged process and delegate commands to
  authenticated users via `sudo`. Requires JWT or OIDC authentication.

In every mode a command runs in a login bash (`/bin/bash -l`), whatever the user's login shell, so
`module` and the site's tools behave the same for everyone. No startup file reads a file's content
or changes where a command starts, and nothing the login initialisation prints is returned, with
one exception: over ssh, a background job started by the remote login shell's own rc file (zsh's
`.zshenv`, say) can write into a result while the command runs
([`issues/startup-background-jobs.md`](issues/startup-background-jobs.md)). A result holds all of
the command's output, however slowly it arrives: the launcher reports the command's end on both
streams, and the call returns there, so a background job the command or a startup file leaves
running never holds it, and what such a job prints afterwards is not returned. A command killed by
signal N (or exiting 128+N) has exit code `-N`. `write_file` and `sbatch`'s job script are written
byte for byte; over ssh their content never rides a command's stdin but goes by SFTP to a private
temporary file beside the target, which is checked against the bytes sent (its size and checksum)
and then moved into place, so the file is replaced whole and keeps its permissions (but setuid and
setgid, as `cat >` leaves them). A transfer that fails or falls short (a full filesystem, a spent
quota) leaves the file untouched and says why, and a write refuses what `cat >` refuses (a file you
may not write, a link whose target's directory is missing). A command that exceeds its `timeout`
returns what it printed so far with exit code `-1001`; over ssh, a connection lost before the
command's end was reported gives `-1003`: the command may have run.

See [SECURITY.md](SECURITY.md) for detailed architecture and configuration.

## Hosted HTTP Server

For a shared hosted instance with authentication, run `cluster-mcp` installed with the extras the
cluster needs (the Quick Start's requirement):

### Basic HTTP Server

```bash
cluster-mcp -t http --ssh-host cluster.rcac.purdue.edu
```

### With JWT Authentication

```bash
export JWT_SECRET="your-secret-key-at-least-32-characters"
cluster-mcp -t http -a jwt -e delegate

# Generate a token for clients
cluster-mcp --generate-token --lifetime 86400
```

### Docker Compose with TLS

For production-like deployments with HTTPS:

```bash
# Install mkcert if needed
brew install mkcert
mkcert -install

# Generate certificates
mkdir -p certs
mkcert -cert-file certs/cert.pem -key-file certs/key.pem mcp.rcac.dev localhost 127.0.0.1

# Add to /etc/hosts
echo "127.0.0.1 mcp.rcac.dev" | sudo tee -a /etc/hosts

# Run
docker compose up
```

The server will be available at `https://mcp.rcac.dev:8443`.

## RCAC Documentation

This server does not search RCAC documentation. The separate `rcac-docs-mcp` service at
`https://docs.rcac.purdue.edu/mcp` does: add it to your MCP client alongside this server.

## Available Tools

The tools come in three groups, as the server's instructions list them: the core, which every
install serves; the Slurm tools, served with the `[slurm]` extra; and the RCAC-specific tools,
served with the `[rcac]` extra (install it with `[slurm]`: several of its tools take a Slurm job id).
A server serves only the groups installed.

### Core

Shell and files:

- `run_command(command, cwd, timeout)` — Execute a shell command on the remote system
- `list_directory(path, show_hidden)` — List contents of a directory
- `read_file(path, encoding, max_size)` — Read contents of a file
- `write_file(path, content, append, create_dirs, encoding)` — Write content to a file, byte for byte (`encoding="base64"` for binary)
- `upload_file(local_path, remote_path)` — Upload a file to the remote system
- `download_file(remote_path, local_path)` — Download a file from the remote system

Site context:

- `cluster_context()` — The cluster's rules from `/etc/agents.d`, in full, as read at startup

### Slurm (`[slurm]`)

- `sbatch(...)` — Submit a batch job (from script path or inline content, written byte for byte); `args` are the job script's arguments, `extra_args` more sbatch options, each a list with one argument per element
- `squeue(...)` — View the job queue
- `scancel(...)` — Cancel jobs
- `sacct(...)` — Query job accounting history
- `sinfo(...)` — Cluster and partition status
- `scontrol_show_job(job_id)` — Detailed Slurm job info
- `scontrol_show_node(node)` — Detailed node info

The `extra_args` of `sbatch`, `squeue`, `scancel`, `sacct` and `sinfo` is a list of options, one argument per element (`extra_args=["--long"]`); a string is refused.

### RCAC-specific (`[rcac]`, with `[slurm]`)

- `myquota()` — Show storage usage and quota limits
- `storage_paths()` — Get resolved paths for home, scratch, and depot
- `jobinfo(job_id)` — Detailed job information
- `jobcmd(job_id)` — Command submitted for a job
- `jobenv(job_id)` — Environment variables for a job
- `jobscript(job_id)` — Full submission script for a job
- `showpartitions()` — Available partitions and their status
- `average_wait(partition, account)` — Queue wait time statistics
- `slist()` — Slurm accounts and usage
- `sfeatures()` — Node hardware features and constraints

## Development

```bash
uv sync               # the core and every capability, editable, through the root's extras
cluster-mcp -e local
```

Run the test suite:

```bash
pytest
```

## License

MIT
