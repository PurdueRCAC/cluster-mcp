#!/bin/sh
# P3's gate: the invariants and docs describe the fixed behaviour, then the profile's full verify.
# Usage: p3.sh [docs|full|full-legacy|full-modern|all]. `docs` is the phase-only part (seconds);
# `full` runs only the profile's verify; `full-legacy` is its lock check and legacy-era suite,
# `full-modern` its modern-era suite and sandboxed --help, the two halves for a caller with a 10 min
# command cap; `all` (the default) runs docs then full. Footprint: one process tree at a time; the
# full verify is about 8 min on mac-m2, under 1 GB. Run from the worktree root.
set -eu
MODE=${1:-all}
case $MODE in docs|full|full-legacy|full-modern|all) ;; *) echo "p3.sh: unknown mode $MODE" >&2; exit 2 ;; esac

fail() { echo "p3.sh: $*" >&2; exit 1; }

# The text of one numbered Invariants subsection: from its heading to the next heading.
section() {
  awk -v n="### $1. " 'index($0, n) == 1 { on = 1; print; next } on && /^###? / { exit } on' AGENTS.md
}

if [ "$MODE" = docs ] || [ "$MODE" = all ]; then
  S1=$(section 1); S7=$(section 7); S8=$(section 8)
  [ -n "$S1" ] && [ -n "$S7" ] && [ -n "$S8" ] || fail 'cannot find Invariants sections 1, 7 and 8'

  # Section 1 says reads set the executor in on_read_resource and the boundary bounds them.
  printf '%s\n' "$S1" | grep -q 'on_read_resource' || fail 'section 1 does not name on_read_resource'
  printf '%s\n' "$S1" | grep -q 'ResourceError' || fail 'section 1 does not say how the boundary bounds a read'
  printf '%s\n' "$S1" | grep -q 'is called per tool call, from middleware `on_call_tool`' \
    && fail 'section 1 still says the executor is set per tool call only'
  # Section 7 no longer records the resource's TypeError as current.
  printf '%s\n' "$S7" | grep -q 'currently gets this wrong' && fail 'section 7 still records the resources.py defect'
  printf '%s\n' "$S7" | grep -q 'resolve_storage_paths' || fail 'section 7 does not name the undecorated helper'
  printf '%s\n' "$S7" | grep -q 'storage-paths-resource-typeerror' && fail 'section 7 still points at the absorbed seed'
  printf '%s\n' "$S7" | grep -q 'raises `TypeError' && fail 'section 7 still says the resource raises TypeError'
  # Section 8 no longer records rcac://storage as a known defect, and says how reads are served.
  printf '%s\n' "$S8" | grep -q 'issues/resource-reads-without-executor' && fail 'section 8 still points at the defect seed'
  printf '%s\n' "$S8" | grep -q 'rcac://storage` is unchanged' && fail 'section 8 still records rcac://storage as unchanged'
  printf '%s\n' "$S8" | grep -q 'OPEN_RESOURCES' || fail 'section 8 does not name OPEN_RESOURCES'
  # The places that restate section 1 follow it.
  awk '/^### Request Isolation in Delegate Mode/ { on = 1; next } on && /^##/ { exit } on' SECURITY.md \
    | grep -q 'on_read_resource' || fail 'SECURITY.md request isolation does not mention reads'
  grep -q 'middleware.on_call_tool ──▶' AGENTS.md && fail 'the architecture diagram still shows tool calls only'
  grep -n 'both set the per-request executor in `on_call_tool`' AGENTS.md && fail 'the repository map still says on_call_tool only'
  grep -q 'test_storage_resource.py' AGENTS.md || fail 'Testing has no entry for test_storage_resource.py'
  # No spec ids leaked into the package or the suite.
  uv run pytest -q tests/test_hygiene.py::test_no_spec_ids_in_the_package_or_the_suite
  echo 'p3.sh: docs ok'
fi

case $MODE in full|full-legacy|all)
  uv lock --check
  uv run pytest -q ;;
esac
case $MODE in full|full-modern|all)
  CLUSTER_MCP_TEST_ERA=modern uv run pytest -q
  bin/sandbox.sh uv run rcac-mcp --help >/dev/null ;;
esac
