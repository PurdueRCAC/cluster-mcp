---
slug: mutant-child-outlives-timeout
title: A mutant whose child run hangs is reported, and leaves nothing running
kind: fix
appetite: small
status: in_review
branch: fix/mutant-child-outlives-timeout
base: develop
current_phase: done
last_updated: '2026-11-10'
phases:
- id: P1
  name: A child run past its limit is stopped whole, reported, and the sweep goes on
  status: done
  satisfies:
  - R1
  - R2
  - R3
  - R4
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv run python -I spec/mutant-child-outlives-timeout/verify/gate.py controls && uv run python -I spec/mutant-child-outlives-timeout/verify/gate.py untouched && uv run python -I spec/mutant-child-outlives-timeout/verify/gate.py rows legacy && uv run python -I spec/mutant-child-outlives-timeout/verify/gate.py rows modern && uv run pytest -q tests/test_hygiene.py tests/test_mutations.py && uv run python -I spec/mutant-child-outlives-timeout/verify/gate.py within-limit
- id: P2
  name: The ledger, and the full gate in both eras
  status: done
  satisfies:
  - R1
  - R2
  - R3
  - R4
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv run python -I spec/mutant-child-outlives-timeout/verify/gate.py prepush && uv run python -I spec/mutant-child-outlives-timeout/remediation/untouched.py && uv run python -I spec/mutant-child-outlives-timeout/remediation/names.py && uv lock --check && uv run pytest -q tests/test_ssh_exec.py -k silent && uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k silent && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && bin/sandbox.sh uv run cluster-mcp --help
review:
  last_reviewed_commit: 3f5bdf991876e499651fd9efe896810d936a2f1c
  verdict: changes-requested
  blocked_reason: 'review 2: a failed look in the stop leaves the case unreported and the run running (F4); timeout_violations undescribed (F5)'
  cycle: 2
---

# TECH.md — A mutant whose child run hangs is reported, and leaves nothing running

The **context engine and finite-state machine** for building this cycle. The YAML frontmatter above
is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/mutant-child-outlives-timeout/TECH.md`);
the per-phase checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via `uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`,
and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md) (§ 2 the design, § 6 the rows and the mutant list).
- **The frozen gate:** [`verify/gate.py`](verify/gate.py), one mode per requirement (its docstring
  lists them), and [`verify/within-limit.expected`](verify/within-limit.expected), develop's runner's
  output for the R4 sample. Never edit either to make a phase pass: a gate that is wrong is a stop and
  a question for the foreman.

## Conventions (apply to every phase)

- Commit conventions, code style, and load-bearing invariants come from the repo's `AGENTS.md` — it
  is the constitution. Walk the sections of its § Invariants that this change touches; that is the
  curated footgun checklist.
- One phase per `code-build` invocation by default; one atomic commit containing **both** the code and
  the `TECH.md` state change. The branch commit subject is code-build's (`$KB/skill/code-build.md` →
  Step 6), not restated here; branch commits are squashed away at `code-publish` per the profile's
  `landing`. Trailers follow the profile's `branch commits`.
- The last phase carries the standing last-phase items: the deferral ledger (`code-plan` Step 6.8),
  and every item the previous cycle's last phase carried for a project-level obligation. The previous
  cycle (`suite-ci-time-budget`) carried the ledger; the ledger is the one that applies.
- A PR body (when the profile's `landing` opens one) ends with an attribution naming the actual
  harness, model, and variant.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`): the
  help text, docs, or generated files it names change **in the same commit**. Here: the module
  docstring of `tests/mutants.py` and `AGENTS.md` § Testing's mutation-runner bullet change with the
  behaviour, in P1.
- Export `UV_PYTHON=3.14` before every `verify:` on this host. Stage before running a `verify:`: the
  gate's data modes read the index, and `rows` and `within-limit` refuse a working copy that differs
  from it. A gate near or over the Bash tool's 10-minute cap (P2's full `verify`) runs through
  `run_in_background`; never a disowned launch.
