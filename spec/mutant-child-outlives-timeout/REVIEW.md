# REVIEW — A mutant whose child run hangs is reported, and leaves nothing running

> Adversarial QA by `code-review`, run in an isolated/clean context (a subagent; where the runtime
> has none, `code-review`'s sequential fallback). The correctness pass grades the branch diff against
> [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants **only** — it does not see
> `PLAN.md`/`TECH.md` (avoids grading-its-own-homework / plan-sycophancy). Every finding cites an
> **executed** command, not an assertion.

- **Reviewed commit:** 6c0396a7fd176a597bbbaa5b5a1a5229792fd1fb  ·  **Base:** develop (`origin/develop` e378c33)  ·  **Date:** 2026-11-09
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md` (escalate to human on non-convergence)

One fresh blind reviewer (a subagent, no sequential fallback) graded the spec-excluded diff
(`git diff origin/develop...HEAD -- . ':(exclude)spec/'`) and the log. The orchestrator graded the
spec-held part of R4's evidence (the recorded develop output and the frozen gate). Contract drift:
`GOAL.md` moved after the shape commit only by dated Clarifications recorded at the GOAL and
PLAN/TECH gates (`d15317a`); graded against `GOAL.md` as it stands at the reviewed commit.

Evidence: the reviewer's probes and logs are in the gitignored `.local/review1/`, the orchestrator's
in `.local/review1-orch/`.

## Verification run

Commands actually executed and their outcomes:

- `uv sync --locked` → no-op; `.venv` unchanged.
- The profile's `verify`, both eras, as its four commands per era (`.local/review1/verify-legacy.log`,
  `verify-modern.log`) → 1343 passed per era; `uv lock --check` and
  `bin/sandbox.sh uv run cluster-mcp --help` → pass (`verify-docs-readers.log`).
- New rows of `tests/test_mutations.py` (`verify-new-rows.log`) → pass; the integration row
  `test_a_child_past_its_limit_is_stopped_whole_and_reported` takes 9.42 s.
- Timeout drive, `.local/review1/probe_timeout.py 6` (runner imported, limit patched to 6 s, a hung
  child with same-group, own-group, new-session, signal-ignoring, fork-loop and orphaned descendants;
  unrelated processes in the runner's group, in a new session and in a sandbox) →
  `FAILED  hang: timeout: the child ran past its 6.0 s limit and was stopped`; every reachable run
  process gone; unrelated processes untouched (still `S`/`Ss`); the next two cases ran; exit 1; the
  runner's scratch listing right after `run_case` is `[]` (`probe-timeout-branch.log`).
- Signal drive, `.local/review1/probe_sigterm.py` → TERM, HUP and INT to the runner mid-run each stop
  the whole run and remove scratch; the runner ends by the signal (`probe-sigterm.log`).
- R4 behavioural sample, 14 cases plus `--self-check`, branch runner through `bin/sandbox.sh` vs
  develop's runner (`branch-cli-planted.log`, `develop-planted.log`) → identical report lines, exit 0;
  unmutated pass (`branch-unmutated.log`, `develop-unmutated.log`) → identical, every target passes.
- Mutant sweep, 62 mutants over the new stop/report/signal code (`.local/review1/mutsweep.py`,
  `mutsweep.jsonl`, `mut/<id>.log`) → 55 killed, 7 survived (Coverage observations below); runner
  restored and hash-checked against `HEAD` after every batch; post-sweep `tests/test_mutations.py` →
  1201 passed (`post-sweep-recheck.log`).
- Orchestrator, `gate.py within-limit` → `ok  within-limit` in 199 s: the 22-case sample and the three
  `--self-check` controls print exactly `within-limit.expected`, and the unmutated pass exactly
  `unmutated.expected` (`.local/review1-orch/within-limit.log`).
- Orchestrator, `gate.py controls` → `ok  controls` (every plant refused for its reason).
- Orchestrator, `gate.py untouched` → **red** at the reviewed commit (F3); the same gate with `BASE`
  re-pinned to the rebased shape commit `1e3ea35` → `ok  untouched`
  (`.local/review1-orch/untouched-as-committed.log`, `untouched-rebased.log`).
- § Conventions spec-id grep over the added lines (`spec-id-grep.log`) → no match;
  `test_no_spec_ids_in_the_package_or_the_suite` passes.

## Requirement → evidence matrix

| R-ID | Implemented by (file/commit) | Verified how | Status |
|------|------------------------------|--------------|--------|
| R1 | `tests/mutants.py` `run_members`, `stop_run`, `run_child` (`start_new_session`); `6881072` | Reviewer: timeout drive (every reachable descendant gone, unrelated processes untouched; the out-of-reach escape survives, as the Clarification allows); mutant sweep | ✅ |
| R2 | `tests/mutants.py` `_wait_gone`, `run_case` scratch removal; `6881072` | Reviewer: timeout drive (no run process left, scratch `[]` before the report); mutant sweep. P1 below concerns one survivor | ✅ (P1 open) |
| R3 | `tests/mutants.py` `ChildTimeout`, `run_case` try, report; `6881072` | Reviewer: timeout drive (`FAILED` line naming the timeout and its limit, later cases run, exit 1); integration row in both eras | ✅ |
| R4 | `tests/mutants.py` (all other statements unchanged) | Reviewer: 14-case planted and unmutated sample vs develop's runner, identical. Orchestrator (spec-held evidence): `gate.py within-limit` green against the recorded develop output; `gate.py untouched` red as committed (F3), green re-pinned | ✅ behaviour; gate record per F3 |

Unmapped changes (possible scope creep): the runner's own signal handling (`RunnerSignal`,
`stop_on_signals`, `die_by`, the `HELD` mask, `except BaseException: stop_run(proc)` in `run_child`,
the `__main__` wrapper). No R-ID asks for it; it follows from running the child in its own session,
which takes the child out of the terminal's process group, and the signal drive shows it stops the
whole run. Reported, not blocking. The `issues/` status flips and the `ROADMAP.md` line are
lifecycle bookkeeping.

## Findings

### [MEDIUM/CONFIRMED] F1 — `AGENTS.md` § Testing and the module docstrings misdescribe the runner and its test module
- **Where:** `AGENTS.md:1432`; the runner paragraph of § Testing (`AGENTS.md:1553-1586`);
  `tests/test_mutations.py:4`; `tests/mutants.py:25`.
- **Failure scenario:** § Testing lists `tests/test_mutations.py` as (`unit`), "the fast half of the
  mutation runner", but the diff adds an `@pytest.mark.integration` row that drives real processes
  through `bin/sandbox.sh` for about 9.4 s; sibling entries record both markers. The runner paragraph
  gained only the `LIMIT` sentence: it does not say the child runs in a session of its own, that
  TERM, HUP or Ctrl-C to the runner stop the whole run first, or that a report can carry a second
  `still running 10 s after the stop: pids …` line. None of the new names (`GONE_WITHIN`,
  `GONE_POLL`, `HELD`, `ChildTimeout`, `RunnerSignal`, `run_members`, `stop_run`, `_wait_gone`,
  `stop_on_signals`, `die_by`) appears in `AGENTS.md`.
- **Evidence:** `git grep -n 'mark.integration' -- tests/test_mutations.py` → line 474;
  `verify-new-rows.log` (9.42 s); `.local/review1/agents-symbol-grep.log` (no hit for each name).
- **Touches:** rubric Scope 5, operating-manual drift outside § Invariants (MEDIUM).

### [LOW/CONFIRMED] F2 — `issues/sandbox-dirs-left-on-kill.md` misstates how the runner kills its sandbox, and breaks a referent
- **Where:** `issues/sandbox-dirs-left-on-kill.md:23-25`.
- **Failure scenario:** the added sentence says the timeout path is "where `subprocess.run` SIGKILLs
  the `bin/sandbox.sh` it started". `run_child` no longer uses `subprocess.run`; the wrapper is frozen
  and then SIGKILLed by `stop_run`. The defect the seed records still holds (a sandbox home is left
  on the timeout path). The sentence is also inserted before "The last three point the drive's
  `TMPDIR` at the test's own directory", which now reads as including the runner, which sets no
  `TMPDIR` and leaves its homes in the host's.
- **Evidence:** `git grep -n 'subprocess.run' -- tests/mutants.py` → only `tests/mutants.py:5729`
  (`_processes`); `git grep -n TMPDIR -- tests/mutants.py` → none; `probe-timeout-branch.log`
  (a sandbox home left in the runner's `TMPDIR`).
- **Touches:** a seed in the graded diff that misstates the repo (rubric, *What the reviewer sees*).

### [LOW/CONFIRMED] F3 — the cycle's frozen `untouched` gate is red at the reviewed commit: its `BASE` predates the rebase
- **Where:** `spec/mutant-child-outlives-timeout/verify/gate.py:44` (`BASE = '71a3a49…'`).
- **Failure scenario:** `BASE` pins the pre-rebase shape commit, which is no longer an ancestor of
  `HEAD`. After the rebase onto `e378c33`, `git diff --cached --name-status BASE` also carries
  develop's own commits since `0bfacae` (`ROADMAP.md`, four `issues/skip-check-*` files,
  `spec/skip-check-fence-gaps/*`, `tests/test_hygiene.py`), so the gate both phases' `verify` name
  reports twelve files outside the cycle and exits 1. R4's Clarification cites this gate as part of
  its evidence. The property it checks holds: the runner, its test module and `AGENTS.md` are
  identical between `71a3a49` and `origin/develop`, and with `BASE` re-pinned to the rebased shape
  commit the gate is green.
- **Evidence:** `uv run --no-project python -I spec/mutant-child-outlives-timeout/verify/gate.py untouched`
  → twelve `FAIL … outside the cycle's files`, `red  untouched`, exit 1
  (`.local/review1-orch/untouched-as-committed.log`); the same file with `BASE = '1e3ea35…'`
  (`.local/review1-orch/gate-rebased-base.py`) → `ok  untouched`.
- **Touches:** R4's recorded evidence; rubric, "a green gate can lie" (here a red one that no longer
  measures the cycle).

### [PLAUSIBLE] P1 — no row pins that the stop waits for every process it found, not only the wrapper's
- **Where:** `tests/mutants.py` `stop_run` → `_wait_gone`.
- **Scenario:** mutant `sr-wait-gone-wrapper-only` (the stop hands only the wrapper's pid and group to
  `_wait_gone`) survives `tests/test_mutations.py`. SIGKILL is delivered asynchronously, so a run
  process outside the wrapper's group (a new-session descendant) can still be in the table, not yet
  a zombie, when the runner prints its report; R2 says no process of the run is running once the
  case is reported. The reviewer's real-tree drive with the mutant planted gave the branch's outcome
  (`mutprobe-sr-wait-gone-wrapper-only.log`), so the window was not reproduced; it is likeliest on a
  loaded host.
- **Recommendation:** fix (it cites R2's wording, so fix or drop, never defer): a row that holds
  `stop_run` to hand every found pid and group to `_wait_gone`. Cheap, in the module the build
  reopens anyway.

### Coverage observations (surviving mutants, not CONFIRMED)

| Mutant | Class | Why |
|---|---|---|
| `rm-pid1-included` | equivalent | pid 1 has ppid 0 and group 1; it can never be linked to the run |
| `wg-strict-end` (`>=` → `>`) | equivalent | the deadline boundary only |
| `rm-single-pass` | equivalent at the stop | the outer walk-and-look loops reach the fixpoint; real-tree drive identical (`mutprobe-rm-single-pass.log`); no unit row pins `run_members`' own "until nothing is added" |
| `rm-own-group-seeded` | defence in depth | the seed group is always the wrapper's session-led group, never the runner's |
| `wg-gone-not-filtered`, `wg-groups-not-pruned` | defence in depth | guards against pid or pgid reuse within `GONE_WITHIN`; the `still-running` row's "never signalled again" is held by the members filter, not by these |
| `sr-wait-gone-wrapper-only` | see P1 | |

The rubric's default home for these is an `issues/` seed. Since the module goes back to build for
F1–F3, the recommendation is to fold the `rm-single-pass` and the two `wg-*` pins into that build
instead; the routing is the gate's call.

Timing figures (`LIMIT` 300 s, `GONE_WITHIN` 10 s, `GONE_POLL` 0.1 s, the integration row's run
time) were not graded; their use was: `LIMIT` reaches `communicate(timeout=LIMIT)` and
`ChildTimeout(LIMIT, …)`, `_wait_gone` uses only the two `GONE_*` figures, and the mutants that
hard-code either figure are killed.

## Human-gate triggers

- Not triggered. No CONFIRMED finding is in a path on § Invariants' high-blast-radius list or in a
  section marked *[human gate]*: F1 is in § Testing and two test-module docstrings, F2 in an
  `issues/` seed, F3 in this cycle's `spec/` gate.

## Optional completeness sub-pass (separate reviewer; may see TECH.md)

- Not run (not requested).
