# cluster-mcp

An MCP server for HPC clusters. It exposes shell execution, filesystem access, Slurm job management
and site-specific tooling to AI agents over the Model Context Protocol.

This is the core member of the cluster-mcp workspace: the server, the CLI (`cluster-mcp`), the
execution backends and the generic tools, importable as `cluster_mcp.core`. Installed alone it
serves the core's tools only. The capabilities are its extras: `[slurm]` installs the Slurm member
(`cluster-mcp-slurm`) and `[rcac]` the Purdue RCAC member (`cluster-mcp-rcac`), which goes with
`[slurm]`. Install it from git with uv, naming the extras your cluster needs:

```
uvx --from 'cluster-mcp[slurm,rcac] @ git+https://github.com/PurdueRCAC/cluster-mcp#subdirectory=packages/cluster-mcp' cluster-mcp --help
```

The full documentation is the repository's README: https://github.com/PurdueRCAC/cluster-mcp
