#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P2's gate: the storage resource and its alias belong to the RCAC member, and no core module names
# a member any more.
#
#   sh spec/capability-extras/verify/p2.sh [phase|mutants|full|full-legacy|full-modern|all]
#
# `phase` (about 4 min): `uv sync --locked`; imports.py p2 (no core module names a member, anywhere);
# compose.py p2 (the storage URIs served exactly with the RCAC capability, the alias a copy of its
# target, the core's open set the two context URIs); docs.py p2; planted.sh extra; baseline.sh;
# then this phase's tests in both eras. `mutants` runs every case planting into the resource
# modules, plus the new `storage-resource-unconditional`. `full` is the profile's verify. `all` (the
# default) runs phase, mutants, full. Footprint: one process tree at a time, under 1 GB.
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" phase mutants full full-legacy full-modern all

if [ "$MODE" = phase ] || [ "$MODE" = all ]; then
  uv sync --locked -q
  uv run --no-project python $V/imports.py p2
  uv run python $V/compose.py p2
  uv run --no-project python $V/docs.py p2
  sh $V/planted.sh extra
  sh $V/baseline.sh
  pytest_both "tests/test_capabilities.py::test_storage_is_served_only_with_the_rcac_capability
tests/test_capabilities.py::test_a_capability_resource_must_need_an_executor
tests/test_capabilities.py::test_a_duplicate_resource_uri_is_refused
tests/test_capabilities.py::test_a_capability_resource_is_validated
tests/test_capabilities.py::test_aliases_follow_every_primary_uri
tests/test_capabilities.py::test_core_imports_no_member
tests/test_capabilities.py
tests/test_storage_resource.py
tests/test_surface.py::test_served_surface_matches_baseline
tests/test_no_executor.py
tests/test_isolation.py
tests/test_identity.py
tests/test_hygiene.py
tests/test_mutations.py"
  echo 'p2.sh: phase ok' >&2
fi
if [ "$MODE" = mutants ] || [ "$MODE" = all ]; then
  # shellcheck disable=SC2046
  run_mutants $(cases_for 'core/resources.py core/capabilities.py rcac/capability.py rcac/resources.py rcac/tools.py' \
    storage-resource-unconditional capability-resource-open-allowed)
fi
case $MODE in full|full-legacy|all) full_legacy ;; esac
case $MODE in full|full-modern|all) full_modern ;; esac
