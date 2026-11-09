# GOAL — A dispatched mutation run finishes and reports every case

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** mutants-workflow-timeout
- **kind:** ci
- **appetite:** small

## Problem

`.github/workflows/mutants.yml` is the on-demand mutation run (`AGENTS.md` § Testing): on
`workflow_dispatch` it runs every case in `tests/mutants.py` (`mutants.CASES`) serially, in one
`ubuntu-24.04` job with `timeout-minutes: 30` (`mutants.yml:21-25`), and fails when a case survives,
when a report line is lost, or when no cases are found (`mutants.yml:36-45`). Each case is a child
pytest of its targets under `bin/sandbox.sh`, against a mutated copy of the namespace.

The job cannot finish. At `origin/develop` `0bfacae` the file defines **1,164 cases on Linux**
(1,165 on macOS, where `tpc-clobber` is also defined). A case was measured at about 2.5–5 s on a
development host (`spec/capability-probe/research/03-testing-and-budget.md` §5), which projects a
serial run at about **49–97 minutes** before the runner's own setup. The job is cancelled at 30
minutes, and a cancelled job reports nothing: none of the cases it did run reaches a verdict anyone
can read. The projection is not a measurement on the hosted runner. The workflow has never been
dispatched (`gh run list --workflow mutants.yml` lists no run, 2026-11-09), so the hosted
per-case cost is unknown.

The case count grows with nearly every cycle: 660 at `c520432`, 931 after `capability-probe`
(+271), 1,032 after `timeout-process-cleanup` (+101), 1,164 now. So an arrangement sized to
today's count alone fails again within a few cycles. `AGENTS.md` § Testing still says "a child
takes about 2 s, all cases about 3 minutes", true when the file had far fewer cases. The same
paragraph, and the workflow's header comment, say the workflow "becomes dispatchable at the
release that first carries it to `main`"; `main` has carried it since 0.1.5 (`d243aaf`), so that
sentence is stale too.

The cycle gates are unaffected: each phase runs its own cases under a 10-minute command cap, and
publish never reads this workflow (§ Factory, `ci` row). But this is the first "gates first"
entry of 0.2.0 (`ROADMAP.md` Part I): every later mutation gate rests on a full run that can
actually be run and read.

**Pre-existing:** yes. The run passed its timeout before `capability-probe` and has grown with each
mutation sweep since (`capability-extras` 241 cases, `capability-probe` 271,
`timeout-process-cleanup` 101).

## Outcome / vision

The maintainer dispatches the mutation workflow and, within a bounded wall time that keeps
holding as cases are added, gets a verdict for every case the file defines: killed, survived, or
killed for the wrong reason. `AGENTS.md` states what a full run really costs, measured on the
hosted runner, so the next cycle that adds cases can tell whether it still fits.

## Acceptance criteria (the contract)

- **R1** — WHEN the mutation workflow is dispatched, it SHALL run every case `tests/mutants.py`
  defines on the runner's platform, each exactly once, split across jobs each of which finishes
  within 10 minutes of wall time and carries `timeout-minutes: 20`, and SHALL finish with a reported
  verdict for every case before any of its jobs reaches its timeout.
- **R2** — WHEN a dispatched run finishes, the run SHALL fail IF any case survived, was killed for
  the wrong reason, or has no reported verdict, or IF no case was found; and its log SHALL name
  each such case. A run in which every case was killed SHALL pass. (The current single-job checks,
  carried across the split.)
- **R3** — WHEN cases are added to `tests/mutants.py`, the workflow SHALL run all of them with no
  edit to it. The recorded figures (R4) SHALL let a cycle that adds cases tell, without dispatching
  a run, whether the full run still fits the `mutants budget` bound.
- **R4** — `AGENTS.md` § Factory's profile SHALL gain a `mutants budget` row holding the bound (each
  job ≤ 10 minutes of wall time, `timeout-minutes: 20`) and the run's cost as measured at landing:
  the case count, the commit, the runs counted, and each job's wall time, the worst of the counted
  runs. `AGENTS.md` § Testing SHALL state that measured cost, replacing "a child takes about 2 s,
  all cases about 3 minutes", and point to the row.
- **R5** — `AGENTS.md` § Testing and the workflow's header comment SHALL state the workflow's
  current dispatch state (`main` carries it, so a run can be dispatched against any branch that
  has the file), not that it becomes dispatchable at a future release.

## Non-goals (no-gos)

- **Selecting cases by changed files.** R1 is a full run; a targeted or incremental mode is a
  separate decision.
