# PLAN — A mutant whose child run hangs is reported, and leaves nothing running

> **Status:** Draft for review · **Last updated:** 2026-11-09
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). There is no `research/`: this is the lean
> path (`kind: fix`, `appetite: small`, root cause known, no high-blast-radius path touched); the one
> unknown was settled by a lab probe (§ 4). Every design element traces to a GOAL R-ID.

## 1. Summary

`run_child` starts the child run in a session of its own and waits for it with `communicate`, as
`subprocess.run` does today. When the limit passes, the runner freezes the run (SIGSTOP), finds every
process of it from one `ps` table (descendants through live parents, and every member of a process
group one of them is in, to a fixpoint), SIGKILLs them all, and waits until none is running. It then
raises `ChildTimeout`, which `run_case` turns into the case's violation, so `main` prints a `FAILED`
line naming the timeout and its limit and goes on to the next case. Nothing changes on the path of a
child that ends within its limit except how the child is started: a session of its own. The change
stays inside `tests/mutants.py`'s child-run block, plus rows in `tests/test_mutations.py`.

## 2. Design

All code changes are in `tests/mutants.py`. The new statements sit together between `apply_repo` and
`run_child` (the run-child block); `run_child`'s body and `run_case`'s call to it change; the
`__main__` block gains one call. `CASES`, `SURVIVOR_CONTROL`, `apply`, `apply_repo`,
`mutation_violations`, `self_check` and `main` stay byte-identical (the `untouched` gate holds this).

**Figures** (module constants, each a timing bound for the maintainer, § 3 row D3):
`LIMIT = 300`, the per-case limit the GOAL fixes, read by `run_child` at call time (so a test can
patch it); `GONE_WITHIN = 10`, how long after the kill the runner waits for the run to be gone;
`GONE_POLL = 0.1`, how often it looks.

