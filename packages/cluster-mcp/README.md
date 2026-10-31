# cluster-mcp

An MCP server for HPC clusters. It exposes shell execution, filesystem access, Slurm job management
and site-specific tooling to AI agents over the Model Context Protocol.

This is the core member of the cluster-mcp workspace: the server, the CLI (`cluster-mcp`), the
execution backends and the generic tools, importable as `cluster_mcp.core`. A default install also
carries the Slurm member (`cluster-mcp-slurm`) and the Purdue RCAC member (`cluster-mcp-rcac`).
Install it from git with uv:

```
uvx --from "git+https://github.com/PurdueRCAC/cluster-mcp#subdirectory=packages/cluster-mcp" cluster-mcp --help
```

The full documentation is the repository's README: https://github.com/PurdueRCAC/cluster-mcp
