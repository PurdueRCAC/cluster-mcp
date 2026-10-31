#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P1's gate: the uv workspace, the cluster_mcp namespace, the command names, the install probe.
#
#   sh spec/rename-to-cluster-mcp/verify/p1.sh [phase|mutants|full|full-legacy|full-modern|all]
#
# `phase` (the phase-only part, about 6 min): the static checks and their controls; every artifact
# built into a fresh directory and scanned (four wheels, four sdists, no cluster_mcp/__init__.py,
# twine, sdist hygiene); the install probe (probe.sh: the subdirectory install builds the members
# from the same commit; python -m; the old install line); the two commands side by side
# (legacy_cli.sh p1); nothing 0.1.4 had is lost (baseline.sh p1: tests, mutation cases and their
# plants, the served tools' schemas; fixture_deltas.py check p1: the fixture untouched); each tool
# registered by its member (members.py); this phase's tests in both eras.
# `mutants` runs every mutation case and the runner's self-check (6-10 min). `full` is the profile's
# verify (about 8 min), `full-legacy`/`full-modern` its halves. `all` (the default) runs phase,
# mutants, full. Footprint: one process tree at a time, nothing in the background, under 1 GB; the
# build directory is removed on exit. Needs the network on a cold uv cache (probe.sh, baseline.sh).
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" phase mutants full full-legacy full-modern all

if [ "$MODE" = phase ] || [ "$MODE" = all ]; then
  uv run --no-project --with pyyaml python $V/checks.py source imports container profile ci docs-p1
  uv run --no-project --with pyyaml python $V/checks.py controls source imports container ci
  dist=$(mktemp -d "${TMPDIR:-/tmp}/p1-dist.XXXXXX")
  trap 'rm -rf "$dist"' EXIT HUP INT TERM
  uv build -q --all-packages --no-sources -o "$dist"
  uv run --no-project --with pyyaml python $V/checks.py wheels "$dist"
  uvx twine check --strict "$dist"/*
  uv run python bin/sdist_hygiene.py "$dist"
  sh $V/probe.sh
  sh $V/legacy_cli.sh p1
  sh $V/baseline.sh p1
  uv run python $V/fixture_deltas.py check p1
  uv run python $V/members.py
  pytest_both "tests/test_packaging.py::test_no_member_ships_a_namespace_init
tests/test_packaging.py::test_namespace_check_catches_a_stray_init
tests/test_packaging.py::test_each_member_holds_only_its_own_subpackage
tests/test_packaging.py::test_every_distribution_carries_one_version
tests/test_packaging.py::test_version_check_catches_drift
tests/test_packaging.py::test_version_comes_from_the_installed_metadata
tests/test_packaging.py::test_console_scripts_are_cluster_mcp_and_the_legacy_alias
tests/test_packaging.py
tests/test_cli.py::test_legacy_command_warns_then_runs_cluster_mcp
tests/test_cli.py::test_legacy_command_keeps_stdout_clean_on_stdio
tests/test_cli.py::test_python_m_runs_the_entry_point
tests/test_cli.py::test_version_identifies_as_cluster_mcp
tests/test_cli.py
tests/test_hygiene.py::test_spec_id_scan_covers_every_member
tests/test_hygiene.py
tests/test_mutations.py::test_mutation_case_files_name_a_member
tests/test_mutations.py
tests/test_registry.py
tests/test_surface.py::test_served_surface_matches_baseline
tests/test_tools.py
tests/test_sbatch.py"
  echo 'p1.sh: phase ok' >&2
fi
if [ "$MODE" = mutants ] || [ "$MODE" = all ]; then
  # shellcheck disable=SC2046
  run_mutants $(cases_for '*' legacy-command-silent legacy-command-exit-swallowed legacy-warning-to-stdout)
fi
case $MODE in full|full-legacy|all) full_legacy ;; esac
case $MODE in full|full-modern|all) full_modern ;; esac
