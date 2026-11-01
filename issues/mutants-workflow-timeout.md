---
status: unshaped
kind: ci
appetite: small
lane: public
---

# The on-demand mutation run no longer fits its 30-minute job

## Problem

`.github/workflows/mutants.yml` runs every case in `tests/mutants.py` serially, in one job with
`timeout-minutes: 30`. The file defines 660 cases at `c520432`. One case is a child pytest run of its
targets against a copy of the namespace, measured at about 2.5–5 s each on a development host
(`spec/capability-probe/research/03-testing-and-budget.md` §5). That puts the whole run at about
27–33 minutes before a runner's own overhead, so the job reaches its timeout and is cancelled rather
than reporting. `AGENTS.md` § Testing still says "all cases about 3 minutes", which was true when the
runner had far fewer cases.

`capability-probe` adds roughly 200 more cases (its alternatives sweep, PLAN §6), which makes the gap
wider. The cycle gates themselves are unaffected: each phase runs its own cases, split by era, under a
10-minute command cap, and nothing that lands reads this workflow.

**Pre-existing:** yes. The timeout was reached before `capability-probe` and grew with
`capability-extras`' sweep (241 cases).

## Why it was deferred

It is a CI workflow and a § Testing figure, outside every R-ID of `capability-probe`, and
the workflow gates nothing (publish never reads it). Changing it is a `ci` change of its own, and
choosing between a longer timeout, a matrix of shards, and running only the cases touching changed
files is a decision for that cycle.

## Outcome / vision

A manual mutation run finishes and reports every case, and § Testing states its real cost.

## Sketch of the acceptance criteria

- **R1** — WHEN the mutation workflow is dispatched, it SHALL run every case in `tests/mutants.py` and
  report each killed or not before any job timeout.
- **R2** — `AGENTS.md` § Testing SHALL state the measured cost of a full run.

## Notes

- Related: `spec/capability-extras/` (TECH, the F7 sweep); `spec/capability-probe/` (PLAN §6).
- Found by: `capability-probe` plan step research, 2026-11-01.
- 2026-11-01: with its two review remediations, `capability-probe` adds 271 cases, not about 200:
  `tests/mutants.py` defines 931.
