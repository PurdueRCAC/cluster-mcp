---
slug: restore-test-coverage
title: Make the coupled core's contracts executable
kind: test
appetite: big
status: done
branch: test/restore-test-coverage
base: develop
current_phase: done
last_updated: '2026-10-16'
phases:
- id: P1
  name: Request isolation through real concurrent calls, on the harness, the unit
    guard and the mutation runner
  status: done
  satisfies:
  - R1
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/restore-test-coverage/verify/gate.sh P1
- id: P2
  name: Every served tool reaches only the executor the shared middleware installs
  status: done
  satisfies:
  - R3
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/restore-test-coverage/verify/gate.sh P2
- id: P3
  name: No executor set means a client-visible error and no command, after or during
    another request
  status: done
  satisfies:
  - R2
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/restore-test-coverage/verify/gate.sh P3
- id: P4
  name: Identity-claim precedence over real tokens, and the user map's refusals
  status: done
  satisfies:
  - R4
  - R5
  depends_on:
  - P3
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/restore-test-coverage/verify/gate.sh P4
- id: P5
  name: The exact sudo argv and the Executor protocol across all three backends
  status: done
  satisfies:
  - R6
  - R10
  depends_on:
  - P4
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/restore-test-coverage/verify/gate.sh P5
- id: P6
  name: The execution-mode ladder and the middleware each mode installs
  status: done
  satisfies:
  - R7
  depends_on:
  - P5
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/restore-test-coverage/verify/gate.sh P6
- id: P7
  name: Both secret floors and the signer/verifier contract
  status: done
  satisfies:
  - R8
  - R9
  depends_on:
  - P6
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/restore-test-coverage/verify/gate.sh P7
- id: P8
  name: Suite-wide close-out, AGENTS.md and downstream seeds, the deferral ledger,
    a fresh-clone run
  status: done
  satisfies:
  - R11
  - R12
  depends_on:
  - P7
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/restore-test-coverage/verify/gate.sh P8
review:
  last_reviewed_commit: 38f2e19616ee83542f7ca6d0aa7d70787ba71b7d
  verdict: approved
  blocked_reason: ''
  cycle: 3
---

# TECH.md — Make the coupled core's contracts executable

