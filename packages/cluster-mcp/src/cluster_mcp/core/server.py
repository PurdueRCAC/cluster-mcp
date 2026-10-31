# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Create MCP server instance."""


# Type annotations
from __future__ import annotations
from typing import Dict, Iterable, List, Optional, Final, Callable, Awaitable

# Standard libs
from pathlib import Path
import os

# External libs
from fastmcp import FastMCP
from mcp.types import Icon, Request
from starlette.responses import Response, FileResponse

# Internal libs
from cluster_mcp.core.auth import AUTH_MODES
from cluster_mcp.core.capabilities import Loaded, composed, installed
from cluster_mcp.core.instructions import CORE_INSTRUCTIONS
from cluster_mcp.core.middleware import ToolErrorMiddleware
from cluster_mcp.core.tools import CLOSING_TOOLS, CORE_TOOLS
from cluster_mcp.core.resources import RESOURCE_REGISTRY
from cluster_mcp.core.site import DEFAULT_BUDGET, SiteContext, compose, register

# Public interface
__all__ = [
    'base_instructions',
    'create_mcp_server',
]


# Base URL for constructing absolute URLs (icons, etc.)
MCP_BASE_URL = os.environ.get('MCP_BASE_URL', '').rstrip('/')


# Registry for custom routes handled by the server
CUSTOM_ROUTES: Dict[str, Callable[[Request], Awaitable[Response]]] = {}


def custom_route(route: str):
    """Decorator to register custom route handlers."""

    def decorator(func: Callable[[Request], Awaitable[Response]]) -> Callable[[Request], Awaitable[Response]]:
        CUSTOM_ROUTES[route] = func
        return func

    return decorator



# Path to static files directory
STATIC_DIR: Final[Path] = Path(__file__).parent / 'static'
ICON_PATH: Final[Path] = STATIC_DIR / 'purdue-favicon.ico'


ICON_URL = f'{MCP_BASE_URL}/static/purdue-favicon.ico' if MCP_BASE_URL else '/static/purdue-favicon.ico'


# Serve the icon via custom route
@custom_route("/static/purdue-favicon.ico")
async def serve_icon(request: Request) -> FileResponse:
    return FileResponse(ICON_PATH, media_type="image/x-icon")


def base_instructions(capabilities: Iterable[Loaded]) -> str:
    """The served base, never cut: the core's text, then each capability's in composition order.

    Composition order is (order, distribution), so a site overlay such as the RCAC member's sits
    last, directly above the site context `compose` appends. Every text is joined by a blank line.
    """
    texts = [loaded.capability.instructions for loaded in composed(capabilities)]
    return '\n\n'.join((CORE_INSTRUCTIONS, *texts))


def _listed(capabilities: Iterable[Loaded]) -> tuple[Loaded, ...]:
    """`capabilities` in load order, by distribution: the order their tools and resources are listed in."""
    return tuple(sorted(capabilities, key=lambda loaded: (loaded.distribution, loaded.capability.name)))


def _tools_of(capabilities: Iterable[Loaded]) -> list:
    """The tools a server for `capabilities` registers, in listing order.

    The core's tools but the site context tool, then each capability's in load order, then the site
    context tool, which closes the list as the site section closes the instructions.
    """
    opening = [tool for tool in CORE_TOOLS if tool not in CLOSING_TOOLS]
    return [*opening, *(tool for loaded in _listed(capabilities) for tool in loaded.tools), *CLOSING_TOOLS]


def _resources_of(capabilities: Iterable[Loaded]) -> list[dict]:
    """The resource entries a server for `capabilities` registers, in listing order.

    Every `cluster://` entry, the core's then each capability's in load order, then every other
    entry (the deprecated aliases) in the same order.
    """
    entries = [*RESOURCE_REGISTRY,
               *(entry for loaded in _listed(capabilities) for entry in loaded.capability.resources)]
    primary = [entry for entry in entries if entry['uri'].startswith('cluster://')]
    return primary + [entry for entry in entries if not entry['uri'].startswith('cluster://')]


def create_mcp_server(
    auth_mode: Optional[str] = None,
    middlewares: Optional[List] = None,
    *,
    site: SiteContext,
    budget: int = DEFAULT_BUDGET,
    capabilities: Optional[Iterable[Loaded]] = None,
) -> FastMCP:
    """
    Create and configure the MCP server.

    Args:
        auth_mode: Authentication mode ('none', 'jwt', 'oidc').
        middlewares: Optional list of FastMCP Middleware instances to add.
        site: The site context read at startup; the server never reads it again.
        budget: The most characters the composed instructions may take.
        capabilities: The loaded capabilities to serve, in any order; None serves every installed one
            (`installed()`). No flag or environment variable reaches it: installation is the switch.

    Returns:
        Configured FastMCP server instance.
    """
    loaded = installed() if capabilities is None else tuple(capabilities)
    server = FastMCP(
        name='cluster-mcp',
        instructions=compose(base_instructions(loaded), site, budget),
        auth=AUTH_MODES[auth_mode](),
        icons=[
            Icon(
                src=ICON_URL,
                mimeType="image/x-icon",
            ),
        ],
    )

    register(server, site)

    for route, impl in CUSTOM_ROUTES.items():
        server.custom_route(route, methods=['GET'])(impl)

    for tool in _tools_of(loaded):
        server.add_tool(tool)

    # Register resources using the @resource decorator approach
    for resource in _resources_of(loaded):
        server.resource(
            resource['uri'],
            name=resource['name'],
            description=resource['description'],
        )(resource['handler'])

    # The error boundary goes before the caller's middleware: FastMCP runs later middleware inside
    # earlier middleware, so the boundary sees whatever the executor middleware raises.
    server.add_middleware(ToolErrorMiddleware())

    # Add any provided middleware
    if middlewares:
        for middleware in middlewares:
            server.add_middleware(middleware)

    return server
