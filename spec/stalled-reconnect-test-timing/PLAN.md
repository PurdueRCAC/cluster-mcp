# PLAN — Real-time tests fail on behaviour, not on a busy host

> **Status:** Draft for review · **Last updated:** 2026-11-09
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Backing detail is in
> [`research/01-where-the-time-goes.md`](research/01-where-the-time-goes.md). Every design element
> traces to a GOAL R-ID.

## 1. Summary

Executed probes put every sighting on one cause: a stall of the test process inside an interval the
row times, where the stall is no part of the property. A full suite's own generation-2 collections
take 0.03–0.125 s on this host (one landed inside a row-4 start), and none of the protocol's CPU
spinners moved any row. So each row moves its measurement off the host's clock as far as its
property allows. Row 1 counts the reconnect worker as it starts (its count was a race the worker's
0–0.11 s end loses). Rows 2 and 3 measure on a clock only the code's own waits move, as the
Clarifications allow for an ordering. Row 4's property is a real duration, so no reference point
helps; the plan proposes pausing the collector for the timed start (deviation D1, the maintainer's
call) and gives fallback (c)'s figures beside it. No value changes, nothing under `packages/`
changes, and each row gets a planted-fault sweep and an in-process stall control, run on the base
too.

## 2. Design

All edits are in `tests/test_ssh_exec.py`, `tests/test_probes.py` and `tests/test_probe_startup.py`.
`tests/mutants.py` is not edited: no existing case needs retargeting (the 32 that name the four rows
keep their targets and `why`s), and the sweep plants its own faults through the runner's `Case` and
`run_case`, unchanged. No AGENTS.md text describes how these rows measure, so § Testing is not
edited.

### Row 1 — count each worker as it starts (R1, R7)

`test_a_stalled_reconnect_is_abandoned_against_a_real_handshake`:

- A `Thread.start` hook (`monkeypatch.setattr(threading.Thread, 'start', start)`), installed from
  just before the call until the joins below are done, appends each thread named `WORKER` whose
  target is this executor's `_settle` (another executor's worker in a full suite never counts) once
  its real `start` has returned. The `before` snapshot and the `threading.enumerate()` listing go.
  The count must be exactly one: `'{n} reconnect workers started during the call, not one'`.
- Each recorded worker is joined for `STALL_WORKER` (1.0 s) after the call returns, as now; one still
  alive fails with `'the abandoned attempt was still running 1.0 s after the call gave up, past its
  1.0 s bound'`. A worker that ended before the return joins at once and counts; one started after
  the return, while the hook is still on, counts too (two, not one).
- The give-up stays `not_run_violations(result, 'timed out', took, STALL_WINDOW, host=LOOPBACK,
  slack=STALL_LATE)`, measured from just before `executor.run`. `held` (an attempt reached the
  silent host) stays.
- R7: the shared `not_run_violations` time message becomes `'the call gave up {elapsed:.2f} s after it
  began, past its {bound} s bound and {slack} s of slack'` (deviation D4). Every mutant `why` that
  quotes it (`'past its'`) stays a substring.

### Row 2 — measure the call's waits on the row's clock (R2, R7, R9)

`test_a_reconnect_worker_that_cannot_start_frees_the_attempt` already runs on `FakeClock`, whose
offset only the call's waits (`ssh._await`, wrapped by `clock.wait`) and backoff sleeps move.

- `spent` becomes `clock.offset` after the first call minus before it: the seconds the call spent
  waiting on an attempt, which the MCP round trip around it (0.036–0.044 s alone, more on a busy
  host: research § Row 2) never moves. Bound unchanged: `round(spent, 9) >= ssh.ATTEMPT_POLL` fails,
  with `'the call whose worker could not start waited {spent:.2f} s for an attempt on the row's clock,
  not giving up within ATTEMPT_POLL ({ATTEMPT_POLL} s)'`. `>=` and the rounding: a one-poll wait
  advances the offset by `min(ATTEMPT_POLL, deadline − now)` = 0.1 s, a sum of floats (D2).
- `ssh._await` is wrapped once more to record each wait the first call makes on an unfinished attempt
  (`seconds > 0`, event unset); any fails, with `'the call whose worker could not start waited on an
  attempt ({n} waits, the first asking {w:.2f} s), not giving up at once without one'`. A wait
  shorter than a poll moves the offset under 0.1 s; this catches it (D2).
