# 04 — What the suite needs: the internals-bound list, item by item

Baseline: 296 ids collected at `3d010ec` (test_cli 10, test_exec_mode 35, test_executors 13,
test_hygiene 36, test_identity 16, test_instructions 12, test_isolation 10, test_mutations 63,
test_no_executor 32, test_registry 17, test_tokens 23, test_tools 29). Prototype path: re-lock, run
unmodified (collection error on `import httpx`), then fix one thing at a time.

| # | Module | What broke on 4.1 | Rewrite |
|---|---|---|---|
| 1 | `tests/harness.py` | `import httpx` (collection error for every module importing the harness); the 401 now surfaces as an `MCPError` inside an `ExceptionGroup` from the connect-time `server/discover` probe and `initialize` fallback, not as `httpx.HTTPStatusError` | `httpx2`; the client factory records response statuses with an `event_hooks={'response': …}` hook and `call_http` reports `Outcome(True, '', 401)` when a 401 was answered and the connect failed (re-raising anything else); the era selector and post-connect era check (brief 02); new verbs for R2/R3/R4/R6 |
| 2 | `test_exec_mode.py` | nothing (35/35 pass) | none |
| 3 | `test_executors.py` | nothing | none (the argv rows are `safe-execution`'s) |
| 4 | `test_tokens.py` | the five 401 rows (through the harness route, fixed in item 1) | none: `JWTVerifier`'s import path is unchanged and re-exported as before |
| 5 | `mutants.py` / `test_mutations.py` | nothing: every anchor still applies; 53/53 killed for their stated reason on 4.1 in both eras (prototype, with brief 01's fixes) | anchors re-checked each phase; new cases added (below) |
| 6 | `test_registry.py`, `test_instructions.py` | `get_tools()` is gone; `.instructions` still works | both read the served surface through harness verbs (`served_tools`, `served_instructions`) instead of the FastMCP server API, which retires item 6 from the list |

Outside the list, the seven reds after the httpx fix were all the middleware-error masking
(brief 01 item 3): `test_identity` (4), `test_isolation::test_rendezvous_fails_when_calls_are_not_concurrent`,
and `test_tokens` (5, the 401s, item 1). With the boundary middleware and the harness fixes,
295/296 pass with **no edit** to any module outside the list; the 296th is item 6.

## `test_hygiene.py` and the import fence (R8's last clause)

`STACK = ('fastmcp', 'mcp', 'httpx')`. The new stack adds two import names a test module could use
to reach it unseen: `httpx2` (the HTTP client) and `mcp_types` (the protocol types). Widening
`STACK` to `('fastmcp', 'mcp', 'mcp_types', 'httpx', 'httpx2')` keeps the clause's intent ("only
the harness reaches the stack"); `httpx` stays listed so a stray old import is still caught.
`pytest.importorskip("fastmcp")` is not read today: add `importorskip` to the importer names (it is
reached as `pytest.importorskip`, so the dotted-suffix rule already matches once the name is
listed), read its `modname=` keyword as well as `name=`, and track `from pytest import importorskip
as …` aliases. Its new negative controls go in a **new** test function, so no existing test's
source changes (the R8 edit check compares every `test_*` function's source, decorators included,
with the base).

## New tests (one module per requirement, all speaking harness verbs)

- `test_protocol.py` (unit): legacy and modern negotiation over memory and HTTP (R2); the harness
  era self-check; a middleware refusal arrives as a tool error result with its reason (the
  boundary); `era_violations` with planted controls.
- `test_surface.py` (unit): the served surface against `tests/fixtures/served_surface.json`
  (R3), with `surface_violations` and an explicit table of tolerated difference kinds, each with
  its cause; planted controls.
- `test_transports.py` (integration): stdio, http and sse under `bin/sandbox.sh`, each listing
  `EXPECTED_TOOLS` (R4).
- `test_auth_modes.py` (unit): the OIDC all-or-nothing check, eight one-missing rows plus a
  positive control; `none` installs no provider; the `AUTH_MODES` annotation shape (R6, R7).
- `test_audit.py` (unit + integration): the audit script's verdict function and its offline
  fail-closed path (R10).

## Mutation cases to add (R9 and the new contracts)

`tool-error-boundary-dropped`, `instructions-dropped`, `tool-description-summary-only`,
`oidc-check-dropped`, `oidc-secret-not-required`, `oidc-message-incomplete`,
`none-mode-installs-provider`, `auth-modes-annotation-slice` (restores `]:]`). Each names targets
whose violation message carries its `why`, never a stack exception's text.

## Two harness hazards found

- **stdio launches are invisible to `sandbox_violations`.** FastMCP's `StdioTransport` starts the
  process inside the library, so the static check cannot see it. The harness's stdio verb refuses
  an argv whose first element is not this repo's `bin/sandbox.sh`, at runtime.
- **`bin/sandbox.sh` does not forward SIGTERM to its child.** `Popen.terminate()` on the sandbox
  left the server running (and `communicate()` hung). Server drives start with
  `start_new_session=True` and stop with `os.killpg`.
