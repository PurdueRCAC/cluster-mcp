# REVIEW — A dead SSH link that still reads as connected is noticed within a bound

> Adversarial QA by `code-review`, run in isolated contexts: the debate variant, two fresh
> subagents (one arguing "ship", one "block"), since the diff touches the coupled core. The
> correctness pass grades the branch diff against [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md`
> § Invariants **only**; neither reviewer saw `PLAN.md`/`TECH.md`. Every finding cites an
> **executed** command.

- **Reviewed commit:** b09a9914203f1e158440dd7d497444a4558f15c7  ·  **Base:** develop  ·  **Date:** 2026-11-05
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3

## Verification run

Each reviewer worked in its own clone of the reviewed commit, with a second clone of
`origin/develop` (`9a32382`) as the develop control.

- `uv lock --check` → passes (both reviewers).
- `bin/sandbox.sh uv run cluster-mcp --help` → exit 0, usage printed (both).
- Full suite, both eras (ship reviewer): legacy 4929 passed / 14 skipped (722 s); modern 4929 passed /
  14 skipped (772 s). CI run 42023864497 on the reviewed commit: both suites and `gate` green on
  attempt 2 (attempt 1's modern era failed one seeded-class timing row in `test_probes.py`, see
  `issues/stalled-reconnect-test-timing.md`).
- Block reviewer, both eras: `test_ssh_liveness.py` 24 passed; `test_ssh_exec.py` 186 passed;
  `test_mutations`, `test_hygiene`, `test_writes`, `test_sbatch`, `test_executors`, `test_transports`
  1374 passed.
- Opt-in rows, `CLUSTER_MCP_TEST_EVERY_KIND=1` (ship reviewer): the reconnect row passes for all 9
  tools in both eras; the gone-host row passes for all 9.
- Develop control (both reviewers, the head's tests on a develop clone): 33–37 of the 41 silent rows
  fail at the watchdog's `still waiting …`; the rows that pass on develop are the R4 completeness
  rows and the timeout-first row, as expected.
- Default 15 s bound, reviewer-written rows (ship): reconnect after 15.24 s; a gone host gives −1002
  at 45.01 s; a running command is lost (−1003) 43.81 s after the silence; a quiet command survives a
  20 s outage beginning at a background probe, on one connection.
- Mutants, beyond the committed sweep: the ship reviewer planted `_gone→False`, `_cut→False` and a
  background verdict at B; each was killed by a loopback row.
- Probe rows (block), kept outside the repo: `test_review_write_raises_oserror_after_writing` (F2)
  and `test_review_timeout_beside_a_stalled_upload` (F1), run three times with the same result.

## Requirement → evidence matrix

| R-ID | Implemented by | Verified how | Status |
|------|----------------|--------------|--------|
| R1 | `executor/ssh.py` (`_Liveness`, `_opening`, `_gone`) | reconnect and gone-host rows for 9 tools, both eras; develop fails them; mutants `shol-poke-removed`, `shol-retry-removed` killed; 15.24 s at the real bound | ✅ |
| R2 | `ssh.py` (`TransferLost`, `_cut`) | `…may_be_partly_made[…]` ×9, both eras; develop fails all 9 | ✅ (contract docs: F2) |
| R3 | `ssh.py` (`_collect`, the verdict's close) | `…_is_lost[no-timeout\|later-timeout]`, `never_run_twice[…]`, `ends_at_its_timeout`; −1003 at 43.81 s | ❌ concurrent case (F1) |
| R4 | `ssh.py` (`heard` stamp, split verdict, priming probe) | quiet, slow-link, slow-transfer ×3, spell rows; unit rows pin 29/44/45/0.55; 20 s outage survived | ✅ two bullets; third unpinned (F4); floor seed misstated (F3) |
| R5 | `ssh.py` (judge and sender threads) | `call_beside_a_command…`, `call_beside_a_transfer_stalled…` (write path shown held); develop fails both | ✅ |
| R6 | `AGENTS.md` footgun, §2, §3, § Testing; README | every commit touching `ssh.py` touches `AGENTS.md`; `test_liveness_texts_state_the_monitor` | ❌ `executor/base.py` not updated (F2) |
| R7 | `tests/ssh_server.py` `SilentLink`; rows in both eras | develop control above | ✅ |

No R-ID is met by an artifact under `spec/`; the reviewers graded all seven.

Unmapped changes, accepted as within R2's reach: a `write` whose `mkdir` or place step cannot
reconnect after its SFTP session opened now raises `TransferLost` instead of returning −1002, so
`sbatch` with `script_content` reports "Failed to write job script: … may be partly made". The two
prior-cycle rows were rewritten to match, and the `cannot connect` text survives inside the message.
F2 makes the Protocol say so. Also: a reset during a channel open now reconnects (noted on
`issues/ssh-open-session-reset-raises.md`); the `suite-ci-time-budget` seed; dated seed notes; a
README paragraph; 45 `shol-*` mutation cases.

## Findings

### [HIGH/CONFIRMED] F2 — The Protocol still promises "nothing was written/transferred" for errors now raised after a partial write
- **Where:** `packages/cluster-mcp/src/cluster_mcp/core/executor/base.py:172-177` (`write`, Raises
  `OSError`), `:198-201` (`put`) and `:219-222` (`get`) (Raises `ConnectionError`).
- **Failure scenario:** `SSHExecutor.write` raises `TransferLost` (an `OSError`) after its place
  step may have replaced or appended to the target; `put`/`get` raise it (a `ConnectionError`)
  after a partial transfer. A caller or a new backend reading the Protocol concludes the target is
  unchanged.
- **Evidence:** the block probe makes the link go silent at the place step's exec:
  `raised TransferLost (OSError: True, TransferLost: True): the connection to 127.0.0.1 was lost
  during the write; … x.txt is either the old file or the new one …`, then `target now holds 'new
  content\n'`. `git diff --stat origin/develop...HEAD -- …/executor/base.py` is empty.
- **Touches:** R2, R6; § Conventions (a restated rule is a same-commit obligation everywhere it is
  restated), hence HIGH; `executor/base.py` is § Invariants §2.

### [MEDIUM/CONFIRMED] F1 — A command's own timeout is held to the verdict while another call holds the write path
- **Where:** `ssh.py:223` (`_signal` takes `transport.clear_to_send_lock` with no bound), reached
  from `_collect` (`ssh.py:312`) on the timeout.
- **Failure scenario:** a `run` with a timeout is running while an upload on the same connection is
  stalled on the silent link, holding the write path. At the timeout, the TERM blocks on that lock
  until the verdict closes the transport, so the call ends at the bound, not at its timeout. At the
  default bound, a `timeout=10` call returns about 30 s late.
- **Evidence:** `test_review_timeout_beside_a_stalled_upload` (B patched to 4, timeout 3 s), three
  runs: `call ended 8.55 s after its deadline (11.18 s after the silence), exit -1001`; alone, `1.02 s
  after its deadline`; stack 2.5 s past the deadline `ssh.py:223 _signal <- ssh.py:312 _collect <-
  ssh.py:1424 _exec <- ssh.py:1387 _run`.
- **Touches:** R3 ("no later than the earlier of its own timeout and the bound"), R5.
- **Judge's reading:** §3's "not counting the link's own delay" covers a slow link delaying the
  command's own traffic, not another call's held write path. R3 states the earlier of the two
  without that exclusion, and the delay here is not this call's link delay. CONFIRMED against R3.

### [LOW/CONFIRMED] F3 — The floor's seed misstates its own verdict
- **Where:** `ROADMAP.md:157-160`; `issues/ssh-liveness-message-gap.md:8` (title).
- **Failure scenario:** both say a live link is called dead after a probe has been out "for one
  connect bound". The code judges a background probe at `out + 2B − VERDICT_MARGIN` (`ssh.py:564`,
  29 s at the default); one bound holds only while a call starts. The issue's own body says so.
