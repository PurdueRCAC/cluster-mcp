---
slug: ssh-reconnect-loop
title: A lost SSH connection fails a call within a bound, never hangs it
kind: fix
appetite: small
status: done
branch: fix/ssh-reconnect-loop
base: develop
current_phase: done
last_updated: '2026-10-27'
phases:
- id: P1
  name: 'Executor: a reconnect that ends within the bound, reported as not run'
  status: done
  satisfies:
  - R1
  - R4
  - R5
  - R6
  - R7
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/ssh-reconnect-loop/verify/gate.sh P1 && sh spec/ssh-reconnect-loop/remediation/F2-abort-recheck.sh && sh spec/ssh-reconnect-loop/remediation/F4-unpinned-lines.sh && sh spec/ssh-reconnect-loop/remediation/F6-last-start.sh && sh spec/ssh-reconnect-loop/remediation/F8-surviving-rules.sh
- id: P2
  name: 'Recovery and callers: the host returns, every tool reports it, in both eras'
  status: done
  satisfies:
  - R1
  - R2
  - R3
  - R4
  - R6
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/ssh-reconnect-loop/remediation/M1-merge-develop.sh P2 && sh spec/ssh-reconnect-loop/remediation/F1-auth-cause.sh && sh spec/ssh-reconnect-loop/remediation/F5-dependency-floor.sh
- id: P3
  name: Full gate and the deferral ledger
  status: done
  satisfies:
  - R6
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv lock --check && uv run pytest -q && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q && sh spec/ssh-reconnect-loop/remediation/M1-merge-develop.sh mutants && test -f issues/ssh-half-open-link.md && grep -q 'issues/ssh-half-open-link.md' ROADMAP.md && bin/sandbox.sh uv run rcac-mcp --help && sh spec/ssh-reconnect-loop/remediation/F3-write-texts.sh && sh spec/ssh-reconnect-loop/remediation/F7-stall-texts.sh
review:
  last_reviewed_commit: 4e33639a2bc2b11e00da5e316b9c084d933c50ea
  verdict: approved
  blocked_reason: ''
  cycle: 3
---

# TECH.md — A lost SSH connection fails a call within a bound, never hangs it

