#!/bin/sh
# Review cycle 1, class 4: the four lines no row pinned. Run from the worktree root.
#
# `_leave`'s done-check, `_publish`'s live-connection branch (reachable: `open()` publishes while
# an attempt runs), the bound's floor, and each of `write`'s own commands sharing its deadline:
# each has a row, named here in both eras, and a mutant that turns it red.
set -eu
T=tests/test_ssh_exec.py
IDS="$T::test_a_call_at_its_deadline_takes_an_outcome_that_has_come
$T::test_a_reconnect_keeps_a_connection_published_meanwhile
$T::test_a_reconnect_bound_never_falls_below_the_default
$T::test_a_write_spends_one_reconnect_window"
uv run pytest -q $IDS
CLUSTER_MCP_TEST_ERA=modern uv run pytest -q $IDS
uv run python tests/mutants.py ssh-reconnect-leave-ignores-outcome ssh-reconnect-publish-replaces-live \
    ssh-reconnect-bound-unfloored ssh-write-parent-own-deadline ssh-write-place-own-deadline \
    ssh-write-probe-own-deadline
echo "F4-unpinned-lines: green" >&2
