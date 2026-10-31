# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""MCP resources for cluster context and configuration.

Resources provide read-only access to data that can be used as context
for LLM interactions. The core's resource is cluster_context, which
serves the /etc/agents.d markdown the server read once at startup; a
capability brings its own resources, which the server lists after these.

Each core resource is served as `cluster://<name>` and, through the deprecation window, under its
old `rcac://<name>` URI too. Every `rcac://` entry is a copy of its `cluster://` target but for its
URI, derived by `legacy_aliases` rather than written by hand, so it shares the target's handler and
executor flag. A capability that keeps an old URI derives its aliases with the same helper.
"""

# Type annotations
from __future__ import annotations
from typing import Final, Iterable

# External libs
from fastmcp.server.dependencies import get_server

# Internal libs
from cluster_mcp.core.site import site_of

# Public interface
__all__ = ['OPEN_RESOURCES', 'RESOURCE_REGISTRY', 'legacy_aliases']


def legacy_aliases(entries: Iterable[dict]) -> list[dict]:
    """The deprecated `rcac://` alias of each entry: the entry with only its URI's scheme changed.

    An alias runs its target's handler and needs an executor exactly when its target does.
    """
    return [{**entry, 'uri': entry['uri'].replace('cluster://', 'rcac://', 1)} for entry in entries]


# Resource registry for server to register: the core's own entries. Each entry holds the uri, name,
# description and handler, and 'executor': whether the handler runs commands through its request's
# executor.
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


# The deprecated `rcac://` aliases, one per entry above. They are appended before OPEN_RESOURCES is
# computed, so an open target's alias is open too.
RESOURCE_REGISTRY += legacy_aliases(list(RESOURCE_REGISTRY))


# The resources that run nothing, so a read needs no executor: they answer any client that can
# connect, and the delegate middleware lets their reads through without resolving an identity.
# Every entry must say whether it needs an executor; one that does not fails here, at import. Only
# the core's entries are here: a capability's resource always needs an executor, so it is never open.
OPEN_RESOURCES: Final[frozenset[str]] = frozenset(
    entry['uri'] for entry in RESOURCE_REGISTRY if not entry['executor'])
