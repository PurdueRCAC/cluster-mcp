# GOAL — Make the coupled core's contracts executable

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** restore-test-coverage
- **kind:** test
- **appetite:** big

## Problem

The documentation strip left a small, honest suite (`tests/test_registry.py`,
`tests/test_instructions.py`, `tests/test_cli.py`) and a `tests/conftest.py` that fails the run on
any test carrying neither `unit` nor `integration`. Those tests pin the tool registry, the served
instructions and the removed CLI flags. The coupled core (`AGENTS.md` § Factory → Profile) has
**never had a test**, and every path § Invariants marks highest-blast-radius sits in it:

- `context.py` / `middleware.py` (§1): the `ContextVar` that keeps one request's tool call from
  running on another request's executor, and the middleware that sets it per call;
- `middleware.py` / `executor/delegate.py` (§5): identity-claim precedence `sub` → `email` →
  `preferred_username` (`AuthExecutorMiddleware._extract_identity`), the hard failure when no claim
  is present, the `PermissionError` for an unmapped identity, the user-map file format, and the
  `sudo -n -H -u <local_user> <shell> -c <command>` argv with `shlex.quote` on `cwd` only;
- `__init__.py` (§4): `MCPServerApp._resolve_exec_mode()`, the five-rung posture ladder, and which
  middleware each mode installs;
- `auth.py` / `token.py` (§6): the `JWT_SECRET` ≥ 32 floor enforced separately in
  `create_jwt_auth()` and in the `--generate-token` path of `MCPServerApp.run()`, and the
  `ISSUER` / `AUDIENCE` / `ALGORITHM` triple that signer and verifier must share;
- `executor/*` (§2): the `Executor` protocol all three backends must satisfy;
- `tools/*` (§1, §7): tools reach the cluster only through `get_executor()`.

Confirmed against `origin/develop` `ca4911e` on 2026-10-16: the anchors above still say what the seed
claims. **Pre-existing:** yes — the gap predates the strip; the strip only made it visible.

It matters now because of what comes next. `ci-workflow` will run this suite on every push;
`stack-upgrade` moves FastMCP 2.x → 4.x and `mcp` 1.x → 2.x and re-expresses auth on the new API;
`safe-execution` changes the `Executor` protocol to an argv API and rewrites every tool on it. Each of
those changes the coupled core. A `verify:` gate over a suite that never exercises the core cannot
tell those cycles whether they preserved its contracts, so today it is theatre exactly where the
blast radius is largest.

## Outcome / vision

A suite whose failures mean something. Replacing `executor_var` with a module global turns it red;
reordering the claim precedence, dropping `-n`, swapping two rungs of the ladder, or lowering one of
the two secret floors turns it red. It needs no root, no sudoers rule, no SSH host, no second real
identity and no real `HOME`. And it is written against **observable contracts**, so that when
`stack-upgrade` and `safe-execution` change the machinery underneath, the tests either keep passing
or fail in a place that names the contract that moved.

## Acceptance criteria (the contract)

Contracts (each pins one § Invariants rule):

- **R1** — WHEN two tool calls run concurrently on the same server, each under a different executor
  (two shared-mode executors, or two delegate-mode identities mapped to different local users), each
  call's command SHALL reach only its own executor, and neither call's result SHALL come from the
  other's. (§1)
- **R2** — IF a tool call reaches a tool with no executor set for that request (no executor
  middleware installed, or delegate mode with no access token), THEN the call SHALL fail with an
  error the MCP client sees and no command SHALL run — including when an earlier or concurrent
  request did set an executor. (§1)
- **R3** — WHEN any tool the server serves (`EXPECTED_TOOLS`) is called through the MCP surface with
  a recording executor installed by `SharedExecutorMiddleware`, the tool's work SHALL reach that
  executor, the tool's result SHALL reach the client, and no process, SSH connection or `sudo`
  invocation SHALL be made outside it. (§1, §7)
- **R4** — WHEN a delegate-mode tool call carries claims, the command SHALL run as the local user
  mapped to the first non-empty of `sub`, `email`, `preferred_username`, in that order; IF none of
  the three is present and non-empty, THEN the call SHALL fail and no command SHALL run, with no
  fallback identity. (§5)
