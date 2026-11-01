#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P1's gate: the Slurm and RCAC tools and instructions register through the entry-point group, and
# the core composes what it serves from the capabilities that loaded.
#
#   sh spec/capability-extras/verify/p1.sh [phase|mutants|full|full-legacy|full-modern|all]
#
# `phase` (about 4 min): `uv sync --locked` (an editable member's entry points are written only by a
# sync, and a stale environment would serve the core alone); pyprojects.py p1 (the entry points
# declared); imports.py p1 (no core module names a member, but resources.py until P2); compose.py p1
# (every capability set and order, in process: the tools, the base and the cross-check); docs.py p1;
# planted.sh extra (a distribution the core has never heard of plugs in, ordered by its key);
# baseline.sh (every capability installed: the surface equals BASE_REF's, the fixture untouched);
# then this phase's tests in both eras. `mutants` runs every case planting into the files this phase
# rewrites, plus the six new ones. `full` is the profile's verify. `all` (the default) runs phase,
# mutants, full. Footprint: one process tree at a time, nothing in the background, under 1 GB.
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" phase mutants full full-legacy full-modern all

if [ "$MODE" = phase ] || [ "$MODE" = all ]; then
  uv sync --locked -q
  uv run --no-project python $V/pyprojects.py p1
  uv run --no-project python $V/imports.py p1
  uv run python $V/compose.py p1
  uv run --no-project python $V/docs.py p1
  sh $V/planted.sh extra
  sh $V/baseline.sh
  pytest_both "tests/test_capabilities.py::test_installed_finds_every_workspace_member
tests/test_capabilities.py::test_composition_order_ignores_discovery_order
tests/test_capabilities.py::test_served_tools_are_the_core_and_the_given_capabilities
tests/test_capabilities.py::test_instructions_name_exactly_the_served_tools
tests/test_capabilities.py::test_a_load_failure_names_the_distribution
tests/test_capabilities.py::test_a_failed_load_leaves_the_registry_as_it_was
tests/test_capabilities.py::test_a_duplicate_tool_is_refused
tests/test_capabilities.py::test_a_tools_module_failure_names_the_distribution
tests/test_capabilities.py::test_instructions_must_list_exactly_the_tools
tests/test_capabilities.py::test_core_text_lists_exactly_the_core_tools
tests/test_capabilities.py::test_a_planted_capability_needs_no_core_edit
tests/test_capabilities.py
tests/test_surface.py::test_served_surface_matches_baseline
tests/test_surface.py
tests/test_instructions.py
tests/test_registry.py::test_registry_matches_expected_tools
tests/test_registry.py::test_served_tools_match_registry
tests/test_protocol.py
tests/test_transports.py
tests/test_site.py
tests/test_site_startup.py
tests/test_context.py
tests/test_tools.py
tests/test_sbatch.py
tests/test_hygiene.py
tests/test_mutations.py"
  echo 'p1.sh: phase ok' >&2
fi
if [ "$MODE" = mutants ] || [ "$MODE" = all ]; then
  # shellcheck disable=SC2046
  run_mutants $(cases_for 'core/server.py core/tools/__init__.py core/capabilities.py core/instructions.py slurm/instructions.py rcac/instructions.py slurm/capability.py rcac/capability.py' \
    capability-order-from-discovery capability-tools-unfiltered core-imports-member-by-name capability-duplicate-tool-allowed \
    capability-tools-import-swallowed capability-instructions-unchecked)
fi
case $MODE in full|full-legacy|all) full_legacy ;; esac
case $MODE in full|full-modern|all) full_modern ;; esac
