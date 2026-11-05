---
slug: ssh-half-open-link
title: A dead SSH link that still reads as connected is noticed within a bound
kind: fix
appetite: small
status: in_progress
branch: fix/ssh-half-open-link
base: develop
current_phase: P2
last_updated: '2026-11-05'
phases:
- id: P1
  name: 'Commands: the liveness monitor, the open-retry, the stall proxy and the documents'
  status: done
  satisfies:
  - R1
  - R3
  - R4
  - R5
  - R6
  - R7
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: uv run pytest -q tests/test_ssh_liveness.py tests/test_ssh_exec.py tests/test_executors.py tests/test_mutations.py tests/test_hygiene.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_liveness.py && uv run python -I spec/ssh-half-open-link/remediation/open-timeout-gate.py commands both
- id: P2
  name: 'Transfers: the bounded SFTP open, TransferLost, the write path, and the documents'
  status: pending
  satisfies:
  - R1
  - R2
  - R4
  - R5
  - R6
  - R7
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv run pytest -q tests/test_ssh_liveness.py tests/test_ssh_exec.py tests/test_writes.py tests/test_sbatch.py tests/test_mutations.py tests/test_hygiene.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_liveness.py && uv run python -I spec/ssh-half-open-link/verify/silent-gate.py transfers both
- id: P3
  name: The mutation sweep, every tool in both eras, and the deferral ledger
  status: pending
  satisfies:
  - R1
  - R2
  - R3
  - R4
  - R5
  - R7
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv run python -I spec/ssh-half-open-link/verify/silent-sweep.py legacy 1 && uv run python -I spec/ssh-half-open-link/verify/silent-sweep.py legacy 2 && uv run python -I spec/ssh-half-open-link/verify/silent-sweep.py modern 1 && uv run python -I spec/ssh-half-open-link/verify/silent-sweep.py modern 2 && CLUSTER_MCP_TEST_EVERY_KIND=1 uv run python -I spec/ssh-half-open-link/remediation/open-timeout-gate.py all both && uv run python -I spec/ssh-half-open-link/verify/ledger-check.py
review:
  last_reviewed_commit: ''
  verdict: none
  blocked_reason: ''
  cycle: 0
---

# TECH.md — A dead SSH link that still reads as connected is noticed within a bound