**Starting the run.** `run_child` builds the same argv and environment as today and starts them with
`subprocess.Popen(..., env=env, stdout=PIPE, stderr=PIPE, text=True, start_new_session=True)`, then
`out, err = proc.communicate(timeout=LIMIT)` and returns
`subprocess.CompletedProcess(proc.args, proc.returncode, out, err)`: exactly what `subprocess.run`
does with `capture_output=True, text=True, timeout=300`, so a child that ends within its limit is
read as before (R4). The new session makes the `bin/sandbox.sh` wrapper the leader of a process group
and a session that hold nothing of the runner's, so the run can be stopped whole without reaching the
runner, its caller or its siblings (R1's "none that the run did not start").

**Early exits.** `except subprocess.TimeoutExpired`: `left = stop_run(proc)`, close `proc.stdout`
and `proc.stderr` without reading them (a process the stop could not reach may still hold the write
end, and draining would wait on it), and `raise ChildTimeout(LIMIT, left) from None`.
`except BaseException`: `stop_run(proc)`, close the pipes, re-raise. The second clause covers a
KeyboardInterrupt and `RunnerSignal` (below): since the run no longer shares the caller's process
group, a Ctrl-C or a group-wide TERM no longer reaches it, so the runner stops it itself (§ 3 row D2).

**`ChildTimeout(Exception)`** carries `limit` and `left` (the pids of the run still running after
`GONE_WITHIN`; empty in every expected case).

**`_processes()`** returns `{pid: (ppid, pgid, stat)}` from one
`subprocess.run([str(SANDBOX), 'ps', '-A', '-o', 'pid=,ppid=,pgid=,stat='], capture_output=True,
text=True, check=True)`. `ps` takes these four keywords on macOS and on Linux (procps); there is no
`/proc` on macOS and `psutil` is not in the lock. It runs through `bin/sandbox.sh` because the suite's
rail requires every launch in `tests/*.py` to (`test_cli_drives_are_sandboxed`; § 3 row D6).

**`run_members(table, pids, groups, own=None)`** (`own` is the runner's `(pid, pgrp)`, read at call
time when not given) is pure: starting from the
known `pids` and `groups`, it adds every process in `table` whose parent is a known pid or whose
group is a known group, and that process's group, until nothing is added. It never adds `own[0]`,
and never adds `own[1]` as a group (a guard: with the run in its own session no process of it can be
in the runner's group, but a regression that drops the new session must not turn the stop on the
runner's own group). It returns the new `(pids, groups)`.

**`stop_run(proc, *, processes=_processes, kill=os.kill, killpg=os.killpg, mask=signal.pthread_sigmask,
clock=time.monotonic, sleep=time.sleep) -> list[int]`**, the stop, in this order:

0. `mask(SIG_BLOCK, {SIGINT, SIGTERM, SIGHUP})`, undone (`SIG_UNBLOCK`) in a `finally` when the stop
   ends: a Ctrl-C or a signal to the runner during the stop is held and acts after it, never half-way.
1. `killpg(proc.pid, SIGSTOP)`: the wrapper's group, which holds the child pytest and everything it
   started without a new group, stops (`ProcessLookupError` ignored: the group may be gone already).
2. Fixpoint: take a table, `run_members` from `({proc.pid}, {proc.pid})`; SIGSTOP each new pid and
   each new group, recording the order they were found in; take a new table; repeat until a table
   adds nothing. A stopped process cannot fork or exit by itself, and a stopped parent cannot reap,
   so the pids found stay theirs while the walk goes on.
3. SIGKILL in reverse discovery order: the groups and pids found last go first, the wrapper's group
   last (`killpg` for each group, `kill` for each pid; `ProcessLookupError` and `PermissionError`
   ignored, and a process that cannot be killed shows up in step 4). Killing a group first could
   orphan a later group of stopped members, and the kernel sends such a group SIGHUP and SIGCONT
   (seen on macOS by the adversarial review, § 7); reverse order kills each group before any group
   its link runs through.
   Steps 1–3 run inside `try`/`finally`: if anything breaks out of them (a `ps` that fails, a
   `ProcessLookupError` where none was expected), the `finally` SIGKILLs every group and pid found so
   far and the wrapper's group, in the same order, then the exception goes on. A frozen run is never
   left behind: its group is orphaned from birth, so nothing would ever continue it.
4. `_wait_gone`: until `GONE_WITHIN` has passed, take a table, extend the members with `run_members`
   (a process forked as its parent stopped lands in the parent's group; one reparented once its
   parent died still carries a group of the run), drop for good every member that is absent or a
   zombie (`Z` in `stat`; init reaps it), so a number the kernel hands out again is never killed, and
   return `[]` as soon as no member is left; otherwise SIGKILL every member still running and sleep
   `GONE_POLL`. After `GONE_WITHIN`, return the pids still running.
5. `proc.wait()`: the wrapper is reaped only now, so its pid and group number stay reserved through
   step 4 (the `finally` of step 3 reaps it too before the exception goes on).

No grace and no TERM: the run is SIGKILLed at the limit, as `subprocess.run` SIGKILLs the wrapper
today (§ 3 row D4). The wrapper's `trap` does not run, so its sandbox home stays, which the GOAL
leaves to [`issues/sandbox-dirs-left-on-kill.md`](../../issues/sandbox-dirs-left-on-kill.md); no
second cleanup is built here.

**`timeout_violations(exc)`** is pure: `[f'timeout: the child ran past its {exc.limit} s limit and was
stopped']`, plus `f'still running {GONE_WITHIN} s after the stop: pids {…}'` when `exc.left` is not
empty.

**`run_case`**: `child = run_child(...)` becomes `try: child = run_child(...)` /
`except ChildTimeout as exc: return timeout_violations(exc)`, inside the existing
`TemporaryDirectory` block, so the case's scratch copy is removed before `run_case` returns and
before `main` prints the case's line (R2). `main` is unchanged: a non-empty violation list prints
`FAILED  {id}: {violations}`, sets `failed` and the loop goes on (R3).

**`stop_on_signals()`** installs one handler for SIGTERM and SIGHUP that raises
`RunnerSignal(signum)`, a `BaseException` subclass, so `run_child`'s `except BaseException` stops the
run. The `__main__` block calls it before `main()`, and catches `RunnerSignal` around `main()` with
`die_by(signum)`: the handler back to `SIG_DFL`, then `os.kill(os.getpid(), signum)`, so the runner
dies by the signal it got, as the project's own contract re-raises a signal death (the
`signal-death-not-reraised` case), rather than exiting 143 or 129. `stop_on_signals` is not called at
import (the suite imports the module), and installs nothing outside the main thread.

**Docs, same commit.** The module docstring gains one sentence on the limit and the stop.
`AGENTS.md` § Testing's mutation-runner bullet: "A `FAILED` line means a case survived … or was killed
for the wrong reason …" gains "or that its child ran past the runner's 300 s limit (`LIMIT`), in which
case the runner first stopped the whole run". *Amended 2026-11-09 (foreman ruling):*
`issues/sandbox-dirs-left-on-kill.md` is not rewritten here. That seed belongs to the
`sandbox-dirs-left-on-kill` cycle, which keeps `bin/sandbox.sh` as it is and has each harness that
SIGKILLs a sandbox point its `TMPDIR` into a directory the harness owns, plus a suite-session sweep;
its sentence naming this runner's timeout path is that cycle's to restate.

**Touch points for the sibling cycle** (`mutants-workflow-timeout`, which may shard or run cases
concurrently): the import block (`signal`, `time`); the run-child block (new, between `apply_repo` and
`run_child`); `run_child`'s body; three lines in `run_case`; one line in the `__main__` block. `main`
and `self_check`, where a sharding change most likely lands, are untouched. Everything in the stop is
per call (the walk starts from that call's own wrapper, and no state is global), so concurrent runs do
not reach each other; only `stop_on_signals` is process-wide, and it stays in `__main__`.

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1   | `start_new_session=True`; `stop_run` (signals held, freeze, `run_members` fixpoint over ppid and pgid, SIGKILL of every group and pid in reverse discovery order, a `finally` that kills what was found, `_wait_gone`), called before `run_child` raises, so before `run_case` returns; `run_members`' guard on the runner's own pid and group; the wrapper reaped last, and gone members dropped, so no reused pid is touched. Reading in § 3 row D1. |
| R2   | `_wait_gone` returns only when no member of the run is running (or names them, after `GONE_WITHIN`); `run_case` returns from inside its `TemporaryDirectory`, which removes the scratch copy before the report. |
| R3   | `ChildTimeout` → `timeout_violations` (names "timeout" and the limit in seconds) → `main`'s unchanged `FAILED` branch; the loop goes on; `failed` makes the exit 1. |
| R4   | Within the limit, `Popen` + `communicate(timeout=LIMIT)` + `CompletedProcess` is `subprocess.run`'s own sequence; nothing else on that path changes (`untouched` gate); the sample sweep and `--self-check` print exactly what develop's runner printed, and the sample's targets, run unmutated, still all pass (`within-limit` gate: both directions, kills and survivals). |

## 3. Invariant gate (AGENTS.md constitution check)

Checked against `AGENTS.md` § Invariants before design and again after it was drafted. The change
touches no numbered section (§1–§9): nothing under `packages/`, and `bin/sandbox.sh` (on the
high-blast-radius list) is only run, never edited. The sections it touches:

- **§ Testing, the mutation runner bullet** — the runner's rule (a case is caught only when every
  target fails with its `why`) is unchanged: a timeout is a `FAILED` line, never a kill (GOAL
  Clarification 2). The bullet changes in the same commit as the behaviour.
- **§ Testing, internals-bound item 5** (`tests/mutants.py` and its anchors) — no anchor and no case
  moves; `test_mutation_anchor_applies` is untouched and stays green.
- **§ Testing, the suite's rails** — every launch in `tests/*.py` goes through `bin/sandbox.sh`
  (`_processes`' `ps`, the integration row's sentinels); unit rows launch nothing (the unit guard),
  using fakes injected into `stop_run` and a fake `Popen`; every new test carries `unit` or
  `integration`.
- **§ Conventions** — comments are declarative and carry no spec or finding id
  (`test_no_spec_ids_in_the_package_or_the_suite`); no `Co-Authored-By`; a rule is pointed to, not
  restated (the bullet names `LIMIT`, it does not restate the stop).
- **§ Factory, `ci budget`** — the new rows run in each era's fourth suite command; their cost is
  row D5.
- **§ Throwaway environment** — every child run, `ps` and sentinel is under `bin/sandbox.sh`; the
  sandbox's contract is untouched.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| **D1 — R1/R2 reading: "every process that run started" is every process reachable from the run's wrapper at the stop, through a chain of live parents or through membership in a process group of such a process.** A process that both left every group of the run (`setsid`, `setpgid`) and lost its parent before the stop has no link left to the run, and is not found. **Settled: GOAL Clarifications, 2026-11-09, foreman ruling at the PLAN/TECH gate** (§ 5, Q-A). | POSIX gives no way to name "everything descended from X" once a link is gone: there is no session kill, macOS has no `/proc` and no child subreaper, and `ps` reports only the parent and group links this walk follows. In the suite such processes exist only where a row creates one on purpose (`tests/test_launch.py`'s `ESCAPE`, `tests/test_timeout_stop.py`'s `LEFT`), each sleeping 20–30 s and removed by its own row's teardown, which a SIGKILLed run skips. The 2026-11-05 leftover (the pytest itself, its loopback execs, its relay) is all reachable. | (a) An environment marker in the child, matched with `ps -E`/`/proc/*/environ`: the loopback server starts every exec under `env -i`, and `sudo` resets the environment, so the marker misses exactly these processes. (b) Linux `PR_SET_CHILD_SUBREAPER`: Linux only, and under the sibling cycle's possible concurrency it would mix runs, breaking "none that the run did not start". (c) `lsof` on the runner's pipes: pytest's fd capture means a test's processes do not hold them. |
| **D2 — The run no longer shares its caller's process group or session**, and the runner adds two stops: on any exception out of `communicate` (`except BaseException`), and SIGTERM/SIGHUP handlers installed by the `__main__` block. | A new session is what makes the run's groups stoppable without reaching the runner or its caller (a `tee` in the caller's pipeline shares the runner's group). It also takes the run out of reach of a Ctrl-C at the terminal and of a caller that signals the runner's group (GNU `timeout`, a harness's command cap), which today reach it; the two stops restore that for SIGINT, SIGTERM and SIGHUP, and the runner still dies by a TERM or HUP it gets (`die_by`), as today. A SIGKILL to the caller's group still reaches only the runner, which is the one case the change makes worse (§ 5). | Keeping the run in the caller's group and walking parents only: the runner can never `killpg` its own group, so an orphan left in it by the run is missed, and a walk by parent alone misses every orphan. |
| **D3 — Timing figures (needs the maintainer's ruling):** `GONE_WITHIN = 10` s, `GONE_POLL = 0.1` s. | R2 needs the runner to know the run is gone before it reports; a SIGKILLed process is gone only once the kernel has torn it down, so the runner looks until it is, within a bound so a process stuck in an uninterruptible wait cannot hold the sweep forever. | No bound: a process stuck in an uninterruptible wait would hold every later case. No poll (one look): a loaded host can show a just-killed process for a few milliseconds, and R2 would then fail at random. |
| **D4 — No grace: SIGKILL at the limit** (SIGSTOP first, to freeze the walk). | The GOAL fixes the limit and leaves any grace to the maintainer; none is needed for R1–R3. | SIGTERM, a grace, then SIGKILL: it would let the sandbox's `trap` remove its home, which the GOAL gives to `issues/sandbox-dirs-left-on-kill.md`, and it adds a figure. |
| **D5 — Suite cost (needs the maintainer's ruling):** the integration row runs a real sandboxed child at a patched `LIMIT = 8` s, about 10–11 s per era on a development host (projected; measured by P1's build at 10.06 s legacy and 9.51 s modern, § 5), in each era's fourth suite command. | R1–R3 are about real processes; only a real child run proves the walk finds a pytest, its same-group child, its same-group orphan and its new-session child, and leaves the caller's own processes alone. The unit rows pin each decision without a process. | A row at the real 300 s limit: five minutes per era. A row with no real child: it would test the fakes, not `ps`, signals or the sandbox. |
| **D6 — `ps` runs under `bin/sandbox.sh`**, about 30 ms per table on a development host (measured 2026-11-09). | The suite's rail requires every launch in `tests/*.py` to go through it, and `tests/mutants.py` is read by that rail. | Exempting `tests/mutants.py` from the rail loosens a gate for every later change to it. |
| **D7 — R4 is shown by a 22-case sample in two passes (planted: every case still killed with its `why`; unmutated: every target still passes) and the three `--self-check` controls**, each against develop's recorded output, and by the `untouched` gate; not by a sweep of all 1,165 cases. **Shows R4 another way; settled: GOAL Clarifications, 2026-11-09, foreman ruling at the PLAN/TECH gate** (§ 5, Q-B). | A full sweep is 49–97 minutes serial (sibling GOAL's projection), twice over (before and after); the change to the within-limit path is one `Popen` argument, which the sample exercises in every family of child (executors, loopback SSH, launcher, startup, probes, timeout stop, repository plants). | The full sweep per phase: well past the 10-minute command cap for a `small` appetite. |