- Only `tests/mutants.py`, `tests/test_mutations.py`, `AGENTS.md` (the mutation-runner bullet, and
  since review cycle 1's F1 the § Testing entry for `tests/test_mutations.py`) and, since F2, the
  one sentence of `issues/sandbox-dirs-left-on-kill.md` naming this runner change, besides this
  cycle's `spec/` (the `untouched` mode, run through `remediation/untouched.py` since F1).
  In `tests/mutants.py`, `CASES`, `SURVIVOR_CONTROL`, `apply`, `apply_repo`, `mutation_violations`,
  `self_check` and `main` stay byte-identical, and new statements go between `apply_repo` and
  `run_child`; that keeps the sibling cycle `mutants-workflow-timeout` rebasing cleanly (PLAN § 2,
  touch points). No dispatch of `.github/workflows/mutants.yml`, and no phase waits on a hosted run.

---

## Phase P1 — A child run past its limit is stopped whole, reported, and the sweep goes on
**Satisfies:** R1, R2, R3, R4 · **Depends on:** —
**Goal:** a case whose child run passes `LIMIT` is frozen, found whole, killed, confirmed gone and
reported `FAILED` with the timeout and its limit named, before the next case runs; a child that ends
within its limit is read exactly as before.

- [x] In `tests/mutants.py`, between `apply_repo` and `run_child`: `LIMIT = 300`, `GONE_WITHIN = 10`,
      `GONE_POLL = 0.1` (approved, amendment 1; a later ruling changes the constant and
      `test_the_stop_figures` together), `ChildTimeout`,
      `RunnerSignal`, `_processes`, `run_members`, `_wait_gone`, `stop_run`, `timeout_violations`,
      `stop_on_signals`, `die_by`, each as PLAN § 2 specifies (signatures; the stop's order: signals
      held, freeze, walk, SIGKILL in reverse discovery order inside `try`/`finally`, confirmation,
      then `wait`; exact violation strings).
- [x] `run_child`: `Popen(..., start_new_session=True)` with the same argv and environment as today,
      `communicate(timeout=LIMIT)` read at call time, the two early-exit clauses (PLAN § 2), and a
      `CompletedProcess` built as `subprocess.run` builds it.
- [x] `run_case`: catch `ChildTimeout` inside the `TemporaryDirectory` block and return
      `timeout_violations(exc)`. `main` and `self_check` are not edited.
- [x] The `__main__` block calls `stop_on_signals()`, then `sys.exit(main())` with `RunnerSignal`
      caught and handed to `die_by` (it stays the file's last statement).
- [x] Imports: `signal`, `time`. The module docstring gains one sentence on the limit and the stop.
- [x] `AGENTS.md` § Testing, the mutation-runner bullet: the `FAILED` sentence names the timeout
      (PLAN § 2, Docs). `issues/sandbox-dirs-left-on-kill.md` is not edited (amendment 2).
- [x] `tests/test_mutations.py`: every row PLAN § 6 lists, with exactly the names and parameter ids
      the gate's `ROWS` freezes, each tagged `unit` or `integration` as listed. The unit rows launch
      nothing (fakes injected into `stop_run`, a fake `Popen`, a recorded `signal.signal`). The
      integration row's processes carry `mutant-hang-` in their argv and its teardown kills each one.
- [x] Mutant pass (code-build Step 4): plant each mutant of PLAN § 6's decision list into a scratch
      copy of `tests/mutants.py` and run the rows it names; each must go red. Record the table (mutant,
      rows red, or survivor and why) in the commit body.
- [x] Measure the integration row's time in each era (`pytest --durations=0`) and put both figures
      in the commit body; PLAN § 5's 10–11 s is a projection until then.
- **Verify:** the frontmatter `verify:`: `controls`, `untouched`, `rows legacy`, `rows modern`,
  `tests/test_hygiene.py` with `tests/test_mutations.py` (the sandbox rail and the spec-id check over
  the new code), then `within-limit` (R4, both passes, about 200 s).
- **Touches:** `tests/mutants.py`, `tests/test_mutations.py`, `AGENTS.md`.
- **Amendments (2026-11-09, P1 build):**
  1. D3 and D5 approved by the maintainer at the PLAN/TECH gate, 2026-11-09: `GONE_POLL = 0.1`,
     `GONE_WITHIN = 10`; one integration row at about 10–11 s per era in each era's fourth suite
     command, and a measurement above 15 s per era goes back to the maintainer before P1 lands.
  2. Foreman ruling: `issues/sandbox-dirs-left-on-kill.md` is not rewritten in this cycle. That seed
     is owned by the `sandbox-dirs-left-on-kill` cycle since 2026-11-09, which keeps `bin/sandbox.sh`
     as it is and has each harness that SIGKILLs a sandbox point its `TMPDIR` into a directory the
     harness owns, plus a suite-session sweep. This cycle does not change how the runner sets
     `TMPDIR` for its child (the PLAN never did); only the integration row points its own `TMPDIR`
     under `tmp_path`, as PLAN § 6 planned.
  3. Build detail beyond PLAN § 2's names, all inside the run-child block: `HELD` (the held signals),
     `Table` (the table's type), `_send` (a signal send that ignores a vanished or foreign target) and
     `_raise_runner_signal` (the handler). `run_members` returns its pids and groups as lists in
     discovery order (the stop's kill order needs it) and never adds pid or group 0 or 1, so no
     signal can go to `kill(0)`, `killpg(0)` or init. `_wait_gone` also drops a group once no live
     member of the run carries it. `die_by` raises `SystemExit(128 + signum)` should the signal not
     end the runner.
  4. Three rows strengthened after the mutant pass's first run showed a named row green (each
     mutant was still killed by another row). The integration row's orphan starts a child in a
     session of its own, reachable only through the orphan's group, so "`run_members` ignores
     pgid" turns the row red (killing the wrapper's group alone had reached the orphan); and its
     spawner lingers 0.3 s, with the layout check requiring the orphan's parent to be neither the
     pytest nor the spawner, so "the orphan's layout not waited for" is red every time, not by a
     race. The `gone-*` rows compare against the approved figures stated in the test module, not
     the imported constants, so "`GONE_WITHIN` 10 → 1" and "`GONE_POLL` 0.1 → 1" turn
     `still-running` and `gone-after-polls` red as listed.

## Phase P2 — The ledger, and the full gate in both eras
**Satisfies:** R1, R2, R3, R4 (the whole suite, both eras, on the final tree) · **Depends on:** P1
**Goal:** the branch's final tree passes the profile's full `verify`, the cycle's changes stay in its
files, and the ledger is clean.

- [x] The ledger (`code-plan` Step 6.8): walk P1's and P2's bodies, PLAN.md and the branch's commit
      bodies for the phrases the `prepush` mode lists; each such item names an `issues/` seed with a
      `ROADMAP.md` entry (the `prepush` mode checks it). This plan files no new seed: its deferrals are
      the sandbox home ([`issues/sandbox-dirs-left-on-kill.md`](../../issues/sandbox-dirs-left-on-kill.md))
      and the sweep's arrangement ([`issues/mutants-workflow-timeout.md`](../../issues/mutants-workflow-timeout.md)),
      both already seeded and indexed.
- [x] Put P1's measured integration-row times into PLAN § 5 (D5), naming the run that measured them.
- [x] Stage, then run the frontmatter `verify:` through `run_in_background`: `prepush`, `untouched`,
      then the profile's full `verify`, both eras.
- **Remediation, review cycle 1** (`REVIEW.md`, changes-requested at `6c0396a`; P2 reopened):
  - [x] F1: `AGENTS.md` § Testing's `tests/test_mutations.py` entry names its `integration` row and
        the stop's unit rows; the runner bullet describes the stop (own session, freeze, walk,
        SIGKILL, `GONE_WITHIN`/`GONE_POLL`, the `still running … pids` line, the out-of-reach case,
        Ctrl-C/TERM/HUP stopping the run first, a group SIGKILL reaching the runner alone, the home
        left in the runner's `TMPDIR`) with every new name; both module docstrings say the same.
  - [x] F2: the seed's sentence on this runner states `stop_run`'s freeze-then-SIGKILL of the whole
        run, follows "The last three …" so that referent stays the three test harnesses, and says the
        runner sets no `TMPDIR`.
  - [x] F3: `verify/gate.py` derives `BASE` from the shape commit's subject on HEAD's history.
  - [x] Review P1: `test_stop_run_waits_for_every_process_it_found` pins that the stop hands every
        pid and group it found to the confirmation.
  - [x] Coverage: rows `run_members…[found-later-in-the-table]`, `[never-init-or-kernel]`, the
        `runner-group` row seeded with the runner's own group, and
        `gone_waits…[gone-numbers-never-followed]`; the sweep and its record,
        [`verify/sweep.py`](verify/sweep.py) and [`verify/sweep.md`](verify/sweep.md).
  - [x] Run the retuned frontmatter `verify:` (amendment R1-3) in the background.
- **Amendments (2026-11-09, review cycle 1 remediation):**
  - R1-1. F3, by the foreman's ruling at the review gate: `verify/gate.py` is edited, the frozen
    gate's one change: `BASE` is the commit on HEAD's history whose subject is
    `[fix] Shape mutant-child-outlives-timeout goal` (exactly one, else the gate stops), so a
    rebase cannot stale it. Seen red first: a wrong subject stops the gate, and the pre-rebase
    `71a3a49` reports `tests/test_hygiene.py` and develop's other files outside the cycle.
  - R1-2. F2, by the foreman's ruling at the review gate, supersedes P1 amendment 2 for the one
    sentence on this runner: the cycle corrects it, since the cycle's own shape commit wrote it. The
    sentence's runtime claims were checked by a drive of the runner's `__main__` path on one
    hanging case: at a 5 s limit it printed the `FAILED … timeout` line, exit 1, the pytest, the
    wrapper and a new-session child gone, the scratch copy gone, and one sandbox home left in the
    `TMPDIR` the runner was started with.
  - R1-3. F1 changes an `AGENTS.md` entry outside the mutation-runner bullet, which the frozen
    `untouched` mode refuses (seen red: "changed outside the mutation-runner bullet"). It runs
    unchanged under [`remediation/untouched.py`](remediation/untouched.py), which also cuts that one
    entry from both sides of the `AGENTS.md` comparison and controls that an edit elsewhere is still
    refused; P2's `verify:` names the wrapper in the bare mode's place. P1's `verify:` is its record.
  - R1-4. The same drive checked the manual's signal claims: SIGTERM, SIGHUP and SIGINT to the
    runner each left the run gone and the scratch copy removed, and the runner ended by that signal
    (exit -15, -1, -2); a SIGKILL to the runner's process group ended the runner alone and left the
    run running (then killed by the drive).
- **Remediation, review cycle 2** (`REVIEW.md` cycle 2, changes-requested at `3f5bdf9`; branch
  rebased onto develop `146cbc6` first; P2 reopened):
  - [x] F4: `run_child` turns any `Exception` out of `stop_run` (a `ps` that fails or cannot start, a
        look cut short) into `ChildTimeout(LIMIT, [], unfinished)`; `stop_run` has already killed the
        wrapper's group and every process it found. `child_timeout_violations` then reports
        `timeout: the child ran past its N s limit` (never "and was stopped") and `the stop could not
        finish (<error>): … others of the run may still be running`; `run_case` returns it and the
        sweep goes on. A `KeyboardInterrupt` or `RunnerSignal` during the stop still propagates.
        Rows: `run_child_reports_a_stop_that_could_not_finish[ps-cannot-start|ps-fails-mid-walk|
        interrupt-during-stop]`, `a_stop_that_could_not_finish_is_reported_and_the_sweep_goes_on`,
        `a_timeout_reason_names_the_limit[unfinished]`, `a_failed_ps_is_an_error_not_an_empty_table`.
  - [x] F5: every name the cycle adds is described: the runner's in `AGENTS.md` § Testing (the
        private ones there or in its docstring), the test module's helpers in its docstring. Two
        runner names renamed where they collided with other test modules' top-level names:
        `timeout_violations` → `child_timeout_violations` (`tests/test_executors.py` has a different
        `timeout_violations`) and `HELD` → `HELD_SIGNALS` (`tests/test_auth_modes.py`,
        `tests/test_ssh_exec.py` and `tests/test_timeout_stop.py` each bind a `HELD`); the manual
        tells `child_timeout_violations` apart from `test_executors.py`'s helper.
        [`remediation/names.py`](remediation/names.py) checks it mechanically.
  - [x] `wg-end-absolute`: `gone_waits_until_every_process_ends[clock-not-at-zero]`.
  - [x] Sweep extended ([`verify/sweep.md`](verify/sweep.md)); the retuned frontmatter `verify:`
        run in the background.
- **Amendments (2026-11-10, review cycle 2 remediation):**
  - R2-1. P2's `verify:` runs [`remediation/names.py`](remediation/names.py) after the `untouched`
    wrapper. It lists the top-level names the cycle adds since the shape commit and refuses one not
    described (above), a public runner name bound at the top level of another `tests/` module, and an
    empty list; its controls plant each. Seen red on the reviewed tree: 24 violations, among them
    `timeout_violations` and `HELD` colliding, and `Table`, `_processes`, `_send`,
    `_raise_runner_signal` and the test module's helpers undescribed.
  - R2-2. F4 seen on the real path with review cycle 2's own probe (`probe_psfail2.py`: the run's
    new-session filler forks until the probe's lowered process budget is spent): the hang case is
    now reported, `FAILED  hang: timeout: the child ran past its 6 s limit; the stop could not
    finish (BlockingIOError: [Errno 35] Resource temporarily unavailable): …`, and the runner goes
    on to the next case. That case's own launch then fails with the same `BlockingIOError`, since the
    filler the stop could not reach (a new-session child of the frozen pytest, found by no look)
    still holds the budget; the probe then killed the 51 run processes left. The line names that
    others may be running.
- **Verify:** the frontmatter `verify:`.
- **Touches:** `spec/mutant-child-outlives-timeout/PLAN.md`, `spec/mutant-child-outlives-timeout/TECH.md`;
  in the remediation, `AGENTS.md`, `tests/mutants.py`, `tests/test_mutations.py`,
  `issues/sandbox-dirs-left-on-kill.md`, `spec/mutant-child-outlives-timeout/verify/`,
  `spec/mutant-child-outlives-timeout/remediation/`.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[fix]` commit; stop and report.
