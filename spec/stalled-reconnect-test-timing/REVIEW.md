# REVIEW — Real-time tests fail on behaviour, not on a busy host

> Adversarial QA by `code-review`, run in an isolated context (a fresh blind subagent at effort
> xhigh). The correctness pass grades the branch diff against [`GOAL.md`](GOAL.md) + the repo's
> `AGENTS.md` § Invariants **only** — it does not see `PLAN.md`/`TECH.md`. Every finding cites an
> **executed** command, not an assertion.

- **Reviewed commit:** `0dbb3ff` (the code under review is `8cb9e3f`; `0dbb3ff` adds only this
  review's seed pair, `issues/timing-rows-unrouted-waits.md` and its `ROADMAP.md` entry)  ·
  **Base:** `origin/develop` `146cbc6`  ·  **Date:** 2026-11-10
- **Verdict:** approved
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md`
- **Mode:** a fresh blind pass over the full spec-excluded diff; the sequential fallback did not run.

## Pre-flight

- Branch `test/stalled-reconnect-test-timing`, tree clean, HEAD `8cb9e3f`, `next_phase.py`:
  `in_review`, 6 of 6 phases done, `review.cycle` 0, no warnings.
- Spec-excluded diff: 6 files, +319/−20 (`tests/test_ssh_exec.py`, `tests/test_probes.py`,
  `tests/test_probe_startup.py`, `issues/stalled-reconnect-test-timing.md`,
  `issues/loopback-ssh-breaks-under-load.md`, `ROADMAP.md`).
- **Contract drift:** `GOAL.md` moved after its shape commit only by `af1012e`, the dated GOAL-gate
  clarifications, which the foreman confirmed as legitimate. The other recorded maintainer answer
  is the D1 ruling (TECH amendments, 2026-11-09): row 4 times its start with the collector paused, and
  a row-4 failure reports the collector's pause. The blind reviewer was not given D1; it raised no
  flag on `collector_paused()` or `gc.disable`, and graded R4 met with `collector_paused()` in place,
  so there was nothing to reconcile. The rebase map from the TECH amendments applies: the frozen
  records' `abe12e3`/`758e7d1` are `af1012e`/`64137f6` on this branch.

## Verification run

**Orchestrator, the spec-held gates, light modes** (`verify/timing-gate.py`, tests tree `9d82fd2c`,
gate `72c2ab5596+b2d822f751`; evidence in `.local/review1/orchestrator/`):

- `values` and `values 1 2 3 4` → ok (R9's constants, no skip/xfail/flaky/early return, each row's
  reference point and R7 message fragments present).
- `scope` → ok (touched files within the allowed set, gate scripts' changes named in
  `amendments.txt`, the four rows collect the same ids as BASE in both eras). Re-run after staging
  the seed pair → ok.
- `ledger` → ok (re-run after staging the seed pair → ok).
- `sweep-check` → ok: every sweep part (1–4, `cases`, `times`) green on this tests tree and gate, no
  red on them.
- `sweep times` → green, 213 s, load 2.3–2.9 (each touched row's module three times, BASE
  `af1012e` vs HEAD, handshake era):

  | target | BASE | HEAD |
  |---|---|---|
  | row 1 (one test) | 4.4–10.1 s | 4.3–4.5 s |
  | row 2 (one test) | 1.1–1.3 s | 1.1–1.2 s |
  | `tests/test_probes.py` (167) | 7.8–7.9 s | 7.8–7.9 s |
  | `tests/test_probe_startup.py` (405) | 21.1 s | 21.0–21.1 s |

  The mode appends to the tracked `verify/sweep.txt`; the appended lines are kept in
  `.local/review1/orchestrator/sweep-appended.txt` and the file was restored, so the committed record
  is unchanged.
- `load-protocol.py check` → "every row 20 of 20 alone and loaded on this tests tree".
- `timing-gate.py profile check` → ok (`profile-verify.txt`, 2026-11-10 06:26: the profile's verify
  exit 0 in 1537 s on tests tree `9d82fd2c` and packages tree `c35f446`; rows passed 2/2, 2/2,
  112/112, 384/384, once per era).
- The full sweep and the load protocol were not re-run: the light parts graded every claim.
- **A listed-mutant gate can't grade an open-ended class.** The gate's `faults` (about twenty named
  product faults across rows 1–4) and `cases` are a fixed list: they prove each listed fault is
  killed, not that the class it samples is closed. This repo has no generated diff sweep for Python,
  so class coverage rests on the blind reviewer's hand-planted faults, graded per
  `method/mutation-testing.md` § When a review is done.

**CI** (foreman, observed): run 42807663490 on `8cb9e3f`, green, all 9 jobs, 6:14 wall.

**Blind reviewer** (evidence in `.local/review1/reviewer/`):

- Narrowed profile verify, both eras (`verify-narrowed.log`): `uv lock --check` exit 0;
  `-k silent` 44 passed (211.5 s / 211.4 s); `-k 'not silent'` 154 passed (145.0 s / 145.0 s);
  `test_probes.py test_probe_startup.py test_mutations.py` 1748 passed (40.1 s / 43.6 s);
  `bin/sandbox.sh uv run cluster-mcp --help` exit 0.
- Hand-planted faults in tree copies (`planted.log`, `planted-on-base.log`,
  `planted-r2-realhalf.log`): one killed fault per R1–R4 property (list under the matrix); two
  deeper-layer survivors (coverage observations below).
- `tests/mutants.py --self-check` on the 32 `CASES` that target in-scope rows: all killed, the
  runner's controls passed (`mutants-touched.log`); the 23 cases on rows that share the reworded
  `not_run_violations`: all killed (`mutants-helper.log`).
- Load probes: 4 CPU spinners in their own process group beside a suite part, load 6–9 on 10 cores;
  every in-scope row instance passed 21 times alone and 40 times under load; rows 2–4 also in situ
  inside their suite parts (`load-p2*.jsonl`, `load-p4*.jsonl`, `alone.jsonl`). The longest
  collector pause in the row-2 process under load was 46 ms.
- Collection per gate part, both eras, against base (`collect-summary.log`): p1 44, p2 154, p3 507,
  p4 4383 (base 4149, plus the unchanged `test_audit.py`, which does not collect in a copy without
  `uv.lock`); each in-scope row in exactly one part, once per era.

## Requirement → evidence matrix

| R-ID | Implemented by | Verified how | Who | Status |
|------|----------------|--------------|-----|--------|
| R1 | row 1, `tests/test_ssh_exec.py:2183–2200` (a patched `Thread.start` counts this executor's workers as they start); `not_run_violations` | positive probe, worker ends before `run` returns: base red "0 reconnect workers ran, not one", head green (`r1-worker-ends-first.log`); faults gives-up-late, no-attempt, no-worker, two-workers, abort-closes-nothing all killed (`planted.log`); gate `sweep` part 1 green | reviewer; orchestrator (sweep record) | ✅ |
| R2 | row 2, `tests/test_ssh_exec.py:2053–2113` (offset on the row's clock, `waits`, the real `_ensure_connected` span) | faults waits-a-poll, waits-half-a-poll, waits-a-real-poll, sleeps-a-backoff killed; 21 alone and 40 loaded passes, in situ too; gate part 2 green | reviewer; orchestrator | ✅ (one coverage observation) |
| R3 | `ProbeClock`, `tests/test_probes.py:277–380` (`waited < BOUND / 2`, the `engaged` check) | faults posted-at-the-deadline (14 rows) and reason-read-at-the-deadline (13 rows) killed; 7,168 row-runs loaded plus 128 in situ passed; gate part 3 green | reviewer; orchestrator | ✅ (one coverage observation) |
| R4 | `collector_paused()`, `tests/test_probe_startup.py:410–440` (D1); bound and measure unchanged | faults hang-waits-past-the-bound and at-once-waits-half-a-second killed; under load `main()` at most 0.313 s against 0.8 and 0.001 s against 0.5; gate part 4 green, including `collects-slowly-in-the-start` | reviewer; orchestrator | ✅ |
| R5 | `verify/load-runs.txt` (committed artifact) | read the record and ran `load-protocol.py check` → every row 20 of 20 alone and 20 of 20 loaded, macOS, tests tree `9d82fd2c` (HEAD's) | orchestrator (artifact R-ID) | ✅ (observations for the maintainer below) |
| R6 | the gate's planted faults; `mutants.CASES` | gate `sweep` parts 1–4 and `cases` green on this tree (orchestrator, `sweep-check`); reviewer's own plants, one killed per property; `ssh-reconnect-unstarted-worker-holds-slot` and all 32 in-scope cases killed | both | ✅ |
| R7 | failure messages: `not_run_violations` `:1273`; row 2 `:2105–2113`; row 1 lingering `:2213`; row 3 `took`/`waited`; row 4 `:509–511` | planted-fault failures showed interval, value and bound; gate `values` MESSAGES fragments present | reviewer; orchestrator | ✅ |
| R8 | no change to `.github/`, `AGENTS.md`, `pyproject.toml`, `uv.lock`, `packages/`, `bin/` | `git diff --stat` on those paths empty; collection per part both eras; profile record rows once per era; CI run 42807663490 green, 9 jobs, 6:14 wall, inside the 10-minute job budget | reviewer; orchestrator; foreman (CI) | ✅ |
| R9 | constants unchanged | `STALL_*` 3/0.5/1.0, `ATTEMPT_POLL` 0.1, `BOUND/2` 0.15 against 0.3, row 4's 0.8/0.5; row 2's `spent > 0.1` became `round(spent, 9) >= 0.1` on the row's clock (same value, stricter); gate `values` ok; no fallback taken | reviewer; orchestrator | ✅ |

Unmapped changes (possible scope creep): none. The `ROADMAP.md` and `issues/` edits carry out the
GOAL's split-out of the loopback seed; the reviewer checked their prose against the repository
(cited rows and `CLUSTER_MCP_TEST_EVERY_KIND` gating exist, Part I 28→29, executor group 6→7,
status lines consistent). § Conventions spec-id grep: the only R/P ids in the diff are in
`issues/loopback-ssh-breaks-under-load.md` prose; `test_no_spec_ids_in_the_package_or_the_suite`
passed.

## Findings

None: no CONFIRMED and no PLAUSIBLE findings.

The reviewer's refuted candidates, for the record:

- Row 2's real-time `ensured >= ATTEMPT_POLL` check as a flake mechanism: the bounded span measured
  0.021–0.080 ms against 100 ms, alone, under load and in situ; dropped.
- A collector or monitor thread moving row 2's fake clock or recording a wait: only the calling
  path uses `_await`; the liveness monitor waits on real Events (`ssh.py:1025`, `:1044`); the only
  long sleep is on the KILL path (`:293`), which the row never reaches; dropped.
- `test_probe_startup.py::test_an_interrupt_while_waiting_for_the_probe_interrupts_the_start` (not
  an in-scope row) was red in the reviewer's loaded part 4. Run 1, loaded and started with `&`: red,
  because the background start inherits SIGINT as ignored. Run 2, alone: 4 passed. Backgrounded
  without load: red again. Backgrounded with SIGINT reset: passed (`interrupt-rerun.log`). The red
  was the probe harness, not load or the diff; dropped.

### Coverage observations (seeded)

Each is a deeper layer of a property class a planted fault already pins on these rows. Seeded as
`issues/timing-rows-unrouted-waits.md` with its `ROADMAP.md` entry, commit `0dbb3ff`.

- Row 3 misses a deadline sleep through `time.sleep` bound at import (`_wall_sleep`), which the
  row's clock does not route: all 14 raised rows green on head, every raised row red on base. The
  class is pinned by posted-at-the-deadline and reason-read-at-the-deadline, both killed.
- Row 2 misses a sub-poll wait made directly on `pending.done.wait(0.05)`, bypassing `_await`:
  green on head, red on base ("took 0.1 s") only through the wall-clock measure that made it flaky.
  The class is pinned by waits-a-poll, waits-half-a-poll and waits-a-real-poll, all killed.

### Observations for the maintainer (R5's load, not findings)

- The recorded loaded runs reached a 1-minute load of only 2.6–6.1 on 10 cores; the blind
  reviewer's own load probes reached 6–9. The GOAL's before-figure for row 2 (12 of 20) was at load
  22–26. The protocol as the Clarifications word it (four spinners beside a full-suite run) was
  met; the load it produced on this host is well below the sighting conditions.
- The beside suite ran the profile's suite commands in order and, over the whole loaded phase,
  reached only its first two (`tests/test_ssh_exec.py -k silent`, 217 s, and `-k 'not silent'`,
  154 s). Every loaded run had a suite command beside it, but no loaded run had the probe or
  remaining modules beside it.
- The controls (`timing-gate.py controls`: under a planted stall, each row passes on HEAD and fails
  on BASE with its sighting's text) are the stronger evidence that load no longer reds the rows;
  they are green in the sweep record.

## Human-gate triggers

- Not triggered: there is no CONFIRMED finding, and the diff touches no path on § Invariants'
  high-blast-radius list and no `[human gate]` section (tests, `issues/` and `ROADMAP.md` only).

## Conduct

- Reviewer: `git status --porcelain` empty at hand-back; `.venv` freeze diff empty
  (`freeze-before.txt` vs `freeze-after.txt`); no build state mutated (mutants in the runner's temp
  copies, tree copies under `.local/review1/reviewer/tree-*`); spinners killed by trap, `pgrep`
  empty after each run and at the end; no cluster tools, commits, pushes, `spec/` or CI logs. `DONE`
  written 2026-11-10 07:16:29.
- Orchestrator: tree clean, `.venv` freeze unchanged across the review
  (`.local/review1/orchestrator/venv-freeze-{before,after}.txt`), no spinners left.

## Optional completeness sub-pass (separate reviewer; may see TECH.md)

- Not run (not requested).
