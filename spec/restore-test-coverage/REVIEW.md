# REVIEW — Rebuild test coverage over the coupled core

> Adversarial QA by `code-review`, run in an isolated context (a fresh subagent, xhigh effort). The
> correctness pass graded the branch diff against [`GOAL.md`](GOAL.md) and the repo's `AGENTS.md`
> § Invariants **only**; it did not see `PLAN.md`, `TECH.md`, `verify/` or commit bodies. Every
> finding cites an **executed** command. For a `kind: test` cycle the reviewer also planted each
> contract's violation itself and read the suite's verdict.

- **Reviewed commit:** f420d019ce0264b36ae4802985bb969c76d979f5  ·  **Base:** develop (ca4911e)  ·  **Date:** 2026-10-16
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md`

## Verification run

- `uv sync --locked` → no changes. Profile verify `uv lock --check && uv run pytest -q &&
  bin/sandbox.sh uv run rcac-mcp --help` → 254 passed in 8.8 s; `--help` exit 0.
- `uv run python tests/mutants.py --self-check <all 43 ids>` → exit 0 in 1:13; 43/43 killed for
  their stated reason; the surviving-mutant and wrong-origin controls behaved.
- `git diff --stat origin/develop...HEAD -- src/ bin/ pyproject.toml uv.lock` → empty (no `src/`
  change).
- Markers: `-m 'not unit and not integration'` selects 0 of 254. The 39 test ids on develop
  (collected from `git archive origin/develop`) are all present and pass; `test_registry`,
  `test_instructions` and `test_cli` unchanged. The integration subset run under a throwaway `HOME`
  wrote nothing to it. CLI drives go through `bin/sandbox.sh` (checked statically).
- Reviewer's own plants, through `mutants.apply` and `run_child` on copies: `get_executor` falling
  back to the last executor (5 red), the middleware dropping `call_next` (red), `-u <identity>`
  instead of the mapped user (red), the map check removed (red, on "not authorized"), CLI unset
  secret defaulted / auth floor 33 / CLI floor 33 (all red), signer issuer changed and algorithm
  hard-coded (red). Three plants survived (F1–F3).
- Cleanliness at hand-back: `git status --porcelain` empty, HEAD unmoved, ignored set unchanged, no
  `mutant-*` / `probe-*` / sandbox directories left in `$TMPDIR`, real `HOME` untouched.

## Requirement → evidence matrix

| R-ID | Tests | Verified how | Status |
|------|-------|--------------|--------|
| R1 | `test_isolation` (delegate, shared, rendezvous control) | runner: module-global, executor-cached killed; plant: last-executor fallback → red | ✅ (see F2) |
| R2 | `test_no_executor`: bare server × 23 tools; after / in-flight; tokenless delegate | 6 runner cases incl. transfer-local-fallback; last-executor fallback → red | ✅ |
| R3 | `test_tools` × 23 + coverage test | local and ssh self-built executor cases killed; `call_next` dropped → red | ✅ |
| R4 | precedence (5 rows), no identity (2 rows) | 5 runner cases; `-u <identity>` → red | ✅ |
| R5 | unmapped, no fall-through, `KeyError`, loader | 5 runner cases; map check removed → red | ⚠️ partial (F3) |
| R6 | `test_sudo_argv` × 3, shell captured at construction | 5 runner cases; `-u` identity → red | ✅ |
| R7 | 13 ladder rows | 5 runner cases | ⚠️ partial (F1) |
| R8 | unit floors + sandboxed CLI floors | 3 runner cases; unset/33/33 plants → red | ✅ |
| R9 | minted tokens accepted; 5 mismatch rows → 401 | 7 runner cases; signer plants → red; ISSUER == AUDIENCE swap recorded as undetectable | ✅ |
| R10 | 3 backends, `Connection` faked | 3 runner renames | ✅ |
| R11 | suite-wide | markers, ids, HOME, sandbox checks above; `test_exec_mode` drives `MCPServerApp.main` in-process under the unit guard, which blanks the same environment | ✅ |
| R12 | `tests/mutants.py` | 43/43 killed for their reason; no plant in `src/` | ✅ (gaps F1–F3 add cases) |

Unmapped changes: a new Part III in `ROADMAP.md` and the seed
`issues/absence-check-leftover-classification.md` (deferral records the four-homes table allows);
dated hand-off notes in `ci-workflow`, `safe-execution` and `stack-upgrade`, checked accurate (43
cases, ~73 s; the `cwd`-expansion claim matches `delegate.py`). None blocks.

## Findings

### [MEDIUM/CONFIRMED] F1 — R7 never pins rung 1 for `-e ssh`
- **Where:** `tests/test_exec_mode.py:60-78` (`LADDER_CASES`): rows cover explicit `-e local` and
  `-e delegate`, none explicit `-e ssh`.
- **Failure scenario:** a refactor keyed on the unused `DEFAULT_EXEC_MODE = 'ssh'`
  (`__init__.py:49`), e.g. `if self.exec_mode and self.exec_mode != 'ssh':` at `__init__.py:207`,
  makes `-t http -e ssh` resolve to `local` and `-t http -a jwt -e ssh` to `delegate`, widening
  `local` (§4 forbids), and the suite stays green.
- **Evidence:** that plant → `test_exec_mode.py` 18 passed; `_resolve_exec_mode()` under
  `bin/sandbox.sh` on the mutated copy returned `local` where the original returns `ssh` and fails
  closed.
- **Routing:** as a class — every rung-1 value (`-e local`, `-e ssh`, `-e delegate`) has a row, each
  asserting mode, status and reason; add the plant as a mutation case.

### [MEDIUM/CONFIRMED] F2 — §1's "set per tool call" is not pinned for `SharedExecutorMiddleware`
- **Where:** no test calls one shared server twice (`test_tools`, `test_isolation`,
  `test_no_executor`).
- **Failure scenario:** setting the executor only on the first call in `on_call_tool`
  (`middleware.py:53`) passes the suite; a second call on the same server then returns
  `No executor configured`. It fails closed, but it breaks the §1 rule the GOAL's Problem names.
- **Evidence:** that plant → the three modules, 69 passed; a direct probe of two sequential calls:
  first `one|echo first`, second `No executor configured`.
- **Routing:** as a class — every executor middleware is shown to set the executor on every call
  (sequential calls on one server, shared and delegate); add the plant as a mutation case.

### [MEDIUM/CONFIRMED] F3 — The R5 line-number check can't tell lines from entries
- **Where:** `tests/test_identity.py:134-139`: the malformed line 3 has only valid entries above
  it.
- **Failure scenario:** a loader that counts entries, or drops comments and blanks before numbering,
  still reports "line 3".
- **Evidence:** `{len(user_map) + 1}` in place of `{line_num}` → `test_identity.py` 16 passed.
- **Routing:** as a class — the fixture puts a comment and a blank line before the malformed line, so
  line number and entry count differ; add the plant as a mutation case.

### [MEDIUM/CONFIRMED] F4 — `AGENTS.md` overstates the harness as the single FastMCP touchpoint
- **Where:** `AGENTS.md:249` versus `tests/test_tokens.py:35`, which imports
  `fastmcp.server.auth.providers.jwt.JWTVerifier` directly; the internals-bound list half-covers it.
- **Failure scenario:** `stack-upgrade` trusts the manual, rewrites only `tests/harness.py`, and
  `test_tokens.py` breaks at import when the path moves.
- **Evidence:** `grep -rn 'from fastmcp\|import fastmcp\|from mcp\|import httpx' tests/`.
- **Routing:** as a class — every direct FastMCP / mcp / httpx import in `tests/` either goes through
  the harness or is named in the manual's internals-bound list, and the "single touchpoint"
  sentence matches what the grep shows.

## Human-gate triggers

- None. No finding touches a path on § Invariants' high-blast-radius list; all four are test or
  manual gaps, not violations by the code.

## Review cycle 2 — changes-requested (2026-10-16)

- **Reviewed commit:** 8d89a7bf5b1ba3c07205d6c7e31e826541636601 · **Mode:** scoped by the foreman to
  verifying the remediation of F1–F4, plus a no-regression check (fresh blind subagent, xhigh).
- **Verification run:** profile verify → `uv lock --check` ok, 272 passed, sandboxed `--help` exit 0;
  `-m 'not unit and not integration'` selects 0 of 272; R#/P# grep (excluding `noqa:` lines) empty;
  no `src/` diff; test ids 254 → 272 and mutation cases 43 → 49 with none removed (one `why`
  tightened from `'line 3'` to `'does not name line 5'` to match the stricter assertion);
  `tests/mutants.py --self-check` over all cases → exit 0, 49/49 killed for their stated reason,
  both runner controls behaved. Hand-back clean (HEAD unmoved, ignored set unchanged, plants on
  copies only).
- **F2 — closed.** The original shared set-once plant now fails
  `test_sequential_shared_calls_each_get_the_executor` ("'echo second' ran 0 times … No executor
  configured"); siblings caught too: set once per tool name (same test), delegate set once per
  identity (`test_sequential_delegate_calls_each_get_their_executor`, "'echo alice-2' ran 0 times").
- **F3 — closed.** `{len(user_map) + 1}` → "does not name line 5 … at line 3"; three other numberings
  (non-blank only, non-comment only, from zero) → "line 4", all red.
- **F4 — closed** (with N2 below). The stack-import grep finds imports only in `tests/harness.py`; the
  standing test fails on the original shape and on a planted `import httpx`, naming file and line;
  `AGENTS.md` § Testing's sentence and internals-bound list (item 6) match the code.
- **F1 — partly closed.** The original plant now fails `explicit-ssh-over-auth-none` and
  `explicit-ssh-over-auth` ("mode: resolved local/delegate, expected ssh"), and the three
  ignore-`-e` mutation cases are killed. Siblings in the same class survive: N1.

### [MEDIUM/CONFIRMED] N1 — Rung 1 is still not separated from every later rung
- **Where:** `tests/test_exec_mode.py:62-73` (`LADDER_CASES`).
- **Failure scenario:** two plants at `src/rcac_mcp/__init__.py:207`, each leaving all 21
  `test_exec_mode.py` tests green: (a) `if self.exec_mode and not (self.exec_mode == 'delegate' and
  self.auth == 'none'):` makes `-t http -e delegate` resolve to `local` — an unauthenticated local
  shell, the §4 posture the ladder exists to prevent — because no `-e delegate` row runs with auth
  `none`; (b) `if self.exec_mode and not os.environ.get('RCAC_SSH_HOST'):` makes `-e local` and
  `-a jwt -e delegate` resolve to `ssh` when `RCAC_SSH_HOST` is set, because the rung-1-over-host
  rows use only `--ssh-host`.
- **Evidence:** both confirmed with `_resolve_exec_mode()` on the original and the mutated copy
  under `bin/sandbox.sh`.
- **Routing (orchestrator):** as the full class, not another instance — explicit `-e` must win over
  every later-rung trigger, so the ladder rows cover the cross-product of each `-e` value
  (`local`, `ssh`, `delegate`) with each later trigger (`stdio` transport, `--ssh-host`,
  `RCAC_SSH_HOST`, auth `none`, auth `jwt`), each asserting mode, middleware, status and reason
  where the mode fails closed; both plants become mutation cases with stated kill reasons.

### [LOW/CONFIRMED] N2 — The stack-import check misses `import_module("fastmcp")`
- **Where:** `tests/test_hygiene.py:360` (`_dotted` returns `import_module`).
- **Failure scenario:** a test that imports the stack dynamically
  (`from importlib import import_module; import_module("fastmcp")`) passes the check, though the
  check's docstring says this form is read. Nothing in the suite uses it today.
- **Evidence:** planted in a copy of `test_cli.py` → the check passed.
- **Routing:** the check reads the string argument of `importlib.import_module` / `__import__`
  calls (and says what it can't read), shown red on the planted form.

### Human-gate triggers (cycle 2)

- None. Both findings are test gaps; the code under test is unchanged and no high-blast-radius path
  is edited.

## Review cycle 3 — approved (2026-10-16)

- **Reviewed commit:** f8a2655 · **Mode:** scoped by the foreman to verifying the remediation of N1
  and N2, plus a no-regression check (fresh blind subagent, xhigh). The last cycle the bounded loop
  allows.
- **Verification run:** profile verify → `uv lock --check` ok, 296 passed, sandboxed `--help` exit 0;
  `-m 'not unit and not integration'` deselects all 296; R#/P# grep (excluding `noqa:` lines) and
  the `src/` diff both empty; all 272 ids from aa886b1 present; `tests/mutants.py --self-check` over
  all 53 cases → exit 0 in 88 s, every case killed for its stated reason, both runner controls
  behaved, the `mutants.py` delta additions only. Hand-back clean (`.pytest_cache` restored
  byte-for-byte; runs used `PYTHONDONTWRITEBYTECODE=1`).
- **N1 — fixed.** Inputs the ladder reads, enumerated from `_resolve_exec_mode`
  (`src/rcac_mcp/__init__.py:205-219`): `exec_mode`, `transport` (stdio/sse/http), `ssh_host`
  (truthiness), `RCAC_SSH_HOST`, `auth` (none/jwt/oidc); `run()` picks the middleware from the
  mode; `-H`, `-p`, `--sub`, `--lifetime` are not read, and `--generate-token` returns before the
  ladder. `EXPLICIT_CASES` covers all 18 rows, and `test_explicit_mode_decides_alone[mode]` drives
  the full 36-way product per value. Re-planted (a) and (b) → red ("resolved local, expected
  delegate"; "resolved ssh" with a connection to the env host). Nine new sibling plants (sse, flag
  host only, oidc, two-trigger combinations, stdio + jwt, ssh yielding to sse + none, Shared
  middleware for delegate under auth none, env host over flag host) → all red for the right
  reason; five of them only by the cross-product test. Out-of-class control: a rung 1 reading `-H`
  survives, as expected — a new ladder input is a §4 change made in the same commit as its test.
- **N2 — fixed.** In a copy of `tests/`, five dynamic-import shapes (positional
  `import_module("fastmcp")`, `importlib.import_module(name=…)`, an aliased nested loader,
  `__import__(name="httpx")`, `import_module(package="fastmcp", name=".client")`) are red at HEAD
  and pass at aa886b1. The documented limit (a non-literal name) holds.
- **Observation, not a blocking finding (orchestrator):** `pytest.importorskip("fastmcp")` is
  neither read by the stack-import check nor named among its documented limits
  (`tests/test_hygiene.py:230-233`). The check is defence-in-depth guarding the internals-bound
  list; it breaks no R-ID's stated check and no reachable behaviour, and nothing in the suite uses
  the form. Seeded as a dated note on [`stack-upgrade`](../../issues/stack-upgrade.md), the cycle
  that next moves the harness, committed as `38f2e19` before this verdict; the approval is pinned
  to that commit.
- **Convergence.** Three cycles: four MEDIUM → one MEDIUM + one LOW, both in classes the first
  remediation had only partly covered → approved with one observation. Routing N1 as the full
  cross-product ended the sibling chase; the nine new siblings this cycle tried are all caught.

### Human-gate triggers (cycle 3)

- None in any cycle.