- **Evidence:** read against `ssh.py:564` and the issue body; the R4 rows pin 29 s.
- **Touches:** R4 (GOAL names this seed as where the limit is recorded).

### [LOW/CONFIRMED] F4 — R4's third bullet has no row
- **Where:** `tests/test_ssh_liveness.py`, `tests/test_ssh_exec.py`.
- **Failure scenario:** R4 states that while another call starts, a quiet command and a slow transfer
  survive only within that call's 15 s verdict. No row starts a call on a live link during a quiet
  command or a slow transfer, so a change to that case passes the suite.
- **Evidence:** `grep 'def test_.*beside'` finds only the two silent-link rows.
- **Touches:** R4.

### Dropped or out of scope
- One `PytestUnhandledThreadExceptionWarning` (an `EOFError` from `packetizer.send_message`) in one
  legacy full run, not from a liveness thread (the `silenced` fixture would fail the row), not
  recurring, not tied to a row: dropped under the refutation protocol.
- A write that succeeds after a reconnect leaves its staging directory: on develop too, already
  seeded (`issues/ssh-write-staging-leftover.md`), outside R2 (nothing was cut short).
- Landing: `issues/stalled-reconnect-test-timing.md` conflicts with `origin/develop` (`4b10c40`,
  `9a32382`); keep both sets of dated notes at publish.

