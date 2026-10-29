# 01 — FastMCP 4.1.4 resources/read path

Installed: `fastmcp 4.1.4`, `mcp 2.3.0`, `mcp_types 2.3.0`. Paths below are relative to
`.venv/lib/python3.14/site-packages/`. Probes are in the session scratchpad (`p1.py`–`p4.py`) and ran
through `tests.harness` (`in_memory`, `read_resource`, `http_client`, `delegate_server`, `mint`)
with an explicit `era=` for each era.

## 1. Dispatch and order

- Wire entry: `fastmcp/server/mixins/mcp_operations.py:301-334` `_on_read_resource`, inside
  `bind_request_context(ctx)` (`:307`, the same binding `_on_call_tool` uses at `:240`), calls
  `self.read_resource(str(uri))` (`:314`).
- `fastmcp/server/server.py:1580-1623` `read_resource`: opens `Context(fastmcp=self)`, builds a
  `MiddlewareContext(message=ReadResourceRequestParams(uri=str(uri)), method="resources/read")` and
  runs `_dispatch_component_middleware` (`:622-639`). Its `call_next` re-enters
  `read_resource(str(context.message.uri), run_middleware=False)`. So **every middleware's
  `on_read_resource` runs before the resource lookup and before the handler**. The lookup comes
  after: prefab synthesis (`:1642`), concrete `_lookup_resource` (`:1648`), then templates.
- Order: `_run_middleware` (`server.py:588-620`) wraps `reversed(self.middleware)`, so
  `self.middleware[0]` is outermost. **Later-added runs inside earlier-added.** Probe p1:
  `['outer>', 'inner>', '<inner', '<outer']`. In `create_mcp_server` (`src/rcac_mcp/server.py:156-161`)
  `ToolErrorMiddleware` is added before the executor middleware, so it wraps the executor middleware
  on reads too. `DereferenceRefsMiddleware` (auto-added, `server.py:519-525`) hooks only
  `on_list_tools` and `on_list_resource_templates` (`middleware/dereference.py:24,33`).
- Per-method hook selection: `middleware/middleware.py:178` (`"resources/read"` → `on_read_resource`).
- `check_resource_access` (`middleware.py:246-253`) is a no-op hook. The **base**
  `on_read_resource` (`:255-261`) calls it and then `call_next`. Its only other caller is
  `FastMCP._check_resource_access` (`server.py:1566-1578`), which only the skills
  directory provider uses (`providers/skills/directory_provider.py:400`, extension discovery).
  **resources/list never calls it.** It goes through `on_list_resources` (`middleware.py:185`). Probe
  p2: a middleware whose `check_resource_access` denies `rcac://storage` still lists both URIs, and
  the read is denied. Overriding `on_read_resource` without calling `super()` skips
  `check_resource_access` entirely. Neither choice changes what resources/list serves.

## 2. ContextVar into a sync handler

