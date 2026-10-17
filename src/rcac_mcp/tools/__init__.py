# SPDX-FileCopyrightText: 2025 Purdue University
# SPDX-License-Identifier: MIT

"""MCP tool definitions."""

# Type annotations
from __future__ import annotations
from typing import List, Callable, Any

# Standard libs
import inspect

# External libs
from fastmcp.tools import Tool

# Public interface
__all__ = ['TOOL_REGISTRY', 'mcp_tool']


# Registry of tool functions for us to add to server later
TOOL_REGISTRY: List[Tool] = []


def mcp_tool(func: Callable[..., Any]) -> Tool:
    """Decorator to register MCP tool functions.

    The served description is the full docstring (`Args:`, `Returns:` and `Examples:` included):
    FastMCP 4 otherwise serves only its summary paragraph, and every model reads the description to
    choose a tool. FastMCP still copies each `Args:` line into its property's description.
    """
    tool = Tool.from_function(func, description=inspect.getdoc(func))
    TOOL_REGISTRY.append(tool)
    return tool


# Import tool modules to trigger registration
# These imports must come after TOOL_REGISTRY and mcp_tool are defined
from rcac_mcp.tools import shell  # noqa: E402, F401
from rcac_mcp.tools import filesystem  # noqa: E402, F401
from rcac_mcp.tools import transfer  # noqa: E402, F401
from rcac_mcp.tools import rcac  # noqa: E402, F401
from rcac_mcp.tools import slurm  # noqa: E402, F401
