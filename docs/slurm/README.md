# Slurm tools (`[slurm]`)

The `[slurm]` extra adds tools for Slurm jobs and cluster status. Install it by naming the extra in
the requirement, as in the [Quick Start](../../README.md#quick-start).

## Tools

- `sbatch(...)` — Submit a batch job (from script path or inline content, written byte for byte); `args` are the job script's arguments, `extra_args` more sbatch options, each a list with one argument per element
- `squeue(...)` — View the job queue
- `scancel(...)` — Cancel jobs
- `sacct(...)` — Query job accounting history
- `sinfo(...)` — Cluster and partition status
- `scontrol_show_job(job_id)` — Detailed Slurm job info
- `scontrol_show_node(node)` — Detailed node info

The `extra_args` of `sbatch`, `squeue`, `scancel`, `sacct` and `sinfo` is a list of options, one
argument per element (`extra_args=["--long"]`). A string is refused.

## What it needs on the cluster

- `sbatch`, `squeue`, `scancel`, `sacct`, `sinfo` and `scontrol`, found through the login shell the
  tools run in.

If the cluster is missing any of them, the server withholds the extra: none of its tools,
resources or instructions are served. See
[Which capabilities are served](../core/README.md#which-capabilities-are-served).

## How it behaves

- Each tool runs its Slurm command on the cluster, in the login bash every command runs in
  ([Commands](../core/README.md#commands)).
- The server's instructions list these tools, after the core's.
- `sbatch` writes an inline job script byte for byte, as `write_file` writes a file
  ([File writes](../core/README.md#file-writes)). A lost link can cut that write short, as it can
  any transfer ([The connection](../core/README.md#the-connection)).
- Pass options a tool has no argument for in `extra_args`, one argument per element.
