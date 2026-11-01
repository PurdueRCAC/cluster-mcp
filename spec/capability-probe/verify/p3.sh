#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P3's gate, the last phase: every independent check of the cycle on the finished tree, the whole
# cycle's alternatives covered, the surface and suite against BASE_REF, the release recipe's offline
# steps, the deferral ledger and the full verify.
#
#   sh spec/capability-probe/verify/p3.sh [phase|ledger|recipe|equivalents|full-legacy|full-modern|all]
#
# `phase` (about 3 min warm): declared.py, lookups.py, startup_order.py, drives.py all, docs_gate.py
# p2, alternatives.py coverage all (every alternative of both phases has a case, every case a row
# beside each member set), baseline.sh. `ledger` (seconds, pre-push safe): ledger.py. `recipe`: under
# bin/sandbox.sh, the release recipe's build, `twine check --strict` and sdist hygiene into the
# sandbox HOME (the networked dependency audit is the recipe's and CI's, never a phase gate's).
# `equivalents`: each recorded equivalent planted, its targets passing in both eras (seconds per
# equivalent). The phases' cases are not run again here: each phase ran its own. `full-legacy` /
# `full-modern`: the profile's verify, in halves. `all` runs every mode. Footprint: one process tree
# at a time, nothing in the background, under 1 GB.
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" phase ledger recipe equivalents full-legacy full-modern all

if [ "$MODE" = phase ] || [ "$MODE" = all ]; then
  uv lock --check
  uv sync --locked -q
  $PY $V/declared.py
  bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run python -I spec/capability-probe/verify/lookups.py'
  $PY $V/startup_order.py
  bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run python -I spec/capability-probe/verify/drives.py all'
  $PY $V/docs_gate.py p2
  $PY $V/alternatives.py coverage all
  sh $V/baseline.sh
  echo 'p3.sh: phase ok' >&2
fi
if [ "$MODE" = ledger ] || [ "$MODE" = all ]; then
  uv run --no-project python -I $V/ledger.py
fi
if [ "$MODE" = recipe ] || [ "$MODE" = all ]; then
  bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv build -q --all-packages --no-sources -o "$HOME/dist" && uvx --offline twine check --strict "$HOME"/dist/* && uv run python bin/sdist_hygiene.py "$HOME/dist"'
fi
case $MODE in equivalents|all) $PY $V/alternatives.py equivalents all ;; esac
case $MODE in full-legacy|all) full_legacy ;; esac
case $MODE in full-modern|all) full_modern ;; esac
