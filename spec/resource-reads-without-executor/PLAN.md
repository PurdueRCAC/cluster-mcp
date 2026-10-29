# PLAN — Reading rcac://storage returns the user's storage paths

> **Status:** Draft for review · **Last updated:** 2026-10-28
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Backing detail is in
> [`research/`](research/). Every design element traces to a GOAL R-ID.

## 1. Summary

A resource read gets its request's executor the way a tool call does: from the executor middleware,
in a new `on_read_resource` hook that shares one resolution path with `on_call_tool`. The shared
middleware sets its executor; the delegate middleware maps the token's identity and refuses exactly
as it refuses a tool call, except for `rcac://context`, which `resources.py` declares open and the
middleware lets through untouched. The error boundary gains the same read hook so a refusal keeps its
reason in both eras. The handler stops calling the decorated tool and calls an undecorated helper
the tool now also calls. Three phases: the shared-mode read, the delegate-mode read, then the
invariants and the full gate.

## 2. Design

**The storage helper** (`src/rcac_mcp/tools/rcac.py`). The body of `storage_paths` moves into an
undecorated module function, `resolve_storage_paths() -> StoragePaths`, which calls `get_executor()`
and runs `['findscratch']` then `['myquota']` exactly as today. The decorated `storage_paths` keeps
its name, signature, `-> StoragePaths` annotation and docstring word for word, and its body becomes
`return resolve_storage_paths()`. FastMCP builds the served description and schemas from those, so
the served tool is unchanged (02 §6, probed). This is also the undecorated seam the GOAL allows
`generalize-storage-discovery` to reuse; nothing is designed for that cycle.

**The resource** (`src/rcac_mcp/resources.py`). `_storage_paths_resource` calls
`resolve_storage_paths()` (still a function-local import, which keeps importing `resources.py` from
pulling in the tool registry) and formats the same text as today; it stays parameterless and returns
`str`, so it stays a concrete `text/plain` resource. Each `RESOURCE_REGISTRY` entry gains a boolean
`'executor'` key: `False` for `rcac://context`, `True` for `rcac://storage`. Below the registry,
`OPEN_RESOURCES: Final[frozenset[str]]` is the set of URIs whose entry says `False`: resources that
run nothing and answer any client that can connect (§8). It reads `entry['executor']`, never
`.get('executor', False)`, so an entry without the key fails at import instead of being silently
exempt. `server.py` reads only the keys it already
reads; nothing it serves changes.

**The executor middlewares** (`src/rcac_mcp/middleware.py`).

- `SharedExecutorMiddleware`: a private `_install()` holds the one `set_executor(self._executor)`;
  `on_call_tool` and a new `on_read_resource` each call it and then `return await call_next(context)`.
  Every read sets the executor, the open one included: harmless, and it keeps the shared path
  identical for both message kinds.
- `AuthExecutorMiddleware`: the body of today's `on_call_tool` up to `call_next` moves into
  `async def _install(self, context) -> None`, unchanged in order and text: no token → return having
  set nothing; no identity claim → `RuntimeError`; identity absent from the map → `PermissionError`;
  otherwise `DelegatingExecutor(identity, self._user_map)`, `set_executor`, and the two
  request-scoped `set_state` calls. `on_call_tool` is `await self._install(context)` then
  `return await call_next(context)`, so a tool call behaves as before. `on_read_resource` calls
  `_install` only when `context.message.uri not in OPEN_RESOURCES`, then returns
  `await call_next(context)`. `context.message.uri` is a `str` and FastMCP resolves concrete
  resources by exact string, so the exemption covers exactly the reads that reach the context
  handler (01 §5). The middleware imports `OPEN_RESOURCES` from `rcac_mcp.resources`; nothing in
  `middleware.py` names a URI.
- `ToolErrorMiddleware`: the try/except moves into one module function,
  `_bounded(context, call_next, error, passes)`, that returns `await call_next(context)`, re-raises
  any exception in `passes`, and raises any other `Exception` as `error(str(exc)) from exc`.
  `on_call_tool` passes `ToolError` and `(FastMCPError,)`, exactly today's behaviour. A new
  `on_read_resource` passes `fastmcp.exceptions.ResourceError` and
  `(FastMCPError, NotFoundError, DisabledError)`: FastMCP raises `NotFoundError` for an unknown URI
  inside the middleware chain, and it subclasses plain `Exception`, so wrapping it would turn today's
  `-32602 Resource not found: '<uri>'` (with `data.uri`) into `-32603 Unknown resource: '<uri>'`, a
  served-surface change in every mode (adversarial review, finding 1). A `ResourceError` reaches the
  client as an `MCPError` carrying the same text in both eras (01 §3). It still catches
  `Exception`, never `BaseException`, and sets nothing. The class keeps its name (it is exported, the
  server adds it, and tests and § Invariants cite it); its docstring says it bounds tool calls and
  resource reads.

