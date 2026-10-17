# 02 — Serving both protocol eras, and driving each in tests

Sources: `mcp_types/version.py`, `fastmcp/client/client.py` (`ConnectMode`, `_negotiate`,
`instructions`), `fastmcp/server/middleware/middleware.py` (`on_initialize`, `on_discover`,
`on_message`), the MCP 2026-07-28 *Versioning and Compatibility* page (read 2026-10-17), and
probes against the prototype (scratch copy of the tree on FastMCP 4.1).

## What the stack speaks

`mcp_types.version`: `HANDSHAKE_PROTOCOL_VERSIONS = 2024-11-05 … 2025-11-25` (the `initialize`
era), `MODERN_PROTOCOL_VERSIONS = ("2026-07-28",)`. A FastMCP 4 server is dual-era with no
configuration: an `initialize` selects legacy semantics for that session or process; a request
carrying modern `_meta` is served statelessly. The spec's matrix: legacy client → dual-era server
works; dual-era client → dual-era server stays modern.

## Where `instructions` go

`FastMCP(instructions=…)` feeds both results: `InitializeResult.instructions` (legacy) and
`DiscoverResult.instructions` (modern). Nothing in the repo changes for that.

## Client modes (`fastmcp.Client(..., mode=)`)

| mode | wire | `protocol_version` | `initialize_result` | `instructions` |
|---|---|---|---|---|
| `"legacy"` | `initialize`, `notifications/initialized` | `2025-11-25` | set | from `InitializeResult` |
| `"auto"` (default) | `server/discover` probe, then modern requests | `2026-07-28` | `None` | from `DiscoverResult` |
| `"2026-07-28"` (pin) | **no** discover: a synthesized `DiscoverResult` | `2026-07-28` | `None` | **`None`** |

Observed with an `on_message` recorder on the server, in memory and over the in-process ASGI route:
legacy → `['initialize', 'notifications/initialized', 'tools/list']`; auto →
`['server/discover', 'tools/list']`; pin → `['tools/list']`. All three list the 23 tools.

**Consequence:** a modern-era test must use `mode="auto"` and then *assert* that it negotiated
`2026-07-28` (auto falls back to legacy silently on any non-modern answer); the pin never sends
`server/discover`, so it cannot prove R2's "answer `server/discover` with the instructions".
The legacy test uses `mode="legacy"`. Each asserts the methods the server saw: `initialize`
present and `server/discover` absent, or the reverse.

## Transports

`SSETransport.legacy_only = True` on the client, and the server's SSE app is handshake-only: an
`auto` client on `-t sse` negotiates `2025-11-25`. stdio and streamable HTTP serve both eras.
Probe of the real CLI under `bin/sandbox.sh` (`-e local`): http legacy/auto → 23 tools at
`2025-11-25`/`2026-07-28`; sse legacy/auto → 23 tools at `2025-11-25`; stdio legacy/auto → 23 tools
at `2025-11-25`/`2026-07-28`. The 2026-07-28 spec deprecates HTTP+SSE but FastMCP 4.1 still serves
it, so per the GOAL's clarification `-t sse` stays and R4's rejection path does not fire.

## Running the whole suite in each era

The contract tests were written against the handshake era; all 296 pass in it on 4.1 after the
fixes in brief 01. Running every harness client in the modern era (pinned) also passes 296/296,
and the 53 mutation cases are all killed in both eras. A test-id-preserving way to keep both is a
harness-level era selector read from the environment (`CLUSTER_MCP_TEST_ERA=legacy|modern`,
default `legacy`), with the harness refusing an unknown value and *checking after every connect*
that the client negotiated the era asked for (so an ignored selector fails loudly instead of
running the same era twice). Parametrizing the suite by era instead would rename every id and break
R8's "every id collected at `3d010ec`".

## Harness verbs this adds

`negotiate(server_or_app, era, token=None) -> Negotiated` (protocol version, whether an
`InitializeResult` exists, served instructions, tool names, methods the server saw), via a
`MethodLog` middleware the builders accept as `extra`; and `ERA`, the selected era. The R2 test
module speaks only those.
