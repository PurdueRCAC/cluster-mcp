# SPDX-FileCopyrightText: 2025 Purdue University
# SPDX-License-Identifier: MIT

"""Middleware for authentication and executor setup."""

# Type annotations
from __future__ import annotations
from typing import Any, Awaitable, Callable, Dict, Optional

# Standard libs
import os

# External libs
from fastmcp.exceptions import DisabledError, FastMCPError, NotFoundError, ResourceError, ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_access_token

# Internal libs
from rcac_mcp.context import set_executor
from rcac_mcp.executor import Executor
from rcac_mcp.executor.delegate import DelegatingExecutor, load_user_map
from rcac_mcp.resources import OPEN_RESOURCES

# Public interface
__all__ = ['AuthExecutorMiddleware', 'SharedExecutorMiddleware', 'ToolErrorMiddleware']


async def _bounded(context: MiddlewareContext, call_next: Callable[[MiddlewareContext], Awaitable[Any]],
                   error: type[FastMCPError], passes: tuple[type[Exception], ...]) -> Any:
    """
    Run the rest of the chain; re-raise a failure in it as `error` with exactly its text.

    An exception of a type in `passes` propagates untouched. Any other `Exception` is raised as
    `error(str(exc))`, chained to the original; a `BaseException` that is not an `Exception`
    (cancellation) propagates.
    """
    try:
        return await call_next(context)
    except passes:
        raise
    except Exception as exc:
        raise error(str(exc)) from exc


class ToolErrorMiddleware(Middleware):
    """
    Turn an exception raised around a tool call or a resource read into an error carrying its reason.

    FastMCP 4 converts only exceptions raised in a tool's or a resource handler's body into an error
    the client reads; one raised by middleware (an unmapped identity's PermissionError, a token
    without an identity claim's RuntimeError, an MCPError) reaches the client as a masked protocol
    error, its reason erased. This middleware restores the reason: a tool call gets an error result,
    and a resource read an error, whose text is exactly `str(exc)`, with no type name and no
    traceback. A FastMCPError passes through untouched, since FastMCP already reports it with its
    text; so do the NotFoundError and DisabledError FastMCP raises for a resource it does not serve,
    which reach the client as the protocol's own not-found error. Only `Exception` is caught, so
    cancellation and other `BaseException`s propagate.

    `create_mcp_server` adds it before any middleware the caller passes, and FastMCP runs middleware
    added later inside middleware added earlier, so it wraps the executor middleware and anything
    after it and sees whatever they raise. It sets nothing and always returns the rest of the chain.
    """

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Run the rest of the chain; re-raise a failure in it as a ToolError with the same text."""
        return await _bounded(context, call_next, ToolError, (FastMCPError,))

    async def on_read_resource(self, context: MiddlewareContext, call_next):
        """Run the rest of the chain; re-raise a failure in it as a ResourceError with the same text."""
        return await _bounded(context, call_next, ResourceError, (FastMCPError, NotFoundError, DisabledError))


class SharedExecutorMiddleware(Middleware):
    """
    Middleware that sets a shared executor for all requests.

    Used for SSH and local execution modes where a single executor
    is shared across all requests. It sets the executor in each tool call's and each resource
    read's own context, never at construction, so a request it did not see holds none.
    """

    _executor: Executor

    def __init__(self, executor: Executor) -> None:
        """
        Initialize the middleware.

        Args:
            executor: The shared executor instance.
        """
        super().__init__()
        self._executor = executor

    def _install(self) -> None:
        """
        Set the shared executor in the current request's context.

        ContextVars are task-local, so the executor is set in each request's own async context,
        and a sync handler reads the copy of that context its worker thread runs in.
        """
        set_executor(self._executor)

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Set the shared executor for this tool call, then run the rest of the chain."""
        self._install()
        return await call_next(context)

    async def on_read_resource(self, context: MiddlewareContext, call_next):
        """Set the shared executor for this resource read, then run the rest of the chain."""
        self._install()
        return await call_next(context)