- **R5** — IF a delegate-mode identity is absent from the user map, THEN the tool call SHALL fail
  with a not-authorized error and no command SHALL run, and constructing `DelegatingExecutor`
  directly for that identity SHALL raise `KeyError`; IF the user-map file holds a line without a
  local user, THEN loading SHALL fail with a `ValueError` naming that line number, while `#` comment
  lines and blank lines load cleanly. (§5)
- **R6** — WHEN `DelegatingExecutor.run` executes a command, the process it starts SHALL be exactly
  `sudo -n -H -u <mapped local user> <shell> -c <command line>`, where `<shell>` is the server
  process's `$SHELL` captured at construction (a later change to `$SHELL` does not alter it) and a
  `cwd` containing spaces or shell metacharacters is quoted as a single word while the command
  itself is passed through unquoted — asserted on a recorded call, never by running `sudo`. (§5)
- **R7** — WHEN the server app resolves its execution mode, it SHALL follow the five rungs of
  § Invariants §4 in order (explicit `-e`; `stdio` → `ssh`; SSH host from `--ssh-host` or
  `RCAC_SSH_HOST` → `ssh`; `auth == 'none'` → `local`; otherwise `delegate`), so in particular a
  configured auth mode with no SSH host and no `-e` SHALL resolve to `delegate`, never `local`; and
  it SHALL install `AuthExecutorMiddleware` for `delegate` and `SharedExecutorMiddleware` for every
  other mode. (§4)
- **R8** — IF `JWT_SECRET` is unset or shorter than 32 characters, THEN both `create_jwt_auth()` and
  `rcac-mcp --generate-token` SHALL refuse — the CLI with `exit_status.bad_argument` and no token on
  stdout — and WHEN it is exactly 32 characters, both SHALL accept it. (§6)
- **R9** — WHEN a token minted by `rcac-mcp --generate-token --sub <X>` (or `generate_token`) with
  secret `S` is presented to the `jwt` verifier built from the same `S`, it SHALL be accepted with
  identity `X`; IF the token's issuer, audience, signing secret or algorithm differs from the
  verifier's, or it has expired, THEN it SHALL be rejected. (§6)
- **R10** — Each of `SSHExecutor`, `LocalShellExecutor` and `DelegatingExecutor` SHALL satisfy
  `isinstance(x, Executor)`, constructed without a real network connection or `sudo`. (§2)

Suite-wide:

- **R11** — Every test this cycle adds SHALL carry `@mark.unit` or `@mark.integration`
  (`tests/conftest.py` is extended, not replaced); no test SHALL read or write the developer's real
  `HOME`, reach a real host, or invoke real `sudo`; every test that drives the CLI SHALL do so through
  `bin/sandbox.sh`; and the existing tests and their check-function names and test ids SHALL remain
  and pass. The profile's full `verify` SHALL pass.