## Human-gate triggers

- **Triggered by F2:** `executor/base.py` is on § Invariants' high-blast-radius list, and the
  finding concerns §2 *[human gate]*. Under the cluster-mcp autonomy decision (2026-10-16), the
  foreman is judge at human gates. Ruling: the behaviour F2 documents is what GOAL R2 asks for
  (a transfer cut short says what may remain), so the fix brings §2's restatements into line with
  R2 and widens nothing. Reported to Geoffrey with this verdict.

## Review cycle 2 — changes-requested (2026-11-05)

- **Reviewed commit:** ac4909a8b01e21b90ff50432bf6645b621e6af3f · **Mode:** a fresh blind pass over the full
  spec-excluded diff (the default), the debate variant again: two new reviewers who never saw cycle 1's findings.
- **CI** run on the reviewed commit: both eras 4961 passed, `gate` green, on attempt 1.

### Verification run

- Both reviewers, in their own clones with `UV_PYTHON=3.14` (CI's interpreter): `test_ssh_liveness.py` +
  `test_ssh_exec.py` 218 passed per era; the rest of the suite 4726 passed / 14 skipped (both eras for the ship
  reviewer, handshake era for the block reviewer); `uv lock --check` passes; `bin/sandbox.sh uv run cluster-mcp
  --help` exits 0.
- Develop control (the head's tests on `9a32382`): 39–40 rows fail. The 34 behavioural failures read "still
  waiting …". The others pass on develop or fail on a missing constant: R4 rows (develop doesn't misbehave
  there), the timeout-first row, and `write_path[free]`.
- Ship reviewer's own drive through `bin/sandbox.sh` against `SilentLink`:
  - B = 3: reconnect 3.18 s; gone host −1002 at 9.00 s; `put`/`get` `TransferLost` at 8.19/8.10 s; −1003 at
    7.86 s (stated 8.45 s); a beside call 3.15 s; a quiet command of 11 s finishes on one connection.
  - B = 15: reconnect 15.22 s; `put` 44.16 s; −1003 at 43.81 s (stated 44.45 s).
- Negative controls: 11 author mutants and 3 of the ship reviewer's own were killed by their target rows. One
  plant survived and is equivalent: dropping the "answered" clear in `step()`, which `_verdict` already ignores
  through `heard >= out`.
- The block reviewer's probe rows (a reviewer-local file, not in the repo) cover the two cases below. Its other
  candidates were dropped under refutation: a TERM queued behind EOF under contention still arrived and ran its
  trap; `heard` was not starved by transport-thread sends (worst gap 3.46 s against a 5 s floor); Paramiko
  3.2's internals match.

### Requirement → evidence matrix

| R-ID | Status | Note |
|------|--------|------|
| R1 | ❌ one path | F-A: a late reconnect onto a link that goes silent again ends past 3B |
| R2 | ✅ | 9 shapes; develop fails all 9; `_cut→False` plant fails 4 rows |
| R3 | ✅ | −1003 within 3B − 0.55; timeout-first −1001; F1's stalled-upload row |
| R4 | ✅ | including the four beside-a-starting-call rows (cycle 1 F4) |
| R5 | ✅ | `write_path[held]` fails on develop |
| R6 | ✅ | the doc pin reads the Protocol's Raises (cycle 1 F2) |
| R7 | ✅ | develop control above |

Unmapped changes: none beyond those recorded in cycle 1.

### Findings

#### [HIGH/CONFIRMED] F-C — A cycle-scoped review-finding id in the suite
- **Where:** `tests/mutants.py:5517`: `# Review cycle 1, F1: everything a call sends …`, added in `ac4909a`.
- **Failure scenario:** the id points into this cycle's `spec/` record and collides with every other cycle's
  F1. That is the reason § Conventions bans feature-scoped ids. The suite's own check
  (`tests/test_hygiene.py:616`, `SPEC_ID = r'\b[RPQ][0-9]{1,2}\b'`) does not match F-numbers, so it passes.
- **Evidence:** `git diff 9a32382 HEAD -- packages tests | grep '^+' | grep -E '\bF[0-9]+\b'` → that one line,
  found by both reviewers. `git log -S"Review cycle 1, F1"` → `ac4909a`.
- **Judge's reading:** a review finding id is feature-scoped by the rule's own reason, so this is a § Conventions
  violation, HIGH under the rubric.

#### [MEDIUM/CONFIRMED] F-A — A call that reconnects late onto a link that goes silent again outlives the bound
- **Where:** `ssh.py:1503-1507` (the `run` retry loop) and `:1534` (`open_session(timeout=_open_timeout(…))`
  under `_opening`); `_sftp` has the same shape. `_open_timeout` (`:718`) takes no account of the call's
  deadline.
- **Failure scenario:** a call starts on a silent link. The host refuses, then comes back just before the call's
  last start, and the new link goes silent again (a flapping link). The open on the new transport waits for that
  connection's own verdict, B after its poke, with no cap at the call's deadline.
- **Evidence:** the block reviewer's probe uses `SilentLink`, `server.refuse()`, `serve_again()` and
  `silent_after_handshake=True`, 0.4 s before the last start:
  - B = 6: `exit=-1002 … ended 22.19 s after the call began …; reconnect bound 18 s`.
  - B = 15: `ended 58.06 s …; reconnect bound 45 s`.
  - `test_a_reconnect_onto_a_link_that_goes_silent_still_ends_in_time` reconnects only early.
  - AGENTS § Testing's sentence on it is broader than the code.
- **Touches:** R1. Develop is worse here (it never notices the first silence), so this is incomplete, not a
  regression.

### Dropped

- **F-B: a link that goes silent while the exec request is in flight** ends at the bound (−1003, 44.13 s at
  B = 15, inside 3B), not at the call's own timeout. Dropped as consistent with the contract:
  - §3 runs the ssh timeout "from the command's start", which the client knows only at the exec reply. Until
    then the timeout has not begun, and the bound governs (GOAL Q6).
  - Cycle 1's F1 differs: there the timeout had begun and another call's held write path delayed it.
  - It cites R3's wording, so it is dropped, not deferred.

### Human-gate triggers

- None new: neither confirmed finding touches a high-blast-radius path. Cycle 1's F2 (`executor/base.py`, §2)
  remains recorded, judged by the foreman under the autonomy decision.

### Escalation

This is cycle 2 without convergence. Per code-review Step 6, it goes to Geoffrey before a second remediation.

## Review cycle 3 — changes-requested (2026-11-05)

- **Reviewed commit:** e2ad380c06d19aa91d93bdffc1296c7fea1257d8 · **Mode:** scoped verification of cycle 2's F-A
  and F-C, as Geoffrey chose: one fresh blind reviewer, in clones at `e2ad380` and `82b1f0e`, given GOAL, the
  rubric, AGENTS.md § Factory onward and the two findings' text.
- **CI** run on the reviewed commit: both eras 4984 passed, `gate` green, on attempt 1 (848/871 s of pytest).

### Verification run

- Profile verify on the head, `UV_PYTHON=3.14`: `uv lock --check` exits 0; the full suite 4967 passed / 14
  skipped per era; `bin/sandbox.sh uv run cluster-mcp --help` exits 0.
- The reviewer's own probe through `bin/sandbox.sh`, head against `82b1f0e`, seconds from the call's start:
  - cycle 2's probe as written (B = 15, `run`): 58.17 base, 45.00 head (−1002, nothing received by the server);
  - late reconnect onto a link that goes silent again, run / write / put: 22.08–22.06 base, 18.00–18.01 head at
    B = 6; 58.13–58.22 base, 45.00–45.01 head at B = 15; two other placements of the reconnect, and silence at
    the channel, SFTP subsystem and version steps, all at the bound on the head;
  - a late reconnect onto a live link completes on both trees (43.03–43.49 s at B = 15).
- Negative controls: the cap removed fails both default late rows in both eras (10.1 s against 9 s); a late
  SFTP session left open is caught (`_close_quietly` disabled); 16 of the remediation's mutation cases killed.
- No `cluster-mcp-open` worker outlives B + 2 s; no call was cut before its deadline.

### Status of cycle 2's findings

| Finding | Status | Evidence |
|---|---|---|
| F-A | ✅ fixed as a class | every open before a call's work, command and SFTP paths, cut at the deadline (table above) |
| F-C | ✅ fixed | the line is gone; the widened check fails on the base tree naming it; no false positives in the 79 files it reads |

### Requirement → evidence matrix (R-IDs the diff touches)

| R-ID | Status | Note |
|------|--------|------|
| R1 | ✅ | at the bound for B = 3, 6, 15, every tool; live late reconnects complete; cut calls read −1002 / nothing transferred |
| R2 | ✅ | untouched; place step silent at its channel: `TransferLost` 6.12 s after the silence |
| R3 | ✅ | exec after a late reconnect: −1003 17.1 s after the silence, on both trees (unchanged) |
| R4 | ✅ | `shol-cap-always` killed by the slow-write row; full suite green |
| R6 | ❌ text | N1: the new rule text is broader than the code |
| R7 | ✅ | new rows red with the cap removed, both eras |

Unmapped changes: the seed `issues/mutant-child-outlives-timeout.md` and its ROADMAP entry, and the timing note
in `issues/suite-ci-time-budget.md`. Neither is a defect.

### Findings

#### [MEDIUM/CONFIRMED] N1 — The new rule text claims a cap a `write`'s own later commands don't get
- **Where:** the `executor/ssh.py` footgun in AGENTS.md § Invariants and the `SSHExecutor` docstring
  (`ssh.py:1274-1279`), pinned verbatim as `OPEN_TEXT`. `_write` runs its mkdir and place steps through `_run`
  (`ssh.py:1780`, `:1836`), which takes the connection the write itself just reconnected to as found live
  (`:1623`), so their open is not capped (`:1629`).
- **Failure scenario:** at B = 6 a write opens its session on a late reconnect at 16.0 s and stages its content;
  the new link goes silent at the place step's channel open. The write ends at 22.14 s (22.18 s on base), past
  the 18 s the text promises, with an honest `TransferLost … unchanged …`.
- **Judge's reading:** the behaviour is in contract: the transfer is in flight, so R2 governs and holds (6.12 s
  after the silence). The defect is the § Invariants text this diff added and pinned, the same shape as cycle
  2's "§ Testing broader than the code". MEDIUM stands: no behaviour is wrong.

