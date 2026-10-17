---
status: unshaped
kind: refactor
appetite: big
lane: public
---

# Move to FastMCP 4 and the current MCP SDK before building on them

## Problem

`pyproject.toml` pins `fastmcp>=2.0.0,<3`, and `uv.lock` resolves `fastmcp` 2.14.4 and `mcp`
1.26.0. FastMCP is now on 4.x — two majors ahead — and the MCP Python SDK on 2.x, one major ahead.
`AGENTS.md` § Project still describes the server as "built on FastMCP 2.x".

The protocol moved too. MCP revision **2026-07-28** is stateless: there is no `initialize`
handshake and no protocol session, and a server answers `server/discover`, whose result carries the
`instructions`. FastMCP 4 serves that revision and the earlier ones from the same server, so a
current client and an older one can both connect. The locked stack speaks only the older revisions.

That would be ordinary dependency drift, except for what comes next. The cycles that follow build
three mechanisms directly on the FastMCP API:

- **Plugin registration** ([`capability-extras.md`](capability-extras.md)) — today `@mcp_tool`
  wraps `Tool.from_function` into a list (`tools/__init__.py:21`); FastMCP 4's providers and `mount`
  are candidate carriers for capability groups.
- **Composed instructions** ([`agents-d-instructions.md`](agents-d-instructions.md)) — served in
  `InitializeResult` on the old revisions and in `DiscoverResult.instructions` on the new one.
- **Annotations, `_meta` hints and tool search** ([`tool-surface.md`](tool-surface.md)).

Built on 2.x, each of those is built twice. And there is no step anywhere that would notice a
locked dependency falling behind: no CI, no audit, nothing that surfaces an advisory against the
lock.

## Why it was deferred

Not deferred — a roadmap cycle, placed in Part 0 after the test suite and CI exist, so the upgrade
lands against a real gate, and before any mechanism is built on the API.

It absorbs [`auth-modes-annotation-typo.md`](auth-modes-annotation-typo.md): `auth.py` is rewritten
against the new auth API anyway, so the one-character fix rides with it rather than being made to
code that is about to be replaced. That seed's criteria — the annotation evaluates to the intended
type, and a test asserts it — carry over.

**Pre-existing:** n/a — the pin is a choice, not a defect.

## Outcome / vision

The server runs on FastMCP 4.x and the MCP SDK 2.x, answers clients on revision 2026-07-28 and on
the earlier revisions, and behaves the same as before to every existing client: same tools, same
schemas, same resources, same instructions. Auth modes (`jwt`, `oidc`) are re-expressed on the new
API and re-tested.

Dependency security advisories stay visible from now on: a dependency-audit step in CI checks the
lock and reports what it finds, so the next drift is noticed when it starts rather than two majors
later.

Questions the plan has to answer rather than assume:

1. **Transports.** Confirm which of today's `stdio`, `sse` and `http` the new stack still serves. If
   `sse` goes, that is a user-visible change and belongs in `README.md`.
2. **The decorator.** `@mcp_tool` returning a non-callable `FunctionTool` is the root of
   [`storage-paths-resource-typeerror.md`](storage-paths-resource-typeerror.md); check whether the
   new `Tool` type changes that before fixing the resource, which comes next.
3. **Audit policy.** Whether the audit step fails the build or only reports is a shaping call.

## Sketch of the acceptance criteria

- **R1** — `pyproject.toml` SHALL require FastMCP 4.x, and `uv.lock` SHALL resolve MCP SDK 2.x.
- **R2** — WHEN a client on revision 2026-07-28 connects, the server SHALL answer `server/discover`
  with its tools and instructions; WHEN a client on an earlier revision connects, the server SHALL
  complete `initialize`. Both SHALL be tested.
- **R3** — The tool list (names and input schemas), the resources and the served instructions SHALL
  match a snapshot taken before the upgrade, except for differences listed in the PR.
- **R4** — The auth module's type hints SHALL evaluate to the intended types, asserted by a test
  (carried from `auth-modes-annotation-typo` R1–R2).
- **R5** — CI SHALL run a dependency-audit step against the lock and report known advisories.
- **R6** — `AGENTS.md` (§ Project, § Invariants §6 and §7) SHALL describe the new stack in the same
  commit as the code.

## Notes

- Depends on [`restore-test-coverage.md`](restore-test-coverage.md) (the snapshot and auth tests
  need a suite) and [`ci-workflow.md`](ci-workflow.md) (the audit step lands in its workflow).
- Related: [`auth-modes-annotation-typo.md`](auth-modes-annotation-typo.md) (absorbed),
  [`capability-extras.md`](capability-extras.md), [`agents-d-instructions.md`](agents-d-instructions.md),
  [`tool-surface.md`](tool-surface.md), [`https-token-mode.md`](https-token-mode.md) (built on the
  upgraded HTTP transport).
- Found by: roadmap revision, 2026-10-16 (out of cycle).
- 2026-10-16: `restore-test-coverage` confines the suite's FastMCP, mcp and httpx imports to
  `tests/harness.py` (`test_hygiene.py` fails on one anywhere else), which is the rewrite point:
  the in-memory client, `http_app()` and its router lifespan,
  `StreamableHttpTransport(httpx_client_factory=…)` over `httpx.ASGITransport`, the
  `Middleware.on_call_tool` hook its `Rendezvous` implements, and the `JWTVerifier` import path it
  re-exports. Three more internals-bound spots: `tests/test_exec_mode.py`'s stub of
  `rcac_mcp.create_mcp_server` (moves only if server construction moves),
  `tests/test_tokens.py`'s verifier route (`create_jwt_auth()` returning a `JWTVerifier`;
  acceptance and 401s observed through the harness's HTTP route), and the older
  `tests/test_registry.py` and `tests/test_instructions.py`, which read `get_tools()` and
  `instructions` off a FastMCP server directly. The other contract tests speak harness verbs and
  should pass unchanged. The planted violations in `tests/mutants.py`
  anchor on today's `auth.py`, `token.py` and `middleware.py` text; an edited anchor fails
  `test_mutation_anchor_applies[<case>]`, and the case is re-planted and re-run in the same cycle.
  If FastMCP 4 drops the `httpx_client_factory` hook, the fallback is uvicorn on a random localhost
  port, as an `integration` test. `AGENTS.md` § Testing holds the internals-bound list.
- 2026-10-16: the restore-test-coverage review (cycle 3) observed that the stack-import hygiene
  check (`tests/test_hygiene.py`, `stack_import_violations`) does not read
  `pytest.importorskip("fastmcp")`, and its docstring's list of unread loaders doesn't name that
  form either. Nothing in the suite uses it today. When this cycle moves the harness, either read
  `pytest.importorskip` with a literal name or list it among the documented limits.
