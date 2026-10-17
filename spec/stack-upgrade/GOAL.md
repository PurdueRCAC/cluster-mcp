# GOAL — Move to FastMCP 4 and the MCP SDK 2 with every pinned contract intact

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** stack-upgrade
- **kind:** refactor
- **appetite:** big

## Problem

The server is two FastMCP majors and one MCP SDK major behind. `pyproject.toml:8` pins
`fastmcp>=2.0.0,<3`; `uv.lock` resolves `fastmcp` 2.14.4 and `mcp` 1.26.0. The current releases are
`fastmcp` 4.1.0 (2026-10-08) and `mcp` 2.3.0 (2026-10-02). `AGENTS.md:23` still describes the server
as "built on FastMCP 2.x".

The protocol moved with them. MCP revision **2026-07-28** is stateless: there is no `initialize`
handshake, and a server answers `server/discover`, whose result carries the `instructions`. FastMCP
4.0 (2026-08-31) serves that revision and still serves clients on the earlier ones. The locked
stack speaks only the earlier revisions, so a current client and the server do not share an era.

This is more than drift because of what is queued behind it. `capability-extras` (plugin
registration, today `@mcp_tool` wrapping `Tool.from_function`), `agents-d-instructions` (composed
instructions, carried by `InitializeResult` on the old revisions and by `server/discover` on the
new one), `tool-surface` (annotations, `_meta`, tool search) and `https-token-mode` (the HTTP
transport) are each built directly on the FastMCP API. Built on 2.x, each is built twice.

Nothing notices a locked dependency falling behind or acquiring a known advisory: no CI, no audit
step, nothing in either gate. Security-relevant detail is tracked privately, per `AGENTS.md`
§ Factory → Profile (`security lane`); this GOAL states only the observable outcome.

The upgrade touches every high-blast-radius path that speaks FastMCP: `auth.py`, `token.py`,
`middleware.py`, `server.py` and `context.py` (§ Invariants §1, §5, §6, §9). The regression net is
already in place: `restore-test-coverage` landed a 296-test suite and 53 mutation cases on
`develop`, with every FastMCP, mcp and httpx import in the suite confined to `tests/harness.py`
and the remaining stack-bound tests named in `AGENTS.md` § Testing → *Internals-bound tests*.

The absorbed seed `auth-modes-annotation-typo` rides along because `auth.py` is rewritten here
anyway. `src/rcac_mcp/auth.py:65` reads `AUTH_MODES: Final[Dict[str, Callable[[], AuthProvider]]:]`;
the `:` makes the subscript a slice, and `typing.get_type_hints` silently returns
`Final[slice(Dict[...], None, None)]` rather than raising. Any check that only asserts evaluation
succeeds passes on the broken code. The § Invariants footgun line claims the annotation "only
parses because of PEP 563"; the seed verified that is false (it evaluates eagerly too, on Python
3.14). **Pre-existing:** the annotation, yes (on `main` since `2def4a4`); the pin is a choice, not a
defect.

Anchors confirmed against `origin/develop` `3d010ec` on 2026-10-17: `pyproject.toml:8`, the
`uv.lock` versions, `auth.py:65`, the `-t/--transport` choices `stdio`, `sse`, `http`
(`__init__.py:123`, dispatched at `:194–198`), `AGENTS.md:23`.

## Outcome / vision

The server runs on FastMCP 4.x and the MCP SDK 2.x and, to every existing client, behaves exactly as
before: same tools, schemas, resources and instructions, same transports, same auth posture. A
client on revision 2026-07-28 is served too. The suite and the mutation runner prove it: the tests
that spoke only harness verbs pass untouched, the internals-bound ones are rewritten knowingly where
the API moved, and every planted violation is still caught for its stated reason. `AGENTS.md` says
what is now true. And the release gate refuses a locked tree with a known advisory, so the next
drift is caught when it starts rather than two majors later.

## Acceptance criteria (the contract)

Stack and protocol:

- **R1** — `pyproject.toml` SHALL require FastMCP 4.x (`>=4,<5`), and `uv.lock` SHALL resolve
  `fastmcp` 4.x and `mcp` 2.x, with `uv lock --check` and `uv sync --locked` passing on the supported
  Python.
