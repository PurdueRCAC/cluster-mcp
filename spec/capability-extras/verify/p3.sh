#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P3's gate: a capability that fails to load stops the server at startup, naming its distribution.
#
#   sh spec/capability-extras/verify/p3.sh [phase|mutants|full|full-legacy|full-modern|all]
#
# `phase` (about 3 min): `uv sync --locked`; planted.sh broken (eleven planted failures, each driven
# through cluster-mcp and rcac-mcp: exit 5, the message naming the distribution on stderr and as the
# stdio answer, no mode ladder before it, --help unaffected; one over http, exiting before the bind); planted.sh extra; docs.py p3; then this
# phase's tests in both eras. `mutants` runs every case planting into the startup path and the
# loader, plus the two new ones. `full` is the profile's verify. `all` (the default) runs phase,
# mutants, full. Footprint: one process tree at a time, under 1 GB.
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" phase mutants full full-legacy full-modern all

if [ "$MODE" = phase ] || [ "$MODE" = all ]; then
  uv sync --locked -q
  sh $V/planted.sh broken
  sh $V/planted.sh extra
  uv run --no-project python $V/docs.py p3
  pytest_both "tests/test_startup.py::test_a_broken_capability_stops_startup
tests/test_startup.py::test_help_works_with_a_broken_capability
tests/test_startup.py::test_capabilities_load_before_the_mode_ladder
tests/test_startup.py::test_http_load_failure_exits_before_binding
tests/test_startup.py
tests/test_capabilities.py
tests/test_cli.py
tests/test_deprecation_window.py
tests/test_hygiene.py
tests/test_mutations.py"
  echo 'p3.sh: phase ok' >&2
fi
if [ "$MODE" = mutants ] || [ "$MODE" = all ]; then
  # shellcheck disable=SC2046
  run_mutants $(cases_for 'core/__init__.py core/capabilities.py core/startup.py' \
    capability-load-failure-swallowed capability-load-after-ladder)
fi
case $MODE in full|full-legacy|all) full_legacy ;; esac
case $MODE in full|full-modern|all) full_modern ;; esac