class AuthExecutorMiddleware(Middleware):
    """
    Middleware that extracts user identity from auth context and sets up
    a DelegatingExecutor for the request.

    For authenticated requests (JWT or OIDC), this middleware:
    1. Extracts the identity from token claims ('sub' for JWT, 'email' for OIDC)
    2. Maps the identity to a local user via the user map file
    3. Creates a DelegatingExecutor for that user
    4. Sets it as the active executor for the request

    The identity is extracted in order of preference:
    - 'sub' claim (JWT subject, most common)
    - 'email' claim (OIDC, some providers)
    - 'preferred_username' claim (some OIDC providers)
    """

    _user_map: Dict[str, str]
    _auth_mode: str

    def __init__(self, auth_mode: str, user_map_path: Optional[str] = None) -> None:
        """
        Initialize the middleware.

        Args:
            auth_mode: The authentication mode ('jwt' or 'oidc').
            user_map_path: Path to the user mapping file. If None, reads from
                          RCAC_USER_MAP environment variable.
        """
        super().__init__()
        self._auth_mode = auth_mode

        # Load user map
        user_map_path = user_map_path or os.environ.get('RCAC_USER_MAP')
        if not user_map_path:
            raise ValueError(
                'User map path required: provide user_map_path or set RCAC_USER_MAP'
            )
        self._user_map = load_user_map(user_map_path)

    def _extract_identity(self, claims: dict) -> Optional[str]:
        """
        Extract user identity from token claims.

        Tries claims in order of preference:
        1. 'sub' - Standard JWT subject claim
        2. 'email' - Common in OIDC
        3. 'preferred_username' - Some OIDC providers

        Args:
            claims: The token claims dictionary.

        Returns:
            The identity string, or None if no suitable claim found.
        """
        # Try claims in order of preference
        for claim in ('sub', 'email', 'preferred_username'):
            if claim in claims and claims[claim]:
                return str(claims[claim])
        return None

    async def _install(self, context: MiddlewareContext) -> None:
        """
        Set up the executor for the current request based on the authenticated user.

        A request with no access token is let through with nothing set, so whatever needs an
        executor fails at `get_executor()`; a token naming no identity, or an identity absent from
        the user map, is refused here, before the handler runs. Tool calls and resource reads are
        resolved and refused by this one path, so they cannot drift apart.
        """
        # Get access token from auth context
        access_token = get_access_token()

        if access_token is None:
            # No auth - this shouldn't happen in delegate mode
            # but let the request proceed (will fail at executor access)
            return

        # Extract identity from claims
        identity = self._extract_identity(access_token.claims)
        if identity is None:
            raise RuntimeError(
                'Could not extract user identity from token claims. '
                'Token must contain sub, email, or preferred_username claim.'
            )

        # Check if identity is in user map
        if identity not in self._user_map:
            raise PermissionError(
                f'User {identity!r} is not authorized. '
                'Contact administrator to request access.'
            )

        # Create delegating executor for this user
        executor = DelegatingExecutor(identity, self._user_map)
        set_executor(executor)

        # Store identity in request-scoped context state for logging/debugging. The setter is
        # async; request scope (serializable=False) keeps a per-user value out of the session store.
        await context.fastmcp_context.set_state('rcac_user', identity, serializable=False)
        await context.fastmcp_context.set_state('rcac_local_user', executor.local_user, serializable=False)

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """
        Set up executor for tool calls based on authenticated user.

        This hook runs before each tool invocation, ensuring the executor
        is configured for the authenticated user.
        """
        await self._install(context)
        return await call_next(context)

    async def on_read_resource(self, context: MiddlewareContext, call_next):
        """
        Set up executor for resource reads based on authenticated user, as for a tool call.

        A read of a resource in OPEN_RESOURCES runs nothing and answers any client that can connect,
        so it is let through untouched; every other read is resolved, and refused, exactly as a tool
        call from the same request is.
        """
        if context.message.uri not in OPEN_RESOURCES:
            await self._install(context)
        return await call_next(context)
