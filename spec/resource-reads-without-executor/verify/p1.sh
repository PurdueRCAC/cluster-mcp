#!/bin/sh
# P1's gate: the shared-mode read of rcac://storage.
# Usage: p1.sh [tests|mutants|all]. `tests` runs the named tests in the legacy era, then again in
# the modern era; `mutants` runs only the mutation cases this phase plants or re-plants; `all` (the
# default) runs both in that order. Footprint: one process tree at a time (one pytest, or the
# mutation runner and its one sequential child), under 1 GB; about 1 min on mac-m2.
# Run from the worktree root.
set -eu
MODE=${1:-all}
case $MODE in tests|mutants|all) ;; *) echo "p1.sh: unknown mode $MODE" >&2; exit 2 ;; esac

S=tests/test_storage_resource.py
TESTS="$S::test_storage_read_runs_on_the_shared_executor
$S::test_storage_read_runs_the_local_executor
$S::test_storage_read_without_executor_middleware_fails
tests/test_surface.py::test_served_surface_matches_baseline
tests/test_tools.py::test_tool_reaches_only_the_installed_executor[storage_paths]
tests/test_tools.py::test_slurm_and_site_argvs[storage-paths]
tests/test_mutations.py
tests/test_hygiene.py::test_no_spec_ids_in_the_package_or_the_suite
tests/test_hygiene.py::test_only_the_harness_imports_the_stack"

if [ "$MODE" != mutants ]; then
  # Word splitting on newlines only; globbing off so the bracketed ids pass through literally.
  set -f
  IFS='
'
  uv run pytest -q $TESTS
  CLUSTER_MCP_TEST_ERA=modern uv run pytest -q $TESTS
  unset IFS
  set +f
fi

if [ "$MODE" != tests ]; then
  uv run python tests/mutants.py \
    resource-calls-decorated-tool \
    shared-read-sets-no-executor \
    shared-middleware-sets-first-call-only \
    shared-middleware-sets-at-construction
fi