- **Running on push or pull request, or gating anything.** The workflow stays `workflow_dispatch`
  only, and publish still never reads it (§ Factory, `ci` row unchanged).
- **The runner's case semantics.** No case's edits, targets or `why` change, and no test bound or
  wait is loosened, to make the run fit. Whether a case is killed is not this cycle's to change.
- **A child that outlives its timeout.** `run_child`'s `subprocess.run(timeout=300)` leaving a
  pytest behind is [`issues/mutant-child-outlives-timeout.md`](../../issues/mutant-child-outlives-timeout.md),
  its own cycle (in flight as `mutant-child-outlives-timeout`). It changes how the runner stops a
  hung case, not the limit: 300 s per case stays, and a hung case still costs up to about 310 s.
- **The timing-sensitive reconnect test.** [`issues/stalled-reconnect-test-timing.md`](../../issues/stalled-reconnect-test-timing.md)
  stays its own cycle; if the plan runs children concurrently, its rows are a known hazard the
  plan's risk section must face, not fix.
- **`ci.yml` and its `ci budget`.** The eight suite jobs, their 10-minute budget and their
  timeouts are untouched.
- **The macOS case set on CI.** The workflow runs on `ubuntu-24.04`; `tpc-clobber`, defined only
  on macOS, is out of its reach and stays a local case.

## Clarifications

- **Q1 — the run's timing bound.** Before: one job, `timeout-minutes: 30`, projected 49–97 min
  serial for 1,164 cases (2.5–5 s per case on a development host; never measured on the hosted
  runner), so it is cancelled with no report. The profile's `ci budget` row does not cover it (it
  binds jobs that run a suite command). — **A:** shard the run; each job finishes within 10 minutes
  of wall time and carries `timeout-minutes: 20` (the `ci budget` figures). At today's count that is
  about 6–13 jobs and about 10 minutes of wall time plus queueing; runner-minutes are the serial
  total plus each job's setup. The mechanism stays the plan's choice. Shard sizing assumes the
  sibling cycle `mutant-child-outlives-timeout`'s behaviour: a hung case is still stopped at the
  300 s per-case limit and costs up to about 310 s of its job. (Resolved 2026-11-09, maintainer.)
- **Q2 — a profile baseline for the run.** The run's cost is cumulative across cycles, like the
  suite's. — **A:** add a `mutants budget` row to `AGENTS.md` § Factory with the bound and the run's
  cost as measured at landing (R4). (Resolved 2026-11-09, maintainer.)
- **Q3 — survivors found by the first hosted run.** The full set has never run on the hosted
  runner. — **A:** a case that survives or is killed for the wrong reason on the first full run is
  seeded as its own `issues/` entry, not fixed here; the cycle lands with the run reporting it (R2).
  More than a few such cases go back to the foreman before the cycle continues. (Resolved
  2026-11-09, foreman ruling at the GOAL gate.)
- **Q4 — the hosted-runner evidence.** R1 and R4 need dispatched runs on the hosted runner. —
  **A:** up to 3 `workflow_dispatch` runs of `mutants.yml` on `ci/mutants-workflow-timeout`, the
  worst of the 3 counted; no other dispatches. (Resolved 2026-11-09, maintainer.)
- **Q5 — R5's scope.** R5 (the stale dispatch-state sentence) was added in shaping, beyond the
  seed. — **A:** R5 stays. (Resolved 2026-11-09, foreman ruling at the GOAL gate.)

## Related materials

- Seed: [`issues/mutants-workflow-timeout.md`](../../issues/mutants-workflow-timeout.md)
- Roadmap: `ROADMAP.md` Part I, "The on-demand mutation run no longer fits its 30-minute job"
- `.github/workflows/mutants.yml`; `tests/mutants.py` (`CASES`, `main`, `run_child`);
  `tests/test_mutations.py`
- `AGENTS.md` § Testing (the mutation runner paragraph), § Factory (`ci`, `ci budget` rows),
  § Conventions ("CI mirrors the gate")
- Timing evidence: [`spec/capability-probe/research/03-testing-and-budget.md`](../capability-probe/research/03-testing-and-budget.md) §5;
  [`spec/timeout-process-cleanup/TECH.md`](../timeout-process-cleanup/TECH.md) (suite growth, the
  sweep's ≈ 11 min per era)
- Prior art for a split CI budget: [`spec/suite-ci-time-budget/`](../suite-ci-time-budget/)
- Neighbouring seeds: [`issues/mutant-child-outlives-timeout.md`](../../issues/mutant-child-outlives-timeout.md),
  [`issues/stalled-reconnect-test-timing.md`](../../issues/stalled-reconnect-test-timing.md)
