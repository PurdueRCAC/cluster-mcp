# 01 — FastMCP 2.14 → 4.1 and mcp 1.26 → 2.3: every API the repo touches

Method: a scratch venv with `fastmcp` 4.1.0 and `mcp` 2.3.0 (source read directly), and a scratch
copy of `3d010ec` re-locked with `fastmcp>=4,<5` and run unmodified, then with each fix below.
Reference reads: `fastmcp/server/server.py`, `server/mixins/{transport,mcp_operations}.py`,
`server/middleware/middleware.py`, `server/context.py`, `tools/{base,function_tool}.py`,
`client/client.py`, `client/transports/{http,sse}.py`, `mcp_types/version.py`; the FastMCP upgrade
guide and changelog (gofastmcp.com, read 2026-10-17).

## Packaging shape

- `fastmcp` 4.1.0 is a meta-package over `fastmcp-slim[client,server]` 4.1.0; the import name is
  still `fastmcp`. `mcp` 2.3.0 depends on a new `mcp-types` 2.3.0 (import `mcp_types`;
  `mcp.types` re-exports it: `mcp.types.Icon is mcp_types.Icon`).
- **The HTTP client is `httpx2`** (import `httpx2`, with `httpcore2`); plain `httpx` leaves the lock.
  `tests/harness.py`'s `import httpx` is the first thing that breaks (collection error).

## Unchanged (verified by running the code, not by reading)

| Surface | Status on 4.1 |
|---|---|
| `FastMCP(name=, instructions=, auth=, icons=)` | same keywords; `instructions` still a property |
| `Tool.from_function(fn)` → `FunctionTool` | same; **still not callable** (`TypeError: 'FunctionTool' object is not callable`); the class moved to `fastmcp.tools.function_tool.FunctionTool`; `.fn` holds the function |
| `server.add_tool`, `server.resource(uri, name=, description=)(fn)`, `server.add_middleware` | same |
| `server.custom_route(path, methods=['GET'])` | same; the icon route answers 200 `image/x-icon` on the http and sse apps |
| `server.http_app()` + `app.router.lifespan_context(app)` | same |
| `server.run(transport='stdio' / 'sse' / 'streamable-http', host=, port=)` | same; **SSE survives** (`Transport = Literal["stdio", "http", "sse", "streamable-http"]`) |
| `Middleware.on_call_tool(context, call_next)`, `MiddlewareContext.fastmcp_context` | same hook; dispatched once per `tools/call` |
| `fastmcp.server.dependencies.get_access_token()` | same; `AccessToken.claims` unchanged (a new `subject` field is unused) |
| `JWTVerifier(public_key=, issuer=, audience=, algorithm=)` at `fastmcp.server.auth.providers.jwt` | same keywords; HS256 with the shared secret as `public_key` verifies; all five mismatch rows still 401 |
| `OIDCProxy(config_url=, client_id=, client_secret=, base_url=)` at `fastmcp.server.auth.oidc_proxy` (re-exported by `fastmcp.server.auth`) | same keywords; `client_secret` is now **optional**, `issuer_url` defaults from `base_url`, `valid_scopes` defaults to `None`; **new and on by default:** `enable_cimd` (fetch client-supplied metadata documents) and `forward_resource` (review finding 5): both passed `False` to keep the 2.x posture |
| `mcp.types.Icon(src=, mimeType=)` | accepted, serializes as before |
| `fastmcp.Client(server)`, `StreamableHttpTransport(url, auth=token, httpx_client_factory=)` | same; the factory must build an `httpx2.AsyncClient` |

Running the whole suite under `-W error::DeprecationWarning` raises nothing from the repo's own
calls.

## Changed — each needs a decision

1. **`get_tools()` is gone** → `list_tools()` returning a list of `Tool`. Only
   `tests/test_registry.py` calls it (internals-bound item 6).
2. **`Context.set_state` is async** (and JSON-only unless `serializable=False`). `middleware.py:153–154`
   calls it bare: the coroutine is never awaited (a `RuntimeWarning`), so the state silently never
   lands. Fix: `await …set_state(key, value, serializable=False)`; `serializable=False` keeps the 2.x
   scope (request-local, not session-wide), which is what a per-call identity wants (§1, §5).
3. **An exception raised by middleware is a masked protocol error.** 2.14 (mcp 1.x's low-level
   handler) turned any exception in the `tools/call` path into `CallToolResult(isError=True,
   text=str(exc))`. 4.1 converts only exceptions from the tool *body* (`ToolError("Error calling tool
   'x': …")`); a `PermissionError`/`RuntimeError` raised in `on_call_tool` reaches the SDK runner and
   the client gets JSON-RPC `-32603 Internal server error` with the reason erased. Probe, same
   two-line middleware on each stack: 2.14 → `result True ["User 'ghost' is not authorized."]`;
   4.1 → `raised MCPError Internal server error`. Seven suite tests go red on it (the unmapped and
   no-identity refusals, the rendezvous control). Fix: an outermost boundary middleware, below.
4. **Tool descriptions are parsed.** FastMCP 4 runs griffe over the docstring: the description
   becomes the summary paragraph only (`Args:`/`Returns:`/`Examples:` dropped), and each `Args:`
   line moves into the property's `description` in the input schema. All 23 descriptions change
   (§9: docstrings are surface). Fix: `Tool.from_function(func, description=inspect.getdoc(func))`
   restores the exact 2.x description; the per-property descriptions stay (additive metadata).
5. **Generated schema metadata.** Input schemas gain `"additionalProperties": false` (validation
   is unchanged: both stacks already reject an unknown argument with `unexpected_keyword_argument`,
   and neither coerces `5` to a string); output schemas of `list_directory` and `storage_paths`
   inline their `$defs` (`dereference_schemas=True`); `_meta` key `_fastmcp` becomes `fastmcp`.
   Argument names, required lists, types and defaults are identical for all 23 tools.

## The boundary middleware (decision for item 3)

A `ToolErrorMiddleware` in `middleware.py`, added **first** by `create_mcp_server` (FastMCP 4 wraps
middleware in reverse, so the first added is outermost: `for mw in reversed(self.middleware)`):
`on_call_tool` returns `await call_next(context)`, re-raises `FastMCPError` untouched, and
re-raises any other `Exception` (an `MCPError` too: on 2.x it was an error result, and the foreman
ruled parity) as `ToolError(str(exc)) from exc`; `BaseException` (cancellation) passes through. That reproduces the 2.x wire shape
exactly (`isError: true`, text `str(exc)`), for the executor middlewares and any test middleware
alike, without changing what §5 says they raise (`PermissionError`, `RuntimeError`) or moving a
mutation anchor. Prototype: with it, 295/296 pass (the remaining one is `get_tools`).

Rejected: raising `ToolError` inside each executor middleware (rewrites §5's documented exception
types, moves anchored lines, and leaves the next middleware to rediscover the trap); FastMCP's
`ErrorHandlingMiddleware` (it transforms to `MCPError` with a code: still a protocol error).

## Sources

FastMCP source 4.1.0 (scratch venv); changelog entries "Run FastMCP middleware for every inbound
message", "Migrate to MCP SDK v2.0.0b2 (httpx2)", "Use issuer_url for OAuth issuer identity"
(v4.0.0, 2026-08-31); upgrade guide (decorators return the function; `get_*` → `list_*`;
async `set_state`).
