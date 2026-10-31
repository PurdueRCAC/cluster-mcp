# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The RCAC member as a capability: its tools module and its overlay on the served instructions.

This member's `cluster_mcp.capabilities` entry point names `CAPABILITY`, which the core loads at
startup. Importing this module registers no tool: the core imports the tools module when it loads.
"""

# Internal libs
from cluster_mcp.core.capabilities import Capability
from cluster_mcp.rcac.instructions import RCAC_INSTRUCTIONS

# Public interface
__all__ = ['CAPABILITY']


# The site overlay sorts last in the base, directly above the site context.
CAPABILITY = Capability(name='rcac', order=900, tools='cluster_mcp.rcac.tools', instructions=RCAC_INSTRUCTIONS)
