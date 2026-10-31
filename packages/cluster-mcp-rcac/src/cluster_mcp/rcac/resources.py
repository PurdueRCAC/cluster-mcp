# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The RCAC member's resource: the user's resolved storage paths, `cluster://storage`.

The handler and the `storage_paths` tool both call the undecorated `resolve_storage_paths()`, on
the executor of the request that read it. Importing this module registers no tool.
"""

# Public interface
__all__ = ['STORAGE']


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


# The storage summary runs commands through its request's executor, so it is never open.
STORAGE = {
    'uri': 'cluster://storage',
    'name': 'storage_paths',
    'description': "User's resolved storage paths for home, scratch, and depot spaces",
    'handler': _storage_paths_resource,
    'executor': True,
}
