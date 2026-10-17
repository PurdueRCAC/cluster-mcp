---
slug: stack-upgrade
title: Move to FastMCP 4 and the MCP SDK 2 with every pinned contract intact
kind: refactor
appetite: big
status: done
branch: refactor/stack-upgrade
base: develop
current_phase: done
last_updated: '2026-10-17'
phases:
- id: P1
  name: The stack moves and the regression net holds
  status: done
  satisfies:
  - R1
  - R8
  - R9
  - R11
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: sh spec/stack-upgrade/verify/gate.sh P7
- id: P2
  name: Both protocol eras, each pinned
  status: done
  satisfies:
  - R2
  - R8
  - R9
  - R11
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/stack-upgrade/verify/gate.sh P2
- id: P3
  name: The served surface matches 3d010ec
  status: done
  satisfies:
  - R3
  - R8
  - R9
  - R11
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/stack-upgrade/verify/gate.sh P3
- id: P4
  name: Every transport starts in the sandbox and lists the tools
  status: done
  satisfies:
  - R4
  - R8
  - R9
  - R11
  depends_on:
  - P3
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/stack-upgrade/verify/gate.sh P4
- id: P5
  name: Auth on the new provider API, the OIDC check and the annotation pinned
  status: done
  satisfies:
  - R5
  - R6
  - R7
  - R8
  - R9
  - R11
  depends_on:
  - P4
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/stack-upgrade/verify/gate.sh P7
- id: P6
  name: The release gate refuses a lock with a known advisory
  status: done
  satisfies:
  - R10
  - R8
  - R9
  - R11
  depends_on:
  - P5
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/stack-upgrade/verify/gate.sh P7
- id: P7
  name: Closeout, deferral ledger and the fresh-clone run
  status: done
  satisfies:
  - R8
  - R9
  - R11
  depends_on:
  - P6
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/stack-upgrade/verify/gate.sh P7
review:
  last_reviewed_commit: a207f9577699f61f1620107e1633e3834b0554df
  verdict: approved
  blocked_reason: ''
  cycle: 3
---

# TECH.md — Move to FastMCP 4 and the MCP SDK 2 with every pinned contract intact

The **context engine and finite-state machine** for building this cycle. The YAML frontmatter
above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/stack-upgrade/TECH.md`); the
per-phase checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via `uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`,
and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** [`research/00-digest.md`](research/00-digest.md) + briefs; the audit
  script's draft is [`research/prototypes/audit_lock.py`](research/prototypes/audit_lock.py).

## Frontmatter field reference

- `status` (top): `planned | in_progress | blocked | in_review | done` (`done` is stamped by
  `code-publish` after confirmation, just before landing — the terminal state of the retained record)
- `appetite`: `small | big` — caps phase count and build-iteration budget (circuit breaker).
- `branch`, `base`: the cycle's branch and the profile's `base`.
- phase `status`: `pending | in_progress | done | blocked`
- `satisfies`: GOAL R-IDs this phase delivers (traceability anchor for `code-review`). R8, R9 and
  R11 recur: every phase re-proves the regression net (R8, R9) and updates the `AGENTS.md` lines its
  own code moves (R11).
- `depends_on`: phase ids that must be `done` first.
- `parallel`: `false` throughout: every phase touches the coupled core or the suite that pins it.
- `hammerable`: `false` throughout: each phase is a correctness or gate deliverable.
- `hill`: `uphill` → `crest` → `downhill`.
- `attempts`: durable failed-verify counter, bumped by `set_phase.py --phase P<n> --record-attempt`.
- `verify`: the cumulative phase gate; see "The gate" below.
- `review.cycle`: completed review passes.

## The gate (every phase)

`sh spec/stack-upgrade/verify/gate.sh P<n>` runs inside `bin/sandbox.sh` and, cumulatively:
scope (only this cycle's paths; `bin/sandbox.sh` untouched; no `R#`/`P#` in comments under `src/`
or `tests/`) → R1 (the pin is exactly `fastmcp>=4,<5`; the lock resolves `fastmcp` 4.x and `mcp`
2.x and no `httpx`; `uv lock --check`; `uv sync --locked`) → the baseline: an archive of `3d010ec`
synced in its own 2.x environment yields its 296 ids, its 53 mutation case ids and (P3+) its served
surface → marker witness → the suite with no era selector, then with `CLUSTER_MCP_TEST_ERA=modern`,
each JUnit report holding every baseline id and every `verify/ids/P1..P<n>.txt` id PASSED and
nothing skipped, failed or errored, and each pass's `CLUSTER_MCP_ERA_LOG` proving its era
(`verify/era_log.py`: at least `SUITE_CONNECTS` connects, every one modern via `server/discover` or
legacy via `initialize`); `CLUSTER_MCP_TEST_ERA=bogus` must stop the run naming the variable →
`verify/edits.py` (R8: only `harness.py`, `mutants.py`, `test_registry.py` and
`test_instructions.py` may change existing lines; `test_hygiene.py` only its stack-import check;
every other module, `test_tokens.py`, `test_exec_mode.py`, `test_executors.py` and
`test_mutations.py` included, gains lines only) →
`verify/controls.py` (every baseline case still present; every case P1..P<n> owns exists and
targets a required id; negative controls on `ids_check`, `edits`, and from P3 `surface_violations`,
from P6 `audit_violations`, `COMMAND`, `child_env`) → **every** case in `tests/mutants.py` with
`--self-check`, era-logged (`MUTANT_CONNECTS`; P1 and P7 also in the modern era) → CLI drives.
Raise `SUITE_CONNECTS`/`MUTANT_CONNECTS` in `run.sh` to the counts P1 measures (rounded down to a
round number); never lower them. *Amendment (P1 build, 2026-10-17):* the planned placeholder
`SUITE_CONNECTS=100` sat above what the suite can log (P1 measured 81 in-process connects per pass,
in both eras), so the first P1 run failed on the floor alone; it is set to 80, and
`MUTANT_CONNECTS` raised from 30 to 50 (measured 55 legacy, 53 modern). The era log records the
first *request* each connection's server saw: the previous connection's `notifications/initialized`
is unanswered and can land after the next connect begins. **Paste the mutation report into the phase commit body.**

