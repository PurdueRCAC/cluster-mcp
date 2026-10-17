# PLAN — Make the coupled core's contracts executable

> **Status:** Draft for review · **Last updated:** 2026-10-16
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Backing detail is in
> [`research/`](research/). Every design element traces to a GOAL R-ID.

## 1. Summary

The plan adds seven test modules, one harness module and a guard in `tests/conftest.py`, and changes
nothing in `src/`. Contracts are driven through the server's public MCP surface: an in-memory client
for shared mode, and an **in-process ASGI HTTP route carrying real JWTs** for delegate mode. That
route reaches the real `JWTVerifier` and `AuthExecutorMiddleware` with no port and no patched
FastMCP internals. A **rendezvous middleware** makes "concurrent" mean both calls are in flight at
once. Servers are built inside the driven coroutine, as production builds and serves in one
context. Launches are recorded at `subprocess.Popen`, so nothing runs `sudo`. A unit-test guard
refuses processes, network and the real `HOME`, and a `PATH` shim refuses `sudo` and `ssh` for every
test. Every contract is shown red by **source mutations** of a copy of the package, each run as a
sandboxed child pytest and counted as caught only when the named targets fail for a stated reason
(43 planted violations, R12). The runner is not collected: every phase gate runs it, and its report
goes in the phase commit (the build record). The fast checks of the runner stay in the suite. The
work is eight vertical slices, the novel harness first. That is big appetite, at the GOAL's agreed
size.

## 2. Design

### 2.1 Files

| Path | Role | R-IDs |
|---|---|---|
| `tests/conftest.py` | **Extended, not replaced.** The collection hook stays byte-for-byte. Adds a session-wide `PATH` shim, an autouse **unit guard** (§2.3) for `unit`-marked items, a `guard` fixture exposing its refusals, a `launches` fixture (unit and integration) that swaps `Popen` for a recorder, and a main-context executor check after every test. It never adds a marker. | R3, R11 |
| `tests/harness.py` | **The only module that touches FastMCP/mcp/httpx** (§2.2). Its docstring names it the `stack-upgrade` rewrite point. Not collected (no `test_` prefix). | R1–R5, R9 |
| `tests/test_isolation.py` | Concurrent calls stay on their own executor; `isolation_violations`. | R1 |
| `tests/test_hygiene.py` | Static sandbox rule (`sandbox_violations`) over every test file; self-tests of the guard (process, exec family, network, HOME), the `PATH` shim (unit and sandboxed child), the harness fence, and the build-inside-the-loop rule. | R11 |
| `tests/mutants.py` | **Not collected.** The `Case` table, the runner (`apply`, `run_child`), `mutation_violations` and a CLI (`python tests/mutants.py [--self-check] CASE…`) that every phase gate runs (§2.5). | R12 |
| `tests/test_mutations.py` | Unit only, milliseconds: `test_mutation_anchor_applies[<case>]` and the `mutation_violations` controls. | R12 |
| `tests/test_tools.py` | Every `EXPECTED_TOOLS` tool through `SharedExecutorMiddleware`; `TOOL_CASES`, `tool_violations`. | R3 |
| `tests/test_no_executor.py` | No executor set means an error and no command; `refusal_violations`. | R2 |
| `tests/test_identity.py` | Claim precedence over HTTP; the user map; `delegation_violations`. | R4, R5 |
| `tests/test_executors.py` | The `sudo` argv and `$SHELL` capture; Protocol `isinstance`; `sudo_argv_violations`. | R6, R10 |
| `tests/test_exec_mode.py` | The ladder through `MCPServerApp.main`; `LADDER_CASES`, `ladder_violations`. | R7 |
| `tests/test_tokens.py` | Both secret floors; signer/verifier agreement; `token_cli_violations`. | R8, R9 |
| `AGENTS.md` § Testing | Rewritten in P8 to describe the suite, the guard, the harness and the internals-bound list. | R11 |
| `issues/stack-upgrade.md`, `issues/safe-execution.md`, `issues/ci-workflow.md` | Dated notes in P8 (§2.6). | — |
| `spec/restore-test-coverage/verify/` | The phase gates (§6): `gate.sh`, `run.sh`, `controls.py`, `ids_check.py` (reads the JUnit report), `ids/P0..P8.txt`. | all |

Existing modules (`test_registry.py`, `test_instructions.py`, `test_cli.py`) are untouched. Their
39 ids are pinned in `verify/ids/P0.txt`. New tests import `EXPECTED_TOOLS` from `test_registry` and
never redefine it.

### 2.2 The harness (`tests/harness.py`)

Signatures are a contract: `verify/controls.py` imports some of them.

- `Outcome(is_error: bool, text: str, status: int | None = None)`: a frozen dataclass. `text` joins
  the result's text content. `status` is the HTTP status when the transport rejected the request
  (401), in which case `is_error=True` and `text=''`.
- `drive(coro, timeout=30)`: `asyncio.run(asyncio.wait_for(coro, timeout))`, which copies the main
  context as production's `MCPServerApp.run()` → `mcp.run()` does. **Every server and middleware is
  constructed inside `coro`**: the builders below raise unless an event loop is running. So anything
  a construction sets in the context reaches the request tasks, as it would in production. (A fresh,
  empty context per drive, the first draft, hid exactly that: adversarial review finding 1.) The
  conftest's main-context check (§2.3) keeps one test's leak from reaching the next.
- **Fence:** `serving`, `in_memory`, `http_client` and `call_http` raise unless `subprocess.Popen`
  is the unit guard's refuser or the `launches` recorder (both carry `test_fence = True`). No
  in-process server call can reach a real `sudo`, in a unit or an integration test.
