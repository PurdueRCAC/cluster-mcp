# cluster-mcp

cluster-mcp is an MCP server that gives AI agents shell, files, jobs and storage on HPC clusters.
It runs commands on a cluster over SSH for one user, or serves many users from a shared host. Its
core works on any cluster, and extras add the Slurm tools (`[slurm]`) and the Purdue RCAC tools
with the Slurm tools (`[rcac]`).

## Quick Start

Add the server to your MCP client (Claude Desktop, Cursor, Warp or another), with an SSH host
pointing at your cluster:

```json
{
  "mcpServers": {
    "cluster": {
      "command": "uvx",
      "args": ["--from", "cluster-mcp[rcac] @ git+https://github.com/PurdueRCAC/cluster-mcp#subdirectory=packages/cluster-mcp",
               "cluster-mcp", "--ssh-host", "cluster.rcac.purdue.edu"]
    }
  }
}
```

The client then runs the server on your machine in `stdio` mode. The server runs commands on the
cluster over SSH, with your existing `~/.ssh/config` and keys.

Name the extra your cluster needs in the requirement: `[slurm]` adds the Slurm tools, and `[rcac]`
the Purdue RCAC tools together with the Slurm tools. With no extra you get the core alone. To install
and run it from a shell:

```bash
uvx --from 'cluster-mcp[rcac] @ git+https://github.com/PurdueRCAC/cluster-mcp#subdirectory=packages/cluster-mcp' cluster-mcp --help
```

Claude Code cuts long server instructions, so the server trims its own to fit. To serve the
cluster's rules in full, [raise both limits](docs/core/README.md#the-instructions-budget).

## Capabilities

| Capability | Install | What it adds | Docs |
|---|---|---|---|
| Core | `cluster-mcp` | Shell, file and site-context tools, on any cluster | [docs/core](docs/core/README.md) |
| Slurm | `cluster-mcp[slurm]` | Slurm job and cluster-status tools | [docs/slurm](docs/slurm/README.md) |
| RCAC | `cluster-mcp[rcac]` | Purdue RCAC storage, job, partition and account tools, with the Slurm tools. To search RCAC documentation, add the [RCAC documentation service](docs/rcac/README.md#rcac-documentation) | [docs/rcac](docs/rcac/README.md) |

The server serves an extra only where the cluster has the commands it needs.

## Run modes

| Mode | For | How it runs |
|---|---|---|
| [`ssh`](SECURITY.md#mode-1-ssh-execution-stdio) | One user, from a desktop client (the default for stdio) | Runs commands on the cluster over SSH |
| [`local`](SECURITY.md#mode-2-local-execution-http-with-authnone) | Development and testing only | Runs commands on the server's own host, under bash |
| [`delegate`](SECURITY.md#mode-3-delegated-execution-http-with-auth) | Many users, from a shared host | Runs each user's commands as that user, through `sudo`; needs JWT or OIDC |

[SECURITY.md](SECURITY.md) says how to run each mode, including a hosted HTTP server, and what each
mode trusts.

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

## Development

```bash
uv sync               # the core and every capability, editable, through the root's extras
cluster-mcp -e local
```

Run the test suite:

```bash
pytest
```

The rules for changing the code are in [AGENTS.md](AGENTS.md).

## License

MIT