`resources/function_resource.py:201-213`: an async fn is awaited in-task. A sync fn goes to
`call_sync_fn_in_threadpool` (`utilities/async_utils.py:26-34`, `anyio.to_thread.run_sync`, which
copies the caller's context). Probe p1 (both eras):

```
rcac://ok  (sync)  -> 'set-by-mw|AnyIO worker thread'
rcac://aok (async) -> 'set-by-mw|MainThread'
VAR in main after reads: None
```

Probe p3: two concurrent reads, each setting the var to its own URI in middleware, held together by
a `threading.Barrier(2)` inside the sync handlers. Result: `['rcac://a saw rcac://a', 'rcac://b saw rcac://b']`
in both eras. The var is per request and does not leak.

## 3. Error surfacing (`mask_error_details`: default False, `settings.py:207`; overridable by env `FASTMCP_MASK_ERROR_DETAILS`; `create_mcp_server` does not pass it)

Client-visible text from `harness.read_resource` (probe p1):

| raised where / what | legacy | modern |
|---|---|---|
| on_read_resource mw: `PermissionError('x')` | `x` | `Internal server error` |
| on_read_resource mw: `RuntimeError('x')` | `x` | `Internal server error` |
| on_read_resource mw: `ResourceError('x')` | `x` | `x` |
| sync handler: `RuntimeError('x')` | `Error reading resource 'rcac://boom': x` | same |
| any of the above, with an outer boundary mw (`except FastMCPError: raise; except Exception as e: raise ResourceError(str(e))`) | `x` (handler case unchanged: prefixed) | `x` (same) |
| unknown URI | `Resource not found: '<uri>'` (-32602) | same |

Mechanics:
- Handler exceptions: `server.py:1650-1681`. A `FastMCPError` is re-raised as-is (so a handler's own
  `ResourceError('x')` reads `x`). Any other exception becomes
  `ResourceError(f"Error reading resource {uri!r}: {e}")`, or the bare prefix when masking is on.
- `_on_read_resource` turns `FastMCPError` into `MCPError` via `to_mcp_error`
  (`exceptions.py:117-144`: `ResourceError` → -32603 with `str(exc)`, NotFound → -32602).
- A non-FastMCP exception from middleware escapes to the SDK. Legacy:
  `mcp/shared/jsonrpc_dispatcher.py:771-778` writes `ErrorData(code=0, message=str(e))`. Modern:
  `mcp/server/runner.py:534-548` writes `INTERNAL_ERROR "Internal server error"`. This is the same
  erasure `ToolErrorMiddleware` exists for on tool calls.

## 4. `get_access_token()` in on_read_resource

`server/dependencies.py:665-692`: method-agnostic. It reads `request.scope["user"]` of the current
HTTP request, falling back to the SDK's auth context var. The read handler binds the same request
context as tool calls (`mcp_operations.py:307` vs `:240`). Probe p3 (`delegate_server` + `serving` +
`http_client(app, mint(...))`, both eras): a recorder inside `AuthExecutorMiddleware` saw
`('read','rcac://context','alice'), ('read','rcac://storage','alice'), ('call','run_command','alice')`.
Over `in_memory` it saw `None`. `context.fastmcp_context.set_state(..., serializable=False)` also
works in on_read_resource (p4, both eras).

## 5. URI form and resolution

- `context.message.uri` is a **`str`** (`mcp_types/_types.py:885-886`, `uri: str`). For a read of
  `rcac://context` it is exactly `'rcac://context'`: no trailing slash, no case change server-side.
- Concrete lookup is an **exact string compare** against `str(resource.uri)`
  (`server/providers/local_provider/local_provider.py:384-388`). Registered keys stringify as
  `'rcac://context'`, `'rcac://storage'`.
- The fastmcp `Client` normalizes before sending: `str(AnyUrl(uri))`
  (`client/mixins/resources.py:233-235, 296-302`). This lowercases only the scheme. Probe p2, server
  side, with `client.read_resource` and the raw `client.session.read_resource`:

```
'RCAC://context'  fastmcp client: OK (sent as 'rcac://context')   raw: Resource not found (mw saw 'RCAC://context')
'rcac://context/' | 'rcac://CONTEXT' | 'Rcac://Context' | '?x=1' | '#f' | 'rcac:context'
'rcac:///context' | 'rcac://context//' | 'rcac://%63ontext' | 'rcac://context.'  -> Resource not found, both paths
```

  The middleware always saw the string that would be looked up. **Only the exact string
  `'rcac://context'` resolves to the context resource.** No other string reaching the server does.
  That string cannot resolve elsewhere, because concrete resources win over templates
  (`server.py:1648-1688`) and the repo registers no templates, providers or transforms.

## 6. Other things that could surprise

- Middleware runs **before** lookup. A delegate refusal for "any URI but `rcac://context`" therefore
  also answers unknown URIs with the refusal, not `Resource not found`, for unmapped or
  identity-less callers.
- `read_resource` is re-entrant with `run_middleware=True` from `ctx.read_resource` / the
  `ResourcesAsTools` transform (`server/context.py:600-609`, `transforms/resources_as_tools.py:155`).
  The repo uses neither, but such a read would run on_read_resource nested inside on_call_tool.
- The repo installs no caching middleware (`middleware/caching.py:522` would cache reads
  across users by URI). There are no templates or `task=` resources, so the template/security path
  (`server.py:1690-1714`) and Docket tasks do not apply.
- R3 "same reason" with no token: `AuthExecutorMiddleware.on_call_tool` passes a token-less call
  through, and the tool then fails at `get_executor()`. A resource handler failing the same way
  reaches the client as `Error reading resource 'rcac://storage': No executor configured. ...`.
  The prefix differs from the tool's text, but it contains `No executor configured`, the string
  `tests/test_no_executor.py:36` matches on.
- Baseline today (p3, HTTP, both eras): an unmapped `ghost` token reads `rcac://context` fine and
  gets the `FunctionTool` error on `rcac://storage`, while its tool call is refused with
  `User 'ghost' is not authorized. Contact administrator to request access.`

## Implications for the design

1. Override `on_read_resource` (not `check_resource_access`) in `SharedExecutorMiddleware` and
   `AuthExecutorMiddleware`. resources/list is unaffected either way, and `on_read_resource` is the
   one hook that wraps the handler, so a `set_executor` there reaches the sync handler (copied
   context, per request, isolated under concurrency).
2. The `ToolErrorMiddleware` read boundary is **required for the modern era**. Without it a
   `PermissionError`/`RuntimeError` refusal reads `Internal server error`. Mirror `on_call_tool`:
   re-raise `FastMCPError`, wrap other `Exception`s as `ResourceError(str(exc))`. Client text is then
   exactly the refusal string in both eras. It does not touch handler errors, which are already
   `ResourceError`s.
3. Exempt `rcac://context` by `str(context.message.uri) == 'rcac://context'`. That compare equals
   FastMCP's own resolution rule, so it neither over- nor under-exempts. Reuse the registry's URI
   constant rather than a second literal.
4. `get_access_token()` behaves identically in the read hook. Extract the token → identity → map →
   `DelegatingExecutor` sequence from `on_call_tool` into a shared helper, so the refusal text cannot
   drift between tools and reads. Decide deliberately whether token-less reads pass through (as
   tool calls do, failing with `No executor configured`) or refuse early.
5. The handler fix stays separate: call the undecorated `storage_paths` function (the
   `FunctionTool` is not callable). A handler failure surfaces prefixed
   `Error reading resource 'rcac://storage': …`, which tests should match by substring.
