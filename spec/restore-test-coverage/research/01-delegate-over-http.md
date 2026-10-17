# 01 — Driving delegate mode through the public MCP surface with real bearer tokens

**Question.** Delegate mode reads identity from `get_access_token()` inside
`AuthExecutorMiddleware.on_call_tool`. The in-memory `fastmcp.Client(server)` carries no HTTP auth,
so that lookup returns `None`. How do tests present a real JWT to the real verifier and reach the
middleware, without root, a port, or patching FastMCP?

**Sources read** (installed `.venv`, fastmcp 2.14.4, mcp 1.26.0, httpx 0.28.1, starlette 0.52.1):
`fastmcp/server/dependencies.py` (`get_access_token`), `fastmcp/client/transports.py`
(`StreamableHttpTransport`), `fastmcp/server/server.py` (`http_app`, `_apply_middleware`),
`fastmcp/server/auth/providers/jwt.py` (`JWTVerifier.load_access_token`),
`mcp/client/streamable_http.py`, `mcp/server/lowlevel/server.py`.

## How a claim reaches the middleware

1. `server.http_app()` builds a Starlette app with FastMCP's bearer-auth middleware in front of the
   streamable-HTTP endpoint (`/mcp`). With `auth=JWTVerifier(...)` (what `create_mcp_server('jwt')`
   installs via `AUTH_MODES['jwt']` → `create_jwt_auth()`), a request without a valid token gets a
   401 before any MCP message is processed.
2. A valid token becomes `AuthenticatedUser(access_token)` in the ASGI scope; `JWTVerifier` puts the
   full decoded payload in `AccessToken.claims`.
3. `get_access_token()` first reads `get_http_request().scope['user']` (the per-message request, set
   by the low-level server's request context), then falls back to the SDK's `auth_context_var`. Over
   the in-memory transport both are absent, so it returns `None`.
4. `AuthExecutorMiddleware._extract_identity(access_token.claims)` then sees exactly the claims the
   test minted.

## Options evaluated

| Route | Verdict |
|---|---|
| **In-process ASGI**: `app = server.http_app()`; `async with app.router.lifespan_context(app)`; `fastmcp.Client(StreamableHttpTransport('http://t/mcp', auth=<token>, httpx_client_factory=f))` where `f(...)` returns `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t', headers=..., auth=...)` | **Chosen.** Real verifier, real middleware chain, real per-request task, real bearer header. No socket, no port, no subprocess, so it is a `unit` test under the marker's own definition. |
| Real uvicorn on a random localhost port | Rejected. A bound socket and a server thread or process: a network-shaped test, slower, flaky on port reuse, and it would need the network guard (brief 03) relaxed. Adds nothing the ASGI route lacks. |
| Monkeypatch `get_access_token` or set `auth_context_var` | Rejected. It skips the verifier, which R9 must exercise, and binds to FastMCP internals that `stack-upgrade` replaces. |
| Call `AuthExecutorMiddleware.on_call_tool` with a stub context | Rejected as the primary route (it bypasses the tool and the client), kept as the fallback if FastMCP 4 removes the factory hook. |

**Prototype** (`prototypes/isolation_over_http.py`, `prototypes/tokens_over_http.py`), executed
2026-10-16: both the default stateful app and `stateless_http=True, json_response=True` work through
`ASGITransport` (SSE responses complete because each POST response ends; the client's DELETE on
close and the lifespan shutdown both return). Results:

- `sub=alice` → `sudo -n -H -u ualice /bin/zsh -c id -un` recorded; `sub=bob` → `-u ubob`.
- A token with no `sub` (only `iss/aud/iat/exp`) is accepted by the verifier and reaches the
  middleware, which raises the "Could not extract user identity" `RuntimeError`; the client gets an
  error result (`is_error=True`, message text intact), and nothing is launched.
- `email`-only and `preferred_username`-only tokens (minted with PyJWT, same
  `ISSUER`/`AUDIENCE`/`ALGORITHM`/secret) map through the user map as expected.
- Garbage token, wrong issuer, wrong audience, wrong secret, `HS512`, and `exp` 60 s in the past
  each → HTTP 401 (`httpx.HTTPStatusError` from the client), and no launch.
- A token printed by `bin/sandbox.sh env JWT_SECRET=<32 chars> <venv>/bin/rcac-mcp --generate-token
  --sub alice` is accepted and runs as `ualice`.

`JWTVerifier` checks `exp` with no leeway (`exp < time.time()` rejects) and restricts the algorithm
to the configured one (authlib `JsonWebToken([algorithm])`); a token without `exp` is accepted, which
does not matter here because `generate_token` always sets it.

## Recommendation

- One harness module (`tests/harness.py`) owns the route: `serving(server)` (an async context
  manager running the app's lifespan), `http_client(app, token)`, `in_memory(server)`, `mint(...)`
  (PyJWT with the `token.py` constants and overridable `iss/aud/alg/key/exp`, plus arbitrary claims),
  and `call(...)` returning a normalized outcome: `is_error`, `text`, and `status` (401 on HTTP
  rejection).
- Use the default stateful app: it is what `mcp.run(transport='streamable-http')` serves.
- Build a fresh server per test. Never reuse one across tests or mutate its middleware list.
- `httpx` is imported directly by the harness but is only a transitive dependency (through
  `fastmcp`/`mcp`). Record it as a risk rather than add a dev dependency: the harness is the one
  module `stack-upgrade` rewrites anyway.
