# 03 — The ContextVar executor contract under FastMCP 4

Question: FastMCP 4.0 "runs middleware for every inbound message" and serves a stateless era.
Does that move where or how often `set_executor()` runs, and does §1 isolation still hold under
concurrency?

## Where `on_call_tool` runs

`Middleware._dispatch_handler` (4.1) switches on `context.method`: `tools/call` →
`on_call_tool`; `initialize` → `on_initialize`; `server/discover` → `on_discover`; and so on, with
`on_request`/`on_message` wrapping every message. "Every inbound message" means `on_message` and
`on_request` now see the lifecycle and discover traffic too; the **typed** hook `on_call_tool`
still fires only for `tools/call`, and once per call. Probe (an `on_call_tool` counter on a shared
server over the ASGI route, two calls): legacy era → 2, modern era → 2. Our two executor
middlewares define only `on_call_tool`, so they set the executor exactly where §1 says: per tool
call, never at construction or per connection.

## Where the tool body runs

`FunctionTool` runs a sync function through `call_sync_fn_in_threadpool` →
`anyio.to_thread.run_sync`, which propagates `contextvars` into the worker thread (FastMCP's own
docstring says so, and the isolation tests prove it: the executor set in middleware is the one the
tool reads). So in 4.x every sync tool runs on a worker thread with a *copy* of the request's
context. Two consequences:

- Isolation is, if anything, stronger: two concurrent calls run on two threads with two context
  copies. A module global still crosses them, and the `Rendezvous` still holds both calls inside
  the executor middleware until both are in flight, so `isolation-module-global` is killed (both
  eras).
- A `set_executor()` *inside* a tool would no longer leak back to the middleware's context (it
  lands in the thread's copy). Nothing does that; §1 already forbids tools constructing executors.

## The boundary middleware and §1

`ToolErrorMiddleware` (brief 01) is a new middleware outside the executor middleware. §1's rule
for new middleware is "must not swallow the call chain": it returns `await call_next(context)` and
only translates an exception already raised. It sets nothing in the context. Order: it is added
first by `create_mcp_server`, the executor middleware (from `MCPServerApp.run` or a harness
builder) after it, test middleware (`Rendezvous`, `MethodLog`) after that; FastMCP wraps in
reverse, so the order of execution is boundary → executor middleware → test middleware → tool.

## `get_access_token()` in the stateless era

Delegate mode over the ASGI route in the modern era: the bearer token still reaches
`AuthExecutorMiddleware` through `get_access_token()` on every `tools/call` (the HTTP request is the
unit), and the sequential and concurrent delegate tests pass unchanged. A tokenless delegate call
still fails with `No executor configured`.

## Request state

`set_state` is async in 4.x; un-awaited, the identity never lands (a silent no-op today on the
prototype). `await …set_state(…, serializable=False)` keeps it request-scoped as in 2.x; the
session-scoped default would put a per-user value in a store keyed by session, which has no user
meaning in the stateless era. Nothing reads these keys; they exist for logging.

## Verdict

§1 holds as written. The wording to update (R11): §1's "one per HTTP request under
FastMCP/Starlette" becomes "one per request; sync tools run on a worker thread that receives a copy
of the request's context"; and the new-middleware rule gains the boundary's place as the outermost
middleware.

## Already-broken, out of scope

Resource reads get no executor: both executor middlewares hook only `on_call_tool`, so reading
`rcac://context` fails with `No executor configured` on 2.14 and on 4.1 alike (probed on both). It
fails closed and is not a regression; it needs an `issues/` seed (the last phase files it).
