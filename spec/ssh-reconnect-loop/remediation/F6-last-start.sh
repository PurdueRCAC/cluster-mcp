#!/bin/sh
# Review cycle 2, class 2: no connect attempt starts after the stated last start. Run from the
# worktree root.
#
# A call starts or joins no attempt later than `FINAL_ATTEMPT_LEAD` before its deadline, first
# attempts and a write's later commands included; one that reaches its last start with the
# connection lost gives up at once with `timed out` or the last cause it saw. The old claim (only
# "its last attempt starting at least 2 s before that") is absent from every live text, and the
# pinned bound statement says what the code does. Named ids in both eras, then the class's
# mutants: the last-start check dropped, a joiner inheriting an abort (re-planted on the check's
# new home), and the retry unbounded.
set -eu
if git grep -n -i 'last attempt starting at least' -- src AGENTS.md README.md SECURITY.md INSTRUCTIONS.md; then
    echo "F6-last-start: a live text still states only the last attempt's start" >&2
    exit 1
fi
T=tests/test_ssh_exec.py
IDS="$T::test_a_call_past_its_last_start_starts_no_attempt
$T::test_a_write_command_past_its_last_start_starts_no_attempt
$T::test_a_reconnect_that_cannot_succeed_fails_within_the_bound
$T::test_a_call_never_inherits_an_aborted_attempt
$T::test_a_write_spends_one_reconnect_window
$T::test_reconnect_texts_state_the_bound"
uv run pytest -q $IDS
CLUSTER_MCP_TEST_ERA=modern uv run pytest -q $IDS
uv run python tests/mutants.py ssh-reconnect-starts-past-last-start ssh-reconnect-joiner-inherits-abort \
    ssh-reconnect-unbounded-retry
echo "F6-last-start: green" >&2
