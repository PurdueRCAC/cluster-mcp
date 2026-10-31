#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# Nothing the 0.1.4 release had is lost in the move: its tests, its mutation cases, its tools.
#
#   sh spec/rename-to-cluster-mcp/verify/baseline.sh p1|p3|p4      from the worktree root
#
# The 0.1.4 tree (the tag) is extracted under the sandbox HOME and synced from its own lock. From it
# and from this tree, in each one's environment: the collected test ids, the mutation case ids, and
# the served surface (surface.py). Then compare.py requires, for every test function 0.1.4 collected
# (file::function, parameters dropped), at least as many collected ids here under the same file and
# function; every 0.1.4 mutation case here with the same plant, targets and `why` (compare.py says
# what the move may change, and replants.txt names each case allowed to change more); the tools served byte-for-byte alike (name,
# description, input and output schemas, annotations); and the resources: identical in p1, and from
# p3 the 0.1.4 entries kept under their rcac:// URIs with a cluster:// twin of each, equal but for its
# URI, and nothing else. From p4 the server name is cluster-mcp (0.1.4's was RCAC). Runs inside
# bin/sandbox.sh. Footprint: one uv or pytest process at a time, under 1 GB; about 1 min warm.
set -eu
phase=${1:?usage: baseline.sh p1|p3|p4}
case $phase in p1|p3|p4) ;; *) echo "baseline: unknown phase $phase" >&2; exit 2 ;; esac
if [ -z "${CLUSTER_MCP_SANDBOX:-}" ]; then
  exec bin/sandbox.sh sh "$PWD/spec/rename-to-cluster-mcp/verify/baseline.sh" "$@"
fi
V="$CLUSTER_MCP_REPO/spec/rename-to-cluster-mcp/verify"
b="$HOME/baseline"
mkdir -p "$b"
git -C "$CLUSTER_MCP_REPO" archive 0.1.4 | tar -x -C "$b"
list() { # list DIR PACKAGE PREFIX: ids, cases and surface of the tree at DIR
  (
    set -eu
    cd "$1"
    UV_PROJECT=$PWD
    export UV_PROJECT
    unset VIRTUAL_ENV CLUSTER_MCP_TEST_ERA
    uv sync --locked -q
    uv run pytest --collect-only -q -p no:cacheprovider > "$HOME/$3-collect.txt" 2>&1 || {
      tail -n 20 "$HOME/$3-collect.txt" >&2; echo "baseline: collection failed in $1" >&2; exit 1; }
    grep '::' "$HOME/$3-collect.txt" > "$HOME/$3-ids.txt" || { echo "baseline: no ids collected in $1" >&2; exit 1; }
    uv run python -c "import dataclasses, json, sys; sys.path.insert(0, 'tests'); import mutants; json.dump([dataclasses.asdict(c) for c in mutants.CASES], sys.stdout)" > "$HOME/$3-cases.json"
    uv run python "$V/surface.py" "$2" "$HOME/$3-surface.json"
  )
}
list "$b" rcac_mcp base
list "$CLUSTER_MCP_REPO" cluster_mcp.core head
uv run --no-project python "$V/compare.py" "$phase" "$HOME" "$V/replants.txt"