The **context engine and finite-state machine** for building this cycle. The YAML frontmatter
above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/restore-test-coverage/TECH.md`); the
per-phase checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md). Section references below (§2.x) are to it.
- **Backing research:** [`research/00-digest.md`](research/00-digest.md), briefs `01`–`06`, and
  executable [`research/prototypes/`](research/prototypes/).
- **Gates:** [`verify/`](verify/): `gate.sh` (the one command each phase runs), `run.sh`,
  `controls.py`, `ids_check.py` (reads the JUnit report) and `ids/P0..P8.txt` (the test ids each
  phase requires). The adversarial design review's findings and what each changed are in PLAN §4.

## Frontmatter field reference

- `status` (top): `planned | in_progress | blocked | in_review | done` (`done` is stamped by
  `code-publish` after confirmation, just before landing — the terminal state of the retained record)
- `appetite`: `small | big` — caps phase count and build-iteration budget (circuit breaker).
- `branch`, `base`: the cycle's branch (prefix per GOAL `kind`, from the profile's `branches`) and the
  profile's `base`.
- phase `status`: `pending | in_progress | done | blocked`
- `satisfies`: GOAL R-IDs this phase delivers (traceability anchor for `code-review`). R11 and R12
  are suite-wide: every gate exercises them (markers, guard, sandbox rule, each slice's planted
  cases), and P8 owns them as a whole. No R-ID here is met by a `spec/` artifact; every one is
  graded from the suite and the CLI.
- `depends_on`: phase ids that must be `done` first (a phase is actionable only when met).
- `parallel`: `true` only for genuinely independent, non-coupled work. Every phase here is `false`:
  the slices share `tests/harness.py`, `tests/conftest.py` and `tests/mutants.py`, and pin the
  coupled core's contracts, so they are built in order.
- `hammerable`: `false` marks a correctness/security phase that scope-hammering must **never** cut.
- `hill`: `uphill` (still figuring it out) → `crest` (unknowns resolved) → `downhill` (just
  executing). A phase stuck `uphill` across builds is a raised hand → escalate to the human.
- `attempts`: durable failed-verify counter (absent = 0), bumped by `set_phase.py --phase P<n>
  --record-attempt` on every red verify gate; `next_phase.py` warns at ≥3 — the circuit breaker
  runs on this file, not on session memory.
- `verify`: the exact command that proves the phase. Here it is always
  `sh spec/restore-test-coverage/verify/gate.sh P<n>`, which runs inside `bin/sandbox.sh` (PLAN §6).
- `review.cycle`: completed review passes, auto-incremented by every `set_phase.py --verdict …`;
  REVIEW.md's "Cycle {n}" mirrors it and the ≤3-cycle bound is graded against it. `--verdict approved`
  also clears `review.blocked_reason` unless one is passed explicitly.

## Conventions (apply to every phase)

- Commit conventions, code style, and load-bearing invariants come from the repo's `AGENTS.md` — it
  is the constitution. Walk the sections of its § Invariants that this change touches (PLAN §3);
  that is the curated footgun checklist.
- One phase per `code-build` invocation by default; one atomic commit containing **both** the code and
  the `TECH.md` state change. Branch commit subjects follow the house style `[{category}] Build {slug}
  P<n>: …` (no `WIP:` prefix), where `{category}` is the GOAL's `kind` verbatim — squashed away at
  `code-publish` per the profile's `landing`. Trailers follow the profile's `branch commits`.
- A PR body (when the profile's `landing` opens one) ends with an attribution naming the actual
  harness, model, and variant.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`). This
  cycle changes no CLI, tool or dependency.
- **Cycle rules:**
  - **Never edit `src/`.** The gate fails on any committed or working-tree difference from the
    merge base.
  - Every new test carries `@pytest.mark.unit` or `@pytest.mark.integration`.
  - Comments and docstrings state the invariant or the *why*, never `R#`/`P#`.
  - A test that leans on an internal (PLAN §2.2 and research `06`) says so in its docstring.
  - Build every server and middleware inside the coroutine handed to `harness.drive` (the builders
    refuse otherwise), and request `launches` for any in-process server call in an integration
    test (the harness fence refuses otherwise).
  - **Build record (R12):** the gate runs `tests/mutants.py --self-check` over every case the phases
    so far own. Paste its report (one line per case: killed by which target, for which reason) into
    the phase commit body.
  - A case that survives, or is killed for the wrong reason, means the test is hollow or the reason
    is wrong: fix the test, never the target list. A retarget, a reworded `why` or a removal goes in
    the commit body with its reason.
- **Deferrals.** A test that would have to assert a defect leaves that path unpinned. Its record goes
  to `issues/{slug}.md`, pre-shaped from the KB's `ISSUE.md` template (`status: unshaped`), plus a
  `ROADMAP.md` entry. A live cross-user, wrong-host or unauthenticated execution path goes to
  `.security/issues/{slug}.md` plus `.security/ROADMAP.md` instead. Name the file in this `TECH.md`
  (the phase body) in the same commit; P8's ledger checks it. Never `spec/` and never the KB inbox.

---

## Phase P1 — Request isolation through real concurrent calls
**Satisfies:** R1 (and the first slices of R11, R12) · **Depends on:** —
**Goal:** two concurrent tool calls on one server, each under a different delegate identity, each
run as their own user and get back only their own result. A module-global `executor_var` or a
middleware that caches one executor turns this red, as a standing mutation in the suite. The
harness, the unit guard, the sandbox rule and the mutation runner that every later slice reuses land
here. This is the novel part, built first.

