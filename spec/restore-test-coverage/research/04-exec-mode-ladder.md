# 04 — The execution-mode ladder (R7) through `MCPServerApp`, without a server or SSH

**Question.** How does a test observe which mode `MCPServerApp` resolves, and which middleware it
installs, for each rung of § Invariants §4, without starting a server, binding a port or opening
SSH?

## Code path (`src/rcac_mcp/__init__.py`)

`MCPServerApp.main(argv)` (cmdkit) parses, then `run()`:

1. the `--generate-token` branch (R8/R9 only);
2. `exec_mode = self._resolve_exec_mode()` and `log.info(f'Execution mode: {exec_mode}')`;
3. `delegate` → `AuthExecutorMiddleware(self.auth)`, which needs `RCAC_USER_MAP`; otherwise
   `self._create_executor(mode)` (`SSHExecutor(host)` or `LocalShellExecutor()`, or `ValueError('SSH
   host required…')`) wrapped in `SharedExecutorMiddleware`;
4. `mcp = create_mcp_server(self.auth, middlewares=middlewares)` (the name is bound in the
   `rcac_mcp` module namespace), then `mcp.run(transport=…)`, then `executor.close()`.

cmdkit maps `ValueError` → `exit_status.bad_argument` (2) through `MCPServerApp.exceptions`.

## Drive

- Call `MCPServerApp.main(argv)` in-process, never `rcac_mcp.main(argv)`: `main` does `argv or
  sys.argv[1:]`, so an empty list would read pytest's own argv.
- `monkeypatch.setattr(rcac_mcp, 'create_mcp_server', stub)`: the stub records `auth_mode` and
  `middlewares` and returns an object whose `run(**kw)` records the transport and returns at once.
  No FastMCP object is built, so `-a jwt` needs no `JWT_SECRET` and `-a oidc` needs no discovery.
- `monkeypatch.setattr(rcac_mcp.executor.ssh, 'Connection', FakeConnection)` (brief 03): the `ssh`
  rung constructs `SSHExecutor(host)` and the fake records the host. A real connection attempt would
  also be refused by the unit guard.
- `RCAC_SSH_HOST` is unset by the guard; the env-host case sets it. `RCAC_USER_MAP` points at a
  `tmp_path` map for the delegate cases.
- Observe three things: the `Execution mode: <mode>` record (`caplog` at INFO on logger `rcac_mcp`;
  executed in a scratch pytest run, it captures the cmdkit logger's record), the middleware classes
  the stub received, and the hosts `FakeConnection` saw. Plus the exit status, and whether the stub
  was called at all.

Executed (`prototypes/exec_mode_ladder.py`, 2026-10-16):

| argv (env) | status | mode | middleware | executor |
|---|---|---|---|---|
| `-t stdio -e local` | 0 | local | Shared | Local |
| `-t stdio -a jwt` | 2 (SSH host required) | ssh | — (server never built) | — |
| `-t http --ssh-host h1` | 0 | ssh | Shared | SSH `h1` |
| `-t sse` (`RCAC_SSH_HOST=h2`) | 0 | ssh | Shared | SSH `h2` |
| `-t http` | 0 | local | Shared | Local |
| `-t http -a jwt` | 0 | delegate | Auth | — |
| `-t http -a oidc --ssh-host h3` | 0 | ssh | Shared | SSH `h3` |

## Case table (one test id per row; each row separates two adjacent rungs)

| id | argv / env | expected |
|---|---|---|
| `explicit-local-over-stdio` | `-t stdio -e local` | local · Shared · no SSH |
| `explicit-local-over-host` | `-t http -e local --ssh-host h` | local · Shared · no SSH |
| `explicit-local-over-auth` | `-t http -a jwt -e local` | local · Shared |
| `explicit-delegate-over-stdio` | `-t stdio -a jwt -e delegate` | delegate · Auth |
| `stdio-over-auth` | `-t stdio -a jwt` | ssh · status 2 · server never built |
| `stdio-default` | `-t stdio` | ssh · status 2 · server never built |
| `host-flag-over-auth-none` | `-t http --ssh-host h` | ssh `h` · Shared |
| `env-host-over-auth-none` | `-t sse`, `RCAC_SSH_HOST=h` | ssh `h` · Shared |
| `host-over-jwt` | `-t http -a jwt --ssh-host h` | ssh `h` · Shared |
| `auth-none-http` | `-t http` | local · Shared |
| `auth-none-sse` | `-t sse` | local · Shared |
| `jwt-without-host` | `-t http -a jwt` | delegate · Auth (the GOAL's "never local") |
| `oidc-without-host` | `-t sse -a oidc` | delegate · Auth |

Planted ladder violations (`prototypes/mutation_cases.py`): rungs 1↔2 swapped, rungs 3↔4 swapped,
`RCAC_SSH_HOST` ignored, rung 4 widened to every auth mode, delegate routed to the shared branch.
Each names the rows it must turn red.

## Binding notes

- `rcac_mcp.create_mcp_server`, `rcac_mcp.executor.ssh.Connection`, the logger name `rcac_mcp` and
  the `Execution mode: …` text are `rcac_mcp`'s own seams, not FastMCP's. They survive
  `stack-upgrade` unless it moves server construction; the test's docstring says so.
- Middleware is identified by class (`rcac_mcp.middleware.AuthExecutorMiddleware` /
  `SharedExecutorMiddleware`), exactly the names R7 states. No private attribute
  (`SharedExecutorMiddleware._executor`) is read: the executor kind comes from the log line and the
  `FakeConnection` record.
