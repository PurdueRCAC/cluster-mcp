# Mutant sweep of the stop — record

Last run 2026-11-10, review cycle 2's remediation build, on its final `tests/mutants.py` and
`tests/test_mutations.py`, with [`sweep.py`](sweep.py): each mutant planted into a working copy of its
file (a plant that does not compile is reported `BOTCHED`, never run), only the rows it names run, the
file restored from a backup after each mutant and byte-compared at the end. 68 mutants in about
240 s on a development host: 67 killed (every named row red), 1 survived, recorded below as
equivalent. One plant (`pipes-drained`) first matched inside the new `try` at the wrong indentation
and broke the module's import; its anchor was moved to the statement after the `try` and it was run
again, killed.

The list holds PLAN § 6's decision list (the first 33), review cycle 1's surviving mutants (`sr-*`,
`rm-*`, `wg-*`, pinned by that remediation), review cycle 2's (`wg-end-absolute`, `f4-*`, `ps-*`), the gate's ruling on a child that cannot
launch (`launch-*`), and
additive mutants (`add-*`: code added, nothing removed), among them the three cycle 2 named: the
stop's error swallowed silently, the report claiming "stopped" after a failed look, and the sweep
halting, and the ruling's three: a launch error swallowed as a kill, the sweep halting on it, and its
cause dropped.

