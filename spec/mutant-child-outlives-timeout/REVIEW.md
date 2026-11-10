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

## Review cycle 2 — changes-requested (2026-11-10)

- **Reviewed commit:** 3f5bdf991876e499651fd9efe896810d936a2f1c  ·  **Base:** develop (merge base `e378c33`; `origin/develop` now `146cbc6`)  ·  **Date:** 2026-11-10
- **Verdict:** changes-requested
- **Cycle:** 2 of ≤3 — mirrors `review.cycle` in `TECH.md`
- **Mode:** a fresh blind pass over the full spec-excluded diff, which also checked cycle 1's findings
  closed as properties (not a remediation-only pass).

One fresh blind reviewer (a subagent, effort xhigh, no sequential fallback) graded
`git diff origin/develop...HEAD -- . ':(exclude)spec/'` and the log, with `GOAL.md` and the rubric
inline, `AGENTS.md` by path, and cycle 1's finding text. A usage limit cut the reviewer off mid-pass;
it was resumed with HEAD unmoved and re-ran its whole pass (nothing from the cut-off run was saved or
reused). The orchestrator graded F3 and the spec-held part of R4's evidence. Contract drift: as in
cycle 1, `GOAL.md` moved after shaping only by the dated gate Clarifications (`d15317a`); graded
against `GOAL.md` at the reviewed commit. CI on `3f5bdf9` is green (reported by the foreman, not
observed here).

Evidence: the reviewer's probes, sweep and logs in the gitignored `.local/review2/`, the
orchestrator's in `.local/review2-orch/`. The reviewer's report came back as text; the harness refused
the orchestrator's copy of it as `.local/review2/REPORT.md`, so this section is its record.

### Verification run

- `uv sync --locked`, `uv lock --check` → exit 0 (`setup.log`).
- `tests/test_mutations.py`, legacy and modern eras → 1205 passed per era (`baseline-legacy.log`,
  `baseline-modern.log`); the integration row passed, not skipped, in both, 9.43 s and 9.45 s alone
  (`integration-duration-*.log`).
- `tests/test_hygiene.py tests/test_suite_parts.py`, both eras → 179 passed per era
  (`static-*.log`), `test_no_spec_ids_in_the_package_or_the_suite` included; a grep of every added
  line for spec ids → no match.
- R4 behavioural sample: 22 cases (seeded draw weighted to session- and group-sensitive targets,
  `r4-sample.txt`), branch runner vs develop's runner, both through `bin/sandbox.sh` (`r4_run.sh`,
  `r4/`): planted byte-identical, 22/22 killed with their `why`, exit 0; unmutated byte-identical,
  every target passes; `--self-check` byte-identical, three controls OK. Repeated under a controlling
  terminal for the 12 session-sensitive cases (`r4_pty.sh`, `r4pty/`) → identical.
- Timeout drive (`probe_timeout.py`, `probe-a/out.log`, limit patched to 6 s; a run tree with
  same-group, new-group, new-session, signal-ignoring fork-churning, zombie-holding and orphaned
  descendants; sentinels outside the run in three placements) → at each hang's report no run process
  left, all sentinels alive and not stopped, scratch empty;
  `FAILED  hang: timeout: the child ran past its 6 s limit and was stopped`; later cases ran; exit 1.
- Signal drive (`probe-sig-{TERM,HUP,INT}/out.log`) → the whole run stopped, sentinels alive, scratch
  empty; the runner died by the signal (143, 129, 130).
- Fork-failure drives (`probe_psfail.py`, `psfail/`; `probe_psfail2.py`, `psfail2/`) → F4 below.
- Mutant sweep, 105 mutants of the new code (46 deletions, 31 flips, **25 additive**, 3 reorders),
  each a preloaded copy under `.local/review2/mutants/` (the runner was never edited in place), against
  the 40 non-anchor rows, integration row included (`sweep-legacy.*`, `sweep-modern-survivors.*`) →
  85 killed, 3 killed by hang, 17 survived (the same 17 in the modern era); none CONFIRMED (table
  below).
- Orchestrator, `remediation/untouched.py` (the frozen `untouched` mode with the one § Testing entry
  F1 needed also cut; accepted at the build gate) → its two controls `ok`, then `ok  untouched`
  (`.local/review2-orch/untouched-remediation.log`).
- Orchestrator, `gate.py controls` → `ok  controls` (`.local/review2-orch/controls.log`).
- Orchestrator, `gate.py within-limit` → `ok  within-limit` in 179 s: the 22-case sample and the three
  `--self-check` controls print exactly `within-limit.expected`, the unmutated pass exactly
  `unmutated.expected` (`.local/review2-orch/within-limit.log`).
