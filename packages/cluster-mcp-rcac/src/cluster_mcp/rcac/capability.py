# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The RCAC member as a capability: its tools module, its overlay on the served instructions and its
storage resource.

This member's `cluster_mcp.capabilities` entry point names `CAPABILITY`, which the core loads at
startup. Importing this module registers no tool: the core imports the tools module when it loads.

It declares the two site commands its storage resource needs, `findscratch` and `myquota`, which
also mark a cluster as RCAC's: the core withholds the member where either is missing. It does not
declare every command its tools run: a cluster lacking one of the others keeps the rest of the
member, and that tool reports its own missing command when called.
"""

# Internal libs
from cluster_mcp.core.capabilities import Capability
from cluster_mcp.core.resources import legacy_aliases
from cluster_mcp.rcac.instructions import RCAC_INSTRUCTIONS
from cluster_mcp.rcac.resources import STORAGE

# Public interface
__all__ = ['CAPABILITY']


# The site overlay sorts last in the base, directly above the site context. Its storage resource
# keeps its deprecated `rcac://storage` alias, derived as the core derives its own.
CAPABILITY = Capability(name='rcac', order=900, tools='cluster_mcp.rcac.tools', instructions=RCAC_INSTRUCTIONS,
                        resources=(STORAGE, *legacy_aliases((STORAGE,))),
                        commands=('findscratch', 'myquota'))
