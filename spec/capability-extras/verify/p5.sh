#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P5's gate, the last phase: every independent check of the cycle on the finished tree, the
# release recipe's offline gate steps on this head, the deferral ledger, and the full verify.
#
#   sh spec/capability-extras/verify/p5.sh [phase|ledger|recipe|mutants|full|full-legacy|full-modern|all]
#
# `phase` (about 8 min warm): every earlier gate's independent checks, each once, in their final
# modes (pyprojects p4, imports p2, compose p2, docs p4, planted extra and broken, coreonly, probe,
# baseline). `ledger`: ledger.py (pre-push safe, seconds). `recipe`: under bin/sandbox.sh, the
# release recipe's build, `twine check --strict` and sdist hygiene into the sandbox HOME (the
# networked dependency audit is the recipe's and CI's, never a phase gate's). `mutants`: every case
# planting into a file this cycle changed, and every new case (about 15 min). `full`: the profile's
# verify. `all` (the default) runs phase, ledger, recipe, mutants, full. Footprint: one process tree
# at a time, nothing in the background, under 1 GB.
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" phase ledger recipe mutants full full-legacy full-modern all

if [ "$MODE" = phase ] || [ "$MODE" = all ]; then
  uv lock --check
  uv sync --locked -q
  uv run --no-project python $V/pyprojects.py p4
  uv run --no-project python $V/imports.py p2
  uv run python $V/compose.py p2
  uv run --no-project python $V/docs.py p4
  sh $V/planted.sh extra
  sh $V/planted.sh broken
  sh $V/coreonly.sh
  sh $V/probe.sh
  sh $V/baseline.sh
  echo 'p5.sh: phase ok' >&2
fi
if [ "$MODE" = ledger ] || [ "$MODE" = all ]; then
  uv run --no-project python $V/ledger.py
fi
if [ "$MODE" = recipe ] || [ "$MODE" = all ]; then
  bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv build -q --all-packages --no-sources -o "$HOME/dist" && uvx --offline twine check --strict "$HOME"/dist/* && uv run python bin/sdist_hygiene.py "$HOME/dist"'
fi
if [ "$MODE" = mutants ] || [ "$MODE" = all ]; then
  # shellcheck disable=SC2046
  run_mutants $(cases_for 'core/server.py core/tools/__init__.py core/capabilities.py core/resources.py core/__init__.py core/startup.py core/instructions.py slurm/instructions.py slurm/capability.py rcac/instructions.py rcac/capability.py rcac/resources.py rcac/tools.py' \
    capability-order-from-discovery capability-tools-unfiltered core-imports-member-by-name capability-duplicate-tool-allowed \
    capability-tools-import-swallowed capability-instructions-unchecked \
    storage-resource-unconditional capability-resource-open-allowed capability-load-failure-swallowed capability-load-after-ladder)
fi
case $MODE in full|full-legacy|all) full_legacy ;; esac
case $MODE in full|full-modern|all) full_modern ;; esac