- **R2** — WHEN a client on a revision earlier than 2026-07-28 connects, the server SHALL complete
  `initialize`, return `SERVER_INSTRUCTIONS` as its instructions and list exactly `EXPECTED_TOOLS`;
  WHEN a client on revision 2026-07-28 connects, the server SHALL answer `server/discover` with
  `SERVER_INSTRUCTIONS` as its `instructions` and list exactly `EXPECTED_TOOLS`, with no
  `initialize`. Each era SHALL be pinned by its own test.
- **R3** — The served surface SHALL match a snapshot taken from the server at `3d010ec`: tool names,
  each tool's description and input schema, resource URIs, and served instructions. No tool name,
  argument name, required-ness or argument type SHALL differ; any other difference (generated schema
  metadata, say) SHALL be listed with its cause in the PR body.
- **R4** — WHEN the server is started under `bin/sandbox.sh` on each supported transport (`stdio`,
  `http`, and `sse` per Clarifications), it SHALL start and a client SHALL list `EXPECTED_TOOLS` from
  it. IF the locked FastMCP 4.x no longer serves SSE, THEN `-t sse` SHALL be rejected before the
  server starts with `exit_status.bad_argument` (a `flag_violations` case), and `README.md`,
  `APP_USAGE`/`APP_HELP`, `SECURITY.md`'s mode table and `AGENTS.md` § Project SHALL drop it in the
  same commit.

Auth (§ Invariants §6):

- **R5** — In `jwt` mode, tokens signed through `token.py` and by the sandboxed `--generate-token`
  SHALL be accepted by the verifier `create_jwt_auth()` builds, and a wrong issuer, audience, secret or
  algorithm, or an expired token, SHALL be refused with a 401 and nothing launched; IF `JWT_SECRET`
  is shorter than 32 characters, THEN both `create_jwt_auth()` and `--generate-token` SHALL refuse it,
  each pinned on its own.
- **R6** — In `oidc` mode, IF any of `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`,
  `MCP_BASE_URL` is unset or empty, THEN provider construction SHALL fail before any provider or
  network request is made, with an error naming all four, pinned by a test for each one-missing
  case. In `none` mode, the server SHALL install no auth provider.
- **R7** — WHEN `typing.get_type_hints(rcac_mcp.auth)['AUTH_MODES']` is resolved, its `Final`
  argument SHALL be a mapping type from `str` to a zero-argument provider factory, and SHALL NOT be a
  `slice`. A test SHALL assert the resolved shape (not merely that evaluation succeeds).

Regression net:

- **R8** — Every test id collected at `3d010ec` SHALL still be collected and pass under the profile's
  `verify`, except ids naming a transport dropped under R4, each listed in the commit body. Test
  modules outside `AGENTS.md` § Testing's internals-bound list SHALL pass with no edit to an existing
  test (added tests are allowed), `tests/test_hygiene.py` excepted for the next clause.
  `tests/harness.py` SHALL remain the only test module importing FastMCP, mcp or httpx, and
  `stack_import_violations` SHALL either flag `pytest.importorskip` called with a literal stack name
  or list that form among the limits its docstring documents.
- **R9** — Every mutation case present at `3d010ec` SHALL be killed for its stated `why` under
  `tests/mutants.py --self-check`; a case whose anchor moved SHALL be re-planted to break the same
  contract, and a retarget or removal SHALL record its reason in the commit body. The tests added for
  R6 and R7 SHALL each have a case that kills them: R7's case restores the slice annotation.

Dependency audit and documentation:

- **R10** — The release recipe's `gate` SHALL include a dependency audit over the tree `uv.lock`
  resolves, which SHALL exit non-zero, naming the package, version and advisory, WHEN any locked
  package carries a known advisory, and SHALL exit non-zero IF the advisory source cannot be
  reached. It SHALL pass on the lock this cycle ships, and SHALL be shown red once against a planted
  lock carrying a version with a published advisory (recorded in the build log). Where the CI
  workflow exists on `develop` when this cycle lands, it SHALL run the same audit (§ Conventions:
  CI mirrors the gate). The profile's `verify` SHALL NOT run it.
