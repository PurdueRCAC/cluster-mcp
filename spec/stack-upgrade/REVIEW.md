# REVIEW — Move the stack before building on it

> Adversarial QA by `code-review`, run as the rubric's **debate variant** (the diff touches the
> profile's coupled core): two independent fresh subagents at xhigh effort, one arguing "ship" and
> one "block", each in its own clone of the reviewed commit, with the same curated inputs — the
> GOAL, the spec-excluded diff, the runnable repo, `AGENTS.md` and the rubric. Neither saw `PLAN.md`,
> `TECH.md`, `verify/` or commit bodies. Every finding cites an executed command.

- **Reviewed commit:** 1a8e50e9219233cd5b09247ebda4edad928acd0f  ·  **Base:** develop (3d010ec)  ·  **Date:** 2026-10-17
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md`
- **Contract drift:** `GOAL.md` changed after the shape commit once, in the plan commit `d47cf63`
  (clarifications dated 2026-10-17 from the adversarial design review). That is the plan step's
  sanctioned route for a clarification at PLAN/TECH sign-off; the foreman, judge for this effort,
  confirmed the contract before grading.

## Verification run

- Profile verify (both reviewers) → exit 0, 416 passed, sandboxed `--help` printed;
  `CLUSTER_MCP_TEST_ERA=modern` → 416 passed, era log 88 connects, all
  `version=2026-07-28 first=server/discover`.
- `tests/mutants.py --self-check` over all 67 cases → 67/67 killed in legacy and 67/67 in modern,
  both runner controls ok (both reviewers).
- Independent R3 snapshots taken on 3d010ec's FastMCP 2 environment by both reviewers equal
  `tests/fixtures/served_surface.json` byte for byte; HEAD differs only in the tolerated shapes.
- Raw-HTTP `initialize` at 2024-11-05, 2025-03-26, 2025-06-18 and 2025-11-25 each negotiated that
  version with `instructions == SERVER_INSTRUCTIONS` and exactly `EXPECTED_TOOLS`; an `auto` client
  got 2026-07-28 with no `InitializeResult`; `sse` falls back to 2025-11-25.
- Real HTTP with `-a jwt`: a generated token → 200; no token, wrong secret, expired → 401. 31-char
  secret → exit 2 on `--generate-token`.
- R10 audit: HEAD lock exit 0 over 94 packages; the base lock exit 1 naming packages and versions;
  `UV_OFFLINE=1` and a dead loopback proxy each exit 2; the profile verify does not run it.
- Block-side probes, all clean: extra arguments were already rejected server-side on 3d010ec with
  identical text (no documented call breaks under `additionalProperties: false`); a parity run of
  all 23 tool cases matched exactly (text, content blocks, structured content, error flag); 12 users
  over HTTP with tokens, with and without the rendezvous, 1/3/4 rounds, both eras — no crossing;
  `SSHExecutor` through `~/.ssh/config` with ed25519, ecdsa and RSA OpenSSH keys against a loopback
  server on paramiko 5 / cryptography 50 — all worked, and PKCS1 and encrypted keys load as on
  paramiko 4; the icon route unchanged; `server/discover` without a token → 401.
- Release gate offline steps: `uv build`, `twine check --strict`, sdist hygiene → pass.
- Cleanliness: each reviewer worked only in its own clone; no sudo/ssh, no push, network only for
  package resolution and the advisory source.

## Requirement → evidence matrix

| R-ID | Verified how | Planted violation → verdict | Status |
|------|--------------|------------------------------|--------|
| R1 | pyproject `fastmcp>=4,<5`; lock fastmcp 4.1.0, mcp 2.3.0; `uv lock --check`, `uv sync --locked` | — | ✅ |
| R2 | four `test_client_era_is_served` rows; raw-HTTP handshakes at four legacy revisions; `auto` → 2026-07-28 | `instructions-dropped` killed in both eras | ✅ |
| R3 | two independent base snapshots equal the fixture | `timeout` float→int caught; `cwd` default change caught | ✅ |
| R4 | stdio and http in both eras, sse in legacy; no leftover processes | `sse-transport-unserved` killed | ✅ |
| R5 | `test_tokens` + real HTTP 200/401s + CLI floor | 9 token/floor mutants killed | ✅ |
| R6 | 8 one-missing rows; posture test; recorder + guard prove nothing built or reached | `oidc-*` killed; `forward_resource` deletion caught | ✅ |
| R7 | `get_type_hints` resolves to `Final[Dict[str, Callable[[], AuthProvider \| None]]]` | `auth-modes-annotation-slice` killed | ✅ |
| R8 | all 296 base ids collected (`comm -23` empty); 416 pass per era; only allowed modules edited; importorskip forms flagged | removing `importorskip` from `IMPORTERS` → 3 failures | ✅ |
| R9 | 67/67 killed in both eras; the 53 base cases unchanged | — | ✅ |
| R10 | live audit runs above | — | ✅ |
| R11 | § Project, §1, §6, §7, the footgun line, § Testing, release gate; §6 defaults, §7 `FunctionTool` TypeError and the sse fallback executed | high-blast-radius list diff empty | ✅ |

Unmapped changes: none material. Every upgrade outside the stack was resolver-forced or flagged by
the base lock's audit; the two new seeds and their ROADMAP entries are deferral records the manual
allows. `test_hygiene.py`'s widened `STACK` is covered by the GOAL's clarification C3.

## Findings

All four are LOW and CONFIRMED; both reviewers argued ship.

### [LOW/CONFIRMED] F1 — `bin/audit_lock.py` claims a CI workflow runs it
- **Where:** `bin/audit_lock.py:17-18` (docstring).
- **Failure scenario:** the docstring says "a CI workflow mirrors that gate by running the same file,
  so the two cannot drift"; there is no `.github/`, and R10's CI clause is vacuous for this cycle.
- **Evidence:** `git ls-files .github` → empty (both reviewers).
- **Routing:** the class — every claim in this branch's files that a CI workflow exists or runs
  something — is made true or worded as future (ci-workflow lands it).

### [LOW/CONFIRMED] F2 — An upgraded OIDC deployment silently loses its client registrations
- **Where:** behaviour change from FastMCP 2.14's encrypted `DiskStore`
  (`<home>/oauth-proxy/cache.db`) to 4.1's `FileTreeStore` (`<home>/oauth-proxy/<key-fingerprint>/`);
  `AGENTS.md:34-36` records only the 30-minute idle close as an accepted behaviour change.
- **Failure scenario:** after the upgrade, clients registered with the old proxy must register
  again; nothing tells an operator.
- **Evidence:** registered `client-1` with the 2.14 proxy, built a 4.1 proxy on the same home and
  key → `get_client` returned false.
- **Routing:** record it among the accepted 4.x behaviour changes (AGENTS.md § Project and §6,
  SECURITY.md's OIDC subsection) and in the landing message.

### [LOW/CONFIRMED] F3 — Request-scoped middleware state is not pinned
- **Where:** `src/rcac_mcp/middleware.py:182-183`; § Invariants §1 states the rule.
- **Failure scenario:** dropping `serializable=False` moves `rcac_user` into the session-scoped
  store and nothing fails. No reader exists today, so impact is nil, but it is an invariant line
  with no pin.
- **Evidence:** planted `serializable=True` → the full suite passed (416 and 422 in the two clones);
  `grep set_state\|serializable tests/` → nothing.
- **Routing:** a test pins that the state is request-scoped (not visible to a later request on the
  same session), plus a mutation case that drops `serializable=False`.

### [LOW/CONFIRMED] F4 — Unlisted client-visible text and a stale roadmap entry
- **Where:** the unknown-tool error text (`Unknown tool: no_such_tool` → `Unknown tool:
  'no_such_tool'`); `serverInfo.version` (2.14.4 → 4.1.0, FastMCP's own version); `ROADMAP.md`'s
  stack-upgrade entry ("puts a dependency-audit step in CI", "Depends on … ci-workflow").
- **Failure scenario:** the landing message under-reports what clients see; the roadmap misstates
  the audit's home and the landing order.
- **Evidence:** a base-vs-HEAD call of an unknown tool; `git diff` of `ROADMAP.md`.
- **Routing:** both text changes go in the landing message's difference list; the roadmap entry
  gets a dated 2026-10-17 correction (audit in the release gate; ci-workflow lands after and picks
  it up through its mirror check), historical text kept.

## Human-gate triggers

- None. F3's file (`middleware.py`) is on the high-blast-radius list, but F3 is a missing pin, not
  a violation: the code is correct and no contract is broken. Recorded here so the next cycle's
  review can see the judgement.

## Review cycle 2 — changes-requested (2026-10-17)

- **Reviewed commit:** 49a0e5655a9f33aa2d15ad1fdec0aa6904c53961 · **Mode:** scoped by the foreman to
  verifying the remediation of F1–F4, plus a no-regression check (fresh blind subagent, xhigh).
- **Verification run:** profile verify → rc 0, 423 passed; `CLUSTER_MCP_TEST_ERA=modern` → 423
  passed; `tests/mutants.py --self-check` over all 68 cases → 68 killed in each era, both controls
  report; ids 416 → 423 (7 added, 0 removed); cases 67 → 68 (0 removed); spec-id grep (`-w`,
  `noqa:` excluded) → 0 hits with a positive control; hand-back clean.
- **F1 — fixed.** A predicate sweep (`git grep -i -E 'workflow|github actions'`, `git grep -i -w ci`)
  over every tracked file outside `spec/`: `bin/audit_lock.py:17-18`, `AGENTS.md:926` and the
  profile's `ci` key all say no CI exists yet; no remaining text claims CI runs anything today.
- **F2 — fixed, reproduced.** `create_auth_oidc()` against a loopback discovery document with
  `FASTMCP_HOME`/`HOME` in scratch: 2.14 wrote `oauth-proxy/cache.db` and found the client; 4.1
  returned `None` and created `oauth-proxy/<sha256(key)[:12]>/…`. The three sites state it accurately.
- **F3 — fixed.** `serializable=True` planted at both sites → `test_delegate_state_is_request_scoped[legacy]`
  failed with "state outlived its request"; the modern row passes, and the reviewer's own probe
  confirmed why: legacy keeps one `mcp-session-id` across a connection, the 2026-07-28 era sends no
  session header and a new state prefix per request. `delegate-state-session-scoped` killed in
  both eras; four negative controls cover the check's branches.
- **F4 — fixed** for the stack-upgrade entry (`ROADMAP.md:58-60`, dated, historical sentence kept).

### [LOW/CONFIRMED] N1 — Other roadmap text still says CI lands first and carries the audit
- **Where:** `ROADMAP.md:39` (the ci-workflow entry: "`stack-upgrade` adds a dependency-audit step
  to it") and `ROADMAP.md:30-31` (Part 0's blurb: the first cycle is the CI gate); and
  `issues/ci-workflow.md` names no audit step among its criteria.
- **Failure scenario:** the index contradicts the stack-upgrade correction and the landing order.
- **Routing (orchestrator):** dated 2026-10-17 corrections at both ROADMAP sites, historical text
  kept, stating that stack-upgrade lands first and that ci-workflow's mirror of the release gate
  will include the audit. `issues/ci-workflow.md` is adopted by the in-flight ci-workflow cycle on
  its own branch; the foreman records the audit-in-CI requirement as a clarification in that
  cycle's GOAL when it rebases onto develop, so this branch does not edit that seed (it would
  conflict with the adopting branch).

### Human-gate triggers (cycle 2)

- None.

## Review cycle 3 — approved (2026-10-17)

- **Reviewed commit:** a207f9577699f61f1620107e1633e3834b0554df · **Mode:** scoped by the foreman to
  verifying the remediation of N1, plus a no-regression check (fresh blind subagent, xhigh). The last
  cycle the bounded loop allows.
- **Verification run (clean clone at a207f95):** profile verify → exit 0; suite → 423 passed in the
  handshake era and 423 in the modern era; `tests/mutants.py --self-check` over all 68 cases → 68
  killed with both self-check controls in each era; markers 404 unit + 19 integration = 423; spec-id
  grep (`-w`, `noqa:` excluded) → 0; the delta is two `ROADMAP.md` hunks (8 lines added, 0 removed),
  both mapping to N1; hand-back clean.
- **N1 — fixed.** Dated 2026-10-17 corrections at `ROADMAP.md:33-35` (Part 0) and `:45-47`
  (ci-workflow entry), historical text kept at `:30-31` and `:43`; both match the repo (the release
  recipe's `gate` runs `bin/audit_lock.py`, AGENTS.md:537; no `.github/`; the profile's `ci` key reads
  "none yet", AGENTS.md:508) and agree with the stack-upgrade correction at `:66-68`.
- **Observation, not a blocking finding (orchestrator):** the reviewer's predicate sweep found the
  same class in two more places — the stack-upgrade entry's own `Depends on: … ci-workflow` field
  (`ROADMAP.md:70`) and this cycle's adopted seed `issues/stack-upgrade.md` (`:37`, `:54`, `:77`,
  `:84-85`). Both live in records this cycle's landing retires: `code rcac-mcp roadmap` deletes the
  adopted seed and the stack-upgrade entry, `Depends on` line included, once the cycle is on
  `develop`. The same reasoning dropped strip-docs-subsystem's adopted-seed residual (2026-10-16).
  The orchestrator's own N1 routing named two sites instead of the whole predicate, which is why a
  third cycle found a sibling; recorded so the routing of prose classes is stated as a predicate
  over every live record.
- **Convergence.** Three cycles: four LOW → one LOW (a sibling of F4's class) → approved with one
  observation in records the landing retires. No CRITICAL, HIGH or MEDIUM in any cycle; both debate
  reviewers argued ship in cycle 1.

### Human-gate triggers (cycle 3)

- None in any cycle (cycle 1's F3 touched `middleware.py` as a missing pin, not a violation).
