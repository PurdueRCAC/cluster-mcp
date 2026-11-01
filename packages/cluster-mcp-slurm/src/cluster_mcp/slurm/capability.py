# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The Slurm member as a capability: its tools module and its part of the served instructions.

This member's `cluster_mcp.capabilities` entry point names `CAPABILITY`, which the core loads at
startup. Importing this module registers no tool: the core imports the tools module when it loads.
"""

# Internal libs
from cluster_mcp.core.capabilities import Capability
from cluster_mcp.slurm.instructions import SLURM_INSTRUCTIONS

# Public interface
__all__ = ['CAPABILITY']


# The scheduler's text comes early in the base, before any site overlay.
CAPABILITY = Capability(name='slurm', order=100, tools='cluster_mcp.slurm.tools', instructions=SLURM_INSTRUCTIONS)