#### [LOW/CONFIRMED] N2 — The cap on the SFTP subsystem and version steps is pinned only behind an opt-in
- **Where:** the `[write_file-subsystem]` and `[write_file-version]` late rows run only with
  `CLUSTER_MCP_TEST_EVERY_KIND=1`, which CI never sets; no mutation case covers the steps.
- **Failure scenario:** a cap on `_sftp`'s channel open alone, with the subsystem and version steps on the
  call's thread, passes the default suite (`[write_file]` 9.12 s) and fails both opt-in rows (10.1 / 10.2 s).

#### [LOW/CONFIRMED] N3 — A review-finding id survives in an identifier, so the new § Testing sentence is false
- **Where:** `tests/test_timeout_stop.py:471` `F3_SETTINGS` (used at 493, 524, 789, 830), pre-existing from
  `9a41ea1`. `\b` doesn't fall between `3` and `_`, so neither the old nor the widened check sees it
  (`F3_ROWS` and `R3_ROWS` planted: both missed).
- **Failure scenario:** the diff's § Testing sentence says no review-finding id appears in the suite, and the
  gate is green while one does.
- **Grading:** the reviewer graded it PLAUSIBLE, unable to see `spec/`. The orchestrator confirmed it from the
  timeout-process-cleanup record, whose review cycle names that F3 for exactly these four settings. The code is
  pre-existing; the false claim is this diff's.

