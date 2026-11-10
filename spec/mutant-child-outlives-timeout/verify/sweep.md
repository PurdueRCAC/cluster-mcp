# Mutant sweep of the stop — record (review cycle 1 remediation)

Run 2026-11-09 by the remediation build, on the final `tests/mutants.py` and `tests/test_mutations.py`
of that build, with [`sweep.py`](sweep.py): each mutant planted into a working copy of its file, only
the rows it names run, the file restored from a backup after each mutant and byte-compared at the
end. 51 mutants in 205 s on a development host: 50 killed (every named row red), 1 survived, recorded
below as equivalent.

The list holds PLAN § 6's decision list (the first 33, as P1's build ran them), review cycle 1's
surviving mutants (rows pinned by the remediation, `sr-*`, `rm-*`, `wg-*`), and additive mutants
(`add-*`: code added, nothing removed).

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
| `orphan-not-waited` | killed (1/1) | `a_child_past_its_limit_is_stopped_whole_and_reported` |

## Survivors and review cycle 1's coverage observations

- `wg-strict-end` (`_wait_gone`'s `clock() >= end` → `clock() > end`): **equivalent.** The two differ
  only when a look lands on the deadline exactly; then the strict form looks once more, `GONE_POLL`
  later. That is a zero-width boundary of a real-time bound, not a decision any caller can observe:
  no row could tell the forms apart without fixing the clock to the deadline's exact float, which the
  monotonic clock never yields.
- `sr-wait-gone-wrapper-only` (review P1): pinned by `stop_run_waits_for_every_process_it_found`.
- `rm-single-pass`: pinned by `run_members_follow_parents_and_groups[found-later-in-the-table]`.
- `rm-own-group-seeded`: pinned by `run_members_follow_parents_and_groups[runner-group]`, which now
  hands the runner's own group in as known.
- `rm-pid1-included` (the review's equivalent): pinned anyway by
  `run_members_follow_parents_and_groups[never-init-or-kernel]`, with `rm-pid0-and-1-included` and
  `rm-group-1-added` beside it, since a 0 or 1 in the run would send a signal to `kill(0)`,
  `killpg(0)` or init.
- `wg-gone-not-filtered`, `wg-groups-not-pruned`: pinned by
  `gone_waits_until_every_process_ends[gone-numbers-never-followed]`.
