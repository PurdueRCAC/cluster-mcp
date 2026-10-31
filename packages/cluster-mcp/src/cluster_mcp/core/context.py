# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Context management for request-scoped state."""

# Type annotations
from __future__ import annotations
from typing import Optional

# Standard libs
from contextvars import ContextVar

# Internal libs
from cluster_mcp.core.executor import Executor

# Public interface
__all__ = ['executor_var', 'get_executor', 'set_executor']


# Context variable for the current executor
executor_var: ContextVar[Optional[Executor]] = ContextVar('executor', default=None)


def get_executor() -> Executor:
    """
    Get the current executor from context.

    Returns:
        The executor for the current request/session.

    Raises:
        RuntimeError: If no executor has been set.
    """
    executor = executor_var.get()
    if executor is None:
        raise RuntimeError('No executor configured. Set executor via set_executor() first.')
    return executor


def set_executor(executor: Executor) -> None:
    """
    Set the executor for the current context.

    Args:
        executor: The executor to use for command execution.
    """
    executor_var.set(executor)