Each row was read against R1–R4's wording. D1 and D7 are the two where the design reads or shows an
R-ID in a way the GOAL's words did not settle; both went to the sign-off and are now GOAL
Clarifications (§ 5). D3 and D5
are figures; their before-and-after is in § 5. *Amended 2026-11-09:* D3 (`GONE_POLL = 0.1`,
`GONE_WITHIN = 10`) and D5 (one integration row at about 10–11 s per era, in each era's fourth suite
command; above 15 s per era as P1 measures it, it goes back to the maintainer) were approved by the
maintainer at the PLAN/TECH gate, 2026-11-09.

## 4. Rabbit holes (resolved)

- **Finding a run's processes on macOS without `/proc`** → `ps -A -o pid=,ppid=,pgid=,stat=` works on
  both platforms. A lab probe (2026-11-09, a throwaway directory, removed after) started a run in its
  own session holding a same-group orphan (parent gone) and a new-session grandchild, froze the group,
  walked: two rounds found all three by ppid and pgid; the runner's own group was never in the set;
  SIGKILL of the groups and pids left nothing running at the first confirmation look (15 ms). One
  table: 17 ms bare, about 30 ms under `bin/sandbox.sh`, 821 processes on the host.
- **Does a new session change a within-limit verdict?** The suite's own uses of the process group
  (`tests/test_timeout_stop.py`'s and `tests/test_launch.py`'s teardowns compare against
  `os.getpgrp()` only to avoid killing their own group) behave the same in either group; no test
  reads a controlling terminal; CI and agent gates run without one already. The baseline sample
  (`verify/within-limit.expected`, develop's runner, 99–104 s) is reproducible: two runs, same text.
- **Draining after the stop** → not done: a process the stop could not reach (row D1) may hold the
  pipe's write end, and `communicate()` would wait on it. The pipes are closed unread; a timed-out
  case reports no stderr tail.
- **The race between walk and kill** → the freeze holds through the walk: stopped processes neither
  fork nor exit, and stopped parents do not reap, so no pid found is reused before the kill. It does
  not hold through the kill by itself: killing a group can orphan a group of stopped members, which
  the kernel continues (SIGHUP and SIGCONT; the adversarial review saw it on macOS). Reverse discovery
  order kills such a group first, and `_wait_gone`'s re-walk catches anything a continued member
  forks before its SIGKILL lands (it inherits a known group). A fork already inside the kernel when
  its parent stopped lands in the parent's group, which the kill and the re-walk cover.
- **Adversarial review** (trigger 3: the runner is a verification harness) → see § 7.

## 5. Risks & open questions

- **Q-A (resolved, GOAL Clarifications, 2026-11-09, foreman ruling at the PLAN/TECH gate): R1/R2's
  reach.** "Every process that run started" is every process reachable at the stop through a live
  parent or a process group of the run (row D1); a process that has cut both links before the stop is
  out of reach.
- **Q-B (resolved, GOAL Clarifications, 2026-11-09, foreman ruling at the PLAN/TECH gate): how R4 is
  shown.** By the 22-case two-pass sample and the controls against develop's recorded output, with the
  `untouched` gate holding every other runner statement byte-identical (row D7).
- **D2's trade-off** (a SIGKILL to the caller's whole group reaches only the runner) was accepted at
  the PLAN/TECH gate, 2026-11-09.
