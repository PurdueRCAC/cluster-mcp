# REVIEW — Reading rcac://storage returns the user's storage paths

> Adversarial QA by `code-review`, run in an isolated/clean context (a subagent; where the runtime
> has none, `code-review`'s sequential fallback). The correctness pass grades the branch diff against
> [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants **only** — it does not see
> `PLAN.md`/`TECH.md` (avoids grading-its-own-homework / plan-sycophancy). Every finding cites an
> **executed** command, not an assertion.

- **Reviewed commit:** d38bf45  ·  **Base:** develop  ·  **Date:** 2026-10-28
- **Verdict:** changes-requested (cycles 1 and 2); approved at cycle 3 — see § Review cycle 3
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md` (escalate to human on non-convergence)
- **Mode:** debate variant (the diff touches the coupled core: `middleware.py`). Two blind
  reviewers, "ship" and "block", each in its own clone of `d38bf45`, ran at the same time; the
  foreman reconciled.

## Verification run

Both reviewers ran the profile's `verify` in their clones:

- `uv lock --check` → ok.
- `uv run pytest -q` → 2128 passed, 14 skipped (both reviewers). The 14 are the existing
  `bash 4.1 or later is not installed here` skips; CI ran them.
- `CLUSTER_MCP_TEST_ERA=modern uv run pytest -q` → 2128 passed, 14 skipped (both reviewers).
- `bin/sandbox.sh uv run rcac-mcp --help` → exit 0.
- `tests/mutants.py` over every case touching `middleware.py`, `resources.py` and `context.py` →
  27/27 killed (ship); the 21 cases touching the diff → all killed (block).
- Real-program drives under `bin/sandbox.sh`:
  - `rcac-mcp -e local` over stdio, with fake `findscratch`/`myquota`, both eras: the
    `rcac://storage` read returns the summary with the same paths as the `storage_paths` tool. On
    `develop` (`bd89d72`) the same drive fails with `'FunctionTool' object is not callable` (both
    reviewers).
  - `rcac-mcp -t http -a jwt -e delegate` on loopback with real JWTs, both eras (ship): an unmapped
    identity's storage read fails with the same `-32603` text as its tool call; a no-claim token,
    likewise; `rcac://context` answers both. No sudo was attempted.
- CI on the branch head (run 40791997808, `d38bf45`): success, 2142 passed per era, nothing
  skipped, lock audit clean.

## Requirement → evidence matrix

| R-ID | Implemented by (file/commit) | Verified how | Status |
|------|------------------------------|--------------|--------|
| R1 | `SharedExecutorMiddleware.on_read_resource` → `_install`; `resources.py` calls the undecorated `resolve_storage_paths()` | stdio drive in `local` mode, both eras, against a `develop` control; `test_storage_read_runs_on_the_shared_executor`, `test_storage_read_runs_the_local_executor` | ✅ |
| R2 | `AuthExecutorMiddleware.on_read_resource` → the shared `_install` | `test_storage_read_runs_as_the_mapped_user`, `test_concurrent_storage_reads_stay_isolated`, `test_sequential_storage_reads_each_get_their_executor`; `isolation-*` mutants killed; reviewer probes mixing reads and tool calls of two users (ship: 2-way; block: 9-way), both eras, each request ran only as its own user | ✅ |
| R3 | the same `_install`; `ToolErrorMiddleware.on_read_resource` → `ResourceError(str(exc))` | `test_storage_read_refused` (5 rows × 2 eras); the delegate JWT drive; refusal mutants killed | ✅ |
| R4 | `OPEN_RESOURCES` from the registry's `'executor': False` | `test_any_client_reads_the_context_in_delegate_mode` (4 × 2); `context-read-closed` killed; JWT drive; context read byte-identical to `develop` | ✅ |
| R5 | decorated `storage_paths` is a thin wrapper over `resolve_storage_paths()` | full surface dump (tools, schemas, resources, `storage_paths` result, executor calls) on `bd89d72` and `d38bf45`, both eras: identical (both reviewers) | ✅ |
| R6 | `tests/test_storage_resource.py`, `test_context.py` | 40 new or changed tests pass with 0 skipped, both eras; mutants above; F1 and F2 below are gaps in this coverage | ❌ (F1, F2) |
| R7 | `AGENTS.md` §1, §7, §8, repository map, diagram; `SECURITY.md` | greps for the removed defect text (none left); §1/§8 claims spot-checked against the code (modern era masks a read refusal without the boundary; the unknown-URI behaviour) | ✅ |

Unmapped changes (possible scope creep): none. The `_bounded` refactor, `_install`, the registry
key, the harness additions and the seeds' status changes all serve R1–R7.

## Findings

### [LOW/CONFIRMED] F1 — The read boundary's client-visible text is not pinned
- **Where:** `src/rcac_mcp/middleware.py:68-70` (`ToolErrorMiddleware`'s read side).
- **Failure scenario:** the boundary's docstring and `AGENTS.md` §1 promise a read refusal whose text
  is exactly `str(exc)`, with no type name and no traceback. The tool boundary's text is pinned
  exactly (`tests/test_protocol.py`); the read boundary's is checked only for containment. Two
  planted mutants, one appending `traceback.format_exc()` and one prefixing the type name, pass the
  suite, and a refused delegate client then sees
  `"User 'mallory' is not authorized. ...\nTraceback (most recent call last): ..."` or
  `"PermissionError: User 'mallory' is not authorized…"`, in both eras.
- **Evidence (block):** mutants `read-boundary-leaks-traceback` and `read-boundary-type-name`, planted
  in the reviewer's clone; `uv run pytest tests/test_storage_resource.py tests/test_context.py
  tests/test_protocol.py tests/test_identity.py tests/test_no_executor.py tests/test_isolation.py` →
  175 passed in both eras for each; a delegate probe showed the leaked texts above.
- **Touches:** R6 (the suite is the guard for what reads return), R7 (the §1 text it documents).

### [LOW/CONFIRMED] F2 — Nothing pins that the delegate read hook refuses every non-open URI
- **Where:** `src/rcac_mcp/middleware.py:234` (`AuthExecutorMiddleware.on_read_resource`).
- **Failure scenario:** `AGENTS.md` §1 and §8 say a refused caller reading any URI outside
  `OPEN_RESOURCES`, an unknown one included, gets the identity refusal. A planted mutant that resolves
  identity only for `rcac://storage` passes the suite; an unmapped caller reading `rcac://nope` then
  gets `-32602 Resource not found` instead of the refusal. Harmless today, but it is the difference
  between refusing by default and refusing one named resource, which matters for the next resource
  that runs commands.
- **Evidence (block):** mutant `read-hook-resolves-storage-only`, the same six test files → 175 passed
  in both eras; the URI probe showed the changed code.
- **Touches:** R6, R7 (the §1/§8 text).

### Dropped after refutation
- The open-resource exemption reached by another URI spelling: the middleware and the lookup see the
  same string; 10 (ship) and 14 (block) odd spellings, in both eras, found no divergence.
- Cross-user leakage, stale-executor reuse, templates, task-augmented reads, an `MCPError` rewritten
  by the read boundary: not reproduced.

### Observation (not a finding)
In `delegate` mode, an unmapped or no-claim caller reading an unknown URI now gets the refusal
(`-32603`) where `develop` returned `-32602 Resource not found`. Both reviewers reproduced it; it
follows from the hook running before lookup, as on the tool path, and §8 documents it.

### Out of Scope, seeded
During the build's final gate, `tests/test_ssh_exec.py::test_a_stalled_reconnect_is_abandoned_against_a_real_handshake`
failed once under full-suite load and passed alone and on re-run. Neither reviewer saw it. The cycle
touches no SSH code. Filed as [`issues/stalled-reconnect-test-timing.md`](../../issues/stalled-reconnect-test-timing.md)
with its `ROADMAP.md` entry.

## Routing

Both findings route as properties, with a mutant sweep:
- **The read boundary:** a refused read's client-visible text is exactly the refusal's `str(exc)`, in
  both eras: no type name and no traceback. Pin it as strictly as the tool boundary is pinned, and
  sweep every decision in `ToolErrorMiddleware`'s read side and `_bounded`.
- **The delegate read hook:** in `delegate` mode, every read outside `OPEN_RESOURCES` resolves
  identity, unknown URIs included; only the open set skips it. Pin both sides (an unknown URI is
  refused for an unmapped caller, and still `Resource not found` for a mapped one and in shared
  mode), and sweep every decision in `on_read_resource` and `_install`.

Each mutant runs in both protocol eras; equivalent mutants are recorded with the reason.

## Human-gate triggers

- Triggered: F1 and F2 are in `src/rcac_mcp/middleware.py`, on § Invariants' high-blast-radius list.
  Under decision 2026-10-16-cluster-mcp-autonomous the foreman is the judge at this gate. The foreman
  signed it off for remediation (2026-10-28). The gate holds until publish: a clean later cycle
  still records the sign-off here.

## Optional completeness sub-pass (separate reviewer; may see TECH.md)

- Not run.

## Review cycle 2 — changes-requested (2026-10-28)

- **Reviewed commit:** 3145974 · **Mode:** scoped to verifying F1 and F2's remediation (foreman's
  ruling: the remediation changed no `src/`, and `src/` at `d38bf45` was passed by both cycle-1
  reviewers), one blind reviewer planting its own mutants across every decision in `_bounded`,
  `ToolErrorMiddleware.on_read_resource`, `AuthExecutorMiddleware.on_read_resource` and `_install`,
  in both eras.
- **Verify (reviewer's clone):** `uv lock --check` ok; handshake era 2178 passed, 14 skipped
  (`bash 4.1 or later is not installed here`); modern era 2178 passed, 14 skipped; sandboxed
  `--help` exit 0. CI run 40806230666 on `3145974`: success.
- `git diff d38bf45 3145974 -- src/` is empty.

### F1 — resolved
Every behaviour-changing mutant of the read boundary is killed in both eras (35 planted across
`_bounded` and the read hook, among them the cycle-1 traceback and type-name plants); equivalents
recorded by the reviewer: chaining-only changes, one-line refusals, FastMCP 4.1.4 mapping every
`FastMCPError` on a read to -32603 with `str(e)`, and no disabled resources or template reads here.

### F2 — resolved for its instance; G1 remains

### [LOW/CONFIRMED] G1 — Default refusal is pinned at one unknown URI, not over the URI domain
- **Where:** `src/rcac_mcp/middleware.py:234`; the pin is `tests/test_storage_resource.py:64`
  (`UNKNOWN = 'rcac://nope'`).
- **Failure scenario:** two mutants that sort unknown URIs by shape keep `rcac://nope` refused and
  pass the suite: `a-prefix-open` (`not uri.startswith(tuple(OPEN_RESOURCES))`) and
  `a-rcac-scheme-only` (`uri.startswith('rcac://') and uri not in OPEN_RESOURCES`). Under them, an
  unmapped or no-claim delegate caller reading `rcac://context/x` or `rcac://contextual` (first), or
  `file:///nope` or `https://example.org/x` (second), gets `-32602 Resource not found` instead of the
  refusal, against §8's "every read of a URI not in `OPEN_RESOURCES`, an unknown one included". No
  command runs and no identity crosses.
- **Evidence:** each mutant passed the 210 tests of the six read and middleware files in both eras,
  and the full 2192-test run failed only the anchor checks (`test_mutation_anchor_applies`), a
  wrong-reason kill. An HTTP probe of a delegate server with `ghost` and no-claim tokens, both eras:
  on the clean code all of `rcac://context/`, `rcac://context/x`, `rcac://contextual`,
  `rcac://CONTEXT`, `file:///nope`, `https://example.org/x`, `rcac://storage/`, `RCAC://storage` are
  refused with -32603 and the exact reason.
- **Touches:** R6, R7 (§8).

### Routing
The property is F2's, over its whole domain: in `delegate` mode, for every URI not exactly in
`OPEN_RESOURCES`, a refused caller gets the refusal; the shapes that must be pinned include an
extension or prefix-sharer of an open URI, a case variant, a trailing slash, an executor URI's
variant, and another scheme. The open side stays pinned too: exactly the open URIs skip identity.
Sweep URI-shape mutants of the read hook's membership test (prefix, scheme, case-folding, suffix
stripping), each in both eras.

### Human-gate triggers
- Still triggered (`middleware.py`, as in cycle 1). The foreman, judge under decision
  2026-10-16-cluster-mcp-autonomous, signed it off for remediation (2026-10-28). Cycle 3 is the last
  under the bound.

## Review cycle 3 — approved (2026-10-29)

- **Reviewed commit:** 344a3a3 (finding), 8cbe6d0 (remediation, verified by the foreman) ·
  **Mode:** scoped to verifying G1's remediation, one blind reviewer planting its own URI-shape
  mutants of the read hook's membership test and of the `OPEN_RESOURCES` derivation, in both eras.
- **Verify (reviewer's clone, 344a3a3):** `uv lock --check` ok; handshake era 2201 passed, 14
  skipped (`bash 4.1 or later is not installed here`); modern era 2201 passed, 14 skipped; sandboxed
  `--help` exit 0. `git diff d38bf45 344a3a3 -- src/` is empty.

### F1, F2, G1 — resolved
Every shape in G1's 21-shape `NOT_OPEN` table is refused to an unmapped and a no-claim delegate
caller, and answered -32602 to the others, in both eras; G1's two mutants and its sweep are killed.
No regression.

### [LOW/CONFIRMED] L1 — The refusal is pinned over a finite table, not the URI neighbourhood
- **Where:** `src/rcac_mcp/middleware.py:234`; the pin is `tests/test_storage_resource.py`
  (`NOT_OPEN`, `test_unknown_uri_read_is_refused`).
- **Failure scenario:** ten URI normalisers planted in the membership test each change only shapes
  outside the table and pass the suite in both eras: CR/LF stripped, a trailing `?`/`#` stripped, a
  port dropped, userinfo dropped, a trailing dot stripped, tab and newline removed, a leading slash
  stripped, quotes and angle brackets stripped, a trailing NUL stripped, a `/.` segment dropped; so do
  their disjunction and an open set that also holds `rcac://context?`. Under any of them a refused
  delegate caller reading such a shape (`rcac://context?`, `rcac://context:80`, `rcac://u@context`,
  `<rcac://context>`, …) gets -32602 instead of the refusal. No command runs and no identity crosses;
  the shipped code is correct.
- **Touches:** R6, R7 (§8).

### Ruling at the bound
Cycle 3 is the last under the bound, so the foreman escalated. Geoffrey ruled (2026-10-29): a
scoped fix, verified by the foreman, then land, with no fourth review.

### Remediation (8cbe6d0) and foreman verification
- The pin is generated: `NEAR_OPEN` holds, for every served URI, every one-character insertion,
  deletion and substitution over printable ASCII and NUL, tab, newline, VT, FF, CR and DEL, plus
  wrappers, suffixes and userinfo, leaving out exactly the registry's open URIs: 5,712 shapes.
  `test_near_open_read_is_refused[no-claims|unmapped]` reads each verbatim in the selected era;
  `test_near_open_shapes_cover_every_served_uri` pins what the set holds. G1's table pins stay.
- `tests/mutants.py` gains the reviewer's twelve cases; the L1 checker
  (`remediation/L1-read-hook-refuses-near-open-uris.py`) sweeps 41 cases.
- `git diff d38bf45 8cbe6d0 -- src/` is empty.
- The foreman re-ran the L1 checker: 26 pinning tests pass in each era; 41/41 killed in each era.
- The foreman planted three normalisers of its own, none in the reviewer's set: whitespace removed
  and case folded, any trailing punctuation stripped, `%` removed. `test_near_open_read_is_refused`
  killed each in both eras, naming a shape it let through (`' rcac://context'`, `'rcac://context!'`,
  `'%rcac://context'`).
- Builder's gate: frozen `p2.sh` 597 passed per era, 74/74 killed; F1 12/12, F2 49/49, G1 41/41, L1
  41/41 per era; full verify 2216 passed, 14 skipped in each era; sandboxed `--help` exit 0.
- CI run 40860906079 on `8cbe6d0`: success on the first attempt, 2230 passed in each era.
- The generated rows cost about 5 s per era; accepted.

### Human-gate triggers
- Still triggered (`middleware.py`). The foreman, judge under decision
  2026-10-16-cluster-mcp-autonomous, signs it off for landing (2026-10-29), per Geoffrey's ruling.
