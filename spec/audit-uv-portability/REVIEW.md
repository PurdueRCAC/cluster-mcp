# REVIEW — The dependency audit and the suite work under every supported uv

> Adversarial QA by `code-review`, run in an isolated/clean context (a subagent; where the runtime
> has none, `code-review`'s sequential fallback). The correctness pass grades the branch diff against
> [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants **only** — it does not see
> `PLAN.md`/`TECH.md` (avoids grading-its-own-homework / plan-sycophancy). Every finding cites an
> **executed** command, not an assertion.

- **Reviewed commit:** 219bf2379aa9c076514400e94f5a5e62bbde9e5a  ·  **Base:** develop (`2b006fa`)  ·  **Date:** 2026-10-17
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md` (escalate to human on non-convergence)

## Verification run

Commands actually executed by the blind reviewer and their outcomes:

- The profile's `verify` with uv 0.12.17 first on `PATH` → exit 0: `445 passed` in each protocol
  era, `bin/sandbox.sh uv run rcac-mcp --help` printed its usage. Also green under uv 0.12.24.
- The profile's `verify` under uv 0.13.1 → exit 0: `445 passed` in each era, usage printed.
- `UV_OFFLINE=1 bin/sandbox.sh sh -c 'uv run python "$CLUSTER_MCP_REPO/bin/audit_lock.py"'` under
  0.12.17 and 0.13.1 → rc 2, `audit_lock: advisory source unreachable: the audit ran offline (uv
  audit exited 2)`; unchanged after warming the cache with a real online audit.
- The wrapper under the sandbox with every proxy at a hostile endpoint (refused, DNS failure,
  accept-then-close, TLS garbage, proxy 503, a hang to 20 s), on both releases → rc 2, unreachable.
- Fake `UV` executables: exit 5 with unknown text → rc 2 ("could not run"); `kill -9` → rc 2; exit 0
  without the summary → rc 3; exit 1 → rc 1; a missing binary → rc 1.
- uv 0.12.16 against `sync`, `sync --locked`, `sync --frozen`, `run --frozen`, `run --no-sync`,
  `lock`, `lock --check`, from a subdirectory, via `UV_PROJECT` and via `--project` → rc 2 each,
  `Required uv version >=0.12.17 does not match the running version 0.12.16`.
- Canary probe: offline → 0 connections for `UV_OFFLINE` values `1`, `TRUE`, `y`, empty, `garbage`,
  `' 0'`; online → 91–93 connections. The wrapper's reading of the variable matches uv's own on both
  releases (uv rejects the empty, padded and garbage values the wrapper reads as offline).
- Mutants, in a scratch copy: dropping `--offline` from `command()` → 11 failed under both releases
  (the canary row among them); passing `offline=False` from `main()` → `33 passed` under 0.13.1,
  `1 failed` under 0.12.17 (finding 1).

The foreman separately re-ran every phase gate green on `219bf23` (P3: `445 passed` per era under
0.12.17 and 0.13.1, usage printed twice).

## Requirement → evidence matrix

No R-ID is an artifact deliverable; the blind reviewer graded all eight.

| R-ID | Implemented by (file/commit) | Verified how | Status |
|------|------------------------------|--------------|--------|
| R1 | `bin/audit_lock.py` (`8c84e5a`) | offline wrapper run under 0.12.17 and 0.13.1, cold and warm cache | ✅ |
| R2 | `bin/audit_lock.py` (`8c84e5a`) | six hostile-proxy cases on both releases | ✅ |
| R3 | `bin/audit_lock.py` (`8c84e5a`) | five fake-`UV` exits | ✅ |
| R4 | whole branch | full `verify` under 0.12.17 (and 0.12.24) | ✅ |
| R5 | whole branch | full `verify` under 0.13.1 (latest on PyPI) | ✅ |
| R6 | `pyproject.toml` (`3835a22`) | ten refusal paths under 0.12.16 | ✅ |
| R7 | `tests/test_audit.py` (`8c84e5a`) | suite green across three releases; messages pinned, uv text only as planted input | ❌ finding 1 |
| R8 | `bin/audit_lock.py`, `tests/test_audit.py` (`8c84e5a`) | canary probe across six values; `--offline` mutant caught on both releases | ✅ |

Unmapped changes (possible scope creep): none. Three changes go past the bare fix, each serving an
R-ID: `UV_HTTP_RETRIES` joins the audit's environment allowlist (the canary rows, R8); the wrapper
runs the launching uv through `UV` (R4, R5, R8; `uv run` sets it under both releases); an offline
audit that also prints advisories now exits 2, not 1 (R1).

## Findings

### [LOW/CONFIRMED] A wiring regression in `main()` passes the suite under the current uv

- **Where:** `tests/test_audit.py:180` (`test_main_runs_the_command_and_env_it_derives`), against
  `bin/audit_lock.py:126-127`.
- **Failure scenario:** `main()` stops handing its offline decision to `audit_violations`
  (`offline=False`). Offline under uv 0.12 is then reported as "the audit could not run", the
  GOAL's own defect, yet the suite passes under 0.13.1, because the unit row for `main()` pins only
  the exit status and the integration row's uv-0.13 output still matches the `requires network
  access` marker. Only a run under the 0.12.17 floor catches it.
- **Evidence:** the `offline=False` mutant in a scratch copy: `uv run pytest -q tests/test_audit.py`
  → `33 passed` (0.13.1), `1 failed` (0.12.17).
- **Touches invariant / requirement:** R7 (the tests pin the audit's own messages); the defect class
  of R1 and R4.
- **Routed as its class:** every value `main()` derives on its way to the verdict (argv, the child
  environment, the offline decision, the lock text, the combined output) and the reasons it prints
  must be pinned on the wrapper's own `audit_lock:` message and exit status, so that a wiring
  regression anywhere in `main()` fails under each supported uv on its own, never only under the
  floor.

## Human-gate triggers

- None. The finding is in `tests/test_audit.py` and `bin/audit_lock.py`, neither on § Invariants'
  high-blast-radius list, and the diff touches no *[human gate]* section.

## Blindness note

The reviewer disclosed that one repo-wide `grep` meant to exclude `spec/` did not (BSD grep has no
`\|`), and printed about a dozen single lines of `PLAN.md` and `TECH.md`, mostly symbol names already
in the diff. Finding 1 and both mutants predate that grep; no `spec/` file beyond `GOAL.md` was
opened. The foreman judges the pass's independence intact.

## Optional completeness sub-pass (separate reviewer; may see TECH.md)

- Not run.

## Review cycle 2 — changes-requested (2026-10-17)

- **Reviewed commit:** 6d08cb76cdbb60bee00f1316b745e8cd7e8307ea · **Mode:** a fresh blind pass over the
  full spec-excluded diff (the default), not scoped to cycle 1's finding.
- **Cycle 1's F1 is closed.** The reviewer's own 14-mutant matrix, run under uv 0.12.17 and 0.13.1
  separately, killed every `main()` wiring mutant (`main-drops-offline`, `never-offline`,
  `no-offline-flag`, `classify-by-text` among them) with the same failure counts under each uv; none
  depends on which uv runs. The remediation's own 18-mutant table (`6d08cb7`'s body) agrees.

### Verification run

- Full `verify` with uv 0.12.17 first on `PATH` (`UV` resolved to the 0.12.17 binary) → `uv lock
  --check`, `450 passed` per era, sandboxed `--help`; exit 0. The same under 0.13.1; exit 0.
- uv 0.12.16 refuses `sync --locked`, `run`, `lock --check` and the sandboxed `uv run`, naming
  0.12.17; exit 2.
- A 24-value `UV_OFFLINE` matrix per uv through `bin/sandbox.sh` and the canary: every value uv reads
  as true, plus empty, `garbage`, `' 0'` and `' 1'` → exit 2, the offline message, 0 connections.
- Nine unreachable-source modes per uv (dead port, DNS, accept-close, hang, 403, 502, garbage,
  CONNECT-then-reset, CONNECT-then-non-TLS) → exit 2, "advisory source unreachable"; also with
  default retries.
- A fake `UV` exiting 7 → exit 2, "the audit could not run (uv audit exited 7)".
- Negative control: `origin/develop`'s `tests/test_audit.py` under 0.12.17 → `FAILED
  test_audit_fails_closed_offline`; under 0.13.1 it passes. The GOAL's defect, reproduced.
- Checked and dropped by the reviewer: `--no-config` skipping `required-version` (the documented
  `uv run python bin/audit_lock.py` enforces it); `uvx --from <tree>` under 0.12.16; the OSV query
  served from cache (never); AGENTS.md claims (all match); spec ids in source (none); markers (all
  present).

### Requirement → evidence matrix

| R-ID | Status | Verified how (cycle 2) |
|------|--------|------------------------|
| R1 | ✅ | offline run under both releases; the 24-value matrix |
| R2 | ✅ | nine unreachable modes per release |
| R3 | ✅ | fake `UV` exit 7 |
| R4 | ✅ | full `verify` under 0.12.17 |
| R5 | ✅ | full `verify` under 0.13.1 |
| R6 | ✅ | 0.12.16 refusals |
| R7 | ✅ | tests assert only exit status and `audit_lock:` lines |
| R8 | ❌ finding 1 | canary 0 offline / ~90 online; but see finding 1 |

Unmapped changes: none.

### [LOW/CONFIRMED] The suite does not pin uv's one-letter boolean values for `UV_OFFLINE`

- **Where:** `tests/test_audit.py:145,149` (the offline and online value lists), against
  `bin/audit_lock.py:51` (`FALSE_VALUES`, which is correct today).
- **Failure scenario:** a regression that reads `t` or `y` as false (`'t','y'` added to
  `FALSE_VALUES`) makes `UV_OFFLINE=t` audit online and send a request, breaking R8, and the whole
  `tests/test_audit.py` still passes (`38 passed` under 0.12.17 and under 0.13.1). The mirror
  regression (`f`/`n` dropped from `FALSE_VALUES`) also survives; it fails safe, refusing an online
  audit the user asked for.
- **Evidence:** mutant `truthy-t-y-online` in a scratch `git archive` copy → `38 passed` under each
  uv; driven through `bin/sandbox.sh` with the canary, `UV_OFFLINE=t` → exit 2 but `conns=1`.
  `drop-false-f-n` → `38 passed` under each uv.
- **Why CONFIRMED, not a coverage observation:** the surviving mutant breaks a reachable behaviour
  R8 states (rubric → *Coverage observation*); `FALSE_VALUES` is the primary offline decision, not
  defence in depth.
- **Routed as its class:** the wrapper's reading of `UV_OFFLINE` must agree with uv's for every
  value of uv's boolean vocabulary, in every case form, and for the values outside it, and the suite
  must pin that agreement so a change to the table fails under each supported uv on its own. With it,
  a mutant sweep over every decision in `bin/audit_lock.py`, so the next pass meets no sibling.

### Human-gate triggers

- None (neither file is on § Invariants' high-blast-radius list).

### Blindness

- The reviewer read nothing outside its inputs (GOAL.md and the rubric only).

## Review cycle 3 — changes-requested (2026-10-17)

- **Reviewed commit:** a1b224c87f8d145768828bbc3a3c4bbe7722041a · **Mode:** a fresh blind pass over the
  full spec-excluded diff.
- **Cycle 2's F1 is closed:** the vocabulary rows and the integration agreement test kill both of
  its mutants under each uv; the reviewer's 69 mutants across every function were killed under 0.12.17
  and 0.13.1 independently, except the three below.
- **The bound is reached.** This is review cycle 3 of ≤3 and it did not converge (cycle 1: one LOW;
  cycle 2: one LOW; cycle 3: two MEDIUM). Per `code-review` Step 6 and the foreman's gates, the cycle
  STOPs here and goes to Geoffrey; nothing is remediated until he rules.

### Verification run

- Full `verify` with uv 0.12.17 first on `PATH` (`UV` confirmed as that binary) → `uv lock --check`,
  `550 passed` per era, sandboxed `--help`; exit 0. The same under 0.13.1; exit 0.
- `UV_OFFLINE` = `1`, `TRUE`, `yEs` under both releases → exit 2, "advisory source unreachable: the
  audit ran offline", 0 canary connections. Six unreachable shapes per release, retries 0 and
  default → exit 2, unreachable. A real online audit under both → exit 0, 94 packages.
- uv 0.12.16, 0.12.0, 0.10.0, 0.8.0, 0.6.0, 0.5.31 and 0.5.14 → exit 2 naming the required version
  for `sync --locked`, `run`, `lock`, `lock --check`; 0.5.13 and older → see finding 2.

### Requirement → evidence matrix

| R-ID | Status | Verified how (cycle 3) |
|------|--------|------------------------|
| R1 | ✅ behaviour; guard weak (finding 1) | offline runs under both releases |
| R2 | ✅ | six unreachable shapes, both releases |
| R3 | ✅ | cannot-run, killed, exit-5 rows; their mutants killed |
| R4 | ✅ | full `verify` under 0.12.17 |
| R5 | ✅ | full `verify` under 0.13.1 |
| R6 | ❌ partial (finding 2) | refusals from 0.5.14 to 0.12.16; none at 0.5.13 and older |
| R7 | ❌ finding 1 | 66 of 69 mutants killed per release |
| R8 | ✅ | 0 offline / 90–93 online connections; drop-the-flag mutants killed per release |

Unmapped changes: none (new rows pinning pre-existing verdicts are tests only).

### [MEDIUM/CONFIRMED] `main()` decides "offline" a second time, and the suite pins neither decision's agreement

- **Where:** `bin/audit_lock.py:126-127` (`offline=offline_requested(environ)`, separate from
  `command(environ)`), `tests/test_audit.py:240-254`.
- **Failure scenario:** a `main()` that reaches its verdict's offline decision by any other parse
  than `command()`'s passes the whole suite under both releases, because `main()`'s rows use only
  unset, `'1'` and `'yes'`, and the integration rows only `'1'` or unset. With
  `offline=environ.get('UV_OFFLINE','').lower() in ('1','yes')`, `UV_OFFLINE=on` under 0.12.17 →
  `audit_lock: the audit could not run (uv audit exited 2)`: the GOAL's R1 defect, back. With
  `offline='UV_OFFLINE' in environ`, `UV_OFFLINE=0` turns a clean online audit (94 packages) into
  "advisory source unreachable: the audit ran offline", exit 2, under both releases. It also makes
  `AGENTS.md:344` ("a wiring fault anywhere in `main()` fails under any uv") false.
- **Evidence:** the three mutants in a `git archive` copy → `138 passed` under 0.12.17 and under
  0.13.1; the drives above through `bin/sandbox.sh`.
- **Touches:** R1, R7.

### [MEDIUM/CONFIRMED] uv 0.5.13 and older run the project despite the floor

- **Where:** `pyproject.toml:46-48` (the comment and `required-version`), `AGENTS.md:111-112`.
- **Failure scenario:** R6 and both texts say a uv older than 0.12.17 refuses. Releases 0.5.14
  through 0.12.16 do; 0.4.30, 0.5.0, 0.5.10 and 0.5.13 print ``unknown field `required-version` ``
  and then sync and run (`uv run --locked python -c 'print("RAN")'` → `RAN`, exit 0; `sync --locked`
  → exit 0). No uv-native mechanism reaches those releases.
- **Touches:** R6 (as worded, it reaches every older release), and the two doc claims.

### Human-gate triggers

- None on the high-blast-radius list. **Escalated** on the review bound (Step 6), not on a path.

## Review cycle 4 — approved (2026-10-18)

- **Reviewed commit:** 4fe1030753cbf792eeea6b7d917eba86e200f74d · **Mode:** scoped to verifying cycle 3's
  two findings and anything their fixes touched.
- **Why a fourth cycle:** Geoffrey's ruling at the review-bound escalation (2026-10-18): fix both
  findings (F1 structurally, F2 through the GOAL clarification at `81c303d`), then one review scoped
  to them, as a named exception to the ≤3 bound.

### Verification run

- **F1 — fixed.** `main()` calls `offline_requested(environ)` once; `command(launcher, offline)` and
  `audit_violations(…, offline=offline)` take that value, and no other runtime call exists. 23
  mutants on a `git archive` copy, each against all of `tests/test_audit.py` (234 tests), were
  killed under uv 0.12.17 alone and under 0.13.1 alone with identical counts: the three cycle-3
  mutants at the decision (38, 49, 50 failures); a second decision for the verdict only (38–107);
  a second decision for the argv only (38–107); the flag inverted, never or always added inside
  `command` (206, 99, 108); and six mutants of `offline_requested` itself, `.casefold()` included
  (3–87). The new agreement assertion fired on `UV_OFFLINE=0` for a verdict-only mutant.
- Real drives under `bin/sandbox.sh` with a counting proxy, both releases: `on`, `ON`, `1`, `yes`,
  empty, `garbage`, `' 0'` → exit 2, "the audit ran offline", 0 connections; `0`, `OFF`, `False`,
  unset → exit 2, online "advisory source unreachable", 91–93 connections; with no proxy, `0` and
  unset → exit 0, no known vulnerabilities in 94 packages.
- **F2 — fixed.** uv 0.4.30 and 0.5.13 warn ``unknown field `required-version` `` and run; 0.5.14,
  0.9.0 and 0.12.16 refuse `sync --locked`, `lock --check` and `run`, exit 2, naming 0.12.17.
  `pyproject.toml:46-50` and `AGENTS.md:111-114` state exactly that; a grep outside `spec/` finds
  no other floor claim.
- Full `verify` after `uv sync --locked`: `646 passed` in each era under 0.12.17 and under 0.13.1,
  sandboxed `--help` printed usage; `-m integration` selected all three audit integration rows.
- No new finding. R1–R8 hold for the code the fixes touched.

### Requirement → evidence matrix (cycle 4)

| R-ID | Status | Verified how |
|------|--------|--------------|
| R1 | ✅ | offline drives under both releases |
| R2 | ✅ | unit rows; online drives through the counting proxy |
| R3 | ✅ | unit rows |
| R4 | ✅ | full `verify` under 0.12.17 |
| R5 | ✅ | full `verify` under 0.13.1 |
| R6 | ✅ | refusals from 0.5.14 to 0.12.16; texts scoped per the 2026-10-18 clarification |
| R7 | ✅ | unchanged pins of the wrapper's own text |
| R8 | ✅ | 0 offline connections; `--offline` mutants killed per release |

### Human-gate triggers

- None (neither file is on § Invariants' high-blast-radius list). The bound escalation was resolved
  by Geoffrey's ruling above.

### Blindness

- The reviewer read only `GOAL.md`, the rubric, `AGENTS.md` and the repo outside `spec/`.