**Control flow of a read**, outermost first, as `create_mcp_server` adds them: boundary → executor
middleware (sets the executor, or refuses before the handler runs) → test middleware → handler on a
worker thread with a copy of the request's context → `resolve_storage_paths()` →
`get_executor().run(…)`. What each case gives the client:

| Mode, request | Read of `rcac://storage` | Read of `rcac://context` |
|---|---|---|
| `ssh` / `local` | the summary, from the shared executor | the startup text |
| `delegate`, mapped identity | the summary, run as the mapped user | the startup text |
| `delegate`, no token (in-memory only; HTTP answers 401 first) | `Error reading resource 'rcac://storage': No executor configured. …`, nothing run | the startup text |
| `delegate`, no identity claim | `Could not extract user identity from token claims. …`, nothing run | the startup text |
| `delegate`, unmapped identity | `User '<id>' is not authorized. Contact administrator to request access.`, nothing run | the startup text |

Each refusal carries the reason a `storage_paths` call from that request gets; only the tool's
`Error calling tool 'storage_paths': ` prefix differs in the no-token row.

**Test harness** (`tests/conftest.py`, `tests/harness.py`; 02 §1–2, §8).

- `RecordedPopen` gains an answer hook (a class attribute, like `answer_code`, mapping a launched
  command to the text it answers, default today's `<user>|<command>`), keeping the launcher framing in
  one place. A fixture or helper sets it to answer `findscratch` with `/scratch/test/<user>` and
  `myquota` with a per-user quota table.
- `Rendezvous` gains `on_read_resource` (the same barrier), so two reads are in flight together
  inside the executor middleware. The harness docstring's touchpoint list follows.

**Tests.** A new module, `tests/test_storage_resource.py` (`@mark.unit`, SPDX header, a docstring
stating the contract, an `AGENTS.md` § Testing entry), plus one test in `tests/test_context.py`:

| Test | What it asserts | R-ID |
|---|---|---|
| `test_storage_read_runs_on_the_shared_executor[legacy\|modern]` | over `shared_server` with a quota-answering `RecordingExecutor`, one in-memory client reads the resource and calls the tool: the text is exactly today's format; the executor ran `['findscratch']` then `['myquota']` for the read; home, scratch and every depot path in the text equal the tool's | R1, R5, R6 |
| `test_storage_read_runs_the_local_executor[legacy\|modern]` | the same read through a real `LocalExecutor` under `launches` with the answer hook: the summary returns and no launch carries a `sudo` prefix | R1, R6 |
| `test_storage_read_without_executor_middleware_fails[legacy\|modern]` | over `bare_server`, the read fails naming `No executor configured` and nothing runs | §1 |
| `test_storage_read_runs_as_the_mapped_user[legacy\|modern]` | delegate over HTTP with a minted token for a mapped identity, `launches` with the answer hook: both launches carry `sudo -n -H -u <mapped user>` and the text names that user's paths | R2, R6 |
| `test_concurrent_storage_reads_stay_isolated[legacy\|modern]` | two clients, alice and bob, read together behind `Rendezvous(2)`: each user's two launches ran as that user only, and each text names only its own user's paths | R2, R6 |
| `test_sequential_storage_reads_each_get_their_executor` | alice, bob, alice in turn on one server: each read ran as its own user | R2 |
| `test_storage_check_catches_crossing[…]` | drift control: the isolation check above flags a crossed user, a missing launch and a foreign path | R6 (check honesty) |
| `test_storage_read_refused[{no-token,no-claims,all-empty,unmapped,first-claim-unmapped}-{legacy,modern}]` | the read fails; its text contains the row's fixed reason fragment (`No executor configured`, `Could not extract user identity`, `is not authorized`) and the reason a `storage_paths` call on an identically built request returns (that call's text without its `Error calling tool …: ` prefix); `launches == []` | R3 |
| `test_storage_read_without_token_after_an_authenticated_read_fails[legacy\|modern]`, `test_storage_read_without_token_while_an_authenticated_read_is_in_flight[legacy\|modern]` | the read versions of `test_no_executor.py`'s stale-executor tests: a tokenless read on a delegate server that has served, or is serving, a mapped read finds no executor and runs nothing | R3, §1 |
| `test_unknown_uri_is_not_found[legacy\|modern]` | over `shared_server`, reading `rcac://nope` is still the protocol's `Resource not found` (code -32602) | §9 |
| `test_context.py::test_any_client_reads_the_context_in_delegate_mode[{no-token,no-claim,unmapped,mapped}-{legacy,modern}]` | the startup text, and `launches == []` | R4 |