- **Timing figures for the maintainer.**
  - *Stop confirmation* (D3). Before: no stop; `subprocess.run` SIGKILLs the wrapper at 300 s and
    raises; the run's pytest has been seen running more than 7 minutes later. After: at 300 s the run
    is frozen and SIGKILLed (no grace, as before), and the runner waits up to `GONE_WITHIN = 10` s,
    looking every `GONE_POLL = 0.1` s; expected cost after the limit, about 0.1 s (two or three tables
    at about 30 ms, one confirmation look); worst case 10 s plus the walk.
  - *Grace* (D4). Before: 0 s (SIGKILL at the limit). After: 0 s. No change.
  - *Suite cost* (D5). Before: `tests/test_mutations.py` is all `unit`, under 1 s. After: plus one
    integration row at a patched `LIMIT = 8` s, about 10–11 s per era (projected). Measured: 10.06 s in
    the legacy era and 9.51 s in the modern era (`pytest --durations=0`, the row alone, run right after
    P1's gate on the P1 commit's code, a development host at load average about 5, 2026-11-09), in each
    era's fourth suite command; the `ci budget` row's baselines for those
    jobs are 7:22 (`suite-legacy-4`) and 7:33 (`suite-modern-4`) of 10:00. The 8 s leaves room for
    every step the row asserts: the child is ready (pids written) about 1.5 s after start on a
    development host (sandbox and pytest start about 0.15 s, the import-origin check about 1 s); a
    hosted runner at three times that is still inside 8 s, and a child not ready by then fails the row
    by name ("never got ready"), never passes it.
  - *Test-only bounds* (inside the integration row, no effect on the runner): the patched limit,
    8 s; the timed-out case must return within `LIMIT + 5` s; the teardown waits up to 2 s for each
    process it killed to be gone.
