# 00 — Research digest: restore-test-coverage

Full fan-out (appetite big; trigger 2, since every contract file is on the high-blast-radius list;
trigger 3, since test infrastructure is the deliverable). The planner ran as a foreman's subagent,
so the research ran sequentially, without workers. Every load-bearing claim below was executed
against the installed stack (fastmcp 2.14.4, mcp 1.26.0, httpx 0.28.1, pytest 9.0.2, pytest-asyncio
1.3.0, Python 3.14) on 2026-10-16. The prototypes are kept in [`prototypes/`](prototypes/) and run
from the worktree root.

## Decisions

1. **Delegate mode over the public surface** ([01](01-delegate-over-http.md)): in-process ASGI.
   `server.http_app()` with its lifespan running, and a `fastmcp.Client` over `StreamableHttpTransport`
   whose `httpx_client_factory` returns an `httpx.AsyncClient(transport=ASGITransport(app))`. Real
   JWTs (minted by `generate_token`, by PyJWT with the `token.py` constants, or by the sandboxed
   CLI) go through the real `JWTVerifier` into `AuthExecutorMiddleware`. No port, no socket, no
   patch of `get_access_token`. uvicorn on a localhost port was rejected.
2. **Isolation proof** ([02](02-isolation-proof.md)): a `Rendezvous` middleware (`asyncio.Barrier`
   under a timeout) sits inside the executor middleware, so both calls have set their executor
   before either tool reads it. A plain `gather` is hollow, because sync tools run inline with no
   yield between set and get. The planted module global was shown to cross users deterministically.
   Serialized dispatch fails the barrier instead of passing.
3. **R2** ([02](02-isolation-proof.md)): a bare server (no executor middleware) and an in-memory,
   tokenless call to a jwt+delegate server, each run after, and concurrently with, a request that did
   set an executor.
4. **Process, network and HOME** ([03](03-process-network-home-fakes.md)): record launches at
   `subprocess.Popen` (catches every stdlib launch path whatever the import style). Fake
   `rcac_mcp.executor.ssh.Connection` for construction. An autouse **unit guard** in `conftest.py`
   (unit-marked items only) redirects `HOME`/XDG, blanks the auth and SSH env, and refuses process
   launch and network, recording attempts. Contract tests assert no refusals in the body. A static
   AST check (`sandbox_violations`) makes "every CLI drive goes through `bin/sandbox.sh`" executable
   for every non-unit call site.
5. **Ladder** ([04](04-exec-mode-ladder.md)): `MCPServerApp.main(argv)` in-process with
   `rcac_mcp.create_mcp_server` stubbed and `Connection` faked. The mode is observed from the
   `Execution mode:` log record, the middleware classes and the SSH host; 13 rows, each separating
   two adjacent rungs.
6. **R12** ([05](05-mutation-harness-and-pytest.md)): source mutations on a copy of the package, run
   as a sandboxed child pytest with `PYTHONPATH` and an import-origin pre-check. The pure
   `mutation_violations` demands exit 1 and a `FAILED` line for every target. There are 38 cases
   with anchors verified once each, and harness controls for survival, wrong origin and anchor drift.
7. **pytest** ([05](05-mutation-harness-and-pytest.md)): no async tests. `harness.drive` runs each
   coroutine in a fresh `contextvars.Context`, so strict mode is irrelevant.
8. **Upgrade survival** ([06](06-upgrade-survival.md)): FastMCP/mcp touchpoints are confined to
   `tests/harness.py`. `rcac_mcp` seams are named in docstrings, and the internals-bound list goes
   to the `stack-upgrade` and `safe-execution` seeds in P8.

## Contradictions resolved

- *The GOAL's clarification expected the access-token lookup to need an internal.* It does not: the
  ASGI route reaches the real verifier and middleware through public FastMCP 2.x API. The harness
  is still isolated, because that API is what FastMCP 4 may change.
- *The seed sketched R1 as "two `asyncio` tasks that each `set_executor()`".* That tests the
  `ContextVar` primitive, not the server: it stays green if the middleware caches an executor, and
  it calls `set_executor` from the test. The design drives real tool calls through the middleware
  instead, and plants both the global and a cached executor.
- *"Two shared-mode executors on the same server"* cannot exist (a second shared middleware simply
  wins). R1 is met by two delegate identities on one server, with a two-server shared shape as
  supplementary coverage.

## Residual unknowns (carried to PLAN § 5)

- FastMCP 4's client and middleware API: not installed, not guessed.
- Mutation-pass runtime (~1.5–2 min) on slower hosts.


## Amendment (2026-10-16)

The adversarial design review changed decisions 2/7 (no fresh context per drive; build servers
inside the driven loop), 4 (the `PATH` shim, the harness fence, and a reason required on refusals)
and 6 (a gate-run runner with JUnit kill reasons; 43 cases). PLAN §4 records each finding and what
it changed.