`gate.sh P6 --audit <planted-dir>` and `gate.sh P7 --audit <planted-dir>` are the networked R10
proofs (green on the shipped lock; red, naming package, version and advisory, on a planted lock,
also with `UV_PROJECT` naming the shipped tree; red offline by construction). The planted directory is outside the repo: a `pyproject.toml` and a `uv.lock`
pinning a version with a published advisory, prepared by build. Their
output goes to the **private build log only**: never a commit body, the squash body, or a file
under `spec/`. No committed file names an advisory or calls a locked version vulnerable.

## Conventions (apply to every phase)

- `AGENTS.md` is the constitution; walk § Invariants §1, §5, §6, §7, §9 and § Conventions for the
  lines each phase touches. Comments state the invariant or the why, never an `R#`/`P#`.
- One phase per `code-build` invocation; one atomic commit with the code and the `TECH.md` state
  change; subject `[refactor] Build stack-upgrade P<n>: …`; no `Co-Authored-By:` trailer. No pushes.
- Same-commit rules: `uv.lock` with `pyproject.toml`; each `AGENTS.md` line with the code it
  describes (R11); a new mutation case with the test it targets; a moved anchor re-planted in the
  commit that moves it, its reason in the commit body when the case's targets or `why` change (R9).
- Every new test carries `@pytest.mark.unit` or `@pytest.mark.integration`, speaks harness verbs
  only, and sits beside a pure `*_violations` check with planted negative controls.
- A test id collected at `3d010ec` is never renamed, removed or skipped.

---

## Phase P1 — The stack moves and the regression net holds
**Satisfies:** R1, R8, R9, R11 · **Depends on:** —
**Goal:** the server runs on FastMCP 4.x / MCP SDK 2.x, and the existing 296 tests and 53 cases
pass and are killed in both protocol eras, with the one behaviour change the move introduced fixed.

