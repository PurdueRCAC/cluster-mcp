# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The generic core of the served instructions: the core's own tools and its context resource.

The served base is this text, then each loaded capability's (`server.base_instructions` joins
them). It names no site and no tool a capability registers. This module imports nothing, so any
module can import it without a cycle.
"""

CORE_INSTRUCTIONS = """\
cluster-mcp: tools for working on an HPC cluster. Prefer a dedicated tool
below to run_command when one fits. The site context section after this one
carries the cluster's own rules; follow them.

Shell and files:
- run_command: Execute a shell command
- list_directory: List a directory
- read_file: Read a file
- write_file: Write a file
- upload_file: Copy a file to the cluster
- download_file: Copy a file from the cluster

Site:
- cluster_context: The cluster's rules from /etc/agents.d, in full

Resources: cluster://context (the site context in full)."""
