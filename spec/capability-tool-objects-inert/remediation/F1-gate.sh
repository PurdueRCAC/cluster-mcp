#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# Review cycle 1, F1 to F3: every refusal the tool rules can make is held by the suite, and R4's
# generic rule passes a field's own declared default unwarned.
#
#   sh spec/capability-tool-objects-inert/remediation/F1-gate.sh [pins|control|sweep-handshake-K|sweep-modern-K|report
#                                                               |sweep-return-type-ERA|report-return-type]
#
# `pins` (about 1 min): the pins this remediation adds, by name, in both eras (verify/lib.sh's
# pytest_both: a missing id, an empty parameter set or a skip fails). `control` (about 80 s): the
# sweep's unmutated rewrite passes its targets in both eras. `sweep-<era>-<K>`, K 1 to 4: shard K of 4
# of F1-tool-rule-sweep.py's mutants in that era, two children at a time, its log under
# .local/f1-sweep/ (gitignored), started afresh. Measured 2026-11-12 on a shared host: 9 to 12 min a
# shard, 85 min for all eight, so each runs through the harness's background runner, never as one
# capped call (the budget is the maintainer's call; see the remediation report). `report`: every
# mutant ran in both eras, each killed or recorded equivalent (reads the eight logs). Footprint: at
# most two mutant children at a time, under 1 GB; nothing in the background.
#
# Review cycle 2, N1 changed one function of the package, `_return_type_violation`, after the eight
# shards ran on 4b04dad. `sweep-return-type-<era>` (handshake or modern) re-runs that function's
# mutants alone in the era, as the shards run theirs, its log under .local/f1-sweep/, started afresh
# (116 mutants, about 13 min an era on a shared host, 2026-11-12).
# `report-return-type`: the report over those two logs for that function and the eight 4b04dad shard
# logs for every other mutant; it refuses when any mutant outside the function is gone, new, or plants
# other text than it did at 4b04dad, so an old verdict stands only for an unchanged mutant.
set -eu
. "$(dirname "$0")/../verify/lib.sh"
R=spec/capability-tool-objects-inert/remediation
LOGS=.local/f1-sweep
MODE=${1:-}
case $MODE in
  pins)
    uv sync --locked -q
    pytest_both 'tests/test_capabilities.py::test_a_capability_that_cannot_load_is_refused_naming_it
tests/test_capabilities.py::test_a_tool_state_a_newer_model_refuses_is_refused_naming_it
tests/test_capabilities.py::test_a_tool_state_a_newer_model_accepts_loads
tests/test_capabilities.py::test_the_default_rule_compares_node_for_node
tests/test_capabilities.py::test_a_default_made_from_the_other_fields_is_never_made
tests/test_capabilities.py::test_a_field_no_rule_names_is_checked_by_the_generic_rule
tests/test_capabilities.py::test_a_field_no_rule_names_passes_its_own_declared_default_unwarned
tests/test_capabilities.py::test_an_inert_tool_of_every_accepted_shape_loads
tests/test_capabilities.py::test_a_return_type_that_holds_itself_loads_and_the_load_returns
tests/test_surface.py::test_served_surface_matches_baseline
tests/test_mutations.py::test_mutation_anchor_applies'
    echo 'F1-gate.sh: pins ok' >&2 ;;
  control)
    $PY $R/F1-tool-rule-sweep.py control handshake
    $PY $R/F1-tool-rule-sweep.py control modern ;;
  sweep-handshake-[1-4]|sweep-modern-[1-4])
    era=${MODE#sweep-}; k=${era##*-}; era=${era%-*}
    $PY $R/F1-tool-rule-sweep.py run "$era" "$k/4" "$LOGS/$era-$k.log" ;;
  sweep-return-type-handshake|sweep-return-type-modern)
    era=${MODE#sweep-return-type-}
    $PY $R/F1-tool-rule-sweep.py function "$era" _return_type_violation "$LOGS/return-type-$era.log" ;;
  report-return-type)
    $PY $R/F1-tool-rule-sweep.py merged 4b04dad _return_type_violation \
      "$LOGS"/return-type-handshake.log "$LOGS"/return-type-modern.log -- \
      "$LOGS"/handshake-1.log "$LOGS"/handshake-2.log "$LOGS"/handshake-3.log "$LOGS"/handshake-4.log \
      "$LOGS"/modern-1.log "$LOGS"/modern-2.log "$LOGS"/modern-3.log "$LOGS"/modern-4.log ;;
  report)
    $PY $R/F1-tool-rule-sweep.py report "$LOGS"/handshake-1.log "$LOGS"/handshake-2.log "$LOGS"/handshake-3.log \
      "$LOGS"/handshake-4.log "$LOGS"/modern-1.log "$LOGS"/modern-2.log "$LOGS"/modern-3.log "$LOGS"/modern-4.log ;;
  *) echo "F1-gate.sh: unknown mode '$MODE' (pins|control|sweep-handshake-K|sweep-modern-K|report|sweep-return-type-ERA|report-return-type)" >&2; exit 2 ;;
esac
