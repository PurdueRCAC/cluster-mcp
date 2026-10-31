#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P2's gate: the CLUSTER_MCP_* variables, the legacy names honoured with a warning, the sandbox.
#
#   sh spec/rename-to-cluster-mcp/verify/p2.sh [phase|mutants|full|full-legacy|full-modern|all]
#
# `phase` (about 3 min): the env and docs checks and their controls; failclosed.sh (either SSH-host
# variable exported in the calling shell, or carried by a uv env file, both commands still fail
# closed under the sandbox, by the venv binary and by `uv run`, with seen-red controls); legacy_cli.sh p2 (the commands alike, no RCAC or Purdue in --help/--version,
# the budget warning on stderr of a stdio session, never stdout); this phase's tests in both eras.
# `mutants` runs every case planting into the files that read the variables, plus the new ones.
# `full` as in p1.sh. `all` (the default) runs phase, mutants, full. Footprint: one process tree at a
# time, nothing in the background, under 1 GB.
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" phase mutants full full-legacy full-modern all

if [ "$MODE" = phase ] || [ "$MODE" = all ]; then
  uv run --no-project --with pyyaml python $V/checks.py source imports env container profile ci docs-p1 docs-p2
  uv run --no-project --with pyyaml python $V/checks.py controls env
  sh $V/failclosed.sh
  sh $V/legacy_cli.sh p2
  uv run python $V/fixture_deltas.py check p1
  uv run python $V/members.py
  pytest_both "tests/test_env.py::test_replacement_is_read
tests/test_env.py::test_legacy_is_honoured_with_a_warning
tests/test_env.py::test_replacement_wins_over_legacy
tests/test_env.py::test_empty_counts_as_unset
tests/test_env.py::test_whitespace_host_is_not_stripped
tests/test_env.py::test_warning_fires_once_per_name
tests/test_env.py::test_warning_names_replacement_and_window
tests/test_env.py
tests/test_exec_mode.py::test_env_host_selects_ssh
tests/test_exec_mode.py
tests/test_hygiene.py::test_sandbox_unsets_both_names
tests/test_hygiene.py
tests/test_cli.py
tests/test_identity.py
tests/test_site_startup.py
tests/test_startup.py
tests/test_mutations.py"
  echo 'p2.sh: phase ok' >&2
fi
if [ "$MODE" = mutants ] || [ "$MODE" = all ]; then
  # shellcheck disable=SC2046
  run_mutants $(cases_for 'core/__init__.py core/deprecation.py core/middleware.py core/site.py' \
    env-legacy-wins env-legacy-ignored env-replacement-ignored env-no-warning env-warning-to-stdout \
    env-host-stripped user-map-legacy-ignored budget-legacy-ignored)
fi
case $MODE in full|full-legacy|all) full_legacy ;; esac
case $MODE in full|full-modern|all) full_modern ;; esac