- `serving(server)`: an async context manager. It builds `app = server.http_app()` (the default
  stateful app, as `mcp.run(transport='streamable-http')` serves) and runs
  `app.router.lifespan_context(app)`.
- `http_client(app, token)`: a `fastmcp.Client` over `StreamableHttpTransport('http://test/mcp',
  auth=token, httpx_client_factory=…)`. The factory returns `httpx.AsyncClient(transport=
  httpx.ASGITransport(app=app), base_url='http://test', …)`. No socket, no port.
- `in_memory(server)`: `fastmcp.Client(server)`, with no HTTP and so no access token.
- `call(client, tool, args) -> Outcome`: `call_tool(..., raise_on_error=False)`.
- `call_http(app, token, tool, args) -> Outcome`: connects and calls in one verb. The verifier's 401
  surfaces at connect (`async with client`), not in `call_tool`, so this verb wraps both and
  normalizes `httpx.HTTPStatusError` to `Outcome(True, '', status)`. Concurrency tests connect first
  with `http_client` and then `call`.
- `mint(secret, *, iss=ISSUER, aud=AUDIENCE, alg=ALGORITHM, exp_in=300, **claims) -> str`: PyJWT with
  the `rcac_mcp.token` constants as defaults. The claims are exactly what the caller passes (no
  implicit `sub`).
- `user_map(tmp_path, text) -> str`: writes a map file and returns its path.
- `RecordingExecutor(name, responder=None)`: implements all eight `Executor` members. It records
  `('run', command, cwd, timeout)`, `('put', l, r)` and `('get', r, l)` in `.calls`. `run` answers
  `CommandResult(stdout=responder(command) if responder else f'{name}|{command}', stderr='',
  exit_code=0, hostname=f'{name}.invalid')`.
- `Rendezvous(parties, timeout=5.0)`: a `fastmcp` `Middleware` whose `on_call_tool` awaits a shared
  `asyncio.Barrier(parties)` under `asyncio.timeout(timeout)` and then `return await
  call_next(context)`. On timeout it raises `RuntimeError('rendezvous: calls were never in flight
  together')`. It is added **after** the executor middleware, which puts it inside it (FastMCP
  applies `reversed(self.middleware)`).
- `delegate_server(map_path)`: `create_mcp_server('jwt', middlewares=[AuthExecutorMiddleware('jwt',
  map_path)])`. `JWT_SECRET` is set by the caller with `monkeypatch`. `shared_server(executor)`:
  `create_mcp_server('none', middlewares=[SharedExecutorMiddleware(executor)])`. `bare_server()`:
  `create_mcp_server('none')`. Each raises `RuntimeError` when no event loop is running
  (construction belongs inside the driven coroutine). Each test builds fresh servers; none is reused
  or has its middleware list edited after construction (beyond `add_middleware(Rendezvous)` before
  first use).

### 2.3 The unit guard and the launch recorder (`tests/conftest.py`)

Research [03](research/03-process-network-home-fakes.md). An autouse fixture acts only when
`request.node.get_closest_marker('unit')` is set:

- **HOME:** `HOME` and `XDG_{CONFIG,CACHE,DATA}_HOME` → under `tmp_path`. `RCAC_SSH_HOST`,
  `RCAC_USER_MAP`, `JWT_SECRET`, `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` and
  `MCP_BASE_URL` are unset (`bin/sandbox.sh`'s blanking).
- **Refusers** that record `(name, args)` and raise `OSError('unit guard: … refused')`:
  `subprocess.Popen`, `os.system`, `os.popen`, `os.posix_spawn`, `os.posix_spawnp`, `os.fork`,
  `os.forkpty`, every `os.exec*` and `os.spawn*`, `pty.fork`, `pty.spawn`,
  `_posixsubprocess.fork_exec`, `multiprocessing.Process.start`, `socket.socket.connect`,
  `socket.socket.connect_ex`, `socket.create_connection`, `socket.getaddrinfo`.
- **Not guarded: file I/O.** A tool that falls back to local file operations is caught by the
  reason check in `refusal_violations` (§2.4) and the `transfer-local-fallback` case, not by the
  guard.
- **Teardown:** a non-empty refusal list fails the test, listing the attempts.
- **`guard` fixture:** exposes `.refused` (the list) so contract tests assert `guard.refused == []`
  **inside the test body**. A refusal raised inside a tool becomes a tool error, which some tests
  expect, so only the in-body assertion makes the test `FAILED`.
- **`launches` fixture** (unit **and** integration): replaces `Popen` with a recorder (`args`,
  `returncode`, `communicate`, `poll`, `wait`, `kill`, `pid`, context manager, `test_fence = True`).
  It appends `list(args)` and answers `stdout` with the marker `f'{user}|{argv[-1]}'`, where `user`
  follows `-u` (or is `argv[0]` when there is no `-u`). It returns `str` under `text=True`, else bytes,
  with exit 0. Each test gets its own list. An integration test that also launches a sandboxed CLI
  (`test_cli_minted_token_is_accepted`) runs that drive before requesting the recorder, or through a
  saved reference to the real `subprocess.run`, named in its docstring.
- **Main-context check** (every test): after the test, `rcac_mcp.context.executor_var.get()` in the
  main context must be `None`; otherwise the test fails, naming the leak, and the value is reset so
  the next test starts clean.
- **`PATH` shim** (session-wide, every test): a temporary directory holding `sudo` and `ssh` scripts
  that print `refused by the test PATH shim` and exit 126 is prepended to `PATH`. `bin/sandbox.sh`
  keeps `PATH`, so sandboxed children inherit it. `test_path_shim_shadows_sudo_and_ssh` (unit:
  `shutil.which` resolves both into the shim) and `test_path_shim_reaches_sandboxed_children`
  (integration: `command -v` inside `bin/sandbox.sh`) prove it is active.

Integration tests are not guarded, because they launch processes on purpose. R11's "through
`bin/sandbox.sh`" is enforced statically by `sandbox_violations(source, filename) -> list[str]`
(`tests/test_hygiene.py`). It walks the AST, resolving `import subprocess as sp` aliases, and flags:
- every `subprocess.{run,Popen,call,check_call,check_output}`, `os.system`/`os.popen`/`os.exec*`/
  `os.spawn*` or `asyncio.create_subprocess_{exec,shell}` call whose first argument is not a list or
  tuple literal starting with `SANDBOX` or `str(SANDBOX)`;
- every call through a bare name imported from `subprocess`;
- every argv literal holding `sudo` or `ssh`, or a string ending in `/sudo` or `/ssh`.

It exempts calls lexically inside a function decorated `@pytest.mark.unit` (the guard refuses those
at runtime). `test_cli_drives_are_sandboxed` runs it over every `tests/*.py`, `mutants.py`
included.

### 2.4 Contract tests

Each module pairs its tests with one **pure check function** that its tests call and that the gate
imports with planted shapes (`verify/controls.py`). The signatures below are a contract. So is the
**violation vocabulary**, because a planted case counts as caught only when its target's failure
carries a stated fragment (§2.5):

| Check | Violation messages contain |
|---|---|
| `isolation_violations` | `ran as`, `ran N times`, `unexpected run`, `result for … lacks`, `result for … carries` |
| `tool_violations` | `error result`, `never reached the executor`, `launched outside the executor`, `result lacks` |
| `refusal_violations` | `not an error`, `error lacks reason`, `executor ran`, `process launched` |
| `delegation_violations` | `error result`, `launch count`, `ran as`, `result lacks` |
| `sudo_argv_violations` | `argv differs` |
| `ladder_violations` | `mode:`, `middleware:`, `ssh host:`, `status:`, `started:` |
| `token_cli_violations` | `status`, `stdout`, `token`, `subject`, `reason` |
| other assertions | `does not satisfy Executor`, `map differs`, `line 3`, `expected 401`; `pytest.raises` failures carry `DID NOT RAISE` |

Tests assert `violations == [], violations` so the messages reach the failure text.

**R1, `test_isolation.py`.** `isolation_violations(expected: Mapping[str, str], ran: Sequence[tuple[str,
str]], results: Mapping[str, str]) -> list[str]`. `expected` maps command → owner; `ran` holds the
(owner, command) pairs seen at the boundary; `results` maps command → the text its caller received.
It flags a command run under the wrong owner, run 0 or ≥2 times, an unexpected run, and a result
lacking its own `owner|command` marker or carrying another call's.
- `test_concurrent_delegate_calls_stay_isolated` (unit): one `delegate_server` plus
  `Rendezvous(2)`; a map `alice ualice` / `bob ubob`; two `http_client`s with `mint(S, sub='alice')`
  and `mint(S, sub='bob')`, connected first, then `asyncio.gather` of `run_command` `echo from-alice`
  and `echo from-bob`. Owners come from `launches` (the `-u` user). It also asserts every launch is
  `sudo -n -H -u …` and `guard.refused == []`.
- `test_concurrent_shared_servers_stay_isolated` (unit): two `shared_server`s over
  `RecordingExecutor('exec-a')` and `RecordingExecutor('exec-b')` sharing one `Rendezvous(2)`; two
  `in_memory` clients in one `drive`. This is supplementary: one server cannot hold two shared
  executors (research [02](research/02-isolation-proof.md)).
- `test_rendezvous_fails_when_calls_are_not_concurrent` (unit): one call through `Rendezvous(2,
  timeout=0.5)` gets an error outcome naming the rendezvous, which proves the barrier is not vacuous.
- `test_isolation_check_catches_crossing[crossed-user|foreign-result|missing-launch|duplicate-launch|unexpected-launch]`.

**R3, `test_tools.py`.** `TOOL_CASES: dict[str, ToolCase]`, one per `EXPECTED_TOOLS` name:
`args`, a `responder` (command → stdout; e.g. `ls -l` lines for `list_directory`, `findscratch`
and `myquota` tables for `storage_paths`, `Submitted batch job 4242` for `sbatch`), and `expect`
(a sentinel that must appear in the result text, or `None` for `write_file`). `download_file` uses a
`tmp_path` destination and expects that path. `tool_violations(outcome, calls, refused, expect) ->
list[str]` flags an error outcome, no executor call, any refusal, and a missing `expect`.
- `test_tool_reaches_only_the_installed_executor[<tool>]` (unit, 23 ids): `shared_server(rec)`,
  `in_memory` call, `tool_violations(...) == []`, `guard.refused == []`.
- `test_tool_cases_cover_expected_tools`: `set(TOOL_CASES) == EXPECTED_TOOLS`.
- `test_tool_check_catches_bypass[no-executor-call|outside-launch|result-dropped|error-result]`.

**R2, `test_no_executor.py`.** `refusal_violations(outcome, calls, launches, reason) -> list[str]`
flags a non-error outcome, an error whose text lacks `reason` (case-insensitive), any executor call
and any launch. **Any error is not enough** (adversarial review finding 2: a planted local fallback
in `download_file` failed with a local `[Errno 2]` and passed a reason-free check). Reasons:
`No executor configured` for the bare and tokenless paths; `not authorized` for an unmapped
identity; `Could not extract` for a token with no identity claim.
- `test_tool_without_executor_middleware_fails[<tool>]` (unit, 23 ids): `bare_server()`,
  `TOOL_CASES[tool].args`, `in_memory`. It asserts `refusal_violations(...) == []` (with `launches`
  recorded) and `guard.refused == []`.
- `test_no_executor_after_earlier_request`: a `shared_server(rec)` call completes, then a
  `bare_server` call in the same `drive`. `rec.calls` holds only the first command.
- `test_no_executor_while_other_request_in_flight`: the same pair, both with one shared
  `Rendezvous(2)`.
- `test_delegate_without_token_fails`: an `in_memory` call to a `delegate_server`.
- `test_delegate_without_token_after_authenticated_request` and `…_while_authenticated_request_in_flight`:
  on one `delegate_server`, an `http_client` (`sub=alice`) call first, or concurrently through
  `Rendezvous(2)`, then the `in_memory` call. Launches hold exactly alice's command, as `ualice`.
- `test_refusal_check_catches_execution[not-an-error|lacks-reason|executor-ran|process-launched]`.

**R4/R5, `test_identity.py`.** `delegation_violations(outcome, launches, user, command) -> list[str]`
flags an error outcome, a launch count other than one, a launch under a user other than `user` or
for a command other than `command`, and a result without `user|command`. The map is `alice ualice`,
`al@example.org uemail`, `al-pu upu`, `bob ubob`.
- `test_identity_claim_precedence[…]` (HTTP, real tokens): `all-three` (sub=alice, email, pu →
  `ualice`); `sub-empty` (sub='', email → `uemail`); `sub-absent` (email + pu → `uemail`);
  `email-empty` (email='', pu → `upu`); `username-only` (pu → `upu`).
- `test_token_without_identity_fails[no-claims|all-empty]`: `refusal_violations == []`.
- `test_unmapped_identity_is_not_authorized`: `sub=ghost` → refusal, and `'not authorized'` in the
  lowercased text.
- `test_first_claim_unmapped_does_not_fall_through`: `sub=ghost`, `email=al@example.org` → refusal
  and not authorized. The first non-empty claim decides, with no fallback to the next.
- `test_executor_rejects_unmapped_identity`: `DelegatingExecutor('ghost', {...})` raises `KeyError`.
- `test_user_map_rejects_line_without_local_user`: line 3 is `carol` → `ValueError` whose message
  contains `line 3`.
- `test_user_map_skips_comments_and_blanks`: `#`, indented `#`, blank and whitespace-only lines →
  exactly `{'alice': 'ualice', 'bob': 'ubob'}`.
- `test_delegation_check_catches_drift[wrong-user|refused|ran-twice|foreign-result]`.

**R6/R10, `test_executors.py`.** `sudo_argv_violations(argv, user, shell, command_line) -> list[str]`
compares against exactly `['sudo', '-n', '-H', '-u', user, shell, '-c', command_line]` and names each
difference.
- `test_sudo_argv[no-cwd|cwd-spaces|cwd-metacharacters]`: `SHELL=/opt/test-shell-a`;
  `DelegatingExecutor('bob', {'bob': 'ubob'}).run('echo $HOME; ls *', cwd=…)` with `launches`. The
  cwds are `/data/my dir` and `/data/x; rm -rf / $(id) 'q'` (absolute: `~` expansion is a non-goal).
  The expected command line is `f'cd {shlex.quote(cwd)} && echo $HOME; ls *'`, and
  `shlex.split(argv[-1])[:3] == ['cd', cwd, '&&']`. With no cwd, `argv[-1]` is the command verbatim.
- `test_shell_is_captured_at_construction`: construct under `SHELL=/opt/test-shell-a`, then set
  `/opt/test-shell-b`, then run. The argv carries shell-a.
- `test_argv_check_catches_drift[n-dropped|H-dropped|command-quoted|cwd-unquoted|wrong-shell|wrong-user]`.
- `test_backend_satisfies_executor_protocol[ssh|local|delegate]`: `isinstance(x, Executor)`. The
  `ssh` row replaces `rcac_mcp.executor.ssh.Connection` with a `FakeConnection` and asserts it was
  constructed and opened for the host. All rows assert `guard.refused == []`.

**R7, `test_exec_mode.py`.** `LADDER_CASES` holds the 13 `pytest.param` rows of research
[04](research/04-exec-mode-ladder.md). The test stubs `rcac_mcp.create_mcp_server` (recording
`middlewares`, returning an object whose `run` returns at once), fakes `Connection`, writes
`RCAC_USER_MAP`, sets or leaves unset `RCAC_SSH_HOST`, calls `MCPServerApp.main(argv)` (never
`rcac_mcp.main`, which falls back to `sys.argv`), and reads `Execution mode:` from `caplog`.
`ladder_violations(observed: dict, expected: dict) -> list[str]` has observed keys `status`, `mode`,
`middleware` (class names or `None`), `ssh_hosts`, `started`, and expected keys `status`, `mode`,
`middleware`, `ssh_host`, `started`. Ids: `test_exec_mode_ladder[<row>]` and
`test_ladder_check_catches_drift[wrong-mode|wrong-middleware|extra-middleware|connected-in-delegate|started-when-failing-closed]`.

**R8/R9, `test_tokens.py`.** `token_cli_violations(returncode, stdout, stderr, accept, secret=None,
sub=None) -> list[str]`. To accept, it needs exit 0 and exactly one stdout line that decodes with
`secret`, `ISSUER`, `AUDIENCE` and `ALGORITHM`, with `sub` matching. To refuse, it needs exit
`exit_status.bad_argument`, empty stdout, and `JWT_SECRET` in stderr: the reason, so a removed
`--generate-token` flag, which also exits 2, cannot pass.
- `test_jwt_auth_refuses_short_secret[unset|empty|31-chars]` (unit): `create_jwt_auth()` raises
  `ValueError`. `test_jwt_auth_accepts_32_char_secret`: it returns a provider.
- `test_generate_token_refuses_short_secret[…]` / `test_generate_token_accepts_32_char_secret`
  (integration): `[str(SANDBOX), 'env', 'JWT_SECRET=…', str(CLI), '--generate-token', '--sub', …]`.
  The sandbox unsets `JWT_SECRET`, and `env` sets it after. For `unset`, `env` is omitted.
- `test_minted_token_is_accepted` (unit): `generate_token(S, 60, 'alice')` → `delegate_server` with
  `JWT_SECRET=S` → `run_command` runs as `ualice` (`delegation_violations == []`).
- `test_cli_minted_token_is_accepted` (integration): the sandboxed CLI mints with `--sub alice`;
  then, under the `launches` recorder (the harness fence requires it), the token is presented
  through the same in-process route.
- `test_mismatched_token_is_rejected[issuer|audience|secret|algorithm|expired]` (unit): `mint(...)`
  with one field wrong → `Outcome.status == 401` (via `call_http`), and no launch. Each row is shown
  red by an unchecked-verifier plant (`verifier-audience-unchecked`, `verifier-issuer-unchecked`;
  finding 6). `ISSUER == AUDIENCE == 'rcac-mcp'`, so a signer that swapped issuer and audience is
  indistinguishable and cannot be pinned. That is a recorded limitation in `AGENTS.md` § Testing (the
  "issuer/audience swap"), not a defect: no token can differ.
- `test_token_check_catches_drift[accepted-short-secret|token-on-refusal|wrong-status|refused-for-another-reason|no-token|two-lines|other-secret|wrong-subject]`.

### 2.5 Planted violations (`tests/mutants.py`, run by the gate; R12)

Research [05](research/05-mutation-harness-and-pytest.md); the table is
[`research/prototypes/mutation_cases.py`](research/prototypes/mutation_cases.py): 43 cases, every
anchor verified to occur once, every mutant compiles. Five of them came from the adversarial review.

**Where it runs (foreman's ruling on finding 5).** About 1.5 s per child, so 43 children would add
60–80 s to every profile verify; today's suite takes 5 s. The case table and the runner therefore
live in `tests/mutants.py`, which pytest does not collect. Every phase gate runs it for the cases the
phases so far own. Its report (one line per case: killed by which target, for which reason) goes in
the phase commit body, which is the cycle's build record. That is GOAL R12's "recorded mutation in
the cycle's build record", and it is re-run, not merely recorded, at every gate and in P8's fresh
clone. The fast parts stay in the suite: `test_mutation_anchor_applies[<case>]` and the
`mutation_violations` controls, both unit, in milliseconds. A dated note on `issues/ci-workflow.md`
offers `python tests/mutants.py --self-check <all cases>` as an opt-in CI job.

- `Case(id, file, edits, targets, why)`, a frozen dataclass. `file` is relative to the package
  directory, `edits` is a tuple of `(old, new)`, `targets` are `tests/`-relative ids that must FAIL,
  and `why` is the fragment of the violation vocabulary (§2.4) each target's failure must carry.
- `apply(case, dest)`: `copytree(Path(rcac_mcp.__file__).parent, dest/'src'/'rcac_mcp',
  ignore=ignore_patterns('__pycache__'))`, then each edit with an exactly-once check.
- `run_child(src_root, targets, junit)`: `subprocess.run([str(SANDBOX), 'sh', '-c', CHILD, 'sh',
  sys.executable, str(src_root), str(junit), *targets], env={**os.environ, 'PYTHONPATH':
  str(src_root), 'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, text=True, timeout=300)`.
  `CHILD` does `cd "$CLUSTER_MCP_REPO"`, runs the origin pre-check (exit 97 unless `rcac_mcp`
  resolves under `src_root`), then `exec "$py" -m pytest -q -rA -p no:cacheprovider
  --junitxml="$junit" "$@"`.
- `mutation_violations(returncode, junit_xml, targets, why) -> list[str]`. The child must exit 1:
  0 means the mutant survived, 97 a wrong import origin, anything else a harness failure. The JUnit
  report must parse. Each target's testcase must hold a `<failure>` (not an `<error>`, not
  `<skipped>`) whose message or text contains `why`. **A kill for the wrong reason is not a kill**
  (finding 3: renaming `FastMCP(` failed the isolation target with a `NameError` and counted as
  caught). Terminal summaries are no longer parsed.
- CLI: `python tests/mutants.py [--self-check] CASE_ID…` prints one line per case and exits non-zero
  if any case survives, is killed for the wrong reason, or names an unknown id. `--self-check` also
  runs the runner's own controls: a docstring-only edit of `context.py` with an isolation target must
  be reported as surviving, and a pre-check against a directory the child does not import from must
  be reported as a wrong origin.
- Tests in the suite: `test_mutation_anchor_applies[<case>]` (unit, all 43) and
  `test_mutation_check_flags_survivors[all-passed|target-passed|collection-error|usage-error|target-missing|wrong-origin|wrong-reason|error-not-failure|teardown-error-only]`
  (unit, synthetic JUnit).
- Cases land with their slice: P1 isolation (2), P2 tools (2), P3 no-executor (6, including the two
  set-at-construction plants and `transfer-local-fallback`), P4 identity and map (10), P5 argv and
  protocol (8), P6 ladder (5), P7 secrets and tokens (10, including the two unchecked-verifier
  plants). The build may add a case. It removes or retargets one only with the reason recorded in
  the phase commit, because a target that will not go red is a hollow test until shown otherwise.

### 2.6 Documentation and downstream notes (P8)

- `AGENTS.md` § Testing replaces "The suite is three files" and "no tests yet" with:
  - the module list;
  - the guard (what `unit` now enforces) and the `PATH` shim;
  - the harness as the single FastMCP touchpoint, and the build-inside-the-loop rule;
  - the mutation runner (`tests/mutants.py`: how to run it, what a surviving or wrong-reason case
    means, that it is gate-run and not collected), and what a red
    `test_mutation_anchor_applies[…]` means;
  - the recorded limitations: the issuer/audience swap is undetectable while
    `ISSUER == AUDIENCE`, and file I/O is not guarded;
  - the internals-bound list (research [06](research/06-upgrade-survival.md)).

  `pyproject.toml`'s marker text is unchanged.
- Dated notes:
  - `issues/stack-upgrade.md`: `tests/harness.py`, `test_exec_mode.py`'s stub and `test_tokens.py`'s
    verifier route are the rewrite points.
  - `issues/safe-execution.md`: `tests/test_executors.py` argv and protocol rows, and the
    `delegate.py`/`shell.py`/`ssh.py`/`transfer.py` mutation anchors.
  - `issues/ci-workflow.md`: the suite needs `bin/sandbox.sh` and `uv`; `tests/mutants.py` is the
    opt-in mutation job (~60–80 s).

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1 | `test_isolation.py`: delegate identities over the ASGI route plus `Rendezvous`; the two-server shared shape; `isolation_violations`; cases `isolation-module-global`, `isolation-executor-cached` |
| R2 | `test_no_executor.py`: bare server ×23 tools; tokenless delegate; earlier and concurrent variants, servers built inside the driven loop; `refusal_violations` with a required reason; six cases |
| R3 | `test_tools.py`: `TOOL_CASES` ×23 through `SharedExecutorMiddleware`; guard refusals; `tool_violations`; two cases |
| R4 | `test_identity.py`: five precedence rows and two no-claim rows over HTTP with real tokens; five cases |
| R5 | `test_identity.py`: unmapped over HTTP, no fall-through, `KeyError`, malformed line, comments and blanks; five cases |
| R6 | `test_executors.py`: exact argv at `Popen`, `$SHELL` captured, cwd quoted and command not; five cases |
| R7 | `test_exec_mode.py`: 13 ladder rows through `MCPServerApp.main`, middleware class per mode; five cases; gate drive of `-t stdio -a jwt` |
| R8 | `test_tokens.py`: `create_jwt_auth` and the sandboxed CLI at unset/empty/31/32; three cases; gate drive |
| R9 | `test_tokens.py`: `generate_token` and CLI tokens accepted through the real verifier; five mismatches rejected; seven cases (both halves shown red) |
| R10 | `test_executors.py`: `isinstance` for all three, `SSHExecutor` on a fake `Connection`; three cases |
| R11 | Every test marked (hook plus `--noconftest` witness); unit guard (HOME, processes, network); `PATH` shim; harness fence; `sandbox_violations`; P0's 39 ids pass; profile verify in P8 |
| R12 | `tests/mutants.py`: 43 source mutations on a package copy, each killed by its named targets for its stated reason, run by every gate and recorded in each phase commit; anchor and check controls in the suite; `src/` byte-identical to the base |

## 3. Invariant gate (AGENTS.md constitution check)

The gate was walked three times: from the GOAL before research, against this design, and again
after the adversarial review's changes. The change edits only `tests/`, `AGENTS.md` § Testing, three
seeds and `spec/`. It **edits no high-blast-radius path**. It *reads and pins* §1, §2, §4, §5, §6 and
§7, and *uses* `bin/sandbox.sh` without editing it. Untouched: §3 (timeout asymmetry, a non-goal), §8
(resources, a non-goal) and §9 (no tool change; `SERVER_INSTRUCTIONS`, the README and
`EXPECTED_TOOLS` are unchanged).

- **§1 Per-request isolation:** tests drive real calls through the real middleware and never call
  `set_executor` themselves; only the conftest's main-context check reads `executor_var`. The
  test-only `Rendezvous` middleware ends in `return await call_next(context)` (§1's last bullet).
  The planted cases cover the module global, a cached executor, and a set at construction (§1's
  "not at server construction"), so the contract is pinned.
- **§2 Executor protocol:** `RecordingExecutor` implements all eight members, and R10 checks the
  three real backends. `isinstance` checks presence only (§2), which is what R10 asks; signatures
  are exercised by R6 and R3's calls.
- **§4 Ladder:** the R7 rows separate each adjacent pair of rungs. `jwt-without-host` and
  `oidc-without-host` pin "never widen `local`".
- **§5 Delegate:** claim precedence, no fallback, `PermissionError` versus `KeyError` (both kept),
  the map format and the exact argv are each pinned against real tokens or real calls. No `sudo`
  runs: the recorder, the harness fence and the `PATH` shim each stand in the way.
- **§6 Auth:** both floors are pinned separately (two cases). The issuer/audience/algorithm triple is
  pinned from the signer side and the verifier side, for acceptance and rejection. OIDC is a
  non-goal.
- **§7 Tool registration:** R3 calls every served tool through `get_executor()`. Three cases plant a
  tool that builds its own executor or falls back to a local one.
- **§ Conventions:**
  - every new test carries `unit` or `integration`;
  - every CLI drive goes through `bin/sandbox.sh` (statically checked), and pytest drives step back
    into the repo;
  - exit codes use `exit_status.bad_argument`;
  - comments and docstrings carry no `R#`/`P#`, and the gate greps for them, `noqa` codes aside;
  - no `Co-Authored-By`;
  - no dependency change, so no `uv lock`.
- **§ Testing / § Packaging:** the stale-checkout trap still applies (a mutation copy uses
  `ignore_patterns('__pycache__')`). `tests/fixtures` is not created. PyYAML stays out.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| A unit guard, a `PATH` shim and a harness fence in `conftest.py`/`harness.py` (beyond the marker hook) | R3's "no process, SSH or `sudo` outside the executor" and R11's "no real `HOME`/host/`sudo`" need an observer that sees launch paths the test did not anticipate, in unit and integration tests alike | Per-test mocks see only what each test thought to mock. A planted `LocalShellExecutor` in a tool would slip past, and an integration test could reach a real `sudo` (finding 7) |
| Mutation runner outside the collected suite, run by every gate (~60–80 s), report recorded in each phase commit | R12's planted violations, without making the profile verify 15× slower (foreman's ruling on finding 5) | Mutations only in commit bodies decay. Runtime monkeypatch plants are reimplementations, not the source the GOAL names. Collected mutation tests cost every verify a minute |
| Phase gates as scripts under `spec/…/verify/` instead of inline `verify:` strings | Each gate needs `$( )`, loops, ~270 named ids, a JUnit check, the mutation runner and a clone run. Inline YAML would need several quoting levels | The inline form ran to ~3 KB per phase last cycle and is the source of the KB inbox's quoting friction. The script path is one plain command |
| A supplementary two-server shared-mode R1 test | It pins the in-process case a module global would also break | Delegate-only meets R1's "or" but leaves shared mode unpinned |
| `tests/harness.py` imports `httpx` transitively (via `fastmcp`/`mcp`) | `StreamableHttpTransport`'s factory must return an `httpx.AsyncClient` | Adding `httpx` to the dev group changes `pyproject.toml` and `uv.lock` for a module `stack-upgrade` rewrites anyway (§5 risk) |

## 4. Rabbit holes (resolved)

- Delegate mode with real tokens through the public surface → in-process ASGI, not uvicorn and not
  a patched `get_access_token` ([01](research/01-delegate-over-http.md)).
- A concurrency test that a module global cannot pass → the `Rendezvous` inside the executor
  middleware. A plain `gather` is hollow because sync tools never yield
  ([02](research/02-isolation-proof.md)).
- R2's no-executor paths and "earlier or concurrent" → a bare server, tokenless in-memory calls, and
  a shared rendezvous across servers or transports ([02](research/02-isolation-proof.md)), with
  servers built inside the driven loop (review finding 1).
- Recording `sudo` without running it, `$SHELL` capture, `SSHExecutor` construction → `Popen`-level
  recorder and a `Connection` fake; the unit guard ([03](research/03-process-network-home-fakes.md)).
- The ladder without a server or SSH → `MCPServerApp.main` with `create_mcp_server` stubbed
  ([04](research/04-exec-mode-ladder.md)).
- R12 → source mutations of a package copy with origin, anchor and kill-reason checks, gate-run
  ([05](research/05-mutation-harness-and-pytest.md), revised by findings 3 and 5).
- pytest-asyncio strict mode → no async tests; `harness.drive` wraps `asyncio.run`
  ([05](research/05-mutation-harness-and-pytest.md)).
- What survives FastMCP 4 → the internals-bound list ([06](research/06-upgrade-survival.md)).
- **Adversarial design review (trigger 3), ran 2026-10-16.** The foreman ran a fresh reviewer. It
  built the harness, the guard, the recorder, R1, parts of R2/R9 and the mutation runner per §2 in a
  scratch clone at `483166f`, and attacked them. **Held up:** the Rendezvous (a module global crossed
  users 3/3; a token-prefix cache and a set-at-construction plant were killed), the real verifier on
  the path, children importing the mutated copy, `gate.sh` sh-clean, and a real P8 clone. Every
  finding was folded in:
  1. **HIGH, a fresh `Context` per drive hid construction-time context.** A planted
     `set_executor(...)` in `AuthExecutorMiddleware.__init__` survived, although production
     (construct and serve in one context) ran the tokenless call as `ualice`. → `drive` now copies
     the main context; builders refuse to run outside a running loop; a main-context check runs
     after every test; and two plants were added (`auth-middleware-sets-at-construction`,
     `shared-middleware-sets-at-construction`) targeting the tokenless and earlier/concurrent R2
     ids (§2.2, §2.3).
  2. **HIGH, `refusal_violations` accepted any error.** A planted local fallback in `download_file`
     passed with `[Errno 2]`. → It requires a stated reason (`No executor configured`, `not
     authorized`, `Could not extract`); a `lacks-reason` control and the `transfer-local-fallback`
     case were added. File I/O is recorded as unguarded (§2.3, §2.4).
  3. **MEDIUM, a kill was counted without its reason.** A `NameError` mutant counted as caught. →
     The child writes JUnit; a kill needs a `<failure>` carrying the case's `why` from the violation
     vocabulary; `wrong-reason` and `error-not-failure` controls (§2.4, §2.5).
  4. **MEDIUM, gate ids satisfiable by captured output.** → Gates read the JUnit report
     (`verify/ids_check.py`), in the worktree and the clone, never the terminal (§6).
  5. **MEDIUM, cost.** → Foreman's ruling: the runner moved to the non-collected `tests/mutants.py`,
     run by every gate and recorded in each phase commit. Anchor and check controls stay in the
     suite. A `ci-workflow` note offers it as an opt-in job (§2.5).
  6. **MEDIUM, R9's rejection half was never shown red.** → `verifier-audience-unchecked` and
     `verifier-issuer-unchecked`. The undetectable issuer/audience swap (`ISSUER == AUDIENCE`) is a
     recorded limitation in `AGENTS.md` § Testing. It is not a defect, because no token can tell the
     two apart, so no deferral (§2.4).
  7. **MEDIUM, real-`sudo` exposure in integration tests.** → `launches` works for integration
     items; the harness fence refuses any in-process server call without the recorder or the guard;
     a session `PATH` shim refuses `sudo` and `ssh` in every test and its children, with two tests
     proving it active; `sandbox_violations` rejects `sudo`/`ssh` argv (§2.3).
  8. **MEDIUM, the spec-id grep matched `# noqa: F401`.** → `noqa:` lines are excluded (§6).
  - **LOW, all folded:** the 401 surfaces at connect, so `call_http` wraps connect and call; the
    guard now covers `os.forkpty`, `os.exec*`/`os.spawn*`, `pty`, `_posixsubprocess.fork_exec` and
    `multiprocessing.Process.start`, and the static check covers aliases, `asyncio.create_subprocess_*`
    and `os.exec*`; the base is `merge-base HEAD origin/develop`, after a fetch outside the
    sandbox, falling back to `develop`, and failing with a message when neither exists.

## 5. Risks & open questions

- **FastMCP 4 API is unknown.** The harness is the single rewrite point. If FastMCP 4 drops the
  `httpx_client_factory` hook, the fallback is uvicorn on a random localhost port, unguarded, as an
  `integration` test.
- **Transitive `httpx`.** If `fastmcp` stops depending on it, `harness.py` fails at import, loudly.
- **Gate runtime.** The suite stays fast (unit-heavy, a few sandboxed CLI drives). The mutation
  runner adds ~60–80 s per gate. P8 runs suite and runner twice (worktree and clone) plus a clone
  sync, so ~4 min. `ci-workflow` is told.
- **Mutation anchors are brittle by design.** Any edit to an anchored line fails
  `test_mutation_anchor_applies[<case>]`, naming the contract. That is the intended signal, and it
  binds `safe-execution` and `stack-upgrade` to re-plant.
- **Kill reasons bind to message text.** A reworded violation message turns a case into
  "wrong reason" until its `why` is updated: loud, never silent.
- **Logger capture.** `caplog` captures cmdkit's `rcac_mcp` record today (executed). If a later
  cmdkit stops propagating, the ladder test fails loudly ("no Execution mode record"), not silently.
- **Recorded limitations, not deferrals:** the issuer/audience swap (`ISSUER == AUDIENCE`), and file
  I/O outside the guard.
- **A defect surfaced by a test** is not fixed here (non-goal). The path is left unpinned and
  recorded as `issues/{slug}.md` plus a `ROADMAP.md` entry, or in `.security/` when it is a live
  cross-user or wrong-host path. P8's ledger checks each recorded deferral.
- **Gate scripts and the mutation report live outside the blind reviewer's view** (`spec/`, commit
  bodies). The orchestrator grades them. Any edit to `verify/` after the plan commit is recorded in
  that phase's commit body.