- [x] `pyproject.toml`: `"fastmcp>=4,<5"`. Lock **only as far as it must** (foreman's ruling):
      `uv lock --upgrade-package fastmcp --upgrade-package mcp`; then `uv audit --frozen --no-config
      --preview-features audit-command` and add `--upgrade-package <name>` for each package it
      reports, repeating until clean (the audit output stays in the private build log). `uv sync
      --locked`. In the commit body, list **every package whose major version moved** with its reason:
      "the stack" (`fastmcp`, `mcp`), "required by fastmcp 4" (e.g. `starlette`), or, for an
      audit-driven move, "moved to the current release; selection recorded privately" (never name an
      advisory). P7's gate fails on a moved major no commit body names.
- [x] If `paramiko` or `fabric` moved (the prototype moves `paramiko` 4 → 5): new
      `tests/test_ssh_smoke.py` (integration) from `research/prototypes/ssh_smoke.py`:
      `test_ssh_executor_runs_over_a_loopback_server` drives `SSHExecutor('127.0.0.1', port=…,
      user=…, connect_kwargs={'pkey': …, 'look_for_keys': False, 'allow_agent': False})` with fabric's
      SSH-config loading off, `HOME` under `tmp_path`, `SSH_AUTH_SOCK` unset, against an in-process
      paramiko server bound to `127.0.0.1` that answers exec requests with canned output and a
      non-zero exit status (no process launched); asserts stdout, exit status and hostname, and that
      the server received the exact command. Mutation case `ssh-exit-status-dropped`
      (`exit_code=result.exited,` → `exit_code=0,` in `executor/ssh.py`; why = the test's exit-status
      message). If neither moved, record that in the commit body and drop the id and case from
      `verify/` in the same commit.
- [x] `middleware.py`: add `ToolErrorMiddleware` (`on_call_tool`: `return await call_next(context)`;
      `except FastMCPError: raise`; `except Exception as exc: raise ToolError(str(exc)) from exc`, so
      an `MCPError` becomes an error result as on 2.x and a `BaseException` such as
      `CancelledError` propagates; the text is exactly `str(exc)`), with a docstring stating why
      (FastMCP 4 masks an exception raised outside the tool body). Await both `set_state` calls with
      `serializable=False`.
- [x] `server.py`: `create_mcp_server` adds `ToolErrorMiddleware()` before the caller's middleware.
- [x] `tests/harness.py`: `httpx2`; the response-status recorder, `rejection_status(statuses)` (401
      only when the **last** answer was 401) and `call_http`'s 401 path; `select_era(environ)`
      (`CLUSTER_MCP_TEST_ERA`, default `legacy`; an unknown value raises `ValueError` naming the
      variable) applied at import to every client, with the post-connect era check; `MethodLog` on
      every server it connects to (builders add it; `in_memory`/`serving` attach one if absent) and,
      when `CLUSTER_MCP_ERA_LOG` is set, one appended line per in-process connect
      (`era=… version=… first=…`, the first method the server saw on that connection);
      `served_tools`, `served_instructions`; `protocol_error(message)` (an `MCPError` for the boundary
      row). Module docstring lists the stack touchpoints it now relies on.
- [x] `tests/test_registry.py::test_served_tools_match_registry` and
      `tests/test_instructions.py::_served_instructions`: read through the new verbs (ids unchanged).
- [x] `tests/test_hygiene.py`: `STACK` += `mcp_types`, `httpx2`, `httpcore2`; `IMPORTERS` += `importorskip`;
      `_imported_name` reads `modname=`; `from pytest import importorskip as …` aliases tracked;
      docstring updated; new function `test_stack_import_check_catches_new_stack_names` (ids in
      `verify/ids/P1.txt`). No existing `test_*` function changes.
- [x] New `tests/test_protocol.py`: `test_middleware_refusal_is_a_tool_error_result[permission-memory|
      permission-http|runtime-memory|mcp-error-memory]` (a middleware raising that exception yields
      `Outcome(is_error=True)` whose text **equals** `str(exc)`; a raised exception is reported as
      `protocol error instead of a tool error result: …`; a different text as `error text differs`);
      `test_boundary_lets_cancellation_through` (calls `ToolErrorMiddleware().on_call_tool` directly
      with a `call_next` raising `asyncio.CancelledError`; anything but that propagating is
      `swallowed cancellation`); `test_harness_clients_speak_the_selected_era`;
      `test_harness_refuses_an_unknown_era`; `test_http_rejection_is_the_last_answer[…]`.
- [x] `tests/mutants.py`: `tool-error-boundary-dropped` (drop the boundary's `add_middleware`;
      targets the four refusal rows; `why='protocol error instead of a tool error result'`),
      `boundary-leaks-traceback` (`str(exc)` → `str(exc) + traceback.format_exc()`; `why='error text
      differs'`), `boundary-catches-base-exception` (`except Exception` → `except BaseException`;
      target the cancellation row; `why='swallowed cancellation'`), `boundary-reraises-mcp-error`
      (`MCPError` back in the re-raise; target `[mcp-error-memory]`), and `ssh-exit-status-dropped`
      (above). Re-check every existing anchor; none is expected to move (any re-plant and its reason
      in the commit body).
- [x] `AGENTS.md`: § Project stack line (FastMCP 4.x, MCP SDK 2.x; eras come in P2) and the accepted
      4.x behaviour change (a streamable-HTTP session closes after 30 minutes idle; 2.x never closed
      it); repository-map `middleware.py` row; §1 (boundary outermost; worker-thread context copy; "one per request");
      §7 (`fastmcp.tools.function_tool.FunctionTool`, not callable, function on `.fn`); § Testing
      (harness touchpoints, `httpx2`, era selector and era log, fence names and `importorskip`,
      item 6 retired, `test_protocol.py`, `test_ssh_smoke.py`).
- **Verify:** `sh spec/stack-upgrade/verify/gate.sh P1`.
- **Touches:** `pyproject.toml`, `uv.lock`, `src/rcac_mcp/middleware.py`, `src/rcac_mcp/server.py`,
  `tests/harness.py`, `tests/test_registry.py`, `tests/test_instructions.py`, `tests/test_hygiene.py`,
  `tests/test_protocol.py`, `tests/test_ssh_smoke.py`, `tests/mutants.py`, `AGENTS.md`.

*Remediation (review cycle 1, F3, 2026-10-17):* `AGENTS.md` §1 states that middleware state is
request-scoped, and nothing pinned it: a plant dropping `serializable=False` passed the suite.
- [x] Harness: `StateProbe(*keys)` (an `on_request` middleware recording each request's method and
      the context state each key holds as it arrives) and `tool_names(client)` (a tool listing on a
      connected client: a later request on the same session that no executor middleware sees).
- [x] `test_protocol.py`: `state_scope_violations(seen, expected)` (the tool call sees the identity
      the delegate middleware stored, so its later absence is not vacuous; no later request sees any
      of it); `test_delegate_state_is_request_scoped[legacy|modern]` (a delegate session over HTTP:
      a call, then a listing); planted controls `test_state_scope_check_catches_drift[leaked|
      never-set|no-later-request|no-call]`. Ids join `verify/ids/P1.txt`.
- [x] `tests/mutants.py`: `delegate-state-session-scoped` (both `set_state` calls lose
      `serializable=False`; target `[legacy]`; `why='state outlived its request'`). The modern row
      cannot catch it: under revision 2026-07-28 there is no session, and FastMCP keys each request's
      state afresh (measured: a new state key on every request), so a session-scoped value is
      invisible to the next request either way. The row stays as the era's pin of the property. The
      case joins P1's list in `verify/controls.py`.
- [x] `AGENTS.md`: §1's state line names the test; § Testing's `test_protocol.py` entry and the
      harness verb list.
- **Verify:** retuned to `sh spec/stack-upgrade/verify/gate.sh P7` (the latest done phase's gate),
  set with `set_phase.py --verify-file` and read back byte-identical.

## Phase P2 — Both protocol eras, each pinned
**Satisfies:** R2, R8, R9, R11 · **Depends on:** P1
**Goal:** a handshake-era client completes `initialize` and a 2026-07-28 client is answered on
`server/discover`, each with `SERVER_INSTRUCTIONS` and exactly `EXPECTED_TOOLS`, each pinned by its
own test, in memory and over HTTP.

- [x] Harness: `MethodLog` middleware (records `context.method` in `on_message`) accepted as `extra`
      by the builders; `negotiate(target, era, token=None) -> Negotiated(protocol_version,
      has_initialize_result, instructions, tools, methods)`; modern = `mode='auto'` plus the
      `2026-07-28` check, never the version pin.
- [x] `test_protocol.py`: `era_violations(negotiated, era)` (legacy: handshake version, an
      `InitializeResult`, `initialize` seen, no `server/discover`; modern: `2026-07-28`, no
      `InitializeResult`, `server/discover` seen, no `initialize`; both: instructions equal
      `SERVER_INSTRUCTIONS`, tools equal `EXPECTED_TOOLS`); `test_client_era_is_served[legacy-memory|
      legacy-http|modern-memory|modern-http]`; planted controls `test_era_check_catches_drift[…]`;
      modern-era contract rows: `test_modern_era_delegate_calls_stay_isolated` (reuses
      `isolation_violations` and a `Rendezvous`), `test_modern_era_tokenless_delegate_call_is_refused`
      (`No executor configured`), `test_modern_era_rejects_a_foreign_token` (401, nothing launched).
- [x] `tests/mutants.py`: `instructions-dropped` (`instructions=SERVER_INSTRUCTIONS,` →
      `instructions=None,` in `server.py`; targets `test_client_era_is_served[legacy-memory]` and
      `[modern-memory]`; `why` = the instructions fragment of `era_violations`' message).
- [x] `AGENTS.md`: § Project (both protocol eras: `initialize` for handshake-era clients,
      `server/discover` for 2026-07-28, instructions in each); § Testing (`test_protocol.py`).
- **Verify:** `sh spec/stack-upgrade/verify/gate.sh P2`.
- **Touches:** `tests/harness.py`, `tests/test_protocol.py`, `tests/mutants.py`, `AGENTS.md`.

## Phase P3 — The served surface matches 3d010ec
**Satisfies:** R3, R8, R9, R11 · **Depends on:** P2
**Goal:** tool names, descriptions, input schemas, resources and instructions served on 4.x match a
snapshot taken from the `3d010ec` server; every other difference is a named, caused, tolerated kind.

- [x] Take the snapshot **from the baseline, not the new stack**: `git archive 3d010ec` into a
      scratch directory, `UV_PROJECT=$PWD uv sync --locked` there, `uv run python
      <worktree>/spec/stack-upgrade/verify/snapshot.py <worktree>/tests/fixtures/served_surface.json`.
      The gate re-derives it every phase from P3 and fails on any difference.
- [x] `tools/__init__.py`: `Tool.from_function(func, description=inspect.getdoc(func))`.
- [x] Harness: `served_surface()` (the snapshot's shape, through a client in the selected era).
- [x] New `tests/test_surface.py`: `surface_violations(snapshot, served)` and `TOLERATED` per
      `PLAN.md` §2.4 (four kinds, `output-model-description` only on nodes that were `$ref` targets
      in the 2.x snapshot; `additionalProperties` exactly `false`); `tolerated_differences(snapshot, served)` (the per-tool list for the squash
      body); tests and planted controls per `verify/ids/P3.txt`.
- [x] `tests/mutants.py`: `tool-description-summary-only` (drop `description=…`; target
      `test_served_surface_matches_baseline`; `why='description differs'` or the exact fragment the
      check emits).
- [x] `AGENTS.md`: §7/§9 (the full docstring is the served description; `Args:` lines also become
      property descriptions); § Testing (`test_surface.py`, the fixture and how it was taken).
- **Verify:** `sh spec/stack-upgrade/verify/gate.sh P3`.
- **Touches:** `src/rcac_mcp/tools/__init__.py`, `tests/fixtures/served_surface.json`,
  `tests/harness.py`, `tests/test_surface.py`, `tests/mutants.py`, `AGENTS.md`,
  `spec/stack-upgrade/verify/ids/P2.txt`.

*Amendments (P3 build, 2026-10-17):*
- `verify/ids/P2.txt` gains `test_protocol.py::test_era_check_catches_drift[modern-pinned]`, the
  control P2 shipped beyond its list, so every gate from here requires it (foreman's ruling).
- On the locked stack no inlined output node carries a model description, so
  `output-model-description` occurs on no tool; the kind stays in `TOLERATED` per `PLAN.md` §2.4,
  pinned by its planted row, and the served differences are the other three kinds only.
- Deferred to P7's ledger: the fixture is 2.x-shaped by design and the shape test rejects one
  re-taken on 4.x, so how it follows a deliberate surface change after this cycle is unsettled
  (`AGENTS.md` §9 says so) → `issues/surface-fixture-after-a-surface-change.md` plus its
  `ROADMAP.md` entry.

## Phase P4 — Every transport starts in the sandbox and lists the tools
**Satisfies:** R4, R8, R9, R11 · **Depends on:** P3
**Goal:** `rcac-mcp -e local` on stdio, http and sse starts under `bin/sandbox.sh` and a client lists
`EXPECTED_TOOLS` from it. FastMCP 4.1 serves SSE, so `-t sse` stays (handshake era only) and R4's
rejection path does not apply: no test id is dropped and `README.md`, `APP_USAGE`/`APP_HELP` and
`SECURITY.md` are unchanged.

- [x] Harness: `stdio_tools(argv, era)` (raises unless `argv[0]` is this repo's `bin/sandbox.sh`),
      `url_tools(url, transport, era)`; remote verbs are not fenced and say why.
- [x] New `tests/test_transports.py` (integration): a free-port helper; a server drive that starts
      `[str(SANDBOX), str(CLI), '-e', 'local', '-t', t, '-H', '127.0.0.1', '-p', port]` with
      `start_new_session=True`, waits for the port (bounded), and stops it with `os.killpg` (the
      sandbox does not forward SIGTERM); `test_transport_lists_expected_tools[stdio-legacy|
      stdio-modern|http-legacy|http-modern|sse-legacy]` asserting the tool set and the negotiated
      era; a failure to listen reports `<t>: the server did not start listening`;
      `test_harness_refuses_unsandboxed_stdio`.
- [x] `tests/mutants.py`: `sse-transport-unserved` (the `sse` dispatch in `__init__.py` becomes a
      no-op; target `[sse-legacy]`; `why='did not start'`). The child runs the installed console
      script, which imports the mutated copy through `PYTHONPATH` as `floor-cli-31` already relies on.
- [x] `AGENTS.md`: § Project transports (stdio and http serve both eras; sse is handshake-only and
      deprecated by revision 2026-07-28 but still served); § Testing (`test_transports.py`, the
      process-group stop).
- **Verify:** `sh spec/stack-upgrade/verify/gate.sh P4`.
- **Touches:** `tests/harness.py`, `tests/test_transports.py`, `tests/mutants.py`, `AGENTS.md`.

*Amendments (P4 build, 2026-10-17):*
- `url_tools` refuses any host but loopback (the foreman's ruling: transports bind loopback only in
  tests), pinned by `test_harness_refuses_a_remote_url[…]`; `stdio_tools` takes `env` (default: the
  test's environment, so the PATH shim and a mutant's `PYTHONPATH` reach the server) and closes the
  server on exit (`keep_alive=False`; FastMCP's default leaves it running). Both return `Listed`.
- `test_transports.py` gains the pure `transport_violations` with planted controls (the module
  convention), and each server row asserts its teardown: the process group gone, the port closed,
  the sandbox directory removed. The new control ids join `verify/ids/P4.txt`, as P2's extra control
  joined `P2.txt`.
- `test_harness_refuses_unsandboxed_stdio` is `unit`, so a missing refusal would trip the unit guard.

## Phase P5 — Auth on the new provider API, the OIDC check and the annotation pinned
**Satisfies:** R5, R6, R7, R8, R9, R11 · **Depends on:** P4
**Goal:** both `JWT_SECRET` floors and the signer/verifier agreement hold on 4.x (R5, through the
existing `test_tokens.py` ids and cases, in both eras); OIDC refuses a half configuration before any
provider or request (R6); `none` installs nothing; `AUTH_MODES`' annotation resolves to the mapping
it means (R7).

- [x] `auth.py`: `AUTH_MODES: Final[Dict[str, Callable[[], AuthProvider | None]]] = {…}`; drop the
      local `from fastmcp.server.auth.oidc_proxy import OIDCProxy` in `create_auth_oidc` (the module
      import is the one used); drop the trailing blank line; build the proxy with
      `enable_cimd=False, forward_resource=False` (2.x posture; foreman's ruling), with a comment
      saying both are held off pending a deliberate decision. The JWT block and the OIDC check's text
      are otherwise unchanged (the existing anchors must still apply).
- [x] Harness: `installed_auth(server)`.
- [x] New `tests/test_auth_modes.py`: `oidc_violations(raised, message, built, refused)`;
      `test_oidc_requires_all_four[<VAR>-unset|<VAR>-empty]` × 4 (the other three set; the test
      replaces `rcac_mcp.auth.OIDCProxy` with a recorder and asserts a `ValueError` naming all four,
      nothing built, `guard.refused == []`); `test_oidc_with_all_four_builds_the_proxy` (the recorder
      is reached, so "nothing built" is not vacuous; it binds the keywords it receives with
      `inspect.signature(<the real OIDCProxy>).bind(**kwargs)`, so a keyword the real class lacks
      fails); `test_oidc_proxy_keeps_the_2x_posture` (`enable_cimd is False`, `forward_resource is
      False`); `test_none_mode_installs_no_provider`
      (`AUTH_MODES['none']() is None`; `installed_auth` of a `none` server is `None`; a tokenless HTTP
      call to a shared `none` server succeeds); `annotation_violations(hint)` and
      `test_auth_modes_annotation_is_a_provider_factory_map` (resolved via
      `typing.get_type_hints(rcac_mcp.auth)`; `Final`; a mapping origin; `str` keys; a `Callable`
      whose parameter list is exactly `[]` (`Callable[..., X]` is rejected) returning `AuthProvider` or `AuthProvider | None`; never a
      `slice`); planted controls per `verify/ids/P5.txt`.
- [x] `tests/mutants.py`: `oidc-check-dropped` (all eight rows), `oidc-secret-not-required` (the
      two `OIDC_CLIENT_SECRET` rows), `oidc-message-incomplete` (the error stops naming
      `MCP_BASE_URL`; the two `MCP_BASE_URL` rows), `oidc-cimd-enabled` (drop `enable_cimd=False`;
      target the posture row), `none-mode-installs-provider` (`'none'` returns a
      `JWTVerifier`), `auth-modes-annotation-slice` (restores `]:]`; `why='slice'`). Each `why` is the
      fragment of the check's own message.
- [x] `AGENTS.md`: §6 (provider types and import paths; `OIDCProxy`'s `client_secret` is optional
      upstream but required here; CIMD and resource forwarding held off at 2.x behaviour pending a
      deliberate decision); `SECURITY.md` (the same OIDC note); the `AUTH_MODES` footgun line (typo fixed; the PEP 563 claim
      removed: the slice evaluated eagerly too); § Testing (`test_auth_modes.py`).
- **Verify:** `sh spec/stack-upgrade/verify/gate.sh P5`.
- **Touches:** `src/rcac_mcp/auth.py`, `tests/harness.py`, `tests/test_auth_modes.py`,
  `tests/mutants.py`, `AGENTS.md`, `SECURITY.md`.

*Amendments (P5 build, 2026-10-17):*
- The positive and posture rows get their own pure checks beside `oidc_violations`:
  `proxy_violations(signature, args, kwargs, expected)` (the recorded arguments bind to the real
  `OIDCProxy` signature, read at import before any test replaces it, and carry the four values) and
  `posture_violations(signature, args, kwargs)` (after the real defaults apply, `enable_cimd` and
  `forward_resource` are `False`, so dropping a keyword reads as the default `True`). The
  `test_oidc_check_catches_drift` rows `unknown-keyword`, `cimd-enabled` and `resource-forwarded`
  are their planted controls.
- `none-mode-installs-provider` plants a `JWTVerifier` built from the shared constants;
  `why='none mode installed a provider'`, the test's own assertion message. The other cases' `why`s:
  `raised no ValueError` (`oidc-check-dropped`, `oidc-secret-not-required`), `does not name
  MCP_BASE_URL`, `enable_cimd=True`, `slice`.
- § Repository map's `auth.py` row also names OIDC's all-four check (R11).

*Remediation (review cycle 1, F2, 2026-10-17):* the OIDC proxy's client-registration store moved
(FastMCP 2's encrypted `DiskStore` at `<home>/oauth-proxy/cache.db` → FastMCP 4's encrypted
`FileTreeStore` under `<home>/oauth-proxy/<key-fingerprint>/`, which does not read the old store), so
an upgraded `-a oidc` deployment's clients must register again, and no record said so.
- [x] `AGENTS.md` § Project: the accepted behaviour changes become a list (the 30-minute idle close;
      the registrations that do not survive the upgrade). §6: a bullet stating the store change.
      `SECURITY.md` § OIDC Configuration: the same, for operators.
- **Verify:** retuned to `sh spec/stack-upgrade/verify/gate.sh P7`, which now checks all three
  sites (`--verify-file`, read back byte-identical).

## Phase P6 — The release gate refuses a lock with a known advisory
**Satisfies:** R10, R8, R9, R11 · **Depends on:** P5
**Goal:** the release recipe's `gate` audits the tree `uv.lock` resolves and fails, naming package,
version and advisory, on a known advisory, and fails when the advisory source is unreachable; green
on the shipped lock; shown red once on a planted lock; CI runs the same step if the workflow exists.

- [x] **Before starting:** the foreman rebases this branch onto `develop` if `ci-workflow` has
      landed. Then `.github/workflows/ci.yml` either exists on the base or does not; record which in
      the commit body.
- [x] `bin/audit_lock.py` from `research/prototypes/audit_lock.py` (stdlib; `uv audit --frozen
      --no-config --preview-features audit-command --project <this checkout>` run with `child_env`,
      which drops `UV_PROJECT` and every `UV_*` outside the allowlist; `audit_violations` decides;
      exits 0/1/2/3 as its docstring says; no options).
- [x] New `tests/test_audit.py`: `test_audit_check_accepts_a_clean_audit`;
      `test_audit_check_catches[…]` (planted outputs, ids in `verify/ids/P6.txt`, each red for its
      stated reason); `test_audit_names_this_checkout_whatever_uv_project_says` (`COMMAND` carries
      `--project` with the script's own checkout, and `child_env` with `UV_PROJECT` set elsewhere
      drops it); `test_audit_env_drops_uv_selectors` (`UV_NO_DEV`, `UV_ONLY_GROUP` … dropped;
      `UV_OFFLINE`, `PATH` kept); integration `test_audit_fails_closed_offline` (the real script under
      `bin/sandbox.sh` with `UV_OFFLINE=1` and `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` at
      `http://127.0.0.1:9`: exit 2, "advisory source unreachable", **and** uv's own "requires network
      access … offline mode" line, so no request was attempted). Load the script with
      `importlib.util.spec_from_file_location`.
- [x] `AGENTS.md` § Factory → Release recipe `gate`: `- uv run python bin/audit_lock.py` right
      after `- uv lock --check`, and a caveat (fails closed; needs the network; no waiver: an
      advisory with no fixed release holds the release until a seed takes it up). The profile's
      `verify` is unchanged. § Packaging/§ Testing as they now read.
- [x] If `.github/workflows/ci.yml` exists: add `- run: uv run python bin/audit_lock.py` where the
      "CI mirrors the gate" rule puts it, in this same commit. If it does not: R10's CI clause is
      vacuous; add a dated note to the `ci-workflow` seed under `issues/` (or its successor record)
      that the workflow must carry the step, and a matching `ROADMAP.md` line.
- [x] Prepare the planted project outside the repo (a scratch `pyproject.toml` + `uv.lock` pinning a
      version with a published advisory, chosen and recorded in the private build log) and run
      `sh spec/stack-upgrade/verify/gate.sh P6 --audit <planted-dir>` (networked). Its output, the
      planted lock's advisory report included, goes to the private build log; the commit body says only
      "audit proofs passed (green / red planted / red offline)".
- **Verify:** `sh spec/stack-upgrade/verify/gate.sh P6` (plus the `--audit` mode above, by build).
- **Touches:** `bin/audit_lock.py`, `tests/test_audit.py`, `AGENTS.md`, `.github/workflows/ci.yml`
  (if present), the `ci-workflow` seed and `ROADMAP.md` (only if the workflow is absent).

*Amendments (P6 build, 2026-10-17):*
- **No workflow on the base.** `.github/workflows/ci.yml` does not exist on `develop` (the
  `ci-workflow` cycle is held and lands after this one), so R10's CI clause is vacuous here (GOAL
  Clarifications). Foreman's ruling: no `.github/` file is added or edited, and the `ci-workflow` seed
  and `ROADMAP.md` are not touched (that cycle is in flight on its own branch and owns its record).
  Instead, when `ci-workflow` rebases onto `develop` after this lands, its own "CI mirrors the gate"
  check binds `ci.yml` to the release recipe's `gate` list verbatim, so it cannot land without the
  `uv run python bin/audit_lock.py` step. Recorded here and in the P6 commit body; P7's confirmation
  of a seed note and ROADMAP line is void accordingly.
- The offline integration row decides with a pure `offline_violations(returncode, stderr)` in
  `tests/test_audit.py` (exit 2, "advisory source unreachable", uv's own offline refusal), whose
  planted controls (a zero exit, a missing reason, a refusal without uv's offline line) run inside
  `test_audit_fails_closed_offline` before the real drive. The drive runs the script with the
  suite's interpreter under `bin/sandbox.sh` (it is stdlib-only), with every proxy variable, upper
  and lower case, at `http://127.0.0.1:9` and `NO_PROXY` removed.
- `bin/audit_lock.py`'s docstring says the release gate runs it and a CI workflow mirrors that gate
  by running the same file (the prototype said the workflow already does).
- `AGENTS.md` also gains a § Packaging bullet (the release gate audits the lock) and the repository
  map's repo-level paths name `bin/audit_lock.py` (R11).

*Remediation (review cycle 1, F1, 2026-10-17):* `bin/audit_lock.py`'s docstring said a CI workflow
mirrors the release gate; none exists (R10's CI clause is vacuous, P6 amendment). The class is every
live claim that a CI workflow exists or runs something. Sites found by the sweep (tracked files
outside `spec/`, `issues/` and `ROADMAP.md`, which are records): `bin/audit_lock.py:17-18` and
`AGENTS.md` § Conventions ("The release recipe's `gate` mirrors CI.", present on `develop`, added to
the sweep here). Both now say no workflow exists yet and the one `ci-workflow` adds is to mirror the
gate. In the records: `ROADMAP.md`'s stack-upgrade entry gets F4's dated correction; the `ci-workflow`
entry's "`stack-upgrade` adds a dependency-audit step to it" is already future-worded and belongs to
that cycle's record (P6 ruling), and `issues/stack-upgrade.md` is a seed record; both are left as
written. No `.github/` file is added.
- [x] Both live sites reworded as future.
- [x] P7's gate asserts the class absent: while `.github/workflows` does not exist, no tracked file
      outside the records matches a present-tense CI claim.
- **Verify:** retuned to `sh spec/stack-upgrade/verify/gate.sh P7` (`--verify-file`, read back
  byte-identical).

## Phase P7 — Closeout, deferral ledger and the fresh-clone run
**Satisfies:** R8, R9, R11 · **Depends on:** P6
**Goal:** `AGENTS.md` says what is now true everywhere, every deferral has its record, and a fresh
clone proves the committed state.

- [x] `AGENTS.md` sweep: no "FastMCP 2.x", `get_tools()`, `fastmcp.tools.tool.FunctionTool` or PEP
      563 claim left; § Project names FastMCP 4, MCP SDK 2, 2026-07-28 and the three transports;
      § Testing names every new module, the fixture, the era selector, `httpx2`, `mcp_types`,
      `importorskip`; the high-blast-radius list keeps every entry it had at `3d010ec` (gated).
- [x] **Deferral ledger.** Walk P1–P6 above for "deferred", "known limitation", "follow-up", "out of
      scope" and confirm each has its record. Known item: resource reads never receive an executor
      (both executor middlewares hook only `on_call_tool`; `rcac://context` fails with
      `No executor configured` on 2.x and 4.x alike; fails closed, so public lane) →
      `issues/resource-reads-without-executor.md` from the KB `ISSUE.md` template (`status: unshaped`,
      **Pre-existing:** yes) plus its `ROADMAP.md` entry. From P3: how the 2.x-shaped surface
      fixture follows a deliberate surface change → `issues/surface-fixture-after-a-surface-change.md`
      (`status: unshaped`, **Pre-existing:** no) plus its `ROADMAP.md` entry. P6 found no workflow and, by the
      foreman's ruling, left the `ci-workflow` seed and `ROADMAP.md` alone (P6 amendment). Nothing goes in `spec/` or the
      KB inbox.
- [x] Squash-body material for publish (C2 in `PLAN.md`): the tolerated R3 differences per tool
      (`test_surface.tolerated_differences`) and the `_meta` key rename; "no test id collected at
      3d010ec was dropped (sse is still served)"; every retargeted or removed mutation case with its
      reason (none expected); the accepted 4.x behaviour changes: the 30-minute HTTP session idle
      expiry, and the OIDC proxy's CIMD and resource forwarding held off; every major that moved in
      `uv.lock` (from P1's commit body).
      Put it in the P7 commit body.
- [x] ~~Run `sh spec/stack-upgrade/verify/gate.sh P7 --audit <planted-dir>` again on the final lock
      (private log).~~ Left to the foreman by amendment (below): the lock is the one P6's proofs ran on.
- **Verify:** `sh spec/stack-upgrade/verify/gate.sh P7` (includes the document and ledger checks;
  every base case whose `file`, `edits`, `targets` or `why` changed, and every package whose major
  moved in `uv.lock`, named in a branch commit body; and the fresh clone with `UV_PROJECT=$PWD`: both
  eras, every id, every case).
- **Touches:** `AGENTS.md`, `issues/resource-reads-without-executor.md`, `ROADMAP.md`.

*Amendments (P7 build, 2026-10-17):*
- The gate's case-table comparison (step 8) could not run: it loaded both `mutants.py` copies
  without registering them in `sys.modules`, and their dataclass, under postponed annotations,
  fails to build then (seen on a dry run of the comparison, before any gate run). `run.sh` now
  registers each copy under its own name, and also fails on a base case missing from the table.
- The fresh clone now proves each suite pass's era from its era log (`SUITE_CONNECTS`) and runs
  every case in both eras (the handshake pass with `--self-check`), each mutation pass era-logged
  (`MUTANT_CONNECTS`), as the worktree passes are; a failure there names its step.
- The `--audit` re-run is left to the foreman. `uv.lock` has not changed since P1, so the final lock
  is the one P6's networked proofs passed on; the build's standing ruling is loopback-only network
  (package resolution aside); and the release gate runs the audit at release in any case.
- `AGENTS.md` beyond the gated sweep: §8 records that a resource read gets no executor, with its
  seed and the ordering constraint against the context cache; §9 points at the surface-fixture
  seed; §1 notes that the boundary would also turn a missing-client-capability error into a tool
  error result (`PLAN.md` §5); the profile's `verify` row says it runs the handshake era; the
  internals-bound item 4 says the move left `test_tokens.py` unchanged; the mutation runner's timing
  is re-measured (67 cases, about 2½ minutes). Two lines that named "FastMCP 2.x" as history now
  say "FastMCP 2".
- `ROADMAP.md`: the resource-read seed is a Part 0 entry after `agents-d-instructions` (it depends
  on the cache's retirement), so Part 0 now counts six cycles; the surface-fixture seed is a
  Part III entry. Both placements are proposals for the maintainer.
- Ledger walk, beyond the two seeds: the held OIDC posture (§6, `SECURITY.md`), the untested live
  OIDC flow (§ Testing) and the 30-minute idle expiry (§ Project) are recorded in `AGENTS.md` as a
  pending decision, a limitation and an accepted change, not deferred work; the `ci-workflow` seed
  stays untouched (P6 amendment).
- Touches also `issues/surface-fixture-after-a-surface-change.md` and
  `spec/stack-upgrade/verify/run.sh`.

*Remediation (review cycle 1, F4 and the landing list, 2026-10-17):*
- [x] `ROADMAP.md`'s stack-upgrade entry: a dated 2026-10-17 correction (the audit lives in the
      release recipe's `gate`, not in CI; this cycle lands first and `ci-workflow` picks the step up
      through its "CI mirrors the gate" check). The historical text stays.
- [x] P7's gate also checks F2's three sites and the correction (`verify/run.sh`, `p7_checks`).
- [x] Squash-body material for publish: the remediation commit's body carries an addendum to P7's,
      in the same place (C2: the squash body; this phase's material lives in commit bodies):
      client-visible differences beyond R3's list (an unknown tool's error text now quotes the name,
      `Unknown tool: no_such_tool` → `Unknown tool: 'no_such_tool'`; `serverInfo.version` reports
      FastMCP's own version, 4.1.0, where it reported 2.14.4); the OIDC client-registration reset as
      an accepted 4.x behaviour change; the added mutation case (15 in all).
- **Same commit, P5, P6 and P7:** F2's store change is stated in `AGENTS.md`, `SECURITY.md` and the
  squash-body list of accepted changes, and F1's false CI claim sits in `bin/audit_lock.py` and in
  `ROADMAP.md`'s stack-upgrade entry; a fact restated in several places changes in every copy in one
  commit. P1's F3 fix shares no copy with them and is committed on its own.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[refactor]` commit; stop and
   report.
