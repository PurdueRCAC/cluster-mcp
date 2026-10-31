# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""MCP resources for cluster context and configuration.

Resources provide read-only access to data that can be used as context
for LLM interactions. The primary resource is cluster_context, which
serves the /etc/agents.d markdown the server read once at startup.

Each resource is served as `cluster://<name>` and, through the deprecation window, under its old
`rcac://<name>` URI too. Every `rcac://` entry is a copy of its `cluster://` target but for its URI,
derived below rather than written by hand, so it shares the target's handler and executor flag.
"""

# Type annotations
from __future__ import annotations
from typing import Final

# External libs
from fastmcp.server.dependencies import get_server

# Internal libs
from cluster_mcp.core.site import site_of

# Public interface
__all__ = ['OPEN_RESOURCES', 'RESOURCE_REGISTRY']


# Resource registry for server to register. Each entry holds the uri, name, description and
# handler, and 'executor': whether the handler runs commands through its request's executor.
RESOURCE_REGISTRY = []


def _cluster_context_resource() -> str:
    """
    The site context read from /etc/agents.d when the server started.

    Every `*.md` file directly in /etc/agents.d but the assembled `AGENTS.md`, each under a
    `<!-- Source: name.md -->` header, in byte order of their names: exactly what the
    `cluster_context` tool returns. Nothing is read or run here, so the read needs no executor.

    Returns:
        The site context as Markdown, an empty string when the site publishes no rules, or the
        one-line reason the files could not be read.
    """
    return site_of(get_server()).text


# Register the resource
RESOURCE_REGISTRY.append({
    'uri': 'cluster://context',
    'name': 'cluster_context',
    'description': 'The site context read from /etc/agents.d at startup: every *.md file but AGENTS.md',
    'handler': _cluster_context_resource,
    'executor': False,
})


def _storage_paths_resource() -> str:
    """
    User's resolved storage paths.

    Returns the actual filesystem paths for all storage spaces the user
    has access to. This provides immediate context about where data can
    be read and written.

    Returns:
        Formatted text showing home, scratch, and depot paths with usage.
    """
    # Imported here, so importing this module does not register the tools.
    from cluster_mcp.rcac.tools import resolve_storage_paths

    paths = resolve_storage_paths()

    lines = [
        'User Storage Paths:',
        '',
        f'Home: {paths.home.path}',
        f'  Usage: {paths.home.size} / {paths.home.limit} ({paths.home.usage_percent})',
        '',
        f'Scratch: {paths.scratch.path}',
        f'  Usage: {paths.scratch.size} / {paths.scratch.limit} ({paths.scratch.usage_percent})',
        '',
        f'Depot Spaces ({len(paths.depots)} available):',
    ]

    for depot in paths.depots:
        lines.append(f'  - {depot.path}')
        lines.append(f'    Usage: {depot.size} / {depot.limit} ({depot.usage_percent})')

    return '\n'.join(lines)


RESOURCE_REGISTRY.append({
    'uri': 'cluster://storage',
    'name': 'storage_paths',
    'description': "User's resolved storage paths for home, scratch, and depot spaces",
    'handler': _storage_paths_resource,
    'executor': True,
})


# The deprecated `rcac://` aliases, one per entry above: each is its target with only the URI
# changed, so it runs the same handler and needs an executor exactly when its target does. They are
# appended before OPEN_RESOURCES is computed, so an open target's alias is open too.
RESOURCE_REGISTRY += [{**entry, 'uri': entry['uri'].replace('cluster://', 'rcac://', 1)}
                      for entry in list(RESOURCE_REGISTRY)]


# The resources that run nothing, so a read needs no executor: they answer any client that can
# connect, and the delegate middleware lets their reads through without resolving an identity.
# Every entry must say whether it needs an executor; one that does not fails here, at import.
OPEN_RESOURCES: Final[frozenset[str]] = frozenset(
    entry['uri'] for entry in RESOURCE_REGISTRY if not entry['executor'])