The **context engine and finite-state machine** for building this fix. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/ssh-reconnect-loop/TECH.md`); the per-phase
checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** [`research/00-digest.md`](research/00-digest.md) + briefs.
- **Gate:** [`verify/gate.sh`](verify/gate.sh). Each phase's mode runs named test ids in both eras,
  then that phase's mutation cases and the sandboxed CLI drive. `tests` and `mutants` are the
  parts on their own.

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

---

## Phase P1 — Executor: a reconnect that ends within the bound, reported as not run
**Satisfies:** R1, R4, R5, R6, R7 · **Depends on:** —
**Goal:** `SSHExecutor` gives up a reconnect within three times the connect bound of the call's
start.
- On giving up, `run` and `write` return −1002 with `cannot connect to <host>: <cause>`, and `put`
  and `get` raise that message.
- A connection is published only once it has opened, under a lock.
- At most one connect attempt is in flight at a time, and a call that arrives during one joins it
  under its own deadline (R7).
- Unit rows pin it under an injected clock and real-Fabric construction, and the texts state the
  bound.

- [x] **Move the message helper.** `connect_failure_message` and its helpers (`_chain`, `_refused`,
      `_cause_class`, `_detail`, `CHAIN_DEPTH`) move from `startup.py` into `executor/ssh.py`.
      `startup.py` and `__init__.py` import them from there. The text is unchanged (PLAN §2.1).
- [x] **Add the new pieces.** `RECONNECT_FACTOR`, `ATTEMPT_POLL`, `FINAL_ATTEMPT_LEAD`,
      `self._lock`, `self._window`, `self._inflight`, `_bound`, `_new`, `_attempt`, `_release` (the client and the
      gateway chain, outside the lock), `_publish` (returns a transport, refreshes `_window`),
      `_Pending` and `_await`.
  - `open()` runs one `_new()` + `open()` on the calling thread and publishes it.
  - Its startup behaviour and exception are unchanged.
- [x] **Rewrite `_ensure_connected(deadline)`** exactly as PLAN §2.1 says:
  - The fast path returns the transport it captured.
  - `_new()` and `open()` run only on the worker, never on the calling thread.
  - The wait goes through `_await`, every `ATTEMPT_POLL`.
  - One attempt in flight (R7): under the lock, a call joins `self._inflight` (`waiters += 1`), or
    starts the attempt if there is none.
  - The worker owns its outcome. Under the lock it publishes a success (even with no waiter left)
    or records a failure, then clears `self._inflight` and sets `done`.
  - At its own deadline a call leaves (`waiters -= 1`). The last to leave closes
    `client.get_transport()` and the gateway chain, outside the lock. The slot stays occupied until
    the worker ends.
  - The worker catches `except Exception`. A `BaseException` outcome is re-raised by every waiter.
  - `AuthenticationException` gives up at once.
  - Backoff is capped so the last attempt starts at least `FINAL_ATTEMPT_LEAD` before the deadline.
  - The clock is read only as `time.monotonic` and `time.sleep`.
  - It returns the message on giving up.
- [x] **Callers.** Every public method takes `deadline = time.monotonic() + self._window` at entry.
  - `run` wraps `_run(…, deadline)` and returns the −1002 `CommandResult` directly, never through
    `launch.separate`.
  - `write` returns −1002 on a failed first connect and passes its deadline to the inner `_run`
    calls.
  - `_reason` treats −1002 as "no reason".
  - `put` and `get` raise a one-argument `ConnectionError(f'{message}; nothing was transferred')`.
- [x] **Texts** (PLAN §2.3):
  - The bound statement goes in word for word, in the `SSHExecutor` docstring and in AGENTS.md's
    `executor/ssh.py` footgun entry, replacing "reconnect backoff (… never gives up …)".
  - AGENTS.md §3's −1002 bullet gains the reconnect cause and its stderr. The foreman approved
    this at the gate, 2026-10-23 (PLAN deviation table, row 1).
  - AGENTS.md's repository-map rows for `startup.py` and `executor/ssh.py`.
  - `base.py`'s −1002 comment and `Executor.run` Returns, and `put`/`get` `Raises: ConnectionError`.
  - `ssh.py`'s module, constants and method docstrings.
  - The statement reads per executor call, as GOAL Q6 rules.
- [x] **Tests** (`tests/test_ssh_exec.py`, a new "A reconnect" section next to "A lost
      connection", marker `unit`). PLAN §2.4 and §6 describe the harness; each row the gate names
      is built here.
  - **`FakeClock`**: real time plus an offset, with short sleeps passed through and an `_await`
    stand-in that advances the clock. `Runaway(BaseException)` fires past 2 × the bound, only on
    the test thread.
  - **A scripted fake `Connection`**: `'ok'`, `(spent, exc)` or `'hang'`. Rows start from a dead
    published connection.
  - **Real `_new()` rows**, needing no socket:
    - `_bound` from ssh_config `ConnectTimeout 30`, and from `connect_kwargs` `timeout` 30;
    - `CanonicalizeHostname` with `socket.gethostbyname` patched to block.
  - **`test_concurrent_calls_during_a_stall_start_one_attempt`** (R7): K calls during a `'hang'`
    and during a real `_new()` blocked in canonicalisation each give −1002 at their own bound, and
    `_new` runs once. A call after they have all left joins the same attempt.
  - **What every row asserts**: `guard.refused == []`. Every R1 row also asserts −1002, never
    −1003, and fake elapsed time no more than the bound.
  - **`test_reconnect_texts_state_the_bound`** pins R5's two texts and the old text's absence.
- [x] **Mutants** (`tests/mutants.py`):
  - New cases. Each targets an executor-level row, and its `why` is the row's failure text:
    - `ssh-reconnect-unbounded-poll`;
    - `ssh-reconnect-unbounded-retry`;
    - `ssh-reconnect-reads-as-lost`;
    - `ssh-reconnect-retries-refused-auth`;
    - `ssh-reconnect-late-success-leaks`;
    - `ssh-reconnect-attempt-per-call` (R7: each call starts its own attempt; target: the
      one-attempt row).
  - Re-plants, each named in the commit body:
    - `startup-host-unnamed`, on the helper's new home;
    - `startup-no-connect-timeout`, on `_new`'s `Connection(...)` line;
    - `staged-checksum-unchecked`, on write's place step, now a `_run` call;
    - `transfer-cause-unnamed`, on the `_reason` call.
  - Update the § Testing rows for all of them.
- **Amendment (build, 2026-10-23).** The design is PLAN §2.1's; three helpers carry it that the
  list above does not name. `_settle(pending)` is the worker's body (it runs `_attempt`, then
  publishes or records under the lock); `_leave(pending)` is a call's exit at its deadline (the
  last to leave runs `_abort`); `_live(conn)` reads a published transport. `_publish` runs with
  the lock held and returns the transport and the connection to release once the lock is let go.
  `_attempt` takes the `_Pending` so it can set `pending.conn`. The existing unit row
  `test_an_oversize_program_is_refused_before_connecting` builds a bare executor, so it now sets
  `_window` too, and its `_ensure_connected` stand-in takes the deadline.
- **Verify:** `sh spec/ssh-reconnect-loop/verify/gate.sh P1`.
- **Touches:** `src/rcac_mcp/executor/ssh.py`, `src/rcac_mcp/executor/base.py` (docstrings),
  `src/rcac_mcp/startup.py`, `src/rcac_mcp/__init__.py` (import), `tests/test_ssh_exec.py`,
  `tests/mutants.py`, `AGENTS.md`.

## Phase P2 — Recovery and callers: the host returns, every tool reports it, in both eras
**Satisfies:** R1, R2, R3, R4, R6 · **Depends on:** P1
**Goal:** Pin, against the in-process SSH server, that a host which comes back is used and that the
server keeps serving after a failure. Every tool's failed reconnect reads as "not run" and spends
one window per executor call, in both protocol eras.

- [x] **`tests/ssh_server.py`.** Two new methods on `LoopbackSSH`:
  - `refuse()` closes the listener **and** `_drop()`s every server transport;
  - `serve_again()` rebinds the same port with `SO_REUSEADDR` and restarts the accept thread.

  Update its docstring and the § Testing row.
- [x] **`tools/slurm.py`.**
  - `sbatch` maps −1002 to `The job was not submitted: {stderr}` on both paths: the `run(argv)`
    branch beside −1003, and the `script_content` path's `write`.
  - `sacct` checks `whoami`'s exit, and on failure raises `Failed to get the current user: {stderr}`.
- [x] **`resources.py` `load_cluster_context`.** Any −1002, from the listing or from a `cat`, stops
      the load and returns `''` without caching. §8's path, glob, order and headers are unchanged.
- [x] **Tests** (`tests/test_ssh_exec.py`). Integration rows wait for the client's transport to
      read inactive before calling.
  - **R2** (integration): `refuse()`, then a counting `Connection` subclass calls `serve_again()`.
    Parametrised on the second attempt and on an attempt 40 s into the window. Each gives the
    baseline's result, a second accept and a new `_conn`.
  - **R3** (integration): one `in_memory` session. Call 1 gives −1002 within the fake bound, then
    `serve_again()`, then call 2 succeeds on the same server object.
  - **Abandonment** (integration): a silent accept-and-hold listener, with `ssh.CONNECT_TIMEOUT`
    patched to 1 before the executor is built, and `banner_timeout=30`. The call returns within
    about 3.5 s real, and the worker exits within 1 s more.
  - **Tool rows** (unit, through `_tool` in the selected era, under a real-time watchdog):
    - `run_command`;
    - `sbatch` on `script_path` and on `script_content`: not submitted, never "may have been
      submitted";
    - `write_file`, `upload_file` and `download_file`, each carrying `cannot connect to <host>`;
    - `sacct`, whose failed `whoami` spends one window.
  - **The context cache** isn't filled on −1002, from the listing or from a `cat`.
- [x] **Mutants**, each targeting the row above that it should turn red; update the § Testing rows:
  - `ssh-reconnect-gives-up-for-good`;
  - `sbatch-not-started-reads-as-failed`;
  - `sacct-whoami-unchecked`;
  - `context-caches-not-started`.
- **Amendment (build, 2026-10-26).**
  - **The abandonment row restores `CONNECT_TIMEOUT` once the executor is built.** The patch to 1
    gives the 3 s window. A reconnect attempt built under it would get a 1 s handshake bound too:
    Fabric passes the connect timeout to `start_client`, which gives up at it (research 01 §1). That
    attempt would fail on its own at 1 s, and nothing would be abandoned. Under the restored 15 s
    the attempt waits on the silent host past the window, so the row pins that the call's give-up
    closes `client.get_transport()`. Closing `conn.transport` instead was run once and turned it red.
  - **`LoopbackSSH` carries the two methods on three helpers.** `_listen` (bind, `SO_REUSEADDR`, start
    the accept thread), `_stop_listening` (shut down, close, join; `close()` uses it too) and
    `_accept(listener)`, so a stopped accept thread never reads the new listener.
  - **`not_run_violations` takes `host` and `slack`.** The real-handshake row names `127.0.0.1` and
    allows 0.5 s of real lateness.
  - Tool and context rows measure the fake seconds a call spent (`clock.offset`), so the in-memory
    session's own real time is not charged to the reconnect.
- **Amendment (develop merge, 2026-10-26; foreman's ruling).** Merging `origin/develop` before the
  final review brought `agents-d-instructions` (`09ce3af`), which deleted `load_cluster_context`, its
  process-global cache and `get_cached_context`/`clear_context_cache`. The site context is now read
  once at startup (`site.py`), and `cluster_context` and `rcac://context` serve that text and run
  nothing. A `-1002` can no longer reach the context, so the guard above (R3: a not-started read is
  never cached as the context) is met by construction, and the merge takes develop's `resources.py`
  without it.
  - **Retired:** the row `test_a_reconnect_failure_is_never_cached_as_cluster_context[listing|cat]`
    with its `AnsweredFirst` and `CONTEXT_ANSWERS` helpers, and the mutant `context-caches-not-started`
    (its anchors were the guard's two lines, now gone).
  - **Kept, against the new code:** `test_a_reconnect_failure_never_changes_the_cluster_context`
    (unit, both eras): in one session on a server built with a two-file site, `cluster_context` and
    `rcac://context` return the startup text before and after a `run_command` whose reconnect gives
    up with `-1002`, and neither starts a connect attempt. The mutant
    `context-served-from-a-failed-read` (the tool answering from a read through the executor) turns
    it red with `not the startup read`. AGENTS.md § Testing's reconnect row names both.
  - **Gate.** `verify/` is frozen (code-build Step 1.3) and `gate.sh` still names the retired row and
    mutant in `P2_IDS` and `P2_MUTANTS`, so its `P2`, `tests` and `mutants` modes can no longer pass.
    `remediation/M1-merge-develop.sh <mode>` runs a copy of the frozen gate with exactly those two
    names rewritten to their successors, and fails if either name has left the gate. P2's `verify:`
    runs it in place of `gate.sh P2`; P3's runs `M1-merge-develop.sh mutants` in place of
    `gate.sh mutants`. P1's gate names neither and is unchanged.
- **Verify:** `sh spec/ssh-reconnect-loop/verify/gate.sh P2`.
- **Touches:** `tests/ssh_server.py`, `src/rcac_mcp/tools/slurm.py`, `src/rcac_mcp/resources.py`,
  `tests/test_ssh_exec.py`, `tests/mutants.py`, `AGENTS.md` (§ Testing).

## Phase P3 — Full gate and the deferral ledger
**Satisfies:** R6 · **Depends on:** P2
**Goal:** The profile's full `verify` in both eras, the cycle's mutation cases with the runner's
self-check, and every deferral recorded where `AGENTS.md` § Factory says.

- [x] Run the profile's full `verify`, which runs both eras. R6 requires the new rows to run there:
      confirm each id in `verify/gate.sh` ran in both era runs, and none was skipped.
- [x] Run `sh spec/ssh-reconnect-loop/verify/gate.sh mutants` (with `--self-check`). Every case is
      caught.
- [x] **Deferral ledger.**
  - Walk P1, P2, PLAN §5 and the review findings for "not fixed here", "known limitation",
    "left as a follow-up", "seed" or "deferred". Each must have an `issues/` file and a
    `ROADMAP.md` entry.
  - Known so far: the half-open link (Q5), already filed at plan time as
    `issues/ssh-half-open-link.md` with its ROADMAP entry. The gate's `test -f` and `grep -q`
    check both.
  - A new deferral found in build gets its seed and entry here, or goes to the security lane
    (`AGENTS.md` § Factory → Where deferred work goes) if it describes an unremediated weakness.
  - Result (build, 2026-10-26): the half-open link is the one seed, already filed. The
    `Thread.start()` gap P2 found is fixed under the amendment below, not deferred. No new seed
    went into `issues/`.
- [x] Confirm `issues/ssh-reconnect-loop.md` still reads `status: adopted:ssh-reconnect-loop`
      (`code-roadmap` retires it after landing, not this cycle).
- **Amendment (build, 2026-10-26; foreman ruling, scoped edit to `executor/ssh.py`).** P2 found that
  a reconnect worker whose `Thread.start()` raises left `self._inflight` set for good: every later
  call joined an attempt that never ran and failed at its own deadline, until restart. The foreman
  signed off on a fix scoped to that gap, and it is fixed here, not deferred:
  - `_ensure_connected`: if the worker fails to start, the slot is freed under the lock, the
    attempt records the failure and sets `done` (so any joined waiter gets the same outcome), and
    the call gives up at once with `cannot connect to <host>: <cause>`, which `run` reports as
    −1002 in the form R1 and R4 give. A `BaseException` is re-raised after the slot is freed. The
    next call starts a fresh attempt. The method docstring says so.
  - **Test** (`integration`): `test_a_reconnect_worker_that_cannot_start_frees_the_attempt` patches
    `threading.Thread.start` to refuse the first `cluster-mcp-reconnect` worker. Through
    `run_command` in the selected era, against `LoopbackSSH` under the fake clock: the call gives
    −1002 naming the host and the cause at once, the slot is free, and the next call starts one new
    worker and runs on a second accepted connection. It runs in both eras' full-suite runs.
  - **Mutant** `ssh-reconnect-unstarted-worker-holds-slot` leaves the slot set; the test kills it
    (`stayed taken`).
  - `verify/gate.sh` carries the id and the case in its `tests` and `mutants` modes, so P3's gate
    runs the case; P1's and P2's modes are unchanged. AGENTS.md's `executor/ssh.py` footgun gains
    one clause and § Testing the row and the case.
- **Verify:** `uv lock --check && uv run pytest -q && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q && sh spec/ssh-reconnect-loop/verify/gate.sh mutants && test -f issues/ssh-half-open-link.md && grep -q 'issues/ssh-half-open-link.md' ROADMAP.md && bin/sandbox.sh uv run rcac-mcp --help`.
- **Touches:** `issues/`, `ROADMAP.md` (only for a deferral found in build); under the amendment,
  `src/rcac_mcp/executor/ssh.py`, `tests/test_ssh_exec.py`, `tests/mutants.py`, `verify/gate.sh`,
  `AGENTS.md`.

## Remediation — review cycle 1 (build, 2026-10-26)

`REVIEW.md` cycle 1 returned changes-requested with four classes, routed by the foreman, who holds
the human gate for `executor/ssh.py` under the autonomy decision and signed off on edits within
them. P1, P2 and P3 are reopened together and land in **one commit**: the classes share
`executor/ssh.py`, `tests/test_ssh_exec.py`, `tests/mutants.py` and `AGENTS.md`, and class 3's seed
must ride in the same commit as its texts (the foreman's ruling). `verify/` stays frozen; each
class's checker is `remediation/F<n>-*.sh`, run after the phase's frozen gate: P1 runs F2 and F4,
P2 runs F1, P3 runs F3 after its full gate.

- [x] **F1, only a refusal ends the reconnect at once** (P2; R1, R2, R5). `_auth_ending` reads an
      `AuthenticationException` by its cause: Paramiko's `transport shut down or saw EOF`
      (`AUTH_CLOSED`) and `Authentication timeout.` (`AUTH_TIMED_OUT`) are no refusal; anything
      else is the server's answer. Only `refused` gives up at once. `connect_failure_message` names
      `connection closed during authentication` (without Paramiko's "Authentication failed" text)
      and `timed out`. A call that waited on an aborted attempt (`_Pending.aborted`) starts or joins
      a fresh one at once, with no backoff, while one can still start in time.
  - Rows: `RECONNECT_FAILURES[auth-closed|auth-timed-out]` (unit), `test_startup.py` `CAUSES`
    (`authentication-closed`, `-timeout`, `-type`), `test_an_authentication_cut_short_is_retried
    [closed|timed-out]` and `test_a_call_never_inherits_an_aborted_attempt` (loopback server).
  - Mutants: `ssh-reconnect-auth-class-not-cause` (collapsed back to the class),
    `ssh-reconnect-joiner-inherits-abort`; `ssh-reconnect-retries-refused-auth` re-planted on the
    new line.
  - Texts: the `SSHExecutor` docstring, the AGENTS.md footgun and `RECONNECT_BOUND_TEXT` state what
    a refused authentication is. Sweep sites added past the named ones: `connect_failure_message`'s
    docstring, `README.md`'s cause list and AGENTS.md § Testing's startup row (the classes they
    list).
- [x] **F2, an abort never closes a published connection** (P1; R4, R7). `_abort` is now the
      executor's: it takes the decision again under the lock as it acts (an attempt whose outcome
      has come, or that a call has joined since, is left alone), marks an attempt with transports
      to close `aborted`, and closes them outside the lock; `_settle` never publishes an aborted
      attempt. `_transports` replaces the module-level `_abort`.
  - Row: `test_an_abort_and_a_publish_never_cross[published-first|opened-first]`, a hook at the
    seam each way round, no timing race.
  - Mutants: `ssh-reconnect-abort-unchecked`, `ssh-reconnect-publishes-aborted`;
    `ssh-reconnect-late-success-leaks` re-planted on the re-indented publish line.
- [x] **F3, a write's texts say what it leaves** (P3; R4). `SSHExecutor.write`, AGENTS.md § Invariants
      §2 (foreman's sign-off) and the `executor/ssh.py` footgun say the staging can remain when the
      host is lost after staging. Sweep site added: `Executor.write`'s docstring in
      `executor/base.py` (human-gated; the same claim, within the class). The cleanup is filed as
      `issues/ssh-write-staging-leftover.md` (`lane: public`) with its `ROADMAP.md` entry.
- [x] **F4, the four unpinned lines** (P1; R6, R7). Each has a row and a mutant:
  - `_leave`'s done-check: `test_a_call_at_its_deadline_takes_an_outcome_that_has_come`,
    `ssh-reconnect-leave-ignores-outcome`;
  - `_publish`'s live branch is reachable (`open()` publishes while an attempt runs), so it stays:
    `test_a_reconnect_keeps_a_connection_published_meanwhile`, `ssh-reconnect-publish-replaces-live`;
  - the bound's floor: `test_a_reconnect_bound_never_falls_below_the_default[ssh-config|
    connect-kwargs|connect-timeout]`, `ssh-reconnect-bound-unfloored`;
  - `write`'s shared deadline: `test_a_write_spends_one_reconnect_window[parent|place|probe]`, one
    mutant per command (`ssh-write-parent-own-deadline`, `-place-own-deadline`,
    `-probe-own-deadline`).
- AGENTS.md § Testing gains every row and case above.
- Result (build, 2026-10-26): P1's gate with F2 and F4, P2's with F1, and P3's (the full suite,
  1788 passed per era, none skipped; `gate.sh mutants` with its self-check) with F3, all green; the
  review's probes reproduce no finding.

## Remediation — review cycle 2 (build, 2026-10-26)

`REVIEW.md` cycle 2 returned changes-requested with four classes, routed by the foreman, who holds
the human gate for `executor/ssh.py` and signed off on edits within them, `pyproject.toml`'s
dependency floor included (class 1). P1, P2 and P3 are reopened together and land in **one
commit**, as in cycle 1: the classes share `executor/ssh.py`, `tests/test_ssh_exec.py`,
`tests/mutants.py` and `AGENTS.md`, and a dependency change lands with its `uv lock` (§ Conventions).
`verify/` stays frozen; each class's checker is `remediation/F<n>-*.sh`, numbered on from cycle 1's,
run after the phase's frozen gate and cycle 1's checkers: P1 adds F6 and F8, P2 adds F5, P3 adds F7.

- [x] **F5, the declared dependency range is the range the behaviour holds on** (P2; R1, R2, R5).
      Paramiko 3.2 is the oldest that names a link closed during authentication apart from a
      refusal and has `AuthFailure` (3.1.0 and 3.2.0 checked in scratch environments), so the floor
      is raised rather than the text reading replaced: `paramiko>=3.2` is a direct dependency with
      its reason, `uv lock` adds it with no locked version moved, and `PARAMIKO_FLOOR` in `ssh.py`
      is the classifier's own statement of it. `_auth_ending` classifies every subclass by cause:
      `BadAuthenticationType`, `PartialAuthentication` and `PasswordRequiredException` are refusals
      (`REFUSALS`); an `AuthFailure` is decided by `_auth_cause`, a refusal only when every source
      was refused, otherwise as its first non-refused source (which may be no authentication
      failure at all, such as a lost agent: retried, and named for it).
  - Rows: `test_the_declared_paramiko_floor_matches_the_classifier` (the floor read from
    `pyproject.toml` against `PARAMIKO_FLOOR`, and the installed Paramiko still raising both texts),
    `test_every_refusal_ends_the_reconnect_at_once[bad-type|partial|password-required|auth-failure]`,
    `RECONNECT_FAILURES[auth-failure-closed|auth-failure-agent]`, and five `test_startup.py`
    `CAUSES` rows.
  - Mutants: `ssh-auth-strategy-read-as-refusal`, `ssh-auth-subclass-not-refusal`,
    `ssh-paramiko-floor-disagrees`.
- [x] **F6, no connect attempt starts after the stated last start** (P1; R1, R5, R7). At the top of
      `_ensure_connected`'s loop a call that has not just slept a backoff (which ends no later than
      its last start) and is at or past its last start starts and joins nothing and gives up at
      once, naming `timed out` or the last cause seen; the aborted path's own check folds into it.
      Texts: the `SSHExecutor` docstring, the footgun and `RECONNECT_BOUND_TEXT` say a call starts or
      joins no attempt later than 2 s before its deadline and that a `write`'s later command past it
      gives up at once; `FINAL_ATTEMPT_LEAD`'s comment and `_ensure_connected`'s docstring match.
  - Rows: `test_a_call_past_its_last_start_starts_no_attempt[none-in-flight|one-in-flight]` (unit),
    `test_a_write_command_past_its_last_start_starts_no_attempt` (loopback, late_write's shape).
  - Mutant: `ssh-reconnect-starts-past-last-start`; `ssh-reconnect-joiner-inherits-abort`
    re-planted on the aborted path's new `continue`.
- [x] **F7, every text about stalls says what the code does** (P3; R5, R7). `_abort`'s docstring
      and the footgun: a step before the transport exists has nothing to close and its late success
      is published; an SSH-agent query has its transport closed, runs on until the agent answers,
      and its late outcome is discarded. `issues/ssh-reconnect-stuck-step.md` and its `ROADMAP.md`
      entry (both filed this cycle) get the corrected sentence and a dated correction. Sweep sites
      past the named ones: the test module's docstring and AGENTS.md § Testing's reconnect rows
      (`an attempt that hangs before it has a transport`).
- [x] **F8, the two surviving rules** (P1; R6, R7). Each has a row and a mutant:
  - the abort spares an attempt another call joined since:
    `test_an_abort_spares_an_attempt_another_call_joined_since` (a `shake` step whose transport
    exists while it waits; the joining call enters at the seam before the abort acts),
    `ssh-reconnect-abort-spares-no-joiner`;
  - a failed attempt releases its connection: `test_a_failed_attempt_releases_its_connection`
    (loopback, an authentication held past a 1 s auth timeout, leak.py's shape),
    `ssh-reconnect-failed-attempt-unreleased`.
- AGENTS.md § Testing gains every row and case above, and its startup row the new causes.
- Result (build, 2026-10-26): P1's gate with F2, F4, F6 and F8, P2's with F1 and F5, and P3's (the
  full suite, 1811 passed per era, none skipped; `gate.sh mutants` with its self-check) with F3 and
  F7, all green; the seven new and re-planted cases are killed. Of the review's probes,
  `late_write.py` now starts no attempt and gives `timed out` at once; `agent_stall.py` and
  `leak.py` show what the corrected texts and the new row state. `bin/audit_lock.py` is red on
  `fastmcp` 4.1.0, the cycle base's locked version (fixed in 4.1.2; develop already carries 4.1.4),
  not on anything this remediation locks.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[fix]` commit; stop and report.