| Mutant | Verdict | Rows it names |
|---|---|---|
| `new-session-dropped` | killed (2/2) | `run_child_returns_what_the_child_returned`, `a_child_past_its_limit_is_stopped_whole_and_reported` |
| `members-ignore-pgid` | killed (3/3) | `run_members_follow_parents_and_groups[orphan-in-the-group]`, `run_members_follow_parents_and_groups[new-session-group]`, `a_child_past_its_limit_is_stopped_whole_and_reported` |
| `members-ignore-ppid` | killed (4/4) | `run_members_follow_parents_and_groups[child]`, `run_members_follow_parents_and_groups[grandchild]`, `run_members_follow_parents_and_groups[new-session-group]`, `a_child_past_its_limit_is_stopped_whole_and_reported` |
| `own-group-not-excluded` | killed (1/1) | `run_members_follow_parents_and_groups[runner-group]` |
| `freeze-dropped` | killed (1/1) | `stop_run_freezes_then_kills_the_whole_run` |
| `member-freeze-dropped` | killed (1/1) | `stop_run_freezes_then_kills_the_whole_run` |
| `group-kill-dropped` | killed (1/1) | `stop_run_freezes_then_kills_the_whole_run` |
| `kill-in-discovery-order` | killed (1/1) | `stop_run_freezes_then_kills_the_whole_run` |
| `wrapper-group-not-last` | killed (1/1) | `stop_run_freezes_then_kills_the_whole_run` |
| `mask-not-blocked` | killed (2/2) | `stop_run_freezes_then_kills_the_whole_run`, `stop_run_kills_what_it_found_when_it_is_cut_short[table-fails]` |
| `mask-not-unblocked` | killed (2/2) | `stop_run_freezes_then_kills_the_whole_run`, `stop_run_kills_what_it_found_when_it_is_cut_short[table-fails]` |
| `finally-kill-dropped` | killed (1/1) | `stop_run_kills_what_it_found_when_it_is_cut_short[table-fails]` |
| `first-stop-lookup-not-ignored` | killed (1/1) | `stop_run_kills_what_it_found_when_it_is_cut_short[wrapper-gone]` |
| `wait-before-confirmation` | killed (1/1) | `stop_run_freezes_then_kills_the_whole_run` |
| `gone-returns-at-once` | killed (3/3) | `gone_waits_until_every_process_ends[gone-after-polls]`, `gone_waits_until_every_process_ends[new-member-in-a-group]`, `gone_waits_until_every_process_ends[still-running]` |
| `gone-ignores-zombie` | killed (1/1) | `gone_waits_until_every_process_ends[zombie-is-gone]` |
| `gone-never-rewalks` | killed (1/1) | `gone_waits_until_every_process_ends[new-member-in-a-group]` |
| `gone-rekills-a-reused-number` | killed (1/1) | `gone_waits_until_every_process_ends[still-running]` |
| `gone-within-1` | killed (2/2) | `the_stop_figures`, `gone_waits_until_every_process_ends[still-running]` |
| `gone-poll-1` | killed (2/2) | `the_stop_figures`, `gone_waits_until_every_process_ends[gone-after-polls]` |
| `limit-30` | killed (1/1) | `the_stop_figures` |
| `communicate-300` | killed (2/2) | `run_child_returns_what_the_child_returned`, `a_child_past_its_limit_is_stopped_whole_and_reported` |
| `except-base-dropped` | killed (2/2) | `run_child_stops_the_run_on_every_early_exit[interrupt]`, `run_child_stops_the_run_on_every_early_exit[signal]` |
| `except-narrowed-to-interrupt` | killed (1/1) | `run_child_stops_the_run_on_every_early_exit[signal]` |
| `pipes-drained` | killed (1/1) | `run_child_stops_the_run_on_every_early_exit[timeout]` |
| `run-case-no-catch` | killed (1/1) | `a_child_past_its_limit_is_stopped_whole_and_reported` |
| `reason-omits-limit` | killed (3/3) | `a_timeout_reason_names_the_limit[gone]`, `a_timeout_reason_names_the_limit[left]`, `a_child_past_its_limit_is_stopped_whole_and_reported` |
| `scratch-kept` | killed (1/1) | `a_child_past_its_limit_is_stopped_whole_and_reported` |
| `handler-returns` | killed (2/2) | `a_runner_signal_exits_through_the_stop[term]`, `a_runner_signal_exits_through_the_stop[hup]` |
| `die-by-exit-status` | killed (2/2) | `a_runner_signal_exits_through_the_stop[term]`, `a_runner_signal_exits_through_the_stop[hup]` |
| `main-no-stop-on-signals` | killed (1/1) | `the_script_installs_the_signal_stop` |
| `main-no-die-by` | killed (1/1) | `the_script_installs_the_signal_stop` |
| `sr-wait-gone-wrapper-only` | killed (1/1) | `stop_run_waits_for_every_process_it_found` |
| `rm-single-pass` | killed (1/1) | `run_members_follow_parents_and_groups[found-later-in-the-table]` |
| `rm-own-group-seeded` | killed (1/1) | `run_members_follow_parents_and_groups[runner-group]` |
| `rm-pid1-included` | killed (1/1) | `run_members_follow_parents_and_groups[never-init-or-kernel]` |
| `rm-pid0-and-1-included` | killed (1/1) | `run_members_follow_parents_and_groups[never-init-or-kernel]` |
| `rm-group-1-added` | killed (1/1) | `run_members_follow_parents_and_groups[never-init-or-kernel]` |
| `wg-gone-not-filtered` | killed (1/1) | `gone_waits_until_every_process_ends[gone-numbers-never-followed]` |
| `wg-groups-not-pruned` | killed (1/1) | `gone_waits_until_every_process_ends[gone-numbers-never-followed]` |
| `wg-strict-end` | **survived** (0/1) | `gone_waits_until_every_process_ends[still-running]` |
| `add-sigcont-before-kill` | killed (2/2) | `stop_run_freezes_then_kills_the_whole_run`, `stop_run_kills_what_it_found_when_it_is_cut_short[table-fails]` |
| `add-wait-before-walk` | killed (1/1) | `stop_run_freezes_then_kills_the_whole_run` |
| `add-extra-look-before-confirm` | killed (2/2) | `stop_run_freezes_then_kills_the_whole_run`, `stop_run_waits_for_every_process_it_found` |
| `add-own-group-kill` | killed (3/3) | `stop_run_freezes_then_kills_the_whole_run`, `stop_run_kills_what_it_found_when_it_is_cut_short[table-fails]`, `stop_run_kills_what_it_found_when_it_is_cut_short[wrapper-gone]` |
| `add-own-pid-to-members` | killed (1/1) | `run_members_follow_parents_and_groups[runner-group]` |
| `add-sleep-before-first-look` | killed (2/2) | `gone_waits_until_every_process_ends[gone-at-once]`, `gone_waits_until_every_process_ends[zombie-is-gone]` |
| `add-left-line-always` | killed (2/2) | `a_timeout_reason_names_the_limit[gone]`, `a_child_past_its_limit_is_stopped_whole_and_reported` |
| `add-sigint-handler` | killed (2/2) | `a_runner_signal_exits_through_the_stop[term]`, `a_runner_signal_exits_through_the_stop[hup]` |
| `add-rewait-after-unblock` | killed (2/2) | `stop_run_freezes_then_kills_the_whole_run`, `stop_run_waits_for_every_process_it_found` |
| `wg-end-absolute` | killed (1/1) | `gone_waits_until_every_process_ends[clock-not-at-zero]` |
| `f4-no-catch` | killed (3/3) | `run_child_reports_a_stop_that_could_not_finish[ps-cannot-start]`, `run_child_reports_a_stop_that_could_not_finish[ps-fails-mid-walk]`, `a_stop_that_could_not_finish_is_reported_and_the_sweep_goes_on` |
| `f4-catch-base` | killed (1/1) | `run_child_reports_a_stop_that_could_not_finish[interrupt-during-stop]` |
| `f4-claims-stopped` | killed (2/2) | `a_timeout_reason_names_the_limit[unfinished]`, `a_stop_that_could_not_finish_is_reported_and_the_sweep_goes_on` |
| `f4-cause-dropped` | killed (2/2) | `a_timeout_reason_names_the_limit[unfinished]`, `a_stop_that_could_not_finish_is_reported_and_the_sweep_goes_on` |
| `ps-check-false` | killed (1/1) | `a_failed_ps_is_an_error_not_an_empty_table` |
| `ps-unsandboxed` | killed (1/1) | `a_failed_ps_is_an_error_not_an_empty_table` |
| `add-f4-error-swallowed` | killed (3/3) | `run_child_reports_a_stop_that_could_not_finish[ps-cannot-start]`, `run_child_reports_a_stop_that_could_not_finish[ps-fails-mid-walk]`, `a_stop_that_could_not_finish_is_reported_and_the_sweep_goes_on` |
| `add-f4-claims-stopped` | killed (2/2) | `a_timeout_reason_names_the_limit[unfinished]`, `a_stop_that_could_not_finish_is_reported_and_the_sweep_goes_on` |
| `add-f4-sweep-halts` | killed (3/3) | `run_child_reports_a_stop_that_could_not_finish[ps-cannot-start]`, `run_child_reports_a_stop_that_could_not_finish[ps-fails-mid-walk]`, `a_stop_that_could_not_finish_is_reported_and_the_sweep_goes_on` |
| `add-f4-left-claimed-empty` | killed (3/3) | `run_child_reports_a_stop_that_could_not_finish[ps-cannot-start]`, `run_child_reports_a_stop_that_could_not_finish[ps-fails-mid-walk]`, `a_stop_that_could_not_finish_is_reported_and_the_sweep_goes_on` |
| `launch-no-catch` | killed (2/2) | `a_child_that_cannot_start_is_reported_and_the_sweep_goes_on[process-limit]`, `a_child_that_cannot_start_is_reported_and_the_sweep_goes_on[subprocess-error]` |
| `launch-catch-oserror-only` | killed (1/1) | `a_child_that_cannot_start_is_reported_and_the_sweep_goes_on[subprocess-error]` |
| `launch-case-no-catch` | killed (2/2) | `a_child_that_cannot_start_is_reported_and_the_sweep_goes_on[process-limit]`, `a_child_that_cannot_start_is_reported_and_the_sweep_goes_on[subprocess-error]` |
| `launch-cause-dropped` | killed (2/2) | `a_child_that_cannot_start_is_reported_and_the_sweep_goes_on[process-limit]`, `a_child_that_cannot_start_is_reported_and_the_sweep_goes_on[subprocess-error]` |
| `add-launch-swallowed-as-killed` | killed (2/2) | `a_child_that_cannot_start_is_reported_and_the_sweep_goes_on[process-limit]`, `a_child_that_cannot_start_is_reported_and_the_sweep_goes_on[subprocess-error]` |
| `add-launch-sweep-halts` | killed (2/2) | `a_child_that_cannot_start_is_reported_and_the_sweep_goes_on[process-limit]`, `a_child_that_cannot_start_is_reported_and_the_sweep_goes_on[subprocess-error]` |
| `orphan-not-waited` | killed (1/1) | `a_child_past_its_limit_is_stopped_whole_and_reported` |