- The row clock sees only the waits that go through `ssh._await` and `ssh.time`. The executor's own
  give-up is also timed on the real clock: `SSHExecutor._ensure_connected` is wrapped for the first
  call and timed on `_REAL_MONOTONIC` from its entry to its return, and `ensured >= ssh.ATTEMPT_POLL`
  fails, with `'the executor took {x:.3f} s from entering its reconnect to giving up, on the real
  clock, not under ATTEMPT_POLL ({ATTEMPT_POLL} s)'`. Same value, a reference point that excludes
  the MCP round trip: the interval measured 0.0000–0.0001 s alone and loaded (research § Row 2). It
  catches a wait off the row's clock (a real `Event().wait`), which the base row caught and the
  clock alone would not (review H1).
- The slot check (`'stayed taken'`, the existing case's `why`), the message, the next call and the
  connection count stay.

### Row 3 — decide the RAISED endings on a probe clock (R3, R7, R9)

`test_every_ending_without_an_answer_serves_the_capability` gains a `ProbeClock`, defined in
`tests/test_probes.py`:

- It stands in for `probes.time` (its `monotonic`, `perf_counter` and `monotonic_ns` read the clock,
  frozen at `ORIGIN` = 100.0; its `sleep` advances it, once every other probe worker has ended, so an
  advance never races a worker on its way to its answer) and for `probes.threading` (its
  `Event.wait` and its `Thread`). For the row's length the real `time.sleep` is routed too
  (`monkeypatch.setattr(time, 'sleep', clock.routed_sleep)`): on the main thread and the probe's
  workers it is the clock's, on any other thread (a full suite's leftovers) the real one, so a probe
  that sleeps through `__import__('time')` still moves the clock. A wait returns
  True, moving nothing, when its event is set, at once or while a probe worker still runs, however
  long that takes in real time (up to `SETTLE`, 10 s, then the row fails naming it). When the event is
  still unset once every worker the probe started (but the waiting thread) has ended, the deadline has come: the clock
  advances by the wait's timeout (`math.inf` for none) and the wait returns False. `unstartable`
  replaces `threading_whose_start_raises` for `thread-cannot-start` (that helper stays for the
  interrupt row).
