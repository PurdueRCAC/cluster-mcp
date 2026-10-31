#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P4's gate: the instructions split into a generic core, the Slurm snippet and the RCAC overlay, and
# the server's name.
#
#   sh spec/rename-to-cluster-mcp/verify/p4.sh [phase|mutants|full|full-legacy|full-modern|all]
#
# `phase` (about 4 min): the static checks (uris now in full); instructions.py (R11, R12, read from
# the members, independent of the suite); the fixture's deltas (fixture_deltas.py check p4); the
# served surface against 0.1.4 with the server named cluster-mcp (baseline.sh p4); legacy_cli.sh p2;
# this phase's tests in both eras. `mutants` runs every case planting into the server, the site
# composer or an instructions module, plus the new ones. `full` as in p1.sh. `all` (the default)
# runs phase, mutants, full. Footprint: one process tree at a time, nothing in the background,
# under 1 GB.
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" phase mutants full full-legacy full-modern all

if [ "$MODE" = phase ] || [ "$MODE" = all ]; then
  uv run --no-project --with pyyaml python $V/checks.py source imports env uris container profile ci docs-p1 docs-p2 docs-p3 docs-p4
  uv run --no-project --with pyyaml python $V/checks.py controls uris
  uv run python $V/instructions.py
  uv run python $V/fixture_deltas.py check p4
  sh $V/baseline.sh p4
  sh $V/legacy_cli.sh p2
  pytest_both "tests/test_instructions.py::test_core_instructions_are_generic
tests/test_instructions.py::test_overlay_is_labelled_and_lists_the_rcac_member
tests/test_instructions.py::test_slurm_snippet_lists_the_slurm_member
tests/test_instructions.py::test_base_is_core_slurm_then_overlay
tests/test_instructions.py
tests/test_protocol.py::test_server_identifies_as_cluster_mcp
tests/test_protocol.py
tests/test_surface.py
tests/test_site.py
tests/test_site_startup.py
tests/test_transports.py
tests/test_context.py
tests/test_mutations.py"
  echo 'p4.sh: phase ok' >&2
fi
if [ "$MODE" = mutants ] || [ "$MODE" = all ]; then
  # shellcheck disable=SC2046
  run_mutants $(cases_for 'core/server.py core/site.py core/instructions.py slurm/instructions.py rcac/instructions.py' \
    overlay-dropped core-names-rcac-tool server-name-rcac)
fi
case $MODE in full|full-legacy|all) full_legacy ;; esac
case $MODE in full|full-modern|all) full_modern ;; esac