The existing `rcac://context` guards in `test_context.py`, the tool's served-surface pin
(`test_surface.py::test_served_surface_matches_baseline`) and its argv pins
(`test_tools.py::test_tool_reaches_only_the_installed_executor[storage_paths]`,
`::test_slurm_and_site_argvs[storage-paths]`) run unchanged and guard R4 and R5.

**Mutants** (`tests/mutants.py`; each anchors on text that occurs once, the hook's `def` line
included where two hooks share a body):

| Case | Plant | Targets (why) |
|---|---|---|
| `resource-calls-decorated-tool` (new) | the handler calls the decorated `storage_paths` again | the shared read test (`not callable`) |
| `shared-read-sets-no-executor` (new) | `SharedExecutorMiddleware.on_read_resource` skips `_install` | the shared read test |
| `auth-read-sets-no-executor` (new) | `AuthExecutorMiddleware.on_read_resource` skips `_install` | the mapped-user read test, the unmapped refusal rows |
| `storage-read-left-open` (new) | `rcac://storage`'s entry says `'executor': False` | the unmapped refusal rows (`not authorized`) |
| `context-read-closed` (new) | `OPEN_RESOURCES` is empty | the R4 test's unmapped and no-claim rows |
| `read-boundary-dropped` (new) | `ToolErrorMiddleware.on_read_resource` returns `call_next` unguarded | the modern unmapped refusal row |
| `read-boundary-wraps-not-found` (new) | the read boundary passes only `FastMCPError` | the unknown-URI test |
| `read-no-token-reuses-last-executor` (new) | the delegate read hook remembers the executor it installed and sets it again for a tokenless read | the two tokenless-read stale-executor tests |
| existing `middleware.py` cases | re-planted on the refactored text; `isolation-executor-cached`, `unmapped-gets-default-user`, `no-claim-fallback-identity`, `no-token-fallback-identity` and `auth-middleware-sets-at-construction` also target the matching read test; `isolation-module-global` and `no-executor-module-global` (`context.py`) also target the concurrent-read and stale-executor read tests | as today |

The exact `why` fragments follow the tests' violation messages, which build writes; each case is run
and killed in its phase gate.

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1 | `resolve_storage_paths()` called by the handler; `SharedExecutorMiddleware.on_read_resource`; the shared and local read tests in both eras |
| R2 | `AuthExecutorMiddleware.on_read_resource` → the shared `_install` → a fresh `DelegatingExecutor` per read in the request's `ContextVar`; the mapped-user, concurrent and sequential read tests |
| R3 | `_install`'s refusals, shared with tool calls, raised before the handler; `ToolErrorMiddleware.on_read_resource` keeping the reason in the modern era; the no-token pass-through failing at `get_executor()` as a tool call does; `test_storage_read_refused` and the two stale-executor read tests |
| R4 | `OPEN_RESOURCES` (`rcac://context`) skipped by the delegate read hook; the handler unchanged; `test_any_client_reads_the_context_in_delegate_mode` plus the existing `test_context.py` guards |
| R5 | `storage_paths` keeps name, docstring, signature and annotation, its body the helper call; the served-surface and argv pins unchanged |
| R6 | `tests/test_storage_resource.py` in both eras and both middleware kinds, the R4 test, and the mutants each phase gate kills |
| R7 | `AGENTS.md` § Invariants §1 (reads set the executor in `on_read_resource`; the boundary bounds reads), §7 (the `TypeError` note gone, the helper named), §8 (the defect bullet replaced by how reads are served and refused), with the sections that restate them (§ Repository map, § Architecture, § Testing, `SECURITY.md` § Request Isolation) |