- For every ending (all 32, so the existing cases' rows keep running): the reason check unchanged;
  the wall check `took <= BOUND + SLACK` unchanged, its message now `'the verdicts took {took:.2f} s,
  past the bound ({BOUND} s) and its slack ({SLACK} s)'` (R7); and an engagement check,
  `math.isclose(pending._deadline, ProbeClock.ORIGIN + BOUND) and isinstance(pending._answered,
  clock.Event)`, and a worker started through the clock's `Thread` but for `thread-cannot-start`,
  failing with `"the probe did not take its deadline and its wait on the row's
  clock"`: a probe that stops reading `probes.time` or `probes.threading` turns the row red, never
  green (D3).
- For RAISED endings: `waited < BOUND / 2`, `waited` the clock's advance, failing with `'decided only
  at the deadline ({waited:.2f} s into its {BOUND} s bound on the row's clock, not under {BOUND / 2}
  s), not when it happened'`. A raised ending decided as it happens reads 0.00; one decided at the
  deadline reads 0.30, by the sleep, the wait or the post that reached it.

### Row 4 — the timed start (R4, R7, R9; decision at sign-off)

`test_every_ending_without_an_answer_serves_every_capability`. The property is a real duration: any
wait anywhere in the start (the probe's, a join, a sleep after the verdicts) must count, so the row
keeps the real clock. A reference point inside the start removes nothing measurable: before the
probe's start ≤ 1.1 ms, after its verdicts ≤ 0.7 ms (research § Rows 3 and 4). **(a) is impractical
for row 4.** Two ways forward, for the maintainer at the PLAN/TECH sign-off:

- **D1, proposed: pause the collector for the timed start.** A `collector_paused()` context manager
  in `tests/test_probe_startup.py` (`gc.disable()`, re-enabled after only if it was on, as `timeit`
  times its runs) wraps the row's `start(...)` call. Values, comparison and reference point
  unchanged: `observed.seconds >= (0.3 if ending in ('hang', 'timeout-code') else 0) + 0.5` fails,
  with `"the start took {s:.2f} s, past its {b + 0.5} s bound (the probe's own wait, {b} s, and 0.5 s
  of slack)"`. It is neither
  a reference-point change nor the named fallback, so it needs a ruling.
  *Ruled 2026-11-09: the maintainer approved D1, bounds unchanged, and added that a row-4 failure
  reports the collector's pause time: `collector_paused()` yields the seconds any collection still
  took inside the block, and the message ends `, the collector pausing it {p:.2f} s of that`
  (TECH Amendments; fault 4/`collects-slowly-in-the-start` in § 6).*
- **(c), the named fallback: widen the slack.** Figures in § 5.

TECH's P4 builds D1. If the sign-off picks (c) instead, P4 drops `collector_paused()` and sets the
slack to the signed value, and the gate's `KEPT[4]`, `BUILT[4]` and the `waits-*` faults' sizes
follow (§ 6), amended in the plan before build.

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1 | Row 1: `Thread.start` hook counts each worker as it starts; join each for 1.0 s; give-up and `held` unchanged. Faults 1/* (§ 6). |
| R2 | Row 2: `spent` on `FakeClock`'s offset, `>= ATTEMPT_POLL`; no wait on an attempt; the executor's own give-up on the real clock under `ATTEMPT_POLL`. Faults 2/*; control 2. |
| R3 | Row 3: `ProbeClock` (and the real `time.sleep` routed to it); `waited < BOUND / 2`; engagement check. Faults 3/*; control 3; D7's residual. |
| R4 | Row 4: D1 (or (c), as signed); values unchanged. Faults 4/*; control 4. |
| R5 | P6: `verify/load-protocol.py run` on the final tree, recorded in `verify/load-runs.txt`; `check` grades it. |
| R6 | `verify/timing-gate.py`: each phase's `row` mode (faults and controls for its row); P5's sweep on the final tree, every row and the 31 existing cases that name rows 3–4 plus `ssh-reconnect-unstarted-worker-holds-slot`, recorded in `verify/sweep.txt`. |
| R7 | The messages above: each names the interval, its value and the bound with its slack. |
| R8 | No gate command, partition or workflow edit (`scope`: the diff touches only the three test modules, `spec/`, `issues/`, ROADMAP); each era collects the same ids of the four rows as the base (`scope`); per-module times before and after (P5, § 6). |
| R9 | `values`: `STALL_WINDOW`, `STALL_LATE`, `STALL_WORKER`, `BOUND`, `SLACK`, `RAISED` keep their text; each row's code (its AST, nested functions included, never a comment) keeps its bound comparison; no skip, xfail or flaky mark, no skip call or raise, no early return; no added line of the three modules carries a skip, a retry, a broad `except` or a load condition. |

## 3. Invariant gate (AGENTS.md constitution check)

Gate #1 (before research): the change is test-only. No § Invariants numbered section governs a test
module's measurement; the sections the rows *observe* are §2 (`executor/ssh.py`'s reconnect bound,
via the footgun list) and §7 (the probe, `probes.py`). Neither file changes (Non-goal), so no
high-blast-radius path is touched: trigger 2 does not fire. § Conventions touched: "CI mirrors the
gate" (no command, partition or workflow change), "Tests: only `@mark.unit` and `@mark.integration`"
(no new test; markers unchanged), the mutation-runner paragraph of § Testing (cases rerun, none
retargeted).

Gate #2 (after design):

- §2, `executor/ssh.py` footgun (the reconnect bound): unchanged code; row 1 still pins the 3 s window
  from a 1 s connect bound and the abandon; row 2 still pins "a worker that cannot start frees the
  slot and gives up at once".
- §7 (`probes.py`): unchanged code; rows 3 and 4 still pin "decided at once" and "bounded".
- § Conventions, "CI mirrors the gate": `scope` refuses any edit to `.github/`, AGENTS.md's profile,
  `pyproject.toml` or `uv.lock`, and each era collects the same row ids.
- § Testing, the mutation runner: `tests/mutants.py` unedited; its 32 cases naming the rows rerun in
  P5 (`cases`).

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| **D1** (row 4): the timed start runs with the cyclic collector paused. Not one of the Clarifications' named moves; **needs the maintainer's ruling** at sign-off. | Row 4's stall lands inside the probe's own window (a 100.5 ms collection inside `exit-1-local-stdio-core-only`, research § The full suite's own pauses); no reference point excludes it, and the property needs a real clock. Pausing the collector removes the in-process source the sightings point to and keeps every value, comparison and fault. | (a) alone: moving the reference to the probe's start removes ≤ 1.1 ms. (c): a 1.0 s slack lets a start wait up to 1.0 s past its bound (§ 5: faults 4/`waits-past-the-bound` and 4/`waits-after-the-answer` survive). |
| **D2** (row 2): the comparison becomes `round(spent, 9) >= ATTEMPT_POLL` (was `spent > ATTEMPT_POLL`), and the row adds "no wait on an unfinished attempt". Value 0.1 s unchanged. | On the row's clock a one-poll wait advances `min(ATTEMPT_POLL, 45 − 0)` = 0.1 s: `>` passes it, and an offset that is a sum of floats can read it as 0.0999…; `>=` after rounding to 1e-9 fails it either way. A wait shorter than a poll (0.05 s) passes any 0.1 s comparison. Both are "waits for an attempt" (R2). `values` pins the comparison in the AST; fault 2/`waits-half-a-poll` pins the wait check. | Keep `>` on real time: the 0.036–0.044 s round trip, more under load, is what failed. Keep `>` on the clock: fault 2/`waits-one-poll` (a one-poll wait) passes it. |
| **D3** (row 3): the row reads two private attributes, `pending._deadline` and `pending._answered`, to prove the probe read the row's clock. | Without it, a probe that took its deadline or its wait from the real modules would read 0.00 on the row's clock and pass "decided at the deadline" green. | Measure on the wall clock from the ending: a stall in the window still counts, and an ending a stall delays past 0.15 s makes "posts at the deadline" pass (research § What a reference point can and cannot remove). |
| **D4** (shared helper): `not_run_violations`' time message names the slack and two decimals; 13 call sites' messages change (10 direct, 3 through `_not_run_violations`), no check does; the cases whose fragment quotes it (`past its`) rerun in `cases`. | R7: row 1 misses 3 s + 0.5 s, and `.1f` prints 3.54 s as 3.5. | A row-local copy of the check: a second assertion of the same bound. |
| **D5** (R2–R4 evidence, a reading): beside R5's protocol, each row runs under an in-process stall (`verify/srtt_stall.py`) on HEAD (must pass) and on the base (must fail with the sighting's words). | R5's protocol runs each row in a fresh process beside spinners; the source behind the sightings is the row's own process (research § The load protocol's reach). The protocol is still run in full (P6); the controls add to it. | The protocol alone: every base row passed every planning-sample run under it, so it cannot tell the cycle's rows from the base's. |
| **D7** (row 3, a residual for sign-off): a worker-side delay through a real primitive the row does not route (a fresh `__import__('threading').Event().wait(t)`, a socket timeout) leaves the row's clock at 0.00. It is caught only by the unchanged wall check, `took <= BOUND + SLACK`: detection limit 0.8 s for that kind, against the base row's 0.15 s. Sleeps (`time.sleep` by any route), the probe's own `Event` and its deadline are on the clock (faults 3/*). | Any real-time check from the ending to the verdicts is the base row's exposure again (a collection in that window, research § The full suite's own pauses). | A real-time 0.15 s check from the ending to the post (the reviewer's H1 alternative): it puts the row back under the stall the cycle exists to remove. |
| **D6** (R5, a reading): the 20 runs alternate eras (odd runs handshake, even modern), and a row is all its tests in one pytest process (row 3: its 56 RAISED parameters; row 4: its 192). | R5 names no era; the gate runs each row once per era (R8). | 20 per era doubles a ~20 min background run on a shared host. |

## 4. Rabbit holes (resolved)

- **Row 1's "0 workers": a product defect?** No. Every probed run started exactly one worker; the
  abort ends it 0–0.11 s after the return, once before it; a 0.05 s delay before the listing lost it
  2 of 3 times, 0.2 s 3 of 3 ([research](research/01-where-the-time-goes.md) § Row 1). The count is the
  bug; no `fix` seed.
- **Where rows 2–4 spend their time.** Row 2: 94 % in the MCP round trip, 0.0 s in the executor, no
  fake advance. Rows 3–4: under a millisecond beyond row 4's own 0.3 s wait. Spinners moved nothing;
  the full suite's generation-2 collections (to 125 ms here) did (research §§ Row 2, Rows 3 and 4,
  The full suite's own pauses).
- **Is (a) possible per row?** Rows 1–3 yes (§ 2). Row 4 no: evidence above; D1 or (c).
- **Do the existing mutation cases still bite?** The 32 cases naming the rows keep their `why`
  prefixes. Two (`probe-worker-catches-exception`, `probe-worker-re-raises`) leave the worker dead with
  no post: on the probe clock the deadline comes when the worker has ended, so they still fail at once
  with the "did not answer" reason. Run in P5.
- **Adversarial design review** (trigger 3; one pass, appetite small): see § 7.

## 5. Risks & open questions

- **For the maintainer: row 4, D1 or (c).** Figures, from this plan's runs and the profile's baseline:

  | | Before (base) | D1 (proposed) | (c), slack 1.0 s |
  |---|---|---|---|
  | Bound, hang / timeout-code | 0.3 + 0.5 = 0.8 s | 0.8 s | 0.3 + 1.0 = 1.3 s |
  | Bound, other endings | 0.5 s | 0.5 s | 1.0 s |
  | Row 4 alone, max (576 tests) | 0.3125 s / 0.0011 s | same | same |
  | A 100.5 ms in-suite collection inside a start | charged | not charged | charged, within slack |
  | Control 4 on the cycle's row (the same collection) | — | 192 of 192 pass | pass (0.6 + 0.3 < 1.3) |
  | Fault `waits-past-the-bound` (hang start measured 0.91 s) | killed | killed | survives (< 1.3 s) |
  | Fault `joins-the-hung-worker` (hang start measured 1.01 s) | killed | killed | survives (< 1.3 s) |
  | Fault `waits-after-the-answer` (other endings, measured 0.60–0.61 s) | killed | killed | survives (< 1.0 s) |
  | Control 4 on the base (a 0.6 s first collection, armed in each start) | 143 of 192 fail (the rest took theirs on the probe's worker, inside its own wait) | — | — |
  | CI job time (`suite-legacy-4` / `suite-modern-4`, budget 10:00) | 7:22 / 7:33 | unchanged: the row's tests take the same time; the bound is a ceiling | unchanged |

  D1's residual: a stall that is not a collection (a CI runner losing its CPU for > 0.5 s) still
  fails row 4. The single row-4 sighting (0.85 s on CI) cannot be attributed from its log; a
  recurrence after D1 would be evidence for (c), at that time, with its own figures.
- **D2, D4 and the D5/D6 readings** are listed for sign-off; none bends an R-ID's words.
- **The row clocks see the waits that go through them.** Row 2's clock sees `ssh._await` and
  `ssh.time`; a wait another way is caught by its real-clock check of `_ensure_connected` (fault
  2/`waits-off-the-clock`), at the cost of a 0.1 s real bound on a 0.0001 s interval, which a stall of
  0.1 s inside that interval would still fail (residual, rare: the interval is 1000 times shorter
  than the round trip that failed). Row 3's engagement check covers the deadline, the event and the
  worker's start; a worker's real wait on another primitive is D7.
- **Out of scope, unchanged:** row 3's 0.8 s wall check and every other wall-clock read in the suite
  (Non-goal: a suite-wide sweep); the loopback SSH breaks (`issues/loopback-ssh-breaks-under-load.md`)
  may redden P6's beside suite, whose result is recorded, not graded.
- **Sibling cycles.** `full-volume-fixture-leaks-hdiutil` edits `tests/test_ssh_exec.py`'s fixture
  region; this cycle's hunks are the two row bodies and one helper line, far from it. The gate imports
  `tests/mutants.py`'s `Case` and `run_case`, which `mutants-workflow-timeout` and
  `mutant-child-outlives-timeout` may change: if a signature moves, the gate's `faults` and `cases`
  follow it, and the runner is never edited here. The two existing cases above now take one worker's
  end (milliseconds), not 0.3 s.

## 6. Verification strategy

One gate script, `verify/timing-gate.py`, offers its parts as modes (code-plan 6.9); P1–P4 run `row
<n>`, P5 the sweep, P6 the load protocol. Footprint: one child at a time.

- **What every mode reads.** The staged tree (`git write-tree`), as code-build stages before a
  phase's verify: never HEAD (the previous phase) and never an unstaged working copy (a mode that runs
  tests refuses one). Records name the staged `tests/` tree and the gate's own blobs.
- **`values`, `scope`** (static, ~5 s): R9 and the Non-goals from the staged text, by AST; an added-line
  scan of the three modules (from the merge-base with `origin/develop`) for skips, retries, broad
  `except`s and load conditions; R8's file list and per-era collection; and the gate pinned: a gate
  script changed since the plan commit must be named, with its reason, in `verify/amendments.txt`.
- **`rows <n>`**: the row's tests in both eras.
- **`faults <n>`**: the decision list below, each a `mutants.Case` planted in a copy of the namespace
  and run by `run_case`; every target must fail with the fragment. Each fault is sized just past its
  bound, so a row that widened its own slack lets it survive.

  | Row | Fault | Property (direction: still fails when broken) | Fragment |
  |---|---|---|---|
  | 1 | `gives-up-late`: poll gives up at deadline + 0.7 s | the call gives up within 3 s + 0.5 s | `past its 3 s bound and 0.5 s of slack` |
  | 1 | `starts-no-attempt`: gives up before any attempt | one attempt reaches the host | `no attempt reached the silent host` |
  | 1 | `two-workers`: two workers per attempt | exactly one worker (a count of one kind only, or a set, passes this) | `2 reconnect workers started during the call, not one` |
  | 1 | `abort-closes-nothing` | the abandoned worker ends within 1.0 s | `still running 1.0 s after the call gave up` |
  | 1 | `window-one-factor-more`: window 4 s | window 3 s from a 1 s bound | `window, not 3 s` |
  | 2 | `waits-out-the-deadline`: slot freed, no give-up, waits to the deadline | gives up at once (the message alone is unchanged) | `on the row's clock` |
  | 2 | `waits-one-poll`: one 0.1 s wait, then gives up | at the bound: `>=` | `on the row's clock` |
  | 2 | `waits-half-a-poll`: one 0.05 s wait | any wait on an attempt | `waited on an attempt` |
  | 2 | `retries-after-backoff`: no give-up, backoff, retry | gives up with the failure | `on the row's clock` |
  | 2 | `waits-off-the-clock`: a real `Event().wait(ATTEMPT_POLL)`, then gives up | any wait, by any route | `from entering its reconnect to giving up` |
  | 3 | `decides-at-the-deadline`: verdicts sleep to the deadline | decided before the deadline | `decided only at the deadline` |
  | 3 | `posts-at-the-deadline`: both posts wait for the deadline | the same, from the worker's side | `decided only at the deadline` |
  | 3 | `reads-the-answer-when-the-wait-runs-out`: no `set()`, answer read at the timeout | the same, by the event | `decided only at the deadline` |
  | 3 | `worker-sleeps-off-the-clock`: `__import__('time').sleep(0.25)` before the worker's post | the same, by the real `time.sleep` | `decided only at the deadline` |
  | 3 | `deadline-off-the-rows-clock` / `wait-off-the-rows-clock` | the instrument is engaged | `did not take its deadline and its wait on the row's clock` |
  | 4 | `waits-past-the-bound`: the wait runs to 3× the bound | a start never waits past the bound + slack | `the start took` |
  | 4 | `joins-the-hung-worker`: joins the probe's worker for 1.0 s | the same, outside the probe | `the start took` |
  | 4 | `waits-after-the-answer`: 0.6 s sleep after the verdicts | the same, anywhere in the start | `the start took` |
  | 4 | `collects-slowly-in-the-start` (added at the D1 ruling): an explicit collection inside the start that takes 0.6 s | the same, and the failure names the collector's share | `the collector pausing it`, and a pause of at least the planted 0.6 s (a predicate, TECH Amendments) |

- **`controls <n>`** (the other direction: does not fail when bounded): `verify/srtt_stall.py` stalls
  the row inside its own interval: row 1, 0.3 s on the main thread after the call's time is taken and
  before the workers are counted (at the first `threading.enumerate` or `Thread.join` after the return); row 2,
  0.3 s inside the MCP call after the give-up; row 3, 0.2 s as the worker handles the ending (past the
  base's 0.15 s cut, short of the deadline, as the sightings were); row 4, the first collection during
  the start made 0.6 s slow, thresholds lowered so one comes. The tree under test must pass, every
  test; the base must fail, with the sighting's own words (`reconnect workers ran, not one`, `not
  giving up at once`, `decided only at the deadline`, `the start took`), in each era. Both trees are
  read from git (`git archive`), the tree under test from the index.
- **`cases`**: `tests/mutants.py --self-check` on the 32 existing cases (R6's second clause), the cases
  whose fragment quotes `not_run_violations`' message (`past its`, D4), and the runner's controls.
- **The sweep record.** `sweep.txt` is appended; each line names the staged `tests/` tree and the
  gate's blobs. `sweep-check` wants a green line per part for this tree and gate, and fails on any red
  line for them: a red is not washed out by a later green on the same tree (it goes to the foreman).
- **`profile`**: the profile's `verify` with `PYTEST_ADDOPTS=-rA`; the record counts each row's PASSED
  lines (twice its tests, once per era), so a skip or a missing row fails `profile check` (R8).
- **Gate-decision mutants** (planning, § 7): a row that lists threads after the return, compares with
  `>`, drops row 2's wait check, widens a slack, skips under load or drops `collector_paused()` each
  turns its phase gate red.
- **R5 (P6):** `verify/load-protocol.py run`, in the background (about 20 minutes): 20 runs alone,
  then 4 CPU spinners (`python -c 'while True: pass'`, one session each) and the profile's suite
  commands cycling beside 20 loaded runs; a loaded run counts only when one suite command ran beside
  the whole of it (one that spans a command's end is recorded and made again); the suite is never
  killed, the spinners' process groups are killed and checked gone. The record is appended; `check`
  grades every run on the staged tree, recounting the run lines (not the summaries), and wants macOS
  and no failed run. Mechanics dry run on the folded prototype (`run --runs 2`, a planning-only
  override `check` ignores): 239 s, every row 2 of 2 alone and loaded (load 5.4–5.7, the first suite
  command beside every loaded run), `check` refusing 2 of 20 as it should, no spinner left. Planning sample (4 `yes` spinners and one `-k 'not silent'` command beside,
  load 6–7): row 1 8 of 8, row 2 10 of 10, row 3 5 of 5, row 4 3 of 3, all on the base's rows.
- **R8 times:** P5's `times` part times each touched module three times on the base archive and on
  the tree, handshake era. Planning (pytest's own figure, a quiet moment): `tests/test_probes.py`
  6.74–6.95 s on the prototype against 6.77 s on the base; row 4's 192 tests 5.4 s both; rows 1–2
  3.1–3.4 s and 0.16–0.3 s both. A single loaded run is mostly load: the dry run's one-shot `times`
  read `tests/test_probes.py` at 7.9 s (base) and 14.6 s (prototype) at load 5.9, and pytest's own
  figure for the prototype minutes later was 6.74 s; hence three runs. CI job times are read at
  landing, as the profile says.
- **Measured gate times.** Before the review's folds (prototype's final tree, load 4.6–5.9 from other
  sessions): `sweep 1` 43 s, `sweep 2` 19 s, `sweep 3` 41 s, `sweep 4` 130 s, `sweep cases` 81 s,
  `sweep times` 87 s at one run each. After them (controls in both eras, 43 cases): row 4's parts
  13 s, 13 s and 234 s (its control, both eras, the base's 192 starts each charged a 0.6 s collection),
  `cases` 198 s. So `row 4` and `sweep 4` take about 4.5 min, `sweep times` about 4.5 min at three
  runs, the rest under 2 min each; none near the 10-minute cap. The profile's `verify` on the
  prototype: exit 0 in 1605 s (both eras; 4311 passed and 14 skipped in each fourth command).

## 7. Adversarial review

One pass (trigger 3, appetite small), by a fresh reviewer given GOAL, the drafted PLAN and TECH, the
research brief, the three gate scripts and the prototype's diff, with a throwaway clone to plant
faults in. It ran two plants through `mutants.run_case` itself. Every finding is folded in; none
needed a stop.

| Finding | Severity | What it showed | Fold |
|---|---|---|---|
| H1 | HIGH | Row 2: a real `Event().wait(ATTEMPT_POLL)` before the give-up survived the new row (the base killed it). Row 3: `__import__('time').sleep(0.25)` before the worker's post survived (the base killed it). The draft's claim that row 3's engagement check covered such a change was wrong. | Row 2 adds the real-clock check of `_ensure_connected` (§ 2); row 3 routes the real `time.sleep` to its clock. Both plants join the fault list (`waits-off-the-clock`, `worker-sleeps-off-the-clock`). A worker's wait on another real primitive stays a residual: D7. |
| H2 | HIGH | A skip or retry keyed on full-suite conditions passed every part: faults run quiet, the protocol runs fresh processes, `profile check` read only the exit status; `values` skipped nested functions, aliases, `raise …Skip…`, module marks and retry loops. | `values` walks nested functions and raises, checks decorators against an allow-list, and scans every added line of the three modules for skips, retries, broad `except`s and load conditions; `profile run` uses `-rA` and `check` wants each row PASSED once per era. |
| M1 | MEDIUM | Gates mixed HEAD (the previous phase, since code-build verifies before it commits) with the working copy, and stamped records with HEAD's tree. | Every mode reads the staged tree; a test-running mode refuses an unstaged working copy; records name the staged tree. |
| M2 | MEDIUM | `sweep-check` and the load record let a re-run wash out a red. | `sweep-check` fails on any red for the tree and gate; the load record is appended and every run on the tree is graded. |
| M3 | MEDIUM | The gate itself could be edited after sign-off and re-run green. | Records carry the gate's blobs; `scope` wants each gate script changed since the plan commit named in `verify/amendments.txt`. |
| M4 | MEDIUM | Control 1 stalled inside the interval it times (3.34–3.42 s against 3.5 s on a quiet host). | The stall is armed at the call's return and taken at the next `threading.enumerate` or `Thread.join`: after the time is read. |
| M5 | MEDIUM | A loaded run spanning a suite command's end was recorded as "suite yes"; `check` trusted summary lines. | A run counts only with one command beside the whole of it; `check` recounts the run lines and wants macOS. |
| L1 | LOW | Row 1's hook was removed before the joins; another executor's worker could count. | Hook kept through the joins; workers filtered by target. |
| L2 | LOW | Row 2 recorded every `_await`, a finished one included; the message named no bound. | Only waits on an unfinished attempt; the message names the count and the time asked. |
| L3 | LOW | D2's reasoning was wrong: `>` passes a one-poll wait exactly, not by rounding. | D2 rewritten; the comparison rounds to 1e-9. |
| L4 | LOW | D4's "16 call sites" counted definitions; the cases quoting the message were not rerun. | 13 call sites; `cases` adds the `past its` cases on `ssh.py`. |
| L5 | LOW | Row 4's message printed "the probe's bound (0 s)" for answered endings. | It names the bound missed and what it is made of. |
| L6 | LOW | `ProbeClock`: a main-thread sleep could race a worker; a wait on a worker thread counted itself alive; no worker check; `perf_counter`, `monotonic_ns` unproxied. | Sleep settles the other workers first; liveness excludes the waiting thread; the engagement check wants a worker; both readings proxied. |
| L7 | LOW | `scope` diffed from a fixed base, so a rebase onto siblings' commits would fail good work. | Diffs from the merge-base with `origin/develop`. |
| L8 | LOW | Controls ran in one era. | Both eras. |
| L9 | LOW | Code checks matched text, so a comment could keep a bound while the code widened it. | Code checks match the row's AST (nested functions included); message checks stay textual. |

The reviewer's figure checks: D1's bounds and survivors, the test counts and the case count held; the
control-4 wording (143 of 192, not every start) is corrected in § 5.

Gate-decision mutants run in planning against the prototype's row gates (before the folds): a row 2
compared with `>` (the faults stayed green on that draft, so the comparison is now pinned in
`values`' AST check), a row 2 without its wait check (fault
2/`waits-half-a-poll` survived: gate red), a row 1 that lists threads after the return and a row 4
without `collector_paused()` (the base's rows: controls 1 and 4 red on them).

---

*Backing research: [`research/01-where-the-time-goes.md`](research/01-where-the-time-goes.md) (no
fan-out: one planner's probes, so no digest).*
