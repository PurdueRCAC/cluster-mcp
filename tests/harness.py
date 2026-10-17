# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""Drive the server through its public MCP surface: the only test module that imports FastMCP, mcp or httpx.

Every test that calls a tool goes through this module, so the FastMCP 2.x → 4.x and mcp 1.x → 2.x
move (the `stack-upgrade` seed) rewrites this file and leaves the contract tests alone. It relies on
these FastMCP and mcp internals: `FastMCP.http_app()` and its router lifespan, the
`StreamableHttpTransport(httpx_client_factory=...)` hook, `fastmcp.Client` over a server object, the
`fastmcp.server.middleware.Middleware.on_call_tool` hook that `Rendezvous` implements, FastMCP
running middleware added later inside middleware added earlier (the builders' `extra` relies on it),
and the import path of `JWTVerifier`, re-exported for the test that checks what `create_jwt_auth()`
returns.
`test_hygiene.py` fails on a FastMCP, mcp or httpx import in any other test module.

Delegate mode is reached over an in-process ASGI route: a real bearer token goes through the real
`JWTVerifier` and `AuthExecutorMiddleware`, with no socket and no port. Shared mode and tokenless
calls use the in-memory client.

Two rules keep a test honest:

- **Build inside the loop.** Every server is built inside the coroutine handed to `drive`; the
  builders raise otherwise. `drive` lets `asyncio.run` copy the main context, as production's
  `MCPServerApp.run()` builds and serves in one context, so anything a construction sets in the
  context reaches the request tasks exactly as it would in production.
- **The fence.** `serving`, `in_memory`, `http_client` and `call_http` raise unless
  `subprocess.Popen` is the unit guard's refuser or the `launches` recorder, so no in-process server
  call can reach a real `sudo`, in a unit or an integration test.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import subprocess
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Coroutine, TypeVar

import httpx
import jwt
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.middleware import Middleware, MiddlewareContext

from rcac_mcp.executor.base import CommandResult, Executor
from rcac_mcp.middleware import AuthExecutorMiddleware, SharedExecutorMiddleware
from rcac_mcp.server import create_mcp_server
from rcac_mcp.token import ALGORITHM, AUDIENCE, ISSUER

__all__ = ['Outcome', 'drive', 'serving', 'http_client', 'in_memory', 'call', 'call_http', 'mint',
           'user_map', 'RecordingExecutor', 'Rendezvous', 'delegate_server', 'shared_server',
           'bare_server', 'JWTVerifier']

T = TypeVar('T')

BASE_URL = 'http://test'


@dataclass(frozen=True)
class Outcome:
    """What the client saw: an error flag, the joined text content, and the HTTP status on rejection."""

    is_error: bool
    text: str
    status: int | None = None


def drive(coro: Coroutine[Any, Any, T], timeout: float = 30) -> T:
    """Run `coro` to completion in a fresh event loop that copies the main context."""
    return asyncio.run(asyncio.wait_for(coro, timeout))


def _require_fence(verb: str) -> None:
    if not getattr(subprocess.Popen, 'test_fence', False):
        raise RuntimeError(
            f'harness fence: {verb} needs subprocess.Popen to be the unit guard or the launches '
            'recorder; request the `launches` fixture (or mark the test unit) before calling a server')


def _require_running_loop(builder: str) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        raise RuntimeError(
            f'{builder}: build servers inside the coroutine handed to harness.drive, '
            'where production builds and serves them') from None


@asynccontextmanager
async def _serving(server: FastMCP) -> AsyncIterator[Any]:
    app = server.http_app()
    async with app.router.lifespan_context(app):
        yield app


def serving(server: FastMCP) -> Any:
    """Serve `server`'s default stateful streamable-HTTP app (what `mcp.run` serves) for a block."""
    _require_fence('serving')
    return _serving(server)


def http_client(app: Any, token: str | None) -> Client:
    """A client that reaches `app` over in-process ASGI, presenting `token` as a bearer token."""
    _require_fence('http_client')

    def factory(headers: Any = None, timeout: Any = None, auth: Any = None, **_: Any) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {} if timeout is None else {'timeout': timeout}
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL,
                                 headers=headers, auth=auth, follow_redirects=True, **kwargs)

    return Client(StreamableHttpTransport(f'{BASE_URL}/mcp', auth=token, httpx_client_factory=factory))


def in_memory(server: FastMCP) -> Client:
    """A client wired straight to `server`: no HTTP, so no access token reaches the middleware."""
    _require_fence('in_memory')
    return Client(server)