### Dropped

- None. The exec request after a late reconnect (−1003, 17.1 s after the silence) is R3 and the cycle-2 F-B
  ruling, unchanged by this diff; the reviewer did not raise it.

### Human-gate triggers

- None new. N1 touches § Invariants text, not a high-blast-radius path's behaviour.

### Escalation

This is cycle 3, the loop's last, without convergence. Per code-review Step 6, it goes to Geoffrey.

## Remediation 3 — approved by foreman verification (2026-11-06)

- **Verified commit:** 4b4ad2879c871d621ae6ed955c97a26da1e621fa · **Mode:** as Geoffrey chose at cycle 3's
  escalation, no fourth blind pass: the foreman, as judge, read the remediation diff (`f1fa641..4b4ad28`,
  spec excluded) and re-ran its checks.
- **CI** run on the verified commit: both eras 4996 passed, `gate` green, on attempt 1 (782/810 s of pytest).

### Verification run (the foreman's own)

- `F9-glued-id-hygiene.py`: green. The widened check, run over `f1fa641`'s tree, names exactly the seven glued
  lines (`tests/test_literal_args.py:264, 736`; `tests/test_timeout_stop.py:471, 493, 524, 789, 830`).
- `F7-open-rule-statement.py both`: green. Callers of `_run`: `run` and the write's own `MAKE_PARENT`, `VERIFY`
  and `PROBE`; of `_sftp`: `write`, `put`, `get`. A cap on every `_run` open is killed by the new
  `…_is_a_lost_transfer[mkdir|place]` rows in both eras.