- **R11** — In the same commit as the code each describes, `AGENTS.md` SHALL describe the new stack:
  § Project (FastMCP 4.x, MCP SDK 2.x, both protocol eras, the transports that remain); § Invariants
  wherever the API moved (§1's middleware hook, §6's provider types, §7's tool type and whether a
  decorated tool is callable), and the `AUTH_MODES` footgun line, whose PEP 563 claim is false;
  § Testing (the harness's stack touchpoints and the internals-bound list); and § Factory
  → Release recipe's `gate` (R10). The high-blast-radius list only widens.

## Non-goals (no-gos)

- **Adopting FastMCP 4 features beyond what the migration requires**: providers and `mount`
  (`capability-extras`), tool annotations, `_meta` hints and tool search (`tool-surface`), CodeMode,
  composed instructions (`agents-d-instructions`). They are later cycles' material; this cycle only
  leaves the API they will be built on in place.
- **Any tool-surface change**: names, arguments, docstrings, `SERVER_INSTRUCTIONS` text, resources
  (`tool-surface`; § Invariants §9).
- **Fixing the `rcac://storage` `TypeError`** (`storage-paths-resource-typeerror`). This cycle only
  records, in §7, whether the new tool type is callable (the seed's question 2); the resource fix
  follows against it.
- **The executor redesign** (`safe-execution`), including `tests/test_executors.py`'s argv rows and
  the `Connection` fakes.
- **The rename** to `cluster-mcp`, and packaging extras.
- **The `rcac://context` cross-user cache** (§8; `agents-d-instructions`).
- **Creating the CI workflow** (`ci-workflow`), and a repo-wide type checker or `get_type_hints`
  sweep (the typo seed's note; it belongs with `ci-workflow`).
- **A waiver mechanism for advisories with no fixed release** (see Clarifications).
- **New features, new auth modes, new transports** (`https-token-mode` builds on the upgraded HTTP
  transport later).

## Clarifications

- **Q:** Appetite and kind? — **A:** `refactor`, `big`, from the seed's frontmatter; no round-up
  (resolved 2026-10-17).
- **Q:** Does `sse` stay supported? — **A:** It stays exactly as long as the locked FastMCP 4.x serves
  it: removing a transport the stack still serves is a surface change, which is a non-goal, even
  though revision 2026-07-28 deprecates HTTP+SSE. If FastMCP 4 has dropped it, the drop is
  user-visible and follows R4's clean-rejection path (the seed's question 1: "if `sse` goes … it
  belongs in `README.md`"). Which case holds is the plan's research, not a shaping assumption
  (resolved 2026-10-17).
- **Q:** Does the audit fail the gate or only report (the seed's question 3), and which gate? —
  **A:** It fails, and fails closed when the advisory source is unreachable: a gate that passes green
  offline is theatre (§ Conventions, "exit 0 is not enough"). It goes in the release recipe's
  `gate`, not the profile's `verify`: phase gates must stay offline-capable and deterministic, and an
  audit needs the network and answers differently as advisories are published. CI runs it too,
  because CI mirrors the gate (§ Conventions) (resolved 2026-10-17).
- **Q:** Is there a waiver path for an advisory with no fixed release? — **A:** No; it is a
  non-goal. Such an advisory holds the release gate and CI red, which fails safe. If that ever bites,
  a seed takes it up then (resolved 2026-10-17).
- **Q:** CI on a public repo will print advisory names against the lock. Is that acceptable under
  the security lane? — **A:** Yes. Advisory databases and GitHub's dependency graph are already
  public; the security lane holds this project's own unremediated findings, not public advisories
  (resolved 2026-10-17).
- **Q:** `ci-workflow` is in flight; does R10 depend on it? — **A:** No. It is expected to land on
  `develop` first, in which case R10's CI clause applies. If it has not landed when this cycle does,
  the clause is vacuous and `ci-workflow` carries the audit step when it mirrors the gate; this cycle
  does not create CI (resolved 2026-10-17).
- **Q:** The typo seed's R1–R2? — **A:** Carried as R7 (the resolved shape, not evaluation success)
  and R9 (seen red, by a mutation case that restores the slice). Its other notes, the redundant
  local `OIDCProxy` import (`auth.py:44`) and the trailing blank line, are left to the plan: cleaned
  if the rewrite touches them, not criteria (resolved 2026-10-17).
- **Q:** OIDC was a non-goal of `restore-test-coverage` because exercising it needs a live discovery
  endpoint. — **A:** R6 pins only the all-or-nothing configuration check, which precedes any
  network request; a live OIDC flow stays untested (resolved 2026-10-17).
- **Q:** Eleven criteria sit just past the size circuit-breaker's ~8–10. Split? — **A:** No. One
  deliverable: R5 restates contracts the suite already pins, split from R6 only so each has its own
  pass/fail, and R8 and R9 are the regression net over everything else, not separate work, and the
  plan can slice phases by subsystem (resolved 2026-10-17).

Raised by planning and its adversarial design review (each changes how an R-ID is read):

- **Q:** The MCP SDK 2.2+ closes an idle streamable-HTTP session after 30 minutes (2.x never did).
  Does "behaves exactly as before" require pinning "never"? — **A:** No. Keep the SDK default and
  record it in `AGENTS.md` and the squash body as an accepted 4.x behaviour change (resolved
  2026-10-17).
- **Q:** R3 lists differences "in the PR body", but landing is `squash-local`. — **A:** The squash
  commit body carries R3's difference list (resolved 2026-10-17).
- **Q:** Does R8's `tests/test_hygiene.py` exception cover widening its stack-name list to the new
  import names (`httpx2`, `httpcore2`, `mcp_types`)? — **A:** Yes (resolved 2026-10-17).
- **Q:** How is R2's "with no `initialize`" observed? — **A:** The server saw no `initialize` on
  that connection (a server-side method log); "answer `server/discover` with the instructions"
  means the server saw `server/discover` and the client's instructions came from its
  `DiscoverResult` (resolved 2026-10-17).
- **Q:** May the suite run the audit script to prove it fails closed offline, given R10's last
  sentence? — **A:** Only offline by construction: uv is told it is offline, every proxy is a dead
  loopback port, and uv's own offline refusal is asserted, so no advisory lookup can happen
  (resolved 2026-10-17).
- **Q:** How far does R1's lock move? — **A:** The stack (`fastmcp`, `mcp`), what the resolver
  forces, and what the audit reports, nothing else; every package whose major version moves is named
  with its reason in a commit body (an advisory-driven reason without naming the advisory). If
  `paramiko` or `fabric` moves, an offline smoke test of the `ssh` executor lands in this cycle
  (resolved 2026-10-17).
- **Q:** FastMCP 4's `OIDCProxy` turns on client-metadata (CIMD) fetches and `resource` forwarding,
  which 2.14 lacked. Is that "the same auth posture"? — **A:** No. Both are passed off, pinned by
  R6's tests, and noted in § Invariants §6 and `SECURITY.md` pending a deliberate decision
  (resolved 2026-10-17).
- **Q:** On 2.x an `MCPError` raised around a tool call reached the client as a tool error result;
  on 4.x it is a protocol error. — **A:** Parity: it is a tool error result carrying `str(exc)`, as
  are the other exceptions the boundary converts (resolved 2026-10-17).

All answers came from the cycle's foreman, which the maintainer made judge at every gate for this
effort.

## Related materials

- Seed: [`issues/stack-upgrade.md`](../../issues/stack-upgrade.md) (promoted 2026-10-17;
  `status: adopted:stack-upgrade`), including its 2026-10-16 notes on the harness rewrite point and
  `pytest.importorskip`
- Absorbed seed: [`issues/auth-modes-annotation-typo.md`](../../issues/auth-modes-annotation-typo.md)
  (`status: adopted:stack-upgrade`)
- Roadmap: `ROADMAP.md` → *Move the stack before building on it*; downstream
  `storage-paths-resource-typeerror`, `agents-d-instructions`, `capability-extras`, `tool-surface`,
  `https-token-mode`; sibling `ci-workflow`
- Prior cycle: [`spec/restore-test-coverage/`](../restore-test-coverage/) (the suite this cycle
  leans on)
- `AGENTS.md` § Invariants §1, §5, §6, §7, §9 and the high-blast-radius list; § Testing (harness,
  internals-bound list, mutation runner); § Packaging (`uv.lock` same-commit rule); § Conventions
- Source: `pyproject.toml`, `uv.lock`, `src/rcac_mcp/auth.py`, `token.py`, `middleware.py`,
  `server.py`, `context.py`, `__init__.py`, `tests/harness.py`
