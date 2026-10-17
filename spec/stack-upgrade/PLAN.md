# PLAN — Move to FastMCP 4 and the MCP SDK 2 with every pinned contract intact

> **Status:** Draft for review · **Last updated:** 2026-10-17 (adversarial review folded)
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Backing detail is in
> [`research/`](research/). Every design element traces to a GOAL R-ID.

## 1. Summary

A prototype (the `3d010ec` tree re-locked on `fastmcp` 4.1.0 / `mcp` 2.3.0) passes 296/296 tests
in both protocol eras and kills 53/53 planted violations in both, after five small source changes
and a harness port. So the cycle is mostly proof, not porting: move the lock only as far as the stack
and the audit require (and smoke-test the `ssh` executor, whose `paramiko` moves), fix the one real
behaviour change (a middleware refusal became a masked protocol error), hold the OIDC proxy's
posture at 2.x, keep tool descriptions byte-identical, then pin each GOAL contract with its own test and
mutation case: both eras (R2), the served surface against a `3d010ec` snapshot (R3), every
transport under the sandbox (R4), the auth checks (R5–R7), and a release-gate audit that fails
closed (R10). Seven vertical phases, `parallel: false` throughout; every gate runs the whole suite
in both eras and every mutation case.

## 2. Design

### 2.1 Stack and lock (R1)

`pyproject.toml`: `"fastmcp>=4,<5"`. The lock moves **only as far as it must** (foreman's ruling
on review finding 3): `uv lock --upgrade-package fastmcp --upgrade-package mcp`, plus whatever the
resolver forces, plus `--upgrade-package` for each package `uv audit` then reports, repeated until
the audit is clean; committed with the pin in P1 (§ Packaging same-commit rule). Every package whose
**major** version moves outside the stack is named in the P1 commit body with its reason; a reason
that is an advisory is written as "moved to the current release; selection recorded privately"
(public lane). On the prototype the majors that move are `fastmcp`, `mcp`, `starlette` (forced)
and, outside the stack, `cryptography` and `paramiko` (selection recorded privately). **`paramiko` drives the default `ssh` executor**,
which no gate exercised, so P1 adds an offline smoke test (2.6). P7's gate requires every moved major
to be named in a branch commit body. Lock format stays `revision = 5`; uv 0.12.17 (the CI pin) and
0.13.1 both read it ([06](research/06-lock-and-uv.md)). Later phases do not re-lock.

### 2.2 Source changes (all small; the coupled core keeps its shape)