## 6. Verification strategy

**How each slice is built.** Write the slice's tests and check function, and see them green. Then
add the slice's cases to `tests/mutants.py`, run them, and see each killed for its stated reason.
Paste the runner's report into the phase commit body. `src/` is never edited.

**Every phase runs one command:** `sh spec/restore-test-coverage/verify/gate.sh P<n>`. It resolves
the base (`merge-base HEAD origin/develop`, after a fetch outside the sandbox), then runs inside
`bin/sandbox.sh` (scratch files in the sandbox `HOME`) and checks, cumulatively for P1..Pn:

1. Scope:
   - `src/` byte-identical to the base, in commits and in the working tree;
   - only cycle paths changed;
   - no `\b[RPF][0-9]+\b` in `tests/*.py` outside `noqa:` comments.
2. The marker witness: `pytest --noconftest --collect-only -m 'not unit and not integration'`
   exits 5.
3. The whole suite, exit 0, with `--junitxml`. `verify/ids_check.py` requires every id in
   `verify/ids/P0..Pn.txt` to be a passed testcase and nothing anywhere skipped, failed or errored.
   That includes P0's 39 existing ids and each owned case's `test_mutation_anchor_applies[…]`.
4. `verify/controls.py <n>`: each pure check function rejects planted shapes and accepts a clean
   one. The case table holds every case the phases so far own, each with a specific kill reason, and
   every case target is a required id.
