# 01 — Where each row's time goes, by executed probe

Planning probes, 2026-11-09, macOS 27.0.1 on a 10-core host (load 2.2–2.9 before any probe), Python
3.14.6, the four rows of `develop` at `0bfacae` (identical in `tests/` to the GOAL's `abe12e3`).
Each probe instrumented a throwaway copy of the row in a prototype worktree and wrote one JSON line
per run; no product code was touched. Figures are the probes' own output.

## Row 1 — the count of reconnect workers is a race, not a missed bound

The row lists live threads named `cluster-mcp-reconnect` once `executor.run` has returned. Probe: a
`Thread.start` hook recorded every worker as it started, a wrapper on `SSHExecutor._settle` stamped
the moment each worker ended, and an optional sleep (`PROBE_DELAY`) sat between the call's return
and the listing.

| Delay before listing | Runs | Workers started | Workers listed | Worker ended after the return |
|---|---|---|---|---|
| none | 10 | 1 each | 1 each | 0.061–0.108 s |
| 0.05 s | 3 | 1 each | 0, 1, 0 | 0.002–0.071 s |
| 0.2 s | 3 | 1 each | 0 each | −0.0002–0.110 s |

Every run started exactly one worker, and the call gave up at 3.000–3.010 s. The abort the call
makes at its deadline ends the worker 0.0–0.11 s after the call returns, once before it. So any
delay of the row's main thread between the return and the listing longer than that loses the
worker, and the row says "0 reconnect workers ran, not one": the text every kept failure carried.
The product behaves; the row's count is wrong. A full suite supplies the delay (below).

## Row 2 — 94 % of the measured interval is the MCP round trip, not the executor

The row times the whole `run_command` call through the in-memory client, on `FakeClock.elapsed()`
(real time plus the fake offset). Probe: a wrapper on `SSHExecutor._ensure_connected` stamped its
entry and exit and the fake clock's offset.

| Load | Runs | Call (s) | Before the executor | `_ensure_connected` | After it (MCP reply) | Fake advance |
|---|---|---|---|---|---|---|
| alone | 10 | 0.039–0.047 | 0.002–0.003 | 0.0000 | 0.036–0.044 | 0.0 |
| 4 spinners + a suite chunk | 10 | 0.041–0.046 | 0.002–0.003 | 0.0000–0.0001 | 0.037–0.044 | 0.0 |

The executor gives up in under 0.1 ms and never advances the fake clock; the rest is the client and
server around it, real time a busy host or a collector pause stretches. A fresh process's first run
failed once in this session (alone, load 2.5, not instrumented), its first MCP call slower.

## Rows 3 and 4 — decided in under a millisecond; the outliers are in-process pauses

Row 3 (the 56 RAISED parameters) and row 4 (192 parameters), alone and under load:

| Row | Load | Tests | Max (s) |
|---|---|---|---|
| 3 | alone, 3 runs | 168 | 0.0002 |
| 3 | 4 spinners + a suite chunk, 5 runs | 280 | 0.0003 |
| 4 hang / timeout-code | alone, 3 runs | 96 | 0.3125 (the 0.3 s bound itself) |
| 4 others | alone, 3 runs | 480 | 0.0011 |
| 4 hang / timeout-code | loaded, 3 runs | 96 | 0.3151 |
| 4 others | loaded, 3 runs | 480 | 0.0026 |

For row 4 the time before the probe starts (load, ladder, executor, budget, site read, compose) was
≤ 1.1 ms in every run, and after its verdicts ≤ 0.7 ms: the start's time is the probe's own wait.

CPU spinners beside the rows did not move any figure: the CI sightings (0.18–0.25 s for row 3,
0.85 s for row 4) are not host CPU contention of this kind.

## The full suite's own pauses

The gate's fourth command (every module but the four `--ignore`d), run once with a collector
callback (`gc.callbacks`) recording every collection over 10 ms: 4310 passed, 222 s. Thresholds
`(2000, 10, 10)`; 21 collections over 10 ms, every one generation 2, 29.5–125.0 ms, rising as the
heap grows (`test_storage_resource.py`: 104–125 ms). One landed inside row 4:
`exit-1-local-stdio-core-only`, a 100.5 ms collection, and that parameter took 0.1009 s against
0.0003 s alone. A generation-2 collection holds the interpreter: it is charged to whatever interval
is open on the main thread, and it is load the row's own process makes, which no number of spinners
in other processes reproduces.

So the sightings' mechanism, in each row:

- Row 1: any stall of the main thread between the call's return and the listing (a collection,
  being descheduled, waiting for the GIL behind the suite's other threads) longer than the worker's
  0–0.11 s.
- Row 2: a stall anywhere in the MCP round trip, which the row times though it is no wait of the call.
- Row 3: a stall anywhere between `start()` and the verdicts' return: 0.15 s is a third of the 0.30 s
  between "as it happens" and "at the deadline", and one collection on a CI runner is enough.
- Row 4: a stall inside the start, which is the probe's own window: no reference point inside the
  start excludes it.

## What a reference point can and cannot remove

- Rows 2 and 3 measure an ordering (did the call wait on an attempt; was the ending decided before
  the deadline). On a clock only the code's own waits move, the measured value is 0 however long
  the host takes, and a wait to the deadline still moves it the whole bound. This is the
  Clarifications' "clock the test controls".
- Row 1 needs no clock: counting each worker as it starts removes the race.
- Row 4's property is a real duration ("never waits past the probe's bound") in which any wait
  anywhere in the start counts (a join, a sleep), so the row must keep a real clock; moving its
  reference point to the probe's start removes ≤ 1.1 ms. What can be removed is the collector's
  pause, by pausing the collector for the timed start (as `timeit` does), or what is left is the
  slack (fallback (c)).

## The load protocol's reach

R5's protocol runs each row in its own process beside spinners and a suite. The in-process source
above never reaches such a run: the row's process is fresh, its heap small. The protocol can show a
row stays green under host load; it cannot show a row stays green under the pauses that produced the
sightings. Hence the in-process controls (`verify/srtt_stall.py`), which stall each row inside its own
interval: the base's rows fail under them with the sightings' own words, the cycle's rows must not.
