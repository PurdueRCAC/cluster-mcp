#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P1's gate: the load decides every registered tool object inert (exactly a FunctionTool, every field
# of the installed model holding what its rule accepts, a field no rule names checked by the generic
# rule), refusing it naming the distribution, and AGENTS.md §7 says so in the same commit.
#
#   sh spec/capability-tool-objects-inert/verify/p1.sh [phase|cli-legacy|cli-modern|replanted-legacy|replanted-modern|mutants-legacy-K|mutants-modern-K|all]   (K = 1, 2, 3, 4)
#
# `phase` (about 2 min warm): the served-surface fixture as develop held it (index against BASE_REF); docs_gate.py; rows.py; alternatives.py coverage p1; then P1's named
# tests in both eras. `cli-<era>`: every tool-object kind of the refusal (and the re-carried
# `served-tool` timing) driven through the CLI over each drive, `CLUSTER_MCP_TEST_EVERY_KIND=1`
# (about 73 kinds x 3 drives at about 1.1 s a row, measured at the plan: about 4 min an era). `replanted-<era>`: every loader case this change
# re-plants (replanted.py), killed in that era (counted at build; at about 3 s a case, a count over
# 180 is split before it nears the 10-minute command cap).
# `mutants-<era>-K`: shard K of 4 of every P1 alternative's case, killed in that era (358
# alternatives on the plan's prototype at about 3 s a case: about 4.5 min a shard). `all` runs every
# mode. Footprint: one process tree at a time, nothing in the background, under 1 GB.
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" phase cli-legacy cli-modern replanted-legacy replanted-modern \
  mutants-legacy-1 mutants-legacy-2 mutants-legacy-3 mutants-legacy-4 \
  mutants-modern-1 mutants-modern-2 mutants-modern-3 mutants-modern-4 all

if [ "$MODE" = phase ] || [ "$MODE" = all ]; then
  uv sync --locked -q
  git diff --cached --quiet $BASE_REF -- tests/fixtures/served_surface.json || fail 'the served-surface fixture differs from develop at the cycle start'
  $PY $V/docs_gate.py
  $PY $V/rows.py
  $PY $V/alternatives.py coverage p1
  pytest_both 'tests/test_capabilities.py::test_a_capability_that_cannot_load_is_refused_naming_it
tests/test_capabilities.py::test_a_keyboard_interrupt_while_loading_still_interrupts
tests/test_capabilities.py::test_what_a_server_would_refuse_is_refused_at_load
tests/test_capabilities.py::test_every_function_tool_field_has_a_rule
tests/test_capabilities.py::test_a_field_no_rule_names_is_checked_by_the_generic_rule
tests/test_capabilities.py::test_an_inert_tool_of_every_accepted_shape_loads
tests/test_capabilities.py::test_a_tool_registered_before_the_load_is_decided_too
tests/test_capabilities.py::test_the_locked_model_holds_no_private_attribute_and_forbids_extras
tests/test_capabilities.py::test_a_capability_whose_entry_point_imports_its_tools_loads
tests/test_capabilities.py::test_a_capability_whose_tools_are_already_imported_keeps_them
tests/test_startup.py::test_a_capability_that_cannot_load_stops_startup
tests/test_startup.py::test_the_cli_drives_name_kinds_that_exist
tests/test_surface.py::test_served_surface_matches_baseline
tests/test_registry.py::test_registry_matches_expected_tools
tests/test_registry.py::test_served_tools_match_registry
tests/test_instructions.py::test_instructions_match_registry
tests/test_instructions.py::test_every_tool_belongs_to_a_member
tests/test_instructions.py::test_base_is_core_slurm_then_overlay
tests/test_mutations.py::test_mutation_anchor_applies
tests/test_hygiene.py::test_no_spec_ids_in_the_package_or_the_suite'
  echo 'p1.sh: phase ok' >&2
fi
cli() {
  CLUSTER_MCP_TEST_EVERY_KIND=1 ran_pytest "$1" tests/test_startup.py::test_a_capability_that_cannot_load_stops_startup \
    -k 'tool-subclass or tool-exact or tool-default or tool-state or tool-changed or served-tool'
}
replanted() {
  ids=$($PY $V/replanted.py)
  # shellcheck disable=SC2086
  env -u CLUSTER_MCP_SKIP_PROBES CLUSTER_MCP_TEST_ERA=$1 uv run python tests/mutants.py --self-check $ids
}
case $MODE in cli-legacy|all) cli legacy ;; esac
case $MODE in cli-modern|all) cli modern ;; esac
case $MODE in replanted-legacy|all) replanted legacy ;; esac
case $MODE in replanted-modern|all) replanted modern ;; esac
case $MODE in mutants-legacy-1|all) $PY $V/alternatives.py cases p1 handshake 1/4 ;; esac
case $MODE in mutants-legacy-2|all) $PY $V/alternatives.py cases p1 handshake 2/4 ;; esac
case $MODE in mutants-legacy-3|all) $PY $V/alternatives.py cases p1 handshake 3/4 ;; esac
case $MODE in mutants-legacy-4|all) $PY $V/alternatives.py cases p1 handshake 4/4 ;; esac
case $MODE in mutants-modern-1|all) $PY $V/alternatives.py cases p1 modern 1/4 ;; esac
case $MODE in mutants-modern-2|all) $PY $V/alternatives.py cases p1 modern 2/4 ;; esac
case $MODE in mutants-modern-3|all) $PY $V/alternatives.py cases p1 modern 3/4 ;; esac
case $MODE in mutants-modern-4|all) $PY $V/alternatives.py cases p1 modern 4/4 ;; esac
