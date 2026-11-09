#!/bin/sh
# Last-phase gate for full-volume-fixture-leaks-hdiutil. Modes, each usable alone:
#   pre      rows.sh all; the docs name the new tests; the cycle touched only its files; the ledger
#   sweep-a  the mutant sweep's first half (verify/mutants.py a), written in P3
#   sweep-b  its second half (verify/mutants.py b)
#   full     the profile's full verify, verbatim (~26 min on the build host: run it in the background)
#   all      pre, sweep-a, sweep-b, full, in that order
#   selftest pre, with the scope graded from HEAD instead of the plan commit (a prototype has none);
#            used only to dry-run this gate, never as the phase's verify
#
# Footprint: one command at a time; peak about 6 processes (pytest, a stand-in and its child, ps, the
# sweep's driver); under 500 MB. The sweep KILLs each case's process group at its cap.

set -u
SLUG=full-volume-fixture-leaks-hdiutil
HERE=spec/$SLUG/verify

pre() {
    sh "$HERE/rows.sh" all || return 1
    for name in test_a_disk_image_step_that_fails_or_hangs_leaves_nothing_running test_a_stopped_step_still_running_is_named; do
        grep -qF "$name" AGENTS.md || { echo "p3.sh: AGENTS.md does not name $name" >&2; return 1; }
    done
    grep -q 'hdiutil' tests/test_ssh_exec.py && sed -n '1,/^"""$/p' tests/test_ssh_exec.py | sed -n '2,$p' | grep -q 'hdiutil' \
        || { echo 'p3.sh: the module docstring does not describe the disk-image rows' >&2; return 1; }
    scope "${1:-}" || return 1
    ledger || return 1
    echo 'p3.sh: pre ok'
}

scope() {
    # Graded from the plan commit: the cycle changes only the fixture's module, the stand-in, AGENTS.md
    # and its own spec directory (staged or committed).
    if [ "${1:-}" = selftest ]; then plan=$(git rev-parse HEAD); else plan=$(git log --format=%H -1 --grep="Plan $SLUG"); fi
    [ -n "$plan" ] || { echo 'p3.sh: no plan commit found' >&2; return 1; }
    stray=$( { git diff --name-only "$plan" HEAD; git diff --cached --name-only "$plan"; } | sort -u \
        | grep -v -e '^tests/test_ssh_exec\.py$' -e '^tests/hdiutil_standin\.py$' -e '^AGENTS\.md$' -e "^spec/$SLUG/")
    [ -z "$stray" ] || { echo "p3.sh: files outside the cycle's scope changed:" >&2; echo "$stray" >&2; return 1; }
}

ledger() {
    # Every deferral the plan or roadmap states, in prose or a list item (never a heading), names an
    # issues/ seed that exists and a ROADMAP.md entry pointing at it.
    bad=0
    for f in "spec/$SLUG/PLAN.md" "spec/$SLUG/TECH.md"; do
        grep -n -i -E 'follow-up|known limitation|do not fix here|left for|deferred to|seed is filed' "$f" | grep -v -E '^[0-9]+:#' \
        | while IFS= read -r line; do
            seed=$(printf '%s\n' "$line" | grep -o -E 'issues/[a-z0-9-]+\.md' | head -1)
            if [ -z "$seed" ] || [ ! -f "$seed" ] || ! grep -qF "($seed)" ROADMAP.md; then  # The seed and its index entry.
                echo "p3.sh: an unrecorded deferral in $f: $line" >&2
                echo bad
            fi
          done
    done | grep -q bad && bad=1
    [ "$bad" -eq 0 ] || return 1
    echo 'p3.sh: ledger ok'
}

sweep() {
    [ -f "$HERE/mutants.py" ] || { echo "p3.sh: $HERE/mutants.py is not written yet (P3 writes it)" >&2; return 1; }
    UV_PYTHON=3.14 uv run python -I "$PWD/$HERE/mutants.py" "$1"
}

full() {
    export UV_PYTHON=3.14
    uv lock --check && uv run pytest -q tests/test_ssh_exec.py -k silent && uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k silent && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && bin/sandbox.sh uv run cluster-mcp --help
}

main() {
    case ${1:-} in
        pre) pre ;;
        selftest) pre selftest ;;
        sweep-a) sweep a ;;
        sweep-b) sweep b ;;
        full) full ;;
        all) pre && sweep a && sweep b && full ;;
        *) echo 'usage: p3.sh pre|sweep-a|sweep-b|full|all' >&2; return 2 ;;
    esac
}

main "$@"; exit $?