- [x] `tests/conftest.py`: keep the collection hook unchanged. Add:
      - the session `PATH` shim (`sudo`, `ssh` refused);
      - the unit guard (HOME/XDG redirection, env blanking, the widened process and network
        refusers, teardown failure on refusals);
      - the `guard` fixture and the `launches` recorder (unit and integration);
      - the main-context executor check after every test (PLAN §2.3).
- [x] `tests/harness.py`: `Outcome`, `drive`, `serving`, `http_client`, `in_memory`, `call`,
      `call_http`, `mint`, `user_map`, `RecordingExecutor`, `Rendezvous`, `delegate_server`,
      `shared_server`, `bare_server`, with the fence and the build-inside-the-loop rule (PLAN §2.2).
      Its module docstring names it the single FastMCP/mcp touchpoint and the `stack-upgrade`
      rewrite point.
- [x] `tests/test_isolation.py`: `isolation_violations` and the tests PLAN §2.4 lists for R1.
- [x] `tests/test_hygiene.py`: `sandbox_violations` (aliases, exec family, asyncio, `sudo`/`ssh`
      argv), `test_cli_drives_are_sandboxed`, its controls, and the self-tests of the guard, the
      `PATH` shim, the fence and the build-inside-the-loop rule.
- [x] `tests/mutants.py` (not collected): `Case` with `why`, `apply`, `run_child` (JUnit),
      `mutation_violations`, the CLI with `--self-check`, and the two isolation cases from
      `research/prototypes/mutation_cases.py` (PLAN §2.5).
- [x] `tests/test_mutations.py` (unit): `test_mutation_anchor_applies[<case>]` and
      `test_mutation_check_flags_survivors[…]` on synthetic JUnit.
- [x] Confirm `--self-check` really runs children (it takes seconds), and that
      `isolation-module-global` is killed by both targets with `ran as`.
- [x] **Remediation, review cycle 1 (F2):** §1's "set per tool call" for every executor
      middleware. The class is the two in `src/` (`SharedExecutorMiddleware`,
      `AuthExecutorMiddleware`); `test_sequential_shared_calls_each_get_the_executor` and
      `test_sequential_delegate_calls_each_get_their_executor` make three calls in turn on one
      server (alice, bob, alice for delegate). Planted: `shared-middleware-sets-first-call-only` and
      `auth-middleware-sets-first-call-only`, each killed with `ran 0 times` (the later calls find
      no executor).
- **Verify:** `sh spec/restore-test-coverage/verify/gate.sh P1`. It checks:
  - `src/` untouched, and the marker witness;
  - the suite green, with every id in `ids/P0.txt` and `ids/P1.txt` passed in the JUnit report;
  - `controls.py 1` (the isolation, sandbox and mutation checks reject planted shapes; P1's cases
    present);
  - `tests/mutants.py --self-check` over P1's cases.
- **Touches:** `tests/conftest.py`, `tests/harness.py`, `tests/test_isolation.py`,
  `tests/test_hygiene.py`, `tests/mutants.py`, `tests/test_mutations.py`.

## Phase P2 — Every served tool reaches only the installed executor
**Satisfies:** R3 · **Depends on:** P1
**Goal:** all 23 `EXPECTED_TOOLS`, called through an in-memory client with a `RecordingExecutor`
installed by `SharedExecutorMiddleware`, do their work on that executor and return its result. No
process, socket or `sudo` happens outside it.