## 3. Invariant gate (AGENTS.md constitution check)

Walked before research and again against this design.

- **§1 Per-request executor isolation.** The executor stays in the `ContextVar`; it is set per read
  by middleware, never at construction or per connection, and a sync handler reads the copy of its
  request's context (01 §2, probed isolated under concurrency). No handler constructs or sets an
  executor. Every new hook returns `await call_next(context)`. The boundary still wraps the executor
  middleware; it gains a read hook that lets FastMCP's own not-found and disabled errors through, so
  only a failure raised around the read is rewrapped. §1's text changes under R7 to say so.
- **§4 Mode resolution.** No change to the ladder. The shared hook installs only the shared
  executor, and the delegate hook lives in `AuthExecutorMiddleware`, installed only in `delegate`
  mode; no delegate behaviour enters the shared path.
- **§5 Delegate mode.** Claim precedence, the no-claim `RuntimeError`, the unmapped
  `PermissionError` and the `DelegatingExecutor` re-check are the same code, moved once into
  `_install`, never copied. Reads run as the mapped user through the same `sudo -n -H -u` launch.
- **§7 Decorated tools are not callable.** The fix is the pattern §7 prescribes: an undecorated
  helper both callers use.
- **§8 Resources.** `rcac://context` keeps its handler, text and openness; its handler still calls
  neither `get_executor()` nor `set_executor()`. A read of `rcac://storage` is satisfied only by
  its request's own executor. No caching middleware or cache hint is added (01 §6), so one user's
  summary is never served to another.
- **§9 Agent-facing surface.** No tool, resource, description or instruction changes;
  `served_surface.json` is untouched and its test guards it. An unknown URI keeps its
  `Resource not found` protocol error (`test_unknown_uri_is_not_found`).
- **§2, §3.** The helper runs the same two argvs through `Executor.run` and reads `exit_code` as
  today.
- **§ Conventions.** Identity → executor stays in middleware; no comment or test carries a spec id;
  every new test is `@mark.unit`; the docs that restate §1 and §8 move in the commit that changes the
  behaviour they describe; a moved mutation anchor is re-planted in the same commit.

High-blast-radius paths touched: `src/rcac_mcp/middleware.py` (human-gated; also coupled core, so
every phase is `parallel: false` and review runs its debate variant). `context.py`, `server.py`,
`executor/*` and `__init__.py` are not changed.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| The delegate read hook exempts the URIs in `OPEN_RESOURCES` from identity resolution: a small allowlist on the security path. | R4 keeps `rcac://context` open to unmapped and identity-less clients while R3 refuses them `rcac://storage`; the middleware must tell the two apart before the handler runs. | (a) Refuse every read the way a tool call is refused: closes `rcac://context` to unmapped clients, against R4 and §8. (b) Defer the refusal into `context.py` (`get_executor()` raising a stored reason): moves the change into the highest-blast-radius file and changes `get_executor()`'s contract for every tool. (c) Resolve the identity in the handler: puts identity → executor outside middleware (§ Conventions) and copies §5's checks. |

Checked against the R-IDs it touches: R3 (the storage read is still refused with the tool call's
reason, before the handler), R4 (the context read is untouched, as R4 words it), R2 (mapped reads
still resolve per read). It changes no R-ID's SHALL. Its failure modes are closed: an executor-free
resource left off the set is refused to unmapped clients (visible, safe), and an executor resource
wrongly put on it finds no executor and fails with `No executor configured` (the
`storage-read-left-open` mutant pins that it is caught).

## 4. Rabbit holes (resolved)

- Does FastMCP 4.1.4 offer a hook that wraps the resource handler, and does a `ContextVar` set there
  reach a sync handler? → Yes: `on_read_resource`, before lookup; sync handlers run on an AnyIO
  worker with a copied context; probed per request and isolated under concurrency in both eras
  ([`research/01-fastmcp-resource-read.md`](research/01-fastmcp-resource-read.md) §1–2).
- Does a refusal raised in a read hook reach the client with its reason? → Not in the modern era
  (`Internal server error`) unless re-raised as a `FastMCPError`; hence the read boundary (01 §3,
  02 §4).
- Can a URI exemption be dodged by spelling? → No: the server sees a `str` and resolves by exact
  string; every variant probed was `Resource not found` (01 §5), and stays so after the fix because
  the read boundary passes `NotFoundError` through.
