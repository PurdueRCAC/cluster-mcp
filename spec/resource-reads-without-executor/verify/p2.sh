#!/bin/sh
# P2's gate: delegate-mode reads, refusals, isolation and the open context resource.
# Usage: p2.sh [tests|mutants|all]. `tests` runs the new tests with the modules that share the
# middleware with them, in the legacy era, then again in the modern era; `mutants` runs every
# middleware.py and context.py case plus this phase's new ones; `all` (the default) runs both in
# that order. Footprint: one process tree at a time (one pytest, or the mutation runner and its one
# sequential child), under 1 GB; about 3 min on mac-m2. Run from the worktree root.
set -eu
MODE=${1:-all}
case $MODE in tests|mutants|all) ;; *) echo "p2.sh: unknown mode $MODE" >&2; exit 2 ;; esac

S=tests/test_storage_resource.py
TESTS="$S::test_storage_read_runs_as_the_mapped_user
$S::test_concurrent_storage_reads_stay_isolated
$S::test_sequential_storage_reads_each_get_their_executor
$S::test_storage_check_catches_crossing
$S::test_storage_read_refused
$S::test_storage_read_without_token_after_an_authenticated_read_fails
$S::test_storage_read_without_token_while_an_authenticated_read_is_in_flight
$S::test_unknown_uri_is_not_found
$S
tests/test_context.py::test_any_client_reads_the_context_in_delegate_mode
tests/test_context.py
tests/test_identity.py
tests/test_isolation.py
tests/test_no_executor.py
tests/test_protocol.py
tests/test_surface.py::test_served_surface_matches_baseline
tests/test_mutations.py
tests/test_hygiene.py"

if [ "$MODE" != mutants ]; then
  set -f
  IFS='
'
  uv run pytest -q $TESTS
  CLUSTER_MCP_TEST_ERA=modern uv run pytest -q $TESTS
  unset IFS
  set +f
fi

if [ "$MODE" != tests ]; then
  # Every case that plants into middleware.py or context.py, read from the runner itself so a
  # re-planted or added case cannot be left out, then the cases this phase adds by name, deduped.
  # A named case the runner does not know is passed through, and the runner reports it FAILED.
  CASES=$(uv run python -c "
import sys
sys.path.insert(0, 'tests')
import mutants
ids = [c.id for c in mutants.CASES if c.file in ('middleware.py', 'context.py')]
if not ids:
    sys.exit('p2.sh: no middleware or context cases found')
print(*dict.fromkeys(ids + sys.argv[1:]))
" resource-calls-decorated-tool auth-read-sets-no-executor storage-read-left-open \
    context-read-closed read-boundary-dropped read-boundary-wraps-not-found \
    read-no-token-reuses-last-executor)
  # shellcheck disable=SC2086
  uv run python tests/mutants.py $CASES
fi