5. `tests/mutants.py --self-check <cases owned by P1..Pn>`: every case killed by every target for
   its reason, plus the runner's own surviving-mutant and wrong-origin controls.
6. Direct drives: P6+ runs `rcac-mcp -t stdio -a jwt` (exit 2, `Execution mode: ssh`, `SSH host
   required`). P7+ runs `--generate-token` at 31 characters (exit 2, empty stdout, names
   `JWT_SECRET`) and at 32 (a token that decodes with the shared constants and the `--sub`).

**P8** adds:
- the profile's full verify;
- the `AGENTS.md` § Testing and downstream-seed checks;
- the deferral ledger (every `issues/*.md` named in `TECH.md` exists and has a `ROADMAP.md` entry);
- a fresh `git clone` of the branch, run in a plain subshell under `set -eu`, with `UV_PROJECT=$PWD`,
  `VIRTUAL_ENV` unset, its own `uv sync --locked`, an import-origin assertion, and `src/` equal to the
  base. In it, the full suite passes the JUnit id check and the mutation runner kills every case
  again.

`gate.sh P8 --phase-only` runs only P8's own checks. The clone reads committed state, so build runs
P8's gate on a throwaway commit (`git worktree add --detach`) before the phase commit.

---

*Backing research: [`research/00-digest.md`](research/00-digest.md).*
