# GOAL — A mutant whose child run hangs is reported, and leaves nothing running

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** mutant-child-outlives-timeout
- **kind:** fix
- **appetite:** small

## Problem

`tests/mutants.py` is the mutation runner every phase gate's sweep and the on-demand mutation
workflow run (`AGENTS.md` § Testing). Each case plants its edits in a scratch copy and runs its
targets in a child pytest: `run_child` (`tests/mutants.py:5692-5699`) starts
`bin/sandbox.sh sh -c CHILD …`, where `CHILD`'s last line `exec`s pytest (`tests/mutants.py:73`),
through `subprocess.run(..., timeout=300)`. A mutant is allowed to make its target hang; that is
one of the ways mutated code can break. When the 300 s limit passes, two things go wrong.

- **The run is left behind.** `subprocess.run` kills only the process it started, the sandbox
  wrapper. The pytest below it keeps running, reparented to init, holding its loopback servers,
  its silent hop and the files it uses, until it ends by itself. The wrapper is killed outright, so
  its own `trap` (`bin/sandbox.sh:60`) never removes its throwaway home either (that leftover is
  `issues/sandbox-dirs-left-on-kill.md`'s; see Non-goals).
- **The sweep stops.** `run_case` (`tests/mutants.py:5749-5761`) does not catch the
  `TimeoutExpired`, so it propagates out of `main` (`tests/mutants.py:5781-5806`): the case is
  never reported, and no case after it runs.

Seen on 2026-11-05, during the `ssh-half-open-link` review cycle 2 remediation: a case that hung its
target for the full 300 s left its pytest running, parent PID 1, more than seven minutes later,
until it was killed by hand. On a development host that is a stray process holding ports and
scratch; in a gate's or the workflow's sweep it is every later case's verdict lost.

**Pre-existing:** yes. The runner's child, its 300 s limit and the uncaught timeout landed together
in `restore-test-coverage` (`b4dde4d`) and are on `develop` at `0bfacae`.

## Outcome / vision

A case whose child run passes its time limit leaves nothing of that run behind, is reported as not
killed with the timeout named, and the sweep goes on to its next case. Every case whose child ends
within its limit is reported exactly as it is today.

## Acceptance criteria (the contract)

- **R1** — WHEN a case's child run passes its time limit, the runner SHALL stop every process that
  run started, the child pytest and anything it started included, before it reports the case; and
  SHALL stop none that the run did not start.
- **R2** — WHEN a case's child run passes its time limit, no process of that run SHALL still be
  running, and no scratch directory the runner itself created for that run SHALL still exist, once
  the runner has reported the case.
- **R3** — WHEN a case's child run passes its time limit, the runner SHALL report that case as
  not killed (a `FAILED` line for it) with a reason that names the timeout and its limit, SHALL go
  on to run every case named after it, and SHALL exit non-zero.
- **R4** — WHEN a case's child run ends within its time limit, the runner SHALL report that case,
  and SHALL exit, exactly as it does on `develop` at `0bfacae`: no case's verdict, and no
  `--self-check` control's, changes.

## Non-goals (no-gos)

- **The time limit itself.** The per-case limit stays 300 s; this cycle sets, loosens or tightens
  no timing figure. If the plan's way of stopping a run needs any grace period after the limit, that
  figure is the maintainer's call at the plan gate, with its before-and-after.
- **Counting a timeout as a kill.** A case caught by a hang is still not caught: the runner's rule,
  that a case is caught only when every target fails with its `why` (`tests/mutants.py` module
  docstring), is unchanged.
- **How the sweep is arranged.** Sharding, concurrency, case selection, the mutation workflow
  (`.github/workflows/mutants.yml`) and its job timeout, and § Testing's figures for a full run are
  [`issues/mutants-workflow-timeout.md`](../../issues/mutants-workflow-timeout.md), shaped as its own
  cycle. R1's "none that the run did not start" is the one property here that a concurrent
  arrangement would also lean on; this cycle does not build that arrangement.
- **The sandbox home a killed `bin/sandbox.sh` leaves behind:**
  [`issues/sandbox-dirs-left-on-kill.md`](../../issues/sandbox-dirs-left-on-kill.md), which now names
  this runner's timeout path. The plan may choose a way of stopping the run that lets the wrapper's
  own `trap` run, but it SHALL NOT build a second sandbox-cleanup mechanism here.
- **The hang that exposed it.** Whatever made the 2026-11-05 mutant hang its target is the mutant
  doing its job, not a defect to fix here.
- **Case content.** No case's edits, targets or `why` change.
- **Other timeouts in the suite.** The `subprocess.TimeoutExpired` handling in the suite's own tests
  (`tests/test_transports.py`, `tests/test_startup.py`, `tests/test_probe_startup.py`) and the
  executors' timeout contract are untouched.

## Clarifications

- **Q:** Does R2 cover the sandbox home that a SIGKILLed `bin/sandbox.sh` leaves behind? — **A:** No.
  That is the general defect of `issues/sandbox-dirs-left-on-kill.md`, which covers every harness
  that kills a sandbox outright and now names this runner's timeout path. R2 keeps the run's
  processes and the scratch directories the runner itself creates; the plan may pick a stop that
  lets the wrapper's `trap` run, but builds no second sandbox-cleanup mechanism, and any grace
  period after the limit stays the maintainer's call (foreman ruling at the GOAL gate, resolved
  2026-11-09).
- **Q:** Does a case whose child run passes its time limit count as killed? — **A:** No, it is
  reported as not killed (R3). That is the runner's documented rule, that a case is caught only when
  every target fails with its `why`, and the conservative reading for a gate (foreman ruling at the
  GOAL gate, resolved 2026-11-09).
- **Q:** Which processes does "every process that run started" (R1, and R2's "no process of that
  run") cover? — **A:** Every process reachable from the run's wrapper at the stop, through a chain of
  live parents or through membership in a process group of such a process. A process that cut both
  links before the stop (left every group of the run and lost its parent) is out of portable reach,
  and is not covered; in the suite only the rows that make such an escape on purpose do that
  (2026-11-09, foreman ruling at the PLAN/TECH gate).
- **Q:** How is R4 ("no case's verdict … changes") shown, without a sweep of every case? — **A:** By
  the 22-case sample run in two passes against develop's recorded output (planted: each case still
  killed with its `why`; unmutated: each target still passes), the three `--self-check` controls, and
  the gate that holds every other statement of the runner byte-identical to develop's (2026-11-09,
  foreman ruling at the PLAN/TECH gate).

## Related materials

- Seed: [`issues/mutant-child-outlives-timeout.md`](../../issues/mutant-child-outlives-timeout.md)
- Roadmap: `ROADMAP.md` Part I, "A mutant's child run outlives its timeout"
- `tests/mutants.py` (`CHILD`, `run_child`, `run_case`, `self_check`, `main`);
  `tests/test_mutations.py` (the runner's fast tests); `bin/sandbox.sh`
- Where it was seen: [`spec/ssh-half-open-link/`](../ssh-half-open-link/)
- Where it shipped: [`spec/restore-test-coverage/`](../restore-test-coverage/)
- Neighbouring cycle: [`issues/mutants-workflow-timeout.md`](../../issues/mutants-workflow-timeout.md)
- Neighbouring seed: [`issues/sandbox-dirs-left-on-kill.md`](../../issues/sandbox-dirs-left-on-kill.md)