- [x] `tests/test_tools.py`: `TOOL_CASES` (args, responder, expect per tool), `tool_violations`,
      `test_tool_reaches_only_the_installed_executor[<tool>]`, `test_tool_cases_cover_expected_tools`,
      and the bypass controls (PLAN §2.4). Amended in build: each case also names `reaches`, a
      fragment (the tool's own argument, or the command it wraps) some executor call must carry,
      passed to `tool_violations` as an optional fifth argument; its control is
      `test_tool_check_requires_the_tool_argument_at_the_executor`. A tool that returns nothing
      (`write_file`) is otherwise pinned only by "some call happened".
- [x] `tests/mutants.py`: add `tool-builds-local-executor` and `tool-builds-ssh-executor`.
- **Verify:** `sh spec/restore-test-coverage/verify/gate.sh P2` (cumulative: P0–P2 ids;
  `controls.py 2` adds `tool_violations` and `TOOL_CASES == EXPECTED_TOOLS`).
- **Touches:** `tests/test_tools.py`, `tests/mutants.py`.

## Phase P3 — No executor set means a client-visible error and no command
**Satisfies:** R2 · **Depends on:** P2
**Goal:** a tool call with no executor for its request fails where the client sees it, and nothing
runs. This holds for the bare server (all 23 tools) and for the tokenless delegate call, including
right after, and while, another request on the same server or process did set one.

- [x] `tests/test_no_executor.py`: `refusal_violations` (with its required reason,
      `No executor configured`) and the tests PLAN §2.4 lists for R2. The earlier and concurrent
      variants use the same `delegate_server` for the HTTP and the in-memory client, and one shared
      `Rendezvous(2)` across the two shared-mode servers. Every server is built inside the driven
      coroutine.
- [x] `tests/mutants.py`: add `no-executor-module-global`, `no-executor-default-fallback`,
      `no-token-fallback-identity`, `auth-middleware-sets-at-construction`,
      `shared-middleware-sets-at-construction` and `transfer-local-fallback`.
- **Verify:** `sh spec/restore-test-coverage/verify/gate.sh P3`.
- **Touches:** `tests/test_no_executor.py`, `tests/mutants.py`.

## Phase P4 — Identity-claim precedence over real tokens, and the user map's refusals
**Satisfies:** R4, R5 · **Depends on:** P3
**Goal:** over the in-process HTTP route with real JWTs, the command runs as the user mapped to the
first non-empty of `sub`, `email`, `preferred_username`. No claim, or an unmapped first claim, fails
with nothing run and no fall-through. `DelegatingExecutor` raises `KeyError` for an unmapped
identity. The map loader names a malformed line and loads comments and blanks cleanly.

- [x] `tests/test_identity.py`: `delegation_violations` and the tests PLAN §2.4 lists for R4/R5.
      Tokens come from `harness.mint` with exactly the claims each row names. Refusals carry
      `not authorized` (unmapped) or `Could not extract` (no claim).
- [x] `tests/mutants.py`: add the ten identity and map cases.
- [x] **Remediation, review cycle 1 (F3):** the malformed-line fixture now has a comment and a
      blank line before the bad line, so its file line (5) differs from its entry count and from
      its count among kept lines (both 3); the test requires exactly `line 5`. Planted:
      `map-line-counts-entries` (`{len(user_map) + 1}` for `{line_num}`), killed with
      `does not name line 5`. `map-line-number-dropped`'s `why` follows the reworded message
      (`line 3` → `does not name line 5`). The loader's line number is the class's only site.
- **Verify:** `sh spec/restore-test-coverage/verify/gate.sh P4`.
- **Touches:** `tests/test_identity.py`, `tests/mutants.py`.

## Phase P5 — The exact sudo argv and the Executor protocol
**Satisfies:** R6, R10 · **Depends on:** P4
**Goal:** `DelegatingExecutor.run` launches exactly `sudo -n -H -u <user> <$SHELL at construction> -c
<command line>`, with `cwd` quoted as one word and the command verbatim, recorded at `Popen`. All
three backends satisfy `Executor`, with `SSHExecutor` built on a fake `Connection`.

- [x] `tests/test_executors.py`: `sudo_argv_violations` and the tests PLAN §2.4 lists for R6/R10.
      Its docstring says the argv rows are `safe-execution`'s deliberate rewrite and the `ssh` row
      fakes `rcac_mcp.executor.ssh.Connection`.
- [x] `tests/mutants.py`: add the five argv cases and the three protocol cases.
- **Verify:** `sh spec/restore-test-coverage/verify/gate.sh P5`.
- **Touches:** `tests/test_executors.py`, `tests/mutants.py`.

## Phase P6 — The execution-mode ladder and its middleware
**Satisfies:** R7 · **Depends on:** P5
**Goal:** the 13 ladder rows resolve as § Invariants §4 orders them, observed through
`MCPServerApp.main` with server construction stubbed. A configured auth with no host and no `-e` is
`delegate`, never `local`. `delegate` installs `AuthExecutorMiddleware`, every other mode
`SharedExecutorMiddleware`. The `ssh` rung fails closed without a host.

- [x] `tests/test_exec_mode.py`: `LADDER_CASES`, `ladder_violations`, `test_exec_mode_ladder[…]`,
      and the drift controls (PLAN §2.4, research `04`). Its docstring names the
      `rcac_mcp.create_mcp_server` stub and the `Connection` fake as `rcac_mcp` seams.
- [x] `tests/mutants.py`: add the five ladder cases.
- [x] **Remediation, review cycle 1 (F1):** every value rung 1 takes has rows of its own:
      `explicit-ssh-over-auth-none` and `explicit-ssh-over-auth` (mode `ssh`, exit 2, `SSH host
      required`) and `explicit-delegate-over-host`, beside the three `-e local` rows and
      `explicit-delegate-over-stdio`; the ladder is now 16 rows. Planted, one per value:
      `ladder-explicit-local-ignored`, `ladder-explicit-ssh-ignored` (the reviewer's
      `self.exec_mode != 'ssh'`) and `ladder-explicit-delegate-ignored`, each killed with `mode:`.
- [x] **Remediation, review cycle 2 (N1):** the class predicate is *an explicit `-e` value is
      decided at rung 1 regardless of every input a later rung reads*. Evaluated against
      `_resolve_exec_mode` and `MCPServerApp.run`: the ladder reads `transport`, `--ssh-host`,
      `RCAC_SSH_HOST` and `auth`, and nothing else (`RCAC_USER_MAP` and the OIDC variables are
      read after resolution, by the middleware and the stubbed server). Beyond the five triggers
      the review named, auth `oidc` is a distinct later-rung value (rung 5's other way in), so it
      joins the cross-product. `EXPLICIT_CASES` now holds 3 × 6 rows
      (`explicit-{local,ssh,delegate}-over-{stdio,host,env-host,auth-none,auth,oidc}`; the seven
      existing ids kept), each asserting mode, middleware, the SSH host connected to, and the exit
      status and `SSH host required` where `-e ssh` has no host. The predicate itself is the gate:
      `test_explicit_mode_decides_alone[local|ssh|delegate]` drives all 36 combinations of
      transport × auth × flag host × env host per value. The ladder is now 27 rows. Planted:
      `ladder-explicit-delegate-yields-to-auth-none` and `ladder-explicit-yields-to-env-host` (the
      reviewer's plants a and b), `ladder-explicit-yields-to-oidc` (the extra input), and
      `ladder-explicit-misrouted` (rung 1 decides to the wrong mode), which turns red the rows
      whose later rungs agree with the explicit value, where no input-keyed plant can. `-e
      delegate` with auth `none` resolves to `delegate` with the auth middleware, which refuses
      every call (`test_no_executor.py`); pinned as today's behaviour.
- **Verify:** `sh spec/restore-test-coverage/verify/gate.sh P6` (adds the direct drive
  `rcac-mcp -t stdio -a jwt`: exit 2, `Execution mode: ssh`, `SSH host required`).
- **Touches:** `tests/test_exec_mode.py`, `tests/mutants.py`.

## Phase P7 — Both secret floors and the signer/verifier contract
**Satisfies:** R8, R9 · **Depends on:** P6
**Goal:** `create_jwt_auth()` and `rcac-mcp --generate-token` each refuse an unset, empty or
31-character `JWT_SECRET` (the CLI with `bad_argument` and no token) and accept 32. Tokens minted by
`generate_token` and by the sandboxed CLI are accepted, as their subject, by the verifier built from
the same secret. A different issuer, audience, secret or algorithm, or an expired token, is rejected
with nothing run.

- [x] `tests/test_tokens.py`: `token_cli_violations` and the tests PLAN §2.4 lists for R8/R9. CLI
      drives are `[str(SANDBOX), 'env', 'JWT_SECRET=…', str(CLI), …]` (the sandbox blanks the
      secret; `env` sets it after). Rejections go through `call_http` (the 401 surfaces at
      connect). `test_cli_minted_token_is_accepted` presents its token under `launches`.
- [x] `tests/mutants.py`: add the ten floor and token cases (two floors planted separately; the two
      unchecked-verifier plants show the rejection half red).
- **Verify:** `sh spec/restore-test-coverage/verify/gate.sh P7` (adds direct `--generate-token`
  drives at 31 and 32 characters).
- **Touches:** `tests/test_tokens.py`, `tests/mutants.py`.

## Phase P8 — Suite-wide close-out
**Satisfies:** R11, R12 · **Depends on:** P7
**Goal:** the suite as a whole meets R11 and R12 on committed state. `AGENTS.md` describes it. The
seeds that will rewrite parts of it know where. Every deferral is recorded.

- [x] `AGENTS.md` § Testing: rewrite per PLAN §2.6. Name every new module (including
      `mutants.py`), the guard, the `PATH` shim, the harness and its build-inside-the-loop rule, the
      gate-run mutation runner, the recorded limitations (the issuer/audience swap; file I/O is
      unguarded), and the internals-bound list. Remove "The suite is three files" and "no tests
      yet".
- [x] Dated (2026-10-…) append-only notes on `issues/stack-upgrade.md`, `issues/safe-execution.md`
      and `issues/ci-workflow.md` (PLAN §2.6).
- [x] **Deferral ledger:** walk P1–P7's bodies and commit messages for "do not fix here", "known
      limitation", "follow-up", "deferred" and "unpinned". Confirm each has its `issues/{slug}.md`
      plus `ROADMAP.md` entry (or `.security/` pair) and is named in this file. The gate checks that
      every `issues/*.md` named here exists and is indexed.
- [x] Run the gate on committed state. The clone in `gate.sh P8` reads committed state, so first
      commit P8's work in a throwaway `git worktree add --detach` and run the gate there; then make
      the phase commit and run it again on the branch. `gate.sh P8 --phase-only` runs P8's own
      checks alone for the fail-once step.
- **Deferral ledger (built 2026-10-16).** P1–P7's bodies and commit messages record no new
  deferral: no test had to assert a defect, nothing was left "do not fix here" or "follow-up", and
  no `.security/` entry was needed. Every path the cycle leaves unpinned is a GOAL non-goal that
  already has its seed and `ROADMAP.md` entry:
  - the timeout asymmetry: `issues/executor-timeout-asymmetry.md`, absorbed into
    `issues/safe-execution.md`;
  - `cwd` expansion in delegate mode: `issues/safe-execution.md` (its 2026-10-16 note);
  - the cross-user `rcac://context` cache: `issues/context-cache-cross-user.md`, with
    `issues/agents-d-instructions.md`;
  - the `storage_paths()` resource `TypeError`: `issues/storage-paths-resource-typeerror.md`;
  - the `AUTH_MODES` annotation typo and OIDC behaviour: `issues/auth-modes-annotation-typo.md`,
    absorbed into `issues/stack-upgrade.md`;
  - the absence check's leftover classification: `issues/absence-check-leftover-classification.md`;
  - CI, and the mutation runner as an opt-in job: `issues/ci-workflow.md`.

  Two recorded limitations need no seed, with the reason in `AGENTS.md` § Testing: the
  issuer/audience swap cannot be told apart while `ISSUER == AUDIENCE` (not a defect), and file I/O
  is outside the unit guard (covered by the stated-reason check and `transfer-local-fallback`).
- **Amendment (build):** P1's two isolation tests and `test_cli_drives_are_sandboxed` now assert
  with `'\n'.join(violations)`, as P2–P7 do, so a longer violation list cannot push a mutation's
  kill reason into pytest's elided middle.
- [x] **Remediation, review cycle 1 (F4):** the class is every FastMCP / mcp / httpx touchpoint in
      `tests/` outside the harness. Sites found: `test_tokens.py`'s direct `JWTVerifier` import
      (now re-exported by `tests/harness.py`), five `server.add_middleware(Rendezvous…)` calls in
      `test_isolation.py` and `test_no_executor.py` (now the builders' `*extra` middleware, same
      order), and `test_registry.py` / `test_instructions.py` reading `get_tools()` and
      `instructions` off a FastMCP server (left unchanged as develop's modules; added to the
      internals-bound list as item 6). Durable gate: `test_hygiene.py`'s `stack_import_violations`
      and `test_only_the_harness_imports_the_stack` (P8's ids), which fail on any such import
      outside the harness, so the manual cites a test, not this spec. `AGENTS.md` § Testing's
      "single touchpoint" sentence now says what the test enforces, and its module notes carry
      F1–F3.
- **Amendment (remediation):** the 2026-10-16 hand-off notes this cycle wrote are corrected in
  place, not appended to, since they have not landed: `issues/stack-upgrade.md` (imports, not
  all use, are confined to the harness; the two older modules named) and `issues/ci-workflow.md`
  (no hard-coded case count; 60–90 s). P1's checklist line calling the harness "the single
  FastMCP/mcp touchpoint" is a build record and stays; the module docstring now says "the only test
  module that imports" them. The case count is now 49 (P1 +2, P4 +1, P6 +3).
- [x] **Remediation, review cycle 2 (N2):** the class is every way a test module can name a stack
      module to an importer by a string the check can read. `stack_import_violations` now reads
      `importlib.import_module` / `__import__` calls reached by any dotted path ending in the
      importer's name (a bare `import_module` after `from importlib import import_module`,
      `il.import_module`, `builtins.__import__`) or by a `from importlib import … as` alias, with
      the name positional or `name=`, and a relative name resolved against its literal package.
      Its docstring says plainly what it cannot read: a non-literal name, an importer rebound by
      assignment or reached through `getattr` / a container / `sys.modules`, other loaders
      (`importlib.util`, `runpy`, `pkgutil`), and `exec` / `eval` source. Six new negative
      controls (`from-import-module`, `aliased-import-module`, `aliased-importlib`, `name-keyword`,
      `relative-with-package`, `builtins-dunder-import`), each returning `[]` from the old check,
      plus a clean `import_module("rcac_mcp.docs")` and `import_module(name)`. The reviewer's plant
      in a copy of `test_cli.py` passed before and fails after (`test_cli.py:126: imports
      fastmcp`). `AGENTS.md` § Testing's hygiene note says what the check reads. Suite ids 272 →
      296; mutation cases 49 → 53 (P6 +4), the full list run by this gate in the tree and the clone.
- **Verify:** `sh spec/restore-test-coverage/verify/gate.sh P8`. It covers everything P1–P7 check
  (all ids, all controls, all planted cases, both direct drives), plus the profile's full
  verify, the § Testing and seed checks, and the ledger. It ends with a fresh `git clone`
  (`UV_PROJECT=$PWD`, `VIRTUAL_ENV` unset, own `uv sync --locked`, import origin under the clone,
  `src/` equal to the base) in which the suite passes the JUnit id check and the mutation runner
  kills every case again.
- **Touches:** `AGENTS.md`, `issues/stack-upgrade.md`, `issues/safe-execution.md`,
  `issues/ci-workflow.md`, plus any deferral pair the build recorded.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[test]` commit; stop and report.
