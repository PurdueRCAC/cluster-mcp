#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P2's gate: a server built from the loaded capabilities, and its listing, run none of a capability's
# code, and a call runs only its handler; then the whole cycle's checks on the finished tree, the
# deferral ledger, and the profile's full verify.
#
#   sh spec/capability-tool-objects-inert/verify/p2.sh [phase|ledger|full-legacy-K|full-modern-K|full-ends|all]   (K = 1, 2, 3, 4)
#
# `phase` (about 2 min warm): the served-surface fixture as develop held it (index against BASE_REF); docs_gate.py; rows.py; alternatives.py coverage all; P2's named test and
# P1's in both eras. `ledger` (seconds): ledger.py. `full-<era>-K`: command K of that era's four suite
# commands (AGENTS.md § Factory `verify`; CI's slowest is 7:34, under the 10-minute command cap);
# `full-ends`: `uv lock --check` and the sandboxed `cluster-mcp --help`. The full modes are the
# heavy runs: run one at a time. `all` runs every mode. Footprint: one process tree at a time, nothing
# in the background, under 1 GB.
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" phase ledger full-legacy-1 full-legacy-2 full-legacy-3 full-legacy-4 \
  full-modern-1 full-modern-2 full-modern-3 full-modern-4 full-ends all

if [ "$MODE" = phase ] || [ "$MODE" = all ]; then
  uv sync --locked -q
  git diff --cached --quiet $BASE_REF -- tests/fixtures/served_surface.json || fail 'the served-surface fixture differs from develop at the cycle start'
  $PY $V/docs_gate.py
  $PY $V/rows.py
  $PY $V/alternatives.py coverage all
  pytest_both 'tests/test_capabilities.py::test_a_served_capability_runs_none_of_its_code_but_its_handler
tests/test_capabilities.py::test_a_capability_that_cannot_load_is_refused_naming_it
tests/test_capabilities.py::test_every_function_tool_field_has_a_rule
tests/test_capabilities.py::test_a_field_no_rule_names_is_checked_by_the_generic_rule
tests/test_capabilities.py::test_an_inert_tool_of_every_accepted_shape_loads
tests/test_surface.py::test_served_surface_matches_baseline'
  echo 'p2.sh: phase ok' >&2
fi
case $MODE in ledger|all) $PY $V/ledger.py ;; esac
for era in legacy modern; do
  for k in 1 2 3 4; do
    case $MODE in "full-$era-$k"|all) full_part "$era" "$k" ;; esac
  done
done
case $MODE in full-ends|all) full_ends ;; esac
