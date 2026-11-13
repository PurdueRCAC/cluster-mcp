#!/bin/sh
# Phase gate for integration-marker-wording. From the worktree root, after staging:
#
#   sh spec/integration-marker-wording/verify/gate.sh P1|P2|P3   a phase: its parts, in order
#   sh spec/integration-marker-wording/verify/gate.sh prepush    P3 without the full verify
#   sh spec/integration-marker-wording/verify/gate.sh <part>     one part: wording, slice, ids,
#                                                                sweep, ledger, full, or scope-P1|P2|P3
#
# P1 = wording slice scope-P1. P2 = wording slice ids sweep scope-P2. P3 = the same with scope-P3
# and ledger, then full (the profile's full verify: run P3 in the background). Every part refuses a
# tree with unstaged or untracked changes. Offline: nothing reaches a host but 127.0.0.1.
#
# Footprint: one child at a time (uv, then one python or pytest; the sweep's pytest children run one
# after another); peak under 400 MB outside `full`, which is the profile's own suite. No background
# work, so nothing outlives the gate; each part removes its own temporary directory.

V=spec/integration-marker-wording/verify

fail() { echo "gate[$phase]: $*" >&2; exit 1; }
gpy() { uv run --no-sync python -I "$V/marker_gate.py" "$@"; }

# The descriptions make only claims the probe proves against tests/conftest.py, every route the
# probe finds open is named, and AGENTS.md states the markers word for word (the drafted check).
wording() {
    PYTHONPATH=tests uv run --no-sync pytest -q -p no:cacheprovider -p conftest -c pyproject.toml --rootdir=. \
        "$V/guard_claims.py" || fail 'a wording claim is not what tests/conftest.py enforces'
    gpy wording || fail 'AGENTS.md or pyproject.toml does not state the markers as planned'
}

# The module the cycle edits, in both protocol eras, and pytest reads the new descriptions.
slice() {
    for era in legacy modern; do
        CLUSTER_MCP_TEST_ERA=$era uv run --no-sync pytest -q -p no:cacheprovider tests/test_hygiene.py ||
            fail "tests/test_hygiene.py is red in the $era era"
    done
    markers=$(uv run --no-sync pytest --markers)
    printf '%s\n' "$markers" | grep -q '^@pytest.mark.unit: starts no process' ||
        fail 'pytest does not read the new unit description'
    printf '%s\n' "$markers" | grep -q '^@pytest.mark.integration: needs what a unit test is refused' ||
        fail 'pytest does not read the new integration description'
}

# Every named id ran and passed, in both eras: the live check, each planned row, the kept rails.
ids() {
    tmp=$(mktemp -d)
    for era in legacy modern; do
        CLUSTER_MCP_TEST_ERA=$era uv run --no-sync pytest -q -p no:cacheprovider --junitxml="$tmp/$era.xml" \
            tests/test_hygiene.py >/dev/null
    done
    gpy ids "$tmp/legacy.xml" "$tmp/modern.xml"
    rc=$?
    rm -rf "$tmp"
    [ "$rc" -eq 0 ] || fail 'a named id is missing or not passed'
}

# Every mutant of the check, decision or carve-out, is killed by the rows it names.
sweep() {
    uv run --no-sync python -I "$V/marker_mutants.py" || fail 'a mutant of the check survived'
}

scope() { gpy scope "$1" || fail "the $1 tree changes what it may not"; }

ledger() { gpy ledger || fail 'a deferral has no seed and roadmap entry'; }

# The profile's full verify, word for word (AGENTS.md § Factory, Profile).
full() {
    uv lock --check &&
        uv run pytest -q tests/test_ssh_exec.py -k silent &&
        uv run pytest -q tests/test_ssh_exec.py -k 'not silent' &&
        uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py &&
        uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py &&
        CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k silent &&
        CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k 'not silent' &&
        CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py &&
        CLUSTER_MCP_TEST_ERA=modern uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py &&
        bin/sandbox.sh uv run cluster-mcp --help >/dev/null ||
        fail "the profile's full verify is red"
}

# The pytest parts run the working copy; the checks read the index. They agree only on a tree with
# nothing unstaged and nothing untracked, so the gate refuses any other.
staged_only() {
    git diff --quiet && [ -z "$(git ls-files --others --exclude-standard)" ] ||
        fail 'unstaged or untracked changes: stage the phase first, so the gate grades what commits'
}

main() {
    set -u
    export UV_PYTHON=3.14
    cd "$(git rev-parse --show-toplevel)" || exit 1
    phase=${1:?usage: gate.sh P1|P2|P3|prepush|wording|slice|ids|sweep|ledger|full|scope-P1|scope-P2|scope-P3}
    staged_only
    case $phase in
        P1) wording; slice; scope P1 ;;
        P2) wording; slice; ids; sweep; scope P2 ;;
        P3) wording; slice; ids; sweep; scope P3; ledger; full ;;
        prepush) wording; slice; ids; sweep; scope P3; ledger ;;
        wording|slice|ids|sweep|ledger|full) "$phase" ;;
        scope-P1|scope-P2|scope-P3) scope "${phase#scope-}" ;;
        *) fail "unknown phase or part" ;;
    esac
    echo "gate[$phase]: ok"
}

main "$@"; exit $?
