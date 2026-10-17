# 00 — Digest: decisions for stack-upgrade

Research ran sequentially in the planner (no child subagents in this runtime), against the
installed source of `fastmcp` 4.1.0 / `mcp` 2.3.0 and a scratch prototype: `3d010ec` re-locked on
the new stack, run unmodified, then fixed one finding at a time until 296/296 passed in both
protocol eras and 53/53 mutation cases were killed in both. Briefs:
[01 API deltas](01-api-deltas.md) · [02 dual era](02-dual-era.md) ·
[03 executor contract](03-executor-contextvar.md) · [04 test suite](04-test-suite.md) ·
[05 dependency audit](05-dependency-audit.md) · [06 lock and uv](06-lock-and-uv.md).

## Decisions

1. **Lock:** `fastmcp>=4,<5`; `uv lock --upgrade-package fastmcp --upgrade-package mcp`, plus what
   the resolver forces and what the audit reports, nothing else (foreman's ruling after the design
   review; supersedes the whole-tree upgrade this digest first chose). Moved majors are named in the
   P1 commit body. `paramiko` moves, so an offline `ssh` executor smoke test lands in P1. Lock format
   unchanged (revision 5); uv 0.12.17 reads it. (06)
2. **The masked middleware error is the one real behaviour change**, and it is fixed, not
   tolerated: `ToolErrorMiddleware`, added first by `create_mcp_server`, turns any non-FastMCP
   exception (an `MCPError` included, for parity) raised around a tool call into
   `ToolError(str(exc))`, the exact 2.x wire shape; `BaseException` passes through.
   §5's exception types and every mutation anchor stay put. (01, 03)
3. **`set_state` is awaited, request-scoped** (`serializable=False`). (01, 03)
4. **Descriptions are pinned to the full docstring** with `description=inspect.getdoc(func)` in
   `@mcp_tool`; the per-argument descriptions, `additionalProperties: false`, inlined output
   `$defs` and the `_meta` key rename are tolerated differences, each with its cause, in an explicit
   table the R3 test enforces and the squash body lists. (01)
5. **Both eras:** the server needs no change. Tests use `mode="legacy"` and `mode="auto"` plus a
   check that auto negotiated `2026-07-28`; never the version pin (it skips `server/discover`). The
   harness gains an era selector (`CLUSTER_MCP_TEST_ERA`, default `legacy`) that every harness
   client honours and verifies after connect; every phase gate runs the suite in both eras. (02)
6. **SSE stays.** FastMCP 4.1 serves it (handshake era only). R4's rejection path does not fire;
   no test id is dropped. (02)
7. **§1 holds as written.** `on_call_tool` fires once per `tools/call`; sync tools run on a worker
   thread with a copy of the request context; isolation and every §1 mutation case hold in both
   eras. Wording updates only. (03)
8. **Internals-bound list:** item 1 (harness) is rewritten; 2–5 pass unchanged (5 gains cases);
   item 6 moves onto harness verbs and leaves the list. `test_hygiene.py`'s `STACK` widens to the
   new import names (`httpx2`, `mcp_types`) and its check reads `pytest.importorskip`. (04)
9. **Audit:** `uv audit --frozen --no-config --preview-features audit-command --project <checkout>`
   with every non-allowlisted `UV_*` dropped from its environment, wrapped by `bin/audit_lock.py`, which also requires the audited package count to equal the lock's. It fails
   closed (exit 2) offline or unreachable; red/green proofs run in a networked gate mode whose
   output stays in the private build log. (05)
10. **OIDC test seam:** remove the redundant local `OIDCProxy` import in `create_auth_oidc` so a
    test can replace `rcac_mcp.auth.OIDCProxy` and prove no provider is built before the check. (04)

11. **OIDC posture parity:** `OIDCProxy(..., enable_cimd=False, forward_resource=False)`; 4.x
    turns both on by default and 2.14 had neither (review finding 5, ruled).
12. **Era evidence:** every in-process connect is logged with its negotiated version and the first
    method the server saw; the gate requires each pass's log to match its era (review finding 2).

The adversarial design review (2026-10-17) and how each finding changed the design are recorded in
`PLAN.md` §4.

## Contradictions resolved

- Foreman's sketch put the audit in "the release recipe's `gate` and CI": kept, through one script
  both run (the ci-workflow cycle's `bin/sdist_hygiene.py` pattern), so the two cannot drift.
- Brief 02 offered making the modern-era pass part of the profile's `verify`; rejected for this
  cycle (it would change the profile and, through ci-workflow's mirror rule, the workflow).
  Instead the default run keeps a set of modern-era contract rows in `test_protocol.py`, and the
  cycle's gates run the full suite in both eras.

## Found along the way (deferrals)

- Resource reads never get an executor (`on_call_tool` only): `rcac://context` fails with
  `No executor configured` on 2.14 and 4.1 alike. Fails closed; public lane; seeded by the last
  phase as `issues/resource-reads-without-executor.md`.
