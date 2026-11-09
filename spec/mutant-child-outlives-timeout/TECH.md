---
slug: mutant-child-outlives-timeout
title: A mutant whose child run hangs is reported, and leaves nothing running
kind: fix
appetite: small
status: in_progress
branch: fix/mutant-child-outlives-timeout
base: develop
current_phase: P1
last_updated: '2026-11-09'
phases:
- id: P1
  name: A child run past its limit is stopped whole, reported, and the sweep goes on
  status: pending
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
  status: pending
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
  verify: uv run python -I spec/mutant-child-outlives-timeout/verify/gate.py prepush && uv run python -I spec/mutant-child-outlives-timeout/verify/gate.py untouched && uv lock --check && uv run pytest -q tests/test_ssh_exec.py -k silent && uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k silent && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && bin/sandbox.sh uv run cluster-mcp --help
review:
  last_reviewed_commit: ''
  verdict: none
  blocked_reason: ''
  cycle: 0
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
- Only `tests/mutants.py`, `tests/test_mutations.py`, `AGENTS.md` (the mutation-runner bullet) and
  `issues/sandbox-dirs-left-on-kill.md` change, besides this cycle's `spec/` (the `untouched` mode).
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

- [ ] In `tests/mutants.py`, between `apply_repo` and `run_child`: `LIMIT = 300`, `GONE_WITHIN = 10`,
      `GONE_POLL = 0.1` (the figures stand as PLAN § 3 D3 and D5 propose until the maintainer rules on
      them; a ruling changes the constant and `test_the_stop_figures` together), `ChildTimeout`,
      `RunnerSignal`, `_processes`, `run_members`, `_wait_gone`, `stop_run`, `timeout_violations`,
      `stop_on_signals`, `die_by`, each as PLAN § 2 specifies (signatures; the stop's order: signals
      held, freeze, walk, SIGKILL in reverse discovery order inside `try`/`finally`, confirmation,
      then `wait`; exact violation strings).
- [ ] `run_child`: `Popen(..., start_new_session=True)` with the same argv and environment as today,
      `communicate(timeout=LIMIT)` read at call time, the two early-exit clauses (PLAN § 2), and a
      `CompletedProcess` built as `subprocess.run` builds it.
- [ ] `run_case`: catch `ChildTimeout` inside the `TemporaryDirectory` block and return
      `timeout_violations(exc)`. `main` and `self_check` are not edited.
- [ ] The `__main__` block calls `stop_on_signals()`, then `sys.exit(main())` with `RunnerSignal`
      caught and handed to `die_by` (it stays the file's last statement).
- [ ] Imports: `signal`, `time`. The module docstring gains one sentence on the limit and the stop.
- [ ] `AGENTS.md` § Testing, the mutation-runner bullet: the `FAILED` sentence names the timeout
      (PLAN § 2, Docs). `issues/sandbox-dirs-left-on-kill.md`: the sentence naming this runner's
      timeout path states the new mechanism (the whole run SIGKILLed, `bin/sandbox.sh` included); its
      home is still left, which is that seed's.
- [ ] `tests/test_mutations.py`: every row PLAN § 6 lists, with exactly the names and parameter ids
      the gate's `ROWS` freezes, each tagged `unit` or `integration` as listed. The unit rows launch
      nothing (fakes injected into `stop_run`, a fake `Popen`, a recorded `signal.signal`). The
      integration row's processes carry `mutant-hang-` in their argv and its teardown kills each one.
- [ ] Mutant pass (code-build Step 4): plant each mutant of PLAN § 6's decision list into a scratch
      copy of `tests/mutants.py` and run the rows it names; each must go red. Record the table (mutant,
      rows red, or survivor and why) in the commit body.
- [ ] Measure the integration row's time in each era (`pytest --durations=0`) and put both figures
      in the commit body; PLAN § 5's 10–11 s is a projection until then.
- **Verify:** the frontmatter `verify:`: `controls`, `untouched`, `rows legacy`, `rows modern`,
  `tests/test_hygiene.py` with `tests/test_mutations.py` (the sandbox rail and the spec-id check over
  the new code), then `within-limit` (R4, both passes, about 200 s).
- **Touches:** `tests/mutants.py`, `tests/test_mutations.py`, `AGENTS.md`,
  `issues/sandbox-dirs-left-on-kill.md`.

## Phase P2 — The ledger, and the full gate in both eras
**Satisfies:** R1, R2, R3, R4 (the whole suite, both eras, on the final tree) · **Depends on:** P1
**Goal:** the branch's final tree passes the profile's full `verify`, the cycle's changes stay in its
files, and the ledger is clean.

- [ ] The ledger (`code-plan` Step 6.8): walk P1's and P2's bodies, PLAN.md and the branch's commit
      bodies for the phrases the `prepush` mode lists; each such item names an `issues/` seed with a
      `ROADMAP.md` entry (the `prepush` mode checks it). This plan files no new seed: its deferrals are
      the sandbox home ([`issues/sandbox-dirs-left-on-kill.md`](../../issues/sandbox-dirs-left-on-kill.md))
      and the sweep's arrangement ([`issues/mutants-workflow-timeout.md`](../../issues/mutants-workflow-timeout.md)),
      both already seeded and indexed.
- [ ] Put P1's measured integration-row times into PLAN § 5 (D5), naming the run that measured them.
- [ ] Stage, then run the frontmatter `verify:` through `run_in_background`: `prepush`, `untouched`,
      then the profile's full `verify`, both eras.
- **Verify:** the frontmatter `verify:`.
- **Touches:** `spec/mutant-child-outlives-timeout/PLAN.md`, `spec/mutant-child-outlives-timeout/TECH.md`.

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
