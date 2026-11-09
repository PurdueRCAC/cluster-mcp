#!/bin/sh
# Row-level gate for full-volume-fixture-leaks-hdiutil: runs the named disk-image rows, in both
# protocol eras, by exact test id, and fails unless every named id passed (a deselected or missing
# id is red, never a quiet green).
#
# Usage, from the cycle worktree root:  sh spec/full-volume-fixture-leaks-hdiutil/verify/rows.sh p1|p2|all
#   p1   the stop-and-name rows (no device cleanup), the survivor and figures tests, the control row,
#        and the three real full-volume rows (real hdiutil on macOS, the in-process path on Linux)
#   p2   p1 plus the cleanup, leftover and report-order rows: every stand-in row
#   all  p2 plus the suite's own rails (hygiene, the -k partition)
# Every mode also resolves the annotations of both files (the annotation check's rule, applied to tests/).
#
# Footprint: one pytest at a time; peak about 5 processes (pytest, a stand-in step, its child, ps);
# under 400 MB. Everything runs in the foreground; a stand-in a row starts is killed by that row's own
# teardown (`_kill_recorded`); every mode then checks that no stand-in runs and (macOS) no image the
# rows made is attached.
# Time, measured on the prototype (macOS 27, both eras; PLAN §6 dry runs): p1 ~16 s, p2 ~34 s, all ~39 s.

set -u
MOD=tests/test_ssh_exec.py
ROWS=test_a_disk_image_step_that_fails_or_hangs_leaves_nothing_running

P1_IDS="$ROWS[create-hangs] $ROWS[create-fails] $ROWS[every-step-succeeds] $ROWS[body-fails] test_a_stopped_step_still_running_is_named test_the_disk_image_figures"
P2_IDS="$ROWS[create-hangs-with-device] $ROWS[create-fails-with-device] $ROWS[attach-hangs] $ROWS[attach-hangs-with-device] $ROWS[attach-fails] $ROWS[attach-fails-with-device] $ROWS[detach-hangs] $ROWS[detach-fails] $ROWS[body-and-detach-fail] $ROWS[cleanup-detach-hangs] $ROWS[cleanup-detach-fails] $ROWS[info-fails-in-cleanup] $ROWS[info-answers-garbled]"
REAL_IDS="test_a_write_that_runs_out_of_room_keeps_the_file[8k-free] test_a_write_that_runs_out_of_room_keeps_the_file[32k-free] test_a_write_that_runs_out_of_room_keeps_the_file[edquot]"

run_ids() {
    # $1: the era ('' or modern); the rest: test ids. Every id must be reported PASSED.
    era=$1; shift
    args=""
    for id in "$@"; do args="$args $MOD::$id"; done
    if [ -n "$era" ]; then
        out=$(CLUSTER_MCP_TEST_ERA=$era uv run pytest -q -rA -p no:cacheprovider $args 2>&1)
    else
        out=$(env -u CLUSTER_MCP_TEST_ERA uv run pytest -q -rA -p no:cacheprovider $args 2>&1)
    fi
    status=$?
    for id in "$@"; do
        printf '%s\n' "$out" | grep -qF "PASSED $MOD::$id" || {
            printf '%s\n' "$out" | tail -40
            echo "rows.sh: not passed in era '${era:-legacy}': $id" >&2
            return 1
        }
    done
    [ "$status" -eq 0 ] || { printf '%s\n' "$out" | tail -40; echo "rows.sh: pytest exited $status" >&2; return 1; }
    echo "rows.sh: era ${era:-legacy}: $# ids passed"
}

partition() {
    # The new rows land in the `-k 'not silent'` part of the suite (the CI job with the room), never in `-k silent`.
    quiet=$(uv run pytest -q --collect-only -p no:cacheprovider $MOD -k 'not silent' 2>&1)
    loud=$(uv run pytest -q --collect-only -p no:cacheprovider $MOD -k silent 2>&1)
    for id in $P1_IDS $P2_IDS; do
        printf '%s\n' "$quiet" | grep -qF "$MOD::$id" || { echo "rows.sh: $id is not in -k 'not silent'" >&2; return 1; }
        if printf '%s\n' "$loud" | grep -qF "$MOD::$id"; then echo "rows.sh: $id is in -k silent" >&2; return 1; fi
    done
    echo 'rows.sh: partition ok'
}

hints() {
    # Every function either file defines resolves its annotations to types.
    uv run python -I -c "
import inspect, sys, typing
sys.path.insert(0, 'tests')
import hdiutil_standin, test_ssh_exec
n = 0
for module in (hdiutil_standin, test_ssh_exec):
    for name, f in vars(module).items():
        if inspect.isfunction(f) and f.__module__ == module.__name__:
            typing.get_type_hints(getattr(f, '__wrapped__', f)); n += 1
assert n > 10, n
print(f'rows.sh: annotations resolve ({n} functions)')
"
}

leftovers() {
    # Nothing the rows started outlives them: no stand-in process, and (macOS) no image a row attached.
    # A stand-in's argv starts with the interpreter running the script; a shell whose command line
    # merely mentions the script (this gate's caller, say) never matches.
    standin='^[^Z][^ ]* +[^ ]*python[^ ]* -I [^ ]*tests/hdiutil_standin\.py '
    if ps -A -ww -o stat= -o args= | grep -Eq "$standin"; then
        ps -A -ww -o stat= -o args= | grep -E "$standin" >&2
        echo 'rows.sh: a stand-in process is still running' >&2; return 1
    fi
    if command -v hdiutil >/dev/null 2>&1 && hdiutil info | grep -q 'pytest-of-'; then
        echo 'rows.sh: a disk image the rows made is still attached' >&2; return 1
    fi
}

main() {
    export UV_PYTHON=3.14
    mode=${1:-}
    case $mode in
        p1) ids="$P1_IDS $REAL_IDS" ;;
        p2|all) ids="$P1_IDS $P2_IDS $REAL_IDS" ;;
        *) echo 'usage: rows.sh p1|p2|all' >&2; return 2 ;;
    esac
    # shellcheck disable=SC2086
    run_ids '' $ids || return 1
    # shellcheck disable=SC2086
    run_ids modern $ids || return 1
    leftovers || return 1
    hints || return 1
    if [ "$mode" = all ]; then
        partition || return 1
        uv run pytest -q -p no:cacheprovider tests/test_hygiene.py || return 1
    fi
    echo "rows.sh: $mode ok"
}

main "$@"; exit $?
