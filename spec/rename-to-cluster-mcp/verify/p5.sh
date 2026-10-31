#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P5's gate: the repository's text, the release recipe's gate on this head, the deferral ledger, and
# every earlier check once more.
#
#   sh spec/rename-to-cluster-mcp/verify/p5.sh [docs|release|carry|mutants|full|full-legacy|full-modern|all]
#
# `docs` (the phase-only part, about 1 min): URLs (R13), SPDX (R14), the README's one deprecation
# section (R16), the profile and recipe (R15), CI's mirror, the deferral ledger, every name check, and
# every check's controls. `release` (needs the network): the release recipe's gate, read from
# AGENTS.md and run verbatim (recipe_gate.sh), then the install probe. `carry` re-runs the
# earlier phases' own drives (failclosed.sh, legacy_cli.sh p2, instructions.py, fixture_deltas.py
# check p4, baseline.sh p4). `mutants` runs every case. `full` is the profile's verify. `all` (the
# default) runs docs, release, carry, mutants, full: about 35 min. Footprint: one process tree at a
# time, nothing in the background, under 1 GB; the build directory is removed on exit.
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" docs release carry mutants full full-legacy full-modern all

if [ "$MODE" = docs ] || [ "$MODE" = all ]; then
  uv run --no-project --with pyyaml python $V/checks.py source imports env uris urls spdx readme ledger \
    container profile-final ci docs-p1 docs-p2 docs-p3 docs-p4 docs-p5
  uv run --no-project --with pyyaml python $V/checks.py controls
  uv run pytest -q -p no:cacheprovider tests/test_hygiene.py::test_no_spec_ids_in_the_package_or_the_suite
  echo 'p5.sh: docs ok' >&2
fi
if [ "$MODE" = release ] || [ "$MODE" = all ]; then
  sh $V/recipe_gate.sh
  sh $V/probe.sh
  echo 'p5.sh: release ok' >&2
fi
if [ "$MODE" = carry ] || [ "$MODE" = all ]; then
  sh $V/failclosed.sh
  sh $V/legacy_cli.sh p2
  uv run python $V/members.py
  uv run python $V/instructions.py
  uv run python $V/fixture_deltas.py check p4
  sh $V/baseline.sh p4
  echo 'p5.sh: carry ok' >&2
fi
if [ "$MODE" = mutants ] || [ "$MODE" = all ]; then
  # shellcheck disable=SC2046
  run_mutants $(cases_for '*')
fi
case $MODE in full|full-legacy|all) full_legacy ;; esac
case $MODE in full|full-modern|all) full_modern ;; esac
