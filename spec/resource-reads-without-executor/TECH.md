---
slug: resource-reads-without-executor
title: Reading rcac://storage returns the user's storage paths
kind: fix
appetite: small
status: done
branch: fix/resource-reads-without-executor
base: develop
current_phase: done
last_updated: '2026-10-29'
phases:
- id: P1
  name: Shared-mode read of rcac://storage
  status: done
  satisfies:
  - R1
  - R5
  - R6
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/resource-reads-without-executor/verify/p1.sh
- id: P2
  name: Delegate-mode reads, refusals and the open context resource
  status: done
  satisfies:
  - R2
  - R3
  - R4
  - R6
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/resource-reads-without-executor/verify/p2.sh && sh spec/resource-reads-without-executor/verify/p3.sh docs && uv run python spec/resource-reads-without-executor/remediation/F1-read-boundary-text.py && uv run python spec/resource-reads-without-executor/remediation/F2-read-hook-refuses-by-default.py && uv run python spec/resource-reads-without-executor/remediation/G1-read-hook-refuses-every-uri-shape.py && uv run python spec/resource-reads-without-executor/remediation/L1-read-hook-refuses-near-open-uris.py
- id: P3
  name: Invariants, docs, the deferral ledger and the full gate
  status: done
  satisfies:
  - R7
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: sh spec/resource-reads-without-executor/verify/p3.sh
review:
  last_reviewed_commit: 8cbe6d0
  verdict: approved
  blocked_reason: ''
  cycle: 3
---

# TECH.md — Reading rcac://storage returns the user's storage paths

The **context engine and finite-state machine** for building this fix. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/resource-reads-without-executor/TECH.md`); the per-phase
checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** [`research/00-digest.md`](research/00-digest.md) + briefs.

## Frontmatter field reference

- `status` (top): `planned | in_progress | blocked | in_review | done` (`done` is stamped by
  `code-publish` after confirmation, just before landing — the terminal state of the retained record)
- `appetite`: `small | big` — caps phase count and build-iteration budget (circuit breaker).
- `branch`, `base`: the cycle's branch (prefix per GOAL `kind`, from the profile's `branches`) and the
  profile's `base`.
- phase `status`: `pending | in_progress | done | blocked`
- `satisfies`: GOAL R-IDs this phase delivers (traceability anchor for `code-review`).
  **Artifact-deliverable R-IDs.** Some requirements are met by a *committed document* — a research
  audit, a protocol doc, an assessment — not by CLI-observable behaviour. Attach such an R-ID to the
  phase that produces and commits the artifact, and give that phase a content `verify:`
  (`test -f …`, a `grep -q` for the sections that must exist) rather than forcing a CLI drive.
  **Say so in the phase body**, because it changes who can grade it: `code-review` blinds its reviewer
  to all of `spec/`, so an R-ID whose evidence lives there is graded by the *orchestrator*, not the
  blind reviewer. Naming it in `TECH.md` is what lets the review skill route it correctly instead of
  reporting an unverifiable requirement.
- `depends_on`: phase ids that must be `done` first (a phase is actionable only when met).
- `parallel`: `true` only for genuinely independent, non-coupled work (docs, tests, isolated leaf
  modules). Any phase touching the profile's `coupled core` is always `false`.
- `hammerable`: `false` marks a correctness/security phase that scope-hammering must **never** cut.
- `hill`: `uphill` (still figuring it out) → `crest` (unknowns resolved) → `downhill` (just
  executing). A phase stuck `uphill` across builds is a raised hand → escalate to the human.
- `attempts`: durable failed-verify counter (absent = 0), bumped by `set_phase.py --phase P<n>
  --record-attempt` on every red verify gate; `next_phase.py` warns at ≥3 — the circuit breaker
  runs on this file, not on session memory.
- `verify`: the exact command that proves the phase (prefer driving the real CLI, not just tests —
  wrap CLI drives in the profile's `throwaway environment` helper, `<helper> sh -c "…"`, so they hit
  a disposable instance, never the developer's real data). A gate carrying `$( )` or quoting the
  calling shell would mangle is set with `set_phase.py --verify-file PATH`, not `--verify`.
- `review.cycle`: completed review passes, auto-incremented by every `set_phase.py --verdict …`;
  REVIEW.md's "Cycle {n}" mirrors it and the ≤3-cycle bound is graded against it. `--verdict approved`
  also clears `review.blocked_reason` unless one is passed explicitly.

## Conventions (apply to every phase)

- Commit conventions, code style, and load-bearing invariants come from the repo's `AGENTS.md` — it
  is the constitution. Walk the sections of its § Invariants that this change touches; that is the
  curated footgun checklist.
- One phase per `code-build` invocation by default; one atomic commit containing **both** the code and
  the `TECH.md` state change. The branch commit subject is code-build's (`$KB/skill/code-build.md` →
  Step 6), not restated here; branch commits are squashed away at `code-publish` per the profile's
  `landing`. Trailers follow the profile's `branch commits`.
- The last phase carries the standing last-phase items: the deferral ledger (`code-plan` Step 6.8),
  and every item the previous cycle's last phase carried for a project-level obligation (mpsearch's
  `## Times` quote, taken as `code-build` Step 4 says). A plan that drops one says why in `PLAN.md`.
