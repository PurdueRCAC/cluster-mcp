#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# The release recipe's gate, read from AGENTS.md and run verbatim on this tree (GOAL R15).
#
#   sh spec/rename-to-cluster-mcp/verify/recipe_gate.sh        from the worktree root
#
# Each step of `release.gate`, in order, through `sh -c`, as the release skill runs them; the steps
# are never restated here, so a wrong step in the recipe fails here. The recipe's `clean_paths`
# must be absent before (a stale dist/ would be checked in place of this build) and are removed
# after, on every exit path. Then this cycle's wheel scan over the dist/ the gate built. Needs the
# network (the dependency audit fails closed without it). Footprint: one process tree at a time,
# under 1 GB; about 10 min.
set -eu
V=spec/rename-to-cluster-mcp/verify
fail() { echo "recipe_gate: $*" >&2; exit 1; }
steps=$(mktemp "${TMPDIR:-/tmp}/recipe-gate.XXXXXX")
uv run --no-project --with pyyaml python - "$steps" <<'PY'
import sys
sys.path.insert(0, 'spec/rename-to-cluster-mcp/verify')
from pathlib import Path
from checks import recipe, text
rel = recipe(text(Path('.'), 'AGENTS.md') or '')
if not rel or not rel.get('gate') or rel.get('clean_paths') != ['dist/']:
    sys.exit('recipe_gate: cannot read release.gate, or clean_paths is not [dist/]')
if any('\n' in s for s in rel['gate']):
    sys.exit('recipe_gate: a gate step spans lines')
Path(sys.argv[1]).write_text(''.join(f'{s}\n' for s in rel['gate']))
PY
[ ! -e dist ] || fail 'dist/ exists: remove it first (the recipe clean_paths)'
trap 'rm -rf dist "$steps"' EXIT HUP INT TERM
n=0
while IFS= read -r step; do
  n=$((n + 1))
  echo "recipe_gate: step $n: $step" >&2
  sh -c "$step" < /dev/null || fail "step $n failed: $step"
done < "$steps"
[ "$n" -ge 7 ] || fail "only $n gate steps ran"
uv run --no-project --with pyyaml python $V/checks.py wheels dist
echo "recipe_gate: ok ($n steps)" >&2
