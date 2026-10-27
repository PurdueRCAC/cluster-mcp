#!/bin/sh
# Review cycle 2, class 4: the two rules that survived mutation. Run from the worktree root.
#
# The abort spares an attempt another call has joined since its last waiter decided to abort (a
# hook at the seam: the joining call comes in before the abort acts), and a failed attempt releases
# its connection (the loopback server holding an authentication past the client's auth timeout).
# Named ids in both eras, then a mutant for each.
set -eu
T=tests/test_ssh_exec.py
IDS="$T::test_an_abort_spares_an_attempt_another_call_joined_since
$T::test_a_failed_attempt_releases_its_connection"
uv run pytest -q $IDS
CLUSTER_MCP_TEST_ERA=modern uv run pytest -q $IDS
uv run python tests/mutants.py ssh-reconnect-abort-spares-no-joiner ssh-reconnect-failed-attempt-unreleased
echo "F8-surviving-rules: green" >&2