- **R12** — For each of R1–R10, the build SHALL show the contract's test failing against a planted
  violation of that contract (for example: `executor_var` as a module global, precedence reordered,
  `-n` dropped, two rungs swapped, one floor lowered to 31, the verifier's audience changed) and
  passing once it is reverted — either as a standing negative control in the suite or as a recorded
  mutation in the cycle's build record. No planted violation is committed to `src/`.

## Non-goals (no-gos)

- **Fixing any defect the tests surface.** This cycle pins today's behaviour; a test that would have
  to assert a known defect leaves that path unpinned and names the seed that owns it.
- **The timeout asymmetry** between `SSHExecutor` and the other two backends (§3) — owned by
  `executor-timeout-asymmetry`, absorbed into `safe-execution`. The timeout path is not pinned.
- **The cross-user `rcac://context` cache** keyed by hostname (§8) — owned by
  `context-cache-cross-user` / `agents-d-instructions`. Resources are not under test here.
- **The `storage_paths()` resource `TypeError`** (§7) — owned by `storage-paths-resource-typeerror`.
- **The `AUTH_MODES` annotation typo** — owned by `auth-modes-annotation-typo`, absorbed into
  `stack-upgrade`.
- **OIDC proxy behaviour**, including the four-variable all-or-nothing check (§6): it needs a live
  discovery endpoint to exercise past configuration, and `stack-upgrade` re-expresses it.
- **How `cwd` is path-expanded** in delegate mode: R6 pins quoting, not expansion. Owned by
  `safe-execution` (its 2026-10-16 note).
- **`absence_violations` classifying a leftover by git status instead of file suffix** (the seed's
  2026-10-16 note): a message fix to an existing check, not a core contract; owned by
  `absence-check-leftover-classification`.
- **CI** (`ci-workflow`), coverage percentages or a coverage tool, and any change to `src/`.

## Clarifications

- **Q:** Which machinery may the tests lean on, given that `stack-upgrade` replaces FastMCP 2.x and
  `mcp` 1.x and `safe-execution` replaces the executor API? — **A:** A design constraint, not a
  design. Prefer the server's public MCP surface (an in-memory client over `create_mcp_server(…)`,
  or the CLI under `bin/sandbox.sh`) and the executor contract through fakes, over FastMCP 2.x
  internals. Where a contract can only be reached through an internal — the auth verifier and the
  access-token lookup are the likely cases, since an in-memory client does not pass through the HTTP
  auth layer — the test says so in its docstring and is kept isolated (its own module or clearly
  grouped), so `stack-upgrade` can rewrite it knowingly. R6's argv is expected to change under
  `safe-execution`; its test is that cycle's deliberate rewrite, not an obstacle (resolved
  2026-10-16).
- **Q:** How is a delegate-mode test kept off real `sudo` and real identities? — **A:** The process
  launch is replaced by a fake that records the argv; identities come from stub claims or a minted
  test token and a user-map file under `tmp_path` (resolved 2026-10-16).
- **Q:** The seed's R6 asked only for `isinstance` on all three backends, and `SSHExecutor` connects
  at construction (`executor/ssh.py`, `__init__` calls `open()`). — **A:** R10 keeps the check and
  requires construction without a real connection; how is the plan's (resolved 2026-10-16).
- **Q:** What async mode does `pytest-asyncio` run in? — **A:** No `asyncio_mode` is configured, so
  strict mode; the existing suite drives async code with `asyncio.run`. The plan picks; nothing here
  depends on it (resolved 2026-10-16).
- **Q:** Does "a test exists" satisfy a `kind: test` criterion? — **A:** No. Each contract test must
  be shown red against a planted violation (R12); a test that cannot be made red does not pin its
  contract (resolved 2026-10-16).
- **Q:** Size circuit-breaker: ten contract criteria plus two suite-wide ones, one deliverable.
  Ship as one cycle, or split? — **A:** One cycle, R1–R12 as written. It is one deliverable, and
  every contract must be pinned before `stack-upgrade`. Ten contract criteria sit at the breaker's
  upper bound, but each is a small, independent test module the plan can slice into phases; R11 and
  R12 are suite-wide criteria, not separate deliverables (resolved 2026-10-16).

All answers came from the cycle's foreman, which the maintainer made judge at every gate for this
effort.

## Related materials

- Seed: [`issues/restore-test-coverage.md`](../../issues/restore-test-coverage.md) (promoted
  2026-10-16; `status: adopted:restore-test-coverage`)
- Roadmap: `ROADMAP.md` entry for this seed; downstream `ci-workflow`, `stack-upgrade`,
  `safe-execution`
- `AGENTS.md` § Testing, § Invariants §1–§7 and the high-blast-radius list, § Conventions (markers,
  `bin/sandbox.sh`, pytest drives step back into the repo)
- `SECURITY.md` § *Request Isolation in Delegate Mode*
- Sources: `src/rcac_mcp/context.py`, `middleware.py`, `executor/{base,shell,ssh,delegate}.py`,
  `__init__.py` (`_resolve_exec_mode`, `run`), `auth.py`, `token.py`, `tools/__init__.py`,
  `server.py` (`create_mcp_server`)
- Existing suite: `tests/conftest.py`, `tests/test_registry.py`, `tests/test_instructions.py`,
  `tests/test_cli.py`
- Prior cycle: [`spec/strip-docs-subsystem/`](../strip-docs-subsystem/)
