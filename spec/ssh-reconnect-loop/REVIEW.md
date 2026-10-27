# REVIEW — A lost SSH connection makes every later call wait forever

> Adversarial QA by `code-review`, run in an isolated/clean context (subagents). The correctness
> pass grades the branch diff against [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants
> **only** — it does not see `PLAN.md`/`TECH.md`. Every finding cites an **executed** command.

- **Reviewed commit:** 6cde041621ed973b36a6254517aeab033c27b3e7  ·  **Base:** develop `d34de62`  ·  **Date:** 2026-10-26
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — the debate variant (the diff touches the coupled core: `executor/ssh.py`),
  two blind reviewers at once, each in its own clone.

## Verification run

- Both clones: `uv lock --check`; `1760 passed` per era, none skipped (era logs show `initialize`
  at 2025-11-25 and `server/discover` at 2026-07-28); `--help` exits 0; the cycle's 15 mutants
  killed.
- Real `SSHExecutor` against `tests/ssh_server.py` under `bin/sandbox.sh`, a 3 s window: refused
  host, silent listener, a `getaddrinfo` stall, a silent ProxyJump host, a never-answering agent,
  staggered and concurrent calls (16 at once: one attempt in flight, descriptors and threads flat),
  refused auth (one attempt, at once); 14 tools through MCP in both eras.

## Requirement → evidence matrix

| R-ID | Verified how | Status |
|------|--------------|--------|
| R1 | every failure class returns −1002 naming host and cause within the per-call bound | ✅ (cause misnamed under F1) |
| R2 | host back 0.7 s into the window: same result as unbroken; banner-phase drop recovers at 1.59 s | ❌ F1 |
| R3 | the next call after each failure succeeds; `gives-up-for-good` killed | ✅ |
| R4 | −1002 only before a channel; `sbatch` "not submitted"; put/get "nothing was transferred" | ✅ (F3 docs) |
| R5 | footgun, §3 bullet, map, docstring match the bound; `test_reconnect_texts_state_the_bound` | ❌ F1, F3 wording |
| R6 | fakes and the loopback server, both eras | ✅ (blind to F1, C1) |
| R7 | one worker at peak; per-call mutant killed | ✅ |

Unmapped changes: none material (`sacct`'s whoami check, the context-cache guard and the moved
`connect_failure_message` serve Q6, R3 and Q3).

## Findings

### [MEDIUM/CONFIRMED] Any `AuthenticationException` ends the reconnect, not only a refusal
- **Where:** `src/rcac_mcp/executor/ssh.py:779`; texts at `:580`, `AGENTS.md:1143`.
- **Failure scenario:** Paramiko raises the class for a link lost mid-auth ("transport shut down or
  saw EOF"), this executor's own `_abort` during auth, and "Authentication timeout." A drop mid-auth
  with the host back 1 s later returns −1002 "authentication failed" in < 0.01 s of a 45 s window;
  a call joining an attempt another call's give-up aborted fails as "authentication failed" in
  0.01–0.10 s (3 of 3, no injection); one 5 s auth stall gives up at 2.06 s. The tests script only
  'Authentication failed.'.
- **Touches:** R2, R1 ("names the cause"), R5; Q4 covers a refused authentication only.

### [LOW/CONFIRMED by forced interleaving] An abort can close a connection just published
- **Where:** `ssh.py:716-725` (`_leave`), `:705` (`_settle`).
- **Failure scenario:** `_leave` decides under the lock to abort and calls `_abort` outside it
  without checking again; a publish in that gap is closed. With 0.3 s injected before `_abort`, the
  next call on the healthy host got −1003 ("may have run"; through `sbatch`, "may have been
  submitted") and the executor kept a dead connection. 0 natural hits in 400 runs.
- **Touches:** R7, R4; the `_abort` docstring ("never the one closed"), `AGENTS.md:1149`.

### [LOW/CONFIRMED] A write that cannot reconnect leaves its staging behind
- **Where:** `ssh.py:884` docstring ("writes nothing"); § Invariants §2's "removed on every path".
- **Failure scenario:** drop after staging, host down: −1002 with the target untouched (R4 holds),
  but `.cluster-mcp-<hex>/{content,expected}` stays beside it, since `_discard` runs on the dead
  session. Pre-existing in kind: at `d34de62` a drop there also left it (and raised).

### Coverage observations (LOW/CONFIRMED)
- `_leave`'s done-check (`:719`) and `_publish`'s live-connection branch (`:663`) survive mutation
  (block); the bound's floor (`:285`, `max(CONNECT_TIMEOUT, …)`) and `write`'s shared deadline
  across its inner runs (`:904, 944, 957`) survive every reconnect row (ship). The code is right in
  each; nothing pins it.

### Observations (no finding)
- The stuck-step trade (Q7, R7) reproduced as `issues/ssh-reconnect-stuck-step.md` states it.

## Human-gate triggers

- All three findings are in `executor/ssh.py` (high-blast-radius, coupled core); F3 touches §2's
  text. The foreman holds the gate (decision `2026-10-16-cluster-mcp-autonomous`) and routes them to
  a fix; sign-off is recorded once the fix is reviewed.

## Routing (each as its class) — cycle 1

1. **Only a refusal ends the reconnect at once.** Classify each authentication outcome by its
   cause: the server rejecting the credentials ends the attempt at once; a lost link, an auth
   timeout and an abort are not refusals, are named as what they are, and leave the window open. A
   call whose window is still open never inherits the outcome of an attempt aborted for another
   call's deadline. Pin each cause, with the real server where it can produce it.
2. **An abort never closes a published connection.** Every abort decision is re-checked against
   the attempt's state at the moment it acts; pin with a deterministic interleaving at the seam.
3. **A write's texts say what it leaves.** The docstring and § Invariants §2 state that a staging
   directory can remain when the host is lost after staging; its cleanup is filed as a seed.
4. **Pin the four unpinned lines** (`_leave`'s done-check, `_publish`'s live branch, the bound's
   floor, `write`'s shared deadline), each with a test and a mutant, or delete the branch if it is
   unreachable.

## Review cycle 2 — changes-requested (2026-10-26)

- **Reviewed commit:** 091adfa1c2abcd4625fb28d8692ecb2e496cee17 · a fresh blind debate pass over the
  full spec-excluded diff.
- **Verification:** both clones `1788 passed` per era, `--help` exits 0 (locked Paramiko 5.0.0,
  Fabric 3.2.2). Ship drove every R-ID against the real executor and loopback server (refused,
  silent, banner, auth cut short and timed out, abort during auth, DNS and agent stalls, ProxyJump
  target, gateway and channel, eight concurrent calls on a returning host) and its seven mutations
  all went red. Block's 30-trial real-thread stress run (180 calls, auth held 0–4 s, the host
  returning at random): none past the window + 0.35 s, none raised, no −1003, never more than one
  attempt, no leaked worker or session, every trial's last call succeeded. Cycle 1's four classes
  hold at the locked versions.

### [MEDIUM/CONFIRMED] The auth classification holds only on Paramiko ≥ 3.2
- **Where:** `src/rcac_mcp/executor/ssh.py:72-77, 374`; `AGENTS.md:1181`.
- **Failure scenario:** the cause is read from Paramiko's message text. On Paramiko 2.12–3.1, which
  the declared range allows (`fabric>=3.0`, Fabric 3.2.2 requires `paramiko>=2.4`), a link closed
  during auth and this executor's own abort raise `AuthenticationException("Authentication
  failed.")`, the refusal's text. In a scratch venv with Paramiko 3.1.0 the suite's own rows
  `test_an_authentication_cut_short_is_retried[closed]` and
  `test_a_call_never_inherits_an_aborted_attempt` fail: −1002 "authentication failed" with the host
  back. `type(exc) is AuthenticationException` also counts every subclass as a refusal (PLAUSIBLE
  for Fabric's opt-in `AuthFailure`).
- **Touches:** R2, R1 (the cause), R5 (the footgun's claim).

### [LOW/CONFIRMED] A first attempt can start after the stated last start
- **Where:** `ssh.py:825-846`; texts at `AGENTS.md:1166-1167`, `:612-614`, `:809-810`.
- **Failure scenario:** only retries and aborted attempts check `FINAL_ATTEMPT_LEAD`; a write's later
  commands share its deadline, so their first attempt started at 2.43 s and 3.53 s (past the
  deadline) of a 3 s window whose last start is 1.0 s, the second reporting `timed out` against a
  refusing host. The bound holds; the texts do not.

### [LOW/CONFIRMED] The texts on an agent stall are wrong
- **Where:** `ssh.py:777-779`; `issues/ssh-reconnect-stuck-step.md:15`.
- **Failure scenario:** both say an agent query has no transport and nothing to close, and that its
  late success is published. With an agent that never answers, the attempt had a transport, the
  abort closed it, the worker stayed in `agent.py _read_all`, and its eventual `lost ssh-agent` was
  discarded.

### [LOW/CONFIRMED] Two rules survive mutation
- `_abort`'s re-check reduced to "the outcome has come" (dropping "another call has joined since")
  and `_release(conn)` removed from a failed attempt (one live transport left per attempt, by
  probe) both pass the 52 reconnect rows.

### Scope triage (foreman)
- **Startup's message:** an auth timeout now reads `timed out (…)` and a link shut during auth
  `connection closed during authentication`, where both read `authentication failed` before. The
  non-goal leaves the startup *connect* and its timeout unchanged; Q3 requires one message form for
  both, so startup naming each cause as the reconnect does is in scope. No change.
- **`sacct`'s whoami** raising on any non-zero exit (not only −1002): accepted under Q6; a failed
  whoami used to run the query with `-u ''`.

## Human-gate triggers — cycle 2

- All CONFIRMED findings are in `executor/ssh.py` (high-blast-radius); the foreman holds the gate
  under the autonomy decision and routes them to a fix.

## Routing (each as its class) — cycle 2

1. **The declared dependency range is the range the behaviour holds on.** Classify an
   authentication outcome by something every allowed Paramiko provides, or raise the declared floor
   to where the classification holds (`paramiko>=3.2`, with the reason); pin it with a test that
   fails if the floor and the classifier disagree. Every `AuthenticationException` subclass Paramiko
   or Fabric can raise is classified by its cause.
2. **No connect attempt starts after the stated last start**, first attempts and a write's later
   commands included; a call that cannot start one in time returns −1002 at once naming the cause.
   The texts state exactly what the code does.
3. **Every text about stalls says what the code does** (the agent case: a transport exists, the
   abort closes it, a late outcome is discarded), in the docstring, AGENTS.md and the seed.
4. **Pin the two surviving rules**: the abort spares an attempt another call joined since, and a
   failed attempt releases its connection.

## Review cycle 3 — approved (2026-10-27)

- **Reviewed commit:** d60302e15c61c93d7b71111162bd9547309b1d79 (the branch with develop `1b8f2b5`
  merged in) · **Pinned:** 4e33639a2bc2b11e00da5e316b9c084d933c50ea, after the out-of-Scope seed
  below · **Mode:** a fresh blind pass over the full spec-excluded diff, debate variant (ship and
  block), each reviewer in its own clone at xhigh.
- **Verdict:** approved. No CONFIRMED and no PLAUSIBLE findings from either reviewer.

### Verification run

- Both clones, after `uv sync --locked`: `uv lock --check` exit 0; `uv run pytest -q` 2080 passed,
  14 skipped; `CLUSTER_MCP_TEST_ERA=modern uv run pytest -q` 2080 passed, 14 skipped;
  `bin/sandbox.sh uv run rcac-mcp --help` exit 0. The 14 skips are the bash ≥ 4.1 rows; no
  reconnect test is skipped (`-rs`).
- Mutants: the branch's 28 cases all killed (block); the 9 reconnect cases killed (ship).
- Real-program drives against the in-process SSH server, no fakes, default window:
  - refused host: 43.0 s, −1002, `cannot connect to <host>: connection refused (…); the command was
    not run`, through the real stdio CLI under `bin/sandbox.sh` (ship) and an in-memory MCP in both
    eras;
  - black-holed host: 45.0 s, −1002, `timed out`, attempts starting at 0.0, 15.6 and 31.6 s, no
    worker left 1 s after;
  - host back within the window: 3.6 s, the same result as a healthy call; the next call after a
    failure: 0.03–0.08 s, exit 0, server process alive;
  - six concurrent calls while down: one reconnect worker at peak, each −1002 at the bound; a DNS
    stall on the worker thread gives one lookup for all calls, and the next call after it reconnects;
  - bound arithmetic against real Fabric: default 45 s, `ConnectTimeout 5` 45 s, `ConnectTimeout 30`
    90 s, `connect_timeout=40` 120 s; with a 6 s window the call gave up at 4.00 s (the 2 s last
    start).
- CI on d60302e (run 40576645120): 2094 passed in each era; the lock audit was red on a dnspython
  advisory published 2026-10-27, outside this cycle. It is fixed on develop by `03437cb` (CI green,
  run 40579454545) and clears when develop is merged in for landing.

### Requirement → evidence

| R | Met | Verified by |
|---|---|---|
| R1 | yes | both: real drives (refused, black-holed) at 43–45 s with −1002; tool rows in both eras; unbounded-poll/-retry mutants killed |
| R2 | yes | both: host-back drive; `…gives_the_same_result[second-attempt\|forty-seconds-in]`; a dropped-final-attempt probe caught |
| R3 | yes | both: next-call drive 0.03–0.08 s; `test_a_failed_reconnect_leaves_the_server_serving`; slot-release probes caught; gives-up-for-good mutant killed |
| R4 | yes | both: run −1002 "not run", sbatch "The job was not submitted", write −1002, put/get "nothing was transferred"; every tool interpolates stderr (grep); sbatch-not-started mutant killed |
| R5 | yes | both: docstring and AGENTS.md footgun state 45 s = 3 × 15 s, the 2 s last start and the ssh_config rule; arithmetic matches real Fabric; `test_reconnect_texts_state_the_bound` |
| R6 | yes | both: 31 new tests, loopback server and fakes only, none skipped in either era; mutants gate not hollow |
| R7 | yes | both: six concurrent calls, one worker; stall drive, one lookup; attempt-per-call mutant killed |

No artifact R-IDs. No scope creep: the `paramiko>=3.2` floor (with its lock), the sacct `whoami`
stop and the moved startup message map to the Clarifications.

### Out of Scope

- **ProxyJump hops are unpinned** (block). Cutting `_links` to the first link survives
  `test_ssh_exec.py`, `test_startup.py` and `test_executors.py` (232 passed); the bound still holds
  under it, and no R-ID asks for hop cleanup. Filed as `issues/ssh-gateway-hops-unpinned.md` with
  its ROADMAP entry (`4e33639`).
- **Staging left after a lost host** (both): reproduced exactly as `issues/ssh-write-staging-leftover.md`
  states, and pre-existing on develop `1b8f2b5`.
- **Half-open link** (block): the seed's Paramiko citations hold on 5.0.0; its SFTP-open wording now
  names `transport.open_sftp_client()` (`4e33639`).
- `SSHExecutor.__enter__` opens on the caller's thread, outside the one-attempt slot (ship); no
  caller in `src/` uses it as a context manager. Hardening only, not filed.

## Human-gate triggers — cycle 3

- The diff touches `executor/ssh.py` (high-blast-radius, coupled core) and amends § Invariants §2's
  text (staging can remain when the host is lost after staging; pre-existing, seeded). The foreman
  holds the gate under decision `2026-10-16-cluster-mcp-autonomous`: with cycles 1–2's findings
  fixed and cycle 3 clean, **signed off by the foreman, 2026-10-27**.
