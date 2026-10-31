# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The RCAC member's overlay on the served instructions: every tool this member registers.

The overlay is labelled RCAC-specific on its first line and comes last in the base, directly above
the site context, by its capability's order. This module imports nothing. The member's capability
(`capability.py`) carries the text to the core.
"""

RCAC_INSTRUCTIONS = """\
RCAC-specific tools:
- storage_paths: Resolve home, scratch and depot paths
- myquota: Storage spaces, usage and quotas
- jobinfo: Detailed job information
- jobcmd: The command a job was submitted with
- jobenv: A job's environment variables
- jobscript: A job's submission script
- showpartitions: Partitions and their status
- average_wait: Queue wait time statistics
- slist: Slurm accounts and usage
- sfeatures: Node features and constraints

Resources: cluster://storage (what storage_paths returns)."""