| File | Change | Why |
|---|---|---|
| `src/rcac_mcp/middleware.py` | new `ToolErrorMiddleware`: `on_call_tool` returns `await call_next(context)`; re-raises `FastMCPError` untouched (FastMCP already turns it into an error result); re-raises any other `Exception`, `MCPError` included, as `ToolError(str(exc)) from exc`, the text exactly `str(exc)` (no traceback, no type name); never catches `BaseException`, so cancellation propagates | FastMCP 4 converts only tool-*body* exceptions into an `isError` result; a `PermissionError`/`RuntimeError`/`MCPError` raised in middleware reaches the client as JSON-RPC `-32603 Internal server error`, reason erased. 2.x returned `isError: true` with `str(exc)` for all three; the boundary restores exactly that (foreman's ruling on finding 6: parity for `MCPError` too) ([01](research/01-api-deltas.md) §3) |
| `src/rcac_mcp/server.py` | `create_mcp_server` adds `ToolErrorMiddleware()` **first**, before the caller's middleware | FastMCP wraps in reverse order, so the first added is outermost and sees what every later middleware raises |
| `src/rcac_mcp/middleware.py` | `await context.fastmcp_context.set_state(key, value, serializable=False)` (two lines) | `set_state` is async in 4.x; un-awaited it silently does nothing. `serializable=False` keeps 2.x's request scope |
| `src/rcac_mcp/tools/__init__.py` | `Tool.from_function(func, description=inspect.getdoc(func))` | FastMCP 4 parses docstrings and serves only the summary; this serves the full docstring, byte-identical to 2.x (§9) |
| `src/rcac_mcp/auth.py` | annotation `Final[Dict[str, Callable[[], AuthProvider \| None]]]` (the stray `:` removed; `\| None` because `'none'` returns `None`); the redundant local `OIDCProxy` import in `create_auth_oidc` removed; trailing blank line removed; `OIDCProxy(..., enable_cimd=False, forward_resource=False)` | R7; the module-level `OIDCProxy` becomes the one the function uses, so a test can replace it and prove nothing is built before the check (R6). 4.x `OIDCProxy` adds two behaviours 2.14 did not have, both on by default: fetching client-supplied metadata documents (CIMD) and forwarding the `resource` parameter upstream. Held at 2.x behaviour ("same auth posture"; foreman's ruling on finding 5) pending a deliberate decision, noted in §6 and `SECURITY.md` |

Nothing else in `src/` changes: `context.py`, `token.py`, `executor/*`, `__init__.py`,
`resources.py` and the tool modules are untouched. `-t sse` stays (FastMCP 4.1 serves it), so R4's
rejection path, and its `README.md`/`APP_HELP` edits, do not fire (`SECURITY.md` changes only for
the OIDC posture note). **Accepted 4.x behaviour change** (ruling on C1): a stateful streamable-HTTP
session now closes after 30 minutes idle (2.x: never); the SDK default is kept and recorded in
§ Project and §1's neighbourhood of § Invariants, and in the squash body.

### 2.3 Test harness (internals-bound item 1)

`tests/harness.py` stays the only test module that imports the stack:

- `httpx` → `httpx2`. `http_client` gains a response-status recorder (`event_hooks`); `call_http`
  returns `Outcome(True, '', 401)` only when the connect failed **and the last HTTP answer was a
  401** (a pure `rejection_status(statuses)` decides, with its own rows), and re-raises anything else
  (in 4.x the 401 arrives as an `MCPError` from the connect-time negotiation, not as
  `HTTPStatusError`).
- **Era selector.** `ERA = os.environ.get('CLUSTER_MCP_TEST_ERA', 'legacy')`; anything but
  `legacy`/`modern` raises at import. Every harness client is built with `mode='legacy'` or
  `mode='auto'`, and after connect the harness checks the negotiated era: legacy → a handshake
  version with an `InitializeResult`; modern → `2026-07-28` with none. A mismatch raises
  `RuntimeError('harness era: …')`, so an ignored selector fails loudly instead of running one era
  twice. The version pin (`mode='2026-07-28'`) is never used: it skips `server/discover`
  ([02](research/02-dual-era.md)). The selection is a pure `select_era(environ)` that raises
  `ValueError` naming `CLUSTER_MCP_TEST_ERA` for an unknown value.
- **Era evidence the gate reads** (review finding 2: a harness reading the wrong variable ran both
  passes in the legacy era and every check still passed). Every server the harness connects to
  carries a `MethodLog` (the builders add it; `in_memory`/`serving` attach one if absent), and when
  `CLUSTER_MCP_ERA_LOG` is set the harness appends one line per in-process connect:
  `era=<selected> version=<negotiated> first=<first method the server saw on that connection>`.
  `verify/era_log.py` then requires, per suite pass and per mutation pass, at least a floor of lines
  and every line consistent with the era (modern: `2026-07-28` via `server/discover`; legacy: a
  handshake version via `initialize`), and the gate runs `CLUSTER_MCP_TEST_ERA=bogus` and requires
  the run to stop naming the variable. Remote verbs (stdio/http/sse subprocesses) do not log.
- New verbs, each a thin, documented use of one FastMCP client feature: `negotiate` (era,
  instructions, tools and the methods a `MethodLog` middleware saw), `served_tools`,
  `served_instructions`, `served_surface` (the R3 shape, from a client), `stdio_tools` (refuses an
  argv whose first element is not this repo's `bin/sandbox.sh`, because FastMCP launches stdio
  servers where `sandbox_violations` cannot see), `url_tools` (http and sse), `installed_auth`.
  Remote verbs are not fenced (they make no in-process server call); in-process ones keep the fence.

`tests/test_registry.py` and `tests/test_instructions.py` read the served tools and instructions
through `served_tools`/`served_instructions` instead of the FastMCP server API (`get_tools()` is
gone in 4.x), with no test id changed; item 6 leaves the internals-bound list.
`tests/test_hygiene.py`: `STACK` widens to `('fastmcp', 'mcp', 'mcp_types', 'httpx', 'httpx2',
'httpcore2')` (the new stack's import names); `IMPORTERS` gains `importorskip`, `_imported_name` reads `modname=`,
and `from pytest import importorskip as …` aliases are tracked; the docstring says so. The new
negative controls go in a **new** test function, so no existing test's source changes.

### 2.4 New tests, one module per contract

| Module | Marker | Pins | Pure check (negative controls beside it) |
|---|---|---|---|
| `test_protocol.py` | unit | the boundary: a `PermissionError` (memory, HTTP), a `RuntimeError` and an `MCPError` raised in middleware each arrive as a tool error result whose text **equals** `str(exc)`; `CancelledError` propagates through the boundary (called directly); the harness era self-check and `select_era`; `rejection_status`; R2 per era and route; modern-era rows for delegate isolation, the tokenless refusal and a foreign token's 401 (so the default run keeps the modern era's §1/§5/§6 contracts) | `era_violations` |
| `test_ssh_smoke.py` | integration | the `ssh` executor on the moved `paramiko`/`fabric`: an in-process paramiko server on `127.0.0.1` (generated host and client keys, canned exec replies, no process launched) driven through `SSHExecutor`; asserts stdout, exit status and hostname come back. Isolated from the real machine: `HOME` under `tmp_path`, `SSH_AUTH_SOCK` unset, `look_for_keys=False`, `allow_agent=False`, fabric's SSH-config loading off | — |
| `test_surface.py` | unit | R3 against `tests/fixtures/served_surface.json` | `surface_violations`, `TOLERATED` |
| `test_transports.py` | integration | R4: stdio (both eras), http (both), sse (handshake) under `bin/sandbox.sh`, each listing `EXPECTED_TOOLS` | — (asserts names and negotiated era) |
| `test_auth_modes.py` | unit | R6 (eight one-missing rows; a positive control whose recorder **binds its keywords against `inspect.signature` of the real `OIDCProxy`**, so an unknown keyword fails, and asserts `enable_cimd=False`, `forward_resource=False`; `none` installs nothing), R7 (a `Callable` with exactly `[]` parameters: `Callable[..., X]` is rejected) | `oidc_violations`, `annotation_violations` |
| `test_audit.py` | unit + integration | R10's verdict function; the command names this checkout with `--project` and the child environment drops `UV_PROJECT` and every other non-allowlisted `UV_*` (finding 1); the real script fails closed offline **by construction** (`UV_OFFLINE=1` and dead loopback proxies; asserts uv's own "requires network access … offline mode" message, so no request was attempted) | `audit_violations`, `child_env` (in `bin/audit_lock.py`) |

**R3's comparison** (`surface_violations(snapshot, served)`): tool name set equal; description
equal; per tool, argument names, `required`, and each property's schema with its `description`
key removed equal; top-level input-schema keys equal except `additionalProperties`, which must be
**exactly `false`** where it was added (a planted `true` is a violation); output schema equal after
inlining the 2.x `$defs`, ignoring only a `description` key on a node that was a `$ref` target in
2.x; resource URIs, names, descriptions and MIME types equal; instructions equal (in whichever era
the run selects). `TOLERATED` names each accepted difference kind with its cause:
`argument-description` (FastMCP 4 copies each docstring's `Args:` line into its property),
`additional-properties` (FastMCP 4 advertises the unknown-argument rejection both stacks already
enforce), `output-defs-inlined` (FastMCP 4 dereferences `$defs`), `output-model-description`
(dereferencing carries the model class's docstring onto the inlined node: `list_directory`'s items,
`storage_paths` and its items; review finding 4). A `description` on any other output node, or any
other difference, is a violation. The squash body lists the tolerated differences per tool (`tolerated_differences`), plus
the `_meta` key rename (`_fastmcp` → `fastmcp`), which R3 does not cover.

**The snapshot.** `spec/stack-upgrade/verify/snapshot.py`, run in an archive of `3d010ec` in its
own locked 2.x environment, writes `tests/fixtures/served_surface.json` (`tests/fixtures/` is
already excluded from the sdist). Every gate from P3 re-runs it there and requires the committed
fixture to be identical, so the fixture cannot drift toward the new stack.

### 2.5 The dependency audit (R10)

`bin/audit_lock.py` (stdlib; the house pattern of the ci-workflow cycle's `bin/sdist_hygiene.py`):
runs `uv audit --frozen --no-config --preview-features audit-command --project <this checkout>`
with `child_env(os.environ)` (every `UV_*` removed but `UV_CACHE_DIR`, `UV_OFFLINE`, `UV_NATIVE_TLS`,
`UV_SYSTEM_CERTS`: `bin/sandbox.sh` exports `UV_PROJECT`, and review finding 1 showed the unpinned
command audited whatever tree that named) and decides with
`audit_violations(returncode, output, lock_text)`:

- any finding line, or exit 1 → **1**, uv's report printed (package, version, advisory);
- any other non-zero → **2**, "advisory source unreachable" when uv says so, else "the audit could
  not run";
- exit 0 → green only when uv's no-findings summary is present **and** its package count equals the
  lock's registry packages; otherwise **3** (fail closed if uv's wording changes or it audits a
  subset).

`--no-config` stops a user or system `uv.toml` adding ignores or a service URL; the script takes no
options, so there is no waiver path. It runs as `- uv run python bin/audit_lock.py` in the release
recipe's `gate`, right after `uv lock --check`, and as its own step in `.github/workflows/ci.yml`
when that file exists on the base this cycle lands on (the foreman rebases before P6). It is never
in the profile's `verify`. Draft: [`research/prototypes/audit_lock.py`](research/prototypes/audit_lock.py)
(probed: 0 on the prototype lock, 1 on a planted lock, 2 offline).

### 2.6 The `ssh` executor smoke (finding 3's condition)

`paramiko` moves a major (4 → 5), and `fabric`/`paramiko` carry the default `ssh`
executor, which nothing in the suite ran. `tests/test_ssh_smoke.py` (integration, offline, loopback
only) drives `SSHExecutor` against an in-process `paramiko` server; the prototype
([`research/prototypes/ssh_smoke.py`](research/prototypes/ssh_smoke.py)) returns
`CommandResult(stdout='smoke:echo hi', exit_code=3, hostname='127.0.0.1')` on paramiko 5.0.0 and
4.0.0 alike. Mutation case `ssh-exit-status-dropped` (`exit_code=result.exited` → `exit_code=0`)
proves it pins the result mapping.

### 2.7 `AGENTS.md` (R11), each part in the commit whose code it describes

P1: § Project's stack line (FastMCP 4.x, MCP SDK 2.x) and the 30-minute HTTP session idle expiry as
a 4.x behaviour change, the repository map's `middleware.py` row,
§1 (the boundary as outermost middleware and the new-middleware rule; a sync tool runs on a worker
thread with a copy of the request context), §7 (`fastmcp.tools.function_tool.FunctionTool`, still
not callable; the function is on `.fn`), § Testing (harness touchpoints, `httpx2`, the era selector,
the import fence's names and `importorskip`, item 6 retired). P2: § Project's two eras; § Testing's
`test_protocol.py`. P3: §7/§9 (the full docstring is the description; `Args:` also lands in the
property descriptions), § Testing's `test_surface.py` and fixture. P4: § Project's transports (sse
is handshake-only), § Testing's `test_transports.py`. P5: §6 (provider types and import paths;
`OIDCProxy`'s `client_secret` is optional upstream but required here; CIMD and resource forwarding
held off at 2.x behaviour pending a decision; the same note in `SECURITY.md`), the `AUTH_MODES` footgun
line (the PEP 563 claim is false and the typo is fixed), § Testing's `test_auth_modes.py`. P6:
§ Factory → Release recipe `gate` plus a caveat (fails closed, no waiver, needs the network),
§ Packaging's "no CI" lines if still present, § Testing's `test_audit.py`. The high-blast-radius
list only widens.

### Requirement → design map

| R-ID | Design element(s) | Phase |
|------|-------------------|-------|
| R1 | 2.1: pin + minimal lock move; gate parses both; P7 names every moved major | P1 |
| R2 | no server change; harness `negotiate`/`MethodLog`; `test_protocol.py::test_client_era_is_served[…]` per era × route; `instructions-dropped` case | P2 |
| R3 | `snapshot.py` → fixture; `test_surface.py`; `description=inspect.getdoc`; `TOLERATED`; squash-body list | P3 |
| R4 | `test_transports.py` (5 rows); sse survives, so no rejection path; `sse-transport-unserved` case | P4 |
| R5 | existing `test_tokens.py` ids, both eras, its 10 cases (the module is held to additions only); the harness's 401 recorder; gate CLI drives | P1 (net), P5 (gated) |
| R6 | `test_auth_modes.py` oidc rows + signature-bound positive control + posture + `none`; local import removed; 5 cases | P5 |
| R7 | annotation fixed; `test_auth_modes_annotation_is_a_provider_factory_map`; `auth-modes-annotation-slice` | P5 |
| R8 | every phase: the 296 baseline ids (collected live from `3d010ec`) pass in both eras, each pass proven by the era log; `edits.py` (only the harness, the case table and the two item-6 modules may change existing lines; `test_hygiene.py` only its import check); harness-only imports with the widened fence and `importorskip` | P1–P7 |
| R9 | every phase: all cases incl. the 53 baseline ones, `--self-check`, era-logged; P1 and P7 also in the modern era; R6/R7 cases; P7 requires every base case whose `file`, `edits`, `targets` or `why` changed to be named in a commit body | P1–P7 |
| R10 | 2.5; `test_audit.py`; `gate.sh P6 --audit` proofs; CI step if present | P6 |
| R11 | 2.7, per phase; P7 sweeps | P1–P7 |

## 3. Invariant gate (AGENTS.md constitution check)

Walked before research and again against this design. Sections touched: §1, §5, §6, §7, §9,
§ Conventions; §4 and the high-blast `__init__.py` only through mutation anchors (no code change);
§2, §3, §8 untouched. High-blast paths edited: `middleware.py`, `server.py`, `auth.py`
(`context.py`, `token.py`, `executor/*`, `__init__.py` and `bin/sandbox.sh` are not; the gate
fails if `bin/sandbox.sh` changes).

- **§1** — the executor stays in the `ContextVar`; `on_call_tool` still fires once per `tools/call`
  in both eras (probed); sync tools run on a worker thread that receives a copy of the request
  context, so isolation holds and every §1 case is killed in both eras. The boundary returns
  `await call_next(context)` and sets nothing.
- **§5** — claim precedence, the user-map refusal and `DelegatingExecutor`'s re-check are untouched;
  their exceptions keep their types; the boundary only changes how the client sees them (back to
  2.x). Identity state is request-scoped.
- **§6** — both `JWT_SECRET` floors and the `token.py` constants are untouched; the verifier is
  built with the same keywords; R6's all-or-nothing check is unchanged and now pinned; the OIDC
  proxy's two new upstream behaviours (CIMD fetches, resource forwarding) are switched off so the
  auth posture is the 2.x one, and the test asserts it.
- **§7** — import-time registration is untouched; the decorator passes the full docstring; the tool
  type is still not callable (recorded, not fixed: `storage-paths-resource-typeerror` follows).
- **§9** — tool names, arguments, docstrings, `SERVER_INSTRUCTIONS` and resources are unchanged and
  now pinned against `3d010ec`.
- **§ Conventions** — `uv.lock` with the pin in one commit; `AGENTS.md` with each code change; no
  spec ids in comments (gated); CLI drives under `bin/sandbox.sh`; CI mirrors the gate.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| A new middleware in the coupled core (`ToolErrorMiddleware`) | 4.x masks every exception raised around a tool call as `Internal server error`: a refused delegate call would lose its reason, a client-visible change and a regression of what the identity tests pin | raising `ToolError` inside each executor middleware rewrites §5's documented exception types, moves anchored lines, and leaves the next middleware (and the harness's `Rendezvous`) to rediscover the trap |
| A test-only environment selector (`CLUSTER_MCP_TEST_ERA`) | the contract tests must hold in both eras, and R8 forbids renaming ids, which parametrizing by era would do | no selector leaves the modern era of §1/§5/§6 unproven; a profile-`verify` change is a wider edit (it drags the CI workflow along) |
| `tests/test_hygiene.py`'s `STACK` widened (an edit outside the internals-bound list) | the stack's import names changed (`httpx2`, `mcp_types`); without them a test module could import the new stack unseen | R8 excepts `test_hygiene.py` for exactly this clause; every existing `test_*` function stays byte-identical (gated) |

## 4. Rabbit holes (resolved)

- API deltas for everything the repo touches → five real changes, everything else identical
  ([01](research/01-api-deltas.md)).
- Dual-era serving and testing → the server needs nothing; `legacy` and `auto` (+ check) clients;
  never the pin ([02](research/02-dual-era.md)).
- The ContextVar contract under per-message middleware → §1 holds as written
  ([03](research/03-executor-contextvar.md)).
- The internals-bound list → item 1 rewritten, 2–5 unchanged, 6 moves to verbs; two harness hazards
  (stdio launches unseen by the static check; the sandbox does not forward SIGTERM: drives use
  `start_new_session` and `killpg`) ([04](research/04-test-suite.md)).
- The audit → `uv audit` behind `bin/audit_lock.py`; fails closed; count cross-check
  ([05](research/05-dependency-audit.md)).
- Lock and uv → whole-tree upgrade; revision 5; CI's uv reads it ([06](research/06-lock-and-uv.md)).
- **Adversarial design review** (2026-10-17, run by the foreman against a copy of the prototype,
  executed; trigger 3). Seven findings, all folded:
  1. HIGH — the audit followed `UV_PROJECT` (exported by the sandbox): a planted lock audited
     green, the real one failed on a count mismatch → `--project <this checkout>`, `child_env`, a
     test row, and the `--audit` proof re-run with `UV_PROJECT` pointing elsewhere.
  2. HIGH — nothing proved the modern passes ran modern (a mis-wired selector or a version pin
     passed) → the era log, `era_log.py` with a floor, the `bogus` selector control.
  3. MEDIUM — whole-tree upgrade moved untested majors → stack-only move (ruling), majors named in
     the P1 commit body and checked at P7, and the SSH smoke because `paramiko` moves.
  4. MEDIUM — R3 would fail the good build (model docstrings on inlined output nodes) →
     `output-model-description`; `additionalProperties` must be exactly `false`.
  5. MEDIUM — `OIDCProxy` widened the posture (CIMD, resource forwarding) → held off (ruling), the
     recorder binds against the real signature and asserts both.
  6. MEDIUM — the boundary's text and breadth were unpinned → exact text, a cancellation row,
     `boundary-leaks-traceback`, `boundary-catches-base-exception`; `MCPError` converted for
     parity (ruling) with `boundary-reraises-mcp-error`.
  7. MEDIUM — `edits.py` exempted modules that need no edit → only four modules exempt; P7's
     retarget check compares `file` and `edits` too.
  LOW, folded: `call_http`'s 401 must be the last answer; `httpcore2` in `STACK`; `Callable[..., X]`
  rejected; the offline audit test offline by construction. Held up under attack and kept: uv
  0.12.17's `uv audit` (same flags and summary), the count cross-check under `UV_NO_DEV`,
  `inspect.getdoc` reproducing all 23 descriptions, auto mode 296/296, the network guard, kills in
  both eras, ids cannot drop unnoticed.

## 5. Risks & open questions

- **HTTP session idle expiry** (ruled, C1). The MCP SDK 2.2+ closes a stateful streamable-HTTP
  session after 30 minutes idle (2.x: never); a legacy HTTP client idle that long re-initializes.
  Kept, recorded in `AGENTS.md` and the squash body.
- **`MCPError` parity vs SEP-2575.** The boundary turns every `MCPError` raised around a tool call
  into an error result, as 2.x did, including a missing-client-capability error that 4.x would put on
  the wire as `-32021`. No tool here requires a client capability; a later cycle that adds one
  revisits the boundary.
- **The lock is time-dependent.** P1's `uv lock --upgrade` may pick newer releases than the
  prototype did. Every gate re-proves the suite and cases on the committed lock; P6's networked
  proof re-audits it. A release published between P1 and landing that breaks nothing is fine; one
  that carries an advisory turns the release gate red, by design (no waiver).
- **`uv audit` is experimental.** A wording change makes the script exit 3 (fail closed) and blocks
  a release until it is updated; acceptable for a gate.
- **ci-workflow ordering.** Its static checker binds `ci.yml` to the gate lists verbatim; P6 must
  run after the foreman's rebase so the audit step is added to both lists in one commit. If
  ci-workflow has not landed by P6, R10's CI clause is vacuous and P6 notes it for ci-workflow.
- **OIDC live flow** stays untested (upstream changed issuer identity to `issuer_url`, defaulting
  from `base_url`); R6 pins only the configuration check.
- **Pre-existing, out of scope:** resource reads never get an executor (`on_call_tool` only), on
  2.x and 4.x alike; P7 seeds `issues/resource-reads-without-executor.md`.

### Clarifications (ruled by the foreman 2026-10-17; recorded in `GOAL.md`)

- **C1** — keep the SDK's 30-minute idle default; record it as a 4.x behaviour change.
- **C2** — R3's list goes in the squash commit body (landing is `squash-local`, no PR).
- **C3** — R8's `test_hygiene.py` exception covers widening `STACK` to the new import names.
- **C4** — R2's "no `initialize`" = the server saw no `initialize` on that connection; "answer
  `server/discover` with the instructions" = the server saw `server/discover` and the client's
  instructions came from its `DiscoverResult`.
- **C5** — accepted only offline by construction: `UV_OFFLINE=1`, dead loopback proxies, and uv's
  own offline refusal asserted.
- **Lock scope** (finding 3) — stack-only, plus forced and audit-flagged packages; every moved major
  named with its reason; the SSH smoke because `paramiko` moves.
- **Posture parity** (finding 5, 6) — `OIDCProxy` CIMD and resource forwarding off; `MCPError`
  around a tool call becomes an error result as on 2.x.

## 6. Verification strategy

One cumulative gate, `sh spec/stack-upgrade/verify/gate.sh P<n>`, inside `bin/sandbox.sh`
([`verify/`](verify/)): scope (only cycle paths; `bin/sandbox.sh` untouched; no spec ids in
comments) → R1 (pin, majors, `uv lock --check`, `uv sync --locked`) → the baseline (an archive of
`3d010ec` in its own 2.x environment: its 296 ids, its 53 case ids, and from P3 its served surface)
→ marker witness → the suite twice (no selector, then `CLUSTER_MCP_TEST_ERA=modern`), each JUnit
report holding every baseline id and every phase id PASSED and each era log proving its era, plus
the `bogus` selector control → `edits.py` (R8's edit rule) →
`controls.py` (case table, and negative controls on the gate's own checkers) → every mutation case
with `--self-check`, era-logged (also in the modern era at P1 and P7) → CLI drives (help lists the three
transports; a bare stdio server fails closed; from P3 the fixture equals the baseline surface; from
P5 the secret floors and the OIDC refusal naming all four; from P6 the audit wiring and its offline
refusal by construction) → P7: document and ledger checks, changed cases and moved majors named in
a commit body, a fresh clone
with `UV_PROJECT=$PWD` running both eras and every case. `gate.sh P6 --audit <planted-dir>` (networked, run by
build at P6 and P7) proves green on the shipped lock, red on a planted lock (also with
`UV_PROJECT` pointing at the shipped tree) and red offline. The
planted project lives outside the repo; build prepares it and records which version it pins in
the private build log, as it does the gate's output. The gate was dry-run end to end on the prototype
(green at P1 in 3 min 44 s with P1's own new ids blanked).

---

*Backing research: [`research/00-digest.md`](research/00-digest.md).*