- `F8-session-steps-cap.py both`: green. The channel-only cap survives the ten default rows of the `_sftp` family
  without the pin and is killed by the opt-in step rows; both `shol-session-` cases are killed by the default
  pin.
- `tests/test_hygiene.py -k 'spec_id or id_rule'`: 16 passed; the N2 pin: 3 passed in each era.
- The builder's full gate on the identical tree, from its logs: every step green. One union-step red on
  `test_a_stalled_reconnect_is_abandoned_against_a_real_handshake`, the class `issues/stalled-reconnect-test-timing.md`
  names, went through code-build's flake route (three passes alone, a green re-run) and has a dated line in that seed.

### Status of cycle 3's findings

| Finding | Status | Evidence |
|---|---|---|
| N1 | ✅ fixed | `OPEN_TEXT`, the footgun and § Testing now state the cap for opens before a call's work starts, and a `write`'s own commands as they run; F7 holds every caller path to the text |
| N2 | ✅ fixed | a default-suite unit pin (about 0.7 s per era) kills the review's plant; two mutation cases |
| N3 | ✅ fixed | `F3_SETTINGS` and `r1_violations` renamed; the check catches glued ids; § Testing and § Conventions state it word for word, pinned |

No new defect found in the remediation diff. The diff changes no behaviour: `ssh.py` changes only the docstring
and one comment.

### Verdict

Approved at `4b4ad28`. Next: publish.
