# 02 — Proving request isolation non-hollowly (R1) and the no-executor paths (R2)

**Question.** How does a test show two tool calls genuinely in flight at once, each under its own
executor, so that replacing `executor_var` with a module global turns it red? Where are R2's
"no executor set" paths, and how do "an earlier or concurrent request did set an executor" become
observable?

## Why a naive concurrent test is hollow

- FastMCP 2.14 runs a sync tool inline on the event loop: `FunctionTool.run` calls the function
  through `type_adapter.validate_python(arguments)` and awaits only if the result is awaitable. Every
  tool here is sync, so a blocking executor stalls the loop and two tool bodies never overlap.
- `SharedExecutorMiddleware` and `AuthExecutorMiddleware` call `set_executor(...)` and then `await
  call_next(context)`; nothing between that set and the tool's `get_executor()` yields. With a module
  global, `asyncio.gather` of two calls still runs set→get→run for one call before the other's set,
  so the global holds the right value at every read and the test passes. **A plain `gather` cannot
  see the planted violation.**

## The rendezvous

A test-only FastMCP `Middleware` added *after* the executor middleware (FastMCP applies
`reversed(self.middleware)`, so the first added is outermost and later ones sit between it and the
tool) awaits an `asyncio.Barrier(n)` inside `on_call_tool` under `asyncio.timeout(...)`. Each call
has therefore set its executor before any call's tool body runs.

- **Correct code:** each call's task carries its own `ContextVar` copy; both read their own executor.
- **Module global** (planted at runtime in `prototypes/isolation_over_http.py plant`, executed
  2026-10-16): the last set wins; `alice`'s `echo A` was launched as `sudo … -u ubob`, and the result
  alice's client received named `ubob`. Deterministic, not timing-dependent.
- **Serialized dispatch** (a server that handled one request at a time) never fills the barrier: the
  timeout raises inside the call, the client sees an error, and the isolation check fails. The test
  cannot pass by the calls not overlapping, and a standing control
  (`test_rendezvous_fails_when_calls_are_not_concurrent`: one call, two parties, short timeout)
  proves the barrier is not vacuous.

The low-level server spawns a task per message (`mcp/server/lowlevel/server.py`,
`tg.start_soon(self._handle_message, …)`), and each HTTP client has its own session, so both calls
are dispatched concurrently in one event loop, in-memory and over ASGI.

## What the check compares

Each call sends a distinct command, and the boundary fake answers with a marker naming the user (or
recording executor) and the command it received. A pure check, `isolation_violations(expected, ran,
results)`, takes: `expected` (command → the user or executor it must run under), `ran` (pairs
observed at the boundary), and `results` (command → the text that caller's client received). It
flags a command run under the wrong owner, a command run zero or several times, an unexpected run,
and a result that lacks its own marker or carries another call's. Standing negative controls feed it
crossed, foreign-result, missing and extra observations.

## Two R1 shapes

1. **Delegate** (the security case): one server, `create_mcp_server('jwt', [AuthExecutorMiddleware])`
   plus the rendezvous, two HTTP clients with `sub=alice` and `sub=bob` tokens, launches recorded at
   `subprocess.Popen` (brief 03).
2. **Shared** (supplementary): two servers in one process, each with `SharedExecutorMiddleware` over
   its own recording executor and the same rendezvous object, two in-memory clients. "Two shared-mode
   executors on the same server" cannot exist (a second `SharedExecutorMiddleware` simply wins), so
   the GOAL's "or" is met by the delegate shape. The shared shape guards the in-process case, where a
   module global would also bite.

## R2 paths (no executor set for this request)

- **No executor middleware:** `create_mcp_server('none')` with no middleware. `get_executor()` raises
  `RuntimeError('No executor configured…')` in the tool, and the client sees `is_error=True`.
- **Delegate, no token:** an in-memory client against `create_mcp_server('jwt', [AuthExecutorMiddleware])`.
  `get_access_token()` returns `None`, the middleware calls `call_next` without setting anything, and
  the tool's `get_executor()` raises. The same server also serves an authenticated HTTP client, so
  "earlier" and "concurrent" requests that *did* set an executor live on the same server.
- **Earlier:** call the executor-setting path first and wait for it, then make the bare call.
  **Concurrent:** both calls meet at the rendezvous. Under the planted global, the bare call ran on
  the other request's executor (`echo ANON` launched as `ualice`).
- "No command ran" is three observations: the client saw an error; the recording executor or launch
  recorder saw only the other request's command; the unit guard (brief 03) refused nothing.

## Context hygiene

`asyncio.run` copies the caller's context. A test that ever called `set_executor` at the top level
would leak into later tests' runs and could make R2 red (or a crossed R1 accidentally right). The
harness runs every drive as `contextvars.Context().run(asyncio.run, coro)`: a fresh, empty context
per drive. A module-global plant is not a `ContextVar`, so the fresh context does not hide it. No
test reads or writes `executor_var` directly.


## Amendment (2026-10-16, adversarial design review)

The "Context hygiene" recommendation above (a fresh, empty `contextvars.Context` per drive) is
**withdrawn**. Production builds the middleware and serves in one context, so anything set at
construction reaches every request task; a fresh context hid a planted `set_executor` in
`AuthExecutorMiddleware.__init__` (finding 1). The design now builds every server inside the driven
coroutine, lets `asyncio.run` copy the main context, and checks after every test that the main
context holds no executor (PLAN §2.2, §2.3).