## Survivors, and the reviews' coverage observations

- `wg-strict-end` (`_wait_gone`'s `clock() >= end` → `clock() > end`): **equivalent.** The two differ
  only when a look lands on the deadline exactly; then the strict form looks once more, `GONE_POLL`
  later. That is a zero-width boundary of a real-time bound, not a decision any caller can observe:
  no row could tell the forms apart without fixing the clock to the deadline's exact float, which the
  monotonic clock never yields.
- Review cycle 1: `sr-wait-gone-wrapper-only` pinned by `stop_run_waits_for_every_process_it_found`;
  `rm-single-pass` by `run_members…[found-later-in-the-table]`; `rm-own-group-seeded` by the
  `runner-group` row handing in the runner's own group; `rm-pid1-included` (with
  `rm-pid0-and-1-included` and `rm-group-1-added`) by `[never-init-or-kernel]`;
  `wg-gone-not-filtered` and `wg-groups-not-pruned` by `gone_waits…[gone-numbers-never-followed]`.
- Review cycle 2: `wg-end-absolute` pinned by `gone_waits…[clock-not-at-zero]`; `ps-check-false`
  by `a_failed_ps_is_an_error_not_an_empty_table`. Its other coverage observations
  (`sr-wait-gone-groups-wrapper-only`, `sos-valueerror-propagates`, `main-extra-sigint-ignore`,
  `send-no-swallow-perm`) and the survivors it classed equivalent were not routed to this build.