- A PR body (when the profile's `landing` opens one) ends with an attribution naming the actual
  harness, model, and variant.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`): the
  help text, docs, or generated files it names change **in the same commit**.

Cycle-specific: `src/rcac_mcp/middleware.py` is high-blast-radius and coupled core. Every phase is
`parallel: false`, and review runs its debate variant. No comment, docstring, test id or message in
`src/` or `tests/` carries a spec id (`tests/test_hygiene.py`). A moved mutation anchor is re-planted
in the same commit, and the case is re-run by the phase gate.

---

## Phase P1 — Shared-mode read of rcac://storage
**Satisfies:** R1, R5, R6 · **Depends on:** —
**Goal:** in `ssh` and `local` mode, in both eras, reading `rcac://storage` returns today's text
format from the server's executor, naming what the `storage_paths` tool names; the tool is served
unchanged.

- [x] `src/rcac_mcp/tools/rcac.py`: move `storage_paths`'s body into the undecorated
      `resolve_storage_paths() -> StoragePaths` (docstring stating it runs on the request's executor);
      the decorated `storage_paths` keeps name, signature, annotation and docstring word for word, its
      body `return resolve_storage_paths()`.
- [x] `src/rcac_mcp/resources.py`: the storage handler calls `resolve_storage_paths()` (function-local
      import kept); the output text is unchanged.
- [x] `src/rcac_mcp/middleware.py`: `SharedExecutorMiddleware._install()` holds the one
      `set_executor(self._executor)`; `on_call_tool` and a new `on_read_resource` call it, then
      `return await call_next(context)`. Docstrings state the per-request contract for both.
- [x] `tests/conftest.py`: give `RecordedPopen` an answer hook (a class attribute, default today's
      `<user>|<command>` answer) and a way for a test to answer `findscratch` and `myquota` per user,
      inside the launcher framing `RecordedPopen` already builds.
- [x] `tests/test_storage_resource.py` (new, `@pytest.mark.unit`, SPDX header, contract docstring):
      `test_storage_read_runs_on_the_shared_executor[legacy|modern]`,
      `test_storage_read_runs_the_local_executor[legacy|modern]`,
      `test_storage_read_without_executor_middleware_fails[legacy|modern]`, as PLAN § 2 describes.
      Each failure message names what ran and what was expected, so the mutants' `why` can match it.
- [x] `tests/mutants.py`: add `resource-calls-decorated-tool` and `shared-read-sets-no-executor`;
      re-plant `shared-middleware-sets-first-call-only` and `shared-middleware-sets-at-construction`
      on the refactored text (anchors unique: include the hook's `def` line where two hooks share a
      body); `tests/test_mutations.py::test_mutation_anchor_applies` stays green for every case.
- [x] `AGENTS.md` same-commit rule: § Testing gains the `test_storage_resource.py` entry and the
      `RecordedPopen` answer hook. (§ Invariants text moves in P3, with the delegate path it also
      describes.)
- **Verify:** `sh spec/resource-reads-without-executor/verify/p1.sh` — the named tests, surface and
  argv pins, mutation anchors and hygiene in both eras, then the four mutants killed.
- **Touches:** `src/rcac_mcp/tools/rcac.py`, `src/rcac_mcp/resources.py`,
  `src/rcac_mcp/middleware.py`, `tests/conftest.py`, `tests/test_storage_resource.py`,
  `tests/mutants.py`, `AGENTS.md` (§ Testing).

## Phase P2 — Delegate-mode reads, refusals and the open context resource
**Satisfies:** R2, R3, R4, R6 · **Depends on:** P1
**Goal:** in `delegate` mode, in both eras, a mapped identity's read of `rcac://storage` runs as its
mapped user and only as that user under concurrency; every unusable request is refused with the
reason its tool call gets and runs nothing; `rcac://context` still answers every client.

- [x] `src/rcac_mcp/resources.py`: each `RESOURCE_REGISTRY` entry gains `'executor'` (`False` for
      `rcac://context`, `True` for `rcac://storage`); `OPEN_RESOURCES: Final[frozenset[str]]` below
      the registry, derived from it with `entry['executor']` (a missing key fails at import), with a
      comment stating the contract (runs nothing; answers any client that can connect).
- [x] `src/rcac_mcp/middleware.py`: `AuthExecutorMiddleware._install(context)` holds today's
      `on_call_tool` body up to `call_next`, unchanged in order and text; `on_call_tool` awaits it and
      returns `call_next`; `on_read_resource` awaits it unless `context.message.uri in OPEN_RESOURCES`,
      then returns `call_next`. `ToolErrorMiddleware`: the try/except moves into
      `_bounded(context, call_next, error, passes)`; `on_call_tool` passes `ToolError` and
      `(FastMCPError,)` (today's behaviour), the new `on_read_resource` passes `ResourceError` and
      `(FastMCPError, NotFoundError, DisabledError)`, so an unknown URI keeps its `Resource not found`
      protocol error; docstrings say it bounds tool calls and resource reads.
- [x] `tests/harness.py`: `Rendezvous.on_read_resource` (the same barrier); the module docstring's
      touchpoint list follows. *Amended in build:* `Rendezvous.waiting` (the barrier's `n_waiting`),
      so the in-flight tokenless read is sent only once the authenticated read is held, its executor
      set, which `read-no-token-reuses-last-executor` needs to be killed whatever the scheduling; and
      `read_refusal(client, uri) -> Refused`, since the unknown-URI test must read the error's code
      (-32602) and no test module may import `mcp`.
- [x] `tests/test_storage_resource.py`: `test_storage_read_runs_as_the_mapped_user[legacy|modern]`,
      `test_concurrent_storage_reads_stay_isolated[legacy|modern]`,
      `test_sequential_storage_reads_each_get_their_executor`,
      `test_storage_check_catches_crossing[…]`,
      `test_storage_read_refused[{no-token,no-claims,all-empty,unmapped,first-claim-unmapped}-{legacy,modern}]`,
      `test_storage_read_without_token_after_an_authenticated_read_fails[legacy|modern]`,
      `test_storage_read_without_token_while_an_authenticated_read_is_in_flight[legacy|modern]`,
      `test_unknown_uri_is_not_found[legacy|modern]`,
      as PLAN § 2 describes. A refusal row builds the same request twice, calls `storage_paths` on
      one and reads on the other, and asserts the read's text contains the row's fixed fragment and
      the tool's reason (the tool text without its `Error calling tool …: ` prefix), and
      `launches == []`.
- [x] `tests/test_context.py`:
      `test_any_client_reads_the_context_in_delegate_mode[{no-token,no-claim,unmapped,mapped}-{legacy,modern}]`:
      the startup text and `launches == []`.
- [x] `tests/mutants.py`: add `auth-read-sets-no-executor`, `storage-read-left-open`,
      `context-read-closed`, `read-boundary-dropped`, `read-boundary-wraps-not-found`,
      `read-no-token-reuses-last-executor`; re-plant every `middleware.py` case whose anchor moved;
      extend the targets of `isolation-executor-cached`, `unmapped-gets-default-user`,
      `no-claim-fallback-identity`, `no-token-fallback-identity`, `auth-middleware-sets-at-construction`,
      `isolation-module-global` and `no-executor-module-global` to the matching read test (PLAN § 2's
      mutant table). Record each retarget in the commit body.
- [x] `AGENTS.md` § Testing: the new tests and the read-capable `Rendezvous`.
- **Verify:** `sh spec/resource-reads-without-executor/verify/p2.sh` — the new tests with the
  modules sharing the middleware, in both eras, then every `middleware.py` and `context.py` mutant
  plus the new ones, each killed.
- **Touches:** `src/rcac_mcp/resources.py`, `src/rcac_mcp/middleware.py`, `tests/harness.py`,
  `tests/test_storage_resource.py`, `tests/test_context.py`, `tests/mutants.py`, `AGENTS.md`
  (§ Testing).

### P2 amendment — review 1 remediation (2026-10-28)

Review 1 (`REVIEW.md`) found two LOW gaps in R6's coverage of P2's read hooks, both routed as
properties with a mutant sweep in both eras. Both are P2's domain (its `middleware.py` read hooks and
R6), so P2 is reopened rather than a phase added. The fix is pinning only: no `src/` change, nothing
the tool path or a read returns changes, and no pin exposed a defect. `verify/` stays frozen at the
plan commit; the class checkers are in `remediation/`.

- [x] **F1 — the read boundary's client-visible text.** Property: a read refused around its handler
      reaches the client as an internal error (-32603) whose text is exactly `str(exc)`, with no type
      name and no traceback, in both eras. Pinned in `tests/test_protocol.py`:
      `read_boundary_violations` (code and exact text) with `test_read_boundary_check_catches_drift`;
      `test_middleware_refusal_is_a_read_error[{permission,runtime}-{memory,http},mcp-error-memory,other-memory × era]`
      over `Raises`, which now also raises on reads; the read row of
      `test_boundary_lets_cancellation_through[on_call_tool|on_read_resource]`. In
      `tests/test_storage_resource.py`, `test_storage_read_refused` is exact against each row's full
      reason (the tokenless row with FastMCP's `Error reading resource …: ` prefix), for the read and
      the tool call, replacing the containment check that let the reviewer's plants pass: a relative
      read-equals-tool pin also let a `_bounded` plant pass, since the tool text carried the same
      leak. The code is pinned too: unbounded, the handshake era sends the reason under code 0, so a
      text-only pin would leave `read-boundary-dropped` alive there. `harness.read_resource` returns
      a protocol error's code in `Outcome.code`.
- [x] **F2 — the delegate read hook refuses by default.** Property: in `delegate` mode every read
      outside `OPEN_RESOURCES` resolves identity, an unknown URI included; only the open set skips it.
      Pinned in `tests/test_storage_resource.py`: `test_unknown_uri_read_is_refused[{no-claims,all-empty,unmapped,first-claim-unmapped} × era]`
      (exactly the tool call's reason) and `test_unknown_uri_is_not_found_in_delegate_mode[{mapped,no-token} × era]`
      (-32602), beside the shared-mode `test_unknown_uri_is_not_found`;
      `test_sequential_storage_reads_each_get_their_executor` now runs in both eras and counts each
      read's launches; `tests/test_protocol.py::test_delegate_read_state_is_request_scoped[era]` (with
      `state_scope_violations` taking the request's method, and its drift control).
- [x] **Mutants** (`tests/mutants.py`). New: `read-boundary-leaks-traceback`,
      `read-boundary-type-name`, `boundary-type-name`, `boundary-catches-named-only`,
      `boundary-reraises-original`, `boundary-passes-nothing`, `boundary-drops-result`,
      `read-hook-resolves-storage-only`, `read-hook-ignores-open-set`, `read-hook-open-set-inverted`,
      `read-hook-installs-after-handler`, `read-hook-drops-result`, `no-token-refused-in-middleware`,
      `no-claim-not-refused`, `delegate-state-not-set`. Retargeted: `boundary-leaks-traceback` (+ read
      rows), `boundary-catches-base-exception` (both cancellation rows), `read-boundary-dropped` (both
      eras; why `refused read: error`), `read-boundary-wraps-not-found` (+ the delegate not-found rows),
      `auth-middleware-sets-first-call-only` (+ the sequential reads), `delegate-state-session-scoped`
      (+ the read row). Equivalent mutants, each run against the six read-related modules in both
      eras and surviving, are recorded with their reasons in the checkers, not as cases:
      `read-boundary-raises-tool-error`, `read-boundary-wraps-disabled`,
      `read-boundary-rewraps-fastmcp-error`, `boundary-drops-cause`, `read-boundary-passes-mcp-error`,
      `no-token-check-falsy`, `read-hook-stringifies-uri`, `executor-set-after-state`.
- [x] `AGENTS.md` § Testing: the read boundary rows, the exact refusal reasons, the unknown-URI pins,
      the read state row, `Raises` on reads and `Outcome.code`.
- [x] Class checkers: `remediation/F1-read-boundary-text.py` and
      `remediation/F2-read-hook-refuses-by-default.py` (shared `remediation/sweep.py`). Each runs its
      pinning tests in both eras, then its sweep under `CLUSTER_MCP_TEST_ERA` unset and `modern`. The
      sweep is every case whose anchor lands in the swept functions, found by locating the anchor in
      `middleware.py` (F1: `_bounded`, `ToolErrorMiddleware.on_read_resource`; F2:
      `AuthExecutorMiddleware.on_read_resource`, `._install`, plus the `OPEN_RESOURCES` cases in
      `resources.py`), so a case added there later is swept without being named.
- **Verify (amended):** the frozen `verify/p2.sh`, then `verify/p3.sh docs` (P3 is done and later,
  so the reopened gate carries its document checks), then the two checkers. Over a 10-minute command
  cap, run the four as separate commands. The profile's whole `verify` runs after it, as P3's gate
  (`p3.sh full-legacy`, `p3.sh full-modern`).
- **Touches (amended):** `tests/harness.py`, `tests/test_protocol.py`, `tests/test_storage_resource.py`,
  `tests/mutants.py`, `AGENTS.md` (§ Testing), `spec/resource-reads-without-executor/remediation/`.

### P2 amendment — review 2 remediation (2026-10-28)

Review 2 (`REVIEW.md`, cycle 2) resolved F1 and found F2 fixed for its instance only: G1, the default
refusal pinned at one unknown URI (`rcac://nope`), not over the URI domain, so two mutants that sort
URIs by shape (`not uri.startswith(tuple(OPEN_RESOURCES))`; `uri.startswith('rcac://') and uri not in
OPEN_RESOURCES`) passed the suite. The property is F2's over its whole domain, in P2's read hook and
R6, so P2 is reopened again. No `src/` change: no pin exposed a defect.

- [x] **The class, scoped by probing, not by grep.** A delegate server with a probe middleware, read
      by an unmapped, a no-claim, a mapped and a tokenless caller and a shared-mode one, 33 URI shapes,
      each sent through FastMCP's client and verbatim through its session, both eras (identical): the
      read hook sees exactly the string sent and FastMCP looks up exactly that string; nothing on the
      server normalises. FastMCP's client normalises before sending (pydantic `AnyUrl`: it lowercases
      the scheme and strips surrounding space, so `RCAC://storage` from it is the storage read itself
      and `RCAC://context` the open read); any other client sends what it likes. On the clean code
      every shape not exactly `rcac://context` is refused for the refused callers, with the exact
      reason, and is -32602 for the others, `RCAC://storage` sent verbatim included. So the pins send
      verbatim, and the live sites of the claim are `AGENTS.md` §1, §8 and § Testing and `SECURITY.md`
      § Request Isolation, which now say membership is the exact string sent.
- [x] **Pins** (`tests/test_storage_resource.py`). `NOT_OPEN`, 21 shapes, replaces `UNKNOWN`: a path
      below the open URI, a URI it prefixes, a prefix of it, a URI ending in it, a trailing slash, host
      and scheme case variants, a percent-encoded and a full-width letter, a leading and a trailing
      space, a query, a fragment, no authority slashes, no scheme, `rcac://storage/`, `RCAC://storage`,
      `rcac://STORAGE`, `file:///nope`, `https://example.org/x`, `rcac://nope`. Every shape is read in
      `test_unknown_uri_read_is_refused` (exactly the tool call's reason, -32603),
      `test_unknown_uri_is_not_found_in_delegate_mode` and `test_unknown_uri_is_not_found` (-32602),
      each violation naming the shape; the test ids and counts are unchanged, so F2's checker stands.
      New `test_not_open_shapes_are_neither_open_nor_served` keeps the table clear of a served or open
      URI. `harness.read_verbatim` (the session's `read_resource`, the string as given) replaces
      `read_refusal`, which nothing else used.
- [x] **Mutants** (`tests/mutants.py`), each replacing the membership test, each killed by the refused
      rows with a `why` naming a shape it lets through: `read-hook-open-by-prefix` and
      `read-hook-rcac-scheme-only` (the reviewer's two, planted as written), `read-hook-open-by-suffix`,
      `-open-by-substring`, `-open-within-open-uri`, `-open-if-prefix-of-open`, `-open-by-host`,
      `-case-folded`, `-casefolded`, `-scheme-case-folded`, `-strips-trailing-slash`, `-strips-space`,
      `-strips-leading-space`, `-drops-query-and-fragment`, `-authority-only`, `-ignores-scheme`,
      `-defaults-scheme`, `-adds-authority-slashes`, `-unquotes`, `-nfkc-normalised`; in `resources.py`,
      `open-set-holds-slash-variants`; the other side, `read-hook-refuses-unserved` (an unserved URI
      refused by shape), killed by the mapped and tokenless not-found rows. Equivalent, planted against
      the six read-related modules (211 tests) in both eras and surviving, recorded in the checker:
      `read-hook-open-by-equality` (`!= 'rcac://context'` while the open set holds one URI) and
      `read-hook-open-in-list` (list membership is the same equality).
- [x] Class checker `remediation/G1-read-hook-refuses-every-uri-shape.py`: its pins in both eras, then
      every case whose edit replaces the membership test or the `OPEN_RESOURCES` derivation, found by
      evaluating each case's edits (`sweep.cases_editing`), in both eras. Seen red first: with
      `NOT_OPEN` cut back to `rcac://nope`, the reviewer's two cases survive.
- [x] `AGENTS.md`: § Testing (the shapes, `read_verbatim` for `read_refusal`, the table guard); §1 and
      §8 say *exactly* in `OPEN_RESOURCES`, membership being the string sent. `SECURITY.md` § Request
      Isolation likewise.
- **Verify (amended):** as review 1's, then the G1 checker; over a 10-minute command cap, five separate
  commands. Then the profile's whole `verify` (`p3.sh full-legacy`, `p3.sh full-modern`).
- **Touches (amended):** `tests/harness.py`, `tests/test_storage_resource.py`, `tests/mutants.py`,
  `AGENTS.md` (§ Testing, §1, §8), `SECURITY.md`, `spec/resource-reads-without-executor/remediation/`.

### P2 amendment — review 3 remediation (2026-10-29)

Review 3 found L1 (LOW): G1's pin is a finite table, so ten URI normalisers planted in the read hook's
membership test, their disjunction, and an open set that also holds each open URI with `?` appended
each change only shapes outside `NOT_OPEN`, and passed the suite in both eras. Geoffrey's ruling at the
review bound (2026-10-29): one scoped remediation, which the foreman verifies; no fourth review. The
property is G1's, in P2's read hook and R6, so P2 is reopened a third time. No `src/` change: the shipped
code refuses every generated shape, and no pin exposed a defect.

- [x] **Pin, generated** (`tests/test_storage_resource.py`). `NEAR_OPEN`: for every served URI (the
      open ones and those that run commands), every one-character insertion, deletion and substitution
      over printable ASCII plus NUL, tab, newline, vertical tab, form feed, carriage return and DEL, at
      every position; wrappers (`<>`, quotes, backticks, brackets, surrounding space, tab, newline,
      CRLF, NUL); suffixes (`?`, `#`, `?#`, `:`, `:80`, `.`, `/.`, `/./`, `/`, `//`, CRLF); userinfo
      (`@`, `u@`, `u:p@`); leaving out exactly the URIs the registry marks open: 5,712 shapes today,
      about 2,850 per URI. It excludes the registry's open entries, not `OPEN_RESOURCES`: the first draft
      excluded `OPEN_RESOURCES`, and `open-set-holds-query-variants` survived, since a grown open set
      removed its own shape from the domain. `test_near_open_read_is_refused[no-claims|unmapped]` reads
      every shape verbatim (`harness.read_verbatim`) on one session, 128 reads in flight, and requires
      exactly the row's reason as -32603 and no launch. It speaks the selected era, not an `era`
      parameter: about 5 s (handshake) and 4 s (modern) per row, so the profile's two suite runs carry
      one era each, and the checkers run it under both. `test_near_open_shapes_cover_every_served_uri`
      pins what the set holds (every deletion; control, punctuation and whitespace at both ends; 15
      normaliser targets; no open URI; a size floor). G1's named table and its other side stay as
      they were: mapped, tokenless and shared callers get -32602 for every `NOT_OPEN` shape, and
      `rcac://context` answers every client. Generating the other side too was left out for time
      (a mapped caller adds about 5 s per era); it guards against over-refusal, not a bypass.
- [x] **Mutants** (`tests/mutants.py`), each a membership-test replacement killed by
      `test_near_open_read_is_refused[unmapped]` with a `why` naming a shape it lets through:
      `read-hook-strips-crlf`, `-strips-trailing-query-or-fragment-mark`, `-drops-port`,
      `-drops-userinfo`, `-strips-trailing-dot`, `-removes-tab-and-newline`, `-strips-leading-slash`,
      `-strips-quotes-and-brackets`, `-strips-trailing-nul`, `-drops-dot-segment`, `-any-normaliser`
      (all ten at once); in `resources.py`, `open-set-holds-query-variants`. Seen red first: targeted
      at G1's table rows, all twelve survive in both eras; with `NEAR_OPEN` cut back to `NOT_OPEN`,
      all twelve survive the new row in both eras.
- [x] Class checker `remediation/L1-read-hook-refuses-near-open-uris.py`: the generated and table pins
      in both eras, then G1's sweep evaluated afresh (every case editing the membership test or the
      `OPEN_RESOURCES` derivation, `sweep.cases_editing`), each in both eras. Equivalent, carried from
      G1: `read-hook-open-by-equality`, `read-hook-open-in-list`. G1's checker is not superseded and
      still passes; its sweep now also runs the twelve.
- [x] `AGENTS.md` § Testing: the generated neighbourhood, its two tests and why it speaks the selected
      era. §1, §8 and `SECURITY.md` already say *exactly* in `OPEN_RESOURCES`, the string sent; unchanged.
- **Verify (amended):** as review 2's, then the L1 checker; over a 10-minute command cap, six separate
  commands. Then the profile's whole `verify`.
- **Touches (amended):** `tests/test_storage_resource.py`, `tests/mutants.py`, `AGENTS.md` (§ Testing),
  `spec/resource-reads-without-executor/remediation/`.

## Phase P3 — Invariants, docs, the deferral ledger and the full gate
**Satisfies:** R7 · **Depends on:** P2
**Goal:** `AGENTS.md` § Invariants and the docs that restate it describe what is true after the fix,
and the profile's whole `verify` is green. R7's evidence is `AGENTS.md`, outside `spec/`, so the
blind reviewer grades it.

- [x] `AGENTS.md` § Invariants §1: `set_executor()` is called per tool call and per resource read,
      from `on_call_tool` and `on_read_resource`; a sync resource handler reads its request's copy as a
      sync tool does; the delegate read hook skips `OPEN_RESOURCES`; `ToolErrorMiddleware` also
      bounds reads, raising `ResourceError(str(exc))`.
- [x] §7: drop the `resources.py` `TypeError` sentence and its parenthetical; name
      `resolve_storage_paths()` as the undecorated helper the tool and the resource share.
- [x] §8: replace the "`rcac://storage` is unchanged" sentence and its seed pointer with how reads are
      served (each read gets its request's executor; `rcac://storage` runs as the mapped user in
      `delegate` mode and is refused as a tool call is; `OPEN_RESOURCES` names the resources that run
      nothing and answer any client, an unknown URI from a refused caller drawing the refusal);
      reword "the middleware refuses every tool call" to cover reads but `OPEN_RESOURCES`.
- [x] Same-commit restatements: § Repository map (`middleware.py`, `resources.py`, `tools/rcac.py`
      rows), § Architecture & data flow (the diagram's `on_call_tool` arrow covers reads),
      `SECURITY.md` § Request Isolation in Delegate Mode (the middleware hook covers reads).
- [x] Deferral ledger: walk P1–P3 and this cycle's commits for "do not fix here", "known
      limitation", "follow-up"; each needs an `issues/{slug}.md` (from the KB `ISSUE.md` template)
      and a `ROADMAP.md` entry, or the security lane for a live weakness. None is planned. The seeds this
      cycle adopted stay `adopted:resource-reads-without-executor`; `code rcac-mcp roadmap` retires
      them and their `ROADMAP.md` entry after landing, not this phase.
- **Verify:** `sh spec/resource-reads-without-executor/verify/p3.sh` — the R7 document checks, then
  the profile's whole `verify`. Over a 10-minute command cap, run `p3.sh docs`, `p3.sh full-legacy`
  and `p3.sh full-modern` as separate commands; together they are `p3.sh all`.
- **Touches:** `AGENTS.md`, `SECURITY.md`.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[{category}]` commit; stop and report.
