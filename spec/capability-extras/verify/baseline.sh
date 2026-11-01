#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# With every capability installed, the server serves exactly what it served before the cycle, and
# the suite has lost nothing.
#
#   sh spec/capability-extras/verify/baseline.sh        from the worktree root
#
# The tree at BASE_REF (lib.sh) is extracted under the sandbox HOME and synced from its own lock
# into its own environment. In it and in this tree's environment (`uv sync --locked`, which installs
# every member through the compat root's extras): surface.py describes a default server, and
# compare.py requires the two equal, listing order and the split of the three texts included;
# `pytest --collect-only` lists the test ids and tests/mutants.py the mutation case ids, and kept.py
# requires every BASE_REF test function and case id still present here, but those
# verify/retired.txt names with a phase and a reason. Then the surface fixture and
# tests/test_surface.py must be byte-identical to BASE_REF's, committed, so
# test_served_surface_matches_baseline passes with no fixture (or comparator) edit; and the suite may
# carry no more skip or xfail marks than BASE_REF's. PYTHONPATH is dropped, so nothing outside each
# environment is imported. Runs inside bin/sandbox.sh.
# Footprint: one uv or python process at a time, under 1 GB; about 1 min warm, offline from a warm
# uv cache. Leaves base.json in the sandbox HOME for probe.sh.
set -eu
if [ -z "${CLUSTER_MCP_SANDBOX:-}" ]; then
  exec bin/sandbox.sh sh "$PWD/spec/capability-extras/verify/baseline.sh" "$@"
fi
cd "$CLUSTER_MCP_REPO"
. spec/capability-extras/verify/lib.sh
R=$CLUSTER_MCP_REPO
b="$HOME/base"
mkdir -p "$b"
git archive "$BASE_REF" | tar -x -C "$b"
unset VIRTUAL_ENV CLUSTER_MCP_TEST_ERA PYTHONPATH
list() { # list DIR PREFIX: the surface, the collected ids and the case ids of the tree at DIR
  (
    set -eu
    cd "$1"
    UV_PROJECT=$PWD
    export UV_PROJECT
    uv sync --locked -q --offline
    uv run --offline python -I "$R/$V/surface.py" "$HOME/$2.json"
    uv run --offline pytest --collect-only -q -p no:cacheprovider > "$HOME/$2-collect.txt" 2>&1 || {
      tail -n 20 "$HOME/$2-collect.txt" >&2; echo "baseline: collection failed in $1" >&2; exit 1; }
    uv run --offline python -c "import sys; sys.path.insert(0, 'tests'); import mutants; print(*(c.id for c in mutants.CASES), sep='\n')" > "$HOME/$2-cases.txt"
  ) || fail "cannot list $2 (above)"
}
list "$b" base
list "$R" head
uv run --no-project python -I "$R/$V/compare.py" "$HOME/base.json" "$HOME/head.json" || fail 'the served surface changed'
uv run --no-project python -I "$R/$V/kept.py" "$HOME/base-collect.txt" "$HOME/head-collect.txt" \
  "$HOME/base-cases.txt" "$HOME/head-cases.txt" "$R/$V/retired.txt" || fail 'the suite lost a test or a mutation case'
for f in tests/fixtures/served_surface.json tests/test_surface.py; do
  git diff --quiet "$BASE_REF" -- "$f" || fail "$f differs from $BASE_REF's"
  git diff --quiet -- "$f" || fail "$f has an uncommitted edit"
done
skips() { cat "$1"/tests/*.py | grep -E -o 'mark\.(skip|skipif|xfail)\b|pytest\.(skip|xfail)\(' | wc -l | tr -d ' '; }
[ "$(skips "$R")" -le "$(skips "$b")" ] || fail "the suite skips or xfails more than at $BASE_REF ($(skips "$R") > $(skips "$b"))"
echo 'baseline: ok' >&2
