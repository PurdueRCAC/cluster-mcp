#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P3's gate: cluster:// resources, each rcac:// alias derived from its target, in every mode.
#
#   sh spec/rename-to-cluster-mcp/verify/p3.sh [phase|mutants|full|full-legacy|full-modern|all]
#
# `phase` (about 5 min): the URI and docs checks; the fixture's resource delta (fixture_deltas.py
# check p3); the served resources are 0.1.4's plus a cluster:// twin of each, the tools unchanged
# (baseline.sh p3); this phase's tests in both eras, the read-hook neighbourhood included. `mutants`
# runs every case planting into resources.py, middleware.py or context.py, plus the alias cases and
# the scheme twins. `full` as in p1.sh. `all` (the default) runs phase, mutants, full. Footprint: one
# process tree at a time, nothing in the background, under 1 GB.
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" phase mutants full full-legacy full-modern all

if [ "$MODE" = phase ] || [ "$MODE" = all ]; then
  uv run --no-project --with pyyaml python $V/checks.py source imports env uris-p3 container profile ci docs-p1 docs-p2 docs-p3
  uv run python $V/members.py
  uv run python $V/fixture_deltas.py check p3
  sh $V/baseline.sh p3
  pytest_both "tests/test_storage_resource.py::test_aliases_are_derived_from_their_targets
tests/test_storage_resource.py::test_open_resources_are_the_context_uris
tests/test_storage_resource.py::test_alias_read_returns_target_content
tests/test_storage_resource.py::test_near_open_read_is_refused
tests/test_storage_resource.py
tests/test_context.py::test_any_client_reads_the_context_in_delegate_mode
tests/test_context.py
tests/test_no_executor.py
tests/test_identity.py
tests/test_isolation.py
tests/test_protocol.py
tests/test_surface.py
tests/test_mutations.py"
  echo 'p3.sh: phase ok' >&2
fi
if [ "$MODE" = mutants ] || [ "$MODE" = all ]; then
  # shellcheck disable=SC2046
  run_mutants $(cases_for 'core/resources.py core/middleware.py core/context.py' \
    alias-flag-hand-set-open alias-flag-hand-set-closed open-set-before-aliases open-set-target-scheme-only \
    alias-handler-differs alias-missing read-hook-cluster-scheme-only read-hook-rcac-scheme-only \
    read-hook-open-by-equality)
fi
case $MODE in full|full-legacy|all) full_legacy ;; esac
case $MODE in full|full-modern|all) full_modern ;; esac
