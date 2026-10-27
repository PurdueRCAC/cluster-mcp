#!/bin/sh
# Review cycle 2, class 1: the declared dependency range is the range the behaviour holds on. Run
# from the worktree root.
#
# The authentication classifier needs Paramiko 3.2 (its closed-link text and `AuthFailure`), so
# `pyproject.toml` declares `paramiko>=3.2` and the lock carries it with no locked version moved
# against the cycle's base (its merge base with develop). Every `AuthenticationException` Paramiko
# raises is classified by its cause: the refusal subclasses give up at once, an `AuthFailure` is a
# refusal only when every source was refused, and the startup message names each. Named ids in both eras, then the class's mutants:
# an `AuthFailure` read as a refusal whatever its sources, the refusal subclasses read as none, and
# the classifier's floor drifting from the declared one.
set -eu
uv lock --check
grep -q '^    "paramiko>=3.2",$' pyproject.toml
git show "$(git merge-base HEAD origin/develop)":uv.lock >"${TMPDIR:-/tmp}/ssh-reconnect-loop-base.lock"
uv run python - "${TMPDIR:-/tmp}/ssh-reconnect-loop-base.lock" <<'PY'
import sys, tomllib
from pathlib import Path

def versions(path):
    return {p['name']: p.get('version') for p in tomllib.loads(Path(path).read_text())['package']}

base, head = versions(sys.argv[1]), versions('uv.lock')
moved = {name: (base.get(name), head.get(name)) for name in base.keys() | head.keys() if base.get(name) != head.get(name)}
assert not moved, f'the floor moved locked versions: {moved}'
assert tuple(int(part) for part in head['paramiko'].split('.')[:2]) >= (3, 2), head['paramiko']
PY
T=tests/test_ssh_exec.py
IDS="tests/test_startup.py::test_connect_failure_names_host_and_cause
$T::test_the_declared_paramiko_floor_matches_the_classifier
$T::test_every_refusal_ends_the_reconnect_at_once
$T::test_a_reconnect_refused_authentication_fails_at_once
$T::test_a_reconnect_that_cannot_succeed_fails_within_the_bound"
uv run pytest -q $IDS
CLUSTER_MCP_TEST_ERA=modern uv run pytest -q $IDS
uv run python tests/mutants.py ssh-auth-strategy-read-as-refusal ssh-auth-subclass-not-refusal \
    ssh-paramiko-floor-disagrees
echo "F5-dependency-floor: green" >&2