- **A SIGKILL to the caller's process group** (a harness's hard kill) now kills only the runner and
  leaves its current run going until it ends by itself; today it kills both. SIGINT, SIGTERM and
  SIGHUP are handled (row D2). Mitigation beyond that needs a supervisor process, out of this
  appetite.
- **The sibling cycle** may change `run_case` too (concurrency). The overlap is three lines; the stop
  itself holds no global state and is safe to call from several threads, but `stop_on_signals` must
  stay in the main thread's `__main__` block.
- **Pid reuse** is closed rather than accepted: the wrapper is reaped only after the confirmation, so
  its number and its group's stay reserved, and a member found absent or a zombie is dropped for good,
  so a number handed out again is never signalled.
- **A run process owned by another user** (a `sudo` row run as root) cannot be signalled; it is
  reported in the `FAILED` line by `_wait_gone`, not hidden.
- **No prototype worktree.** The step's rules allow writes only inside the cycle worktree and the
  temporary directory, so the skill's detached prototype worktree was not made. The gates were
  dry-run on the base tree (§ 6), which is develop's runner; the `rows` mode stops at "not in the
  report" until P1 writes the rows.

## 6. Verification strategy

The frozen gate is [`verify/gate.py`](verify/gate.py): modes `untouched`, `rows ERA`, `within-limit`,
`prepush`, `controls` (its docstring says what each proves). Never edit it to make a phase pass.

