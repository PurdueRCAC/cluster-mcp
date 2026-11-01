#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P4's gate: the capabilities are extras; the core alone installs and serves the core; the compat
# root installs every capability and serves what it served before; the docs name the extras.
#
#   sh spec/capability-extras/verify/p4.sh [phase|mutants|full|full-legacy|full-modern|all]
#
# `phase` (about 6 min warm): `uv lock --check`; `uv sync --locked`; pyprojects.py p4; docs.py p4;
# coreonly.sh (real environments for the core alone, each extra alone and both); probe.sh (the
# built metadata and every install line from one commit, and the old line's surface against
# BASE_REF's); baseline.sh; then this phase's tests in both eras. `mutants` re-runs
# `core-imports-member-by-name` (its targets are the static scans: a mutant child carries every
# member on PYTHONPATH, so no core-only drive can be its target). `full` is the
# profile's verify. `all` (the default) runs phase, mutants, full. Offline from a warm uv cache.
# Footprint: one process tree at a time, under 1 GB.
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" phase mutants full full-legacy full-modern all

if [ "$MODE" = phase ] || [ "$MODE" = all ]; then
  uv lock --check
  uv sync --locked -q
  uv run --no-project python $V/pyprojects.py p4
  uv run --no-project python $V/docs.py p4
  sh $V/coreonly.sh
  sh $V/probe.sh
  sh $V/baseline.sh
  pytest_both "tests/test_core_only.py::test_core_only_install_serves_the_core
tests/test_core_only.py::test_core_only_instructions_name_exactly_its_tools
tests/test_core_only.py
tests/test_packaging.py::test_core_declares_the_capability_extras
tests/test_packaging.py::test_compat_root_installs_every_capability
tests/test_packaging.py
tests/test_capabilities.py
tests/test_hygiene.py
tests/test_mutations.py"
  echo 'p4.sh: phase ok' >&2
fi
if [ "$MODE" = mutants ] || [ "$MODE" = all ]; then
  run_mutants core-imports-member-by-name
fi
case $MODE in full|full-legacy|all) full_legacy ;; esac
case $MODE in full|full-modern|all) full_modern ;; esac
