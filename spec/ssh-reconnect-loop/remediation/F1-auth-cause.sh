#!/bin/sh
# Review cycle 1, class 1: only a refusal ends the reconnect at once. Run from the worktree root.
#
# An authentication is read by its cause: the server rejecting the credentials gives up at once; a
# link closed during authentication, an auth timeout and an abort are not refusals, are named for
# what they are, and are retried within the bound; a call never takes on the failure of an attempt
# aborted at another call's deadline. Named ids in both eras (the cut-short and abort rows against
# the loopback server), then the class's mutants: the classification collapsed back to the
# exception class, a joiner inheriting the abort, and the refusal retried.
set -eu
T=tests/test_ssh_exec.py
IDS="tests/test_startup.py::test_connect_failure_names_host_and_cause
$T::test_a_reconnect_that_cannot_succeed_fails_within_the_bound
$T::test_a_reconnect_refused_authentication_fails_at_once
$T::test_an_authentication_cut_short_is_retried
$T::test_a_call_never_inherits_an_aborted_attempt
$T::test_reconnect_texts_state_the_bound"
uv run pytest -q $IDS
CLUSTER_MCP_TEST_ERA=modern uv run pytest -q $IDS
uv run python tests/mutants.py ssh-reconnect-auth-class-not-cause ssh-reconnect-joiner-inherits-abort \
    ssh-reconnect-retries-refused-auth
echo "F1-auth-cause: green" >&2