- Clean-up: `git status --porcelain` empty at hand-back and after; `tests/mutants.py` and
  `tests/test_mutations.py` hash-match HEAD; no probe process left; no build state mutated (the
  rlimit squeezes applied only to probe processes that have exited).

### Requirement → evidence matrix

| R-ID | Implemented by | Verified how (who) | Status |
|------|----------------|--------------------|--------|
| R1 | `run_child` (`start_new_session`), `stop_run`, `run_members`, `_wait_gone` | Reviewer: timeout drive, integration row both eras, R1 mutants killed; fork-failure drives (F4) | ❌ edge path (F4); ✅ main path |
| R2 | `_wait_gone` before return; scratch removed before the report | Reviewer: timeout drive (no run process, scratch empty at report), integration row | ✅ |
| R3 | `ChildTimeout` → `timeout_violations` → `FAILED` line; `main` goes on, exits 1 | Reviewer: timeout drive (exact line, later cases ran, exit 1), integration row; fork-failure drives (F4) | ❌ edge path (F4); ✅ main path |
| R4 | `Popen` + `communicate(timeout=LIMIT)`; every other statement unchanged | Reviewer: 22-case planted and unmutated sample + `--self-check` vs develop's runner, with and without a terminal. Orchestrator (spec-held): `gate.py within-limit` green; `untouched` green through `remediation/untouched.py` | ✅ |

Unmapped changes: the runner's own signal handling (`HELD`, the `except BaseException` stop,
`RunnerSignal`, `stop_on_signals`, `die_by`, the `__main__` wrapper), as in cycle 1; it follows from
the child's own session. Reported, not blocking. Seed and `ROADMAP.md` status lines are bookkeeping.

### Cycle-1 findings