async def call(client: Client, tool: str, args: dict[str, Any]) -> Outcome:
    """Call `tool` on a connected client and normalize what came back."""
    result = await client.call_tool(tool, args, raise_on_error=False)
    return Outcome(result.is_error, ''.join(getattr(part, 'text', '') for part in result.content))


async def call_http(app: Any, token: str | None, tool: str, args: dict[str, Any]) -> Outcome:
    """Connect and call in one verb; an HTTP rejection becomes `Outcome(True, '', status)`.

    The verifier's 401 surfaces when the client connects, not in `call_tool`, so both are wrapped.
    """
    _require_fence('call_http')
    try:
        async with http_client(app, token) as client:
            return await call(client, tool, args)
    except httpx.HTTPStatusError as exc:
        return Outcome(True, '', exc.response.status_code)


def mint(secret: str, *, iss: str = ISSUER, aud: str = AUDIENCE, alg: str = ALGORITHM, exp_in: float = 300,
         **claims: Any) -> str:
    """A JWT carrying exactly `claims` plus the registered ones; no implicit `sub`."""
    now = dt.datetime.now(dt.timezone.utc)
    payload = {'iss': iss, 'aud': aud, 'iat': now, 'exp': now + dt.timedelta(seconds=exp_in), **claims}
    return jwt.encode(payload, secret, algorithm=alg)


def user_map(tmp_path: Path, text: str) -> str:
    """Write a user-map file under `tmp_path` and return its path."""
    path = tmp_path / 'user_map'
    path.write_text(text)
    return str(path)


@dataclass
class RecordingExecutor:
    """An `Executor` that records every call and answers `<name>|<command>` unless given a responder."""

    name: str
    responder: Callable[[str], str] | None = None
    calls: list[tuple[Any, ...]] = field(default_factory=list)

    @property
    def hostname(self) -> str:
        return f'{self.name}.invalid'

    def run(self, command: str, cwd: str | None = None, timeout: float | None = None) -> CommandResult:
        self.calls.append(('run', command, cwd, timeout))
        stdout = self.responder(command) if self.responder else f'{self.name}|{command}'
        return CommandResult(stdout=stdout, stderr='', exit_code=0, hostname=self.hostname)

    def put(self, local_path: str, remote_path: str) -> None:
        self.calls.append(('put', local_path, remote_path))

    def get(self, remote_path: str, local_path: str) -> None:
        self.calls.append(('get', remote_path, local_path))

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def __enter__(self) -> RecordingExecutor:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class Rendezvous(Middleware):
    """Hold each tool call until `parties` calls are in flight together, then let them all proceed.

    Added after the executor middleware, it sits inside it (FastMCP applies middleware in reverse),
    so every call has set its executor before any call's tool body runs. Without it, sync tools
    never yield and two "concurrent" calls run one after the other, which a module global survives.
    """

    def __init__(self, parties: int, timeout: float = 5.0) -> None:
        super().__init__()
        self.timeout = timeout
        self._barrier = asyncio.Barrier(parties)

    async def on_call_tool(self, context: MiddlewareContext, call_next: Callable[..., Awaitable[Any]]) -> Any:
        try:
            async with asyncio.timeout(self.timeout):
                await self._barrier.wait()
        except TimeoutError:
            raise RuntimeError('rendezvous: calls were never in flight together') from None
        return await call_next(context)


def delegate_server(map_path: str, *extra: Middleware) -> FastMCP:
    """A `jwt` server with `AuthExecutorMiddleware` over `map_path`; the caller sets `JWT_SECRET`.

    `extra` middleware (a `Rendezvous`, say) is added after the executor middleware, so it runs
    inside it; the same holds for the other builders.
    """
    _require_running_loop('delegate_server')
    return create_mcp_server('jwt', middlewares=[AuthExecutorMiddleware('jwt', map_path), *extra])


def shared_server(executor: Executor, *extra: Middleware) -> FastMCP:
    """An unauthenticated server whose `SharedExecutorMiddleware` installs `executor` per call."""
    _require_running_loop('shared_server')
    return create_mcp_server('none', middlewares=[SharedExecutorMiddleware(executor), *extra])


def bare_server(*extra: Middleware) -> FastMCP:
    """An unauthenticated server with no executor middleware at all."""
    _require_running_loop('bare_server')
    return create_mcp_server('none', middlewares=list(extra))
