#!/bin/sh
# Review cycle 1, class 2: an abort never closes a published connection. Run from the worktree root.
#
# The abort re-checks the attempt under the lock as it acts, and an aborted attempt is never
# published: both crossings are forced by a hook at the seam, with no timing race. Named ids in
# both eras, then the mutants that drop the re-check and that publish an aborted attempt.
set -eu
IDS="tests/test_ssh_exec.py::test_an_abort_and_a_publish_never_cross
tests/test_ssh_exec.py::test_a_reconnect_attempt_that_hangs_is_abandoned_at_the_bound
tests/test_ssh_exec.py::test_concurrent_calls_during_a_stall_start_one_attempt"
uv run pytest -q $IDS
CLUSTER_MCP_TEST_ERA=modern uv run pytest -q $IDS
uv run python tests/mutants.py ssh-reconnect-abort-unchecked ssh-reconnect-publishes-aborted \
    ssh-reconnect-late-success-leaks
echo "F2-abort-recheck: green" >&2