| Finding | Status at `3f5bdf9` | Verified by |
|---|---|---|
| F1 (AGENTS/docstring drift) | **Not closed as a property**: every new name and behaviour is described except the new public `timeout_violations` (F5) | Reviewer |
| F2 (seed misstates the stop) | Closed: `issues/sandbox-dirs-left-on-kill.md:25-28` true at HEAD (freeze then SIGKILL, no `TMPDIR` set, homes in the runner's `TMPDIR`, seen in `probe-a`); the "last three" referent intact; seed `status:` and `ROADMAP.md` pointer correct | Reviewer |
| F3 (`untouched` gate red after rebase) | Closed: `BASE` is now found by the shape commit's subject on HEAD's history; the gate is green through `remediation/untouched.py` | Orchestrator |
| P1 (stop waits only for the wrapper's) | Closed for reachable input: `sr-wait-gone-wrapper-only` killed by `test_stop_run_waits_for_every_process_it_found` | Reviewer |
| Coverage observations | `rm-pid1-included`, `rm-single-pass`, `rm-own-group-seeded`, `wg-gone-not-filtered`, `wg-groups-not-pruned` now killed; `wg-strict-end` survives, equivalent | Reviewer |

### Findings

#### [MEDIUM/CONFIRMED] F4 — when the stop's own process-table look fails, the case goes unreported, the sweep stops and the run is left running
- **Where:** `tests/mutants.py:5892-5897` (`run_child`'s `except subprocess.TimeoutExpired`): an
  exception from `stop_run` escapes. `stop_run` forks `ps` for every look (`_processes`,
  `tests/mutants.py:5735`, `check=True`); `run_case` (`tests/mutants.py:5962`) catches only
  `ChildTimeout`. The row `test_stop_run_kills_what_it_found_when_it_is_cut_short[table-fails]` pins
  the re-raise; nothing turns it into a reported case.
- **Failure scenario:** a hung mutant whose run has used up the user's process budget (a fork loop
  that retries on `EAGAIN`, one of the ways mutated code can hang). At the limit the runner cannot
  fork `ps`: `BlockingIOError` leaves `main`, the case gets no `FAILED` line, no later case runs, and
  only the wrapper's group was frozen and killed. That is the GOAL's own defect again on this path:
  R3 unmet, and R1 unmet for the run's processes outside the wrapper's group.
- **Evidence:** `.local/review2/psfail2/out.log`: the probe lowered only its own `RLIMIT_NPROC` soft
  limit (user count + 40; no runner code patched); the run's new-session filler forked 50 sleepers to
  `EAGAIN`; at the stop `BlockingIOError: [Errno 35]` out of `main`, case `quick` never ran, 52 run
  processes still running (`S`/`Ss`, not frozen). `.local/review2/psfail/out.log` and
  `leftover-after-crash.txt`: the same crash with the limit squeezed after the run was ready.
- **Reachability:** reachable input class (a mutant that fork-loops while hanging); no existing case
  is known to do it. The reviewer did not exhaust the host's real per-user budget, for host safety.
- **Route as the property, both ways:** a case whose run passes its limit is always reported as not
  killed with the timeout named, and the sweep goes on, whatever the stop meets (a failed look
  included); and the stop never reports a run as fully stopped when it could not look, so the
  report names what may be left. Pin the completeness side (the report and the next case) and the
  liveness side (the run's processes outside the wrapper's group are still reached when a later
  look succeeds, or are named as possibly left).

#### [MEDIUM/CONFIRMED] F5 — residual operating-manual drift, F1's class: `timeout_violations` in the runner is described nowhere
- **Where:** `tests/mutants.py:5846` adds a public `timeout_violations(exc)` with its own row
  (`test_a_timeout_reason_names_the_limit`, `tests/test_mutations.py:331`). Neither `AGENTS.md` nor
  either module docstring names it, and `AGENTS.md`'s only mention of the name (`AGENTS.md:852`) is
  `tests/test_executors.py:197`'s different `timeout_violations(result, elapsed, bound)`, so a reader
  who looks it up lands on the wrong module.
- **Evidence:** `grep -n timeout_violations AGENTS.md` → line 852 only;
  `git grep -n 'def timeout_violations' -- . ':(exclude)spec/'` → two definitions; the reviewer's
  scripted check: all 89 other public `*_violations` in `tests/` are named in `AGENTS.md`.
- **Touches:** rubric Scope 5, drift outside § Invariants (MEDIUM). Route as F1's property: every
  symbol, behaviour and on-disk effect the diff introduces is described, checked mechanically.

### Mutant sweep: survivors (none CONFIRMED)

| Mutant | Class | Why |
|---|---|---|
| `rm-group1-seeded`, `rm-unsorted`, `rm-add-parent-of-found` (additive), `wg-strict-end`, `wg-own-dropped`, `sr-wait-gone-pids-wrapper-only`, `sr-extra-kill-found-groups-in-wait` (additive), `tv-figure-literal`, `rs-exception-base`, `die-exit-code`, `ps-min-fields` | equivalent | seeds are real pids > 1; same fixpoint set; a found process's parent is the run, the runner or init; deadline boundary; `own` never passed; every found pid's group is in the set; group ids are leaders' pids; the literal equals the constant; no `except Exception` where `RunnerSignal` lands; the process dies by the signal first; `ps` prints four fields |
| `wg-end-absolute` | coverage observation | the fakes start their clock at 0, so `end = GONE_WITHIN` is indistinguishable from `clock() + GONE_WITHIN`; in production it would skip every re-kill and wait after the first look. A 3 GiB-heap run process was already gone at the first look (`slow-*`), so it is not shown to break R2 |
| `sr-wait-gone-groups-wrapper-only` | coverage observation | matters only for a fork racing SIGSTOP into a non-wrapper group |
| `sos-valueerror-propagates` | coverage observation | reached only off the main thread, which never happens |
| `main-extra-sigint-ignore` (additive) | coverage observation | no R-ID; the documented Ctrl-C behaviour is not pinned against extra statements |
| `ps-check-false` | coverage observation | only when `ps` itself fails (F4's path) |
| `send-no-swallow-perm` | coverage observation | EPERM needs another real uid, which an unprivileged run cannot start |

The rubric's home for coverage observations is an `issues/` seed. The module goes back to build for
F4 and F5, and F4's fix runs through `ps-check-false`'s path, so the recommendation is to fold the
`wg-end-absolute` pin (a fake clock that does not start at 0) into that build and seed the rest only
if the gate prefers; the routing is the gate's call.

Timing figures (`LIMIT`, `GONE_WITHIN`, `GONE_POLL`, the integration row's run time) were not graded:
maintainer-approved. Their use was checked: the integration row runs 9.4 s per era, as `AGENTS.md`
states.

### Human-gate triggers

- Not triggered. F4 and F5 are in `tests/mutants.py` and `AGENTS.md` § Testing; neither is on
  § Invariants' high-blast-radius list nor in a section marked *[human gate]*. No earlier cycle
  recorded a trigger.

### Loop bound

Cycle 2 has not converged (cycle 1's F1 class recurs as F5, and F4 is new). Per the bounded loop,
escalated to Geoffrey before a third build↔review round.
