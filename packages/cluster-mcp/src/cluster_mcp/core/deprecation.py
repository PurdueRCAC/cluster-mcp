# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The names this server had as rcac-mcp, and the window through which they keep working.

Every legacy name still honoured says so once on stderr, naming its replacement and the window, and
never on stdout: stdout carries the stdio transport.

This is the one module of the server that names a legacy environment variable, and the one that
reads a replacement from the environment: every other module asks `env_setting` for it by name.
"""


# Type annotations
from __future__ import annotations
from typing import Final

# Standard libs
import os

# External libs
from cmdkit.logging import Logger

# Public interface
__all__ = ['WINDOW', 'LEGACY_ENV', 'legacy_warning', 'env_setting']

# The deprecation window every legacy-name warning states, and the README states once.
WINDOW: Final[str] = 'deprecated in 0.2.0, removed no earlier than 0.4.0'

# Each environment variable the server reads, and the legacy name honoured in its place.
LEGACY_ENV: Final[dict[str, str]] = {
    'CLUSTER_MCP_SSH_HOST': 'RCAC_SSH_HOST',
    'CLUSTER_MCP_USER_MAP': 'RCAC_USER_MAP',
    'CLUSTER_MCP_INSTRUCTIONS_BUDGET': 'RCAC_INSTRUCTIONS_BUDGET',
}

log = Logger.with_name(__name__)

# The legacy names already warned about in this process.
_warned: set[str] = set()


def legacy_warning(old: str, new: str) -> None:
    """Warn on stderr that `old` is deprecated in favour of `new`, once per process for each `old`."""
    if old in _warned:
        return
    _warned.add(old)
    log.warning(f'{old} is {WINDOW}: use {new} instead')


def ignored_warning(old: str, new: str) -> None:
    """Warn on stderr that `old` is ignored because `new` is set, once per process for each `old`."""
    if old in _warned:
        return
    _warned.add(old)
    log.warning(f'{old} is {WINDOW}, and ignored: {new} is set')


def env_setting(name: str) -> tuple[str | None, str]:
    """The value of environment variable `name`, else of its legacy name, and the variable it came from.

    A non-empty `name` wins; when its legacy name is set too, a warning says the legacy one is
    ignored. Otherwise a non-empty legacy value is returned, with its deprecation warning. An empty
    value counts as unset, and a value is never stripped: a whitespace-only host is a host. With
    neither set, the value is None and the variable is `name`.
    """
    legacy = LEGACY_ENV[name]
    value = os.environ.get(name)
    if value:
        if os.environ.get(legacy):
            ignored_warning(legacy, name)
        return value, name
    value = os.environ.get(legacy)
    if value:
        legacy_warning(legacy, name)
        return value, legacy
    return None, name