**Rows P1 adds to `tests/test_mutations.py`** (names and parameter ids are frozen in the gate's
`ROWS`; each must be in the report and passed, in each era):

- `test_run_members_follow_parents_and_groups[child|grandchild|orphan-in-the-group|new-session-group|unrelated-orphan|runner-group]`
  (`unit`, tables as data): a child by ppid; a grandchild through a live parent; an orphan (ppid 1)
  in the wrapper's group; a new-session grandchild, and an orphan in its group; an unrelated orphan in
  another group, excluded; the runner's own pid and group, never added even when a table puts the
  wrapper in the runner's group.
- `test_gone_waits_until_every_process_ends[gone-at-once|zombie-is-gone|gone-after-polls|new-member-in-a-group|still-running]`
  (`unit`, fake tables, clock, sleep and kill): returns `[]` with no sleep; a zombie is gone; gone after
  two looks, sleeping `GONE_POLL` each time and re-killing a member still running; a pid that appears
  only in the second table, in a known group (and one whose parent is a known pid), is SIGKILLed and
  waited for; returns the pid once the clock passes `GONE_WITHIN`; a pid once absent is not killed
  when a later table shows that number again.
- `test_stop_run_freezes_then_kills_the_whole_run` (`unit`, fakes): the recorded calls are the signal
  mask blocked, SIGSTOP to the wrapper's group, SIGSTOP to each member and group as found and before
  the next table, SIGKILL to every group and pid in reverse discovery order with the wrapper's group
  last, the confirmation, `wait`, and the mask unblocked. The `runner-group` row of
  `test_run_members_follow_parents_and_groups` uses the default `own` (the test's real pid and group).
- `test_stop_run_kills_what_it_found_when_it_is_cut_short[table-fails|wrapper-gone]` (`unit`, fakes):
  the fake `processes` raises on its second table, and SIGKILL still goes to every group and pid
  already found and the wrapper's group, `wait` is called, the mask is unblocked, and the error
  propagates; a `ProcessLookupError` from the first SIGSTOP is ignored and the walk goes on.
- `test_the_stop_figures` (`unit`): `LIMIT == 300`, `GONE_WITHIN == 10`, `GONE_POLL == 0.1`.
- `test_a_timeout_reason_names_the_limit[gone|left]` (`unit`): the exact violation strings.
- `test_run_child_returns_what_the_child_returned` (`unit`, fake `Popen`): `start_new_session=True`,
  pipes, `text=True`, the same argv and `PYTHONPATH` as today; `communicate(timeout=LIMIT)` (patched
  value); the result's args, returncode, stdout and stderr; `stop_run` never called.
- `test_run_child_stops_the_run_on_every_early_exit[timeout|interrupt|signal]` (`unit`, fake
  `Popen`): a `TimeoutExpired` calls `stop_run` once, closes both pipes, never calls `communicate`
  again, and raises `ChildTimeout` with the patched limit and `stop_run`'s list; a `KeyboardInterrupt`,
  and a `RunnerSignal(SIGTERM)`, each call `stop_run` and propagate.
- `test_a_runner_signal_exits_through_the_stop[term|hup]` (`unit`, `signal.signal` and `os.kill`
  recorded): the installed handler raises `RunnerSignal` with that signal; `die_by` sets `SIG_DFL` for
  it, then sends it to the runner's own pid.
- `test_the_script_installs_the_signal_stop` (`unit`, AST of `tests/mutants.py`): the `__main__` block
  calls `stop_on_signals()` before `main()`, and its handler for `RunnerSignal` calls `die_by`.
- `test_a_child_past_its_limit_is_stopped_whole_and_reported` (`integration`): a throwaway repository
  in `tmp_path` holds `tests/test_hang.py` (records the pytest's pid, the wrapper's, a same-group
  child, a new-session child and a same-group orphan, each a `python -c` sleeper carrying the token
  `mutant-hang-` in its argv; each sleeper writes its own `getppid()`, `getpgrp()` and `getsid(0)`
  once it is in place, the orphan only once its parent is no longer its spawner; the test records
  its `PYTHONPATH`, writes a ready file, then sleeps) and `tests/test_quick.py` (fails with
  `planted`). `TMPDIR` is set to a directory under `tmp_path` for the row, so the sandbox homes the
  killed wrappers leave go with `tmp_path`, not into the host's temporary directory. With `mutants.LIMIT` patched to 8, `mutants.TESTS` to that repository's
  `tests/`, `mutants.CASES` to a `hang` case then a `quick` case (both planting `SURVIVOR_CONTROL`'s
  docstring edit), `tempfile.tempdir` to an empty directory, and two sentinels started through
  `bin/sandbox.sh` (one in the test's own process group, one in a session of its own), it calls
  `mutants.main(['hang', 'quick'])` with `run_case` wrapped so that, the moment the `hang` case
  returns, it records: whether the ready file exists; each recorded pid's state, checked
  independently of the runner (`os.kill(pid, 0)`, and `ps -o stat=` under the sandbox for a zombie);
  the scratch directory's entries; and the time the case took. It asserts: ready; the layout as
  planned (the orphan's parent is not the pytest and its group is the wrapper's; the new-session
  child's group and session are its own; the child's group is the wrapper's), else it fails with
  "layout not as planned"; the recorded `PYTHONPATH` under the patched scratch directory; every
  recorded process gone or a zombie; the scratch directory empty; the case took under `LIMIT + 5` s; both
  sentinels running and not stopped (`T` absent from their `stat`); the output is exactly
  `FAILED  hang: timeout: the child ran past its 8 s limit and was stopped` followed by the `killed
  quick: …` line; the exit is 1. Its teardown SIGKILLs every recorded pid and both sentinels and
  waits, up to 2 s, until each is gone, so the gate's leftover check reads a settled host.

**Mutant decision list** (build's mutant pass plants each into a scratch copy of `tests/mutants.py`
and runs the rows; each must turn the named rows red, or is listed as an expected survivor with its
reason):

| Mutant | Must turn red |
|--------|---------------|
| `start_new_session=True` dropped | `returns_what_the_child_returned`, the integration row |
| `run_members` ignores pgid | `orphan-in-the-group`, `new-session-group`, the integration row |
| `run_members` ignores ppid | `child`, `grandchild`, `new-session-group`, the integration row |
| the runner's own group not excluded | `runner-group` |
| SIGSTOP freeze dropped | `freezes_then_kills` |
| group SIGKILL dropped (pids only) | `freezes_then_kills` |
| kill in discovery order (not reversed), or the wrapper's group not last | `freezes_then_kills` |
| signal mask not blocked, or not unblocked | `freezes_then_kills`, `cut_short[table-fails]` |
| the `finally` kill dropped | `cut_short[table-fails]` |
| first SIGSTOP's `ProcessLookupError` not ignored | `cut_short[wrapper-gone]` |
| `proc.wait()` before the confirmation | `freezes_then_kills` |
| `_wait_gone` returns at once / ignores `Z` / never re-walks / re-kills a number once gone | the `gone-*` rows (`new-member-in-a-group` for the re-walk) |
| `GONE_WITHIN` 10 → 1, `GONE_POLL` 0.1 → 1, `LIMIT` 300 → 30 | `test_the_stop_figures`, `gone-after-polls`, `still-running` |
| `communicate(timeout=LIMIT)` → `timeout=300` | `returns_what_the_child_returned`, the integration row (time bound) |
| `except BaseException` stop dropped | `early_exit[interrupt]`, `early_exit[signal]` |
| `except BaseException` narrowed to `KeyboardInterrupt` | `early_exit[signal]` |
| pipes drained (`communicate()` again) after the stop | `early_exit[timeout]` |
| `run_case` does not catch `ChildTimeout` | the integration row (the sweep stops) |
| the reason omits the limit | `reason_names_the_limit`, the integration row |
| the scratch `TemporaryDirectory` kept (`delete=False`) | the integration row |
| handler returns instead of raising | `runner_signal_exits` |
| `die_by` exits with a status instead of the signal | `runner_signal_exits` |
| `stop_on_signals()` or `die_by` dropped from `__main__` | `script_installs_the_signal_stop` |
| the orphan's layout not waited for (spawner still its parent) | the integration row's layout check |

**The `untouched` gate** holds, beyond the file list and the `AGENTS.md` bullet: every top-level
statement of `tests/mutants.py` but the docstring, the imports, `run_child`, `run_case` and the
`__main__` block byte-identical and in order; imports only at the top; one `__main__` block, last;
every new statement inside the run-child block and binding no name `BASE` binds (so no new statement
can rebind `CASES`, `MEMBERS`, `apply` or `SURVIVOR_CONTROL`); `run_case` unchanged but for one added
`try` around a statement of `BASE`'s; and every non-import top-level statement of
`tests/test_mutations.py` at `BASE` kept, byte-identical and in order (no existing row weakened).

**Gates per phase** (TECH.md): P1 runs `controls`, `untouched`, `rows` in each era,
`tests/test_hygiene.py` with `tests/test_mutations.py`, and `within-limit`. P2 runs `prepush` and
then the profile's full `verify`. Dry runs on the base tree (2026-11-09): `controls` ok (every plant
refused for its reason, the sound data accepted, 35 checks); `untouched` ok; `within-limit`'s planted
pass ok in 99 s and 104 s and its unmutated pass recorded in 81 s (the baselines,
`verify/within-limit.expected` and `verify/unmutated.expected`), then the whole mode re-run against
both: ok in 187 s; `prepush` ok once the gate's own
control text and a TECH sentence stopped tripping the private-text and ledger checks; `rows` stops at "not
in the report" until P1 writes the rows (17 s per era for the existing rows).

## 7. Adversarial review

One fresh reviewer pass (trigger 3; `appetite: small`), given the GOAL, this design and the drafted
gates, 2026-11-09. It found two HIGH and ten lower problems; every one is folded in above.

- **HIGH — a stop cut short left the run frozen for good** (a failing `ps`, a signal during the walk,
  a vanished wrapper group), worse than develop, since the run's group is orphaned from birth and
  nothing would continue it. Folded: signals held for the stop, steps 1–3 in `try`/`finally` that kill
  what was found, the first SIGSTOP's `ProcessLookupError` ignored; row `cut_short[…]`.
- **HIGH — the R4 sample checked only kills**, so a new-session start that made a target fail by
  itself (a false kill, which hides a survivor) would pass. Folded: the unmutated pass in
  `within-limit`, recorded on develop.
- **MEDIUM — the freeze does not survive the kill**: killing a group orphaned another group of stopped
  members, and macOS continued it (the reviewer's probe). Folded: reverse discovery order, § 4
  corrected, and the order pinned by `freezes_then_kills`.
- **MEDIUM — three mutants would have survived** (`except` narrowed to `KeyboardInterrupt`, no
  re-walk in `_wait_gone`, and the integration row passing on a layout it did not check). Folded:
  `early_exit[signal]`, `gone[new-member-in-a-group]`, the row's layout and `PYTHONPATH` assertions.
- **MEDIUM — the `untouched` gate had holes** (a rebinding of `CASES` inside the block, a fake
  `__main__`-like `if`, late imports, a free `run_case`, existing rows weakened). Folded: § 6's
  `untouched` list, each with a control.
- **LOW** — the row leaked a sandbox home into the host's temporary directory (`TMPDIR` now under
  `tmp_path`); `own` as an import-time default (now read at call time, one row uses it); pid reuse
  (closed, § 5); a TERM or HUP turned into an exit status (now `die_by`); a teardown that did not wait
  (now up to 2 s).

The reviewer confirmed sound: the within-limit path is `subprocess.run`'s own; group membership in a
new session cannot reach a process the run did not start; the `start_new_session`-dropped mutant is
caught by the integration row; nothing in the suite uses job control or a controlling terminal; the
arithmetic of the 8 s patched limit; and D1 and D7 belong at the sign-off.
