# RCAC MCP Server

Purdue RCAC MCP Server: Enables agentic development with HPC clusters and storage services.

## Quick Start (Desktop Clients)

For MCP-enabled desktop applications like Claude Desktop, Cursor, or Warp, add this server
to your MCP configuration with an SSH host pointing at your cluster:

```json
{
  "mcpServers": {
    "rcac": {
      "command": "uvx",
      "args": ["git+https://github.com/purduercac/rcac-mcp", "--ssh-host", "cluster.rcac.purdue.edu"]
    }
  }
}
```

This runs the server locally in `stdio` mode, executing commands on the cluster over SSH
using your existing `~/.ssh/config` and keys.

Alternatively, set `RCAC_SSH_HOST` in your environment and omit `--ssh-host` from the args.

## Execution Modes

The server supports three execution modes:

- **`ssh`** (default for stdio) — Execute commands on a remote HPC cluster via SSH.
- **`local`** — Execute commands locally via `$SHELL`. For development/testing only.
- **`delegate`** — Multi-user mode; run as a privileged process and delegate commands to
  authenticated users via `sudo`. Requires JWT or OIDC authentication.

See [SECURITY.md](SECURITY.md) for detailed architecture and configuration.

## Hosted HTTP Server

For a shared hosted instance with authentication:

### Basic HTTP Server

```bash
rcac-mcp -t http --ssh-host cluster.rcac.purdue.edu
```

### With JWT Authentication

```bash
export JWT_SECRET="your-secret-key-at-least-32-characters"
rcac-mcp -t http -a jwt -e delegate

# Generate a token for clients
rcac-mcp --generate-token --lifetime 86400
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

### Shell & Filesystem

- `run_command(command, cwd, timeout)` — Execute a shell command on the remote system
- `list_directory(path, show_hidden)` — List contents of a directory
- `read_file(path, encoding, max_size)` — Read contents of a file
- `write_file(path, content, append, create_dirs)` — Write content to a file
- `upload_file(local_path, remote_path)` — Upload a file to the remote system
- `download_file(remote_path, local_path)` — Download a file from the remote system

### RCAC Cluster

- `myquota()` — Show storage usage and quota limits
- `storage_paths()` — Get resolved paths for home, scratch, and depot
- `jobinfo(job_id)` — Detailed job information
- `jobcmd(job_id)` — Command submitted for a job
- `jobenv(job_id)` — Environment variables for a job
- `jobscript(job_id)` — Full submission script for a job
- `showpartitions()` — Available partitions and their status
- `average_wait(partition, account)` — Queue wait time statistics

### Slurm

- `sbatch(...)` — Submit a batch job (from script path or inline content)
- `squeue(...)` — View the job queue
- `scancel(...)` — Cancel jobs
- `sacct(...)` — Query job accounting history
- `sinfo(...)` — Cluster and partition status
- `scontrol_show_job(job_id)` — Detailed Slurm job info
- `scontrol_show_node(node)` — Detailed node info
- `slist()` — Slurm accounts and usage (RCAC-specific)
- `sfeatures()` — Node hardware features and constraints (RCAC-specific)

## Development

```bash
uv sync
rcac-mcp -e local
```

Run the test suite:

```bash
pytest
```

## License

MIT
