#!/bin/sh
# Phase gate for restore-test-coverage. From the worktree root:
#
#   sh spec/restore-test-coverage/verify/gate.sh P<n>               the cumulative gate for phase n
#   sh spec/restore-test-coverage/verify/gate.sh P8 --phase-only    P8's own checks: no suite, no clone
#
# The base is resolved here, outside the sandbox, where git can still reach origin with the real
# credentials. The whole gate then runs inside bin/sandbox.sh: a throwaway HOME, a blank auth
# environment, no RCAC_SSH_HOST, and every scratch file in the sandbox directory, which the
# sandbox removes on exit. run.sh steps back into the repository first, so pytest reads
# pyproject.toml.
set -eu
root=$(git rev-parse --show-toplevel)
git -C "$root" fetch -q origin develop 2> /dev/null || echo 'gate: could not fetch origin/develop; using the local ref' >&2
GATE_BASE=$(git -C "$root" merge-base HEAD origin/develop 2> /dev/null || git -C "$root" merge-base HEAD develop 2> /dev/null) || {
    echo 'gate: neither origin/develop nor develop is reachable; run git fetch origin develop' >&2
    exit 2
}
export GATE_BASE
exec "$root/bin/sandbox.sh" sh "$root/spec/restore-test-coverage/verify/run.sh" "$@"
