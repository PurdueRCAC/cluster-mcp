# RCAC tools (`[rcac]`)

The `[rcac]` extra adds tools that wrap Purdue RCAC's own commands: storage, job details,
partitions and accounts. Install it with `[slurm]`, as `cluster-mcp[slurm,rcac]` in the
[Quick Start](../../README.md#quick-start).

## Tools

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

## What it needs on the cluster

- `findscratch` and `myquota`, found through the login shell the tools run in.
- The Slurm extra beside it, [`[slurm]`](../slurm/README.md): several of its tools take a Slurm job
  id.

If the cluster is missing either command, the server withholds the extra: none of its tools,
resources or instructions are served. See
[Which capabilities are served](../core/README.md#which-capabilities-are-served).

## How it behaves

- Each tool runs RCAC's command on the cluster, in the login bash every command runs in
  ([Commands](../core/README.md#commands)).
- The server's instructions list these tools, after the core's and the Slurm extra's.
- The `cluster://storage` resource returns what `storage_paths` returns. In `delegate` mode it
  runs as the mapped user of the request that read it
  ([`SECURITY.md`](../../SECURITY.md#request-isolation-in-delegate-mode)).

## RCAC documentation

This server does not search RCAC documentation. The separate `rcac-docs-mcp` service at
`https://docs.rcac.purdue.edu/mcp` does: add it to your MCP client alongside this server.
