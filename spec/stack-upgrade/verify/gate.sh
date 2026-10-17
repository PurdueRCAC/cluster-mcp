#!/bin/sh
# Phase gate for stack-upgrade. From the worktree root:
#
#   sh spec/stack-upgrade/verify/gate.sh P<n>             the cumulative, offline-capable gate for phase n
#   sh spec/stack-upgrade/verify/gate.sh P<n> --audit DIR n >= 6: the networked audit proofs only; DIR is a
#                                                         planted project (pyproject.toml + uv.lock) build prepares
#   sh spec/stack-upgrade/verify/gate.sh P7 --phase-only  P7's document and ledger checks: no suite, no clone
#
# Two bases. GATE_BASE is the merge-base with develop, resolved here, outside the sandbox, where
# git can reach origin with the real credentials: it scopes "what this cycle changed", so a rebase
# onto a newer develop is not counted as this cycle's edit. BASELINE is 3d010ec, fixed by the GOAL:
# the commit whose test ids, mutation cases and served surface the cycle must preserve. Everything
# after this point runs inside bin/sandbox.sh: a throwaway HOME, a blank auth environment, no
# RCAC_SSH_HOST, and every scratch file under the sandbox directory, removed on exit.
set -eu
root=$(git rev-parse --show-toplevel)
git -C "$root" fetch -q origin develop 2> /dev/null || echo 'gate: could not fetch origin/develop; using the local ref' >&2
GATE_BASE=$(git -C "$root" merge-base HEAD origin/develop 2> /dev/null || git -C "$root" merge-base HEAD develop 2> /dev/null) || {
    echo 'gate: neither origin/develop nor develop is reachable; run git fetch origin develop' >&2
    exit 2
}
BASELINE=$(git -C "$root" rev-parse --verify -q 3d010ec^{commit}) || {
    echo 'gate: the baseline commit 3d010ec is not in this repository' >&2
    exit 2
}
export GATE_BASE BASELINE
exec "$root/bin/sandbox.sh" sh "$root/spec/stack-upgrade/verify/run.sh" "$@"
