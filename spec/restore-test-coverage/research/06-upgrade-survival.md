# 06 — Which tests survive `stack-upgrade` (FastMCP 4, mcp 2) and `safe-execution` unchanged

The GOAL asks that tests "either keep passing or fail in a place that names the contract that
moved", and that any test leaning on an internal says so and is kept isolated. FastMCP 4's API is
not installed here and is not guessed at. This brief classifies what each test touches.

## FastMCP/mcp-bound: confined to `tests/harness.py`

Every FastMCP and mcp touchpoint lives in one module. Each test module speaks harness verbs only
(`drive`, `serving`, `http_client`, `in_memory`, `call`, `mint`, `Rendezvous`, `RecordingExecutor`):

| Touchpoint | Used for |
|---|---|
| `fastmcp.Client(server)` (in-memory transport) | R2, R3 |
| `FastMCP.http_app()`, `app.router.lifespan_context(app)` | R1, R2, R4, R5, R9 |
| `fastmcp.client.transports.StreamableHttpTransport(url, auth=, httpx_client_factory=)` + `httpx.ASGITransport` | R1, R2, R4, R5, R9 |
| `Client.call_tool(name, args, raise_on_error=False)` → `.is_error`, `.content[*].text`; `httpx.HTTPStatusError` → status | all tool-call tests |
| `fastmcp.server.middleware.Middleware.on_call_tool` + `server.add_middleware` (the `Rendezvous`) | R1, R2 concurrency |

When `stack-upgrade` lands, `harness.py` is the rewrite point. If a verb cannot be re-expressed,
every test using it fails at import or first call with a harness error, never a silent pass. The
harness docstring states this.

## `rcac_mcp`-internal seams (survive FastMCP 4; named in each test's docstring)

| Seam | Tests | Expected to move in |
|---|---|---|
| `rcac_mcp.create_mcp_server` (module-global name used by `run()`) | R7 ladder | `stack-upgrade` only if server construction moves |
| `rcac_mcp.executor.ssh.Connection` (Fabric binding) | R7, R10 | `safe-execution` |
| logger `rcac_mcp`, record `Execution mode: <mode>` | R7 | stable |
| `DelegatingExecutor(identity, user_map)`, `load_user_map(path)` | R5, R6, R10 | `safe-execution` (R6 is its deliberate rewrite) |
| `create_jwt_auth()`, `generate_token(secret, lifetime, subject)` | R8, R9 | `stack-upgrade` (auth re-expressed) |
| `SharedExecutorMiddleware(executor)`, `AuthExecutorMiddleware(auth_mode, user_map_path)` | R1–R5 server construction, R7 class check | `stack-upgrade` |
| Mutation anchors (exact source strings) | R12 | everything: a moved anchor fails `test_mutation_anchor_applies[<case>]`, naming the case |

## Stdlib-boundary fakes (survive both)

`subprocess.Popen` recorder and refuser, the socket refusers, `HOME` redirection (brief 03).

## Expected to pass unchanged after FastMCP 4

R8 (`create_jwt_auth` floor; CLI `--generate-token` drives), the R9 CLI mint, R5's user-map loading
and `DelegatingExecutor` `KeyError`, R6's argv (until `safe-execution`), R10's `isinstance` (until
`safe-execution` changes the Protocol), R7 (no FastMCP touched), the guard and hygiene checks, and
the mutation runner's mechanics. The registry and instruction tests (existing) use
`create_mcp_server('none').get_tools()`, a FastMCP API outside this cycle's scope.

## Internals-bound list (for the foreman and the downstream seeds)

1. `tests/harness.py`: all of it (FastMCP/mcp client, ASGI route, middleware API, result decoding).
2. `tests/test_exec_mode.py`: the `rcac_mcp.create_mcp_server` stub and the `Connection` fake.
3. `tests/test_executors.py`: the `Connection` fake (`ssh` row); the argv cases (`safe-execution`).
4. `tests/test_tokens.py`: `create_jwt_auth()` returning a verifier; acceptance and rejection observed
   through the harness's HTTP route (status 401).
5. `tests/mutants.py` (and its anchor checks in `tests/test_mutations.py`): anchors tied to today's source text.

`P8` writes dated notes on `issues/stack-upgrade.md` (items 1, 2, 4) and `issues/safe-execution.md`
(items 2, 3, 5), so those cycles inherit the list.