- `get_access_token()` in a read hook → identical to a tool call's; `None` in-memory (01 §4).
- Can the suite observe "as whom" for a read? → Yes, with an answer hook on `RecordedPopen` and a
  read-capable `Rendezvous` (02 §1–2).
- Does factoring the tool body change the served tool? → No, probed (02 §6).
- Mutation anchors in `middleware.py` would duplicate if hook bodies were copied → one shared private
  method per middleware (02 §7).
- **Adversarial design review** (code-plan trigger 3: R6 makes the suite the gate). A fresh reviewer
  given GOAL, this design and the drafted gates attacked both directions; it ran. Folded in:
  (1, MEDIUM) a read boundary passing only `FastMCPError` would rewrap FastMCP's `NotFoundError` and
  change every unknown URI's protocol error → `_bounded` takes the exceptions it passes, the read
  hook passes `NotFoundError` and `DisabledError`, plus `test_unknown_uri_is_not_found` and the
  `read-boundary-wraps-not-found` mutant; (2, MEDIUM) no read test caught a hook reusing a remembered
  executor for a tokenless read → the two stale-executor read tests, the
  `read-no-token-reuses-last-executor` mutant and retargeted `context.py` cases; (3) refusal rows
  also assert a fixed fragment, so an empty tool text cannot pass them; (4) `p3.sh docs` also refuses
  the stale §1 bullet, the diagram arrow and the absorbed seed's name; (5) `p2.sh` dedupes its case
  list; (6) `p3.sh` gains `full-legacy` and `full-modern` modes for the 10-minute cap; (8)
  `OPEN_RESOURCES` reads `entry['executor']` so a missing key fails at import. Held: the URI
  exemption, the copied context, the `_install` refactor's equivalence for tool calls, the plants the
  tests catch, the gates as shell, and the deviation row against R3 and R4.

## 5. Risks & open questions

- **Unknown URIs from refused callers.** The read hook runs before lookup, so an unmapped or
  identity-less caller reading an unknown URI in `delegate` mode gets the refusal, not
  `Resource not found` (01 §6); every other caller keeps `Resource not found`. A
  tool call to an unknown tool from such a caller behaves the same way today; no R-ID covers it, and
  it discloses nothing. §8's rewrite says so in one clause.
- **A nested read.** `ctx.read_resource` inside a tool would run the read hook inside the tool hook
  (01 §6). Nothing in the repo does it; the hook would resolve the same identity again.
- **Mutation re-planting** touches about sixteen existing `middleware.py` cases; each is re-run in
  P1 or P2's gate, so a stale anchor or a survivor is red there, not in review.
- **`ToolErrorMiddleware` now bounds reads under a tool-only name.** Kept to avoid churn in an
  exported, cited name; its docstring and §1 say what it covers.
- **The no-token row** is reachable only in-memory: over HTTP the auth layer answers 401 before any
  middleware. Its reason is today's tool-call reason, `No executor configured`, by the GOAL's
  non-goal on tool refusals.

## 6. Verification strategy

Each phase gate is a script in `spec/resource-reads-without-executor/verify/`, run one process at a
time:

- **P1** (`verify/p1.sh`): the new shared-mode read tests, the served-surface and storage argv pins,
  the mutation anchors and the hygiene checks, in the legacy era and again with
  `CLUSTER_MCP_TEST_ERA=modern`; then the new and re-planted shared-path mutants, each killed.
- **P2** (`verify/p2.sh`): the delegate read, concurrency, refusal, stale-executor, unknown-URI and
  R4 tests with the regression modules they share middleware with (`test_context.py`,
  `test_identity.py`, `test_isolation.py`, `test_no_executor.py`, `test_protocol.py`), in both eras;
  then every `middleware.py` and `context.py` case plus the new ones, deduped, each killed.
- **P3** (`verify/p3.sh`): the R7 document checks, then the profile's whole `verify` (lock check,
  the suite in both eras, `bin/sandbox.sh uv run rcac-mcp --help`). `p3.sh docs` runs the document
  checks alone; `full-legacy` and `full-modern` split the suite for a 10-minute command cap.

There is no CLI flow that reads a resource short of a client: the in-process harness client over the
real server builder, the real middleware and the real executors (with `Popen` recorded) is the drive,
and the sandboxed `--help` stays as the profile's smoke check.

---

*Backing research: [`research/00-digest.md`](research/00-digest.md).*