The **context engine and finite-state machine** for building this fix. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/ssh-half-open-link/TECH.md`); the per-phase
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

Cycle-specific:

- **Touches the coupled core and a high-blast-radius path** (`core/executor/ssh.py`): every phase is
  `parallel: false`, `hammerable: false`.
- **R6 rides with the code.** P1 and P2 each change `AGENTS.md` (the `executor/ssh.py` footgun, §2,
  §3, § Testing), `README.md` and the docstrings for what they deliver, in the phase's one commit
  (PLAN §2.3). A phase whose documents lag its code is red at review.
- **Row names are the gates' interface.** `silent-gate.py` names each row by id (PLAN §6). A renamed
  or re-parametrized row changes the gate in the same commit.
- **`tests/test_ssh_exec.py` names nothing at import that develop (`13c0e83`) lacks.**
  `silent-gate.py` runs it against develop's `packages/`, and a collection error there would make
  every row fail for the wrong reason. The names the fix adds (`_Liveness`, `_verdict`,
  `TransferLost`, `PROBE_REQUEST`, `_liveness_clock`) are used in `tests/test_ssh_liveness.py`,
  or inside a row's body only where the row cannot reach them on develop. `SilentLink` lives in
  `tests/ssh_server.py`, which the gate copies from this tree.
- **Every silent row:**
  - `integration`, with `CONNECT_TIMEOUT` patched to 2 (B = 2 s, the bound 6 s; at 1 no reconnect
    can start after a verdict, PLAN §4.1 finding 1);
  - the call on a thread under a watchdog: its figure plus 1.0 s from `go_silent` returning (B + 1 s
    for a call's start, 3B + 1 s in flight; the verdict's exact values are the unit rows'). The
    watchdog fails with `still waiting <t> s after the link went silent`, adding `at <step>` for a
    row that goes silent at a server hook's step. It says so only while the call's thread is alive;
    otherwise the thread's own exception is re-raised. Then it releases the call by `link.close()`;
  - a row that goes silent mid-transfer does it from a server hook on a protocol event, never at a
    byte count;
  - the `later-timeout` row's timeout outlasts its watchdog, so develop hangs rather than timing
    out; the measured times in every violation; 2.0 s for any thread to end; a
  `threading.excepthook` fixture that fails the row on a monitor or sender thread's exception
  (thread exceptions are only warnings in this suite). A row that calls a tool requests `executes`.
- **The monitor never reads `ssh.time` or `_await`**, and its threads are never named
  `cluster-mcp-reconnect`: the fake-clock rows patch the first and wait on the second.
- **Gate scripts** in `spec/ssh-half-open-link/verify/` run with `uv run python -I`, are named after
  what they check (never a Python module's name), copy `os.environ` before clearing anything, run
  one pytest child at a time in its own process group, kill it on exit and assert with `pgrep` that
  nothing of theirs is left, and state their footprint. `tests/mutants.py` is the repo's own runner.
- **Measured times** (plan session, macOS, load 3–9), with projections at B = 2: `tests/test_ssh_exec.py` 131 s legacy and
  146 s modern (research 03 §4); `test_mutations.py` 13 s; `test_hygiene.py` 2 s;
  `test_writes.py` 12 s; `test_sbatch.py` 8 s; `test_executors.py` 10 s; `silent-gate.py`'s
  develop copy and sync 5.2 s (dry run). A mutant child took 3.2–3.7 s on a fake-clock target, plus
  the row's real time on a loopback one. Projected, from research 03's row times:
  - **P1** ≈ 8 min: the files ≈ 4 min with the new rows, and `silent-gate.py commands both`
    ≈ 2.5 min per era (18 rows here; develop's failing in-flight rows each wait out a 7 s
    watchdog, its call-start rows a 3 s one).
  - **P2** ≈ 9 min.
  - **P3** ≈ 15 min: four sweep halves ≈ 2.5 min each, and the every-tool gate ≈ 3 min per era.

  The suite grows ≈ +150 s per era (≈ 25%; PLAN §6). Gates longer than the 10-minute
  command cap run in the background, and build waits on them.
- **Deferrals in this cycle** go to `issues/ssh-liveness-message-gap.md` (filed with the plan: R4's
  floor, PLAN §3 Deviation 3, as amended at sign-off) and its `ROADMAP.md` entry. Each of these gets a dated, append-only
  note on its existing seed and entry:
  - the ProxyJump close order unmeasured: `issues/ssh-gateway-hops-unpinned.md`;
  - the staging left on a cut write: `issues/ssh-write-staging-leftover.md`;
  - the open-retry covering a reset: `issues/ssh-open-session-reset-raises.md`;
  - a load sighting: `issues/stalled-reconnect-test-timing.md`.

  Anything else deferred gets its own seed and entry, never `spec/`.

---

## Phase P1 — Commands: the liveness monitor, the open-retry, the stall proxy and the documents
**Satisfies:** R1, R3, R4, R5, R6, R7 (for `run` and every tool built on it) · **Depends on:** —
**Goal:** a call through `run` that meets a silent link reconnects or fails as a failed reconnect
does, a command running as the link goes silent ends as −1003 within the bound, and a quiet or
slow live link is never cut, each pinned through a stall proxy in both eras and shown to fail on
develop.

- [x] **`SilentLink`** in `tests/ssh_server.py` (PLAN §2.4):
  - `go_silent()` holds both directions and new connections, closing nothing;
  - `come_back()` (new connections), `resume()` (the held pairs), `rate=`, `forwarded`, `held`,
    `silent_after_handshake`, the step hooks, `close()`, `executor()`;
  - the 16 KiB receive buffer on accepted sockets;
  - the rebind away from 54001–54005.

  Its module docstring and AGENTS § Testing's `test_ssh_exec.py` entry describe it.
- [x] **`_Liveness`** in `core/executor/ssh.py` (PLAN §2.1):
  - the `read_message` instance hook;
  - the priming probe, never judged;
  - the pure `_verdict`, split: a poke's verdict at B, a background probe's at
    `2B − VERDICT_MARGIN` (`VERDICT_MARGIN = 1.0`), a call starting while one is out judged B after
    its poke (PLAN §2.1, §4.2);
  - the judge thread (`cluster-mcp-liveness`, `LIVENESS_TICK`, no transport lock) and the sender
    thread (`cluster-mcp-probe`, `PROBE_REQUEST` with want_reply true through
    `_send_user_message`, errors swallowed, one send in flight, `out` stamped at hand-over);
  - `_liveness_clock`;
  - the close of `_transports(conn)`, outermost hop first;
  - only a Paramiko `Transport` is watched.

  Wire it to `_publish` (made under the lock, started after) and to `close()`. The old monitor
  stops with the connection it watched.
- [x] **The poke** on `_ensure_connected`'s fast path, on the monitor of the transport the call
  captured.
- [x] **`_exec`'s open guarded:**
  - a loss (the monitor `dead`, or the transport inactive after `SETTLE`) goes back to
    `_ensure_connected` with the same deadline, and the deadline ends it as the reconnect's −1002;
  - a live failure is raised as today;
  - the open waits `max(OPEN_TIMEOUT, B + 1)`;
  - nothing changes from the exec request on.
- [x] **Rows** in `tests/test_ssh_exec.py`, in a new section after "A host that goes down and comes
  back" (PLAN §6's table; P1's shapes):
  - `test_a_call_on_a_silent_link_reconnects[run|run_command]`: a new connection accepted after the
    call began and within B + 1 s of it;
  - `test_a_call_on_a_silent_link_to_a_gone_host_is_not_run[run|run_command|sbatch-path|read_file|list_directory]`:
    the tool's not-run text, with `cannot connect to 127.0.0.1: timed out`, nothing received by the
    server, at least one attempt held by the proxy;
  - `test_a_channel_open_outlasting_its_own_timeout_on_a_silent_link_reconnects[run]`:
    `OPEN_TIMEOUT` patched below `B − SETTLE`;
  - `test_a_reconnect_onto_a_link_that_goes_silent_still_ends_in_time`: silent again once the new
    connection's handshake is done;
  - `test_a_command_cut_by_a_silent_link_is_never_run_twice[run|sbatch-path]`: `come_back()` before
    the verdict, −1003, the wire received once;
  - `test_an_idle_connection_is_not_taken_for_a_silent_link`: idle past 3B, then a call on the same
    connection, the server's connection count unchanged;
  - `test_a_quiet_command_rides_out_a_silent_spell_shorter_than_its_verdict`: the server's hook goes
    silent as a background probe arrives; `resume()` 2.5 s later (past B, inside the 3 s background
    verdict); the result exact, on the same connection. It runs on this tree only: develop sends no
    probe;
  - `test_a_command_on_a_link_that_goes_silent_is_lost[no-timeout|later-timeout]`: −1003 and
    `LOST_NOTE` within 3B + 1 s of `go_silent`;
  - `test_a_command_on_a_link_that_goes_silent_ends_at_its_timeout`: −1001, Deviation 1;
  - `test_a_quiet_command_is_not_taken_for_a_silent_link[quiet|slow-link]`: a `sleep` past 3B, and
    output trickled through `rate` so probe replies queue behind data; results exact;
  - `test_a_call_beside_a_command_on_a_silent_link_ends_in_time`: the new call, and the stalled one
    with it, end within B + 1 s of the new call's start.
- [x] **`tests/test_ssh_liveness.py`** (`unit`, plus `integration` for the Paramiko pair):
  - `_verdict`'s arithmetic on a fake clock:
    - due at B quiet;
    - a poke probes at once;
    - with `heard < out`: dead at `out + 2B − VERDICT_MARGIN` for a background probe, and at
      `max(out, poked) + B` while a poke waits, whichever is first; never before either;
    - any message clears;
    - an answered probe clears;
    - a poke stays latched past a probe that predates it;
    - a poke never moves `out`;
    - the priming probe is never judged;
    - a hand-over sets `out` while the sender is busy;
  - the hook stamps nothing on a read that raises;
  - the monitor's bound is `_bound(conn)` (a fake connection with `connect_timeout=40`);
  - no `cluster-mcp-liveness` or `cluster-mcp-probe` thread is left after `close()`, and a call woken
    by `close()` starts no attempt;
  - the hook on a real Paramiko client and server pair: every message stamped, `REQUEST_FAILURE`
    included, and the one in-progress read missed;
  - the close order on a fake gateway chain;
  - the poke reaching the captured transport's monitor;
  - a fake connection gets no monitor;
  - **the doc pin**: AGENTS' footgun, the `SSHExecutor` docstring and the README state B after a
    call's start, a background verdict of `2B − VERDICT_MARGIN` (at most 3B − 0.55 s after the last
    message heard, in flight), the 3B bound, and the floor at the default bound (29 s, 44 s), and
    name `PROBE_REQUEST` and `VERDICT_MARGIN`.
- [x] **`tests/mutants.py`:** re-plant every case whose anchor the edits touch, so
  `test_mutation_anchor_applies` passes. The sweep's new cases are P3's.
- [x] **Documents** (R6, this commit; PLAN §2.3), the command half:
  - the footgun's silent-link paragraph;
  - §3's −1003 entry;
  - § Testing;
  - the README's reconnect paragraph and its −1003 line;
  - the `SSHExecutor` and `run` docstrings.
- **Amended in build (2026-11-05):**
  - The gone-host rows and `test_a_reconnect_onto_a_link_that_goes_silent_still_ends_in_time` take
    the reconnect bound (3B) as their watchdog figure, not B: such a call ends only once its
    reconnect gives up, about 2B after its start on a correct build.
  - `silent_after_handshake` goes silent at a new connection's first probe or channel open, since a
    call's channel open can reach the server before the new monitor's priming probe.
  - The servers' step hooks in P1 are `channel`, `exec` and `probe`.
  - **The gate runs under a recorded wrapper** (the foreman's ruling, 2026-11-05):
    `test_a_channel_open_outlasting_its_own_timeout_on_a_silent_link_reconnects[run]` cannot fail
    on develop with `still waiting`, as the frozen `silent-gate.py` requires of every "fails" row.
    With `OPEN_TIMEOUT` below `B − SETTLE`, develop's open raises Paramiko's
    `Timeout opening channel.` within a second, before any watchdog. That raise is develop failing
    the row, by a raise rather than a hang. The frozen gate was red on that row alone, in both eras
    (attempt 1). `remediation/open-timeout-gate.py` runs `silent-gate.py` unchanged. For that row id
    only, and only in the develop runs, it also accepts a failure carrying `Timeout opening channel`;
    every other row and check stays the frozen gate's. It was seen red first, in the legacy era:
    - with the row's develop failure text changed to carry neither phrase;
    - with the row forced to pass on develop.

    A first try at the first of those did not land: the altered failure kept Paramiko's text
    through the exception chain, and the wrapper went green. It was redone with the chain dropped.
    P1's `verify:` and P3's run the wrapper in place of the bare gate wherever they run
    `commands` rows (P3's `all both`). P2's `transfers both` holds no such row, and keeps the bare
    gate.
- **Verify:** the frontmatter's. `silent-gate.py commands both` requires every P1 row to pass here
  in both eras, and on develop's `packages/` every "fails" row to fail with `still waiting` and
  every "passes" row to pass.
- **Touches:** `packages/cluster-mcp/src/cluster_mcp/core/executor/ssh.py`, `tests/ssh_server.py`,
  `tests/test_ssh_exec.py`, `tests/test_ssh_liveness.py`, `tests/mutants.py`, `AGENTS.md`,
  `README.md`.

## Phase P2 — Transfers: the bounded SFTP open, TransferLost, the write path, and the documents
**Satisfies:** R1, R2, R4, R5, R6, R7 (for `write`, `put`, `get`, and the tools built on them) ·
**Depends on:** P1
**Goal:** every file transfer that meets a silent link at its start reconnects or fails as a failed
reconnect does; one in flight ends within the bound with an error naming the host that says it may
be partly made; a slow live transfer runs to its end; a transfer stalled on the write path cannot
hold a concurrent call.

- [ ] **`_sftp(transport, deadline)`** replaces the three `open_sftp_client()` calls (PLAN §2.2).
  It runs `open_session(timeout=max(OPEN_TIMEOUT, B + 1))`, `invoke_subsystem('sftp')` and the
  `SFTPClient`. A loss anywhere in it reconnects within the call's deadline.
- [ ] **`TransferLost(ConnectionError)`**, raised for a loss once the session is open, with the
  host, "the transfer may be partly made", and what may remain:
  - `put`: the remote target, truncated or partial;
  - `get`: the local file;
  - `write` while staging: the target unchanged, the staging directory named;
  - `write` at its place step: the place step's −1003 raised the same way, with what the move,
    append or write-through can leave.

  The loss is decided by state, before `_upload`'s, `_is_dir`'s, `_loops`' and the staging
  block's `except OSError`. It covers `EOFError` and `SSHException` as well as `OSError`.
  `_reason` and `_discard` are skipped on a lost link. A −1003 or −1002 from the parent `mkdir` or
  the place step is raised as `TransferLost` with that step's text.
- [ ] **Rows** (PLAN §6's table; P2's shapes):
  - `test_a_call_on_a_silent_link_reconnects[write_file]`;
  - `test_an_sftp_open_cut_by_a_silent_link_reconnects[channel|subsystem|version]`;
  - `test_a_channel_open_outlasting_its_own_timeout_on_a_silent_link_reconnects[sftp]`;
  - `test_a_call_on_a_silent_link_to_a_gone_host_is_not_run[write_file|upload_file|download_file|sbatch-content]`;
  - `test_a_transfer_on_a_link_that_goes_silent_may_be_partly_made[put|get|write-lookup|write-stage|write-upload|write-mkdir|write-place|write-place-gone|sbatch]`:
    - the host named and `may be partly made`, within 3B + 1 s of `go_silent`;
    - each goes silent from a server hook at its step: the target's lookup, the staging `mkdir`, an
      SFTP write, the parent `mkdir`'s exec, the place step's exec (with the host back, or gone),
      a read;
    - the step is named in the watchdog;
    - `sbatch` says the script was not written and submits nothing;
    - the leftovers asserted as the message states them;
  - `test_a_slow_transfer_is_not_taken_for_a_silent_link[put|get|write]`: through `rate`, the bytes
    exact;
  - `test_a_call_beside_a_transfer_stalled_on_a_silent_link_ends_in_time`: a 4 MiB `put` in
    flight under `go_silent`. The row first asserts the write path is held (a helper thread's
    `send_ignore` still blocked after 0.5 s), failing, never skipping, when it is not. Then a
    concurrent `run` ends within the bound.
- [ ] **Units** in `tests/test_ssh_liveness.py`: `TransferLost`'s text per shape, and the doc pin
  widened to §2's transfer text.
- [ ] **`tests/mutants.py`:** re-plant the touched anchors.
- [ ] **Documents** (R6, this commit), the transfer half:
  - §2's `write`, `put` and `get` (`TransferLost`, and what each leaves);
  - the footgun's transfer sentences;
  - the README's transfer lines;
  - the `write`, `put` and `get` docstrings.

  `issues/ssh-write-staging-leftover.md` and its `ROADMAP.md` entry get a dated note: a cut write
  now names its staging directory.
- **Verify:** the frontmatter's.
- **Touches:** `core/executor/ssh.py`, `tests/ssh_server.py` (the place-step hook),
  `tests/test_ssh_exec.py`, `tests/test_ssh_liveness.py`, `tests/mutants.py`, `AGENTS.md`,
  `README.md`, `issues/ssh-write-staging-leftover.md`, `ROADMAP.md`.

## Phase P3 — The mutation sweep, every tool in both eras, and the deferral ledger
**Satisfies:** R1–R5 (the sweep), R7 (both eras, every tool) · **Depends on:** P2
**Goal:** every decision of the monitor and the call paths is planted at every alternative it can
take and is killed, or shown equivalent, in both eras. Every tool's rows pass here and fail on
develop. Every recorded item has its seed.

- [ ] **`tests/mutants.py` cases `shol-*`**, one per alternative in PLAN §6's list, each with its
  targets (the rows that kill it) and its `why`. Values handed to calls count as decisions:
  - the bound given to `_verdict`;
  - the open timeout;
  - `LIVENESS_TICK`;
  - the deadline passed on a retry.
- [ ] **`verify/silent-sweep.py {legacy|modern} [1|2]`**, on `spec/timeout-process-cleanup/verify/sweep.py`'s
  model:
  - the `SWEEP` table (decision, alternative, outcome: a case id, an equivalent planted against its
    neighbours' killers, or a reason it cannot be planted);
  - the table checked against `tests/mutants.py` both ways;
  - each half under the 10-minute cap.
- [ ] **`verify/ledger-check.py`:**
  - it walks P1–P3's bodies and the branch's commit bodies for "do not fix here", "known
    limitation", "left as a follow-up", "limit", "deferred" and "floor", reading prose and list
    items, never Markdown headings;
  - each hit must name an `issues/` seed that exists and has a `ROADMAP.md` entry;
  - expected: `issues/ssh-liveness-message-gap.md` (filed with the plan), and the dated notes on
    `issues/ssh-gateway-hops-unpinned.md`, `issues/ssh-write-staging-leftover.md` and
    `issues/ssh-open-session-reset-raises.md`, which the phase adds if P1–P2 have not;
  - an item with no seed fails the phase.
- [ ] **Every tool, both eras**: `CLUSTER_MCP_TEST_EVERY_KIND=1 silent-gate.py all both`.
- [ ] **Suite growth per era**: measure the full suite on this tree and on `13c0e83` back to back,
  and the new rows alone. Record both, and CI's two era jobs once pushed.
- [ ] **The masked pair** (the foreman's ruling at P1, 2026-11-05): "a judged probe still
  unanswered at an open's failure counts as a loss" and the open timeout
  `max(OPEN_TIMEOUT, B + 1)` each mask the other's mutant. Either show the pair equivalent by an
  exact argument, or propose dropping the redundant rule as a TECH amendment, with the reason.
- [ ] **Standing last-phase items:** the previous cycle's last phase carried no project-level
  obligation beyond the ledger (no `## Times` quote in this repo).
- **Verify:** the frontmatter's (≈ 10 min, run in the background).
- **Touches:** `tests/mutants.py`, `spec/ssh-half-open-link/verify/`, and nothing else but a seed or
  entry the ledger finds missing.

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
